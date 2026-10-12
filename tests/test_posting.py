"""A resident who only posts (docs/POSTING.md): every move a reply on the bridge's fake Delve over a genesis town,
the hand posting each draft as `post` does (long ones threaded).

Evidence for docs/POSTING.md (layer: transport).

Refuted by: a reply over the clip posted whole, a reply answering several cards addressed to one of them, or a move
the guide teaches that a poster cannot make.
"""
import tempfile
import unittest

from tests.poster import Poster
from tests.town import Town


class Resident(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.poster = Poster(cls.tmp.name, cls.town.client)

    def test_a_reply_answering_two_cards_is_addressed_to_the_commonplace(self):
        [both] = self.poster.say('delvetalk bell/1 tend\ndelvetalk library read / page: spells')
        self.assertEqual(both['object'], 'commonplace')
        [one] = self.poster.say('delvetalk library read / page: laws')
        self.assertEqual(one['object'], 'library')


    def test_an_indented_spell_among_words_is_a_quotation_and_casts_nothing(self):
        v = self.town.client.send({'op': 'world-view', 'principal': 'anonymous', 'object': 'bell/1'})['version']
        self.assertEqual(self.poster.say('  delvetalk bell/1 tend\nthat is how one tends it'), [])
        self.assertEqual(self.town.client.send({'op': 'world-view', 'principal': 'anonymous', 'object': 'bell/1'})['version'], v)


if __name__ == '__main__':
    unittest.main()
