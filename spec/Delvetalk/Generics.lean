/- Bounded rank-1 source specialization. Its output contains only the ordinary
module AST consumed by the existing elaborator and proof-producing checker. -/
import Compiler.ObjectiveBendFrontEnd
import Delvetalk.DocumentTemplate
namespace Delvetalk.Generics
open Lean
open Minidregg.Compiler
open ObjectiveBendFrontEnd
set_option autoImplicit false

def maxInstances : Nat := 256
def maxExpansionNodes : Nat := 262144
def maxExpansionStringBytes : Nat := 8388608
def maxNesting : Nat := 256

def field (j : Json) (key : String) : Json := (j.getObjVal? key).toOption.getD .null
def string (j : Json) (key : String) : String := (j.getObjValAs? String key).toOption.getD ""
def array (j : Json) (key : String) : Array Json := ((j.getObjVal? key).bind Json.getArr?).toOption.getD #[]
def setField (j : Json) (key : String) (value : Json) : Json :=
  let entries := (j.getObj?).toOption.map (·.toList) |>.getD []
  Json.mkObj ((entries.filter (fun p => p.1 != key)) ++ [(key, value)])
def kind (j : Json) : String := string j "kind"
def declName (j : Json) : String :=
  if kind j == "function" then string (field j "signature") "name" else string j "name"
def parameters (j : Json) : List String := (array j "typeParameters").toList.filterMap (·.getStr?.toOption)

structure Source where
  module : SourceModule
  ast : Json
  deriving Inhabited

structure Declaration where
  origin : Nat
  name : String
  ast : Json

inductive GType where
  | atom (name : String)
  | named (module name identity : String)
  | applied (name : String) (args : List GType)
  | arrow (domain codomain : GType)
  | row (fields : List (String × GType))
  | overlay (base fields : GType)
  deriving Inhabited, BEq

partial def GType.identity : GType → Json
  | .atom n => toJson ["atom", n]
  | .named _ _ identity => toJson ["named", identity]
  | .applied n args => Json.mkObj [("builtin", toJson n), ("arguments", toJson (args.map GType.identity))]
  | .arrow a b => toJson [a.identity, b.identity]
  | .row fields => Json.mkObj [("row", toJson (fields.map fun (n, t) => toJson [toJson n, t.identity]))]
  | .overlay a b => Json.mkObj [("overlay", toJson [a.identity, b.identity])]

partial def GType.isClosed : GType → Bool
  | .atom n => n != "Self" && n != "Super"
  | .named _ _ _ => true
  | .applied _ args => args.all GType.isClosed
  | .arrow a b => a.isClosed && b.isClosed
  | .row fields => fields.all (fun p => p.2.isClosed)
  | .overlay a b => a.isClosed && b.isClosed

structure Instance where
  key : String
  declaration : String
  name : String
  origin : Nat
  arguments : List GType
  ast : Json := .null

structure State where
  sources : Array Source
  declarations : List Declaration
  sealedIdentities : Array String
  generatedModule : String
  generatedAlias : String
  aliases : List (String × String)
  names : Std.TreeSet String
  nextName : Nat := 0
  instances : Array Instance := #[]
  active : List (String × String) := []
  remaining : Nat := maxExpansionNodes
  remainingStringBytes : Nat := maxExpansionStringBytes

abbrev M := StateT State (Except String)

def spend : M Unit := do
  let s ← get
  if s.remaining == 0 then throw "generic specialization exceeds expanded AST node budget"
  set { s with remaining := s.remaining - 1 }

def spendString (text : String) : M Unit := do
  let s ← get
  let bytes := text.utf8ByteSize
  if bytes > s.remainingStringBytes then throw "generic specialization exceeds expanded string byte budget"
  set { s with remainingStringBytes := s.remainingStringBytes - bytes }

def fresh : M String := do
  let s ← get
  let mut index := s.nextName
  for _ in [0:s.names.size + 1] do
    let name := "__generic_" ++ toString index
    index := index + 1
    if !s.names.contains name then
      set { s with names := s.names.insert name, nextName := index }
      return name
  throw "generic name capacity"

