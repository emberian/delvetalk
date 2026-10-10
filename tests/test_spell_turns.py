"""The host reads spells (WHOLENESS §2, host day 2): a `receive {text, post}` to a card written in the
message dialect is parsed by the host (Host/Spell.lean); a spell that fits runs the method it names with
the typed argument (`inputOrigin.kind = "spell"`); one that does not is refused `badSpell` with its
clause, reason and hint; a spell missing fields, or prose, runs `receive` with the bare field lines in
`fields`; `?` is answered with the usage; a spell naming another card runs on it.

Evidence for HOST-HANDOFF 5.49 (layer: host). Refuted by a fitting spell that does not run its method, a
misfit admitted or refused without its clause, prose that does not reach `receive`, or a refusal whose
public projection hides the clause or hint.

    python3 -W error -m unittest tests.test_spell_turns -v
"""
import unittest

from tests.test_reflection import POLICY, Reflection
from tests.test_turn_world import label, nat, record, declared

GARDEN = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  planted: String
  origin: String
  heard: String
  fields: Nat
record Edits:
  planted: Plans.Edit<String, {}>
  origin: Plans.Edit<String, {}>
  heard: Plans.Edit<String, {}>
  fields: Plans.Edit<Nat, Nat>
sum Colour:
  amber: {}
  violet: {}
  silver: {}
record Binding:
  name: String
  value: String
def initial() -> State:
  {planted: "", origin: "", heard: "", fields: 0n}
def keep() -> Edits:
  {planted: Plans.Edit.keep({}), origin: Plans.Edit.keep({}), heard: Plans.Edit.keep({}), fields: Plans.Edit.keep({})}
def colourText(c: Colour) -> String:
  match c:
    case amber(_): "amber"
    case violet(_): "violet"
    case silver(_): "silver"
def plant(state: State, input: {colour: Colour, seed: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {planted: Plans.Edit.set({value: textConcat(colourText(input.colour), textConcat(":", input.seed))}), origin: Plans.Edit.set({value: textConcat(context.inputOrigin.kind, textConcat("|", context.inputOrigin.command))})}))
  1n
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {heard: Plans.Edit.set({value: input.text}), fields: Plans.Edit.set({value: Lists.length::<Binding>(input.fields)})}))
  2n
