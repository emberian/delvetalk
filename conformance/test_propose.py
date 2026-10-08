#!/usr/bin/env python3
"""Proposal evidence binds exact source, explicit lowering, cases and host bytes."""
import copy
from decimal import Decimal
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('proposal', ROOT / 'scripts/propose.py')
proposal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proposal)
canonical = proposal.translation.canonical


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'protocols/counter/protocol.json').read_bytes()
        self.scenarios = (ROOT / 'protocols/counter/scenarios.json').read_bytes()

    def check(self, source=None, scenarios=None, syntax='protocol-json@1'):
        return proposal.propose(syntax, self.source if source is None else source,
                                self.scenarios if scenarios is None else scenarios)

    def test_reproducible_receipts_and_identity(self):
        first = self.check()
        self.assertTrue(first['passed'])
        self.assertEqual(first, self.check())
        self.assertEqual(first['candidate']['artifact']['source']['text'].encode(), self.source)
        self.assertEqual(first['candidate']['scenarios']['source'].encode(), self.scenarios)
        self.assertEqual(first['outcomes'][0]['steps'][0]['receipt']['data']['root']['state'], {'count': 3})
        # Changing only source formatting still changes the proposal identity.
        changed = self.check(source=self.source + b'\n')
        self.assertNotEqual(first['candidate']['id'], changed['candidate']['id'])
        self.assertEqual(first['candidate']['artifact']['lowered_sha256'],
                         changed['candidate']['artifact']['lowered_sha256'])
        value = copy.deepcopy(first)
        identity = value.pop('id')
        self.assertEqual(identity, proposal.digest(canonical(value)))

    def test_markdown_and_json_share_lowering_not_source_identity(self):
        markdown = b'# Counter proposal\r\n\r\n```delvetalk-protocol\r\n' + self.source + b'\n```\n'
        report = self.check(source=markdown, syntax='protocol-markdown@1')
        plain = self.check()
        self.assertTrue(report['passed'])
        self.assertEqual(report['candidate']['artifact']['lowered'], plain['candidate']['artifact']['lowered'])
        self.assertNotEqual(report['candidate']['id'], plain['candidate']['id'])
        with self.assertRaises(ValueError):
            self.check(source=markdown + markdown, syntax='protocol-markdown@1')

    def test_spween_executable_bundle_and_source_only_refusal(self):
        source = b"""---
id: proposal_scene
---
=== hello
A scene may carry a protocol proposal.
* [Leave]
  -> END
"""
        scenarios = [{'name': 'scene-turns', 'law': ['a'], 'steps': [
            {'principal': 'a', 'command': 'start', 'input': {}, 'root': 'initial', 'kind': 'committed',
             'result': {'scene': 'proposal_scene', 'command': 'start'}},
            {'principal': 'a', 'command': 'choose:0:0', 'input': {}, 'root': 'initial',
             'kind': 'refused', 'error': 'stale read root'},
            {'principal': 'a', 'command': 'choose:0:0', 'input': {}, 'root': 'current', 'kind': 'committed',
             'result': {'scene': 'proposal_scene', 'command': 'choose:0:0'}},
            {'principal': 'a', 'command': 'choose:0:0', 'input': {}, 'root': 'current',
             'kind': 'refused', 'error': 'precondition failed'}]}]
        report = self.check(source=source, scenarios=canonical(scenarios), syntax='spween-scene-i64@1')
        self.assertTrue(report['passed'], report['outcomes'])
        self.assertEqual(report['candidate']['host']['selection'], 'lowered.protocol')
        self.assertEqual(report['candidate']['artifact']['lowered']['source'].encode(), source)
        self.assertIn('ast', report['candidate']['artifact']['lowered'])
        with self.assertRaisesRegex(ValueError, 'must target'):
            self.check(source=source, scenarios=canonical(scenarios), syntax='spween-source@1')

    def test_boolean_and_number_assertions_are_distinct(self):
        definition = {'profile': 'delvetalk-local-v1', 'initial': {'x': True}, 'commands': {
            'read': {'require': [], 'set': {}, 'result': ['state', 'x'], 'outbox': []}}}
        scenarios = [{'name': 'types', 'law': ['a'], 'steps': [
            {'principal': 'a', 'command': 'read', 'input': {}, 'root': 'current',
             'kind': 'committed', 'state': {'x': 1}, 'result': 1}]}]
        report = self.check(source=canonical(definition), scenarios=canonical(scenarios))
        self.assertFalse(report['passed'])
        self.assertEqual([f['field'] for f in report['outcomes'][0]['failures']], ['state', 'result'])

    def test_shared_markdown_greeting_example(self):
        report = self.check(source=(ROOT / 'syntaxes/examples/convention.md').read_bytes(),
                            scenarios=(ROOT / 'protocols/examples/greeting-scenarios.json').read_bytes(),
                            syntax='protocol-markdown@1')
        self.assertTrue(report['passed'])

    def test_assertion_failure_and_rejected_installation(self):
        scenarios = proposal.translation.load_json(self.scenarios)
        scenarios[0]['steps'][0]['state']['count'] = 99
        report = self.check(scenarios=canonical(scenarios))
        self.assertFalse(report['passed'])
        self.assertEqual(report['outcomes'][0]['failures'][0]['field'], 'state')
        definition = proposal.translation.load_json(self.source)
        definition['commands']['add']['result'] = ['shell', 'echo unsafe']
        report = self.check(source=canonical(definition))
        self.assertFalse(report['passed'])
        self.assertEqual(report['outcomes'][0]['failures'][0]['at'], 'installation')
        self.assertEqual(report['outcomes'][0]['steps'], [])

    def test_malformed_and_ambiguous_scenarios_refuse(self):
        cases = [b'[]', b'{}', b'NaN', b'[{"name":"a","name":"b"}]']
        base = proposal.translation.load_json(self.scenarios)
        cases.append(canonical(base + base))
        for field, value in [('root', 'latest'), ('kind', 'anything'), ('input', []),
                             ('shell', 'touch /tmp/proposal-should-never-run')]:
            variant = copy.deepcopy(base)
            variant[0]['steps'][0][field] = value
            cases.append(canonical(variant))
        for raw in cases:
            with self.subTest(raw=raw[:100]), self.assertRaises(ValueError):
                self.check(scenarios=raw)
        with self.assertRaises(ValueError):
            self.check(source=b'["nat","1"]', syntax='core-json@1')
        with self.assertRaises(ValueError):
            self.check(syntax='agent-inferred@1')

    def test_precise_decimals_and_empty_law(self):
        number = Decimal('0.12345678901234567890123456789')
        definition = {'profile': 'delvetalk-local-v1', 'initial': {'n': number}, 'commands': {
            'read': {'require': [], 'set': {}, 'result': ['state', 'n'], 'outbox': []}}}
        scenarios = [{'name': '../../path-is-only-data', 'law': ['a'], 'steps': [
            {'principal': 'a', 'command': 'read', 'input': {}, 'root': 'initial', 'kind': 'committed',
             'state': {'n': number}, 'result': number, 'outbox': []}]}]
        report = self.check(source=canonical(definition), scenarios=canonical(scenarios))
        self.assertTrue(report['passed'])
        self.assertEqual(report['outcomes'][0]['steps'][0]['receipt']['data']['result'], number)
        scenarios[0]['law'] = []
        scenarios[0]['steps'][0] = {'principal': 'a', 'command': 'read', 'input': {},
                                  'root': 'initial', 'kind': 'refused', 'error': 'unauthorized'}
        self.assertTrue(self.check(source=canonical(definition), scenarios=canonical(scenarios))['passed'])

    def test_cli_existing_world_and_source_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, scenarios, report = [directory / name for name in ('protocol.json', 'scenarios.json', 'report.json')]
            source.write_bytes(self.source)
            scenarios.write_bytes(self.scenarios)
            command = [sys.executable, str(ROOT / 'scripts/propose.py'), '--syntax', 'protocol-json@1',
                       str(source), str(scenarios)]
            for protected in (source, scenarios):
                before = protected.read_bytes()
                result = subprocess.run(command + ['-o', str(protected)], capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(protected.read_bytes(), before)
            result = subprocess.run(command + ['-o', str(report)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(proposal.translation.load_json(report.read_bytes())['passed'])
            before = report.read_bytes()
            result = subprocess.run(command + ['-o', str(report)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(report.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
