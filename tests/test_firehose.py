"""REPO "Live subscription": durable bytes, bounded replay, and sparse MST inversion, without a Lean host or signing.

Refuted by a cursor changing bytes after compaction/restart, 201 ops or 2,000,001 CAR bytes becoming a
commit, or an inverse needing a node absent from the event, including root shrink and neighbour merges.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from transport.atproto.cbor import block, decode
from transport.atproto.mst import Tree, layer
from transport.firehose import EventLog, commit_event, create_op, fits, frame
from transport.atproto.mst import invert
from types import SimpleNamespace


class SyntheticSigned(SimpleNamespace):
    """A byte-only signed source for socket and restart-ordering tests."""
    def __init__(self, **values):
        super().__init__(events=False, pending={}, pending_bytes=0, **values)

    def release_events(self, height):
        with self.lock:
            for h in list(self.pending):
                if h <= height:
                    _, body = self.pending.pop(h)
                    self.pending_bytes -= len(body['blocks'])

    def stop_events(self):
        with self.lock:
            self.events = False


def inverse(blocks, root, ops):
    """Independent consumer: decode prefix keys, undo record changes, merge adjacent equal-layer ranges,
    keep intermediate layers, then collapse empty root layers (repository spec, MST inversion).
    Unvisited branches remain opaque CIDs; no server tree or inversion helper is used.
    """
    generated = {}

    def depth(key):
        import hashlib
        digest = ''.join(f'{byte:08b}' for byte in hashlib.sha256(key).digest())
        return (len(digest) - len(digest.lstrip('0'))) // 2

    def load(cid):
        if cid is None:
            return [], [None]
        n = decode(generated[cid] if cid in generated else blocks[cid])
        keys, last = [], b''
        for e in n['e']:
            last = last[:e['p']] + e['k']
            keys.append((last, e['v']))
        return keys, [n['l']] + [e['t'] for e in n['e']]

    def save(keys, branches):
        if not keys and branches[0] is None:
            return None
        last, entries = b'', []
        for (key, value), child in zip(keys, branches[1:]):
            prefix = 0
            while prefix < min(len(last), len(key)) and last[prefix] == key[prefix]:
                prefix += 1
            entries.append({'p': prefix, 'k': key[prefix:], 'v': value, 't': child})
            last = key
        cid, data = block({'l': branches[0], 'e': entries})
        generated[cid] = data
        return cid

    def join(a, b):
        if a is None or b is None:
            return b if a is None else a
        ka, ca = load(a)
        kb, cb = load(b)
        return save(ka + kb, ca[:-1] + [join(ca[-1], cb[0])] + cb[1:])

    def split(cid, key):
        if cid is None:
            return None, None
        keys, children = load(cid)
        i = sum(k < key for k, _ in keys)
        left, right = split(children[i], key)
        return save(keys[:i], children[:i] + [left]), save(keys[i:], [right] + children[i + 1:])

    def edit(cid, key, value, level):
        keys, children = load(cid) if cid else ([], [None])
        i = sum(k < key for k, _ in keys)
        if i < len(keys) and keys[i][0] == key:
            if value is None:
                return save(keys[:i] + keys[i + 1:], children[:i] + [join(children[i], children[i + 1])] + children[i + 2:])
            keys[i] = (key, value)
        elif value is not None and depth(key) == level:
            a, b = split(children[i], key)
            keys.insert(i, (key, value))
            children[i:i + 1] = [a, b]
        else:
            children[i] = edit(children[i], key, value, level - 1)
        return save(keys, children)

    def height(cid):
        keys, children = load(cid)
        return depth(keys[0][0]) if keys else (height(children[0]) + 1 if children[0] else 0)

    for op in reversed(ops):
        key = op['path'].encode()
        value = None if op['action'] == 'create' else op['prev']
        level = height(root)
        if value is not None and depth(key) > level:
            a, b = split(root, key)
            for _ in range(level + 1, depth(key)):
                a, b = save([], [a]) if a else None, save([], [b]) if b else None
            root = save([(key, value)], [a, b])
        else:
            root = edit(root, key, value, level)
        while True:
            keys, children = load(root)
            if keys or children[0] is None:
                break
            root = children[0]
    keys, children = load(root)
    return root if keys or children[0] else None


def tree(pairs):
    t = Tree()
    for key, value in sorted(pairs):
        t.append(key, value)
    t.root()
    return t


class Inversion(unittest.TestCase):
    def verify(self, before, after, ops):
        expected = before.root() if before.keys else None
        restored, nodes = invert(after, ops)
        self.assertEqual(restored, expected)
        self.assertEqual(inverse(dict(nodes), after.root(), ops), expected)
        from transport.atproto.mst import find
        for op in ops:
            self.assertEqual(find(dict(nodes), after.root(), op['path'].encode()), op['cid'])
        full = dict(after.blocks())
        if not after.keys:  # the zero-key root predates the default blocks(since=0) filter
            cid, data = block({'l': None, 'e': []})
            full[cid] = data
        self.assertLessEqual(dict(nodes).items(), full.items())
        return nodes

    def test_zero_ops_preserve_empty_and_nonempty_tree_data(self):
        empty = tree([])
        self.verify(empty, empty, [])
        held = tree([(b'online.fg-goose.gsb.entry/one', block({'v': 1})[0])])
        self.verify(held, held, [])

    def test_every_append_including_new_layers_and_rightmost_root_shrink(self):
        pairs, roots, shrinks = [], 0, 0
        value = block({'record': 'value'})[0]
        for i in range(1000):
            key = f'online.fg-goose.gsb.entry/{i:013d}'.encode()
            before = tree(pairs)
            pairs.append((key, value))
            after = tree(pairs)
            if layer(key) > before.top()[0]:
                roots += 1
                shrinks += int(bool(before.keys))
            self.verify(before, after, [{'action': 'create', 'path': key.decode(), 'cid': value}])
        self.assertGreater(roots, 0)
        self.assertGreater(shrinks, 0)

    def test_updates_deletes_and_mixed_ops_use_only_read_nodes(self):
        old, new = block({'v': 0})[0], block({'v': 1})[0]
        pairs = [(f'online.fg-goose.gsb.entry/{i:013d}'.encode(), old) for i in range(80)]
        before = tree(pairs)
        for i in range(80):
            key = pairs[i][0]
            self.verify(before, tree(pairs[:i] + pairs[i + 1:]),
                        [{'action': 'delete', 'path': key.decode(), 'cid': None, 'prev': old}])
            self.verify(before, tree([(k, new if k == key else v) for k, v in pairs]),
                        [{'action': 'update', 'path': key.decode(), 'cid': new, 'prev': old}])
        self.verify(tree([pairs[0]]), tree([]), [{'action': 'delete', 'path': pairs[0][0].decode(), 'cid': None, 'prev': old}])
        ops = [{'action': 'delete', 'path': pairs[i][0].decode(), 'cid': None, 'prev': old} for i in (0, 3, 79)]
        ops.append({'action': 'update', 'path': pairs[20][0].decode(), 'cid': new, 'prev': old})
        after = tree([(k, new if i == 20 else v) for i, (k, v) in enumerate(pairs) if i not in (0, 3, 79)])
        self.verify(before, after, ops)


class LogAndBudgets(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'events'

    def test_exact_budget_boundary_and_overflow_choose_sync(self):
        commit = block({'rev': 'revision'})
        for count, size, kind in ((200, 2_000_000, '#commit'), (201, 1, '#sync'), (1, 2_000_001, '#sync')):
            ops, blocks = [{}] * count, b'x' * size
            self.assertEqual(fits(ops, blocks), kind == '#commit')
            chosen, body = commit_event('did:web:test', commit, 'revision', None, None, ops, blocks)
            self.assertEqual(chosen, kind)
            if kind == '#sync':
                from transport.atproto.cbor import read_car
                self.assertEqual(read_car(body['blocks']), ([commit[0]], dict([commit])))

    def test_compaction_restart_and_torn_tail_preserve_retained_frames_and_seq(self):
        with patch('transport.firehose.WINDOW', 3):
            log = EventLog(self.path)
            events = [log.append('#sync', {'did': 'did:web:test', 'rev': str(i)}, 2, i) for i in range(8)]
            retained = log.retained()
            self.assertEqual([e.seq for e in retained], [6, 7, 8])
            self.assertEqual([e.frame for e in retained], [e.frame for e in events[-3:]])
            with self.path.open('ab') as f:
                f.write(b'\x00\x00')
            again = EventLog(self.path)
            self.assertEqual(again.retained(), retained)
            self.assertEqual(again.append('#identity', {'did': 'did:web:test'}, 3, 8).seq, 9)

    def test_complete_corrupt_sequence_is_refused_instead_of_truncated(self):
        log = EventLog(self.path)
        first = log.append('#sync', {}, 0, 1)
        with self.path.open('ab') as f:
            f.write(log.record(first))
        size = self.path.stat().st_size
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            EventLog(self.path)
        self.assertEqual(self.path.stat().st_size, size)

    def test_separate_endpoint_logs_do_not_use_overlapping_world_heights_as_seq(self):
        a, b = EventLog(self.path), EventLog(self.path.with_name('other'))
        for log in (a, b):
            self.assertEqual(log.append('#sync', {}, 0, 50).seq, 1)
            self.assertEqual(log.append('#identity', {}, 1, 50).seq, 2)
            self.assertEqual(log.append('#sync', {}, 1, 50).seq, 3)
        self.assertNotEqual(frame('#sync', {'seq': 1}), frame('#identity', {'seq': 1}))


class SelectorSockets(unittest.TestCase):
    """Actual listener with a synthetic signed head isolates RFC 6455 and cursor ordering from cryptography."""
    def setUp(self):
        import threading
        from types import SimpleNamespace
        from transport.firehose import Firehose
        from tests.firehose_client import Consumer
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        commit = block({'rev': 'head'})
        signed = SyntheticSigned(lock=threading.Lock(), ledger={'epochs': []}, base=0, heights=[None],
                                 head=SimpleNamespace(commit=commit, rev='head'), catch_up=lambda host: None)
        repo = SimpleNamespace(signed=signed, did='did:web:test', handle='test')
        self.hose = Firehose(repo, None, Path(tmp.name) / 'events', interval=60).start()
        self.addCleanup(self.hose.close)
        self.Consumer = Consumer

    def client(self, query=''):
        c = self.Consumer(self.hose.address, query)
        self.addCleanup(c.close)
        return c

    def test_replay_live_handoff_orders_queued_events_and_preserves_payloads(self):
        # Production and subscription run on one thread. Queue a head before subscribing; append at the
        # next poll while the socket is still draining replay. Large frames make that overlap observable.
        import time
        from transport.firehose import Firehose
        def production(hose, initial=False):
            if initial:
                for i in range(40):
                    hose.emit('#sync', {'did': 'did:web:test', 'rev': str(i), 'padding': b'x' * 50000}, 0, 1)
            elif hose.log.tail == 40 and any(s.live for s in hose.clients.values()):
                hose.emit('#identity', {'did': 'did:web:test'}, 0, 1)
        self.hose.close()
        with patch.object(Firehose, 'produce', production):
            self.hose = Firehose(self.hose.repo, None, self.hose.log.path.with_name('handoff'), interval=0.02).start()
            self.addCleanup(self.hose.close)
            c = self.client('?cursor=1')
            deadline = time.monotonic() + 30
            while self.hose.log.tail < 41 and time.monotonic() < deadline:
                self.assertIsNone(self.hose.error)
                time.sleep(0.01)
            expected = self.hose.log.retained()[1:]
            self.assertEqual(len(expected), 40)
            for event in expected:
                self.assertEqual(c.event()[2], event.frame)

    def test_cursor_errors_close_and_masked_ping_pong_close_are_served(self):
        import struct
        for query, error in (('?cursor=2', 'FutureCursor'), ('?cursor=x', 'InvalidRequest')):
            c = self.client(query)
            h, body, _ = c.event()
            self.assertEqual((h, body['error']), ({'op': -1}, error))
            self.assertEqual(c.raw()[0], 8)
            with self.assertRaises(EOFError):
                c.take(1)
        c = self.client()
        c.control(9, b'x' * 125)
        self.assertEqual(c.raw(), (10, b'x' * 125))
        c.control(10, b'hello')
        c.control(8, struct.pack('!H', 1000))
        self.assertEqual(c.raw(), (8, struct.pack('!H', 1000)))
        c = self.client()
        c.control(9, b'bad', masked=False)
        self.assertEqual(c.raw(), (8, struct.pack('!H', 1002)))


class SocketQueues(unittest.TestCase):
    """A socket pair isolates replay/live ordering and masking where a sandbox cannot bind TCP."""
    def test_stalled_close_discards_input_disables_reads_and_expires(self):
        import socket
        import selectors
        import time
        from types import SimpleNamespace
        from transport.firehose import Firehose, Subscriber
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        hose = Firehose(SimpleNamespace(signed=True), None, Path(tmp.name) / 'events')
        self.addCleanup(hose.selector.close)
        self.addCleanup(hose.wake_read.close)
        self.addCleanup(hose.wake_write.close)
        sock, peer = socket.socketpair()
        self.addCleanup(sock.close)
        self.addCleanup(peer.close)
        sock.setblocking(False)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        while True:
            try:
                sock.send(b'x' * 65536)
            except BlockingIOError:
                break
        sub = Subscriber()
        sub.upgraded = sub.live = True
        hose.clients[sock] = sub
        hose.selector.register(sock, selectors.EVENT_READ, sub)
        hose.queue(sock, sub, b'queued output')
        peer.sendall(b'\x89\x00' + b'x' * 1000)  # unmasked control after output has stalled
        now = time.monotonic()
        with patch('transport.firehose.time.monotonic', return_value=now):
            hose.read(sock, sub)
        self.assertTrue(sub.closing)
        self.assertEqual(sub.input, b'')
        self.assertEqual(hose.selector.get_key(sock).events, selectors.EVENT_WRITE)
        peer.setblocking(False)
        for _ in range(20):
            try:
                peer.send(b'x' * 1000)
            except BlockingIOError:
                pass
            hose.read(sock, sub)  # even a stale readiness notification cannot retain input
            hose.write(sock, sub)
        self.assertEqual(sub.input, b'')
        with patch('transport.firehose.time.monotonic', return_value=now + 1):
            hose.heartbeat()
        self.assertIn(sock, hose.clients)
        with patch('transport.firehose.time.monotonic', return_value=now + 6):
            hose.heartbeat()
        self.assertNotIn(sock, hose.clients)

    def test_queue_budget_disconnects_after_event_is_durably_logged(self):
        import socket
        import selectors
        from types import SimpleNamespace
        from transport.firehose import Firehose, Subscriber
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        hose = Firehose(SimpleNamespace(signed=True), None, Path(tmp.name) / 'events')
        self.addCleanup(hose.selector.close)
        self.addCleanup(hose.wake_read.close)
        self.addCleanup(hose.wake_write.close)
        sock, peer = socket.socketpair()
        self.addCleanup(sock.close)
        self.addCleanup(peer.close)
        sub = Subscriber()
        sub.upgraded = sub.live = True
        hose.clients[sock] = sub
        hose.selector.register(sock, selectors.EVENT_READ, sub)
        with patch('transport.firehose.MAX_QUEUED', 1):
            event = hose.emit('#sync', {'did': 'did:web:test', 'rev': 'one'}, 0, 1)
        self.assertNotIn(sock, hose.clients)
        self.assertEqual(EventLog(hose.log.path).retained(), [event])

    def test_live_frame_waits_behind_every_replay_frame(self):
        import socket
        import selectors
        from types import SimpleNamespace
        from transport.firehose import Firehose, Subscriber
        from tests.firehose_client import Consumer
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        hose = Firehose(SimpleNamespace(signed=True), None, Path(tmp.name) / 'events')
        self.addCleanup(hose.selector.close)
        self.addCleanup(hose.wake_read.close)
        self.addCleanup(hose.wake_write.close)
        sock, client = socket.socketpair()
        self.addCleanup(sock.close)
        self.addCleanup(client.close)
        sock.setblocking(False)
        sub = Subscriber()
        sub.upgraded = sub.live = True
        hose.clients[sock] = sub
        hose.selector.register(sock, selectors.EVENT_READ, sub)
        a = hose.log.append('#sync', {'did': 'did:web:test', 'rev': 'one'}, 0, 1)
        b = hose.log.append('#sync', {'did': 'did:web:test', 'rev': 'two'}, 0, 1)
        sub.replay = [a, b]
        c = hose.emit('#identity', {'did': 'did:web:test'}, 0, 1)
        reader = Consumer.__new__(Consumer)
        reader.socket, reader.buffer = client, bytearray()
        for event in (a, b, c):
            while sub.output or sub.replay or sub.pending:
                hose.write(sock, sub)
                if not sub.output or len(sub.output) < 1000:
                    break
            hose.write(sock, sub)
            self.assertEqual(reader.event()[2], event.frame)
        payload = b'x' * 125
        client.sendall(b'\x89\xfdabcd' + bytes(v ^ b'abcd'[i % 4] for i, v in enumerate(payload)))
        hose.read(sock, sub)
        hose.write(sock, sub)
        self.assertEqual(reader.raw(), (10, payload))
        client.sendall(b'\x89\x00')
        hose.read(sock, sub)
        hose.write(sock, sub)
        self.assertEqual(reader.raw(), (8, b'\x03\xea'))

    def test_cursor_handshake_and_huge_integer_controls_without_a_tcp_bind(self):
        import socket
        import selectors
        from types import SimpleNamespace
        from transport.firehose import Firehose, Subscriber, ROUTE
        from tests.firehose_client import Consumer
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        hose = Firehose(SimpleNamespace(signed=True), None, Path(tmp.name) / 'events')
        self.addCleanup(hose.selector.close)
        self.addCleanup(hose.wake_read.close)
        self.addCleanup(hose.wake_write.close)
        for i in range(8):
            hose.log.append('#sync', {'rev': str(i)}, 0, 1)
        for cursor, expected in (('9' * 5000, 'FutureCursor'), ('no', 'InvalidRequest'), ('0', 'OutdatedCursor')):
            sock, client = socket.socketpair()
            self.addCleanup(sock.close)
            self.addCleanup(client.close)
            sub = Subscriber()
            hose.clients[sock] = sub
            hose.selector.register(sock, selectors.EVENT_READ, sub)
            request = (f'GET {ROUTE}?cursor={cursor} HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n'
                       'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n'
                       'Sec-WebSocket-Key: YWJjZGVmZ2hpamtsbW5vcA==')
            hose.handshake(sock, sub, request.encode())
            # Leave the registered socket open until this test has consumed all queued bytes.
            wire = bytes(sub.output)
            self.assertTrue(wire.startswith(b'HTTP/1.1 101'))
            _, _, payload = wire.partition(b'\r\n\r\n')
            reader = Consumer.__new__(Consumer)
            reader.socket, reader.buffer = client, bytearray(payload)
            header, body, _ = reader.event()
            self.assertEqual(body.get('error') or body.get('name'), expected)
            self.assertEqual(header['op'], 1 if expected == 'OutdatedCursor' else -1)
            if expected != 'OutdatedCursor':
                self.assertEqual(reader.raw()[0], 8)
            hose.drop(sock)

    def test_empty_start_announces_first_live_height_as_commit_with_null_since_and_prev_data(self):
        import threading
        from types import SimpleNamespace
        from transport.atproto.cbor import car
        from transport.firehose import Firehose
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        signed = SyntheticSigned(lock=threading.Lock(), ledger={'epochs': [], 'head': None}, base=0,
                                 heights=[], head=None, catch_up=lambda host: None)
        hose = Firehose(SimpleNamespace(signed=signed, did='did:web:test', handle='test'), None, Path(tmp.name) / 'events')
        self.addCleanup(hose.selector.close)
        self.addCleanup(hose.wake_read.close)
        self.addCleanup(hose.wake_write.close)
        hose.produce(initial=True)
        self.assertEqual(hose.log.tail, 0)
        record = block({'$type': 'online.fg-goose.gsb.entry', 'height': 1})
        commit = block({'rev': 'one'})
        item = SimpleNamespace(record=record, commit=commit, rev='one', prev_data=None)
        signed.pending[1] = commit_event('did:web:test', commit, 'one', None, None,
                                       [create_op('one', record)], car(commit[0], [commit, record]))
        signed.pending_bytes = len(signed.pending[1][1]['blocks'])
        signed.heights.append(item)
        signed.head = item
        signed.ledger['head'] = {'height': 1, 'rev': 'one'}
        hose.produce()
        event = hose.log.retained()[0]
        self.assertEqual(event.kind, '#commit')
        self.assertEqual((event.seq, event.body['since'], event.body['prevData']), (1, None, None))

    def test_host_unavailable_poll_retries_without_sequence_and_storage_failure_is_fatal(self):
        from types import SimpleNamespace
        from transport.firehose import Firehose
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        hose = Firehose(SimpleNamespace(signed=True), None, Path(tmp.name) / 'events')
        self.addCleanup(hose.selector.close)
        self.addCleanup(hose.wake_read.close)
        self.addCleanup(hose.wake_write.close)
        failure = RuntimeError('host disconnected')
        failure.body = {'reply': {'class': 'hostUnavailable'}}
        with patch.object(hose, 'produce', side_effect=failure):
            hose.poll()
        self.assertIs(hose.poll_error, failure)
        self.assertEqual(hose.log.tail, 0)
        with patch.object(hose, 'produce'):
            hose.poll()
        self.assertIsNone(hose.poll_error)
        with patch.object(hose, 'produce', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                hose.poll()

    def test_interrupted_identity_is_not_duplicated_and_pending_sync_finishes_epoch(self):
        import threading
        from types import SimpleNamespace
        from transport.firehose import Firehose
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        commit = block({'rev': 'after-rotation'})
        signed = SyntheticSigned(lock=threading.Lock(), ledger={'epochs': [{'cause': 'rotation'}]},
                                 base=0, heights=[None], head=SimpleNamespace(commit=commit, rev='after-rotation'),
                                 catch_up=lambda host: None)
        hose = Firehose(SimpleNamespace(signed=signed, did='did:web:test', handle='test'), None, Path(tmp.name) / 'events')
        self.addCleanup(hose.selector.close)
        self.addCleanup(hose.wake_read.close)
        self.addCleanup(hose.wake_write.close)
        hose.log.append('#sync', {'rev': 'before'}, 0, 1)
        identity = hose.log.append('#identity', {'did': 'did:web:test', 'handle': 'test'}, 1, 1)
        hose.produce(initial=True)
        self.assertEqual([e.kind for e in hose.log.retained()], ['#sync', '#identity', '#sync'])
        self.assertEqual(hose.log.retained()[1], identity)
        self.assertEqual(hose.log.tail, 3)
        hose.produce(initial=True)
        self.assertEqual(hose.log.tail, 3)


if __name__ == '__main__':
    unittest.main()
