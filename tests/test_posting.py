"""A resident who only posts (docs/POSTING.md): every move a reply on the bridge's fake Delve over a genesis town,
the hand posting each draft as `post` does (long ones threaded).

Evidence for docs/POSTING.md (layer: transport).

Refuted by: a reply over the clip posted whole, a reply answering several cards addressed to one of them, or a move
the guide teaches that a poster cannot make.
"""
import tempfile
import unittest
from unittest import mock

from deploy import genesis
from tests.poster import Poster
from transport import interpret, post
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


    def test_the_guide_is_its_contents_by_post_and_every_part_is_the_webs_text(self):
        pages = genesis.guide_pages()
        [contents] = self.poster.say('delvetalk guide')
        self.assertEqual(contents['object'], 'library')
        self.assertIn(pages[0][3], contents['text'])  # the library's paint may stand above it
        bodies = []
        for name, _, _, body in pages[1:]:
            [part] = self.poster.say(f'delvetalk library read / page: {name}')
            self.assertIn(body, part['text'], name)
            self.assertLessEqual(len(part['text']), post.CLIP, name)
            bodies.append('\n'.join(body.splitlines()[1:-1]))
        joined = ' '.join(' '.join(bodies).split())
        self.assertEqual(joined, ' '.join(genesis.guide_text().split()))  # the same text the front serves, cut at its sections
        [index] = self.poster.say('delvetalk library read / page: library')
        self.assertNotIn('guide-2', index['text'])

    def test_every_page_and_walk_answers_a_post_within_the_clip(self):
        for name, _, _, body in genesis.shelf():
            if '-' in name:
                continue
            [read] = self.poster.say(f'delvetalk library read / page: {name}')
            self.assertIn(body.rstrip('\n'), read['text'], name)
            self.assertTrue(all(len(p) <= post.CLIP for p in post.parts(read['text'])), name)


    def test_a_reply_carries_the_things_verified_paint_above_its_exact_card(self):
        host = self.town.client
        host.send({'op': 'world-renders'})  # a worker attends
        asked = host.send({'op': 'world-render', 'principal': 'anonymous', 'object': 'library'})
        self.assertIn(asked['status'], ('pending', 'painted'), asked)
        paint = 'A shelf of pages under a lamp, each one ending on the next to read.'
        reply = lambda req: {'status': 'replied', 'raw': paint, 'model': 'claude-haiku-5-5', 'usage': {'input_tokens': 1, 'output_tokens': 1}}  # noqa: E731
        interpret.paint(host, reply)
        self.assertEqual(host.send({'op': 'world-render', 'principal': 'anonymous', 'object': 'library'}).get('text'), paint)
        [read] = self.poster.say('delvetalk library read / page: laws')
        self.assertTrue(read['text'].startswith(paint + '\n\nhob:'), read['text'][:200])
        self.assertLessEqual(len(read['text']), post.CLIP)


    def test_entering_a_place_by_post_tells_what_happened_there_above_the_reply(self):
        host = self.town.client
        self.poster.say('delvetalk porch ?')  # the poster has arrived
        host.send({'op': 'world-renders'})  # a worker attends: the bridge waits the host's patience for it
        told = 'The porch was swept and quiet, its lamp lit over the step.'
        model = lambda req: {'status': 'replied', 'raw': told if 'a telling of porch' in req['user'][:80] else 'A plain thing.',  # noqa: E731
                             'model': 'claude-haiku-5-5', 'usage': {'input_tokens': 1, 'output_tokens': 1}}
        with mock.patch('transport.bridge.time.sleep', lambda _: interpret.paint(host, model)):  # the worker paints while the bridge waits
            [entered] = self.poster.say('delvetalk porch enter')
        self.assertTrue(entered['text'].startswith('Before you arrived\n' + told + '\n\n'), entered['text'][:300])
        self.assertLessEqual(len(entered['text']), post.CLIP)

if __name__ == '__main__':
    unittest.main()
