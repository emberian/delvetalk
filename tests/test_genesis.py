import json
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
                o = genesis.OPENER
                self.assertEqual(sorted(genesis.existing(host, o)), sorted([n for n, _, _ in genesis.seeds(o)] + [o, 'env/' + o, 'wake/' + o]))
                # the opener arrived first: another reader sees their handle, not a DID fragment
                avatar = host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': o})
                self.assertIn('ember.delve.town is at', json.dumps(avatar))
                again, refusal = genesis.run(host)
                self.assertEqual(again, [])
                self.assertIn('already run', refusal)
                self.assertEqual((len(genesis.DOORS), len(genesis.seeds(genesis.OPENER))), (7, 10))
                said = {}
                for word in ('ROOMS', 'PLAY', 'STUDIO'):
                    got = host.send({'op': 'world-turn', 'principal': 'did:plc:stranger', 'object': 'directory', 'method': 'receive',
                                     'argument': genesis.rec(text=genesis.lab(word), post=genesis.lab('at://x/p/' + word), slot=genesis.lab('')),
                                     'identity': 'door-' + word})
                    self.assertEqual(got['status'], 'admitted', got)
                    said[word] = got['offers'][0]['text']
                self.assertTrue(said['ROOMS'].startswith('SCENE The Moss Gate'), said)
                self.assertTrue(said['PLAY'].startswith('AUTOMATAFL, round 0'), said)
                # The link door has no object: naming it reaches Plan.card on the empty reference (the Directory answers
                # "The door to  opens on nothing yet."), so only the menu carries its URL.
                menu = host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'directory'})['text']
                self.assertIn('https://delvetalk.fg-goose.online/AGENTS.md', menu)
            finally:
                stop_hostd(d)


if __name__ == '__main__':
    unittest.main()
