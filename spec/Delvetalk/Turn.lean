/- Activity turns: run an activity to its next `perform`, hand the Plan out as
   data with a checkpoint, and continue it when resumed with a response.
   The checkpoint is the collected machine state as canonical tokens
   (Theory.ObjectiveBendCheckpoint). The type of the response is never taken
   from the client: it is re-derived from the verified artifact. -/
import Compiler.ObjectiveBendFrontEnd
import Compiler.ObjectiveBendDataWire
import Theory.ObjectiveBendDemandData
import Theory.ObjectiveBendFiniteDataTyping
import Theory.ObjectiveBendCheckpoint
import Theory.ObjectiveBendCheckpointRoundTrip
import Theory.ObjectiveBendCheckpointV2
import Theory.ObjectiveBendCheckpointV2RoundTrip
import Theory.ObjectiveBendDemandCollect
import Theory.ObjectiveBendDemandSettleProofs
import Theory.ObjectiveBendDemandCollectProofs
import Theory.ObjectiveBendDataConformance
import Delvetalk.Limits
import Delvetalk.Canonical
import Delvetalk.Profile
import Delvetalk.Entry
import Std.Data.HashSet

open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData
open Minidregg.Compiler.ObjectiveBendDataWire
open Minidregg.Theory.ObjectiveBendCheckpoint (Dictionary encodeStateV3 decodeCheckpoint)

namespace Delvetalk.Turn

/-- Re-address the original annotation table when application wraps its term.
The argument subtree is annotation-free first-order data, never raw code. -/
def applyArgument (source : AnnotatedTerm) (argument : Term)
    (extras : AnnotationTree := .empty) : AnnotatedTerm :=
  { source with
    term := .app source.term argument
    annotations := fun position => match position with
      | 0 :: rest => source.annotations rest
      | 1 :: rest => extras.lookup rest
      | _ => none }

def bounded (j : Json) (key : String) (fallback cap : Nat) : Except String Nat := do
  let value ← match j.getObjVal? key with
    | .error _ => pure fallback
    | .ok x => jsonNat x
  if value > cap then throw (key ++ " exceeds package capacity")
  return value


def failureName : Failure → String
  | .tickExhausted => "tick budget exhausted"
  | .budget => "node or byte budget exhausted"
  | .duplicateField => "duplicate field in result"
  | .executableValue => "result is executable, not data"
  | .suspended => "heap or stack capacity exhausted"
  | .divergent => "divergent (blackhole)"
  | .refused => "machine refused the program"
  | .yielded => "yielded"

/-- What a refused turn says: the program's own reason when it refused by name
(`Term.refuse`), else the failure's name. -/
def refusalText (failure : Failure) (state : State) : String :=
  match failure, state.control with
  | .refused, .refused (.program reason) => reason
  | .refused, .refused .unfetched => "a stored row is missing from the store or exceeds the cell bound"
  | _, _ => failureName failure

/-- The activity shape a turn requires of a checked type. -/
def activityShape (assumptions : Assumptions) (type : Ty) : Except String (Ty × Ty × Ty) :=
  let bounds := assumptions.bounds
  let rigid := assumptions.rigid
  let isData := fun (t : Ty) => t.isDataUnder bounds rigid Ty.dataFuel []
  match type with
  | .computation plan response result =>
      if !plan.isPlanUnder bounds rigid then .error "turn refused: Plan type is not a message (a record of first-order data)"
      else if !isData response then .error "turn refused: response type is not first-order data"
      else if !isData result then .error "turn refused: result type is not first-order data"
      else .ok (plan, response, result)
  | _ => .error "turn refused: entry is not an activity (computation type)"

/-- The type an activity entry finally yields once every parameter is applied. -/
def peelArrows : Nat → Ty → Ty
  | 0, type => type
  | fuel + 1, .arrow _ _ _ codomain => peelArrows fuel codomain
  | _, type => type

structure Budgets where
  ticks : Nat
  heap : Nat
  stack : Nat
  nodes : Nat
  bytes : Nat

def budgets (limits : Json) : Except String Budgets := do
  return ⟨← bounded limits "ticks" Bounds.ticksDefault Bounds.ticksMax,
    ← bounded limits "heap" Bounds.heapDefault Bounds.heapMax,
    ← bounded limits "stack" Bounds.stackDefault Bounds.stackMax,
    ← bounded limits "nodes" Bounds.nodesDefault Bounds.nodesMax,
    ← bounded limits "bytes" Bounds.bytesDefault Bounds.bytesMax⟩

open Minidregg.Theory.ObjectiveBendCheckpoint in
/-- A token as itself: a natural a JSON number, a text a JSON string, a string
reference a negative number (`-(i+1)`). -/
def tokenJson : Token → Json
  | .nat n => toJson n
  | .text s => toJson s
  | .str i => toJson (-((i : Int) + 1))

open Minidregg.Theory.ObjectiveBendCheckpoint in
/-- The JSON of a checkpoint's tokens: bare numbers and strings. -/
def tokensJson (tokens : Tokens) : Json := Json.arr (tokens.map tokenJson).toArray

