# Objects handoff

The objects lane's surface as it stands (lane/rewrite12, 2026-10-11): what is in `world/`, how a card speaks, what
genesis makes, and what is open. History is the git log (`git log -- world/ deploy/genesis.py`); this file says only
what is.

## Run

- `make check`; narrow first: `DELVETALK_OBEND=<binary> python3 -W ignore -m tests.run test_kinds test_genesis …`.
  Never run `lake` here; never commit a binary. Re-record pins in every commit touching `world/`
  (`python3 -m tests.test_artifact_pins --record`).
- persvati down: hbox, a lane directory under `~/scratch/`, the foundation binary
  `~/scratch/dt-foundation/.lake/build/bin/delvetalk-obend`; rsync the tree, run `tests.run`, remove the directory
  when the lane ends.
- `tests/host.py` fails any reply whose card or offer carries `bafy`: a card cites `<object> v<n>`, never a hash.

## The world

`world/objects/` (Avatar, Env, Kind, Library, Policy, Record, Thing, Tide, Wake, Workshop), `world/bodies/` (layers
over Record that a kind lays on each thing it makes: bell, bond, cistern, commonplace, door, garden, lantern, room,
weather), `world/lib/` (Card, Event, Form, Forms, Mentions, Menu, Plan, Policies, Relation, Rows, Scenes, Spell,
Spween, Text, World; `prelude/` Abi, List; `document/` Document). About 2,000 lines of libraries, 2,450 of objects,
1,200 of bodies.

**Kinds** (METAPHYSICS §5, §7). THING (`Thing.obend`: custody, offer and accept, copy, inspirit, a keeper, `lend`
and a `circle`), RECORD (`Record.obend`: lines keyed {author, n}, admissions, marks, doors, the made header, a scene
for rooms, things lying in it, tending), WAKE (`Wake.obend`: triggers as data, typed receivers, schedules), BOND (the
`bond` body over RECORD: countersignatures as marks, an amendment at rest), KIND (`Kind.obend`: a form, a law its
things are created under, a head and a body; `make` and the owner's `place`). PLACE folded into RECORD; Deal into
BOND; the directory into the commonplace.

**Lawful packages** (declare `law`): Env, Library, Policy, Thing, Tide, Wake, Workshop; Avatar and Thing keep a Bend
predicate (`def law`) beside it. Record and Kind declare none: a lawful module cannot be imported and every kind
imports the package it makes, so the creator passes the law (`Record.lawText()` = genesis `RECORD_LAW`,
`Kind.lawText()` = `KIND_LAW`). A made thing is created under `law kind "<kind>'s law holds": under "<kind>"`
(`Kind.lawOf`): the kind's `law` field governs every instance, and the kind's owner amends it once for all.

## How a card speaks (docs/VOICE.md)

- **Protocol.** `render(state, context) -> Document` is the card as that reader sees it (`Card.reads`,
  `Card.mine`); form blocks declare the spells; `methods()` lists other public definitions (`~` hides one from
  `?`); `actions(state, context)` narrows what a reader is offered (Kind offers `place` to its owner alone, Record
  `admit` to the keeper and doors to the owner). `receive` gets only what ran no method: `Card.Reply {text, post,
  fields, spell: Cast}`, or `Card.Heard` (with `misfit`) for a card that reads words (the commonplace, a room).
- **One budget.** A reply is the card plus the receipt line the bridge stamps (`Card.limit(context)` = 1,400 less
  twice the id and 120); every renderer clips with `Card.left`/`Card.clippedWithin`, "… and N more" counted. The
  library's pages are at most 1,266 characters (`shelve`'s body bound) for the same reason.
