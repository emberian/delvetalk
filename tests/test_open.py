"""`open` writes one bridge row per world, starting nothing (docs/FEDERATION.md section 4); the bridge and `post` of
that world read it.

Evidence for FEDERATION §4 (layer: transport).
"""
import io
import json
import tempfile
import unittest
from pathlib import Path

from transport.__main__ import main
from transport.state import State


class Open(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def open(self, *argv):
        out = io.StringIO()
        return main(['open', '--state', self.tmp.name, *argv], out), out.getvalue()

    def test_bad_names_missing_arguments_and_a_second_open_are_refused_and_write_nothing(self):
        for argv in (['--world', 'scratch', '--transport', 'delve', '--realm', 'p'], ['--world', 'Ring', '--transport', 'delve', '--realm', 'p'],
                     ['--world', 'x' * 33, '--transport', 'delve', '--realm', 'p'], ['--world', 'ring', '--transport', 'zulip', '--realm', 'r']):
            with self.assertRaises(SystemExit):
                self.open(*argv)
        self.assertFalse((Path(self.tmp.name) / 'bridges').exists())
        self.open('--world', 'ring', '--transport', 'delve', '--realm', 'p')
        with self.assertRaises(SystemExit):
            self.open('--world', 'ring', '--transport', 'delve', '--realm', 'q')
        self.assertEqual(State(self.tmp.name, 'ring').bridge()['realm'], 'p')

    def test_a_zulip_row_is_what_the_worlds_bridge_reads_and_a_world_without_one_is_on_delve(self):
        self.assertEqual(self.open('--world', 'ring', '--transport', 'zulip', '--realm', 'tulip.arke.me', '--channel', 'ring',
                                   '--zuliprc', '/rc', '--topic', 'mobo')[0], 0)
        row = State(self.tmp.name, 'ring').bridge()
        self.assertEqual((row['transport'], row['channel'], row['zuliprc'], row['topic']), ('zulip', 'ring', '/rc', 'mobo'))
        self.assertEqual(json.loads((Path(self.tmp.name) / 'bridges' / 'ring.json').read_text()), row)
        self.assertEqual(State(self.tmp.name).bridge(), {'world': 'town', 'transport': 'delve'})


if __name__ == '__main__':
    unittest.main()
