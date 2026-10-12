"""The bridge turns observed posts into turns in creation order, routes a reply by its nearest
recorded ancestor, and drafts each offer once, never posting.

Evidence for FOUNDATION §7 (layer: transport).
"""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy import genesis
from deploy.genesis import DOORS, STUDIO
from tests import test_outbound
from tests.test_receive import door
from tests.test_chain import town_garden
from tests.test_transport import DID, Script, mk
from transport import bridge, delve, observe
from tests.host import served
from transport.config import Config
from transport.host import HostClient
from transport.hand import Hand
from transport.state import State
from tests.wire import label, listing, nat, record
from tests.bend import closure, declared

CARD = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  seen: Nat
%s
def initial() -> State:
  {seen: 5n}
def act(context: Abi.Context) -> Activity<Nat>:
%s
def receive(state: State, input: {text: String, post: String}, context: Abi.Context) -> Activity<Nat>:
  act(context)
def plant(state: State, input: {seed: String, colour: String}, context: Abi.Context) -> Activity<Nat>:
  act(context)
""")
OFFERING = """  match world.offer({to: "", document: Document.text(textConcat("hello ", context.principal))}):
    case offered(_): 1n
    case _: 0n"""
REFUSING = """  match world.write(extend(keep(), {seen: Plans.Edit::<Nat, Nat>.set({value: 0n})})):
    case written(_): 1n
    case _: 0n"""


def modules(body, law=''):
    return closure('Document', 'World') + [{'name': 'Card', 'source': CARD % (law, body)}]


def spell_post(n, card, ts):
    p = mk(n, f'delvetalk {card} plant\nseed: a\ncolour: amber')
    p['record']['createdAt'] = ts
    return p


def summon_post(n, ts):
    p = mk(n, '@livedelvetalk.delve.town hi #gsb')
    p['record']['createdAt'] = ts
    return p


LOOPBACK = Config(origin='http://127.0.0.1:8765')  # a front only this machine opens: drafts cite no link (bridge.reachable)


class BridgeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = State(Path(self.tmp.name) / 'state', config=LOOPBACK)
        self.state.append(self.state.taught, DID)  # not a newcomer: a first reply's next moves are test_posting's

    @property
    def host(self):
        """A `serve` of this test's own, started by the first test that talks to a real host
        (the routing tests drive a Stub and never do)."""
        if '_host' not in self.__dict__:
            serving = served(str(Path(self.tmp.name) / 'serve'), cleanup=self.addCleanup)
            self._host = HostClient(serving.sock)
        return self._host

    def make(self, name, body=OFFERING, law='', **more):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-' + name, 'object': name,
                            'modules': modules(body, law), 'entry': 'initial', 'seed': record(seen=nat(5)), **more})
        self.assertEqual(r['status'], 'created', r)

    def observe(self, posts):
        t = Script(**{'town.delve.feed.searchPosts': lambda p: (200, {'posts': posts}),
                      'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})
        ob = observe.Observer(self.state, delve.Client(t))
        ob.poll()
        ob.db.close()

    def drafts(self):
        return [json.loads(p.read_text()) for p in sorted(self.state.outbox.glob('*.json'),
                                                         key=lambda p: int(p.name.split('-')[0]))]

    def run_bridge(self):
        return bridge.run(self.state, self.host)


class DirectReplies(BridgeCase):
    """A reply in a card's own thread is addressed to it: the commonplace hears prose naming
    nothing (and no policy to read it) as a turn that offers nothing, so no reply is drafted."""

    def test_prose_naming_nothing_in_the_commonplaces_thread_is_heard_and_drafts_no_reply(self):
        cites = [door(*d) for d in DOORS] + [door(STUDIO[0], '', (), STUDIO[1])]
        made = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-commonplace', 'object': 'commonplace',
                               'modules': closure('Menu', 'Policies', 'Record'), 'entry': 'initial', 'law': genesis.RECORD_LAW,
                               'seed': record(owner=label('ember'), keeper=label('ember'), head=label('THE COMMONPLACE'), cites=listing(cites))})
        self.assertEqual(made['status'], 'created', made)
        body = self.host.send({'op': 'world-reprogram', 'principal': 'ember', 'identity': 'body-commonplace', 'object': 'commonplace', 'version': 0,
                               'package': genesis.body_of('commonplace'), 'mode': 'extend'})
        self.assertEqual(body['status'], 'admitted', body)
        hub = 'at://did:plc:ember/town.delve.feed.post/hub'
        self.host.send({'op': 'world-post-reserve', 'principal': 'transport', 'intent': 'hub', 'source': 'delve'})  # a post settles its reservation
        recorded = self.host.send({'op': 'world-posted', 'principal': 'transport', 'uri': hub, 'cid': 'bafyhub', 'object': 'commonplace', 'intent': 'hub'})
        self.assertNotEqual(recorded.get('status'), 'error', recorded)
        posts = [mk(n, text, parent=hub) for n, text in enumerate(('hello, what is this?', 'lovely evening', 'thanks all'), 1)]
        for n, p in enumerate(posts):
            p['record']['createdAt'] = '2026-10-09T10:00:0%dZ' % n
        self.observe(posts)
        self.run_bridge()
        texts = [d['text'] for d in self.drafts()]
        self.assertEqual(texts, ['', '', ''])  # three journaled turns, none with words to post
        self.assertEqual([d['object'] for d in self.drafts()], ['commonplace'] * 3)


class OpenerPosts(BridgeCase):
    """The opener's privileges are the root socket's, which the bridge never holds (HOST-HANDOFF 5.125, 5.131); her
    ordinary turns are the public socket's: a post by the opener runs as a resident's turn, not skipped."""

    @property
    def host(self):
        if '_host' not in self.__dict__:
            serving = served(str(Path(self.tmp.name) / 'serve'), cleanup=self.addCleanup, opener=DID)
            self._host = HostClient(serving.sock)
        return self._host

    def test_a_post_by_the_opener_runs_as_a_residents_turn(self):
        self.make('garden-1')
        post = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')
        self.observe([post])
        got = self.run_bridge()
        self.assertEqual((got['turns'], got['failed']), ([post['uri']], []), got)
        skipped = self.state.skipped
        self.assertFalse(skipped.exists() and post['uri'] in skipped.read_text().split())
        self.assertEqual(self.run_bridge()['turns'], [])


class Bridging(BridgeCase):

    def test_three_posts_three_turns_in_created_order_then_nothing(self):
        self.make('garden-1')
        self.make('commonplace')
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:03Z'), summon_post(2, '2026-10-09T10:00:01Z'),
                      spell_post(3, 'garden-1', '2026-10-09T10:00:02Z')])
        first = self.run_bridge()
        order = [u[-6:] for u in first['turns']]
        self.assertEqual(order, ['000002', '000003', '000001'])
        drafts = self.drafts()
        self.assertEqual(len(drafts), 3)
        self.assertEqual([d['replyTo'][-6:] for d in drafts], order)
        for d in drafts:
            self.assertFalse(d['posted'])
            self.assertFalse(d['principalVerified'])
            self.assertEqual((d['principal'], d['replyHandle']), (DID, 'talkie.delve.town'))
            self.assertEqual(d['text'], f"hello {DID}\n{bridge.receipt_line(d['receipt'])}")
        self.assertEqual(self.run_bridge(), {'turns': [], 'failed': []})
        self.assertEqual(len(self.drafts()), 3)

    def test_a_post_of_two_spells_is_two_turns_and_one_draft_with_both_lines(self):
        self.make('garden-1')
        p = mk(1, 'delvetalk garden-1 plant\ndelvetalk garden-1 plant')
        self.observe([p])
        self.assertEqual(self.run_bridge()['turns'], [p['uri']])
        (d,) = self.drafts()
        receipts = [self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': f"{p['uri']}#{n}"})['receipt'] for n in (1, 2)]
        self.assertEqual(d['receipt']['hash'], receipts[1]['hash'])
        self.assertEqual(d['text'], ''.join(bridge.receipt_line(r) for r in receipts))  # the lines, no cards: three fit one reply

    def test_a_plan_is_one_turn_one_draft_and_one_post_of_the_quota(self):
        """A plan (HOST-HANDOFF 5.203) is one turn under the post's identity: one draft, so one post of the town's hour,
        its acts' lines above the receipt; a refused plan's draft names the act."""
        self.make('garden-1')
        p = mk(1, 'delvetalk plan\ndelvetalk garden-1 plant / seed: a / colour: amber\ndelvetalk garden-1 plant / seed: b / colour: amber')
        q = mk(2, 'delvetalk plan\ndelvetalk garden-1 plant / seed: a / colour: amber\ndelvetalk garden-1 prune')
        q['record']['createdAt'] = '2026-10-09T10:00:09Z'
        self.observe([p, q])
        self.assertEqual(self.run_bridge()['turns'], [p['uri'], q['uri']])
        d, e = self.drafts()
        self.assertEqual(d['receipt']['identity']['intent'], p['uri'])
        self.assertEqual(e['receipt']['height'], d['receipt']['height'] + 1)  # one entry a plan
        self.assertIn('1. delvetalk garden-1 plant / seed: a / colour: amber: done\n2. delvetalk garden-1 plant / seed: b / colour: amber: done\n', d['text'])
        self.assertTrue(e['text'].startswith('act 2 of 2 refused, so none of the plan was done:\nrefused noAction: act 2 (delvetalk garden-1 prune)'), e['text'])

    def test_crash_between_turn_and_draft_recovers_with_the_same_receipt(self):
        self.make('garden-1')
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        with mock.patch.object(State, 'write', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):
                self.run_bridge()
        self.assertEqual(self.drafts(), [])
        uri = f'at://{DID}/town.delve.feed.post/r000001'
        before = self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': uri})['receipt']
        self.run_bridge()
        (d,) = self.drafts()
        self.assertEqual(d['receipt']['hash'], before['hash'])
        self.assertEqual(self.host.send({'op': 'world-status'})['height'], before['height'])  # no second turn
        self.assertEqual(d['receipt']['height'], before['height'])
        self.assertNotIn('not retained', d['text'])  # the journal retains offers: the retry has the card

    def test_refused_spell_yields_a_refusal_draft_with_class_and_no_state(self):
        self.make('stern', REFUSING, 'law seen: monotone(seen)\n')
        self.observe([spell_post(1, 'stern', '2026-10-09T10:00:00Z')])
        self.run_bridge()
        (d,) = self.drafts()
        self.assertTrue(d['text'].startswith("refused "), d['text'])
        self.assertNotIn('proposal observed', d['text'])
        import re
        self.assertFalse(re.search(r'bafy|[0-9a-f]{64}', d['text']), d['text'])
        self.assertTrue(d['text'].startswith('refused seen: stern\nreceipt '), d['text'])  # the clause names the law line; no state value


    def test_host_error_without_receipt_leaves_the_post_for_retry(self):
        self.make('garden-1')
        p = mk(1, 'delvetalk garden-1 plant\nseed: a')
        self.observe([p])
        with mock.patch.object(self.host, 'send', return_value={'status': 'error', 'message': 'boom'}):
            r = self.run_bridge()
        self.assertEqual((r['turns'], r['failed'][0]['message']), ([], 'boom'))
        self.assertEqual(self.run_bridge()['turns'], [p['uri']])


    def test_a_spell_post_to_a_real_garden_is_bridged_into_a_draft_saying_planted(self):
        town_garden(lambda **q: self.host.send(q), id='garden-1')
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        self.assertEqual(self.run_bridge()['failed'], [])
        (d,) = self.drafts()
        self.assertIn('planted', d['text'])
        self.assertTrue(d['text'].endswith(f"● admitted garden-1 v1, entry {d['receipt']['height']}, receipt {d['receipt']['slug']}\n"), d['text'])


class Private(BridgeCase):
    """A reply is posted where everyone reads it: what a turn offered from a thing the public may not read is the
    author's alone, so its draft carries the receipt line and not the offer."""

    def test_an_offer_from_a_thing_only_its_reader_may_read_is_not_drafted_into_a_public_reply(self):
        self.make('diary', read={'principals': [DID]})
        self.make('garden-1')
        self.observe([spell_post(1, 'diary', '2026-10-09T10:00:00Z'), spell_post(2, 'garden-1', '2026-10-09T10:00:01Z')])
        self.assertEqual(self.run_bridge()['failed'], [])
        private, public = self.drafts()
        self.assertEqual(private['text'], bridge.receipt_line(private['receipt']))
        self.assertEqual(public['text'], f"hello {DID}\n{bridge.receipt_line(public['receipt'])}")
        # Whether a draft may carry the offers is the host's answer (`inPublic`), never a `world-view` per object (simplify (1)).
        for d, seen in ((private, False), (public, True)):
            r = self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': d['receipt']['identity']['intent']})
            self.assertEqual(r.get('inPublic'), seen, r)