"""


class SpellTurns(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        for name in ("garden", "plot"):
            r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                               modules=[{"name": "Garden", "source": declared(GARDEN)}],
                               entry="initial", seed=record())
            self.assertEqual(r["status"], "created", r)

    def say(self, text, card="garden", principal="glm", identity=None):
        return self.turn(card, "receive", record(text=label(text), post=label("")), principal=principal, identity=identity)

    def field(self, name, card="garden"):
        return {f["name"]: f["value"] for f in self.state(card)["fields"]}[name]

    def test_a_fitting_spell_runs_its_method_with_the_typed_argument(self):
        r = self.say("delvetalk garden plant\ncolour: silver\nseed: fern")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.field("planted"), label("silver:fern"))
        self.assertEqual(self.field("origin"), label("spell|delvetalk garden plant"))
        self.reopen()
        self.assertEqual(self.field("planted"), label("silver:fern"))

    def test_the_one_line_form_and_a_bare_spell(self):
        self.assertEqual(self.say("delvetalk garden plant / colour: amber / seed: moss")["status"], "admitted")
        self.assertEqual(self.field("planted"), label("amber:moss"))
        self.assertEqual(self.say("colour: violet\nseed: rue")["result"], nat(1))
        self.assertEqual(self.field("planted"), label("violet:rue"))

    def test_misfits_are_refused_by_clause_with_reason_and_hint(self):
        cases = [("delvetalk garden plant\ncolour: gold\nseed: fern", "badValue", "colour is one of: amber, violet, silver"),
                 ("delvetalk garden plant\nsize: big", "unknownField", "Unknown field size"),
                 ("delvetalk garden plant\ncolour: amber\ncolour: amber\nseed: x", "duplicateField", "Duplicate field colour"),
                 ("delvetalk garden water", "noAction", "garden has no action water."),
                 ("delvetalk nowhere plant", "otherCard", "There is no card nowhere."),
                 ("delvetalk garden plant\nseed: <<END\nfern\n", "unclosedBlock", "the block <<END for seed is never closed by a line END")]
        for i, (text, clause, reason) in enumerate(cases):
            r = self.say(text, identity=f"bad{i}")
            out = r["receipt"]["outcome"]
            self.assertEqual((r["status"], out["class"], out["clause"], out["reason"]), ("refused", "badSpell", clause, reason), r)
            self.assertIn("delvetalk", out["hint"])
        self.assertIn("colour: gold", self.say("delvetalk garden plant\ncolour: gold\nseed: fern", identity="again")["receipt"]["outcome"]["hint"])
        # Another principal sees the public projection, with the clause and the hint.
        public = self.host.send(op="world-receipt", principal="kim", identity="bad0", of="glm")
        self.assertEqual((public.get("class"), public.get("clause")), ("badSpell", "badValue"), public)
        self.assertIn("hint", public)
        self.assertEqual(self.field("planted"), label(""))

    def test_missing_fields_and_prose_reach_receive_with_the_bare_fields(self):
        r = self.say("delvetalk garden plant\nseed: fern")
        self.assertEqual(r["result"], nat(2), r)
        self.assertEqual(self.field("fields"), nat(1))
        r = self.say("what a lovely garden")
        self.assertEqual(r["result"], nat(2), r)
        self.assertEqual((self.field("heard"), self.field("fields")), (label("what a lovely garden"), nat(0)))

    def test_usage_is_the_hosts_and_journals_nothing(self):
        r = self.say("delvetalk garden ?")
        self.assertEqual(r["status"], "usage", r)
        self.assertIn("delvetalk garden plant\ncolour: <amber, violet, silver>\nseed: <text, 0 to 1400 characters>", r["text"])

    def test_a_spell_naming_another_card_runs_on_it(self):
        r = self.say("delvetalk plot plant\ncolour: amber\nseed: oak", card="garden")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual((self.field("planted", "plot"), self.field("planted", "garden")), (label("amber:oak"), label("")))


LENSED = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./Form.obend as Form
import ./World.obend as World
record State:
  name: String
  size: Nat
  mood: String
  origin: String
record Edits:
  name: Plans.Edit<String, {}>
  size: Plans.Edit<Nat, Nat>
  mood: Plans.Edit<String, {}>
  origin: Plans.Edit<String, {}>
record Binding:
  name: String
  value: String
def initial() -> State:
  {name: "", size: 0n, mood: "", origin: ""}
def keep() -> Edits:
  {name: Plans.Edit.keep({}), size: Plans.Edit.keep({}), mood: Plans.Edit.keep({}), origin: Plans.Edit.keep({})}
def lenses() -> Lists.List<Form.Field>:
  Lists.List::<Form.Field>.cons({head: {name: "name", kind: Form.Kind.text({min: 1n, max: 12n})}, tail: Lists.List::<Form.Field>.cons({head: {name: "size", kind: Form.Kind.natural({min: 1n, max: 9n})}, tail: Lists.List::<Form.Field>.cons({head: {name: "mood", kind: Form.Kind.choice({options: Lists.List::<String>.cons({head: "calm", tail: Lists.List::<String>.cons({head: "wild", tail: Lists.List::<String>.nil()})})})}, tail: Lists.List::<Form.Field>.nil()})})})
def origin(context: Abi.Context) -> Plans.Edit<String, {}>:
  Plans.Edit.set({value: textConcat(context.inputOrigin.kind, textConcat("|", context.inputOrigin.command))})
def textEdit(field: String, value: String, context: Abi.Context) -> Edits:
  if field == "name" then extend(keep(), {name: Plans.Edit.set({value: value}), origin: origin(context)}) else extend(keep(), {mood: Plans.Edit.set({value: value}), origin: origin(context)})
def edit(field: String, value: Form.Value, context: Abi.Context) -> Edits:
  match value:
    case text(t): textEdit(field, t.value, context)
    case natural(n): extend(keep(), {size: Plans.Edit.set({value: n.value}), origin: origin(context)})
    case choice(c): textEdit(field, c.value, context)
def set(state: State, input: {field: String, value: Form.Value}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(edit(input.field, input.value, context))
  1n
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  2n
""")


