"""The theme, without a browser: both palettes pass WCAG AA on every text-on-surface pair, the site carries the front's
palette, every kind the brief names has its own botanical mark, a receipt's fate is a word and an icon in the markup (never
colour alone), doors are visibly doors at rest and ringed on focus, and spells are set in the monospace."""
import re
import unittest
from pathlib import Path

from transport import pages

ROOT = Path(__file__).resolve().parent.parent
FRONT, SITE = ROOT / 'transport' / 'static' / 'style.css', ROOT / 'site' / 'style.css'
SPECIMEN = ROOT / 'transport' / 'static' / 'specimen.html'
TEXT = ('ink', 'soft', 'muted', 'amber', 'violet', 'silver', 'terracotta', 'sage')  # every colour text is set in
SURFACES = ('paper', 'leaf', 'tint', 'rtint')  # every colour text is set on
KINDS = {'garden': 'garden', 'bell': 'garden/bell/1', 'env': 'env/did:plc:x', 'wake': 'wake/did:plc:x', 'tide': 'tide', 'deal': 'deal/1',
         'scene': 'rooms', 'place': 'place/1', 'thing': 'thing/1', 'anthology': 'anthology', 'workshop': 'workshop'}


def palettes(css):
    """{'light': {token: hex}, 'dark': {...}} from the token blocks; the media block and the [data-theme=dark] block must agree."""
    blocks = re.findall(r'([^{}]*)\{([^{}]*--paper[^{}]*)\}', css)
    found = {}
    for selector, body in blocks:
        tokens = dict(re.findall(r'--([a-z]+):\s*(#[0-9a-f]{6})', body))
        found.setdefault('dark' if 'dark' in selector or ':not([data-theme=light])' in selector else 'light', []).append(tokens)
    assert all(t == found['dark'][0] for t in found['dark']), 'the two dark blocks differ'
    return {k: v[0] for k, v in found.items()}


def contrast(a, b):
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + .05) / (lo + .05)


def mark(css, oid):
    """The glyph the stylesheet gives `.kind[data-id=oid]`: the last matching rule wins, as the cascade has it."""
    glyph = None
    for selectors, body in re.findall(r'([^{}]*\.kind\[data-id[^{}]*)\{([^{}]*)\}', css):
        for op, value in re.findall(r'\.kind\[data-id(\^=|\*=|=)"([^"]*)"\]::before', selectors):
            if {'=': oid == value, '^=': oid.startswith(value), '*=': value in oid}[op]:
                glyph = re.search(r'content:\s*"([^"]*)"', body)[1]
    return glyph


class Theme(unittest.TestCase):
    def test_every_text_pair_passes_wcag_aa_in_both_palettes(self):
        failures = []
        for name, p in palettes(FRONT.read_text()).items():
            pairs = [(fg, bg) for fg in TEXT for bg in SURFACES] + [('bink', 'button'), ('violet', 'leaf')]
            failures += [(name, fg, bg, round(contrast(p[fg], p[bg]), 2)) for fg, bg in pairs if contrast(p[fg], p[bg]) < 4.5]
            self.assertGreaterEqual(contrast(p['amber'], p['paper']), 3, 'the focus ring')  # non-text contrast
        self.assertEqual(failures, [])

    def test_text_stays_aa_where_it_crosses_the_notebooks_ruled_lines(self):
        for name, p in palettes(FRONT.read_text()).items():
            self.assertEqual([fg for fg in TEXT if contrast(p[fg], p['ruleline']) < 4.5], [], name)
            self.assertLess(contrast(p['ruleline'], p['paper']), 1.5, f'{name}: a ruled line is faint')

    def test_doors_are_doors_at_rest_and_ringed_on_focus(self):
        for name, p in palettes(FRONT.read_text()).items():  # the door's edge and face, non-text contrast at rest
            self.assertGreaterEqual(min(contrast(p['violet'], p[bg]) for bg in ('paper', 'leaf')), 3, name)
        for css in (FRONT.read_text(), SITE.read_text()):
            door = re.search(r'\n\.door \{([^}]*)\}', css)[1]
            for rest in ('border-color: var(--violet)', 'box-shadow: 0 2px 0 var(--violet)', 'linear-gradient(currentColor, currentColor)'):
                self.assertIn(rest, door)  # the button face and the underline are there before any hover
            self.assertRegex(css, r'\.door::before \{ content: "\["')
            self.assertRegex(css, r'\.door:focus-visible[^{]*\{ outline: 2px solid var\(--amber\)')

    def test_a_receipts_fate_is_a_word_and_an_icon_never_colour_alone(self):
        self.assertEqual(len(set(pages.STAMPS.values())), len(pages.STAMPS))
        specimen = SPECIMEN.read_text()
        for fate, icon in pages.STAMPS.items():
            self.assertIn(f'<span class="stamp">{icon} {fate}</span>', specimen)  # shown in /style/ as the markup carries it
        for css in (FRONT.read_text(), SITE.read_text()):
            self.assertNotRegex(css, r'\.(slip|stamp)[^{,]*::(before|after)[^{]*\{[^}]*content')  # no fate drawn by the stylesheet alone

    def test_spells_are_monospace_everywhere_they_appear(self):
        for css in (FRONT.read_text(), SITE.read_text()):
            for rule in (r'\npre \{', r'\ncode, kbd \{', r'\ntextarea, input \{', r'\.slip \.line \{', r'\.door, button \{'):
                self.assertRegex(css, rule + r'[^}]*var\(--mono\)', rule)
        self.assertIn('<pre class="spell">{spell}</pre>', (ROOT / 'transport' / 'static' / 'pages.html').read_text())

    def test_the_site_carries_the_fronts_palette(self):
        self.assertEqual(palettes(SITE.read_text()), palettes(FRONT.read_text()))

    def test_every_kind_has_its_own_mark(self):
        css = FRONT.read_text()
        marks = {kind: mark(css, oid) for kind, oid in KINDS.items()}
        self.assertNotIn(None, marks.values(), marks)
        self.assertEqual(len(set(marks.values())), len(KINDS), marks)
        self.assertEqual(mark(css, 'play'), None)  # anything else falls back to the plain sprig
        self.assertEqual(marks, {k: mark(SITE.read_text(), oid) for k, oid in KINDS.items()})

    def test_the_card_is_never_reflowed(self):
        for css in (FRONT.read_text(), SITE.read_text()):
            card = re.search(r'\n\.card \{([^}]*)\}', css)[1]
            self.assertIn('white-space: pre;', card)
            self.assertIn('72ch', card)
            self.assertIn('overflow-x: auto', card)  # a long line scrolls inside its frame, never the page


if __name__ == '__main__':
    unittest.main()
