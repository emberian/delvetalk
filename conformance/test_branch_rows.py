"""Source conditionals agree on canonical rows without changing core conversion."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / '.lake/build/bin/delvetalk-obend'
SOURCE = '''edition ObjectiveBend 1
record State:
  a: String
  b: String
record Decision:
  state: State
def revise(s: State, choose: Bool) -> Decision:
  if choose then {state: s} else {state: extend(s, {b: "new"})}
def forever() -> State:
  forever()
def lazy() -> State:
  if true then {b: "kept", a: "safe"} else extend(forever(), {b: "unused"})
def nested() -> String:
  revise({a: "old", b: "old"}, false).state.b
def inherited() -> String:
  revise({a: "old", b: "old"}, true).state.b
def rowOrder() -> String:
  let row = if false then {a: "one", b: "two"} else {b: "four", a: "three"} in row.a
'''


def call(request):
    return json.loads(subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
        text=True, capture_output=True, timeout=20, check=True).stdout)


class BranchRows(unittest.TestCase):
    def test_extended_nested_rows_reordered_rows_and_lazy_unchosen_branch(self):
        for entry, expected in [('nested', 'new'), ('inherited', 'old'), ('rowOrder', 'three')]:
            result = call({'op': 'compile', 'source': SOURCE, 'entry': entry})
            self.assertEqual(result['status'], 'compiled', result)
            run = call({'op': 'run', 'artifact': result['artifact'], 'arguments': []})
            self.assertEqual(run.get('value'), {'tag': 'label', 'value': expected}, run)
        result = call({'op': 'compile', 'source': SOURCE, 'entry': 'lazy'})
        self.assertEqual(result['status'], 'compiled', result)
        run = call({'op': 'run', 'artifact': result['artifact'], 'arguments': [], 'limits': {'ticks': 1000}})
        self.assertEqual(run['status'], 'finished', run)

    def test_mutually_recursive_sum_match_keeps_declared_result(self):
        source = """edition ObjectiveBend 1
sum V:
  none: {}
  list: {values: L}
sum L:
  nil: {}
  cons: {head: V, tail: L}
def find(xs: L) -> V:
  match xs:
    case nil(_): V.none()
    case cons(c): if true then c.head else find(c.tail)
def entry() -> V:
  find(L.cons({head: V.none(), tail: L.nil()}))
"""
        compiled = call({'op': 'compile', 'source': source, 'entry': 'entry'})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        result = call({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertEqual(result.get('value'), {'tag': 'variant', 'label': 'none',
            'payload': {'tag': 'record', 'fields': []}}, result)

    def test_real_type_mismatch_and_restricted_value_smuggling_refuse(self):
        sources = [
            SOURCE.replace('extend(s, {b: "new"})', 'extend(s, {b: 7n})'),
            '''edition ObjectiveBend 1
def bad(affine n: Nat) -> {x: Nat}:
  if true then {x: 1n} else extend({x: fn(u: Nat) -> Nat: n}, {x: 1n})
''',
            '''edition ObjectiveBend 1
def bad(affine n: Nat) -> Nat:
  if true then n else n
''']
        for source in sources:
            result = call({'op': 'compile', 'source': source, 'entry': 'bad' if 'def bad' in source else 'nested'})
            self.assertEqual(result['status'], 'error', result)
            self.assertIn('objective-typed-check', result.get('message', ''), result)


if __name__ == '__main__': unittest.main()
