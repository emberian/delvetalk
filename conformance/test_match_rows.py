"""Natural and sum match results use existing checked row conversion."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / '.lake/build/bin/delvetalk-obend'
SOURCE = '''edition ObjectiveBend 1
record Row:
  a: String
  b: String
sum Choice:
  first: {}
  second: {}
  third: {}
def natural(n: Nat) -> Row:
  match n:
    case 0: {a: "zero", b: "kept"}
    case 1+k: {b: "kept", a: "successor"}
def choice(tag: Choice) -> Row:
  match tag:
    case first(_): {a: "first", b: "kept"}
    case second(_): extend({a: "old", b: "kept"}, {a: "second"})
    case third(_): {b: "kept", a: "third"}
def nested(n: Nat) -> {row: Row}:
  match n:
    case 0: {row: {a: "zero", b: "kept"}}
    case 1+k: {row: {b: "kept", a: "nested"}}
def zero() -> String:
  natural(0n).a
def successor() -> String:
  natural(3n).a
def second() -> String:
  choice(Choice.second()).a
def third() -> String:
  choice(Choice.third()).a
def nestedResult() -> String:
  nested(2n).row.a
'''


def call(request):
    return json.loads(subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
        text=True, capture_output=True, timeout=30, check=True).stdout)


class MatchRows(unittest.TestCase):
    def test_equivalent_row_order_and_extensions_run_in_every_match_form(self):
        for entry, text in [('zero', 'zero'), ('successor', 'successor'), ('second', 'second'),
                            ('third', 'third'), ('nestedResult', 'nested')]:
            compiled = call({'op': 'compile', 'source': SOURCE, 'entry': entry})
            self.assertEqual(compiled['status'], 'compiled', compiled)
            result = call({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
            self.assertEqual(result.get('value'), {'tag': 'label', 'value': text}, result)

    def test_incompatible_results_and_hidden_restricted_closures_refuse(self):
        bad = [SOURCE.replace('a: "successor"', 'a: 7n'), SOURCE.replace('a: "third"', 'a: 7n')]
        for arms in ['''  match n:
    case 0: {x: 1n}
    case 1+k: extend({x: fn(u: Nat) -> Nat: token}, {x: 1n})
''', '''  match n == 0n:
    case true: {x: 1n}
    case false: extend({x: fn(u: Nat) -> Nat: token}, {x: 1n})
''', '''  match tag:
    case left(_): {x: 1n}
    case right(_): extend({x: fn(u: Nat) -> Nat: token}, {x: 1n})
''']:
            bad.append('''edition ObjectiveBend 1
sum Choice:
  left: {}
  right: {}
def bad(affine token: Nat, n: Nat, tag: Choice) -> {x: Nat}:
''' + arms)
        for source in bad:
            compiled = call({'op': 'compile', 'source': source, 'entry': 'bad' if 'def bad' in source else 'zero'})
            self.assertEqual(compiled['status'], 'error', compiled)
            self.assertIn('objective-typed-check', compiled.get('message', ''), compiled)


if __name__ == '__main__': unittest.main()
