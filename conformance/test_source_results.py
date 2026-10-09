"""Declared constant aliases and finite variant default arms use checked core."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('DELVETALK_TEXT_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))
NODE = '''edition ObjectiveBend 1
record Node:
  value: Nat
  next: Link
sum Link:
  none: {}
  some: Node
def initial() -> Node:
  {value: 1n, next: Link.some({value: 2n, next: Link.none()})}
def revised() -> Node:
  extend(initial(), {value: 9n})
def read() -> Nat:
  revised().value
'''
CHOICE = '''edition ObjectiveBend 1
sum Choice:
  left: Nat
  middle: String
  right: {}
def choose(choice: Choice, fallback: Nat) -> Nat:
  match choice:
    case left(n): n
    case _: fallback
def entry() -> {left: Nat, middle: Nat, right: Nat}:
  {left: choose(Choice.left(7n), 11n), middle: choose(Choice.middle("moth"), 11n), right: choose(Choice.right(), 11n)}
'''


def call(request):
    return json.loads(subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
        text=True, capture_output=True, check=True, timeout=30).stdout)


class SourceResults(unittest.TestCase):
    def compile(self, source, entry):
        return call({'op': 'compile', 'source': source, 'entry': entry})

    def execute(self, source, entry='entry', limits=None):
        result = self.compile(source, entry)
        self.assertEqual(result['status'], 'compiled', result)
        return call({'op': 'run-data-v1', 'artifact': result['artifact'], 'arguments': [],
                     'limits': limits or {}})

    def test_recursive_nullary_record_alias_without_dummy_argument(self):
        result = self.execute(NODE, 'read')
        self.assertEqual(result.get('value'), {'tag': 'natural', 'value': '9'}, result)

    def test_nullary_wrong_declared_result_still_refuses(self):
        for source in [NODE.replace('value: 1n', 'value: "wrong"'), NODE.replace('def initial() -> Node:', 'def initial() -> Nat:')]:
            result = self.compile(source, 'read')
            self.assertEqual(result['status'], 'error', result)
            self.assertIn('objective-typed-check', result.get('message', ''), result)

    def test_wildcard_covers_each_remaining_payload_type_and_preserves_scope(self):
        result = self.execute(CHOICE)
        fields = {f['name']: f['value'] for f in result['value']['fields']}
        self.assertEqual(fields, {'left': {'tag': 'natural', 'value': '7'},
                                 'middle': {'tag': 'natural', 'value': '11'},
                                 'right': {'tag': 'natural', 'value': '11'}})
        self.assertEqual(self.execute(CHOICE.replace('    case left(n): n\n', ''))['status'], 'finished')

    def test_missing_duplicate_unknown_and_unreachable_arms_refuse(self):
        for source in [CHOICE.replace('    case _: fallback\n', ''),
                       CHOICE.replace('    case _: fallback', '    case left(n): n\n    case _: fallback'),
                       CHOICE.replace('case left(n)', 'case absent(n)'),
                       CHOICE.replace('    case _: fallback', '    case _: fallback\n    case _: fallback'),
                       CHOICE.replace('    case left(n): n\n    case _: fallback', '    case _: fallback\n    case left(n): n')]:
            self.assertEqual(self.compile(source, 'entry')['status'], 'error')

    def test_wildcard_preserves_linear_usage_refusals(self):
        source = CHOICE.split('def choose')[0] + '''def bad(linear token: Nat, choice: Choice) -> Nat:
  match choice:
    case left(n): 0n
    case _: 0n
'''
        # The present core treats both affine and linear as at most one use.
        self.assertEqual(self.compile(source, 'bad')['status'], 'compiled')
        for body in ('token + token', 'token'):
            # Even one reference copied into two remaining arms keeps the core's
            # conservative sum-of-arm use accounting; it cannot gain contraction.
            result = self.compile(source.replace('case _: 0n', 'case _: ' + body), 'bad')
            self.assertEqual(result['status'], 'error', result)
            self.assertIn('objective-typed-check', result.get('message', ''), result)

    def test_constant_sharing_and_lazy_unused_constant(self):
        source = '''edition ObjectiveBend 1
def spin() -> Nat:
  spin()
def expensive() -> String:
  sha256Text("''' + 'x' * 10000 + '''")
def callable(start: {}) -> String:
  sha256Text("''' + 'x' * 10000 + '''")
def shared() -> {first: String, second: String}:
  {first: expensive(), second: expensive()}
def calls() -> {first: String, second: String}:
  {first: callable({}), second: callable({})}
def unused() -> Nat:
  if true then 7n else spin()
'''
        self.assertEqual(self.execute(source, 'shared', {'ticks': 10000})['status'], 'finished')
        self.assertEqual(self.execute(source, 'calls', {'ticks': 10000})['status'], 'refused')
        self.assertEqual(self.execute(source, 'unused', {'ticks': 100})['value'], {'tag': 'natural', 'value': '7'})


if __name__ == '__main__': unittest.main()
