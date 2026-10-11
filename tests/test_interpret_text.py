"""hob's one answer to prose handed on from the garden: a spell runs, `none` is silence, `ask` one
question over the plant spell, `card` the garden card; there is no second attempt.

Evidence for FOUNDATION §6 (layer: objects).

The garden reads no words (docs/METAPHYSICS.md §7.2): prose sent to it is handed on to the commonplace,
whose hob reads it against the garden's forms (docs/FLEX.md §2). The host resumes an interpretation whose
reply carries no `{method, argument}` json by fitting the words: a spell that fits is the host's
`proposal`; `ask: <question>` is `unclear {needs: [question]}` (so is a spell that does not fit,
its reason the need), `card` is `replied {text: "card"}`, and `none` is `unclear: not addressed`.
Card.hobNeeds / Card.hobSaid classify these: an ask, or none (not addressed, blank, or a
`model:` need, a model that could not be asked); the text "card" is the card, any other text none.
The commonplace answers `ask` with hob's fixed line naming only the offered fields the need names
(`hob: still needs colour; the spell is below.`, or `hob: not a spell as said; ...`: never the
model's words) and the plant spell with blanks, `card` with the garden card, `none` with silence, still one attempt.

Refuted by: a spell in the model's text not planting, `none` offering a card, an `ask` asked
again or answered without its question, or a second interpretation being requested.
"""
import unittest

from tests.host import as_owner

from tests import test_chain, test_policy
from tests.test_objects import run_pure
from tests.wire import label, record

SPELL = "delvetalk garden plant / colour: silver / seed: a fern that remembers"

PROBE = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./Form.obend as Form
import ./Card.obend as Card
import ./Text.obend as Text
# The garden's plant form (world/bodies/garden.obend) as the forms a card offers.
def forms() -> Lists.List<Form.Form>:
  Lists.List::<Form.Form>.cons({head: {card: "garden", action: "plant", fields: Form.Fields.cons({head: {name: "colour", kind: Form.Kind.choice({options: Lists.append::<String>(Lists.append::<String>(Lists.append::<String>(Form.Names.nil(), "amber"), "violet"), "silver")})}, tail: Form.Fields.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 80n})}, tail: Form.Fields.nil()})})}, tail: Lists.List::<Form.Form>.nil()})
def need(text: String) -> String:
  match Card.hobNeeds(Form.Names.cons({head: text, tail: Form.Names.nil()}), forms()):
    case ask(a): textConcat("ask ", Text.joined(a.needs))
    case none(_): "none"
    case card(_): "card"
    case said(_): "said"
def said(text: String) -> String:
  match Card.hobSaid(text):
    case ask(_): "ask"
    case none(_): "none"
    case card(_): "card"
    case said(_): "said"
