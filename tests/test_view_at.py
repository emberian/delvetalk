"""`viewAt {object, version}`: a past version of an object's state, rebuilt from the journal and
answered as `view` answers the present one, under read authority, with the root recorded at the
object's CURRENT version.

Evidence for HOST-HANDOFF 5.47 (layer: host). Refuted by a state other than the one the version had, a
root at the old version, a future version answered, or a private object answered.

    python3 -W error -m unittest tests.test_view_at -v
"""
import unittest

from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record

COUNTER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
sum Plan:
  write: {object: Plans.Reference, edits: Edits}
  viewAt: {object: Plans.Reference, version: Nat}
sum Response:
  viewed: {version: Nat, state: State}
  written: {}
  denied: {}
  refused: {clause: String}
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
    case written(_): state.count + 1n
    case _: 0n
def at(state: State, input: {target: String, version: Nat}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.viewAt({object: {world: "", object: input.target}, version: input.version})):
    case viewed(v): v.state.count * 100n + v.version
    case refused(_): 999999n
    case denied(_): 888888n
    case _: 0n
"""


class ViewAt(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()

    def counter(self, name, **extra):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name, source=COUNTER,
                           entry="initial", seed=record(count=nat(5)), **extra)
        self.assertEqual(r["status"], "created", r)

    def at(self, target, version, principal="ann", reader="reader"):
        return self.turn(reader, "at", record(target=label(target), version=nat(version)), principal=principal)

    def test_each_past_version_and_the_root_is_the_current_version(self):
        self.counter("reader")
        self.counter("c")
        for _ in range(3):
            self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        for version, count in ((0, 5), (1, 6), (2, 7), (3, 8)):
            r = self.at("c", version)
            self.assertEqual(r["result"], nat(count * 100 + version), (version, r))
        r = self.at("c", 1)
        self.assertIn({"object": "c", "version": 3}, r["receipt"]["roots"])
        self.assertEqual(self.at("c", 4)["result"], nat(999999))
        self.reopen()
        self.assertEqual(self.at("c", 2)["result"], nat(702))

    def test_a_private_object_is_denied(self):
        self.counter("reader")
        self.counter("vault", read={"principals": ["ember"]})
        self.assertEqual(self.at("vault", 0)["result"], nat(888888))
        self.assertEqual(self.at("vault", 0, principal="ember")["result"], nat(500))


if __name__ == "__main__":
    unittest.main()
