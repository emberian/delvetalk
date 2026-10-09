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
pin; since `binaryPin` reads 1 MiB and only beside a snapshot, reopen is 0.10 s (full replay 0.16 s).
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
- **Snapshot.lean**: snapshot bytes, `binaryPin`, `openContent` (the snapshot-aware replay `openWorld` uses).
- **Session.lean** (194): the only IO. `Open {world, path, handle}`, `openWorld`, `durable`, `stepWorld`,
  `syncHandle` (extern, `spec/native/sync.c`). Journal lines are appended and fsynced before any reply.
  Durability is fsync, not a full barrier: an entry may be lost on power loss within the OS write-back
  window; the chain verifies on reopen so a torn tail is cut, never corrupted. `world-open {sync}` is
  `"fsync"` by default, `"full"` for the old F_FULLFSYNC barrier (macOS; it stalls every other writer
  on the disk), `"none"` (flush only) for test journals.

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
`world-inspect {principal, object}`, `world-library {principal, identity}` (reload the library path; a changed pin is
a journaled change judged by the world law), `world-interpretations`, `world-interpretation {id, reply}`.
`world-open` also takes `verify: true` and answers `snapshot {resumed, refused [{height, reason}]}`;
`world-open {sync: "none" | "fsync" | "full"}` picks how that process makes appends durable (default `"fsync"`,
never journaled, reported by `world-status` as `sync`; the old boolean is accepted for one release, false = none,
true = fsync); `tests/host.py` opens every test journal with `"none"`, deploy and hostd keep the default. `world-snapshot` writes a snapshot now (`{status: "snapshot", height}` or `{refused}`), journaling nothing.
`world-open` may also carry `clock` (the one principal that may `world-advance` and `world-posted`; transport
uses "transport") and `postQuota` (hourly posting cap, default 16, reported by `world-status`): the first open naming
either journals a `settings` entry, and a later open with other values is refused by name.
`world-posted {principal, uri, cid, object, slot?}` journals a `posted` entry (identity `posted:<uri>`) and indexes
`world.posts`; `world-addressee {parent}` answers `{status: "addressee", object, slot?}` or `{status: "unknown"}`.
`turn` is host-assigned on propose, amend and reprogram; a client-sent `turn` is a request error.
Every journaling op goes through `durable`: step, then `settleAll` (resume what the step released, then run
pending deliveries oldest first, each followed by another resume pass, up to `deliveriesPerSettle` 64; the reply
carries `resumed` and `delivered`), then append ALL new entries, one fsync. Nobody needs to call `world-deliver`;
it runs what a capped pass left. `world-open` itself never settles. `await` accepts `until` (absolute clock
height) instead of `patience`, and Plan `awaitUntil {slot, until}` carries it. A reply exists only after the bytes are durable.
Request errors (`Except.error`) journal nothing; refusals are receipts.

## 2. Journal entries

One JSON object per line. Common fields: `height`, `previous`, `hash`, `identity {principal, intent}`,
`roots [{object, version}]`, `turn`, `request` (digest), `outcome {tag, ...}`. Hash = SHA-256 of the
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
  callers [string], kinds [0|1|2]}]` (parallel to `edits`: the object that called the writing method, "" for the
  turn's own; kind 0 write, 1 reprogram, 2 amend; a reprogram or amend is an empty-edits step),
  reprograms?, amendments?, creates?}`.
  - `reprograms [{object, oldPin, newPin, source, migration, result}]` (result = new state Data).
  - `amendments [{object, old, new}]` (law texts).
  - `creates [{object, pin, sourcesSha256, read, chain, compile, seed, law}]`.
  Replay rebuilds a `Proposal` (writes from `writes`, programs/laws/creates/absent from the fields),
  checks `request == p.digest`, re-runs `judge`, and requires that `judged.reprograms`,
  `amendments`, `creates` equal the recorded JSON exactly and that each recorded write version equals
  the replayed new version. So admitted entries are re-judged, not trusted.
- **refused**: `{tag, class, clause?, object?, reason?}`. Classes (`refusalClasses`): staleRoot,
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
  `maxSuspended` 4096, `maxResumesPerCall` 1024.
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
3. **Context.** `contextData` is the single constructor: `{world, object, principal, caller, intent, height, inputOrigin}`;
   `height` is the height the turn read (a resumed turn keeps the one it started with).
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
   (identity `interpretation`/id, verdict `proposal {method, argument}` or `unclear {needs}`) and the settle pass resumes the turn.
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
   principal the whole entry, anyone else a refusal as `publicRefusal` (`{status: "refused", class, root}`, exactly)
   and other entries as chain fields, identity, turn, outcome tag, the roots and writes of objects the reader may
   view and an `elided` count (no result, offers, sends, sources, checkpoint). `world-history` takes a principal
   ("" = anonymous, public objects only), is `denied` for an object the reader cannot view, and projects each entry.
