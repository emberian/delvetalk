"""The host reads spells (WHOLENESS §2, host day 2): a `receive {text, post}` to a card written in the
message dialect is parsed by the host (Host/Spell.lean); a spell that fits runs the method it names with
the typed argument (`inputOrigin.kind = "spell"`); one that does not is refused `badSpell` with its
clause, reason and hint; a spell missing fields, or prose, runs `receive` with the bare field lines in
`fields`; `?` is answered with the usage; a spell naming another card runs on it.

Evidence for HOST-HANDOFF 5.49 (layer: host). Refuted by a fitting spell that does not run its method, a
misfit admitted or refused without its clause, prose that does not reach `receive`, or a refusal whose
public projection hides the clause or hint.

    python3 -W error -m unittest tests.test_spell_turns -v
"""
import unittest

from tests.host import as_owner

from tests.test_reflection import POLICY, Reflection
from tests.wire import label, nat, record, reference
from tests.bend import declared

GARDEN = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  planted: String
  origin: String
  heard: String
  fields: Nat
sum Colour:
  amber: {}
  violet: {}
  silver: {}
record Binding:
  name: String
  value: String
def initial() -> State:
  {planted: "", origin: "", heard: "", fields: 0n}
def colourText(c: Colour) -> String:
  match c:
    case amber(_): "amber"
    case violet(_): "violet"
    case silver(_): "silver"
def plant(state: State, input: {colour: Colour, seed: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {planted: Plans.Edit.set({value: textConcat(colourText(input.colour), textConcat(":", input.seed))}), origin: Plans.Edit.set({value: textConcat(context.inputOrigin.kind, textConcat("|", context.inputOrigin.command))})}))
  1n
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {heard: Plans.Edit.set({value: input.text}), fields: Plans.Edit.set({value: Lists.length::<Binding>(input.fields)})}))
  2n
