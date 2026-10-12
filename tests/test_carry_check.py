"""deploy/carry-check.sh answers what serve will do with the newest backup: "green" only when the candidate replays it
under the library the candidate's image seals, since serve compares that library with the one the journal sealed at
its start and refuses a world whose bytes differ; a replay under another library is "green, breaking: the deploy must
carry". deploy/verify.sh --library seals a tree's world/lib as serve does (its files and ../objects/Avatar.obend).

Evidence for docs/DEPLOY.md "Before a merge that touches the host" (layer: ops). Refuted by a carry-check that answers
plain green for a candidate whose world/lib differs from the sealed one (the deploy of b1fbdded: carry-check said
"replays and carries" and serve refused "the bytes differ"), or by verify.sh --library refusing the very library serve
sealed.

    python3 -W error -m unittest tests.test_carry_check -v
"""
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from tests.host import binary
from tests.town import Town
from transport.config import LIBRARY

DEPLOY = Path(__file__).resolve().parent.parent / 'deploy'


class CarryCheck(unittest.TestCase):
    independent = True  # each test reads the class's backup and never writes it: tests/run.py may run them apart

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = Path(tmp.name)
        cls.data = cls.tmp / 'v1'
        town = Town(str(cls.data), cleanup=cls.addClassCleanup, furnished=False)  # a genesis, as production begins
        cls.height = town.send(op='world-status')['height']
        town.close()
        cls.verify(['--snapshot'], cls.data)  # what backup.sh writes into every tarball: the head snapshot a carry reads
        cls.backup = cls.tmp / 'delvetalk-20261012T000000Z.tar.gz'
        with tarfile.open(cls.backup, 'w:gz') as t:
            t.add(cls.data / 'state', arcname='state')
        # Another tree's world/: the same packages, one library file's bytes changed (a comment).
        cls.other = cls.tmp / 'other' / 'world'
        shutil.copytree(Path(LIBRARY).parent, cls.other)
        with open(cls.other / 'lib' / 'Text.obend', 'a') as f:
            f.write('# a byte the journal never sealed\n')

    @staticmethod
    def verify(flags, data):
        return subprocess.run(['bash', str(DEPLOY / 'verify.sh'), *flags, '--binary', binary(), str(data)], capture_output=True, text=True, timeout=600)

    def check(self, *flags):
        return subprocess.run(['bash', str(DEPLOY / 'carry-check.sh'), *flags, binary(), str(self.backup)], capture_output=True, text=True, timeout=900)

    def test_verify_seals_a_library_as_serve_does_and_refuses_another(self):
        self.assertGreater(self.height, 0)
        same = self.verify(['--full', '--library', LIBRARY], self.data)
        self.assertEqual(same.returncode, 0, same.stderr)
        self.assertIn('"status":"opened"', same.stdout)
        other = self.verify(['--full', '--library', str(self.other / 'lib')], self.data)
        self.assertEqual(other.returncode, 1, other.stdout)
        self.assertIn('the bytes differ', other.stderr)

    def test_carry_check_is_green_only_under_the_sealed_library(self):
        same = self.check()
        self.assertEqual(same.returncode, 0, same.stderr)
        self.assertIn('carry-check: green: the backup replays under this binary and its library, and carries', same.stdout)
        other = self.check('--library', str(self.other / 'lib'))
        self.assertEqual(other.returncode, 0, other.stderr)
        self.assertIn('carry-check: green, breaking: the deploy must carry: the backup replays under this binary, but library at', other.stdout)
        self.assertIn('the bytes differ', other.stdout)
        self.assertNotIn('carry-check: green: the backup replays', other.stdout)


if __name__ == '__main__':
    unittest.main()
