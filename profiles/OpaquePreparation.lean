/- An invitation grants only its own bounded owner computation. Dependency reads
   remain participant-authorized; all selections bind exact source and roots. -/
import Preparation
import OpaqueInteraction

namespace OpaquePreparation
open Lean World
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Compiler.ObjectiveBendDataWire (dataJson)

-- A view is re-evaluated under its current grant before selecting an export.
-- Caller supplied export names, observation flags and definitions never select code.
abbrev BudgetView := Json → String → Nat → Except String (Json × Nat)

def validate (request : Json) (preparing : Bool) : Except String Unit := do
  let required := if preparing then
    ["op", "object", "principal", "panel", "expected", "key", "observations", "intent", "contribution"]
    else ["op", "object", "principal", "panel", "expected", "key"]
  let optional := if preparing then ["audience"] else ["audience", "observations"]
  let keys := (← pairs request).map Prod.fst
  unless required.all keys.contains && keys.all ((optional ++ required).contains) &&
      keys.length == required.length + (optional.filter keys.contains).length do
    throw "invitation request fields"
  if !RetainedRoots.isReference (← field request "expected") then throw "invitation requires retained reference"

def offeredBudget (evaluate : BudgetView) (world request : Json) (budget : Nat) : Except String (Json × Data × Nat) := do
  let id ← str request "object"
  let index := RetainedRoots.fromWorld world
  let expected ← RetainedRoots.resolve index id (← field request "expected")
  let viewRequest := obj ([("op", .str "opaque-view"), ("object", .str id),
    ("principal", ← field request "principal"), ("panel", ← field request "panel"),
    ("expected", expected)] ++
    match (field request "audience").toOption with | none => [] | some a => [("audience", a)])
  -- Check view authority through the shared gate; its evaluator threads the
  -- actual receiving budget through source execution and typed conversion.
  let root ← field (← field world "objects") id
  discard (OpaqueInteraction.view (fun _ _ => pure .null) world viewRequest)
  let (result, afterView) ← evaluate root (← str request "panel") budget
  let (data, remaining) ← (Delvetalk.PackageData.decode 256 result).run afterView
  let invitations ← Preparation.member data "invitations"
  let invitation ← Preparation.member invitations (← str request "key")
  match ← Preparation.member invitation "visible" with
  | .boolean true => pure ()
  | _ => throw "invitation unavailable"
  return (expected, invitation, remaining)

def observations (world : Json) (owner principal : String) (invitation : Data) : Except String Json := do
  let objects ← field world "objects"
  let index := RetainedRoots.fromWorld world
  let mut result := #[]
  let mut seen : List String := []
  for observation in (← Preparation.list 17 (← Preparation.member invitation "observations")) do
    Preparation.exact observation ["object", "inspectState", "inspectLaw"]
    let id ← Preparation.identity (← Preparation.member observation "object")
    if seen.contains id then throw "duplicate invitation observation"
    seen := id :: seen
    let root ← if id == owner then field objects id else readObject objects id principal
    let flags ← ["inspectState", "inspectLaw"].mapM fun name => do
      let .boolean flag ← Preparation.member observation name | throw "invitation observation flag"
      return (name, .bool flag)
    result := result.push (obj ([("object", .str id), ("root", ← RetainedRoots.reference index id root)] ++ flags))
  return .arr result

def selectBudget (evaluate : BudgetView) (world request : Json) (budget : Nat) : Except String Json := do
  let (_, invitation, _) ← offeredBudget evaluate world request budget
  let captured ← observations world (← str request "object") (← str request "principal") invitation
  if let some expected := (field request "observations").toOption then
    if expected != captured then throw "invitation dependencies changed"
  let selection := obj ([("object", ← field request "object"), ("panel", ← field request "panel"),
    ("expected", ← field request "expected"), ("key", ← field request "key"), ("observations", captured)] ++
    match (field request "audience").toOption with | none => [] | some a => [("audience", a)])
  return obj [("selection", selection), ("invitation", dataJson invitation)]

def prepareBudget (evaluate : BudgetView) (world request : Json) (budget : Nat) : Except String (Json × Nat) := do
  validate request true
  let (root, invitation, remaining) ← offeredBudget evaluate world request budget
  let owner ← str request "object"
  let principal ← str request "principal"
  let captured ← observations world owner principal invitation
  if captured != (← field request "observations") then throw "invitation dependencies changed"
  let index := RetainedRoots.fromWorld world
  let mut expanded := #[]
  for item in (← captured.getArr?) do
    expanded := expanded.push (← put item "root" (← RetainedRoots.resolve index (← str item "object") (← field item "root")))
  let mut internal := obj [("op", .str "prepare"), ("object", .str owner), ("root", root),
    ("entry", .str (← Preparation.text (← Preparation.member invitation "prepare"))),
    ("contribution", ← field request "contribution"), ("observations", .arr expanded),
    ("principal", .str principal), ("intent", ← field request "intent")]
  if let .ok codec := Preparation.member invitation "contributionCodec" then
    internal ← put internal "contributionCodec" (.str (← Preparation.text codec))
  if let .ok definitions := Preparation.member invitation "definitions" then
    let values ← Preparation.list 17 definitions
    let selections ← values.mapM fun item => do
      return obj [("object", .str (← Preparation.text (← Preparation.member item "object"))),
        ("package", .str (← Preparation.text (← Preparation.member item "package")))]
    internal ← put internal "definitions" (toJson selections)
  -- Authorization is already bound to this exact exposed invitation. No caller
  -- can access this callback outside this route, and dependency reads still check.
  Preparation.runBudget world internal remaining (RetainedRoots.reference index) none
    (fun _ id caller => if id == owner && caller == principal then pure () else throw "invitation owner differs")

def queryBudget (evaluate : BudgetView) (world request : Json) (budget : Nat) : Except String Json :=
  match (do
    let op ← str request "op"
    validate request (op == "opaque-prepare")
    if op == "opaque-prepare" then
      let (reply, _) ← prepareBudget evaluate world request budget
      if (str reply "kind").toOption == some "ready" then
        return obj [("kind", .str "ready"), ("summary", ← field reply "summary"),
          ("request", ← put request "op" (.str "opaque-transaction"))]
      -- Inspection is a full-read tool, not an invitation-only export. Authored
      -- questions/refusals are the invitation's public preparation outcomes.
      if !(["question", "refused"].contains ((str reply "kind").toOption.getD "")) then
        throw "opaque preparation result unavailable"
      let selection := obj ([("object", ← field request "object"),
        ("panel", ← field request "panel"), ("expected", ← field request "expected"),
        ("key", ← field request "key"), ("observations", ← field request "observations")] ++
        match (field request "audience").toOption with | none => [] | some a => [("audience", a)])
      return ← put reply "publicSelection" selection
    else selectBudget evaluate world request budget) with
  | .ok reply => .ok reply
  | .error _ => .error "opaque preparation refused"
end OpaquePreparation
