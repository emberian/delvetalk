"""One durable event log and one selector thread per front/world (docs/REPO.md, ATPROTO L4).

Sequence positions belong to emitted events, never journal heights. The log stores exact DAG-CBOR
message bytes with coverage metadata; replay cannot re-sign or rebuild them. The selector thread owns
production, the listener and all subscriber sockets, independently of the HTTP worker pool.
"""
import base64
import hashlib
import os
import re
import selectors
import socket
import struct
import threading
import time
import traceback
import urllib.parse
from collections import deque, namedtuple
from datetime import datetime, timezone
from pathlib import Path

from transport.atproto.cbor import car, decode, encode

WINDOW = 10_000  # retained events; atomic compaction at twice this many physical records
MAX_OPS, MAX_BLOCKS = 200, 2_000_000
ROUTE = '/xrpc/com.atproto.sync.subscribeRepos'
MAX_HEADER = 16_384
MAX_PENDING = 32 * 1024 * 1024  # a slow subscriber reconnects with its cursor instead of growing unbounded queues
MAX_QUEUED = 128 * 1024 * 1024  # aggregate queued bytes share the front container with HTTP
MAX_CLIENTS = 128
HANDSHAKE_SECONDS, PING_SECONDS = 10, 30
GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


def frame(kind, body):
    """The event-stream message: two DAG-CBOR values in one binary WebSocket message."""
    return encode({'op': 1, 't': kind} if kind else {'op': -1}) + encode(body)


def websocket(payload, opcode=2):
    n = len(payload)
    length = bytes([n]) if n < 126 else (b'\x7e' + struct.pack('!H', n) if n < 65536 else b'\x7f' + struct.pack('!Q', n))
    return bytes([0x80 | opcode]) + length + payload


def fits(ops, blocks):
    return len(ops) <= MAX_OPS and len(blocks) <= MAX_BLOCKS


def create_op(rkey, record):
    """One record path for the signed tree, inversion and the event's operation list."""
    return {'action': 'create', 'path': decode(record[1])['$type'] + '/' + rkey, 'cid': record[0]}


def sync_event(did, commit, rev):
    return '#sync', {'did': did, 'blocks': car(commit[0], [commit]), 'rev': rev}


def commit_event(did, commit, rev, since, prev_data, ops, blocks):
    """The single budget decision, shared by production and synthetic boundary tests."""
    if not fits(ops, blocks):
        return sync_event(did, commit, rev)
    return '#commit', {'repo': did, 'commit': commit[0], 'rev': rev, 'since': since,
                       'prevData': prev_data, 'blocks': blocks, 'ops': ops, 'blobs': [],
                       'rebase': False, 'tooBig': False}


class Event(namedtuple('Event', 'seq kind epoch height frame')):
    __slots__ = ()

    @property
    def body(self):
        return decode(self.frame[len(encode({'op': 1, 't': self.kind})):])