class Lenses(Reflection):
    """Lens `set` through the host (WHOLENESS §2; second root decisions, 2): a card of the message
    dialect with a `set {field, value: Form.Value}` method and a pure `lenses() -> List<Form.Field>`
    takes `delvetalk <card> set` with one `<field>: <value>` line; the value is judged against the
    lens's kind and `set` runs with the typed value; `?` lists the lenses."""

    def setUp(self):
        super().setUp()
        self.open_library()
        r = self.host.send(op="world-create", principal="ember", identity="mk-lamp", object="lamp",
                           modules=[{"name": "Lamp", "source": LENSED}], entry="initial", seed=record())
        self.assertEqual(r["status"], "created", r)

    def say(self, text, identity=None):
        return self.turn("lamp", "receive", record(text=label(text), post=label("")), principal="glm", identity=identity)

    def field(self, name):
        return {f["name"]: f["value"] for f in self.state("lamp")["fields"]}[name]

    def test_set_runs_through_the_lens_typed(self):
        r = self.say("delvetalk lamp set\nname: Moth")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.field("name"), label("Moth"))
        self.assertEqual(self.field("origin"), label("spell|delvetalk lamp set"))
        self.assertEqual(self.say("delvetalk lamp set / size: 7")["status"], "admitted")
        self.assertEqual(self.field("size"), nat(7))
        self.assertEqual(self.say("delvetalk lamp set\nmood: wild")["status"], "admitted")
        self.assertEqual(self.field("mood"), label("wild"))

    def test_misfits_are_refused_by_clause(self):
        cases = [("delvetalk lamp set\nsize: 12", "badValue", "size"),
                 ("delvetalk lamp set\nmood: grim", "badValue", "mood is one of: calm, wild"),
                 ("delvetalk lamp set\ncolour: red", "unknownField", "Unknown field colour; set takes one of: name, size, mood"),
                 ("delvetalk lamp set\nname: a\nsize: 2", "unknownField", "set takes one field a spell, not name, size")]
        for i, (text, clause, reason) in enumerate(cases):
            out = self.say(text, identity=f"bad{i}")["receipt"]["outcome"]
            self.assertEqual((out["class"], out["clause"]), ("badSpell", clause), out)
            self.assertIn(reason, out["reason"])
            self.assertIn("delvetalk lamp set", out["hint"])
        self.assertEqual(self.field("size"), nat(0))

    def test_set_without_a_field_is_receive_and_usage_lists_the_lenses(self):
        self.assertEqual(self.say("delvetalk lamp set")["result"], nat(2))
        usage = self.say("delvetalk lamp ?")
        self.assertEqual(usage["status"], "usage", usage)
        self.assertIn("To change a field, reply (one field a spell):", usage["text"])
        self.assertIn("delvetalk lamp set\nmood: <calm, wild>", usage["text"])


