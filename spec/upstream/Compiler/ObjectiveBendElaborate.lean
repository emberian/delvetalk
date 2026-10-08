/- Objective Bend surface → Core4 elaboration: THE elaborator.

Reads the `dregg.objective-bend.module.v1` AST that `Compiler.ObjectiveBendParse`
produces and emits the Core4 term and its lambda/inject typing proposals. It was
ported from the retired TypeScript elaborator and translation-validated against
it until that elaborator was deleted (docs/OBJECTIVE-BEND-FRONTEND.md,
"Provenance"). What is proved of its output once the checker accepts it is in
`Compiler.ObjectiveBendFrontEndAdequacy`; "surface meaning preserved" needs a
surface semantics, which does not exist. All recursion is fuel-bounded; running
out of fuel is a refusal, never a guess. -/
import Lean
import Compiler.ObjectiveBendParse
import Compiler.ObjectiveBendLaw
import Std.Data.HashMap
import Theory.ObjectiveBendOpenRecursion
import Compiler.ObjectiveBendC4
import Compiler.ObjectiveBendContract
namespace Minidregg.Compiler.ObjectiveBendElaborate
open Lean
set_option autoImplicit false

abbrev CoreTerm := Minidregg.Theory.ObjectiveBendOpenRecursion.Term
abbrev CorePrimitive := Minidregg.Theory.ObjectiveBendOpenRecursion.Primitive

/-! String helpers (ASCII whitespace, as the TS `trim`). -/
def isSpace (c : Char) : Bool := c == ' ' || c == '\t' || c == '\n' || c == '\r'
def trimStart (s : String) : String := String.ofList (s.toList.dropWhile isSpace)
def trimEnd (s : String) : String := String.ofList ((s.toList.reverse.dropWhile isSpace).reverse)
def trimStr (s : String) : String := trimEnd (trimStart s)
def dropStr (s : String) (n : Nat) : String := String.ofList (s.toList.drop n)
def dropEndStr (s : String) (n : Nat) : String := String.ofList (s.toList.take (s.length - n))

/-! ## Surface AST -/

structure Param where
  name : String
  type : String
  quantity : String
  deriving Inhabited, Repr

inductive Expr where
  | var (name : String)
  | nat (value : String)
  | bool (value : Bool)
  | str (value : String)
  | unit
  | record (fields : List (String × Expr))
  | extend (inherited : Expr) (fields : List (String × Expr))
  | member (target : Expr) (name : String)
  | call (callee : Expr) (args : List Expr)
  | compose (specs : List Expr)
  | fix (spec inherited : Expr)
  | closure (params : List Param) (resultType : String) (body : Expr)
  | binary (op : String) (left right : Expr)
  | ite (condition whenTrue whenFalse : Expr)
  /-- `let name: type = value in body` (type `_` when unannotated). -/
  | letE (name type : String) (value body : Expr)
  deriving Inhabited, Repr

inductive Pattern where
  | zero | succ (binder : String) | wildcard | bool (value : Bool) | ctor (label binder : String)
  deriving Inhabited, Repr, BEq

inductive Body where
  | expr (e : Expr)
  | cases (scrutinee : Expr) (branches : List (Pattern × Body))
  /-- `let name: type = value` then the rest of the body. -/
  | letB (name type : String) (value : Expr) (body : Body)
  deriving Inhabited, Repr

structure Method where
  name : String
  params : List Param
  resultType : String
  qualifier : String
  body : Body
  /-- The authored signature (method JSON minus its body), for the interface label. -/
  signature : Json
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
  requirements : Json
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
  | function (name : String) (params : List Param) (resultType : String) (body : Body)
  | record (name : String) (fields : List (String × String)) (methods : List Signature)
  | sum (name : String) (cases : List (String × String))
  deriving Inhabited

def Decl.name : Decl → String
  | .spec s => s.name | .extension n .. => n | .function n .. => n | .record n .. => n | .sum n .. => n

structure Module where
  name : String
  /-- (alias, imported module name) in source order. -/
  imports : List (String × String)
  decls : List Decl
  /-- The module's top-level enforced laws (`law NAME: EXPR`), in source order. They are not
  terms: the elaborator never sees them; the front end hands the entry module's to the artifact. -/
  laws : List (String × ObjectiveBendLaw.LawExpr) := []
  deriving Inhabited

/-! ## Decoding the TS parser's AST JSON -/

