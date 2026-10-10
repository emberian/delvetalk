"""world/lib/World.obend, the world's protocol (docs/WHOLENESS.md section 1), through the real
checker: an object in the message dialect compiles against it, every protocol method it uses
lowers to one message to the world, and the artifact names them. Running such an object
through the host waits for the host's message dispatch (WHOLENESS §4, host day 2).
"""
import unittest

from tests.test_objects import closure, compile_job
from tests.test_turn_world import TurnWorld, label, nat, record

USER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./Document.obend as Document
import ./World.obend as World
import ./List.obend as Lists
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
def keep() -> Edits:
  {count: Plans.Edit.keep({})}
def initial() -> State:
  {count: 0n}
def bump(state: State, input: {}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {count: add 1n}
  state.count + 1n
def peek(state: State, input: {other: Plans.Reference}, context: Abi.Context) -> Activity<Nat>:
  match world.view::<State>({object: input.other}):
    case viewed(v): v.state.count
    case _: 0n
def asked(state: State, input: {other: Plans.Reference}, context: Abi.Context) -> Activity<String>:
  match world.call::<String>({object: input.other, method: "name", argument: Plans.nothing()}):
    case returned(r): r.result
    case _: ""
def follow(state: State, input: {other: Plans.Reference}, context: Abi.Context) -> Activity<String>:
  match world.subscribe({object: input.other, field: "count", method: "changed"}):
    case subscribed(_): "subscribed"
    case denied(_): "denied"
    case refused(r): r.clause
def past(state: State, input: {other: Plans.Reference, version: Nat}, context: Abi.Context) -> Activity<Nat>:
  match world.viewAt::<State>({object: input.other, version: input.version}):
    case viewed(v): v.state.count
    case _: 0n
def counted(state: State, input: {other: Plans.Reference}, context: Abi.Context) -> Activity<Nat>:
  match world.viewDerived::<Nat>({object: input.other, view: "doubled"}):
    case derived(d): d.value
    case _: 0n
def changed(state: State, input: {object: Plans.Reference, field: String, version: Nat, inserted: Lists.List<Nat>, retracted: Lists.List<Nat>}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {count: Plans.Edit.set({value: Lists.length(input.inserted) + state.count})}))
  state.count
def views() -> Lists.List<String>:
  Lists.List.cons({head: "doubled", tail: Lists.List.nil({})})
def doubled(state: State, context: Abi.Context) -> Nat:
  state.count * 2n
def shown(state: State, input: {}, context: Abi.Context) -> Activity<Nat>:
  let offered(_) = world.offer({to: "", document: Document.text("hello\\n")})
  match world.inspect({object: Plans.self(context)}):
    case inspected(i): textLength(i.pin)
    case _: 0n
"""


class WorldProtocol(unittest.TestCase):
    def compiled(self, entry):
        modules, seen = [], set()
        for name in ("World", "Abi"):
            closure(name, seen, modules)
        out = compile_job(modules + [{"name": "User", "source": USER}], entry)
        self.assertEqual(out["status"], "compiled", out)
        return out["artifact"]

    def test_an_object_in_the_message_dialect_compiles_against_the_world_protocol(self):
        for entry, methods in [("bump", ["write"]), ("peek", ["view"]), ("asked", ["call"]), ("shown", ["offer", "inspect"]),
                               ("follow", ["subscribe"]), ("past", ["viewAt"]), ("counted", ["viewDerived"])]:
            artifact = self.compiled(entry)
            self.assertEqual(artifact.get("dialect"), "message", entry)
            self.assertEqual(artifact.get("world"), methods, entry)



class WorldTurns(TurnWorld):
    """The same object through the host's world dispatch (host8): writes, a subscription, a
    `changed` delivery, a past version and a derived view."""

    def test_bump_subscribe_changed_view_at_and_view_derived_through_the_host(self):
        modules, seen = [], set()
        for name in ("World", "Abi"):
            closure(name, seen, modules)
        modules = modules + [{"name": "User", "source": USER}]
        for name in ("a", "b"):
            r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name, modules=modules,
                               entry="initial", seed=record(count=nat(0)))
            self.assertEqual(r["status"], "created", r)
        other = lambda n: record(other=record(world=label(""), object=label(n)))
        self.assertEqual(self.turn("b", "follow", other("a"))["result"], label("subscribed"))
        self.assertEqual(self.turn("a", "bump", record())["status"], "admitted")
        self.host.send(op="world-deliver", limit=8)
        view = lambda n: {f["name"]: f["value"] for f in self.host.send(op="world-view", principal="ember", object=n)["state"]["fields"]}
        self.assertEqual((view("a")["count"], view("b")["count"]), (nat(1), nat(1)))  # b took a's one inserted value
        self.assertEqual(self.turn("b", "past", record(other=record(world=label(""), object=label("a")), version=nat(0)))["result"], nat(0))
        self.assertEqual(self.turn("b", "counted", other("a"))["result"], nat(2))


if __name__ == "__main__":
    unittest.main()
