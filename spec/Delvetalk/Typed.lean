/- DelveTalk's array AST plus Mini's byte-exact annotated partial checker.
   This module adapts packets and diagnostics; it defines no typing rules. -/
import Delvetalk.Core
import Theory.ObjectiveBendTyping

open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendTyping

namespace Delvetalk.Typed

def schema : String := "delvetalk.typed-core.v1"

/-- Positions are exactly the child positions used by Mini's `infer`,
`inferFields`, and `inferArms`. Only annotations at these nodes are consumed. -/
partial def annotationSites (term : Term) (path : List Nat := []) : List (List Nat) :=
  let child (i : Nat) (t : Term) := annotationSites t (path ++ [i])
  let fields (basePath : List Nat) (fs : List (String × Term)) :=
    (fs.zipIdx).flatMap fun (entry, i) => annotationSites entry.2 (basePath ++ [i])
  match term with
  | .lam b | .perform b | .done b => path :: child 0 b
  | .inject _ b => path :: child 0 b
  | .app a b | .mix a b | .fix a b | .specification a b | .prototype a b =>
      child 0 a ++ child 1 b
  | .binary _ a b => child 0 a ++ child 1 b
  | .reflect a | .metadata a | .project a | .get a _ => child 0 a
  | .record fs => fields path fs
  | .extend a fs | .case a fs => child 0 a ++ fields (path ++ [1]) fs
  | .ifZero a b c | .ifBool a b c => child 0 a ++ child 1 b ++ child 2 c
  | .bound _ | .nat _ | .boolean _ | .label _ => []

/-- Decode only the envelope here. Types, quantities, bounds, contexts, annotation
payloads and budgets use the pinned Mini decoder; terms use the existing core
array decoder, so raw and typed profiles cannot drift to different term syntax. -/
def decodeJob (j : Json) : Except String (String × DecodedPacket) := do
  let obj ← j.getObj?
  unless obj.toList.all (fun (k,_) =>
      ["schema", "name", "term", "types", "annotations", "bounds",
       "shareableVariables", "rigidVariables", "context", "fuel"].contains k) do
    throw "unknown typed job key"
  unless (← j.getObjValAs? String "schema") == schema do
    throw "delvetalk.typed-core.v1 schema required"
  let name ← j.getObjValAs? String "name"
  let table ← decodeTypeTable (← j.getObjVal? "types")
  let term ← Delvetalk.decode (← j.getObjVal? "term")
  let parts ← decodePacketParts j table
  let rigid ← (← (← j.getObjVal? "rigidVariables").getArr?).toList.mapM jsonNat
  unless decide rigid.Nodup do throw "duplicate rigid variable"
  unless rigid.all (fun i => (parts.assumptions.bounds.lookup i).isSome) do
    throw "rigid variable requires a declared bound"
  let sites := annotationSites term
  for entry in (← (← j.getObjVal? "annotations").getArr?) do
    let path ← (← (← entry.getObjVal? "path").getArr?).toList.mapM jsonNat
    unless sites.contains path do throw "annotation path does not address lam, inject, perform or done"
  return (name, ⟨⟨term, parts.annotations, { parts.assumptions with rigid := rigid }⟩,
    parts.context, parts.fuel⟩)

/-- Refusal is a checker diagnostic, never the core evaluator's `stuck` result.
The classifier is Mini's own checker re-run under its documented relaxations. -/
def checkJob (name : String) (packet : DecodedPacket) : Json :=
  let header := [("schema", toJson schema), ("name", toJson name)]
  match check packet.source packet.context packet.fuel with
  | some result => Json.mkObj (header ++ [
      ("status", toJson "accepted"), ("type", typeJson result.type),
      ("uses", toJson result.uses),
      ("shareable", toJson (result.type.shareableUnder packet.source.assumptions.shareableVariables))])
  | none =>
      let kind := match refusalKind packet with
        | .budget => "budget" | .ownership => "ownership" | .typing => "typing"
      Json.mkObj (header ++ [("status", toJson "refused"),
        ("diagnostic", Json.mkObj [("stage", toJson "checker"), ("kind", toJson kind),
          ("message", toJson (refusalReason packet))])])

def job (j : Json) : Except String Json := do
  let (name, packet) ← decodeJob j
  return checkJob name packet

def malformed (name : Json) (message : String) : Json := Json.mkObj [
  ("schema", toJson schema), ("name", name), ("status", toJson "error"),
  ("diagnostic", Json.mkObj [("stage", toJson "decode"),
    ("kind", toJson "malformed"), ("message", toJson message)])]

end Delvetalk.Typed
