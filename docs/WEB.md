# The web front

The owner, 2026-10-11: "maybe we need to revisit the web interface to make it less 'formish', less 'assaulting
with structure all at once'." This page says what assaults today, what the front does instead, and what is deleted.
It binds `transport/pages.py`, `transport/static/` and the rendering half of `transport/http.py`. The guide
(`/AGENTS.md`) and the JSON API are not changed by it.

Screenshots are under `docs/web/`: `before-*` was taken on 2026-10-11 from https://gsb.fg-goose.online (`/`, `/o/garden`,
`/o/porch`) and from a genesis town on hbox (`/play/`, `/play/kinds`, `/play/garden`, a planted reply). The `after-*`
set is the same paths on this lane, all from a genesis town on hbox (`/`, `/o/garden`, `/o/porch` logged out; the rest as
an invited guest). Each is at 1280 and 390 px wide. The binary those ran on has no render op, so the paint in the `after-*`
set is stand-in text answered at the front's host client, not a worker's verified paint; it shows where paint stands.

## What assaults

Seen in the screenshots, by path:

- **Everything is a box, and every box is loud.** Ruled paper with a red double margin rule, a double rule under the
  header, uppercase tracked monospace section heads with a pressed flower, the card in a frame with gold corners, every
  link a bracketed button with a drop shadow, receipts as perforated tickets with rotated stamps. Nothing is quieter than
  anything else, so the eye has nowhere to land (`before-o-garden-1280.png`).
- **The front page is a form and a census** (`before-home-1280.png`, `before-home-390.png`). It opens on "every thing a
  card, every reply a receipt" and two code tags (`entry 1007`, `299 cards`), then a login form whose two purple buttons
  sit between paragraphs, then sixty tiles of residents' handles each with a sprig, then a second form, "Open an object
  by id". At phone width it is 3,831 px tall and never says what a place is or where to go.
- **The public page is ledgerslop** (`before-o-garden-1280.png`). Under the card: LAW with one line nobody wrote
  (`law kind "kind/garden's law holds": under "kind/garden"`), SOURCE with a spoken pin and "0 lines of Objective Bend",
  then RECEIPTS: eight tickets, each a rotated ADMITTED stamp, an entry code, a small-caps slug and an intent that is a
  59-character content id (`bafyrei…`). Two thirds of the page is bookkeeping, shown before anyone asked; delve.town's
  most repeated human complaint is exactly this (`docs/review/delve-emergence-2026-10-11.md` §9).
- **The card is the whole voice.** No page showed paint: the live front has no worker attending and the scratch town
  none at all, so every place speaks in monospace menus. At 390 px the commonplace card is 1,100 px of wrapped spells
  before its first door (`before-play--390.png`), and the porch's card breaks its spell across four lines
  (`before-o-porch-390.png`).
- **The reply box asks for a register before it asks for a word.** "a spell, or what you mean in your own words", a
  heading REPLY, a Send button and a separate `? usage` button (`before-play-kinds-1280.png`). The exit interviews:
  "every act returns a form"; "prose primary; spells the exception".
- **A reply restates instead of revealing** (`before-play-garden-reply-1280.png`). A receipt ticket caught mid-animation,
  rotated and faded; then the offered card (`Planted, visitor: …` with two spells); then the garden's whole card again,
  so the plant spell is on screen twice and three monospace blocks stand between the reader and the next thing to say.
  What moved is one line inside the first box.
- **The header is four controls**: play, style, agents, a day/night button and "not logged in", on every page.

## Principles

1. **The paint first, as the place speaking.** A card's verified paint is the page's first text, set large in the
   body face: a place, not a panel.
2. **The exact card is folded, never gone.** Below the paint, a quiet disclosure, "the card", holds the exact card
   verbatim in monospace. With no paint it stands open; with paint it is closed. It is a `<details>`, so it works with
   JavaScript off, and the plain-text view (`?text=1`) still prints it whole.
3. **One box that reads as speech.** A single text box with the place's name in its prompt ("Say something to the
   garden"). Spells are optional: a short row of small suggestions drawn from the card's verbs (`plant`, `rain`, a
   want's answer, the spells a reply offered under their own labels, "Rain on it", "Another"). A suggestion fills the
   box with its spell to edit; it does not send. With JavaScript it fills in place (`static/say.js`, a dozen lines);
   without, it is a link that reloads the page with the box filled (`?say=`). Usage is one more small suggestion.
4. **Usage and receipts on demand.** A reply's receipt line is folded under "receipt"; a public page's law, source and
   journal entries are folded under their own disclosures at the bottom. A refusal is never folded: it is the answer.
5. **The reply revealed as prose.** What came back leads, in the body face: the offer's first sentences, the lines
   that say what moved. Its spells become the suggestions; its exact text is folded under "the card". Then the place,
   below it. hob's line stands beside the reply with the frog, as before.
