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
/-- Steps of type-argument inference (type resolution and synthesis), over the whole pass.
Separate from the node budget, so a module that infers nothing is refused exactly as before. -/
def maxInferenceSteps : Nat := 4194304

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
  /-- The generic declaration's own name (in the module `origin` names). -/
  declarationName : String
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
  /-- The instance of each (declaration key, argument identity) met so far. -/
  instanceOf : Std.HashMap (String × String) Nat := {}
  /-- Declaration keys, by (origin, name). -/
  declarationKeys : Std.HashMap (Nat × String) String := {}
  /-- Instances being rewritten: (declaration key, argument identity). -/
  active : List (String × String) := []
  remaining : Nat := maxExpansionNodes
  remainingStringBytes : Nat := maxExpansionStringBytes
  /-- The first declaration of each (module, name), as `resolve` finds it. -/
  byName : Std.HashMap (String × String) Declaration := {}
  /-- Rendered rewrites of unbound type texts, by (origin, target module, text): a
  rewrite outside any type-parameter binding is a function of these once its instances
  exist. -/
  rendered : Std.HashMap (Nat × String × String) String := {}
  /-- Instances by their fresh name. -/
  instanceByName : Std.HashMap String Nat := {}
  inferRemaining : Nat := maxInferenceSteps

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
  if let some key := (← get).declarationKeys[(d.origin, d.name)]? then return key
  let m ← originModule d.origin
  let some sealedIdentity := (← get).sealedIdentities[d.origin]? | throw "generic sealed module identity missing"
  let key := (toJson [m.name, m.sha256, sealedIdentity, d.name]).compress
  modify fun s => { s with declarationKeys := s.declarationKeys.insert (d.origin, d.name) key }
  return key

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

/-! ## Type-argument inference

A call of a generic definition or constructor written without `::<...>` is given the
type arguments its explicit spelling would name, read off the arguments' types and the
type the call's position expects (rank 1: every type parameter is a whole type). The
pass then rewrites the call exactly as it rewrites the explicit spelling: arguments
first, then the instance (its type arguments instantiated left to right, nested
instances first, as `typeOf` instantiates a type text), so instance numbers and the
packet are those of the explicit spelling.

Inference never instantiates: a generic sum met while resolving or synthesizing a type
stays an application (`IType.app`) until the call's own arguments are fixed. -/

/-- A type during inference. `param` is a type parameter of the callee being inferred;
`lit` is the row of a record literal (weaker evidence than a declared type: a literal
binds a parameter only when nothing declared does); `unknown` is what synthesis could
not tell. -/
inductive IType where
  | ground (type : GType)
  | param (name : String)
  /-- A generic sum applied: its origin, name and declaration key. -/
  | app (origin : Nat) (name key : String) (args : List IType)
  | arrow (domain codomain : IType)
  | row (fields : List (String × IType))
  | lit (fields : List (String × IType))
  | applied (name : String) (args : List IType)
  | unknown
  deriving Inhabited

/-- Fully known (no `unknown`, no `param`), and whether a literal row occurs. -/
partial def IType.complete : IType → Bool
  | .ground _ => true
  | .param _ | .unknown => false
  | .app _ _ _ args | .applied _ args => args.all IType.complete
  | .arrow a b => a.complete && b.complete
  | .row fs | .lit fs => fs.all (·.2.complete)

partial def IType.weak : IType → Bool
  | .lit _ => true
  | .app _ _ _ args | .applied _ args => args.any IType.weak
  | .arrow a b => a.weak || b.weak
  | .row fs => fs.any (·.2.weak)
  | _ => false

partial def IType.subst (σ : List (String × IType)) : IType → IType
  | .param p => (σ.lookup p).getD .unknown
  | .app o n k args => .app o n k (args.map (IType.subst σ))
  | .applied n args => .applied n (args.map (IType.subst σ))
  | .arrow a b => .arrow (a.subst σ) (b.subst σ)
  | .row fs => .row (fs.map fun (n, t) => (n, t.subst σ))
  | .lit fs => .lit (fs.map fun (n, t) => (n, t.subst σ))
  | t => t

