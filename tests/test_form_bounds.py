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
record Edits:
  got: Plans.Edit<String, {}>
  note: Plans.Edit<String, {}>
def initial() -> State:
  {got: "", note: ""}
def keep() -> Edits:
  {got: Plans.Edit.keep({}), note: Plans.Edit.keep({})}
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


if __name__ == "__main__":
    unittest.main()