def str (j : Json) (k : String) : Except String String := j.getObjValAs? String k
def arr (j : Json) (k : String) : Except String (List Json) := do return (← (← j.getObjVal? k).getArr?).toList

def decodeParam (j : Json) : Except String Param := do
  return ⟨← str j "name", (← str j "type"), (j.getObjValAs? String "quantity").toOption.getD "default"⟩

mutual
def decodeExpr : Nat → Json → Except String Expr
  | 0, _ => .error "AST nesting capacity"
  | fuel + 1, j => do
    let fields := fun (key : String) => do
      (← arr j key).mapM fun f => do return (← str f "name", ← decodeExpr fuel (← f.getObjVal? "value"))
    let sub := fun (key : String) => do decodeExpr fuel (← j.getObjVal? key)
    match ← str j "kind" with
    | "var" => return .var (← str j "name")
    | "nat" => return .nat (← str j "value")
    | "bool" => return .bool (← j.getObjValAs? Bool "value")
    | "string" => return .str (← str j "value")
    | "unit" => return .unit
    | "record" => return .record (← fields "fields")
    | "extend" => return .extend (← sub "inherited") (← fields "fields")
    | "member" => return .member (← sub "target") (← str j "name")
    | "call" => return .call (← sub "callee") (← (← arr j "args").mapM (decodeExpr fuel))
    | "compose" => return .compose (← (← arr j "specifications").mapM (decodeExpr fuel))
    | "fix" => return .fix (← sub "specification") (← sub "inherited")
    | "extension-value" => return .closure (← (← arr j "parameters").mapM decodeParam) (← str j "targetType") (← sub "body")
    | "lambda" => return .closure (← (← arr j "parameters").mapM decodeParam) (← str j "resultType") (← sub "body")
    | "binary" => return .binary (← str j "op") (← sub "left") (← sub "right")
    | "if" => return .ite (← sub "condition") (← sub "whenTrue") (← sub "whenFalse")
    | "let" => return .letE (← str j "name") (← str j "type") (← sub "value") (← sub "body")
    | other => .error ("unknown AST expression " ++ other)

def decodeBody : Nat → Json → Except String Body
  | 0, _ => .error "AST nesting capacity"
  | fuel + 1, j => do
    match ← str j "kind" with
    | "expression" => return .expr (← decodeExpr fuel (← j.getObjVal? "expression"))
    | "match" =>
      let branches ← (← arr j "branches").mapM fun b => do
        let p ← b.getObjVal? "pattern"
        let binder := (p.getObjValAs? String "binder").toOption.getD "_"
        let pattern ← match ← str p "kind" with
          | "zero" => pure Pattern.zero
          | "succ" => pure (.succ binder)
          | "wildcard" => pure .wildcard
          | "bool" => pure (.bool (← p.getObjValAs? Bool "value"))
          | "constructor" => pure (.ctor (← str p "label") binder)
          | other => .error ("unknown pattern " ++ other)
        return (pattern, ← decodeBody fuel (← b.getObjVal? "body"))
      return .cases (← decodeExpr fuel (← j.getObjVal? "scrutinee")) branches
    | "let" =>
      let value ← decodeExpr fuel (← j.getObjVal? "value")
      let rest ← decodeBody fuel (← j.getObjVal? "body")
      return .letB (← str j "name") (← str j "type") value rest
    | other => .error ("unknown AST body " ++ other)
end

def withoutKey (j : Json) (key : String) : Json :=
  match j with
  | .obj kvs => .obj (kvs.erase key)
  | other => other

def decodeSignature (j : Json) : Except String Signature := do
  return ⟨← str j "name", ← (← arr j "parameters").mapM decodeParam, ← str j "resultType"⟩

