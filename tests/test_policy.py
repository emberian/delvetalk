"""The interpretation policy as an object, and Garden.receive falling through to it.

The host does not implement `interpret` yet: a turn that performs it is refused as

    {'class': 'evaluation', 'reason': 'plan not supported: interpret'}

so the fall-through steps are expected failures and flip when it lands.
"""
import unittest

from tests.test_chain import Chain, boolean, garden_seed, nil, reference
from tests.test_objects import check, closure, compile_job, computation, row_names
from tests.test_places import listing
from tests.test_turn_world import label, nat, record

PROBE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Garden.obend as Garden
import ./Policy.obend as Policy
def sample() -> Policy.State:
  {model: "claude-haiku", system: "You turn words into one spell.", lexicon: Lists.List::<Policy.Term>.cons({head: {word: "moth", meaning: "a seed"}, tail: Lists.List::<Policy.Term>.nil()}), examples: Lists.List::<Policy.Example>.cons({head: {utterance: "a silver fern", spell: "delvetalk garden-1 plant, seed: a fern, colour: silver"}, tail: Lists.List::<Policy.Example>.nil()}), confirm: true, escalate: ""}
def forms(context: Abi.Context) -> Lists.List<Form.Form>:
  Lists.List::<Form.Form>.cons({head: Garden.plantForm(context), tail: Lists.List::<Form.Form>.nil()})
def plantPrompt(context: Abi.Context) -> String:
  Policy.prompt(sample(), forms(context), "plant me a moth")
def examples(n: Nat) -> Lists.List<Policy.Example>:
  match n:
    case 0: Lists.List::<Policy.Example>.nil()
    case 1+p: Lists.List::<Policy.Example>.cons({head: {utterance: "a silver fern that remembers yesterday", spell: "delvetalk garden-1 plant, seed: a fern that remembers yesterday, colour: silver"}, tail: examples(p)})
def many(n: Nat, context: Abi.Context) -> Nat:
  textLength(Policy.prompt({model: "m", system: "s", lexicon: Lists.List::<Policy.Term>.nil(), examples: examples(n), confirm: true, escalate: ""}, forms(context), "plant me a moth"))
