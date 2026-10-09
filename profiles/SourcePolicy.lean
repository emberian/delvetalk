/- Law-held pure source predicates and candidate invariants share the same
   native execution ledger as the body. Facts contain logical checked Data;
   arbitrary configuration retains exact JSON through Preparation.Value. -/
import Preparation

namespace SourcePolicy
open Lean World
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Compiler.ObjectiveBendDataWire (dataJson)

def check (execute : Json → Array Json → Evaluation Data)
    (policy facts : Json) : Evaluation Unit := do
  let keys := (← pairs policy).map Prod.fst
  unless keys.length == 2 && keys.all ["package", "config"].contains do
    throw "source policy requires exactly package and config"
  let package ← field policy "package"
  let keys := (← pairs package).map Prod.fst
  unless keys.length == 2 && keys.all ["modules", "entry"].contains do
    throw "source policy requires standalone modules and entry"
  let op ← str facts "op"
  unless ["create", "reprogram", "law", "invoke"].contains op do
    throw "unknown source policy operation"
  let state ← Delvetalk.PackageData.decode 256 (← field (← field facts "state") "model")
  -- Only World helpers add this field through a native Option Data parameter;
  -- caller request fields are never copied into the policy context.
  let input ← if let some metadata := (field facts "settlementInput").toOption then do
      unless op == "invoke" && (← str facts "command") == "$messages-settle" do
        throw "invalid source policy settlement context"
      pure (Data.variant "settlement" (← Delvetalk.PackageData.decode 256 metadata))
    else if op == "invoke" then do
      let value ← Delvetalk.PackageData.decode 256 (← field facts "input")
      pure (Data.variant "invoke" (Data.variant (← str facts "command") value))
    else pure (Data.variant "none" (Data.record []))
  let mut fields := [("object", Data.label (← str facts "object")),
    ("principal", Data.label (← str facts "principal")), ("op", Data.label op),
    ("command", Data.label (← str facts "command")), ("state", state), ("input", input)]
  if let some next := (field facts "nextState").toOption then
    fields := fields ++ [("nextState", ← Delvetalk.PackageData.decode 256 (← field next "model"))]
  let context := Data.record fields
  let config ← Preparation.encodeValue Preparation.retainedValueDepth (← field policy "config")
  match ← execute package #[dataJson context, dataJson config] with
  | .boolean true => pure ()
  | .boolean false => throw "source policy refused"
  | _ => throw "source policy must return Bool"

end SourcePolicy
