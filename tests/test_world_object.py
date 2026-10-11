"""The world as an object (WHOLENESS §1, host day 1): a message activity's yield,
`World.Message {object: {world: "", object: "world"}, method, argument}`, is answered by the method's
name, with the arms the sum-Plan dialect answers by constructor; `write` is the running object's,
`notWorld`/`noMethod` refuse what the world does not answer, and the id `world` is reserved.

Evidence for HOST-HANDOFF 5.48 (layer: host). Refuted by a message activity that cannot write, view or
send through the world, a method outside the protocol answered, or an object created as `world`.

    python3 -W error -m unittest tests.test_world_object -v
"""
import os
import shutil
import tempfile
import unittest


from tests.test_reflection import Reflection
from tests.test_reflection import LIBRARY
from tests.wire import label, nat, record
from tests.bend import declared

# The library's World module with one method the host does not answer.
EXTRA = "  teleport({to: String}) -> Written\n"


def extended_library(scratch, extra):
    """A copy of world/lib whose World protocol declares `extra` lines as well."""
    target = os.path.join(scratch, "lib")
    shutil.copytree(LIBRARY, target)
    with open(os.path.join(target, "World.obend"), "a", encoding="utf-8") as f:
        f.write(extra)
    return target


THING = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def bump(state: State, input: {}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {count: add 1n}
  state.count + 1n
def peek(state: State, input: {other: String}, context: Abi.Context) -> Activity<Nat>:
  match world.view::<State>({object: {world: "", object: input.other}}):
    case viewed(v): v.state.count * 100n + v.version
    case denied(_): 888888n
    case _: 0n
def copy(state: State, input: {other: String}, context: Abi.Context) -> Activity<Nat>:
  let viewed(v) = world.view::<State>({object: {world: "", object: input.other}})
  let written(_) = world.write(extend(keep(), {count: Plans.Edit.set({value: v.state.count})}))
  v.state.count
def ring(state: State, input: {loud: Bool}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {count: add 10n}
  state.count + 10n
def tell(state: State, input: {other: String}, context: Abi.Context) -> Activity<String>:
  match world.send({object: {world: "", object: input.other}, method: "ring", argument: {loud: true}}):
    case delivery(_): "sent"
    case refused(r): r.clause
def later(state: State, input: {}, context: Abi.Context) -> Activity<Nat>:
  match world.await({slot: {principal: "ann", intent: "go"}, patience: 50n}):
    case reply(_):
      let written(_) = write {count: add 100n}
      1n
    case _: 0n
def field(state: State, input: {other: String, field: String}, context: Abi.Context) -> Activity<Nat>:
  match world.viewField::<Nat>({object: {world: "", object: input.other}, field: input.field}):
    case viewed(v): v.state
    case refused(r): if r.clause == "field" then 777777n else 666666n
    case _: 0n
def fieldText(state: State, input: {other: String}, context: Abi.Context) -> Activity<String>:
  match world.viewField::<String>({object: {world: "", object: input.other}, field: "count"}):
    case viewed(v): v.state
    case refused(r): r.clause
    case _: ""
def away(state: State, input: {}, context: Abi.Context) -> Activity<String>:
  match world.teleport({to: "moon"}):
    case written(_): "went"
    case refused(r): r.clause
""")


class WorldObject(Reflection):
    def setUp(self):
        super().setUp()
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.open_library(library=extended_library(scratch.name, EXTRA))

    def thing(self, name, count=0):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                           modules=[{"name": "Thing", "source": THING}],
                           entry="initial", seed=record(count=nat(count)))
        self.assertEqual(r["status"], "created", r)

    def count(self, name):
        return self.state(name)["fields"][0]["value"]


    def test_view_field_answers_one_field_at_the_readers_type(self):
        self.thing("a")
        self.thing("b", 9)
        r = self.turn("a", "field", record(other=label("b"), field=label("count")))
        self.assertEqual(r["result"], nat(9), r)
        self.assertIn({"object": "b", "field": "count", "key": "*", "version": 0}, r["receipt"]["roots"])
        self.assertEqual(self.turn("a", "field", record(other=label("b"), field=label("nope")))["result"], nat(777777))
        self.assertEqual(self.turn("a", "fieldText", record(other=label("b")))["result"], label("typeMismatch"))
        # A method the world has not is refused by name, and the id `world` is reserved.
        self.assertEqual(self.turn("a", "away", record())["result"], label("noMethod"))
        r = self.host.send(op="world-create", principal="ember", identity="mk-w", object="world",
                           modules=[{"name": "Thing", "source": THING}], entry="initial", seed=record())
        self.assertIn("not world", r["message"])

if __name__ == "__main__":
    unittest.main()