class HostParses(BridgeCase):
    """Whether a post is a spell, and to which card, is the host's answer (`world-reach` reads it with its parser), never Python's."""
    def test_a_standalone_question_mark_spell_reaches_the_card_and_is_answered_with_its_usage(self):
        self.make('garden-1')
        post = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')
        post['record']['text'] = 'delvetalk garden-1 ?'
        self.observe([post])
        got = self.run_bridge()
        self.assertEqual(got['turns'], [post['uri']], got)
        (d,) = self.drafts()
        self.assertTrue(d['usage'], d)
        self.assertIn('delvetalk garden-1', d['text'])
        self.assertEqual(self.run_bridge()['turns'], [])  # answered once, not retried

    def test_a_line_the_host_does_not_read_as_a_spell_is_not_routed_by_its_second_word(self):
        self.make('garden-1')
        post = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')
        post['record']['text'] = f"delvetalk {'g' * 129} plant\nseed: a\ncolour: amber"  # past 128 bytes the host reads no card
        self.observe([post])
        got = self.run_bridge()
        self.assertEqual((got['turns'], self.drafts()), ([], []), got)


class Stub:
    """A host that answers from canned data and records everything it is sent."""
    RESUMED = {'hash': 'h', 'height': 9, 'slug': 'lodif-rukuz', 'outcome': {'tag': 'admitted'}, 'roots': [{'object': 'garden-1', 'version': 1}]}
    def __init__(self, reaches=None, mentions=4):
        self.ops, self.reaches, self.suspending, self.offers, self.silent = [], reaches or {}, set(), {}, set()
        self.mentions = mentions

    def send(self, req):
        self.ops.append(req)
        op = req['op']
        if op == 'world-reach':  # the host's answer, by the post (tests/test_reach.py checks the host's own): else a spell
            lines = [l.split() for l in req['text'].split('\n') if l.startswith('delvetalk ') and len(l.split()) > 2]  # line's card, a summons the commonplace
            return self.reaches.get(req['uri']) or ({'status': 'reached', 'object': lines[-1][1], 'how': 'spell'} if lines else
                {'status': 'reached', 'object': 'commonplace', 'how': 'mention'} if req['kind'] == 'summon' else {'status': 'unreached'})
        if op == 'world-offers':
            return {'status': 'offers', 'offers': self.offers.get(req['principal'], []), 'more': False}
        if op == 'world-turn' and req['object'] in self.suspending:
            return {'status': 'suspended', 'receipt': {'hash': 'h', 'height': 5, 'outcome': {'tag': 'suspended'}}}
        if op == 'world-turn':
            return {'status': 'admitted', 'receipt': {'hash': 'h', 'height': len(self.ops), 'outcome': {'tag': 'admitted'}}, 'inPublic': True,
                    **({} if req['object'] in self.silent else {'offers': [{'principal': req['principal'], 'text': 'to ' + req['object']}]})}
        if op == 'world-receipt':  # a suspended turn stays suspended until its offer is there
            return {'status': 'receipt', 'receipt': self.RESUMED, 'inPublic': True} if self.offers.get(req['principal']) else \
                {'status': 'receipt', 'receipt': {'outcome': {'tag': 'suspended'}}}
        if op == 'world-pending':
            return {'status': 'pending', 'count': 0}
        if op == 'bounds':
            return {'status': 'bounds', 'host': {'mentionsAddressed': self.mentions}}
        if op == 'world-publications':
            return {'status': 'publications', 'publications': [], 'more': False}
        return {'status': 'ok'}


