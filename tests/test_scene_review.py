"""Destination guards survive stitching; every parsed label can name one choice."""
import unittest

from tests import test_chain
from tests.bend import closure
from tests.test_objects import run_pure
from tests.test_rooms import body, make_room
from tests.test_scene import heard, plain
from tests.wire import cast_refusal, label, nat, record


PARSE_PROBE = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./Scenes.obend as Scenes
import ./Spween.obend as Spween
def choiceText(c: Scenes.Choice) -> String:
  "  * {c.label} -> {c.to}"
def passageText(p: Scenes.Passage) -> String:
  textJoin(Lists.map(p.choices, choiceText), "\\n")
def described(read: Spween.Parsed) -> String:
  match read:
    case refused(r): "refused: {r.reason}"
    case parsed(p): textJoin(Lists.map(p.seed.passages, passageText), "\\n")
def summary(text: String) -> String:
  described(Spween.parse(text))
def wing(text: String) -> String:
  described(Spween.wing(text))
"""


def summary(text, entry="summary"):
    out = run_pure("Spween", entry, label(text), probe=PARSE_PROBE, limits={"ticks": "1000000"})
    assert out["status"] == "finished", out
    return out["value"]["value"]


class Labels(unittest.TestCase):
    def test_empty_and_65_character_labels_are_refused_in_scenes_and_wings(self):
        for entry in ("summary", "wing"):
            for text in ("", "   ", "A" * 65, "杯" * 65):
                with self.subTest(entry=entry, label=text):
                    parsed = summary("=== a\n* [%s] -> END\n" % text, entry)
                    self.assertEqual(parsed, "refused: a choice's label holds 1 to 64 characters")

    def test_one_and_64_character_labels_parse_in_scenes_and_wings(self):
        for entry in ("summary", "wing"):
            for text in ("A", "A" * 64, "杯" * 64):
                with self.subTest(entry=entry, label=text):
                    parsed = summary("=== a\n* [%s] -> END\n" % text, entry)
                    self.assertIn("  * %s -> END" % text, parsed)

    def test_duplicate_labels_and_explicit_continue_collisions_are_refused(self):
        for entry in ("summary", "wing"):
            for choices, duplicate in (("* [Go] -> a\n* [ Go ] -> END\n", "Go"),
                                       ("* [Continue] -> a\n-> END\n", "Continue"),
                                       ("-> a\n* [Continue] -> END\n", "Continue"),
                                       ("-> a\n-> END\n", "Continue")):
                with self.subTest(entry=entry, choices=choices):
                    parsed = summary("=== a\n" + choices, entry)
                    self.assertEqual(parsed, "refused: === a offers %s twice; each choice needs its own label" % duplicate)

    def test_the_same_label_in_different_passages_and_distinct_case_are_selectable(self):
        parsed = summary("=== a\n* [Go] -> b\n* [go] -> END\n=== b\n* [Go] -> END\n")
        self.assertEqual(parsed.count("  * Go ->"), 2)
        self.assertIn("  * go -> END", parsed)


class Stitched(test_chain.Chain):
    def setUp(self):
        super().setUp()
        make_room(self, "scene")
        version = self.host.send(op="world-view", principal="ember", object="scene")["version"]
        laid = self.host.send(op="world-reprogram", principal="ember", identity="station-body", object="scene",
                              version=version, package=body("station"), mode="extend")
        self.assertEqual(laid["status"], "admitted", laid)

    def stitch(self, text):
        reply = self.turn("scene", "stitch", record(spween=label(text)))
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def view(self):
        view = self.host.send(op="world-view", principal="ember", object="scene")
        self.assertEqual(view["status"], "viewed", view)
        return view["version"], plain(view["state"])

    def choose(self, text, who="visitor"):
        return self.turn("scene", "choose", record(choice=label(text)), principal=who)

    def test_a_later_wings_destination_guard_refuses_before_effects_or_casts(self):
        self.stitch("=== a\n* [Go] -> b\n  ~ unlocked = 1\n  ~ cast delvetalk missing ring\n"
                    "* [Unlock] -> a\n  ~ unlocked = 1\n")
        entered = self.turn("scene", "enter", principal="visitor")
        self.assertEqual(entered["result"]["label"], "entered", entered)
        before = self.view()
        self.assertEqual(cast_refusal(self.choose("Go")), ("noPassage", "b is not in this room"))
        self.assertEqual(self.view(), before)
        self.stitch("=== b { unlocked >= 1 }\nB.\n")
        before = self.view()
        refused = self.choose("Go")
        self.assertEqual(cast_refusal(refused), ("guarded", "Go needs unlocked >= 1."))
        self.assertEqual(self.view(), before)
        self.assertEqual(refused["receipt"]["outcome"].get("fired", []), [])
        self.assertEqual(self.choose("Unlock")["status"], "admitted")
        moved = self.choose("Go")
        self.assertEqual((moved["status"], moved["result"]["label"]), ("admitted", "moved"), moved)
        self.assertEqual(next(p for p in self.view()[1]["presence"] if p["who"] == "visitor")["at"], "b")

    def test_a_later_wings_law_guard_is_judged_for_the_reader_and_filters_cards(self):
        self.stitch("=== a\n* [Go] -> b\n")
        self.stitch('=== b { request.subject == new.owner }\nB.\n')
        entered = self.turn("scene", "enter", principal="visitor")
        self.assertEqual(entered["status"], "admitted", entered)
        self.assertNotIn("  * Go", entered["offers"][0]["text"])
        before = self.view()
        self.assertEqual(cast_refusal(self.choose("Go")), ("guarded", "Go needs request.subject == new.owner."))
        self.assertEqual(self.view(), before)
        entered = self.turn("scene", "enter", principal="ember")
        self.assertIn("  * Go\n", entered["offers"][0]["text"])
        self.assertEqual(self.choose("Go", "ember")["result"]["label"], "moved")

    def test_a_later_wings_reader_guard_uses_each_readers_own_variables(self):
        self.stitch("=== a\n* [Go] -> b\n  ~ my.key = 1\n* [Unlock] -> a\n  ~ my.key = 1\n")
        self.stitch("=== b { my.key >= 1 }\nB.\n")
        for who in ("visitor", "other"):
            self.assertEqual(self.turn("scene", "enter", principal=who)["status"], "admitted")
        before = self.view()
        self.assertEqual(cast_refusal(self.choose("Go")), ("guarded", "Go needs my.key >= 1."))
        self.assertEqual(self.view(), before)
        self.assertEqual(self.choose("Unlock")["status"], "admitted")
        before = self.view()
        self.assertEqual(cast_refusal(self.choose("Go", "other")), ("guarded", "Go needs my.key >= 1."))
        self.assertEqual(self.view(), before)
        self.assertEqual(self.choose("Go")["result"]["label"], "moved")

    def test_one_and_64_character_labels_can_be_chosen_through_the_room_form(self):
        longest = "杯" * 64
        self.stitch("=== a\n* [%s] -> b\n=== b\n* [X] -> END\n" % longest)
        self.assertEqual(self.turn("scene", "enter", principal="visitor")["status"], "admitted")
        for text, result in ((longest, "moved"), ("X", "left")):
            reply = self.turn("scene", "receive", heard("delvetalk scene choose / choice: " + text), principal="visitor")
            self.assertEqual((reply["status"], reply["result"]["label"]), ("admitted", result), reply)

    def test_a_later_wings_holding_guard_reads_the_destination_for_each_reader(self):
        self.make("key", closure("Thing"), record(owner=label("ember"), keeper=label("visitor")))
        self.stitch("=== a\n* [Go] -> b\n")
        self.stitch("=== b { keeps.key }\nB.\n")
        for who in ("visitor", "other"):
            self.assertEqual(self.turn("scene", "enter", principal=who)["status"], "admitted")
        before = self.view()
        self.assertEqual(cast_refusal(self.choose("Go", "other")), ("guarded", "Go needs keeps.key."))
        self.assertEqual(self.view(), before)
        self.assertEqual(self.choose("Go")["result"]["label"], "moved")

    def test_an_unreferenced_passages_invalid_law_guard_refuses_stitching(self):
        self.stitch("=== a\nA.\n")
        before = self.view()
        reply = self.turn("scene", "stitch", record(spween=label("=== c\nC.\n=== b { count(new.presence) >> 1 }\nB.\n")))
        clause, reading = cast_refusal(reply)
        self.assertEqual(clause, "spween")
        self.assertTrue(reading.startswith("The guard `count(new.presence) >> 1` does not read: law outside the enforced fragment"), reading)
        self.assertEqual(self.view(), before)

    def test_the_start_passage_guard_is_checked_on_entry_and_on_return(self):
        self.stitch("=== a { !my.left }\n* [Out] -> b\n  ~ my.left = true\n"
                    "=== b\n* [Back] -> a\n  ~ my.left = false\n")
        self.assertEqual(self.turn("scene", "enter", principal="visitor")["status"], "admitted")
        self.assertEqual(self.choose("Out")["status"], "admitted")
        before = self.view()
        self.assertEqual(cast_refusal(self.choose("Back")), ("guarded", "Back needs !my.left."))
        self.assertEqual(self.view(), before)
        self.assertEqual(self.turn("scene", "leave", principal="visitor")["status"], "admitted")
        before = self.view()
        self.assertEqual(cast_refusal(self.turn("scene", "enter", principal="visitor")),
                         ("unmet", "The room requires !my.left."))
        self.assertEqual(self.view(), before)
        self.assertEqual(self.turn("scene", "enter", principal="other")["status"], "admitted")

    def test_a_draw_checks_only_its_selected_destination_and_end_has_no_guard(self):
        self.stitch("=== a\n* [Open draw]\n  -> b weight: 1\n  -> c weight: 0\n"
                    "* [Locked draw]\n  -> b weight: 0\n  -> c weight: 1\n  ~ unlocked = 1\n"
                    "* [End draw]\n  -> c weight: 0\n  -> END weight: 1\n"
                    "* [Law draw]\n  -> b weight: 0\n  -> d weight: 1\n  ~ unlocked = 1\n"
                    "=== b\n* [Back] -> a\n=== c { unlocked >= 1 }\nC.\n"
                    "=== d { request.subject == new.owner }\nD.\n")
        self.assertEqual(self.turn("scene", "enter", principal="visitor")["status"], "admitted")
        before = self.view()
        self.assertEqual(cast_refusal(self.choose("Locked draw")), ("guarded", "Locked draw needs unlocked >= 1."))
        self.assertEqual(self.view(), before)
        self.assertEqual(cast_refusal(self.choose("Law draw")), ("guarded", "Law draw needs request.subject == new.owner."))
        self.assertEqual(self.view(), before)
        self.assertEqual(self.choose("Open draw")["result"]["label"], "moved")
        self.assertEqual(next(p for p in self.view()[1]["presence"] if p["who"] == "visitor")["at"], "b")
        self.assertEqual(self.choose("Back")["status"], "admitted")
        self.assertEqual(self.choose("End draw")["result"]["label"], "left")
        self.assertEqual(self.turn("scene", "enter", principal="ember")["status"], "admitted")
        self.assertEqual(self.choose("Law draw", "ember")["result"]["label"], "moved")
        self.assertEqual(next(p for p in self.view()[1]["presence"] if p["who"] == "ember")["at"], "d")

    def test_stitch_and_restitch_keep_identical_casts_named_within_each_wing(self):
        first = "=== a\n* [Ring here] -> a\n  ~ cast delvetalk missing ring\n* [Go] -> b\n"
        second = "=== b { request.subject == new.owner }\n* [Wait] -> b\n"
        second += "* [Ring there] -> b\n  ~ cast delvetalk missing ring\n"
        third = "=== c\n* [Ring again] -> c\n  ~ cast delvetalk missing ring\n"
        self.stitch(first)
        self.stitch(second)

        def names():
            reply = self.host.send(op="world-rules", principal="ember", object="scene")
            return {r["name"] for r in reply["rows"]}

        self.assertEqual(names(), {"a_1", "b_2"})
        self.assertEqual(self.turn("scene", "enter", principal="ember")["status"], "admitted")
        self.assertEqual(self.choose("Go", "ember")["status"], "admitted")
        rang = self.choose("Ring there", "ember")
        receipt = self.host.send(op="world-entry", principal="ember", hash=rang["receipt"]["hash"])["receipt"]
        self.assertEqual([r["rule"] for r in receipt.get("fired", [])], ["b_2"])
        for i, wing in enumerate((first, second), 1):
            reply = self.turn("scene", "restitch", record(spween=label(wing), part=nat(i), wings=nat(2)))
            self.assertEqual(reply["status"], "admitted", reply)
            self.assertEqual(names(), {"a_1"} if i == 1 else {"a_1", "b_2"})
        self.stitch(third)
        self.assertEqual(names(), {"a_1", "b_2", "c_1"})


if __name__ == "__main__":
    unittest.main()
