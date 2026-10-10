"""The spend report totals a month of model calls and the grant left.

Evidence for FOUNDATION §6 (layer: transport).
"""
import unittest
from pathlib import Path

from deploy import spend
from transport.delve import canonical


class Spend(unittest.TestCase):
    def test_spend_totals_a_month_at_haiku_rates_and_prints_the_remaining_grant(self):
        import calendar
        import io
        import tempfile
        rows = [(calendar.timegm((2026, 10, 3, 0, 0, 0)), 1_000_000, 200_000), (calendar.timegm((2026, 10, 30, 0, 0, 0)), 500_000, 0),
                (calendar.timegm((2026, 9, 30, 23, 0, 0)), 9_000_000, 9_000_000)]
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'model-spend.jsonl').write_text(''.join(canonical({'at': at, 'inputTokens': i, 'outputTokens': o}) + '\n' for at, i, o in rows))
            out = io.StringIO()
            spend.main(['--state', d, '--month', '2026-10', '--grant', '200'], out)
        text = out.getvalue()
        self.assertIn('2026-10  2 calls  1500000 in  200000 out  $0.2500', text)
        self.assertIn('2026-09  1 calls', text)
        self.assertIn('2026-10: $0.2500 of $200.00 grant spent, $199.7500 remaining', text)


if __name__ == '__main__':
    unittest.main()
