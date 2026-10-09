/- Activity turns: run an activity to its next `perform`, hand the Plan out as
   data with a checkpoint, and continue it when resumed with a response.
   The checkpoint is the collected machine state as canonical tokens
   (Theory.ObjectiveBendCheckpoint). The type of the response is never taken
   from the client: it is re-derived from the verified artifact. -/
import Compiler.ObjectiveBendFrontEnd
import Compiler.ObjectiveBendDataWire
import Theory.ObjectiveBendDemandData
import Theory.ObjectiveBendCheckpoint
import Theory.ObjectiveBendCheckpointRoundTrip
import Theory.ObjectiveBendDemandCollect
import Theory.ObjectiveBendDemandSettleProofs
import Theory.ObjectiveBendDataConformance
import Delvetalk.Limits
import Delvetalk.Canonical

open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData
open Minidregg.Compiler.ObjectiveBendDataWire

namespace Delvetalk.Turn

/-- Re-address the original annotation table when application wraps its term.
The argument subtree is annotation-free first-order data, never raw code. -/
def applyArgument (source : AnnotatedTerm) (argument : Term)
    (extras : List (List Nat × LambdaAnnotation) := []) : AnnotatedTerm :=
  { source with
    term := .app source.term argument
    annotations := fun position => match position with
      | 0 :: rest => source.annotations rest
      | 1 :: rest => (extras.find? (·.1 == rest)).map (·.2)
      | _ => none }

def bounded (j : Json) (key : String) (fallback cap : Nat) : Except String Nat := do
  let value ← match j.getObjVal? key with
    | .error _ => pure fallback
    | .ok x => jsonNat x
  if value > cap then throw (key ++ " exceeds package capacity")
  return value

/- Closed first-order data as a term. Unlike `run` arguments, variants are
admitted: a response to a Plan is usually a sum. -/
mutual
def dataTerm : Data → Term
  | .natural n => .nat n
  | .boolean b => .boolean b
  | .label s => .label s
  | .record fields => .record (dataFields fields)
  | .variant label payload => .inject label (dataTerm payload)
def dataFields : List (String × Data) → List (String × Term)
  | [] => []
  | (k,v) :: rest => (k, dataTerm v) :: dataFields rest
end

/-- A variant argument is injected at its declared sum, never guessed from one
label: give each injection of closed data the annotation its declared type
fixes (payload type, sum or recursive variable). Positions follow the checker:
an injection's payload is child 0, a record's field `i` is child `i`. -/
partial def annotateData (bounds : DataBounds) (expected : Ty) (data : Data) (path : List Nat) :
    List (List Nat × LambdaAnnotation) :=
  match data with
  | .variant tag payload =>
    let row? := match expected with
      | .variant row => some row
      | .variable index => match bounds.lookup index with
          | some (.variant row) => some row
          | _ => none
      | _ => none
    match row? with
    | none => []
    | some row => match row.lookup bounds Ty.dataFuel tag with
      | none => []
      | some member =>
        (path, ⟨member, expected, .unrestricted, .reusable⟩) :: annotateData bounds member payload (path ++ [0])
  | .record fields =>
    let rec memberOf : Ty → String → Option Ty
      | .field n m tail, name => if n == name then some m else memberOf tail name
      | _, _ => none
    (fields.zipIdx.map fun ((name, value), i) => match memberOf expected name with
      | some member => annotateData bounds member value (path ++ [i])
      | none => []).flatten
  | _ => []

/-- The singleton type of closed data: the type an argument of the universal type
`Data` is checked at inside its `toData` injection. Every injection is annotated
at a one-label sum naming exactly its own label. -/
instance : Inhabited Ty := ⟨.natural⟩
partial def shapeType : Data → Ty
  | .natural _ => .natural
  | .boolean _ => .boolean
  | .label _ => .label
  | .record fields => fields.foldr (fun (name, value) tail => .field name (shapeType value) tail) .emptyRow
  | .variant tag payload => .variant (.field tag (shapeType payload) .emptyRow)

