/- Why the checker refused, and where in the source.

`Typing.check` answers a typed packet with a derivation or nothing. When it answers
nothing, `explain` walks the same term the way `infer` does: at each node it infers the
children in `infer`'s order and fuel, descends into the first child that does not infer,
and at a node whose children all infer it names the premise of the node's rule that fails,
with the expected and found types. It is diagnostics only: it decides nothing (acceptance
stays `check`'s), and a walk that finds every premise satisfied says so generically.

`locate` turns the refused node's position into the source: the elaborator marks every
term it elaborates from a surface node with that node's location (`ATerm.located`, which
the checker never sees), so the innermost mark on the path to a position is the source
of the term there. `Naming` renders checker types in surface syntax, by the declared name
of a record or sum where one has exactly that type. -/
import Compiler.ObjectiveBendElaborate
import Theory.ObjectiveBendTyping
namespace Minidregg.Compiler.ObjectiveBendBlame
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Compiler.ObjectiveBendElaborate (ATerm Loc)
set_option autoImplicit false

/-- The kind of a refusal, for hints. -/
inductive Kind where
  | mismatch
  /-- Applied to an argument but not a function. -/
  | notFunction
  | missingField (name : String)
  | notSum
  | unknownArm (label : String)
  | other
  deriving Inhabited, BEq

structure Blame where
  /-- The refused node, in the checker's positions. -/
  path : List Nat
  /-- What to point at: the node itself or the child whose type is wrong. -/
  focus : List Nat
  message : String
  expected : Option Ty := none
  found : Option Ty := none
  kind : Kind := .other
  deriving Inhabited

def primitiveName : Primitive → String
  | .add => "+" | .multiply => "*" | .equal => "==" | .conjunction => "&&" | .labelEqual => "=="
  | .subtract => "-" | .divide => "/" | .less => "<" | .lessEqual => "<=" | .modulo => "%"
  | .textConcat => "textConcat" | .textTake => "textTake" | .textDrop => "textDrop"
  | .textSpan => "textSpan" | .textBreak => "textBreak"

def unaryName : UnaryPrimitive → String
  | .natText => "natText" | .textLength => "textLength" | .sha256Text => "sha256Text"

def ordinal : Nat → String
  | 0 => "first" | 1 => "second" | 2 => "third" | n => toString (n + 1) ++ "th"

def at_ (path focus : List Nat) (message : String) (kind : Kind := .other)
    (expected found : Option Ty := none) : Blame :=
  { path, focus, message, expected, found, kind }

def mismatch (path focus : List Nat) (message : String) (expected found : Ty) : Blame :=
  { path, focus, message, expected := some expected, found := some found, kind := .mismatch }

