# Host handoff

State on 2026-10-10 (lane/host12 89ec3cc, after the codex review of a3e1fb2; items 5.87 to 5.110).

## Summary

The host is one Lean process holding a world of durable objects. Every state change is a hash-chained journal entry (CID of canonical DAG-CBOR); memory is derived from the journal by `record`, and replay re-judges admitted entries. A reply exists only after its bytes are durable.

- Files: `spec/Delvetalk/Host/` `Store` (data, `Limits`), `Journal` (hash, chain), `Law` (law evaluator), `Slug`, `DiskCache` (the on-disk compile cache), `Ops` (pure kernel: judge, commit, record, replay, reads, `Refusal.voiced`), `Spell` (the spell grammar), `TurnLoop` (turns, the world's methods, sends, changes, suspension), `Snapshot` (CBOR snapshots, fork genesis), `Session` (journal IO, ops dispatch). `PackageSession.lean` imports Session; `spec/PackageMain.lean` is the JSON-lines driver.
- An activity yields `World.Message`s; `answer` dispatches on the method name against `worldMethods` (5.48). Write is self-only; cross-object change is `call`/`send`, judged by the callee's own law; `reprogram` and `amend` of another object are judged by the target's law.
- Only declared methods run from outside (5.62). A direct `receive` is read as a spell by the host (5.49, 5.54, 5.63); a misfit is `badSpell` with `clause`, `reason`, `hint`.
- Relations: canonical rows, keyed edits, inserts commuting and rows rebasing (5.45), `insertOnly` under retention (5.74); subscriptions deliver `changed` to typed receivers (5.50, 5.53); `viewField` field roots (5.51), `viewAt` (5.47), `viewDerived` (5.46).
- An object's pin is the CID of its sealed source closure, never a compiler output. A `fixed` State field is set at creation only (5.76).
- Laws: a text law (`law NAME "reading": EXPR`) judges every change; an optional Bend `law(old, new, request)` runs after it for kind-0 writes and may give a reading (5.67).
- Refusals are receipts with a class from `refusalClasses` (17); every `reason` is written by `Refusal.voiced` (5.75). `staleRoot`, `budget`, `evaluation`, `capacity` and `quota` are transient (a retry with the same identity runs again).
- Ops in section 2. Limits in section 4 (`Store.lean`, namespace `Limits`).
- Run: `make check` (parallel runner `tests/run.py`), `make smoke` (`test_turn_world test_chain`). Narrow: `DELVETALK_OBEND=<binary> python3 -W ignore -m tests.run test_x`. `tests/host.py` opens test journals with `sync: "none"`.
- Tests: 1,077 `def test_` across 99 files at 189b534; host11's full run on hbox passed with only the pin fixture to re-record. Wall-clock bounds (`test_snapshot` reopen under 5 s, `test_relation` under 3 s, `test_hypermedia`'s long poll) are fsync- and load-bound and can miss on a loaded box.
- Open: section 7.

## 1. Module map

Import order: Store, Journal, Law, Slug, DiskCache, Ops, Spell, TurnLoop, Snapshot, Session. Snapshot imports Ops only; Spell imports no host module.

