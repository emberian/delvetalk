"""An interpretation's proposal names the card whose form it fitted (HOST-HANDOFF 5.64).

Evidence for interpretation (layer: host).

A message-dialect object that offers forms of several cards (the Directory offers its doors')
hears a model's spell as `proposal {object, method, argument}`, checked against the object the
fitted form names, not the asking one; the asker then calls that object. Refuted by: the
proposal checked against the asker (`unclear`, since the asker has no `plant`), the proposal
lacking `object`, the call not reaching the garden, or a form naming a method its card does not
offer being proposed.
"""
import unittest

from transport.journal import entries as journal_entries

from tests.host import as_owner, bounds

from tests.test_chain import Chain
from tests.test_policy import PolicyObject
from tests.wire import cid_of, field, label, listing, nat, record, variant
from tests.test_heard import HeardCase, BELL
from tests.test_snapshot import read_snapshot, write_snapshot
from tests.bend import MODULES, closure, declared

WORLD_LINE = "  proposal: {object: String, method: String, argument: R, spell: String}"

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
def offered(card: String, action: String) -> World.Forms:
  Lists.List::<Form.Form>.cons({head: {card: card, action: action, fields: Lists.List::<Form.Field>.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 140n})}, tail: Lists.List::<Form.Field>.nil({})})}, tail: Lists.List::<Form.Form>.nil({})})
def ask(state: State, input: {text: String, card: String, action: String}, context: Abi.Context) -> Activity<String>:
  match world.interpret::<Data>({utterance: input.text, offers: offered(input.card, input.action), policy: {world: "", object: "policy"}, model: ""}):
    case proposal(p): passOn(p.object, p.method, p.argument)
    case unclear(u): "unclear"
    case _: "other"
def passOn(object: String, method: String, argument: Data) -> Activity<String>:
  match world.call::<Data>({object: {world: "", object: object}, method: method, argument: argument}):
    case returned(_): "passed {object} {method}"
    case _: "refused"
""", "ask")

GARDEN = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  planted: Nat
  last: String
def initial() -> State:
  {planted: 0n, last: ""}
def plant(state: State, input: {seed: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {planted: add 1n, last: set input.seed}
  state.planted + 1n
def tend(state: State, input: {seed: String}, context: Abi.Context) -> Activity<Nat>:
  0n
""", "plant")


# hob's reply that stopped the second playtest (message 69158; journal height 349), verbatim: prose, no spell.
PLAYTEST_69158 = "That's a good result to see end to end: a clause you wrote, with your own name and reading, parsed, enforced on the first attempt, and the receipt quoted your words back. The refusal reads as the card's own voice, not a generic error, which is the point of putting the reading next to the law.\n\nI'm the card's hob here, so I should be plain about what I did and didn't do: I'm not going to add a spell from this message, since it's a comment on the mechanism rather than a request to act on the card. If you want something run, tell me the spell in words, for example \"delvetalk garden plant, seed: ..., colour: ...\", and I'll answer with the spell or ask for what's missing."


