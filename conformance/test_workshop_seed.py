"""New shared creations remain usable after one builder installs a new program."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import workshop
import affordances


class SharedSeed(unittest.TestCase):
    def test_create_reprogram_use_and_explicit_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'world'
            workshop.initialize(directory)
            desk = workshop.b.desk_module.Desk(directory / 'world.json', directory / 'artifacts', profile='compiled')
            view = workshop.b.inspect_view(directory, 'factory:objects')
            card = affordances.card(view)
            create = affordances.request(view, card['actions'][0]['id'], 'moss', 'create-lantern', {'name': 'lantern'})
            made = desk.exchange(create)
            self.assertEqual(made['kind'], 'committed', made)
            child = affordances.allocated_refs(made)[0]['object']
            protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
                'light': {'require': [], 'set': {'lit': ['literal', True]},
                          'result': ['literal', 'The moth wakes.'], 'outbox': []}}}
            installed = desk.exchange({'op': 'reprogram', 'object': child, 'principal': 'iris',
                'intent': 'install-lantern', 'expected': desk.inspect(child), 'protocol': protocol,
                'state': {'lit': False}})
            self.assertEqual(installed['kind'], 'committed', installed)
            before = desk.inspect(child)
            unauthorized = desk.exchange({'op': 'invoke', 'object': child, 'principal': 'stranger',
                'intent': 'uninvited', 'expected': before, 'command': 'light', 'input': {}})
            self.assertEqual(unauthorized['kind'], 'refused')
            self.assertEqual(desk.inspect(child), before)
            used = desk.exchange({'op': 'invoke', 'object': child, 'principal': 'moss',
                'intent': 'use-lantern', 'expected': before, 'command': 'light', 'input': {}})
            self.assertEqual(used['kind'], 'committed', used)
            self.assertEqual(used['data']['result'], 'The moth wakes.')
            self.assertTrue(desk.inspect(child)['state']['lit'])
            # The independent game table never inherits child-builder management.
            table = desk.inspect('table:automatafl')
            refused = desk.exchange({'op': 'law', 'object': 'table:automatafl', 'principal': 'moss',
                'intent': 'change-game-rules', 'expected': table, 'law': ['moss']})
            self.assertEqual(refused['kind'], 'refused')
            self.assertEqual(desk.inspect('table:automatafl'), table)


if __name__ == '__main__':
    unittest.main()
