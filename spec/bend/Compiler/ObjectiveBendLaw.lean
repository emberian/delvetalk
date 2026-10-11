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
            | REF == REF | REF <= REF | REF <= REF + INT | REF <= REF + REF
            | monotone(FIELD) | writeOnce(FIELD)
            | appendOnly(FIELD) | unchanged(FIELD) | REF in new.FIELD
            | insertOnly(FIELD) | REF in new.FIELD.COLUMN
            | count(new.FIELD) <= INT | count(new.FIELD) <= count(old.FIELD) + INT
            | changed(new.FIELD.COLUMN) by WHO
    WHO   ::= request.subject | request.caller
    REF   ::= new.FIELD | old.FIELD | request.subject | request.caller | request.height
            | request.turn | request.pin | request.kind | request.method | request.clock
            | request.object
    INT   ::= -?[0-9]+

`implies` binds loosest and associates to the right; `or` then `and` associate to the left;
`not` applies to the atom (or parenthesised expression) after it. Edition 1 reads TOP-LEVEL
fields only: `new.a.b` and `old.a.b` refuse by name. `old.F` is the field before the write
(docs/LAW.md §4 E); at creation, when there is no before, it reads as the empty value of
`new.F`'s type, as `writeOnce` treats an empty field. `request.clock` is the world clock at the
write, in minutes; `request.object` the written object's own id (LAW §4 A, H). The kernel's
predicate reads the clock and the object as slots; an atom reading `old.F`, and the three-slot
bound `REF <= REF + REF`, compile to `any []` and the host judges them, as it judges relations. `appendOnly` holds when the new list is the old list with zero or more items appended;
`unchanged` when the field is equal in old and new. `new.F == request.subject` compares a
text field with the principal.

`changed(new.F.COL) by WHO` (LAW §4 B) ranges over the write's own difference: every row of the
relation F that the write inserted, replaced or retracted (the rows of old absent from new and the
rows of new absent from old, compared whole by canonical bytes, less the rows the declared
retention evicted) has COL equal to the fact; at creation every row counts. A replaced row
contributes both its rows, so a write replaces only the fact's row with the fact's row. -/
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
  /-- The pin of the package the object runs after the write (host extension). -/
  | pin
  /-- 0 for a write of state, 1 for a reprogram, 2 for an amendment, 3 proposed: a state write
  no method of the object made (host extension). Written by name or number. -/
  | kind
  /-- The method whose run made the change, "" for an op (host extension). -/
  | method
  /-- The world clock at the write, in minutes (host extension; LAW §4 A). -/
  | clock
  /-- The written object's own id (host extension; LAW §4 H). -/
  | object
  /-- `old.name`: the top-level field before the write; at creation the empty value (host
  extension; LAW §4 E). -/
  | old (name : String)
  deriving DecidableEq, Repr, Inhabited

/-- The enforced fragment. `old.` appears only through `monotone` and `writeOnce`. -/
inductive LawExpr where
  | eqC (ref : LawRef) (value : Int)
  | leC (ref : LawRef) (value : Int)
  | inC (ref : LawRef) (values : List Int)
  /-- `request.subject`, `request.caller` or `request.pin` equals a text constant. -/
  | eqS (ref : LawRef) (text : String)
  | eqR (left right : LawRef)
  | leR (left right : LawRef)
  | leROff (left right : LawRef) (offset : Int)
  /-- `REF <= REF + REF`, the three-slot bound (`request.clock <= old.tended + new.gap`; host). -/
  | leRSum (left right addend : LawRef)
  | monotone (field : String)
  | writeOnce (field : String)
  /-- The new list is the old list with items appended (host extension). -/
  | appendOnly (field : String)
  /-- The field is equal in old and new (host extension). -/
  | unchanged (field : String)
  /-- `REF in new.FIELD`: the text fact is an item of the list-of-text field (host extension). -/
  | member (ref : LawRef) (field : String)
  /-- The new relation holds every row of the old one, unchanged (relations, host extension). -/
  | insertOnly (field : String)
  /-- `count(new.FIELD) <= INT` (relations, host extension). -/
  | countLe (field : String) (bound : Int)
  /-- `count(new.FIELD) <= count(old.FIELD) + INT` (relations, host extension). -/
  | countGrowth (field : String) (offset : Int)
  /-- `REF in new.FIELD.COLUMN`: the text fact is the COLUMN of some row of the relation
  (relations, host extension). -/
  | memberColumn (ref : LawRef) (field column : String)
  /-- `changed(new.FIELD.COLUMN) by WHO`: every row of the relation this write inserted, replaced or
  retracted, less the evicted, has COLUMN equal to WHO, `request.subject` or `request.caller`
  (relations, host extension; LAW §4 B). -/
  | changed (field column : String) (who : LawRef)
  | not (body : LawExpr)
  | and (left right : LawExpr)
  | or (left right : LawExpr)
  | implies (premise conclusion : LawExpr)
  deriving DecidableEq, Repr, Inhabited

