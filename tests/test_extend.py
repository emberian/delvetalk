"""Extend, not replace: a layer grafted by reprogram or the extend Plan overrides what it defines,
stacks, survives snapshots and replay, and is judged by the object's law.

Evidence for FOUNDATION §8 extend (layer: host).

Extend, not replace: `reprogram {mode: extend}` and Plan
`extend` add the offered module as a layer over the object's current code, which it sees as
`Super`; what the layer defines overrides, everything else is the code below.

    python3 -W error -m unittest tests.test_extend -v
"""
import unittest

from tests.test_reflection import Reflection
from tests.wire import field, label, nat, record
from tests.bend import closure, declared
from tests.test_chain import Chain

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


# THING's own package with a verb of its own (a lawful module takes no layer, so its owner reprograms it whole).
def shining():
    from tests.bend import MODULES
    source = open(MODULES["Thing"]).read()
    return source.replace('  Text.words("transfer copy copyFor drop ~act")', '  Text.words("transfer copy copyFor drop ~act shine")') + "def shine(state: State, context: Abi.Context) -> Activity<Bool>:\n  true\n"


class Copy(Chain):
    def test_a_copy_of_a_reprogrammed_thing_runs_its_program(self):
        """Codex objects 12: `copy` created the copy from the package named "Thing", the library's module, so a
        thing its owner reprogrammed to `shine` copied into one that could not (or, its package holding no module
        of that name, not at all). The copy is made from the copied thing's own sealed package."""
        made = self.host.send(op="world-create", principal="ember", identity="mk-lamp", object="lamp", modules=closure("Thing"),
                              entry="initial", seed=record(owner=label("ember"), name=label("lamp")))
        self.assertEqual(made["status"], "created", made)
        version = self.host.send(op="world-view", principal="ember", object="lamp")["version"]
        grafted = self.host.send(op="world-reprogram", principal="ember", identity="graft", object="lamp", version=version, package=shining())
        self.assertEqual(grafted["status"], "admitted", grafted)
        copied = self.turn("lamp", "copy", record(), principal="glm")
        self.assertEqual(copied["status"], "admitted", copied)
        [created] = copied["receipt"]["outcome"]["creates"]
        names = {m["name"] for m in self.host.send(op="world-inspect", principal="glm", object=created["object"])["methods"]}
        self.assertIn("shine", names)
        self.assertEqual(self.turn(created["object"], "shine", record(), principal="glm")["status"], "admitted")


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


# A card of the base (it hears replies), and a kind: any object whose state holds a layer `body`.
CARD = BASE + """def receive(state: State, input: {text: String, post: String}, context: Abi.Context) -> Activity<Nat>:
  0n
"""

KIND = declared("""edition ObjectiveBend 1
record State:
  name: String
  body: String
def initial() -> State:
  {name: "", body: ""}
""")

KIND_LAW = declared("""edition ObjectiveBend 1
record State:
  name: String
  law: String
def initial() -> State:
  {name: "", law: ""}
""")


