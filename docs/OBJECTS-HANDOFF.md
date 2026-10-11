# Objects handoff

## lane/rewrite6 (2026-10-11): step 1, first half — PLACE folded into RECORD; checkpoint, not yet green

Standing order (the owner, verbatim): "we can adopt these things. we need to maturify and take forward
everything that we've started and bring it to its full sophistication and make sure the code is all
'fungused together' (no seams or welds where rich semantic braiding is called for). approved, and let's not
leave behind 'old things', no scar and growth tissue." The plan is METAPHYSICS §7 (§7.5, §7.6); the steps are
the brief's: (1) the commonplace underneath, (2) the furniture as kinds by spell at genesis, (3) tending, THING
with `me`/`go`/`lend`/`circle`, BOND from Deal, (4) genesis to §7's table, voice, GENESIS.md, previews, seed
posts, this file rewritten, the parked branch `lane/rewrite5-garden` deleted.

Inherited from lane/rewrite5 (its last turns, read with ClusterVision): it landed afee930 (one budget per
card; `me`/`env`/`wake` on one's own cards; no DID or post address on cards) and b349587 (the policy card in
one budget), both merged in foundation; it idled on the metaphysics decision with `lane/rewrite5-garden`
(3a12ac9, red) untouched. Its parked garden-as-PLACE design (verbs/head on Place, the layer generator, held
spells on Place) is superseded by this lane's shape: a garden is `kind/garden`, a RECORD with a body whose
`plant` calls `Record.making` (below), so nothing of that branch is to be merged; delete it in step 4.

Done here (commit "RECORD absorbs PLACE"):

