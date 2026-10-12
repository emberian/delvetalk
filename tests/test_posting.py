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


    def test_a_receipt_is_looked_up_by_post_and_one_typed_by_hand_does_not_resolve(self):
        [tended] = self.poster.say('delvetalk bell/1 tend')
        slug = tended['receipt']['slug']
        [found] = self.poster.say(f'delvetalk receipt / of: {slug}')
        self.assertIn(f'receipt {slug}', found['text'])
        self.assertIn('admitted bell/1', found['text'])
        [mine] = self.poster.say(f"delvetalk receipt / of: {tended['replyTo']}")
        self.assertIn(f'receipt {slug}', mine['text'])
        [typed] = self.poster.say('delvetalk receipt / of: lusab-babad')
        self.assertEqual(typed['text'], 'no receipt here is named lusab-babad: no host issued it, so it records nothing\n')
        made = self.town.client.send({'op': 'world-create', 'principal': self.poster.did, 'identity': 'mk-receipt', 'object': 'receipt', 'modules': [], 'entry': 'initial'})
        self.assertNotEqual(made.get('status'), 'created', made)


if __name__ == '__main__':
    unittest.main()
