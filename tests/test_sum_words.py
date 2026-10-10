"""A text word for a sum of empty cases at the boundary (HOST-HANDOFF 5.52): where an argument from
outside (a direct `world-turn`, an interpretation's proposal) has a text where the method's input has a
closed sum whose every case has an empty payload, the text is taken as the case of that name, in a field,
a nested record or a list; a word naming no case is refused `typeMismatch` naming the cases (a direct
turn) or answered `unclear` naming them (a proposal). A sent or delivered argument is typed already and
is never read so.

Evidence for HOST-HANDOFF 5.52 (layer: host). Refuted by a case word that does not run the method with the
case, a word naming no case that is admitted or refused without the cases, or a proposal whose word
reaches the object as text.

    python3 -W error -m unittest tests.test_sum_words -v
"""
import unittest

from tests.test_reflection import Reflection, POLICY
from tests.test_turn_world import label, nat, record, declared


def variant(name, payload):
    return {"tag": "variant", "label": name, "payload": payload}

GARDEN = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./Form.obend as Form
import ./World.obend as World
record State:
  planted: String
sum Colour:
  amber: {}
  violet: {}
  silver: {}
record Planting:
  colour: Colour
  seed: String
def initial() -> State:
  {planted: ""}
def colourText(c: Colour) -> String:
  match c:
    case amber(_): "amber"
    case violet(_): "violet"
    case silver(_): "silver"
def colours(cs: Lists.List<Colour>) -> String:
  match cs:
    case nil(_): ""
    case cons(c): textConcat(colourText(c.head), textConcat(",", colours(c.tail)))
def put(text: String) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {planted: Plans.Edit.set({value: text})}))
  1n
def plant(state: State, input: Planting, context: Abi.Context) -> Activity<Nat>:
  put(textConcat(colourText(input.colour), textConcat(":", input.seed)))
def border(state: State, input: {bed: {colours: Lists.List<Colour>}}, context: Abi.Context) -> Activity<Nat>:
  put(colours(input.bed.colours))
def named(state: State, input: {name: String}, context: Abi.Context) -> Activity<Nat>:
  put(input.name)
def offered() -> Lists.List<Form.Form>:
  Lists.List::<Form.Form>.cons({head: {card: "garden", action: "plant", fields: Lists.List::<Form.Field>.nil()}, tail: Lists.List::<Form.Form>.nil()})
def ask(state: State, input: {utterance: String}, context: Abi.Context) -> Activity<Nat>:
  match world.interpret::<Planting>({utterance: input.utterance, offers: offered(), policy: {world: "", object: "policy"}, model: ""}):
    case proposal(p): put(textConcat(colourText(p.argument.colour), textConcat(":", p.argument.seed)))
    case unclear(_): put("unclear")
    case _: put("other")
""")


class SumWords(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("policy", POLICY, record(model=label("m"), system=label(""), examples=label("")))
        r = self.host.send(op="world-create", principal="ember", identity="mk-garden", object="garden",
                           modules=[{"name": "Garden", "source": GARDEN}], entry="initial", seed=record())
        self.assertEqual(r["status"], "created", r)

    def planted(self):
        return self.state("garden")["fields"][0]["value"]

    def test_a_word_is_the_case_of_that_name(self):
        r = self.turn("garden", "plant", record(colour=label("violet"), seed=label("rue")))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.planted(), label("violet:rue"))
        # The typed case is accepted as before.
        r = self.turn("garden", "plant", record(colour=variant("amber", record()), seed=label("moss")))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.planted(), label("amber:moss"))

    def test_words_in_a_nested_record_and_a_list(self):
        bed = record(colours={"tag": "list", "items": [label("silver"), label("amber")]})
        r = self.turn("garden", "border", record(bed=bed))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.planted(), label("silver,amber,"))

    def test_a_text_field_stays_text(self):
        r = self.turn("garden", "named", record(name=label("amber")))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.planted(), label("amber"))

    def test_a_word_naming_no_case_is_refused_naming_the_cases(self):
        r = self.turn("garden", "plant", record(colour=label("gold"), seed=label("rue")), identity="gold")
        first = r["receipt"]
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"]), ("refused", "typeMismatch"), r)
        self.assertIn("colour is one of: amber, violet, silver (not gold)", out["reason"])
        self.assertEqual(out["expected"]["cases"], {"at": "colour", "given": "gold", "cases": ["amber", "violet", "silver"]})
        bed = record(colours={"tag": "list", "items": [label("silver"), label("teal")]})
        r = self.turn("garden", "border", record(bed=bed))
        self.assertIn("bed.colours[1] is one of: amber, violet, silver (not teal)", r["receipt"]["outcome"]["reason"])
        self.assertEqual(self.planted(), label(""))
        # It binds: the identity's retry answers the same receipt.
        again = self.turn("garden", "plant", record(colour=label("gold"), seed=label("rue")), identity="gold")
        self.assertEqual(again["receipt"], first)
        self.reopen()
        self.assertEqual(self.planted(), label(""))

    def interpret(self, argument):
        r = self.turn("garden", "ask", record(utterance=label("plant something purple")))
        self.assertEqual(r["status"], "suspended", r)
        [item] = self.host.send(op="world-interpretations")["pending"]
        return self.host.send(op="world-interpretation", id=item["id"],
                              reply={"status": "replied", "model": "m", "json": {"method": "plant", "argument": argument}})

    # World.obend's proposal names its object (`proposal {object, method, argument}`, HOST-HANDOFF 5.64).
    def test_a_proposals_word_is_the_case(self):
        settled = self.interpret({"colour": "violet", "seed": "rue"})
        verdict = settled["receipt"]["outcome"]["verdict"]
        self.assertEqual(verdict["tag"], "proposal", settled)
        self.assertEqual(verdict["argument"], record(colour=variant("violet", record()), seed=label("rue")))
        self.assertEqual(settled["resumed"][0]["status"], "admitted", settled)
        self.assertEqual(self.planted(), label("violet:rue"))

    def test_a_proposals_word_naming_no_case_is_unclear_naming_the_cases(self):
        settled = self.interpret({"colour": "gold", "seed": "rue"})
        verdict = settled["receipt"]["outcome"]["verdict"]
        self.assertEqual(verdict, {"tag": "unclear", "needs": ["colour is one of: amber, violet, silver (not gold)"]}, settled)
        self.assertEqual(self.planted(), label("unclear"))


if __name__ == "__main__":
    unittest.main()