class ProposalForAnotherCard(Chain):
    policy = PolicyObject.policy

    def modules(self, name, source):
        with open(MODULES["World"], encoding="utf-8") as f:
            self.assertIn(WORLD_LINE, f.read())
        out = closure(*("Abi", "List", "Form", "Plan", "World"))
        return out + [{"name": name, "source": source}]

    def setUp(self):
        super().setUp()
        self.policy()
        self.make("hub", self.modules("Hub", HUB), record())
        self.make("g", self.modules("Garden", GARDEN), record())

    def ask(self, text, card="g", action="plant"):
        asked = self.turn("hub", "ask", record(text=label("plant a fern"), card=label(card), action=label(action)), principal="glm")
        self.assertEqual(asked["status"], "suspended", asked)
        [pending] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "raw": text, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return settled, resumed

    def test_the_proposal_names_the_garden_and_the_hub_calls_it(self):
        settled, resumed = self.ask("delvetalk g plant\nseed: a fern")
        verdict = settled["receipt"]["outcome"]["verdict"]
        self.assertEqual((verdict["tag"], verdict["object"], verdict["method"]), ("proposal", "g", "plant"), verdict)
        self.assertEqual((resumed["status"], resumed["result"]["value"]), ("admitted", "passed g plant"), resumed)
        state = {f["name"]: f["value"] for f in self.state("g")["fields"]}
        self.assertEqual((state["planted"]["value"], state["last"]["value"]), ("1", "a fern"))

    def test_overlapping_readings_settle_after_an_offered_cards_state_moves(self):
        for identity in ("first-reading", "second-reading"):
            waiting = self.turn("hub", "ask", record(text=label("plant a fern"), card=label("g"), action=label("plant")),
                                principal="glm", identity=identity)
            self.assertEqual(waiting["status"], "suspended", waiting)
        pending = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(len(pending), 2)
        self.assertEqual(len({item["id"] for item in pending}), 2)
        reply = {"status": "replied", "json": None, "raw": "delvetalk g plant / seed: a fern", "model": "m"}
        for n, item in enumerate(pending, 1):
            settled = self.host.send(op="world-interpretation", id=item["id"], reply=reply)
            self.assertEqual(settled["status"], "interpreted", settled)
            self.assertEqual(field(self.state("g"), "planted"), nat(n), settled)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.reopen()
        self.assertEqual(field(self.state("g"), "planted"), nat(2))

    def test_a_plant_keeps_offered_revisions_and_the_next_heard_reading_still_plants(self):
        PolicyObject.garden(self)
        for identity in ("heard-first", "heard-second"):
            waiting = PolicyObject.say(self, "a fern, maybe", identity=identity)
            self.assertEqual(waiting["status"], "suspended", waiting)
        pending = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(len(pending), 2)
        reading = pending[1]["roots"]
        self.assertEqual(reading, pending[0]["roots"])
        reply = PolicyObject.raw(self, "delvetalk garden plant\nseed: a fern that remembers\ncolour: silver")
        first = self.host.send(op="world-interpretation", id=pending[0]["id"], reply=reply)
        [ran] = [as_owner(self.host, r) for r in first["resumed"]]
        self.assertEqual(ran["status"], "admitted", ran)
        self.assertEqual(len(PolicyObject.things(self)), 1)
        snap = self.host.send(op="world-snapshot")
        self.assertEqual(snap["status"], "snapshot", snap)
        stored = {o["id"]: o for o in read_snapshot(self.path + ".snapshot.%d.cbor" % snap["height"])["objects"]}
        for root in reading:
            self.assertEqual(stored[root["object"]].get("behaviour", 0), root["behaviour"], root)
        [garden] = [r for r in reading if r["object"] == "garden"]
        self.assertGreater(stored["garden"]["version"], garden["version"])
        second = self.host.send(op="world-interpretation", id=pending[1]["id"], reply=reply)
        [ran] = [as_owner(self.host, r) for r in second["resumed"]]
        self.assertEqual(ran["status"], "admitted", ran)
        [acted] = [r for r in ran["receipt"]["roots"] if r["object"] == "garden"]
        self.assertEqual(acted, {"object": "garden", "version": stored["garden"]["version"], "behaviour": garden["behaviour"]})
        self.assertEqual(len(PolicyObject.things(self)), 2)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.reopen()
        self.assertEqual(len(PolicyObject.things(self)), 2)

    def test_a_bend_interpret_reoffers_after_a_rule_on_its_offered_card_is_removed(self):
        self.make("speaker", self.modules("Speaker", BELL), record(owner=label("ember")))
        placed = self.turn("speaker", "receive", record(text=label('delvetalk g rule / name: planting / when: request.method == "plant" / then: delvetalk g plant / seed: echo'),
                                                        post=label(""), fields=listing([])))
        self.assertEqual(placed["status"], "admitted", placed)
        waiting = self.turn("hub", "ask", record(text=label("plant a fern"), card=label("g"), action=label("plant")), principal="glm")
        self.assertEqual(waiting["status"], "suspended", waiting)
        [item] = self.host.send(op="world-interpretations")["pending"]
        removed = self.turn("speaker", "receive", record(text=label("delvetalk g unrule / name: planting"), post=label(""), fields=listing([])))
        self.assertEqual(removed["status"], "admitted", removed)
        reply = {"status": "replied", "json": None, "raw": "delvetalk g plant / seed: a fern", "model": "m"}
        settled = self.host.send(op="world-interpretation", id=item["id"], reply=reply)
        [again] = settled["resumed"]
        self.assertEqual(again["status"], "suspended", again)
        self.assertIn("rerunOf", again)
        stale = [e for e in journal_entries(self.path) if e["hash"] == again["rerunOf"]][0]["outcome"]
        self.assertEqual((stale["class"], stale["object"]), ("staleRoot", "g"))
        self.assertIn("g's behaviour changed", stale["reason"])
        self.assertEqual(field(self.state("g"), "planted"), nat(0))
        [fresh] = self.host.send(op="world-interpretations")["pending"]
        self.assertNotEqual(fresh["id"], item["id"])
        self.assertEqual([r for r in fresh["roots"] if r["object"] == "g"], [{"object": "g", "version": 0, "behaviour": 2}])
        finished = self.host.send(op="world-interpretation", id=fresh["id"], reply=reply)
        [ran] = [as_owner(self.host, r) for r in finished["resumed"]]
        self.assertEqual(ran["status"], "admitted", ran)
        self.assertEqual(field(self.state("g"), "planted"), nat(1))
        self.assertEqual([r for r in ran["receipt"]["roots"] if r["object"] == "g"], [{"object": "g", "version": 0, "behaviour": 2}])
        self.reopen()

    def test_hobs_answers_that_are_no_spell(self):
        # docs/OVERHAUL.md §2: hob answers the spell meant, `grow:` with its spell, `ask: <question>` or `none`, and
        # states no fact: `say:` and `card` are gone, read as any prose with no spell is, silence (the second
        # playtest's stop, 69158, verbatim below; 69275, hob's `say:` stating a falsehood that was believed).
        answer = "A kind is a template for a made thing. The make form takes a name and an of."
        for said, verdict in (("none", {"tag": "unclear", "needs": ["not addressed"]}),
                              ("  None\n", {"tag": "unclear", "needs": ["not addressed"]}),
                              ("card", {"tag": "unclear", "needs": ["not addressed"]}),
                              ("ask: which seed, 1 to 140 characters?", {"tag": "unclear", "needs": ["which seed, 1 to 140 characters?"]}),
                              ("say: " + answer, {"tag": "unclear", "needs": ["not addressed"]}),
                              (answer, {"tag": "unclear", "needs": ["not addressed"]}),
                              (PLAYTEST_69158, {"tag": "unclear", "needs": ["not addressed"]})):
            settled, _ = self.ask(said)
            self.assertEqual(settled["receipt"]["outcome"]["verdict"], verdict, said)


