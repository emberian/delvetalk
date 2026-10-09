/- Bounded rank-1 source specialization. It rewrites the parsed surface
(`Compiler.ObjectiveBendSurface`) and hands the elaborator ordinary modules: every
`f::<T>` becomes a reference to the instance `__generic_N` of a generated module,
every `Data.of::<T>(v)` the `dataOf` node, and every type text names its instances. -/
import Compiler.ObjectiveBendFrontEnd
import Delvetalk.DocumentTemplate
namespace Delvetalk.Generics
open Lean (Json toJson)
open Minidregg.Compiler
open ObjectiveBendFrontEnd
open ObjectiveBendSurface (Span Param Expr Body Signature Decl)
set_option autoImplicit false

def maxInstances : Nat := 256
/-- Surface nodes visited, over all rewriting. -/
def maxExpansionNodes : Nat := 262144
def maxExpansionStringBytes : Nat := 8388608
def maxNesting : Nat := 256

structure Source where
  module : SourceModule
  ast : ObjectiveBendSurface.Module
  deriving Inhabited

structure Declaration where
  origin : Nat
  name : String
  ast : Decl

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
  ast : Option Decl := none

structure State where
  sources : Array Source
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
  /-- The first declaration of each (module, name), as `resolve` finds it. -/
  byName : Std.HashMap (String × String) Declaration := {}
  /-- Rendered rewrites of unbound type texts, by (origin, target module, text): a
  rewrite outside any type-parameter binding is a function of these once its instances
  exist. -/
  rendered : Std.HashMap (Nat × String × String) String := {}

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
  return (← get).byName[(target, localName)]?

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

/-- `Alias.name` for a declaration of `module`, at the span of the reference it replaces. -/
def ref (module name : String) (span : Span) : M Expr := do
  let s ← get
  let alias ← if module == s.generatedModule then pure s.generatedAlias else
    match s.aliases.find? (·.2 == module) with
    | some (a, _) => pure a
    | none => throw "generic reference module missing"
  spendString alias
  spendString name
  return .member (.var alias span) name span

/-- The declaration path an unshadowed `name` or `Alias.name` reference spells. -/
def path (locals : List String) : Expr → Option String
  | .var name _ => if locals.contains name then none else some name
  | .member (.var alias _) name _ => if locals.contains alias then none else some (alias ++ "." ++ name)
  | _ => none

def trim := ObjectiveBendElaborate.trimStr
def split := ObjectiveBendElaborate.splitTop
def inner (s : String) : String := String.ofList (s.toList.drop 1 |>.dropLast)

/-- Where a rewrite happens: the declaration's own module, the module its output lands in,
the type-parameter bindings, and whether references to declarations are lifted to
qualified ones (inside an instance, which lives in the generated module). -/
structure Site where
  origin : Nat
  target : String
  bindings : List (String × GType)
  lifted : Bool

/- Rewriting visits children in the order the AST JSON's sorted keys put them (`args`
before `callee`, `inherited` before `specification`, a method's `body` before its
signature, a spec's claims, methods, requirements, then target): instances are numbered
in the order they are first met, and those numbers are in every packet. -/
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
      let .sum .. := declaration.ast | throw ("generic type is not a sum: " ++ name)
      return ← instantiate fuel declaration args
    if ["Nat", "Bool", "String", "Data", "_", "", "Self", "Super", "SpecMeta", "SpecClaims"].contains text then
      return .atom text
    let some declaration ← resolve origin text | throw ("unknown source type in specialization: " ++ text)
    if !declaration.ast.typeParameters.isEmpty then throw ("generic type needs explicit arguments: " ++ text)
    match declaration.ast with
    | .typeAlias _ type _ => return ← typeOf fuel declaration.origin [] type
    | .sum .. | .record .. =>
      return .named (← originModule declaration.origin).name declaration.name (← declarationKey declaration)
    | _ => throw ("not a source type: " ++ text)

def instantiate : Nat → Declaration → List GType → M GType
  | 0, _, _ => throw "generic instance nesting capacity"
  | fuel + 1, declaration, arguments => do
    spend
    let binders := declaration.ast.typeParameters
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
    let site : Site := ⟨declaration.origin, generated, binders.zip arguments, true⟩
    let ast ← match ← rewriteDecl fuel site [] declaration.ast with
      | .function sig _ body span => pure (Decl.function { sig with name := name } (some []) body span)
      | .sum _ cases _ span => pure (Decl.sum name cases [] span)
      | _ => throw ("declaration is not generic: " ++ declaration.name)
    modify fun s => { s with instances := s.instances.modify index (fun i => { i with ast := some ast }), active := s.active.tail }
    return .named generated name key

