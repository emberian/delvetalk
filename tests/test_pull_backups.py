"""deploy/pull-backups.sh keeps the pulled tarballs 7/56/forever (docs/OPERATIONS.md section b): every tarball a week,
the first of each day eight weeks, the first of each month always; the rest, and their checksums, go.

Evidence for OPERATIONS section b (layer: transport).
"""
import datetime
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / 'deploy' / 'pull-backups.sh'


class Retention(unittest.TestCase):
    def test_seven_days_whole_eight_weeks_daily_and_months_forever(self):
        now = datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)
        name = lambda t: f"delvetalk-{t.strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
        made = {}
        for days in (0, 3, 10, 40, 100, 400):
            for hours in (12, 6):  # two a day: the earlier is the day's first
                t = now - datetime.timedelta(days=days, hours=hours)
                made[(days, hours)] = name(t)
        with tempfile.TemporaryDirectory() as d:
            for n in made.values():
                (Path(d) / n).write_bytes(b'x')
                (Path(d) / (n + '.sha256')).write_text('x')
            subprocess.run(['bash', str(SCRIPT), '--keep-only', d], check=True, capture_output=True)
            kept = {p.name for p in Path(d).glob('*.tar.gz')}
            self.assertEqual({k for k, n in made.items() if n in kept} >= {(0, 12), (0, 6), (3, 12), (3, 6), (10, 12), (40, 12)}, True)
            self.assertNotIn(made[(10, 6)], kept)  # past a week, not the day's first
            self.assertNotIn(made[(100, 6)], kept)
            for days in (100, 400):  # past eight weeks only a month's first stays
                first_of_month = min((n for (dd, h), n in made.items() if n[10:16] == made[(days, 12)][10:16]))
                self.assertEqual(made[(days, 12)] in kept, made[(days, 12)] == first_of_month)
            self.assertEqual({p.name[:-7] for p in Path(d).glob('*.sha256')}, kept)


if __name__ == '__main__':
    unittest.main()
