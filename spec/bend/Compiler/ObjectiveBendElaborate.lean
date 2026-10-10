/- Objective Bend surface → Core4 elaboration: THE elaborator.

Reads the `Compiler.ObjectiveBendSurface` AST that `Compiler.ObjectiveBendParse`
produces (`ofSurface`) and emits the Core4 term and its lambda/inject typing proposals. It was
ported from the retired TypeScript elaborator and translation-validated against
it until that elaborator was deleted (docs/OBJECTIVE-BEND-FRONTEND.md,
"Provenance"). What is proved of its output once the checker accepts it is in
`Compiler.ObjectiveBendFrontEndAdequacy`; "surface meaning preserved" needs a
surface semantics, which does not exist. All recursion is fuel-bounded; running
out of fuel is a refusal, never a guess. -/
import Lean
import Compiler.ObjectiveBendParse
import Compiler.ObjectiveBendSurface
import Compiler.ObjectiveBendLaw
import Std.Data.HashMap
import Std.Data.HashSet
import Theory.ObjectiveBendOpenRecursion
import Compiler.ObjectiveBendC4
import Compiler.ObjectiveBendContract
namespace Minidregg.Compiler.ObjectiveBendElaborate
open Lean
set_option autoImplicit false

abbrev CoreTerm := Minidregg.Theory.ObjectiveBendOpenRecursion.Term
abbrev CorePrimitive := Minidregg.Theory.ObjectiveBendOpenRecursion.Primitive
abbrev CoreUnaryPrimitive := Minidregg.Theory.ObjectiveBendOpenRecursion.UnaryPrimitive

/-! String helpers (ASCII whitespace, as the TS `trim`). -/
def isSpace (c : Char) : Bool := c == ' ' || c == '\t' || c == '\n' || c == '\r'
def trimStart (s : String) : String := String.ofList (s.toList.dropWhile isSpace)
def trimEnd (s : String) : String := String.ofList ((s.toList.reverse.dropWhile isSpace).reverse)
def dropStr (s : String) (n : Nat) : String := String.ofList (s.toList.drop n)
def dropEndStr (s : String) (n : Nat) : String := String.ofList (s.toList.take (s.length - n))

/-! ## Surface AST -/

abbrev Param := ObjectiveBendSurface.Param

/-- Every node keeps the span of the surface node it was read from (an implicit field:
patterns never mention it), so a refusal can point at the source. -/
inductive Expr where
  | var (name : String) {span : ObjectiveBendSurface.Span}
  | nat (value : String) {span : ObjectiveBendSurface.Span}
  | bool (value : Bool) {span : ObjectiveBendSurface.Span}
  | str (value : String) {span : ObjectiveBendSurface.Span}
  | unit {span : ObjectiveBendSurface.Span}
  | record (fields : List (String × Expr)) {span : ObjectiveBendSurface.Span}
  | extend (inherited : Expr) (fields : List (String × Expr)) {span : ObjectiveBendSurface.Span}
  | member (target : Expr) (name : String) {span : ObjectiveBendSurface.Span}
  | call (callee : Expr) (args : List Expr) {span : ObjectiveBendSurface.Span}
  | compose (specs : List Expr) {span : ObjectiveBendSurface.Span}
  | fix (spec inherited : Expr) {span : ObjectiveBendSurface.Span}
  | closure (params : List Param) (resultType : String) (body : Expr) {span : ObjectiveBendSurface.Span}
  | binary (op : String) (left right : Expr) {span : ObjectiveBendSurface.Span}
  | ite (condition whenTrue whenFalse : Expr) {span : ObjectiveBendSurface.Span}
  /-- `let name: type = value in body` (type `_` when unannotated). -/
  | letE (name type : String) (value body : Expr) {span : ObjectiveBendSurface.Span}
  /-- `Data.of::<T>(value)` (rewritten by the hosted front end): inject first-order
  data of type `T` into the universal type `Data`. -/
  | toData (type : String) (value : Expr) {span : ObjectiveBendSurface.Span}
  /-- `world.METHOD::<T>(argument)` as the generics pass lowers it (`input`, `result` are
  the instantiated types as this module spells them): the perform of the message
  `{object: {world: "", object: "world"}, method, argument: Data}` at `result`. -/
  | worldCall (method input result : String) (argument : Expr) {span : ObjectiveBendSurface.Span}
  deriving Inhabited, Repr

def Expr.span : Expr → ObjectiveBendSurface.Span
  | @var _ s | @nat _ s | @bool _ s | @str _ s | @unit s | @record _ s | @extend _ _ s | @member _ _ s
  | @call _ _ s | @compose _ s | @fix _ _ s | @closure _ _ _ s | @binary _ _ _ s | @ite _ _ _ s
  | @letE _ _ _ _ s | @toData _ _ s | @worldCall _ _ _ _ s => s

abbrev Pattern := ObjectiveBendSurface.Pattern

inductive Body where
  | expr (e : Expr) {span : ObjectiveBendSurface.Span}
  /-- `armSpans` are the branches' own spans, in order. -/
  | cases (scrutinee : Expr) (branches : List (Pattern × Body)) {span : ObjectiveBendSurface.Span}
      {armSpans : List ObjectiveBendSurface.Span}
  /-- `let name: type = value` then the rest of the body. -/
  | letB (name type : String) (value : Expr) (body : Body) {span : ObjectiveBendSurface.Span}
  deriving Inhabited, Repr

def Body.span : Body → ObjectiveBendSurface.Span
  | @expr _ s | @cases _ _ s _ | @letB _ _ _ _ s => s

structure Method where
  name : String
  params : List Param
  resultType : String
  qualifier : String
  body : Body
  /-- The authored signature, for the interface label (`Surface.Method.signatureJson`). -/
  authored : ObjectiveBendSurface.Signature
  deriving Inhabited

structure Claim where
  name : String
  params : List Param
  body : Expr
  deriving Inhabited

structure Spec where
  name : String
  suffix : Bool
  parents : List String
  targetType : String
  requirements : List ObjectiveBendSurface.Signature
  methods : List Method
  claims : List Claim
  /-- `Self has {...}, Super has {...}` of an open spec (OB-LTUO LT2), "" for `spec S for T`. -/
  binders : String := ""
  deriving Inhabited

structure Signature where
  name : String
  params : List Param
  resultType : String
  deriving Inhabited

inductive Decl where
  | spec (s : Spec)
  | extension (name : String) (params : List Param) (targetType : String) (body : Body) (binders : String)
  | reexport (name target : String)
  | function (name : String) (params : List Param) (resultType : String) (body : Body)
  | record (name : String) (fields : List (String × String)) (methods : List Signature)
  | sum (name : String) (cases : List (String × String))
  deriving Inhabited

def Decl.name : Decl → String
  | .spec s => s.name | .extension n .. => n | .function n .. => n | .record n .. => n | .sum n .. => n | .reexport n .. => n

structure Module where
  name : String
  /-- (alias, imported module name) in source order. -/
  imports : List (String × String)
  decls : List Decl
  /-- The module's top-level enforced laws (`law NAME: EXPR`), in source order. They are not
  terms: the elaborator never sees them; the front end hands the entry module's to the artifact. -/
  laws : List (String × ObjectiveBendLaw.LawExpr) := []
  /-- `layer over ./X.obend`: the module this one is a layer over (its `Super`). -/
  layerOver : Option String := none
  /-- The module's protocols: name, then each method's name, type text and span. -/
  protocols : List (String × List (String × String × String × ObjectiveBendSurface.Span)) := []
  /-- `implements NAME` lines. -/
  implements : List (String × ObjectiveBendSurface.Span) := []
  /-- The module's `form` blocks (a field naming a closed sum resolved to its choice). -/
  forms : List ObjectiveBendSurface.FormBlock := []
  deriving Inhabited

/-! ## Reading the parsed surface -/

namespace Surface
open ObjectiveBendSurface

/-- A surface expression without its spans. `fuel` bounds the nesting read, as the AST
decoder did ("AST nesting capacity"). -/
def expr : Nat → ObjectiveBendSurface.Expr → Except String Expr
  | 0, _ => .error "AST nesting capacity"
  | fuel + 1, e => do
    let fields := fun (fs : List (String × ObjectiveBendSurface.Expr)) =>
      fs.mapM fun (n, v) => do return (n, ← expr fuel v)
    match e with
    | .var n s => return .var n (span := s)
    | .nat v s => return .nat v (span := s)
    | .bool v s => return .bool v (span := s)
    | .str v s => return .str v (span := s)
    | .unit s => return .unit (span := s)
    | .record fs s => return .record (← fields fs) (span := s)
    | .extend i fs s => return .extend (← expr fuel i) (← fields fs) (span := s)
    | .member t n s => return .member (← expr fuel t) n (span := s)
    | .call c args s => return .call (← expr fuel c) (← args.mapM (expr fuel)) (span := s)
    | .compose specs s => return .compose (← specs.mapM (expr fuel)) (span := s)
    | .fix spec inherited s => return .fix (← expr fuel spec) (← expr fuel inherited) (span := s)
    | .extensionValue ps t b s => return .closure ps t (← expr fuel b) (span := s)
    | .lambda ps r b s => return .closure ps r (← expr fuel b) (span := s)
    | .binary op l r s => return .binary op (← expr fuel l) (← expr fuel r) (span := s)
    | .ite c t f s => return .ite (← expr fuel c) (← expr fuel t) (← expr fuel f) (span := s)
    | .letE n t v b s => return .letE n t (← expr fuel v) (← expr fuel b) (span := s)
    | .dataOf t v s => return .toData t (← expr fuel v) (span := s)
    | .worldCall method i r a s => return .worldCall method i r (← expr fuel a) (span := s)
    | .specialize .. => .error "unknown AST expression specialize"

def body : Nat → ObjectiveBendSurface.Body → Except String Body
  | 0, _ => .error "AST nesting capacity"
  | fuel + 1, b => do
    match b with
    | .expr e s => return .expr (← expr fuel e) (span := s)
    | .cases sc branches s =>
      let arms ← branches.mapM fun (p, b, _) => do return (p, ← body fuel b)
      return .cases (← expr fuel sc) arms (span := s) (armSpans := branches.map (·.2.2))
    | .letB n t v rest s => return .letB n t (← expr fuel v) (← body fuel rest) (span := s)

def signature (s : ObjectiveBendSurface.Signature) : Signature := ⟨s.name, s.params, s.resultType⟩

def decl (d : ObjectiveBendSurface.Decl) : Except String Decl := do
  let fuel := 4096
  match d with
  | .spec sp =>
    let methods ← sp.methods.mapM fun m => do
      return Method.mk m.signature.name m.signature.params m.signature.resultType m.qualifier
        (← body fuel m.body) m.signature
    let claims ← sp.claims.mapM fun c => do return Claim.mk c.name c.params (← expr fuel c.body)
    return .spec (Spec.mk sp.name sp.suffix sp.parents sp.targetType sp.requirements methods claims (sp.binders.getD ""))
  | .extension n ps t b binders _ => return .extension n ps t (← body fuel b) (binders.getD "")
  | .function sig _ b _ => return .function sig.name sig.params sig.resultType (← body fuel b)
  | .record n methods fields _ => return .record n (fields.map fun f => (f.name, f.type)) (methods.map signature)
  | .reexport n t _ => return .reexport n t
  | .sum n cases _ _ => return .sum n (cases.map fun c => (c.name, c.type))
  | other => .error ("unknown AST declaration " ++ other.kind)

end Surface

/-- A parsed module, its import aliases resolved to module names: what the elaborator reads.
Top-level laws are parsed into their enforced form and set aside (`Module.laws`). -/
def ofSurface (name : String) (imports : List (String × String)) (m : ObjectiveBendSurface.Module) :
    Except String Module := do
  let mut decls : List Decl := []
  let mut laws : List (String × ObjectiveBendLaw.LawExpr) := []
  let mut protocols : List (String × List (String × String × String × ObjectiveBendSurface.Span)) := []
  for d in m.decls do
    if let .law lawName source _ _ := d then
      laws := laws ++ [(lawName, ← ObjectiveBendLaw.parse source)]
    else if let .protocol name methods shown _ := d then
      protocols := protocols ++ [(name, (methods.zip (shown ++ methods.map (·.type))).map fun (f, s) => (f.name, f.type, s, f.span))]
    else decls := decls ++ [← Surface.decl d]
  ObjectiveBendLaw.checkNames laws
  let layerOver := m.layerOver.bind fun _ => (imports.find? (·.1 == "Super")).map (·.2)
  return ⟨name, imports, decls, laws, layerOver, protocols, m.implements, m.forms⟩

/-! ## Proposal types (the `Ty` JSON wire of Theory.ObjectiveBendTyping.typeJson, plus `variant`) -/

inductive PTy where
  | natural | boolean | label | emptyRow
  | variable (index : Nat)
  | arrow (reuse parameter : String) (domain codomain : PTy)
  | field (name : String) (member tail : PTy)
  | specification (metadata extension : PTy)
  | prototype (spec target : PTy)
  | variant (row : PTy)
  | computation (plan response result : PTy)
  /-- The universal first-order type (hosted extension). -/
  | data
  deriving Inhabited, Repr, BEq, Hashable

def PTy.row : List (String × PTy) → PTy
  | [] => .emptyRow
  | (n, t) :: rest => .field n t (PTy.row rest)

def arrowTy (d c : PTy) (parameter := "unrestricted") (reuse := "reusable") : PTy := .arrow reuse parameter d c
def extensionTy (t : PTy) : PTy := arrowTy t (arrowTy t t)

def PTy.insertCanonical : PTy → String → PTy → PTy
  | .field prior old tail, name, member =>
    if name == prior then .field name member tail
    else if name < prior then .field name member (.field prior old tail)
    else .field prior old (tail.insertCanonical name member)
  | tail, name, member => .field name member tail

def PTy.canonical : PTy → PTy
  | .arrow r q d c => .arrow r q d.canonical c.canonical
  | .specification m e => .specification m.canonical e.canonical
  | .prototype s t => .prototype s.canonical t.canonical
  | .variant r => .variant r.canonical
  | .computation p r a => .computation p.canonical r.canonical a.canonical
  | .field n m t => t.canonical.insertCanonical n m.canonical
  | other => other

def sameTy : Option PTy → Option PTy → Bool
  | some a, some b => a.canonical == b.canonical
  | _, _ => false

def callable : Option PTy → Option PTy
  | some (.specification _ e) => callable (some e)
  | t => t

def lookupRow : Option PTy → String → Option PTy
  | some (.field n m t), name => if n == name then some m else lookupRow (some t) name
  | _, _ => none

/-- Member reads may use a declared lower bound without equating its abstract
    Self/Super variable with that row. Mirrors the core checker's bounded lookup. -/
def lookupRowBounded (bounds : List (Nat × PTy)) : Nat → Option PTy → String → Option PTy
  | 0, _, _ => none
  | fuel + 1, some (.field n member tail), name =>
    if n == name then some member else lookupRowBounded bounds fuel (some tail) name
  | fuel + 1, some (.variable index), name =>
    lookupRowBounded bounds fuel (bounds.lookup index) name
  | _, _, _ => none

def PTy.json : PTy → Json
  | .natural => Json.mkObj [("tag", "natural")]
  | .boolean => Json.mkObj [("tag", "boolean")]
  | .label => Json.mkObj [("tag", "label")]
  | .emptyRow => Json.mkObj [("tag", "emptyRow")]
  | .variable i => Json.mkObj [("tag", "variable"), ("index", toString i)]
  | .arrow r q d c => Json.mkObj [("tag", "arrow"), ("reuse", r), ("parameter", q), ("domain", d.json), ("codomain", c.json)]
  | .field n m t => Json.mkObj [("tag", "field"), ("name", n), ("member", m.json), ("tail", t.json)]
  | .specification m e => Json.mkObj [("tag", "specification"), ("metadata", m.json), ("extension", e.json)]
  | .prototype s t => Json.mkObj [("tag", "prototype"), ("spec", s.json), ("target", t.json)]
  | .variant r => Json.mkObj [("tag", "variant"), ("row", r.json)]
  | .computation p r a => Json.mkObj [("tag", "computation"), ("plan", p.json), ("response", r.json), ("result", a.json)]
  | .data => Json.mkObj [("tag", "data")]

def isComputation : Option PTy → Bool
  | some (.computation ..) => true
  | _ => false

/-! ## Annotated core -/

structure Proposal where
  domain : Option PTy
  codomain : Option PTy
  parameter : String
  reuse : String
  reason : Option String := none
  deriving Inhabited

/-- Where elaborated code comes from: the module and declaration being elaborated and the
span of the surface node in that module's source. -/
structure Loc where
  module : String
  definition : String
  span : ObjectiveBendSurface.Span
  deriving Inhabited, Repr

inductive ATerm where
  /-- The term elaborated from the surface node at `loc`. Transparent: it renders, erases
  and annotates as its term, adds no checker position, and exists so that a refusal of the
  checker at a position can be traced back to the source (`ObjectiveBendBlame.locate`). -/
  | located (loc : Loc) (term : ATerm)
  | bound (index : Nat)
  | lam (proposal : Proposal) (body : ATerm)
  | app (fn arg : ATerm)
  | mix (lower upper : ATerm)
  | fix (spec seed : ATerm)
  | specification (metadata extension : ATerm)
  | prototype (spec target : ATerm)
  | reflect (value : ATerm) | metadata (value : ATerm) | project (value : ATerm)
  | nat (value : String) | boolean (value : Bool) | label (value : String)
  | binary (primitive : String) (left right : ATerm)
  | unary (primitive : String) (argument : ATerm)
  | extend (inherited : ATerm) (fields : List (String × ATerm))
  | record (fields : List (String × ATerm))
  | get (target : ATerm) (name : String)
  | ifZero (value zero successor : ATerm)
  | inject (label : String) (type : Option PTy) (reason : Option String) (payload : ATerm)
  | case (scrutinee : ATerm) (arms : List (String × ATerm))
  | ifBool (condition whenTrue whenFalse : ATerm)
  /-- Yield a Plan; carries the enclosing activity's Plan and Response types. -/
  | perform (plan response : PTy) (value : ATerm)
  /-- A pure tail of an activity body (inserted, never authored). -/
  | done (plan response : PTy) (value : ATerm)
  /-- `Data.of::<T>(value)`; `type` is the authored `T`. -/
  | toData (type : PTy) (value : ATerm)
  /-- `textJoin(list, separator)`. -/
  | textJoin (list separator : ATerm)
  /-- Refuse the turn, naming why; `type` is the activity type it stands in for. -/
  | refuse (type : PTy) (reason : String)
  deriving Inhabited

mutual
def ATerm.json : ATerm → Json
  | .located _ t => t.json
  | .bound i => Json.mkObj [("tag", "bound"), ("index", toJson i)]
  | .lam _ b => Json.mkObj [("tag", "lam"), ("body", b.json)]
  | .app f a => Json.mkObj [("tag", "app"), ("fn", f.json), ("arg", a.json)]
  | .mix l u => Json.mkObj [("tag", "mix"), ("lower", l.json), ("upper", u.json)]
  | .fix s i => Json.mkObj [("tag", "fix"), ("spec", s.json), ("seed", i.json)]
  | .specification m e => Json.mkObj [("tag", "specification"), ("metadata", m.json), ("extension", e.json)]
  | .prototype s t => Json.mkObj [("tag", "prototype"), ("spec", s.json), ("target", t.json)]
  | .reflect v => Json.mkObj [("tag", "reflect"), ("value", v.json)]
  | .metadata v => Json.mkObj [("tag", "metadata"), ("value", v.json)]
  | .project v => Json.mkObj [("tag", "project"), ("value", v.json)]
  | .nat v => Json.mkObj [("tag", "nat"), ("value", v)]
  | .boolean v => Json.mkObj [("tag", "boolean"), ("value", toJson v)]
  | .label v => Json.mkObj [("tag", "label"), ("value", v)]
  | .unary p a => Json.mkObj [("tag", "unary"), ("primitive", p), ("argument", a.json)]
  | .binary p l r => Json.mkObj [("tag", "binary"), ("primitive", p), ("left", l.json), ("right", r.json)]
  | .extend i fs => Json.mkObj [("tag", "extend"), ("inherited", i.json), ("fields", fieldsJson fs)]
  | .record fs => Json.mkObj [("tag", "record"), ("fields", fieldsJson fs)]
  | .get t n => Json.mkObj [("tag", "get"), ("target", t.json), ("name", n)]
  | .ifZero v z s => Json.mkObj [("tag", "ifZero"), ("value", v.json), ("zero", z.json), ("successor", s.json)]
  | .inject l _ _ p => Json.mkObj [("tag", "inject"), ("label", l), ("payload", p.json)]
  | .case s arms => Json.mkObj [("tag", "case"), ("scrutinee", s.json), ("arms", armsJson arms)]
  | .ifBool c t f => Json.mkObj [("tag", "ifBool"), ("condition", c.json), ("whenTrue", t.json), ("whenFalse", f.json)]
  | .perform _ _ v => Json.mkObj [("tag", "perform"), ("plan", v.json)]
  | .done _ _ v => Json.mkObj [("tag", "done"), ("value", v.json)]
  | .toData _ v => Json.mkObj [("tag", "toData"), ("value", v.json)]
  | .textJoin l s => Json.mkObj [("tag", "textJoin"), ("list", l.json), ("separator", s.json)]
  | .refuse _ r => Json.mkObj [("tag", "refuse"), ("reason", r)]
