"""A spell is judged by the card's own form (HOST-HANDOFF 5.69): the kinds its `forms()` declares
override the defaults the method's input type gives, and a `source` field (`Form.Kind.source`) takes
Bend source up to `Limits.formSourceMax` (16 KiB), as a `<<BEND` block or as the reply's ```obend
fenced block.

Evidence for spells (layer: host). Refuted by: a 6 KB source block refused at the type's 1,400
characters; a 20 KB one admitted, or refused without naming the field; a fenced block not reaching
the method; a form's bounds not shown by world-inspect.
"""
import unittest

from tests.test_chain import Chain
from tests.test_turn_world import ON_DISK, closure, declared, label, record

KIND_LINE = ("  choice: {options: Names}\n", "  choice: {options: Names}\n  source: {}\n")

BENCH = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  got: String
  note: String
def initial() -> State:
  {got: "", note: ""}
def field(name: String, kind: Form.Kind) -> Form.Field:
  {name: name, kind: kind}
def forms() -> Lists.List<Form.Form>:
  Lists.List::<Form.Form>.cons({head: {card: "bench", action: "check", fields: Lists.List::<Form.Field>.cons({head: field("source", Form.Kind.source({})), tail: Lists.List::<Form.Field>.nil({})})}, tail: Lists.List::<Form.Form>.cons({head: {card: "bench", action: "jot", fields: Lists.List::<Form.Field>.cons({head: field("note", Form.Kind.text({min: 2n, max: 5n})), tail: Lists.List::<Form.Field>.nil({})})}, tail: Lists.List::<Form.Form>.nil({})})})