/-- A type text as the target module must spell it. -/
def rewriteType : Nat → Site → String → M String
  | 0, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, raw => do
    if site.bindings.isEmpty then
      if let some rendered := (← get).rendered[(site.origin, site.target, raw)]? then return rendered
    let rendered ← render site.target (← typeOf fuel site.origin site.bindings raw)
    spendString rendered
    if site.bindings.isEmpty then
      modify fun s => { s with rendered := s.rendered.insert (site.origin, site.target, raw) rendered }
    return rendered

def rewriteParam : Nat → Site → Param → M Param
  | 0, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, p => do
    spend
    spendString p.name
    spendString p.quantity
    return { p with type := ← rewriteType fuel site p.type }

def rewriteSignature : Nat → Site → Signature → M Signature
  | 0, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, s => do
    spend
    spendString s.name
    return { s with params := ← s.params.mapM (rewriteParam fuel site), resultType := ← rewriteType fuel site s.resultType }

def rewriteExpr : Nat → Site → List String → Expr → M Expr
  | 0, _, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, locals, e => do
    spend
    let recur := rewriteExpr fuel site locals
    let recurFields := fun (fs : List (String × Expr)) => fs.mapM fun (n, v) => do
      spendString n
      return (n, ← recur v)
    if let .call (.specialize target types _) args span := e then
      if path locals target == some "Data.of" && (← resolve site.origin "Data").isNone then
        let [typeArgument] := types | throw "Data.of takes exactly one type argument"
        let [value] := args | throw "Data.of takes exactly one value"
        return .dataOf (← rewriteType fuel site typeArgument) (← recur value) span
    if let .specialize target types span := e then
      let some name := path locals target | throw "generic specialization requires an unshadowed declaration"
      let some declaration ← resolve site.origin name | throw ("unknown generic declaration: " ++ name)
      let args ← types.mapM (typeOf fuel site.origin site.bindings)
      let .named module name _ ← instantiate fuel declaration args | throw "generic instance has no declaration"
      return ← ref module name span
    if let some name := path locals e then
      -- A bare import alias is not a declaration; member resolution handles it.
      let imported := (← originModule site.origin).imports.any (·.importAlias == name)
      if !imported then
        if let some declaration ← resolve site.origin name then
          if let .typeAlias _ type _ := declaration.ast then
            let .named module name _ ← typeOf fuel declaration.origin [] type
              | throw "constructor alias must name a sum"
            return ← ref module name e.span
          if !declaration.ast.typeParameters.isEmpty then throw ("generic declaration needs explicit specialization: " ++ name)
          if site.lifted then return ← ref (← originModule declaration.origin).name declaration.name e.span
    match e with
    | .var n s => do spendString n; return .var n s
    | .nat v s => do spendString v; return .nat v s
    | .bool v s => return .bool v s
    | .str v s => do spendString v; return .str v s
    | .unit s => return .unit s
    | .record fs s => return .record (← recurFields fs) s
    | .extend i fs s =>
      let fs ← recurFields fs
      return .extend (← recur i) fs s
    | .member t n s => do spendString n; return .member (← recur t) n s
    | .call c args s =>
      let args ← args.mapM recur
      return .call (← recur c) args s
    | .compose specs s => return .compose (← specs.mapM recur) s
    | .fix spec inherited s =>
      let inherited ← recur inherited
      return .fix (← recur spec) inherited s
    | .lambda ps r b s =>
      return .lambda (← ps.mapM (rewriteParam fuel site)) (← rewriteType fuel site r)
        (← rewriteExpr fuel site (ps.map (·.name) ++ locals) b) s
    | .extensionValue ps t b s =>
      return .extensionValue (← ps.mapM (rewriteParam fuel site)) (← rewriteType fuel site t)
        (← rewriteExpr fuel site (ps.map (·.name) ++ locals) b) s
    | .binary op l r s => do spendString op; return .binary op (← recur l) (← recur r) s
    | .ite c t f s =>
      let c ← recur c
      let f ← recur f
      return .ite c (← recur t) f s
    | .letE n t v b s =>
      let value ← recur v
      let body ← rewriteExpr fuel site (n :: locals) b
      return .letE n (← rewriteType fuel site t) value body s
    | .specialize .. | .dataOf .. => return e

