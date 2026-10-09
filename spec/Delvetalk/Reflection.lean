/- A typed observer of a retained source specification. This is not a loader,
   closure-code inspector, object-reference resolver or provenance constructor. -/
import Theory.ObjectiveBendTyping

namespace Delvetalk.Reflection
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendTyping

/-- Wrap the exact checked source term with Core4.metadata. Every existing
    annotation moves under the observer's sole child; no types/bounds are invented.
    The ordinary package data executor checks the wrapped term again. -/
def metadataPacket (packet : Json) : Except String Json := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "reflection requires a closed source entry"
  let some checked := check decoded.source [] decoded.fuel | throw "reflection source checker refusal"
  match checked.type with
  | .specification _ _ => pure ()
  | _ => throw "reflection entry must return a Specification"
  let annotations ← (← (← packet.getObjVal? "annotations").getArr?).toList.mapM fun entry => do
    let path ← (← entry.getObjVal? "path").getArr?
    let fields ← entry.getObj?
    return Json.mkObj (fields.toArray.toList.map fun (key, value) =>
      (key, if key == "path" then Json.arr (#[toJson (0 : Nat)] ++ path) else value))
  let fields ← packet.getObj?
  let term ← packet.getObjVal? "term"
  return Json.mkObj (fields.toArray.toList.map fun (key, value) =>
    (key, if key == "term" then Json.mkObj [("tag", toJson "metadata"), ("value", term)]
      else if key == "annotations" then Json.arr annotations.toArray else value))

end Delvetalk.Reflection
