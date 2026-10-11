/- The `law` fragment of Objective Bend: its abstract syntax, its parser and its renderer.

A package declares, at top level, `law NAME "reading": EXPR`, one clause a line. A law is an
admission predicate on one write of one object, judged once at commit on the state before the
write, the state after it and the request's facts (docs/LAW.md §1). The host judges every clause
(`Delvetalk.Host.Law.denote`); this module is the syntax, so the front end and the host parse one
grammar and render it one way. Anything outside it refuses, naming what it found and the rule.

    EXPR   ::= EXPR implies EXPR | EXPR or EXPR | EXPR and EXPR | not EXPR | ( EXPR ) | ATOM
    ATOM   ::= REF == TERM | REF <= TERM
             | TERM in [INT, …] | TERM in new.FIELD | TERM in new.FIELD.COLUMN
             | TERM in "OBJECT".FIELD.COLUMN
             | RULE(FIELD) | changed(new.FIELD.COLUMN) by TERM | under "OBJECT"
    RULE   ::= monotone | writeOnce | appendOnly | unchanged | insertOnly
    TERM   ::= REF | INT | "TEXT" | TERM + TERM
    REF    ::= new.FIELD | old.FIELD | request.FACT | COUNT
    COUNT  ::= count(SIDE.FIELD) | count(SIDE.FIELD where COLUMN == TERM)
    SIDE   ::= new | old
    FACT   ::= subject | caller | height | turn | pin | kind | method | clock | object
    INT    ::= -?[0-9]+
    OBJECT ::= 1..128 bytes of letters, digits and . _ : / -

`implies` binds loosest and associates to the right; `or` then `and` associate to the left; `not`
applies to the atom or parenthesised expression after it; `+` associates to the left. A law reads
top-level fields only: `new.a.b` refuses. `request.kind` compares with a number or a kind's name
(`write` 0, `reprogram` 1, `amend` 2, `proposed` 3). A text constant compares (`==`) with a
reference that reads as text (a field, a principal, the pin, the method, the object), never with
a number, and never sums.

What each form means (the host's `denote` is the definition; docs/LAW.md §4 the design):

- `new.F` and `old.F` read a top-level field after and before the write; at creation `old.F` is
  the empty value of `new.F`'s type, as `writeOnce` reads an empty field. `request.clock` is the
  world clock at the write in minutes; `request.object` the written object's id.
- `count(new.F)` is the number of rows of the relation (or items of the list) F; `count(old.F)`
  before the write, 0 at creation. `where COLUMN == TERM` counts only the rows whose COLUMN equals
  the term by canonical bytes. So `count(new.F where C == V) <= count(old.F where C == V) + 1` is a
  growth bound on the matching rows, and `count(new.G) <= count(new.F where C == V) + 0` a quorum:
  every member of G has its matching row.
- `TERM in …` is membership: in a list of integers, in a list field, or in one column of a
  relation's rows, by canonical bytes. `TERM in "OBJECT".F.C` reads the column C of the relation F
  of another object, at the version the write's turn read: the host records each cited object
  (`LawExpr.reads`) as a root of the write, judged only when the subject may view it; an absent or
  unviewable object holds no member.
- `monotone` (never decreases), `writeOnce` (changes at most once, away from its empty value),
  `appendOnly` (the old list is a prefix of the new), `unchanged`, `insertOnly` (no row of the old
  relation is retracted or altered, rows the declared retention evicted aside).
- `changed(new.F.C) by TERM`: every row of F the write inserted, replaced or retracted (the rows of
  old absent from new and of new absent from old, compared whole by canonical bytes, less the
  evicted) has C equal to the term; at creation every row counts. A replaced row contributes both
  its rows, so a write replaces only the term's row with the term's row.
- `under "OBJECT"` is law by reference: the cited object's `law` field, text in this grammar (one
  `law NAME "reading": EXPR` a line), holds of this write as if its clauses were written here,
  judged on this write's old, new and facts. The cited object is a root (`LawExpr.reads`), so
  amending its law re-laws every object that cites it at their next write. The host resolves the
  citation at judgment: it parses the cited text, follows the citations within it to a bounded
  depth, refuses a cycle or an absent object when the citing law is accepted (creation, amendment,
  reprogram), and judges an absent, unviewable or unparsable citation as holding nothing. -/
import Theory.AssertCompiled
namespace Delvetalk.Compiler.ObjectiveBendLaw
set_option autoImplicit false

/-! ## Syntax -/

/-- A request fact a law reads (`request.FACT`). -/
inductive LawFact where
  | subject | caller | height | turn
  /-- The pin of the package the object runs after the write. -/
  | pin
  /-- 0 a write by the object's own method, 1 reprogram, 2 amend, 3 proposed. -/
  | kind
  /-- The method whose run made the change, "" for an op. -/
  | method
  /-- The world clock at the write, in minutes. -/
  | clock
  /-- The written object's own id. -/
  | object
  deriving DecidableEq, Repr, Inhabited

