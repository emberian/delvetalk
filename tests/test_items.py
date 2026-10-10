"""List items are amended and removed by their canonical bytes, so two removals never race on an
index, and every object writes that way.

Evidence for FOUNDATION §3 Edits (layer: host).

Entries by item: `amendItem {item, change}` and `removeItem {item}`
address the first list item whose canonical bytes equal `item`, so two turns that each remove
something do not race on an index. The index forms stay one release.

The host landed them with lane/host4 (7196363, merged in foundation 88b9534); before it, the
turn was refused with class "evaluation" and reason "malformed write plan".

Refuted by: a removeItem that removes another item or none, an amendItem of an absent item that
commits, or the index forms stopping to work before the release ends.
"""
import unittest

from tests.test_chain import nil
from tests.test_replay import get, items, relation, rows
from tests.test_turn_world import TurnWorld, closure, label, record
from tests.test_turn_world import declared

ROSTER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  names: Lists.List<String>
def initial() -> State:
  {names: Lists.List::<String>.nil()}
def write(context: Abi.Context, edit: Plans.Entries<String, String>) -> Activity<Nat>:
  match world.write(extend(keep(), {names: edit})):
    case _: 1n
def add(state: State, input: {name: String}, context: Abi.Context) -> Activity<Nat>:
  write(context, Plans.Entries::<String, String>.append({item: input.name}))
def drop(state: State, input: {name: String}, context: Abi.Context) -> Activity<Nat>:
  write(context, Plans.Entries::<String, String>.removeItem({item: input.name}))
def rename(state: State, input: {name: String, to: String}, context: Abi.Context) -> Activity<Nat>:
  write(context, Plans.Entries::<String, String>.amendItem({item: input.name, change: input.to}))
""")


class Items(TurnWorld):
    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal="ember", identity="mk-roster", object="roster",
                           modules=closure("World") + [{"name": "Roster", "source": ROSTER}], entry="initial", seed=record(names=nil()))
        self.assertEqual(r["status"], "created", r)
        for name in ("glm", "kimik3", "glm", "gemini"):
            self.assertEqual(self.turn("roster", "add", record(name=label(name)))["status"], "admitted")

    def names(self):
        state = self.host.send(op="world-view", principal="ember", object="roster")["state"]
        return [n["value"] for n in items(get(state, "names"))]

    def test_remove_item_removes_the_first_equal_item_only(self):
        r = self.turn("roster", "drop", record(name=label("glm")))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.names(), ["kimik3", "glm", "gemini"])

    def test_amend_item_replaces_the_first_equal_item(self):
        r = self.turn("roster", "rename", record(name=label("gemini"), to=label("gemini-2")))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.names(), ["glm", "kimik3", "glm", "gemini-2"])

    def test_an_absent_item_is_refused_by_name_and_changes_nothing(self):
        r = self.turn("roster", "drop", record(name=label("nobody")))
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "absentItem"), r)
        self.assertEqual(self.names(), ["glm", "kimik3", "glm", "gemini"])


if __name__ == "__main__":
    unittest.main()


class ObjectsWriteByItem(TurnWorld):
    """Every object that amends or removes a list item now addresses it by bytes: the receipt
    carries removeItem/amendItem with the item, never an index. Refuted by an index form in any
    receipt below, or by the wrong item going."""

    def labels(self, reply):
        import json
        text = json.dumps(reply["receipt"]["outcome"]["writes"])
        return {l for l in ("removeItem", "amendItem", "insert", "upsert", "retract") if '"label": "%s"' % l in text}

    def test_a_place_retracts_who_leaves_by_key(self):
        from tests.test_chain import Chain
        from tests.test_places import place_seed
        Chain.make(self, "porch", closure("Place"), place_seed("Porch", present=["glm", "kimik3", "gemini"]))
        r = self.turn("porch", "leave", principal="kimik3")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.labels(r), {"retract", "insert"})   # who left, and the trace
        state = self.host.send(op="world-view", principal="ember", object="porch")["state"]
        self.assertEqual([get(p, "object")["value"] for p in rows(get(state, "present"))], ["glm", "gemini"])

    def test_a_tide_resubscription_upserts_the_subscribers_own_row(self):
        from tests.test_chain import nil as empty
        from tests.test_turn_world import nat
        r = self.host.send(op="world-create", principal="ember", identity="mk-tide", object="tide", modules=closure("Tide"),
                           entry="initial", seed=record(ticks=nat(0), last=nat(0), gap=nat(1), subs=relation()))
        self.assertEqual(r["status"], "created", r)
        for who in ("glm", "kimik3"):
            self.turn("tide", "subscribe", record(every=nat(2), note=label("hi " + who)), principal=who)
        again = self.turn("tide", "subscribe", record(every=nat(3), note=label("again")), principal="glm")
        self.assertEqual(self.labels(again), {"upsert"})
        subs = rows(get(self.host.send(op="world-view", principal="ember", object="tide")["state"], "subs"))
        self.assertEqual([(get(s, "who")["value"], get(s, "note")["value"]) for s in subs], [("glm", "again"), ("kimik3", "hi kimik3")])
