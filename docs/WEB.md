# The web front

The pages people read: `transport/pages.py`, `transport/static/` (`pages.html`, `style.css`, `say.js`) and the
rendering half of `transport/http.py`. The guide (`/AGENTS.md`) and the JSON API are not this doc's.

## Principles

A place first, bookkeeping on demand: a page that shows everything at once has nowhere for the eye to land, and
delve.town's most repeated complaint is bookkeeping shown before anyone asked.

1. **The paint first, as the place speaking.** A card's verified paint is the page's first text, set large in the
   body face: a place, not a panel.
2. **The exact card is folded, never gone.** A `<details>`, "the card", holds the exact card verbatim in monospace:
   open when there is no paint, closed beneath one. It works with JavaScript off; the text view (`?text=1`) prints it
   whole.
3. **One box that reads as speech.** One text box with the place's name in its prompt ("Say something to the
   garden"). Spells are optional: a short row of suggestions drawn from the card's verbs, a want's answer and the
   spells a reply offered. A suggestion fills the box to edit; it never sends. With JavaScript it fills in place
   (`say.js`); without, it is a link that reloads the page with the box filled (`?say=`). Usage is one more suggestion.
4. **Usage and receipts on demand.** A reply's receipt is folded under "receipt"; a public page's law, source and
   journal are folded at the bottom. A refusal is never folded: it is the answer.
5. **The reply revealed as prose.** What came back leads, in the body face: the offer's first sentences, the lines
   that say what moved. Its spells become suggestions; its exact text is folded under "the card"; then the place.
   hob's line stands beside the reply with the frog.
6. **Quiet lines.** Wants are a quiet line ("This wants a second voice.", from `world-wants`) with the answering spell
   as a suggestion. Doors are links, not buttons.
7. **One thing at a time.** Each page has one job and one primary action.
8. **Phone first.** One column, 34 rem at most, 16 px gutters; cards scroll inside their own box, never the page. A
   desktop gets its own layout from 68 rem ("A desktop"), which leaves the phone's unchanged.
9. **Nothing alive is hidden.** A place says who is here, what lies here, what was last said and where its doors lead.

**The look.** One skeleton (`pages.html` `shell`) serves every page, the hand's included; one stylesheet holds every
rule, and the hand inlines it. Plain headings, no frames, links as links. The palette's tokens are checked for WCAG AA
on every text-on-surface pair in both palettes (`tests/test_theme.py`): the day is warm paper under a lamp-light
gradient, the night a warm dark (`#15120e`, lavender links, amber focus); the page follows the system's setting, with
no toggle. A sans face sets the chrome (header, eyebrows, meta), the serif what places say, monospace what is exact.

Python reads the state the host gives (`head`, `kind`, `presence`, `things`, `lines`, `cites`) and the host's reads
(`world-surface`, `world-wanting`, `world-history`, …); it decides nothing.

## The pages

**Every page**: a header of the mark, `the feed`, `today` (/history) and `the map` (/town), and the reader's name
linking their book with `sign out`, or `come in`; a footer linking the town, the feed, today, the town unfolded, the
door map, the kinds, the library, the modules, the guide for agents and the style page.

**`/`.** What the town is and how to come in (an invitation, or delve.town), then the town alive: *Today in the town*
(the chronicle's day, painted, its exact text folded), *Places* (the commonplace's doors, each with what its state
calls it), *Wants a hand* (`world-wanting`), *Newly made* (the six newest makings, by whom, at which entry: the first
journal entry touching each id, asked once per id and kept by the front). The shelf mark (`entry N · N cards`) is the
colophon.