# MENU §2.2: a reply with several spells is `proposals {items}`, each item a proposal or `unclear`.
MULTI = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  asked: Nat
def initial() -> State:
  {asked: 0n}
def form(action: String) -> Form.Form:
  {card: "g", action: action, fields: Lists.List::<Form.Field>.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 140n})}, tail: Lists.List::<Form.Field>.nil({})})}
def offered() -> World.Forms:
  Lists.List::<Form.Form>.cons({head: form("plant"), tail: Lists.List::<Form.Form>.cons({head: form("tend"), tail: Lists.List::<Form.Form>.nil({})})})
def ask(state: State, input: {text: String}, context: Abi.Context) -> Activity<String>:
  match world.interpret::<Data>({utterance: input.text, offers: offered(), policy: {world: "", object: "policy"}, model: ""}):
    case proposals(p): passAll(p.items, "")
    case proposal(p): "one {p.method}"
    case unclear(u): "unclear"
    case _: "other"
def passAll(items: Lists.List<World.Proposed<Data>>, said: String) -> Activity<String>:
  match items:
    case nil(_): said
    case cons(c): passOne(c.head, c.tail, said)
def passOne(item: World.Proposed<Data>, rest: Lists.List<World.Proposed<Data>>, said: String) -> Activity<String>:
  match item:
    case proposal(p):
      match world.call::<Data>({object: {world: "", object: p.object}, method: p.method, argument: p.argument}):
        case returned(_): passAll(rest, textConcat(said, "+{p.method}"))
        case _: passAll(rest, textConcat(said, "!{p.method}"))
    case unclear(_): passAll(rest, textConcat(said, "?"))