/-- The type as a reader would write it (for refusals only). -/
partial def IType.show : IType → String
  | .ground (.atom n) => n
  | .ground (.named _ n _) => n
  | .ground (.applied n args) => n ++ "<" ++ ", ".intercalate (args.map fun g => (IType.ground g).show) ++ ">"
  | .ground (.arrow a b) => (IType.ground a).show ++ " -> " ++ (IType.ground b).show
  | .ground (.row fs) => "{" ++ ", ".intercalate (fs.map fun (n, t) => n ++ ": " ++ (IType.ground t).show) ++ "}"
  | .ground (.overlay a b) => (IType.ground a).show ++ " with " ++ (IType.ground b).show
  | .param p => p
  | .app _ n _ args | .applied n args => n ++ "<" ++ ", ".intercalate (args.map IType.show) ++ ">"
  | .arrow a b => a.show ++ " -> " ++ b.show
  | .row fs | .lit fs => "{" ++ ", ".intercalate (fs.map fun (n, t) => n ++ ": " ++ t.show) ++ "}"
  | .unknown => "_"

/-- The result an activity type finishes with; any other type is itself. -/
def IType.value : IType → IType
  | .applied "Activity" [_, _, a] => a
  | t => t

/-- Where a rewrite happens: the declaration's own module, the module its output lands in,
the type-parameter bindings, and whether references to declarations are lifted to
qualified ones (inside an instance, which lives in the generated module). -/
structure Site where
  origin : Nat
  target : String
  bindings : List (String × GType)
  lifted : Bool
  /-- The declared result type of the definition being rewritten (for `perform`). -/
  result : M IType := pure .unknown

def spendInfer : M Unit := do
  let s ← get
  if s.inferRemaining == 0 then throw "type-argument inference exceeds its step budget"
  set { s with inferRemaining := s.inferRemaining - 1 }

/-- `resolve`, with an unresolvable name as `none` rather than a refusal. -/
def resolveQuiet (origin : Nat) (name : String) : M (Option Declaration) :=
  tryCatch (resolve origin name) fun _ => pure none

def originOf (moduleName : String) : M (Option Nat) := do
  return (← get).sources.findIdx? (·.module.name == moduleName)

def declarationNamed (moduleName name : String) : M (Option Declaration) := do
  return (← get).byName[(moduleName, name)]?

/-- A closed type as an inference type: an instance of a generic sum is opened back into
its application, so it unifies with the generic declaration it instantiates. -/
partial def ofG (g : GType) : M IType := do
  match g with
  | .named m n _ =>
    let s ← get
    if m == s.generatedModule then
      if let some index := s.instanceByName[n]? then
        if let some i := s.instances[index]? then
          return .app i.origin i.declarationName i.declaration (← i.arguments.mapM ofG)
    return .ground g
  | .arrow a b => return .arrow (← ofG a) (← ofG b)
  | .row fs => return .row (← fs.mapM fun (n, t) => do return (n, ← ofG t))
  | .applied n args => return .applied n (← args.mapM ofG)
  | _ => return .ground g

/-- A type text as an inference type, without instantiating anything (mirrors `typeOf`;
whatever `typeOf` would refuse is `unknown` here and refused later by `typeOf`). -/
partial def itypeOf (origin : Nat) (bindings : List (String × IType)) (raw : String) : M IType := do
  spendInfer
  let text := trim raw
  if let some t := bindings.lookup text then return t
  let arrows := split text "->"
  if arrows.length > 1 then
    return .arrow (← itypeOf origin bindings arrows.head!) (← itypeOf origin bindings (String.intercalate "->" arrows.tail))
  if text.startsWith "(" && text.endsWith ")" then return ← itypeOf origin bindings (inner text)
  if (split text " with ").length == 2 then return .unknown
  if text.startsWith "{" && text.endsWith "}" then
    let contents := trim (inner text)
    if contents.isEmpty then return .row []
    let mut fields : List (String × IType) := []
    for f in split contents "," do
      let parts := split f ":"
      let name := trim (parts.headD "")
      if parts.length < 2 || !ObjectiveBendParse.isIdent name.toList then return .unknown
      fields := fields ++ [(name, ← itypeOf origin bindings (String.intercalate ":" parts.tail))]
    return .row fields
  if text.endsWith ">" && (text.splitOn "<").length > 1 then
    let name := trim (text.splitOn "<").head!
    let argsText := String.ofList (text.toList.drop (name.length + 1) |>.dropLast)
    let args ← (split argsText ",").mapM (itypeOf origin bindings)
    if ["Prototype", "Extension", "Specification", "Activity"].contains name then return .applied name args
    let some d ← resolveQuiet origin name | return .unknown
    let .sum _ _ ps _ := d.ast | return .unknown
    if ps.length != args.length then return .unknown
    return .app d.origin d.name (← declarationKey d) args
  if ["Nat", "Bool", "String", "Data", "_", "", "Self", "Super", "SpecMeta", "SpecClaims"].contains text then
    return .ground (.atom text)
  let some d ← resolveQuiet origin text | return .unknown
  if !d.ast.typeParameters.isEmpty then return .unknown
  match d.ast with
  | .typeAlias _ type _ => itypeOf d.origin [] type
  | .sum .. | .record .. => return .ground (.named (← originModule d.origin).name d.name (← declarationKey d))
  | _ => return .unknown

