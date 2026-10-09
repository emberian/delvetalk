"""The interpretation policy as an object, and Garden.receive falling through to it.

`interpret` suspends the turn; `world-interpretations` lists what waits and
`world-interpretation {id, reply}` settles it with the model's reply, which the host checks
against the offered form and Garden.plant's input before resuming the garden.
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
import ./Policy.obend as Policy
def sample() -> Policy.State:
  {owner: "ember", model: "claude-haiku", system: "You turn words into one spell.", lexicon: Lists.List::<Policy.Term>.cons({head: {word: "moth", meaning: "a seed"}, tail: Lists.List::<Policy.Term>.nil()}), examples: Lists.List::<Policy.Example>.cons({head: {utterance: "a silver fern", spell: "delvetalk garden-1 plant seed: a fern, colour: silver"}, tail: Lists.List::<Policy.Example>.nil()}), escalate: ""}
# Garden's plant form (Garden.planting), written out: Garden and Policy together exceed
# one closure's declaration capacity.
def plantForm(context: Abi.Context) -> Form.Form:
  {card: context.object, action: "plant", fields: Form.Fields.cons({head: {name: "colour", kind: Form.Kind.choice({options: Lists.append::<String>(Lists.append::<String>(Lists.append::<String>(Form.Names.nil(), "amber"), "violet"), "silver")})}, tail: Form.Fields.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 80n})}, tail: Form.Fields.nil()})})}
def forms(context: Abi.Context) -> Lists.List<Form.Form>:
  Lists.List::<Form.Form>.cons({head: plantForm(context), tail: Lists.List::<Form.Form>.nil()})
def plantPrompt(context: Abi.Context) -> String:
  Policy.prompt(sample(), forms(context), "plant me a moth")
def examples(n: Nat) -> Lists.List<Policy.Example>:
  match n:
    case 0: Lists.List::<Policy.Example>.nil()
    case 1+p: Lists.List::<Policy.Example>.cons({head: {utterance: "a silver fern that remembers yesterday", spell: "delvetalk garden-1 plant seed: a fern that remembers yesterday, colour: silver"}, tail: examples(p)})
def many(n: Nat, context: Abi.Context) -> Nat:
  textLength(Policy.prompt({owner: "ember", model: "m", system: "s", lexicon: Lists.List::<Policy.Term>.nil(), examples: examples(n), escalate: ""}, forms(context), "plant me a moth"))
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
    for m in closure("Policy"):
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
        for method in ("teach", "define", "receive"):
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
    def policy(self, name="policy"):
        """world-create with the whole state: a creator cannot import Policy, whose source
        declares a law ("a law belongs to the package's entry module; Policy is imported")."""
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                           modules=closure("Policy"), entry="initial",
                           seed=record(owner=label("ember"), model=label("claude-haiku"), system=label("S"),
                                       lexicon=nil(), examples=nil(), escalate=label("")))
        self.assertEqual(r["status"], "created", r)

    def card(self, name, principal="glm"):
        return self.turn(name, "receive", record(text=label(""), post=label(""), slot=label("")), principal=principal)["offers"][0]["text"]

    def test_teach_define_and_set_model_edit_the_policy_in_order(self):
        self.policy()
        for utterance, spell in (("a fern", "delvetalk garden-1 plant seed: fern, colour: silver"), ("a moth", "delvetalk garden-1 plant seed: moth, colour: amber")):
            reply = self.turn("policy", "teach", record(example=record(utterance=label(utterance), spell=label(spell))), principal="ember")
            self.assertEqual((reply["status"], reply["result"]["label"]), ("admitted", "taught"), reply)
        reply = self.turn("policy", "define", record(term=record(word=label("moth"), meaning=label("a seed"))), principal="ember")
        self.assertEqual(reply["status"], "admitted", reply)
        for spell in ("delvetalk policy set\nmodel: claude-sonnet", "delvetalk policy set\nescalate: claude-opus"):
            reply = self.turn("policy", "receive", record(text=label(spell), post=label(""), slot=label("")), principal="ember")
            self.assertEqual((reply["status"], reply["result"]["label"]), ("admitted", "done"), reply)
        card = self.card("policy")
        print("\n--- policy card ---\n" + card)
        self.assertIn("Model: claude-sonnet", card)
        self.assertIn("When unsure I escalate to claude-opus.", card)
        self.assertIn("delvetalk policy teach", card)
        self.assertIn("- moth: a seed", card)
        self.assertLess(card.index("Participant: a fern"), card.index("Participant: a moth"))

    def test_only_the_owner_teaches_and_the_law_refuses_what_bend_would_not(self):
        self.policy()
        example = record(example=record(utterance=label("x"), spell=label("y")))
        stranger = self.turn("policy", "teach", example, principal="glm")
        self.assertEqual(stranger["status"], "admitted", stranger)
        self.assertEqual(stranger["result"]["label"], "refused")
        self.assertIn("Only the policy's owner", stranger["result"]["payload"]["fields"][0]["value"]["value"])
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="policy")["version"], 0)
        # The same write proposed directly is judged by the law in the source.
        proposed = self.host.send(op="world-propose", principal="glm", identity="forged",
                                  roots=[{"object": "policy", "version": 0}],
                                  writes=[{"object": "policy", "edits": [record(
                                      model={"tag": "variant", "label": "set", "payload": record(value=label("evil"))},
                                      escalate={"tag": "variant", "label": "keep", "payload": record()},
                                      system={"tag": "variant", "label": "keep", "payload": record()},
                                      lexicon={"tag": "variant", "label": "keep", "payload": record()},
                                      examples={"tag": "variant", "label": "keep", "payload": record()})]}])
        self.assertEqual(proposed["status"], "refused", proposed)
        self.assertEqual((proposed["receipt"]["outcome"]["class"], proposed["receipt"]["outcome"].get("clause")), ("lawRefused", "owner"))

    def test_the_sixteenth_example_is_the_last(self):
        self.policy()
        for i in range(16):
            r = self.turn("policy", "teach", record(example=record(utterance=label("u%d" % i), spell=label("s"))), principal="ember")
            self.assertEqual(r["result"]["label"], "taught", r)
        over = self.turn("policy", "teach", record(example=record(utterance=label("u16"), spell=label("s"))), principal="ember")
        self.assertEqual(over["result"]["label"], "refused")

    def test_the_prompt_for_gardens_plant_form_contains_its_fields_and_bounds_verbatim(self):
        out = run("plantPrompt", context())
        self.assertEqual(out["status"], "finished", out)
        prompt = out["value"]["value"]
        print("\n--- prompt ---\n" + prompt)
        for needle in ("You turn words into one spell.\n", "Lexicon:\n- moth: a seed\n",
                       "Participant: a silver fern\nSpell:\ndelvetalk garden-1 plant seed: a fern, colour: silver\n",
                       "delvetalk garden-1 plant\n  colour: one of amber, violet, silver\n  seed: text of 1 to 80 characters\n",
                       "Answer with one spell in exactly that grammar, or with unclear: <what is missing>, and nothing else.",
                       "Participant: plant me a moth"):
            self.assertIn(needle, prompt)

    def test_a_policy_with_64_examples_renders_its_prompt_under_the_default_budget(self):
        """About 208,600 ticks (examples generated in the probe included): under the host's
        1,000,000-tick turn budget, over the 100,000 a bare `run` allows. A policy now holds
        at most sixteen."""
        out = run("many", nat(64), context(), limits={"ticks": "1000000"})
        print("\n  prompt with 64 examples: %s ticks, %s bytes" % (out.get("ticksUsed"), out.get("value", {}).get("value")))
        self.assertEqual(out["status"], "finished", out)

    # --- Garden.receive falls through to the policy ---------------------------------

    def garden(self, policy, confirm=True):
        self.make("garden", closure("Garden"), garden_seed(policy, confirm=confirm))

    def say(self, text, principal="glm", identity=None):
        return self.turn("garden", "receive", record(text=label(text), post=label("at://glm/p/1"), slot=label("")), principal=principal,
                         identity=identity)

    def interpret(self, reply):
        pending = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(len(pending), 1, pending)
        settled = self.host.send(op="world-interpretation", id=pending[0]["id"], reply=reply)
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = settled["resumed"]
        # A resumed turn's offers are retained on its receipt as {to, text}.
        resumed.setdefault("offers", [{"principal": o["to"], "text": o["text"]} for o in resumed["receipt"].get("offers", [])])
        return resumed

    def planting(self, colour="silver", seed="a fern that remembers"):
        return {"status": "replied", "model": "m", "json": {"method": "plant", "argument": {"colour": colour, "seed": seed}}}

    def pending(self):
        return [f["value"] for f in self.state("garden")["fields"] if f["name"] == "pending"][0]

    def test_without_a_policy_prose_is_a_one_line_refusal(self):
        self.garden("")
        reply = self.say("Could we plant a silver fern?")
        self.assertEqual(reply["offers"][0]["text"], "Not planted: The garden has no interpretation policy.\n")

    def test_a_typed_spell_never_consults_the_policy(self):
        self.policy()
        self.garden("policy")
        reply = self.say("delvetalk garden plant\nseed: a fern")
        self.assertIn("I still need: colour.", reply["offers"][0]["text"])

    def test_prose_suspends_and_lists_the_plant_form_for_the_model(self):
        self.policy()
        self.garden("policy")
        reply = self.say("Could we plant a silver fern that remembers?")
        self.assertEqual(reply["status"], "suspended", reply)
        [item] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(item["object"], "garden")
        self.assertEqual(item["utterance"], "Could we plant a silver fern that remembers?")
        self.assertEqual([o["action"] for o in item["offers"]], ["plant"])

    def test_with_confirm_on_the_garden_asks_first_then_yes_from_the_same_principal_plants(self):
        self.policy()
        self.garden("policy", confirm=True)
        self.say("Could we plant a silver fern that remembers?")
        asked = self.interpret(self.planting())
        self.assertEqual(asked["status"], "admitted", asked)
        self.assertEqual(asked["result"]["label"], "confirming")
        self.assertIn("Reply yes or correct it.", asked["offers"][0]["text"])
        # The confirm card is addressed: to the principal who spoke, and by name.
        self.assertTrue(asked["offers"][0]["text"].startswith("✾ THE NIGHT GARDEN\n\nglm, I understood this:\n"), asked["offers"][0])
        self.assertEqual(asked["offers"][0]["principal"], "glm", asked["offers"][0])
        self.assertNotEqual(self.pending()["items"], [])
        # Another principal's yes is not glm's: it is heard afresh (prose, so interpreted).
        other = self.say("yes", principal="kimik3")
        self.assertEqual(other["status"], "suspended", other)
        planted = self.say("  Yes \n")
        self.assertEqual(planted["status"], "admitted", planted["receipt"]["outcome"])
        self.assertEqual(planted["result"]["label"], "planted", planted)
        self.assertIn("Planted for glm: a silver bell, “a fern that remembers”.", planted["offers"][0]["text"])
        self.assertEqual(self.pending()["items"], [])

    def test_no_drops_the_waiting_proposal(self):
        self.policy()
        self.garden("policy", confirm=True)
        self.say("a violet moth please")
        self.interpret(self.planting("violet", "a moth"))
        dropped = self.say("no")
        self.assertEqual(dropped["result"]["label"], "cleared", dropped)
        self.assertEqual(self.pending()["items"], [])
        self.assertEqual([f["value"] for f in self.state("garden")["fields"] if f["name"] == "planted"][0], nat(0))

    def test_with_confirm_off_the_garden_plants_and_a_bad_colour_is_refused_by_name(self):
        self.policy()
        self.garden("policy", confirm=False)
        self.say("Could we plant a silver fern that remembers?")
        planted = self.interpret(self.planting())
        self.assertEqual(planted["result"]["label"], "planted", planted)
        self.say("a green one", identity="green")
        green = self.interpret(self.planting("green", "a fern"))
        self.assertEqual(green["result"]["label"], "refused")
        self.assertEqual(green["offers"][0]["text"], "Not planted: colour is one of: amber, violet, silver\n")

    def test_an_unclear_interpretation_offers_its_needs(self):
        self.policy()
        self.garden("policy")
        self.say("plant something")
        unclear = self.interpret({"status": "failed", "reason": "rate", "detail": "429"})
        self.assertEqual(unclear["status"], "admitted", unclear)
        self.assertIn("I did not quite get that. I still need: the model did not reply: rate", unclear["offers"][0]["text"])


if __name__ == "__main__":
    unittest.main()
