# Objects handoff

State on 2026-10-10 (foundation f178383; §1a and the relational lines by lane/objects6 on foundation 613639d; the Wholeness migration section by lane/objects8 on foundation b44440e).

## Summary

World objects are `.obend` files in `world/objects/` (24 objects: Anthology, Appointment, Appointments, Avatar, Bell, Cistern, Commons, Counter, Deal, Directory, Door, Env, Garden, Lantern, Loop, Place, Policy, Scene, Seat, Table, Thing, Tide, Wake, Workshop). Libraries are flat-named modules in `world/lib`, `world/lib/prelude`, `world/lib/document`, `world/lib/game`; an object imports them by basename. Every object follows the card protocol (`world/lib/Card.obend`).

- Needed first: `Plan.obend` (the host contract; `write {field: op value}` sugar), `Card.obend` (route/answer/lenses/interpretation), `Spell.obend` (spell grammar), `Policies.obend` (policy state; lives in lib because Policy declares a law and cannot be imported).
- Run: `make check`; narrow `DELVETALK_OBEND=<binary> python3 -W ignore -m tests.run test_objects test_spell …`. Compile-only: put a `delvetalk-obend` binary in `DELVETALK_OBEND`; never run `lake`, never commit the binary.
- Tests: 896 `def test_` across `tests/test_*.py`. `tests/host.py` fails any host reply whose card or offer text contains `bafy` (no hash in a card; cite `<object> v<n>`).
- Tick budgets that tests pin: Bell card of 1,025 rains 76,511 (`test_tariff`; 76,485 before the rains were a relation); 64-field spell parse 79,583 (`test_tariff`); glm's 1,788-character reply under a bell under 20,000 ticks and the directory's reading under 250,000 (`test_hub`); `test_places` under 100,000.
- Lawful objects (declare `law`): Anthology, Commons, Deal, Directory, Env, Garden, Policy, Scene, Table, Thing, Tide, Wake. A creator cannot import a lawful module; their owners make them with `world-create`.
- Open: section 4.

## 1. Conventions