/-- The site's type-parameter bindings as inference types. -/
def siteBindings (site : Site) : M (List (String × IType)) :=
  site.bindings.mapM fun (n, g) => do return (n, ← ofG g)

def itypeAt (site : Site) (raw : String) : M IType := do
  itypeOf site.origin (← siteBindings site) raw

/-- The payload type of a sum's case. -/
partial def payloadOf (t : IType) (label : String) : M IType := do
  match t with
  | .applied "Activity" [_, _, a] => payloadOf a label
  | .app origin name _ args =>
    let some d ← declarationNamed (← originModule origin).name name | return .unknown
    let .sum _ cases ps _ := d.ast | return .unknown
    let some c := cases.find? (·.name == label) | return .unknown
    itypeOf d.origin (ps.zip args) c.type
  | .ground (.named m n _) =>
    let some d ← declarationNamed m n | return .unknown
    let .sum _ cases [] _ := d.ast | return .unknown
    let some c := cases.find? (·.name == label) | return .unknown
    itypeOf d.origin [] c.type
  | _ => return .unknown

/-- The type of a record's field. -/
def fieldOf (t : IType) (name : String) : M IType := do
  match t.value with
  | .row fs | .lit fs => return (fs.lookup name).getD .unknown
  | .ground (.row fs) => ofG ((fs.lookup name).getD (.atom "_"))
  | .ground (.named m n _) =>
    let some d ← declarationNamed m n | return .unknown
    let .record _ _ fields _ := d.ast | return .unknown
    let some f := fields.find? (·.name == name) | return .unknown
    itypeOf d.origin [] f.type
  | _ => return .unknown

/-- What a call's callee is: a definition or a sum's constructor, with its type
parameters, its parameters' types and its result (over `param` for the type
parameters), and the type arguments the source gave (`::<...>`), if any. -/
structure Callee where
  declaration : Declaration
  typeParameters : List String
  params : List IType
  result : IType
  given : Option (List IType)
  /-- The constructor label, for a sum's constructor. -/
  label : Option String
  /-- The expression naming the declaration (the call's callee, or a constructor's sum). -/
  named : Expr

def functionCallee (d : Declaration) (named : Expr) (given : Option (List IType)) : M (Option Callee) := do
  let .function sig tps _ _ := d.ast | return none
  let tps := tps.getD []
  let bindings := tps.map fun p => (p, IType.param p)
  let params ← sig.params.mapM fun p => itypeOf d.origin bindings p.type
  return some ⟨d, tps, params, ← itypeOf d.origin bindings sig.resultType, given, none, named⟩

def ctorCallee (d : Declaration) (label : String) (named : Expr) (given : Option (List IType)) : M (Option Callee) := do
  match d.ast with
  | .sum _ cases ps _ =>
    let some c := cases.find? (·.name == label) | return none
    let bindings := ps.map fun p => (p, IType.param p)
    let result ← if ps.isEmpty then
        pure (IType.ground (.named (← originModule d.origin).name d.name (← declarationKey d)))
      else pure (.app d.origin d.name (← declarationKey d) (ps.map .param))
    return some ⟨d, ps, [← itypeOf d.origin bindings c.type], result, given, some label, named⟩
  | .typeAlias _ type _ =>
    let t ← itypeOf d.origin [] type
    match t with
    | .app .. | .ground (.named ..) => return some ⟨d, [], [← payloadOf t label], t, none, some label, named⟩
    | _ => return none
  | _ => return none

