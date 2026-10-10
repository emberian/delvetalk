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
from tests.test_turn_world import label, nat, record, declared
from tests.test_reflection import LIBRARY

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
record Edits:
  count: Plans.Edit<Nat, Nat>
def initial() -> State:
  {count: 0n}
def keep() -> Edits:
  {count: Plans.Edit.keep({})}
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

    def test_write_view_and_send_are_world_calls(self):
        self.thing("a")
        self.thing("b", 7)
        bumped = self.turn("a", "bump", record())
        self.assertEqual((bumped["status"], bumped["result"]), ("admitted", nat(1)), bumped)
        peek = self.turn("a", "peek", record(other=label("b")))
        self.assertEqual(peek["result"], nat(700), peek)
        self.assertIn({"object": "b", "version": 0}, peek["receipt"]["roots"])
        copied = self.turn("a", "copy", record(other=label("b")))
        self.assertEqual(copied["result"], nat(7), copied)
        self.assertEqual(self.count("a"), nat(7))
        told = self.turn("a", "tell", record(other=label("b")))
        self.assertEqual(told["result"], label("sent"), told)
        self.assertEqual(self.count("b"), nat(17))
        self.reopen()
        self.assertEqual((self.count("a"), self.count("b")), (nat(7), nat(17)))

    def test_a_message_activity_suspends_on_await_and_resumes(self):
        self.thing("a")
        self.thing("b")
        waiting = self.turn("a", "later", record())
        self.assertEqual(waiting["status"], "suspended", waiting)
        go = self.turn("b", "bump", record(), identity="go", principal="ann")
        [resumed] = go["resumed"]
        self.assertEqual((resumed["status"], resumed["result"]), ("admitted", nat(1)), resumed)
        self.assertEqual(self.count("a"), nat(100))
        self.reopen()
        self.assertEqual(self.count("a"), nat(100))

    def test_view_field_answers_one_field_at_the_readers_type(self):
        self.thing("a")
        self.thing("b", 9)
        r = self.turn("a", "field", record(other=label("b"), field=label("count")))
        self.assertEqual(r["result"], nat(9), r)
        self.assertIn({"object": "b", "field": "count", "key": "*", "version": 0}, r["receipt"]["roots"])
        self.assertEqual(self.turn("a", "field", record(other=label("b"), field=label("nope")))["result"], nat(777777))
        self.assertEqual(self.turn("a", "fieldText", record(other=label("b")))["result"], label("typeMismatch"))

    def test_a_method_the_world_has_not_is_refused_by_name(self):
        self.thing("a")
        r = self.turn("a", "away", record())
        self.assertEqual(r["result"], label("noMethod"), r)

    def test_the_id_world_is_reserved(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-w", object="world",
                           modules=[{"name": "Thing", "source": THING}],
                           entry="initial", seed=record())
        self.assertEqual(r["status"], "error", r)
        self.assertIn("not world", r["message"])


if __name__ == "__main__":
    unittest.main()
