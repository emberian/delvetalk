# Views: a thing drawn live, and clicked

A body may give its thing a view: data in a closed vocabulary that the web front draws beside the exact card, live,
with buttons and tiles that cast the thing's own spells as the reader. The code: `world/lib/View.obend`,
`transport/views.py` (the encoder), the host's `world-derived` op (`TurnLoop.derivedOp`), `/live/<id>`, `say.js` and
`style.css`. The library's page is `capsules/pages/views.txt`.

## 1. The decision: a declarative view, drawn by the town

A page on the town's origin has every signed-in resident's session in reach, and the hand's; resident-authored HTML or
script served there is cross-site scripting against all of them. So a view is data, never markup: a body returns a
View, and the front turns it into HTML from its own tables. Nothing a resident writes becomes a tag, an attribute
name, a style, a script or an address. A test puts an attack in every word and attribute and reads the output back
tag by tag against an allowlist.

Raw HTML/JS is not built. If animation or free-form art is ever wanted, it comes only in a sandboxed iframe on a
separate cookie-less origin (`srcdoc`, `sandbox="allow-scripts"`, no `allow-same-origin`), its `postMessage`s mapped to
the thing's own offered forms (§3) and confirmed by the viewer, never to text.

## 2. The language (`world/lib/View.obend`)

A body defines `view(state: State, context: Abi.Context) -> View.View` and names it in `views()`. It is an ordinary
derived view (FOUNDATION §9): pure, of the committed state and the reader's Context, so the same state draws one view
for a member and another for a stranger, and another object can read it with `viewDerived`. A `def view` of any other
type is refused by the checker with the shape it needs.

    sum View:
      text: {value, tone, size}        heading: {value}          rule: {}
      stack: {items: Views}            row: {items: Views}
      button: {label, act: Act, tone}  ask: {label, act, field, placeholder}
      progress: {value, max, label, tone}                         table: {head, rows}
      grid: {columns, tiles: Tiles}    hexes: {columns, tiles: Tiles}
      drawing: {width, height, shapes: Shapes}                    image: {source, alt, width}
    record Tile: {fill, mark, label, title, act: Act}
    sum Shape: circle | rect | line | path {d} | label
    record Act: {action, fields: List<{name, value}>}

**Tones** are words, never colours: the page's own (`ink`, `muted`, `paper`, `leaf`, `amber`, `violet`, …), players'
(`red blue green orange purple cyan magenta yellow`, `View.player(n)`) and terrains (`grass forest hills mountain water
shallows sand snow cave village castle keep road`). Each is a class in `style.css`, set for both palettes; an unknown
word draws as the default.

- **Numbers** are naturals in the drawing's own units; a path's `d` keeps only commands and numbers.
- **Images** are `data:image/png|gif|jpeg|webp;base64` (no SVG), or an address on a host in `views.IMAGE_HOSTS`, which
  is empty: no view makes a reader's browser call a third party.
- **Hexes** are pointy-top, odd rows half a tile right, numbered along each row from the top left.
- Helpers (`say`, `button`, `tile`, `tiles`, `two` … `five`; Bend has no list literal) keep bodies short.

**Bounds.** The host answers at most `Limits.maxViewBytes` (256 KiB of wire JSON; past it `viewTooLarge`, never cut),
within one turn's ticks (`budget` past them), nesting as deep as a Document's wire (a 4,096-cell list validates), and
names a failure's cause in `detail` for the author. The front draws at most `Limits.maxViewNodes` (4,096) nodes, 24
deep, 4,000 characters a text, 8 a tile label, and says when it stopped. Both numbers are the host's (`bounds`); the
front restates neither.

## 3. Acts: a click is the reader's turn

A button, a box (`ask`) or a tile carries an Act: one of the thing's own forms and the fields it fills. The front draws
it live only if the host offers that form to this reader (`world-inspect`'s `offered`, after the law and the card's
`actions`), every field is declared, every needed one is given and each value fits its bound; otherwise it is drawn
inert. Clicking sends `do=action?field=value&…` to `/play/<id>`; the front checks it again and casts the form directly,
as the agent API's `fields` call does, under the reader's own principal and intent. The host judges it as any spell.
One click is one turn, journaled, its receipt shown where it was clicked.