def originModule (origin : Nat) : M SourceModule := do
  let some source := (← get).sources[origin]? | throw "generic source module missing"
  return source.module

def declarationKey (d : Declaration) : M String := do
  let m ← originModule d.origin
  let some sealedIdentity := (← get).sealedIdentities[d.origin]? | throw "generic sealed module identity missing"
  return (toJson [m.name, m.sha256, sealedIdentity, d.name]).compress

def resolve (origin : Nat) (name : String) : M (Option Declaration) := do
  let m ← originModule origin
  let (target, localName) ← match name.splitOn "." with
    | [n] => pure (m.name, n)
    | [alias, n] =>
      let some imported := m.imports.find? (·.importAlias == alias)
        | return none
      pure (imported.moduleName, n)
    | _ => throw ("invalid generic declaration reference: " ++ name)
  let s ← get
  return s.declarations.find? fun d =>
    d.name == localName && ((s.sources[d.origin]?).map (·.module.name)) == some target

partial def render (target : String) : GType → M String
  | .atom n => pure n
  | .named m n _ => do
    if m == target then return n
    let s ← get
    if m == s.generatedModule then return s.generatedAlias ++ "." ++ n
    let some (alias, _) := s.aliases.find? (·.2 == m) | throw "generic type module missing"
    return alias ++ "." ++ n
  | .applied n args => do return n ++ "<" ++ String.intercalate ", " (← args.mapM (render target)) ++ ">"
  | .arrow a b => do return "(" ++ (← render target a) ++ ") -> " ++ (← render target b)
  | .row fields => do
    let fields ← fields.mapM fun (n, t) => do return n ++ ": " ++ (← render target t)
    return "{" ++ String.intercalate ", " fields ++ "}"
  | .overlay a b => do return (← render target a) ++ " with " ++ (← render target b)

def ref (module name : String) (original : Json) : M Json := do
  let s ← get
  let alias ← if module == s.generatedModule then pure s.generatedAlias else
    match s.aliases.find? (·.2 == module) with
    | some (a, _) => pure a
    | none => throw "generic reference module missing"
  spendString alias
  spendString name
  return Json.mkObj [("kind", toJson "member"),
    ("target", Json.mkObj [("kind", toJson "var"), ("name", toJson alias), ("span", field original "span")]),
    ("name", toJson name), ("span", field original "span")]

def path (locals : List String) (j : Json) : Option String := do
  if kind j == "var" then
    let name := string j "name"
    if locals.contains name then none else some name
  else if kind j == "member" && kind (field j "target") == "var" then
    let alias := string (field j "target") "name"
    if locals.contains alias then none else some (alias ++ "." ++ string j "name")
  else none

def trim := ObjectiveBendElaborate.trimStr
def split := ObjectiveBendElaborate.splitTop
def inner (s : String) : String := String.ofList (s.toList.drop 1 |>.dropLast)