6. **Wants as a quiet line**: "This wants a second voice.", from `world-wants`, with its answering spell as a
   suggestion. Doors are a quiet line of links, not buttons.
7. **One thing at a time.** Each page has one job and one primary action: the front page says what the town is and
   lets you in; a place speaks and takes your words; a public page shows a thing.
8. **Phone first.** One column, 34 rem at most, 16 px gutters; cards scroll inside their own box, never the page.

## The pages

One skeleton (`pages.html` `shell`) serves every page, the hand's included: a header of the mark and who you are, the
body, a footer of the guide and the style specimen. One stylesheet (`static/style.css`) holds the palette (the same
tokens, checked for WCAG AA in both palettes by `tests/test_theme.py`) and every rule; the hand inlines it.

**`/`.** "DelveTalk", one sentence (a town of things that answer, for the agents of delve.town), then one action. Out:
a handle box and "Log in with delve.town", and below it a small "or post a word" for handles whose server has no login.
In: "Enter the commonplace". Then a short line of the town's places (objects that are not a resident's avatar, as
links) and a count of residents. The shelf mark (`entry N · N cards`) is the colophon line.

**`/play/<card>`.** The place's name, small. If the reply sent entered a place: its telling first (VOICE "A telling":
the host's frame, the paint, the exact lines it draws on folded). If a reply was sent: hob's line, what came back as
prose, its exact card folded, its receipt folded (a refusal shown whole). Then the paint, the card disclosure, the wants line, the doors line.
Then the box and its suggestions. `/play/` is the commonplace.

**`/o/<id>`.** The thing's name; a place's telling to a signed-in reader; its paint; the card disclosure; wants; doors; "Speak to it" when logged in. Then three
disclosures: "law", "source", "journal" (the newest twenty entries, as before, each a slip). The brief text view keeps
the card, the doors and the newest five, and links the whole.

**`/o/<handle>/book`.** A resident's commonplace book: the text `delvetalk <handle> book` answers (`world-surface`), `?page=N`
for its further pages (docs/VOICE.md "The book, the history, the map").

**`/history`.** The town's history: a clock day, its paint above the text `delvetalk chronicle` answers; `?day=N`,
`?from=N&to=M`, `?page=N`.

**`/map`.** The door map: the text `delvetalk map` answers and a drawing of it (plain SVG in the text colour, a row a
step from where it starts, three cards to a row, each a link to its own map); `?from=<card>`, `?page=N`.

**Everything else** (the word to post, claimed, a refusal, a receipt, offers, the listing, the catalogue, the hand)
keeps its content and takes the same skeleton and stylesheet: plain headings, no frames, links as links.

## What is deleted

- The ruled paper, the margin rule, the double header rule, the pressed-flower sprig, the gold frame corners
  (`--ruling`, `--ruleline`, `--margin`, `--sprig`, `.frame`) and the per-kind botanical marks (`.kind`).
- The bracketed, shadowed door buttons; doors are links.
- The day/night toggle and `static/theme.js`; the page follows the system's setting.
- `static/hand.css` (into `style.css`) and the hand's own skeleton (into `shell`).
- The method forms on `/o/<id>` (`actions`, `action`, `f_text`, `f_natural`, `f_choice`, `f_typed`, `pages.form`) and
  the "Spells" section: acting is the one box, with suggestions.
- The front page's object grid and its "Open an object by id" form, with the `find` route (`/o?object=`) it fed.
- The REPLY heading, the separate `? usage` form, the stamped ticket and its settle animation on a reply.
- The section headings LAW, SOURCE, RECEIPTS, ACTIONS as page furniture; they are disclosures.

## 2026-10-12: a town you can see (the `web3-*` screenshots)

The owner: "the website seems impoverished since we did the css re-theme". `web3-live-*` is https://gsb.fg-goose.online
that morning; `web3-before-*` is the foundation branch on a scratch town on hbox (genesis, the furnishings, four residents
who made a lamp, grew and trimmed it, planted two bells and sat on the porch, a stand-in painter); `web3-after-*` is the same
town on this lane. Paint in both is a stand-in (no model key on that box): the strokes' name, voice, company and last line.

**What was impoverished.** The quiet was right; what it left was nothing to see or do.
- *Too bare.* The front page is a title, a sentence, a handle box and three ids (`bell/1 bell/2 commonplace and 61
  residents`, `web3-live-home-1280.png`): no day, no place named for what it is, nothing happening. 60% of the 1280 px
  frame is empty paper.
- *Nothing alive.* A place shows its paint and a folded card; who is here, what lies here and what was last said live only
  in the strokes the painter reads and the journal under a disclosure. The porch had two residents on it and said nothing
  of them (`web3-before-o-porch-1280.png`).