class Reaching(BridgeCase):
    """Where a post reaches is the host's (`world-reach`): the bridge passes the post and the ancestors it saw with their
    authors, sends the turn the host's answer names, and skips, once, a post that reaches nothing."""
    def test_the_bridge_passes_what_it_saw_and_turns_where_the_host_says(self):
        u = lambda n: f'at://{DID}/town.delve.feed.post/{n}'
        reached = lambda obj, how, replyTo=None: {'status': 'reached', 'object': obj, 'how': how, **({'replyTo': replyTo} if replyTo else {})}
        posts = [mk(1, 'a fern, please', parent=u('card')), mk(2, 'plant: a bell', parent=u(1)), mk(3, 'the anthology', parent=u(2)),
                 mk(4, 'chatter', parent=u(3)), summon_post(5, '2026-10-09T10:00:09Z')]
        for i, p in enumerate(posts[:4]):
            p['uri'] = u(i + 1)
            p['record']['createdAt'] = f'2026-10-09T10:00:0{i}Z'
        stub = Stub({u(1): reached('garden-1', 'reply', u('card')), u(2): reached('garden-1', 'fields'), u(3): reached('anthology', 'door'),
                     posts[4]['uri']: reached('commonplace', 'mention')})
        self.observe(posts)
        r = bridge.run(self.state, stub)
        asked = {o['uri']: o for o in stub.ops if o['op'] == 'world-reach'}
        self.assertEqual([a['uri'] for a in asked[u(4)]['chain']], [u(3), u(2), u(1)])  # every ancestor it saw, nearest first
        self.assertEqual(asked[u(4)]['chain'][-1], {'uri': u(1), 'author': DID, 'replyTo': u('card')})
        self.assertEqual((asked[u(4)]['replyTo'], asked[u(4)]['mentions'], asked[u(4)]['author']), (u(3), 0, DID))
        turns = {t['identity']: (t['object'], t.get('reach'), t.get('replyTo')) for t in stub.ops if t['op'] == 'world-turn'}
        self.assertEqual(turns, {u(1): ('garden-1', None, u('card')), u(2): ('garden-1', 'fields', u(1)), u(3): ('anthology', 'door', u(2)),
                                 posts[4]['uri']: ('commonplace', 'mention', None)})
        self.assertEqual([f['name'] for f in stub.ops[[o['op'] for o in stub.ops].index('world-turn')]['argument']['fields']], ['text', 'post'])
        self.assertEqual(len(r['turns']), 4)
        self.assertIn(u(4), self.state.skipped.read_text())
        n = len([o for o in stub.ops if o['op'] == 'world-reach'])
        bridge.run(self.state, stub)
        self.assertEqual(len([o for o in stub.ops if o['op'] == 'world-reach']), n)  # drafts and skips are remembered

    def test_a_cycle_in_what_was_observed_passes_each_ancestor_once(self):
        a, b = f'at://{DID}/town.delve.feed.post/ca', f'at://{DID}/town.delve.feed.post/cb'
        stub = Stub()
        x, y = mk(1, 'x', parent=b), mk(2, 'y', parent=a)
        x['uri'], y['uri'] = a, b
        self.observe([x, y])
        bridge.run(self.state, stub)
        self.assertEqual([[c['uri'] for c in o['chain']] for o in stub.ops if o['op'] == 'world-reach'], [[b, a], [a, b]])