mutual
/-- Why `infer` refuses `term` at `position` with `fuel` (called only where it does). -/
partial def explain (a : Assumptions) (ann : Annotations) (ctx : Context) (pos : List Nat) :
    Nat → Term → Blame
  | 0, _ => at_ pos pos "the checker's fuel ran out here"
  | fuel + 1, term =>
    let child := fun (i : Nat) => pos ++ [i]
    let sub := fun (c : Context) (i : Nat) (t : Term) => infer a ann c (child i) fuel t
    let down := fun (c : Context) (i : Nat) (t : Term) => explain a ann c (child i) fuel t
    match term with
    | .bound _ => at_ pos pos "a variable the checker's context does not bind"
    | .nat _ | .boolean _ | .label _ => at_ pos pos "the checker refused a literal"
    | .lam body =>
      match ann pos with
      | none => at_ pos pos "a function the typing proposal does not annotate"
      | some an =>
        let inner : Context := ⟨an.domain, an.parameter⟩ :: ctx
        match sub inner 0 body with
        | none => down inner 0 body
        | some r =>
          if !agree a r.type an.codomain then
            mismatch pos (child 0) "the result is not of the declared result type" an.codomain r.type
          else if !safeUses inner r.uses then
            at_ pos pos "a parameter is used more often than its quantity allows"
          else at_ pos pos "a reusable function captures a value it may use only once"
    | .app function argument =>
      match sub ctx 0 function with
      | none => down ctx 0 function
      | some fn =>
        match sub ctx 1 argument with
        | none => down ctx 1 argument
        | some arg =>
          match callable fn.type with
          | .arrow _ _ domain _ =>
            if !agree a arg.type domain then
              mismatch pos (child 1) "an argument is not of its parameter's type" domain arg.type
            else at_ pos (child 1) "an argument is passed where its quantity forbids it"
          | other => at_ pos (child 0) "this is applied to an argument but is not a function (too many arguments?)"
              .notFunction none (some other)
    | .record fields => explainFields a ann ctx pos 0 fuel fields
    | .get target name =>
      match sub ctx 0 target with
      | none => down ctx 0 target
      | some r => at_ pos pos ("no field `" ++ name ++ "` here") (.missingField name) none (some r.type)
    | .extend target fields =>
      match sub ctx 0 target with
      | none => down ctx 0 target
      | some prior =>
        match inferFields a ann ctx (child 1) 0 fuel fields with
        | none => explainFields a ann ctx (child 1) 0 fuel fields
        | some _ => at_ pos (child 0) "only a record can be extended" .other none (some prior.type)
    | .binary p left right =>
      match sub ctx 0 left with
      | none => down ctx 0 left
      | some l =>
        match sub ctx 1 right with
        | none => down ctx 1 right
        | some r =>
          let (lt, rt, _) := primitiveTypes p
          if l.type != lt then
            mismatch pos (child 0) (primitiveName p ++ " takes " ++ "its first operand of another type") lt l.type
          else mismatch pos (child 1) (primitiveName p ++ " takes its second operand of another type") rt r.type
    | .unary p argument =>
      match sub ctx 0 argument with
      | none => down ctx 0 argument
      | some x => mismatch pos (child 0) (unaryName p ++ " takes its operand of another type") (unaryTypes p).1 x.type
    | .ifZero value zero successor =>
      match sub ctx 0 value with
      | none => down ctx 0 value
      | some v =>
        if v.type != .natural then mismatch pos (child 0) "a Nat match needs a Nat" .natural v.type else
        match sub ctx 1 zero with
        | none => down ctx 1 zero
        | some z =>
          let inner : Context := ⟨.natural, .unrestricted⟩ :: ctx
          match sub inner 2 successor with
          | none => down inner 2 successor
          | some s =>
            if !agree a s.type z.type then
              mismatch pos (child 2) "the arms of this Nat match give different types" z.type s.type
            else at_ pos pos "the predecessor is used more often than its quantity allows"
    | .inject tag payload =>
      match ann pos with
      | none => at_ pos pos ("an injection of `" ++ tag ++ "` the typing proposal does not annotate")
      | some an =>
        match sub ctx 0 payload with
        | none => down ctx 0 payload
        | some v =>
          let row? := match an.codomain with
            | .variant row => some row
            | .variable i => match a.alias i with
              | some (.variant row) => some row
              | _ => none
            | _ => none
          match row? with
          | none => at_ pos pos ("`" ++ tag ++ "` is injected into something that is not a sum") .notSum none (some an.codomain)
          | some row =>
            if row.lookup a.bounds (fuel + 1) tag != some an.domain then
              at_ pos pos ("the sum has no case `" ++ tag ++ "`") (.unknownArm tag) none (some an.codomain)
            else if !agree a v.type an.domain then
              mismatch pos (child 0) ("case `" ++ tag ++ "` carries another type") an.domain v.type
            else at_ pos pos ("case `" ++ tag ++ "` carries an Activity")
    | .case scrutinee arms =>
      match sub ctx 0 scrutinee with
      | none => down ctx 0 scrutinee
      | some v =>
        let produced := match v.type with
          | .computation _ _ produced => produced
          | t => t
        match variantRow a produced with
        | none => at_ pos (child 0) "a match on a value that is not a sum" .notSum none (some produced)
        | some row =>
          match inferArms a ann ctx (child 1) 0 row none fuel arms with
          | none => explainArms a ann ctx (child 1) 0 row none fuel arms
          | some typed => at_ pos pos "the arms of this match do not form an activity over the scrutinee's Plan"
              .other none (some typed.result)
    | .ifBool condition whenTrue whenFalse =>
      match sub ctx 0 condition with
      | none => down ctx 0 condition
      | some c =>
        match sub ctx 1 whenTrue with
        | none => down ctx 1 whenTrue
        | some t =>
          match sub ctx 2 whenFalse with
          | none => down ctx 2 whenFalse
          | some f =>
            if c.type != .boolean then mismatch pos (child 0) "a condition must be a Bool" .boolean c.type
            else mismatch pos (child 2) "the branches of this `if` give different types" t.type f.type
    | .perform plan =>
      match ann pos with
      | none => at_ pos pos "a perform the typing proposal does not annotate"
      | some an =>
        match sub ctx 0 plan with
        | none => down ctx 0 plan
        | some v =>
          if !agree a v.type an.domain then
            mismatch pos (child 0) "perform takes the activity's Plan" an.domain v.type
          else at_ pos pos "the activity's Plan or response is not first-order data"
    | .textJoin list separator =>
      match sub ctx 0 list with
      | none => down ctx 0 list
      | some l =>
        match sub ctx 1 separator with
        | none => down ctx 1 separator
        | some s =>
          if !l.type.isTextList a.bounds then
            at_ pos (child 0) "textJoin takes a list of String" .mismatch none (some l.type)
          else mismatch pos (child 1) "textJoin takes a String separator" .label s.type
    | .toData inner =>
      match sub ctx 0 inner with
      | none => down ctx 0 inner
      | some v => at_ pos (child 0) "only first-order data can be Data (no functions or activities)"
          .mismatch (some .data) (some v.type)
    | .done inner =>
      match sub ctx 0 inner with
      | none => down ctx 0 inner
      | some v => at_ pos (child 0) "an activity's result must be data, not another activity" .other none (some v.type)
    | .refuse _ => at_ pos pos "refuse stands only where an activity over a Plan sum finishes"
    | .specification m e | .prototype m e | .mix m e | .fix m e =>
      match sub ctx 0 m with
      | none => down ctx 0 m
      | some _ =>
        match sub ctx 1 e with
        | none => down ctx 1 e
        | some _ => at_ pos pos "the checker refused this specification, prototype or fixed point"
    | .reflect x | .metadata x | .project x =>
      match sub ctx 0 x with
      | none => down ctx 0 x
      | some v => at_ pos (child 0) "this needs a prototype or specification" .other none (some v.type)

