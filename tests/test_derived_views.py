"""Derived views (FOUNDATION §16): pure definitions an object names in `views()`, of its state
and the reader's context, that another object asks for with `viewDerived {object, view}`.
Garden's `byColour` counts its bells by colour as a relation keyed {colour}; Place's
`affordances` is what can be done there, as spells. The pure definitions run here through
the checker; asking for one through the host waits for the host's `viewDerived`
(HOST-HANDOFF §7 item 6), so that case is an expected failure until it lands.
"""
import unittest

from tests.test_chain import Chain, garden_seed
from tests.test_objects import closure, run_pure
from tests.test_replay import rows
from tests.test_turn_world import label, nat, record
from tests.test_turn_world import declared

GARDEN = declared("""edition ObjectiveBend 1
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
import ./Card.obend as Card
import ./Relation.obend as Relations
import ./Bell.obend as Bell
import ./Garden.obend as O
def child(n: Nat, colour: Bell.Colour) -> O.Child:
  {world: "", object: "garden/bell/{natText(n)}", colour: colour}
def counted(n: Nat) -> String:
  let children = Relations.Relation.rows({items: Lists.List.cons({head: child(1n, Bell.Colour.violet({})), tail: Lists.List.cons({head: child(2n, Bell.Colour.amber({})), tail: Lists.List.cons({head: child(3n, Bell.Colour.violet({})), tail: Lists.List.nil({})})})})})
  let state: O.State = extend(O.initial(), {children: children})
  textJoin(Lists.map(Relations.rows(O.byColour(state, Card.stranger())), fn(t: O.Tally) -> String: "{Bell.colourName(t.colour)} {natText(t.count)}"), ", ")
""")

PLACE = declared("""edition ObjectiveBend 1
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
import ./Card.obend as Card
import ./Document.obend as Document
import ./Relation.obend as Relations
import ./Place.obend as O
def shown(n: Nat) -> String:
  let state: O.State = extend(O.initial(), {things: Relations.Relation.rows({items: Lists.List.cons({head: {world: "", object: "porch/stone"}, tail: Lists.List.nil({})})}), exits: Lists.List.cons({head: {label: "in", to: {world: "", object: "garden"}}, tail: Lists.List.nil({})})})
  Document.plain(O.affordances(state, extend(Card.stranger(), {object: "porch", principal: "did:plc:glm"})))
""")


class DerivedViews(Chain):
    def test_garden_by_colour_counts_its_bells_one_row_a_colour(self):
        out = run_pure("Garden", "counted", nat(0), probe=GARDEN)
        self.assertEqual(out["value"]["value"], "amber 1, violet 2")

    def test_place_affordances_are_its_forms_the_things_to_take_and_the_exits(self):
        text = run_pure("Place", "shown", nat(0), probe=PLACE)["value"]["value"]
        self.assertEqual(text, (
            "\nReply with a spell:\n"
            "\n    delvetalk porch say\n    line: <text, 1 to 280 characters>\n"
            "\n    delvetalk porch emote\n    line: <text, 1 to 280 characters>\n"
            "\n    delvetalk porch whisper\n    to: <text, 1 to 160 characters>\n    line: <text, 1 to 280 characters>\n"
            "\n    delvetalk porch/stone acquire\n"
            "\n    delvetalk did:plc:glm move\n    exit: in\n"))

    def test_another_object_asks_the_garden_for_by_colour(self):
        self.make("garden", closure("Garden"), garden_seed())
        planted = self.turn("garden", "plant", record(colour=label("violet"), seed=label("a moth")), principal="glm")
        self.assertEqual(planted["status"], "admitted", planted)
        asker = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def ask(state: State, context: Abi.Context) -> Activity<Data>:
  match world.viewDerived::<Data>({object: {world: context.world, object: "garden"}, view: "byColour"}):
    case derived(d): d.value
    case _: Plans.nothing()
""")
        r = self.host.send(op="world-create", principal="ember", identity="mk-asker", object="asker",
                           modules=closure("World") + [{"name": "Asker", "source": asker}], entry="initial", seed=record(n=nat(0)))
        self.assertEqual(r["status"], "created", r)
        asked = self.turn("asker", "ask", principal="glm")
        self.assertEqual(asked["status"], "admitted", asked)
        tallies = [{f["name"]: f["value"] for f in row["fields"]} for row in rows(asked["result"])]
        self.assertEqual([(t["colour"]["label"], t["count"]["value"]) for t in tallies], [("violet", "1")])


if __name__ == "__main__":
    unittest.main()