"""


def context(card="garden-1"):
    text = lambda v: {"tag": "label", "value": v}
    return record(world=text(""), object=text(card), principal=text("glm"), caller=text(""), intent=text("probe"),
                  height={"tag": "natural", "value": "0"}, inputOrigin=record(
        kind=text("request"), object=text(""), command=text(""), program=text(""),
        immediatelyPrevious=boolean(False)))


def run(entry, *arguments, limits=None):
    modules = []
    seen = set()
    for m in closure("Garden") + closure("Policy"):
        if m["name"] not in seen:
            seen.add(m["name"])
            modules.append(m)
    modules.append({"name": "Probe", "source": PROBE})
    compiled = compile_job(modules, entry)
    assert compiled["status"] == "compiled", compiled
    request = {"op": "run", "artifact": compiled["artifact"], "arguments": list(arguments)}
    if limits:
        request["limits"] = limits
    return check(request)


class Types(unittest.TestCase):
    def test_every_method_is_an_activity_over_the_plan_library(self):
        for method in ("teach", "define", "setModel", "describe"):
            with self.subTest(method=method):
                reply = compile_job(closure("Policy"), method)
                self.assertEqual(reply["status"], "compiled", reply)
                self.assertEqual(row_names(computation(reply["artifact"]["type"])["plan"]["row"])[:3], ["view", "write", "call"])

    def test_the_plan_gained_inspect_check_and_the_new_interpret_and_offer(self):
        plan_row = row_names(computation(compile_job(closure("Policy"), "teach")["artifact"]["type"])["plan"]["row"])
        for name in ("interpret", "offer", "reprogram", "inspect", "check"):
            self.assertIn(name, plan_row)
        response_row = row_names(computation(compile_job(closure("Policy"), "teach")["artifact"]["type"])["response"]["row"])
        for name in ("inspected", "checked", "proposal", "unclear"):
            self.assertIn(name, response_row)


class PolicyObject(Chain):
    def policy(self, confirm=True, name="policy"):
        self.make(name, closure("Policy"), record(model=label("claude-haiku"), system=label("S"),
                                                  confirm=boolean(confirm), escalate=label("")))

    def test_teach_define_and_set_model_edit_the_policy_in_order(self):
        self.policy()
        for utterance, spell in (("a fern", "delvetalk garden-1 plant, seed: fern, colour: silver"), ("a moth", "delvetalk garden-1 plant, seed: moth, colour: amber")):
            reply = self.turn("policy", "teach", record(example=record(utterance=label(utterance), spell=label(spell))), principal="ember")
            self.assertEqual(reply["status"], "admitted", reply)
        reply = self.turn("policy", "define", record(term=record(word=label("moth"), meaning=label("a seed"))), principal="ember")
        self.assertEqual(reply["status"], "admitted", reply)
        reply = self.turn("policy", "setModel", record(model=label("claude-sonnet"), escalate=label("claude-opus")), principal="ember")
        self.assertEqual(reply["status"], "admitted", reply)
        card = self.turn("policy", "describe", principal="glm")["offers"][0]["text"]
        print("\n--- policy card ---\n" + card)
        self.assertIn("Model: claude-sonnet", card)
        self.assertIn("I ask before acting on what I understood.", card)
        self.assertIn("When unsure I escalate to claude-opus.", card)
        self.assertIn("delvetalk policy teach", card)
        self.assertIn("- moth: a seed", card)
        self.assertLess(card.index("Participant: a fern"), card.index("Participant: a moth"))

    def test_the_prompt_for_gardens_plant_form_contains_its_fields_and_bounds_verbatim(self):
        out = run("plantPrompt", context())
        self.assertEqual(out["status"], "finished", out)
        prompt = out["value"]["value"]
        print("\n--- prompt ---\n" + prompt)
        for needle in ("You turn words into one spell.\n", "Lexicon:\n- moth: a seed\n",
                       "Participant: a silver fern\nSpell:\ndelvetalk garden-1 plant, seed: a fern, colour: silver\n",
                       "delvetalk garden-1 plant\n  colour: one of amber, violet, silver\n  seed: text of 1 to 80 characters\n",
                       "Answer with one spell in exactly that grammar, or with unclear: <what is missing>, and nothing else.",
                       "Participant: plant me a moth"):
            self.assertIn(needle, prompt)

    def test_a_policy_with_64_examples_renders_its_prompt_under_the_default_budget(self):
        """About 208,600 ticks (examples generated in the probe included): under the host's
        1,000,000-tick turn budget, over the 100,000 a bare `run` allows."""
        out = run("many", nat(64), context(), limits={"ticks": "1000000"})
        print("\n  prompt with 64 examples: %s ticks, %s bytes" % (out.get("ticksUsed"), out.get("value", {}).get("value")))
        self.assertEqual(out["status"], "finished", out)
        self.assertEqual(out["value"]["value"], "9299")
        self.assertLess(out["ticksUsed"], 1000000)

    # --- Garden.receive falls through to the policy ---------------------------------

    def garden(self, policy):
        self.make("garden", closure("Garden"), garden_seed(policy))

    def say(self, text):
        return self.turn("garden", "receive", record(text=label(text), post=label("at://glm/p/1")), principal="glm")

    def test_without_a_policy_prose_is_a_one_line_refusal(self):
        self.garden("")
        reply = self.say("Could we plant a silver fern?")
        self.assertEqual(reply["offers"][0]["text"], "Not planted: The garden has no interpretation policy.\n")

    def test_a_typed_spell_never_consults_the_policy(self):
        self.policy()
        self.garden("policy")
        reply = self.say("delvetalk garden plant\nseed: a fern")
        self.assertIn("I still need: colour.", reply["offers"][0]["text"])

    @unittest.expectedFailure
    def test_prose_is_interpreted_and_with_confirm_on_the_garden_asks_first(self):
        self.policy(confirm=True)
        self.garden("policy")
        reply = self.say("Could we plant a silver fern that remembers?")
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertIn("Reply yes or correct it.", reply["offers"][0]["text"])

    @unittest.expectedFailure
    def test_prose_is_interpreted_and_with_confirm_off_the_garden_plants(self):
        self.policy(confirm=False)
        self.garden("policy")
        reply = self.say("Could we plant a silver fern that remembers?")
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertEqual(reply["result"]["label"], "planted")

    @unittest.expectedFailure
    def test_an_unclear_interpretation_offers_its_needs(self):
        self.policy()
        self.garden("policy")
        reply = self.say("plant something")
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertIn("I still need:", reply["offers"][0]["text"])


if __name__ == "__main__":
    unittest.main()