def decodeDecl (j : Json) : Except String Decl := do
  let fuel := 4096
  match ← str j "kind" with
  | "spec" =>
    let methods ← (← arr j "methods").mapM fun m => do
      let name ← str m "name"
      let params ← (← arr m "parameters").mapM decodeParam
      let resultType ← str m "resultType"
      let qualifier := (m.getObjValAs? String "qualifier").toOption.getD "primary"
      let body ← decodeBody fuel (← m.getObjVal? "body")
      return (Method.mk name params resultType qualifier body (withoutKey m "body"))
    let claims ← (← arr j "claims").mapM fun l => do
      let name ← str l "name"
      let params ← (← arr l "parameters").mapM decodeParam
      let body ← decodeExpr fuel (← l.getObjVal? "body")
      return (Claim.mk name params body)
    let name ← str j "name"
    let suffix := (j.getObjValAs? Bool "suffix").toOption.getD false
    let parents ← (← arr j "parents").mapM (fun p => p.getStr?)
    let targetType ← str j "targetType"
    let requirements ← j.getObjVal? "requirements"
    let binders := (j.getObjValAs? String "binders").toOption.getD ""
    return .spec (Spec.mk name suffix parents targetType requirements methods claims binders)
  | "extension" =>
    let name ← str j "name"
    let params ← (← arr j "parameters").mapM decodeParam
    let targetType ← str j "targetType"
    let body ← decodeBody fuel (← j.getObjVal? "body")
    return .extension name params targetType body ((j.getObjValAs? String "binders").toOption.getD "")
  | "function" =>
    let s ← j.getObjVal? "signature"
    let name ← str s "name"
    let params ← (← arr s "parameters").mapM decodeParam
    let resultType ← str s "resultType"
    let body ← decodeBody fuel (← j.getObjVal? "body")
    return .function name params resultType body
  | "record" =>
    let name ← str j "name"
    let fields ← (← arr j "fields").mapM fun f => do return (← str f "name", ← str f "type")
    let methods ← (← arr j "methods").mapM decodeSignature
    return .record name fields methods
  | "sum" => return .sum (← str j "name") (← (← arr j "cases").mapM fun c => do return (← str c "label", ← str c "type"))
  | other => .error ("unknown AST declaration " ++ other)

/-- `{name, imports:[{alias, moduleName}], ast}` as the TS elaborator receives it. -/
def decodeModule (j : Json) : Except String Module := do
  let ast ← j.getObjVal? "ast"
  let mut decls : List Decl := []
  let mut laws : List (String × ObjectiveBendLaw.LawExpr) := []
  for d in ← arr ast "declarations" do
    if (str d "kind").toOption == some "law" then
      laws := laws ++ [(← str d "name", ← ObjectiveBendLaw.parse (← str d "source"))]
    else decls := decls ++ [← decodeDecl d]
  ObjectiveBendLaw.checkNames laws
  return ⟨← str j "name", ← (← arr j "imports").mapM (fun i => do return (← str i "alias", ← str i "moduleName")),
    decls, laws⟩

/-! ## Proposal types (the `Ty` JSON wire of Theory.ObjectiveBendTyping.typeJson, plus `variant`) -/

inductive PTy where
  | natural | boolean | label | emptyRow
  | variable (index : Nat)
  | arrow (reuse parameter : String) (domain codomain : PTy)
  | field (name : String) (member tail : PTy)
  | specification (metadata extension : PTy)
  | variant (row : PTy)
  | computation (plan response result : PTy)
  deriving Inhabited, Repr, BEq

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

def PTy.json : PTy → Json
  | .natural => Json.mkObj [("tag", "natural")]
  | .boolean => Json.mkObj [("tag", "boolean")]
  | .label => Json.mkObj [("tag", "label")]
  | .emptyRow => Json.mkObj [("tag", "emptyRow")]
  | .variable i => Json.mkObj [("tag", "variable"), ("index", toString i)]
  | .arrow r q d c => Json.mkObj [("tag", "arrow"), ("reuse", r), ("parameter", q), ("domain", d.json), ("codomain", c.json)]
  | .field n m t => Json.mkObj [("tag", "field"), ("name", n), ("member", m.json), ("tail", t.json)]
  | .specification m e => Json.mkObj [("tag", "specification"), ("metadata", m.json), ("extension", e.json)]
  | .variant r => Json.mkObj [("tag", "variant"), ("row", r.json)]
  | .computation p r a => Json.mkObj [("tag", "computation"), ("plan", p.json), ("response", r.json), ("result", a.json)]

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

inductive ATerm where
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
  deriving Inhabited

mutual
def ATerm.json : ATerm → Json
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
  | other => .error ("primitive " ++ other ++ " is not a Core4 constructor yet")

mutual
def ATerm.erase : ATerm → Except String CoreTerm
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

structure St where
  globalTypes : List (String × Option PTy) := []
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

abbrev M := StateT St (Except String)

def fail {α : Type} (message : String) : M α := throw message
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

