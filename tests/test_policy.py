"""The interpretation policy is an object its owner teaches; prose handed on from the garden to the
commonplace suspends on it, and the model's answer plants, asks first, or is refused by name.

Evidence for FOUNDATION §6 (layer: objects).

The interpretation policy as an object, and the commonplace's hob reading the garden's prose with it.

`interpret` suspends the turn; `world-interpretations` lists what waits and
`world-interpretation {id, reply}` settles it with the model's reply, which the host checks
against the offered forms (the garden's plant) before resuming the commonplace's turn.
"""
import unittest

from deploy import genesis
from tests.host import as_owner

from tests.test_chain import Chain, town_garden
from tests.test_receive import commonplace
from tests.test_objects import check, compile_job
from tests.wire import boolean, field, label, nil, record, rows
from tests.bend import closure, declared

PROBE = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Policy.obend as Policy
def sample() -> Policy.State:
  {owner: "ember", ownerHandle: "", model: "claude-haiku", system: "You turn words into one spell.", lexicon: Lists.List::<Policy.Term>.cons({head: {word: "moth", meaning: "a seed"}, tail: Lists.List::<Policy.Term>.nil()}), examples: Lists.List::<Policy.Example>.cons({head: {utterance: "a silver fern", spell: "delvetalk garden-1 plant seed: a fern, colour: silver"}, tail: Lists.List::<Policy.Example>.nil()}), macros: Lists.List::<Policy.Macro>.nil(), confirmFor: Lists.List::<String>.nil()}
# The garden's plant form (world/bodies/garden.obend), written out.
def plantForm(context: Abi.Context) -> Form.Form:
  {card: context.object, action: "plant", fields: Form.Fields.cons({head: {name: "colour", kind: Form.Kind.choice({options: Lists.append::<String>(Lists.append::<String>(Lists.append::<String>(Form.Names.nil(), "amber"), "violet"), "silver")})}, tail: Form.Fields.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 80n})}, tail: Form.Fields.nil()})})}
def forms(context: Abi.Context) -> Lists.List<Form.Form>:
  Lists.List::<Form.Form>.cons({head: plantForm(context), tail: Lists.List::<Form.Form>.nil()})
def plantPrompt(context: Abi.Context) -> String:
  Policy.prompt(sample(), {utterance: "plant me a moth", offers: forms(context), card: "THE CARD\\n", held: "", misfit: ""})
def heldPrompt(context: Abi.Context) -> String:
  Policy.prompt(sample(), {utterance: "plant me a moth", offers: forms(context), card: "THE CARD\\n", held: "a planting with seed \\"moth\\"; still needs colour", misfit: "badValue, colour is one of: amber, violet, silver"})
def examples(n: Nat) -> Lists.List<Policy.Example>:
  match n:
    case 0: Lists.List::<Policy.Example>.nil()
    case 1+p: Lists.List::<Policy.Example>.cons({head: {utterance: "a silver fern that remembers yesterday", spell: "delvetalk garden-1 plant seed: a fern that remembers yesterday, colour: silver"}, tail: examples(p)})
def many(n: Nat, context: Abi.Context) -> Nat:
  textLength(Policy.prompt({owner: "ember", ownerHandle: "", model: "m", system: "s", lexicon: Lists.List::<Policy.Term>.nil(), examples: examples(n), macros: Lists.List::<Policy.Macro>.nil(), confirmFor: Lists.List::<String>.nil()}, {utterance: "plant me a moth", offers: forms(context), card: "THE CARD\\n", held: "", misfit: ""}))
