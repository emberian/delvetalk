/- Typed Objective Bend data on the JSON wire (typed-values-v1 plus `variant`):
the ONE decoder of the responses a yielded activity is resumed with, and the
ONE printer of extracted Plans. Consumers: Host/ObjectiveBendPreview (the
clear preview's turns) and Compiler/ObjectiveBendEmitCRun (the C backend's
differential, which resumes both machines with the same decoded responses). -/
import Lean.Data.Json
import Theory.ObjectiveBendDemandData

namespace Minidregg.Compiler.ObjectiveBendDataWire
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)
set_option autoImplicit false

/-- The elements of a proper list: a chain of `nil` / `cons {head, tail}` variants ending in
`nil {}`. Anything else (a `cons` whose tail is not a list, extra fields) is not a list and
stays a variant. Iterative: the chain may be long. -/
partial def listItems? (data : Data) : Option (Array Data) :=
  let rec go (d : Data) (acc : Array Data) : Option (Array Data) :=
    match d with
    | .variant "nil" (.record []) => some acc
    | .variant "cons" (.record [("head", h), ("tail", t)])
    | .variant "cons" (.record [("tail", t), ("head", h)]) => go t (acc.push h)
    | _ => none
  go data #[]

/-- A list's elements as the `nil` / `cons` chain the machine and `Data.conforms` see. -/
def listData (items : Array Data) : Data :=
  items.foldr (fun h t => .variant "cons" (.record [("head", h), ("tail", t)])) (.variant "nil" (.record []))

/-- Typed data on the wire: typed-values-v1 plus `variant`, and `list`: a proper list is
`{"tag":"list","items":[...]}`, not a nested chain. The decoder refuses the chain. -/
partial def dataJson (data : Data) : Json :=
  match listItems? data with
  | some items => Json.mkObj [("tag",toJson "list"),("items",Json.arr (items.map dataJson))]
  | none => match data with
  | .natural n => Json.mkObj [("tag",toJson "natural"),("value",toJson (toString n))]
  | .boolean b => Json.mkObj [("tag",toJson "boolean"),("value",toJson b)]
  | .label s => Json.mkObj [("tag",toJson "label"),("value",toJson s)]
  | .record fields => Json.mkObj [("tag",toJson "record"),("fields",Json.arr (fields.foldl (fun result field =>
      result.push (Json.mkObj [("name",toJson field.1),("value",dataJson field.2)])) #[]))]
  | .variant label payload => Json.mkObj [("tag",toJson "variant"),("label",toJson label),("payload",dataJson payload)]

/-- Exact UTF-8 size of `dataJson value |>.compress`, without allocating its
nested JSON wrapper tree or one whole encoded string. JSON quoting is delegated
only for leaf strings, so escaping follows Lean's physical wire printer. -/
partial def dataJsonBytes (data : Data) : Nat :=
  match listItems? data with
  | some items => 25 + items.foldl (fun total item => total + dataJsonBytes item) 0 + (items.size - 1)
  | none => match data with
  | .natural n => 26 + (toJson (toString n)).compress.utf8ByteSize
  | .boolean b => if b then 30 else 31
  | .label s => 24 + (toJson s).compress.utf8ByteSize
  | .record fields => 28 + fields.foldl (fun total field =>
      total + 18 + (toJson field.1).compress.utf8ByteSize + dataJsonBytes field.2) 0
      + (fields.length - 1)
  | .variant label payload => 37 + (toJson label).compress.utf8ByteSize + dataJsonBytes payload

/-- A list is `{"tag":"list","items":[...]}` on the wire. A `nil` / `cons` chain of
variants that forms a proper list (the in-memory shape) is refused by name; a `cons`
whose tail is not a list is an ordinary variant, which `dataJson` also prints as one. -/
def consChainRefusal : String := "cons chains are no longer accepted on the wire; send a list"

def decodeNatural (json : Json) : Except String Data := do
  let text ← json.getObjValAs? String "value"
  let some n := text.toNat? | throw "response natural must be canonical decimal"
  if toString n != text then throw "response natural must be canonical decimal"
  pure (.natural n)

def decodeData : Nat → Json → Except String Data
  | 0, _ => throw "response nesting capacity"
  | fuel + 1, json => do
    let tag ← json.getObjValAs? String "tag"
    if tag == "natural" then decodeNatural json
    else if tag == "boolean" then return .boolean (← json.getObjValAs? Bool "value")
    else if tag == "label" then return .label (← json.getObjValAs? String "value")
    else if tag == "record" then
      let fields ← (← json.getObjVal? "fields").getArr?
      return .record (← fields.toList.mapM fun field => do
        return (← field.getObjValAs? String "name", ← decodeData fuel (← field.getObjVal? "value")))
    else if tag == "list" then
      let items ← (← json.getObjVal? "items").getArr?
      return listData (← items.mapM (decodeData fuel))
    else if tag == "variant" then
      let value := Data.variant (← json.getObjValAs? String "label") (← decodeData fuel (← json.getObjVal? "payload"))
      if (listItems? value).isSome then throw consChainRefusal
      return value
    else throw "unknown response data tag"

end Minidregg.Compiler.ObjectiveBendDataWire