class Suspended(BridgeCase):
    def test_a_suspended_turn_has_no_draft_then_the_resumed_offer_is_drafted_once(self):
        stub = Stub()
        stub.suspending = {'garden-1'}
        p = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')
        self.observe([p])
        bridge.run(self.state, stub)
        self.assertEqual(self.drafts(), [])
        turns = len([o for o in stub.ops if o['op'] == 'world-turn'])
        bridge.run(self.state, stub)
        self.assertEqual(len([o for o in stub.ops if o['op'] == 'world-turn']), turns)  # not re-run while it waits
        self.assertEqual(self.drafts(), [])  # settled with no offer: still no draft
        stub.offers[DID] = [{'height': 9, 'ordinal': 0, 'identity': {'principal': DID, 'intent': p['uri']}, 'text': 'Planted.'},
                            {'height': 9, 'ordinal': 1, 'identity': {'principal': DID, 'intent': 'someone-else'}, 'text': 'not mine'}]
        r = bridge.run(self.state, stub)
        self.assertEqual(r['offered'], [p['uri']])
        (d,) = self.drafts()
        self.assertEqual((d['text'], d['replyTo'], d['principal'], d['posted']), ('Planted.\n' + bridge.receipt_line(Stub.RESUMED), p['uri'], DID, False))
        self.assertNotIn('offered', bridge.run(self.state, stub))
        self.assertEqual(len(self.drafts()), 1)

    def test_an_offer_for_a_handed_on_turn_is_drafted_against_the_originating_post(self):
        stub = Stub()
        stub.suspending = {'garden-1'}
        p = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')
        self.observe([p])
        bridge.run(self.state, stub)
        stub.offers[DID] = [{'height': 9, 'ordinal': 0, 'identity': {'principal': DID, 'intent': 'handed-on-turn'},
                             'from': {'principal': DID, 'intent': p['uri']}, 'text': 'Handed over.'}]
        self.assertEqual(bridge.run(self.state, stub)['offered'], [p['uri']])
        (d,) = self.drafts()
        self.assertEqual((d['text'], d['replyTo']), ('Handed over.\n' + bridge.receipt_line(Stub.RESUMED), p['uri']))


