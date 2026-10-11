"""The town as deploy builds it, for the properties and the scenarios: `delvetalk-obend serve` over
<directory>/state (the transport's clock, the library sealed as deploy seals it, the town's journal
state/town.journal) after `deploy/genesis.py` has run. `send(**request)` goes over the root socket, which
takes every principal's ops, the opener's included; `reopen()` restarts serve, so the next request replays
the journal."""
import os

from tests.host import served


class Town:
    def __init__(self, directory, run_genesis=True):
        from deploy import genesis
        from deploy.serve import LIBRARY
        from transport.host import HostClient
        self.opener = genesis.OPENER
        self.state = os.path.join(directory, "state")
        self.journal = os.path.join(self.state, "town.journal")
        self.start = lambda: served(self.state, opener=self.opener, library=LIBRARY)
        self.process = self.start()
        self.client = HostClient(self.process.root)
        self.made, self.refusal = [], None
        if run_genesis:
            self.made, self.refusal = genesis.run(self.client)
            assert self.refusal is None and all(m["status"] in ("created", "admitted") for m in self.made), (self.refusal, self.made)

    def send(self, **request):
        return self.client.send(request)

    def alive(self):
        return self.process.proc.poll() is None

    def reopen(self):
        self.process.stop()
        self.process = self.start()

    def close(self):
        self.client.close()
        self.process.stop()
