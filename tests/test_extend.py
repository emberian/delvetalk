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
from tests.test_turn_world import declared

BASE = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def add(context: Abi.Context, n: Nat) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: n})})):
    case _: n
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  add(context, 1n)
def peek(state: State, context: Abi.Context) -> State:
  {count: state.count}
""")

LAYER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
type State = Super.State
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  Super.add(context, 10n)
def triple(state: State, context: Abi.Context) -> Activity<Nat>:
  Super.add(context, 3n)
""")

SECOND = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Main.obend as Base
type State = Base.State
def triple(state: State, context: Abi.Context) -> Activity<Nat>:
  Super.triple(state, context)
def zero(state: State, context: Abi.Context) -> Activity<Nat>:
  Base.add(context, 0n)
""")


FORGE = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  note: String
def initial() -> State:
  {note: ""}
def graft(state: State, input: {target: String, package: String}, context: Abi.Context) -> Activity<String>:
  match world.extend({object: {world: "", object: input.target}, package: input.package, migration: ""}):
    case reprogrammed(r): "grafted"
    case refused(r): r.clause
    case _: "other"
""")


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


LOUDER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
type State = Super.State
def render(state: State, context: Abi.Context) -> Document.Document:
  Document.concat(Document.text("LOUDER\\n"), Super.render(state, context))
""")


PROPOSER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  note: String
def initial() -> State:
  {note: ""}
def propose(state: State, input: {target: String, package: String, migration: String}, context: Abi.Context) -> Activity<String>:
  match world.reprogram({object: {world: "", object: input.target}, package: input.package, migration: input.migration}):
    case reprogrammed(_): "reprogrammed"
    case refused(r): textConcat(r.clause, textConcat(" | ", r.reading))
    case _: "other"
""")


class ReprogramReading(Reflection):
    """codex agent 12: a refused reprogram tells its proposer what to correct (the migration's or the
    compiler's diagnostic), not the clause alone."""

    def test_a_missing_migration_is_named_in_the_refusal(self):
        self.open_library()
        self.make("c", BASE, record(count=nat(0)))
        self.make("p", PROPOSER, record(note=label("")))
        wider = BASE.replace("  count: Nat\n", "  count: Nat\n  extra: Nat\n", 1).replace("{count: 0n}", "{count: 0n, extra: 0n}").replace(
            "{count: state.count}", "{count: state.count, extra: 0n}")
        self.assertNotEqual(wider, BASE)
        r = self.turn("p", "propose", record(target=label("c"), package=label(wider), migration=label("nope")))
        self.assertEqual(r["status"], "admitted", r)
        said = r["result"]["value"]
        self.assertTrue(said.startswith("migration | "), said)
        self.assertIn("nope", said)


class ExtensionPins(Reflection):
    """An extension's pin is its compiled closure's (docs 2): the same layer over the same base under two
    libraries is two closures and two pins."""

    def test_the_same_layer_under_another_library_is_another_pin(self):
        import os, shutil, tempfile
        from tests.test_reflection import LIBRARY
        with tempfile.TemporaryDirectory() as scratch:
            lib = os.path.join(scratch, "lib")
            shutil.copytree(LIBRARY, lib)
            self.open_library(lib)
            self.make("c", BASE, record(count=nat(0)))
            self.make("d", BASE, record(count=nat(0)))
            first = self.host.send(op="world-reprogram", principal="ember", identity="x1", object="c", version=0,
                                   package=LAYER, mode="extend")
            self.assertEqual(first["status"], "admitted", first)
            with open(os.path.join(lib, "World.obend"), "a", encoding="utf-8") as f:
                f.write("# another library\n")
            self.assertEqual(self.host.send(op="world-library", principal="ember", identity="lib-2")["status"], "library")
            second = self.host.send(op="world-reprogram", principal="ember", identity="x2", object="d", version=0,
                                    package=LAYER, mode="extend")
            self.assertEqual(second["status"], "admitted", second)
            pins = [r["receipt"]["outcome"]["reprograms"][0]["newPin"] for r in (first, second)]
            self.assertNotEqual(pins[0], pins[1])
            self.reopen()
            self.assertEqual([self.host.send(op="world-inspect", principal="ember", object=o)["pin"] for o in "cd"], pins)


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
