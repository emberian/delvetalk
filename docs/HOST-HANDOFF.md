# Host handoff (lane/host4: kernel integration, snapshots, FOUNDATION section 13)

For the lane that continues the host. The authority model (FOUNDATION section 11 rows 1 to 3) and
program reflection (row 5: inspect, check, the sealed library, interpret) are built; section 5 says how.
Everything is in `spec/Delvetalk/Host/`. Line numbers drift; grep the names.
Tests that pin behaviour: `tests/test_world.py`, `test_turn_world.py`,
`test_deliveries.py`, `test_reprogram.py`, `test_await.py`, `test_replay.py`, `test_authority.py`,
`test_reflection.py`, `test_grants.py`, `test_outbound.py`, `test_journal.py`, `test_workshop.py`,
`test_integration.py`.
`make check` runs everything in parallel (~2 min); `make smoke` the fast pair. Two wall-clock bounds
(`test_turn_world` 200 bumps under 5 s, `test_http` 200 turns under 10 s) are fsync-bound and can miss under a
loaded box; alone they take 3.3 s and pass. `test_snapshot`'s reopen under 1 s takes 0.2 to 0.4 s alone and
measured 1.08 s inside the parallel suite on hbox at load 30 while every open read the whole binary for its
pin; snapshots name no binary since host7's hash pass, and reopen is 0.10 s (full replay 0.16 s).
Build: `LEAN_NUM_THREADS=2 lake build 2>&1 | grep -v "^warning\|deprecated" | grep -A10 error`.
Run tests with `python3 -W error -m unittest tests.test_X` (the whole set takes ~3 min).

## 1. Module map

Import order: Store, Journal, Law, Ops, TurnLoop, Snapshot, Session; `PackageSession.lean`
imports Session and `PackageMain.lean` drives it.

- **Store.lean** (263): `Limits` namespace (all numbers), `Law` (= `List (String x LawExpr)`),
  `Compiled`, `Ledger`, `ReadPolicy`, `Program`, `Object`, `World`, `identityKey`. Pure data.
- **Journal.lean** (33): `bodyHash (body : Json) : String` (SHA-256 of `body.compress`; Lean orders
  object keys so bytes are canonical), `sealEntry (height previous) (fields) : Json` (adds `hash`),
  `verify (height : Nat) (previous : String) (entry : Json) : Except String Unit` (hash, height, chain).
- **Law.lean** (213): `Facts`, `Reading`, `denote`, `admits`, `refusedBy`. The evaluator of the law
  fragment; tests are `#guard`s at the bottom. The fragment syntax itself is
  `spec/bend/Compiler/ObjectiveBendLaw.lean` (host extensions there: `request.pin`, `request.kind`,
  text constants `REF == "text"` for subject/caller/pin).
- **Ops.lean** (1464): the pure world kernel. Edits, `Proposal`, `judge`, `commit`, `record`, `push`,
  creation (`compileObject`, `makeObject`, `buildObject`, `create`), program preparation, `replayEntry`,
  `replay`, `advance`, reads (`view`, `receipt`, `history`).
- **TurnLoop.lean** (1303): `world-turn` and everything that runs activities: the `M` monad,
  `runMethod`/`drive`/`awaitPlan`/`answer`, `finishTurn`, `runTurnWith`, `resumeOne`/`settle`
  (suspended turns), `deliverOne`/`deliver` (sends), `reprogramOp`, `amendOp`.
- **Snapshot.lean**: snapshot bytes, `openContent` (the snapshot-aware replay `openWorld` uses).
- **Session.lean** (194): the only IO. `Open {world, path, handle}`, `openWorld`, `durable`, `stepWorld`,
  `syncHandle` (extern, `spec/native/sync.c`). Journal lines are appended and fsynced before any reply.
  Durability is fsync, not a full barrier: an entry may be lost on power loss within the OS write-back
  window; the chain verifies on reopen so a torn tail is cut, never corrupted. `world-open {sync}` is
  `"fsync"` by default, `"full"` for the old F_FULLFSYNC barrier (macOS; it stalls every other writer
  on the disk), `"none"` (flush only) for test journals.

