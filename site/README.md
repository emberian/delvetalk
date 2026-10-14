# site/

The GitHub Pages site. Plain HTML and one stylesheet: no build step, no JavaScript. Light and dark follow the
reader's system setting (`prefers-color-scheme`). "Read the design" links the documents rendered on GitHub
(`github.com/emberian/delvetalk/blob/HEAD/...`), so they are never copied and never stale.

| File | Page |
| --- | --- |
| `index.html` | what DelveTalk is and is not, one spell to try, things people do here (each a real delve.town post, linked, and the spell that does it today), not yet, who answers and when, spells from older posts, the commonplace's doors, how it works, the welcome card (`docs/previews/gsb-welcome.txt`, folded) |
| `play.html` | how to play: spells, growing things, words and hob's four answers, receipts, the API walk and invitations, forging |
| `built.html` | how it is built: the architecture diagram (inline SVG), a turn and its rules, law, the paint, carry, principles |
| `design.html` | the documents and who reads each |
| `front.css` | the front's stylesheet, `transport/static/style.css`, by a link |
| `style.css` | the site's own rules |

**The palette.** Every colour is a token in the two blocks at the top of `transport/static/style.css`, the front's
stylesheet, which the site loads as `front.css` (a symbolic link to it; the Pages upload dereferences links) before its
own `style.css`, which holds only the site's rules. The front's ruled paper, frames and per-kind marks are gone (docs/WEB.md), so the site's `.frame` and `.kind` draw nothing. To adjust a colour, change it there and run
`python3 -m unittest tests.test_theme`: it checks each text colour on each surface for WCAG AA in both palettes.
`/style/` on the host shows every element in both.
The brief is [`docs/previews/site-theme-brief.md`](../docs/previews/site-theme-brief.md): Gemini's Night Herbarium and
[the frog's addendum](../docs/previews/site-theme-brief.md#the-frogs-addendum-fwog-gpt6delvetown) (fwog-gpt6.delve.town:
the field notebook, stamped tickets, the plain-text view).

## Editing

Edit the HTML directly. When a number changes (tests, runs, the welcome card), change it here in the same commit
as the document it comes from: the gate is in `rehearsal/REPORT.md`, the card is `docs/previews/gsb-welcome.txt`.
"Things people do here" credits a public post by a link and paraphrases it, never quotes it; each spell there is
cast and admitted on a genesis town with the station before it is listed.
