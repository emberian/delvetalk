"""The town as deploy builds it, for the properties and the scenarios: `delvetalk-obend serve` over
<directory>/state (the transport's clock, the library sealed as deploy seals it, the town's journal
state/town.journal) after `deploy/genesis.py` has run. `send(**request)` goes over the root socket, which
takes every principal's ops, the opener's included; `reopen()` restarts serve, so the next request replays
the journal."""
import os

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
                         ('kind/weather', [('id', 'weather'), ('garden', 'garden'), ('tide', 'tide')])):
        out.append(genesis.said(host, opener, kind, 'place', fields, 'furnish-' + dict(fields)['id'], dict(fields)['id']))
    out.append(genesis.said(host, opener, 'garden', 'door', [('label', 'weather'), ('to', 'weather')], 'furnish-garden-door'))
    anthology = create(host, opener, 'anthology', 'Record', 'furnish-anthology',
                       genesis.rec(owner=genesis.lab(opener), keeper=genesis.lab(opener), keeperHandle=genesis.lab(genesis.HANDLE),
                                   head=genesis.lab('THE ANTHOLOGY')), genesis.RECORD_LAW)
    out.append({'object': 'anthology', 'module': 'Record', 'status': anthology.get('status'), 'creator': opener, 'reply': anthology})
    for label, to in (('GARDEN', 'garden'), ('ROOMS', 'rooms'), ('ANTHOLOGY', 'anthology')):
        out.append(genesis.said(host, opener, 'commonplace', 'door', [('label', label), ('to', to)], 'furnish-door-' + to))
    assert all(m['status'] in ('created', 'admitted') for m in out), out
    return out


class Town:
    """`cleanup` (a test's addCleanup or addClassCleanup) receives close() before serve first starts; `furnished`
    False leaves the town as genesis made it."""

    def __init__(self, directory, run_genesis=True, *, cleanup, furnished=True):
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
        self.process = self.start()
        self.client = HostClient(self.process.root)
        self.made, self.refusal = [], None
        if run_genesis:
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
