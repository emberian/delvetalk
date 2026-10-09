/- Running a compiled method's activity without re-reading its packet. `Delvetalk.Turn`'s
   `startActivity`/`resumeActivity` take the packet as JSON and, on every segment, decode it,
   type-check it, check the applied term again and hash the whole packet for the checkpoint
   (110 ms a segment for Garden's closure). The host compiles a method once and keeps a
   `Prepared`: the decoded source, its checked entry type and the packet's CID (the artifact's
   `packetSha256`, computed by the compiler). A segment then only applies its data arguments
   (each conforming to its declared domain, as the kernel requires), runs, and concludes.

   What is not repeated per segment, and why that is sound: the packet was decoded and checked
   when it was prepared; an argument is closed first-order data that conforms to the arrow's
   domain (checked here exactly as `prepareStart` checks it), so the application has the arrow's
   codomain, whose activity shape is read off the checked type (`activityShape`) instead of
   re-checking the applied term. Everything else (budgets, the machine, conclusion, checkpoint
   binding and digest checks on resume) is the kernel's own code. When the kernel lands its
   decoded-packet session cache this file goes. -/
import Delvetalk.Turn

namespace Delvetalk.Host.Run
open Lean (Json)
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData
open Delvetalk.Turn

structure Prepared where
  /-- The packet's CID, as the checkpoint names it (`packetDigest packet`). -/
  digest : String
  source : AnnotatedTerm
  entryType : Ty


/-- Decode and check a packet once. `digest` is the compiler's `packetSha256` of it. -/
def prepare (packet : Json) (digest : String) : Except String Prepared := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let some entry := check decoded.source [] decoded.fuel | throw "package refused by Mini type checker"
  return { digest, source := decoded.source, entryType := entry.type }

/-- The kernel's `conclude`, with the checkpoint named by the prepared digest instead of a hash
    of the packet's JSON. -/
def conclude (p : Prepared) (binding : Delvetalk.Turn.Binding) (bounds : DataBounds) (plan response result : Ty) (b : Budgets)
    (limits : Limits) (outcome : Except (Failure × State × Budget) (Data × Budget)) : Except String Delvetalk.Turn.Outcome :=
  let make := fun (tokens : Minidregg.Theory.ObjectiveBendCheckpoint.Tokens) =>
    (⟨p.digest, binding.object, binding.principal, binding.intent, binding.rootsDigest, tokens,
      checkpointDigest p.digest binding.object binding.principal binding.intent binding.rootsDigest tokens⟩ : Delvetalk.Turn.Checkpoint)
  match outcome with
  | .ok (value, remaining) =>
      if !value.conformsUnder bounds result then .error "turn refused: result does not conform to its type"
      else .ok (.finished value result (b.ticks - remaining.ticks))
  | .error (.yielded, state, remaining) =>
      match yieldedPlan limits remaining state with
      | .error (failure, st, rem) =>
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
            (make (Minidregg.Theory.ObjectiveBendCheckpoint.encodeState
              (Minidregg.Theory.ObjectiveBendDemandCollect.checkpoint extracted.state)))
            (b.ticks - extracted.remaining.ticks))
  | .error (failure, st, rem) =>
      match exhaustedResource limits failure st rem with
      | some resource => .ok (.exhausted resource (b.ticks - rem.ticks))
      | none => .error ("turn refused: " ++ failureName failure)

/-- The source applied to data arguments, each conforming to its arrow's domain, and the type
    left after them. -/
def apply (p : Prepared) (arguments : List Data) : Except String (AnnotatedTerm × Ty) := do
  let bounds := p.source.assumptions.bounds
  let mut source := p.source
  let mut entryType := p.entryType
  for v in arguments do
    let .arrow _ _ domain rest := entryType | throw "turn refused: too many arguments"
    if domain.isDataUnder bounds [] Ty.dataFuel [] && !v.conformsUnder bounds domain then
      throw "turn refused: argument does not conform to its type"
    unless domain == .data || domain.isDataUnder bounds [] Ty.dataFuel [] do
      throw "turn refused: an argument position is not data"
    let (term, extras) ← argumentAt bounds domain v
    source := applyArgument source term extras
    entryType := rest
  return (source, entryType)

/-- The applied source and its activity shape, as `prepareStart` gives them. -/
def applied (p : Prepared) (arguments : List Data) : Except String (AnnotatedTerm × Ty × Ty × Ty) := do
  let (source, entryType) ← apply p arguments
  let (plan, response, result) ← activityShape p.source.assumptions entryType
  return (source, plan, response, result)

/-- A pure definition applied to data arguments and run to its value under the budgets: the
    outcome is `finished` or `exhausted` (a pure definition never yields). -/
def evaluate (p : Prepared) (arguments : List Data) (b : Budgets) : Except String Delvetalk.Turn.Outcome := do
  let (source, result) ← apply p arguments
  unless result.isDataUnder p.source.assumptions.bounds p.source.assumptions.rigid Ty.dataFuel [] do
    throw "the definition does not return data"
  let capacities : Limits := ⟨b.heap, b.stack⟩
  let outcome := (executeWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ source.term).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude p ⟨"", "", "", ""⟩ source.assumptions.bounds .emptyRow .emptyRow result b capacities outcome

def start (p : Prepared) (arguments : List Data) (binding : Delvetalk.Turn.Binding) (b : Budgets) : Except String Delvetalk.Turn.Outcome := do
  let (source, plan, response, result) ← applied p arguments
  let capacities : Limits := ⟨b.heap, b.stack⟩
  let outcome := (executeWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ source.term).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude p binding source.assumptions.bounds plan response result b capacities outcome

/-- The resumed machine state, after the checks `prepareResume` makes. -/
def resumed (p : Prepared) (checkpoint : Delvetalk.Turn.Checkpoint) (binding : Delvetalk.Turn.Binding) (value : Data) :
    Except String (Ty × Ty × Ty × State × State) := do
  let (plan, response, result) ← activityShape p.source.assumptions (peelArrows Bounds.entryArrowDepth p.entryType)
  unless checkpoint.packetSha256 == p.digest do throw "checkpoint belongs to another package"
  unless checkpoint.digest == checkpointDigest checkpoint.packetSha256 checkpoint.object checkpoint.principal
      checkpoint.intent checkpoint.rootsDigest checkpoint.tokens do throw "checkpoint digest mismatch"
  unless checkpoint.object == binding.object do throw "checkpoint belongs to another object"
  unless checkpoint.principal == binding.principal do throw "checkpoint belongs to another principal"
  unless checkpoint.intent == binding.intent do throw "checkpoint belongs to another intent"
  unless checkpoint.rootsDigest == binding.rootsDigest do throw "checkpoint was taken under different roots"
  let some state := Minidregg.Theory.ObjectiveBendCheckpoint.decodeState checkpoint.tokens
    | throw "checkpoint does not decode"
  unless value.conformsUnder p.source.assumptions.bounds response do
    throw "turn refused: response does not conform to the response type"
  let some next := resume (Delvetalk.Turn.dataTerm value) state
    | throw "turn refused: checkpoint is not a yielded state"
  return (plan, response, result, state, next)

def resumeWith (p : Prepared) (checkpoint : Delvetalk.Turn.Checkpoint) (binding : Delvetalk.Turn.Binding) (value : Data) (b : Budgets) :
    Except String Delvetalk.Turn.Outcome := do
  let (plan, response, result, state, next) ← resumed p checkpoint binding value
  let capacities := Minidregg.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ state
  let outcome := (executeStateWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ next).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude p binding p.source.assumptions.bounds plan response result b capacities outcome

end Delvetalk.Host.Run