/-- The fields a law reads, in source order (with repetition). -/
def LawRef.fields : LawRef → List String
  | .field name | .old name => [name]
  | _ => []

def LawExpr.fields : LawExpr → List String
  | .eqC ref _ | .leC ref _ | .inC ref _ | .eqS ref _ => ref.fields
  | .eqR left right | .leR left right | .leROff left right _ => left.fields ++ right.fields
  | .leRSum left right addend => left.fields ++ right.fields ++ addend.fields
  | .monotone field | .writeOnce field | .appendOnly field | .unchanged field => [field]
  | .member ref field | .memberColumn ref field _ => ref.fields ++ [field]
  | .insertOnly field | .countLe field _ | .countGrowth field _ | .changed field _ _ => [field]
  | .not body => body.fields
  | .and left right | .or left right | .implies left right => left.fields ++ right.fields

/-- A field or variant name that cannot alias another path (`Kernel.ObjectRecord.stateSlots`
projects only these). Stated over `toList`, so the kernel evaluates it (`String.all` does not
reduce in the kernel) and proofs read its characters. -/
def plainName (name : String) : Bool :=
  !name.toList.isEmpty && name.toList.all (fun c => c != '.' && c != '@' && c != '/')

/-- Every field a law reads is a plain name. -/
def LawRef.plain : LawRef → Bool
  | .field name | .old name => plainName name
  | _ => true

/-- Every field a law names is a law field name. -/
def LawExpr.fieldsPlain : LawExpr → Bool
  | .eqC ref _ | .leC ref _ | .inC ref _ | .eqS ref _ => ref.plain
  | .eqR left right | .leR left right | .leROff left right _ => left.plain && right.plain
  | .leRSum left right addend => left.plain && right.plain && addend.plain
  | .monotone field | .writeOnce field | .appendOnly field | .unchanged field => plainName field
  | .member ref field => ref.plain && plainName field
  | .memberColumn ref field column => ref.plain && plainName field && plainName column
  | .insertOnly field | .countLe field _ | .countGrowth field _ => plainName field
  | .changed field column _ => plainName field && plainName column
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
  | .pin => "request/pin"
  | .kind => "request/kind"
  | .method => "request/method"
  | .clock => "request/clock"
  | .object => "request/object"
  | .old name => "old/" ++ name

/-- Whether a reference reads the state before the write, which no view slot holds. -/
def LawRef.readsOld : LawRef → Bool
  | .old _ => true
  | _ => false

