"""A plan is one turn (docs/HOST-HANDOFF.md 5.203): `delvetalk plan` (or a fence tagged `plan`) and the spells after it
run in order inside one turn of the speaker, each reading what the acts before it wrote and made (`{made N}`), every
law judged once at the commit against the world the acts leave, one receipt; any refusal refuses the whole plan and
names the act.

Evidence for HOST-HANDOFF 5.203 (layer: host). Refuted by: a plan that leaves a kind, its thing or a rule behind when
a later act is refused (in its frame or at the commit); a later act that cannot name what an earlier made; a plan of
several acts journaled as more than one entry or answered under `#1` identities; a hole naming no earlier act that
runs anyway; a plan entry that does not replay.

    python3 -W error -m unittest tests.test_plan -v
"""
import unittest

from deploy import genesis
from tests.test_chain import Chain
from tests.test_kinds import GLM, KIM
from tests.bend import closure
from tests.wire import label, record

# The thing and rule a plan makes: the rule's own hole `{new.lines}` is left for the rule.
MAKE_PLACE = ("delvetalk plan\n"
              "delvetalk kinds make / name: lamp / of: record\n"
              "delvetalk {made 1} make\n"
              'delvetalk {made 2} rule / name: lit / when: request.method == "write" / then: delvetalk {made 2} ?\n')