/-- Why `inferFields` refuses (positions `pos ++ [index + k]`, as it numbers them). -/
partial def explainFields (a : Assumptions) (ann : Annotations) (ctx : Context) (pos : List Nat)
    (index : Nat) : Nat → List (String × Term) → Blame
  | 0, _ => at_ pos pos "the checker's fuel ran out here"
  | _ + 1, [] => at_ pos pos "the checker refused this record"
  | fuel + 1, (name, body) :: rest =>
    match infer a ann ctx (pos ++ [index]) fuel body with
    | none => explain a ann ctx (pos ++ [index]) fuel body
    | some first =>
      if first.type.isComputation then
        at_ pos (pos ++ [index]) ("field `" ++ name ++ "` holds an Activity; a field is a shared lazy cell")
      else explainFields a ann ctx pos (index + 1) fuel rest

/-- Why `inferArms` refuses. -/
partial def explainArms (a : Assumptions) (ann : Annotations) (ctx : Context) (pos : List Nat)
    (index : Nat) (row : Ty) (expected : Option Ty) : Nat → List (String × Term) → Blame
  | 0, _ => at_ pos pos "the checker's fuel ran out here"
  | _ + 1, [] => at_ pos pos "a match with no arms"
  | fuel + 1, (name, body) :: rest =>
    match row.lookup a.bounds (fuel + 1) name with
    | none => at_ pos (pos ++ [index]) ("this sum has no case `" ++ name ++ "`") (.unknownArm name) none (some (.variant row))
    | some payload =>
      let inner : Context := ⟨payload, .unrestricted⟩ :: ctx
      match infer a ann inner (pos ++ [index]) fuel body with
      | none => explain a ann inner (pos ++ [index]) fuel body
      | some first =>
        let result := expected.getD first.type
        if !agree a first.type result then
          mismatch pos (pos ++ [index]) ("arm `" ++ name ++ "` gives another type than the first arm") result first.type
        else if !safeUses inner first.uses then
          at_ pos (pos ++ [index]) ("arm `" ++ name ++ "` uses its payload more often than allowed")
        else explainArms a ann ctx pos (index + 1) row (some result) fuel rest
end

/-! ## From a checker position to the source -/

