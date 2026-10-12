"""Shared host helper for every suite that drives delvetalk-obend.

* The binary is copied once per test run into a temp dir, so a rebuild elsewhere never races a
  running suite. DELVETALK_OBEND names the source; tests/run.py copies once and shares the copy
  with its workers through DELVETALK_OBEND_COPY. The copy goes at exit; one whose owner died
  without exiting (its `owner.pid` names a process that is gone) goes when the next copy is made.
* served() takes the test's cleanup registrar and registers the stop before serve starts. SIGTERM
  and SIGHUP stop every serve and remove the copy before the process dies (deploy/serve.py has
  the rest: process group, served.pid, Linux parent-death signal, atexit).
* HostCase starts ONE host process per test class and opens a fresh temp journal per test. A test
  that needs a fresh process (restart, tamper) asks for one: spawn(), reopen(), release().
* check() serves stateless ops (compile, run) from one process per run and memoizes compiles.
"""
import atexit
import glob
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FOUNDATION = "/Users/ember/dev/delvetalk2/.lake/build/bin/delvetalk-obend"
_copy = None


def source_binary():
    local = os.path.join(ROOT, ".lake", "build", "bin", "delvetalk-obend")
    return os.environ.get("DELVETALK_OBEND") or (local if os.path.exists(local) else FOUNDATION)


COPY_PREFIX = "dt-obend-"
_owned = []  # the copy directory this process made, removed at exit or on SIGTERM/SIGHUP


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def sweep_copies():
    """Remove each binary copy whose owner.pid names a process that is gone (an owner killed before its exit ran).
    A copy with no owner.pid was made before owners were recorded; it is not this function's to judge."""
    for directory in glob.glob(os.path.join(tempfile.gettempdir(), COPY_PREFIX + "*")):
        try:
            with open(os.path.join(directory, "owner.pid")) as f:
                owner = int(f.read())
        except (OSError, ValueError):
            continue
        if owner != os.getpid() and not _alive(owner):
            shutil.rmtree(directory, True)


def _remove_copies():
    while _owned:
        shutil.rmtree(_owned.pop(), True)


def binary():
    global _copy
    if _copy is None:
        shared = os.environ.get("DELVETALK_OBEND_COPY")
        if shared and os.path.exists(shared):
            _copy = shared
        else:
            sweep_copies()
            directory = tempfile.mkdtemp(prefix=COPY_PREFIX)
            _owned.append(directory)
            with open(os.path.join(directory, "owner.pid"), "w") as f:
                f.write("%d\n" % os.getpid())
            _copy = os.path.join(directory, "delvetalk-obend")
            shutil.copy2(source_binary(), _copy)
    return _copy


atexit.register(_remove_copies)


def _on_signal(signum, frame):
    """SIGTERM or SIGHUP: stop this process's serves and remove its copy, then die of the signal as before."""
    from deploy.serve import stop_all
    stop_all()
    _remove_copies()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


if threading.current_thread() is threading.main_thread():
    for _s in (signal.SIGTERM, signal.SIGHUP):
        if signal.getsignal(_s) == signal.SIG_DFL:
            signal.signal(_s, _on_signal)


class Host:
    def __init__(self):
        self.proc = subprocess.Popen([binary()], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1)

    def raw(self, request=None, **fields):
        """One request as given, one reply as the host printed it."""
        request = dict(request or {}, **fields)
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, "host closed its output"
        return json.loads(line)

    def send(self, request=None, **fields):
        """A request as a dict or as keywords. Test journals only flush (`world-open {sync: "none"}`);
        deploy and `serve` keep the default `fsync`; `raw` sends it as given."""
        request = dict(request or {}, **fields)
        if request.get("op") == "world-open" and "sync" not in request:
            request["sync"] = "none"
        reply = self.raw(request)
        hashed = [t for t in card_texts(reply) if "bafy" in t]
        assert not hashed, "a card or offer cites a hash: %r" % hashed[:1]
        return reply

    def alive(self):
        return self.proc.poll() is None

    def close(self):
        if self.proc.stdin.closed:
            return
        self.proc.stdin.close()
        self.proc.wait(timeout=60)
        self.proc.stdout.close()


class Hosts(list):
    """Private processes of one test; remove() of a process already gone is a no-op."""

    def remove(self, host):
        if host in self:
            super().remove(host)


class HostCase(unittest.TestCase):
    independent = True  # a fresh journal per test: tests share only the process (tests/run.py may split the class)
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shared = Host()
        cls.addClassCleanup(lambda: cls.shared.close())

    def setUp(self):
        if not self.shared.alive():
            type(self).shared = Host()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "world.journal")
        self.hosts = Hosts()
        self.addCleanup(self._close_private)
        self.host = self.shared
        self.assertEqual(self.host.send(op="world-open", path=self.path)["status"], "opened")

    def _close_private(self):
        for h in self.hosts:
            h.close()

    def spawn(self):
        h = Host()
        self.hosts.append(h)
        return h

    def release(self):
        """Let go of the journal so a test may edit the file: close a private process, or point the
        shared one at a scratch journal. Afterwards self.host must not be used until reopen()."""
        if self.host in self.hosts:
            self.host.close()
            self.hosts.remove(self.host)
        elif self.host.alive():
            self.host.send(op="world-open", path=os.path.join(self.dir.name, "released.journal"))

    def reopen(self):
        """Process death and replay: a fresh process opens the same journal."""
        self.release()
        self.host = self.spawn()
        self.assertEqual(self.host.send(op="world-open", path=self.path)["status"], "opened")