def rewriteBody : Nat → Site → List String → Body → M Body
  | 0, _, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, locals, b => do
    spend
    match b with
    | .expr e s => return .expr (← rewriteExpr fuel site locals e) s
    | .cases scrutinee branches s =>
      let scrutinee ← rewriteExpr fuel site locals scrutinee
      let branches ← branches.mapM fun (pattern, body, span) => do
        return (pattern, ← rewriteBody fuel site (pattern.binder :: locals) body, span)
      return .cases scrutinee branches s
    | .letB n t v rest s =>
      let value ← rewriteExpr fuel site locals v
      let rest ← rewriteBody fuel site (n :: locals) rest
      return .letB n (← rewriteType fuel site t) value rest s

def rewriteDecl : Nat → Site → List String → Decl → M Decl
  | 0, _, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, locals, d => do
    spend
    spendString d.name
    match d with
    | .reexport name target span =>
      if let some declaration ← resolve site.origin target then
        if !declaration.ast.typeParameters.isEmpty then
          throw ("unspecialized generic export is unsupported: " ++ target ++ " in " ++ (← originModule site.origin).name ++
            " at " ++ span.json.compress ++ "; export an ordinary checked definition")
      spendString target
      return .reexport name target span
    | .function sig typeParameters body span =>
      let sig ← rewriteSignature fuel site sig
      return .function sig typeParameters (← rewriteBody fuel site (sig.params.map (·.name) ++ locals) body) span
    | .extension name ps t body binders span =>
      let ps ← ps.mapM (rewriteParam fuel site)
      let t ← rewriteType fuel site t
      return .extension name ps t (← rewriteBody fuel site (ps.map (·.name) ++ locals) body) binders span
    | .spec sp =>
      let locals := ["self", "super"] ++ locals
      let claims ← sp.claims.mapM fun c => do
        let body ← rewriteExpr fuel site (c.params.map (·.name) ++ locals) c.body
        return { c with body, params := ← c.params.mapM (rewriteParam fuel site) }
      let methods ← sp.methods.mapM fun m => do
        let body ← rewriteBody fuel site (m.signature.params.map (·.name) ++ locals) m.body
        return { m with body, signature := ← rewriteSignature fuel site m.signature }
      let requirements ← sp.requirements.mapM (rewriteSignature fuel site)
      let targetType ← rewriteType fuel site sp.targetType
      return .spec { sp with targetType, requirements, methods, claims }
    | .record name methods fields span =>
      let fields ← fields.mapM fun f => do return { f with type := ← rewriteType fuel site f.type }
      let methods ← methods.mapM (rewriteSignature fuel site)
      return .record name methods fields span
    | .sum name cases typeParameters span =>
      let cases ← cases.mapM fun c => do return { c with type := ← rewriteType fuel site c.type }
      return .sum name cases typeParameters span
    | .law .. | .typeAlias .. => return d
end

structure Output where
  modules : List ObjectiveBendElaborate.Module
  instances : Json

/-! ## Whether a module needs the pass at all -/

mutual
def exprGenerics : Expr → Bool
  | .specialize .. => true
  | .var .. | .nat .. | .bool .. | .str .. | .unit .. => false
  | .record fs _ => fieldsHaveGenerics fs
  | .extend i fs _ => (exprGenerics i) || fieldsHaveGenerics fs
  | .member t _ _ => (exprGenerics t)
  | .call c args _ => (exprGenerics c) || listHasGenerics args
  | .compose specs _ => listHasGenerics specs
  | .fix spec inherited _ => (exprGenerics spec) || (exprGenerics inherited)
  | .lambda _ _ b _ | .extensionValue _ _ b _ => (exprGenerics b)
  | .binary _ l r _ => (exprGenerics l) || (exprGenerics r)
  | .ite c t f _ => (exprGenerics c) || (exprGenerics t) || (exprGenerics f)
  | .letE _ _ v b _ => (exprGenerics v) || (exprGenerics b)
  | .dataOf _ v _ => (exprGenerics v)
