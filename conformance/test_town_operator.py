"""Durable operator loop: actual Lean, GET-only card binding and lost-reply recovery."""
import copy
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import town
from conformance import test_town_receiving as receiving_fixture
A, B = receiving_fixture.A, receiving_fixture.B


class TownOperatorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = receiving_fixture.TownReceivingTests(methodName='test_current_law_and_stale_root_remain_lean_decisions')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.operator = town.Town(self.fixture.c.state, request=self.fixture.pds)

    def test_capture_bind_receive_and_same_retained_response_without_network(self):
        f = self.fixture
        card = self.operator.capture('counter', alias='opening')
        publication = {**f.parent, 'uri': f.parent['uri'] + '-opening', 'cid': 'opening-cid'}
        f.pds.records[publication['uri']] = (publication['cid'], {'$type': town.clerk.FEED, 'text': 'Welcome!\n' + card['body']})
        self.operator.bind('opening', publication['uri'], publication['cid'])
        source = f.post('operator', text='delvetalk opening a1 {"amount":4}', parent=publication)
        response = self.operator.receive(*source)
        self.assertEqual(response['receipt']['reply']['kind'], 'committed')
        self.assertEqual(response['cards'][0]['view']['root']['state']['count'], 4)
        self.assertIn('original reply', response['body'])
        self.assertIn('delvetalk reply-1-1', response['body'])
        before = f.c.database.read_bytes()
        f.pds.records.clear()
        restarted = town.Town(f.c.state, request=f.pds)
        with patch.object(restarted, '_configuration', side_effect=AssertionError('no reconfiguration')):
            self.assertEqual(restarted.receive(*source), response)
        self.assertEqual(f.c.database.read_bytes(), before)
        self.assertEqual(f.book.aliases(), ['counter', 'opening', 'reply-1-1'])
        with self.assertRaisesRegex(ValueError, 'different CID'):
            restarted.receive(source[0], 'edited')

    def test_uncertain_admission_recovery_does_not_repeat_application_action(self):
        f = self.fixture
        source = f.post('lost')
        receive = self.operator.clerk.receive
        def lose(uri, cid):
            receive(uri, cid)
            raise OSError('reply lost after commit')
        with patch.object(self.operator.clerk, 'receive', side_effect=lose):
            unknown = self.operator.receive(*source)
        self.assertEqual(unknown['status'], 'uncertain')
        self.assertIn('Do not repost', unknown['body'])
        self.assertNotIn('cards', unknown)
        self.assertEqual(f.c.snapshot('counter')['root']['state']['count'], 3)
        f.pds.records.clear()
        recovered = town.Town(f.c.state, request=f.pds).receive(*source)
        self.assertEqual(recovered['receipt']['reply']['kind'], 'committed')
        self.assertEqual(f.c.snapshot('counter')['root']['state']['count'], 3)
        self.assertEqual(recovered['cards'][0]['alias'], 'reply-1-1')

    def test_lost_response_save_keeps_captured_view_alias_and_body_after_world_advances(self):
        f = self.fixture
        source = f.post('lost-response')
        save = town.save
        def lose(path, value):
            if 'response' in value:
                raise OSError('failed final response custody')
            save(path, value)
        with patch.object(town, 'save', side_effect=lose), self.assertRaises(OSError):
            self.operator.receive(*source)
        first_card = f.book.card('reply-1-1')
        root = f.c.snapshot('counter')['root']
        later = town.clerk.world.exchange(f.c.database, {'op': 'invoke', 'object': 'counter', 'principal': A,
            'intent': 'later', 'expected': root, 'command': 'add', 'input': {'amount': 2}})
        self.assertEqual(later['kind'], 'committed')
        response = town.Town(f.c.state, request=f.pds).receive(*source)
        self.assertEqual(response['cards'][0], first_card)
        self.assertEqual(response['cards'][0]['view']['root']['state']['count'], 3)
        self.assertEqual(f.c.snapshot('counter')['root']['state']['count'], 5)
        self.assertEqual(f.book.aliases(), ['counter', 'reply-1-1'])

    def test_stale_and_unauthorized_refusals_produce_current_next_card_without_writes(self):
        f = self.fixture
        self.operator.receive(*f.post('first'))
        stale = self.operator.receive(*f.post('second'))
        self.assertEqual(stale['receipt']['reply']['data'], 'stale read root')
        self.assertEqual(stale['cards'][0]['view']['root']['state']['count'], 3)
        f.capture('current', f.c.snapshot('counter')['root'])
        denied = self.operator.receive(*f.post('denied', author=B, text='delvetalk current a1 {"amount":2}'))
        self.assertEqual(denied['receipt']['reply']['data'], 'unauthorized')
        self.assertIn('refused', denied['body'])
        self.assertEqual(f.c.snapshot('counter')['root']['state']['count'], 3)

    def test_factory_refusal_skips_absent_read_and_commit_captures_enrolled_child(self):
        f = self.fixture
        protocol = town.loads((ROOT / 'conformance/fixtures/allocation-object.json').read_bytes())
        changed = town.clerk.world.exchange(f.c.database, {'op': 'reprogram', 'object': 'counter',
            'principal': A, 'intent': 'install-factory', 'expected': f.root,
            'protocol': protocol, 'state': protocol['initial']})
        self.assertEqual(changed['kind'], 'committed')
        root = changed['data']['root']
        f.capture('factory', root)
        transaction = {'op': 'transaction', 'reads': {'counter': {'expected': root}, 'counter/missing': {'expected': None}},
            'calls': [{'object': 'counter', 'command': 'make', 'input': {'name': 'missing'}}]}
        text = 'delvetalk-request v1\n\n```delvetalk-request\n' + town.clerk.world.wire_dumps(transaction) + '\n```'
        refused = self.operator.receive(*f.post('absent-refusal', author=B, text=text))
        self.assertEqual(refused['receipt']['reply']['kind'], 'refused')
        self.assertEqual(refused['notices'], [{'object': 'counter/missing', 'reason': 'absent'}])
        created = self.operator.receive(*f.post('make-child', text='delvetalk factory a1 {"name":"lamp"}'))
        self.assertEqual(created['receipt']['reply']['kind'], 'committed')
        self.assertEqual({c['card']['object'] for c in created['cards']}, {'counter', 'counter/lamp'})
        self.assertIn('counter/lamp', f.c.config()['objects'])
        child = next(c for c in created['cards'] if c['card']['object'] == 'counter/lamp')
        reference = {**f.parent, 'uri': f.parent['uri'] + '-outcome', 'cid': 'outcome-cid'}
        f.pds.records[reference['uri']] = (reference['cid'], {'$type': town.clerk.FEED, 'text': created['body']})
        self.operator.bind(child['alias'], reference['uri'], reference['cid'])
        used = self.operator.receive(*f.post('write-child', parent=reference,
            text='delvetalk ' + child['alias'] + ' a1 {"text":"Hello child"}'))
        self.assertEqual(used['receipt']['reply']['kind'], 'committed')
        self.assertEqual(f.c.snapshot('counter/lamp')['root']['state']['text'], 'Hello child')

    def test_unrenderable_current_view_preserves_receipt_and_explains_missing_card(self):
        f = self.fixture
        protocol = copy.deepcopy(f.root['protocol'])
        protocol['affordances'] = {'profile': 'unknown-future-metadata'}
        changed = town.clerk.world.exchange(f.c.database, {'op': 'reprogram', 'object': 'counter',
            'principal': A, 'intent': 'opaque-view', 'expected': f.root,
            'protocol': protocol, 'state': f.root['state']})
        self.assertEqual(changed['kind'], 'committed')
        source = f.post('opaque-current')
        result = self.operator.receive(*source)
        self.assertEqual(result['receipt']['reply']['kind'], 'refused')
        self.assertEqual(result['cards'], [])
        self.assertEqual(result['notices'][0]['reason'], 'card-unavailable')
        self.assertIn('No next card for', result['body'])
        self.assertEqual(self.operator.receive(*source), result)

    def test_get_binding_identity_scope_and_cli_capture_are_explicit(self):
        f = self.fixture
        with self.assertRaisesRegex(ValueError, 'enrolled'): self.operator.capture('unknown')
        with self.assertRaises(ValueError): self.operator.bind('counter', f.parent['uri'], 'wrong-cid')
        command = [sys.executable, str(ROOT / 'scripts/town.py'), '--clerk-state', str(f.c.state),
                   '--text', 'capture', 'counter', '--alias', 'cli-card']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith('[[delvetalk-card cli-card]]'))
        self.assertNotIn('textSha256', result.stdout)
        other = town.Town(f.c.state, state=f.base / 'other-operator', request=f.pds)
        with self.assertRaisesRegex(ValueError, 'another operator'): other.capture('counter')
        with patch.object(town.clerk, 'pins', return_value={}):
            with self.assertRaisesRegex(ValueError, 'pins changed'): self.operator.capture('counter')


if __name__ == '__main__': unittest.main()
