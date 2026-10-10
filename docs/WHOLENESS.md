# The world from within itself

Read against `foundation` 5eac2a6 (RELATIONAL §11 holds the scale decisions). Landed by 189b534 with the root decisions at the end, and per-row roots (§3a) still after launch: FOUNDATION §3, §4 and §6 say what was built. FOUNDATION section numbers cited here are those of the tree read against; today the principles are §8, the gate §11. Line numbers are that tree's. Three changes land as one before launch, beside the relational slice (RELATIONAL §9); each deletes a closed sum or a convention. The lineage is LambdaMOO's `#0` and Smalltalk's VM-as-object; Faré's rule: "I/O effects are system calls into an outside program, the controller", and the fixed top of a tower "limits the access rights of all implementations" (Faré's FAREOO.md (outside this tree, at ~/dev/fareoo) §8, `fci` §5.1-5.2). The controller is an object named `world`; its interface is the fixed top; the host is the implementation below.

## 1. The world as an object

**The message.** The kernel's Plan type is one record and its Response type is `Data`:

```
record Message:            # world/lib/World.obend
  object: Plans.Reference
  method: String
  argument: Data
```

`Plan.obend`'s `sum Plan<E>` (Plan.obend:125-154) and `sum Response<S, R>` (155-182) are deleted, with the payload records `View`, `Await`, `Interpret`, `Offering`, `Grant`, `Publish` (84-124). Kept in `Plan.obend` as library types: `Reference`, `Edit<T, D>`, `Entries<D, U>` (with RELATIONAL §3's `insert`/`upsert`/`retract`), `Slot`, `Outcome`, `Receipt`, `Handled<R>`, `nothing()`, `self()`, `nobody()`, `same()`, `isNobody()`, `indexOf()`. `Form.obend` is unchanged.

**The world's interface** is `world/lib/World.obend`, a `protocol` declaration (a new declaration form, parsed as `form` blocks are, ObjectiveBendParse.lean:871, 1020; one signature per line) plus the result sums it names. The world's reference is `{world: "", object: "world"}`; the id `world` is reserved at creation (`validObjectId`, Ops.lean:50 refuses it).

```
protocol world:
  view<S>({object: Reference}) -> Viewed<S>
  viewField<S>({object: Reference, field: String}) -> Viewed<S>
  write<E>(E) -> Written
  judge<E>(E) -> Judged
  call<R>({object: Reference, method: String, argument: Data}) -> Returned<R>
  callVia<R>({object: Reference, method: String, argument: Data, via: String}) -> Returned<R>
  run<R>({object: Reference, method: String, argument: Data, handler: Reference}) -> Returned<R>
  spell<R>({text: String}) -> Returned<R>
  send({object: Reference, method: String, argument: Data}) -> Sent
  sendVia({object: Reference, method: String, argument: Data, via: String}) -> Sent
  create({package: String, seed: Data, law: String, requireAbsent: Reference}) -> Created
  createUnder({package: String, seed: Data, law: String, requireAbsent: Reference, supervisor: Reference}) -> Created
  await({slot: Slot, patience: Nat}) -> Awaited
  awaitUntil({slot: Slot, until: Nat}) -> Awaited
  awaitPost({post: String, patience: Nat}) -> Awaited
  awaitPostUntil({post: String, until: Nat}) -> Awaited
  interpret<R>({utterance: String, offers: Forms, policy: Reference, model: String}) -> Interpreted<R>
  offer({to: String, document: Document}) -> Offered
  publish({page: String, section: String, body: String}) -> Published
  reprogram({object: Reference, package: String, migration: String}) -> Programmed
  extend({object: Reference, package: String, migration: String}) -> Programmed
  amend({object: Reference, law: String}) -> Amended
  inspect({object: Reference}) -> Inspected
  check({package: String}) -> Checked
  grant({to: String, object: Reference, method: String, until: Nat}) -> Granted
  grantWith({to: String, object: Reference, method: String, until: Nat, fixed: Data, uses: Nat}) -> Granted
  revoke({id: String}) -> Revoked
  objects({prefix: String, after: String}) -> Listed
  card({object: Reference}) -> Carded
  subscribe({object: Reference, field: String}) -> Subscribed
  unsubscribe({object: Reference, field: String}) -> Subscribed
```

