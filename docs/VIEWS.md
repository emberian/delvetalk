# Views: a thing drawn live, and clicked

The owner, 2026-10-13: "support some kind of View or HTML aspect in the obend world so that stuff gets rendered live and
is maybe even mildly interactive. I'd like to make a wesnoth-lite in there." Written on `lane/views` from foundation
c9bd3c80. It binds `world/lib/View.obend`, `transport/views.py`, the `world-derived` op and `/live/<id>`. Screenshots
(`docs/web/views-*`, a genesis town on hbox, three guests): the counter and the hexboard at 1280 and 390 px, after a
click, after another's click arrived live, as a stranger sees them, and with scripts off.

## 1. The decision: a declarative view, drawn by the town

Security is the first constraint. A page on the town's origin runs with every signed-in resident's session cookie in
reach of its forms, and the hand behind it; any resident-authored HTML or script served there is cross-site scripting
against all of them. Two shapes were weighed.

**(A) A declarative View, drawn by the host.** A body returns data in a closed vocabulary (text, stacks, buttons,
grids, hexes, shapes, a table, a bar); the front turns it into HTML from its own tables. Nothing a resident writes
becomes a tag, an attribute name, a style, a script or an address. Safe by construction: the encoder has no path from
a word to markup, and a test puts an attack in every word and attribute and reads the output back tag by tag.

**(B) Raw HTML/JS in a sandboxed iframe** on a separate cookie-less origin (`srcdoc` with `sandbox="allow-scripts"` and
no `allow-same-origin`), speaking to the page only by `postMessage`, which the page would turn into a spell the viewer
confirms. It draws anything, and costs a second origin kept cookie-less, a confirm on every click (else the frame casts as the
viewer at will), no JS-off or text reading, nothing a law or a test can read, and a frame that can still phish or hang a
phone.

**Chosen: (A) as the core, and (B) not built.** The game needs hex tiles with terrain, discs and labels for units,
clickable cells, numbers, a bar for HP, a table for a roster, and a few drawn shapes; (A) expresses every one (§7).
What (A) cannot do is animation and free-form art. If that is ever wanted, (B) comes fenced exactly as above, its
messages mapped to the thing's own offered forms (§3), never to text.

## 2. The language (`world/lib/View.obend`)

A body defines `view(state: State, context: Abi.Context) -> View.View` and names it in `views()`. It is an ordinary
derived view (FOUNDATION §9): pure, of the committed state and the reader's Context, so the same state draws one view
for a member and another for a stranger, and another object can read it with `viewDerived`. No second mechanism.

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

- **Tones** are words, never colours: the page's own (`ink`, `muted`, `paper`, `leaf`, `amber`, `violet`, …), players'
  (`red blue green orange purple cyan magenta yellow`, `View.player(n)`) and terrains (`grass forest hills mountain
  water shallows sand snow cave village castle keep road`). Each is a class in `style.css`, set for both palettes; an
  unknown word draws as the default.
