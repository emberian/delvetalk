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

def transition (world request : Json) (principal : String) : Except String (Json × Json) := do
  if (← str request "op") != "transaction" then
    return ← World.transition world request principal
  let objects ← field world "objects"
  let reads ← pairs (← field request "reads")
  let calls ← (← field request "calls").getArr?
  if calls.isEmpty then throw "transaction requires at least one call"
  -- Check every exact preimage against the initial world before running any call.
  -- Additional read-only roots are guards on the same atomic commit.
  for (id, expected) in reads do
    if id.isEmpty then throw "empty object id"
    if (← field objects id) != expected then throw "stale read root"
  let execution : Evaluation (Json × Array Json × Array Json) := do
    let mut staged := objects
    let mut results : Array Json := #[]
    let mut outbox : Array Json := #[]
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
      let (nextObj, result, emitted) ← if op == "reprogram" then do
        authorizeRequest o (← put call "op" (.str op)) principal
        let candidate ← reprogramCandidate call results
        let nextObj ← reprogramObject o (← field candidate "protocol") (← field candidate "state")
        pure (nextObj, Json.null, (#[] : Array Json))
      else do
        let input ← callInput call results
        let invocation ← put (← put call "input" input) "op" (.str op)
        authorizeRequest o invocation principal
        let (nextState, result, emitted) ← executeCommand o invocation principal
        let n ← (← field o "version").getNat?
        let nextObj ← put (← put o "state" nextState) "version" (toJson (n + 1))
        pure (nextObj, result, emitted)
      staged ← put staged id nextObj
      for payload in emitted do
        outbox := outbox.push (obj [("object", .str id),
          ("step", toJson results.size), ("payload", payload)])
      results := results.push result
    return (staged, results, outbox)
  let ((staged, results, outbox), _) ← execution.run 10000
  let roots ← reads.mapM fun (id, _) => do return (id, ← field staged id)
  let next ← put world "objects" staged
  return (next, receipt request "committed" (obj [
    ("roots", obj roots), ("results", .arr results), ("outbox", .arr outbox)]))

def handle (world request : Json) : Except String (Json × Json) :=
  World.handleWith transition world request

def job (j : Json) : Json := World.jobWith handle j

end Transactions

def main : IO Unit := World.serve Transactions.job
