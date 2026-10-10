# Host handoff

State on 2026-10-09 (foundation f178383).

## Summary

The host is one Lean process holding a world of durable objects. Every state change is a hash-chained journal entry (CID of canonical DAG-CBOR); memory is derived from the journal by `record`, and replay re-judges admitted entries. A reply exists only after its bytes are durable.

- Files: `spec/Delvetalk/Host/` `Store` (data, `Limits`), `Journal` (hash, chain), `Law` (law evaluator), `Ops` (pure kernel: judge, commit, record, replay, reads), `TurnLoop` (turns, activities, sends, suspension), `Snapshot` (CBOR snapshots, fork genesis), `Session` (journal IO, ops dispatch), `Slug`. `PackageSession.lean` imports Session; `spec/PackageMain.lean` is the JSON-lines driver.
- Write is self-only. Cross-object change is `call`/`send`; the callee's own law judges it. `reprogram` and `amend` of another object are judged by the target's law.
- An object's pin is the CID of its sealed source closure, never a compiler output.
- Laws: a text law (`law NAME "reading": EXPR`) judges every change; an optional Bend `law(old, new, request)` runs after it for kind-0 writes.
- Refusals are receipts with a class; `staleRoot`, `budget`, `evaluation`, `capacity` are transient (a retry with the same identity runs again).
- Ops in section 2. Limits in section 4 (`Store.lean`, namespace `Limits`).
- Run: `make check` (parallel runner `tests/run.py`), `make smoke` (`test_turn_world test_chain`). Narrow: `DELVETALK_OBEND=<binary> python3 -W ignore -m tests.run test_x`. `tests/host.py` opens test journals with `sync: "none"`.
- Tests: 896 `def test_` across `tests/test_*.py` on 2026-10-09.
- Wall-clock bounds (`test_turn_world.Maximum` 200 bumps under 5 s, `test_http` 200 turns under 10 s, `test_snapshot` reopen under 1 s) are fsync- and load-bound and can miss on a loaded box.
- Open: section 7 (forms for sum inputs, nested handlers, foreign worlds, one stale `expectedFailure` in `tests/test_bridge.py`).

## 1. Module map

Import order: Store, Journal, Law, Slug, Ops, TurnLoop, Snapshot, Session. Snapshot imports Ops only.

