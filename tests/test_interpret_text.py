"""The garden reads the model's own words (rehearsal findings 2 and 3, objects side).

The host resumes an interpretation whose reply carries no `{method, argument}` json with
`replied {text}`; the garden fits the text with Spell against its plant form, takes
`unclear: <need>` as what is missing, and ends the turn with no card at all for
`unclear: not addressed` (prose that names no card) or anything else.

Refuted by: a spell in the model's text not planting, `unclear: not addressed` offering a card, or a
named need not reaching the needs card."""
import unittest

from tests import test_chain, test_policy
from tests.test_objects import PROBE_HEAD_G, run_pure
from tests.test_turn_world import label

SPELL = "delvetalk garden plant / colour: silver / seed: a fern that remembers"

PROBE = PROBE_HEAD_G + """def back(text: String) -> String:
  match O.heardBack(text):
    case spell(_): "spell"
    case unclear(u): textConcat("unclear ", u.need)
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
        self.assertEqual(self.back("unclear: colour"), "unclear colour")
        self.assertEqual(self.back("  unclear:   seed  \nmore"), "unclear seed")
        self.assertEqual(self.back("unclear: not addressed"), "silent")
        self.assertEqual(self.back("unclear:"), "silent")
        self.assertEqual(self.back("I think they are just chatting."), "silent")


class Resumed(test_chain.Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None
    policy = test_policy.PolicyObject.policy
    garden = test_policy.PolicyObject.garden
    say = test_policy.PolicyObject.say
    interpret = test_policy.PolicyObject.interpret

    def text(self, raw):
        return {"status": "replied", "json": None, "raw": raw, "model": "m"}

    def test_a_spell_in_the_models_text_plants(self):
        self.policy()
        self.garden("policy", confirm=False)
        self.say("Could we plant a silver fern that remembers?")
        resumed = self.interpret(self.text(SPELL))
        self.assertEqual(resumed["result"]["label"], "planted", resumed)

    def test_not_addressed_ends_the_turn_with_no_card(self):
        self.policy()
        self.garden("policy")
        self.say("What makes you think anyone needs a portal?")
        resumed = self.interpret(self.text("unclear: not addressed"))
        self.assertEqual((resumed["status"], resumed["result"]["label"], resumed["offers"]), ("admitted", "silent", []), resumed)

    def test_a_named_need_reaches_the_needs_card(self):
        self.policy()
        self.garden("policy")
        self.say("plant something pretty")
        resumed = self.interpret(self.text("unclear: colour"))
        self.assertIn("I still need: colour.", resumed["offers"][0]["text"])


if __name__ == "__main__":
    unittest.main()