- **Register.** The thing speaks in the third person, present; nobody on a card says I (hob's lines are hob's, at
  a line's head). A spell is indented, typed back whole, with `»` and what comes back; a blank is `<1 to 80
  characters>`, `<up to 200 characters>`, `<amber, violet or silver>`, `<a number from 1 to 9>` (`Forms.blank`).
  A principal is named by handle (`Card.shown(did, handle)`, `Card.name`), never by DID.
- **Refusals.** Every refusal is answered by `Card.refusing(result, refusal, context)`: one line, `refused
  <clause>: <reading>` (`Card.refusalLine`), the reading carrying the next line to type when there is one; nothing
  is written. An object that called another gets the refusal back as data and passes it on without saying it again
  (Record's making, Avatar's moves, Thing's room calls). The turn is still admitted: see Open 1.
- **Words.** A card with a policy asks `world.interpret` (`Card.interpretation`); `Policy.prompt(state, asked)` is
  FLEX §2's prompt (hob's line, the card as the speaker reads it, its forms, the lexicon, held and misfit, the
  examples, five answers: spells, `ask:`, `card`, `say:` in at most two sentences, `none`), or, when one offered
  form takes source, the drafting prompt (no card, no spell, the `object` page's package, one ```obend block back).
  Prose a card does not take is handed on to the commonplace (`Card.handingOn`).

## The objects

- **The commonplace** (Record + `bodies/commonplace.obend`): the first card. Its doors are its `cites`
  (`Card.Doorway {label, to, description, examples}`), drawn as a trie (`world/lib/Menu.obend`): KINDS, WORKSHOP,
  GARDEN, ROOMS, TIDE, PORCH, ANTHOLOGY with one spell each, STUDIO (a link door), then YOURS; `since / entry: N`
  adds what changed (`world.changed`), a principal's own cards left out. It greets each principal once under hob's
  line, reads words with the policy (macros first, then the model), runs a proposal on its door, answers a miss with
  the doors the words touched, at most hourly per speaker (`missed`, `due`).
- **Kinds** (`kinds`, of kind; `kind/<name>`): `kinds make / name / of / form / head / law / body` makes a kind and
  lays its generated layer (`Kind.layerSource`: `make` with the form's fields, and for a kind of things `place` with
  `id: text 1..64`); a law that does not read is refused `badValue` before anything is made (`Kind.lawChecked`:
  `law ` lines, each checked by `world.check` in a minimal package). `makeUnder` takes text fields from a record
  making under itself (a garden's `plant`, a room's spween block), judged against the form by `Forms.fault`.
