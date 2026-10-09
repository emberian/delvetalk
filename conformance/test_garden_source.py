#!/usr/bin/env python3
"""Stateful garden source through actual compiled admission, views and recovery."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'protocols/town-garden'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


world = module('garden_source_world', 'scripts/world.py')
source_bundle = module('garden_source_bundle', 'syntaxes/source_bundle.py')
room = module('garden_source_room', 'scene/room.py')
affordances = module('garden_source_affordances', 'scripts/affordances.py')


def read(name):
    return json.loads((PACKAGE / name).read_bytes())


def protocol():
    return source_bundle.load(PACKAGE / 'binding.json', [('Garden', PACKAGE / 'Garden.obend')])


class GardenSource(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / '.lake/build/bin/delvetalk-compiled').is_file(), 'prebuilt compiled host required')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db = Path(self.temporary.name) / 'world.json'
        self.serial = 0

    def call(self, request):
        return world.exchange(self.db, request, profile='compiled')

    def create(self, candidate=None, identity='garden', law=None):
        receipt = self.call({'op': 'create', 'object': identity, 'principal': 'operator',
            'intent': 'create-' + identity, 'protocol': protocol() if candidate is None else candidate,
            'law': read('law.json') if law is None else law})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        return receipt['data']['root']

    def root(self, identity='garden'):
        return self.call({'op': 'inspect', 'object': identity, 'principal': 'observer'})

    def request(self, principal, command, fields, root=None):
        self.serial += 1
        return {'op': 'invoke', 'object': 'garden', 'principal': principal, 'intent': str(self.serial),
                'expected': self.root() if root is None else root, 'command': command, 'input': fields}

    def invoke(self, principal, command, fields, kind='committed', root=None):
        receipt = self.call(self.request(principal, command, fields, root))
        self.assertEqual(receipt['kind'], kind, receipt)
        return receipt

    def card(self, panel='main'):
        return affordances.card(room.inspect_object(self.root(), 'garden', panel=panel))

    def source_value(self, entry, arguments):
        self.serial += 1
        identity = 'source-' + str(self.serial)
        package = protocol()['viewProgram']['package'] | {'entry': entry}
        candidate = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'run': {
            'require': [], 'set': {}, 'outbox': [],
            'result': ['package', package, [['literal', value] for value in arguments]]}}}
        root = self.create(candidate, identity, ['operator'])
        receipt = self.call({'op': 'invoke', 'object': identity, 'principal': 'operator',
            'intent': 'run-' + identity, 'expected': root, 'command': 'run', 'input': {}})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        return receipt['data']['result']

    def test_source_binding_and_explicit_migration_exports(self):
        self.assertEqual(protocol(), read('protocol.json'))
        self.assertEqual(protocol()['initial'], read('migration.json'))
        example = read('migration-example.json')
        self.assertEqual(self.source_value(example['entry'], [example['before']]), example['after'])
        empty = read('legacy-v1.json')['initial']
        self.assertEqual(self.source_value('migrateEmpty', [empty]), protocol()['initial'])
        # No Python state transition: source produces both accepted and refused decisions.
        host = protocol()['initial']
        context = {'object': 'garden', 'principal': 'moss'}
        result = self.source_value('plantTurn', [host, {'seed': 'Moon', 'colour': 'amber'}, context])
        self.assertTrue(result['accepted'])
        self.assertEqual(result['state']['value']['planter'], 'moss')
        refused = self.source_value('rainTurn', [result['state'], {'line': 'My own rain'}, context])
        self.assertFalse(refused['accepted'])
        self.assertTrue(refused['reason'])

    def test_actual_admission_changes_state_and_source_view(self):
        self.create()
        self.assertIn('soil', self.card('image')['prose'])
        self.assertEqual([a['command'] for a in self.card()['actions']], ['plant'])
        planted = self.invoke('moss', 'plant', {'seed': 'A bell for lost moths', 'colour': 'amber'})
        self.assertEqual(planted['data']['result'], {'by': 'moss', 'seed': 'A bell for lost moths', 'colour': 'amber'})
        self.assertEqual(planted['data']['outbox'], [])
        self.assertEqual(self.card('planter')['prose'], 'moss')
        self.assertEqual([a['command'] for a in self.card()['actions']], ['rain'])
        self.invoke('iris', 'rain', {'line': 'Rain remembers the names of stars.'})
        self.assertIn('AMBER', self.card('image')['prose'])
        self.assertEqual(self.card('rainmaker')['prose'], 'iris')
        before = self.root()['state']['value']['lastCompleted']
        self.invoke('fern', 'plant', {'seed': 'A staircase', 'colour': 'violet'})
        current = self.root()['state']['value']
        self.assertTrue(current['hasCompleted'])
        self.assertEqual(current['lastCompleted'], before)
        self.assertEqual(current['rain'], '')
        self.invoke('moss', 'rain', {'line': 'Each drop leaves a step.'})
        self.assertIn('VIOLET', self.card('image')['prose'])
        self.assertEqual(self.root()['state']['value']['lastCompleted']['planter'], 'fern')

    def test_invalid_input_actor_phase_and_exact_roots(self):
        empty = self.create()
        for principal, fields in [('visitor', {'seed': 'Moon', 'colour': 'silver'}),
                ('builder', {'seed': 'Moon', 'colour': 'silver'}),
                ('moss', {'seed': True, 'colour': 'silver'}),
                ('moss', {'seed': '', 'colour': 'silver'}),
                ('moss', {'seed': 'Moon', 'colour': 'green'})]:
            self.invoke(principal, 'plant', fields, 'refused')
            self.assertEqual(self.root(), empty)
        self.invoke('moss', 'plant', {'seed': 'Moon', 'colour': 'silver'})
        planted = self.root()
        refusal = self.invoke('moss', 'rain', {'line': 'Both voices'}, 'refused')
        self.assertIn('different participant', refusal['data'])
        self.invoke('moss', 'rain', {'line': 'Forged voice', 'principal': 'iris'}, 'refused')
        self.invoke('iris', 'rain', {'line': False}, 'refused')
        self.invoke('iris', 'rain', {'line': ''}, 'refused')
        self.invoke('iris', 'rain', {'line': 'Old card'}, 'refused', empty)
        self.invoke('iris', 'plant', {'seed': 'Overwrite', 'colour': 'silver'}, 'refused')
        self.assertEqual(self.root(), planted)

    def test_current_law_replay_and_late_transaction_rollback(self):
        self.create()
        original = self.request('moss', 'plant', {'seed': 'Moon', 'colour': 'silver'})
        receipt = self.call(original)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        planted = self.root()
        transaction = {'op': 'transaction', 'principal': 'iris', 'intent': 'rollback',
            'reads': {'garden': planted}, 'calls': [
                {'object': 'garden', 'command': 'rain', 'input': {'line': 'Once'}},
                {'object': 'garden', 'command': 'rain', 'input': {'line': 'Twice'}}]}
        self.assertEqual(self.call(transaction)['kind'], 'refused')
        self.assertEqual(self.root(), planted)
        law = read('law.json')
        law['invoke']['plant'].remove('moss')
        law['invoke']['rain'].remove('iris')
        self.assertEqual(self.call({'op': 'law', 'object': 'garden', 'principal': 'steward',
            'intent': 'revoke', 'expected': planted, 'law': law})['kind'], 'committed')
        self.invoke('iris', 'rain', {'line': 'Revoked'}, 'refused')
        self.assertEqual(self.call(original), receipt)  # fresh native process on every exchange
        changed = copy.deepcopy(original)
        changed['input']['seed'] = 'Not the same attempt'
        self.assertEqual(self.call(changed)['data'], 'intent reused for different request')
        self.invoke('fern', 'rain', {'line': 'Still permitted'})

    def test_migrate_completed_legacy_history_without_replaying_old_code(self):
        self.create(read('legacy-v1.json'))
        original = self.request('moss', 'plant', {'seed': 'Moon', 'colour': 'amber'})
        receipt = self.call(original)
        self.assertEqual(receipt['kind'], 'committed')
        self.invoke('iris', 'rain', {'line': 'A retained offering'})
        before = self.root()
        migrated = self.source_value('migrateComplete', [before['state']])
        request = {'op': 'reprogram', 'object': 'garden', 'principal': 'builder', 'intent': 'source-garden',
            'expected': before, 'protocol': protocol(), 'state': migrated}
        self.assertEqual(self.call(request)['kind'], 'committed')
        after = self.root()
        self.assertEqual(after['law'], before['law'])
        self.assertEqual(after['state']['value']['lastCompleted'], before['state']['lastCompleted'])
        self.assertEqual(self.call(original), receipt)
        self.assertEqual(self.root(), after)
        self.assertEqual(self.card('rain')['prose'], 'A retained offering')
        self.invoke('fern', 'plant', {'seed': 'Next season', 'colour': 'silver'})
        self.assertEqual(self.root()['state']['value']['lastCompleted'], before['state']['lastCompleted'])


if __name__ == '__main__':
    unittest.main()