/-- An argument as a term with its injection annotations. At the universal type the
host has already decided conformance (well-formed data), so the value is injected
at its own shape. -/
def argumentAt (bounds : DataBounds) (domain : Ty) (v : Data) :
    Except String (Term × List (List Nat × LambdaAnnotation)) :=
  if domain == .data then
    if !v.wellFormed then .error "turn refused: argument does not conform to Data (repeated field)"
    else .ok (.toData (dataTerm v), annotateData bounds (shapeType v) v [0])
  else .ok (dataTerm v, annotateData bounds domain v [])

def failureName : Failure → String
  | .tickExhausted => "tick budget exhausted"
  | .budget => "node or byte budget exhausted"
  | .duplicateField => "duplicate field in result"
  | .executableValue => "result is executable, not data"
  | .suspended => "heap or stack capacity exhausted"
  | .divergent => "divergent (blackhole)"
  | .refused => "machine refused the program"
  | .yielded => "yielded"

/-- The activity shape a turn requires of a checked type. -/
def activityShape (assumptions : Assumptions) (type : Ty) : Except String (Ty × Ty × Ty) :=
  let bounds := assumptions.bounds
  let rigid := assumptions.rigid
  let isData := fun (t : Ty) => t.isDataUnder bounds rigid Ty.dataFuel []
  match type with
  | .computation plan response result =>
      if !plan.isPlanUnder bounds rigid then .error "turn refused: Plan type is not a first-order sum"
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
def tokensJson (tokens : Tokens) : Json := Json.arr (tokens.map tokenJson).toArray

open Minidregg.Theory.ObjectiveBendCheckpoint in
def tokensOfJson (json : Json) : Except String Tokens := do
  let items ← json.getArr?
  items.toList.mapM fun item => do
    match item.getObjVal? "n" with
    | .ok n =>
        let text ← n.getStr?
        let some value := text.toNat? | throw "checkpoint does not decode"
        if toString value != text then throw "checkpoint does not decode"
        return Token.nat value
    | .error _ => return Token.text (← item.getObjValAs? String "s")

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
def checkpointDigest (packetSha256 object principal intent rootsDigest : String) (tokens : Tokens) : String :=
  Delvetalk.Canonical.cidJson (Json.mkObj [("packetSha256", Lean.toJson packetSha256),
    ("object", Lean.toJson object), ("principal", Lean.toJson principal), ("intent", Lean.toJson intent),
    ("rootsDigest", Lean.toJson rootsDigest), ("tokens", tokensJson tokens)])

def Checkpoint.make (packet : Json) (binding : Binding) (tokens : Minidregg.Theory.ObjectiveBendCheckpoint.Tokens) :
    Checkpoint :=
  let p := packetDigest packet
  ⟨p, binding.object, binding.principal, binding.intent, binding.rootsDigest, tokens,
    checkpointDigest p binding.object binding.principal binding.intent binding.rootsDigest tokens⟩

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
def exhaustedResource (limits : Limits) (failure : Failure) (state : State) (remaining : Budget) :
    Option String :=
  match failure with
  | .tickExhausted => some "ticks"
  | .budget => some (if remaining.nodes == 0 then "nodes" else "bytes")
  | .suspended =>
      let next := stepRaw state
      if next.heap.size > limits.heap then some "heap"
      else if next.stack.length > limits.stack then some "stack"
      else some "bytes"
  | _ => none

open Minidregg.Theory.ObjectiveBendCheckpoint Minidregg.Theory.ObjectiveBendDemandCollect in
/-- Turn the outcome of a bounded run into a typed outcome. -/
def conclude (packet : Json) (binding : Binding) (bounds : DataBounds) (plan response result : Ty) (b : Budgets) (limits : Limits)
    (outcome : Except (Failure × State × Budget) (Data × Budget)) : Except String Delvetalk.Turn.Outcome :=
  match outcome with
  | .ok (value, remaining) =>
      if !value.conformsUnder bounds result then .error "turn refused: result does not conform to its type"
      else .ok (.finished value result (b.ticks - remaining.ticks))
  | .error (.yielded, state, remaining) =>
      match yieldedPlan limits remaining state with
      | .error (failure, st, rem) =>
          -- A materialization budget failure is nodes when it vanishes with unlimited nodes.
          let resource? := match failure with
            | .budget => some (match yieldedPlan limits {remaining with nodes := 1 <<< 40} state with
                | .error (.budget, _, _) => "bytes"
                | _ => "nodes")
            | _ => exhaustedResource limits failure st rem
          match resource? with
          | some resource => .ok (.exhausted resource (b.ticks - rem.ticks))
          | none => .error ("turn refused: " ++ failureName failure)
      | .ok extracted =>
          if !extracted.value.conformsUnder bounds plan then .error "turn refused: Plan does not conform to its type"
          else .ok (.yielded extracted.value plan response
            (Checkpoint.make packet binding (encodeState (checkpoint extracted.state)))
            (b.ticks - extracted.remaining.ticks))
  | .error (failure, st, rem) =>
      match exhaustedResource limits failure st rem with
      | some resource => .ok (.exhausted resource (b.ticks - rem.ticks))
      | none => .error ("turn refused: " ++ failureName failure)

