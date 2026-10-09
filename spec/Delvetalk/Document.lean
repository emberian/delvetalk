/- Host-side projection of a Document to text. A Document is ordinary Data:
   variants over records, with `List<Document>` as `nil | cons {head, tail}`
   (world/lib/document/Document.obend). `render` is exactly Bend's
   `Document.plain`, `lines` exactly `Document.lines`, at zero machine ticks. -/
import Lean.Data.Json
import Compiler.ObjectiveBendDataWire
import Theory.ObjectiveBendDemandData

namespace Delvetalk.Document
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Compiler.ObjectiveBendDataWire (decodeData dataJson)

/-- Nesting of documents (a sequence's items and a quote's body are one deeper). -/
def maxDepth : Nat := 64
/-- Documents plus list cells visited. -/
def maxNodes : Nat := 65536
def maxOutputBytes : Nat := 1048576
/-- Nesting capacity of the JSON wire form: a list cell costs two data levels. -/
def wireDepth : Nat := 8192
/-- Offers one turn may emit, and the rendered bytes they may carry together. -/
def maxOffersPerTurn : Nat := 16

structure Walk where
  leaves : Array String := #[]
  nodes : Nat := 0
  bytes : Nat := 0

abbrev W := StateT Walk (Except String)

def tick : W Unit := do
  let s ← get
  if s.nodes ≥ maxNodes then throw s!"document exceeds {maxNodes} nodes"
  set { s with nodes := s.nodes + 1 }

def emit (text : String) : W Unit := do
  let s ← get
  let bytes := s.bytes + text.utf8ByteSize
  if bytes > maxOutputBytes then throw s!"document text exceeds {maxOutputBytes} bytes"
  set { s with leaves := s.leaves.push text, bytes }

def malformed {α : Type} (what : String) : W α := throw s!"malformed document: {what}"

def textField (fields : List (String × Data)) (name : String) : W String :=
  match fields.lookup name with
  | some (.label s) => pure s
  | _ => malformed s!"{name} must be text"

mutual
partial def walk (depth : Nat) (document : Data) : W Unit := do
  if depth > maxDepth then throw s!"document depth exceeds {maxDepth}"
  tick
  let .variant tag payload := document | malformed "not a variant"
  let .record f := payload | malformed s!"{tag} payload is not a record"
  match tag with
  | "text" => emit (← textField f "value")
  | "sequence" =>
    let some items := f.lookup "items" | malformed "sequence without items"
    walkItems depth items
  | "quote" =>
    emit (← textField f "attribution"); emit ": "
    let some body := f.lookup "body" | malformed "quote without body"
    walk (depth + 1) body
  | "reference" => emit (← textField f "label")
  | "offer" => emit (← textField f "label")
  | "fields" => pure ()
  | "source" => emit (← textField f "code")
  | "result" =>
    let some body := f.lookup "body" | malformed "result without body"
    walk (depth + 1) body
  | "continuation" => emit (← textField f "label")
  | other => malformed s!"unknown document form {other}"

partial def walkItems (depth : Nat) (items : Data) : W Unit := do
  tick
  match items with
  | .variant "nil" _ => pure ()
  | .variant "cons" (.record f) =>
    let some head := f.lookup "head" | malformed "list cell without head"
    let some tail := f.lookup "tail" | malformed "list cell without tail"
    walk (depth + 1) head
    walkItems depth tail
  | _ => malformed "items must be a list"
end

/-- Exactly Bend's `Document.plain`. -/
def render (document : Data) : Except String String := do
  let ((), s) ← (walk 1 document).run {}
  return String.join s.leaves.toList

/-- Exactly Bend's `Document.lines`: the rendered text split at newlines, a
final empty line dropped. -/
def linesOf (text : String) : List String :=
  let parts := text.splitOn "\n"
  match parts.reverse with
  | "" :: rest => rest.reverse
  | _ => parts

def lines (document : Data) : Except String (List String) := return linesOf (← render document)

def renderOp (j : Json) : Except String Json := do
  let document ← decodeData wireDepth (← j.getObjVal? "document")
  let text ← render document
  return Json.mkObj [("status", toJson "rendered"), ("text", toJson text),
    ("lines", Json.arr ((linesOf text).map toJson).toArray), ("bytes", toJson text.utf8ByteSize)]

end Delvetalk.Document
