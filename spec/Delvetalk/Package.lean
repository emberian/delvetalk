/- Generic source-package boundary. Mini owns parsing, elaboration, typing and
   shared-demand execution. This adapter adds only JSON framing and data IO. -/
import Delvetalk.Core
import Delvetalk.FrontEnd
import Compiler.ObjectiveBendFrontEnd
import Compiler.ObjectiveBendDataWire
import Theory.ObjectiveBendDemandData
import Delvetalk.PackageData
import Delvetalk.Reflection
import Delvetalk.Turn
import Delvetalk.Document
import Delvetalk.EvaluateTerm
import Delvetalk.Limits
import Delvetalk.Canonical
import Delvetalk.Hints

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
  ("ticks", toJson (toString Bounds.ticksDefault)), ("heap", toJson (toString Bounds.heapDefault)),
  ("stack", toJson (toString Bounds.stackDefault)), ("typeFuel", toJson (toString Bounds.typeFuelDefault))]

def getLimits (j : Json) : Json := (j.getObjVal? "limits").toOption.getD defaultLimits

/-- A compiler refusal, structurally: stage, message, and for a source refusal the
module and line span (`dregg.bend.compiler-diagnostic.v1` as data). -/
abbrev Diagnostic := Minidregg.Compiler.ObjectiveBendFrontEnd.Diagnostic

/-- A refusal of the request itself (not of the source): no module, no span. -/
def requestRefusal (message : String) : Diagnostic := { stage := "package-request", message }

/-- The flat form: a request refusal is its message, a compiler refusal its diagnostic JSON. -/
def Diagnostic.render (d : Diagnostic) : String :=
  if d.stage == "package-request" then d.message else d.json.compress

private def lift {α : Type} (x : Except String α) : Except Diagnostic α := x.mapError requestRefusal

/-- A sealed in-memory package: imports name earlier modules explicitly supplied
by the caller. The adapter never reads an import path from the filesystem. -/
def modulesOfStructured (j : Json) : Except Diagnostic (List SourceModule × Json) := do
  let raw ← match j.getObjVal? "modules" with
    | .ok value => lift value.getArr?
    | .error _ => pure #[Json.mkObj [("name", toJson "Package"), ("source", ← lift (j.getObjVal? "source"))]]
  if raw.isEmpty || raw.size > Bounds.maxModules then
    throw (requestRefusal s!"package requires 1..{Bounds.maxModules} modules")
  let mut modules : List SourceModule := []
  for value in raw do
    let name ← lift (value.getObjValAs? String "name")
    let source ← lift (value.getObjValAs? String "source")
    unless Minidregg.Compiler.ObjectiveBendParse.isIdent name.toList do throw (requestRefusal "invalid module name")
    if modules.any (fun m => m.name == name) then throw (requestRefusal "duplicate module name")
    if source.utf8ByteSize > Bounds.maxModuleBytes then throw (requestRefusal "source exceeds 512 KiB")
    let ast ← FrontEnd.parseSource name source
    let mut imports : List LockedImport := []
    for edge in (← lift ((← lift (ast.getObjVal? "imports")).getArr?)) do
      let path ← lift (edge.getObjValAs? String "path")
      let some target := modules.zipIdx.find? (fun (m,_) => path == "./" ++ m.name ++ ".obend")
        | throw { stage := "package-request", message := "import must name an earlier supplied module",
                  sourceModule := some name }
      imports := imports ++ [⟨path, ← lift (edge.getObjValAs? String "alias"), ← lift (edge.getObjVal? "span"),
        target.2, target.1.name, target.1.sha256⟩]
    modules := modules ++ [⟨name,source,Minidregg.Compiler.Sha256.hexString source,imports⟩]
  return (modules, .arr raw)

def modulesOf (j : Json) : Except String (List SourceModule × Json) :=
  (modulesOfStructured j).mapError Diagnostic.render

/-- A compiled package: the artifact JSON, the entry's checked type and its laws. -/
abbrev Compiled := Json × Ty × List (String × Minidregg.Compiler.ObjectiveBendLaw.LawExpr)

