import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import test_outbound
from tests.test_chain import garden_state
from tests.test_http import BINARY
from tests.test_transport import DID, Script, mk
from tests.test_turn_world import closure, label, nat, record
from transport import bridge, delve, observe
from tests.host import start_hostd, stop_hostd
from transport.hostproc import HostClient

CARD = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
import ./Plan.obend as Plans
record State:
  seen: Nat
record Edits:
  seen: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, Nat>
%s
def initial() -> State:
  {seen: 5n}
def receive(state: State, input: {text: String, post: String, slot: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
%s
"""
OFFERING = """  match perform(Plan.offer({to: "", document: Document.text(textConcat("hello ", context.principal))})):
    case offered(_): 1n
    case _: 0n"""
REFUSING = """  match perform(Plan.write({object: Plans.self(context), edits: {seen: Plans.Edit::<Nat, Nat>.set({value: 0n})}})):
    case written(_): 1n
    case _: 0n"""


def modules(body, law=''):
    out, seen = [], set()
    for m in closure('Document') + closure('Plan') + [{'name': 'Card', 'source': CARD % (law, body)}]:
        if m['name'] not in seen:
            seen.add(m['name'])
            out.append(m)
    return out


def spell_post(n, card, ts):
    p = mk(n, f'delvetalk {card} plant\nseed: a\ncolour: amber')
    p['record']['createdAt'] = ts
    return p


def summon_post(n, ts):
    p = mk(n, '@livedelvetalk.delve.town hi #gsb')
    p['record']['createdAt'] = ts
    return p


class BridgeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / 'state'
        self.hostd = start_hostd(str(Path(self.tmp.name) / 'hostd'), BINARY)
        self.addCleanup(stop_hostd, self.hostd)
        self.host = HostClient(Path(self.tmp.name) / 'hostd' / 'host.sock')

    def make(self, name, body=OFFERING, law=''):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-' + name, 'object': name,
                            'modules': modules(body, law), 'entry': 'initial', 'seed': record(seen=nat(5))})
        self.assertEqual(r['status'], 'created', r)

    def observe(self, posts):
        t = Script(**{'town.delve.feed.searchPosts': lambda p: (200, {'posts': posts}),
                      'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})
        ob = observe.Observer(self.state, delve.Client(t))
        ob.poll()
        ob.db.close()

    def drafts(self):
        return [json.loads(p.read_text()) for p in sorted((self.state / 'outbox').glob('*.json'),
                                                         key=lambda p: int(p.name.split('-')[0]))]

    def run_bridge(self):
        return bridge.run(self.state, self.host)


class Bridging(BridgeCase):
    def test_three_posts_three_turns_in_created_order_then_nothing(self):
        self.make('garden-1')
        self.make('directory')
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
            self.assertEqual(d['text'], 'hello ' + DID)
        self.assertEqual(self.run_bridge(), {'turns': [], 'failed': []})
        self.assertEqual(len(self.drafts()), 3)

    def test_crash_between_turn_and_draft_recovers_with_the_same_receipt(self):
        self.make('garden-1')
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        with mock.patch.object(bridge, 'write_atomic', side_effect=RuntimeError('crash')):
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
        self.assertTrue(d['text'].startswith("proposal observed, not committed\nreason: lawRefused\n"), d['text'])
        import re
        self.assertFalse(re.search(r'bafy|[0-9a-f]{64}', d['text']), d['text'])
        self.assertNotIn('seen', d['text'])  # no state field

    def test_unknown_card_yields_unknownObject_draft(self):
        self.observe([spell_post(1, 'nowhere', '2026-10-09T10:00:00Z')])
        self.run_bridge()
        (d,) = self.drafts()
        self.assertIn('reason: unknownObject', d['text'])

    def test_host_error_without_receipt_leaves_the_post_for_retry(self):
        self.make('garden-1')
        p = mk(1, 'delvetalk garden-1 plant\nseed: a')
        self.observe([p])
        with mock.patch.object(self.host, 'send', return_value={'status': 'error', 'message': 'boom'}):
            r = self.run_bridge()
        self.assertEqual((r['turns'], r['failed'][0]['message']), ([], 'boom'))
        self.assertEqual(self.run_bridge()['turns'], [p['uri']])

    def test_outbox_listing_and_mark_posted(self):
        self.make('garden-1')
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        self.run_bridge()
        out = io.StringIO()
        bridge.main(['outbox', '--state', str(self.state)], out)
        self.assertTrue(out.getvalue().startswith('=== reply to: at://'))
        self.assertIn('hello ' + DID, out.getvalue())
        self.assertIn('post --draft', out.getvalue())
        self.assertIn('--object garden-1', out.getvalue())
        self.assertIn('mark-posted', out.getvalue())
        bridge.main(['mark-posted', str(next((self.state / 'outbox').glob('*.json')))])
        out = io.StringIO()
        bridge.main(['outbox', '--state', str(self.state)], out)
        self.assertEqual(out.getvalue(), '')

    def test_real_garden_receive_end_to_end(self):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk', 'object': 'garden-1',
                            'modules': closure('Garden'), 'entry': 'initial', 'seed': garden_state(0)})
        self.assertEqual(r['status'], 'created', r)
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        self.assertEqual(self.run_bridge()['failed'], [])
        self.assertIn('planted', self.drafts()[0]['text'])

    def test_two_hundred_observations_under_fifteen_seconds(self):
        self.make('garden-1')
        self.observe([spell_post(i, 'garden-1', f'2026-10-09T10:{i // 60:02d}:{i % 60:02d}Z') for i in range(200)])
        t0 = time.time()
        self.assertEqual(len(self.run_bridge()['turns']), 200)
        self.assertLess(time.time() - t0, 15)
        self.assertEqual(len(self.drafts()), 200)


class Stub:
    """A host that speaks the new ops from canned data and records everything it is sent."""
    def __init__(self, addressee=None):
        self.ops, self.addressee, self.suspending, self.offers, self.silent = [], addressee or {}, set(), {}, set()

    def send(self, req):
        self.ops.append(req)
        op = req['op']
        if op == 'world-addressee':
            return self.addressee.get(req['parent'], {'status': 'unknown'})
        if op == 'world-offers':
            return {'status': 'offers', 'offers': self.offers.get(req['principal'], []), 'more': False}
        if op == 'world-turn' and req['object'] in self.suspending:
            return {'status': 'suspended', 'receipt': {'hash': 'h', 'height': 5, 'outcome': {'tag': 'suspended'}}}
        if op == 'world-turn':
            return {'status': 'admitted', 'receipt': {'hash': 'h', 'height': len(self.ops), 'outcome': {'tag': 'admitted'}},
                    **({} if req['object'] in self.silent else {'offers': [{'principal': req['principal'], 'text': 'to ' + req['object']}]})}
        if op == 'world-pending':
            return {'status': 'pending', 'count': 0}
        if op == 'world-publications':
            return {'status': 'publications', 'publications': [], 'more': False}
        return {'status': 'ok'}


class Routing(BridgeCase):
    def test_clock_ticks_once_per_run_and_only_in_unix_minutes(self):
        stub = Stub()
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z'), spell_post(2, 'garden-1', '2026-10-09T10:00:01Z')])
        with mock.patch.object(bridge.time, 'time', return_value=6000.0):
            bridge.run(self.state, stub)
        self.assertEqual([o for o in stub.ops if o['op'] == 'world-advance'], [{'op': 'world-advance', 'principal': 'transport', 'height': 100}])

    def test_a_reply_to_a_journaled_post_goes_to_its_addressee_not_the_card_word(self):
        parent = f'at://{DID}/town.delve.feed.post/welcome'
        stub = Stub({parent: {'status': 'addressee', 'object': 'directory', 'slot': 'welcome'}})
        plain = mk(1, 'just replying', parent=parent)
        spelled = mk(2, 'delvetalk garden-1 plant', parent=parent)
        orphan_reply = mk(3, 'replying elsewhere', parent=f'at://{DID}/town.delve.feed.post/other')
        self.observe([plain, spelled, orphan_reply, summon_post(4, '2026-10-09T10:00:09Z')])
        r = bridge.run(self.state, stub)
        turns = {t['identity'][-6:]: t for t in stub.ops if t['op'] == 'world-turn'}
        self.assertEqual({k: v['object'] for k, v in turns.items()}, {'000001': 'directory', '000002': 'directory', '000004': 'directory'})
        self.assertEqual([f['name'] for f in turns['000001']['argument']['fields']], ['text', 'post'])  # the host fills slot
        self.assertEqual(turns['000001']['replyTo'], parent)
        self.assertNotIn('replyTo', turns['000004'])  # a top-level summon answers no post
        self.assertEqual(len(r['turns']), 3)
        self.assertIn(orphan_reply['uri'], (self.state / 'skipped.txt').read_text())
        n = len([o for o in stub.ops if o['op'] == 'world-addressee'])
        bridge.run(self.state, stub)
        self.assertEqual(len([o for o in stub.ops if o['op'] == 'world-addressee']), n)  # drafts and skips are remembered

    def test_a_reply_deep_in_a_thread_routes_by_the_root_when_its_parent_has_no_address(self):
        root = f'at://{DID}/town.delve.feed.post/root01'
        mid = f'at://{DID}/town.delve.feed.post/mid001'
        stub = Stub({root: {'status': 'addressee', 'object': 'garden-1'}})
        deep = mk(1, 'silver, then', parent=mid)
        deep['record']['reply']['root'] = {'uri': root, 'cid': 'x'}
        self.observe([deep])
        bridge.run(self.state, stub)
        self.assertEqual([t['object'] for t in stub.ops if t['op'] == 'world-turn'], ['garden-1'])
        self.assertEqual([o['parent'] for o in stub.ops if o['op'] == 'world-addressee'], [mid, root])

    def test_a_deep_reply_routes_to_the_nearest_recorded_ancestor(self):
        u = lambda n: f'at://{DID}/town.delve.feed.post/t{n}'
        stub = Stub({u(2): {'status': 'addressee', 'object': 'garden-1'}, u(1): {'status': 'addressee', 'object': 'wrong'}})
        posts = [mk(1, 'root post'), mk(2, 'recorded', parent=u(1)), mk(3, 'third', parent=u(2)), mk(4, 'fourth', parent=u(3))]
        for i, (p, n) in enumerate(zip(posts, range(1, 5))):
            p['uri'] = u(n)
            p['record']['createdAt'] = f'2026-10-09T10:00:0{i}Z'
        posts[3]['record']['reply']['root'] = {'uri': u(1), 'cid': 'x'}
        self.observe(posts)
        bridge.run(self.state, stub)
        turns = {t['identity'][-2:]: t['object'] for t in stub.ops if t['op'] == 'world-turn'}
        self.assertEqual(turns['t4'], 'garden-1')  # 4 -> 3 (unknown) -> 2 (recorded): nearest, not the root
        asked = [o['parent'] for o in stub.ops if o['op'] == 'world-addressee']
        self.assertEqual(turns['t2'], 'wrong')  # its own parent is the recorded post 1
        self.assertEqual(asked.count(u(1)), 1)  # only t2 asked about the root; t3 and t4 stopped at post 2
        self.assertEqual(turns['t3'], 'garden-1')

    def test_the_walk_is_bounded_and_survives_a_cycle(self):
        a, b = f'at://{DID}/town.delve.feed.post/ca', f'at://{DID}/town.delve.feed.post/cb'
        stub = Stub()
        x, y = mk(1, 'x', parent=b), mk(2, 'y', parent=a)
        x['uri'], y['uri'] = a, b
        self.observe([x, y])
        bridge.run(self.state, stub)
        self.assertLessEqual(len([o for o in stub.ops if o['op'] == 'world-addressee']), 4)

    def test_card_word_still_routes_a_post_with_no_journaled_parent(self):
        stub = Stub()
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        bridge.run(self.state, stub)
        self.assertEqual([t['object'] for t in stub.ops if t['op'] == 'world-turn'], ['garden-1'])

    @unittest.expectedFailure
    def test_end_to_end_clock_and_addressee_against_the_real_host(self):
        # Until the host lands world-addressee: {'message': 'unknown world operation world-addressee'}
        self.assertEqual(self.host.send({'op': 'world-addressee', 'parent': 'at://x/y/z'}).get('status'), 'addressee')


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
        self.assertEqual((d['text'], d['replyTo'], d['principal'], d['posted']), ('Planted.', p['uri'], DID, False))
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
        self.assertEqual((d['text'], d['replyTo']), ('Handed over.', p['uri']))

    def test_end_to_end_a_handed_on_offer_carries_from_on_the_real_host(self):
        from deploy import genesis
        from transport.hostproc import LIBRARY
        with tempfile.TemporaryDirectory() as tmp:
            d = start_hostd(tmp, BINARY, opener=genesis.OPENER, library=LIBRARY)
            try:
                host = HostClient(Path(tmp) / 'host.sock')
                self.assertIsNone(genesis.run(host)[1])
                host.send({'op': 'world-turn', 'principal': genesis.OPENER, 'object': 'directory', 'method': 'receive', 'identity': 'handed',
                           'argument': genesis.rec(text=genesis.lab('delvetalk garden plant\nseed: a\ncolour: amber'), post=genesis.lab('at://x/p/1'), slot=genesis.lab(''))})
                offers = host.send({'op': 'world-offers', 'principal': genesis.OPENER})['offers']
                self.assertTrue(offers and all('from' in o for o in offers), offers)
            finally:
                stop_hostd(d)


class Slugs(unittest.TestCase):
    def test_a_draft_cites_the_slug_and_carries_no_cid(self):
        import re
        receipt = {'hash': 'bafyrei' + 'a' * 52, 'slug': 'babab-dabab', 'height': 9, 'roots': [{'object': 'garden', 'version': 3}], 'outcome': {'tag': 'admitted'}, 'offers': 1}
        refused = {'status': 'refused', 'receipt': {**receipt, 'outcome': {'tag': 'refused', 'class': 'lawRefused'}},
                   'public': {'class': 'lawRefused', 'root': {'object': 'garden', 'version': 3}}}
        texts = [bridge.draft_text({'receipt': receipt}, 'https://x.example'), bridge.draft_text(refused)]
        self.assertIn('receipt babab-dabab: garden v3 at height 9', texts[0])
        self.assertIn('receipt babab-dabab\n', texts[1])
        for t in texts:
            self.assertFalse(re.search(r'bafy', t), t)

    def test_end_to_end_the_host_names_receipts_with_slugs(self):
        from deploy import genesis
        from transport.hostproc import LIBRARY
        with tempfile.TemporaryDirectory() as tmp:
            d = start_hostd(tmp, BINARY, opener=genesis.OPENER, library=LIBRARY)
            try:
                host = HostClient(Path(tmp) / 'host.sock')
                self.assertIsNone(genesis.run(host)[1])
                self.assertIn('slug', host.send({'op': 'world-receipt', 'principal': genesis.OPENER, 'identity': 'genesis-garden'})['receipt'])
            finally:
                stop_hostd(d)


class Mentions(BridgeCase):
    GLM, KIMI = 'did:plc:' + 'b' * 24, 'did:plc:' + 'c' * 24

    def facet(self, text, handle, did):
        start = text.index('@' + handle)
        return {'index': {'byteStart': start, 'byteEnd': start + len(handle) + 1}, 'features': [{'$type': 'app.bsky.richtext.facet#mention', 'did': did}]}

    def seen(self, n, did, handle):
        p = mk(n, f'{handle} was here')
        p['author'] = {'did': did, 'handle': handle}
        return p

    def test_a_post_mentioning_two_handles_is_a_turn_on_each_env_under_the_author(self):
        stub = Stub()
        glm = mk(1, 'glm here')
        glm['author'] = {'did': self.GLM, 'handle': 'glm.delve.town'}
        text = 'hello @glm.delve.town and @kimi.delve.town'  # glm by a known author's handle, kimi by facet
        post = mk(2, text, facets=[self.facet(text, 'kimi.delve.town', self.KIMI)])
        self.observe([glm, self.seen(3, self.KIMI, 'kimi.delve.town'), post])
        r = bridge.run(self.state, stub)
        turns = [o for o in stub.ops if o['op'] == 'world-turn' and o['object'].startswith('env/')]
        self.assertEqual([(t['object'], t['principal'], t['method'], t['identity']) for t in turns],
                         [(f'env/{d}', DID, 'receive', f"{post['uri']}#env:{d}") for d in (self.KIMI, self.GLM)])  # facets first, then @text
        fields = {f['name']: f['value']['value'] for f in turns[0]['argument']['fields']}
        self.assertEqual(fields, {'text': text, 'post': post['uri']})
        self.assertEqual(r['mentioned'], [post['uri']])
        before = len(stub.ops)
        self.assertNotIn('mentioned', bridge.run(self.state, stub))  # once per post
        self.assertEqual([o['op'] for o in stub.ops[before:]].count('world-turn'), 0)

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
        self.assertEqual([o['object'] for o in stub.ops if o['op'] == 'world-turn'], [f'env/{self.GLM}'])
        self.assertIn(f"{post['uri']}#mention:{self.KIMI}", (self.state / 'skipped.txt').read_text().split())
        self.assertEqual(r['failed'], [])
        before = len(stub.ops)
        bridge.run(self.state, stub)
        self.assertEqual([o['op'] for o in stub.ops[before:]].count('world-turn'), 0)

    def test_only_the_first_four_mentions_are_addressed(self):
        stub = Stub()
        dids = ['did:plc:' + c * 24 for c in 'defgh']
        text = ' '.join(f'@u{i}.delve.town' for i in range(5))
        post = mk(1, text, facets=[self.facet(text, f'u{i}.delve.town', d) for i, d in enumerate(dids)])
        self.observe([post] + [self.seen(10 + i, d, f'u{i}.delve.town') for i, d in enumerate(dids)])
        bridge.run(self.state, stub)
        self.assertEqual([o['object'] for o in stub.ops if o['op'] == 'world-turn'], [f'env/{d}' for d in dids[:4]])


class Unaddressed(BridgeCase):
    def run_refused(self, post):
        parent = f'at://{DID}/town.delve.feed.post/welcome'
        stub = Stub({parent: {'status': 'addressee', 'object': 'directory', 'slot': 'welcome'}})
        real = stub.send
        stub.send = lambda req: ({'status': 'refused', 'receipt': {'hash': 'h', 'height': 5, 'outcome': {'tag': 'refused', 'class': 'budget'}}}
                                 if req['op'] == 'world-turn' else real(req))
        self.observe([post])
        bridge.run(self.state, stub)
        return self.drafts()

    def test_a_plain_reply_refused_budget_gets_no_draft_but_a_spell_does(self):
        parent = f'at://{DID}/town.delve.feed.post/welcome'
        (chatter,) = self.run_refused(mk(1, 'lovely thread, thanks all', parent=parent))
        self.assertEqual(chatter['text'], '')  # journaled, listed by `outbox --all`, never drafted
        self.assertEqual(chatter['receipt']['outcome']['class'], 'budget')

    def test_a_spell_refused_budget_is_drafted(self):
        (spell,) = self.run_refused(spell_post(2, 'garden-1', '2026-10-09T10:00:00Z'))
        self.assertIn('reason: budget', spell['text'])

    def test_field_lines_in_a_reply_count_as_addressed(self):
        parent = f'at://{DID}/town.delve.feed.post/welcome'
        (fields,) = self.run_refused(mk(3, 'plant: a fern\ncolour: silver', parent=parent))
        self.assertIn('reason: budget', fields['text'])


class Silence(BridgeCase):
    def test_a_turn_that_offers_nothing_has_no_draft_in_the_outbox_unless_asked(self):
        stub = Stub()
        stub.silent = {'garden-1'}
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        self.assertEqual(len(bridge.run(self.state, stub)['turns']), 1)
        self.assertEqual(bridge.run(self.state, stub)['turns'], [])  # journaled once, not re-run
        out = io.StringIO()
        bridge.main(['outbox', '--state', str(self.state)], out)
        self.assertEqual(out.getvalue(), '')
        out = io.StringIO()
        bridge.main(['outbox', '--state', str(self.state), '--all'], out)
        self.assertIn('=== reply to:', out.getvalue())


class RealOffers(test_outbound.Offers):
    def test_offer_drafts_match_the_hosts_real_identity_shape(self):
        self.turn("teller", "tell", record(to=label(""), text=label("hello")), principal="ann", identity="t-1")
        self.assertIsInstance(self.host.send(op="world-offers", principal="ann")["offers"][0]["identity"], dict)
        with tempfile.TemporaryDirectory() as d:
            bridge.write_atomic(bridge.awaiting_path(d, "t-1"), {"uri": "t-1", "principal": "ann", "replyHandle": "ann.delve.town",
                                                                 "object": "teller", "slot": None, "height": 0})
            outer = self

            class H:
                def send(self, req):
                    return outer.host.send(**req)
            self.assertEqual(bridge.offer_drafts(d, H()), ["t-1"])
            (draft,) = list((Path(d) / "outbox").glob("*.json"))
            self.assertEqual(json.loads(draft.read_text())["text"], "hello")
            self.assertEqual(bridge.offer_drafts(d, H()), [])


class Projection(unittest.TestCase):
    def test_a_refusal_draft_is_the_hosts_public_projection_verbatim_and_nothing_else(self):
        reply = {'status': 'refused', 'receipt': {'hash': 'h', 'outcome': {'tag': 'refused', 'class': 'unknownObject', 'reason': 'SECRET state'}},
                 'public': {'status': 'refused', 'class': 'unknownObject', 'root': {'object': 'nope'}, 'object': 'nope', 'hint': 'try garden'}}
        text = bridge.draft_text(reply)
        self.assertEqual(text, 'proposal observed, not committed\nreason: unknownObject\nroot: nope\nobject: nope\nhint: try garden\n')
        self.assertNotIn('SECRET', text)
        reply['public'] = {'status': 'refused', 'class': 'lawRefused', 'root': {'object': 'm', 'version': 2, 'cid': 'bafy' + 'a' * 50}}
        self.assertEqual(bridge.draft_text(reply), 'proposal observed, not committed\nreason: lawRefused\nroot: m v2\n')
        self.assertEqual(bridge.draft_text(reply, 'https://x.example/'),
                         'proposal observed, not committed\nreason: lawRefused\nroot: m v2\nhttps://x.example/o/m#v2\n')

    def test_no_draft_text_carries_a_hash_or_a_blob(self):
        import re
        h = 'bafyrei' + 'a' * 52
        receipt = {'hash': h, 'height': 9, 'roots': [{'object': 'garden', 'version': 3}], 'outcome': {'tag': 'admitted'}, 'offers': 1}
        texts = [bridge.draft_text({'receipt': receipt}, 'https://x.example'),
                 bridge.draft_text({'status': 'refused', 'receipt': {**receipt, 'hash': 'f' * 64, 'outcome': {'tag': 'refused', 'class': 'lawRefused'}}}, 'https://x.example'),
                 bridge.draft_text({'status': 'refused', 'receipt': receipt, 'public': {'class': 'lawRefused', 'root': {'object': 'g', 'version': 1, 'cid': h}}})]
        self.assertIn('receipt: garden v3 at height 9\nhttps://x.example/o/garden#v3', texts[0])
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
        self.assertEqual(stub.ops[first_turn - 1]['op'], 'world-arrive')
        bridge.run(self.state, stub)
        self.assertEqual(len([o for o in stub.ops if o['op'] == 'world-arrive']), 2)

    def test_end_to_end_arrive_against_the_real_host(self):
        from transport.hostproc import LIBRARY
        with tempfile.TemporaryDirectory() as tmp:
            d = start_hostd(tmp, BINARY, opener=DID, library=LIBRARY)
            try:
                got = HostClient(Path(tmp) / 'host.sock').send({'op': 'world-arrive', 'principal': 'transport', 'did': DID, 'handle': 'talkie.delve.town'})
                self.assertEqual(len(got.get('created', [])), 3, got)
            finally:
                stop_hostd(d)


class RealAwaitPost(test_outbound.ReplyIsAddress):
    def test_a_bridged_reply_settles_a_waiting_awaitPost_on_the_real_host(self):
        waiting = self.turn("w", "waitFor", record(post=label(test_outbound.URI)), principal="ann", identity="wait-1")
        self.assertEqual(waiting["status"], "suspended", waiting)
        self.posted(test_outbound.URI, obj="card")
        outer = self

        class H:
            def send(self, req):
                return outer.host.send(**req)
        reply = mk(1, "thanks", parent=test_outbound.URI)
        t = Script(**{'town.delve.feed.searchPosts': lambda p: (200, {'posts': [reply]}),
                      'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})
        with tempfile.TemporaryDirectory() as d:
            observe.Observer(d, delve.Client(t)).poll()
            result = bridge.run(d, H(), now=60)  # the clock stays inside the waiter's patience
        self.assertEqual(result["turns"], [reply["uri"]], result)
        self.assertTrue(self.note().startswith("answered by"), self.note())


class Daemon(unittest.TestCase):
    def test_loops_until_stopped_writes_and_removes_the_pid_file(self):
        import os
        import threading
        with tempfile.TemporaryDirectory() as d:
            stop, steps = threading.Event(), []

            def step():
                steps.append(1)
                self.assertEqual(Path(d, 'bridge.pid').read_text(), str(os.getpid()))
                if len(steps) == 3:
                    stop.set()
            bridge.daemon(d, 'bridge', 0, step, stop)
            self.assertEqual(len(steps), 3)
            self.assertFalse(Path(d, 'bridge.pid').exists())

    def test_each_finished_step_refreshes_the_pid_file(self):
        import os
        import threading
        with tempfile.TemporaryDirectory() as d:
            stop, seen = threading.Event(), []
            pid = Path(d, 'bridge.pid')

            def step():
                seen.append(pid.stat().st_mtime)
                os.utime(pid, (0, 0))  # as if the previous step finished long ago
                if len(seen) == 2:
                    stop.set()
            bridge.daemon(d, 'bridge', 0, step, stop)
            self.assertGreater(seen[1], 0)

    def test_a_live_pid_file_blocks_a_second_daemon(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'bridge.pid').write_text(str(os.getpid()))
            with self.assertRaises(SystemExit):
                bridge.daemon(d, 'bridge', 0, lambda: None)
            Path(d, 'bridge.pid').write_text('999999')  # stale
            import threading
            stop = threading.Event()
            bridge.daemon(d, 'bridge', 0, stop.set, stop)


if __name__ == '__main__':
    unittest.main()
