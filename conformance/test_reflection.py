#!/usr/bin/env python3
"""Source-bound specification observation and actual reflected composition."""
import copy
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / '.lake/build/bin/delvetalk-obend'
SOURCE = (ROOT / 'syntaxes/examples/reflection/ReflectiveDoor.obend').read_text()


def call(request):
    reply = subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
                           capture_output=True, text=True, timeout=15, check=True)
    return json.loads(reply.stdout)


def fields(value):
    return {field['name']: field['value'] for field in value['fields']}


class ReflectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = {}
        for entry in ('reflected', 'assembly', 'answer', 'inspect', 'name', 'unrelatedTarget',
                      'demandAnswer', 'leftAssociated', 'rightAssociated', 'leftAnswer', 'rightAnswer'):
            compiled = call({'op': 'compile', 'source': SOURCE, 'entry': entry})
            if compiled.get('status') != 'compiled':
                raise AssertionError((entry, compiled))
            cls.artifacts[entry] = compiled['artifact']

    def run_entry(self, entry, **limits):
        return call({'op': 'run-data-v1', 'artifact': self.artifacts[entry],
                     'arguments': [], 'limits': limits})

    def inspect(self, entry, **limits):
        return call({'op': 'inspect-spec-v1', 'artifact': self.artifacts[entry], 'limits': limits})

    def test_lazy_reflection_preserves_reusable_behavior(self):
        self.assertEqual(self.run_entry('answer')['value'], {'tag': 'natural', 'value': '13'})
        self.assertEqual(self.run_entry('name')['value'], {'tag': 'label', 'value': 'Package.Base'})
        reflected = self.inspect('reflected')
        self.assertEqual(reflected['status'], 'finished', reflected)
        self.assertEqual(reflected['value']['label'], 'declared')
        # Target demand is observably different from metadata observation.
        demanded = self.run_entry('demandAnswer', ticks=1000)
        self.assertEqual(demanded['status'], 'refused', demanded)

    def test_observer_matches_source_metadata_and_retains_binding(self):
        native = self.inspect('assembly')
        source = self.run_entry('inspect')
        self.assertEqual(native['value'], source['value'])
        self.assertEqual(native['reflectionProfile'], 'delvetalk-source-specification-v1')
        self.assertEqual(native['sourceBinding'], {
            key: self.artifacts['assembly'][key]
            for key in ('entry', 'sourcesSha256', 'packetSha256')})
        composed = fields(native['value']['payload'])
        self.assertEqual(native['value']['label'], 'composed')
        declared = fields(composed['inherited']['payload'])
        self.assertEqual(declared['name']['value'], 'Package.Base')
        interface = json.loads(declared['interface']['value'])
        self.assertEqual(interface['methods'][0]['name'], 'answer')
        claims = fields(declared['claims']['payload'])
        self.assertEqual(claims['status']['value'], 'unchecked')

    def test_association_changes_metadata_but_not_completed_answer(self):
        left = self.inspect('leftAssociated')
        right = self.inspect('rightAssociated')
        self.assertEqual(left['status'], 'finished', left)
        self.assertEqual(right['status'], 'finished', right)
        self.assertNotEqual(left['value'], right['value'])
        a, b = self.run_entry('leftAnswer'), self.run_entry('rightAnswer')
        self.assertEqual(a['value'], {'tag': 'natural', 'value': '23'})
        self.assertEqual(a['value'], b['value'])

    def test_raw_prototype_does_not_certify_its_target(self):
        self.assertEqual(self.run_entry('unrelatedTarget')['value'], {'tag': 'natural', 'value': '7'})
        # We can inspect a stored specification while its unrelated target is 7.
        # No target lineage, live resource identity, or authority is manufactured.
        self.assertEqual(self.inspect('reflected')['status'], 'finished')

    def test_non_specification_forged_artifact_and_capacity_refuse(self):
        self.assertIn('must return a Specification', self.inspect('answer')['message'])
        forged = copy.deepcopy(self.artifacts['assembly'])
        forged['packet'] = self.artifacts['reflected']['packet']
        reply = call({'op': 'inspect-spec-v1', 'artifact': forged})
        self.assertIn('recompilation', reply['message'])
        reply = self.inspect('assembly', work=1)
        self.assertIn('capacity', reply['message'])
        reply = self.inspect('assembly', bytes=2, inputBytes=2)
        self.assertEqual(reply['status'], 'refused', reply)

    def test_named_prototype_wrong_target_type_refuses(self):
        source = 'edition ObjectiveBend 1\ndef identity(p: Prototype<Nat, Bool>) -> Nat:\n  targetOf(p)\n'
        reply = call({'op': 'compile', 'source': source, 'entry': 'identity'})
        self.assertEqual(reply['status'], 'error', reply)


if __name__ == '__main__':
    unittest.main()
