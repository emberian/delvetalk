"""hob's one answer to prose at the commonplace: a spell runs, `none` is silence, `ask` one question
naming the fields it needs; there is no second attempt.

Evidence for FOUNDATION §6 (layer: objects).

The host reads prose at the commonplace with hob against its forms and its doors' (HOST-HANDOFF 5.163). The host resumes an
interpretation whose reply carries no `{method, argument}` json by fitting the words: a spell that
fits is the host's `proposal`; `ask: <question>` is `unclear {needs: [question]}` (so is a spell that
does not fit, its reason the need), and `none` is `unclear: not addressed`. The host classifies these
(HOST-HANDOFF 5.163): an ask, or none (not addressed, blank, or a `model:` need, a model that could not be asked).
The host answers `ask` with hob's fixed line naming only the offered fields the need names, with the
spells that take them (`hob: that still needs colour; send it filled:`, never the model's words), and
`none` with silence, still one attempt (docs/OVERHAUL.md §2.7: the commonplace's words are the host's).

Refuted by: a spell in the model's text not planting, `none` offering a card, an `ask` asked
again or answered without its question, or a second interpretation being requested.
"""
import json
import unittest

from tests.host import as_owner

from tests import test_chain, test_policy
from tests.wire import label, record

SPELL = "delvetalk garden plant / colour: silver / seed: a fern that remembers"

class Resumed(test_chain.Chain):
    policy = test_policy.PolicyObject.policy
    garden = test_policy.PolicyObject.garden
    say = test_policy.PolicyObject.say
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

    def test_hob_states_nothing_a_say_is_silence(self):
        """hob has no `say:` (docs/OVERHAUL.md §2; 69275, a `say:` that stated a falsehood and was believed): an
        answer so headed is prose with no spell, silence, and no line of hob's stands beside the garden's card."""
        self.policy()
        self.garden()
        self.say("What makes you think anyone needs a portal?")
        item, said = self.settle("say: A portal here is a door; the garden has none of its own.")
        self.assertNotIn("hob: A portal", json.dumps(said))
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_an_ask_is_one_attempt_whose_question_stands_over_the_doors(self):
        self.policy()
        self.garden()
        self.say("plant something pretty")
        first, asked = self.settle("ask: which colour?")
        # One attempt: nothing is asked again.
        self.assertEqual(asked["receipt"]["outcome"]["tag"], "admitted", asked)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(first["policy"]["model"], "claude-haiku", first)
        [card] = [o["text"] for o in asked["receipt"]["offers"]]
        self.assertTrue(card.startswith("hob: that still needs colour; send it filled:\n\n    delvetalk garden plant\n    colour: "), card)
        self.assertEqual(self.things(), [])  # and nothing is made

    def test_a_spell_that_does_not_fit_is_hobs_question_with_the_reason(self):
        self.policy()
        self.garden()
        self.say("plant something pretty")
        _, missed = self.settle("delvetalk garden plant / seed: something pretty")
        self.assertEqual(missed["receipt"]["outcome"]["tag"], "admitted", missed)
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
        self.assertEqual(planted["receipt"]["outcome"]["tag"], "admitted", planted)
        self.assertNotIn("Reply yes", planted["receipt"]["offers"][0]["text"])
        self.assertEqual(self.things(), ["garden/bell/1"])

    def test_the_policys_owner_makes_plant_ask_first(self):
        self.policy()
        changed = self.turn("policy", "receive", record(text=label("delvetalk policy confirm / action: plant / ask: yes"), post=label("")), principal="ember")
        self.assertEqual(changed["result"]["label"], "changed", changed)
        self.garden()
        self.say("Could we plant a silver fern that remembers?")
        _, asked = self.settle(SPELL)
        self.assertEqual(asked["receipt"]["outcome"]["tag"], "admitted", asked)
        [card] = [o["text"] for o in asked["receipt"]["offers"]]
        self.assertTrue(card.startswith("hob: that asks first; send it filled:\n\n    delvetalk garden plant\n"), card)
        card = self.turn("policy", "receive", record(text=label(""), post=label("")), principal="glm")["offers"][0]["text"]
        self.assertIn("runs at once, except: reprogram, amend, offer, plant, which ask the speaker first.\n", card)
        self.assertEqual(self.things(), [])


if __name__ == "__main__":
    unittest.main()
