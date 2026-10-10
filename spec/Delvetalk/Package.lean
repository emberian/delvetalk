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
import Delvetalk.Entry

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
def modulesAndAsts (j : Json) :
    Except Diagnostic (List SourceModule × Json × List Minidregg.Compiler.ObjectiveBendSurface.Module) := do
  let raw ← match j.getObjVal? "modules" with
    | .ok value => lift value.getArr?
    | .error _ => pure #[Json.mkObj [("name", toJson "Package"), ("source", ← lift (j.getObjVal? "source"))]]
  if raw.isEmpty || raw.size > Bounds.maxModules then
    throw (requestRefusal s!"package requires 1..{Bounds.maxModules} modules")
  let mut modules : List SourceModule := []
  let mut asts : List Minidregg.Compiler.ObjectiveBendSurface.Module := []
  for value in raw do
    let name ← lift (value.getObjValAs? String "name")
    let source ← lift (value.getObjValAs? String "source")
    unless Minidregg.Compiler.ObjectiveBendParse.isIdent name.toList do throw (requestRefusal "invalid module name")
    if modules.any (fun m => m.name == name) then throw (requestRefusal "duplicate module name")
    if source.utf8ByteSize > Bounds.maxModuleBytes then throw (requestRefusal "source exceeds 512 KiB")
    let ast ← FrontEnd.parseSource name source
    let mut imports : List LockedImport := []
    for edge in ast.imports do
      let some target := modules.zipIdx.find? (fun (m,_) => edge.path == "./" ++ m.name ++ ".obend")
        | throw { stage := "package-request", message := s!"import must name an earlier supplied module: {edge.path}",
                  sourceModule := some name }
      imports := imports ++ [⟨edge.path, edge.importAlias, edge.span, target.2, target.1.name, target.1.sha256⟩]
    let module : SourceModule := ⟨name,source,Minidregg.Compiler.Sha256.hexString source,imports⟩
    checkImports module ast
    modules := modules ++ [module]
    asts := asts ++ [ast]
  return (modules, .arr raw, asts)

def modulesOfStructured (j : Json) : Except Diagnostic (List SourceModule × Json) := do
  let (modules, raw, _) ← modulesAndAsts j
  return (modules, raw)

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
  else
    let modules := (requestSources j).map fun (name, source) =>
      (name, source, (FrontEnd.parseSource name source).toOption)
    { d with hint := Delvetalk.Hints.hintFor modules d.stage d.message d.sourceModule (d.span.map (·.line)) }

/-- A parsed module's function definitions with their parameters' declared type texts. -/
def signaturesOf (ast : Minidregg.Compiler.ObjectiveBendSurface.Module) : List (String × List String) :=
  ast.decls.filterMap fun
    | .function signature _ _ _ =>
      some (signature.name, signature.params.map fun p => Minidregg.Compiler.ObjectiveBendElaborate.trimStr p.type)
    | _ => none

def functionSignatures (name source : String) : Except Diagnostic (List (String × List String)) := do
  return signaturesOf (← FrontEnd.parseSource name source)

open Minidregg.Compiler.ObjectiveBendElaborate (PTy lookupRow) in
/-- The first `n` parameter types of an elaborated function type and its result. -/
def peelPTy : Nat → PTy → List PTy × PTy
  | n + 1, .arrow _ _ domain codomain => let (rest, result) := peelPTy n codomain; (domain :: rest, result)
  | _, ty => ([], ty)

open Minidregg.Compiler.ObjectiveBendElaborate (PTy lookupRow) in
/-- The entry module's method table: every definition whose first parameter is
`State`, called as `(state, [input,] [context])`, with its input type (`{}` when
it takes none), result type and whether it is an activity. Type JSON is the
packet's (recursive sums are variables of the packet's bounds). Definitions with
more than one input beyond state and context are not callable methods and are
left out. -/
def methodTable (moduleName : String) (signatures : List (String × List String)) (globals : Option PTy) : Json :=
  Json.arr (methodRows moduleName signatures globals).toArray
where methodRows (moduleName : String) (signatures : List (String × List String)) (globals : Option PTy) : List Json :=
  signatures.filterMap fun ((fname, types) : String × List String) => do
    guard (types.head? == some "State")
    let ty ← lookupRow globals (moduleName ++ "." ++ fname)
    let (domains, result) := peelPTy types.length ty
    let context := types.length > 1 && (types.getLast?.map (·.endsWith "Context")).getD false
    let inputs := (types.drop 1).take (types.length - 1 - (if context then 1 else 0))
    guard (inputs.length ≤ 1)
    let input := if inputs.length == 1 then (domains[1]?.map PTy.json).getD (Json.mkObj [("tag", toJson "emptyRow")])
      else Json.mkObj [("tag", toJson "emptyRow")]
    let activity := match result with | .computation .. => true | _ => false
    return Json.mkObj [("name", toJson fname), ("input", input), ("result", result.json),
      ("activity", toJson activity), ("context", toJson context)]