A view cannot make a reader cast on another card, cast a helper or an unoffered action, slip a second spell line into
a field, or act as anyone but the one clicking. A button's exact spell is its tooltip and its text-view line, and `ask`
keeps **Try it first**.

**Without a script** a button is a form that posts (with the session's CSRF token), and a tile is a link to
`/play/<id>?say=<its spell>`, which fills the box to send. `?text=1` prints every button as its form (`POST
/play/counter`, `do: plus`, `[ + ]`). **With `say.js`** a tile or button is one click: the reply (with its receipt) and
the new view are put in place.

**The page** that draws a view carries a Content-Security-Policy (`VIEW_POLICY`): scripts, styles and connections only
from the town, images only from it and `data:`.

## 4. Live: `/live/<id>`

The view section names its channel, `data-live="/live/<id>?v=<version>"`. `say.js` opens an `EventSource`; the front
holds the stream 55 s (then the browser returns with `Last-Event-ID`), sends keep-alives every 15 s, and sends `event:
view`, `id: <version>`, the view drawn for that reader, whenever the thing moves past the version the page drew. One
thread follows the journal's tail (the host's height every 0.2 s) while any page listens and wakes every stream when it
moves; each stream asks only its own thing's version (`world-derived`) and redraws if it changed. Past 16 streams at
once (each holds one of the front's 48 workers; `503` past it), or with no script, the page is as drawn and fresh at
every load (`transport/http.py` `LIVE_MAX`, `LIVE_SECONDS`, `LIVE_BEAT`, `TAIL_STEP`).

The edge must pass the stream unbuffered: the front sends `Cache-Control: no-cache, no-transform` and
`X-Accel-Buffering: no`; Caddy flushes `text/event-stream` at once, and its `encode` must leave that type alone (check
at deploy with `curl -N`). The town's own channel, `GET /live`, sends `moved` when the journal moves (docs/WEB.md "The
town at a glance").

## 5. Moderation

A view is answered by the same host as its card: an object the root has hidden answers `denied` to `world-derived` as
to `world-card`, and the automatic moderation's redaction applies to a view's reply as to a card's (`Session.lean`).
Every word of a view is drawn as escaped text, so a hidden text's placeholder is all a page shows.

## 6. What is built

- **Host**: `world-derived {principal, object, view}`, a derived view run for a reader outside a turn, as `viewDerived`
  is inside one; `Limits.maxViewBytes`, `maxViewNodes`.
- **Front**: the view on `/o/<id>` and `/play/<id>` (on a wide screen it takes the whole main column, scaled up to 72%
  of the window's height), `do` on the play POST, `/live/<id>` and its catalogue entry, the CSP.
- **Kinds**: `kind/counter` (`world/bodies/counter.obend`: `plus`, `minus`, never below nought, a line per move) and
  `kind/hexboard` (`hexboard.obend`: `place / cell: N` marks `hex N` for the placer, once a hex; each hand's colour the
  order it first placed; the card prints the board in letters). `deploy/genesis.py` `playthings` places `counter` and a
  7-by-7 `hexboard` in an open town's genesis; a carried open town that lacks them gets them on refresh
  (`genesis.placed_playthings`); an invited town gets none.
- **Tests**: `tests/test_view_pages.py`: deterministic drawing, the attack read back tag by tag, the bounds, acts only
  of offered forms, `noView`, `viewTooLarge`, a 600-cell list, a click cast as its reader, a forged `do` refused, a
  placing replayed after a restart, no-script reading and acting, a live page told of another's click within a second.

## 7. Open

- **Looks.** Choosing a unit and then a hex needs a pointer that is not a write: a tile carrying `look` fields instead
  of an Act, chosen by a GET (`?look.unit=7`) and passed to `view(state, context, look)` as a third argument. Not built.
- **Wesnoth-lite**, the motivating game: a two-to-four-side hex skirmish played in turns, every move a spell (`move`,
  `attack`, `recruit`, `end`), every rule Bend under law (a base kind with mutable units, a Bend `law` judging zone of
  control and gold on every write, hits from the turn's seeded draw so replay reproduces them, scenarios as files,
  residents' unit kinds as layers). It needs looks first. Not built.
- Whether the exact card and Lately also go live (only the view streams; after a click the folded card is a version
  behind until reload); sound and animation; an `IMAGE_HOSTS` entry.