/-- The request's modules as (name, source), for hints. -/
def requestSources (j : Json) : List (String × String) :=
  match j.getObjVal? "modules" >>= Json.getArr? with
  | .ok raw => raw.toList.filterMap fun m =>
      match m.getObjValAs? String "name", m.getObjValAs? String "source" with
      | .ok name, .ok source => some (name, source)
      | _, _ => none
  | .error _ => match j.getObjValAs? String "source" with
    | .ok source => [("Package", source)]
    | .error _ => []

/-- A source refusal carries the dialect hint its source suggests, if any. -/
def withHint (j : Json) (d : Diagnostic) : Diagnostic :=
  if d.stage == "package-request" || d.hint.isSome then d
  else { d with hint := Delvetalk.Hints.hintFor (requestSources j) d.sourceModule (d.span.map (·.line)) }

/-- Compilation proper, refusing with the structured diagnostic. -/
def compileStructured (j : Json) : Except Diagnostic Compiled :=
  (compileStructuredBare j).mapError (withHint j)
where compileStructuredBare (j : Json) : Except Diagnostic Compiled := do
  let (modules, sources) ← modulesOfStructured j
  let entry ← lift (j.getObjValAs? String "entry")
  let (lowered, genericInstances) ← FrontEnd.lowerWithInstances modules (modules.length - 1) entry (.arr #[]) (.arr #[]) (getLimits j) "definition"
  let accepted ← (accept lowered).mapError (fun diagnostic => { diagnostic with message := diagnostic.message ++
      (if genericInstances == Json.arr #[] then "" else "; selected generic instances: " ++ genericInstances.compress) })
  let packet := lowered.packet
  let artifact := Json.mkObj [
    ("schema", toJson "delvetalk.obend-package.v1"),
    ("modules", sources),
    ("sourcesSha256", toJson (Delvetalk.Canonical.cidJson sources)),
    ("entry", toJson entry), ("genericInstances", genericInstances), ("limits", getLimits j), ("packet", packet),
    ("packetSha256", toJson (Delvetalk.Canonical.cidJson packet)),
    ("type", typeJson accepted.typed.type)]
  return (artifact, accepted.typed.type, lowered.laws)

/-- The functions of a module with the span of each body, in source order. -/
def functionBodies (ast : Json) : List (String × Minidregg.Compiler.ObjectiveBendParse.Span) :=
  match ast.getObjVal? "declarations" >>= Json.getArr? with
  | .error _ => []
  | .ok declarations => declarations.toList.filterMap fun d => do
      guard ((d.getObjValAs? String "kind").toOption == some "function")
      let name ← (d.getObjVal? "signature" >>= (·.getObjValAs? String "name")).toOption
      let span ← (d.getObjVal? "body" >>= (·.getObjVal? "span")).toOption
      let start ← (span.getObjValAs? Nat "start").toOption
      let stop ← (span.getObjValAs? Nat "end").toOption
      let line ← (span.getObjValAs? Nat "line").toOption
      return (name, ⟨start, stop, line⟩)

/-- The elaborator and the checker refuse without a position. For a refusal that has none,
find the first function (in module, then source order) that on its own, with the modules
before it, is refused with the same stage and message, and report that module and the span of
its body. A refusal that already carries a span is returned unchanged. -/
def localize (modules : List (String × String)) (limits : Json) (d : Diagnostic) : Diagnostic := Id.run do
  if d.span.isSome then return d
  let mut seen := 0
  for (name, source) in modules do
    seen := seen + 1
    let .ok ast := FrontEnd.parseSource name source | continue
    for (function, span) in functionBodies ast do
      let request := Json.mkObj [("entry", toJson function), ("limits", limits),
        ("modules", Json.arr ((modules.take seen).map fun (n, src) =>
          Json.mkObj [("name", toJson n), ("source", toJson src)]).toArray)]
      if let .error e := compileStructured request then
        if e.stage == d.stage && e.message == d.message then
          return { d with span := some span, sourceModule := some name }
  return d

/-- A pure dry-run compile of `(name, source)` modules, in dependency order, for `entry`:
the artifact, or the diagnostic with its stage, message, module and span intact. -/
def checkPackage (modules : List (String × String)) (entry : String) (limits : Json := defaultLimits) :
    Except Diagnostic Json := do
  let request := Json.mkObj [("entry", toJson entry), ("limits", limits),
    ("modules", Json.arr (modules.map fun (name, source) =>
      Json.mkObj [("name", toJson name), ("source", toJson source)]).toArray)]
  match compileStructured request with
  | .error d => throw (localize modules limits d)
  | .ok (artifact, _, laws) =>
    if !laws.isEmpty then throw (requestRefusal "package laws require a host law adapter; this pure profile refuses them")
    return artifact

def compileKeepingLaws (j : Json) :
    Except String (Json × Ty × List (String × Minidregg.Compiler.ObjectiveBendLaw.LawExpr)) :=
  (compileStructured j).mapError Diagnostic.render

def compile (j : Json) : Except String Json := do
  let (artifact, _, laws) ← compileKeepingLaws j
  if !laws.isEmpty then throw "package laws require a host law adapter; this pure profile refuses them"
  return artifact

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

open Delvetalk.Turn (applyArgument bounded)

/-- One global demand/extraction budget. No game rule or host authority lives here. -/
def executePacket (packet arguments limits : Json) (profile : Bool := false) : Except String Json := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let values ← (← arguments.getArr?).toList.mapM (decodeData Bounds.dataWireDepth)
  let terms ← values.mapM argumentTerm
  let source := terms.foldl applyArgument decoded.source
  let some checked := check source [] decoded.fuel | throw "applied package refused by Mini type checker"
  if !checked.type.isData then throw "package result must have first-order data type"
  let ticks ← bounded limits "ticks" Bounds.ticksDefault Bounds.ticksMax
  let heap ← bounded limits "heap" Bounds.heapDefault Bounds.heapMax
  let stack ← bounded limits "stack" Bounds.stackDefault Bounds.stackMax
  let nodes ← bounded limits "nodes" Bounds.nodesDefault Bounds.nodesMax
  let bytes ← bounded limits "bytes" Bounds.bytesDefault Bounds.bytesMax
  let budget : Budget := ⟨nodes,ticks,bytes⟩
  let capacities : Limits := ⟨heap,stack⟩
  let profiled := fun (reply : Json) => if profile then
      reply.setObjVal! "profile" (Delvetalk.Profile.profile capacities bytes ticks (initial source.term))
    else reply
  match execute capacities budget source.term with
  | .ok execution =>
      let result := execution.extraction.result
      return profiled <| Json.mkObj [("status", toJson "finished"), ("value", dataJson result.value),
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
  let converted ← (← arguments.getArr?).toList.mapM (jsonData Bounds.plainJsonDepth)
  let inputNodes := (converted.map Prod.snd).foldl (· + ·) 0
  let result ← executePacket packet (.arr ((converted.map fun pair => dataJson pair.1).toArray)) limits
  if (← result.getObjValAs? String "status") != "finished" then return result
  let (value,outputNodes) ← dataPlain Bounds.plainJsonDepth (← decodeData Bounds.dataWireDepth (← result.getObjVal? "value"))
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
    ((j.getObjValAs? Bool "profile").toOption.getD false)

def run (j : Json) : Except String Json := do
  verifyArtifact (← j.getObjVal? "artifact")
  runVerified j

/-- Native callers keep checked materialized Data in memory. Wire encoding is
reserved for the transport boundary; it must not become a second evaluation or
an unnecessary decode of our own output inside one receiving turn. -/
structure DataUsage where
  ticksUsed : Nat
  conversionNodes : Nat
  heapCells : Nat

inductive DataExecution where
  | refused (failure : String) (usage : DataUsage)
  | finished (value : Data) (type : Ty) (nodesUsed : Nat) (usage : DataUsage)

def DataExecution.usage : DataExecution → DataUsage
  | .refused _ usage | .finished _ _ _ usage => usage

def DataUsage.fields (usage : DataUsage) : List (String × Json) :=
  [("ticksUsed", toJson usage.ticksUsed), ("conversionNodes", toJson usage.conversionNodes),
   ("heapCells", toJson usage.heapCells)]

def DataExecution.wire : DataExecution → Json
  | .refused failure usage => Json.mkObj (
      [("executionProfile", toJson "delvetalk-package-data-v1"),
       ("status", toJson "refused"), ("failure", toJson failure)] ++ usage.fields)
  | .finished value type nodes usage => Json.mkObj (
      [("executionProfile", toJson "delvetalk-package-data-v1"),
       ("status", toJson "finished"), ("value", dataJson value), ("type", typeJson type),
       ("nodesUsed", toJson nodes)] ++ usage.fields)

/-- Explicit recursive-data execution. Full eager materialization and output
shape checking happen here, before any native consumer sees a Data value.
Conversion and machine work share the existing whole-execution allowance. -/
private def executePreparedData (prepared : PackageData.Work (AnnotatedTerm × Ty × Nat))
    (argumentBytes : Nat) (limits : Json) : Except String DataExecution := do
  let bytes ← bounded limits "bytes" Bounds.bytesDefault Bounds.bytesMax
  let inputBytes ← bounded limits "inputBytes" bytes Bounds.bytesMax
  if argumentBytes > inputBytes then throw "typed data input byte capacity"
  let ticks ← bounded limits "ticks" Bounds.ticksDefault Bounds.ticksMax
  let work ← bounded limits "work" ticks Bounds.ticksMax
  let allowance := min ticks work
  let ((source, type, _), remaining) ← prepared.run allowance
  let before := allowance - remaining
  let heap ← bounded limits "heap" Bounds.heapDefault Bounds.heapMax
  let stack ← bounded limits "stack" Bounds.stackDefault Bounds.stackMax
  let nodes ← bounded limits "nodes" Bounds.nodesDefault Bounds.nodesMax
  let budget : Budget := ⟨nodes, ticks - before, bytes⟩
  match execute ⟨heap, stack⟩ budget source.term with
  | .error (failure, state, rest) =>
      return .refused (reprStr failure) ⟨budget.ticks - rest.ticks, before, state.heap.size⟩
  | .ok execution =>
      let result := execution.extraction.result
      -- Recursive aliases and the complete returned value are checked, including
      -- payloads which a later source Decision may explicitly refuse.
      let outputAllowance := min remaining result.remaining.ticks
      let (_, after) ← (PackageData.validate source.assumptions Bounds.dataWireDepth result.value type).run outputAllowance
      return .finished result.value type (nodes - result.remaining.nodes)
        ⟨budget.ticks - result.remaining.ticks, before + outputAllowance - after, result.state.heap.size⟩

/-- Native finite arguments retain lazy demand cells instead of literal syntax.
Their preparation and extraction still consume the shared execution allowance. -/
private def executePreparedNative (prepared : PackageData.Work PackageData.NativePreparation)
    (argumentBytes : Nat) (limits : Json) : Except String DataExecution := do
  let bytes ← bounded limits "bytes" Bounds.bytesDefault Bounds.bytesMax
  let inputBytes ← bounded limits "inputBytes" bytes Bounds.bytesMax
  if argumentBytes > inputBytes then throw "typed data input byte capacity"
  let ticks ← bounded limits "ticks" Bounds.ticksDefault Bounds.ticksMax
  let work ← bounded limits "work" ticks Bounds.ticksMax
  let allowance := min ticks work
  let (preparation, remaining) ← prepared.run allowance
  let source := preparation.source
  let type := preparation.resultType
  let before := allowance - remaining
  let heap ← bounded limits "heap" Bounds.heapDefault Bounds.heapMax
  let stack ← bounded limits "stack" Bounds.stackDefault Bounds.stackMax
  let nodes ← bounded limits "nodes" Bounds.nodesDefault Bounds.nodesMax
  let budget : Budget := ⟨nodes, ticks - before, bytes⟩
  match executeDataArguments ⟨heap, stack⟩ budget source.term preparation.arguments.toList with
  | .error (failure, state, rest) =>
      return .refused (reprStr failure) ⟨budget.ticks - rest.ticks, before, state.heap.size⟩
  | .ok execution =>
      let result := execution.extraction.result
      -- Recursive aliases and the complete returned value are checked, including
      -- payloads which a later source Decision may explicitly refuse.
      let outputAllowance := min remaining result.remaining.ticks
      let (_, after) ← (PackageData.validate source.assumptions Bounds.dataWireDepth result.value type).run outputAllowance
      return .finished result.value type (nodes - result.remaining.nodes)
        ⟨budget.ticks - result.remaining.ticks, before + outputAllowance - after, result.state.heap.size⟩

/-- Conformance reference only; no physical operation dispatch selects it. -/
def executeQuotedDataValue (packet arguments limits : Json) : Except String DataExecution :=
  executePreparedData (PackageData.prepare packet arguments) arguments.compress.utf8ByteSize limits

def executeDataValue (packet arguments limits : Json) : Except String DataExecution :=
  executePreparedNative (PackageData.prepareNativeWire packet arguments) arguments.compress.utf8ByteSize limits

/-- Checked native execution retains the physical wire byte cap. Finite values
use lazy native demand cells; their first force avoids source-literal machinery. -/
def executeDataValues (packet : Json) (arguments : Array Data) (limits : Json) : Except String DataExecution :=
  let argumentBytes := 2 + arguments.foldl (fun n value => n + dataJsonBytes value) 0
    + (arguments.size - 1)
  executePreparedNative (PackageData.prepareNative packet arguments) argumentBytes limits

/-- A native receiving caller supplies the exact size of its retained physical
argument frames; it must not replace compact physical bytes with an expanded
internal DataWire representation when enforcing the transport cap. -/
def executeDataValuesSized (packet : Json) (arguments : Array Data) (physicalBytes : Nat)
    (limits : Json) : Except String DataExecution :=
  executePreparedNative (PackageData.prepareNative packet arguments) physicalBytes limits

/-- All-compact physical package boundary: input and output interpretation is
bound to the exact checked packet carried by the verified artifact. -/
def runCompactDataVerified (j : Json) : Except String Json := do
  let artifact ← j.getObjVal? "artifact"
  let packet ← artifact.getObjVal? "packet"
  let arguments ← j.getObjVal? "arguments"
  let execution ← executePreparedNative (PackageData.prepareNativeCompact packet arguments)
    arguments.compress.utf8ByteSize (getLimits j)
  match execution with
  | .refused _ _ => return execution.wire
  | .finished value type nodes usage =>
    let decoded ← decodePacket packet
    let ticks ← bounded (getLimits j) "ticks" Bounds.ticksDefault Bounds.ticksMax
    let work ← bounded (getLimits j) "work" ticks Bounds.ticksMax
    let allowance := min ticks work
    let available := allowance - (usage.ticksUsed + usage.conversionNodes)
    let (wire, remaining) ← (PackageData.encodeCompact decoded.source.assumptions Bounds.dataWireDepth type value).run available
    let usage := { usage with conversionNodes := usage.conversionNodes + available - remaining }
    return Json.mkObj ([("executionProfile", toJson "delvetalk-package-compact"),
      ("status", toJson "finished"), ("value", wire), ("type", typeJson type),
      ("nodesUsed", toJson nodes), ("schemaPacketSha256", ← artifact.getObjVal? "packetSha256")] ++ usage.fields)

def runCompactData (j : Json) : Except String Json := do
  verifyArtifact (← j.getObjVal? "artifact")
  runCompactDataVerified j

/-- The external recursive-data wire is unchanged. Native receiving uses the
same execution function without serializing and decoding its checked result. -/
def executeDataPacket (packet arguments limits : Json) : Except String Json := do
  return (← executeDataValue packet arguments limits).wire

def runDataVerified (j : Json) : Except String Json := do
  let artifact ← j.getObjVal? "artifact"
  executeDataPacket (← artifact.getObjVal? "packet") (← j.getObjVal? "arguments") (getLimits j)

def runData (j : Json) : Except String Json := do
  verifyArtifact (← j.getObjVal? "artifact")
  runDataVerified j

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

/-- Physical conversion against a selected type of the exact verified artifact.
The packet hash travels with the result; a different schema is never inferred. -/
def compactCodec (j : Json) (encode : Bool) : Except String Json := do
  let selection ← j.getObjVal? "selection"
  let (a, declared, path) ← selectedDataType selection
  let work ← bounded j "work" Bounds.ticksDefault Bounds.ticksMax
  let bytes ← bounded j "bytes" Bounds.bytesDefault Bounds.bytesMax
  let value ← j.getObjVal? "value"
  if value.compress.utf8ByteSize > bytes then throw "compact codec input byte capacity"
  let action : PackageData.Work Json := do
    let ty ← PackageData.select a declared path
    PackageData.shape a Bounds.dataWireDepth [] ty
    if encode then
      let data ← PackageData.decode Bounds.dataWireDepth value
      PackageData.validate a Bounds.dataWireDepth data ty
      PackageData.encodeCompact a Bounds.dataWireDepth ty data
    else
      let data ← PackageData.decodeCompact a Bounds.dataWireDepth ty value
      PackageData.validate a Bounds.dataWireDepth data ty
      return dataJson data
  let (wire, remaining) ← action.run work
  if wire.compress.utf8ByteSize > bytes then throw "compact codec output byte capacity"
  return Json.mkObj [("status", toJson (if encode then "encoded" else "decoded")),
    ("value", wire), ("conversionNodes", toJson (work - remaining)),
    ("schemaPacketSha256", ← (← selection.getObjVal? "artifact").getObjVal? "packetSha256")]

def compareDataTypes (j : Json) : Except String Json := do
  let (left, lt, lp) ← selectedDataType (← j.getObjVal? "left")
  let (right, rt, rp) ← selectedDataType (← j.getObjVal? "right")
  let work ← bounded j "work" Bounds.ticksDefault Bounds.ticksMax
  let action : PackageData.Work Bool := do
    let a ← PackageData.select left lt lp
    let b ← PackageData.select right rt rp
    PackageData.shape left Bounds.dataWireDepth [] a
    PackageData.shape right Bounds.dataWireDepth [] b
    PackageData.equivalent left right Bounds.dataWireDepth [] a b
  let (equal, remaining) ← action.run work
  return Json.mkObj [("status", toJson "compared"), ("equal", toJson equal),
    ("conversionNodes", toJson (work - remaining))]

/-- Validate every typed allocation alternative against the checked source Value
ABI. Configuration models remain independently typed for receiving admission. -/
def allocationDataTypes (j : Json) : Except String Json := do
  let (left, lt, lp) ← selectedDataType (← j.getObjVal? "left")
  let (right, rt, rp) ← selectedDataType (← j.getObjVal? "right")
  let work ← bounded j "work" Bounds.ticksDefault Bounds.ticksMax
  let action : PackageData.Work Bool := do
    let allocations ← PackageData.select left lt lp
    let value ← PackageData.select right rt rp
    PackageData.shape right Bounds.dataWireDepth [] value
    let head ← PackageData.allocationListType left allocations
    for leaf in (← PackageData.allocationLeaves left Bounds.dataWireDepth head) do
      let fields ← PackageData.members Bounds.dataWireDepth leaf
      for key in ["protocol", "law"] do
        let some member := fields.lookup key | throw "allocation descriptor field missing"
        unless (← PackageData.equivalent left right Bounds.dataWireDepth [] member value) do return false
    return true
  let (equal, remaining) ← action.run work
  return Json.mkObj [("status", toJson "compared"), ("equal", toJson equal),
    ("conversionNodes", toJson (work - remaining))]

def turnStartVerified (j : Json) : Except String Json := do
  let artifact ← j.getObjVal? "artifact"
  Delvetalk.Turn.start (← artifact.getObjVal? "packet") (← j.getObjVal? "arguments") (getLimits j) j

def turnResumeVerified (j : Json) : Except String Json := do
  let artifact ← j.getObjVal? "artifact"
  Delvetalk.Turn.resumeTurn (← artifact.getObjVal? "packet") (← j.getObjVal? "checkpoint")
    (← j.getObjVal? "response") (getLimits j) j

def turnStart (j : Json) : Except String Json := do
  verifyArtifact (← j.getObjVal? "artifact")
  turnStartVerified j

def turnResume (j : Json) : Except String Json := do
  verifyArtifact (← j.getObjVal? "artifact")
  turnResumeVerified j

def job (j : Json) : Except String Json := do
  match ← j.getObjValAs? String "op" with
  | "source-imports-v1" =>
    let raw ← (← j.getObjVal? "modules").getArr?
    if raw.isEmpty || raw.size > Bounds.maxModules then throw s!"source import request requires 1..{Bounds.maxModules} modules"
    let mut names : List String := []
    let mut total := 0
    let mut parsed : Array Json := #[]
    for value in raw do
      let name ← value.getObjValAs? String "name"
      unless Minidregg.Compiler.ObjectiveBendParse.isIdent name.toList do throw "invalid module name"
      if names.contains name then throw "duplicate module name"
      names := name :: names
      let source ← value.getObjValAs? String "source"
      if source.utf8ByteSize > Bounds.maxModuleBytes then throw "source exceeds 512 KiB"
      total := total + source.utf8ByteSize
      if total > Bounds.maxPackageSourceBytes then throw "source import request exceeds 1 MiB"
      let ast ← (FrontEnd.parseSource name source).mapError (fun d => d.json.compress)
      parsed := parsed.push (Json.mkObj [("name", toJson name), ("imports", ← ast.getObjVal? "imports")])
    return Json.mkObj [("status", toJson "parsed-imports"), ("modules", Json.arr parsed)]
  | "template-expand" =>
    let source ← j.getObjValAs? String "source"
    if source.utf8ByteSize > Bounds.maxModuleBytes then throw "source exceeds 512 KiB"
    let expanded ← (FrontEnd.parse "Template" source).mapError (fun d => d.json.compress)
    return Json.mkObj [("status", toJson "expanded"), ("source", toJson expanded.expandedSource),
      ("schema", toJson "delvetalk.document-template-expansion.v1")]
  | "check-package" =>
    let raw ← (← j.getObjVal? "modules").getArr?
    let modules ← raw.toList.mapM fun m => do return (← m.getObjValAs? String "name", ← m.getObjValAs? String "source")
    match checkPackage modules (← j.getObjValAs? String "entry") (getLimits j) with
    | .ok artifact => return Json.mkObj [("status", toJson "checked"), ("artifact", artifact)]
    | .error d => return Json.mkObj [("status", toJson "refused"), ("diagnostic", d.json)]
  | "compile" => return Json.mkObj [("status", toJson "compiled"), ("artifact", ← compile j)]
  | "run" => run j
  | "canonical-encode" => Delvetalk.Canonical.encodeOp j
  | "canonical-decode" => Delvetalk.Canonical.decodeOp j
  | "evaluate-term" => Delvetalk.EvaluateTerm.op j
  | "render-document" => Delvetalk.Document.renderOp j
  | "turn-start" => turnStart j
  | "turn-resume" => turnResume j
  | "run-data-v1" => runData j
  | "run-compact" => runCompactData j
  | "encode-compact" => compactCodec j true
  | "decode-compact" => compactCodec j false
  | "inspect-spec-v1" => inspectSpecification j
  | "compare-data-types-v1" => compareDataTypes j
  | "allocation-data-types-v1" => allocationDataTypes j
  | _ => throw "package operation must be compile or run"

end Delvetalk.Package
