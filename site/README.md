# site/

The GitHub Pages site. Plain HTML and one stylesheet: no build step, no JavaScript. Light and dark follow the
reader's system setting (`prefers-color-scheme`). "Read the design" links the documents rendered on GitHub
(`github.com/emberian/delvetalk/blob/HEAD/...`), so they are never copied and never stale.

| File | Page |
| --- | --- |
| `index.html` | what DelveTalk is, the six doors, the welcome card (`docs/previews/gsb-welcome-v3.txt`) |
| `play.html` | how to play: spells, prose, receipts, the API walk, forging |
| `built.html` | how it is built: the architecture diagram (inline SVG), a turn, law, principles |
| `design.html` | the documents and who reads each |
| `status.html` | tests, the gate, the rehearsal runs table |
| `style.css` | the one stylesheet |

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
as the document it comes from: the runs table is `rehearsal/REPORT.md`'s, the card is `docs/previews/gsb-welcome-v3.txt`.
