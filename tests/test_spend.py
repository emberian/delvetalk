"""`hand spend` totals the model's calls by month and reports the grant left.

Evidence for FOUNDATION §6 (layer: transport).
"""
import calendar
import io
import json
import tempfile
import unittest

from transport.__main__ import main
from transport.delve import canonical
from transport.state import State


class Spend(unittest.TestCase):
    def test_spend_totals_a_month_at_haiku_rates_and_reports_the_remaining_grant(self):
        rows = [(calendar.timegm((2026, 10, 3, 0, 0, 0)), 1_000_000, 200_000), (calendar.timegm((2026, 10, 30, 0, 0, 0)), 500_000, 0),
                (calendar.timegm((2026, 9, 30, 23, 0, 0)), 9_000_000, 9_000_000)]
        with tempfile.TemporaryDirectory() as d:
            State(d).spend.write_text(''.join(canonical({'at': at, 'world': 'town', 'inputTokens': i, 'outputTokens': o}) + '\n' for at, i, o in rows))
            out = io.StringIO()
            self.assertEqual(main(['hand', 'spend', '--state', d, '--month', '2026-10', '--json'], out), 0)
        got = json.loads(out.getvalue())
        self.assertEqual(got['months']['2026-10'], {'calls': 2, 'inputTokens': 1_500_000, 'outputTokens': 200_000, 'dollars': 0.25})
        self.assertEqual(got['months']['2026-09']['calls'], 1)
        self.assertTrue(got['2026-10'].startswith('$0.2500 of $200.00 grant spent, $199.7500 remaining'), got)


if __name__ == '__main__':
    unittest.main()
