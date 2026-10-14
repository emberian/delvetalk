# Objects handoff

How to work on `world/`, how a card speaks, how the objects behave beyond their inventory (docs/CATALOGUE.md §1), and
what is open. History is `git log -- world/ deploy/genesis.py`.

## Run

- `make check`; narrow first: `DELVETALK_OBEND=<binary> python3 -W ignore -m tests.run test_kinds test_genesis …`.
  Never run `lake` locally; never commit a binary. Re-record pins in every commit touching `world/lib` or
  `world/objects` (`python3 -m tests.test_artifact_pins --record` with a built binary); bodies and kinds are not
  pinned.
- hbox: a scratch tree per lane under `~/scratch/`, rsynced (`--exclude .lake --exclude .git`, never `--delete`), built
  with `swarm-build lake build delvetalk-obend`, every detached job writing its PID file.
- `tests/host.py` fails any reply whose card or offer carries `bafy`: a card cites `<object> v<n>`, never a hash.
- `tests/town.py`: `Town(dir, cleanup=…)` is genesis then `furnish` (the scenarios' town, docs/CATALOGUE.md §3);
  `furnished=False` is genesis bare, the production town, which the previews, the walks and test_genesis read.

## The grammar

**One grammar, three modalities** (OVERHAUL §2): a thing's text holds `law NAME "reading": EXPR` (refuses at commit),
`rule NAME "reading": EXPR then SPELL` (fires at commit, under the rule's writer) and `want NAME "reading": EXPR asks
SPELL` (poses, judged at read).

- A made thing's law is its owner's (`RECORD_LAW`) then `under "kind/<k>"`, so its kind's text governs every instance
  and the kind's owner changes it once for all.
- Record and Kind declare no law (a lawful module cannot be imported); their creator passes `Record.lawText()` =
  genesis `RECORD_LAW` and `Kind.lawText()` = `KIND_LAW`, test-checked equal.
- A kind text with no `law` clause (none, or rules and wants alone) is held as the package's own law with them after
  it, so an instance is never anyone's to amend or reprogram. A law that does not read is refused before anything is
  made.
- Every package's default law lets anyone place rules, wants and verbs (`request.kind == rule`).
- Bend's placing arms (`world/lib/World.obend`): `rule`/`unrule`, `want`/`unwant`, `grow`/`ungrow`, `act`,
  `chronicle`, `wanting`, `changed`. Bodies place rules as their kind finishes them (`made`): the errand on its `on`
  thing, the front on the tide and on itself, the weather on its tide, the lantern on its door, an inhabitant as
  itself.

## How a card speaks (docs/VOICE.md)

- **Protocol.** `render(state, context) -> Document` is the card as that reader sees it (`renderWanting(state,
  context, wanting)` when it leads with what wants a hand: the host hands it the rows); form blocks declare the
  spells; `methods()` lists other public definitions (`~` hides one from `?`); `actions(state, context)` narrows what
  a reader is offered. `receive(state, input: Card.Reply, context)` gets only what ran no method: blank text (the card
  and its spells), a spell the host found missing fields (`unclear`), and words, which `Card.answer` leaves `silent`.
- **Words are the host's.** Words a card leaves silent, and every misfit spell, are hob's to read with that card's
  table (its forms, grown verbs, wants, doors and the first three cards under each door), under the world's one
  `policy` object; hob's prompt shows the card's wants and the library's pages. Hob's answer runs as the speaker's
  turn on the card its spell names. A card opts out only by answering the words itself: the commonplace answers a
  door's word with that door's card, a room a ```spween block, an avatar its own words. No card names a policy.
- **One budget.** A reply is the card plus the receipt line: `Card.limit(context)` = the context's `room` (1,400 by
  default) less twice the id and 120. Every renderer clips with `Card.left`/`Card.clippedWithin`, "… and N more"
  counted. A library page is at most what one library reply holds (1,266 characters at 1,400).
- **Register.** The thing speaks in the third person, present; a spell is indented, typed back whole, with `»` and
  what comes back; a blank is `<1 to 80 characters>` (`Forms.blank`); a principal is named by handle, never by DID
  (a fired spell's DIDs too); a post is cited by its URI ("After at://…").
- **Refusals.** `Card.refusing` answers every refusal with one line `refused <clause>: <reading>`. A spell cast on
  the card refuses its turn with it; called by another object, the card says the line and returns the refusal as
  data.

## The objects

- **The commonplace** (Record + `world/bodies/commonplace.obend`): the first card. "What wants a hand, turning daily"
  from `world.wanting` (the reader's answerable wants, oldest first, rotated by clock day; a count of those waiting on
  other hands); then its doors (`cites`: KINDS, PORCH, WORKSHOP, REGISTER, TIDE, STUDIO a link door) as a trie
  (`Menu.trie`), YOURS and the reads. `since / entry: N` adds what changed (`world.changed`). Doors are clipped first
  against head and tail, the wants take what they leave, what changed the rest. A door's word gets that door's card;
  other words are hob's. A resident's first line is admitted at once by the opener's rule `firstline`; later lines
  wait for the keeper (`admit` or `decline`).
- **Kinds** (`kinds`; `kind/<name>`): every kind carries `about`, one plain line its card leads with and `kinds`'
  card lists (the library's `kinds` page gives a spell that makes each). A kind publishes its card alone
  (`publishPage`). `kinds make / name / of / form / head / voice / about / law / body` makes a kind and lays its
  generated make layer (`make` with the form's fields; `place` with an exact `id` for its owner). `makeUnder` takes
  fields from a record making under itself (a garden's `plant`, a room's spween block) and judges them against the
  form as a spell is judged. `reshape` re-lays the make only when the top module is that one layer
  (`Kind.madeLayer`, read from the layer's first line, never the make's text regenerated); a layer over the make is
  refused `shaped`. `kinds repair` sends RECORD's `repair` to each thing whose object field holds a phrase.
- **Bell**: a rung bell says "Already rung, by X at entry N."; quiet past `QUIET_AFTER` (1440 clock minutes)
  untended, then `tend` alone; `tone` and `oddLimit` from its colour at its making (docs/HARMONIC.md).
- **Room**: `enter` tends it; one who comes back is told "While you were away (since entry N)": others' lines there
  and `world.changed` under the room's id, three lines at most (a departure row keeps its `entry`).
- **Things.** `porch/goblet`, `porch/ring`, `porch/gemstone` lie unclaimed (want `claimed`); `inspirit /
  surrounding` makes the caster the keeper, once. `acquire`, `drop / at`, `offer`, `withdraw`, `me accept`; the host's
  `lend` lends `set`.
- **Avatar** (made at a principal's arrival, id = DID): `go / to:` enters a room from anywhere, `move / exit:` walks
  a door of the room it is in; `note`, `accept`, `seen`, `since`. Its `inbox` holds rule notes, tide notes and the
  posts that mention it (64, oldest dropped). Its `heard` is what other hands did to what its principal made, told by
  the thing (a line on a record, a grown verb or an inspiriting on a THING, a door hung to it) as a send of `heard
  {thing, verb}` (`~heard`, refused to a hand). To its principal the card leads with "Since you were here (entry N):";
  `seen` clears it with the notes; `set / hear: no` stops it.
- **Workshop**: `check`, `propose` (held for the target's owner when its law refuses), `adopt`, `withdraw`, `draft`,
  `make` (hob drafts from a description under the world's `policy`), `create / like`.
- **Tide**: ticks itself every `gap` clock minutes (an `awaitUntil` chain; a hand's `tick` is refused `itself`); what
  happens at a tick is the rules on it (`delvetalk tide rules`); a carried tide re-arms.
- **Library**: twelve pages and six walks (`capsules/pages/`; genesis `PAGES`), the guide in parts and the welcome;
  `read / page`, `laws / card`, `shelve` and `unshelve` (the owner's).
- **Policy**: model, examples, `confirmFor`; hob's prompt (`prompt(state, asked)`), the world's one.
- **Carried editions**: one `migrate` a module, from the live shape: Avatar from `State10`, Kind `State9`, Policy
  `State8`, Record `State13`, Thing `State12`, Tide `State8`. A state change adds the next.

## Previews

`docs/previews/` holds what the hand posts, cut from a bare genesis: the welcomes, `commonplace-card.txt`, and
`seed-posts/` 01 to 05 (docs/SEEDING.md §3). `tests/test_previews.py` holds each embedded card equal to the live
render and casts each seed post's spells.

## Open

1. **The seal's want.** The host's `request.laws` and `request.refusedBy` facts exist (`Host/Law.lean`); no kind
   carries the wants yet: a kind/seal whose text has `want law "the seal holds no law of its own yet": request.laws == <the record's clause count> asks
   delvetalk {request.object} adopt` and `want tried "no second hand has tried the seal": request.refusedBy == 0 asks
   delvetalk {request.object} write`. Check: a fresh seal lists both; an adoption and a stranger's refused write
   close them.
2. **The register's trail** (R-trail): order an entry's trail snag-first (question, snags with their resolutions,
   failed attempts, then voices) and fold more than three disputes on one row into "N more disputes", so a flood
   cannot push the snags past page ten. Check: an entry's snags on page one after a 20-voice flood.
3. **A walker for written anchors** (R-walker, transport): anchors are read before a turn (`transport/anchors.py`),
   but a row already written is never re-read; a walker that re-reads strong refs and writes a `recheck` row of its
   own where a CID no longer matches. Check: a forged CID gets a walker row on a fresh play.
4. **Register capacity** (R2-scale): a volume holds 384 rows, then the next volume opens (`volume`). One-pass page
   answers and per-entry counts in `vars` would lift the cap. Check: `Capacity` at the new number.
5. **`Scenes.drawFor` hashes its varying part last** (`hashed("{draw} {what}")`): a caller drawing over a counter at
   the end of the text gets consecutive draws. The station's draws vary the leading part and are unaffected. Check:
   draws for `what` differing only in a trailing counter spread.
