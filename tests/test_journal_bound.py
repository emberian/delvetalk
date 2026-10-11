"""The journal's byte bound is met at append, as a receipt, not at the next restart (docs/OPERATIONS.md §c 1).

Evidence for HOST-HANDOFF 5.124 (layer: host). `Limits.maxJournalBytes` was checked only when a journal
opened, so a live host appended past it and the next restart refused the file. Now an append that would
come within `Limits.journalHeadroom` (1 MiB) of the bound is refused `capacity` naming the bound, the
refusal itself journaled (it fits the headroom), and past the bound nothing is appended at all. Refuted
by an admitted turn past the threshold, a refusal that does not name the bound or is not journaled, or a
journal over its bound that opens. `world-open {maxJournalBytes}` lowers the bound for one process (never
raises it), so the test need not write 256 MiB.
"""
import os
import tempfile
import unittest

from tests.host import Host
from tests.wire import nat, record
from tests.bend import counter_modules

MIB = 1 << 20


class JournalBound(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "world.journal")
        self.host = None
        self.open()
        made = self.host.send(op="world-create", principal="e", identity="mk", object="c", modules=counter_modules(),
                              entry="initial", seed=record(count=nat(0)))
        self.assertEqual(made["status"], "created", made)

    def tearDown(self):
        if self.host:
            self.host.close()

    def open(self, **bound):
        if self.host:
            self.host.close()
        self.host = Host()
        return self.host.send(op="world-open", path=self.path, sync="none", **bound)

    def bump(self, n):
        return self.host.send(op="world-turn", principal="e", object="c", method="bump", argument=record(), identity="b%d" % n)

    def test_an_append_near_the_bound_is_a_capacity_receipt_and_past_it_nothing_is_appended(self):
        size = os.path.getsize(self.path)
        # A journal over its bound does not open, and the bound is never raised past its cap.
        for bound in (size - 1, 1 << 40, "big"):
            self.assertEqual(self.open(maxJournalBytes=bound)["status"], "error", bound)
        self.assertIn("maxJournalBytes", self.open(maxJournalBytes=size - 1)["message"])
        self.assertEqual(self.open(maxJournalBytes=size + MIB + 3000)["status"], "opened")
        admitted = 0
        for n in range(40):
            r = self.bump(n)
            if r["status"] != "admitted":
                break
            admitted += 1
        self.assertGreater(admitted, 0)
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"]), ("refused", "capacity"), r)
        self.assertIn("maxJournalBytes", out["reason"])
        # The refusal is journaled: the receipt answers by identity, and the journal reopens.
        again = self.host.send(op="world-receipt", principal="e", identity="b%d" % admitted)
        self.assertEqual(again["receipt"]["hash"], r["receipt"]["hash"])
        self.assertLessEqual(os.path.getsize(self.path), size + MIB + 3000)
        self.assertEqual(self.open(maxJournalBytes=size + MIB + 3000)["status"], "opened")
        # Inside the headroom only refusals are written; one that would cross the bound is not.
        full = self.open(maxJournalBytes=os.path.getsize(self.path) + 100)
        self.assertEqual(full["status"], "opened", full)
        before = os.path.getsize(self.path)
        r = self.bump(99)
        self.assertEqual(r["status"], "error", r)
        self.assertIn("maxJournalBytes", r["message"])
        self.assertEqual(os.path.getsize(self.path), before)

if __name__ == "__main__":
    unittest.main()