/-- Split at top-level occurrences of `sep`, outside `<`, `(`, `{` nesting
(a `>` preceded by `-` is part of an arrow, not a closing bracket). -/
def splitTop (text : String) (sep : String) : List String :=
  let chars := text.toList
  let sepChars := sep.toList
  let rec go : Nat → List Char → Option Char → Int → List Char → List String → List String
    | 0, _, _, _, current, parts => (parts ++ [String.ofList current])
    | _ + 1, [], _, _, current, parts => parts ++ [String.ofList current]
    | fuel + 1, c :: rest, prev, depth, current, parts =>
      if "<({".toList.contains c then go fuel rest (some c) (depth + 1) (current ++ [c]) parts
      else if ">)}".toList.contains c && !(c == '>' && prev == some '-') then go fuel rest (some c) (depth - 1) (current ++ [c]) parts
      else if depth == 0 && (c :: rest).take sepChars.length == sepChars then
        go fuel ((c :: rest).drop sepChars.length) (sepChars.getLast?) depth [] (parts ++ [String.ofList current])
      else go fuel rest (some c) depth (current ++ [c]) parts
  (go (chars.length + 1) chars none 0 [] []).map trimStr

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
def builtinTypeNames : List String := [specMetaName, specClaimsName]
def builtinSource : String :=
  "edition ObjectiveBend 1\n" ++
  "sum SpecClaims:\n  none: {}\n  claim: {name: String, status: String, rest: SpecClaims}\n\n" ++
  "sum SpecMeta:\n  declared: {name: String, interface: String, claims: SpecClaims}\n" ++
  "  composed: {inherited: SpecMeta, wrapping: SpecMeta}\n  extension: {}\n"

def lookupGlobal (c : Ctx) (name : String) (m : Module) : Option String :=
  let key := m.name ++ "." ++ name
  if (c.decls.find? (·.1 == key)).isSome then some key else none

def declOf (c : Ctx) (key : String) : Option (Decl × Module) := (c.decls.find? (·.1 == key)).map (·.2)

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
        match c.sums.find? (·.1 == key) with
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

def isPerform (c : Ctx) (e : Expr) (env : List Binding) (m : Module) : Bool :=
  match e with
  | .call (.var "perform") _ => !env.any (·.name == "perform") && (lookupGlobal c "perform" m).isNone
  | _ => false

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

def requirementsOf (s : Spec) : M (List Signature) :=
  match s.requirements.getArr? with
  | .ok a => a.toList.mapM fun j => match decodeSignature j with
    | .ok r => pure r
    | .error e => fail ("requirement of spec " ++ s.name ++ ": " ++ e)
  | .error _ => pure []

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

mutual
def sourceType (c : Ctx) : Nat → String → String → List String → M (Option PTy)
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
    if name.startsWith "Activity<" && name.endsWith ">" then
      let parts := splitTop (dropEndStr (dropStr name "Activity<".length) 1) ","
      match parts with
      | [planText, responseText, resultText] =>
        let plan ← sourceType c fuel planText moduleName seen
        let response ← sourceType c fuel responseText moduleName seen
        let result ← sourceType c fuel resultText moduleName seen
        return match plan, response, result with
          | some p, some r, some a => some (.computation p r a)
          | _, _, _ => none
      | _ => do typeError "Activity<Plan, Response, Result> takes three types"; return none
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
    if let some (_, .sum _ cases) := c.sums.find? (·.1 == key) then
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
    let some (_, .record _ recordFields methods) := c.records.find? (·.1 == key)
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
    if let some t := (← get).globalTypes.lookup key then return t
    if (← get).inferring.contains key then
      typeError ("result inference cycle through " ++ key ++ "; annotate its result type"); return none
    let some (d, m) := declOf c key | return none
    modify fun s => { s with inferring := s.inferring ++ [key] }
    let t ← match d with
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
    modify fun s => { s with inferring := s.inferring.erase key, globalTypes := s.globalTypes ++ [(key, t)] }
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
            return ← globalType c fuel (importedModule ++ "." ++ name)
      return lookupRow (← synth c fuel target env m) name
    | .record fields =>
      let mut row : List (String × PTy) := []
      for (n, v) in fields do
        match ← synth c fuel v env m with
        | some t => row := row ++ [(n, t)]
        | none => return none
      return some (PTy.row row)
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
    | .call callee args =>
      if isPerform c e env m then
        return (← get).effect.map fun (p, r) => .computation p r r
      if let some sc := sumCase c callee env m then return ← sourceType c fuel sc.2.2 sc.2.1 []
      if let .var name := callee then
        if ["reflect", "metadata", "targetOf", "prototype"].contains name && !env.any (·.name == name) then
          -- metadata(s) of a specification-typed s is its SpecMeta; the prototype
          -- forms have no synthesized type (annotate a let).
          if name == "metadata" then
            if let [a] := args then
              if let some (.specification metaTy _) := (← synth c fuel a env m) then return some metaTy
          return none
      let mut t ← synth c fuel callee env m
      for _ in args do
        match callable t with
        | some (.arrow _ _ _ codomain) => t := some codomain
        | _ => return none
      return t
    | _ => return none

