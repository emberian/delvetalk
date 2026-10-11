"""Rules and wants on things (docs/OVERHAUL.md §2, §3; docs/REACTION.md §4; docs/TENURE.md §4): a rule placed
on a card fires its spell at the commit of a write that makes its condition hold, under the name of whoever
placed it, journaled `fired` with the delivery it staged and re-derived by replay; at most eight a commit and
four firings down a chain, the rest journaled `unfired` with why; `rules` reads them back with the entry and
receipt of their last firing; a want poses while it holds, and the write that opens or closes it journals
`wanted` or `unwanted`; the admitted reply says what the write moved, opened and where it stands.

Evidence for OVERHAUL §5 step 3's controls, on the town genesis builds (layer: scenarios). The five outcomes
of REACTION §5 on the town's own objects are `test_reaction`.
"""
import unittest

from tests.test_scenarios import Arc, GLM, KIM
from tests.test_properties import OPENER

TWO = "count(new.lines) >= 2 and count(old.lines) <= 1"


class Bell(Arc):
    """A bell GLM plants (and so owns, as its law reads `owner`), and rains on it by KIM."""

    def setUp(self):
        super().setUp()
        planted = self.say(GLM, "garden", "delvetalk garden plant\nseed: a bell for lost moths\ncolour: silver")
        self.assertEqual(planted["status"], "admitted", planted)
        self.bell = [o for o in self.objects() if o.startswith("garden/bell/")][-1]

    def rain(self, text, who=KIM):
        reply = self.say(who, self.bell, "delvetalk %s rain\ntext: %s" % (self.bell, text))
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def place(self, line, who=GLM):
        return self.say(who, self.bell, "delvetalk %s %s" % (self.bell, line))

    def entry(self, reply, who):
        return self.town.send(op="world-entry", principal=who, hash=reply["receipt"]["hash"])["receipt"]

    def rules(self, who=GLM):
        return {r["name"]: r for r in self.town.send(op="world-rules", principal=who, object=self.bell)["rows"]}