def fieldsHaveGenerics : List (String × Expr) → Bool
  | [] => false
  | (_, v) :: rest => (exprGenerics v) || fieldsHaveGenerics rest
def listHasGenerics : List Expr → Bool
  | [] => false
  | e :: rest => (exprGenerics e) || listHasGenerics rest
end

mutual
def bodyGenerics : Body → Bool
  | .expr e _ => (exprGenerics e)
  | .cases sc branches _ => (exprGenerics sc) || branchesHaveGenerics branches
  | .letB _ _ v b _ => (exprGenerics v) || (bodyGenerics b)
def branchesHaveGenerics : List (ObjectiveBendSurface.Pattern × Body × Span) → Bool
  | [] => false
  | (_, b, _) :: rest => (bodyGenerics b) || branchesHaveGenerics rest
end

/-- A specialization anywhere, a type alias, or a declaration with type parameters. -/
def declGenerics (d : Decl) : Bool :=
  !d.typeParameters.isEmpty ||
  match d with
  | .typeAlias .. => true
  | .function _ _ b _ | .extension _ _ _ b _ _ => (bodyGenerics b)
  | .spec sp => sp.methods.any (fun m => bodyGenerics m.body) || sp.claims.any (fun c => exprGenerics c.body)
  | _ => false

/-! ## The names a fresh `__generic_N` must avoid

Every identifier-shaped run of the module's strings as JSON prints them (so a run never
crosses a string, and an escape's letters join the run they touch), restricted to the
strings that could hold a `__generic_` run at all. -/

def candidate (s : String) : Bool := (s.splitOn "__generic_").length > 1

def addNames (names : Std.TreeSet String) (s : String) : Std.TreeSet String :=
  if candidate s then
    (DocumentTemplate.identifiers (toJson s).compress).foldl (fun acc n => acc.insert n) names
  else names

mutual
def exprStrings : Expr → List String
  | .var n _ | .nat n _ | .str n _ => [n]
  | .bool .. | .unit .. => []
  | .record fs _ => fieldStrings fs
  | .extend i fs _ => (exprStrings i) ++ fieldStrings fs
  | .member t n _ => n :: (exprStrings t)
  | .call c args _ => (exprStrings c) ++ listStrings args
  | .compose specs _ => listStrings specs
  | .fix spec inherited _ => (exprStrings spec) ++ (exprStrings inherited)
  | .lambda ps t b _ | .extensionValue ps t b _ => paramStrings ps ++ [t] ++ (exprStrings b)
  | .binary op l r _ => op :: (exprStrings l) ++ (exprStrings r)
  | .ite c t f _ => (exprStrings c) ++ (exprStrings t) ++ (exprStrings f)
  | .letE n t v b _ => n :: t :: (exprStrings v) ++ (exprStrings b)
  | .specialize t types _ => (exprStrings t) ++ types
  | .dataOf t v _ => t :: (exprStrings v)
def fieldStrings : List (String × Expr) → List String
  | [] => []
  | (n, v) :: rest => n :: (exprStrings v) ++ fieldStrings rest
def listStrings : List Expr → List String
  | [] => []
  | e :: rest => (exprStrings e) ++ listStrings rest
def paramStrings : List Param → List String
  | [] => []
  | p :: rest => p.name :: p.type :: p.quantity :: paramStrings rest
end

mutual
def bodyStrings : Body → List String
  | .expr e _ => (exprStrings e)
  | .cases sc branches _ => (exprStrings sc) ++ branchStrings branches
  | .letB n t v b _ => n :: t :: (exprStrings v) ++ (bodyStrings b)
def branchStrings : List (ObjectiveBendSurface.Pattern × Body × Span) → List String
  | [] => []
  | (p, b, _) :: rest =>
    (match p with | .ctor l binder => [l, binder] | .succ binder => [binder] | _ => []) ++
      (bodyStrings b) ++ branchStrings rest
end

def signatureStrings (s : Signature) : List String := s.name :: s.resultType :: paramStrings s.params