def synthBody (c : Ctx) : Nat → Body → List Binding → Module → M (Option PTy)
  | 0, _, _, _ => fail "type synthesis fuel"
  | fuel + 1, .expr e, env, m => synth c fuel e env m
  | fuel + 1, .letB name type value rest, env, m => do
    let ty ← if type == "_" then synth c fuel value env m else sourceType c fuel type m.name []
    synthBody c fuel rest (⟨name, ty, "unrestricted"⟩ :: env) m
  | fuel + 1, .cases scrutinee branches, env, m => do
    if branches.any (fun b => match b.1 with | .ctor .. | .bool _ => true | _ => false) then
      let scrutineeTy ← synth c fuel scrutinee env m
      let row := variantRowOf (← get) scrutineeTy
      let mut types : List (Option PTy) := []
      for (pattern, b) in branches do
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
  | .variant r => .variant (r.subst σ)
  | .computation p r a => .computation (p.subst σ) (r.subst σ) (a.subst σ)
  | other => other

mutual
/-- Apply `f` to every type annotation of a lowered term. -/
def ATerm.mapTypes (f : PTy → PTy) : ATerm → ATerm
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



mutual
def expression (c : Ctx) : Nat → Expr → List Binding → Module → M ATerm
  | 0, _, _, _ => fail "elaboration fuel"
  | fuel + 1, e, env, m => do
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
            let key := importedModule ++ "." ++ name
            if (declOf c key).isNone then fail ("missing imported declaration " ++ key)
            return ← globalRef env key
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
      let i ← expression c fuel inherited env m
      return .extend i (← fieldsOf c fuel fields env m)
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
    | .call callee args =>
      if isPerform c e env m then
        let some (p, r) := (← get).effect
          | fail "refused (perform-outside-activity): perform needs an enclosing definition whose result type is Activity<Plan, Response, Result>"
        match args with
        | [a] =>
          noActivity c fuel a env m "effect-in-plan" "a Plan is data"
          return .perform p r (← expression c fuel a env m)
        | _ => fail "perform takes exactly one Plan"
      if let some (caseLabel, moduleName, sumName) := sumCase c callee env m then
        let key := moduleName ++ "." ++ sumName
        let hasCase := match c.sums.find? (·.1 == key) with
          | some (_, .sum _ cases) => cases.any (·.1 == caseLabel)
          | _ => false
        if !hasCase then fail ("sum " ++ key ++ " has no case " ++ caseLabel)
        if args.length > 1 then fail "a sum case carries one payload; use a record"
        if let [a] := args then noActivity c fuel a env m "effect-in-payload" "a sum payload is a shared lazy cell"
        let payload ← match args with
          | [a] => expression c fuel a env m
          | _ => pure (.record [])
        let type ← sourceType c fuel sumName moduleName []
        return .inject caseLabel type (if type.isSome then none else some ("sum " ++ key ++ " type unresolved")) payload
      if let .var name := callee then
        if !env.any (·.name == name) && (lookupGlobal c name m).isNone then
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
      for a in args do fn := .app fn (← expression c fuel a env m)
      return fn