open Minidregg.Theory.ObjectiveBendCheckpoint in
def tokensOfJson (json : Json) : Except String Tokens := do
  let items ← json.getArr?
  items.toList.mapM fun item => do
    match item with
    | .str s => return Token.text s
    | .num n =>
      if n.exponent != 0 then throw "checkpoint does not decode"
      let i := n.mantissa
      if i < 0 then return Token.str (-i - 1).toNat else return Token.nat i.toNat
    | _ => throw "checkpoint does not decode"

/-- Digests are CIDs of canonical bytes (Canonical.lean). -/
def packetDigest (packet : Json) : String := Delvetalk.Canonical.cidJson packet

def tokensDigest (tokens : Minidregg.Theory.ObjectiveBendCheckpoint.Tokens) : String :=
  Delvetalk.Canonical.cidJson (tokensJson tokens)

/-- SHA-256 of the canonical roots list: `[{object, version}]` in recorded order. -/
def rootsDigest (roots : List (String × Nat)) : String :=
  Delvetalk.Canonical.cidJson (Json.arr (roots.map fun (object, version) =>
    Json.mkObj [("object", Lean.toJson object), ("version", Lean.toJson version)]).toArray)

/-- What a suspended activity belongs to: the object whose method it runs, the
principal and intent of the turn, and the roots the turn had read when it
yielded. A checkpoint resumes only for the same binding. -/
structure Binding where
  object : String
  principal : String
  intent : String
  rootsDigest : String

def Binding.make (object principal intent : String) (roots : List (String × Nat)) : Binding :=
  ⟨object, principal, intent, Delvetalk.Turn.rootsDigest roots⟩

/-- Wire: `object`, `principal`, `intent` strings and `roots`, an array of `{object, version}`. -/
def Binding.ofJson (j : Json) : Except String Binding := do
  let roots ← (← j.getObjVal? "roots").getArr?
  let pairs ← roots.toList.mapM fun r => do return (← r.getObjValAs? String "object", ← jsonNat (← r.getObjVal? "version"))
  return Binding.make (← j.getObjValAs? String "object") (← j.getObjValAs? String "principal")
    (← j.getObjValAs? String "intent") pairs

open Minidregg.Theory.ObjectiveBendCheckpoint in
/-- A suspended activity: its collected machine state as canonical tokens, bound
to the exact packet and the binding it was produced under, and to its own
contents by a digest covering all of them. -/
structure Checkpoint where
  packetSha256 : String
  object : String
  principal : String
  intent : String
  rootsDigest : String
  tokens : Tokens
  digest : String

open Minidregg.Theory.ObjectiveBendCheckpoint in
/-- A token's canonical CBOR, as `Canonical.writeJson` writes its `tokensJson` form: a natural,
a text, or a string reference as the negative integer `-(i+1)`. -/
def writeToken (out : ByteArray) : Token → ByteArray
  | .nat n => Canonical.natural out n
  | .text t => Canonical.text out t
  | .str i => Canonical.head out 1 i

open Minidregg.Theory.ObjectiveBendCheckpoint in
/-- The canonical CBOR of the checkpoint's digest preimage, written straight from the tokens:
the map `{packetSha256, object, principal, intent, rootsDigest, tokens}` with its keys in
DAG-CBOR order (by byte length, then bytes: intent, object, tokens, principal, rootsDigest,
packetSha256), the bytes `Canonical.encodeJson` writes for the same map with `tokensJson`
(checked below), without building that `Json`. -/
def checkpointPreimage (packetSha256 object principal intent rootsDigest : String) (tokens : Tokens) : ByteArray :=
  let out := Canonical.head (ByteArray.emptyWithCapacity (64 * tokens.length + 256)) 5 6
  let out := Canonical.text (Canonical.text out "intent") intent
  let out := Canonical.text (Canonical.text out "object") object
  let out := Canonical.head (Canonical.text out "tokens") 4 tokens.length
  let out := tokens.foldl writeToken out
  let out := Canonical.text (Canonical.text out "principal") principal
  let out := Canonical.text (Canonical.text out "rootsDigest") rootsDigest
  Canonical.text (Canonical.text out "packetSha256") packetSha256

open Minidregg.Theory.ObjectiveBendCheckpoint in
def checkpointDigest (packetSha256 object principal intent rootsDigest : String) (tokens : Tokens) : String :=
  Canonical.cid (checkpointPreimage packetSha256 object principal intent rootsDigest tokens)