""", "ask")


class SeveralSpells(Chain):
    policy = PolicyObject.policy
    modules = ProposalForAnotherCard.modules

    def setUp(self):
        super().setUp()
        self.policy()
        self.make("hub", self.modules("Multi", MULTI), record())
        self.make("g", self.modules("Garden", GARDEN), record())

    def ask(self, text):
        asked = self.turn("hub", "ask", record(text=label("plant two")), principal="glm")
        self.assertEqual(asked["status"], "suspended", asked)
        [pending] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "raw": text, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return settled["receipt"]["outcome"]["verdict"], resumed

    def test_two_spells_and_a_misfit_are_three_items_in_order(self):
        verdict, resumed = self.ask("Here you go:\ndelvetalk g plant\nseed: a fern\ndelvetalk g plant\nseed: a moss\n"
                                    "delvetalk g tend\nseed: x")
        self.assertEqual(verdict["tag"], "proposals", verdict)
        self.assertEqual([i["tag"] for i in verdict["items"]], ["proposal", "proposal", "unclear"], verdict)
        self.assertEqual([i.get("argument") for i in verdict["items"][:2]], [record(seed=label("a fern")), record(seed=label("a moss"))])
        self.assertIn("tend is not a method g offers", verdict["items"][2]["reasons"][0])
        self.assertEqual((resumed["status"], resumed["result"]["value"]), ("admitted", "+plant+plant?"), resumed)
        state = {f["name"]: f["value"] for f in self.state("g")["fields"]}
        self.assertEqual((state["planted"]["value"], state["last"]["value"]), ("2", "a moss"))


class BehaviorReadings(HeardCase):
    """An offered card's placements change its behaviour, without moving ordinary state roots."""

    def place(self, spell, card="bell", who="ember"):
        ran = self.say("delvetalk %s %s" % (card, spell), card=card, who=who)
        self.assertEqual(ran["status"], "admitted", ran)
        return ran

    def reading(self, card="bell"):
        waiting = self.say("water it for me", card=card)
        self.assertEqual(waiting["status"], "suspended", waiting)
        [item] = self.pending()
        return waiting, item

    def stale(self, raw, card="bell"):
        _, ran = self.settle(raw)
        out = ran["receipt"]["outcome"]
        self.assertEqual((ran["status"], out["class"], out["object"]), ("refused", "staleRoot", card), ran)
        self.assertIn(card, out["reason"])
        self.assertIn("behaviour changed", out["reason"])
        self.assertEqual(ran["public"]["reason"], out["reason"])
        self.assertIn("behaviour", ran["public"]["root"])
        self.assertEqual((self.value("acts"), self.value("rains")), ("0", "0"))
        self.assertEqual(self.pending(), [])
        return ran

    def test_ungrow_while_the_model_waits_refuses_the_old_reading(self):
        self.place('grow / name: water / reading: poured on by a hand')
        waiting, item = self.reading()
        self.assertIn("water", [o["action"] for o in item["offers"]])
        self.place("ungrow / name: water")
        ran = self.stale("delvetalk bell water / text: water it for me")
        self.assertEqual(item["roots"], waiting["receipt"]["roots"])
        self.assertEqual(ran["receipt"]["roots"], item["roots"])
        self.assertEqual(item["roots"], [{"object": "bell", "version": 0, "behaviour": 1}])

    def test_unrule_while_the_model_waits_refuses_even_a_still_present_verb(self):
        self.place('grow / name: water / reading: poured on by a hand')
        self.place('rule / name: watering / when: request.verb == "water" / then: delvetalk square rain / text: watered')
        self.reading()
        self.place("unrule / name: watering")
        self.stale("delvetalk bell water / text: water it for me")
        self.assertEqual(self.value("rains", "square"), "0")
        self.assertIn("water", self.host.send(op="world-inspect", principal="glm", object="bell")["offered"])

    def test_any_placing_on_an_offered_card_is_relevant_even_for_another_verb(self):
        self.reading()
        self.place('rule / name: elsewhere / when: request.verb == "unused" / then: delvetalk square rain / text: other', who="kim")
        self.stale("delvetalk bell rain / text: rain now")

    def test_a_changed_door_card_invalidates_the_reading_at_its_parent(self):
        _, item = self.reading(card="square")
        self.assertIn(("bell", "rain"), [(o["card"], o["action"]) for o in item["offers"]])
        self.place('want / name: water / when: new.rains == 0 / asks: delvetalk bell rain / text: water')
        self.stale("delvetalk bell rain / text: rain now", card="bell")

    def test_a_placing_on_an_unoffered_card_preserves_the_reading_and_its_receipt(self):
        self.make("other", BELL, record(owner=label("ember")))
        _, item = self.reading()
        self.place('rule / name: elsewhere / when: request.verb == "unused" / then: delvetalk square rain / text: other', card="other", who="kim")
        _, ran = self.settle("delvetalk bell rain / text: " + "x" * bounds()["host"]["formTextMax"])
        self.assertEqual(ran["status"], "admitted", ran)
        self.assertEqual((self.value("rains"), self.value("last")), ("1", "x" * bounds()["host"]["formTextMax"]))
        self.assertEqual(ran["receipt"]["roots"], item["roots"])
        self.assertEqual(item["roots"], [{"object": "bell", "version": 0, "behaviour": 0}])
        self.reopen()
        receipt = self.host.send(op="world-receipt", principal="glm", identity=ran["receipt"]["identity"]["intent"])["receipt"]
        self.assertEqual(receipt["roots"], item["roots"])

    def test_the_owners_ordinary_write_keeps_its_original_root_bytes_after_a_strangers_placing(self):
        before = self.host.send(op="world-view", principal="ember", object="bell")
        roots = [{"object": "bell", "version": before["version"]}]
        self.place('rule / name: elsewhere / when: request.verb == "unused" / then: delvetalk square rain / text: other', who="kim")
        ran = self.host.send(op="world-propose", principal="ember", identity="own-write", roots=roots,
                             writes=[{"object": "bell", "edits": [record(last=variant("set", value=label("still mine")))]}])
        self.assertEqual(ran["status"], "admitted", ran)
        self.assertEqual(ran["receipt"]["roots"], roots)
        self.assertEqual(ran["receipt"]["request"], cid_of({"roots": roots, "writes": [{"object": "bell",
            "edits": [record(last=variant("set", value=label("still mine")))], "callers": [""], "kinds": [3]}]}))
        self.assertNotIn("behaviour", ran["receipt"]["outcome"]["writes"][0])
        self.assertEqual(self.value("last"), "still mine")

    def test_reprogram_moves_the_behaviour_revision_and_refuses_the_pending_reading(self):
        _, item = self.reading()
        changed = BELL.replace('state.rains + 1n', 'state.rains + 2n')
        ran = self.host.send(op="world-reprogram", principal="ember", identity="new-rain", object="bell", version=0, package=changed)
        self.assertEqual(ran["status"], "admitted", ran)
        self.stale("delvetalk bell rain / text: obsolete")
        self.reopen()
        _, current = self.reading()
        self.assertEqual(current["roots"], [{"object": "bell", "version": 1, "behaviour": 1}])
        self.assertEqual(item["roots"], [{"object": "bell", "version": 0, "behaviour": 0}])

    def test_snapshot_and_replay_keep_a_revision_even_after_every_placing_is_removed(self):
        self.place('grow / name: water / reading: poured on by a hand')
        self.place("ungrow / name: water")
        self.reopen()
        waiting, item = self.reading()
        self.assertEqual(item["roots"], [{"object": "bell", "version": 0, "behaviour": 2}])
        snap = self.host.send(op="world-snapshot")
        self.assertEqual(snap["status"], "snapshot", snap)
        self.reopen()
        report = self.host.send(op="world-open", path=self.path)["snapshot"]
        self.assertEqual(report["resumed"], snap["height"], report)
        self.assertEqual(report["refused"], [], report)
        self.assertEqual(self.pending()[0]["roots"], waiting["receipt"]["roots"])
        self.place('want / name: water / when: new.rains == 0 / asks: delvetalk bell rain / text: water')
        self.reopen()
        self.stale("delvetalk bell rain / text: obsolete")

    def test_a_forged_snapshot_cannot_roll_back_the_revision_of_an_empty_table(self):
        self.place('grow / name: water / reading: poured on by a hand')
        self.place("ungrow / name: water")
        snap = self.host.send(op="world-snapshot")
        self.assertEqual(snap["status"], "snapshot", snap)
        path = self.path + ".snapshot.%d.cbor" % snap["height"]
        self.release()
        body = read_snapshot(path)
        [bell] = [o for o in body["objects"] if o["id"] == "bell"]
        self.assertEqual(bell["behaviour"], 2)
        bell["behaviour"] = 0
        write_snapshot(path, body)
        self.reopen()
        report = self.host.send(op="world-open", path=self.path)["snapshot"]
        self.assertEqual(report["resumed"], 0, report)
        self.assertEqual(report["refused"][0]["height"], snap["height"])
        self.assertIn("not the journal's", report["refused"][0]["reason"])
        _, item = self.reading()
        self.assertEqual(item["roots"], [{"object": "bell", "version": 0, "behaviour": 2}])


if __name__ == "__main__":
    unittest.main()