/-- A tail position of an activity body: pure results are lifted with `done`. -/
def tail (c : Ctx) : Nat → Expr → List Binding → Module → M ATerm
  | 0, _, _, _ => fail "elaboration fuel"
  | fuel + 1, e, env, m => do
    if let .fix .. := e then modify fun st => { st with fixTarget := st.resultType }
    let some (p, r) := (← get).effect | expression c fuel e env m
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
    return .done p r (← expression c fuel e env m)

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
    let layer ← withTypes [("Self", selfVar), ("Super", superVar)] do
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
  | fuel + 1, .letB name type value rest, env, m =>
    lowerLet c fuel name type value env m true (expression c fuel value env m)
      (fun inner => body c fuel rest inner m) (fun inner => synthBody c fuel rest inner m)
  | fuel + 1, .cases scrutinee branches, env, m => do
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
    if branches.any (fun b => match b.1 with | .ctor .. => true | _ => false) then
      if !branches.all (fun b => match b.1 with | .ctor .. => true | _ => false) then
        fail "a sum match takes only label(binder) cases; wildcards are refused (no default arm)"
      let labels := branches.map (fun b => match b.1 with | .ctor l _ => l | _ => "")
      if duplicate labels then fail "duplicate sum case"
      let row := variantRowOf (← get) (← synth c fuel scrutinee env m)
      if let some r := row then
        let rowLabels := rowNames r
        let missing := rowLabels.filter (fun l => !labels.contains l)
        let extra := labels.filter (fun l => !rowLabels.contains l)
        if !missing.isEmpty || !extra.isEmpty then
          fail ("sum match is not exhaustive: missing [" ++ String.intercalate ", " missing ++ "], unknown [" ++ String.intercalate ", " extra ++ "]")
      let st ← expression c fuel scrutinee env m
      let mut arms : List (String × ATerm) := []
      for (pattern, b) in branches do
        match pattern with
        | .ctor l binder => arms := arms ++ [(l, ← body c fuel b (⟨binder, lookupRow row l, "unrestricted"⟩ :: env) m)]
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
    ("precedence", toJson list), ("requirements", s.requirements),
    ("methods", Json.arr (s.methods.map (·.signature)).toArray)] ++
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


/-! ## The package knot, entry selection, arguments -/

def resultOf : Option PTy → Nat → Option PTy
  | t, 0 => t
  | some (.arrow _ _ _ cod), n + 1 => resultOf (some cod) n
  | _, _ + 1 => none

def exactKeys (j : Json) (expected : List String) : Bool :=
  match j with
  | .obj kvs => (kvs.toList.map (·.1)).mergeSort (· ≤ ·) == expected.mergeSort (· ≤ ·)
  | _ => false

def isCanonicalNat (s : String) : Bool :=
  s == "0" || (match s.toList with | d :: rest => d != '0' && d.isDigit && rest.all Char.isDigit | [] => false)

def legacyArgument : Nat → Json → Except String ATerm
  | 0, _ => .error "argument nesting capacity"
  | fuel + 1, a =>
    match a with
    | .str s => if isCanonicalNat s then .ok (.nat s) else .error "runtime arguments are canonical decimal Nat strings, Bool or records"
    | .bool b => .ok (.boolean b)
    | .obj kvs => do return .record (← kvs.toList.mapM fun (k, v) => do return (k, ← legacyArgument fuel v))
    | _ => .error "runtime arguments are canonical decimal Nat strings, Bool or records"

def typedArgument : Nat → Json → Except String ATerm
  | 0, _ => .error "argument nesting capacity"
  | fuel + 1, a => do
    let tag := (a.getObjValAs? String "tag").toOption.getD ""
    if tag == "natural" && exactKeys a ["tag", "value"] then
      if let .ok v := a.getObjValAs? String "value" then if isCanonicalNat v then return .nat v
    if tag == "boolean" && exactKeys a ["tag", "value"] then
      if let .ok v := a.getObjValAs? Bool "value" then return .boolean v
    if tag == "label" && exactKeys a ["tag", "value"] then
      if let .ok v := a.getObjValAs? String "value" then return .label v
    if tag == "record" && exactKeys a ["tag", "fields"] then
      let fields ← (← a.getObjVal? "fields").getArr?
      let names ← fields.toList.mapM fun f => do
        if !exactKeys f ["name", "value"] then throw "typed record arguments require exact distinct named fields"
        f.getObjValAs? String "name"
      if duplicate names then throw "typed record arguments require exact distinct named fields"
      return .record (← fields.toList.mapM fun f => do return (← f.getObjValAs? String "name", ← typedArgument fuel (← f.getObjVal? "value")))
    throw "malformed typed argument value; no implicit Nat/String coercion"

