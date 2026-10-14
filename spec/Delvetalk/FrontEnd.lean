/- Hosted syntax belongs above the local core parser and typed frontend. This layer
adds only document literal expansion and a hygienic import of the already
selected Document dependency; checking and evaluation remain ordinary Bend. -/
import Compiler.ObjectiveBendFrontEnd
import Delvetalk.DocumentTemplate
import Delvetalk.Generics

namespace Delvetalk.FrontEnd
open Lean
open Delvetalk.Compiler
open ObjectiveBendFrontEnd
set_option autoImplicit false

def parseExpanded (name : String) (expanded : DocumentTemplate.Expansion) :
    Except Diagnostic ObjectiveBendSurface.Module := do
  match ObjectiveBendParse.parseObjective expanded.source with
  | .ok ast => return expanded.remap ast
  | .error diagnostic =>
    let span := if expanded.origins.isEmpty then diagnostic.span else
      diagnostic.span.map expanded.span
    throw { stage := "objective-source-parse", message := diagnostic.message, span := span, sourceModule := some name }

/-- The sealed package loader resolves this exact edge to an earlier supplied
module and its source hash. We neither search a filesystem basename nor choose
an ambient prelude. A revised explicit dependency remains source-owned. -/
def parseSource (name source : String) : Except Diagnostic ObjectiveBendSurface.Module := do
  let expanded ← (DocumentTemplate.lower source).mapError fun message =>
    { stage := "document-template", message, sourceModule := some name }
  let ast ← parseExpanded name expanded
  let some binding := expanded.binding | return ast
  let some dependency := ast.imports.find? (·.path == "./Document.obend")
    | throw { stage := "document-template", sourceModule := some name, message := "doc literals require an explicit import of ./Document.obend (any alias is allowed); no document library is supplied implicitly" }
  let edge : ObjectiveBendSurface.Import := ⟨"./Document.obend", binding, dependency.span⟩
  return { ast with imports := ast.imports ++ [edge] }

/-- A closure through elaboration, checked once (the normal typed frontend on hosted parsed
modules; original source hashes and the exact derived import transcript travel through the
existing check): everything about a package that does not
depend on the entry. Lowering an entry from it (`Prepared.lower`) selects the reached knot,
builds the proposal and the packet, nothing more. -/
structure Prepared where
  modules : List SourceModule
  asts : List ObjectiveBendSurface.Module
  decoded : List ObjectiveBendElaborate.Module
  elaborated : ObjectiveBendElaborate.Elaborated
  instances : Json

/-- An unlocated refusal that names a generic instance (`__generic_…`) lists the selected instances; a located one
names its definition and place instead, and one naming none is left as it is (obend 2026-10-14: kestrel's
`missing selected entry` carried kilobytes of instance table after the line that said what to send). -/
def instancesNote (instances : Json) (diagnostic : Diagnostic) : Diagnostic :=
  if diagnostic.span.isSome || (diagnostic.message.splitOn "__generic").length < 2 then diagnostic else
  { diagnostic with message := diagnostic.message ++
    (if instances == Json.arr #[] then "" else "; selected generic instances: " ++ instances.compress) }

/-- A generic instance's knot key to its generic declaration's module and name, from the
specialization's instance table (`declaration` is `[module, sha, sealed, name]`). -/
def originsOf (instances : Json) : Origins := fun key => do
  let items ← instances.getArr?.toOption
  let item ← items.find? fun i => (i.getObjValAs? String "name").toOption == some key
  let declaration ← (item.getObjValAs? String "declaration").toOption
  let parts ← (Json.parse declaration).toOption.bind (·.getArr?.toOption)
  let module ← (parts[0]?).bind (·.getStr?.toOption)
  let name ← (parts[3]?).bind (·.getStr?.toOption)
  return (module, name)

/-- Specialize, elaborate and check a closure whose modules are already parsed. -/
def prepareParsed (modules : List SourceModule) (asts : List ObjectiveBendSurface.Module) (limits : Json) :
    Except Diagnostic Prepared := do
  if modules.length > 64 then throw (elaborationRefusal "preview module capacity refused")
  let sources := (modules.zip asts).map fun (module, ast) => Generics.Source.mk module ast
  let specialized ← (Generics.run sources.toArray).mapError fun r =>
    { stage := "source-specialization", message := r.message, span := r.span, sourceModule := r.module }
  let note := instancesNote specialized.instances
  let origins := originsOf specialized.instances
  let elaborated ← (ObjectiveBendElaborate.elaboratePackageLocated specialized.modules).mapError
    (fun e => note (locatedRefusal origins e))
  (checkClosure modules elaborated limits origins).mapError note
  return ⟨modules, asts, specialized.modules, elaborated, specialized.instances⟩

def prepare (modules : List SourceModule) (limits : Json) : Except Diagnostic Prepared := do
  let asts ← modules.mapM fun module => do
    let ast ← parseSource module.name module.source
    checkImports module ast
    return ast
  prepareParsed modules asts limits

def Prepared.lower (p : Prepared) (entryModule : Nat) (entryDefinition : String)
    (limits : Json) : Except Diagnostic Lowering :=
  (lowerElaborated p.modules p.decoded p.elaborated true entryModule entryDefinition limits).mapError
    (instancesNote p.instances)

def lowerWithInstances (modules : List SourceModule) (entryModule : Nat) (entryDefinition : String)
    (limits : Json) : Except Diagnostic (Lowering × Json) := do
  discard <| options limits
  let prepared ← prepare modules limits
  return (← prepared.lower entryModule entryDefinition limits, prepared.instances)

def lower (modules : List SourceModule) (entryModule : Nat) (entryDefinition : String)
    (limits : Json) : Except Diagnostic Lowering := do
  return (← lowerWithInstances modules entryModule entryDefinition limits).1

end Delvetalk.FrontEnd