open Minidregg.Theory.ObjectiveBendCheckpoint in
/-- The digest as it was defined, through `Json`: the reference `checkpointDigest` agrees
with (the guards below, and `test_turn`'s digests of real checkpoints). -/
def checkpointDigestJson (packetSha256 object principal intent rootsDigest : String) (tokens : Tokens) : String :=
  Delvetalk.Canonical.cidJson (Json.mkObj [("packetSha256", Lean.toJson packetSha256),
    ("object", Lean.toJson object), ("principal", Lean.toJson principal), ("intent", Lean.toJson intent),
    ("rootsDigest", Lean.toJson rootsDigest), ("tokens", tokensJson tokens)])

open Minidregg.Theory.ObjectiveBendCheckpoint in
-- v3 tokens (naturals past 2^64, negative string references, non-ASCII text), site-prefixed
-- tokens and an empty list, each against the `Json` definition.
#guard
  let cases : List Tokens := [
    [.text "dregg.objective-bend.checkpoint.v3", .nat 17, .nat 18446744073709551616, .nat 255,
      .nat 65536, .str 0, .str 23, .str 24, .str 70000, .text "", .text "Grüße ✾"],
    [.text "delvetalk.checkpoint.site.v1", .nat 4, .text "dregg.objective-bend.checkpoint.v3", .nat 1],
    []]
  cases.all fun t =>
    checkpointDigest "bafy" "garden/bell/1" "did:plc:x" "intent-1" "bafyroots" t ==
      checkpointDigestJson "bafy" "garden/bell/1" "did:plc:x" "intent-1" "bafyroots" t

def Checkpoint.makeFor (pin : String) (binding : Binding) (tokens : Minidregg.Theory.ObjectiveBendCheckpoint.Tokens) :
    Checkpoint :=
  ⟨pin, binding.object, binding.principal, binding.intent, binding.rootsDigest, tokens,
    checkpointDigest pin binding.object binding.principal binding.intent binding.rootsDigest tokens⟩

def Checkpoint.make (packet : Json) (binding : Binding) (tokens : Minidregg.Theory.ObjectiveBendCheckpoint.Tokens) :
    Checkpoint :=
  Checkpoint.makeFor (packetDigest packet) binding tokens

def Checkpoint.toJson (c : Checkpoint) : Json :=
  Json.mkObj [("packetSha256", Lean.toJson c.packetSha256), ("object", Lean.toJson c.object),
    ("principal", Lean.toJson c.principal), ("intent", Lean.toJson c.intent),
    ("rootsDigest", Lean.toJson c.rootsDigest), ("tokens", tokensJson c.tokens), ("digest", Lean.toJson c.digest)]

def Checkpoint.fromJson (j : Json) : Except String Checkpoint := do
  return ⟨← j.getObjValAs? String "packetSha256", ← j.getObjValAs? String "object",
    ← j.getObjValAs? String "principal", ← j.getObjValAs? String "intent",
    ← j.getObjValAs? String "rootsDigest", ← tokensOfJson (← j.getObjVal? "tokens"),
    ← j.getObjValAs? String "digest"⟩

inductive Outcome where
  | finished (value : Data) (result : Ty) (ticksUsed : Nat)
  | yielded (plan : Data) (planType responseType : Ty) (checkpoint : Checkpoint) (ticksUsed : Nat)
  /-- A budget ran out: `resource` is one of ticks, heap, stack, nodes, bytes. Not an
  error: the turn is a named silence the host journals as class `budget`. -/
  | exhausted (resource : String) (ticksUsed : Nat)

def Outcome.toJson : Outcome → Json
  | .finished value result ticks => Json.mkObj [("status", Lean.toJson "finished"),
      ("value", dataJson value), ("type", typeJson result), ("ticksUsed", Lean.toJson ticks)]
  | .yielded plan planType responseType checkpoint ticks => Json.mkObj [("status", Lean.toJson "yielded"),
      ("plan", dataJson plan), ("planType", typeJson planType), ("responseType", typeJson responseType),
      ("checkpoint", checkpoint.toJson), ("ticksUsed", Lean.toJson ticks)]
  | .exhausted resource ticks => Json.mkObj [("status", Lean.toJson "exhausted"),
      ("resource", Lean.toJson resource), ("ticksUsed", Lean.toJson ticks)]

open Minidregg.Theory.ObjectiveBendDemandMachine in
/-- Which budget a machine failure names, if it is budget exhaustion. A capacity
suspension keeps the pre-step state: whichever of heap or stack the next step would
exceed is the resource; otherwise the step's text allocation exceeded `bytes`. -/
def exhaustedResource (limits : Limits) (failure : Failure) (state : State) (remaining : Budget)
    (fetch : Fetch := Fetch.none) : Option String :=
  match failure with
  | .tickExhausted => some "ticks"
  | .budget => some (if remaining.nodes == 0 then "nodes" else "bytes")
  | .suspended =>
      -- A row fetch suspends before its step: its heap is the row's fields.
      match fetchable fetch state with
      | some (_, _, _, row) =>
        some (if state.heap.size + Minidregg.Theory.ObjectiveBendDemandMachineFast.nativeChildren row > limits.heap
          then "heap" else "bytes")
      | none =>
      let next := stepRaw state
      if next.heap.size > limits.heap then some "heap"
      else if next.stack.length > limits.stack then some "stack"
      else some "bytes"
  | _ => none

/-! ## Call sites of a message activity

A message activity (`Activity<R>`, Plan `World.Message`) resumes each perform at that
perform's own result type, the codomain of its annotation. The machine keeps no positions,
so a site is named by its plan term: the yielded plan cell's origin before the checkpoint
settles it. An entry in which two performs build the same plan term at different result
types is refused at compile (`messageSites`), so the plan term names exactly one type. A
checkpoint taken at a message yield is prefixed `[siteEdition, i]`, `i` the site's index
in `messageSites`; resuming reads the type there. The prefix is inside the digest, so it
is bound like the state; a checkpoint without one names no site and does not resume. -/

/-- The edition marker a message checkpoint's site index follows. -/
def siteEdition : String := "delvetalk.checkpoint.site.v1"

/-- The site whose plan the yielded state's plan cell was built from. -/
def yieldedSite (sites : Array (Term × Ty)) (state : State) : Option Nat :=
  match state.control with
  | .yielded address => match state.heap[address]? with
    | some (.suspended c) | some (.evaluating c) | some (.cached c _) =>
      sites.findIdx? fun (t, _) => Minidregg.Theory.ObjectiveBendCheckpoint.termEq t c.term
    | _ => none
  | _ => none

open Minidregg.Theory.ObjectiveBendCheckpoint in
/-- A checkpoint's site index and its state tokens. -/
def splitSite : Tokens → Option Nat × Tokens
  | .text edition :: .nat i :: rest => if edition == siteEdition then (some i, rest) else (none, .text edition :: .nat i :: rest)
  | tokens => (none, tokens)

/-- The response type a yield resumes at: its site's. -/
def resumeTypeAt (sites : Option (Array (Term × Ty))) (_response : Ty) : Option Nat → Except String Ty
  | none => .error "checkpoint names no call site of this entry"
  | some i => match sites with
    | some s => match s[i]? with
      | some (_, t) => .ok t
      | none => .error "checkpoint names no call site of this entry"
    | none => .error "checkpoint does not decode"

open Minidregg.Theory.ObjectiveBendCheckpoint in
/-- The response type a checkpoint resumes at, and its state tokens. -/
def resumeType (sites : Option (Array (Term × Ty))) (response : Ty) (tokens : Tokens) :
    Except String (Ty × Tokens) := do
  let (site, rest) := splitSite tokens
  return (← resumeTypeAt sites response site, rest)

/-- The dictionary a packet's checkpoints are written against: its entry term's. -/
def programDictionary (packet : Json) : Dictionary :=
  match decodePacket packet with
  | .ok decoded => Dictionary.ofProgram decoded.source.term
  | .error _ => {}

/-- A yield held in this process: the yielded state as the machine left it, with what its
checkpoint binds (pin, binding) and is written against (dictionary, site). A host that
answers the Plan at once resumes from it (`resumeSuspended`), neither collecting nor
encoding it; a turn that truly suspends makes the `Checkpoint` (`Suspension.checkpoint`:
`encodeStateV3` of `checkpoint state`). The two resumptions agree: `resumeEntry` decodes the
tokens to exactly `checkpoint state` (`stateV3_roundTrip`), and resuming `checkpoint state`
decides the same verdict, spends the same ticks and extracts the same Plan or result as
resuming `state`, each under `limitsPast` of its own heap (`checkpoint_resume_segment`). -/
structure Suspension where
  pin : String
  binding : Binding
  dictionary : Dictionary
  site : Option Nat
  state : State

/-- The checkpoint of a held yield: the state's v3 tokens (after the site prefix, for a
message activity), bound and digested. -/
def Suspension.checkpoint (s : Suspension) : Checkpoint :=
  let tokens := encodeStateV3 s.dictionary (Minidregg.Theory.ObjectiveBendDemandCollect.checkpoint s.state)
  Checkpoint.makeFor s.pin s.binding (match s.site with
    | some i => .text siteEdition :: .nat i :: tokens
    | none => tokens)

