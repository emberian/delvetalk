"""Places, things and avatars: the MUD floor as ordinary objects.

Compile-level types for every method, then turns through the real host.

The host implements the `remove` list edit, so leave, take, move and acquire run
end to end.
"""
import unittest

from tests.test_chain import Chain, boolean, nil, reference
from tests.test_objects import check, closure, compile_job, computation, row_names
from tests.test_turn_world import label, nat, record

NOBODY = reference("")


def listing(items):
    wire = nil()
    for item in reversed(items):
        wire = {"tag": "variant", "label": "cons", "payload": record(head=item, tail=wire)}
    return wire


def place_seed(name, exits=(), present=(), things=()):
    return record(name=label(name), description=label("about " + name),
                  exits=listing([record(label=label(l), to=reference(t)) for l, t in exits]),
                  present=listing([reference(p) for p in present]),
                  things=listing([reference(t) for t in things]))


def thing_seed(name, holder="", location=""):
    return record(name=label(name), description=label("a " + name), holder=reference(holder), location=reference(location))


def avatar_seed(handle, at="", holding=()):
    return record(handle=label(handle), at=reference(at), holding=listing([reference(h) for h in holding]))


def names(wire):
    out = []
    while wire["label"] == "cons":
        fields = {f["name"]: f["value"] for f in wire["payload"]["fields"]}
        out.append([f["value"]["value"] for f in fields["head"]["fields"] if f["name"] == "object"][0])
        wire = fields["tail"]
    return out


class Types(unittest.TestCase):
    METHODS = {"Place": ["enter", "leave", "take", "put", "receive"], "Thing": ["acquire", "drop", "give", "receive"],
               "Avatar": ["move", "arrive", "note", "hold", "release", "receive"]}

    def test_every_method_is_an_activity_over_the_plan_library(self):
        for module, methods in self.METHODS.items():
            for method in methods:
                with self.subTest(method="%s.%s" % (module, method)):
                    reply = compile_job(closure(module), method)
                    self.assertEqual(reply["status"], "compiled", reply)
                    comp = computation(reply["artifact"]["type"])
                    self.assertEqual(row_names(comp["plan"]["row"])[:3], ["view", "write", "call"])

    def test_every_object_exports_initial(self):
        for module in self.METHODS:
            self.assertEqual(compile_job(closure(module), "initial")["status"], "compiled")


