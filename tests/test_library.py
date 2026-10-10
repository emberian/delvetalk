"""The library (docs/LIBRARY.md): genesis shelves the pages of capsules/pages/ as the opener; anyone reads a
page by its name or by a word of what they said, a card's law with its readings; only the owner shelves.

Evidence for LIBRARY (a), (e) (layer: transport). Refuted by a page over the clip, a page not starting with
hob's line, a page that is not its file, a "next" pointing at no page, or a stranger's shelve admitted.
"""
import tempfile
import unittest
from pathlib import Path

from deploy import genesis
from tests.host import start_hostd, stop_hostd
from tests.test_turn_world import BINARY
from transport.hostproc import LIBRARY, HostClient


class Library(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.hostd = start_hostd(cls.tmp.name, BINARY, opener=genesis.OPENER, library=LIBRARY)
        cls.addClassCleanup(stop_hostd, cls.hostd)
        cls.host = HostClient(Path(cls.tmp.name) / 'host.sock')
        cls.made, cls.refusal = genesis.run(cls.host)
        cls.n = 0

    def spell(self, text, who='did:plc:stranger'):
        type(self).n += 1
        got = self.host.send({'op': 'world-turn', 'principal': who, 'object': 'library', 'method': 'receive', 'identity': 'lib-%d' % self.n,
                              'argument': genesis.rec(text=genesis.lab(text), post=genesis.lab('at://x/p/%d' % self.n))})
        return got

    def offer(self, got):
        self.assertEqual(got['status'], 'admitted', got)
        return got['offers'][0]['text']


    def test_a_page_is_found_by_a_word_and_a_miss_names_the_pages(self):
        self.assertEqual(self.offer(self.spell('delvetalk library read / page: how do i read laws?')), genesis.page_body('laws'))
        miss = self.offer(self.spell('delvetalk library read / page: dragons'))
        self.assertTrue(miss.startswith('hob: no page called dragons. Pages: spells laws object relations protocol world; walks: .\n\nhob: six pages'), miss)


    def test_only_the_owner_shelves(self):
        got = self.spell('delvetalk library shelve / name: mine / kind: page / title: t / body: hob: mine')
        self.assertTrue(self.offer(got).startswith('Not done: Only ember.delve.town shelves a page'), got)
        self.assertNotIn('mine', self.host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'library'})['text'])


if __name__ == '__main__':
    unittest.main()
