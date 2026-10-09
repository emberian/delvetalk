#!/usr/bin/env python3
"""Contextual source menus through real Lean, portal cards and local town custody.

Publication fixtures exercise exact binding, not remote PDS authentication.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import history
import portal
import propose
import town_cards as town

spec = importlib.util.spec_from_file_location('menu_projection', ROOT / 'scene/projection.py')
projection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(projection)

SOURCE = '''edition ObjectiveBend 1
record State:
  lit: Bool
record Action:
  visible: Bool
  text: String
  command: String
  input: {}
record Actions:
  light: Action
  douse: Action
record View:
  title: String
  prose: String
  actions: Actions
def view(state: State, panel: String) -> View:
  {title: "A small lantern", prose: if state.lit then "A lantern glows." else "The room is dark.", actions: {light: {visible: if state.lit then false else true, text: "Light the lantern", command: "light", input: {}}, douse: {visible: state.lit, text: "Douse the lantern", command: "douse", input: {}}}}
'''
ISSUER, ACTOR = ['did:plc:' + c * 24 for c in 'ab']


class SourceMenus(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.db = self.directory / 'world.json'
        self.runtime = history.runtime('compiled')
        self.protocol = {'profile': 'delvetalk-local-v1', 'initial': {'lit': False},
            'commands': {name: {'require': [[['state', 'lit'], ['literal', before]]],
                'set': {'lit': ['literal', after]}, 'result': ['literal', name], 'outbox': []}
                for name, before, after in [('light', False, True), ('douse', True, False)]},
            'viewProgram': {'profile': projection.MENU_PROFILE,
                'package': {'modules': [{'name': 'Lantern', 'source': SOURCE}], 'entry': 'view'}}}
        made = self.call({'op': 'create', 'object': 'lantern', 'principal': 'maker',
            'intent': 'create', 'protocol': self.protocol, 'law': [ACTOR]})
        self.assertEqual(made['kind'], 'committed', made)
        self.root = made['data']['root']

    def call(self, request):
        return projection.world.exchange(self.db, request, profile='compiled')

    def project(self, root=None):
        return projection.project(root or self.root, 'lantern', expected_runtime=self.runtime)

    def test_visible_menu_and_actual_guards_are_separate(self):
        original = self.db.read_bytes()
        view = self.project()
        self.assertEqual(self.db.read_bytes(), original)
        self.assertEqual(set(view['rawData']['actions']), {'light', 'douse'})
        self.assertEqual(set(view['data']['actions']), {'light'})
        self.assertNotIn('visible', view['data']['actions']['light'])
        self.assertFalse(view['rawData']['actions']['douse']['visible'])
        self.assertEqual(view['source']['package']['modules'][0]['source'], SOURCE)
        with self.assertRaisesRegex(projection.ProjectionError, 'unknown view action'):
            projection.request(view, 'douse', ACTOR, 'hidden')
        raw = {'op': 'invoke', 'object': 'lantern', 'principal': ACTOR, 'intent': 'raw-hidden',
               'expected': self.root, 'command': 'douse', 'input': {}}
        self.assertEqual(self.call(raw)['data'], 'precondition failed')
        denied = projection.request(view, 'light', 'stranger', 'denied')
        self.assertEqual(self.call(denied)['data'], 'unauthorized')
        request = projection.request(view, 'light', ACTOR, 'light-once')
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        next_view = self.project(receipt['data']['root'])
        self.assertEqual(set(next_view['data']['actions']), {'douse'})
        self.assertEqual(set(view['data']['actions']), {'light'})
        self.assertEqual(self.call(request), receipt)
        self.assertEqual(self.call({**request, 'intent': 'stale'})['data'], 'stale read root')

    def test_hidden_descriptors_must_be_well_formed(self):
        before = self.db.read_bytes()
        # The hidden command is still source-evaluated and schema-checked.
        root = copy.deepcopy(self.root)
        root['protocol']['viewProgram']['package']['modules'][0]['source'] = SOURCE.replace(
            'command: "douse"', 'command: "missing"')
        with self.assertRaisesRegex(projection.ProjectionError, 'absent command'):
            self.project(root)
        root['protocol']['viewProgram']['package']['modules'][0]['source'] = SOURCE.replace(
            'visible: Bool', 'visible: Nat').replace(
            'visible: if state.lit then false else true', 'visible: 1n').replace(
            'visible: state.lit', 'visible: 0n')
        with self.assertRaisesRegex(projection.ProjectionError, 'visible Bool'):
            self.project(root)
        raw = self.project()['rawData']
        for field, value in [('visible', 0), ('text', False), ('input', 'not a record')]:
            changed = copy.deepcopy(raw)
            changed['actions']['douse'][field] = value
            with self.subTest(field=field), self.assertRaises(projection.ProjectionError):
                projection._menu_data(changed, self.root)
        changed = copy.deepcopy(raw)
        changed['actions']['douse']['extra'] = 'hidden is not unchecked'
        with self.assertRaises(projection.ProjectionError):
            projection._menu_data(changed, self.root)
        changed = copy.deepcopy(raw)
        changed['actions'] = {str(i): copy.deepcopy(raw['actions']['douse']) for i in range(65)}
        with self.assertRaisesRegex(projection.ProjectionError, 'at most 64'):
            projection._menu_data(changed, self.root)
        self.assertEqual(self.db.read_bytes(), before)

    def test_hiding_without_a_receiving_guard_does_not_deny_a_call(self):
        protocol = copy.deepcopy(self.protocol)
        protocol['commands']['douse']['require'] = []
        revised = self.call({'op': 'reprogram', 'object': 'lantern', 'principal': ACTOR,
            'intent': 'remove-guard', 'expected': self.root, 'protocol': protocol, 'state': {'lit': False}})
        self.assertEqual(revised['kind'], 'committed', revised)
        root = revised['data']['root']
        self.assertNotIn('douse', self.project(root)['data']['actions'])
        direct = self.call({'op': 'invoke', 'object': 'lantern', 'principal': ACTOR,
            'intent': 'direct-hidden', 'expected': root, 'command': 'douse', 'input': {}})
        self.assertEqual(direct['kind'], 'committed', direct)

    def test_profile_and_runtime_are_explicit(self):
        root = copy.deepcopy(self.root)
        root['protocol']['viewProgram']['profile'] = projection.SOURCE_PROFILE
        with self.assertRaisesRegex(projection.ProjectionError, 'invalid action descriptor'):
            self.project(root)  # Existing v1 does not silently gain visibility semantics.
        view = self.project()
        projection.assert_runtime(view, self.runtime)
        wrong = copy.deepcopy(self.runtime)
        wrong['files']['spec/bend/Compiler/ObjectiveBendFrontEnd.lean'] = '0' * 64
        with self.assertRaisesRegex(projection.ProjectionError, 'expected compiled runtime'):
            projection.assert_runtime(view, wrong)
        with self.assertRaisesRegex(projection.ProjectionError, 'expected compiled runtime'):
            projection.project(self.root, 'lantern', expected_runtime=wrong)

    def test_same_menu_reaches_portal_town_and_inspection(self):
        (self.directory / 'manifest.json').write_text(json.dumps({'runtime': self.runtime}))
        app = portal.Portal(self.directory)
        browser = app.object('lantern')
        self.assertEqual([a['command'] for a in browser['actions']], ['light'])
        detail = app.detail(browser['card'])
        self.assertFalse(detail['source']['rawViewData']['actions']['douse']['visible'])
        self.assertEqual(set(detail['source']['publicViewData']['actions']), {'light'})
        prepared = app.prepare({'card': browser['card'], 'action': 'a1', 'fields': {}})
        book = town.CardBook.create(self.directory / 'town', issuer_did=ISSUER,
            world_id='urn:test:menu', runtime=self.runtime)
        card = book.capture(self.project(), 'lantern-dark')
        self.assertEqual([a['command'] for a in card['card']['actions']], ['light'])
        self.assertNotIn('Douse the lantern', card['body'])
        publication = {'uri': f'at://{ISSUER}/{town.FEED}/lantern', 'cid': 'publication'}
        value = {'$type': town.FEED, 'text': card['body']}
        def fetch(uri, cid):
            self.assertEqual((uri, cid), (publication['uri'], publication['cid']))
            return copy.deepcopy(value)
        book.bind(card['alias'], publication, fetch)
        action, = card['card']['actions']
        text = town.spell(card['alias'], action, {}, selector=town.action_word(action, card['card']['actions']))
        record = {'$type': town.FEED, 'text': text, 'reply': {'root': publication, 'parent': publication}}
        source = {'uri': f'at://{ACTOR}/{town.FEED}/light', 'cid': 'reply', 'author': ACTOR,
                  'pds': 'https://pds.delve.town'}
        wire, _ = book.resolve(record, ACTOR, source, fetch, [ISSUER])
        self.assertEqual(wire, prepared['wire'])
        receipt = self.call({**wire, 'principal': ACTOR, 'intent': source['uri']})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual([a['command'] for a in app.object('lantern')['actions']], ['douse'])
        # Old exact observation remains inspectable after the current menu changes.
        self.assertEqual(app.detail(browser['card']), detail)

    def test_authored_observation_examples_use_normalized_menu(self):
        expected = self.project()['data']
        results = propose.run_scenarios(self.protocol, [{'name': 'opening menu', 'law': [ACTOR],
            'steps': [{'observe': 'main', 'view': expected}]}], profile='compiled')
        self.assertEqual(results[0]['failures'], [])
        observation = results[0]['steps'][0]['view']
        self.assertIn('douse', observation['rawData']['actions'])
        self.assertNotIn('douse', observation['data']['actions'])


if __name__ == '__main__':
    unittest.main()