class EventLog:
    """State.firehose: length-prefixed DAG-CBOR {seq, kind, epoch, height, frame} records in one file.

    Append + fsync precedes delivery. A partial final record was never delivered and is truncated on
    opening; corruption of a complete record fails closed. The newest WINDOW events are available even
    before compaction; rewrite at 2*WINDOW preserves their bytes and fsyncs the containing directory.
    One front owns the file. Its lock orders append, replay snapshot and live subscription registration.
    """
    def __init__(self, path):
        self.path, self.rows, self.lock = Path(path), [], threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.exists():
            with self.path.open('r+b') as f:
                valid = 0
                while True:
                    size = f.read(4)
                    if not size:
                        break
                    if len(size) < 4:
                        break
                    n = struct.unpack('!I', size)[0]
                    if n > 5_100_000:
                        raise ValueError('firehose record exceeds the event limit')
                    data = f.read(n)
                    if len(data) < n:
                        break
                    row = Event(**decode(data))
                    if self.rows and row.seq != self.rows[-1].seq + 1:
                        raise ValueError('firehose sequence is not contiguous')
                    if row.kind not in ('#commit', '#sync', '#identity') or not row.frame.startswith(encode({'op': 1, 't': row.kind})):
                        raise ValueError('firehose record does not contain its declared event header')
                    if type(row.seq) is not int or row.seq < 1 or type(row.body['seq']) is not int or row.body['seq'] != row.seq:
                        raise ValueError('firehose frame sequence differs from its log record')
                    self.rows.append(row)
                    valid = f.tell()
                if f.tell() != valid:
                    f.truncate(valid)
                    f.flush()
                    os.fsync(f.fileno())
        if len(self.rows) >= 2 * WINDOW:
            self._compact()

    @property
    def tail(self):
        return self.rows[-1].seq if self.rows else 0

    def retained(self):
        with self.lock:
            return self.rows[-WINDOW:]

    def coverage(self):
        return next((e for e in reversed(self.rows) if e.kind in ('#sync', '#commit')), None)

    @staticmethod
    def record(event):
        data = encode(event._asdict())
        return struct.pack('!I', len(data)) + data

    def directory_sync(self):
        fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _compact(self):
        kept = self.rows[-WINDOW:]
        tmp = self.path.with_name(self.path.name + '.tmp')
        with tmp.open('wb') as f:
            for row in kept:
                f.write(self.record(row))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        self.directory_sync()
        self.rows = kept

    def append(self, kind, body, epoch, height):
        with self.lock:
            seq = self.tail + 1
            body = {**body, 'seq': seq, 'time': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')}
            event = Event(seq, kind, epoch, height, frame(kind, body))
            first = not self.path.exists()
            with self.path.open('ab') as f:
                f.write(self.record(event))
                f.flush()
                os.fsync(f.fileno())
            if first:
                self.directory_sync()
            self.rows.append(event)
            if len(self.rows) >= 2 * WINDOW:
                self._compact()
            return event


class Subscriber:
    def __init__(self):
        self.input, self.output = bytearray(), bytearray()
        self.upgraded, self.live, self.closing = False, False, False
        self.replay, self.replay_at = [], 0
        self.pending, self.pending_bytes = deque(), 0
        self.opened = self.activity = time.monotonic()
        self.ping, self.ping_at = None, None


class Firehose:
    """start() performs the initial reconciliation on the owning thread before returning the address.
    close() wakes that thread and joins it. No subscriber or journal polling thread is created.
    """
    def __init__(self, repo, host, path, address=('127.0.0.1', 0), interval=1.0):
        if repo.signed is None:
            raise ValueError('a firehose requires a signed repository')
        self.repo, self.host, self.log = repo, host, EventLog(path)
        self.address, self.interval = address, interval
        self.stop, self.ready = threading.Event(), threading.Event()
        self.error, self.poll_error, self.thread = None, None, None
        self.selector = selectors.DefaultSelector()
        self.clients = {}
        self.wake_read, self.wake_write = socket.socketpair()
        self.wake_read.setblocking(False)
        self.selector.register(self.wake_read, selectors.EVENT_READ, 'wake')
        self.listener, self.empty_epoch = None, None

    def start(self):
        self.thread = threading.Thread(target=self.run, name='firehose', daemon=True)
        self.thread.start()
        self.ready.wait()
        if self.error:
            self.close()
            raise self.error
        return self

    def close(self):
        self.stop.set()
        try:
            self.wake_write.send(b'x')
        except OSError:
            pass
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join()

    def emit(self, kind, body, epoch, height):
        with self.log.lock:
            event = self.log.append(kind, body, epoch, height)
            wire = websocket(event.frame)
            for sock, sub in list(self.clients.items()):
                if sub.live and not sub.closing:
                    self.queue(sock, sub, wire)
            return event

    def produce(self, initial=False):
        signed = self.repo.signed
        signed.catch_up(self.host)
        with signed.lock:
            epoch, height = len(signed.ledger['epochs']), signed.base + len(signed.heights)
            head, base = signed.head, signed.base
            virgin = signed.ledger.get('head') is None
            epochs = list(signed.ledger['epochs'])
            last = self.log.coverage()
            new = signed.heights[max(0, last.height - signed.base) if last else 0:]
        if head is None:
            if initial and last is None and virgin:
                self.empty_epoch = epoch
            return
        live_empty = last is None and not initial and self.empty_epoch == epoch
        if initial or (last is None and not live_empty) or (last is not None and last.epoch != epoch):
            if last is not None and last.epoch == epoch and last.height == height and last.body['rev'] == head.rev:
                return
            announced = last.epoch if last else 0
            rotations = [i + 1 for i, e in enumerate(epochs) if i + 1 > announced and e['cause'] == 'rotation']
            tail = self.log.rows[-1] if self.log.rows else None
            if rotations and not (tail and tail.kind == '#identity' and tail.epoch == epoch):
                self.emit('#identity', {'did': self.repo.did, 'handle': self.repo.handle}, epoch, height)
            kind, body = sync_event(self.repo.did, head.commit, head.rev)
            self.emit(kind, body, epoch, height)
            return
        # HTTP may have caught up Signed: logged coverage is the watermark. Release the chain lock
        # before log fsyncs and socket queuing so production does not hold ordinary signed reads.
        since = last.body['rev'] if last else None
        for h, item in enumerate(new, last.height + 1 if last else base + 1):
            ops = [create_op(item.rev, item.record)]
            kind, body = commit_event(self.repo.did, item.commit, item.rev, since, item.prev_data, ops, item.blocks)
            self.emit(kind, body, epoch, h)
            since = item.rev

    def poll(self):
        try:
            self.produce()
            self.poll_error = None
        except Exception as err:
            # An unavailable host will reconnect on the next poll. Invalid journal data and failed
            # durable writes are fatal: retrying them could announce an uncertain chain.
            reply = getattr(err, 'body', {}).get('reply') or {}
            if reply.get('class') not in ('hostUnavailable', 'hostTimeout'):
                raise
            self.poll_error = err

    def run(self):
        try:
            self.produce(initial=True)
            self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listener.bind(self.address)
            self.listener.listen(128)
            self.listener.setblocking(False)
            self.address = self.listener.getsockname()
            self.selector.register(self.listener, selectors.EVENT_READ, 'listener')
            self.ready.set()
            next_poll = time.monotonic() + self.interval
            while not self.stop.is_set():
                now = time.monotonic()
                if now >= next_poll:
                    self.poll()
                    next_poll = time.monotonic() + self.interval
                for key, mask in self.selector.select(max(0, min(0.25, next_poll - time.monotonic()))):
                    sock, sub = key.fileobj, key.data
                    if sub == 'wake':
                        self.wake_read.recv(1024)
                    elif sub == 'listener':
                        self.accept()
                    else:
                        try:
                            if mask & selectors.EVENT_READ:
                                self.read(sock, sub)
                            if sock in self.clients and mask & selectors.EVENT_WRITE:
                                self.write(sock, sub)
                        except (OSError, ValueError, UnicodeError):
                            self.drop(sock)
                self.heartbeat()
        except Exception as err:
            self.error = err
            traceback.print_exc()
        finally:
            self.ready.set()
            for sock in list(self.clients):
                self.drop(sock)
            if self.listener:
                self.listener.close()
            self.wake_read.close()
            self.wake_write.close()
            self.selector.close()

    def accept(self):
        while True:
            try:
                sock, _ = self.listener.accept()
            except BlockingIOError:
                return
            if len(self.clients) >= MAX_CLIENTS:
                sock.close()
                continue
            sock.setblocking(False)
            sub = Subscriber()
            self.clients[sock] = sub
            self.selector.register(sock, selectors.EVENT_READ, sub)

    def drop(self, sock):
        if sock in self.clients:
            self.selector.unregister(sock)
            del self.clients[sock]
            sock.close()

    def interest(self, sock, sub):
        if sock in self.clients:
            self.selector.modify(sock, selectors.EVENT_READ | (selectors.EVENT_WRITE if sub.output or sub.replay or sub.pending else 0), sub)

    def room(self, sock, sub, size):
        held = sum(len(s.output) + s.pending_bytes for s in self.clients.values())
        if len(sub.output) + sub.pending_bytes + size > MAX_PENDING or held + size > MAX_QUEUED:
            self.drop(sock)
            return False
        return True

    def queue(self, sock, sub, data):
        if not self.room(sock, sub, len(data)):
            return
        if sub.replay or sub.pending:
            sub.pending.append(data)
            sub.pending_bytes += len(data)
        else:
            sub.output.extend(data)
        self.interest(sock, sub)

    def finish(self, sock, sub, code=1000, payload=None):
        sub.live, sub.closing, sub.replay = False, True, []
        self.queue(sock, sub, websocket(struct.pack('!H', code) if payload is None else payload, 8))

    def error_frame(self, sock, sub, error, message):
        self.queue(sock, sub, websocket(frame(None, {'error': error, 'message': message})))
        self.finish(sock, sub)

    def handshake(self, sock, sub, raw):
        lines = raw.decode('ascii').split('\r\n')
        method, target, version = lines[0].split(' ')
        headers = {}
        for line in lines[1:]:
            k, v = line.split(':', 1)
            k = k.lower()
            if k in headers:
                raise ValueError('duplicate header')
            headers[k] = v.strip()
        url = urllib.parse.urlsplit(target)
        try:
            key = headers['sec-websocket-key']
            valid_key = len(base64.b64decode(key, validate=True)) == 16
        except (KeyError, ValueError):
            valid_key = False
        if (method != 'GET' or version != 'HTTP/1.1' or url.path != ROUTE or not headers.get('host') or
                headers.get('upgrade', '').lower() != 'websocket' or
                'upgrade' not in [v.strip().lower() for v in headers.get('connection', '').split(',')] or
                headers.get('sec-websocket-version') != '13' or not valid_key):
            sub.closing = True
            self.queue(sock, sub, b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            return
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest())
        self.queue(sock, sub, b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                   b'Sec-WebSocket-Accept: ' + accept + b'\r\n\r\n')
        sub.upgraded = True
        q = urllib.parse.parse_qs(url.query, keep_blank_values=True)
        cursor = q.get('cursor')
        if cursor is not None and (len(cursor) != 1 or not re.fullmatch(r'-?[0-9]+', cursor[0])):
            return self.error_frame(sock, sub, 'InvalidRequest', 'cursor must be one integer')
        n = None
        if cursor is not None:
            digits = cursor[0].lstrip('-').lstrip('0') or '0'
            # Only its ordering matters beyond the largest possible seq; avoid Python's decimal digit cap.
            n = (int(digits) if len(digits) <= 20 else self.log.tail + 1) * (-1 if cursor[0].startswith('-') else 1)
        with self.log.lock:
            tail, retained = self.log.tail, self.log.retained()
            if n is not None and n > tail:
                return self.error_frame(sock, sub, 'FutureCursor', f'cursor is beyond newest sequence {tail}')
            if n is not None:
                if retained and n < retained[0].seq:
                    self.queue(sock, sub, websocket(frame('#info', {'name': 'OutdatedCursor'})))
                sub.replay = [e for e in retained if e.seq > n]
            # The replay snapshot and live registration share append's ordering. Live queues wait behind replay.
            sub.live = True
            self.interest(sock, sub)

    def read(self, sock, sub):
        data = sock.recv(65536)
        if not data:
            return self.drop(sock)
        sub.input.extend(data)
        if not sub.upgraded:
            end = sub.input.find(b'\r\n\r\n')
            if end < 0:
                if len(sub.input) > MAX_HEADER:
                    self.drop(sock)
                return
            if end > MAX_HEADER:
                return self.drop(sock)
            raw = bytes(sub.input[:end])
            del sub.input[:end + 4]
            self.handshake(sock, sub, raw)
        while sub.upgraded and not sub.closing and len(sub.input) >= 2:
            first, second = sub.input[:2]
            opcode, n, at = first & 15, second & 127, 2
            if first & 0x70 or not second & 0x80 or opcode not in (8, 9, 10) or not first & 0x80 or n > 125:
                return self.finish(sock, sub, 1002)
            if len(sub.input) < at + 4 + n:
                return
            mask = sub.input[at:at + 4]
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(sub.input[at + 4:at + 4 + n]))
            del sub.input[:at + 4 + n]
            sub.activity = time.monotonic()
            if opcode == 8:
                if len(payload) == 1:
                    return self.finish(sock, sub, 1002)
                if len(payload) >= 2:
                    code = int.from_bytes(payload[:2], 'big')
                    if code not in (1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014) and not 3000 <= code <= 4999:
                        return self.finish(sock, sub, 1002)
                    try:
                        payload[2:].decode('utf8')
                    except UnicodeError:
                        return self.finish(sock, sub, 1007)
                return self.finish(sock, sub, payload=payload)
            if opcode == 9:
                self.queue(sock, sub, websocket(payload, 10))
            elif payload == sub.ping:
                sub.ping = None

    def write(self, sock, sub):
        # Replay has priority over all post-snapshot events, but the HTTP upgrade/info goes first.
        if sub.output:
            try:
                sent = sock.send(sub.output)
            except BlockingIOError:
                return
            del sub.output[:sent]
        if not sub.output and sub.replay:
            event = sub.replay[sub.replay_at]
            wire = websocket(event.frame)
            if not self.room(sock, sub, len(wire)):
                return
            sub.replay_at += 1
            if sub.replay_at == len(sub.replay):
                sub.replay, sub.replay_at = [], 0
            sub.output.extend(wire)
        if not sub.output and sub.pending:
            data = sub.pending.popleft()
            sub.pending_bytes -= len(data)
            sub.output.extend(data)
        if not sub.output and sub.closing:
            return self.drop(sock)
        self.interest(sock, sub)

    def heartbeat(self):
        now = time.monotonic()
        for sock, sub in list(self.clients.items()):
            if not sub.upgraded and now - sub.opened > HANDSHAKE_SECONDS:
                self.drop(sock)
            elif sub.upgraded and not sub.closing:
                if sub.ping is not None and now - sub.ping_at > PING_SECONDS:
                    self.finish(sock, sub, 1001)
                elif sub.ping is None and now - sub.activity > PING_SECONDS:
                    sub.ping, sub.ping_at = os.urandom(4), now
                    self.queue(sock, sub, websocket(sub.ping, 9))
