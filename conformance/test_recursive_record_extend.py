"""Concrete recursive record updates preserve lazy sharing and checked usage."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('DELVETALK_TEXT_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))
SOURCE = '''edition ObjectiveBend 1
record Node:
  value: Nat
  next: Link
sum Link:
  none: {}
  some: Node
def revise(node: Node) -> Node:
  extend(node, {value: 9n})
def initial(start: {}) -> Node:
  {value: 1n, next: Link.some({value: 2n, next: Link.none()})}
def tailValue(link: Link) -> Nat:
  match link:
    case none(_): 0n
    case some(node): node.value
def updated() -> {value: Nat, tail: Nat}:
  let node = revise(initial({}))
  {value: node.value, tail: tailValue(node.next)}
def loop() -> Node:
  loop()
def lazyBase() -> Nat:
  extend(loop(), {value: 7n}).value
def lazyOverride() -> Nat:
  tailValue(extend(initial({}), {value: loop().value}).next)
''' 


def call(request):
    return json.loads(subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
        text=True, capture_output=True, timeout=30, check=True).stdout)


def compile_source(source, entry):
    return call({'op': 'compile', 'source': source, 'entry': entry})


class RecursiveRecordExtend(unittest.TestCase):
    def run_entry(self, entry, source=SOURCE, limits=None):
        compiled = compile_source(source, entry)
        self.assertEqual(compiled['status'], 'compiled', compiled)
        request = {'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []}
        if limits is not None:
            request['limits'] = limits
        return call(request)

    def test_recursive_update_preserves_link_and_resolves_let_type(self):
        result = self.run_entry('updated')
        self.assertEqual(result.get('value', {}).get('tag'), 'record', result)
        fields = {field['name']: field['value'] for field in result['value']['fields']}
        self.assertEqual(fields, {'value': {'tag': 'natural', 'value': '9'},
                                 'tail': {'tag': 'natural', 'value': '2'}}, result)

    def test_overridden_base_and_unused_override_stay_lazy(self):
        for entry, expected in [('lazyBase', '7'), ('lazyOverride', '2')]:
            result = self.run_entry(entry)
            self.assertEqual(result.get('value'), {'tag': 'natural', 'value': expected}, result)

    def test_demanded_inherited_divergence_refuses(self):
        source = SOURCE + '\ndef demand() -> Nat:\n  tailValue(extend(loop(), {value: 7n}).next)\n'
        result = self.run_entry('demand', source, {'ticks': 1000, 'work': 1000})
        self.assertEqual(result.get('status'), 'refused', result)

    def test_extension_can_change_or_add_field_with_explicit_result_type(self):
        source = SOURCE + '''
def changed() -> {value: String, next: Link, note: Bool}:
  extend(initial({}), {value: "changed", note: true})
def readChanged() -> String:
  changed().value
'''
        result = self.run_entry('readChanged', source)
        self.assertEqual(result.get('value'), {'tag': 'label', 'value': 'changed'}, result)

    def test_wrong_field_types_and_affine_bases_remain_rejected(self):
        for source in [SOURCE.replace('{value: 9n}', '{value: "wrong"}'), SOURCE + '''
def bad(affine node: Node) -> Node:
  extend(node, {value: 8n})
''', SOURCE + '''
def captured(affine token: Nat) -> Node:
  {value: token, next: Link.none()}
def bad(affine token: Nat) -> Node:
  extend(captured(token), {value: 8n})
''']:
            result = compile_source(source, 'bad' if 'def bad' in source else 'updated')
            self.assertEqual(result['status'], 'error', result)
            self.assertIn('objective-typed-check', result.get('message', ''), result)


if __name__ == '__main__':
    unittest.main()