def fieldsJson : List (String × ATerm) → Json
  | fs => Json.arr (fieldsArray fs).toArray
def fieldsArray : List (String × ATerm) → List Json
  | [] => []
  | (n, v) :: rest => Json.mkObj [("name", n), ("value", v.json)] :: fieldsArray rest
def armsJson : List (String × ATerm) → Json
  | arms => Json.arr (armsArray arms).toArray
def armsArray : List (String × ATerm) → List Json
  | [] => []
  | (l, b) :: rest => Json.mkObj [("label", l), ("body", b.json)] :: armsArray rest
end

/-- Erasure to the Core4 `Term` the checker and demand machine consume. -/
def primitiveOf : String → Except String CorePrimitive
  | "add" => .ok .add | "multiply" => .ok .multiply | "equal" => .ok .equal | "conjunction" => .ok .conjunction
  | "labelEqual" => .ok .labelEqual
  | "subtract" => .ok .subtract | "divide" => .ok .divide | "less" => .ok .less | "lessEqual" => .ok .lessEqual
  | "modulo" => .ok .modulo
  | "textConcat" => .ok .textConcat | "textTake" => .ok .textTake | "textDrop" => .ok .textDrop
  | "textSpan" => .ok .textSpan | "textBreak" => .ok .textBreak | "textHasAny" => .ok .textHasAny
  | "textCanonicalCompare" => .ok .textCanonicalCompare
  | other => .error ("primitive " ++ other ++ " is not a Core4 constructor yet")

def unaryPrimitiveOf : String → Except String CoreUnaryPrimitive
  | "natText" => .ok .natText | "textLength" => .ok .textLength
  | "sha256Text" => .ok .sha256Text
  | other => .error ("unknown hosted unary primitive " ++ other)

mutual
def ATerm.erase : ATerm → Except String CoreTerm
  | .located _ t => t.erase
  | .bound i => .ok (.bound i)
  | .lam _ b => return .lam (← b.erase)
  | .app f a => return .app (← f.erase) (← a.erase)
  | .mix l u => return .mix (← l.erase) (← u.erase)
  | .fix s i => return .fix (← s.erase) (← i.erase)
  | .specification m e => return .specification (← m.erase) (← e.erase)
  | .prototype s t => return .prototype (← s.erase) (← t.erase)
  | .reflect v => return .reflect (← v.erase)
  | .metadata v => return .metadata (← v.erase)
  | .project v => return .project (← v.erase)
  | .nat v => match v.toNat? with
    | some n => if toString n = v then .ok (.nat n) else .error "non-canonical natural"
    | none => .error "non-canonical natural"
  | .boolean v => .ok (.boolean v)
  | .label v => .ok (.label v)
  | .unary p a => return .unary (← unaryPrimitiveOf p) (← a.erase)
  | .binary p l r => return .binary (← primitiveOf p) (← l.erase) (← r.erase)
  | .extend i fs => return .extend (← i.erase) (← eraseFields fs)
  | .record fs => return .record (← eraseFields fs)
  | .get t n => return .get (← t.erase) n
  | .ifZero v z s => return .ifZero (← v.erase) (← z.erase) (← s.erase)
  | .inject l _ _ p => return .inject l (← p.erase)
  | .case sc arms => return .case (← sc.erase) (← eraseFields arms)
  | .ifBool c t f => return .ifBool (← c.erase) (← t.erase) (← f.erase)
  | .perform _ _ v => return .perform (← v.erase)
  | .done _ _ v => return .done (← v.erase)
  | .toData _ v => return .toData (← v.erase)
  | .textJoin l s => return .textJoin (← l.erase) (← s.erase)
  | .refuse _ r => return .refuse r
def eraseFields : List (String × ATerm) → Except String (List (String × CoreTerm))
  | [] => .ok []
  | (n, v) :: rest => return (n, ← v.erase) :: (← eraseFields rest)
end

/-! ## Elaboration state -/

structure Binding where
  name : String
  ty : Option PTy
  quantity : String
  deriving Inhabited

structure Ctx where
  /-- The user's modules. -/
  modules : List Module
  decls : List (String × Decl × Module)
  records : List (String × Decl)
  sums : List (String × Decl)
  /-- `decls`, `records` and `sums` by key (keys are distinct: `context` refuses duplicates). -/
  declIndex : Std.HashMap String (Decl × Module) := {}
  recordIndex : Std.HashMap String Decl := {}
  sumIndex : Std.HashMap String Decl := {}
  /-- A layer stack (the entry module and the modules it is `layer over`, transitively),
  bottom first; empty for an unlayered package. -/
  stack : Array String := #[]
  /-- Each declaration a layer above overrides, to the nearest overriding declaration. -/
  overrides : Std.HashMap String String := {}

/-- The record declared under `key`, as `records.find?` would return it. -/
def Ctx.record? (c : Ctx) (key : String) : Option (String × Decl) := (c.recordIndex[key]?).map (key, ·)
/-- The sum declared under `key`, as `sums.find?` would return it. -/
def Ctx.sum? (c : Ctx) (key : String) : Option (String × Decl) := (c.sumIndex[key]?).map (key, ·)

structure St where
  /-- Declaration types by knot key (the first recorded for a key stands). -/
  globalTypes : Std.HashMap String (Option PTy) := {}
  /-- Resolved source types, keyed by (module, text), for resolutions made outside any
  recursive unfolding (`seen = []`) and outside a template's `Self`/`Super` bindings. Once a
  recursive type is registered its variable is stable, so such a resolution is a function of
  its key; failures are not cached (their type errors are reported where they occur). -/
  typeMemo : Std.HashMap (String × String) PTy := {}
  inferring : List String := []
  typeErrors : Array String := #[]
  sumVariables : List (String × Nat) := []
  sumBounds : List (Nat × PTy) := []
  precedence : List (String × List String) := []
  linearizing : List String := []
  hidden : Array (String × ATerm × Option PTy) := #[]
  /-- Layer instances emitted so far: (spec key, inherited type JSON) ↦ knot field name. -/
  instances : List ((String × String) × String) := []
  /-- Source type names bound while a template is elaborated (`Self`, `Super`). -/
  typeBindings : List (String × PTy) := []
  /-- Per open declaration: its `Self` variable and its `Super` bound row. -/
  openBounds : List (String × (PTy × PTy)) := []
  /-- Per open declaration, in emission order: its key, its `Self` variable's index and its
  knot field (the template at its own bounds). The front end checks each once with that
  variable RIGID (`ObjectiveBendFrontEnd.checkTemplates`, D2). -/
  templates : List (String × List Nat × ATerm) := []
  /-- Each open declaration's template layer at its own bounds, elaborated ONCE: the knot field
  holds it (checked rigid) and every chain instance is `instantiate σ` of it. -/
  templateLayers : List (String × (Nat × Nat × ATerm)) := []
  /-- The declared result type of the body being lowered (for a `fix` in tail position). -/
  resultType : Option PTy := none
  /-- The target a `fix` about to be lowered must produce (tail position or annotated let). -/
  fixTarget : Option PTy := none
  /-- The Plan/Response of the activity being lowered (none outside one). -/
  effect : Option (PTy × PTy) := none
  /-- The knot key of the declaration being elaborated (`Loc.definition`). -/
  declKey : String := ""
  /-- The innermost surface node being elaborated: where a refusal is reported. -/
  here : Option Loc := none

/-- An elaboration refusal: its message, where it was raised when known, and a one-line
statement of the real form when one applies. -/
structure Refusal where
  message : String
  loc : Option Loc := none
  hint : Option String := none
  /-- For a refusal about a sum's cases: the sum and the case found, in surface syntax. -/
  expected : Option String := none
  found : Option String := none
  deriving Inhabited

instance : Coe String Refusal := ⟨fun message => { message }⟩

abbrev M := StateT St (Except Refusal)

def fail {α : Type} (message : String) : M α := do
  throw { message, loc := (← get).here }

/-- Refuse at `loc` (rather than at the node being elaborated), with a hint. -/
def failAt {α : Type} (loc : Option Loc) (message : String) (hint : Option String := none)
    (expected found : Option String := none) : M α :=
  throw { message, loc, hint, expected, found }

/-- Elaborate the surface node at `span` of module `m`: refusals inside are reported there
(unless a deeper node claims them), and the term is marked with where it came from. -/
def withLoc (span : ObjectiveBendSurface.Span) (m : Module) (action : M ATerm) : M ATerm := do
  let outer := (← get).here
  let loc : Loc := ⟨m.name, (← get).declKey, span⟩
  modify fun st => { st with here := some loc }
  let t ← action
  modify fun st => { st with here := outer }
  return .located loc t

/-- Elaborate declaration `key`: its nodes' locations name it. -/
def inDecl {α : Type} (key : String) (action : M α) : M α := do
  let outer := (← get).declKey
  modify fun st => { st with declKey := key }
  let a ← action
  modify fun st => { st with declKey := outer }
  return a
def typeError (message : String) : M Unit := modify fun s => { s with typeErrors := s.typeErrors.push message }

def quantityOf (p : Param) : M String :=
  match p.quantity with
  | "default" | "copy" => pure "unrestricted"
  | "dead" => pure "erased"
  | "affine" => pure "affine"
  | "linear" => pure "linear"
  | other => fail ("unsupported source quantity " ++ other)
def restricted (q : String) : Bool := q == "affine" || q == "linear"

def duplicate (names : List String) : Bool := names.eraseDups.length != names.length

def importOf (m : Module) (alias : String) : Option String := (m.imports.find? (·.1 == alias)).map (·.2)
def moduleNamed (c : Ctx) (name : String) : Option Module := c.modules.find? (·.name == name)

def isIdentStart (ch : Char) : Bool := ch.isAlpha || ch == '_'
def isIdentChar (ch : Char) : Bool := ch.isAlphanum || ch == '_'
def isIdent (s : String) : Bool :=
  match s.toList with
  | ch :: rest => isIdentStart ch && rest.all isIdentChar
  | [] => false
/-- `^([A-Za-z_]\w*)\.([A-Za-z_]\w*)$` -/
def qualifiedName (s : String) : Option (String × String) :=
  match s.splitOn "." with
  | [a, b] => if isIdent a && isIdent b then some (a, b) else none
  | _ => none

/-- The bytes `[start, stop)` of `bytes` without ASCII spaces at either end (`isSpace`), as a
string; every cut is at an ASCII byte, so the range is whole UTF-8. -/
def trimmedRange (bytes : ByteArray) (start stop : Nat) : String := Id.run do
  let space := fun (b : UInt8) => b == 32 || b == 9 || b == 10 || b == 13
  let mut a := start
  let mut z := stop
  while a < z && space bytes[a]! do a := a + 1
  while a < z && space bytes[z - 1]! do z := z - 1
  return String.fromUTF8! (bytes.extract a z)

def trimStr (s : String) : String :=
  let bytes := s.toUTF8
  trimmedRange bytes 0 bytes.size

/-- `text` cut at every `sep` outside `<...>`, `(...)` and `{...}` (the `>` of an arrow `->` is
not a bracket), each piece trimmed. It scans UTF-8 bytes: brackets and separators are ASCII,
so no byte of a multi-byte character is mistaken for one, and the character before a `>` is
`-` exactly when the byte before it is. -/
def splitTop (text : String) (sep : String) : List String := Id.run do
  let bytes := text.toUTF8
  let sepBytes := sep.toUTF8
  let isPrefixAt := fun (i : Nat) => Id.run do
    if i + sepBytes.size > bytes.size then return false
    for k in [0:sepBytes.size] do
      if bytes[i + k]! != sepBytes[k]! then return false
    return true
  let mut parts : Array String := #[]
  let mut start := 0
  let mut depth : Int := 0
  let mut prev : UInt8 := 0
  let mut i := 0
  while i < bytes.size do
    let c := bytes[i]!
    if c == 60 || c == 40 || c == 123 then
      depth := depth + 1; prev := c; i := i + 1
    else if (c == 62 || c == 41 || c == 125) && !(c == 62 && prev == 45) then
      depth := depth - 1; prev := c; i := i + 1
    else if depth == 0 && sepBytes.size > 0 && isPrefixAt i then
      parts := parts.push (trimmedRange bytes start i)
      i := i + sepBytes.size
      start := i
      prev := sepBytes[sepBytes.size - 1]!
    else
      prev := c; i := i + 1
  parts := parts.push (trimmedRange bytes start bytes.size)
  return parts.toList

/-- The one public metadata type of every specification (`Specification<T>` is
`specification(SpecMeta, Extension<T>)`), declared in the built-in module as two
recursive sums (`builtinSource`):

    sum SpecClaims:  none: {} | claim: {name: String, status: String, rest: SpecClaims}
    sum SpecMeta:  declared: {name: String, interface: String, claims: SpecClaims}
                 | composed: {inherited: SpecMeta, wrapping: SpecMeta}
                 | extension: {}

It is first-order data, the same for every target, so claims and composition never change
a specification's public type, and `compose` is closed over `Specification<T>`. The
reflection contract (what a client may observe) is docs/objective-bend/REFLECTION.md. -/
def specMetaName : String := "SpecMeta"
def specClaimsName : String := "SpecClaims"
/-- The built-in module: types every module resolves by bare name; no module may declare
them, and it has no definitions (nothing of it is emitted). Not a legal source module name. -/
def builtinModuleName : String := "$builtin"
def builtinTypeNames : List String := [specMetaName, specClaimsName, "TextPieces"]
def builtinSource : String :=
  "edition ObjectiveBend 1\n" ++
  "sum SpecClaims:\n  none: {}\n  claim: {name: String, status: String, rest: SpecClaims}\n\n" ++
  "sum SpecMeta:\n  declared: {name: String, interface: String, claims: SpecClaims}\n" ++
  "  composed: {inherited: SpecMeta, wrapping: SpecMeta}\n  extension: {}\n" ++
  -- The list an interpolated string of more than four pieces is joined over.
  "sum TextPieces:\n  nil: {}\n  cons: {head: String, tail: TextPieces}\n"

def lookupGlobal (c : Ctx) (name : String) (m : Module) : Option String :=
  let key := m.name ++ "." ++ name
  if c.declIndex.contains key then some key else none

def declOf (c : Ctx) (key : String) : Option (Decl × Module) := c.declIndex[key]?

/-! ## Layer stacks: late binding through the knot

Every reference to a declaration is a read of the package knot through `self`, so the knot
already binds late; a layer stack only has to say which field answers a name. For each
definition `B.f` a layer above overrides, the field `B.f` holds `self.L.f` (`L.f` the
nearest override, itself aliased further up when overridden again) and `B.f`'s own body
moves to `B.f#below`. A reference from a layer to a module below it (`Super.f`, or any alias
of a lower module) names the version of `f` at that module's level: the topmost definition
at or below it, through its `#below` field when something above overrides it. -/

def belowSuffix : String := "#below"

/-- The level of a module in the layer stack (0 = bottom). -/
def Ctx.level (c : Ctx) (module : String) : Option Nat := c.stack.findIdx? (· == module)

/-- The field a reference from module `from` to `module.name` reads: late bound unless
`module` is below `from` in the stack. Also the key whose declaration types it. -/
def Ctx.resolve (c : Ctx) (from_ module name : String) : String × String :=
  let key := module ++ "." ++ name
  match c.level from_, c.level module with
  | some l, some k =>
    if k < l then
      -- The topmost definition of `name` at or below level `k`.
      let found := (List.range (k + 1)).reverse.findSome? fun j =>
        c.stack[j]?.bind fun m => let d := m ++ "." ++ name; if c.declIndex.contains d then some d else none
      match found with
      | some d => if c.overrides.contains d then (d ++ belowSuffix, d) else (d, d)
      | none => (key, key)
    else (key, key)
  | _, _ => (key, key)

inductive ResultSpec where
  | source (text : String)
  | given (type : Option PTy)

def primitiveSignature : String → Option (String × PTy × PTy)
  | "+" => some ("add", .natural, .natural)
  | "*" => some ("multiply", .natural, .natural)
  | "==" => some ("equal", .natural, .boolean)
  | "&&" => some ("conjunction", .boolean, .boolean)
  | "-" => some ("subtract", .natural, .natural)
  | "/" => some ("divide", .natural, .natural)
  | "%" => some ("modulo", .natural, .natural)
  | "<" => some ("less", .natural, .boolean)
  | "<=" => some ("lessEqual", .natural, .boolean)
  | _ => none
/-- `a > b` is `!(a <= b)` and `a >= b` is `!(a < b)`: the operands stay in source
order (left evaluated first), unlike a swap to `b < a`. -/
def negatedOrder : String → Option String
  | ">" => some "lessEqual"
  | ">=" => some "less"
  | _ => none
def operatorTypes (op : String) : Option (PTy × PTy) :=
  match primitiveSignature op with
  | some (_, input, output) => some (input, output)
  | none => (negatedOrder op).map fun _ => (.natural, .boolean)
