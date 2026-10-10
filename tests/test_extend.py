"""Extend, not replace (FOUNDATION section 13, row 3): `reprogram {mode: extend}` and Plan
`extend` add the offered module as a layer over the object's current code, which it sees as
`Super`; what the layer defines overrides, everything else is the code below.

    python3 -W error -m unittest tests.test_extend -v
"""
import unittest

from tests.test_chain import field
from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record

BASE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
def initial() -> State:
  {count: 0n}
def add(context: Abi.Context, n: Nat) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: n})}})):
    case _: n
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  add(context, 1n)
def peek(state: State, context: Abi.Context) -> State:
  {count: state.count}
"""

LAYER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
type State = Super.State
type Plan = Super.Plan
type Response = Super.Response
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  Super.add(context, 10n)
def triple(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  Super.add(context, 3n)
"""

SECOND = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Main.obend as Base
type State = Base.State
type Plan = Base.Plan
type Response = Base.Response
def triple(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  Super.triple(state, context)
def zero(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  Base.add(context, 0n)
"""


FORGE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  note: String
record Edits:
  note: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
def initial() -> State:
  {note: ""}
def graft(state: State, input: {target: String, package: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.extend({object: {world: "", object: input.target}, package: input.package, migration: ""})):
    case reprogrammed(r): "grafted"
    case refused(r): r.clause
    case _: "other"
"""


# The layer of tests/test_layers.py, grafted by the host's extend Plan.
LOUDER = """layer over ./Bell.obend
edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
type State = Super.State
def render(state: State, context: Abi.Context) -> Document.Document:
  Document.concat(Document.text("LOUDER\\n"), Super.render(state, context))
"""


class LouderBell(Reflection):
    """Louder over Bell through the host's `extend` Plan: a rain reply's card is the bell as the
    layer renders it (Bell's receive calls render; with late binding across the stack,
    KERNEL-HANDOFF section 13, that is Louder's). The host's extend still composes layers by
    `delegate` and names the object's code `Super` without a layer line: today the graft is
    refused programRefused/compile, "import must name an earlier supplied module:
    ./Bell.obend". Expected to fail until the host lane drops `delegate`."""

    def setUp(self):
        super().setUp()
        self.open_library()
        with open("world/objects/Bell.obend") as handle:
            bell = handle.read()
        empty = {"tag": "list", "items": []}
        self.make("bell", bell, record(colour={"tag": "variant", "label": "amber", "payload": record()}, seed=label("a fern"),
                                       rains=empty, rung={"tag": "boolean", "value": False}, planting=label(""),
                                       planter=label("glm"), planterHandle=label(""), observers=empty))
        self.make("forge", FORGE, record(note=label("")))

    @unittest.expectedFailure
    def test_a_rain_reply_after_the_graft_shows_louders_card(self):
        graft = self.turn("forge", "graft", record(target=label("bell"), package=label(LOUDER)))
        self.assertEqual((graft["status"], graft["result"]), ("admitted", label("grafted")), graft)
        rain = self.turn("bell", "receive", record(text=label("delvetalk bell rain\ntext: a drizzle"), post=label("at://x/1")), principal="glm")
        self.assertEqual((rain["status"], rain["result"]["label"]), ("admitted", "done"), rain)
        card = rain["offers"][0]["text"]
        self.assertIn("a drizzle", card)
        self.assertTrue(card.startswith("LOUDER\n"), card)


class Extend(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("c", BASE, record(count=nat(0)))

    def count(self):
        return field(self.state("c"), "count")["value"]

    def extend(self, source, who="ember", ident="x1"):
        version = self.host.send(op="world-view", principal="ember", object="c")["version"]
        return self.host.send(op="world-reprogram", principal=who, identity=ident, object="c", version=version,
                              package=source, mode="extend")

    def test_a_layer_overrides_what_it_defines_and_keeps_the_rest(self):
        before = self.host.send(op="world-inspect", principal="ember", object="c")
        r = self.extend(LAYER)
        self.assertEqual(r["status"], "admitted", r)
        [prog] = r["receipt"]["outcome"]["reprograms"]
        self.assertEqual(prog["mode"], "extend")
        self.assertNotEqual(prog["newPin"], before["pin"])
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(self.count(), "10")
        self.assertEqual(self.turn("c", "triple")["status"], "admitted")
        self.assertEqual(self.count(), "13")
        names = {m["name"] for m in self.host.send(op="world-inspect", principal="ember", object="c")["methods"]}
        self.assertTrue({"bump", "triple", "peek"} <= names, names)
        self.reopen()
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(self.count(), "23")

    def test_layers_stack_and_a_layer_reaches_two_down(self):
        self.assertEqual(self.extend(LAYER)["status"], "admitted")
        r = self.extend(SECOND, ident="x2")
        self.assertEqual(r["status"], "admitted", r["receipt"]["outcome"])
        self.assertEqual(self.turn("c", "triple")["status"], "admitted")
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(self.count(), "13")
        self.assertIn("height", self.host.send(op="world-snapshot"))
        self.reopen()
        opened = self.host.send(op="world-open", path=self.path)
        self.assertGreater(opened["snapshot"]["resumed"], 0, opened)
        self.assertEqual(self.turn("c", "zero")["status"], "admitted")
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(self.count(), "23")

    def test_the_extend_plan_grafts_a_layer_from_another_object(self):
        self.make("forge", FORGE, record(note=label("")))
        r = self.turn("forge", "graft", record(target=label("c"), package=label(LAYER)))
        self.assertEqual((r["status"], r["result"]), ("admitted", label("grafted")), r)
        self.assertEqual(r["receipt"]["outcome"]["reprograms"][0]["mode"], "extend")
        self.turn("c", "bump")
        self.assertEqual(self.count(), "10")
        theirs = self.turn("forge", "graft", record(target=label("c"), package=label(SECOND)), principal="kim")
        self.assertEqual((theirs["status"], theirs["result"]), ("admitted", label("owner")), theirs)
        self.assertNotIn("reprograms", theirs["receipt"]["outcome"])

    def test_an_extension_is_judged_by_the_objects_law_and_a_broken_layer_is_refused(self):
        stranger = self.extend(LAYER, who="mallory")
        self.assertEqual((stranger["status"], stranger["receipt"]["outcome"]["class"]), ("refused", "lawRefused"))
        broken = self.extend(LAYER.replace("Super.add(context, 3n)", "missing(context)"), ident="x3")
        self.assertEqual((broken["status"], broken["receipt"]["outcome"]["class"]), ("refused", "programRefused"), broken)
        self.turn("c", "bump")
        self.assertEqual(self.count(), "1")
        bad = self.host.send(op="world-reprogram", principal="ember", identity="x4", object="c", version=1,
                             package=LAYER, mode="graft")
        self.assertEqual(bad["status"], "error")


if __name__ == "__main__":
    unittest.main()