"""


# The second playtest's message 69062, verbatim (docs/review/zulip-playtest-2.md, D1).
PLAYTEST_69062 = "0-for-3 on persistence. the garden forgets but the octopus doesn't.\n\ndelvetalk garden plant\ncolour: violet\nseed: the gap that doesn't exist from the inside \u2014 third planting\n\ndelvetalk kinds make / name: erratum / of: record / form: correction: text 1..80 / head: a record of what was wrong and when / law: / body:"


class SpellTurns(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        for name in ("garden", "plot"):
            r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                               modules=[{"name": "Garden", "source": declared(GARDEN)}],
                               entry="initial", seed=record())
            self.assertEqual(r["status"], "created", r)

    def say(self, text, card="garden", principal="glm", identity=None):
        return self.turn(card, "receive", record(text=label(text), post=label("")), principal=principal, identity=identity)

    def field(self, name, card="garden"):
        return {f["name"]: f["value"] for f in self.state(card)["fields"]}[name]

    def test_a_fitting_spell_runs_its_method_in_any_case_on_a_direct_reply_and_on_the_card_it_names(self):
        r = self.say("delvetalk garden plant\ncolour: silver\nseed: fern")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.field("planted"), label("silver:fern"))
        self.assertEqual(self.field("origin"), label("spell|delvetalk garden plant"))
        # docs/FLEX.md §4 host 2: the card's name folded to the object it names; on a direct reply
        # (reach `direct` or `reply`) a first line naming one of the card's actions is the spell.
        r = self.say("Delvetalk GARDEN Plant\nColour: silver\nSeed: fern")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        r = self.turn("garden", "receive", record(text=label("plant.\ncolour: amber\nseed: moss"), post=label("")),
                      principal="glm", reach="direct")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.field("planted"), label("amber:moss"))
        r = self.turn("garden", "receive", record(text=label("Plant / colour: violet / seed: rue"), post=label("")),
                      principal="glm", reach="direct")
        self.assertEqual(self.field("planted"), label("violet:rue"), r)
        # Unaddressed (a mention), the same words are not a spell.
        r = self.turn("garden", "receive", record(text=label("plant / colour: amber / seed: rye"), post=label("")),
                      principal="glm", reach="mention")
        self.assertEqual((r["result"], self.field("planted")), (nat(2), label("violet:rue")), r)
        # A spell naming another card runs on it.
        r = self.say("delvetalk plot plant\ncolour: amber\nseed: oak", card="garden")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual((self.field("planted", "plot"), self.field("planted", "garden")), (label("amber:oak"), label("violet:rue")))

    def test_several_spells_at_a_lines_start_are_a_turn_each_and_a_fourth_is_refused(self):
        post = ("first the garden:\ndelvetalk garden plant / colour: amber / seed: a\n"
                "delvetalk plot plant / colour: silver / seed: b\n\nand then:\ndelvetalk garden plant / colour: gold / seed: c\n"
                "delvetalk plot plant / colour: violet / seed: d\ndelvetalk garden plant / colour: amber / seed: e")
        r = self.say(post, identity="post-1")
        self.assertEqual(r["status"], "spells", r)
        turns = r["turns"]
        intents = [t["receipt"]["identity"]["intent"] for t in turns]
        self.assertEqual(intents, ["post-1#1", "post-1#2", "post-1#3", "post-1#4"])
        # Each judged alone: the third misfits (gold is no colour) and the others stand.
        self.assertEqual([t["status"] for t in turns], ["admitted", "admitted", "refused", "refused"], turns)
        self.assertEqual(turns[2]["receipt"]["outcome"]["clause"], "badValue")
        self.assertEqual(turns[3]["receipt"]["outcome"]["clause"], "tooManySpells")
        self.assertIn("the 2 after them are not cast", turns[3]["receipt"]["outcome"]["reason"])
        self.assertEqual((self.field("planted"), self.field("planted", "plot")), (label("amber:a"), label("silver:b")))
        # A retry of the post is answered from each identity.
        again = self.say(post, identity="post-1")
        self.assertEqual([t["receipt"]["hash"] for t in again["turns"]], [t["receipt"]["hash"] for t in turns])
        # One identity, one request: the post's identity is its spells', and a single turn's is its own.
        self.assertEqual(self.say("delvetalk garden plant / colour: amber / seed: z", identity="post-1")["class"], "duplicateIdentity")
        self.assertEqual(self.say("delvetalk garden plant / colour: amber / seed: y", identity="post-2")["status"], "admitted")
        self.assertEqual(self.say(post, identity="post-2")["class"], "duplicateIdentity")

    def test_the_second_playtests_69062_casts_both_its_spells(self):
        """D1: 69062, verbatim, ran only its `kinds make`; its planting got no receipt. Now a turn each, two receipts."""
        r = self.say(PLAYTEST_69062, identity="zulip://delvetalk/welcome/69062")
        self.assertEqual(r["status"], "spells", r)
        planted, made = r["turns"]
        self.assertEqual((planted["status"], planted["receipt"]["identity"]["intent"]), ("admitted", "zulip://delvetalk/welcome/69062#1"))
        self.assertEqual(self.field("planted"), label("violet:the gap that doesn't exist from the inside \u2014 third planting"))
        self.assertEqual(made["receipt"]["identity"]["intent"], "zulip://delvetalk/welcome/69062#2")  # no kinds card here: its own receipt

    def test_a_spell_missing_fields_reaches_receive_with_its_card_and_action(self):
        # The host's reading of the spell, so no card reads the spell line again (fungus H1).
        source = declared(GARDEN.replace(
            "def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:\n"
            "  let written(_) = world.write(extend(keep(), {heard: Plans.Edit.set({value: input.text}),",
            "record Cast:\n  card: String\n  action: String\n"
            "def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>, spell: Cast}, context: Abi.Context) -> Activity<Nat>:\n"
            "  let written(_) = world.write(extend(keep(), {heard: Plans.Edit.set({value: textConcat(input.spell.card, textConcat(\" \", input.spell.action))}),"))
        made = self.host.send(op="world-create", principal="ember", identity="mk-cast", object="cast",
                              modules=[{"name": "Garden", "source": source}], entry="initial", seed=record())
        self.assertEqual(made["status"], "created", made)
        r = self.say("delvetalk Cast plant\ncolour: silver", card="cast")  # seed missing: a derived text field is required
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(2)), r)
        self.assertEqual(self.field("heard", "cast"), label("Cast plant"))
        self.say("just words", card="cast")
        self.assertEqual(self.field("heard", "cast"), label(" "))

    def test_missing_fields_and_prose_reach_receive_with_the_bare_fields(self):
        r = self.say("delvetalk garden plant\nseed: fern")
        self.assertEqual(r["result"], nat(2), r)
        self.assertEqual(self.field("fields"), nat(1))
        r = self.say("what a lovely garden")
        self.assertEqual(r["result"], nat(2), r)
        self.assertEqual((self.field("heard"), self.field("fields")), (label("what a lovely garden"), nat(0)))


LENSED = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./Form.obend as Form
import ./World.obend as World
record State:
  name: String
  size: Nat
  mood: String
  origin: String
record Binding:
  name: String
  value: String
def initial() -> State:
  {name: "", size: 0n, mood: "", origin: ""}
def lenses() -> Lists.List<Form.Field>:
  Lists.List::<Form.Field>.cons({head: {name: "name", kind: Form.Kind.text({min: 1n, max: 12n})}, tail: Lists.List::<Form.Field>.cons({head: {name: "size", kind: Form.Kind.natural({min: 1n, max: 9n})}, tail: Lists.List::<Form.Field>.cons({head: {name: "mood", kind: Form.Kind.choice({options: Lists.List::<String>.cons({head: "calm", tail: Lists.List::<String>.cons({head: "wild", tail: Lists.List::<String>.nil()})})})}, tail: Lists.List::<Form.Field>.nil()})})})
def origin(context: Abi.Context) -> Plans.Edit<String, {}>:
  Plans.Edit.set({value: textConcat(context.inputOrigin.kind, textConcat("|", context.inputOrigin.command))})
def textEdit(field: String, value: String, context: Abi.Context) -> Edits:
  if field == "name" then extend(keep(), {name: Plans.Edit.set({value: value}), origin: origin(context)}) else extend(keep(), {mood: Plans.Edit.set({value: value}), origin: origin(context)})
def edit(field: String, value: Form.Value, context: Abi.Context) -> Edits:
  match value:
    case text(t): textEdit(field, t.value, context)
    case natural(n): extend(keep(), {size: Plans.Edit.set({value: n.value}), origin: origin(context)})
    case choice(c): textEdit(field, c.value, context)
def set(state: State, input: {field: String, value: Form.Value}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(edit(input.field, input.value, context))
  1n
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  2n
""")