- **Records with bodies.** bell (rain, tend, lines; rings at its seventh rain: the planter's wake, asked by the
  bell's `made`, calls `ring` on the row numbered 7 and notes the `rung` mark; quiet past `QUIET_AFTER` untended,
  then `tend` alone, by kind/bell's `alive`), garden (`plant` and `dig` make bells and cisterns under it; its
  weather line), weather (subscribes to its tide's ticks; rains on the garden's first 32 bells and writes the
  garden's weather), room and porch (the scene: enter, choose, leave, say, emote, whisper; presence by handle;
  unclaimed things to inspirit; a ```spween block makes a room under it), door (`knock` marks `open`), lantern
  (watches a door's marks), cistern (`pour`; `law level`), bond (parties by handle, countersign, withdraw; at rest it
  amends `amends` to `law`).
- **Things.** `porch/goblet`, `porch/ring`, `porch/gemstone` lie unclaimed on the porch; `inspirit / surrounding`
  makes the caster the keeper, once, and writes the porch's line. `acquire`, `drop / at`, `offer / to / until`,
  `withdraw`, `me accept / thing`; lenses `name`, `description`, `copyable`, `circle` (a bond at rest whose signers
  set it too); the host's `lend` lends `set`.
- **Avatar, Env, Wake** (made at a principal's arrival): the avatar is where it last entered (`go`, `move`), what it
  holds, its notes, its outbox and follows (`send`, `subscribe`, `watch`); the env takes mentions as events
  (`observe`, `seen`); the wake's triggers (`mention`, `keyword`, `rows`, `writes`, `grows`, `turns`, `remind`,
  `unwatch`) note the avatar or call a card.
- **Workshop**: `check` (a block, or a target's source), `propose` (held for the target's owner when its law
  refuses), `adopt`, `withdraw`, `draft` and `make` (a describer's package, held, then made with its lineage),
  `create / like` (a thing's copy).
- **Tide**: `tick` (gap 1; too soon `refused tooSoon`), `subscribe / every / note`; the opener's wake ticks it
  every 60 clock minutes.
- **Library**: six pages and five walks (`capsules/pages/`), `read / page` by name or a word of what was said,
  `laws / card` (inspect's law with readings, following `under` to a kind's law), `shelve` (the owner's).
- **Policy**: model, hob's system line, a lexicon, examples, macros, `confirmFor`; taught by its owner.

## Genesis (docs/GENESIS.md is the order)

`deploy/genesis.py`: the opener arrives; creates `policy`, `commonplace` (then its body), `tide`, `workshop`,
`kinds` (shaped), `anthology`, `library`; `kinds` makes `KINDS` (record, bell, cistern, room, porch, garden,
weather, door, lantern, bond); the hand places `HANDS` by spell (`garden`, `rooms` the Moss Gate, `porch`, `weather`,
`bell/1` the sixth bell); the garden cites its weather, the porch the sixth bell; `THINGS` lie on the porch; the
opener's wake runs `arrived` and the tide schedule; the library shelves `PAGES`; each door publishes its page.

## Previews

`docs/previews/` holds what the hand posts: `gsb-welcome.txt`, `zulip-welcome.txt`, `commonplace-card.txt` (the live
commonplace verbatim) and `seed-posts/01..05`. `tests/test_previews.py` holds each embedded card equal to a fresh
genesis's render and casts each seed post's spells, so a card change fails it until the preview is re-cut.

## Open, in order

1. **A refusal refuses the turn** (playtest 2's D6). Bend's `refuse` takes only a string literal
   (`ObjectiveBendElaborate.refuseCall`); the kernel's `refuse(<String expression>)` (host lane, lane/host19) lets
   `Card.refusing` end a cast turn with its line: `if context.caller == "" then refuse(refusalLine(r)) else
   tell(…)`, and each test asserting `("admitted", "refused")` becomes `("refused", …)` (a refused turn drafts the
   reason and the receipt's name, tested by probe). Check: `delvetalk kind/moss make / id: x` by a stranger is a
   refused turn whose draft is `refused notOwner: …` and the receipt name.
2. **`workshop make` drafts** (D3's host half). The host binds a reply that is one ```obend block to the offered
   form's source field (withFence's rule for interpretations); Workshop offers `check` alone. Check: the dry run's
   `workshop make / name: lamp / description: a lamp anyone lights` holds `#1`.
3. **`adopt / law:` takes law text** (F2's host half: TurnLoop's `adopt` and its usage, "<a kind's or a page's id>").
4. **The receipt names the card addressed** (D10's other half): `transport/bridge.py` `turn_root` names `kind/room`
   for a spell on `room/1`. Transport.
5. **`kind/orchard`** (METAPHYSICS §7.2's table: a room kind by another name, a head line only): add to `KINDS` once
   the third playtest is over (genesis's ids were held still while it ran). Check: test_genesis's kinds.
6. **Docs owned elsewhere that describe gone surfaces**: VOICE.md's surfaces table (Directory, Garden.confirmCard,
   hob's miss line now a `refused noPage` line), LIBRARY.md (the walk texts, `body 1..1400`, `submit`), SEEDING.md
   (Place, Deal, the clapper and the ledger). Voice lane.
**D6 unblocked (2026-10-11, lane/kernel16, edition 8):** `refuse(line)` takes a computed String; a card's refusal refuses its turn as `cardRefused` with the clause and reading parsed from `refused <clause>: <reading>` (else clause `card`). Next: `Card.refusing` becomes `refuse(refusalLine(refusal))`, and every method that announces a refusal with `tell` refuses instead.