"""


class Classified(unittest.TestCase):
    def back(self, method, text):
        out = run_pure("Card", method, label(text), probe=PROBE)
        self.assertEqual(out["status"], "finished", out)
        return out["value"]["value"]

    def test_a_need_is_an_ask_naming_only_the_cards_fields_unless_it_is_not_addressed_blank_or_a_model_failure(self):
        # The model's words are never kept: only the offered fields a need names (the owner's order).
        self.assertEqual(self.back("need", "which colour?"), "ask colour")
        self.assertEqual(self.back("need", "how many moths, since I reasoned so?"), "ask ")
        self.assertEqual(self.back("need", "not addressed"), "none")
        self.assertEqual(self.back("need", ""), "none")
        self.assertEqual(self.back("need", "model: timed out"), "none")

    def test_the_text_card_is_the_card_and_any_other_text_is_none(self):
        self.assertEqual(self.back("said", "card"), "card")
        self.assertEqual(self.back("said", "  card \n"), "card")
        self.assertEqual(self.back("said", "I think they are just chatting."), "none")
        self.assertEqual(self.back("said", ""), "none")


class Resumed(test_chain.Chain):
    policy = test_policy.PolicyObject.policy
    garden = test_policy.PolicyObject.garden
    say = test_policy.PolicyObject.say
    handed = test_policy.PolicyObject.handed
    things = test_policy.PolicyObject.things

    def text(self, raw):
        return {"status": "replied", "json": None, "raw": raw, "model": "m"}

    def settle(self, raw):
        """Settle the one pending interpretation with the model's text; the resumed turn."""
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"], reply=self.text(raw))
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return item, resumed

    def test_hobs_prose_is_its_line_beside_the_card_the_words_were_for(self):
        """hob's answer that is no spell and no prefix is `said` (the host's): its line stands above the garden's card,
        never inside it."""
        self.policy()
        self.garden()
        self.say("What makes you think anyone needs a portal?")
        _, said = self.settle("A portal here is a door; the garden has none of its own.")
        [card] = [o["text"] for o in said["receipt"]["offers"]]
        self.assertEqual((said["status"], said["result"]["label"]), ("admitted", "usage"), said)
        self.assertTrue(card.startswith("hob: A portal here is a door; the garden has none of its own.\n✾ THE NIGHT GARDEN\n"), card)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_an_ask_is_one_attempt_whose_question_stands_over_the_plant_spell(self):
        self.policy()
        self.garden()
        self.say("plant something pretty")
        first, asked = self.settle("ask: which colour?")
        # One attempt: nothing is asked again.
        self.assertEqual((asked["status"], asked["result"]["label"]), ("admitted", "unclear"), asked)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(first["policy"]["model"], "claude-haiku", first)
        [card] = [o["text"] for o in asked["receipt"]["offers"]]
        self.assertTrue(card.startswith("hob: still needs colour; the spell is below.\n"), card)
        self.assertIn("delvetalk garden plant\n", card)
        self.assertIn("colour: <amber, violet, silver>", card)
        self.assertEqual(self.things(), [])  # and nothing is made

    def test_a_spell_that_does_not_fit_is_hobs_question_with_the_reason(self):
        self.policy()
        self.garden()
        self.say("plant something pretty")
        _, missed = self.settle("delvetalk garden plant / seed: something pretty")
        self.assertEqual((missed["status"], missed["result"]["label"]), ("admitted", "unclear"), missed)
        [card] = [o["text"] for o in missed["receipt"]["offers"]]
        self.assertTrue(card.startswith("hob: "), card)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_an_ask_offers_only_the_question_card_to_the_speaker(self):
        self.policy()
        self.garden()
        self.say("plant something pretty")
        _, asked = self.settle("ask: which colour?")
        self.assertEqual([o["to"] for o in asked["receipt"]["offers"]], ["glm"], asked)

    def test_with_the_default_policy_an_understood_planting_plants_and_the_receipt_answers(self):
        """Confirmation is per action: the policy's confirmFor (reprogram, amend, offer by
        default) does not name plant, so the commonplace runs the garden's plant at once."""
        self.policy()
        self.garden()
        self.say("Could we plant a silver fern that remembers?")
        _, planted = self.settle(SPELL)
        self.assertEqual((planted["status"], planted["result"]["label"]), ("admitted", "passed"), planted)
        self.assertNotIn("Reply yes", planted["receipt"]["offers"][0]["text"])
        self.assertEqual(self.things(), ["garden/bell/1"])

    def test_the_policys_owner_makes_plant_ask_first(self):
        self.policy()
        taught = self.turn("policy", "receive", record(text=label("delvetalk policy confirm / action: plant / ask: yes"), post=label("")), principal="ember")
        self.assertEqual(taught["result"]["label"], "taught", taught)
        self.garden()
        self.say("Could we plant a silver fern that remembers?")
        _, asked = self.settle(SPELL)
        self.assertEqual((asked["status"], asked["result"]["label"]), ("admitted", "asked"), asked)
        [card] = [o["text"] for o in asked["receipt"]["offers"]]
        self.assertTrue(card.startswith("hob: that asks first; send it filled:\n\n    delvetalk garden plant\n"), card)
        card = self.turn("policy", "receive", record(text=label(""), post=label("")), principal="glm")["offers"][0]["text"]
        self.assertIn("A card asks the speaker first before: reprogram, amend, offer, plant.\n", card)
        self.assertEqual(self.things(), [])


if __name__ == "__main__":
    unittest.main()