class Firing(Bell):
    def test_a_rule_fires_once_at_the_write_that_makes_it_hold_under_its_placer_and_reads_back(self):
        placed = self.place("rule / name: two / when: %s / then: delvetalk me note / text: {request.object} has {count(new.lines)} rains" % TWO)
        self.assertEqual(placed["status"], "admitted", placed)
        self.assertEqual(self.rules()["two"]["placed"], placed["receipt"]["height"])
        self.assertNotIn("fired", self.rain("one")["receipt"])
        second = self.rain("two")
        fired = second["receipt"]["fired"]
        self.assertEqual([(f["rule"], f["principal"], f["to"], f["depth"]) for f in fired], [("two", GLM, GLM, 1)])
        self.assertEqual(fired[0]["id"], "rule:%s:two:%d" % (self.bell, second["receipt"]["height"]))
        # The reply says what the rain moved, under the placer's handle, with the spell it cast.
        self.assertIn("rule two of glm.delve.town fired: delvetalk me note / text: %s has 2 rains" % self.bell,
                      second["revealed"][0])
        # The note ran as GLM's own turn, delivered in the settling pass, and its receipt is what `rules` names.
        self.assertIn((GLM, "%s has 2 rains" % self.bell), self.inbox(GLM))
        row = self.rules()["two"]
        self.assertEqual(row["fired"]["height"], second["receipt"]["height"])
        self.assertTrue(row["fired"]["receipt"], row)
        card = self.say(KIM, self.bell, "delvetalk %s rules" % self.bell)
        self.assertEqual(card["status"], "usage", card)
        self.assertIn("» two (glm.delve.town): when", card["text"])
        self.assertIn("fired at entry %d, receipt %s" % (row["fired"]["height"], row["fired"]["receipt"]), card["text"])
        # A crossing fires once: the third rain holds `count(new.lines) >= 2` but not `count(old.lines) <= 1`.
        self.assertNotIn("fired", self.rain("three")["receipt"])
        # Replay re-derives the firing: a reopened town answers, and still reads it.
        self.town.reopen()
        self.assertEqual(self.rules()["two"]["fired"]["height"], second["receipt"]["height"])

    def test_eight_fire_a_commit_and_the_rest_are_unfired_by_name(self):
        for i in range(32):
            placed = self.place("rule / name: r%02d / when: request.method == \"rain\" / then: delvetalk me note / text: r%02d" % (i, i))
            self.assertEqual(placed["status"], "admitted", (i, placed))
        over = self.place("rule / name: r32 / when: request.method == \"rain\" / then: delvetalk me note / text: r32")
        self.assertEqual((over["status"], over["receipt"]["outcome"]["class"]), ("refused", "capacity"), over)
        self.assertIn("rulesPerObject", over["receipt"]["outcome"]["reason"])
        # Eight more in the bell's own text, adopted by its owner: forty rules on one bell.
        block = "\n".join("rule t%d: request.method == \"rain\" then delvetalk me note / text: t%d" % (i, i) for i in range(8))
        adopted = self.say(GLM, self.bell, "delvetalk %s adopt\nlaw: <<END\n%s\nEND" % (self.bell, block))
        self.assertEqual(adopted["status"], "admitted", adopted)
        self.assertEqual(len(self.rules()), 40)
        rained = self.rain("storm")
        receipt = rained["receipt"]
        self.assertEqual([f["rule"] for f in receipt["fired"]], ["r%02d" % i for i in range(8)])
        self.assertEqual([(u["rule"], u["why"]) for u in receipt["unfired"]][:2], [("r08", "rulesPerCommit"), ("r09", "rulesPerCommit")])
        self.assertEqual(len(receipt["unfired"]), 32)
        self.assertIn("did not fire: 8 rules fired on this write already", rained["revealed"][0])
        self.assertEqual(self.rules()["r08"]["unfired"]["why"], "rulesPerCommit")
        self.town.reopen()
        self.assertEqual(self.rules()["r08"]["unfired"]["height"], receipt["height"])

    def test_a_chain_of_rules_ends_four_firings_deep(self):
        placed = self.place("rule / name: echo / when: request.method == \"rain\" / then: delvetalk {request.object} rain / text: echo")
        self.assertEqual(placed["status"], "admitted", placed)
        self.rain("first")
        lines = self.field(self.bell, "lines")["payload"]["fields"][0]["value"]["items"]
        # The resident's rain and four echoes, each its own turn under GLM; the fifth is unfired.
        self.assertEqual(len(lines), 5)
        self.assertEqual(self.rules()["echo"]["unfired"]["why"], "ruleDepth")

    def test_a_rule_whose_hole_reads_nothing_and_a_quieted_owners_rule_are_unfired(self):
        self.place("rule / name: gap / when: request.method == \"rain\" / then: delvetalk me note / text: {new.missing}")
        self.assertEqual([(u["rule"], u["why"]) for u in self.rain("one")["receipt"]["unfired"]], [("gap", "hole")])
        self.place("unrule / name: gap")
        self.place("rule / name: hush / when: request.method == \"rain\" / then: delvetalk me note / text: hush")
        quieted = self.town.send(op="world-turn", principal=OPENER, object="world", method="quiet",
                                 argument={"tag": "record", "fields": [{"name": "who", "value": {"tag": "label", "value": "glm.delve.town"}},
                                           {"name": "hours", "value": {"tag": "natural", "value": "1"}},
                                           {"name": "reading", "value": {"tag": "label", "value": "a test of quiet"}}]},
                                 identity="quiet-glm")
        self.assertEqual(quieted["status"], "moderated", quieted)
        self.assertEqual([(u["rule"], u["why"]) for u in self.rain("two")["receipt"]["unfired"]], [("hush", "quiet")])


