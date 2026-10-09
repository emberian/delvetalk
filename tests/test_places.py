"""Places, things and movers: the MUD floor as ordinary objects.

Compile-level types for every method, then turns through the real host.

The host does not implement the `remove` list edit yet. The turn that carries it
is refused as

    {'class': 'evaluation', 'reason': 'malformed write plan'}

so every path through Place.leave and Place.take (and so Mover.move and
Thing.acquire) is an expected failure; they flip when the host lands remove.
"""
import unittest

from tests.test_chain import Chain, boolean, nil, reference
from tests.test_objects import check, closure, compile_job, computation, row_names
from tests.test_turn_world import label, nat, record

REMOVE_REFUSAL = "malformed write plan"
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


def mover_seed(name, at):
    return record(name=label(name), at=reference(at), holding=nil())


def names(wire):
    out = []
    while wire["label"] == "cons":
        fields = {f["name"]: f["value"] for f in wire["payload"]["fields"]}
        out.append([f["value"]["value"] for f in fields["head"]["fields"] if f["name"] == "object"][0])
        wire = fields["tail"]
    return out


class Types(unittest.TestCase):
    METHODS = {"Place": ["enter", "leave", "take", "put", "describe"], "Thing": ["acquire", "drop", "give", "inspect"],
               "Mover": ["move"]}

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
    def world(self):
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm"]))
        self.make("garden", closure("Place"), place_seed("Garden", [("out", "porch")], things=["stone"]))
        self.make("glm", closure("Mover"), mover_seed("glm", "porch"))
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))

    def by(self, name="glm", **fields):
        return record(by=reference(name), **fields)

    def card(self, name, principal="glm"):
        reply = self.turn(name, "describe", principal=principal)
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
            self.assertEqual(self.result_label(self.turn("porch", "enter", record(who=reference(who)), principal=who)), "done")
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: glm\nHere: kimik3\n")
        before = self.version("porch")
        again = self.turn("porch", "enter", record(who=reference("glm")), principal="glm")
        self.assertEqual(self.refusal_reason(again), "Already here.")
        self.assertEqual(self.version("porch"), before)

    def test_a_thing_held_in_the_garden_is_dropped_on_the_porch_and_seen_there(self):
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm"]))
        self.make("stone", closure("Thing"), thing_seed("stone", holder="glm", location="garden"))
        dropped = self.turn("stone", "drop", record(by=reference("glm"), at=reference("porch")), principal="glm")
        self.assertEqual(self.result_label(dropped), "done", dropped)
        self.assertIn("Lying here: stone\n", self.card("porch"))
        view = self.state("stone")
        self.assertEqual(names({"label": "cons", "payload": record(head=[f for f in view["fields"] if f["name"] == "holder"][0]["value"], tail=nil())}), [""])
        self.assertEqual(self.version("porch"), 1)
        self.assertEqual(self.version("stone"), 1)

    def test_dropping_what_you_do_not_hold_or_where_you_are_not_is_refused_and_changes_nothing(self):
        self.make("porch", closure("Place"), place_seed("Porch", present=["glm"]))
        self.make("stone", closure("Thing"), thing_seed("stone", holder="kimik3", location="garden"))
        reply = self.turn("stone", "drop", record(by=reference("glm"), at=reference("porch")), principal="glm")
        self.assertEqual(self.refusal_reason(reply), "You are not holding it.")
        reply = self.turn("stone", "drop", record(by=reference("kimik3"), at=reference("porch")), principal="kimik3")
        self.assertEqual(self.refusal_reason(reply), "Only someone here can put things down.")
        self.assertEqual((self.version("porch"), self.version("stone")), (0, 0))

    def test_give_requires_the_caller_to_be_the_holder(self):
        self.make("stone", closure("Thing"), thing_seed("stone", holder="glm", location="garden"))
        refused = self.turn("stone", "give", record(to=reference("kimik3")), principal="kimik3")
        self.assertEqual(self.refusal_reason(refused), "You are not holding it.")
        self.assertEqual(self.version("stone"), 0)
        given = self.turn("stone", "give", record(to=reference("kimik3")), principal="glm")
        self.assertEqual(self.result_label(given), "done")
        holder = [f for f in self.state("stone")["fields"] if f["name"] == "holder"][0]["value"]
        self.assertEqual([f["value"]["value"] for f in holder["fields"] if f["name"] == "object"], ["kimik3"])

    def test_acquire_of_a_held_thing_is_refused_by_name(self):
        self.world()
        self.make("held", closure("Thing"), thing_seed("held", holder="kimik3", location="garden"))
        reply = self.turn("held", "acquire", self.by(), principal="glm")
        self.assertEqual(self.refusal_reason(reply), "Already held by kimik3")

    def test_a_move_through_a_nonexistent_exit_is_refused_and_changes_nothing(self):
        self.world()
        versions = {o: self.version(o) for o in ("porch", "garden", "glm", "stone")}
        reply = self.turn("glm", "move", record(exit=label("up")), principal="glm")
        self.assertEqual(self.refusal_reason(reply), "There is no exit named up")
        self.assertEqual({o: self.version(o) for o in versions}, versions)

    def test_thing_inspect_offers_its_card(self):
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))
        reply = self.turn("stone", "inspect", principal="glm")
        self.assertEqual(reply["offers"][0]["text"], "stone\na stone\nNobody holds it.\n")

    def test_a_place_with_64_things_renders_under_the_default_budget(self):
        things = ["thing%02d" % i for i in range(64)]
        # A 64-deep cons list is over the wire's nesting capacity ('response nesting
        # capacity' on world-create), so the hall is stocked one put at a time.
        self.make("hall", closure("Place"), place_seed("Hall", [("out", "porch")], present=["glm", "kimik3"]))
        for thing in things:
            put = self.turn("hall", "put", record(thing=reference(thing), by=reference("glm")), principal="glm")
            self.assertEqual(self.result_label(put), "done", put)
        reply = self.turn("hall", "describe", principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        text = reply["offers"][0]["text"]
        self.assertEqual(text.count("Lying here: "), 64)
        print("\n  place with 64 things: describe turn %s ticks, card %d bytes" % (reply["ticksUsed"], len(text)))
        self.assertLess(reply["ticksUsed"], 100000)

    # --- paths that need remove: expected failures until the host lands it ------------

    def test_leave_removes_from_present(self):
        self.make("porch", closure("Place"), place_seed("Porch", present=["glm", "kimik3"]))
        reply = self.turn("porch", "leave", record(who=reference("glm")), principal="glm")
        self.assertEqual(self.result_label(reply), "done", reply["receipt"]["outcome"])
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: kimik3\n")

    def test_take_removes_from_things(self):
        self.make("garden", closure("Place"), place_seed("Garden", present=["glm"], things=["stone", "fern"]))
        reply = self.turn("garden", "take", record(thing=reference("stone"), by=reference("glm")), principal="glm")
        self.assertEqual(self.result_label(reply), "done", reply["receipt"]["outcome"])
        self.assertEqual(self.card("garden"), "Garden\nabout Garden\nHere: glm\nLying here: fern\n")

    def test_a_mover_walks_porch_to_garden_and_back_carrying_a_thing(self):
        self.world()
        moved = self.turn("glm", "move", record(exit=label("in")), principal="glm")
        self.assertEqual(self.result_label(moved), "moved", moved["receipt"]["outcome"])
        self.assertIn("Here: glm\n", self.card("garden"))
        self.assertNotIn("Here: glm\n", self.card("porch"))
        got = self.turn("stone", "acquire", self.by(), principal="glm")
        self.assertEqual(self.result_label(got), "done", got["receipt"]["outcome"])
        self.assertNotIn("Lying here", self.card("garden"))
        back = self.turn("glm", "move", record(exit=label("out")), principal="glm")
        self.assertEqual(self.result_label(back), "moved", back["receipt"]["outcome"])
        dropped = self.turn("stone", "drop", record(by=reference("glm"), at=reference("porch")), principal="glm")
        self.assertEqual(self.result_label(dropped), "done", dropped)
        self.assertIn("Lying here: stone\n", self.card("porch"))


if __name__ == "__main__":
    unittest.main()
