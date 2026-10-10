/- The parsed source of one Objective Bend module, as Lean data.

`Compiler.ObjectiveBendParse` produces it, the hosted front end (document templates,
generics) rewrites it, and `Compiler.ObjectiveBendElaborate.ofSurface` reads it. Every
node keeps the span the parser gave it (UTF-8 byte offsets, 1-based line). Type
annotations stay the source text the parser cut out (the elaborator and the generics
pass parse type text themselves, with their own refusals).

`Module.json` renders the `dregg.objective-bend.module.v1` AST the parser used to emit
as JSON, byte for byte; it is for diagnostics and inspection only. Two pieces of it
are still identity-bearing and are rendered from here: an import edge (`Import.json`,
in each packet's `sourceModules`) and a spec's requirement and method signatures
(`Signature.json`, `Method.signatureJson`, inside the spec's interface label). -/
import Lean
namespace Minidregg.Compiler.ObjectiveBendSurface
open Lean
set_option autoImplicit false

structure Span where
  start : Nat
  stop : Nat
  line : Nat
  deriving Inhabited, Repr, BEq, Hashable

def Span.json (s : Span) : Json :=
  Json.mkObj [("start", toJson s.start), ("end", toJson s.stop), ("line", toJson s.line)]

structure Param where
  name : String
  type : String
  quantity : String
  deriving Inhabited, Repr, BEq, Hashable

def Param.json (p : Param) : Json :=
  Json.mkObj [("name", toJson p.name), ("type", toJson p.type), ("quantity", toJson p.quantity)]

inductive Expr where
  | var (name : String) (span : Span)
  | nat (value : String) (span : Span)
  | bool (value : Bool) (span : Span)
  | str (value : String) (span : Span)
  | unit (span : Span)
  | record (fields : List (String × Expr)) (span : Span)
  | extend (inherited : Expr) (fields : List (String × Expr)) (span : Span)
  | member (target : Expr) (name : String) (span : Span)
  | call (callee : Expr) (args : List Expr) (span : Span)
  | compose (specifications : List Expr) (span : Span)
  | fix (specification inherited : Expr) (span : Span)
  | lambda (params : List Param) (resultType : String) (body : Expr) (span : Span)
  | extensionValue (params : List Param) (targetType : String) (body : Expr) (span : Span)
  | binary (op : String) (left right : Expr) (span : Span)
  | ite (condition whenTrue whenFalse : Expr) (span : Span)
  | letE (name type : String) (value body : Expr) (span : Span)
  /-- `target::<T, ...>`: resolved by the generics pass, never elaborated. -/
  | specialize (target : Expr) (types : List String) (span : Span)
  /-- `Data.of::<T>(value)` as the generics pass rewrites it. -/
  | dataOf (type : String) (value : Expr) (span : Span)
  deriving Inhabited, Repr, BEq

def Expr.span : Expr → Span
  | .var _ s | .nat _ s | .bool _ s | .str _ s | .unit s | .record _ s | .extend _ _ s | .member _ _ s
  | .call _ _ s | .compose _ s | .fix _ _ s | .lambda _ _ _ s | .extensionValue _ _ _ s | .binary _ _ _ s
  | .ite _ _ _ s | .letE _ _ _ _ s | .specialize _ _ s | .dataOf _ _ s => s

inductive Pattern where
  | zero
  | succ (binder : String)
  | wildcard
  | bool (value : Bool)
  | ctor (label binder : String)
  /-- Every label no other arm names, each arm refusing the turn by name
  (`refuse("unexpected response <label>")`). Written by `let label(x) = perform(...)`. -/
  | unexpected
  deriving Inhabited, Repr, BEq

/-- The binder a pattern names, `""` when it names none (as the AST's absent `binder`). -/
def Pattern.binder : Pattern → String
  | .succ b | .ctor _ b => b
  | _ => ""

inductive Body where
  | expr (expression : Expr) (span : Span)
  | cases (scrutinee : Expr) (branches : List (Pattern × Body × Span)) (span : Span)
  | letB (name type : String) (value : Expr) (body : Body) (span : Span)
  deriving Inhabited, Repr, BEq

structure Signature where
  name : String
  params : List Param
  resultType : String
  span : Span
  deriving Inhabited, Repr, BEq

structure Method where
  signature : Signature
  qualifier : String
  body : Body
  deriving Inhabited, Repr, BEq

structure Claim where
  name : String
  params : List Param
  body : Expr
  span : Span
  deriving Inhabited, Repr, BEq

structure Field where
  name : String
  type : String
  span : Span
  deriving Inhabited, Repr, BEq

structure Spec where
  name : String
  suffix : Bool
  parents : List String
  targetType : String
  requirements : List Signature
  methods : List Method
  claims : List Claim
  /-- `Self has {...}, Super has {...}` of an open spec; `none` for `spec S for T`. -/
  binders : Option String
  span : Span
  deriving Inhabited, Repr, BEq

inductive Decl where
  | reexport (name target : String) (span : Span)
  | spec (s : Spec)
  | extension (name : String) (params : List Param) (targetType : String) (body : Body)
      (binders : Option String) (span : Span)
  | typeAlias (name type : String) (span : Span)
  | sum (name : String) (cases : List Field) (typeParameters : List String) (span : Span)
  | record (name : String) (methods : List Signature) (fields : List Field) (span : Span)
  /-- `law NAME "reading": EXPR`; `reading` is "" when the source gives none. -/
  | law (name source reading : String) (span : Span)
  /-- `typeParameters` is present (possibly empty) exactly when the source wrote `def f<...>`
  or the generics pass made the function an instance. -/
  | function (signature : Signature) (typeParameters : Option (List String)) (body : Body) (span : Span)
  deriving Inhabited, Repr, BEq

def Decl.name : Decl → String
  | .reexport n .. | .extension n .. | .typeAlias n .. | .sum n .. | .record n .. | .law n .. => n
  | .spec s => s.name
  | .function s .. => s.name

def Decl.span : Decl → Span
  | .reexport _ _ s | .extension _ _ _ _ _ s | .typeAlias _ _ s | .sum _ _ _ s | .record _ _ _ s
  | .law _ _ _ s | .function _ _ _ s => s
  | .spec s => s.span

/-- The declaration's generic type parameters (`[]` for every non-generic declaration). -/
def Decl.typeParameters : Decl → List String
  | .sum _ _ ps _ => ps
  | .function _ (some ps) _ _ => ps
  | _ => []

def Decl.kind : Decl → String
  | .reexport .. => "reexport" | .spec .. => "spec" | .extension .. => "extension"
  | .typeAlias .. => "typeAlias" | .sum .. => "sum" | .record .. => "record" | .law .. => "law"
  | .function .. => "function"

structure Import where
  path : String
  importAlias : String
  span : Span
  deriving Inhabited, Repr, BEq

structure Module where
  imports : List Import
  decls : List Decl
  deriving Inhabited, Repr, BEq

/-! ## The JSON rendering (`dregg.objective-bend.module.v1`) -/

def node (kind : String) (fields : List (String × Json)) (span : Span) : Json :=
  Json.mkObj ([("kind", toJson kind)] ++ fields ++ [("span", span.json)])

def paramsJson (ps : List Param) : Json := Json.arr (ps.map Param.json).toArray

mutual
def Expr.json : Expr → Json
  | .var n s => node "var" [("name", toJson n)] s
  | .nat v s => node "nat" [("value", toJson v)] s
  | .bool v s => node "bool" [("value", toJson v)] s
  | .str v s => node "string" [("value", toJson v)] s
  | .unit s => node "unit" [] s
  | .record fs s => node "record" [("fields", fieldsJson fs)] s
  | .extend i fs s => node "extend" [("inherited", i.json), ("fields", fieldsJson fs)] s
  | .member t n s => node "member" [("target", t.json), ("name", toJson n)] s
  | .call c args s => node "call" [("callee", c.json), ("args", Json.arr (listJson args).toArray)] s
  | .compose specs s => node "compose" [("specifications", Json.arr (listJson specs).toArray)] s
  | .fix spec inherited s => node "fix" [("specification", spec.json), ("inherited", inherited.json)] s
  | .lambda ps r b s => node "lambda" [("parameters", paramsJson ps), ("resultType", toJson r), ("body", b.json)] s
  | .extensionValue ps t b s =>
    node "extension-value" [("parameters", paramsJson ps), ("targetType", toJson t), ("body", b.json)] s
  | .binary op l r s => node "binary" [("op", toJson op), ("left", l.json), ("right", r.json)] s
  | .ite c t f s => node "if" [("condition", c.json), ("whenTrue", t.json), ("whenFalse", f.json)] s
  | .letE n t v b s => node "let" [("name", toJson n), ("type", toJson t), ("value", v.json), ("body", b.json)] s
  | .specialize t types s => node "specialize" [("target", t.json), ("types", toJson types)] s
  | .dataOf t v s => node "dataOf" [("type", toJson t), ("value", v.json)] s
def fieldsJson : List (String × Expr) → Json
  | fs => Json.arr (fieldsList fs).toArray
def fieldsList : List (String × Expr) → List Json
  | [] => []
  | (n, v) :: rest => Json.mkObj [("name", toJson n), ("value", v.json)] :: fieldsList rest
def listJson : List Expr → List Json
  | [] => []
  | e :: rest => e.json :: listJson rest
end

def Pattern.json : Pattern → Json
  | .wildcard => Json.mkObj [("kind", toJson "wildcard")]
  | .bool v => Json.mkObj [("kind", toJson "bool"), ("value", toJson v)]
  | .ctor l b => Json.mkObj [("kind", toJson "constructor"), ("label", toJson l), ("binder", toJson b)]
  | .succ b => Json.mkObj [("kind", toJson "succ"), ("binder", toJson b)]
  | .zero => Json.mkObj [("kind", toJson "zero")]
  | .unexpected => Json.mkObj [("kind", toJson "unexpected")]

mutual
def Body.json : Body → Json
  | .expr e s => Json.mkObj [("kind", toJson "expression"), ("expression", e.json), ("span", s.json)]
  | .cases sc branches s => Json.mkObj [("kind", toJson "match"), ("scrutinee", sc.json),
      ("branches", Json.arr (branchesJson branches).toArray), ("span", s.json)]
  | .letB n t v b s => Json.mkObj [("kind", toJson "let"), ("name", toJson n), ("type", toJson t),
      ("value", v.json), ("body", b.json), ("span", s.json)]
def branchesJson : List (Pattern × Body × Span) → List Json
  | [] => []
  | (p, b, s) :: rest =>
    Json.mkObj [("pattern", p.json), ("body", b.json), ("span", s.json)] :: branchesJson rest
end

def Signature.fields (s : Signature) : List (String × Json) :=
  [("name", toJson s.name), ("parameters", paramsJson s.params), ("resultType", toJson s.resultType),
    ("span", s.span.json)]

def Signature.json (s : Signature) : Json := Json.mkObj s.fields

/-- A method without its body: the authored signature and qualifier (the interface label's form). -/
def Method.signatureJson (m : Method) : Json :=
  Json.mkObj (m.signature.fields ++ [("qualifier", toJson m.qualifier)])

def Method.json (m : Method) : Json :=
  Json.mkObj (m.signature.fields ++ [("qualifier", toJson m.qualifier), ("body", m.body.json)])

def Claim.json (c : Claim) : Json :=
  Json.mkObj [("name", toJson c.name), ("parameters", paramsJson c.params), ("body", c.body.json),
    ("span", c.span.json)]

def Field.json (f : Field) : Json :=
  Json.mkObj [("name", toJson f.name), ("type", toJson f.type), ("span", f.span.json)]

def Field.caseJson (f : Field) : Json :=
  Json.mkObj [("label", toJson f.name), ("type", toJson f.type), ("span", f.span.json)]

def bindersField : Option String → List (String × Json)
  | some b => [("binders", toJson b)]
  | none => []

def Decl.json : Decl → Json
  | .reexport n t s => Json.mkObj [("kind", toJson "reexport"), ("name", toJson n), ("target", toJson t), ("span", s.json)]
  | .spec sp => Json.mkObj ([("kind", toJson "spec"), ("name", toJson sp.name), ("suffix", toJson sp.suffix),
      ("parents", toJson sp.parents), ("targetType", toJson sp.targetType),
      ("requirements", Json.arr (sp.requirements.map Signature.json).toArray),
      ("methods", Json.arr (sp.methods.map Method.json).toArray),
      ("claims", Json.arr (sp.claims.map Claim.json).toArray), ("span", sp.span.json)] ++ bindersField sp.binders)
  | .extension n ps t b binders s => Json.mkObj ([("kind", toJson "extension"), ("name", toJson n),
      ("parameters", paramsJson ps), ("targetType", toJson t), ("body", b.json), ("span", s.json)] ++
      bindersField binders)
  | .typeAlias n t s => Json.mkObj [("kind", toJson "typeAlias"), ("name", toJson n), ("type", toJson t), ("span", s.json)]
  | .sum n cases ps s => Json.mkObj [("kind", toJson "sum"), ("name", toJson n),
      ("cases", Json.arr (cases.map Field.caseJson).toArray), ("typeParameters", toJson ps), ("span", s.json)]
  | .record n methods fields s => Json.mkObj [("kind", toJson "record"), ("name", toJson n),
      ("methods", Json.arr (methods.map Signature.json).toArray), ("fields", Json.arr (fields.map Field.json).toArray),
      ("span", s.json)]
  | .law n source reading s => Json.mkObj ([("kind", toJson "law"), ("name", toJson n), ("source", toJson source)] ++
      (if reading.isEmpty then [] else [("reading", toJson reading)]) ++ [("span", s.json)])
  | .function sig ps b s => Json.mkObj ([("kind", toJson "function"), ("signature", sig.json)] ++
      (match ps with | some ps => [("typeParameters", toJson ps)] | none => []) ++
      [("body", b.json), ("span", s.json)])

def Import.json (i : Import) : Json :=
  Json.mkObj [("path", toJson i.path), ("alias", toJson i.importAlias), ("span", i.span.json)]

def moduleSchema : String := "dregg.objective-bend.module.v1"

def Module.json (m : Module) : Json :=
  Json.mkObj [("schema", toJson moduleSchema), ("edition", toJson "objective-bend-1"),
    ("imports", Json.arr (m.imports.map Import.json).toArray),
    ("declarations", Json.arr (m.decls.map Decl.json).toArray),
    ("theoremScope", toJson "new source AST; elaboration and reference semantics are Objective Core4")]

/-! ## Span maps (document-template origins) -/

mutual
def Expr.mapSpans (f : Span → Span) : Expr → Expr
  | .var n s => .var n (f s)
  | .nat v s => .nat v (f s)
  | .bool v s => .bool v (f s)
  | .str v s => .str v (f s)
  | .unit s => .unit (f s)
  | .record fs s => .record (mapFieldSpans f fs) (f s)
  | .extend i fs s => .extend (i.mapSpans f) (mapFieldSpans f fs) (f s)
  | .member t n s => .member (t.mapSpans f) n (f s)
  | .call c args s => .call (c.mapSpans f) (mapListSpans f args) (f s)
  | .compose specs s => .compose (mapListSpans f specs) (f s)
  | .fix spec inherited s => .fix (spec.mapSpans f) (inherited.mapSpans f) (f s)
  | .lambda ps r b s => .lambda ps r (b.mapSpans f) (f s)
  | .extensionValue ps t b s => .extensionValue ps t (b.mapSpans f) (f s)
  | .binary op l r s => .binary op (l.mapSpans f) (r.mapSpans f) (f s)
  | .ite c t e s => .ite (c.mapSpans f) (t.mapSpans f) (e.mapSpans f) (f s)
  | .letE n t v b s => .letE n t (v.mapSpans f) (b.mapSpans f) (f s)
  | .specialize t types s => .specialize (t.mapSpans f) types (f s)
  | .dataOf t v s => .dataOf t (v.mapSpans f) (f s)
def mapFieldSpans (f : Span → Span) : List (String × Expr) → List (String × Expr)
  | [] => []
  | (n, v) :: rest => (n, v.mapSpans f) :: mapFieldSpans f rest
def mapListSpans (f : Span → Span) : List Expr → List Expr
  | [] => []
  | e :: rest => e.mapSpans f :: mapListSpans f rest
end

mutual
def Body.mapSpans (f : Span → Span) : Body → Body
  | .expr e s => .expr (e.mapSpans f) (f s)
  | .cases sc branches s => .cases (sc.mapSpans f) (mapBranchSpans f branches) (f s)
  | .letB n t v b s => .letB n t (v.mapSpans f) (b.mapSpans f) (f s)
def mapBranchSpans (f : Span → Span) : List (Pattern × Body × Span) → List (Pattern × Body × Span)
  | [] => []
  | (p, b, s) :: rest => (p, b.mapSpans f, f s) :: mapBranchSpans f rest
end

def Signature.mapSpans (f : Span → Span) (s : Signature) : Signature := { s with span := f s.span }
def Method.mapSpans (f : Span → Span) (m : Method) : Method :=
  { m with signature := m.signature.mapSpans f, body := m.body.mapSpans f }
def Field.mapSpans (f : Span → Span) (x : Field) : Field := { x with span := f x.span }

def Decl.mapSpans (f : Span → Span) : Decl → Decl
  | .reexport n t s => .reexport n t (f s)
  | .spec sp =>
    let requirements := sp.requirements.map fun x => x.mapSpans f
    let methods := sp.methods.map fun x => x.mapSpans f
    let claims := sp.claims.map fun c => { c with body := c.body.mapSpans f, span := f c.span }
    .spec { sp with requirements, methods, claims, span := f sp.span }
  | .extension n ps t b binders s => .extension n ps t (b.mapSpans f) binders (f s)
  | .typeAlias n t s => .typeAlias n t (f s)
  | .sum n cases ps s => .sum n (cases.map (fun x => x.mapSpans f)) ps (f s)
  | .record n methods fields s => .record n (methods.map (fun x => x.mapSpans f)) (fields.map (fun x => x.mapSpans f)) (f s)
  | .law n source reading s => .law n source reading (f s)
  | .function sig ps b s => .function (sig.mapSpans f) ps (b.mapSpans f) (f s)

def Module.mapSpans (f : Span → Span) (m : Module) : Module :=
  { imports := m.imports.map fun i => { i with span := f i.span }, decls := m.decls.map (fun x => x.mapSpans f) }

end Minidregg.Compiler.ObjectiveBendSurface
