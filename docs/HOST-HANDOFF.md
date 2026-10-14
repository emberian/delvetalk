# Host handoff

The reference for changing `spec/Delvetalk/Host/`: what each module holds, every op, the journal's shape, the limits,
and each subsystem as it works now. The queue is §7.

## Summary

The host is one Lean process holding a world of durable objects. Every state change is a journal entry naming the one
before it (CID of canonical DAG-CBOR); memory is derived from the journal by `record`, and replay re-judges admitted
entries. A reply exists only after its bytes are durable.

- An activity yields `World.Message`s; `answer` dispatches on the method name against `worldMethods`. Write is
  self-only; cross-object change is `call`/`send`, judged by the callee's own law; `reprogram` and `amend` of another
  object are judged by the target's law.
- Only declared methods run from outside. A direct `receive` is read as a spell by the host. Words that reached a card
  and run none of its spells, and a misfit spell, are hob's to read for that card with its table; hob's answer runs as
  the speaker's turn.
- An object's pin is the CID of its sealed source closure, never a compiler output.
- Laws: a text law (`law NAME "reading": EXPR`) judges every change by `request.kind` (`write` 0, `reprogram` 1, `amend`
  2, `proposed` 3, `rule` 4); an optional Bend `law(old, new, request)` runs after it for kinds 0 and 3.
- Refusals are receipts with a class from `refusalClasses`; every `reason` is written by `Refusal.voiced`. Transient
  classes (`transientClasses`: `staleRoot`, `budget`, `evaluation`, `capacity`, `quota`, `quiet`) do not bind: a retry
  with the same identity runs again.
- Replay edition 20, snapshot `delvetalk.snapshot.v5` (§6).
- Run: `make check` (parallel runner `tests/run.py`), `make smoke` (`test_turn_world test_chain`). Narrow:
  `DELVETALK_OBEND=<binary> python3 -W ignore -m tests.run test_x`. `tests/host.py` opens test journals with
  `sync: "none"`. Wall-clock bounds (`test_snapshot` reopen under 5 s, `test_relation` under 3 s, `test_hypermedia`'s
  long poll) are fsync- and load-bound and can miss on a loaded box.

## 1. Module map

`spec/Delvetalk/Host/`, pure unless noted. Imports: `Blocks` (only `Canonical`) ← `Store` ← `Journal`; `Spell`, `Tongue`
← Store; `Law` ← Store, Spell; `Screen`, `DiskCache` ← Journal; `Ops` ← Store, Journal, Law, Slug, Spell, DiskCache,
Screen; `Snapshot`, `Surfaces` ← Ops; `TurnLoop` ← Ops, Spell, Surfaces, Tongue; `Root`, `Enchant` ← TurnLoop;
`Moderation` ← Enchant; `RootEdit` ← Snapshot; `Session` ← Ops, TurnLoop, Snapshot, Root, Enchant, Moderation;
`PackageSession` ← Session, Spell; `Serve` ← PackageSession; `Carry` ← Snapshot, RootEdit, Serve; `spec/PackageMain.lean`
(the JSON-lines driver and the `delvetalk-obend` subcommands) ← PackageSession, Serve, RootEdit, Carry.

- `Blocks.lean`: `Entries` (the chain in memory: every CID, each record's span, the CID index, the step's unwritten
  entries, `base` the heights before this journal's first entry; `get?` reads and CID-checks one record through
  `readAt`, a `pread` behind `implemented_by`, pure because a written record never changes), `Link` (one chain line,
  `Link.ofLine`), `recordBytes`.
- `Store.lean`: `Limits`, `Law`, `Compiled`, `Ledger`, `ReadPolicy`, `Program`, `Object`, `World`, `identityKey`
  (compressed `[principal, intent]`). Pure data.