class Spells(Stub):
    """Each post of several spells answered as the host answers one: a turn per spell line, `segments` naming each
    one's status (`usage` for a `?`, `suspended`, else admitted)."""
    def __init__(self, segments):
        super().__init__()
        self.segments = segments

    def send(self, req):
        if req['op'] != 'world-turn':
            return super().send(req)
        self.ops.append(req)
        turns = []
        for n, status in enumerate(self.segments, 1):
            identity = {'principal': req['principal'], 'intent': f"{req['identity']}#{n}"}
            rc = {'hash': f'h{n}', 'height': 10 + n, 'slug': f'lodif-ruku{"zb"[n % 2]}', 'identity': identity,
                  'outcome': {'tag': 'suspended' if status == 'suspended' else 'admitted'}, 'roots': [{'object': 'bell-1', 'version': n}]}
            turns.append({'status': 'usage', 'text': 'delvetalk bell-1 rain / text: <1 to 200>\n'} if status == 'usage' else
                         {'status': status, 'object': 'bell-1', 'receipt': rc})
        return {'status': 'spells', 'turns': turns}


class SeveralSpells(BridgeCase):
    def test_a_usage_line_among_the_spells_is_answered_with_the_others(self):
        stub = Spells(['admitted', 'usage'])
        self.observe([mk(1, 'delvetalk bell-1 rain\ntext: hello\ndelvetalk bell-1 ?')])
        self.assertEqual(bridge.run(self.state, stub)['failed'], [])
        (d,) = self.drafts()
        self.assertIn('admitted bell-1 v1', d['text'])
        self.assertIn('delvetalk bell-1 rain / text: <1 to 200>', d['text'])

    def test_a_suspended_spell_among_them_is_answered_when_its_offer_comes(self):
        stub = Spells(['admitted', 'suspended'])
        p = mk(1, 'delvetalk bell-1 rain\ntext: hello\ndelvetalk bell-1 tend')
        self.observe([p])
        self.assertEqual(bridge.run(self.state, stub)['failed'], [])
        stub.offers[DID] = [{'height': 20, 'ordinal': 0, 'identity': {'principal': DID, 'intent': p['uri'] + '#2'}, 'text': 'Tended.'}]
        self.assertEqual(bridge.run(self.state, stub)['offered'], [p['uri'] + '#2'])
        later = [d for d in self.drafts() if 'Tended.' in d['text']]
        self.assertEqual([d['replyTo'] for d in later], [p['uri']])