open Minidregg.Compiler.ObjectiveBendElaborate (PTy) in
/-- A layer stack's method table: every method of every layer, the topmost definition of a
name winning (the one every call reaches). `stack` is top first: (module, its signatures). -/
def stackMethodTable (stack : List (String × List (String × List String))) (globals : Option PTy) : Json := Id.run do
  let mut seen : List String := []
  let mut rows : Array Json := #[]
  for (moduleName, signatures) in stack do
    for row in methodTable.methodRows moduleName (signatures.filter fun s => !seen.contains s.1) globals do
      rows := rows.push row
    seen := seen ++ signatures.map (·.1)
  return Json.arr rows

open Minidregg.Compiler.ObjectiveBendElaborate (PTy lookupRow) in
/-- A package's optional Bend law predicate, checked by shape: `law(old: State,
new: State, request: Request) -> Verdict`, pure, with `Verdict` exactly the sum
`admitted: {} | refused: {clause: String}` or `admitted: {} | refused: {clause: String, reading: String}`
(the host copies a reading into the refusal's reason); and `lawReads()` beside it. Nothing runs it here. -/
def lawShape (moduleName : String) (signatures : List (String × List String)) (globals : Option PTy)
    (sums : List (Nat × PTy)) : Except Diagnostic Json := do
  let refusal := fun (message : String) =>
    ({ stage := "objective-core-elaboration", message, sourceModule := some moduleName } : Diagnostic)
  let reads := signatures.any (·.1 == "lawReads")
  match signatures.find? (·.1 == "law") with
  | none =>
    if reads then throw <| refusal "lawReads needs a law: def law(old: State, new: State, request: Request) -> Verdict"
    else return Json.mkObj [("present", toJson false)]
  | some (_, types) =>
    unless types.length == 3 && types.take 2 == ["State", "State"] do
      throw <| refusal "law takes (old: State, new: State, request: Request)"
    let some ty := lookupRow globals (moduleName ++ ".law") | throw (refusal "law has no elaborated type")
    let (_, result) := peelPTy 3 ty
    if let .computation .. := result then throw (refusal "law must not be an activity")
    let row? := match result with
      | .variant row => some row
      | .variable index => match sums.lookup index with
        | some (.variant row) => some row
        | _ => none
      | _ => none
    let verdict := match row? with
      | some row => (Minidregg.Compiler.ObjectiveBendElaborate.rowNames row).length == 2 &&
          lookupRow (some row) "admitted" == some PTy.emptyRow &&
          (lookupRow (some row) "refused" == some (PTy.field "clause" .label .emptyRow) ||
           lookupRow (some row) "refused" == some (PTy.field "clause" .label (.field "reading" .label .emptyRow)) ||
           lookupRow (some row) "refused" == some (PTy.field "reading" .label (.field "clause" .label .emptyRow)))
      | none => false
    unless verdict do throw <| refusal "law must return Verdict: sum Verdict: admitted{} | refused{clause: String[, reading: String]}"
    return Json.mkObj [("present", toJson true), ("reads", toJson reads)]

/-- A request's closure, parsed once and prepared (specialized, elaborated, checked whole):
what a session caches per package, keyed by the request's modules and limits. -/
structure PreparedRequest where
  prepared : FrontEnd.Prepared
  sources : Json
  limits : Json
  /-- `sourcesSha256` of every artifact compiled from it (the CID of `sources`). -/
  sourcesCid : String

def prepareRequest (j : Json) : Except Diagnostic PreparedRequest :=
  (bare j).mapError (withHint j)
where bare (j : Json) : Except Diagnostic PreparedRequest := do
  let (modules, sources, asts) ← modulesAndAsts j
  return ⟨← FrontEnd.prepareParsed modules asts (getLimits j), sources, getLimits j,
    Delvetalk.Canonical.cidJson sources⟩

/-- One compiled entry: the artifact, the entry decoded and checked (no re-decoding needed
to run it), its type and the entry module's laws. -/
structure EntryCompiled where
  artifact : Json
  entry : Delvetalk.CheckedEntry
  laws : List (String × Minidregg.Compiler.ObjectiveBendLaw.LawExpr)
  /-- Each law's reading (`law NAME "reading": EXPR`; "" when none), by law name. -/
  readings : List (String × String)

/-- The readings the entry module's source gives its laws (`law NAME "reading": EXPR`). -/
def lawReadings (ast : Minidregg.Compiler.ObjectiveBendSurface.Module) : List (String × String) :=
  ast.decls.filterMap fun d => match d with
    | .law name _ reading _ => some (name, reading)
    | _ => none

/-- The artifact's `laws` table, `[{name, reading}]`: one entry per law the package
ENFORCES (`EntryCompiled.laws`), in that order, with its source reading or "" when it has
none. Built from the enforced laws, not from the source's readings, so a host looking a
refusing law up by name always finds it (`lawTable_names`). -/
def lawTable (laws : List String) (ast : Minidregg.Compiler.ObjectiveBendSurface.Module) :
    List (String × String) :=
  let readings := lawReadings ast
  laws.map fun name => (name, (readings.lookup name).getD "")

theorem lawTable_names (laws : List String) (ast : Minidregg.Compiler.ObjectiveBendSurface.Module) :
    (lawTable laws ast).map (·.1) = laws := by
  simp [lawTable, Function.comp_def]

/-- The world method a message plan term names (`{object, method: "X", argument}`). -/
def worldMethodOf : Minidregg.Theory.ObjectiveBendOpenRecursion.Term → Option String
  | .record fields => match fields.lookup "method" with
    | some (.label m) => some m
    | _ => none
  | _ => none

/-- A message activity's artifact (WHOLENESS §1): `dialect: "message"`, `world`, the world
methods the entry performs (first occurrence order), and `worldProtocol`, the World module's
source SHA-256. Any other artifact is unchanged. -/
def messageFields (modules : List SourceModule) (held : Delvetalk.CheckedEntry) (artifact : Json) : Json :=
  match held.sites with
  | none => artifact
  | some sites =>
    let methods := sites.toList.filterMap (worldMethodOf ·.1)
    let methods := methods.foldl (fun acc m => if acc.contains m then acc else acc ++ [m]) []
    let artifact := (artifact.setObjVal! "dialect" (toJson "message")).setObjVal! "world" (toJson methods)
    match modules.find? (·.name == "World") with
    | some world => artifact.setObjVal! "worldProtocol" (toJson world.sha256)
    | none => artifact

/-- Compile `entry` from a prepared closure: select its reached knot, build the proposal
and packet once, check it. -/
def compileEntryCore (request : PreparedRequest) (entry : String) : Except Diagnostic EntryCompiled := do
  let prepared := request.prepared
  let modules := prepared.modules
  let lowered ← prepared.lower (modules.length - 1) entry (.arr #[]) (.arr #[]) request.limits "definition"
  let accepted ← (accept lowered).mapError (FrontEnd.instancesNote prepared.instances)
  let packet := lowered.packet
  let entryModule := modules.getLast!
  let signatures := signaturesOf (prepared.asts.getLastD default)
  let globals := lowered.output.globalRow
  let law ← lawShape entryModule.name signatures globals lowered.output.sumBounds
  let stack := prepared.elaborated.ctx.stack.toList.reverse
  let methods := if stack.isEmpty then methodTable entryModule.name signatures globals else
    stackMethodTable (stack.filterMap fun name => do
      let i ← modules.findIdx? (·.name == name)
      let ast ← prepared.asts[i]?
      return (name, signaturesOf ast)) globals
  let pin := Delvetalk.Canonical.cidJson packet
  let artifact := Json.mkObj [
    ("schema", toJson "delvetalk.obend-package.v1"),
    ("modules", request.sources),
    ("sourcesSha256", toJson request.sourcesCid),
    ("entry", toJson entry), ("genericInstances", prepared.instances), ("limits", request.limits), ("packet", packet),
    ("packetSha256", toJson pin),
    ("type", typeJson accepted.typed.type),
    ("methods", methods), ("law", law)]
  -- Protocols the entry module claims (checked at elaboration): listed, and each method row
  -- names its protocol. Absent for a module that claims none (its artifact is unchanged).
  let claims := match prepared.elaborated.ctx.modules.find? (·.name == entryModule.name) with
    | some m => prepared.elaborated.ctx.claims m
    | none => []
  let artifact := if claims.isEmpty then artifact else
    let tagged := match artifact.getObjVal? "methods" with
      | .ok (.arr rows) => Json.arr (rows.map fun row =>
          match (row.getObjValAs? String "name").toOption.bind fun n => claims.find? (·.2.contains n) with
          | some (p, _) => row.setObjVal! "protocol" (toJson p)
          | none => row)
      | _ => artifact.getObjValD "methods"
    (artifact.setObjVal! "methods" tagged).setObjVal! "protocols" (toJson (claims.map (·.1)))
  let entryModuleName := (modules.getLast?).map (·.name)
  let refused := fun (message : String) =>
    ({ stage := "objective-typed-check", message, definition := some entry, sourceModule := entryModuleName } : Diagnostic)
  let held ← (Delvetalk.CheckedEntry.make pin accepted.source accepted.typed accepted.packet.fuel).mapError refused
  let artifact := messageFields modules held artifact
  let readings := lawTable (lowered.laws.map (·.1)) (prepared.asts.getLastD default)
  let artifact := if readings.isEmpty then artifact else artifact.setObjVal! "laws"
    (Json.arr (readings.toArray.map fun (name, reading) =>
      Json.mkObj [("name", toJson name), ("reading", toJson reading)]))
  return ⟨artifact, held, lowered.laws, readings⟩

/-- Compile the request's entry: prepare its closure, then the entry. -/
def compileEntry (j : Json) : Except Diagnostic EntryCompiled := do
  let request ← prepareRequest j
  (compileEntryCore request (← lift (j.getObjValAs? String "entry"))).mapError (withHint j)

-- A law without a reading is in the artifact's table with reading "", beside one with a
-- reading, in source order.
#guard
  let source := "edition ObjectiveBend 1\nrecord State:\n  count: Nat\nlaw small \"stays small\": new.count <= 100\nlaw plain: new.count <= 1000\ndef initial() -> State:\n  {count: 0n}\n"
  let request := Json.mkObj [("entry", toJson "initial"), ("modules", Json.arr #[Json.mkObj [("name", toJson "Package"), ("source", toJson source)]])]
  let entry := fun (name reading : String) => Json.mkObj [("name", toJson name), ("reading", toJson reading)]
  match compileEntry request with
  | .ok c => (c.artifact.getObjVal? "laws").toOption == some (Json.arr #[entry "small" "stays small", entry "plain" ""]) &&
      c.readings == [("small", "stays small"), ("plain", "")] && c.laws.map (·.1) == ["small", "plain"]
  | .error _ => false

/-- Compilation proper, refusing with the structured diagnostic. -/
def compileStructured (j : Json) : Except Diagnostic Compiled := do
  let compiled ← compileEntry j
  return (compiled.artifact, compiled.entry.type, compiled.laws)

/-- The functions of a module with the span of each body, in source order. -/
def functionBodies (ast : Minidregg.Compiler.ObjectiveBendSurface.Module) :
    List (String × Minidregg.Compiler.ObjectiveBendSurface.Span) :=
  ast.decls.filterMap fun
    | .function signature _ body _ => some (signature.name, match body with
      | .expr _ s | .cases _ _ s | .letB _ _ _ _ s => s)
    | _ => none

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

/-- Execute a checked closed term of first-order data type. -/
def executeTyped (term : Term) (type : Ty) (limits : Json) (profile : Bool) : Except String Json := do
  if !type.isData then throw "package result must have first-order data type"
  let ticks ← bounded limits "ticks" Bounds.ticksDefault Bounds.ticksMax
  let heap ← bounded limits "heap" Bounds.heapDefault Bounds.heapMax
  let stack ← bounded limits "stack" Bounds.stackDefault Bounds.stackMax
  let nodes ← bounded limits "nodes" Bounds.nodesDefault Bounds.nodesMax
  let bytes ← bounded limits "bytes" Bounds.bytesDefault Bounds.bytesMax
  let budget : Budget := ⟨nodes,ticks,bytes⟩
  let capacities : Limits := ⟨heap,stack⟩
  let profiled := fun (reply : Json) => if profile then
      reply.setObjVal! "profile" (Delvetalk.Profile.profile capacities bytes ticks (initial term))
    else reply
  match execute capacities budget term with
  | .ok execution =>
      let result := execution.extraction.result
      return profiled <| Json.mkObj [("status", toJson "finished"), ("value", dataJson result.value),
        ("type", typeJson type), ("ticksUsed", toJson (ticks - result.remaining.ticks)),
        ("heapCells", toJson result.state.heap.size),
        ("nodesUsed", toJson (nodes - result.remaining.nodes))]
  | .error (failure,state,remaining) =>
      return Json.mkObj [("status", toJson "refused"),
        ("failure", toJson (reprStr failure)),
        ("ticksUsed", toJson (ticks - remaining.ticks)), ("heapCells", toJson state.heap.size)]

/-- One global demand/extraction budget. No game rule or host authority lives here. -/
def executePacket (packet arguments limits : Json) (profile : Bool := false) : Except String Json := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let values ← (← arguments.getArr?).toList.mapM (decodeData Bounds.dataWireDepth)
  let terms ← values.mapM argumentTerm
  let source := terms.foldl applyArgument decoded.source
  let some checked := check source [] decoded.fuel | throw "applied package refused by Mini type checker"
  executeTyped source.term checked.type limits profile

/-- `run` on a held entry: arguments are checked alone and composed with its derivation. -/
def executeEntry (entry : Delvetalk.CheckedEntry) (arguments limits : Json) (profile : Bool := false) :
    Except String Json := do
  let values ← (← arguments.getArr?).toList.mapM (decodeData Bounds.dataWireDepth)
  let mut applied := entry
  for value in values do
    applied ← applied.apply (← argumentTerm value) .empty
  executeTyped applied.source.term applied.type limits profile

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

/-- Native data execution on a held entry: the packet is neither decoded nor re-checked;
the arguments are admitted against the entry's checked type (`prepareNativeChecked`). -/
def executeDataEntry (entry : Delvetalk.CheckedEntry) (arguments : Array Data) (limits : Json) :
    Except String DataExecution :=
  let argumentBytes := 2 + arguments.foldl (fun n value => n + dataJsonBytes value) 0 + (arguments.size - 1)
  executePreparedNative (PackageData.prepareNativeChecked entry.source entry.checked entry.fuel arguments)
    argumentBytes limits

/-- A package's declared relations (RELATIONAL §2): the value of its nullary `relations()`
(a list of `{field, key: List<String>}`), evaluated once at compile so the host reads it from
the artifact without compiling a def per object. `none` when the entry module declares none. -/
def relationsOf (request : PreparedRequest) : Except Diagnostic (Option Json) := do
  let ast := request.prepared.asts.getLastD default
  unless (signaturesOf ast).any (fun s => s.1 == "relations" && s.2.isEmpty) do return none
  let refusal := fun (message : String) =>
    ({ stage := "objective-core-elaboration", message := "relations(): " ++ message,
       sourceModule := (request.prepared.modules.getLast?).map (·.name) } : Diagnostic)
  let compiled ← compileEntryCore request "relations"
  match executeDataEntry compiled.entry #[] request.limits with
  | .error e => throw (refusal e)
  | .ok (.refused failure _) => throw (refusal failure)
  | .ok (.finished value _ _ _) =>
    let some rows := Minidregg.Compiler.ObjectiveBendDataWire.listItems? value
      | throw (refusal "is not a list")
    let decls ← rows.toList.mapM fun row => do
      let .record fields := row | throw (refusal "a declaration is {field, key}")
      let some (.label field) := fields.lookup "field" | throw (refusal "a declaration names its field")
      let some keyData := fields.lookup "key" | throw (refusal "a declaration names its key")
      let some keys := Minidregg.Compiler.ObjectiveBendDataWire.listItems? keyData
        | throw (refusal "a key is a list of column names")
      let columns ← keys.toList.mapM fun k => match k with
        | .label c => pure c
        | _ => throw (refusal "a key column is a String")
      return Json.mkObj [("field", toJson field), ("key", toJson columns)]
    return some (Json.arr decls.toArray)

/-- Compile `entry` from a prepared closure; the artifact lists the package's `relations`
when it declares them. -/
def compileEntryFrom (request : PreparedRequest) (entry : String) : Except Diagnostic EntryCompiled := do
  let compiled ← compileEntryCore request entry
  match ← relationsOf request with
  | none => return compiled
  | some relations => return { compiled with artifact := compiled.artifact.setObjVal! "relations" relations }

/-- `run-data-v1` on a held entry (the strict typed-data wire). -/
def executeDataEntryWire (entry : Delvetalk.CheckedEntry) (arguments limits : Json) : Except String Json := do
  let values ← (← arguments.getArr?).toList.mapM fun value => do
    return (← (PackageData.decode 256 value).run Bounds.ticksMax).1
  return (← executePreparedNative (PackageData.prepareNativeChecked entry.source entry.checked entry.fuel values.toArray)
    arguments.compress.utf8ByteSize limits).wire

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
      parsed := parsed.push (Json.mkObj [("name", toJson name),
        ("imports", Json.arr (ast.imports.map (·.json)).toArray)])
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
