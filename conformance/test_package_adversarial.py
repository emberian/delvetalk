#!/usr/bin/env python3
"""Source/packet binding and bounded typed package execution; no compiler builds."""
import copy
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / '.lake/build/bin/delvetalk-obend'
N = lambda n: {'tag': 'natural', 'value': str(n)}
BOOL = lambda b: {'tag': 'boolean', 'value': b}


def jobs(requests):
    result = subprocess.run([str(RUNNER)], input=''.join(json.dumps(r) + '\n' for r in requests),
                            capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise AssertionError(result.stderr)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    if len(rows) != len(requests):
        raise AssertionError((len(rows), len(requests), result.stderr))
    return rows


def source(value):
    return f'edition ObjectiveBend 1\ndef main() -> Nat:\n  {value}n\n'


class PackageAdversarial(unittest.TestCase):
    def compile(self, text, entry='main', **extra):
        row, = jobs([{'op': 'compile', 'source': text, 'entry': entry, **extra}])
        self.assertEqual(row['status'], 'compiled', row)
        return row['artifact']

    def run_package(self, artifact, arguments=(), **extra):
        row, = jobs([{'op': 'run', 'artifact': artifact, 'arguments': list(arguments), **extra}])
        return row

    def test_separately_valid_source_and_packet_hashes_do_not_establish_binding(self):
        a, b = self.compile(source(1)), self.compile(source(2))
        for fieldset in [('modules', 'sourcesSha256'), ('packet', 'packetSha256')]:
            with self.subTest(fields=fieldset):
                forged = copy.deepcopy(a)
                for field in fieldset:
                    forged[field] = copy.deepcopy(b[field])
                result = self.run_package(forged)
                self.assertEqual(result['status'], 'error', result)
                self.assertIn('recompilation', result['message'])
        self.assertEqual(self.run_package(a)['value'], N(1))
        self.assertEqual(self.run_package(b)['value'], N(2))

    def test_metadata_and_limit_substitution_cannot_bypass_exact_artifact_check(self):
        text = 'edition ObjectiveBend 1\ndef main() -> Nat:\n  1n\ndef other() -> Nat:\n  2n\n'
        artifact = self.compile(text)
        for mutate in [lambda a: a.update(entry='other'),
                       lambda a: a.update(type={'tag': 'boolean'}),
                       lambda a: a['limits'].update(typeFuel='1'),
                       lambda a: a.update(unrecognized='ignored?')]:
            candidate = copy.deepcopy(artifact)
            mutate(candidate)
            result = self.run_package(candidate)
            self.assertEqual(result['status'], 'error', result)
        # A valid run in the same process must not allow subsequent changed
        # artifacts to reuse a verification cache keyed only by source or hash.
        forged = copy.deepcopy(artifact)
        forged['entry'] = 'other'
        rows = jobs([{'op': 'run', 'artifact': a, 'arguments': []}
                     for a in [artifact, forged, artifact]])
        self.assertEqual([r['status'] for r in rows], ['finished', 'error', 'finished'])

    def test_arguments_are_typed_data_not_code_or_an_authority_claim(self):
        artifact = self.compile('edition ObjectiveBend 1\ndef main(x: Nat) -> Nat:\n  x + 1n\n')
        self.assertEqual(self.run_package(artifact, [N(4)])['value'], N(5))
        for argument in [BOOL(True), {'tag': 'term', 'term': ['perform', ['label', 'write']]},
                         {'tag': 'variant', 'label': 'grant', 'payload': N(0)}]:
            with self.subTest(argument=argument):
                self.assertEqual(self.run_package(artifact, [argument])['status'], 'error')
        self.assertEqual(self.run_package(artifact, [])['status'], 'error')

    def test_duplicate_data_fields_cannot_escape_into_plain_json(self):
        # Source literals reject duplicates, but the ordered typed-data wire can
        # carry them. The upstream extractor must refuse to publish an ambiguous
        # record before the compiled host's Data-to-JSON conversion is reached.
        text = ('edition ObjectiveBend 1\nrecord R:\n  x: Nat\n'
                'def main(value: R) -> R:\n  value\n'
                'def first(value: R) -> Nat:\n  value.x\n')
        duplicate = {'tag': 'record', 'fields': [
            {'name': 'x', 'value': N(1)}, {'name': 'x', 'value': N(2)}]}
        identity = self.compile(text)
        result = self.run_package(identity, [duplicate])
        self.assertEqual(result['status'], 'refused', result)
        self.assertIn('duplicateField', result['failure'])
        self.assertNotIn('value', result)
        # Lookup still means first matching field; refusing output must not
        # retroactively reinterpret source lookup as JSON's last-key-wins.
        projection = self.compile(text, entry='first')
        self.assertEqual(self.run_package(projection, [duplicate])['value'], N(1))

    def test_execution_limits_are_enforced_independently_of_compile_limits(self):
        artifact = self.compile('edition ObjectiveBend 1\ndef main(x: Nat) -> Nat:\n  x + 1n\n')
        for limits in [{'ticks': '0'}, {'nodes': '0'}, {'heap': '0'}, {'bytes': '0'}]:
            with self.subTest(limits=limits):
                result = self.run_package(artifact, [N(1)], limits=limits)
                self.assertEqual(result['status'], 'refused', result)
                self.assertNotIn('value', result)
        for limits in [{'ticks': '1000001'}, {'heap': '1000001'}, {'stack': '100001'},
                       {'nodes': '1000001'}, {'bytes': '16777217'}]:
            with self.subTest(limits=limits):
                result = self.run_package(artifact, [N(1)], limits=limits)
                self.assertEqual(result['status'], 'error', result)
                self.assertIn('capacity', result['message'])

    def test_supplied_module_import_is_bound_and_filesystem_paths_refused(self):
        library = 'edition ObjectiveBend 1\ndef amount() -> Nat:\n  8n\n'
        main = 'edition ObjectiveBend 1\nimport ./Library.obend as Library\ndef main() -> Nat:\n  Library.amount()\n'
        modules = [{'name': 'Library', 'source': library}, {'name': 'Main', 'source': main}]
        row, = jobs([{'op': 'compile', 'modules': modules, 'entry': 'main'}])
        self.assertEqual(row['status'], 'compiled', row)
        self.assertEqual(self.run_package(row['artifact'])['value'], N(8))
        for invalid in [list(reversed(modules)), [modules[1]],
                        [modules[0], {'name': 'Main', 'source': main.replace('./Library.obend', '../Library.obend')}]]:
            refused, = jobs([{'op': 'compile', 'modules': invalid, 'entry': 'main'}])
            self.assertEqual(refused['status'], 'error', refused)
            self.assertIn('earlier supplied module', refused['message'])


if __name__ == '__main__':
    unittest.main()