- **RECORD carries what PLACE and Scene had** (`world/objects/Record.obend`): `cites` (the doors: the field
  renamed, the card's word stays *door*), `makes` (kinds a body makes under the record through
  `Record.making(state, kind, fields, context)`: <record>/<kind>/<n>, citing it home, answered "Made, at
  <id>."), and a room's `start`, `passages`, `cooldown`, `requires`, `presence` {who, at} (32), `vars`,
  `left` (`Rows.Departure`, 64), `things` (256). `relationsWith(lines)` lets a body keep more lines (bell 768).
  The record law's owner clause holds `cites`, `makes` and the scene unchanged for anyone but the owner, so a
  room is revisable by its owner's reprogram (GROUND change 7) and a stranger's proposal is refused `owner`.
  Traces are gone: a visit is a line the visitor writes (`write`), or none.
- **`kind/room`** (`world/bodies/room.obend`, over RECORD): Scene's verdicts unchanged in substance (enter,
  choose, leave, guards, effects, END, requires, cooldown and `crowded` as method refusals), Place's talk
  (`say`, `emote`, `whisper` to those present) and floor (`take`, `put`); a room without passages is entered
  at "". A ```spween block posted to a room makes a room under it by its kind (`makeUnder` with a `spween`
  field the kind's seed reads into the scene). Results are `Scenes.Done` (world/lib/Scenes.obend), shared by
  the avatar and the thing. Deleted: `Place.obend`, `Places.obend`, `Scene.obend`, `PLACE_LAW`, `Rows.Trace`,
  Place's lenses and its generated `shape` layer.
- **KIND**: ids minted past held ones (`requireAbsent` `<under>/<name>/`, HOST-HANDOFF 5.127; the await test
  that waited on it now passes); `kind/place` is `kind/room` (`of: record`, body `room`, head `{name}`); the
  kinds form's `body` bound is the package bound (131,072).
- **Avatar** `go / to: <room>` is that room's `enter`; `move / exit:` reads the room's `cites` by
  `viewField`; scoped resolution reads the room's `things` by `viewField` (arrival's sealed library no longer
  needs a state mirror in world/lib). **Thing** takes itself from a room by calling its `take`.
- **Wake** watches a room's `presence` where it watched traces. **genesis**: `rooms` is a Record seeded with
  the Moss Gate and given the room's body by an extend; KINDS make record, bell, cistern, room.
- Tests: test_places is test_rooms; test_scene, test_spween, test_kinds, test_strangers, test_lenses (the
  place lenses deleted with them), test_hub, test_await, test_objects and the rest migrated.

Red at the checkpoint (full run on persvati: 781 tests, 3 failed classes), the next turns' first work:

1. `test_kinds` `test_a_spween_block_posted_to_a_room_makes_a_room_under_it`: a block posted to a room made
   by `kind/room make` (body grafted by delivery) is answered with the room's card, not carved; the same
   through a room made by `world-reprogram extend` (test_spween `Made`) carves. Find why the grafted room's
   `receive` does not see the block.
2. `test_genesis` `MenuFromState`: glm's root menu opens on ROOMS, not on its last door (ANTHOLOGY), after
   kimi enters `rooms` through the directory. Check what `visits` the directory writes when the room's enter
   answers `entered`.
3. `test_properties` `EveryMethod`: an avatar's `publishPage` (the host's default page) ran from outside for a
   stranger. Avatar changed only its imports and move/go; find what the artifact now declares.

4. A loss to restore: Scene refused a proposed write by its owner too (`methods`); a room's owner can now
   propose `presence` (the record law's owner clause admits the owner at any kind). Add to RECORD's law a
   clause that refuses a proposal (`request.kind == proposed` is in the fragment, KERNEL-HANDOFF §24), and put
   back test_strangers' creator assertion (`test_a_stranger_cannot_place_themselves_in_a_room`).

Routed here by docs/review/fungus-2026-10-11.md §3 (on foundation; merge it into this lane first), each folded
into the step that touches the same object:

- **H1** (step 1, second half, with Card): delete the reduced spell parser in `world/lib/Spell.obend`; the
  Garden's macros and `Card.unanswered` read the host's `spell-parse` answer through the existing Plan, or the
  one remaining use is declared and only that kept.
- **O1**: done here (Place and its five unused garden-as-place fields are deleted with it).
- **O2**: the half-done cut is this lane's steps.
- **O4** (step 1, second half): one door record, one `Names`, one `Forms`, each in one library.
- **O5** (step 4, with `Policy.prompt`): delete the unused `Policy.escalate` (field, lens, card line).
- **T31** (step 4): drop the `Participant:` tail `Policy.prompt` appends; the transport lane then sends the
  utterance once, with no cut, in `interpret.py`.
- `capsules/world.txt` is gone; the library page `capsules/pages/world.txt` is the one text.

Host findings for the host lane (repros above in this lane's history):

- **Create-then-extend in one turn (5.122) is not usable by KIND yet**, so Kind keeps the self-sent graft.
  (a) A kind made by `kinds` (itself a layered Kind) and extended in the creating turn refuses every later
  write of its own with `typeMismatch` naming it (make, makeUnder), and a later `shape` lays nothing
  (`writes: []`); the same kind shaped in a later turn works. (b) A record made by a kind and extended with the
  bell body in the creating turn is refused (the turn refuses "could not be given its body"): the made thing's
  law judges the extend with the running kind as proposer, which the record law's `request.subject ==
  new.owner` refuses. Repro: Kind.making with `world.extend` after `created` (this lane's first version).
- A layer may import only modules its base's closure supplies, and a layer that imports Plan derives Edits
  for every State field, so Record imports Spween (for the room) and the bell body imports Scenes.

Transport finding (not this lane's files): the bridge routes a summons to `directory` and reads door words
from its `doors`; when the commonplace replaces the directory (step 1, second half) `transport/bridge.py`
`route` and `named_door` and `transport/http.py`'s play default must name `commonplace` and read `cites`.

Remaining of step 1 (next): the `commonplace` RECORD as the first card, its blank-reply card rendering over
`world.changed` (eight items `<id> v<n> by <handle>, entry N`, then `delvetalk kinds make / name: <a thing> /
of: record` and `delvetalk <id> ?`), its `cites` the door-menu of the hand's named things; the Directory's
hub (greeting, hob at the root, macros, several proposals, `missed`/`Card.owed`) moved onto the commonplace's
body (a layer cannot add state: `greeted` and the hourly `missed` join RECORD's state), Directory.obend,
Menu's news/visits and `Card.directory` deleted; the Wake's head "WAKE of {handle}". Then steps 2 to 4 as the
brief lists them. Tide's `ownRows` family and Deal's `signer` wait on `changed(new.F.COL) by` in a binary
(not in foundation cd35a4c).

## lane/rewrite5 (2026-10-11): the neutral half of 4b; the garden as a seed parked

The owner put the town picture on hold ("when we reconsidered the metaobjects we should also reconsider the
metaphysics"): no garden as a seed, scene body, genesis table, seed posts or previews until that lands.

Landed here (metaphysics-neutral):

- **hob never prints the model's words** (cracks R2, playtest 68746). `Card.Hob.ask {needs}` keeps only the
  offered fields a need names as a word (`Card.fieldNeeds`); the lines are VOICE's: a card's ask `hob: still
  needs {fields}; the spell is below.` or `hob: not a spell as said; the spell is below.` over its first spell;
  the root's `hob: no door takes that as said. The nearest:` (or `…; still needs {fields}. The nearest:`); the
  escalation copy `{name} said: {words}; hob found no spell in it ({card}).`
- **hob at the root is offered the first card under each door too** (`Mentions.doorForms`: a bell's rain).
- **WATCH's spells** (GROUND §6 change 5) on the Wake: `writes / object / field / above`, `grows`, `turns`,
  `rows / object / field / where / count` (`where` one `column op value` line: `=`, `>`, `<`, `has`; blank
  for every row; anything else `refused badWhere`), `remind / at / every` (a schedule that notes the owner).
  Form field names must be lower case: the host folds a spell's field names (5.119), so `atLeast` could never
  be typed. The rename to WATCH and `do: say` wait: arrival names the Wake module, and `say` needs a place.
- **`Kind.makeUnder` judges text fields against its form** (`Forms.fault`: `missing`, `badValue` with the
  host's readings), so a place handing text cannot seed a value outside the form. Forms' generators take
  the form's action (`<action><Field>Text`), for verbs other than `make`.

Parked on `lane/rewrite5-garden` (3a12ac9, red, not for merge): the garden as a PLACE seed. Place gains
`verbs` {action, kind, done} and `head` (owner text with holes); `shape` writes one form per verb with exactly
its kind's fields, or one `make` that needs only its own kind's fields (completed in `receive`, which closes
4a's finding); the garden's word handling on Place (held spells completed by their missing lines, no, macros,
misfits, merge, hob with the newest made thing's forms, a proposal run by a call to the card it names, the
place's own included); genesis `garden_seed`; tests/test_garden.py green, about half the other test files
migrated. Before it can land: `Place.obend` is 51,672 bytes, past the 32 KiB bound a reprogram is held to, so
the layer generator goes to a library (Forms) and the word handling to Card; Kind's closure (Kind, Record,
Place) is near the 256 generic instances (`Generics.maxInstances`): every new type a Place helper maps over
costs one, so Place uses `Spell.Binding` and `Forms.Spec` rather than new row types. An asked-first proposal
cannot be held for yes: its argument is Data, which Bend cannot print or keep as text. Host: the proposal
carries its spell text (then Card holds it and renders `hob: I read that as`; cracks L1).

Open, found here:

- **The hand-on costs no model call (landed, HOST-HANDOFF 127, 128):** a `send` of `receive` keeps the reach of the
  turn that sent it, so prose that reached no one stays `not addressed` at the directory.
- **Methods without input take `{}` only (landed, HOST-HANDOFF 132):** a field the input does not declare is a
  `typeMismatch` naming it, and test_principal's `ignored` sends `{}`.
- **An avatar keeps its first handle** after a second arrival under a new one (cracks): with THING.
- rehearsal/rehearse.py reads the garden's `children`; with the parked garden it is `made` ({object, kind, n})
  and `count` (rehearsal lane).

## The cut in progress (lane/rewrite, 2026-10-10 evening; docs/CATALOGUE.md §5)

Done, each green on hbox (1261 tests, 0 failed) with pins re-recorded:

1. **Deletion** (3cec2d6): Counter, Loop, Door, Lantern in `tests/fixtures/objects/`; Seat, Table and the
   game library in `examples/automatafl/`; Commons, Appointment, Appointments gone; genesis without
   `commons` and `play`.
2. **RECORD** (7b53d7a, f38ed9c): `world/objects/Record.obend` (lines {author, n} 128, `admitted` {n},
   `marks` {name}, and the made header: head, kind, fields, maker, makerHandle, post, all fixed);
   lawless, its law is `Record.lawText()` = genesis `RECORD_LAW`. The anthology is a Record seed. Env's
   `mention` is `write`; watches and the menu read `lines` (`changedLines`).
3. **KIND, first half** (97b522c): `world/objects/Kind.obend`, `world/bodies/{bell,cistern}.obend`,
   genesis `kinds` + kind/record, kind/bell, kind/cistern; `tests/test_kinds.py`.

Findings the successor builds on:

- **A turn reaches what it created only by `extend` (host 122).** `extend` of an object created earlier in the
  same turn lays the layer into the making; `call` and `write` to it still answer `unknownObject`. KIND still
  grafts a body (and shapes a made kind) by a message it sends itself, delivered in the same settling
  (`grafting`, `graft`, `shape`), so a make is not yet one create.
- **A kind's make is a generated layer.** `Kind.layerSource(state)` writes `form make:` from the form's
  field lines plus a `make` that calls `Super.making(state, <rows>, "", context)`, and a
  `make<Field>Text` match per choice field (`a | b | c` -> sum `Make<Field>`). Field names must be Bend
  identifiers; a choice option named like a keyword (`record`) does not compile, so `kinds`' `of` is
  text. A layer may not retype what it overrides, which is why Kind itself has no `make`.
- **Layers late-bind.** The bell body overrides only `headLine`, `entry`, `relations`, `write` (refuses
  over 200 characters) and adds `rain`, `ring`, `strike`; Record's `write` then renders the bell's head.
  A layer's form blocks replace the forms below, so a body re-declares the base forms it keeps
  (`lines`, `door`, `undoor`) with one-line delegations.
- **`Library.laws` reads `inspect` without the source (landed, HOST-HANDOFF 123):** `world.inspect({object,
  source: false})` answers `laws` with readings and `offered`, so a long card's law page costs no source ticks.
- **Usage cards list what the reader is offered (landed, HOST-HANDOFF 123):** `Card.offeredCard` and
  `dueOffered` filter the forms by `inspect`'s `offered`.
- Reader-specific: Record's `actions` shows admit to the keeper, door/undoor to the owner.

Step 3b, done on lane/rewrite2 (d3bd6aa, 82136a0; 1288 tests, 0 failed): the garden plants through kind/bell
and digs through kind/cistern (`makeUnder`, quiet, a door home); Bell.obend and Cistern.obend are test
fixtures in tests/fixtures/objects (the host's view, subscription, layer, await and limit tests keep them);
a wake watches a bell's `rung` as a `marks` row; the KINDS door ("KINDS · 3 made"); the WORKSHOP door
teaches `workshop make / name / description` (hob drafts a `draft`, checked, held as #n for the describer,
whose `adopt` `make`s it with `madeFrom`); the root menu's head and tail in v4's words; Spell.obend folds
case as the host does; the library's laws page reads inspect's `laws`; kind/cistern adds `monotone(next)`.
Tests use `tests.test_chain.town_kinds(send)` wherever a garden plants.

Step 4a, done on lane/rewrite3 (d706f13; 1,334 tests, 0 failed; pins re-recorded): hob reads once and
PLACE stands lawless.

- **FLEX §2 in Bend.** `world.interpret` carries `held` and `misfit`; `Card.Heard {text, post, fields,
  misfit}` is what Garden's and Directory's `receive` take (host 121), so a direct misfit spell reaches
  them: with a policy hob sees `Misfit: <clause>, <reason>`, with none the card refuses by that clause
  (Garden `Card.answerRefused`, Directory `refusing`). `Card.hobNeeds`/`hobSaid` read hob's answers;
  `Card.hobbed` is none (silence), card (the card), ask (`hob: {q}` over the first spell, `askCard`, and
  the escalateTo copy). The root's ask is `hob: {q} The nearest:` over the pruned menu. Gone: the second
  attempt, `escalate` as a retry model (the field stays in Policy, unused), the mention gate, every
  "I still need" card. Garden keeps a held planting through hob's none and shows it as `held`.
  `Card.offeredCard` lists only inspect's `offered`. `Policy.prompt(state, asked)` is FLEX's text.
- **PLACE** (Place.obend, state in `world/lib/Places.obend`): lawless (`PLACE_LAW`), exits are
  `Card.Doorways` (owner's `door`/`undoor`), `keep` bounds traces (`traces` lens; 0 keeps none, the
  card says nothing), `makes`/`made`/`count`, `making` calls the kind's `makeUnder`, the owner's `shape`
  grafts `form make: kind: <choice>` plus the union of the makes' fields (`Forms.obend`, shared with
  Kind). Also on the state for the garden to come: `policy`, `confirmFor`, `held` (Pending {principal,
  kind, fields, needs}), `pageCheckpoint`. `kind/place` makes `place/<n>` from `name` (Kind's
  `placeSeed`). Places.obend is not folded: arrival's sealed library is world/lib plus Avatar, Env and
  Wake only (`Serve.arrival`, `Ops.arrivals`, hostproc `ARRIVAL`), and the avatar imports it.
- **The root menu**: a link door is never clipped (`Menu.trieUnder` says it after the clipped branches);
  the greeting's head drops "words reach hob; its spell runs unless the card asks first" (hob's line says
  it). Seven doors and the bell arc fit 1,400 on the day the newest names show, greeting included
  (`tests/test_genesis.py`). docs/previews/gsb-root-menu-v4.txt is that render.

Open, found in 4a:

- **A handed-on reply keeps its reach (landed, HOST-HANDOFF 127, 128):** `Card.handingOn` is a `send` and the
  directory's turn carries the sender's reach, so a bell reply with no reach leaves nothing pending.
- **Place's generated make requires every field of every kind** (the union, each required): a place
  making bells and cisterns could not make a cistern without a colour. Either one form per kind
  (`plant` for bell, `dig` for cistern: the alias design below) or Kind's form gaining optional fields.
  (`Kind.makeUnder` now judges the text fields against its form, `Forms.fault`.)
- `kind/place make` takes `name` only; description, traces and doors are the owner's lenses and spells
  after. CATALOGUE §4's `/ traces: 0` and `/ makes: kind/bell` in one spell need optional fields.
- hob is offered only the doors' own forms at the root (`Mentions.doorForms`); FLEX's 801-token root
  counts the bell's rain as well. Decide: offer the first child's forms too, or say so in FLEX.

Still open from 3b (the host side has landed; the objects side has not):

- **Atomic make**: host 122 lays an `extend` into a creation of the same turn, and the `typeMismatch` on a method
  the layer adds did not reproduce on foundation fixtures (HOST-HANDOFF 127); Kind still keeps the self-sent
  graft (`grafting`/`graft`). Check: `kind/key make / seed: x` through create-then-extend.
- **A taken id stops a kind**: the host mints under a prefix (`requireAbsent` ending in `/`, HOST-HANDOFF 127),
  but Kind names `<under>/<name>/<count+1>` itself (`idOf`), so a held id is the turn's requiredAbsence
  (tests/test_await.py expectedFailure stands until it asks for the prefix).
- **The workshop's lineage needs the receipt hash**: an await's `Plans.Receipt` carries `hash` (HOST-HANDOFF 127),
  but `adopt` still passes `madeFrom.receipt: ""` (`Workshop.making`); it should await the holding turn and
  cite it.

Remaining, in order (each a commit, the suite green, pins re-recorded):

4b. **The garden as a PLACE seed.** genesis `garden` from Place with `makes: [kind/bell, kind/cistern]`,
   `policy`, owner ember, then `shape`. Design to settle first: `plant` as the alias of make. Proposal:
   Place gains `verbs: List<{action, kind}>` (seed; `plant` -> kind/bell, `dig` -> kind/cistern) and the
   shape layer emits one form per verb with that kind's exact fields, each calling `Super.making`;
   `make` stays for a place whose kinds share their fields. Garden.obend's prose handling (held
   plantings, confirm, macros, `hobbed`) moves to Card as FLEX objects 4 says (`Card` holds the
   asked-first proposal per principal; Place has `held` for it), so a Place with a policy reads words
   with its makes' forms. The planted card (`Planted, {handle}: an amber bell, “{seed}”, at {id}; {n}
   planted.` / `Rain on it:` / the spell / `Another:`) and the garden card are VOICE's, pinned by
   tests/test_objects.py: Place's render needs a `head` (seed text) and the made line per kind, or a
   garden body; CATALOGUE §5 lists no garden body, so prefer a seed `head` and a per-verb `»` line.
   The directory's GARDEN door watches `made` (`count`) instead of `children`; Wake's `watchBell` send
   moves with it; `byColour` and the page (`publishPage`, merge) need a home or go (decide with the
   owner: the page is ember's wiki checkpoint). Delete Garden.obend; tests re-pointed by
   `tests.test_chain.town_kinds` and a `town_garden` helper.
4c. **The directory as a body over PLACE** (world/bodies/directory.obend). A layer cannot add state, so
   Place's state must carry what the directory keeps: exits as the doors need `examples`, `watch` and
   `place` (a `Card.Doorway` has only label and to): either Doorway grows (Record's doors too) or Place
   gains `doors: Relation<Menu.Listed>` beside `exits`; and `greeted`, `news`, `visits`, `missed`. Its
   laws (`greeted` insertOnly) join PLACE_LAW for the root (genesis passes a law per instance). Keep the
   Directory's 32 KiB bound.
4d. **The scene as a body over PLACE** (world/bodies/scene.obend; Scenes, Spween unchanged): Scene's
   state (title, start, passages, presence, vars, cooldown, requires, left) onto Place as with 4c;
   its Bend law (cooldown, `crowded`) needs a law in a layer or text law clauses. **Rooms revisable**:
   `passages` and `start` out of `law fixed`, so only the owner's reprogram with a migration (kind 1,
   which the Bend law does not judge) revises them; the Workshop's propose shows `v+1`. kind/scene.
5. **WATCH** from Wake (forms for `rows`/`writes`/`grows`/`turns`, `where` as one `column op value`
   line, `do: say`); tide as a body over WATCH; **THING** from Thing with the avatar body (`me`, `go`,
   `lend`, the `circle` lens); **BOND** from Deal with `deals` by spell. Arrival still names Avatar,
   Env, Wake modules (`Ops.lean` `arrivals`, `transport/hostproc.py` ARRIVAL): ask the host lane for
   Record/Watch/Thing with seeds before Env and Wake files go. kind/watch, kind/thing, kind/bond.
6. Genesis to §5's table; the library's walks (`capsules/pages/<walk>.txt`, kind `walk`) and the four
   "how do I" macros (`find {words}`); every card in VOICE's register;
   this file rewritten as the surface as it stands.

Folkways and arcs so far: folkway 1 and the seventh rain's `ring`/`strike` (bell body); folkway 3
(Record's `kept`, `admit`); folkways 4 and 5 (Place: traces, `notPresent`); the flood's level (cistern
body's `next`); the rest are still in their old objects (Thing 6; Deal 7; Directory 9; Scene 10;
Tide 2) and must move with them.

## Summary

World objects are `.obend` files in `world/objects/` (15: Avatar, Deal, Directory, Env, Garden, Kind, Library, Place, Policy, Record, Scene, Thing, Tide, Wake, Workshop; 3,619 lines), with two bodies, layers over RECORD, in `world/bodies/` (bell, cistern; 111 lines). Libraries are flat-named modules in `world/lib`, `world/lib/prelude` and `world/lib/document` (19 files, 2,251 lines); an object imports them by basename. Counter, Loop, Door, Lantern and a Bell and Cistern fixture are in `tests/fixtures/objects/`; Seat, Table and the game library are in `examples/automatafl/`; Commons, Appointment and Appointments are gone, and the Anthology is a Record seed.

- Every object speaks the one dialect: methods are `Activity<A>` over `world.X(...)` (`world/lib/World.obend`), self-writes are `write {f: op v}` over `Edits`/`keep()` the kernel derives from `record State`, and a field nothing may change is `fixed` (lawless objects) or `unchanged` in law. No object writes `Edits`, `keep()`, a `Seed` ritual or a `perform`.
- The host parses spells, resolves the card, and runs the declared method a spell names; `receive(state, input: Card.Reply, context)` gets only what runs no method (prose, a spell missing fields, field lines naming no form). Only declared methods are public: form-block actions, `methods()`, `views()`, conventional names (HOST-HANDOFF 5.62).
- Needed first: `World.obend` (the protocol and its result sums), `Plan.obend` (`Reference`, `Edit`/`Entries`, `Slot`, `Receipt`: what messages carry), `Card.obend` (answer, tell, names, doors, pages, interpretation and macro helpers), `Relation.obend` and `Rows.obend` (relations and shared row types), `Form.obend`, `Text.obend`, `Policies.obend`, `Places.obend`. `Spell.obend` keeps only the binding types.
- Run: `make check`; narrow `DELVETALK_OBEND=<binary> python3 -W ignore -m tests.run test_objects test_spell_turns …`. Compile-only: put a `delvetalk-obend` binary in `DELVETALK_OBEND`; never run `lake`, never commit the binary. `tests/host.py` fails any host reply whose card or offer text contains `bafy` (no hash in a card; cite `<object> v<n>`).
- Tests: the count is in HOST-HANDOFF's Summary. Tick bounds tests hold: glm's 1,788-character reply under a bell under 25,000 (with the hourly `due` call and the card it owes) and the directory's reading under 250,000 (`test_hub`); `test_places` under 100,000.
- Lawful objects (declare `law`): Deal, Directory, Env, Garden, Library, Policy, Scene, Thing, Tide, Wake. Place, Kind and Record declare none (a creator passes the law, `lawText()`), because a creator cannot import a lawful module; their owners make them with `world-create`. Bend predicates (`def law`): Thing (custody), Tide (`tooSoon`, `self`), Scene (cooldown, `crowded` retention), Deal (`signer`), and Workshop and Avatar beside the default law; every one refuses a write no method made (`Plans.unnamed`, clause `methods`).
- Open: section 4.

## 1. Conventions

- **State and initial.** `record State` and `def initial() -> State`, the one constructor. The host's `create` lays a seed (a record of some State fields) over `initial()` and fills a text `owner` from the creating principal when the seed names none. `world-create` takes a partial State too. Scene keeps a `Scenes.Seed` of passage data.
- **Edits are derived** (KERNEL-HANDOFF §23). A list or relation field is `Entries<X, X>`, a `Nat` `Edit<Nat, Nat>`, anything else `Edit<T, {}>`. `colour: fixed Colour` has no edit at all (Record's head, kind, fields, maker and post, set when a kind makes it); a lawful object says the same with `unchanged(F)` (Scene `law fixed`, Tide `law gap`, Deal `law fixed`).
- **Card protocol.** Every object has `render(state, context) -> Document` (`Card.stranger()` is a nobody Context), `forms()` (the host reads their bounds, HOST-HANDOFF 5.69), `blurb()`, `methods()` when it has public State-first definitions beside its forms, and `receive(state, input: Card.Reply, context)` with `Reply {text, post, fields}`, answering `Card.Replied` (`done`, `usage`, `unclear`, `refused`). `Card.answer` (or `answerAs` for an own result type) offers the card or hands prose to the directory.
- **Form blocks.** `form ACTION [as NAME]:` with field lines (`text A..B`, `natural A..B`, `source`, `a | b | c`, or a closed sum `T` in scope) declares the Form value and the method's input record `ActionInput`; Garden's `plant` takes `Planting`, whose `colour` is `Bell.Colour`. The kernel derives `forms()` from the blocks in source order (it needs `import ./List.obend`); Directory and Kind write an empty `forms()` (a kind's `make` is a generated layer).
- **Handles and the clock.** `Card.name(did, context)` shows the reader's own observed handle (`context.handle`) and anyone else as `Card.handle`: never a raw DID; a handle stored when the host knew it shows by `Card.shown`. Deadlines compare `context.clock`, which only `world-advance` moves.
- **Reader-specific cards.** `Card.reads(principal, context)`, `Card.mine(principal, context)` (" (yours)"). A member sees more: an Env's events, a Wake's triggers, an Avatar's notes and follows, a Deal's countersign spell, a Policy's teaching card, a Scene passage.
- **Cards by characters.** `Card.clipped` keeps at most `Card.budget()` (1,200) characters of rows, its "… and N more" counted among them; `Card.clippedWithin` what a long head leaves. One budget per renderer: `Card.limit()` (1,400, what readers see) and `Card.left(used)` give each list what the card's other parts leave (Bell: head and doors; Scene: head, then choices; a Scene title shows 120 characters). A card prints its spells first.
- **Spell shape** (the host's grammar, `Host/Spell.lean`). A card name is `[a-z0-9:/.-]+`, at most 160 bytes; actions and fields `[a-z0-9-]+`; `?` is an action. Fields follow the action after ` / ` or commas, or on field lines. The spell is the post's last delvetalk line that is not quotation (indented four or a tab; `>` and fence lines are never spell lines). Block values: `field: <<DELIM` … `DELIM`; unclosed is refused `unclosedBlock`. A `source` field the spell lacks takes the reply's first ```obend fence. A literal brace in Bend source is `{{`/`}}`.
- **Lenses.** `def lenses() -> Lists.List<Form.Field>` and `set(state, input: {field, value: Form.Value}, context)`: the host judges the value against the field's kind and runs `set`, which refuses a stranger by name (the law judges the write); `?` lists the lenses; a `fixed` field is never a lens. Lenses: Policy (`model`, `escalate`, `escalate-to`, `system`), Avatar (`handle`), Place (`name`, `description`), Thing (`copyable`, `name`, `description`), Garden (`confirm`). `Card.valueText` reads a Value.
- **Interpretation (Garden, Directory).** A card with a policy views it (`world.view::<Policies.State>`) and asks `world.interpret::<T>(Card.interpretation(...))`. The host fits the model's spell and answers `proposal {object, method, argument}` (the Directory calls that card's method), `proposals {items: List<World.Proposed<R>>}` for a reply holding two or three spells (`Policy.prompt` asks for each, one `delvetalk` line apiece; the Directory folds them in order as this turn, each call admitted or refused on its own, and offers a card listing each spell with `» admitted`, `» refused <clause>: <reading>`, `» asks first …` or `» unclear: …`; the Garden takes the first), `unclear {needs}`, `replied {text}` or `denied` (refused `policy`). hob answers once (4a): the spell meant, `ask: <question>` (`unclear {needs}`, read by `Card.hobNeeds`), `card` or `none` (`replied` or silence, read by `Card.hobSaid`), and `Card.hobbed` acts on the last three. There is no second attempt: `Policy.escalate` stays a field and a lens that nothing reads. An activity composes only in tail position, so the object owns the loop.
- **Confirmation per action.** `Policies.State.confirmFor` (default reprogram, amend, offer; the owner's `delvetalk policy confirm / action: plant / ask: yes|no`) names what an interpreted proposal waits for a yes before (`Card.confirms`). Garden keeps its own `confirmFor`, empty at genesis (its `confirm` lens adds or drops plant). A card holding a proposal for its speaker reads a bare answer first: `Card.answerOf(text)` is yes (yes, y, yeah, yep, ok, okay, sure, go ahead, do it) or no (no, n, nope, cancel, never mind), a closing `.` or `!` aside; Garden answers a bare yes or no with nothing waiting `refused nothingWaiting`.
- **Completing a spell.** A planting spell missing fields is held for its speaker (Garden `Pending {principal, colour, seed, needs}`, keyed {principal}; empty needs = waiting for yes); a reply whose `Reply.fields` name the missing fields completes it. The Directory passes field-only lines whose first name is a field of a door's form to that door.
- **Macros.** Policy `macros` (owner: `delvetalk policy macro / name: … / pattern: moth for {who} / expansion: garden plant / colour: violet`; a same-named macro is replaced; sixteen; a pattern starts with a word). Garden and Directory check `Card.expanded(text, policy)` before the model; a hit is dispatched as a typed spell with no interpretation. Garden's `?` appends `Card.macroUsage`.
- **Direct replies.** A reply to a card itself (no card handed it on: its thread, a summon, the play page) is never quiet the first time: prose that fits none of a card's forms gets the card and its forms (`Card.owed`), prose to the Directory naming nothing gets the menu under "I heard no door, spell or field in that." (pruned to the doors it named, when the model was asked and found nothing addressed), each at most once an hour per speaker across the town: the Directory's `missed` relation ({principal}, 64; 60 clock minutes) is the clock, marked by its greeting and its `due` method, which `Card.owed` calls. Whether the Directory's hob reads prose at all is the host's reach (a mention, a door's word, field lines or a direct turn: FLEX §2), so prose that reached no card costs no model call and a hub thread costs at most one card an hour. The owner is answered as anyone is.
- **Handed to the directory.** Prose `Card.answer` does not take is sent to `directory` (`Card.directory`) as `receive {text, post, fields}` under the speaker; the card offers nothing. A turn some object started forwards nothing. The Directory learns its doors' declared forms by `inspect` in one pass a turn and `Mentions.touches` only prunes the menu hob's question stands over to the doors a reply names; it no longer gates the model.
- **Link doors.** A Directory door whose `to` is nobody (genesis's STUDIO) answers its word with `<label>\n<description>`, prints its description on its door line, and is skipped when field lines and the model look for forms. The menu is ordered by each door row's `place`.
- **The root menu** (docs/MENU.md §1; `world/lib/Menu.obend`, pure). The Directory card is a trie: per top door `DOOR · <count>`, each of its `examples` (`{example, comes}`: the spell typed back whole in the inline grammar, and the owner's `»` line, "" for none), then the examples of its arcs (door rows whose object is a card under the door's object, `garden/bell/1`). The reader's last door (`visits`, written in `passOn` and `calling`, only when it changes) leads; the rest follow `place`. Branches are clipped whole within what the head and the two-line tail leave of 1,400. A door's `watch` names the field of its object its line counts (`children`, `ticks`, `proposals`, `held`, `presence`): `add` reads the field's count (`viewField`), writes a `news` row and subscribes the directory to it (`Card.subscribing`, the owner's turn) with the receiver for its rows (`changedChildren`, `changedNat`, `changedProposals`, `changedHeld`, `changedPresence`: helpers, counting only the watched object's own change on a watched field); `remove` drops the row and the subscription. A news row keeps the count and the newest row's name (`garden/bell/3`, `#4`, `#2 for garden/bell/1`), shown for 1,440 clock minutes after it came. A door added before its object exists watches nothing, so genesis adds the doors after creating their objects. Prose reading (mention scan, learned forms, miss words) is `world/lib/Mentions.obend`; the Directory keeps under the 32 KiB package bound (`maxPackageBytes`) that a reprogram is held to.
- **Env.** `Env.receive` and `mention` from anyone but the owner are taken in as a `mention` event; the law admits them (kind 0, `mention` or `receive`, owner, handle and seen unchanged). Arrival seeds `handle`; the card reads "ENV of <handle>" with the newest eight events. An Env lives at `env/<did>`. Its `buffer` holds 256 (the host drops the oldest).
- **Workshop.** A package fault (compile, program, packageBytes, migration, stateType) is answered by name and never held; adoption names one met later as itself, keeping "Only the owner … adopts" for the law's refusals. `check {target, source}` and `propose {target, migration, source}` take Bend as a `source` field (a block or the reply's fence, 1 to 16,384 characters). It views its target (state type `Data`) and says "Was: <id> v1 / Now: <id> v2". A `propose` the target's law refuses is held (`held`, keyed {n}, sixteen) for the owner: `adopt / n` runs the reprogram under the adopter, `withdraw / n` is the proposer's. Compile, program, packageBytes and migration refusals are not held.
- **Scoped resolution (Avatar).** An Avatar's own principal's prose with no spell names its object by the first word that is a thing lying in its place, else an object of that id; the avatar sends `receive {text: "delvetalk <id> <action>\n<field>: <rest>", post}`, which the host reads as a spell (HOST-HANDOFF 5.63). Two of a name are answered "Which one: …?"; `look` offers the place's card (`world.card`).
- **Place.** Its State, Exit and Done are `Places.obend`'s; its law is `Place.lawText()`, passed by the creator (Place declares none): only the owner renames, redescribes, reprograms or changes exits and makes; anyone's kind-0 write keeps them. `say {line}`, `emote {line}`, `whisper {to, line}` offer the line to every avatar present (in key order, at most 32); someone not present is refused `notPresent`. Each enter, leave, take and put is traced as `Rows.Trace`, 64 kept (the card shows the newest eight).
- **Thing.** `copyable` (default true; the owner's lens). The Workshop's `create / like: <thing>` sends `copy`; the thing creates a Thing from its own package with its state minus holder, offer and owner. Not copyable is refused by name.
- **Doors on any card.** `Card.Doorway {label, to}`, `doors: Card.Doorways`, `Card.doorAdd`/`doorRemove` (owner's; eight at most; `doorTaken`, `doorsFull`), `Card.doorLines`. Record, Place and the bell and cistern bodies declare `form door`/`form undoor`; a thing a kind makes under a place has a door home to it.
- **Wake.** Rules as data (`On`: `mention`, `keyword`, `reply`, `schedule`, `writes {object, field, above}`, `rows {object, field, where, atLeast}`; patterns `equals`, `above`, `below`, `contains`). It subscribes with typed receivers: a scalar to `changedNat`, a relation to one receiver per `Rows` type, its Env's `buffer` to `changedSensed`. Receivers are helpers and check `context.caller`.
- **Deal.** Law `members`: every change is a party's, and a write is `countersign`'s or `withdraw`'s (so neither a stranger's amendment nor anyone's proposal passes); the Bend law refuses a new signature that is not the requester's (`signer`). `amendment {object, law}` (object "" for none). The countersignature that brings the deal to rest calls `amend` with the deal as caller, judged by the object's own law; a refusal is answered `amendRefused`, the signature standing. `countersign` takes `{}` and cites `context.inputOrigin.post` (a turn from no post is refused `unposted`).
- **Hub.** The Directory greets each principal once (`greeted`, insert-only in law); with a policy, a first reply that names a door, action or field is read as any later reply first, and the menu follows whatever it drew, opening on the door a proposal or a macro went through (`greet` through `consulted` … `calling`, `welcomed`). A second miss is answered with the trie pruned to the doors whose word, object, or learned actions and fields the reply names (`Mentions.touches`, `Menu.pruned`), under hob's `no door takes that as said` line (`Directory.missLine`). It is silent to its owner and answers a door word with that door's card. Garden ends with no offer for prose the model calls `not addressed`. Tide answers subscribe and tick with its card.
- **Pages.** The host publishes a default page (`## Card`, `## How to reply`) for `publishPage {page}` to a card that declares none (HOST-HANDOFF 5.68); Garden keeps its own (`page`, `Card.defaultPage`, `Card.pageText`). An object with a page keeps `owner` and `pageCheckpoint`; `Card.isMerge` reads the owner's `merge` reply.
- **Library** (docs/LIBRARY.md). `library`: `pages` keyed {name} (32; `Page {name, kind: page | walk, title, body 1..1400, place}`); `read {page}` offers the page named, else the first whose name is a whole word of what was given, else hob's miss line and the index (nothing written, no model); `laws {card}` renders `world.inspect`'s law with readings from the source's law lines (a law given at creation has only the host's form, no readings); `shelve {name, kind, title, body}` is the owner's (refused `notOwner` by name, and by the law). `render` is the index, in shelving order. The action is `laws`, not `law`: a definition named `law` is a card's Bend predicate. Genesis shelves `capsules/pages/<name>.txt` (`deploy/genesis.py` `PAGES`), so a page in the world and its file are one text (`tests/test_library.py`).
- **Anthology.** A RECORD seed (`anthology`, keeper the opener; Record.obend): anyone `write`s, the keeper `admit`s by number. A line's number is `next` when it came (keyed {n}, so it survives older lines being dropped); a write is answered "#N is written: <line>" before the card, a list with lines left ends with `delvetalk anthology lines / from: N`, and `lines {from}` shows the card from there. A stranger's admit is the keeper law's refusal, a missing number `noLine` with the card.
- **Laws that guard fields** read `owner: unchanged(owner) and (request.subject == new.owner or (request.kind == 0 and unchanged(…)))`. Kind 0 is the object's own method writes; a `world-propose` write and a migration's state are kind 3 (`proposed`, HOST-HANDOFF 93), so the kind clause admits no proposal; without the kind, anyone's reprogram or amendment (which change no field) passes; without `unchanged(owner)`, a migration could write the owner that admits it. Never write `request.kind == 0 implies X`: it says nothing of kind 3. Tide has an owner (filled at creation) who alone reprograms or amends it. Every law has a reading. A Bend predicate may refuse with a reading (`Abi.Verdict.refused {clause, reading}`).
- **Refusals are sums.** `Card.Refusal {clause, reading}`; a card shows `refused <clause>: <reading>` or `Not done: <reading>`. Such a result is an answer, not a turn's refusal: the turn is admitted and commits whatever it staged, so a method returns it before any write; to end a turn with nothing written, `refuse("why")` (`evaluation`, transient). One `refusal(w) -> Card.Refusal` match per object that names its own whys: Avatar, Deal, Garden, Place, Policy, Thing, Tide, Wake; Directory, Env, Record, Kind and Workshop carry `Card.Refusal` in their results.
- **Mailbox.** An Avatar's `send` inserts a `Rows.Letter` into its `outbox` (keyed {at, n}, 64); `subscribe {to}` subscribes to another avatar's outbox, delivered to `mailed`; `watch {to, field}` follows any field (a bell's `rung`), delivered to `news`; `unsubscribe {to}` ends either. It follows at most 32; the host serves at most 32 changes a turn (`unserved`) and 64 subscribers an object. Its inbox is keyed {at, from, n}, 64 kept. There are no observers anywhere.
- **Layers.** `world-reprogram {mode: extend}` with a module `type State = Super.State` overrides what it defines; `tests/test_layers.py` (Louder over Bell) keeps rain; `tests/test_extend.py` `LateBinding` grafts `layer over ./Bell.obend` by the `extend` message and a rain reply's card starts LOUDER.
- **Scenes.** `world/lib/Scenes.obend` is the data (`sum Op`, `sum Test`, choices with effects and guards, passages of at most 600 characters); `world/lib/Spween.obend` lowers spween to it (refusing weight, `~ call`, `has:` by name); a ```spween block posted to a Scene makes `<scene>/<id>`. Scene has guards, effect lists, END, `requires`, a cooldown, `presence` keyed {who} (16) and `left` keyed {at, who} (64).
- **Idioms.** `::<T>` only where a world call's result cannot be inferred (`world.view::<S>`, `world.call::<R>` when the result is read, `world.interpret::<R>`). Self-write `write {field: add n | set v | append x | remove x | amend x with c | insert r | upsert r | retract k, …}` (`remove` is `removeItem`, or `retract` on a relation); a computed edit is `world.write(extend(keep(), {…}))`; bind a write's answer with `let written(_) = write {…}`. Strings are interpolated (`"{expr}"`; an `if` inside a string is a `let` first). An activity composes only in tail position; a reusable method takes `then: Result -> T`. No `else match`: put the match in its own def. Payloads are Data: give the value where Data is expected.

## 2. Relations (docs/RELATIONAL.md is the contract)

- **The library** (`world/lib/Relation.obend`, imported `as Relations`). `sum Relation<T>: rows: {items: List<T>}`; `record Decl {field, key: List<String>, limit}`; an object declares its relation fields with `def relations() -> Relations.Decls`, which the kernel lists in the artifact. Pure queries: `rows`, `empty`, `where`, `project`, `count`, `exists`, `lookup(rel, key, keyOf)`, `order`, `group`, `joinOn(left, right, leftKey, rightKey)` (one merge; both sides in the order of their join keys), `fromList(items, keyOf)`, and `insert`/`upsert`/`retract`, the host's table applied in Bend so a card can show what its own write leaves.
- **Keys in Bend.** A key is the key projection as a record (`rainKey(r) = {author: r.author, at: r.at, n: r.n}`), and `Relations.compare` is the kernel's `canonicalCompare` (0/1/2 by canonical DAG-CBOR bytes, the host's own order: a shorter map key first, so `{author, at, n}` sorts by `n`, then `at`, then `author`; a text by byte length, then bytes). Rows are records: a relation of principals is `Rows.Greeting {principal}`. Shared row types (`Rain`, `Greeting`, `Presence`, `Trace`, `Letter`, …) live in `world/lib/Rows.obend` so a Wake can import them.
- **Ordinals.** A row an author may add twice at one height carries `n`, the relation's count at the turn's read, in its key. Since `n` sorts first and only grows while nothing is retracted, key order is the order of arrival. Only one author's two writes at one read height and count collide (`keyTaken`), which no current object does.
- **Declared relations and limits.** Record `lines` {author, n} 128 (the bell body: 768, a rain 1 to 200 characters), `admitted` {n} 128 and `marks` {name} 16; Kind `made` {object} 1,024; Library `pages` {name} 32; Directory `doors` {label} 64 (rows `Listed {label, description, to, examples, watch, place}`, the menu ordered by `place`), `greeted` {principal} 2,048, `news` {card} 64 and `visits` {principal} 64; Deal `signatures` {principal} 64; Garden `pending` {principal} 64 and `children` {object} 2,048; Tide `subs` {who} 32 (`subsMax`, the sends one tick makes); Env `buffer` {at, actor, uri, n} 256 (an event keeps 280 characters of its text); Place `present` and `things` {object} 256, `traces` {at, who, action, n} 64; Avatar `inbox` {at, from, n} and `outbox` {at, n} 64; Scene `presence` {who} 16 and `left` {at, who} 64 (an entry is `crowded` while cooling departures, readers present and the entrant would pass 64, so a cooling row is never dropped); Place also `made` {object} 1,024 and `held` {principal} 64 (declared, and read by nothing: the parked garden's); Workshop `held` {n} 12. Every limit times its widest row fits in 256 KiB of canonical bytes (HOST-HANDOFF 108; `tests/test_relation_limits.py` fills the Bell, Garden, Directory, Workshop and Env to their limits at their widest and writes once more). Past the limit the host drops the first rows in key order. An unbounded collection is a sequence of child objects, never one relation. Still lists: doors on every card, Policy's teaching lists. Records by design: RELATIONAL §9 "Stays a record".
- **Laws.** Tide's predicate merges old and new rows: every key added, replaced or retracted must be the requester's (`tests/test_wakes.py`). Directory's `greeted` and Deal's `signatures` are `insertOnly` in law text; a row the retention dropped does not count.
- **Seeds on the wire.** A relation seed is the `rows` variant (`tests.test_turn_world.relation(*rows)`, rows in key order; `{"tag": "variant", "label": "rows", "payload": {items: [...]}}`); `deploy/genesis.py` seeds the directory's doors that way.
- **Costs** (hbox, `tests/test_relation_lib.py`): `joinOn` of two stored 200-row relations 188,023 ticks with building them (about 400 a row); `fromList` of 64 reversed rows 57,457. A card joins at most a few dozen rows per turn, and sorting belongs to the host.
- **Derived views.** `def views() -> Lists.List<String>` names pure definitions `(state, context) -> first-order data` another object reads with `world.viewDerived::<T>({object, view})`. Garden `byColour` (a relation of `Tally {colour, count}` from its children rows); Place `affordances` (a Document of `acquire` for each thing lying there and `move` for each exit). A view is declared, so `inspect` lists it and `viewDerived` calls it, but it has no form: `?` and the usage never show it, and no spell can invoke it (`TurnLoop.lean` filters views from the forms; `delvetalk garden ?` has no `byColour`). `tests/test_derived_views.py`, `tests/test_view_derived.py`.

## 3. The surface as it stands

What an object asks of the world, and the shape every object has at 189b534:

- **The world.** `world/lib/World.obend`: `Message {object, method, argument}`, one closed result sum per method (`refused {clause}` on each, `denied {}` on reads), and `protocol world:` with `view`, `viewField`, `viewAt`, `viewDerived`, `write`, `judge`, `call`, `callVia`, `run`, `send`, `sendVia`, `create`, `createUnder`, `await`, `awaitUntil`, `awaitPost`, `awaitPostUntil`, `interpret`, `offer`, `publish`, `reprogram`, `extend`, `amend`, `inspect`, `check`, `grant`, `grantWith`, `revoke`, `objects`, `card`, `subscribe`, `unsubscribe`. `Changed {object, field, version, inserted, retracted}` is what a receiver takes, with its own row types for the two lists. There is no `spell` method: the host's spell path runs methods directly. `tests/test_world_protocol.py` runs a message-dialect object through the host.
- **What went.** `Plan.obend`'s `Plan`/`Response`/`Handled` sums and their payload records, Card's Plan-dialect helpers (`Heard`, `Routed`, `route`, `withBare`, `fitting`, `answerLensed*`, `tellPlan`, `merge`, …), the observer convention (`Observer`, `broadcast`, `notified`, `notifyRows`), `Form.Lens`, Spell.obend's `fit`, `bare` and block and field-line readers (the host's `spell-parse` is the grammar; `tests/test_spell.py` and `tests/test_host_spell.py` test it against fixtures; a reduced reader of the last spell line stays for `Card.unanswered` and `spellAction`), `Relations.insertedOnly`, the Seed ritual, every hand-written `Edits`/`keep()`, the Wake's Bend law, the Directory's Bend greeting cap, Document's unused variants, `Encounter.obend` and `Phrasebook.obend` (WORLD-REVIEW, status section).
- **Size.** `world/` is 6,046 lines (objects 3,619 in 15 files, bodies 111 in 2, libraries 2,251 in 19, READMEs 65), from 5,987 before the review.

## 4. Open

- VOICE "Card texts re-cut" and hob's lines (VOICE "For the lanes"): check each card against VOICE's strings. Queued, objects.
- A hand-written `forms()` beside form blocks is not yet refused (kernel). Check: a named diagnostic in `test_sugar`.
- **Per-reader actions.** The host offers a reader only what the law and a card's `actions(state, context)` leave (HOST-HANDOFF 103); the bell and cistern bodies declare `actions` (door and undoor for the owner alone), so the Directory's `learnedOf` no longer filters `Card.ownerActions` (gone). Other cards with guards kept in Bend (Deal's countersign, Avatar's owner-only methods, Workshop's adopt) may declare theirs. Queued, objects; check: a stranger's `world-inspect` of each lists no action its method refuses them.
- A Scene passage is not editable once made; spween `tags`, custom fields, floats and negative numbers are skipped or compared as text; a scene near the 16 × 8 limit has not been measured.
- `run` refuses variant arguments and recursive results: build in a probe module.
- A kernel hint can mislead: an unbalanced parenthesis is reported with "there is no Maybe builtin" or "definitions are `def name(x: T) -> U:`".
- `transport/http.py` `MAX_BODY` (64 KiB) answers 413 for a larger body.
- **A Record drops lines past its limit** (128; the bell's 768), admitted ones with the rest: the record of admitted lines belongs in child pages (`anthology/page/n`). Queued, objects; check: an admitted line survives 129 later writes.
- **A blank reply's answer card** is the card plus `Card.usage` (every form's template), which the renderers' budget does not count; a Record's passes 1,400 with eight long lines. Queued, objects (Card.answerCard); check: a blank reply to a full record is at most 1,400 characters.
- **The tide's door line** says `tick N` without MENU's `next at clock C`: the delivery carries the new tick count but not the tide's `last` or `gap`. A second watched field per door (`last`) or a derived view would give it. Queued, objects; check: the genesis menu reads `TIDE · tick N, next at clock C`.
