#!/usr/bin/env python3
"""Fresh resident custody, namespace-bound message bootstrap, and exact archives."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('resident_workspace_test', ROOT / 'scripts/workspace.py')
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)
b = workspace.bootstrap
world = b.desk_module.world


class ResidentWorkspaceTests(unittest.TestCase):
    def test_fresh_native_seed_restart_and_archive_match_file_semantics(self):
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {'message': 'Ready'},
                    'commands': {'write': {'require': [], 'set': {'message': ['input', 'message']},
                                           'result': ['state', 'message'], 'outbox': []}}}
        seeds = [{'id': 'entry', 'syntax': 'protocol-json@1', 'source': b.canonical(protocol),
                  'law': ['builder']}]
        options = dict(entry_objects=['entry'], principal='builder', profile='compiled',
                       world_id='urn:test:resident-workspace', messaging=True, pending_limit=16)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            native, reference = directory / 'native', directory / 'reference'
            seed = workspace.initialize(native, seeds, backend='resident', **options)
            file_seed = workspace.initialize(reference, seeds, backend='file', **options)
            self.assertEqual(seed['head'], file_seed['head'])
            self.assertEqual(seed['entries'], 2)
            database = native / 'world.json'
            self.assertFalse(database.exists(), 'resident workspace must not use a JSON world mirror')
            with world.resident_session(database, profile='compiled'):
                initial = world.snapshot(database)
                self.assertEqual(initial, world.snapshot(reference / 'world.json'))
                self.assertEqual(initial['receipts'][0]['request']['op'], 'messages-init')
                self.assertEqual(initial['messages']['lineage'], options['world_id'])
                root = b.inspect_view(native)['root']
                request = {'op': 'invoke', 'object': 'entry', 'principal': 'builder', 'intent': 'write-once',
                           'expected': root, 'command': 'write', 'input': {'message': 'After restart'}}
                reply = world.exchange(database, request, profile='compiled')
                self.assertEqual(reply['kind'], 'committed')
                self.assertEqual(world.retained_reply(database, request), reply)
            with world.resident_session(database, profile='compiled'):
                self.assertEqual(world.exchange(database, request, profile='compiled'), reply)
                final = world.snapshot(database)
                bundle = directory / 'bundle'
                evidence = b.export_bootstrap(native, bundle)
            restored = directory / 'restored'
            result = b.restore_bootstrap(bundle, restored, expected_genesis=evidence['genesis'],
                                        expected_head=evidence['head'])
            self.assertTrue(result['operatorEnrollmentReady'])
            self.assertEqual(world.snapshot(restored / 'world.json'), final)
            recovered_seed = b.loads((restored / 'seed.json').read_bytes())
            self.assertEqual(recovered_seed['head'], seed['head'])
            self.assertEqual(recovered_seed['entries'], 2)
            self.assertEqual(b.inspect_view(restored)['root']['state']['message'], 'After restart')

    def test_options_and_message_namespace_binding_refuse(self):
        with self.assertRaisesRegex(ValueError, 'unknown workspace backend'):
            workspace.initialize('unused', [], entry_objects=[], principal='builder', backend='implicit')
        with self.assertRaisesRegex(ValueError, 'messaging requires'):
            workspace.initialize('unused', [], entry_objects=[], principal='builder', messaging=True)
        metadata = {'format': 'delvetalk-workspace-v1', 'worldId': 'urn:test:one',
                    'messaging': {'lineage': 'urn:test:one', 'pendingLimit': 16}}
        record = {'request': {'op': 'messages-init', 'principal': 'builder',
                             'intent': 'workspace-messages:urn:test:other',
                             'lineage': 'urn:test:one', 'pendingLimit': 16},
                  'receipt': {'kind': 'committed'}}
        with self.assertRaisesRegex(ValueError, 'anchored first admission'):
            b.workspace_message_prefix(metadata, [record])


if __name__ == '__main__':
    unittest.main()
