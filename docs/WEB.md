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

**`/play/<card>`.** The place's name, small. If a reply was sent: hob's line, what came back as prose, its exact card
folded, its receipt folded (a refusal shown whole). Then the paint, the card disclosure, the wants line, the doors line.
Then the box and its suggestions. `/play/` is the commonplace.

**`/o/<id>`.** The thing's name; its paint; the card disclosure; wants; doors; "Speak to it" when logged in. Then three
disclosures: "law", "source", "journal" (the newest twenty entries, as before, each a slip). The brief text view keeps
the card, the doors and the newest five, and links the whole.

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

## Not decided here

The home sentence replaces "every thing a card, every reply a receipt" (VOICE's "Claim your handle" quotes it; VOICE
is the docs lane's to re-cut). `site/` keeps loading `front.css`; its `.kind` spans now draw nothing. The reply lines
OVERHAUL §2 names (what fired, what opened or closed) render as prose here when the host sends them as offer text; no
new field is read.