- `Store.lean`: `Limits`, `Law`, `Compiled`, `Ledger`, `ReadPolicy`, `Program`, `Object`, `World`, `identityKey` (compressed `[principal, intent]`). Pure data.
- `Journal.lean`: `bodyHash` (CID of the body's canonical bytes), `sealEntry`, `verify height previous entry`.
- `Law.lean`: `Facts`, `Reading`, `denote`, `admits`, `refusedBy`; `#guard` tests at the bottom. Syntax is `spec/bend/Compiler/ObjectiveBendLaw.lean`.
- `Ops.lean`: edits, `Proposal`, `judge`, `commit`, `record`, `push`, creation (`compileObject`, `makeObject`, `buildObject`), `replayEntry`, `replay`, `advance`, reads.
- `TurnLoop.lean`: `M` monad (`ExceptT Abort (StateM TurnState)`), `runMethod`, `drive`, `answer`, `finishTurn`, `runTurnWith`, `resumeOne`, `settle`, `deliver`, `reprogramOp`, `amendOp`.
- `Snapshot.lean`: snapshot bytes, `openContent`, fork genesis. It does IO (snapshot files).
- `Session.lean`: `Open {world, path, handle, report, sync, snapshotAt}`, `openWorld`, `durable`, `stepWorld`, `syncHandle` (extern, `spec/native/sync.c`).

Durability is fsync, not a full barrier: an entry may be lost on power loss inside the OS write-back window. The chain verifies on reopen, so a torn tail is cut, never corrupted. `world-open {sync: "none" | "fsync" | "full"}` picks the mode per process (default `fsync`; `full` = F_FULLFSYNC; a boolean is still accepted: false = none, true = fsync). Never journaled; `world-status` reports `sync`. `openWorld` takes an exclusive flock and refuses "journal is open in another process".

Signatures a newcomer calls (pure unless noted):

```lean
def commit (w : World) (p : Proposal) (extra : List (String x Json) := [])
    (forced : Option Refusal := none)
    (onAdmit : List (String x Object) -> List (String x Json) := fun _ => []) : World x Json
def judge (w : World) (height : Nat) (p : Proposal) : Except Refusal Judged
def record (w : World) (entry : Json) (key : String) (touch : List String) : World
def replay (content : String) : Except String World
def runTurnWith (w : World) (req : TurnRequest) (how : TurnMeta) : Except String (World x Json)
def resumeOne (w : World) (sus : Json) (kind : Resume) : Except String (World x Json)
def settle (w : World) : Except String (World x Array Json)
def deliver (w : World) (limit : Nat) : Except String (World x Json)
def durable (s : Open) (step : World -> Except String (World x Json)) : IO (Session x Except String Json)
```

## 2. Ops

All ops are cases of `Session.stepWorld`. A request error (`Except.error`) journals nothing; a refusal is a receipt.

- Open and status: `world-open {path, library?, principal?, libraryLaw?, sync?, verify?, clock?, postQuota?, opener?}`, `world-status`, `world-snapshot`.
- Turns: `world-create`, `world-turn` (`replyTo?`, `profile?`), `world-propose`, `world-deliver {limit}`, `world-pending`, `world-reprogram {mode: replace | extend}`, `world-amend`, `world-advance {height}`, `world-revoke`, `world-interpretations`, `world-interpretation {id, reply}`.
- Reads: `world-view`, `world-receipt`, `world-history`, `world-offers`, `world-objects`, `world-card`, `world-inspect`, `world-check`, `world-state-cid`, `world-resolve`, `world-entry`, `world-entries`, `world-object`, `world-source`, `world-sources`, `world-grants`, `world-publications`, `world-addressee`.
- Registry and arrival: `world-principal`, `world-arrive`, `world-posted`, `world-library`, `world-fork`. `library-load {path}` is a stateless op.

Rules:
- `turn` is host-assigned on propose, amend and reprogram; a client-sent `turn` is a request error.
- Every journaling op runs through `durable`: step, `settleAll` (resume what the step released, run pending deliveries oldest first, each followed by a resume pass, up to `deliveriesPerSettle`), then append all new entries with one fsync. The reply carries `resumed` and `delivered`. `world-deliver` runs what a capped pass left. `world-open` never settles.
- `world-open` seals `library` (a directory) on first open and journals it; a later open whose bytes differ is refused by name. `verify: true` replays everything and answers `snapshot {resumed, refused [{height, reason}]}`.
- `clock` (the one principal that may `world-advance` and `world-posted`) and `postQuota` (hourly post cap, default 16) are journaled in a `settings` entry on first naming; a later open with other values is refused. `opener` goes in the same entry; the opener alone may `world-create {…, owner}`.
- Reads take a principal through `readerOf`: 1..128 bytes, or `anonymous` / "" (public objects only). Object ids at creation are 1..128 bytes of letters, digits and `. _ : / -` (`validObjectId`); replay accepts any id a journal holds.
- Optional request fields go through `optText`/`optNat`, which refuse a present but malformed value by name. `world-deliver.limit` is 1..16; `world-history` `after`/`limit` 1..100.
- `world-posted {principal, uri, cid, object, slot?, page?, section?}` (`uri` an `at://` post or a `zulip://<stream>/<topic>/<id>` message, `postSchemes`) journals a `posted` entry (identity `posted:<uri>`) and indexes `world.posts`. `world-addressee {parent}` answers `{status: "addressee", object, slot?, page?, section?}` or `{status: "unknown"}`.
- `world-principal {principal, did, handle}` (clock principal only) journals a `principal` entry for the handle registry; "" forgets a handle.

## 3. Journal

One JSON object per line. Common fields: `height`, `previous`, `hash`, `identity {principal, intent}`, `roots [{object, version}]`, `turn`, `request` (digest), `outcome {tag, …}`. `hash` is the CID of the canonical DAG-CBOR of the entry without `hash` (`tests/wire.py` is an independent Python encoder). Genesis `previous` is 64 zeros (`Limits.genesis`). A forked world's height-1 `previous` is the forked entry's CID (section 5.12).

`world.receipts` maps `identityKey` to the entry index (first wins, except that a suspension or a transient refusal is replaced by the identity's next entry). Transient refusals (`transientClasses`) are journaled but do not bind; admitted outcomes and every other refusal bind.

A state is named once, by the entry that wrote it: `writes[].cid`, or a created seed. `world-state-cid` answers it to a reader who may view the object.

Sources are carried once per journal: compile inputs name each module `{name, cid}`; the first entry needing a source carries it in top-level `sources [{cid, source}]` (checked against its CID on replay). Compiled packages are cached by input digest (`world.builds`, `buildKey`, `maxBuilds`), so creation and replay compile each distinct package once. Reprogram `source` fields are verbatim.

Optional top-level fields (all inside the hash): `absent [id]`, `turnRequest`, `ticksUsed`, `ledger {depth, work, storage}`, `result`, `sends [{id, to, method, argument, ledger}]`, `delivery {id, from}`, `resumes` (hash of the suspension it continues), `offers [{to, text}]`, `replyTo`, `rerun`, `ended`, `publishes`, `blocks`.

Outcomes:

- `created`: `{object, pin, sourcesSha256, compile, seed, read, chain, supervisor?, owner?}`; `roots []`, `turn 0`. Replay recompiles, requires the pin to match the source closure, the seed to conform and the amendment dry run to pass at the entry's height.
- `admitted`: `{writes [{object, version, edits, callers, kinds, cid?}], reprograms?, amendments?, creates?, grants?, revokes?, spent?}`. `kinds`: 0 write, 1 reprogram, 2 amend. Also per change, only when non-empty: `methods`, `vias`, `arguments`. Replay rebuilds the `Proposal`, checks `request == p.digest`, re-runs `judge`, and requires the recorded reprograms, amendments, creates and write versions to equal the replayed ones.
- `refused`: `{class, clause?, object?, reason?, expected?, root?}`. Classes (`refusalClasses`): staleRoot, typeMismatch, capacity, outOfRange, absentItem, lawRefused, unknownObject, duplicateIdentity (never journaled), evaluation, budget (reason = machine resource: ticks, heap, stack, nodes, bytes, or `law ticks`), budgetExhausted (reason = ledger field), programRefused (clause packageBytes, compile, stateType, migration, `law syntax`), requiredAbsence. Replay checks only that the class is known. A text-law refusal with a reading journals `reason: "refused <name>: <reading>"`; `publicRefusal` shows it.
- `suspended`: `{slot {principal, intent}, deadline, activity {object, method, argument, checkpoint {packetSha256, tokens, digest}, roots, absent, writes, sends, creates, programs, laws, ticks, awaited, awaits, offers, violation?}}` plus `request`, `ledger`, `ticksUsed`. Replay requires `digest == tokensDigest tokens` and registers it in `world.suspended`.
- `principal`: `{did, handle}`, identity `{clock, "principal:<did>:<height>"}`. `advanced`: `{from, to}`, replay requires `from == w.clock && to > from`. `settings`, `library {pin, previous, modules, law?}`, `posted`, `interpreted`, `forked`.

Cross-entry invariants (`checkDelivery`, `checkSends`, `checkResumes`):
- A `sends` id equals `deliveryId principal intent ordinal` (CID of `[principal, intent, ordinal]`).
- An entry with `delivery` consumes exactly the pending delivery it names, under the sender's principal, `intent == id`. A `budgetExhausted` refusal names a ledger field that is zero.
- An entry with `resumes` names a waiting suspension of the same identity.
- `record` derives `pending`, `suspended`, `clock`, `touched`, `receipts`, `outbox`, `handles`, `posts`, `replies`, `blocks`, `modules`.

## 4. Turn state and limits

`TurnState` lives in `M`; `Abort` is `request | evaluation | budget | suspend`. `finishTurn`: `.suspend` writes a `suspended` entry; `.evaluation` refuses `evaluation`; a `violation` refuses `requiredAbsence` (the violating creator is journaled as `root`, the taken id as `object`); `.ok` calls `commit`. A request error journals nothing, except for a delivered or resumed turn, which is refused.

- `roots`: set by `recordRoot`; validated at commit by `judge`, at resume by `resumeOne`.
- `writes`: `addWrite` (the running object only; another target is answered `refused {clause: notSelf}`), `ensureWrite` (reprogram/amend).
- `sends`: ids derive from the ordinal at commit (`sendsJson`). A send's ledger is `{depth-1, work - used, storage - bytes added}` (saturating). Work is charged after the fact: a turn may overshoot `work` by one turn.
- `creates`: built in-turn by `buildCreated` (compile, evaluate `initial()`, overlay the partial seed with `mergeSeed`, `makeObject`), installed by `commit`.
- A `create` with `requireAbsent.object == ""` gets `<creator>/<package lowercased>/<n>` (`mintId`); every creation of an id of that shape raises its parent's `minted`.
- `await` accepts `until` (absolute clock height) as well as `patience`; Plan `awaitUntil`. `awaitPost {post, patience}` / `awaitPostUntil` wait for the turn that replied to a recorded post.
- Await inside a `call` is refused; only the top activity checkpoints.

Limits (`Store.lean`, `Limits`; kernel bounds are in `Limits.lean`, see KERNEL-HANDOFF):

| group | names and values |
| --- | --- |
| ids, text | `maxObjectIdBytes` 128, `maxPrincipalBytes` 128, `maxIntentBytes` 256, `maxMethodBytes` 128, `maxHandleBytes` 256, `maxTitleBytes` 256, `maxUriBytes` 512 |
| per turn | `maxRoots` 64, `maxWrites` 64, `maxEditsPerWrite` 256, `maxPlansPerTurn` 1024, `maxCallDepth` 8, `sendsPerTurn` 32, `createsPerTurn` 8, `awaitsPerTurn` 8, `checksPerTurn` 8, `grantsPerTurn` 8, `publishesPerTurn` 4, `listPage` 64 |
| data | `dataDepth` 8192, `plainDepth` 64, `maxStateBytes` 262144, `maxSeedBytes` 262144, `maxObjects` 10000 |
| journal | `maxEntryBytes` 1 MiB, `maxJournalEntries` 1,000,000, `maxJournalBytes` 256 MiB, `maxHistoryLimit` 100, `maxCheckpointBytes` 512 KiB, `snapshotEvery` 1000, `maxSnapshotBytes` 256 MiB |
| ledger | `maxDepth` 100, `chainWork` 10,000,000, `chainStorage` 1 MiB (creation may lower, never raise) |
| time | `maxTurnTicks` 1,000,000, `maxPatience` 1,000,000, `interpretationPatience` 64 |
| delivery | `deliveriesPerCall` 16, `deliveriesPerSettle` 64, `maxPending` 4096, `pendingActivitiesPerObject` 8, `pendingInterpretationsPerObject` 64, `maxSuspended` 4096, `maxResumesPerCall` 1024, `maxGrants` 4096 |
| programs, laws | `maxPackageBytes` 32768, `maxLawBytes` 4096, `maxLawClauses` 16, `maxPreparedPrograms` 16, `maxCompiledPackets` 256, `maxBuilds` 1024, `maxReaders` 256, `maxLibraryModules` 256, `maxLibraryBytes` 786432 |
| interpret | `maxUtteranceBytes` 8192, `maxOffersBytes` 65536, `maxReplyBytes` 262144 |
| forms | `formTextMax` 1400, `formNaturalMax` 1000000000 |

A full count refuses the turn with class `capacity`, reason the limit's name.

## 5. Subsystems

### 5.1 Authority and laws

- `Facts {subject, caller, height, turn, pin, kind, method}`. `caller` is the object whose method wrote ("" for the turn's own method and client proposals; for a delivered turn, the sending object). `method` is the method whose run made the change ("" for ops).
- Fragment: `request.subject`, `request.caller`, `request.pin`, `request.kind`, `request.method`, text constants, `x in new.F` (`member`), `appendOnly(F)`, `unchanged(F)`, `writeOnce(F)`. `writeOnce` admits exactly one change of F away from its empty value (`emptyValue`: 0, false, "", the empty list, a record of empty values); a field missing from the old state fails closed.
- `judge` judges every distinct (caller, kind) of an object's changes. Default law `owner: request.kind == 0 or request.subject == "<creator>"`: anyone may invoke methods, only the creator may reprogram or amend (`defaultLaw`). Metarule: an amendment must be admitted by the existing law for its proposer; message "law does not admit an amendment by its proposer <p>: <name>: <expr>".
- `Object.readings` holds the package's law readings for clauses that are still the package's; `makeObject` keeps those the effective law leaves equal, an amendment keeps those it leaves equal, a reprogram keeps all. `parseLawTextReadings` reads `law NAME "reading": EXPR`; a malformed reading is `law syntax`.
- Context (`contextData`, also the Bend law's request context): `{world, object, principal, handle, caller, intent, height, clock, inputOrigin}`. The host fits each Context to the receiving code's own declared record (`fitRecord`), so a field added to the library later never breaks an older object.
- Two-tier law: for an artifact with `law.present` (`Object.predicate`), after the text admits, `judge` runs `law(old, new, request)` once per distinct kind-0 change (`bendLaw`) with `request = {context, method, argument, kind, pin, reads}` (`inputOrigin.kind = "law"`). `reads` are the ids `lawReads()` returns; `commit` adds them to the roots (`withLawReads`). Runs under `Bounds.lawTicks`: `admitted`, `refused {clause}` (= `lawRefused clause`), exhaustion is class `budget` reason `law ticks`, anything else fails closed as `lawRefused law`/`lawReads`. Reprograms and amendments are the text's alone. `warmLaws` compiles `law`/`lawReads` before `judge`.
- Commutative edits: `judge` accepts a root `(id, seen)` whose object moved (`seen < version now`) when every change of `id` is a kind-0 write whose every edit is `keep`, `add`, `append`, `insert` (`EditKind.commutes`), or an `upsert`/`retract` of a relation row whose key no admitted write since `seen` touched (`keysChangedSince`, read from `writes[].edits`; a `set` or list edit of the relation touches every key), or, on a resumed turn's own object, an edit of a field later writes left alone (`movedRootAdmits`, one rule for `judge` and `resumeOne`). The entry keeps the roots as read, so `writes[].version` can be past `seen + 1`. Any other moved root is `staleRoot`. List items by bytes: `amendItem {item, change}` and `removeItem {item}` address the first item with the same canonical DAG-CBOR; none is `absentItem`. The index forms `amend {index}`/`remove {index}` are still accepted; `world/` uses none.
- Stale resumptions: a resumed turn's own object may have moved while it waited. `judge` and `resumeOne` accept it when `movedRootAdmits` holds (every later change was an ordinary write and each of the turn's edits commutes, is a row edit of an untouched key, or touches a field those left alone). Otherwise `staleRoot` (transient), and `resumeOne` re-runs the direct turn once from its journaled request (`TurnMeta.rerun`, journaled `rerun: true`, reply `rerunOf`). Deliveries are not re-run.
- Cross-object dry run: a `reprogram`/`extend`/`amend` Plan naming another object records it as a root and dry-runs the change alone through `judge` (`dryChange`). A refusal is answered `refused {clause}` and nothing is staged. The commit still judges the whole turn.
- Typed arguments: an argument that does not fit the method's input type (`argumentFits`, `kernelRefusal`) refuses with class `typeMismatch`, which binds. The refused outcome journals `expected {method, type, form?}` (`expectedInput`); the receipt carries it for the turn's own principal only. In a `call` the Plan is answered `refused {clause: typeMismatch}`.

### 5.2 Grants

- Plans `grant {to, object, method, until}` -> `granted {id}`, `grantWith {…, fixed: Data, uses: Nat}` (uses >= 1; 0 is `refused {clause: uses}`), `revoke {id}`, `callVia`/`sendVia`. Only a direct turn's top frame may grant (`notDirect`); the grantor is the turn's principal, the holder the running object. `to` is a principal or object id and must be the frame's subject or the calling object at use.
- A grant stands (`grantStands`) while not revoked, the clock is `<= until`, and object and method match. Under a grant the callee runs with subject = grantor, caller = the calling object. `judge` re-checks the grant (`lawRefused noGrant`). A `sendVia` delivery runs as the grantor and is refused `noGrant` (consumed) if the grant fell in between.
- `grantFor` checks the grant, the grantee, a use left (`grantSpent`), and `attenuate`s: a fixed record's fields join the caller's record; a field the caller gives with other bytes is `grantConflict`. A use is spent only when the call runs or the send is staged; the admitted entry records `spent [{id, uses}]`.
- Revocation: the holder object, or the grantor in an undelegated frame (`notGrantor` otherwise). `world-revoke {principal, identity, grant}` is the grantor's write outside any object. Entries carry `grants [{id, grantor, holder, to, object, method, until}]` and `revokes [id]`, installed by `applyGrants`. Ids are CIDs of `["grant", principal, intent, ordinal]`.
- Tests: `test_grants` (incl. `Attenuation`).

### 5.3 Reflection, library, extension, supervisors, handlers

- Library: `Library {pin, modules}` sealed by `sealLibrary` (dependency order, then name). Objects' compile inputs carry `"library": pin` and only their own modules; `resolveInputs` prepends the library closure on every compile. A reprogram compiles against the world's current library. A library change is a `library` entry judged by the world law (default `opener: request.subject == "<opening principal>"`, kind 1); replay re-seals and re-judges.
- `inspect` answers pin, law text, the entry module's source and the method forms under the reader's `ReadPolicy` (`denied` otherwise). `check` runs `Package.checkPackage` over the library closure, answers `"<module>:<line>: <stage>: <message>"` strings and a following `"<module>:<line>: hint: <text>"` line when the kernel has a hint; it installs nothing.
- `world-check {principal, modules | source, entry, limits?}` compiles over the world's library (`overLibrary`), journals nothing, any principal may ask. Stateless `check-package`/`compile` take `library: <pin>`, resolved among the world's libraries then those sealed with `library-load` (at most 4 kept).
- Method table and forms: `Object.methods` is the artifact's method table (reprogram replaces it; for a layer stack it lists every layer's methods, top first). `world-inspect` answers it as `methods` plus `forms`. A form is `{card, action, fields}` for each method that takes a context and whose input is a record of `String` (text 0..`formTextMax`), `Nat` (0..`formNaturalMax`) or a closed sum of empty payloads.
- Extend: `world-reprogram {mode: "extend"}` and Plan `extend` add the source as module `Layer<n>`. The host writes `layer over ./<module below>.obend` as its first line (`layerLine`), so the kernel builds a layer stack with late binding. New pin = CID of `["extend", old pin, source CID]`; the state type must be equal under `canonicalTy` or a migration named. A layer written in the older `import … as Super` form is rewritten on replay and on snapshot load (`stackForm`). Tests: `test_extend`, `test_layers`.
- Supervisors: `Object.supervisor` is fixed at creation (`world-create {supervisor}`, Plan `createUnder`; `refused {clause: supervisor}` if not an object). An activity of a supervised object ends `broken` when refused `evaluation`, `budget` when a machine budget ran out, `timedOut` when a segment resumed past its deadline ends in any way. `commit` puts an `ended {id, to, method: "ended", argument, sender, ledger}` field in that entry (`endedField`, `endedId`); `record` makes it a pending delivery with argument `{receipt, how}`. A ledger refusal (`budgetExhausted`) tells nobody. Replay checks the id and that `to` is the supervisor (`checkEnded`). Test: `test_supervisors`.
- Handlers: Plan `run {object, method, argument, handler}` runs the callee as `call` does, but every Plan the callee's own frame yields is first offered to the handler's pure `handle(state, plan[, context]) -> Handled<R>` (`answer {response}` or `pass`). The handler must be readable by the subject (`refused {clause: handler}`) and is a root. Plan `judge {edits}` answers `judged {admitted, clause}` without committing. Test: `test_handlers`.
- Held entries: `compiledMethod`/`compileDef` use `compileEntryIn` (`Package.prepareRequest` cached in `world.requests`, `Package.compileEntryFrom`); `Compiled.entry` is a decoded, checked `CheckedEntry`. Turns run `Turn.startEntry`/`resumeEntry`; pure definitions (law, `lawReads`, handler, pure methods, migrations) run `Package.executeDataEntry`. Only `initial()` at creation runs from the packet.
- Kernel integration: `world-turn {…, profile: true}` returns `profile [{kind, steps, ticks}]` (not journaled). `annotateData` (`Turn.lean`) annotates sum-valued arguments.

### 5.4 Interpretation

- Plan `interpret {utterance, offers, policy, model}` suspends like `await` with `interpretation {id, object, policy, utterance, offers, model?}` (id = hash of principal, intent, ordinal). Deadline `interpretationPatience`, resuming `timedOut`.
- `world-interpretations` lists pending items with the Policy's state as `{model, system, examples}`; `policy.system` is the Policy's pure `prompt(state, offers, utterance)` (`policyPrompt`) else its `system` field; `policy.model` is the item's `model` when non-empty (at most 128 bytes), else the Policy's.
- `world-interpretation {id, reply}` journals an `interpreted` entry and the settle pass resumes the turn. Verdicts: `proposal {method, argument}` (the method exists, is offered, the argument conforms, the Response can carry it), `replied {text}` (reply `json` not `{method, argument}` with `raw`), `unclear {needs}` (failed reply; `failed` gives `needs: ["model: <reason>"]`).
- Capacity: `mayWait … (interpreting := true)` counts interpretations apart. Test: `test_interpret_text`, `test_policy`.

### 5.5 Cards, offers, publish, posts

- Plan `card {object}` -> `carded {document}`: `renderCard` runs the target's card on its committed state under the turn's ticks (records a root; `denied` without read authority, `noCard`, `refused {clause: render}`). It runs `renderFor(state, context)` when the method table lists it, else `render`. `cardContext`: principal = reader, caller = asking object ("" for the op), `inputOrigin.kind` "card". `world-card {principal, object}` -> `{status: "card", text, document}`; `ownCards` `env`/`wake` resolve to `<name>/<principal>` (`resolveCard`).
- Plan `objects {prefix, after}` -> `listed {ids, more}` (ids the subject may view, byte order, `listPage`); op `world-objects`.
- `offer {to, document}` ("" = the frame's subject). An admitted entry retains `offers [{to, text}]`; `record` indexes them by addressee (`world.outbox`). `world-offers {principal, after?}` answers `offers [{height, ordinal, identity, text, from {post, principal, intent}}]` (`originOf`). A turn's reply carries only offers addressed to its own principal. A turn that offers nothing has no `offers` field.
- Reads under authority: `world-receipt {principal, identity, of?}`; `projectEntry` gives the identity's own principal the whole entry, anyone else a `publicRefusal` (`{status: "refused", class, root {object, version?}, reason?}`, plus `object` and `hint` for `unknownObject`, `object` for `requiredAbsence`) or chain fields, roots and writes of objects the reader may view, and an `elided` count. A refused turn reply carries it as `public`.
- `publish {page, section, body}` -> `published {post}` (at most `publishesPerTurn`; a title or section with a line break or over 256 bytes is `refused {clause: title}`). The admitted entry retains `publishes [{id, object, page, section, text}]` with agentwiki text (`wiki: Title\n\nbody` or `edit: Title › Section\n\nbody`). `world-publications {principal, after?, before?, reverse?, limit?}` answers `publications [{height, ordinal, id, object, page, section, body, hash, replyTo?}]`.
- `world-turn {replyTo}` (in the digest): when the parent is a post recorded for the turn's object, the entry journals `replyTo` and `World.replies` maps the post to the turn. `receive`'s `slot` is the host's (`receiveArgument`): dropped for an object declaring `{text, post}`, filled from the recorded post's slot for one still declaring it.
- Transport side: `transport/bridge.py` `publication_drafts` writes each publication as an outbox draft and never posts; `transport/post.py --record` confirms as the clock principal and calls `world-posted`.

### 5.6 Snapshots and replay

- `durable` writes `<journal>.snapshot.<height>.cbor` after the fsync when the height is `snapshotEvery` past the last snapshot written or resumed from; the reply carries `snapshot {height}` or `{refused}` (a failed snapshot refuses nothing). The newest three are kept. File: DAG-CBOR `{cid, body}`; `tests/test_snapshot.py` has an independent Python encoder.
- The body holds objects (state, `stateCid`, law text, version, read policy, ledger, compile inputs by CID, `pin`, `packet` cached), types, method tables and law shapes by pin, libraries, grants, posts, settings, `supervisor`, `minted`, `readings`; plus `clock`, `pending`, `suspended` as cross-checks. Everything `record` derives is rebuilt by `recordAll`. Sources no entry carries by CID (reprogrammed and extended modules) are kept whole (`knownByCid`).
- `openContent`: parse and hash-walk every entry (`entriesOf`), then per snapshot newest first check the CID, edition, height, `head`, derived copies, each object's version and pin against the entries (`expectedObjects`), each law reading back from its text, and that every later entry replays on it. The first failure refuses the snapshot by name and the next older is tried, then full replay.
- `install` refuses "the state of X is not its CID's" and "object X carries no state CID". Against a forger who recomputes both, `resume` compares each object with `anchoredStates` (a created or child seed, or a write's `cid`): "the state of X is not the one the journal commits to at version V". `world-open {verify: true}` replays everything and refuses each snapshot that differs from the replayed store ("it disagrees with replay at its height").
- Pins are sources. No packet digest is journaled: replay recompiles from the journaled sources with the current compiler and requires the compile to succeed, the seed to conform and the recomputed pin to equal the recorded one. `world-status.recompiledDifferently` counts objects rebuilt after a snapshot resume whose packet differs from the one the snapshot cached (`World.cachedPackets`, `noteRecompiled`). An old `compiled {binary, packet}` field is ignored.
- Suspension checkpoints are journaled as `tokenTree {depth, roots}` over content-defined blocks (`cutBlocks`: leaves 32..256 tokens, a token of 256 bytes or more its own leaf; inner nodes 2..16 names), each block once per journal as a top-level `blocks [{cid, items}]` item (`World.blocks`); an interpretation's `offers` are a one-item block (`offersBlock`). Replay still reads older blocks and `utteranceBlock`; a `tokenTree.relative` checkpoint is refused by name. Measured on hbox at foundation 6b928f6 (132 directory suspensions, `tests/test_suspension_size.py`): median 9,392 B with blocks against 119,119 B with the v2 codec alone.

### 5.7 Slugs, fork, repository reads

- Slug (`Slug.lean` `ofCid`, `decode`): proquint of the first 32 bits of a CID's multihash digest (`lusab-babad`). Replies show receipts with `slug` beside `hash`; `world-inspect` shows `pinSlug`. `world-resolve {principal, slug}` answers `{status: "resolved", kind: receipt | pin | state, cid, receipt?}`, `{status: "ambiguous", matches, message}` or `{status: "unknown", message}` over `slugTargets`. Test: `test_slug`.
- `world-fork {principal, height?, into}` (`Session.forkWorld`; `into` must not exist) writes a new journal whose one entry is a `forked` genesis (`Snapshot.forkGenesis`): the store at `height` as a snapshot body with whole sources, only the objects `principal` may view (with grants, pending deliveries, suspended activities), the handle registry, `omitted [ids]`, `forkedFrom {world, height, cid}`. Opener, clock principal and library-law principal are `principal`. Height 1 chains to the forked entry's `cid` (`entriesOf`); replay starts from the installed genesis (`installFork`). Answers `{status: "forked", into, forkedFrom, carried, omitted}`. Test: `test_fork`.
- `world-entry {principal, hash, bytes?}` (`bytes` = hex of the canonical DAG-CBOR, identity's own principal only); `world-entries {principal, after?, before?, reverse?, limit?}` (limit 1..100); `world-object {principal, object, version?}` -> `record {object, version, pin, pinSlug, law, readings, laws [{object, version, pin, name, clause, reading?}], stateCid, library?}` as of the version (`pinAndLawAt`); `world-source`/`world-sources` -> `{cid, name, text, height}` for sources of objects the reader may view and the libraries'; `world-grants`. Test: `test_reads`.

### 5.8 Arrival

`world-arrive {principal, did, handle}` (clock principal only; the world must name an opener and have a library) records the handle as `world-principal` does, then creates each absent one of `<did>` from library module `Avatar`, `env/<did>` from `Env`, `wake/<did>` from `Wake`, as `create` by the opener with identity `arrive:<id>`, `owner: did`. Idempotent: a repeat answers `{status: "arrived", did, handle, created: []}` with no entry. Reply: `created [{object, height}]` and `principal`. A missing library module is a request error naming it. `transport/hostproc.py` `ARRIVAL` lists the packages the sealed library must hold (`Avatar`, `Env`, `Wake`, `Place`). `docs/GENESIS.md` says when transport calls it. Test: `test_arrive`.

43. **Per-op timing (host7).** With `DELVETALK_TIMING=1` in its environment, the host binary writes one stderr line per
   op after the reply: `timing<TAB>op<TAB>ms<TAB>object=…<TAB>method=…<TAB>principal=…<TAB>resumed=n<TAB>delivered=n`
   (`PackageMain.timingLine`; ms from reading the request to writing the reply, the settling pass included). hostd's
   children inherit the variable and the stderr, so a rehearsal run with it set leaves the lines in `hostd.stderr`.

44. **Rehearsal run 9's costs (host7, finding 5).** Measured with `DELVETALK_TIMING=1` on the run (host ms by op and
   object): directory `receive` turns 15.5 s (120 turns, ~130 ms), `world-arrive` 8.3 s (77 arrivals, ~110 ms), garden
   `receive` 6.1 s, env `receive` 5.5 s (277 turns), `world-interpretation` 1.7 s. Fixes, measured as host CPU per op
   on the run's own journal (median of 15, hbox at load ~20): `libraryClosure` is a worklist that reads each wanted
   module's imports once (it re-split every library module's source once per library module per call, and a creation
   calls it twice): an arrival 190 -> 20 ms. The checkpoint dictionary (`Dictionary.ofProgram`, which the kernel built
   twice per yield) is built once per compiled method (`Compiled.dictionary`) and passed to `Turn.startEntry` /
   `resumeEntry` (an optional parameter added to the kernel's functions): a directory prose turn 310 -> 180 ms.

45. **Relations, day 1 (host7; RELATIONAL.md §2, §3, §11 item 1).** A package declares relations with `def relations() ->
   Lists.List<Decl>` (`{field, key: List<String>, limit: Nat, retain?}`; `retain` only `dropOldest`). The host reads it
   only when a module of the package has a `def relations(` line (`declaresRelations`), compiling it as a held entry
   (`relationDecls`; `prepareProgram` compiles it from the program's resolved inputs) into `Object.relations` /
   `Program.relations : List RelDecl` (snapshots keep `relations` per object). A relation field holds
   `rows {items: List<T>}` of records `T`; `checkRelations` refuses at creation (and reprogram, clause `key`) a field that
   is not one or a key column `T` lacks, by name. `canonicalRows`: rows sorted by the canonical DAG-CBOR bytes of their
   key projection (NB: DAG-CBOR orders map keys by length first, so key `{author, at}` sorts by `at` before `author`; the
   contract's "sorted by key" means these bytes), no key twice (`duplicateKey`, refused by name at creation), at most
   `limit` rows (0: `Limits.maxRelationRows` 4,096), the oldest by key order dropped. Seeds are canonicalized before they
   are journaled (`create`, `buildCreated`, `buildObjectIn`), migration results in `judge`, and every write of a relation
   field (`applyStep` with the object's decls). Edits `insert {row}`, `upsert {row}`, `retract {key}` (`EditKind`,
   `relationEdit`) follow the nine-cell table; `keyTaken` and `duplicateKey` are refusal classes. Against a moved root (day 2): an insert commutes (re-applied on the rows now: a fresh key adds, the same row is no change, another row under the key is `keyTaken`, which binds); an upsert or retract commutes when no admitted write since the turn read touched its key, else `staleRoot` (transient). When that `staleRoot` falls on a resumed direct turn, `resumeOne` re-runs it once from its request (`rerun`), and the re-run reads the rows as they are now: a retract then removes whatever row holds the key now (or is a no-op if it is gone), an insert meets `keyTaken`. Tests: `tests/test_relation.py` `Moved`. The host reads edit
   labels, not type names, so a package may declare its own `Relation<T>` and row-edit sum until `Relation.obend` and
   Plan.obend's constructors land. Tests: `tests/test_relation.py`.

46. **Derived views (host8).** Plan `viewDerived {object, view}` answers `derived {version, value: Data}`: the
   target package's pure definition `view`, which its `def views() -> List<String>` must name (read once
   per compile, as `lawReads()` is: `declaredViews`), runs on the committed state, with the reader's Context
   (`inputOrigin.kind = "view"`, `command` the view) when it takes one, under the turn's remaining ticks,
   as a card renders (`derivedView`). Read authority and the root are `view`'s. Refusals: `noView` (not
   declared, or no such definition), `view` (fails, runs out, or its result type is not first-order data);
   `denied` without read authority. `world-inspect` lists `views` when the package declares any. The host
   reads the Plan label, so a package may declare its own Plan/Response arms; Plan.obend's constructors
   (`viewDerived` at the end of `Plan`, `derived` at the end of `Response`) and World.obend's protocol line
   are the objects lane's, added with their pin re-record. Test: `tests/test_view_derived.py`.

47. **Past versions (host8).** Plan `viewAt {object, version}` answers `viewed {version, state}` with the state
   the object had at `version`, rebuilt by `stateAt` (Ops): the created seed (or a creating turn's), then each
   admitted write in order, its edits re-applied under the object's relations or a reprogram's recorded
   `result` taken, each checked against the write's recorded `cid`; refused `version` when the version is
   past the current one, before a fork genesis, or a rebuilt state is not the journaled one. Read authority
   as `view`; the root is recorded at the CURRENT version. Cost is linear in the object's writes up to
   `version`. Test: `tests/test_view_at.py`.

48. **The world object (host8; WHOLENESS §1, host day 1).** A message activity (`Activity<R>`, artifact
   `dialect: "message"`) yields `World.Message {object, method, argument}`; `drive` re-heads it
   (`messagePlan`) as the variant the arms answer: `write`'s argument is the running object's edits,
   `judge`'s the edits to judge, every other method's argument is its arm's payload. A message whose
   `object` is not `{world: "", object: "world"}` is answered `refused {clause: notWorld}` (a message to an
   object is a `call`), a method outside `worldMethods` `refused {clause: noMethod}`; `spell`, `subscribe`
   and `unsubscribe` are listed and answered by later days. The response is checked against the call
   site's type the kernel reports (`responseType`). A sum Plan is answered by constructor as before, so
   both dialects run side by side. A handler (`run`) sees the Message as yielded. The world has no state
   and no law (WHOLENESS §5): who may call which method is the authority model as built (`write`
   self-only, `create` under the creator's rules, grants, read policy). The id `world` is reserved
   (`worldId`, `validObjectId`). A message suspension's checkpoint (two-token site prefix) goes through
   the block scheme like any other. `viewField {object, field}` (RELATIONAL §6) answers `viewed {version,
   state}` with one field when its value conforms to the call site's type (`typeMismatch` otherwise,
   `field` for a missing field); read authority and root as `view`. Test: `tests/test_world_object.py`.

49. **The host reads spells (host8; WHOLENESS §2, host day 2).** `Host/Spell.lean` is Spell.obend's grammar in
   Lean, rule for rule (`parse`, `bare`, `fit`, reasons verbatim, plus a `Clause`: `otherCard`, `noAction`,
   `unknownField`, `duplicateField`, `badValue`, `unclosedBlock`, `unclear`); the stateless op `spell-parse
   {text, form?}` answers `{status: "parsed", spell | notASpell, fit?, bare}`; `tests/test_host_spell.py` runs
   115 fixtures (`tests/fixtures/spells/`) through both parsers and they agree. `runTurn` sends a direct
   `receive {text, post}` to a card whose `receive` is in the message dialect through `spellTurn` (a sum-Plan
   card reads its own replies, unchanged): the spell's card resolves (`resolveCard`) and the turn is
   retargeted to it (same principal, identity, `replyTo`); `?` answers `{status: "usage", object, text}` and
   journals nothing; the action is looked up in the card's `methodForms`; a fitting spell runs the method with
   the typed argument (text, natural, a choice as its empty-payload variant), `inputOrigin.kind = "spell"`,
   `command` the spell line; a misfit is refused, class `badSpell` (binding), with `clause`, `reason` and
   `hint` (the spell with the given fields and blanks; the usage for `noAction`/`otherCard`), all in the
   public projection. Per the root decision, a spell missing fields and a reply with no spell run `receive`
   with the bare `name: value` lines as `fields` (when `receive` declares them): completion is the card's
   policy. A reply with no spell line whose first field line names one of the card's actions or fields is
   that form's spell (`Card.withBare`). The interpretation fit and lens `set` are 5.54. Test:
   `tests/test_spell_turns.py`.

50. **Subscriptions and `changed` (host8; WHOLENESS §3, host day 3).** Plan/world method `subscribe {object, field}`
   stages `Subscription {subscriber: the running object, principal: the frame's subject, object, field}`:
   `denied` unless the subject may view the object, `field` unless the object's state has that top-level
   field, `subscribers` past `Limits.subscribersPerObject` 64; a repeat is idempotent; `unsubscribe` ends
   the running object's own. The admitted entry journals `subscribes`/`unsubscribes` (also in the request
   digest; `judge` re-counts the bound); `record` derives `World.subscriptions` (`subscriptionsAfter`), so
   replay and snapshot resume rebuild it; a suspended activity carries its staged ones. After an admitted
   write, `changesJson` owes each subscription to a field the turn's ordinary edits touched a delivery
   `{id, to, object, field, version, principal, ledger, argument}` beside `sends` (ids continue the sends'
   ordinals; ledger as a send's, `childLedger`), argument `{object: Reference, field, version, inserted,
   retracted}`: for a relation the rows added and removed (an upsert that replaced a row is both), for a
   list the items added and removed, for a scalar `[new]` and `[old]`. Sends and changes together are at
   most `sendsPerTurn`; the subscribers past it are named in `unserved`. `record` queues them as pending
   deliveries of method `changed` (sender the changed object, run under the subscription's principal).
   Unlike WHOLENESS's "re-derived, never stored", the argument IS journaled: a scalar's old value is not in
   `writes[].edits`; replay re-derives the whole `changes`/`unserved` from the states and requires them
   equal, so it is checked, not trusted. `deliverOne` refuses a `changed` whose principal may no longer view
   the object (`lawRefused`, clause `denied`) and `record` drops that subscription. Test: `tests/test_changes.py`.

51. **Field roots (host8; WHOLENESS §3a, the part the host can see).** `viewField` records a field root
   (`recordFieldRoot`; none when the whole object is already a root): `{object, field, key: "*", version}` in
   the entry's `roots` beside the object roots (`allRootsJson`; `parseRoots` skips them, `parseFieldRoots`
   reads them; in the request digest as `fieldRoots`). `judge` and `resumeOne` hold a moved field root
   current while no write since its version touched the field (`fieldsChangedSince`, from the per-object
   index). Both count against `maxRoots`. Not done, and not doable from the host alone: per-row roots
   (`{object, field, key}` for the rows a turn's code read). The host sees the whole state go into a turn
   and cannot tell which rows `lookup`/`where` touched; that needs the kernel's lazy state cells
   (KERNEL-HANDOFF §15), whose `fetch` would call `recordRows`. Test: `tests/test_changes.py`
   `test_a_field_root_is_stale_only_when_its_field_moved`.

52. **Words for sums at the boundary (host9).** An argument from outside, a direct turn's (`runFrame` at
   depth 0 of a direct turn) or an interpretation proposal's (`interpretVerdict`), is read against the
   method's input type before the conformance check (`wordsAsCases`, Ops; `inputWords`, TurnLoop): where
   the type has a closed sum whose every case has an empty payload and the value is a text, the text is the
   case of that name, in fields, nested records, list items and the payloads of named cases. A word naming
   no case refuses the direct turn `typeMismatch` (binding), reason `... : colour is one of: amber, violet,
   silver (not gold)` (path `bed.colours[1]` inside lists), `expected.cases {at, given, cases}`; a proposal's
   is `unclear {needs: ["colour is one of: ..."]}`. The frame's argument (`Written.argument`, the Bend
   law's `request.argument`) is the read one; the request digest is of the argument as sent. Deliveries,
   `call` and `send` arguments are typed values and are not read so. Test: `tests/test_sum_words.py`.

53. **Typed receivers (host9; WHOLENESS second root decisions, 3 and 5).** `subscribe {object, field,
   method}` names the subscriber's receiver; "" or absent is `changed`. The receiver must be a method of
   the subscriber (`refused {clause: method}`). One subscription per (subscriber, object, field): a
   subscribe naming another receiver replaces the standing one (journaled as an unsubscribe of the old
   and a subscribe of the new). `Subscription.method` is journaled in `subscribes`/`unsubscribes` and in
   each `changes` item only when it is not `changed`; `record` queues the delivery to that method.
   `inserted`/`retracted` are checked against the receiver's declared input at delivery as any
   delivered argument is (`argumentFits`): rows that do not conform refuse the delivery `typeMismatch`
   with `expected {method, type}`; the subscription stands. A change delivery is told apart from a send
   by its `field` (the read-authority recheck and the `denied` drop use it). `spell` is not a world
   method (`noMethod`): the host's spell path runs a card's methods directly. World.obend's
   `subscribe` line gains `method: String` in the objects lane (tests replace the line in a library
   copy until then). Test: `tests/test_changes.py` `Receivers`.

54. **Spells, the rest (host9; WHOLENESS §2, second root decisions 2).** Interpretation: a model's text
   to an activity of the message dialect is fitted against the offered forms (`spellVerdict`): a spell
   naming an offered form that fits is that form's `proposal {method, argument}` (checked as a JSON
   proposal is, `proposalVerdict`), a misfit `unclear {needs: [reason]}`, missing fields `unclear
   {needs: [names]}`, a spell naming no offered form `unclear`; a text with no spell line whose first
   field line names an offered action or field is that form's spell; prose stays `replied {text}`. A
   sum-Plan activity still hears every text as `replied` (Garden and the Directory read their own until
   they migrate). Lenses: a message-dialect card declares its lenses as data, `def lenses() ->
   Lists.List<Form.Field>` (name and kind; the sum dialect's `lenses()` of `Form.Lens` closures is not
   data and reads as none), and puts through a method `set(state, input: {field: String, value:
   Form.Value}, context)`. `delvetalk <card> set` with one `<field>: <value>` line is judged against
   the lens's kind (`badValue`, reason as a form field's) and runs `set` with the typed value
   (`inputOrigin.kind = "spell"`, `command` `delvetalk <card> set`); a field no lens names, or more than
   one field line, is `badSpell` `unknownField`; no field line is `receive` with the bare fields
   (completion is the card's policy). A card whose forms already have an action `set` keeps it. `?`
   lists the lenses after the forms. `bridge.draft_text` reading `hint` is transport's. Tests:
   `tests/test_spell_turns.py` `Lenses`, `Interpreted`.

55. **`admits` per method (host9; AGENTS-API "host ops wanted" 1).** `world-inspect`'s `methods` rows
   that take a context carry `admits: true | {clause, reading?}` (`methodAdmits`): the text law judged
   for a kind-0 change by the reader through that method on the unchanged state (`Facts {subject:
   reader, caller: "", kind: 0, method, height = turn = height + 1, pin}`). Only a clause that reads no
   state field (`LawExpr.fields` empty) can refuse here, since the change cannot alter its verdict; a
   clause that reads the state is left to the commit (`true`), so `admits` never refuses what a commit
   would admit. The Bend law is not consulted. The front (`transport/http.py`) then omits refused
   actions: `tests/test_hypermedia.py`'s law-refusal reply no longer offers `bump`. Test:
   `tests/test_inspect_reads.py`.

56. **Methods in a listing (host9; AGENTS-API "host ops wanted" 2).** `world-objects {principal, prefix?,
   after?, methods?: true}` adds `methods: {<id>: [<name>]}`, the turnable method names (`context:
   true`, table order) of each listed id; the ids are the reader's as before. `methods` other than a
   boolean is a request error. Test: `tests/test_inspect_reads.py` `Listed`.

57. **`world-inspect {source: false}` (host9).** Omits `source`; everything else is as with `source: true`
   (the default). A non-boolean is a request error. Test: `tests/test_inspect_reads.py`.

58. **In-process yields hold the machine state (host9; KERNEL-HANDOFF §18).** `runFrame` starts with
   `Turn.startEntryStep`; `drive` takes a `Turn.Step`, whose yield holds a `Turn.Suspension`; a Plan
   answered in this process resumes with `Turn.resumeSuspended` (no checkpoint encoded, digested or
   decoded). Only `await*` and `interpret`, which may suspend, build `suspension.checkpoint`; the profile
   reads it lazily. A journaled resumption uses `resumeEntryStep`. Measured on hbox, the offline
   rehearsal with `DELVETALK_TIMING=1`, one run each on the same tree (before at load ~5, after at ~17):
   host ms 25,646 -> 13,621; directory `receive` 11,339 -> 4,521 (120 turns, median 70 -> 22 ms); garden
   `receive` 5,189 -> 2,010; env `receive` 3,681 -> 2,267; rehearsal wall 62.3 -> 43.4 s.

59. **Compile caches per process (host9).** `World.compiled`, `requests`, `builds` and `programs` are
   keyed by content addresses (compile inputs naming the library by pin and modules by CID; `defKey`,
   `buildKey`, `programKey`), so `Session.stepWorld` hands the caches of the world it had open to the
   next it opens (`Caches`, `World.caches`/`withCaches`; `openWorld` -> `openContent` -> `startOf`,
   `replayAll`, `resume`), and `world-fork`'s replay uses them. `world-status.compiled {packages,
   closures, methods}` counts them. Measured on hbox (`world-create` of Place, Garden, Directory, Thing
   from `world/objects`, a fresh world each time, one process): first world 78/137/92/102 ms, the next
   world 6/8/6/6 ms. Separate processes (hostd's heaps) still compile from scratch: the on-disk cache is
   queued (§7). Test: `tests/test_compile_cache.py`.

## 6. Gotchas

- `conformsUnder` needs the packet's bounds (`Object.bounds`, `Compiled.bounds`); bare `conforms` is only for closed non-recursive types.
- `canonicalTy` (Ops): two state types are equal when their canonical forms agree (variables renamed in order of first use, at most 4096 steps, else "type too deep to compare"). Reprogram and extend depend on it.
- Plan wire shapes: `world/lib/Plan.obend` is the contract. `write.edits` is a record with one variant per state field. `respond` picks the first payload that conforms to the object's Response type; a sum lacking the label gives "response type cannot carry <label>".
- Seeds are laid over `initial()` (`mergeSeed`): a record of some fields, `{}` for `initial()`; a field the state lacks is `typeMismatch`. A seed that does not set a text `owner` gets the named `owner`, else the creating principal (`withOwner`). `create`'s `package` is a module name in the creator's sealed chain, or source starting `edition`; `law` is used only if it starts `law `.
- Hand-built Contexts in tests must carry caller, intent and height or the method does not type.
- Lean keywords: `meta`, `from`, `seal`. Structure-instance continuation lines must be indented past the first field.
- A suspended identity has a `suspended` entry; `retained` ignores it so the final commit can reuse the identity.
- Settling runs inside `durable`, after the triggering op, and appends to the same write.
- `Handle.flush` is not durable; `sync.c` does `fflush` + `fsync` (or `F_FULLFSYNC`). One sync per `durable` call. The build needs `lakefile.lean` for `extern_lib`.
- `python3 -W error` turns leaked subprocess warnings into failures; close hosts in `tearDown`. `tests.test_replay` and `test_await` are slow because every `world-create` compiles.
- Never run an unfiltered package suite on a loop.

## 7. Open

- Forms for sum inputs: `methodForms` lists only text, natural and closed empty-payload sums; a sum held as a bounds variable has none. Closes when a sum held as a bounds variable yields a choice or form (resolve variables through the packet's `bounds`).
- Handlers over nested frames and activities: `run` offers only the callee's own frame's plans to a pure `handle`.
- Foreign worlds: `Reference.world != ""` is refused `foreignWorld`.
- `tests/test_bridge.py` `test_end_to_end_clock_and_addressee_against_the_real_host` is still `@unittest.expectedFailure` with a comment that `world-addressee` is missing; the op exists (`Session.lean`). Remove the decorator and run it.
- `world-reprogram`/`amend` are gated only by the object's law.

### Queue for the next host lane, in order (from lane/host8, which stopped at its context ceiling)

host8 landed, one commit each (5.46 to 5.51 and the commits on lane/host8): compile caches kept across
turns and card reads; a migration made canonical (test); the relational law atoms denoted; relations read
once per build from the entry module only; relations day 2 (inserts commute, keyed row rebase,
`movedRootAdmits`); state bytes counted without printing; the per-object write index (`World.touches`);
`viewDerived`; `viewAt`; the world object (message dispatch, `world` reserved); `viewField`; Host/Spell.lean
and `spell-parse`; spells read by the host for message-dialect cards (`badSpell`); subscriptions and
`changed`; field roots. Build and test on hbox in your own directory with `swarm-build`; narrow suites, then
the full `tests.run` once (1011 tests green at lane/host8's last commit).

1. Done on lane/host9 (5.52).
2. Done on lane/host9 (5.54).
3. Done on lane/host9 (5.55 to 5.57).
4. Per-process half done on lane/host9 (5.59). **The on-disk half is open:** heaps are separate
   processes. Measured on hbox: compiling a package's `initial` 82 ms (Place), running it from its
   packet (decode, Mini re-check, run) 10 ms, so a packet cache saves about 85%. Design points found:
   (a) the key must also name the compiler: pins are sources and replay "recompiles with the current
   compiler", so a disk cache keyed by inputs alone would serve an old binary's packet after an upgrade;
   the binary is 129 MB, too big to hash per process in Lean, so use a stamp (size and mtime of
   `IO.appPath`) as the cache's subdirectory, and say the operator removes old ones; (b) the compile
   paths are pure (`compileObject`, `compileEntryIn`, `compiledMethod`): either Session prefetches the
   keys a step will need (a `world-create`'s `buildKey`; the defs of objects the journal names, at
   open) and writes new keys after `durable`, or the cache read is an `implemented_by` memo; the
   prefetch is the clean one and misses only methods first compiled in a session; (c) `Built.laws` is
   `LawExpr`, which has no codec: add one in `Law.lean` (encode, decode, `#guard` round trip) or
   re-derive from the entry module's law lines; `Compiled` comes back from `CheckedEntry.ofPacket`
   (re-checked by Mini, so a damaged file fails closed to a compile); (d) gate it on
   `DELVETALK_COMPILE_CACHE=<dir>` (hostd's children inherit it), default off; (e) the cache dir is in
   the TCB as the binary is: a forged packet type-checks but need not be its source's.
5. **`world-open {interpretQuota: n}`** (default 48): interpretations one principal may start per clock hour,
   counted from the journal (suspended entries with `interpretation`, by principal and clock); the next is a
   journaled transient refusal, class `quota`, whose public projection carries `next: <clock>` and the message
   "interpretations: N an hour; next at clock M"; `world-status {principal}` reports the cap and the caller's
   remaining count; the opener and the clock principal are exempt. Test: the 49th prose turn in an hour
   refused, the first after the hour admitted.
6. **Deletion pass** (no deployed journal exists): the boolean `sync`; the `slot` tolerance in `receive`
   (`receiveArgument`); the `import … as Super` layer form (`stackForm`); `utteranceBlock` and pre-v3 block
   shapes; the ignored `compiled`/`binary` fields (`withoutCompiled`); the relative-address refusal; the index
   edit forms `amend {index}`/`remove {index}` (objects6 deleted them from Plan.obend); `via` beside
   `callVia` if both remain. Tests converted, replay of the test journals green, the "accepted for one
   release" sentences gone from this file. One commit.
7. **Rows as roots, the rest** (WHOLENESS §3a): per-row roots need the kernel's lazy cells (KERNEL-HANDOFF
   §15); when `fetch` lands, record `{object, field, key}` there and judge it with `keysChangedSince`.
8. **Rehearsal wall.** foundation at 6fe2740 runs the rehearsal in 32 to 36 s wall on hbox at load 14 to 50
   (host CPU 16 to 18 s); the 50 s target holds. Measure on a quiet box before quoting a number.
9. Older open items (above): forms for sum inputs held as bounds variables, handlers over nested frames,
   foreign worlds, `tests/test_bridge.py`'s stale `expectedFailure` (check it is still there).

Requests to other lanes (not the host's files):
- Kernel: (a) in-turn yields encode, hash and decode the whole checkpoint for every Plan the host answers at
  once (`Turn.conclude` -> `Checkpoint.makeFor` -> `checkpointDigest`, then `prepareResumeEntry` re-hashes and
  decodes): ~45% of host CPU in the rehearsal profile. A yielded outcome that carries the machine state and a
  lazily built checkpoint, plus a resume from that state, would remove it for every non-suspending Plan.
  (b) `CheckedEntry.apply` (Entry.lean) re-infers the quoted state argument with `ObjectiveBendTyping.infer`,
  quadratic in rows through `inferFields`' list append: ~75% of a 1000-row relation insert turn (57 ms). A
  typing derivation from `conformsUnder` (or a linear `inferFields`) would make the per-turn cost the edit's.
  (c) `Package.compileEntryFrom` compiles and runs `relations()` on every method compile; the artifact's
  `relations` lacks `limit`/`retain`, so the host compiles it once per build itself (`Built.relations`).
- Objects: World.obend's protocol may now declare `spell`, `subscribe`/`unsubscribe` (with a `Subscribed`
  sum: `subscribed {} | denied {} | refused {clause}`), `viewDerived`, `viewAt`: the host answers them
  (tests append these lines to a library copy until then).
- Measured limit: a 2,000-row relation cannot be seeded: `maxStateBytes` (262,144) counts wire JSON, about
  150 bytes a row. Decide whether the bound should count canonical CBOR (about 25 bytes a row) instead.
