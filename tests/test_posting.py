"""A resident who only posts (docs/POSTING.md): every move a reply on the bridge's fake Delve over a genesis town,
the hand posting each draft as `post` does (long ones threaded).

Evidence for docs/POSTING.md (layer: transport).

Refuted by: a reply over the clip posted whole, a reply answering several cards addressed to one of them, or a move
the guide teaches that a poster cannot make.
"""
import re
import tempfile
import unittest
from unittest import mock

from deploy import genesis
from tests.poster import Poster
from transport import interpret, post
from transport.hand import WELCOME, Hand
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
        paint = 'Like moonlight through silk.'
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
        selected = {}
        def model(req):
            source = 'A plain thing.'
            if 'a telling of porch' in req['user'][:80]:
                event = re.search(r'^- (\d+): event; porch; .*; clause: (.+)$', req['user'], re.M)
                self.assertIsNotNone(event, req['user'])
                selected['clause'] = event[2]
                source = '[[%s]]\nLike moonlight through silk.' % event[1]
            return {'status': 'replied', 'raw': source, 'model': 'claude-haiku-5-5',
                    'usage': {'input_tokens': 1, 'output_tokens': 1}}
        with mock.patch('transport.bridge.time.sleep', lambda _: interpret.paint(host, model)):  # the worker paints while the bridge waits
            [entered] = self.poster.say('delvetalk porch enter')
        told = selected['clause'] + '.\nLike moonlight through silk.'
        lead = 'Before you arrived\n' + told + '\n\n'
        self.assertTrue(entered['text'].startswith(lead), entered['text'][:300])
        self.assertEqual(entered['told'], len(lead))
        reply = entered['text'][len(lead):]
        if reply.startswith('Next, see it before it is real'):
            reply = reply.partition('\n')[2]
        offers = [o['text'] for o in entered['receipt']['offers'] if o['to'] == self.poster.did]
        self.assertTrue(offers, entered['receipt'])
        self.assertTrue(reply.startswith('\n'.join(offers).rstrip('\n') + '\n'), reply)
        self.assertIn('● admitted porch', reply)
        rendered = host.send({'op': 'world-render', 'principal': self.poster.did, 'object': 'porch', 'telling': {}})
        self.assertEqual((rendered['status'], rendered.get('text')), ('painted', told), rendered)
        exact = rendered['telling']['exact']
        self.assertTrue(any(line.startswith('entry ') and not line.endswith(selected['clause']) for line in exact), exact)
        self.assertTrue(reply.endswith('\nWhat it draws on:\n' + '\n'.join(exact) + '\n'), reply)
        self.assertLessEqual(len(entered['text']), post.CLIP)

    def test_the_welcome_is_one_move_done_and_offered_back_and_a_first_reply_teaches_the_next(self):
        h = Hand(self.poster.st, self.town.client, sleep=lambda _: None)
        came = h.welcome()
        text = came['text']
        self.assertTrue(text.startswith('hob: the frog on the quiet line'), text)
        self.assertIn('    ' + WELCOME, text)  # the move as cast, quoted: never cast again by being posted
        self.assertIn(f"receipt {came['slug']}", text)  # a real receipt, which resolves
        self.assertIn('Yours: reply under this post with\n    delvetalk kind/bell make / seed: <your words> / colour: silver', text)
        self.assertLessEqual(len(text), post.CLIP)
        self.assertEqual(h.welcome()['drafted'], came['drafted'])  # once: the same intent is the same move
        newcomer = Poster(self.tmp.name + '/n', self.town.client, did='did:plc:newcomer', handle='newcomer.delve.town')
        [first] = newcomer.say('delvetalk kind/bell make / seed: a bell of my own / colour: amber')
        self.assertIn('Next, see it before it is real: delvetalk try', first['text'])
        self.assertIn(f"delvetalk receipt / of: {first['receipt']['slug']}", first['text'])
        [second] = newcomer.say('delvetalk library read / page: laws')
        self.assertNotIn('Next, see it before it is real', second['text'])


    def test_a_resident_who_only_posts_learns_the_town_makes_grows_rules_reads_and_previews(self):
        r = Poster(self.tmp.name + '/journey', self.town.client, did='did:plc:journeyer', handle='journeyer.delve.town')
        said = lambda text: self.one(r, text)  # noqa: E731
        self.assertIn('hob: the guide, in', said('delvetalk guide'))
        self.assertIn('KINDS', said('delvetalk commonplace since / entry: 0'))
        make = 'delvetalk kinds make / name: wick / of: record / form: light: text 1..80'
        preview = said('delvetalk try\n  ' + make)
        self.assertTrue(preview.startswith('preview, nothing done'), preview)
        self.assertEqual(self.town.client.send({'op': 'world-view', 'principal': 'anonymous', 'object': 'kind/wick'})['status'], 'unknown')
        guard = next(line for line in preview.splitlines() if line.startswith('if: '))
        self.assertEqual(preview.splitlines()[-1], guard)
        self.assertRegex(guard, r'/b\d+(?:, |$)')
        self.assertIn('admitted', said(guard + '\n' + make))
        thing = said('delvetalk kind/wick make / light: moth glow')
        self.assertIn('admitted', thing)
        made = re.search(r'\b(wick/\d+)\b', thing)[1]
        grown = said(f'delvetalk {made} grow / name: trim / reading: the wick trimmed / takes: nothing\ndelvetalk {made} trim')
        self.assertEqual(grown.count(f'admitted {made}'), 2, grown)  # grown, then used: one reply
        self.assertIn('trim', said(f'delvetalk {made} verbs'))
        ruled = said(f'delvetalk {made} rule / name: lit / when: count(new.lines) >= 1 / then: delvetalk me note / text: the wick is lit')
        self.assertIn('admitted', ruled)
        self.assertIn('lit', said(f'delvetalk {made} rules'))
        fired = said(f'delvetalk {made} trim')
        self.assertIn('lit', fired)
        self.assertIn('fired', fired)
        self.assertIn('hob: ', said('delvetalk library read / page: laws'))
        slug = re.search(r'receipt ([a-z]+-[a-z]+)', ruled)[1]
        self.assertIn(f'receipt {slug}', said(f'delvetalk receipt / of: {slug}'))

    def one(self, r, text):
        """The one reply to a post, each of its parts within the clip."""
        [d] = r.say(text)
        self.assertTrue(all(len(p) <= post.CLIP for p in post.parts(d['text'])), d['text'][:200])
        return d['text']


if __name__ == '__main__':
    unittest.main()
