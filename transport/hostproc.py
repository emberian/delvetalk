"""Host processes and the clients of the one that owns the world.

Host / Heaps run `delvetalk-obend` in-process: used by hostd (the only daemon that does) and by
tests. HostClient / RemoteHeaps are what every other program uses: one JSON
line per op over hostd's unix socket (<state>/host.sock).
"""
import collections
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

BINARY = os.environ.get('DELVETALK_OBEND', '/Users/ember/dev/delvetalk2/.lake/build/bin/delvetalk-obend')
LIBRARY = Path(__file__).resolve().parent.parent / 'world' / 'lib'
# The packages `world-arrive` creates from; the sealed library must hold them or arrival creates nothing.
ARRIVAL = ('Avatar', 'Env', 'Wake')
OBJECTS = LIBRARY.parent / 'objects'
HOST_TIMEOUT, POOL = 120, 8
DID_RE = __import__('re').compile(r'did:plc:[a-z2-7]{24}\Z')


class HostDied(Exception):
    pass


class Host:
    """One host subprocess, one request at a time; respawned and reopened if it dies.
    With journal=None it is a stateless compile/run process."""

    def __init__(self, journal, binary=BINARY, clock=None, opener=None, library=None, librarian=None, preload=None, sync='fsync', post_quota=None):
        self.post_quota = post_quota  # world-open {postQuota}: the hourly post cap, journaled at first naming (host default 16)
        self.sync = sync  # world-open {sync}: "none" flushes, "fsync" (the default) asks the OS to write the bytes out, "full" forces the disk
        self.preload, self.pin = preload, None  # a stateless process loads this library at each spawn; pin is its answer
        self.journal, self.binary, self.proc, self.clock, self.opener = journal, binary, None, clock, opener
        # A library directory is sealed into the journal at its first open, as `librarian` (who may change it).
        self.library = {'library': str(library), 'principal': librarian} if library and librarian else {}
        self.lock = threading.Lock()

    def _spawn(self):
        self.proc = subprocess.Popen([self.binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        if self.journal:
            reply = self._exchange({'op': 'world-open', 'path': self.journal, **({'clock': self.clock} if self.clock else {}),
                                     **({'opener': self.opener} if self.opener else {}), **({'postQuota': self.post_quota} if self.post_quota else {}), **self.library, 'sync': self.sync})
            if reply.get('status') != 'opened':
                raise HostDied('world-open refused: ' + json.dumps(reply))
        elif self.preload:
            reply = self._exchange({'op': 'library-load', 'path': str(self.preload)})
            if reply.get('status') != 'library':
                raise HostDied('library-load refused: ' + json.dumps(reply))
            self.pin = reply['pin']

    def _exchange(self, request):
        watchdog = threading.Timer(HOST_TIMEOUT, self.proc.kill)
        watchdog.start()
        try:
            self.proc.stdin.write(json.dumps(request) + '\n')
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        except (BrokenPipeError, OSError, ValueError):
            line = ''
        finally:
            watchdog.cancel()
        if not line:
            raise HostDied('host closed its output')
        return json.loads(line)

    def send(self, request):
        """A turn is retried once after a restart: the host answers a repeated identity with the original receipt."""
        with self.lock:
            for attempt in (0, 1):
                try:
                    if self.proc is None or self.proc.poll() is not None:
                        self.close()
                        self._spawn()
                    return self._exchange(request)
                except (HostDied, ValueError):
                    self.close()
                    if attempt:
                        return {'status': 'error', 'class': 'hostUnavailable', 'message': 'host unavailable'}

    def close(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait()
            for s in (self.proc.stdin, self.proc.stdout):
                s.close()
            self.proc = None


class Heaps:
    """Per-principal journals, each in its own host process; least recently used evicted.
    A heap is reopened by the host's replay, so eviction loses nothing."""

    def __init__(self, directory, size=POOL, binary=BINARY, library=None):
        self.dir, self.size, self.binary, self.library = Path(directory), size, binary, library
        self.pool = collections.OrderedDict()

    def journal(self, did):
        return self.dir / f'{did}.journal'

    def get(self, did):
        if did in self.pool:
            self.pool.move_to_end(did)
            return self.pool[did]
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        while len(self.pool) >= self.size:
            self.pool.popitem(last=False)[1].close()
        self.pool[did] = Host(str(self.journal(did)), self.binary, library=self.library, librarian=did)
        return self.pool[did]

    def close(self):
        for h in self.pool.values():
            h.close()
        self.pool.clear()


# Ops the host answers the same way when sent twice: reads, and a turn (bound to its identity). Only these are
# re-sent on a new connection after a broken one; any other op surfaces "hostd unavailable" and the caller decides.
IDEMPOTENT = frozenset({'world-status', 'world-view', 'world-card', 'world-objects', 'world-offers', 'world-history', 'world-receipt',
                        'world-resolve', 'world-inspect', 'world-entries', 'world-entry', 'world-object', 'world-publications',
                        'world-grants', 'world-source', 'world-sources', 'world-state-cid', 'world-addressee', 'hostd-info', 'world-turn'})


class HostClient:
    """Same send() as Host, over hostd's socket. heap=<did> addresses a private heap; stateless=True the REPL process.
    One persistent connection per thread, re-made on EOF or when the socket path names a different hostd (a restart).
    hostd serves connections concurrently and still runs ops one at a time, in arrival order."""

    def __init__(self, path, heap=None, stateless=False, timeout=HOST_TIMEOUT + 30):
        self.path, self.heap, self.stateless, self.timeout = str(path), heap, stateless, timeout
        self.local = threading.local()

    def _connection(self):
        """-> (socket, reader, fresh). A held connection is dropped if the socket file is no longer the one it reached."""
        held = getattr(self.local, 'conn', None)
        if held is not None:
            try:
                if os.stat(self.path).st_ino == held[2]:
                    return held[0], held[1], False
            except OSError:
                pass
            self.close()
        s, deadline = socket.socket(socket.AF_UNIX), time.monotonic() + self.timeout
        try:
            s.settimeout(self.timeout)
            while True:  # a full accept backlog answers EAGAIN at once; nothing was sent, so any op may wait and connect again
                try:
                    s.connect(self.path)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.01)
            self.local.conn = (s, s.makefile('rb'), os.stat(self.path).st_ino)
        except OSError:
            s.close()
            raise
        return self.local.conn[0], self.local.conn[1], True

    def send(self, request):
        envelope = dict(request)
        if self.heap:
            envelope['heap'] = self.heap
        if self.stateless:
            envelope['stateless'] = True
        data = (json.dumps(envelope) + '\n').encode()
        for _ in (0, 1):
            fresh = True
            try:
                s, reader, fresh = self._connection()
                s.sendall(data)
                line = reader.readline()
                if not line:
                    raise OSError('hostd closed the connection')
                return json.loads(line)
            except TimeoutError:  # hostd took the request and did not answer; a turn it ran may still commit: never re-sent
                self.close()
                return {'status': 'error', 'class': 'hostTimeout', 'message': f'hostd did not answer within {self.timeout} seconds'}
            except (OSError, ValueError):
                self.close()
                if fresh or request.get('op') not in IDEMPOTENT:  # a stale reused connection: once more on a new one, if the op is safe to repeat
                    break
        return {'status': 'error', 'class': 'hostUnavailable', 'message': 'hostd unavailable'}

    def close(self):
        held = getattr(self.local, 'conn', None)
        self.local.conn = None
        if held is not None:
            for f in (held[1], held[0]):
                try:
                    f.close()
                except OSError:
                    pass


class RemoteHeaps:
    """Heaps owned by hostd: a handle per principal; the pool lives in the daemon."""

    def __init__(self, path, directory):
        self.path, self.dir = path, Path(directory)

    def get(self, did, create=True):
        if not create and not (self.dir / f'{did}.journal').exists():
            return None
        return HostClient(self.path, heap=did)

    def close(self):
        pass


def connect(args):
    """The host a program talks to: hostd's socket."""
    return HostClient(args.host_socket or Path(args.state) / 'host.sock')


def add_host_args(ap):
    ap.add_argument('--host-socket', metavar='PATH', help='hostd socket (default <state>/host.sock)')
