"""Host processes and the clients of the one that owns the world.

Host / Heaps run `delvetalk-obend` in-process: used by hostd (the only daemon that does) and by
tests and --standalone runs. HostClient / RemoteHeaps are what every other program uses: one JSON
line per op over hostd's unix socket (<state>/host.sock).
"""
import collections
import json
import os
import socket
import subprocess
import threading
from pathlib import Path

BINARY = os.environ.get('DELVETALK_OBEND', '/Users/ember/dev/delvetalk2/.lake/build/bin/delvetalk-obend')
HOST_TIMEOUT, POOL = 120, 8
DID_RE = __import__('re').compile(r'did:plc:[a-z2-7]{24}\Z')


class HostDied(Exception):
    pass


class Host:
    """One host subprocess, one request at a time; respawned and reopened if it dies.
    With journal=None it is a stateless compile/run process."""

    def __init__(self, journal, binary=BINARY, clock=None):
        self.journal, self.binary, self.proc, self.clock = journal, binary, None, clock
        self.lock = threading.Lock()

    def _spawn(self):
        self.proc = subprocess.Popen([self.binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        if self.journal:
            reply = self._exchange({'op': 'world-open', 'path': self.journal, **({'clock': self.clock} if self.clock else {})})
            if reply.get('status') != 'opened':
                raise HostDied('world-open refused: ' + json.dumps(reply))

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
                        return {'status': 'error', 'message': 'host unavailable'}

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

    def __init__(self, directory, size=POOL, binary=BINARY):
        self.dir, self.size, self.binary = Path(directory), size, binary
        self.pool = collections.OrderedDict()

    def journal(self, did):
        return self.dir / f'{did}.journal'

    def get(self, did, create=True):
        if did in self.pool:
            self.pool.move_to_end(did)
            return self.pool[did]
        if not create and not self.journal(did).exists():
            return None
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        while len(self.pool) >= self.size:
            self.pool.popitem(last=False)[1].close()
        self.pool[did] = Host(str(self.journal(did)), self.binary)
        return self.pool[did]

    def close(self):
        for h in self.pool.values():
            h.close()
        self.pool.clear()


class HostClient:
    """Same send() as Host, over hostd's socket. heap=<did> addresses a private heap; stateless=True the REPL process."""

    def __init__(self, path, heap=None, stateless=False):
        self.path, self.heap, self.stateless = str(path), heap, stateless

    def send(self, request):
        envelope = dict(request)
        if self.heap:
            envelope['heap'] = self.heap
        if self.stateless:
            envelope['stateless'] = True
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(HOST_TIMEOUT + 30)
                s.connect(self.path)
                s.sendall((json.dumps(envelope) + '\n').encode())
                line = s.makefile('rb').readline()
            return json.loads(line)
        except (OSError, ValueError):
            return {'status': 'error', 'message': 'hostd unavailable'}

    def close(self):
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


def connect(args, clock=None):
    """The host a program talks to: hostd's socket, or an in-process host with --standalone."""
    if getattr(args, 'standalone', False):
        return Host(args.journal, clock=clock)
    return HostClient(args.host_socket or Path(args.state) / 'host.sock')


def add_host_args(ap):
    ap.add_argument('--host-socket', metavar='PATH', help='hostd socket (default <state>/host.sock)')
    ap.add_argument('--standalone', action='store_true', help='spawn an in-process host over --journal (single-program use only)')
    ap.add_argument('--journal', help='world journal (--standalone only)')
