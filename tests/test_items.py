"""Entries by item (FOUNDATION section 13, row 1): `amendItem {item, change}` and `removeItem {item}`
address the first list item whose canonical bytes equal `item`, so two turns that each remove
something do not race on an index. The index forms stay one release.

The host landed them with lane/host4 (7196363, merged in foundation 88b9534); before it, the
turn was refused with class "evaluation" and reason "malformed write plan".

Refuted by: a removeItem that removes another item or none, an amendItem of an absent item that
commits, or the index forms stopping to work before the release ends."""
import unittest

from tests.test_chain import nil
from tests.test_replay import get, items
from tests.test_turn_world import TurnWorld, closure, label, record

ROSTER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
record State:
  names: Lists.List<String>
record Edits:
  names: Plans.Entries<String, String>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
def initial() -> State:
  {names: Lists.List::<String>.nil()}
def write(context: Abi.Context, edit: Plans.Entries<String, String>) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {names: edit}})):
    case _: 1n
def add(state: State, input: {name: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  write(context, Plans.Entries::<String, String>.append({item: input.name}))
def drop(state: State, input: {name: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  write(context, Plans.Entries::<String, String>.removeItem({item: input.name}))
def rename(state: State, input: {name: String, to: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  write(context, Plans.Entries::<String, String>.amendItem({item: input.name, change: input.to}))
def dropAt(state: State, input: {index: Nat}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  write(context, Plans.Entries::<String, String>.remove({index: input.index}))
"""


class Items(TurnWorld):
    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal="ember", identity="mk-roster", object="roster",
                           modules=closure("Plan") + [{"name": "Roster", "source": ROSTER}], entry="initial", seed=record(names=nil()))
        self.assertEqual(r["status"], "created", r)
        for name in ("glm", "kimik3", "glm", "gemini"):
            self.assertEqual(self.turn("roster", "add", record(name=label(name)))["status"], "admitted")

    def names(self):
        state = self.host.send(op="world-view", principal="ember", object="roster")["state"]
        return [n["value"] for n in items(get(state, "names"))]

    def test_the_index_forms_still_work(self):
        self.assertEqual(self.turn("roster", "dropAt", record(index={"tag": "natural", "value": "1"}))["status"], "admitted")
        self.assertEqual(self.names(), ["glm", "glm", "gemini"])

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
