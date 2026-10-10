"""`viewDerived {object, view}`: a card reads a view another object's package derives from its state,
as first-order Data, under read authority, with the root recorded; a view the package does not declare
in `views()` is refused by name; `world-inspect` lists the declared views.

Evidence for HOST-HANDOFF 5.46 (layer: host). Refuted by a value other than the view's, a view read
without the root, a private object answered, or an undeclared definition run as a view.

The reader declares its own Plan and Response sums: the host reads Plan labels, not library types,
so this needs no Plan.obend constructor.

    python3 -W error -m unittest tests.test_view_derived -v
"""
import unittest

from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record

READER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  note: String
sum Plan:
  viewDerived: {object: Plans.Reference, view: String}
sum Response:
  derived: {version: Nat, value: Data}
  denied: {}
  refused: {clause: String}
def initial() -> State:
  {note: ""}
def peek(state: State, input: {target: String, view: String}, context: Abi.Context) -> Activity<Plan, Response, Data>:
  match perform(Plan.viewDerived({object: {world: "", object: input.target}, view: input.view})):
    case derived(d): d.value
    case refused(r): Data.of::<String>(r.clause)
    case denied(_): Data.of::<String>("denied")
"""
TARGET = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
record State:
  count: Nat
  words: String
def initial() -> State:
  {count: 3n, words: "hidden"}
def views() -> Lists.List<String>:
  Lists.List::<String>.cons({head: "doubled", tail: Lists.List::<String>.cons({head: "greeting", tail: Lists.List::<String>.nil({})})})
def doubled(state: State) -> Nat:
  state.count + state.count
def greeting(state: State, context: Abi.Context) -> String:
  textConcat("hello ", context.principal)
def secret(state: State) -> String:
  state.words
"""


class ViewDerived(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("reader", READER, record(note=label("")))

    def target(self, name, **extra):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name, source=TARGET,
                           entry="initial", seed=record(), **extra)
        self.assertEqual(r["status"], "created", r)

    def peek(self, target, view, principal="ann"):
        return self.turn("reader", "peek", record(target=label(target), view=label(view)), principal=principal)

    def test_a_declared_view_answers_its_value_and_records_the_root(self):
        self.target("counter")
        r = self.peek("counter", "doubled")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(6)), r)
        self.assertIn({"object": "counter", "version": 0}, r["receipt"]["roots"])
        hello = self.peek("counter", "greeting", principal="kim")
        self.assertEqual(hello["result"], label("hello kim"), hello)

    def test_an_undeclared_definition_is_not_a_view(self):
        self.target("counter")
        self.assertEqual(self.peek("counter", "secret")["result"], label("noView"))
        self.assertEqual(self.peek("counter", "missing")["result"], label("noView"))

    def test_a_private_object_is_denied(self):
        self.target("vault", read={"principals": ["ember"]})
        self.assertEqual(self.peek("vault", "doubled")["result"], label("denied"))
        self.assertEqual(self.peek("vault", "doubled", principal="ember")["result"], nat(6))

    def test_inspect_lists_the_declared_views(self):
        self.target("counter")
        r = self.host.send(op="world-inspect", principal="ann", object="counter")
        self.assertEqual(r["views"], ["doubled", "greeting"], r)


if __name__ == "__main__":
    unittest.main()
