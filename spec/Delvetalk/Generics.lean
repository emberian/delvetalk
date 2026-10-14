/- Bounded rank-1 source specialization. It rewrites the parsed surface
(`Compiler.ObjectiveBendSurface`) and hands the elaborator ordinary modules: every
`f::<T>` becomes a reference to the instance `__generic_N` of a generated module,
every `Data.of::<T>(v)` the `dataOf` node, and every type text names its instances. -/
import Compiler.ObjectiveBendFrontEnd
import Delvetalk.DocumentTemplate
namespace Delvetalk.Generics
open Lean (Json toJson)
open Delvetalk.Compiler
open ObjectiveBendFrontEnd
open ObjectiveBendSurface (Span Param Expr Body Signature Decl)
set_option autoImplicit false

/-- Generic instances one package specializes. Measured on persvati (lane/kernel13): a closure
of N row types each used through Relation insert, count, retract and rows (about eleven
instances each) checks and compiles an entry reaching every instance in 0.15 s at 354 instances,
0.73 s at 1,025 (107 MB resident, a 2.0 MB packet), 1.12 s at 1,410 and 2.7 s at 2,818: 1,024 is
the most whose check and compile together stay under a second. The world's largest closure
(Kind) is 197. -/
def maxInstances : Nat := 1024
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

/-- A type as a refusal names it (`Lists.List<Rows.Rain>`). -/
partial def GType.brief : GType → String
  | .atom n => n
  | .named m n _ => m ++ "." ++ n
  | .applied n args => n ++ "<" ++ ", ".intercalate (args.map GType.brief) ++ ">"
  | .arrow a b => a.brief ++ " -> " ++ b.brief
  | .row fields => "{" ++ ", ".intercalate (fields.map fun (n, t) => n ++ ": " ++ t.brief) ++ "}"
  | .overlay a b => a.brief ++ " with " ++ b.brief

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
  /-- The answers of inference demands met so far, by demand (`demand`). -/
  demanded : Std.HashMap Nat IType := {}
  nextDemand : Nat := 0
  /-- Inference types of type texts read without type-parameter bindings, by (origin, text):
  such a reading is a function of the declarations, which a state never changes. -/
  itypes : Std.HashMap (Nat × String) IType := {}
  /-- Callee skeletons (type parameters, parameter and result types over `param`), by the
  declaration's origin and name and the constructor label ("" for a definition). -/
  callees : Std.HashMap (Nat × String × String) (List String × List IType × IType) := {}
  /-- The declaration being rewritten (module, name), which an instance is specialized for. -/
  current : String × String := ("", "")

/-- A refusal of the pass: its message and, when known, the module and the span of the source
that asked for it. A refusal raised inside a declaration's rewriting is placed at that
declaration (`run`) unless it names a span of its own. -/
structure Refusal where
  message : String
  module : Option String := none
  span : Option Span := none
  deriving Inhabited

instance : Coe String Refusal := ⟨fun message => { message }⟩
instance : MonadLift (Except String) (Except Refusal) := ⟨fun e => e.mapError (fun message => { message })⟩

abbrev M := StateT State (Except Refusal)

/-- The pass throws and catches text (`throw "…"`, `tryCatch … fun message => …`); a refusal
placed at a span is thrown with `throwThe Refusal`, and text caught is its message alone. -/
instance : MonadExceptOf String M where
  throw message := throwThe Refusal { message }
  tryCatch x handle := tryCatchThe Refusal x fun r => handle r.message

/-- A refusal at `span` of `module`. -/
def refusalAt (module : String) (span : Span) (message : String) : Refusal :=
  { message, module := some module, span := some span }

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

/-- Why `text` names no source type, and what does: a qualified name's module and the types it declares (playtest 5:
"unknown source type in specialization: Super.Done", over a record, whose layer beneath declares no Done). -/
def unknownType (origin : Nat) (text : String) : M String := do
  let said := "unknown source type in specialization: " ++ text
  let m ← originModule origin
  let [alias, n] := text.splitOn "." | return said
  let some imported := m.imports.find? (·.importAlias == alias)
    | return said ++ "; " ++ alias ++ " is no import of module " ++ m.name
  let types := ((← get).byName.toList.filterMap fun ((module, name), d) =>
    if module != imported.moduleName then none else match d.ast with
      | .record .. | .sum .. | .typeAlias .. => some name
      | _ => none).mergeSort (fun a b => decide (a ≤ b))
  return said ++ "; " ++ alias ++ " (" ++ imported.moduleName ++ ") declares no type " ++ n ++
    (if types.isEmpty then "" else "; its types: " ++ ", ".intercalate (types.take 24))

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

def spendInfer : M Unit := do
  let s ← get
  if s.inferRemaining == 0 then throw "type-argument inference exceeds its step budget"
  set { s with inferRemaining := s.inferRemaining - 1 }

/-- A type computed on demand and at most once: the first demand runs `action`, every later
one reads its answer, so a local used u times synthesizes its initializer once (and a binding
nobody demands costs nothing). Synthesis reads only what the pass never changes once made
(sources, declaration keys, instances), so the answer is the one a rerun would give. A refusal
is not kept: a later demand runs `action` again and refuses again. A refusal that `tryCatch`
recovers from rolls the state back, demands made inside it with their answers. -/
def demand (action : M IType) : M (M IType) := do
  let s ← get
  let id := s.nextDemand
  set { s with nextDemand := id + 1 }
  return do
    if let some t := (← get).demanded[id]? then return t
    let t ← action
    modify fun s => { s with demanded := s.demanded.insert id t }
    return t

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
  if bindings.isEmpty then
    if let some t := (← get).itypes[(origin, raw)]? then return t
    let t ← reading origin [] raw
    modify fun s => { s with itypes := s.itypes.insert (origin, raw) t }
    return t
  reading origin bindings raw
where reading (origin : Nat) (bindings : List (String × IType)) (raw : String) : M IType := do
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

/-- A callee's skeleton, read once per declaration (and label) and kept (`State.callees`). -/
def skeleton (d : Declaration) (label : String)
    (read : M (Option (List String × List IType × IType))) : M (Option (List String × List IType × IType)) := do
  if let some c := (← get).callees[(d.origin, d.name, label)]? then return some c
  let some c ← read | return none
  modify fun s => { s with callees := s.callees.insert (d.origin, d.name, label) c }
  return some c