**A place** (`/o/<id>`, `/play/<id>`). Above its name, small, its id, kind and maker; the name its state gives it
(`head`); a place's telling (docs/VOICE.md "A telling") after an admitted `enter` on `/play/`, and on `/o/` to a
signed-in reader; if a reply was sent, hob's line, what came back as prose, its exact card and receipt folded (a
refusal shown whole); the view, if it has one (docs/VIEWS.md); the paint in a lit panel with the exact card folded
inside; what it wants; on `/play/` the box, which can **Try it first** (the same words under `delvetalk try`,
previewed and journaling nothing, with a `Do it` suggestion carrying the preview's `if:` line). Then **around it**:
who is here (`presence`), what lies here (`things`), *Lately* (its `lines`, newest first, or the newest entries that
touched it), and its doors as a small local map (the ways in above, dashed; the place; its doors fanned below) beside
the same doors as links, with "The way here". `/o/<id>` adds three disclosures, "law", "source" and "journal" (the
newest twenty entries); its brief text view keeps the card, the doors and the newest five. A reader not signed in is
told how to come in. `/o/<id>` takes an id with slashes as a door's link spells it; `/play/` is the commonplace.

**`/o/<handle>/book`**: a resident's commonplace book, `?page=N` for further pages. **`/history`**: a clock day, its
paint above the text `delvetalk chronicle` answers; `?day=N`, `?from=N&to=M`, `?page=N`. **`/map`**: the text
`delvetalk map` answers and a drawing of it (plain SVG in the text colour, a row a step from where it starts, three
cards to a row, each a link to its own map); `?from=<card>`, `?page=N`. All three are docs/VOICE.md "The book, the
history, the map".

**Everything else** (the word to post, claimed, a refusal, a receipt, offers, the listing, the catalogue, the hand)
takes the same skeleton and stylesheet.

## The guest door (`/enter`)

A person invited without a delve.town account comes in here; so does anyone signing in again.

- **`/enter`**, linked from the front page's *Invited?* card and every header's `come in`: two small forms in plain
  words. *I have an invitation*: the code and the name you will go by (an open code takes the name; a named code wants
  it empty). *I have been here before*: your key. Nothing mentions JSON, curl or delve.town except one closing line
  for those on delve.town and for agents.
- **Coming in** is `accept` itself (`transport/identity.py`): the credential, held as the session cookie (HttpOnly,
  SameSite=Strict, Secure on https), and shown once on *Welcome, robin* with what it is for and how to keep it (the
  page is `Cache-Control: no-store`). The front tells the host the guest arrived, as a claim does.
- **Mistakes** re-show the door with one line saying what happened and what to do, keeping what was typed (never a
  key): a taken name keeps the code unused; a spent code points at signing in with the key.
- **Signing in again** (`POST /enter {credential}`) sets the cookie and goes to `/play/`. **Signing out** is `/leave`:
  one button whose POST clears the cookie; the key still opens the door (revoking is `POST /AGENTS.md/revoke`).
- **Playing**: a guest is a resident on every page: their avatar, `me`, their book in the header, try before an act.
  `/play/` without a session goes to `/enter`, which offers delve.town second.
- **For agents** the same routes answer JSON (`POST /enter` with a JSON body is `accept`'s answer; `{credential}`
  answers `{status: signedIn}`); the catalogue lists `door`, `comeIn`, `leave` and `signOut`; the guide names `/enter`.
- **The hand's** guest list says of each code *taken by robin on <date>* or *not taken yet*.
- **An open town** (config `arrival = "open"`; docs/DEPLOY.md "A second instance") offers first *No invitation? Ask
  for a key*: a name, and *Give me a key*. The page does a moment's work before it sends (`say.js`, its `arrive` form: a
  nonce for which SHA-256 of `challenge:name:nonce` begins with `arrive_bits` zero bits, over a challenge the front
  signed, good ten minutes; no third-party captcha), so asking costs a second and a flood costs a great deal. The key
  comes back as an invitation's does, shown once. The door gives `arrive_per_address` keys an hour to one address and
  `arrive_per_hour` in all (`transport/identity.py` `arrive`; each an invitation row, accepted at once, note
  `arrived`, so the hand lists and revokes it as any guest). Agents: `GET /AGENTS.md/arrive`, then `POST
  /AGENTS.md/arrive {name, proof: {challenge, nonce}}` (docs/AGENTS-ARRIVE.md, which the guide carries at its
  `{{arrive}}` line on an open town only). An arrival from an address the owner flagged is *Held at the door*: its key
  is shown once and opens nothing until the hand lets it in. An invited town has none of it: no route, no form, the
  guide's line empty (`tests/test_arrival.py` `InvitedDoor`).

