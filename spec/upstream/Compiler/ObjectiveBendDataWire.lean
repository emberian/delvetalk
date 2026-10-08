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

/-- Typed data on the wire: typed-values-v1 plus `variant`. -/
partial def dataJson : Data → Json
  | .natural n => Json.mkObj [("tag",toJson "natural"),("value",toJson (toString n))]
  | .boolean b => Json.mkObj [("tag",toJson "boolean"),("value",toJson b)]
  | .label s => Json.mkObj [("tag",toJson "label"),("value",toJson s)]
  | .record fields => Json.mkObj [("tag",toJson "record"),("fields",Json.arr (fields.map fun field =>
      Json.mkObj [("name",toJson field.1),("value",dataJson field.2)]).toArray)]
  | .variant label payload => Json.mkObj [("tag",toJson "variant"),("label",toJson label),("payload",dataJson payload)]

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
    else if tag == "variant" then
      return .variant (← json.getObjValAs? String "label") (← decodeData fuel (← json.getObjVal? "payload"))
    else throw "unknown response data tag"

end Minidregg.Compiler.ObjectiveBendDataWire
