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
import Theory.ObjectiveBendCheckpointV3
import Theory.ObjectiveBendCheckpointV3RoundTrip
import Theory.ObjectiveBendDemandCollect
import Theory.ObjectiveBendDemandSettleProofs
import Theory.ObjectiveBendDemandCollectProofs
import Theory.ObjectiveBendDataConformance
import Theory.ObjectiveBendCellConformance
import Delvetalk.Limits
import Delvetalk.Canonical
import Delvetalk.Profile
import Delvetalk.Entry
import Std.Data.HashSet

open Lean (Json toJson)
open Delvetalk.Theory.ObjectiveBendTyping
open Delvetalk.Theory.ObjectiveBendOpenRecursion
open Delvetalk.Theory.ObjectiveBendTypes
open Delvetalk.Theory.ObjectiveBendDemandMachine
open Delvetalk.Theory.ObjectiveBendDemandData
open Delvetalk.Compiler.ObjectiveBendDataWire
open Delvetalk.Theory.ObjectiveBendCheckpoint (Dictionary encodeStateV3 decodeCheckpoint)

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
  | .budget => "byte budget exhausted"
  | .nodes => "node budget exhausted"
  | .duplicateField => "duplicate field in result"
  | .executableValue => "result is executable, not data"
  | .suspended => "heap or stack capacity exhausted"
  | .divergent => "divergent (blackhole)"
  | .refused => "machine refused the program"
  | .yielded => "yielded"

/-- What a machine failure says: a program's own refusal its reason (a turn's is an outcome,
`Step.refused`; a card's or a view's is this text), a store's refusal what was not fetched. -/
def refusalText (failure : Failure) (state : State) : String :=
  match failure, state.control with
  | .refused, .refused (.program reason) => reason
  | .refused, .refused .unfetched =>
    "a stored row is missing from the store or exceeds the cell bound, or a lookup's key is not its relation's declared key"
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

open Delvetalk.Theory.ObjectiveBendCheckpoint in
/-- A token as itself: a natural a JSON number, a text a JSON string, a string
reference a negative number (`-(i+1)`). -/
def tokenJson : Token → Json
  | .nat n => toJson n
  | .text s => toJson s
  | .str i => toJson (-((i : Int) + 1))

open Delvetalk.Theory.ObjectiveBendCheckpoint in
/-- The JSON of a checkpoint's tokens: bare numbers and strings. -/
def tokensJson (tokens : Tokens) : Json := Json.arr (tokens.map tokenJson).toArray

open Delvetalk.Theory.ObjectiveBendCheckpoint in
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

open Delvetalk.Theory.ObjectiveBendCheckpoint in
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

open Delvetalk.Theory.ObjectiveBendCheckpoint in
/-- A token's canonical CBOR, as `Canonical.writeJson` writes its `tokensJson` form: a natural,
a text, or a string reference as the negative integer `-(i+1)`. -/
def writeToken (out : ByteArray) : Token → ByteArray
  | .nat n => Canonical.natural out n
  | .text t => Canonical.text out t
  | .str i => Canonical.head out 1 i

open Delvetalk.Theory.ObjectiveBendCheckpoint in
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

open Delvetalk.Theory.ObjectiveBendCheckpoint in
def checkpointDigest (packetSha256 object principal intent rootsDigest : String) (tokens : Tokens) : String :=
  Canonical.cid (checkpointPreimage packetSha256 object principal intent rootsDigest tokens)