def declStrings : Decl → List String
  | .reexport n t _ => [n, t]
  | .spec sp => [sp.name, sp.targetType] ++ sp.parents ++ sp.binders.toList ++
      sp.requirements.flatMap signatureStrings ++
      sp.methods.flatMap (fun m => m.qualifier :: signatureStrings m.signature ++ bodyStrings m.body) ++
      sp.claims.flatMap (fun c => c.name :: paramStrings c.params ++ exprStrings c.body)
  | .extension n ps t b binders _ => n :: t :: paramStrings ps ++ binders.toList ++ (bodyStrings b)
  | .typeAlias n t _ => [n, t]
  | .sum n cases ps _ => n :: ps ++ cases.flatMap (fun c => [c.name, c.type])
  | .record n methods fields _ => n :: methods.flatMap signatureStrings ++ fields.flatMap (fun f => [f.name, f.type])
  | .law n source _ => [n, source]
  | .function sig ps b _ => signatureStrings sig ++ ps.getD [] ++ (bodyStrings b)

def moduleNames (m : ObjectiveBendSurface.Module) (names : Std.TreeSet String) : Std.TreeSet String :=
  let names := m.imports.foldl (fun acc i => addNames (addNames acc i.path) i.importAlias) names
  m.decls.foldl (fun acc d => (declStrings d).foldl addNames acc) names

/-! ## The pass -/

def run (sources : Array Source) : Except String Output := do
  if !sources.any (fun s => s.ast.decls.any declGenerics) then
    let modules ← sources.toList.mapM fun source =>
      ObjectiveBendElaborate.ofSurface source.module.name source.module.aliases source.ast
    return ⟨modules, Json.arr #[]⟩
  let mut declarations : Array Declaration := #[]
  let mut names : Std.TreeSet String := {}
  for source in sources do
    names := moduleNames source.ast names
    names := names.insert source.module.name
  for index in [:sources.size] do
    for d in sources[index]!.ast.decls do
      declarations := declarations.push ⟨index, d.name, d⟩
  let mut sealedIdentities : Array String := #[]
  for source in sources do
    let imports ← source.module.imports.mapM fun edge => do
      let some identity := sealedIdentities[edge.target]? | throw "generic import must target an earlier sealed module"
      return toJson [edge.moduleName, edge.sha256, identity]
    sealedIdentities := sealedIdentities.push (Minidregg.Compiler.Sha256.hexString
      (toJson [toJson source.module.name, toJson source.module.sha256, toJson imports]).compress)
  let byName := declarations.foldl (fun (map : Std.HashMap (String × String) Declaration) d =>
    match sources[d.origin]? with
    | some source => if map.contains (source.module.name, d.name) then map else map.insert (source.module.name, d.name) d
    | none => map) {}
  let initial : State := { sources, sealedIdentities, generatedModule := "", generatedAlias := "", aliases := [], names, byName }
  let action : M Output := do
    let moduleName ← fresh
    let moduleAlias ← fresh
    let mut aliases := []
    for source in sources do aliases := aliases ++ [(← fresh, source.module.name)]
    modify fun s => { s with generatedModule := moduleName, generatedAlias := moduleAlias, aliases }
    let mut rewritten : List (String × ObjectiveBendSurface.Module) := []
    for index in [:sources.size] do
      let source := sources[index]!
      let site : Site := ⟨index, source.module.name, [], false⟩
      let mut ordinary : Array Decl := #[]
      for d in source.ast.decls do
        if (d matches .typeAlias ..) || !d.typeParameters.isEmpty then continue
        ordinary := ordinary.push (← rewriteDecl maxNesting site [] d)
      rewritten := rewritten ++ [(source.module.name, { source.ast with decls := ordinary.toList })]
    let state ← get
    let generated : ObjectiveBendSurface.Module := ⟨[], state.instances.toList.filterMap (·.ast)⟩
    rewritten := rewritten ++ [(moduleName, generated)]
    let mut decoded := []
    for (name, ast) in rewritten do
      let own := (sources.find? (·.module.name == name)).map (·.module.aliases) |>.getD []
      let imports := own ++ aliases ++ [(moduleAlias, moduleName)]
      decoded := decoded ++ [← ObjectiveBendElaborate.ofSurface name imports ast]
    let instances := toJson (state.instances.toList.map fun i => Json.mkObj [
      ("declaration", toJson i.declaration), ("arguments", toJson (i.arguments.map GType.identity)),
      ("name", toJson (moduleName ++ "." ++ i.name)), ("span", (i.ast.map (·.span.json)).getD .null)])
    return ⟨decoded, instances⟩
  return (← action.run initial).1

end Delvetalk.Generics
