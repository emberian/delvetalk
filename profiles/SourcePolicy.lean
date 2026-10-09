/- Law-held pure source predicates and candidate invariants share the same
   native execution ledger as the body. Source receives complete exact JSON
   observations through Value, including typed state and decimal spellings. -/
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
  let context ← Preparation.encodeValue Preparation.retainedValueDepth facts
  let config ← Preparation.encodeValue Preparation.retainedValueDepth (← field policy "config")
  match ← execute package #[dataJson context, dataJson config] with
  | .boolean true => pure ()
  | .boolean false => throw "source policy refused"
  | _ => throw "source policy must return Bool"

end SourcePolicy
