"""Grown verbs (docs/COLLABORATOR.md §3; docs/OVERHAUL.md §2): a verb is a row the host keeps on a thing, grown
by a hand with `grow` (a placing of kind `rule`, judged by the thing's law with `request.verb` `grow`), credited
to its grower, sixteen at most; the spell grammar reads it exactly as a declared form, and its use runs the
thing's `act {verb, text}` with `request.verb` the verb, so a rule reading `request.verb` is its consequence
(`does`, placed in the same entry). hob answers words with the spell meant, `grow:` and the spell that uses it,
`ask:` or `none`.

Evidence for OVERHAUL §5 step 3's grown verbs (layer: host). Refuted by a grown verb whose spell does not run
`act`, a use that does not carry its verb to the law and the rules, a grow the law cannot refuse, a verb lost
across a reopen, or hob's `grow:` not proposing the grow and the use in one answer.
"""
import unittest

from tests.host import as_owner
from tests.test_chain import Chain
from tests.test_policy import PolicyObject
from tests.test_reflection import Reflection
from tests.wire import field, label, nat, record
from tests.bend import closure, declared

THING = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record Binding:
  name: String
  value: String
record State:
  owner: String
  rains: Nat
  acts: Nat
  last: String
  verb: String
def initial() -> State:
  {owner: "", rains: 0n, acts: 0n, last: "", verb: ""}
