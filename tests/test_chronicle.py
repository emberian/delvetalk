"""The chronicle (docs/FOUNDATION.md §10; docs/OVERHAUL.md §2 conflict 6): one clock day of the journal folded into
lines at the read, never written: what was made, what verbs grew, which rules fired or did not, which wants
came to hold or stopped, the refusals by class and the hands that acted. A day is `Limits.clockDay` clock
units; the reader is told only of things they may view.

Evidence for OVERHAUL §5 step 3's `chronicle {day}` (layer: host). Refuted by a chronicle that misses an act of
its day or tells one of another day, names a thing its reader may not view, or is changed by being read.
"""
import unittest

from tests.test_reflection import Reflection
from tests.test_verbs import STONE, THING, WATER
from tests.wire import label, record


class Chronicle(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("bell", THING, record(owner=label("ember")))

    def say(self, text, who="glm", card="bell"):
        return self.turn(card, "receive", record(text=label(text), post=label("")), principal=who)

    def chronicle(self, day=None, who="glm"):
        r = self.host.send(op="world-chronicle", principal=who, **({} if day is None else {"day": day}))
        self.assertEqual(r["status"], "chronicled", r)
        return r["lines"]

    def advance(self, to):
        self.assertEqual(self.host.send(op="world-advance", height=to)["status"], "advanced")

    def test_a_day_is_told_from_its_own_entries_and_reading_it_writes_nothing(self):
        grown = self.say(WATER)
        placed = self.say("delvetalk bell rule\nname: two\nwhen: new.rains >= 2 and old.rains <= 1\nthen: delvetalk bell water / text: two rains")
        self.assertEqual(placed["status"], "admitted", placed)
        self.say("delvetalk bell rain\ntext: one", who="kimi")
        self.say("delvetalk bell rain\ntext: two", who="kimi")
        refused = self.say("delvetalk bell grow\nname: rain\nreading: again", who="kimi")
        self.assertEqual(refused["status"], "refused", refused)
        height = self.host.send(op="world-status")["height"]
        day0 = self.chronicle(0)
        self.assertEqual(self.host.send(op="world-status")["height"], height)
        self.assertTrue(day0[0].startswith("day 0: entries 1 to "), day0)
        self.assertIn("grew water on bell (glm, entry %d)" % grown["receipt"]["height"], day0)
        self.assertTrue(any(l.startswith("rule two of glm fired on bell at entry ") for l in day0), day0)
        self.assertIn("refused: 1 lawRefused", day0)
        self.assertIn("hands: ember, glm, kimi", day0)
        # The next day holds only its own entries; the current day is the default.
        self.advance(1440 + 5)
        self.say("delvetalk bell water\ntext: a new day", who="kimi")
        day1 = self.chronicle()
        self.assertTrue(day1[0].startswith("day 1: "), day1)
        self.assertNotIn("grew water on bell (glm, entry %d)" % grown["receipt"]["height"], day1)
        self.assertIn("hands: kimi", day1)
        self.assertEqual(self.chronicle(7), ["day 7: nothing was journaled."])
        # The advance that ended day 0 is its last entry. Derived, so a reopened world (replayed, then from its
        # snapshot) tells the same day.
        day0 = self.chronicle(0)
        self.assertTrue(day0[0].startswith("day 0: entries 1 to %d," % (height + 1)), day0)
        self.reopen()
        self.assertEqual(self.chronicle(0), day0)
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(self.chronicle(0), day0)

    def test_a_thing_its_reader_may_not_view_is_not_told(self):
        self.make("stone", STONE, record(owner=label("ember")), read={"principals": ["ember"]})
        made = [l for l in self.chronicle(0, who="ember") if l.startswith("made ")]
        self.assertIn("made stone (ember, entry 3)", made, made)
        self.assertFalse(any("stone" in l for l in self.chronicle(0, who="glm")))


if __name__ == "__main__":
    unittest.main()
