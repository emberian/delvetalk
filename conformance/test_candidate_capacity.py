"""Retained source data keeps the declared module and native frame capacities."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(os.environ.get('DELVETALK_TEST_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
import desk
import source_object
from syntaxes import obend_object

SOURCE = '''edition ObjectiveBend 1
import ./Abi.obend as A
import ./Encounter.obend as E
record State:
  count: Nat
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: Nat
record Description:
  name: String
  initial: State
  methods: {add: {label: String, fields: {amount: A.NatField}}}
  panels: {}
def describe() -> Description:
  {name: "A retained counter", initial: {count: 0n}, methods: {add: {label: "Add", fields: {amount: {type: "nat", minimum: 0n, maximum: 99n}}}}, panels: {}}
def add(state: State, input: {amount: Nat}, context: A.Context) -> Decision:
  {accepted: true, reason: "", state: {count: state.count + input.amount}, result: state.count + input.amount}
def view(state: State, panel: String) -> {title: String, prose: String, actions: {}, children: E.Children}:
  {title: "A retained counter", prose: "A counter kept by source.", actions: {}, children: E.Children.nil()}
'''


class CandidateCapacity(unittest.TestCase):
    def test_transport_value_strings_are_symmetric_without_raising_presentation_bounds(self):
        text = 'x' * 70000
        self.assertEqual(source_object.values('decode', source_object.values('encode', [text])), [text])
        number = {'tag': 'variant', 'label': 'number', 'payload': source_object.data({'encoded': '1' * 70000})}
        with self.assertRaisesRegex(ValueError, 'text capacity'):
            source_object.values('decode', [number])
        with self.assertRaisesRegex(ValueError, 'exceeds 1 MiB'):
            source_object.values('encode', ['x' * (1024 * 1024)])

    def test_single_large_module_can_be_retained_checked_inspected_and_released(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            client = desk.Desk(base / 'world.json', base / 'artifacts')
            modules = [{'name': name, 'source': (ROOT / ('world/lib/prelude/' + name + '.obend')).read_text()}
                       for name in ('List', 'Abi', 'Encounter')]
            protocol = obend_object.lower_data_modules(modules + [{'name': 'Counter', 'source': SOURCE}])
            law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'add': ['player']},
                   'reprogram': ['reviewer'], 'law': ['owner']}
            target = client.exchange({'op': 'create', 'object': 'target', 'principal': 'owner',
                'intent': 'create-target', 'protocol': protocol, 'law': law})
            self.assertEqual(target['kind'], 'committed', target)
            target = target['data']['root']
            candidate_law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'submit': ['author'],
                'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': ['reviewer']},
                'reprogram': [], 'law': ['owner']}
            candidate = client.create('candidate', 'owner', 'create-candidate', candidate_law)['data']['root']
            large = SOURCE + '\n# ' + 'exact retained source ' * 4000 + '\n'
            self.assertGreater(len(large.encode()), 64 * 1024)
            full = modules + [{'name': 'Counter', 'source': large}]
            entries = [{'name': module['name'], 'sourceRef': desk.source_store.store_bytes(
                client.artifact_store, module['source'].encode(), kind='source')} for module in full]
            scenarios = desk.canonical([{'name': 'actual-source-add', 'law': ['player'], 'steps': [{
                'principal': 'player', 'command': 'add', 'input': {'amount': 3}, 'root': 'initial',
                'kind': 'committed', 'result': 3}]}])
            proposal = desk.source_store.prepare_module_proposal(client.artifact_store,
                desk.source_store.seal_modules(entries), scenarios, syntax='objective-bend-spell@3')
            submitted = client.submit_refs('candidate', 'author', 'submit', candidate,
                proposal, target['state'], 'target')
            self.assertEqual(submitted['kind'], 'committed', submitted)
            checked = client.check('candidate', 'compiler', 'compile', submitted['data']['root'])
            self.assertEqual(checked['kind'], 'committed', checked)
            ready = checked['data']['root']
            before = desk.canonical(ready)
            state = desk.candidate_state(ready)
            self.assertEqual(state['status'], 'ready', state['diagnostics'])
            retained = state['protocol']['sourcePackages']['resident']['modules']
            self.assertEqual(retained[-1]['source'], large)
            self.assertEqual(desk.canonical(ready), before)
            released = client.adopt('candidate', 'target', 'reviewer', 'release', ready, target)
            self.assertEqual(released['kind'], 'committed', released)
            installed = client.inspect('target')
            self.assertEqual(installed['protocol']['sourcePackages']['resident']['modules'][-1]['source'], large)
            self.assertEqual(installed['state'], target['state'])
            self.assertEqual(installed['law'], target['law'])
            self.assertEqual(client.adopt('candidate', 'target', 'reviewer', 'release', ready, target), released)
            used = client.exchange({'op': 'invoke', 'object': 'target', 'principal': 'player',
                'intent': 'use-source', 'expected': installed, 'command': 'add', 'input': {'amount': 4}})
            self.assertEqual(used['kind'], 'committed', used)
            self.assertEqual(used['data']['result'], 4)
            with self.assertRaises(ValueError):
                desk.source_store.store_bytes(client.artifact_store,
                    b'x' * (desk.source_store.LIMITS['source'] + 1), kind='source')


if __name__ == '__main__':
    unittest.main()