def rain(state: State, input: {text: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {rains: add 1n, last: set input.text}
  state.rains + 1n
def act(state: State, input: {verb: String, text: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {acts: add 1n, last: set input.text, verb: set input.verb}
  state.acts + 1n
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  0n
""", "rain", "act", "receive")

# A thing with no `act`: no verb grows on it.
STONE = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record Binding:
  name: String
  value: String
record State:
  owner: String
  rains: Nat
def initial() -> State:
  {owner: "", rains: 0n}
def rain(state: State, input: {text: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {rains: add 1n}
  state.rains + 1n
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  0n
""", "rain", "receive")

WATER = "delvetalk bell grow\nname: water\nreading: poured on by a hand; a line, and the bell is tended"


class Verbs(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("bell", THING, record(owner=label("ember")))

    def say(self, text, who="glm", card="bell"):
        return self.turn(card, "receive", record(text=label(text), post=label("")), principal=who)

    def value(self, name, card="bell"):
        return field(self.state(card), name)["value"]

    def entry(self, reply):
        """The whole entry, as its own principal reads it."""
        return self.host.send(op="world-entry", principal=reply["receipt"]["identity"]["principal"],
                              hash=reply["receipt"]["hash"])["receipt"]

    def test_a_verb_grown_by_a_hand_is_a_spell_of_the_card_that_runs_act_with_its_verb(self):
        grown = self.say(WATER)
        self.assertEqual(grown["status"], "admitted", grown)
        self.assertEqual(self.entry(grown)["outcome"]["placements"],
                         [{"object": "bell", "verb": "water", "reading": "poured on by a hand; a line, and the bell is tended", "takes": "text"}])
        # The card's usage and `verbs` print it with its grower and the entry that grew it.
        usage = self.say("delvetalk bell ?")
        self.assertIn("delvetalk bell water\ntext:", usage["text"])
        self.assertNotIn("delvetalk bell act", usage["text"])
        verbs = self.say("delvetalk bell verbs", who="kimi")
        self.assertIn("Declared by its kind: rain.", verbs["text"])
        self.assertIn("» water (grown by glm, entry %d)" % grown["receipt"]["height"], verbs["text"])
        # Anyone uses it, exactly and free: the host runs `act`, and the write's verb is the grown one.
        used = self.say("delvetalk bell water\ntext: I water the bell", who="kimi")
        self.assertEqual((used["status"], used["result"]), ("admitted", nat(1)), used)
        self.assertEqual((self.value("verb"), self.value("last")), ("water", "I water the bell"))
        [written] = self.entry(used)["outcome"]["writes"]
        self.assertEqual((written["object"], written["methods"], written["verbs"]), ("bell", ["act"], ["water"]))
        # The inspect a card reads offers it among its forms, and never `act`.
        forms = self.host.send(op="world-inspect", principal="kimi", object="bell")["offered"]
        self.assertEqual(forms, ["rain", "water"])
        # The strokes a paint reads hold it once, with its grower and reading, after the kind's.
        strokes = self.host.send(op="world-strokes", principal="kimi", object="bell")["strokes"]
        self.assertEqual([(v["name"], v.get("by", ""), v.get("reading", "")) for v in strokes["verbs"]],
                         [("rain", "", ""), ("water", "glm", "poured on by a hand; a line, and the bell is tended")])
        self.assertEqual(strokes["verbs"][1]["spell"], "delvetalk bell water / text: <text, 1 to 1400 characters>")

    def test_a_rule_reading_request_verb_is_the_verbs_consequence_and_does_places_it_with_the_verb(self):
        grown = self.say(WATER + "\ndoes: delvetalk bell rain / text: watered")
        self.assertEqual(grown["status"], "admitted", grown)
        placed = self.entry(grown)["outcome"]["placements"]
        self.assertEqual([p.get("verb") or p.get("rule") for p in placed], ["water", "water"])
        self.assertEqual(placed[0]["does"], "water")
        rules = {r["name"]: r for r in self.host.send(op="world-rules", principal="ember", object="bell")["rows"]}
        self.assertEqual((rules["water"]["owner"], rules["water"]["when"]), ("glm", 'request.verb == "water"'))
        # A rain is no water: the rule holds only of the verb's use, which fires it under the grower.
        self.say("delvetalk bell rain\ntext: rain", who="kimi")
        self.assertEqual(self.value("rains"), "1")
        used = self.say("delvetalk bell water\ntext: from the can", who="kimi")
        self.assertEqual([f["rule"] for f in used["receipt"]["fired"]], ["water"], used)
        self.assertIn("rule water of glm fired: delvetalk bell rain / text: watered", used["revealed"][0])
        self.assertEqual((self.value("rains"), self.value("last")), ("2", "watered"))
        # `ungrow` by a stranger is refused; by its grower it takes the verb and the rule it does.
        self.assertEqual(self.say("delvetalk bell ungrow\nname: water", who="kimi")["receipt"]["outcome"]["clause"], "notPlacer")
        gone = self.say("delvetalk bell ungrow\nname: water")
        self.assertEqual(gone["status"], "admitted", gone)
        self.assertEqual(self.host.send(op="world-rules", principal="ember", object="bell")["rows"], [])
        self.assertEqual(self.say("delvetalk bell water\ntext: again", who="kimi")["receipt"]["outcome"]["clause"], "noAction")

    def test_the_law_judges_a_grow_and_the_names_and_bounds_hold(self):
        def refused(text, who="glm", card="bell"):
            r = self.say(text, who=who, card=card)
            self.assertEqual(r["status"], "refused", r)
            o = r["receipt"]["outcome"]
            return o.get("clause") or o["class"], o.get("reading") or o.get("reason") or ""
        # A declared form, a host spell and a grown verb are taken names.
        self.assertEqual(refused(WATER.replace("name: water", "name: rain"))[0], "nameTaken")
        self.assertEqual(refused(WATER.replace("name: water", "name: rule"))[0], "nameTaken")
        self.assertEqual(self.say(WATER)["status"], "admitted")
        self.assertEqual(refused(WATER)[0], "nameTaken")
        self.assertEqual(refused(WATER.replace("name: water", "name: Two Words"))[0], "verb")
        self.assertEqual(refused(WATER.replace("poured on", "x" * 201))[0], "verb")
        self.assertEqual(refused(WATER.replace("name: water", "name: soak") + "\ntakes: a bucket")[0], "badValue")
        # Sixteen a thing.
        for i in range(15):
            self.assertEqual(self.say(WATER.replace("name: water", "name: v%d" % i))["status"], "admitted", i)
        clause, reason = refused(WATER.replace("name: water", "name: v99"))
        self.assertEqual(clause, "capacity")
        self.assertIn("verbsPerObject", reason)
        # A thing with no act grows nothing, by name.
        self.make("stone", STONE, record(owner=label("ember")))
        self.assertEqual(refused(WATER.replace("bell", "stone", 1), card="stone")[0], "act")
        # A direct act naming a verb nobody grew is refused: act runs only grown verbs.
        r = self.turn("bell", "act", record(verb=label("sing"), text=label("la")), principal="kimi")
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "noMethod"), r)

    def test_a_law_that_refuses_grows_refuses_them_by_name_and_still_admits_rules(self):
        adopted = self.say('delvetalk bell adopt\nlaw: law kept "verbs are the owner\'s": request.verb == "grow" implies request.subject == new.owner', who="ember")
        self.assertEqual(adopted["status"], "admitted", adopted)
        r = self.say(WATER)
        self.assertEqual((r["status"], r["receipt"]["outcome"].get("clause")), ("refused", "kept"), r)
        rule = self.say("delvetalk bell rule\nname: two\nwhen: count(new.rains) >= 2\nthen: delvetalk me note / text: two")
        self.assertEqual(rule["status"], "admitted", rule)
        # The usage offers grow only to whom the law admits it.
        self.assertNotIn("delvetalk bell grow", self.say("delvetalk bell ?")["text"])
        self.assertIn("delvetalk bell grow", self.say("delvetalk bell ?", who="ember")["text"])
        self.assertEqual(self.say(WATER, who="ember")["status"], "admitted")

    def test_a_grown_verb_survives_a_reopen_and_a_snapshot(self):
        grown = self.say(WATER)
        self.assertEqual(grown["status"], "admitted", grown)
        self.reopen()
        self.assertEqual(self.say("delvetalk bell water\ntext: after", who="kimi")["status"], "admitted")
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertIn("» water (grown by glm, entry %d)" % grown["receipt"]["height"], self.say("delvetalk bell verbs")["text"])

    def test_a_spell_naming_no_verb_says_how_it_grows(self):
        r = self.say("delvetalk bell water\ntext: x", who="kimi")
        self.assertEqual(r["receipt"]["outcome"]["clause"], "noAction", r)
        self.assertIn("and water grows on it: delvetalk bell grow / name: water / reading: <what it does>",
                      r["receipt"]["outcome"]["reason"])


# hob reads words into a verb the card does not take yet: `grow:` and the spell that uses it, answered as two
# proposals, which the asking card calls in order; the grow is staged and the use sees it in the same turn.
HUB = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  asked: Nat
def initial() -> State:
  {asked: 0n}
def ask(state: State, input: {text: String}, context: Abi.Context) -> Activity<String>:
  match world.interpret::<Data>({utterance: input.text, offers: Lists.List::<Form.Form>.nil({}), policy: {world: "", object: "policy"}, model: "", held: "", misfit: ""}):
    case proposals(p): each(p.items, "")
    case unclear(u): "unclear"
    case _: "other"
def each(items: Lists.List<World.Proposed<Data>>, said: String) -> Activity<String>:
  match items:
    case nil(_): said
    case cons(c): one(c.head, c.tail, said)
def one(item: World.Proposed<Data>, rest: Lists.List<World.Proposed<Data>>, said: String) -> Activity<String>:
  match item:
    case proposal(p): passOn(p.object, p.method, p.argument, rest, said)
    case unclear(_): each(rest, "{said} unclear")
def passOn(object: String, method: String, argument: Data, rest: Lists.List<World.Proposed<Data>>, said: String) -> Activity<String>:
  match world.call::<Data>({object: {world: "", object: object}, method: method, argument: argument}):
    case returned(_): each(rest, "{said} {method}")
    case refused(r): each(rest, "{said} refused {r.clause}")
    case _: each(rest, "{said} denied")
""", "ask")


class Grow(Chain):
    policy = PolicyObject.policy

    def setUp(self):
        super().setUp()
        self.policy()
        base = closure("Abi", "List", "Form", "Plan", "World")
        self.make("bell", base + [{"name": "Thing", "source": THING}], record(owner=label("ember")))
        self.make("hub", base + [{"name": "Hub", "source": HUB}], record())

    def ask(self, raw):
        asked = self.turn("hub", "ask", record(text=label("I water the bell")), principal="glm")
        self.assertEqual(asked["status"], "suspended", asked)
        [pending] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=pending["id"],
                                 reply={"status": "replied", "json": None, "raw": raw, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return settled["receipt"]["outcome"]["verdict"], resumed

    def test_hobs_grow_proposes_the_grow_and_the_use_and_one_turn_runs_both(self):
        verdict, resumed = self.ask('grow: water "poured on by a hand; a line, and the bell is tended"\n'
                                    'delvetalk bell water\ntext: I water the bell')
        self.assertEqual(verdict["tag"], "proposals", verdict)
        grow, use = verdict["items"]
        self.assertEqual((grow["object"], grow["method"]), ("bell", "grow"), grow)
        self.assertEqual(grow["spell"], "delvetalk bell grow\nname: water\nreading: poured on by a hand; a line, and the bell is tended")
        self.assertEqual((use["object"], use["method"], use["spell"]), ("bell", "act", "delvetalk bell water\ntext: I water the bell"), use)
        self.assertEqual((resumed["status"], resumed["result"]["value"]), ("admitted", " grow act"), resumed)
        self.assertEqual((field(self.state("bell"), "verb")["value"], field(self.state("bell"), "last")["value"]),
                         ("water", "I water the bell"))
        rows = self.turn("bell", "receive", record(text=label("delvetalk bell verbs"), post=label("")), principal="kimi")
        self.assertIn("» water (grown by glm, entry %d)" % resumed["receipt"]["height"], rows["text"])

    def test_a_grow_whose_spell_uses_another_verb_is_unclear(self):
        verdict, _ = self.ask('grow: water "poured on"\ndelvetalk bell rain\ntext: x')
        self.assertEqual(verdict, {"tag": "unclear", "needs": ["the spell after grow: water uses rain"]})


class Town(unittest.TestCase):
    """Grown verbs on the town's own things, as genesis makes them (docs/AUTHORING.md §5 step 1): RECORD and
    THING keep `act` from usage (`~act`) and list their own `actions`, so a verb grown on them is a spell only
    when the host offers it by the law alone. Refuted by a grown verb missing from `?`, its use going to hob, or
    its line not carrying the verb."""

    YUE, KES = "did:plc:yueyueyueyueyueyueyueyue", "did:plc:kestrelkestrelkestrelkes"

    @classmethod
    def setUpClass(cls):
        import tempfile
        from tests.town import Town as Genesis
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Genesis(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        for did, handle in ((cls.YUE, "yue.delve.town"), (cls.KES, "kestrel.delve.town")):
            cls.town.send(op="world-arrive", principal="transport", did=did, handle=handle)

    def say(self, who, card, text):
        Town.said = getattr(Town, "said", 0) + 1
        return self.town.send(op="world-turn", principal=who, object=card, method="receive", identity="said-%d" % Town.said,
                              argument=record(text=label(text), post=label("")))

    def told(self, reply):
        return "".join(o["text"] for o in reply.get("offers") or [])

    def grown_and_used(self, card):
        grown = self.say(self.YUE, card, "delvetalk %s grow / name: water / reading: poured on by a hand / takes: text" % card)
        self.assertEqual(grown["status"], "admitted", grown)
        usage = self.say(self.KES, card, "delvetalk %s ?" % card)
        self.assertIn("delvetalk %s water\ntext:" % card, usage["text"])
        self.assertNotIn("delvetalk %s act" % card, usage["text"])
        used = self.say(self.KES, card, "delvetalk %s water / text: a cup" % card)
        self.assertEqual(used["status"], "admitted", used)
        [written] = self.town.send(op="world-entry", principal=self.KES, hash=used["receipt"]["hash"])["receipt"]["outcome"]["writes"]
        self.assertEqual((written["object"], written["methods"], written["verbs"]), (card, ["act"], ["water"]))
        return used

    def test_a_verb_grown_on_a_genesis_bell_is_its_spell(self):
        used = self.grown_and_used("bell/1")
        self.assertIn("kestrel.delve.town (yours) (water): a cup", self.told(used))

    def test_a_verb_grown_on_a_genesis_thing_is_its_spell(self):
        used = self.grown_and_used("porch/goblet")
        self.assertIn("water: a cup", self.told(used))

    def test_a_verb_grown_on_a_thing_of_a_residents_kind_is_its_spell(self):
        made = self.say(self.YUE, "kinds", "delvetalk kinds make / name: jar / of: record / form: what: text 1..80")
        self.assertEqual(made["status"], "admitted", made)
        jar = self.say(self.KES, "kind/jar", "delvetalk kind/jar make / what: a jar of rain")
        self.assertEqual(jar["status"], "admitted", jar)
        self.grown_and_used("jar/1")


if __name__ == "__main__":
    unittest.main()