# The lamp with `mood` fixed: set when the lamp is made, never by an edit, so no lens names it.
FIXED = (LENSED.replace("  mood: String\n  origin: String", "  mood: fixed String\n  origin: String", 1)
         .replace("  mood: Plans.Edit<String, {}>\n", "")
         .replace(" mood: Plans.Edit.keep({}),", "")
         .replace("extend(keep(), {mood: Plans.Edit.set({value: value}), origin: origin(context)})",
                  "extend(keep(), {name: Plans.Edit.set({value: value}), origin: origin(context)})"))


class FixedFields(Reflection):
    """A `fixed` State field (the artifact's `fixed`): the creating seed sets it; no lens offers it,
    `delvetalk <card> set` naming it is refused `fixed`, and world-inspect lists it."""

    def setUp(self):
        super().setUp()
        self.open_library()
        r = self.host.send(op="world-create", principal="ember", identity="mk-lamp", object="lamp",
                           modules=[{"name": "Lamp", "source": FIXED}], entry="initial", seed=record(mood=label("calm")))
        self.assertEqual(r["status"], "created", r)

    def say(self, text, identity=None):
        return self.turn("lamp", "receive", record(text=label(text), post=label("")), principal="glm", identity=identity)

    def field(self, name):
        return {f["name"]: f["value"] for f in self.state("lamp")["fields"]}[name]

    def test_a_fixed_field_is_set_at_creation_and_no_lens_names_it(self):
        self.assertEqual(self.field("mood"), label("calm"))
        inspected = self.host.send(op="world-inspect", principal="glm", object="lamp", source=False)
        self.assertEqual(inspected.get("fixed"), ["mood"], inspected)
        usage = self.say("delvetalk lamp ?")
        self.assertIn("delvetalk lamp set\nname: <text, 1 to 12 characters>", usage["text"])
        self.assertNotIn("mood", usage["text"])
        out = self.say("delvetalk lamp set\nmood: wild", identity="fix")["receipt"]["outcome"]
        self.assertEqual((out["class"], out["clause"]), ("badSpell", "fixed"), out)
        self.assertEqual(out["reason"], "mood is fixed; it is set when lamp is made and never after.")
        self.assertEqual(self.field("mood"), label("calm"))
        self.assertEqual(self.say("delvetalk lamp set\nname: Moth")["status"], "admitted")
        self.assertEqual(self.say("delvetalk lamp set")["result"], nat(2))  # set without a field is receive
        self.reopen()
        self.assertEqual(self.host.send(op="world-inspect", principal="glm", object="lamp", source=False).get("fixed"), ["mood"])

    def test_no_proposed_write_migration_or_reprogram_moves_a_fixed_field(self):
        keep = {"tag": "variant", "label": "keep", "payload": record()}
        edits = record(name=keep, size=keep, origin=keep, mood={"tag": "variant", "label": "set", "payload": record(value=label("wild"))})
        r = self.host.send(op="world-propose", principal="ember", identity="p1", roots=[{"object": "lamp", "version": 0}],
                           writes=[{"object": "lamp", "edits": [edits]}])
        out = r["receipt"]["outcome"]
        self.assertEqual((out["class"], out["clause"]), ("lawRefused", "fixed"), r)
        self.assertEqual(out["reason"], "refused fixed: mood is fixed; it is set when lamp is made and never after.")
        moved = FIXED + "def migrate(old: State) -> State:\n  {name: old.name, size: old.size, mood: \"wild\", origin: old.origin}\n"
        r = self.host.send(op="world-reprogram", principal="ember", identity="rp", object="lamp", version=0, package=moved, migration="migrate")
        out = r["receipt"]["outcome"]
        self.assertEqual((out["class"], out["clause"]), ("programRefused", "fixed"), r)
        self.assertIn("the migration sets mood, which is fixed", out["reason"])
        kept = FIXED + "def migrate(old: State) -> State:\n  {name: \"Moth\", size: old.size, mood: old.mood, origin: old.origin}\n"
        r = self.host.send(op="world-reprogram", principal="ember", identity="rp2", object="lamp", version=0, package=kept, migration="migrate")
        self.assertEqual(r["receipt"]["outcome"]["tag"], "admitted", r)
        self.assertEqual((self.field("mood"), self.field("name")), (label("calm"), label("Moth")))
        # codex host 5 / docs 1: code that no longer fixes `mood` would let a migration, or any later
        # write, move it.
        moved = LENSED + "def migrate(old: State) -> State:\n  {name: old.name, size: old.size, mood: \"wild\", origin: old.origin}\n"
        for identity, package, migration in (("u1", moved, "migrate"), ("u2", LENSED, "")):
            r = self.host.send(op="world-reprogram", principal="ember", identity=identity, object="lamp", version=1,
                               package=package, migration=migration)
            out = r["receipt"]["outcome"]
            self.assertEqual((out["class"], out.get("clause")), ("programRefused", "fixed"), r)
        self.assertEqual(self.field("mood"), label("calm"))


    def test_an_unchanged_spell_retry_after_a_reprogram_is_the_retained_receipt(self):
        # codex host 13: the retry was routed again, met the new code's refusal, and was answered
        # duplicateIdentity instead of the receipt the identity already holds.
        spell = "delvetalk lamp set\nname: Moth"
        first = self.say(spell, identity="s1")
        self.assertEqual(first["status"], "admitted", first)
        gone = FIXED.replace("def lenses()", "def unusedLenses()")
        r = self.host.send(op="world-reprogram", principal="ember", identity="rp", object="lamp", version=1, package=gone)
        self.assertEqual(r["status"], "admitted", r)
        self.assertNotEqual(self.say(spell, identity="s2")["status"], "admitted")
        again = self.say(spell, identity="s1")
        self.assertEqual((again["status"], again["receipt"]["hash"]), ("admitted", first["receipt"]["hash"]), again)