def check(state: State, input: {source: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {got: set input.source}
  0n
def jot(state: State, input: {note: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {note: set input.note}
  0n
def receive(state: State, input: {text: String, post: String}, context: Abi.Context) -> Activity<Nat>:
  0n
""", "check", "jot")


class FormBounds(Chain):
    def setUp(self):
        super().setUp()
        with open(ON_DISK["Form"], encoding="utf-8") as f:
            form = f.read()
        override = {"Form": form if "source:" in form else form.replace(*KIND_LINE)}
        seen, out = set(), []
        for dep in ("Abi", "List", "Form", "Plan", "World"):
            closure(dep, seen, out, override)
        self.make("bench", out + [{"name": "Bench", "source": BENCH}], record())

    def got(self, name="got"):
        return {f["name"]: f["value"] for f in self.state("bench")["fields"]}[name]["value"]

    def say(self, text):
        return self.turn("bench", "receive", record(text=label(text), post=label("")), principal="glm")

    def test_a_source_block_takes_sixteen_kib_and_no_more(self):
        code = ("def x() -> Nat:\n  0n\n" * 400)[:6000].rstrip("\n")
        r = self.say("delvetalk bench check\nsource: <<BEND\n" + code + "\nBEND")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(len(self.got()), len(code))
        big = "x" * 20000
        r = self.say("delvetalk bench check\nsource: <<BEND\n" + big + "\nBEND")
        outcome = r["receipt"]["outcome"]
        self.assertEqual((outcome["class"], outcome["clause"]), ("badSpell", "badValue"), r)
        self.assertIn("source takes 1 to 16384 characters", outcome["reason"])

    def test_a_fenced_block_is_the_source_field_under_the_same_bound(self):
        r = self.say("delvetalk bench check\n\n```obend\nedition ObjectiveBend 1\n```\n")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.got(), "edition ObjectiveBend 1")
        r = self.say("delvetalk bench check\n```obend\n" + "y" * 17000 + "\n```")
        self.assertEqual(r["receipt"]["outcome"]["clause"], "badValue", r)

    def test_the_forms_bounds_hold_and_inspect_shows_them(self):
        self.assertEqual(self.say("delvetalk bench jot\nnote: abcdefg")["receipt"]["outcome"]["clause"], "badValue")
        self.assertEqual(self.say("delvetalk bench jot\nnote: abc")["status"], "admitted")
        self.assertEqual(self.got("note"), "abc")
        forms = self.host.send(op="world-inspect", principal="glm", object="bench", source=False)["forms"]
        self.assertIn("16384", str(forms))
        self.assertIn("{'name': 'max', 'value': {'tag': 'natural', 'value': '5'}}", str(forms))


class WorkshopSource(Chain):
    """The Workshop's `check` takes a `source` block by its form's bound, not the text default."""

    def create(self):
        self.make("workshop", closure("Workshop"), record())

    def say(self, text):
        return self.turn("workshop", "receive", record(text=label(text), post=label("")), principal="glm")

    def test_a_six_kib_block_is_checked_and_twenty_kib_refused_by_name(self):
        self.create()
        code = "edition ObjectiveBend 1\n" + ("def x() -> Nat:\n  0n\n" * 400)[:6000].rstrip("\n")
        r = self.say("delvetalk workshop check\nsource: <<BEND\n" + code + "\nBEND")
        self.assertEqual(r["status"], "admitted", r)
        r = self.say("delvetalk workshop check\nsource: <<BEND\n" + "x" * 20000 + "\nBEND")
        outcome = r["receipt"]["outcome"]
        self.assertEqual((outcome["class"], outcome["clause"]), ("badSpell", "badValue"), r)
        self.assertIn("source takes 1 to 16384 characters", outcome["reason"])
        forms = self.host.send(op="world-inspect", principal="glm", object="workshop", source=False)["forms"]
        self.assertIn("16384", str(forms))


class ExpectedForm(Chain):
    """A typeMismatch's `expected.form` is the card's declared form (the Garden's `seed: text 1..80`),
    the bounds the spell path and the front's actions use, not the input type's default 0..1400."""

    def test_the_expected_form_carries_the_declared_bounds(self):
        from tests.test_chain import garden_seed
        from tests.test_turn_world import nat
        self.make("garden", closure("Garden"), garden_seed())
        r = self.turn("garden", "plant", record(colour=label("amber"), seed=nat(3)), principal="glm")
        out = r["receipt"]["outcome"]
        self.assertEqual(out["class"], "typeMismatch", r)
        fields = {f["name"]: f["kind"] for f in out["expected"]["form"]["fields"]}
        self.assertEqual((fields["seed"]["min"], fields["seed"]["max"]), (1, 80), fields)


# A form block and no hand-written forms() or methods(): the kernel derives forms() and lists it in
# the artifact's `declares`, so `jot` is public and judged by its block's bound.
DERIVED = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./Form.obend as Form
import ./World.obend as World
record State:
  got: String
record Binding:
  name: String
  value: String
def initial() -> State:
  {got: ""}
form jot:
  note: text 2..5
def jot(state: State, input: {note: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {got: set input.note}
  1n
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  0n
"""


class DerivedForms(Chain):
    def setUp(self):
        super().setUp()
        seen, out = set(), []
        for dep in ("Abi", "List", "Form", "Plan", "World"):
            closure(dep, seen, out)
        self.modules = out + [{"name": "Bench", "source": DERIVED}]
        self.make("bench", self.modules, record())

    def say(self, text):
        return self.turn("bench", "receive", record(text=label(text), post=label("")), principal="glm")

    def test_a_derived_forms_makes_its_method_public_and_bounded(self):
        artifact = self.host.send(op="compile", modules=self.modules, entry="initial")["artifact"]
        self.assertIn("forms", artifact["declares"])
        self.assertEqual(self.turn("bench", "jot", record(note=label("abc")), principal="glm")["status"], "admitted")
        out = self.say("delvetalk bench jot\nnote: abcdefg")["receipt"]["outcome"]
        self.assertEqual((out["class"], out["clause"]), ("badSpell", "badValue"), out)
        self.assertEqual(self.say("delvetalk bench jot\nnote: abcd")["status"], "admitted")
        forms = self.host.send(op="world-inspect", principal="glm", object="bench", source=False)["forms"]
        self.assertIn("{'name': 'max', 'value': {'tag': 'natural', 'value': '5'}}", str(forms))


if __name__ == "__main__":
    unittest.main()