11. **publish.** `publish {page, section, body}` -> `published {post}` (post = hash of `["publish", principal,
   intent, ordinal]`; at most `publishesPerTurn` 4; a title or section with a line break or over 256 bytes is
   `refused {clause: title}`). The page is the object's: `page` "" means the object id. The admitted entry
   retains `publishes [{id, object, page, section, text}]` with the agentwiki text (`wiki: Title\n\nbody`, or
   `edit: Title › Section\n\nbody`); `world-offers` for the publisher (the clock principal, else "transport")
   adds `publications`. Transport posts the text, confirms with `world-posted {uri, cid, object}`, and routes a
   reply (`merge` from the page's owner) by `world-addressee` to the object's `receive` (bridge work).

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
   snapshot newest first check: CID over the stored bytes, edition, `binary` (= `binaryPin`, the CID of the
   executable's size and its first 1 MiB, computed once per process and only when a snapshot is read or
   written; Lean handles cannot seek, and reading the whole 127 MB file cost every open 0.45 s on hbox), height within the journal, `head` = the journal's hash at that height, the derived
   copies, each object's version and pin against what the entries record (`expectedObjects`), every law
   reading back from its text, and finally that every later entry replays on it. The first failure refuses
   the snapshot by name in the report and the next older is tried, then full replay. A forger who recomputes
   the CID and keeps versions and pins can change a state unnoticed by a plain open; `world-open {verify:
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
   extension at module level: the layer sees the code below as `Super` (the host adds
   `import ./<module below>.obend as Super` after the `edition` line unless present, so the layer's diagnostics
   are one line later than its author's), and `delegate` compiles each method from the highest layer that
   defines it, everything else from below (no late binding: a method below that calls another sees its own
   module's). A layer that declares `type State = Super.State` gets its methods in the method table (the
   compiler lists only `state: State` methods); the object's table is the layer's rows plus the rows below it
   does not override. The new pin is the CID of `["extend", old pin, source CID]`; the state type must be the
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
- **relevantBounds** (Ops): closes the variables a type reaches to a fixpoint (at most `bounds.length + 1`
  rounds; "type too deep to compare" if not reached; it used to stop after eight rounds and answer "same"). a package's `bounds` table includes entries for its own method row, so
  comparing whole tables says two identical state types differ as soon as any def is added. Compare
  `ty` plus only the bounds that `ty` transitively uses (`relevantBounds`). Reprogram depends on it.
- **conformsUnder bounds**: every conformance and `isDataUnder` call needs the packet's bounds
  (`Object.bounds`, `Compiled.bounds`); the bare `conforms` is only for closed non-recursive types.
- **Plan.obend wire shapes** (`world/lib/Plan.obend` is the contract): `write.edits` is a RECORD with one
  variant per state field (`keep`, `set {value}`, `add {delta}`; lists: `keep`, `append {item}`,
  `amend {index, change}`, `remove {index}`); `Reference {world, object}` with `world ""`; responses
  `viewed {version, state}` (full state), `denied`, `written`, `refused {clause}`, `returned {result}`,
  `delivery {id}`, `created {object}`, `reply {receipt}`, `timedOut`, `broken`, `reprogrammed {pin}`,
  `amended`. `respond` picks the first payload that conforms to the object's own Response type; an
  object whose Response sum lacks the label gets "response type cannot carry <label>". Text is `.label`.
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
4. **Snapshot verification by default.** A plain open trusts a snapshot whose CID, head, binary pin, derived
   copies, versions and pins check; only `verify: true` catches a consistently forged state. If snapshots ever
   leave the host's directory, journal the snapshot's CID (a `snapshot` entry) and check it on open.
5. **Pure methods.** A state-returning method and `render` still go through `Package.executeDataValues` (packet
   JSON); move them to `executeDataEntry` with `compiledMethod`'s held entry.
6. **Transport asks** (from host3, unchanged): `receive {text, post, slot?}` with a missing `slot`.

What was wrong in the previous version of this file: section 7 queued snapshots, section 13 and the kernel batch
as not started; section 5 said nothing of Data payloads (the one-variant unwrap in `mergeSeed` is gone).
