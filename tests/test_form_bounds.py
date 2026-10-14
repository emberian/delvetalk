"""A spell is judged by the card's own form (HOST-HANDOFF §5.3 "Forms", §5.1 "Typed arguments"): the kinds its `forms()` declares
override the defaults the method's input type gives, and a `source` field (`Form.Kind.source`) takes
Bend source up to `Limits.formSourceMax` (`Bounds.maxPackageBytes`, 128 KiB), as a `<<BEND` block or as the reply's ```obend
fenced block.

Evidence for spells (layer: host). Refuted by: a 6 KB source block refused at the type's 1,400
characters; a 140 KB one admitted, or refused without naming the field; a fenced block not reaching
the method; a form's bounds not shown by world-inspect.
"""
import unittest

from tests.test_chain import Chain, town_garden
from tests.wire import label, nat, record
from tests.bend import closure, declared


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
        out = closure(*("Abi", "List", "Form", "Plan", "World"))
        self.make("bench", out + [{"name": "Bench", "source": BENCH}], record())

    def got(self, name="got"):
        return {f["name"]: f["value"] for f in self.state("bench")["fields"]}[name]["value"]

    def say(self, text):
        return self.turn("bench", "receive", record(text=label(text), post=label("")), principal="glm")

    def test_a_fenced_block_is_the_source_field_under_the_same_bound(self):
        r = self.say("delvetalk bench check\n\n```obend\nedition ObjectiveBend 1\n```\n")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.got(), "edition ObjectiveBend 1")
        r = self.say("delvetalk bench check\n```obend\n" + "y" * 131073 + "\n```")
        self.assertEqual(r["receipt"]["outcome"]["clause"], "badValue", r)


class WorkshopSource(Chain):
    """The Workshop's `check` takes a `source` block by its form's bound, not the text default."""

    def create(self):
        self.make("workshop", closure("Workshop"), record())

    def say(self, text):
        return self.turn("workshop", "receive", record(text=label(text), post=label("")), principal="glm")

    def test_a_six_kib_block_is_checked_and_one_past_the_package_bound_refused_by_name(self):
        self.create()
        code = "edition ObjectiveBend 1\n" + ("def x() -> Nat:\n  0n\n" * 400)[:6000].rstrip("\n")
        r = self.say("delvetalk workshop check\nsource: <<BEND\n" + code + "\nBEND")
        self.assertEqual(r["status"], "admitted", r)
        r = self.say("delvetalk workshop check\nsource: <<BEND\n" + "x" * 140000 + "\nBEND")
        outcome = r["receipt"]["outcome"]
        self.assertEqual((outcome["class"], outcome["clause"]), ("badSpell", "badValue"), r)
        self.assertIn("source takes 1 to 131072 characters", outcome["reason"])
        forms = self.host.send(op="world-inspect", principal="glm", object="workshop", source=False)["forms"]
        self.assertIn("131072", str(forms))


class ExpectedForm(Chain):
    """A typeMismatch's `expected.form` is the card's declared form (the garden's `seed: text 1..80`),
    the bounds the spell path and the front's actions use, not the input type's default 0..1400."""

    def test_the_expected_form_carries_the_declared_bounds(self):
        town_garden(self.host.send)
        r = self.turn("garden", "plant", record(colour=label("amber"), seed=nat(3)), principal="glm")
        out = r["receipt"]["outcome"]
        self.assertEqual(out["class"], "typeMismatch", r)
        fields = {f["name"]: f["kind"] for f in out["expected"]["form"]["fields"]}
        self.assertEqual((fields["seed"]["min"], fields["seed"]["max"]), (1, 80), fields)


class ObjectFields(Chain):
    def setUp(self):
        super().setUp()
        source = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  got: String
def initial() -> State:
  {got: ""}
form walk:
  target: object 1..128
form optional:
  target: object 0..128
def walk(state: State, input: WalkInput, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {got: set input.target}
  0n
def optional(state: State, input: OptionalInput, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {got: set input.target}
  0n
def receive(state: State, input: {text: String, post: String}, context: Abi.Context) -> Activity<Nat>:
  0n
"""
        self.make("walker", closure(*("Abi", "List", "Form", "Plan", "World")) +
                  [{"name": "Walker", "source": source}], record())

    def test_object_form_checks_spells_direct_turns_bounds_and_optional_empty(self):
        for target in ("A0-:/._", "x" * 128):
            with self.subTest(target=target):
                for method, argument in (("walk", record(target=label(target))),
                                         ("receive", record(text=label("delvetalk walker walk / target: " + target), post=label("")))):
                    reply = self.turn("walker", method, argument)
                    self.assertEqual(reply["status"], "admitted", reply)
                    self.assertIn({"name": "got", "value": label(target)}, self.state("walker")["fields"])
        before = self.state("walker")
        for target in ("", "x" * 129, "a phrase", "x\ny", "x\ty", "x?", "é"):
            with self.subTest(target=target):
                reply = self.turn("walker", "walk", record(target=label(target)))
                self.assertEqual(reply["status"], "refused", reply)
                self.assertIn("target takes an object id", reply["receipt"]["outcome"]["reason"])
                self.assertEqual(self.state("walker"), before)
        reply = self.turn("walker", "receive", record(text=label("delvetalk walker optional"), post=label("")))
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertIn({"name": "got", "value": label("")}, self.state("walker")["fields"])
        inspected = self.host.send(op="world-inspect", principal="ember", object="walker", source=False)
        self.assertIn('"object"', str(inspected["forms"]).replace("'", '"'))


if __name__ == "__main__":
    unittest.main()
