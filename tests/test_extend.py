"""Extend, not replace: a layer grafted by reprogram or the extend Plan overrides what it defines,
stacks, survives snapshots and replay, and is judged by the object's law.

Evidence for FOUNDATION §8 extend (layer: host).

Extend, not replace: `reprogram {mode: extend}` and Plan
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

    def test_a_snapshot_holding_a_layer_of_the_older_form_still_runs(self):
        # Before the layer line, the host inserted `import ./Main.obend as Super` after `edition`;
        # a snapshot written then holds that source, and loading gives it the line.
        from tests.test_snapshot import read_snapshot, write_snapshot
        self.assertEqual(self.extend(LAYER)["status"], "admitted")
        height = self.host.send(op="world-snapshot")["height"]
        path = self.path + f".snapshot.{height}.cbor"
        body = read_snapshot(path)
        [obj] = [o for o in body["objects"] if o["id"] == "c"]
        [layer] = [m for m in obj["compile"]["modules"] if m["name"] == "Layer1"]
        below = obj["compile"]["modules"][-2]["name"]
        first, rest = layer["source"].split("\n", 1)
        self.assertEqual(first, f"layer over ./{below}.obend")
        edition, more = rest.split("\n", 1)
        layer["source"] = f"{edition}\nimport ./{below}.obend as Super\n{more}"
        write_snapshot(path, body)
        self.release()
        self.host = self.spawn()
        opened = self.host.send(op="world-open", path=self.path)
        self.assertEqual(opened["snapshot"]["resumed"], height, opened)
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(self.turn("c", "peek")["status"], "admitted")
        self.assertEqual(self.count(), "10")

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


LOUDER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
type State = Super.State
def render(state: State, context: Abi.Context) -> Document.Document:
  Document.concat(Document.text("LOUDER\\n"), Super.render(state, context))
"""


class LateBinding(Reflection):
    """The host writes `layer over` as the layer's first line, so the kernel binds the whole stack late:
    Bell's own rain reply calls render, which a Louder layer grafted by the extend Plan overrides.
    Refuted by a rain reply without LOUDER, or by losing it on replay."""

    def setUp(self):
        super().setUp()
        self.open_library()

    def rain(self, text, ident):
        r = self.turn("bell", "receive", record(text=label("rain: " + text), post=label("at://x/" + ident)),
                      principal="glm", identity=ident)
        self.assertEqual(r["status"], "admitted", r)
        return r["offers"][-1]["text"]

    def test_a_louder_layer_changes_the_card_bells_own_rain_reply_renders(self):
        from tests.test_objects import closure
        amber = {"tag": "variant", "label": "amber", "payload": record()}
        r = self.host.send(op="world-create", principal="ember", identity="mk-bell", object="bell", modules=closure("Bell"),
                           entry="initial", seed=record(colour=amber, seed=label("a fern"), planter=label("glm")))
        self.assertEqual(r["status"], "created", r)
        self.assertFalse(self.rain("a drizzle", "r1").startswith("LOUDER"))
        self.make("forge", FORGE, record(note=label("")))
        g = self.turn("forge", "graft", record(target=label("bell"), package=label(LOUDER)))
        self.assertEqual((g["status"], g["result"]), ("admitted", label("grafted")), g)
        said = self.rain("a fog", "r2")
        self.assertTrue(said.startswith("LOUDER\n"), said)
        self.assertIn("a fog", said)
        names = [m["name"] for m in self.host.send(op="world-inspect", principal="ember", object="bell")["methods"]]
        self.assertIn("rain", names)
        self.reopen()
        self.assertTrue(self.rain("a mist", "r3").startswith("LOUDER\n"))


if __name__ == "__main__":
    unittest.main()