Result sums, each closed, in World.obend, with `refused {clause: String}` on every one that `answer` refuses today and `denied {}` on every read: `Viewed<S>: viewed {version: Nat, state: S}`; `Written: written {}`; `Judged: judged {admitted: Bool, clause: String}`; `Returned<R>: returned {result: R}`; `Sent: delivery {id: String}`; `Created: created {object: Reference}`; `Awaited: reply {receipt: Receipt} | unknown {} | timedOut {} | broken {}`; `Interpreted<R>: proposal {method: String, argument: R} | unclear {needs: Names} | replied {text: String} | timedOut {}`; `Offered: offered {}`; `Published: published {post: String}`; `Programmed: reprogrammed {pin: String}`; `Amended: amended {}`; `Inspected: inspected {pin, law, source: String, methods: Forms}`; `Checked: checked {diagnostics: Names}`; `Granted: granted {id: String}`; `Revoked: revoked {}`; `Listed: listed {ids: Names, more: Bool}`; `Carded: carded {document: Document}`; `Subscribed: subscribed {}`. Clauses are the strings `answer` uses (TurnLoop.lean:709-1010).

Deleted as facilities: `viewData` and `viewDataField`; `Data` is universal, so `world.view::<Data>` and `world.viewField::<Data>` are them (Workshop uses the first). `viewField` is RELATIONAL §6's, answered when the target's field type canonically equals `S` or `S` is `Data`. `viewAt` and `viewDerived` (FOUNDATION §9) enter World.obend the day the host answers them: a protocol line is a promise the host keeps. `spell` is the one new facility: the host parses `text` (§2), resolves its card, fits and runs the method as `call` does; Garden and the Directory use it for macro expansions (Card.obend:493-498), spell text by the owner's hand.

**Elaboration.** `world` is reserved as `perform` is (`isPerform`, ObjectiveBendElaborate.lean:755). `world.X::<T>(arg)`, or `world.X(arg)` when `T` is absent or inferable from `arg` (`inferArguments`, Generics.lean; `write<E>` and `judge<E>` infer `E`), lowers to

```
perform({object: {world: "", object: "world"}, method: "X", argument: Data.of::<Input>(arg)})
```

typed `Activity<Result[T]>`, `arg` checked against the instantiated input (a `Data` field injects as today, `coerceAt`). Surface `perform(...)` is withdrawn: the only yields are world calls. `let viewed(v) = world.view::<Policies.State>({object: state.policy})` keeps the `let label(x) =` sugar (KERNEL-HANDOFF §8), whose scrutinee rule becomes "a world call". `write {f: op v}` lowers to `world.write(extend(keep(), {...}))` (Parse.lean:529-554 drops the `object` field). `refuse` is unchanged.

**`Activity<A>`.** Surface `Activity<A>` is kernel `computation Message Data A`; the three-argument form goes on day 4. A per-activity `R` is the closed Response sum under another name, instantiated once for all an object's methods, which is why a Bell cannot read the Directory (RELATIONAL §6); the response type belongs to the call site, as a function's result does. Kernel changes:

- `Ty.computation plan response result` stays (ObjectiveBendTypes.lean:28-32); `Ty.isPlanUnder` (122-131) admits a record row of data beside a variant.
- `PartialTyping.perform` (ObjectiveBendTyping.lean:324-328) concludes `computation planType .data T` with premises `planType.isPlanUnder`, `T.isDataUnder`; the checker's perform case (628-637) already reads a per-site annotation `{domain, codomain}` and now takes `T` from it. `done`, `refuse`, `effectCase` (345-362) are unchanged in shape. The `decide` examples at 1545-1560 are restated.
- The elaborated `ATerm.perform (plan response : PTy)` (Elaborate.lean:336) already carries the site's types; `response` becomes the site's result.
- `Turn.conclude` (Turn.lean:310-331) reports the yield's `responseType` as the site's `T`, found as the annotation at the preorder index of the yielded `perform` (the index `Dictionary.ofProgram` assigns, CheckpointV2); `resumeActivity` (391-441) checks the response against the same site type, recomputed from the decoded state. No `Checkpoint` field changes.
- `Package.methodTable` (Package.lean:130-146) is unchanged in shape; `activity` is true for `Activity<A>`. The artifact gains `world: [method names]`, the world methods the entry's closure performs, so `inspect` can say what an object asks of the world.

**The host.** `answer` (TurnLoop.lean:709) matches `plan` as `.record [object, method, argument]`, requires `object` to be the world's reference (`refused {clause: notWorld}`: a Message to another object is a `call`), and dispatches on `method` as a string; the arms are today's, re-headed. `respond` (195) checks the payload against the site type the yield reported. `drive` (576-596) routes `await*` and `interpret` by name. `handleWith` (485): a handler's `handle(state, message: World.Message, context) -> Plans.Handled<Data>` sees one type for every callee. `write` stays self-only where it is (743-747, `notSelf`); `addWrite` (258) is unchanged. Read authority, grants, the ledger and `recordRoot` are untouched: who may call which world method is the authority model as built (HOST-HANDOFF 5.1-5.2); the world object has no state and no law, so nothing is judged on it.

**The objects.** Every `perform(Plan.…)` (156 sites in 25 files: 41 `write`, 15 `send`, 12 `call`, 11 `view`, 11 `inspect`, 6 `offer`, 6 `create`, 3 `await`, the rest under 3) becomes a world call; 36 `write {…}` sugar sites are unchanged in source; 439 `Activity<Plan, Response, X>` signatures become `Activity<X>`; `type Plan`/`type Response` lines go; `keep()` stays. Card.obend's `<E, S, R, T>` helpers (`tell`, Card.obend:315) become `<T>`.

**Theorems.** None move. `Message` and `Data` are first-order: `conformsUnder_iff`/`conformsFuel_sound` (ObjectiveBendDataConformance.lean) relate the same `conformsUnder` to the same `HasType` over unchanged `Data` and `Ty` constructors. `checkpoint_resume_segment`, `related_collect` and the collector lemmas (DemandCollectProofs.lean:356-640) are about machine states and `collect`, not types; `settle_resume_segment` likewise; the checkpoint round trips encode terms, and `Term.perform` (OpenRecursion.lean:28-40) is unchanged. Only the typing rule and the `decide` examples change; the "not proved" list (KERNEL-HANDOFF §1) neither grows nor shrinks.

**Tests.** `test_turn` (yield shapes), `test_handlers` (handler input type), `test_methods` (table), `test_view_data` (becomes `view::<Data>` cases), `test_sugar` (`write` lowering), `test_located`/`test_hints` (world-call refusals: unknown method, missing `::<T>`, argument shape). `tests/test_artifact_pins.py` re-records once.

**Pins.** Every world source changes, so every pin moves once, on day 4 together with the relational re-record (RELATIONAL §9). No deployed journal exists; genesis reseeds.

## 2. The host parses spells

