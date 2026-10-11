"""`delvetalk-obend serve` as a child process of a script or a test (HOST-HANDOFF 5.125): started over a state
directory, waited for until both sockets listen, stopped by its own handle. Production runs serve as compose's
`delvetalk-host` service instead; this is for capture-examples, the bench, the rehearsal and tests/host.py.

A serve outlives nothing that started it. It runs in its own process group (a terminal's ^C reaches the script, which
stops it), its PID is in `<state>/served.pid` from the moment it starts, and it is stopped by that PID, then its group:
by `stop()`, which a caller registers before the start (`cleanup`); by `stop_all()` at interpreter exit; and on Linux by
the kernel, which sends it SIGTERM when the thread that started it dies, however abruptly (PR_SET_PDEATHSIG).
"""
import atexit
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from transport.config import Config
from transport.state import State

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


_live = set()  # every Served started and not yet stopped
PIDFILE = 'served.pid'  # this module's record of the serve it started; serve keeps its own serve.pid


def stop_all():
    """Stop every serve this process started and has not stopped (atexit; a test harness's signal handler)."""
    for served in list(_live):
        served.stop()


atexit.register(stop_all)


def _orphan_guard():
    """A Popen preexec_fn: on Linux, SIGTERM to the child when the thread that forked it dies, and exit now if that
    already happened between the fork and this call. Elsewhere None: stop() and stop_all() are the only guards."""
    if not sys.platform.startswith('linux'):
        return None
    import ctypes
    prctl, parent = ctypes.CDLL(None, use_errno=True).prctl, os.getpid()  # resolved before the fork, never in the child
    PR_SET_PDEATHSIG = 1

    def guard():
        if prctl(PR_SET_PDEATHSIG, signal.SIGTERM) != 0 or os.getppid() != parent:
            os._exit(70)
    return guard


def _exited(pid):
    """Whether child `pid` has exited, without reaping it: until it is reaped its PID names its group and nothing else."""
    try:
        return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
    except ChildProcessError:
        return True


class Served:
    """serve over `state` with the config's settings, except that it seals no library and names no opener unless given
    (`opener`, `library`, any other field), and appends unsynced unless `sync` says otherwise. `cleanup`, when given,
    receives `stop` before the process starts (a test's addCleanup or addClassCleanup)."""

    def __init__(self, state, binary=None, sync='none', opener='', library='', cleanup=None, **settings):
        self.proc = self.log = None
        settings = dict(settings, sync=sync, opener=opener, library=str(library or ''), **({'obend': str(binary)} if binary else {}))
        self.place = State(Path(state).resolve(), config=Config.load(Path(state), **settings))
        self.state, binary = self.place.root, self.place.config.obend
        self.sock, self.root = str(self.place.host_socket), str(self.place.root_socket)
        for p in (self.sock, self.root):
            if os.path.exists(p):
                os.unlink(p)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.path.sep in binary:
            pin_cache(self.state, binary)
        self.pidfile = self.state / PIDFILE
        if cleanup:
            cleanup(self.stop)
        self.log = open(self.state / 'serve.log', 'w')  # a file, not a pipe: a chatty serve (DELVETALK_TIMING) never blocks on it
        _live.add(self)
        self.proc = subprocess.Popen(self.place.serve_argv(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=self.log,
                                     start_new_session=True, preexec_fn=_orphan_guard())
        self.pidfile.write_text(f'{self.proc.pid}\n')
        deadline = time.monotonic() + 120
        while not (os.path.exists(self.sock) and os.path.exists(self.root)):
            if self.proc.poll() is not None:
                self.stop()
                raise RuntimeError(f'serve exited {self.proc.returncode}: {(self.state / "serve.log").read_text()}')
            if time.monotonic() > deadline:
                self.stop()
                raise RuntimeError('serve did not listen within 120 s')
            time.sleep(0.02)
        ready, client = time.monotonic() + READY, self.place.host(world=None)
        try:  # a socket file is not yet a server answering: the first op waits for `serve-status` (under load it lags the file)
            while (got := client.send({'op': 'serve-status'})).get('status') != 'serve':
                if self.proc.poll() is not None or time.monotonic() > ready:
                    self.stop()
                    raise RuntimeError(f'serve did not answer serve-status within {READY} s: {got.get("message")}')
                time.sleep(0.05)
        finally:
            client.close()

    def stop(self):
        """SIGTERM to the PID in served.pid (serve finishes the op in hand and removes its sockets and serve.pid), SIGKILL
        after 60 s; then SIGKILL to its group while its unreaped PID still names the group; then served.pid goes.
        Idempotent: a cleanup, stop_all and the caller may each call it."""
        _live.discard(self)
        if self.proc is not None and self.proc.returncode is None:
            pid = int(self.pidfile.read_text()) if self.pidfile.exists() else self.proc.pid
            assert pid == self.proc.pid, f'{self.pidfile} names {pid}, not the serve this handle started ({self.proc.pid})'
            if not _exited(pid):
                os.kill(pid, signal.SIGTERM)
                deadline = time.monotonic() + 60
                while not _exited(pid):
                    if time.monotonic() > deadline:
                        os.kill(pid, signal.SIGKILL)
                        deadline = float('inf')
                    time.sleep(0.01)
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):  # an empty group; Darwin answers EPERM for a zombie's
                pass
            self.proc.wait()
        if self.proc is not None:
            self.pidfile.unlink(missing_ok=True)
        if self.log is not None:
            self.log.close()


class Pipe:
    """A host process of a script's own on stdin and stdout, one JSON line each way, over `journal` when given (a
    probe on a copy, the bench's raw path); never a world's writer."""

    def __init__(self, binary=None, journal=None, **opening):
        self.proc = subprocess.Popen([str(binary or Config.load().obend)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
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