class Floor(Chain):
    test_ring_then_open_then_light = None  # inherited from Chain; not a floor test

    def world(self):
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm"]))
        self.make("garden", closure("Place"), place_seed("Garden", [("out", "porch")], things=["stone"]))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch"))
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))

    def card(self, name, principal="glm"):
        """The card is what receive offers for an empty reply."""
        reply = self.turn(name, "receive", record(text=label(""), post=label(""), slot=label("")), principal=principal)
        self.assertEqual(reply["status"], "admitted", reply)
        return reply["offers"][0]["text"]

    def version(self, name):
        return self.host.send(op="world-view", principal="ember", object=name)["version"]

    def result_label(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        return reply["result"]["label"]

    def refusal_reason(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertEqual(reply["result"]["label"], "refused", reply)
        return reply["result"]["payload"]["fields"][0]["value"]["value"]

    # --- paths that do not need remove -------------------------------------------------

    def test_the_room_card_lists_who_is_here_and_the_exits(self):
        self.world()
        text = self.card("porch")
        self.assertEqual(text, "Porch\nabout Porch\nHere: glm\nExit in to garden\n")
        self.assertEqual(self.card("garden"), "Garden\nabout Garden\nLying here: stone\nExit out to porch\n")

    def test_two_movers_in_one_place_both_appear_on_describe(self):
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm", "kimik3"]))
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: glm\nHere: kimik3\nExit in to garden\n")

    def test_enter_appends_in_order_and_a_second_entry_is_refused(self):
        self.make("porch", closure("Place"), place_seed("Porch"))
        for who in ("glm", "kimik3"):
            self.assertEqual(self.result_label(self.turn("porch", "enter", record(), principal=who)), "done")
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: glm\nHere: kimik3\n")
        before = self.version("porch")
        again = self.turn("porch", "enter", record(), principal="glm")
        self.assertEqual(self.refusal_reason(again), "Already here.")
        self.assertEqual(self.version("porch"), before)

    def test_a_thing_held_in_the_garden_is_dropped_on_the_porch_and_seen_there(self):
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm"]))
        self.make("stone", closure("Thing"), thing_seed("stone", holder="glm", location="garden"))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch", holding=["stone"]))
        dropped = self.turn("stone", "drop", record(at=reference("porch")), principal="glm")
        self.assertEqual(self.result_label(dropped), "done", dropped)
        self.assertIn("Lying here: stone\n", self.card("porch"))
        view = self.state("stone")
        self.assertEqual(names({"label": "cons", "payload": record(head=[f for f in view["fields"] if f["name"] == "holder"][0]["value"], tail=nil())}), [""])
        self.assertEqual(self.version("porch"), 1)
        self.assertEqual(self.version("stone"), 1)
        self.assertEqual(self.holding("glm"), [])

    def test_dropping_what_you_do_not_hold_or_where_you_are_not_is_refused_and_changes_nothing(self):
        self.make("porch", closure("Place"), place_seed("Porch", present=["glm"]))
        self.make("stone", closure("Thing"), thing_seed("stone", holder="kimik3", location="garden"))
        reply = self.turn("stone", "drop", record(at=reference("porch")), principal="glm")
        self.assertEqual(self.refusal_reason(reply), "You are not holding it.")
        reply = self.turn("stone", "drop", record(at=reference("porch")), principal="kimik3")
        self.assertEqual(self.refusal_reason(reply), "Only someone here can put things down.")
        self.assertEqual((self.version("porch"), self.version("stone")), (0, 0))

    def test_give_requires_the_caller_to_be_the_holder_and_notes_the_recipient(self):
        self.make("stone", closure("Thing"), thing_seed("stone", holder="glm", location="garden"))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch", holding=["stone"]))
        self.make("kimik3", closure("Avatar"), avatar_seed("kimik3", "porch"))
        refused = self.turn("stone", "give", record(to=reference("kimik3")), principal="kimik3")
        self.assertEqual(self.refusal_reason(refused), "You are not holding it.")
        self.assertEqual(self.version("stone"), 0)
        given = self.turn("stone", "give", record(to=reference("kimik3")), principal="glm")
        self.assertEqual(self.result_label(given), "done", given)
        holder = [f for f in self.state("stone")["fields"] if f["name"] == "holder"][0]["value"]
        self.assertEqual([f["value"]["value"] for f in holder["fields"] if f["name"] == "object"], ["kimik3"])
        self.assertEqual(self.holding("glm"), [])
        self.assertEqual(self.holding("kimik3"), ["stone"])
        self.assertEqual(self.inbox("kimik3"), [("glm", "gave you stone")])
        self.assertEqual(self.inbox("glm"), [])

    def holding(self, name):
        return names([f["value"] for f in self.state(name)["fields"] if f["name"] == "holding"][0])

    def inbox(self, name):
        wire = [f["value"] for f in self.state(name)["fields"] if f["name"] == "inbox"][0]
        out = []
        while wire["label"] == "cons":
            fields = {f["name"]: f["value"] for f in wire["payload"]["fields"]}
            note = {f["name"]: f["value"]["value"] for f in fields["head"]["fields"]}
            out.append((note["from"], note["text"]))
            wire = fields["tail"]
        return out

    def test_acquire_of_a_held_thing_is_refused_by_name(self):
        self.world()
        self.make("held", closure("Thing"), thing_seed("held", holder="kimik3", location="garden"))
        reply = self.turn("held", "acquire", record(), principal="glm")
        self.assertEqual(self.refusal_reason(reply), "Already held by kimik3")

    def test_a_move_through_a_nonexistent_exit_is_refused_and_changes_nothing(self):
        self.world()
        versions = {o: self.version(o) for o in ("porch", "garden", "glm", "stone")}
        reply = self.turn("glm", "move", record(exit=label("up")), principal="glm")
        self.assertEqual(self.refusal_reason(reply), "There is no exit named up")
        self.assertEqual({o: self.version(o) for o in versions}, versions)

    def test_thing_inspect_offers_its_card(self):
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))
        self.assertTrue(self.card("stone").startswith("stone\na stone\nNobody holds it.\n\nReply with a spell:\n\n    delvetalk stone acquire\n"), self.card("stone"))

    def test_a_place_with_64_things_renders_under_the_default_budget(self):
        things = ["thing%02d" % i for i in range(64)]
        self.make("hall", closure("Place"), place_seed("Hall", [("out", "porch")], present=["glm", "kimik3"], things=things))
        reply = self.turn("hall", "receive", record(text=label(""), post=label(""), slot=label("")), principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        text = reply["offers"][0]["text"]
        self.assertEqual(text.count("Lying here: "), 8)
        self.assertIn("… and 56 more\n", text)
        self.assertLess(len(text), 1400)
        print("\n  place with 64 things: describe turn %s ticks, card %d bytes" % (reply["ticksUsed"], len(text)))
        self.assertLess(reply["ticksUsed"], 100000)

    def test_an_avatar_with_a_full_inbox_describes_under_the_default_budget(self):
        """A list in state is a nested cons chain on the wire; the host decodes to
        depth 8192, so an inbox is bounded by state bytes, not by a count of 247."""
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch"))
        for i in range(247):
            note = self.turn("glm", "note", record(text=label("note %03d" % i)), principal="kimik3")
            self.assertEqual(note["status"], "admitted", note)
        over = self.turn("glm", "note", record(text=label("one too many")), principal="kimik3")
        self.assertEqual(over["status"], "admitted", over)  # the wire now decodes lists to depth 8192; the cap is bytes, not count
        reply = self.turn("glm", "receive", record(text=label(""), post=label(""), slot=label("")), principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        text = reply["offers"][0]["text"]
        self.assertEqual(text.count("kimik3: note "), 7)  # and "one too many", the newest
        self.assertLess(text.index("one too many"), text.index("kimik3: note 246"))  # newest first
        self.assertIn("… and 240 more\n", text)
        print("\n  avatar with 247 notes: describe turn %s ticks, card %d bytes" % (reply["ticksUsed"], len(text)))
        self.assertLess(reply["ticksUsed"], 100000)

    # --- paths through remove -----------------------------------------------------------

    def test_leave_removes_from_present(self):
        self.make("porch", closure("Place"), place_seed("Porch", present=["glm", "kimik3"]))
        reply = self.turn("porch", "leave", record(), principal="glm")
        self.assertEqual(self.result_label(reply), "done", reply["receipt"]["outcome"])
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: kimik3\n")

    def test_take_removes_from_things_when_the_thing_asks_for_itself(self):
        self.make("garden", closure("Place"), place_seed("Garden", present=["glm"], things=["stone", "fern"]))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "garden"))
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))
        reply = self.turn("stone", "acquire", record(), principal="glm")
        self.assertEqual(self.result_label(reply), "done", reply["receipt"]["outcome"])
        self.assertEqual(self.card("garden"), "Garden\nabout Garden\nHere: glm\nLying here: fern\n")

    def test_a_place_hears_take_and_put_only_from_the_thing_itself(self):
        self.make("garden", closure("Place"), place_seed("Garden", present=["glm"], things=["stone"]))
        for method in ("take", "put"):
            reply = self.turn("garden", method, record(), principal="glm")
            self.assertEqual(self.refusal_reason(reply), "Only a thing can %s itself%s." % (("take", "") if method == "take" else ("put", " down")))
        self.assertEqual(self.version("garden"), 0)

    def test_an_avatar_walks_porch_to_garden_and_back_carrying_a_thing(self):
        self.world()
        moved = self.turn("glm", "move", record(exit=label("in")), principal="glm")
        self.assertEqual(self.result_label(moved), "moved", moved["receipt"]["outcome"])
        self.assertIn("Here: glm\n", self.card("garden"))
        self.assertNotIn("Here: glm\n", self.card("porch"))
        got = self.turn("stone", "acquire", record(), principal="glm")
        self.assertEqual(self.result_label(got), "done", got["receipt"]["outcome"])
        self.assertNotIn("Lying here", self.card("garden"))
        self.assertEqual(self.holding("glm"), ["stone"])
        back = self.turn("glm", "move", record(exit=label("out")), principal="glm")
        self.assertEqual(self.result_label(back), "moved", back["receipt"]["outcome"])
        dropped = self.turn("stone", "drop", record(at=reference("porch")), principal="glm")
        self.assertEqual(self.result_label(dropped), "done", dropped)
        self.assertIn("Lying here: stone\n", self.card("porch"))


if __name__ == "__main__":
    unittest.main()
