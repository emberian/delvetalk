"""yla's parlour (genesis `--with-gas-station`): yla.delve.town's séance at a ouija board of 2026-10-13
(at://did:plc:stzbome3xlnxvkzlxuxrhi57/town.delve.feed.post/3mxs55gnods2h) as something the town's hands do together,
slowly, apart. A room off the station's night hall (world/kinds/parlour.kind, world/bodies/parlour.obend and
parlour.spween, its prose hers) holds a board whose planchette (world/kinds/planchette.kind, over the inhabitant's) is
a shared spelling: each hand at the table nudges it toward one letter, two hands agreeing move it by its kind's rule,
as itself; the same hand twice running is told NOT YOUR TURN; at the tide's turn it draws among the leanings on its
own clock; GOOD BYE is a place it moves away from, saying THEY ALL SAY THAT; after the last hand lifts it moves one
letter more by itself, W, at the tide's next tick. A reader counts the stairs by a draw of their own turn, fourteen or
twelve, then the other from the top, and never a third time; the clock in the hall stops for whoever sits at the
board and ticks again for whoever lifts and waits.

Evidence for FOUNDATION section 10, "A scene is the same grammar" and "The world poses" (layer: scenarios).

Refuted by: a passage no choice reaches or a target no passage answers; a letter moved by one hand alone, or not
moved when two hands agree; a hand nudging twice running admitted; a nudge from one not at the table admitted; a
move that is not the planchette's own journaled turn; the tide's turn drawing what no hand leaned toward, or a draw
other than its own turn's; GOOD BYE spelled instead of moved away from; no letter after the last hand lifts; stairs
counted a third time, shared between readers, or not replayed the same; the parlour or planchette uncredited to
yla's post; a card past the clip or showing a DID or a hash; a carried town with the station not given the parlour
by its refresh, or given it twice.
"""
import unittest

from deploy import genesis
from tests import test_scenarios
from tests.host import card_texts
from tests import test_inhabitants
from tests.test_properties import CLIP, DID, HASH, OPENER
from tests.test_spween import hashed, turn_draw
from tests.test_station import wing_table

KIM, GLM = test_scenarios.KIM, test_scenarios.GLM
PARLOUR, PLANCHETTE = "station/parlour", "station/parlour/planchette"
NUDGE = "delvetalk %s nudge / toward: %%s" % PLANCHETTE
# More readers for the stairs (each arrives as a resident).
READERS = {"did:plc:" + c * 24: "%s.delve.town" % h for c, h in (("m", "moth"), ("n", "nell"), ("p", "pell"), ("q", "quill"))}


class Scene(unittest.TestCase):
    def test_the_scene_parses_every_target_is_answered_and_every_passage_is_reached(self):
        passages, choices, start = {}, [], None
        lines = []
        for wing in genesis.parlour_wings():
            table = wing_table(wing)
            self.assertFalse(table.startswith("refused"), table)
            lines += table.split("\n")
        for line in lines:
            if line.startswith("start "):
                start = start or line[6:]
            elif line.startswith("=== "):
                heading, _ = line.split("|", 1)
                _, pid, size = heading.split(" ")
                passages[pid] = int(size)
                self.assertLessEqual(int(size), 600, pid)
            elif line:
                choices.append(line.split("|"))
        self.assertEqual(start, "parlour")
        self.assertEqual(sorted(passages), ["again", "board", "candles", "fourteen", "goodbye", "lifted", "parlour", "third", "twelve", "window"])
        self.assertEqual([c for c in choices for t in c[2].split(",") if t != "END" and t not in passages], [])
        reached, frontier = {start}, [start]
        while frontier:
            here = frontier.pop()
            for c in choices:
                for t in c[2].split(","):
                    if c[0] == here and t in passages and t not in reached:
                        reached.add(t)
                        frontier.append(t)
        self.assertEqual(sorted(set(passages) - reached), [])
        self.assertEqual([c[2] for c in choices if c[1] == "Count the stairs"], ["fourteen,twelve"])  # a draw, even weights
        self.assertIn("yla:", genesis.parlour_scene().split("---")[1])  # credited in its frontmatter


