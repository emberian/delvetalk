import json
import tempfile
import unittest
from pathlib import Path

from deploy import genesis
from tests.host import start_hostd, stop_hostd
from tests.test_turn_world import BINARY
from transport.hostproc import LIBRARY, HostClient


class Genesis(unittest.TestCase):
    """One genesis per class: a hostd opened by the opener with the library sealed, then
    deploy/genesis.py's whole sequence."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.hostd = start_hostd(cls.tmp.name, BINARY, opener=genesis.OPENER, library=LIBRARY)
        cls.addClassCleanup(stop_hostd, cls.hostd)
        cls.host = HostClient(Path(cls.tmp.name) / 'host.sock')
        cls.made, cls.refusal = genesis.run(cls.host)

    def test_the_whole_sequence_is_created_once_and_refused_a_second_time(self):
        host, made, refusal = self.host, self.made, self.refusal
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
        made_names = {m['object'] for m in made}
        self.assertEqual([l for l, _, to in genesis.DOORS if to and to not in made_names], [])  # every door with an object resolves
        self.assertEqual([l for l, _, to in genesis.DOORS if not to], ['STUDIO'])
        self.assertEqual([l for l, _, _ in genesis.DOORS], ['GARDEN', 'ROOMS', 'PLAY', 'WORKSHOP', 'TIDE', 'ANTHOLOGY', 'STUDIO'])
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

    @unittest.expectedFailure
    def test_every_door_publishes_its_page_and_the_outbox_holds_a_wiki_draft_each(self):
        # Tide has no publishPage method (Card.publishPage is generic; Tide never instantiates it), so the
        # TIDE door's page is refused "method publishPage does not compile: missing selected entry".
        from transport import bridge
        host, made, tmp = self.host, self.made, self.tmp.name
        pages = {m['object']: m['page']['status'] for m in made if 'page' in m}
        self.assertEqual(pages, {to: 'admitted' for _, _, to in genesis.DOORS if to}, pages)
        drafted, problem = bridge.publication_drafts(tmp, host)
        self.assertIsNone(problem)
        texts = [json.loads(p.read_text())['text'] for p in sorted((Path(tmp) / 'outbox').glob('*.json'))]
        self.assertEqual(len(texts), len([1 for _, _, to in genesis.DOORS if to]))
        self.assertTrue(all(t.startswith('wiki: ') for t in texts), texts)


if __name__ == '__main__':
    unittest.main()
