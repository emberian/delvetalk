/- Hosted syntax belongs above the local core parser and typed frontend. This layer
adds only document literal expansion and a hygienic import of the already
selected Document dependency; checking and evaluation remain ordinary Bend. -/
import Compiler.ObjectiveBendFrontEnd
import Delvetalk.DocumentTemplate
import Delvetalk.Generics

namespace Delvetalk.FrontEnd
open Lean
open Minidregg.Compiler
open ObjectiveBendFrontEnd
set_option autoImplicit false

structure Parsed where
  ast : Json
  /-- Equivalent ordinary source for inspection, with the generated import
  made explicit. Package identity still uses the original source bytes. -/
  expandedSource : String

def parseExpanded (name : String) (expanded : DocumentTemplate.Expansion) : Except Diagnostic Json := do
  match ObjectiveBendParse.parseObjective expanded.source with
  | .ok ast => return expanded.remap ast
  | .error diagnostic =>
    let span := if expanded.origins.isEmpty then diagnostic.span else
      diagnostic.span.map fun span =>
        let start := expanded.position span.start
        let stop := expanded.position span.stop
        { span with start := start.byte, stop := stop.byte, line := start.line }
    throw { stage := "objective-source-parse", message := diagnostic.message, span := span, sourceModule := some name }

/-- The sealed package loader resolves this exact edge to an earlier supplied
module and its source hash. We neither search a filesystem basename nor choose
an ambient prelude. A revised explicit dependency remains source-owned. -/
def parse (name source : String) : Except Diagnostic Parsed := do
  let expanded ← (DocumentTemplate.lower source).mapError fun message =>
    { stage := "document-template", message, sourceModule := some name }
  let ast ← parseExpanded name expanded
  let some binding := expanded.binding | return ⟨ast, source⟩
  let imports := ((ast.getObjVal? "imports").bind Json.getArr?).toOption.getD #[]
  let some dependency := imports.find? (fun edge =>
      (edge.getObjValAs? String "path").toOption == some "./Document.obend")
    | throw { stage := "document-template", sourceModule := some name, message := "doc literals require an explicit import of ./Document.obend (any alias is allowed); no document library is supplied implicitly" }
  let edge := Json.mkObj [("path", toJson "./Document.obend"), ("alias", toJson binding),
    ("span", (dependency.getObjVal? "span").toOption.getD Json.null)]
  let fields := (ast.getObj?).toOption.map (·.toList) |>.getD []
  let ast := Json.mkObj (fields.map fun (key, value) =>
    (key, if key == "imports" then Json.arr (imports.push edge) else value))
  return ⟨ast, "import ./Document.obend as " ++ binding ++ "\n" ++ expanded.source⟩

def parseSource (name source : String) : Except Diagnostic Json := do
  return (← parse name source).ast

/-- A closure through elaboration, checked once (the normal typed frontend on hosted parsed
modules; original source hashes and the exact derived import transcript travel through the
existing check): everything about a package that does not
depend on the entry. Lowering an entry from it (`Prepared.lower`) selects the reached knot,
builds the proposal and the packet, nothing more. -/
structure Prepared where
  modules : List SourceModule
  asts : List Json
  decoded : List ObjectiveBendElaborate.Module
  elaborated : ObjectiveBendElaborate.Elaborated
  instances : Json

def instancesNote (instances : Json) (diagnostic : Diagnostic) : Diagnostic :=
  { diagnostic with message := diagnostic.message ++
    (if instances == Json.arr #[] then "" else "; selected generic instances: " ++ instances.compress) }

/-- Specialize, elaborate and check a closure whose modules are already parsed. -/
def prepareParsed (modules : List SourceModule) (asts : List Json) (limits : Json) : Except Diagnostic Prepared := do
  if modules.length > 64 then throw (elaborationRefusal "preview module capacity refused")
  let sources := (modules.zip asts).map fun (module, ast) => Generics.Source.mk module ast
  let specialized ← (Generics.run sources.toArray).mapError fun message =>
    { stage := "source-specialization", message }
  let note := instancesNote specialized.instances
  let elaborated ← (ObjectiveBendElaborate.elaboratePackage specialized.modules).mapError
    (fun e => note (elaborationRefusal e))
  (checkClosure modules elaborated limits).mapError note
  return ⟨modules, asts, specialized.modules, elaborated, specialized.instances⟩

def prepare (modules : List SourceModule) (limits : Json) : Except Diagnostic Prepared := do
  let asts ← modules.mapM fun module => do
    let ast ← parseSource module.name module.source
    checkImports module ast
    return ast
  prepareParsed modules asts limits

def Prepared.lower (p : Prepared) (entryModule : Nat) (entryDefinition : String)
    (args projections limits : Json) (mode : String) : Except Diagnostic Lowering :=
  (lowerElaborated p.modules p.decoded p.elaborated true entryModule entryDefinition args projections limits mode).mapError
    (instancesNote p.instances)

def lowerWithInstances (modules : List SourceModule) (entryModule : Nat) (entryDefinition : String)
    (args projections limits : Json) (mode : String) : Except Diagnostic (Lowering × Json) := do
  discard <| options projections limits mode
  let prepared ← prepare modules limits
  return (← prepared.lower entryModule entryDefinition args projections limits mode, prepared.instances)

def lower (modules : List SourceModule) (entryModule : Nat) (entryDefinition : String)
    (args projections limits : Json) (mode : String) : Except Diagnostic Lowering := do
  return (← lowerWithInstances modules entryModule entryDefinition args projections limits mode).1

end Delvetalk.FrontEnd
