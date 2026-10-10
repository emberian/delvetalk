import tempfile
import unittest
from pathlib import Path

from deploy import genesis
from tests.host import start_hostd, stop_hostd
from tests.test_turn_world import BINARY
from transport.hostproc import LIBRARY, HostClient


class Genesis(unittest.TestCase):
    def test_the_whole_sequence_is_created_once_and_refused_a_second_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = start_hostd(tmp, BINARY, opener=genesis.OPENER, library=LIBRARY)
            try:
                host = HostClient(Path(tmp) / 'host.sock')
                made, refusal = genesis.run(host)
                self.assertEqual((refusal, [(m['object'], m['status']) for m in made]),
                                 (None, [(n, 'created') for n, _, _ in genesis.seeds(genesis.OPENER)]), made)
                self.assertEqual(sorted(genesis.existing(host, genesis.OPENER)), sorted(n for n, _, _ in genesis.seeds(genesis.OPENER)))
                again, refusal = genesis.run(host)
                self.assertEqual(again, [])
                self.assertIn('already run', refusal)
                self.assertEqual(len(genesis.DOORS), 7)
            finally:
                stop_hostd(d)


if __name__ == '__main__':
    unittest.main()