- **State, Seed, seeded, initial.** `record State`, `record Seed` (or `type Seed = {}`), `defaultSeed()`, `seeded(seed) -> State`, `initial() = seeded(defaultSeed())`. The host's `create` lays the seed (a record naming some State fields) over `initial()`; it does not call `seeded`. `world-create` takes a whole State. The host fills a text `owner` from the creating principal when the seed names none.
- **Card protocol.** Every object has `render(state, context) -> Document` (the card as the reader sees it; `Card.stranger()` is a nobody Context), `forms() -> Card.Forms`, `blurb()`, and `receive(state, input: Card.Heard, context)` with `Heard = {text, post}` (a turn's argument may carry `slot`; the record reads only these two, and the host drops or fills `slot` by the declared type). Usual receive: `Card.route(text, context, forms())` (`Card.routeHeard(input, …)` keeps the post), `act` dispatched by action, anything else `Card.answer(routed, context, forms(), render(state, context))`. `Routed`: act, usage, unclear, refused, set, help, quiet.
- **Handles and the clock.** `Card.name(did, context)` shows the reader's own observed handle (`context.handle`) and anyone else as `Card.handle`: never a raw DID, a long fragment is `…` and its last eight. A handle stored when the host knew it shows by `Card.shown`. Deadlines compare `context.clock`, which only `world-advance` moves.
- **Reader-specific cards.** `Card.reads(principal, context)`, `Card.mine(principal, context)` (" (yours)"). A member sees more: an Env's events, a Wake's triggers, an Avatar's notes and follows, a Deal's countersign spell, a Policy's teaching card, a Scene passage, a Commons' gates.
- **Spell shape.** A card name is `[a-z0-9:/.-]+`, at most 160 bytes; actions and fields `[a-z0-9-]+`; `?` is an action. Fields follow the action separated by ` / ` or commas. The spell is the post's last delvetalk line that is not quotation (indented four or a tab; `>` and fence lines are never spell lines). Block values: `field: <<DELIM` (1 to 32 of A-Z 0-9 _) takes the following lines up to a line that is exactly DELIM; unclosed is refused by name ("the block <<BEND for source is never closed by a line BEND"). Workshop reads `source:` as its code. A literal brace in Bend source is `{{`/`}}`.
- **Lenses.** `Form.Lens<E>.lens {field, form: Form.Kind, put}`; an object exports `lenses()` and answers with `Card.answerLensed(routed, context, forms(), lenses(), guard, card)` (`answerLensedAs` for an own result type). `delvetalk <card> set` plus one `<field>: <value>` line is judged against the kind and written through `put` (a non-empty guard refuses by name first; the law judges the write); `?` answers the usage card. Lenses: Policy (model, system, escalate), Avatar (handle), Place and Thing (name/description), Garden (confirm). Workshop has none. `Card.valueText/valueNatural` read a Value.
- **Interpretation (Garden, Directory).** A card with a policy views it (`Plan.view`, state type `Policies.State`) and asks with `Card.asking(utterance, forms, reference, policy, attempt, needs)`. `Card.fitting(text, forms)` reads the reply `replied {text}`: `hit {card, parsed}`, `silent` (`unclear: not addressed` or empty), else `miss {needs}`. A first miss is asked once more (utterance plus `\n\nmissing: <needs>`, `model:` the policy's `escalate`); a second offers the needs card and, when `escalateTo` names a principal, `Card.escalation`'s copy to it. A host `unclear {needs}` is not retried. An activity composes only in tail position, so the object owns the loop (`interpreted`/`readBack` in Garden, `interpreting`/`readBack` in Directory); Card gives the Plans, the reading and `Card.unfit`. A read-only root that moves while the interpretation waits does not make the resumption stale.
- **Confirmation per action.** `Policies.State.confirmFor` (default reprogram, amend, offer; owner's `delvetalk policy confirm / action: plant / ask: yes|no`) names what an interpreted proposal waits for a yes before (`Card.confirms`). Garden keeps its own `confirmFor` (its `confirm` lens adds or drops plant). Directory shows a confirmed action's spell back instead of passing it on. A card holding a proposal for its speaker reads a bare answer first, with no model call: `Card.answerOf(text)` is yes (yes, y, yeah, yep, ok, okay, sure, go ahead, do it) or no (no, n, nope, cancel, never mind), in the case people write them, a closing `.` or `!` aside; Garden answers a bare yes or no with nothing of the speaker waiting `refused nothingWaiting` instead of interpreting it.
- **Completing a spell.** An unclear spell is held for its speaker (Garden `Pending {principal, spell, needs}`; empty needs = waiting for yes); a reply of only `name: value` lines (`Card.onlyFields`) is appended (`Card.completed`) and judged again. Directory passes field-only lines whose first name is a field of a door's form to that door as they are.
- **Macros.** Policy `macros` (owner: `delvetalk policy macro / name: … / pattern: moth for {who} / expansion: garden plant / colour: violet`; a same-named macro is replaced; sixteen; a pattern starts with a word). Garden and Directory check `Card.expanded(text, policy)` before the model: words compared exactly (a trailing `.!?` dropped), a `{hole}` takes the shortest run of one or more words that lets the rest match; a hit is dispatched as a typed spell with no interpret. Garden's `?` appends `Card.macroUsage`.
- **Handed to the directory.** Quiet prose is sent by Card's default (`Card.forwarded`) to `directory` (`Card.directory`, the genesis id) as `receive {text, post}` under the speaker; the card offers nothing. A turn some object started forwards nothing. The directory keeps `words` (door labels and ids, form actions) and `fields` (form fields), learned by inspect when a door is added or on the first handed-on reply after a seeded genesis (`writeOnce`), and sends to the model only prose that `Card.mentions` (a word, or a field as `name:`), scanning the first 2,000 characters. At judgement it counts only methods that take fields, as offered forms do (the method table also lists helpers such as here, guard, reading); a bell's `rain` is always known (`knownFields`). It also reads the first object under each door (`objects {prefix}`, then inspect), and a handed-on reply does not count its caller's family. A door added before its object exists learns only its label and id. A card cannot `view directory` (a view answers in the card's own state type); the hand-off is a send, not a call.
- **Admitted act answers with its card.** A rain from a reply (`Bell.rainedCard`) and a submission (`Anthology.submittedCard`) offer the card as the write leaves it; the direct `rain` and `submit` answer only their count.
- **Link doors.** A Directory door whose `to` is nobody (genesis's STUDIO) answers its word with `<label>\n<description>` and is skipped when field lines and the model look for forms.
- **Env.** `Env.receive` from anyone but the owner is taken in as a `mention` event (`Event.handle`); the law admits that receive (kind 0, method receive, owner/handle/seen/subscribers unchanged). Arrival seeds `handle`; the card reads "ENV of <handle>" with the newest eight events, one line each (first line, 100 characters). An Env lives at `Events.envOf(did)` = `env/<did>`; one elsewhere refuses publish. Its buffer holds 256 (the host drops the oldest).
- **Workshop.** Views its target (state type `Data`) and says "Was: bell-1 v1 / Now: bell-1 v2". A `propose` the target's law refuses is held as `{n, target, package, migration, proposer, proposerHandle}` (sixteen; a seventeenth drops the oldest); `adopt / n` runs the reprogram under the adopter, so the target's law admits only its owner; `withdraw / n` is the proposer's. Compile, program, packageBytes and migration refusals are not held.
- **Scoped resolution (Avatar).** An Avatar's own principal's prose with no spell names its object by the first word that is a thing lying in its place, else an object of that id (the doors: garden, rooms, play); the avatar `send`s `delvetalk <id> <action>` with the rest of the line in the form's first field. Two of a name are answered "Which one: …?".
- **Place.** Forms `say {line}`, `emote {line}`, `whisper {to, line}`: offered under the speaker's name to every avatar present (in key order, at most 32); someone not present is refused by name (`notPresent`). Each enter, leave, take, put and talk is traced, admitted or refused, as `Trace {who, handle, action, clause, at, n}`, 64 kept by the host (the card shows the newest eight); a refusal therefore writes a trace.
- **Thing.** `copyable` (default true; owner's lens). The Workshop's `create / like: <thing>` sends `copy`; the thing creates a Thing from its own package with its state minus holder, offer and owner (the host fills owner with the creating principal). Not copyable is refused by name.
- **Doors on any card.** `Card.Doorway {label, to}`, `doors: Card.Doorways`, `Card.doorForm()`/`undoorForm()`, `Card.dooring` (owner's; eight at most; `doorTaken`, `doorsFull`), `Card.doorLines`. Bell has them; Garden plants each bell with `garden: <garden>`.
- **Wake.** `On.writes {object, field, above}`; `watch` with it sends the watched object `observe {object: wake, method: "written"}`. Garden keeps observers and tells them `{field: "planted", value}` after each planting; `Wake.written` fires when the value passes `above`. A Wake is also a rule over rows (RELATIONAL §7): `On.rows {object, field, where: [Where], atLeast}`, a `Where` one of `equals {column, equals: Relations.Cell}` (canonical bytes), `above {column, above: Nat}`, `below {column, below: Nat}` and `contains {column, contains: String}` (a whole word, by `textHasAny`); `watch` sends `observe {object: wake, method: "rows"}`; the observed object tells observers whose method is `rows` what a write inserted (`Card.notifyRows(observers, field, rows, then)`, `{field, rows}`, each row `Card.Row`, its columns by name with natural or text values, since Bend cannot read Data), and `Wake.rows` fires a trigger once when at least `atLeast` (at least one) rows match every pattern. Every other observer gets the object's own message (`Card.ownObservers`), so a door told on a ring is never sent rows. Bell tells of each rain; Garden's planted count goes only to its own observers.
- **Deal.** `amendment {object, law}` (object "" for none). The countersignature that brings the deal to rest performs `amend` with the deal as caller, judged by the object's own law; a refusal is answered `amendRefused`, the signature standing.
- **Hub.** Directory passes a spell naming another card to its receive by call, greets each principal once, is silent to its owner, answers a door word with that door's card. Garden ends with no offer for prose the model calls `not addressed`. Tide answers subscribe and tick with its card.
- **publishPage.** `Card.publishPage(name, page)` performs `publish {page: name, section: "", body}`, where `name` is the one given or "" for the door word. Garden, Scene, Table, Workshop, Anthology and Tide expose `publishPage` (every door object publishes a page); the host lists the publication (`world-publications`).
- **Pages.** An object with a page keeps `owner` and `pageCheckpoint`; `Card.isMerge` and `Card.merge` record the owner's `merge` reply (Garden).
- **Anthology.** Owner admits. The owner's handle is seeded as `ownerHandle` and stored at each admission.
- **Laws that guard fields** read `owner: request.subject == new.owner or (request.kind == 0 and unchanged(…))`; without the kind, anyone's reprogram or amendment (which change no field) passes. The host prints a law fully parenthesised. `world-amend` does not parse a law text with a reading ("law syntax"): amend with `law NAME: EXPR`. `law(old, new, request)` Bend predicates run after the text admits a kind-0 write (Tide: self, tooSoon; Wake: owner); `tests/test_laws.py` shows them biting. Scene's cooldown is a Bend `law` over `context.clock` with no law text. Scene and Table keep `owner` and `law owner "...": request.kind == 0 or request.subject == new.owner`.
- **List edits by item.** The index forms are gone from Plan.obend (objects6): `amendItem {item, change}` and `removeItem {item}` address the first item with the same canonical bytes (`absentItem` when none); find the stored item with `Lists.find`.
- **Composition.** An activity composes only in tail position; a reusable method takes `then: Result -> T`. No `else match`: put the match in its own def. Payloads are Data: give the value where Data is expected; `Plans.nothing()` is the empty payload.
- **Idioms.** No `::<…>` (type arguments are inferred; a definition whose parameter appears in no argument needs a smaller signature). Self-write `write {field: add n | set v | append x | removeItem x | insert r | upsert r | retract k, …}` (the kernel's `remove i` lowers to a constructor Plan.obend no longer has) (amendItem, keep-only and computed Entries stay `Plan.write(...)`); bind a write's answer with `let written(_) = perform(…)`. Forms are `form ACTION [as NAME]:` blocks. Strings are interpolated (`"{expr}"`; an `if` inside a string is a `let` first). Every law has a reading: `law owner "only …": …`.
- **Refusals are sums.** `Card.Refusal {clause, reading}` is the payload of `Card.Reply.refused` and `Card.Routed.refused`; a card shows `refused <clause>: <reading>`. Protocol clauses: otherCard, noAction, oneField, spell, notSettable, noField, notOwner, badValue, noPost. A `sum Why` (one arm per refusal), `why(w)`, `clause(w)` and `refused(w)` builder: Thing, Place (its Done is Thing's and Avatar's), Garden (`world {clause}` keeps a host clause such as requiredAbsence), Tide, Wake, Deal, Policy. Scene, Commons, Avatar (Mailed), Anthology, Appointments give a clause at each site. `{reason}` payloads remain in Directory's `Heard.refused`, Seat and Table `Done`, Env `Done`, Appointment, Workshop's `Verdict`, Avatar's `Moved`, and `Card.Change`.
- **Observers and mailbox.** `Card.observing` (16) and `Card.observingUpTo(…, cap)`; `Card.broadcast`. An Avatar's mailing list holds 32 (the host's `sendsPerTurn`; a turn past it is refused whole, "turn exceeds the send capacity"); its inbox keeps 64.
- **Layers.** `world-reprogram {mode: extend}` with a module `type State = Super.State` overrides what it defines; `tests/test_layers.py` (Louder over Bell) keeps rain; `tests/test_extend.py` LouderBell grafts `layer over ./Bell.obend` by the `extend` Plan and a rain reply's card starts LOUDER.
- **Scenes.** `world/lib/Scenes.obend` is the data (Choice {label, to, effects, guard}, Effect set/add/sub, Clause, Seed {title, start, passages, cooldown, requires}); `world/lib/Spween.obend` lowers spween to it (refusing weight, `~ call`, has: by name); a ```spween block posted to a Scene makes `<scene>/<id>` (id's `_` become `-`). Scene has guards, effect lists, END, `requires` and a cooldown.

## 1a. Relational (objects6; docs/RELATIONAL.md is the contract)

* **The library** (`world/lib/Relation.obend`, imported `as Relations`). `sum Relation<T>:
  rows: {items: List<T>}`; `record Decl {field, key: List<String>, limit}`; an object declares its
  relation fields with `def relations() -> Relations.Decls`. Pure queries: `rows`, `empty`,
  `where`, `project` (a List), `count`, `exists`, `lookup(rel, key, keyOf)` (stops past the
  key), `order(rel, by)` and `group(rel, by)` (a stable merge sort; `Group<T, K>.group {key,
  rows}`), `joinOn(left, right, leftKey, rightKey)` (one merge; both sides must already be
  in the order of their join keys, i.e. the relation's key or its leading canonical
  columns; `Joined<A, B>.pair {left, right}`), `fromList(items, keyOf)` (sort; of a key the
  first row kept), and `insert`/`upsert`/`retract`, the host's table applied in Bend so a
  card can show what its own write leaves.
* **Keys in Bend.** A key is the key projection as a record (`rainKey(r) = {author: r.author,
  at: r.at, n: r.n}`; `keyOf: T -> K`), and `Relations.compare` is the kernel's
  `canonicalCompare` (0/1/2 by canonical DAG-CBOR bytes, the host's own order: a shorter map
  key first, so `{author, at, n}` sorts by `n`, then `at`, then `author`; a text by byte
  length, then bytes; it is written out from the type, any first-order type, monomorphised
  in generic definitions). `Relations.Cell` (natural or text) stays as the value a Wake
  pattern names and an observer's row column carries. `insertedOnly(old, new, keyOf)`
  compares whole rows with it.
* **Edits** (`Plans.Entries`): `insert {row}`, `upsert {row}`, `retract {key: Data}` (the key
  projection as a record) beside the six; a self-write of one is `write {rains: insert rain}`
  (`upsert row`, `retract key`); a computed or mixed edit stays `Plan.write(...)`.
* **Declaring.** `def relations() -> Relations.Decls`, each `{field, key, limit}`; past
  `limit` rows the host drops the first in key order (0 is its default, 4,096). A relation is
  bounded: an unbounded collection is a sequence of child objects (`anthology/page/n`),
  never one relation. Limits: Bell rains 2,048, Env buffer 256, Place traces 64, Directory
  greeted 4,096, Anthology proposals 1,024, Tide subs 1,024.
* **Ordinals.** A row an author may add twice at one height carries `n`, the relation's count
  at the turn's read (`Relations.count`), in its key: `{author, at, n}`. Since `n` sorts
  first (one letter) and only grows while nothing is retracted, key order is the order
  of falling, and a card that listed the old list in append order lists the relation the
  same. Two concurrent turns that read one root give two rows one `n`; their authors or
  heights differ, so the keys do. Only one author's two writes at one read height and
  count collide (keyTaken), which no current object does.
* **Migrated / records.** Migrated, with key and limit: Bell `rains` {author, at, n} 2,048;
  Tide `subs` {who} 1,024 (the Bend cap stays 64: a tick sends to every due one); Directory
  `doors` {label} 64 and `greeted` {principal} 4,096 (rows `Greeting {principal}`: a
  relation's rows are records); Anthology `proposals` {author, at, n} 1,024; Deal
  `signatures` {principal} 64; Garden `pending` {principal} 64 and `children` {object}
  4,096; Env `buffer` {at, actor, uri, n} 256 (rows `Env.Sensed`, an Event with `n`; the
  host drops the oldest, so the Env no longer removes its own); Place `present` and
  `things` {object} 256 and `traces` {at, who, action, n} 64 (the card shows the newest
  eight). Thing and Avatar declare `relations()` of none, because they import Place (see
  "Against the host"). Still lists: observers and doors on every card. Records by design: RELATIONAL §9 "Stays a
  record".
* **What the cards show now.** Bell, Anthology (n first: the order of falling, so a line's
  number is unchanged) and Garden (`garden/bell/<n>` sorts by length then bytes, so in
  planting order) show what they did. Tide's subscribers, a Deal's signatures and who is
  in a Place (its "Here:" lines and the order talk is offered in) are listed in key order (by `who`/`principal`: shorter DIDs first), no longer in the order they came.
  The Directory's menu keeps the owner's order: a door row is `Listed {label, description,
  to, place}` and `menu(state)` orders by `place` (an added door takes one past the last;
  genesis seeds 0..6), while every walk whose order does not show uses key order
  (`doors(state)`). `add {door: Door}` is unchanged; `remove` is a `retract {label}`.
* **Laws.** Tide's `ownSubs` is one merge of old and new rows: every key added, replaced or
  retracted must be the requester's (`tests/test_wakes.py` checks the four cases).
  `insertOnly` parses now (kernel) but the host's Law.lean denotes it false (fail closed)
  until relations day 2, so Directory's greeted and Deal's signatures say it in the Bend
  predicate, `Relations.insertedOnly(old, new, keyOf)` (one merge; clauses `greeted`,
  `signed`), with a TODO(insertOnly) beside each to move it into the law text then.
* **Seeds on the wire.** A relation seed is the `rows` variant (`tests.test_turn_world.relation(*rows)`,
  rows in key order); `deploy/genesis.py` seeds the directory's doors that way with places.
* **Against the host** (host7, foundation 613639d). The edits, canonical order, keys and
  limits are the host's now; inserts do not yet commute (relations day 2), so a turn whose
  root another write moved re-runs: two prose replies of one speaker to the garden (each
  upserts that speaker's pending row) cost a second interpretation of the later one
  (`test_policy ...checkpoint_blocks_once`). Two host behaviours to know: (1) a package
  any of whose modules declares `relations()` has the ENTRY module's `relations()`
  compiled, so a package importing a module that declares relations (Thing and Avatar import
  Place) or an object made from such a chain (a Cistern dug from Garden's) must declare its
  own (they declare none), else creation fails "missing selected entry"; (2) that compile
  runs at every creation: 20 bells 6.7 s with `relations()` and 0.31 s without (the test
  lane has since dropped `test_journal.Maximum`'s wall-clock bound). Wire: a relation is
  `{"tag": "variant", "label": "rows", "payload": {items: [...]}}`; `tests.test_replay.rows`
  reads one, `tests.test_turn_world.relation` builds one.
* **Costs** (hbox, `tests/test_relation_lib.py`, with canonicalCompare): `joinOn` of two
  stored 200-row relations 188,023 ticks with building them (linear, about 400 a row: RELATIONAL
  §4's "a few thousand ticks" for two hundred-row relations is two orders low); `fromList` of
  64 reversed rows 57,457. So a card joins at most a few dozen rows per turn, and sorting
  belongs to the host.

* **Derived views** (FOUNDATION §16). `def views() -> Lists.List<String>` names pure
  definitions `(state, context) -> first-order data` another object asks for with
  `viewDerived {object, view}` -> `derived {version, value: Data}` (both appended to
  Plan.obend). Garden `byColour`: a relation of `Tally {colour, count}` keyed {colour}, from
  its children rows, which now keep the bell's colour (`Child {world, object, colour}`);
  Place `affordances`: a Document of its forms, `delvetalk <thing> acquire` for each thing
  lying there and `delvetalk <reader> move / exit: <label>` for each exit (pure, so it cannot
  read the things' own forms). The host answers "plan not supported: viewDerived" until it
  lands; `tests/test_derived_views.py` runs both views as pure probes and holds the
  end-to-end case as an expected failure.

* **The world protocol** (WHOLENESS §1; objects6). `world/lib/World.obend` is the `protocol
  world:` declaration (KERNEL-HANDOFF §17): `Message {object, method, argument}`, one closed
  result sum per method (`refused {clause}` on each, `denied {}` on reads), `Derived<T>`,
  `Subscribed`, and `Changed {object, field, version, inserted, retracted}` (Data; a
  subscriber types the two lists in its own `changed` input). Every method host8 answers is a
  line (`viewAt`, `viewDerived`, `viewField`, `subscribe`, `unsubscribe` included); `spell` is
  not, because host8 lists it but has no arm for it. `tests/test_world_protocol.py` compiles a
  message-dialect object and runs it through the host: a write, a subscription and its
  `changed` delivery, `viewAt` and `viewDerived`.

### Wholeness migration: where it stands (lane/objects8 stopped here; a successor starts from this)

lane/objects8 (on foundation b44440e, tested against the host10 binary that adds called-receive
reading, `proposal {object}`, Verdict readings and the default page) moved, one commit each:
Scene, Workshop, Directory, Bell, Env and Wake together (coupled), Garden and Policy. It also added
Lantern/Door `watch` and Commons `allow` to `methods()`, changed the Directory's `remove` to
`{door: {label}}`, gave `Abi.Verdict.refused` a `reading`, and deleted the five pasted
`publishPage`s. Seventeen objects now speak the message dialect. Still in the Plan dialect: **Place,
Thing, Avatar** (and Seats/Encounter libraries they use).

**What the moved objects settled (read the commits for the detail).**
* A spell's method cannot see the reply's post. The Garden plants with `context.intent` as the
  planting post when `inputOrigin.kind == "spell"` (the bridge names a turn by its post). Host item:
  `Abi.Context.inputOrigin.post`. Deal's countersign still cites the post through `receive`.
* A form-expressible method input becomes a host form, and the host routes a reply's first bare
  field line to it. So a method that is not meant as a spell takes a nested record (Directory
  `add {door}`, `remove {door: {label}}`). A form's fields are exactly what the host accepts: extra
  lines are `unknownField`. Policy's macro expansion is therefore one field line that keeps its
  slashes.
* `?`, `set` routing, kind checks (`badValue`), unknown or extra lens fields, unclosed blocks and
  unknown cards are the host's (badSpell). `receive` sees blank text, prose, spells missing fields
  (with `fields`), and bare field lines naming no form. Blank-reply cards may add what the host's
  `?` cannot know (Garden's shortcuts from its policy).
* Interpretation: `world.interpret::<T>` with `Card.interpretation(...)`. A `proposal {object,
  method, argument}` runs (the Directory calls the door's method). `unclear` needs that are
  `not addressed` or empty mean silence; `model: …` means answer at once; any other is a miss
  asked once more (escalate model), then `Card.unfitted`. A `replied` text reads through
  `Card.prose` (`unclear: …` lines).
* Subscriptions replace observers: Door/Lantern on `rung`/`open`; Wake on env `buffer`
  (`changedSensed`), a scalar (`changedNat`, fires when the old value was at most `above` and the
  new is over it) and relations (one receiver per Rows type; `Rows.*Columns` projections).
  Receivers are helpers (the host delivers to them; no turn may name them) and check
  `context.caller`.
* Env takes mentions on `mention {text, post}`; `receive` would let the host retarget a quoted
  spell. Transport item: `bridge.py` `mention_turns` must send `mention`.
* Transport items left expectedFailure: http.py gives no `spell` template for a form with a choice
  field (test_hypermedia ×2); the play page does not render the host's `?` usage reply
  (test_http directory card).

**Remaining, in order.**
1. `git merge foundation` once the host10 merge lands. The expectedFailures it answers are already
   flipped (df72541, green against its binary); test_outbound's slot case comes with that merge.
2. Place, Thing, Avatar together (Thing and Avatar import Place's State/Done; WORLD-REVIEW 20
   moves those types to a library so Place can declare `law owner`). Lenses as data plus `set`
   (Place and Thing: name/description; Avatar: handle; Thing: copyable). Avatar's mailing list
   becomes an `outbox` relation (insert on `send`, limit with drop-oldest), followed by
   subscription. test_mailbox's bell follower is expectedFailure until then. host10 declared
   `methods()` for Place ("enter leave take put"), Thing ("transfer copy drop") and Avatar
   ("observe unobserve notice hold release"); keep the names whose methods remain.
3. With the last of them, the deletions: Card's `…Plan` helpers, `Routed`, `route`/`routeHeard`/
   `withBare`/`bareSpell`/`fitting`/`asking`/`unfit`/`escalation`/`onlyFields`/`completed`/
   `spellText`, observers (`Observer`, `observing`, `broadcast`, `notified`, `Change`,
   `Column`/`Row` and `notifyRows`), `forwarding`/`forwarded`/`sending`/`offering`/
   `answerLensed*`/`merge`/`checkpointed`, `Replied` (once nothing returns it), Spell.obend's
   parser apart from what `spellAction` and the Garden's and Directory's macros need, and
   Plan.obend's `Plan`/`Response` sums. Move Directory's and Deal's insert-only predicates into
   the law text (`insertOnly(greeted)` keeps the Bend 4,096 check: WORLD-REVIEW 10's trap).
## 2. Limits found

- An await only proves that some turn with that identity was admitted. A turn suspended on an object resumes refused `staleRoot` if anything wrote that object meanwhile, unless its writes are all keep/add/append (they commute).
- `run` refuses variant arguments and recursive results: build in a probe module.
- A kernel hint can mislead: an unbalanced parenthesis is reported with "there is no Maybe builtin" or "definitions are `def name(x: T) -> U:`".
- `transport/http.py` `MAX_BODY` (64 KiB) answers 413 for a larger body.

## 3. Directory of objects

Counter, Garden, Bell, Cistern, Anthology (owner admits), Directory (owner adds and removes), Door, Lantern, Loop, Place, Thing, Avatar (mailbox: subscribe, send, unsubscribe; handle lens), Policy (owner law with `request.method`; lenses), Workshop (check prints the checker's hint under its problem; inspect; propose), Env, Wake, Tide, Appointments/Appointment, Deal, Seat and Table, Scene (passages and choices as data; enter, choose, leave), Commons (places, paths, ways in, gates: open, members, object).

## 4. Open

- Place cannot declare a law while Thing and Avatar import it for State and Done (both still `import ./Place.obend`). Closes when those types move to a library module, as Seats did.
- An addressee `slot` reaches receive but no object reads it (`Heard` is `{text, post}`).
- A Scene passage is not editable once made; spween `tags`, custom fields, floats and negative numbers are skipped or compared as text; a scene near the 16 x 8 limit has not been measured.
- A kernel word-set builtin would remove the per-word loop cost of `Card.mentions`.
- Garden's `plant {colour}` should be `Bell.Colour` (a sum of empty cases), so the method table offers a `choice`. Tried (objects6) and held back: a model's JSON proposal and an HTTP form POST both send the colour as text, and the host does not take a label for an empty-payload case, so the JSON proposals of `test_policy` answer `unclear`. Needs the host to fit a label to the case of that name where the input type is such a sum (`interpretVerdict`'s `jsonData` path and world-turn arguments); then the Garden change is one line plus the tests' four `plant` calls.