class Mentions(BridgeCase):
    GLM, KIMI = 'did:plc:' + 'b' * 24, 'did:plc:' + 'c' * 24

    def facet(self, text, handle, did):
        start = text.index('@' + handle)
        return {'index': {'byteStart': start, 'byteEnd': start + len(handle) + 1}, 'features': [{'$type': 'app.bsky.richtext.facet#mention', 'did': did}]}

    def seen(self, n, did, handle):
        p = mk(n, f'{handle} was here')
        p['author'] = {'did': did, 'handle': handle}
        return p

    def test_a_post_mentioning_two_handles_is_a_receive_on_each_mentioned_avatar_under_the_author(self):
        stub = Stub()
        glm = mk(1, 'glm here')
        glm['author'] = {'did': self.GLM, 'handle': 'glm.delve.town'}
        text = 'hello @glm.delve.town and @kimi.delve.town'  # glm by a known author's handle, kimi by facet
        post = mk(2, text, facets=[self.facet(text, 'kimi.delve.town', self.KIMI)])
        self.observe([glm, self.seen(3, self.KIMI, 'kimi.delve.town'), post])
        r = bridge.run(self.state, stub)
        turns = [o for o in stub.ops if o['op'] == 'world-turn' and o['method'] == 'receive']
        self.assertEqual([(t['object'], t['principal'], t['reach'], t['identity']) for t in turns],
                         [(d, DID, 'mentioned', f"{post['uri']}#mention:{d}") for d in (self.KIMI, self.GLM)])  # facets first, then @text
        fields = {f['name']: f['value']['value'] for f in turns[0]['argument']['fields']}
        self.assertEqual(fields, {'text': text, 'post': post['uri']})
        self.assertEqual(r['mentioned'], [post['uri']])
        before = len(stub.ops)
        self.assertNotIn('mentioned', bridge.run(self.state, stub))  # once per post
        self.assertEqual([o['op'] for o in stub.ops[before:]].count('world-turn'), 0)

    def test_a_mention_through_the_bridge_is_admitted_on_the_mentioned_avatar_of_a_real_host(self):
        """The v8 deploy's lost mentions: the bridge sends `{text, post}`, and the avatar's `receive` takes `fields` and
        `spell` too, which the host fills (empty, and no cast: a mention is heard, never cast)."""
        from tests.town import Town
        town = Town(str(Path(self.tmp.name) / 'town'), cleanup=self.addCleanup)
        host = type('TownHost', (), {'send': lambda _, req: town.send(**req)})()
        glm = mk(1, 'glm here')
        glm['author'] = {'did': self.GLM, 'handle': 'glm.delve.town'}
        post = mk(2, 'a bell for @glm.delve.town')
        self.observe([glm, post])
        r = bridge.run(self.state, host)
        self.assertEqual((r['mentioned'], r['failed']), ([post['uri']], []), r)
        got = host.send({'op': 'world-receipt', 'principal': DID, 'identity': f"{post['uri']}#mention:{self.GLM}"})
        self.assertEqual((got['status'], got['receipt']['outcome']['tag']), ('receipt', 'admitted'), got)

    def test_a_never_seen_handle_gets_no_turn_and_an_observed_author_is_arrived_and_reached(self):
        stub = Stub()
        glm = mk(1, 'glm only chats')  # an author whose post is no spell, reply or mention
        glm['author'] = {'did': self.GLM, 'handle': 'glm.delve.town'}
        text = 'hello @glm.delve.town and @ghost.delve.town'
        post = mk(2, text, facets=[self.facet(text, 'ghost.delve.town', self.KIMI)])  # kimi was never observed
        self.observe([glm, post])
        r = bridge.run(self.state, stub)
        arrivals = [o['did'] for o in stub.ops if o['op'] == 'world-arrive']
        self.assertEqual(sorted(arrivals), sorted([DID, self.GLM]))  # every observed author, once; never the unseen kimi
        self.assertEqual([o['object'] for o in stub.ops if o['op'] == 'world-turn'], [self.GLM])
        self.assertIn(f"{post['uri']}#mention:{self.KIMI}", (self.state.skipped).read_text().split())
        self.assertEqual(r['failed'], [])
        before = len(stub.ops)
        bridge.run(self.state, stub)
        self.assertEqual([o['op'] for o in stub.ops[before:]].count('world-turn'), 0)

    def test_only_the_first_mentions_the_host_addresses_are_turned(self):
        # How many mentions of a post are addressed is the host's bound (`bounds.host.mentionsAddressed`), never the bridge's.
        self.assertEqual(self.host.send({'op': 'bounds'})['host']['mentionsAddressed'], 4)
        stub = Stub(mentions=3)
        dids = ['did:plc:' + c * 24 for c in 'defgh']
        text = ' '.join(f'@u{i}.delve.town' for i in range(5))
        post = mk(1, text, facets=[self.facet(text, f'u{i}.delve.town', d) for i, d in enumerate(dids)])
        self.observe([post] + [self.seen(10 + i, d, f'u{i}.delve.town') for i, d in enumerate(dids)])
        bridge.run(self.state, stub)
        self.assertEqual([o['object'] for o in stub.ops if o['op'] == 'world-turn'], dids[:3])