/-- A segment's outcome with its yield held (`Suspension`), not yet a `Checkpoint`. -/
inductive Step where
  | finished (value : Data) (result : Ty) (ticksUsed : Nat)
  | yielded (plan : Data) (planType responseType : Ty) (suspension : Suspension) (ticksUsed : Nat)
  | exhausted (resource : String) (ticksUsed : Nat)

/-- The outcome a caller outside this process sees: a yield's checkpoint made. -/
def Step.outcome : Step → Outcome
  | .finished value result ticks => .finished value result ticks
  | .yielded plan planType responseType suspension ticks =>
    .yielded plan planType responseType suspension.checkpoint ticks
  | .exhausted resource ticks => .exhausted resource ticks

open Minidregg.Theory.ObjectiveBendDemandCollect in
/-- Turn the outcome of a bounded run into a typed step; a yield holds the collected state. -/
def concludeStep (dictionary : Dictionary) (pin : String) (binding : Binding) (bounds : DataBounds) (plan response result : Ty) (b : Budgets) (limits : Limits)
    (outcome : Except (Failure × State × Budget) (Data × Budget))
    (sites : Option (Array (Term × Ty)) := none) (fetch : Fetch := Fetch.none) : Except String Step :=
  match outcome with
  | .ok (value, remaining) =>
      if !value.conformsUnder bounds result then .error "turn refused: result does not conform to its type"
      else .ok (.finished value result (b.ticks - remaining.ticks))
  | .error (.yielded, state, remaining) =>
      match yieldedPlan fetch limits remaining state with
      | .error (failure, st, rem) =>
          -- A materialization budget failure is nodes when it vanishes with unlimited nodes.
          let resource? := match failure with
            | .budget => some (match yieldedPlan fetch limits {remaining with nodes := 1 <<< 40} state with
                | .error (.budget, _, _) => "bytes"
                | _ => "nodes")
            | _ => exhaustedResource limits failure st rem fetch
          match resource? with
          | some resource => .ok (.exhausted resource (b.ticks - rem.ticks))
          | none => .error ("turn refused: " ++ refusalText failure st)
      | .ok extracted =>
          if !extracted.value.conformsUnder bounds plan then .error "turn refused: Plan does not conform to its type"
          else
            let ticks := b.ticks - extracted.remaining.ticks
            let held := fun (site : Option Nat) =>
              ({ pin, binding, dictionary, site, state := extracted.state } : Suspension)
            match sites with
            | none => .ok (.yielded extracted.value plan response (held none) ticks)
            | some sites => match yieldedSite sites extracted.state with
              | some i => .ok (.yielded extracted.value plan (sites[i]?.map (·.2) |>.getD response) (held (some i)) ticks)
              | none => .error "turn refused: the yielded message has no call site in this entry"
  | .error (failure, st, rem) =>
      match exhaustedResource limits failure st rem fetch with
      | some resource => .ok (.exhausted resource (b.ticks - rem.ticks))
      | none => .error ("turn refused: " ++ refusalText failure st)