def functionCallee (d : Declaration) (named : Expr) (given : Option (List IType)) : M (Option Callee) := do
  let .function sig tps _ _ := d.ast | return none
  let some (tps, params, result) ← skeleton d "" do
      let tps := tps.getD []
      let bindings := tps.map fun p => (p, IType.param p)
      let params ← sig.params.mapM fun p => itypeOf d.origin bindings p.type
      return some (tps, params, ← itypeOf d.origin bindings sig.resultType)
    | return none
  return some ⟨d, tps, params, result, given, none, named⟩

def ctorCallee (d : Declaration) (label : String) (named : Expr) (given : Option (List IType)) : M (Option Callee) := do
  match d.ast with
  | .sum _ cases ps _ =>
    let some (tps, params, result) ← skeleton d label do
        let some c := cases.find? (·.name == label) | return none
        let bindings := ps.map fun p => (p, IType.param p)
        let result ← if ps.isEmpty then
            pure (IType.ground (.named (← originModule d.origin).name d.name (← declarationKey d)))
          else pure (.app d.origin d.name (← declarationKey d) (ps.map .param))
        return some (ps, [← itypeOf d.origin bindings c.type], result)
      | return none
    return some ⟨d, tps, params, result, given, some label, named⟩
  | .typeAlias _ type _ =>
    let some (_, params, t) ← skeleton d label do
        let t ← itypeOf d.origin [] type
        match t with
        | .app .. | .ground (.named ..) => return some ([], [← payloadOf t label], t)
        | _ => return none
      | return none
    return some ⟨d, [], params, t, none, some label, named⟩
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
  else if name == "textHasAny" && arity == 2 then some (.ground (.atom "Bool"))
  else if (name == "canonicalCompare" && arity == 2) || (name == "relationCount" && arity == 1) then
    some (.ground (.atom "Nat"))
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

/-! ## World calls -/

/-- The world's protocol: the module named `World` and its `protocol world:` methods. -/
def worldProtocol : M (Option (Nat × List ObjectiveBendSurface.Field)) := do
  let sources := (← get).sources
  for i in [:sources.size] do
    if sources[i]!.module.name == "World" then
      for d in sources[i]!.ast.decls do
        if let .protocol "world" methods _ _ := d then return some (i, methods)
  return none

/-- `world` as the reserved receiver: not a local, a declaration or an import alias. -/
def isWorldReceiver (site : Site) (names : List String) : Expr → M Bool
  | .var "world" _ => do
    if names.contains "world" then return false
    if (← originModule site.origin).imports.any (·.importAlias == "world") then return false
    return (← resolveQuiet site.origin "world").isNone
  | _ => pure false

/-- A world call's method, its type arguments as written (if any) and its argument. -/
def worldCallOf (site : Site) (names : List String) : Expr → M (Option (String × Option (List String) × List Expr))
  | .call (.specialize (.member receiver method _) types _) args _ => do
    if ← isWorldReceiver site names receiver then return some (method, some types, args) else return none
  | .call (.member receiver method _) args _ => do
    if ← isWorldReceiver site names receiver then return some (method, none, args) else return none
  | _ => pure none

/-- A world method's input and result type texts (its type is `INPUT -> RESULT`). -/
def worldSignature (f : ObjectiveBendSurface.Field) : String × String :=
  match split f.type "->" with
  | input :: rest => (trim input, trim (String.intercalate "->" rest))
  | [] => (f.type, "")

/-- The world method `method` of the package's protocol, refused by name when absent. -/
def worldMethod (method : String) : M (Nat × ObjectiveBendSurface.Field) := do
  let some (origin, methods) ← worldProtocol
    | throw ("refused (world-call): world." ++ method ++ " is a call of the world's protocol, which no module " ++
        "named World in this package declares (`protocol world:`); import ./World.obend")
  let some f := methods.find? (·.name == method)
    | throw ("refused (world-call): the world has no method " ++ method ++ "; its methods are " ++
        ", ".intercalate (methods.map (·.name)))
  return (origin, f)

/-- The type arguments of a world call written without `::<...>`: a method whose input is
exactly its one type parameter (`write<E>(E)`, `judge<E>(E)`) takes the argument's type. -/
def worldArgumentsOf (synth : Expr → M IType) (method : String)
    (f : ObjectiveBendSurface.Field) (args : List Expr) : M (List IType) := do
  let (input, _) := worldSignature f
  let cannot : M (List IType) := throw ("refused (world-call): cannot infer the type argument" ++
    (if f.typeParameters.length > 1 then "s " else " ") ++ ", ".intercalate f.typeParameters ++ " of world." ++
    method ++ "; write world." ++ method ++ "::<" ++ ", ".intercalate f.typeParameters ++ ">(...)")
  match f.typeParameters, args with
  | [], _ => return []
  | [p], [arg] =>
    if trim input != p then return ← cannot
    let t ← synth arg
    if !t.complete then return ← cannot
    return [t]
  | _, _ => cannot



/-- The type an expression synthesizes, without rewriting or instantiating anything.
`locals` holds each local's type, computed on demand and at most once (`demand`). -/
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
    let t ← demand (if trim type == "_" then synthI site locals v else itypeAt site type)
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
    if let some (method, given, args) ← worldCallOf site names e then
      let (origin, f) ← worldMethod method
      let types ← match given with
        | some ts => ts.mapM (itypeAt site)
        | none => worldArgumentsOf (synthI site locals) method f args
      if types.length != f.typeParameters.length then return .unknown
      return ← itypeOf origin (f.typeParameters.zip types) (worldSignature f).2
    if let some name := path names callee then
      if (← resolveQuiet site.origin name).isNone then
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


/-- Parameters as locals: each its declared type, on demand and at most once. -/
def paramLocals (site : Site) (ps : List Param) : M (List (String × M IType)) :=
  ps.mapM fun p => do return (p.name, ← demand (itypeAt site p.type))

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
    let some declaration ← resolve origin text | throw (← unknownType origin text)
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
    let argumentId := Delvetalk.Compiler.Sha256.hexString argumentIdentity
    let key := Delvetalk.Compiler.Sha256.hexString (toJson [declarationId, argumentId]).compress
    if state.instances.size >= maxInstances then
      let (module, name) := state.current
      throw (s!"refused (generic-instances): the package needs more than {maxInstances} generic instances; " ++
        s!"{module}.{name} asks for instance {maxInstances + 1}, {declaration.name} at " ++
        ", ".intercalate (arguments.map GType.brief) ++ " (Generics.maxInstances)")
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