/-- The type of `compose(left, right)`: a specification whose metadata is `metaTy` (the
one SpecMeta type, whatever the operands' metadata) and whose extension runs `right`
over `left` under one final self. It depends on the operands only through their
callable extension types, so composing two `Specification<T>`/`Extension<T>` values
gives `Specification<T>` (`composeTy_closed`). -/
def composeTy (metaTy : PTy) (left right : Option PTy) : Option PTy :=
  match callable left, callable right with
  | some (.arrow _ _ ld (.arrow _ _ li _)), some (.arrow _ _ _ (.arrow _ _ _ rp)) =>
    some (.specification metaTy (arrowTy ld (arrowTy li rp)))
  | _, _ => none
/-- `Sum.label(…)` / `Alias.Sum.label(…)`: (label, module name, sum type name). -/
def sumCase (c : Ctx) (callee : Expr) (env : List Binding) (m : Module) : Option (String × String × String) :=
  match callee with
  | .member target caseLabel =>
    let typeName : Option String := match target with
      | .var n => if env.any (·.name == n) then none else some n
      | .member (.var alias) n => if env.any (·.name == alias) || (importOf m alias).isNone then none else some (alias ++ "." ++ n)
      | _ => none
    typeName.bind fun typeName =>
      let resolved : Option (String × String) := match qualifiedName typeName with
        | some (alias, n) => (importOf m alias).map fun mod => (mod ++ "." ++ n, mod)
        | none => if builtinTypeNames.contains typeName then some (builtinModuleName ++ "." ++ typeName, builtinModuleName)
            else some (m.name ++ "." ++ typeName, m.name)
      resolved.bind fun (key, moduleName) =>
        match c.sum? key with
        | some (_, .sum sumName _) => some (caseLabel, moduleName, sumName)
        | _ => none
  | _ => none
def variantRowOf (s : St) : Option PTy → Option PTy
  | some (.computation _ _ result) => match result with
    | .variable i => match s.sumBounds.lookup i with
      | some (.variant row) => some row
      | _ => none
    | .variant row => some row
    | _ => none
  | some (.variable i) => match s.sumBounds.lookup i with
    | some (.variant row) => some row
    | _ => none
  | some (.variant row) => some row
  | _ => none

/-- A yield: the only one is a world call. -/
def isPerform (_c : Ctx) (e : Expr) (_env : List Binding) (_m : Module) : Bool :=
  match e with
  | .worldCall .. => true
  | _ => false

/-- `perform(...)` naming no local or global: the withdrawn surface yield. -/
def isSurfacePerform (c : Ctx) (e : Expr) (env : List Binding) (m : Module) : Bool :=
  match e with
  | .call (.var "perform") _ => !env.any (·.name == "perform") && (lookupGlobal c "perform" m).isNone
  | _ => false

def withdrawnPerform : String :=
  "refused (perform): surface perform is withdrawn; an Activity<Result> yields by world calls, world.METHOD(argument)"


/-! ## Types: source annotations, declaration types, synthesis -/

/-- `overlay provided inherited`: the provided fields first, then the inherited row
(the first field of a name wins, as Core4 `overlay` after `extend`). -/
def PTy.overlay : PTy → PTy → PTy
  | .field n t rest, inherited => .field n t (rest.overlay inherited)
  | _, inherited => inherited

/-- The row a spec's method definitions leave over `inherited` (canonical). -/
def overDefs (defs : List (String × PTy)) (inherited : PTy) : PTy :=
  (PTy.overlay (PTy.row defs) inherited).canonical

def isRowTy : PTy → Bool
  | .field .. | .emptyRow => true
  | _ => false

/-- An activity over messages (`Activity<Result>`): its Plan is a record, its response `Data`. -/
def isMessageEffect : Option (PTy × PTy) → Bool
  | some (p, .data) => isRowTy p
  | _ => false

/-- A proposal type in surface syntax (structural: rows and sums spelled out). -/
partial def typeText : PTy → String
  | .natural => "Nat" | .boolean => "Bool" | .label => "String" | .data => "Data" | .emptyRow => "{}"
  | .variable i => "T" ++ toString i
  | .arrow _ _ d c => "(" ++ typeText d ++ ") -> " ++ typeText c
  | t@(.field ..) =>
    let rec fields : PTy → List String
      | .field n m rest => (n ++ ": " ++ typeText m) :: fields rest
      | .emptyRow => []
      | other => ["..." ++ typeText other]
    "{" ++ ", ".intercalate (fields t) ++ "}"
  | .variant row =>
    let rec cases : PTy → List String
      | .field n m rest => (n ++ ": " ++ typeText m) :: cases rest
      | .emptyRow => []
      | other => ["..." ++ typeText other]
    "(" ++ " | ".intercalate (cases row) ++ ")"
  | .computation p r a =>
    if isMessageEffect (some (p, r)) then "Activity<" ++ typeText a ++ ">"
    else "Activity<" ++ typeText p ++ ", " ++ typeText r ++ ", " ++ typeText a ++ ">"
  | .specification m e => "Specification<" ++ typeText m ++ ", " ++ typeText e ++ ">"
  | .prototype sp t => "Prototype<" ++ typeText sp ++ ", " ++ typeText t ++ ">"

def requirementsOf (s : Spec) : M (List Signature) :=
  pure (s.requirements.map Surface.signature)

def signatureText (r : Signature) : String :=
  r.name ++ "(" ++ ", ".intercalate (r.params.map fun p => p.name ++ ": " ++ p.type) ++ ") -> " ++ r.resultType

/-- `Self has {...}, Super has {...}`: the Self and Super bound texts (Super defaults to `{}`). -/
def bindersOf (text : String) : M (String × String) := do
  let mut selfBound : Option String := none
  let mut superBound : Option String := none
  for part in splitTop text "," do
    match part.splitOn " has " with
    | [name, bound] =>
      let n := trimStr name
      if n == "Self" && selfBound.isNone then selfBound := some (trimStr bound)
      else if n == "Super" && superBound.isNone then superBound := some (trimStr bound)
      else fail ("binder " ++ n ++ ": only `Self has {...}` and `Super has {...}`, once each")
    | _ => fail ("binder `" ++ part ++ "`: expected `Self has {...}` or `Super has {...}`")
  let some sb := selfBound | fail "an open declaration binds `Self has {...}`"
  return (sb, superBound.getD "{}")

/-- Run `k` with source type names bound (restored afterwards). -/
def withTypes {α : Type} (bindings : List (String × PTy)) (k : M α) : M α := do
  let saved := (← get).typeBindings
  modify fun st => { st with typeBindings := bindings ++ saved }
  let r ← k
  modify fun st => { st with typeBindings := saved }
  return r

/-- `refuse("why")` (unshadowed): its reason, or a refusal when it is not one string literal. -/
def refuseCall (c : Ctx) (e : Expr) (env : List Binding) (m : Module) : Option (M String) :=
  match e with
  | .call (.var "refuse") args =>
    if env.any (·.name == "refuse") || (lookupGlobal c "refuse" m).isSome then none
    else some (match args with
      | [.str reason] => pure reason
      | _ => fail "refuse takes one string literal: refuse(\"why\")")
  | _ => none

/-- A turn refusal at the activity type being lowered. -/
def refusal (reason : String) : M ATerm := do
  match (← get).resultType with
  | some (.computation p r a) => return .refuse (.computation p r a) reason
  | _ => fail "refused (refuse-outside-activity): refuse ends a turn, so it stands only in an Activity"

mutual
def sourceType (c : Ctx) : Nat → String → String → List String → M (Option PTy)
  | 0, _, _, _ => fail "type resolution fuel"
  | fuel + 1, raw, moduleName, seen => do
    let memo := seen.isEmpty && (← get).typeBindings.isEmpty
    if memo then
      if let some t := (← get).typeMemo[(moduleName, raw)]? then return some t
    let result ← sourceTypeUncached c fuel raw moduleName seen
    if memo then
      if let some t := result then
        if (← get).typeBindings.isEmpty then
          modify fun st => { st with typeMemo := st.typeMemo.insert (moduleName, raw) t }
    return result

def sourceTypeUncached (c : Ctx) : Nat → String → String → List String → M (Option PTy)
  | 0, _, _, _ => fail "type resolution fuel"
  | fuel + 1, raw, moduleName, seen => do
    let name := trimStr raw
    if name == "_" || name == "" then return none
    if let some t := (← get).typeBindings.lookup name then return some t
    let arrows := splitTop name "->"
    if arrows.length > 1 then
      let mut t ← sourceType c fuel arrows.getLast! moduleName seen
      for d' in (arrows.dropLast).reverse do
        let d ← sourceType c fuel d' moduleName seen
        t := match d, t with | some d, some t => some (arrowTy d t) | _, _ => none
      return t
    if name.startsWith "(" && name.endsWith ")" then
      return ← sourceType c fuel (dropEndStr (dropStr name 1) 1) moduleName seen
    -- `R with {f: T, ...}`: the row R overlaid by the listed fields (R's other fields kept).
    if let [left, right] := splitTop name " with " then
      let some l ← sourceType c fuel left moduleName seen | return none
      let some r ← sourceType c fuel right moduleName seen | return none
      let bounds := (← get).sumBounds
      let rowVariable := match l with
        | .variable k => match bounds.lookup k with
          | some bound => isRowTy bound
          | none => false
        | _ => false
      if !(isRowTy l || rowVariable) || !isRowTy r then
        typeError ("`" ++ name ++ "`: `with` overlays a record row on a record row"); return none
      return some (PTy.overlay r l).canonical
    if name.startsWith "{" && name.endsWith "}" then
      let inner := trimStr (dropEndStr (dropStr name 1) 1)
      if inner.isEmpty then return some .emptyRow
      let mut fields : List (String × PTy) := []
      let mut ok := true
      for f in splitTop inner "," do
        -- A method member `m(p: T, ...) -> R` (as in a record declaration).
        let arrowParts := splitTop f "->"
        let head := arrowParts.headD ""
        if arrowParts.length > 1 && head.endsWith ")" && (head.splitOn "(").length > 1 &&
            isIdent (trimStr ((head.splitOn "(").headD "")) then
          let n := trimStr ((head.splitOn "(").headD "")
          let paramsText := dropEndStr (dropStr head (n.length + 1)) 1
          let resultText := String.intercalate "->" (arrowParts.drop 1)
          let mut params : List Param := []
          for pt in (if (trimStr paramsText).isEmpty then [] else splitTop paramsText ",") do
            match pt.splitOn ":" with
            | pn :: prest => params := params ++ [⟨trimStr pn, trimStr (String.intercalate ":" prest), "default"⟩]
            | [] => ok := false
          match ← signatureTy c fuel params (.source resultText) moduleName seen with
          | some t => fields := fields ++ [(n, t)]
          | none => ok := false
          continue
        match f.splitOn ":" with
        | fieldName :: rest =>
          let n := trimEnd fieldName
          let typeText := trimStart (String.intercalate ":" rest)
          if isIdent n && !typeText.isEmpty then
            match ← sourceType c fuel typeText moduleName seen with
            | some t => fields := fields ++ [(n, t)]
            | none => ok := false
          else ok := false
        | [] => ok := false
      return if ok then some (PTy.row fields) else none
    if name == "Nat" then return some .natural
    if name == "Bool" then return some .boolean
    if name == "String" then return some .label
    if name == "Data" then return some .data
    if name.startsWith "Activity<" && name.endsWith ">" then
      let parts := splitTop (dropEndStr (dropStr name "Activity<".length) 1) ","
      match parts with
      | [_, _, resultText] => do
        typeError ("refused (old-dialect): Activity<Plan, Response, Result> is withdrawn; write Activity<" ++
          trimStr resultText ++ "> and yield by world calls (docs/WHOLENESS.md section 1)")
        return none
      | [resultText] =>
        -- `Activity<Result>`: yields `World.Message`s, each world call resumed at its own result.
        if (moduleNamed c "World").isNone then
          typeError ("Activity<" ++ trimStr resultText ++ "> yields World.Message, but no module named World is in this package; import ./World.obend")
          return none
        let message ← sourceType c fuel "Message" "World" []
        let result ← sourceType c fuel resultText moduleName seen
        return match message, result with
          | some p, some a => if isRowTy p then some (.computation p .data a) else none
          | _, _ => none
      | _ => do typeError "Activity<Result> takes one type"; return none
    if name.startsWith "Prototype<" && name.endsWith ">" then
      let parts := splitTop (dropEndStr (dropStr name "Prototype<".length) 1) ","
      match parts with
      | [specText, targetText] =>
        let spec ← sourceType c fuel specText moduleName seen
        let target ← sourceType c fuel targetText moduleName seen
        return match spec, target with
          | some s, some t => some (.prototype s t)
          | _, _ => none
      | _ => do typeError "Prototype<Spec, Target> takes two types"; return none
    for (generic, isExtension) in [("Extension<", true), ("Specification<", false)] do
      if name.startsWith generic && name.endsWith ">" && name.length > generic.length + 1 then
        let some target ← sourceType c fuel (dropEndStr (dropStr name generic.length) 1) moduleName seen | return none
        if isExtension then return some (extensionTy target)
        let some metaTy ← sourceType c fuel specMetaName builtinModuleName [] | return none
        return some (.specification metaTy (extensionTy target))
    if let some (alias, typeName) := qualifiedName name then
      let imported := (moduleNamed c moduleName).bind (importOf · alias)
      let some importedModule := imported | do typeError ("unresolved source type import " ++ name); return none
      return ← sourceType c fuel typeName importedModule seen
    let moduleName := if builtinTypeNames.contains name then builtinModuleName else moduleName
    let key := moduleName ++ "." ++ name
    if let some (_, .sum _ cases) := c.sum? key then
      let s ← get
      if seen.contains key then
        let index ← match s.sumVariables.lookup key with
          | some k => pure k
          | none => do
            let k := s.sumVariables.length + 1
            modify fun s => { s with sumVariables := s.sumVariables ++ [(key, k)] }
            pure k
        return some (.variable index)
      if let some k := s.sumVariables.lookup key then
        if (s.sumBounds.lookup k).isSome then return some (.variable k)
      let mut row : List (String × PTy) := []
      let mut ok := true
      for (caseLabel, caseType) in cases do
        match ← sourceType c fuel caseType moduleName (seen ++ [key]) with
        | some t => row := row ++ [(caseLabel, t)]
        | none => ok := false
      if !ok then return none
      let variant := PTy.variant (PTy.row row)
      if let some k := (← get).sumVariables.lookup key then
        modify fun s => { s with sumBounds := s.sumBounds ++ [(k, variant)] }
        return some (.variable k)
      return some variant
    -- A record naming itself is a recursive type, like a recursive sum: every occurrence,
    -- the outermost included, is one bounded variable whose bound is the record's row
    -- (OB-LTUO LT2 D6). The checker unfolds one declared head (`sameType`).
    if seen.contains key then
      let s ← get
      let index ← match s.sumVariables.lookup key with
        | some k => pure k
        | none => do
          let k := s.sumVariables.length + 1
          modify fun s => { s with sumVariables := s.sumVariables ++ [(key, k)] }
          pure k
      return some (.variable index)
    let some (_, .record _ recordFields methods) := c.record? key
      | do typeError ("unsupported source type " ++ name); return none
    if let some k := (← get).sumVariables.lookup key then
      if ((← get).sumBounds.lookup k).isSome then return some (.variable k)
    let mut row : List (String × PTy) := []
    let mut ok := true
    for (fieldName, fieldType) in recordFields do
      match ← sourceType c fuel fieldType moduleName (seen ++ [key]) with
      | some t => row := row ++ [(fieldName, t)]
      | none => ok := false
    for method in methods do
      match ← signatureTy c fuel method.params (.source method.resultType) moduleName (seen ++ [key]) with
      | some t => row := row ++ [(method.name, t)]
      | none => ok := false
    if !ok then return none
    if let some k := (← get).sumVariables.lookup key then
      modify fun s => { s with sumBounds := s.sumBounds ++ [(k, PTy.row row)] }
      return some (.variable k)
    return some (PTy.row row)

def signatureTy (c : Ctx) : Nat → List Param → ResultSpec → String → List String → M (Option PTy)
  | 0, _, _, _, _ => fail "type resolution fuel"
  | fuel + 1, params, result, moduleName, seen => do
    let initial : Option PTy ← (match result with
      | .source text => sourceType c fuel text moduleName seen
      | .given given => pure given)
    let mut t := initial
    let quantities ← params.mapM quantityOf
    for i in (List.range params.length).reverse do
      let d ← sourceType c fuel params[i]!.type moduleName seen
      match d, t with
      | some d, some t' =>
        let once := (quantities.take i).any restricted
        t := some (arrowTy d t' quantities[i]! (if once then "once" else "reusable"))
      | _, _ => return none
    return t

def globalType (c : Ctx) : Nat → String → M (Option PTy)
  | 0, _ => fail "type resolution fuel"
  | fuel + 1, key => do
    if let some t := (← get).globalTypes[key]? then return t
    if (← get).inferring.contains key then
      typeError ("result inference cycle through " ++ key ++ "; annotate its result type"); return none
    let some (d, m) := declOf c key | return none
    modify fun s => { s with inferring := s.inferring ++ [key] }
    let t ← match d with
      | .reexport .. => fail "internal unresolved export"
      | .function _ params resultType body => do
        let mut result ← sourceType c fuel resultType m.name []
        if resultType == "_" then
          let mut env : List Binding := []
          for p in params do
            env := ⟨p.name, ← sourceType c fuel p.type m.name [], ← quantityOf p⟩ :: env
          result ← synthBody c fuel body env m
          if result.isNone then typeError ("result inference requires an annotation for " ++ key)
        signatureTy c fuel params (.given result) m.name []
      | .extension _ params targetType _ binders =>
        if binders.isEmpty then signatureTy c fuel params (.source targetType) m.name []
        else do
          -- An open extension's knot field is its instance at its own bounds.
          let some (selfVar, superRow) ← openBinding c fuel key binders [] m.name | pure none
          withTypes [("Self", selfVar), ("Super", superRow)] (signatureTy c fuel params (.source targetType) m.name [])
      | .spec s => do
        -- Claims are not part of the type (they are checked as their own hidden fields).
        let metaTy ← sourceType c fuel specMetaName builtinModuleName []
        if !s.binders.isEmpty then
          -- An open spec's knot field is its instance at its own bounds.
          let some (selfVar, superRow) ← openBinding c fuel key s.binders (← requirementsOf s) m.name | pure none
          let some provided ← withTypes [("Self", selfVar), ("Super", superRow)] (specProvided c fuel s m.name superRow)
            | pure none
          pure (metaTy.map fun mt => .specification mt (arrowTy selfVar (arrowTy superRow provided)))
        else
          let target ← sourceType c fuel s.targetType m.name []
          pure (match target, metaTy with
            | some target, some metaTy => some (.specification metaTy (extensionTy target))
            | _, _ => none)
      | _ => pure none
    modify fun s => { s with inferring := s.inferring.erase key, globalTypes := s.globalTypes.insertIfNew key t }
    return t

/-- An open declaration's `Self` (a bounded variable whose bound is the Self row, its
`requires` lines included, so an F-bound such as `heavier(other: Self) -> Self` refers to
it) and its `Super` bound row. Memoized per declaration. -/
def openBinding (c : Ctx) : Nat → String → String → List Signature → String → M (Option (PTy × PTy))
  | 0, _, _, _, _ => fail "type resolution fuel"
  | fuel + 1, key, binders, requirements, moduleName => do
    if let some b := (← get).openBounds.lookup key then return some b
    let (selfText, superText) ← bindersOf binders
    let s ← get
    let index := s.sumVariables.length + 1
    modify fun s => { s with sumVariables := s.sumVariables ++ [("$Self:" ++ key, index)] }
    let selfVar := PTy.variable index
    let saved := (← get).typeBindings
    modify fun st => { st with typeBindings := [("Self", selfVar)] ++ saved }
    let selfRow ← sourceType c fuel selfText moduleName []
    let mut required : List (String × PTy) := []
    let mut ok := true
    for r in requirements do
      match ← signatureTy c fuel r.params (.source r.resultType) moduleName [] with
      | some t => required := required ++ [(r.name, t)]
      | none => ok := false
    let superRow ← sourceType c fuel superText moduleName []
    modify fun st => { st with typeBindings := saved }
    match selfRow, superRow with
    | some sr, some ir =>
      if !ok || !isRowTy sr || !isRowTy ir then
        typeError ("open declaration " ++ key ++ ": Self and Super bounds must be record rows"); return none
      -- Super is abstract too (GPT-6 row D): a second bounded variable whose bound is the Super
      -- row, so the template is checked against what it READS of the row beneath, never against
      -- the bound row as if it were the row itself (super-rigid).
      let superIndex := (← get).sumVariables.length + 1
      modify fun s => { s with sumVariables := s.sumVariables ++ [("$Super:" ++ key, superIndex)] }
      modify fun s => { s with sumBounds := s.sumBounds ++ [(index, (PTy.overlay (PTy.row required) sr).canonical),
        (superIndex, ir.canonical)] }
      let superVar := PTy.variable superIndex
      modify fun s => { s with openBounds := s.openBounds ++ [(key, (selfVar, superVar))] }
      return some (selfVar, superVar)
    | _, _ => return none

/-- The members a spec's methods define, at their declared types. -/
def specDefs (c : Ctx) : Nat → Spec → String → M (Option (List (String × PTy)))
  | 0, _, _ => fail "type resolution fuel"
  | fuel + 1, s, moduleName => do
    let mut defs : List (String × PTy) := []
    for method in s.methods do
      let some t ← signatureTy c fuel method.params (.source method.resultType) moduleName [] | return none
      defs := defs ++ [(method.name, t)]
    return some defs

/-- The row a plain spec provides over `inherited`: its methods overlaid on it (canonical). -/
def specProvided (c : Ctx) : Nat → Spec → String → PTy → M (Option PTy)
  | 0, _, _, _ => fail "type resolution fuel"
  | fuel + 1, s, moduleName, inherited => do
    let some defs ← specDefs c fuel s moduleName | return none
    return some (overDefs defs inherited)

/-- Only a declared recursive record is transparent here. Open Self/Super variables
have row lower bounds, not record aliases, and must retain their abstract tails. -/
def recursiveRecordRow (c : Ctx) (st : St) (ty : PTy) : Option PTy := do
  let .variable k := ty | none
  let (key, _) ← st.sumVariables.find? (fun (_, index) => index == k)
  if !c.recordIndex.contains key then none
  else
    let row ← st.sumBounds.lookup k
    if isRowTy row then some row else none

def synth (c : Ctx) : Nat → Expr → List Binding → Module → M (Option PTy)
  | 0, _, _, _ => fail "type synthesis fuel"
  | fuel + 1, e, env, m => do
    match e with
    | .nat _ => return some .natural
    | .bool _ => return some .boolean
    | .str _ => return some .label
    | .unit => return some .emptyRow
    | .var name =>
      if let some b := env.find? (·.name == name) then return b.ty
      match lookupGlobal c name m with
      | some key => globalType c fuel key
      | none => return none
    | .member target name =>
      if let .var alias := target then
        if !env.any (·.name == alias) then
          if let some importedModule := importOf m alias then
            return ← globalType c fuel (c.resolve m.name importedModule name).2
      let targetType ← synth c fuel target env m
      return lookupRowBounded (← get).sumBounds fuel targetType name
    | .record fields =>
      let mut row : List (String × PTy) := []
      for (n, v) in fields do
        match ← synth c fuel v env m with
        | some t => row := row ++ [(n, t)]
        | none => return none
      return some (PTy.row row)
    | .extend inherited fields =>
      let some base ← synth c fuel inherited env m | return none
      let some provided ← synth c fuel (.record fields (span := e.span)) env m | return none
      let bounds := (← get).sumBounds
      let rowVariable := match base with
        | .variable k => (bounds.lookup k).map isRowTy | _ => none
      if !(isRowTy base || rowVariable.getD false) then return none
      -- Keep an abstract Super as the row tail; a lower bound is not its alias.
      return some (PTy.overlay provided ((recursiveRecordRow c (← get) base).getD base)).canonical
    | .binary op left right =>
      if op == "!=" || op == "==" then return some .boolean
      if op == "||" then
        return if sameTy (← synth c fuel left env m) (some .boolean) && sameTy (← synth c fuel right env m) (some .boolean)
          then some .boolean else none
      let some (input, output) := operatorTypes op | return none
      return if sameTy (← synth c fuel left env m) (some input) && sameTy (← synth c fuel right env m) (some input)
        then some output else none
    | .letE name type value body =>
      let ty ← if type == "_" then synth c fuel value env m else sourceType c fuel type m.name []
      synth c fuel body (⟨name, ty, "unrestricted"⟩ :: env) m
    | .ite _ whenTrue whenFalse =>
      let a ← synth c fuel whenTrue env m
      let b ← synth c fuel whenFalse env m
      return if a.isSome && b.isSome && sameTy a b then a else none
    | .compose specs =>
      match specs with
      | [] => return none
      | first :: rest =>
        let some metaTy ← sourceType c fuel specMetaName builtinModuleName [] | return none
        let mut t ← synth c fuel first env m
        for next in rest do t := composeTy metaTy t (← synth c fuel next env m)
        return t
    | .fix spec _ =>
      return match callable (← synth c fuel spec env m) with
        | some (.arrow _ _ d _) => some d
        | _ => none
    | .closure params resultType _ => signatureTy c fuel params (.source resultType) m.name []
    | .toData type value =>
      let declared ← sourceType c fuel type m.name []
      return if sameTy (← synth c fuel value env m) declared then some .data else none
    | .worldCall _ _ resultText _ =>
      let some (p, r) := (← get).effect | return none
      return (← sourceType c fuel resultText m.name []).map fun t => .computation p r t
    | .call callee args =>
      if let some sc := sumCase c callee env m then return ← sourceType c fuel sc.2.2 sc.2.1 []
      if let .var name := callee then
        if !env.any (·.name == name) && (lookupGlobal c name m).isNone then
          if ["natText", "sha256Text"].contains name && args.length == 1 then return some .label
          if name == "textLength" && args.length == 1 then return some .natural
          if name == "textConcat" && args.length == 2 then return some .label
          if ["textSpan", "textBreak"].contains name && args.length == 2 then return some .natural
          if name == "textHasAny" && args.length == 2 then return some .boolean
          if name == "canonicalCompare" && args.length == 2 then return some .natural
          if ["textTake", "textDrop"].contains name && args.length == 2 then return some .label
          if name == "textSlice" && args.length == 3 then return some .label
          if name == "textJoin" && args.length == 2 then return some .label
          if name == "refuse" && args.length == 1 then
            return match (← get).resultType with
              | some (.computation p r a) => some (.computation p r a)
              | _ => none
        if ["reflect", "metadata", "targetOf", "prototype"].contains name &&
            !env.any (·.name == name) && (lookupGlobal c name m).isNone then
          match name, args with
          | "prototype", [s, t] =>
            let spec ← synth c fuel s env m
            let target ← synth c fuel t env m
            return match spec, target with
              | some s, some t => some (.prototype s t)
              | _, _ => none
          | "metadata", [value] =>
            match ← synth c fuel value env m with
            | some (.specification metaTy _) => return some metaTy
            | _ => return none
          | "reflect", [value] =>
            match ← synth c fuel value env m with
            | some (.prototype spec _) => return some spec
            | _ => return none
          | "targetOf", [value] =>
            match ← synth c fuel value env m with
            | some (.prototype _ target) => return some target
            | _ => return none
          | _, _ => return none
      let mut t ← synth c fuel callee env m
      for _ in args do
        match callable t with
        | some (.arrow _ _ _ codomain) => t := some codomain
        | _ => return none
      return t

def synthBody (c : Ctx) : Nat → Body → List Binding → Module → M (Option PTy)
  | 0, _, _, _ => fail "type synthesis fuel"
  | fuel + 1, .expr e, env, m => synth c fuel e env m
  | fuel + 1, .letB name type value rest, env, m => do
    let ty ← if type == "_" then synth c fuel value env m else sourceType c fuel type m.name []
    synthBody c fuel rest (⟨name, ty, "unrestricted"⟩ :: env) m
  | fuel + 1, .cases scrutinee branches, env, m => do
    if branches.any (fun b => match b.1 with | .ctor .. | .bool _ | .wildcard | .unexpected => true | _ => false) then
      let scrutineeTy ← synth c fuel scrutinee env m
      let row := variantRowOf (← get) scrutineeTy
      let mut types : List (Option PTy) := []
      for (pattern, b) in branches do
        if pattern == .unexpected then continue
        let env' := match pattern with
          | .ctor l binder => ⟨binder, lookupRow row l, "unrestricted"⟩ :: env
          | _ => env
        types := types ++ [← synthBody c fuel b env' m]
      -- An activity scrutinee makes the whole match an activity; pure arms are lifted.
      if isComputation scrutineeTy || types.any isComputation then
        let effect := (← get).effect
        types := types.map fun t => match t, effect with
          | some t', some (p, r) => if isComputation (some t') then some t' else some (.computation p r t')
          | _, _ => t
      return match types with
        | first :: _ => if types.all (fun t => t.isSome && sameTy t first) then first else none
        | [] => none
    let zero := branches.find? (fun b => b.1 == .zero)
    let succ := branches.find? (fun b => match b.1 with | .succ _ => true | _ => false)
    match zero, succ with
    | some (_, zb), some (.succ binder, sb) =>
      let z ← synthBody c fuel zb env m
      let s ← synthBody c fuel sb (⟨binder, some .natural, "unrestricted"⟩ :: env) m
      return if z.isSome && s.isSome && sameTy z s then z else none
    | _, _ => return none
end

/-! ## Term elaboration -/

def globalsIndex (env : List Binding) : M Nat :=
  match env.findIdx? (·.name == "$globals") with
  | some i => pure i
  | none => fail "internal: $globals is not in scope"

def globalRef (env : List Binding) (key : String) : M ATerm := do
  return .get (.bound (← globalsIndex env)) key

/-- Curried lambdas with their checker proposals. Reuse is `once` when any
visible lexical binding (outer or earlier parameter) is affine or linear. -/
def abstractWith (c : Ctx) (fuel : Nat) (params : List Param) (domains : Option (List (Option PTy))) (env : List Binding)
    (lower : List Binding → M ATerm) (nodeName : String) (result : ResultSpec) (moduleName : String) : M ATerm := do
  if duplicate (params.map (·.name)) then fail "duplicate lexical parameter"
  let mut bindings : List Binding := []
  for (p, i) in params.zipIdx do
    -- A given domain (a `let`'s synthesized type) stands in for the source annotation when it resolved.
    let given := (domains.bind (·[i]?)).bind id
    let domain ← match given with
      | some d => pure (some d)
      | none => sourceType c fuel p.type moduleName []
    bindings := bindings ++ [⟨p.name, domain, ← quantityOf p⟩]
  let initial : Option PTy ← (match result with
    | .source text => sourceType c fuel text moduleName []
    | .given given => pure given)
  -- A body whose declared result is an Activity is lowered in effect mode.
  let saved := (← get).effect
  let savedResult := (← get).resultType
  modify fun s => { s with effect := match initial with
    | some (.computation p r _) => some (p, r)
    | _ => none }
  modify fun s => { s with resultType := initial }
  -- (A failure aborts the whole elaboration, so only success restores the mode.)
  let lowered ← lower (bindings.reverse ++ env)
  modify fun s => { s with effect := saved, resultType := savedResult }
  let mut value := lowered
  let mut codomain := initial
  for i in (List.range params.length).reverse do
    let b := bindings[i]!
    let visible := bindings.take i ++ env
    let reuse := if visible.any (fun v => restricted v.quantity) then "once" else "reusable"
    let reason := if b.ty.isNone then some ("parameter " ++ b.name ++ " has no resolvable type")
      else if codomain.isNone then some ("result type of " ++ nodeName ++ " is not resolvable") else none
    value := .lam ⟨b.ty, codomain, b.quantity, reuse, reason⟩ value
    codomain := match b.ty, codomain with
      | some d, some cod => some (arrowTy d cod b.quantity reuse)
      | _, _ => none
  return value

def abstract (c : Ctx) (fuel : Nat) (params : List Param) (env : List Binding)
    (lower : List Binding → M ATerm) (nodeName : String) (result : ResultSpec) (moduleName : String) : M ATerm :=
  abstractWith c fuel params none env lower nodeName result moduleName

/-- Substitute type variables (`σ i = some t` replaces variable `i`). -/
def PTy.subst (σ : Nat → Option PTy) : PTy → PTy
  | .variable i => (σ i).getD (.variable i)
  | .arrow r q d c => .arrow r q (d.subst σ) (c.subst σ)
  | .field n m t => .field n (m.subst σ) (t.subst σ)
  | .specification m e => .specification (m.subst σ) (e.subst σ)
  | .prototype s t => .prototype (s.subst σ) (t.subst σ)
  | .variant r => .variant (r.subst σ)
  | .computation p r a => .computation (p.subst σ) (r.subst σ) (a.subst σ)
  | other => other

mutual
/-- Apply `f` to every type annotation of a lowered term. -/
def ATerm.mapTypes (f : PTy → PTy) : ATerm → ATerm
  | .located l t => .located l (t.mapTypes f)
  | .bound i => .bound i
  | .lam p b => .lam { p with domain := p.domain.map f, codomain := p.codomain.map f } (b.mapTypes f)
  | .app x y => .app (x.mapTypes f) (y.mapTypes f)
  | .mix x y => .mix (x.mapTypes f) (y.mapTypes f)
  | .fix x y => .fix (x.mapTypes f) (y.mapTypes f)
  | .specification x y => .specification (x.mapTypes f) (y.mapTypes f)
  | .prototype x y => .prototype (x.mapTypes f) (y.mapTypes f)
  | .reflect x => .reflect (x.mapTypes f)
  | .metadata x => .metadata (x.mapTypes f)
  | .project x => .project (x.mapTypes f)
  | .nat v => .nat v
  | .boolean v => .boolean v
  | .label v => .label v
  | .unary p a => .unary p (a.mapTypes f)
  | .binary p x y => .binary p (x.mapTypes f) (y.mapTypes f)
  | .extend x fs => .extend (x.mapTypes f) (ATerm.mapFieldTypes f fs)
  | .record fs => .record (ATerm.mapFieldTypes f fs)
  | .get x n => .get (x.mapTypes f) n
  | .ifZero x z y => .ifZero (x.mapTypes f) (z.mapTypes f) (y.mapTypes f)
  | .inject l t r x => .inject l (t.map f) r (x.mapTypes f)
  | .case x arms => .case (x.mapTypes f) (ATerm.mapFieldTypes f arms)
  | .ifBool x y z => .ifBool (x.mapTypes f) (y.mapTypes f) (z.mapTypes f)
  | .perform p r x => .perform (f p) (f r) (x.mapTypes f)
  | .done p r x => .done (f p) (f r) (x.mapTypes f)
  | .toData t x => .toData (f t) (x.mapTypes f)
  | .textJoin l s => .textJoin (l.mapTypes f) (s.mapTypes f)
  | .refuse t r => .refuse (f t) r
def ATerm.mapFieldTypes (f : PTy → PTy) : List (String × ATerm) → List (String × ATerm)
  | [] => []
  | (n, x) :: rest => (n, x.mapTypes f) :: ATerm.mapFieldTypes f rest
end

/-- A template's instance at σ: its annotations substituted, then canonical (the instance a
chain emits; MODULAR-TYPING §6 `template[σ]`). -/
def ATerm.instantiate (σ : Nat → Option PTy) (t : ATerm) : ATerm :=
  t.mapTypes fun ty => (ty.subst σ).canonical

/-- Re-annotate the result of the `n`-parameter function `t` as `result` (the last layer of a
chain over a recursive record is annotated with the record's variable, which unfolds to the
row the layer provides). Returns the term and its new type. -/
def ATerm.retarget (result : PTy) : Nat → ATerm → ATerm × Option PTy
  | 0, t => (t, some result)
  | n + 1, .lam p b =>
    let (b', cod) := ATerm.retarget result n b
    (.lam { p with codomain := cod } b', match p.domain, cod with
      | some d, some c => some (arrowTy d c p.parameter p.reuse)
      | _, _ => none)
  | _, t => (t, none)

def rowNames : PTy → List String
  | .field n _ t => n :: rowNames t
  | _ => []

def notTerm (x : ATerm) : ATerm := .ifBool x (.boolean false) (.boolean true)

/-- Named refusals: an activity never occupies a shared (suspended) position.
Outside an activity only a literal perform is checked (the checker refuses the
rest), so packages without activities elaborate exactly as before. -/
def noActivity (c : Ctx) (fuel : Nat) (e : Expr) (env : List Binding) (m : Module) (rule why : String) : M Unit := do
  let flagged ← if isPerform c e env m then pure true
    else if (← get).effect.isSome then pure (isComputation (← synth c fuel e env m)) else pure false
  if flagged then
    fail ("refused (" ++ rule ++ "): an Activity cannot be used here; " ++ why ++
      ", so its effect would be cached and shared. Match on it first.")

/-- `let x = v` then body: (λx. body) v. The machine allocates ONE lazy cell for the
argument of an application and caches it on first demand, so `v` is evaluated at most
once however often x is used and not at all when x is unused (call-by-need): a let is
sharing, never a copy of v. Scope is the body only: `v` is elaborated outside the
binder. In an activity tail the lambda's codomain is the activity type (a pure body is
lifted with `done`). The order of effects is part of the contract (it assigns
recursive-sum variable numbers). -/
def lowerLet (c : Ctx) (fuel : Nat) (name type : String) (value : Expr) (env : List Binding) (m : Module)
    (tailPosition : Bool) (elaborateValue : M ATerm) (lowerBody : List Binding → M ATerm)
    (bodyType : List Binding → M (Option PTy)) : M ATerm := do
  noActivity c fuel value env m "effect-in-let" "a let-bound value is a shared lazy thunk"
  let ty ← if type == "_" then synth c fuel value env m else sourceType c fuel type m.name []
  let mut codomain ← bodyType (⟨name, ty, "unrestricted"⟩ :: env)
  if tailPosition then
    if let (some (p, r), some cod) := ((← get).effect, codomain) then
      if !isComputation (some cod) then codomain := some (.computation p r cod)
  let fn ← abstractWith c fuel [⟨name, type, "default"⟩] (some [ty]) env lowerBody "let" (.given codomain) m.name
  if let .fix .. := value then
    if type != "_" then modify fun st => { st with fixTarget := ty }
  return .app fn (← elaborateValue)

/-! ## Specifications, declared ancestry and method combination -/

def outerEnv : List Binding := [⟨"$seed", some .emptyRow, "unrestricted"⟩, ⟨"$globals", some (.variable 0), "unrestricted"⟩]

def specOf (c : Ctx) (key : String) : Option (Spec × Module) :=
  match declOf c key with
  | some (.spec s, m) => some (s, m)
  | _ => none

def specKey (c : Ctx) (name : String) (m : Module) : M String := do
  let key ← match qualifiedName name with
    | some (alias, n) => match importOf m alias with
      | some mod => pure (mod ++ "." ++ n)
      | none => fail ("unknown import alias in spec parent " ++ name)
    | none => pure (m.name ++ "." ++ name)
  if (specOf c key).isNone then fail ("spec parent " ++ name ++ " is not a spec declaration")
  return key

def precedence (c : Ctx) : Nat → String → M (List String)
  | 0, _ => fail "ancestry depth fuel"
  | fuel + 1, key => do
    if let some l := (← get).precedence.lookup key then return l
    let some (s, m) := specOf c key | fail ("internal: unknown spec " ++ key)
    if (← get).linearizing.contains key then fail ("spec ancestry cycle through " ++ key)
    modify fun st => { st with linearizing := st.linearizing ++ [key] }
    let parents ← s.parents.mapM (specKey c · m)
    for p in parents do discard <| precedence c fuel p
    let memo := (← get).precedence
    let graph : ObjectiveBendC4.Graph := ⟨fun k => (memo.lookup k).getD [k],
      fun k => match specOf c k with | some (s', _) => s'.suffix | none => false⟩
    let list ← match ObjectiveBendC4.linearize graph [key] [parents] with
      | .ok (l, _) => pure l
      | .error e => fail ("C4 linearization of " ++ key ++ " refused: " ++ e.message)
    modify fun st => { st with linearizing := st.linearizing.erase key, precedence := st.precedence ++ [(key, list)] }
    return list

def qualifierGroup (q : String) : String := if q == "around" then "around" else "primary"
def hasLayer (s : Spec) (group : String) : Bool := s.methods.any (fun x => qualifierGroup x.qualifier == group)
def plainSpec (s : Spec) : Bool :=
  s.parents.isEmpty && !hasLayer s "around" && s.methods.all (·.qualifier == "primary")
def combination : String → Option (String × ATerm)
  | "+" => some ("add", .nat "0")
  | "*" => some ("multiply", .nat "1")
  | "and" => some ("conjunction", .boolean true)
  | _ => none

def checkSpecMethods (s : Spec) : M Unit := do
  for method in s.methods do
    if method.qualifier == "before" || method.qualifier == "after" then
      fail (method.qualifier ++ " methods run for their effects and discard their result; Objective Bend core has no effect constructor yet")
  for group in ["primary", "around"] do
    if duplicate ((s.methods.filter (fun x => qualifierGroup x.qualifier == group)).map (·.name)) then
      fail ("duplicate " ++ group ++ " method")

def selfSuperParams (s : Spec) : List Param :=
  if s.binders.isEmpty then [⟨"self", s.targetType, "default"⟩, ⟨"super", s.targetType, "default"⟩]
  else [⟨"self", "Self", "default"⟩, ⟨"super", "Super", "default"⟩]
def selfSuperEnv (target : Option PTy) : List Binding :=
  ⟨"super", target, "unrestricted"⟩ :: ⟨"self", target, "unrestricted"⟩ :: outerEnv


/-- A declaration named in a `fix` chain (bare or `Alias.Name`, not shadowed): a plain spec
(closed or open) or an extension declaration with exactly `self` and `super` parameters. -/
def chainOp (c : Ctx) (e : Expr) (env : List Binding) (m : Module) : Option (String × Decl × Module) :=
  let key? : Option String := match e with
    | .var n => if env.any (·.name == n) then none else lookupGlobal c n m
    | .member (.var alias) n => if env.any (·.name == alias) then none else (importOf m alias).map (· ++ "." ++ n)
    | _ => none
  key?.bind fun key => match declOf c key with
    | some (d@(.spec s), sm) => if plainSpec s then some (key, d, sm) else none
    | some (d@(.extension _ params _ _ _), sm) => if params.length == 2 then some (key, d, sm) else none
    | _ => none

/-- The operands of `fix(X, seed)` / `fix(compose(X1, ..., Xn), seed)` when every operand is a
chain declaration; otherwise none (the expression is lowered as an ordinary value). -/
def fixChain (c : Ctx) (spec : Expr) (env : List Binding) (m : Module) : Option (List (String × Decl × Module)) :=
  let ops := match spec with
    | .compose ops => ops
    | e => [e]
  ops.mapM (chainOp c · env m)

def Decl.binders : Decl → String
  | .spec s => s.binders
  | .extension _ _ _ _ b => b
  | _ => ""

def rowFields : PTy → List (String × PTy)
  | .field n t rest => (n, t) :: rowFields rest
  | _ => []

/-- A row as the composition contract reads it: its fields, each at its canonical type, so the
contract's `==` on a member type is `sameTy`. -/
def contractRow (row : PTy) : ObjectiveBendContract.Row PTy :=
  (rowFields row).map fun (n, t) => (n, t.canonical)

/-- The text of a composition-contract refusal (the `refused (...)` names the cohorts pin). -/
def contractRefusalText : ObjectiveBendContract.Refusal → String
  | .selfBound key missing => "refused (self-bound): " ++ key ++ " needs the final self to have " ++
      ", ".intercalate missing ++ " at the types its Self bound declares; the self of this fix does not"
  | .inheritedUnprovided key missing beneath => "refused (inherited-unprovided): " ++ key ++ " needs " ++
      ", ".intercalate missing ++ " from the row beneath it, which is {" ++ ", ".intercalate beneath ++ "}"
  | .replaceUndeclared key members => "refused (replace-undeclared): " ++ key ++ " gives " ++
      ", ".intercalate members ++ " a type other than the row beneath it gives; a layer may add a member " ++
      "or override it at the same type, and no source form declares a replacement"
  | .requiresUnprovided missing => "refused (requires-unprovided): this fix leaves " ++ ", ".intercalate missing ++
      " of its final self unprovided: no layer of the composition and not the seed provides it"
  | .seedExtra extra => "refused (seed-extra): the composition and seed provide " ++ ", ".intercalate extra ++
      ", which the final self does not declare"
  | .providedMismatch => "refused (provided-mismatch): the composition provides members of the final self at other types than it declares"

/-- An open declaration's Self and Super bounds at a final self `target`. -/
def boundsAt (c : Ctx) (fuel : Nat) (binders : String) (requirements : List Signature) (moduleName : String)
    (target : PTy) : M (Option (PTy × PTy)) :=
  withTypes [("Self", target)] do
    let (selfText, superText) ← bindersOf binders
    let some selfRow ← sourceType c fuel selfText moduleName [] | return none
    let mut required : List (String × PTy) := []
    for r in requirements do
      let some t ← signatureTy c fuel r.params (.source r.resultType) moduleName [] | return none
      required := required ++ [(r.name, t)]
    let some superRow ← sourceType c fuel superText moduleName [] | return none
    return some ((PTy.overlay (PTy.row required) selfRow).canonical, superRow)

/-- One `compose` step over lowered operands (the composite's metadata is
`SpecMeta.composed{P value, P right}`). -/
def composeStep (metaTy : Option PTy) (value : ATerm) (valueTy : Option PTy) (right : ATerm) (rightTy : Option PTy) :
    ATerm × Option PTy :=
  let composite := metaTy.bind (composeTy · valueTy rightTy)
  let reason := if composite.isSome then none else some "composition operand types are not resolvable as extensions"
  -- An operand's provenance: its own SpecMeta when it is a specification, else
  -- `extension {}` (a bare extension carries no metadata). Decided statically.
  let provenance := fun (ty : Option PTy) (operand : ATerm) => match ty with
    | some (.specification _ _) => ATerm.metadata operand
    | _ => ATerm.inject "extension" metaTy reason (.record [])
  let body := ATerm.specification
    (.inject "composed" metaTy reason
      (.record [("inherited", provenance valueTy (.bound 1)), ("wrapping", provenance rightTy (.bound 0))]))
    (.mix (.bound 1) (.bound 0))
  let inner := ATerm.lam ⟨rightTy, composite, "unrestricted", "reusable", reason⟩ body
  let outerCodomain := match rightTy, composite with
    | some r, some comp => some (arrowTy r comp)
    | _, _ => none
  let outer := ATerm.lam ⟨valueTy, outerCodomain, "unrestricted", "reusable", reason⟩ inner
  (.app (.app outer value) right, composite)



/-- What keeps a type from being first-order data, by name: `some "a function"` for an
arrow (or a specification or prototype) anywhere in it, `some "an Activity"` for a
computation, `none` otherwise (unresolved parts are left to the checker). -/
def PTy.notData (bounds : List (Nat × PTy)) : Nat → List Nat → PTy → Option String
  | 0, _, _ => none
  | fuel + 1, seen, t =>
    match t with
    | .arrow .. | .specification .. | .prototype .. => some "a function"
    | .computation .. => some "an Activity"
    | .field _ member tail => (member.notData bounds fuel seen).orElse fun _ => tail.notData bounds fuel seen
    | .variant row => row.notData bounds fuel seen
    | .variable k =>
      if seen.contains k then none
      else (bounds.lookup k).bind (PTy.notData bounds fuel (k :: seen))
    | _ => none

/-- The row a record-typed expected type names (a recursive record's bound). -/
def expectedRow (st : St) : Option PTy → Option PTy
  | some (.variable k) => match st.sumBounds.lookup k with
    | some row => if isRowTy row then some row else none
    | none => none
  | some t => if isRowTy t then some t else none
  | none => none

/-- Whether a value at `expected` could need an implicit `Data` injection: `expected` is
`Data`, or a record row (through recursive-record bounds) with such a field. -/
def mentionsData (bounds : List (Nat × PTy)) : Nat → List Nat → PTy → Bool
  | 0, _, _ => false
  | fuel + 1, seen, t =>
    match t with
    | .data => true
    | .field _ member tail => mentionsData bounds fuel seen member || mentionsData bounds fuel seen tail
    | .variable k =>
      if seen.contains k then false
      else match bounds.lookup k with
        | some bound => isRowTy bound && mentionsData bounds fuel (k :: seen) bound
        | none => false
    | _ => false

/- Implicit `Data` injection. Where the expected type is `Data` and an expression
synthesizes a first-order data type `T`, the elaborated term is wrapped exactly as
`Data.of::<T>(e)` wraps it (`toData T`). Expected types reach a value through a sum
payload, a call's parameter, an extended field and a definition's result, and descend
through record literals and `if`. The probe runs after the ordinary elaboration and
its state is discarded unless it injects, so a program that injects nothing elaborates
exactly as before. -/
def coerceGo (c : Ctx) : Nat → Option PTy → Expr → ATerm → List Binding → Module → M (ATerm × Bool)
  | 0, _, _, t, _, _ => return (t, false)
  | fuel + 1, expected, e, t, env, m => do
    let some ty := expected | return (t, false)
    -- A location mark is transparent: coerce what it marks, keep the mark.
    if let .located loc inner := t then
      let (inner', changed) ← coerceGo c fuel expected e inner env m
      return (.located loc inner', changed)
    if let (.ite _ whenTrue whenFalse, .ifBool ct tt ft) := (e, t) then
      let (tt', a) ← coerceGo c fuel (some ty) whenTrue tt env m
      let (ft', b) ← coerceGo c fuel (some ty) whenFalse ft env m
      return (.ifBool ct tt' ft', a || b)
    if let .data := ty then
      if let .toData .. := e then return (t, false)
      match ← synth c fuel e env m with
      | none | some .data => return (t, false)
      | some actual =>
        if let some what := actual.notData (← get).sumBounds 4096 [] then
          fail ("refused (data-injection): this value is " ++ what ++
            ", not first-order data, so it cannot be passed as Data")
        return (.toData actual t, true)
    match e, t with
    | .record fields, .record terms =>
      let some row := expectedRow (← get) (some ty) | return (t, false)
      if fields.length != terms.length then return (t, false)
      let mut out : List (String × ATerm) := []
      let mut changed := false
      for ((n, v), (n', av)) in fields.zip terms do
        let (av', ch) ← coerceGo c fuel (lookupRow (some row) n) v av env m
        out := out ++ [(n', av')]
        changed := changed || ch
      return (.record out, changed)
    | _, _ => return (t, false)

def coerceAt (c : Ctx) (fuel : Nat) (expected : Option PTy) (e : Expr) (t : ATerm) (env : List Binding) (m : Module) : M ATerm := do
  let some ty := expected | return t
  if !mentionsData (← get).sumBounds 4096 [] ty then return t
  let saved ← get
  let (t', changed) ← coerceGo c fuel expected e t env m
  unless changed do set saved
  return t'

/-- A call's arguments at the callee's parameter types (`coerceAt` for each). -/
def coerceArgs (c : Ctx) (fuel : Nat) (callee : Expr) (args : List Expr) (terms : List ATerm) (env : List Binding) (m : Module) :
    M (List ATerm) := do
  let saved ← get
  let mut calleeTy := callable (← synth c fuel callee env m)
  let mut out : List ATerm := []
  let mut changed := false
  for (a, t) in args.zip terms do
    let domain := match calleeTy with
      | some (.arrow _ _ d _) => some d
      | _ => none
    calleeTy := match calleeTy with
      | some (.arrow _ _ _ cod) => callable (some cod)
      | _ => none
    match domain with
    | some d =>
      if mentionsData (← get).sumBounds 4096 [] d then
        let (t', ch) ← coerceGo c fuel domain a t env m
        out := out ++ [t']
        changed := changed || ch
      else out := out ++ [t]
    | none => out := out ++ [t]
  unless changed do set saved
  return out

/-! ## `canonicalCompare(a, b)`: the canonical (DAG-CBOR) order, as Bend

The comparison of two values of one first-order type by the bytes of their canonical
encoding (`Delvetalk.Canonical`), written out from the type as an ordinary Bend term: no new
core form, so the machine, the codecs and the proofs are untouched. It mirrors the encoding:
a natural compares as a number (shortest heads and big-endian bignums order numerically), a
Bool `false` below `true`, a text by UTF-8 byte length then bytes (`textCanonicalCompare`), a
record field by field in map-key order (byte length, then bytes), a sum by its label in that
order and then its payload, and a list-shaped sum (`nil: {}`, `cons: {head, tail}`), which
encodes as an array, by length first and then item by item. 0 less, 1 equal, 2 greater. -/

def canonicalKeyLess (a b : String) : Bool :=
  a.utf8ByteSize < b.utf8ByteSize || (a.utf8ByteSize == b.utf8ByteSize && decide (a < b))

def sortCanonical (fields : List (String × PTy)) : List (String × PTy) :=
  (fields.toArray.qsort fun x y => canonicalKeyLess x.1 y.1).toList

/-- An operand of the comparison: its term at a given binder depth. -/
abbrev Operand := Nat → ATerm

def atLevel (level : Nat) : Operand := fun depth => .bound (depth - 1 - level)

def cmpLam (domain codomain : PTy) (body : ATerm) : ATerm :=
  .lam ⟨some domain, some codomain, "unrestricted", "reusable", none⟩ body

/-- `first`, then `next` when `first` was equal (1): `(λr. if r == 1 then next else r) first`. -/
def cmpThen (first : ATerm) (next : ATerm) : ATerm :=
  .app (cmpLam .natural .natural (.ifBool (.binary "equal" (.bound 0) (.nat "1")) next (.bound 0))) first

/-- A list-shaped sum's element type: `nil: {}` and `cons: {head: H, tail: itself}`. -/
def listElement (k : Nat) (row : PTy) : Option PTy :=
  match sortCanonical (rowFields row) with
  | [("nil", .emptyRow), ("cons", payload)] | [("cons", payload), ("nil", .emptyRow)] =>
    match sortCanonical (rowFields payload) with
    | [("head", h), ("tail", .variable k')] | [("tail", .variable k'), ("head", h)] => if k' == k then some h else none
    | _ => none
  | _ => none

/-- The comparison of `x` and `y` of type `t` at binder depth `depth`; `selfs` maps a
recursive type's variable to the level of its comparator and whether it is a list's. -/
partial def cmpTerm (t : PTy) (x y : Operand) (depth : Nat) (selfs : List (Nat × Nat × Bool)) : M ATerm := do
  let refuse := fun (what : String) =>
    (fail ("refused (canonical-compare): " ++ what ++ "; canonicalCompare takes two values of one first-order type") : M ATerm)
  match t with
  | .natural =>
    return .ifBool (.binary "less" (x depth) (y depth)) (.nat "0")
      (.ifBool (.binary "equal" (x depth) (y depth)) (.nat "1") (.nat "2"))
  | .boolean =>
    return .ifBool (x depth) (.ifBool (y depth) (.nat "1") (.nat "2")) (.ifBool (y depth) (.nat "0") (.nat "1"))
  | .label => return .binary "textCanonicalCompare" (x depth) (y depth)
  | .emptyRow => return .nat "1"
  | .field .. =>
    let rec fields : List (String × PTy) → Nat → M ATerm
      | [], _ => pure (.nat "1")
      | (name, ft) :: rest, d => do
        let first ← cmpTerm ft (fun dd => .get (x dd) name) (fun dd => .get (y dd) name) d selfs
        return cmpThen first (← fields rest (d + 1))
    fields (sortCanonical (rowFields t)) depth
  | .variant row =>
    let labels := sortCanonical (rowFields row)
    if labels.any (fun (l, _) => l == "nil" || l == "cons") then
      return ← refuse "a sum with nil or cons beside other cases encodes some values as arrays"
    let ranked := labels.zipIdx
    let mut armsA : List (String × ATerm) := []
    for ((la, pa), ia) in ranked do
      let mut armsB : List (String × ATerm) := []
      for ((lb, _), ib) in ranked do
        let body ← if la == lb then
            cmpTerm pa (atLevel depth) (atLevel (depth + 1)) (depth + 2) selfs
          else pure (.nat (if ia < ib then "0" else "2"))
        armsB := armsB ++ [(lb, body)]
      armsA := armsA ++ [(la, .case (y (depth + 1)) armsB)]
    return .case (x depth) armsA
  | .variable k =>
    if let some (level, list) := selfs.lookup k then
      let call := ATerm.app (.app (.bound (depth - 1 - level)) (x depth)) (y depth)
      return if list then .app call (.nat "1") else call
    let some bound := (← get).sumBounds.lookup k | refuse "a type that does not resolve"
    let fn : PTy := arrowTy t (arrowTy t .natural)
    match bound with
    | .variant row =>
      if let some h := listElement k row then
        -- go(a, b, acc): length first (the shorter list is less), else the first unequal item.
        let goTy : PTy := arrowTy t (arrowTy t (arrowTy .natural .natural))
        let d := depth
        let acc := atLevel (d + 4)
        let headCmp ← cmpTerm h (fun dd => .get (.bound (dd - 1 - (d + 5))) "head")
          (fun dd => .get (.bound (dd - 1 - (d + 6))) "head") (d + 7) ((k, d, true) :: selfs)
        let recur := ATerm.app (.app (.app (.bound (d + 7 - 1 - d)) (.get (.bound (d + 7 - 1 - (d + 5))) "tail"))
            (.get (.bound 0) "tail"))
          (.ifBool (.binary "equal" (acc (d + 7)) (.nat "1")) headCmp (acc (d + 7)))
        let body := ATerm.case (.bound (d + 5 - 1 - (d + 2)))
          [("nil", .case (.bound (d + 6 - 1 - (d + 3))) [("nil", acc (d + 7)), ("cons", .nat "0")]),
           ("cons", .case (.bound (d + 6 - 1 - (d + 3))) [("nil", .nat "2"), ("cons", recur)])]
        let go := ATerm.fix (cmpLam goTy (arrowTy .emptyRow goTy) (cmpLam .emptyRow goTy
          (cmpLam t (arrowTy t (arrowTy .natural .natural)) (cmpLam t (arrowTy .natural .natural)
            (cmpLam .natural .natural body))))) (.record [])
        return .app (.app (.app go (x depth)) (y depth)) (.nat "1")
      let _ := fn
      let body ← cmpTerm bound (atLevel (depth + 2)) (atLevel (depth + 3)) (depth + 4) ((k, depth, false) :: selfs)
      let fixed := ATerm.fix (cmpLam fn (arrowTy .emptyRow fn) (cmpLam .emptyRow fn
        (cmpLam t (arrowTy t .natural) (cmpLam t .natural body)))) (.record [])
      return .app (.app fixed (x depth)) (y depth)
    | .field .. | .emptyRow =>
      let body ← cmpTerm bound (atLevel (depth + 2)) (atLevel (depth + 3)) (depth + 4) ((k, depth, false) :: selfs)
      let fixed := ATerm.fix (cmpLam fn (arrowTy .emptyRow fn) (cmpLam .emptyRow fn
        (cmpLam t (arrowTy t .natural) (cmpLam t .natural body)))) (.record [])
      return .app (.app fixed (x depth)) (y depth)
    | _ => refuse "a type variable that is not a record or a sum"
  | .data => refuse "a Data value (Bend cannot read its shape)"
  | .arrow .. => refuse "a function"
  | .computation .. => refuse "an Activity"
  | _ => refuse "a specification or prototype"

/-- `λa:T. λb:T. compare a b`, closed. -/
def canonicalComparator (t : PTy) : M ATerm := do
  let body ← cmpTerm t (atLevel 0) (atLevel 1) 2 []
  return cmpLam t (arrowTy t .natural) (cmpLam t .natural body)

mutual
def expression (c : Ctx) : Nat → Expr → List Binding → Module → M ATerm
  | 0, _, _, _ => fail "elaboration fuel"
  | fuel + 1, e, env, m => withLoc e.span m do
    match e with
    | .var name =>
      if let some i := env.findIdx? (·.name == name) then return .bound i
      match lookupGlobal c name m with
      | some key => globalRef env key
      | none => fail ("unbound source variable " ++ name)
    | .nat v => return .nat v
    | .bool v => return .boolean v
    | .str v => return .label v
    | .unit => return .record []
    | .member target name =>
      if let .var alias := target then
        if !env.any (·.name == alias) then
          if let some importedModule := importOf m alias then
            let (field, key) := c.resolve m.name importedModule name
            if (declOf c key).isNone then fail ("missing imported declaration " ++ importedModule ++ "." ++ name)
            return ← globalRef env field
      if let .var "self" := target then
        if let some b := env.find? (·.name == "self") then
          if let some (.variable k) := b.ty then
            if let some bound := (← get).sumBounds.lookup k then
              if isRowTy bound && (lookupRow (some bound) name).isNone then
                fail ("refused (self-unbound-member): self." ++ name ++ " is read, but the self's type declares only {" ++
                  ", ".intercalate (rowNames bound) ++ "}")
      if let .var "super" := target then
        if let some b := env.find? (·.name == "super") then
          if let some ty := b.ty then
            let bounds := (← get).sumBounds
            let ty := match ty with
              | .variable k => (bounds.lookup k).getD ty
              | t => t
            if isRowTy ty && (lookupRow (some ty) name).isNone then
              fail ("refused (inherited-unprovided): super." ++ name ++ " is read, but nothing below this layer provides " ++
                name ++ " (inherited: {" ++ ", ".intercalate (rowNames ty) ++ "})")
      return .get (← expression c fuel target env m) name
    | .record fields =>
      if duplicate (fields.map (·.1)) then fail "duplicate record field"
      for (_, v) in fields do noActivity c fuel v env m "effect-in-field" "a record field is a shared lazy cell"
      return .record (← fieldsOf c fuel fields env m)
    | .extend inherited fields =>
      if duplicate (fields.map (·.1)) then fail "duplicate provided field"
      for (_, v) in fields do noActivity c fuel v env m "effect-in-field" "an extended field is a shared lazy cell"
      let base ← synth c fuel inherited env m
      if let some row := base.bind (recursiveRecordRow c (← get)) then
        -- A concrete recursive alias is not an open row tail. Reconstruct its known
        -- fields, sharing the inherited expression in one lazy application cell.
        -- Overridden fields never project the base; unchanged fields remain lazy.
        -- The unrestricted parameter forbids duplicating restricted captures.
        let result ← synth c fuel e env m
        let fn ← abstractWith c fuel [⟨"$extended", "_", "default"⟩] (some [base]) env
          (fun inner => do
            let provided ← fieldsOf c fuel fields inner m
            let retained := (rowNames row).filter (fun name => !(fields.map (·.1)).contains name)
            return .record (provided ++ retained.map (fun name => (name, .get (.bound 0) name))))
          "recursive record extension" (.given result) m.name
        return .app fn (← expression c fuel inherited env m)
      let i ← expression c fuel inherited env m
      let terms ← fieldsOf c fuel fields env m
      let row := expectedRow (← get) base
      let mut coerced : List (String × ATerm) := []
      for ((n, v), (n', t)) in fields.zip terms do
        coerced := coerced ++ [(n', ← coerceAt c fuel (lookupRow row n) v t env m)]
      return .extend i coerced
    | .closure params resultType bodyExpr =>
      abstract c fuel params env (fun next => expression c fuel bodyExpr next m) "closure" (.source resultType) m.name
    | .binary op left right =>
      if op == "==" || op == "!=" then
        let l ← synth c fuel left env m
        let r ← synth c fuel right env m
        if sameTy l (some .boolean) && sameTy r (some .boolean) then
          let rightTerm ← expression c fuel right env m
          let leftTerm ← expression c fuel left (⟨"$right", some .boolean, "unrestricted"⟩ :: env) m
          let reuse := if env.any (fun b => restricted b.quantity) then "once" else "reusable"
          let eq := ATerm.app (.lam ⟨some .boolean, some .boolean, "unrestricted", reuse, none⟩
            (.ifBool leftTerm (.bound 0) (notTerm (.bound 0)))) rightTerm
          return if op == "==" then eq else notTerm eq
        let primitive ← if sameTy l (some .natural) && sameTy r (some .natural) then pure "equal"
          else if sameTy l (some .label) && sameTy r (some .label) then pure "labelEqual"
          else fail (op ++ " needs both operands' types resolved to Nat, String or Bool (annotate the parameters)")
        let lt ← expression c fuel left env m
        let rt ← expression c fuel right env m
        let eq := ATerm.binary primitive lt rt
        return if op == "==" then eq else notTerm eq
      if op == "||" then
        let lt ← expression c fuel left env m
        let rt ← expression c fuel right env m
        return .ifBool lt (.boolean true) rt
      if let some primitive := negatedOrder op then
        let lt ← expression c fuel left env m
        let rt ← expression c fuel right env m
        return notTerm (.binary primitive lt rt)
      match primitiveSignature op with
      | some (primitive, _, _) =>
        let lt ← expression c fuel left env m
        let rt ← expression c fuel right env m
        return .binary primitive lt rt
      | none => fail ("unknown operator " ++ op)
    | .ite condition whenTrue whenFalse =>
      let ct ← expression c fuel condition env m
      let tt ← expression c fuel whenTrue env m
      let ft ← expression c fuel whenFalse env m
      return .ifBool ct tt ft
    | .letE name type value bodyE =>
      -- Not a tail position: the body is a pure expression even inside an activity body.
      lowerLet c fuel name type value env m false (expression c fuel value env m)
        (fun inner => expression c fuel bodyE inner m) (fun inner => synth c fuel bodyE inner m)
    | .compose specs =>
      match specs with
      | [] => fail "empty composition requires an explicit identity extension"
      | first :: rest =>
        let metaTy ← sourceType c fuel specMetaName builtinModuleName []
        let mut value ← expression c fuel first env m
        let mut valueTy ← synth c fuel first env m
        for next in rest do
          let right ← expression c fuel next env m
          let rightTy ← synth c fuel next env m
          (value, valueTy) := composeStep metaTy value valueTy right rightTy
        return value
    | .fix spec inherited =>
      let expected := (← get).fixTarget
      modify fun st => { st with fixTarget := none }
      if let some chain := fixChain c spec env m then
        if let some lowered := (← chainFix c fuel chain inherited expected env m) then return lowered
      let st ← expression c fuel spec env m
      let it ← expression c fuel inherited env m
      return .fix st it
    | .toData type value =>
      noActivity c fuel value env m "effect-in-data" "Data.of takes first-order data"
      let some declared ← sourceType c fuel type m.name []
        | fail ("Data.of::<" ++ type ++ ">: unknown type " ++ type)
      let actual ← synth c fuel value env m
      unless sameTy actual (some declared) do
        fail ("Data.of::<" ++ type ++ ">: the value is not a " ++ type)
      return .toData declared (← expression c fuel value env m)
    | .worldCall method inputText resultText argument =>
      let shown := "world." ++ method
      let some (p, _) := (← get).effect
        | fail ("refused (world-call-outside-activity): " ++ shown ++ " needs an enclosing definition whose result type is Activity<Result>")
      noActivity c fuel argument env m "effect-in-plan" "a world call's argument is data"
      let some input ← sourceType c fuel inputText m.name [] | fail (shown ++ ": unknown input type " ++ inputText)
      let some result ← sourceType c fuel resultText m.name [] | fail (shown ++ ": unknown result type " ++ resultText)
      let actual ← synth c fuel argument env m
      let term ← expression c fuel argument env m
      let saved ← get
      let (term, changed) ← if mentionsData saved.sumBounds 4096 [] input then
          coerceGo c fuel (some input) argument term env m
        else pure (term, false)
      unless changed do set saved
      if !changed && actual.isSome && !sameTy actual (some input) then
        failAt (← get).here ("refused (world-call): " ++ shown ++ " takes " ++ typeText input ++ ", not " ++
            ((actual.map typeText).getD "unresolved"))
          (some ("the argument is the input the world's protocol (`protocol world:`) declares for " ++ method))
          (some (typeText input)) (actual.map typeText)
      let world := ATerm.record [("world", .label ""), ("object", .label "world")]
      return .perform p result (.record [("object", world), ("method", .label method), ("argument", .toData input term)])
    | .call callee args =>
      if isSurfacePerform c e env m then fail withdrawnPerform
      if let some (caseLabel, moduleName, sumName) := sumCase c callee env m then
        let key := moduleName ++ "." ++ sumName
        let hasCase := match c.sum? key with
          | some (_, .sum _ cases) => cases.any (·.1 == caseLabel)
          | _ => false
        if !hasCase then
          let cases := match c.sum? key with
            | some (_, .sum _ cases) => cases.map (·.1)
            | _ => []
          throw { message := "sum " ++ key ++ " has no case " ++ caseLabel, loc := (← get).here,
                  expected := some (sumName ++ " (" ++ " | ".intercalate cases ++ ")"), found := some caseLabel,
                  hint := some ("the cases of " ++ sumName ++ " are " ++ ", ".intercalate cases) }
        if args.length > 1 then fail "a sum case carries one payload; use a record"
        if let [a] := args then noActivity c fuel a env m "effect-in-payload" "a sum payload is a shared lazy cell"
        let payload ← match args with
          | [a] => expression c fuel a env m
          | _ => pure (.record [])
        let type ← sourceType c fuel sumName moduleName []
        let payload ← match args with
          | [a] => coerceAt c fuel (lookupRow (variantRowOf (← get) type) caseLabel) a payload env m
          | _ => pure payload
        return .inject caseLabel type (if type.isSome then none else some ("sum " ++ key ++ " type unresolved")) payload
      if let .var name := callee then
        if !env.any (·.name == name) && (lookupGlobal c name m).isNone then
          if ["natText", "textLength", "sha256Text", "textConcat", "textSlice", "textSpan", "textBreak", "textHasAny", "canonicalCompare", "textTake", "textDrop", "textJoin"].contains name then
            for a in args do noActivity c fuel a env m "effect-in-text" "text operands are pure"
            match name, args with
            | "natText", [a] | "textLength", [a] | "sha256Text", [a] => return .unary name (← expression c fuel a env m)
            | "textConcat", [a,b] => return .binary "textConcat" (← expression c fuel a env m) (← expression c fuel b env m)
            | "textSpan", [a,b] | "textBreak", [a,b] | "textTake", [a,b] | "textDrop", [a,b] =>
              return .binary name (← expression c fuel a env m) (← expression c fuel b env m)
            | "canonicalCompare", [a, b] =>
              let ta ← synth c fuel a env m
              let tb ← synth c fuel b env m
              let some t := ta | fail "refused (canonical-compare): the first value's type does not resolve; annotate it"
              unless sameTy ta tb do
                fail "refused (canonical-compare): the two values are of different types; canonicalCompare orders values of one type"
              let cmp ← canonicalComparator t
              return .app (.app cmp (← expression c fuel a env m)) (← expression c fuel b env m)
            | "textHasAny", [text, words] =>
              -- The word list once, as text (`textJoin`, linear), then one pass over both.
              return .binary "textHasAny" (← expression c fuel text env m)
                (.textJoin (← expression c fuel words env m) (.label " "))
            | "textJoin", [list, separator] =>
              return .textJoin (← expression c fuel list env m) (← expression c fuel separator env m)
            | "textSlice", [a,start,count] =>
              return .binary "textTake" (.binary "textDrop" (← expression c fuel a env m) (← expression c fuel start env m)) (← expression c fuel count env m)
            | _, _ => fail (name ++ " has wrong arity")
          if name == "refuse" then
            if (← get).effect.isNone then discard <| refusal ""
            fail "refused (refuse-outside-tail): refuse(\"why\") ends the turn, so it stands only where an activity finishes"
          if ["reflect", "metadata", "targetOf"].contains name then
            match args with
            | [a] =>
              let v ← expression c fuel a env m
              return if name == "reflect" then .reflect v else if name == "metadata" then .metadata v else .project v
            | _ => fail (name ++ " expects one argument")
          if name == "prototype" then
            match args with
            | [s, t] =>
              let st ← expression c fuel s env m
              let tt ← expression c fuel t env m
              return .prototype st tt
            | _ => fail "prototype expects spec and lazy target"
      for a in args do noActivity c fuel a env m "effect-as-argument" "an argument is a shared lazy thunk"
      let mut fn ← expression c fuel callee env m
      let mut terms : List ATerm := []
      for a in args do terms := terms ++ [← expression c fuel a env m]
      if !args.isEmpty then terms ← coerceArgs c fuel callee args terms env m
      for t in terms do fn := .app fn t
      return fn

/-- A tail position of an activity body: pure results are lifted with `done`. -/
def tail (c : Ctx) : Nat → Expr → List Binding → Module → M ATerm
  | 0, _, _, _ => fail "elaboration fuel"
  | fuel + 1, e, env, m => withLoc e.span m do
    if let .fix .. := e then modify fun st => { st with fixTarget := st.resultType }
    let some (p, r) := (← get).effect | do
      coerceAt c fuel (← get).resultType e (← expression c fuel e env m) env m
    if let some reason := refuseCall c e env m then return ← refusal (← reason)
    if let .letE name type value bodyE := e then
      return ← lowerLet c fuel name type value env m true (expression c fuel value env m)
        (fun inner => tail c fuel bodyE inner m) (fun inner => synth c fuel bodyE inner m)
    if let .ite condition whenTrue whenFalse := e then
      let ct ← expression c fuel condition env m
      let tt ← tail c fuel whenTrue env m
      let ft ← tail c fuel whenFalse env m
      return .ifBool ct tt ft
    if isPerform c e env m || isComputation (← synth c fuel e env m) then
      return ← expression c fuel e env m
    let result := match (← get).resultType with
      | some (.computation _ _ a) => some a
      | _ => none
    return .done p r (← coerceAt c fuel result e (← expression c fuel e env m) env m)

/-- An open declaration's template layer at its own bounds (Self and Super its two rigid
bounded variables), elaborated once and cached: `(Self index, Super index, layer)`. The knot
field holds it, `checkTemplates` checks it rigid, and a chain's instance is `instantiate σ` of it. -/
def templateLayer (c : Ctx) : Nat → String → Decl → Module → M (Nat × Nat × ATerm)
  | 0, _, _, _ => fail "elaboration fuel"
  | fuel + 1, key, d, m => do
    if let some t := (← get).templateLayers.lookup key then return t
    let requirements ← match d with
      | .spec s => requirementsOf s
      | _ => pure []
    let some (selfVar, superVar) ← openBinding c fuel key d.binders requirements m.name
      | fail ("open declaration " ++ key ++ ": its Self/Super bounds do not resolve")
    let (.variable i, .variable j) := (selfVar, superVar)
      | fail ("open declaration " ++ key ++ ": its Self/Super variables are unresolved")
    let layer ← inDecl key <| withTypes [("Self", selfVar), ("Super", superVar)] do
      match d with
      | .spec s =>
        let some provided ← specProvided c fuel s m.name superVar
          | fail ("open spec " ++ key ++ ": a method signature does not resolve")
        layerAt c fuel s m selfVar superVar provided
      | .extension _ params targetType b _ =>
        abstract c fuel params outerEnv (fun next => body c fuel b next m) d.name (.source targetType) m.name
      | _ => fail ("open declaration " ++ key ++ ": not a spec or extension")
    modify fun st => { st with templateLayers := st.templateLayers ++ [(key, (i, j, layer))] }
    return (i, j, layer)

/-- The primary layer of plain spec `s` at final self `target` and inherited `inherited`:
`λself: target. λsuper: inherited. extend super {defs}`, typed
target → inherited → provided (provided = overlay(defs, inherited), canonical). -/
def layerAt (c : Ctx) : Nat → Spec → Module → PTy → PTy → PTy → M ATerm
  | 0, _, _, _, _, _ => fail "elaboration fuel"
  | fuel + 1, s, m, target, inherited, provided => do
    let env : List Binding := ⟨"super", some inherited, "unrestricted"⟩ :: ⟨"self", some target, "unrestricted"⟩ :: outerEnv
    let mut methods : List (String × ATerm) := []
    for method in s.methods do
      let value ← abstract c fuel method.params env (fun inner => body c fuel method.body inner m)
        method.name (.source method.resultType) m.name
      methods := methods ++ [(method.name, value)]
    abstractWith c fuel (selfSuperParams s) (some [some target, some inherited]) outerEnv
      (fun _ => pure (.extend (.bound 0) methods)) s.name (.given (some provided)) m.name

/-- `fix` over a chain of declared plain specs with a seed that is not a whole target: the
open inherited row (OB-LTUO LT2 D3). Each layer is instantiated at the row actually
beneath it (I₀ = the seed's type, Iₖ = overlay(defsₖ, Iₖ₋₁)); a layer reading `super.m`
that nothing below provides is refused by name, and the final row must be exactly the
target: a member that no layer and not the seed provides is `requires-unprovided`. A
whole-target seed (or any operand that is not a declared plain spec) keeps the closed
lowering (none). -/
def chainFix (c : Ctx) : Nat → List (String × Decl × Module) → Expr → Option PTy → List Binding → Module → M (Option ATerm)
  | 0, _, _, _, _, _ => fail "elaboration fuel"
  | fuel + 1, chain, inherited, expected, env, m => do
    let anyOpen := chain.any fun (_, d, _) => !d.binders.isEmpty
    let allClosedSpecs := chain.all fun (_, d, _) => match d with
      | .spec s => s.binders.isEmpty
      | _ => false
    if !anyOpen && !allClosedSpecs then return none
    -- The final self: every closed layer's, else the expected type, else refused.
    let mut targets : List PTy := []
    for (_, d, dm) in chain do
      if !d.binders.isEmpty then continue
      match d with
      | .spec s => if let some t ← sourceType c fuel s.targetType dm.name [] then targets := targets ++ [t]
      | .extension _ params _ _ _ => if let some t ← sourceType c fuel params[0]!.type dm.name [] then targets := targets ++ [t]
      | _ => pure ()
    let target ← match targets.head?, expected with
      | some t, _ => pure t
      | none, some e => pure e
      | none, none =>
        if anyOpen then fail ("refused (self-undetermined): every layer of this fix is open over Self; " ++
          "give the enclosing definition a result type or bind the fix with an annotated let")
        else return none
    if targets.any (fun t => !sameTy (some t) (some target)) then
      if anyOpen then fail "refused (self-conflict): the closed layers of this fix name different final selves"
      else return none
    let some seedTy ← synth c fuel inherited env m
      | if anyOpen then fail "refused (seed-unresolved): the seed's type does not resolve" else return none
    if !anyOpen && sameTy (some seedTy) (some target) then return none
    if !isRowTy seedTy then
      if anyOpen then fail "refused (seed-not-record): an open chain closes over a record seed" else return none
    let bounds := (← get).sumBounds
    -- A recursive record target is a bounded variable: discharge against its row; the last
    -- layer is annotated with the variable itself (one declared head unfolds to it).
    let targetRow := match target with
      | .variable k => (bounds.lookup k).getD target
      | t => t
    if !isRowTy targetRow then return none
    let metaTy ← sourceType c fuel specMetaName builtinModuleName []
    let mut below := seedTy.canonical
    let mut operands : List (ATerm × Option PTy) := []
    let last := chain.length - 1
    for ((key, d, dm), position) in chain.zipIdx do
      -- Open declarations: discharge the bounds at Self = target, Super = the row beneath.
      let mut bindings : List (String × PTy) := []
      if !d.binders.isEmpty then
        let requirements ← match d with
          | .spec s => requirementsOf s
          | _ => pure []
        let some (selfBound, superBound) ← boundsAt c fuel d.binders requirements dm.name target
          | fail ("open declaration " ++ key ++ ": its bounds do not resolve at this self")
        -- The read clauses of this layer's composition contract (ObjectiveBendContract.checkBounds).
        match ObjectiveBendContract.checkBounds (contractRow targetRow) (contractRow below)
            { name := key, assumes := contractRow selfBound, consumes := contractRow superBound, provides := [] } with
        | .error refusal => fail (contractRefusalText refusal)
        | .ok () => pure ()
        bindings := [("Self", target), ("Super", below)]
      let mut provided? : Option PTy := none
      let mut writes : Option (ObjectiveBendContract.Row PTy × Bool) := none
      match d with
      | .spec s =>
        let some defs ← withTypes bindings (specDefs c fuel s dm.name) | return none
        writes := some (defs.map (fun (n, t) => (n, t.canonical)), false)
        provided? := some (overDefs defs below)
      | .extension _ params targetType _ binders =>
        if binders.isEmpty then
          -- A closed extension keeps its declared types: the row beneath must be its super.
          let some inheritedTy ← sourceType c fuel params[1]!.type dm.name [] | return none
          if !sameTy (some inheritedTy) (some below) then
            fail ("refused (inherited-mismatch): extension " ++ key ++ " takes super : {" ++
              ", ".intercalate (rowNames inheritedTy) ++ "}, but the row beneath it is {" ++ ", ".intercalate (rowNames below) ++ "}")
          provided? ← sourceType c fuel targetType dm.name []
        else
          provided? := (← withTypes bindings (sourceType c fuel targetType dm.name [])).map PTy.canonical
      | _ => pure ()
      let some provided := provided? | return none
      -- The write clause of this layer's contract (ObjectiveBendContract.checkProvides): a
      -- specification's methods, or an extension's whole declared result row.
      let (provides, whole) := writes.getD (contractRow provided, true)
      match ObjectiveBendContract.checkProvides (contractRow below)
          { name := key, assumes := [], consumes := [], provides := provides, whole := whole } with
      | .error refusal => fail (contractRefusalText refusal)
      | .ok _ => pure ()
      let annotated := if position == last && (match target with | .variable _ => true | _ => false) &&
          sameTy (some provided) (some targetRow) then target else provided
      match d with
      | .extension _ _ _ _ binders =>
        if binders.isEmpty then
          operands := operands ++ [(← globalRef env key, some (arrowTy target (arrowTy below provided)))]
          below := provided
          continue
      | _ => pure ()
      let index := (key, (Json.arr #[target.json, below.json, annotated.json]).compress)
      let name ← match (← get).instances.lookup index with
        | some name => pure name
        | none => do
          let name := key ++ "@" ++ toString (← get).instances.length
          -- An open declaration's instance is its checked template at σ = {Self ↦ target,
          -- Super ↦ below}: the square `template[σ] = instance` holds by construction.
          let instanceOf := fun (arity : Nat) => do
            let (i, j, layer) ← templateLayer c fuel key d dm
            let σ := fun k => if k == i then some target else if k == j then some below else none
            pure (ATerm.retarget annotated arity (layer.instantiate σ)).1
          let (value, type) ← match d with
            | .spec s => do
              let layer ← if d.binders.isEmpty then withTypes bindings (layerAt c fuel s dm target below annotated)
                else instanceOf 2
              pure (ATerm.specification (.metadata (← globalRef outerEnv key)) layer,
                metaTy.map fun mt => PTy.specification mt (arrowTy target (arrowTy below annotated)))
            | .extension _ params _ _ _ => do
              let layer ← instanceOf params.length
              pure (layer, some (arrowTy target (arrowTy below annotated)))
            | _ => fail "internal: chain operand"
          modify fun st => { st with instances := st.instances ++ [(index, name)] }
          modify fun st => { st with hidden := st.hidden.push (name, value, type) }
          pure name
      let operandTy := match d with
        | .spec _ => metaTy.map fun mt => PTy.specification mt (arrowTy target (arrowTy below annotated))
        | _ => some (arrowTy target (arrowTy below annotated))
      operands := operands ++ [(← globalRef env name, operandTy)]
      below := annotated
    let finalRow := match below with
      | .variable k => (bounds.lookup k).getD below
      | t => t
    -- The composition contract discharged at fix (ObjectiveBendContract.close): the final row
    -- must be exactly the final self.
    match ObjectiveBendContract.close (contractRow targetRow) (contractRow finalRow) with
    | .ok () => pure ()
    | .error (.requiresUnprovided missing) =>
      let mut requiredBy : List String := []
      for (key, d, _) in chain do
        if let .spec s := d then
          if (← requirementsOf s).any (fun r => missing.contains r.name) then requiredBy := requiredBy ++ [key]
      fail (contractRefusalText (.requiresUnprovided missing) ++
        (if requiredBy.isEmpty then "" else " (required by " ++ ", ".intercalate requiredBy ++ ")"))
    | .error refusal => fail (contractRefusalText refusal)
    let some (first, firstTy) := operands.head? | return none
    let mut value := first
    let mut valueTy := firstTy
    for (right, rightTy) in operands.drop 1 do
      (value, valueTy) := composeStep metaTy value valueTy right rightTy
    return some (.fix value (← expression c fuel inherited env m))

def fieldsOf (c : Ctx) : Nat → List (String × Expr) → List Binding → Module → M (List (String × ATerm))
  | 0, _, _, _ => fail "elaboration fuel"
  | _ + 1, [], _, _ => return []
  | fuel + 1, (n, v) :: rest, env, m => do
    let t ← expression c fuel v env m
    return (n, t) :: (← fieldsOf c fuel rest env m)

def body (c : Ctx) : Nat → Body → List Binding → Module → M ATerm
  | 0, _, _, _ => fail "elaboration fuel"
  | fuel + 1, .expr e, env, m => tail c fuel e env m
  | fuel + 1, b@(.letB name type value rest), env, m => withLoc b.span m do
    lowerLet c fuel name type value env m true (expression c fuel value env m)
      (fun inner => body c fuel rest inner m) (fun inner => synthBody c fuel rest inner m)
  | fuel + 1, b@(@Body.cases scrutinee branches _ armSpans), env, m => withLoc b.span m do
    if branches.any (fun b => match b.1 with | .bool _ => true | _ => false) then
      let t := branches.find? (fun b => b.1 == .bool true)
      let f := branches.find? (fun b => b.1 == .bool false)
      match t, f with
      | some (_, tb), some (_, fb) =>
        if branches.length != 2 then fail "Bool match requires exactly true and false branches"
        let ct ← expression c fuel scrutinee env m
        let tt ← body c fuel tb env m
        let ft ← body c fuel fb env m
        return .ifBool ct tt ft
      | _, _ => fail "Bool match requires exactly true and false branches"
    if branches.any (fun b => match b.1 with | .ctor .. | .wildcard | .unexpected => true | _ => false) then
      if !branches.all (fun b => match b.1 with | .ctor .. | .wildcard | .unexpected => true | _ => false) then
        fail "a sum match takes label(binder) cases and an optional final wildcard"
      let labels := branches.filterMap (fun b => match b.1 with | .ctor l _ => some l | _ => none)
      if duplicate labels then fail "duplicate sum case"
      if isSurfacePerform c scrutinee env m then fail withdrawnPerform
      if branches.any (·.1 == .unexpected) && !isPerform c scrutinee env m then
        fail "refused (let-response): `let label(x) = ...` takes a world call: it continues with one result and refuses the turn on any other"
      let defaults := branches.filter (fun b => b.1 == .wildcard || b.1 == .unexpected)
      if defaults.length > 1 then fail "duplicate sum wildcard"
      if !defaults.isEmpty && !(branches.getLast?.map (fun b => b.1 == .wildcard || b.1 == .unexpected)).getD false then
        fail "sum wildcard must be the final case"
      let row := variantRowOf (← get) (← synth c fuel scrutinee env m)
      let some r := row | fail "sum match needs a resolved variant type"
      let rowLabels := rowNames r
      let missing := rowLabels.filter (fun l => !labels.contains l)
      let extra := labels.filter (fun l => !rowLabels.contains l)
      if (!missing.isEmpty && defaults.isEmpty) || !extra.isEmpty then
        -- Point at the first arm naming no case (else at the match), naming the cases.
        let here := (← get).here
        let arm := (branches.zip armSpans).find? fun ((p, _), _) => match p with
          | .ctor l _ => extra.contains l
          | _ => false
        let loc := match arm, here with
          | some (_, span), some h => some { h with span }
          | _, h => h
        failAt loc ("sum match is not exhaustive: missing [" ++ String.intercalate ", " missing ++ "], unknown [" ++ String.intercalate ", " extra ++ "]")
          (some ("the cases of this sum are " ++ String.intercalate ", " rowLabels ++
            (if extra.isEmpty then "; add the missing ones or a final `case _:`" else "")))
          (some ("(" ++ " | ".intercalate rowLabels ++ ")")) (if extra.isEmpty then none else some (", ".intercalate extra))
      let st ← expression c fuel scrutinee env m
      let mut arms : List (String × ATerm) := []
      for (pattern, b) in branches do
        match pattern with
        | .ctor l binder => arms := arms ++ [(l, ← body c fuel b (⟨binder, lookupRow row l, "unrestricted"⟩ :: env) m)]
        | .wildcard =>
          for l in missing do
            -- A core arm always binds one payload. Use an inaccessible name so
            -- source scope is preserved while outer de Bruijn references shift.
            arms := arms ++ [(l, ← body c fuel b (⟨"", lookupRow row l, "unrestricted"⟩ :: env) m)]
        | .unexpected =>
          -- Exactly the arms `case l(_): refuse("unexpected response l")`, in row order.
          for l in missing do
            arms := arms ++ [(l, ← refusal ("unexpected response " ++ l))]
        | _ => pure ()
      return .case st arms
    let zero := branches.find? (fun b => b.1 == .zero)
    let succ := branches.find? (fun b => match b.1 with | .succ _ => true | _ => false)
    match zero, succ with
    | some (_, zb), some (.succ binder, sb) =>
      if branches.length != 2 then fail "Nat match currently requires exactly zero and successor branches"
      let vt ← expression c fuel scrutinee env m
      let zt ← body c fuel zb env m
      let st ← body c fuel sb (⟨binder, some .natural, "unrestricted"⟩ :: env) m
      return .ifZero vt zt st
    | _, _ => fail "Nat match currently requires exactly zero and successor branches"
end

def layer (c : Ctx) (fuel : Nat) (s : Spec) (m : Module) (group : String) : M ATerm := do
  let target ← sourceType c fuel s.targetType m.name []
  let selfSuper := selfSuperEnv target
  let mut methods : List (String × ATerm) := []
  for method in s.methods.filter (fun x => qualifierGroup x.qualifier == group) do
    let n := method.params.length
    let value ← abstract c fuel method.params selfSuper (fun inner => do
      let own ← body c fuel method.body inner m
      match combination method.qualifier with
      | none => return own
      | some (primitive, _) =>
        let mut next := ATerm.get (.bound n) method.name
        for i in List.range n do next := .app next (.bound (n - 1 - i))
        return .binary primitive own next) method.name (.source method.resultType) m.name
    methods := methods ++ [(method.name, value)]
  -- A recursive record target is a bounded variable: `extend` would keep the variable as
  -- an open tail, which is not the record. Rebuild the record from its bound instead:
  -- every field is the layer's method or the lazy `super.f` (same laziness as extend).
  let bounds := (← get).sumBounds
  let recursiveRow : Option PTy := match target with
    | some (.variable k) => match bounds.lookup k with
      | some row@(.field ..) => some row
      | _ => none
    | _ => none
  let provided := match recursiveRow with
    | some row => ATerm.record ((rowNames row).map fun f => (f, (methods.lookup f).getD (.get (.bound 0) f)))
    | none => ATerm.extend (.bound 0) methods
  abstract c fuel (selfSuperParams s) outerEnv (fun _ => pure provided) s.name (.source s.targetType) m.name

def layerRef (c : Ctx) (key group : String) : M ATerm := do
  let some (s, _) := specOf c key | fail ("internal: unknown spec " ++ key)
  globalRef outerEnv (if plainSpec s && group == "primary" then key else key ++ "#" ++ group)

def shiftRef (t : ATerm) (by_ : Nat) : M ATerm :=
  match t with
  | .get (.bound i) n => pure (.get (.bound (i + by_)) n)
  | _ => fail "internal: only global references are shifted"

def interfaceLabel (s : Spec) (list : List String) : String :=
  (Json.mkObj ([("targetType", toJson s.targetType), ("suffix", toJson s.suffix), ("parents", toJson s.parents),
    ("precedence", toJson list), ("requirements", Json.arr (s.requirements.map (·.json)).toArray),
    ("methods", Json.arr (s.methods.map fun m => Json.mkObj (m.authored.fields ++
      [("qualifier", toJson m.qualifier)])).toArray)] ++
    (if s.binders.isEmpty then [] else [("binders", toJson s.binders)]))).compress

/-- Claims and the declared SpecMeta around a spec's extension. -/
def finishSpecification (c : Ctx) (fuel : Nat) (s : Spec) (m : Module) (key : String) (list : List String)
    (extension : ATerm) : M ATerm := do
  -- Each claim is checked code in its own hidden knot field `key#claim#name` (typed over
  -- self, super and its parameters, result Bool); the metadata records its name and
  -- status. Status `unchecked`: typed, retained, never evaluated (LT6 owns discharge).
  if duplicate (s.claims.map (·.name)) then fail ("duplicate claim in spec " ++ key)
  let claimsMeta ← sourceType c fuel specClaimsName builtinModuleName []
  let claimsReason := if claimsMeta.isSome then none else some "SpecClaims type unresolved"
  let mut claimList : ATerm := .inject "none" claimsMeta claimsReason (.record [])
  for claim in s.claims.reverse do
    claimList := .inject "claim" claimsMeta claimsReason
      (.record [("name", .label claim.name), ("status", .label "unchecked"), ("rest", claimList)])
  for claim in s.claims do
    let params := selfSuperParams s ++ claim.params
    let code ← abstract c fuel params outerEnv
      (fun inner => expression c fuel claim.body inner m) claim.name (.source "Bool") m.name
    let type ← signatureTy c fuel params (.given (some .boolean)) m.name []
    modify fun st => { st with hidden := st.hidden.push (key ++ "#claim#" ++ claim.name, code, type) }
  let metaTy ← sourceType c fuel specMetaName builtinModuleName []
  let metadata := ATerm.inject "declared" metaTy (if metaTy.isSome then none else some "SpecMeta type unresolved")
    (.record [("name", .label key), ("interface", .label (interfaceLabel s list)), ("claims", claimList)])
  return .specification metadata extension

def specification (c : Ctx) (fuel : Nat) (s : Spec) (m : Module) : M ATerm := do
  checkSpecMethods s
  let key := m.name ++ "." ++ s.name
  if !s.binders.isEmpty then
    -- An open spec: checked once at its own bounds; its knot field is that instance.
    let some (selfVar, superVar) ← openBinding c fuel key s.binders (← requirementsOf s) m.name
      | fail ("open spec " ++ key ++ ": its Self/Super bounds do not resolve")
    let (_, _, layer) ← templateLayer c fuel key (.spec s) m
    return ← withTypes [("Self", selfVar), ("Super", superVar)] (finishSpecification c fuel s m key [key] layer)
  let target ← sourceType c fuel s.targetType m.name []
  -- `requires` is checked: a requirement is a member of the closed target, at its type.
  if let some t := target then
    for r in ← requirementsOf s do
      let rt ← signatureTy c fuel r.params (.source r.resultType) m.name []
      match lookupRow (some t) r.name with
      | none => fail ("refused (requires-unprovided): spec " ++ key ++ " requires " ++ signatureText r ++
          ", which " ++ s.targetType ++ " does not declare")
      | some mt => if !sameTy rt (some mt) then
          fail ("refused (requires-signature): spec " ++ key ++ " requires " ++ signatureText r ++
            ", but " ++ s.targetType ++ "." ++ r.name ++ " has another type")
  let list ← precedence c fuel key
  let extension ← if plainSpec s then layer c fuel s m "primary" else do
    for ancestor in list do
      let some (a, am) := specOf c ancestor | fail "internal"
      if target.isSome && !sameTy (← sourceType c fuel a.targetType am.name []) target then
        fail ("ancestor " ++ ancestor ++ " targets " ++ a.targetType ++ "; declared ancestry composes one target type (" ++ s.targetType ++ ")")
    for group in ["primary", "around"] do
      if hasLayer s group then
        let l ← layer c fuel s m group
        modify fun st => { st with hidden := st.hidden.push (key ++ "#" ++ group, l, target.map extensionTy) }
    let mut qualifiers : List (String × String × Method × String) := []
    for ancestor in list do
      let some (a, am) := specOf c ancestor | fail "internal"
      for method in a.methods do
        if qualifierGroup method.qualifier != "primary" then continue
        match qualifiers.find? (·.1 == method.name) with
        | some (_, q, _, _) =>
          if q != method.qualifier then
            fail ("method " ++ method.name ++ " is " ++ q ++ " in one ancestor and " ++ method.qualifier ++ " in another of " ++ key)
        | none => qualifiers := qualifiers ++ [(method.name, method.qualifier, method, am.name)]
    let mut layers : List ATerm := []
    for (name, q, method, moduleName) in qualifiers do
      let some (_, zero) := combination q | continue
      let init ← abstract c fuel method.params (selfSuperEnv target) (fun _ => pure zero) method.name (.source method.resultType) moduleName
      layers := layers ++ [← abstract c fuel (selfSuperParams s) outerEnv (fun _ => pure (.extend (.bound 0) [(name, init)])) s.name (.source s.targetType) m.name]
    for group in ["primary", "around"] do
      for ancestor in list.reverse do
        let some (a, _) := specOf c ancestor | fail "internal"
        if hasLayer a group then layers := layers ++ [← layerRef c ancestor group]
    match layers with
    | [] => fail ("spec " ++ key ++ " and its ancestors provide no methods")
    | [only] =>
      let shifted ← shiftRef only 2
      abstract c fuel (selfSuperParams s) outerEnv (fun _ => pure (.app (.app shifted (.bound 1)) (.bound 0))) s.name (.source s.targetType) m.name
    | first :: rest => pure (rest.foldl (fun lower upper => .mix lower upper) first)
  finishSpecification c fuel s m key list extension


/-! ## The package knot and entry selection -/

def resultOf : Option PTy → Nat → Option PTy
  | t, 0 => t
  | some (.arrow _ _ _ cod), n + 1 => resultOf (some cod) n
  | _, _ + 1 => none

structure Output where
  term : ATerm
  /-- Every declaration of the closure at its type: the method table and law shape read it. -/
  globalRow : Option PTy
  /-- The packet's knot: only the fields the entry reaches (`reachableKnot`). -/
  knotRow : Option PTy := globalRow
  sumBounds : List (Nat × PTy)
  typeErrors : Array String
  /-- The open declarations' templates (`St.templates`). -/
  templates : List (String × List Nat × ATerm) := []

/-- One declaration of the package knot: its field and the hidden layer fields it created. -/
def emitDecl (c : Ctx) (fuel : Nat) (m : Module) (d : Decl) (fields : List (String × ATerm)) : M (List (String × ATerm)) := do
  match d with
  | .record .. | .sum .. => return fields
  | _ => pure ()
  let key := m.name ++ "." ++ d.name
  if let .function _ _ resultType _ := d then
    let r := trimStr resultType
    if r.startsWith "Activity<" && r.endsWith ">" &&
        (splitTop (dropEndStr (dropStr r "Activity<".length) 1) ",").length == 3 then
      fail ("refused (old-dialect): Activity<Plan, Response, Result> is withdrawn; write Activity<Result> " ++
        "and yield by world calls (docs/WHOLENESS.md section 1)")
  if let .function _ [] resultType _ := d then
    if (trimStr resultType).startsWith "Activity<" then
      fail ("refused (nullary-activity): " ++ key ++ " has no parameters, so it is a shared lazy value; an Activity needs a parameter, e.g. (start: {})")
  let value ← inDecl key <| match d with
    | .reexport _ target => do
      let some (alias, name) := qualifiedName target | fail ("invalid export target " ++ target)
      let some origin := importOf m alias | fail ("unknown export import alias " ++ target)
      globalRef outerEnv (origin ++ "." ++ name)
    | .function _ params resultType b => do
      let result ← if resultType == "_" then do pure (ResultSpec.given (resultOf (← globalType c fuel key) params.length))
        else pure (ResultSpec.source resultType)
      let value ← abstract c fuel params outerEnv (fun next => body c fuel b next m) d.name result m.name
      if params.isEmpty then
        -- Convert the declared result before nesting it in the global record.
        -- A nullary constant is still a shared lazy value; this closed identity
        -- uses the existing checked application conversion, not deeper equality.
        let target ← match result with
          | .source text => sourceType c fuel text m.name []
          | .given ty => pure ty
        let reason := if target.isNone then some ("nullary result type of " ++ key ++ " is not resolvable") else none
        pure (.app (.lam ⟨target, target, "unrestricted", "reusable", reason⟩ (.bound 0)) value)
      else pure value
    | .extension _ params targetType b binders =>
      if binders.isEmpty then abstract c fuel params outerEnv (fun next => body c fuel b next m) d.name (.source targetType) m.name
      else do
        -- Checked once, at its own bounds (Self and Super the two rigid bounded variables);
        -- every chain instance is this template at its σ.
        let (_, _, layer) ← templateLayer c fuel key d m
        pure layer
    | .spec s => specification c fuel s m
    | _ => fail "unsupported declaration"
  if !d.binders.isEmpty then
    match (← get).openBounds.lookup key with
    | some (.variable k, .variable j) => modify fun st => { st with templates := st.templates ++ [(key, [k, j], value)] }
    | _ => fail ("open declaration " ++ key ++ ": its Self variable is unresolved")
  let mut fields := fields
  match c.overrides[key]? with
  | some over =>
    -- Overridden by a layer above: the field answers with the override; the body stays
    -- reachable below it (for `Super`).
    let below := key ++ belowSuffix
    let mine ← globalType c fuel key
    modify fun st => { st with globalTypes := st.globalTypes.insertIfNew below mine }
    fields := fields ++ [(key, ← globalRef outerEnv over), (below, value)]
  | none => fields := fields ++ [(key, value)]
  for (name, value, type) in (← get).hidden do
    fields := fields ++ [(name, value)]
    modify fun st => { st with globalTypes := st.globalTypes.insertIfNew name type }
  modify fun st => { st with hidden := #[] }
  return fields

/-- The knot keys a term names: every global reference is `globalRef`, a `get` of the
knot by key, so these are exactly the declarations the term can reach (every other
`get` name is harmless: it names no knot field, or one that is reached anyway). -/
partial def knotNames (t : ATerm) (acc : Array String) : Array String :=
  match t with
  | .get target name => knotNames target (acc.push name)
  | .located _ t => knotNames t acc
  | .bound _ | .nat _ | .boolean _ | .label _ | .refuse _ _ => acc
  | .lam _ b | .reflect b | .metadata b | .project b | .unary _ b | .inject _ _ _ b | .perform _ _ b
  | .done _ _ b | .toData _ b => knotNames b acc
  | .app a b | .mix a b | .fix a b | .specification a b | .prototype a b | .binary _ a b | .textJoin a b =>
    knotNames b (knotNames a acc)
  | .ifZero a b c | .ifBool a b c => knotNames c (knotNames b (knotNames a acc))
  | .extend i fs => fs.foldl (fun acc (_, v) => knotNames v acc) (knotNames i acc)
  | .record fs => fs.foldl (fun acc (_, v) => knotNames v acc) acc
  | .case s arms => arms.foldl (fun acc (_, v) => knotNames v acc) (knotNames s acc)

/-- A whole closure elaborated once: every knot field with the knot keys it names, the
field types, and the elaborator's final state. Selecting an entry (`Elaborated.select`)
reuses it; nothing here depends on the entry. -/
structure Elaborated where
  ctx : Ctx
  fields : List (String × ATerm)
  references : Std.HashMap String (Array String)
  rowFields : List (String × PTy)
  unresolved : List String
  state : St

/-- The knot fields `entryKey` reaches, transitively (recursion included), in declaration
order. A spec's claims (`key#claim#name`) are kept with their spec: nothing references
them, and they are typed only as knot fields. The packet carries no unreachable
declaration (they are checked once per closure, `Elaborated.whole`). -/
def Elaborated.reachable (e : Elaborated) (entryKey : String) : List (String × ATerm) := Id.run do
  let mut seen : Std.HashSet String := {}
  let mut work : Array String := #[entryKey]
  while h : work.size > 0 do
    let key := work[work.size - 1]
    work := work.pop
    if seen.contains key then continue
    seen := seen.insert key
    for name in e.references.getD key #[] do
      if !seen.contains name then work := work.push name
  let claimed := fun (key : String) => match key.splitOn "#claim#" with
    | [owner, _] => seen.contains owner
    | _ => false
  return e.fields.filter fun (key, _) => seen.contains key || claimed key

/-- An override keeps the declared type of what it overrides; refused by name, at the override. -/
def checkOverrides (c : Ctx) (fuel : Nat) : M Unit := do
  for (below, over) in c.overrides.toList do
    let mine ← globalType c fuel below
    let theirs ← globalType c fuel over
    unless sameTy mine theirs do
      let shown := fun (t : Option PTy) => match t with
        | some t => typeText t
        | none => "unresolved"
      let loc : Option Loc := match declOf c over with
        | some (.function _ _ _ body, m) => some ⟨m.name, over, body.span⟩
        | _ => none
      failAt loc ("refused (layer-override): " ++ over ++ " is " ++ shown theirs ++ ", but it overrides " ++ below ++
        ", which is " ++ shown mine ++ "; an override keeps the type it overrides")
        (some ("give " ++ over ++ " the signature of " ++ below ++ ", or name it differently to add a method"))
        (shown mine) (shown theirs)

/-! ## Protocols

`protocol P:` lists methods with their types; `State`, `Plan` and `Response` in them are the
implementer's, so they are placeholders a claim binds consistently across the protocol's
methods (`matchProtocol`). `implements P` is checked here, after every declaration's type
is known: a missing method, or one whose type does not match, is refused by name. -/

/-- The placeholder variable a protocol's free type name stands for. -/
def protocolFree : List String := ["State", "Plan", "Response"]
def protocolVariable (i : Nat) : Nat := 1099511627776 + i

/-- Match a protocol type (placeholders free) against an implementation's, binding each
placeholder once. -/
partial def matchProtocol (pattern actual : PTy) (σ : List (Nat × PTy)) : Option (List (Nat × PTy)) :=
  match pattern, actual with
  | .variable i, t =>
    if i ≥ protocolVariable 0 then
      match σ.lookup i with
      | some bound => if bound.canonical == t.canonical then some σ else none
      | none => some ((i, t) :: σ)
    else if t == .variable i then some σ else none
  | .arrow r q d c, .arrow r' q' d' c' =>
    if r == r' && q == q' then (matchProtocol d d' σ).bind (matchProtocol c c' ·) else none
  | .field .., .field .. =>
    let p := pattern.canonical
    let a := actual.canonical
    match p, a with
    | .field n m t, .field n' m' t' => if n == n' then (matchProtocol m m' σ).bind (matchProtocol t t' ·) else none
    | _, _ => none
  | .specification a b, .specification a' b' | .prototype a b, .prototype a' b' =>
    (matchProtocol a a' σ).bind (matchProtocol b b' ·)
  | .variant r, .variant r' => matchProtocol r r' σ
  | .computation p r a, .computation p' r' a' =>
    ((matchProtocol p p' σ).bind (matchProtocol r r' ·)).bind (matchProtocol a a' ·)
  | p, a => if p == a then some σ else none

/-- The protocol `name` names from module `m`: `Alias.P`, a protocol of `m` itself, of the
import aliased `P`, or of any import. -/
def protocolOf (c : Ctx) (m : Module) (name : String) :
    Option (Module × String × List (String × String × String × ObjectiveBendSurface.Span)) :=
  let inModule := fun (module p : String) => (moduleNamed c module).bind fun pm => (pm.protocols.lookup p).map (pm, p, ·)
  match name.splitOn "." with
  | [alias, p] => (importOf m alias).bind (inModule · p)
  | [p] => (inModule m.name p).orElse fun _ => ((importOf m p).bind (inModule · p)).orElse fun _ =>
      m.imports.findSome? fun (_, module) => inModule module p
  | _ => none

/-- The protocols each module claims, checked. -/
def checkProtocols (c : Ctx) (fuel : Nat) : M Unit := do
  for m in c.modules do
    for (name, span) in m.implements do
      let claim : Option Loc := some ⟨m.name, m.name, span⟩
      let some (pm, pname, methods) := protocolOf c m name
        | failAt claim ("refused (protocol): " ++ m.name ++ " implements " ++ name ++ ", which no module it imports declares")
            (some "a protocol is declared `protocol NAME:` with `name: TYPE` lines, in a module the implementer imports")
      let placeholders := protocolFree.zipIdx.map fun (n, i) => (n, PTy.variable (protocolVariable i))
      let mut σ : List (Nat × PTy) := []
      for (method, resolved, declared, _) in methods do
        let key := m.name ++ "." ++ method
        let some expected ← withTypes placeholders (sourceType c fuel resolved pm.name [])
          | failAt claim ("refused (protocol): " ++ pname ++ "." ++ method ++ " has a type that does not resolve: " ++ declared)
        match declOf c key with
        | none =>
          failAt claim ("refused (protocol): " ++ m.name ++ " implements " ++ pname ++ " but defines no " ++ method ++
              "; " ++ pname ++ " declares " ++ method ++ ": " ++ declared)
            (some ("add `def " ++ method ++ "` with the type protocol " ++ pname ++ " gives it: " ++ declared))
            (some declared) (some "nothing")
        | some (d, dm) =>
          let found ← globalType c fuel key
          let at_ : Option Loc := match d with
            | .function _ _ _ body => some ⟨dm.name, key, body.span⟩
            | _ => claim
          match found.bind (matchProtocol expected · σ) with
          | some σ' => σ := σ'
          | none =>
            failAt at_ ("refused (protocol): " ++ key ++ " is " ++ ((found.map typeText).getD "unresolved") ++
                ", but protocol " ++ pname ++ " declares " ++ method ++ ": " ++ declared)
              (some ("give " ++ method ++ " the type protocol " ++ pname ++ " declares (State, Plan and Response are this module's, the same in every method)"))
              (some declared) (found.map typeText)

/-- The protocols module `m` claims (each by its declared name) with their methods' names. -/
def Ctx.claims (c : Ctx) (m : Module) : List (String × List String) :=
  m.implements.filterMap fun (name, _) => (protocolOf c m name).map fun (_, p, methods) => (p, methods.map (·.1))

def elaboratePackageM (c : Ctx) : M (List (String × ATerm) × List (String × PTy) × List String) := do
  let fuel := 100000
  checkOverrides c fuel
  let mut fields : List (String × ATerm) := []
  for m in c.modules do
    for d in m.decls do
      fields ← emitDecl c fuel m d fields
  checkProtocols c fuel
  let mut rowFields : List (String × PTy) := []
  let mut unresolved : List String := []
  for (name, _) in fields do
    match ← globalType c fuel name with
    | some t => rowFields := rowFields ++ [(name, t)]
    | none => unresolved := unresolved ++ [name]
  return (fields, rowFields, unresolved)

/-- The knot over `knot`'s fields: `fix` of the package specification. -/
def Elaborated.root (e : Elaborated) (knot : List (String × ATerm)) : ATerm :=
  let reason := if e.unresolved.isEmpty then none
    else some ("declaration types unresolved: " ++ String.intercalate ", " e.unresolved)
  let rootExtension := ATerm.lam ⟨some (.variable 0), some (arrowTy .emptyRow (.variable 0)), "unrestricted", "reusable", reason⟩
    (.lam ⟨some .emptyRow, some (.variable 0), "unrestricted", "reusable", reason⟩ (.extend (.bound 0) knot))
  let packageLabel := (toJson (e.ctx.modules.map (·.name))).compress
  ATerm.fix (.specification (.record [("package", .label packageLabel)]) rootExtension) (.record [])

def Elaborated.globalRow (e : Elaborated) : Option PTy :=
  if e.unresolved.isEmpty then some (PTy.row e.rowFields) else none

/-- The whole closure as one term (every declaration, every template): what is checked
once per package so that pruning an entry's packet never skips checking a declaration. -/
def Elaborated.whole (e : Elaborated) : Output :=
  { term := e.root e.fields, globalRow := e.globalRow, knotRow := e.globalRow, sumBounds := e.state.sumBounds,
    typeErrors := e.state.typeErrors, templates := e.state.templates }

/-- Select an entry of an elaborated closure: its reached knot, applied to `args`. -/
def Elaborated.select (e : Elaborated) (entryModule : Nat) (entryDefinition : String) : Except String Output := do
  let some entry := e.ctx.modules[entryModule]? | throw "missing selected entry"
  let entryKey := entry.name ++ "." ++ entryDefinition
  -- A layer's entry it does not define is the topmost definition below it.
  let entryKey := if (declOf e.ctx entryKey).isSome then entryKey else
    (e.ctx.stack.toList.reverse.findSome? fun m =>
      let k := m ++ "." ++ entryDefinition; if (declOf e.ctx k).isSome then some k else none).getD entryKey
  if (declOf e.ctx entryKey).isNone then throw "missing selected entry"
  let knot := e.reachable entryKey
  let kept : Std.HashSet String := knot.foldl (fun set (k, _) => set.insert k) {}
  let globalRow := e.globalRow
  let knotRow := globalRow.map fun _ => PTy.row (e.rowFields.filter fun (k, _) => kept.contains k)
  let selected := ATerm.get (e.root knot) entryKey
  return { term := selected, globalRow, knotRow, sumBounds := e.state.sumBounds, typeErrors := e.state.typeErrors,
           templates := e.state.templates.filter fun (key, _, _) => kept.contains key }

/-- The built-in module: `builtinSource` through the parser. -/
def builtinModule : Except String Module := do
  let ast ← match ObjectiveBendParse.parseObjective builtinSource with
    | .ok ast => pure ast
    | .error d => throw ("builtin: " ++ d.message)
  ofSurface builtinModuleName [] ast

/-- Build the context; duplicate declarations / types refuse as in the TS. The built-in
module contributes types only (no declaration of it is emitted). -/
def context (modules : List Module) : Except String Ctx := do
  let mut decls : List (String × Decl × Module) := []
  let mut records : List (String × Decl) := []
  let mut sums : List (String × Decl) := []
  for m in modules do
    for d in m.decls do
      let key := m.name ++ "." ++ d.name
      match d with
      | .record .. | .sum .. => pure ()
      | _ =>
        if (decls.find? (·.1 == key)).isSome then throw ("duplicate declaration " ++ key)
        match d with
        | .reexport _ target =>
          if m.imports.any (·.1 == d.name) then throw ("export collides with import alias " ++ key)
          let some (alias, name) := qualifiedName target | throw ("export requires Alias.name: " ++ target)
          let some origin := importOf m alias | throw ("unknown export import alias " ++ target)
          let targetKey := origin ++ "." ++ name
          let some (_, original, definingModule) := decls.find? (·.1 == targetKey)
            | throw ("export target is not an earlier imported value declaration: " ++ target)
          match original with
          | .function .. => pure ()
          | _ => throw ("export currently requires a function or constant declaration: " ++ target)
          if m.decls.any (fun other => other.name == d.name && match other with | .record .. | .sum .. => true | _ => false) then
            throw ("export collides with source type " ++ key)
          decls := decls ++ [(key, original, definingModule)]
        | _ => decls := decls ++ [(key, d, m)]
  for m in modules ++ [← builtinModule] do
    for d in m.decls do
      let key := m.name ++ "." ++ d.name
      match d with
      | .record .. | .sum .. =>
        if (records.find? (·.1 == key)).isSome || (sums.find? (·.1 == key)).isSome then throw ("duplicate type " ++ key)
        if m.name != builtinModuleName && builtinTypeNames.contains d.name then
          throw ("refused (builtin-type): " ++ d.name ++ " is the built-in specification metadata type; choose another name")
        match d with
        | .record .. => records := records ++ [(key, d)]
        | _ => sums := sums ++ [(key, d)]
      | _ => pure ()
  let index := fun {α : Type} (entries : List (String × α)) =>
    entries.foldl (fun (map : Std.HashMap String α) (key, value) =>
      if map.contains key then map else map.insert key value) {}
  -- The layer stack: its top is the last layer no other layer is over (the entry module;
  -- the generics pass appends its generated module after it), then what each is over.
  let mut stack : List String := []
  let mut current := (modules.filter fun m => m.layerOver.isSome &&
    !modules.any (·.layerOver == some m.name)).getLast?
  for _ in [0:modules.length] do
    let some m := current | break
    if stack.contains m.name then throw ("refused (layer-cycle): " ++ m.name ++ " is a layer over itself")
    stack := m.name :: stack
    current := m.layerOver.bind fun below => modules.find? (·.name == below)
  if stack.length < 2 then stack := []
  let declIndex := index decls
  let functionsOf := fun (name : String) => match modules.find? (·.name == name) with
    | some m => m.decls.filterMap fun (d : Decl) => match d with | .function f .. => some f | _ => none
    | none => []
  let mut overrides : Std.HashMap String String := {}
  for i in [1:stack.length] do
    let some layer := stack[i]? | continue
    for f in functionsOf layer do
      let below := (List.range i).reverse.findSome? fun j =>
        stack[j]?.bind fun m => if (functionsOf m).contains f then some (m ++ "." ++ f) else none
      if let some b := below then overrides := overrides.insert b (layer ++ "." ++ f)
  return { modules, decls, records, sums, declIndex, recordIndex := index records, sumIndex := index sums,
           stack := stack.toArray, overrides }

/-- Elaborate every declaration of a closure once; a refusal says where it was raised. -/
def elaboratePackageLocated (modules : List Module) : Except Refusal Elaborated := do
  let c ← (context modules).mapError fun message => ({ message } : Refusal)
  let ((fields, rowFields, unresolved), state) ← (elaboratePackageM c).run {}
  let references := fields.foldl (fun (map : Std.HashMap String (Array String)) (key, value) =>
    map.insert key (knotNames value #[])) {}
  return ⟨c, fields, references, rowFields, unresolved, state⟩

def elaboratePackage (modules : List Module) : Except String Elaborated :=
  (elaboratePackageLocated modules).mapError (·.message)

def elaborate (modules : List Module) (entryModule : Nat) (entryDefinition : String) :
    Except String Output := do
  (← elaboratePackage modules).select entryModule entryDefinition

/-! ## The typing proposal (literalAnnotations) -/

structure Annotation where
  path : List Nat
  domain : PTy
  codomain : PTy
  parameter : String
  reuse : String

mutual
def annotate (bounds : List (Nat × PTy)) : ATerm → List Nat → Except String (List Annotation)
  | .located _ t, path => annotate bounds t path
  | .lam p b, path => do
    let some d := p.domain | throw (p.reason.getD "unresolved lambda type")
    let some cod := p.codomain | throw (p.reason.getD "unresolved lambda type")
    return ⟨path, d, cod, p.parameter, p.reuse⟩ :: (← annotate bounds b (path ++ [0]))
  | .inject l type reason payload, path => do
    let some t := type | throw (reason.getD "injection has no declared sum type")
    let variant := match t with
      | .variable i => bounds.lookup i
      | other => some other
    let some (.variant row) := variant | throw "injection has no declared sum type"
    let some d := lookupRow (some row) l | throw ("injection label " ++ l ++ " absent from its declared sum")
    -- The codomain is the DECLARED sum type: a recursive sum stays its bounded variable.
    return ⟨path, d, t, "unrestricted", "reusable"⟩ :: (← annotate bounds payload (path ++ [0]))
  | .perform p r v, path | .done p r v, path => do
    return ⟨path, p, r, "unrestricted", "reusable"⟩ :: (← annotate bounds v (path ++ [0]))
  | .toData _ v, path => annotate bounds v (path ++ [0])
  | .refuse t _, path => return [⟨path, t, t, "unrestricted", "reusable"⟩]
  | .textJoin l s, path => return (← annotate bounds l (path ++ [0])) ++ (← annotate bounds s (path ++ [1]))
  | .app f a, path => return (← annotate bounds f (path ++ [0])) ++ (← annotate bounds a (path ++ [1]))
  | .fix s i, path => return (← annotate bounds s (path ++ [0])) ++ (← annotate bounds i (path ++ [1]))
  | .mix l u, path => return (← annotate bounds l (path ++ [0])) ++ (← annotate bounds u (path ++ [1]))
  | .unary _ a, path => annotate bounds a (path ++ [0])
  | .binary _ l r, path => return (← annotate bounds l (path ++ [0])) ++ (← annotate bounds r (path ++ [1]))
  | .prototype s t, path => return (← annotate bounds s (path ++ [0])) ++ (← annotate bounds t (path ++ [1]))
  | .specification md e, path => return (← annotate bounds md (path ++ [0])) ++ (← annotate bounds e (path ++ [1]))
  | .reflect v, path | .metadata v, path | .project v, path => annotate bounds v (path ++ [0])
  | .get t _, path => annotate bounds t (path ++ [0])
  | .ifZero v z s, path => return (← annotate bounds v (path ++ [0])) ++ (← annotate bounds z (path ++ [1])) ++ (← annotate bounds s (path ++ [2]))
  | .ifBool v z s, path => return (← annotate bounds v (path ++ [0])) ++ (← annotate bounds z (path ++ [1])) ++ (← annotate bounds s (path ++ [2]))
  | .case s arms, path => return (← annotate bounds s (path ++ [0])) ++ (← annotateFields bounds arms (path ++ [1]) 0)
  | .record fs, path => annotateFields bounds fs path 0
  | .extend i fs, path => return (← annotate bounds i (path ++ [0])) ++ (← annotateFields bounds fs (path ++ [1]) 0)
  | _, _ => return []
def annotateFields (bounds : List (Nat × PTy)) : List (String × ATerm) → List Nat → Nat → Except String (List Annotation)
  | [], _, _ => return []
  | (_, v) :: rest, path, i => return (← annotate bounds v (path ++ [i])) ++ (← annotateFields bounds rest path (i + 1))
end

/-! ### The shared type table

Every composite type is one table
entry whose children are inline leaves or `{tag:"ref", index}` to an earlier entry;
identical entries are stored once. Entries are created in post-order (children
before parent, in the fixed order of each constructor's fields), walking the
annotations in order (domain, then codomain), then the global bound, then the sum
bounds. The order is a contract (the checker decodes refs to earlier entries only). -/

/-- A table slot: an inline leaf, or a reference to an earlier table entry. -/
inductive Slot where
  | leaf (t : PTy)
  | ref (index : Nat)
  deriving BEq, Hashable

def Slot.json : Slot → Json
  | .leaf t => t.json
  | .ref index => Json.mkObj [("tag", "ref"), ("index", toString index)]

/-- A composite type node with its children already interned: equal keys are equal entries,
and a key hashes in constant time (no subtree is serialized or rehashed). -/
inductive InternKey where
  | arrow (reuse parameter : String) (domain codomain : Slot)
  | field (name : String) (member tail : Slot)
  | specification (metadata extension : Slot)
  | prototype (spec target : Slot)
  | variant (row : Slot)
  | computation (plan response result : Slot)
  deriving BEq, Hashable

def InternKey.json : InternKey → Json
  | .arrow r q d c => Json.mkObj [("tag", "arrow"), ("reuse", r), ("parameter", q), ("domain", d.json), ("codomain", c.json)]
  | .field n m t => Json.mkObj [("tag", "field"), ("name", n), ("member", m.json), ("tail", t.json)]
  | .specification m e => Json.mkObj [("tag", "specification"), ("metadata", m.json), ("extension", e.json)]
  | .prototype s t => Json.mkObj [("tag", "prototype"), ("spec", s.json), ("target", t.json)]
  | .variant r => Json.mkObj [("tag", "variant"), ("row", r.json)]
  | .computation p r a => Json.mkObj [("tag", "computation"), ("plan", p.json), ("response", r.json), ("result", a.json)]

structure Interner where
  table : Array Json := #[]
  seen : Std.HashMap InternKey Nat := {}
  /-- The slot of each composite type object already walked, by its address: read and written
  only by the compiled `PTy.internSlot` (`internSlotShared`); the definition never touches it.
  Sound because one interning walks objects that all exist before it starts (it allocates no
  `PTy`), so an address names one object for the whole walk. An `Interner` is never reused
  across walks. -/
  shared : Std.HashMap USize Slot := {}

abbrev InternM := StateM Interner

def internNode (key : InternKey) : InternM Slot := do
  let s ← get
  match s.seen[key]? with
  | some i => return .ref i
  | none =>
    set ({ s with table := s.table.push key.json, seen := s.seen.insert key s.table.size } : Interner)
    return .ref s.table.size

/-- `PTy.internSlot`, walking each shared subtree once: the elaborator builds a type once and
refers to it from many annotations, so a type object met again has its slot already. -/
unsafe def PTy.internSlotShared (t : PTy) : InternM Slot := do
  match t with
  | .natural | .boolean | .label | .emptyRow | .variable _ | .data => return .leaf t
  | _ =>
    let address := ptrAddrUnsafe t
    if let some slot := (← get).shared[address]? then return slot
    let slot ← match t with
      | .arrow r q d c => do internNode (.arrow r q (← d.internSlotShared) (← c.internSlotShared))
      | .field n m t => do internNode (.field n (← m.internSlotShared) (← t.internSlotShared))
      | .specification m e => do internNode (.specification (← m.internSlotShared) (← e.internSlotShared))
      | .prototype s t => do internNode (.prototype (← s.internSlotShared) (← t.internSlotShared))
      | .variant r => do internNode (.variant (← r.internSlotShared))
      | .computation p r a => do internNode (.computation (← p.internSlotShared) (← r.internSlotShared) (← a.internSlotShared))
      | _ => return .leaf t
    modify fun s => { s with shared := s.shared.insert address slot }
    return slot

@[implemented_by PTy.internSlotShared]
def PTy.internSlot (t : PTy) : InternM Slot := do
  match t with
  | .natural | .boolean | .label | .emptyRow | .variable _ | .data => return .leaf t
  | .arrow r q d c => internNode (.arrow r q (← d.internSlot) (← c.internSlot))
  | .field n m t => internNode (.field n (← m.internSlot) (← t.internSlot))
  | .specification m e => internNode (.specification (← m.internSlot) (← e.internSlot))
  | .prototype s t => internNode (.prototype (← s.internSlot) (← t.internSlot))
  | .variant r => internNode (.variant (← r.internSlot))
  | .computation p r a => internNode (.computation (← p.internSlot) (← r.internSlot) (← a.internSlot))

def PTy.intern (t : PTy) : InternM Json := do
  return (← t.internSlot).json

def Annotation.intern (a : Annotation) : InternM Json := do
  let d ← a.domain.intern
  let c ← a.codomain.intern
  return Json.mkObj [("path", toJson (a.path.map toString)), ("domain", d), ("codomain", c),
    ("parameter", a.parameter), ("reuse", a.reuse)]

/-- Annotations, then the global bound, then the sum bounds, in that order. -/
def internProposal (annotations : List Annotation) (row : PTy) (bounds : List (Nat × PTy)) :
    InternM (List Json × List Json) := do
  let annotationJson ← annotations.mapM Annotation.intern
  let globalType ← row.intern
  let sumJson ← bounds.mapM fun (k, t) => do
    let type ← t.intern
    return Json.mkObj [("index", toString k), ("type", type)]
  return (annotationJson, Json.mkObj [("index", "0"), ("type", globalType)] :: sumJson)

/-- The typing proposal as Lean data: the annotations, the knot row and the sum bounds
(sorted by index), or why there is none. -/
structure Proposed where
  annotations : List Annotation
  row : PTy
  bounds : List (Nat × PTy)

def propose (out : Output) : Except String Proposed := do
  let bounds := out.sumBounds.mergeSort (fun a b => a.1 ≤ b.1)
  -- A lambda whose type did not resolve names the downstream symptom; the type error the
  -- resolver recorded first is the cause, so the refusal leads with it.
  let annotations ← match annotate bounds out.term [] with
    | .ok a => pure a
    | .error e => throw (match out.typeErrors[0]? with
      | some cause => cause ++ " (" ++ e ++ ")"
      | none => e)
  let some row := out.knotRow | throw (out.typeErrors[0]?.getD "global row unresolved")
  return ⟨annotations, row, bounds⟩

/-- The typing-proposal fields that translation validation compares. -/
def proposalJson (out : Output) : Except String Json := do
  let ⟨annotations, row, bounds⟩ ← propose out
  let ((annotationJson, boundJson), interner) := (internProposal annotations row bounds).run {}
  return Json.mkObj [("types", Json.arr interner.table),
    ("annotations", Json.arr annotationJson.toArray),
    ("bounds", Json.arr boundJson.toArray),
    ("shareableVariables", toJson ("0" :: bounds.map (fun b => toString b.1)))]

end Minidregg.Compiler.ObjectiveBendElaborate

