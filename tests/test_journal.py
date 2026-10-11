"""A source module is journaled once and named by CID after, a journal opens in one process at a
time, and a second object of the same source carries none.

Evidence for FOUNDATION §2 Journal (layer: host).

Journal weight: each source module is journaled once, by CID, and each distinct package
compiles once per process (creation and replay alike).
"""
import os
import unittest

from tests.test_reflection import Reflection
from tests.wire import boolean, empty, label, nil, record
from tests.host import ROOT

BELL = open(os.path.join(ROOT, "tests", "fixtures", "objects", "Bell.obend")).read()
SEED = record(colour={"tag": "variant", "label": "silver", "payload": empty()}, seed=label("s"),
              rains={"tag": "variant", "label": "rows", "payload": record(items=nil())}, rung=boolean(False), planting=label(""), planter=label("glm"), planterHandle=label(""))


class Sources(Reflection):
    def bell(self, name):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name, source=BELL,
                           entry="initial", seed=SEED)
        self.assertEqual(r["status"], "created", r)
        return r["receipt"]

    def test_a_source_is_carried_by_the_first_entry_that_needs_it_and_named_by_cid_after(self):
        self.open_library()
        first, second = self.bell("a"), self.bell("b")
        [carried] = first["sources"]
        self.assertEqual(carried["source"], BELL)
        self.assertNotIn("sources", second)
        for entry in (first, second):
            [module] = entry["outcome"]["compile"]["modules"]
            self.assertEqual(module, {"name": "Main", "cid": carried["cid"]})
        self.assertEqual(sum(line.count("def initial(") for line in self.lines()), 1)


class Lock(Reflection):
    def test_a_second_process_cannot_open_a_held_journal_and_the_first_still_commits(self):
        self.open_library()
        self.assertTrue(self.host.send(op="world-status")["locked"])
        other = self.spawn()
        refused = other.send(op="world-open", path=self.path)
        self.assertEqual(refused, {"status": "error", "message": "journal is open in another process"})
        self.assertEqual(self.host.send(op="world-create", principal="ember", identity="mk", object="a", source=BELL,
                                        entry="initial", seed=SEED)["status"], "created")
        # The same process may reopen its own journal; once it lets go, the other may open it.
        self.assertEqual(self.host.send(op="world-open", path=self.path)["status"], "opened")
        self.release()
        opened = other.send(op="world-open", path=self.path)
        self.assertEqual((opened["status"], opened["objects"]), ("opened", 1), opened)


if __name__ == "__main__":
    unittest.main()
