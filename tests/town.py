"""The town as deploy builds it, for the properties and the scenarios: `delvetalk-obend serve` over
<directory>/state (the transport's clock, the library sealed as deploy seals it, the town's journal
state/town.journal) after `deploy/genesis.py` has run. `send(**request)` goes over the root socket, which
takes every principal's ops, the opener's included; `reopen()` restarts serve, so the next request replays
the journal."""
import os

from tests.host import served


class Town:
    """`cleanup` (a test's addCleanup or addClassCleanup) receives close() before serve first starts."""

    def __init__(self, directory, run_genesis=True, *, cleanup):
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
