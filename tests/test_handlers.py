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
import ./World.obend as World
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
def keep() -> Edits:
  {count: Plans.Edit.keep({})}
law small: new.count <= 3
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})):
    case written(_): state.count + 1n
    case _: 0n
def probe(state: State, input: {n: Nat}, context: Abi.Context) -> Activity<String>:
  match world.judge(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: input.n})})):
    case judged(j): if j.admitted then "admitted" else j.clause
    case _: "other"
""")

# Answers the counter's writes itself: the write never reaches the host.
SANDBOX = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
def keep() -> Edits:
  {count: Plans.Edit.keep({})}
def initial() -> State:
  {count: 0n}
sum Handled:
  pass: {}
  answer: {response: Data}
def handle(state: State, message: World.Message, context: Abi.Context) -> Handled:
  if message.method == "write" then Handled.answer({response: Data.of::<World.Written>(World.Written.written({}))}) else Handled.pass({})
""")

# Answers only views: a write is another method of the message, so it passes.
VIEWS = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
sum Handled:
  pass: {}
  answer: {response: Data}
def handle(state: State, message: World.Message, context: Abi.Context) -> Handled:
  if message.method == "view" then Handled.answer({response: Data.of::<World.Viewed<{}>>(World.Viewed::<{}>.denied({}))}) else Handled.pass({})
""")

RUNNER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  note: Nat
record Edits:
  note: Plans.Edit<Nat, Nat>
def keep() -> Edits:
  {note: Plans.Edit.keep({})}
def initial() -> State:
  {note: 0n}
def go(state: State, input: {target: String, handler: String}, context: Abi.Context) -> Activity<Nat>:
  match world.run::<Nat>({object: {world: "", object: input.target}, method: "bump", argument: Plans.nothing(), handler: {world: "", object: input.handler}}):
    case returned(r): r.result
    case refused(_): 99n
    case _: 98n
""")

# Calls the counter: the counter's frame is one deeper than the frame `run` started.
NESTER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.call::<Nat>({object: {world: "", object: "c"}, method: "bump", argument: Plans.nothing()}):
    case returned(r): r.result + 10n
    case _: 97n
""")

# Runs the counter under a handler of its own, from inside another `run`.
INNER = RUNNER.replace("def go(", "def bump(").replace('head: "go"', 'head: "bump"').replace("input: {target: String, handler: String}, ", "").replace(
    "input.target", '"c"').replace("input.handler", '"views"')


# The same three in the message dialect: a handler takes the World.Message a frame yields and
# answers with the result the call site's protocol method types (`write` -> Written).
MESSAGE_COUNTER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
def keep() -> Edits:
  {count: Plans.Edit.keep({})}
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {count: add 1n}
  state.count + 1n
""")

MESSAGE_NESTER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.call::<Nat>({object: {world: "", object: "mc"}, method: "bump", argument: {}}):
    case returned(r): r.result + 10n
    case _: 97n
""")

MESSAGE_SANDBOX = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./World.obend as World
record State:
  count: Nat
sum Handled:
  answer: {response: World.Written}
  pass: {}
def initial() -> State:
  {count: 0n}
def handle(state: State, plan: World.Message, context: Abi.Context) -> Handled:
  if plan.method == "write" then Handled.answer({response: World.Written.written({})}) else Handled.pass({})
""")

MESSAGE_RUNNER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./World.obend as World
record State:
  note: Nat
def initial() -> State:
  {note: 0n}
def go(state: State, input: {target: String, handler: String}, context: Abi.Context) -> Activity<Nat>:
  match world.run::<Nat>({object: {world: "", object: input.target}, method: "bump", argument: {}, handler: {world: "", object: input.handler}}):
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

    def test_a_handler_answers_the_plans_of_frames_its_callee_calls(self):
        self.make("nester", NESTER, record(n=nat(0)))
        r = self.turn("runner", "go", record(target=label("nester"), handler=label("sandbox")))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(11)), r)
        self.assertEqual(self.count(), "0")
        self.assertEqual([w["object"] for w in r["receipt"]["outcome"]["writes"]], [])
        # Without the handler the nested write is the host's.
        self.assertEqual(self.turn("nester", "bump")["result"], nat(11))
        self.assertEqual(self.count(), "1")

    def test_a_pass_goes_to_the_next_handler_out(self):
        # inner runs the counter under `views`, which passes a write; the `sandbox` around it answers it.
        self.make("inner", INNER, record(note=nat(0)))
        r = self.turn("runner", "go", record(target=label("inner"), handler=label("sandbox")))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.count(), "0")
        # Under `views` alone the write passes to the host.
        self.assertEqual(self.turn("inner", "bump")["result"], nat(1))
        self.assertEqual(self.count(), "1")

    def test_a_message_handler_answers_the_writes_of_nested_message_frames(self):
        for name, source in (("mc", MESSAGE_COUNTER), ("mn", MESSAGE_NESTER), ("ms", MESSAGE_SANDBOX), ("mr", MESSAGE_RUNNER)):
            self.make(name, source, record())
        mc = lambda: field(self.state("mc"), "count")["value"]
        for target, result in (("mc", nat(1)), ("mn", nat(11))):
            r = self.turn("mr", "go", record(target=label(target), handler=label("ms")))
            self.assertEqual((r["status"], r["result"]), ("admitted", result), r)
            self.assertEqual([w["object"] for w in r["receipt"]["outcome"]["writes"]], [])
        self.assertEqual(mc(), "0")
        self.assertEqual(self.turn("mn", "bump")["result"], nat(11))
        self.assertEqual(mc(), "1")

    def test_judge_answers_the_verdict_and_commits_nothing(self):
        r = self.turn("c", "probe", record(n=nat(5)))
        self.assertEqual((r["status"], r["result"]), ("admitted", label("small")), r)
        self.assertEqual(self.turn("c", "probe", record(n=nat(2)))["result"], label("admitted"))
        self.assertEqual(self.count(), "0")
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="c")["version"], 0)


if __name__ == "__main__":
    unittest.main()
