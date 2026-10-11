"""The host's client: one JSON line per op over a socket of `delvetalk-obend serve` (HOST-HANDOFF 5.125), which owns the
directory, its lock and every journal. `<dir>/host.sock` is public; the root socket (deploy's /run/delvetalk-root/root.sock,
mounted into the hand's and the ops containers only) takes `world-root`, the root ops and every op naming the opener.
Every op carries `world: <name>` (default `town`)."""
import json
import os
import socket
import threading
import time

HOST_TIMEOUT, CONNECT_WAIT = 150, 2  # seconds an op may take; seconds to wait for a socket not (yet) there
CLOCK, ON_ROOT = 'transport', 'the opener speaks on the root socket'  # the clock principal serve opens each world with; its refusal
# Ops answered the same when sent twice (reads; a turn, by its identity): only these are re-sent after a broken connection.
IDEMPOTENT = {'world-' + op for op in 'status view card objects offers history receipt resolve inspect entries entry object publications '
              'grants source sources state-cid addressee turn render strokes'.split()} | {'serve-status'}
PAINT_STEP = 0.25  # seconds between two looks at a pending paint


class HostClient:
    """send(request) -> the host's reply. `world` addresses a world served here (`town`, or `scratch/<name>` for the request's principal's scratch world);
    stateless=True the journal-less session.
    One persistent connection per thread, re-made on EOF or when the socket file is a new one (serve restarted)."""

    def __init__(self, path, world='town', stateless=False, timeout=HOST_TIMEOUT):
        self.path, self.world, self.stateless, self.timeout = str(path), world, stateless, timeout
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
        envelope = {**({'world': self.world} if self.world else {}), **request,
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

    def at(self, world):
        """A client for another world served here, e.g. `at('scratch/try')`."""
        return HostClient(self.path, world, timeout=self.timeout)

    def close(self):
        held, self.local.conn = getattr(self.local, 'conn', None), None
        for f in (held or ())[1::-1]:
            try:
                f.close()
            except OSError:
                pass


def painted(host, principal, obj, sleep=time.sleep):
    """The painted card of `obj` as `principal` reads it (docs/OVERHAUL.md section 4), or None, when the exact card stands
    alone: the host's `pending` is looked at again every PAINT_STEP seconds for the `patience` it names, no longer."""
    r = host.send({'op': 'world-render', 'principal': principal, 'object': obj})
    for _ in range(int((r.get('patience') or 0) / PAINT_STEP)):
        if r.get('status') != 'pending':
            break
        sleep(PAINT_STEP)
        r = host.send({'op': 'world-render', 'principal': principal, 'object': obj})
    return r.get('text') if r.get('status') == 'painted' else None
