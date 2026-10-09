import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.test_http import BINARY
from tests.test_transport import DID, Script, mk
from tests.test_turn_world import closure, label, nat, record
from transport import bridge, delve, observe
from transport.http import Host

CARD = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
import ./Plan.obend as Plans
record State:
  seen: Nat
record Edits:
  seen: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits, {}>
type Response = Plans.Response<State, Nat>
%s
def initial() -> State:
  {seen: 5n}
def receive(state: State, input: {text: String, who: String, post: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
%s
"""
OFFERING = """  match perform(Plan.offer({to: "", document: Document.text(textConcat("hello ", input.who))})):
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
        self.host = Host(str(Path(self.tmp.name) / 'world.journal'), BINARY)
        self.addCleanup(self.host.close)

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
        bridge.main(['mark-posted', str(next((self.state / 'outbox').glob('*.json')))])
        out = io.StringIO()
        bridge.main(['outbox', '--state', str(self.state)], out)
        self.assertEqual(out.getvalue(), '')

    def test_real_garden_receive_end_to_end(self):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk', 'object': 'garden-1',
                            'modules': closure('Garden'), 'entry': 'initial', 'seed': record(planted=nat(0), policy=record(world=label(""), object=label("")))})
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


if __name__ == '__main__':
    unittest.main()
