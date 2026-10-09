/- Activity turns: run an activity to its next `perform`, hand the Plan out as
   data with a checkpoint, and continue it when resumed with a response.
   The checkpoint is the collected machine state as canonical tokens
   (Theory.ObjectiveBendCheckpoint). The type of the response is never taken
   from the client: it is re-derived from the verified artifact. -/
import Compiler.ObjectiveBendFrontEnd
import Compiler.ObjectiveBendDataWire
import Theory.ObjectiveBendDemandData
import Theory.ObjectiveBendCheckpoint
import Theory.ObjectiveBendDemandCollect

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
def applyArgument (source : AnnotatedTerm) (argument : Term) : AnnotatedTerm :=
  { source with
    term := .app source.term argument
    annotations := fun position => match position with
      | 0 :: rest => source.annotations rest
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
def activityShape (type : Ty) : Except String (Ty × Ty × Ty) :=
  match type with
  | .computation plan response result =>
      if !plan.isPlan then .error "turn refused: Plan type is not a first-order sum"
      else if !response.isData then .error "turn refused: response type is not first-order data"
      else if !result.isData then .error "turn refused: result type is not first-order data"
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
  return ⟨← bounded limits "ticks" 100000 1000000, ← bounded limits "heap" 100000 1000000,
    ← bounded limits "stack" 10000 100000, ← bounded limits "nodes" 100000 1000000,
    ← bounded limits "bytes" 1048576 16777216⟩

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

open Minidregg.Theory.ObjectiveBendCheckpoint Minidregg.Theory.ObjectiveBendDemandCollect in
/-- Turn the outcome of a bounded run into the wire reply. -/
def conclude (plan response result : Ty) (b : Budgets) (limits : Limits)
    (outcome : Except (Failure × State × Budget) (Data × Budget)) : Except String Json :=
  match outcome with
  | .ok (value, remaining) =>
      if !value.conforms result then .error "turn refused: result does not conform to its type"
      else .ok (Json.mkObj [("status", toJson "finished"), ("value", dataJson value),
        ("type", typeJson result), ("ticksUsed", toJson (b.ticks - remaining.ticks))])
  | .error (.yielded, state, remaining) =>
      match yieldedPlan limits remaining state with
      | .error (failure, _, _) => .error ("turn refused: " ++ failureName failure)
      | .ok extracted =>
          if !extracted.value.conforms plan then .error "turn refused: Plan does not conform to its type"
          else .ok (Json.mkObj [("status", toJson "yielded"), ("plan", dataJson extracted.value),
            ("planType", typeJson plan), ("responseType", typeJson response),
            ("checkpoint", tokensJson (encodeState (checkpoint extracted.state))),
            ("ticksUsed", toJson (b.ticks - extracted.remaining.ticks))])
  | .error (failure, _, _) => .error ("turn refused: " ++ failureName failure)

/-- `packet` belongs to an artifact the caller has already verified. -/
def start (packet arguments limits : Json) : Except String Json := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let values ← (← arguments.getArr?).toList.mapM (decodeData 256)
  let source := values.foldl (fun s v => applyArgument s (dataTerm v)) decoded.source
  let some checked := check source [] decoded.fuel | throw "applied package refused by Mini type checker"
  let (plan, response, result) ← activityShape checked.type
  let b ← budgets limits
  let capacities : Limits := ⟨b.heap, b.stack⟩
  let outcome := (executeWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ source.term).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude plan response result b capacities outcome

open Minidregg.Theory.ObjectiveBendCheckpoint Minidregg.Theory.ObjectiveBendDemandCollect in
def resumeTurn (packet checkpointJson responseJson limits : Json) : Except String Json := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let some entry := check decoded.source [] decoded.fuel | throw "package refused by Mini type checker"
  let (plan, response, result) ← activityShape (peelArrows 64 entry.type)
  let some state := decodeState (← tokensOfJson checkpointJson) | throw "checkpoint does not decode"
  let value ← decodeData 256 responseJson
  unless value.conforms response do throw "turn refused: response does not conform to the response type"
  let some resumed := Minidregg.Theory.ObjectiveBendDemandMachine.resume (dataTerm value) state
    | throw "turn refused: checkpoint is not a yielded state"
  let b ← budgets limits
  let capacities := limitsPast ⟨b.heap, b.stack⟩ state
  let outcome := (executeStateWith (fun _ => true) capacities ⟨b.nodes, b.ticks, b.bytes⟩ resumed).map
    fun e => (e.extraction.result.value, e.extraction.result.remaining)
  conclude plan response result b capacities outcome

end Delvetalk.Turn
