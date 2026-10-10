"""The garden fits the model's own words with Spell: a spell plants, `unclear: not addressed` is
silence, a miss is asked once more and then answered with what is still needed.

Evidence for FOUNDATION §6 (layer: objects).

The garden reads the model's own words (rehearsal findings 2 and 3, objects side), with
Card's interpretation default.

The host resumes an interpretation whose reply carries no `{method, argument}` json with
`replied {text}`; Card.fitting fits the text with Spell against the offered forms: a spell that
fits is a hit, `unclear: not addressed` is silence, and a spell that does not fit, any other
`unclear: <need>` or words that are no spell are a miss with what is missing. A miss is asked
once more, the utterance with "missing: <needs>" and the policy's escalate model; a second miss
offers the needs card to the speaker and a short copy to the policy's escalateTo principal.

Refuted by: a spell in the model's text not planting, `unclear: not addressed` offering a card, a
first miss not asked again with its needs, or a second miss not reaching the needs card and the
escalation copy.
"""
import unittest

from tests import test_chain, test_policy
from tests.test_objects import PROBE_HEAD_G, run_pure
from tests.test_turn_world import label, record

SPELL = "delvetalk garden plant / colour: silver / seed: a fern that remembers"

PROBE = PROBE_HEAD_G + """import ./Spell.obend as Spell
def back(text: String) -> String:
  match Card.fitting(text, Card.Forms.cons({head: Card.named(O.planting(), "garden"), tail: Card.Forms.nil()})):
    case hit(_): "spell"
    case miss(m): textConcat("miss ", Spell.joined(m.needs))
    case silent(_): "silent"
"""


class Classified(unittest.TestCase):
    def back(self, text):
        out = run_pure("Garden", "back", label(text), probe=PROBE)
        self.assertEqual(out["status"], "finished", out)
        return out["value"]["value"]

    def test_the_models_words_are_a_spell_a_need_or_silence(self):
        self.assertEqual(self.back(SPELL), "spell")
        self.assertEqual(self.back("Here you go:\n" + SPELL), "spell")
        self.assertEqual(self.back("unclear: colour"), "miss colour")
        self.assertEqual(self.back("  unclear:   seed  \nmore"), "miss seed")
        self.assertEqual(self.back("unclear: not addressed"), "silent")
        self.assertEqual(self.back("unclear:"), "silent")
        self.assertEqual(self.back("delvetalk garden plant / seed: a fern"), "miss colour")
        self.assertEqual(self.back("delvetalk garden water / seed: a fern"), "miss garden water is not offered")
        self.assertEqual(self.back("I think they are just chatting."), "miss ")


class Resumed(test_chain.Chain):
    policy = test_policy.PolicyObject.policy
    garden = test_policy.PolicyObject.garden
    say = test_policy.PolicyObject.say
    interpret = test_policy.PolicyObject.interpret

    def text(self, raw):
        return {"status": "replied", "json": None, "raw": raw, "model": "m"}

    def test_not_addressed_ends_the_turn_with_no_card(self):
        self.policy()
        self.garden("policy")
        self.say("What makes you think anyone needs a portal?")
        resumed = self.interpret(self.text("unclear: not addressed"))
        self.assertEqual((resumed["status"], resumed["result"]["label"], resumed["offers"]), ("admitted", "silent", []), resumed)

    def settle(self, raw):
        """Settle the one pending interpretation with the model's text; the resumed turn."""
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"], reply=self.text(raw))
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = settled["resumed"]
        return item, resumed

    def test_a_miss_is_asked_once_more_with_its_needs_and_a_hit_then_plants(self):
        self.policy(escalate="claude-opus")
        self.garden("policy", confirm=False)
        self.say("plant something pretty")
        first, again = self.settle("unclear: colour")
        self.assertEqual(again["status"], "suspended", again)
        [item] = self.host.send(op="world-interpretations")["pending"]
        self.assertNotEqual(item["id"], first["id"])
        self.assertEqual(item["utterance"], "plant something pretty\n\nmissing: colour")
        # The second attempt asks the policy's escalate model; the first asked its own.
        self.assertEqual((first["policy"]["model"], item["policy"]["model"]), ("claude-haiku", "claude-opus"), item)
        _, planted = self.settle(SPELL)
        self.assertEqual((planted["status"], planted["result"]["label"]), ("admitted", "planted"), planted)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_a_second_miss_offers_the_needs_card_and_a_copy_to_escalate_to(self):
        self.policy(escalate="claude-opus", escalate_to="did:plc:operator4keeper")
        self.garden("policy")
        self.say("plant something pretty")
        self.settle("unclear: colour")
        _, missed = self.settle("delvetalk garden plant / seed: something pretty")
        self.assertEqual((missed["status"], missed["result"]["label"]), ("admitted", "unclear"), missed)
        offers = [(o["to"], o["text"]) for o in missed["receipt"]["offers"]]
        self.assertEqual(offers, [("did:plc:operator4keeper", "glm said: plant something pretty; I could not fit it (garden).\n"),
                                  ("glm", "✾ THE NIGHT GARDEN\n\nI did not quite get that. I still need: colour.\n")])
        self.assertEqual(offers[-1], ("glm", "✾ THE NIGHT GARDEN\n\nI did not quite get that. I still need: colour.\n"))
        copy = [o["text"] for o in self.host.send(op="world-offers", principal="did:plc:operator4keeper")["offers"]]
        self.assertEqual(copy, ["glm said: plant something pretty; I could not fit it (garden).\n"])

    def test_without_escalate_to_a_second_miss_offers_only_the_needs_card(self):
        self.policy()
        self.garden("policy")
        self.say("plant something pretty")
        self.settle("unclear: colour")
        _, missed = self.settle("unclear: colour")
        self.assertEqual([o["to"] for o in missed["receipt"]["offers"]], ["glm"], missed)
        self.assertIn("I still need: colour.", missed["receipt"]["offers"][0]["text"])

    def test_with_the_default_policy_an_understood_planting_plants_and_the_receipt_answers(self):
        """Confirmation is per action: the policy's confirmFor (reprogram, amend, give, offer by
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
        self.assertEqual(taught["result"]["label"], "done", taught)
        self.garden("policy", confirm=False)
        self.say("Could we plant a silver fern that remembers?")
        _, asked = self.settle(SPELL)
        self.assertEqual(asked["result"]["label"], "confirming", asked)
        card = self.turn("policy", "receive", record(text=label(""), post=label("")), principal="glm")["offers"][0]["text"]
        self.assertIn("A card asks the speaker first before: reprogram, amend, give, offer, plant.\n", card)

    def test_words_that_are_no_spell_twice_end_with_no_card(self):
        self.policy()
        self.garden("policy")
        self.say("What makes you think anyone needs a portal?")
        self.settle("I think they are just chatting.")
        _, quiet = self.settle("Still chatting.")
        self.assertEqual((quiet["status"], quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("admitted", "silent", []), quiet)


if __name__ == "__main__":
    unittest.main()
