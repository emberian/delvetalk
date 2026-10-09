"""Actual native account realms, durable source evaluation and governed programming."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import agent_heaps as heaps
import desk
import world

ALICE = {'accountId': 'a' * 32, 'did': 'did:plc:' + 'a' * 24}
BOB = {'accountId': 'b' * 32, 'did': 'did:plc:' + 'b' * 24}
SOURCE = {'modules': [{'name': 'Main', 'source': 'edition ObjectiveBend 1\ndef answer() -> Nat:\n  6n * 7n\n'}],
          'entry': 'answer', 'arguments': []}


class AccountHeaps(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shared = self.root / 'shared.json'
        self.shared_protocol = {'profile': 'delvetalk-local-v1', 'initial': {'n': 0}, 'commands': {
            'set': {'require': [], 'set': {'n': ['input', 'n']}, 'outbox': [], 'result': ['state', 'n']}}}
        reply = world.exchange(self.shared, {'op': 'create', 'principal': 'operator', 'intent': 'seed',
            'object': 'garden', 'protocol': self.shared_protocol, 'law': [ALICE['did']]}, profile='compiled')
        self.assertEqual(reply['kind'], 'committed')

    def manager(self, **options):
        return heaps.HeapManager(self.root / 'accounts', self.shared, max_active=1, **options)

    def test_native_restart_isolation_source_repl_and_authored_encounter(self):
        with self.manager() as manager:
            alice = manager.catalogue(ALICE)
            bob = manager.catalogue(BOB)
            self.assertNotEqual(alice['world'], bob['world'])
            self.assertEqual(alice['head']['sequence'], 3)  # lineage, notebook, source desk
            card = manager.encounter(ALICE, 'private', 'notebook')
            draft = manager.prepare(ALICE, 'private', {'card': card['card'], 'action': card['actions'][0]['id'],
                'fields': {'source': 'Alice secret', 'result': 'A private thought'}})
            receipt = manager.execute(ALICE, 'private', {'draft': draft['draft']})
            self.assertEqual(receipt['kind'], 'committed')
            self.assertEqual(manager.receipt(ALICE, 'private', draft['intent']), receipt['reply'])
            with self.assertRaises(ValueError): manager.reading(BOB, 'private', 'draft', draft['draft'])
            self.assertNotIn('Alice secret', heaps.encoded(manager.catalogue(BOB)).decode())
            self.assertNotIn('Alice secret', heaps.encoded(manager.catalogue(ALICE, 'shared')).decode())
            result = manager.repl(ALICE, 'private', 'experiment', SOURCE)
            self.assertEqual(result['evaluation']['value'], {'tag': 'natural', 'value': '42'})
            self.assertEqual(result['receipt']['kind'], 'committed')
            seal = manager.checkpoint(ALICE)
            self.assertTrue(seal)
        with self.manager() as restarted:
            self.assertEqual(restarted.catalogue(ALICE)['world'], alice['world'])
            with mock.patch.object(restarted, '_evaluate', side_effect=AssertionError('repeat evaluation')):
                self.assertEqual(restarted.repl(ALICE, 'private', 'experiment', SOURCE), result)
            self.assertEqual(restarted.execute(ALICE, 'private', {'draft': draft['draft']}), receipt)
            self.assertEqual(restarted.catalogue(BOB)['head']['sequence'], 3)

    def test_source_interpretation_retains_one_job_and_account_bound_draft(self):
        calls = []
        def provider(body):
            calls.append(body)
            return {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text':
                '{"action":"record","fields":{"source":"Alice private thought","result":"not executed"}}'}]}
        with self.manager(model_provider=provider) as manager:
            card = manager.encounter(ALICE, 'private', 'notebook')
            original = {'card': card['card'], 'text': 'Keep my private thought.'}
            result = manager.interpretation(ALICE, 'private', original)
            self.assertEqual(result['status'], 'ready', result)
            self.assertEqual(len(calls), 1)
            self.assertEqual(manager.interpretation(ALICE, 'private', original), result)
            self.assertEqual(len(calls), 1)
            saved = manager.reading(ALICE, 'private', 'interpretation', result['interpretation'])
            self.assertEqual(saved['input'], original)
            self.assertIn('sourceRequest', saved)
            with self.assertRaises(ValueError):
                manager.reading(BOB, 'private', 'interpretation', result['interpretation'])
            with self.assertRaises(ValueError):
                manager.execute(BOB, 'private', {'draft': result['draft']['draft']})
            committed = manager.execute(ALICE, 'private', {'draft': result['draft']['draft']})
            self.assertEqual(committed['kind'], 'committed', committed)
            visible = manager.encounter(ALICE, 'private', 'notebook')
            self.assertIn('Keep my private thought.', visible['prose'])
            self.assertEqual(manager.interpretation(ALICE, 'private', original), result)
            self.assertEqual(len(calls), 1)
        with self.manager(model_provider=provider) as restarted:
            self.assertEqual(restarted.interpretation(ALICE, 'private', original), result)
            self.assertEqual(restarted.execute(ALICE, 'private', {'draft': result['draft']['draft']}), committed)
            self.assertEqual(len(calls), 1)

    def test_literal_bypasses_provider_and_uncertain_model_job_is_retained(self):
        calls = []
        def unavailable(body):
            calls.append(body)
            raise TimeoutError('private provider detail must not escape')
        with self.manager(model_provider=unavailable) as manager:
            card = manager.encounter(ALICE, 'private', 'notebook')
            action = card['actions'][0]
            literal = {'card': card['card'], 'text': action['token'] + ' {"source":"a note","result":""}'}
            routed = manager.interpretation(ALICE, 'private', literal)
            self.assertEqual(routed['status'], 'proposed', routed)
            self.assertEqual(calls, [])
            payload = {'card': card['card'], 'text': 'Please keep this thought.'}
            result = manager.interpretation(ALICE, 'private', payload)
            self.assertEqual(result['status'], 'uncertain', result)
            self.assertNotIn('private provider detail', heaps.encoded(result).decode())
            self.assertEqual(manager.interpretation(ALICE, 'private', payload), result)
            self.assertEqual(len(calls), 1)
            saved = manager.reading(ALICE, 'private', 'interpretation', result['interpretation'])
            self.assertEqual(saved['providerReceipt']['status'], 'uncertain')

    def test_encounter_quota_applies_to_completion_and_replacement(self):
        with self.manager(operation_bytes=128, max_entries=2) as manager:
            path = self.root / 'accounts' / 'test' / 'encounters' / 'private' / 'interpretations' / 'record.json'
            manager._save_encounter(path, {'pending': True})
            with self.assertRaisesRegex(heaps.HeapLimit, 'encounter custody'):
                manager._save_encounter(path, {'completion': 'x' * 128})
            self.assertEqual(world.wire_loads(path.read_bytes()), {'pending': True})
            manager._save_encounter(path, {'completion': 'small'})
            self.assertEqual(world.wire_loads(path.read_bytes()), {'completion': 'small'})

    def test_shared_native_law_account_namespace_and_no_principal_choice(self):
        with self.manager() as manager:
            shared = manager.inspect(ALICE, 'shared', 'garden')
            request = {'op': 'invoke', 'object': 'garden', 'intent': 'garden-touch',
                       'expected': shared, 'command': 'set', 'input': {'n': 9}}
            self.assertEqual(manager.turn(BOB, 'shared', request)['kind'], 'refused')
            self.assertEqual(manager.turn(ALICE, 'shared', request)['kind'], 'committed')
            with self.assertRaisesRegex(ValueError, 'omit principal'):
                manager.turn(BOB, 'shared', {**request, 'principal': ALICE['did']})
            create = {'op': 'create', 'intent': 'own-object', 'object': 'reserved',
                      'protocol': self.shared_protocol, 'law': [ALICE['did']]}
            with self.assertRaisesRegex(ValueError, 'assigned agent namespace'):
                manager.turn(ALICE, 'shared', create)
            create['object'] = manager.catalogue(ALICE, 'shared')['sharedCreatePrefix'] + 'counter'
            self.assertEqual(manager.turn(ALICE, 'shared', create)['kind'], 'committed')

    def test_physical_quota_refusal_restarts_without_admitting_or_wedging(self):
        with self.manager(max_accounts=1, max_entries=3) as manager:
            initial = manager.inspect(ALICE, 'private', 'notebook')
            with self.assertRaisesRegex(heaps.HeapLimit, 'journal quota'):
                manager.turn(ALICE, 'private', {'op': 'invoke', 'object': 'notebook', 'intent': 'over-quota',
                    'expected': initial, 'command': 'record', 'input': {'source': 'too late', 'result': ''}})
            self.assertEqual(manager.inspect(ALICE, 'private', 'notebook'), initial)
            self.assertIsNone(manager.receipt(ALICE, 'private', 'over-quota'))
            with self.assertRaisesRegex(heaps.HeapLimit, 'account heap quota'):
                manager.catalogue(BOB)
            with self.assertRaisesRegex(ValueError, 'binding differs'):
                manager.catalogue({**ALICE, 'did': BOB['did']})

    def test_shared_realm_custody_cannot_be_retargeted_on_restart(self):
        with self.manager(): pass
        with self.assertRaisesRegex(ValueError, 'another shared realm'):
            heaps.HeapManager(self.root / 'accounts', self.root / 'another.json')
        with self.assertRaisesRegex(ValueError, 'another shared realm'):
            heaps.HeapManager(self.root / 'accounts', self.shared, shared_world='another-world')

    def test_private_source_desk_compiles_and_atomically_programs(self):
        source = (ROOT / 'syntaxes/examples/lantern.obend').read_text()
        scenarios = '[{"name":"light","law":["visitor"],"steps":[{"principal":"visitor","command":"light","input":{},"root":"initial","kind":"committed","state":{"lit":true},"result":"A small sun for lost moths.","outbox":[]}]}]'
        with self.manager(timeout=20) as manager:
            candidate = manager.inspect(ALICE, 'private', 'source-desk')
            target = manager.turn(ALICE, 'private', {'op': 'create', 'intent': 'target', 'object': 'lantern',
                'protocol': self.shared_protocol, 'law': [ALICE['did']]})['data']['root']
            pending = manager.turn(ALICE, 'private', {'op': 'invoke', 'intent': 'submit', 'object': 'source-desk',
                'expected': candidate, 'command': 'submit', 'input': {'proposal': {
                    'syntax': 'objective-bend-spell@2', 'source': source, 'scenarios': scenarios},
                    'migration': {'lit': False}, 'target': 'lantern'}})['data']['root']
            compiled = manager.check(ALICE, 'private', 'source-desk', 'check', pending)
            self.assertEqual(compiled['kind'], 'committed', compiled)
            ready = compiled['data']['root']
            self.assertEqual(desk.candidate_state(ready)['status'], 'ready', desk.candidate_state(ready))
            with mock.patch.object(desk, 'bounded_compile', side_effect=AssertionError('recompiled')):
                self.assertEqual(manager.check(ALICE, 'private', 'source-desk', 'check', pending), compiled)
            request = desk.adoption.request('source-desk', 'lantern', ALICE['did'], 'adopt', ready, target)
            request.pop('principal')
            adopted = manager.turn(ALICE, 'private', request)
            self.assertEqual(adopted['kind'], 'committed', adopted)
            lantern = manager.inspect(ALICE, 'private', 'lantern')
            played = manager.turn(ALICE, 'private', {'op': 'invoke', 'object': 'lantern', 'intent': 'light',
                'expected': lantern, 'command': 'light', 'input': {}})
            self.assertEqual(played['kind'], 'committed', played)
            self.assertEqual(played['data']['root']['state'], {'lit': True})


if __name__ == '__main__': unittest.main()
