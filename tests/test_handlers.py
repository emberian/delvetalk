"""A handler object answers a callee's Plans before the host does, and judge answers the law's
verdict on edits without committing them.

Evidence for FOUNDATION §8 handlers (layer: host).

Handlers as cards and judge as a dry run.

`run {object, method, argument, handler}` runs the callee as `call` does, but offers every Plan
the callee yields to the handler's pure `handle(state, plan, context)` first: `answer {response}`
answers it (with a response of the callee's type), `pass` (or a plan the handler's input does
not name) lets the host answer. `judge {edits}` answers the verdict the turn would get with that
write added, committing nothing.

    python3 -W error -m unittest tests.test_handlers -v
"""
import unittest

from tests.test_chain import field
from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record
from tests.test_turn_world import declared

COUNTER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./Variant.obend as Variant
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Variant.Plan<Edits>
type Response = Variant.Response<State, {}>
law small: new.count <= 3
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
    case written(_): state.count + 1n
    case _: 0n
def probe(state: State, input: {n: Nat}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.judge({edits: {count: Plans.Edit::<Nat, Nat>.add({delta: input.n})}})):
    case judged(j): if j.admitted then "admitted" else j.clause
    case _: "other"
""")

# Answers the counter's writes itself: the write never reaches the host.
SANDBOX = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./Variant.obend as Variant
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Variant.Plan<Edits>
type Response = Variant.Response<State, {}>
type Handled = Variant.Handled<Response>
def initial() -> State:
  {count: 0n}
def handle(state: State, plan: Plan, context: Abi.Context) -> Handled:
  match plan:
    case write(_): Handled.answer({response: Response.written({})})
    case _: Handled.pass({})
""")

# Takes only views: a write does not conform to its input, so it passes.
VIEWS = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./Variant.obend as Variant
record State:
  count: Nat
sum Views:
  view: Variant.View
type Response = Variant.Response<State, {}>
type Handled = Variant.Handled<Response>
def initial() -> State:
  {count: 0n}
def handle(state: State, plan: Views) -> Handled:
  Handled.answer({response: Response.denied({})})
""")

RUNNER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./Variant.obend as Variant
record State:
  note: Nat
record Edits:
  note: Plans.Edit<Nat, Nat>
type Plan = Variant.Plan<Edits>
type Response = Variant.Response<State, Nat>
def initial() -> State:
  {note: 0n}
def go(state: State, input: {target: String, handler: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.run({object: {world: "", object: input.target}, method: "bump", argument: Plans.nothing(), handler: {world: "", object: input.handler}})):
    case returned(r): r.result
    case refused(_): 99n
    case _: 98n
""")


class Handlers(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("c", COUNTER, record(count=nat(0)))
        self.make("sandbox", SANDBOX, record(count=nat(0)))
        self.make("views", VIEWS, record(count=nat(0)))
        self.make("runner", RUNNER, record(note=nat(0)))

    def count(self):
        return field(self.state("c"), "count")["value"]

    def go(self, handler):
        return self.turn("runner", "go", record(target=label("c"), handler=label(handler)))

    def test_a_handler_answers_the_callees_write_and_nothing_is_written(self):
        r = self.go("sandbox")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.count(), "0")
        self.assertIn(("sandbox", 0), [(x["object"], x["version"]) for x in r["receipt"]["roots"]])
        self.assertEqual([w["object"] for w in r["receipt"]["outcome"]["writes"]], [])

    def test_a_plan_the_handler_does_not_name_passes_to_the_host(self):
        r = self.go("views")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.count(), "1")

    def test_an_unknown_handler_is_refused(self):
        self.assertEqual(self.go("ghost")["result"], nat(99))
        self.assertEqual(self.count(), "0")

    def test_judge_answers_the_verdict_and_commits_nothing(self):
        r = self.turn("c", "probe", record(n=nat(5)))
        self.assertEqual((r["status"], r["result"]), ("admitted", label("small")), r)
        self.assertEqual(self.turn("c", "probe", record(n=nat(2)))["result"], label("admitted"))
        self.assertEqual(self.count(), "0")
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="c")["version"], 0)


if __name__ == "__main__":
    unittest.main()
