"""Reach: only words that reached a card go to the model (docs/FLEX.md §2; HOST-HANDOFF 5.118).

Evidence for interpretation (layer: host).

A turn's `reach` says how its words reached the card: `reply` (its `replyTo` names a post the world
recorded: the host checks), `spell` (its text has a spell line: the host reads it), `direct` (a
principal named a method other than `receive`), `delivery` (an object sent it), or what the
transport saw of the post and states: `mention`, `door`, `fields` (the host checks the field line)
or `direct` (asked on the card itself). An `interpret` of a turn with none is answered `unclear
{needs: ["not addressed"]}` at once: no suspension, no model, no quota. Every interpretation
journals its reach. Where a post reaches at all is the host's too (`world-reach`, 5.162): the bridge passes
the post and the ancestors it saw with their authors. Refuted by: prose with no reach suspending or listed for the model, a reached
interpretation listed without its reach, a stated `fields` with no field line or an unknown reach
admitted, or a reach left out of the retry digest; a reply reaching a card other than its direct parent's,
prose deep in a thread reaching its root, a door named outside the world's threads reaching that door, a Zulip
message under another resident's reaching the card above it, or a walk looping on a cycle.
"""
import unittest

from tests.host import posted
from tests.test_chain import Chain, town_garden
from tests.test_receive import commonplace
import tests.test_policy as policy_tests
from tests.wire import label, record
from tests.bend import closure, declared

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
  match world.interpret::<Data>({utterance: text, offers: offered(card), policy: {world: "", object: "policy"}, model: "", held: "", misfit: ""}):
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

RELAY = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def receive(state: State, input: {text: String, post: String}, context: Abi.Context) -> Activity<String>:
  match world.send({object: {world: "", object: "card"}, method: "receive", argument: Data.of::<{text: String, post: String}>({text: input.text, post: input.post})}):
    case delivery(d): "handed on"
    case _: "other"
