#!/usr/bin/env python3
"""Reusable prototype types and row-extension synthesis through the real frontend."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / '.lake/build/bin/delvetalk-obend'
SOURCE = (ROOT / 'syntaxes/examples/reflection/ReusablePrototype.obend').read_text()


def call(request):
    reply = subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
                           text=True, capture_output=True, timeout=15, check=True)
    return json.loads(reply.stdout)


class FrontendAbstractions(unittest.TestCase):
    def compile(self, source, entry):
        return call({'op': 'compile', 'source': source, 'entry': entry})

    def execute(self, entry, source=SOURCE):
        compiled = self.compile(source, entry)
        self.assertEqual(compiled['status'], 'compiled', compiled)
        result = call({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertEqual(result['status'], 'finished', result)
        return result['value']

    def test_named_prototype_can_be_returned_passed_revised_and_reused(self):
        self.assertEqual(self.execute('twice'), {'tag': 'natural', 'value': '26'})
        self.assertEqual(self.execute('projected'), {'tag': 'natural', 'value': '7'})
        metadata = self.execute('history')
        self.assertEqual(metadata['tag'], 'variant')
        self.assertEqual(metadata['label'], 'composed')

    def test_let_extension_infers_result_and_preserves_open_super(self):
        record = self.execute('revisedRecord')
        values = {field['name']: field['value'] for field in record['fields']}
        self.assertEqual(values, {'x': {'tag': 'natural', 'value': '1'},
                                  'title': {'tag': 'label', 'value': 'moon'}})
        self.assertEqual(self.execute('inferredRecord')['fields'][0]['value'], {'tag': 'natural', 'value': '2'})
        self.assertEqual(self.execute('openLayers'), {'tag': 'natural', 'value': '7'})

    def test_wrong_prototype_components_and_observers_refuse(self):
        cases = [
            ('Prototype<Specification<Door>, Door>:\n  prototype(Base, unfinished())',
             'Prototype<Specification<Door>, Nat>:\n  prototype(Base, unfinished())'),
            ('prototype(Base, unfinished())', 'prototype(7n, unfinished())'),
            ('def projected() -> Nat:', 'def projected() -> Bool:'),
            ('targetOf(p)\n\ndef revisedRecord', 'reflect(7n)\n\ndef revisedRecord')]
        for before, after in cases:
            self.assertIn(before, SOURCE)
            result = self.compile(SOURCE.replace(before, after), 'twice')
            self.assertEqual(result['status'], 'error', result)

    def test_wrong_extension_types_and_rigid_bounds_still_refuse(self):
        for changed in (
            SOURCE.replace('extend(original, {x: 2n})', 'extend(7n, {x: 2n})'),
            SOURCE.replace('title: "moon"', 'title: 2n'),
            SOURCE.replace('y: self.x + 1n', 'y: self.missing + 1n'),
            SOURCE.replace('let original: Super = super', 'let original: {x: Nat} = super')):
            result = self.compile(changed, 'openLayers')
            self.assertEqual(result['status'], 'error', result)

    def test_prototypes_do_not_become_serializable_data(self):
        compiled = self.compile(SOURCE, 'carry')
        self.assertEqual(compiled['status'], 'compiled', compiled)
        self.assertEqual(compiled['artifact']['type']['tag'], 'prototype')
        result = call({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertIn('not serializable', result['message'])

    def test_builtin_spelling_can_be_shadowed_by_ordinary_source_function(self):
        source = 'edition ObjectiveBend 1\ndef prototype(x: Nat) -> Nat:\n  x + 1n\ndef answer():\n  prototype(4n)\n'
        self.assertEqual(self.execute('answer', source), {'tag': 'natural', 'value': '5'})

    def test_reversible_git_pin_verification(self):
        result = subprocess.run(['python3', 'scripts/check_capsules.py'], cwd=ROOT,
                                text=True, capture_output=True, check=True)
        self.assertIn('identities match', result.stdout)


if __name__ == '__main__':
    unittest.main()