mutual
/-- What a law compares: a reference into the write (a field, a fact, a count), a constant, or
a sum. -/
inductive LawTerm where
  /-- `new.name`: the top-level field after the write. -/
  | field (name : String)
  /-- `old.name`: the top-level field before the write. -/
  | old (name : String)
  | fact (fact : LawFact)
  /-- `count(of)` or `count(of where COLUMN == VALUE)`, `of` a `field` or an `old`. -/
  | count (of : LawTerm) (filter : LawFilter)
  | int (value : Int)
  | text (text : String)
  | sum (left right : LawTerm)
/-- Which rows a count counts. -/
inductive LawFilter where
  | all
  | eq (column : String) (value : LawTerm)
end
deriving instance DecidableEq for LawTerm, LawFilter
deriving instance Repr for LawTerm, LawFilter
instance : Inhabited LawTerm := ⟨.int 0⟩

/-- What a membership is in. -/
inductive LawPlace where
  /-- `[INT, …]`. -/
  | ints (values : List Int)
  /-- `new.FIELD`, a list field. -/
  | list (field : String)
  /-- `new.FIELD.COLUMN`, one column of a relation's rows. -/
  | column (field column : String)
  /-- `"OBJECT".FIELD.COLUMN`, one column of a relation of another object. -/
  | cited (object field column : String)
  deriving DecidableEq, Repr, Inhabited

/-- The rules over one field's old and new values. -/
inductive LawRule where
  | monotone | writeOnce | appendOnly | unchanged | insertOnly
  deriving DecidableEq, Repr, Inhabited

inductive LawExpr where
  | eq (left right : LawTerm)
  | le (left right : LawTerm)
  | member (term : LawTerm) (place : LawPlace)
  | rule (rule : LawRule) (field : String)
  /-- `changed(new.FIELD.COLUMN) by WHO`. -/
  | changed (field column : String) (who : LawTerm)
  /-- `under "OBJECT"`: the cited object's `law` field holds of this write. -/
  | under (object : String)
  | not (body : LawExpr)
  | and (left right : LawExpr)
  | or (left right : LawExpr)
  | implies (premise conclusion : LawExpr)
  deriving DecidableEq, Repr, Inhabited

/-! ## Names: what a law reads, in one walk -/

/-- A name a law reads: a field of the written object's state, a column of one of its relations,
or a column of another object's relation. -/
inductive LawName where
  | field (name : String)
  | column (name : String)
  | cited (object field column : String)
  /-- The `law` field of another object, cited by `under`. -/
  | law (object : String)
  deriving DecidableEq, Repr

mutual
def LawTerm.names : LawTerm → List LawName
  | .field name | .old name => [.field name]
  | .count of filter => of.names ++ filter.names
  | .sum left right => left.names ++ right.names
  | .fact _ | .int _ | .text _ => []
def LawFilter.names : LawFilter → List LawName
  | .all => []
  | .eq column value => .column column :: value.names
end

def LawPlace.names : LawPlace → List LawName
  | .ints _ => []
  | .list field => [.field field]
  | .column field col => [.field field, .column col]
  | .cited object field col => [.cited object field col]

/-- Every name a law reads, in source order (with repetition). -/
def LawExpr.names : LawExpr → List LawName
  | .eq left right | .le left right => left.names ++ right.names
  | .member term place => term.names ++ place.names
  | .rule _ field => [.field field]
  | .changed field column who => .field field :: .column column :: who.names
  | .under object => [.law object]
  | .not body => body.names
  | .and left right | .or left right | .implies left right => left.names ++ right.names

/-- The fields a law reads, in source order (with repetition). -/
def LawExpr.fields (e : LawExpr) : List String :=
  e.names.filterMap fun | .field name => some name | _ => none

/-- The objects a law cites, each once, in source order: the roots the host records. -/
def LawExpr.reads (e : LawExpr) : List String :=
  (e.names.filterMap fun | .cited object _ _ | .law object => some object | _ => none).eraseDups

/-- An object id a law may cite: 1..128 bytes of letters, digits and `. _ : / -` (the host's
`validObjectId` alphabet). -/
def plainObject (id : String) : Bool :=
  !id.toList.isEmpty && id.utf8ByteSize ≤ 128 &&
    id.toList.all fun c => ('a' ≤ c && c ≤ 'z') || ('A' ≤ c && c ≤ 'Z') || ('0' ≤ c && c ≤ '9') || ".-_:/".toList.contains c

/-- A field or column name that cannot alias another path. Stated over `toList`, so proofs read
its characters. -/
def plainName (name : String) : Bool :=
  !name.toList.isEmpty && name.toList.all (fun c => c != '.' && c != '@' && c != '/')

