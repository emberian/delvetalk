# Objects handoff

The objects lane's surface as it stands (lane/rewrite14, OVERHAUL step 4; lane/attend, 2026-10-12): what is in `world/`, how a card
speaks, what genesis makes, and what is open. History is the git log (`git log -- world/ deploy/genesis.py`); this
file says only what is.

## Run

- `make check`; narrow first: `DELVETALK_OBEND=<binary> python3 -W ignore -m tests.run test_kinds test_genesis …`.
  Never run `lake` locally; never commit a binary. Re-record pins in every commit touching `world/lib` or
  `world/objects` (`python3 -m tests.test_artifact_pins --record` with a built binary; bodies are not pinned).
- hbox: a scratch tree per lane under `~/scratch/`, rsynced (`--exclude .lake --exclude .git`, never `--delete`), built
  with `swarm-build lake build delvetalk-obend`, every detached job writing its PID file.
- `tests/host.py` fails any reply whose card or offer carries `bafy`: a card cites `<object> v<n>`, never a hash.
- `tests/town.py`: `Town(dir, cleanup=…)` is genesis then `furnish` (the garden, the Moss Gate, the weather, the
  anthology and their doors, by ordinary spells), the scenarios' town; `furnished=False` is genesis bare, the
  production town, which the previews, the walks and test_genesis read.

## The world

`world/objects/` (Avatar, Kind, Library, Policy, Record, Thing, Tide, Workshop), `world/bodies/` (layers over Record a
kind lays on each thing it makes: bell, bond, cistern, commonplace, door, errand, front, garden, lantern, room,
weather), `world/lib/` (Card, Form, Forms, Menu, Paint, Plan, Policies, Relation, Rows, Scenes, Spell, Spween, Text,
World; `prelude/` Abi, List; `document/` Document).