**Pins are sources (host6).** An object's pin is the CID of its sealed source closure: the artifact's
`sourcesSha256`, the Canonical CID of its modules in order (library modules included), so it depends on bytes and
never on the compiler. No packet digest is journaled (host7's hash pass): replay recompiles from the journaled
sources with the current compiler, requires the compile to succeed, the seed to conform and the recomputed source pin
to equal the recorded `pin`; `world-status.recompiledDifferently` (memory, per process, informational) counts objects
rebuilt after a snapshot resume whose packet differs from the one that snapshot cached for the same inputs
(`World.cachedPackets`, `noteRecompiled`). A `compiled {binary, packet}` field on an entry written before is ignored.
Field names: `created {pin, compile, seed, …}`, `creates[] {object, pin, …}`, `reprograms[] {object, oldPin, newPin,
…}`, `library {pin, …}`; `Object.pin`, `Object.packet` (memory); snapshot objects carry `pin` and `packet`; `inspected.pin`, `request.pin` in laws, receipts and projections are the
source pin. An extension's pin is the CID of `["extend", old pin, source CID]`, sources too. The host builds each
Context (and a law's Request) as the receiving code's own library declares it (`fitRecord`: the record type's
fields, in its order, through the packet's bounds), so a field added to the library later never breaks an object
compiled before it. `tests/fixtures/pins/artifacts.json` (kernel lane) still keys by module and entry and compares
packet digests; the shape the rule asks for keys each entry by its source pin and keeps the packet digest
informational.

**Slugs are names for people; CIDs are names for machines; a post carries slugs, never CIDs (host7).** A slug
(`Host/Slug.lean`: `ofCid`, `decode`) is the proquint of the first 32 bits of a CID's multihash digest, two
five-letter words (`lusab-babad`). Replies show every receipt with `slug` beside `hash` (`slugged`; the journal stores
only the hash), `world-inspect` shows `pinSlug`, a public refusal carries its receipt's `slug`. `world-resolve
{principal, slug}` (`resolveOp`, over `slugTargets`: every entry hash, and the pins and journal-named state CIDs of
objects the reader may view) answers `{status: "resolved", slug, kind: receipt | pin | state, cid, receipt?}` (the
receipt as `world-receipt` renders it to that reader), `{status: "ambiguous", matches, message}` when the slug names two
or more CIDs ("ambiguous: N matches; cite the object and version"), or `{status: "unknown", message}`. Tests:
`tests/test_slug.py` (a fixed slug, round trips, a pinned 32-bit collision of two states).

Signatures a newcomer calls (all pure unless noted):

```lean
def commit (w : World) (p : Proposal) (extra : List (String x Json) := [])
    (forced : Option Refusal := none)
    (onAdmit : List (String x Object) -> List (String x Json) := fun _ => []) : World x Json
def judge (w : World) (height : Nat) (p : Proposal) : Except Refusal Judged
def record (w : World) (entry : Json) (key : String) (touch : List String) : World   -- bookkeeping only
def push (w : World) (key : String) (fields : List (String x Json)) (touch : List String) : World x Json
def replay (content : String) : Except String World
def replayEntry (w : World) (entry : Json) : Except String World
def runTurnWith (w : World) (req : TurnRequest) (how : TurnMeta) : Except String (World x Json)
def runTurn (w : World) (req : TurnRequest) : Except String (World x Json)
partial def runMethod (depth : Nat) (id method : String) (argument : Data) (origin : String) : M Data
partial def drive (depth : Nat) (self : String) (compiled : Compiled)
    (outcome : Delvetalk.Turn.Outcome) (_n : Nat) : M Data
partial def answer (depth : Nat) (self : String) (bounds : DataBounds) (plan : Data)
    (responseType : Ty) : M Data
def finishTurn (w : World) (ctx : Ctx) (result : Except Abort Data) (st : TurnState)
    : Except String (World x Json)
def resumeOne (w : World) (sus : Json) (kind : Resume) : Except String (World x Json)
def settle (w : World) : Except String (World x Array Json)
def deliver (w : World) (limit : Nat) : Except String (World x Json)
def stepWorld (session : Session) (request : Json) : IO (Session x Except String Json)   -- IO
def durable (s : Open) (step : World -> Except String (World x Json)) : IO (Session x Except String Json)
abbrev M := ExceptT Abort (StateM TurnState)
```

Session ops (`stepWorld`): `world-open {path, library?, principal?, libraryLaw?}` (replay; with `library` it seals
that directory, journals it on first open or refuses by name if the bytes differ from the journal's pin), `world-create`, `world-turn`, `world-propose`,
`world-view {principal, object}`, `world-receipt {principal, identity, of?}`, `world-history {principal, object, after?, limit?}`,
`world-offers {principal, after?}`, `world-status`,
`world-deliver {limit}`, `world-pending`, `world-reprogram`, `world-amend`, `world-advance {height}`,
`world-inspect {principal, object}`, `world-state-cid {principal, object, version}`, `world-resolve {principal, slug}`, `world-fork {principal, height?, into}` (5.41), `world-check {principal, modules | source, entry}` (5.28), `world-library {principal, identity}` (reload the library path; a changed pin is
a journaled change judged by the world law), `world-interpretations`, `world-interpretation {id, reply}`.
`world-open` also takes `verify: true` and answers `snapshot {resumed, refused [{height, reason}]}`;
`world-open {sync: "none" | "fsync" | "full"}` picks how that process makes appends durable (default `"fsync"`,
never journaled, reported by `world-status` as `sync`; the old boolean is accepted for one release, false = none,
true = fsync); `tests/host.py` opens every test journal with `"none"`, deploy and hostd keep the default. `world-snapshot` writes a snapshot now (`{status: "snapshot", height}` or `{refused}`), journaling nothing.
`world-open` may also carry `clock` (the one principal that may `world-advance` and `world-posted`; transport
uses "transport") and `postQuota` (hourly posting cap, default 16, reported by `world-status`): the first open naming
either journals a `settings` entry, and a later open with other values is refused by name.
`world-open {opener}` records the world's opener in the same settings entry (only when named); the opener alone may
`world-create {…, owner}`. `world-principal {principal, did, handle}` (clock principal only) journals a `principal`
entry for the handle registry (5.22); `world-arrive {principal, did, handle}` also creates the newcomer's Avatar, Env and Wake (5.31).
`world-posted {principal, uri, cid, object, slot?, page?, section?}` (`uri` an `at://` post or a `zulip://<stream>/<topic>/<id>`
message of the playtest transport, `postSchemes`; another scheme is refused by name) journals a `posted` entry (identity `posted:<uri>`;
`page`/`section` when the post carried the object's publication, section "" for the whole page) and indexes
`world.posts` (`Post {object, slot, page, part, height}`; snapshots keep them); `world-addressee {parent}` answers
`{status: "addressee", object, slot?, page?, section?}` or `{status: "unknown"}`.
`turn` is host-assigned on propose, amend and reprogram; a client-sent `turn` is a request error.
Every journaling op goes through `durable`: step, then `settleAll` (resume what the step released, then run
pending deliveries oldest first, each followed by another resume pass, up to `deliveriesPerSettle` 64; the reply
carries `resumed` and `delivered`), then append ALL new entries, one fsync. Nobody needs to call `world-deliver`;
it runs what a capped pass left. `world-open` itself never settles. `await` accepts `until` (absolute clock
height) instead of `patience`, and Plan `awaitUntil {slot, until}` carries it. A reply exists only after the bytes are durable.
Request errors (`Except.error`) journal nothing; refusals are receipts.

## 2. Journal entries

One JSON object per line. Common fields: `height`, `previous`, `hash`, `identity {principal, intent}`,
`roots [{object, version}]` (the state at a version is named once, by the entry that wrote it: `writes[].cid`, or a
created seed; `world-state-cid {principal, object, version}` answers it to a reader who may view the object; a root
`cid` in an entry written before the hash pass is ignored), `turn`, `request` (digest), `outcome {tag, ...}`. Hash = SHA-256 of the
compressed entry without `hash`. Genesis `previous` is 64 zeros. `identityKey` = compressed
`[principal, intent]`; `world.receipts` maps it to the entry index (first wins, except that a suspension or a
transient refusal is replaced by the identity's next entry). Transient refusals (`transientClasses`: staleRoot,
budget, evaluation) are journaled but do not bind: `retained`/`retainedTurn` let a retry with the same identity run
and be judged again (whatever its request); admitted outcomes and every other refusal bind.

Sources by CID: compile inputs in `created.compile`, `creates[].compile` and suspended activities name each
module as `{name, cid}` (`sourceCid` for a bare source); the first entry that needs a source carries it in a
top-level `sources [{cid, source}]` field (checked against its CID on replay; `world.modules`). Objects keep
full inputs in memory (`expandInputs` on replay). Compiled packages are cached in memory by the digest of their
inputs (`world.builds`, `buildKey`, `maxBuilds` 1024), so creation and replay compile each distinct package once:
500 library Bells went from create 135 s / reopen 133 s / 3.14 MB to 4.3 s / 0.5 s / 0.82 MB. (The
coordinator asked for separate `module` entries; a field on the introducing entry keeps every height and
turn number unchanged and needs no ordering against judging.) Reprogram `source` fields are still verbatim.
Optional top-level fields, all inside the hash: `absent [id]` (objects required absent), `turnRequest`
(digest of the original turn request), `ticksUsed`, `ledger {depth, work, storage}`, `result` (Data wire),
`sends [{id,to,method,argument,ledger}]`, `delivery {id, from}`, `resumes` (hash of the suspension it
continues), `offers [{to, text}]` (the rendered offers, retained; see 5.10).

Outcomes:

- **created** (`world-create`): `{tag, object, pin, sourcesSha256, compile (inputs), seed (Data wire),
  read, chain}`. `roots []`, `turn 0`. Replay: `buildObject` recompiles, pin and sources hash must match,
  the amendment-clause dry run must pass at `height = entry height`, creator = identity principal.
- **admitted**: `{tag, writes [{object, version (new), edits [Data wire of Edits records],
  callers [string], kinds [0|1|2], cid?}]` (`cid`: the new state's, host7, 5.35) (parallel to `edits`: the object that called the writing method, "" for the
  turn's own; kind 0 write, 1 reprogram, 2 amend; a reprogram or amend is an empty-edits step),
  reprograms?, amendments?, creates?}`.
  - `reprograms [{object, oldPin, newPin, source, migration, result}]` (result = new state Data).
  - `amendments [{object, old, new}]` (law texts).
  - `creates [{object, pin, sourcesSha256, read, chain, compile, seed, law}]`.
  Replay rebuilds a `Proposal` (writes from `writes`, programs/laws/creates/absent from the fields),
  checks `request == p.digest`, re-runs `judge`, and requires that `judged.reprograms`,
  `amendments`, `creates` equal the recorded JSON exactly and that each recorded write version equals
  the replayed new version. So admitted entries are re-judged, not trusted.
- **refused**: `{tag, class, clause?, object?, reason?, expected?, root?}` (`expected`: 5.29, `root`: 5.33). Classes (`refusalClasses`): staleRoot,
  typeMismatch (conformance), capacity (byte or count limit), outOfRange (index past the end), lawRefused, unknownObject, duplicateIdentity (never journaled), evaluation,
  budget (reason = the exhausted machine resource: ticks, heap, stack, nodes, bytes),
  budgetExhausted (reason = exhausted ledger field), programRefused (clause = packageBytes, compile,
  stateType, migration, law syntax), requiredAbsence. Replay checks only that the class is known (and
  delivery/resume consistency); refusals are not re-judged.
- **suspended**: `{tag, slot {principal, intent}, deadline, activity {object, method, argument,
  checkpoint {packetSha256, tokens, digest}, roots, absent, writes, sends, creates, programs, laws, ticks,
  awaited, awaits, offers, violation?}}`. The entry also carries `request` = the turn digest, `ledger`,
  `ticksUsed`, `delivery?`, `resumes?` (if it re-suspends). Replay: `digest == tokensDigest tokens`
  (never trust the token), registers it in `world.suspended`.
- **principal** (`world-principal`): identity `{clock, "principal:<did>:<height>"}`, `{tag, did, handle}`; `record`
  indexes `World.handles` (so snapshots rebuild it); "" forgets a handle.
- **settings** may carry `opener`; **created** may carry `owner` (replay requires the opener's principal).
- **advanced**: identity `{clock, "advance:<to>"}`, `{tag, from, to}`. Replay: `from == w.clock && to > from`.

Cross-entry invariants (`checkDelivery`, `checkSends`, `checkResumes` in Ops):
- A `sends` id must equal `deliveryId principal intent ordinal` (SHA-256 of `[principal, intent, ordinal]`).
- An entry with `delivery` must consume exactly the pending delivery it names, under the sender's
  principal, `intent == id`; a `budgetExhausted` refusal must name a ledger field that is actually zero;
  a delivery with an exhausted ledger cannot have run. Skipped when `resumes` is present.
- An entry with `resumes` must name a waiting suspension of the same identity.
- `record` derives memory state from entries: `pending` (sends of admitted entries, minus consumed
  deliveries), `suspended` (add on `suspended`, remove on `resumes`), `clock` (on `advanced`), `touched`.

## 3. Turn state while running

`TurnState` lives in `M`; Abort is `request | evaluation | budget | suspend`.

- `roots : (id, version)` : set by `recordRoot` (runMethod on entry, a permitted `view`). Capacity
  `maxRoots`. Validated at commit by `judge` (stale), at resume by `resumeOne`.
- `absent : id list` : set by `create` (the id it needs free). `judge` throws staleRoot if one exists.
- `violation : Option id` : a `create` found its id taken; the turn is later journaled refused
  `requiredAbsence` naming it (the Plan is answered `refused {clause: "requiredAbsence"}` first).
- `writes : (id, List Written)` : `addWrite id caller step` (the running object only; any other target is answered
  `refused {clause: notSelf}` before it gets here), `ensureWrite id caller kind` (reprogram/amend, self only).
  `Written {caller, kind, edits}`; a Step is one Edits record.
- `checks` : `check` Plans run (at most `checksPerTurn`); the journal keeps the count.
- `programs` / `laws` : reprogram/amend requests; prepared programs are cached in `world.programs`.
- `sends : (to, method, argument, sender)` : `send` Plan (the sender is the running object, the delivered turn's `caller`); ids derive from ordinal at commit (`sendsJson`).
  `sendsPerTurn`, `maxPending` checked when the Plan is answered.
- `creates : (id, CreateRec)` : built in-turn by `buildCreated` (compile, evaluate `initial()`, overlay the
  partial seed with `mergeSeed`, `makeObject`), installed by `commit` via `Judged.creations`.
- `offers : List (to, text)` : rendered `offer` documents with their addressees; the journal retains them.
- `ticks` : remaining machine ticks (`spend`); `plans`, `awaited`, `awaits` : counters.
- Ledger : `Ctx.ledger` (object `chain` at start, or the delivery's inherited one). A send's ledger is
  `{depth-1, work - used, storage - bytes added}` (saturating), computed in `sendsJson` only for an
  admitted turn. Pending deliveries are `world.pending`.

End of a segment (`finishTurn`): `.suspend` -> a `suspended` entry; `.evaluation` -> refused `evaluation`;
`violation` -> refused `requiredAbsence`; `.ok` -> `commit` (judge + admitted entry + `onAdmit` sends).
`.request` errors throw (nothing journaled) except for a delivery or a resumed turn, which are refused.

## 4. Limits (Store.lean `Limits`)

- Ids and text: `maxObjectIdBytes` 128, `maxPrincipalBytes` 128, `maxIntentBytes` 256, `maxMethodBytes` 128.
- Per proposal/turn: `maxRoots` 64, `maxWrites` 64, `maxEditsPerWrite` 256 (also steps per object),
  `maxPlansPerTurn` 1024, `maxCallDepth` 8, `sendsPerTurn` 32, `createsPerTurn` 8, `awaitsPerTurn` 8.
- Data: `dataDepth` 8192 (decode nesting), `maxStateBytes` 256 KiB and `maxSeedBytes` 256 KiB
  (compressed `dataJson`), `maxObjects` 10000.
- Journal: `maxEntryBytes` 1 MiB (one line), `maxJournalEntries` 1,000,000, `maxJournalBytes` 256 MiB,
  `maxHistoryLimit` 100 (history/pending page size), `maxCheckpointBytes` 512 KiB.
- Ledger: `maxDepth` 100, `chainWork` 10,000,000 ticks, `chainStorage` 1 MiB. Creation may lower an
  object's `chain`, never raise it.
- Time/ticks: `maxTurnTicks` 1,000,000 (default and request ceiling), `maxPatience` 1,000,000 clock units.
- Delivery/suspension: `deliveriesPerCall` 16, `maxPending` 4096, `pendingActivitiesPerObject` 8,
  `pendingInterpretationsPerObject` 64 (counted apart from awaits), `maxSuspended` 4096, `maxResumesPerCall` 1024.
  A full count refuses the turn class `capacity`, reason the limit's name; `capacity` is transient.
- Principals: `maxHandleBytes` 256.
- Programs/laws: `maxPackageBytes` 32 KiB (reprogram), `maxLawBytes` 4096, `maxLawClauses` 16,
  `maxPreparedPrograms` 16 (memory cache), `maxCompiledPackets` 256 (memory cache), `maxReaders` 256.

## 5. The authority model and reflection, as built

1. **Write is self-only.** `answer` case `write` applies only to `self`; a Reference to another object is answered
   `refused {clause: notSelf}` in-turn. `reprogram` and `amend` of ANOTHER object are allowed: the proposer reads the
   target (a root) and the change is recorded with `callers = [proposing object]`, kind 1 or 2, so the target's own law
   judges it (a Forge/Workshop names itself in the target's law: `request.caller == "forge"`). Cross-object change is a `call`: the callee
   runs as its own `self`, so its writes are its own, judged by its own law. `judge` has no `unreadWrite`; a
   `world-propose` that writes an object it does not name as a root is a request error.
2. **Law facts.** `Facts {subject = principal, caller, height, turn, pin, kind, method}`; `method` is the method whose
   run made the change ("" for ops; journaled per change as `methods`). `request.subject in new.F` / `request.caller in
   new.F` is membership in a `List<String>` field (`LawExpr.member`, parsed in `spec/bend/Compiler/ObjectiveBendLaw.lean`,
   which the kernel lane owns: the host extensions there are `pin`, `kind`, `method`, text constants, `member`). `caller` is the object whose method
   wrote ("" for the turn's own method and for client proposals; for a delivered turn, the sending object).
   `judge` judges every distinct (caller, kind) of an object's changes, so a bundled reprogram does not skip kind 0.
   `new.F == request.subject` compares a text field; `appendOnly(F)` (new list = old list plus appended items, by canonical
   Data) and `unchanged(F)` are in `Law.lean`; syntax in `spec/bend/Compiler/ObjectiveBendLaw.lean`.
   The default law `owner: request.kind == 0 or request.subject == "<creator>"` therefore means: anyone may invoke my
   methods, only my creator may reprogram or amend me (documented at `defaultLaw`).
3. **Context.** `contextData` (Ops) is the single constructor, the Bend law's request included:
   `{world, object, principal, handle, caller, intent, height, clock, inputOrigin}`; `handle` is the registry's handle of
   the frame's subject ("" unknown), `height` the journal height the turn read, `clock` the world clock.
4. **Clauses.** `typeMismatch`, `capacity`, `outOfRange`, and the in-turn `notSelf`, `unknownObject`, `capacity`.
5. **Library.** `Library {pin, modules}` (Store.lean) sealed by `sealLibrary` (dependency order, then name; <= 256
   modules, 768 KiB). Objects' compile inputs carry `"library": pin` and only their own modules; `resolveInputs`
   prepends the imported library closure whenever it compiles (create, reprogram, method packets, replay), so every
   object stays compiled under the library it was created with (`world.libraries` by pin). A reprogram compiles against the
   world's current library. A library change is a `library` entry `{pin, previous, modules, law?}` judged by the
   world law (default `opener: request.subject == "<opening principal>"`, kind 1 facts); replay re-seals and re-judges.
6. **inspect / check.** `inspect` answers pin, law text and the entry module's source under the reader's `ReadPolicy`
   (`denied` otherwise). `check` runs `Package.checkPackage` over the library closure and answers
   `"<module>:<line>: <stage>: <message>"` strings; it installs nothing and the entry keeps a `checks` count.
7. **interpret.** The Plan suspends like `await` with outcome field `interpretation {id, object, policy, utterance, offers}`
   (id = hash of principal, intent, ordinal). `world-interpretations` lists the pending ones with the Policy object's state as
   `{model, system, examples}` and offers as plain JSON; `world-interpretation {id, reply}` journals an `interpreted` entry
   (identity `interpretation`/id, verdict `proposal {method, argument}`, `replied {text}` or `unclear {needs}`; 5.22) and the settle pass resumes the turn.
   A verdict is `proposal` only if the method exists, is one of the offered actions, its argument conforms to the method's input
   type and the object's Response can carry the proposal; a failed reply is `unclear`. Deadline is `interpretationPatience`
   (64 clock units) from the clock, resuming `timedOut`.

8. **Grants (delegation).** Plan `grant {to, object, method, until}` -> `granted {id}` (id = hash of
   `["grant", principal, intent, ordinal]`), `revoke {id}` -> `revoked {}`, and `callVia` / `sendVia`
   (`call`/`send` plus `via: String`; records have no optional fields, so they are their own constructors;
   the host also honours a `via` field on `call`/`send`). Only a direct turn's top frame may grant
   (`notDirect` for a callee, a delivered turn, or a frame already under a grant); the grantor is the
   turn's principal, the holder the running object. The grantee `to` is a principal or an object id and
   must be the frame's subject or the calling object at use. A grant stands while not revoked, the clock
   is `<= until`, and object and method match (`grantStands`). Under a grant the callee's frame runs with
   subject = grantor (context.principal, read authority, law `request.subject`) and caller = the calling
   object; its changes record `vias` and `methods` (parallel to `edits`, emitted only when non-empty) and
   `judge` re-checks the grant (`lawRefused noGrant` if it no longer stands). A `sendVia` journals
   `via` and `principal` (the grantor) on the send; the delivery runs as the grantor, carries
   `delivery.via`, and is refused `noGrant` (consumed) if the grant fell between send and delivery; a
   suspended turn whose staged sendVia lost its grant is refused at commit. Revocation: the holder object,
   or the grantor in an undelegated frame (`notGrantor` otherwise; `judge` requires the grantor's principal
   or the holder among the roots). Grants and revokes are outcome fields of an admitted entry
   (`grants [{id, grantor, holder, to, object, method, until}]`, `revokes [id]`), installed by
   `applyGrants`; `world.grants` holds them all (`maxGrants` 4096, `grantsPerTurn` 8). The frame lives in
   `TurnState.subject/method/via`, set and restored by `runMethod`; `principal` stays the identity's and
   derives send and grant ids. Tests: `tests/test_grants.py`.
9. **Listing and cards.** Plan `objects {prefix, after}` -> `listed {ids, more}` (`listIds`: ids the frame's subject
   may view, prefix match, strictly after `after` in byte order, sorted, `listPage` 64) and op
   `world-objects {principal, prefix?, after?}` -> `{status: "listed", ids, more}`. Plan `card {object}` ->
   `carded {document}`: `renderCard` runs the target's card on its committed state under the turn's ticks
   (records the target as a root; `denied` without read authority, `noCard` without a card method,
   `refused {clause: render}` if it fails). The card has a point of view: `renderFor(state, context)` when the
   method table lists it, else `render`, given the reader's Context when it takes two arguments (so the
   objects' rename of `renderFor` to `render` changes nothing here). The Context (`cardContext`): principal =
   the reader (the frame's subject), object = the target, caller = the asking object ("" for the op), intent
   and height of the current turn ("" and the world's height for the op), `inputOrigin.kind` "card". It runs the
   held entry (`executeDataEntry`). Op `world-card {principal, object}` -> `{status: "card", text, document}`
   (text by `Document.render`) as that principal sees it, journals nothing; the HTML object page asks it for
   the logged-in reader (its receive-turn fallback is gone).
10. **The outbound channel.** `offer {to, document}`: `to` "" is the frame's subject. An admitted entry retains
   `offers [{to, text}]`; `record` indexes them by addressee (`world.outbox`), and `world-offers {principal, after?}`
   answers `{status: "offers", offers [{height, ordinal, identity, text}], more}` (after = journal height,
   exclusive). A turn's reply carries only the offers addressed to its own principal (`turnReply`, derived from
   the entry, so a retry returns them identically); receipts in `delivered`, `resumed` and `world-deliver`'s
   `receipts` carry none, since the op's caller is not their addressee. Reads under authority: `world-receipt
   {principal, identity, of?}` reads identity (`of`, default the reader); `projectEntry` gives the identity's own
   principal the whole entry, anyone else a refusal as `publicRefusal` (`{status: "refused", class, root, reason?}`, root
   `{object, version?}`; 5.22)
   and other entries as chain fields, identity, turn, outcome tag, the roots and writes of objects the reader may
   view and an `elided` count (no result, offers, sends, sources, checkpoint). `world-history` takes a principal
   ("" = anonymous, public objects only), is `denied` for an object the reader cannot view, and projects each entry.
11. **publish.** `publish {page, section, body}` -> `published {post}` (post = hash of `["publish", principal,
   intent, ordinal]`; at most `publishesPerTurn` 4; a title or section with a line break or over 256 bytes is
   `refused {clause: title}`). The page is the object's: `page` "" means the object id. The admitted entry
   retains `publishes [{id, object, page, section, text}]` with the agentwiki text (`wiki: Title\n\nbody`, or
   `edit: Title › Section\n\nbody`); `world-offers` for the publisher (the clock principal, else "transport")
   adds `publications`. `world-publications {principal, after?}` (the publisher only; anyone else `denied`) answers
   `{status: "publications", publications [{height, ordinal, id, object, page, section, body, replyTo?}], more}`;
   `replyTo` is, for a section edit, the newest recorded post of that object's whole page (`pagePosts`). The
   bridge (`publication_drafts`, cursor `<state>/publications.after`) writes each as an outbox draft
   `<height>-pub-<id>.json` `{publication {id, height, object}, page, section, replyTo, text, posted: false}`,
   never posts it, and fills `replyTo` of an unposted section draft once the page post is recorded. `post.py
   --record` confirms as the clock principal ("transport") and adds `page`/`section` parsed from the posted text's
   `wiki:`/`edit:` header; a reply (`merge`) to that post routes by `world-addressee` to the object's
   `receive {text, post, slot}`.

12. **Kernel integration (host4).** An argument that does not conform to the method's input type
   (`argumentFits`: at `Data` well-formed, at a data type `conformsUnder` the packet's bounds; the kernel's
   own "turn refused: argument does not conform to its type" from `startActivity` is mapped the same way by
   `kernelRefusal`) refuses the turn with the journaled class `typeMismatch` (`object` = the turn's object;
   it binds, it is not transient); in a `call` the Plan is answered `refused {clause: typeMismatch}` and the
   callee does not run. `world-turn {…, profile: true}` sums `Delvetalk.Profile` over every activity
   segment the turn ran (start and each resume, nested calls included; pure methods have none) and returns it
   as `profile [{kind, steps, ticks}]`, heaviest first; it is not in the digest and never journaled, and a
   retry or a later resumption carries none. `Object.methods` is the artifact's method table (reprogram
   replaces it); `world-inspect` answers it raw as `methods` plus `forms`; the `inspect` Plan answers
   `inspected {pin, law, source, methods: Forms}` (Plan.obend line changed) where each form is
   `{card: object, action: method, fields}` for every method that takes a context and whose input is a
   record of `String` (text 0..`formTextMax` 1400), `Nat` (natural 0..`formNaturalMax`) or a closed sum of
   empty payloads (choice); a method with any other input field (a list, a nested record, a sum held as a
   bounds variable) is not listed. An object whose Response predates the field gets the old three-field form.
   `Object.predicate`/`predicateReads` record the artifact's `law: {present, reads}` for item 3(e).

13. **Snapshots (host4).** `durable` writes `<journal>.snapshot.<height>.cbor` after the fsync whenever the height is
   `Limits.snapshotEvery` (1000) past the last snapshot written or resumed from (`Open.snapshotAt`), so the
   height is the first durable boundary at or past each thousand; the reply that crossed it carries
   `snapshot {height}` (or `{refused}`; a failed snapshot refuses nothing). The newest three are kept. File:
   the DAG-CBOR map `{cid, body: bytes}`, `cid` the CID of the canonical body bytes (an independent Python
   encoder agrees, `tests/test_snapshot.py`). The body holds what replay pays for: objects (state, law text,
   version, read policy, ledger, compile inputs by CID), their types, method tables and law shapes by pin
   (`types`), libraries, grants (with `revoked`), posts, settings; plus `clock`, `pending` ids and
   `suspended` hashes as cross-checks. Everything `record` derives (receipts, touched, outbox, published,
   modules, pending, suspended, clock) is rebuilt by `recordAll`, a bookkeeping-only pass over the entries up
   to the height. `openContent`: parse and hash-walk every entry from genesis (`entriesOf`), then for each
   snapshot newest first check: CID over the stored bytes, edition (no binary pin since host7's hash pass: binary
   identity is deploy's smoke test's; an older snapshot's `binary` is ignored), height within the journal, `head` = the journal's hash at that height, the derived
   copies, each object's version and pin against what the entries record (`expectedObjects`), every law
   reading back from its text, and finally that every later entry replays on it. The first failure refuses
   the snapshot by name in the report and the next older is tried, then full replay. A forger who recomputes
   the CID and keeps versions and pins is caught by each state's `stateCid` against the journal (5.35); `world-open {verify:
   true}` replays everything and refuses, by name, each snapshot whose body differs from the replayed store's
   at its height ("it disagrees with replay at its height"). 500 creates of one package (hbox): reopen 0.10 s from
   the snapshot, 0.16 s by full replay (the build cache already makes that cheap; the snapshot pays off with
   many packages, reprograms and judged turns), snapshot ~4 KB per object type plus ~1 KB per object.

14. **Commutative edits (host4, FOUNDATION 13 row 1).** `judge` accepts a root `(id, seen)` whose object has moved
   (`seen < version now`; a future version stays stale) when every change of `id` in the proposal is a kind-0 write
   made only of `keep`, `add`, `append` (`EditKind.commutes`, `commutesAt`): `applyEdits` already runs on the
   current state, and the law judges old = now. The entry keeps the roots as read, so `writes[].version` is past
   `seen + 1`; replay applies the same rule. A moved root that is only read, or changed by anything else
   (set, amend, remove, reprogram, amend-law), is `staleRoot`. `resumeOne` refuses at resume only a moved root
   whose staged changes already include a non-commuting one; anything else resumes and `judge` decides at the
   end (so a strike that awaits and then adds commits after rains moved its bell). List items by bytes:
   `Entries.amendItem {item, change}` and `removeItem {item}` (Plan.obend; `amend`/`remove` with an `item`
   payload are accepted too) address the first item whose canonical DAG-CBOR equals `item`'s; none is the new
   refusal class `absentItem`. The index forms stay for one release (`world/objects` still use them).

15. **Grants completed (host4, FOUNDATION 13).** Plan `grantWith {to, object, method, until, fixed: Data, uses: Nat}`
   (Plan.obend) makes a grant that fixes part of the callee's argument and serves `uses` (>= 1; 0 is answered
   `refused {clause: uses}`); plain `grant` is unlimited and fixes nothing. `Grant.fixed` (Data wire) and
   `Grant.uses` (left) are in `Grant.json`. At each `callVia`/`sendVia`, `grantFor` checks the grant stands, the
   grantee, a use left (`grantSpent`), and `attenuate`s: a fixed record's fields are added to the caller's
   record, a field the caller gives with other canonical bytes is `grantConflict` (a non-record fixed value must
   be the whole argument, or the caller gives `{}`); the callee and its law see the merged argument, and a send
   journals it merged. A use is spent (`spendGrant`, `TurnState.spent`) only when the call runs or the send is
   staged; the admitted entry records `spent [{id, uses}]` (in the digest), `judge` re-checks the uses are still
   there (`lawRefused grantSpent`), `applyGrants` decrements, replay re-derives. `grantStands` ignores uses, so
   a delivery whose send spent the last use still runs. `world-revoke {principal, identity, grant}` is the
   grantor's own write to the grant outside any object (admitted entry with `revokes`; anyone else
   `lawRefused notGrantor`; an unknown grant is a request error).

16. **Objects-lane asks (host4).** `check` answers the kernel's dialect hint, when the diagnostic has one, as the
   next line `"<module>:<line>: hint: <text>"` after the refusal it explains. `writeOnce(F)` admits exactly one
   change of F away from its empty value, for every type (`Law.emptyValue`: 0, false, "", the empty list, a
   record of empty values; any other value is never empty), and a field missing from the old state fails
   closed; it used to admit any change of a text field.

17. **Held entries (host4).** `compiledMethod` (and `compileDef` for `law`/`lawReads`) compiles a definition with
   `compileEntryIn`: the package's closure is prepared once (`Package.prepareRequest`, cached in `world.requests`
   by the digest of the resolved inputs) and each definition compiled from it (`Package.compileEntryFrom`); the
   `Compiled` keeps the decoded, checked `CheckedEntry` (`Compiled.entry`), cached per `inputsKey/method`. Turns
   run `Turn.startEntry`/`Turn.resumeEntry`; pure definitions (the Bend law, `lawReads`, a handler's `handle`)
   run `Package.executeDataEntry` through `runPure`. Nothing on the turn path decodes, re-checks or re-hashes a
   packet. A full `compiled` cache is emptied and refilled rather than bypassed. Measured before the kernel's
   entries landed, with the host's own interim cache (since replaced by these): 200 Counter bumps 3.36 s ->
   1.42 s, a warm Garden `receive` 285 ms -> 21 ms (5,541 ticks either way); the first call of a method still
   compiles it.
18. **Extend, not replace (host4, FOUNDATION 13 row 3).** `world-reprogram {…, mode: "extend"}` (`mode` is
   `replace` by default; anything else is a request error) and Plan `extend {object, package, migration}`
   (Plan.obend; `reprogram` with a `mode: "extend"` field is honoured too) add the source as a module `Layer<n>`
   over the object's modules (`extendInputs`; `inputs.layers` counts them). Bend's `extension X(self, super)`
   composes records under `fix`; an object's package is a module of top-level methods, so the host realizes the
   extension at module level: it writes `layer over ./<module below>.obend` as the layer's first line (unless the
   author did; diagnostics are one line later than the author's), which imports the code below as `Super` and
   makes the modules a kernel layer stack (kernel5): every method resolves with late binding (Bell's own `rain`
   reply calls `render`, and a Louder layer's `render` is the one it reaches), and the artifact's method table lists
   the whole stack, top first (host7; `delegate` is gone). A layer built before held `import ./<below>.obend as
   Super` instead; replay re-derives the new form from the journaled source, and a snapshot holding the old form
   gets the line on load (`stackForm`). State types compare canonically (`canonicalTy`), since the stack's packet
   numbers its variables anew. Tests: `test_extend` (LateBinding: Louder through the `extend` Plan, and replay;
   an older-form snapshot). The new pin is the CID of `["extend", old pin, source CID]`; the state type must be the
   same or a migration named, as for replace; the target's law judges kind 1 as for any reprogram; the
   recorded reprogram carries `mode: "extend"` and `Proposal.layered` replays it. Snapshots keep whole any
   source no entry carries by CID (`knownByCid`; reprogrammed and extended objects' modules), which also fixed
   snapshots of reprogrammed objects.

19. **Supervisors (host4, FOUNDATION 13 row 5).** `Object.supervisor` (an object id, "" for none) is fixed at
   creation: `world-create {…, supervisor?}` (it must be an object; journaled as `supervisor` on the created
   outcome) or Plan `createUnder {package, seed, law, requireAbsent, supervisor: Reference}` (Plan.obend;
   `refused {clause: supervisor}` when it is not an object; recorded on the `creates[]` record). An activity of
   a supervised object *ends* `broken` when its turn is refused `evaluation` (including a delivered or resumed
   turn's request error), `budget` when a machine budget ran out, and `timedOut` when a segment resumed past its
   await's deadline ends in any way. `commit`'s `onEnd` then puts an `ended {id, to, method: "ended", argument,
   sender, ledger}` field in that entry (`endedField`; id = `endedId principal intent height`); `record` makes
   it a pending delivery whatever the entry's outcome, run as the activity's principal with the object as
   `caller`, argument `{receipt: Receipt, how}` (Plan.obend's `Receipt` of the entry itself), under the ledger
   the activity ran with, depth one less and work less what it spent, so a ring of supervisors stops when the
   depth runs out. A ledger refusal (`budgetExhausted`) tells nobody: it has no causal budget to tell with.
   Replay checks the id and that `to` is the object's supervisor (`checkEnded`). The supervisor declares
   `def ended(state, input: {receipt: Plans.Receipt, how: String}, context)`; another input is refused
   `typeMismatch` at delivery. Snapshots keep `supervisor`; `world-inspect` shows it.

20. **The two-tier law (host4).** For an object whose artifact has `law.present` (`Object.predicate`), `judge`
   runs, after the law text admits, the current code's `law(old, new, request)` once per distinct ordinary
   (kind 0) change (`bendLaw`), with `request = {context, method, argument: Data, kind, pin, reads}` (`Abi.Request`:
   context as the changing frame saw it with `inputOrigin.kind = "law"` and the world's height; `argument` the
   changing method's, journaled per change as `arguments` only for such objects; `reads` = `[{object, version,
   state}]` for the ids `lawReads()` returns, which `commit` adds to the proposal's roots before its digest
   (`withLawReads`) and `bendLaw` requires among them). It runs through `Run.evaluate` under
   `Bounds.lawTicks`: `admitted` admits, `refused {clause}` is `lawRefused clause`, exhaustion is class `budget`
   reason `law ticks` (transient), anything else fails closed as `lawRefused law`/`lawReads`. Reprograms and
   amendments are the text's alone (the metarule stays on the fragment, and a predicate cannot seal out the
   reprogramming hand either). `warmLaws` compiles `law`/`lawReads` into `world.compiled` before `judge`
   (commit and replay), since `judge` is pure. A package with `law.present` was never refused at creation.

21. **Handlers and judge (host4, FOUNDATION 13 row 4).** Plan `run {object, method, argument, handler}` runs the
   callee as `call` does (argument checked, depth counted; no grant), but every Plan the callee's own frame
   yields is first offered to the handler's pure `handle(state, plan[, context]) -> Handled<R>` (Plan.obend
   `sum Handled<R>: pass {} | answer {response: R}`): `answer` is the callee's response (it must conform to the
   callee's response type), `pass`, or a plan that does not conform to `handle`'s input type, goes to the host.
   The handler must be readable by the frame's subject (`refused {clause: handler}`) and is a root; its ticks
   come from the turn's. `TurnState.handlers` maps the frame depth to the handler; nested calls of the callee are
   not offered. Plan `judge {edits: E}` answers `judged {admitted, clause}`: `judge` (with the Bend laws warmed
   and law reads added) on the turn so far plus this write of the running object, committing nothing.

22. **lane/host6: the rehearsal's host findings.**
   - *Interpretation* (finding 2). `world-interpretations` sends as `policy.system` the Policy's pure
     `prompt(state, offers, utterance)` (compiled by name, `policyPrompt`; the method table does not list it), else
     its `system` field. A replied reply whose `json` is not `{method, argument}` and that carries `raw` resumes
     `replied {text}` (Plan.obend Response); an object whose Response cannot carry it hears `unclear`. `failed`
     resumes `unclear {needs: ["model: <reason>"]}`. Garden fits the text with its own Spell (objects lane).
   - *Silence* (finding 3). A turn that offers nothing has no `offers` field (`test_outbound` pins it).
   - *Refusals and own cards* (finding 7). `publicRefusal entry`: `{status, class, root: {object, version?}}`, plus `object` and `hint` for `unknownObject`; a refused
     turn reply carries it as `public` (anonymous reader). `ownCards` `env`/`wake` resolve to `<name>/<principal>`
     in `runTurn` and `world-card` (`resolveCard`); the bare ids are reserved.
   - *Handles* (finding 8). `World.handles`, `handleOf`, `principalOp`.
   - *Metarule* (finding 10). `amendable` answers "law does not admit an amendment by its proposer <p>: <name>:
     <expr>"; `isAmendmentRefusal`. `World.opener` from settings; `create` with `owner` builds with the owner as the
     metarule's and default law's principal.
   - *Capacity* (rerun findings). `mayWait … (interpreting := true)` counts interpretations apart;
     `transientClasses` includes `capacity`.
   - *Root CIDs.* Removed in host7's hash pass: roots are `{object, version}`; the state's CID lives on the write
     that made the version (`writes[].cid`, 5.35) and `world-state-cid` reads it (`stateCidAt`, `stateCidOp`).

23. **Reply-is-address (host6).** `world-turn {…, replyTo: <parent uri>}` (in the digest when given): when the parent
   is a post recorded for the turn's object, the entry journals `replyTo` and `World.replies` (built by `record`)
   maps the post to the first such turn's identity; replay checks the post is recorded for the entry's first root.
   Plan `awaitPost {post, patience}` / `awaitPostUntil {post, until}` waits for that turn's receipt (`reply`), or
   `timedOut`; the suspension records `post` instead of `slot`. `receive`'s `slot` is the host's
   (`receiveArgument`): dropped for an object declaring `{text, post}`, filled from the recorded post's slot
   (compressed JSON, "" for none) for one still declaring it.
24. **Minted child ids (host6).** A `create` whose `requireAbsent.object` is "" gets `<creator>/<package
   lowercased>/<n>` (`mintId`; a source package is `created`): the first `n` past the creator's `Object.minted`
   not held by an object, this turn's creates, or a suspended turn's `absent`. Every creation of an id of that
   shape, named or minted, raises its parent's counter (`noteMinted`, at commit, world-create and replay);
   snapshots keep `minted`. A named `requireAbsent` behaves as before.
25. **Checkpoint blocks (host6; cut and addressed anew in 5.34).** The kernel already collects before encoding (`Turn.conclude`:
   `checkpoint = collect (settle state)`); what remained was the program's own terms in every checkpoint. A
   suspended entry's `checkpoint.tokens` is journaled as `tokenTree {depth, roots}` over content-defined blocks
   (`cutBlocks`: windowed FNV cut, leaves 32..1024 tokens, inner 4..64 names, at most 16 roots), each block a
   top-level `blocks [{cid, items}]` item once per journal (`World.blocks`, derived by `record`);
   `expandCheckpoint` reassembles the tokens for replay's digest check and for resumption. Garden prose: the
   first suspension 272,621 bytes (was 225,719), the next 10,948.
26. **Stale resumptions (host6).** A resumed turn's own object (`Proposal.rebaseOwn`, set when the segment
   `resumes`; replay sets it from the entry's `resumes` and first root) may have moved while it waited: `judge` and
   `resumeOne`'s early check accept it when `rebasable` holds (every later change of it was an ordinary write, by
   `fieldsChangedSince` from the journal, and each of the turn's edits of it commutes or touches a field those left
   alone; a turn that only read it qualifies), and the writes apply to the current state. Otherwise the resumption is
   refused `staleRoot` (transient) and `resumeOne` re-runs the direct turn once, at once, from its journaled request
   (`TurnMeta.rerun`, journaled `rerun: true`; the reply carries `rerunOf` = the refusal's hash); a re-run's own
   stale resumption is final. Deliveries are not re-run.

27. **The binding fills the Context (host7).** Stateless `turn-start` on an entry whose last parameter is a Context
   (`isContextType`: a record, through the bounds, naming `principal` and `intent`, every field one `contextData` fills)
   and that is sent one argument short appends the Context itself (`withBindingContext`, Ops; called from
   `PackageSession.runHeld`): object, principal and intent from the binding, `inputOrigin {kind: "repl", command: <entry>}`,
   `handle`/`height`/`clock` from the world the process has open, else "" and 0, fitted to the entry's own Context
   type. A REPL caller passes only the method's own input. A request that sends the Context too is as before (for one
   release); `turn-resume` needs nothing (the checkpoint holds it). Tests: `test_turn.ContextTests`.

28. **Checks against the sealed library (host7).** `world-check {principal, modules | source, entry, limits?}` compiles the
   modules over the world's library (`overLibrary`: the library modules they import, in library order, then their own
   modules minus those that are the library's own bytes; another module of a library name is refused "shadows"), journals
   nothing, and answers `check-package`'s shape plus `library` (`checkModules`: `{status: "checked", artifact}` or
   `{status: "refused", diagnostic}` with module, span and hint). Any principal ("" anonymous) may ask; a package with
   laws compiles, as at `world-create`. Stateless `check-package` and `compile` take `library: <pin>` instead of the
   library's modules (`PackageSession.overLibrary`): resolved among the open world's libraries, then those this process
   sealed with `library-load {path}` (answers `{status: "library", pin, modules}`; at most 4 kept, newest first); an
   unknown pin is a request error naming it. The pure profile still refuses laws. `overLibrary` also lets a package be a
   library module named by itself (all own modules the library's: the last is the entry and stays); `attachLibrary` keeps
   it, which `world-arrive` (5.31) needs. Tests: `test_reflection.LibraryCheck`.

29. **A typeMismatch says what was expected (host7).** A turn (or delivery) refused `typeMismatch` because its argument
   does not fit the method's input journals `expected {method, type, form?}` on the refused outcome (`expectedInput`,
   `Refusal.expected`, `Abort.refused … expected`): `type` is the input as the artifact's method table records it
   (resolved, readable alone), else the compiled domain's `typeJson`; `form` is the card form `methodForms` derives for
   the method (plain JSON: `{card, action, fields [{name, kind {tag, min, max | options}}]}`) when it has one. The
   receipt carries it whole for the turn's own principal; the public projection does not. A `call` Plan is still answered
   `refused {clause: typeMismatch}`. The package loader's "import must name an earlier supplied module" now ends
   `: <path>` (`Package.modulesAndAsts`, a one-line edit in the kernel's file). Tests: `test_integration.Integration`.

30. **Another object's law is asked in the turn (host7).** A `reprogram`/`extend` or `amend` Plan naming an object other
   than the running one records the target as a root and dry-runs that change alone through `judge` (`dryChange`: the
   target's law text with kind 1 or 2, `request.caller` = the proposer, the frame's subject or grantor; a reprogram's
   compile, migration and state type; an amendment's syntax and metarule), at the version read. A refusal is answered
   `refused {clause}` (the class when there is no clause; the metarule's message as the clause) and nothing is staged, so
   the proposer commits what it says about the refusal and never offers "Reprogrammed X" in a turn the target's law
   would refuse. The commit still judges the whole turn (the dry run cannot see a change the same turn makes later). A
   change of the running object itself is judged only at the commit, as before. Tests: `test_reflection.ReprogramAnother`,
   `test_workshop.Workshop`, `test_extend.Extend`.

31. **Arrival (host7).** `world-arrive {principal, did, handle}` (`arriveOp`; the clock principal only, the world must
   name an opener and have a library) records the handle as `world-principal` does, then creates each of `arrivals did`
   that is absent: `<did>` from the library module `Avatar`, `env/<did>` from `Env`, `wake/<did>` from `Wake`. Each is
   `create` with principal = the opener, identity `arrive:<id>`, `owner: did`, modules = that one library module (the
   entry stays, 5.28), and a partial seed naming, of `owner` (the DID), `handle` and `env` (Reference to `env/<did>`),
   the fields the package's `initial()` state has. So the journal holds ordinary `created` entries (owner checked
   against the opener on replay) and a `principal` entry; nothing new replays. Idempotent: a repeat answers
   `{status: "arrived", did, handle, created: []}` with no entry; a new handle is one `principal` entry. The reply
   carries `created [{object, height}]` and `principal` (the principal entry, when one was written). A missing library
   module is a request error naming it, and nothing is journaled (the step is one durable write). GENESIS.md says when
   transport calls it. Tests: `tests/test_arrive.py` (a library of world/lib plus Avatar, Env, Wake and Place).

32. **Law readings in refusals (host7).** `Object.readings` holds the artifact's `laws[]` readings (`artifactReadings`,
   empty ones dropped) for the clauses that are still the package's: `makeObject` keeps those whose clause the effective
   law (the package's, or a law text given at creation) leaves equal; an amendment keeps those whose clause it leaves
   equal (by parsed `LawExpr`); a reprogram keeps them (the law is not code). Snapshots carry `readings` only when non-empty.
   A refusal by a text-law clause with a reading journals `reason: "refused <name>: <reading>"` (`readingOf`), and
   `publicRefusal` shows a `lawRefused` outcome's `reason` (the package's public text, never state), so the receipt, the
   turn reply's `public` and other readers' projections say it. Bend-law (`law(old, new, request)`) clauses and the
   metarule have no readings. Tests: `test_law.Readings`.

33. **A requiredAbsence names its root (host7, rehearsal run 6 finding 1).** The object whose `create` found the id taken
   (`TurnState.violator`, kept through suspensions as the activity's `violator`) is journaled as the refused outcome's
   `root` beside `object` (the taken id); `Refusal.root`. `publicRefusal` builds its `root {object, version}` from
   `outcome.root` when present (the creator at the version the turn read it) and adds `object` (the taken id): a second
   cistern reads `{class: requiredAbsence, root: {object: garden, version}, object: garden/cistern}`. Tests:
   `test_hub` (the cistern pair).

34. **Suspensions journal only what changed (host7, rehearsal run 6 finding 5; revised at foundation 6b928f6).** Checkpoint
   tokens are journaled as a `tokenTree {depth, roots}` of content-defined blocks (`cutBlocks`: leaves of 32..256 tokens,
   a token of 256 bytes or more a leaf of its own; inner nodes 2..16 names), each block once per journal; an
   interpretation's `offers` are a one-item block named by CID (`offersBlock`, `compactInterpretation`,
   `expandInterpretation`; `interpretationOf w s` restores them). With the kernel's checkpoint v2 and canonical cell
   order, measured on hbox (rehearsal journal, 132 directory suspensions; `tests/test_suspension_size.py`):

   | | rehearsal median / total | one speaker median | nine speakers median |
   | --- | --- | --- | --- |
   | v2, blocks and offers block (kept) | 9,392 B / 1.71 MB | 5,549 B | 9,797 B |
   | v2, offers block, no checkpoint blocks | 109,972 B / 14.6 MB | 48,221 B | 48,404 B |
   | v2 alone | 119,119 B / 15.8 MB | 49,961 B | 50,144 B |

   v2 alone is about 12x the combined result, so the block scheme stays. Deleted as inert on v2: `Host/Relative.lean`
   (relative heap addresses; it could not decode v2 and journaled plain), the argument/utterance leaf marking (v2 has no
   `{"s"}` tokens), and the utterance block (the utterance is inline again). Replay still reads host6 blocks and the
   `utteranceBlock` of host7 entries; a `tokenTree.relative` checkpoint (host7 builds 0b3363c..6b928f6 only, no
   deployed journal) is refused by name. Before host7 on v1 the rehearsal median was 51,858 B (5.94 MB).

35. **Snapshots verified by default (host7, §7 item 4).** Each snapshot object carries `stateCid` (`stateCid`, the CID roots
   use), and `install` refuses "the state of X is not its CID's" when the stored state does not hash to it, or "object X
   carries no state CID" (a snapshot written before host7: refused once, the open replays and writes a new one). Since
   a forger can recompute both, the CID is also checked against the journal: an admitted write now journals the new
   state's `cid` beside its `version` (`writes[].cid`, checked on replay when present), and `resume` compares each
   object with `anchoredStates` (a created or child seed, or a write's `cid`): "the state of X is not the one the journal commits to at version V". No replay, one hash per object
   and per anchor. An object no entry anchors at its version (only pre-host7 writes, never read since) is checked
   against its own CID only; `verify: true` still replays everything. Tests: `test_snapshot` (stale CID, consistent
   forgery).

36. **Pure methods on held entries (host7, §7 item 5).** A method returning the new state runs `Package.executeDataEntry`
   on `compiledMethod`'s held `CheckedEntry` (`entryOf`), as cards do; a reprogram's migration is held too
   (`CheckedEntry.ofPacket` once in `prepareProgram`, `executeDataEntry` in `judge`, the packet path kept for a
   `Compiled` without an entry). Only `initial()` at creation still runs from the packet (once per package). Measured on
   hbox, before and after interleaved, three runs each (`test_turn_world.Maximum`): 200 pure bumps of a one-field
   counter 0.04-0.05 s -> 0.03-0.04 s; 200 pure bumps whose method renders a Document (a larger packet) 0.06-0.07 s ->
   0.03-0.04 s; 200 activity bumps 0.17 s either way (already held). A first measurement of 0.45 s / 0.15 s was the
   box's load (about 9.5), not the code.

37. **The interpretation's model (host7).** `Plan.interpret` carries `model` (Plan.obend: "" for the policy's own; a card's
   second attempt names the Policy's `escalate`). `interpretPlan` journals it on the suspension's `interpretation` when
   non-empty (at most 128 bytes), and `interpretationsReply` puts it in the pending item's `policy.model` in place of the
   Policy's, so transport calls that model. Test: `test_interpret_text` (the second attempt shows `claude-opus`).

38. **Law text takes readings (host7).** `parseLawTextReadings` reads the compiler's grammar, `law NAME: EXPR` or
   `law NAME "reading": EXPR` (the reading a JSON string literal, so it may hold `:`), for `world-amend`, the `amend`
   Plan, a create's law text and snapshots alike (`parseLawText` is its law half). The law text is kept as given (readings
   included), and an amendment's readings replace the object's for those clauses; a clause it leaves as it was without a
   reading keeps the old one (5.32). A malformed reading is `law syntax`. Tests: `test_law.Readings`.

39. **Offers name the turn they answer (host7, rehearsal run 7 finding 1).** `world-offers` gives each offer
   `from {post, principal, intent}` (`originOf`): the entry's own identity, or for a delivered turn the direct turn it
   descends from, followed through `delivery.from` and `world.receipts` up to the ledger depth; `post` is that turn's
   `replyTo` when it answered a recorded post, else its intent (the bridge's identity for an observed post). A reply a
   bell handed to the directory by `send` is drafted against the post the author replied to. Tests:
   `test_hub.HandedToTheDirectory`, `test_bridge` (end to end, no longer an expected failure).

40. **viewData and viewDataField (host7).** Plan `viewData {object}` -> `viewedData {version, state: Data}` and
   `viewDataField {object, field}` -> `viewedField {version, value: Data}` (Plan.obend, appended at the end of `Plan`
   and `Response` so the existing constructors keep their order): another object's state, or one top-level field of
   it, as `Data` the reader may pass along or hand to a Plan but not take apart (`view` answers in the reader's own
   state type, so a Bell could not view the directory). Read authority (`denied` otherwise) and the root as for
   `view`; a field the state lacks is `refused {clause: field}`. The Plan.obend change moved every source pin, so
   `tests/fixtures/pins/artifacts.json` is re-recorded (no entry stopped compiling); objects already created keep the
   library they were compiled under. Tests: `tests/test_view_data.py` (the directory has no `words` field; `words` is a
   def, so the test reads a fixture object's `words` and `greeted` fields).

41. **Fork a world (host7, FOUNDATION 15).** `world-fork {principal, height?, into}` (`Session.forkWorld`; `into` must not
   exist) writes a new journal whose one entry is a `forked` genesis (`Snapshot.forkGenesis`): the store at `height`
   (default the head; an earlier height replays the entries up to it) as a snapshot body with whole sources, only the
   objects `principal` may view (their grants, pending deliveries, and suspended activities with checkpoints and offers
   written out whole), the handle registry, `omitted [ids]`, and `forkedFrom {world (the journal path), height, cid}`.
   The fork's opener, clock principal and library-law principal are `principal`. Its `previous` is `cid`, the forked
   world's entry at that height: `entriesOf` lets height 1 chain there only when the entry is `forked` and names that
   cid. Every replay (`replayAll`, `verify`, snapshot `resume` through `startOf`/`installFork`) starts from the
   installed genesis; `expectedObjects` and `anchoredStates` read its objects. `world-status` reports `forkedFrom`.
   Nothing is journaled in the forked world. Answers `{status: "forked", into, forkedFrom, carried, omitted}`. hostd
   exposes it as a heap op later (transport). Tests: `tests/test_fork.py` (a planting in the fork leaves the shared
   world unchanged, replay and a snapshot of the fork, an earlier height, a carried suspended reading settles in the
   fork only, a private object omitted for a stranger).

42. **The repository façade's reads (host7; docs/REPO.md "Host ops").** One public reader: every read op takes its
   principal through `readerOf`, which accepts 1..128 bytes, `anonymous` or "", the last two read as "" (public objects
   only); `world-objects`, `world-view`, `world-inspect`, `world-card`, `world-offers`, `world-check`, `world-state-cid`
   and `world-resolve` used to refuse "". `world-entry {principal, hash, bytes?}` (`entryOp`) answers `{status: "receipt",
   receipt}` as `projectEntry` shows it to the reader, plus `bytes` (hex of the entry's canonical DAG-CBOR without
   `hash`, whose CID is the hash) only for the identity's own principal; `unknown` otherwise. `world-entries {principal,
   after?, before?, reverse?, limit?}` (`entriesOp`) pages every entry by height (`pageByHeight`: ascending after
   `after`, or descending below `before` with `reverse`; `limit` 1..100). Test: `tests/test_reads.py`.

## 6. Gotchas

- **annotateData** (`spec/Delvetalk/Turn.lean`, mine): a state or argument containing a sum value
  (a `List` field) cannot be applied as an untyped `inject`; `startActivity` annotates each injection from
  the entry's arrow domain and the packet bounds. If you add a new argument that is a sum, it goes
  through this too. Responses resumed via `resumeActivity` are not re-annotated (checked by
  `conformsUnder`).
- **No silent defaults** (§11 row 11): optional request fields go through `optText`/`optNat`, which refuse a
  present but malformed value by name (turn `limits` and `limits.ticks`, `world-deliver.limit` 1..16,
  `world-history` `after`/`limit` 1..100, `world-offers.after`, `world-objects` `prefix`/`after`,
  `world-reprogram.migration`, the clock principal of `world-advance`).
- **canonicalTy** (Ops): two state types are the same when their canonical forms agree: variables renamed in order of
  first use, a bound one's body written where first met (at most 4096 steps, else "type too deep to compare"). A
  package's `bounds` table has entries for its own method rows, and a layer stack's packet numbers variables anew, so
  neither whole tables nor raw `Ty` equality decide it. Reprogram and extend depend on it.
- **conformsUnder bounds**: every conformance and `isDataUnder` call needs the packet's bounds
  (`Object.bounds`, `Compiled.bounds`); the bare `conforms` is only for closed non-recursive types.
- **Plan.obend wire shapes** (`world/lib/Plan.obend` is the contract): `write.edits` is a RECORD with one
  variant per state field (`keep`, `set {value}`, `add {delta}`; lists: `keep`, `append {item}`,
  `amend {index, change}`, `remove {index}`); `Reference {world, object}` with `world ""`; responses
  `viewed {version, state}` (full state), `denied`, `written`, `refused {clause}`, `returned {result}`,
  `delivery {id}`, `created {object}`, `reply {receipt}`, `timedOut`, `broken`, `reprogrammed {pin}`,
  `amended`. `respond` picks the first payload that conforms to the object's own Response type; an
  object whose Response sum lacks the label gets "response type cannot carry <label>". Text is `.label`.
- **world-create seeds** are laid over `initial()` like the create Plan's (`mergeSeed`, Ops): a record of some fields,
  `{}` for `initial()` itself; a field the state lacks is `typeMismatch: …`. The created entry journals the whole state.
  A seed that does not set a text `owner` field gets the named `owner`, else the creating principal (`withOwner`; the
  create Plan too), before the law's dry run.
- **create semantics**: `package` is a module NAME in the creator's sealed chain (Garden says "Bell"), or
  source starting `edition`; `law` is only used if it starts `law `; the seed is a PARTIAL record
  overlaid on `initial()` (a variant wrapper is unwrapped). Full-conforming seeds pass as is.
- **Hand-built Contexts in tests** must carry caller, intent and height or the method does not type.
- **Names and keywords**: `meta`, `from`, `seal` are Lean keywords (use `how`, `sender`, `sealEntry`).
  Structure-instance continuation lines must be indented past the first field, or use the
  one-field-per-line form; `{ principal, x := ...}` mixing abbreviations and `:=` failed to parse.
- **Suspension identity**: a suspended identity has a `suspended` entry; `retained` ignores it so the
  final commit can use the same identity, and `record` lets the final entry replace the receipt.
  Await inside a `call` is refused; only the top activity checkpoints.
- **Settling**: resumption runs inside `durable`, after the triggering op, and appends to the same
  write. A resumed turn that re-suspends gets a new entry with `resumes` = the old hash.
- **Deliveries and work**: work is charged after the fact (a turn may overshoot the chain's `work` by at
  most one turn); `budgetExhausted` requires a ledger field to be exactly zero.
- **Replay recompile cost**: `world-open` compiles each distinct package once (`world.builds`) and each
  reprogram record, and re-runs `judge`. Method packets are
  compiled lazily and cached in memory only. 1000 plain proposals replay in ~0.08 s.
- **fsync**: `Handle.flush` is not durable. `spec/native/sync.c` does `fflush` + `fsync`, or with `sync: "full"`
  `fcntl(F_FULLFSYNC)` (macOS); the full barrier made 1000 proposals cost 5 to 7 s (was 0.1 s) and 200 bumps ~3 s,
  and hammered the disk for every other user of the box, so it is no longer the default. One sync per
  `durable` call (not per entry). The build needs `lakefile.lean` (the TOML cannot declare `extern_lib`).
- **Journal lock**: `openWorld` takes an exclusive `flock` on the journal handle (`IO.FS.Handle.tryLock`, the
  runtime's flock; no second C extern was needed) and refuses "journal is open in another process"; the lock lives
  as long as the session's handle, so opening another path releases it. Re-opening the same path in the same
  process reuses the held handle. `world-status` reports `locked: true`.
- **1Password**: `git commit` can fail with "1Password: failed to fill whole buffer"; make the commit
  unsigned (`git -c commit.gpgsign=false commit ...`), which the owner's notes allow for unattended work.
- **Tests**: never run an unfiltered package suite on a loop; `tests.test_replay` and `test_await` each
  take ~12 to 40 s because every `world-create` compiles. `python3 -W error` turns leaked subprocess
  warnings into failures; close hosts in `tearDown`.
- **Not done**: `world-reprogram`/`amend` are gated only by the object's law;
  foreign worlds (`Reference.world != ""`) are always refused.

## 7. Where lane/host4 stopped, and the queue

lane/host4 is based on foundation a5287f4 and has merged foundation a08cb38 (objects2) and 81ea9ec (kernel2).
Done here, each with tests (`test_integration`, `test_snapshot`, `test_commute`, `test_grants` Attenuation,
`test_extend`, `test_supervisors`, `test_law`, `test_handlers`): the kernel batch (typeMismatch, profiles, methods
as forms), snapshots, all of FOUNDATION section 13's host items (commutative edits and item-addressed entries,
attenuated and counted grants with `world-revoke`, extension layers, supervisors, the two-tier law, `run` and
`judge`), the objects lane's asks (the check hint, `writeOnce` for every type), held entries on the turn path,
`sync: false`, and the one-variant seed unwrap deleted (`mergeSeed`: payloads are Data). Build and test on hbox
(`~/scratch/dt-host4`, `swarm-build lake build`; the full suite there is about 65 s).

Queued, none started:

1. **Late binding across layers.** `delegate` resolves a method to the highest layer defining it, but a method
   below calling another sees its own module's: real open recursion needs the kernel's `extension`/`fix` over a
   record of methods, i.e. packages written as a methods record. Decide with the kernel and objects lanes.
2. **Forms for every input.** `methodForms` lists only methods whose input is text, naturals and closed sums of
   empty payloads; a sum held as a bounds variable (most declared sums) has no form yet. Resolve variables
   through the packet bounds (the artifact's `type` table) or have the kernel inline them in the method table.
3. **Handlers for nested frames and activities.** `run` offers only the callee's own frame's plans to a pure
   `handle`; an activity handler (a card that asks before answering) and handlers over the callee's own calls
   are open.
4. ~~Snapshot verification by default.~~ Done in host7 (5.35).
5. ~~Pure methods.~~ Done in host7 (5.36).

lane/host5 (based on foundation 7d90f1b) did: journal durability modes (`sync: "none" | "fsync" | "full"`, default
fsync); cards with a point of view (5.9); `publish` end to end (5.11: `world-publications`, page-aware `posted`, the
bridge's publication drafts, `post.py --record` as the clock principal); and closed the transport ask: `receive` takes
exactly `{text, post, slot}`, the bridge and the HTML front always send all three, nothing in Host or transport
tolerates two fields (a missing or forged field is refused `typeMismatch`, `tests/test_receive.py`).
Still open from transport: `post.py --slot` passes text while `world-posted` takes a slot `{principal, intent}`,
so `--record --slot` is refused by the host; no object reads `slot` or acts on `merge` yet (objects lane).

lane/host6 (based on foundation 8d922a2, merged e240d41) did 5.22: the rehearsal's host findings 2, 3, 7, 8, 10,
the interpretation capacity and transient `capacity`, root CIDs, and `Context.clock`. Still open from section 7's
queue: items 1 to 5 above, unchanged. Asks for other lanes: transport should send the utterance only (the system text
now holds lexicon, examples, forms and the utterance), call `world-principal` at each author's first post, and open
with `opener`; `transport/model.py`'s comment ("the host fits raw") is now the object's fitting; Env.obend's comment
quotes the old metarule message.

lane/host7 (based on foundation 4068305) did, one commit each: the binding fills a REPL turn's Context (5.27);
`world-check`, `library: <pin>` and `library-load` (5.28); `typeMismatch` carries `expected` (5.29);
another object's reprogram or amendment is dry-run against its law in the turn (5.30); `world-arrive` (5.31); law readings in refusals (5.32);
from rehearsal run 6: a `requiredAbsence` names its root (5.33); suspensions journal only what changed (5.34).
Section 7's queue items 1 to 5 above are unchanged. Asks it leaves for other lanes: transport (hostd) should send
`library-load {path}` to its stateless process at spawn and the HTTP front `library: <pin>` (the pin `world-open`
answers) instead of reading world/lib (5.28), and the bridge should call `world-arrive`, not `world-principal`, at a
principal's first post (5.31); objects/deploy: the sealed library must hold Avatar, Env, Wake and Place for
`world-arrive` to make anything (world/lib does not); api: AGENTS-API step 12 may drop "pass its Context as the last
argument" (5.27); kernel: a collector that orders cells so a walked list's materialized prefix does not renumber the
rest of the heap would shrink a speaker's first reading further (5.34). `tests/test_artifact_pins` fails at base
4068305 (world/ moved after the fixture was recorded; foundation re-recorded it since); no host change touches it.

What was wrong in the previous version of this file: section 7 queued snapshots, section 13 and the kernel batch
as not started; section 5 said nothing of Data payloads (the one-variant unwrap in `mergeSeed` is gone).
