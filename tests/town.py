"""The town as deploy builds it, for the properties and the scenarios: a production
`transport.hostproc.Host` over <directory>/world.journal (the transport's clock, the library sealed as
hostd seals it) after `deploy/genesis.py` has run. `send(**request)`; `reopen()` kills the process, so
the next request replays the journal."""
import os

from tests.host import binary


class Town:
    def __init__(self, directory, run_genesis=True):
        from deploy import genesis
        from transport.hostd import sealed_library
        from transport.hostproc import LIBRARY, Host as Process
        self.opener = genesis.OPENER
        self.journal = os.path.join(directory, "world.journal")
        library = sealed_library(LIBRARY, os.path.join(directory, "library"))
        self.process = Process(self.journal, binary(), clock="transport", opener=self.opener, library=library,
                               librarian=self.opener, sync="none")
        if run_genesis:
            made, refusal = genesis.run(self.process)
            assert refusal is None and all(m["status"] == "created" for m in made), (refusal, made)

    def send(self, **request):
        return self.process.send(request)

    def reopen(self):
        self.process.close()

    def close(self):
        self.process.close()
