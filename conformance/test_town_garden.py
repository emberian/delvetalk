#!/usr/bin/env python3
"""An independently authored garden variation reuses the retained planting behavior."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('garden_reuse_fixture', ROOT / 'conformance/test_garden_source.py')
garden = importlib.util.module_from_spec(spec)
spec.loader.exec_module(garden)


class TownGarden(unittest.TestCase):
    def test_ordinary_source_variation_preserves_contributions_and_current_authority(self):
        fixture = garden.GardenSource()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.create()
        fixture.invoke('moss', 'plant', {'seed': 'A listening moon', 'colour': 'silver'})
        fixture.invoke('iris', 'rain', {'id': 1, 'line': 'The sky listens back.'})
        before = fixture.root()
        successor = garden.adapter.lower_data_modules(garden.modules() + [
            {'name': 'EveningGarden', 'source': (garden.PACKAGE / 'EveningGarden.obend').read_text()}])
        request = {'op': 'reprogram', 'object': 'garden', 'principal': 'moss', 'intent': 'not-builder',
                   'expected': before, 'protocol': successor, 'state': before['state']}
        self.assertEqual(fixture.call(request)['kind'], 'refused')
        request.update(principal='builder', intent='new-sign')
        self.assertEqual(fixture.call(request)['kind'], 'committed')
        self.assertEqual(fixture.root()['state'], before['state'])
        self.assertEqual(fixture.root()['law'], before['law'])
        self.assertEqual(fixture.card()['title'], 'The Night Garden · a sign made together')
        self.assertIn('The sky listens back.', fixture.card()['prose'])
        fixture.invoke('fern', 'cutting', {'id': 1, 'colour': 'amber'})
        self.assertEqual(garden.plantings(fixture.root())[0], garden.plantings(before)[0])
        self.assertEqual(garden.plantings(fixture.root())[1]['parent'], 1)


if __name__ == '__main__':
    unittest.main()
