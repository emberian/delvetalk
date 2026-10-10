"""`delvetalk-obend serve` as a child process of a script or a test (HOST-HANDOFF 5.125): started over a state
directory, waited for until both sockets listen, stopped by its own handle. Production runs serve as compose's
`delvetalk-host` service instead; this is for capture-examples, the bench, the rehearsal and tests/host.py.
"""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

BINARY = os.environ.get('DELVETALK_OBEND', 'delvetalk-obend')
LIBRARY = Path(__file__).resolve().parent.parent / 'world' / 'lib'
READY = 30  # seconds a started serve has to answer its first op
_pins = {}


def pin_cache(state, binary):
    """<state>/binary-pin as serve keeps it (path, size, mtimeNs, sha256), hashed here once per binary: serve's own
    hash of a 130 MB binary takes 3.3 s on hbox, against 0.2 s for hashlib, and every fresh directory pays it."""
    real = os.path.realpath(binary)
    st = os.stat(real)
    key = (real, st.st_size, st.st_mtime_ns)
    if key not in _pins:
        with open(real, 'rb') as f:
            _pins[key] = hashlib.sha256(f.read()).hexdigest()
    (Path(state) / 'binary-pin').write_text(json.dumps({'path': real, 'size': st.st_size, 'mtimeNs': st.st_mtime_ns, 'sha256': _pins[key]}))


class Served:
    def __init__(self, state, binary=BINARY, opener=None, library=None, sync='none', extra=()):
        self.state = Path(state).resolve()
        self.sock, self.root = str(self.state / 'host.sock'), str(self.state / 'root' / 'root.sock')
        for p in (self.sock, self.root):
            if os.path.exists(p):
                os.unlink(p)
        argv = [str(binary), 'serve', '--state', str(self.state), '--sync', sync] + (['--opener', opener] if opener else []) + \
            (['--library', str(library)] if library else []) + list(extra)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.path.sep in str(binary):
            pin_cache(self.state, binary)
        self.log = open(self.state / 'serve.log', 'w')  # a file, not a pipe: a chatty serve (DELVETALK_TIMING) never blocks on it
        self.proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=self.log)
        deadline = time.monotonic() + 120
        while not (os.path.exists(self.sock) and os.path.exists(self.root)):
            if self.proc.poll() is not None:
                self.log.close()
                raise RuntimeError(f'serve exited {self.proc.returncode}: {(self.state / "serve.log").read_text()}')
            if time.monotonic() > deadline:
                self.stop()
                raise RuntimeError('serve did not listen within 120 s')
            time.sleep(0.02)
        from transport.host import HostClient
        ready, client = time.monotonic() + READY, HostClient(self.sock, None)
        try:  # a socket file is not yet a server answering: the first op waits for `hostd-info` (under load it lags the file)
            while (got := client.send({'op': 'hostd-info'})).get('status') != 'hostd':
                if self.proc.poll() is not None or time.monotonic() > ready:
                    self.stop()
                    raise RuntimeError(f'serve did not answer hostd-info within {READY} s: {got.get("message")}')
                time.sleep(0.05)
        finally:
            client.close()

    def stop(self):
        """SIGTERM to this child alone: serve finishes the op in hand and removes its sockets and pid file."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.close()


class Pipe:
    """A host process of a script's own on stdin and stdout, one JSON line each way, over `journal` when given (a
    probe on a copy, the bench's raw path); never a world's writer."""

    def __init__(self, binary=BINARY, journal=None, **opening):
        self.proc = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        if journal:
            opened = self.send({'op': 'world-open', 'path': str(journal), 'sync': 'none', **opening})
            assert opened.get('status') == 'opened', opened

    def send(self, request):
        self.proc.stdin.write(json.dumps(request) + '\n')
        return json.loads(self.proc.stdout.readline())

    def close(self):
        self.proc.stdin.close()
        self.proc.wait()
        self.proc.stdout.close()