structure Output where
  term : ATerm
  globalRow : Option PTy
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
  if let .function _ [] resultType _ := d then
    if (trimStr resultType).startsWith "Activity<" then
      fail ("refused (nullary-activity): " ++ key ++ " has no parameters, so it is a shared lazy value; an Activity needs a parameter, e.g. (start: {})")
  let value ← match d with
    | .function _ params resultType b => do
      let result ← if resultType == "_" then do pure (ResultSpec.given (resultOf (← globalType c fuel key) params.length))
        else pure (ResultSpec.source resultType)
      abstract c fuel params outerEnv (fun next => body c fuel b next m) d.name result m.name
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
  let mut fields := fields ++ [(key, value)]
  for (name, value, type) in (← get).hidden do
    fields := fields ++ [(name, value)]
    modify fun st => { st with globalTypes := st.globalTypes ++ [(name, type)] }
  modify fun st => { st with hidden := #[] }
  return fields

def elaborateM (c : Ctx) (entryModule : Nat) (entryDefinition : String) (args : Json) (mode : String) : M Output := do
  let fuel := 100000
  let userModules := c.modules
  let mut fields : List (String × ATerm) := []
  for m in userModules do
    for d in m.decls do
      fields ← emitDecl c fuel m d fields
  let mut rowFields : List (String × PTy) := []
  let mut unresolved : List String := []
  for (name, _) in fields do
    match ← globalType c fuel name with
    | some t => rowFields := rowFields ++ [(name, t)]
    | none => unresolved := unresolved ++ [name]
  let globalRow := if unresolved.isEmpty then some (PTy.row rowFields) else none
  let reason := if unresolved.isEmpty then none else some ("declaration types unresolved: " ++ String.intercalate ", " unresolved)
  let rootExtension := ATerm.lam ⟨some (.variable 0), some (arrowTy .emptyRow (.variable 0)), "unrestricted", "reusable", reason⟩
    (.lam ⟨some .emptyRow, some (.variable 0), "unrestricted", "reusable", reason⟩ (.extend (.bound 0) fields))
  let packageLabel := (toJson (userModules.map (·.name))).compress
  let root := ATerm.fix (.specification (.record [("package", .label packageLabel)]) rootExtension) (.record [])
  let some entry := userModules[entryModule]? | fail "missing selected entry"
  let entryKey := entry.name ++ "." ++ entryDefinition
  if (declOf c entryKey).isNone then fail "missing selected entry"
  let mut selected := ATerm.get root entryKey
  if mode == "definition" then
    match args with
    | .arr a => if !a.isEmpty then fail "definition mode forbids invocation arguments"
    | _ => fail "definition mode forbids invocation arguments"
  else match args with
    | .arr a => for x in a do
        match legacyArgument 256 x with
        | .ok t => selected := .app selected t
        | .error e => fail e
    | envelope =>
      if exactKeys envelope ["schema", "values"] && (envelope.getObjValAs? String "schema").toOption == some "dregg.objective-bend.argument-values.v1" then
        match (envelope.getObjVal? "values").bind Json.getArr? with
        | .ok values => for x in values do
            match typedArgument 256 x with
            | .ok t => selected := .app selected t
            | .error e => fail e
        | .error _ => fail "arguments must select a supported complete value envelope"
      else fail "arguments must select a supported complete value envelope"
  let st ← get
  return ⟨selected, globalRow, st.sumBounds, st.typeErrors, st.templates⟩

/-- The built-in module: `builtinSource` through the parser and the AST decoder. -/
def builtinModule : Except String Module := do
  let ast ← match ObjectiveBendParse.parseObjective builtinSource with
    | .ok ast => pure ast
    | .error d => throw ("builtin: " ++ d.message)
  decodeModule (Json.mkObj [("name", toJson builtinModuleName), ("imports", Json.arr #[]), ("ast", ast)])

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
        decls := decls ++ [(key, d, m)]
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
  return ⟨modules, decls, records, sums⟩

def elaborate (modules : List Module) (entryModule : Nat) (entryDefinition : String) (args : Json) (mode : String) :
    Except String Output := do
  let c ← context modules
  let (out, _) ← (elaborateM c entryModule entryDefinition args mode).run {}
  return out

/-! ## The typing proposal (literalAnnotations) -/

structure Annotation where
  path : List Nat
  domain : PTy
  codomain : PTy
  parameter : String
  reuse : String

mutual
def annotate (bounds : List (Nat × PTy)) : ATerm → List Nat → Except String (List Annotation)
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
  | .app f a, path => return (← annotate bounds f (path ++ [0])) ++ (← annotate bounds a (path ++ [1]))
  | .fix s i, path => return (← annotate bounds s (path ++ [0])) ++ (← annotate bounds i (path ++ [1]))
  | .mix l u, path => return (← annotate bounds l (path ++ [0])) ++ (← annotate bounds u (path ++ [1]))
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

structure Interner where
  table : Array Json := #[]
  seen : Std.HashMap String Nat := {}

abbrev InternM := StateM Interner

def internNode (node : Json) : InternM Json := do
  let key := node.compress
  let s ← get
  let index ← match s.seen[key]? with
    | some i => pure i
    | none => do
      set ({ table := s.table.push node, seen := s.seen.insert key s.table.size } : Interner)
      pure s.table.size
  return Json.mkObj [("tag", "ref"), ("index", toString index)]

def PTy.intern : PTy → InternM Json
  | .natural => pure (Json.mkObj [("tag", "natural")])
  | .boolean => pure (Json.mkObj [("tag", "boolean")])
  | .label => pure (Json.mkObj [("tag", "label")])
  | .emptyRow => pure (Json.mkObj [("tag", "emptyRow")])
  | .variable i => pure (Json.mkObj [("tag", "variable"), ("index", toString i)])
  | .arrow r q d c => do
    let dj ← d.intern
    let cj ← c.intern
    internNode (Json.mkObj [("tag", "arrow"), ("reuse", r), ("parameter", q), ("domain", dj), ("codomain", cj)])
  | .field n m t => do
    let mj ← m.intern
    let tj ← t.intern
    internNode (Json.mkObj [("tag", "field"), ("name", n), ("member", mj), ("tail", tj)])
  | .specification m e => do
    let mj ← m.intern
    let ej ← e.intern
    internNode (Json.mkObj [("tag", "specification"), ("metadata", mj), ("extension", ej)])
  | .variant r => do
    let rj ← r.intern
    internNode (Json.mkObj [("tag", "variant"), ("row", rj)])
  | .computation p r a => do
    let pj ← p.intern
    let rj ← r.intern
    let aj ← a.intern
    internNode (Json.mkObj [("tag", "computation"), ("plan", pj), ("response", rj), ("result", aj)])

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

/-- The typing-proposal fields that translation validation compares. -/
def proposalJson (out : Output) : Except String Json := do
  let bounds := out.sumBounds.mergeSort (fun a b => a.1 ≤ b.1)
  -- A lambda whose type did not resolve names the downstream symptom; the type error the
  -- resolver recorded first is the cause, so the refusal leads with it.
  let annotations ← match annotate bounds out.term [] with
    | .ok a => pure a
    | .error e => throw (match out.typeErrors[0]? with
      | some cause => cause ++ " (" ++ e ++ ")"
      | none => e)
  let some row := out.globalRow | throw (out.typeErrors[0]?.getD "global row unresolved")
  let ((annotationJson, boundJson), interner) := (internProposal annotations row bounds).run {}
  return Json.mkObj [("types", Json.arr interner.table),
    ("annotations", Json.arr annotationJson.toArray),
    ("bounds", Json.arr boundJson.toArray),
    ("shareableVariables", toJson ("0" :: bounds.map (fun b => toString b.1)))]

/-! ## Driver: a batch of jobs in, one result per job out -/

def runJob (job : Json) : Json :=
  let name := (job.getObjValAs? String "name").toOption.getD ""
  let result : Except String Json := do
    let modules ← (← (← job.getObjVal? "modules").getArr?).toList.mapM decodeModule
    let entryModule ← job.getObjValAs? Nat "entryModule"
    let out ← elaborate modules entryModule (← job.getObjValAs? String "entryDefinition")
      (← job.getObjVal? "arguments") ((job.getObjValAs? String "mode").toOption.getD "application")
    let typed := match proposalJson out with
      | .ok j => j
      | .error e => Json.mkObj [("unsupported", toJson e)]
    let erased := match out.term.erase with
      | .ok _ => Json.null
      | .error e => toJson e
    return Json.mkObj [("term", out.term.json), ("typed", typed), ("coreTermErasure", erased)]
  match result with
  | .ok j => Json.mkObj [("name", name), ("ok", toJson true), ("output", j)]
  | .error e => Json.mkObj [("name", name), ("ok", toJson false), ("error", e)]

end Minidregg.Compiler.ObjectiveBendElaborate

