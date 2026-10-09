# Host handoff (lane/host2, after the authority model and program reflection)

For the lane that continues the host. The authority model (FOUNDATION section 11 rows 1 to 3) and
program reflection (row 5: inspect, check, the sealed library, interpret) are built; section 5 says how.
Everything is in `spec/Delvetalk/Host/`. Line numbers drift; grep the names.
Tests that pin behaviour: `tests/test_world.py`, `test_turn_world.py`,
`test_deliveries.py`, `test_reprogram.py`, `test_await.py`, `test_replay.py`, `test_authority.py`,
`test_reflection.py`.
Build: `LEAN_NUM_THREADS=2 lake build 2>&1 | grep -v "^warning\|deprecated" | grep -A10 error`.
Run tests with `python3 -W error -m unittest tests.test_X` (the whole set takes ~3 min).

## 1. Module map

Import order: Store, Journal, Law, Ops, TurnLoop, Session; `PackageSession.lean`
imports Session and `PackageMain.lean` drives it.

- **Store.lean** (172): `Limits` namespace (all numbers), `Law` (= `List (String x LawExpr)`),
  `Compiled`, `Ledger`, `ReadPolicy`, `Program`, `Object`, `World`, `identityKey`. Pure data.
- **Journal.lean** (33): `bodyHash (body : Json) : String` (SHA-256 of `body.compress`; Lean orders
  object keys so bytes are canonical), `sealEntry (height previous) (fields) : Json` (adds `hash`),
  `verify (height : Nat) (previous : String) (entry : Json) : Except String Unit` (hash, height, chain).
- **Law.lean** (142): `Facts`, `Reading`, `denote`, `admits`, `refusedBy`. The evaluator of the law
  fragment; tests are `#guard`s at the bottom. The fragment syntax itself is
  `spec/bend/Compiler/ObjectiveBendLaw.lean` (host extensions there: `request.pin`, `request.kind`,
  text constants `REF == "text"` for subject/caller/pin).
- **Ops.lean** (807): the pure world kernel. Edits, `Proposal`, `judge`, `commit`, `record`, `push`,
  creation (`compileObject`, `makeObject`, `buildObject`, `create`), program preparation, `replayEntry`,
  `replay`, `advance`, reads (`view`, `receipt`, `history`).
- **TurnLoop.lean** (817): `world-turn` and everything that runs activities: the `M` monad,
  `runMethod`/`drive`/`awaitPlan`/`answer`, `finishTurn`, `runTurnWith`, `resumeOne`/`settle`
  (suspended turns), `deliverOne`/`deliver` (sends), `reprogramOp`, `amendOp`.
- **Session.lean** (100): the only IO. `Open {world, path, handle}`, `openWorld`, `durable`, `stepWorld`,
  `syncHandle` (extern, `spec/native/sync.c`). Journal lines are appended and fsynced before any reply.

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
`world-view {principal, object}`, `world-receipt {principal, identity}`, `world-history`, `world-status`,
`world-deliver {limit}`, `world-pending`, `world-reprogram`, `world-amend`, `world-advance {height}`,
`world-inspect {principal, object}`, `world-library {principal, identity}` (reload the library path; a changed pin is
a journaled change judged by the world law), `world-interpretations`, `world-interpretation {id, reply}`.
`turn` is host-assigned on propose, amend and reprogram; a client-sent `turn` is a request error.
Every journaling op goes through `durable`: step, then `settle` (resume what the step released),
then append ALL new entries, one fsync. A reply exists only after the bytes are durable.
Request errors (`Except.error`) journal nothing; refusals are receipts.

## 2. Journal entries

One JSON object per line. Common fields: `height`, `previous`, `hash`, `identity {principal, intent}`,
`roots [{object, version}]`, `turn`, `request` (digest), `outcome {tag, ...}`. Hash = SHA-256 of the
compressed entry without `hash`. Genesis `previous` is 64 zeros. `identityKey` = compressed
`[principal, intent]`; `world.receipts` maps it to the entry index (first wins, except a suspension is
replaced by the identity's final entry).

Optional top-level fields, all inside the hash: `absent [id]` (objects required absent), `turnRequest`
(digest of the original turn request), `ticksUsed`, `ledger {depth, work, storage}`, `result` (Data wire),
`sends [{id,to,method,argument,ledger}]`, `delivery {id, from}`, `resumes` (hash of the suspension it
continues), `offers` (count).

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
- `offers : List String` : rendered `offer` documents; the reply carries texts, the journal a count.
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
   `refused {clause: notSelf}` in-turn (same for `reprogram` and `amend`). Cross-object change is a `call`: the callee
   runs as its own `self`, so its writes are its own, judged by its own law. `judge` has no `unreadWrite`; a
   `world-propose` that writes an object it does not name as a root is a request error.
2. **Law facts.** `Facts {subject = principal, caller, height, turn, pin, kind}`. `caller` is the object whose method
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

## 6. Gotchas

- **annotateData** (`spec/Delvetalk/Turn.lean`, mine): a state or argument containing a sum value
  (a `List` field) cannot be applied as an untyped `inject`; `startActivity` annotates each injection from
  the entry's arrow domain and the packet bounds. If you add a new argument that is a sum, it goes
  through this too. Responses resumed via `resumeActivity` are not re-annotated (checked by
  `conformsUnder`).
- **relevantBounds** (Ops): a package's `bounds` table includes entries for its own method row, so
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
- **Replay recompile cost**: `world-open` recompiles each created object and each reprogram/creation
  record, and re-runs `judge`; a Bell/Garden chain costs ~0.2 to 1 s per object. Method packets are
  compiled lazily and cached in memory only. 1000 plain proposals replay in ~0.08 s.
- **fsync**: `Handle.flush` is not durable. `spec/native/sync.c` does `fflush` + `fcntl(F_FULLFSYNC)`
  (macOS) / `fsync`; this made 1000 proposals cost 5 to 7 s (was 0.1 s) and 200 bumps ~3 s. One sync per
  `durable` call (not per entry). The build needs `lakefile.lean` (the TOML cannot declare `extern_lib`).
- **1Password**: `git commit` can fail with "1Password: failed to fill whole buffer"; make the commit
  unsigned (`git -c commit.gpgsign=false commit ...`), which the owner's notes allow for unattended work.
- **Tests**: never run an unfiltered package suite on a loop; `tests.test_replay` and `test_await` each
  take ~12 to 40 s because every `world-create` compiles. `python3 -W error` turns leaked subprocess
  warnings into failures; close hosts in `tearDown`.
- **Not done**: `publish` and `offer` to a real transport are out of the kernel (`offer` renders
  text on the reply only); history/receipt reads do not apply `ReadPolicy`; `world-reprogram`/`amend`
  are gated only by the object's law; foreign worlds (`Reference.world != ""`) are always refused.
