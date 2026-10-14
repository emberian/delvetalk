# site/

The GitHub Pages site. Plain HTML and one stylesheet: no build step, no JavaScript. Light and dark follow the
reader's system setting (`prefers-color-scheme`). "Read the design" links the documents rendered on GitHub
(`github.com/emberian/delvetalk/blob/HEAD/...`), so they are never copied and never stale.

| File | Page |
| --- | --- |
| `index.html` | what DelveTalk is (law, rules, wants, grown verbs, hob, the paint, carry), the commonplace's doors, the welcome card (`docs/previews/gsb-welcome.txt`) |
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

## Enabling Pages

Pages serves a branch only from `/` or `/docs`, so `site/` is published by a workflow.

1. Add `.github/workflows/pages.yml`:

   ```yaml
   name: pages
   on:
     push:
       branches: [main]
       paths: [site/**]
     workflow_dispatch:
   permissions:
     contents: read
     pages: write
     id-token: write
   concurrency:
     group: pages
     cancel-in-progress: true
   jobs:
     deploy:
       runs-on: ubuntu-latest
       environment:
         name: github-pages
         url: ${{ steps.deployment.outputs.page_url }}
       steps:
         - uses: actions/checkout@v4
         - uses: actions/configure-pages@v5
         - uses: actions/upload-pages-artifact@v3
           with:
             path: site
         - id: deployment
           uses: actions/deploy-pages@v4
   ```

   Pin each action to a commit SHA before relying on it; the tags above are the current majors.
   Change `main` to the branch you push the site from.
2. Repository Settings, Pages, Build and deployment, Source: **GitHub Actions**.
3. Push. The site is at `https://emberian.github.io/delvetalk/`.

## Editing

Edit the HTML directly. When a number changes (tests, runs, the welcome card), change it here in the same commit
as the document it comes from: the runs table is `rehearsal/REPORT.md`'s, the card is `docs/previews/gsb-welcome.txt`.
