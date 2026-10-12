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



class CarriedTown(unittest.TestCase):
    """A carried town's refresh (deploy/genesis.py `refresh`: the opener's `refresh-*` turns after the carried genesis)
    is the host's upkeep, not the town's: the chronicle counts none of it among the day's admitted acts or hands, and
    names none of it as a first; the firsts are residents' acts and the makings the carry kept. Refuted by the v12
    carry of 2026-10-12, whose day read "58 admitted", "hands: ember.delve.town", the porch's first room at a refresh
    entry and bell/1's coinage at another."""

    def test_the_refresh_is_no_act_of_the_day_and_no_first(self):
        import re
        import subprocess
        import tempfile
        import unittest.mock
        from deploy import genesis
        from tests.host import binary
        from tests.test_properties import STRANGERS
        from tests.town import Town
        from transport.host import HostProcess
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        kim, handle = next(iter(STRANGERS.items()))
        rain = lambda send, n: send(op="world-turn", principal=kim, object="bell/1", method="receive", identity="rain-%d" % n,
                                    argument=record(text=label("delvetalk bell/1 rain / text: rain %d" % n), post=label("at://%s/post/%d" % (kim, n))))
        # The world before: an older law, so the refresh has things to bring to the image's; a resident's rain.
        old_record = genesis.RECORD_LAW.rsplit("\nwant pending", 1)[0]
        old_kinds = [(n, of, form, head, "\n".join([old_record] + ([law.split("\nrule seven", 1)[0]] if law else [])), body)
                     for n, of, form, head, law, body in genesis.KINDS]
        with unittest.mock.patch.multiple(genesis, RECORD_LAW=old_record, KINDS=old_kinds):
            town = Town(tmp.name, cleanup=self.addCleanup)
        town.send(op="world-arrive", principal="transport", did=kim, handle=handle)
        self.assertEqual(rain(town.send, 1)["status"], "admitted")
        firsts = lambda text: [l for l in text.splitlines() if l.strip().startswith("the first ")]
        history = lambda send: (lambda r: r.get("whole") or r["text"])(send(op="world-surface", principal="anonymous", read="chronicle"))
        before = firsts(history(town.send))
        self.assertTrue(any("the first room: " in l for l in before), before)
        self.assertEqual(town.send(op="world-snapshot")["status"], "snapshot")
        town.close()
        out = tmp.name + "/carried.journal"
        p = subprocess.run([binary(), "carry", "--from", town.journal, "--out", out, "--reason", "a newer host"],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr)
        host = HostProcess(binary(), out)
        self.addCleanup(host.close)
        rows = genesis.refresh(host, genesis.OPENER, genesis.ancestry(out))
        self.assertTrue(any(r["status"] == "refreshed" for r in rows), rows)
        self.assertEqual(rain(host.send, 2)["status"], "admitted")  # the town's one act since the carry
        lines = host.send(op="world-chronicle", principal="anonymous")["lines"]
        start, stop = map(int, re.match(r"day \d+: entries (\d+) to (\d+), ", lines[0]).groups())
        entries = host.send(op="world-entries", principal=genesis.OPENER, after=start - 1, limit=100)["entries"]
        refreshes = [e["height"] for e in entries if e["identity"]["intent"].startswith("refresh-")]
        self.assertTrue(refreshes and all(start <= h <= stop for h in refreshes), (refreshes, lines[0]))
        # The rain and the delivery it sent: kim's, the day's only acts.
        acts = [e["height"] for e in entries if e["outcome"].get("tag") == "admitted" and e["height"] not in refreshes]
        self.assertEqual({e["identity"]["principal"] for e in entries if e["height"] in acts}, {kim})
        self.assertTrue(lines[0].endswith(", %d admitted." % len(acts)), (lines, acts))
        self.assertEqual([l for l in lines if l.startswith("hands: ")], ["hands: " + handle], lines)
        # What the refresh made a thing want is still the day's news of that thing.
        self.assertTrue(any(re.fullmatch(r".+ came to want .+ at entry (\d+)", l) and int(l.rsplit(" ", 1)[1]) in refreshes for l in lines), lines)
        after = firsts(history(host.send))
        self.assertEqual(after, before)
        for h in refreshes:
            self.assertFalse(any(l.endswith("entry %d" % h) for l in after), (h, after))


if __name__ == "__main__":
    unittest.main()