**Where.** `world-turn {method: "receive", argument: {text, post}}` (Session.lean:231; transport/bridge.py:320 sends exactly this) enters `spellTurn` before `runTurnWith` (TurnLoop.lean:1246): `Host/Spell.lean`'s `parse` runs over `text`. The grammar is Spell.obend's, in Lean, rule for rule: the last unquoted `delvetalk <card> <action>` line (Spell.obend:74-81), ` / ` and comma fields on the line (128-131), `name: value` lines, `<<DELIM` blocks of 1-32 `[A-Z0-9_]` closed by the exact line (207-220), `#`, `>`, blank and bare fence lines skipped, info-string fences skipped whole (100-107), `---` ends fields, a card name `[a-z0-9:/.-]{1,160}`, actions and fields `[a-z0-9-]+` or `?`. `bare` (226-234) collects field lines when no spell line stands. `fit` (296-321) judges bindings against a form: `unknownField`, `duplicateField`, `badValue` (text bounds in scalars, naturals in plain digits within bounds, a choice among options); an action-named line fills the first open text field (`rebound`, 302-313); missing fields are `unclear {needs}`.

**Then.** The card resolves as `Card.names` does (Card.obend:84-87: the object's id, or `env`/`wake` for the speaker's own; `resolveCard`, Ops.lean:1434). A spell naming another object retargets the turn to it under the same principal, identity and `replyTo`: the Directory's `passOn` (Directory.obend:101-106) and Card's `otherCard` go, and a reply under any post reaches the card it names. The action is looked up in the target's `methodForms` (TurnLoop.lean:412-419); `set` and `?` are the protocol's. The host builds the typed argument (text to label, natural to natural, choice to the variant with an empty payload) and runs the method, `inputOrigin.kind = "spell"`, `command` the spell line. `receive {text, post, fields}` runs only when no spell line stands and no bare field line names an action or field of the target's forms (the `withBare` rule, Card.obend:76-87, now the host's); `?` the host answers itself with the usage card (`Card.usage`'s lines, 146-150, rendered in Lean). `Heard.fields: Spell.Bindings` carries the bare `name: value` lines the host found, so no object scans for them; `Card.mentions` reads it (Card.obend:231).

**Refused by name.** A spell that does not fit is a refused turn, class `badSpell` (added to `refusalClasses`, Ops.lean:329; binds the identity), `clause` one of `otherCard` (unknown or hidden card), `noAction`, `unknownField`, `duplicateField`, `badValue`, `unclosedBlock`, `unclear`; `reason` the located problem ("line 3: colour is one of: amber, violet, silver"); `hint` the action's template filled with the fields given. `publicRefusal` (Ops.lean:2390) carries `clause` and `hint`; `bridge.draft_text` drafts `hint` for an addressed reply (one line of transport). Completion is by resend: the hint is the whole spell with its blanks. Garden's `Pending` with non-empty `needs` (Garden.obend:15-18, 388-404) is deleted; a proposal waiting for yes (empty needs) stays, since that is policy.

**Interpretation.** The model's reply is text the host already judges (`interpretVerdict`, TurnLoop.lean:1750); it now fits a spell-text reply against the offered forms and answers `proposal {method, argument}` or `unclear {needs}`. `Card.fitting` and its helpers (Card.obend:436-457) and all of `Spell.fit` in Bend go. `Spell.obend` keeps `Binding`, `Bindings`, `Entry`, `Entries`, `Value` and nothing executable. `test_spell.py`'s 31 cases become fixtures (`tests/fixtures/spells/*.json`) run through a stateless op `spell-parse {text, form?}`; until day 3 both parsers answer them, then the Lean one alone.

**Card.obend loses** `route` through `natural` (Card.obend:54-135), `fitting` and helpers, `onlyFields`, `fieldLinesOnly`, `spellText`, `completed` (458-471), the `Routed` sum. **Keeps** `Reply`, `Refusal`, `answer`/`answerAs`/`offering`/`forwarded` for prose (hand on to the directory, 160-176), `usage`/`template`/`help`, `mentions`, and lenses: a lens is a form (`set` with one `<field>: <value>`); the host judges the value against the lens kind (`badValue`) and calls `set(state, {field, value}, context)`, which `answerLensed`'s `putting`/`judgedPut` (287-304) become.

**The Directory.** Grammar to the host, policy in Bend: the host decides what a reply *is*; the Directory decides what to do with prose: the door word (Directory.obend:109-122), the greeting, `mentions` over learned `words`/`fields`, the model, macros. Field-line routing to doors (129-152) stays in Bend reading `input.fields`, forwarding `receive {text, post, fields}` by `world.send` as today; the host parses the same text at the door. `knownFields()` (221) stays.

**Ticks saved.** `test_tariff` pins the 64-field spell parse at 79,583 ticks; OBJECTS-HANDOFF pins glm's 1,788-character reply under a bell under 20,000 and the directory's reading under 250,000. After this a spell costs its method alone (a Bell `rain` is of the bump turn's order, 56 + 10), prose costs `mentions`, and the parse costs no ticks. The 64-field row is deleted; `test_hub:361` re-pins the hand-on.

## 3. The host delivers changes

**Subscribe.** `world.subscribe({object, field})` records `{subscriber: self, principal: s.subject, object, field}`: the subscriber is the running object, the principal the frame's subject, who must be permitted to view the target (`ReadPolicy.permits`, Store.lean:155; else `refused {clause: denied}`). `field` names a top-level field of the target's state (else `refused {clause: field}`). `Limits.subscribersPerObject` 64 (`refused {clause: subscribers}` beyond); one subscription per (subscriber, object, field), repeats idempotent; `unsubscribe` by the subscriber or the principal's direct turn. Journaled in the admitted entry as `subscribes`/`unsubscribes [{subscriber, principal, object, field}]`, installed by `commit` (Ops.lean:1588), rebuilt by `record` (1459) into `World.subscriptions`; the snapshot body carries them.

**Changed.** After every admitted write `commit` enqueues, per subscription of `(object, field)` whose step touched `field` (an edit other than `keep`), a delivery `{to: subscriber, method: "changed", argument: {object: Reference, field, version, inserted: Data, retracted: Data}, principal, ledger}`: for a relation, the rows inserted and retracted (`upsert` is both); for a list, `append` inserts, `removeItem` retracts, `amendItem` both; for a scalar, one-item lists of the new and old value. Both are canonical lists (`listData`). The entry records `changes [{id, to, object, field, version, principal, ledger}]` beside `sends` (TurnLoop.lean:1072-1083); the argument is re-derived from `writes[].edits` on replay, never stored twice. Ids are `deliveryId principal intent ordinal` after the sends'. The ledger is the writing turn's decremented as a send's (`depth - 1, work - used, storage - added`), so a cascade dies at `maxDepth`, `chainWork` or `chainStorage` with `budgetExhausted` (Store.lean:44-48); `deliverOne` (TurnLoop.lean:1492-1530) runs them unchanged. Per write, sends and changes together obey `sendsPerTurn` 32: changes are served in subscription order and the entry names the rest under `unserved [subscriber]`; `version` is monotone, so a subscriber reading a version that is not last-seen-plus-one knows to `view`. `record` derives `pending` from `changes` as from `sends`; `checkSends` (Ops.lean:2064) gains the same check.

**Read authority** at delivery: `deliverOne` re-checks `permits principal` now; a subscription whose principal lost the right is consumed as a refused delivery `lawRefused denied` and dropped, as a fallen grant is (1511-1514). The `changed` turn runs under the subscription's principal, `caller` the changed object.

**What goes.** The observers convention (`Card.Observer` through `notified`, Card.obend:324-360); `notifyRows` is never written. Bell's `observers`, `observe`, `unobserve`, `observed` (Bell.obend:27, 39, 77-87) and `rang`'s broadcast (72-74): `rang` writes `rung` and ends. Door.obend's `observers` and broadcast (17-60): a Door subscribes to its bell's `rung` at creation and `changed` opens it; a Lantern subscribes to the door's `open`. Garden's observers and `notified` (Garden.obend:33, 418-437). Wake's `observed` send (Wake.obend:92-100) becomes `world.subscribe` in `added`; `written` (104-120) becomes `changed(state, input: World.Changed, context)`: `On.writes {object, field, above}` fires when a scalar's `inserted` value passes `above`; RELATIONAL §7's `On.rows` matches `inserted` rows by column equality. Env's `subscribers` and `publish`'s broadcast (Env.obend:20, 69, 84-94): the owner's Wake subscribes to `env/<did>.buffer`. Avatar's mailing list (Avatar.obend:21, 88-111): `send` inserts into an `outbox` relation (RELATIONAL §11 limit, `dropOldest`) and followers subscribe to it. Place traces are the Place's own writes (Place.obend:91-107) and stay; a Thing or Avatar that wants to know who entered subscribes to `present`. Doorways on cards (391-418) are links, unchanged. `tests/test_deliveries.py:128` (ring, door, lantern) becomes two subscriptions and one write.

## 3a. Rows as roots

This is what makes RELATIONAL §11's limits policy rather than necessity: an object whose rows are its roots is loaded by the rows a turn touches, not by its size.

**Recording.** Today a read records `{object, version}` (`recordRoot`, TurnLoop.lean:146) and a moved root is `staleRoot` unless every edit commutes (`judge`, Ops.lean:1318-1322). With relations the host records, per turn, which rows of which relations the turn read. The kernel lane is writing the feasibility note for lazy host-backed state cells, which would make "forced" exact; until it lands, the rule is syntactic and over-approximate: `lookup`, `where`, `group`, `order`, `joinOn` and `render` over a relation (RELATIONAL §4) read the rows they return, `count` and `exists` read the whole relation, and `view`/`viewField` of another object read every row of the fields they answer. `recordRoot` gains `recordRows (id field : String) (keys : List Data)`; the turn's roots become `{object, version}` for scalar fields and `{object, field, key}` per row read, both bounded by `maxRoots` 64 (a relation read whole past that bound falls back to the object-version root, named in the receipt as `{object, field, key: "*"}`).

**Judging.** `judge`'s root check becomes: for a row root, no admitted write since `seen` touched that key, read from the per-object index of height to keys touched (RELATIONAL §11, the index that makes `keysChangedSince` constant); for a scalar root, the object's version as today. The insert-commutes rule (`EditKind.commutes`, Ops.lean:101) becomes a special case: an insert of a fresh key touches no key anyone read, so it passes the row check without being named, and `commutesAt` (1267) is kept only for the scalar `add`/`append` forms. `rebasable` (1300) is subsumed for relations and kept for scalars. Two agents reading and retracting different rows of one relation commit against each other; two reading the same row and one retracting it leave the other `staleRoot` naming `{object, field, key}`.

**Receipt and replay.** `roots` in the entry lists both shapes; `rootsJson`/`parseRoots` (Ops.lean:226, 241) carry `{object, field, key}` beside `{object, version}`; `Binding.make`'s `rootsDigest` (checkpoint binding) hashes the list as written, so a suspension bound to row roots resumes under them. Replay re-derives the verdict exactly as today: `replayEntry` rebuilds the `Proposal` with the recorded roots and re-runs `judge` against the replayed index, which `record` maintains from `writes[].edits` per height; nothing new is stored. `world-receipt`'s public projection names a stale row root as it names an object root.

**Not changed.** Scalars keep the object version; laws keep `old`/`new` whole; `maxRoots` is the bound on rows read per turn, so a card over a 4,096-row relation renders eight rows and a count and records eight row roots plus one whole-relation root for the count. The limit is then a size the owner chose, not a wall the host needs.

## 4. Migration

Three wholeness lanes (kernel, host, objects) in disjoint files, concurrent with RELATIONAL §9's four days. The relational lane owns `Relation.obend`, `Plan.obend`'s `Entries`, `Ops.lean` edits/judge/canonical, `Law.lean`, `ObjectiveBendLaw.lean`, and the object files on its schedule (Bell day 1; Tide, Directory, Anthology, Deal day 2; Env, Place, Garden, Wake, Thing day 3). The rule that lets both proceed: additive first, deletion last. Until day 4 the kernel accepts both `Activity<P, R, A>` with a variant Plan and `Activity<A>` over `Message`, and `answer` dispatches on the plan's shape, so an object compiles in either dialect and neither migration of it waits on the other.

**Wire names, fixed here so no lane waits on another's file.** World id `"world"`, reference `{world: "", object: "world"}`. `World.Message {object, method, argument}`. Method names as the protocol above. Result sum labels as listed. Refusal class `badSpell`; clauses `otherCard, noAction, unknownField, duplicateField, badValue, unclosedBlock, unclear`; refusal fields `reason`, `hint`. `Heard {text, post, fields}`. Op `spell-parse {text, form?}` answering `{status: "parsed", spell | notASpell, fit?}`. Entry fields `subscribes`, `unsubscribes`, `changes`, `unserved`. Delivery method `changed`, payload `{object, field, version, inserted, retracted}`. `Limits.subscribersPerObject = 64`. Artifact field `world: [names]`. `inputOrigin.kind = "spell"`.

**Day 1.** Kernel: `protocol` parse, `world` reserved, world-call elaboration with site types, `Activity<A>`, `isPlanUnder` record case, the `perform` rule and checker case, `write` relowered; `test_sugar`, `test_located` (Parse, Elaborate, Types, Typing, Generics). Host: `Host/Spell.lean`, `spell-parse`, `tests/test_host_spell.py` over `test_spell.py`'s cases as fixtures against both parsers (new files). Objects: `World.obend`; `Card.obend` rewritten to `<T>` helpers without `route`.

**Day 2.** Kernel: `Turn.conclude`/`resumeActivity` site type, artifact `world`, `test_turn` (Turn.lean, Package.lean). Host: `answer` by method name beside the variant arms, `handleWith` on `Message`, `spellTurn` on `receive` (parse, retarget, fit, run, `badSpell`, `?`, `Heard.fields`; TurnLoop.lean, Ops.lean, Session.lean), `tests/test_spell_turns.py`. Objects: those the relational lane never touches (Counter, Lantern, Door, Loop, Cistern, Seat, Table, Scene, Policy, Workshop, Avatar, Appointment, Appointments, Commons); Door and Lantern on `subscribe`.

**Day 3.** Host: `subscribe`/`unsubscribe`, `changes` in `commit`/`record`/`deliverOne`/`checkChanges`, snapshot field, `Limits`; `tests/test_changes.py` (bounds, authority, ledger, replay, `unserved`); rows as roots (§3a) in `judge`/`recordRoot`. Objects: Bell, Tide, Directory, Anthology, Deal; Wake `changed`; Spell.obend's parser deleted once the fixtures pass on Lean alone. Transport: `draft_text` reads `hint` (bridge.py:82).

**Day 4.** Objects: Env, Place, Garden, Thing; Plan.obend's sums and Card's observers deleted. Kernel: the three-argument `Activity` and the variant Plan refused by name. Host: the variant arms of `answer` deleted. Root: full `lake build`, pins re-recorded once with the relational re-record, `make check`, rehearsal run 10; FOUNDATION §3 becomes the protocol table, §5 names the host as the parser, §8's "claims and wishes" row names `subscribe`.

**Day 5.** Rehearsal findings; nothing new lands.

## 5. What this does not buy, and the risks

**The new closed thing.** The world's method table is closed in `World.obend` and `answer`. A facility after this is an arm in `answer`, a protocol line, a result sum, a test; only the objects that use it name it, and `inspect` shows which do. No object changes for a facility it does not use; `Plan.obend` never changes again. Not bought: objects cannot add world methods; the world is not programmable from within (Faré's "no fixed bottom", `fci` §5.3, stops at the kernel), and a world object with state and a law is refused here.

**Law on the world object.** None; authority is the model as built. `create` is anyone's, as today (the child's law and `requiredAbsence` decide, HOST-HANDOFF §4); `world-create {owner}` stays the opener's op. `subscribe` needs read authority and a free slot. `grant` stays a direct turn's (TurnLoop.lean:961). The clock principal keeps `world-advance` and `world-posted` as ops: time is an input, not a method.

