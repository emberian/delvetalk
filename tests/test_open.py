"""deploy/open.py writes one bridge row per world and prints how to start it, starting nothing
(docs/FEDERATION.md section 4).

Evidence for FEDERATION §7 row 3 (layer: transport).
"""
import io
import json
import tempfile
import unittest
from pathlib import Path

from deploy import open as opener


class Open(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)

    def open(self, *argv):
        out = io.StringIO()
        code = opener.main(['--state', str(self.state), *argv], out)
        return code, out.getvalue()


    def test_bad_names_missing_arguments_and_a_second_open_are_refused_and_write_nothing(self):
        for argv in (['--world', 'scratch', '--transport', 'delve', '--realm', 'p'], ['--world', 'Ring', '--transport', 'delve', '--realm', 'p'],
                     ['--world', 'x' * 33, '--transport', 'delve', '--realm', 'p'], ['--world', 'ring', '--transport', 'zulip', '--realm', 'r']):
            with self.assertRaises(SystemExit):
                self.open(*argv)
        self.assertFalse((self.state / 'bridges').exists())
        self.open('--world', 'ring', '--transport', 'delve', '--realm', 'p')
        with self.assertRaises(SystemExit):
            self.open('--world', 'ring', '--transport', 'delve', '--realm', 'q')
        self.assertEqual(json.loads((self.state / 'bridges' / 'ring.json').read_text())['realm'], 'p')


if __name__ == '__main__':
    unittest.main()