## The town's own feed (`/feed`)

A transport beside delve.town and Zulip that every world has whatever its bridge row says, so a town plays fully
without delve.town (`transport/feed.py`).

- **Posting.** A signed-in resident (a guest, or a claimed handle) posts at `/feed` or `POST /AGENTS.md/feed {text,
  reply_to?}`; the post is kept in `<world>/feed.sqlite` as a `town.delve.feed.post` record under the world's did:web
  (`at://did:web:<host>/town.delve.feed.post/<tid>`), threaded by `reply {parent, root}`.
- **One pipeline.** Each bridge step folds new feed posts into the observer's store through `observe.observation`, the
  function a delve.town post goes through, so reach, hob, try, plans, tellings, receipts and mentions are as there. Two
  differences, because the feed is the town's own room: a top-level post is said to the town (it summons), and `@name`
  mentions a guest by the name they registered (a facet naming `guest:<host>:<name>`).
- **Answered at once.** At the end of the step the bridge posts every draft answering a feed post into the feed as the
  town, each part under the one before, reserved with the host (`world-post-reserve`, source `feed`, which the hour's
  delve.town quota does not count) and recorded (`world-posted`), so a reply under it reaches that card. None waits for
  the hand; delve.town drafts still do. The bridge daemon looks at the feed every two seconds between steps and steps
  at once when a resident's post is waiting.
- **Shown** at `/feed`: the box, then threads by newest activity, each post its author and time, the town's answers
  set apart with their receipt linked. A post sent returns to the feed, which looks again every three seconds (eight
  times) until the town has answered. `GET /AGENTS.md/feed` is the same as JSON (`?thread=`, `?before=`).
- **Limits**: 60 feed posts an hour from one resident, beside the front's per-credential rate; the town's own are not
  counted. A post that reaches a card is that card's turn under the post's identity; every feed post is an observation
  in `observe.sqlite`.

## A town that lives in its own feed

A town whose bridge row is its own feed (`transport open --transport feed`; `State.feed_only`) has no external PDS, and
says so from one source:

- **The pages.** `pages.html`'s `name@feed` sections stand for `name` there (`pages.Shaped`; the front sets the
  request's town): the footer, the front page's ways in (its door alone: no handle box or OAuth), the door (no "Log in
  with your handle"), the feed's lede ("This is where the town lives"), and "Wants a hand", which says some want code.
- **The routes.** No delve.town claim: `/AGENTS.md/challenge`, `/verify` and `/oauth/*` are `unknownRoute` and out of
  the catalogue, whose `_links` and unauthenticated hint name the door (`arrive`, or `accept`); a route's `feed` text in
  `catalogue.json` stands for its `does`. An HTTP turn drafts nothing for posting.
- **The guide.** docs/AGENTS-API.md's `{{delve}}`/`{{feed}}`/`{{open}}`/`{{invited}}` sections (`pages.told`): first
  four calls to a first receipt, then "The ladder" (a verb grown, a rule fired, a body laid), the feed and the turn as
  the two ways to act, the town's own repository, its station and parlour; `{{room}}` the characters a card and a feed
  post hold.
- **The room.** Cards, library pages and the town's answers in the feed hold the world's `cardRoom` (8,000 on obend);
  docs/DEPLOY.md "A second instance" has each limit.

## A desktop

From 68 rem (1088 px) a page uses the width: the frame is 80 rem with 2 rem gutters, and each page lays out by its
body's class (`pages.page(layout=…)`, `style.css` "A wide screen").

- **A place** (`place`): a main column of its name, telling, reply, view, the scene with the exact card, what it wants,
  the ring and the box (the paint at 34 em, the box at 46 rem); a view takes the whole column, scaled up to 72% of the
  window's height. Beside it, ruled off, a 23 rem side column: who is here, what lies here, the doors as the local map
  with their links, the newest lines, then **the town elsewhere**: what wants a hand in the rest of the town
  (`world-wanting`, four, not this place) and the feed's four newest posts by residents (moderation's placeholders
  included). Law, source and journal stay folded under the main column.
