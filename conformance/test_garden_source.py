#!/usr/bin/env python3
"""The ordinary source garden through real admission, encounters and recovery."""
import copy
from functools import lru_cache
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
adapter = module('garden_source_adapter', 'syntaxes/obend_object.py')
room = module('garden_source_room', 'scene/room.py')
affordances = module('garden_source_affordances', 'scripts/affordances.py')


def modules():
    return [{'name': name, 'source': (directory / (name + '.obend')).read_text()}
            for directory, name in [(ROOT / 'world/lib/prelude', 'Abi'),
                                    (ROOT / 'world/lib/prelude', 'Encounter'),
                                    (PACKAGE, 'Blooms'), (PACKAGE, 'Garden')]]


@lru_cache(maxsize=1)
def protocol():
    return adapter.lower_data_modules(modules())


def read(name):
    return json.loads((PACKAGE / name).read_bytes())


def data(wire):
    if wire['tag'] == 'record':
        return {field['name']: data(field['value']) for field in wire['fields']}
    if wire['tag'] == 'variant':
        return {'label': wire['label'], 'payload': data(wire['payload'])}
    if wire['tag'] == 'natural':
        return int(wire['value'])
    return wire['value']


def plantings(root):
    """Decode retained source data for assertions, never choose a transition."""
    beds = data(root['state']['model'])['beds']
    result = []
    while beds['label'] == 'cons':
        row = beds['payload']['row']
        while row['label'] == 'cons':
            result.append(row['payload']['head'])
            row = row['payload']['tail']
        beds = beds['payload']['tail']
    return result


