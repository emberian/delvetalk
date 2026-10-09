"""Workspace seeds retain explicit source module bytes and sealed closure identity."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_store
import workspace
import world
from conformance.test_obend_data_object import SOURCE


class WorkspaceModuleSeeds(unittest.TestCase):
    def test_explicit_module_seed_keeps_exact_source_and_native_object(self):
        modules = [{'name': 'Shelf', 'source': SOURCE}]
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'world'
            seed = workspace.initialize(destination, [{'id': 'shelf', 'syntax': 'objective-bend-object',
                'modules': modules, 'law': {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker']}, 'reprogram': ['maker'], 'law': ['maker']}}], entry_objects=['shelf'], principal='maker')
            self.assertEqual(seed['entryObjects'], ['shelf'])
            raw = SOURCE.encode('utf-8')
            retained = source_store.reference(raw)
            self.assertEqual(source_store.read_bytes(destination / 'artifacts', retained), raw)
            lowerings = list((destination / 'artifacts/lowerings').glob('*.json'))
            self.assertEqual(len(lowerings), 1)
            artifact = json.loads(lowerings[0].read_text())
            material = artifact['source']
            self.assertEqual(material['modules'][0]['source'], SOURCE)
            self.assertEqual(material['manifest'], source_store.seal_modules([{'name': 'Shelf', 'sourceRef': retained}]))
            root = world.query(destination / 'world.json', {'op': 'inspect', 'object': 'shelf',
                'principal': 'maker'}, profile='compiled')
            self.assertEqual(root['protocol'], artifact['lowered'])
            self.assertEqual(root['version'], 0)

    def test_ambiguous_or_invalid_module_seed_refuses_before_custody(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'world'
            base = {'id': 'shelf', 'syntax': 'objective-bend-object',
                    'modules': [{'name': 'Shelf', 'source': SOURCE}], 'law': {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker']}, 'reprogram': ['maker'], 'law': ['maker']}}
            for invalid in ({**base, 'source': SOURCE.encode()},
                            {**base, 'syntax': 'protocol-json@1'},
                            {**base, 'modules': [{'name': 'Shelf', 'source': SOURCE, 'extra': True}]}):
                with self.assertRaises(ValueError):
                    workspace.initialize(destination, [invalid], entry_objects=['shelf'], principal='maker')
                self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