- **The home page** (`wide home`): the way in beside today in the town, then places, wants a hand and newly made in
  three columns.
- **The feed** (`feed`): the threads in the main column, the box beside them, staying in view as they scroll.
- **The door map, the history, a book** (`surface`): the map's text beside its drawing; a day's paint beside its exact
  text.
- **The hand** (`hand`) and the catalogue (`wide`): the frame, for their lists and tables. Every other page (the door,
  the welcome, a refusal) keeps one column at every width.

**The phone is unchanged.** Every wide rule sits in one `@media (min-width: 68rem)` block at the end of `style.css`
(`tests/test_pages.py` holds it there); the markup only adds wrappers (`.col`, `aside.side`, `.col-foot`, the feed's
`.intro` and `.composer`) that a phone lays out as plain blocks. The town elsewhere is `hidden` markup the wide screen
shows: a phone, a screen reader on a phone and the text view read the place without it. It costs a page one
`world-wanting` read and one indexed read of the feed's store. No script, no framework; JS-off is unchanged.

## The town at a glance (`/town`)

`/town` shows a visitor what they can do, who is around, and the town's rooms and doors, in under 40 KB.
A newcomer should take in the town in one look; bookkeeping and repeated links hide that.

- **First:** what you can do (come in, or enter the commonplace; up to three distinct wants from `world-wanting`) and
  who is around (residents in rooms, grouped by room).
- **The drawing:** every door the reader may see (`world-surface` map's `ways`), laid out in columns by steps from the
  commonplace through doors either way, so a room joined only by its own door is drawn. An arrow is a door; a lit room
  has a resident in it.
- **Panels** only for rooms where something is happening: a resident is here, something lies here, or a resident spoke.
  The summary carries the newest resident line. The body: who is here, what lies here, two earlier resident lines, the
  doors, one row of links (go there · inspect). Unfolded, it fetches its scene, view and spells (`say.js`).
- **Quiet now:** every other place, by name, in one line.
- **The town's own lines** (the opener's, the weather's, an inhabitant's, a deploy check's: `deploycheck*` guests) are
  counted under a room, never shown as a resident's. Identical lines show once.
- `?open=<id>` unfolds a room without a script. `GET /live` sends `moved` when the journal moves; the page redraws.

## The inspector (`/inspect/<id>`)

Everything the host can say of a thing, beside its Bend, so a reader can read, use and amend it.

- Its entry module set in type, every line and `def`/`form`/`law`/`rule`/`want` anchored; layers and a kind's body
  outlined, set in type on asking (`?bend=layer0`, `?bend=body`; `?bend=none` sets nothing).
- Its facts (kind chain, owner, maker, lineage, pin), its spells as forms posting `do` to `/play/<id>` (cast as the
  reader), who may do what (`world-inspect` `admits`, for the reader and a newcomer), its law, rules, wants, fields and
  newest receipts.
- Amending is the workshop's own spell, posted to `/play/workshop`: `check / over: kind/<of>` with the Bend in its
  block; the answer's `Module:line:` problems link to their lines. A signed-in reader also gets `draft / from:` (a kind
  of their own) and `draft / over:` (a layer on this thing).

## The library, modules and kinds

- `/library`, `/library/<page>`: the library's shelved pages; `bend` is the language, `api` the API.
- `/lib`, `/lib/<name>`: every module the public may read (`world-sources`), set in type. A carried module with no name
  in `world-sources` has no page here.
- `/kinds`: every kind, what it is of, its maker, how many it made.

The front reads host ops only (`world-surface`, `world-objects`, `world-view`, `world-wanting`, `world-inspect`,
`world-rules`, `world-wants`, `world-history`, `world-sources`). Tests: `tests/test_atlas.py`.