**Budget.** Host-side parsing costs no ticks; it is bounded by the text's bytes (the HTTP body cap of 64 KiB, OBJECTS-HANDOFF §2), one pass per line, and the forms' sizes. An adversarial 64 KiB reply costs a linear scan and a refused entry, as today.

**The grammar frozen in Lean.** Grammar changes are the host lane's, each with a fixture; `spell-parse` is the oracle objects and transport test against, and there is no second parser to drift. A town convention (a new separator) is a host release, not a reprogram: a grammar every card shares is no card's policy.

**Decided losses.** Completion is by resend: "I still need: colour" is answered by the whole spell again, which the hint supplies filled in. If run 10's archived field-only completions fail, the held spell returns to Garden as policy, in Bend, reading `Heard.fields`. The per-site response type is the one kernel change with substance; its failure mode is a `perform` site the dictionary cannot name, and rank-1 specialization makes every instance its own site. `::<T>` appears in `world/` for the first time (`view`, `call` when the result is read, `interpret`).

**Receipts and the gate.** The receipt's shape is unchanged: identity, roots, writes or refusal class, budget, height; `badSpell` is one more class with `clause`, `reason`, `hint`; `changes` and `subscribes` are entry fields as `sends` and `grants` are. The gate's six items (FOUNDATION §11) and `rehearsal/run.sh` are unchanged and are the acceptance.