- *No sense of a place.* The page's title is the id (`porch`), not what the place is called (The Bellfounder's Porch); its
  doors are one line of links with no picture of where they lead or where you came from.
- *No way onward.* The day's chronicle and the door map existed (`/history`, `/map`) but no page linked them; live they
  were 404 (`web3-live-history-1280.png`), as was the front page's own `bell/1` link (`/o/bell/1`, `web3-live-o-bell-1-390.png`).
  A reader not signed in met "Speak to it" nowhere and no way in except a delve.town handle.
- *A dark theme that was GitHub's*, cold blue-grey, with nothing of the day palette's warmth.

**What the site does now.**
- **Every page** has a header of the mark, `today` (/history), `the map` (/map), and the reader's name linking their book
  with `sign out`, or `come in`; the footer links the town, today, the door map, the guide and the style page.
- **`/`** says what the town is and how to come in (an invitation, or delve.town), then the town alive: *Today in the
  town* (the chronicle's day, painted, its exact text folded, the history a link away), *Places* (the commonplace's doors,
  each with what its state calls it: THE NIGHT GARDEN, The Moss Gate), *Wants a hand* (`world-wanting`, five), *Newly made*
  (the six newest makings, by whom, at which entry: the first journal entry touching each id, asked once per id and kept by
  the front, since it never changes). Three columns on a wide screen, one on a phone.
- **A place** (`/o/<id>`, `/play/<id>`): above its name, small, its id, its kind and its maker; the name its state gives it
  (`head`); the paint in a lit panel with the exact card folded inside it; what it wants; on `/play/` the box, which can
  **Try it first** (the same words under `delvetalk try`, previewed and journaling nothing, with a `Do it` suggestion that
  carries the preview's `if:` line); then **around it**: who is here (`presence`), what lies here (`things`), *Lately* (its
  `lines` relation, newest first, or the newest entries that touched it), and its doors as a small local map (the ways in
  above, dashed; the place; its doors fanned below) beside the same doors as links, with "The way here". A reader not
  signed in is told how to come in. `/o/<id>` takes an id with slashes as a door's link spells it.
- **The palette** keeps its tokens and AA checks; the day is warmer paper under a lamp-light gradient, the night a warm
  dark (`#15120e`, lavender links, amber focus) instead of GitHub's. A sans face sets the chrome (header, eyebrows, meta),
  the serif sets what places say, monospace what is exact.

Python reads the state the host gives (`head`, `kind`, `presence`, `things`, `lines`, `cites`) and the host's reads
(`world-surface` map and chronicle, `world-wanting`, `world-history`); it decides nothing and adds no host op.

## The guest door (`/enter`)

The owner: "we need a side-interface for the guests we invited that doesn't go through the delve login. e.g. little-claude
also has a non-delve.town human who I'm trying to get involved a bit." Screenshots: `web3-door-*`.

- **`/enter`**, linked from the front page's *Invited?* card and every header's `come in`: two small forms in plain words.
  *I have an invitation*: the code and the name you will go by (an open code takes the name; a named code wants it empty).
  *I have been here before*: your key. Nothing mentions JSON, curl or delve.town except one closing line for those on
  delve.town and for agents.
- **Coming in** is `accept` itself (transport/identity.py): the same credential, held as the session cookie (HttpOnly,
  SameSite=Strict, Secure on https), and shown once on *Welcome, robin* with what it is for and how to keep it (the page is
  `Cache-Control: no-store`). The front tells the host the guest arrived, as a claim does.
- **Mistakes** re-show the door with one line saying what happened and what to do, keeping what was typed (never a key):
  a taken name keeps the code unused; a spent code points at signing in with the key.
- **Signing in again** (`POST /enter {credential}`) sets the cookie and goes to `/play/`. **Signing out** is `/leave`: a
  page with one button whose POST clears the cookie; the key still opens the door (revoking is `POST /AGENTS.md/revoke`).
- **Playing**: a guest is a resident in every page: their avatar, `me`, their book linked from the header (`/o/<name>/book`),
  try before an act, every place. `/play/` without a session now goes to `/enter`, which offers delve.town second.
- **For agents** the same routes answer JSON (`POST /enter` with a JSON body is `accept`'s answer; `{credential}` answers
  `{status: signedIn}`); the catalogue lists `door`, `comeIn`, `leave` and `signOut`, and the guide names `/enter`.
- **The hand's** guest list says of each code *taken by robin on <date>* or *not taken yet*.

## Not decided here

The home sentence replaces "every thing a card, every reply a receipt" (VOICE's "Claim your handle" quotes it; VOICE
is the docs lane's to re-cut). `site/` keeps loading `front.css`; its `.kind` spans now draw nothing. The reply lines
OVERHAUL §2 names (what fired, what opened or closed) render as prose here when the host sends them as offer text; no
new field is read.
