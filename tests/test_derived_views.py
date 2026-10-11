"""Derived views (FOUNDATION §3, §9): pure definitions an object names in `views()`, of its state
and the reader's context, that another object asks for with `viewDerived {object, view}`.
Garden's `byColour` counts its bells by colour as a relation keyed {colour}, run here through
the checker and asked for through the host by another object.

Evidence for FOUNDATION §9 (layer: objects).
"""
import unittest

from tests.test_chain import Chain, garden_seed, town_kinds
from tests.test_objects import run_pure
from tests.wire import label, nat, record, rows
from tests.bend import closure, declared

GARDEN = declared("""edition ObjectiveBend 1
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
import ./Card.obend as Card
import ./Relation.obend as Relations
import ./Rows.obend as Rows
import ./Garden.obend as O
def child(n: Nat, colour: Rows.Colour) -> O.Child:
  {world: "", object: "garden/bell/{natText(n)}", colour: colour}
def counted(n: Nat) -> String:
  let children = Relations.Relation.rows({items: Lists.List.cons({head: child(1n, Rows.Colour.violet({})), tail: Lists.List.cons({head: child(2n, Rows.Colour.amber({})), tail: Lists.List.cons({head: child(3n, Rows.Colour.violet({})), tail: Lists.List.nil({})})})})})
  let state: O.State = extend(O.initial(), {children: children})
  textJoin(Lists.map(Relations.rows(O.byColour(state, Card.stranger())), fn(t: O.Tally) -> String: "{O.colourName(t.colour)} {natText(t.count)}"), ", ")
""")


class DerivedViews(Chain):
    def test_garden_by_colour_counts_its_bells_purely_and_for_another_object(self):
        self.assertEqual(run_pure("Garden", "counted", nat(0), probe=GARDEN)["value"]["value"], "amber 1, violet 2")
        self.make("garden", closure("Garden"), garden_seed())
        town_kinds(self.host.send)
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
