"""The host's client: one JSON line per op over a socket of `delvetalk-obend serve` (HOST-HANDOFF 5.125), which owns the
directory, its lock and every journal. `<dir>/host.sock` is public; the root socket (deploy's /run/delvetalk-root/root.sock,
mounted into the hand's and the ops containers only) takes `world-root`, the root ops and every op naming the opener.
Every op carries `world: <name>` (default `town`)."""
import json
import os
import socket
import threading
import time
from pathlib import Path

HOST_TIMEOUT, CONNECT_WAIT = 150, 2  # seconds an op may take; seconds to wait for a socket not (yet) there
CLOCK, ON_ROOT = 'transport', 'the opener speaks on the root socket'  # the clock principal serve opens each world with; its refusal
# Ops answered the same when sent twice (reads; a turn, by its identity): only these are re-sent after a broken connection.
IDEMPOTENT = {'world-' + op for op in 'status view card objects offers history receipt resolve inspect entries entry object publications '
              'grants source sources state-cid addressee turn'.split()} | {'hostd-info', 'serve-status'}


class HostClient:
    """send(request) -> the host's reply. heap=<did> addresses a private heap; stateless=True the journal-less session.
    One persistent connection per thread, re-made on EOF or when the socket file is a new one (serve restarted)."""

    def __init__(self, path, world='town', heap=None, stateless=False, timeout=HOST_TIMEOUT):
        self.path, self.world, self.heap, self.stateless, self.timeout = str(path), world, heap, stateless, timeout
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
            started = time.monotonic()
            while True:  # nothing was sent, so any op may wait and connect again: a full backlog (EAGAIN), or a serve starting
                try:
                    s.connect(self.path)
                    break
                except (BlockingIOError, FileNotFoundError, ConnectionRefusedError) as err:
                    if time.monotonic() > (deadline if isinstance(err, BlockingIOError) else started + CONNECT_WAIT):
                        raise
                    time.sleep(0.01)
            self.local.conn = (s, s.makefile('rb'), os.stat(self.path).st_ino)
        except OSError:
            s.close()
            raise
        return self.local.conn[0], self.local.conn[1], True

    def send(self, request):
        envelope = {**({'world': self.world} if self.world else {}), **request, **({'heap': self.heap} if self.heap else {}),
                    **({'stateless': True} if self.stateless else {})}  # a request naming its own world keeps it
        data, began = (json.dumps(envelope) + '\n').encode(), time.monotonic()
        for _ in (0, 1):
            fresh = True
            try:
                s, reader, fresh = self._connection()
                s.sendall(data)
                line = reader.readline()
                if not line:
                    raise OSError('the host closed the connection')
                return json.loads(line)
            except TimeoutError:  # the host took the request and did not answer; a turn it ran may still commit: never re-sent
                self.close()
                return {'status': 'error', 'class': 'hostTimeout', 'message': f'the host did not answer within {self.timeout} seconds'}
            except (OSError, ValueError):
                self.close()
                if fresh or request.get('op') not in IDEMPOTENT:  # a stale reused connection: once more on a new one, if the op is safe to repeat
                    break
        return {'status': 'error', 'class': 'hostUnavailable', 'message': f'the host is unavailable at {self.path} after {time.monotonic() - began:.1f} s'}

    def at(self, heap):
        return HostClient(self.path, self.world, heap=heap, timeout=self.timeout)

    def close(self):
        held, self.local.conn = getattr(self.local, 'conn', None), None
        for f in (held or ())[1::-1]:
            try:
                f.close()
            except OSError:
                pass


def add_host_args(ap, root=False):
    """--host-socket (default <state>/host.sock), or for the opener's programs --root-socket (DELVETALK_ROOT_SOCKET, else
    serve's default <state>/root/root.sock); --world."""
    ap.add_argument('--root-socket' if root else '--host-socket', metavar='PATH', default=os.environ.get('DELVETALK_ROOT_SOCKET') if root else None)
    ap.add_argument('--world', default=os.environ.get('DELVETALK_WORLD', 'town'), help='the world the ops address (default town, or DELVETALK_WORLD)')


def connect(args, **more):
    if hasattr(args, 'root_socket'):
        return HostClient(args.root_socket or Path(args.state) / 'root' / 'root.sock', args.world, **more)
    return HostClient(args.host_socket or Path(args.state) / 'host.sock', args.world, **more)
