"""The previews are cut from a bare genesis's live cards (no furnishing, as production begins): the card text each embeds equals the live render, and every seed-post spell is admitted."""
import os
import html
import re
import tempfile
import unittest

from deploy import genesis
from tests.town import Town
from tests.wire import label, record

PREVIEWS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'previews')
STRANGER = 'did:plc:stranger'
# preview file -> the cards whose live render it embeds
EMBEDS = {
    'gsb-welcome.txt': ['commonplace'],
    'zulip-welcome.txt': ['commonplace'],
    'commonplace-card.txt': ['commonplace'],
    'seed-posts/01-porch.txt': ['porch'],
    'seed-posts/02-garden.txt': ['kind/garden'],
    'seed-posts/03-rain-bell-1.txt': ['bell/1'],
}


def read(name):
    with open(os.path.join(PREVIEWS, name), encoding='utf-8') as f:
        return f.read()


class Previews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.turns = 0
        cls.render = {}
        cls.town.send(op='world-arrive', principal='transport', did=STRANGER, handle='x.test')
        for cards in EMBEDS.values():
            for card in cards:
                cls.render[card] = cls.town.send(op='world-card', principal=STRANGER, object=card)['text']

    def test_each_preview_embeds_the_live_card_verbatim(self):
        for name, cards in EMBEDS.items():
            text = read(name)
            for card in cards:
                self.assertIn(self.render[card].rstrip('\n'), text, '%s: re-cut it from the live %s card' % (name, card))
        self.assertEqual(read('commonplace-card.txt'), self.render['commonplace'])

    def test_paint_is_followed_by_the_open_exact_card_with_current_status_and_actions(self):
        from transport import pages
        card = self.render['bell/1']
        self.assertIn('silent', card)
        self.assertIn('delvetalk bell/1 rain', card)
        shown = pages.place(card, paint='Like moonlight through silk.')
        self.assertLess(shown.index('class="paint"'), shown.index('<pre class="card">'))
        self.assertIn('<details class="card" open><summary>the card</summary>', shown)
        self.assertIn(html.escape(card), shown)

    def test_every_seed_post_has_its_header_and_its_spells_are_admitted(self):
        seeds = sorted(n for n in os.listdir(os.path.join(PREVIEWS, 'seed-posts')) if n.endswith('.txt'))
        self.assertTrue(seeds)
        for n, name in enumerate(seeds):
            text = read('seed-posts/' + name)
            head = re.match(r'recorded against: (\S+) · (.+)\n', text)
            self.assertTrue(head, name)
            body = text
            for card in EMBEDS.get('seed-posts/' + name, []):
                body = body.replace(self.render[card].rstrip('\n'), '')
            spells = [l.strip() for l in body.splitlines() if l.strip().startswith('delvetalk ')]
            for i, spell in enumerate(spells):
                unique = 'preview-%s-%d' % (name, i)
                got = self.town.send(op='world-turn', principal=genesis.OPENER, object=head.group(1), method='receive', identity=unique,
                                     argument=record(text=label(spell), post=label('at://x/' + unique)))
                self.assertEqual(got['status'], 'admitted', (name, spell, got))
                said = ''.join(o.get('text', '') for o in got.get('offers', []))
                self.assertFalse(any(l.startswith('refused') for l in said.splitlines()), (name, spell, said))
                self.assertTrue(said.strip(), (name, spell))


if __name__ == '__main__':
    unittest.main()