class Unaddressed(BridgeCase):
    """Whether a refusal is drafted is the host's fact: its `public` projection. The post's wording is never read for it."""
    def run_refused(self, post, public=True):
        parent = f'at://{DID}/town.delve.feed.post/welcome'
        stub = Stub({post['uri']: {'status': 'reached', 'object': 'commonplace', 'how': 'reply', 'replyTo': parent}})
        real = stub.send
        outcome = {'tag': 'refused', 'class': 'quota', 'reason': 'the interpreter has read 48 this hour; reply with the spell itself, or wait.', 'next': 600}
        stub.send = lambda req: ({'status': 'refused', 'receipt': {'hash': 'h', 'height': 5, 'slug': 'bofab-lukid', 'outcome': outcome},
                                  **({'public': {'status': 'refused', 'class': 'quota', 'reason': outcome['reason'], 'next': 600}} if public else {})}
                                 if req['op'] == 'world-turn' else real(req))
        self.observe([post])
        bridge.run(self.state, stub)
        return self.drafts()

    def test_a_plain_prose_reply_refused_by_quota_is_drafted_with_the_hosts_explanation(self):
        parent = f'at://{DID}/town.delve.feed.post/welcome'
        (chatter,) = self.run_refused(mk(1, 'lovely thread, thanks all', parent=parent))
        self.assertEqual(chatter['text'], 'refused quota: the interpreter has read 48 this hour; reply with the spell itself, or wait.\nreceipt bofab-lukid\n')

    def test_a_refusal_the_host_gives_no_public_projection_is_journaled_not_drafted(self):
        (spell,) = self.run_refused(spell_post(2, 'garden-1', '2026-10-09T10:00:00Z'), public=False)
        self.assertEqual((spell['text'], spell['receipt']['outcome']['class']), ('', 'quota'))


class Silence(BridgeCase):
    def test_a_turn_that_offers_nothing_has_no_draft_in_the_outbox_unless_asked(self):
        stub = Stub()
        stub.silent = {'garden-1'}
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        self.assertEqual(len(bridge.run(self.state, stub)['turns']), 1)
        self.assertEqual(bridge.run(self.state, stub)['turns'], [])  # journaled once, not re-run
        hand = Hand(self.state, stub)
        self.assertEqual(hand.outbox(), [])
        self.assertEqual(len(hand.outbox(all=True)[0]['drafts']), 1)


    def test_a_spell_that_changed_something_and_offered_nothing_is_answered_with_its_receipt(self):
        self.make('still-1', body=REFUSING)  # writes `seen`, offers no card
        self.observe([spell_post(1, 'still-1', '2026-10-09T10:00:00Z')])
        self.assertEqual(self.run_bridge()['failed'], [])
        (d,) = self.drafts()
        self.assertEqual(d['text'], bridge.receipt_line(d['receipt']))


class RealOffers(test_outbound.TellerWorld):
    def test_offer_drafts_match_the_hosts_real_identity_shape(self):
        self.turn("teller", "tell", record(to=label(""), text=label("hello")), principal="ann", identity="t-1")
        self.assertIsInstance(self.host.send(op="world-offers", principal="ann")["offers"][0]["identity"], dict)
        with tempfile.TemporaryDirectory() as d:
            d = State(d, config=LOOPBACK)
            d.write(bridge.awaiting_path(d, "t-1"), {"uri": "t-1", "principal": "ann", "replyHandle": "ann.delve.town",
                                                                 "object": "teller", "slot": None, "height": 0})
            outer = self

            class H:
                def send(self, req):
                    return outer.host.send(**req)
            self.assertEqual(bridge.offer_drafts(d, H()), ["t-1"])
            (draft,) = list(d.outbox.glob("*.json"))
            slug = self.host.send(op="world-receipt", principal="ann", identity="t-1")["receipt"]["slug"]
            self.assertRegex(json.loads(draft.read_text())["text"], rf"^hello\n● admitted teller v\d+, entry \d+, receipt {slug}\n$")
            self.assertEqual(bridge.offer_drafts(d, H()), [])


