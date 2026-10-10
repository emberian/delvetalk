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

from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record

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
                               modules=[{"name": "Garden", "source": GARDEN}],
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


if __name__ == "__main__":
    unittest.main()