/-- `packet` belongs to an artifact the caller has already verified. -/
def startActivity (packet : Json) (arguments : List Data) (binding : Binding) (b : Budgets) : Except String Delvetalk.Turn.Outcome := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let some entry := check decoded.source [] decoded.fuel | throw "package refused by Mini type checker"
  let mut source := decoded.source
  let mut entryType := entry.type
  for v in arguments do
    let (domain, rest) := match entryType with
      | .arrow _ _ d c => (d, c)
      | other => (other, other)
    let bounds := decoded.source.assumptions.bounds
    if domain.isDataUnder bounds [] Ty.dataFuel [] && !v.conformsUnder bounds domain then
      throw "turn refused: argument does not conform to its type"
    let (term, extras) ← argumentAt bounds domain v
    source := applyArgument source term extras
    entryType := rest
  let some checked := check source [] decoded.fuel | throw "applied package refused by Mini type checker"
  let (plan, response, result) ← activityShape source.assumptions checked.type
  let capacities : Limits := ⟨b.heap, b.stack⟩
  let outcome := (executeWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ source.term).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude packet binding source.assumptions.bounds plan response result b capacities outcome

open Minidregg.Theory.ObjectiveBendCheckpoint Minidregg.Theory.ObjectiveBendDemandCollect in
def resumeActivity (packet : Json) (checkpoint : Checkpoint) (binding : Binding) (value : Data) (b : Budgets) :
    Except String Delvetalk.Turn.Outcome := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let some entry := check decoded.source [] decoded.fuel | throw "package refused by Mini type checker"
  let (plan, response, result) ← activityShape decoded.source.assumptions (peelArrows Bounds.entryArrowDepth entry.type)
  unless checkpoint.packetSha256 == packetDigest packet do throw "checkpoint belongs to another package"
  unless checkpoint.digest == checkpointDigest checkpoint.packetSha256 checkpoint.object checkpoint.principal
      checkpoint.intent checkpoint.rootsDigest checkpoint.tokens do throw "checkpoint digest mismatch"
  unless checkpoint.object == binding.object do throw "checkpoint belongs to another object"
  unless checkpoint.principal == binding.principal do throw "checkpoint belongs to another principal"
  unless checkpoint.intent == binding.intent do throw "checkpoint belongs to another intent"
  unless checkpoint.rootsDigest == binding.rootsDigest do throw "checkpoint was taken under different roots"
  let some state := decodeState checkpoint.tokens | throw "checkpoint does not decode"
  unless value.conformsUnder decoded.source.assumptions.bounds response do throw "turn refused: response does not conform to the response type"
  let some resumed := Minidregg.Theory.ObjectiveBendDemandMachine.resume (dataTerm value) state
    | throw "turn refused: checkpoint is not a yielded state"
  let capacities := limitsPast ⟨b.heap, b.stack⟩ state
  let outcome := (executeStateWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ resumed).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude packet binding decoded.source.assumptions.bounds plan response result b capacities outcome

def start (packet arguments limits request : Json) : Except String Json := do
  let values ← (← arguments.getArr?).toList.mapM (decodeData Bounds.dataWireDepth)
  return (← startActivity packet values (← Binding.ofJson request) (← budgets limits)).toJson

def resumeTurn (packet checkpointJson responseJson limits request : Json) : Except String Json := do
  let checkpoint ← Checkpoint.fromJson checkpointJson
  let value ← decodeData Bounds.dataWireDepth responseJson
  return (← resumeActivity packet checkpoint (← Binding.ofJson request) value (← budgets limits)).toJson

end Delvetalk.Turn