_checker = None
_memo = {}


def check(request):
    """A stateless op on the run's shared process. Compiles are memoized (artifacts live in that process)."""
    global _checker
    if _checker is None or not _checker.alive():
        _checker = Host()
        _memo.clear()
    key = json.dumps(request, sort_keys=True) if request.get("op") == "compile" else None
    if key in _memo:
        return _memo[key]
    reply = _checker.send(**request)
    if key:
        _memo[key] = reply
    return reply


_bounds = None


def bounds():
    """The host's own answer to `bounds`: `kernel` and `host` bounds by name, `refusalClasses`, `transientClasses`."""
    global _bounds
    if _bounds is None:
        _bounds = check({"op": "bounds"})
    return _bounds


class Stateless:
    """send(**request) on the run's shared stateless process."""

    @staticmethod
    def send(**request):
        return check(request)


atexit.register(lambda: _checker and _checker.alive() and _checker.close())


POLL = 0.05  # socketserver's default 0.5 s poll made every daemon's shutdown cost half a second


def serve(server):
    """Serve a socketserver (the HTTP front, a fake) from a daemon thread; stop with server.shutdown()."""
    import threading
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": POLL}, daemon=True).start()
    return server


def served(state, *, cleanup, **settings):
    """`delvetalk-obend serve` over `state` (its journals unsynced), a child of this test process (HOST-HANDOFF 5.125).
    `cleanup` is the test's addCleanup or addClassCleanup: it receives the stop before serve starts, so a failure
    anywhere after, the start's own included, still stops it."""
    from deploy.serve import Served
    if os.environ.get("DELVETALK_SPAWN_LOG"):
        with open(os.environ["DELVETALK_SPAWN_LOG"], "a") as f:
            f.write("serve\n")
    return Served(state, binary(), cleanup=cleanup, **settings)


class ServeCase(unittest.TestCase):
    """One `serve` per test class, its town opened by OPENER with the world library sealed; tests share its
    world, so each names its own objects. `host` is the public socket, `root` the opener's."""
    OPENER = "did:plc:" + "a" * 24

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from transport.config import LIBRARY
        from transport.host import HostClient
        cls.state_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.state_dir.cleanup)
        cls.server = served(cls.state_dir.name, cleanup=cls.addClassCleanup, opener=cls.OPENER, library=LIBRARY)
        cls.socket, cls.root_socket = cls.server.sock, cls.server.root
        cls.host, cls.root = HostClient(cls.socket), HostClient(cls.root_socket)


def whole(host, reply):
    """A turn another op's settling ran, as its own principal reads it (`world-receipt`): the
    settling reply carries it for anyone else only as its projection (codex host 1)."""
    identity = reply["receipt"]["identity"]
    r = host.send(op="world-receipt", principal=identity["principal"], identity=identity["intent"])
    assert r.get("status") == "receipt", r
    return r["receipt"]


def as_owner(host, reply, principal=None):
    """A settled turn's reply as its own principal would have had it: the whole receipt (read with
    `world-entry` as that principal) and its `result` and `ticksUsed` lifted, as a turn's reply lifts
    them. `principal` names the owner when the projection does not (a refusal's)."""
    receipt = reply["receipt"]
    principal = principal or receipt["identity"]["principal"]
    r = host.send(op="world-entry", principal=principal, hash=receipt["hash"])
    assert r.get("status") == "receipt", r
    out = dict(reply, receipt=r["receipt"])
    for k in ("result", "ticksUsed"):
        if k in r["receipt"]:
            out[k] = r["receipt"][k]
    return out


def addressed(host, uri):
    """What a reply to the post at `uri` reaches (`world-reach`): its object and what the post was made for (slot, page and
    section, why it left the town), or None for a post the world never recorded."""
    request = dict(op="world-reach", uri=uri + "#reply", text="", kind="post", author="transport", replyTo=uri)
    try:
        got = host.send(request)
    except TypeError:  # a driver that takes fields alone (tests.town.Town)
        got = host.send(**request)
    return {k: v for k, v in got.items() if k not in ("status", "how", "replyTo")} if got["status"] == "reached" else None


def posted(host, intent=None, source="test", **request):
    """`world-posted` as the transport makes it (HOST-HANDOFF 5.107): the post's reservation first, under
    its intent (by default its uri; a source other than `delve` counts against no quota)."""
    intent = intent or request["uri"]
    principal = request.get("principal", "transport")
    host.send(op="world-post-reserve", principal=principal, intent=intent, source=source)
    return host.send(op="world-posted", intent=intent, **request)


def card_texts(reply):
    """Every card and offer text in a host reply: what a reader sees, which never cites a hash."""
    out = []
    def walk(v, offered):
        if isinstance(v, dict):
            for k, x in v.items():
                if k == "text" and offered and isinstance(x, str):
                    out.append(x)
                else:
                    walk(x, offered or k in ("offers", "document"))
        elif isinstance(v, list):
            for x in v:
                walk(x, offered)
    walk(reply, False)
    if reply.get("status") == "card" and isinstance(reply.get("text"), str):
        out.append(reply["text"])
    return out