class HostSpells(Reflection):
    """docs/CATALOGUE.md §2: the host's own spells on any card, each a direct turn judged by the card's
    own law: `become` lays a kind's body over the card."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("c", CARD, record(count=nat(0)))
        self.make("kind/louder", KIND, record(name=label("louder"), body=label(LAYER)))

    def say(self, text, who="ember", identity=None):
        return self.turn("c", "receive", record(text=label(text), post=label("")), principal=who, identity=identity)

    def test_become_lays_the_kinds_body_under_the_cards_own_law(self):
        self.assertIn("delvetalk c become\nkind:", self.say("delvetalk c ?")["text"])
        self.assertNotIn("become", self.say("delvetalk c ?", who="kim")["text"])
        stranger = self.say("delvetalk c become\nkind: kind/louder", who="kim", identity="b0")
        self.assertEqual((stranger["status"], stranger["receipt"]["outcome"]["class"]), ("refused", "lawRefused"), stranger)
        r = self.say("delvetalk c become\nkind: kind/louder", identity="b1")
        self.assertEqual(r["status"], "admitted", r)
        [prog] = r["receipt"]["outcome"]["reprograms"]
        kind = self.host.send(op="world-inspect", principal="ember", object="kind/louder")
        self.assertEqual(prog["mode"], "extend")
        self.assertEqual((prog["madeFrom"]["object"], prog["madeFrom"]["pin"]), ("kind/louder", kind["pin"]))
        self.assertTrue(prog["madeFrom"]["receipt"].startswith("bafy"), prog)
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(field(self.state("c"), "count")["value"], "10")
        self.assertEqual(self.say("delvetalk c become\nkind: kind/louder", identity="b1"), r)   # a retry: the receipt
        self.reopen()
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(field(self.state("c"), "count")["value"], "20")
        missing = self.say("delvetalk c become\nkind: kind/none", identity="b2")["receipt"]["outcome"]
        self.assertEqual((missing["class"], missing["clause"]), ("badSpell", "unknownKind"), missing)

    def test_adopt_appends_a_kinds_clauses_under_the_amend_metarule(self):
        circle = 'law circle "only ember and kim count": request.subject == "ember" or request.subject == "kim"'
        self.make("kind/circle", KIND_LAW, record(name=label("circle"), law=label(circle)))
        self.assertIn("delvetalk c adopt\nlaw:", self.say("delvetalk c ?")["text"])
        stranger = self.say("delvetalk c adopt\nlaw: kind/circle", who="kim", identity="a0")
        self.assertEqual((stranger["status"], stranger["receipt"]["outcome"]["class"]), ("refused", "lawRefused"), stranger)
        r = self.say("delvetalk c adopt\nlaw: kind/circle", identity="a1")
        self.assertEqual(r["status"], "admitted", r)
        laws = self.host.send(op="world-inspect", principal="ember", object="c", source=False)["laws"]
        self.assertIn(("circle", "only ember and kim count"), [(l["name"], l.get("reading")) for l in laws])
        self.assertEqual(self.turn("c", "bump", principal="eve")["receipt"]["outcome"].get("clause"), "circle")
        self.assertEqual(self.turn("c", "bump", principal="kim")["status"], "admitted")
        clash = self.say("delvetalk c adopt\nlaw: kind/circle", identity="a2")["receipt"]["outcome"]
        self.assertEqual((clash["class"], clash["clause"]), ("badSpell", "lawClash"), clash)
        self.reopen()
        self.assertEqual(self.turn("c", "bump", principal="eve")["receipt"]["outcome"].get("clause"), "circle")

    def test_adopt_takes_a_law_written_inline(self):
        """The second playtest's F2: `adopt / law:` taught that a law is adopted only by id. A value that
        starts `law ` is the clause set itself, with its reading; the usage says both."""
        self.assertIn("delvetalk c adopt\nlaw: law <name> \"<reading>\": <expression>, or a kind's or a page's id\n",
                      self.say("delvetalk c ?")["text"])
        r = self.say('delvetalk c adopt\nlaw: law small "ten at most": new.count <= 10', identity="i1")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual([x["object"] for x in r["receipt"]["roots"]], ["c"], r)
        laws = self.host.send(op="world-inspect", principal="ember", object="c", source=False)["laws"]
        self.assertIn(("small", "ten at most"), [(l["name"], l.get("reading")) for l in laws])
        bad = self.say("delvetalk c adopt\nlaw: law broken: new.count <<< 2", identity="i2")["receipt"]["outcome"]
        self.assertEqual((bad["class"], bad["clause"]), ("programRefused", "law syntax"), bad)
        unknown = self.say("delvetalk c adopt\nlaw: kind/none", identity="i3")["receipt"]["outcome"]
        self.assertEqual((unknown["class"], unknown["clause"]), ("badSpell", "unknownLaw"), unknown)
        self.assertIn("or write the law", unknown["reason"])

    def test_lend_grants_a_method_until_a_clock_and_the_borrower_runs_it_as_the_lender(self):
        version = self.host.send(op="world-view", principal="ember", object="c")["version"]
        a = self.host.send(op="world-amend", principal="ember", identity="own", object="c", version=version,
                           law='law owner "only ember counts": not (request.kind == 0) or request.subject == "ember"')
        self.assertEqual(a["status"], "admitted", a)
        self.assertEqual(self.turn("c", "bump", principal="kim")["receipt"]["outcome"].get("clause"), "owner")
        self.assertNotIn("lend", self.say("delvetalk c ?", who="kim")["text"])
        self.assertIn("delvetalk c lend\nto:", self.say("delvetalk c ?")["text"])
        theirs = self.say("delvetalk c lend\nto: me\nmethod: bump\nuntil: +5", who="kim", identity="l0")["receipt"]["outcome"]
        self.assertEqual((theirs["class"], theirs["clause"]), ("badSpell", "notYours"), theirs)
        r = self.say("delvetalk c lend\nto: kim\nmethod: bump\nuntil: +5", identity="l1")
        self.assertEqual(r["status"], "admitted", r)
        [g] = r["receipt"]["outcome"]["grants"]
        self.assertEqual((g["to"], g["method"], g["until"], g["holder"]), ("kim", "bump", 5, "c"))
        self.assertEqual(g["reading"], "lent by ember: bump, until clock 5")
        lent = self.turn("c", "bump", principal="kim")
        self.assertEqual(lent["status"], "admitted", lent)
        self.reopen()
        self.assertEqual(self.turn("c", "bump", principal="kim")["status"], "admitted")
        self.host.send(op="world-advance", height=6)
        self.assertEqual(self.turn("c", "bump", principal="kim")["receipt"]["outcome"].get("clause"), "owner")


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


if __name__ == "__main__":
    unittest.main()