""")


def context(card="garden-1"):
    text = lambda v: {"tag": "label", "value": v}
    return record(world=text(""), object=text(card), principal=text("glm"), handle=text(""), caller=text(""), intent=text("probe"),
                  height={"tag": "natural", "value": "0"}, clock={"tag": "natural", "value": "0"}, inputOrigin=record(
        kind=text("request"), object=text(""), command=text(""), program=text(""),
        immediatelyPrevious=boolean(False), post=text("")))


def run(entry, *arguments, limits=None):
    modules = closure("Policy") + [{"name": "Probe", "source": PROBE}]
    compiled = compile_job(modules, entry)
    assert compiled["status"] == "compiled", compiled
    request = {"op": "run", "artifact": compiled["artifact"], "arguments": list(arguments)}
    if limits:
        request["limits"] = limits
    return check(request)


HOB_ANSWERS = (
    "\nAnswer with exactly one of these, and nothing else:\n"
    "- the spell, up to three one after another; every value from their words, never invented, a choice never widened;\n"
    "- ask: <one short question> when a value is missing or does not fit: name the field and what it takes; no thanks, sorry or please;\n"
    "- card when they ask something the card already shows (a count, a rule, who is here);\n"
    "- say: <answer> for a question about what a card is or does: at most two sentences, from the card, its forms and the pages given;\n"
    "- none when the words ask nothing of this card: talk among participants, a report, a note.\n")
SPELL = "delvetalk garden plant\nseed: a fern that remembers\ncolour: silver"


class PolicyObject(Chain):
    def policy(self, name="policy"):
        """world-create with the whole state: a creator cannot import Policy, whose source
        declares a law ("a law belongs to the package's entry module; Policy is imported")."""
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                           modules=closure("Policy"), entry="initial",
                           seed=record(owner=label("ember"), model=label("claude-haiku"), system=label("S"),
                                       lexicon=nil(), examples=nil(), macros=nil(),
                                       confirmFor={"tag": "list", "items": [label(a) for a in ("reprogram", "amend", "offer")]}))
        self.assertEqual(r["status"], "created", r)

    def card(self, name, principal="glm"):
        return self.turn(name, "receive", record(text=label(""), post=label("")), principal=principal)["offers"][0]["text"]

    def test_teach_define_and_set_model_edit_the_policy_in_order_and_a_stranger_is_offered_no_spell(self):
        self.policy()
        for utterance, spell in (("a fern", "delvetalk garden-1 plant seed: fern, colour: silver"), ("a moth", "delvetalk garden-1 plant seed: moth, colour: amber"),
                                ("a long one", "delvetalk garden-1 plant seed: " + "x" * 230 + ", colour: amber")):
            reply = self.turn("policy", "teach", record(utterance=label(utterance), spell=label(spell)), principal="ember")
            self.assertEqual((reply["status"], reply["result"]["label"]), ("admitted", "taught"), reply)
        reply = self.turn("policy", "define", record(word=label("moth"), meaning=label("a seed")), principal="ember")
        self.assertEqual(reply["status"], "admitted", reply)
        reply = self.turn("policy", "receive", record(text=label("delvetalk policy set\nmodel: claude-sonnet"), post=label("")), principal="ember")
        self.assertEqual((reply["status"], reply["result"]["label"]), ("admitted", "done"), reply)
        card = self.card("policy")
        owners = self.card("policy", "ember")
        for spell in ("teach\n", "define / word: moth", "macro\n"):
            self.assertIn("\n    delvetalk policy %s" % spell, owners)
        # The rest of the owner's spells would pass what the receipt line under the card leaves of 1,400
        # (Card.limit: 2 x 6 + 120 for `policy`), so the card names `?` instead.
        self.assertTrue(owners.endswith("\nIts spells: delvetalk policy ?\n") and len(owners) <= 1400 - 132, owners)
        self.assertNotIn("Reply with a spell", card)  # a stranger is offered none of the owner's spells: no usage
        self.assertIn("✾ INTERPRETATION POLICY, model claude-sonnet", card)
        self.assertIn("a spell hob reads runs at once, except: reprogram, amend, offer, which ask the speaker first.\n", card)
        self.assertIn("- moth: a seed", card)
        self.assertLess(card.index("Said: a fern"), card.index("Said: a moth"))


    def test_only_the_owner_teaches_and_the_law_refuses_what_bend_would_not(self):
        self.policy()
        example = record(utterance=label("x"), spell=label("y"))
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
                                      macros={"tag": "variant", "label": "keep", "payload": record()},
                                      confirmFor={"tag": "variant", "label": "keep", "payload": record()},
                                      system={"tag": "variant", "label": "keep", "payload": record()},
                                      lexicon={"tag": "variant", "label": "keep", "payload": record()},
                                      examples={"tag": "variant", "label": "keep", "payload": record()})]}])
        self.assertEqual(proposed["status"], "refused", proposed)
        self.assertEqual((proposed["receipt"]["outcome"]["class"], proposed["receipt"]["outcome"].get("clause")), ("lawRefused", "owner"))

    # --- Macros: the owner's shortcuts, checked before the model ----------------------

    # The expansion is one field line, which keeps its slashes.
    MOTH = "delvetalk policy macro\nname: moth-bell\npattern: moth for {who}\nexpansion: garden plant / colour: violet / seed: a bell for {who}"

    def test_the_owner_teaches_a_macro_and_a_stranger_is_refused_by_name(self):
        self.policy()
        stranger = self.turn("policy", "receive", record(text=label(self.MOTH), post=label("")), principal="glm")
        self.assertEqual(stranger["result"]["label"], "refused", stranger)
        self.assertIn("Only the policy's owner may teach it", stranger["result"]["payload"]["fields"][1]["value"]["value"])
        taught = self.turn("policy", "receive", record(text=label(self.MOTH), post=label("")), principal="ember")
        self.assertEqual((taught["status"], taught["result"]["label"]), ("admitted", "taught"), taught)
        [macro] = [f["value"] for f in self.state("policy")["fields"] if f["name"] == "macros"][0]["items"]
        self.assertEqual({f["name"]: f["value"]["value"] for f in macro["fields"]},
                         {"name": "moth-bell", "pattern": "moth for {who}", "expansion": "garden plant / colour: violet / seed: a bell for {who}"})
        holes = self.turn("policy", "receive", record(text=label("delvetalk policy macro / name: all / pattern: {x} / expansion: garden plant"), post=label("")), principal="ember")
        self.assertIn("starts with a word", holes["result"]["payload"]["fields"][1]["value"]["value"])
        card = self.card("policy")
        self.assertNotIn("Reply with a spell", card)  # no usage for a stranger
        self.assertIn("Macro moth-bell: moth for {who}\n  means: delvetalk garden plant / colour: violet / seed: a bell for {who}\n", card)

    def test_a_macro_fires_without_the_model_and_a_non_match_falls_through_to_it(self):
        self.policy()
        self.turn("policy", "receive", record(text=label(self.MOTH), post=label("")), principal="ember")
        self.turn("policy", "receive", record(text=label("delvetalk policy macro\nname: two\npattern: a {colour} bell for {who} please\nexpansion: garden plant / colour: {colour} / seed: a bell for {who}"), post=label("")), principal="ember")
        self.garden("policy")
        fired = self.handed(self.say("moth for the lost ones."))
        self.assertEqual((fired["status"], fired["result"]["label"]), ("admitted", "passed"), fired)
        self.assertIn("Planted, glm: a violet bell, “a bell for the lost ones”, at garden/bell/1", fired["receipt"]["offers"][0]["text"])
        two = self.handed(self.say("a silver bell for the night walkers please", identity="two"))
        self.assertEqual((two["status"], two["result"]["label"]), ("admitted", "passed"), two)
        self.assertIn("a silver bell, “a bell for the night walkers”", two["receipt"]["offers"][0]["text"])
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(self.handed(self.say("moth for", identity="through"))["status"], "suspended")
        [item] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(item["utterance"], "moth for")

    def test_the_sixteenth_example_is_the_last(self):
        self.policy()
        for i in range(16):
            r = self.turn("policy", "teach", record(utterance=label("u%d" % i), spell=label("s")), principal="ember")
            self.assertEqual(r["result"]["label"], "taught", r)
        over = self.turn("policy", "teach", record(utterance=label("u16"), spell=label("s")), principal="ember")
        self.assertEqual(over["result"]["label"], "refused")

    def test_the_prompt_shows_what_the_card_holds_and_the_misfit_before_the_examples(self):
        out = run("heldPrompt", context())
        self.assertEqual(out["status"], "finished", out)
        prompt = out["value"]["value"]
        self.assertIn('\n\nHeld for this participant: a planting with seed "moth"; still needs colour\n'
                      "Misfit: badValue, colour is one of: amber, violet, silver\n"
                      "\nSaid, and the answer:\nSaid: a silver fern\n", prompt)
        self.assertTrue(prompt.endswith(HOB_ANSWERS), prompt)
        plain = run("plantPrompt", context())["value"]["value"]
        self.assertNotIn("Held for this participant", plain)
        self.assertNotIn("Misfit:", plain)
        self.assertNotIn("plant me a moth", plain)  # the utterance is the user turn, not the system text (docs/FLEX.md section 2)

    # --- the garden's prose goes on to the commonplace, whose hob reads it ------------

    def garden(self, policy="policy"):
        """The town garden, and the commonplace (with `policy`, or none) it hands prose on to."""
        town_garden(self.host.send)
        commonplace(self, policy, doors=[("GARDEN", "garden", [])])

    def say(self, text, principal="glm", identity=None, obj="garden", reach="mention"):
        """Words at the garden; its hand-on to the commonplace is delivered before this returns."""
        reply = self.turn(obj, "receive", record(text=label(text), post=label("at://glm/p/1")), principal=principal,
                          identity=identity, reach=reach)
        self.deliver_all()
        return reply

    def interpret(self, reply):
        pending = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(len(pending), 1, pending)
        settled = self.host.send(op="world-interpretation", id=pending[0]["id"], reply=reply)
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = settled["resumed"]
        resumed = as_owner(self.host, resumed)
        # A resumed turn's offers are retained on its receipt as {to, text}.
        resumed.setdefault("offers", [{"principal": o["to"], "text": o["text"]} for o in resumed["receipt"].get("offers", [])])
        return resumed

    def planting(self, colour="silver", seed="a fern that remembers"):
        return {"status": "replied", "model": "m", "json": {"method": "plant", "argument": {"colour": colour, "seed": seed}}}

    def things(self):
        return [field(r, "object")["value"] for r in rows(field(self.state("garden"), "things"))]

    def handed(self, reply):
        """The one turn the garden's hand-on ran at the commonplace."""
        self.assertEqual(reply["status"], "admitted", reply)
        turn = reply["delivered"][0]
        self.assertEqual(turn["receipt"]["delivery"]["from"]["intent"], reply["receipt"]["identity"]["intent"], turn)
        return turn

    def test_without_a_policy_prose_at_the_garden_asks_no_one(self):
        self.garden("")
        reply = self.say("Could we plant a silver fern?")
        # The garden answers with its own card and reads nothing; the commonplace, handed the words, has no hob to ask.
        self.assertEqual(reply["result"]["label"], "silent", reply)
        self.assertTrue(reply["offers"][0]["text"].startswith("✾ THE NIGHT GARDEN\n"), reply["offers"])
        handed = self.handed(reply)
        self.assertEqual((handed["status"], handed["result"]["label"]), ("admitted", "silent"), handed)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(self.things(), [])

    def test_a_typed_spell_missing_a_field_never_asks_the_policy(self):
        self.policy()
        self.garden()
        typed = self.say("delvetalk garden plant\nseed: a fern")
        self.assertIn("Almost. Still needs colour.", typed["offers"][0]["text"])
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_the_gardens_prose_is_handed_on_and_read_once_by_hob_against_the_gardens_forms(self):
        self.policy()
        self.garden()
        reply = self.say("Could we plant a silver fern that remembers?")
        self.assertEqual(reply["result"]["label"], "silent", reply)
        [item] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual({o["card"] for o in item["offers"]}, {"garden"}, item["offers"])
        self.assertEqual([o["action"] for o in item["offers"]], ["plant", "dig", "lines"], item["offers"])
        planted = self.interpret(self.raw(SPELL))
        self.assertEqual((planted["status"], planted["result"]["label"]), ("admitted", "passed"), planted)
        self.assertTrue(planted["offers"][0]["text"].startswith("Planted, glm: a silver bell, “a fern that remembers”, at garden/bell/1; 1 planted.\n"), planted["offers"])
        self.assertEqual(self.things(), ["garden/bell/1"])
        # The bell awaits a reply to the post that was read (codex objects 12).
        self.assertEqual(field(self.state("garden/bell/1"), "post"), label("at://glm/p/1"))

    def raw(self, text):
        return {"status": "replied", "json": None, "raw": text, "model": "m"}

    NONE = {"status": "replied", "json": None, "raw": "none", "model": "m"}

    def hob_says(self, text):
        return self.raw(text)

    def test_a_model_that_could_not_be_asked_is_silence(self):
        self.policy()
        self.garden()
        self.say("plant something")
        # A failure the host does not retry (`rate` and `transport` it does: HOST-HANDOFF 5.107):
        # `model: refused` is no question for the speaker, so hob's answer is none.
        silent = self.interpret({"status": "failed", "reason": "refused", "detail": "400"})
        self.assertEqual((silent["status"], silent["result"]["label"], silent.get("offers", [])), ("admitted", "silent", []), silent)
        self.assertEqual(self.things(), [])

    def test_hob_none_at_the_gardens_prose_is_silence(self):
        self.policy()
        self.garden()
        self.say("my cat is called Pip, by the way")
        silent = self.interpret(self.NONE)
        self.assertEqual((silent["status"], silent["result"]["label"], silent.get("offers", [])), ("admitted", "silent", []), silent)
        self.assertEqual(self.things(), [])

    def test_a_colour_the_form_does_not_take_comes_back_as_hobs_one_question(self):
        self.policy()
        self.garden()
        self.say("a green one")
        green = self.interpret(self.raw("delvetalk garden plant / colour: green / seed: a fern"))
        # The host reads the colour's word as its case: one naming none is `unclear` (HOST-HANDOFF
        # 5.52). hob is asked once: its line names the field the need names (never the model's or the
        # host's words: VOICE's fixed line), over the plant spell with blanks.
        self.assertEqual((green["status"], green["result"]["label"]), ("admitted", "unclear"), green)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])  # hob is asked once
        self.assertEqual(green["offers"][0]["text"], (
            "hob: still needs colour; the spell is below.\n"
            "\n"
            "    delvetalk garden plant\n"
            "    colour: <amber, violet, silver>\n"
            "    seed: <text, 1 to 80 characters>\n"))
        self.assertEqual(self.things(), [])

    def test_the_gardens_own_misfit_is_its_refusal_and_asks_no_one(self):
        # HOST-HANDOFF 121: the garden's receive takes a direct turn's misfit and answers it by clause; it is no prose.
        self.policy()
        self.garden()
        misfit = self.say("delvetalk garden plant\nseed: a fern\ncolour: green")
        self.assertEqual((misfit["status"], misfit["result"]["label"]), ("admitted", "refused"), misfit)
        self.assertIn("refused badValue: colour is one of: amber, violet, silver\n", misfit["offers"][0]["text"])
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(self.things(), [])

    def test_a_misfit_spell_the_commonplace_takes_is_read_by_hob_with_its_clause_and_reason(self):
        # With a policy hob is shown the commonplace's own misfit (no card by that name) with its clause.
        self.policy()
        self.garden()
        self.assertEqual(self.say("hello", obj="commonplace")["status"], "suspended")
        self.interpret(self.NONE)
        misfit = self.say("delvetalk orchard plant", obj="commonplace")
        self.assertEqual(misfit["status"], "suspended", misfit)
        [item] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(item["misfit"], "otherCard, There is no card orchard; the directory lists the doors.")
        self.assertIn("\nMisfit: otherCard, There is no card orchard; the directory lists the doors.\n", item["policy"]["system"])
        asked = self.interpret(self.hob_says("ask: Which card: the garden?"))
        self.assertEqual(asked["result"]["label"], "unclear", asked)
        self.assertNotIn("Which card", asked["offers"][0]["text"])  # the model's words never reach the card

    def test_prose_with_no_stated_reach_is_not_addressed_at_once(self):
        # HOST-HANDOFF 118: no reach, no model, no suspension, no quota.
        self.policy()
        self.garden()
        reply = self.say("Could we plant a silver fern?", reach=None)
        handed = self.handed(reply)
        self.assertEqual((handed["status"], handed["result"]["label"]), ("admitted", "silent"), handed)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    # --- The model's own text, fitted by the commonplace to the garden's forms (rehearsal finding 2) ---

    def test_the_request_carries_the_policys_rendered_prompt_as_its_system_text(self):
        self.policy()
        self.garden()
        self.say("Could we plant a silver fern that remembers?")
        [item] = self.host.send(op="world-interpretations")["pending"]
        system = item["policy"]["system"]
        self.assertTrue(item["card"].startswith("✾ DELVETALK · THE COMMONPLACE\n"), item["card"])
        self.assertTrue(system.startswith("S\n\nThe card they answered:\n" + item["card"]), system)
        self.assertIn("delvetalk garden plant\n  colour: one of amber, violet, silver\n  seed: text of 1 to 80 characters\n", system)
        self.assertTrue(system.endswith(HOB_ANSWERS), system)
        # What the user turn carries is the utterance alone; no Held or Misfit line for a plain reply.
        self.assertNotIn("Could we plant", system)
        self.assertEqual((item["utterance"], item["held"], item["misfit"]), ("Could we plant a silver fern that remembers?", "", ""))

    def test_the_workshops_make_asks_for_a_package_with_no_card_and_no_spell_in_the_prompt(self):
        """Playtest 2's D3: the dry run's `workshop make / name: lamp / description: a lamp anyone lights` was answered
        with the workshop's own spell copied from its card. The drafting prompt holds no card and no spell, shows one
        whole package (the library's `object` page's), and asks for one ```obend block alone."""
        self.policy()
        self.make("workshop", closure("Workshop"), record(title=label("Workshop"), policy=record(world=label(""), object=label("policy"))))
        asked = self.turn("workshop", "make", record(name=label("lamp"), description=label("a lamp anyone lights")), principal="glm")
        self.assertEqual(asked["status"], "suspended", asked)
        [item] = self.host.send(op="world-interpretations")["pending"]
        system = item["policy"]["system"]
        self.assertNotIn("delvetalk", system)
        self.assertNotIn("✾ WORKSHOP", system)
        package = "".join(line + "\n" for line in genesis.page_body("object").splitlines()[1:] if not line.startswith(("METHODS", "Check:", "Next:")))
        self.assertIn("```obend\n" + package + "```\n", system)
        self.assertTrue(system.endswith("Answer with one ```obend block holding the package, and nothing else.\n"), system)
        self.assertEqual(item["utterance"], "Write the Bend for a thing called lamp: a lamp anyone lights")
        self.assertEqual([(o["card"], o["action"]) for o in item["offers"]], [("workshop", "check")])

    def test_a_plain_spell_reply_is_fitted_to_a_proposal_and_the_garden_grows_the_bell(self):
        self.policy()
        self.garden()
        self.say("Could we plant a silver fern that remembers?")
        pending = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=pending[0]["id"], reply=self.raw(SPELL))
        # The host fits the model's spell to the offered plant form (HOST-HANDOFF 5.54).
        verdict = settled["receipt"]["outcome"]["verdict"]
        self.assertEqual((verdict["tag"], verdict["method"]), ("proposal", "plant"), settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "passed"), resumed)
        self.assertIn("Planted, glm: a silver bell, “a fern that remembers”, at garden/bell/1", resumed["receipt"]["offers"][0]["text"])

    def test_a_resumed_interpretation_whose_commonplace_moved_meanwhile_still_admits(self):
        """Rehearsal run 5, finding 6: inkling's prose resumed after another principal's greeting
        had moved the commonplace, was refused staleRoot, and nobody retried it."""
        self.policy()
        commonplace(self, "policy", doors=[("GARDEN", "garden", [])])
        prose = lambda who, text, ident: self.turn("commonplace", "receive", record(text=label(text), post=label("at://" + ident)),
                                                   principal=who, identity=ident, reach="mention")
        # With a policy a first reply is read by hob before the menu (docs/FLEX.md section 2).
        none = lambda utterance: self.host.send(op="world-interpretation", id=[p for p in self.host.send(op="world-interpretations")["pending"]
                                                                                  if p["utterance"] == utterance][0]["id"],
                                                reply={"status": "replied", "json": None, "raw": "none", "model": "m"})
        self.assertEqual(prose("inkling", "hello, town", "i-1")["status"], "suspended")
        self.assertEqual([r["status"] for r in none("hello, town")["resumed"]], ["admitted"])      # greeted once
        waiting = prose("inkling", "an env interface card for the garden, perhaps?", "i-2")
        self.assertEqual(waiting["status"], "suspended", waiting)
        self.assertEqual(prose("zero", "what is this portal", "z-1")["status"], "suspended")
        moved = none("what is this portal")                                                      # greets zero: the commonplace moves
        self.assertEqual([r["status"] for r in moved["resumed"]], ["admitted"], moved)
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"],
                                 reply={"status": "replied", "json": None, "raw": "none", "model": "m"})
        [resumed] = settled["resumed"]
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertNotIn("rerunOf", resumed)
        self.reopen()
        self.assertEqual(self.host.send(op="world-receipt", principal="inkling", identity="i-2")["receipt"]["outcome"]["tag"], "admitted")

    def test_interpretations_have_their_own_capacity_apart_from_awaits(self):
        """The rehearsal rerun: the ninth prose reply in a batch was refused at the await cap."""
        # One principal starts 65 here: the hourly interpretation quota (48 by default) is lifted.
        self.assertEqual(self.host.send(op="world-open", path=self.path, interpretQuota=1000)["status"], "opened")
        self.policy()
        self.garden("policy")
        for i in range(64):
            r = self.say("a fern, maybe %d" % i, identity="p%d" % i)
            self.assertEqual(self.handed(r)["status"], "suspended", (i, r))
        over = self.say("one more fern", identity="p64")
        # The garden's turn is admitted; the hand-on it sent the commonplace is the one refused.
        self.assertEqual(over["status"], "admitted", over)
        out = over["delivered"][0]["receipt"]["outcome"]
        self.assertEqual((out["class"], out["object"], out["reason"]), ("capacity", "commonplace", "the host's pendingInterpretationsPerObject is full; try later."))
        pending = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(len(pending), 64)
        # A capacity refusal is transient: once the interpretations settle, the next hand-on is read.
        for item in pending:
            self.host.send(op="world-interpretation", id=item["id"], reply=self.raw(SPELL))
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(len(self.things()), 64)
        retried = self.say("one more fern", identity="p65")
        self.assertEqual(self.handed(retried)["status"], "suspended", retried)
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"], reply=self.raw(SPELL))
        [resumed] = settled["resumed"]
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertEqual(len(self.things()), 65)


if __name__ == "__main__":
    unittest.main()