class Plans(Chain):
    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal="ember", identity="mk-kinds", object="kinds", modules=closure("Kind"),
                           entry="initial", seed=record(owner=label("ember"), name=label("kinds"), of=label("kind"),
                                                        form=label(genesis.KINDS_FORM), head=label("")), law=genesis.KIND_LAW)
        self.assertEqual(r["status"], "created", r)
        self.assertEqual(self.turn("kinds", "shape", record(object=label("kinds")))["status"], "admitted")

    def said(self, text, who=KIM, card="kinds", identity=None):
        self.said_n = getattr(self, "said_n", 0) + 1
        identity = identity or "plan-%d" % self.said_n
        return self.turn(card, "receive", record(text=label(text), post=label("at://x/" + identity)), principal=who, identity=identity)

    def ids(self):
        return self.host.send(op="world-objects", principal="ember")["ids"]

    def height(self):
        return self.host.send(op="world-status")["height"]

    def test_a_plan_makes_a_kind_one_of_it_and_places_a_rule_on_it_in_one_turn(self):
        before = self.height()
        r = self.said(MAKE_PLACE, identity="post-make")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(r["receipt"]["identity"]["intent"], "post-make")  # the post's own identity, no `#1`
        self.assertEqual(r["receipt"]["height"], before + 1)
        acts = r["plan"]["acts"]
        self.assertEqual([(a["act"], a["done"], a.get("made")) for a in acts],
                         [(1, "ran", ["kind/lamp"]), (2, "ran", ["lamp/1"]), (3, "staged", None)], acts)
        self.assertEqual(r["revealed"][:3], ["1. delvetalk kinds make / name: lamp / of: record: made kind/lamp",
                                             "2. delvetalk {made 1} make: made lamp/1",
                                             '3. delvetalk {made 2} rule / name: lit / when: request.method == "write" / then: delvetalk {made 2} ?: placed'])
        self.assertIn("kind/lamp", self.ids())
        self.assertIn("lamp/1", self.ids())
        rules = self.host.send(op="world-rules", principal=KIM, object="lamp/1")["rows"]
        self.assertEqual([(x["name"], x["owner"]) for x in rules], [("lit", KIM)], rules)
        # The kind counts the thing an act of the same turn made of it.
        self.assertEqual(self.state("kind/lamp")["fields"][[f["name"] for f in self.state("kind/lamp")["fields"]].index("count")]["value"],
                         {"tag": "natural", "value": "1"})
        # A retry is answered from the identity; the journal replays the plan's one entry.
        again = self.said(MAKE_PLACE, identity="post-make")
        self.assertEqual(again["receipt"]["hash"], r["receipt"]["hash"])
        self.reopen()
        self.assertEqual(self.host.send(op="world-rules", principal=KIM, object="lamp/1")["rows"], rules)
        self.assertIn("lamp/1", self.ids())

    def test_a_plan_whose_third_act_is_refused_commits_nothing(self):
        # The third act refused in its frame (no such spell), and at the commit (the law of the hand's lantern
        # refuses kim's amendment): either way no kind, no thing, one refused entry naming act 3.
        made = self.said('delvetalk plan\ndelvetalk kinds make / name: lantern / of: record / law: ' + genesis.RECORD_LAW.split("\n")[0] +
                         '\ndelvetalk {made 1} make', who="ember")
        self.assertEqual((made["status"], made["plan"]["acts"][1].get("made")), ("admitted", ["lantern/1"]), made)
        for third, clause in (("delvetalk {made 2} polish", "noAction"),
                              ('delvetalk lantern/1 adopt / law: law mine "kim\'s": request.subject == "%s"' % KIM, "owner")):
            with self.subTest(clause=clause):
                before = self.height()
                text = ("delvetalk plan\ndelvetalk kinds make / name: wick / of: record\ndelvetalk {made 1} make\n" + third)
                r = self.said(text)
                self.assertEqual(r["status"], "refused", r)
                self.assertEqual(r["receipt"]["height"], before + 1)
                self.assertEqual(r["receipt"]["outcome"].get("clause"), clause, r)
                self.assertEqual(r["plan"]["refused"], 3, r["plan"])
                self.assertEqual((r["public"]["act"], r["public"]["acts"]), (3, 3), r["public"])
                self.assertNotIn("kind/wick", self.ids())
                self.assertNotIn("wick/1", self.ids())
        self.assertIn("act 3 (delvetalk {made 2} polish)", self.said(
            "delvetalk plan\ndelvetalk kinds make / name: wick / of: record\ndelvetalk {made 1} make\ndelvetalk {made 2} polish")["receipt"]["outcome"]["reason"])

    def test_a_hole_names_only_what_an_earlier_act_made(self):
        for text, why in (("delvetalk plan\ndelvetalk kinds make / name: cup / of: record\ndelvetalk {made 3} make", "{made 3} names no act before act 2"),
                          ("delvetalk plan\ndelvetalk kinds ?\ndelvetalk {made 1} make", "{made 1}: act 1 made nothing")):
            with self.subTest(text=text):
                r = self.said(text)
                self.assertEqual((r["status"], r["receipt"]["outcome"]["clause"]), ("refused", "hole"), r)
                self.assertIn(why, r["receipt"]["outcome"]["reason"])
                self.assertNotIn("kind/cup", self.ids())

    def test_a_plan_of_too_many_acts_is_refused_whole(self):
        acts = "".join("delvetalk kinds make / name: k%d / of: record\n" % i for i in range(9))
        r = self.said("delvetalk plan\n" + acts)
        self.assertEqual((r["status"], r["receipt"]["outcome"]["clause"]), ("refused", "tooManyActs"), r)
        self.assertNotIn("kind/k0", self.ids())

    def test_a_fenced_plan_with_prose_around_it_is_the_same_turn(self):
        r = self.said("making a lamp and one of it:\n```plan\n  delvetalk kinds make / name: lamp / of: record\n  delvetalk {made 1} make\n```\nthanks!")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual([a.get("made") for a in r["plan"]["acts"]], [["kind/lamp"], ["lamp/1"]])

    def test_later_acts_read_what_earlier_acts_wrote(self):
        """A thing written by act 2 is read by act 3 as act 2 left it: two writes to the thing an act made, both kept."""
        r = self.said("delvetalk plan\ndelvetalk kinds make / name: log / of: record\ndelvetalk {made 1} make\n"
                      "delvetalk {made 2} write / text: first\ndelvetalk {made 2} write / text: second", who=GLM)
        self.assertEqual(r["status"], "admitted", r)
        lines = [f for f in self.state("log/1")["fields"] if f["name"] == "lines"][0]["value"]
        self.assertEqual(str(lines).count("first") + str(lines).count("second"), 2, lines)


if __name__ == "__main__":
    unittest.main()
