"""Shared host helper for every suite that drives delvetalk-obend.

* The binary is copied once per test run into a temp dir, so a rebuild elsewhere never races a
  running suite. DELVETALK_OBEND names the source; tests/run.py copies once and shares the copy
  with its workers through DELVETALK_OBEND_COPY.
* HostCase starts ONE host process per test class and opens a fresh temp journal per test. A test
  that needs a fresh process (restart, tamper) asks for one: spawn(), reopen(), release().
* check() serves stateless ops (compile, run) from one process per run and memoizes compiles.
"""
import atexit
import json
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FOUNDATION = "/Users/ember/dev/delvetalk2/.lake/build/bin/delvetalk-obend"
_copy = None


def source_binary():
    local = os.path.join(ROOT, ".lake", "build", "bin", "delvetalk-obend")
    return os.environ.get("DELVETALK_OBEND") or (local if os.path.exists(local) else FOUNDATION)


def binary():
    global _copy
    if _copy is None:
        shared = os.environ.get("DELVETALK_OBEND_COPY")
        if shared and os.path.exists(shared):
            _copy = shared
        else:
            directory = tempfile.mkdtemp(prefix="dt-obend-")
            atexit.register(shutil.rmtree, directory, True)
            _copy = os.path.join(directory, "delvetalk-obend")
            shutil.copy2(source_binary(), _copy)
    return _copy


class Host:
    def __init__(self):
        self.proc = subprocess.Popen([binary()], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1)

    def send(self, **request):
        # Test journals only flush (`world-open {sync: "none"}`); deploy and hostd keep the default `fsync`.
        if request.get("op") == "world-open" and "sync" not in request:
            request["sync"] = "none"
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, "host closed its output"
        reply = json.loads(line)
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


class Stateless:
    """send(**request) on the run's shared stateless process."""

    @staticmethod
    def send(**request):
        return check(request)


atexit.register(lambda: _checker and _checker.alive() and _checker.close())


def start_hostd(state, binary_path=None, opener=None, library=None):
    """A hostd serving <state>/host.sock from a thread, over <state>/world.journal. Stop with stop_hostd."""
    import threading
    from transport.hostd import Hostd
    d = Hostd(state, os.path.join(state, "world.journal"), binary_path or binary(), opener=opener, library=library)
    threading.Thread(target=d.serve_forever, daemon=True).start()
    return d


def stop_hostd(d):
    d.shutdown()
    d.close()


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