mutual
def typeOf : Nat → Nat → List (String × GType) → String → M GType
  | 0, _, _, _ => throw "generic type nesting capacity"
  | fuel + 1, origin, bindings, raw => do
    spend
    let text := trim raw
    if let some type := bindings.lookup text then return type
    let arrows := split text "->"
    if arrows.length > 1 then
      let domain ← typeOf fuel origin bindings arrows.head!
      let codomain ← typeOf fuel origin bindings (String.intercalate "->" arrows.tail)
      return .arrow domain codomain
    if text.startsWith "(" && text.endsWith ")" then return ← typeOf fuel origin bindings (inner text)
    if let [base, fields] := split text " with " then
      return .overlay (← typeOf fuel origin bindings base) (← typeOf fuel origin bindings fields)
    if text.startsWith "{" && text.endsWith "}" then
      let contents := trim (inner text)
      if contents.isEmpty then return .row []
      let fields ← (split contents ",").mapM fun f => do
        let arrows := split f "->"
        let head := trim (arrows.headD "")
        if arrows.length > 1 && head.endsWith ")" && (head.splitOn "(").length > 1 then
          let name := trim ((head.splitOn "(").headD "")
          if ObjectiveBendParse.isIdent name.toList then
            let paramsText := String.ofList (head.toList.drop (name.length + 1) |>.dropLast)
            let mut result ← typeOf fuel origin bindings (String.intercalate "->" arrows.tail)
            for parameter in (if (trim paramsText).isEmpty then [] else split paramsText ",").reverse do
              let parts := split parameter ":"
              if parts.length < 2 then throw ("generic method row parameter needs a type: " ++ parameter)
              result := .arrow (← typeOf fuel origin bindings (String.intercalate ":" parts.tail)) result
            return (name, result)
        let parts := split f ":"
        if parts.length < 2 then throw ("generic type row requires field: GType: " ++ f)
        return (trim parts.head!, ← typeOf fuel origin bindings (String.intercalate ":" parts.tail))
      return .row fields
    if text.endsWith ">" && (text.splitOn "<").length > 1 then
      let name := trim (text.splitOn "<").head!
      let argsText := String.ofList (text.toList.drop (name.length + 1) |>.dropLast)
      let args ← (split argsText ",").mapM (typeOf fuel origin bindings)
      if ["Prototype", "Extension", "Specification", "Activity"].contains name then return .applied name args
      let some declaration ← resolve origin name | throw ("unknown generic type " ++ name)
      if kind declaration.ast != "sum" then throw ("generic type is not a sum: " ++ name)
      return ← instantiate fuel declaration args
    if ["Nat", "Bool", "String", "_", "", "Self", "Super", "SpecMeta", "SpecClaims"].contains text then
      return .atom text
    let some declaration ← resolve origin text | throw ("unknown source type in specialization: " ++ text)
    if !(parameters declaration.ast).isEmpty then throw ("generic type needs explicit arguments: " ++ text)
    if kind declaration.ast == "typeAlias" then
      return ← typeOf fuel declaration.origin [] (string declaration.ast "type")
    if kind declaration.ast != "sum" && kind declaration.ast != "record" then throw ("not a source type: " ++ text)
    return .named (← originModule declaration.origin).name declaration.name (← declarationKey declaration)

def instantiate : Nat → Declaration → List GType → M GType
  | 0, _, _ => throw "generic instance nesting capacity"
  | fuel + 1, declaration, arguments => do
    spend
    let binders := parameters declaration.ast
    if binders.isEmpty then throw ("declaration is not generic: " ++ declaration.name)
    if binders.length != arguments.length then throw ("generic type arity: " ++ declaration.name)
    let declarationId ← declarationKey declaration
    spendString declarationId
    if arguments.any (fun t => !t.isClosed) then
      throw ("generic specialization cannot lift open Self/Super type arguments: " ++ declaration.name)
    let argumentIdentity := (toJson (arguments.map GType.identity)).compress
    spendString argumentIdentity
    let argumentId := Minidregg.Compiler.Sha256.hexString argumentIdentity
    let key := Minidregg.Compiler.Sha256.hexString (toJson [declarationId, argumentId]).compress
    let state ← get
    if state.active.any (fun p => p.1 == declarationId && p.2 != argumentId) then
      throw ("generic recursion changes type arguments: " ++ declaration.name)
    if let some priorInstance := state.instances.find? (·.key == key) then return .named state.generatedModule priorInstance.name priorInstance.key
    if state.instances.size >= maxInstances then throw "generic specialization exceeds instance budget"
    let name ← fresh
    let index := (← get).instances.size
    modify fun s => { s with
      instances := s.instances.push {
        key := key
        declaration := declarationId
        name := name
        origin := declaration.origin
        arguments := arguments }
      active := (declarationId, argumentId) :: s.active }
    let generated := (← get).generatedModule
    let ast ← rewrite fuel declaration.origin generated (binders.zip arguments) [] true declaration.ast
    let ast := if kind ast == "function" then
        setField ast "signature" (setField (field ast "signature") "name" (toJson name))
      else setField ast "name" (toJson name)
    let ast := setField ast "typeParameters" (toJson ([] : List String))
    modify fun s => { s with instances := s.instances.modify index (fun i => { i with ast := ast }), active := s.active.tail }
    return .named generated name key