**The unit of load is the object** (RELATIONAL §11): a turn materialises the whole state, and `changed` makes every popular object a sender. Three mitigations land with the relational slice: every relation declares `limit` with `dropOldest` retention enforced by `Relation.canonical` (default 4,096 rows); the host trusts its own stored state and runs `conformsUnder` only on arguments from outside; an unbounded collection is a sequence of child objects (`anthology/page/n`), never one relation. Subscribers per object 64 and `changed` under the per-turn send bound are the wholeness half of the same decision. Lazy state cells, so a count never materialises its rows, are after launch.

## Root decisions on this contract (2026-10-10)

Adopted as written, with one override: spell completion stays by bare field
lines, not by resend. The host fills `Heard.fields` from `name: value` lines
and refuses nothing; the Garden (and the Card default) keeps its pending
proposal per speaker and completes it from those fields, since that is policy
and belongs in Bend. The yes-waiting pending stays too. The relational slice
(RELATIONAL.md) lands first in each lane; the kernel accepts both `Activity`
dialects and the host dispatches on plan shape until the last object is
rewritten, so no object's rewrite waits on another's.

## Root decisions for the object migration (2026-10-10, second set)

1. The Directory's `door()` blurb accessor is renamed `blurb()`; `door {label,
   to}` is the action the host runs for the spell `door`.
2. Lens `set` and the fitting of model replies land in the host first; the
   lens objects (Policy, Avatar, Place, Thing, Garden) and the two
   interpreting objects (Garden, Directory) migrate last, after that.
3. A subscriber names a typed receiver at `subscribe {object, field, method}`;
   the host delivers `changed` to that method with `inserted` and `retracted`
   checked against the method's declared row type, as `call` payloads are
   checked. Shared row types (`Rain`, `Sensed`, `Greeting`, `Proposal`,
   `Trace`, `Subscription`) live in `world/lib/Rows.obend` so a Wake can import
   them.
4. The message-dialect `receive` takes `Reply {text, post, fields}`; `Heard`
   stays for unmigrated cards until the last one moves.
5. `spell` is not in the World protocol until the host answers it; the host's
   spell path runs methods directly, which is the facility the contract wanted.