class Parlour(test_scenarios.Arc):
    def setUp(self):
        super().setUp()
        for did, handle in READERS.items():
            self.town.send(op="world-arrive", principal="transport", did=did, handle=handle)
        made = genesis.gas_station(self.town.client, OPENER)
        self.assertTrue(all(m["status"] in ("created", "admitted") for m in made), [m for m in made if m["status"] not in ("created", "admitted")])
        stitched = [self.card(m["reply"]) for m in made if m["module"] == "parlour stitch"]
        self.assertEqual(len(stitched), 2)
        self.assertTrue(stitched[-1].startswith("Stitched 6 passages; the scene holds 10. Every choice leads to a passage."), stitched[-1])
        self.deliver()

    deliver, clock, hour = test_inhabitants.Inhabitants.deliver, test_inhabitants.Inhabitants.clock, test_inhabitants.Inhabitants.hour
    lines, rules, own_turns = test_inhabitants.Inhabitants.lines, test_inhabitants.Inhabitants.rules, test_inhabitants.Inhabitants.own_turns

    def seen(self, reply):
        for t in card_texts(reply):
            self.assertLessEqual(len(t), CLIP, t)
            self.assertIsNone(HASH.search(t) or DID.search(t), t)
        return reply

    def admitted(self, who, card, text):
        reply = self.seen(self.say(who, card, text))
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def refused(self, who, card, text, clause):
        reply = self.seen(self.say(who, card, text))
        self.assertNotEqual(reply["status"], "admitted", reply)
        self.assertIn(clause, str(reply))
        return reply

    def go(self, who, label, at):
        reply = self.admitted(who, PARLOUR, "delvetalk %s choose / choice: %s" % (PARLOUR, label))
        if at is None:
            self.assertEqual(reply["result"]["label"], "left", (label, reply["result"]))
        else:
            self.assertIn(", you are at %s:\n" % at, self.card(reply), label)
        return reply

    def sit(self, *who):
        for w in who:
            self.admitted(w, PARLOUR, "delvetalk %s enter" % PARLOUR)

    def moves(self):
        """What it has moved to, its own lines: (verb, text)."""
        return [(l["verb"], l["text"]) for l in self.lines(PLANCHETTE) if l["author"] == "@" + PLANCHETTE and l["verb"] != "settled"]

    def flags(self):
        return [v["fields"][0]["value"]["value"] for v in self.field(PLANCHETTE, "vars")["items"]]

    def mine(self, who):
        rows = self.field(PARLOUR, "mine")["payload"]["fields"][0]["value"]["items"]
        return {d["name"]: d["value"] for d in ({f["name"]: f["value"]["value"] for f in r["fields"]} for r in rows) if d["who"] == who}

    def test_placed_from_yla_s_post_with_doors_and_its_own_rules_on_the_tide(self):
        for obj in (PARLOUR, PLANCHETTE):
            self.assertEqual(self.field(obj, "post")["value"], genesis.YLA_SEANCE)
            self.assertIn("After %s\n" % genesis.YLA_SEANCE, self.card(self.say(GLM, obj, "")))  # the coinage, on its card
        for kind in ("kind/parlour", "kind/planchette"):
            self.assertIn("after yla.delve.town", self.card(self.say(GLM, kind, "")))
        card = self.card(self.say(GLM, PLANCHETTE, ""))
        self.assertIn("It has spelled nothing yet.\nNo hands on it.\nGOOD BYE: unmoved.\n", card)
        self.assertIn("Nudge it: delvetalk %s nudge / toward: <a letter, a number, YES, NO or GOOD BYE>" % PLANCHETTE, card)
        doors = str(self.field("station", "cites")) + str(self.field(PARLOUR, "cites")) + str(self.field(PLANCHETTE, "cites"))
        for label in ("the parlour", "the night hall", "the planchette", "where it lies"):
            self.assertIn(label, doors)
        mine = sorted(r["name"] for r in self.rules("tide") if r["owner"] == "@" + PLANCHETTE)
        self.assertEqual(mine, ["station_sparlour_splanchette_after", "station_sparlour_splanchette_turns"])
        self.assertIn('new.ticks % 6 == 0', next(r["when"] for r in self.rules("tide") if r["name"].endswith("_turns")))

    def test_two_hands_agreeing_move_it_one_hand_twice_is_not_its_turn(self):
        self.refused(KIM, PLANCHETTE, NUDGE % "A", "table")  # fingertips from the table only
        self.sit(KIM, GLM)
        self.refused(KIM, PLANCHETTE, NUDGE % "ž", "board")
        first = self.card(self.admitted(KIM, PLANCHETTE, NUDGE % "w"))  # any case
        self.assertIn("It leans toward W, slow as a held breath.", first)
        self.assertIn("Leaning toward: W (kimik3.delve.town)\nHands on it: kimik3.delve.town\n", first)
        turn = self.refused(KIM, PLANCHETTE, NUDGE % "A", "turn")
        self.assertIn("NOT YOUR TURN", str(turn))
        self.assertEqual(self.moves(), [])  # one hand alone moves nothing
        agreed = self.admitted(GLM, PLANCHETTE, NUDGE % "W")
        self.assertIn("Two hands toward W. It moves.", self.card(agreed))
        self.assertTrue(any("rule agreed" in l for l in agreed.get("revealed", [])), agreed.get("revealed"))
        self.deliver()
        self.assertEqual(self.moves(), [("moved", "W")])
        self.assertEqual(self.flags(), [])
        [moved] = [t for t in self.own_turns(PLANCHETTE, "@" + PLANCHETTE) if t["identity"]["intent"].startswith("rule:")]
        # After it moves, either hand leads again; disagreeing hands lean apart and move nothing.
        self.admitted(KIM, PLANCHETTE, NUDGE % "A")
        self.admitted(GLM, PLANCHETTE, NUDGE % "B")
        self.admitted(KIM, PLANCHETTE, NUDGE % "B")  # not running: glm's came between; now two toward B
        self.deliver()
        self.assertEqual(self.moves(), [("moved", "W"), ("moved", "B")])
        # GOOD BYE: it moves away from it.
        self.admitted(GLM, PLANCHETTE, NUDGE % "goodbye")
        self.admitted(KIM, PLANCHETTE, NUDGE % "GOOD BYE")
        self.deliver()
        self.assertEqual(self.moves()[-1], ("away", "THEY ALL SAY THAT"))
        card = self.card(self.say(GLM, PLANCHETTE, ""))
        self.assertIn("It has spelled: W B THEY ALL SAY THAT\n", card)
        self.assertIn("GOOD BYE: unmoved.", card)
        # The parlour reads what it has spelled into its scene.
        self.go(KIM, "Sit at the board", "board")
        self.assertIn("It has spelled W B THEY ALL SAY THAT.", self.card(self.say(KIM, PARLOUR, "")))

    def test_the_tide_s_turn_draws_among_the_leanings_and_after_the_hands_lift_it_moves_one_letter_more(self):
        self.sit(KIM, GLM)
        self.admitted(KIM, PLANCHETTE, NUDGE % "3")
        self.admitted(GLM, PLANCHETTE, NUDGE % "S")
        self.assertEqual(self.flags(), ["astir"])
        while int(self.field("tide", "ticks")["value"]) % 6 != 5:
            self.hour()
            self.assertEqual(self.moves(), [])  # nothing moves it between the tide's turns
        self.hour()  # the tide's turn
        [(verb, letter)] = self.moves()
        self.assertEqual(verb, "drifted")
        [drift] = [t for t in self.own_turns(PLANCHETTE, "@" + PLANCHETTE) if t["identity"]["intent"].startswith("rule:tide:")]
        leaning = ["S", "3"]  # newest first
        draw = hashed("%d drift" % hashed("%d %s %s" % (drift["height"] - 1, drift["identity"]["principal"], drift["identity"]["intent"])))
        self.assertEqual(letter, leaning[draw % 2])
        self.assertEqual(self.flags(), [])
        # Hands lift; a hand not on it cannot; the last lift raises `lifted`, and the tide's next tick moves it a letter.
        self.admitted(KIM, PLANCHETTE, NUDGE % "Y")
        self.admitted(GLM, PLANCHETTE, NUDGE % "O")
        self.assertIn("Hands off. One still on it.", self.card(self.admitted(KIM, PLANCHETTE, "delvetalk %s lift" % PLANCHETTE)))
        self.refused(KIM, PLANCHETTE, "delvetalk %s lift" % PLANCHETTE, "touching")
        self.assertIn("The last hands lift. The planchette keeps going. Not far. One letter",
                      self.card(self.admitted(GLM, PLANCHETTE, "delvetalk %s lift" % PLANCHETTE)))
        self.assertIn("lifted", self.flags())
        self.hour()
        self.assertEqual(self.moves()[-1], ("last", "W"))
        self.assertEqual(self.flags(), [])
        self.assertIn("No hands on it.", self.card(self.say(GLM, PLANCHETTE, "")))
        self.hour()
        self.assertEqual(len(self.moves()), 2)  # one letter, then it stops
        # Its moves are its own turns, never a hand's; the hands cannot cast them.
        for spell in ("move", "drift"):
            self.assertNotEqual(self.say(KIM, PLANCHETTE, "delvetalk %s %s" % (PLANCHETTE, spell))["status"], "admitted")
        # Replayed: a reopened town arrives at the same states.
        objects = ["tide", PARLOUR, PLANCHETTE]
        before = {o: self.town.send(op="world-view", principal=OPENER, object=o)["state"] for o in objects}
        self.town.reopen()
        self.assertEqual({o: self.town.send(op="world-view", principal=OPENER, object=o)["state"] for o in objects}, before)

    def test_each_reader_counts_the_stairs_by_their_own_draw_then_the_other_and_never_a_third_time(self):
        counted = {}
        for who in [KIM, GLM, *READERS]:
            self.sit(who)
            self.go(who, "Sit at the board", "board")
            self.assertIn("the clock in the hall has stopped, or we stopped hearing it.", self.card(self.go(who, "Stand up from the table", "parlour")))
            reply = self.admitted(who, PARLOUR, "delvetalk %s choose / choice: Count the stairs" % PARLOUR)
            at = ["fourteen", "twelve"][0 if hashed("%d parlour.4" % turn_draw(reply)) % 20 < 10 else 1]
            self.assertIn(", you are at %s:\n" % at, self.card(reply))
            self.go(who, "Back down", "parlour")
            counted[who] = self.mine(who)["stairs"]
            self.assertEqual(counted[who], {"fourteen": "14", "twelve": "12"}[at])
            again = self.card(self.go(who, "Count them again from the top", "again"))
            self.assertIn("I count them again from the top. %s." % ("twelve" if counted[who] == "14" else "fourteen"), again)
            self.go(who, "Continue", "parlour")
            self.assertIn("I do not count a third time", self.card(self.go(who, "Count them a third time", "third")))
            self.assertNotIn("Count the stairs", self.card(self.go(who, "Continue", "parlour")))
        self.assertEqual(set(counted.values()), {"14", "12"}, counted)  # the readers' counts differ
        # The clock in the hall: ticking for the one who lifted and waited, stopped for the others.
        self.go(KIM, "Sit at the board", "board"); self.go(KIM, "Take your hands off", "lifted")
        self.assertIn("the clock in the hall is ticking again, and has been the whole time", self.card(self.go(KIM, "Wait", "parlour")))
        self.assertIn("the clock in the hall has stopped, or we stopped hearing it.", self.card(self.say(GLM, PARLOUR, "")))
        self.go(KIM, "Sit at the board", "board")  # sitting again, it stops again for them
        self.assertIn("the clock in the hall has stopped", self.card(self.go(KIM, "Stand up from the table", "parlour")))
        # Every other passage, once.
        for label, at in (("Watch the candles", "candles"), ("Continue", "parlour"), ("Listen to the window", "window"), ("Continue", "parlour"),
                          ("Sit at the board", "board"), ("Ask it something", "board"), ("Watch it circle the alphabet", "board"),
                          ("Watch it go to the numbers", "board"), ("Look at your hands", "board"), ("Move it toward GOOD BYE", "goodbye"),
                          ("Say goodbye", "goodbye"), ("Back to the board", "board"), ("Move it toward GOOD BYE", "goodbye"),
                          ("Say GOODBYE", "lifted"), ("Wait", "parlour"), ("Back to the night hall", None)):
            self.go(GLM, label, at)
        # Replayed: each reader's stairs as they counted them.
        self.town.reopen()
        self.assertEqual({who: self.mine(who)["stairs"] for who in counted}, counted)


