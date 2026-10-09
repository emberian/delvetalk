/- Opt-in ordered local transactions. The single-object evaluator and receipt
   lifecycle are shared with World; no protocol evaluator lives in transport. -/
import WorldCore
open Lean World

namespace Transactions

def priorResult (index : Json) (results : Array Json) : Except String Json := do
  let index ← index.getNat?
  match results[index]? with
  | some result => pure result
  | none => throw "inputFrom must name an earlier call"

-- Inputs are either explicit pure records or a complete earlier pure result.
-- The latter conveys data, never the earlier object's authority.
def callInput (call : Json) (results : Array Json) : Except String Json := do
  for (key, _) in (← pairs call) do
    if !(["op", "object", "command", "input", "inputFrom"].contains key) then
      throw "unsupported transaction call field"
  let input? := (field call "input").toOption
  let from? := (field call "inputFrom").toOption
  let input ← match input?, from? with
    | some input, none => pure input
    | none, some index => priorResult index results
    | _, _ => throw "call requires exactly one of input or inputFrom"
  discard (pairs input)
  return input

-- This descriptor is made only from previously admitted calls in this batch.
-- Equal explicit input never receives provenance. It transfers no authority.
def callInputOrigin (call : Json) (calls : Array Json) (completed : Nat) : Except String Json := do
  match (field call "inputFrom").toOption with
  | none => return World.noInputOrigin
  | some value =>
    let index ← value.getNat?
    if index >= completed then throw "inputFrom must name an earlier call"
    let prior ← match calls[index]? with
      | some prior => pure prior
      | none => throw "inputFrom must name an earlier call"
    let op ← match (field prior "op").toOption with
      | none => pure "invoke"
      | some value => value.getStr?
    if op != "invoke" then return World.noInputOrigin
    return obj [("present", .bool true), ("object", .str (← str prior "object")),
      ("command", .str (← str prior "command")),
      ("immediatelyPrevious", .bool (index + 1 == completed))]

def reprogramCandidate (call : Json) (results : Array Json) : Except String Json := do
  let candidate ← match (field call "inputFrom").toOption with
    | some index => do
      for (key, _) in (← pairs call) do
        if !(["op", "object", "inputFrom"].contains key) then
          throw "unsupported transaction reprogram field"
      priorResult index results
    | none => do
      for (key, _) in (← pairs call) do
        if !(["op", "object", "protocol", "state"].contains key) then
          throw "unsupported transaction reprogram field"
      pure (obj [("protocol", ← field call "protocol"), ("state", ← field call "state")])
  for (key, _) in (← pairs candidate) do
    if !(["protocol", "state"].contains key) then
      throw "reprogram result requires exactly protocol and state"
  discard (field candidate "protocol")
  discard (field candidate "state")
  return candidate

def transitionWith (runtime : World.Runtime) (world request : Json) (principal : String) : Except String (Json × Json) := do
  if (← str request "op") != "transaction" then
    return ← World.transitionWith runtime world request principal
  let objects ← field world "objects"
  let reads ← pairs (← field request "reads")
  let calls ← (← field request "calls").getArr?
  if calls.isEmpty then throw "transaction requires at least one call"
  -- Check every exact preimage against the initial world before running any call.
  -- Additional read-only roots are guards on the same atomic commit.
  for (id, expected) in reads do
    if id.isEmpty then throw "empty object id"
    if expected == .null then
      if (field objects id).isOk then throw "stale absence root"
    else if (← field objects id) != expected then throw "stale read root"
  let absent := (reads.filter (fun entry => entry.2 == .null)).map Prod.fst |>.toArray
  let execution : Evaluation (Json × Array Json × Array Json × Json) := do
    let mut staged := objects
    let mut results : Array Json := #[]
    let mut outbox : Array Json := #[]
    let mut allocatedRoots := obj []
    for call in calls do
      tick
      let id ← str call "object"
      if !(reads.any (fun entry => entry.1 == id)) then
        throw "transaction target missing from read set"
      let o ← field staged id
      let op ← match (field call "op").toOption with
        | some value => value.getStr?
        | none => pure "invoke"
      if op != "invoke" && op != "reprogram" then
        throw "unsupported transaction operation"
      -- The operation is explicit; the principal remains the global caller.
      -- Both profiles use one authority engine.
      let (nextObj, result, emitted, invocation, inputOrigin) ← if op == "reprogram" then do
        authorizeRequest o (← put call "op" (.str op)) principal
        let candidate ← reprogramCandidate call results
        let nextObj ← reprogramObjectWith runtime o (← field candidate "protocol") (← field candidate "state")
        pure (nextObj, Json.null, (#[] : Array Json), Json.null, World.noInputOrigin)
      else do
        let input ← callInput call results
        let inputOrigin ← callInputOrigin call calls results.size
        let invocation ← put (← put call "input" input) "op" (.str op)
        authorizeRequest o invocation principal
        let (nextState, result, emitted) ← executeCommandWith runtime o invocation principal inputOrigin
        let n ← (← field o "version").getNat?
        let nextObj ← put (← put o "state" nextState) "version" (toJson (n + 1))
        pure (nextObj, result, emitted, invocation, inputOrigin)
      staged ← put staged id nextObj
      if op == "invoke" then
        let (nextObjects, created) ← allocateChildrenWith runtime staged o invocation principal absent inputOrigin
        staged := nextObjects
        -- Preserve creation evidence even when later calls replace a child.
        for (child, initialRoot) in (← pairs created) do
          allocatedRoots ← put allocatedRoots child initialRoot
      for payload in emitted do
        outbox := outbox.push (obj [("object", .str id),
          ("step", toJson results.size), ("payload", payload)])
      results := results.push result
    return (staged, results, outbox, allocatedRoots)
  let ((staged, results, outbox, allocatedRoots), _) ← execution.run runtime.budget
  let roots := reads.map fun (id, _) => (id, (field staged id).toOption.getD .null)
  let next ← put world "objects" staged
  let mut data := obj [
    ("roots", obj roots), ("results", .arr results), ("outbox", .arr outbox)]
  if allocatedRoots != obj [] then data ← put data "allocated" allocatedRoots
  return (next, receipt request "committed" data)

def transition (world request : Json) (principal : String) : Except String (Json × Json) :=
  transitionWith {} world request principal

def handle (world request : Json) : Except String (Json × Json) :=
  World.handleWith transition world request

def job (j : Json) : Json := World.jobWith handle j

end Transactions