- `Journal.lean`: `bodyHash` (CID of the body's canonical bytes), `sealEntry`, `verify height previous entry`.
- `Law.lean`: `Facts`, `Reading`, `denote`, `admits`, `refusedBy`, `refusal`, `work`, `fill`/`filled`, the law-text
  parser (`parseLawText`, `renderLaw`); `#guard` tests at the bottom. Grammar: `spec/bend/Compiler/ObjectiveBendLaw.lean`.
- `Spell.lean`: the spell grammar (`parse`, `bare`, `fit`, `bind`, `segments`, `plan`, `render`/`renderChecked`, the
  `Clause`s), `#guard`s.
- `Ops.lean`: edits, `Proposal`, `judge`, `commit`, `record`, `push`, creation (`compileObject`, `makeObject`,
  `buildObject`), `replayEntry`, `replay`, `advance`, `reactions`, `carried`, `citesOf`, reads, `Refusal.voiced`.
- `DiskCache.lean`: the on-disk compile and render caches' reads.
- `TurnLoop.lean`: `M` (`ExceptT Abort (StateM TurnState)`), `runMethod`, `drive`, `answer`, `finishTurn`, `runTurn`,
  `runTurnWith`, `runSpells`, `runPlan`, `resumeOne`, `resumeHeard`, `settle`, `deliver`, `reprogramOp`, `amendOp`,
  `renderCard`, `wanting`, `wantRows`, `receipt`, `history`, `reachOp`, `derivedOp`, `cardOp`.
- `Snapshot.lean` (IO: the chain, the block store, snapshot files): `storeJson`, `indexJson`, `installIndex`,
  `openJournal`, `reopen`, `replayAll`, `resume`, `checkAnchors`, `writeJournal`, `ancestryOf`, the store-installing
  geneses (`genesisEntry`, `forkGenesis`, `wholeSuspension`, `carriedKeys`, `installGenesis`).
- `Root.lean`: `rootKinds`, `rootFieldsOf`, `rootOp`, `worldSettingsOp`.
- `Screen.lean` (pure) and `Moderation.lean` (ops): the automatic moderation.
- `Surfaces.lean`: the town's reads (`book`, `chronicle`, `map`, `source`, `makings`).
- `Enchant.lean`: strokes, the paint check, the render cache and the render ops. `Tongue.lean`: languages a paint and
  hob answer in.
- `Session.lean`: `Open {world, path, handle, store, report, sync, snapshotAt, every, bound, renders}`, `openWorld`,
  `durableIO`/`durable`, `settledStep`, `appendJournal`, `stepWorld` (every op), `syncHandle` (extern,
  `spec/native/sync.c`).
- `RootEdit.lean`: `delvetalk-obend root-edit` and `migrate` (namespace `Migrate`). `Carry.lean`: `delvetalk-obend carry`.
- `spec/Delvetalk/Serve.lean` and `spec/native/serve.c`: the directory of worlds and its two sockets.
  `PackageSession.lean`: the per-process session above Session (`world-repl`, the stateless kernel ops).

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

All world ops are cases of `Session.stepWorldCore`. A request error (`Except.error`) journals nothing; a refusal is a
receipt. `stepWorld` redacts what moderation hid from every reply but the opener's (`Screen.redactJson`).

- **Open and status.** `world-open {path, library?, principal?, libraryLaw?, sync?, verify?, snapshotEvery?,
  maxJournalBytes?, maxObjects?, maxGrants?, clock?, postQuota?, interpretQuota?, opener?, name?}`, `world-status
  {principal?}`, `world-snapshot`.
- **Turns.** `world-create`, `world-turn {…, replyTo?, reach?, profile?, if?}`, `world-try` (the same, nothing written),
  `world-propose`, `world-deliver {limit}`, `world-pending`, `world-reprogram {mode: replace | extend}`, `world-amend`,
  `world-advance {height}`, `world-revoke`, `world-interpretations`, `world-interpretation {id, reply}`.
- **Reads.** `world-view`, `world-derived {principal, object, view}`, `world-card {principal, object, whole?}`,
  `world-inspect`, `world-check`, `world-receipt`, `world-history`, `world-offers`, `world-objects`, `world-state-cid`,
  `world-resolve`, `world-entry`, `world-entries`, `world-object`, `world-source`, `world-sources`, `world-grants`,
  `world-publications`, `world-reach`, `world-wanting`, `world-rules`, `world-wants`, `world-chronicle`,
  `world-surface`.
- **Paint** (never journaled): `world-strokes`, `world-render-check`, `world-render {principal, object, version?}`,
  `world-renders`, `world-render-submit {key, reply}`.
- **Registry, arrival, posting.** `world-principal`, `world-arrive`, `world-post-reserve`, `world-post-release`,
  `world-posted`.
- **Root and moderation.** `world-root {principal, reason, act}`, `world-settings`, `world-library`, `world-fork`,
  `world-dump`, `world-screen`, `world-screen-verdicts`, `world-screen-review`, `world-screened`, `world-redact`.
- **Serve's** (§5.7 "Serve"): `world-scratch {principal, name, from?}`, `world-cite {principal, scratch, receipt,
  identity?}`, `world-repl`, `serve-status`; `world-relay` and `world-cross` are serve's own, refused on both sockets.
  `world-view`/`world-card`/`world-inspect` of `<world>:<object>` read another served world.
- **Stateless:** `bounds`, `library-load {path}`, `spell-parse {text, form?, addressee?}`, `check-package`, `compile`.
  `bounds` answers `{kernel, host, refusalClasses, transientClasses}`: every `Nat` of `Delvetalk.Bounds` (and
  `Generics.maxInstances`) and of `Limits` by name (`natsIn%`), so the front, its module checks and the tests read the
  bounds rather than restate them (`tests/host.py` `bounds()`, `transport/host.py` `history_limit`).

Rules:
- `turn` is host-assigned on propose, amend and reprogram; a client-sent `turn` is a request error.
- Every journaling op runs through `durable`: step, `settleAll` (resume what the step released, run pending deliveries
  oldest first, each followed by a resume pass, up to `deliveriesPerSettle`), then append all new entries with one
  sync. The reply carries `resumed` and `delivered`, shown as the op's `principal` may see them (`settledFor`: the
  turn's own principal gets the reply whole but for `offers`; anyone else `status`, the receipt's `projectEntry`,
  `public`/`rerunOf`). `world-deliver` runs what a capped pass left. `world-open` never settles; an open that journals
  nothing answers `{}`.
- `world-open` seals `library` (a directory) on first open and journals it; a later open whose bytes differ is refused
  by name. `verify: true` replays everything and answers `snapshot {resumed, refused [{height, reason}]}`.
- `clock` (the one principal that may `world-advance`, `world-posted` and `world-principal`), `postQuota` (default 16)
  and `interpretQuota` (default 48) are journaled in a `settings` entry on first naming; a later open with other values
  is refused. `opener` goes in the same entry; the opener alone may `world-create {…, owner}`. `maxObjects`,
  `maxGrants` and `maxJournalBytes` lower the process's bound only, never journaled.
- Reads take a principal through `readerOf`: 1..128 bytes, or `anonymous` / "" (public objects only). Object ids at
  creation are 1..`maxObjectIdBytes` of `Limits.nameAlphabet` (`validObjectId`); `world`, `me`, `objects`, `try`,
  `receipt`, `guide` are taken; replay accepts any id a journal holds.
- Optional request fields go through `optText`/`optNat`, which refuse a present but malformed value by name.
- Paging: `world-entries`, `world-history`, `world-sources`, `world-grants`, `world-publications` page by height
  (`pageByHeight`): `after`/`before`/`reverse` by whole heights, `cursor: "<height>.<n>"` continuing after (or with
  `reverse` before) exactly that item; `limit` 1..`maxHistoryLimit`; a page with `more` answers its last item's
  `cursor`. An unknown or denied object answers before the limit is read.
- `world-turn`/`world-try {if: [{object, version}]}` (at most `maxRoots`): a root that moved, or that the principal
  may not view, answers `{status: refused, class: moved, moved: [{object, was, now}], line}`, nothing journaled. A
  guard that does not read fails closed.

## 3. Journal

A journal at `J` is two files: `J`, the chain, one line per entry `{at, bytes, hash, height, previous}`, and `J.blocks`,
the block store, where each entry's record (its canonical DAG-CBOR without `hash`, whose CID is the `hash`) lies at
`at`. `tests/wire.py` is an independent Python encoder; `transport/journal.py` (`links`, `records`, `entries`, `tail`,
`size`, `copy`) the Python reader; `tests/wire.py` `write_journal` writes what a test forges.

An entry's common fields: `height`, `previous`, `hash`, `identity {principal, intent}`, `roots [{object, version,
scalar?, fields?, rows?, spans?, gaps?, behaviour?}]`, `turn`, `request` (digest), `outcome {tag, …}`. Genesis
`previous` is 64 zeros (`Limits.genesis`); entry 1 carries `replay` (the edition). A fork's genesis chains to the
forked entry's CID at height 1; a carry's genesis sits at the old head's height + 1 (`Snapshot.firstHeight`).

`world.receipts` maps `identityKey` to the entry index (first wins, except that a suspension or a transient refusal is
replaced by the identity's next entry). A state is named once, by the entry that wrote it: `writes[].cid`, or a created
seed; `world-state-cid` answers it to a reader who may view the object.

Sources are carried once per journal: compile inputs name each module `{name, cid}`; the first entry needing a source
carries it in top-level `sources [{cid, source}]` (checked against its CID on replay). Compiled packages are cached by
input digest (`world.builds`, `buildKey`, `maxBuilds`), so creation and replay compile each distinct package once.

Optional top-level fields (all inside the hash): `absent [id]`, `turnRequest`, `ticksUsed`, `ledger {depth, work,
storage}`, `result`, `sends [{id, to, method, argument, ledger, world?, reach?}]`, `delivery {id, from}`, `resumes`
(hash of the suspension it continues), `offers [{to, text}]`, `replyTo`, `rerun`, `ended`, `publishes`, `blocks`,
`cites [{world, object, version, stateCid, height, head}]`, `plan {acts, of}`, `root {by, reason}`.

Outcomes:

- `created`: `{object, pin, sourcesSha256, compile, seed, read, chain, supervisor?, owner?, law?, lawText, madeFrom?,
  lines?, placed}`; `roots []`, `turn 0`. Replay recompiles, requires the pin to match the source closure, the seed to
  conform and the amendment dry run to pass at the entry's height.
- `admitted`: `{writes [{object, version, edits, callers, kinds, cid?, evicted?}], reprograms?, amendments?, creates?,
  grants?, revokes?, spent?, placements?, placed?, fired?, unfired?, wanted?, unwanted?, verbs?}`. Per change, only
  when non-empty: `methods`, `vias`, `arguments`. Replay rebuilds the `Proposal`, checks `request == p.digest`, re-runs
  `judge` and `reactions`, and requires every recorded derivation to equal the replayed one.
- `refused`: `{class, clause?, object?, reason?, reading?, expected?, root?, hint?, next?, act?}`; a `lawRefused` entry
  also carries the `wanted`/`unwanted` its refusal flips. Classes (`refusalClasses`): staleRoot, typeMismatch,
  capacity, absentItem, lawRefused, unknownObject, duplicateIdentity (never journaled), evaluation, budget,
  budgetExhausted, programRefused, requiredAbsence, keyTaken, duplicateKey, badSpell, quota, noMethod, quiet,
  cardRefused. Replay checks only that the class is known. A refused entry drops `offers` and `publishes`.
- `suspended`: `{slot {principal, intent}, deadline, activity {…}}` plus `request`, `ledger`, `ticksUsed`; a call
  across worlds adds `crossing {world, to, method, argument, sender, ledger}`; a host reading has no checkpoint
  (`hostResumed`). Replay requires the checkpoint digest to match its tokens and registers it in `world.suspended`.
- `relayed {world, receipt, height}` with one `sends` row, and `crossed {world, answer {tag, class?, clause?, reason?},
  receipt? {hash, height}}` with `result?` and, for a send, `delivery`: the two halves of a call or send across.
- `principal {did, handle}` (identity `{clock, "principal:<did>:<height>"}`); `advanced {from, to, wanted?,
  unwanted?}` (replay requires `from == w.clock && to > from`); `settings`; `library {pin, previous, modules, law?}`;
  `posted`, `unposted`, `reserved`, `released`, `attempted`; `interpreted`; `cited {world, receipt, entry}`; `named
  {name}`; `root`; `moderated`; `forked`; `carried`.

Cross-entry invariants (`checkDelivery`, `checkSends`, `checkResumes`, `checkEnded`):
- A `sends` id equals `deliveryId principal intent ordinal` (CID of `[principal, intent, ordinal]`).
- An entry with `delivery` consumes exactly the pending delivery it names, under the sender's principal, `intent ==
  id`. A `budgetExhausted` refusal's reason names a ledger field that is zero (`exhaustedReason`).
- An entry with `resumes` names a waiting suspension of the same identity.
- `record` derives `pending`, `suspended`, `clock`, `touched`, `touches`, `changes`, `anchors`, `receipts`, `outbox`,
  `handles`, `posts`, `blocks`, `modules`, `ruleLog`, `wanting`, `wantReaders`, `wantCites`, `refusedBy`, `days`,
  `hourCounts`, `screened`, `turnsStarted` and the grant ring.

Durability is fsync, not a full barrier: an entry may be lost on power loss inside the OS write-back window. An append
writes every record to the block store and syncs it, then every link to the chain and syncs that, so a crash between
leaves records no link names. A chain whose last line is torn is refused by name (`journal broken at height N:
unterminated final line`, `Snapshot.chainOf`); the host never cuts its own file. Recovery is a verified copy:
`deploy/backup.sh` cuts the torn line in its mirror and replays it, `deploy/restore.sh` installs the tarball (DEPLOY
"Durability and backups", "A torn tail"). `world-open {sync: "none" | "fsync" | "full"}` picks the mode per process
(default `fsync`; `full` = F_FULLFSYNC; anything else is refused); never journaled; `world-status` reports `sync`.
`openWorld` takes an exclusive flock and refuses "journal is open in another process".

The journal bound: `durable` measures the chain and the store (`journalBytes`, exactly) against `Open.bound`
(`Limits.maxJournalBytes`; `maxJournalEntries` binds first for small entries). An append that would come within
`journalHeadroom` of the bound is not written: a turn is refused `capacity` ("the host's maxJournalBytes is full; try
later."), journaled into the headroom; an op with no identity, or a refusal that would itself pass the bound, is a
request error "journal is full: …". Open refuses a journal past its bound. A line-format journal is refused on open;
`delvetalk-obend migrate --journal OLD --out NEW` is the one reader of it. Tests: `test_journal_bound`,
`test_block_store`.

## 4. Turn state and limits

`TurnState` lives in `M`; `Abort` is `request | evaluation | budget | suspend | card | named`. `finishTurn`: `.suspend`
writes a `suspended` entry; `.evaluation` refuses `evaluation`; `.card` commits `cardRefused` with nothing of the turn;
`.named` is a refusal given whole (a grant's clause); a `violation` refuses `requiredAbsence` (the violating creator
journaled as `root`, the taken id as `object`); `.ok` calls `commit`. A request error journals nothing, except for a
delivered or resumed turn, which is refused.

- `roots`: `recordRoot` (a whole read), `recordCells` (the cells a frame read), `recordBehaviour` (an offered card's
  behaviour revision); validated at commit by `judge`, at resume by `resumeSegment` and `resumeHeard`.
- `writes`: `addWrite` (the running object only; another target is answered `refused {clause: notSelf}`),
  `ensureWrite` (reprogram/amend).
- Every frame reads its object `asWritten`: the committed state with the edits the turn has staged on it applied in
  order (as committed when none, or when they do not apply, which the commit refuses). The frame's version, its cell
  roots and `view`/`viewField`/`viewAt` stay at the committed version.
- `sends`: ids derive from the ordinal at commit (`sendsJson`). A send's ledger is `{depth-1, work - used, storage -
  bytes added}` (saturating); `childLedger` lowers storage by each created object's whole state as well. Work is
  charged after the fact: a turn may overshoot `work` by one turn.
- `creates`: built in-turn by `buildCreated` (compile, evaluate `initial()`, overlay the partial seed with `mergeSeed`,
  `makeObject`), installed by `commit`. A `create` with `requireAbsent.object == ""` gets `<creator>/<package
  lowercased>/<n>` (`mintId`); one ending in `/` takes the first free `<prefix><n>` (`mintUnder`: not an object, not
  created this turn, not held by a suspension's absence). What a turn creates is an object of the turn (`madeIn`):
  later frames and acts read, write, extend and place on it, judged over the state it is made with.
- `await` accepts `until` (absolute clock) as well as `patience` (never 0); Plan `awaitUntil`. Await inside a `call` is
  refused; only the top activity checkpoints. An object holds one self-wait at a time (`refused waiting`); a self-wait
  the clock ends goes on under the object's own `chain`, a whole budget each period (`selfWait`).
- In-process yields hold the machine state (`Turn.Suspension`, resumed with `Turn.resumeSuspended`); only `await*` and
  `interpret` build a checkpoint (`Held.kept`), resumed from the journal with `Turn.resumeEntry`.
- `world-turn {profile: true}` returns `profile [{kind, steps, ticks}]` (not journaled). With `DELVETALK_TIMING=1` the
  binary writes one stderr line per op after the reply (`Serve.timingLine`: op, ms, object, method, principal, resumed,
  delivered); hostd's children inherit it.

Limits (`Store.lean`, `Limits`; kernel bounds are `Delvetalk.Bounds`, KERNEL-HANDOFF). A full count refuses the turn
`capacity`, reason the limit's name; `bounds` answers every one by name.

| group | names and values |
| --- | --- |
| ids, text | `maxObjectIdBytes` 128, `maxPrincipalBytes` 128, `maxIntentBytes` 256, `maxMethodBytes` 128, `maxHandleBytes` 256, `maxTitleBytes` 256, `maxUriBytes` 512, `maxReasonBytes` 256, `maxRefusalBytes` 4096, `askLine` 160 |
| per turn | `maxRoots` 64, `maxWrites` 64, `maxEditsPerWrite` 256, `maxPlansPerTurn` 1024, `maxCallDepth` 8, `sendsPerTurn` 32, `createsPerTurn` 8, `awaitsPerTurn` 8, `checksPerTurn` 8, `grantsPerTurn` 8, `publishesPerTurn` 4, `crossingsPerTurn` 1, `planActs` 8, `spellsPerReply` 3, `listPage` 64 |
| data | `dataDepth` 8192, `plainDepth` 64, `Bounds.maxCellBytes` 262144 (the scalar part and each relation row), `maxRelationRows` 4096 (a relation's `limit` 0), `maxObjects` 10000, `objectsPerPrincipal` 128 |
| journal | `maxEntryBytes` 1 MiB (a record), `maxJournalEntries` 1,000,000, `maxJournalBytes` 4 GiB, `journalHeadroom` 1 MiB, `maxHistoryLimit` 100, `maxCheckpointBytes` 512 KiB, `snapshotEvery` 1000, `maxSnapshotBytes` 256 MiB |
| ledger | `maxDepth` 100, `chainWork` 10,000,000, `chainStorage` 1 MiB (creation may lower, never raise) |
| time | `maxTurnTicks` 1,000,000, `maxPatience` 1,000,000, `interpretationPatience` 64, `crossingPatience` 60, `clockDay` 1440, `interpretBackoffMax` 60 |
| worlds | `scratchPerPrincipal` 2, `scratchJournalBytes` 16 MiB, `scratchObjects` 1,000, `scratchMinutes` 360 |
| delivery | `deliveriesPerCall` 16, `deliveriesPerSettle` 64, `deliveryAttempts` 4, `maxPending` 4096, `pendingActivitiesPerObject` 8, `pendingInterpretationsPerObject` 64, `maxSuspended` 4096, `maxResumesPerCall` 1024 |
| grants | `maxGrants` 4096, `grantsPerPrincipal` 64, `maxGrantTombstones` 256 |
| rules, wants, verbs | `rulesPerObject` 32, `wantsPerObject` 32, `verbsPerObject` 16, `placedPerHand` 4, `placedPerHandOnTownThing` 8, `placedByOthers` 24, `placedOnTownThing` 512, `verbsByOthers` 12, `verbNameMax` 32, `verbReadingMax` 200, `rulesPerCommit` 8, `ruleDepth` 4, `wantReviewed` 64, `clauseTicks` (`Bounds.lawTicks / 8`), `lawDepth` 4, `chronicleLines` 48 |
| programs, laws | `maxPackageBytes` (= `Bounds.maxPackageBytes` 131072), `maxLawBytes` 4096, `maxLawClauses` 16 (all three modalities), `maxPreparedPrograms` 16, `maxCompiledPackets` 256, `maxBuilds` 1024, `maxReaders` 256, `maxLibraryModules` 256, `maxLibraryBytes` 786432, `maxSourceBytes` 64 |
| interpret | `interpretAttempts` 8, `modelQuota` 2000 a clock day, `maxUtteranceBytes` 8192, `maxOffersBytes` 65536, `maxReplyBytes` 262144, `mentionsAddressed` 4 |
| cards, forms, views | `cardShownChars` 1400 (`formTextMax`), `maxCardRoom` 65536, `cardWanting` 8, `formNaturalMax` 1000000000, `formSourceMax` (= `maxPackageBytes`), `maxViewBytes` 262144, `maxViewNodes` 4096 |

## 5. Subsystems

### 5.1 Authority and laws

- **Facts.** `Facts {subject, caller, height, turn, pin, kind, method, verb, evicted, clock, object, reads, wants,
  standing, relations}`. `caller` is the object whose method wrote ("" for the turn's own method and client proposals;
  for a delivered turn, the sending object); `method` the method whose run made the change ("" for ops); `verb` the
  `act` verb, `grow` for a verb's placing, `rule`/`want` for theirs; `reads` the states of the objects the law cites;
  `standing {laws, refusedBy}` for the written thing and each it cites.
- **Grammar** (`ObjectiveBendLaw.lean`, denoted in `Law.lean`): `and`, `or`, `not`, `implies`; `==`, `!=`, `<`, `>`,
  `<=`; `request.subject|caller|height|turn|pin|kind|method|verb|clock|object|laws|refusedBy`; `old.F` (the field
  before the write; at creation its kind's empty value) and `new.F`; a sum left of `<=` whose first part is a reference
  (`old.last + old.gap <= request.clock`) and the three-slot `REF <= REF + REF`; integer and text constants;
  `monotone(F)`, `writeOnce(F)` (exactly one change away from the empty value: 0, false, "", the empty list, a record
  of empty values), `appendOnly(F)`, `unchanged(F)`, `x in new.F`; for relations `insertOnly(F)`, `count(new.F) <= N`,
  `count(new.F) <= count(old.F) + N`, `x in new.F.COL`, `count(SIDE.F where COL == TERM [and …])` as a reference,
  `changed(new.F.COL) by TERM` (every row the write changed carries the term), `TERM in "O".F.COL`, `under "O"` (every
  clause of O's `law` field at depth − 1; depth 0, an absent object, a non-text or unparsable law is false), `"O" wants
  N`, and the transition term `changed(TERM)` (the term read against old and new; false when either side is missing;
  refused wherever there is no old state, so never in a want). A field the state lacks is read from its `fields` rows
  (`{name, value}`, what its kind's make took; digits as a number). A field missing from the old state fails closed.
- **Judging.** `judge` applies every write first and judges each law, Bend law, amendment and placing against the
  candidate world it leaves, per distinct (caller, kind) of an object's changes. Default law `owner: request.kind == 0
  or request.kind == rule or request.subject == "<creator>"` (`defaultLaw`). Metarule: an amendment must be admitted by
  the existing law for its proposer (clause `amendable`). The opener's amendment (kind 2) is admitted whatever the law
  (`openerAmends`, gated by `openerActs`: the opener, not a resident request); `world-inspect`'s `laws` lead with
  `{name: opener, clause, reading, host: true}`. An `under` atom holds of an amendment by the citing state's text
  `owner` (`ownerAmends`), so a thing's owner can always amend it out from under its kind.
- **Kind 3, `proposed`.** A state write no method of the object made: a `world-propose`'s writes and a reprogram's
  migration result (judged as kind 3 beside kind 1, by the text law). A law that admits `request.kind == 0` admits only
  the object's own method writes; `request.kind == 0 implies X` does not constrain proposals. `Law.kindNames` is
  `world-inspect`'s `requestKinds`.
- **Citations.** `Ops.citesOf` is the one closure of what names cite (`"O".F`, `under "O"`, `"O" wants N`), `lawDepth`
  deep; `citing` sets `reads`, `wants` and `standing`. `withLawReads` adds the law's citations to the roots at the
  version read, within `maxRoots` (past it `capacity`); a cited object the subject may not view refuses `lawRefused
  lawReads`. `citationRefusal` refuses at creation and amendment an `under` of a missing object, of an unparsable law,
  or a cycle within `lawDepth`. `world-inspect` answers `cites`.
- **Standing.** `request.laws` counts the thing's law clauses, its own and each its `under` citations hold, each
  (holder, clause) once; `request.refusedBy` counts journaled `lawRefused` entries naming it (`World.refusedBy`). A
  want reading `laws` moves only when its own thing is written.
- **Law work.** `Law.work`: a step per atom and a row per row a clause walks, each side, through `under`; `judge`
  meters the law's clauses per judgment against `Bounds.lawTicks` (`budget`, reason `law ticks`, transient). Row
  membership is one pass over a set of canonical bytes.
- **Readings.** `parseLawTextReadings` reads `law NAME "reading": EXPR` (malformed: `law syntax`). `Refusal.reading`
  is the refusing clause's reading wherever the law came from (package, creation, amendment, an `under` citation
  followed to its innermost clause by `Law.refusal`, a Bend verdict, the host's own clauses `fixed`, `lawReads`,
  `noGrant`, `grantSpent`, `notGrantor`, `denied`, `law`, `amendable`, `under`); `voiced` writes `reason: "refused
  <clause>: <reading>"`. `Object.readings` keeps the package's readings for clauses still the package's.
