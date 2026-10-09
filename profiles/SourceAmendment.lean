/- A law-held source guard restricts actual law replacement. Its configuration
   is opaque data; the host neither interprets identities nor chooses grants. -/
import Preparation

namespace SourceAmendment
open Lean World
open Minidregg.Compiler.ObjectiveBendDataWire (dataJson)

def exact (value : Json) (names : List String) : Except String Unit := do
  let keys := (← pairs value).map Prod.fst
  unless keys.length == names.length && keys.all names.contains do
    throw "source amendment has missing or unknown fields"

def check (execute : Json → Array Json → Evaluation Json)
    (amendment before after request : Json) (principal : String) : Evaluation Unit := do
  let op ← str request "op"
  -- The runtime hook is still selected on every write, so hosts without this
  -- extension fail closed. Ordinary calls do not recompile an amendment guard.
  if op != "create" && op != "law" then return
  exact amendment ["profile", "package", "config"]
  if (← str amendment "profile") != "delvetalk-source-amendment-v1" then
    throw "unknown source amendment profile"
  let package ← field amendment "package"
  -- A law holds its own complete code; candidate-local names cannot change it.
  exact package ["modules", "entry"]
  let context := Preparation.rec [
    ("object", .label (← str request "object")),
    ("principal", .label principal),
    ("currentLaw", ← Preparation.encodeValue Preparation.retainedValueDepth (← field before "law")),
    ("nextLaw", ← Preparation.encodeValue Preparation.retainedValueDepth (← field after "law"))]
  let result ← execute package #[dataJson context]
  match ← Delvetalk.PackageData.decode 256 result with
  | .boolean true => pure ()
  | .boolean false => throw "source amendment refused"
  | _ => throw "source amendment must return Bool"

end SourceAmendment
