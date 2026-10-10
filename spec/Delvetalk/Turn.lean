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

open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData
open Minidregg.Compiler.ObjectiveBendDataWire
open Minidregg.Theory.ObjectiveBendCheckpoint (Dictionary encodeStateV2 decodeStateAny checkpointEditionV2)

namespace Delvetalk.Turn

/-- Re-address the original annotation table when application wraps its term.
The argument subtree is annotation-free first-order data, never raw code. -/
def applyArgument (source : AnnotatedTerm) (argument : Term)
    (extras : Delvetalk.AnnotationTree := .empty) : AnnotatedTerm :=
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

private instance : Inhabited Term := ⟨.nat 0⟩

mutual
/-- A value's annotations at its own shape (`shapeAnnotations` as a tree) with that shape
(`Data.shapeType`), built bottom-up: each node's shape type is made once from its
children's, so a long list costs linear time and space (recomputing `shapeType` per
injection was quadratic). -/
def shapeTree : Data → Delvetalk.AnnotationTree × Ty
  | .variant tag payload =>
    let (tree, payloadShape) := shapeTree payload
    let shape := Ty.variant (.field tag payloadShape .emptyRow)
    (.node (some ⟨payloadShape, shape, .unrestricted, .reusable⟩) #[tree], shape)
  | .record fields => let (trees, row) := shapeFieldTrees fields; (.node none trees.toArray, row)
  | .natural _ => (.empty, .natural)
  | .boolean _ => (.empty, .boolean)
  | .label _ => (.empty, .label)
def shapeFieldTrees : List (String × Data) → List Delvetalk.AnnotationTree × Ty
  | [] => ([], .emptyRow)
  | (name, value) :: rest =>
    let (tree, shape) := shapeTree value
    let (trees, row) := shapeFieldTrees rest
    (tree :: trees, .field name shape row)
end

/-- An argument as a term with its injection annotations, directed by its declared
type: a variant is injected at its declared sum, never guessed from one label (the
annotation names its payload type and its sum or recursive variable), and a value
at a universal position (`Data`) is wrapped in `toData` and checked at its own shape
(`Data.shapeType`), the host having already decided its conformance. Positions follow
the checker: an injection's payload is child 0, a record's field `i` is child `i`,
the operand of `toData` child 0. The term itself is `Data.term` up to those `toData`
wrappers. -/
partial def quoteAt (bounds : DataBounds) (expected : Ty) (data : Data) : Term × Delvetalk.AnnotationTree :=
  if expected == .data then (.toData data.term, .node none #[(shapeTree data).1]) else
  match data with
  | .variant tag payload =>
    let row? := match expected with
      | .variant row => some row
      | .variable index => match bounds.lookup index with
          | some (.variant row) => some row
          | _ => none
      | _ => none
    match row? >>= fun row => row.lookup bounds Ty.dataFuel tag with
    | none => (data.term, .empty)
    | some member =>
      let (payloadTerm, annotations) := quoteAt bounds member payload
      (.inject tag payloadTerm, .node (some ⟨member, expected, .unrestricted, .reusable⟩) #[annotations])
  | .record fields =>
    let rec memberOf : Ty → String → Option Ty
      | .field n m tail, name => if n == name then some m else memberOf tail name
      | _, _ => none
    let quoted := fields.map fun (name, value) => match memberOf expected name with
      | some member => (name, quoteAt bounds member value)
      | none => (name, (value.term, .empty))
    (.record (quoted.map fun (name, term, _) => (name, term)), .node none (quoted.map (·.2.2)).toArray)
  | other => (other.term, .empty)

def argumentAt (bounds : DataBounds) (domain : Ty) (v : Data) :
    Except String (Term × Delvetalk.AnnotationTree) :=
  if domain == .data && !v.wellFormed then .error "turn refused: argument does not conform to Data (repeated field)"
  else .ok (quoteAt bounds domain v)

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
  | _, _ => failureName failure

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
/-- A v2 token as itself: a natural a JSON number, a text a JSON string, a string
reference a negative number (`-(i+1)`). -/
def tokenJsonV2 : Token → Json
  | .nat n => toJson n
  | .text s => toJson s
  | .str i => toJson (-((i : Int) + 1))

open Minidregg.Theory.ObjectiveBendCheckpoint in
/-- The JSON of a checkpoint's tokens: a v1 checkpoint's as before (`{"n"}`/`{"s"}` objects,
so its digest is unchanged), any other as bare numbers and strings. -/
def tokensJson (tokens : Tokens) : Json :=
  match tokens with
  | .text edition :: _ =>
    if edition == checkpointEdition then Json.arr (tokens.map tokenJson).toArray
    else Json.arr (tokens.map tokenJsonV2).toArray
  | _ => Json.arr (tokens.map tokenJsonV2).toArray

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
    | _ =>
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

/-- The dictionary a packet's checkpoints are written against: its entry term's. -/
def programDictionary (packet : Json) : Dictionary :=
  match decodePacket packet with
  | .ok decoded => Dictionary.ofProgram decoded.source.term
  | .error _ => {}

open Minidregg.Theory.ObjectiveBendCheckpoint Minidregg.Theory.ObjectiveBendDemandCollect in
/-- Turn the outcome of a bounded run into a typed outcome. -/
def conclude (dictionary : Minidregg.Theory.ObjectiveBendCheckpoint.Dictionary) (pin : String) (binding : Binding) (bounds : DataBounds) (plan response result : Ty) (b : Budgets) (limits : Limits)
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
          | none => .error ("turn refused: " ++ refusalText failure st)
      | .ok extracted =>
          if !extracted.value.conformsUnder bounds plan then .error "turn refused: Plan does not conform to its type"
          else .ok (.yielded extracted.value plan response
            (Checkpoint.makeFor pin binding (encodeStateV2 dictionary (checkpoint extracted.state)))
            (b.ticks - extracted.remaining.ticks))
  | .error (failure, st, rem) =>
      match exhaustedResource limits failure st rem with
      | some resource => .ok (.exhausted resource (b.ticks - rem.ticks))
      | none => .error ("turn refused: " ++ refusalText failure st)

/-- `packet` belongs to an artifact the caller has already verified. The checked, applied entry of an activity and its Plan/response/result types. -/
def prepareStart (packet : Json) (arguments : List Data) :
    Except String (AnnotatedTerm × Ty × Ty × Ty) := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let some entry := check decoded.source [] decoded.fuel | throw "package refused by Mini type checker"
  let mut source := decoded.source
  let mut entryType := entry.type
  let mut fuel := decoded.fuel
  for v in arguments do
    let (domain, rest) := match entryType with
      | .arrow _ _ d c => (d, c)
      | other => (other, other)
    let bounds := decoded.source.assumptions.bounds
    if domain.isDataUnder bounds [] Ty.dataFuel [] && !v.conformsUnder bounds domain then
      throw "turn refused: argument does not conform to its type"
    let (term, extras) ← argumentAt bounds domain v
    source := applyArgument source term extras
    fuel := Delvetalk.argumentFuel fuel term
    entryType := rest
  let some checked := check source [] fuel | throw "applied package refused by Mini type checker"
  let (plan, response, result) ← activityShape source.assumptions checked.type
  return (source, plan, response, result)

def startActivity (packet : Json) (arguments : List Data) (binding : Binding) (b : Budgets) : Except String Delvetalk.Turn.Outcome := do
  let (source, plan, response, result) ← prepareStart packet arguments
  let capacities : Limits := ⟨b.heap, b.stack⟩
  let outcome := (executeWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ source.term).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude (programDictionary packet) (packetDigest packet) binding source.assumptions.bounds plan response result b capacities outcome

open Minidregg.Theory.ObjectiveBendCheckpoint Minidregg.Theory.ObjectiveBendDemandCollect in
def prepareResume (packet : Json) (checkpoint : Checkpoint) (binding : Binding) (value : Data) :
    Except String (DataBounds × Ty × Ty × Ty × State × State) := do
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
  let some state := decodeStateAny (Dictionary.ofProgram decoded.source.term) checkpoint.tokens
    | throw "checkpoint does not decode"
  unless value.conformsUnder decoded.source.assumptions.bounds response do throw "turn refused: response does not conform to the response type"
  let some resumed := Minidregg.Theory.ObjectiveBendDemandMachine.resume value.term state
    | throw "turn refused: checkpoint is not a yielded state"
  return (decoded.source.assumptions.bounds, plan, response, result, state, resumed)

open Minidregg.Theory.ObjectiveBendDemandCollect in
def resumeActivity (packet : Json) (checkpoint : Checkpoint) (binding : Binding) (value : Data) (b : Budgets) :
    Except String Delvetalk.Turn.Outcome := do
  let (bounds, plan, response, result, state, resumed) ← prepareResume packet checkpoint binding value
  let capacities := limitsPast ⟨b.heap, b.stack⟩ state
  let outcome := (executeStateWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ resumed).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude (programDictionary packet) (packetDigest packet) binding bounds plan response result b capacities outcome

/-! ## A decoded, checked entry: no packet decoding or re-checking per turn -/

/-- The checked application of a held entry to turn arguments, and its activity shape:
each argument is checked alone and composed with the entry's own derivation. -/
def prepareStartEntry (entry : Delvetalk.CheckedEntry) (arguments : List Data) :
    Except String (Delvetalk.CheckedEntry × Ty × Ty × Ty) := do
  let bounds := entry.source.assumptions.bounds
  let mut current := entry
  for v in arguments do
    let domain := match callable current.type with
      | .arrow _ _ d _ => d
      | other => other
    if domain.isDataUnder bounds [] Ty.dataFuel [] && !v.conformsUnder bounds domain then
      throw "turn refused: argument does not conform to its type"
    let (term, extras) ← argumentAt bounds domain v
    current ← current.apply term extras
  let (plan, response, result) ← activityShape current.source.assumptions current.type
  return (current, plan, response, result)

/-- `startActivity` on a held entry. -/
def startEntry (entry : Delvetalk.CheckedEntry) (arguments : List Data) (binding : Binding) (b : Budgets)
    (dictionary : Option Minidregg.Theory.ObjectiveBendCheckpoint.Dictionary := none) :
    Except String Delvetalk.Turn.Outcome := do
  let (applied, plan, response, result) ← prepareStartEntry entry arguments
  let capacities : Limits := ⟨b.heap, b.stack⟩
  let outcome := (executeWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ applied.source.term).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude (dictionary.getD (Dictionary.ofProgram entry.source.term)) entry.pin binding applied.source.assumptions.bounds plan response result b capacities outcome

open Minidregg.Theory.ObjectiveBendCheckpoint Minidregg.Theory.ObjectiveBendDemandCollect in
def prepareResumeEntry (entry : Delvetalk.CheckedEntry) (checkpoint : Checkpoint) (binding : Binding) (value : Data)
    (dictionary : Option Dictionary := none) :
    Except String (DataBounds × Ty × Ty × Ty × State × State) := do
  let assumptions := entry.source.assumptions
  let (plan, response, result) ← activityShape assumptions (peelArrows Bounds.entryArrowDepth entry.type)
  unless checkpoint.packetSha256 == entry.pin do throw "checkpoint belongs to another package"
  unless checkpoint.digest == checkpointDigest checkpoint.packetSha256 checkpoint.object checkpoint.principal
      checkpoint.intent checkpoint.rootsDigest checkpoint.tokens do throw "checkpoint digest mismatch"
  unless checkpoint.object == binding.object do throw "checkpoint belongs to another object"
  unless checkpoint.principal == binding.principal do throw "checkpoint belongs to another principal"
  unless checkpoint.intent == binding.intent do throw "checkpoint belongs to another intent"
  unless checkpoint.rootsDigest == binding.rootsDigest do throw "checkpoint was taken under different roots"
  let some state := decodeStateAny (dictionary.getD (Dictionary.ofProgram entry.source.term)) checkpoint.tokens
    | throw "checkpoint does not decode"
  unless value.conformsUnder assumptions.bounds response do throw "turn refused: response does not conform to the response type"
  let some resumed := Minidregg.Theory.ObjectiveBendDemandMachine.resume value.term state
    | throw "turn refused: checkpoint is not a yielded state"
  return (assumptions.bounds, plan, response, result, state, resumed)

open Minidregg.Theory.ObjectiveBendDemandCollect in
/-- `resumeActivity` on a held entry. -/
def resumeEntry (entry : Delvetalk.CheckedEntry) (checkpoint : Checkpoint) (binding : Binding) (value : Data)
    (b : Budgets) (dictionary : Option Minidregg.Theory.ObjectiveBendCheckpoint.Dictionary := none) :
    Except String Delvetalk.Turn.Outcome := do
  let dictionary := dictionary.getD (Dictionary.ofProgram entry.source.term)
  let (bounds, plan, response, result, state, resumed) ← prepareResumeEntry entry checkpoint binding value (some dictionary)
  let capacities := limitsPast ⟨b.heap, b.stack⟩ state
  let outcome := (executeStateWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ resumed).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude dictionary entry.pin binding bounds plan response result b capacities outcome

def wantsProfile (request : Json) : Bool := (request.getObjValAs? Bool "profile").toOption.getD false

def start (packet arguments limits request : Json) : Except String Json := do
  let values ← (← arguments.getArr?).toList.mapM (decodeData Bounds.dataWireDepth)
  let b ← budgets limits
  let reply := (← startActivity packet values (← Binding.ofJson request) b).toJson
  if !wantsProfile request then return reply
  let (source, _) ← prepareStart packet values
  return reply.setObjVal! "profile" (Delvetalk.Profile.profile ⟨b.heap, b.stack⟩ b.bytes b.ticks (initial source.term))

def startEntryJson (entry : Delvetalk.CheckedEntry) (arguments limits request : Json) : Except String Json := do
  let values ← (← arguments.getArr?).toList.mapM (decodeData Bounds.dataWireDepth)
  let b ← budgets limits
  let reply := (← startEntry entry values (← Binding.ofJson request) b).toJson
  if !wantsProfile request then return reply
  let (applied, _) ← prepareStartEntry entry values
  return reply.setObjVal! "profile" (Delvetalk.Profile.profile ⟨b.heap, b.stack⟩ b.bytes b.ticks (initial applied.source.term))

def resumeEntryJson (entry : Delvetalk.CheckedEntry) (checkpointJson responseJson limits request : Json) :
    Except String Json := do
  let checkpoint ← Checkpoint.fromJson checkpointJson
  let value ← decodeData Bounds.dataWireDepth responseJson
  let b ← budgets limits
  let binding ← Binding.ofJson request
  let reply := (← resumeEntry entry checkpoint binding value b).toJson
  if !wantsProfile request then return reply
  let (_, _, _, _, state, resumed) ← prepareResumeEntry entry checkpoint binding value
  return reply.setObjVal! "profile"
    (Delvetalk.Profile.profile (Minidregg.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ state) b.bytes b.ticks resumed)

def resumeTurn (packet checkpointJson responseJson limits request : Json) : Except String Json := do
  let checkpoint ← Checkpoint.fromJson checkpointJson
  let value ← decodeData Bounds.dataWireDepth responseJson
  let b ← budgets limits
  let binding ← Binding.ofJson request
  let reply := (← resumeActivity packet checkpoint binding value b).toJson
  if !wantsProfile request then return reply
  let (_, _, _, _, state, resumed) ← prepareResume packet checkpoint binding value
  return reply.setObjVal! "profile"
    (Delvetalk.Profile.profile (Minidregg.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ state) b.bytes b.ticks resumed)

end Delvetalk.Turn