- **Numbers** are naturals in the drawing's own units; a path's `d` keeps only commands and numbers.
- **Images** are `data:image/png|gif|jpeg|webp;base64` (no SVG), or an address on a host the town lists
  (`IMAGE_HOSTS`, empty: no view can make a reader's browser call a third party).
- **Hexes** are pointy-top, odd rows half a tile right, numbered along each row from the top left: the layout
  Wesnoth's maps use turned a quarter, and the one the hexboard's card prints in letters.
- Helpers (`say`, `button`, `tile`, `tiles`, `two` … `five`, Bend having no list literal) keep bodies short.

**Bounds.** The host answers at most `Limits.maxViewBytes` (256 KiB of wire JSON; past it `viewTooLarge`, never cut), in
one turn's ticks (`budget` past them), nesting as deep as a Document's wire (a 4,096-cell list), and names a failure's
cause in `detail` for the author. The front draws at most `Limits.maxViewNodes` (4,096) nodes, 24 deep, 4,000
characters a text, 8 a tile label, and says when it stopped. Both numbers are the host's (`bounds`); the front restates
neither.

## 3. Acts: a click is the reader's turn

A button, a box (`ask`) or a tile carries an Act: the name of one of the thing's own forms and the fields it fills. The
front draws it only if the host offers that form to this reader (`world-inspect`'s `offered`, after the law and the
card's `actions`), every field is declared, every needed one is given and each value fits its bound (a natural in
range, a text of one line within its length, a choice among its words); otherwise it is drawn inert. Clicking sends
`do=action?field=value&…` to `/play/<id>`; the front checks it again the same way and casts the form directly, as the
agent API's `fields` call does, under the reader's own principal and intent. The host judges it as any spell: the law,
the form's bounds, the method. One click is one turn, journaled, its receipt shown open where it was clicked.

A view cannot make a reader cast on another card, cast a helper or an unoffered action, slip a second spell line into
a field, or act as anyone but the one clicking. A thing's own form, labelled by its author, does what its body says, as
a typed spell does: its exact spell is the button's tooltip and text-view line, and `ask` keeps **Try it first**.

**Without a script** a button is a form that posts (the front adds the session's CSRF token to it as to every form),
and a tile is a link to `/play/<id>?say=<its spell>`, which fills the box to send: two steps, nothing hidden. `?text=1`
prints every button as its form (`POST /play/counter`, `do: plus`, `[ + ]`). **With `say.js`** a tile or a button is
one click: the form is fetched, and the reply (with its receipt) and the new view are put in place.

**The page** that draws a view carries a Content-Security-Policy: scripts, styles and connections only from the town,
images only from it and `data:`. A drawing bug cannot run script or call out.

## 4. Live: `/live/<id>`

The view section names its channel: `data-live="/live/<id>?v=<version>"`. `say.js` opens an `EventSource`; the front
holds the stream (55 s, then the browser comes back with `Last-Event-ID`) and sends `event: view`, `id: <version>`,
the view drawn for that reader, whenever the thing moves past the version the page drew. Changes come from the
journal's tail: one thread in the front asks the host's height every 0.2 s while any page listens and wakes every
stream when it moves; each stream then asks only its own thing's version (`world-derived`) and redraws if it changed.
With no script, or past 16
streams at once (each holds one of the front's 48 workers; past it `503`), the page is as it was drawn, and fresh at
every load.

The edge must pass the stream unbuffered: the front sends `Cache-Control: no-cache, no-transform` and
`X-Accel-Buffering: no`; Caddy flushes `text/event-stream` at once, and its `encode` must leave that type alone (check
at deploy, `curl -N`). At scale, the tail follower is replaced by the firehose's event log (ATPROTO §1), which already
names each height's writes, so a stream wakes only for its own thing.

## 5. Moderation

A view is a derived value of the thing's state, answered by the same host as its card: an object the root has hidden
answers `denied` to `world-derived` as to `world-card`, and the automatic moderation's text redaction (the automod lane,
`Screen.redact`) applies to `world-derived`'s reply where it applies to `world-card`'s; that lane's merge adds the op to
its list. Every word of a view is then drawn as escaped text, so a hidden text's placeholder is all a page shows.

## 6. The first slice, as built

- **Host** (`spec/Delvetalk/Host/TurnLoop.lean` `derivedOp`): `world-derived {principal, object, view}`, the derived
  view run for a reader outside a turn, as `viewDerived` is inside one; `Limits.maxViewBytes`, `maxViewNodes`. The
  kernel takes a `depth` limit (`Package.lean`), up to a Document's, so a long list of tiles validates.
- **Front**: `transport/views.py` (the encoder), the view on `/o/<id>` and `/play/<id>`, `do` on the play POST,
  `/live/<id>`, its catalogue entry, the CSP; `say.js` (live and one click); `style.css` (the tones).
- **Bend**: `View.obend`; `kind/counter` (`world/bodies/counter.obend`: `plus`, `minus`, never below nought, its count
  in the record's variable `count`, a line per move) and `kind/hexboard` (`hexboard.obend`: `place / cell: N` marks
  `hex N` for the placer, once a hex, RECORD's law keeping marks; each hand's colour the order it first placed; the
  card prints the board in letters). `deploy/genesis.py` `playthings` makes both kinds and places `counter` and
  `hexboard` (7 by 7) in an open town's genesis (obend's profile); a carried open town that lacks them gets them in the
  carry's refresh (`genesis.placed_playthings`, rows `placed`; an invited town such as gsb gets none).
- **Tests** (`tests/test_view_pages.py`, 13): deterministic drawing; an attack in every word and attribute read back
  tag by tag against an allowlist; the bounds; acts only of offered forms; `noView`, `viewTooLarge`, a 600-cell list;
  a click cast as its reader, a forged `do` refused; a hexboard placing replayed after a restart; no-script reading
  and acting; a live page told of another's click within a second (132 ms in the browser, Playwright).

## 7. Wesnoth-lite

A two-to-four-side skirmish on a hex map, played by residents in turns, every move a spell, every rule Bend under law.

**Kinds.**
- `world/lib/Hex.obend`: odd-r offsets, neighbours, distance, a bounded cheapest-path search over move costs.
- `world/objects/Battle.obend`, a base like RECORD (RECORD's schema has no mutable rows: marks only grow, and units
  move and bleed): `map` (terrain letters, row by row), `units: Relation<Unit>` keyed by id `{type, side, owner, at,
  hp, moves, attacked}`, `sides: List<Side>` `{name, owner, gold, villages, colour}`, `turn`, `side`, `seed`, and
  `lines`. A unit is owned by the resident who recruited it; a side by the resident who took its seat (`join / side:`).
- `kind/battle` (`of: battle`): the rules. `unitTypes()` (`{name, cost, hp, moves, attacks: [{name, damage,
  strikes, range}], costs per terrain, defense per terrain}`), `terrains()` (letter, tone, name, village/castle/keep),
  `start(scenario)`.
- `kind/scenario`, its text a spween-like file read in Bend (as `Spween.obend` reads a scene): front matter (`id`,
  `title`, `turns`, `gold`, `income`), the map as rows of terrain letters, `side` lines (`north: keep 3,1; leader
  Lieutenant`), `victory` lines (`leader`, `turns`). `delvetalk kind/battle make / scenario: kind/scenario/ford`.

**Spells, judged by laws.** `move / unit: 7 / to: 41`, `attack / unit: 7 / target: 12 / with: sword`, `recruit /
type: Spearman / at: 18`, `end`. The method computes and refuses by name (`notYourTurn`, `notYours`, `tooFar`,
`zoneOfControl`, `occupied`, `notAdjacent`, `noGold`, `notACastle`); the package's Bend `law(old, new, request)` judges
the same invariants on every write, so a proposed write or a layer's bug cannot move a unit through a zone of control
or spend gold a side lacks. Clause laws carry what reads in one line: `law seat "a side is played by its owner":
request.method == "end" implies request.subject == …`.
- *Movement*: cheapest path within `moves` by terrain cost; entering a hex next to an enemy ends movement (zone of
  control).
- *Combat*: attacker and defender strike alternately, each strike hitting with the defender's terrain defense as its
  chance, drawn from `Scenes.turnDraw(height, principal, intent)` and `drawFor(draw, "strike N")`: the seeded draw
  spween's scenes use, the turn's own entry, so replay reproduces every hit and nobody can re-roll.
- *Recruiting*: a leader on a keep recruits into a connected castle hex for the type's cost.
- *Economy*: at a side's turn, gold += 2 + villages; a village is captured by ending a move on it.
- *Turns*: `end` passes to the next side; a seat may instead follow the tide (a rule on the tide: `request.method ==
  "tick" and new.ticks % 6 == 0 then delvetalk battle/1 end`), so a slow table plays one turn an hour while nobody is
  up. A battle `wants` its next side's hand, which the commonplace offers.

**The view.** `hexes` with each tile's `fill` its terrain tone, `mark` the unit's side colour, `label` its glyph and
hp (`Sp 24`), `title` its type and stats; a `row` per side (`progress` gold and villages); a `table` roster; the last
lines of the battle. One gap: choosing a unit and then a hex needs a pointer that is not a write. **Stage 2 adds
looks**: a tile may carry `look` fields instead of an Act; choosing it is a GET (`?look.unit=7`) and the host passes
the look to `view(state, context, look)` as a third argument, fitted to its type like the Context. The view then marks
the unit's reachable hexes and attack targets as tiles whose Acts are `move` and `attack`. Nothing is written until the
second click.

**What residents add.** A kind `of: kind/battle` whose layer overrides `unitTypes()` with `Lists.concat(Super.unitTypes(),
…)` adds a unit; `terrains()` likewise; a `kind/scenario` file is a new map; a faction is a kind whose `recruits(side)`
names its types. All go through `kinds make` and the workshop's checker (AUTHORING §5), are credited by `madeFrom`,
and leave the law the base kind's: a new unit cannot outrun the movement law.

**Lanes, each a commit with its control.**

| # | Lane | Control |
| --- | --- | --- |
| 1 | views (this) | §6's tests |
| 2 | looks: `world-derived {look}`, `?look.` links, tiles with a `look` | a board highlights a hex's neighbours on one GET, journaling nothing |
| 3 | `Hex.obend` and `Battle.obend`: map, units, move with zone of control, `end`, the Bend law | two seats move in turn; a move through a ZOC is refused by the method and, proposed, by the law; replay |
| 4 | combat by the seeded draw; recruiting, gold, villages | a scripted battle's hits equal across a restart and a carry; a recruit without gold refused |
| 5 | `kind/scenario` and its reader; victory | the two-side `ford` scenario played to a leader's death in tests |
| 6 | the view: terrain, units, sides, looks to move and attack; screenshots at 390 and 1280 px | a playtest's moves are all clicks |
| 7 | tide turns, wants for the next hand, residents' unit kinds | a resident's `kind/skirmisher` recruits in obend |

## 8. Not decided here

Whether the exact card and Lately also go live (the view alone streams; after a click the folded card is a version
behind until reload); sound and animation ((B), or a new fenced node); an `IMAGE_HOSTS` entry.