INTERPRETING = (GARDEN + """record Planting:
  colour: Colour
  seed: String
def colourField() -> Form.Field:
  {name: "colour", kind: Form.Kind.choice({options: Lists.List::<String>.cons({head: "amber", tail: Lists.List::<String>.cons({head: "violet", tail: Lists.List::<String>.cons({head: "silver", tail: Lists.List::<String>.nil()})})})})}
def offered() -> Lists.List<Form.Form>:
  Lists.List::<Form.Form>.cons({head: {card: "garden", action: "plant", fields: Lists.List::<Form.Field>.cons({head: colourField(), tail: Lists.List::<Form.Field>.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 40n})}, tail: Lists.List::<Form.Field>.nil()})})}, tail: Lists.List::<Form.Form>.nil()})
def joined(needs: Lists.List<String>) -> String:
  match needs:
    case nil(_): ""
    case cons(c): textConcat("|", textConcat(c.head, joined(c.tail)))
def ask(state: State, input: {utterance: String}, context: Abi.Context) -> Activity<String>:
  match world.interpret::<Planting>({utterance: input.utterance, offers: offered(), policy: {world: "", object: "policy"}, model: ""}):
    case proposal(p):
      let written(_) = world.write(extend(keep(), {planted: Plans.Edit.set({value: textConcat(colourText(p.argument.colour), textConcat(":", p.argument.seed))})}))
      "proposal"
    case unclear(u): textConcat("unclear", joined(u.needs))
    case replied(r): textConcat("replied|", r.text)
    case _: "other"
""").replace("import ./World.obend as World", "import ./Form.obend as Form\nimport ./World.obend as World")


class Interpreted(Reflection):
    """The model's text fitted as a spell against the offered forms (WHOLENESS §2, "Interpretation"):
    a fitting spell is the form's proposal, a misfit or a spell missing fields is `unclear` naming why,
    a bare field line naming an offered field is that form's spell, and prose is `replied`."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("policy", POLICY, record(model=label("m"), system=label(""), examples=label("")))
        r = self.host.send(op="world-create", principal="ember", identity="mk-garden", object="garden",
                           modules=[{"name": "Garden", "source": declared(INTERPRETING)}], entry="initial", seed=record())
        self.assertEqual(r["status"], "created", r)

    def interpret(self, raw):
        self.n = getattr(self, "n", 0) + 1
        r = self.turn("garden", "ask", record(utterance=label("plant something")), identity=f"ask{self.n}")
        self.assertEqual(r["status"], "suspended", r)
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"],
                                 reply={"status": "replied", "model": "m", "json": None, "raw": raw})
        return settled["receipt"]["outcome"]["verdict"], settled["resumed"][0]["result"]

    def test_a_fitting_spell_is_a_proposal(self):
        verdict, result = self.interpret("Sure.\ndelvetalk garden plant\ncolour: violet\nseed: rue")
        self.assertEqual((verdict["tag"], verdict["method"]), ("proposal", "plant"), verdict)
        self.assertEqual(result, label("proposal"))
        self.assertEqual({f["name"]: f["value"] for f in self.state("garden")["fields"]}["planted"], label("violet:rue"))

    def test_bare_fields_naming_an_offered_field_are_its_spell(self):
        verdict, _ = self.interpret("colour: amber\nseed: moss")
        self.assertEqual(verdict["tag"], "proposal", verdict)

    def test_misfits_and_missing_fields_are_unclear(self):
        self.assertEqual(self.interpret("delvetalk garden plant\ncolour: gold\nseed: rue")[0],
                         {"tag": "unclear", "needs": ["colour is one of: amber, violet, silver"]})
        self.assertEqual(self.interpret("delvetalk garden plant\ncolour: amber")[0], {"tag": "unclear", "needs": ["seed"]})
        self.assertEqual(self.interpret("delvetalk garden water")[0],
                         {"tag": "unclear", "needs": ["garden water is not one of the offered actions"]})

    def test_prose_is_replied(self):
        verdict, result = self.interpret("I could not tell what you meant.")
        self.assertEqual(verdict, {"tag": "replied", "text": "I could not tell what you meant."})
        self.assertEqual(result, label("replied|I could not tell what you meant."))


if __name__ == "__main__":
    unittest.main()
