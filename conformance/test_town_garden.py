#!/usr/bin/env python3
"""Legacy garden behavior remains replayable on the original world profile."""
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


world = module('garden_world', 'scripts/world.py')
room = module('garden_room', 'scene/room.py')
affordances = module('garden_affordances', 'scripts/affordances.py')


class TownGarden(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / '.lake/build/bin/delvetalk-world').is_file(), 'prebuilt host required')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'garden.json'
        self.serial = 0
        reply = self.call({'op': 'create', 'object': 'garden', 'principal': 'operator', 'intent': 'create',
            'protocol': json.loads((PACKAGE / 'legacy-v1.json').read_bytes()),
            'law': json.loads((PACKAGE / 'law.json').read_bytes())})
        self.assertEqual(reply['kind'], 'committed', reply)

    def call(self, request):
        return world.exchange(self.db, request)

    def root(self):
        return self.call({'op': 'inspect', 'object': 'garden', 'principal': 'observer'})

    def request(self, who, command, fields, root=None):
        self.serial += 1
        return {'op': 'invoke', 'object': 'garden', 'principal': who, 'intent': str(self.serial),
            'expected': self.root() if root is None else root, 'command': command, 'input': fields}

    def invoke(self, who, command, fields, kind='committed', root=None):
        reply = self.call(self.request(who, command, fields, root))
        self.assertEqual(reply['kind'], kind, reply)
        return reply

    def card(self, panel='main'):
        return affordances.card(room.inspect_object(self.root(), 'garden', panel=panel))

    def plant(self, colour='amber'):
        return self.invoke('moss', 'plant', {'seed': 'A bell for lost moths', 'colour': colour})

    def rain(self):
        return self.invoke('iris', 'rain', {'line': 'Rain carries the names of forgotten stars.'})

    def test_two_voices_change_image_and_can_start_next_season(self):
        empty_image = self.card('image')['prose']
        self.assertIn('soil', empty_image)
        self.assertEqual([a['command'] for a in self.card()['actions']], ['plant'])
        self.plant()
        self.assertEqual(self.card()['title'], 'A bell for lost moths')
        self.assertIn('Someone other than its planter', self.card()['prose'])
        self.assertEqual(self.card('planter')['prose'], 'moss')
        self.assertEqual([a['command'] for a in self.card()['actions']], ['rain'])
        self.rain()
        self.assertEqual(self.card()['prose'], 'Rain carries the names of forgotten stars.')
        self.assertIn('AMBER', self.card('image')['prose'])
        self.assertNotEqual(self.card('image')['prose'], empty_image)
        for panel, value in [('seed', 'A bell for lost moths'), ('planter', 'moss'),
                             ('rain', 'Rain carries the names of forgotten stars.'),
                             ('rainmaker', 'iris'), ('colour', 'amber')]:
            self.assertEqual(self.card(panel)['prose'], value)
        completed = self.root()['state']['lastCompleted']
        self.assertEqual(completed['planter'], 'moss')
        self.assertEqual(completed['rainmaker'], 'iris')
        self.assertEqual([a['command'] for a in self.card()['actions']], ['plant'])
        self.invoke('fern', 'plant', {'seed': 'A quiet blue staircase', 'colour': 'violet'})
        self.assertEqual(self.root()['state']['lastCompleted'], completed)
        self.assertEqual(self.root()['state']['rain'], '')
        self.invoke('moss', 'rain', {'line': 'Each drop leaves one step behind.'})
        self.assertIn('VIOLET', self.card('image')['prose'])
        self.assertEqual(self.root()['state']['lastCompleted']['planter'], 'fern')

    def test_roles_values_staleness_and_retained_identity(self):
        self.invoke('visitor', 'plant', {'seed': 'Not enrolled', 'colour': 'amber'}, 'refused')
        self.invoke('builder', 'plant', {'seed': 'Management is not play', 'colour': 'amber'}, 'refused')
        for fields in [{'seed': '', 'colour': 'amber'}, {'seed': True, 'colour': 'amber'},
                       {'seed': 'Valid seed', 'colour': 'green'}]:
            self.invoke('moss', 'plant', fields, 'refused')
        empty = self.root()
        request = self.request('moss', 'plant', {'seed': 'A bell for lost moths', 'colour': 'silver',
                                               'planter': 'iris'})
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(self.root()['state']['planter'], 'moss')
        self.invoke('moss', 'rain', {'line': 'Impersonation', 'principal': 'iris'}, 'refused')
        self.invoke('iris', 'rain', {'line': 'Stale soil'}, 'refused', empty)
        self.invoke('iris', 'plant', {'seed': 'Overwrite', 'colour': 'amber'}, 'refused')
        self.rain()
        self.assertIn('SILVER', self.card('image')['prose'])
        self.assertEqual(self.call(request), receipt)
        collision = copy.deepcopy(request)
        collision['input']['seed'] = 'Different seed'
        self.assertEqual(self.call(collision)['data'], 'intent reused for different request')

    def test_typed_action_uses_exact_observation_and_current_law(self):
        view = room.inspect_object(self.root(), 'garden')
        card = affordances.card(view)
        request = affordances.request(view, card['actions'][0]['id'], 'moss', 'typed-plant',
            {'seed': 'An acorn full of doors', 'colour': 'violet'})
        self.assertEqual(request['expected'], view['root'])
        with self.assertRaises(ValueError):
            affordances.request(view, card['actions'][0]['id'], 'moss', 'long',
                {'seed': 'x' * 81, 'colour': 'violet'})
        self.assertEqual(self.call(request)['kind'], 'committed')
        before = self.root()
        updated = json.loads((PACKAGE / 'law.json').read_bytes())
        updated['invoke'] = {'plant': ['moss', 'fern'], 'rain': ['moss', 'fern']}
        self.assertEqual(self.call({'op': 'law', 'object': 'garden', 'principal': 'steward', 'intent': 'revoke',
            'expected': before, 'law': updated})['kind'], 'committed')
        self.invoke('iris', 'rain', {'line': 'Revoked rain'}, 'refused')
        self.invoke('fern', 'rain', {'line': 'A door learns to listen.'})

    def test_builder_can_replace_view_without_rewriting_contributions(self):
        self.plant()
        self.rain()
        before = self.root()
        proposal = copy.deepcopy(before['protocol'])
        # A new authored view is an ordinary program replacement under preserved law.
        proposal['viewProgram']['term'] = ['lam', ['lam', ['record', [
            ['title', ['label', 'The garden has a new sign']],
            ['prose', ['get', ['bound', 1], 'rain']], ['actions', ['record', []]]]]]]
        request = {'op': 'reprogram', 'object': 'garden', 'principal': 'moss', 'intent': 'not-builder',
            'expected': before, 'protocol': proposal, 'state': before['state']}
        self.assertEqual(self.call(request)['kind'], 'refused')
        request.update(principal='builder', intent='new-sign')
        self.assertEqual(self.call(request)['kind'], 'committed')
        self.assertEqual(self.root()['state'], before['state'])
        self.assertEqual(self.root()['law'], before['law'])
        self.assertEqual(self.card()['title'], 'The garden has a new sign')
        self.assertEqual(self.card()['prose'], before['state']['rain'])


if __name__ == '__main__':
    unittest.main()
