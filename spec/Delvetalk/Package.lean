/- Generic source-package boundary. Mini owns parsing, elaboration, typing and
   shared-demand execution. This adapter adds only JSON framing and data IO. -/
import Delvetalk.Core
import Compiler.ObjectiveBendFrontEnd
import Compiler.ObjectiveBendDataWire
import Theory.ObjectiveBendDemandData
import Delvetalk.PackageData
import Delvetalk.Reflection

open Lean (Json toJson)
open Minidregg.Compiler.ObjectiveBendFrontEnd
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData
open Minidregg.Compiler.ObjectiveBendDataWire

namespace Delvetalk.Package

def defaultLimits : Json := Json.mkObj [
  ("ticks", toJson "100000"), ("heap", toJson "100000"),
  ("stack", toJson "10000"), ("typeFuel", toJson "16384")]

def getLimits (j : Json) : Json := (j.getObjVal? "limits").toOption.getD defaultLimits

/-- A sealed in-memory package: imports name earlier modules explicitly supplied
by the caller. The adapter never reads an import path from the filesystem. -/
def modulesOf (j : Json) : Except String (List SourceModule × Json) := do
  let raw ← match j.getObjVal? "modules" with
    | .ok value => value.getArr?
    | .error _ => pure #[Json.mkObj [("name", toJson "Package"), ("source", ← j.getObjVal? "source")]]
  if raw.isEmpty || raw.size > 64 then throw "package requires 1..64 modules"
  let mut modules : List SourceModule := []
  for value in raw do
    let name ← value.getObjValAs? String "name"
    let source ← value.getObjValAs? String "source"
    unless Minidregg.Compiler.ObjectiveBendParse.isIdent name.toList do throw "invalid module name"
    if modules.any (fun m => m.name == name) then throw "duplicate module name"
    if source.utf8ByteSize > 524288 then throw "source exceeds 512 KiB"
    let ast ← (parseSource name source).mapError (fun d => d.json.compress)
    let mut imports : List LockedImport := []
    for edge in (← (← ast.getObjVal? "imports").getArr?) do
      let path ← edge.getObjValAs? String "path"
      let some target := modules.zipIdx.find? (fun (m,_) => path == "./" ++ m.name ++ ".obend")
        | throw "import must name an earlier supplied module"
      imports := imports ++ [⟨path, ← edge.getObjValAs? String "alias", ← edge.getObjVal? "span",
        target.2, target.1.name, target.1.sha256⟩]
    modules := modules ++ [⟨name,source,Minidregg.Compiler.Sha256.hexString source,imports⟩]
  return (modules, .arr raw)

