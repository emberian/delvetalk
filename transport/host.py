"""The host's client and its wire: one JSON line per op over a socket of `delvetalk-obend serve` (HOST-HANDOFF 5.125),
which owns the directory, its lock and every journal, or over the stdin of a host process of a script's own. `<dir>/host.sock`
is public; the root socket (deploy's /run/delvetalk-root/root.sock, mounted into the hand's and the ops containers only)
takes `world-root`, the root ops and every op naming the opener. Every op carries `world: <name>` (default `town`)."""
import json
import os
import socket
import subprocess
import threading
import time

HOST_TIMEOUT, CONNECT_WAIT = 150, 2  # seconds an op may take; seconds to wait for a socket not (yet) there
CLOCK, ON_ROOT = 'transport', 'the opener speaks on the root socket'  # the clock principal serve opens each world with; its refusal
# Ops answered the same when sent twice (reads; a turn, by its identity): only these are re-sent after a broken connection.
IDEMPOTENT = {'world-' + op for op in 'status view card objects offers history receipt resolve inspect entries entry object publications '
              'grants source sources state-cid addressee turn render strokes'.split()} | {'serve-status'}
PAINT_STEP = 0.25  # seconds between two looks at a pending paint
PUBLIC = 'anonymous'  # the reader an unauthenticated request is, and a public channel's: what everyone may read


class HostClient:
    """send(request) -> the host's reply. `world` addresses a world served here (`town`, or `scratch/<name>` for the request's principal's scratch world).
    One persistent connection per thread, re-made on EOF or when the socket file is a new one (serve restarted)."""

    def __init__(self, path, world='town', timeout=HOST_TIMEOUT):
        self.path, self.world, self.timeout = str(path), world, timeout
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
        envelope = {**({'world': self.world} if self.world else {}), **request}  # a request naming its own world keeps it
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


class HostProcess:
    """A host process of a script's own on stdin and stdout, one JSON line each way (carry's check, genesis's refresh of a
    carried journal, the bench's raw path, a stub in a test); with `journal`, that journal opened unsynced. Never a
    served world's writer."""

    def __init__(self, binary, journal=None, **opening):
        self.proc = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        if journal:
            opened = self.send({'op': 'world-open', 'path': str(journal), 'sync': 'none', **opening})
            assert opened.get('status') == 'opened', opened

    def send(self, request=None, **fields):
        self.proc.stdin.write(json.dumps({**(request or {}), **fields}) + '\n')
        return json.loads(self.proc.stdout.readline())

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=60)
        self.proc.stdout.close()


def paged(host, request, field):
    """Every item of a paged read (`world-offers`, `world-history`): `request` again `after` the last item's height while
    the host says there is `more`."""
    while True:
        got = host.send(request)
        items = got.get(field) or []
        yield from items
        if not got.get('more') or not items:
            return
        request = {**request, 'after': items[-1]['height']}


def typed(value):
    """Plain JSON as the host's typed data: text is a label, an integer a natural, an object a record."""
    if isinstance(value, dict):
        return value if 'tag' in value else {'tag': 'record', 'fields': [{'name': k, 'value': typed(v)} for k, v in value.items()]}
    if isinstance(value, list):
        return {'tag': 'list', 'items': [typed(v) for v in value]}
    if isinstance(value, bool):
        return {'tag': 'boolean', 'value': value}
    return {'tag': 'natural', 'value': str(value)} if isinstance(value, int) else {'tag': 'label', 'value': str(value)}


def plain(data):
    """Typed data as plain JSON, for reading only (a form's fields, a view's doors); never sent back to the host."""
    tag = data.get('tag') if isinstance(data, dict) else None
    if tag == 'record':
        return {f['name']: plain(f['value']) for f in data['fields']}
    if tag == 'list':
        return [plain(i) for i in data['items']]
    if tag == 'variant':
        inner = plain(data['payload'])
        return {'tag': data['label'], **inner} if isinstance(inner, dict) else {'tag': data['label'], 'value': inner}
    return int(data['value']) if tag == 'natural' else data.get('value') if tag else data


def handles(host, reader, principals, known):
    """{principal: handle} in `known`, filled for `principals` as `reader` sees them: the `handle` of each one's avatar
    (`world-arrive` seeds it from the registry). A handle once found is kept; one with no avatar is asked again next time."""
    for p in set(principals) - set(known):
        view = host.send({'op': 'world-view', 'principal': reader, 'object': p})
        handle = (plain(view.get('state') or {}) or {}).get('handle') if view.get('status') == 'viewed' else None
        if isinstance(handle, str) and handle:
            known[p] = handle
    return known
