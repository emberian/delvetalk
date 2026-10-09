/- Select exact source bytes only from already held roots. Read authority is
   checked by Preparation before the held set is supplied. No filesystem reads,
   source rewriting, program selection or application policy live here. -/
import Theory.ObjectiveBendDemandData
import MessagesCore
import SourcePackages

namespace SourceReflection
open Lean World
open Minidregg.Theory.ObjectiveBendDemandData (Data)
abbrev Work := StateT Nat (Except String)
def spend : Work Unit := do
  let remaining ← get
  if remaining == 0 then throw "definition reflection work capacity"
  set (remaining - 1)
def rec (fields : List (String × Data)) : Data := .record fields
def cons (head tail : Data) : Data := .variant "cons" (rec [("head", head), ("tail", tail)])
def nil : Data := .variant "nil" (rec [])

def definitions (held : List (String × Json)) (requests : Json) : Work Data := do
  let entries ← requests.getArr?
  if entries.size > 16 then throw "definition reflection count capacity"
  let mut identities : List (String × String) := []
  let mut definitions := nil
  let mut bytes := 0
  for request in entries.toList.reverse do
    spend
    let keys := (← pairs request).map Prod.fst
    if keys.length != 2 || !keys.all (["object", "package"].contains) then
      throw "definition reflection requires object and package"
    let object ← str request "object"
    let package ← str request "package"
    if object.isEmpty || package.isEmpty || object.utf8ByteSize > 512 || package.utf8ByteSize > 128 then
      throw "definition reflection identity capacity"
    if identities.contains (object, package) then throw "duplicate reflected definition"
    identities := (object, package) :: identities
    let some root := held.lookup object | throw "definition reflection root was not captured"
    let protocol ← field root "protocol"
    -- Table validation rejects unsupported fields, duplicate module names and
    -- malformed sources. We retain its exact order and bytes from this root.
    let modulesJson ← (← SourcePackages.modules protocol package).getArr?
    if modulesJson.size == 0 || modulesJson.size > 64 then throw "definition reflection module capacity"
    let mut modules := nil
    let mut names : List String := []
    for module in modulesJson.toList.reverse do
      spend
      let keys := (← pairs module).map Prod.fst
      if keys.length != 2 || !keys.all (["name", "source"].contains) then
        throw "definition reflection module requires exact name and source"
      let name ← str module "name"
      if name.isEmpty || name.utf8ByteSize > 128 || names.contains name then
        throw "definition reflection module identity capacity"
      names := name :: names
      let source ← str module "source"
      bytes := bytes + name.utf8ByteSize + source.utf8ByteSize
      if bytes > maxRequestBytes then throw "definition reflection source byte capacity"
      modules := cons (rec [("name", .label name), ("source", .label source)]) modules
    definitions := cons (rec [("object", .label object),
      ("version", .natural (← (← field root "version").getNat?)),
      ("program", .label (Messages.digest protocol)), ("package", .label package),
      ("modules", modules)]) definitions
  return definitions
end SourceReflection
