#!/usr/bin/env python3
"""Checked recursive-data boundary, using the actual source compiler and machine."""
import copy
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / '.lake/build/bin/delvetalk-obend'
SOURCE = '''edition ObjectiveBend 1
sum List:
  nil: {}
  cons: {head: Nat, tail: List}
sum Option:
  none: {}
  some: List
record State:
  items: List
  selected: Option
def empty() -> List:
  List.nil()
def identity(xs: List) -> List:
  xs
def total(xs: List) -> Nat:
  match xs:
    case nil(_): 0n
    case cons(c): c.head + total(c.tail)
def push(xs: List, n: Nat) -> List:
  List.cons({head: n, tail: xs})
def state(s: State) -> State:
  s
def forever() -> List:
  List.cons({head: 1n, tail: forever()})
def namedTags(x: {tag: String, label: String}) -> {tag: String, label: String}:
  x
'''


def record(**fields):
    return {'tag': 'record', 'fields': [{'name': k, 'value': v} for k, v in fields.items()]}


def variant(label, payload):
    return {'tag': 'variant', 'label': label, 'payload': payload}


def natural(n):
    return {'tag': 'natural', 'value': str(n)}


def list_value(*numbers):
    value = variant('nil', record())
    for n in reversed(numbers):
        value = variant('cons', record(head=natural(n), tail=value))
    return value


def call(request):
    result = subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
                            text=True, capture_output=True, timeout=15, check=True)
    return json.loads(result.stdout)


class CollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = {}
        for entry in ('empty', 'identity', 'total', 'push', 'state', 'forever', 'namedTags'):
            result = call({'op': 'compile', 'source': SOURCE, 'entry': entry})
            if result.get('status') != 'compiled':
                raise AssertionError(result)
            cls.artifacts[entry] = result['artifact']

    def run_data(self, entry, arguments=(), **limits):
        return call({'op': 'run-data-v1', 'artifact': self.artifacts[entry],
                     'arguments': list(arguments), 'limits': limits})

    def compare(self, left, right, left_path=(), right_path=(), **extra):
        return call({'op': 'compare-data-types-v1',
                     'left': {'artifact': left, 'path': list(left_path)},
                     'right': {'artifact': right, 'path': list(right_path)}, **extra})

    def test_recursive_lists_traverse_append_and_roundtrip(self):
        self.assertEqual(self.run_data('empty')['value'], list_value())
        for numbers in ((), (7,), (2, 3, 5)):
            value = list_value(*numbers)
            result = self.run_data('identity', [value])
            self.assertEqual(result['status'], 'finished', result)
            self.assertEqual(result['executionProfile'], 'delvetalk-package-data-v1')
            self.assertEqual(result['value'], value)
            self.assertGreater(result['conversionNodes'], 0)
            self.assertEqual(self.run_data('total', [value])['value'], natural(sum(numbers)))
        self.assertEqual(self.run_data('push', [list_value(2, 3), natural(1)])['value'], list_value(1, 2, 3))

    def test_nested_options_records_and_ordinary_tag_fields(self):
        for selection in (variant('none', record()), variant('some', list_value(9))):
            value = record(items=list_value(1, 2), selected=selection)
            result = self.run_data('state', [value])
            self.assertEqual(result['value'], value, result)
        ordinary = record(tag={'tag': 'label', 'value': 'variant'},
                          label={'tag': 'label', 'value': 'not a constructor'})
        self.assertEqual(self.run_data('namedTags', [ordinary])['value'], ordinary)

    def test_wrong_constructor_payload_and_record_shape_refuse(self):
        duplicate = record(head=natural(1), tail=list_value())
        duplicate['fields'].append(copy.deepcopy(duplicate['fields'][0]))
        bad = [variant('missing', record()), variant('cons', natural(1)),
               variant('cons', record(head=natural(1), tail=natural(2))),
               variant('cons', record(head=natural(1))),
               variant('cons', record(head=natural(1), tail=list_value(), extra=natural(4))),
               variant('cons', duplicate),
               {**list_value(), 'hidden': 'unknown'},
               {'tag': 'natural', 'value': '01'}]
        for value in bad:
            with self.subTest(value=value):
                self.assertEqual(self.run_data('identity', [value])['status'], 'error')

    def test_forged_artifact_never_reaches_new_route(self):
        forged = copy.deepcopy(self.artifacts['identity'])
        forged['packet']['term'] = {'tag': 'nat', 'value': '999'}
        result = call({'op': 'run-data-v1', 'artifact': forged, 'arguments': [list_value()]})
        self.assertIn('recompilation', result['message'])
        result = self.compare(forged, self.artifacts['empty'], ['domain'])
        self.assertIn('recompilation', result['message'])

    def test_old_fragment_and_artifacts_keep_their_meaning(self):
        again = call({'op': 'compile', 'source': SOURCE, 'entry': 'identity'})['artifact']
        self.assertEqual(again, self.artifacts['identity'])
        old = call({'op': 'run', 'artifact': again, 'arguments': [list_value()]})
        self.assertIn('variant arguments', old['message'])
        old = call({'op': 'run', 'artifact': self.artifacts['empty'], 'arguments': []})
        self.assertIn('first-order data', old['message'])

    def test_shared_capacity_and_infinite_value_refuse(self):
        result = self.run_data('identity', [list_value(1, 2, 3)], work=1)
        self.assertIn('work capacity', result['message'])
        result = self.run_data('identity', [list_value(1, 2, 3)], ticks=1)
        self.assertIn('work capacity', result['message'])
        result = self.run_data('forever', ticks=1000, nodes=20)
        self.assertEqual(result['status'], 'refused', result)
        result = self.run_data('identity', [list_value(1, 2, 3)], ticks=1000)
        self.assertEqual(result['status'], 'finished', result)
        self.assertLessEqual(result['ticksUsed'] + result['conversionNodes'], 1000)

    def test_unused_executable_alternative_refuses(self):
        source = '''edition ObjectiveBend 1
sum Hidden:
  empty: {}
  callable: {run(n: Nat) -> Nat}
def empty() -> Hidden:
  Hidden.empty()
'''
        compiled = call({'op': 'compile', 'source': source, 'entry': 'empty'})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        result = call({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertIn('not serializable', result['message'])

    def test_ignored_scalar_input_has_an_explicit_byte_bound(self):
        source = 'edition ObjectiveBend 1\ndef ignore(x: String) -> Nat:\n  0n\n'
        compiled = call({'op': 'compile', 'source': source, 'entry': 'ignore'})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        arguments = [{'tag': 'label', 'value': 'x' * 100000}]
        request = {'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': arguments,
                   'limits': {'bytes': 4, 'work': 30, 'ticks': 100}}
        result = call(request)
        self.assertIn('input byte capacity', result['message'])
        request['limits']['inputBytes'] = 200000
        result = call(request)
        self.assertEqual(result['status'], 'finished', result)
        self.assertEqual(result['value'], natural(0))
        self.assertLessEqual(result['ticksUsed'] + result['conversionNodes'], 100)
        # Count UTF-8 bytes rather than characters, and cover exact inclusive bound.
        request['arguments'] = [{'tag': 'label', 'value': '🌙'}]
        size = len(json.dumps(request['arguments'], ensure_ascii=False, separators=(',', ':')).encode())
        request['limits']['inputBytes'] = size
        self.assertEqual(call(request)['status'], 'finished')
        request['limits']['inputBytes'] = size - 1
        self.assertIn('input byte capacity', call(request)['message'])

    def test_reordered_rows_and_recursive_alternatives_compare_equal(self):
        left_source = '''edition ObjectiveBend 1
record Pair:
  a: Nat
  b: Bool
sum Chain:
  nil: {}
  cons: {head: Pair, tail: Chain}
def empty() -> Chain:
  Chain.nil()
'''
        right_source = left_source.replace('  a: Nat\n  b: Bool', '  b: Bool\n  a: Nat').replace(
            '  nil: {}\n  cons: {head: Pair, tail: Chain}',
            '  cons: {tail: Chain, head: Pair}\n  nil: {}')
        artifacts = []
        for source in (left_source, right_source):
            compiled = call({'op': 'compile', 'source': source, 'entry': 'empty'})
            self.assertEqual(compiled['status'], 'compiled', compiled)
            artifacts.append(compiled['artifact'])
        result = self.compare(*artifacts)
        self.assertEqual(result.get('equal'), True, result)
        # A reordered but different member still fails comparison.
        changed = call({'op': 'compile', 'source': right_source.replace('b: Bool', 'b: String'), 'entry': 'empty'})
        self.assertEqual(changed['status'], 'compiled', changed)
        self.assertFalse(self.compare(artifacts[0], changed['artifact'])['equal'])

    def test_schema_comparison_is_alias_independent_and_exact(self):
        renamed = SOURCE.replace('List', 'Chain').replace('edition ObjectiveBend 1\n',
            'edition ObjectiveBend 1\nsum Extra:\n  stop: {}\n  more: Extra\n'
            'def extra() -> Extra:\n  Extra.stop()\n')
        other = call({'op': 'compile', 'source': renamed, 'entry': 'empty'})['artifact']
        self.assertNotEqual(self.artifacts['empty']['type'], other['type'])
        result = self.compare(self.artifacts['identity'], other, ['domain'])
        self.assertEqual(result.get('equal'), True, result)
        result = self.compare(self.artifacts['state'], other, ['domain', {'field': 'items'}])
        self.assertEqual(result.get('equal'), True, result)
        changed = '''edition ObjectiveBend 1
sum Chain:
  nil: {}
  cons: {head: String, tail: Chain}
def empty() -> Chain:
  Chain.nil()
'''
        compiled = call({'op': 'compile', 'source': changed, 'entry': 'empty'})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        other = compiled['artifact']
        self.assertFalse(self.compare(self.artifacts['empty'], other)['equal'])
        result = self.compare(self.artifacts['empty'], self.artifacts['empty'], work=1)
        self.assertIn('work capacity', result['message'])
        result = self.compare(self.artifacts['empty'], self.artifacts['empty'], ['domain'])
        self.assertIn('requires an arrow', result['message'])


if __name__ == '__main__':
    unittest.main()
