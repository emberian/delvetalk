/- Hosted syntax belongs above the local core parser and typed frontend. This layer
adds only document literal expansion and a hygienic import of the already
selected Document dependency; checking and evaluation remain ordinary Bend. -/
import Compiler.ObjectiveBendFrontEnd
import Delvetalk.DocumentTemplate

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

/-- The normal typed frontend on hosted parsed modules. Original source hashes
and the exact derived import transcript travel through the existing check. -/
def lower (modules : List SourceModule) (entryModule : Nat) (entryDefinition : String)
    (args projections limits : Json) (mode : String) : Except Diagnostic Lowering := do
  discard <| options projections limits mode
  let decoded ← modules.mapM fun module => do
    checkParsed module (← parseSource module.name module.source)
  lowerDecoded modules decoded entryModule entryDefinition args projections limits mode

end Delvetalk.FrontEnd