/-! ## A decoded, checked entry: no packet decoding or re-checking per turn -/

open Minidregg.Theory.ObjectiveBendCheckpoint Minidregg.Theory.ObjectiveBendDemandCollect in
/-- A checkpoint's state, checked against the entry and the binding and decoded, with the site
it names. `issued` is the digest the caller recorded when the checkpoint was made (the host's
journal, a session's issued table): the tokens and binding must hash to it. The `digest` carried
beside the tokens is never trusted, since anyone can recompute it over invented tokens. -/
def checkpointState (entry : Delvetalk.CheckedEntry) (checkpoint : Checkpoint) (issued : String) (binding : Binding)
    (dictionary : Dictionary) : Except String (State × Option Nat) := do
  discard <| activityShape entry.source.assumptions (peelArrows Bounds.entryArrowDepth entry.type)
  unless checkpoint.packetSha256 == entry.pin do throw "checkpoint belongs to another package"
  unless issued == checkpointDigest checkpoint.packetSha256 checkpoint.object checkpoint.principal
      checkpoint.intent checkpoint.rootsDigest checkpoint.tokens do throw "checkpoint digest mismatch"
  unless checkpoint.object == binding.object do throw "checkpoint belongs to another object"
  unless checkpoint.principal == binding.principal do throw "checkpoint belongs to another principal"
  unless checkpoint.intent == binding.intent do throw "checkpoint belongs to another intent"
  unless checkpoint.rootsDigest == binding.rootsDigest do throw "checkpoint was taken under different roots"
  let (site, tokens) := splitSite checkpoint.tokens
  let some state := decodeCheckpoint dictionary tokens | throw "checkpoint does not decode"
  return (state, site)

/-- A yielded state resumed with `value`: its activity shape, the response type of its site,
the response's conformance and the machine's `resume`. -/
def resumeState (entry : Delvetalk.CheckedEntry) (state : State) (site : Option Nat) (value : Data) :
    Except String (DataBounds × Ty × Ty × Ty × State) := do
  let assumptions := entry.source.assumptions
  let (plan, response, result) ← activityShape assumptions (peelArrows Bounds.entryArrowDepth entry.type)
  let response ← resumeTypeAt entry.sites response site
  unless value.conformsUnder assumptions.bounds response do throw "turn refused: response does not conform to the response type"
  let some resumed := Minidregg.Theory.ObjectiveBendDemandMachine.resume value.term state
    | throw "turn refused: checkpoint is not a yielded state"
  return (assumptions.bounds, plan, response, result, resumed)

/-! ## Stored state (KERNEL-HANDOFF §15)

The stored path takes every argument natively (no quoting, no per-turn check: each data
argument is admitted by `conformsUnder`, which `conformsUnder_iff` makes `HasType`, as a card's
are), and the first, the object's state, as one stored object cell whose relations named in the
store are stored cells: rows are fetched from the store only when forced, and a segment reports
the rows it forced (`Reads`) for the host to record as roots. -/

/-- A relation field of the state the host holds: its row count and key columns, at the turn's
read height. -/
structure StoredRelation where
  field : String
  size : Nat
  key : List String

/-- The host's store for one turn: its stored relations and their rows (`fetch field position`,
canonical key order, at the turn's read height). -/
structure Store where
  relations : List StoredRelation
  fetch : Fetch

def Store.empty : Store := ⟨[], Fetch.none⟩

/-- What the kernel fetches: the store's rows within the cell bound (`Bounds.maxCellBytes`); a
larger one is refused as missing (`refusalText`). -/
def Store.bounded (store : Store) : Fetch := fun field position =>
  (store.fetch field position).filter (·.canonicalBytes ≤ Bounds.maxCellBytes)

/-- A forced row: its relation field, its key projection (a record of the key columns), and
its canonical bytes. -/
structure Read where
  field : String
  key : Data
  bytes : Nat

/-- A segment's reads: the rows it forced and, per stored field, how far its spine was forced
(`n + 1` once its `nil` was: the whole key set was observed). -/
structure Reads where
  rows : List Read
  spans : List (String × Nat)

def keyProjection (key : List String) : Data → Data
  | .record fields => .record (key.filterMap fun column => (fields.lookup column).map (column, ·))
  | row => row

def Store.readsOf (store : Store) (state : State) : Reads :=
  { rows := (forcedRows state).filterMap fun (field, position) => do
      let relation ← store.relations.find? (·.field == field)
      let row ← store.fetch field position
      return ⟨field, keyProjection relation.key row, row.canonicalBytes⟩
    spans := spineReach state }

def Reads.toJson (r : Reads) : Json :=
  Json.mkObj [("rows", Json.arr (r.rows.map fun read => Json.mkObj [("field", Lean.toJson read.field),
      ("key", dataJson read.key), ("bytes", Lean.toJson read.bytes)]).toArray),
    ("spans", Json.arr (r.spans.map fun (field, reach) =>
      Json.mkObj [("field", Lean.toJson field), ("reach", Lean.toJson reach)]).toArray)]

/-- The state with its stored relations emptied (`rows {items: []}`): what the kernel checks
of a stored state, and the scalar part the host bounds by `Bounds.maxCellBytes`. -/
def scalarPart (stored : List String) : Data → Data
  | .record fields => .record (fields.map fun (name, value) =>
      if stored.contains name then (name, .variant "rows" (.record [("items", .variant "nil" (.record []))]))
      else (name, value))
  | state => state

/-! ### The per-cell bound (KERNEL-HANDOFF §15, step 4)

A state is bounded per cell: its scalar part (`scalarPart`) and each row of a stored relation are
at most `Bounds.maxCellBytes` canonical bytes. A write pays the canonical bytes of the cells it
changes: the scalar part when a scalar field changed, and each row whose key is new or whose row
changed. The host calls these at write (the bound, the storage ledger). -/

/-- The rows of a stored relation field of a state record (`rows {items}`), or none. -/
def relationRows (state : Data) (field : String) : Array Data :=
  match state with
  | .record fields => match fields.lookup field with
    | some (.variant "rows" (.record [("items", items)])) => (listItems? items).getD #[]
    | _ => #[]
  | _ => #[]

/-- The first cell of `state` past the cell bound: `"scalar"` for its scalar part, else the
relation field and the key of a row (of the relations named in `rows`, by default all: a write
names those it edited); none when every cell fits. -/
def cellOverBound (relations : List (String × List String)) (state : Data)
    (rows : List String := relations.map (·.1)) : Option (String × Data) :=
  let stored := relations.map (·.1)
  if (Canonical.encode (scalarPart stored state)).size > Bounds.maxCellBytes then some ("scalar", .record [])
  else (relations.filter (rows.contains ·.1)).findSome? fun (field, key) =>
    (relationRows state field).findSome? fun row =>
      if (Canonical.encode row).size > Bounds.maxCellBytes then some (field, keyProjection key row) else none

/-- The canonical bytes a write from `before` to `after` changes: the scalar part's when a scalar
field differs, plus each row of `after` whose key is new or whose row differs (in the relations
named in `rows`, by default all: a write names those it edited, the rest being unchanged). -/
def changedCellBytes (relations : List (String × List String)) (before after : Data)
    (rows : List String := relations.map (·.1)) : Nat :=
  let stored := relations.map (·.1)
  let scalar := Canonical.encode (scalarPart stored after)
  let scalarBytes := if scalar == Canonical.encode (scalarPart stored before) then 0 else scalar.size
  -- A row is unchanged when the same bytes stood before: its key is a projection of them.
  (relations.filter (rows.contains ·.1)).foldl (fun total (field, _) =>
    let old : Std.HashSet ByteArray := (relationRows before field).foldl (fun s row => s.insert (Canonical.encode row)) {}
    (relationRows after field).foldl (fun total row =>
      let bytes := Canonical.encode row
      if old.contains bytes then total else total + bytes.size) total) scalarBytes

-- A changed scalar pays the scalar part; an inserted row pays its bytes; an unchanged row nothing.
#guard
  let row := fun (n : Nat) (t : String) => Data.record [("n", .natural n), ("text", .label t)]
  let rel := fun (rows : List Data) => Data.variant "rows" (.record [("items", rows.foldr
    (fun r tail => .variant "cons" (.record [("head", r), ("tail", tail)])) (.variant "nil" (.record [])))])
  let s := fun (count : Nat) (rows : List Data) => Data.record [("count", .natural count), ("rains", rel rows)]
  let decl := [("rains", ["n"])]
  changedCellBytes decl (s 1 [row 0 "a"]) (s 1 [row 0 "a"]) == 0 &&
  changedCellBytes decl (s 1 [row 0 "a"]) (s 1 [row 0 "a", row 1 "b"]) == (Canonical.encode (row 1 "b")).size &&
  changedCellBytes decl (s 1 [row 0 "a"]) (s 1 [row 0 "z"]) == (Canonical.encode (row 0 "z")).size &&
  changedCellBytes decl (s 1 [row 0 "a"]) (s 2 [row 0 "a"]) == (Canonical.encode (scalarPart ["rains"] (s 2 []))).size &&
  (cellOverBound decl (s 1 [row 0 "a"])).isNone &&
  (cellOverBound decl (s 1 [row 0 (String.mk (List.replicate 262144 (Char.ofNat 120)))])).map (·.1) == some "rains"

/-- The machine state a stored turn starts from, with its activity shape: `entry` applied to
the state (one stored object cell at address 0) and the remaining arguments natively. -/
def storedStart (entry : Delvetalk.CheckedEntry) (arguments : List Data) (store : Store) :
    Except String (State × Ty × Ty × Ty) := do
  let bounds := entry.source.assumptions.bounds
  let stored := store.relations.map (·.field)
  let mut type := entry.type
  for (v, i) in arguments.zipIdx do
    let (domain, rest) := match callable type with
      | .arrow _ _ d c => (d, c)
      | other => (other, other)
    let checked := if i == 0 then scalarPart stored v else v
    if domain.isDataUnder bounds [] Ty.dataFuel [] && !checked.conformsUnder bounds domain then
      throw "turn refused: argument does not conform to its type"
    if domain == .data && !checked.wellFormed then throw "turn refused: argument does not conform to Data (repeated field)"
    type := rest
  let (plan, response, result) ← activityShape entry.source.assumptions type
  -- With no stored relation every argument is native, whatever its shape.
  if store.relations.isEmpty then
    return (⟨#[], .evaluate entry.source.term [], arguments.map .nativeArgument⟩, plan, response, result)
  let .record fields :: rest := arguments | throw "turn refused: a stored turn's first argument is its state record"
  let start : State := ⟨#[.stored (.object fields (store.relations.map fun r => (r.field, r.size))) none],
    .evaluate entry.source.term [], .argument (.bound 0) [0] :: rest.map .nativeArgument⟩
  return (start, plan, response, result)

/-- Run a stored segment from `start` under `limits`, conclude it, and read its reads off the
state it ended in (a yield's after its Plan was materialized). -/
def runStored (entry : Delvetalk.CheckedEntry) (store : Store) (dictionary : Dictionary) (binding : Binding)
    (plan response result : Ty) (b : Budgets) (limits : Limits) (start : State) : Except String (Step × Reads) := do
  let fetch := store.bounded
  let run := executeStateWith (fun _ => true) fetch limits ⟨b.nodes, b.ticks, b.bytes⟩ start
  let ended := match run with
    | .ok e => e.extraction.result.state
    | .error (_, state, _) => state
  let step ← concludeStep dictionary entry.pin binding entry.source.assumptions.bounds plan response result b limits
    (run.map fun e => (e.extraction.result.value, e.extraction.result.remaining)) entry.sites fetch
  let ended := match step with
    | .yielded _ _ _ suspension _ => suspension.state
    | _ => ended
  return (step, store.readsOf ended)

/-- The rows of `field` from `position` on as the list `List<T>` they stand for, from `store`;
none when the store does not answer one. -/
def storedList (store : Store) (field : String) (position size : Nat) : Option Data :=
  ((List.range (size - position)).mapM fun i => store.fetch field (position + i)).map fun rows =>
    rows.foldr (fun row tail => .variant "cons" (.record [("head", row), ("tail", tail)])) (.variant "nil" (.record []))

/-- The native data a stored part stands for, from `store`. -/
def storedData (store : Store) : Stored → Option Data
  | .object fields stored => do
    return .record (← fields.mapM fun (name, value) => match stored.lookup name with
      | some size => do return (name, .variant "rows" (.record [("items", ← storedList store name 0 size)]))
      | none => pure (name, value))
  | .relation f n => do return .variant "rows" (.record [("items", ← storedList store f 0 n)])
  | .items f n => do return .record [("items", ← storedList store f 0 n)]
  | .spine f j n => storedList store f j n
  | .cons f j n => do return .record [("head", ← store.fetch f j), ("tail", ← storedList store f (j + 1) n)]
  | .row f j => store.fetch f j

/-- A yielded state, collected as its checkpoint is (`ObjectiveBendDemandCollect.checkpoint`), with
every stored cell it still holds unforced replaced by the native data it stands for, and the stored
fields so replaced: what a checkpoint kept past this process holds, so that resuming it fetches
nothing (forcing a native cell is forcing the stored cell it replaced). -/
def materializeStored (store : Store) (yielded : State) : State × List String :=
  let state := Minidregg.Theory.ObjectiveBendDemandCollect.checkpoint yielded
  let fieldsOf : Stored → List String
    | .object _ stored => stored.map (·.1)
    | .relation f _ | .items f _ | .spine f _ _ | .cons f _ _ | .row f _ => [f]
  let (heap, fields) := state.heap.foldl (fun (heap, fields) cell => match cell with
    | .stored part none => match storedData store part with
      | some d => (heap.push (.native d), fields ++ fieldsOf part)
      | none => (heap.push cell, fields)
    | other => (heap.push other, fields)) (#[], [])
  ({ state with heap }, fields.eraseDups)

/-- Start a stored turn on a held entry: its first step and the rows it forced. -/
def startEntry (entry : Delvetalk.CheckedEntry) (arguments : List Data) (store : Store) (binding : Binding)
    (b : Budgets) (dictionary : Option Dictionary := none) : Except String (Step × Reads) := do
  let (start, plan, response, result) ← storedStart entry arguments store
  runStored entry store (dictionary.getD (Dictionary.ofProgram entry.source.term)) binding plan response result b
    ⟨b.heap, b.stack⟩ start

/-- Resume a stored yield held in this process (`resumeSuspended`'s refusals), fetching from
`store`, which must answer the read height the turn started at. -/
def resumeSuspended (entry : Delvetalk.CheckedEntry) (suspension : Suspension) (store : Store)
    (binding : Binding) (value : Data) (b : Budgets) : Except String (Step × Reads) := do
  discard <| activityShape entry.source.assumptions (peelArrows Bounds.entryArrowDepth entry.type)
  unless suspension.pin == entry.pin do throw "checkpoint belongs to another package"
  unless suspension.binding.object == binding.object do throw "checkpoint belongs to another object"
  unless suspension.binding.principal == binding.principal do throw "checkpoint belongs to another principal"
  unless suspension.binding.intent == binding.intent do throw "checkpoint belongs to another intent"
  unless suspension.binding.rootsDigest == binding.rootsDigest do throw "checkpoint was taken under different roots"
  let (_, plan, response, result, resumed) ← resumeState entry suspension.state suspension.site value
  runStored entry store suspension.dictionary binding plan response result b
    (Minidregg.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ suspension.state) resumed

/-- Resume a stored turn's checkpoint whose digest the caller recorded (`issued`). -/
def resumeEntry (entry : Delvetalk.CheckedEntry) (checkpoint : Checkpoint) (issued : String)
    (binding : Binding) (value : Data) (b : Budgets) (store : Store) (dictionary : Option Dictionary := none) :
    Except String (Step × Reads) := do
  let dictionary := dictionary.getD (Dictionary.ofProgram entry.source.term)
  let (state, site) ← checkpointState entry checkpoint issued binding dictionary
  let (_, plan, response, result, resumed) ← resumeState entry state site value
  runStored entry store dictionary binding plan response result b
    (Minidregg.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ state) resumed

def wantsProfile (request : Json) : Bool := (request.getObjValAs? Bool "profile").toOption.getD false

/-- A store over a state's own rows, for the JSON ops: `stored: [{field, key}]` names the state's
relation fields to hold as stored cells (the host builds its `Store` from its own store). -/
def storeOfState (state : Data) (stored : Json) : Except String Store := do
  let .record fields := state | throw "a stored turn's state is a record"
  let relations ← (← stored.getArr?).toList.mapM fun decl => do
    let field ← decl.getObjValAs? String "field"
    let key ← decl.getObjValAs? (List String) "key"
    let some (.variant "rows" (.record [("items", items)])) := fields.lookup field
      | throw s!"stored field {field} is not a relation"
    let some rows := listItems? items | throw s!"stored field {field} holds no list"
    pure (({ field, size := rows.size, key } : StoredRelation), rows)
  return ⟨relations.map (·.1), fun field position => ((relations.find? (·.1.field == field)).map (·.2)).bind (·[position]?)⟩

def stepJson (step : Step) (reads : Reads) : Json := step.outcome.toJson.setObjVal! "reads" reads.toJson

/-- `turn-start`: the first argument's relations named in `stored: [{field, key}]` held as stored
cells over its own rows (none named: every argument native); the reply carries `reads`, and with
`profile: true` the segment's tick breakdown. -/
def startEntryJson (entry : Delvetalk.CheckedEntry) (arguments limits request : Json) : Except String Json := do
  let values ← (← arguments.getArr?).toList.mapM (decodeData Bounds.dataWireDepth)
  let b ← budgets limits
  let store ← match request.getObjVal? "stored" with
    | .ok stored => storeOfState (values.headD (.record [])) stored
    | .error _ => pure Store.empty
  let (step, reads) ← startEntry entry values store (← Binding.ofJson request) b
  let reply := stepJson step reads
  if !wantsProfile request then return reply
  let (start, _) ← storedStart entry values store
  return reply.setObjVal! "profile" (Delvetalk.Profile.profile ⟨b.heap, b.stack⟩ b.bytes b.ticks start store.bounded)

/-- The refusal of a checkpoint whose digest the resuming process did not record. -/
def notIssued : String := "checkpoint was not issued by this process"

/-- `turn-resume` in a process without a journal: `issued` answers whether this process handed
out a checkpoint with that digest; the supplied digest is only the key looked up. -/
def resumeEntryJson (entry : Delvetalk.CheckedEntry) (issued : String → Bool) (checkpointJson responseJson limits request : Json) :
    Except String Json := do
  let checkpoint ← Checkpoint.fromJson checkpointJson
  unless issued checkpoint.digest do throw notIssued
  let value ← decodeData Bounds.dataWireDepth responseJson
  let b ← budgets limits
  let binding ← Binding.ofJson request
  let store ← match request.getObjVal? "stored" with
    | .ok stored => storeOfState (← decodeData Bounds.dataWireDepth (← request.getObjVal? "state")) stored
    | .error _ => pure Store.empty
  let (step, reads) ← resumeEntry entry checkpoint checkpoint.digest binding value b store
  let reply := stepJson step reads
  if !wantsProfile request then return reply
  let dictionary := Dictionary.ofProgram entry.source.term
  let (state, site) ← checkpointState entry checkpoint checkpoint.digest binding dictionary
  let (_, _, _, _, resumed) ← resumeState entry state site value
  return reply.setObjVal! "profile" (Delvetalk.Profile.profile
    (Minidregg.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ state) b.bytes b.ticks resumed store.bounded)

end Delvetalk.Turn