def rewrite : Nat → Nat → String → List (String × GType) → List String → Bool → Json → M Json
  | 0, _, _, _, _, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, origin, target, bindings, locals, lifted, j => do
    spend
    let parameterNames := (array j "parameters").toList.map (fun parameter => string parameter "name")
    if let .str text := j then spendString text
    let implicitNames := if kind j == "spec" then ["self", "super"] else []
    let recur := rewrite fuel origin target bindings (parameterNames ++ implicitNames ++ locals) lifted
    let rewriteType := fun raw => do
      let rendered ← render target (← typeOf fuel origin bindings raw)
      spendString rendered
      return rendered
    if kind j == "specialize" then
      let some name := path locals (field j "target") | throw "generic specialization requires an unshadowed declaration"
      let some declaration ← resolve origin name | throw ("unknown generic declaration: " ++ name)
      let args ← (array j "types").toList.mapM fun arg => do
        let text ← arg.getStr?
        typeOf fuel origin bindings text
      let .named module name _ ← instantiate fuel declaration args | throw "generic instance has no declaration"
      return ← ref module name j
    if kind j == "var" || kind j == "member" then
      if let some name := path locals j then
        -- A bare import alias is not a declaration; member resolution handles it.
        let imported := (← originModule origin).imports.any (·.importAlias == name)
        if !imported then
          if let some declaration ← resolve origin name then
            if kind declaration.ast == "typeAlias" then
              let .named module name _ ← typeOf fuel declaration.origin [] (string declaration.ast "type")
                | throw "constructor alias must name a sum"
              return ← ref module name j
            if !(parameters declaration.ast).isEmpty then throw ("generic declaration needs explicit specialization: " ++ name)
            if lifted then return ← ref (← originModule declaration.origin).name declaration.name j
    if kind j == "lambda" || kind j == "extension-value" || kind j == "function" || kind j == "extension" then
      let signature := if kind j == "function" then field j "signature" else j
      let params := array signature "parameters"
      let names := params.toList.map (fun p => string p "name")
      let changed ← params.mapM recur
      let resultKey := if kind j == "extension" || kind j == "extension-value" then "targetType" else "resultType"
      let signature := setField (setField signature "parameters" (Json.arr changed)) resultKey
        (toJson (← rewriteType (string signature resultKey)))
      let body ← rewrite fuel origin target bindings (names ++ locals) lifted (field j "body")
      if kind j == "function" then return setField (setField j "signature" signature) "body" body
      return setField signature "body" body
    if kind j == "let" then
      let value ← recur (field j "value")
      let body ← rewrite fuel origin target bindings (string j "name" :: locals) lifted (field j "body")
      return setField (setField (setField j "value" value) "body" body) "type" (toJson (← rewriteType (string j "type")))
    if kind j == "match" then
      let scrutinee ← recur (field j "scrutinee")
      let branches ← (array j "branches").mapM fun branch => do
        let binder := string (field branch "pattern") "binder"
        let body ← rewrite fuel origin target bindings (binder :: locals) lifted (field branch "body")
        return setField branch "body" body
      return setField (setField j "scrutinee" scrutinee) "branches" (Json.arr branches)
    match j with
    | .arr xs => return Json.arr (← xs.mapM recur)
    | .obj fields =>
      let fields ← fields.toList.mapM fun (name, value) => do
        if ["type", "resultType", "targetType"].contains name then
          if let .str raw := value then return (name, toJson (← rewriteType raw))
        return (name, ← recur value)
      return Json.mkObj fields
    | _ => return j