""", "receive")


class Reach(Chain):
    policy = policy_tests.PolicyObject.policy

    def setUp(self):
        super().setUp()
        self.policy()
        mods = closure(*("Abi", "List", "Form", "Plan", "World"))
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

    def test_a_reply_handed_on_by_send_keeps_its_reach(self):
        """A card that hands a reply on to another (a card forwarding to the directory) passes how the words
        reached it: prose that reached no one is still not addressed, a mention is still a mention."""
        mods = closure(*("Abi", "List", "Plan", "World"))
        self.make("relay", mods + [{"name": "Relay", "source": RELAY}], record())
        quiet = self.host.send(op="world-turn", principal="glm", object="relay", method="receive",
                               argument=record(text=label(PROSE), post=label("at://glm/p/q")), identity="q")
        self.assertEqual(quiet["status"], "admitted", quiet)
        self.assertEqual([d.get("result") for d in quiet["delivered"]], [label("not addressed")], quiet)
        loud = self.host.send(op="world-turn", principal="glm", object="relay", method="receive", reach="mention",
                              argument=record(text=label(PROSE), post=label("at://glm/p/l")), identity="l")
        self.assertEqual([d["status"] for d in loud["delivered"]], ["suspended"], loud)
        self.assertEqual([i["reach"] for i in self.pending()], ["mention"])

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


DID, OTHER = 'did:plc:glm', 'did:plc:kim'
U = lambda n: f'at://{DID}/town.delve.feed.post/{n}'
Z = lambda n: f'zulip://delvetalk/t/{n}'


class WorldReach(Chain):
    """`world-reach`: where an observed post reaches, found by the host from what the bridge saw (5.162)."""
    def setUp(self):
        super().setUp()
        town_garden(self.host.send)
        commonplace(self, doors=[('anthology', 'anthology', [])], studio=False)
        for uri, obj in ((U('card'), 'garden'), (U('welcome'), 'commonplace'), (Z(1), 'garden')):
            self.assertEqual(posted(self.host, principal='transport', uri=uri, cid='bafy' + uri[-4:], object=obj)['status'], 'posted')

    def reach(self, text, uri=None, kind='post', author=DID, replyTo=None, root=None, mentions=0, chain=()):
        got = self.host.send(op='world-reach', uri=uri or U('new'), text=text, kind=kind, author=author, mentions=mentions,
                             chain=[{'uri': u, 'author': a, **({'replyTo': r} if r else {})} for u, a, r in chain],
                             **({'replyTo': replyTo} if replyTo else {}), **({'root': root} if root else {}))
        return (got['object'], got['how'], got.get('replyTo')) if got['status'] == 'reached' else got['status']

    def test_a_reply_reaches_its_direct_parents_card_and_names_the_post_it_answers(self):
        self.assertEqual(self.reach('a fern, please', replyTo=U('card')), ('garden', 'reply', U('card')))
        self.assertEqual(self.reach('delvetalk garden plant', replyTo=U('welcome')), ('commonplace', 'reply', U('welcome')))
        # Its parent is no card's post: not by an ancestor, and its prose names no door.
        self.assertEqual(self.reach('fourth', replyTo=U('t3'), root=U('welcome'), chain=[(U('t3'), OTHER, U('card'))]), 'unreached')

    def test_a_spell_line_reaches_its_card_and_a_summons_the_commonplace(self):
        self.assertEqual(self.reach('delvetalk garden ?'), ('garden', 'spell', None))
        self.assertEqual(self.reach('I planted a fern #gsb', kind='summon'), ('commonplace', 'mention', None))
        self.assertEqual(self.reach('delvetalk garden ?', kind='wiki'), 'unreached')  # a page is no spell
        self.assertEqual(self.reach('replying elsewhere', replyTo=U('other')), 'unreached')

    def test_in_a_thread_the_world_opened_field_lines_reach_its_card_and_a_named_door_its_door(self):
        deep = dict(replyTo=U('agent1'), root=U('card'), chain=[(U('agent1'), OTHER, U('card'))])
        self.assertEqual(self.reach('For the record:\n\nplant: a bell\ncolour: silver', **deep), ('garden', 'fields', None))
        self.assertEqual(self.reach('And yes, that line belongs in the Anthology.', **deep), ('anthology', 'door', None))
        self.assertEqual(self.reach('Open recursion deserves to be carved into the lintel.', **deep), 'unreached')
        # The thread is the root's when the walk finds nothing recorded above.
        self.assertEqual(self.reach('plant: moss', replyTo=U('mid'), root=U('card')), ('garden', 'fields', None))
        # A door named outside the world's threads reaches nothing.
        self.assertEqual(self.reach('that line belongs in the anthology', replyTo=U('elsewhere')), 'unreached')

    def test_a_cycle_ends_the_walk(self):
        self.assertEqual(self.reach('x', replyTo=U('ca'), chain=[(U('ca'), OTHER, U('cb')), (U('cb'), OTHER, U('ca'))]), 'unreached')

    def test_on_zulip_the_walk_passes_only_the_authors_own_messages(self):
        mine = [(Z(2), DID, Z(1))]
        self.assertEqual(self.reach('and a last thought', uri=Z(3), replyTo=Z(2), chain=mine), ('garden', 'reply', Z(1)))
        # Under another resident's message: the words answer them, and reach nothing.
        self.assertEqual(self.reach('me too', uri=Z(3), replyTo=Z(2), chain=[(Z(2), OTHER, Z(1))]), 'unreached')
        # A message mentioning only other residents is theirs.
        self.assertEqual(self.reach('@**Carol** nice fern', uri=Z(3), replyTo=Z(1), mentions=1), 'unreached')
        self.assertEqual(self.reach('plant: moss', uri=Z(3), replyTo=Z(9)), 'unreached')  # no thread rule on Zulip


if __name__ == "__main__":
    unittest.main()