class GardenSource(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / '.lake/build/bin/delvetalk-compiled').is_file(), 'prebuilt compiled host required')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db = Path(self.temporary.name) / 'world.json'
        self.serial = 0

    def call(self, request):
        return world.exchange(self.db, request, profile='compiled')

    def create(self):
        receipt = self.call({'op': 'create', 'object': 'garden', 'principal': 'operator',
            'intent': 'create-garden', 'protocol': protocol(), 'law': read('law.json')})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        return receipt['data']['root']

    def root(self):
        return self.call({'op': 'inspect', 'object': 'garden', 'principal': 'observer'})

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

    def test_two_gardeners_keep_multiple_blooms_and_reuse_an_attributed_cutting(self):
        self.create()
        self.assertIn('soil', self.card('image')['prose'])
        self.assertEqual([a['command'] for a in self.card()['actions']], ['plant'])
        first = self.invoke('moss', 'plant', {'seed': 'A bell for lost moths', 'colour': 'amber'})
        self.assertEqual(first['data']['result']['planter'], 'moss')
        self.invoke('iris', 'plant', {'seed': 'A staircase', 'colour': 'violet'})
        # A second waiting seed does not overwrite the first one or redirect its rain.
        self.invoke('iris', 'rain', {'id': 1, 'line': 'Rain remembers the names of stars.'})
        self.invoke('moss', 'rain', {'id': 2, 'line': 'Each drop leaves a step.'})
        original = plantings(self.root())
        self.assertEqual([b['planter'] for b in original], ['moss', 'iris'])
        self.assertEqual([b['rainmaker'] for b in original], ['iris', 'moss'])
        self.invoke('fern', 'cutting', {'id': 1, 'colour': 'silver'})
        self.assertEqual(plantings(self.root())[:2], original)
        child = plantings(self.root())[2]
        self.assertEqual((child['parent'], child['planter'], child['seed']), (1, 'fern', original[0]['seed']))
        self.assertIn('rain by iris', self.card('parent')['prose'])
        self.invoke('moss', 'rain', {'id': 3, 'line': 'The old bell learns a new song.'})
        self.invoke('iris', 'visit', {'id': 1})
        self.assertIn('AMBER', self.card('image')['prose'])
        self.assertEqual(self.card('rain')['prose'], original[0]['rain'])
        history = self.card('history')['prose']
        self.assertIn('1. A bell for lost moths', history)
        self.assertIn('2. A staircase', history)
        self.assertIn('3. A bell for lost moths', history)
        self.assertEqual(plantings(self.root())[:2], original)

    def test_authorship_bounds_and_missing_or_completed_targets_refuse_atomically(self):
        empty = self.create()
        for principal, fields in [('visitor', {'seed': 'Moon', 'colour': 'silver'}),
                ('builder', {'seed': 'Moon', 'colour': 'silver'}),
                ('moss', {'seed': True, 'colour': 'silver'}),
                ('moss', {'seed': '', 'colour': 'silver'}),
                ('moss', {'seed': 'x' * 81, 'colour': 'silver'}),
                ('moss', {'seed': 'Moon', 'colour': 'green'}),
                ('moss', {'seed': 'Moon', 'colour': 'silver', 'planter': 'iris'})]:
            self.invoke(principal, 'plant', fields, 'refused')
            self.assertEqual(self.root(), empty)
        self.invoke('moss', 'plant', {'seed': 'Moon', 'colour': 'silver'})
        planted = self.root()
        for who, command, fields in [('moss', 'rain', {'id': 1, 'line': 'Both voices'}),
                ('iris', 'rain', {'id': 1, 'line': 'x' * 241}),
                ('iris', 'rain', {'id': 2, 'line': 'No seed'}),
                ('iris', 'rain', {'id': 1, 'line': '', 'principal': 'fern'}),
                ('iris', 'cutting', {'id': 1, 'colour': 'amber'}),
                ('iris', 'visit', {'id': 999})]:
            self.invoke(who, command, fields, 'refused')
            self.assertEqual(self.root(), planted)
        self.invoke('iris', 'rain', {'id': 1, 'line': 'A real second voice.'}, 'refused', empty)
        self.invoke('iris', 'rain', {'id': 1, 'line': 'A real second voice.'})
        grown = self.root()
        self.invoke('fern', 'rain', {'id': 1, 'line': 'Replace history'}, 'refused')
        self.assertEqual(self.root(), grown)

    def test_current_law_exact_retry_and_late_transaction_rollback(self):
        self.create()
        original = self.request('moss', 'plant', {'seed': 'Moon', 'colour': 'silver'})
        receipt = self.call(original)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        planted = self.root()
        transaction = {'op': 'transaction', 'principal': 'iris', 'intent': 'rollback',
            'reads': {'garden': planted}, 'calls': [
                {'object': 'garden', 'command': 'rain', 'input': {'id': 1, 'line': 'Once'}},
                {'object': 'garden', 'command': 'rain', 'input': {'id': 1, 'line': 'Twice'}}]}
        self.assertEqual(self.call(transaction)['kind'], 'refused')
        self.assertEqual(self.root(), planted)
        law = read('law.json')
        law['invoke']['plant'].remove('moss')
        law['invoke']['rain'].remove('iris')
        self.assertEqual(self.call({'op': 'law', 'object': 'garden', 'principal': 'steward',
            'intent': 'revoke', 'expected': planted, 'law': law})['kind'], 'committed')
        self.invoke('iris', 'rain', {'id': 1, 'line': 'Revoked'}, 'refused')
        self.assertEqual(self.call(original), receipt)
        changed = copy.deepcopy(original)
        changed['input']['seed'] = 'Not the same attempt'
        self.assertEqual(self.call(changed)['data'], 'intent reused for different request')
        self.invoke('fern', 'rain', {'id': 1, 'line': 'Still permitted'})

    def test_forms_invite_exact_targets_and_retain_inspectable_source(self):
        self.create()
        view = room.inspect_object(self.root(), 'garden')
        plant = self.card()['actions'][0]
        self.assertEqual(next(f for f in plant['fields'] if f['name'] == 'seed')['example'], 'A bell for lost moths')
        request = affordances.request(view, plant['id'], 'moss', 'offered-plant',
                                      {'seed': 'A listening moon', 'colour': 'violet'})
        self.assertEqual(request['expected'], view['root'])
        self.assertEqual(self.call(request)['kind'], 'committed')
        waiting = room.inspect_object(self.root(), 'garden')
        rain = next(a for a in self.card()['actions'] if a['command'] == 'rain')
        selected = affordances.request(waiting, rain['id'], 'iris', 'offered-rain', {'line': 'The sky listens back.'})
        self.assertEqual(selected['input'], {'id': 1, 'line': 'The sky listens back.'})
        self.assertEqual(self.call(selected)['kind'], 'committed')
        self.assertEqual(self.root()['protocol']['sourcePackages']['resident']['modules'], modules())
        self.assertEqual(self.root()['protocol']['commands']['plant']['transition']['package']['entry'], 'plant')

    def test_collection_crosses_a_row_and_full_garden_keeps_history(self):
        self.create()
        for n in range(1, 33):
            self.invoke('moss' if n % 2 else 'iris', 'plant', {'seed': '🌙' * 78 + str(n), 'colour': 'amber'})
        before = self.root()
        self.assertEqual(len(plantings(before)), 32)
        self.assertIn('32. ', self.card('history')['prose'])
        self.assertNotIn('1. ', self.card('history')['prose'])
        self.invoke('moss', 'page', {'index': 4}, 'refused')
        self.invoke('fern', 'plant', {'seed': 'Overflow', 'colour': 'silver'}, 'refused')
        self.assertEqual(self.root(), before)
        self.invoke('iris', 'rain', {'id': 17, 'line': 'Rain reaches the next bed.'})
        self.invoke('moss', 'visit', {'id': 1})
        self.assertEqual(self.card('seed')['prose'], '🌙' * 78 + '1')
        self.assertIn('1. ', self.card('history')['prose'])
        self.assertNotIn('9. ', self.card('history')['prose'])
        self.assertEqual(len(plantings(self.root())), 32)
        self.assertNotIn('plant', [a['command'] for a in self.card()['actions']])
        self.assertEqual(plantings(self.root())[16]['rainmaker'], 'iris')

    def test_authored_examples(self):
        proposal = module('garden_examples_proposal', 'scripts/propose.py')
        examples = module('garden_examples_parser', 'syntaxes/spell_examples.py')
        outcomes = proposal.run_scenarios(protocol(), examples.parse((PACKAGE / 'Garden.examples').read_text()), profile='compiled')
        self.assertEqual([item['failures'] for item in outcomes], [[]])


if __name__ == '__main__':
    unittest.main()
