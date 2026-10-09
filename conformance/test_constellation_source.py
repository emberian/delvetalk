"""Source constellation: real receiving admission and offered shared encounter."""
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'protocols/constellation-commons'

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

world = module('constellation_world', 'scripts/world.py')
adapter = module('constellation_adapter', 'syntaxes/obend_object.py')
room = module('constellation_room', 'scene/room.py')
affordances = module('constellation_affordances', 'scripts/affordances.py')

def modules():
    return [{'name': name, 'source': (directory / (name + '.obend')).read_text()}
            for directory, name in [(ROOT / 'world/lib/prelude', 'Abi'),
                                    (ROOT / 'world/lib/prelude', 'List'),
                                    (ROOT / 'world/lib/prelude', 'Encounter'),
                                    (PACKAGE, 'Stars'), (PACKAGE, 'Constellation')]]

@lru_cache(maxsize=1)
def protocol():
    return adapter.lower_data_modules(modules())

def law():
    return json.loads((PACKAGE / 'law.json').read_text())

class ConstellationSource(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'world.json'
        self.serial = 0
        receipt = self.call({'op': 'create', 'object': 'sky', 'principal': 'operator',
            'intent': 'create', 'protocol': protocol(), 'law': law()})
        self.assertEqual(receipt['kind'], 'committed', receipt)

    def call(self, request):
        return world.exchange(self.db, request, profile='compiled')

    def root(self):
        return self.call({'op': 'inspect', 'object': 'sky', 'principal': 'observer'})

    def request(self, who, command, fields, root=None):
        self.serial += 1
        return {'op': 'invoke', 'object': 'sky', 'principal': who, 'intent': str(self.serial),
            'expected': self.root() if root is None else root, 'command': command, 'input': fields}

    def invoke(self, who, command, fields, kind='committed', root=None):
        receipt = self.call(self.request(who, command, fields, root))
        self.assertEqual(receipt['kind'], kind, receipt)
        return receipt

    def card(self, panel='main'):
        return affordances.card(room.inspect_object(self.root(), 'sky', panel=panel))

    def test_two_authors_contribute_revisit_and_revise_through_offered_actions(self):
        view = room.inspect_object(self.root(), 'sky')
        action = self.card()['actions'][0]
        request = affordances.request(view, action['id'], 'iris', 'first-light',
            {'image': 'A brass feather', 'line': 'The repaired bird remembers the sky.'})
        first = self.call(request)
        self.assertEqual(first['kind'], 'committed', first)
        self.assertEqual(first['data']['result']['author'], 'iris')
        self.invoke('moss', 'contribute', {'image': 'A listening moon', 'line': 'Silence gathers under its wing.'})
        self.invoke('iris', 'visit', {'id': 1})
        selected = self.card('selected')['prose']
        self.assertIn('brass feather', selected)
        offered = next(a for a in self.card()['actions'] if a['command'] == 'revise')
        observed = room.inspect_object(self.root(), 'sky')
        revised = affordances.request(observed, offered['id'], 'iris', 'revised-light',
            {'image': 'A silver feather', 'line': 'The repaired bird lends the moon a wing.'})
        self.assertEqual(revised['input']['id'], 1)
        receipt = self.call(revised)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['result']['revision'], 2)
        self.invoke('moss', 'revise', {'id': 2, 'image': 'A listening moon', 'line': 'Both birds rest here.'})
        sky = self.card('sky')['prose']
        for text in ['silver feather', 'iris', 'listening moon', 'moss', 'Both birds rest here.']:
            self.assertIn(text, sky)
        self.assertEqual(self.root()['protocol']['sourcePackages']['resident']['modules'], modules())
        self.assertEqual(self.call(request), first)

    def test_unauthorized_edits_forged_authors_invalid_words_and_stale_roots_refuse(self):
        empty = self.root()
        self.invoke('iris', 'contribute', {'image': 'Moon', 'line': 'A place for each voice.'})
        before = self.root()
        attempts = [('moss', 'revise', {'id': 1, 'image': 'Stolen', 'line': 'Overwrite'}),
            ('visitor', 'contribute', {'image': 'Moon', 'line': 'No grant'}),
            ('iris', 'contribute', {'image': 'Moon', 'line': 'Forged', 'author': 'moss'}),
            ('iris', 'revise', {'id': 999, 'image': 'Absent', 'line': 'No light'}),
            ('iris', 'contribute', {'image': '', 'line': 'Empty'}),
            ('iris', 'contribute', {'image': 'x' * 81, 'line': 'Long'}),
            ('iris', 'revise', {'id': 1, 'image': 'Moon', 'line': 'x' * 241}),
            ('iris', 'contribute', {'image': True, 'line': 'Wrong type'})]
        for who, command, fields in attempts:
            self.invoke(who, command, fields, 'refused')
            self.assertEqual(self.root(), before)
        self.invoke('iris', 'revise', {'id': 1, 'image': 'Moon', 'line': 'Stale'}, 'refused', empty)
        self.assertEqual(self.root(), before)
        self.invoke('moss', 'contribute', {'image': 'Cloud', 'line': 'Another voice.'})
        before = self.root()
        transaction = {'op': 'transaction', 'principal': 'iris', 'intent': 'same-caller',
            'reads': {'sky': before}, 'calls': [
                {'object': 'sky', 'command': 'revise', 'input': {'id': 1, 'image': 'New moon', 'line': 'Allowed first edit'}},
                {'object': 'sky', 'command': 'revise', 'input': {'id': 2, 'image': 'Stolen cloud', 'line': 'Cannot become moss'}}]}
        self.assertEqual(self.call(transaction)['kind'], 'refused')
        self.assertEqual(self.root(), before)

    def test_full_sky_still_allows_own_revision_and_current_law_applies(self):
        for n in range(12):
            self.invoke('iris' if n % 2 == 0 else 'moss', 'contribute',
                {'image': 'Light ' + str(n + 1), 'line': 'A small shared sky.'})
        full = self.root()
        self.invoke('fern', 'contribute', {'image': 'Overflow', 'line': 'Thirteenth'}, 'refused')
        self.assertEqual(self.root(), full)
        self.assertNotIn('contribute', [a['command'] for a in self.card()['actions']])
        self.invoke('iris', 'revise', {'id': 1, 'image': 'First light', 'line': 'Room to change.'})
        changed_law = law()
        changed_law['invoke']['revise'].remove('iris')
        receipt = self.call({'op': 'law', 'object': 'sky', 'principal': 'steward',
            'intent': 'current-policy', 'expected': self.root(), 'law': changed_law})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        before = self.root()
        self.invoke('iris', 'revise', {'id': 1, 'image': 'First light', 'line': 'Revoked'}, 'refused')
        self.assertEqual(self.root(), before)
        self.assertIn('12. Light 12', self.card('sky')['prose'])

if __name__ == '__main__':
    unittest.main()
