"""Derived views (FOUNDATION §3, §9): pure definitions an object names in `views()`, of its state
and the reader's context, that another object asks for with `viewDerived {object, view}`.
The garden's `byKind` counts what grows in it by kind as a relation, one row a kind, asked for
through the host by another object.

Evidence for FOUNDATION §9 (layer: objects).
"""
import unittest

from tests.test_chain import Chain, town_garden
from tests.wire import label, nat, record, rows
from tests.bend import closure, declared

class DerivedViews(Chain):
    def test_garden_by_kind_counts_what_grows_in_it_for_another_object(self):
        town_garden(self.host.send)
        for colour, seed in (("violet", "a moth"), ("amber", "a wick"), ("violet", "a fern")):
            planted = self.turn("garden", "plant", record(colour=label(colour), seed=label(seed)), principal="glm")
            self.assertEqual(planted["status"], "admitted", planted)
        dug = self.turn("garden", "dig", record(name=label("")), principal="glm")
        self.assertEqual(dug["status"], "admitted", dug)
        asker = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def ask(state: State, context: Abi.Context) -> Activity<Data>:
  match world.viewDerived::<Data>({object: {world: context.world, object: "garden"}, view: "byKind"}):
    case derived(d): d.value
    case _: Plans.nothing()
""")
        r = self.host.send(op="world-create", principal="ember", identity="mk-asker", object="asker",
                           modules=closure("World") + [{"name": "Asker", "source": asker}], entry="initial", seed=record(n=nat(0)))
        self.assertEqual(r["status"], "created", r)
        asked = self.turn("asker", "ask", principal="glm")
        self.assertEqual(asked["status"], "admitted", asked)
        tallies = [{f["name"]: f["value"] for f in row["fields"]} for row in rows(asked["result"])]
        self.assertEqual([(t["kind"]["value"], t["count"]["value"]) for t in tallies], [("bell", "3"), ("cistern", "1")])


if __name__ == "__main__":
    unittest.main()
