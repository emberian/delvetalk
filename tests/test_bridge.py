import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

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
        self.assertEqual(d['text'], f"proposal observed, not committed\nreason: lawRefused\nreceipt: {d['receipt']['hash']}\n")

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
        self.ops, self.addressee, self.suspending, self.offers = [], addressee or {}, set(), {}

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
                    'offers': [{'principal': req['principal'], 'text': 'to ' + req['object']}]}
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
        slot = {f['name']: f['value']['value'] for f in turns['000001']['argument']['fields']}['slot']
        self.assertEqual(slot, 'welcome')
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
        stub.offers[DID] = [{'height': 9, 'ordinal': 0, 'identity': p['uri'], 'text': 'Planted.'},
                            {'height': 9, 'ordinal': 1, 'identity': 'someone-else', 'text': 'not mine'}]
        r = bridge.run(self.state, stub)
        self.assertEqual(r['offered'], [p['uri']])
        (d,) = self.drafts()
        self.assertEqual((d['text'], d['replyTo'], d['principal'], d['posted']), ('Planted.', p['uri'], DID, False))
        self.assertNotIn('offered', bridge.run(self.state, stub))
        self.assertEqual(len(self.drafts()), 1)


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
