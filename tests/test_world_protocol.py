"""world/lib/World.obend, the world's protocol (docs/WHOLENESS.md section 1), through the real
checker: an object in the message dialect compiles against it, every protocol method it uses
lowers to one message to the world, and the artifact names them. Running such an object
through the host waits for the host's message dispatch (WHOLENESS §4, host day 2).
"""
import unittest

from tests.test_objects import closure, compile_job

USER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./Document.obend as Document
import ./World.obend as World
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
        for entry, methods in [("bump", ["write"]), ("peek", ["view"]), ("asked", ["call"]), ("shown", ["offer", "inspect"])]:
            artifact = self.compiled(entry)
            self.assertEqual(artifact.get("dialect"), "message", entry)
            self.assertEqual(artifact.get("world"), methods, entry)


if __name__ == "__main__":
    unittest.main()
