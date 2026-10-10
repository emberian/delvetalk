"""Reach: only words that reached a card go to the model (docs/FLEX.md §2; HOST-HANDOFF 5.118).

Evidence for interpretation (layer: host).

A turn's `reach` says how its words reached the card: `reply` (its `replyTo` names a post the world
recorded: the host checks), `spell` (its text has a spell line: the host reads it), `direct` (a
principal named a method other than `receive`), `delivery` (an object sent it), or what the
transport saw of the post and states: `mention`, `door`, `fields` (the host checks the field line)
or `direct` (asked on the card itself). An `interpret` of a turn with none is answered `unclear
{needs: ["not addressed"]}` at once: no suspension, no model, no quota. Every interpretation
journals its reach. Refuted by: prose with no reach suspending or listed for the model, a reached
interpretation listed without its reach, a stated `fields` with no field line or an unknown reach
admitted, or a reach left out of the retry digest.
"""
import unittest

from tests.host import posted
from tests.test_chain import Chain
import tests.test_policy as policy_tests
from tests.test_turn_world import closure, declared, label, record

CARD = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  heard: Nat
def initial() -> State:
  {heard: 0n}
def offered(card: String) -> World.Forms:
  Lists.List::<Form.Form>.cons({head: {card: card, action: "plant", fields: Lists.List::<Form.Field>.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 140n})}, tail: Lists.List::<Form.Field>.nil({})})}, tail: Lists.List::<Form.Form>.nil({})})
def first(names: Lists.List<String>) -> String:
  match names:
    case cons(c): c.head
    case nil(_): ""
def hear(text: String, card: String) -> Activity<String>:
  match world.interpret::<Data>({utterance: text, offers: offered(card), policy: {world: "", object: "policy"}, model: ""}):
    case proposal(p): "proposal {p.method}"
    case unclear(u): first(u.needs)
    case _: "other"
def receive(state: State, input: {text: String, post: String}, context: Abi.Context) -> Activity<String>:
  hear(input.text, context.object)
def ask(state: State, input: {text: String}, context: Abi.Context) -> Activity<String>:
  hear(input.text, context.object)
def plant(state: State, input: {seed: String}, context: Abi.Context) -> Activity<Nat>:
  0n
""", "receive", "ask", "plant")

PROSE = "lovely evening, the moths are out"


class Reach(Chain):
    policy = policy_tests.PolicyObject.policy

    def setUp(self):
        super().setUp()
        self.policy()
        seen, mods = set(), []
        for dep in ("Abi", "List", "Form", "Plan", "World"):
            closure(dep, seen, mods)
        self.make("card", mods + [{"name": "Card", "source": CARD}], record())

    def say(self, text=PROSE, identity=None, **extra):
        self.n = getattr(self, "n", 0) + 1
        identity = identity or "r%d" % self.n
        return self.host.send(op="world-turn", principal="glm", object="card", method="receive",
                              argument=record(text=label(text), post=label("at://glm/p/" + identity)),
                              identity=identity, **extra)

    def pending(self):
        return self.host.send(op="world-interpretations")["pending"]

    def test_prose_with_no_reach_is_not_addressed_at_once(self):
        r = self.say()
        self.assertEqual((r["status"], r["result"]), ("admitted", {"tag": "label", "value": "not addressed"}), r)
        self.assertEqual(self.pending(), [])
        status = self.host.send(op="world-status", principal="glm")
        self.assertEqual(status["interpretations"]["remaining"], status["interpretQuota"], status)


    def test_a_reply_to_a_recorded_post_reaches_by_reply_and_to_another_post_does_not(self):
        hub = "at://did:plc:ember/town.delve.feed.post/card"
        got = posted(self.host, principal="transport", uri=hub, cid="bafycard", object="card")
        self.assertEqual(got["status"], "posted", got)
        r = self.say(replyTo=hub)
        self.assertEqual(r["status"], "suspended", r)
        self.assertEqual(self.pending()[0]["reach"], "reply")
        r = self.say(replyTo="at://did:plc:someone/app.bsky.feed.post/x")  # an unrecorded post does not reach
        self.assertEqual(r["result"]["value"], "not addressed", r)

    def test_a_named_method_reaches_directly(self):
        r = self.host.send(op="world-turn", principal="glm", object="card", method="ask",
                           argument=record(text=label(PROSE)), identity="a1")
        self.assertEqual(r["status"], "suspended", r)
        self.assertEqual(self.pending()[0]["reach"], "direct")

    def test_stated_field_lines_must_be_there_and_an_unknown_reach_is_a_request_error(self):
        for bad in ("thread", "reply", "spell", "delivery", 1):
            r = self.say(reach=bad)
            self.assertEqual(r["status"], "error", (bad, r))
        r = self.say(reach="fields")
        self.assertEqual(r["status"], "error", r)
        self.assertIn("field line", r["message"])
        r = self.say("note: a fern\nand the rest is prose", reach="fields")
        self.assertEqual(r["status"], "suspended", r)
        self.assertEqual(self.pending()[0]["reach"], "fields")

    def test_the_reach_is_part_of_the_request(self):
        self.say(identity="same")
        again = self.say(identity="same", reach="mention")
        self.assertEqual(again.get("class"), "duplicateIdentity", again)


if __name__ == "__main__":
    unittest.main()