/-- `locals` are the names in scope with their types (computed on demand, each at most once:
`demand`); `expected` is the type the expression's position expects (`unknown` when nothing
does), on demand. -/
def rewriteExpr : Nat → Site → List (String × M IType) → M IType → Expr → M Expr
  | 0, _, _, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, locals, expected, e => do
    spend
    let names := locals.map (·.1)
    let recur := rewriteExpr fuel site locals (pure .unknown)
    let recurFields := fun (fs : List (String × Expr)) (fieldTypes : String → M IType) => fs.mapM fun (n, v) => do
      spendString n
      return (n, ← rewriteExpr fuel site locals (fieldTypes n) v)
    if let some (method, given, args) ← worldCallOf site names e then
      let (origin, f) ← tryCatch (worldMethod method) fun why => throw (why ++ " (line " ++ toString e.span.line ++ ")")
      let at_ := " (line " ++ toString e.span.line ++ ")"
      let [arg] := args | throw ("refused (world-call): world." ++ method ++ " takes exactly one argument" ++ at_)
      let (input, result) := worldSignature f
      let (types, itypes) ← match given with
        | some written =>
          if written.length != f.typeParameters.length then
            throw ("refused (world-call): world." ++ method ++ " takes " ++ toString f.typeParameters.length ++
              " type argument" ++ (if f.typeParameters.length == 1 then "" else "s") ++ ", not " ++ toString written.length ++ at_)
          pure (← written.mapM (typeOf fuel site.origin site.bindings), ← written.mapM (itypeAt site))
        | none =>
          let itypes ← tryCatch (worldArgumentsOf (synthI site locals) method f args) fun why => throw (why ++ at_)
          pure (← itypes.mapM (toG fuel), itypes)
      let target := site.target
      let inputShown ← render target (← typeOf fuel origin (f.typeParameters.zip types) input)
      let resultShown ← render target (← typeOf fuel origin (f.typeParameters.zip types) result)
      spendString inputShown
      spendString resultShown
      let arg ← rewriteExpr fuel site locals (itypeOf origin (f.typeParameters.zip itypes) input) arg
      return .worldCall method inputShown resultShown arg (match e with | .call _ _ sp => sp | _ => e.span)
    if let .call (.specialize target types _) args span := e then
      if path names target == some "Data.of" && (← resolve site.origin "Data").isNone then
        let [typeArgument] := types | throw "Data.of takes exactly one type argument"
        let [value] := args | throw "Data.of takes exactly one value"
        return .dataOf (← rewriteType fuel site typeArgument) (← recur value) span
    if let .call callee args span := e then
      if let some c ← calleeOf site names callee then
        if !c.typeParameters.isEmpty && c.given.isNone then
          -- Inferred: the explicit spelling's rewrite, with the arguments it would name.
          let σ := inferArguments c (← args.mapM (synthI site locals)) (← expected)
          let missing := c.typeParameters.filter fun p => (σ.lookup p).isNone
          unless missing.isEmpty do
            let written := match c.named with
              | .var n _ => n
              | .member (.var a _) n _ => a ++ "." ++ n
              | _ => c.declaration.name
            -- A State's edits are typed as its derived Edits name them (`deriveEdits`): a number's field
            -- Edit<Nat, Nat>, any other field's Edit<T, {}>, a list's or a relation's Entries<X, X>; the refusal
            -- fills in what that fixes (playtest 5: "the mystery second type argument").
            let known := fun (p : String) => (σ.lookup p).map IType.show
            let edits := c.declaration.name == "Edit" || c.declaration.name == "Entries"
            let fixed : String → Option String := fun p =>
              if !edits then known p else match c.declaration.name, c.typeParameters, p with
                | "Edit", [t, d], _ =>
                  let number := known t == some "Nat" || known d == some "Nat"
                  if number then some "Nat" else if p == d then (known t).map fun _ => "{}" else known p
                | "Entries", [x, u], _ => known x <|> known u
                | _, _, _ => known p
            let shown := c.typeParameters.map fun p => (fixed p).getD p
            let spelled := written ++ "::<" ++ ", ".intercalate shown ++ ">" ++ ((c.label.map ("." ++ ·)).getD "")
            let named := missing.filter fun p => (fixed p).isNone
            let called := written ++ (match c.label with | some l => "." ++ l | none => "")
            let writeNote := if !edits then "" else
              "; in a write the field names them: let written(_) = write {field: set value} (add, append, insert, …); " ++
              "a number's field is Edit<Nat, Nat>, any other field's Edit<T, {}>, a list's or a relation's Entries<X, X>"
            throw ("cannot infer the type argument" ++ (if missing.length > 1 then "s " else " ") ++
              ", ".intercalate missing ++ " of " ++ called ++
              " (line " ++ toString span.line ++ ") from its arguments or the type its position expects; write " ++
              spelled ++ "(...)" ++ (if named.isEmpty then "" else " naming " ++ ", ".intercalate named) ++ writeNote)
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
    if let .specialize target types span := e then
      let some name := path names target |
        throw "type arguments `::<…>` follow the name of a declaration this module can see, before its call: Plans.Edit::<Nat, {}>.set(...), never after a call or on a local name"
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
    | .record fs s =>
      let expected ← demand expected
      return .record (← recurFields fs fun n => do fieldOf (← expected) n) s
    | .extend i fs s =>
      let base ← demand (synthI site locals i)
      let fs ← recurFields fs fun n => do fieldOf (← base) n
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
      let inner := (← paramLocals site ps) ++ locals
      return .lambda (← ps.mapM (rewriteParam fuel site)) (← rewriteType fuel site r)
        (← rewriteExpr fuel site inner (itypeAt site r) b) s
    | .extensionValue ps t b s =>
      let inner := (← paramLocals site ps) ++ locals
      return .extensionValue (← ps.mapM (rewriteParam fuel site)) (← rewriteType fuel site t)
        (← rewriteExpr fuel site inner (pure .unknown) b) s
    | .binary op l r s => do spendString op; return .binary op (← recur l) (← recur r) s
    | .ite c t f s =>
      let c ← recur c
      let expected ← demand expected
      let f ← rewriteExpr fuel site locals expected f
      return .ite c (← rewriteExpr fuel site locals expected t) f s
    | .letE n t v b s =>
      let declared ← demand (if trim t == "_" then synthI site locals v else itypeAt site t)
      let value ← rewriteExpr fuel site locals (if trim t == "_" then pure .unknown else declared) v
      let body ← rewriteExpr fuel site ((n, declared) :: locals) expected b
      return .letE n (← rewriteType fuel site t) value body s
    | .specialize .. | .dataOf .. | .worldCall .. => return e