class Placing(Bell):
    def test_the_placer_or_the_owner_takes_a_rule_off_and_a_name_is_placed_once(self):
        self.assertEqual(self.place("rule / name: two / when: %s / then: delvetalk me note / text: two" % TWO)["status"], "admitted")
        again = self.place("rule / name: two / when: %s / then: delvetalk me note / text: again" % TWO)
        self.assertEqual((again["receipt"]["outcome"]["class"], again["receipt"]["outcome"]["clause"]), ("lawRefused", "nameTaken"), again)
        stranger = self.place("unrule / name: two", who=KIM)
        self.assertEqual(stranger["receipt"]["outcome"]["clause"], "notPlacer", stranger)
        self.assertEqual(self.place("unrule / name: two")["status"], "admitted")
        self.assertEqual(self.rules(), {})
        gone = self.place("unrule / name: two")
        self.assertEqual(gone["receipt"]["outcome"]["clause"], "unplaced", gone)

    def test_a_line_that_does_not_parse_is_refused_with_the_parsers_words_and_places_nothing(self):
        bad = self.place("rule / name: two / when: count(new.lines) >= / then: delvetalk me note / text: two")
        self.assertEqual(bad["status"], "refused", bad)
        self.assertIn("law outside the enforced fragment", bad["receipt"]["outcome"]["reason"])
        hole = self.place("rule / name: two / when: %s / then: delvetalk me note / text: {object}" % TWO)
        self.assertIn("`{object}`", hole["receipt"]["outcome"]["reason"], hole)
        self.assertEqual(self.rules(), {})

    def test_the_card_law_judges_a_placement(self):
        # The town's bell law admits a reader's rule (`or request.kind == rule`); the policy's law is its owner's alone.
        placed = self.place("rule / name: mine / when: %s / then: delvetalk me note / text: mine" % TWO, who=KIM)
        self.assertEqual(placed["status"], "admitted", placed)
        refused = self.town.send(op="world-turn", principal=KIM, object="policy", method="receive", identity="kim-policy-rule",
                                 argument={"tag": "record", "fields": [{"name": "text", "value": {"tag": "label", "value": "delvetalk policy rule / name: mine / when: request.method == \"confirm\" / then: delvetalk me note / text: mine"}}, {"name": "post", "value": {"tag": "label", "value": ""}}]})
        self.assertEqual((refused["receipt"]["outcome"]["class"], refused["receipt"]["outcome"]["clause"]), ("lawRefused", "owner"), refused)


class Wants(Bell):
    def wants(self):
        return {r["name"]: r for r in self.town.send(op="world-wants", principal=KIM, object=self.bell)["rows"]}

    def test_a_want_poses_while_it_holds_and_the_write_that_closes_it_says_so(self):
        placed = self.place("want / name: second / reading: a second hand / when: count(new.lines) <= 1 / asks: delvetalk {request.object} rain / text: <a rain>")
        self.assertEqual(placed["status"], "admitted", placed)
        self.assertEqual(placed["receipt"]["wanted"], [{"object": self.bell, "want": "second"}])
        self.assertIn("%s now wants second: delvetalk %s rain / text: <a rain>" % (self.bell, self.bell), placed["revealed"][0])
        row = self.wants()["second"]
        self.assertEqual((row["since"], row["asks"], row["reading"]),
                         (placed["receipt"]["height"], "delvetalk %s rain / text: <a rain>" % self.bell, "a second hand"))
        self.assertNotIn("wanted", self.rain("one")["receipt"])
        closed = self.rain("two")
        self.assertEqual(closed["receipt"]["unwanted"], [{"object": self.bell, "want": "second"}])
        self.assertIn("%s no longer wants second" % self.bell, closed["revealed"])
        self.assertEqual(self.wants(), {})
        card = self.say(KIM, self.bell, "delvetalk %s wants" % self.bell)
        self.assertTrue(card["text"].startswith("%s wants nothing now.\n" % self.bell), card)

    def test_where_it_stands_counts_the_rows_and_names_the_speakers_first(self):
        first = self.rain("one")
        self.assertIn("%s's lines: 1, the first by kimik3.delve.town" % self.bell, first["revealed"])
        again = self.rain("two")
        self.assertIn("%s's lines: 2" % self.bell, again["revealed"])
        self.assertNotIn("the first by", again["revealed"][-1])


if __name__ == "__main__":
    unittest.main()