def LawName.plain : LawName → Bool
  | .field name | .column name => plainName name
  | .cited object f col => plainObject object && plainName f && plainName col
  | .law object => plainObject object

/-- Every name a law reads is plain; a clause that reads another refuses every write. -/
def LawExpr.fieldsPlain (e : LawExpr) : Bool := e.names.all LawName.plain

/-! ## Rendering (receipts, cards, the built package's law text) -/

def LawFact.name : LawFact → String
  | .subject => "subject" | .caller => "caller" | .height => "height" | .turn => "turn"
  | .pin => "pin" | .kind => "kind" | .method => "method" | .clock => "clock" | .object => "object"

def LawFact.all : List LawFact := [.subject, .caller, .height, .turn, .pin, .kind, .method, .clock, .object]

def LawRule.name : LawRule → String
  | .monotone => "monotone" | .writeOnce => "writeOnce" | .appendOnly => "appendOnly"
  | .unchanged => "unchanged" | .insertOnly => "insertOnly"

def LawRule.all : List LawRule := [.monotone, .writeOnce, .appendOnly, .unchanged, .insertOnly]

mutual
def LawTerm.render : LawTerm → String
  | .field name => "new." ++ name
  | .old name => "old." ++ name
  | .fact fact => "request." ++ fact.name
  | .count of filter => "count(" ++ of.render ++ filter.render ++ ")"
  | .int value => toString value
  | .text t => "\"" ++ t ++ "\""
  | .sum left right => left.render ++ " + " ++ right.render
def LawFilter.render : LawFilter → String
  | .all => ""
  | .eq column value => " where " ++ column ++ " == " ++ value.render
end

def LawPlace.render : LawPlace → String
  | .ints values => "[" ++ ", ".intercalate (values.map toString) ++ "]"
  | .list field => "new." ++ field
  | .column field col => "new." ++ field ++ "." ++ col
  | .cited object field col => "\"" ++ object ++ "\"." ++ field ++ "." ++ col

def LawExpr.render : LawExpr → String
  | .eq left right => s!"{left.render} == {right.render}"
  | .le left right => s!"{left.render} <= {right.render}"
  | .member term place => s!"{term.render} in {place.render}"
  | .rule r field => s!"{r.name}({field})"
  | .changed field column who => s!"changed(new.{field}.{column}) by {who.render}"
  | .under object => s!"under \"{object}\""
  | .not body => s!"not ({body.render})"
  | .and left right => s!"({left.render}) and ({right.render})"
  | .or left right => s!"({left.render}) or ({right.render})"
  | .implies premise conclusion => s!"({premise.render}) implies ({conclusion.render})"

/-! ## Refusals: one shape, `law outside the enforced fragment: FOUND (RULE)` -/

def refusalPrefix : String := "law outside the enforced fragment: "

/-- The one refusal: what was found, and the rule it breaks. -/
def refusal (found rule : String) : String := refusalPrefix ++ found ++ " (" ++ rule ++ ")"

def refuse {α : Type} (found rule : String) : Except String α := .error (refusal found rule)

/-- The rules a refusal cites. -/
def termRule : String := "a term is new.FIELD, old.FIELD, request.FACT, count(…), an integer or a \"text\" constant"
def factRule : String :=
  "a law reads " ++ ", ".intercalate (LawFact.all.map fun f => "request." ++ f.name)
def pathRule : String := "a law reads top-level fields only: new.FIELD, old.FIELD"
def countRule : String := "a count is count(new.FIELD) or count(old.FIELD), optionally with where COLUMN == TERM"
def atomRule : String := "an atom is REF == TERM, REF <= TERM, TERM in …, RULE(FIELD), \
  changed(new.FIELD.COLUMN) by TERM or under \"OBJECT\""
def underRule : String := "law by reference is under \"OBJECT\", the object's id in quotes"
def placeRule : String := "membership is in [INT, …], new.FIELD, new.FIELD.COLUMN or \"OBJECT\".FIELD.COLUMN"
def objectRule : String := "a cited object is 1..128 bytes of letters, digits and . _ : / -"
def ruleRule : String := "a rule takes one top-level field: " ++ ", ".intercalate (LawRule.all.map fun r => r.name ++ "(FIELD)")
def changedRule : String := "changed reads one column of a relation: changed(new.FIELD.COLUMN) by a field, \
  request.subject, request.caller, request.pin, request.method, request.object or a text constant"
def kindRule : String := "a kind is write, reprogram, amend, proposed, or its number"
def textRule : String := "a text constant compares with ==, against a field, request.subject, request.caller, \
  request.pin, request.method or request.object"
