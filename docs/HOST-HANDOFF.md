# Host handoff

State on 2026-10-13 (lane/paintfix: 5.228, no edition change; lane/cx-world: 5.219–5.225, replay edition 14; lane/authority: 5.209–5.214, replay edition 13; lane/plan: 5.203, a plan is one turn, no edition change; host32: 5.200 to 5.202, no edition change; host31: 5.182 on, replay edition 12; host30: 5.179 to 5.181, replay edition 11; lane/host29: the second codex review's host findings, 5.175, merged with lane/kernel18's state as cells, replay edition 10 and snapshot `v5`; lane/host28: calls and sends across worlds, 5.173, the scratch REPL, 5.174; lane/host23 continued by host27: what wants a hand, what a thing stands at, a post read once, frames read their turn's writes, mentions filled, a question answered by its card, root's field set (5.164 to 5.172); host26: words a card heard are hob's (5.163); host25: the carry's moves whole (re-arm, package law and lines, the refresh call), reach as a host op (5.162); host24: carry moves with migrations and bodies, placings move no state version; lane/enchant 5.161, enchantment, no replay edition change; lane/host22 5.160, rules fire and wants pose, replay edition 9, snapshot v4; lane/host21 5.159, the carry and the no-wipe gate, replay edition 8; lane/kernel16 5.157, a card's own refusal, replay edition 8; lane/host19 from 5.153 to 5.156, replay edition 7; lane/host18 from 5.142 to 5.152, the serve status and bounds in 5.125 and section 2; lane/host17 from 5.137 to 5.141; lane/host16 5.136; lane/host14, continued by host15 through 5.128 to 5.135, on top of host14's 5.126 and 5.127, host13's 5.118 to 5.125 and host12's 5.87 to 5.117; the codex review's findings and their commits are `docs/review/codex-2026-10-10/ROUTING.md`). The queue is section 7, in order.

## Summary

The host is one Lean process holding a world of durable objects. Every state change is a journal entry naming the one before it (CID of canonical DAG-CBOR); memory is derived from the journal by `record`, and replay re-judges admitted entries. A reply exists only after its bytes are durable.

- Files: `spec/Delvetalk/Host/` `Blocks` (the block store: `Entries`, `Link`, the pure record read), `Store` (data, `Limits`), `Journal` (hash, chain), `Law` (law evaluator), `Slug`, `DiskCache` (the on-disk compile cache), `Ops` (pure kernel: judge, commit, record, replay, reads, `Refusal.voiced`), `Spell` (the spell grammar), `TurnLoop` (turns, the world's methods, sends, changes, suspension), `Snapshot` (CBOR snapshots and their indexes, opening, the store-installing geneses of a fork and a carry), `Session` (journal IO, ops dispatch), `RootEdit` (the offline tools: `root-edit`, `migrate`), `Carry` (the offline `carry`, 5.159), `Enchant` (strokes, the paint check and the render cache, 5.161). `PackageSession.lean` imports Session; `spec/PackageMain.lean` is the JSON-lines driver.
- An activity yields `World.Message`s; `answer` dispatches on the method name against `worldMethods` (5.48). Write is self-only; cross-object change is `call`/`send`, judged by the callee's own law; `reprogram` and `amend` of another object are judged by the target's law.
- Only declared methods run from outside (5.62). A direct `receive` is read as a spell by the host (5.49, 5.54, 5.63). Words that reached a card and run none of its spells, and a misfit spell, are hob's to read for that card with its table; hob's answer runs as the speaker's turn on it (5.163).
- Relations: canonical rows, keyed edits, inserts commuting and rows rebasing (5.45), `insertOnly` under retention (5.74); `viewField` field roots (5.51), `viewAt` (5.47), `viewDerived` (5.46).
- An object's pin is the CID of its sealed source closure, never a compiler output. A `fixed` State field is set at creation only (5.76).
- Laws: a text law (`law NAME "reading": EXPR`) judges every change; `request.kind` is `write` 0, `reprogram` 1, `amend` 2 or `proposed` 3, a write no method of the object made (5.93); an optional Bend `law(old, new, request)` runs after it for kinds 0 and 3 and may give a reading (5.67).
- Refusals are receipts with a class from `refusalClasses` (18, `quiet` the newest, 5.126); every `reason` is written by `Refusal.voiced` (5.75). `staleRoot`, `budget`, `evaluation`, `capacity` and `quota` are transient (a retry with the same identity runs again).
- Ops in section 2. Limits in section 4 (`Store.lean`, namespace `Limits`).
- Run: `make check` (parallel runner `tests/run.py`), `make smoke` (`test_turn_world test_chain`). Narrow: `DELVETALK_OBEND=<binary> python3 -W ignore -m tests.run test_x`. `tests/host.py` opens test journals with `sync: "none"`.
- Posting and model retries are host decisions (5.107): `world-post-reserve` counts delve.town posts against `postQuota`; a transient model failure is journaled `attempted` with a backoff. `make` creates from a resident's source with `madeFrom` lineage.
- Tests: 1,241 `def test_` across 109 files at b0f3618; no expected failures stand. Wall-clock bounds (`test_snapshot` reopen under 5 s, `test_relation` under 3 s, `test_hypermedia`'s long poll) are fsync- and load-bound and can miss on a loaded box.
- Open: section 7.

## 1. Module map

Import order: Blocks, Store, Journal, Law, Slug, DiskCache, Ops, Spell, TurnLoop, Snapshot, Root, Session; `Serve.lean` and `PackageSession.lean` sit above them, and `RootEdit`, `Carry` (which seals a library as `Serve` does) above those, for `PackageMain`. Blocks imports only `Canonical`; Snapshot imports Ops only; Spell imports only Store; Root imports TurnLoop.

- `Blocks.lean`: `Entries` (the chain in memory: every CID, each record's span, the step's unwritten entries; `get?` reads and CID-checks one record through `readAt`, a `pread` behind `implemented_by`, pure because a written record never changes), `Link` (one chain line, `Link.ofLine`), `recordBytes`.
- `Store.lean`: `Limits`, `Law`, `Compiled`, `Ledger`, `ReadPolicy`, `Program`, `Object`, `World`, `identityKey` (compressed `[principal, intent]`). Pure data.
- `Journal.lean`: `bodyHash` (CID of the body's canonical bytes), `sealEntry`, `verify height previous entry`.
- `Law.lean`: `Facts`, `Reading`, `denote`, `admits`, `refusedBy`; `#guard` tests at the bottom. Syntax is `spec/bend/Compiler/ObjectiveBendLaw.lean`.
- `Ops.lean`: edits, `Proposal`, `judge`, `commit`, `record`, `push`, creation (`compileObject`, `makeObject`, `buildObject`), `replayEntry`, `replay`, `advance`, reads.
- `DiskCache.lean`: the on-disk compile cache's reads (5.66).
- `Spell.lean`: `parse`, `bare`, `fit` and the `Clause`s of the spell grammar (5.49).
- `TurnLoop.lean`: `M` monad (`ExceptT Abort (StateM TurnState)`), `runMethod`, `drive`, `answer`, `finishTurn`, `runTurnWith`, `resumeOne`, `settle`, `deliver`, `reprogramOp`, `amendOp`.
- `Snapshot.lean`: snapshot bytes (`storeJson`, `indexJson`, `installIndex`), `openJournal`, `reopen`, `replayAll`, `resume`, `checkAnchors`, `writeJournal`, the store-installing geneses (`genesisEntry`, `forkGenesis`, `wholeSuspension`, `carriedKeys`, `installGenesis`). It does IO (the chain, the block store, snapshot files).
- `Carry.lean`: `delvetalk-obend carry` (5.159): `readWorld` (a snapshot body under `readKeys` only), `rebuilt`, `resumable`, `carryWorld`, `carryGenesis`, `main`.
- `Enchant.lean` (5.161): `Strokes` and `assemble`/`strokesAt` (a thing as exact data at a version), `verify` (the paint check, its fixtures as `#guard`s), `Cache` and the render ops. Imports TurnLoop; Session imports it.
- `Session.lean`: `Open {world, path, handle, store, report, sync, snapshotAt, every, bound, renders}`, `openWorld`, `durableIO`/`durable`, `appendJournal`, `stepWorld`, `syncHandle` (extern, `spec/native/sync.c`).
- `Root.lean`: `rootKinds`, `rootFieldsOf`, `rootOp`, `worldSettingsOp` (5.126).
- `Serve.lean` and `spec/native/serve.c`: the directory of worlds and its two sockets (5.125, 5.131). `PackageSession.lean` is the per-process session above Session.

Durability is fsync, not a full barrier: an entry may be lost on power loss inside the OS write-back window. An append writes every record to the block store and syncs it, then every link to the chain and syncs that, so a crash between leaves records no link names (bytes nothing reads). A chain whose last line is torn is refused by name (`journal broken at height N: unterminated final line`, `Snapshot.chainOf`); the host never cuts its own file. Recovery is a verified copy: `deploy/backup.sh` cuts the torn line in its mirror and replays it, `deploy/restore.sh` installs the tarball (DEPLOY "Durability and backups", "A torn tail"). `world-open {sync: "none" | "fsync" | "full"}` picks the mode per process (default `fsync`; `full` = F_FULLFSYNC; anything else, a boolean too, is refused). Never journaled; `world-status` reports `sync`. `openWorld` takes an exclusive flock and refuses "journal is open in another process".

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

- Open and status: `world-open {path, library?, principal?, libraryLaw?, sync?, verify?, snapshotEvery?, maxJournalBytes?, clock?, postQuota?, opener?}`, `world-status`, `world-snapshot`.
- Turns: `world-create`, `world-turn` (`replyTo?`, `profile?`), `world-propose`, `world-deliver {limit}`, `world-pending`, `world-reprogram {mode: replace | extend}`, `world-amend`, `world-advance {height}`, `world-revoke`, `world-interpretations`, `world-interpretation {id, reply}`.
- Reads: `world-view`, `world-receipt`, `world-history`, `world-offers`, `world-objects`, `world-card`, `world-inspect`, `world-check`, `world-state-cid`, `world-strokes`, `world-render-check`, `world-resolve`, `world-entry`, `world-entries`, `world-object`, `world-source`, `world-sources`, `world-grants`, `world-publications`, `world-reach` (5.162), `world-wanting` (5.164).
- Paint (5.161, never journaled): `world-render {principal, object, version?}`, `world-renders`, `world-render-submit {key, reply}`; `world-status.renders {cached, rejected, pending}`.
- Registry and arrival: `world-principal`, `world-arrive`, `world-posted` (`unposted: true`), `world-library`, `world-fork`.
- `serve`'s (5.140): `world-scratch {principal, name, from?}`, `world-cite {principal, scratch, receipt}`, `serve-status` (the process, its worlds and scratches, 5.125); `world-view`/`world-card`/`world-inspect` of `<world>:<object>`; the root act `expire`, and the owner's `delvetalk world expire / scratch: <name>` (a `world-turn` on `world`, method `expire`, or the spell as words: `Serve.expiryAsked`; journaled nowhere). `world-relay` and `world-cross` (5.173) are serve's own, refused on both sockets.
- Root and moderation (5.126): `world-root {principal, reason, act}`, `world-settings`. `library-load {path}` is a stateless op.
- `bounds` (stateless): `{kernel, host, refusalClasses, transientClasses}`, every `Nat` definition of `Delvetalk.Bounds` (and `Generics.maxInstances`) and of `Limits` by its name (`natsIn%`, Ops), so the front's `limits`, its module checks and the tests read the bounds rather than restate them (`tests/host.py` `bounds()`).

Rules:
- `turn` is host-assigned on propose, amend and reprogram; a client-sent `turn` is a request error.
- Every journaling op runs through `durable`: step, `settleAll` (resume what the step released, run pending deliveries oldest first, each followed by a resume pass, up to `deliveriesPerSettle`), then append all new entries with one fsync. The reply carries `resumed` and `delivered`. `world-deliver` runs what a capped pass left. `world-open` never settles.
- `world-open` seals `library` (a directory) on first open and journals it; a later open whose bytes differ is refused by name. `verify: true` replays everything and answers `snapshot {resumed, refused [{height, reason}]}`.
- `clock` (the one principal that may `world-advance` and `world-posted`) and `postQuota` (hourly post cap, default 16) are journaled in a `settings` entry on first naming; a later open with other values is refused. `opener` goes in the same entry; the opener alone may `world-create {…, owner}`.
- Reads take a principal through `readerOf`: 1..128 bytes, or `anonymous` / "" (public objects only). Object ids at creation are 1..128 bytes of letters, digits and `. _ : / -` (`validObjectId`); replay accepts any id a journal holds.
- Optional request fields go through `optText`/`optNat`, which refuse a present but malformed value by name. `world-deliver.limit` is 1..16; `world-history` pages as `world-entries` does (`after`/`before`/`reverse`/`cursor`, `limit` 1..100).
- `world-posted {principal, uri, cid, object, slot?, page?, section?}` (`uri` an `at://` post or a `zulip://<stream>/<topic>/<id>` message, `postSchemes`) journals a `posted` entry (identity `posted:<uri>`) and indexes `world.posts`. A reply to a recorded post reaches what it was made for (`world-reach`, 5.162: `object`, `slot?`, `page?`, `section?`, `unposted?`).
- `world-principal {principal, did, handle}` (clock principal only) journals a `principal` entry for the handle registry; "" forgets a handle.

## 3. Journal

A journal at `J` is two files (5.137): `J`, the chain, one line per entry `{at, bytes, hash, height, previous}`, and `J.blocks`, the block store, where each entry's record (its canonical DAG-CBOR without `hash`, whose CID is the `hash`) lies at `at`. An entry's common fields: `height`, `previous`, `hash`, `identity {principal, intent}`, `roots [{object, version, scalar?, fields?, rows?, spans?, gaps?}]` (5.136; `gaps` kernel18), `turn`, `request` (digest), `outcome {tag, …}`. `hash` is the CID of the canonical DAG-CBOR of the entry without `hash` (`tests/wire.py` is an independent Python encoder). Genesis `previous` is 64 zeros (`Limits.genesis`). A forked world's height-1 `previous` is the forked entry's CID (section 5.7).

`world.receipts` maps `identityKey` to the entry index (first wins, except that a suspension or a transient refusal is replaced by the identity's next entry). Transient refusals (`transientClasses`) are journaled but do not bind; admitted outcomes and every other refusal bind.

A state is named once, by the entry that wrote it: `writes[].cid`, or a created seed. `world-state-cid` answers it to a reader who may view the object.

Sources are carried once per journal: compile inputs name each module `{name, cid}`; the first entry needing a source carries it in top-level `sources [{cid, source}]` (checked against its CID on replay). Compiled packages are cached by input digest (`world.builds`, `buildKey`, `maxBuilds`), so creation and replay compile each distinct package once. Reprogram `source` fields are verbatim.

Optional top-level fields (all inside the hash): `absent [id]`, `turnRequest`, `ticksUsed`, `ledger {depth, work, storage}`, `result`, `sends [{id, to, method, argument, ledger, world?}]` (`world`: a send across, 5.173), `delivery {id, from}`, `resumes` (hash of the suspension it continues), `offers [{to, text}]`, `replyTo`, `rerun`, `ended`, `publishes`, `blocks`.

Outcomes:

- `created`: `{object, pin, sourcesSha256, compile, seed, read, chain, supervisor?, owner?}`; `roots []`, `turn 0`. Replay recompiles, requires the pin to match the source closure, the seed to conform and the amendment dry run to pass at the entry's height.
- `admitted`: `{writes [{object, version, edits, callers, kinds, cid?}], reprograms?, amendments?, creates?, grants?, revokes?, spent?}`. `kinds`: 0 write, 1 reprogram, 2 amend. Also per change, only when non-empty: `methods`, `vias`, `arguments`. Replay rebuilds the `Proposal`, checks `request == p.digest`, re-runs `judge`, and requires the recorded reprograms, amendments, creates and write versions to equal the replayed ones.
- `refused`: `{class, clause?, object?, reason?, reading?, expected?, root?, hint?, next?}`. Classes (`refusalClasses`): staleRoot, typeMismatch, capacity, absentItem, lawRefused, unknownObject, duplicateIdentity (never journaled), evaluation, budget (resource ticks, heap, stack, nodes, bytes or `law ticks`), budgetExhausted, programRefused (clause packageBytes, compile, stateType, migration, `law syntax`), requiredAbsence, keyTaken, duplicateKey, badSpell (5.49), quota (5.60), noMethod (5.62), quiet (5.126; transient), cardRefused (5.157). Every `reason` is written once, at commit, by `Refusal.voiced` (5.75); a law refusal with a reading journals it as `reading` and `voiced` writes `reason: "refused <clause>: <reading>"` from it (5.154), as for a card's own refusal (5.157). Replay checks only that the class is known; `publicRefusal` shows a law refusal's reason and reading.
- `suspended`: `{slot {principal, intent}, deadline, activity {object, method, argument, checkpoint {packetSha256, tokens, digest}, roots, absent, writes, sends, creates, programs, laws, ticks, awaited, awaits, offers, violation?}}` plus `request`, `ledger`, `ticksUsed`. Replay requires `digest == tokensDigest tokens` and registers it in `world.suspended`.
- `relayed` `{world, receipt, height}` with one `sends` row, and `crossed` `{world, answer {tag, class?, clause?, reason?}, receipt? {hash, height}}` with `result?` and, for a send, `delivery`: the two halves of a call or send across (5.173). A `suspended` entry's `crossing {world, to, method, argument, sender, ledger}` is a call across waiting.
- `principal`: `{did, handle}`, identity `{clock, "principal:<did>:<height>"}`. `advanced`: `{from, to}`, replay requires `from == w.clock && to > from`. `settings`, `library {pin, previous, modules, law?}`, `posted`, `interpreted`, `forked`.

Cross-entry invariants (`checkDelivery`, `checkSends`, `checkResumes`):
- A `sends` id equals `deliveryId principal intent ordinal` (CID of `[principal, intent, ordinal]`).
- An entry with `delivery` consumes exactly the pending delivery it names, under the sender's principal, `intent == id`. A `budgetExhausted` refusal's reason names a ledger field that is zero (`exhaustedReason`).
- An entry with `resumes` names a waiting suspension of the same identity.
- `record` derives `pending`, `suspended`, `clock`, `touched`, `receipts`, `outbox`, `handles`, `posts`, `replies`, `blocks`, `modules`.

## 4. Turn state and limits

`TurnState` lives in `M`; `Abort` is `request | evaluation | budget | suspend`. `finishTurn`: `.suspend` writes a `suspended` entry; `.evaluation` refuses `evaluation`; a `violation` refuses `requiredAbsence` (the violating creator is journaled as `root`, the taken id as `object`); `.ok` calls `commit`. A request error journals nothing, except for a delivered or resumed turn, which is refused.

- `roots`: set by `recordRoot`, with `recordBehaviour` adding an offered card's optional `behaviour`; validated at commit by `judge`, at resume by `resumeSegment` and `resumeHeard` (`staleBehaviour`, 5.222).
- `writes`: `addWrite` (the running object only; another target is answered `refused {clause: notSelf}`), `ensureWrite` (reprogram/amend).
- `sends`: ids derive from the ordinal at commit (`sendsJson`). A send's ledger is `{depth-1, work - used, storage - bytes added}` (saturating). Work is charged after the fact: a turn may overshoot `work` by one turn.
- `creates`: built in-turn by `buildCreated` (compile, evaluate `initial()`, overlay the partial seed with `mergeSeed`, `makeObject`), installed by `commit`.
- A `create` with `requireAbsent.object == ""` gets `<creator>/<package lowercased>/<n>` (`mintId`); every creation of an id of that shape raises its parent's `minted`.
- `await` accepts `until` (absolute clock height) as well as `patience`; Plan `awaitUntil`.
- Await inside a `call` is refused; only the top activity checkpoints.

Limits (`Store.lean`, `Limits`; kernel bounds are in `Limits.lean`, see KERNEL-HANDOFF):

| group | names and values |
| --- | --- |
| ids, text | `maxObjectIdBytes` 128, `maxPrincipalBytes` 128, `maxIntentBytes` 256, `maxMethodBytes` 128, `maxHandleBytes` 256, `maxTitleBytes` 256, `maxUriBytes` 512 |
| per turn | `maxRoots` 64, `maxWrites` 64, `maxEditsPerWrite` 256, `maxPlansPerTurn` 1024, `maxCallDepth` 8, `sendsPerTurn` 32, `createsPerTurn` 8, `awaitsPerTurn` 8, `checksPerTurn` 8, `grantsPerTurn` 8, `publishesPerTurn` 4, `listPage` 64 |
| data | `dataDepth` 8192, `plainDepth` 64, `Bounds.maxCellBytes` 262144 (the scalar part and each relation row, 5.136), `maxObjects` 10000 |
| journal | `maxEntryBytes` 1 MiB (a record), `maxJournalEntries` 1,000,000, `maxJournalBytes` 4 GiB (chain and store), `maxHistoryLimit` 100, `maxCheckpointBytes` 512 KiB, `snapshotEvery` 1000 (`world-open {snapshotEvery}` per process), `maxSnapshotBytes` 256 MiB |
| ledger | `maxDepth` 100, `chainWork` 10,000,000, `chainStorage` 1 MiB (creation may lower, never raise) |
| time | `maxTurnTicks` 1,000,000, `maxPatience` 1,000,000, `interpretationPatience` 64, `crossingPatience` 60 |
| worlds | `scratchPerPrincipal` 2, `scratchJournalBytes` 16 MiB, `scratchObjects` 1,000, `scratchMinutes` 360, `crossingsPerTurn` 1 |
| delivery | `deliveriesPerCall` 16, `deliveriesPerSettle` 64, `deliveryAttempts` 4, `maxPending` 4096, `pendingActivitiesPerObject` 8, `pendingInterpretationsPerObject` 64, `maxSuspended` 4096, `maxResumesPerCall` 1024, `maxGrants` 4096 |
| programs, laws | `maxPackageBytes` 131072 (`Bounds.maxPackageBytes`), `maxLawBytes` 4096, `maxLawClauses` 16, `maxPreparedPrograms` 16, `maxCompiledPackets` 256, `maxBuilds` 1024, `maxReaders` 256, `maxLibraryModules` 256, `maxLibraryBytes` 786432 |
| interpret | `maxUtteranceBytes` 8192, `maxOffersBytes` 65536, `maxReplyBytes` 262144 |
| forms | `formTextMax` (= `cardShownChars`) 1400, `formNaturalMax` 1000000000 |

A full count refuses the turn with class `capacity`, reason the limit's name. The `bounds` op answers every one of them by name.

## 5. Subsystems

### 5.1 Authority and laws

- `Facts {subject, caller, height, turn, pin, kind, method, evicted, clock, object, reads}` (`reads`: the states of the objects the law cites, 5.139) (`relations`: the object's declarations, for `insertOnly`, 5.74). `caller` is the object whose method wrote ("" for the turn's own method and client proposals; for a delivered turn, the sending object). `method` is the method whose run made the change ("" for ops).
- Fragment (grammar in `ObjectiveBendLaw.lean`): `and`, `or`, `not`, `implies`; `request.subject`, `request.caller`, `request.height`, `request.turn`, `request.pin`, `request.kind`, `request.method`, `request.clock` (the world clock the turn read, `Facts.clock`), `request.object` (the written object's id, `Facts.object`; text-comparable), `old.F` (the field before the write; at creation its kind's empty value, `emptyReading`), the three-slot bound `REF <= REF + REF` (`leRSum`), integer and text constants, `monotone(F)`, `writeOnce(F)`, `appendOnly(F)`, `unchanged(F)`, `x in new.F` (`member`), and for relations `insertOnly(F)`, `count(new.F) <= N`, `count(new.F) <= count(old.F) + N`, `x in new.F.COL`; and the relational atoms (5.139): `count(SIDE.F where COL == TERM)` as a reference, `changed(new.F.COL) by TERM`, `TERM in "O".F.COL`, `under "O"`. `writeOnce` admits exactly one change of F away from its empty value (`emptyValue`: 0, false, "", the empty list, a record of empty values); a field missing from the old state fails closed.
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
- Extend: `world-reprogram {mode: "extend"}` and Plan `extend` add the source as module `Layer<n>`. The host writes `layer over ./<module below>.obend` as its first line (`layerLine`), so the kernel builds a layer stack with late binding. The new pin seals the whole source closure, including the library; the state type must be equal under `canonicalTy` or a migration named. Tests: `test_extend`, `test_layers`.
- Supervisors: `Object.supervisor` is fixed at creation (`world-create {supervisor}`, Plan `createUnder`; `refused {clause: supervisor}` if not an object). An activity of a supervised object ends `broken` when refused `evaluation`, `budget` when a machine budget ran out, `timedOut` when a segment resumed past its deadline ends in any way. `commit` puts an `ended {id, to, method: "ended", argument, sender, ledger}` field in that entry (`endedField`, `endedId`); `record` makes it a pending delivery with argument `{receipt, how}`. A ledger refusal (`budgetExhausted`) tells nobody. Replay checks the id and that `to` is the supervisor (`checkEnded`). Test: `test_supervisors`.
- Handlers: Plan `run {object, method, argument, handler}` runs the callee as `call` does, but every Plan the callee's frame, or any frame it calls, yields is first offered to the handlers around it, innermost first, each a pure `handle(state, plan[, context]) -> Handled<R>` (`answer {response}`, or `pass` to the next one out; 5.73). The handler must be readable by the subject (`refused {clause: handler}`) and is a root. Plan `judge {edits}` answers `judged {admitted, clause}` without committing. Test: `test_handlers`.
- Held entries: `compiledMethod`/`compileDef` use `compileEntryIn` (`Package.prepareRequest` cached in `world.requests`, `Package.compileEntryFrom`); `Compiled.entry` is a decoded, checked `CheckedEntry`. Turns run `Turn.startEntry`/`resumeSuspended`/`resumeEntry` over a `Turn.Store`; pure methods, cards and views run `Package.executeDataEntryStored`; law, `lawReads`, handlers and migrations run `Package.executeDataEntry`. Only `initial()` at creation runs from the packet.
- Kernel integration: `world-turn {…, profile: true}` returns `profile [{kind, steps, ticks}]` (not journaled; a fetched row is `fetch`). Every argument enters natively (5.136).

### 5.4 Interpretation

- `world.interpret::<R>({utterance, offers, policy, model})` suspends like `await` with `interpretation {id, object, policy, utterance, offers, model?}` (id = hash of principal, intent, ordinal). Deadline `interpretationPatience`, resuming `timedOut`.
- `world-interpretations` lists pending items with the Policy's state as `{model, system, examples}`; `policy.system` is the Policy's pure `prompt(state, offers, utterance)` (`policyPrompt`) else its `system` field; `policy.model` is the item's `model` when non-empty (at most 128 bytes), else the Policy's.
- `world-interpretation {id, reply}` journals an `interpreted` entry and the settle pass resumes the turn. Verdicts, as `Interpreted<R>`: `proposal {object, method, argument, spell}` (the reply's text, `raw`, is a spell fitting an offered form; the method is one its object offers and the argument conforms; `interpretVerdict`, `spellVerdict`, `proposalVerdict`; a reply without `raw` is a request error, 5.187), `unclear {needs}` (a misfit or missing fields; a failed reply gives `needs: ["model: <reason>"]`). `denied {}` when the Policy is not readable by the turn's principal (TurnLoop, `interpret`); Garden and the Directory refuse it with clause `policy`.
- Capacity: `mayWait … (interpreting := true)` counts interpretations apart (`waitFull`); `interpretGate` is the hour's and the day's quotas. Test: `test_interpret_text`, `test_policy`.
- The host starts a reading itself for words a card heard (5.163, `heardTurn`): a suspension with no checkpoint (`hostResumed`), resumed by `resumeHeard`, which runs hob's answer as the speaker's turn on the card. `world-interpretations` gives a Policy's `prompt(state, asked)` the card's `wants` (each with its filled `asks`) and the library's `pages` beside `{utterance, offers, card, misfit}` (`misfit` the host's own, from `heardTurn`; the `interpret` arm takes no `held` or `misfit`, 5.168).

### 5.5 Cards, offers, publish, posts

- Plan `card {object}` -> `carded {document}`: `renderCard` runs the target's card on its committed state under the turn's ticks (records a root; `denied` without read authority, `noCard`, `refused {clause: render}`). It runs `renderWanting(state, context, wanting)` when the package declares it (the host hands it `wanting`'s rows for the reader, 5.184), else `render`. `cardContext`: principal = reader, caller = asking object ("" for the op), `inputOrigin.kind` "card". `world-card {principal, object}` -> `{status: "card", text, document}`; `ownCards` `env`/`wake` resolve to `<name>/<principal>` (`resolveCard`).
- Plan `objects {prefix, after}` -> `listed {ids, more}` (ids the subject may view, byte order, `listPage`); op `world-objects`.
- `offer {to, document}` ("" = the frame's subject). An admitted entry retains `offers [{to, text}]`; `record` indexes them by addressee (`world.outbox`). `world-offers {principal, after?}` answers `offers [{height, ordinal, identity, text, from {post, principal, intent}}]` (`originOf`). A turn's reply carries only offers addressed to its own principal. A turn that offers nothing has no `offers` field.
- Reads under authority: `world-receipt {principal, identity, of?}`; `projectEntry` gives the identity's own principal the whole entry, anyone else a `publicRefusal` (`{status: "refused", class, root {object, version?}, reason?}`, plus `object` and `hint` for `unknownObject`, `object` for `requiredAbsence`) or chain fields, roots and writes of objects the reader may view, and an `elided` count. A refused turn reply carries it as `public`.
- `publish {page, section, body}` -> `published {post}` (at most `publishesPerTurn`; a title or section with a line break or over 256 bytes is `refused {clause: title}`). The admitted entry retains `publishes [{id, object, page, section, text}]` with agentwiki text (`wiki: Title\n\nbody` or `edit: Title › Section\n\nbody`). `world-publications {principal, after?, before?, reverse?, limit?}` answers `publications [{height, ordinal, id, object, page, section, body, hash, replyTo?}]`.
- `world-turn {replyTo}` (in the digest): when the parent is a post recorded for the turn's object, the entry journals `replyTo` and `World.replies` maps the post to the turn. `receive` takes `{text, post}` as sent (host10 deleted `receiveArgument`: a `slot` field is a `typeMismatch` like any other).
- Transport side: `transport/bridge.py` `publication_drafts` writes each publication as an outbox draft and never posts; `transport/post.py --record` confirms as the clock principal and calls `world-posted`.

### 5.6 Snapshots and replay

- `durable` writes `<journal>.snapshot.<height>.cbor` after the sync when the height is `every` (`world-open {snapshotEvery}`, default `Limits.snapshotEvery`) past the last snapshot written or resumed from, and at once after an `ignore`/`unignore`; the reply carries `snapshot {height}` or `{refused}` (a failed snapshot refuses nothing). The newest three are kept. File: DAG-CBOR `{cid, body}` (`delvetalk.snapshot.v3`); `tests/test_snapshot.py` has an independent Python reader.
- The body is the store (`storeJson`: objects with state, `stateCid`, law text, version, read policy, ledger, compile inputs by CID, `pin`, `packet` cached, `supervisor`, `minted`, `readings`; types, method tables and law shapes by pin; libraries, grants, posts, settings, the clock) and `index` (`indexJson`): every index `record` derives (receipts, `touched`, `touches`, `anchors`, `changes`, subscriptions, pending, suspended, replies, handles, where each source and block lies, outbox, publications, reservations, attempts, interpretations started, root acts, cards, quiets, hidden, the ignore sets, `shadowed`, the day's and the hour's counts, `forkedFrom`). Sources no entry carries by CID (reprogrammed and extended modules) are kept whole (`knownByCid`).
- `openJournal`: the chain read whole (`chainOf`: links in sequence, each naming the one before; every link inside the store), entry 1 read for the edition, then `reopen`: per snapshot newest first check the CID, edition, height and `head` against the chain, install the indexes and the store, refuse it if a later `ignore`/`unignore` names a height at or before it, check each object against its anchors (`checkAnchors`), and replay every later entry, each read and checked (`checkedEntry`: its record is its CID's, its height, its `previous`). The first failure refuses the snapshot by name and the next older is tried, then full replay (`replayAll`, which also finds the ignore set first, `ignoresFrom`).
- `install` refuses "the state of X is not its CID's" and "object X carries no state CID". Against a forger who recomputes both, `checkAnchors` reads, per object, the entries `World.anchors` names for its version, pin and law (`versionIn`, `pinIn`, `lawIn`, `stateCidIn`): "the state of X is not the one the journal commits to at version V", "object X is not at the journal's version and pin", "the law of X is not the journal's". A forger who points an object back at an older genuine anchor is `verify`'s: `world-open {verify: true}` replays from height 0 and refuses each snapshot whose body (store and indexes) differs from the replayed world's ("it disagrees with replay at its height").
- Pins are sources. No packet digest is journaled: replay recompiles from the journaled sources with the current compiler and requires the compile to succeed, the seed to conform and the recomputed pin to equal the recorded one. `world-status.recompiledDifferently` counts objects rebuilt after a snapshot resume whose packet differs from the one the snapshot cached (`World.cachedPackets`, `noteRecompiled`).
- Suspension checkpoints are journaled as `tokenTree {depth, roots}` over content-defined blocks (`cutBlocks`: leaves 32..256 tokens, a token of 256 bytes or more its own leaf; inner nodes 2..16 names), each block once per journal as a top-level `blocks [{cid, items}]` item (`World.blocks` names the entry carrying each; `blockItems` reads it); an interpretation's `offers` are a one-item block (`offersBlock`). Measured on hbox at foundation 6b928f6 (132 directory suspensions, `tests/test_suspension_size.py`): median 9,392 B with blocks against 119,119 B with the v2 codec alone.

### 5.7 Slugs, fork, repository reads

- Slug (`Slug.lean` `ofCid`, `decode`): proquint of the first 32 bits of a CID's multihash digest (`lusab-babad`). Replies show receipts with `slug` beside `hash`; `world-inspect` shows `pinSlug`. `world-resolve {principal, slug}` answers `{status: "resolved", kind: receipt | pin | state, cid, receipt?}`, `{status: "ambiguous", matches, message}` or `{status: "unknown", message}` over `slugTargets`. Test: `test_slug`.
- `world-fork {principal, height?, into}` (`Session.forkWorld`; `into` must not exist) writes a new journal whose one entry is a `forked` genesis (`Snapshot.forkGenesis`): the store at `height` (`Snapshot.reopen` over the chain's prefix) as `storeJson`, only the objects `principal` may view (with grants, pending deliveries, suspended activities written out whole), the handle registry, `omitted [ids]`, `forkedFrom {world, height, cid}`. Opener, clock principal and library-law principal are `principal`. Height 1 chains to the forked entry's `cid` (`checkedEntry`); written by `writeJournal`; replay starts from the installed genesis (`installGenesis`). Answers `{status: "forked", into, forkedFrom, carried, omitted}`. Test: `test_fork`.
- A fork and a carry (5.159) are one mechanism, the store-installing genesis (`Ops.installsStore`, `genesisOrigin`, `genesisRow`; `Snapshot.genesisEntry`, `installGenesis`): the store, every source its objects compile from carried once in the entry's own `sources` and named by CID (as any entry carries the sources it is first to name; an older fork's whole sources still install), the pending deliveries and whole suspensions, the handles; `previous` the origin's `cid`. A carry adds the world's standing indexes (`carriedKeys`, as `indexJson` writes them, laid over an empty world's) and `carriedFrom` with the old chain's `entries {hash: height}`. `world-status` shows `forkedFrom` or `carriedFrom` from entry 1 (`originShown`, the entries left out); `World.forkedFrom` stays in the v3 snapshot index only until the next snapshot edition, which drops it. `world-resolve` answers a carried world's old receipts (`carriedEntries`, every generation) as `{kind: receipt, carried {world, height, at}}` and an installed object's pin and state.
- `world-entry {principal, hash, bytes?}` (`bytes` = hex of the canonical DAG-CBOR, identity's own principal only); `world-entries {principal, after?, before?, reverse?, limit?}` (limit 1..100); `world-object {principal, object, version?}` -> `record {object, version, pin, pinSlug, law, readings, laws [{object, version, pin, name, clause, reading?}], stateCid, library?}` as of the version (`pinAndLawAt`); `world-source`/`world-sources` -> `{cid, name, text, height}` for sources of objects the reader may view and the libraries'; `world-grants`. Test: `test_reads`.

### 5.8 Arrival

`world-arrive {principal, did, handle}` (clock principal only; the world must name an opener and have a library) records the handle as `world-principal` does, then creates each absent one of `<did>` from library module `Avatar`, `env/<did>` from `Env`, `wake/<did>` from `Wake`, as `create` by the opener with identity `arrive:<id>`, `owner: did`. Idempotent: a repeat answers `{status: "arrived", did, handle, created: []}` with no entry. Reply: `created [{object, height}]` and `principal`. A missing library module is a request error naming it. `transport/hostproc.py` `ARRIVAL` lists the packages the sealed library must hold (`Avatar`, `Env`, `Wake`; the Avatar imports `Places.obend` from the library). `docs/GENESIS.md` says when transport calls it. Test: `test_arrive`.

Items 5.43 to 5.117 follow, numbered by the lane that wrote them (5.9 to 5.42 were folded into 5.1 to 5.8).

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
   object is a `call`), a method outside `worldMethods` `refused {clause: noMethod}`; `spell` is not a world method. The response is checked against the call
   site's type the kernel reports (`responseType`): the result sum of that protocol method in World.obend
   (`Written`, `Returned<R>`, `Interpreted<R>`, ...). A handler (`run`) sees the Message as yielded. The world has no state
   and no law (WHOLENESS §5): who may call which method is the authority model as built (`write`
   self-only, `create` under the creator's rules, grants, read policy). The id `world` is reserved
   (`worldId`, `validObjectId`). A message suspension's checkpoint (two-token site prefix) goes through
   the block scheme like any other. `viewField {object, field}` (RELATIONAL §6) answers `viewed {version,
   state}` with one field when its value conforms to the call site's type (`typeMismatch` otherwise,
   `field` for a missing field); read authority and root as `view`. Test: `tests/test_world_object.py`.

49. **The host reads spells (host8; WHOLENESS §2, host day 2).** `Host/Spell.lean` is the spell grammar, ported
   from Spell.obend in Lean rule for rule and now the only complete one (Spell.obend keeps a reduced reader of the last spell
   line, its card, action and inline fields, which `Card.unanswered` and `spellAction` still call: a second reading of
   one grammar until `Heard` carries the card and action) (`parse`, `bare`, `fit`, reasons verbatim, plus a `Clause`: `otherCard`, `noAction`,
   `unknownField`, `duplicateField`, `badValue`, `unclosedBlock`, `unclear`); the stateless op `spell-parse
   {text, form?}` answers `{status: "parsed", spell | notASpell, fit?, bare}`; `tests/test_host_spell.py` runs
   116 fixtures (`tests/fixtures/spells/`, recorded while both parsers agreed, lane/objects9) through the host's. `runTurn` sends a direct
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

50. **Subscriptions and `changed`**: deleted with Wake (5.161); a rule on the thing is the reaction (5.160).

51. **Field roots (host8; WHOLENESS §3a).** `viewField` reads one field: the root is journaled as
   `{object, version, fields: [f]}` (`recordFieldRoot`, now a `Cells` reading, 5.136), current while no write
   since its version touched the field (`cellsCurrent`, from the per-object index); it counts against
   `maxRoots` beside the object roots.

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

53. **Typed receivers**: deleted with Wake (5.161); a rule on the thing is the reaction (5.160).

54. **Spells, the rest (host9; WHOLENESS §2, second root decisions 2).** Interpretation: a model's text
   to an activity of the message dialect is fitted against the offered forms (`spellVerdict`): a spell
   naming an offered form that fits is that form's `proposal {method, argument}` (checked by
   `proposalVerdict`), a misfit `unclear {needs: [reason]}`, missing fields `unclear
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
   `Turn.startEntry`; `drive` takes a `Turn.Step`, whose yield holds a `Turn.Suspension`; a Plan
   answered in this process resumes with `Turn.resumeSuspended` over the frame's store (no checkpoint
   encoded, digested or decoded). Only `await*` and `interpret`, which may suspend, build a checkpoint
   (`Held.kept`, 5.136). A journaled resumption uses `Turn.resumeEntry`. Measured on hbox, the offline
   rehearsal with `DELVETALK_TIMING=1`, one run each on the same tree (before at load ~5, after at ~17):
   host ms 25,646 -> 13,621; directory `receive` 11,339 -> 4,521 (120 turns, median 70 -> 22 ms); garden
   `receive` 5,189 -> 2,010; env `receive` 3,681 -> 2,267; rehearsal wall 62.3 -> 43.4 s.

59. **Compile caches per process (host9).** `World.compiled`, `requests`, `builds` and `programs` are
   keyed by content addresses (compile inputs naming the library by pin and modules by CID; `defKey`,
   `buildKey`, `programKey`), so `Session.stepWorld` hands the caches of the world it had open to the
   next it opens (`Caches`, `World.caches`/`withCaches`; `openWorld` -> `openJournal` -> `reopen`,
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
   render, forms, lenses, set, publishPage, page, relations, methods, law, lawReads, views,
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
   interpretation's `named` flag: no journal from before host10 is opened). Test:
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
   `spellUsage`), joined by a line as `Card.pageText` joins sections, under `page`, else the object's id; the result is the post id. The turn writes nothing and
   stages one publication. The five pasted `publishPage` methods (Anthology, Scene, Table, Tide,
   Workshop) may go (objects lane); Garden keeps its own. Test: `tests/test_publish.py` `DefaultPage`.

69. **A card's own form bounds (host10; WORLD-REVIEW finding 3).** When the entry module declares `forms()`,
   the host runs it (`declaredForms`) and its kinds override, field by field, the defaults the method's
   input type gives (`methodForms` with `declared`; `formsOf`, `spellForms`, `spellFormsData`): a
   spell is judged by the card's bounds (text min and max, natural range, choice set), and
   `world-inspect` `forms`, the `inspect` Plan and `?` usage show them. A field no form names keeps its
   type's kind. `Form.Kind.source` (any payload) reads as text of 1 to `Limits.formSourceMax` (`Bounds.maxPackageBytes`, 131,072)
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
   `lenses` (and, for `publicMethods`, `methods`) is read only from the artifact's `declares:
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
   <card>; the commonplace lists the doors". Usage lists only the forms whose method the
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

108. **State bytes are canonical bytes (host12; OBJECTS-HANDOFF §4).** `stateBytes` (now only
   `world-inspect`'s; the bound and the ledger are per cell, 5.136) is the length of the Data's canonical DAG-CBOR (`Delvetalk.Canonical.encode`), not of its wire
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
   `noAction`). `delvetalk <card> become / kind: <id>` installs the kind's stack, followable text and lineage
   in one turn by the speaker, judged by the card's own law (reprogram kind 1, amendment kind 2),
   journaled under the turn's identity (a retry answers the receipt). `kindChange`, shared with KIND's
   making (`world.compose`), lays ancestors bottom first and replaces a component's changed bodies at
   their recorded positions (5.219). `madeFrom {object, pin, receipt, components}` names the source;
   replay reads the component bodies and positions back. Refusals: `missingField`, `unknownKind`,
   `of` (an unreadable or too deep ancestor), the law's, or `programRefused` with the compiler's
   diagnostic. A bodyless kind supplies its text and
   identity. `?` usage adds "The host's spells for any card" with `become` when the law would admit
   the speaker's reprogram (`kindAdmits`, as `methodAdmits` on the state as it stands). Tests:
   `tests/test_extend.py` `HostSpells`, `tests/test_kinds.py` (5.219).

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

116. **Prose with a colon ends the fields (host12; docs/FLEX.md §4 host 1).** `Spell.binding` takes a
   line as a field only when it `looksLikeField` (`name: value`, the name an identifier), as `bareT`
   does; any other line ends the fields as prose. The playtest's 68673 and 68675 (a clean, indented
   planting with a sentence like "First-pass read while I'm at it: …" after it, refused `unknownField`
   twice) are parse fixtures and plant. A misspelt or capitalised name (`Seed:`, `see d:`) is now prose
   too, so the spell is `unclear` naming what it lacks instead of `unknownField` (FLEX host 2 folds case).
   `world/lib/Spell.obend` has no field-line reader to mirror (deleted with its parser, lane/objects9);
   its inline reader already checks `looksLikeField`. Five fixture rows re-recorded, two added. Tests:
   `tests/test_spell.py` `test_a_prose_line_with_a_colon_after_the_fields_ends_them`,
   `test_a_name_outside_the_identifier_alphabet_is_no_field_and_ends_the_fields`.

117. **What the model sees, and hob's answers (host12; docs/FLEX.md §4 host 5, 6; `held` and the arm's `misfit`
   deleted by 5.168).** `world-interpretations` lists, beside the utterance and offers, `card` (the asking card as the
   speaker reads it now, `cardText`, at most `Limits.cardShownChars` 1,400 characters), `misfit` (the misfit spells
   a host reading reads past), and the policy's `lexicon`; a Policy whose `prompt` takes `(state, asked)` gets `asked =
   {utterance, offers, card, misfit, wants, pages}` fitted to its type (the old `(state, offers, utterance)`
   still runs). `interpretVerdict` reads hob's three non-spell answers before the spells: `none` is
   `unclear {needs: ["not addressed"]}`, `card` is `replied {text: "card"}` (`unclear ["card"]` where
   the Response has no `replied`), `ask: <one line>` is `unclear {needs: [<question>]}`; spells and
   `proposals` as before. Tests: `tests/test_interpret_object.py` `test_hobs_three_answers_that_are_no_spell`,
   `test_the_request_carries_the_card_as_the_speaker_reads_it`, `tests/test_policy.py`
   `test_the_interpretation_shows_the_model_the_card_as_the_speaker_reads_it`.

118. **Reach (host13; docs/FLEX.md §2).** A turn's `reach` says how its words reached the object:
   `reply` (its `replyTo` names a post the world recorded; the host checks), `spell` (its text has a
   spell line; the host parses), `delivery` (an object sent it), `direct` (a principal named a method
   other than `receive`), or what the transport saw of the post and states on `world-turn {reach}`
   (`statedReaches`: `mention`, a mention or summons of the world; `door`, a door's word in a thread
   the world opened; `fields`, field lines there, checked: a `fields` with no field line is a request
   error; `direct`, asked on the card itself: the play page and `/turn` send it). Any other value,
   `reply` and `spell` included, is a request error. A stated reach is part of the request digest.
   `runTurn` settles it (`reachOf`) before the spell is read; `TurnState.reach` carries it through
   calls; a suspension's activity journals it (when non-empty), so a resumed segment and a stale
   re-run keep it, and `world-interpretations` lists it per item. An `interpret` Plan of a turn with
   no reach answers `unclear {needs: ["not addressed"]}` at once: no suspension, no model, no quota.
   The bridge must state the rule `route` used (transport lane; until then the town's prose is not
   addressed), and on Zulip pass the recorded ancestor it found as `replyTo`. Tests:
   `tests/test_reach.py`; prose tests in test_policy, test_hub, test_fork state `mention` (or
   `direct` for the play page's).

119. **Names in any case, and no `delvetalk` on a direct reply (host13; docs/FLEX.md §4 host 2).**
   `delvetalk` is read in any case; actions and field names fold to lower case (`Spell.foldT`;
   `looksLikeField`, `binding`, `bareT`, `startField`); an action written with capitals is one only when
   nothing but inline fields follows it (`heading`), so "delvetalk Is The word" stays a sentence. A
   card's name is kept as written: `fit` compares it folded, `spellVerdict` too, and `castSpell` reads
   `Me`/`ENV` as `me`/`env` and a name no object has as written as the one object whose id folds to it
   (`foldedId`; none when several do). One trailing `.` or `:` on the action is trimmed (`unmarked`).
   On a direct turn whose reach is `direct` or `reply`, `routeSpell` parses with the addressee
   (`Spell.parseFor`, `addressedText`): when the text has no spell line, a first non-blank line naming
   one of the card's actions or `?`, alone or after the card's name, with nothing after it but inline
   `/ name: value` fields, is the spell line (`plant.`, `Garden plant / seed: x`); a field line, a `>`
   quotation or a sentence ("Plant something pretty") is not. `spell-parse` takes `addressee {card,
   actions}`. One fit fixture re-recorded (`Seed: fern` is the field now). `world/lib/Spell.obend`'s
   inline reader is not folded (objects lane). Tests: `tests/test_spell.py`
   `test_card_action_and_field_names_are_read_in_any_case`, `test_a_trailing_full_stop_or_colon_on_the_spell_line_is_trimmed`,
   `test_a_reply_to_the_card_needs_no_delvetalk`; `tests/test_spell_turns.py`
   `test_a_spell_in_any_case_and_a_direct_reply_without_delvetalk`.

120. **A value without a name, bound by type (host13; docs/FLEX.md §4 host 3).** In a spell's field
   lines a line with no colon is a value without a name (`Binding` named ""), and so are the slashed
   form's leading segments before the first with a colon (`leading`: `plant / silver / a fern`; after a
   named field a ` / ` stays inside its value). Values run on only while their lines have no colon
   (`loose`), so prose after them never reads a later `name: value` line as a field, and a value after
   a blank line is prose that ends the fields (`afterBlank`). `Spell.bind` (in `fit` and `castSpell`,
   before `withFence`) binds each in order: to the open choice whose option it is (folded; the form's
   spelling), else digits to the one open natural, else the one open text field; a value whose first
   word is one of the form's field names (`seed fern`, a missing colon) or that fits nothing is
   dropped, so fit names what is still missing (`verdigris` leaves `colour` asked). Lens and host
   spells see the named fields only. A bare value in a reply with no spell line is the card's to
   complete (objects lane, `Held`). Four parse rows re-recorded (each now shows its `=value`; the fits
   are unchanged). Tests: `tests/test_spell.py` `test_a_value_without_a_name_binds_by_type`,
   `test_prose_after_a_blank_line_or_with_a_colon_is_no_value`; `tests/test_spell_turns.py`
   `test_values_without_names_plant_by_type`.

121. **A direct turn's misfit (host13).** Replaced by 5.163: a misfit spell is hob's to read past, for every card,
   never the card's `receive`.

122. **A turn's `extend` reaches what it created (host13; the rewrite lane's Kind).** An `extend` (or
   `reprogram {mode: extend}`) naming an object the same turn created lays the layer into the making
   (`extendCreation`): the creation is built again by `buildCreated … layer` from the package, seed
   and law it was asked with (`CreateRec.creator`, `package`, `seedArg`, `lawArg`, `layer`, never
   journaled), over which `extendInputs` lays the layer, so the `created` entry journals one closure and
   its pin, and replay rebuilds it as any creation. The made thing's own text law judges it as a
   reprogram (kind 1, proposer the running object) before it is staged; a compile failure answers
   `refused {clause: compile, reading}` and nothing is staged, so a kind that `refuse`s on it leaves
   nothing made. A replacing reprogram (`unknownObject`, with a reading), a migration (`migration`) or
   a second layer (`duplicate`) of a thing not made yet is refused. A `call` or `write` to a creation of
   the same turn is still `unknownObject` (judge and replay know only committed objects); the Kind's
   send-then-graft can become create-then-extend. No replay edition change (creations replay from
   their recorded inputs as before). Tests: `tests/test_make.py` `CreateThenExtend`.

123. **`inspect` without the source, with the laws and what the reader is offered (host13; the
   rewrite lane's 2 and 3).** The `inspect` Plan takes `source: Bool` (World.obend: `inspect({object,
   source})`; a Plan without it answers the source, as before) and answers `inspected {pin, law,
   source, methods, laws, offered}`: `source` "" under `source: false` (the library's laws page read
   31,879 characters of garden at 70 ticks each), `laws` the clauses as `World.LawRow {name, clause,
   reading}` (`lawRowsOf`: the reading the text gives, else the package's while its clause stands,
   "" for none), `offered` the names of the actions offered to the turn's subject (`offeredTo`, 5.103),
   so a card's usage built in Bend lists only those. A call site whose `Inspected` lacks the new fields
   gets the older shapes. `world-inspect` leaves the source out unless asked `source: true` (the HTTP
   source page asks) and answers `offered` beside `forms`. World.obend's callers pass `source`:
   Avatar and Directory `false`, Workshop (which checks the source) and Library `true` (the rewrite
   lane moves the laws page to `i.laws` and `false`); `tests/fixtures/pins` re-recorded. Tests:
   `tests/test_reflection.py` `test_the_inspect_plan_without_the_source_answers_the_laws_and_what_the_reader_is_offered`,
   `tests/test_inspect_reads.py` `test_the_source_is_left_out_unless_asked_for`,
   `test_offered_names_the_actions_the_reader_is_offered`.

124. **The journal bound at append (host13; docs/OPERATIONS.md §c 1).** `durable` measures the journal's
   bytes (the chain and the store, `journalBytes`) and meets its bound (`Open.bound`, `Limits.maxJournalBytes`).
   An append that would come within `Limits.journalHeadroom` (1 MiB) of the bound is not written: a turn
   (the step's reply carries a receipt identity) is refused `capacity`, reason the bound's ("the host's
   maxJournalBytes is full; try later."), journaled into the headroom, so `hand` shows it on the live
   world; an op with no identity, or a refusal that would itself pass the bound, is a request error
   "journal is full: appending would pass maxJournalBytes (N bytes)" and appends nothing. Open still
   refuses a journal past its bound, naming it. The bound is 4 GiB (5.137). `world-open
   {maxJournalBytes}` lowers the bound for one process, never raises it. Tests:
   `tests/test_journal_bound.py`.

125. **`serve`: the host holds its directory and its sockets (host13; docs/FEDERATION.md §1, docs/ROOT.md
   §1.4).** `delvetalk-obend serve --state DIR [--socket PATH] [--root-socket PATH] [--root-group GROUP] [--opener DID] [--library DIR]
   [--sync none|fsync|full] [--clock P] [--home NAME]` (`Delvetalk/Serve.lean`, `spec/native/serve.c`)
   is the one process over a directory of worlds.
   - *Lock.* `flock` on `DIR/journal.lock` before anything else, held for the process's life (the
     handle is kept in `Server.lock`: a dropped handle is a released lock, which the first test found);
     a second `serve` exits 75, "refusing to start a second writer". `DIR/serve.pid` is rewritten per op.
   - *Library.* `DIR/library` rebuilt at start from `--library` and `../objects/{Avatar,Env,Wake}.obend`;
     the stateless session `library-load`s it, and `serve-status` answers its pin.
   - *Worlds.* `DIR/<name>.journal`, `name` by `Host.validWorldName` (`[a-z][a-z0-9-]{0,31}`, not `did
     zulip at world me scratch`); envelope `world: <name>`, default `--home` (`town`). The first op naming
     a world opens it with the clock, opener, library (librarian the opener), sync and `name`; `world-open
     {name}` journals `named {name}` once (`nameOp`; replay sets `World.name`, the snapshot carries it; no
     replay edition change: journals without it replay as before) and refuses a journal that holds
     another ("this journal is the world ring, not moor"). Every world of the directory is opened at start
     and held (5.137 made a held world its live state), so a turn in one reads another (5.140); `world:
     scratch/<name>` is the request principal's scratch world; `stateless: true` the journal-less session. `world-open` over a
     socket is refused ("serve opens its worlds").
   - *Status.* `serve-status` is the process's one status: `hostSha256` (the binary, cached in `DIR/binary-pin`
     by path, size and mtime), `pid`, `replay`, `library` (the sealed pin), `worlds [{name, height, objects,
     clock, replay, snapshot {resumed, refused}}]` (`replay` read from the world's first entry; `resumed` the
     snapshot height it reopened from, 0 a replay from genesis) and `scratches` (5.140). `test_serve`.
   - *Sockets.* `DIR/host.sock` and the root socket (default `DIR/root/root.sock`; deploy passes the
     `/data/root` volume's path), the public socket 0600 and the root socket 0660 (its group `--root-group`, 5.131) under umask 0177, backlog 128. The C shim accepts every
     connection, reads newline-framed lines (16 MiB) and hands Lean the next completed line in order with
     its connection and socket; one thread answers it. SIGTERM/SIGINT end the loop after the op in hand,
     removing the sockets and pid file. The public socket refuses `rootOps` (`world-root`, `world-library`,
     `world-settings`, `world-fork`, `world-snapshot`, `library-load`) and every op whose `principal` is
     the opener: a request error of class `opener`, "the opener speaks on the root socket" (5.188).
   - Ops are bounded by ticks, heap, ledger and entry bounds, and `HostClient`'s timeout answers
     `hostTimeout`. The clock is the bridge's `tick`.
   - *Transport (5.131):* `tests/host.py` `Served` starts it; the opener's ordinary turns go on the public socket
     (`resident`, 5.131). Tests: `tests/test_serve.py` (one writer, named worlds, the root socket, the status).

126. **ROOT and MODERATION in one edition (host14; docs/ROOT.md §1 to §3; replay edition 3).**
   - *`world-root {principal, reason, act}`* (`Host/Root.lean`, `rootOp`): the opener only (`serve` keeps it to
     the root socket), `reason` one line of 1..256 bytes. Acts: `set {object, field, value}` for `state`, `law`,
     `program` (`{modules}` over the object's entry and limits, recompiled; the outcome names the new `pin`),
     `pin` (stored alone: turns still run the closure the sources compile to, the reply says so), `owner`, `read`,
     `version`, `fixed`, `supervisor`, `ledger`, `readings`, `activities` (the suspension hashes of the object to
     keep); `delete {object}` (`before` the whole record, `objectRecord`; the id is free); `as {principal, turn
     {object, method, argument, identity}}` (`runTurnWith` with `TurnMeta.root`: an ordinary judged entry with
     `root {by, reason}` beside it, inside the hash); `settings {clock?, clockPrincipal?, postQuota?,
     interpretQuota?, modelQuota?, opener?, libraryLaw?}` (`clock` the clock's value, either way; the reply lists
     the `suspensions` and `grants` whose deadline or end lies between, `clockAffected`); `library {modules}`;
     `ignore`/`unignore {height}`; `card {object, text|null}`; `quiet {principal, hours}` (0 clears), `hide`,
     `show`, `retire`, `unretire` (`object`), `revoke {grant}`, unjudged. `expire` is a request error until
     scratch worlds exist.
   - *Entry:* `{identity {opener, root:<n>}, root: true, reason, turn 0, roots [], request, outcome {tag: root,
     kind, object?, field?, height?, principal?, grant?, before, after, version?, cid?, pin?}}`; `projectEntry`
     shows it (and every `moderated` entry) whole to any reader. A state or owner set raises the version and
     pushes a `Touch` with unknown edits, so a turn that read the old version is stale.
   - *Replay:* `rootBefore` reads the replaced value from the store, `applyRoot` lays `after` on it (no judge,
     no conformance, no pin check), `recordActs` moves the derived indexes (clock, `cards`, `quiets`, `hidden`,
     `ignored`, `rootActs`, suspensions); live and replay call the same three, and replay refuses "root entry N:
     before does not match". `Snapshot.ignoresFrom` finds the final ignore set before replay; `replayStep` records an
     ignored height inert (`recordInert`: in the chain, its sources and blocks known, its identity unbound), and
     after the lowest height any `ignore`/`unignore` names, an entry that no longer replays is shadowed
     (`World.shadowed [{height, by, reason}]`, `world-status.shadowed`, `world-open`'s reply, `verify`); before
     it a disagreement still breaks the journal. After an `ignore` or `unignore` the session re-derives the live
     store (`Snapshot.reopen`, from the newest snapshot below the height it names) and writes a snapshot at once. A
     snapshot with a later `ignore`/`unignore` naming a height at or before it is refused ("an ignore after it changes
     what it holds"); a snapshot carries the ignore sets and `shadowed`.
   - *The metarule, widened (§2.1), held by the host:* an amendment (kind 2) whose subject is the world's opener
     is admitted whatever the law (`openerAmends`, in `judge`), and the proposer half of the metarule is not
     asked of it. ROOT says each law must admit it, checked at creation; that would refuse every town object
     whose law reads `request.subject == new.owner` (Avatar, Env, Wake, Library, …), since the law grammar
     cannot name the opener and a package's law is written before any world. So the default law is unchanged and
     `world-inspect`'s `laws` gain a first row `{name: opener, clause, reading, host: true}`. test_wakes' Env
     test now expects the opener's amendment admitted.
   - *Powers (§2.2):* `world-turn` on `world` (`quiet`, `unquiet`, `settings`, `revoke`) and on a card
     (`retire`, `unretire`, `hide`, `show`, when the card has no such method), or the same as spells
     (`delvetalk world quiet / who: … / hours: … / reading: …`; `hostSpells` gains the card powers). Opener only,
     else `badSpell` clause `opener`; `reading` required (one line, no quotes). `quiet`/`unquiet`, `hide`/`show`
     journal `moderated {power, …, before, after, reading}` (replay: the opener's, `before` checked, applied as
     root's); a quieted principal's direct turns are refused `quiet` (new transient class: clause `until clock
     N`, `next` N); `retire` is the opener's amendment appending `law retired "<reading>": request.kind == 2 and
     request.subject == "<opener>"`, `unretire` removes it; `revoke` is a `commit` with `revokes` (judge lets the
     opener revoke any grant, so `world-revoke` is widened too). `world-settings {principal, reading, identity?,
     postQuota?, interpretQuota?, modelQuota?}` and the `settings` power journal a later `settings` entry under the
     opener (`settingsChange`; replay takes quotas only). `modelQuota` (default 2,000 a clock day) counts
     interpretations started and attempts (`modelDay`), refuses `interpret` `quota` with `next` the next day,
     nobody exempt. `world-status` answers `modelQuota {quota, used, next}`, `hour {hour, turns, refused {class:
     n}, interpretations, attempts}` (`hourCounts`, derived by `record`), `shadowed` and `ignored`.
   - *`unposted`:* `world-posted {principal, uri, unposted: true, reason}` journals `unposted {uri, reason,
     object}` (identity `unposted:<uri>`); the post's record (`Post.unposted`, a reply's `world-reach`) says so; a uri
     never recorded is a request error; the reservation stays settled.
   - Not built: a `before`/`after` past `maxEntryBytes` by CID in `blocks` (a root act that large is refused by
     `durable`'s entry bound); retries of a root act (every one is a new `root:<n>`). Tests: `tests/test_root.py`
     (each act's `before` and a reopen; an ignored entry, a shadowed one, the snapshot before it refused, `verify`,
     `unignore`; the powers), `tests/test_post_reserve.py` `Unposted`; the catalogue and AGENTS-API's class table
     gain `quiet`.

127. **The objects lane's three, and a handed-on reply's reach (host14).**
   - *Atomic make:* on foundation fixtures a body grafted by same-turn create-then-extend gives the made thing
     its methods, a form-derived input (`RainInput`) included, which run, survive a later `extend` and a reopen
     (`tests/test_make.py`
     `test_a_method_the_body_adds_runs_on_the_made_thing_and_a_later_layer_lays_over_it`); a body that
     declares less than the code below it is 5.138.
   - *Minting under a prefix:* a `create` whose `requireAbsent.object` ends in `/` takes the first free
     `<prefix><n>` (`mintUnder`: not an object, not created this turn, not held by a suspension's absence), so a
     squatted `garden/bell/3` refuses nothing; the creation's `object` names the id taken (a kind grafts
     `c.object.object`). Test: `test_a_prefix_mints_past_the_ids_already_held`.
   - *An await's receipt carries `hash`:* `Plan.obend` `Receipt` gains `hash: String` (the entry's CID;
     `receiptData`, `receiptReply`: one shape, 5.141); the `ended` receipt carries "" (its entry is the one being sealed). Pins re-recorded.
     Test: `ReceiptHash`.
   - *A handed-on reply keeps its reach:* a `send` of `receive` from a turn whose reach is not `delivery`
     carries that reach (`Send.reach`, journaled on the send and across a suspension; `TurnMeta.reach`), so
     the receiver's turn has it: prose that reached nobody stays "not addressed" at the directory and costs
     no model call. `test_hub`'s HandedToTheDirectory now states `reach: mention`, as the bridge must. Test:
     `tests/test_reach.py` `test_a_reply_handed_on_by_send_keeps_its_reach`. The original `replyTo` is not
     carried (the `post` is in the argument).

128. **A proposal carries its spell; the real hand-on checked (host15).**
   - *`spell` on a proposal:* `World.Proposed` and `Interpreted`'s `proposal` gain `spell: String`, the spell the
     proposal stands for (`proposalSpell`: `delvetalk <card> <method>` as the form names the card, a line per
     argument field, text with a line break as a `<<END` block, a case as its word; "" when a field has no
     spell form), journaled on the verdict, so a card that asks first can hold it and print it back
     (`proposalData`, one shape, 5.141). Replay reads the journaled verdict, so no edition bump. Tests: `test_reflection` Interpret,
     `test_hub` HandedToTheDirectory.
   - *The hand-on:* the objects lane's "still costs a model call" was reported before 5.127 landed. Through
     the real Bell and Directory, prose with no reach handed on by `Card.handingOn` is heard `silent` at the
     directory within the turn, nothing pending, `hour.interpretations` 0
     (`test_prose_that_reached_no_one_handed_on_is_not_addressed_at_the_directory`).

129. **`changed`, and `delvetalk objects ?` (host15; docs/METAPHYSICS.md §5).**
   - *`changed({since, prefix, after}) -> Since`:* `Since = changed {items: List<Change>, more} | denied`, `Change
     {object, version, height, by}`. `World.changes` (Store) is the height index, the inverse of `touches`: an
     admitted entry's creations (version 0) then its writes, a `created` entry's object, a root `set state`
     (`changesOf`, `recordActs`). `changedSince` walks it from the newest back to `since` (exclusive), the
     newest row per object, those under the prefix the asker may read, 64 a page, `after` the last object of
     the page before; `by` is the principal's handle when the world knows one. A derived read: no root. The
     index derives the same from any journal (no journaled field or judging changes), so no edition bump.
   - *`objects`:* `delvetalk objects ?` (fields `prefix`, `after`) is a host listing (`objectsListing`, 20 a
     reply; ids holding a DID only to a prefix naming one); every card's `?` ends with `objectsLine`;
     `objects` is no object's id (`validObjectId`). `me ?` already answered the avatar's usage
     (`test_arrive`). Tests: `tests/test_changed.py`.

130. **Two defects rehearsal run 12 found (host15).**
   - *A creation's law readings:* `makeObject` journaled `renderLaw laws` (no readings), so an object a turn
     created with a law text lost its readings on full replay (`verify`, a reopen without a snapshot): bare
     refusals and `inspect`. It keeps the creator's text (`lawText.getD (renderLaw laws)`). Old journals still
     replay without those readings. Test: `test_law` CreatedReadings.
   - *An open that journals nothing answers `{}`:* `settingsOp` and `nameOp` answered `Json.null` when the
     settings or name were already journaled, and `durable`'s settling pass set `delivered` on it (`PANIC at
     Lean.Json.setObjVal!` on stderr, reopening with a queue left). Test: `test_deliveries` Restart
     `test_a_reopen_naming_its_settings_settles_the_queue_without_a_panic`.

131. **`serve` after the transport's switch (host15; ROOT §1.4).**
   - `--socket PATH` places the public socket (the front then mounts no journal); the root socket is 0660 and
     `--root-group GROUP` gives it that group (`spec/native/serve.c` `listen_on`, `getgrnam`; an unknown group
     fails the start).
   - The opener's ordinary turns are admitted on the public socket. `serve` marks every public world request
     `resident: true` (stripping any the client sent; the root socket's is stripped too); `Session` sets
     `World.resident` for that request and erases the field before any digest; the settling pass runs with it
     false. `openerActs w p` (the opener, not resident) gates `openerAmends`, revoking any grant, the powers
     and naming an owner at `world-create`; arrival makes a newcomer's things as the opener whatever the socket.
     Replay never sees it: what a resident turn admitted, the opener's would have. `world-root` acts gain
     `unquiet {principal}`, journaled as `quiet` of zero hours (no new replay kind).
   - `world-dump {principal, object}` (root only): `owner`, `read`, `fixed`, `supervisor`, `ledger`, `activities`
     (each waiting suspension's hash, principal, intent, method, post or slot, deadline, interpretation).
   - Tests: `tests/test_serve.py` (`Placement`; `test_the_openers_ordinary_turns_are_the_public_sockets_and_its_privileges_the_roots`;
     `test_unquiet_and_the_dump`); `test_bridge` OpenerPosts now runs the opener's post as a turn. `deploy/serve.py`'s
     `Served` reads `--socket`/`--root-socket` from `extra`. The bridge's `ON_ROOT` skip is now reached only by a root op.

132. **The input check is exact (host15; the root's decision on EveryMethod).** A method without an input takes
   only `{}` (`argumentFits`); a record argument with a field the input does not declare is refused `typeMismatch`
   naming it (`extraField`, `misfitReason`: "<method> takes no field <f>"; a field it needs and lacks or holds
   of another type is named too, 5.141; a call's or run's reading "<id> <method>
   takes no field <f>."), for direct turns, spells, calls and deliveries alike (all reach `runFrame` or the call
   arms). Fixtures that called or sent a no-input method with an argument now pass `{}` (test_grants,
   test_authority, test_reflection's PROBE); test_principal's `ignored` asserts the refusal by name, then `{}`
   admitted. Replay never re-runs a method (Snapshot imports Ops, not TurnLoop), so no admitted entry is re-judged:
   no edition bump. test_properties' `malformed` no longer drops a `receive`'s host-filled `fields`/`misfit`.
   EveryMethod's one remaining violation is the policy card past the clip (objects lane).

133. **Law facts: the clock, the object, `old.F` (host15; LAW §4 A, E, H; KERNEL-HANDOFF §25 L).** `Facts` gains
   `clock` and `object`, set at every judging site (`judge` in Ops with `w.clock` and the object's id; `amendable`,
   the reprogram check, `methodAdmits`/`kindAdmits` where the id is known). `read` takes the old state: `old.F`
   reads it, or the empty value of the new field's kind at creation; `eqS` compares `request.object`. The kernel's
   fail-closed arms are gone. `#guard`s at the bottom of `Law.lean` (the `alive` clause at, inside and past its
   window, at creation, the object, the three-slot bound); `tests/test_law.py` `Alive` over a real object with the
   clock advanced. Facts are derived from the turn and the journaled clock: no edition bump.

134. **The package bound is the kernel's (host15; KERNEL-HANDOFF §25 item 1).** `Limits.maxPackageBytes` and
   `formSourceMax` are `Bounds.maxPackageBytes` (131,072); the four refusals (`creationInputs`, `buildCreated`,
   `checkSource`, `prepareProgram`) read "package source exceeds maxPackageBytes (131072 bytes)". Tests:
   `test_form_bounds`, `test_reprogram` Maximum. Landed in the other lanes since: Card.obend's and Policy.obend's literal (Bend cannot read the bound) and the
   front's `moduleTooLarge` read 131072 too. Still 16,384: `test_relation_limits` keeps 16,384-byte packages in the Workshop's `held`: a full Workshop's seed is one
   `created` entry, bounded by `maxEntryBytes`.

135. **`delvetalk-obend root-edit` (host15; ROOT §1.5; §7 item 1 of host14's queue).** `Host/RootEdit.lean`,
   dispatched by `PackageMain`. `--journal J --out J2 --reason R` with `truncate --height N`, `drop --height N`,
   `rewrite --height N --entry FILE` (one JSON object), `splice --at N --entries FILE` (JSON lines or an array);
   `--state DIR --reason R delete-world --name W` moves `W.journal`, `W.journal.blocks` and its snapshots to
   `deleted/W-<stamp>.*` beside `W-<stamp>.json` (reason, old head, what moved), refused while `serve` holds
   `journal.lock`. J must verify and not be open (`flock`; exit 75); J2 must not exist; J is never written.
   `reseal` keeps entries 1..kept and re-seals the rest: `previous`/`hash`; height 1 holds `replay` (and a fork's
   genesis keeps its `previous`), no later entry does; a `turn` equal to the old height becomes the new; an
   `ended` id is recomputed (`endedId` under the new height), and under a changed intent the send, change,
   publish and interpretation ids are too (`idOf`, matched against the old formula); every later string equal
   to an old entry hash or an old id is rewritten (`subst`: `resumes`, `delivery.id`, `identity.intent`, slots);
   a root `ignore`/`unignore` height follows its entry (an edit removing the entry it names is refused). The
   first re-sealed entry carries `rootEdit {command, reason, oldHead, at}`; `truncate` and a `drop` of the last
   entry re-seal nothing and carry no marker (J2 is a prefix of J). J2 is chained and replayed in full
   (`Snapshot.replayAll`) before it is written (`writeJournal`: J2 and J2.blocks); a failure writes nothing. Snapshots at or below the kept height
   are copied. The reply prints `oldHead`, `newHead`, `at`, `slugsChanged` and the table `{oldHeight, old,
   height, new, oldSlug, slug}`. Not rewritten: CIDs quoted inside checkpoints and states (an await's
   `Receipt.hash`), and `at://` citations elsewhere, which stop resolving as ROOT says. Tests:
   `tests/test_root_edit.py` (drop over an `ended` delivery, a resumed suspension and turns, then `verify`;
   splice back what drop took; truncate; rewrite; an edit that breaks replay; an open journal; delete-world).

136. **The stored path (host16; KERNEL-HANDOFF §15, §16 item 14; replay edition 4).** Every frame runs its
   object's state through the kernel's stored path, and the quoted path is gone.
   - *Runs.* `runFrame` builds a `Held` (`storeOf`: each declared relation's rows at the object's committed
     version, in key order as `canonicalRowsDropping` keeps them) and starts the method with `Turn.startEntry`
     on `storedState` (the relations emptied; their rows are fetched only when forced); `drive` keeps the
     `Held` for in-process segments (`Turn.resumeSuspended`). A pure method, a card (`renderCard`) and a
     derived view run `Package.executeDataEntryStored` (`storedPure`). Law, `lawReads`, handlers and
     migrations still take whole states natively (`executeDataEntry`). A checkpoint that may leave the
     process (`await*`, `interpret`) is `Held.kept`: collected, then every stored cell it still holds unforced
     made the native rows it stands for (`Turn.materializeStored`), so a journaled resumption needs no store
     at the version read (`Held.journaled`, `Turn.resumeEntry`) and those relations count as read whole.
   - *Roots by cells.* A frame's object is a root read by its cells (`Cells {scalar, fields, rows, spans}`,
     Ops; `recordCells`, joined per root; `recordRoot` still records a whole read, which covers the cells).
     `cellsOf` turns the kernel's `Reads` into cells: a span is the key of the last row its spine reached, or
     the whole key set. Journaled on the root: `{object, version, scalar: true, fields?, rows?: [{field, key}],
     spans?: [{field, through?}]}`; a whole root stays `{object, version}`; `viewField` is `fields` (the old
     `{object, field, key: "*"}` root and `fieldRoots` are gone). `rootAdmits` (one rule for `judge` and a
     journaled resumption): the whole-object rule (`movedRootAdmits`), or the cells current (`cellsCurrent`:
     no scalar changed, no field read changed, no key read touched, no key at or before a span's last touched)
     and the turn's own edits clear of what changed since (`editsAdmit`). The cells only admit more; on a
     resumed turn's own object the field rule (5.1) still admits whatever it read.
   - *Bound and ledger per cell.* A write is refused `capacity`, clause `maxCellBytes`, when its scalar part
     or a row of a relation it edited passes `Bounds.maxCellBytes` ("the rains row keyed {...} of b pass
     maxCellBytes (262144 canonical bytes)"; `cellRefusal`, `editedFields`); a migration's result
     `programRefused` the same; a seed the same at creation. The storage ledger charges `cellBytes` (the
     changed cells of the edited relations, every cell of a created object). `Limits.maxStateBytes` and
     `maxSeedBytes` are gone; a grant's `fixed` is held to `maxCellBytes`. `world-inspect` adds `scalarBytes`.
   - *Kernel.* `Turn.startEntry`/`resumeSuspended`/`resumeEntry` are the stored runners (renamed from
     `…Stored`); `quoteAt`, `argumentAt`, `shapeTree`, `startActivity`, `prepareStart*`, `prepareResumeEntry`,
     `runResumed` and the quoted runners are deleted; `storedStart` takes every argument natively when the
     store holds no relation; `materializeStored`; `cellOverBound` and `changedCellBytes` take the relations
     a write edited and run in linear time; `Profile.profile` fetches through the store. `turn-start` and
     `turn-resume` always run stored (`stored` names the relations; the reply carries `reads`).
   - *Measured* (persvati, `measure/stored_turn.py` in the lane's scratch, 200 turns of "write `count`, read row
     2" through the JSON-lines driver): 2,048 rows, median 72.0 ms (best 27.7) at foundation f687cc3, 13.3 ms
     (best 9.4) after; 0 rows 0.42 -> 0.30 ms. What is left of the 13 ms is the write's own O(state) work:
     `conformsUnder` of the whole written state, its `stateCid`, and `storeOf`'s walk (§7).
   - No `test_tariff` pin moved (its activity cases compare a run with itself). Tests: `test_relation` Cells
     (a span journaled; a write past it leaves a resumed turn current; another object's view stale inside its
     span and current past it) and CellBound; root shapes in test_turn_world, test_outbound, test_commute,
     test_changes, test_world_object; edition 4 in test_replay_edition and test_serve; test_relation_limits
     bounds `scalarBytes`.

137. **The journal as a block store, and a streaming open (host17; §7 item 2 of host16's queue).** A journal at
   `J` is the chain `J` (one link a line, `{at, bytes, hash, height, previous}`) and the block store `J.blocks`
   (each entry's canonical record, the entry without `hash`, at `at`; CID of the record = `hash`).
   - *In memory* (`World.entries : Entries`, `Blocks.lean`): every CID, each record's span and the CID index
     (persistent structures, so a step extending the session's world copies nothing), and the step's unwritten
     entries. `Entries.get?` reads one record by `pread` (`readAt`, `implemented_by` over the `delvetalk_handle_pread`
     extern in `sync.c`: a written record never changes, so the read is a function), checks it against its CID and
     decodes it; every reader of an entry goes through it (`retained`, receipts, history, offers, `stateAt`,
     `touchEdits`, `blockItems`, `sourceText`, the scans of `world-sources`, `world-grants`, `world-resolve`).
     `World.blocks` and `World.modules` name the entry carrying each checkpoint block and source; `Touch` is
     `{version, height}`, its edits read from its entry when the moved-root rule asks (`touchEdits`).
   - *Append* (`Session.appendJournal`): the records to the store, synced, then the links to the chain, synced.
     `maxEntryBytes` bounds a record; the journal bound counts both files, exactly (`linksAt`).
   - *Open* (`Snapshot.openJournal`): the chain read whole and linked (`chainOf`, `Link.ofLine`, no JSON built),
     entry 1 for the edition, then `reopen`: the newest snapshot that passes, whose indexes (`indexJson`: every
     index `record` derives, `anchors` among them) are installed instead of reading the entries before it, each
     object checked against its anchors (`checkAnchors`), then the tail replayed, each entry checked against the
     chain (`checkedEntry`). Replay from 0 (`replayAll`) is the slow path; `verify` compares every snapshot's
     store and indexes with it. Snapshot edition `delvetalk.snapshot.v3`. No replay edition change: the entries,
     what they hash and what replay derives from them are as they were (`anchors` derives from any journal, as
     `changes` did in 5.129).
   - *Measured* (persvati, `measure/journal_open.py` in the lane's scratch, 20,000 bump turns through the JSON-lines
     driver, intents of 208 bytes; snapshot every 1,000; an empty process peaks at 70 MB): foundation 3c96c27d, a
     22.3 MB line journal: open 5.25 s, 284 MB peak; now, 21.2 MB (chain 4.0, store 17.2): open 0.19 s, 124 MB
     peak; with 7-byte intents (17.2 MB): 0.16 s, 109 MB. About 1.4 KB a held entry remains at open (the chain,
     the receipt and change indexes, the snapshot's decoded index). Building the 20,000 turns: 7.9 s before, 8.9 s
     after (a record is encoded once more than its hash needs).
   - `maxJournalBytes` is 4 GiB; `maxJournalEntries` (1,000,000) binds first for small entries. `world-open
     {snapshotEvery}` sets the cadence per process; an `ignore`/`unignore` re-derives the store from the newest
     snapshot below the height it names (`Session`, `Snapshot.reopen`) and writes a snapshot at once.
   - *Tools.* `delvetalk-obend migrate --journal OLD --out NEW` is the one reader of the line format
     (`Migrate.lineEntries`); an open of a line journal is refused naming it. `root-edit` reads and writes chains
     and stores (`journalEntries`, `writeJournal`); `delete-world` moves the store too. `transport/journal.py`
     (`links`, `records`, `entries`, `tail`, `size`, `copy`) is the Python reader for the hand's probe, the
     harvest, the rehearsal and the tests; `tests/wire.py` `write_journal` writes what a test forges.
     `deploy/verify.sh` copies each store with its chain; `backup.sh`'s rsync takes the chain before the store.
   - Tests: `tests/test_block_store.py` (an open from a snapshot answers every read as `verify` and an open
     without snapshots do; the line format refused, migrated, verified); every test that read or forged a journal
     file now reads `transport.journal` and writes `write_journal`; `test_root` (the snapshot written at an ignore,
     the one before it refused when it is gone); `test_journal_bound` (both files).

138. **A layer laid in the making has its stack's shape (host17; §7 item 6 of host16's queue; replay edition 5).**
   The objects lane's failing input: a Kind's `make` creating a record and extending it with the cistern's body
   in the same turn; the next `cistern/1 pour {text}` was refused `typeMismatch`. The body names only `write`
   in `methods()` and declares no `relations()`; `buildCreated` compiled the stack and took the top layer's
   declarations alone, so RECORD's relation went undeclared and the pour's row insert failed, where a later
   `extend` (`prepareProgram`) kept the code below's public methods, relations and law shape. Now the stack
   has one shape however it is compiled: `compileObject` compiles the code below a layer (`lowerInputs`) and
   keeps its exposed methods, its relations when the layer declares none, and its law shape when the layer
   declares no Bend law (`Built.lawShape`, `Built.shape`); `makeObject`, the root `program` act and
   `prepareProgram` (now `compileObject` plus the migration and state-type checks) read it. Replay of a
   layered creation derives the new shape: edition 5. Tests: `tests/test_make.py`
   `test_a_body_laid_in_the_making_has_the_shape_a_later_extend_gives` (refused on the binary before, the
   same-turn body's methods and forms equal a later extend's, a reopen); the objects lane's `Kind` with the
   body laid in the turn (its scratch `Kind-inturn.obend`) passes all of `test_kinds`.

139. **The law's relational atoms (host17; KERNEL-HANDOFF §25 item M; LAW §4 B, C, D, F; edition 5).** The kernel's
   grammar (lane/kernel14) is denoted in `Host/Law.lean`, the fail-closed arms gone:
   - `count(SIDE.F where COL == TERM)`: the rows whose column canons to the term's value; a reference, so the
     quorum `count(new.G) <= count(new.F where C == V) + N` is a comparison. `memberData` reads every term
     (a numeric reading as a natural) and serves the filter, membership and `changed`.
   - `changed(new.F.COL) by TERM`: every row the write changed (`changedRows`: gone by canonical bytes less
     what retention evicted, and new) carries the term in its column.
   - `TERM in "O".F.COL` and `under "O"` read `Facts.reads`, the states of the cited objects (`citedStates`,
     closed under the citations of each cited object's `law` text, `lawCitations`, `Limits.lawDepth` 4).
     `under "O"` judges the write by every clause of O's `law` field at depth − 1; depth 0, an absent object,
     a non-text or unparsable law is false. The law-text parser (`parseLawText`, `renderLaw`) moved into
     `Law.lean` beside `denote`.
   - *Roots.* `withLawReads` adds every citation to the write's roots at the version read (so a cited
     object moved since is `staleRoot`, and replay re-judges from them), within `maxRoots`; a cited object
     the subject may not view refuses the write `lawRefused`, clause `lawReads`.
   - *Acceptance* (creation in `makeObject`, amendment in `judge`): `citationRefusal` refuses an `under` of
     a missing object, of one whose `law` does not parse, or a cycle within `lawDepth` ("under: a cycle of
     citations: a -> b -> a"); the metarule (`amendable`) judges with the cited states. `world-inspect`
     answers `cites`.
   - Tests: `Law.lean`'s `#guard`s (filter, quorum, changed by with eviction, cited membership, under at
     depth, a cycle, a non-law); `tests/test_law.py` `Atoms` (an instance judged by its kind's law as it
     changes, the kind a root, a reopen; a missing citation refused; a private kind refusing `lawReads`;
     rows changed by whom, a cited roster, a quorum, a reopen). The objects lane may now delete the Tide's
     and Deal's predicates (KERNEL-HANDOFF §25 M, last item).

140. **Scratch worlds and references across worlds (host17; docs/FEDERATION.md §2, §3; edition 5).** The private
   heap is gone: no `heap` envelope, no `DIR/heaps/`, no front route under `/heap/`.
   - *A scratch* (`Serve.scratchOp`): `world-scratch {principal, name, from?: {world, height?}}` writes
     `DIR/scratch/<principal>/<name>.journal`: empty with the sealed library and the principal its opener, clock
     and librarian, or `from` a world (or the principal's other scratch) by `world-fork` at a height, carrying
     what the principal may view. Its turns name `world: scratch/<name>` beside the principal. At most
     `Limits.scratchPerPrincipal` (2) at once (a third is refused `capacity`, naming the oldest), each under
     `scratchJournalBytes` (16 MiB) and `scratchObjects` (1,000; `world-open {maxObjects}`, `World.objectBound`).
   - *Expiry*: `serve` keeps each scratch's home-world clock at its last op (`Server.scratches`, and `<name>.last` beside its journal, so a restart does not renew it: `used`)
     and, on the home world's `world-advance`, discards each `Limits.scratchMinutes` (360) past it: session,
     journal, block store, snapshots (`discard`, the one deletion; a scratch is not custody). An op on it then
     is "scratch/<name> expired at clock N; open it again with world-scratch". The root act `expire {principal,
     scratch}` (root socket) discards one now, logged by the hand only. `serve-status.scratches [{principal,
     world, lastTurn, expires}]`; the home `world-status.scratches {open, expiring}` (within 60 minutes).
   - *An exit*: `world-cite {principal, scratch, receipt, identity?}` reads the scratch entry and journals it
     whole in the home world as `cited {world, receipt, entry}` (`Ops.citeOp`, identity `cite:<hash>`; the entry
     must be its hash's). `make` into a shared world is the client's, from its checked source.
   - *References* (FEDERATION §2): a `Reference {world, object}` with a world names that world's object (a
     scratch as `scratch/<name>`, the reader's own). `view` and `card` of one read the other world's own
     answer under the reader (`World.foreign : Foreign`, a closure `serve` builds per request over its held
     worlds, `foreignFor`; cleared after the step), and the entry journals `cites [{world, object, version,
     stateCid, height, head}]` (`TurnState.cites`), not roots: a foreign read can go stale without refusing the
     turn, and replay, which never re-runs a method, reads nothing foreign. A world not served here is
     `refused {clause: foreignWorld}`. `world-view`/`world-card` of `<world>:<object>` (the text before the first
     `:` a world served here) answer that world's reply with `asOf`.
   - Tests: `tests/test_scratch.py` (a scratch apart from the town and from another principal's, the limit and
     the root act; a fork carrying only what its principal may view; expiry by the town clock, files gone, a
     citation kept; a turn reading another world's object and citing it; the ops' `asOf`); `test_serve`'s
     scratch and stateless worlds; the front's scratch routes in `test_http`.

141. **One shape per answer (host17; §7 item 5 of host16's queue).** Every object compiles from `world/lib`, so no
   call site holds an older `Receipt`, `Proposed` or `Interpreted`: an await's reply is `receiptReply` (the receipt
   with its `hash`), a proposal `proposalData` (with its `spell`), a `proposals` verdict its items, and a reply of
   several spells is always `proposals` (the first-item fallback for a Response without that arm is gone).
   `misfitReason` names the field that does not fit: one the input does not declare, one it needs and lacks
   ("bump2 needs field n"), one of another type ("bump2's field n is not of its type"); the bare "argument does not
   conform" is left only for an input that is not a record of fields. Test: `tests/test_make.py` `Misfit`.

142. **hob answers a question (host18; the owner on /play/kinds, 2026-10-11; the second playtest's D2).** A fifth
   answer, `say: <text>`, is the verdict `said {text}` (World.obend's `Interpreted` gains `said`): at most
   `Limits.saySentences` (2) sentences and `Limits.sayChars` (300) characters, cut only at a sentence end outside
   quotes and backticks (`sayClip`), and nothing when the first sentence alone passes (`saidVerdict`). Only an
   explicit `say:` is an answer: prose with no prefix and no spell is `none`, silence (the second playtest stopped
   at 69158 on two paragraphs of the model's own posted as hob's line). `replied` is only `card`. A Response that
   cannot carry `said` hears `unclear`. The play page follows the turn and every turn it handed on (`follow`:
   each settled receipt's `sends`, delivered under the same principal with the send's id as intent) while any is
   suspended or undelivered, up to `WAIT_MAX`, then shows what they offered; the turn line names the card
   addressed (`bridge.turn_root(receipt, addressed)`). Tests: `test_interpret_object` (say, both bounds, an
   example's full stop, prose, 69158 verbatim), `test_interpret_text`, `test_http.Play` (a question to kinds). No
   replay edition change: the verdict is journaled, not re-derived; replay's known verdicts include `said`.

143. **A post quoting a card casts nothing (host18; the owner's outreach on delve.town, 2026-10-11).** The root
   menu quoted under a greeting (its spells indented two spaces) was read as a spell and admitted `env observe`
   for the owner (entry 147). Now `Spell.parse` casts a `delvetalk` line only at the margin: an indented one, at
   any depth, is an example (the quoted fallback, which cast a 4-space line when nothing else stood, is gone;
   inside a spell's fields an indented spell line neither ends nor replaces it). A text holding a card's header
   line (`cardHeader`: `✾ `, `Seven doors.`, `KIND `, a line ending `Make one:`) beside any `delvetalk` line is
   `Parsed.quotation` (`quotes`), refused `badSpell` clause `quotation` with the card's usage; `spell-parse`
   answers `{quotation {reason}}`, and hob's text that quotes a card is `unclear`. Fixtures: the four recorded
   indented rows and the playtest's two indented plantings no longer cast (`tests/fixtures/spells`;
   `test_spell`'s pair moved to the margin); `test_host_spell.Margin` (the owner's post, the root menu v4 preview
   under a greeting; a margin spell; the same indented by two spaces, four, a tab, among other lines). A post that
   is one spell block and nothing else (`wholeSpell`: its non-blank lines a `delvetalk` line and field lines, each
   starting with the first's indent, bare or inside one ```` ``` ````/```` ```text ```` fence) is dedented and cast:
   a Zulip code block, a spell pasted with its indent (`Margin`'s block cases). Several spells: 5.148; Bend's
   reduced reader is the objects lane's to delete (H1).

144. **A refused turn offers nothing (host18; the objects lane's `sealed/1 write`).** A turn's offers and publishes
   happen only if it is admitted: `commit` drops `offers` and `publishes` from a refused entry, so the resident
   hears the refusal line and the card as it stood, never "#1 is written". No replay edition change (what replay
   derives from an existing entry is unchanged; new refused entries carry less). Test: `tests/test_law.py`
   `RefusedOffers`.

145. **A refusal under a kind's law names the clause that failed (host18).** `Law.refusal` follows a refusing
   clause that is `under "O"` into O's law text (`innermost`, through further `under`s within `lawDepth`) and
   answers that clause's name and its reading there: `refused small: two at most`, not `refused kind`.
   `refusedBy` is its name; the judge's `reading` is the cited one, else the object's own (5.154). Tests:
   `Law.lean`'s `#guard refusal`; `test_law.Atoms` (the kind's clause and reading).

146. **A sum left of `<=` (host18; the kernel's grammar file, by the coordinator's leave).** `old.last + old.gap <=
   request.clock` parses: `ATOM ::= … | REF + TERM <= TERM`, a sum whose first part is a reference
   (`LawTerm.referenceSum`); `==` still starts with a reference and `1 + old.last <= …` still refuses. `denote`
   already read sums. Proofs: `parse_accepts`, `render_reads_back` (`canonical`), `refusals_name_what_and_why`.

147. **A `text 0..N` field may be left out (host18; the objects lane's `kinds make` and its `id`).** `Spell.fit`
   needs only the fields that are not `Field.optional` (a text bound starting at 0); one left out reads as the
   empty text, so `delvetalk kinds make / name: lamp / of: record` makes a kind. The host's usage prints such a
   field `<optional text, up to N characters>` (`spellHint`; Bend's `Card` hint is the objects lane's). Tests:
   `Spell.lean`'s `#guard`; `test_host_spell.Clauses`.

148. **Several spells in one post: a turn each (host18; the coordinator's decision).** A direct `receive` whose text
   holds two or more spells at a line's start (`Spell.segments`, also hob's split; not a quotation) runs
   `runSpells`: each spell, with the lines after it, is its own turn as if posted alone (identity the post's plus
   `#1` .. `#3`, digest the post's and the ordinal), judged alone with its own receipt, so a law refusal of one
   never sinks the others; a fourth and later are one refusal `#4`, `badSpell` clause `tooManySpells` naming how
   many were not cast. The reply is `{status: "spells", turns: [...]}`, in order. The bridge drafts one reply
   carrying every line (the last receipt the draft's); the play page and the agent route show each turn.
   (`runTurn` dispatches; `runOne` is the single turn.) Tests: `test_spell_turns` (four turns, a misfit standing
   alone, a retry), `test_bridge` (two spells, one draft).

149. **`receive` hears the spell the host read (host18; fungus H1's host half).** When a card's `receive`
   declares `spell: {card, action}`, the host fills it (`heardArgument`, `castData`): the spell as written when
   it lacked fields (`castSpell`'s `unclear` arm), else what `Spell.parse` reads in the text, `{card: "",
   action: ""}` for none; a card that does not declare it is unchanged (the shapes tried are fields, with spell,
   with misfit, with both). So the objects lane can delete Bend's last spell reader (`world/lib/Spell.obend`
   `parse`, `Card.spellMissing`, `spellAction`). `withFields` is gone. A derived `String` field is `text
   1..formTextMax` (`formKind`): required; only a form or kind that declares `0..N` makes one optional. Test:
   `test_spell_turns` (a missing seed reaches `receive` with `Cast plant`; prose with `" "`).

150. **A send refused transiently is delivered again (host18; replay edition 6).** The commonplace lost words handed
   on to it when that delivery was refused `capacity` after the card's turn was admitted. Now `record` keeps a
   delivery refused with a transient class pending (`redelivered`): `attempts` counted on it and `next` the clock
   after the refusal's; `deliver` and `settleAll` take the first pending send that is `deliverable` (its `next`
   passed), so it runs again once the clock moves, and the refusal of its `Limits.deliveryAttempts` (4)th attempt
   is its last. The identity does not bind on a transient refusal, so the retry is the same delivery. Replay
   derives the kept send: edition 6. Tests: `test_deliveries.Redelivery` (a spinning receiver refused `budget`,
   unlocked, delivered when the clock moves, a reopen; a send refused every time dropped after four).

151. **`world.principal {handle}` (host18; the objects lane's `offer / to:` and `lend / to:` a handle).** World.obend's
   protocol gains `principal({handle}) -> Named` (`named {principal}` or `unknown {}`): the registry's principal
   for a handle, case folded as a DNS name is (`Ops.principalNamed`, which the host's `quiet`/`unquiet` and
   `lend` spells now share), `me` the turn's subject. A read: no root, nothing journaled beyond the turn. Test:
   `test_world_object.PrincipalByHandle`.

152. **A line whose name the form lacks ends a spell's fields (host18; the second playtest's D7, 69082).** `Spell.fit`
   takes the bound fields up to the first whose name the form lacks (`hob: still owed …`, `smell: sweet`), as a
   prose line with a colon already ended them: what follows is the reply's prose. So a spell is no longer refused
   `unknownField` for a trailing line; a misnamed field is a missing one (`unclear`). `unknownField` stays the
   lens spell's (`set` naming a field no lens has). Tests: `Spell.lean`'s `#guard`s (69082's shape),
   `test_receive.Cards` (a `hob:` line after a whole planting plants), the recorded `fit` rows re-recorded.

153. **A card hears a misfit only when it reads words (host19).** Replaced by 5.163: no card hears a misfit, and
   `readsWords` (a card's `policy` field as the signal) is gone; the world's one `policy` object is hob's.
154. **Every law refusal carries its reading (host19; the objects lane's finding on a law given at creation).**
   A law given at creation kept its readings since 8e015ca6 (`makeObject`'s `given`), but no refusal carried a
   `reading`: each site composed `reason` itself ("refused <clause>: …"), and test_properties split it back
   out. Now `Refusal.reading` is the refusing clause's reading wherever the law came from (the package, a law
   given at creation or by amendment, the kind's clause an `under` cites, a Bend verdict's `reading`, and the
   host's own clauses `fixed` and `lawReads`); `commit` journals it, `Refusal.voiced` writes `reason` from it,
   and `publicRefusal` shows both. `readingOf` is gone. The amendment rules name their clause: `law syntax`
   (the parse error its reading), `under` (a citation that does not stand) and `amendable` (the self-sealing
   rule, its reading the old message naming the proposer); the host's own `noGrant`, `grantSpent`,
   `notGrantor`, `denied`, `law` and `lawReads` say why. A call site hears a refused amendment, reprogram or
   layer of another object as `{clause, reading}` with the bare reading (`dryChange`), never "refused …" twice. No replay edition change: replay checks a refusal's
   class, not its words. Tests: `test_law` `LawAtCreation`, `Readings` (the outcome's and the public
   projection's `reading`); test_properties holds every `lawRefused` to a clause, a reading and the reason
   voiced from them.

155. **`context.sender` (host19; replay edition 7).** `Abi.Context` gains `sender`: the object whose send the
   turn delivers (a `send`, a subscription's `changed`, a supervised activity's `ended`), "" for a turn a
   principal began. It is the turn's (`TurnState.sender`, from `TurnMeta.caller` when the turn is a
   delivery, and from the journaled activity's caller on a resume), so every frame of the turn sees it, while
   `caller` stays the frame's calling object: in a delivered `rain` that calls the ledger, the ledger sees
   `sender=weather caller=bell`. A Bend law's context carries it too (`Proposal.sender`), and replay reads it
   from the pending delivery the entry consumes: edition 7. So the weather's rain may be credited to the
   weather (`author: if context.sender != "" then context.sender else context.principal`, the objects lane's).
   `fitRecord` keeps an object compiled under an older Abi running. Pins re-recorded (Abi is in every
   closure). Card's `stranger()` and the tests' hand-built Contexts carry `sender: ""`. Tests: `tests/test_sender.py` (a delivery's frames, a call's, a direct turn's; a Bend
   law refusing a sender, the same law admitting a call, a verifying reopen).

156. **Three of the second playtest's host rows (host19; the coordinator's list after the objects lane's fixes).**
   - *D3, a drafted thing.* An interpretation's offered forms keep their `source` fields (`OfferedForm`: the
     spell form and its source names; `Spell.Form.ofData` alone dropped any form with one), and a model's
     ```obend block is the value of the first source field the spell lacks, as `withFence` binds it for a typed
     spell. A reply that is one block and no spell settles the one offered form that takes source; a spell
     naming a source form without a block is `unclear` naming the field. So `workshop make` drafts: hob's Bend
     is the `check` form's `source`, the draft is held. Test: `test_workshop` (a fenced reply held as #1).
   - *F2, a law written inline.* `adopt / law:` takes a law that starts `law ` as the clause set itself (no
     source root), else the id of a kind or page as before; the usage (`adoptLine`) and an unknown id's
     refusal say both. Test: `test_extend.HostSpells` (inline with its reading, a syntax error, an unknown id).
   - *D10, the card a turn line names.* `runTurnWith`'s reply carries `object`, the card the turn ran on (a
     spell's card as resolved); `bridge` drafts, `spell_line`, the play page's `turn_line` and the hand's
     `speak`/`ask` name it instead of guessing from the first root (`kind/room` for an entered room). Test:
     `test_rooms.Floor` (a spell entering a porch names the porch).
157. **A card's own refusal refuses its turn (kernel16; playtest 2's D6; replay edition 8).** `refuse(line)` takes
   any String the card computes (KERNEL-HANDOFF §26), and the kernel answers it as `Turn.Step.refused line`, an
   outcome, where it was a `turn refused: …` error the turn loop journaled `evaluation` (transient). `drive` throws
   `Abort.card (cardRefusal self line)`; `finishTurn` commits it with nothing of the turn (no writes, creates,
   sends, offers or publishes; a supervisor hears it only when the await timed out). `Ops.cardRefusal`: class
   `cardRefused`, binding; `clause` and `reading` from `refused <clause>: <reading>` (the clause one word of at
   most `maxMethodBytes`, split at the first `: `), else clause `card` and the line whole; `object` the card that
   refused, a callee as well (its refusal refuses the caller's turn, as before); the reading within
   `Limits.maxRefusalBytes` (4096; `withinBytes` keeps the whole characters that fit, then `…`). `voiced` writes
   `reason: "refused <clause>: <reading>"` as for `lawRefused`; `publicRefusal` shows a stranger the class and root
   only (the reading is computed and may carry state). Being binding, a delivered send a card refuses is consumed,
   not delivered again. The catalogue (`transport/static/catalogue.json`) has the class; `evaluation` now means
   only a host or kernel failure. Edition 8: a class replay checks, checkpoint term tag 26 of a new shape, the
   packets of every refusing program. Test: `test_card_refusal` (a reading from the state, the write before it
   dropped; the `card` clause; a callee's refusal names the callee; a long reading kept within its bound; a
   stranger sees no reading; reopened).

157. **The commonplace in the host's strings (host20).** The first card is `commonplace`: `unknownObject`'s reason
   and the refused turn's hint, `otherCard`'s reason and its usage, say "the commonplace lists the doors"; a card
   with no spells says "reply in words and hob places them". `Spell.cardHeader` matches the commonplace's head
   line by its door count (`doorsHead`: `One door.` or `<count> doors.`, as `Menu.trieHead` writes it). Test:
   `test_host_spell.Margin` (a quote from the door line on, and a one-door head, cast nothing).

158. **A target checked whole (host20).** `world.checkObject({object})` answers `Checked` for what a readable
   object runs: its whole source closure (`Ops.checkObject`: `resolveInputs` of its inputs, the library modules
   its pin names, the base package and every layer) compiled for `initial`, the diagnostics as `checkSource`
   writes them (`checkDiagnostics`, shared); an unknown or unreadable object is `refused unknownObject`; it counts
   against `checksPerTurn`. Workshop's `check / target:` calls it, where it checked `inspect`'s entry source, the
   top layer alone (`import must name an earlier supplied module: ./Record.obend` on a bell or the garden).
   Pins re-recorded (World is in every closure). Test: `test_genesis.Checked` (bell/1 and the garden, each
   `layer over`, check clean; a missing card is named).

159. **Carry and the no-wipe gate (host21; OVERHAUL steps 0 and 1; FOUNDATION §2).** No replay edition change: a
   `carried` genesis is a new tag, and every journal that exists replays as before.
   - *The gate.* `deploy.genesis` lists every world journal under `--towns` (`DELVETALK_TOWNS`; compose mounts
     `/var/lib/delvetalk` read-only into `delvetalk-ops` at `/towns`) other than its own and refuses, naming each
     with its height, unless `--wipe-with-the-owners-word R`, which it writes on the commonplace and admits as
     the town's first line. `deploy/carry-check.sh [--old-image I | --old-binary P] [--leave O]... BINARY BACKUP`
     is the merge check the root runs on hbox: the newest pulled tarball replayed from genesis
     (`verify.sh --full`) and carried (`transport carry`) under the candidate; green, green-breaking (the deploy
     carries) or red. `backup.sh` writes each world's head snapshot into every tarball (`verify.sh --snapshot`).
   - *The host.* `delvetalk-obend carry --from J --out J2 --reason R [--library DIR] [--leave OBJ]...`
     (`Carry.lean`): J only read (a verified chain, its flock free), J2 must not exist. The world is read from
     J's snapshot at its head (`verifiedBody`, then `readWorld`: the index keys in `readKeys` laid over an empty
     world's, so an older binary's v3 body is a contract on those keys alone, then `install` and
     `checkAnchors`), never from J's entries, which need not replay here. `carryWorld` rebuilds every object
     under this binary (`rebuilt`: the sources seal to the pin, the state conforms to the type this compiler
     makes, its rows are canonical under its relations; then this host's type, bounds, method table, law shape,
     packet, relations, fixed and declared fields) and checks every suspension (`resumable`: the method compiled,
     the checkpoint's packet this host's, its tokens decoding under this kernel's dictionary). Each failure
     refuses the carry, all of them listed by name. `--leave OBJ` carries an object retired (`Ops.retiredLaw`,
     now also the root `retire` and the card power's, one clause), its state as it was and its suspensions
     dropped, each supervisor told `ended {how: broken}` as a pending delivery (`droppedEnd`, `endedField`).
     `--library DIR` seals DIR as serve seals it (`Serve.sealLibrary` into J2's directory) and makes it the
     current library when its pin differs (`carriedFrom.library {from, to}`).
   - *Moves with migrations* (host24). With `--library DIR` the image's packages are that library's modules and
     `DIR/../objects` (by name, as `deploy/seed.py` names them), and its bodies are `--body OBJ=FILE` (one per
     `deploy/genesis.py` KINDS row and the commonplace's, passed by transport/carry.py). `movedInputs`: an
     object's own modules named as the image names one take its source, a module the new source newly imports
     comes before it, its first layer takes the body its kind names (or its own id names), laid over the module
     below as extend lays one, later layers stay, `library` the new pin. A kind takes its body as its `body`
     field. Compiled (`moved`): the same pin and body keep the object as it was; else it moves (version + 1, the
     new type, bounds, methods, relations, fixed, packet). Its state stays when it conforms to the new type;
     else the package's `migrate` (`Ops.compileMigration`, its argument type read by the state as it was;
     `Ops.runMigration`, the two shared with reprogram) converts it, checked to conform, canonical under the new
     relations, within `maxCellBytes`, moving no fixed field. A moved object's suspensions are dropped (the code
     they waited in is gone), supervisors told; one whose package offers `carried` (`~carried`, as a body's `~made`)
     is told `carried {}` once (`rearmed`: a pending delivery `carried:<id>` in the genesis, from no object, under
     the carry's principal), which the first settling runs: the tide waits again for the tick its last one scheduled.
     A moved object holding its package's law as it was (`lawUnder`: its law renders as the old package's) takes the
     new package's law and readings when they changed (`law {before, after}` on its move); one an owner amended
     keeps its own, named (`kept [{object, law}]`). Such an object (its law its package's) also takes its new package's
     top-level `rule`/`want` lines as `makeObject` places them (`placedUnder`): a row its old package placed that the new
     one changes or drops taken off, each line whose name its text and rows leave free placed under its owner, `since`
     1 (`placed`, `unplaced` on its move); hands' rows stay. Only a package-declared law is the carry's: a law given at
     creation (genesis's `RECORD_LAW`, a kind's `under`) and a kind's `law`/`voice` state are genesis's, laid by
     `deploy.genesis refresh` at the end of the transport's carry (objects lane). Left, retired at its old pin (its `retired` clause reading the reason's first line within 200 bytes; the
     carry prints the whole reason in `left`): an
     object whose own entry package the image no longer ships (`gone`: Wake, Env), one whose move refuses (no
     compile, no `migrate` for a state that does not conform, a `migrate` that refuses), and one `--leave`
     names. Only an object that does not rebuild under its own pin refuses the carry, by name.
     `carryGenesis`: `carriedFrom {world, height, cid, replay, reason, entries, library?, carriedFrom?}` (the old
     genesis's own when it was a carry), `index`, `left`, `moved [{object, from, to, migration, before, after,
     body?, law?, placed?, unplaced?}]` (pins, `migrate` or "", state CIDs, `body` when it took the image's body), `kept`, `dropped`,
     `rearmed`. J2 is replayed from its genesis and every object's state
     CID compared with the snapshot's (a moved one's with `after`) before it is written. Prints `{status:
     carried, hash, slug, replay, carriedFrom, library, objects, pending, suspended, grants, posts, receipts,
     left, moved, kept, dropped, rearmed}`; the transport's check compares a moved object with `after`.
   - *The transport.* `python3 -m transport carry --from OLD --to NEW --reason R [--leave [W=]OBJ]... [--obend B]`
     (`transport/carry.py`): every world journal of OLD carried with the config's library; the transport's files
     copied (serve's never: journals, snapshots, lock, `library/`, `root/`, `scratch/`, sockets, pid files);
     `publications.after` and each `awaiting` turn's height set to 1; each carried world checked in a throwaway
     copy beside it (every object's state CID against the old head snapshot and its card rendering for its
     owner, every old receipt's slug resolving to its height, a `world-advance` admitted); then, on each world
     that checked clean, `deploy.genesis.carried` (genesis's laws and kinds as the image stands, as the opener),
     a `{world, refresh: row}` line per slot, any status but `refreshed`, `current` or `left` failing; the hand's
     line last.
     `deploy/playtest.sh --from RUN` carries an earlier run instead of a genesis.
   - *Size.* A carried genesis holds the store with its compiled types and method tables: playtest 3's (51
     objects) is 1.4 MB of record, past `maxEntryBytes`, which bounds appends only (`writeJournal` writes a
     genesis whole, as a fork's always was).
   - Measured on hbox: playtest 3 (`run-20261011-084303`, edition 6, height 489, 51 objects, head snapshot by its
     own binary) carried to edition 8 in 5 s with `--leave wake/did:plc:6amo7col5h4ciq2gpm5eur7b` (the one
     suspension, the opener's wake's `due`, was checkpointed under a packet this compiler no longer emits);
     transport's check: 51 objects at their state CIDs, 51 cards, 489 receipts, a new entry. The v7 town's
     newest backup (`delvetalk-20261011T183505Z`, height 73, 28 objects) the same with nothing left.
   - Tests: `tests/test_carry.py` (every object and receipt across, a carried suspension settling and a spell on a
     carried thing after, a fresh process replaying it; an object left retired; the library shipped sealed and the
     old pins compiling; refusals without the snapshot, over an open journal, into a journal, an unknown
     `--leave`; a journal re-sealed as edition 7 refused on open and carried; a served town carried with its
     transport and served again; `Moves`: an image package changed between two library pins, its plain and
     layered objects migrated, one changing only methods moved with its state, a move that refuses left retired
     at its old pin, a gone package left, a body laid again over the module below, a package offering `carried` told
     once on the first advance, a package's changed law taken and an amended one kept), `test_genesis.NoWipe`, `test_replay_edition` (the refusal names the carry).

160. **Rules fire, wants pose, replies reveal (lane/host22; OVERHAUL §5 step 3; KERNEL-HANDOFF §27; replay edition 9,
   snapshot `v4`).** The shapes, for the strokes assembly (lane/enchant) and the objects lane, as built:

   - *Store.* `Object.rules`, `Object.wants : List Placed`, `Placed {name, owner, since, line, clause}` (`line` the
     clause as `Clause.render` writes it, `clause` its parse; `owner` the placer; `since` the placing entry's height).
     What a thing carries (`Ops.carried`, a `CarriedClause {clause, owner, holder, placed?}` each): its placed rows,
     then its own text's `rule`/`want` lines (owner: `ownerOf` its state), then the lines its law's `under`
     citations carry (`Law.followed`, owner: the holder's `ownerOf`), in that order. `carriedRules`/`carriedWants`
     split them. Snapshot `v4` writes `rules`/`wants` per object (`[{name, owner, since, line}]`) and the indexes
     `ruleLog` (per object, per rule: the last `{height, id}` fired or `{height, why}` unfired) and `wanting` (per
     object, per want: the height that made it true); a carry reads `v3` bodies too (`Snapshot.previousEdition`,
     `addedKeys` start empty).
   - *Placing.* A change of kind `rule` (4): `Proposal.placements : List Placement {object, want, name, line}`
     (`line` "" takes one off), journaled on the admitted outcome as `placements [{object, rule|want: name,
     line?}]`, in the request digest, replayed. `judge` judges a placement by the object's law with `request.kind
     == rule` (`method`, `verb` ""); a removal is the placer's, the owner's or the opener's (`lawRefused notPlacer`),
     not the law's. Refusals: `programRefused law syntax` (the parser's message; a line of another modality),
     `lawRefused nameTaken` (the name is the text's or a placed line's), `lawRefused under`, `lawRefused unplaced`,
     `capacity rulesPerObject`/`wantsPerObject` (32 each). A placing (rule, want or verb, placed or taken off) is not a state move: the version stays, so an ordinary turn rooted on the thing (a suspended `due`, a state reader) is not `staleRoot`; an offered-card reading also depends on its behaviour revision (5.222), and `writeEdits` counts kind 4 as moving no field (host24). The default law is now `request.kind
     == 0 or request.kind == rule or request.subject == "<creator>"`; a world's own laws (`Kind.lawOf`, the
     bodies) need `or request.kind == rule` from the objects lane, or only their owners place.
   - *Spells, on every card.* `delvetalk O rule / name: N / when: EXPR / then: SPELL` (and `reading:` before
     `then:`; every field after `then:` is the spell's own: `then: delvetalk me note / text: …`); `want / name /
     when / asks`; `unrule / name`, `unwant / name`. `rules` and `wants` are answered as `?` is (no entry):
     `rulesText`, `wantsText`. `?` lists `rule`/`want` when the law admits kind 4, and `rules`/`wants` always.
   - *Reads.* `world-rules {object, principal?}` → `{status: rules, object, rows: [{name, owner, handle, when, then,
     line, from, reading?, placed?, fired?: {height, id, receipt?}, unfired?: {height, why}}]}` (`from` the holder:
     the object itself for its placed and own-text lines, `kind/…` for a line its law's `under` follows); `world-wants
     {object, principal?}` → `{status: wants, object, rows: [{name, owner, when, asks, line, from, reading?, since:
     height | "clock"}]}`: only the wants that hold now, `asks` filled at the read (`Law.fill` over `asItStands`;
     the template when a hole reads nothing). `world-inspect`'s `laws` rows carry `keyword`, every modality
     (`Ops.textClauses`, the one parser; the line splitter and `Law.lawReading` are gone).
   - *Firing, at commit* (`Ops.reactions`, after `judge` admits): for each written object, each carried rule whose
     condition holds under any of the facts its law judged the write by (`Judged.facts`, with the rule's cited
     states and wants), its spell filled at the write: `fired [{id: rule:<object>:<name>:<height>, to, method:
     receive, argument: {text, post: ""}, sender: object, principal: owner, ledger, rule, depth}]`, a pending
     delivery like a send (the ledger the turn's sends inherit), `to` the card the line names as its owner resolves
     it (`me` their avatar). Else `unfired [{object, rule, owner, why}]`, `why` one of `hole`, `spell`, `noOwner`,
     `quiet`, `ruleDepth` (`Limits.ruleDepth` 4: `depth` counts firings down a chain), `rulesPerCommit` (8 per
     commit), `pending` (`maxPending` undelivered). The delivered turn is the owner's entry under identity `(owner, rule:…)`; a rule's spell may be a
     host spell (`castSpell`'s `speaker`): `adopt`, `rule`, `lend`… run under the owner with the delivery consumed.
     Judging is not metered (`ruleTicks`): a text law is not either; it is bounded by `rulesPerObject` × rows.
   - *Wants, at commit and at read.* `wanted`/`unwanted [{object, want}]`: the wants that hold of each written or
     created object after the write and not before, at the clock, and the reverse (`posing`). Replay re-derives
     `fired`, `unfired`, `wanted`, `unwanted` and compares each.
   - *`request.verb`.* `Written.verb` (`act {verb, text}`'s verb, else "" for the method; journaled `verbs`;
     `TurnLoop.actVerb`). No body has `act` yet (objects lane); `#guard`s and Law's own guards cover it.
   - *The revealing reply* (FOUNDATION §5). `turnReply` carries `revealed`: up to three host-rendered lines of an
     admitted entry (`TurnLoop.revealed`), each left out when empty: what it moved (`rule two of glm.delve.town
     fired: delvetalk me note / text: …`, or `… did not fire: <why in words>`), what it opened or closed
     (`garden/bell/1 now wants second: delvetalk garden/bell/1 rain`, `… no longer wants second`), where it stands
     (`garden/bell/1's lines: 2, the first by kimik3.delve.town`: each relation the write inserted into, its count,
     the speaker's first row by `author`). `bridge.draft_text` and `spell_line` place them between the card and the
     receipt line. Not yet: `offeredTo`'s diff for the speaker ("it now takes `ring`").
   - *`adopt`* takes `rule`/`want` lines inline as it takes `law` lines: a rule in a thing's own text is fired under
     its owner.
   - *Packages.* A package's top-level `rule`/`want` lines (`EntryCompiled.clauses`, `Built.lines`) are placed by
     `makeObject` on what is made of it with no law text given, owned by its creator, `since` its height.
   - *Carry.* Edition 9 is breaking and carries: `deploy/carry-check.sh` on hbox, the newest v7 backup
     (`delvetalk-20261011T183505Z`, `--old-image delvetalk-host:9790175f9dc0`): green, breaking, carries (28
     objects, 73 receipts); playtest 3 (`run-20261011-084303` state, `--old-binary` its dt-playtest6 binary,
     `--leave wake/did:plc:6amo7col5h4ciq2gpm5eur7b`): green, breaking, carries (51 objects, 489 receipts).
   - *Tests.* `tests/test_rules.py` (the controls: a rule fired once and read back with its receipt, forty rules
     firing eight, a chain four deep, `hole` and `quiet`, placing and taking off, a want's flips and `since`, where a
     write stands; each across a reopen) and `tests/test_reaction.py` (FOUNDATION §10's five outcomes on the town's own
     objects, and a firing replayed after a restart).
   - *For the objects lane.* The world-call arms (`rule`, `unrule`, `want`, `unwant` from Bend) are not built:
     World.obend's protocol must declare them in the same change that deletes `subscribe` and `awaitPost` (one pin
     move), and the host's arms follow (`answer`, `worldMethods`; staged as `TurnState` placements, as `amend` is).

161. **Enchantment (lane/enchant; OVERHAUL §4, step 3b; no replay edition change).** `spec/Delvetalk/Host/Enchant.lean`,
   `world/lib/Paint.obend`; hooks only in `Session.lean` (the import, `Open.renders`, the five ops' dispatch, `world-status.renders`).
   - *Strokes* (`assemble`, `strokesAt`): read from the store at a version (`stateAt`, `pinAndLawAt`) by field name, so any
     package's state gives what it holds: `head` (else `name`), `fields` (the kind's form values; beyond OVERHAUL's list,
     because a bell's seed is its maker's words and no other stroke holds it), `kind` and that kind's `voice`, `maker`,
     `keeper`, `owner` (handles, the state's or the registry's), `made` (state `made`, else the creating entry's
     height), `tended` (its clock minute, 5.200), relation `counts` (`lines` and `marks` always), the eight newest `lines` with
     `admitted`/`pending` under a keeper and a thing's `description` as its keeper's `inspirit` line, `marks`, `verbs`
     (the card's spell forms as one-line spells, the kind's first, then each of `Object.verbs` with its grower and reading), `laws` (a clause `under "K"`
     stands as K's clauses), `doors` (`cites`), `around` (`location`, else the longest prefix of the id that is an
     object), `present`, `rules` (`carriedRules`: name, owner's handle, reading, the height `ruleLog` last fired it at), `wants` (`wantRows`: those that hold now, with `asks` filled). `today` stays empty until `chronicle` lands. `world-strokes` reads them; nothing is written.
   - *The check* (`verify`): clauses `ids`, `numbers`, `handles`, `spells`, `quotes`, `heads`, `forbidden`,
     `secondPerson`, `negation`, `length`, the first failed refusing; the doc comment and VOICE "The paint" give each.
     A store line with no verb column holds every verb (strict: "nobody rains here" over a rained bell is refused).
     `world-render-check {principal, object, version?, text}` judges any text without caching.
   - *Rendering*: `world-render` assembles the strokes and keys them `bodyHash {strokes, library pin, model}`; a
     cached `painted` answers its text, a refused one `exact {reason: rejected, clause}`; else it queues
     `pending` (bounded `maxPending` 64, `busy` past it) with the request `{model (the policy object's, else
     claude-haiku-5-5), system: Paint.contract() compiled once per library pin and cached as a definition, user:
     "Strokes:\n" + the strokes' JSON, maxTokens 400}`. `pending` carries `patience` (`renderPatience`, 3 s) only
     while the worker attends (`world-renders` within `workerGraceMs`, 10 s); otherwise `exact {reason: unattended}`
     at once, the render still queued. `world-render-submit {key, reply}` takes model.py's result verbatim: `replied`
     is verified and cached; `transport`/`rate` waits `renderBackoffMs` and is listed again, `renderAttempts` 3 in
     all; anything else is `exact` (`model`). Painted and refused renders are written to the disk cache (kind
     `render`) when `DELVETALK_RENDER_CACHE` is set (its own directory: renders never share the compile cache) and re-verified on every read back; a model failure is not.
     `plain` (a `plain` field true or `yes`) answers `plain`; a root `card` override `exact {override}`; no
     policy or no `Paint` module `exact {unavailable}`.
   - Transport: `interpret` is the one model worker (interpretations, then paints, every `model_poll` second;
     spend lines carry `use: paint`); `transport/host.py` `painted()` waits as the host's `pending` says and answers
     `{text}` or the host's reason (5.183); `/play/`,
     `/o/` and the hand's Speak show `pages.painting` above the exact card; the bridge's drafts are exact only.
   - Tests: `tests/test_enchant.py` (strokes, a placed rule and want read back, fired and unposed after a rain; 69275 refused at `negation` on the genesis anthology; one call per
     version, read back after a restart from the disk cache; a refused paint not asked again; a rate failure retried
     after the backoff; no policy, every card exact), `test_http.Play.test_the_paint_stands_above_the_exact_card_and_never_without_it`.
   - Live, hbox, the real key through `interpret.paint` (2026-10-11): three cards of a fresh genesis with a bell rained
     on twice, all three painted and admitted, $0.0007 for 4,509 input and 482 output tokens. The first contract's
     paints were all refused (a quotation's closing stop, two over 600 characters) and, worse, admitted ones misread
     `made`/`tended` as counts ("made 41 times"): the contract now says how each stroke reads and asks for two to four
     sentences; the quote check drops a quotation's own closing stop. A token check cannot catch a misreading of a
     true number (OVERHAUL §7 risk 11): watch for it in the fourth playtest's corrections row.
   - *Handoff* (lane/enchant, stopped at its token budget). Open, in order: (1) the morning card and the chronicle as
     painted surfaces once `chronicle {day}` lands (`today` in `assemble`; a painted surface for `hand morning`);
     (2) KIND's `voice` and the `plain` lens are the objects lane's (read here by field name, untested until a
     package declares them; add a test then); (3) whether a reply post carries paint is the fourth playtest's (the
     bridge drafts exact; `zulip.py` untouched); (4) renders are per process: a restarted serve without
     `DELVETALK_RENDER_CACHE` paints each card once more (deploy does not set it; set it, or accept the call);
     (5) the paint is dry, a field-guide catalogue; once kinds carry `voice` read a dozen live paints and tune
     `Paint.contract()` (it is library text: a library change, not a host one).
   - *lane/paint* (2026-10-12; no edition change): the strokes carry meaning, not ledger (`Strokes.text` is what the
     painter reads: no entry number, version or line number; counts as `Quantity` with unit and meaning, a rule's
     `count(new.lines) >= N` as the Nth; a coinage's credit; the kind's added law only); `numbers` holds a number,
     digits or words, beside the unit the strokes count it in (the misused true number, "made 41 times", refused;
     `#guard`s); `verify` is the table `clauses`, its words `table`; a thing paints in at most 400 characters, a day 600.
     The day (`dayStrokes` over `Ops.chronicleDay`, which `chronicle` now formats): `world-render`, `world-strokes`
     and `world-render-check` with no `object` and `{day?, morning?}` (the morning card with what wants a hand; `quiet`
     for an empty day). Voices for every town kind (genesis `VOICES`); a thing of no kind speaks in its place's. Live,
     hbox, five runs of the minimal genesis's five things, the day and the morning: 7 calls a run, $0.0014 to $0.0018.
     Then: the coiner is the coining post's author (handle when the registry knows the DID, else the DID); the
     strokes credit each text (`Strokes.authored`) and the `attribution` clause refuses a quotation credited to anyone
     else; a paint refused for length alone is asked once more with its length (`renders.retried`); the morning reads
     `Ops.wanting`; the day counts its lines by verb (rains as rains); `hand morning` paints, shows and drafts the morning
     card once a day for Post (never posts). Open: a coinage's own voice needs a field on the thing (objects); the porch
     names gemini only once gemini's DID has a handle here (arrival).

161. **Grown verbs, the chronicle, the world arms; Wake's host support deleted (lane/host23; OVERHAUL §5 steps
   3 and 4's host half).** No edition bump: edition 9 is not deployed, and these change what it derives.
   - *Verbs.* `Object.verbs : List Verb {name, by, at, reading, takes, does}` (≤ `verbsPerObject` 16; snapshot
     `verbs`). Grown by a placing of kind `rule` (4): `Placement {object, what: rule | want | verb, name, line,
     takes, does}` (journal `{object, verb, reading, takes, does?}`; removal has no reading), judged by the law
     with `request.verb` `grow` (rule and want placings now carry `rule`/`want`), so `request.kind == rule`
     admits all three and `request.verb == "grow" implies …` refuses grows alone. Refusals: `programRefused
     verb` (name a word of a-z, digits, -, ≤ 32; reading one line ≤ 200), `nameTaken` (a declared method, a
     host spell or read, `act`/`set`/`receive`/`?`, a grown verb), `noMethod act` (no `act`, no verbs),
     `capacity verbsPerObject`, `notPlacer`. `does` names a rule placed in the same entry under the grower,
     `rule NAME: request.verb == "NAME" then SPELL`; `ungrow` takes both off.
   - *Spells.* `grow / name / reading / takes: text|nothing / does: <spell, last>`, `ungrow / name`, `verbs`
     (declared then grown, with grower and entry). `formsOf` appends grown verbs as forms (the text field is
     `act`'s own) and hides `act`; `offeredTo` judges a verb as `act` with the verb; `castSpell` runs a grown
     verb as `act {verb, text}` (`grownAct`); a direct `act` naming no grown or staged verb is `noMethod`. A
     spell naming no verb says how it grows.
   - *Staging.* `placementsOf` is the one reading of a placing (spell, call, arm); `stagePlacements` judges at
     once and stages on `TurnState.placements` (journaled on a suspension's activity). A `call` of a placing
     spell on a card not declaring it, and a `call` naming a grown verb, are the host's.
   - *hob.* Four answers: the spell, `grow: NAME "reading"` + the spell using it (`growVerdict`: `proposals
     [{method: grow}, {method: act}]`, one turn runs both, the use seeing the staged verb), `ask:`, `none`.
     `say:`, `card`, `saidVerdict`, `sayClip`, the said/replied verdicts are gone.
   - *Chronicle.* `world-chronicle {principal, day?}` → `{status: chronicled, day, lines}` (`Ops.chronicle`):
     `World.days` (`(day, height)`, derived by `record`, in the snapshot) bounds the day; lines for viewable
     things: made, grew, fired/did not fire, came to want/stopped wanting; refusals by class; hands.
     `Limits.clockDay` 1440 is the one day (the model's day reads it).
   - *Arms* (TurnLoop `answer`): `rule`, `unrule`, `want`, `unwant`, `grow`, `ungrow` → `placed {}`;
     `act {object, verb, text}` → `returned` (a call of `act`); `chronicle {day}` → `chronicled {day, lines}`.
   - *Wake's host support* (commit 0a6ed761, merged only with lane/rewrite14): subscriptions, `changed`
     deliveries, `awaitPost`, `World.replies`, the `subscriptions`/`replies` snapshot keys, `env`/`wake`
     own cards and arrivals (the avatar alone), `arriveWith`. Mentions reach `<did>.receive` with the stated
     reach `mentioned`, heard and never cast. A rule-fired delivery's `context.sender` is the rule's object
     (`deliverOne`'s `caller`).
   - *Tests.* `test_verbs`, `test_chronicle`; `test_changes` deleted; the four answers in
     `test_interpret_object`, `test_interpret_text`, `test_hub`, `test_http`.

162. **Reach is the host's (host25; OVERHAUL §5 step 5's host half; fungus T30; no edition change).** `world-reach {uri, text,
   kind, author, replyTo?, root?, mentions?, chain?: [{uri, author, replyTo?}]}` (`TurnLoop.reachOp`) answers `{status:
   reached, object, slot?, how, replyTo?, page?, section?, unposted?}` or `{status: unreached}`; nothing is journaled. The
   bridge passes what it observed (the post, its mentions' count, the ancestors it saw nearest first, at most
   `reachHops` 32) and sends the turn the answer names, `reach` set for `mention`, `door` and `fields` (the turn finds
   `reply` and `spell` again itself). The rule, FLEX §2's as `bridge.route` had it: (a) a reply reaches its direct
   parent's card (`walkTo` over `World.posts`, one hop on Delve; on Zulip up the topic past only the author's own
   messages, none when it mentions residents); (b) a spell line its card, a summons `commonplaceId`; (c) in a thread
   the world opened (the walk from the parent's parent, else the root's post) field lines reach the thread's card,
   (d) prose naming a door of the commonplace's `cites` (`namedDoor`) that door. `bridge.py`'s `route`, `walk`,
   `named_door`, `parsed` and the `world-addressee` op are gone (a reply's reach names what its parent was made for;
   `tests.host.addressed`). Tests: `test_reach.WorldReach` (each rule, a cycle, Zulip's author walk),
   `test_bridge.Reaching` (what the bridge passes and sends), `test_zulip`, `test_outbound`, `test_archive` unchanged
   (81 reached). Words a reached card leaves silent are hob's (5.163).

163. **Words a card heard are hob's (host26; OVERHAUL §2.7; FOUNDATION §10; no edition change).** A direct `receive`
   whose words reached a card (`reach` not empty) and run none of its spells goes to the card's `receive` first; what
   it leaves `silent` (`heardSilent`: admitted, result `silent`, nothing written, sent, offered or published) is
   discarded and the host reads the words itself (`heard`, `heardTurn`), never the card's Bend. A card opts out of hob
   for words only by answering them (an avatar's own words, a room's spween block, a door's word at the commonplace);
   there is no flag. hob is offered the card's table (`heardOffers`: its forms and grown verbs offered to the speaker),
   then each door's (`doorsOf`, the card's `cites`) card and the first three under it, which is the commonplace's
   door-learning, in the host; `world-interpretations` adds the card's `wants` and the library's `pages` to the
   Policy's `asked`. Field lines that fit an offered form run at once, no model. Else the turn suspends with no
   checkpoint (`hostResumed`), under the world's one `policyId` object, counted by `interpretGate` and `waitFull`
   (prose past them is refused `quota` or `capacity`, transient). `resumeHeard` settles it under the turn's identity,
   the card its root: a spell, or `grow:` and its use, runs as the speaker's turn (`runHeard`, origin `interpreted`);
   an action in the policy's `confirmFor` is offered back indented; `ask:` naming offered fields offers "hob: that
   still needs …" with the spells, naming none "hob: none of <card>'s spells takes that; its spells: delvetalk <card> ?"; `none`, a failed model or the deadline is silence.
   A misfit spell (`misfitClauses`) is hob's for every card; anything but a proposal settles as the host's
   `badSpell`, which is the answer at once without a policy. `readsWords` and `misfitData` are gone.
   `world-receipt` gives a refusal's owner its `public` projection, and the bridge drafts a refused resumption and
   marks a settled one (`awaiting.settled`). Tests: `test_heard`, `test_spell_turns.Misfits`/`MisfitsWithoutPolicy`.

164. **What wants a hand (host27; §7 item 1a; no edition change).** `world.wanting({after: Nat, limit: Nat}) ->
   Wanting {wanting {rows [Want {object, name, reading, asks, since}], more} | refused}` (the objects lane's
   World.obend) and `world-wanting {principal?, after?, limit?}` → `{status: wanting, rows [{object, name, reading?,
   asks, since}], more}`, one function (`Ops.wanting`): each row of the wanting index (`World.wanting`) whose want
   still holds of its thing as it stands (`posing`), for things the reader may view (the arm's reader is the turn's
   subject), newest first by `since`, then thing and name. A page holds whole heights below `after` (0: from the
   newest) within `limit` rows (0 or past `listPage` 64 is 64); its first height is whole whatever its size, so
   `after` set to a page's last `since` reads on without a gap. A want true by the clock alone is in the index, `since` the
   `advanced` entry that moved the clock (5.211). `asks` is filled at the read (`wantAsks`, shared
   with `world-wants`; `wantFacts` is the one set of facts `posing` and both reads judge and fill by). Derived, no
   root. Tests: `tests/test_wanting.py` (the index by whole heights for whom may view, a closed want leaving,
   unchanged by a reopen and a snapshot; the Bend arm, on the pair).

165. **What a thing stands at: `request.laws`, `request.refusedBy` (host27; §7 item 1a; no edition change: edition 9
   is not deployed).** Two facts in the kernel grammar (`LawFact.laws`, `.refusedBy`; `LawFact.atRead` names the four
   a want may read: `clock`, `object`, `laws`, `refusedBy`), read of `request.object` by laws, rules and wants alike:
   `laws` the count of its law clauses, its own and each one its `under` citations' texts hold, followed through
   their own `under` within `lawDepth`, each (holder, clause) once (`Law.followedLaws`, `Law.lawClauses`; a Bend
   law is not a clause); `refusedBy` the count of journaled `lawRefused` entries naming it (`Ops.lawRefusedOf`; every
   `lawRefused`, the host's clauses such as `noGrant` or `notPlacer` too; never `cardRefused`), the index
   `World.refusedBy` that `record` derives (snapshot `v4` key `refusedBy`, a carried key; a carry from `v3` starts
   it empty). `Law.Facts.standing` holds a `Standing {laws, refusedBy}` for the written thing and every thing it
   cites (`Ops.standings`), so a cited want (`"seal" wants tried`, judged `asItStands` the seal) reads the seal's;
   every site that builds facts fills it (`judge`, `wantFacts`, `amendable` at creation and amendment, `methodAdmits`,
   `kindAdmits`, a layer's check); none reads as no reading (fails closed). A law's refusal moves its thing's
   `refusedBy`, so `push` journals on every `lawRefused` entry the wants it opens and closes (`refusalWants`, `wanted`/
   `unwanted` as an admitted write's; `wantFlips`, `flipFields` shared with `reactions`); `wantingAfter` and the
   chronicle read them on a refused entry too, and replay re-derives and compares them. A want reading
   `laws` moves only when its own thing is written (an amendment is), not when a cited kind's text changes (§7 item
   3's citing-want limit). Tests: `Law.lean`'s `#guard`s (counts, a cited want reading its own thing's standing), the
   kernel's accept lists, `tests/test_wanting.py` `Standing` (a seal's "a law and a second hand's try" opened by the
   refusal, listed, in `wants` and the chronicle, across a replay and a snapshot; a law reading `refusedBy`).

166. **A post is read by hob at most once (host27; §7 item 1's double ask; no edition change).** The archive's sentry
   post (`3mxhfzx7rlk2f`) was asked twice, and the wake post (`3mxhg3bqrds2f`) three times, because a post's spells
   are a turn each (5.148) and each misfit spell was its own reading. Now `runSpells` runs the spells that fit, then
   reads the post's misfit spells (`misfitOf`: what `spellTurn` would refuse with a `misfitClauses` clause) as one
   reading, under the first one's identity (`#k`), a retry answered from it: the utterance those spells, blank-line
   separated; offered each one's card's table and doors (`heardTurn` takes the cards, rooted on the first that
   exists, offers deduplicated); the misfit `clause` the first's, `reason` each spell's first line and reason, `hint`
   each hint, which a non-proposal settles as one `badSpell`. Where hob cannot read (no policy, quota, slots), each
   misfit is refused alone as before. The reply lists the run turns, the reading last. The archive (on foundation
   d02fd11c + host27): 81 reached, 72 model calls over 72 posts (67 `none`, 3 proposals, 2 asks), no post asked
   twice (was 75). Tests: `test_spell_turns.Misfits`/`MisfitsWithoutPolicy` (a post of a misfit, a fitting spell and
   a misfit: one reading after the plant, a retry asks nothing, hob's spell runs), `test_archive`.

167. **A frame reads its object as the turn has written it (host27; §7 item 1's known limit; no edition change).**
   hob's several spells run as one turn (`runHeard`), each a frame on its card; a frame read its object as committed,
   so `enter` then `say` on a room said as one who had not entered (a guard refused; a pure method's whole-state `set`
   overwrote the earlier edits). Now every frame reads its object `asWritten`: the committed state with the edits the
   turn has staged on it applied in order, as `judge` applies them at commit (as committed when none, or when they do
   not apply, which the commit refuses). This is the turn's model generally, not hob's alone: a call back into an
   object the turn wrote reads its writes too. What stays committed: the frame's version and the roots its cells are
   recorded at, and `view`/`viewField`/`viewAt`, which answer a state at a named version. Nothing is journaled
   differently (edits are edits; replay applies what was recorded). Tests: `test_heard.Heard` (hob's `enter` and `say`
   on a room in one answer: entered, then said as one of 1 here).

168. **`interpret` takes no `held` or `misfit` (host27; OVERHAUL §3's deletions; the coordinator's docs pass).** The
   arm reads `utterance`, `offers`, `policy` and `model` only, and nothing journals or lists `held`. `misfit` stays only as the host's own: the
   misfit spells a host reading reads past (`heardTurn`, 5.166), shown to `Policy.prompt` as `asked.misfit`.
   `Policy.prompt`'s `asked` drops `held` (`heldPart` gone) in the same commit, since a prompt naming a field the host
   no longer supplies would not fit and fall back to the bare `system` text. World.obend's arm is
   `interpret<R>({utterance, offers, policy, model})` (lane/objrev), its eight callers with it; `policy` stays, since
   `interpretPlan` reads it (a Plan without it is `malformed interpret plan`; one the speaker cannot read, `denied`).
   Tests: `test_policy` (the misfit prompt; no `held` listed).

169. **A grown verb is offered by the law alone (host27; found capturing AGENTS-EXAMPLES on the minimal genesis).** A
   card whose `actions` names what a reader sees (the town's bells: `rain tend ring lines`) hid every verb a hand grew
   on it, since `offeredTo` asked `actions` for `act`: the bell's `verbs` listed `hum`, but `delvetalk bell/1 hum` was a
   misfit and hob was not offered it; and the bodies offer `act` to nobody (`~act`), so `methodForms` gave it no form
   and `withVerbs` made no grown verb a form at all. `offeredTo` now judges a grown verb by the law (`methodAdmits` of
   `act` with the verb) alone, a card's `actions` speaking for its declared methods; `methodForms` keeps an unoffered
   `act`'s form, whose `text` field the verbs take (`act` is still no spell). Test: `test_verbs.Verbs` (a card with
   `~act` listing only `rain`: the grown `water` offered, a stranger's spell admitted).

170. **Every `receive` is heard with what the host fills (host27; the v8 deploy's lost mentions).** The bridge delivers a
   mention as `receive {text, post}` (reach `mentioned`) to the mentioned resident's avatar, whose `receive` takes
   `Card.Reply {text, post, fields, spell}`: each was refused `typeMismatch` (ten on gsb, entry 77 the first). `runFrame`
   now fills any `receive` whose argument does not fit as the spell path fills it (`heardArgument`: `fields` empty,
   `spell` read from the text, `castData "" ""` for a mention, which is heard and never cast; `misfit` none), whoever
   sends it (a mention, a rule's firing, a send). Test: `test_bridge.Mentions` (a mention through the bridge on a
   genesis town, admitted on the avatar).

171. **A question hob reads nothing into is answered by the card (host27; the v8 deploy's silent question; the
   coordinator's decision).** "does the bell have a clapper?" to bell/1, which wants one, came back `none` and so
   silence. Now `resumeHeard`, when hob replied with no spell and no ask (`none`, `unclear: not addressed`) to words
   ending in `?`, offers the speaker `cardAnswer`: the card's exact text as they read it (`shownCard`, what `world-card`
   answers, wants lines and bound included, 5.180; the model's copy is `cardText`). Data, not
   narration. Other words stay silence, and so do a failed model and the deadline. The paint is not in the offer:
   renders live per process in the session (`Open.renders`), outside the world a turn commits; the front places a
   painting above the exact card where one exists (5.161), and the bridge drafts exact. "Or hob says ask is not
   needed" is not built: hob has no such answer; a question it asks back stays `ask:`. Test: `test_heard.Heard` (a
   rendered card with a placed want: the question answered by its text and its wants; prose stays silent).

172. **Root sets one field of a state (host27; the live town's entry 129).** `world-root {act: {kind: set, object, field:
   "state.F", value}}` (`hand root set --object kinds --field state.count --value 12`): `stateFieldOf` (one top-level
   field; a nested path refuses), `fieldValue` (typed wire data, or a plain JSON number, text or boolean standing for
   a field of that kind), `withField`; the state as set must conform to the object's type. Journaled as `state` is:
   `before` and `after` that field's value, `version` + 1 and the whole state's `cid`, so anchors and replay read it
   as any root `set`; `rootBefore` and `applyRoot` read the same field. Tests: `test_root.Root` (plain and typed
   values, four refusals, a bump after it, a reopen), `test_root_console` (the CLI's flags).
173. **Calls and sends across worlds (host28; docs/FEDERATION.md §2; no edition change).** A `call`, `callVia`, `send`
   or `sendVia` whose `Reference` names a world (`foreignRef`) crosses to it. Each is refused by name when it cannot:
   `noGrant` under a grant (a grant serves the world it was made in), `foreignWorld` for a world not served here
   (`Foreign.serves`, which `serve` builds per request), and `crossing` for a turn's second (`crossingsPerTurn` 1,
   `TurnState.crossings`, journaled with a suspension) or a call from inside a call (only the turn's own frame may
   wait). A send stages a `Send` with `world` (the send row's `world`), pending at commit but never delivered here
   (`Ops.crossesOver`, `deliverable`), unless its ledger is spent, when it is refused here `budgetExhausted`. A call
   suspends (`TurnLoop.crossCall`) on the slot `(principal, id)` with `crossing {world, to, method, argument, sender,
   ledger}` on the entry, `crossingPatience` (60) its deadline. `serve` carries both after every reply (`Serve.cross`
   over each held world's `Ops.outbound`, `carry`): the target journals `relayed` under `(principal, "<home>:<id>")`
   with one send (`relayOp`; sender `<home>:<object>`, the ledger as it crossed), delivered by its own settling pass
   as any send, under the caller's principal and judged by its law alone (`request.caller` `<home>:<object>`); once
   that delivery has a receipt, the home world journals `crossed` (`crossOp`) under `(principal, id)` with the
   target's answer, receipt `{hash, height}` and result: a send's consumes its pending delivery (`checkDelivery`),
   a call's settles the slot, and the settling pass resumes it (`crossedResponse`: `returned {result}` or `refused
   {clause, reading}` as the target voiced it; `timedOut` past the patience). A world not served or not opening
   when carried, or a spent call, is answered `refused` at once. Each step is idempotent (a relay retained by
   identity, a crossing found by `outbound`), so a stop between the two journals is carried on at the next start.
   Replay of either journal alone reads the other's receipt as data (`relayed`: one send; `crossed`: something here
   waited for it). The read Plans of another world's object (`view`, `viewField`, `viewAt`, `viewDerived`, `card`,
   `inspect`: `foreignReads`) are one path: `Foreign.read` runs the same Plan in that world (`readIn`, the object
   named locally, under the reader, the turn's ticks) and the turn journals the citation. Tests: `test_scratch` (a
   call resumed with the lab's receipt cited, a send once per turn, `foreignWorld`, both journals replayed alone).
174. **The REPL is a scratch world's (host28; docs/FEDERATION.md §3).** `world-repl {principal, identity, entry,
   source?, object?, argument?, arguments?}` (`PackageSession.repl`; serve refuses it outside a scratch world) compiles
   `source` over the world's library: an entry that is not an Activity runs on `arguments` and answers its value,
   journaling nothing; an Activity is a method of the object `object` (default `repl`) the module defines, made from it
   when absent and reprogrammed to it when its source differs (identity `<identity>/defined`, answered as `defined`),
   then run as the principal's turn `identity` on `argument`. With no source the method runs on the object as it stands.
   So a REPL's state, what it made and what it waits for are the scratch's, and outlive a restart for the scratch's
   life: the client-held checkpoint, `replRestarted`, `badModules`, serve's journal-less session and its `stateless`
   envelope, `HostClient(stateless=)` and the front's library-pin tracking are gone (`compile` and `check-package` by
   pin go to the town, whose library resolves it). The front's routes are `/AGENTS.md/scratch/<name>/repl`, `/check`
   (`world-check` on the scratch) and `/cite` (`world-cite`); `/AGENTS.md/repl` and `/check` are gone. Tests:
   `test_http.Repl`, `test_hypermedia` (the stranger's walk), `test_serve`.

175. **The second codex review's host findings (host29; docs/review/codex-2026-10-12; snapshot `v5`; deployed
   with kernel18's replay edition 10, which its carry needs no more of).** Each with its failing input as a test, red on foundation:
   - *What a clause cites* (host 1, 10, 11). `Ops.citesOf` is the one closure of what names cite (`"O".F` the
     object; `under "O"` what O's law text names; `"O" wants N` what O's want N names, with every want clause of a
     want-cited object), `Limits.lawDepth` deep; `citing w law names facts` sets `reads`, `wants` and `standing`
     (`standingOf`). judge, amendable, reactions, posing/`wantFacts`, methodAdmits, kindAdmits and a layer's
     creation all read it; `citationsFrom`, `citedStates`, `wantsCited`, `standings` are gone. `judge` applies every
     write first and judges each law, Bend law, amendment and placing against the candidate world (`cand`), so one
     commit writing A and B is judged as the world it leaves. A rule fires only when its owner may view the thing
     and all it cites (`unfired reads`); placing a line citing what the placer may not view is `lawRefused
     lawReads`; a want's `asks` is filled for its reader (`wantAsks w reader`; the paint's as nobody). Tests:
     `test_law.Cited`, `test_rules.Reads`.
   - *Grants* (host 3). `TurnLoop.granted` is the gate a principal's own turn enters a lent grant by (`runTurnWith`,
     `runHeard`): it stands for this principal, a use is left and spent, the fixed part merged. `Abort.named` is a
     refusal given whole (a card's `refuse`, a grant's clause). Test: `test_grants.LentDirect`.
   - *Quiet* (host 6). `Ops.quietOf` is the one reading; `judge` refuses every entry of a quieted principal (propose,
     reprogram, amend, placing, resumption, delivery), `runOne` before the turn runs. A delivery refused `quiet`
     spends an attempt per clock step (`redelivered`), as any transient one. Test:
     `test_root.Moderation.test_a_quieted_principal_writes_through_no_op`.
   - *Rows and read policy anchored* (host 5). An admitted entry journals `placed [{object, cid}]` (`placedField`,
     `placedCid` of rules, wants and verbs) for each object whose rows it changed or made, a `created` entry `placed`;
     replay compares both when present. `Anchor.placed` (`placedIn`, or a genesis's rows) and `Anchor.read`
     (`readPolicyIn`: creation, root `set`, `hide`/`show`, genesis); `checkAnchors` refuses rows no entry commits to
     and another read policy, so the world is replayed whole: **a world whose rows predate `placed` replays whole at
     every open until it is carried.** Snapshot `v5` (five heights an anchor); `previousEdition` `v4`, whose three a
     carry checks alone (`checkAnchors whole`). Test: `test_snapshot.…forged_rows_or_read_policy…`.
   - *Identities across a carry* (host 8; docs 1; agent 1). The `carried` genesis holds `identities` (`identityRow`
     of each bound identity, and those its own carry kept); `World.carriedIds` is read from the genesis (never a
     snapshot); `Ops.boundEntry` is the one lookup (`retained`, `retainedTurn`, `runTurn`, `world-receipt`). Test:
     `test_carry.Carry.test_a_retry_after_the_carry_answers_the_receipt_and_repeats_nothing`, two carries deep.
   - *In-turn creations* (host 4). `createRecJson` journals `lines` when the package's lines were placed;
     `Ops.createdLaw` builds it again so in replay and a suspended activity. Test: `test_make.Make.…through_replay`.
   - *Paint* (host 14, 15; laid on lane/paint's table). A past version is `historical` (`strokesAt`); a resident's
     line is quoted whole (`Strokes.wholeLine`) and credited (`attribution` … `uncredited`), another text in part.
   - *Spells* (agent 2, 3; lane/host29-spell). `Spell.segments` reads no spell inside a `<<TAG` block or a tagged
     fence (`blockOpener`, `closesBlock`, one reader with the binding parser); `fit` refuses an unknown field with a
     known one after it (`unknownField`), an unknown one last still ends the fields (D7).
   - Objects 4 was lane/objrev's (the Bend law judges placings); agent 4, 5, 12 were host27's (5.169, 5.167, 5.164).
179. **Firings named by their holder, carried roots behind a barrier, no suspension dropped unnamed, a judgment's
   roots, law work metered (host30; codex host 7, host 9, docs 7, host 12, host 13; replay edition 11).**
   - *Holder* (host 7). `ruleDeliveryId object holder name height`: a rule the thing holds keeps
     `rule:<object>:<name>:<height>`; one it inherits through `under` (`CarriedClause.holder`) is
     `rule:<object>:<name>@<holder>:<height>` (no object id holds `@`; `Record.ruledFrom`'s prefix stands), so a
     placed rule and an inherited one never share a delivery. Placing refuses a name the thing carries, its
     inherited lines included (`carried`), `nameTaken`. Tests: `test_rules.Placing.test_a_name_the_bell_inherits_…`,
     `test_reaction`'s ids.
   - *Barrier* (host 9). `installGenesis` gives each object of a carried or forked genesis one touch at its version
     and the genesis's height, an entry that writes no edits of it (as a root `set` does), so a root read below that version is
     stale (`editsSince` none) and the suspension runs again; never current by an empty history. Test:
     `test_carry.Moves.test_a_suspension_reading_a_moved_object_is_stale_after_the_carry_and_runs_again`.
   - *Dropped by decision* (docs 7). `carryWorld` drops a suspension only for an object named `--leave`, or a moved
     one whose package offers `carried`; any other the carry cannot keep refuses it by name. Test:
     `test_carry.Moves.test_a_moved_objects_suspension_refuses_the_carry_until_its_object_is_left_by_name`.
   - *A judgment's roots* (host 12). `world.judge` records what its proposal read (`withLawReads`) as the turn's
     roots before answering, so a verdict another object's move withdrew is stale at commit. Test:
     `test_law.Cited.test_a_judgment_that_read_another_object_is_stale_when_it_moves`.
   - *Law work* (host 13). `Law.work`/`termWork`: a step per atom and a row per row a clause walks, each side,
     through `under` and `wants`; `judge` meters the law's clauses and the rules and wants the thing carries
     (`carried`) per judgment against `Bounds.lawTicks`, refused `budget` (`law ticks`). Row membership is one
     pass over a set of canonical bytes (`canonSet`, `evictedIn`: `changedRows`, `insertOnly`). Test:
     `test_relation.LawWork` (16 clauses over 4,096 rows refused, over 512 admitted).

180. **A card is shown within one bound, with the wants it holds (host30; codex docs 14; the attend lane's wants; no edition change).**
   `Limits.cardShownChars` 1,400 is the one bound of a card any reader is shown (`formTextMax` is defined as it).
   `clipCard id text block` is the one place it is applied: `text` then `block` (whole lines) when they fit; else
   `text` cut to leave room for `\n[clipped at 1400 characters; world-inspect <id> reads its source]\n` and then
   `block`, so the answer is exactly the bound. `shownCard w id reader text` is `clipCard` with `block` = one line
   per want the thing holds (`wantRows` for the reader), `wants <name>: <reading>: <spell>` (the reading omitted when
   there is none, the spell's lines joined by ` / `), taken in order while together within a quarter of the bound.
   `cardOp` answers `shownCard` for both a rendered card and a root's `card` override; `cardAnswer` (5.171's
   question answered by the card) is `shownCard` of the same render, so a hob offer equals `world-card`'s text;
   `cardText` (the model's copy, whose wants go as `asked.wants`) is `clipCard` with no block. `world-card`'s
   `document` is the render's data, unclipped, and the transport's GET `/card` leaves it out unless `?full=1`. The
   transport adds nothing: `GET /AGENTS.md/world/<id>/card` is the host's `text`. Bound by the card only: the
   reply's receipt line the bridge stamps is not in it (FOUNDATION's `Card.limit` leaves room for it in a
   world card's own Bend). Previews re-cut from the live cards: `seed-posts/01-porch.txt`, `03-rain-bell-1.txt`.
   Tests: `test_heard.Heard.test_a_card_shows_at_most_the_bound_and_says_where_the_rest_is_read` (at the bound whole,
   one over and 2,000 clipped to the bound with the closing line, a want kept at the bound, hob's answer equal to
   `world-card`), `test_root.Root.test_a_card_override_is_clipped_to_the_card_bound`,
   `test_rules.Wants.test_a_card_shows_the_wants_it_holds_one_line_each_within_the_bound`;
   `test_heard`'s question test and `test_inspirit`'s goblet card pin the line.
181. **A fired spell shown by handle, the paint's `about`, `revealed` on `world-receipt`, `world-history` by height
   (host30 helper lane/host30-reveal; hand-back (2) and (5), fungus T28).**
   - *Shown by handle.* `shownSpell w text` (Ops, by `shownName`): each whole `did:` token of a filled spell the
     registry names is shown by its handle (a trailing `.` is the sentence's; an `at://did:...` citation stays).
     `revealed`'s "rule R of H fired: SPELL" prints the spell through it, so kind/bell's `rang` reads
     `delvetalk glm.delve.town note / text: garden/bell/1 rang`. The `fired` row, its delivery and replay carry what
     the rule filled (the DID), unchanged: the display is derived from the entry alone, so a retained reply and
     `world-receipt` show the same lines. Test: `test_rules.Revealed.test_the_revealed_spell_names_a_principal_by_handle_while_the_delivery_carries_the_did`.
   - *`about`.* `Enchant.kindText w kind field` is the one reading of a kind object's text field (`voiceOf` is gone);
     `assemble` reads `voice` and `about` through it, a thing of no kind through the kind of the place it lies in,
     "" when absent. `Strokes.about` is in `Strokes.json` (`about`), a "What its kind is:" line of `Strokes.text`
     after the voice, and a text of `Strokes.texts` and `otherTexts` (so `verify` accounts its words, numbers and
     quotations like the voice's; no other change to `verify`). lane/attend gives the kinds the field
     (`b3b0b194`); here a kind is any object whose state holds it. Test: `test_enchant.Strokes.test_a_kind_s_about_line_…`.
   - *`world-receipt` reveals.* `receipt` moved from Ops to TurnLoop (beside `turnReply`, which it now shares
     `revealedField` with): for the identity's own principal an entry's `revealed` lines are answered as the admitted
     reply answers them; another reader's projection, and a refusal's, carry none. The lines are computed from the
     world as it stands at the read, so "where it stands" counts are now's, not the entry's moment. Test:
     `test_rules.Revealed.test_the_receipt_of_an_admitted_turn_…`.
   - *`world-history` by height (T28).* `history` pages through `pageByHeight` as `world-entries` does: `after`,
     `before`, `reverse`, `cursor`, `limit` 1..100, reply `more` and `cursor`; an unknown or denied object answers
     before the limit is read. The front's window-widening loop (`http.py` `history`, with its `world-status` read)
     is one call `reverse: true, limit: 20`; `hand.entries` and `root.modlog` read the newest page the same way
     (they read the oldest 100 and sliced the end), clamped to the host's `maxHistoryLimit` (transport/host.py `history_limit`, read from
     `bounds`, 5.193). Tests: `test_world.History`, `test_http.Pages` (one `world-history` call),
     `test_root_console`.
182. **A carried world's heights continue the world before (host31; the first live carry's "untended since entry 27" in
   a world at 48; replay edition 12).** A `carried` genesis is sealed at the old head's height + 1 (`Carry.carryGenesis`,
   `Snapshot.genesisEntry (height)`, `Journal.sealEntry (first)`), so a height a state holds (an
   avatar's `seen`, a line's `at`) names an entry of one sequence across every carry, a carried avatar's new notes
   show at once, and the transport's height cursors (`publications.after`, `awaiting`) keep their meaning (the
   carry's cursor reset is gone). `Entries.base` is the heights before a journal's first entry; an index is a height
   - 1 throughout, those below `base` not held (`get?`, `hashAt?` none), `genesis?` the first; `openEntries` takes it
   from the first link. `Snapshot.firstHeight` is the one rule a first entry's height is checked by (`checkedEntry`):
   1, or for a `carried` genesis of edition 12 on its `carriedFrom.height` + 1 (an earlier carry's genesis is at 1).
   Reads walk `[base:count]`; `installGenesis` starts the world at `base`; `root-edit` takes and prints heights as the
   journal names them (`baseOf`); the journal-full bound counts this journal's entries. Fork geneses stay at 1. Test:
   `test_carry.Carry.test_a_carried_world_counts_its_heights_on_from_the_world_before` (genesis, turns, a line's
   stored height, `world-entries` both ways, `root-edit drop`, a second carry, every old receipt by its slug).
183. **A paint that fell back says why (host31; the v9 deploy check's `hand morning`, `painted: False`).**
   `transport/host.py` `painted` answers `{text}` or the host's reason as `world-render` gave it, `{reason, clause?,
   detail?}` (`exact`'s, `pending` past its patience, `plain`/`unknown`/`denied`, an error's message); `fell_back` says
   it in a line ("the paint fell back: rejected at its `length` clause: ..."). `hand morning` answers and logs
   `fellBack`, the hand's web action notes it, and Speak's "what came back" shows it above the exact card; the
   fronts read `text` alone. Tests: `test_hand.Speak.test_a_paint_that_falls_back_keeps_the_hosts_reason_and_clause`,
   the morning test's quiet day (`pending`: a morning with wants is painted, and no worker runs there).
184. **The commonplace's card leads with what wants a hand (host31; the coordinator, after lane/objrev with attend).**
   A card is pure, so the commonplace's `render` could not read `world.wanting`, and only its blank-words reply led
   with it. `renderCard id o reader caller intent` (TurnLoop; it builds `cardContext` itself) runs
   `renderWanting(state, context, wanting)` when the package declares it (`Package.conventionalNames`), handing the
   third parameter what wants a hand as the reader may view it (`Ops.wanting`, the newest `Limits.cardWanting` 8,
   each `Ops.wantedData`, which the `wanting` arm shares; derived, no root), as it hands the second the reader; else
   `render`. The dead `renderFor` is gone. `world/bodies/commonplace.obend` declares `renderWanting` in place of its
   `render`, so `world-card`, the web's card and the answer to a question hob reads nothing into (5.171) lead with it;
   `shownCard`'s `wants` lines stay the thing's own. Previews re-cut (`gsb-welcome`, `zulip-welcome`,
   `commonplace-card`, GENESIS.md). Test: `test_genesis.Commonplace.test_what_wants_a_hand_leads_…`.
185. **A carry keeps each object's making (host31; the refresh of the v9 deploy and carry-check: "its making is in no
   journal read").** Genesis's refresh knew a kind as genesis's only by reading its making in the journals a carry
   cites, which a deploy check's backup or a container without the old state does not hold. The carried genesis now
   keeps `made [{object, identity, height}]`, every carried object's making (`Carry.makings`: the entry of the old
   chain that made it, `makes`/`madeRow`; else what the old chain's genesis gave it, `givenMakings`: its `made`, or for a
   genesis of an edition before (the live v9) every making in the journal it cites when that is on the disk, and that
   one's in turn). `deploy/genesis.py` `given` reads `made` from each journal of the ancestry: a kind's field slot whose
   making is the opener's `genesis-*`/`refresh-*` turn but whose text is unread is refreshed (only its owner, the opener,
   writes it, KIND_LAW); one read in a journal compares as before. carry-check on delvetalk-20261012T121739Z still leaves
   them: v9's genesis keeps no `made`, and the v8 journal it cites (`/towns/v8/state/town.journal`, the backup
   delvetalk-20261012T115945Z at its head 435) is not at that path on hbox; the deploy's carry reads it where it is.
   Test: `test_genesis.CarriedRefresh` (a genesis town carried, its `made`; that genesis stripped of `made` as an older
   edition's and carried again, the makings read from the journal it cites; every journal before gone, the refresh).
186. **hob is offered the host's placing spells (host31; agent 10).** Words asking a thing to want or watch for
   something had no form hob could answer with: `heardOffers` listed a card's own forms alone. `placingForms` adds,
   on the card the words reached (not its doors'), `rule`, `want`, `unrule` and `unwant` that the card does not declare,
   for a speaker its law admits placing (`kindAdmits`, kind 4, the placing's verb), their fields the usage's
   (`ruleLine`/`wantLine`: `name`, `when`, the spell `then`/`asks` last; `unrule`/`unwant` `name`). `proposalVerdict`
   accepts such a proposal without a compiled method, its fields checked by `placementsOf`, and `runHeard` stages it
   as the spell does; the law judges it at the commit. `grow:` stays hob's own answer (`growVerdict`). Tests:
   `test_heard.Heard.test_hob_is_offered_the_hosts_placing_spells_…`; the offered tables of `test_heard`, `test_policy` and
   `test_hub.RootReadsDoorForms` name them (`PLACING`).
187. **The model's answer is its text (host31; the simplify hand-back (3), fungus H3).** `interpretVerdict` reads a
   reply's `raw` alone: the JSON `{method, argument}` branch is gone (the transport's `model` has long sent text
   only), so a reply without `raw` is a request error, and every proposal is a spell fitted to an offered form. Tests
   reply in text: `test_reflection.Interpret` (its probe's offered form now names `n`; a JSON reply is an error),
   `test_sum_words` (its garden's offered `plant` names text fields, so the words are read as cases by
   `proposalVerdict`), `test_block_store`, `test_snapshot`; `test_policy`'s unused `planting` is gone.
188. **The opener's root-only ops answer a class (host31; the simplify hand-back (4)).** A root op on the public socket
   is `{status: error, class: "opener", message}` (`Serve.errorJson`'s `cls`), so a client matches the class, never
   the prose. The bridge's match of that message (`transport/host.py` `ON_ROOT`) is gone: the bridge sends
   `world-turn`, which never answers it (the opener's own posts run as a resident's turns, ROOT §1.4). Test:
   `test_serve.Serve.test_the_root_ops_speak_on_the_root_socket_only`.
189. **`world-inspect` answers each offered form's template (host31; the simplify hand-back (7), fungus T33/H17).**
   `world-inspect`'s `templates {action: spell}` is each offered form as `?` prints it (`spellTemplate`, its blanks
   `spellHint`'s); the front's `_actions` copy it (`http.py` `actions`), and its own composer (`shown`) is gone, so
   an agent reads one template wherever it reads one. Test: `test_hypermedia.Controls.test_acting_from_the_reply_alone`
   (the template is the host's; `fill` reads the host's blanks).
190. **Whether a turn may be posted is the host's answer (host31; the simplify hand-back (1)).** An admitted entry's
   reply and receipt carry `inPublic` (`TurnLoop.inPublic`: every object of its roots and writes viewable by the
   public reader now), so a draft carries what the turn offered only then, else its receipt line. The transport's
   `bridge.public`, a `world-view` per object of every drafted turn, is gone: `draft_public(reply, …)`, the settled
   offers' draft (`world-receipt`'s `inPublic`) and the front's HTTP draft rule (`Front.draft_turn`) read the field.
   Test: `test_bridge.Private` (the private and the public turn's receipts answer it); the bridge's `Stub` answers it.
   The front's HTTP draft rule is now this field and the front's own policy (it drafts an admitted write, never a
   guest's): the simplify hand-back (8)'s first half.
191. **How many mentions a post addresses is the host's bound (host31; the simplify hand-back (8)).**
   `Limits.mentionsAddressed` 4, answered by `bounds` (`host.mentionsAddressed`); the bridge reads it once a run that
   observed a mention and turns only that many (`mention_turns(…, addressed)`); its `MENTIONS` is gone. Test:
   `test_bridge.Mentions.test_only_the_first_mentions_the_host_addresses_are_turned` (the host answers 4; a stub
   answering 3 gets three turns).
192. **Where a receipt stands is said only while it stands (host31; §7 seen in passing).** `revealed`'s third line
   counts a relation as the world holds it now, so `world-receipt` of an old rain said today's count as the entry's.
   `TurnLoop.revealed` says it of a thing only while the thing is at the version the entry wrote. Test:
   `test_rules.Revealed.test_where_a_receipt_stands_is_said_only_while_it_still_stands`.
193. **A page of history asks the host's bound (host31; §7 seen in passing).** `transport/host.py`'s `HISTORY_LIMIT`
   restated `Limits.maxHistoryLimit`, and `root.modlog` sent `limit: 100`: both read it from `bounds`
   (`history_limit`). Test: `test_hand.HistoryBound`.
194. **A layer checked over what it is laid on; a making takes a stack (lane/author-build; AUTHORING §5 host 1, steps
   2, 3, 5; no edition change).** `world.check {package, layers}`: `package` as `create` takes it (a module of the
   checking object's closure, or source), each of `layers` laid over it as `extend` lays one (`layeredInputs`), compiled
   for `initial` (`TurnLoop.checkStack`, `Ops.checkInputs`); a package of source with no layers is `checkSource`'s, as
   before. `world.checkObject {object, layers}`: what the object runs with `layers` over it (`Ops.checkObject`). Both
   count against `checksPerTurn`. `extendInputs` writes the right `layer over ./<entry>.obend` in place of an author's
   own first `layer over` line (a body written over RECORD laid over a bell's body), so a layer's line numbers are its
   author's. A making takes several layers (`CreateRec.layers`, bottom first; `extendCreation` builds the creation
   again with all of them, each judged by the made thing's law; the `duplicate` refusal is gone). A typed `view` whose
   state does not conform to the call site's `S` answers `refused typeMismatch`, no longer an evaluation error. KIND
   (Bend) uses all three: `stackOf` asks `world.kindStack` (`Ops.kindStack`) for the root package and ancestor bodies
   (four deep); `kinds make` checks the body over that stack and refuses `body` with the checker's lines (the instance-time
   `refused body` is gone); a kind's things install that stack through `world.compose` (5.219); `~checkBody` serves the workshop's
   `check / over:`. Tests: `test_authoring.Authoring`.

195. **A clause reads a made thing's form fields; a spell's field binds in any case (lane/author-build; AUTHORING §5
   host 2, step 6).** `Law.fieldReading`: a name the state has no field for is read from its `fields` rows (`{name,
   value}`, what its kind's make took; `namedValue`), digits as a number, so `count(new.lines where verb == "rain") ==
   new.ringAt` holds at the number the maker chose; `#guard`s beside `monotone`'s. `Spell.spelled`: a binding whose
   folded name is a form field's takes the form's spelling (`ringAt: 3` was folded to `ringat` and never bound a
   camelCase field). Test: `test_authoring.Authoring` (§6.1's tally, its law corrected: a rule fires under the kind's
   owner, so "only its maker rings it" refused the rule's own ring; the build's law says "at its number, not before").

196. **What a check says of reach; every missing import at once (lane/author-build; AUTHORING §5 step 4, D-receive,
   D-imports).** `check`/`checkObject` answer `checked {diagnostics, reaches}`: `reaches` is whether what compiled has
   a `receive` (`Ops.answersSpells` on the artifact's methods; `checkDiagnostics` compiles once, lawful, and returns
   both; `TurnLoop.checkedData` answers `{diagnostics}` alone to a call site compiled before `reaches`). The workshop
   refuses a draft no spell reaches (`noReceive`) and says so under a clean `check`. The kernel's package loader
   (`Package.missingLibraries`, called in `modulesAndAsts` before each module is parsed) names in one refusal every
   library import a module needs and lacks when there are two or more (`Form` and `List` for form blocks, `Plan` for
   `write {…}`/`keep()` beside a State, `World` for `Activity<…>` with no World module in the package); one alone is
   still refused where it is used. The workshop writes a layer's header itself (`Forms.layer`, shared by KIND's
   bodies and `draft / over:`); a held draft over a kind is made by the kind (`~makeDrafted`), over a thing laid on it.
   Tests: `test_authoring`, `test_sugar`, `test_workshop`.

197. **Where a thing's code came from (lane/author-build; AUTHORING §5 host 3, step 7).** `Object.madeFrom`: the
   journaled `madeFrom {object, pin, receipt}` of the `make` that made it or of a reprogram that carried one
   (`become`), set as the commit installs it (`Ops.judge`: `creations`, and the reprogrammed `next`, keeping an earlier
   one when the reprogram carries none), live and replayed alike; the snapshot keeps it under `madeFrom` when present
   (an older snapshot has none). A `make` whose `madeFrom.receipt` is "" cites the turn that made `object`
   (`TurnLoop.madeReceipt`). `?` prints `lineageLine`, "After kind/tapper by yue.delve.town, entry 66.", the principal
   of the cited entry; `world-inspect` answers `madeFrom` and `lineage`. KIND's `~makeFork` (by `kinds`) makes a kind
   forked whole with that lineage; the workshop's `draft / from:` holds one. Test: `test_authoring`.

198. **A verb grown with a body (lane/author-build; AUTHORING §3 (b), §5 objects 4).** `castSpell`: a direct `grow`
   carrying `body` runs `workshop`'s `growBody {object, name, reading, takes, body}` (`workshopId`) as the speaker's
   turn; `growLine` shows the field. The workshop (Bend) writes the one method (`verbLayer`: its `form`, and a `def`
   whose result is a number), lays the header (`Forms.layer`), checks it over the thing and `extend`s it when the
   thing's law lets the grower reprogram it, else holds it over the thing for whoever its law lets lay it (`adopt /
   n`, `laidOn`). A grown verb with a body is a declared method, so no verb row is placed. Test: `test_authoring`
   (with the verb library: a one-verb kind laid by `become`, `?` saying what it is after).
199. **A kind's new form re-lays its make (lane/refresh-fix; §7 2, the refused v9 to v10 carry).** The refresh
   wrote a kind's `.form` text by a write, so the make and place the kind offered (its make layer, laid from the
   form it was made with) no longer matched its text: the live v9 town's `kind/weather` said `over:` and took
   `garden`, and the motion's weather, placed with `over`, waited on hob. `Kind.reshape {form}` (the owner's,
   unoffered) lays the make layer again from the new form (`world.reprogram` of its top module with
   `layerSource(of, form)`), then writes the form, in one turn. It is refused by name, its form left, when the
   kind's code over Kind is not the make its form laid (a layer laid over the make). `deploy/genesis.py` `refresh`
   re-shapes a stale `.form` through it; `carried_fields` reads the place form the kind offers (`world-inspect`
   `templates`, 5.189), not the text. Tests: `test_genesis.Reshape` (a town whose weather kind was made with
   `garden:`: form refreshed, the place offered with `over`, the weather placed `refreshed` and raining on bell/1
   the day someone entered the porch, a second refresh all `current`; a kind with a layer over its make refused).
200. **Tending is read by the clock (host32; §7 2 (a), the live bell/1's "untended since entry 27").** A record or thing
   kept `tendedAt`, the entry it was last tended at, beside `tended`, the clock minute, and the bell's card said "untended
   since entry N" while its law and want read the clock. v8's 27 survived the v8 to v9 carry, which began heights again at
   1 (edition 10), into a sequence where 27 is a v9 clock advance; no stored height says which chain it counts (Bend has
   no height type, and the rows a migrate moved match nothing at the restart), so no carry can re-base one. The clock
   runs on across every carry: `tendedAt` is gone (Record's and Thing's `State`, Kind's make seeds, every write), the
   bell says "quiet, untended a day" / "untended three days" (`untended`, whole clock days) or "quiet, never tended" for
   one tended at clock 0 (a genesis makes its things before the transport sets the clock: the live bell/1 and bell/2),
   `quietSince` answers the clock minute, and the strokes' `tended` is the clock minute (0: never). Record's and Thing's
   `migrate` read the edition-12 shape (`State12`) and drop the field; their edition-9 and edition-8 readers are gone
   (no world holds those shapes since v10). The carry of the newest live backup (delvetalk-20261012T160615Z, v10 at 468)
   moves 22 objects, 9 through `migrate` (bell/1, bell/2, commonplace, porch, porch/lamp, weather, porch/goblet,
   porch/ring, porch/gemstone), and bell/1's card then says "quiet, never tended". What other residue of v8's chain the
   live town holds (read against v9's genesis): the commonplace's line 1 (`at` 58) and its admission (`at` 59), which no
   card or chronicle of v10 reads (a day's lines are this journal's heights), and the wanting index's `since` of the v8
   wants (26 to 34), which orders "What wants a hand" alone. Tests: `test_tending` (a day, three days, never tended; the
   view's clock minute), `test_carry.Carry.test_a_carried_world_counts_its_heights_on_from_the_world_before` (a rain's
   `at`), `test_enchant` (the town's clock set before its making), `test_receive`.
201. **The morning's wants are what still wants a hand, oldest first (host32; §7 2 (b), `hand morning` of day 20737).**
   The live morning painted the eight open wants under "Answered so far:": the day's strokes listed each "answered by:
   <spell>", and day 20737 held nothing else (it lies in v9's journal), so the painter read them as answered.
   `wanting` (and `world-wanting`) takes `oldest`: the longest waiting first, paged past `after` the other way; the
   morning's strokes (`wantsOfDay`) read it as `hand morning` lists them exact beneath ("What wants a hand, oldest
   first" said so of a newest-first list), titled "What still wants a hand, oldest first", by reading and without
   spells, so the `spells` clause refuses a morning paint that names one (the contract's "no spell"). A thing's want
   reads "the spell it asks for: …". Tests: `test_enchant.Strokes.test_the_day_and_the_morning`,
   `test_wanting` (`oldest`, paged), `test_hand` (the exact list's first row the longest waiting).
202. **carry-check says when the image moves objects (host32).** A candidate whose library replays the backup but whose
   packages or bodies differ (5.200's Record) said plain green, and a restart in place keeps every object at the code its
   journal sealed. carry-check reads each world line's `moved`: "green, moving: the deploy must carry: … the image moves
   N objects (…), which a restart in place keeps at the code they had; it carries". Test:
   `test_carry_check.CarryCheck.test_carry_check_says_a_deploy_carries_when_the_image_moves_an_object`.
203. **A plan is one turn (lane/plan).** On delve.town a post is the interface and the town shares `postQuota` (16)
   posts an hour, with no draft-and-try loop (docs/POSTING.md), so one post must make a kind, make one, and place a
   rule on it, all or nothing. A post with `delvetalk plan` at the margin, or a fence tagged `plan`, is a plan
   (`Spell.plan`): every spell of the post an act, in order, at most `Limits.planActs` (8; past it `tooManyActs`).
   `runTurn` runs it as ONE turn under the post's identity (`runPlanTurn`, `runPlan`): each act is read when it
   comes (`routeSpell` on the turn's world) and runs at the top of the turn as a spell posted alone does (a card's
   method frame; a placing staged by `stagePlacements`; `become`, `adopt`, `lend` staged from `hostChange`, which
   `hostSpell` commits for a spell alone; the opener's powers are entries of their own, `notInPlan`). Nothing is judged
   until the one `finishTurn`: `judge` judges every law against the world the acts leave, `reactions` fires rules once,
   one receipt. A later act reads what earlier acts wrote (`asWritten`) and made: what a turn creates is an object of
   the turn (`madeIn` puts it in the turn's world; `judge` judges roots, writes and placements on it over the state it
   is made with, its own law judging them; the commit applies the creation, then the update), and a hole `{made N}`
   is the first object act N made (`fillHoles`; a hole naming no earlier act, or one that made nothing, `hole`). A
   refusal in a frame refuses the plan whole, its reason `act N (<spell line>): …` (`inAct`; an act that would wait,
   `planWaits`); a refusal at the commit is named by the act that staged its object (`planRefusedAct`, from the
   entry's `plan {acts, of}`: each act's line, card, `done` (`ran`, `staged`, `read`), `made` and `touched`). The
   reply carries `plan` (with `refused`), the acts' lines first in `revealed` (`1. <spell>: made kind/lamp`), and a
   refusal's public projection `act`/`acts`, which the bridge drafts as "act N of M refused, so none of the plan was
   done:". A plan is one reply, so one post of the quota. `try` (lane/posting's `world-try`) is this same `runTurn`
   with the world dropped, and `if:` (`world-turn`'s, or the margin line above the plan) guards it whole. hob may
   answer with a plan (the policy's answers say so): the verdict `plan {acts}`, the host's reading only, runs through
   `runPlan` at `resumeHeard`; hob's settled steps run there too (`runHeard`). Replay: an entry that creates and then
   writes or places on what it made, or creates a thing citing what it made, replays (`rebuildCreates` builds each
   creation over the ones before it); no earlier entry could hold either, so the derivation of every existing journal
   is unchanged: no edition change. Tests: `test_plan` (kind, thing and rule in one plan, replayed; a third act refused
   in its frame and at the commit leaves nothing; holes; too many acts; a fence; later acts read earlier writes),
   `test_bridge.Bridging.test_a_plan_is_one_turn_one_draft_and_one_post_of_the_quota`,
   `test_heard.Heard.test_hob_may_answer_with_a_plan_that_runs_as_one_turn_and_stands_or_falls_whole`.
204. **`world-try`: the commit with the write switched off; `if` and `moved` (lane/posting; docs/POSTING.md §2; no
   edition change).** `Session.settledStep` is a step and its settling pass, the world they leave and the reply;
   `durableIO` makes that durable, and `world-try` (`tryTurn`) drops it, answering the turn's own reply with `tried:
   true` and `against {height, hash}`: its receipt the entry that would be journaled (roots with versions, writes
   with their state CIDs, which a `world-turn` at the same head lands byte for byte), its offers the exact cards.
   `world-turn` and `world-try` take `if: [{object, version}]` (at most `maxRoots`); a root that moved, or that the
   principal may not view, answers `{status: refused, class: moved, moved: [{object, was, now}], line}` with nothing
   journaled (`movedRoots`, `movedReply`). A post says both (`Serve.postShaped`, beside `expiryAsked`): a margin
   line `if: bell/1 v0, kind/bell v2` ahead of the spells is the act's `if`, and `delvetalk try` with spells
   indented under it is `world-try` of them, dedented, as direct words to the commonplace (`Spell.heading` reads the
   line alone as card `try`, `Ops.tryCard`, an id no object takes). The front's action takes
   `try: true` and `if`; the bridge drafts a try as `preview, nothing done` (`bridge.preview_text`, no receipt name,
   its last line the `if:` to send it under, `then …` for what the settling pass ran, and what it leaves for later,
   `unresolved {pending, suspended}`, counted) and a `moved` as its line. An `if` that does not read (`if: bell/1`) is
   refused `moved` too: a guard fails closed. The observer keeps a post's leading indent (`observe.LEADING_BLANK`), so
   an indented spell among words stays a quotation through the bridge as it is to the parser. Tests: `test_try` (the CIDs shown are the
   CIDs landed, a moved act journals nothing, a post's indented spells never cast, the bridge's preview and its
   guard).
205. **A receipt looked up by post (lane/posting; the astra posting review (7); emergence §10's as-if receipts).**
   `delvetalk receipt / of: <slug or at:// post>` (`Spell.heading` reads card `receipt`, `Ops.receiptCard`, an id no
   object takes) is answered by serve (`Serve.receiptAsked`) from the home world's `world-resolve` (a slug) or
   `world-receipt` (the asker's own post), journaled nowhere: `{status: "looked", of, found}`. The value is read to the
   line's end, so an at:// address keeps its `/`. The bridge drafts the receipt's line, or "no receipt here is named
   X: no host issued it, so it records nothing" (`bridge.lookup_text`). Test: `test_posting`.
206. **One resident's share of the hour's posts (lane/posting; the astra posting review (6); no edition change).**
   `world-post-reserve` takes `for`, the resident a post answers; it is journaled on the `reserved` outcome and kept
   on the `Reservation` (`resident`, in the snapshot only when set). `postShare` is a quarter of `postQuota`, at least
   one; past it the reservation is refused `quota` with `share: true` and the reason naming the share, while other
   residents' and the hand's own posts (no `for`) go on. Replay holds a reservation to the share as to the quota. An
   entry without `for` (every one before) counts against no share. `world-status.posts` adds `share` and
   `residents {principal: used}`. The transport passes the draft's author (`post.answering`: not the hand's own
   drafts, not publications) and a thread sizes itself by the smaller room (`post.room`). Test:
   `test_post_reserve.Shares`.
207. **`delvetalk guide` (lane/posting; docs/LIBRARY.md "The guide, shelved").** `Spell.heading` reads `delvetalk
   guide` alone as `delvetalk library read / page: guide` (`Ops.guideCard`, an id no object takes), the guide's
   contents page; its parts are pages `guide-1` … shelved from docs/AGENTS-API.md by genesis and its refresh. Test:
   `test_posting` (the parts joined are the front's text).
208. **A hole's reading is data, never spell syntax (astra 2026-10-12 world.md 4).** `Law.fill` joined a spell's text
   and its readings into one string that `Ops.reactions` staged as `receive {text}`, which `routeSpell` reparsed under
   the rule owner's authority, so a resident's `\n` + `delvetalk ...` line, ` / to: eve` or `<<END` in a read field
   changed the card, action or fields (`Ops.wantAsks` showed the same string on cards). `Law.filled` now parses the
   template once with each hole a placeholder (`placeholderPrefix`), takes a reading into a field VALUE only
   (`substHoles`; a card or action must stay a card name or action, a field name may not hold a hole), and writes it
   with `Spell.renderChecked`: `Spell.render` puts values inline (`inlineSafe`, so ordinary spells read as before),
   from the first unsafe value on one field a line, an unsafe one as `name: <<DELIM` (`blockDelimiter`: no value line
   closes it), and the check parses the text back to exactly that spell, one `segments` entry. `Law.fill` keeps its
   signature (`Filled.text`); `Ops.reactions` tells `hole` (a hole read nothing) from `spell` (not one spell after
   filling). A room's spween `~ cast` choices are rules of the room's text (`Scenes.ruleText`, world/lib/Scenes.obend
   :160-173) and fire through the same `reactions`, so they are covered. A reading that quotes a card (header line
   beside a `delvetalk` line) is refused as `spell`, as a quotation casts nothing. Tests: `#guard`s in Law.lean and
   Spell.lean (round trip over hostile values, card/name holes), `test_rules.Holes` (a cited text of KIM's bell,
   fired note and want `asks`).
209. **Tenure: a thing's owner keeps it; a rule it inherits acts as the thing (lane/authority; astra 2026-10-12 world.md
   1, 2, 3; replay edition 13 with 5.210's queue).** A kind's text held its things' whole law: a kind made with one
   `law` line of its maker's dropped RECORD's (`Kind.lawFor`), and its owner, amending it, could take every instance
   from its owner or lock them out. Now each thing holds its owner's law in its own text, `Kind.lawOf package` (its
   root package's `baseLaw`: `Record.lawText()` or `Kind.lawText()`, then `law kind: under "<kind>"`), and a kind's
   text is only its own clauses (`lawFor`; genesis's `KINDS`, `kinds`' `law` ""). `Law.ownerAmends`: an `under` atom
   holds of an amendment (kind 2) by the citing state's text `owner`, so while a thing follows its kind the kind binds
   it, and its owner can always amend it out from under it. A rule a thing carries from its kind's text acts as the
   thing (`Ops.thingPrincipal`: `@<id>`, which no object id, DID or handle spells; `principalThing`; `carried`'s
   followed lines; `unviewable` lets it view itself; `resolveCard`'s `me`; `shownName` shows the id), so the kind
   owner's authority is never lent to code a resident lays below or over the kind, nor the instance owner's to the
   kind's live text; a line of a thing's own text acts as its owner, a placed one as its placer. `carried` orders own
   text, inherited, placed. `genesis.refresh` first `rebased` a carried town's things whose law is only their kind's
   citation (RECORD_LAW or KIND_LAW then that text), before their kinds' texts lose RECORD_LAW. Tests:
   `test_tenure` (red on foundation), `test_kinds` (a kind with no law clause), `test_genesis.Refresh` (bell/2
   rebased), `test_authoring` (§6.4's trade is its keeper's placed rule), `test_rules.Revealed` (the bell notes its
   planter itself).
210. **Rules queue, are judged as their own, hold a share; an errand is one settlement; marks are facts
   (lane/authority; astra 2026-10-12 world.md 6, 7, 8, 9; replay edition 13).**
   - *Queued, never dropped* (7). `Ops.reactions`: past `Limits.rulesPerCommit` a firing is staged with `next =
     clock + i / rulesPerCommit`, so each next eight are deliverable a clock minute later; the `rulesPerCommit`
     unfired reason is gone. `revealed` says "fired (queued until clock N)". Carried clauses run own text,
     inherited, placed (5.209), so residents' placed rules no longer crowd out a kind's.
   - *A rule is its own judging* (6). `judge` meters the law's clauses alone against `lawTicks`; `objectCitations`
     is the law's citations alone, so what a carried rule or want cites is no root of the write; each rule's
     condition is metered in `reactions` against `Limits.clauseTicks` (`lawTicks / 8`, `unfired budget`), each
     want's in `posing` (a want past it does not pose). Placing: a hand other than the owner (or the opener) holds
     at most `Limits.placedPerHand` (4) rules, and 4 wants, all such hands `placedByOthers` (24) of the 32
     (`capacity placedPerHand` / `placedByOthers`).
   - *The errand* (8, world/bodies/errand.obend). One rule on `on` (`settles`); `settle` claims for the doer, once,
     in one turn: `done` mark, `settles` off `on`, and `pay` placed on the errand, `"done" in new.marks.name and
     (request.method == "settle" or request.method == "repay")`, its `pays` with `{request.subject}` replaced by
     the doer (`payFor`, `replaced`; a doer is one word, `oneWord`), firing at that very write. `repay` (the
     maker's) writes a `repay` line, which fires it again for the same hand. `awaiting`, `receipted`, `unpaid`,
     `payIntent` are gone; `arm` still takes an older errand's `_v` rule off.
   - *Facts* (9). Record's `marks` have no retention (`limit 0`): a `rung` or `done` is never dropped. A count of
     lines counts the retained 128; `next` counts every line (AUTHORING §6.1's `ringAt` is `1..128`).
   - Tests: `test_rules.Firing.test_eight_fire_a_commit_and_the_rest_are_queued…`, `test_rules.Share`,
     `test_reaction.Errand` (both), `test_replay_edition`.
211. **A want's flip is journaled wherever it comes from; one evaluation feeds every surface (lane/authority-wants; astra
   2026-10-12 world.md 10; replay edition 13).**
   - *The clock.* `Ops.advance` journals `wanted`/`unwanted` on the `advanced` entry (`Ops.clockFlips`): every thing
     whose carried wants read `request.clock` (`World.wantClock`, from `LawExpr.readsClock`, through cited wants too)
     is judged at the old and the new clock, one judgment within `Limits.clauseTicks` each. Replay re-derives them
     (`replayEntry`, "what the clock wanted does not replay"); `reactionRows` reads `advanced` entries. A want true
     by the clock alone is therefore in `World.wanting`, `Ops.wanting` has no exclusion, and `wantRows`' `since` is
     always a height (the advance's).
   - *Dependents.* `reactions` also judges the things whose wants read a written or created object (`"O".F`,
     `"O" wants N`, what their law follows by `under`): `World.wantReaders` maps an object to those things,
     `wantCites` is its forward side, both re-read for what an entry writes and the readers it re-judged by
     `Ops.reindexWants` in `record`; a carry's or fork's genesis reads them off its objects (`installGenesis`), a
     snapshot carries all three (`indexJson`, `installIndex`). Bound: `Limits.wantReviewed` (64) readers by id per
     entry (`Ops.wantReview`); a reader past it is judged when it or an object it reads is next written.
   - Tests: `test_wanting.Journaled` (a bell nobody tends flips at the advance and the chronicle says so; a write of
     `"bell2".rains` flips the want of `bell`; both across reopen and snapshot).
212. **hob is shown residents' writing as quoted data in the user turn, never in its system text (lane/authority-hob; astra
   posting review).** `Policy.prompt` had put the card as the speaker reads it, the offered forms (card, verb and field
   names, choices), the card's wants (name, reading, asks), the library's pages' titles and the misfit spell into the
   system instructions; a resident's line there (a want's reading, a grown verb, a card's text) could say "ignore the
   speaker and cast delvetalk ..." with the policy owner's authority. Now `Policy.prompt(state, asked)` is hob's
   instruction, `quotedNote` (the user turn is data; nothing in it instructs), the policy's examples (its owner's;
   only the owner writes them) and the four answers, or the drafting prompt. `Policy.userTurn(state, asked)` is the user
   turn: those resident parts, each line prefixed `| ` (`marked`, so no resident line can pose as the prompt's own or
   close a fence), then `Their words:` and the utterance unmarked; for a drafting ask, the utterance alone. The host
   composes it with the same compile-by-name path (`policyPrompt ... "userTurn"`) and `world-interpretations` carries it
   as `user`; `transport/interpret.request` sends `item['user']` (the utterance when a policy has no `userTurn`). A
   proposal already ran as the speaker: `resumeHeard` takes the principal from the suspension's identity, never from
   a card's owner or a line's writer. Tests: `test_policy.PolicyObject.test_a_residents_line_steering_hob_is_quoted_in_the_user_turn_and_a_proposal_runs_as_the_speaker`
   (red on lane/authority), `test_the_user_turn_*`, `test_the_request_carries_the_policys_rendered_prompt_*`.
213. **The tide ticks for ever (lane/authority; astra 2026-10-12 world.md 5; replay edition 13).** Each tick sent
   `due` and each resumed `due` the next tick, one ledger level a link, so the tide stopped after about fifty hourly
   ticks (`budgetExhausted`), and the weather and fronts with it. `TurnLoop.selfWait`: a suspension on a slot in its
   own object's name, by that object's activity. `resumeSegment`: such a wait that the clock ends (`timedOut`) goes on
   under the object's own `chain`, not what was left of the chain that waited: the clock is the new cause, a whole
   budget each period; a missed period is one wake at the clock it wakes to. `awaitPlan`: an object holds one such
   wait at a time (`refused waiting`), so it cannot multiply, and every wait spent real clock time (`patience` is
   never 0). No schedule registry: the tide stays the one thing that writes on the clock. Test:
   `test_reaction.Ticking` (120 hourly ticks; 50 on foundation).
214. **The edition-13 carry of the live town (lane/authority).** `deploy/carry-check.sh` with this lane's binary on
   hbox against `/tank/delvetalk-backups/delvetalk-20261012T185249Z.tar.gz` (v12 at 725): "green, breaking: the deploy
   must carry", 127 objects rendered, none left, no problem; the refresh rebases 18 objects whose law was their kind's
   citation alone (the twelve town kinds; bell/1, bell/2, porch, porch/lamp, room/1, weather) and then gives each kind
   its own clauses. On the way: Record's `migrate` read the edition-12 shape with `tendedAt`, but the live town has
   been the shape after 5.200 since its v12 deploy, and lane/spween's `chose` made seven records "left at the carry";
   `State12` is now that shape, `chose` "".
215. **The town's reads: the book (lane/books).** A read is a spell answered as `?` is, journaling nothing, its text the
   card's own pure Bend definition of the read's name run on its committed state, handed the index the host folds of
   the store as the reader may view it (`Surfaces.lean`: `reads`, `answer`, `run`, as `renderWanting` is handed what
   wants a hand). `castSpell` answers one before `?` (`SpellRoute.read`, the reply `usage` with the read's extra
   fields); a card with a spell of the read's name keeps it. `book` (`Avatar.book(state, context, World.Deeds)`):
   `deeds` is what a principal made (the state's `maker`, else the entry that made it, else its owner; a carried
   thing's entry is the world before's, so none), grew (`Object.verbs`), placed (`Object.rules`, `wants`), wrote
   (`lines` by author) and visited (`presence`, `left`), oldest first. A card is named by a handle too (`namedCard`:
   `me`, an id, folded, or a resident's handle naming their avatar) in a spell and in a direct turn, so `delvetalk
   kimik3.delve.town book` reaches that avatar from the bridge. `world-surface {principal, object?, read, fields?}`
   answers the same text for the web (`/o/<handle>/book`). Pages: `Card.paged`, `Card.pageOf`. The whole of a read
   or a card for the threader (the posting lane's `parts`): a read's reply carries `whole` (page 0 handed, every page)
   beside its first page when they differ, and `bridge.draft_text` drafts it; `world-card {whole: true}` and a read
   rendered whole give the Context `inputOrigin.kind` `whole` (`Card.wholeKind`), for which Bend's `Card.limit` is
   none. Tests:
   `test_surfaces.Book` (made, heard, grown, placed, wrote, visited; by handle with what the reader may view; the web
   equal to the post; pages covering every line once; `whole`), `test_surfaces.Whole` (the commonplace whole and
   clipped), `test_surfaces.Web`.
216. **The town's reads: the history (lane/books).** `chronicle` (the commonplace's `chronicle(state, context,
   World.Annal)`) is a town read: `Spell.townWords` reads `delvetalk chronicle` (alone or with inline fields) as the
   square's spell, and any card without a spell of that name is read by the square's. `Surfaces.annal`: the day
   (`day`, else `from`, else `to`, else today), its date (`civil`, the clock in unix minutes), today, the journal's
   first day, the range, the page, `Ops.chronicle`'s lines and `firsts` (the earliest rain line, room (`offers
   enter`), grown verb, coinage, and rule firing: the journal's first `fired` row, else a carry's `ruleLog`). The reply
   carries `paint {day}`; `bridge.read_text` and `/history` set the day's paint above it. `Ops.chronicleDay` credits a
   made thing's coiner (`coinerOf`, reading `Record.post` as Enchant does; an unknown handle is `the author
   of <post>`) and leaves avatars out. Tests: `test_surfaces.History`, `test_surfaces.Web`.
217. **The town's reads: the map (lane/books).** `map` (the commonplace's `map(state, context, World.Ways)`) is a town
   read (`Spell.townWords`: `delvetalk map`; any card's `map` without its own spell of that name). `Surfaces.ways`:
   every door (`cites`, a link door left out) on a card the reader may view onto one they may view, cards in id order,
   and how many things lie in each place; `pathTo`, the shortest way from the square. The reply carries `ways` and
   `root` for a drawing; `/map` draws them (`pages.door_map`). Tests: `test_surfaces.Map`, `test_surfaces.Web`.
218. **A body replaces its gesture and its rule in one turn (lane/cx-world; astra 2026-10-12 world.md 12).**
   `Workshop.growBody` laid a method over a gesture without removing its `Object.verbs` row or the rule it `does`,
   so the method and the old rule both had a consequence. `Workshop.layingLayer`, shared by `bodyLaying` and held
   layer adoption (`laidOn`), reads the layer's `Forms.formNames`, checks each through `world.ungrow {check: true}`
   and, after `world.extend` admits, stages the same `ungrow` removals (`replacing`). `TurnLoop.stagePlacements`
   with `check` uses the same `Ops.judge` without staging: the gesture's grower, the thing's owner or the opener
   may remove it and its rule. `viewField` can read the state's owner, but the verb's grower and the attached
   rule's owner are host rows (`Object.verbs`, `Object.rules`), not State fields; checking through `judge` also
   preserves the opener's authority and the judgment of placements already staged in the turn. The world arm
   reads `check` by matching `.boolean`, as `inspect` reads `source`; the workshop's `replacing` is the only
   `world.ungrow` call site, passing that flag for both phases. `replacing` returns `World.Placed`, with a removal
   refused as `nameTaken`, naming the gesture and its rule (`judge`'s `notPlacer` reading); `layingLayer` matches
   its `placed` and `refused` arms and ends a refused turn through `refuse(Card.refusalLine(...))`, so the
   failure's clause and reading are formatted by the same function as `Card.refusing`. An `extend` refused by
   the thing's law holds the body with neither removal staged; the owner's adoption checks again and commits
   both removals with the layer and the held row's
   retraction. A verb's own writes stand or refuse synchronously under its user's name; any rule reaction follows
   the commit under its own owner. `TurnLoop.verbsText` names the gesture's effect (a line and tend) and its rule
   reaction separately. Journal state derivation is unchanged: the existing `reprograms` and
   `placements` record both effects, and replay applies their existing judgment. Tests written before the change:
   `test_authoring.test_a_gesture_and_its_does_rule_are_replaced_by_one_bodied_verb` (one water line at the 280-character
   input limit, no rule), `test_a_strangers_body_cannot_replace_a_gesture_they_cannot_take_off` (`nameTaken`, no
   target or workshop change, the gesture's reaction still works), and
   `test_a_held_body_replaces_the_gesture_only_when_its_owner_adopts_it` (gesture and reaction live before adoption,
   one consequence after).

219. **A kind composes alike made and become (lane/cx-world; astra 2026-10-12 world.md 13; replay edition 14).**
   `become` laid only a kind's immediate body, cited none of its text, and stacked another copy on every use.
   `Ops.kindStack` is the one stack definition, reading `of` four deep, ancestor bodies bottom first; KIND's
   `stackOf` asks it through `world.kindStack`, for checking, making and drafting. Its result carries
   `kindCitation`'s line for `Kind.lawOf`, also used by `TurnLoop.kindChange` through `appendedLaw`, `adopt`'s
   amendment path. `kindCitation` uses `Ops.citedLaw`, the same parser-backed check as `citationRefusal` for
   `under`: a kind whose state holds no followable `law` text installs its bodies and lineage without a citation
   or amendment. Later adopting a law on that kind object affects the kind alone, leaving those things' text
   unchanged. An existing citation of that kind is retained; another kind takes the first free name among
   `kind`, `kind1`, `kind2`, …, preserving the thing's original citation. `Kind.composing` asks `world.compose`
   when making a thing; `hostChange`'s `become` uses the same `kindChange`. Code and text stand or refuse in one
   turn under the thing's own law. `madeFrom.components` holds one row per source kind `{object, pin, receipt,
   body, at}`, where `at` is its body's position among the closure's layers (an empty body occupies none).
   `noBody` is gone: an empty immediate body still installs the ancestor stack, followable text and identity.
   The catalogue's `badSpell` clause list drops it; `unknownKind` remains in `kindChange`, and `lawClash` in
   `appendedLaw`. `test_hypermedia` scans those two and `hostChange` as the host spells' refusal sites and keeps
   exact equality between the catalogue and the host's closed set.
   `componentInputs` replaces those bodies in place through `layeredInputs`, skipping unchanged bodies and
   pins and retaining all unrelated layers. A source already installed as an ancestor is never duplicated.
   Body amendments change state, so can change a receipt without changing the kind object's code pin;
   installation compares body and pin, and retains the installed body's receipt when those are unchanged.
   An unchanged repeat stages no reprogram or amendment and keeps the thing's version. A replacing ordinary
   reprogram detaches the component row for its entry module (`programLineage`); extending retains the rows.
   A making journals the final closure and the component rows on its creation, preserving a draft's original
   credit; `extendCreation` preserves those rows when laying a draft above it. Snapshots already carry
   `Object.madeFrom`. Reprogram replay supplies the recorded rows to `programFor` and `prepareProgram`;
   `Proposal.digest` includes the component lineage, and a prepared program's key includes it and the old
   rows. This changes journal state derivation: edition 14, requiring the carry check. Tests written first in
   `test_kinds`: `test_made_and_become_carry_the_same_verb_and_live_kind_law` (the same fourth water refused;
   280-character waters), `test_become_lays_all_bodies_of_the_deepest_stack_bottom_first` (four bodies, three
   `Super.water` hops reach the bottom), `test_become_twice_keeps_one_component_one_citation_and_its_pin` (made and plain),
   `test_become_upgrades_in_place_and_preserves_a_layer_above_it` (a removed verb gone, new body used, the
   unrelated layer stands, snapshot and replay), `test_become_refuses_code_and_citation_together_under_the_things_law`
   (neither changes on refusal). `test_extend.HostSpells.test_become_lays_a_lawless_kind_without_citing_later_adoptions`
   exercises a bare kind's layers without any citation, a later law adopted on the kind and the card still usable
   by another hand after reopening; the existing become test stands unchanged. `test_replay_edition` expects 14;
   current-edition references in FOUNDATION and the document headers agree, while earlier editions' history stays.
   Lean and runtime validation are the supervisor's; this lane has no toolchain.

220. **A kind's clauses name their target (lane/cx-world; astra 2026-10-12 world.md 14).** A resident's `rule`
   on kind/bell placed a row on the kind itself, while bells inherited only the kind state's `law` text; neither
   the editing spell nor `rules` named that difference. `TurnLoop.placingChange` uses `placementsOf`'s clause
   parser for both targets: absent `for:` stages the ordinary placement; `for: things` appends through
   `appendedLaw` to the kind's `law` field and stages a `Written` state edit of kind 2. `unrule` and `unwant` with
   that selector remove only the named clause of their modality from that text; without it they remove the
   placed row on the kind. `parseClauses` keeps the text's 4,096-byte and 16-clause bounds and rejects malformed
   text before any edit is staged. The kind's existing law judges the amendment, naming its clause and reading
   when a stranger asks; no separate owner gate substitutes for that judgment. `thingsText` recognizes the
   state's kind fields, and a non-kind or an unknown target is refused `badValue` in plain words.
   `hostSpell` commits the same `HostChange` for all host spells; `stagePlacements` stages and judges the same
   placing for plans, calls and world arms, including earlier edits of the target. `hostPlacingValue` reads
   `for:` before `then`, `asks` or `does`, so a nested spell's selector belongs to that spell. `ruleLine`,
   `wantLine`, `hostUsage` and `placingForms` show the optional field before the nested spell on the kind
   owner's usage and offers, and show removals with it. `rulesText` prints "for its things" and "on the kind";
   `wantsText` prints the things' clause templates and the kind's holding wants under the same targets.
   `clausesForThings` reads through `Ops.carried`, including ancestor clauses, with each line acting as the
   thing; its template has no kind-object firing history. Bell cards retain their ordinary carried-from line.
   No KIND editing method existed: the host spell uses the existing state-edit amendment judgment and journal,
   preserving the kind's governing text. Journal derivation is unchanged: `judge`, `writtenFields` and
   `parseRecordedWrites` already apply and replay the kind-2 edit, so this adds no edition change to 5.219's 14.
   Tests written first in `test_rules.KindTargets`: live propagation to every existing and a new bell, firing
   as the bell and noting its maker, both target sections, independent same-name placements and their removals,
   a stranger refused by `owner` with its reading, non-kind and unknown targets, wants and their removal,
   per-viewer usage, the full byte and clause bounds and refusal beyond each. A nested reaction's `for:` stays
   in that reaction. Reopening exercises both the amendment and removal through replay. Lean and runtime
   validation are the supervisor's; this lane has no toolchain.

221. **Grown verbs hold the same bounded share as placed clauses (lane/cx-world; astra 2026-10-12 world.md 6's
   remainder; replay edition 14).** `judge` bounded a thing's verbs only by `verbsPerObject` (16), so one stranger
   could fill them and refuse its owner's grow. Its local `checkShare` now checks placer names for verbs, rules
   and wants, each collection separately, reading the rows after every earlier placement or removal in the turn.
   A hand other than the owner (or `openerActs`) holds at most `Limits.placedPerHand` (4) verbs; all non-owner
   growers together at most `Limits.verbsByOthers` (12). The rule/want constant `placedByOthers` (24) cannot
   reserve room in a sixteen-slot table; twelve keeps the same three-quarter share and four slots for the owner.
   A full share is `capacity placedPerHand` or `verbsByOthers`, the full table `capacity verbsPerObject`. Owners
   and the opener bypass shares; the law still admits or refuses grows. `mayRemove` and `placementsOf`'s ungrow
   retain grower, owner and opener cleanup even at capacity. A gesture with `does` holds one verb slot and one
   rule slot: four gestures use four of each share, not eight of one; existing rules still consume that hand's
   rule allowance. `bounds` exposes the new constant through `natsIn%`; usage and `verbsText` print no limit.
   Tests written first in `test_verbs.Verbs`: `test_a_strangers_verbs_take_a_bounded_share_and_leave_the_owner_room`
   (fifth refused, owner grows, reopen, grower's ungrow makes room),
   `test_several_strangers_verbs_leave_a_shared_reserve_for_an_owner_who_is_not_the_opener` (twelve across three
   hands, another refused, all sixteen used, grower and owner cleanup, owner past four, reopen),
   `test_a_gesture_with_a_rule_uses_one_slot_in_each_share_and_ungrow_frees_both` (existing rules limit does,
   refusal leaves no verb, plain verbs still fit, fifth refused, cleanup frees both). Each is red before this
   change because a fifth plain verb or a thirteenth stranger verb admits. The existing sixteen-slot test
   fills the table as its owner and still asserts the seventeenth's refusal.
   `replayEntry` decodes placements with `Placement.ofJson` and calls `judge` again: a historical admission
   exceeding either new share can now refuse on direct replay, so this changes replay derivation within the
   pending edition 14 and requires the supervisor's carry check. A carry imports snapshot rows into its
   genesis without re-judging old placements (`Carry.readWorld`, `Snapshot.installGenesis`); an existing
   oversized share alone therefore does not refuse that carry, and cleanup remains available. Whether the
   live journal contains such admissions is unverified. Lean and runtime validation are the supervisor's.

222. **An offered card has a behaviour revision (lane/cx-world; astra 2026-10-12 world.md 15; pending replay edition
   14).** Placings left the state version unchanged to protect ordinary turns from strangers' rules (5.210), but
   that version alone also approved hob's reading after a verb or its consequences disappeared. `Object.behaviour`
   now counts each placing or removal, each reprogram and each amendment (`Proposal.behaviourMoves`, `judge`);
   `version` keeps its state meaning. `recordBehaviour`, `offeredCards` and `offeredRoots` join the asking card and
   each card whose forms are offered, including doors, to the same roots that carry versions. `rootsJson` includes
   `behaviour` only on such dependencies; `parseBehaviours`, `Proposal.digest`, `commit`, `finishTurn` and
   `replayEntry` preserve it. An ordinary entry's roots and request digest keep their bytes. Any placing on an
   offered card is relevant, including a rule for another verb; a placing on an unoffered card is not.
   `interpretPlan` and `heardTurn` journal those roots, and `interpretationsReply` exposes them beside the offers.
   `staleBehaviour` uses `staleRoot`, with the card and old and current revisions in its plain reason
   (`Refusal.voiced` retains it, `publicRefusal` exposes it with the root's revision for the speaker).
   `interpretVerdict` declines to fit an obsolete reply under current code; `resumeHeard` checks before casting, refusing with no write; `runPlan` carries
   valid readings' behaviour revisions into their action receipts. A host reading holds no Bend checkpoint on
   the offered cards' earlier state: after checking behaviour, `resumeHeard` starts its cast on their current
   versions; `resumes` names the original reading, including its earlier state versions. Carrying the garden's
   earlier version into every plant had refused the other 63 readings after the first plant. `resumeSegment` checks before continuing Bend's
   `interpret`; `resumeOne`'s existing one re-run re-offers on current roots. `interpretationSlot` keeps the turn's
   await numbering and binds only nonzero behaviour revisions, so a behaviour edit renews the slot without
   consuming the old answer; ordinary state moves reuse the settled answer. State versions and cells do not
   number model slots. `test_policy.PolicyObject.test_interpretations_have_their_own_capacity_apart_from_awaits`,
   the existing 64-reading test, stays unchanged;
   `ProposalForAnotherCard.test_overlapping_readings_settle_after_an_offered_cards_state_moves` covers two
   distinct pending slots whose replies both plant and replay without another model call.
   `test_a_plant_keeps_offered_revisions_and_the_next_heard_reading_still_plants` drives the town garden's make
   through hob at the commonplace: a snapshot after the first plant proves each previously offered card's
   revision unchanged while the garden's state moved; the second saved reply plants on current state, keeps
   its read behaviour revision, leaves no pending model call and replays. `behaviourMoves` is per target:
   `Kind.composing` and the made callback target the new thing; their code and placings revise only it, never
   the garden or commonplace. `placedRows`, `placedCid` and `placedIn` commit to the
   counter beside the placed rows, using the existing placed anchor; an empty table after removals is distinct
   from one never edited. `Snapshot.storeBody` and `storeOfBody` retain the counter (an absent field defaults to
   zero, as the existing optional Object fields do); `checkAnchors` verifies its CID, including after code edits.
   Tests written first in `test_interpret_object.BehaviorReadings`: pending `ungrow`, pending `unrule` of a still
   offered verb, a stranger's rule for another verb, a changed door card, an unoffered-card placing with a
   maximum-length rain and matching receipt roots, the owner's pre-placing ordinary write with unchanged root
   bytes and the pre-existing request digest, and an empty placed table reopened by replay and then by an
   accepted snapshot before another placing. A forged zero counter with recomputed snapshot CID is refused
   against the placed anchor and replay restores the revision. Added
   reprogram coverage and `ProposalForAnotherCard.test_a_bend_interpret_reoffers_after_a_rule_on_its_offered_card_is_removed`
   (old answer writes nothing, named stale receipt, a distinct new model slot, current reading admits and replays;
   placing and removal are host spells routed through the Bell fixture with its complete `receive` input,
   `text`, `post` and `fields`, since the Garden fixture has no `receive`).
   Before this change `ungrow` resumes as a method refusal, `unrule` and other relevant placings let the stale
   answer cast, and neither offers nor receipts identify a behaviour revision; the ordinary-write control is
   already green. Lean and runtime checks are the supervisor's. This changes replay's Object derivation and
   placed commitments within pending edition 14; the supervisor must run the carry check before integration.
   Adjacent carry work: a pre-revision interpretation carried unchanged has no behaviour root and must be
   discarded or re-offered by the carry before settlement. Administrative `applyRoot` program and law overrides
   bypass `judge` and its revision counter; those overrides are outside this offered-card change.

223. **A want offers work to the hand that may answer it (lane/cx-world; astra 2026-10-12 world.md 16; pending
   replay edition 14).** `want` stays the one clause modality: held until its condition stops holding, cancelled
   by `unwant`; blocked means held but not answerable by this reader, with neither status stored. `wantAsks` carries the filled text and whether filling
   succeeded, so a hole in a field cannot pass as literal text. The filled ask is read by `wantAnswerable`: its target must exist and be visible and offer its action to this
   reader. It reuses `offeredTo` (method law plus the package's pure `actions`, grown verbs judged as `act` with
   their own verb) and `hostOfferedTo`, the host-action judgment extracted from `hostUsage` and still used there.
   A missing target, unfilled hole or read-only ask (`?`, host reads, surfaces) waits. `wantRows` remains the full
   held list with derived `answerable`; `wantsText` prints each want with answerable/waiting status and its ask
   on one line. `wanting`, `wantRows`, their wire ops and `wantedData` move from Ops to TurnLoop after those
   admission functions; `renderCard` moves after them. Host usage judges the canonical target id, including
   when its printed card is `me` or a handle. No second law evaluator or callback is installed.
   `WantingPage` / Bend `World.WantPage` is `{rows, more, waiting, next}`; the sum's wanting arm, world call and
   `renderWanting` share `wantingData`. Hidden things contribute neither rows nor waiting count. `waiting` is
   the count of all visible held wants this hand cannot answer, before paging. The commonplace prints "N more
   wait on other hands" and offers eight answerable wants. `oldest` sorts `(since, object, name)` ascending,
   rotates its start by `(clock / clockDay) mod count`, wraps, and takes a bounded page. `after` and `next` are
   row offsets in that day's rotated ordering, even within a shared height; restart after the day or answerable
   set changes. Newest-first reads retain whole heights and return the last height as `next`. Morning strokes
   and the commonplace ask this same rotated page, titled "turning daily" in Bend and the paint's strokes.
   `Menu.section` gives the clipper the supplied list's length as its row allowance: the host already bounds
   the page at eight, and the waiting-count line takes no want slot. Its character room still clips ordinary
   cards; a whole card shows the count and all eight rows. The old allowance of eight dropped the ninth line
   even with whole-card room, producing a clipping marker unrelated to `WantPage.more`.
   `test_surfaces.Whole` retains the no-marker assertion and compares the complete section with the query's
   eight rows plus its waiting count; the previous count of eight unindented lines now includes the count line.
   - *Completion audit.* Bell `rain` counts only `verb == "rain"`; `second` counts those same rains, and the
     maker's subset by `where verb == "rain" and author == new.maker`. The clause's existing `LawFilter` gains
     conjunction, with parser, names, facts, read-time checks, rendering, canonical row selection and work
     accounting following every predicate. `seven` already counted that domain. `tend` reads the clock minus
     `tended`, which tend writes. RECORD's door and pending conditions count `cites` and `pending`, which door
     and admit change; its `actions` admits owner and keeper respectively. Room and porch company count
     `presence` (enter), garden five counts `things` (plant), door shut reads `marks` (knock), THING claimed
     reads `keeper` (inspirit): unchanged. No want is declared by front, weather or other shipped bodies.
     Errand's generic open want asked only `?`, which cannot settle it; that clause and its body comment are
     removed. Its open card still prints the work and condition, and its rule still marks completion and pays.
     Genesis's `kinds` read-only want stays descriptive and is counted as waiting; the seeded clapper is a
     two-step grow/use ask, whose description says so and whose condition closes on the `hang` line.
   - *Live kinds.* `deploy/genesis.py` reads `world/kinds/*.kind` through `read_kind`, `kind_text` and `KINDS`.
     `texts` includes each kind's `.law`; `refresh` compares the text genesis last gave it (`given`) and writes
     stale `.law` with its existing world-propose path, retaining owner amendments. Instances follow `under`
     at the next read/write; no relay or new deploy path. Tests install the old bell text under a refresh
     identity, make a grown gesture, refresh, and read the first-rain want on the same existing bell and reopen.
   - *Tests first.* `test_wanting.Wanting` covers owner-only law admission, status in the complete wants list,
     Bend waiting/next, missing/unoffered/unfilled/read asks, Bend actions versus grown verbs, five unanswered
     wants across consecutive days and wraparound cursor pages, and 96 wants opened at one height split at
     listPage plus an out-of-range cursor. `test_wanting.Shipped` covers RECORD owner/keeper wants, their waiting
     count on the commonplace and closure by the right spells. `test_rules.Wants` covers first and second rain
     despite another hand's grown gestures, closure by a real rain and existing-kind refresh. Before the change
     refused asks are listed, status/count/cursor are absent, every day starts at the oldest, a shared height
     exceeds the discovery page bound, and a gesture closes or corrupts the rain wants. Parser accept/readback
     cases and Law guards cover intersected counts and missing evidence. Existing `test_genesis.Commonplace`
     expectations now name the rotated eligible first row instead of the newest planted bell; `test_enchant`
     checks the exact rotation instead of monotonic heights; `test_reaction.Errand` expects its descriptive
     open card with no generic open want, retaining every settlement assertion. The three commonplace preview headings and their
     list/count change by design (candidate day-zero renders: five waiting, porch company, bell/1 rain); pins follow the changed World/Menu/commonplace closure without constants.
   These changed Bend query responses can alter a turn's derived result on replay; compound filters also
   change clause parsing/evaluation, so this is inside pending edition 14, not an edition bump. Newest-first
   existing single-filter semantics and work charges are retained. The supervisor reports a green Lean build
   and passing wanting, rules, reaction, enchant, law, tending, authority and chronicle suites. Its live bare
   commonplace shows two more answerable wants after the two shown, separately from five waiting on other
   hands; the three previews and GENESIS's embedded card follow that render. Commonplace's new query uses
   HostClient's dictionary request, as its fixture requires; HostCase and Town retain their keyword calls.
   Preview/genesis rechecks and the carry check remain with the supervisor. Python syntax and diff checks pass.
   Adjacent: `transport/hand.py` still labels its exact rotated list "oldest first"; this lane cannot edit it.
   Genesis's clapper ask still names grow after hang exists, and the optional station register condition counts
   all register lines rather than sign lines; both are deploy-owned text outside this lane's edit scope.

224. **A transition term beside a level condition (lane/cx-world; astra 2026-10-12 world.md 7's remainder;
   pending replay edition 14).** A rule's `when` remains a level condition: `Ops.reactions` calls `Law.fires`
   on each write's facts, without a previous-truth latch, so it fires on consecutive writes while true.
   `ObjectiveBendLaw.LawExpr.changedTerm` is the atom `changed(TERM)`: `parseUnary` reads it with `parseTerm`
   and refuses every request fact, including those inside count filters. The longer
   `changed(new.FIELD.COLUMN) by TERM` arm still selects the existing changed-row atom, with its original
   AST, denotation and rendering. `Law.denote` reads the new term once against the old state and once
   against the new, with the existing `read` and `Reading.same` equality also used by `==`. Count filters
   read their state terms on the same side as their count. Explicit `old` and cited roots keep their
   ordinary readings. A missing or mistyped reading, or absent old state, makes it false. `LawExpr.atRead`
   and `Law.standingRefusal` refuse it wherever there is no old state: a want's parse/placing names the
   atom and says a want reads the thing as it stands. Names and facts walk the term once in source
   order; `fields`, `reads` and `citesOf` feed both states through the existing `viewFor`. `Law.work` charges both `termWork` evaluations,
   including both row walks. No firing latch, additional delivery path or stored state is added.
   Shipped rules are unchanged: bell's `seven` and cistern's example are threshold crossings; `rang`,
   lantern's `open` and front's `full` are one-way membership additions, not arbitrary changes. Tide's
   old/new comparison is an admission law. No plain change of a term is equivalent to those conditions.
   Existing clause rendering is unchanged, so sources, pins and previews without the new form retain
   their bytes. `Placement.ofJson` carries the line; `Placed.ofJson` parses snapshot rows with the same
   parser; replay re-judges with the same `reactions`. New-form parsing and firing extend replay derivation
   inside pending edition 14, with no bump; clauses without `changed(` keep their semantics.
   Tests written first: `test_rules.Transitions` places a changed rain count and a level count together,
   checks each rain fires both and each subsequent non-rain write only the level, exact line rendering,
   last firing and delivered note counts, reopen through replay and snapshot, a want's plain refusal
   with no row placed, missing fields, nested paths and request facts in terms and filters, and the
   4,096-byte kind text with the next clause refused. They are red before because the parser recognizes
   only the `by` form; the level contrast records the existing firing decision. Parser guards cover ASTs,
   exact readback, malformed terms, old-atom preservation, want refusal and citations; denotation guards
   cover increase/decrease, equal values, text, numeric readings, missing sides, filtered counts on both
   states, arithmetic and both work charges. Existing tests and expectations are retained.
   LAW §8 states the one grammar; FOUNDATION §4, AUTHORING, AGENTS-API and CATALOGUE name both forms;
   FOUNDATION §12's completed row is removed. Python syntax and diff checks pass. Lean compilation,
   guards and runtime/replay/snapshot tests remain with the supervisor; this lane has no toolchain.
   Adjacent: retained counts can plateau at RECORD's 128-line cap, so a changed rain count is a value
   transition, not evidence of every future rain event (LAW §8).

225. **The paint's propositions are host clauses (lane/cx-world; astra 2026-10-12 world.md 17; no journal
   derivation or replay edition change).** `Enchant.Strokes.facts` selects numbered `Fact {id, kind, subject,
   value, clause}` rows from the strokes already assembled and hashed: maker/owner/keeper/location, last
   tending, nonordinal counts with their meaning, recorded marks, present hands, hands in the day/span,
   holding wants and host-derived events. A `rung` mark alone offers "it has rung"; other marks offer only
   their recorded names. Counts measure retained rows or the stated day, never lifetime history or a rule's
   future result. A want offers its holding name, not its reading as a current predicate. Heads, `about`,
   seeds and heard lines remain authored words, not selected facts.
   `Strokes.json` and `Strokes.text` offer these rows, including canonical clauses, so the existing cache
   key commits to their content. `Enchant.part` parses a factual line consisting solely of `[[id,...]]`,
   requires each positive decimal id in this paint's facts, and substitutes host clauses with semicolons
   and a closing stop. The model chooses selection and order, never factual wording, predicates or inference.
   `verify` returns the expanded text; `world-render-check` returns it as `text` when verified. The existing
   `Fate.painted` and disk cache keep the verified source, expand it in `fateAnswer` and reverify on disk load.
   No new render or fallback path, journal field, snapshot field or stored semantic fact is added.
   Existing token checks remain on model-authored lines, with reference ids removed from prose. The new
   `imagery` clause permits quotation lines only with a said/wrote attribution frame, preserving whole-line
   and author checks, or unquoted fragments starting with an explicit simile marker. It blocks listed
   copulas, auxiliaries, perfect/state verbs and subject pronouns, and stroke field/mark/verb/unit/want names,
   identifiers, handles and meaningful head/about/seed/heard-line words. This is a syntax/vocabulary guard;
   it does not establish that every possible metaphor or predicate in every tongue is harmless. The factual
   guarantee is the host-selected clauses. Source and expanded text both satisfy the existing length bound;
   length retries once in every tongue, and every non-model refusal retries once in a supported non-English
   tongue through the same `retried` flag; a second refusal uses the existing exact fallback. Host clauses remain in the
   host catalogue language; imagery and quotation frames use the requested tongue, with existing language
   checks. A reference-only paint still requires a supported tongue.
   `world/lib/Paint.obend` is the one updated contract. The one catalogue string in
   `transport/static/pages.html` keeps the scene's exact card open beneath every paint, so status and actions
   stay visible independently on `/play` and `/o`; the additional transport exception below is rendering
   only, and no lexicon logic is changed.
   Tests written first: `test_enchant.Facts` rejects an unmarked "The bell has rung", offers and canonically
   renders a real rung mark, refuses nonexistent/zero/negative/malformed/inline ids, refuses a historical
   "without a clapper" as present prose before and after a hang gesture but accepts it as credited said
   words, preserves fact order with imagery, covers exactly 400 characters and short references whose
   expansion exceeds the limit, and reads a cached structured paint after reopening without changing the
   exact card or journal height. `test_previews` requires the painted bell's current silent status and rain
   action in the open exact card. Before implementation the raw ringing claim is accepted, numbered facts
   and canonical check text are absent, the seed is accepted as a present description, and the card folds.
   Existing fixtures are recut by the contract: lamp/about and coinage/name use said-word frames; bell/day
   counts, placed wants, anthology keeper and morning wants use fact ids; the bell's uncited seventh-rain
   sentence now refuses `imagery` because a threshold does not establish a future result. Existing Lean
   guards for formerly admitted uncited propositions now expect `imagery`; accepted structured count,
   mark, keeper, event and want guards replace their valid factual forms. Token-rejection expectations
   remain unchanged. HTTP/posting/hand fixtures use simile fragments, with the HTTP card-open expectation
   changed; telling fixtures cite taking, visitors and hands with the same exact quotations and cache/frame
   assertions; tongue fixtures retain each wrong-count/attribution/want/negation rejection and pair the
   accepted quote/simile with a true count reference. `test_town_principal` cites the town's keeper fact,
   retaining the private owner's handle rejection. No test is removed or loosened.
   OVERHAUL §4, VOICE, FOUNDATION and AUTHORING state this contract; FOUNDATION §12 removes finding 17
   from its open row. Paints remain derived reads/cached artifacts; edition 14 stays pending and unchanged.
   The supervisor's Lean build is green; `test_previews`, `test_genesis`, `test_chronicle` and
   `test_hypermedia` pass. Three reported reds were fixtures: morning want facts now match the complete
   reader-eligible `(object, name)` rows rather than assuming anthology; the historical seed's source post
   now belongs to GLM, so the said-word quote credits its actual author rather than the synthetic `x`;
   posting cites a real telling event and checks the canonical paint above the complete exact offered reply
   and admission line. The hand's length-only fallback fixture now starts with a simile and requires the
   length clause, preserving its retry case under the imagery guard. The other touched telling, tongue,
   hand, HTTP, town-principal and preview assertions were reviewed against expansion, attribution, frames,
   clause order, caches and the open exact card. The supervisor subsequently reports `test_enchant` and
   every other touched module green except the posting telling lead: its pre-arrival reference id selected
   a different event in the model's later facts. The posting model now selects its event from the actual
   request and asserts that one canonical clause, imagery, one blank line and the complete exact offered
   reply. New assertions require the host's full `telling.exact` below that reply, including uncited events;
   `transport/bridge.py::with_telling` appends those host lines as "What it draws on" after the complete
   current reply, with no new world predicate, clipping or fallback. Before/away
   maximum-paint cases cover intact long histories through the existing threading and literal historical
   `[[999]]` text without interpreting it; receipt contents and the prefix's `told` count stay unchanged.
   Ember explicitly authorized this rendering-only exception on 2026-10-12, confined to `with_telling`
   and nothing else in `transport/bridge.py`; no other transport file was touched for this correction.
   Foundation's lane/tongues2 (`060ff21b`, merged by `d3a918b3`) is reconciled into this citation contract,
   not retained as a prose-painting alternative. All fifteen worked examples (thing, before arrival, while
   away in ja/zh/es/ru/ar) now offer numbered `{kind, subject, value, clause}` facts, arrange `[[ids]]`,
   quote an attributed line in that tongue's said-word frame and add a guarded simile. Example ids are local;
   tests bind their declared structured facts to the matching real strokes and check the exact expansion,
   not merely that some numbered clause verifies. AR/JA/ES/EN fixtures likewise bind their rain fact from
   the actual model request and expect the host's canonical count; the script, quotation, per-tongue cache,
   wrong-count/want/negation, native-frame, retry-count and final-second-refusal assertions remain.
   The native `Frame:` prompt line, doubled non-English response budget and Spanish plural stem remain.
   A true uncited "dos visitantes" now passes numbers then refuses imagery; "tres visitantes" still
   refuses numbers, while the cited two-visitor fact verifies. Singular/plural stem guards also cover
   visitante/visitantes, clase/clases and carácter/caracteres. The retry notes name `facts` and `imagery`
   failures and their details, teach local `[[id,...]]` selection or attributed quotations/similes, and ask
   for imagery and quotation frames in the speaker's tongue without translating host clauses or history.
   No retry remedy asks for unmarked factual prose or an unquoted historical name. New tests written before
   the prompt/note changes require the fact-id and imagery-specific remedies and a successful second paint;
   those remedies were absent from the textually merged helper. No check or retry limit is weakened.
   The Paint source pin is updated with the existing DAG-CBOR/CID encoder after reproducing foundation's
   imported pin from its exact source; the compiled packet digest remains the imported observation until
   the supervisor recompiles it. No host compilation or runtime suite ran here. The old live-model 89%
   result measured prose painting; the citation examples and retry need their own real-model measurement.
   This merge changes no journal derivation; replay edition 14 remains unchanged.
   Python syntax and diff checks pass; new runtime assertions and real-model validation remain with the
   supervisor. Least certain: the rejection rate/cost of the stricter prompt. Adjacent: retained marks
   and counts still have the lifecycle issue in world.md 9; this paint exposes recorded facts and does not
   turn them into durable semantic evidence. The lexical imagery guard cannot prove semantic harmlessness.
   Transport's `pages.place` docstring and scene catalogue comment still describe folding the card; their
   cleanup belongs to the transport lane under this lane's single catalogue-string exception.

226. **Ended grants release live capacity; makers and grantors hold bounded shares (lane/cx-world;
   astra 2026-10-12 world.md 11; pending replay edition 14).** `record` runs `compactGrants` after
   the entry's clock and revocations: `until` inclusive, a revocation or first clock past it ends
   the grant at that entry's height. `World.grants` holds only unrevoked, unexpired grants;
   zero-use limited grants still stand until revoked or expired. The newest 256 endings, ordered
   by height then id, are `GrantTombstone {id, grantor, holder, to, object, method, ended, endedAt}`;
   no reading, fixed argument or uses. The ring releases live grant slots, never journal bytes.
   `grantRead`, shared by `world-grants {grant?}` and `world-inspect {grant}`, reads live terms,
   the ring, then the journal. Journal lookup uses the same compaction function, not a mutation
   on read. `revoked` is a read projection. Paged listing resolves only the selected page's ids.
   Snapshot/store-installing genesis hold the ring, and a carry normalizes older full grants
   from their journal endings. Ring eviction before a carry leaves the id only in the retained
   old journal; this binary does not traverse an archived earlier edition on a grant read.
   A listing's `height`/`hash` names the making, or the carrying genesis when that is the available
   origin. The full creation receipt retains its reading and terms.
   - *Allocation.* `grantsPerPrincipal = 64`, `objectsPerPrincipal = 128`: 1/64 and about 1/78
     of their global tables, opener exempt. Grant admission subtracts the commit's revocations
     and excludes already-expired incoming grants. `world-open {maxGrants}` only lowers the
     process's bound; it never changes the journal or snapshot. `Object.maker` is the allocation
     principal at creation, not a mutable Bend state field: the turn principal even through a
     kind, or a direct opener-named owner. `objectCapacity` checks the final objects installed
     by direct creation and by `judge`, including restorations, as transient `capacity` with the
     bound's name. Retirement releases the maker's share, not the global object count. `retire`
     remains the opener's power and `--leave` the carry's. A maker may use ordinary amendment
     to add the same guarded `retired` shape with themselves as the amendment principal; the
     metarule still applies. A false clause merely named `retired` releases nothing. Any ordinary
     removal, including the opener's `unretire`, is checked against the maker's share.
     Maker provenance joins the existing anchors (sixth height), snapshots and carried objects;
     it survives layers and reprogramming. Genesis readers use `genesisRow`, the actual
     `outcome.state.objects` store path, including old rows without `maker`. Old three/five-height
     anchors are filled from the journal's creation or genesis before checking; no height zero
     is read and no maker check is skipped based on an unrelated grant field. Snapshot installation
     normalizes old full grants, shared by open and carry; `verify` compares normalized store and
     indexes against replay. Older carries without a creation derive the maker from the genesis's
     state owner or opener, then seal that attribution. An imported
     over-share allocation may shrink or stand but not grow.
   - *Tests* (initial lifecycle and share cases written first). `test_grants.GrantLifecycle`: cap lowered to one, refusal while
     live, revoke/expiry freeing it, inclusive expiry, expiry at creation, cited id/ending,
     replay and snapshot, the 65th resident grant and opener exemption, dropped lent reading,
     257 endings with oldest lookup from the journal, bounded unknown ids, private tombstone
     reads and lowering-only. `test_grants.Attenuation` checks fixed arguments and uses disappear
     from the compact record while remaining in its making. `test_make.ObjectShares`:
     129th resident object refused through both routes, maker attribution through a kind,
     opener exemption, opener retirement freeing only the resident share, resident amendment
     retirement, a misleading retired clause, reopen and over-share restoration refusal. `test_budgets.AllocationBudgets` reads the named host constants.
     `test_carry` keeps endings, normalizes an older full-grant snapshot, retains the maker's
     share, opens and verifies a pre-metadata edition-14 snapshot, carries it twice, carries the
     same old layout at edition 13, and resolves a carried live grant after ring eviction.
     The new share/privacy fixtures explicitly name their opener; the original fixtures and
     existing carry/fork assertions remain unchanged. Before the change ended grants occupied capacity, compacted inspections and the knob
     did not exist, and principal shares were unchecked. Existing assertions are not weakened;
     the grant fixtures are shared without repeating their original test methods.
   - *Remaining lifecycle.* FOUNDATION §2 specifies segmented journals (host/block-store) and
     the 30-clock-day inactive-object archive (host/objects), with the capacity each releases
     and crash/reopen/receipt completion checks in §12. Neither is implemented. Snapshots still
     reclaim no journal or object capacity, carries still preserve it, and retired names still
     occupy the global object table. Old ancestry lookup for evicted grants and ownerless legacy
     allocations is named separately in §12. This changes replay's grant/object derivation and
     maker anchors inside pending edition 14; the number is unchanged. Python syntax and diff
     checks only here. The supervisor's first build elaborated; budgets, snapshot, reaction,
     journal bounds and durability passed. Its carry/fork failures exposed the wrong genesis
     maker path and the new fixtures' unnamed opener and invalid resident power invocation,
     corrected above. The supervisor must rebuild, re-run those suites and the carry check on
     the real backup. Least certain: compatibility with the real backup's oldest carried rows.
227. **A thing acting as itself is named by its id and places within its owner's share (lane/inhabitants; no edition
   change).** The station's inhabitants (docs/GENESIS.md "The all-night station") act as themselves (`@<id>`, 5.209)
   from rules they place on the tide and their place. `Enchant.handleIn`: a line, mark or presence whose principal
   is a thing acting as itself and holds no handle is named by its id, as `shownName` names it (it read "someone",
   and a telling's "came in" had no subject); Bend's `Card.handle` shows such a principal by its id too. The
   placement share (`placedPerHand`, `placedByOthers`, 5.210) counts a rule or want a thing places as itself against
   the hand that owns the thing, so making things that act of themselves mints no hand; the opener's own are the
   owner's, as the weather's are (`checkShare`, 5.221's, for rules, wants and verbs alike). So does what such a thing
   makes count for its owner's `objectsPerPrincipal` (5.226; `objectCapacity`): the regular's coin is the opener's. No journal before this has a thing placing as itself, so replay is unchanged. Tests:
   `test_inhabitants` (a hand's third regular is left inactive by `placedPerHand`; strokes in the live run).
228. **True paints pass the citation contract (lane/paintfix; 5.225's regression; no journal derivation or replay
   edition change).** After 5.225 the inhabitants lane saw every paint it asked for refused. Measured: bell/1, the
   porch's telling, the station's telling and station/regular on a fresh genesis `--with-gas-station`,
   claude-haiku-5-5, 2 reps x 6 tongues: English 0/8, 25 of 48 in all, 16 on the first try. The refused paints named the causes. The contract never said English is the tongue
   when the strokes name none (the painter refused, or wrote its reasoning as lines), and English had no retry. The
   verifier refused true paints: frame words it did not know (と書き込んだ, 「…」とthe townが言った, 由…写下, сказала,
   قالت, قاله, كما قال, two quotations joined by and), the town named in the paint's tongue (町, el pueblo), a
   frame-only line counted against its tongue by its quotation mark and "the town", a simile borrowing its voice
   ("frost" on the regular) blocked because a line repeats the word, كأن folding to كان, 像 not a simile, a thing's own
   line on its own card, and a quotation framed by the verb that wrote it (`station/regular emoted “…”`). The strokes handed the
   painter a coiner's DID to credit, which a paint could then show; and the station's telling ran past 500 once its
   clauses were expanded, which the retry was not told.
   `Enchant`: every non-model refusal retries once, in every tongue (`submitOp`). `frameWords` per tongue; a quoted
   line's own verb (`inflections`) frames it; `Tongue.roles` gains the town's word per tongue, credited to
   `townName` by `attribution`; a Japanese or Chinese run made up whole of frame words and names is a frame. The
   simile marker is cut before the vocabulary check; source words (head, about, seed, lines) its voice holds are free,
   names (kind, field, mark, verb, unit, want) stay blocked and are now met by the tongue's stem (المطر, дождём,
   lluvias). `tongueFault` reads no quotation mark or person's name, and a line of ids, handles and quotations alone is
   in no wrong tongue. `aliases` gives a coiner without a handle (`unnamed`: a DID, or `coinerOf`'s "the author of
   at://…") no name, and `Strokes.text` tells the painter to credit them as its coiner, never by an id or address. The strokes list the words imagery may not use (`Strokes.notImagery`: names, and the source words its
   voice does not hold), the citation budget
   (`Strokes.budget`: the facts' average clause, cite at most half the length's worth), and residents' lines in the
   paint's quotation marks (`Strokes.quote`). An expanded overrun is `"N expanded"`, and its retry is told each cited
   clause's and quotation's cost. `Paint.obend`: English the default, the paint alone, the frame spelled out, a simile
   a noun phrase, one pair of quotation marks, each id's clause counted, and English worked examples (bound to real
   strokes by test_tongues and test_telling).
   Finding 17's protection is unchanged: propositions are host clauses; uncited prose is a guarded simile or a framed
   quotation; history stays quoted. A source word translated (escarcha for a line's frost) is not caught: the guard
   compares the strokes' own words. Live after, on the merged tree (10 reps per card and tongue, the first try and
   its retry): 219 of 240 painted, 137 on the first try; bell 53/60, porch 58/60, station 55/60, regular 53/60; en
   34/40, ja 39, zh 38, es 35, ru 35, ar 38; 22 of 24 cells at 8/10 or more, bell es and regular ru 7/10, each
   remaining refusal a paint that breaks the contract (rain in a Spanish simile, the town's line given to the
   regular, an uncredited or translated quotation). 343 calls, 2.13M tokens in, 23K out: $0.22, under a tenth of a
   cent a paint with its retry. Tests: `test_enchant.LivePaints` holds each refused-but-true live paint (verified now) and finding 17's
   false paints beside the live ones that stay refused (an unmarked "has rung", the seed's "no clapper" as present,
   rain and ringing in imagery in any tongue, a deed in a frame, the town's line given to the regular, a nested
   frame, a DID credit); the English retry and the expanded-length note; the anthology and telling refusals retry
   once before showing exact.

## 6. Gotchas

- **Replay edition (a rule).** `Limits.replayEdition` (Store.lean) is the edition of what replay
  derives; `Journal.sealEntry` writes it as `replay` on every journal's first entry (a fork's and a carry's genesis
  too), `world-status` answers it, and `Snapshot.openJournal` refuses a journal of another edition before
  replaying anything: "journal replay edition 1; this host is 2; a world from another host's edition does not
  reopen here: carry it (`delvetalk-obend carry --from J --out NEW`, ...)" (a journal without the field is edition
  1). The check stands: a world replayed under rules it was not judged by would lie. The policy is FOUNDATION §2's:
  an additive derived field is compared when present and derived when absent, with no bump; a bump is a breaking
  change, which ships with `deploy/carry-check.sh` green on the newest town backup (the deploy then carries,
  5.159) or does not merge; a world is never begun again for one. 2 is host12 (evictions and changes owed as
  facts, lineage, reservations, attempts); 3 is host14 (root, ignore and shadowing, moderation, the opener's
  amendments, later settings, `unposted`; 5.126); 4 is host16 (roots read by their cells, the per-cell bound and
  ledger; 5.136); 5 is host17 (a layered package's shape is its stack's, 5.138; the relational atoms judged and
  their citations roots, 5.139); 6 is host18 (a send refused transiently stays pending, 5.150); 7 is host19
  (`context.sender`, 5.155); 8 is kernel16 (`cardRefused`, 5.157); 9 is host22 (rules and wants placed, fired and
  posed, `request.verb`, 5.160), with snapshot `v4`; 10 is kernel18 (a state named by its cells,
  KERNEL-HANDOFF §15; a carry reads an earlier world by `Ops.Naming.ofEdition`) with host29's rows and read policy
  anchored and identities carried (5.175, snapshot `v5`, whose `previousEdition` `v4` a carry checks by its three
  anchors alone); 11 is host30 (an inherited rule's firing names its holder, a carried genesis's touch
  barriers, law work metered, 5.179), never deployed; 12 is host31 (a carried genesis continues the old heights, 5.182); 13 is lane/authority (tenure, queued rules and wants reviewed independently of the write, 5.209–5.214); 14 is lane/cx-world (component bodies replaced at their journaled positions, 5.219; grown verbs admitted within a stranger's share, 5.221; behaviour revisions on offered-card roots and placed commitments, 5.222; answerable want queries and compound count filters, 5.223; transition terms beside level conditions, 5.224; live-grant endings and immutable maker allocations with anchors, 5.226). Test: `tests/test_replay_edition.py`.
- **The snapshot body is the carry's contract.** `carry` reads an older binary's head snapshot through
  `Carry.readKeys` and `install`: a lane that changes what those read (`storeJson`, or an index key in
  `readKeys`) keeps the reader of the edition before it in the same commit, deleted when the next lands.

- `conformsUnder` needs the packet's bounds (`Object.bounds`, `Compiled.bounds`); bare `conforms` is only for closed non-recursive types.
- `canonicalTy` (Ops): two state types are equal when their canonical forms agree (variables renamed in order of first use, at most 4096 steps, else "type too deep to compare"). Reprogram and extend depend on it.
- Wire shapes: `world/lib/World.obend`'s `protocol world` is the contract (Plan.obend keeps the shared records: `Reference`, `Edit`, `Slot`, `Receipt`). `write`'s edits are a record with one variant per state field. `respond` picks the first payload that conforms to the call site's result type; a sum lacking the label gives "response type cannot carry <label>".
- Seeds are laid over `initial()` (`mergeSeed`): a record of some fields, `{}` for `initial()`; a field the state lacks is `typeMismatch`. A seed that does not set a text `owner` gets the named `owner`, else the creating principal (`withOwner`). `create`'s `package` is a module name in the creator's sealed chain, or source starting `edition`; `law` is used only if it starts `law `.
- Hand-built Contexts in tests must carry caller, intent and height or the method does not type.
- Lean keywords: `meta`, `from`, `seal`. Structure-instance continuation lines must be indented past the first field.
- A suspended identity has a `suspended` entry; `retained` ignores it so the final commit can reuse the identity.
- Settling runs inside `durable`, after the triggering op, and appends to the same write.
- `Handle.flush` is not durable; `sync.c` does `fflush` + `fsync` (or `F_FULLFSYNC`). One sync per `durable` call. The build needs `lakefile.lean` for `extern_lib`.
- `python3 -W error` turns leaked subprocess warnings into failures; close hosts in `tearDown`. `test_await` is slow because every `world-create` compiles.
- Never run an unfiltered package suite on a loop.

## 7. Open

**First, host31's remainder.** Replay edition 12 is merged and not deployed: anything that changes what replay derives
rides it if it lands before the deploy, which carries the live town's edition 10 to 12 (one carry) and ships
`carry-check.sh` green on the newest backup (green, breaking, on delvetalk-20261012T121739Z at 5.182). Each with its
failing input as a test first, merging foundation before each commit:
1. **The live morning's cause** (5.183 makes the hand say why; the cause is not yet read). The v9 deploy check's
   morning (day 20738, 12:05:49Z, `painted: false`) and a 117-token paint call share their second in the backup's
   `model-spend.jsonl`: the paint came back and was refused, or landed after the hand's last look. The verdict is on the
   workhorse alone, a refused render's `render-*.json` (`clause`, `detail`) under `DELVETALK_COMPILE_CACHE`; read it,
   or the next `hand morning`'s `fellBack`, and fix that clause's cause.
2. **The deploy's carry reads v8's makings** (5.185). The live v9 genesis keeps no `made`, so the 10 to 12 carry reads
   every making from the journal v9 cites, `/towns/v8/state/town.journal` (all data directories are mounted at
   `/towns` in the ops container). Check the carry's `made` rows after it (kind/errand's is the opener's
   `genesis-kind-errand`) and that the refresh lines are `refreshed`/`current`, not "its making is in no journal read";
   carry-check on hbox cannot show it (v8 is the backup delvetalk-20261012T115945Z, not at that path).
   **Read, and it blocks the deploy** (lane/deploy12, 2026-10-12, DEPLOY "It carries"). The makings were read: 32
   `refreshed` and 24 `current`, none left. Then the motion's `weather` placing was `suspended`, so the carry exited 1
   and v9 went back up. The refresh rewrote `kind/weather`'s `.form` text to `over:`, while the carried kind's place
   form, shaped once from v8's form, still takes `garden`. `genesis.carried_fields` reads the text, so it kept
   `over: porch` and the spell misfit. Fixed by 5.199 (lane/refresh-fix) and deployed: v9 carried into v10 at 446,
   every refresh row `refreshed`/`current`, kind/errand's `made` the opener's `genesis-kind-errand` (DEPLOY "It
   carries"). The two things the live checks found are fixed and deployed by the v10-to-v11 carry of 550c0478
   (lane/deploy13): (a) bell/1's "untended since entry 27" (v8's height) by tending read by the clock, 5.200 (bell/1's
   `tended` is a clock minute, its card names no entry); (b) `hand morning`'s "Answered so far:" by the morning's wants
   read as still wanted, 5.201 (the live morning card lists only what still wants a hand).
3. **`shownSpell` scans for `did:` tokens** (5.181): a `fired` row keeps the filled spell, not its holes, so a DID the
   speaker typed is shown by handle too. Keep the rule's template and its fills on the row (edition 12 is undeployed:
   it can ride it) and show the fills by handle; delete the scan.
4. Closed without code: the simplify hand-back's (6) (the front's REPL is `world-repl` and matches no prose; the
   kernel's `not issued by this process` and `unknown library pin` are read by tests alone); a seed post with its wants
   lines (476 characters, `01-porch.txt`) is far inside a post's bound once stamped. The duplicate entry numbers are
   gone (lane/author-build's 173 to 177 are 194 to 198).

The queue after host27 (5.164 to 5.172) and host28 (5.173, 5.174), in order. The overhaul (docs/OVERHAUL.md section 5) is the order of work. The owner's
standing order binds every item: "maturify and take forward everything that we've started and bring it to its full
sophistication and make sure the code is all 'fungused together' (no seams or welds where rich semantic braiding is
called for); let's not leave behind 'old things', no scar and growth tissue." So each replacement deletes what it
replaces in the same commit, and this file describes only what is. A merge touching the host runs
`deploy/carry-check.sh` on hbox first (5.159).

0. **For the objects lane, from host27.** (a) A seal's want can now read `request.laws` and `request.refusedBy` (5.165); a
   law refusal journals the wants it opens. (b) Bend arm tests from a body: `wanting` is covered
   (`test_wanting`); `rule`, `grow`, `act`, `chronicle` from a `made` are not.
1. **Left from host27.** `test_http`'s four page-markup assertions (Claim, Play: home's words, the quota page's
   stamp markup, the paint frame) fail on foundation's web redesign: the transport lane's. The question answer
   (5.171) offers the exact card: whether the front or the bridge shows the paint above it is the transport's
   (renders are per session). "hob says ask is not needed" has no answer to read: decide whether hob gains one.
   The fold of a post's misfits (5.166) runs after its fitting spells: a misfit that hob reads into a spell on a
   card an earlier spell wrote reads it as written (5.167).
   From the pair merge, still open: the ring `seven` fires on a carried garden/bell/2 writes nothing (objects lane);
   a default-law object carried from before edition 9 keeps the old default (no `or request.kind == rule`).
2. **Edition and carry.** Edition 9 is not deployed; 5.161 and the pair change what it derives, so they need no
   bump if they merge before any edition-9 world is. If one is deployed first, the pair is edition 10 and ships
   `carry-check.sh` green on the newest v7 backup and the playtest-3 copy, as OVERHAUL plans.
3. **5.160's remainder.** `offeredTo`'s diff for the speaker in `revealed` ("it now takes `ring`", and "it now
   takes `water`" after a grow); judging cost (`ruleTicks`: neither text laws nor rules are metered; bounded by
   `rulesPerObject` × rows, measured on a bell of 768 rains and 32 rules before the playtest); `carried` parses
   each text per commit (keep parsed clauses on the `Object`); a want citing another thing flips only when its own thing is written (a write to the cited thing should
   re-judge the wants citing it: an index of citers by object, judged in `reactions`); `maxLawClauses` 16 counts
   all three modalities.
4. **Verbs' remainder.** `retire` of a verb is `ungrow` (the host spell `retire` is the card power); a
   carried world's things grow once the carry moves them to a pin with `act` (5.159 *Moves*); the card's
   `Grown here:` line reads `Object.verbs` only through a `world.verbs` arm (Bend has no read of it; decide with
   the objects lane); `grow` in a policy's `confirmFor`.
5. **The carry's remainder (host21).**
   - The first carry of the live town: ship `backup.sh`, `verify.sh` and `carry-check.sh` to the workhorse's
     `/opt/delvetalk/deploy/` and hbox's `~/delvetalk-backups/`, so tarballs hold head snapshots; until one does,
     carry-check takes `--old-image delvetalk-host:9790175f9dc0`. The deploy is DEPLOY "A new binary", *It carries*.
   - What a carried world does not yet keep: `world-receipt`/`world-entry` of a pre-carry hash answer unknown (the old
     chain's block store is edition-independent: read it as the world before, by the `carriedFrom.world` path or a
     copy beside the new journal; heights now continue, 5.182, so an old receipt's height is already this world's).
   - A carried genesis's size: the store's compiled types and method tables (1 MB of playtest 3's 1.4 MB) are
     derivable from the carried sources; carry them as blocks, or derive them at install, measured on the v7 town.
   - `slugTargets` scans every entry (and now every carried hash) per `world-resolve`: index slugs (item 8 below).
   - Wake: playtest 3's opener wake is carried retired by the fourth playtest's `--leave`; step 4 deletes Wake, and a
     carry of a world holding Wake objects leaves each by name.
6. **The fungus review's host rows** (docs/review/fungus-2026-10-11.md §1, §3), one commit each, each deleting the
   old path: T29 the REPL's two prose refusals (`unknown library pin`, `not issued by this process`)
   as classes and `http.py` matching the class; T32 `world-status.suspendedBytes {median}`; H2's remainder (`respond` with
   one payload per method: the `refused` and `inspected` ladders); H4 `reprogram {mode: "extend"}`; H5/H6 dispatch on `(method,
   argument)` and the `plan` wire names (with the kernel); H7/H8 root acts and moderation powers as one table,
   settings through `settingsChange`; H10 `sealLibrary` reading `Ops.arrivals`; H11 `serve.c` saying root and the
   frame bound checked once; H12 `Store.lean`'s `Limits` referencing `Bounds` (`maxTurnTicks` = `ticksMax`,
   `plainDepth` = `plainJsonDepth`, the 1400s); H13 `compressedSize`; H14 the duplicates; H15 one list codec
   (`DataWire`); H16 reads of older journals; H18 a host `fit {form, fields}` that `Kind.makeUnder` calls.
7. **FEDERATION's remainder (5.140):** cross-world `call` and `send` are built (5.173), and the foreign reads with
   them; the REPL, `check` and `cite` of a scratch are built (5.174), and the owner's `delvetalk world expire /
   scratch:` (section 2). Left: `world-history` across worlds; the hand's SCRATCHES page; a `Returned` that carries
   the target's receipt (World.obend's, so every pin moves: the objects lane's); `world-repl` of several modules.
8. **The stored path's remainder (5.136): done by lane/kernel18** (KERNEL-HANDOFF §15 "The state as cells"; replay
   edition 10): a write is checked, bounded, charged and named per changed cell, `storeOf` is gone (`Held` holds
   the object's cells), and a lookup reads its key or its gap (roots' `gaps [{field, after?, before?}]`).
9. **The block store's remainder (5.137)** and **the law atoms' remainder (5.139)**, as host17 left them: index
   sources, grants and slugs; CIDs as bytes; one record encoding; `serve --snapshot-every`; held worlds never closed;
   `world-inspect`'s `cites` per clause.
10. Smaller, standing:
   - `hand.speak` (transport) casts one spell through `spell-parse`; a hand post of several spells answers
     `{status: "spells"}` without a top `receipt`, which it reports as an error. Teach it the turns, or keep it one.
   - `tests/test_pull_backups.Retention` depends on the time of day (names built from `now - 12h` and `now - 6h`
     straddle midnight UTC): transport's.
   - Root: a `before`/`after` past `maxEntryBytes` by CID in `blocks`; a retry of a root act is a new `root:<n>`;
     `set pin` stores the pin alone; `as` runs the method as named; `root-edit` does not rewrite CIDs inside
     checkpoints and states. `openerActs`' interpret-quota exemption ignores `resident`: decide.
   - The objects lane, after 5.153: fold `Card.Reply` into `Heard` and delete `Record.misfitted`, the room's
     `Super.misfitted` arm, the commonplace's `isNobody(state.policy)` misfit refusal; credit a delivered write to
     `context.sender` (the weather's rain, 5.155).
   - `readerActions` compiles `actions` per read; `methodAdmits` judges on the state as it stands; a `call` or
     `write` to an object created in the same turn is `unknownObject`.
   - The paint, after 5.228 (lane/paintfix's followups, queued, owner the next Enchant lane unless noted):
     (a) a telling's exact first line names a coiner without a handle by address ("made by the town, after a post by
     the author of at://did:plc:…", `tellingOf`, as the chronicle does since cx-fix-host): a reader is shown an at://
     URI where a name would stand; decide with the transport lane whether the page links the post instead.
     (b) Count clauses read a line's verb as a unit: "1 came", "1 settled", and the strokes' "cames: 1" (`plural`,
     `lineQuantities`); check: the regular's facts say what a reader would. (c) The painter copies the contract's
     example handles (kimik3, glm) as credits on cards they never wrote (Spanish regular, live): give the examples
     handles no fixture uses and rebind test_tongues/test_telling; check: no live credit to an example handle.
     (d) A resident's line is quoted whole or not at all (codex host 15), and the station's 200-character emote keeps
     tellings near their 500 and tempts excerpts, which are refused: Ember to decide whether a marked excerpt may
     stand. (e) A translated source word passes imagery (escarcha for a line's frost): the guard compares the
     strokes' own words; decide whether the tongue's lexicon should carry them.
