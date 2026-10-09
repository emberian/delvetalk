"""Bounds and atomicity at the native Data-to-source-transition receiving join."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_data_world', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


class NativeDataReceiving(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'world.json'

    def call(self, request):
        return world.exchange(self.db, request, profile='compiled')

    def create(self, name, protocol):
        receipt = self.call({'op': 'create', 'object': name, 'principal': 'owner',
            'intent': 'new-' + name, 'protocol': protocol, 'law': ['owner']})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        return receipt['data']['root']

    def test_native_reprogram_digest_keeps_shared_work_and_exact_root_on_refusal(self):
        original = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {}}
        root = self.create('bounded', original)
        proposed = {**original, 'description': 'x' * 155000}
        request = {'op': 'reprogram', 'object': 'bounded', 'principal': 'owner',
                   'intent': 'over-budget', 'expected': root, 'protocol': proposed, 'state': {}}
        refused = self.call(request)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('budget exhausted', refused['data'])
        self.assertEqual(self.call({'op': 'inspect', 'object': 'bounded', 'principal': 'reader'}), root)
        self.assertEqual(self.call(request), refused)
        # The same boundary still admits and fingerprints a smaller complete program.
        accepted = copy.deepcopy(request)
        accepted['intent'] = 'within-budget'
        accepted['protocol']['description'] = 'x' * 1000
        self.assertEqual(self.call(accepted)['kind'], 'committed')

    def test_typed_refusal_does_not_skip_eager_result_materialization(self):
        source = '''edition ObjectiveBend 1
record State:
  count: Nat
record Input:
  amount: Nat
record Origin:
  kind: String
  object: String
  command: String
  immediatelyPrevious: Bool
record Context:
  object: String
  principal: String
  inputOrigin: Origin
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: Nat
def spin(n: Nat) -> Nat:
  spin(n + 1n)
def turn(state: State, input: Input, context: Context) -> Decision:
  {accepted: false, reason: "declined", state: {count: 9n}, result: spin(input.amount)}
'''
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {'model': {
            'tag': 'record', 'fields': [{'name': 'count', 'value': {'tag': 'natural', 'value': '0'}}]}},
            'commands': {'turn': {'transition': {'profile': 'delvetalk-source-data-transition-v1',
                'package': {'modules': [{'name': 'Main', 'source': source}], 'entry': 'turn'}}}}}
        root = self.create('eager', protocol)
        refused = self.call({'op': 'invoke', 'object': 'eager', 'principal': 'owner',
            'intent': 'refuse-with-divergent-result', 'expected': root, 'command': 'turn', 'input': {'amount': 1}})
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('tickExhausted', refused['data'])
        self.assertEqual(self.call({'op': 'inspect', 'object': 'eager', 'principal': 'reader'}), root)


if __name__ == '__main__':
    unittest.main()
