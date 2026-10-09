"""The default workshop retains typed source seeds through replay and use."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import workshop
import portal
import source_object


class WorkshopInitializer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='workshop-entry-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        # An explicitly retained CLI fixture lets acceptance preserve costly
        # successful admissions while refuting later export/encounter checks.
        retained = os.environ.get('DELVETALK_WORKSHOP_FIXTURE')
        cls.home = Path(retained) if retained else cls.base / 'workshop'
        if retained is None:
            subprocess.run([sys.executable, str(ROOT / 'scripts/workshop.py'), str(cls.home),
                '--world-id', 'urn:test:source-workshop-initializer'], check=True, capture_output=True)
        cls.seed = workshop.b.loads((cls.home / 'seed.json').read_bytes())
        cls.roots = workshop.b.desk_module.world.snapshot(cls.home / 'world.json')['objects']

    def test_configured_source_graph_retains_descriptions_roles_and_original_table(self):
        self.assertEqual(len(self.roots), 10)
        for identity, root in self.roots.items():
            self.assertIn('sourcePackages', root['protocol'], identity)
            self.assertNotIn('roomArtifact', root['protocol'])
        def model(identity):
            return source_object.plain(source_object.state_data(self.roots[identity]))
        self.assertEqual(model('places/porch')['title'], 'The workshop porch')
        self.assertEqual(model('entities/moss')['title'], 'moss')
        self.assertTrue(model('commons')['valid'])
        self.assertEqual(workshop.commons.locations(self.roots['commons']), {'moss': '', 'iris': ''})
        self.assertEqual(model('factory:objects')['participants']['variant'], 'array')
        self.assertEqual(model('factory:desks')['base']['compiler'], 'compiler')
        table = model('table:automatafl')
        self.assertEqual((table['width'], table['height']), (11, 11))
        self.assertEqual(table['seats'], {'north': 'moss', 'south': 'iris'})
        self.assertEqual(table['round'], 0)
        self.assertEqual(self.roots['table:automatafl']['law']['reprogram'], [])
        self.assertEqual(self.roots['factory:objects']['law']['view']['main'], 'public')
        artifact_paths = list((self.home / 'artifacts/lowerings').glob('*.json'))
        artifacts = [workshop.b.loads(p.read_bytes()) for p in artifact_paths]
        self.assertTrue(any('configuration' in item for item in artifacts))
        self.assertTrue(all(item['syntax'] == 'objective-bend-object' for item in artifacts))

    def test_source_or_schema_substitution_refuses_native_seed_resolution(self):
        root = deepcopy(self.roots['places/porch'])
        original = deepcopy(root['protocol']['initial'])
        modules = root['protocol']['sourcePackages']['resident']['modules']
        modules[-1]['source'] += '\n# A changed physical source is a different retained schema.\n'
        with self.assertRaises((ValueError, RuntimeError)):
            source_object.state_data({'protocol': root['protocol'], 'state': original})
        refused = workshop.b.desk_module.world.exchange(self.base / 'changed-source.json',
            {'op': 'create', 'object': 'changed', 'principal': 'author', 'intent': 'source-substitution',
             'protocol': root['protocol'], 'law': self.roots['places/porch']['law']}, profile='compiled')
        self.assertEqual(refused['kind'], 'refused', refused)
        root = deepcopy(self.roots['places/porch'])
        root['state']['model']['schema']['packetSha256'] = '0' * 64
        with self.assertRaises((ValueError, RuntimeError)):
            source_object.state_data(root)
        root['protocol']['initial'] = root['state']
        refused = workshop.b.desk_module.world.exchange(self.base / 'changed-schema.json',
            {'op': 'create', 'object': 'changed', 'principal': 'author', 'intent': 'schema-substitution',
             'protocol': root['protocol'], 'law': root['law']}, profile='compiled')
        self.assertEqual(refused['kind'], 'refused', refused)

    def test_configured_state_metadata_matches_operative_lowering(self):
        artifact = next(workshop.b.loads(path.read_bytes()) for path in
            (self.home / 'artifacts/lowerings').glob('*.json')
            if 'configuration' in workshop.b.loads(path.read_bytes()))
        artifact['configuration']['initial'] = {'model': {}}
        with self.assertRaisesRegex(ValueError, 'initial differs'):
            workshop.b.history.lowered_protocol(artifact, self.home / 'seed-history')

    def test_original_lowering_is_retained_transitively_and_source_bound(self):
        artifacts = [workshop.b.loads(path.read_bytes()) for path in
            (self.home / 'artifacts/lowerings').glob('*.json')]
        configured = [item for item in artifacts if 'configuration' in item]
        bundle = self.home / 'seed-history'
        for item in configured:
            sha = item['configuration']['sourceLowering']
            self.assertIn(sha, workshop.b.history.declared_files(item).values())
            original = workshop.b.history.loads(workshop.b.history.read_blob(bundle, sha).read_bytes())
            self.assertEqual(workshop.b.history.digest(original), sha)
            self.assertNotIn('configuration', original)
            self.assertEqual(original['source'], item['source'])
            self.assertEqual(workshop.b.history.lowered_protocol(item, bundle), item['lowered'])
        changed = deepcopy(configured[0])
        changed['configuration']['sourceLowering'] = '0' * 64
        with self.assertRaises((ValueError, FileNotFoundError)):
            workshop.b.history.lowered_protocol(changed, bundle)
        alternate = next(item for item in configured if item['source'] != configured[0]['source'])
        changed = deepcopy(configured[0])
        changed['configuration']['sourceLowering'] = alternate['configuration']['sourceLowering']
        with self.assertRaisesRegex(ValueError, 'different source'):
            workshop.b.history.lowered_protocol(changed, bundle)

    def test_export_fresh_restore_and_offered_factory_action_preserve_source_state(self):
        bundle = self.base / 'export'
        evidence = workshop.b.export_bootstrap(self.home, bundle)
        restored = self.base / 'restored'
        workshop.b.restore_bootstrap(bundle, restored, expected_genesis=evidence['genesis'], expected_head=evidence['head'])
        roots = workshop.b.desk_module.world.snapshot(restored / 'world.json')['objects']
        self.assertEqual(roots, self.roots)
        client = portal.Portal(restored, principal='moss', allow_local_actions=True)
        card = client.object('factory:objects')
        action = next(item for item in card['actions'] if item['label'] == 'Make an object')
        draft = client.prepare({'card': card['card'], 'action': action['id'], 'fields': {'name': 'restored-lantern'}})
        receipt = client.execute({'draft': draft['draft']})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(client.execute({'draft': draft['draft']}), receipt)
        child = workshop.b.desk_module.world.query(restored / 'world.json', {'op': 'inspect',
            'object': 'factory:objects/restored-lantern', 'principal': 'moss'}, profile='compiled')
        self.assertIn('sourcePackages', child['protocol'])
        self.assertEqual(child['law']['invoke']['write'], ['moss', 'iris'])
        self.assertEqual(child['law']['reprogram'], ['moss', 'iris'])
        self.assertEqual(child['law']['law'], ['moss', 'iris'])
        self.assertEqual(source_object.plain(source_object.state_data(roots['table:automatafl']))['width'], 11)


if __name__ == '__main__':
    unittest.main()