INTERPRETING = (GARDEN + """record Planting:
  colour: Colour
  seed: String
def colourField() -> Form.Field:
  {name: "colour", kind: Form.Kind.choice({options: Lists.List::<String>.cons({head: "amber", tail: Lists.List::<String>.cons({head: "violet", tail: Lists.List::<String>.cons({head: "silver", tail: Lists.List::<String>.nil()})})})})}
def offered() -> Lists.List<Form.Form>:
  Lists.List::<Form.Form>.cons({head: {card: "garden", action: "plant", fields: Lists.List::<Form.Field>.cons({head: colourField(), tail: Lists.List::<Form.Field>.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 40n})}, tail: Lists.List::<Form.Field>.nil()})})}, tail: Lists.List::<Form.Form>.nil()})
def joined(needs: Lists.List<String>) -> String:
  match needs:
    case nil(_): ""
    case cons(c): textConcat("|", textConcat(c.head, joined(c.tail)))
def ask(state: State, input: {utterance: String}, context: Abi.Context) -> Activity<String>:
  match world.interpret::<Planting>({utterance: input.utterance, offers: offered(), policy: {world: "", object: "policy"}, model: "", held: "", misfit: ""}):
    case proposal(p):
      let written(_) = world.write(extend(keep(), {planted: Plans.Edit.set({value: textConcat(colourText(p.argument.colour), textConcat(":", p.argument.seed))})}))
      "proposal"
    case unclear(u): textConcat("unclear", joined(u.needs))
    case _: "other"
""").replace("import ./World.obend as World", "import ./Form.obend as Form\nimport ./World.obend as World")


