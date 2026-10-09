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
sys.path.insert(0, str(ROOT))
from conformance.source_custody_fixture import counter_source, count
spec = importlib.util.spec_from_file_location('proposal', ROOT / 'scripts/propose.py')
proposal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proposal)
canonical = proposal.translation.canonical


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.source = counter_source()
        self.scenarios = canonical([{'name': 'source-add', 'law': ['player'], 'steps': [
            {'principal': 'player', 'command': 'add', 'input': {'amount': 3}, 'root': 'initial',
             'kind': 'committed', 'result': 3},
            {'principal': 'player', 'command': 'add', 'input': {'amount': 1}, 'root': 'initial',
             'kind': 'refused', 'error': 'stale read root'},
            {'principal': 'outsider', 'command': 'add', 'input': {'amount': 1}, 'root': 'current',
             'kind': 'refused', 'error': 'unauthorized'}]}])

    def check(self, source=None, scenarios=None, syntax='objective-bend-object'):
        return proposal.propose(syntax, self.source if source is None else source,
                                self.scenarios if scenarios is None else scenarios)

    def test_reproducible_receipts_and_identity(self):
        first = self.check()
        self.assertTrue(first['passed'])
        self.assertEqual(first, self.check())
        self.assertEqual(first['candidate']['artifact']['source']['text'].encode(), self.source)
        self.assertEqual(first['candidate']['scenarios']['source'].encode(), self.scenarios)
        self.assertEqual(count(first['outcomes'][0]['steps'][0]['receipt']['data']['root']), 3)
        # Changing only source formatting still changes the proposal identity.
        changed = self.check(source=self.source + b'\n')
        self.assertNotEqual(first['candidate']['id'], changed['candidate']['id'])
        self.assertEqual(changed['candidate']['artifact']['source']['text'].encode(), self.source + b'\n')
        value = copy.deepcopy(first)
        identity = value.pop('id')
        self.assertEqual(identity, proposal.digest(canonical(value)))

    def test_assertion_failure_and_empty_current_authority(self):
        scenarios = proposal.translation.load_json(self.scenarios)
        scenarios[0]['steps'][0]['result'] = 99
        report = self.check(scenarios=canonical(scenarios))
        self.assertFalse(report['passed'])
        self.assertEqual(report['outcomes'][0]['failures'][0]['field'], 'result')
        scenarios[0]['law'] = []
        scenarios[0]['steps'] = [{'principal': 'player', 'command': 'add', 'input': {'amount': 1},
                                'root': 'initial', 'kind': 'refused', 'error': 'unauthorized'}]
        self.assertTrue(self.check(scenarios=canonical(scenarios))['passed'])

    def test_invalid_source_and_retired_syntax_refuse(self):
        with self.assertRaises(ValueError):
            self.check(source=b'edition ObjectiveBend 1\ndef broken(')
        for syntax in ('spween-scene-i64@1', 'spween-scene-i64@2'):
            with self.subTest(syntax=syntax), self.assertRaises(ValueError):
                self.check(syntax=syntax)

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

    def test_cli_existing_world_and_source_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, scenarios, report = [directory / name for name in ('protocol.json', 'scenarios.json', 'report.json')]
            source.write_bytes(self.source)
            scenarios.write_bytes(self.scenarios)
            command = [sys.executable, str(ROOT / 'scripts/propose.py'), '--syntax', 'objective-bend-object',
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