/-- The child of `t` at the head of `path` and the rest of the path (record fields are
children `i`; an extension's fields and a match's arms are children `1, i`). -/
def step : ATerm → List Nat → Option (ATerm × List Nat)
  | .lam _ b, 0 :: rest | .reflect b, 0 :: rest | .metadata b, 0 :: rest | .project b, 0 :: rest
  | .unary _ b, 0 :: rest | .get b _, 0 :: rest | .inject _ _ _ b, 0 :: rest | .perform _ _ b, 0 :: rest
  | .done _ _ b, 0 :: rest | .toData _ b, 0 :: rest => some (b, rest)
  | .app a _, 0 :: rest | .mix a _, 0 :: rest | .fix a _, 0 :: rest | .specification a _, 0 :: rest
  | .prototype a _, 0 :: rest | .binary _ a _, 0 :: rest | .textJoin a _, 0 :: rest => some (a, rest)
  | .app _ b, 1 :: rest | .mix _ b, 1 :: rest | .fix _ b, 1 :: rest | .specification _ b, 1 :: rest
  | .prototype _ b, 1 :: rest | .binary _ _ b, 1 :: rest | .textJoin _ b, 1 :: rest => some (b, rest)
  | .ifZero a _ _, 0 :: rest | .ifBool a _ _, 0 :: rest => some (a, rest)
  | .ifZero _ b _, 1 :: rest | .ifBool _ b _, 1 :: rest => some (b, rest)
  | .ifZero _ _ c, 2 :: rest | .ifBool _ _ c, 2 :: rest => some (c, rest)
  | .record fs, i :: rest => (fs[i]?).map fun (_, v) => (v, rest)
  | .extend a _, 0 :: rest | .case a _, 0 :: rest => some (a, rest)
  | .extend _ fs, 1 :: i :: rest | .case _ fs, 1 :: i :: rest => (fs[i]?).map fun (_, v) => (v, rest)
  | _, _ => none

/-- The innermost location mark on the way to `path` (and at it). -/
partial def locate (t : ATerm) (path : List Nat) (best : Option Loc := none) : Option Loc :=
  match t with
  | .located l inner => locate inner path (some l)
  | _ => match path with
    | [] => best
    | _ => match step t path with
      | some (child, rest) => locate child rest best
      | none => best

/-! ## Types in surface syntax -/

structure Naming where
  /-- Declared records and sums with their types (key `Module.Name`). -/
  named : List (String × Ty) := []
  /-- Recursive sums: their variable and key. -/
  variables : List (Nat × String) := []
  /-- The refusing module's imports (alias, module): `Module.Name` is shown as `Alias.Name`,
  and a name of the refusing module itself without its module. -/
  imports : List (String × String) := []
  module : String := ""
  assumptions : Assumptions := {}

def Naming.show (n : Naming) (key : String) : String :=
  match key.splitOn "." with
  | [m, name] =>
    if m == n.module then name
    else match n.imports.find? (·.2 == m) with
      | some (alias, _) => alias ++ "." ++ name
      | none => key
  | _ => key

partial def Naming.render (n : Naming) (t : Ty) : String :=
  let named := n.named.find? fun (_, ty) => sameType n.assumptions ty t
  match named, t with
  | some (key, _), _ => n.show key
  | _, .natural => "Nat" | _, .boolean => "Bool" | _, .label => "String" | _, .data => "Data"
  | _, .emptyRow => "{}"
  | _, .custody _ => "Custody"
  | _, .variable i => match n.variables.lookup i with
    | some key => n.show key
    | none => if n.assumptions.rigid.contains i then (if i == n.assumptions.rigid.head! then "Self" else "Super")
      else "T" ++ toString i
  | _, .field .. =>
    let rec fields : Ty → List String
      | .field name member tail => (name ++ ": " ++ n.render member) :: fields tail
      | .emptyRow => []
      | other => ["..." ++ n.render other]
    "{" ++ ", ".intercalate (fields t) ++ "}"
  | _, .variant row =>
    let rec cases : Ty → List String
      | .field name member tail => (name ++ ": " ++ n.render member) :: cases tail
      | .emptyRow => []
      | other => ["..." ++ n.render other]
    "(" ++ " | ".intercalate (cases row) ++ ")"
  | _, .arrow _ _ d c => "(" ++ n.render d ++ ") -> " ++ n.render c
  | _, .computation p r a => "Activity<" ++ n.render p ++ ", " ++ n.render r ++ ", " ++ n.render a ++ ">"
  | _, .specification m e => "Specification<" ++ n.render m ++ ", " ++ n.render e ++ ">"
  | _, .prototype s x => "Prototype<" ++ n.render s ++ ", " ++ n.render x ++ ">"

/-- The arrows a function type still waits for. -/
def arity : Ty → Nat
  | .arrow _ _ _ c => arity c + 1
  | _ => 0

/-- The fields of a record type with their types, through a recursive alias. -/
def rowFields (a : Assumptions) : Ty → List (String × Ty)
  | .field name member tail => (name, member) :: rowFieldsTail tail
  | .variable i => match a.alias i with
    | some (.field name member tail) => (name, member) :: rowFieldsTail tail
    | _ => []
  | _ => []
where rowFieldsTail : Ty → List (String × Ty)
  | .field name member tail => (name, member) :: rowFieldsTail tail
  | _ => []

end Minidregg.Compiler.ObjectiveBendBlame
