/- The enforced `law` fragment of Objective Bend: its abstract syntax and its parser.

A package declares, at top level, `law NAME: EXPR`. The law is an admission law over the
declared state of every object created from the package: the kernel judges every write of that
state by it (`Kernel.ObjectLaw`, which gives the fragment its meaning, `LawExpr.denote`, compiles
it to the kernel's `Pred`, and proves the two agree, `compile_sound`). This module is the syntax
only, so the front end can parse it without importing the kernel.

The fragment, exactly (G1B-ENFORCED-LAW-DESIGN; anything else refuses
`law outside the enforced fragment: …`, never a fallback to `claim`):

    EXPR  ::= EXPR implies EXPR | EXPR or EXPR | EXPR and EXPR | not EXPR | ( EXPR ) | ATOM
    ATOM  ::= REF == INT | REF <= INT | REF in [INT, …]
            | REF == REF | REF <= REF | REF <= REF + INT
            | monotone(FIELD) | writeOnce(FIELD)
    REF   ::= new.FIELD | request.subject | request.caller | request.height | request.turn
    INT   ::= -?[0-9]+

`implies` binds loosest and associates to the right; `or` then `and` associate to the left;
`not` applies to the atom (or parenthesised expression) after it. Edition 1 reads TOP-LEVEL
fields only: `new.a.b` refuses by name. `old.` is readable only through `monotone` and
`writeOnce` (all the kernel's predicate can say about the old state). -/
import Theory.AssertCompiled
import Pred.Core
namespace Minidregg.Compiler.ObjectiveBendLaw
open Minidregg.Pred (Pred Slot)
set_option autoImplicit false

/-! ## Syntax -/

/-- A reference a law reads. `field name` is `new.name`, a top-level field of the declared
state; the others are the request facts of the write. -/
inductive LawRef where
  | field (name : String)
  | subject
  | caller
  | height
  | turn
  deriving DecidableEq, Repr, Inhabited

/-- The enforced fragment. `old.` appears only through `monotone` and `writeOnce`. -/
inductive LawExpr where
  | eqC (ref : LawRef) (value : Int)
  | leC (ref : LawRef) (value : Int)
  | inC (ref : LawRef) (values : List Int)
  | eqR (left right : LawRef)
  | leR (left right : LawRef)
  | leROff (left right : LawRef) (offset : Int)
  | monotone (field : String)
  | writeOnce (field : String)
  | not (body : LawExpr)
  | and (left right : LawExpr)
  | or (left right : LawExpr)
  | implies (premise conclusion : LawExpr)
  deriving DecidableEq, Repr, Inhabited

/-- The fields a law reads, in source order (with repetition). -/
def LawRef.fields : LawRef → List String
  | .field name => [name]
  | _ => []

def LawExpr.fields : LawExpr → List String
  | .eqC ref _ | .leC ref _ | .inC ref _ => ref.fields
  | .eqR left right | .leR left right | .leROff left right _ => left.fields ++ right.fields
  | .monotone field | .writeOnce field => [field]
  | .not body => body.fields
  | .and left right | .or left right | .implies left right => left.fields ++ right.fields

/-- A field or variant name that cannot alias another path (`Kernel.ObjectRecord.stateSlots`
projects only these). Stated over `toList`, so the kernel evaluates it (`String.all` does not
reduce in the kernel) and proofs read its characters. -/
def plainName (name : String) : Bool :=
  !name.toList.isEmpty && name.toList.all (fun c => c != '.' && c != '@' && c != '/')

/-- Every field a law reads is a plain name. -/
def LawRef.plain : LawRef → Bool
  | .field name => plainName name
  | _ => true

/-- Every field a law names is a law field name. -/
def LawExpr.fieldsPlain : LawExpr → Bool
  | .eqC ref _ | .leC ref _ | .inC ref _ => ref.plain
  | .eqR left right | .leR left right | .leROff left right _ => left.plain && right.plain
  | .monotone field | .writeOnce field => plainName field
  | .not body => body.fieldsPlain
  | .and left right | .or left right | .implies left right => left.fieldsPlain && right.fieldsPlain

/-! ## Compilation to the kernel's predicate -/

/-- The view slot a reference reads (`ObjectRecord.stateSlots`, `Facts.slots`). -/
def LawRef.slot : LawRef → Slot
  | .field name => "state/" ++ name
  | .subject => "request/subject"
  | .caller => "request/caller"
  | .height => "request/height"
  | .turn => "request/turn"

/-- The predicate the kernel installs for a law (`Kernel.ObjectLaw.compile_sound`: it evaluates
to the law's meaning on every view the kernel judges). -/
def compile : LawExpr → Pred
  | .eqC ref value => .eq ref.slot value
  | .leC ref value => .le ref.slot value
  | .inC ref values => .memberOf ref.slot values
  | .eqR left right => .eqSlots left.slot right.slot
  | .leR left right => .leSlots left.slot right.slot
  | .leROff left right offset => .leSlotsOff left.slot right.slot offset
  | .monotone field => .monotone ("state/" ++ field)
  | .writeOnce field => .writeOnce ("state/" ++ field)
  | .not body => .not (compile body)
  | .and left right => Pred.all [compile left, compile right]
  | .or left right => Pred.any [compile left, compile right]
  | .implies premise conclusion => Pred.any [.not (compile premise), compile conclusion]

/-- **The law a package installs**: the conjunction of its laws, in order. A law whose fields are
not all plain names compiles to `any []` (refuses every write): a field the views cannot read
never reads as something else. -/
def packageLaw (laws : List (String × LawExpr)) : Pred :=
  Pred.all (laws.map fun law => if law.2.fieldsPlain then compile law.2 else Pred.any [])

/-! ## Rendering (diagnostics and documents) -/

def LawRef.render : LawRef → String
  | .field name => "new." ++ name
  | .subject => "request.subject"
  | .caller => "request.caller"
  | .height => "request.height"
  | .turn => "request.turn"

def LawExpr.render : LawExpr → String
  | .eqC ref value => s!"{ref.render} == {value}"
  | .leC ref value => s!"{ref.render} <= {value}"
  | .inC ref values => s!"{ref.render} in [{", ".intercalate (values.map toString)}]"
  | .eqR left right => s!"{left.render} == {right.render}"
  | .leR left right => s!"{left.render} <= {right.render}"
  | .leROff left right offset => s!"{left.render} <= {right.render} + {offset}"
  | .monotone field => s!"monotone({field})"
  | .writeOnce field => s!"writeOnce({field})"
  | .not body => s!"not ({body.render})"
  | .and left right => s!"({left.render}) and ({right.render})"
  | .or left right => s!"({left.render}) or ({right.render})"
  | .implies premise conclusion => s!"({premise.render}) implies ({conclusion.render})"

/-! ## Tokens -/

inductive Tok where
  | ident (name : String)
  | int (value : Nat)
  | sym (text : String)
  deriving DecidableEq, Repr, Inhabited

def Tok.render : Tok → String
  | .ident name => "`" ++ name ++ "`"
  | .int value => "`" ++ toString value ++ "`"
  | .sym text => "`" ++ text ++ "`"

def refusalPrefix : String := "law outside the enforced fragment: "

def refuse {α : Type} (what : String) : Except String α := .error (refusalPrefix ++ what)

def identStart (c : Char) : Bool := ('a' ≤ c && c ≤ 'z') || ('A' ≤ c && c ≤ 'Z') || c == '_'
def identChar (c : Char) : Bool := identStart c || ('0' ≤ c && c ≤ '9')
def digit (c : Char) : Bool := '0' ≤ c && c ≤ '9'

def digitsValue (digits : List Char) : Nat :=
  digits.foldl (fun n c => 10 * n + (c.toNat - '0'.toNat)) 0

def tokenize : Nat → List Char → Except String (List Tok)
  | _, [] => .ok []
  | 0, _ => refuse "token capacity"
  | fuel + 1, c :: rest => do
    if c == ' ' then tokenize fuel rest
    else if identStart c then
      let name := (c :: rest).takeWhile identChar
      return Tok.ident (String.ofList name) :: (← tokenize fuel ((c :: rest).dropWhile identChar))
    else if digit c then
      let digits := (c :: rest).takeWhile digit
      return Tok.int (digitsValue digits) :: (← tokenize fuel ((c :: rest).dropWhile digit))
    else match c, rest with
      | '=', '=' :: more => return Tok.sym "==" :: (← tokenize fuel more)
      | '<', '=' :: more => return Tok.sym "<=" :: (← tokenize fuel more)
      | _, _ =>
        if "()[],.+-".toList.contains c then return Tok.sym (String.singleton c) :: (← tokenize fuel rest)
        else refuse ("the character `" ++ String.singleton c ++ "` (the fragment compares with == and <=, \
          and combines with and, or, not, implies)")

/-! ## The parser -/

def expectSym (text : String) : List Tok → Except String (List Tok)
  | .sym t :: rest => if t == text then .ok rest else refuse ("expected `" ++ text ++ "`, found `" ++ t ++ "`")
  | t :: _ => refuse ("expected `" ++ text ++ "`, found " ++ t.render)
  | [] => refuse ("expected `" ++ text ++ "` at the end of the law")

def parseInt : List Tok → Except String (Int × List Tok)
  | .sym "-" :: .int n :: rest => .ok (-(Int.ofNat n), rest)
  | .int n :: rest => .ok (Int.ofNat n, rest)
  | t :: _ => refuse ("expected an integer literal, found " ++ t.render)
  | [] => refuse "expected an integer literal at the end of the law"

def startsInt : List Tok → Bool
  | .int _ :: _ => true
  | .sym "-" :: _ => true
  | _ => false

def requestFact : String → Option LawRef
  | "subject" => some .subject
  | "caller" => some .caller
  | "height" => some .height
  | "turn" => some .turn
  | _ => none

def parseRef : List Tok → Except String (LawRef × List Tok)
  | .ident "new" :: .sym "." :: .ident field :: rest =>
    match rest with
    | .sym "." :: _ => refuse ("the nested field path new." ++ field ++ ".… (edition 1 reads top-level fields of the \
        declared state only)")
    | _ => .ok (.field field, rest)
  | .ident "request" :: .sym "." :: .ident fact :: rest =>
    match requestFact fact with
    | some ref => .ok (ref, rest)
    | none => refuse ("request." ++ fact ++ " (a law reads request.subject, request.caller, request.height and \
        request.turn)")
  | .ident "old" :: _ => refuse "old.FIELD outside monotone(FIELD) and writeOnce(FIELD)"
  | t :: _ => refuse (t.render ++ " where a reference new.FIELD or request.FACT was expected")
  | [] => refuse "a comparison missing its reference"

def parseIntList : Nat → List Tok → Except String (List Int × List Tok)
  | 0, _ => refuse "list capacity"
  | fuel + 1, toks => do
    let (value, rest) ← parseInt toks
    match rest with
    | .sym "," :: more =>
      let (values, after) ← parseIntList fuel more
      return (value :: values, after)
    | _ => return ([value], ← expectSym "]" rest)

def parseComparison (fuel : Nat) (toks : List Tok) : Except String (LawExpr × List Tok) := do
  let (left, rest) ← parseRef toks
  match rest with
  | .sym "==" :: more =>
    if startsInt more then
      let (value, after) ← parseInt more
      return (.eqC left value, after)
    else
      let (right, after) ← parseRef more
      return (.eqR left right, after)
  | .sym "<=" :: more =>
    if startsInt more then
      let (value, after) ← parseInt more
      return (.leC left value, after)
    else
      let (right, after) ← parseRef more
      match after with
      | .sym "+" :: offset =>
        let (k, after') ← parseInt offset
        return (.leROff left right k, after')
      | _ => return (.leR left right, after)
  | .ident "in" :: .sym "[" :: .sym "]" :: after => return (.inC left [], after)
  | .ident "in" :: .sym "[" :: more =>
    let (values, after) ← parseIntList fuel more
    return (.inC left values, after)
  | t :: _ => refuse ("the operator " ++ t.render ++ " (an atom is REF == …, REF <= …, or REF in [INT, …])")
  | [] => refuse ("the reference " ++ left.render ++ " compared with nothing")

mutual
def parseImplies : Nat → List Tok → Except String (LawExpr × List Tok)
  | 0, _ => refuse "nesting capacity"
  | fuel + 1, toks => do
    let (premise, rest) ← parseOr fuel toks
    match rest with
    | .ident "implies" :: more =>
      let (conclusion, after) ← parseImplies fuel more
      return (.implies premise conclusion, after)
    | _ => return (premise, rest)
def parseOr : Nat → List Tok → Except String (LawExpr × List Tok)
  | 0, _ => refuse "nesting capacity"
  | fuel + 1, toks => do
    let (first, rest) ← parseAnd fuel toks
    parseOrRest fuel first rest
def parseOrRest : Nat → LawExpr → List Tok → Except String (LawExpr × List Tok)
  | 0, _, _ => refuse "nesting capacity"
  | fuel + 1, acc, toks =>
    match toks with
    | .ident "or" :: more => do
      let (next, after) ← parseAnd fuel more
      parseOrRest fuel (.or acc next) after
    | _ => .ok (acc, toks)
def parseAnd : Nat → List Tok → Except String (LawExpr × List Tok)
  | 0, _ => refuse "nesting capacity"
  | fuel + 1, toks => do
    let (first, rest) ← parseUnary fuel toks
    parseAndRest fuel first rest
def parseAndRest : Nat → LawExpr → List Tok → Except String (LawExpr × List Tok)
  | 0, _, _ => refuse "nesting capacity"
  | fuel + 1, acc, toks =>
    match toks with
    | .ident "and" :: more => do
      let (next, after) ← parseUnary fuel more
      parseAndRest fuel (.and acc next) after
    | _ => .ok (acc, toks)
def parseUnary : Nat → List Tok → Except String (LawExpr × List Tok)
  | 0, _ => refuse "nesting capacity"
  | fuel + 1, toks =>
    match toks with
    | .ident "not" :: more => do
      let (body, after) ← parseUnary fuel more
      return (.not body, after)
    | .sym "(" :: more => do
      let (inner, after) ← parseImplies fuel more
      return (inner, ← expectSym ")" after)
    | .ident "monotone" :: .sym "(" :: .ident field :: .sym ")" :: after => .ok (.monotone field, after)
    | .ident "writeOnce" :: .sym "(" :: .ident field :: .sym ")" :: after => .ok (.writeOnce field, after)
    | .ident "monotone" :: _ => refuse "monotone takes one top-level field name: monotone(FIELD)"
    | .ident "writeOnce" :: _ => refuse "writeOnce takes one top-level field name: writeOnce(FIELD)"
    | _ => parseComparison fuel toks
end

/-- Parse the text after `law NAME:`. -/
def parse (text : String) : Except String LawExpr := do
  let toks ← tokenize (text.length + 1) text.toList
  if toks.isEmpty then refuse "an empty law"
  let (law, rest) ← parseImplies (8 * (toks.length + 2)) toks
  match rest with
  | [] => return law
  | t :: _ => refuse ("unexpected " ++ t.render ++ " after a complete law")

/-- Every law of a package, by name: names are unique. -/
def checkNames (laws : List (String × LawExpr)) : Except String Unit := do
  let names := laws.map (·.1)
  if names.eraseDups.length != names.length then
    throw "duplicate law name in a package"

/-! ## The parser decides (compiled evaluation of string functions; named, not `#guard`) -/

theorem parse_tally :
    (parse "new.total <= 1000 and monotone(total)").toOption =
      some (.and (.leC (.field "total") 1000) (.monotone "total")) := by native_decide

theorem parse_precedence :
    (parse "not new.a == 1 or new.b in [1, -2] implies request.caller == new.c and new.d <= new.e + 3").toOption =
      some (.implies (.or (.not (.eqC (.field "a") 1)) (.inC (.field "b") [1, -2]))
        (.and (.eqR .caller (.field "c")) (.leROff (.field "d") (.field "e") 3))) := by native_decide

theorem parse_refuses_nested :
    (parse "new.a.b == 1").toBool = false ∧ (parse "old.a == 1").toBool = false ∧
      (parse "new.a >= 1").toBool = false ∧ (parse "witnessed(x)").toBool = false ∧
      (parse "new.a == 1 claim").toBool = false ∧ (parse "request.target == 1").toBool = false := by
  native_decide

end Minidregg.Compiler.ObjectiveBendLaw

#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_tally
#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_precedence
#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_refuses_nested