def compile (j : Json) : Except String Json := do
  let (modules, sources) ← modulesOf j
  let entry ← j.getObjValAs? String "entry"
  let lowered ← (lower modules (modules.length - 1) entry (.arr #[]) (.arr #[]) (getLimits j) "definition").mapError
    (fun diagnostic => diagnostic.json.compress)
  if !lowered.laws.isEmpty then throw "package laws require a host law adapter; this pure profile refuses them"
  let accepted ← (accept lowered).mapError (fun diagnostic => diagnostic.json.compress)
  let packet := lowered.packet
  return Json.mkObj [
    ("schema", toJson "delvetalk.obend-package.v1"),
    ("modules", sources),
    ("sourcesSha256", toJson (Minidregg.Compiler.Sha256.hexString sources.compress)),
    ("entry", toJson entry), ("limits", getLimits j), ("packet", packet),
    ("packetSha256", toJson (Minidregg.Compiler.Sha256.hexString packet.compress)),
    ("type", typeJson accepted.typed.type)]

/- Arguments are closed ordinary first-order data. Variants require annotation
construction and are deliberately refused at this small initial boundary. -/
mutual
def argumentTerm : Data → Except String Term
  | .natural n => pure (.nat n)
  | .boolean b => pure (.boolean b)
  | .label s => pure (.label s)
  | .record fields => return .record (← argumentFields fields)
  | .variant _ _ => throw "variant arguments are not in the package execution profile"
def argumentFields : List (String × Data) → Except String (List (String × Term))
  | [] => pure []
  | (k,v) :: rest => do return (k, ← argumentTerm v) :: (← argumentFields rest)
end

/-- Re-address the original annotation table when application wraps its term.
The argument subtree is annotation-free first-order data, never raw code. -/
def applyArgument (source : AnnotatedTerm) (argument : Term) : AnnotatedTerm :=
  { source with
    term := .app source.term argument
    annotations := fun position => match position with
      | 0 :: rest => source.annotations rest
      | _ => none }

def bounded (j : Json) (key : String) (fallback cap : Nat) : Except String Nat := do
  let value ← match j.getObjVal? key with
    | .error _ => pure fallback
    | .ok x => jsonNat x
  if value > cap then throw (key ++ " exceeds package capacity")
  return value

/-- One global demand/extraction budget. No game rule or host authority lives here. -/
def executePacket (packet arguments limits : Json) : Except String Json := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let values ← (← arguments.getArr?).toList.mapM (decodeData 256)
  let terms ← values.mapM argumentTerm
  let source := terms.foldl applyArgument decoded.source
  let some checked := check source [] decoded.fuel | throw "applied package refused by Mini type checker"
  if !checked.type.isData then throw "package result must have first-order data type"
  let ticks ← bounded limits "ticks" 100000 1000000
  let heap ← bounded limits "heap" 100000 1000000
  let stack ← bounded limits "stack" 10000 100000
  let nodes ← bounded limits "nodes" 100000 1000000
  let bytes ← bounded limits "bytes" 1048576 16777216
  let budget : Budget := ⟨nodes,ticks,bytes⟩
  let capacities : Limits := ⟨heap,stack⟩
  match execute capacities budget source.term with
  | .ok execution =>
      let result := execution.extraction.result
      return Json.mkObj [("status", toJson "finished"), ("value", dataJson result.value),
        ("type", typeJson checked.type), ("ticksUsed", toJson (ticks - result.remaining.ticks)),
        ("heapCells", toJson result.state.heap.size),
        ("nodesUsed", toJson (nodes - result.remaining.nodes))]
  | .error (failure,state,remaining) =>
      return Json.mkObj [("status", toJson "refused"),
        ("failure", toJson (reprStr failure)),
        ("ticksUsed", toJson (ticks - remaining.ticks)), ("heapCells", toJson state.heap.size)]

/-- World data conversion: exact naturals, booleans, strings and records only.
The returned node count lets the enclosing host charge its shared budget. -/
def jsonData : Nat → Json → Except String (Data × Nat)
  | 0, _ => throw "package JSON nesting capacity"
  | fuel + 1, value => do
    match value with
    | .bool b => return (.boolean b, 1)
    | .str text => return (.label text, 1)
    | .num _ => return (.natural (← value.getNat?), 1)
    | .obj fields =>
        let converted ← fields.toArray.toList.mapM fun (name,child) => do
          let (datum,nodes) ← jsonData fuel child
          return ((name,datum),nodes)
        return (.record (converted.map Prod.fst), 1 + (converted.map Prod.snd).foldl (· + ·) 0)
    | _ => throw "package JSON requires natural, boolean, string or record"

def dataPlain : Nat → Data → Except String (Json × Nat)
  | 0, _ => throw "package result nesting capacity"
  | fuel + 1, value => do
    match value with
    | .natural n => return (toJson n, 1)
    | .boolean b => return (toJson b, 1)
    | .label text => return (toJson text, 1)
    | .record fields =>
        let converted ← fields.mapM fun (name,child) => do
          let (datum,nodes) ← dataPlain fuel child
          return ((name,datum),nodes)
        return (Json.mkObj (converted.map Prod.fst), 1 + (converted.map Prod.snd).foldl (· + ·) 0)
    | .variant _ _ => throw "variant results are not in the plain JSON package profile"

/-- For hosts that already verified this exact packet's source artifact. The
caller supplies remaining ticks, charges ticksUsed AND conversionNodes against
its enclosing budget, and commits nothing on refusal. -/
def executeJsonPacket (packet arguments limits : Json) : Except String Json := do
  let converted ← (← arguments.getArr?).toList.mapM (jsonData 64)
  let inputNodes := (converted.map Prod.snd).foldl (· + ·) 0
  let result ← executePacket packet (.arr ((converted.map fun pair => dataJson pair.1).toArray)) limits
  if (← result.getObjValAs? String "status") != "finished" then return result
  let (value,outputNodes) ← dataPlain 64 (← decodeData 256 (← result.getObjVal? "value"))
  return Json.mkObj [("status",toJson "finished"),("value",value),
    ("type",← result.getObjVal? "type"),("ticksUsed",← result.getObjVal? "ticksUsed"),
    ("heapCells",← result.getObjVal? "heapCells"),("nodesUsed",← result.getObjVal? "nodesUsed"),
    ("conversionNodes",toJson (inputNodes + outputNodes))]

/-- Re-run the pinned frontend and checker to bind claimed source to executable
packet. Self-hashes alone are integrity fields, never compilation evidence. -/
def verifyArtifact (artifact : Json) : Except String Unit := do
  unless (← artifact.getObjValAs? String "schema") == "delvetalk.obend-package.v1" do
    throw "unsupported package artifact"
  let rebuilt ← compile (Json.mkObj [("modules", ← artifact.getObjVal? "modules"),
    ("entry", ← artifact.getObjVal? "entry"), ("limits", ← artifact.getObjVal? "limits")])
  unless rebuilt == artifact do throw "artifact does not match recompilation of its claimed source"

/-- For a boundary which has already verified the exact artifact value. -/
def runVerified (j : Json) : Except String Json := do
  let artifact ← j.getObjVal? "artifact"
  executePacket (← artifact.getObjVal? "packet") (← j.getObjVal? "arguments") (getLimits j)

def run (j : Json) : Except String Json := do
  verifyArtifact (← j.getObjVal? "artifact")
  runVerified j

/-- Explicit recursive-data route. Legacy executePacket/executeJsonPacket keep
    their original fragment and wire. Conversion and machine work share ticks. -/
def executeDataPacket (packet arguments limits : Json) : Except String Json := do
  let bytes ← bounded limits "bytes" 1048576 16777216
  let inputBytes ← bounded limits "inputBytes" bytes 16777216
  -- Bound complete typed input, including large scalars, before decoding or
  -- decimal conversion. This is compact wire UTF-8, not extraction encoding.
  if arguments.compress.utf8ByteSize > inputBytes then throw "typed data input byte capacity"
  let ticks ← bounded limits "ticks" 100000 1000000
  let work ← bounded limits "work" ticks 1000000
  let allowance := min ticks work
  let ((source, type, _), remaining) ← (PackageData.prepare packet arguments).run allowance
  let before := allowance - remaining
  let heap ← bounded limits "heap" 100000 1000000
  let stack ← bounded limits "stack" 10000 100000
  let nodes ← bounded limits "nodes" 100000 1000000
  let budget : Budget := ⟨nodes, ticks - before, bytes⟩
  match execute ⟨heap, stack⟩ budget source.term with
  | .error (failure, state, rest) =>
      return Json.mkObj [("executionProfile", toJson "delvetalk-package-data-v1"),
        ("status", toJson "refused"), ("failure", toJson (reprStr failure)),
        ("ticksUsed", toJson (budget.ticks - rest.ticks)), ("conversionNodes", toJson before),
        ("heapCells", toJson state.heap.size)]
  | .ok execution =>
      let result := execution.extraction.result
      -- Recheck finite extracted data against the declared result; do not rely
      -- on Data.conforms, which deliberately does not unfold recursive aliases.
      let outputAllowance := min remaining result.remaining.ticks
      let (_, after) ← (PackageData.quote source.assumptions 256 result.value type).run outputAllowance
      return Json.mkObj [("executionProfile", toJson "delvetalk-package-data-v1"),
        ("status", toJson "finished"), ("value", dataJson result.value), ("type", typeJson type),
        ("ticksUsed", toJson (budget.ticks - result.remaining.ticks)),
        ("conversionNodes", toJson (before + outputAllowance - after)),
        ("heapCells", toJson result.state.heap.size),
        ("nodesUsed", toJson (nodes - result.remaining.nodes))]

def runData (j : Json) : Except String Json := do
  let artifact ← j.getObjVal? "artifact"
  verifyArtifact artifact
  executeDataPacket (← artifact.getObjVal? "packet") (← j.getObjVal? "arguments") (getLimits j)

/-- Observe a source-bound specification's actual metadata without applying its
    extension. A raw prototype's reflected specification says nothing about how
    its target was made; this result makes no stronger provenance claim. -/
def inspectSpecification (j : Json) : Except String Json := do
  let artifact ← j.getObjVal? "artifact"
  verifyArtifact artifact
  let packet ← Reflection.metadataPacket (← artifact.getObjVal? "packet")
  let result ← executeDataPacket packet (.arr #[]) (getLimits j)
  let fields ← result.getObj?
  return Json.mkObj (fields.toArray.toList ++ [
    ("reflectionProfile", toJson "delvetalk-source-specification-v1"),
    ("sourceBinding", Json.mkObj [("entry", ← artifact.getObjVal? "entry"),
      ("sourcesSha256", ← artifact.getObjVal? "sourcesSha256"),
      ("packetSha256", ← artifact.getObjVal? "packetSha256")])])

def selectedDataType (selection : Json) : Except String (Assumptions × Ty × Json) := do
  let artifact ← selection.getObjVal? "artifact"
  verifyArtifact artifact
  let packet ← decodePacket (← artifact.getObjVal? "packet")
  let some checked := check packet.source [] packet.fuel | throw "type comparison checker refusal"
  return (packet.source.assumptions, checked.type, ← selection.getObjVal? "path")

def compareDataTypes (j : Json) : Except String Json := do
  let (left, lt, lp) ← selectedDataType (← j.getObjVal? "left")
  let (right, rt, rp) ← selectedDataType (← j.getObjVal? "right")
  let work ← bounded j "work" 100000 1000000
  let action : PackageData.Work Bool := do
    let a ← PackageData.select left lt lp
    let b ← PackageData.select right rt rp
    PackageData.shape left 256 [] a
    PackageData.shape right 256 [] b
    PackageData.equivalent left right 256 [] a b
  let (equal, remaining) ← action.run work
  return Json.mkObj [("status", toJson "compared"), ("equal", toJson equal),
    ("conversionNodes", toJson (work - remaining))]

def job (j : Json) : Except String Json := do
  match ← j.getObjValAs? String "op" with
  | "template-expand" =>
    let source ← j.getObjValAs? String "source"
    if source.utf8ByteSize > 524288 then throw "source exceeds 512 KiB"
    let expanded ← DocumentTemplate.lower source
    return Json.mkObj [("status", toJson "expanded"), ("source", toJson expanded.source),
      ("schema", toJson "delvetalk.document-template-expansion.v1")]
  | "compile" => return Json.mkObj [("status", toJson "compiled"), ("artifact", ← compile j)]
  | "run" => run j
  | "run-data-v1" => runData j
  | "inspect-spec-v1" => inspectSpecification j
  | "compare-data-types-v1" => compareDataTypes j
  | _ => throw "package operation must be compile or run"

end Delvetalk.Package
