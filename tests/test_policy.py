"""The interpretation policy is an object its owner configures; prose at the commonplace suspends on
it, and the model's answer plants, asks first, or is refused by name.

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
from tests.wire import boolean, cast_refusal, field, label, listing, record, rows
from tests.bend import closure, declared

PROBE = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Policy.obend as Policy
def sample() -> Policy.State:
  {owner: "ember", ownerHandle: "", model: "claude-haiku", examples: Lists.List::<Policy.Example>.cons({head: {utterance: "a silver fern", spell: "delvetalk garden-1 plant seed: a fern, colour: silver"}, tail: Lists.List::<Policy.Example>.nil()}), confirmFor: Lists.List::<String>.nil()}
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
  textLength(Policy.prompt({owner: "ember", ownerHandle: "", model: "m", examples: examples(n), confirmFor: Lists.List::<String>.nil()}, {utterance: "plant me a moth", offers: forms(context), card: "THE CARD\\n", held: "", misfit: ""}))
""")


def context(card="garden-1"):
    text = lambda v: {"tag": "label", "value": v}
    return record(world=text(""), object=text(card), principal=text("glm"), handle=text(""), caller=text(""), sender=text(""), intent=text("probe"),
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
    "- the spell they meant, up to three one after another; every value from their words, never invented, a choice never widened;\n"
    "- grow: NAME \"reading\", then on the next line the spell that uses the new verb, when their words name an act the card's verbs do not have; a grown verb is a gesture: one line on the thing, tagged with the verb, and the thing tended;\n"
    "- ask: <one short question> when a value is missing or does not fit: name the field and what it takes; no thanks, sorry or please;\n"
    "- none when the words are not addressed to the card, or are conversation.\n")
SPELL = "delvetalk garden plant\nseed: a fern that remembers\ncolour: silver"