def memberRule : String := "membership in a field reads a field, request.subject, request.caller, request.pin, \
  request.method, request.object or a text constant; a number is a member of [INT, …]"
def sumRule : String := "+ adds numbers"

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

/-- What a refusal found at this point of the token stream. -/
def found : List Tok → String
  | t :: _ => t.render
  | [] => "the end of the law"

def identStart (c : Char) : Bool := ('a' ≤ c && c ≤ 'z') || ('A' ≤ c && c ≤ 'Z') || c == '_'
def identChar (c : Char) : Bool := identStart c || ('0' ≤ c && c ≤ '9')
def digit (c : Char) : Bool := '0' ≤ c && c ≤ '9'

def digitsValue (digits : List Char) : Nat :=
  digits.foldl (fun n c => 10 * n + (c.toNat - '0'.toNat)) 0

def tokenize : Nat → List Char → Except String (List Tok)
  | _, [] => .ok []
  | 0, _ => refuse "a law" "longer than the tokenizer's capacity"
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
        if body.any (fun d => d == '\\' || d.toNat < 32) then
          refuse ("\"" ++ String.ofList body ++ "\"") "a text constant holds no backslash or control character"
        else return Tok.str (String.ofList body) :: (← tokenize fuel more)
      | [] => refuse ("\"" ++ String.ofList body) "a text constant ends with \""
    else match c, rest with
      | '=', '=' :: more => return Tok.sym "==" :: (← tokenize fuel more)
      | '<', '=' :: more => return Tok.sym "<=" :: (← tokenize fuel more)
      | _, _ =>
        if "()[],.+-".toList.contains c then return Tok.sym (String.singleton c) :: (← tokenize fuel rest)
        else refuse ("`" ++ String.singleton c ++ "`") ("a law compares with == and <=, adds with +, and combines with and, or, not, implies")

/-! ## The parser -/

def expectSym (text : String) (toks : List Tok) : Except String (List Tok) :=
  match toks with
  | .sym t :: rest => if t == text then .ok rest else refuse (found toks) ("expected `" ++ text ++ "`")
  | _ => refuse (found toks) ("expected `" ++ text ++ "`")

def parseInt : List Tok → Except String (Int × List Tok)
  | .sym "-" :: .int n :: rest => .ok (-(Int.ofNat n), rest)
  | .int n :: rest => .ok (Int.ofNat n, rest)
  | toks => refuse (found toks) "expected an integer"

def startsInt : List Tok → Bool
  | .int _ :: _ => true
  | .sym "-" :: _ => true
  | _ => false

def factNamed (name : String) : Option LawFact := LawFact.all.find? (·.name == name)
def ruleNamed (name : String) : Option LawRule := LawRule.all.find? (·.name == name)

/-- The request kinds by name: `request.kind == proposed` is `request.kind == 3`. -/
def kindNumber : String → Option Int
  | "write" => some 0 | "reprogram" => some 1 | "amend" => some 2 | "proposed" => some 3 | _ => none

/-- Whether a term reads as text: a field, the principals, the pin, the method, the object, or a
text constant. -/
def LawTerm.textual : LawTerm → Bool
  | .field _ | .old _ | .text _ => true
  | .fact f => f == .subject || f == .caller || f == .pin || f == .method || f == .object
  | _ => false

/-- Whether a term is a reference: what a comparison starts with. -/
def LawTerm.reference : LawTerm → Bool
  | .int _ | .text _ | .sum _ _ => false
  | _ => true

/-- Whether a term may be added: anything but a text constant (a sum of texts reads as nothing). -/
def LawTerm.addable : LawTerm → Bool
  | .text _ => false
  | _ => true

/-- `new.F` or `old.F`, top-level. -/
def parseSide (toks : List Tok) : Except String (LawTerm × List Tok) :=
  match toks with
  | .ident side :: .sym "." :: .ident field :: rest =>
    if side != "new" && side != "old" then refuse (found toks) termRule
    else match rest with
      | .sym "." :: _ => refuse ("`" ++ side ++ "." ++ field ++ ".…`") pathRule
      | _ => .ok (if side == "new" then .field field else .old field, rest)
  | .ident "old" :: _ | .ident "new" :: _ => refuse (found toks) pathRule
  | _ => refuse (found toks) termRule