- **Bend law.** For an artifact with `law.present`, after the text admits, `judge` runs `law(old, new, request)` once
  per distinct kind-0 or kind-3 change with `request = {context, method, argument, kind, pin, reads}`
  (`inputOrigin.kind = "law"`; `context.sender` included); `reads` are the ids `lawReads()` returns, supplied only when
  their read policy permits the subject. `admitted`, `refused {clause}` or `refused {clause, reading}`; exhaustion of
  the law or of `lawReads()` is `budget`, anything else fails closed as `lawRefused law`/`lawReads`. Reprograms and
  amendments are the text's alone. `warmLaws` compiles `law`/`lawReads` before `judge`.
- **Context** (`contextData`, also the Bend law's): `{world, object, principal, handle, caller, sender, intent, height,
  clock, inputOrigin {kind, object, command, program, immediatelyPrevious, post}}`. `sender` is the object whose send
  the turn delivers ("" for a principal's turn; a rule firing's is the rule's object), the same in every frame;
  `inputOrigin.post` the post a frame was asked from (a called frame inherits its caller's; a card render's and a Bend
  law's are ""). Each Context is fitted to the receiving code's declared record (`fitRecord`), so a field added later
  never breaks an older object.
- **Commutative edits.** `judge` accepts a moved root `(id, seen)` when every change of `id` is a kind-0 or kind-3 write
  whose every edit commutes (`keep`, `add`, `append`, `insert`), or an `upsert`/`retract` of a row whose key no admitted
  write since touched (`keysChangedSince`; a `set` or list edit of the relation touches every key; an eviction touches
  its key), or the cells read are current (`cellsCurrent`) and the turn's edits clear (`editsAdmit`), or, on a resumed
  turn's own object, an edit of a field later writes left alone (`movedRootAdmits`). One rule (`rootAdmits`) for
  `judge` and `resumeOne`. Any other moved root is `staleRoot`; `resumeOne` then re-runs the direct turn once from its
  journaled request (`rerun: true`, reply `rerunOf`). Deliveries are not re-run. A placing moves no state version and
  no field.
- **Cross-object dry run.** A `reprogram`/`extend`/`amend` Plan naming another object records it as a root and
  dry-runs the change through `judge` (`dryChange`); a refusal is answered `refused {clause, reading}` and nothing is
  staged. `world.judge {edits}` answers `judged {admitted, clause}` without committing, its proposal's reads recorded
  as roots.
- **Typed arguments.** An argument from outside is read against the method's input before conformance
  (`wordsAsCases`, `inputWords`): a text where a closed sum of empty payloads stands is the case of that name, in
  fields, records, lists and payloads; a word naming no case refuses `typeMismatch` ("colour is one of: …",
  `expected.cases`). The input check is exact: a method without an input takes only `{}`; a field it does not declare,
  lacks or holds of another type is named (`misfitReason`). A misfit refuses `typeMismatch` (binding), journaling
  `expected {method, type, form?}` (`form` the card's declared bounds) for the turn's own principal; in a `call` the
  Plan is answered `refused {clause: typeMismatch, reading}`. A direct turn is then judged against the card's declared
  form (`declaredMisfit`: lengths, ranges, choices). Any `receive` whose argument does not fit is filled as the spell
  path fills it (`heardArgument`). Deliveries, `call` and `send` arguments are typed values and are not read as words.
- **Fixed fields.** The artifact lists an entry's `fixed` State fields (`Object.fixed`); the seed and `initial()` set
  them. A write that changes one is `lawRefused fixed`; a migration that moves one, or a reprogram whose new code does
  not fix every field fixed now, is `programRefused fixed`; `set` naming one is `badSpell fixed`. `world-inspect`
  answers `fixed`.
- **`insertOnly`** exempts exactly the rows retention evicted (`Facts.evicted`); the admitted write journals
  `evicted: [{field, key}]`, replay compares them.
- **Tenure.** A thing's law is its own text: its root package's base law then `law kind: under "<kind>"` (Bend
  `Kind.lawOf`); a kind's text is only its own clauses. Things that act as themselves are named `@<id>` (§5.3
  "Rules, wants and verbs").
- **Quiet.** `Ops.quietOf` is the one reading: `judge` refuses every entry of a quieted principal (propose, reprogram,
  amend, placing, resumption, delivery) and `runOne` before the turn runs, class `quiet` (transient, `next` the clock).
- Tests: `test_law` (`Atoms`, `Cited`, `Proposed`, `Readings`, `LawAtCreation`, `Alive`), `test_tenure`, `test_relation`
  (`Moved`, `Cells`, `LawWork`), `test_commute`, `test_sum_words`, `test_sender`, `test_input_post`, `Law.lean`'s guards.

### 5.2 Grants

- Plans `grant {to, object, method, until}` -> `granted {id}`, `grantWith {…, fixed: Data, uses: Nat}` (uses ≥ 1),
  `revoke {id}`, `callVia`/`sendVia` (only these name a grant). Only a direct turn's top frame may grant (`notDirect`);
  the grantor is the turn's principal, the holder the running object. `to` must be the frame's subject or the calling
  object at use. A grant serves the world it was made in (`noGrant` across worlds).
- A grant stands (`grantStands`) while not revoked, the clock ≤ `until` (inclusive), and object and method match.
  Under a grant the callee runs with subject = grantor, caller = the calling object; `judge` re-checks it (`lawRefused
  noGrant`). A `sendVia` delivery runs as the grantor and is refused `noGrant` (consumed) if the grant fell in between.
- `grantFor` checks the grant, the grantee, a use left (`grantSpent`), and `attenuate`s: a fixed record's fields join
  the caller's record (a field given with other bytes is `grantConflict`; the fixed part is held to `maxCellBytes`). A
  use is spent only when the call runs or the send is staged; the entry records `spent [{id, uses}]`.
  `TurnLoop.granted` is the gate a principal's own turn enters a lent grant by.
- Revocation: the holder object, the grantor in an undelegated frame (`notGrantor` otherwise), or the opener (any
  grant). `world-revoke {principal, identity, grant}` is the grantor's write outside any object. Entries carry `grants
  [{id, grantor, holder, to, object, method, until, reading?}]` and `revokes [id]`. Ids are CIDs of `["grant",
  principal, intent, ordinal]`.
- Lifecycle: `record` runs `compactGrants` after the entry's clock and revocations; `World.grants` holds only live
  grants (a zero-use limited grant stands until revoked or expired). The newest 256 endings are `GrantTombstone {id,
  grantor, holder, to, object, method, ended, endedAt}`. `grantRead` (`world-grants {grant?}`, `world-inspect {grant}`)
  reads live terms, the ring, then the journal. A principal holds at most `grantsPerPrincipal` live grants (opener
  exempt); admission subtracts the commit's revocations.
- `lend` (host spell, §5.3 "Spells") is the speaker's grant with a `reading`.
- Tests: `test_grants` (`Attenuation`, `LentDirect`, `GrantLifecycle`).

### 5.3 Reflection, library, extension, supervisors, handlers

- **Library.** `Library {pin, modules}` sealed by `sealLibrary` (dependency order, then name). Objects' compile inputs
  carry `"library": pin` and only their own modules; `resolveInputs` prepends the library closure on every compile
  (`libraryClosure`, a worklist). A reprogram compiles against the world's current library. A library change is a
  `library` entry judged by the world law (default `opener: request.subject == "<opening principal>"`, kind 1); replay
  re-seals and re-judges. Stateless `check-package`/`compile` take `library: <pin>`, resolved among the world's
  libraries then those sealed with `library-load` (at most 4 kept).
- **Declared methods.** A State-first definition is public only when the entry module declares it: a form's `action`,
  a name `methods()` returns, a `views()` entry, or a conventional name (`conventionalMethods`: receive, render,
  forms, lenses, set, publishPage, page, relations, methods, law, lawReads, views, initial).
  What a module declares is read from the artifact's `declares` (derived definitions included). A `methods()` entry
  written `~name` is public but offered to nobody (`unoffered: true`). The table marks other rows `helper: true` and
  conventional-only rows `protocol: true`. A direct turn or delivery naming a method the object does not offer is
  `noMethod` ("<id> has no method <m>; reply delvetalk <id> ? for its spells."); a `call`/`run`/`send`/`sendVia` naming
  one is answered `refused {clause: noMethod}` (an object may call its own helpers); `ended` to a supervisor may name a
  helper. A layer keeps what the code below declared and may add.
- **Offered to a reader.** `offeredTo w id o reader` is the one filter for usage, `world-inspect`'s `forms`/`offered`
  and the `inspect` Plan: the law admits the method on the state as it stands (`methodAdmits`, a kind-0 change by the
  reader through that method), and the card's own `actions(state, context) -> List<String>`, when it has one, lists
  it; a grown verb is judged by the law alone (as `act` with the verb). `receive` always stands; lenses show only when
  `set` is offered. `world-inspect`'s `methods` rows carry `admits: true | {clause, reading?}`. A spell for another
  action is still fitted and the commit judges it.
- **Forms.** A form is `{card, action, fields}` for each declared method whose input is a record of `String` (text
  1..`formTextMax`; `0..N` makes it optional), `Nat` (0..`formNaturalMax`) or a closed sum of empty payloads; a
  `Form.Kind.source` field is text up to `formSourceMax`, filled by the reply's first ```obend fence (`withFence`).
  When the entry module declares `forms()` its kinds override the type's defaults field by field (`declaredForms`).
  Views are never spells. `world-inspect` answers `templates {action: spell}` (`spellTemplate`, its blanks
  `spellHint`'s), which the front copies.
- **Inspect.** `world-inspect` answers pin, `pinSlug`, law text, `laws [{name, clause, reading?, keyword}]` (every
  modality), `bendLaw`, `cites`, `methods`, `forms`, `offered`, `templates`, `views`, `fixed`, `requestKinds`,
  `stateBytes` (canonical DAG-CBOR length), `scalarBytes`, `madeFrom`, `lineage`, and the entry module's source only
  when asked `source: true`, under the reader's `ReadPolicy` (`denied` otherwise). The `inspect` Plan takes `source:
  Bool` and answers `inspected {pin, law, source, methods, laws, offered}`; it records the object as a root.
- **Check.** `world-check {principal, modules | source, entry, limits?}` compiles over the world's library, journals
  nothing. `world.check {package, layers}` checks a package (a closure module or source) with each layer laid over it
  as `extend` lays one; `world.checkObject {object, layers}` checks what a readable object runs (its whole closure)
  with `layers` over it. Both answer `checked {diagnostics, reaches}` (`"<module>:<line>: <stage>: <message>"` lines,
  a `hint:` line where the kernel has one; `reaches`: whether a `receive` exists) and count against `checksPerTurn`.
  The kernel names every missing library import of a module at once.
- **Extend.** `world-reprogram {mode: "extend"}` and Plan `extend` add the source as module `Layer<n>`; the host writes
  `layer over ./<module below>.obend` as its first line (`layerLine`), replacing an author's own first `layer over`.
  `compileObject` keeps from below a layer its exposed methods, its relations when the layer declares none, and its law
  shape when the layer declares no Bend law, however the stack is compiled. The pin seals the whole closure (base,
  layers, library); the prepared-program cache (`programKey`) names the library too. State types compare by
  `canonicalTy` or a named migration. An `extend` naming an object the same turn created lays the layer into the
  making (`extendCreation`; several layers, `CreateRec.layers`, each judged by the made thing's law); a replacing
  reprogram or a migration of it is refused. Tests: `test_extend`, `test_layers`, `test_make`.
- **Make.** World method `make({package, seed, law, requireAbsent, madeFrom {object, receipt}}) -> Created`: `create`
  with lineage; `madeFrom.receipt` "" cites the turn that made `object`; journaled `madeFrom {object, pin, receipt,
  components?}`, kept on `Object.madeFrom` (also by a reprogram that carries one). A compile failure is `refused
  {clause: compile, reading}`. `?` prints `lineageLine` ("After kind/tapper by …, entry 66.").
- **Kinds.** `Ops.kindStack` is the one stack: the root package and ancestor bodies four deep, bottom first, with
  `kindCitation`'s line (only for a kind whose state holds followable `law` text, `Ops.citedLaw`). `world.kindStack`
  serves KIND's `stackOf`; `world.compose` makes a thing with it; `become` installs it (`kindChange`, shared).
  `madeFrom.components [{object, pin, receipt, body, at}]` (one per source kind, `at` its body's layer position);
  `componentInputs` replaces changed bodies in place, retaining unrelated layers; an unchanged repeat stages nothing.
  A replacing reprogram detaches the entry module's component row (`programLineage`).
- **Supervisors.** `Object.supervisor` is fixed at creation (`world-create {supervisor}`, Plan `createUnder`); a
  supervisor other than the creator must offer `ended` (else `refused supervisor`). A supervised activity ends
  `broken` (refused `evaluation`), `budget` (a machine budget ran out) or `timedOut` (a segment resumed past its
  deadline); `commit` puts an `ended {id, to, method: "ended", argument {receipt, how}, sender, ledger}` field in the
  entry, a pending delivery. A ledger refusal tells nobody. Test: `test_supervisors`.
- **Handlers.** Plan `run {object, method, argument, handler}` runs the callee as `call` does; for its whole extent
  every Plan any frame at that depth or deeper yields is offered to the handlers around it, innermost first, each a pure
  `handle(state, message[, context]) -> Handled<R>` (`answer {response}` or `pass`). The handler must be readable
  (`refused {clause: handler, reading}`) and is a root. Test: `test_handlers`.
- **World object.** An activity is `Activity<R>` (dialect `message`) yielding `World.Message {object, method,
  argument}`; `messagePlan` re-heads it as the arm `answer` names. A message to anything but `{world: "", object:
  "world"}` is `refused notWorld`; a method outside `worldMethods` `refused noMethod`. The response is checked against
  the call site's type (`responseType`); `respond` picks the first payload that conforms ("response type cannot carry
  <label>"); a refusal carries `reading` where the site's type has it (`refusedReading`). `worldMethods`: view,
  viewField, viewAt, viewDerived, write, judge, call, callVia, run, send, sendVia, create, createUnder, make, await,
  awaitUntil, interpret, offer, publish, reprogram, extend, compose, kindStack, amend, inspect, check, checkObject,
  grant, grantWith, revoke, objects, heads, changed, card, principal, rule, unrule, want, unwant, grow, ungrow, act,
  chronicle, wanting, holds, receipt. The world has no state and no law.
- **Reads inside a turn.** `viewField {object, field}` answers one field (a `fields` cell root); `viewAt {object,
  version}` the state at a version (`stateAt`: the seed then each write re-applied, checked against its `cid`; refused
  `version` past now or before a fork genesis; root at the current version); `viewDerived {object, view}` a pure
  `views()` definition on the committed state (`noView` with the line to write, `view`, `denied`); `objects {prefix,
  after}` -> `listed {ids, more}`; `heads` the same with each card's `head` and `owner` (no root); `changed {since,
  prefix, after}` -> `changed {items [{object, version, height, by}], more}` from `World.changes` (no root);
  `principal {handle}` -> `named {principal} | unknown` (case-folded, `me` the subject); `holds {object, when}` a
  condition judged of an object as it stands (the object and its citations roots); `receipt {name}` an entry of this
  chain or a carried ancestor by CID or slug (no root). `world-derived` is `viewDerived` from outside a turn
  (`viewTooLarge` past `maxViewBytes`).
- **Held entries.** `compiledMethod`/`compileDef` use `compileEntryIn` (cached in `world.requests`); turns run
  `Turn.startEntry`/`resumeSuspended`/`resumeEntry` over a `Turn.Store`; pure methods, cards and views run
  `Package.executeDataEntryStored`; law, `lawReads`, handlers and migrations `Package.executeDataEntry`. Every frame's
  object is read by cells (`Cells {scalar, fields, rows, spans}`, journaled on the root as `scalar`, `fields`, `rows
  [{field, key}]`, `spans [{field, through?}]`, `gaps [{field, after?, before?}]`); a whole root stays `{object,
  version}`. A write is refused `capacity maxCellBytes` when its scalar part or a row it edited passes
  `Bounds.maxCellBytes`; the storage ledger charges changed cells.
- **Compile caches.** `World.compiled`, `requests`, `builds`, `programs` are keyed by content address, handed from
  world to world within a process (`Caches`); `world-status.compiled {packages, closures, methods}`. With
  `DELVETALK_COMPILE_CACHE=<dir>`, packages (`build-<cid>.json`) and definitions (`def-<cid>.json`) are kept under
  `<dir>/<size>-<mtime sec>-<mtime nsec>` of the binary, re-checked on read (`CheckedEntry.ofPacket`), written after
  every op (`persistCaches`); `world-status.compileCache {dir, hits, known}`. The directory is in the TCB as the binary
  is. Test: `test_compile_cache`.

#### Rules, wants and verbs

- **Store.** `Object.rules`, `Object.wants : List Placed {name, owner, since, line, clause}`, `Object.verbs : List Verb
  {name, by, at, reading, takes, does}`. What a thing carries (`Ops.carried`, `CarriedClause {clause, owner, holder,
  placed?}`): its own text's `rule`/`want` lines (acting as its owner), then those its law's `under` citations carry
  (acting as the thing, `@<id>`: `thingPrincipal`), then placed rows (acting as their placer). A package's top-level
  `rule`/`want` lines are placed by `makeObject` on what is made of it with no law text given.
- **Placing.** A change of kind `rule` (4): `Placement {object, what: rule | want | verb, name, line, takes, does}`,
  judged by the object's law with `request.kind == rule` and `request.verb` `rule`/`want`/`grow`; journaled
  `placements`, in the request digest. A removal is the placer's, the owner's or the opener's (`notPlacer`). Refusals:
  `programRefused law syntax`, `nameTaken` (the text's, a carried line's, a declared method, a host spell or read),
  `lawRefused under`, `lawRefused lawReads` (a line citing what the placer may not view), `unplaced`, `capacity`
  `rulesPerObject`/`wantsPerObject`/`verbsPerObject`. Shares (`checkShare`, per collection, after earlier placings in
  the turn): a hand other than the owner or opener holds `placedPerHand` (on the opener's things
  `placedPerHandOnTownThing`), all such hands `placedByOthers` rules and wants (`placedOnTownThing` on the opener's
  things) and `verbsByOthers` verbs; a thing placing as itself counts against its owner. Placing moves no version
  (behaviour revision only). `placed [{object, cid}]` commits to each changed table (rows, verbs, behaviour counter).
  `stagePlacements` with `check` judges without staging.
- **Spells.** `delvetalk O rule / name / when / [reading] / [for: things] / then: SPELL` (every field after `then:` is
  the nested spell's), `want / name / when / [for] / asks`, `unrule`/`unwant / name [/ for]`, `grow / name / reading
  / takes: text|nothing / does: <spell> | body`, `ungrow`, and the reads `rules`, `wants`, `verbs`. `for: things` on a
  kind appends the clause to the kind's `law` text (a kind-2 state edit judged by the kind's law; the text's byte and
  clause bounds), so every thing following the kind carries it; without it the row is placed on the kind itself.
  World arms `rule`, `unrule`, `want`, `unwant`, `grow`, `ungrow` -> `placed {}`; `act {object, verb, text}`.
- **Verbs.** A grown verb is a form (the text field `act`'s), run as `act {verb, text}` (`grownAct`); `act` itself is
  no spell; a direct `act` naming no grown verb is `noMethod`. `does` names a rule placed in the same entry under the
  grower, `rule NAME: request.verb == "NAME" then SPELL`; `ungrow` takes both off; `retire` of a verb is `ungrow`. A
  `grow` with `body` runs `workshop`'s `growBody` as the speaker's turn: the workshop lays one method and, when the
  layer admits, removes the gesture and its rule in the same turn (`replacing`, through `world.ungrow {check}`).
- **Firing, at commit** (`Ops.reactions`): for each written object, each carried rule whose condition holds under the
  facts the write was judged by, metered against `clauseTicks` (`unfired budget`), its spell filled at the write
  (`Law.filled`: each hole a field value only, rendered by `Spell.renderChecked` and parsed back to exactly that one
  spell; a hole naming a card or action is refused). It fires `fired [{id, to, method: receive, argument {text, post:
  ""}, sender: object, principal, ledger, rule, depth}]`, a pending delivery: id `rule:<object>:<name>:<height>`, or
  `rule:<object>:<name>@<holder>:<height>` for an inherited one; `to` the card the line names as its actor resolves it.
  Past `rulesPerCommit` a firing is queued (`next = clock + i / rulesPerCommit`). Else `unfired [{object, rule, owner,
  why}]`, `why` one of `hole`, `spell`, `noOwner`, `quiet`, `ruleDepth`, `pending`, `reads` (the actor may not view
  the thing or what it cites), `budget`. The delivered turn is the actor's under identity `(actor, rule:…)`; a host
  spell in a rule runs under it. A condition is a level, not a latch: it fires on every write while true; `changed(…)`
  is the transition form.
- **Wants.** `wanted`/`unwanted [{object, want}]` journal the wants that hold after an entry and not before
  (`posing`, each within `clauseTicks`): of each written or created thing, of the things whose wants read it
  (`World.wantReaders`/`wantCites`, the first `wantReviewed` per entry; `Ops.reindexWants`), on a `lawRefused` entry
  (`refusalWants`), and on an `advanced` entry for every thing whose wants read the clock (`clockFlips`,
  `World.wantClock`). Replay re-derives and compares each.
- **What wants a hand.** `World.wanting` (each want's opening height); `wanting {after, limit, oldest}` /
  `world-wanting {principal?, after?, limit?, oldest?}` -> `{rows [{object, name, reading?, asks, since, answerable}],
  more, waiting, next}` (`wantingData`, one function for the arm, the op and `renderWanting`): wants that still hold, of
  things the reader may view, whose filled ask (`wantAsks`, hole-checked) names a visible target that offers the action
  to this reader (`wantAnswerable` over `offeredTo`/`hostOfferedTo`); `waiting` counts the rest. Newest first by whole
  heights, `next` the last height; `oldest` sorts `(since, object, name)`, rotated daily by `(clock / clockDay) mod
  count`, `after`/`next` row offsets. `world-rules {object, principal?}` and `world-wants` list rows with owner,
  handle, `from` (holder), firings and status; cards show each held want on one line (`shownCard`).
- **`request.verb`.** `Written.verb`: `act`'s verb, else "" for the method; journaled `verbs`.
- **Chronicle.** `world-chronicle {principal, day?}` / arm `chronicle {day}` -> `{day, lines}` (`Ops.chronicle`,
  `World.days`): made (crediting the coiner, `coinerOf`), grew, fired/did not fire, came to want/stopped wanting,
  refusals by class, hands; avatars left out; `chronicleLines` then `and N more`.
- Tests: `test_rules` (`Placing`, `Firing`, `Share`, `Holes`, `Revealed`, `KindTargets`, `Transitions`, `Wants`),
  `test_reaction` (`Errand`, `Ticking`), `test_verbs`, `test_wanting`, `test_chronicle`, `test_inhabitants`.

#### Plans and try

- A post with `delvetalk plan` at the margin, or a fence tagged `plan`, is a plan (`Spell.plan`): every spell an act,
  in order, at most `planActs` (`tooManyActs`). `runPlanTurn`/`runPlan` run it as ONE turn under the post's identity:
  each act is routed when it comes and runs at the top of the turn as a spell alone does (a method frame; a placing
  staged; `become`, `adopt`, `lend` staged from `hostChange`; the opener's powers are refused `notInPlan`). One
  `finishTurn`: one judgment, `reactions` once, one receipt. A hole `{made N}` is the first object act N made
  (`fillHoles`). A refusal in a frame refuses the plan whole, reason `act N (<spell line>): …` (`planWaits` for an act
  that would wait); a refusal at commit names the act that staged its object (`planRefusedAct`, from the entry's `plan
  {acts [{line, card, done, made, touched}], of}`). The reply carries `plan`, the acts' lines first in `revealed`, and
  the public projection `act`/`acts`. hob may answer with a plan (verdict `plan {acts}`). `if:` guards it whole. Replay
  builds each creation over the ones before it (`rebuildCreates`). Test: `test_plan`.
- `world-try` (`tryTurn` over `Session.settledStep`): the turn and its settling pass with the write dropped, answering
  `tried: true`, `against {height, hash}`, the receipt of the entry that would be journaled (roots, writes with state
  CIDs that a `world-turn` at the same head lands byte for byte), the exact cards, and `unresolved {pending,
  suspended}`. A post says both (`Serve.postShaped`): a margin line `if: bell/1 v0, kind/bell v2` ahead of the spells is
  the act's `if`, and `delvetalk try` with indented spells is `world-try` of them, dedented, as direct words to the
  commonplace (card `try`, `Ops.tryCard`). Test: `test_try`.

### 5.4 Interpretation

- **The Plan.** `world.interpret::<R>({utterance, offers, policy, model})` suspends like `await` with `interpretation
  {id, object, policy, utterance, offers, model?}` (id = hash of principal, intent, ordinal), deadline
  `interpretationPatience`, resuming `timedOut`. A turn with no reach answers `unclear {needs: ["not addressed"]}` at
  once (no suspension, no model, no quota). A Policy the speaker cannot read is `denied {}`; a Plan without `policy` is
  `malformed interpret plan`.
- **Words a card heard** (`heard`, `heardTurn`). A direct `receive` whose words reached a card (`reach` not empty) and
  run none of its spells goes to the card's `receive` first; what it leaves `silent` (admitted, result `silent`,
  nothing written, sent, offered or published) is discarded and the host reads the words itself, never the card's
  Bend. A card opts out only by answering. hob is offered the card's table (`heardOffers`: forms and grown verbs offered
  to the speaker, and the host's placing spells `rule`/`want`/`unrule`/`unwant` its law admits, `placingForms`), then
  each door's (`doorsOf`, the card's `cites`) card and the first three under it. Field lines that fit an offered form
  run at once, no model. Else the turn suspends with no checkpoint under the world's `policy` object (`policyId`),
  counted by `interpretGate` (the hour's and the day's quotas) and `waitFull` (prose past them is refused `quota` or
  `capacity`, transient; the refusal's `hint` is the card's usage). The suspension journals the offered cards'
  behaviour revisions as roots.
- **Misfits.** A misfit spell (`misfitClauses`) is hob's for every card; anything but a proposal settles as the host's
  `badSpell`, which is the answer at once without a policy. A post's misfit spells are one reading after its fitting
  spells run (`misfitOf`), under the first's identity (`#k`), offered each one's card table; a retry asks nothing. Where
  hob cannot read, each misfit is refused alone.
- **`world-interpretations`** lists pending items with `{model, system, user, examples, attempts, next, reach, roots, identity}`
  and `asked {utterance, offers, card, misfit, wants, pages}`: `card` the asking card as the speaker reads it
  (`cardText`, at most `cardShownChars`), `misfit` the host's own, `wants` with filled `asks`, the library's `pages`.
  `system` is the Policy's `prompt(state, asked)` (hob's instruction, its owner's examples, the answers); `user` is
  `userTurn(state, asked)`: residents' parts each line prefixed `| `, then `Their words:` and the utterance unmarked.
  Residents' writing never enters the system text. `policy.model` is the item's `model` when non-empty (≤ 128 bytes),
  else the Policy's.
- **`world-interpretation {id, reply}`** takes every transport result verbatim. A `failed` reply whose `reason` is
  transient (`transport`, `rate`, `prose`) under `interpretAttempts` journals `attempted {id, attempt, reason, next}`
  (`next` = clock + 2^(attempt−1), at most `interpretBackoffMax`; identity `(interpretation, "<id>/attempt/<n>")`) and
  answers `{status: "retrying", attempt, next}`; the interpreter asks only items whose `next` has passed. Anything else
  journals `interpreted` and the settle pass resumes the turn.
- **Verdicts** (`interpretVerdict`, reading `raw` alone; a reply without `raw` is a request error): `none` (silence),
  `ask: <question>` (`unclear {needs}`), `grow: NAME "reading"` plus the spell using it (`proposals [{method: grow},
  {method: act}]`, one turn), a plan, or spells: the text is split at each margin `delvetalk` line (`spellSegments`);
  each of the first `spellsPerReply` is fitted against the offered forms (`spellVerdict`, which names the form's card)
  and checked as a proposal (`proposalVerdict`: a method the card offers, an argument that fits, words read as cases),
  `proposal {object, method, argument, spell}` or `proposals {items}` of `proposal`/`unclear {reasons}`. A reply that is
  one ```obend block settles the one offered form that takes source. Prose that is none of these is `none`. A failed
  call is `unclear {needs: ["model: <reason>"]}`.
- **Settling.** `resumeHeard` checks behaviour revisions first (`staleBehaviour`, refusing with no write), then runs a
  proposal as the speaker's turn (`runHeard`, origin `interpreted`, the principal from the suspension's identity,
  current state versions), an action in the policy's `confirmFor` offered back indented; `ask:` naming offered fields
  offers "hob: that still needs …"; naming none, "hob: none of <card>'s spells takes that; its spells: delvetalk
  <card> ?". `none` (or `unclear: not addressed`) to words ending in `?` offers the card as the speaker reads it
  (`cardAnswer` = `shownCard`); any other `none`, a failed model or the deadline is silence. A grow is not stale for its
  own speaker's write. `interpretVerdict` declines to fit an obsolete reply; `interpretationSlot` binds nonzero
  behaviour revisions, so a behaviour edit renews the slot.
- **Reach** (`reachOf`, before the spell is read): `reply` (its `replyTo` names a recorded post), `spell`, `delivery`,
  `direct` (a principal named a method other than `receive`), or what the transport states on `world-turn {reach}`:
  `mention`, `mentioned` (heard, never cast), `door`, `fields` (checked: a field line must exist), `direct`. A stated
  reach is in the request digest; `TurnState.reach` carries it through calls and suspensions; a `send` of `receive`
  carries the sender's reach.
- **Quotas.** `interpretQuota` per principal per clock hour (opener and clock principal exempt; refused `quota` with
  `next`, spent once at start); `modelQuota` per clock day counts interpretations and attempts, nobody exempt.
  `world-status` answers `interpretQuota`, `interpretations {remaining, next} | "exempt"`, `modelQuota {quota, used,
  next}`, `hour {hour, turns, refused, interpretations, attempts}`.
- Tests: `test_heard`, `test_policy`, `test_interpret_object` (`SeveralSpells`, `BehaviorReadings`), `test_interpret_text`,
  `test_interpret_quota`, `test_post_reserve` (`Retries`), `test_reach`, `test_spell_turns` (`Misfits`,
  `MisfitsWithoutPolicy`), `test_archive`.

### 5.5 Cards, offers, publish, posts

- **Cards.** Plan `card {object}` -> `carded {document}`: `renderCard` runs `renderWanting(state, context, wanting)`
  when declared (handed `wantingData` for the reader, `cardWanting` rows), else `render`, under the turn's ticks
  (records a root; `denied`, `noCard`, `refused {clause: render}`). `cardContext`: principal = reader, caller = asking
  object, `inputOrigin.kind` "card" (`whole` for a whole render). `world-card {principal, object, whole?}` -> `{status:
  "card", object, text, document}`. `clipCard id text block` is the one bound: `text` then `block` (whole lines) within
  the room; else `text` cut to leave `\n[clipped at N characters; world-inspect <id> reads its source]\n` then `block`.
  `shownCard` adds one line per held want (`wants <name>: <reading>: <spell>`, within a quarter of the room). The room is
  `cardShownChars`, or `World.cardRoom` (setting, up to `maxCardRoom`) for readers; the model's copy is always
  `cardShownChars`. A root `card` override is clipped the same. `world-card`'s `document` is unclipped.
- **Offers.** `offer {to, document}` ("" = the frame's subject). An admitted entry retains `offers [{to, text}]`,
  indexed by addressee (`world.outbox`). `world-offers {principal, after?}` -> `offers [{height, ordinal, identity,
  text, from {post, principal, intent}}]`. A turn's reply carries only offers to its own principal. A refused turn
  offers and publishes nothing.
- **Receipts.** `world-receipt {principal, identity, of?}`: `projectEntry` gives the identity's own principal the whole
  entry and its `revealed` lines, anyone else a `publicRefusal` (`{status: refused, class, root {object, version?,
  behaviour?}, reason?, …}`; a law refusal's reason and reading; a `cardRefused` reading never; a `quota` hint) or the
  chain fields, roots and writes of objects the reader may view, and an `elided` count. Root and moderated entries are
  shown whole to anyone. A refused turn reply carries it as `public`. A refusal that binds its intent says `spent`; a
  replayed answer says it was answered at entry N.
- **The reply.** `turnReply` carries `object` (the card the turn ran on), `inPublic` (every object of its roots and
  writes viewable by the public now) and `revealed`: up to three host lines of an admitted entry, each left out when
  empty: what it moved ("rule two of H fired: SPELL", "… fired (queued until clock N)", "… did not fire: <why>"; DIDs
  shown by handle, `shownSpell`), what it opened or closed ("X now wants N: SPELL"), where it stands (each relation the
  write inserted into, its count, the speaker's first row; said only while the thing is at that version).
- **Default page.** A direct `publishPage` with optional `page` to a card whose package declares none is the host's
  (`defaultPublishPage`): `## Card` (rendered for nobody) and `## How to reply` (`spellUsage`), under `page`, else the
  id; a non-public card is refused `noMethod`. For a declared method an omitted `page` is filled with empty text on a
  direct turn when the input admits it.
- **Publish.** `publish {page, section, body}` -> `published {post}` (at most `publishesPerTurn`; a title or section
  with a line break or over 256 bytes is `refused title`). The entry retains `publishes [{id, object, page, section,
  text}]` in agentwiki text. `world-publications {principal, after?, before?, reverse?, limit?, cursor?}`.
  `transport/bridge.py` `publication_drafts` writes each as an outbox draft and never posts.
- **Posting.** `world-post-reserve {principal: clock, intent, source, for?}` admits one post: a `source: "delve"` post
  counts against `postQuota` per clock hour and against the resident `for` names a share (`postShare`, a quarter, at
  least one; refused `quota` with `share: true`); other sources reserve without a count. Journals `reserved {intent,
  hour, for?}` under `(clock, "post:"+intent)`, so a retry takes no second slot. `world-post-release {principal,
  intent, reason}` journals `released` for a post that certainly did not leave (never for an ambiguous network
  failure); a released intent is reserved anew under `post:<intent>/<round>`. `world-posted {principal, uri, cid,
  object, intent, slot?, page?, section?}` (`uri` `at://` or `zulip://<stream>/<topic>/<id>`, `postSchemes`) settles
  the reservation (posting without one is refused "a post settles a reservation; name its intent"), journals `posted`
  (identity `posted:<uri>`) and indexes `world.posts`. `world-posted {uri, unposted: true, reason}` journals `unposted
  {uri, reason, object}`. `world-status.posts {hour, sources [{source, used, quota?, next?}], share, residents}`.
  `tests.host.posted` reserves under a test source first. Tests: `test_post_reserve` (`Reservations`, `Shares`,
  `Unposted`).
- **Reach of a post.** `world-reach {uri, text, kind, author, replyTo?, root?, mentions?, chain?: [{uri, author,
  replyTo?}]}` -> `{status: reached, object, slot?, how, replyTo?, page?, section?, unposted?}` or `unreached`,
  journaling nothing: (a) a reply reaches its direct parent's card (`walkTo` over `World.posts`, one hop on Delve; on
  Zulip up the topic past only the author's own messages, none when it mentions residents), (b) a spell line its card,
  a summons the commonplace, (c) field lines in a thread the world opened its card, (d) prose naming a door of the
  commonplace's `cites` that door. At most `reachHops` (32) ancestors. The bridge turns at most `mentionsAddressed`
  mentions, on the mentioned avatar with reach `mentioned`. Tests: `test_reach.WorldReach`, `test_bridge`.
- `world-history` pages as `world-entries` does.

### 5.6 Snapshots and replay

- `durable` writes `<journal>.snapshot.<height>.cbor` after the sync when the height is `every` (`world-open
  {snapshotEvery}`) past the last snapshot written or resumed from, and at once after an `ignore`/`unignore`; the reply
  carries `snapshot {height}` or `{refused}` (a failed snapshot refuses nothing). The newest three are kept. File:
  DAG-CBOR `{cid, body}` (`delvetalk.snapshot.v5`); `tests/test_snapshot.py` has an independent Python reader.
- The body is the store (`storeJson`: objects with state, `stateCid`, law text, version, read policy, ledger, compile
  inputs by CID, pin, cached packet, supervisor, minted, readings, fixed, declares, relations, rules, wants, verbs,
  behaviour, madeFrom, maker; types, method tables and law shapes by pin; libraries in use, grants and the grant ring,
  posts, settings, the clock, the name) and `index` (`indexJson`: every index `record` derives). Lineage bodies are
  named by CID (`Snapshot.knownLineage`); sources no entry carries by CID are kept whole (`knownByCid`).
- `openJournal`: the chain read whole and linked (`chainOf`), entry 1 for the edition, then `reopen`: per snapshot
  newest first, check CID, edition, height and head against the chain, install indexes and store, refuse it if a later
  `ignore`/`unignore` names a height at or before it, check each object against its anchors (`checkAnchors`), replay
  every later entry (`checkedEntry`: its record is its CID's, its height, its `previous`). The first failure refuses
  the snapshot by name and the next older is tried, then full replay (`replayAll`, which finds the ignore set first,
  `ignoresFrom`). `withAncestry` attaches the local journals a carried genesis authenticates (`ancestryOf`: the
  `carriedFrom.world` path or one beside the journal, every link matching the hashes the carry kept).
- Anchors (`World.anchors`, six heights per object: version, pin, law, placed, read policy, maker). `install` refuses
  "the state of X is not its CID's" and "object X carries no state CID"; `checkAnchors` refuses a state, pin, law,
  placed table (with its behaviour counter), read policy or maker that no entry commits to ("the state of X is not the
  one the journal commits to at version V", "object X is not at the journal's version and pin", "the law of X is not
  the journal's"). A forger who points an object back at an older genuine anchor is `verify`'s: `world-open {verify:
  true}` replays from genesis and refuses each snapshot whose body differs from the replayed world's. Snapshot
  installation normalizes older full grants.
- **Pins are sources.** No packet digest is journaled: replay recompiles from the journaled sources with the current
  compiler and requires the compile to succeed, the seed to conform and the recomputed pin to equal the recorded one.
  `world-status.recompiledDifferently` counts objects rebuilt after a snapshot resume whose packet differs from the
  cached one.
- Suspension checkpoints are journaled as `tokenTree {depth, roots}` over content-defined blocks (`cutBlocks`: leaves
  32..256 tokens, a token of 256 bytes or more its own leaf; inner nodes 2..16 names), each block once per journal in
  top-level `blocks [{cid, items}]`. An activity's texts of 256 bytes or more are one-item blocks shared with the
  checkpoint's leaves (`hoistLabels`/`lowerLabels`); an interpretation's `offers` a one-item block, its `utterance`
  `utteranceIsText` or a block. The checkpoint omits what the entry says (object, principal, intent, digest, roots,
  empty fields), derived again by `expandSuspended`. Test: `test_suspension_size`.
- Replay never re-runs a method (Snapshot imports Ops, not TurnLoop): it re-judges and re-derives.

### 5.7 Slugs, fork, repository reads

- **Slugs** (`Slug.lean` `ofCid`, `decode`): proquint of the first 32 bits of a CID's multihash digest
  (`lusab-babad`). Replies show receipts with `slug` beside `hash`. `world-resolve {principal, slug}` -> `{status:
  resolved, kind: receipt | pin | state, cid, receipt?}` (a carried world's old receipts as `{kind: receipt, carried
  {world, height, at}}`), `ambiguous` or `unknown`, over `slugTargets` (a scan of every entry). `delvetalk receipt /
  of: <slug or at:// post>` is answered by serve from `world-resolve` or `world-receipt`, journaled nowhere (`{status:
  looked, of, found}`). Test: `test_slug`, `test_posting`.
- **Fork.** `world-fork {principal, height?, into}` (`into` must not exist) writes a journal whose one entry is a
  `forked` genesis: the store at `height` with only the objects `principal` may view (grants, pending deliveries,
  suspensions written out whole), the handle registry, `omitted [ids]`, `forkedFrom {world, height, cid}`. Opener,
  clock principal and library-law principal are `principal`. Answers `{status: forked, into, forkedFrom, carried,
  omitted}`. Test: `test_fork`.
- **One genesis mechanism** for fork and carry (`Ops.installsStore`, `genesisOrigin`, `genesisRow`;
  `Snapshot.genesisEntry`, `installGenesis`): the store, every source carried once and named by CID, pending deliveries
  and whole suspensions, the handles; each object gets one touch barrier at the genesis height, so a root read below it
  is stale. `world-status` shows `forkedFrom` or `carriedFrom` (`originShown`).
- **Repository reads.** `world-entry {principal, hash, bytes?}` (`bytes` = hex of the canonical DAG-CBOR, the
  identity's own principal only); `world-entries {principal, after?, before?, reverse?, limit?, cursor?}`;
  `world-object {principal, object, version?}` -> `record {object, version, pin, pinSlug, law, readings, laws [{object,
  version, pin, name, clause, reading?}], stateCid, library?}` as of the version (`pinAndLawAt`);
  `world-source`/`world-sources` -> `{cid, name, text, height}` for sources of objects the reader may view and the
  libraries'; `world-grants`. Test: `test_reads`.

#### Serve

`delvetalk-obend serve --state DIR [--socket PATH] [--root-socket PATH] [--root-group GROUP] [--opener DID] [--library
DIR] [--sync none|fsync|full] [--clock P] [--home NAME] [--scratch-quota N]` (`Serve.lean`, `spec/native/serve.c`) is
the one process over a directory of worlds.

- *Lock.* `flock` on `DIR/journal.lock` before anything, held for the process's life (`Server.lock`); a second `serve`
  exits 75, "refusing to start a second writer". `DIR/serve.pid` is rewritten per op.
- *Library.* `DIR/library` rebuilt at start from `--library` and arrival's packages (`Serve.arrival`: `Avatar`); the
  stateless session `library-load`s it; `serve-status` answers its pin.
- *Worlds.* `DIR/<name>.journal`, `name` by `validWorldName` (`[a-z][a-z0-9-]{0,31}`, not `did zulip at world me
  scratch`); envelope `world: <name>`, default `--home` (`town`). Each world is opened at start with the clock, opener,
  library, sync and `name`, and held; `world-open {name}` journals `named {name}` once and refuses a journal that holds
  another. `world-open` over a socket is refused ("serve opens its worlds").
- *Sockets.* `DIR/host.sock` (0600) and the root socket (default `DIR/root/root.sock`, 0660, group `--root-group`)
  under umask 0177, backlog 128. The C shim reads newline-framed lines (16 MiB) and hands Lean the next completed line;
  one thread answers. SIGTERM/SIGINT end the loop after the op in hand, removing sockets and pid file. The public socket
  refuses `rootOps` (`world-root`, `world-library`, `world-settings`, `world-fork`, `world-snapshot`, `library-load`,
  `world-dump`, `world-screen`, `world-screen-verdicts`, `world-screen-review`) with `{status: error, class: "opener",
  message}`. The opener's ordinary turns are the public socket's: serve marks them `resident: true` (`World.resident`,
  erased before any digest), and `openerActs` (the opener, not resident) gates the opener's privileges.
- *Status.* `serve-status`: `hostSha256` (cached in `DIR/binary-pin`), `pid`, `replay`, `library`, `worlds [{name,
  height, objects, clock, replay, snapshot {resumed, refused}}]`, `scratches [{principal, world, lastTurn, expires}]`.
- *Scratch worlds* (`Serve.scratchOp`): `world-scratch {principal, name, from?: {world, height?}}` writes
  `DIR/scratch/<principal>/<name>.journal`, empty with the sealed library and the principal its opener, clock and
  librarian, or forked from a world (what the principal may view). Turns name `world: scratch/<name>`. At most
  `--scratch-quota` (default `scratchPerPrincipal`; a further one refused `capacity` naming the oldest), each under
  `scratchJournalBytes` and `scratchObjects`. Serve keeps each scratch's home clock at its last op (`<name>.last`) and,
  on the home world's `world-advance`, discards each `scratchMinutes` past it (the one deletion); an op on it then is
  "scratch/<name> expired at clock N; open it again with world-scratch". The root act `expire {principal, scratch}` and
  the owner's `delvetalk world expire / scratch: <name>` (`Serve.expiryAsked`) discard one now. `world-status.scratches
  {open, expiring}`.
- *Exit.* `world-cite {principal, scratch, receipt, identity?}` journals the scratch entry whole in the home world as
  `cited {world, receipt, entry}` (identity `cite:<hash>`).
- *REPL.* `world-repl {principal, identity, entry, source?, object?, argument?, arguments?}` (scratch worlds only)
  compiles `source` over the world's library: a non-Activity entry runs on `arguments` and journals nothing; an
  Activity is a method of `object` (default `repl`), made or reprogrammed (`<identity>/defined`), then run as the
  principal's turn. Front routes `/AGENTS.md/scratch/<name>/repl`, `/check`, `/cite`.
- *Across worlds.* A `Reference {world, object}` with a world names that world's object. `view`, `viewField`, `viewAt`,
  `viewDerived`, `card` and `inspect` of one run in that world (`Foreign.read`, under the reader) and the entry
  journals `cites`, not roots (a foreign read can go stale without refusing; replay reads nothing foreign). A `call`,
  `callVia`, `send` or `sendVia` crosses: refused `noGrant` under a grant, `foreignWorld` for a world not served,
  `crossing` for a second per turn or from inside a call. A send stages a `Send` with `world`, never delivered here; a
  call suspends on `(principal, id)` with `crossing`, deadline `crossingPatience`. Serve carries both after every reply
  (`Serve.cross` over each world's `Ops.outbound`): the target journals `relayed` under `(principal, "<home>:<id>")`,
  delivered by its own settling pass under the caller's principal (`request.caller` `<home>:<object>`); the home world
  journals `crossed` with the answer, receipt and result. Each step is idempotent. `world-view`/`world-card` of
  `<world>:<object>` answer that world's reply with `asOf`.
- Tests: `test_serve`, `test_scratch`, `test_http.Repl`.

#### Carry and root-edit

- **Carry.** `delvetalk-obend carry --from J --out J2 --reason R [--library DIR] [--body OBJ=FILE]... [--leave OBJ]...`
  (`Carry.lean`): J only read (verified, flock free), J2 must not exist. The world is read from J's head snapshot
  (`verifiedBody`, `readWorld`: the `readKeys` laid over an empty world's, so an older binary's body is a contract on
  those keys alone; `previousEdition` `v4` checked by its three anchors), never from J's entries. `carryWorld` rebuilds
  every object under this binary (`rebuilt`: sources seal to the pin, state conforms, rows canonical; then this host's
  type, bounds, method table, law shape, packet, relations, fixed and declared fields) and checks every suspension
  (`resumable`). Each failure refuses the carry, all listed by name.
- *Moves.* With `--library`, the image's packages are that library's modules and `DIR/../objects`, its bodies `--body`
  (`movedInputs`). An object whose code changed moves (version + 1): its state stays when it conforms, else the
  package's `migrate` converts it (`compileMigration`, `runMigration`, shared with reprogram; checked, canonical, within
  `maxCellBytes`, moving no fixed field). One whose law is its package's takes the new law and readings (`law {before,
  after}`) and its package's `rule`/`want` lines (`placed`, `unplaced`); an amended law is kept (`kept`). A moved
  object's package that offers `carried` is told `carried {}` once (`rearmed`: pending delivery `carried:<id>`); its
  suspensions are dropped, supervisors told `ended {how: broken}`. Any other suspension the carry cannot keep refuses it.
  Left, retired at its old pin (`Ops.retiredLaw`, reason's first line within 200 bytes): an object `--leave` names, one
  whose entry package the image no longer ships, one whose move refuses.
- *Genesis.* `carried` at the old head's height + 1: `carriedFrom {world, height, cid, replay, reason, entries {hash:
  height}, library?, carriedFrom?}`, `index` (`carriedKeys`), `identities` (every bound identity, read into
  `World.carriedIds`, never from a snapshot: a retry after the carry answers the old receipt; `Ops.boundEntry` the one
  lookup), `made [{object, identity, height}]` (each object's making, `Carry.makings`, from the old chain or its
  genesis's `made`), `left`, `moved`, `kept`, `dropped`, `rearmed`. J2 is replayed from its genesis and each state CID
  compared before it is written. A genesis is written whole (`maxEntryBytes` bounds appends only). A pre-carry
  `world-receipt` answers from the identity row the genesis kept; an old hash or slug resolves to its world and
  height there (`receiptNamed`, `world-resolve`). The ancestor journals, attached when on disk (`ancestry`), serve
  history reads (`historyEntry`: firsts, tellings, the moderation backfill).
- *The no-wipe gate.* `deploy.genesis` refuses, naming each journal under `--towns` other than its own, unless
  `--wipe-with-the-owners-word R`. `deploy/carry-check.sh [--old-image I | --old-binary P] [--leave O]... BINARY
  BACKUP` replays the newest backup from genesis and carries it under the candidate: green, green-breaking (the deploy
  carries), green-moving (the image moves objects; a restart in place keeps them at their old code) or red.
  `python3 -m transport carry --from OLD --to NEW --reason R [--leave [W=]OBJ]... [--obend B]` carries every world, copies
  the transport's files, checks each world in a throwaway copy (state CIDs, cards, every old slug, an advance), then
  runs `deploy.genesis.carried` (genesis's laws and kinds as the image stands; refresh rows must be `refreshed`,
  `current` or `left`). Tests: `test_carry` (`Carry`, `Moves`), `test_carry_check`, `test_genesis` (`NoWipe`,
  `CarriedRefresh`, `Reshape`).
- **Root-edit.** `delvetalk-obend root-edit --journal J --out J2 --reason R` with `truncate --height N`, `drop --height
  N`, `rewrite --height N --entry FILE`, `splice --at N --entries FILE`; `--state DIR --reason R delete-world --name W`
  moves `W.journal`, its store and snapshots to `deleted/W-<stamp>.*` beside `W-<stamp>.json` (refused while serve
  holds `journal.lock`). J must verify and not be open (exit 75); J2 must not exist; J is never written. `reseal`
  re-seals entries after the kept prefix (`previous`/`hash`; a `turn` equal to the old height becomes the new; `ended`,
  send, change, publish and interpretation ids recomputed under a changed intent; every later string equal to an old
  hash or id rewritten; a root `ignore`/`unignore` height follows its entry). The first re-sealed entry carries
  `rootEdit {command, reason, oldHead, at}`. J2 is replayed in full before it is written. Heights are as the journal
  names them (`baseOf`). Not rewritten: CIDs inside checkpoints and states, `at://` citations elsewhere. Test:
  `test_root_edit`.

#### Root and moderation

- **`world-root {principal, reason, act}`** (`Root.lean`, opener only, root socket; `reason` one line ≤
  `maxReasonBytes`). Acts: `set {object, field, value}` for `state`, `state.F` (one top-level field, typed or plain
  JSON, conforming), `law`, `program` (`{modules}`, recompiled), `pin` (stored alone), `owner`, `read`, `version`,
  `fixed`, `supervisor`, `ledger`, `readings`, `activities`; `delete {object}`; `as {principal, turn {object, method,
  argument, identity}}` (an ordinary judged entry with `root {by, reason}`); `settings {clock?, clockPrincipal?, opener?,
  libraryLaw?, <settingKeys>}` (the reply lists suspensions and grants whose deadline lies between, `clockAffected`);
  `library {modules}`; `ignore`/`unignore {height}`; `card {object, text|null}`; `quiet {principal, hours}`, `unquiet
  {principal}` (a quiet of zero hours); `hide`, `show`, `retire`, `unretire`; `revoke {grant}`; `expire` (serve's).
  Every act is a new `root:<n>` identity.
- *Entry:* `{identity {opener, root:<n>}, root: true, reason, turn 0, roots [], request, outcome {tag: root, kind,
  object?, field?, height?, principal?, grant?, before, after, version?, cid?, pin?}}`. A state or owner set raises the
  version and pushes a `Touch` with unknown edits. Replay: `rootBefore` reads the replaced value, `applyRoot` lays
  `after` on it (no judge, conformance or pin check), `recordActs` moves the derived indexes; "root entry N: before does
  not match" refuses. An ignored height replays inert (`recordInert`); after the lowest height any ignore names, an
  entry that no longer replays is shadowed (`World.shadowed [{height, by, reason}]`, in `world-status`, the open reply
  and `verify`); before it a disagreement breaks the journal. After an ignore the session re-derives the store from the
  newest snapshot below it and writes a snapshot at once.
- **Powers.** `world-turn` on `world` (`quiet`, `unquiet`, `settings`, `revoke`) and on a card (`retire`, `unretire`,
  `hide`, `show`, when the card has no such method), or as spells (`delvetalk world quiet / who: … / hours: … /
  reading: …`). Opener only (`badSpell opener`); `reading` required. `quiet`/`hide`/`show` journal `moderated {power,
  …, before, after, reading}`; `retire` is the opener's amendment appending `law retired "<reading>": request.kind == 2
  and request.subject == "<opener>"` (a maker may add the same guarded shape by ordinary amendment), `unretire` removes
  it.
- **Settings.** `world-settings {principal, reading, identity?, <settingKeys>}` and the `settings` power journal a later
  `settings` entry (`settingsChange`, `withQuotas` live and in replay). Keys: `postQuota`, `interpretQuota`,
  `modelQuota`, `turnQuota` (a hand's direct turns a clock hour, 0 none; `turnGate` refuses `quota` clause
  `turnQuota`, counted into `turnsStarted` for entries `startsTurn` names by a `turnCounted` hand), `objectQuota` (the
  world's `objectsPerPrincipal`), `paintQuota` (paints a clock day, 0 none; `Cache.paintDay`), `cardRoom`. Snapshot
  `settings` writes quotas only off their defaults. `world-status` answers `turnQuota`, `objectQuota`, `turns
  {remaining, next}`, `paintQuota {quota, used}`, `cardRoom`. Test: `test_newcomers`.
- **`world-dump {principal, object}`** (root): `owner`, `read`, `fixed`, `supervisor`, `ledger`, `activities` (each
  waiting suspension's hash, principal, intent, method, post or slot, deadline, interpretation).
- **Automatic moderation** (`Screen.lean`, `Moderation.lean`; docs/ROOT.md §2.4): retroactive, never in a turn's path.
  `world-screen {principal, after, limit?, external?, quietHours?, until?, dryRun?}` answers the texts written after
  `after` (at most 512 entries, 256 texts; `external` feed posts from the transport, ≤ 64 KiB each), less those already
  screened; the wordlist (`Screen.prefilter`) acts at once (hidden, author quieted `quietHours`, default 24); answers
  `{status: screen, through, items, acted, policy, start, base}`. `world-screen-verdicts {principal, items, reply,
  quietHours?, model?, dryRun?}` reads the classifier's reply verbatim: high confidence hides and quiets, medium hides,
  low goes to review; `sexual-minors` always high; answers `{acted, passed, unanswered}`. `world-screen-review
  {principal, key, verdict: restore | confirm | hide, reading?}`. Each act is a `moderated` entry under the opener
  (`screen`, `quiet`), applied verbatim on replay (`World.screened`). A text is named by its key (CID of the text); its
  first `screen` entry carries the bytes once, elided in public projections. The town's own principals (opener, clock,
  `@<id>`) are never screened. Every reply but the opener's passes `Screen.redactJson` (`[hidden by moderation]`).
  `world-screened {principal, state?, limit?}` (the opener reads whole; others keys and sources only) and `world-redact
  {items: [{source?, text}]}` serve the front.
- Tests: `test_root`, `test_root_console`, `test_post_reserve.Unposted`, `test_serve`.

### 5.8 Arrival

`world-arrive {principal, did, handle}` (clock principal only; the world must name an opener and have a library)
records the handle as `world-principal` does (a changed handle is one `principal` entry; "" forgets one), then creates
the newcomer's avatar `<did>` from library module `Avatar` (`Ops.arrivals`) when absent, as `create` by the opener with
identity `arrive:<did>`, `owner: did`, the seed naming `owner` and `handle` where the state has them. Idempotent: a
repeat answers `{status: "arrived", did, handle, created: []}` with no entry. A missing library module is a request
error naming it. `me` in any spell or direct turn is the speaker's avatar (`resolveCard`); a speaker with no avatar is
refused `badSpell noAvatar`. A card is also named by a resident's handle (`namedCard`), naming their avatar.
`docs/GENESIS.md` says when transport calls it. Test: `test_arrive`.

#### Spells

`Host/Spell.lean` is the one grammar (`world/lib/Spell.obend` keeps only the inline reader `Card` still calls).
`spell-parse {text, form?, addressee?}` answers `{status: parsed, spell | notASpell | quotation, fit?, bare}`;
`tests/test_host_spell.py` runs the fixtures in `tests/fixtures/spells/`.

- **Lines.** `delvetalk` (any case) at the margin starts a spell; an indented one is an example. A text holding a card's
  header line (`cardHeader`: `✾ `, `Seven doors.`/`One door.` by door count, `KIND `, a line ending `Make one:`)
  beside a `delvetalk` line is a quotation (`badSpell quotation`, with the card's usage). A post that is one spell block
  and nothing else, indented alike, bare or in one ```` ``` ````/```` ```text ```` fence, is dedented and cast
  (`wholeSpell`). No spell is read inside a `<<TAG` block or a tagged fence. Actions and field names fold to lower case;
  a capitalised action is one only when nothing but inline fields follows it; one trailing `.` or `:` is trimmed; a
  card name is kept as written and matched folded (`foldedId`). On a direct turn whose reach is `direct` or `reply`, a
  first line naming one of the card's actions or `?`, alone or after the card's name, is the spell line without
  `delvetalk` (`Spell.parseFor`).
- **Fields.** A line is a field only when it `looksLikeField` (`name: value`, an identifier); any other line, a line
  after a blank, or a name the form lacks ends the fields (an unknown name followed by a known one is `unknownField`).
  A line with no colon, and the slashed form's leading segments, are values without a name, bound in order (`bind`) to
  the open choice they name, else digits to the one open natural, else the one open text field; a value fitting
  nothing is dropped. A binding whose folded name is a form field's takes the form's spelling. A `text 0..N` field may
  be left out. A `source` field the spell lacks takes the reply's first ```obend fence.
- **Routing** (`routeSpell` -> `SpellRoute`: `run`, `usage`, `read`, `host`, `refuse`, `asIs`). A direct turn goes to
  the card the spell names (`resolveCard`: an id, `me`, a handle, folded) and is retargeted there; a call or delivery
  reads only spells naming the card it was sent to (`otherCard`); `callVia`/`sendVia` are never read. A `receive`
  argument with a field the card's input lacks is not read as a spell (`heardFits`). A spell runs the named method only
  if the card offers it, with the typed argument, `inputOrigin.kind = "spell"`, `command` the spell line. A direct turn
  is first answered from its identity (`retainedTurn`) before routing. When a card's `receive` declares `spell: {card,
  action}` (and `fields`), the host fills it (`heardArgument`, `castData`).
- **Misfits** are `badSpell` (binding) with `clause` (`otherCard`, `noAction`, `unknownField`, `duplicateField`,
  `badValue`, `unclosedBlock`, `unclear`, `quotation`, `fixed`, `noAvatar`, `tooManySpells`, `opener`, …), `reason` and
  `hint` (the spell with a blank where the value did not fit, `blankedTemplate`), all public; usage and reasons speak the
  card as the speaker wrote it. Reasons are docs/VOICE.md's (`Refusal.voiced`, `castSpell`, `lensSpell`, `spellUsage`);
  the first card is the commonplace ("the commonplace lists the doors"; a card with no spells: "reply in words and hob
  places them"). A direct turn's `?` usage and hint end with hob's line (`hobTail`) when an object `library` the
  speaker may view exists.
- **Several spells.** A direct `receive` holding two or more margin spells (`Spell.segments`) runs `runSpells`: each
  spell is its own turn (identity the post's plus `#1`..`#3`, judged alone, its own receipt); a fourth and later are one
  refusal `#4`, `tooManySpells`. Reply `{status: "spells", turns}`.
- **`?` and reads.** `?` answers `{status: usage, object, text}` and journals nothing: the offered forms
  (`usageForms`), lenses, the host's spells the law would admit, `lineageLine`, `objectsLine`. Host reads answered as
  `?` is: `rules`, `wants`, `verbs`; `delvetalk objects ?` (`objectsListing`, 20 a reply); the town's reads
  (`Surfaces`: `book` on an avatar; `chronicle`, `map`, `source`, `makings` on any card without its own, rendered by the
  commonplace's definitions over the index the host folds for the reader; `world-surface {principal, object?, read,
  fields?}` for the web); a read's reply carries `whole` beside its first page when they differ. `delvetalk guide` is
  `delvetalk library read / page: guide` (`guideCard`). `delvetalk receipt / of:` is serve's (§5.7).
- **Lenses.** A card declares `lenses() -> List<Form.Field>` and `set(state, {field, value}, context)`; `delvetalk
  <card> set` with one field line is judged against the lens's kind; a field no lens names, or more than one line, is
  `unknownField`; fixed fields have no lens. A card whose forms already have `set` keeps it.
- **Host spells** (`hostSpells`, on a card that defines no form of that name; direct turns only, a call or delivery
  naming one is `noAction`): `become / kind: <id>` (installs the kind's stack, text citation and lineage in one turn,
  judged by the card's law; refusals `missingField`, `unknownKind`, `of`, the law's, `programRefused`), `adopt / law:
  <id or inline law lines>` (appends the clause set, incl. `rule`/`want` lines, under the metarule; `unknownLaw`,
  `noLaw`, `lawClash`, `law syntax`), `lend / to: <handle or me> / method: <m> / until: +<n>` (a grant from the speaker,
  reading "lent by <handle>: <m>, until clock N"; only a method the card offers and the law admits the speaker to run,
  else `notYours`), the placing spells, `grow`/`ungrow`, and the powers `retire`, `unretire`, `hide`, `show`. `?` lists
  each where the law would admit it (`kindAdmits`).
- **Names.** `Limits.nameAlphabet` and `maxObjectIdBytes` are both the id rule and the card-name rule; Spell.obend's
  `cardAlphabet()` is the same string.
- Tests: `test_spell`, `test_host_spell` (`Margin`, `Clauses`), `test_spell_turns` (`Lenses`, `FixedFields`),
  `test_usage_voice` (`ReaderActions`), `test_extend.HostSpells`, `test_surfaces`, `test_posting`.

#### Enchantment (paint)

`Enchant.lean`, `world/lib/Paint.obend`, `Tongue.lean`; never journaled.

- **Strokes** (`assemble`, `strokesAt`; `world-strokes`): read from the store at a version by field name: `head` (else
  `name`), `fields`, `kind` with its `voice` and `about` (`kindText`; a thing of no kind reads its place's kind),
  `maker`, `keeper`, `owner` (handles; a thing acting as itself by its id, `handleIn`), `made`, `tended` (clock
  minute, 0 never), relation `counts` as `Quantity` with unit and meaning, the eight newest `lines`, `marks` (every
  `station-scene-*` row shown as `the scene`, `Mark.ofRow`), `verbs`, `laws`, `doors`, `around`, `present`, `rules`,
  `wants`; a past version is `historical`. `Strokes.facts`: numbered `Fact {id, kind, subject, value, clause}` rows
  (maker/owner/keeper/location, last tending, counts with meaning, recorded marks, present hands, holding wants,
  events). `Strokes.text` is what the painter reads (no entry numbers), with `notImagery`, `budget` and the quotation
  marks. The day (`dayStrokes` over `Ops.chronicleDay`) and the morning (`{day?, morning?}`, what still wants a hand,
  oldest first, no spells) are strokes with no `object`. A coiner without a handle is credited as the coiner, never by
  id or address.
- **The paint.** A factual line is only `[[id,...]]`, expanded by `Enchant.part` into host clauses; uncited prose is a
  guarded simile or a framed quotation of a resident's whole line or a U+2026-marked excerpt (`markedExcerpt`)
  credited to its author. `verify` runs the table `clauses` (`ids`, `numbers`, `handles`, `spells`, `quotes`,
  `attribution`, `heads`, `forbidden`, `secondPerson`, `negation`, `imagery`, `tongue`, `facts`, `length`), the first
  failed refusing; a thing paints in at most 400 characters (source and expansion), a day 600. Tongues: the avatar's
  stated tongue, else the words' (`detect`), else English; per-tongue frame words, numerals, unit stems and the town's
  name; a tongue with no table is not painted. `world-render-check {principal, object?, version?, text}` judges any
  text, answering the expanded text.
- **Rendering.** `world-render` keys the strokes `bodyHash {strokes, library pin, model}`; a cached `painted` answers its
  text, a refused one `exact {reason: rejected, clause}`; else it queues `pending` (`maxPending` 64, `busy` past it)
  with `{model (the policy's, else claude-haiku-5-5), system: Paint.contract(), user: "Strokes:\n" + JSON, maxTokens}`.
  `pending` carries `patience` (`renderPatience` 3 s) only while a worker attends (`world-renders` within
  `workerGraceMs`); otherwise `exact {reason: unattended}`, still queued. `world-render-submit {key, reply}`: `replied`
  is verified and cached; `transport`/`rate` waits `renderBackoffMs` and is listed again (`renderAttempts` 3); every
  non-model refusal is asked once more with its note (`retried`), then `exact`. Past `paintQuota` an uncached render is
  `exact {reason: budget}`. `plain` answers `plain`; a root card override `exact {override}`; no policy or no `Paint`
  module `exact {unavailable}`. With `DELVETALK_RENDER_CACHE` set, painted and refused renders persist (kind `render`)
  and are re-verified on read; otherwise renders are per process (`Open.renders`). `world-status.renders {cached,
  rejected, pending}`.
- Transport: `interpret` is the one model worker (interpretations, then paints); `interpret.paint` reports `verdicts`
  per retry and exact submission; `transport/host.py` `painted()` answers `{text}` or the host's `{reason, clause?,
  detail?}` (`fell_back` says it in a line); fronts place the paint above the exact card; the bridge drafts exact.
- Tests: `test_enchant` (`Strokes`, `Facts`, `LivePaints`), `test_tongues`, `test_telling`, `test_scene_marks`,
  `test_carry_paint`, `test_http.Play`.

## 6. Gotchas

- **Replay edition (a rule).** `Limits.replayEdition` (Store.lean) is the edition of what replay derives;
  `Journal.sealEntry` writes it as `replay` on every journal's first entry (a fork's and a carry's genesis too),
  `world-status` answers it, and `Snapshot.openJournal` refuses a journal of another edition before replaying anything
  ("journal replay edition N; this host is M; … carry it (`delvetalk-obend carry --from J --out NEW`, …)"; no field is
  edition 1). A world replayed under rules it was not judged by would lie. Policy (FOUNDATION §2): an additive derived
  field is compared when present and derived when absent, with no bump; a bump is a breaking change, which ships with
  `deploy/carry-check.sh` green on the newest town backup (the deploy then carries) or does not merge; a world is never
  begun again for one. The editions and what each derives are listed in the doc comment on `replayEdition`
  (1 through 20). Test: `tests/test_replay_edition.py`.
- **The snapshot body is the carry's contract.** `carry` reads an older binary's head snapshot through `Carry.readKeys`
  and `install`: a change to what those read (`storeJson`, or an index key in `readKeys`) keeps the reader of the
  edition before it in the same commit, deleted when the next lands.
- **A world whose rows predate `placed` anchors replays whole at every open until it is carried.** An object carried
  from before rules were placeable keeps its old default law (no `or request.kind == rule`).
- A placing moves no state version, so `version` alone never says a card's behaviour changed: read `behaviour`.
- `World.forkedFrom`/`carriedFrom` live in entry 1 only; a fork's heights start at 1, a carry's continue.
- `conformsUnder` needs the packet's bounds (`Object.bounds`, `Compiled.bounds`); bare `conforms` is only for closed
  non-recursive types.
- `canonicalTy` (Ops): two state types are equal when their canonical forms agree (variables renamed in order of first
  use, at most 4096 steps, else "type too deep to compare"). Reprogram and extend depend on it.
- Wire shapes: `world/lib/World.obend`'s `protocol world` is the contract (Plan.obend keeps the shared records:
  `Reference`, `Edit`, `Slot`, `Receipt` with `hash`, `MadeFrom`). `write`'s edits are a record with one variant per
  state field. A World.obend change moves every pin (`tests/fixtures/pins`).
- Relation rows sort by the canonical DAG-CBOR bytes of their key projection; DAG-CBOR orders map keys by length first,
  so key `{author, at}` sorts by `at` before `author`. Relations: `def relations() -> List<Decl>` (`{field, key, limit,
  retain?}`; `retain` only `dropOldest`), rows `{items}`; edits `insert`, `upsert`, `retract {key}`; `amendItem {item,
  change}`/`removeItem {item}` address a list item by canonical bytes (`absentItem` when none).
- Seeds are laid over `initial()` (`mergeSeed`): a record of some fields, `{}` for `initial()`; a field the state lacks
  is `typeMismatch`. A seed that does not set a text `owner` gets the named `owner`, else the creating principal
  (`withOwner`). `create`'s `package` is a module name in the creator's sealed chain, or source starting `edition`;
  `law` is used only if it starts `law `; `world-create {law}` replaces the package's law from creation (a malformed one
  is a request error), journaled as `lawText`.
- Hand-built Contexts in tests must carry caller, sender, intent and height or the method does not type.
- Lean keywords: `meta`, `from`, `seal`. Structure-instance continuation lines must be indented past the first field.
- A suspended identity has a `suspended` entry; `retained` ignores it so the final commit can reuse the identity.
- Settling runs inside `durable`, after the triggering op, and appends to the same write.
- `Handle.flush` is not durable; `sync.c` does `fflush` + `fsync` (or `F_FULLFSYNC`). One sync per `durable` call. The
  build needs `lakefile.lean` for `extern_lib`.
- `python3 -W error` turns leaked subprocess warnings into failures; close hosts in `tearDown`. `test_await` is slow
  because every `world-create` compiles.
- A counted relation can plateau at its retained cap (RECORD's lines at 128), so a changed count is a value
  transition, not evidence of every future event.
- The paint's imagery guard compares the strokes' own words; it cannot prove a metaphor harmless, and a translated
  source word passes it.
- Never run an unfiltered package suite on a loop.

## 7. Open

Each item: what, owner, the check that closes it. A merge touching the host runs `deploy/carry-check.sh` on hbox first.

1. **`shownSpell` scans for `did:` tokens** (host). A `fired` row keeps the filled spell, not its holes, so a DID the
   speaker typed is shown by handle too. Keep the rule's template and its fills on the row, show the fills by handle,
   delete the scan. Check: a typed DID in a rule's spell shows as typed.
2. **A telling misses marks a kind-2 write inserts** (host). `Ops.writeEdits` returns no edits for a write holding a
   kind-2 step, so `spanOf` sees none: the station's stitch (amends its law and inserts the mark in one write) tells no
   mark. Check: a bare telling of the station lists its scene marks.
3. **Paint fallbacks not yet explained** (next paint lane). Porch, station/dj and station/bee fell back to exact with no
   scene marks to blame; read `interpret.paint`'s `verdicts` for the clause. (a) A telling's exact first line names a
   handle-less coiner by at:// address: decide with transport whether the page links the post. (b) Count clauses read a
   line's verb as a unit ("1 came", "cames: 1", `plural`, `lineQuantities`); check: the regular's facts read as a
   reader would say them. (c) The painter copies the contract's example handles as credits: give the examples handles
   no fixture uses and rebind `test_tongues`/`test_telling`; check: no live credit to an example handle. (d) A Spanish
   paint of one quotation frame alone fails `tongueFault` (two indicators wanted); check: `kimik3.delve.town dijo «a
   line»` alone passes `tongue`. (e) Decide whether a tongue's lexicon carries translated source words for the imagery
   guard.
4. **Rules and verbs remainder** (host, objects lane where noted). `revealed` should say what the speaker is now
   offered ("it now takes `ring`", after a grow "it now takes `water`"). `carried` parses each text per commit: keep
   parsed clauses on the `Object`. The card's `Grown here:` line needs a `world.verbs` arm (decide with objects). Bend
   arm tests from a `made` body for `rule`, `grow`, `act`, `chronicle` (only `wanting` is covered).
5. **Carry remainder** (host). A carried genesis holds the store's compiled types and method tables (most of its
   bytes): carry them as blocks or derive them at install, measured on a live town. `slugTargets` scans every entry
   per `world-resolve`: index slugs.
6. **Host seams to close** (one commit each, deleting the old path):
   T29 the REPL's prose refusals (`unknown library pin`, `checkpoint was not issued by this process`) as classes and
   `http.py` matching the class; T32 `world-status.suspendedBytes {median}`; H2 `respond` with one payload per method
   (the `refused` and `inspected` ladders); H4 `reprogram {mode: "extend"}`; H5/H6 dispatch on `(method, argument)` and
   the `plan` wire names (with the kernel); H7/H8 root acts and powers as one table, settings through `settingsChange`;
   H10 `sealLibrary` reading `Ops.arrivals`; H11 `serve.c` saying root and the frame bound checked once; H12 `Limits`
   referencing `Bounds` (`maxTurnTicks` = `ticksMax`, `plainDepth` = `plainJsonDepth`, the 1400s); H13
   `compressedSize`; H14 the duplicates; H15 one list codec (`DataWire`); H16 reads of older journals; H18 a host `fit
   {form, fields}` that `Kind.makeUnder` calls.
7. **FEDERATION remainder** (host). `world-history` across worlds; the hand's SCRATCHES page (transport); a `Returned`
   carrying the target's receipt (World.obend, every pin moves; objects lane); `world-repl` of several modules.
8. **Block store and law atoms remainder** (host). Index sources, grants and slugs; CIDs as bytes; one record encoding;
   `serve --snapshot-every`; held worlds never closed; `world-inspect`'s `cites` per clause.
9. **Lifecycle** (host; FOUNDATION §2, §12): segmented journals and the 30-clock-day inactive-object archive are
   specified, not built; snapshots reclaim no journal or object capacity, retired names occupy the object table. Old
   ancestry lookup for evicted grants and ownerless legacy allocations is FOUNDATION §12's.
10. **Root** (host; decide). A `before`/`after` past `maxEntryBytes` by CID in `blocks`; a retry of a root act is a new
    `root:<n>`; `set pin` stores the pin alone; `as` runs the method as named; `root-edit` does not rewrite CIDs inside
    checkpoints and states; `openerActs`' interpret-quota exemption ignores `resident`; `applyRoot` program and law
    overrides bypass the behaviour counter.
11. **Smaller** (owner as named). `readerActions` compiles `actions` per read (host; not warmed); a `call` or `write` to
    an object created in the same turn is `unknownObject` (host). hob has no answer for "ask is not needed": decide.
    `hand.speak` casts one spell through `spell-parse` and reports a several-spell post's `{status: "spells"}` as an
    error (transport). `tests/test_pull_backups.py`'s `Retention` depends on the time of day (transport).
    `transport/hand.py` labels the rotated wants list "oldest first" (transport). Genesis's clapper ask names grow after
    hang exists, and the station register condition counts all register lines (deploy). The objects lane: fold
    `Card.Reply` into `Heard` and delete `Record.misfitted`, the room's `Super.misfitted`, the commonplace's
    `isNobody(state.policy)` refusal.
