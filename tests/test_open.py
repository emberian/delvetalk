"""deploy/open.py writes one bridge row per world and prints how to start it, starting nothing
(docs/FEDERATION.md section 4).

Evidence for FEDERATION §7 row 3 (layer: transport).
"""
import io
import json
import shlex
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

    def test_a_zulip_world_gets_its_row_and_the_commands_for_its_bridge_and_interpreter_on_serve(self):
        code, out = self.open('--world', 'ring', '--transport', 'zulip', '--realm', 'tulip.arke.me', '--channel', 'ring', '--zuliprc', '/etc/z/ring')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((self.state / 'bridges' / 'ring.json').read_text()),
                         {'world': 'ring', 'transport': 'zulip', 'realm': 'tulip.arke.me', 'channel': 'ring', 'zuliprc': '/etc/z/ring', 'topicMode': 'channel'})
        lines = [shlex.split(l.rstrip(' &')) for l in out.splitlines()[1:]]
        home = str(self.state / 'worlds' / 'ring')
        self.assertEqual([l[2] for l in lines], ['transport.bridge', 'transport.interpret'])  # serve holds every world: no host per world
        on = ['--host-socket', str(self.state / 'host.sock'), '--world', 'ring']
        self.assertEqual(lines[0][4:], ['--state', home, *on, '--source', 'zulip', '--zuliprc', '/etc/z/ring', '--stream', 'ring', '--poll', '60'])
        self.assertEqual(lines[1][4:], ['--state', home, *on, '--poll', '60'])
        self.assertEqual(list((self.state / 'worlds').glob('*')) if (self.state / 'worlds').exists() else [], [])  # nothing started or made

    def test_a_delve_world_observes_its_pds(self):
        self.assertEqual(self.open('--world', 'second-town', '--transport', 'delve', '--realm', 'pds.example')[0], 0)
        r = json.loads((self.state / 'bridges' / 'second-town.json').read_text())
        self.assertEqual((r['transport'], r['realm'], r['zuliprc']), ('delve', 'pds.example', None))

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