/-- The predicate the kernel installs for a law (`Kernel.ObjectLaw.compile_sound`: it evaluates
to the law's meaning on every view the kernel judges). -/
def compile : LawExpr → Pred
  -- `old.F` is no view slot: an atom reading it is the host's to judge.
  | .eqC ref value => if ref.readsOld then Pred.any [] else .eq ref.slot value
  -- Text constants have no integer reading: the kernel predicate refuses (host laws judge them).
  | .eqS _ _ => Pred.any []
  | .leC ref value => if ref.readsOld then Pred.any [] else .le ref.slot value
  | .inC ref values => if ref.readsOld then Pred.any [] else .memberOf ref.slot values
  | .eqR left right => if left.readsOld || right.readsOld then Pred.any [] else .eqSlots left.slot right.slot
  | .leR left right => if left.readsOld || right.readsOld then Pred.any [] else .leSlots left.slot right.slot
  | .leROff left right offset =>
    if left.readsOld || right.readsOld then Pred.any [] else .leSlotsOff left.slot right.slot offset
  -- A sum of two slots is beyond the kernel predicate: the host judges it.
  | .leRSum _ _ _ => Pred.any []
  | .monotone field => .monotone ("state/" ++ field)
  | .writeOnce field => .writeOnce ("state/" ++ field)
  -- Lists and equality of whole fields are beyond the kernel predicate: host laws judge them.
  | .appendOnly _ | .unchanged _ | .member _ _ => Pred.any []
  -- Relations are lists of records: the host judges these too (RELATIONAL §5).
  | .insertOnly _ | .countLe _ _ | .countGrowth _ _ | .memberColumn _ _ _ | .changed _ _ _ => Pred.any []
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
  | .pin => "request.pin"
  | .kind => "request.kind"
  | .method => "request.method"
  | .clock => "request.clock"
  | .object => "request.object"
  | .old name => "old." ++ name

def LawExpr.render : LawExpr → String
  | .eqC ref value => s!"{ref.render} == {value}"
  | .eqS ref text => s!"{ref.render} == \"{text}\""
  | .leC ref value => s!"{ref.render} <= {value}"
  | .inC ref values => s!"{ref.render} in [{", ".intercalate (values.map toString)}]"
  | .eqR left right => s!"{left.render} == {right.render}"
  | .leR left right => s!"{left.render} <= {right.render}"
  | .leROff left right offset => s!"{left.render} <= {right.render} + {offset}"
  | .leRSum left right addend => s!"{left.render} <= {right.render} + {addend.render}"
  | .monotone field => s!"monotone({field})"
  | .writeOnce field => s!"writeOnce({field})"
  | .appendOnly field => s!"appendOnly({field})"
  | .unchanged field => s!"unchanged({field})"
  | .member ref field => s!"{ref.render} in new.{field}"
  | .insertOnly field => s!"insertOnly({field})"
  | .countLe field bound => s!"count(new.{field}) <= {bound}"
  | .countGrowth field offset => s!"count(new.{field}) <= count(old.{field}) + {offset}"
  | .memberColumn ref field column => s!"{ref.render} in new.{field}.{column}"
  | .changed field column who => s!"changed(new.{field}.{column}) by {who.render}"
  | .not body => s!"not ({body.render})"
  | .and left right => s!"({left.render}) and ({right.render})"
  | .or left right => s!"({left.render}) or ({right.render})"
  | .implies premise conclusion => s!"({premise.render}) implies ({conclusion.render})"

/-! ## Tokens -/

inductive Tok where
  | ident (name : String)
  | int (value : Nat)
  | str (text : String)
  | sym (text : String)
  deriving DecidableEq, Repr, Inhabited

def Tok.render : Tok → String
  | .ident name => "`" ++ name ++ "`"
  | .int value => "`" ++ toString value ++ "`"
  | .str text => "\"" ++ text ++ "\""
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
    else if c == '"' then
      let body := rest.takeWhile (fun d => d != '"')
      match rest.dropWhile (fun d => d != '"') with
      | _ :: more =>
        if body.any (fun d => d == '\\' || d.toNat < 32) then refuse "a text constant with a backslash or control character"
        else return Tok.str (String.ofList body) :: (← tokenize fuel more)
      | [] => refuse "an unterminated text constant"
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
  | "pin" => some .pin
  | "kind" => some .kind
  | "method" => some .method
  | "clock" => some .clock
  | "object" => some .object
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
    | none => refuse ("request." ++ fact ++ " (a law reads request.subject, request.caller, request.height, request.turn, \
        request.pin, request.kind, request.method, request.clock and request.object)")
  | .ident "old" :: .sym "." :: .ident field :: rest =>
    match rest with
    | .sym "." :: _ => refuse ("the nested field path old." ++ field ++ ".… (edition 1 reads top-level fields of the \
        declared state only)")
    | _ => .ok (.old field, rest)
  | .ident "old" :: _ => refuse "old without a field name (a reference is old.FIELD)"
  | t :: _ => refuse (t.render ++ " where a reference new.FIELD, old.FIELD or request.FACT was expected")
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

/-- The request kinds by name: `request.kind == proposed` is `request.kind == 3`. -/
def kindNumber : String → Option Int
  | "write" => some 0 | "reprogram" => some 1 | "amend" => some 2 | "proposed" => some 3 | _ => none

def parseComparison (fuel : Nat) (toks : List Tok) : Except String (LawExpr × List Tok) := do
  let (left, rest) ← parseRef toks
  match rest with
  | .sym "==" :: .str text :: after =>
    match left with
    | .subject | .caller | .pin | .method | .object => return (.eqS left text, after)
    | _ => refuse "a text constant compares with request.subject, request.caller, request.pin, request.method or request.object only"
  | .sym "==" :: .ident name :: after =>
    if left == .kind && name != "new" && name != "request" && name != "old" then
      match kindNumber name with
      | some n => return (.eqC .kind n, after)
      | none => refuse ("request.kind == " ++ name ++ " (a kind is write, reprogram, amend, proposed, or its number)")
    else
      let (right, after') ← parseRef (.ident name :: after)
      return (.eqR left right, after')
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
        if startsInt offset then
          let (k, after') ← parseInt offset
          return (.leROff left right k, after')
        else
          let (addend, after') ← parseRef offset
          return (.leRSum left right addend, after')
      | _ => return (.leR left right, after)
  | .ident "in" :: .ident "new" :: .sym "." :: .ident field :: after =>
    match left, after with
    | _, .sym "." :: .ident _ :: .sym "." :: _ =>
      refuse ("the path new." ++ field ++ ".COLUMN.… (membership reads one column of a relation: REF in new.FIELD.COLUMN)")
    | .subject, .sym "." :: .ident column :: after' | .caller, .sym "." :: .ident column :: after' =>
      return (.memberColumn left field column, after')
    | _, .sym "." :: _ => refuse ("new." ++ field ++ ". without a column name (REF in new.FIELD.COLUMN)")
    | .subject, _ | .caller, _ => return (.member left field, after)
    | _, _ => refuse "membership in a list field or a relation's column reads request.subject or request.caller"
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
    | .ident "appendOnly" :: .sym "(" :: .ident field :: .sym ")" :: after => .ok (.appendOnly field, after)
    | .ident "insertOnly" :: .sym "(" :: .ident field :: .sym ")" :: after => .ok (.insertOnly field, after)
    | .ident "insertOnly" :: _ => refuse "insertOnly takes one top-level relation field: insertOnly(FIELD)"
    | .ident "count" :: .sym "(" :: .ident "new" :: .sym "." :: .ident field :: .sym ")" :: .sym "<=" :: more =>
      if startsInt more then do
        let (bound, after) ← parseInt more
        return (.countLe field bound, after)
      else match more with
        | .ident "count" :: .sym "(" :: .ident "old" :: .sym "." :: .ident other :: .sym ")" :: .sym "+" :: offset =>
          if other != field then refuse ("count(old." ++ other ++ ") beside count(new." ++ field ++ "): a growth bound reads one field")
          else do
            let (k, after) ← parseInt offset
            return (.countGrowth field k, after)
        | _ => refuse "a count bound is count(new.FIELD) <= INT or count(new.FIELD) <= count(old.FIELD) + INT"
    | .ident "changed" :: .sym "(" :: .ident "new" :: .sym "." :: .ident field :: .sym "." :: .ident column :: .sym ")"
        :: .ident "by" :: more => do
      let (who, after) ← parseRef more
      match who with
      | .subject | .caller => return (.changed field column who, after)
      | _ => refuse ("changed(…) by " ++ who.render ++ " (the rows a write changed belong to request.subject or request.caller)")
    | .ident "changed" :: _ => refuse "changed reads one column of a relation the write changed: changed(new.FIELD.COLUMN) by request.subject or request.caller"
    | .ident "count" :: _ => refuse "a count bound is count(new.FIELD) <= INT or count(new.FIELD) <= count(old.FIELD) + INT"
    | .ident "unchanged" :: .sym "(" :: .ident field :: .sym ")" :: after => .ok (.unchanged field, after)
    | .ident "appendOnly" :: _ => refuse "appendOnly takes one top-level field name: appendOnly(FIELD)"
    | .ident "unchanged" :: _ => refuse "unchanged takes one top-level field name: unchanged(FIELD)"
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
    (parse "new.a.b == 1").toBool = false ∧ (parse "old.a.b == 1").toBool = false ∧ (parse "old == 1").toBool = false ∧
      (parse "new.a >= 1").toBool = false ∧ (parse "witnessed(x)").toBool = false ∧
      (parse "new.a == 1 claim").toBool = false ∧ (parse "request.target == 1").toBool = false := by
  native_decide

theorem parse_relational :
    (parse "insertOnly(rains) and count(new.subs) <= 64 and count(new.rains) <= count(old.rains) + 1 and request.subject in new.greeted.principal").toOption =
      some (.and (.and (.and (.insertOnly "rains") (.countLe "subs" 64)) (.countGrowth "rains" 1))
        (.memberColumn .subject "greeted" "principal")) := by native_decide

theorem parse_refuses_relational :
    (parse "insertOnly(a.b)").toBool = false ∧ (parse "count(new.a) <= count(old.b) + 1").toBool = false ∧
      (parse "count(new.a) == 3").toBool = false ∧ (parse "request.height in new.a.b").toBool = false ∧
      (parse "request.subject in new.a.b.c").toBool = false ∧ (parse "count(old.a) <= 3").toBool = false := by
  native_decide

theorem parse_kind_names :
    (parse "request.kind == proposed").toOption = some (.eqC .kind 3) ∧
      (parse "request.kind == write or request.kind == 2").toOption = some (.or (.eqC .kind 0) (.eqC .kind 2)) ∧
      (match parse "request.kind == proposal" with
        | .error e => e == refusalPrefix ++ "request.kind == proposal (a kind is write, reprogram, amend, proposed, or its number)"
        | .ok _ => false) = true ∧
      (parse "new.a == proposed").toBool = false := by
  native_decide

/-- LAW §4 A, E, H: the clock, the object and the state before the write. METAPHYSICS's `alive`
clause in clock minutes; the three-slot bound; `old.F` against `new.F`; the object's id. -/
theorem parse_clock_old_object :
    (parse "request.method == \"tend\" or request.clock <= old.tended + 1440").toOption =
      some (.or (.eqS .method "tend") (.leROff .clock (.old "tended") 1440)) ∧
    (parse "request.clock <= old.tended + new.gap").toOption =
      some (.leRSum .clock (.old "tended") (.field "gap")) ∧
    (parse "new.ticks <= old.ticks or old.last + 0 <= request.clock").toBool = false ∧
    (parse "new.ticks <= old.ticks or old.last <= request.clock").toOption =
      some (.or (.leR (.field "ticks") (.old "ticks")) (.leR (.old "last") .clock)) ∧
    (parse "request.object == \"tide\" and request.subject == request.object").toOption =
      some (.and (.eqS .object "tide") (.eqR .subject .object)) ∧
    (parse "request.clock == \"noon\"").toBool = false ∧
    (parse "request.clock <= old.a.b + 1").toBool = false := by
  native_decide

/-- The clock and the object compile to view slots; an atom reading `old.F` and the three-slot
bound compile to `any []`, the host's to judge; `fields` lists what `old.F` reads. -/
theorem compile_clock_old_object :
    compile (.leC .clock 1440) = .le "request/clock" 1440 ∧
    compile (.eqR .subject .object) = .eqSlots "request/subject" "request/object" ∧
    compile (.leROff .clock (.old "tended") 1440) = Pred.any [] ∧
    compile (.leRSum .clock (.old "tended") (.field "gap")) = Pred.any [] ∧
    (LawExpr.leRSum .clock (.old "tended") (.field "gap")).fields = ["tended", "gap"] ∧
    (parse "request.clock <= old.tended + new.gap").toOption.map LawExpr.render =
      some "request.clock <= old.tended + new.gap" := by
  native_decide

/-- LAW §4 B: the rows a write changed belong to the requester. Tide's `self` and Deal's `signer`
as one line each; the column is named, the field is a top-level relation, the fact is the subject
or the caller; it is the host's to judge, and it renders back to itself. -/
theorem parse_changed :
    (parse "changed(new.subs.who) by request.subject").toOption = some (.changed "subs" "who" .subject) ∧
    (parse "insertOnly(signatures) and changed(new.signatures.principal) by request.caller").toOption =
      some (.and (.insertOnly "signatures") (.changed "signatures" "principal" .caller)) ∧
    (parse "changed(new.subs) by request.subject").toBool = false ∧
    (parse "changed(new.subs.who.x) by request.subject").toBool = false ∧
    (parse "changed(old.subs.who) by request.subject").toBool = false ∧
    (parse "changed(new.subs.who) by request.height").toBool = false ∧
    (parse "changed(new.subs.who) by new.owner").toBool = false ∧
    (parse "changed(new.subs.who)").toBool = false ∧
    (LawExpr.changed "subs" "who" .subject).fields = ["subs"] ∧
    (LawExpr.changed "subs" "who" .subject).fieldsPlain = true ∧
    (LawExpr.changed "subs" "a/b" .subject).fieldsPlain = false ∧
    compile (.changed "subs" "who" .subject) = Pred.any [] ∧
    (parse "(changed(new.lines.author) by request.subject) and (insertOnly(lines))").toOption.map LawExpr.render =
      some "(changed(new.lines.author) by request.subject) and (insertOnly(lines))" := by
  native_decide

end Minidregg.Compiler.ObjectiveBendLaw

#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_tally
#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_precedence
#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_refuses_nested
#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_relational
#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_kind_names
#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_refuses_relational
#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_clock_old_object
#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.compile_clock_old_object
#assert_compiled Minidregg.Compiler.ObjectiveBendLaw.parse_changed