/-- The callee of a call, when it names a definition or a constructor. -/
def calleeOf (site : Site) (names : List String) (callee : Expr) : M (Option Callee) := do
  match callee with
  | .specialize target types _ =>
    let some name := path names target | return none
    let some d ← resolveQuiet site.origin name | return none
    functionCallee d target (some (← types.mapM (itypeAt site)))
  | .member (.specialize target types _) label _ =>
    let some name := path names target | return none
    let some d ← resolveQuiet site.origin name | return none
    ctorCallee d label target (some (← types.mapM (itypeAt site)))
  | _ =>
    if let some name := path names callee then
      if let some d ← resolveQuiet site.origin name then
        if let .function .. := d.ast then return ← functionCallee d callee none
    if let .member target label _ := callee then
      if let some name := path names target then
        if let some d ← resolveQuiet site.origin name then return ← ctorCallee d label target none
    return none

def builtinResult (name : String) (arity : Nat) : Option IType :=
  if ["natText", "sha256Text"].contains name && arity == 1 then some (.ground (.atom "String"))
  else if name == "textLength" && arity == 1 then some (.ground (.atom "Nat"))
  else if ["textConcat", "textTake", "textDrop", "textJoin"].contains name && arity == 2 then some (.ground (.atom "String"))
  else if ["textSpan", "textBreak"].contains name && arity == 2 then some (.ground (.atom "Nat"))
  else if name == "textSlice" && arity == 3 then some (.ground (.atom "String"))
  else none