class PolicyObject(Chain):
    def policy(self, name="policy", examples=()):
        """world-create with the whole state: a creator cannot import Policy, whose source
        declares a law ("a law belongs to the package's entry module; Policy is imported")."""
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                           modules=closure("Policy"), entry="initial",
                           seed=record(owner=label("ember"), model=label("claude-haiku"),
                                       examples=listing(record(utterance=label(u), spell=label(sp)) for u, sp in examples),
                                       confirmFor={"tag": "list", "items": [label(a) for a in ("reprogram", "amend", "offer")]}))
        self.assertEqual(r["status"], "created", r)

    def card(self, name, principal="glm"):
        return self.turn(name, "receive", record(text=label(""), post=label("")), principal=principal)["offers"][0]["text"]

    def test_set_model_edits_the_policy_and_the_card_shows_its_owner_model_stance_and_examples(self):
        self.policy(examples=(("a fern", "delvetalk garden-1 plant seed: fern, colour: silver"), ("a moth", "delvetalk garden-1 plant seed: moth, colour: amber")))
        reply = self.turn("policy", "receive", record(text=label("delvetalk policy set\nmodel: claude-sonnet"), post=label("")), principal="ember")
        self.assertEqual((reply["status"], reply["result"]["label"]), ("admitted", "done"), reply)
        card = self.card("policy")
        owners = self.card("policy", "ember")
        self.assertIn("\n    delvetalk policy confirm\n", owners)
        self.assertNotIn("teach", owners)
        self.assertNotIn("Reply with a spell", card)  # a stranger is offered none of the owner's spells: no usage
        self.assertIn("✾ INTERPRETATION POLICY, model claude-sonnet", card)
        self.assertIn("a spell hob reads runs at once, except: reprogram, amend, offer, which ask the speaker first.\n", card)
        self.assertIn("Owner: ember\n", card)
        self.assertNotIn("Words:", card)
        self.assertLess(card.index("Said: a fern"), card.index("Said: a moth"))

    def test_only_the_owner_changes_the_policy_and_the_law_refuses_what_bend_would_not(self):
        self.policy()
        stranger = self.turn("policy", "receive", record(text=label("delvetalk policy confirm / action: plant / ask: yes"), post=label("")), principal="glm")
        clause, reading = cast_refusal(stranger)
        self.assertEqual(clause, "notOwner", stranger)
        self.assertIn("Only the policy's owner", reading)
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="policy")["version"], 0)
        # The same write proposed directly is judged by the law in the source.
        proposed = self.host.send(op="world-propose", principal="glm", identity="forged",
                                  roots=[{"object": "policy", "version": 0}],
                                  writes=[{"object": "policy", "edits": [record(
                                      model={"tag": "variant", "label": "set", "payload": record(value=label("evil"))},
                                      confirmFor={"tag": "variant", "label": "keep", "payload": record()},
                                      examples={"tag": "variant", "label": "keep", "payload": record()})]}])
        self.assertEqual(proposed["status"], "refused", proposed)
        self.assertEqual((proposed["receipt"]["outcome"]["class"], proposed["receipt"]["outcome"].get("clause")), ("lawRefused", "owner"))

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

    # --- prose at the commonplace, which hob reads ------------------------------------

    def garden(self, policy="policy"):
        """The town garden, and the commonplace (with `policy`, or none) that cites it."""
        town_garden(self.host.send)
        commonplace(self, policy, doors=[("GARDEN", "garden", [])])

    def say(self, text, principal="glm", identity=None, obj="commonplace", reach="mention"):
        """Words at the commonplace (or at `obj`)."""
        return self.turn(obj, "receive", record(text=label(text), post=label("at://glm/p/1")), principal=principal,
                         identity=identity, reach=reach)

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

    def test_without_a_policy_prose_at_the_commonplace_asks_no_one(self):
        self.garden("")
        reply = self.say("Could we plant a silver fern?")
        self.assertEqual((reply["status"], reply["result"]["label"], reply.get("offers", [])), ("admitted", "silent", []), reply)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(self.things(), [])

    def test_prose_at_a_card_is_silent_and_handed_on_to_no_one(self):
        """A card hears a verb or nothing: prose at the garden gets no card, no offer and no reading."""
        self.policy()
        self.garden()
        reply = self.say("Could we plant a silver fern that remembers?", obj="garden")
        self.assertEqual((reply["status"], reply["result"]["label"], reply.get("offers", [])), ("admitted", "silent", []), reply)
        self.assertNotIn("delivered", reply)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_a_typed_spell_missing_a_field_never_asks_the_policy(self):
        self.policy()
        self.garden()
        typed = self.say("delvetalk garden plant\nseed: a fern", obj="garden")
        self.assertIn("Almost. Still needs colour.", typed["offers"][0]["text"])
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_prose_at_the_commonplace_is_read_once_by_hob_against_the_doors_forms(self):
        self.policy()
        self.garden()
        reply = self.say("Could we plant a silver fern that remembers?")
        self.assertEqual(reply["status"], "suspended", reply)
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

    def test_hob_none_at_the_commonplace_is_silence(self):
        self.policy()
        self.garden()
        self.say("my cat is called Pip, by the way")
        silent = self.interpret(self.NONE)
        self.assertEqual((silent["status"], silent["result"]["label"], silent.get("offers", [])), ("admitted", "silent", []), silent)
        self.assertEqual(self.things(), [])

    def test_a_colour_the_form_does_not_take_comes_back_as_hobs_one_question_over_the_doors(self):
        self.policy()
        self.garden()
        self.say("a green one")
        green = self.interpret(self.raw("delvetalk garden plant / colour: green / seed: a fern"))
        # The host reads the colour's word as its case: one naming none is `unclear` (HOST-HANDOFF
        # 5.52). hob is asked once: its line names the field the need names (never the model's or the
        # host's words: VOICE's fixed line), over the doors.
        self.assertEqual((green["status"], green["result"]["label"]), ("admitted", "unclear"), green)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])  # hob is asked once
        self.assertEqual(green["offers"][0]["text"], "hob: no door takes that as said; still needs colour. The doors:\nGARDEN\n")
        self.assertEqual(self.things(), [])

    def test_a_misfit_to_the_garden_which_reads_no_words_is_the_hosts_refusal_and_asks_no_one(self):
        # HOST-HANDOFF 5.153: the garden names no policy, so its misfit is the host's badSpell with the usage; it is no prose.
        self.policy()
        self.garden()
        misfit = self.say("delvetalk garden plant\nseed: a fern\ncolour: green", obj="garden")
        out = misfit["receipt"]["outcome"]
        self.assertEqual((misfit["status"], out["class"], out["clause"], out["reason"]),
                         ("refused", "badSpell", "badValue", "colour is one of: amber, violet, silver"), misfit)
        self.assertIn("delvetalk garden plant", out["hint"])
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(self.things(), [])

    def test_a_misfit_spell_the_commonplace_takes_is_read_by_hob_with_its_clause_and_reason(self):
        # With a policy hob is shown the commonplace's own misfit (no card by that name) with its clause.
        self.policy()
        self.garden()
        misfit = self.say("delvetalk orchard plant")
        self.assertEqual(misfit["status"], "suspended", misfit)
        [item] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(item["misfit"], "otherCard, There is no card orchard; the commonplace lists the doors.")
        self.assertIn("\nMisfit: otherCard, There is no card orchard; the commonplace lists the doors.\n", item["policy"]["system"])
        asked = self.interpret(self.hob_says("ask: Which card: the garden?"))
        self.assertEqual(asked["result"]["label"], "unclear", asked)
        self.assertNotIn("Which card", asked["offers"][0]["text"])  # the model's words never reach the card

    def test_prose_with_no_stated_reach_is_not_addressed_at_once(self):
        # HOST-HANDOFF 118: no reach, no model, no suspension, no quota.
        self.policy()
        self.garden()
        reply = self.say("Could we plant a silver fern?", reach=None)
        self.assertEqual((reply["status"], reply["result"]["label"]), ("admitted", "silent"), reply)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    # --- The model's own text, fitted by the commonplace to the doors' forms (rehearsal finding 2) ---

    def test_the_request_carries_the_policys_rendered_prompt_as_its_system_text(self):
        self.policy()
        self.garden()
        self.say("Could we plant a silver fern that remembers?")
        [item] = self.host.send(op="world-interpretations")["pending"]
        system = item["policy"]["system"]
        self.assertTrue(item["card"].startswith("✾ DELVETALK · THE COMMONPLACE\n"), item["card"])
        self.assertTrue(system.startswith("hob reads for a town of cards. A participant answered the card below in words.") and
                        "\n\nThe card they answered:\n" + item["card"] in system, system)
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
        """Rehearsal run 5, finding 6: inkling's prose resumed after another write had moved the commonplace
        was refused staleRoot, and nobody retried it. Here the owner hangs a door while hob reads."""
        self.policy()
        commonplace(self, "policy", doors=[("GARDEN", "garden", [])])
        waiting = self.turn("commonplace", "receive", record(text=label("an interface card for the garden, perhaps?"), post=label("at://i-2")),
                            principal="inkling", identity="i-2", reach="mention")
        self.assertEqual(waiting["status"], "suspended", waiting)
        moved = self.turn("commonplace", "door", record(label=label("TIDE"), to=label("tide")), principal="ember")
        self.assertEqual(moved["result"]["label"], "done", moved)
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"], reply={"status": "replied", "json": None, "raw": "none", "model": "m"})
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
            self.assertEqual(r["status"], "suspended", (i, r))
        over = self.say("one more fern", identity="p64")
        out = over["receipt"]["outcome"]
        self.assertEqual((out["class"], out["object"], out["reason"]), ("capacity", "commonplace", "the host's pendingInterpretationsPerObject is full; try later."))
        pending = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(len(pending), 64)
        # A capacity refusal is transient: once the interpretations settle, the next reply is read.
        for item in pending:
            self.host.send(op="world-interpretation", id=item["id"], reply=self.raw(SPELL))
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(len(self.things()), 64)
        retried = self.say("one more fern", identity="p65")
        self.assertEqual(retried["status"], "suspended", retried)
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"], reply=self.raw(SPELL))
        [resumed] = settled["resumed"]
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertEqual(len(self.things()), 65)


if __name__ == "__main__":
    unittest.main()
