"""Journal weight: each source module is journaled once, by CID, and each distinct package
compiles once per process (creation and replay alike).

Measured on this branch, 500 Bells from world/objects in a library world: before, create
135 s, reopen 133 s, journal 3.14 MB; after, create 4.3 s, reopen 0.5 s, journal 0.82 MB.
"""
import json
import os
import time
import unittest

from tests.test_chain import boolean, empty, nil, reference
from tests.test_reflection import ROOT, Reflection
from tests.test_turn_world import label, record

BELL = open(os.path.join(ROOT, "world", "objects", "Bell.obend")).read()
SEED = record(colour={"tag": "variant", "label": "silver", "payload": empty()}, seed=label("s"),
              rains={"tag": "variant", "label": "rows", "payload": record(items=nil())}, rung=boolean(False), planting=label(""), planter=label("glm"), planterHandle=label(""), observers=nil())


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
        self.assertEqual(sum(line.count("def seeded(") for line in self.lines()), 1)

    def test_objects_rebuilt_from_cids_replay_to_the_same_state(self):
        self.open_library()
        self.bell("a")
        self.bell("b")
        before = [self.host.send(op="world-inspect", principal="ember", object=n) for n in ("a", "b")]
        self.reopen()
        self.assertEqual([self.host.send(op="world-inspect", principal="ember", object=n) for n in ("a", "b")], before)
        self.assertEqual(before[0]["source"], BELL)


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


class Maximum(Reflection):
    def test_two_hundred_bells_create_and_replay_compiling_once(self):
        self.open_library()
        started = time.time()
        for i in range(200):
            r = self.host.send(op="world-create", principal="ember", identity=f"mk{i}", object=f"bell{i}", source=BELL,
                               entry="initial", seed=SEED)
            self.assertEqual(r["status"], "created", r)
        created = time.time() - started
        reopened = time.time()
        self.reopen()
        replay = time.time() - reopened
        size = os.path.getsize(self.path)
        print(f"\n  200 bells: create {created:.2f}s, reopen {replay:.2f}s, journal {size / 1e6:.2f} MB")
        self.assertLess(created, 10.0)
        self.assertLess(replay, 3.0)
        self.assertLess(size, 600000)


if __name__ == "__main__":
    unittest.main()
