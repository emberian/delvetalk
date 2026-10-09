"""Native row conversion: branch/match parity, lazy evaluation and restricted values."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'conformance/fixtures/checked-rows'
BINARY = Path(os.environ.get('DELVETALK_OBEND_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))


def call(request):
    process = subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
                             text=True, capture_output=True, timeout=30, check=True)
    return json.loads(process.stdout)


class CheckedRows(unittest.TestCase):
    def test_equivalent_rows_in_branches_and_matches(self):
        source = (FIXTURES / 'Rows.obend').read_text()
        for entry, text in [('branchNested', 'new'), ('inherited', 'old'), ('rowOrder', 'three'),
                            ('zero', 'zero'), ('successor', 'successor'), ('second', 'second'),
                            ('third', 'third'), ('nestedResult', 'nested')]:
            with self.subTest(entry=entry):
                compiled = call({'op': 'compile', 'source': source, 'entry': entry})
                self.assertEqual(compiled['status'], 'compiled', compiled)
                result = call({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
                self.assertEqual(result.get('value'), {'tag': 'label', 'value': text}, result)

    def test_lazy_unchosen_branch_and_mutually_recursive_sum(self):
        for entry in ['lazy', 'entry']:
            with self.subTest(entry=entry):
                compiled = call({'op': 'compile', 'source': (FIXTURES / 'Rows.obend').read_text(), 'entry': entry})
                self.assertEqual(compiled['status'], 'compiled', compiled)
                result = call({'op': 'run-data-v1', 'artifact': compiled['artifact'],
                               'arguments': [], 'limits': {'ticks': 1000}})
                self.assertEqual(result['status'], 'finished', result)
                if entry == 'entry':
                    self.assertEqual(result.get('value'), {'tag': 'variant', 'label': 'none',
                                     'payload': {'tag': 'record', 'fields': []}}, result)

    def test_type_mismatch_and_hidden_restricted_values_refuse(self):
        # Each source block is independent: one bad definition must not mask another.
        for source in (FIXTURES / 'Refusals.obend').read_text().split('\n-- fixture boundary --\n'):
            entry = source.split('def ', 1)[1].split('(', 1)[0]
            with self.subTest(entry=entry):
                result = call({'op': 'compile', 'source': source, 'entry': entry})
                self.assertEqual(result['status'], 'error', result)
                self.assertIn('objective-typed-check', result.get('message', ''), result)

    def test_transitive_restricted_closure_capture_refuses(self):
        for quantity in ('affine', 'linear'):
            for value in ('{outer: {call: fn(x: Nat) -> Nat: token}}',
                          'extend({outer: {call: fn(x: Nat) -> Nat: token}}, {outer: {call: fn(x: Nat) -> Nat: x}})'):
                source = ('edition ObjectiveBend 1\ndef nested(' + quantity +
                          ' token: Nat) -> {outer: {call: Nat -> Nat}}:\n  ' + value + '\n')
                result = call({'op': 'compile', 'source': source, 'entry': 'nested'})
                self.assertEqual(result['status'], 'error', result)
                self.assertIn('objective-typed-check', result['message'])

    def test_actual_activity_cannot_be_suspended_in_nested_fields(self):
        prefix = ('edition ObjectiveBend 1\nsum Plan:\n  read: {}\n'
                  'def activity(start: {}) -> Activity<Plan, Nat, Nat>:\n  perform(Plan.read())\n')
        accepted = call({'op': 'compile', 'source': prefix, 'entry': 'activity'})
        self.assertEqual(accepted['status'], 'compiled', accepted)
        for body in ('{outer: {pending: activity(start)}}',
                     'extend({outer: {pending: activity(start)}}, {outer: {pending: activity(start)}})'):
            source = prefix + ('def suspended(start: {}) -> {outer: {pending: Activity<Plan, Nat, Nat>}}:\n  ' + body + '\n')
            refused = call({'op': 'compile', 'source': source, 'entry': 'suspended'})
            self.assertEqual(refused['status'], 'error', refused)


if __name__ == '__main__':
    unittest.main()
