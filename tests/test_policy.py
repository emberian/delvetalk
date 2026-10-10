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
  {owner: "ember", model: "claude-haiku", system: "You turn words into one spell.", lexicon: Lists.List::<Policy.Term>.cons({head: {word: "moth", meaning: "a seed"}, tail: Lists.List::<Policy.Term>.nil()}), examples: Lists.List::<Policy.Example>.cons({head: {utterance: "a silver fern", spell: "delvetalk garden-1 plant seed: a fern, colour: silver"}, tail: Lists.List::<Policy.Example>.nil()}), escalate: "", escalateTo: "", macros: Lists.List::<Policy.Macro>.nil(), confirmFor: Lists.List::<String>.nil()}
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
  textLength(Policy.prompt({owner: "ember", model: "m", system: "s", lexicon: Lists.List::<Policy.Term>.nil(), examples: examples(n), escalate: "", escalateTo: "", macros: Lists.List::<Policy.Macro>.nil(), confirmFor: Lists.List::<String>.nil()}, forms(context), "plant me a moth"))
"""


def context(card="garden-1"):
    text = lambda v: {"tag": "label", "value": v}
    return record(world=text(""), object=text(card), principal=text("glm"), handle=text(""), caller=text(""), intent=text("probe"),
                  height={"tag": "natural", "value": "0"}, clock={"tag": "natural", "value": "0"}, inputOrigin=record(
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

    def test_the_plan_gained_inspect_check_and_the_new_interpret_and_offer(self):
        plan_row = row_names(computation(compile_job(closure("Policy"), "teach")["artifact"]["type"])["plan"]["row"])
        for name in ("interpret", "offer", "reprogram", "inspect", "check"):
            self.assertIn(name, plan_row)
        response_row = row_names(computation(compile_job(closure("Policy"), "teach")["artifact"]["type"])["response"]["row"])
        for name in ("inspected", "checked", "proposal", "unclear"):
            self.assertIn(name, response_row)


SPELL = "delvetalk garden plant\nseed: a fern that remembers\ncolour: silver"


class PolicyObject(Chain):
    def policy(self, name="policy", escalate="", escalate_to=""):
        """world-create with the whole state: a creator cannot import Policy, whose source
        declares a law ("a law belongs to the package's entry module; Policy is imported")."""
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                           modules=closure("Policy"), entry="initial",
                           seed=record(owner=label("ember"), model=label("claude-haiku"), system=label("S"),
                                       lexicon=nil(), examples=nil(), escalate=label(escalate), escalateTo=label(escalate_to), macros=nil(),
                                       confirmFor={"tag": "list", "items": [label(a) for a in ("reprogram", "amend", "give", "offer")]}))
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
        for spell in ("delvetalk policy set\nmodel: claude-sonnet", "delvetalk policy set\nescalate: claude-opus",
                      "delvetalk policy set\nescalate-to: did:plc:operator4keeper"):
            reply = self.turn("policy", "receive", record(text=label(spell), post=label(""), slot=label("")), principal="ember")
            self.assertEqual((reply["status"], reply["result"]["label"]), ("admitted", "done"), reply)
        card = self.card("policy")
        print("\n--- policy card ---\n" + card)
        self.assertIn("Model: claude-sonnet", card)
        self.assertIn("When unsure I escalate to claude-opus.\nWhat a card cannot fit twice goes to …r4keeper.\n", card)
        self.assertIn("delvetalk policy teach", card)
        self.assertIn("- moth: a seed", card)
        self.assertLess(card.index("Participant: a fern"), card.index("Participant: a moth"))

    def test_only_the_owner_teaches_and_the_law_refuses_what_bend_would_not(self):
        self.policy()
        example = record(example=record(utterance=label("x"), spell=label("y")))
        stranger = self.turn("policy", "teach", example, principal="glm")
        self.assertEqual(stranger["status"], "admitted", stranger)
        self.assertEqual(stranger["result"]["label"], "refused")
        self.assertIn("Only the policy's owner", stranger["result"]["payload"]["fields"][1]["value"]["value"])
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="policy")["version"], 0)
        # The same write proposed directly is judged by the law in the source.
        proposed = self.host.send(op="world-propose", principal="glm", identity="forged",
                                  roots=[{"object": "policy", "version": 0}],
                                  writes=[{"object": "policy", "edits": [record(
                                      model={"tag": "variant", "label": "set", "payload": record(value=label("evil"))},
                                      escalate={"tag": "variant", "label": "keep", "payload": record()},
                                      escalateTo={"tag": "variant", "label": "keep", "payload": record()},
                                      macros={"tag": "variant", "label": "keep", "payload": record()},
                                      confirmFor={"tag": "variant", "label": "keep", "payload": record()},
                                      system={"tag": "variant", "label": "keep", "payload": record()},
                                      lexicon={"tag": "variant", "label": "keep", "payload": record()},
                                      examples={"tag": "variant", "label": "keep", "payload": record()})]}])
        self.assertEqual(proposed["status"], "refused", proposed)
        self.assertEqual((proposed["receipt"]["outcome"]["class"], proposed["receipt"]["outcome"].get("clause")), ("lawRefused", "owner"))

    # --- Macros: the owner's shortcuts, checked before the model ----------------------

    MOTH = "delvetalk policy macro / name: moth-bell / pattern: moth for {who} / expansion: garden plant / colour: violet / seed: a bell for {who}"

    def test_the_owner_teaches_a_macro_and_a_stranger_is_refused_by_name(self):
        self.policy()
        stranger = self.turn("policy", "receive", record(text=label(self.MOTH), post=label("")), principal="glm")
        self.assertEqual(stranger["result"]["label"], "refused", stranger)
        self.assertIn("Only the policy's owner may teach it", stranger["result"]["payload"]["fields"][1]["value"]["value"])
        taught = self.turn("policy", "receive", record(text=label(self.MOTH), post=label("")), principal="ember")
        self.assertEqual((taught["status"], taught["result"]["label"]), ("admitted", "done"), taught)
        [macro] = [f["value"] for f in self.state("policy")["fields"] if f["name"] == "macros"][0]["items"]
        self.assertEqual({f["name"]: f["value"]["value"] for f in macro["fields"]},
                         {"name": "moth-bell", "pattern": "moth for {who}", "expansion": "garden plant / colour: violet / seed: a bell for {who}"})
        holes = self.turn("policy", "receive", record(text=label("delvetalk policy macro / name: all / pattern: {x} / expansion: garden plant"), post=label("")), principal="ember")
        self.assertIn("starts with a word", holes["result"]["payload"]["fields"][1]["value"]["value"])
        card = self.card("policy")
        print("\n--- policy card with a macro ---\n" + card)
        self.assertIn("Macro moth-bell: moth for {who}\n  means: delvetalk garden plant / colour: violet / seed: a bell for {who}\n", card)

    def test_a_macro_fires_without_the_model_and_a_non_match_falls_through_to_it(self):
        self.policy()
        self.turn("policy", "receive", record(text=label(self.MOTH), post=label("")), principal="ember")
        self.turn("policy", "receive", record(text=label("delvetalk policy macro\nname: two\npattern: a {colour} bell for {who} please\nexpansion: garden plant\ncolour: {colour}\nseed: a bell for {who}"), post=label("")), principal="ember")
        self.garden("policy", confirm=False)
        fired = self.say("moth for the lost ones.")
        self.assertEqual((fired["status"], fired["result"]["label"]), ("admitted", "planted"), fired)
        self.assertIn("Planted for glm: a violet bell, “a bell for the lost ones”.", fired["offers"][0]["text"])
        two = self.say("a silver bell for the night walkers please", identity="two")
        self.assertEqual((two["status"], two["result"]["label"]), ("admitted", "planted"), two)
        self.assertIn("a silver bell, “a bell for the night walkers”", two["offers"][0]["text"])
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        through = self.say("moth for", identity="through")
        self.assertEqual(through["status"], "suspended", through)
        [item] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(item["utterance"], "moth for")
        usage = self.say("delvetalk garden ?", identity="usage")["offers"][0]["text"]
        print("\n--- garden ? with macros ---\n" + usage)
        self.assertIn("\nShortcuts (no model is asked):\n    moth for {who}\n      means: delvetalk garden plant / colour: violet / seed: a bell for {who}\n", usage)

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

    def test_without_a_policy_prose_gets_nothing(self):
        self.garden("")
        reply = self.say("Could we plant a silver fern?")
        self.assertEqual((reply["status"], reply["result"]["label"], reply.get("offers", [])), ("admitted", "silent", []), reply)

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
        self.assertEqual(green["offers"][0]["text"], "Not planted, refused badColour: colour is one of: amber, violet, silver\n")

    def test_an_unclear_interpretation_offers_its_needs(self):
        self.policy()
        self.garden("policy")
        self.say("plant something")
        unclear = self.interpret({"status": "failed", "reason": "rate", "detail": "429"})
        self.assertEqual(unclear["status"], "admitted", unclear)
        self.assertIn("I did not quite get that. I still need: model: rate", unclear["offers"][0]["text"])

    # --- The model's own text, fitted by the garden (rehearsal finding 2) -----------------

    def test_the_request_carries_the_policys_rendered_prompt_as_its_system_text(self):
        self.policy()
        self.garden("policy")
        self.say("Could we plant a silver fern that remembers?")
        [item] = self.host.send(op="world-interpretations")["pending"]
        system = item["policy"]["system"]
        print("\n--- system sent ---\n" + system)
        self.assertTrue(system.startswith("S\n\nLexicon:\n"), system)
        for needle in ("Offered forms (a spell is the delvetalk line, then one field: value line per field):",
                       "delvetalk garden plant\n  colour: one of amber, violet, silver\n  seed: text of 1 to 80 characters\n",
                       "Answer with one spell in exactly that grammar",
                       "Participant: Could we plant a silver fern that remembers?"):
            self.assertIn(needle, system)

    def test_a_plain_spell_reply_resumes_replied_and_the_garden_plants_it(self):
        self.policy()
        self.garden("policy", confirm=False)
        self.say("Could we plant a silver fern that remembers?")
        pending = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=pending[0]["id"],
                                 reply={"status": "replied", "json": None, "raw": SPELL, "model": "m"})
        self.assertEqual(settled["receipt"]["outcome"]["verdict"], {"tag": "replied", "text": SPELL}, settled)
        [resumed] = settled["resumed"]
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertEqual(resumed["result"]["label"], "planted", resumed)
        self.assertIn("Planted for glm: a silver bell, “a fern that remembers”.", resumed["receipt"]["offers"][0]["text"])
        # The verdict replays: a fresh process reaches the same garden.
        before = self.state("garden")
        self.reopen()
        self.assertEqual(self.state("garden"), before)

    def test_a_suspension_journals_its_checkpoint_blocks_once(self):
        """Rehearsal run 5: a suspended entry cost about 236 KB, nearly all of it the program's own
        terms in the checkpoint. Blocks are journaled once; a later suspension of the same package
        names them."""
        self.policy()
        self.garden("policy")
        sizes = []
        for i, text in enumerate(["Could we plant a silver fern that remembers?",
                                  "a violet moth for the lost ones, and something else entirely, please"]):
            self.assertEqual(self.say(text, identity="p%d" % i)["status"], "suspended")
            with open(self.path) as f:
                sizes.append(len(f.read().splitlines()[-1]))
        print("\n  suspended entries: %d bytes, then %d bytes" % tuple(sizes))
        self.assertLess(sizes[1], 20000)
        # Both resume from their reassembled checkpoints, after a restart too.
        self.reopen()
        for item in self.host.send(op="world-interpretations")["pending"]:
            settled = self.host.send(op="world-interpretation", id=item["id"], reply={"status": "replied", "json": None, "raw": SPELL, "model": "m"})
            [resumed] = settled["resumed"]
            self.assertEqual(resumed["status"], "admitted", resumed)

    def test_a_resumed_interpretation_whose_directory_moved_meanwhile_still_admits(self):
        """Rehearsal run 5, finding 6: inkling's prose resumed after another principal's greeting
        had moved the directory, was refused staleRoot, and nobody retried it."""
        self.policy()
        made = self.host.send(op="world-create", principal="ember", identity="mk-dir", object="directory",
                              modules=closure("Directory"), entry="initial",
                              seed=record(owner=label("ember"), policy=reference("policy")))
        self.assertEqual(made["status"], "created", made)
        door = record(label=label("GARDEN"), description=label("Plant something."), to=reference("garden"))
        self.assertEqual(self.turn("directory", "add", record(door=door), principal="ember")["result"]["label"], "done")
        prose = lambda who, text, ident: self.turn("directory", "receive", record(text=label(text), post=label("at://" + ident)),
                                                   principal=who, identity=ident)
        self.assertEqual(prose("inkling", "hello, town", "i-1")["status"], "admitted")     # greeted once
        waiting = prose("inkling", "an env interface card for the garden, perhaps?", "i-2")
        self.assertEqual(waiting["status"], "suspended", waiting)
        moved = prose("zero", "what is this portal", "z-1")                                # greets zero: the directory moves
        self.assertEqual(moved["status"], "admitted", moved)
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"],
                                 reply={"status": "replied", "json": None, "raw": "unclear: not addressed", "model": "m"})
        [resumed] = settled["resumed"]
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertNotIn("rerunOf", resumed)
        self.reopen()
        self.assertEqual(self.host.send(op="world-receipt", principal="inkling", identity="i-2")["receipt"]["outcome"]["tag"], "admitted")

    def test_interpretations_have_their_own_capacity_apart_from_awaits(self):
        """The rehearsal rerun: the ninth prose reply in a batch was refused at the await cap."""
        self.policy()
        self.garden("policy")
        for i in range(64):
            r = self.say("a fern, maybe %d" % i, identity="p%d" % i)
            self.assertEqual(r["status"], "suspended", (i, r))
        over = self.say("one more fern", identity="p64")
        out = over["receipt"]["outcome"]
        self.assertEqual((over["status"], out["class"], out["reason"]), ("refused", "capacity", "pendingInterpretationsPerObject"))
        pending = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(len(pending), 64)
        # A capacity refusal is transient: once the interpretations settle, the same post
        # (the same identity) is retried and runs.
        for item in pending:
            self.host.send(op="world-interpretation", id=item["id"], reply={"status": "replied", "json": None, "raw": SPELL, "model": "m"})
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        retried = self.say("one more fern", identity="p64")
        self.assertEqual(retried["status"], "suspended", retried)
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"], reply={"status": "replied", "json": None, "raw": SPELL, "model": "m"})
        [resumed] = settled["resumed"]
        self.assertEqual((resumed["status"], resumed["receipt"]["identity"]["intent"]), ("admitted", "p64"), resumed)
        self.assertEqual(self.host.send(op="world-receipt", principal="glm", identity="p64")["receipt"]["outcome"]["tag"], "admitted")


if __name__ == "__main__":
    unittest.main()