class Misfits(Reflection):
    """docs/OVERHAUL.md §2.7, HOST-HANDOFF 5.163: a direct turn's misfit spell (unknownField, noAction,
    badValue, otherCard) is hob's to read past, for every card and never by the card's `receive`: the turn
    waits on hob, shown the clause and reason and the card's table. hob's spell runs on the card as the
    speaker's turn; anything else settles as the host's `badSpell` with the usage hint, which is the answer
    at once in a world with no policy. A duplicate field or an unclosed block is refused always."""

    policy = True

    def setUp(self):
        super().setUp()
        self.open_library()
        if self.policy:
            self.make("policy", POLICY, record(model=label("m"), system=label(""), examples=label("")))
        r = self.host.send(op="world-create", principal="ember", identity="mk-plain", object="plain",
                           modules=[{"name": "Garden", "source": declared(GARDEN)}], entry="initial", seed=record())
        self.assertEqual(r["status"], "created", r)

    def say(self, text, identity=None):
        return self.turn("plain", "receive", record(text=label(text), post=label("")), principal="glm", identity=identity)

    def field(self, name):
        return {f["name"]: f["value"] for f in self.state("plain")["fields"]}[name]

    def settle(self, raw):
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"],
                                 reply={"status": "replied", "model": "m", "json": None, "raw": raw})
        return item, as_owner(self.host, settled["resumed"][0], "glm")

    def test_a_misfit_waits_on_hob_with_its_clause_and_none_is_the_hosts_refusal(self):
        r = self.say("delvetalk plain water")
        self.assertEqual(r["status"], "suspended", r)
        item, resumed = self.settle("none")
        self.assertEqual(item["object"], "plain")
        self.assertTrue(item["misfit"].startswith("noAction, plain has no spell water"), item)
        self.assertIn("plant", [o["action"] for o in item["offers"]])
        out = resumed["receipt"]["outcome"]
        self.assertEqual((out["tag"], out["class"], out["clause"]), ("refused", "badSpell", "noAction"), resumed)
        self.assertIn("delvetalk plain plant", out["hint"])
        # The card's `receive` never heard it.
        self.assertEqual(self.field("heard"), label(""))

    def test_hobs_spell_for_a_misfit_runs_on_the_card(self):
        self.assertEqual(self.say("delvetalk plain plant\ncolour: gold\nseed: rue")["status"], "suspended")
        _, resumed = self.settle("delvetalk plain plant\ncolour: amber\nseed: rue")
        self.assertEqual(resumed["receipt"]["outcome"]["tag"], "admitted", resumed)
        self.assertEqual(self.field("planted"), label("amber:rue"))
        self.assertEqual(self.field("origin"), label("interpreted|delvetalk plain plant\ncolour: amber\nseed: rue"))

    POST = "delvetalk plain water\n\ndelvetalk plain plant\ncolour: amber\nseed: x\n\ndelvetalk plain plant\ncolour: gold\nseed: rue"

    def test_a_posts_misfit_spells_are_one_reading_after_the_spells_that_run(self):
        r = self.say(self.POST, identity="post")
        self.assertEqual([t["status"] for t in r["turns"]], ["admitted", "suspended"], r)
        self.assertEqual(self.field("planted"), label("amber:x"))
        # A retry answers each from its identity: nothing more is asked.
        again = self.say(self.POST, identity="post")
        self.assertEqual([t["receipt"]["hash"] for t in again["turns"]], [t["receipt"]["hash"] for t in r["turns"]])
        item, resumed = self.settle("delvetalk plain plant\ncolour: violet\nseed: rue")
        self.assertEqual((item["object"], item["utterance"]), ("plain", "delvetalk plain water\n\ndelvetalk plain plant\ncolour: gold\nseed: rue"))
        self.assertTrue(item["misfit"].startswith("noAction, delvetalk plain water: plain has no spell water"), item)
        self.assertIn("delvetalk plain plant: ", item["misfit"])
        self.assertEqual(resumed["receipt"]["outcome"]["tag"], "admitted", resumed)
        self.assertEqual(self.field("planted"), label("violet:rue"))

    def test_the_strict_clauses_refuse_at_once(self):
        for i, (text, clause) in enumerate((("delvetalk plain plant\ncolour: amber\ncolour: amber\nseed: x", "duplicateField"),
                                            ("delvetalk plain plant\nseed: <<END\nfern\n", "unclosedBlock"))):
            r = self.say(text, identity="s%d" % i)
            self.assertEqual((r["status"], r["receipt"]["outcome"]["clause"]), ("refused", clause), r)



