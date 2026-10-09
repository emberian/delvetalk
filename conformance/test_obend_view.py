#!/usr/bin/env python3
"""Source-authored views run through the real checked compiled Lean host."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('obend_projection', ROOT / 'scene/projection.py')
projection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(projection)

SOURCE = '''edition ObjectiveBend 1
record State:
  lit: Bool
record Action:
  text: String
  command: String
  input: {}
record Actions:
  knock: Action
record View:
  title: String
  prose: String
  actions: Actions
def view(state: State, panel: String) -> View:
  {title: if panel == "details" then "Door details" else "The paper door", prose: if state.lit then "A lantern glows." else "The room is dark.", actions: {knock: {text: "Knock", command: "knock", input: {}}}}
'''


class SourceViewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / 'world.json'
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {'lit': False},
                    'commands': {'knock': {'require': [], 'set': {'lit': ['literal', True]},
                                           'result': ['literal', 'Welcome'], 'outbox': []}},
                    'viewProgram': {'profile': projection.SOURCE_PROFILE,
                                    'package': {'modules': [{'name': 'Main', 'source': SOURCE}],
                                                'entry': 'view'}}}
        receipt = projection.world.exchange(self.db, {'op': 'create', 'object': 'door',
            'principal': 'maker', 'intent': 'create', 'protocol': protocol, 'law': ['visitor']},
            profile='compiled')
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.root = receipt['data']['root']

    def changed_source(self, source):
        root = copy.deepcopy(self.root)
        root['protocol']['viewProgram']['package']['modules'][0]['source'] = source
        return root

    def test_source_state_panel_and_exact_root_actions(self):
        before = self.db.read_bytes()
        view = projection.project(self.root, 'door')
        self.assertEqual(view['data']['prose'], 'The room is dark.')
        self.assertEqual(projection.project(self.root, 'door', 'details')['data']['title'], 'Door details')
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(view['source']['package']['modules'][0]['source'], SOURCE)
        pins = view['runtimeProfile']
        self.assertEqual(pins['profile'], 'compiled')
        self.assertIn('spec/bend/Compiler/ObjectiveBendFrontEnd.lean', pins['files'])
        request = projection.request(view, 'knock', 'visitor', 'knock-once')
        self.assertEqual(request['expected'], self.root)
        receipt = projection.world.exchange(self.db, request, profile='compiled')
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(projection.project(receipt['data']['root'], 'door')['data']['prose'], 'A lantern glows.')
        stale = projection.request(view, 'knock', 'visitor', 'stale')
        self.assertEqual(projection.world.exchange(self.db, stale, profile='compiled')['data'], 'stale read root')

    def test_semantic_and_schema_refusals_leave_custody_unchanged(self):
        before = self.db.read_bytes()
        sources = [SOURCE.replace('command: "knock"', 'command: "steal"'),
                   SOURCE.replace('prose: String', 'prose: Nat').replace(
                       'prose: if state.lit then "A lantern glows." else "The room is dark."', 'prose: 7n'),
                   SOURCE.replace('-> View:', '-> Nat:'),
                   'edition ObjectiveBend 1\ndef view(state: State, panel: String) -> String:\n  "bad"\n']
        for source in sources:
            with self.subTest(source=source):
                with self.assertRaises(projection.ProjectionError):
                    projection.project(self.changed_source(source), 'door')
                self.assertEqual(self.db.read_bytes(), before)
        for value in (None, [], -1):
            root = copy.deepcopy(self.root)
            root['state']['lit'] = value
            with self.assertRaises(projection.ProjectionError):
                projection.project(root, 'door')

    def test_well_typed_activity_cannot_send_effects(self):
        source = '''edition ObjectiveBend 1
record State:
  lit: Bool
sum Plan:
  send: String
sum Response:
  received: {}
def view(state: State, panel: String) -> Activity<Plan, Response, String>:
  match perform(Plan.send("DO NOT SEND")):
    case received(_): "sent"
'''
        before = self.db.read_bytes()
        with self.assertRaisesRegex(projection.ProjectionError, 'first-order data type'):
            projection.project(self.changed_source(source), 'door')
        self.assertEqual(self.db.read_bytes(), before)

    def test_rejects_caller_supplied_packet_and_unknown_descriptor_fields(self):
        for location in ('program', 'package', 'module'):
            root = copy.deepcopy(self.root)
            program = root['protocol']['viewProgram']
            target = {'program': program, 'package': program['package'],
                      'module': program['package']['modules'][0]}[location]
            target['packet'] = {}
            with self.assertRaises(projection.ProjectionError):
                projection.project(root, 'door')

    def test_world_bound_view_refuses_stable_but_different_runtime(self):
        pins = projection.runtime_profile.file_hashes('compiled')
        expected = {'name': 'compiled', 'files': pins}
        view = projection.project(self.root, 'door', expected_runtime=expected)
        projection.assert_runtime(view, expected)
        changed = dict(pins)
        changed['spec/bend/Compiler/ObjectiveBendFrontEnd.lean'] = '0' * 64
        # Model a source dependency changed BEFORE inspection and stable during
        # it, not merely the already-covered case of changing while it runs.
        with patch.object(projection.runtime_profile, 'file_hashes', return_value=changed):
            with patch.object(projection.subprocess, 'run') as run:
                with self.assertRaisesRegex(projection.ProjectionError, 'expected compiled runtime'):
                    projection.project(self.root, 'door', expected_runtime=expected)
                run.assert_not_called()
            standalone = projection.project(self.root, 'door')
            self.assertEqual(standalone['runtimeProfile']['files'], changed)
            with self.assertRaises(projection.ProjectionError):
                projection.assert_runtime(standalone, expected)
            # Historical source observations compare retained pins, not today's.
            projection.assert_runtime(view, expected)
        for incompatible in ({}, {'name': 'world', 'files': pins},
                             {'name': 'compiled', 'files': {}}):
            with self.subTest(runtime=incompatible):
                with self.assertRaises(projection.ProjectionError):
                    projection.project(self.root, 'door', expected_runtime=incompatible)
                with self.assertRaises(projection.ProjectionError):
                    projection.assert_runtime(view, incompatible)
        forged = copy.deepcopy(view)
        forged['runtimeSha256'] = '0' * 64
        with self.assertRaises(projection.ProjectionError):
            projection.assert_runtime(forged, expected)


if __name__ == '__main__':
    unittest.main()