/-- Bind the type parameters `pattern` mentions to what `actual` has there. A parameter
already bound keeps its binding (a conflict is the elaborator's type error); an
incomplete type binds nothing; a literal's row binds only when `literals`. -/
partial def unify (literals : Bool) (σ : List (String × IType)) : IType → IType → List (String × IType)
  | .param p, actual =>
    if (σ.lookup p).isSome || !actual.complete || (!literals && actual.weak) then σ else σ ++ [(p, actual)]
  | .app _ _ k ps, .app _ _ k' as =>
    if k == k' && ps.length == as.length then (ps.zip as).foldl (fun σ (p, a) => unify literals σ p a) σ else σ
  | .applied n ps, .applied n' as =>
    if n == n' && ps.length == as.length then (ps.zip as).foldl (fun σ (p, a) => unify literals σ p a) σ else σ
  | .arrow a b, .arrow a' b' => unify literals (unify literals σ a a') b b'
  | .row ps, .row as | .row ps, .lit as =>
    ps.foldl (fun σ (n, p) => match as.lookup n with
      | some a => unify literals σ p a
      | none => σ) σ
  | _, _ => σ

/-- The type arguments of a call: from the arguments' declared types, then from the
expected type, then from record literals. An activity callee's result is matched
against an expected activity; a pure callee's against the expected activity's result. -/
def inferArguments (callee : Callee) (args : List IType) (expected : IType) : List (String × IType) := Id.run do
  let target := match callee.result, expected with
    | .applied "Activity" _, e => e
    | _, e => e.value
  let mut σ : List (String × IType) := []
  for (p, a) in callee.params.zip args do σ := unify false σ p a
  σ := unify false σ callee.result target
  for (p, a) in callee.params.zip args do σ := unify true σ p a
  return σ

/-- The type an expression synthesizes, without rewriting or instantiating anything.
`locals` holds each local's type, computed on demand. -/
partial def synthI (site : Site) (locals : List (String × M IType)) (e : Expr) : M IType := do
  spendInfer
  let names := locals.map (·.1)
  match e with
  | .nat .. => return .ground (.atom "Nat")
  | .bool .. => return .ground (.atom "Bool")
  | .str .. => return .ground (.atom "String")
  | .unit _ => return .lit []
  | .record fs _ => return .lit (← fs.mapM fun (n, v) => do return (n, ← synthI site locals v))
  | .extend i _ _ => synthI site locals i
  | .dataOf .. => return .ground (.atom "Data")
  | .binary op _ _ _ =>
    return .ground (.atom (if ["==", "!=", "<", "<=", ">", ">=", "&&", "||"].contains op then "Bool" else "Nat"))
  | .ite _ a b _ =>
    let t ← synthI site locals a
    if t.complete then return t
    synthI site locals b
  | .letE n type v b _ =>
    let t : M IType := if trim type == "_" then synthI site locals v else itypeAt site type
    synthI site ((n, t) :: locals) b
  | .lambda ps r _ _ =>
    let mut t ← itypeAt site r
    for p in ps.reverse do t := .arrow (← itypeAt site p.type) t
    return t
  | .var n _ =>
    if let some t := locals.lookup n then return ← t
    let some d ← resolveQuiet site.origin n | return .unknown
    let some c ← functionCallee d e none | return .unknown
    if !c.typeParameters.isEmpty then return .unknown
    return c.params.foldr .arrow c.result
  | .member target n _ =>
    if let some p := path names e then
      if let some d ← resolveQuiet site.origin p then
        let some c ← functionCallee d e none | return .unknown
        if !c.typeParameters.isEmpty then return .unknown
        return c.params.foldr .arrow c.result
    fieldOf (← synthI site locals target) n
  | .call callee args _ =>
    if let some name := path names callee then
      if (← resolveQuiet site.origin name).isNone then
        if name == "perform" then
          return match (← site.result) with
            | .applied "Activity" [_, r, _] => r
            | _ => .unknown
        if let some t := builtinResult name args.length then return t
    match ← calleeOf site names callee with
    | some c =>
      let σ ← match c.given with
        | some given => pure (c.typeParameters.zip given)
        | none => do
          if c.typeParameters.isEmpty then pure []
          else pure (inferArguments c (← args.mapM (synthI site locals)) .unknown)
      let mut t := c.result.subst σ
      -- A partial application leaves the remaining parameters.
      for p in (c.params.drop args.length).reverse do t := .arrow (p.subst σ) t
      return t
    | none =>
      let mut t ← synthI site locals callee
      for _ in args do
        match t with
        | .arrow _ b => t := b
        | _ => return .unknown
      return t
  | _ => return .unknown


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
    let state ← get
    if state.active.any (fun p => p.1 == declarationId && p.2 != argumentIdentity) then
      throw ("generic recursion changes type arguments: " ++ declaration.name)
    -- The instance key is a function of (declaration key, argument identity): an instance met
    -- before is found by that pair, without hashing again.
    if let some prior := state.instanceOf[(declarationId, argumentIdentity)]? then
      if let some priorInstance := state.instances[prior]? then
        return .named state.generatedModule priorInstance.name priorInstance.key
    let argumentId := Minidregg.Compiler.Sha256.hexString argumentIdentity
    let key := Minidregg.Compiler.Sha256.hexString (toJson [declarationId, argumentId]).compress
    if let some priorInstance := state.instances.find? (·.key == key) then return .named state.generatedModule priorInstance.name priorInstance.key
    if state.instances.size >= maxInstances then throw "generic specialization exceeds instance budget"
    let name ← fresh
    let index := (← get).instances.size
    modify fun s => { s with
      instances := s.instances.push {
        key := key
        declaration := declarationId
        declarationName := declaration.name
        name := name
        origin := declaration.origin
        arguments := arguments }
      instanceOf := s.instanceOf.insert (declarationId, argumentIdentity) index
      instanceByName := s.instanceByName.insert name index
      active := (declarationId, argumentIdentity) :: s.active }
    let generated := (← get).generatedModule
    let site : Site := { origin := declaration.origin, target := generated, bindings := binders.zip arguments, lifted := true }
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

/-- An inference type as the `GType` the explicit spelling's type text resolves to:
nested generic sums are instantiated first, left to right, as `typeOf` does. -/
def toG : Nat → IType → M GType
  | 0, _ => throw "generic type nesting capacity"
  | fuel + 1, t => do
    match t with
    | .ground g => return g
    | .app origin name _ args =>
      let gs ← args.mapM (toG fuel)
      let some d ← declarationNamed (← originModule origin).name name | throw ("generic declaration missing: " ++ name)
      instantiate fuel d gs
    | .arrow a b => return .arrow (← toG fuel a) (← toG fuel b)
    | .row fs | .lit fs => return .row (← fs.mapM fun (n, t) => do return (n, ← toG fuel t))
    | .applied n args => return .applied n (← args.mapM (toG fuel))
    | .param p => throw ("internal: type parameter " ++ p ++ " was not inferred")
    | .unknown => throw "internal: an inferred type is unknown"

/-- `locals` are the names in scope with their types (computed on demand); `expected` is
the type the expression's position expects (`unknown` when nothing does), on demand. -/
def rewriteExpr : Nat → Site → List (String × M IType) → M IType → Expr → M Expr
  | 0, _, _, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, locals, expected, e => do
    spend
    let names := locals.map (·.1)
    let recur := rewriteExpr fuel site locals (pure .unknown)
    let recurFields := fun (fs : List (String × Expr)) (fieldTypes : String → M IType) => fs.mapM fun (n, v) => do
      spendString n
      return (n, ← rewriteExpr fuel site locals (fieldTypes n) v)
    if let .call (.specialize target types _) args span := e then
      if path names target == some "Data.of" && (← resolve site.origin "Data").isNone then
        let [typeArgument] := types | throw "Data.of takes exactly one type argument"
        let [value] := args | throw "Data.of takes exactly one value"
        return .dataOf (← rewriteType fuel site typeArgument) (← recur value) span
    if let .call callee args span := e then
      let isPerform := path names callee == some "perform" && (← resolveQuiet site.origin "perform").isNone
      let found ← if isPerform then pure none else calleeOf site names callee
      if let some c := found then
        if !c.typeParameters.isEmpty && c.given.isNone then
          -- Inferred: the explicit spelling's rewrite, with the arguments it would name.
          let σ := inferArguments c (← args.mapM (synthI site locals)) (← expected)
          let missing := c.typeParameters.filter fun p => (σ.lookup p).isNone
          unless missing.isEmpty do
            let written := match c.named with
              | .var n _ => n
              | .member (.var a _) n _ => a ++ "." ++ n
              | _ => c.declaration.name
            let shown := c.typeParameters.map fun p => ((σ.lookup p).map IType.show).getD p
            let spelled := written ++ "::<" ++ ", ".intercalate shown ++ ">" ++ ((c.label.map ("." ++ ·)).getD "")
            throw ("cannot infer the type argument" ++ (if missing.length > 1 then "s " else " ") ++
              ", ".intercalate missing ++ " of " ++ written ++ (match c.label with | some l => "." ++ l | none => "") ++
              " (line " ++ toString span.line ++ ") from its arguments or the type its position expects; write " ++
              spelled ++ "(...) naming " ++ ", ".intercalate missing)
          let args ← (args.zipIdx).mapM fun (a, i) =>
            rewriteExpr fuel site locals (pure ((c.params[i]?.getD .unknown).subst σ)) a
          let types ← c.typeParameters.mapM fun p => toG fuel ((σ.lookup p).getD .unknown)
          let .named module name _ ← instantiate fuel c.declaration types | throw "generic instance has no declaration"
          let made ← ref module name c.named.span
          let callee := match c.label with
            | some l => Expr.member made l callee.span
            | none => made
          return .call callee args span
        -- A definition or constructor whose type arguments are given or absent: each
        -- argument at its parameter's type.
        let σ := c.typeParameters.zip (c.given.getD [])
        let args ← (args.zipIdx).mapM fun (a, i) =>
          rewriteExpr fuel site locals (pure ((c.params[i]?.getD .unknown).subst σ)) a
        return .call (← recur callee) args span
      if isPerform then
        let planType : M IType := do
          return match (← site.result) with
            | .applied "Activity" [p, _, _] => p
            | _ => .unknown
        let args ← args.mapM (rewriteExpr fuel site locals planType)
        return .call (← recur callee) args span
    if let .specialize target types span := e then
      let some name := path names target | throw "generic specialization requires an unshadowed declaration"
      let some declaration ← resolve site.origin name | throw ("unknown generic declaration: " ++ name)
      let args ← types.mapM (typeOf fuel site.origin site.bindings)
      let .named module name _ ← instantiate fuel declaration args | throw "generic instance has no declaration"
      return ← ref module name span
    if let some name := path names e then
      -- A bare import alias is not a declaration; member resolution handles it.
      let imported := (← originModule site.origin).imports.any (·.importAlias == name)
      if !imported then
        if let some declaration ← resolve site.origin name then
          if let .typeAlias _ type _ := declaration.ast then
            let .named module name _ ← typeOf fuel declaration.origin [] type
              | throw "constructor alias must name a sum"
            return ← ref module name e.span
          if !declaration.ast.typeParameters.isEmpty then
            throw ("generic declaration needs explicit specialization: " ++ name ++
              " (type arguments are inferred only where it is called)")
          if site.lifted then return ← ref (← originModule declaration.origin).name declaration.name e.span
    match e with
    | .var n s => do spendString n; return .var n s
    | .nat v s => do spendString v; return .nat v s
    | .bool v s => return .bool v s
    | .str v s => do spendString v; return .str v s
    | .unit s => return .unit s
    | .record fs s => return .record (← recurFields fs fun n => do fieldOf (← expected) n) s
    | .extend i fs s =>
      let fs ← recurFields fs fun n => do fieldOf (← synthI site locals i) n
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
      let inner := ps.map (fun p => (p.name, itypeAt site p.type)) ++ locals
      return .lambda (← ps.mapM (rewriteParam fuel site)) (← rewriteType fuel site r)
        (← rewriteExpr fuel site inner (itypeAt site r) b) s
    | .extensionValue ps t b s =>
      let inner := ps.map (fun p => (p.name, itypeAt site p.type)) ++ locals
      return .extensionValue (← ps.mapM (rewriteParam fuel site)) (← rewriteType fuel site t)
        (← rewriteExpr fuel site inner (pure .unknown) b) s
    | .binary op l r s => do spendString op; return .binary op (← recur l) (← recur r) s
    | .ite c t f s =>
      let c ← recur c
      let f ← rewriteExpr fuel site locals expected f
      return .ite c (← rewriteExpr fuel site locals expected t) f s
    | .letE n t v b s =>
      let declared : M IType := if trim t == "_" then synthI site locals v else itypeAt site t
      let value ← rewriteExpr fuel site locals (if trim t == "_" then pure .unknown else declared) v
      let body ← rewriteExpr fuel site ((n, declared) :: locals) expected b
      return .letE n (← rewriteType fuel site t) value body s
    | .specialize .. | .dataOf .. => return e

def rewriteBody : Nat → Site → List (String × M IType) → M IType → Body → M Body
  | 0, _, _, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, locals, expected, b => do
    spend
    match b with
    | .expr e s => return .expr (← rewriteExpr fuel site locals expected e) s
    | .cases scrutinee branches s =>
      let scrutinee' ← rewriteExpr fuel site locals (pure .unknown) scrutinee
      let branches ← branches.mapM fun (pattern, body, span) => do
        let binder : M IType := match pattern with
          | .ctor l _ => do payloadOf (← synthI site locals scrutinee) l
          | .succ _ => pure (.ground (.atom "Nat"))
          | _ => pure .unknown
        return (pattern, ← rewriteBody fuel site ((pattern.binder, binder) :: locals) expected body, span)
      return .cases scrutinee' branches s
    | .letB n t v rest s =>
      let declared : M IType := if trim t == "_" then synthI site locals v else itypeAt site t
      let value ← rewriteExpr fuel site locals (if trim t == "_" then pure .unknown else declared) v
      let rest ← rewriteBody fuel site ((n, declared) :: locals) expected rest
      return .letB n (← rewriteType fuel site t) value rest s

def rewriteDecl : Nat → Site → List (String × M IType) → Decl → M Decl
  | 0, _, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, locals, d => do
    spend
    spendString d.name
    let typed := fun (ps : List Param) => ps.map (fun p => (p.name, itypeAt site p.type)) ++ locals
    let untyped := fun (ns : List String) => ns.map (fun n => (n, (pure .unknown : M IType))) ++ locals
    match d with
    | .reexport name target span =>
      if let some declaration ← resolve site.origin target then
        if !declaration.ast.typeParameters.isEmpty then
          throw ("unspecialized generic export is unsupported: " ++ target ++ " in " ++ (← originModule site.origin).name ++
            " at " ++ span.json.compress ++ "; export an ordinary checked definition")
      spendString target
      return .reexport name target span
    | .function sig typeParameters body span =>
      let result := itypeAt site sig.resultType
      let sig' ← rewriteSignature fuel site sig
      let site := { site with result }
      return .function sig' typeParameters (← rewriteBody fuel site (typed sig.params) result body) span
    | .extension name ps t body binders span =>
      let ps' ← ps.mapM (rewriteParam fuel site)
      let t ← rewriteType fuel site t
      return .extension name ps' t (← rewriteBody fuel site (typed ps) (pure .unknown) body) binders span
    | .spec sp =>
      let locals := untyped ["self", "super"]
      let claims ← sp.claims.mapM fun c => do
        let body ← rewriteExpr fuel site (c.params.map (fun p => (p.name, itypeAt site p.type)) ++ locals) (pure .unknown) c.body
        return { c with body, params := ← c.params.mapM (rewriteParam fuel site) }
      let methods ← sp.methods.mapM fun m => do
        let body ← rewriteBody fuel site (m.signature.params.map (fun p => (p.name, itypeAt site p.type)) ++ locals)
          (pure .unknown) m.body
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
  | .law n source reading _ => [n, source, reading]
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
      let site : Site := { origin := index, target := source.module.name, bindings := [], lifted := false }
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
