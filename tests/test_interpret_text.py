"""The garden fits the model's own words with Spell: a spell plants, hob's `none` is silence, its
`ask` one question over the plant spell, its `card` the garden card; there is no second attempt.

Evidence for FOUNDATION §6 (layer: objects).

The garden reads hob's one answer (docs/FLEX.md §2). The host resumes an interpretation whose
reply carries no `{method, argument}` json by fitting the words: a spell that fits is the host's
`proposal`; `ask: <question>` is `unclear {needs: [question]}` (so is a spell that does not fit,
its reason the need), `card` is `replied {text: "card"}`, and `none` is `unclear: not addressed`.
Card.hobNeeds / Card.hobSaid classify these: a question, or none (not addressed, blank, or a
`model:` need, a model that could not be asked); the text "card" is the card, any other text none.
The garden answers `ask` with `hob: {question}` and the plant spell with blanks (and, when the
policy names `escalateTo`, a short copy to that principal), `card` with the garden card, `none`
with silence, still one attempt.

Refuted by: a spell in the model's text not planting, `none` offering a card, an `ask` asked
again or answered without its question, or a second interpretation being requested.
"""
import unittest

from tests.host import as_owner

from tests import test_chain, test_policy
from tests.test_objects import PROBE_HEAD_G, run_pure
from tests.test_replay import rows
from tests.test_turn_world import label, record

SPELL = "delvetalk garden plant / colour: silver / seed: a fern that remembers"

PROBE = PROBE_HEAD_G + """import ./Text.obend as Text
def need(text: String) -> String:
  match Card.hobNeeds(Card.one(text)):
    case ask(a): textConcat("ask ", a.question)
    case none(_): "none"
    case card(_): "card"
def said(text: String) -> String:
  match Card.hobSaid(text):
    case ask(_): "ask"
    case none(_): "none"
    case card(_): "card"
"""