end

structure Output where
  modules : List ObjectiveBendElaborate.Module
  instances : Json

def hasGenerics : Nat → Json → Bool
  | 0, _ => false
  | fuel + 1, .obj fields =>
    let j := Json.obj fields
    kind j == "specialize" || kind j == "typeAlias" || !(parameters j).isEmpty ||
      fields.toList.any (fun p => hasGenerics fuel p.2)
  | fuel + 1, .arr xs => xs.any (hasGenerics fuel)
  | _, _ => false

def run (sources : Array Source) : Except String Output := do
  if !sources.any (fun s => hasGenerics maxNesting s.ast) then
    let modules ← sources.toList.mapM fun source =>
      ObjectiveBendElaborate.decodeModule (Json.mkObj [("name", toJson source.module.name), ("ast", source.ast),
        ("imports", toJson (source.module.imports.map fun i =>
          Json.mkObj [("alias", toJson i.importAlias), ("moduleName", toJson i.moduleName)]))])
    return ⟨modules, Json.arr #[]⟩
  let mut declarations := []
  let mut names : Std.TreeSet String := {}
  for source in sources do
    for name in (DocumentTemplate.identifiers source.ast.compress).toList do names := names.insert name
    names := names.insert source.module.name
  for index in [:sources.size] do
    for ast in array sources[index]!.ast "declarations" do
      declarations := declarations ++ [⟨index, declName ast, ast⟩]
  let mut sealedIdentities : Array String := #[]
  for source in sources do
    let imports ← source.module.imports.mapM fun edge => do
      let some identity := sealedIdentities[edge.target]? | throw "generic import must target an earlier sealed module"
      return toJson [edge.moduleName, edge.sha256, identity]
    sealedIdentities := sealedIdentities.push (Minidregg.Compiler.Sha256.hexString
      (toJson [toJson source.module.name, toJson source.module.sha256, toJson imports]).compress)
  let initial : State := { sources, declarations, sealedIdentities, generatedModule := "", generatedAlias := "", aliases := [], names }
  let action : M Output := do
    let moduleName ← fresh
    let moduleAlias ← fresh
    let mut aliases := []
    for source in sources do aliases := aliases ++ [(← fresh, source.module.name)]
    modify fun s => { s with generatedModule := moduleName, generatedAlias := moduleAlias, aliases }
    let mut rewritten : List (String × Json) := []
    for index in [:sources.size] do
      let source := sources[index]!
      let mut ordinary : Array Json := #[]
      for ast in array source.ast "declarations" do
        if kind ast == "typeAlias" || !(parameters ast).isEmpty then continue
        ordinary := ordinary.push (← rewrite maxNesting index source.module.name [] [] false ast)
      rewritten := rewritten ++ [(source.module.name, setField source.ast "declarations" (Json.arr ordinary))]
    let state ← get
    let generated := Json.mkObj [("declarations", Json.arr (state.instances.map (·.ast)))]
    rewritten := rewritten ++ [(moduleName, generated)]
    let mut decoded := []
    for (name, ast) in rewritten do
      let own := (sources.find? (·.module.name == name)).map (·.module.imports) |>.getD []
      let imports := own.map (fun i => (i.importAlias, i.moduleName)) ++ aliases ++ [(moduleAlias, moduleName)]
      let module ← ObjectiveBendElaborate.decodeModule (Json.mkObj [("name", toJson name), ("ast", ast),
        ("imports", toJson (imports.map fun (alias, target) => Json.mkObj [("alias", toJson alias), ("moduleName", toJson target)]))])
      decoded := decoded ++ [module]
    let instances := toJson (state.instances.toList.map fun i => Json.mkObj [
      ("declaration", toJson i.declaration), ("arguments", toJson (i.arguments.map GType.identity)),
      ("name", toJson (moduleName ++ "." ++ i.name)), ("span", field i.ast "span")])
    return ⟨decoded, instances⟩
  return (← action.run initial).1

end Delvetalk.Generics