open Delvetalk.Theory.ObjectiveBendCheckpoint in
/-- The digest as it was defined, through `Json`: the reference `checkpointDigest` agrees
with (the guards below, and `test_turn`'s digests of real checkpoints). -/
def checkpointDigestJson (packetSha256 object principal intent rootsDigest : String) (tokens : Tokens) : String :=
  Delvetalk.Canonical.cidJson (Json.mkObj [("packetSha256", Lean.toJson packetSha256),
    ("object", Lean.toJson object), ("principal", Lean.toJson principal), ("intent", Lean.toJson intent),
    ("rootsDigest", Lean.toJson rootsDigest), ("tokens", tokensJson tokens)])

open Delvetalk.Theory.ObjectiveBendCheckpoint in
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

def Checkpoint.makeFor (pin : String) (binding : Binding) (tokens : Delvetalk.Theory.ObjectiveBendCheckpoint.Tokens) :
    Checkpoint :=
  ⟨pin, binding.object, binding.principal, binding.intent, binding.rootsDigest, tokens,
    checkpointDigest pin binding.object binding.principal binding.intent binding.rootsDigest tokens⟩

def Checkpoint.make (packet : Json) (binding : Binding) (tokens : Delvetalk.Theory.ObjectiveBendCheckpoint.Tokens) :
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
  /-- The program refused its turn (`Term.refuse`) with the text its reason evaluated to. -/
  | refused (reason : String) (ticksUsed : Nat)

def Outcome.toJson : Outcome → Json
  | .finished value result ticks => Json.mkObj [("status", Lean.toJson "finished"),
      ("value", dataJson value), ("type", typeJson result), ("ticksUsed", Lean.toJson ticks)]
  | .yielded plan planType responseType checkpoint ticks => Json.mkObj [("status", Lean.toJson "yielded"),
      ("plan", dataJson plan), ("planType", typeJson planType), ("responseType", typeJson responseType),
      ("checkpoint", checkpoint.toJson), ("ticksUsed", Lean.toJson ticks)]
  | .exhausted resource ticks => Json.mkObj [("status", Lean.toJson "exhausted"),
      ("resource", Lean.toJson resource), ("ticksUsed", Lean.toJson ticks)]
  | .refused reason ticks => Json.mkObj [("status", Lean.toJson "refused"),
      ("reason", Lean.toJson reason), ("ticksUsed", Lean.toJson ticks)]

open Delvetalk.Theory.ObjectiveBendDemandMachine in
/-- Which budget a machine failure names, if it is budget exhaustion. A capacity
suspension keeps the pre-step state: whichever of heap or stack the next step would
exceed is the resource; otherwise the step's text allocation exceeded `bytes`. -/
def exhaustedResource (limits : Limits) (failure : Failure) (state : State) (remaining : Budget)
    (fetch : Fetch := Fetch.none) : Option String :=
  match failure with
  | .tickExhausted => some "ticks"
  | .budget => some "bytes"
  | .nodes => some "nodes"
  | .suspended =>
      -- A row fetch suspends before its step: its heap is the row's fields.
      match fetchable fetch state with
      | some (_, _, row) =>
        some (if state.heap.size + Delvetalk.Theory.ObjectiveBendDemandMachineFast.nativeChildren row > limits.heap
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

/-- A site whose hash is its plan's matches a term exactly when `termEq` relates them: the hash
only rules sites out. -/
theorem Site.matches_eq (site : Delvetalk.Site) (t : Term)
    (hashed : site.hash = Delvetalk.Theory.ObjectiveBendCheckpoint.termHash site.term) :
    site.matches t (Delvetalk.Theory.ObjectiveBendCheckpoint.termHash t) =
      Delvetalk.Theory.ObjectiveBendCheckpoint.termEq site.term t := by
  unfold Delvetalk.Site.matches
  cases e : Delvetalk.Theory.ObjectiveBendCheckpoint.termEq site.term t with
  | false => simp
  | true =>
    have same := Delvetalk.Theory.ObjectiveBendCheckpointRoundTrip.termEq_eq e
    subst same
    simp [hashed]

#assert_axioms Site.matches_eq

/-- The site whose plan the yielded state's plan cell was built from. -/
def yieldedSite (sites : Array Delvetalk.Site) (state : State) : Option Nat :=
  match state.control with
  | .yielded address => match state.heap[address]? with
    | some (.suspended c) | some (.evaluating c) | some (.cached c _) =>
      let hash := Delvetalk.Theory.ObjectiveBendCheckpoint.termHash c.term
      sites.findIdx? (·.matches c.term hash)
    | _ => none
  | _ => none

open Delvetalk.Theory.ObjectiveBendCheckpoint in
/-- A checkpoint's site index and its state tokens. -/
def splitSite : Tokens → Option Nat × Tokens
  | .text edition :: .nat i :: rest => if edition == siteEdition then (some i, rest) else (none, .text edition :: .nat i :: rest)
  | tokens => (none, tokens)

/-- The response type a yield resumes at: its site's. -/
def resumeTypeAt (sites : Option (Array Delvetalk.Site)) : Option Nat → Except String Ty
  | none => .error "checkpoint names no call site of this entry"
  | some i => match sites with
    | some s => match s[i]? with
      | some site => .ok site.type
      | none => .error "checkpoint names no call site of this entry"
    | none => .error "checkpoint does not decode"

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
  let tokens := encodeStateV3 s.dictionary (Delvetalk.Theory.ObjectiveBendDemandCollect.checkpoint s.state)
  Checkpoint.makeFor s.pin s.binding (match s.site with
    | some i => .text siteEdition :: .nat i :: tokens
    | none => tokens)

/-- A segment's outcome with its yield held (`Suspension`), not yet a `Checkpoint`. -/
inductive Step where
  | finished (value : Data) (result : Ty) (ticksUsed : Nat)
  | yielded (plan : Data) (planType responseType : Ty) (suspension : Suspension) (ticksUsed : Nat)
  | exhausted (resource : String) (ticksUsed : Nat)
  | refused (reason : String) (ticksUsed : Nat)

/-- The outcome a caller outside this process sees: a yield's checkpoint made. -/
def Step.outcome : Step → Outcome
  | .finished value result ticks => .finished value result ticks
  | .yielded plan planType responseType suspension ticks =>
    .yielded plan planType responseType suspension.checkpoint ticks
  | .exhausted resource ticks => .exhausted resource ticks
  | .refused reason ticks => .refused reason ticks

open Delvetalk.Theory.ObjectiveBendDemandCollect in
/-- Turn the outcome of a bounded run into a typed step; a yield holds the collected state. -/
def concludeStep (dictionary : Dictionary) (pin : String) (binding : Binding) (bounds : DataBounds) (plan response result : Ty) (b : Budgets) (limits : Limits)
    (outcome : Except (Failure × State × Budget) (Data × Budget))
    (sites : Option (Array Delvetalk.Site) := none) (fetch : Fetch := Fetch.none) : Except String Step :=
  match outcome with
  | .ok (value, remaining) =>
      if !value.conformsUnder bounds result then .error "turn refused: result does not conform to its type"
      else .ok (.finished value result (b.ticks - remaining.ticks))
  | .error (.yielded, state, remaining) =>
      match yieldedPlan fetch limits remaining state with
      | .error (failure, st, rem) =>
          -- The failure names its resource (`Failure.nodes`, `Failure.budget`): nothing re-runs.
          match exhaustedResource limits failure st rem fetch with
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
              | some i => .ok (.yielded extracted.value plan (sites[i]?.map (·.type) |>.getD response) (held (some i)) ticks)
              | none => .error "turn refused: the yielded message has no call site in this entry"
  | .error (failure, st, rem) =>
      match failure, st.control with
      | .refused, .refused (.program reason) => .ok (.refused reason (b.ticks - rem.ticks))
      | _, _ =>
      match exhaustedResource limits failure st rem fetch with
      | some resource => .ok (.exhausted resource (b.ticks - rem.ticks))
      | none => .error ("turn refused: " ++ refusalText failure st)

/-! ## A decoded, checked entry: no packet decoding or re-checking per turn -/

open Delvetalk.Theory.ObjectiveBendCheckpoint Delvetalk.Theory.ObjectiveBendDemandCollect in
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
  let response ← resumeTypeAt entry.sites site
  unless value.conformsUnder assumptions.bounds response do throw "turn refused: response does not conform to the response type"
  let some resumed := Delvetalk.Theory.ObjectiveBendDemandMachine.resume value.term state
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
  fetch : String → Nat → Option Data

def Store.empty : Store := ⟨[], fun _ _ => none⟩

def keyProjection (key : List String) : Data → Data
  | .record fields => .record (key.filterMap fun column => (fields.lookup column).map (column, ·))
  | row => row

/-- What the kernel fetches (`Fetch`): a row within the cell bound (`Bounds.maxCellBytes`; a larger
one is refused as missing, `refusalText`), and a lookup's probe key, that row's projection onto the
lookup's columns, only when they are the relation's declared key (as a set): rows are in the order
of that key alone, so a search by any other columns is refused, never answered wrong. -/
def Store.bounded (store : Store) : Fetch
  | .row field position => (store.fetch field position).filter (·.canonicalBytes ≤ Bounds.maxCellBytes)
  | .key field position columns => do
    let relation ← store.relations.find? (·.field == field)
    unless columns.length == relation.key.length && columns.all relation.key.contains do none
    let row ← (store.fetch field position).filter (·.canonicalBytes ≤ Bounds.maxCellBytes)
    return keyProjection columns row
  | _ => none

/-- A forced row: its relation field, its key projection (a record of the key columns), and
its canonical bytes. -/
structure Read where
  field : String
  key : Data
  bytes : Nat

/-- A segment's reads of its stored relations, as the host judges them (FOUNDATION §9 "Reads and roots"): the rows it
forced; per field, the prefix of the key order a walk or a count observed (`spans`: through position
`reach - 1`, `n + 1` the whole key set: a spine forced at `j` reaches `j + 1`, a count `n + 1`); the
keys a lookup found (`found`, the row forced or not); and the gaps a lookup that missed observed
(`gaps`: no key between the keys at `position - 1` and `position`, none past either end). A lookup
reads its answer, not the prefix below it, and its probes read nothing: where the sought key falls
decides it. -/
structure Reads where
  rows : List Read
  spans : List (String × Nat)
  found : List (String × Data) := []
  gaps : List (String × Option Data × Option Data) := []

def Store.readsOf (store : Store) (state : State) : Reads :=
  let keyAt := fun (field : String) (position : Nat) => do
    let relation ← store.relations.find? (·.field == field)
    return keyProjection relation.key (← store.fetch field position)
  let reached := fun (reach : List (String × Nat)) (field : String) (here : Nat) =>
    match reach.lookup field with
    | some r => if here > r then (field, here) :: reach.filter (·.1 != field) else reach
    | none => (field, here) :: reach
  -- One pass over the heap: rows (`forcedRows`, in heap order), found keys and gaps are pushed
  -- in heap order, spans folded as before.
  let (rows, spans, found, gaps) := state.heap.foldl (fun (rows, spans, found, gaps) cell => match cell with
    | .stored (.row field position) (some _) =>
      let read := do
        let relation ← store.relations.find? (·.field == field)
        let row ← store.fetch field position
        return (⟨field, keyProjection relation.key row, row.canonicalBytes⟩ : Read)
      (match read with | some r => rows.push r | none => rows, spans, found, gaps)
    | .stored (.spine field position _) (some _) => (rows, reached spans field (position + 1), found, gaps)
    | .stored (.size field size) _ => (rows, reached spans field (size + 1), found, gaps)
    | .stored (.found field position) _ => match keyAt field position with
      | some key => (rows, spans, found.push (field, key), gaps)
      | none => (rows, reached spans field (position + 1), found, gaps)
    | .stored (.absent field position) _ =>
      (rows, spans, found, gaps.push (field, if position == 0 then none else keyAt field (position - 1), keyAt field position))
    | _ => (rows, spans, found, gaps)) (#[], [], #[], #[])
  { rows := rows.toList, spans, found := found.toList, gaps := gaps.toList }

def Reads.toJson (r : Reads) : Json :=
  let key := fun (name : String) (k : Option Data) => (k.map fun k => [(name, dataJson k)]).getD []
  Json.mkObj <| [("rows", Json.arr (r.rows.map fun read => Json.mkObj [("field", Lean.toJson read.field),
      ("key", dataJson read.key), ("bytes", Lean.toJson read.bytes)]).toArray),
    ("spans", Json.arr (r.spans.map fun (field, reach) =>
      Json.mkObj [("field", Lean.toJson field), ("reach", Lean.toJson reach)]).toArray)] ++
    (if r.found.isEmpty then [] else
      [("found", Json.arr (r.found.map fun (field, k) => Json.mkObj [("field", Lean.toJson field), ("key", dataJson k)]).toArray)]) ++
    (if r.gaps.isEmpty then [] else [("gaps", Json.arr (r.gaps.map fun (field, after, before) =>
      Json.mkObj ([("field", Lean.toJson field)] ++ key "after" after ++ key "before" before)).toArray)])

/-- The state with its stored relations emptied (`rows {items: []}`): what the kernel checks
of a stored state, and the scalar part the host bounds by `Bounds.maxCellBytes`. -/
def scalarPart (stored : List String) : Data → Data
  | .record fields => .record (fields.map fun (name, value) =>
      if stored.contains name then (name, .variant "rows" (.record [("items", .variant "nil" (.record []))]))
      else (name, value))
  | state => state

/-! ### The state as cells (KERNEL-HANDOFF §15)

The host holds an object's state as its cells: the scalar part (`scalarPart`) and, for each
declared relation, its rows in key order, each with its key's canonical bytes and its own block's
size and CID. A write changes cells; the whole state is made from them only when something reads it
whole (`StateCells.whole`). The state's block is the scalar part's canonical encoding with each
relation's `items` the CID links (DAG-CBOR tag 42) of its chunks, runs of rows whose ends depend on
the rows alone, and the state's CID that block's: a write of one row encodes and hashes that row, its
chunk and the state's block. A changed cell is checked, bounded by `Bounds.maxCellBytes` and charged
its canonical bytes (`Changes`). -/

/-- The rows of a stored relation field of a state record (`rows {items}`), or none. -/
def relationRows (state : Data) (field : String) : Array Data :=
  match state with
  | .record fields => match fields.lookup field with
    | some (.variant "rows" (.record [("items", items)])) => (listItems? items).getD #[]
    | _ => #[]
  | _ => #[]

/-- A row as the host holds it: the row, its key projection's canonical bytes (its place in the
relation's order), and its block's size and binary CID. -/
structure RowCell where
  row : Data
  key : ByteArray
  bytes : Nat
  cid : ByteArray

instance : Inhabited RowCell := ⟨{ row := .record [], key := .empty, bytes := 0, cid := .empty }⟩

def RowCell.of (key : List String) (row : Data) : RowCell :=
  let block := Canonical.encode row
  { row, key := Canonical.encode (keyProjection key row), bytes := block.size, cid := Canonical.cidBytes block }

/-- A CID link: tag 42 over the binary CID with its multibase identity prefix. -/
def link (out : ByteArray) (cid : ByteArray) : ByteArray :=
  ((Canonical.head (Canonical.head out 6 42) 2 (cid.size + 1)).push 0).append cid

/-- A row ends a chunk when its CID's last byte is below 4 (about one row in 64). Chunk boundaries
depend only on the rows, so an edit re-forms only the chunks it falls in. -/
def RowCell.ends (c : RowCell) : Bool := c.cid.get! (c.cid.size - 1) < 4

/-- A run of a relation's rows in key order, ending at a row that `ends` or at the last row: the
position after its last row, and the binary CID of its block (the array of its rows' links). -/
structure Chunk where
  stop : Nat
  cid : ByteArray
  deriving Inhabited

def chunkOf (rows : Array RowCell) (start stop : Nat) : Chunk :=
  let out := Canonical.head (ByteArray.emptyWithCapacity (3 + 41 * (stop - start))) 4 (stop - start)
  { stop, cid := Canonical.cidBytes ((rows.extract start stop).foldl (fun out c => link out c.cid) out) }

/-- The chunks of `rows` from `start` (where a chunk starts) to the end, after `before`; with
`reuse`, the first re-formed chunk past position `past` that ends where a chunk of `reuse` ended
(`shift` rows earlier) is followed by the rest of `reuse`, shifted. -/
def chunksFrom (rows : Array RowCell) (start : Nat) (before : Array Chunk)
    (reuse : Array Chunk := #[]) (past : Nat := 0) (shift : Int := 0) : Array Chunk := Id.run do
  let mut out := before
  let mut first := start
  for position in [start:rows.size] do
    if rows[position]!.ends || position + 1 == rows.size then
      out := out.push (chunkOf rows first (position + 1))
      first := position + 1
      if position + 1 > past then
        if let some j := reuse.findIdx? fun c => (c.stop : Int) + shift == position + 1 then
          return out ++ (reuse.extract (j + 1) reuse.size).map fun c => { c with stop := ((c.stop : Int) + shift).toNat }
  return out

/-- A declared relation's rows in key order (strictly increasing `key` bytes), and their chunks. -/
structure RelationCells where
  field : String
  key : List String
  rows : Array RowCell
  chunks : Array Chunk

def RelationCells.of (field : String) (key : List String) (rows : Array RowCell) : RelationCells :=
  { field, key, rows, chunks := chunksFrom rows 0 #[] }

/-- `r` with `rows`, the result of an edit at `position` that left `shift` more rows: the chunks
before the one holding `position` are kept, and those after the first re-formed chunk past it that
ends where one did. -/
def RelationCells.edited (r : RelationCells) (rows : Array RowCell) (position : Nat) (shift : Int) : RelationCells :=
  let i := (r.chunks.findIdx? (·.stop > position)).getD (r.chunks.size - 1)
  let start := if i == 0 then 0 else r.chunks[i - 1]!.stop
  { r with rows, chunks := chunksFrom rows start (r.chunks.extract 0 i) (r.chunks.extract i r.chunks.size) position shift }

def RelationCells.insertAt (r : RelationCells) (position : Nat) (c : RowCell) : RelationCells :=
  r.edited (r.rows.insertIdx! position c) position 1

def RelationCells.setAt (r : RelationCells) (position : Nat) (c : RowCell) : RelationCells :=
  r.edited (r.rows.set! position c) position 0

def RelationCells.eraseAt (r : RelationCells) (position : Nat) : RelationCells :=
  r.edited (r.rows.eraseIdx! position) position (-1)

/-- The first position whose key is not below `key`: where a row of that key is, or would go. -/
def RelationCells.position (r : RelationCells) (key : ByteArray) : Nat :=
  go 0 r.rows.size
where
  go (low high : Nat) : Nat :=
    if low < high then
      let middle := (low + high) / 2
      if Canonical.bytesLt r.rows[middle]!.key key then go (middle + 1) high else go low middle
    else low
  termination_by high - low

/-- The row of that key, with its position. -/
def RelationCells.find? (r : RelationCells) (key : ByteArray) : Option (Nat × RowCell) :=
  let i := r.position key
  match r.rows[i]? with
  | some c => if c.key == key then some (i, c) else none
  | none => none

/-- The relation value rows make: `rows {items: [...]}`. -/
def relationValue (rows : Array RowCell) : Data :=
  .variant "rows" (.record [("items", listData (rows.map (·.row)))])

/-- The state's block: the scalar part's canonical encoding (`Canonical.writeData`), each relation
field's value the variant `rows {items}` (`Canonical.variantHead`, as `encode` writes a variant)
holding the links of its chunks in key order, each chunk the array of its rows' links. -/
def stateBlock (scalar : Data) (relations : List RelationCells) : ByteArray :=
  match scalar with
  | .record fields =>
    let sorted := Canonical.sortedUnique fields
    sorted.foldl (fun out (name, value) =>
      let out := Canonical.text out name
      match relations.find? (·.field == name) with
      | some r =>
        let out := Canonical.text (Canonical.head (Canonical.variantHead out "rows") 5 1) "items"
        r.chunks.foldl (fun out c => link out c.cid) (Canonical.head out 4 r.chunks.size)
      | none => Canonical.writeData out value)
      (Canonical.head (ByteArray.emptyWithCapacity (64 + relations.foldl (fun n r => n + 41 * r.chunks.size) 0)) 5 sorted.length)
  | other => Canonical.encode other

/-- The whole state the cells make. -/
def wholeOf (scalar : Data) (relations : List (String × Array RowCell)) : Data :=
  match scalar with
  | .record fields => .record (fields.map fun (name, value) =>
      match relations.lookup name with
      | some rows => (name, relationValue rows)
      | none => (name, value))
  | other => other

/-- An object's state as its cells: the scalar part, its relations (in declaration order), the
state's CID, and the whole state, made from the cells when it is first read. -/
structure StateCells where
  scalar : Data
  relations : List RelationCells
  cid : String
  whole : Thunk Data

def StateCells.make (scalar : Data) (relations : List RelationCells) : StateCells :=
  { scalar, relations, cid := Canonical.cid (stateBlock scalar relations),
    whole := Thunk.mk fun _ => wholeOf scalar (relations.map fun r => (r.field, r.rows)) }

/-- A state's cells under `relations` (`[(field, key)]`); its rows are read in the order they stand,
which the host keeps the key order. -/
def StateCells.of (relations : List (String × List String)) (state : Data) : StateCells :=
  let cells := relations.map fun (field, key) => RelationCells.of field key ((relationRows state field).map (RowCell.of key))
  { StateCells.make (scalarPart (relations.map (·.1)) state) cells with whole := Thunk.pure state }

def StateCells.state (c : StateCells) : Data := c.whole.get

def StateCells.relation? (c : StateCells) (field : String) : Option RelationCells :=
  c.relations.find? (·.field == field)

/-- The store a stored turn of this state fetches from: each relation's rows by position. -/
def StateCells.store (c : StateCells) : Store :=
  { relations := c.relations.map fun r => { field := r.field, size := r.rows.size, key := r.key }
    fetch := fun field position => (c.relation? field).bind fun r => r.rows[position]?.map (·.row) }

/-- The cells a write changed: the scalar part when it changed, and each row it put whose key is new
or whose row is (`Changes.of`). -/
structure Changes where
  scalar : Bool
  rows : List (String × RowCell)

/-- What `after` changed of `before` among the rows `put` (the rows a write inserted, upserted or set,
by field): those `after` holds and `before` did not, each once, and the scalar part if its bytes
moved. -/
def Changes.of (before after : StateCells) (put : List (String × RowCell)) : Changes :=
  let held := fun (c : StateCells) (field : String) (row : RowCell) =>
    ((c.relation? field).bind (·.find? row.key)).any (·.2.cid == row.cid)
  let rows := put.foldl (fun acc (field, row) =>
    if held after field row && !held before field row && !acc.any (fun (f, r) => f == field && r.key == row.key)
    then acc ++ [(field, row)] else acc) []
  { scalar := Canonical.encode before.scalar != Canonical.encode after.scalar, rows }

/-- Every cell of a state: what a created object pays. -/
def Changes.all (c : StateCells) : Changes :=
  { scalar := true, rows := c.relations.flatMap fun r => r.rows.toList.map (r.field, ·) }

/-- The canonical bytes a write pays: the scalar part's when it changed, and each changed row's. -/
def Changes.bytes (changes : Changes) (after : StateCells) : Nat :=
  (if changes.scalar then (Canonical.encode after.scalar).size else 0) +
    changes.rows.foldl (fun n (_, row) => n + row.bytes) 0

/-- The first changed cell past the cell bound: `"scalar"` for the scalar part, else the relation
field and the key projection of a row; none when every changed cell fits. -/
def Changes.overBound (changes : Changes) (after : StateCells) : Option (String × Data) :=
  if changes.scalar && (Canonical.encode after.scalar).size > Bounds.maxCellBytes then some ("scalar", .record [])
  else changes.rows.findSome? fun (field, row) =>
    if row.bytes > Bounds.maxCellBytes then
      (after.relation? field).map fun r => (field, keyProjection r.key row.row)
    else none

/-- The list `listData` makes is the chain the conformance theorems speak of. -/
theorem listData_chain (items : Array Data) :
    listData items = Delvetalk.Theory.ObjectiveBendCellConformance.chain items.toList := by
  unfold listData
  rw [← Array.foldr_toList]
  generalize items.toList = l
  induction l with
  | nil => rfl
  | cons x xs ih => simp [List.foldr, ih, Delvetalk.Theory.ObjectiveBendCellConformance.chain]

#assert_axioms listData_chain

/-- The state the changed cells alone make: the scalar part with each relation holding only its
changed rows. When every row a write left as it was conformed, the state after it conforms exactly
when this does (`listData_chain` with `Theory.ObjectiveBendCellConformance`: `field_typed_iff` per
relation field, `relation_typed_iff` per row, for a relation the host declares only over a genuine
`Relation<T>`), so a write is checked on this. -/
def Changes.checked (changes : Changes) (after : StateCells) : Data :=
  wholeOf after.scalar (after.relations.map fun r => (r.field, (changes.rows.filter (·.1 == r.field)).toArray.map (·.2)))

-- The block of a state without relations is its canonical encoding; a relation's items are links,
-- one per row in key order; a changed scalar pays the scalar part, an inserted or replaced row its
-- bytes, an unchanged row nothing; a row past the bound is named by its key.
#guard
  let row := fun (n : Nat) (t : String) => Data.record [("n", .natural n), ("text", .label t)]
  let s := fun (count : Nat) (rows : List Data) =>
    Data.record [("count", .natural count), ("rains", .variant "rows" (.record [("items", listData rows.toArray)]))]
  let decl := [("rains", ["n"])]
  let c := fun (count : Nat) (rows : List Data) => StateCells.of decl (s count rows)
  let changed := fun (a b : StateCells) => Changes.of a b (b.relations.flatMap fun r => r.rows.toList.map (r.field, ·))
  (StateCells.of [] (s 1 [row 0 "a"])).cid == Canonical.cidOf (s 1 [row 0 "a"]) &&
  (let expected := Canonical.text (Canonical.natural (Canonical.text (Canonical.head .empty 5 2) "count") 1) "rains"
   let expected := Canonical.head (Canonical.text (Canonical.head (Canonical.variantHead expected "rows") 5 1) "items") 4 1
   let chunk := Canonical.cidBytes (link (Canonical.head .empty 4 1) (Canonical.cidBytes (Canonical.encode (row 0 "a"))))
   (c 1 [row 0 "a"]).cid == Canonical.cid (link expected chunk)) &&
  (changed (c 1 [row 0 "a"]) (c 1 [row 0 "a"])).bytes (c 1 [row 0 "a"]) == 0 &&
  (changed (c 1 [row 0 "a"]) (c 1 [row 0 "a", row 1 "b"])).bytes (c 1 []) == (Canonical.encode (row 1 "b")).size &&
  (changed (c 1 [row 0 "a"]) (c 1 [row 0 "z"])).bytes (c 1 []) == (Canonical.encode (row 0 "z")).size &&
  (changed (c 1 [row 0 "a"]) (c 2 [row 0 "a"])).bytes (c 2 [row 0 "a"]) == (Canonical.encode (scalarPart ["rains"] (s 2 []))).size &&
  ((Changes.all (c 1 [row 0 "a"])).overBound (c 1 [row 0 "a"])).isNone &&
  (let big := c 1 [row 0 (String.ofList (List.replicate 262144 (Char.ofNat 120)))]
   ((Changes.all big).overBound big).map (·.1) == some "rains") &&
  ((c 1 [row 0 "a", row 1 "b"]).relation? "rains").map (fun r => (r.find? (Canonical.encode (Data.record [("n", .natural 1)]))).map (·.1)) == some (some 1)

-- An edit re-forms only the chunks it falls in, and the chunks it keeps are those a fresh chunking
-- of the rows after it makes: inserts, replacements and erasures at the front, inside, at a chunk's
-- end and at the end of 400 rows (about six chunks).
#guard
  let cell := fun (n : Nat) (t : String) => RowCell.of ["n"] (Data.record [("n", .natural n), ("text", .label t)])
  let r := RelationCells.of "rains" ["n"] ((List.range 400).toArray.map fun i => cell (2 * i) "t")
  let same := fun (a : RelationCells) =>
    a.chunks.map (fun c => (c.stop, c.cid)) == (RelationCells.of a.field a.key a.rows).chunks.map (fun c => (c.stop, c.cid))
  let ends := r.chunks.map (·.stop)
  r.chunks.size > 2 &&
  ([0, 1, 57, 199, 398, 399] ++ ends.toList.map (· - 1)).all fun p =>
    same (r.insertAt p (cell (2 * p + 1) "new")) && same (r.setAt p (cell (2 * p) "changed")) && same (r.eraseAt p) &&
    same (r.insertAt 400 (cell 9999 "last")) && same ((r.eraseAt p).eraseAt 0)

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
  | .key f j columns => (store.fetch f j).map (keyProjection columns)
  | .found f j => do return .record [("value", ← store.fetch f j)]
  | .absent _ _ => some (.record [])
  | .size _ n => some (.natural n)

/-- The canonical bytes of rows `position ..< size` of `field`, counted row by row: `.error` past
`allowance` (no further row fetched or measured), `none` when the store does not answer a row. -/
def rowsBytesWithin (store : Store) (field : String) (position size allowance : Nat) : Except Unit (Option Nat) := do
  let mut total := 0
  for i in [position:size] do
    let some row := store.fetch field i | return none
    total := total + row.canonicalBytes
    if total > allowance then throw ()
  return some total

/-- The canonical bytes of the native data a stored part stands for (`storedData`), within
`allowance` as `rowsBytesWithin` counts them. -/
def storedBytesWithin (store : Store) (allowance : Nat) : Stored → Except Unit (Option Nat)
  | .object fields stored => do
    let scalars := fields.foldl (fun n (name, value) => if (stored.lookup name).isSome then n else n + value.canonicalBytes) 0
    if scalars > allowance then throw ()
    let mut total := scalars
    for (name, size) in stored do
      let some bytes ← rowsBytesWithin store name 0 size (allowance - total) | return none
      total := total + bytes
    return some total
  | .relation f n | .items f n => rowsBytesWithin store f 0 n allowance
  | .spine f j n => rowsBytesWithin store f j n allowance
  | .cons f j n => rowsBytesWithin store f j n allowance
  | .row f j | .key f j _ | .found f j => rowsBytesWithin store f j (j + 1) allowance
  | .absent _ _ | .size _ _ => pure (some 0)

/-- A yielded state, collected as its checkpoint is (`ObjectiveBendDemandCollect.checkpoint`), with
every stored cell it still holds unforced replaced by the native data it stands for, and the stored
fields so replaced: what a checkpoint kept past this process holds, so that resuming it fetches
nothing (forcing a native cell is forcing the stored cell it replaced). The data made is bounded by
`allowance` canonical bytes (the host's checkpoint capacity, which the checkpoint's own encoding,
larger than the data's canonical bytes, meets only if this does): each part is measured row by row
before it is made, and past the allowance the checkpoint is refused before any of it is built. -/
def materializeStored (store : Store) (yielded : State) (allowance : Nat) : Except String (State × List String) := do
  let state := Delvetalk.Theory.ObjectiveBendDemandCollect.checkpoint yielded
  let fieldsOf : Stored → List String
    | .object _ stored => stored.map (·.1)
    | .relation f _ | .items f _ | .spine f _ _ | .cons f _ _ | .row f _ | .key f _ _ | .found f _
    | .absent f _ | .size f _ => [f]
  let mut heap : Array Cell := #[]
  let mut fields : List String := []
  let mut left := allowance
  for cell in state.heap do
    match cell with
    | .stored part none =>
      match storedBytesWithin store left part with
      | .error () => throw "checkpoint exceeds its byte capacity"
      | .ok none => heap := heap.push cell
      | .ok (some bytes) => match storedData store part with
        | some d =>
          heap := heap.push (.native d)
          fields := fields ++ fieldsOf part
          left := left - bytes
        | none => heap := heap.push cell
    | other => heap := heap.push other
  return ({ state with heap }, fields.eraseDups)

-- Review 2026-10-12 kernel 4: 1,024 unread rows of 4 KiB are refused against a 512 KiB checkpoint
-- before any of them is made native; within the allowance they are made.
#guard
  let row := fun (i : Nat) => Data.record [("at", .natural i), ("text", .label (String.ofList (List.replicate 4096 'x')))]
  let store : Store := ⟨[{ field := "rains", size := 1024, key := ["at"] }], fun f i => if f == "rains" && i < 1024 then some (row i) else none⟩
  let yielded : State := ⟨#[.stored (.relation "rains" 1024) none], .yielded 0, []⟩
  (materializeStored store yielded 524288).toOption.isNone &&
    match materializeStored store yielded (1024 * 4200) with
    | .ok (state, fields) => fields == ["rains"] && state.heap.all (· matches .native _)
    | .error _ => false

mutual
/-- What is left of `left` after admitting `d` (`conformsUnder`, and `wellFormed` at `Data`): each
node `perNode`, each record the pairwise comparison of its field names (`eraseDups`); `none` as soon
as the work passes `left`, without walking further. -/
def admissionLeft (perNode left : Nat) : Data → Option Nat
  | .natural _ | .boolean _ | .label _ => if left < perNode then none else some (left - perNode)
  | .record fields =>
    let cost := perNode + fields.length * fields.length
    if left < cost then none else admissionFieldsLeft perNode (left - cost) fields
  | .variant _ payload => if left < perNode then none else admissionLeft perNode (left - perNode) payload
def admissionFieldsLeft (perNode left : Nat) : List (String × Data) → Option Nat
  | [] => some left
  | (_, value) :: rest => match admissionLeft perNode left value with
    | some left => admissionFieldsLeft perNode left rest
    | none => none
end

/-- Whether a turn's data (its arguments, or a response) can be admitted within its ticks: the
conformance and well-formedness checks are metered by the turn's allowance, so a turn with few
ticks cannot make the host walk a large argument (review 2026-10-12 kernel 7). The work is
bounded, not charged: it does not move any turn's `ticksUsed`. -/
def admits (ticks : Nat) (values : List Data) : Bool :=
  -- Each node is visited once by each check; a record's names are compared pairwise.
  (values.foldl (fun left v => left.bind (admissionLeft 2 · v)) (some ticks)).isSome

#guard admissionLeft 1 100 (.record ((List.range 9).map fun i => (toString i, .natural i))) == some 9 &&
  admissionLeft 1 90 (.record ((List.range 9).map fun i => (toString i, .natural i))) == none &&
  admissionLeft 1 1000000 (.record ((List.range 2000).map fun i => (toString i, .natural i))) == none

/-- Start a stored turn on a held entry: its first step and the rows it forced. -/
def startEntry (entry : Delvetalk.CheckedEntry) (arguments : List Data) (store : Store) (binding : Binding)
    (b : Budgets) (dictionary : Option Dictionary := none) : Except String (Step × Reads) := do
  let stored := store.relations.map (·.field)
  unless admits b.ticks (arguments.zipIdx.map fun (v, i) => if i == 0 then scalarPart stored v else v) do
    return (.exhausted "ticks" b.ticks, { rows := [], spans := [] })
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
  unless admits b.ticks [value] do return (.exhausted "ticks" b.ticks, { rows := [], spans := [] })
  let (_, plan, response, result, resumed) ← resumeState entry suspension.state suspension.site value
  runStored entry store suspension.dictionary binding plan response result b
    (Delvetalk.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ suspension.state) resumed

/-- Resume a stored turn's checkpoint whose digest the caller recorded (`issued`). -/
def resumeEntry (entry : Delvetalk.CheckedEntry) (checkpoint : Checkpoint) (issued : String)
    (binding : Binding) (value : Data) (b : Budgets) (store : Store) (dictionary : Option Dictionary := none) :
    Except String (Step × Reads) := do
  let dictionary := dictionary.getD (Dictionary.ofProgram entry.source.term)
  let (state, site) ← checkpointState entry checkpoint issued binding dictionary
  unless admits b.ticks [value] do return (.exhausted "ticks" b.ticks, { rows := [], spans := [] })
  let (_, plan, response, result, resumed) ← resumeState entry state site value
  runStored entry store dictionary binding plan response result b
    (Delvetalk.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ state) resumed

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
    (Delvetalk.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ state) b.bytes b.ticks resumed store.bounded)

end Delvetalk.Turn