class Refresh(test_scenarios.Arc):
    def test_a_carried_town_with_the_station_and_without_the_parlour_is_given_it_by_its_refresh_once(self):
        real = genesis.parlour
        genesis.parlour = lambda *a, **k: []
        try:
            made = genesis.gas_station(self.town.client, OPENER)
        finally:
            genesis.parlour = real
        self.assertTrue(all(m["status"] in ("created", "admitted") for m in made))
        self.assertNotIn(PARLOUR, self.objects())
        rows = genesis.refresh(self.town.client, OPENER, genesis.ancestry(self.town.journal))
        placed = [r["object"] for r in rows if r.get("reading", "").startswith("placed: kind/")]
        self.assertEqual(placed, [PARLOUR, PLANCHETTE], rows)
        self.assertTrue(all(r["status"] in ("refreshed", "current", "left") for r in rows), [r for r in rows if r["status"] not in ("refreshed", "current", "left")])
        self.town.send(op="world-deliver", principal="transport", limit=64)
        self.assertEqual(len([r for r in self.town.send(op="world-rules", principal=OPENER, object="tide")["rows"] if r["owner"] == "@" + PLANCHETTE]), 2)
        again = genesis.refresh(self.town.client, OPENER, genesis.ancestry(self.town.journal))
        self.assertEqual([r for r in again if r.get("reading", "").startswith("placed: ")], [])


if __name__ == "__main__":
    unittest.main()