class MisfitsWithoutPolicy(Misfits):
    """A world with no policy has no hob: a misfit is the host's refusal at once."""
    policy = False

    def test_a_misfit_waits_on_hob_with_its_clause_and_none_is_the_hosts_refusal(self):
        r = self.say("delvetalk plain water")
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out["clause"]), ("refused", "badSpell", "noAction"), r)
        self.assertIn("delvetalk plain plant", out["hint"])
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_hobs_spell_for_a_misfit_runs_on_the_card(self):
        self.assertEqual(self.say("delvetalk plain plant\ncolour: gold\nseed: rue")["receipt"]["outcome"]["clause"], "badValue")

    def test_a_posts_misfit_spells_are_one_reading_after_the_spells_that_run(self):
        r = self.say(self.POST, identity="post")
        self.assertEqual([(t["status"], t["receipt"]["outcome"].get("clause")) for t in r["turns"]],
                         [("admitted", None), ("refused", "noAction"), ("refused", "badValue")], r)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])


class Interpreted(Reflection):
    """The model's text fitted as a spell against the offered forms (WHOLENESS §2, "Interpretation"):
    a fitting spell is the form's proposal, a misfit or a spell missing fields is `unclear` naming why,
    a bare field line naming an offered field is that form's spell, and prose with no spell is `unclear: not addressed`."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("policy", POLICY, record(model=label("m"), system=label(""), examples=label("")))
        r = self.host.send(op="world-create", principal="ember", identity="mk-garden", object="garden",
                           modules=[{"name": "Garden", "source": declared(INTERPRETING)}], entry="initial", seed=record())
        self.assertEqual(r["status"], "created", r)

    def interpret(self, raw):
        self.n = getattr(self, "n", 0) + 1
        r = self.turn("garden", "ask", record(utterance=label("plant something")), identity=f"ask{self.n}")
        self.assertEqual(r["status"], "suspended", r)
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"],
                                 reply={"status": "replied", "model": "m", "json": None, "raw": raw})
        return settled["receipt"]["outcome"]["verdict"], as_owner(self.host, settled["resumed"][0])["result"]

    # World.obend's proposal names its object (`proposal {object, method, argument}`, HOST-HANDOFF 5.64).
    def test_a_fitting_spell_is_a_proposal_and_a_misfit_unclear(self):
        verdict, result = self.interpret("Sure.\ndelvetalk garden plant\ncolour: violet\nseed: rue")
        self.assertEqual((verdict["tag"], verdict["method"]), ("proposal", "plant"), verdict)
        self.assertEqual(result, label("proposal"))
        self.assertEqual({f["name"]: f["value"] for f in self.state("garden")["fields"]}["planted"], label("violet:rue"))
        # A misfit, a spell missing fields, or another action is unclear naming why.
        self.assertEqual(self.interpret("delvetalk garden plant\ncolour: gold\nseed: rue")[0],
                         {"tag": "unclear", "needs": ["colour is one of: amber, violet, silver"]})
        self.assertEqual(self.interpret("delvetalk garden plant\ncolour: amber")[0], {"tag": "unclear", "needs": ["seed"]})
        self.assertEqual(self.interpret("delvetalk garden water")[0],
                         {"tag": "unclear", "needs": ["garden water is not one of the offered actions"]})


if __name__ == "__main__":
    unittest.main()
