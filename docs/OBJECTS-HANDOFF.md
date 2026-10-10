# Objects handoff

State on 2026-10-10 (foundation f178383; §1a and the relational lines by lane/objects6 on foundation 613639d; the Wholeness migration by lane/objects8 on b44440e and lane/objects9 on 3dc374d, which finished it).

## Summary

World objects are `.obend` files in `world/objects/` (24 objects: Anthology, Appointment, Appointments, Avatar, Bell, Cistern, Commons, Counter, Deal, Directory, Door, Env, Garden, Lantern, Loop, Place, Policy, Scene, Seat, Table, Thing, Tide, Wake, Workshop). Libraries are flat-named modules in `world/lib`, `world/lib/prelude`, `world/lib/document`, `world/lib/game`; an object imports them by basename. Every object speaks the message dialect: `Activity<A>` over `world.*` (World.obend), the host parses spells and runs the method a spell names, and `receive(state, input: Card.Reply, context)` gets what runs no method.

- Needed first: `World.obend` (the protocol), `Plan.obend` (references, `Edit`/`Entries`, receipts: what messages carry), `Card.obend` (answer, tell, names, doors, pages, interpretation and macro helpers), `Policies.obend` (policy state), `Places.obend` (a place's State/Exit/Done, so Place can declare its law). `Spell.obend` keeps only the spell line's card, action and inline fields. `tests/fixtures/obend/Variant.obend` is the variant Plan dialect, for the tests of the host arms that still answer it (the host lane deletes them with those arms).
- Run: `make check`; narrow `DELVETALK_OBEND=<binary> python3 -W ignore -m tests.run test_objects test_spell …`. Compile-only: put a `delvetalk-obend` binary in `DELVETALK_OBEND`; never run `lake`, never commit the binary.
- Tests: 896 `def test_` across `tests/test_*.py`. `tests/host.py` fails any host reply whose card or offer text contains `bafy` (no hash in a card; cite `<object> v<n>`).
- Tick budgets that tests pin: Bell card of 1,025 rains 76,511 (`test_tariff`; 76,485 before the rains were a relation); 64-field spell parse 79,583 (`test_tariff`); glm's 1,788-character reply under a bell under 20,000 ticks and the directory's reading under 250,000 (`test_hub`); `test_places` under 100,000.
- Lawful objects (declare `law`): Anthology, Commons, Deal, Directory, Env, Garden, Place, Policy, Scene, Table, Thing, Tide, Wake. A creator cannot import a lawful module; their owners make them with `world-create`.
- Open: section 4.

## 1. Conventions

- **State, Seed, seeded, initial.** `record State`, `record Seed` (or `type Seed = {}`), `defaultSeed()`, `seeded(seed) -> State`, `initial() = seeded(defaultSeed())`. The host's `create` lays the seed (a record naming some State fields) over `initial()`; it does not call `seeded`. `world-create` takes a whole State. The host fills a text `owner` from the creating principal when the seed names none.
- **Card protocol.** Every object has `render(state, context) -> Document` (`Card.stranger()` is a nobody Context), `forms() -> Card.Forms` (the host reads their bounds, HOST-HANDOFF 5.69), `blurb()`, `methods()` (the State-first defs that are public beside its forms, 5.62) and `receive(state, input: Card.Reply, context)` with `Reply = {text, post, fields}`. The host runs a spell's method, answers `?` and `set`, and refuses misfits `badSpell`; receive sees blank text, prose, a spell missing fields and field lines naming no form, and `Card.answer` (or `answerAs` for an own result type) offers the card or hands prose to the directory.
- **Handles and the clock.** `Card.name(did, context)` shows the reader's own observed handle (`context.handle`) and anyone else as `Card.handle`: never a raw DID, a long fragment is `…` and its last eight. A handle stored when the host knew it shows by `Card.shown`. Deadlines compare `context.clock`, which only `world-advance` moves.
- **Reader-specific cards.** `Card.reads(principal, context)`, `Card.mine(principal, context)` (" (yours)"). A member sees more: an Env's events, a Wake's triggers, an Avatar's notes and follows, a Deal's countersign spell, a Policy's teaching card, a Scene passage, a Commons' gates.
- **Spell shape** (the host's grammar, FOUNDATION §5). A card name is `[a-z0-9:/.-]+`, at most 160 bytes; actions and fields `[a-z0-9-]+`; `?` is an action. Fields follow the action separated by ` / ` or commas, or on field lines. The spell is the post's last delvetalk line that is not quotation (indented four or a tab; `>` and fence lines are never spell lines). Block values: `field: <<DELIM` … `DELIM`; unclosed is refused `unclosedBlock`. A `source` field the spell lacks takes the reply's first ```obend fence (5.69). A literal brace in Bend source is `{{`/`}}`.
- **Lenses.** `def lenses() -> Lists.List<Form.Field>` (data) and `set(state, input: {field, value: Form.Value}, context)`: the host judges the value against the field's kind and runs `set`, which refuses a stranger by name (the law judges the write); `?` lists the lenses. Lenses: Policy (model, escalate, escalate-to, system), Avatar (handle), Place (name, description), Thing (copyable, name, description), Garden (confirm). `Card.valueText` reads a Value.
- **Interpretation (Garden, Directory).** A card with a policy views it (`world.view::<Policies.State>`) and asks `world.interpret::<T>(Card.interpretation(utterance, forms, reference, policy, attempt, needs))`. The host fits the model's spell and answers `proposal {object, method, argument}` (the Directory calls that door's method) or `unclear {needs}`; `replied {text}` reads through `Card.prose`: `not addressed` or empty needs are silence, others a miss, asked once more (escalate model), then `Card.unfitted` (the needs card, and the escalateTo copy). An activity composes only in tail position, so the object owns the loop.
- **Confirmation per action.** `Policies.State.confirmFor` (default reprogram, amend, offer; owner's `delvetalk policy confirm / action: plant / ask: yes|no`) names what an interpreted proposal waits for a yes before (`Card.confirms`). Garden keeps its own `confirmFor` (its `confirm` lens adds or drops plant). Directory shows a confirmed action's spell back instead of passing it on. A card holding a proposal for its speaker reads a bare answer first, with no model call: `Card.answerOf(text)` is yes (yes, y, yeah, yep, ok, okay, sure, go ahead, do it) or no (no, n, nope, cancel, never mind), in the case people write them, a closing `.` or `!` aside; Garden answers a bare yes or no with nothing of the speaker waiting `refused nothingWaiting` instead of interpreting it.
- **Completing a spell.** An unclear spell is held for its speaker (Garden `Pending {principal, spell, needs}`; empty needs = waiting for yes); a reply whose `Reply.fields` name the held planting's fields completes it (Garden `completing`). Directory passes field-only lines whose first name is a field of a door's form to that door as they are.
- **Macros.** Policy `macros` (owner: `delvetalk policy macro / name: … / pattern: moth for {who} / expansion: garden plant / colour: violet`; a same-named macro is replaced; sixteen; a pattern starts with a word). Garden and Directory check `Card.expanded(text, policy)` before the model: words compared exactly (a trailing `.!?` dropped), a `{hole}` takes the shortest run of one or more words that lets the rest match; a hit is dispatched as a typed spell with no interpret. Garden's `?` appends `Card.macroUsage`.
- **Handed to the directory.** Prose `Card.answer` does not take is sent to `directory` (`Card.directory`) as `receive {text, post, fields}` under the speaker; the card offers nothing. A turn some object started forwards nothing. The directory keeps `words` and `fields` (learned by inspect) and sends to the model only prose its own `mentions` scan finds naming one (the first 2,000 characters).
- **Admitted act answers with its card.** A rain from a reply (`Bell.rainedCard`) and a submission (`Anthology.submittedCard`) offer the card as the write leaves it; the direct `rain` and `submit` answer only their count.
- **Link doors.** A Directory door whose `to` is nobody (genesis's STUDIO) answers its word with `<label>\n<description>` and is skipped when field lines and the model look for forms.
- **Env.** `Env.receive` from anyone but the owner is taken in as a `mention` event (`Event.handle`); the law admits that receive (kind 0, method receive, owner/handle/seen/subscribers unchanged). Arrival seeds `handle`; the card reads "ENV of <handle>" with the newest eight events, one line each (first line, 100 characters). An Env lives at `Events.envOf(did)` = `env/<did>`; one elsewhere refuses publish. Its buffer holds 256 (the host drops the oldest).
- **Workshop.** Views its target (state type `Data`) and says "Was: bell-1 v1 / Now: bell-1 v2". A `propose` the target's law refuses is held as `{n, target, package, migration, proposer, proposerHandle}` (sixteen; a seventeenth drops the oldest); `adopt / n` runs the reprogram under the adopter, so the target's law admits only its owner; `withdraw / n` is the proposer's. Compile, program, packageBytes and migration refusals are not held.
- **Scoped resolution (Avatar).** An Avatar's own principal's prose with no spell names its object by the first word that is a thing lying in its place (by its card's first line, then its id's last segment), else an object of that id (the doors: garden, rooms, play); the avatar sends `receive {text: "delvetalk <id> <action>\n<field>: <rest>", post}`, which the host reads as a spell (5.63). Two of a name are answered "Which one: …?"; `look` offers the place's card (`world.card`).
- **Place.** Its State, Exit and Done are `Places.obend`'s; it declares `law owner` (only the owner renames, redescribes, reprograms; anyone's kind-0 write keeps owner, name, description, exits). `say {line}`, `emote {line}`, `whisper {to, line}` offer the line under the speaker's name to every avatar present (in key order, at most 32); someone not present is refused `notPresent` by name. Each enter, leave, take and put is traced, admitted or refused, as `Rows.Trace`, 64 kept by the host (the card shows the newest eight).
- **Thing.** `copyable` (default true; owner's lens). The Workshop's `create / like: <thing>` sends `copy`; the thing creates a Thing from its own package with its state minus holder, offer and owner (the host fills owner with the creating principal). Not copyable is refused by name.
- **Doors on any card.** `Card.Doorway {label, to}`, `doors: Card.Doorways`, `Card.doorForm()`/`undoorForm()`, `Card.dooring` (owner's; eight at most; `doorTaken`, `doorsFull`), `Card.doorLines`. Bell has them; Garden plants each bell with `garden: <garden>`.
- **Wake.** Subscribes with typed receivers: `On.writes {object, field, above}` to a scalar (`changedNat`), `On.rows` to a relation (one receiver per `Rows` type; `Rows.*Columns` projections for its patterns: `equals`, `above`, `below`, `contains`), and its env's `buffer` (`changedSensed`). Receivers are helpers and check `context.caller`.
- **Deal.** `amendment {object, law}` (object "" for none). The countersignature that brings the deal to rest performs `amend` with the deal as caller, judged by the object's own law; a refusal is answered `amendRefused`, the signature standing.
- **Hub.** Directory passes a spell naming another card to its receive by call, greets each principal once, is silent to its owner, answers a door word with that door's card. Garden ends with no offer for prose the model calls `not addressed`. Tide answers subscribe and tick with its card.
- **Pages.** The host publishes a default page (`## Card`, `## How to reply`) for `publishPage {page}` to a card that declares none (5.68); Garden keeps its own (`page`, `Card.defaultPage`, `Card.pageText`).
- **Merge.** An object with a page keeps `owner` and `pageCheckpoint`; `Card.isMerge` reads the owner's `merge` reply (Garden).
- **Anthology.** Owner admits. The owner's handle is seeded as `ownerHandle` and stored at each admission.
- **Laws that guard fields** read `owner: request.subject == new.owner or (request.kind == 0 and unchanged(…))`; without the kind, anyone's reprogram or amendment (which change no field) passes. The host prints a law fully parenthesised. `world-amend` takes `law NAME: EXPR`. `law(old, new, request)` Bend predicates run after the text admits a kind-0 write and may give a reading (`Abi.Verdict.refused {clause, reading}`, 5.67): Thing (custody), Tide (self, tooSoon), Wake (owner); Scene's cooldown is a Bend law over `context.clock`. Insert-only relations are law text: Deal `law signed: insertOnly(signatures)`, Directory `law greeted: request.subject == new.owner or insertOnly(greeted)` (with a limit, insertOnly refuses an insert that drops a row, so the Directory stops greeting at 4,096 in Bend).
- **List edits by item.** The index forms are gone from Plan.obend (objects6): `amendItem {item, change}` and `removeItem {item}` address the first item with the same canonical bytes (`absentItem` when none); find the stored item with `Lists.find`.
- **Composition.** An activity composes only in tail position; a reusable method takes `then: Result -> T`. No `else match`: put the match in its own def. Payloads are Data: give the value where Data is expected; `Plans.nothing()` is the empty payload.
- **Idioms.** No `::<…>` (type arguments are inferred; a definition whose parameter appears in no argument needs a smaller signature). Self-write `write {field: add n | set v | append x | removeItem x | insert r | upsert r | retract k, …}` (the kernel's `remove i` lowers to a constructor Plan.obend no longer has) (amendItem, keep-only and computed Entries stay `Plan.write(...)`); bind a write's answer with `let written(_) = perform(…)`. Forms are `form ACTION [as NAME]:` blocks. Strings are interpolated (`"{expr}"`; an `if` inside a string is a `let` first). Every law has a reading: `law owner "only …": …`.
- **Refusals are sums.** `Card.Refusal {clause, reading}`; a card shows `refused <clause>: <reading>` or `Not done: <reading>`. One `refusal(w) -> Card.Refusal` match per object: Thing, Place, Avatar (WORLD-REVIEW 6 for the rest: Garden, Tide, Wake, Deal, Policy still pair `why`/`clause`). `{reason}` payloads remain in Directory's `Heard.refused`, Seat and Table `Done`, Env `Done`, Appointment, Workshop's `Verdict`.
- **Mailbox.** An Avatar's `send` inserts a `Rows.Letter {handle, text, at, n}` into its `outbox` (keyed {at, n}, 64); `subscribe {to}` is the host subscription to another avatar's outbox, delivered to `mailed`; `watch {to, field}` follows any field (a bell's `rung`), delivered to `news` ("news from <object>"); `unsubscribe {to}` ends either. It follows at most 32; the host serves at most 32 subscribers a turn (`unserved`) and 64 an object. Its inbox is a relation keyed {at, from, n}, 64 kept. There are no observers anywhere.
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
  pattern names and a `Rows.Column` carries.
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
  eight). Avatar `inbox` {at, from, n} and `outbox` {at, n}, 64 each. Still lists: doors on every card. Records by design: RELATIONAL §9 "Stays a
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
  Directory's greeted and Deal's signatures are `insertOnly` in the law text (objects9;
  `Relations.insertedOnly` is gone).
* **Seeds on the wire.** A relation seed is the `rows` variant (`tests.test_turn_world.relation(*rows)`,
  rows in key order); `deploy/genesis.py` seeds the directory's doors that way with places.
* **Against the host** (host7, foundation 613639d). The edits, canonical order, keys and
  limits are the host's now; inserts do not yet commute (relations day 2), so a turn whose
  root another write moved re-runs: two prose replies of one speaker to the garden (each
  upserts that speaker's pending row) cost a second interpretation of the later one
  (`test_policy ...checkpoint_blocks_once`). Two host behaviours to know: (1) a package
  any of whose modules declares `relations()` has the ENTRY module's `relations()`
  compiled, so a package importing a module that declares relations or an object made from
  such a chain (a Cistern dug from Garden's) must declare its own, else creation fails
  "missing selected entry"; (2) that compile
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

### Wholeness migration: done (lane/objects9)

Every object speaks the message dialect (objects8: Scene, Workshop, Directory, Bell, Env, Wake,
Garden, Policy; objects9: Thing ad9d3b8, Avatar 818ff46, Place d822edc). The deletion pass
removed Card's Plan-dialect helpers (`Heard`, `Routed`, route/routeHeard/withBare/bareSpell,
answerLensed*, tellPlan, answerPlan/answerAsPlan, forwarding/forwarded/sending/offering, merge,
checkpointed, fitting, asking, unfit, escalation, onlyFields, completed, spellText, `text`,
`natural`, valueNatural), the observer convention (Observer, observing, broadcast, notified,
Change, Column/Row, notifyRows), `Form.Lens`, Spell.obend's parser (fit, judge, bare, blocks,
field lines; the host's `spell-parse` is the grammar, tests/test_spell.py and
tests/test_host_spell.py test it against fixtures recorded from the Bend parser, which agreed on
every row), `Relations.insertedOnly`, and Plan.obend's `Plan`/`Response`/`Handled` sums with their
payload records (now `tests/fixtures/obend/Variant.obend`). `Card.mentions` moved into the
Directory, its one user. `Replied` stays: it is what every `receive` and `Card.answer` return.

**Remaining.**
1. `Form.Kind` gains `source: {}` (host 5.69 reads it as text of 1 to 16,384) and the Workshop
   declares `check {target, source}` / `propose {target, migration, source}` forms of that kind
   (then `withFence` and the Workshop's own fence reading go; tests/test_form_bounds.py shows it
   with a fixture). Card.hint, Card.valueText and Policy.kindText each need the case.
2. Host: a spell's method cannot see the reply's post (Garden plants with `context.intent`;
   `Abi.Context.inputOrigin.post`); two expectedFailures (test_principal, test_replay) wait.
3. Transport: hostproc.py's ARRIVAL need not copy Place (the Avatar imports only world/lib);
   bridge.py must send mentions to Env's `mention`; http.py's spell template for a choice field
   (test_hypermedia x2) and the play page's `?` usage (test_http) are expectedFailure.
4. Host/kernel day 4: delete the variant arms and the three-argument Activity, and with them
   Variant.obend and the fixtures that use it.
5. WORLD-REVIEW 4 to 6, 12 (Door knocks, Cistern entries), 14, 22 to 25 are untouched.
## 2. Limits found

- An await only proves that some turn with that identity was admitted. A turn suspended on an object resumes refused `staleRoot` if anything wrote that object meanwhile, unless its writes are all keep/add/append (they commute).
- `run` refuses variant arguments and recursive results: build in a probe module.
- A kernel hint can mislead: an unbalanced parenthesis is reported with "there is no Maybe builtin" or "definitions are `def name(x: T) -> U:`".
- `transport/http.py` `MAX_BODY` (64 KiB) answers 413 for a larger body.

## 3. Directory of objects

Counter, Garden, Bell, Cistern, Anthology (owner admits), Directory (owner adds and removes), Door, Lantern, Loop, Place, Thing, Avatar (mailbox: subscribe, send, unsubscribe; handle lens), Policy (owner law with `request.method`; lenses), Workshop (check prints the checker's hint under its problem; inspect; propose), Env, Wake, Tide, Appointments/Appointment, Deal, Seat and Table, Scene (passages and choices as data; enter, choose, leave), Commons (places, paths, ways in, gates: open, members, object).

## 4. Open

- An addressee `slot` reaches receive but no object reads it (`Heard` is `{text, post}`).
- A Scene passage is not editable once made; spween `tags`, custom fields, floats and negative numbers are skipped or compared as text; a scene near the 16 x 8 limit has not been measured.
- A kernel word-set builtin would remove the per-word loop cost of `Card.mentions`.
- Garden's `plant {colour}` should be `Bell.Colour` (a sum of empty cases), so the method table offers a `choice`. Tried (objects6) and held back: a model's JSON proposal and an HTTP form POST both send the colour as text, and the host does not take a label for an empty-payload case, so the JSON proposals of `test_policy` answer `unclear`. Needs the host to fit a label to the case of that name where the input type is such a sum (`interpretVerdict`'s `jsonData` path and world-turn arguments); then the Garden change is one line plus the tests' four `plant` calls.