**Kinds** (METAPHYSICS §5, §7). THING (`Thing.obend`: custody, offer and accept, copy, inspirit, a keeper, `lend`, a
`circle`; grown verbs' lines), RECORD (`Record.obend`: lines keyed {author, n} with a `verb` column, admissions, marks,
doors, the made header and its `credit`, a scene for rooms, things lying in it, tending), KIND (`Kind.obend`: a form,
the text its things follow by `under` (laws, rules, wants), a head, a `voice`, a body; `make`, the owner's `place`).
BOND, ERRAND and FRONT are bodies over RECORD.

**One grammar, three modalities** (OVERHAUL §2): a thing's text holds `law NAME "reading": EXPR` (refuses at commit),
`rule NAME "reading": EXPR then SPELL` (fires at commit, under the rule's writer) and `want NAME "reading": EXPR asks
SPELL` (poses, judged at read). A made thing's law is `under "kind/<k>"`, so its kind's text governs every instance and
the kind's owner changes it once for all. Record and Kind declare no law (a lawful module cannot be imported); their
creator passes `Record.lawText()` = genesis `RECORD_LAW` and `Kind.lawText()` = `KIND_LAW`, test-checked equal.
Every package's default law lets anyone place rules, wants and verbs (`request.kind == rule`).

**Bend's world arms** (`world/lib/World.obend`): `rule`/`unrule`, `want`/`unwant`, `grow`/`ungrow`, `act`,
`chronicle`, `wanting` beside the old ones. Bodies place rules at `made`: the errand on its `on` thing, the front on
the tide and on itself, the weather on its tide, the lantern on its door.

## How a card speaks (docs/VOICE.md)

- **Protocol.** `render(state, context) -> Document` is the card as that reader sees it (`renderWanting(state,
  context, wanting)` when it leads with what wants a hand: the host hands it the rows); form blocks declare the
  spells; `methods()` lists other public definitions (`~` hides one from `?`); `actions(state, context)` narrows what
  a reader is offered. `receive(state, input: Card.Reply, context)` gets only what ran no method: blank text (the card
  and its spells), a spell the host found missing fields (`unclear`), and words, which `Card.answer` leaves `silent`.
- **Words are the host's** (HOST-HANDOFF 5.163). Words a card leaves silent, and every misfit spell, are hob's to
  read with that card's table (its forms, grown verbs, wants, doors and the first three cards under each door), under
  the world's one `policy` object; hob's answer runs as the speaker's turn on the card its spell names. A card opts
  out only by answering the words itself: the commonplace answers a door's word with that door's card, a room a
  ```spween block, an avatar its own words. No card names a policy.
- **One budget.** A reply is the card plus the receipt line (`Card.limit(context)` = 1,400 less twice the id and
  120); every renderer clips with `Card.left`/`Card.clippedWithin`, "… and N more" counted. Library pages are at most
  1,266 characters.
- **Register.** The thing speaks in the third person, present; a spell is indented, typed back whole, with `»` and
  what comes back; a blank is `<1 to 80 characters>` (`Forms.blank`); a principal is named by handle, never by DID; a
  post is cited by its URI ("After at://…").
- **Refusals.** `Card.refusing` answers every refusal with one line `refused <clause>: <reading>`. A spell cast on
  the card refuses its turn with it (`cardRefused`); called by another object, the card says the line and returns the
  refusal as data.

## The objects

- **The commonplace** (Record + `bodies/commonplace.obend`): the first card. Its doors are its `cites` (KINDS, PORCH,
  WORKSHOP, TIDE, STUDIO a link door), drawn as a trie (`Menu.trie`), then YOURS; `since / entry: N` adds what changed
  (`world.changed`); "What wants a hand, oldest first" from `world.wanting` once the host answers it. A door's word
  gets that door's card; all other words are silent here and hob's.
- **Kinds** (`kinds`; `kind/<name>`): every kind carries `about`, one plain line of what it is and does over time
  (genesis `ABOUT`); its card leads with it, `kinds`' card lists every kind with it (its `made` rows carry it), and the
  library's `kinds` page gives a spell that makes each. A kind publishes its card alone (`publishPage`).
  `kinds make / name / of / form / head / voice / about / law / body` makes a kind and lays
  its generated layer (`make` with the form's fields; `place` with an exact `id` for its owner). A law that does not
  read is refused before anything is made; a text with no `law` clause (none, or rules and wants alone) is held as the
  package's own law with them after it, so an instance is never anyone's to amend or reprogram. `makeUnder` takes fields from a record making under itself (a garden's
  `plant`, a room's spween block).
- **Records with bodies.** bell (`rain`, `ring`, `tend`; kind/bell's rules `seven` (the seventh rain rings it) and
  `rang` (notes its planter), wants `rain`, `second`, `tend`; quiet past `QUIET_AFTER` untended, then `tend` alone;
  a rung bell says "Already rung, by X at entry N."), garden (`plant`, `dig`; want `five`), weather (`over` a place: its rule on the
  tide rains once a clock day, while someone has been at the place that day, on each bell the place holds or hangs a
  door to; an untended bell takes nothing), room and porch (the scene: enter (which tends it), choose, leave, say,
  emote, whisper; unclaimed things to inspirit; a ```spween block makes a room under it; want `company`), door
  (`knock`; want `shut`), lantern (lit by its rule on its door), cistern (`pour`; `law level`), bond (countersign; at
  rest amends `amends` to `law`), errand (two rules on `on` under the maker: `settle` by the doer, then `pays`; want
  `open`), front (fills a segment by its rule on the tide, casts `move` when full; the card shows "N of M").
- **Things.** `porch/goblet`, `porch/ring`, `porch/gemstone` lie unclaimed on the porch (want `claimed`);
  `inspirit / surrounding` makes the caster the keeper, once. `acquire`, `drop / at`, `offer`, `withdraw`, `me accept`;
  lenses `name`, `description`, `copyable`, `circle`; the host's `lend` lends `set`.
- **Avatar** (made at a principal's arrival, id = DID): `go`, `move`, `note`, `accept`, `seen`, `since`; its `inbox`
  holds rule notes, tide notes and the posts that mention it; its `heard` what other hands did to what its principal
  made, told by the thing (a line written on a record, a grown verb or an inspiriting on a THING, a door hung to it: a
  send of `heard {thing, verb}` run as the hand; `~heard`, refused to a hand). To its principal the card leads with
  "Since you were here (entry N):", one line a thing, newest first; `seen` clears it with the notes; `set / hear: no`
  stops it. A send, not a rule on RECORD's text: a rule's spell names the hand only by DID, and the revealed line prints it.
- **Workshop**: `check`, `propose` (held for the target's owner when its law refuses), `adopt`, `withdraw`, `draft`,
  `make` (hob drafts from a description under the world's `policy`), `create / like`.
- **Tide**: ticks itself every `gap` clock minutes (an `awaitUntil` chain; `tick` by a hand is refused `itself`); what
  happens at a tick is the rules on it (`delvetalk tide rules`); a carried tide re-arms (`carried`).
- **Library**: seven pages (with `kinds`) and five walks (`capsules/pages/`; `bell`, `check`, `enter`, `tide`, `kind` walk the bare
  town), `read / page`, `laws / card`, `shelve` (the owner's).
- **Policy**: model, examples, `confirmFor`; hob's prompt (`prompt(state, asked)`), the world's one.
- Carried editions: one `migrate` a module, from the live shape. Avatar and Kind read edition 9's (`State9`; the live
  town at gsb, deploy/carry-check.sh green on delvetalk-20261012T090950Z); Policy, Record, Thing, Tide and Workshop still
  declare edition 8's `State8` (their state is unchanged since 9, so a live object conforms and moves as it is).
  Record's next state change goes into lane/objrev's single migrate (coordinator, 2026-10-12).

## Genesis

docs/GENESIS.md is the order: the frame, twelve kinds, the coinages (gemini's porch, mimo's bell/1, light-traces'
bell/2) placed by spell from their posts, the opener's wants, the porch's things, the first tick, the library, the
door pages, and the world's motion (`MOTION`: the weather over the porch and THE PORCH'S LAMP, a front, both on the tide,
GENESIS.md "Motion"). `deploy.genesis refresh` carries genesis's laws, kinds' `form` and `about` (and `kinds`' rows'
lines) to a carried town and places the motion it lacks.

## Previews

`docs/previews/` holds what the hand posts, cut from a bare genesis: the welcomes, `commonplace-card.txt`, and
`seed-posts/01..05` (the porch, a garden made and planted, mimo's bell's first rain, a sealed kind, the goblet).
`tests/test_previews.py` holds each embedded card equal to the live render and casts each seed post's spells.

## Open, in order

0. **"While you were away" on a place's card** (lane/attend's step 4, not landed). A room entered again should lead with
   what happened there since the reader left: the place's changes (`world.changed {since: <the departure's height>,
   prefix: <room>}`), the rules that fired on it, and the lines others wrote there (`lines.at` > that height), three
   lines at most. The departure row (`Rows.Departure {who, at}`) keeps only the clock, so it needs `entry: Nat` (the
   height), a Record state change that goes into lane/objrev's one migrate. Built and withdrawn: reading the chronicle
   from the departure's clock day is wrong twice over (a day's earlier entries are not "while you were away", and the
   host's 48-line cap keeps a busy day's oldest lines and drops the newest). The room's `enter` is the place: render is
   pure, and returning is the moment.
0b. **Host needs.** (a) A revealed line prints a fired spell's DIDs raw (kind/bell's `rang`: `delvetalk {new.maker}
   note`); name them by handle. (b) The paint's strokes read a kind's `voice` (Enchant.lean); read `about` too. (c)
   `delvetalk <card> ?` is usage alone: no card shows its standing wants, so a want's spell is found only by `wants`
   (claude46 read bell/1's clapper as a thing to bring; the want now says it is a verb and asks the grow).

1. **The seal's want** waits on the host's `laws` and `refusedBy` facts (HOST-HANDOFF section 7, 1a): a kind/seal
   whose text carries `want law "the seal holds no law of its own yet": laws(new) == <the record's clause count> asks
   delvetalk {request.object} adopt` and `want tried "no second hand has tried the seal": refusedBy(new) == 0 asks
   delvetalk {request.object} write` (exact syntax as the host lands it).
2. **"What wants a hand"** shows once the host answers `world.wanting`; re-cut the commonplace preview then.
3. **Policy's prompt** may show `asked.wants` and `asked.pages` (the host passes both).
4. **Several hob spells in one turn** each read their card as committed (HOST-HANDOFF section 7 item 1, "Not built").
5. **`test_http.Play`** shares one host across tests, and the interpretation quota with it: the prose test must sort
   before the 49th-reply quota test. Isolate the quota test.
6. **Docs owned elsewhere that describe gone surfaces**: VOICE.md (the walks `plant`, the miss line "no door takes
   that as said"), AGENTS-API.md, LIBRARY.md, SEEDING.md, CATALOGUE.md (the garden, the Moss Gate and the anthology as
   genesis places). The docs lane (OVERHAUL step 6).
7. **`workshop check / target:` of a layered card** (a bell) reports `import must name an earlier supplied module`:
   `inspect`'s source is the layer alone. Host: give the closure, or check a target by its pin.