class Classified(unittest.TestCase):
    def back(self, method, text):
        out = run_pure("Garden", method, label(text), probe=PROBE)
        self.assertEqual(out["status"], "finished", out)
        return out["value"]["value"]

    def test_a_need_is_a_question_unless_it_is_not_addressed_blank_or_a_model_failure(self):
        self.assertEqual(self.back("need", "which colour?"), "ask which colour?")
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
    interpret = test_policy.PolicyObject.interpret
    pending = test_policy.PolicyObject.pending

    def text(self, raw):
        return {"status": "replied", "json": None, "raw": raw, "model": "m"}

    def settle(self, raw):
        """Settle the one pending interpretation with the model's text; the resumed turn."""
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"], reply=self.text(raw))
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return item, resumed

    def test_none_ends_the_turn_with_no_card(self):
        self.policy()
        self.garden("policy")
        self.say("What makes you think anyone needs a portal?")
        _, resumed = self.settle("none")
        self.assertEqual((resumed["status"], resumed["result"]["label"], resumed["receipt"].get("offers", [])), ("admitted", "silent", []), resumed)

    def test_words_that_are_no_spell_are_none_and_end_with_no_card(self):
        self.policy()
        self.garden("policy")
        self.say("What makes you think anyone needs a portal?")
        _, quiet = self.settle("I think they are just chatting.")
        self.assertEqual((quiet["status"], quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("admitted", "silent", []), quiet)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_an_ask_is_one_attempt_whose_question_stands_over_the_plant_spell(self):
        self.policy(escalate="claude-opus")
        self.garden("policy", confirm=False)
        self.say("plant something pretty")
        first, asked = self.settle("ask: which colour?")
        # One attempt: nothing is asked again, and the policy's escalate model is not tried.
        self.assertEqual((asked["status"], asked["result"]["label"]), ("admitted", "unclear"), asked)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(first["policy"]["model"], "claude-haiku", first)
        [card] = [o["text"] for o in asked["receipt"]["offers"]]
        self.assertTrue(card.startswith("hob: which colour?\n"), card)
        self.assertIn("delvetalk garden plant\n", card)
        self.assertIn("colour: <amber, violet, silver>", card)

    def test_a_spell_that_does_not_fit_is_hobs_question_with_the_reason(self):
        self.policy()
        self.garden("policy")
        self.say("plant something pretty")
        _, missed = self.settle("delvetalk garden plant / seed: something pretty")
        self.assertEqual((missed["status"], missed["result"]["label"]), ("admitted", "unclear"), missed)
        [card] = [o["text"] for o in missed["receipt"]["offers"]]
        self.assertTrue(card.startswith("hob: "), card)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_card_offers_the_gardens_card(self):
        self.policy()
        self.garden("policy")
        self.say("what is this place?")
        _, carded = self.settle("card")
        [card] = [o["text"] for o in carded["receipt"]["offers"]]
        self.assertTrue(card.startswith("✾ THE NIGHT GARDEN"), card)

    def test_an_ask_copies_the_question_to_escalate_to(self):
        self.policy(escalate_to="did:plc:operator4keeper")
        self.garden("policy")
        self.say("plant something pretty")
        _, asked = self.settle("ask: which colour?")
        offers = [(o["to"], o["text"]) for o in asked["receipt"]["offers"]]
        self.assertEqual(offers[0], ("did:plc:operator4keeper", "glm said: plant something pretty; hob asked: which colour? (garden).\n"))
        self.assertEqual([to for to, _ in offers], ["did:plc:operator4keeper", "glm"])
        copy = [o["text"] for o in self.host.send(op="world-offers", principal="did:plc:operator4keeper")["offers"]]
        self.assertEqual(copy, ["glm said: plant something pretty; hob asked: which colour? (garden).\n"])

    def test_without_escalate_to_an_ask_offers_only_the_question_card(self):
        self.policy()
        self.garden("policy")
        self.say("plant something pretty")
        _, asked = self.settle("ask: which colour?")
        self.assertEqual([o["to"] for o in asked["receipt"]["offers"]], ["glm"], asked)

    def test_hobs_none_leaves_a_held_planting_held(self):
        self.policy()
        self.garden("policy")
        held = self.turn("garden", "receive", record(text=label("delvetalk garden plant\nseed: a fern"), post=label("at://x/h")), principal="glm")
        self.assertIn("I still need: colour.", held["offers"][0]["text"])
        before = self.pending()
        self.assertEqual(len(rows(before)), 1, before)
        self.say("what a lovely evening")
        self.settle("none")
        self.assertEqual(self.pending(), before)

    def test_a_planting_after_the_models_spell_plants(self):
        self.policy(escalate="claude-opus")
        self.garden("policy", confirm=False)
        self.say("plant something pretty")
        _, planted = self.settle(SPELL)
        self.assertEqual((planted["status"], planted["result"]["label"]), ("admitted", "planted"), planted)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_with_the_default_policy_an_understood_planting_plants_and_the_receipt_answers(self):
        """Confirmation is per action: the policy's confirmFor (reprogram, amend, offer by
        default) does not name plant, and a garden with an empty confirmFor asks nobody."""
        self.policy()
        self.garden("policy", confirm=False)
        self.say("Could we plant a silver fern that remembers?")
        _, planted = self.settle(SPELL)
        self.assertEqual((planted["status"], planted["result"]["label"]), ("admitted", "planted"), planted)
        self.assertNotIn("Reply yes", planted["receipt"]["offers"][0]["text"])

    def test_the_policys_owner_makes_plant_ask_first(self):
        self.policy()
        taught = self.turn("policy", "receive", record(text=label("delvetalk policy confirm / action: plant / ask: yes"), post=label("")), principal="ember")
        self.assertEqual(taught["result"]["label"], "taught", taught)
        self.garden("policy", confirm=False)
        self.say("Could we plant a silver fern that remembers?")
        _, asked = self.settle(SPELL)
        self.assertEqual(asked["result"]["label"], "confirming", asked)
        card = self.turn("policy", "receive", record(text=label(""), post=label("")), principal="glm")["offers"][0]["text"]
        self.assertIn("A card asks the speaker first before: reprogram, amend, offer, plant.\n", card)


if __name__ == "__main__":
    unittest.main()