- `Store.lean`: `Limits`, `Law`, `Compiled`, `Ledger`, `ReadPolicy`, `Program`, `Object`, `World`, `identityKey` (compressed `[principal, intent]`). Pure data.
- `Journal.lean`: `bodyHash` (CID of the body's canonical bytes), `sealEntry`, `verify height previous entry`.
- `Law.lean`: `Facts`, `Reading`, `denote`, `admits`, `refusedBy`; `#guard` tests at the bottom. Syntax is `spec/bend/Compiler/ObjectiveBendLaw.lean`.
- `Ops.lean`: edits, `Proposal`, `judge`, `commit`, `record`, `push`, creation (`compileObject`, `makeObject`, `buildObject`), `replayEntry`, `replay`, `advance`, reads.
- `DiskCache.lean`: the on-disk compile cache's reads (5.66).
- `Spell.lean`: `parse`, `bare`, `fit` and the `Clause`s of the spell grammar (5.49).
- `TurnLoop.lean`: `M` monad (`ExceptT Abort (StateM TurnState)`), `runMethod`, `drive`, `answer`, `finishTurn`, `runTurnWith`, `resumeOne`, `settle`, `deliver`, `reprogramOp`, `amendOp`.
- `Snapshot.lean`: snapshot bytes, `openContent`, fork genesis. It does IO (snapshot files).
- `Session.lean`: `Open {world, path, handle, report, sync, snapshotAt}`, `openWorld`, `durable`, `stepWorld`, `syncHandle` (extern, `spec/native/sync.c`).

Durability is fsync, not a full barrier: an entry may be lost on power loss inside the OS write-back window. The chain verifies on reopen, so a torn tail is cut, never corrupted. `world-open {sync: "none" | "fsync" | "full"}` picks the mode per process (default `fsync`; `full` = F_FULLFSYNC; anything else, a boolean too, is refused). Never journaled; `world-status` reports `sync`. `openWorld` takes an exclusive flock and refuses "journal is open in another process".

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

One JSON object per line. Common fields: `height`, `previous`, `hash`, `identity {principal, intent}`, `roots [{object, version}]`, `turn`, `request` (digest), `outcome {tag, …}`. `hash` is the CID of the canonical DAG-CBOR of the entry without `hash` (`tests/wire.py` is an independent Python encoder). Genesis `previous` is 64 zeros (`Limits.genesis`). A forked world's height-1 `previous` is the forked entry's CID (section 5.7).

`world.receipts` maps `identityKey` to the entry index (first wins, except that a suspension or a transient refusal is replaced by the identity's next entry). Transient refusals (`transientClasses`) are journaled but do not bind; admitted outcomes and every other refusal bind.

A state is named once, by the entry that wrote it: `writes[].cid`, or a created seed. `world-state-cid` answers it to a reader who may view the object.

Sources are carried once per journal: compile inputs name each module `{name, cid}`; the first entry needing a source carries it in top-level `sources [{cid, source}]` (checked against its CID on replay). Compiled packages are cached by input digest (`world.builds`, `buildKey`, `maxBuilds`), so creation and replay compile each distinct package once. Reprogram `source` fields are verbatim.

Optional top-level fields (all inside the hash): `absent [id]`, `turnRequest`, `ticksUsed`, `ledger {depth, work, storage}`, `result`, `sends [{id, to, method, argument, ledger}]`, `delivery {id, from}`, `resumes` (hash of the suspension it continues), `offers [{to, text}]`, `replyTo`, `rerun`, `ended`, `publishes`, `blocks`.

Outcomes:

- `created`: `{object, pin, sourcesSha256, compile, seed, read, chain, supervisor?, owner?}`; `roots []`, `turn 0`. Replay recompiles, requires the pin to match the source closure, the seed to conform and the amendment dry run to pass at the entry's height.
- `admitted`: `{writes [{object, version, edits, callers, kinds, cid?}], reprograms?, amendments?, creates?, grants?, revokes?, spent?}`. `kinds`: 0 write, 1 reprogram, 2 amend. Also per change, only when non-empty: `methods`, `vias`, `arguments`. Replay rebuilds the `Proposal`, checks `request == p.digest`, re-runs `judge`, and requires the recorded reprograms, amendments, creates and write versions to equal the replayed ones.
- `refused`: `{class, clause?, object?, reason?, expected?, root?, hint?, next?}`. Classes (`refusalClasses`): staleRoot, typeMismatch, capacity, absentItem, lawRefused, unknownObject, duplicateIdentity (never journaled), evaluation, budget (resource ticks, heap, stack, nodes, bytes or `law ticks`), budgetExhausted, programRefused (clause packageBytes, compile, stateType, migration, `law syntax`), requiredAbsence, keyTaken, duplicateKey, badSpell (5.49), quota (5.60), noMethod (5.62). Every `reason` is written once, at commit, by `Refusal.voiced` (5.75); a text-law refusal with a reading journals `reason: "refused <name>: <reading>"`. Replay checks only that the class is known; `publicRefusal` shows the reason.
- `suspended`: `{slot {principal, intent}, deadline, activity {object, method, argument, checkpoint {packetSha256, tokens, digest}, roots, absent, writes, sends, creates, programs, laws, ticks, awaited, awaits, offers, violation?}}` plus `request`, `ledger`, `ticksUsed`. Replay requires `digest == tokensDigest tokens` and registers it in `world.suspended`.
- `principal`: `{did, handle}`, identity `{clock, "principal:<did>:<height>"}`. `advanced`: `{from, to}`, replay requires `from == w.clock && to > from`. `settings`, `library {pin, previous, modules, law?}`, `posted`, `interpreted`, `forked`.

Cross-entry invariants (`checkDelivery`, `checkSends`, `checkResumes`):
- A `sends` id equals `deliveryId principal intent ordinal` (CID of `[principal, intent, ordinal]`).
- An entry with `delivery` consumes exactly the pending delivery it names, under the sender's principal, `intent == id`. A `budgetExhausted` refusal's reason names a ledger field that is zero (`exhaustedReason`).
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

- `Facts {subject, caller, height, turn, pin, kind, method, relations}` (`relations`: the object's declarations, for `insertOnly`, 5.74). `caller` is the object whose method wrote ("" for the turn's own method and client proposals; for a delivered turn, the sending object). `method` is the method whose run made the change ("" for ops).
- Fragment (grammar in `ObjectiveBendLaw.lean`): `and`, `or`, `not`, `implies`; `request.subject`, `request.caller`, `request.height`, `request.turn`, `request.pin`, `request.kind`, `request.method`, integer and text constants, `monotone(F)`, `writeOnce(F)`, `appendOnly(F)`, `unchanged(F)`, `x in new.F` (`member`), and for relations `insertOnly(F)`, `count(new.F) <= N`, `count(new.F) <= count(old.F) + N`, `x in new.F.COL`. `writeOnce` admits exactly one change of F away from its empty value (`emptyValue`: 0, false, "", the empty list, a record of empty values); a field missing from the old state fails closed.
- `judge` judges every distinct (caller, kind) of an object's changes. Default law `owner: request.kind == 0 or request.subject == "<creator>"`: anyone may invoke methods, only the creator may reprogram or amend (`defaultLaw`). Metarule: an amendment must be admitted by the existing law for its proposer; message "law does not admit an amendment by its proposer <p>: <name>: <expr>".
- `Object.readings` holds the package's law readings for clauses that are still the package's; `makeObject` keeps those the effective law leaves equal, an amendment keeps those it leaves equal, a reprogram keeps all. `parseLawTextReadings` reads `law NAME "reading": EXPR`; a malformed reading is `law syntax`.
- Context (`contextData`, also the Bend law's request context): `{world, object, principal, handle, caller, intent, height, clock, inputOrigin {kind, object, command, program, immediatelyPrevious, post}}` (`post`: 5.71). The host fits each Context to the receiving code's own declared record (`fitRecord`), so a field added to the library later never breaks an older object.
- Two-tier law: for an artifact with `law.present` (`Object.predicate`), after the text admits, `judge` runs `law(old, new, request)` once per distinct kind-0 change (`bendLaw`) with `request = {context, method, argument, kind, pin, reads}` (`inputOrigin.kind = "law"`). `reads` are the ids `lawReads()` returns; `commit` adds them to the roots (`withLawReads`). Runs under `Bounds.lawTicks`: `admitted`, `refused {clause}` (= `lawRefused clause`), exhaustion is class `budget` reason `law ticks`, anything else fails closed as `lawRefused law`/`lawReads`. Reprograms and amendments are the text's alone. `warmLaws` compiles `law`/`lawReads` before `judge`.
- Commutative edits: `judge` accepts a root `(id, seen)` whose object moved (`seen < version now`) when every change of `id` is a kind-0 write whose every edit is `keep`, `add`, `append`, `insert` (`EditKind.commutes`), or an `upsert`/`retract` of a relation row whose key no admitted write since `seen` touched (`keysChangedSince`, read from `writes[].edits`; a `set` or list edit of the relation touches every key), or, on a resumed turn's own object, an edit of a field later writes left alone (`movedRootAdmits`, one rule for `judge` and `resumeOne`). The entry keeps the roots as read, so `writes[].version` can be past `seen + 1`. Any other moved root is `staleRoot`. List items by bytes: `amendItem {item, change}` and `removeItem {item}` address the first item with the same canonical DAG-CBOR; none is `absentItem`.
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
- Extend: `world-reprogram {mode: "extend"}` and Plan `extend` add the source as module `Layer<n>`. The host writes `layer over ./<module below>.obend` as its first line (`layerLine`), so the kernel builds a layer stack with late binding. New pin = CID of `["extend", old pin, source CID]`; the state type must be equal under `canonicalTy` or a migration named. Tests: `test_extend`, `test_layers`.
- Supervisors: `Object.supervisor` is fixed at creation (`world-create {supervisor}`, Plan `createUnder`; `refused {clause: supervisor}` if not an object). An activity of a supervised object ends `broken` when refused `evaluation`, `budget` when a machine budget ran out, `timedOut` when a segment resumed past its deadline ends in any way. `commit` puts an `ended {id, to, method: "ended", argument, sender, ledger}` field in that entry (`endedField`, `endedId`); `record` makes it a pending delivery with argument `{receipt, how}`. A ledger refusal (`budgetExhausted`) tells nobody. Replay checks the id and that `to` is the supervisor (`checkEnded`). Test: `test_supervisors`.
- Handlers: Plan `run {object, method, argument, handler}` runs the callee as `call` does, but every Plan the callee's frame, or any frame it calls, yields is first offered to the handlers around it, innermost first, each a pure `handle(state, plan[, context]) -> Handled<R>` (`answer {response}`, or `pass` to the next one out; 5.73). The handler must be readable by the subject (`refused {clause: handler}`) and is a root. Plan `judge {edits}` answers `judged {admitted, clause}` without committing. Test: `test_handlers`.
- Held entries: `compiledMethod`/`compileDef` use `compileEntryIn` (`Package.prepareRequest` cached in `world.requests`, `Package.compileEntryFrom`); `Compiled.entry` is a decoded, checked `CheckedEntry`. Turns run `Turn.startEntry`/`resumeEntry`; pure definitions (law, `lawReads`, handler, pure methods, migrations) run `Package.executeDataEntry`. Only `initial()` at creation runs from the packet.
- Kernel integration: `world-turn {…, profile: true}` returns `profile [{kind, steps, ticks}]` (not journaled). `Turn.quoteAt` (`Turn.lean`) annotates sum-valued arguments.

### 5.4 Interpretation

- `world.interpret::<R>({utterance, offers, policy, model})` suspends like `await` with `interpretation {id, object, policy, utterance, offers, model?}` (id = hash of principal, intent, ordinal). Deadline `interpretationPatience`, resuming `timedOut`.
- `world-interpretations` lists pending items with the Policy's state as `{model, system, examples}`; `policy.system` is the Policy's pure `prompt(state, offers, utterance)` (`policyPrompt`) else its `system` field; `policy.model` is the item's `model` when non-empty (at most 128 bytes), else the Policy's.
- `world-interpretation {id, reply}` journals an `interpreted` entry and the settle pass resumes the turn. Verdicts, as `Interpreted<R>`: `proposal {object, method, argument}` (the spell fits an offered form, or a JSON `{method, argument}` for the asking object; the method is one its object offers and the argument conforms; `interpretVerdict`, `spellVerdict`, `proposalVerdict`), `replied {text}` (prose, or reply `json` not `{method, argument}` with `raw`), `unclear {needs}` (a misfit or missing fields; a failed reply gives `needs: ["model: <reason>"]`). `denied {}` when the Policy is not readable by the turn's principal (TurnLoop, `interpret`); Garden and the Directory refuse it with clause `policy`.
- Capacity: `mayWait … (interpreting := true)` counts interpretations apart. Test: `test_interpret_text`, `test_policy`.

### 5.5 Cards, offers, publish, posts

- Plan `card {object}` -> `carded {document}`: `renderCard` runs the target's card on its committed state under the turn's ticks (records a root; `denied` without read authority, `noCard`, `refused {clause: render}`). It runs `renderFor(state, context)` when the method table lists it, else `render`. `cardContext`: principal = reader, caller = asking object ("" for the op), `inputOrigin.kind` "card". `world-card {principal, object}` -> `{status: "card", text, document}`; `ownCards` `env`/`wake` resolve to `<name>/<principal>` (`resolveCard`).
- Plan `objects {prefix, after}` -> `listed {ids, more}` (ids the subject may view, byte order, `listPage`); op `world-objects`.
- `offer {to, document}` ("" = the frame's subject). An admitted entry retains `offers [{to, text}]`; `record` indexes them by addressee (`world.outbox`). `world-offers {principal, after?}` answers `offers [{height, ordinal, identity, text, from {post, principal, intent}}]` (`originOf`). A turn's reply carries only offers addressed to its own principal. A turn that offers nothing has no `offers` field.
- Reads under authority: `world-receipt {principal, identity, of?}`; `projectEntry` gives the identity's own principal the whole entry, anyone else a `publicRefusal` (`{status: "refused", class, root {object, version?}, reason?}`, plus `object` and `hint` for `unknownObject`, `object` for `requiredAbsence`) or chain fields, roots and writes of objects the reader may view, and an `elided` count. A refused turn reply carries it as `public`.
- `publish {page, section, body}` -> `published {post}` (at most `publishesPerTurn`; a title or section with a line break or over 256 bytes is `refused {clause: title}`). The admitted entry retains `publishes [{id, object, page, section, text}]` with agentwiki text (`wiki: Title\n\nbody` or `edit: Title › Section\n\nbody`). `world-publications {principal, after?, before?, reverse?, limit?}` answers `publications [{height, ordinal, id, object, page, section, body, hash, replyTo?}]`.
- `world-turn {replyTo}` (in the digest): when the parent is a post recorded for the turn's object, the entry journals `replyTo` and `World.replies` maps the post to the turn. `receive` takes `{text, post}` as sent (host10 deleted `receiveArgument`: a `slot` field is a `typeMismatch` like any other).
- Transport side: `transport/bridge.py` `publication_drafts` writes each publication as an outbox draft and never posts; `transport/post.py --record` confirms as the clock principal and calls `world-posted`.

### 5.6 Snapshots and replay

- `durable` writes `<journal>.snapshot.<height>.cbor` after the fsync when the height is `snapshotEvery` past the last snapshot written or resumed from; the reply carries `snapshot {height}` or `{refused}` (a failed snapshot refuses nothing). The newest three are kept. File: DAG-CBOR `{cid, body}`; `tests/test_snapshot.py` has an independent Python encoder.
- The body holds objects (state, `stateCid`, law text, version, read policy, ledger, compile inputs by CID, `pin`, `packet` cached), types, method tables and law shapes by pin, libraries, grants, posts, settings, `supervisor`, `minted`, `readings`; plus `clock`, `pending`, `suspended` as cross-checks. Everything `record` derives is rebuilt by `recordAll`. Sources no entry carries by CID (reprogrammed and extended modules) are kept whole (`knownByCid`).
- `openContent`: parse and hash-walk every entry (`entriesOf`), then per snapshot newest first check the CID, edition, height, `head`, derived copies, each object's version and pin against the entries (`expectedObjects`), each law reading back from its text, and that every later entry replays on it. The first failure refuses the snapshot by name and the next older is tried, then full replay.
- `install` refuses "the state of X is not its CID's" and "object X carries no state CID". Against a forger who recomputes both, `resume` compares each object with `anchoredStates` (a created or child seed, or a write's `cid`): "the state of X is not the one the journal commits to at version V". `world-open {verify: true}` replays everything and refuses each snapshot that differs from the replayed store ("it disagrees with replay at its height").
- Pins are sources. No packet digest is journaled: replay recompiles from the journaled sources with the current compiler and requires the compile to succeed, the seed to conform and the recomputed pin to equal the recorded one. `world-status.recompiledDifferently` counts objects rebuilt after a snapshot resume whose packet differs from the one the snapshot cached (`World.cachedPackets`, `noteRecompiled`).
- Suspension checkpoints are journaled as `tokenTree {depth, roots}` over content-defined blocks (`cutBlocks`: leaves 32..256 tokens, a token of 256 bytes or more its own leaf; inner nodes 2..16 names), each block once per journal as a top-level `blocks [{cid, items}]` item (`World.blocks`); an interpretation's `offers` are a one-item block (`offersBlock`). Measured on hbox at foundation 6b928f6 (132 directory suspensions, `tests/test_suspension_size.py`): median 9,392 B with blocks against 119,119 B with the v2 codec alone.

### 5.7 Slugs, fork, repository reads

- Slug (`Slug.lean` `ofCid`, `decode`): proquint of the first 32 bits of a CID's multihash digest (`lusab-babad`). Replies show receipts with `slug` beside `hash`; `world-inspect` shows `pinSlug`. `world-resolve {principal, slug}` answers `{status: "resolved", kind: receipt | pin | state, cid, receipt?}`, `{status: "ambiguous", matches, message}` or `{status: "unknown", message}` over `slugTargets`. Test: `test_slug`.
- `world-fork {principal, height?, into}` (`Session.forkWorld`; `into` must not exist) writes a new journal whose one entry is a `forked` genesis (`Snapshot.forkGenesis`): the store at `height` as a snapshot body with whole sources, only the objects `principal` may view (with grants, pending deliveries, suspended activities), the handle registry, `omitted [ids]`, `forkedFrom {world, height, cid}`. Opener, clock principal and library-law principal are `principal`. Height 1 chains to the forked entry's `cid` (`entriesOf`); replay starts from the installed genesis (`installFork`). Answers `{status: "forked", into, forkedFrom, carried, omitted}`. Test: `test_fork`.
- `world-entry {principal, hash, bytes?}` (`bytes` = hex of the canonical DAG-CBOR, identity's own principal only); `world-entries {principal, after?, before?, reverse?, limit?}` (limit 1..100); `world-object {principal, object, version?}` -> `record {object, version, pin, pinSlug, law, readings, laws [{object, version, pin, name, clause, reading?}], stateCid, library?}` as of the version (`pinAndLawAt`); `world-source`/`world-sources` -> `{cid, name, text, height}` for sources of objects the reader may view and the libraries'; `world-grants`. Test: `test_reads`.

### 5.8 Arrival

`world-arrive {principal, did, handle}` (clock principal only; the world must name an opener and have a library) records the handle as `world-principal` does, then creates each absent one of `<did>` from library module `Avatar`, `env/<did>` from `Env`, `wake/<did>` from `Wake`, as `create` by the opener with identity `arrive:<id>`, `owner: did`. Idempotent: a repeat answers `{status: "arrived", did, handle, created: []}` with no entry. Reply: `created [{object, height}]` and `principal`. A missing library module is a request error naming it. `transport/hostproc.py` `ARRIVAL` lists the packages the sealed library must hold (`Avatar`, `Env`, `Wake`; the Avatar imports `Places.obend` from the library). `docs/GENESIS.md` says when transport calls it. Test: `test_arrive`.

Items 5.43 to 5.110 follow, numbered by the lane that wrote them (5.9 to 5.42 were folded into 5.1 to 5.8).

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
   Lists.List<Decl>` (`{field, key: List<String>, limit: Nat, retain?}`; `retain` only `dropOldest`). The kernel
   evaluates the entry module's `relations()` once per package and lists it in the artifact; the host reads it from there
   (`declsOfArtifact`, host11) into `Object.relations` /
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
   `denied` without read authority. `world-inspect` lists `views` when the package declares any. World.obend's
   `viewDerived<T>` line and `Derived<T>` sum are the contract. Test: `tests/test_view_derived.py`.

47. **Past versions (host8).** Plan `viewAt {object, version}` answers `viewed {version, state}` with the state
   the object had at `version`, rebuilt by `stateAt` (Ops): the created seed (or a creating turn's), then each
   admitted write in order, its edits re-applied under the object's relations or a reprogram's recorded
   `result` taken, each checked against the write's recorded `cid`; refused `version` when the version is
   past the current one, before a fork genesis, or a rebuilt state is not the journaled one. Read authority
   as `view`; the root is recorded at the CURRENT version. Cost is linear in the object's writes up to
   `version`. Test: `tests/test_view_at.py`.

48. **The world object (host8; WHOLENESS §1, host day 1).** An activity is `Activity<R>` (artifact
   `dialect: "message"`; since kernel day 4 the three-argument `Activity<P, R, A>` and a variant Plan
   are refused at compile, and the host has no other arms) and yields `World.Message {object, method,
   argument}`. `drive` reads it with `messagePlan` into the host's internal request `answer` dispatches
   on, by method name: `write`'s argument is the running object's edits, `judge`'s the edits to judge,
   every other method's argument is that method's payload. A message whose
   `object` is not `{world: "", object: "world"}` is answered `refused {clause: notWorld}` (a message to an
   object is a `call`), a method outside `worldMethods` `refused {clause: noMethod}`; `subscribe`
   and `unsubscribe` are answered (5.50); `spell` is not a world method (5.53). The response is checked against the call
   site's type the kernel reports (`responseType`): the result sum of that protocol method in World.obend
   (`Written`, `Returned<R>`, `Interpreted<R>`, ...). A handler (`run`) sees the Message as yielded. The world has no state
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
   116 fixtures (`tests/fixtures/spells/`) through both parsers and they agree. `runTurn` sends a direct
   `receive {text, post}` to a card through `spellTurn`: the spell's card resolves (`resolveCard`) and the turn is
   retargeted to it (same principal, identity, `replyTo`); `?` answers `{status: "usage", object, text}` and
   journals nothing; the action is looked up in the card's `methodForms`; a fitting spell runs the method with
   the typed argument (text, natural, a choice as its empty-payload variant), `inputOrigin.kind = "spell"`,
   `command` the spell line; a misfit is refused, class `badSpell` (binding), with `clause`, `reason` and
   `hint` (the spell with the given fields and blanks; the usage for `noAction`/`otherCard`), all in the
   public projection. Per the root decision, a spell missing fields and a reply with no spell run `receive`
   with the bare `name: value` lines as `fields` (when `receive` declares them): completion is the card's
   policy. A reply with no spell line whose first field line names one of the card's actions or fields is
   that form's spell (the rule `Card.withBare` had in Bend). The interpretation fit and lens `set` are 5.54. Test:
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
   (KERNEL-HANDOFF §15), whose `fetch` would record each row it reads. Test: `tests/test_changes.py`
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
   field line names an offered action or field is that form's spell; prose stays `replied {text}`. Lenses: a card declares its lenses as data, `def lenses() ->
   Lists.List<Form.Field>` (name and kind), and puts through a method `set(state, input: {field: String, value:
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

60. **Interpretation quota (host9).** `world-open {interpretQuota: n}` (default 48) is journaled in the
   `settings` entry when named (as `postQuota`; a later open naming another value is refused) and kept
   in snapshots. `record` derives `World.interpretsStarted` (principal -> (clock hour, count)) from
   `suspended` entries carrying an `interpretation`, by the identity's principal at the entry's clock;
   the clock counts minutes, so the hour is `clock / 60`. An `interpret` Plan past the cap refuses the
   whole turn with class `quota` (in `refusalClasses` and `transientClasses`, so the identity runs again
   later), `reason` "the interpreter has read N this hour; reply with the spell itself, or wait." and `next: M`, both in the public
   projection. The opener and the clock principal are exempt. `world-status` reports `interpretQuota`,
   and with `principal` `interpretations: {remaining, next} | "exempt"`. `tests/test_policy.py`'s
   65-interpretation capacity test lifts the quota. Test: `tests/test_interpret_quota.py`.

61. **Deletion pass (host9).** Gone, with their tests converted: the boolean `world-open {sync}` (refused
   by name now); `stackForm` (the `import … as
   Super` layer form in old snapshots) and its test; `utteranceBlock` in `expandInterpretation`; the
   `tokenTree.relative` refusal; `withoutCompiled` (replay compares reprograms and creations as
   journaled); the index edits `amend {index}`/`remove {index}`, `amendItem`/`removeItem` by index and
   the class `outOfRange`; `via` on `call`/`send` (only `callVia`/`sendVia` name a grant). Kept then:
   `amend {item, change}`/`remove {item}` (item-addressed under the old labels; host10 deleted them,
   since no object writes them: `EditKind.amendItem`/`removeItem` only) and `withBindingContext`'s
   Context-carrying `turn-start` request, which `tests/test_layers.py` and the kernel tests send.
   `receiveArgument` went in host10 (5.65), once transport stopped sending `slot`.

62. **Declared methods (host10; WORLD-REVIEW finding 1).** A State-first definition is public only when
   the package declares it: the `action` of a form its `forms()` lists, a name its `def methods() ->
   Lists.List<String>` returns, a `views()` entry, or a conventional name (`conventionalMethods`: receive,
   render, blurb, forms, lenses, set, publishPage, page, relations, methods, law, lawReads, views,
   initial). Only the entry module's declarations count (as for `relations()`); each is compiled and run
   once per build (`publicMethods`, in `compileObject` and `prepareProgram`; a layer keeps what the code
   below declared and may add). A `methods()` that is not a `List<String>` refuses the package (`methods:`,
   clause `methods` on reprogram); a `forms()` or `views()` that does not evaluate names nothing. The
   method table marks every other row `helper: true` and the conventional-only rows `protocol: true`
   (`markHelpers`; snapshots keep the marks, edition `delvetalk.snapshot.v2`, so an older snapshot is
   refused and the journal replayed). `Object.offers`: a row not marked helper. A direct turn or a
   delivery naming a method the object does not offer (a helper, or a definition that is no method) is
   refused class `noMethod` (in `refusalClasses`, binding), reason "<id> has no method <m>; reply delvetalk <id> ? for its spells.";
   a `call`, `run`, `send` or `sendVia` naming one is answered `refused {clause: noMethod}` (an object
   may call its own helpers). Two deliveries may name a helper, because the receiving object chose the
   receiver: a change to its subscription's method (the delivery has `field`), and `ended` to the
   supervisor its sender was created under (`TurnMeta.receiver`). `world-inspect` `methods` and
   `world-objects {methods}` list only offered rows; `methodForms` (inspect `forms`, `?` usage, spells)
   lists declared rows and `receive`, not helpers or `render`/`set`/`publishPage`. Tests:
   `tests/test_public_methods.py` (the review's reproductions, a bare package, calls and sends, a helper
   receiver); fixtures declare their methods with `tests.test_turn_world.declared`.

63. **Called and delivered spells (host10).** A `receive {text, …}` to a card of the message dialect is
   read as a spell whether a principal turned it, an object called it, or a delivery brought it
   (`routeSpell` -> `SpellRoute`: `run {object, method, argument, command}`, `usage`, `refuse`, `asIs`; the
   direct path, `spellTurn`, is the same function). A direct turn goes to the card the spell names; a call
   or a delivery reads only spells naming the card it was sent to (another is `otherCard`), since its
   sender chose that object, and a `callVia`/`sendVia` is never read (its grant names one method). The
   principal reading is the frame's subject (call) or the delivery's principal. A call's misfit is
   answered `refused {clause}` with the spell's clause; a delivery's is a consumed `badSpell` refusal
   with `clause`, `reason` and `hint`. A `?` in a call or delivery runs `receive` as asked. A spell runs
   the named method only if the card offers it (5.62). Tests: `tests/test_hub.py` `SpellsPassedOn`,
   `HandedToTheDirectory`, `AnthologyReachable` (the Directory's call of the anthology's `receive`),
   `tests/test_places.py` `Scoped` (an avatar's send to a counter); their `expectedFailure`s are gone.

64. **A proposal names its card (host10; root decision).** A message-dialect object's interpretation may
   offer forms of several cards (the Directory offers its doors'). The model's spell is fitted against
   the offered forms (`spellVerdict`, which now returns the form's `card`) and the proposal checked
   against the object that card names (an id, else `resolveCard` for the asking principal): the
   method must be one it offers (5.62) and the argument fit its input. `Interpreted.proposal` carries
   `object: String`, and every verdict names it (host11 deleted the unnamed path and the
   interpretation's `named` flag: no journal from before host10 is opened). A JSON proposal `{method, argument}` is for the asking object. Test:
   `tests/test_interpret_object.py` (a hub whose World copy carries the new line proposes `g plant`
   and calls it; a form naming a method its card does not offer is `unclear`). World.obend's
   `Interpreted.proposal {object, method, argument}` and the Directory's `world.call::<Data>(...)` use it.

65. **`receiveArgument` and the old item labels deleted (host10).** `receive` takes `{text, post}` as sent;
   `amend {item}`/`remove {item}` are gone (`EditKind.amendItem`/`removeItem` only).

66. **The on-disk compile cache (host10; §7 item 1 of host9).** With `DELVETALK_COMPILE_CACHE=<dir>` in the
   host's environment (hostd's children inherit it; off by default), compiled packages (`build-<cid>.json`:
   artifact with packet, laws as text, relations, declared methods; `builtJson`/`builtOf`) and compiled
   definitions (`def-<cid>.json`: the packet; `compiledJson`/`compiledOfPacket`) are kept under
   `<dir>/<size>-<mtime sec>-<mtime nsec>` of `IO.appPath`, so another binary never reads them (the
   operator removes old stamps). Files are named by the CID of the key (`buildKey`, `defKey`) and carry
   it. Reads (`Host/DiskCache.lean`) are a memo of a pure function (`read` is `none` in the model,
   `implemented_by` a file read) at the three compile points: `compileObject` (creation, replay),
   `compileDef` and `compiledMethod`, after the world's own caches. Every packet read is decoded and
   re-checked by Mini (`CheckedEntry.ofPacket`), so a damaged file compiles again; the directory is in
   the TCB as the binary is (a forged packet that type-checks need not be its source's). Writes are
   the session's: after every op `persistCaches` writes each key the process holds that it has not
   written or seen (to a temporary name, then renamed). `world-status.compileCache {dir, hits, known}`
   (null when off). Measured on hbox (load ~17), `world-create` of Place, Garden, Directory, Thing in a
   fresh process: 300/459/265/313 ms off, 70/135/66/86 ms with a warm cache (2.1 MB on disk). Test:
   `tests/test_compile_cache.py` `DiskCache`.

67. **A Bend law's reading (host10; WORLD-REVIEW finding 8).** `law(old, new, request)` may return
   `refused {clause, reading}` as well as `refused {clause}` (`Package.lawShape` accepts both; the
   kernel lane's file, a two-line widening). A non-empty reading becomes the refusal's `reason`,
   "refused <clause>: <reading>", as a text clause's reading does, and so reaches the public projection.
   `Abi.Verdict.refused {clause, reading}` is in the prelude. Test: `tests/test_law.py`
   `test_a_bend_laws_reading_is_the_refusals_reason`.

68. **The host's default page (host10; WORLD-REVIEW finding 16).** A direct `publishPage {page}` to a card
   whose package declares no `publishPage` is the host's (`defaultPublishPage`, chosen in `runTurnWith`):
   it publishes `Card.defaultPage`'s shape, `## Card` (the card rendered for nobody, as `world-card`
   renders it for "") and `## How to reply` (the host's usage of the card's forms and lenses,
   `spellUsage`), joined by a line as `Card.pageText` joins sections, under `page`, else the word the
   pure `blurb()` gives, else the object's id; the result is the post id. The turn writes nothing and
   stages one publication. The five pasted `publishPage` methods (Anthology, Scene, Table, Tide,
   Workshop) may go (objects lane); Garden keeps its own. Test: `tests/test_publish.py` `DefaultPage`.

69. **A card's own form bounds (host10; WORLD-REVIEW finding 3).** When the entry module declares `forms()`,
   the host runs it (`declaredForms`) and its kinds override, field by field, the defaults the method's
   input type gives (`methodForms` with `declared`; `formsOf`, `spellForms`, `spellFormsData`): a
   spell is judged by the card's bounds (text min and max, natural range, choice set), and
   `world-inspect` `forms`, the `inspect` Plan and `?` usage show them. A field no form names keeps its
   type's kind. `Form.Kind.source` (any payload) reads as text of 1 to `Limits.formSourceMax` 16,384
   characters, for Bend source; a `source` field the spell lacks takes the reply's first ```obend
   fenced block (`firstFence`, `withFence`), under the same bound, so a block and a fence are one
   value. A choice is passed as a word and read against the method's input (`spellArgumentFor`,
   `inputWords`): the case of a closed sum there, text where the field is a `String`. Form.obend's
   `Kind.source` and the Workshop's `form check`/`form propose` (`source: source`, the kernel's
   form-block kind since kernel8) declare it. Tests:
   `tests/test_form_bounds.py` (a 6 KB block admitted, 20 KB refused `badValue` naming `source`, a
   fence filling `source`, a declared text bound), `tests/test_hub.py`, `tests/test_hypermedia.py`
   (the garden's declared choice and 1..80 seed).

70. **Suspension fields by block (host10).** A suspended activity's `argument` journals each text of
   256 bytes or more as a one-item block of the string (`hoistLabels`: `{tag: "labelBlock", cid}`), which
   is the same block as the checkpoint's leaf for that text (a token of 256 bytes or more is its own
   leaf), so a reply's text is journaled once whether the argument or the machine holds it;
   `activityArgument` restores it (`lowerLabels`; an entry's whole `argumentBlock` is read too). An
   interpretation whose `utterance` is the argument's `text` journals `utteranceIsText: true` instead;
   another long utterance is an `utteranceBlock` (`blockField`, `unblockField`; `offersBlock` as before).
   `expandInterpretation` now takes the suspended entry's `outcome`. A fork's genesis carries both
   restored. Measured on hbox, the offline rehearsal journal (55 directory suspensions): median
   suspended entry 8,725 B with only argument and utterance blocked whole, 7,615 B with texts shared
   with the checkpoint (foundation 5f3eddd: 10.1 KB); journal 2.57 MB. What remains is the kernel's
   checkpoint blocks (median 4.7 KB fresh per entry) and the `tokenTree` roots (~1 KB); the 7 KB target
   needs the kernel's share.

71. **`inputOrigin.post` (host11; from the objects lane).** The post a turn came from: a frame asked
   `receive {text, post}` has that `post` (`heardPost`), kept when the host reads the reply as a spell
   (`TurnRequest.post`, set by `spellTurn` and `deliverOne`; the called path passes it to `runMethod`), so
   the spell's method, which no longer sees `{text, post}`, sees it; a called frame otherwise inherits its
   caller's (`TurnState.post`, restored after the call), and a delivered `receive` brings its own. It is
   the reply's own post, not `replyTo` (its parent, which `awaitPost` matches against the post a turn
   awaits). Handle and view contexts carry the frame's; a card render's and a Bend law's are "". A
   suspended activity journals `post`, and `origin`/`command` when the turn was a spell, so a call after
   the resumption and a stale re-run (`resumeOne`) see the same Context. `Abi.Origin` gains `post:
   String` (fitted, so an older library's Origin without it runs unchanged). A `receive` argument with a
   field its card's `receive` input lacks (with or without the host's `fields`) is not read as a spell
   (`heardFits`): `receive` runs as asked and is refused `typeMismatch`, so a forged `who` beside a spell
   no longer runs the spell. The Garden reads `context.inputOrigin.post` for its planting post. Not carried: a delivery's post from the sending
   turn (only its own `receive` argument's); `sends` journal no post. Test: `tests/test_input_post.py`.

72. **A suspension journals what it does not already say (host11; §7 item 2 of host10).** The
   journaled checkpoint drops `object`, `principal` and `intent` when they are the activity's object
   and the entry's identity, and its `digest`, which `expandSuspended` (Ops; replay, resumption, fork)
   derives again from them, `packetSha256`, `rootsDigest` and the tokens (an older entry's journaled
   digest is still checked). The activity leaves out every empty or zero field but `ticks` (`absent`,
   `writes`, `sends`, `creates`, `programs`, `laws`, `grants`, `offers`, `awaits`, `checks`, `caller`,
   …; `activityArray`/`activityNat` read them back) and its `roots`, which were always the entry's
   (an older activity's own roots are read first). Measured on hbox (`tests/test_suspension_size.py`):
   one speaker's median 5,532 -> 5,092 B, nine speakers' 7,940 -> 7,500 B. What is left of the host's:
   `slot` beside an interpretation (its id again, ~100 B; `slot` is read in five places), `request`
   and `turnRequest` (two digests, both checked), the argument (~300 B). The rest is the kernel's: the
   fresh checkpoint blocks (3 KB for one speaker, more for nine) and the `tokenTree` roots (~900 B).

73. **Handlers over nested frames (host11; §7 item 3 of host10).** A `run` installs its handler for its
   whole extent: every frame at the callee's depth or deeper until the `run` returns
   (`TurnState.handlers`, innermost first). `drive` offers a yielded Plan to each handler around the
   frame in turn; the first `answer` is the response, a `pass` (or a plan the handler's input does not
   name) goes to the next one out, and the host answers what all passed. Activities need nothing more:
   only a top frame suspends (an await in a call is refused), and a `run` callee is never the top.
   A frame offers the `World.Message` it yields: a handler's `handle` takes `World.Message` and answers
   with the result the site's protocol method types (`written {}` for `write`).
   Test: `tests/test_handlers.py` (a sandbox answers the write of a frame its callee calls; an inner
   `views` handler passes a write to the `sandbox` around it; the same in the message dialect).

74. **`insertOnly` under retention (host11; RELATIONAL §12, WORLD-REVIEW finding 10's trap).**
   `insertOnly(F)` means: no admitted write retracts or alters a row of F; a row the declared retention
   dropped does not count. `Law.Facts.relations` carries the object's declarations (`judge` passes the
   code's `relations`); an old row missing from the new relation is a retention drop when the relation
   is full (`RelDecl.cap`) and the row's key sorts before every kept key (`retentionDropped`, by
   canonical key bytes, `Law.bytesLt`, which `canonicalRows` now shares). An altered row keeps its key,
   so it still refuses; so does a retraction from a relation that is not full. Without a declaration
   (a field that is no relation) the rule is as before. `#guard`s in `Law.lean`; test:
   `tests/test_relation.py` `test_insert_only_does_not_count_the_rows_retention_drops` (limit 2, three
   inserts admitted, an upsert and a retract of a kept row refused). The Directory's `greeted` is `law greeted "...": insertOnly(greeted)`.

75. **Refusal reasons in the town's voice (host11; docs/VOICE.md "The host's refusals").** `commit`
   journals every refusal through `Refusal.voiced` (Ops), which writes `reason` from what the refusal
   names, by class: staleRoot, budget, capacity (a limit's name; a sentence a site wrote stays),
   typeMismatch (the method from `expected`; a word naming no case keeps its "… is one of: …"),
   unknownObject, programRefused (the voiced sentence, then the compiler's or migration's diagnostic after a
   colon), absentItem, requiredAbsence, keyTaken, duplicateKey,
   budgetExhausted; evaluation drops the kernel's `turn refused: ` prefix; lawRefused, quota, noMethod
   and badSpell keep the reason their site writes, now VOICE's text. `duplicateIdentity`'s reply
   carries `reason`. The badSpell reasons (Spell.lean, `castSpell`, `lensSpell`) and the two usage
   lines (`spellUsage`) are VOICE's; an unknown field names the fields the spell takes ("none" for a
   form without fields). Clause names and classes are unchanged. `world/lib/Spell.obend`'s no-line
   reason moved with the host's, for `tests/test_spell.py` `BendReading`'s parity (pins re-recorded).
   Tests and `tests/fixtures/spells/` updated to the new text.

76. **Fixed State fields (host11; kernel9).** The artifact lists an entry's `fixed` State fields;
   `makeObject` and `prepareProgram` keep them as `Object.fixed` (snapshots carry them). The creating
   seed and `initial()` set them, as the kernel says; no edit can. `declaredLenses` drops them, so `?`
   usage offers no lens for one; `delvetalk <card> set` naming one is refused `badSpell` clause
   `fixed` ("<f> is fixed; it is set when <card> is made and never after."), also when it is the
   card's only lens; `world-inspect` answers `fixed: [names]` when there are any, for transport's
   actions. Forms are method inputs and are not filtered. Test: `tests/test_spell_turns.py`
   `FixedFields`.

77. **A refused call says why (host11; rehearsal run 11 finding 3).** A `call`/`callVia` refused by the
   host answers `refused {clause, reading}` where the call site's result has `reading` (World's
   `Returned`, the objects lane's line), else `refused {clause}` as before (`refusedReading`). The
   reading is the refusal's voiced reason (`callReading` over `Refusal.voiced`): a spell's badSpell
   reason, `noMethodReason`, unknownObject's and typeMismatch's sentences; a grant clause says "no
   grant lets this call run <m> on <id> (<clause>).". Test: `tests/test_call_reading.py`.

78. **Declarations from the artifact (host11).** Whether an entry module declares `forms`, `views`,
   `lenses`, `blurb` (and, for `publicMethods`, `methods`) is read only from the artifact's `declares:
   [names]` (the kernel's `declaredNames`, derived definitions included; `Object.declares`, in
   snapshots): a package with form blocks and no hand-written `forms()` has public, bounded actions.
   The source scan is gone. Test: `tests/test_form_bounds.py` `DerivedForms`.

79. **No write or migration moves a fixed field (host11).** `judge` refuses an admitted-to-be write
   (a `world-propose`'s edits, which the kernel never sees) that changes a field of `Object.fixed`:
   class `lawRefused`, clause `fixed`, reason "refused fixed: <f> is fixed; it is set when <id> is
   made and never after." (`movedFixed`, by canonical bytes). A reprogram whose migration changes a
   field the new code fixes is refused `programRefused`, clause `fixed`. Tests:
   `tests/test_spell_turns.py` `FixedFields`, `tests/test_appointments.py` (its marker gone).

80. **Usage and hints as the speaker reads them (host11; rehearsal run 11 finding 5).** `castSpell`
   speaks the card as the speaker wrote it (`env`, never `env/<did>`, though the turn runs on the
   resolved id) in usage, templates and reasons, and `lensSpell` likewise. A misfit's hint is the
   spell with a blank where the value did not fit (`blankedTemplate`; what fitted stays). An
   unknown card's hint is the answering card's usage, or, when it has no spells, "no card named
   <card>; reply to the directory for the doors". Usage lists only the forms whose method the
   speaker's law admits (`usageForms` over `methodAdmits`); a spell for another is still fitted and
   the commit refuses it. Env's `mention` still shows: its law admits anyone and its `methods()`
   lists it (the objects lane's to drop). Test: `tests/test_usage_voice.py`.

81. **Views are no spells (host11; rehearsal run 11 finding 6).** `spellFormsData` leaves out the
   package's `views()` entries, so `?` usage, spell fitting and `world-inspect`'s `forms` never offer
   one (`garden byColour`); `viewDerived` still answers it, and the method table still lists it.
   Test: `tests/test_usage_voice.py`.

82. **A typeMismatch's form is the card's (host11).** `expected.form` takes the card's declared bounds
   (`declaredForms`, as the spell path does), so the receipt's hint and the front's `_actions` agree
   (the Garden's `seed` 1..80, not the type's 0..1400). `expected` is built only for a refusal
   (`expectedNow`). Test: `tests/test_form_bounds.py` `ExpectedForm`.

83. **Public but unoffered methods (host11).** A `methods()` entry written `~name` makes `name` public
   (any turn, call or delivery its law admits may run it) but offered to nobody: its row is marked
   `unoffered: true` (`markHelpers`; a layer keeps it, `declaredRows`), and `isActionRow` and
   `offeredRows` leave it out of `?` usage, `forms`, the spell fitter, `world-inspect`'s `methods`
   and `world-objects {methods}`, so transport's `_actions` never show it. For a method a bridge or
   another object calls (Env's `mention`; the objects lane writes `~mention`). Test:
   `tests/test_public_methods.py` `Unoffered`.

84. **A refused run says why (host11).** The `run` arm's refusals answer `refused {clause, reading}`
   as `call`'s do (5.77): `handler` ("no handler <h> that you may see; …"), unknownObject, noMethod,
   typeMismatch; so World.obend's `Ran<R>` may fold back into `Returned<R>` (objects lane). Test:
   `tests/test_call_reading.py` `test_a_refused_run_says_why` (a World copy with `run -> Returned<R>`).

85. **A newcomer's Wake hears `arrived` (host11).** `world-arrive` (`arriveWith`, TurnLoop, over
   `arriveOp`): when this arrival made `wake/<did>` and its package declares `arrived` (in `methods()`,
   `~arrived` too, or as a form), the host runs `arrived {}` on it as an ordinary turn of the newcomer
   (principal and subject the DID, intent `arrive-<did>`), journaled as any turn and settled in the
   same `durable` write; the reply carries it as `arrivedTurn`. A Wake without `arrived` is unchanged;
   a second arrival makes nothing and runs nothing. Test: `tests/test_arrive.py` `Arrived` (a fixture
   Wake subscribing to a garden's field; the garden's next write owes the wake a change, before and
   after a reopen).

86. **`world-create {law}` (host11).** A non-empty `law` is the object's law text from creation, in
   `world-amend`'s grammar with its readings (`makeObject`'s `lawText`), replacing the package's and the
   default law; the creating principal must still be able to amend it (the metarule). A malformed
   law is a request error "law syntax: …" and creates nothing. The created outcome journals `law`
   and replay builds the object with it. `deploy/genesis.py` creates the cistern with
   `Cistern.lawText` this way instead of amending it in. Tests: `tests/test_law.py`
   `LawAtCreation`, `tests/test_genesis.py`.

87. **A settling pass shows others' turns as their projection (host12; codex host 1).** The turns a
   settling pass ran (`resumed`, `delivered`) and `world-deliver`'s `receipts` are shown as the op's
   `principal` may see them (`settledFor`, TurnLoop; `durable` takes the reader): the turn's own
   principal gets the reply whole but for `offers`; anyone else gets `status`, the receipt's
   `projectEntry`, and `public`/`rerunOf`, never `result`, `ticksUsed`, `resumes` or offers. An op without
   a principal (a bare `world-advance`) reads as nobody. Tests: `tests/test_await.py`
   `test_a_settling_turn_sees_another_principals_resumption_only_as_its_projection`; the tests that read
   another's resumed `result` read it with `world-receipt` as its principal (`tests.host.whole`).

88. **No default page of a private card (host12; codex host 2).** `defaultPublishPage` refuses a card
   whose read policy is not public, class `noMethod` ("<id> is not public, so the host makes no page of
   it; …"), whoever asks: the page goes to `world-publications`, which every reader lists. A package's own
   `publishPage` decides for itself. Test: `tests/test_publish.py`
   `test_a_card_only_some_may_read_gets_no_default_page`.

89. **A Bend law reads only what its subject may view (host12; codex host 3).** `bendLaw` supplies an
   object `lawReads()` names only when that object's read policy permits the judgment's subject (the
   principal, or a grant's grantor); otherwise the write is refused `lawRefused`, clause `lawReads`,
   "refused lawReads: the law of <id> reads <r>, which you may not see.", since the verdict could
   disclose the state. Test: `tests/test_law.py` `test_a_bend_law_is_given_no_object_its_subject_may_not_view`.

90. **A snapshot's laws are the journal's (host12; codex host 7).** A `world-create`'s `created`
   outcome journals `lawText`, the law the object starts with as it holds it (package, default or
   given; replay refuses an object built with another). `Snapshot.expectedLaws` derives each object's
   law from the entries (a fork genesis's, a creation's `lawText` or a creating turn's `law`, each
   amendment's `new`) and `resume` refuses a snapshot holding another: "the law of <id> is not the
   journal's", so a forger who rewrites a law and recomputes the CID gets a full replay. A creation from
   before host12 journals no `lawText` and is not compared. Test: `tests/test_snapshot.py`
   `test_a_snapshot_whose_law_is_not_the_journals_is_refused`.

91. **A supervisor offers `ended` (host12; codex host 6).** A `createUnder` naming another object
   than the creator as supervisor is refused `supervisor` unless that object offers `ended` (in
   `methods()`, `~ended` too); `world-create {supervisor}` likewise is a request error "supervisor <s>
   does not take ended: …". The creator chose the supervisor, so only one that took `ended` (or the
   creator itself) is told; the delivery's helper exemption (5.62) stands for those. Test:
   `tests/test_supervisors.py` `test_a_supervisor_must_offer_ended`.

92. **A fixed field stays fixed (host12; codex host 5, docs 1).** A reprogram whose new code does not
   fix every field the object fixes now is refused `programRefused`, clause `fixed` ("<f> is fixed; it
   is set when <id> is made and never after, so the new code must keep it fixed"), with or without a
   migration; the migration check (5.79) runs after canonicalization, on the state as it will be held.
   Test: `tests/test_spell_turns.py` `test_a_reprogram_cannot_unfix_a_fixed_field`.

93. **`proposed`, request kind 3 (host12; root decision on codex objects 1-8).** A state write no
   method of the object made is judged with `request.kind == 3` instead of 0: a `world-propose`'s
   writes (`parseWrites`, journaled `kinds: [3]`), and the state a reprogram's migration makes (judged
   once more, as kind 3, beside the reprogram's kind 1, by the text law; the old code's Bend law does
   not read the new type). So every law that admits `request.kind == 0` (the default law, the town's
   `owner` clauses) admits only the object's own method writes; a law that wants proposals says
   `request.kind == 3`. The Bend law runs for kinds 0 and 3, its `request.kind` saying which. The
   conflict index, commuting and subscription changes treat a kind-3 write as edits, as a kind-0 one
   (`Law.editKind`). `Law.kindNames` (`write` 0, `reprogram` 1, `amend` 2, `proposed` 3) is
   `world-inspect`'s `requestKinds`. The law grammar reads the number now; the name `proposed` (and the
   other three) waits on the kernel's line in `Compiler/ObjectiveBendLaw.lean`. Caution: a clause
   written `request.kind == 0 implies X` no longer constrains proposals (Deal's `members`; the
   objects lane's, `tests/test_deal.py` marker). Tests: `tests/test_law.py` `Proposed`; `test_world`,
   `test_authority`, `test_places` updated (a stranger's proposal is the owner clause's to refuse).

94. **Law reads within the root bound (host12; codex host 4).** `commit` adds the objects the written
   objects' `lawReads()` name to the roots only when the total (object and field roots) stays within
   `Limits.maxRoots`, the bound replay's `parseRoots` holds every entry to; past it the turn is refused
   `capacity` ("maxRoots") on the roots it read itself, so no admitted entry is one replay refuses.
   Test: `tests/test_law.py` `test_a_law_reading_too_many_objects_is_refused_capacity_and_the_journal_replays`.

95. **Retention evictions are facts of the write (host12; codex host 8, 10).** `applyEditsEvicting`
   returns, beside the state, the rows the declared retention dropped to make room for an insert or
   upsert (`canonicalRowsDropping`). `judge` gives them to the law as `Law.Facts.evicted`, and
   `insertOnly` exempts exactly those rows (5.74's inference from a full relation and key order is
   gone: retract-then-insert into a full relation is refused). The admitted write journals their keys
   as `evicted: [{field, key}]` when there are any (replay re-derives and compares them), and
   `touchesOf` indexes each as a `retract` of its key, so a waiting upsert or retract of an evicted key
   is `staleRoot` and re-run. Tests: `tests/test_relation.py`
   `test_insert_only_counts_a_proposed_retraction_from_a_full_relation`,
   `test_a_retract_of_a_key_retention_evicted_meanwhile_is_stale`; `#guard`s in `Law.lean`.

96. **Creations spend storage (host12; codex host 9).** `commit` hands `onAdmit` the created objects
   beside the updated ones, so `childLedger` lowers the storage a turn's sends and changes inherit by
   each created object's whole state as well as by its writes' growth; a factory chain cannot allocate
   past its ledger. Replay re-derives the changes owed with the same updates and creations (a fix after
   the playtest: replay passed the updates alone, so every turn that created an object and owed a
   change, a planting watched by a Wake, refused a restart at its height). Tests:
   `tests/test_deliveries.py` `test_a_created_child_spends_the_storage_its_sends_inherit`,
   `tests/test_arrive.py` `test_a_world_with_an_arrival_a_subscription_and_a_change_reopens_as_written`.

97. **`inspect` and `subscribe` read roots (host12; codex host 11).** The `inspect` Plan records the
   inspected object as a root at its version, so a turn that inspected, waited and commits after the
   object moved (a reprogram, a write) is `staleRoot` and re-run; `subscribe` records a field root on
   the subscribed field (as `viewField`), so a waiting subscription is stale after a write or a
   migration of that field and not after another field's. Tests: `tests/test_changes.py`
   `test_an_inspected_object_is_a_root_of_the_turn`, `test_a_subscription_reads_its_field`.

98. **A direct turn keeps the card's declared bounds (host12; codex host 12, agent 3).** After the type
   check, a direct turn's argument is judged against the form the card's `forms()` declares for the
   method (`declaredMisfit`, by `Spell.judge`: a text's length, a natural's range, a choice's options,
   a word or the case a sum field took); a misfit is refused `typeMismatch` with the spell path's reason
   ("seed takes 1 to 80 characters; reply delvetalk garden ? …") and `expected.form`. Fields no form
   declares keep their type's freedom; calls and deliveries are not judged (their sender is an object).
   Tests: `tests/test_form_bounds.py` `test_a_direct_turn_is_held_to_the_declared_bounds`;
   `test_places` (an `until` of 0) and `test_wakes` (a pour of 21) now meet the host's refusal first.

99. **A retry before the spell is read (host12; codex host 13).** `runTurn` answers a direct turn from
   its identity (`retainedTurn`) before routing it as a spell, so an identical retry after a reprogram
   that changed what the words route to gets the retained receipt, not `duplicateIdentity` against the
   new route's proposal. Test: `tests/test_spell_turns.py`
   `test_an_unchanged_spell_retry_after_a_reprogram_is_the_retained_receipt`.

100. **An exhausted `lawReads()` is budget (host12; codex host 14).** `lawReadsOf` keeps the kernel's
   `budget` apart from a failure, and `bendLaw` refuses it class `budget` ("law ticks"), transient as
   the Bend law's own exhaustion is, so a retry after the program is fixed runs again; any other
   failure stays `lawRefused`, clause `lawReads`. Test: `tests/test_law.py`
   `test_an_exhausted_law_reads_is_transient_budget`.

101. **A resumed spell stays a spell (host12; codex host 15).** `resumeSegment` restores `origin` and
   `command` beside `post` from the journaled activity, so an activity that suspends again journals
   them again and its stale re-run (`resumeOne`) runs with `inputOrigin.kind = "spell"`. Test:
   `tests/test_input_post.py` `test_a_second_suspension_keeps_the_spells_origin`.

102. **An extension's pin is its closure's (host12; codex docs 2).** `prepareProgram` pins an extension
   by the compiled closure's `sourcesSha256`, as every other package: the extended code's modules, the
   layer and the library it compiled against now. (It hashed the old pin and the layer text, so the
   same layer over the same base under two libraries had one pin for two closures.) Replay re-derives
   `newPin` through the same function. The prepared-program cache (`programKey`) now names the
   world's current library too: it served the first library's compile to a later reprogram under
   another (the test found it). Test: `tests/test_extend.py` `ExtensionPins`.

103. **One per-reader action filter (host12; codex agent 11).** `offeredTo w id o reader` decides
   which actions usage (`?`, the noAction hint), `world-inspect`'s `forms` and the `inspect` Plan's
   `methods` show a reader: the law admits them on the state as it stands (`methodAdmits` now judges
   clauses that read the state too, on old = new = the current state: the Anthology's `request.subject
   == new.owner or (… "submit")` hides `admit` from strangers), and the card's own `def actions(state,
   context) -> List<String>`, when it has one, lists it (for guards a method keeps in Bend: the Bell's
   planter-only `door`; the objects lane adds them). `receive` always stands; lenses show only when
   `set` is offered. A spell for another action is still fitted and the commit judges it.
   `readerActions` compiles `actions` through `compileDef` (the world's or the disk cache; not warmed
   yet, a follow-up if it shows in timing). Tests: `tests/test_usage_voice.py` `ReaderActions`;
   `test_lenses` (a stranger sees none of the owner's policy), `test_inspect_reads` (`cap` on count 3).

104. **A refused reprogram or amendment says what to correct (host12; codex agent 12).** The
   `reprogram`/`extend`/`amend` Plans answer `refused {clause, reading}` (`refusedReading`) where
   the call site's result has `reading`, else `refused {clause}` as before. The reading is the
   refusal's voiced reason, the compiler's or migration's diagnostic included (`dryChange` returns it
   beside the clause); a migration the package does not define is named ("the package defines no
   <m>; a migration is def <m>(old: OldState) -> State"). World.obend's `Programmed` and `Amended`
   carry `refused: {clause, reading}` (host12's two-line shape change; `tests/fixtures/pins`
   re-recorded); the Workshop shows `r.reading` (objects lane). Test: `tests/test_extend.py`
   `ReprogramReading`.

105. **One name rule for objects and spells (host12; codex agent 14, docs 5).** `Limits.nameAlphabet`
   (ASCII letters, digits and `- : / . _`) and `maxObjectIdBytes` (128) are both `validObjectId`'s
   rule and the spell grammar's card name (`Spell.isCardName`, which imports it), and
   `world/lib/Spell.obend`'s `cardAlphabet()` is the same string: every id a creation takes can be
   spelled (`delvetalk Coin_box drop`, `delvetalk My_card ?`). A card name is at most 128 bytes (it
   was 160, longer than any id). Spell fixtures re-recorded where the answer moved (four rows: a
   capital, an underscore, the old length bound); `tests/fixtures/pins` re-recorded. Tests:
   `tests/test_usage_voice.py` `test_a_card_named_as_any_object_may_be_is_spelled_by_that_name`,
   `tests/test_spell.py` `test_the_longest_card_name_is_128_bytes`.

106. **Several spells in one interpretation (host12; docs/MENU.md §2.2).** `interpretVerdict` splits the
   model's text at each line beginning `delvetalk` at the margin (`spellSegments`; prose before the
   first is dropped). With more than one, each of the first `Limits.spellsPerReply` (3) is fitted and
   checked as a single spell is (`spellVerdict`, `proposalVerdict`) and the verdict is `proposals
   {items}`, in order, each `{tag: proposal, object, method, argument}` or `{tag: unclear, reasons}`;
   the Plan hears `proposals {items: List<Proposed<R>>}` (`proposedData`). One spell keeps the single
   `proposal`/`unclear`; an object whose Response has no `proposals` arm hears the first item. Replay
   accepts the tag. World.obend's `sum Proposed<R>` and the `proposals` arm of `Interpreted<R>` are the
   objects lane's lines (lane/objects12): `sum Proposed<R>: proposal: {object: String, method: String,
   argument: R}; unclear: {reasons: Document.Names}` and `proposals: {items: Lists.List<Proposed<R>>}`.
   Zero extra model calls. Test: `tests/test_interpret_object.py` `SeveralSpells` (a World copy with the
   lines; two spells and a misfit, the second garden planting, a replay).

107. **Posting reservations and model retries as host facts (host12; codex transport 9, 10; built as
   designed, with the root's change: the quota is per source).** Python keeps custody (credentials, the network, the record key it fixes) and
   decides nothing; every decision below is a journaled entry keyed by intent, so a restart, a second
   process or a replay reaches the same answer. Clock units are the world clock's (`world-advance`;
   an hour is 60, as `interpretQuota` counts).

   *Posting (transport 9).* `world-post-reserve {principal: clock, intent, source}` admits one post of
   `intent`; a `source: "delve"` post counts against `postQuota` (journaled, per clock hour) and past
   it is refused `{status: refused, class: quota, next}` naming the clock at which a slot frees (no
   entry: the count is the journal's); any other source (`zulip`) reserves without a count and is never
   refused (delve.town's etiquette; Zulip has none); it journals `reserved {intent, hour}` under identity `(clock, "post:"+intent)`,
   so a retry of the same intent returns the same reservation and takes no second slot. The count is
   the hour's reservations minus its releases, never wall time or a directory. `world-post-release
   {principal: clock, intent, reason}` journals `released` for a reservation whose post certainly did
   not leave (credentials unreadable, the request refused before the network); a slot is never given
   back for an ambiguous network failure, which the transport retries under its fixed record key.
   `world-posted {…, intent}` (the existing op, gaining `intent`) settles the reservation: a
   `posted` entry naming a reserved intent is that post's outcome, and posting without a reservation
   is refused by name, "a post settles a reservation; name its intent" (transport reserves every live
   post; the host suites post through `tests.host.posted`, which reserves under a test source first). A released intent is reserved anew under `post:<intent>/<round>`.
   The welcome command and the hand read the quota through `world-status.posts {hour, sources:
   [{source, used, quota?, next?}]}` (`delve` always listed, with `quota` and `next`) and reserve before
   sending; `transport/post.py`'s `take_slot` and `post-log.json` go. Replay re-checks a reservation's
   hour and quota and a release's standing reservation.

   *Model retries (transport 10).* `world-interpretation {id, reply}` takes every transport result
   verbatim, failures included, and the host decides: a `failed` reply whose `reason` is transient
   (`transport`, `rate`; the host's list) under `Limits.interpretAttempts` (8) journals `attempted
   {id, attempt, reason, next}` (`next` = clock + 2^(attempt-1), at most 60) and answers `{status:
   "retrying", attempt, next}`; the activity stays suspended. Any other reply, or the attempt past the
   limit, is the verdict as today (`unclear {needs: ["model: <reason>"]}`). `world-interpretations`
   lists each pending item with `attempts` and `next` (null when it may be asked now), and the
   interpreter asks only items whose `next` has passed; its receipt files and `MAX_ATTEMPTS`/`BACKOFF`
   go (it may keep a cache of a reply it could not submit, keyed by id, and resubmit it verbatim).
   Built as written: `attempted` entries are keyed `(interpretation, "<id>/attempt/<n>")`, replay
   checks their order, `World.attempts` holds `(n, next)`. Tests: `tests/test_post_reserve.py`
   (`Reservations`, `Retries`); `test_policy` and `test_reflection` now fail a reply with a reason the
   host does not retry. The principal's `interpretQuota` is spent once, when the interpretation starts
   (`interpretsStarted`); retries spend none of it, and the `attempted` entries are the record of model
   credit spent.

108. **State bytes are canonical bytes (host12; OBJECTS-HANDOFF §4).** `stateBytes`, which
   `Limits.maxStateBytes` and `maxSeedBytes` (256 KiB), the storage ledger and the creation charge
   count, is the length of the Data's canonical DAG-CBOR (`Delvetalk.Canonical.encode`), not of its wire
   JSON (about 150 B of tags and names per relation row: the Anthology refused its 631st short line).
   `world-inspect` answers `stateBytes`. Measured on hbox, a Bell with 2,048 rains (a 32-byte DID
   author, a 19-byte handle, `at` and `n` four digits) is 216,899 B with 20-character texts, about
   86 B per row plus the text; at 60 characters 2,048 rows exceed the bound (about 297 KB), and at the
   rain form's 280 at most about 716 rows fit. So a relation's `limit` must satisfy limit × (86 + its
   widest text) ≤ 262,144 for the object to stay writable when full (retention cannot drop below the
   byte bound): for the Bell 640 rows (worst case 234 KB), or 2,048 with a 40-character text. The
   statement FOUNDATION's scale section should make: "a relation's declared limit times its widest row
   fits in 256 KiB; the lazy cells (KERNEL-HANDOFF §15) are the real fix, after which the bound is
   per cell". Test: `tests/test_relation.py` `test_state_bytes_are_the_canonical_encodings` (2,048 rows
   that were 600 KB of wire JSON, created).

109. **Paging by (height, item) (host12; codex transport 12).** `pageByHeight` (`world-sources`,
   `world-grants`, `world-entries`, `world-publications`) numbers the items of each height and takes
   `cursor: "<height>.<n>"`, continuing after (or, with `reverse`, before) exactly that item; a page
   with `more` answers the `cursor` of its last item (`pageFields`). `after`/`before` keep paging by
   whole heights. `transport/repo.py` should pass the reply's `cursor` through as the XRPC cursor
   instead of the last item's height (transport lane). Test: `tests/test_reads.py`
   `test_pages_by_height_and_item_skip_nothing` (the library entry's many sources one at a time, both
   orders).

110. **hob's tail line, and inspect's laws with readings (host12; docs/VOICE.md "hob").** A direct
   turn's `?` usage and its badSpell `hint` end, after a blank line, with hob's one line
   (`hobTail`): "hob: how a spell is read: delvetalk library read / page: spells" under usage, "hob: the
   page on this: delvetalk library read / page: spells" under a hint, only when an object `library`
   exists that the speaker may view; never in the `reason`, never in a call's or delivery's reading,
   never twice. `world-inspect` answers `laws: [{name, clause, reading?}]` (`lawRows`: the reading the
   law text gives, else the package's while its clause stands) and `bendLaw` (whether a Bend
   `law(old, new, request)` judges after the text), which the library's `law {card}` page reads.
   Tests: `tests/test_usage_voice.py` `test_hobs_tail_line_follows_usage_and_hints_only_when_a_library_is_visible`,
   `tests/test_law.py` `test_inspect_answers_each_clause_with_its_reading`.

111. **`me` is the speaker's avatar (host12; docs/GROUND.md §6 change 2).** `resolveCard` reads the card
   `me` as the principal's own avatar, the object an arrival makes under the principal's own id
   (`arrivals`: the avatar is `<did>`, not `avatar/<did>`), in direct turns and spells alike, so cards
   print `delvetalk me watch / to: … / field: …`, `me move`, `me accept`, `me go`; usage and reasons
   speak `me`, never the DID. A speaker with no avatar is refused `badSpell`, clause `noAvatar`, "You have
   no avatar here yet; your first arrival in the town makes one, and then me is it." `me` joins
   `ownCards`, so no object may take the id. Test: `tests/test_arrive.py` `test_me_is_the_speakers_own_avatar`.

112. **`make`: an object from a resident's own source, with its lineage (host12; docs/GROUND.md §6
   changes 1 and 6).** The world method `make({package, seed, law, requireAbsent, madeFrom:
   Plans.MadeFrom {object, receipt}}) -> Created` is `create` (the package is Bend source starting
   `edition`, the Workshop's held, checked package; the maker's authority, the creator's library)
   with lineage: the host checks that `madeFrom.object` is an object and `madeFrom.receipt` an entry's
   hash in the journal (else `refused {clause: madeFrom, reading}`), records the object as a root, and
   journals `madeFrom {object, pin, receipt}` (the pin `object` runs now) on the created entry
   (`CreateRec.madeFrom`, `createRecJson`; replay re-derives it from the recorded create). The source
   is journaled by CID as every creation's is, and the pin is its closure's. A compile failure is
   `refused {clause: compile, reading: <the checker's diagnostic>}`: World.obend's `Created` refusal
   carries `reading` now, and `refusedWith` answers `{clause, reading: ""}` to a result shaped so
   (`Created`, `Programmed`, `Amended`). Plan.obend gains `record MadeFrom`; pins re-recorded. Test:
   `tests/test_make.py`.

113. **The host's spells: `become` (host12; docs/CATALOGUE.md §2, higher-order cards).** A spell whose
   action is one of `hostSpells` on a card that defines no form of that name is the host's
   (`SpellRoute.host`, `hostSpell`), a direct turn's only (a call or delivery naming one is refused
   `noAction`). `delvetalk <card> become / kind: <id>` lays the kind's `body` (any readable object whose
   state has a non-empty text `body`: a layer source over the card's package) over the card: a reprogram
   in extend mode by the speaker, judged by the card's own law (kind 1; the default law admits the
   creator only), journaled under the turn's identity (a retry answers the receipt) with `madeFrom
   {object: <kind>, pin, receipt: the entry that made the kind's current version}` on the reprogram
   (`Proposal.madeFrom`; replay reads it back). Refusals: `missingField`, `unknownKind`, `noBody`
   (badSpell), the law's, or `programRefused` with the compiler's diagnostic. `?` usage adds "The
   host's spells for any card" with `become` when the law would admit the speaker's reprogram
   (`kindAdmits`, as `methodAdmits` on the state as it stands). Test: `tests/test_extend.py` `HostSpells`.

114. **`adopt` (host12; docs/CATALOGUE.md §2).** `delvetalk <card> adopt / law: <id>` appends the
   named clause set to the card's law: the text `law` of a readable object (a kind, or a library page
   kept as an object with a `law` field) after the card's current text, with its readings; an
   amendment by the speaker, judged by the metarule and the card's law (kind 2), journaled under the
   turn's identity. Refusals: `missingField`, `unknownLaw`, `noLaw`, `lawClash` (a clause name the law
   already has), `law syntax`, or the law's. `?` lists it where the law would admit the speaker's
   amendment. Test: `tests/test_extend.py` `test_adopt_appends_a_kinds_clauses_under_the_amend_metarule`.

115. **`lend` (host12; docs/CATALOGUE.md §2).** `delvetalk <card> lend / to: <handle or me> / method:
   <m> / until: +<n>` is the speaker's grant: grantor the speaker, holder and object the card, `to` the
   principal the handle names in the registry (`me` the speaker; else as written), until clock now + n,
   with `reading` "lent by <handle>: <m>, until clock N" (`Grant.reading`, journaled with the grant, for
   the holder's card). Only a method the card offers and its law admits the speaker to run
   (`methodAdmits`): else `notYours` ("The law of <card> does not let you run <m>, so you cannot lend
   it."). The borrower's direct turn or spell of `m` on the card runs under the standing grant
   (`lentVia`, `TurnMeta.via`), judged with the lender as subject, until the clock passes it or it is
   revoked. `?` lists `lend` where the speaker may run some offered method. Test: `tests/test_extend.py`
   `test_lend_grants_a_method_until_a_clock_and_the_borrower_runs_it_as_the_lender`.

## 6. Gotchas

- **Replay edition (a rule).** `Limits.replayEdition` (Store.lean) is the edition of what replay
  derives; `Journal.sealEntry` writes it as `replay` on every journal's first entry (a fork's genesis
  too), `world-status` answers it, and `Snapshot.openContent` refuses a journal of another edition
  before replaying anything: "journal replay edition 1; this host is 2; a world from another host's
  edition does not reopen: make it again with a new genesis" (a journal without the field is
  edition 1). **Bump it in the same commit as any change to what replay derives or checks** (a judging
  rule, a derived index, a journaled field replay compares), and say so in the item. 2 is host12
  (evictions and changes owed as facts, lineage, reservations, attempts). Test:
  `tests/test_replay_edition.py`.

- `conformsUnder` needs the packet's bounds (`Object.bounds`, `Compiled.bounds`); bare `conforms` is only for closed non-recursive types.
- `canonicalTy` (Ops): two state types are equal when their canonical forms agree (variables renamed in order of first use, at most 4096 steps, else "type too deep to compare"). Reprogram and extend depend on it.
- Wire shapes: `world/lib/World.obend`'s `protocol world` is the contract (Plan.obend keeps the shared records: `Reference`, `Edit`, `Slot`, `Receipt`). `write`'s edits are a record with one variant per state field. `respond` picks the first payload that conforms to the call site's result type; a sum lacking the label gives "response type cannot carry <label>".
- Seeds are laid over `initial()` (`mergeSeed`): a record of some fields, `{}` for `initial()`; a field the state lacks is `typeMismatch`. A seed that does not set a text `owner` gets the named `owner`, else the creating principal (`withOwner`). `create`'s `package` is a module name in the creator's sealed chain, or source starting `edition`; `law` is used only if it starts `law `.
- Hand-built Contexts in tests must carry caller, intent and height or the method does not type.
- Lean keywords: `meta`, `from`, `seal`. Structure-instance continuation lines must be indented past the first field.
- A suspended identity has a `suspended` entry; `retained` ignores it so the final commit can reuse the identity.
- Settling runs inside `durable`, after the triggering op, and appends to the same write.
- `Handle.flush` is not durable; `sync.c` does `fflush` + `fsync` (or `F_FULLFSYNC`). One sync per `durable` call. The build needs `lakefile.lean` for `extern_lib`.
- `python3 -W error` turns leaked subprocess warnings into failures; close hosts in `tearDown`. `tests.test_replay` and `test_await` are slow because every `world-create` compiles.
- Never run an unfiltered package suite on a loop.

## 7. Open

The queue after host12 (each with who holds it and what closes it):

- **`proposed` by name** (kernel lane): `Compiler/ObjectiveBendLaw.lean` reads `request.kind ==
  write|reprogram|amend|proposed` as 0..3 (host12's report has the lines); until then laws write
  `request.kind == 3`. Closed by a `#guard` there and `tests/test_law.py` `Proposed` with the name.
- **Deal under kind 3** (objects lane): `members` reads `request.kind == 0 implies …`, so a stranger's
  proposal is no longer constrained; `tests/test_deal.py` keeps an `expectedFailure` until Deal guards
  proposals (codex objects 2, 7). Any other clause written `kind == 0 implies` has the same shape.
- **World.obend lines** (objects lane): `sum Proposed<R>` and `Interpreted.proposals` (5.106); the
  Workshop shows `refused.reading` (5.104); Bell's `door`/`undoor` need `actions(state, context)` (5.103);
  the Bell's rain limit or text bound per 5.108.
- **Transport consumes host decisions** (transport lane): `world-post-reserve`/`-release` and
  `world-posted {intent}` replace `take_slot` and `post-log.json`; the interpreter submits every model
  result and reads `attempts`/`next` (5.107); `transport/repo.py` passes the host's `cursor` (5.109).
  Then the host refuses a `world-posted` without `intent` (one line in `postedOp`).
- **`readerActions` compiles `actions` per read** (host): through the world's or the disk cache only;
  warm it as `warmLaws` warms `law` if it shows in `DELVETALK_TIMING`.
- **`methodAdmits` on the state as it stands** (host, watch): a method that moves the clause's own
  field for the speaker (an owner-on-first-use claim) is hidden from them though it would be
  admitted; none in the town does. A card with one says so in `actions()`.
- **hob's matching page** (host, with the library's pages): both tail lines name `page: spells`; a
  hint for a lens or a law clause could name `object` or `laws` once those pages exist.
- **Foreign worlds**: `Reference.world != ""` is refused `foreignWorld`.
- **`world-reprogram`/`amend`** are gated only by the object's law (and, since host12, a reprogram
  keeps every fixed field fixed, 5.92).
- **Rows as roots** (WHOLENESS §3a): blocked on the kernel's lazy cells (KERNEL-HANDOFF §15): when
  `fetch` lands, record `{object, field, key}` there and judge it with `keysChangedSince`; the lazy
  cells also lift 5.108's per-object byte bound.
- **Suspension size** (5.72): run 11's median suspension is 7.4 KB; the host's remaining share is
  ~0.5 KB (`slot` beside an interpretation, read in five places; the argument).
- **A delivery's post** (5.71): a delivered turn sees only its own `receive` argument's post, not the
  sending turn's; `sends` journal none. Add it only when an object needs it (none does).
