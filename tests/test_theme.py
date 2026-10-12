"""The theme, without a browser (docs/WEB.md): both palettes pass WCAG AA on every text-on-surface pair, there is one
stylesheet (the site loads it as site/front.css, the hand inlines it) and one skeleton, and a receipt's fate is a word
and an icon in the markup, never colour alone."""
import re
import unittest
from pathlib import Path

from transport import pages

ROOT = Path(__file__).resolve().parent.parent
FRONT, SITE = ROOT / 'transport' / 'static' / 'style.css', ROOT / 'site' / 'style.css'
SPECIMEN = ROOT / 'transport' / 'static' / 'specimen.html'
TEXT = ('ink', 'soft', 'muted', 'amber', 'violet', 'silver', 'terracotta', 'sage')  # every colour text is set in
SURFACES = ('paper', 'leaf', 'tint', 'rtint')  # every colour text is set on


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


class Theme(unittest.TestCase):
    def test_every_text_pair_passes_wcag_aa_in_both_palettes(self):
        failures = []
        for name, p in palettes(FRONT.read_text()).items():
            pairs = [(fg, bg) for fg in TEXT for bg in SURFACES] + [('bink', 'button'), ('violet', 'leaf')]
            failures += [(name, fg, bg, round(contrast(p[fg], p[bg]), 2)) for fg, bg in pairs if contrast(p[fg], p[bg]) < 4.5]
            self.assertGreaterEqual(contrast(p['amber'], p['paper']), 3, 'the focus ring')  # non-text contrast
        self.assertEqual(failures, [])

    def test_one_stylesheet_and_one_skeleton(self):
        static = sorted(p.name for p in (ROOT / 'transport' / 'static').iterdir() if p.suffix in ('.css', '.js'))
        self.assertEqual(static, ['say.js', 'style.css'])
        self.assertEqual(sum('<!doctype html>' in p.read_text() for p in (ROOT / 'transport' / 'static').glob('*.html')), 1)
        from transport import hand
        self.assertTrue(hand.shell('t', None, 'B').startswith('<!doctype html>'))
        self.assertIn(FRONT.read_text(), hand.shell('t', None, 'B'))  # the hand inlines the one stylesheet

    def test_the_site_loads_the_front_stylesheet_and_keeps_no_palette_of_its_own(self):
        self.assertEqual((ROOT / 'site' / 'front.css').resolve(), FRONT)
        self.assertNotIn('--paper', SITE.read_text())
        for page in (ROOT / 'site').glob('*.html'):
            self.assertIn('<link rel="stylesheet" href="front.css">\n<link rel="stylesheet" href="style.css">', page.read_text(), page.name)

    def test_a_receipts_fate_is_a_word_and_an_icon_never_colour_alone(self):
        self.assertEqual(len(set(pages.STAMPS.values())), len(pages.STAMPS))
        specimen = SPECIMEN.read_text()
        for fate, icon in pages.STAMPS.items():
            self.assertIn(f'<span class="stamp">{icon} {fate}</span>', specimen)  # shown in /style/ as the markup carries it
        for css in (FRONT.read_text(), SITE.read_text()):
            self.assertNotRegex(css, r'\.(slip|stamp)[^{,]*::(before|after)[^{]*\{[^}]*content')  # no fate drawn by the stylesheet alone


if __name__ == '__main__':
    unittest.main()