def rewriteBody : Nat → Site → List (String × M IType) → M IType → Body → M Body
  | 0, _, _, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, locals, expected, b => do
    spend
    match b with
    | .expr e s => return .expr (← rewriteExpr fuel site locals expected e) s
    | .cases scrutinee branches s =>
      let scrutinee' ← rewriteExpr fuel site locals (pure .unknown) scrutinee
      let scrutineeType ← demand (synthI site locals scrutinee)
      let expected ← demand expected
      let branches ← branches.mapM fun (pattern, body, span) => do
        let binder ← demand (match pattern with
          | .ctor l _ => do payloadOf (← scrutineeType) l
          | .succ _ => pure (.ground (.atom "Nat"))
          | _ => pure .unknown)
        return (pattern, ← rewriteBody fuel site ((pattern.binder, binder) :: locals) expected body, span)
      return .cases scrutinee' branches s
    | .letB n t v rest s =>
      let declared ← demand (if trim t == "_" then synthI site locals v else itypeAt site t)
      let value ← rewriteExpr fuel site locals (if trim t == "_" then pure .unknown else declared) v
      let rest ← rewriteBody fuel site ((n, declared) :: locals) expected rest
      return .letB n (← rewriteType fuel site t) value rest s

def rewriteDecl : Nat → Site → List (String × M IType) → Decl → M Decl
  | 0, _, _, _ => throw "generic AST nesting capacity"
  | fuel + 1, site, locals, d => do
    spend
    spendString d.name
    let typed := fun (ps : List Param) => do return (← paramLocals site ps) ++ locals
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
      let result ← demand (itypeAt site sig.resultType)
      let sig' ← rewriteSignature fuel site sig
      return .function sig' typeParameters (← rewriteBody fuel site (← typed sig.params) result body) span
    | .extension name ps t body binders span =>
      let ps' ← ps.mapM (rewriteParam fuel site)
      let t ← rewriteType fuel site t
      return .extension name ps' t (← rewriteBody fuel site (← typed ps) (pure .unknown) body) binders span
    | .spec sp =>
      let locals := untyped ["self", "super"]
      let claims ← sp.claims.mapM fun c => do
        let body ← rewriteExpr fuel site ((← paramLocals site c.params) ++ locals) (pure .unknown) c.body
        return { c with body, params := ← c.params.mapM (rewriteParam fuel site) }
      let methods ← sp.methods.mapM fun m => do
        let body ← rewriteBody fuel site ((← paramLocals site m.signature.params) ++ locals) (pure .unknown) m.body
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
    | .clause .. | .typeAlias .. => return d
    | .protocol name methods shown span =>
      -- The implementer's State, Plan and Response stay names (the elaborator binds them).
      let free := { site with bindings := ["State", "Plan", "Response"].map (fun n => (n, GType.atom n)) ++ site.bindings }
      -- A method with its own type parameters (the world's, `view<S>(...)`) is
      -- instantiated at each call (`lowerWorldCall`), so its text stays as written.
      let methods ← methods.mapM fun f => do
        if !f.typeParameters.isEmpty then return f
        return { f with type := ← rewriteType fuel free f.type }
      return .protocol name methods shown span
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
  | .member (.var "world" _) _ _ => true
  | .member t _ _ => (exprGenerics t)
  | .call c args _ => (exprGenerics c) || listHasGenerics args
  | .compose specs _ => listHasGenerics specs
  | .fix spec inherited _ => (exprGenerics spec) || (exprGenerics inherited)
  | .lambda _ _ b _ | .extensionValue _ _ b _ => (exprGenerics b)
  | .binary _ l r _ => (exprGenerics l) || (exprGenerics r)
  | .ite c t f _ => (exprGenerics c) || (exprGenerics t) || (exprGenerics f)
  | .letE _ _ v b _ => (exprGenerics v) || (exprGenerics b)
  | .dataOf _ v _ | .worldCall _ _ _ v _ => (exprGenerics v)
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
  -- A `write {f: remove v}` is lowered once the State's field types are resolved.
  d.mapVars (fun n => if n == ObjectiveBendParse.removeMarker then "" else n) != d ||
  match d with
  | .typeAlias .. | .protocol .. => true
  | .function _ _ b _ | .extension _ _ _ b _ _ => (bodyGenerics b)
  | .spec sp => sp.methods.any (fun m => bodyGenerics m.body) || sp.claims.any (fun c => exprGenerics c.body)
  | _ => false

/-! ## The names a fresh `__generic_N` must avoid

Every identifier-shaped run of the module's strings as JSON prints them (so a run never
crosses a string, and an escape's letters join the run they touch), restricted to the
strings that could hold a `__generic_` run at all. -/

/-- Whether `s` holds `__generic_` (most strings have no `_` at all, and are passed at once). -/
def candidate (s : String) : Bool := s.contains '_' && (s.splitOn "__generic_").length > 1

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
  | .worldCall m i r v _ => m :: i :: r :: (exprStrings v)
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
  | .clause _ n source reading _ => [n, source, reading]
  | .function sig ps b _ => signatureStrings sig ++ ps.getD [] ++ (bodyStrings b)
  | .protocol n methods shown _ => n :: shown ++ methods.flatMap (fun f => [f.name, f.type])

def moduleNames (m : ObjectiveBendSurface.Module) (names : Std.TreeSet String) : Std.TreeSet String :=
  let names := m.imports.foldl (fun acc i => addNames (addNames acc i.path) i.importAlias) names
  m.decls.foldl (fun acc d => (declStrings d).foldl addNames acc) names

/-! ## Edits and `keep()` derived from the State (KERNEL-HANDOFF §16 item 8a)

A module that declares `State` (a record, or a type naming one) and imports Plan.obend (alias
`P`), and declares neither `Edits` nor `keep`, gets both, at the end of the module, as the source

    record Edits:
      f: P.Entries<X, X>     -- f's type is List.List<X> or Relation.Relation<X>
      g: P.Edit<Nat, Nat>    -- g is a Nat
      h: P.Edit<T, {}>       -- anything else, T its type
    def keep() -> Edits:
      {f: P.Entries::<X, X>.keep({}), g: P.Edit::<Nat, Nat>.keep({}), h: P.Edit::<T, {}>.keep({})}

parsed by the ordinary parser and specialized with the module, so a module that spells this
pair by hand compiles to the same packet. Types are resolved here (through aliases and other
modules), and the types the module did not write itself are spelled through its own imports. -/

/-- The file an import path names (`./lib/List.obend` names `List.obend`). -/
def fileOf (path : String) : String := ((path.splitOn "/").getLast?).getD path

/-- A declaration of module `home` as module `origin` writes its name. -/
def spellName (origin home : Nat) (name : String) : M (Option String) := do
  if origin == home then return some name
  let some source := (← get).sources[origin]? | return none
  return (source.module.imports.find? (·.target == home)).map (·.importAlias ++ "." ++ name)

/-- A type as module `origin` writes it; `none` when a declaration it names is in a module
`origin` does not import. -/
partial def spell (origin : Nat) (g : GType) : M (Option String) := do
  let all := fun (gs : List GType) => do return (← gs.mapM (spell origin)).mapM id
  match g with
  | .atom n => return some n
  | .named m n _ =>
    let s ← get
    if m == s.generatedModule then
      let some index := s.instanceByName[n]? | return none
      let some i := s.instances[index]? | return none
      let some base ← spellName origin i.origin i.declarationName | return none
      let some args ← all i.arguments | return none
      return some (base ++ "<" ++ ", ".intercalate args ++ ">")
    let some home := s.sources.findIdx? (·.module.name == m) | return none
    spellName origin home n
  | .applied n args => return (← all args).map fun a => n ++ "<" ++ ", ".intercalate a ++ ">"
  | .arrow a b =>
    let (some a, some b) := (← spell origin a, ← spell origin b) | return none
    return some ("(" ++ a ++ ") -> " ++ b)
  | .row fields =>
    let some types ← all (fields.map (·.2)) | return none
    return some ("{" ++ ", ".intercalate ((fields.zip types).map fun ((n, _), t) => n ++ ": " ++ t) ++ "}")
  | .overlay a b =>
    let (some a, some b) := (← spell origin a, ← spell origin b) | return none
    return some (a ++ " with " ++ b)

/-- The source modules a type names (an instance: its declaration's and its arguments'), each once, in order. -/
partial def modulesOf (g : GType) : M (List String) := do
  match g with
  | .atom _ => return []
  | .named m n _ =>
    let s ← get
    if m != s.generatedModule then return [m]
    let some i := (s.instanceByName[n]?).bind (s.instances[·]?) | return []
    let home ← originModule i.origin
    return (home.name :: (← i.arguments.mapM modulesOf).flatten).eraseDups
  | .applied _ args => return (← args.mapM modulesOf).flatten.eraseDups
  | .arrow a b | .overlay a b => return ((← modulesOf a) ++ (← modulesOf b)).eraseDups
  | .row fields => return (← fields.mapM fun (_, t) => modulesOf t).flatten.eraseDups

/-- The item type of a `List<X>` or `Relation<X>`: an instance of a one-parameter sum named `List`
with the cases `nil` and `cons`, or named `Relation` with the one case `rows` (the library's, or a
package's own of that shape). -/
def entriesItem (g : GType) : M (Option GType) := do
  let .named m n _ := g | return none
  let s ← get
  if m != s.generatedModule then return none
  let some i := (s.instanceByName[n]?).bind (s.instances[·]?) | return none
  let [x] := i.arguments | return none
  let home ← originModule i.origin
  let some d := s.byName[(home.name, i.declarationName)]? | return none
  let .sum _ cases [_] _ := d.ast | return none
  let labels := cases.map (·.name)
  if (i.declarationName == "List" && labels == ["nil", "cons"]) ||
     (i.declarationName == "Relation" && labels == ["rows"]) then return some x
  return none

/-- The row type of a relation (`Relation<X>`: the one-case sum `rows`), as `entriesItem`
recognises it. -/
def relationItem (g : GType) : M (Option GType) := do
  let .named m n _ := g | return none
  let s ← get
  if m != s.generatedModule then return none
  let some i := (s.instanceByName[n]?).bind (s.instances[·]?) | return none
  let [x] := i.arguments | return none
  let home ← originModule i.origin
  let some d := s.byName[(home.name, i.declarationName)]? | return none
  let .sum _ cases [_] _ := d.ast | return none
  if i.declarationName == "Relation" && cases.map (·.name) == ["rows"] then return some x
  return none

def derivedRefusal (module message : String) (tag := "derived-edits") : String :=
  "refused (" ++ tag ++ "): " ++ message ++ " (module " ++ module ++ ")"

/-- A derivation refusal at the source line that occasions it (KERNEL-HANDOFF §16 item 9). -/
def derivedAt {α : Type} (module : String) (span : Span) (message : String) (tag := "derived-edits") : M α :=
  throwThe Refusal (refusalAt module span (derivedRefusal module message tag))

/-- The State record's fields and the module they are written in. -/
def stateFields (index : Nat) (ast : ObjectiveBendSurface.Module) :
    M (Option (List ObjectiveBendSurface.Field × Nat × Span)) := do
  for d in ast.decls do
    match d with
    | .record "State" _ fields span => return some (fields, index, span)
    | .typeAlias "State" _ span =>
      let .named m n _ ← typeOf maxNesting index [] "State" | return none
      let some home := (← get).sources.findIdx? (·.module.name == m) | return none
      let some declaration := (← get).byName[(m, n)]? | return none
      let .record _ _ fields _ := declaration.ast | return none
      return some (fields, home, span)
    | _ => pure ()
  return none

/-! A `fixed` State field is named by no edit: the fields each `world.write(...)` (and so each
`write {...}`) names, from its argument record or the fields it extends `keep()` with. -/

/-- Whether a callee is `world.write` (or `world.write::<E>`). -/
def isWorldWrite : Expr → Bool
  | .member (.var "world" _) "write" _ => true
  | .specialize (.member (.var "world" _) "write" _) _ _ => true
  | _ => false

def editFields : List Expr → List String
  | [.extend _ fields _] | [.record fields _] => fields.map (·.1)
  | _ => []

/-- The fields a write over `keep()` names (`write {...}`, `world.write(extend(keep(), {...}))`): a State's edits by
name, unlike a record `world.write` takes whole (a cell's `{field, before, after}`). -/
def keptFields : List Expr → List String
  | [.extend _ fields _] => fields.map (·.1)
  | _ => []

mutual
def writtenFields : Expr → List String
  | .call c args _ => (if isWorldWrite c then editFields args else []) ++ writtenFields c ++ writtenList args
  | .record fs _ => writtenFieldList fs
  | .extend i fs _ => writtenFields i ++ writtenFieldList fs
  | .member t _ _ | .specialize t _ _ | .dataOf _ t _ | .worldCall _ _ _ t _ => writtenFields t
  | .compose specs _ => writtenList specs
  | .fix a b _ | .binary _ a b _ | .letE _ _ a b _ => writtenFields a ++ writtenFields b
  | .lambda _ _ b _ | .extensionValue _ _ b _ => writtenFields b
  | .ite c t f _ => writtenFields c ++ writtenFields t ++ writtenFields f
  | _ => []
def writtenFieldList : List (String × Expr) → List String
  | [] => []
  | (_, v) :: rest => writtenFields v ++ writtenFieldList rest
def writtenList : List Expr → List String
  | [] => []
  | e :: rest => writtenFields e ++ writtenList rest
end

mutual
/-- `writtenFields` of the writes over `keep()` alone (`keptFields`). -/
def keptWritten : Expr → List String
  | .call c args _ => (if isWorldWrite c then keptFields args else []) ++ keptWritten c ++ keptList args
  | .record fs _ => keptFieldList fs
  | .extend i fs _ => keptWritten i ++ keptFieldList fs
  | .member t _ _ | .specialize t _ _ | .dataOf _ t _ | .worldCall _ _ _ t _ => keptWritten t
  | .compose specs _ => keptList specs
  | .fix a b _ | .binary _ a b _ | .letE _ _ a b _ => keptWritten a ++ keptWritten b
  | .lambda _ _ b _ | .extensionValue _ _ b _ => keptWritten b
  | .ite c t f _ => keptWritten c ++ keptWritten t ++ keptWritten f
  | _ => []
def keptFieldList : List (String × Expr) → List String
  | [] => []
  | (_, v) :: rest => keptWritten v ++ keptFieldList rest
def keptList : List Expr → List String
  | [] => []
  | e :: rest => keptWritten e ++ keptList rest
end

mutual
def bodyWritten : Body → List String
  | .expr e _ => writtenFields e
  | .cases sc branches _ => writtenFields sc ++ branchesWritten branches
  | .letB _ _ v b _ => writtenFields v ++ bodyWritten b
def branchesWritten : List (ObjectiveBendSurface.Pattern × Body × Span) → List String
  | [] => []
  | (_, b, _) :: rest => bodyWritten b ++ branchesWritten rest
end

def declWritten : Decl → List String
  | .function _ _ b _ | .extension _ _ _ b _ _ => bodyWritten b
  | .spec sp => sp.methods.flatMap (bodyWritten ·.body)
  | _ => []

mutual
def bodyKept : Body → List String
  | .expr e _ => keptWritten e
  | .cases sc branches _ => keptWritten sc ++ branchesKept branches
  | .letB _ _ v b _ => keptWritten v ++ bodyKept b
def branchesKept : List (ObjectiveBendSurface.Pattern × Body × Span) → List String
  | [] => []
  | (_, b, _) :: rest => bodyKept b ++ branchesKept rest
end

/-- The State fields a declaration's writes over `keep()` name. -/
def declKept : Decl → List String
  | .function _ _ b _ | .extension _ _ _ b _ _ => bodyKept b
  | .spec sp => sp.methods.flatMap (bodyKept ·.body)
  | _ => []

/-- The State a module's writes edit: its own, or in a layer that declares none, the State of
the module it is a layer over (its `Super`), as far down as the stack goes. -/
def effectiveStateFields : Nat → Nat → M (Option (List ObjectiveBendSurface.Field × Nat × Span))
  | 0, _ => return none
  | fuel + 1, index => do
    let some source := (← get).sources[index]? | return none
    match ← tryCatch (stateFields index source.ast) (fun _ => pure none) with
    | some found => return some found
    | none =>
      if source.ast.layerOver.isNone then return none
      let some below := (source.module.imports.find? (·.importAlias == "Super")).map (·.target) | return none
      effectiveStateFields fuel below

/-- The fields of the State module `index` edits whose resolved type is a relation: what
`write {f: remove KEY}` retracts by key (`ObjectiveBendParse.lowerRemove`). The State and the
field's type are resolved first, so an alias of either does not change the meaning. -/
def relationFields (index : Nat) : M (List String) := do
  let some (fields, home, _) ← effectiveStateFields (← get).sources.size index | return []
  fields.filterMapM fun f => do
    let some g ← tryCatch (some <$> typeOf maxNesting home [] f.type) (fun _ => pure none) | return none
    return if (← relationItem g).isSome then some f.name else none

/-- Refuse a write that names a fixed field of the State module `index` edits, or a field it does not have: every
unknown name at once, with the State's own fields and where a layer keeps a value of its own (playtest 5: a layer's
`write {warmth: add 1n}` over a record was refused as an uninferred type argument, one error at a time). -/
def checkFixed (index : Nat) : M Unit := do
  let some source := (← get).sources[index]? | return
  let some (fields, home, _) ← effectiveStateFields (← get).sources.size index | return
  let names := fields.map (·.name)
  let unknown := source.ast.decls.flatMap fun d => (declKept d).filter (!names.contains ·) |>.map (·, d.span)
  if let some (_, at_) := unknown.head? then
    let owner := (((← get).sources[home]?).map (·.module.name)).getD source.module.name
    let layered := if home == index then "" else
      "; a layer keeps the State of the one beneath it, so a value of its own lives in a field it has: a number or a word in " ++
      "vars (Scenes.Var, as kind/counter keeps its count), a line by Super.inscribe"
    derivedAt source.module.name at_ ("write names no field of the State (" ++ owner ++ "'s): " ++
      ", ".intercalate (unknown.map (·.1)).eraseDups ++ "; its fields: " ++ ", ".intercalate names ++ layered) "unknown-field"
  let fixed := (fields.filter (·.fixed)).map (·.name)
  if fixed.isEmpty then return
  for d in source.ast.decls do
    for name in declWritten d do
      if fixed.contains name then
        derivedAt source.module.name d.span (name ++ " is fixed; no edit names it") "fixed"

/-- The derived `Edits` and `keep()` of module `index`, when it gets them. -/
def deriveEdits (index : Nat) : M (Option (List Decl)) := do
  let some source := (← get).sources[index]? | return none
  let ast := source.ast
  let some plans := (ast.imports.find? (·.path.endsWith "Plan.obend")).map (·.importAlias) | return none
  if ast.decls.any (fun d => d.name == "Edits" || d.name == "keep") then return none
  let some (fields, home, span) ← tryCatch (stateFields index ast) (fun _ => pure none) | return none
  let module := source.module.name
  let mut lines : Array String := #[]
  let mut keeps : Array String := #[]
  -- Every field whose type names a module this one does not import, with those modules: refused once, all named.
  let mut lacking : Array (String × Span × List String) := #[]
  for f in fields do
    if f.fixed then continue
    let some g ← tryCatch (some <$> typeOf maxNesting home [] f.type) (fun _ => pure none) | return none
    let spelled ← if g == .atom "Nat" then pure (some ("Edit", "Nat, Nat")) else
      match ← entriesItem g with
      | some x => pure ((← spell index x).map fun x => ("Entries", x ++ ", " ++ x))
      | none => pure ((← if home == index then pure (some f.type) else spell index g).map fun t => ("Edit", t ++ ", {}"))
    let some (sum, args) := spelled | do
      let named ← modulesOf g
      lacking := lacking.push (f.name, f.span, named.filter fun m => m != module && !source.module.imports.any (·.moduleName == m))
      continue
    let name := if ObjectiveBendParse.isIdent f.name.toList then f.name else (toJson f.name).compress
    lines := lines.push ("  " ++ name ++ ": " ++ plans ++ "." ++ sum ++ "<" ++ args ++ ">\n")
    keeps := keeps.push (name ++ ": " ++ plans ++ "." ++ sum ++ "::<" ++ args ++ ">.keep({})")
  if let some (_, at_, _) := lacking[0]? then
    let modules := (lacking.toList.flatMap (·.2.2)).eraseDups
    let sources := (← get).sources.toList
    let alias := fun (m : String) => (sources.findSome? fun x => (x.module.imports.find? (·.moduleName == m)).map (·.importAlias)).getD m
    let fieldsShown := ", ".intercalate (lacking.toList.map fun (n, _, ms) => "State." ++ n ++ (if ms.isEmpty then "" else " (" ++ ", ".intercalate ms ++ ")"))
    derivedAt module at_ ("the State's fields hold types from modules " ++ module ++ " does not import: " ++ fieldsShown ++
      "; add " ++ "; ".intercalate (modules.map fun m => "import ./" ++ m ++ ".obend as " ++ alias m))
  let text := "record Edits:\n" ++ String.join lines.toList ++ "def keep() -> Edits:\n  {" ++
    ", ".intercalate keeps.toList ++ "}\n"
  match ObjectiveBendParse.parseObjective text with
  | .ok parsed => return some (parsed.decls.map (·.mapSpans fun _ => span))
  | .error d => derivedAt module span ("State does not derive its Edits: " ++ d.message)

/-! ## The pass -/

/-- The pass's state over `sources`, before any module is rewritten. -/
def initialState (sources : Array Source) : Except String State := do
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
    sealedIdentities := sealedIdentities.push (Delvetalk.Compiler.Sha256.hexString
      (toJson [toJson source.module.name, toJson source.module.sha256, toJson imports]).compress)
  let byName := declarations.foldl (fun (map : Std.HashMap (String × String) Declaration) d =>
    match sources[d.origin]? with
    | some source => if map.contains (source.module.name, d.name) then map else map.insert (source.module.name, d.name) d
    | none => map) {}
  return { sources, sealedIdentities, generatedModule := "", generatedAlias := "", aliases := [], names, byName }

/-- The generated module's name and alias and every module's alias, drawn first. -/
def preamble : M Unit := do
  let moduleName ← fresh
  let moduleAlias ← fresh
  let mut aliases := []
  for source in (← get).sources do aliases := aliases ++ [(← fresh, source.module.name)]
  modify fun s => { s with generatedModule := moduleName, generatedAlias := moduleAlias, aliases }

/-! ## Form blocks: the method's input and `forms()` (KERNEL-HANDOFF §16 item 8c)

`form plant as planting:` declares, beside the Form value the parser wrote in place, the record
`PlantInput` of its fields (`text` and `source` a String, `natural` a Nat, `a | b | c` the
closed sum `PlantColour` of those empty cases, `T` the closed sum `T` names, offered as a choice
of its labels), and, when the module declares form blocks and no `forms()`,
`def forms() -> L.List<F.Form>` of the blocks' values in source order. -/

/-- The labels of the closed sum of empty cases `type` names in module `index`. -/
def closedLabels (index : Nat) (module action field type : String) (span : Span) : M (List String) := do
  let refusal := refusalAt module span (derivedRefusal module ("form " ++ action ++ " offers " ++ field ++ ": " ++ type ++
    ", which is not a closed sum of empty cases") "form-kind")
  let some g ← tryCatch (some <$> typeOf maxNesting index [] type) (fun _ => pure none) | throwThe Refusal refusal
  let .named m n _ := g | throwThe Refusal refusal
  if m == (← get).generatedModule then throwThe Refusal refusal
  let some declaration := (← get).byName[(m, n)]? | throwThe Refusal refusal
  let .sum _ cases [] _ := declaration.ast | throwThe Refusal refusal
  unless cases.all (fun c => trim c.type == "{}") do throwThe Refusal refusal
  return cases.map (·.name)

structure DerivedForms where
  decls : List Decl := []
  /-- The labels of each closed sum a form field names, by its text. -/
  labels : List (String × List String) := []
  forms : List ObjectiveBendSurface.FormBlock := []
  deriving Inhabited

def deriveForms (index : Nat) : M DerivedForms := do
  let some source := (← get).sources[index]? | return {}
  let ast := source.ast
  if ast.forms.isEmpty then return {}
  let module := source.module.name
  let some formAlias := (ast.imports.find? (·.path.endsWith "Form.obend")).map (·.importAlias) | return {}
  let mut text := ""
  let mut labels : List (String × List String) := []
  let mut forms : Array ObjectiveBendSurface.FormBlock := #[]
  for block in ast.forms do
    let mut fields : Array String := #[]
    let mut resolved : Array ObjectiveBendSurface.FormField := #[]
    for f in block.fields do
      let (type, kind) ← match f.kind with
        | .text .. | .object .. | .source => pure ("String", f.kind)
        | .natural .. => pure ("Nat", f.kind)
        | .choice options =>
          let sum := block.choiceSum f.name
          if let some clash := ast.decls.find? (·.name == sum) then
            derivedAt module clash.span ("form " ++ block.action ++ " declares the sum " ++ sum ++ " of " ++ f.name ++
              "'s choices, and so does the module; delete it or name an existing sum: " ++ f.name ++ ": " ++ sum) "form-input"
          text := text ++ "sum " ++ sum ++ ":\n" ++ String.join (options.map ("  " ++ · ++ ": {}\n"))
          pure (sum, f.kind)
        | .named type =>
          let options ← closedLabels index module block.action f.name type f.span
          labels := (type, options) :: labels
          pure (type, .choice options)
      fields := fields.push ("  " ++ f.name ++ ": " ++ type ++ "\n")
      resolved := resolved.push { f with kind }
    if let some clash := ast.decls.find? (·.name == block.input) then
      derivedAt module clash.span ("form " ++ block.action ++ " declares " ++ block.input ++
        ", its method's input, and so does the module; delete it") "form-input"
    text := text ++ (if fields.isEmpty then "type " ++ block.input ++ " = {}\n"
      else "record " ++ block.input ++ ":\n" ++ String.join fields.toList)
    forms := forms.push { block with fields := resolved.toList }
  -- A hand-written forms() beside the blocks is refused: the host validates a direct action
  -- against forms() alone, so one that omits or loosens a block would drop its bounds.
  if let some own := ast.decls.find? (·.name == "forms") then
    derivedAt module own.span ("forms() is derived from the form blocks, whose bounds the host checks " ++
      "through it; a hand-written one beside them could drop a block: delete it") "derived-forms"
  let some lists := (ast.imports.find? (fileOf ·.path == "List.obend")).map (·.importAlias)
    | derivedAt module ((ast.forms.head?.map (·.span)).getD default) "forms() is derived as a List of the form blocks' values; import ./List.obend" "derived-forms"
  let list := ast.forms.foldr (fun b acc => lists ++ ".List.cons({head: " ++ b.value ++ "(), tail: " ++ acc ++ "})")
    (lists ++ ".List.nil({})")
  text := text ++ "def forms() -> " ++ lists ++ ".List<" ++ formAlias ++ ".Form>:\n  " ++ list ++ "\n"
  match ObjectiveBendParse.parseObjective text with
  | .ok parsed =>
    let span := (ast.forms.head?.map (·.span)).getD default
    return { decls := parsed.decls.map (·.mapSpans fun _ => span), labels, forms := forms.toList }
  | .error d => derivedAt module ((ast.forms.head?.map (·.span)).getD default) ("form blocks do not derive their inputs: " ++ d.message) "form-input"

/-- A form field's closed-sum marker as its choice of labels. -/
def resolveChoices (labels : List (String × List String)) : Expr → Expr
  | e@(.call (.var m _) [.str formAlias _, .str type _] span) =>
    if m == ObjectiveBendParse.formChoiceMarker then
      match labels.lookup type with
      | some options => ObjectiveBendParse.choiceKind formAlias options span
      | none => e
    else e
  | e => e

/-- Each module's derived declarations (`Edits`, `keep()`, form inputs, `forms()`; empty where
it gets none) and form blocks. Types are resolved in a pass of their own whose state is dropped. -/
def derivedDecls (sources : Array Source) : Except Refusal (Array (List Decl × DerivedForms × List String)) := do
  let probe : M (Array (List Decl × DerivedForms × List String)) := do
    preamble
    let mut out := #[]
    for index in [:sources.size] do
      checkFixed index
      let edits := (← deriveEdits index).getD []
      let forms ← deriveForms index
      -- The canonical order: `forms()`, then `Edits` and `keep()`, then the form inputs. A
      -- module that writes `forms()` at its end (its `Edits` and inputs derived) is this order.
      let (functions, types) := forms.decls.partition (· matches .function ..)
      out := out.push (functions ++ edits ++ types, forms, ← relationFields index)
    return out
  return (← probe.run (← initialState sources)).1

/-- Rewrite one declaration of module `index`, every refusal placed at the declaration unless
it names a span of its own. -/
def rewriteTop (site : Site) (d : Decl) : M Decl := do
  modify fun s => { s with current := (site.target, d.name) }
  tryCatchThe Refusal (rewriteDecl maxNesting site [] d) fun e =>
    throwThe Refusal (if e.span.isSome then e else { e with module := some site.target, span := some d.span })

def run (sources : Array Source) : Except Refusal Output := do
  if !sources.any (fun s => s.ast.decls.any declGenerics) then
    let modules ← sources.toList.mapM fun source =>
      ObjectiveBendElaborate.ofSurface source.module.name source.module.aliases source.ast
    return ⟨modules, Json.arr #[]⟩
  -- Derived declarations end their module and are specialized after every module's own, so
  -- they number no instance before one the package spells (no other entry's packet moves).
  let found ← derivedDecls sources
  let derived := found.map (·.1)
  let sources := sources.mapIdx fun i source =>
    let (own, forms, relations) := found[i]!
    let decls := if forms.labels.isEmpty then source.ast.decls
      else source.ast.decls.map (·.mapExpr (resolveChoices forms.labels))
    -- `write {f: remove v}`: a retract on a relation field of the resolved State, else removeItem.
    let plans := ((source.ast.imports.find? (·.path.endsWith "Plan.obend")).map (·.importAlias)).getD "Plans"
    let decls := decls.map (·.mapExpr (ObjectiveBendParse.lowerRemove plans relations))
    let blocks := if forms.forms.isEmpty then source.ast.forms else forms.forms
    let ast : ObjectiveBendSurface.Module := { source.ast with decls := decls ++ own, forms := blocks }
    { source with ast }
  let initial ← initialState sources
  let action : M Output := do
    preamble
    let s ← get
    let (moduleName, moduleAlias, aliases) := (s.generatedModule, s.generatedAlias, s.aliases)
    let mut rewritten : List (String × ObjectiveBendSurface.Module) := []
    for index in [:sources.size] do
      let source := sources[index]!
      let site : Site := { origin := index, target := source.module.name, bindings := [], lifted := false }
      let mut ordinary : Array Decl := #[]
      for d in source.ast.decls.take (source.ast.decls.length - derived[index]!.length) do
        if (d matches .typeAlias ..) || !d.typeParameters.isEmpty then continue
        ordinary := ordinary.push (← rewriteTop site d)
      rewritten := rewritten ++ [(source.module.name, { source.ast with decls := ordinary.toList })]
    for index in [:sources.size] do
      if derived[index]!.isEmpty then continue
      let source := sources[index]!
      let site : Site := { origin := index, target := source.module.name, bindings := [], lifted := false }
      let own ← (derived[index]!.filter fun d => !(d matches .typeAlias ..)).mapM (rewriteTop site)
      rewritten := rewritten.set index (source.module.name, { source.ast with
        decls := (rewritten[index]!.2.decls) ++ own })
    let state ← get
    let generated : ObjectiveBendSurface.Module := { imports := [], decls := state.instances.toList.filterMap (·.ast) }
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
