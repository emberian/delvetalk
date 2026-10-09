"""Checked source reexports preserve originating signatures and source closure."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('DELVETALK_TEMPLATE_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))


def call(request):
    done = subprocess.run([str(BINARY)], input=json.dumps(request) + '\n', text=True,
                          capture_output=True, check=True, timeout=120)
    return json.loads(done.stdout)


def module(name, source):
    return {'name': name, 'source': 'edition ObjectiveBend 1\n' + source}


class SourceExports(unittest.TestCase):
    def compile(self, modules, entry):
        return call({'op': 'compile', 'modules': modules, 'entry': entry})

    def test_renamed_chained_signature_uses_defining_type_and_helpers(self):
        original = module('Original', '''record State:
  count: Nat
def helper(n: Nat) -> Nat:
  n + 3n
def add(state: State) -> Nat:
  helper(state.count)
''')
        modules = [original, module('Middle', '''import ./Original.obend as A
export A.add as increment
'''), module('Main', '''import ./Middle.obend as M
record State:
  count: String
def helper(n: Nat) -> Nat:
  99n
export M.increment as chosen
''')]
        direct = self.compile([original], 'add')
        exported = self.compile(modules, 'chosen')
        self.assertEqual(exported['status'], 'compiled', exported)
        self.assertEqual(exported['artifact']['type'], direct['artifact']['type'])
        run = call({'op': 'run-data-v1', 'artifact': exported['artifact'],
                    'arguments': [{'tag': 'record', 'fields': [{'name': 'count', 'value': {'tag': 'natural', 'value': '4'}}]}]})
        self.assertEqual(run['value'], {'tag': 'natural', 'value': '7'}, run)
        self.assertEqual(exported['artifact']['modules'], modules)
        wrong = call({'op': 'run-data-v1', 'artifact': exported['artifact'],
                      'arguments': [{'tag': 'record', 'fields': [{'name': 'count', 'value': {'tag': 'label', 'value': '4'}}]}]})
        self.assertNotEqual(wrong['status'], 'finished', wrong)

    def test_parameter_quantities_survive_export_and_duplication_refuses(self):
        for quantity in ('affine', 'linear'):
            with self.subTest(quantity=quantity):
                original = module('Original', 'def identity(' + quantity + ' value: Nat) -> Nat:\n  value\n')
                composed = [original, module('Main', 'import ./Original.obend as A\nexport A.identity\n')]
                direct = self.compile([original], 'identity')
                exported = self.compile(composed, 'identity')
                self.assertEqual(exported['status'], 'compiled', exported)
                self.assertEqual(exported['artifact']['type'], direct['artifact']['type'])
                original['source'] = original['source'].replace('  value\n', '  value + value\n')
                refused = self.compile(composed, 'identity')
                self.assertEqual(refused['status'], 'error', refused)
                self.assertIn('checker refused', json.dumps(refused))

    def test_revised_origin_and_counterfeit_artifact(self):
        modules = [module('Original', 'def value() -> Nat:\n  1n\n'),
                   module('Main', 'import ./Original.obend as A\nexport A.value\n')]
        first = self.compile(modules, 'value')['artifact']
        revised = deepcopy(modules)
        revised[0]['source'] = revised[0]['source'].replace('1n', '2n')
        second = self.compile(revised, 'value')['artifact']
        self.assertNotEqual(first['sourcesSha256'], second['sourcesSha256'])
        self.assertNotEqual(first['packetSha256'], second['packetSha256'])
        self.assertEqual(call({'op': 'run-data-v1', 'artifact': second, 'arguments': []})['value']['value'], '2')
        counterfeit = deepcopy(first)
        counterfeit['modules'] = revised
        result = call({'op': 'run-data-v1', 'artifact': counterfeit, 'arguments': []})
        self.assertIn('recompilation', json.dumps(result))

    def test_missing_collision_and_unspecialized_generic_refuse(self):
        original = module('Original', 'def value() -> Nat:\n  1n\ndef identity<T>(x: T) -> T:\n  x\n')
        for source, reason in [
            ('export A.value\nexport A.value\n', 'duplicate declaration'),
            ('export A.value\ndef value() -> Nat:\n  2n\n', 'duplicate declaration'),
            ('def value() -> Nat:\n  2n\nexport A.value\n', 'duplicate declaration'),
            ('record value:\n  count: Nat\nexport A.value\n', 'collides with source type'),
            ('export A.absent\n', 'earlier imported value'),
            ('export A.value as A\n', 'collides with import alias'),
            ('export Missing.value\n', 'unknown export import alias'),
            ('export A.identity\n', 'unspecialized generic export'),
        ]:
            with self.subTest(source=source):
                result = self.compile([original, module('Main', 'import ./Original.obend as A\n' + source)], 'value')
                self.assertNotEqual(result['status'], 'compiled', result)
                self.assertIn(reason, json.dumps(result))

    def test_contract_candidate_actual_export_surface(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import source_closure
        roots = [
            ('Candidate', ROOT / 'protocols/editor/Candidate.obend'),
            ('ContractWorkshop', ROOT / 'protocols/contract-workshop/Workshop.obend'),
            ('ContractCandidate', ROOT / 'protocols/contract-workshop/ContractCandidate.obend')]
        modules = source_closure.read(['ContractCandidate'], list(source_closure.LIBRARY) + roots, root=ROOT,
            parser=lambda supplied: source_closure.native_imports(supplied, runner=BINARY))
        candidate_index = next(i for i, m in enumerate(modules) if m['name'] == 'Candidate')
        original = modules[:candidate_index + 1]
        names = ('ordinary', 'submit', 'requestCheck', 'prepareInspectProposal', 'prepareCompilerWork',
                 'compiled', 'failed', 'report', 'adopt', 'prepareRelease', 'view')
        for name in names:
            with self.subTest(export=name):
                direct = self.compile(original, name)
                exported = self.compile(modules, name)
                self.assertEqual(exported['status'], 'compiled', exported)
                self.assertEqual(direct['status'], 'compiled', direct)
                self.assertEqual(exported['artifact']['type'], direct['artifact']['type'])


if __name__ == '__main__':
    unittest.main()
