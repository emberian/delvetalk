/- Object-local source tables. Resolution frames the exact retained modules;
   it neither compiles nor evaluates source, and never consults global state. -/
import Lean

namespace SourcePackages
open Lean

def referenceFormat : String := "delvetalk-source-package-ref-v1"
def tableFormat : String := "delvetalk-source-package-table-v1"

private def pairs (value : Json) : Except String (List (String × Json)) := do
  return (← value.getObj?).toList

private def exact (value : Json) (keys : List String) (label : String) : Except String Unit := do
  let actual := (← pairs value).map Prod.fst
  if actual.length != keys.length || !(keys.all actual.contains) then
    throw (label ++ " has missing or unsupported fields")

/-- Select an exact object-local source table without inventing an entry. -/
def modules (protocol : Json) (name : String) : Except String Json := do
  if name.isEmpty || name.utf8ByteSize > 128 then throw "source package name must be 1..128 bytes"
  let tables ← protocol.getObjVal? "sourcePackages"
  if (← pairs tables).length > 64 then throw "source package table exceeds 64 entries"
  let selected ← match tables.getObjVal? name with
    | .ok value => pure value
    | .error _ => throw ("source package not found in owning protocol: " ++ name)
  exact selected ["format", "modules"] "source package table entry"
  if (← selected.getObjValAs? String "format") != tableFormat then
    throw "unsupported source package table format"
  let modules ← selected.getObjVal? "modules"
  discard modules.getArr?
  return modules

/-- Inline descriptors retain their historical meaning. An explicit selector
resolves only in the owning protocol: exact roots pin both table and selector.
Source validation, typing and execution remain with the package boundary. -/
def resolve (protocol descriptor : Json) : Except String Json := do
  if (descriptor.getObjValAs? String "format").toOption != some referenceFormat then
    return descriptor
  exact descriptor ["format", "name", "entry"] "source package reference"
  let name ← descriptor.getObjValAs? String "name"
  let entry ← descriptor.getObjValAs? String "entry"
  let selected ← modules protocol name
  return Json.mkObj [("modules", selected), ("entry", toJson entry)]

end SourcePackages