class Projection(unittest.TestCase):
    def test_a_draft_cites_the_slug_and_no_draft_text_carries_a_hash_or_a_blob(self):
        h = 'bafyrei' + 'a' * 52
        receipt = {'hash': h, 'slug': 'babab-dabab', 'height': 9, 'roots': [{'object': 'garden', 'version': 3}], 'outcome': {'tag': 'admitted'}, 'offers': 1}
        unslugged = {k: v for k, v in receipt.items() if k != 'slug'}
        texts = [bridge.draft_text({'receipt': receipt}, 'https://x.example'), bridge.draft_text({'receipt': unslugged}, 'https://x.example'),
                 bridge.draft_text({'status': 'refused', 'receipt': {**receipt, 'outcome': {'tag': 'refused', 'class': 'lawRefused'}},
                                    'public': {'class': 'lawRefused', 'root': {'object': 'garden', 'version': 3}}}),
                 bridge.draft_text({'status': 'refused', 'receipt': {**unslugged, 'hash': 'f' * 64, 'outcome': {'tag': 'refused', 'class': 'lawRefused'}}, 'public': {}}, 'https://x.example'),
                 bridge.draft_text({'status': 'refused', 'receipt': unslugged, 'public': {'class': 'lawRefused', 'root': {'object': 'g', 'version': 1, 'cid': h}}})]
        self.assertIn('● admitted garden v3, entry 9, receipt babab-dabab\n', texts[0])  # VOICE's turn line, as the JSON `line` has it
        self.assertIn('● admitted garden v3, entry 9\nhttps://x.example/o/garden#v3', texts[1])
        self.assertIn('receipt babab-dabab\n', texts[2])
        for t in texts:
            self.assertFalse(re.search(r'bafy|[0-9a-f]{64}', t), t)


class Principals(BridgeCase):
    def test_each_author_is_registered_once_by_the_clock_principal_at_their_first_post(self):
        stub = Stub()
        a, b = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z'), spell_post(2, 'garden-1', '2026-10-09T10:00:01Z')
        b['author'] = {'did': 'did:plc:' + 'b' * 24, 'handle': 'glm.delve.town'}
        self.observe([a, b, spell_post(3, 'garden-1', '2026-10-09T10:00:02Z')])
        bridge.run(self.state, stub)
        regs = [o for o in stub.ops if o['op'] == 'world-arrive']
        self.assertEqual(regs, [{'op': 'world-arrive', 'principal': 'transport', 'did': DID, 'handle': 'talkie.delve.town'},
                                {'op': 'world-arrive', 'principal': 'transport', 'did': 'did:plc:' + 'b' * 24, 'handle': 'glm.delve.town'}])
        first_turn = next(i for i, o in enumerate(stub.ops) if o['op'] == 'world-turn')
        self.assertLess(max(i for i, o in enumerate(stub.ops) if o['op'] == 'world-arrive'), first_turn)
        bridge.run(self.state, stub)
        self.assertEqual(len([o for o in stub.ops if o['op'] == 'world-arrive']), 2)


class Daemon(unittest.TestCase):
    def test_a_live_pid_file_blocks_a_second_daemon(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            st = State(d, config=Config(poll=0))
            st.home.mkdir(parents=True)
            st.pidfile('bridge').write_text(str(os.getpid()))
            with self.assertRaises(SystemExit):
                st.daemon('bridge', lambda: None)
            st.pidfile('bridge').write_text('999999')  # stale
            import threading
            stop = threading.Event()
            st.daemon('bridge', stop.set, stop)


class Names(unittest.TestCase):
    """A turn line never carries a DID to a post: a person's own cards are named by their handle."""

    def test_a_persons_cards_are_named_by_handle(self):
        did = 'did:plc:' + 'k' * 24
        handles = {did: 'kestrel'}
        for obj, name in ((did, "kestrel's avatar"), ('garden', 'garden'), ('did:plc:' + 'z' * 24, 'did:plc:' + 'z' * 24)):
            self.assertEqual(bridge.card_name(obj, handles), name)
        receipt = {'height': 9, 'slug': 'lodif-rukuz', 'roots': [{'object': did, 'version': 3}], 'outcome': {'tag': 'admitted'}}
        self.assertEqual(bridge.turn_words(receipt, handles=handles), "admitted kestrel's avatar v3, entry 9, receipt lodif-rukuz")


if __name__ == '__main__':
    unittest.main()
