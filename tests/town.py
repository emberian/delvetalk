"""The town as deploy builds it, for the properties and the scenarios: `delvetalk-obend serve` over
<directory>/state (the transport's clock, the library sealed as deploy seals it, the town's journal
state/town.journal) after `deploy/genesis.py` has run. `send(**request)` goes over the root socket, which
takes every principal's ops, the opener's included; `reopen()` restarts serve, so the next request replays
the journal.

Genesis (and furnish) runs once per test run, not once per town: the first town of each shape builds it in a
template directory under $DELVETALK_TOWN_TEMPLATES (tests/run.py makes one per run; else one per process), and every
town after starts serve over a copy of that state (the journal, its block store and the snapshot at its head), so it
opens the same world from that snapshot. `made` is the template's.
tests/test_town_template.py holds the copy to a fresh genesis, object by object."""
import fcntl
import json
import os
import shutil
import tempfile

from tests.host import served

MOSS_GATE = """---
id: gate
title: The Moss Gate
---
=== gate
A moss gate, ajar.
* [Open]
  ~ gate = open
  -> yard
* [Wait] -> gate
=== yard
A quiet yard.
* [Back] -> gate
* [Knock]
  ~ knock = twice
  -> yard
"""


def furnish(host, opener):
    """The town after its first day, as the scenarios meet it: genesis makes the frame and the town's coinages
    (deploy/genesis.py), and the places the scenarios walk are made after it by ordinary spells and one create, as
    any hand could: THE NIGHT GARDEN, the Moss Gate (`rooms`), the weather over the garden on the tide, the
    anthology the opener keeps, and the commonplace's doors to the three."""
    from deploy import genesis
    from deploy.seed import create
    out = []
    for kind, fields in (('kind/garden', [('id', 'garden'), ('name', 'THE NIGHT GARDEN')]),
                         ('kind/room', [('id', 'rooms'), ('name', 'The Moss Gate'), ('spween', MOSS_GATE)]),
                         ('kind/weather', [('id', 'garden/weather'), ('over', 'garden'), ('tide', 'tide')])):
        out.append(genesis.said(host, opener, kind, 'place', fields, 'furnish-' + dict(fields)['id'], dict(fields)['id']))
    out.append(genesis.said(host, opener, 'garden', 'door', [('label', 'weather'), ('to', 'garden/weather')], 'furnish-garden-door'))
    anthology = create(host, opener, 'anthology', 'Record', 'furnish-anthology',
                       genesis.rec(owner=genesis.lab(opener), keeper=genesis.lab(opener), keeperHandle=genesis.lab(genesis.TOWN),
                                   head=genesis.lab('THE ANTHOLOGY')), genesis.RECORD_LAW)
    out.append({'object': 'anthology', 'module': 'Record', 'status': anthology.get('status'), 'creator': opener, 'reply': anthology})
    for label, to in (('GARDEN', 'garden'), ('ROOMS', 'rooms'), ('ANTHOLOGY', 'anthology')):
        out.append(genesis.said(host, opener, 'commonplace', 'door', [('label', label), ('to', to)], 'furnish-door-' + to))
    assert all(m['status'] in ('created', 'admitted') for m in out), out
    return out


_templates = None


def TEMPLATES():
    """The directory holding this run's genesis templates, shared by every class process of a run."""
    global _templates
    if _templates is None:
        _templates = os.environ.get("DELVETALK_TOWN_TEMPLATES") or tempfile.mkdtemp(prefix="dt-towns-")
        if not os.environ.get("DELVETALK_TOWN_TEMPLATES"):
            import atexit
            atexit.register(shutil.rmtree, _templates, True)
    return _templates


def shape(furnished):
    """The template's name: furnished or not, and a digest of the binary (size, mtime) and of what genesis and furnish
    read as they stand in this process (deploy.genesis's and this module's constants, which a test may patch to make
    an older genesis)."""
    import hashlib
    import sys
    from deploy import genesis
    def stable(v):
        if isinstance(v, dict):
            return repr(sorted((repr(k), stable(x)) for k, x in v.items()))
        if callable(v):
            return repr((v.__code__.co_code, [c for c in v.__code__.co_consts if not hasattr(c, 'co_code')]))
        return repr(v)
    from tests.host import binary
    st = os.stat(os.path.realpath(binary()))
    held = [(st.st_size, st.st_mtime_ns)] + [(m.__name__, k, stable(v)) for m in (genesis, sys.modules[__name__])
                                            for k, v in sorted(vars(m).items()) if k.isupper() and not callable(v)]
    return ("furnished-" if furnished else "genesis-") + hashlib.sha256(repr(held).encode()).hexdigest()[:16]


def _transient(directory, names):
    """What a stopped serve leaves that is its process's, not the world's: sockets, PID files, its log, the lock."""
    return [n for n in names if n.endswith((".sock", ".pid", ".log", ".lock"))]


def template(furnished):
    """`made` and the name of the run's template town of this shape, built by the first process to ask (the others wait on its
    lock): a fresh town, genesis run, stopped; its state is what every later town copies."""
    root, name = TEMPLATES(), shape(furnished)
    done = os.path.join(root, name, "made.json")
    with open(os.path.join(root, name + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not os.path.exists(done):
            building = tempfile.mkdtemp(dir=root, prefix=name + ".")
            stops = []
            town = Town(building, cleanup=stops.append, furnished=furnished, fresh=True)
            made = town.made
            # A snapshot at the head, so every copy opens from it (0.3 s) rather than replaying genesis (1.2 s).
            assert town.send(op="world-snapshot")["status"] == "snapshot"
            for stop in stops:
                stop()
            with open(os.path.join(building, "made.json"), "w") as f:
                json.dump(made, f)
            os.rename(building, os.path.join(root, name))
    with open(done) as f:
        return json.load(f), name


class Town:
    """`cleanup` (a test's addCleanup or addClassCleanup) receives close() before serve first starts; `furnished`
    False leaves the town as genesis made it; `fresh` runs genesis here rather than copying the run's template."""

    def __init__(self, directory, run_genesis=True, *, cleanup, furnished=True, fresh=False):
        from deploy import genesis
        from transport.config import LIBRARY
        from transport.host import HostClient
        self.opener = genesis.OPENER
        self.state = os.path.join(directory, "state")
        self.journal = os.path.join(self.state, "town.journal")
        self.client = self.stop = None
        cleanup(self.close)
        # each start hands close() its serve's stop before that serve starts
        self.start = lambda: served(self.state, cleanup=lambda stop: setattr(self, "stop", stop), opener=self.opener, library=LIBRARY)
        self.made, self.refusal = [], None
        if run_genesis and not fresh:
            self.made, name = template(furnished)
            shutil.copytree(os.path.join(TEMPLATES(), name, "state"), self.state, ignore=_transient, dirs_exist_ok=True)
        self.process = self.start()
        self.client = HostClient(self.process.root)
        if run_genesis and fresh:
            self.made, self.refusal = genesis.run(self.client)
            assert self.refusal is None and all(m["status"] in ("created", "admitted") for m in self.made), (self.refusal, self.made)
            if furnished:
                self.made += furnish(self.client, self.opener)

    def send(self, **request):
        return self.client.send(request)

    def alive(self):
        return self.process.proc.poll() is None

    def reopen(self):
        self.process.stop()
        self.process = self.start()

    def close(self):
        if self.client:
            self.client.close()
        if self.stop:
            self.stop()
