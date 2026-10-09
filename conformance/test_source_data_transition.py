#!/usr/bin/env python3
"""Explicit typed state at the actual source/authority/atomic receiving join."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('data_transition_world', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


def record(**fields):
    return {'tag': 'record', 'fields': [{'name': name, 'value': value} for name, value in fields.items()]}


def variant(label, payload):
    return {'tag': 'variant', 'label': label, 'payload': payload}


def natural(value):
    return {'tag': 'natural', 'value': str(value)}


def sequence(*values):
    tail = variant('nil', record())
    for value in reversed(values):
        tail = variant('cons', record(head=natural(value), tail=tail))
    return tail


SOURCE = '''edition ObjectiveBend 1
sum List:
  nil: {}
  cons: {head: Nat, tail: List}
record State:
  visits: List
record Input:
  object: String
  version: Nat
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
  result: String
def turn(state: State, input: Input, context: Context) -> Decision:
  let ok = context.inputOrigin.kind == "observe" && context.inputOrigin.immediatelyPrevious && context.inputOrigin.object == input.object
  {accepted: ok, reason: if ok then "" else "observe first", state: {visits: List.cons({head: input.version, tail: state.visits})}, result: context.principal}
def identity(xs: List) -> List:
  xs
'''
TARGET = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
    'touch': {'require': [], 'set': {}, 'result': ['literal', {}], 'outbox': []}}}


def protocol(source=SOURCE, initial=None):
    return {'profile': 'delvetalk-local-v1', 'initial': initial or {'model': record(visits=sequence())},
        'commands': {'add': {'transition': {'profile': 'delvetalk-source-data-transition-v1',
            'package': {'modules': [{'name': 'Visits', 'source': source}], 'entry': 'turn'}}}}}


class SourceDataTransition(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'world.json'

    def call(self, request, profile='compiled'):
        return world.exchange(self.db, request, profile=profile)

    def create(self, name, program):
        receipt = self.call({'op': 'create', 'object': name, 'principal': 'owner',
            'intent': 'create-' + name, 'protocol': program, 'law': ['owner', 'visitor']})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        return receipt['data']['root']

    def inspect(self, name):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def add(self, root, *, intent='add', input=None, name='index'):
        return {'op': 'invoke', 'object': name, 'principal': 'visitor', 'intent': intent,
            'expected': root, 'command': 'add', 'input': input or {'object': 'target', 'version': 0}}

    def test_observed_typed_list_state_survives_repeated_invocation_and_restart(self):
        target = self.create('target', TARGET)
        index = self.create('index', protocol())
        for number in range(2):
            calls = ([] if number == 0 else [{'object': 'target', 'command': 'touch', 'input': {}}])
            observed = len(calls)
            calls += [{'op': 'observe', 'object': 'target'},
                      {'object': 'index', 'command': 'add', 'inputFrom': observed}]
            request = {'op': 'transaction', 'principal': 'visitor', 'intent': 'observe-' + str(number),
                'reads': {'target': target, 'index': index}, 'calls': calls}
            receipt = self.call(request)
            self.assertEqual(receipt['kind'], 'committed', receipt)
            self.assertEqual(receipt['data']['results'][-1], 'visitor')
            self.assertEqual(self.call(request), receipt)
            target, index = self.inspect('target'), self.inspect('index')
            self.assertEqual(index['state'], {'model': record(visits=sequence(*reversed(range(number + 1))))})
        # Each exchange is a fresh process against persisted custody. An equal
        # copied witness gets no origin and cannot append a third list cell.
        refused = self.call(self.add(index))
        self.assertEqual(refused['data'], 'source refused: observe first')
        self.assertEqual(self.inspect('index'), index)

    def test_explicit_typed_expression_and_plain_route_do_not_guess_each_other(self):
        descriptor = {'modules': [{'name': 'Lists', 'source': SOURCE}], 'entry': 'identity'}
        expression = ['package-data-v1', descriptor, [['literal', sequence(4, 5)]]]
        candidate = copy.deepcopy(TARGET)
        candidate['commands']['touch']['result'] = expression
        root = self.create('typed', candidate)
        request = {'op': 'invoke', 'object': 'typed', 'principal': 'visitor', 'intent': 'typed',
            'expected': root, 'command': 'touch', 'input': {}}
        self.assertEqual(self.call(request)['data']['result'], sequence(4, 5))
        candidate['commands']['touch']['result'][0] = 'package'
        root = self.create('plain', candidate)
        request.update(object='plain', intent='plain', expected=root)
        self.assertEqual(self.call(request)['kind'], 'refused')
        self.assertEqual(self.inspect('plain'), root)

    def test_malformed_typed_model_and_wrong_schema_refuse_without_writes(self):
        bad_models = [
            {'model': {'tag': 'record', 'fields': [], 'extra': True}},
            {'model': record(visits=variant('unknown', record()))},
            {'model': record(visits=variant('cons', record(head=natural(1), tail=natural(2))))},
            {'model': record(visits=sequence()), 'other': 0},
        ]
        for number, initial in enumerate(bad_models):
            name = 'bad-' + str(number)
            root = self.create(name, protocol(initial=initial))
            refused = self.call(self.add(root, name=name, intent=name))
            self.assertEqual(refused['kind'], 'refused', refused)
            self.assertNotEqual(refused['data'], 'source refused: observe first')
            self.assertEqual(self.inspect(name), root)

    def test_refused_envelope_still_requires_plain_result_and_record_state(self):
        wrong_result = SOURCE.replace('  result: String', '  result: List').replace(
            'result: context.principal', 'result: List.nil()')
        wrong_state = SOURCE.replace('  state: State\n', '  state: Nat\n').replace(
            'state: {visits: List.cons({head: input.version, tail: state.visits})}', 'state: 0n')
        for number, text in enumerate((wrong_result, wrong_state)):
            name = 'bad-envelope-' + str(number)
            root = self.create(name, protocol(text))
            refused = self.call(self.add(root, name=name, intent=name))
            self.assertEqual(refused['kind'], 'refused', refused)
            self.assertNotEqual(refused['data'], 'source refused: observe first')
            self.assertEqual(self.inspect(name), root)

    def test_shared_budget_exhaustion_rolls_back_typed_state(self):
        text = SOURCE.replace('def turn(', 'def loop(n: Nat) -> Nat:\n  if n == 0n then 0n else loop(n - 1n)\ndef turn(')
        start = text.index('  let ok =')
        end = text.index('def identity', start)
        text = text[:start] + ('  let n = loop(input.version)\n'
            '  {accepted: true, reason: "", state: {visits: List.cons({head: n, tail: state.visits})}, result: "done"}\n') + text[end:]
        root = self.create('index', protocol(text))
        once = self.call(self.add(root, input={'object': 'target', 'version': 3000}))
        self.assertEqual(once['kind'], 'committed', once)
        current = self.inspect('index')
        request = {'op': 'transaction', 'principal': 'visitor', 'intent': 'twice',
            'reads': {'index': current}, 'calls': [
                {'object': 'index', 'command': 'add', 'input': {'object': 'target', 'version': 3000}},
                {'object': 'index', 'command': 'add', 'input': {'object': 'target', 'version': 3000}}]}
        refused = self.call(request)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertTrue('capacity' in refused['data'] or 'tickExhausted' in refused['data'], refused)
        self.assertEqual(self.inspect('index'), current)
        self.assertEqual(self.call(request), refused)


if __name__ == '__main__':
    unittest.main()
