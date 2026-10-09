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
import source_object

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
        self.shared_protocol = source_object.load([{'name': 'Counter', 'source':
            (ROOT / 'examples/current-objects/Counter.obend').read_text()}], syntax='objective-bend-object')
        self.shared_law = {'profile': 'delvetalk-scoped-law', 'invoke': {'add': [ALICE['did']]},
                           'read': 'public', 'reprogram': [ALICE['did']], 'law': [ALICE['did']]}
        reply = world.exchange(self.shared, {'op': 'create', 'principal': 'operator', 'intent': 'seed',
            'object': 'garden', 'protocol': self.shared_protocol, 'law': self.shared_law}, profile='compiled')
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
            self.assertEqual(card['actions'][0]['label'], 'Keep a thought')
            self.assertEqual([field['name'] for field in card['actions'][0]['fields']], ['thought'])
            draft = manager.prepare(ALICE, 'private', {'card': card['card'], 'action': card['actions'][0]['id'],
                'fields': {'thought': 'Alice secret'}})
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
                '```json\n{"action":"note","fields":{"thought":"Alice private thought"}}\n```'}]}
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
            self.assertEqual(saved['sourceRequest']['envelope']['tag'], 'record')
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
            literal = {'card': card['card'], 'text': action['token'] + ' {"thought":"a note"}'}
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

    def test_malformed_provider_output_is_visible_and_recovered_without_clarification_loop(self):
        calls = []
        def malformed(body):
            calls.append(body)
            return {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'Here is a proposal: {not-json}'}]}
        with self.manager(model_provider=malformed) as manager:
            card = manager.encounter(ALICE, 'private', 'notebook')
            payload = {'card': card['card'], 'text': 'Keep this later.'}
            result = manager.interpretation(ALICE, 'private', payload)
            self.assertEqual(result['status'], 'provider-error', result)
            self.assertNotIn('draft', result)
            self.assertEqual(manager.interpretation(ALICE, 'private', payload), result)
            saved = manager.reading(ALICE, 'private', 'interpretation', result['interpretation'])
            self.assertEqual(saved['providerReceipt']['status'], 'received')
            self.assertEqual(saved['providerReceipt']['reply']['content'][0]['text'], 'Here is a proposal: {not-json}')
        with self.manager(model_provider=malformed) as restarted:
            self.assertEqual(restarted.interpretation(ALICE, 'private', payload), result)
        self.assertEqual(len(calls), 1)

    def test_encounter_quota_applies_to_completion_and_replacement(self):
        with self.manager(operation_bytes=128, max_entries=2) as manager:
            path = self.root / 'accounts' / 'test' / 'encounters' / 'private' / 'interpretations' / 'record.json'
            manager._save_encounter(path, {'pending': True})
            with self.assertRaisesRegex(heaps.HeapLimit, 'encounter custody'):
                manager._save_encounter(path, {'completion': 'x' * 128})
            self.assertEqual(world.wire_loads(path.read_bytes()), {'pending': True})
            manager._save_encounter(path, {'completion': 'small'})
            self.assertEqual(world.wire_loads(path.read_bytes()), {'completion': 'small'})

    def test_original_seed_survives_interrupted_admission_and_template_change(self):
        original = heaps.QuotaResident.exchange
        interrupted = []
        def lose_reply(receiver, request):
            reply = original(receiver, request)
            if request.get('intent') == heaps.RESERVED + 'notebook' and not interrupted:
                interrupted.append(True)
                raise TimeoutError('lost initial notebook reply')
            return reply
        seeds = [('notebook', self.shared_protocol), ('source-desk', self.shared_protocol)]
        with self.manager() as manager:
            with mock.patch.object(manager, '_seed_protocols', return_value=seeds), \
                    mock.patch.object(heaps.QuotaResident, 'exchange', lose_reply):
                with self.assertRaises(TimeoutError):
                    manager.inspect(ALICE, 'private', 'notebook')
            identity, key = manager._identity(ALICE)
            path = manager.root / key / 'seed.json'
            retained = world.wire_loads(path.read_bytes())
            self.assertEqual(retained['identity'], ALICE)
            self.assertEqual(retained['requests'][1]['protocol'], self.shared_protocol)
        with self.manager() as restarted:
            with mock.patch.object(restarted, '_seed_protocols', side_effect=AssertionError('new template consulted')):
                notebook = restarted.inspect(ALICE, 'private', 'notebook')
                candidate = restarted.inspect(ALICE, 'private', 'source-desk')
            self.assertEqual(source_object.plain(source_object.state_data(notebook)), {'count': 0})
            self.assertEqual(notebook['law']['invoke']['add'], [ALICE['did']])
            self.assertEqual(candidate['law']['invoke']['add'], [ALICE['did']])
            self.assertEqual(world.wire_loads(path.read_bytes()), retained)
            self.assertEqual(restarted._call(lambda: next(iter(restarted.active.values())).sequence), 3)

    def test_shared_native_law_account_namespace_and_no_principal_choice(self):
        with self.manager() as manager:
            shared = manager.inspect(ALICE, 'shared', 'garden')
            request = {'op': 'invoke', 'object': 'garden', 'intent': 'garden-touch',
                       'expected': shared, 'command': 'add', 'input': {'amount': 9}}
            self.assertEqual(manager.turn(BOB, 'shared', request)['kind'], 'refused')
            self.assertEqual(manager.turn(ALICE, 'shared', request)['kind'], 'committed')
            with self.assertRaisesRegex(ValueError, 'omit principal'):
                manager.turn(BOB, 'shared', {**request, 'principal': ALICE['did']})
            create = {'op': 'create', 'intent': 'own-object', 'object': 'reserved',
                      'protocol': self.shared_protocol, 'law': self.shared_law}
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
        source = (ROOT / 'conformance/fixtures/AccountLantern.obend').read_text()
        migration = source_object.load([{'name': 'Main', 'source': source}],
                                       syntax='objective-bend-object')['initial']
        scenarios = """examples DelveTalk 1
case light the lantern
law visitor
as visitor
send light
expect result (String): A small sun for lost moths.
"""
        with self.manager(timeout=20) as manager:
            candidate = manager.inspect(ALICE, 'private', 'source-desk')
            manager.turn(ALICE, 'private', {'op': 'create', 'intent': 'target', 'object': 'lantern',
                'protocol': self.shared_protocol, 'law': {**self.shared_law,
                    'invoke': {'light': [ALICE['did']], 'douse': [ALICE['did']]}}})
            pending = manager.turn(ALICE, 'private', {'op': 'invoke', 'intent': 'submit', 'object': 'source-desk',
                'expected': candidate, 'command': 'submit', 'input': {'proposal': {
                    'syntax': 'objective-bend-object', 'source': source, 'scenarios': scenarios},
                    'migration': migration, 'target': 'lantern'}})['data']['root']
            requested = manager.turn(ALICE, 'private', {'op': 'invoke', 'intent': 'request-check',
                'object': 'source-desk', 'expected': pending, 'command': 'requestCheck', 'input': {}})
            self.assertEqual(requested['kind'], 'committed', requested)
            pending = requested['data']['root']
            work = manager._call(lambda: desk.compiler_work(pending, 'source-desk', ALICE['did'],
                None, receiver=manager._context(ALICE, 'private')[3]))
            self.assertIsNotNone(work)
            check_intent = work['intent']
            compiled = manager.check(ALICE, 'private', 'source-desk', check_intent, pending)
            self.assertEqual(compiled['kind'], 'committed', compiled)
            ready = compiled['data']['root']
            self.assertEqual(desk.candidate_state(ready)['status'], 'ready', desk.candidate_state(ready))
            with mock.patch.object(desk, 'bounded_compile', side_effect=AssertionError('recompiled')):
                self.assertEqual(manager.check(ALICE, 'private', 'source-desk', check_intent, pending), compiled)
            card = manager.encounter(ALICE, 'private', 'source-desk')
            release = next(action for action in card['actions'] if action['label'] == 'Release this checked variation')
            draft = manager.prepare(ALICE, 'private', {'card': card['card'], 'action': release['id'], 'fields': {}})
            adopted = manager.execute(ALICE, 'private', {'draft': draft['draft']})['reply']
            self.assertEqual(adopted['kind'], 'committed', adopted)
            self.assertEqual(manager.receipt(ALICE, 'private', draft['intent']), adopted)
            lantern = manager.inspect(ALICE, 'private', 'lantern')
            played = manager.turn(ALICE, 'private', {'op': 'invoke', 'object': 'lantern', 'intent': 'light',
                'expected': lantern, 'command': 'light', 'input': {}})
            self.assertEqual(played['kind'], 'committed', played)
            self.assertEqual(source_object.plain(source_object.state_data(played['data']['root'])), {'lit': True})


if __name__ == '__main__': unittest.main()