mutual
/-- One term without `+`: a reference, an integer or a text constant. -/
def parseOperand : Nat → List Tok → Except String (LawTerm × List Tok)
  | 0, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, toks =>
    match toks with
    | .str text :: rest => .ok (.text text, rest)
    | .ident "request" :: .sym "." :: .ident fact :: rest =>
      match factNamed fact with
      | some f => .ok (.fact f, rest)
      | none => refuse ("`request." ++ fact ++ "`") factRule
    | .ident "count" :: .sym "(" :: rest => do
      let (of, after) ← parseSide rest
      match after with
      | .sym ")" :: more => return (.count of .all, more)
      | .ident "where" :: .ident column :: .sym "==" :: more =>
        let (value, after') ← parseTerm fuel more
        return (.count of (.eq column value), ← expectSym ")" after')
      | _ => refuse (found after) countRule
    | .ident "count" :: _ => refuse (found toks) countRule
    | _ =>
      if startsInt toks then do
        let (value, rest) ← parseInt toks
        return (.int value, rest)
      else parseSide toks
/-- A term: operands joined by `+`, to the left. -/
def parseTerm : Nat → List Tok → Except String (LawTerm × List Tok)
  | 0, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, toks => do
    let (first, rest) ← parseOperand fuel toks
    parseSum fuel first rest
def parseSum : Nat → LawTerm → List Tok → Except String (LawTerm × List Tok)
  | 0, _, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, acc, toks =>
    match toks with
    | .sym "+" :: more => do
      let (next, after) ← parseOperand fuel more
      if !acc.addable || !next.addable then refuse "a text constant beside +" sumRule
      parseSum fuel (.sum acc next) after
    | _ => .ok (acc, toks)
end

def parseIntList : Nat → List Tok → Except String (List Int × List Tok)
  | 0, toks => refuse (found toks) "a list longer than the parser's capacity"
  | fuel + 1, toks => do
    let (value, rest) ← parseInt toks
    match rest with
    | .sym "," :: more =>
      let (values, after) ← parseIntList fuel more
      return (value :: values, after)
    | _ => return ([value], ← expectSym "]" rest)

/-- What follows `in`. -/
def parsePlace (fuel : Nat) (toks : List Tok) : Except String (LawPlace × List Tok) :=
  match toks with
  | .sym "[" :: .sym "]" :: after => .ok (.ints [], after)
  | .sym "[" :: more => do
    let (values, after) ← parseIntList fuel more
    return (.ints values, after)
  | .ident "new" :: .sym "." :: .ident field :: .sym "." :: .ident column :: after =>
    match after with
    | .sym "." :: _ => refuse ("`new." ++ field ++ "." ++ column ++ ".…`") placeRule
    | _ => .ok (.column field column, after)
  | .ident "new" :: .sym "." :: .ident field :: .sym "." :: _ => refuse ("`new." ++ field ++ ".`") placeRule
  | .ident "new" :: .sym "." :: .ident field :: after => .ok (.list field, after)
  | .str object :: .sym "." :: .ident field :: .sym "." :: .ident column :: after =>
    if !plainObject object then refuse ("\"" ++ object ++ "\"") objectRule
    else match after with
      | .sym "." :: _ => refuse ("`\"" ++ object ++ "\"." ++ field ++ "." ++ column ++ ".…`") placeRule
      | _ => .ok (.cited object field column, after)
  | _ => refuse (found toks) placeRule

/-- An atom that starts with a term: a comparison or a membership. -/
def parseComparison (fuel : Nat) (toks : List Tok) : Except String (LawExpr × List Tok) := do
  let (left, rest) ← parseTerm fuel toks
  match rest with
  | .sym op :: more =>
    if op != "==" && op != "<=" then refuse (found rest) atomRule
    else if !left.reference then refuse ("`" ++ left.render ++ "` before " ++ op) "a comparison starts with a reference"
    else
      let (right, after) ← match left, more with
        | .fact .kind, .ident name :: after =>
          if name == "new" || name == "old" || name == "request" || name == "count" then parseTerm fuel more
          else match kindNumber name with
            | some n => pure (LawTerm.int n, after)
            | none => refuse ("`request.kind == " ++ name ++ "`") kindRule
        | _, _ => parseTerm fuel more
      match right with
      | .text _ =>
        if op != "==" || !left.textual then refuse ("`" ++ left.render ++ " " ++ op ++ " " ++ right.render ++ "`") textRule
        else return (.eq left right, after)
      | _ => return (if op == "==" then .eq left right else .le left right, after)
  | .ident "in" :: more => do
    let (place, after) ← parsePlace fuel more
    match place with
    | .ints _ => return (.member left place, after)
    | _ =>
      if left.textual then return (.member left place, after)
      else refuse ("`" ++ left.render ++ " in " ++ place.render ++ "`") memberRule
  | _ => refuse (found rest) atomRule

mutual
def parseImplies : Nat → List Tok → Except String (LawExpr × List Tok)
  | 0, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, toks => do
    let (premise, rest) ← parseOr fuel toks
    match rest with
    | .ident "implies" :: more =>
      let (conclusion, after) ← parseImplies fuel more
      return (.implies premise conclusion, after)
    | _ => return (premise, rest)
def parseOr : Nat → List Tok → Except String (LawExpr × List Tok)
  | 0, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, toks => do
    let (first, rest) ← parseAnd fuel toks
    parseOrRest fuel first rest
def parseOrRest : Nat → LawExpr → List Tok → Except String (LawExpr × List Tok)
  | 0, _, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, acc, toks =>
    match toks with
    | .ident "or" :: more => do
      let (next, after) ← parseAnd fuel more
      parseOrRest fuel (.or acc next) after
    | _ => .ok (acc, toks)
def parseAnd : Nat → List Tok → Except String (LawExpr × List Tok)
  | 0, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, toks => do
    let (first, rest) ← parseUnary fuel toks
    parseAndRest fuel first rest
def parseAndRest : Nat → LawExpr → List Tok → Except String (LawExpr × List Tok)
  | 0, _, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, acc, toks =>
    match toks with
    | .ident "and" :: more => do
      let (next, after) ← parseUnary fuel more
      parseAndRest fuel (.and acc next) after
    | _ => .ok (acc, toks)
def parseUnary : Nat → List Tok → Except String (LawExpr × List Tok)
  | 0, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, toks =>
    match toks with
    | .ident "not" :: more => do
      let (body, after) ← parseUnary fuel more
      return (.not body, after)
    | .sym "(" :: more => do
      let (inner, after) ← parseImplies fuel more
      return (inner, ← expectSym ")" after)
    | .ident "changed" :: .sym "(" :: .ident "new" :: .sym "." :: .ident field :: .sym "." :: .ident column :: .sym ")"
        :: .ident "by" :: more => do
      let (who, after) ← parseTerm fuel more
      if who.textual then return (.changed field column who, after)
      else refuse ("`changed(new." ++ field ++ "." ++ column ++ ") by " ++ who.render ++ "`") changedRule
    | .ident "changed" :: _ => refuse (found toks) changedRule
    | .ident "under" :: .str object :: after =>
      if plainObject object then .ok (.under object, after) else refuse ("\"" ++ object ++ "\"") objectRule
    | .ident "under" :: rest => refuse (found rest) underRule
    | .ident name :: .sym "(" :: .ident field :: .sym ")" :: after =>
      match ruleNamed name with
      | some rule => .ok (.rule rule field, after)
      | none => parseComparison fuel toks
    | .ident name :: _ =>
      if (ruleNamed name).isSome then refuse (found toks) ruleRule else parseComparison fuel toks
    | _ => parseComparison fuel toks
end

/-- Parse the text after `law NAME:`. -/
def parse (text : String) : Except String LawExpr := do
  let toks ← tokenize (text.length + 1) text.toList
  if toks.isEmpty then refuse "an empty law" "a law is one expression"
  let (law, rest) ← parseImplies (8 * (toks.length + 2)) toks
  match rest with
  | [] => return law
  | _ => refuse (found rest) "after a complete law"

/-- Every law of a package, by name: names are unique. -/
def checkNames (laws : List (String × LawExpr)) : Except String Unit := do
  let names := laws.map (·.1)
  if names.eraseDups.length != names.length then
    throw "duplicate law name in a package"

/-! ## The grammar decides (compiled evaluation of string functions; named, not `#guard`)

One family: what parses and to what, what refuses, that rendering reads back, and what a law
names. -/

/-- Laws and what they parse to. -/
def accepted : List (String × LawExpr) := [
  ("new.total <= 1000 and monotone(total)",
    .and (.le (.field "total") (.int 1000)) (.rule .monotone "total")),
  ("not new.a == 1 or new.b in [1, -2] implies request.caller == new.c and new.d <= new.e + 3",
    .implies (.or (.not (.eq (.field "a") (.int 1))) (.member (.field "b") (.ints [1, -2])))
      (.and (.eq (.fact .caller) (.field "c")) (.le (.field "d") (.sum (.field "e") (.int 3))))),
  ("insertOnly(rains) and count(new.subs) <= 64 and count(new.rains) <= count(old.rains) + 1 and request.subject in new.greeted.principal",
    .and (.and (.and (.rule .insertOnly "rains") (.le (.count (.field "subs") .all) (.int 64)))
      (.le (.count (.field "rains") .all) (.sum (.count (.old "rains") .all) (.int 1))))
      (.member (.fact .subject) (.column "greeted" "principal"))),
  ("request.kind == proposed", .eq (.fact .kind) (.int 3)),
  ("request.kind == write or request.kind == 2", .or (.eq (.fact .kind) (.int 0)) (.eq (.fact .kind) (.int 2))),
  ("unchanged(owner) and (request.kind == 0 or request.subject == new.owner)",
    .and (.rule .unchanged "owner") (.or (.eq (.fact .kind) (.int 0)) (.eq (.fact .subject) (.field "owner")))),
  ("writeOnce(closed) and appendOnly(entries) and request.subject in new.parties",
    .and (.and (.rule .writeOnce "closed") (.rule .appendOnly "entries")) (.member (.fact .subject) (.list "parties"))),
  -- LAW §4 A, E, H: METAPHYSICS `alive` in clock minutes; the three-term bound; old and the object.
  ("request.method == \"tend\" or request.clock <= old.tended + 1440",
    .or (.eq (.fact .method) (.text "tend")) (.le (.fact .clock) (.sum (.old "tended") (.int 1440)))),
  ("request.clock <= old.tended + new.gap", .le (.fact .clock) (.sum (.old "tended") (.field "gap"))),
  ("new.ticks <= old.ticks or old.last <= request.clock",
    .or (.le (.field "ticks") (.old "ticks")) (.le (.old "last") (.fact .clock))),
  ("request.object == \"tide\" and request.subject == request.object",
    .and (.eq (.fact .object) (.text "tide")) (.eq (.fact .subject) (.fact .object))),
  -- LAW §4 B: the rows a write changed are the requester's (Tide's `self`, Deal's `signer`).
  ("changed(new.subs.who) by request.subject", .changed "subs" "who" (.fact .subject)),
  ("insertOnly(signatures) and changed(new.signatures.principal) by request.caller",
    .and (.rule .insertOnly "signatures") (.changed "signatures" "principal" (.fact .caller))),
  ("changed(new.made.owner) by new.owner", .changed "made" "owner" (.field "owner")),
  -- LAW §4 C, G: filtered counts (SEEDING folkway 3), their growth, the quorum.
  ("count(new.lines where author == request.subject) <= 1",
    .le (.count (.field "lines") (.eq "author" (.fact .subject))) (.int 1)),
  ("count(new.votes where vote == \"yes\") <= 3 and count(new.votes where n == -1) <= 0",
    .and (.le (.count (.field "votes") (.eq "vote" (.text "yes"))) (.int 3))
      (.le (.count (.field "votes") (.eq "n" (.int (-1)))) (.int 0))),
  ("count(new.lines where author == request.subject) <= count(old.lines where author == request.subject) + 1",
    .le (.count (.field "lines") (.eq "author" (.fact .subject)))
      (.sum (.count (.old "lines") (.eq "author" (.fact .subject))) (.int 1))),
  ("count(new.members) <= count(new.votes where vote == \"yes\") + 0",
    .le (.count (.field "members") .all) (.sum (.count (.field "votes") (.eq "vote" (.text "yes"))) (.int 0))),
  ("count(new.subs) <= new.cap and new.owner in new.parties",
    .and (.le (.count (.field "subs") .all) (.field "cap")) (.member (.field "owner") (.list "parties"))),
  -- LAW §4 D: membership in another object's relation, the object a root.
  ("request.subject in \"circle/porch\".members.principal",
    .member (.fact .subject) (.cited "circle/porch" "members" "principal")),
  ("request.subject in \"bond/anthology\".signatures.principal or new.owner in \"circle/porch\".members.principal",
    .or (.member (.fact .subject) (.cited "bond/anthology" "signatures" "principal"))
      (.member (.field "owner") (.cited "circle/porch" "members" "principal"))),
  -- LAW §4 F: law by reference (a kind's instance under its kind's law).
  ("under \"kind/bell\"", .under "kind/bell"),
  ("under \"kind/bell\" and request.subject == new.maker",
    .and (.under "kind/bell") (.eq (.fact .subject) (.field "maker"))),
  ("count(new.a where b == count(old.a)) == 0",
    .eq (.count (.field "a") (.eq "b" (.count (.old "a") .all))) (.int 0))]

/-- Laws that refuse. -/
def refused : List String := [
  "new.a.b == 1", "old.a.b == 1", "old == 1", "new.a >= 1", "witnessed(x)", "new.a == 1 claim",
  "request.target == 1", "new.a == proposed", "request.kind == proposal", "request.clock == \"noon\"",
  "request.clock <= old.a.b + 1", "new.a <= \"x\"", "new.a <= new.b + \"x\"", "1 == new.a",
  "insertOnly(a.b)", "monotone(a", "count(new.a) == ", "count(new.a.b) <= 1", "count(a) <= 1",
  "count(request.subject) <= 1", "request.subject in new.a.b.c", "request.subject in new.a.",
  "request.subject in old.a", "request.height in new.members", "count(new.a) in new.b", "changed(new.subs) by request.subject", "changed(new.subs.who.x) by request.subject",
  "changed(old.subs.who) by request.subject", "changed(new.subs.who)", "changed(new.subs.who) by request.height", "count(new.l where a.b == 1) <= 1",
  "count(new.l where a <= 1) <= 1", "count(new.l where a == 1 <= 1", "count(new.l where == 1) <= 1",
  "\"x\" == request.subject", "request.subject in \"circle/porch\".members",
  "request.subject in \"circle porch\".members.principal", "request.subject in \"\".members.principal",
  "request.subject in \"c\".members.principal.x", "request.height in \"c\".members.principal",
  "request.subject in \"c\".a/b.principal",
  "under kind", "under", "under \"kind bell\"", "under \"kind/bell\".law", "under (\"kind/bell\")", "old.last + 0 <= request.clock", "new.a == \"x", "new.a == 1 ; new.b == 2", ""]

/-- Laws whose rendering is their own text. -/
def canonical : List String := [
  "request.clock <= old.tended + new.gap",
  "(changed(new.lines.author) by request.subject) and (insertOnly(lines))",
  "count(new.lines where author == request.subject) <= 1",
  "count(new.votes where n == -1) <= count(old.votes where n == -1) + 2",
  "count(new.members) <= count(new.votes where vote == \"yes\") + 0",
  "request.subject in new.greeted.principal", "new.b in [1, -2]",
  "request.subject in \"circle/porch\".members.principal",
  "(under \"kind/bell\") and (request.subject == new.maker)"]

theorem parse_accepts : accepted.all (fun (law, e) => (parse law).toOption == some e) = true := by native_decide

theorem parse_refuses : refused.all (fun law => (parse law).toBool == false) = true := by native_decide

theorem render_reads_back :
    accepted.all (fun (_, e) => (parse e.render).toOption == some e) = true ∧
    canonical.all (fun law => (parse law).toOption.map LawExpr.render == some law) = true := by native_decide

/-- The refusal a law meets, if any. -/
def refusalOf (law : String) : Option String :=
  match parse law with
  | .error message => some message
  | .ok _ => none

theorem refusals_name_what_and_why :
    refusalOf "request.kind == proposal" = some (refusal "`request.kind == proposal`" kindRule) ∧
    refusalOf "new.a.b == 1" = some (refusal "`new.a.…`" pathRule) ∧
    refusalOf "request.clock == \"noon\"" = some (refusal "`request.clock == \"noon\"`" textRule) ∧
    refusalOf "request.height in new.members" = some (refusal "`request.height in new.members`" memberRule) ∧
    refusalOf "request.subject in \"circle porch\".members.principal" = some (refusal "\"circle porch\"" objectRule) ∧
    refusalOf "under kind" = some (refusal "`kind`" underRule) ∧
    refusalOf "under \"kind bell\"" = some (refusal "\"kind bell\"" objectRule) ∧
    refusalOf "insertOnly(a.b)" = some (refusal "`insertOnly`" ruleRule) ∧
    refusalOf "old.last + 0 <= request.clock" = some (refusal "`old.last + 0` before <=" "a comparison starts with a reference") ∧
    refusalOf "new.a >= 1" = some (refusal "`>`" "a law compares with == and <=, adds with +, and combines with and, or, not, implies") := by
  native_decide

theorem names_walk :
    (LawExpr.le (.count (.field "members") .all) (.sum (.count (.field "votes") (.eq "vote" (.field "choice"))) (.int 0))).fields =
      ["members", "votes", "choice"] ∧
    (LawExpr.changed "subs" "who" (.fact .subject)).names = [.field "subs", .column "who"] ∧
    (LawExpr.changed "subs" "a/b" (.fact .subject)).fieldsPlain = false ∧
    (LawExpr.le (.count (.field "lines") (.eq "a/b" (.text "x"))) (.int 1)).fieldsPlain = false ∧
    (LawExpr.member (.fact .subject) (.column "greeted" "principal")).fieldsPlain = true ∧
    (LawExpr.or (.member (.fact .subject) (.cited "circle/porch" "members" "principal"))
      (.and (.member (.field "owner") (.cited "bond/a" "signatures" "principal"))
        (.member (.fact .caller) (.cited "circle/porch" "members" "principal")))).reads = ["circle/porch", "bond/a"] ∧
    (LawExpr.member (.field "owner") (.cited "bond/a" "signatures" "principal")).fields = ["owner"] ∧
    (LawExpr.member (.fact .subject) (.cited "bond/a" "signatures" "principal")).fields = [] ∧
    (LawExpr.member (.fact .subject) (.cited "bond a" "signatures" "principal")).fieldsPlain = false ∧
    (LawExpr.and (.under "kind/bell") (.or (.member (.fact .subject) (.cited "circle/porch" "members" "principal"))
      (.under "kind/bell"))).reads = ["kind/bell", "circle/porch"] ∧
    (LawExpr.and (.under "kind/bell") (.eq (.fact .subject) (.field "maker"))).fields = ["maker"] := by
  native_decide

end Delvetalk.Compiler.ObjectiveBendLaw

#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.parse_accepts
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.parse_refuses
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.render_reads_back
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.refusals_name_what_and_why
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.names_walk
