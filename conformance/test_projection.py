#!/usr/bin/env python3
"""Actual Lean view computation, bounded failures and governed view replacement."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('projection', ROOT / 'scene/projection.py')
projection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(projection)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'world.json'
        self.program = json.loads((ROOT / 'scene/projections/sign-v1.json').read_text())
        self.law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'light': ['alice', 'bob']},
                    'reprogram': ['programmer'], 'law': ['owner']}
        self.root = projection.world.exchange(self.db, {'op': 'create', 'object': 'sign',
            'principal': 'owner', 'intent': 'create', 'protocol': self.program, 'law': self.law})['data']['root']

    def test_state_and_personal_panel_compute_without_mutation(self):
        before = self.db.read_bytes()
        a = projection.project(self.root, 'sign')
        b = projection.project(self.root, 'sign', 'details')
        self.assertEqual(a['data']['title'], 'The workshop sign')
        self.assertEqual(b['data']['title'], 'Sign details')
        self.assertEqual(a['data']['prose'], 'The lamp is dark.')
        self.assertEqual(a['root'], b['root'])
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(a['source'], self.program['viewProgram'])
        self.assertEqual(a['mode'], 'projection')

    def test_actions_use_same_object_and_exact_root_while_lean_admits(self):
        view = projection.project(self.root, 'sign')
        denied = projection.world.exchange(self.db, projection.request(view, 'light', 'intruder', 'deny'))
        self.assertEqual(denied['data'], 'unauthorized')
        request = projection.request(view, 'light', 'alice', 'light')
        self.assertEqual(request['object'], 'sign')
        self.assertEqual(request['expected'], self.root)
        reply = projection.world.exchange(self.db, request)
        self.assertEqual(reply['kind'], 'committed')
        self.assertEqual(projection.project(reply['data']['root'], 'sign')['data']['prose'], 'The lamp is lit.')
        stale = projection.world.exchange(self.db, projection.request(view, 'light', 'bob', 'stale'))
        self.assertEqual(stale['data'], 'stale read root')
        self.assertEqual(projection.world.exchange(self.db, request), reply)

    def test_reprogram_view_then_another_participant_uses_it(self):
        old = projection.project(self.root, 'sign')
        new = json.loads((ROOT / 'scene/projections/sign-v2.json').read_text())
        request = {'op': 'reprogram', 'object': 'sign', 'principal': 'alice', 'intent': 'no-upgrade',
                   'expected': self.root, 'protocol': new, 'state': self.root['state']}
        self.assertEqual(projection.world.exchange(self.db, request)['data'], 'unauthorized')
        request.update(principal='programmer', intent='upgrade')
        reply = projection.world.exchange(self.db, request)
        self.assertEqual(reply['kind'], 'committed', reply)
        view = projection.project(reply['data']['root'], 'sign')
        self.assertNotEqual(view['programSha256'], old['programSha256'])
        self.assertIn('now teaches', view['data']['prose'])
        self.assertEqual(reply['data']['root']['law'], self.law)
        self.assertEqual(reply['data']['root']['state'], self.root['state'])
        action = projection.request(view, 'light', 'bob', 'bob-uses-new-view')
        self.assertEqual(projection.world.exchange(self.db, action)['kind'], 'committed')
        self.assertEqual(projection.world.exchange(self.db, request), reply)
        self.assertEqual(projection.world.exchange(self.db,
            projection.request(old, 'light', 'bob', 'old-view'))['data'], 'stale read root')

    def test_effect_and_function_results_are_not_display_values(self):
        for term in [['lam', ['lam', ['perform', ['label', 'do-not-send']]]],
                     ['lam', ['lam', ['lam', ['bound', 0]]]]]:
            with self.subTest(term=term):
                root = copy.deepcopy(self.root)
                root['protocol']['viewProgram']['term'] = term
                before = self.db.read_bytes()
                with self.assertRaises(projection.ProjectionError): projection.project(root, 'sign')
                self.assertEqual(self.db.read_bytes(), before)

    def test_divergence_refuses_and_does_not_mutate(self):
        root = copy.deepcopy(self.root)
        root['protocol']['viewProgram']['term'] = ['lam', ['lam',
            ['fix', ['lam', ['lam', ['bound', 1]]], ['record', []]]]]
        before = self.db.read_bytes()
        with self.assertRaises(projection.ProjectionError): projection.project(root, 'sign')
        self.assertEqual(self.db.read_bytes(), before)

    def test_schema_cannot_supply_authority_or_redirect_object(self):
        root = copy.deepcopy(self.root)
        body = root['protocol']['viewProgram']['term'][1][1]
        body[1].append(['object', ['label', 'victim']])
        with self.assertRaisesRegex(projection.ProjectionError, 'exactly title'):
            projection.project(root, 'sign')
        root = copy.deepcopy(self.root)
        root['protocol']['commands'] = {}
        with self.assertRaisesRegex(projection.ProjectionError, 'absent command'):
            projection.project(root, 'sign')

    def test_html_is_escaped_and_non_data_state_refuses(self):
        root = copy.deepcopy(self.root)
        root['state']['title'] = '<script>bad()</script>'
        root['state']['message'] = '<img src=x onerror=bad()>'
        view = projection.project(root, 'sign')
        output = projection.html_view(view)
        self.assertNotIn('<script>', output)
        self.assertNotIn('<img', output)
        self.assertIn('&lt;script&gt;', output)
        self.assertIn('Content-Security-Policy', output)
        root['state']['unsupported'] = None
        with self.assertRaises(projection.ProjectionError): projection.project(root, 'sign')


if __name__ == '__main__': unittest.main()
