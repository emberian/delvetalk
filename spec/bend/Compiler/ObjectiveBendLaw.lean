/- The clause language of Objective Bend: law, rule and want, one grammar, one renderer.

A thing's text is one clause a line, each clause a condition in one modality (docs/OVERHAUL.md §2,
docs/FOUNDATION.md §10, docs/LAW.md):

    law  NAME "reading": EXPR                 refuses at commit: [write]φ
    rule NAME "reading": EXPR then SPELL      fires at commit, under the rule's owner: [write]φ then σ
    want NAME "reading": EXPR asks SPELL      poses, judged at read with the clock: φ standing

The host judges every condition with one function (`Delvetalk.Host.Law.denote`); this module is
the syntax, so the package front end, the host and the world parse one grammar and render it one
way. Anything outside it refuses in one shape, `law outside the enforced fragment: FOUND (RULE)`,
naming what it found and the rule it breaks.

    TEXT     ::= CLAUSE, one a line (blank lines aside); names unique across the text
    CLAUSE   ::= law NAME READING? : EXPR
               | rule NAME READING? : EXPR then SPELL
               | want NAME READING? : EXPR asks SPELL
    READING  ::= a JSON string literal
    SPELL    ::= delvetalk …, one line, its holes {TERM}
    EXPR     ::= EXPR implies EXPR | EXPR or EXPR | EXPR and EXPR | not EXPR | ( EXPR ) | ATOM
    ATOM     ::= TERM == TERM | TERM <= TERM | TERM >= TERM
               | TERM in [INT, …] | TERM in SIDE.FIELD | TERM in SIDE.FIELD.COLUMN
               | RULE(FIELD) | changed(TERM) | changed(new.FIELD.COLUMN) by TERM
               | under "OBJECT" | "OBJECT" wants NAME
    RULE     ::= monotone | writeOnce | appendOnly | unchanged | insertOnly
    TERM     ::= TERM + TERM | TERM % INT | REF | INT | "TEXT"
    REF      ::= SIDE.FIELD | request.FACT | count(SIDE.FIELD) | count(SIDE.FIELD where COLUMN == TERM [and COLUMN == TERM …])
    SIDE     ::= new | old | "OBJECT"
    FACT     ::= subject | caller | height | turn | pin | kind | method | verb | clock | object | laws | refusedBy
    INT      ::= -?[0-9]+
    OBJECT   ::= 1..128 bytes of letters, digits and . _ : / -

`implies` binds loosest and associates to the right; `or` then `and` associate to the left; `not`
applies to the atom or parenthesised expression after it; `+` associates to the left and `%` binds
tighter. A clause reads top-level fields only: `new.a.b` refuses. `request.kind` compares with a
number or a kind's name (`write` 0, `reprogram` 1, `amend` 2, `proposed` 3, `rule` 4). A comparison
reads the write (one side holds a reference). A text constant compares (`==`) with a term that reads
as text (a field, a principal, the pin, the method, the verb, the object), never with a number, and
never sums. `then` and `asks` end a rule's and a want's condition, so neither names a column there.

What each form means (the host's `denote` is the definition):

- `SIDE.F` reads a top-level field: `new` after the write, `old` before it (at creation the empty
  value of `new.F`'s type, as `writeOnce` reads an empty field), `"O"` of another object at the
  version the write's turn read, recorded as a root (`LawExpr.reads`). `request.clock` is the world
  clock in minutes, `request.object` the written object's id, `request.verb` the verb the act named
  (a declared method's name, or a grown verb's: docs/FOUNDATION.md §10). `request.laws` and
  `request.refusedBy` are what the object stands at: the count of its law clauses, its own and those
  each `under` citation's text holds (followed, each cited object once), and the count of writes its
  law has refused (the journal's `lawRefused` entries naming it).
- `count(SIDE.F)` is the number of rows of the relation (or items of the list) F; `where COLUMN ==
  TERM` counts only the rows whose COLUMN equals the term by canonical bytes. So
  `count(new.F where C == V) <= count(old.F where C == V) + 1` is a growth bound and `count(new.G)
  <= count(new.F where C == V) + 0` a quorum.
- `TERM % INT` is the remainder by a positive integer, never negative: `new.ticks % 24 == 0` is a
  period. Linear, as `+` is.
- `TERM in …` is membership, by canonical bytes: in a list of integers, in a list field, or in one
  column of a relation's rows, of either side or of another object.
- `monotone`, `writeOnce`, `appendOnly`, `unchanged`, `insertOnly` compare one field's old and new;
  `changed(new.F.C) by TERM`: every row of F the write inserted, replaced or retracted has C equal to
  the term. The `by` after the closing parenthesis selects this row-column atom.
- `changed(TERM)` compares the term's readings with `==` before and after the write: `new`
  reads the old state for the first evaluation, including inside count filters. Explicit `old`
  and cited roots keep their readings. The term reads no request facts. Missing readings, or no
  old state, make it false; work charges both evaluations. A rule without this atom remains a
  level condition, holding on every write while true.
- `under "OBJECT"` is law by reference: the cited object's `law` text holds of this write as if its
  law clauses were written here; its rules and wants follow too (`Host.Law.followed`), owned by the
  cited object's owner. A root.
- `"OBJECT" wants NAME` holds when the cited object's want NAME holds of it as it stands. A root.
- A rule's SPELL is cast under the rule's owner when its condition holds of a write; a want's SPELL
  is what answers it. A hole `{TERM}` is filled with the term's reading at that write (a want's at
  the read): `{request.object}`, `{request.subject}`, `{new.maker}`, `{"garden".tended}`. `me` in a
  spell is the owner's avatar, the host's to resolve.
- A want reads the thing as it stands: no `old`, no request fact but `clock`, `object`, `laws` and
  `refusedBy`, no rule
  over old and new, no `changed`, no `under`, in its condition and its holes alike (refused by
  name at parse). -/
import Theory.AssertCompiled
import Std.Data.HashMap
namespace Delvetalk.Compiler.ObjectiveBendLaw
set_option autoImplicit false

/-! ## Syntax -/

/-- A request fact a condition reads (`request.FACT`). -/
inductive LawFact where
  | subject | caller | height | turn
  /-- The pin of the package the object runs after the write. -/
  | pin
  /-- 0 a write by the object's own method, 1 reprogram, 2 amend, 3 proposed, 4 rule. -/
  | kind
  /-- The method whose run made the change, "" for an op. -/
  | method
  /-- The verb the act named: a declared method's name, or a grown verb's under `act`. -/
  | verb
  /-- The world clock at the write, in minutes. -/
  | clock
  /-- The written object's own id. -/
  | object
  /-- The count of the object's law clauses: its own, and those its `under` citations' texts hold. -/
  | laws
  /-- The count of writes the object's law has refused (`lawRefused` entries naming it). -/
  | refusedBy
  deriving DecidableEq, Repr, Inhabited

/-- Whose state a reference reads: after the write, before it, or another object's. -/
inductive LawSide where
  | new
  | old
  /-- `"OBJECT"`: another object, at the version the write's turn read. -/
  | cited (object : String)
  deriving DecidableEq, Repr, Inhabited

mutual
/-- What a condition compares: a field, a fact, a count, a constant, a sum or a remainder. -/
inductive LawTerm where
  /-- `SIDE.name`: a top-level field. -/
  | field (side : LawSide) (name : String)
  | fact (fact : LawFact)
  /-- `count(SIDE.field)` or `count(SIDE.field where COLUMN == VALUE)`. -/
  | count (side : LawSide) (field : String) (filter : LawFilter)
  | int (value : Int)
  | text (text : String)
  | sum (left right : LawTerm)
  /-- `term % modulus`, the modulus at least 1. -/
  | mod (term : LawTerm) (modulus : Nat)
/-- Which rows a count counts. -/
inductive LawFilter where
  | all
  | eq (column : String) (value : LawTerm)
  | and (left right : LawFilter)
end
deriving instance DecidableEq for LawTerm, LawFilter
deriving instance Repr for LawTerm, LawFilter
instance : Inhabited LawTerm := ⟨.int 0⟩

/-- What a membership is in. -/
inductive LawPlace where
  /-- `[INT, …]`. -/
  | ints (values : List Int)
  /-- `SIDE.FIELD`, a list field. -/
  | list (side : LawSide) (field : String)
  /-- `SIDE.FIELD.COLUMN`, one column of a relation's rows. -/
  | column (side : LawSide) (field column : String)
  deriving DecidableEq, Repr, Inhabited

/-- The rules over one field's old and new values. -/
inductive LawRule where
  | monotone | writeOnce | appendOnly | unchanged | insertOnly
  deriving DecidableEq, Repr, Inhabited

/-- A condition: what a law refuses without, what a rule fires on, what a want poses. -/
inductive LawExpr where
  | eq (left right : LawTerm)
  | le (left right : LawTerm)
  | ge (left right : LawTerm)
  | member (term : LawTerm) (place : LawPlace)
  | rule (rule : LawRule) (field : String)
  /-- `changed(new.FIELD.COLUMN) by WHO`. -/
  | changed (field column : String) (who : LawTerm)
  /-- `changed(TERM)`: the state term differs before and after the write. -/
  | changedTerm (term : LawTerm)
  /-- `under "OBJECT"`: the cited object's `law` text holds of this write. -/
  | under (object : String)
  /-- `"OBJECT" wants NAME`: the cited object's want NAME holds of it as it stands. -/
  | wants (object name : String)
  | not (body : LawExpr)
  | and (left right : LawExpr)
  | or (left right : LawExpr)
  | implies (premise conclusion : LawExpr)
  deriving DecidableEq, Repr, Inhabited

/-- A piece of a spell: its own text, or a hole the firing fills with a term's reading. -/
inductive SpellPart where
  | text (text : String)
  | hole (term : LawTerm)
  deriving DecidableEq, Repr, Inhabited

/-- A spell a rule casts or a want asks for: one `delvetalk` line with holes. -/
structure Spell where
  parts : List SpellPart
  deriving DecidableEq, Repr, Inhabited

/-- What a clause does with its condition: refuses without it, casts a spell when it holds at
commit, or poses it with the spell that answers it. -/
inductive Modality where
  | law
  | rule (spell : Spell)
  | want (spell : Spell)
  deriving DecidableEq, Repr, Inhabited

/-- One line of a thing's text. `reading` is "" when the line gives none. -/
structure Clause where
  modality : Modality
  name : String
  reading : String := ""
  condition : LawExpr
  deriving DecidableEq, Repr, Inhabited

/-! ## Names: what a clause reads, in one walk -/

/-- A name a clause reads: a field of the written object's state, a column of a relation, a field of
another object, another object's law text, or another object's want. -/
inductive LawName where
  | field (name : String)
  | column (name : String)
  | cited (object field : String)
  /-- The `law` text of another object, cited by `under`. -/
  | law (object : String)
  /-- A want of another object, cited by `"O" wants NAME`. -/
  | want (object name : String)
  deriving DecidableEq, Repr

/-- The name a side's field reads under. -/
def LawSide.nameOf (side : LawSide) (field : String) : LawName :=
  match side with
  | .cited object => .cited object field
  | _ => .field field

mutual
def LawTerm.names : LawTerm → List LawName
  | .field side name => [side.nameOf name]
  | .count side name filter => side.nameOf name :: filter.names
  | .sum left right => left.names ++ right.names
  | .mod term _ => term.names
  | .fact _ | .int _ | .text _ => []
def LawFilter.names : LawFilter → List LawName
  | .all => []
  | .eq column value => .column column :: value.names
  | .and left right => left.names ++ right.names
end

-- The request facts a term reads (`request.FACT`), in source order.
mutual
def LawTerm.facts : LawTerm → List LawFact
  | .fact fact => [fact]
  | .count _ _ filter => filter.facts
  | .sum left right => left.facts ++ right.facts
  | .mod term _ => term.facts
  | .field .. | .int _ | .text _ => []
def LawFilter.facts : LawFilter → List LawFact
  | .all => []
  | .eq _ value => value.facts
  | .and left right => left.facts ++ right.facts
end

/-- The request facts a condition reads, in source order (with repetition). -/
def LawExpr.facts : LawExpr → List LawFact
  | .eq left right | .le left right | .ge left right => left.facts ++ right.facts
  | .member term _ => term.facts
  | .changed _ _ who => who.facts
  | .changedTerm term => term.facts
  | .rule .. | .under _ | .wants .. => []
  | .not body => body.facts
  | .and left right | .or left right | .implies left right => left.facts ++ right.facts

/-- A condition that reads the world clock (`request.clock`): judged again when the clock moves. -/
def LawExpr.readsClock (e : LawExpr) : Bool := e.facts.any fun | .clock => true | _ => false

def LawPlace.names : LawPlace → List LawName
  | .ints _ => []
  | .list side field => [side.nameOf field]
  | .column side field col => [side.nameOf field, .column col]

/-- Every name a condition reads, in source order (with repetition). -/
def LawExpr.names : LawExpr → List LawName
  | .eq left right | .le left right | .ge left right => left.names ++ right.names
  | .member term place => term.names ++ place.names
  | .rule _ field => [.field field]
  | .changed field column who => .field field :: .column column :: who.names
  | .changedTerm term => term.names
  | .under object => [.law object]
  | .wants object name => [.want object name]
  | .not body => body.names
  | .and left right | .or left right | .implies left right => left.names ++ right.names

def Spell.names (spell : Spell) : List LawName :=
  spell.parts.flatMap fun | .hole term => term.names | .text _ => []

def Modality.spell? : Modality → Option Spell
  | .law => none
  | .rule spell | .want spell => some spell

/-- Every name a clause reads: its condition's, then its spell's holes'. -/
def Clause.names (c : Clause) : List LawName :=
  c.condition.names ++ (c.modality.spell?.map Spell.names).getD []

/-- The written object's fields among some names, in order (with repetition). -/
def fieldsOf (names : List LawName) : List String :=
  names.filterMap fun | .field name => some name | _ => none

/-- The other objects among some names, each once, in order: the roots the host records. -/
def readsOf (names : List LawName) : List String :=
  (names.filterMap fun | .cited object _ | .law object | .want object _ => some object | _ => none).eraseDups

def LawExpr.fields (e : LawExpr) : List String := fieldsOf e.names
def LawExpr.reads (e : LawExpr) : List String := readsOf e.names
def Clause.fields (c : Clause) : List String := fieldsOf c.names
def Clause.reads (c : Clause) : List String := readsOf c.names

/-- An object id a clause may cite: 1..128 bytes of letters, digits and `. _ : / -` (the host's
`validObjectId` alphabet). -/
def plainObject (id : String) : Bool :=
  !id.toList.isEmpty && id.utf8ByteSize ≤ 128 &&
    id.toList.all fun c => ('a' ≤ c && c ≤ 'z') || ('A' ≤ c && c ≤ 'Z') || ('0' ≤ c && c ≤ '9') || ".-_:/".toList.contains c

/-- A field or column name that cannot alias another path. Stated over `toList`, so proofs read
its characters. -/
def plainName (name : String) : Bool :=
  !name.toList.isEmpty && name.toList.all (fun c => c != '.' && c != '@' && c != '/')

def identStart (c : Char) : Bool := ('a' ≤ c && c ≤ 'z') || ('A' ≤ c && c ≤ 'Z') || c == '_'
def identChar (c : Char) : Bool := identStart c || ('0' ≤ c && c ≤ '9')

/-- A clause's or a want's name: a letter or `_`, then letters, digits and `_`. -/
def identName (name : String) : Bool :=
  match name.toList with
  | c :: rest => identStart c && rest.all identChar
  | [] => false

def LawName.plain : LawName → Bool
  | .field name | .column name => plainName name
  | .cited object name => plainObject object && plainName name
  | .law object => plainObject object
  | .want object name => plainObject object && identName name

/-- Every name a condition reads is plain; a clause that reads another refuses every write. -/
def LawExpr.fieldsPlain (e : LawExpr) : Bool := e.names.all LawName.plain
def Clause.fieldsPlain (c : Clause) : Bool := c.names.all LawName.plain

/-! ## Rendering (receipts, cards, the built package's law text) -/

def LawFact.name : LawFact → String
  | .subject => "subject" | .caller => "caller" | .height => "height" | .turn => "turn"
  | .pin => "pin" | .kind => "kind" | .method => "method" | .verb => "verb" | .clock => "clock"
  | .object => "object" | .laws => "laws" | .refusedBy => "refusedBy"

def LawFact.all : List LawFact :=
  [.subject, .caller, .height, .turn, .pin, .kind, .method, .verb, .clock, .object, .laws, .refusedBy]

/-- The facts a want reads of the thing as it stands: no principal, kind, method or verb. -/
def LawFact.atRead (fact : LawFact) : Bool :=
  fact == .clock || fact == .object || fact == .laws || fact == .refusedBy

def LawRule.name : LawRule → String
  | .monotone => "monotone" | .writeOnce => "writeOnce" | .appendOnly => "appendOnly"
  | .unchanged => "unchanged" | .insertOnly => "insertOnly"

def LawRule.all : List LawRule := [.monotone, .writeOnce, .appendOnly, .unchanged, .insertOnly]

def LawSide.render : LawSide → String
  | .new => "new"
  | .old => "old"
  | .cited object => "\"" ++ object ++ "\""

mutual
def LawTerm.render : LawTerm → String
  | .field side name => side.render ++ "." ++ name
  | .fact fact => "request." ++ fact.name
  | .count side name filter => "count(" ++ side.render ++ "." ++ name ++ (match filter with | .all => "" | _ => " where " ++ filter.render) ++ ")"
  | .int value => toString value
  | .text t => "\"" ++ t ++ "\""
  | .sum left right => left.render ++ " + " ++ right.render
  | .mod term modulus => term.render ++ " % " ++ toString modulus
def LawFilter.render : LawFilter → String
  | .all => ""
  | .eq column value => column ++ " == " ++ value.render
  | .and left right => left.render ++ " and " ++ right.render
end

def LawPlace.render : LawPlace → String
  | .ints values => "[" ++ ", ".intercalate (values.map toString) ++ "]"
  | .list side field => side.render ++ "." ++ field
  | .column side field col => side.render ++ "." ++ field ++ "." ++ col

def LawExpr.render : LawExpr → String
  | .eq left right => s!"{left.render} == {right.render}"
  | .le left right => s!"{left.render} <= {right.render}"
  | .ge left right => s!"{left.render} >= {right.render}"
  | .member term place => s!"{term.render} in {place.render}"
  | .rule r field => s!"{r.name}({field})"
  | .changed field column who => s!"changed(new.{field}.{column}) by {who.render}"
  | .changedTerm term => s!"changed({term.render})"
  | .under object => s!"under \"{object}\""
  | .wants object name => s!"\"{object}\" wants {name}"
  | .not body => s!"not ({body.render})"
  | .and left right => s!"({left.render}) and ({right.render})"
  | .or left right => s!"({left.render}) or ({right.render})"
  | .implies premise conclusion => s!"({premise.render}) implies ({conclusion.render})"

def SpellPart.render : SpellPart → String
  | .text t => t
  | .hole term => "{" ++ term.render ++ "}"

def Spell.render (spell : Spell) : String := String.join (spell.parts.map SpellPart.render)

def Modality.keyword : Modality → String
  | .law => "law" | .rule _ => "rule" | .want _ => "want"

/-- A reading as the line writes it: a JSON string literal. -/
def quoteReading (reading : String) : String := (Lean.Json.str reading).compress

def Clause.render (c : Clause) : String :=
  c.modality.keyword ++ " " ++ c.name ++ (if c.reading.isEmpty then "" else " " ++ quoteReading c.reading) ++
    ": " ++ c.condition.render ++
    (match c.modality with
      | .law => ""
      | .rule spell => " then " ++ spell.render
      | .want spell => " asks " ++ spell.render)

/-! ## What a want may read: the thing as it stands -/

mutual
/-- The first construct of a term that reads past the thing as it stands (`old`, a request fact
not `LawFact.atRead`), rendered. -/
def LawTerm.atRead : LawTerm → Option String
  | .field .old name => some ("old." ++ name)
  | .field _ _ => none
  | .fact fact => if fact.atRead then none else some ("request." ++ fact.name)
  | .count .old name _ => some ("count(old." ++ name ++ ")")
  | .count _ _ filter => filter.atRead
  | .int _ | .text _ => none
  | .sum left right => left.atRead <|> right.atRead
  | .mod term _ => term.atRead
def LawFilter.atRead : LawFilter → Option String
  | .all => none
  | .eq _ value => value.atRead
  | .and left right => left.atRead <|> right.atRead
end

def LawPlace.atRead : LawPlace → Option String
  | .list .old name | .column .old name _ => some ("old." ++ name)
  | _ => none

/-- The first construct of a condition a want cannot read, rendered. -/
def LawExpr.atRead : LawExpr → Option String
  | .eq left right | .le left right | .ge left right => left.atRead <|> right.atRead
  | .member term place => term.atRead <|> place.atRead
  | e@(.rule _ _) | e@(.changed _ _ _) | e@(.changedTerm _) | e@(.under _) => some e.render
  | .wants _ _ => none
  | .not body => body.atRead
  | .and left right | .or left right | .implies left right => left.atRead <|> right.atRead

def Spell.atRead (spell : Spell) : Option String :=
  spell.parts.findSome? fun | .hole term => term.atRead | .text _ => none

/-- What a clause reads that its modality forbids: for a want, past the thing as it stands. -/
def Clause.atRead (c : Clause) : Option String :=
  match c.modality with
  | .want spell => c.condition.atRead <|> spell.atRead
  | _ => none

/-! ## Refusals: one shape, `law outside the enforced fragment: FOUND (RULE)` -/

def refusalPrefix : String := "law outside the enforced fragment: "

/-- The one refusal: what was found, and the rule it breaks. -/
def refusal (found rule : String) : String := refusalPrefix ++ found ++ " (" ++ rule ++ ")"

def refuse {α : Type} (found rule : String) : Except String α := .error (refusal found rule)

/-- The rules a refusal cites. -/
def termRule : String := "a term is new.FIELD, old.FIELD, \"OBJECT\".FIELD, request.FACT, count(…), an integer or a \"text\" constant"
def factRule : String :=
  "a clause reads " ++ ", ".intercalate (LawFact.all.map fun f => "request." ++ f.name)
def pathRule : String := "a clause reads top-level fields only: new.FIELD, old.FIELD, \"OBJECT\".FIELD"
def countRule : String := "a count is count(SIDE.FIELD), optionally with where COLUMN == TERM joined by and; SIDE is new, old or \"OBJECT\""
def atomRule : String := "an atom is TERM == TERM, TERM <= TERM, TERM >= TERM, TERM in …, RULE(FIELD), \
  changed(TERM), changed(new.FIELD.COLUMN) by TERM, under \"OBJECT\" or \"OBJECT\" wants NAME"
def compareRule : String := "a comparison reads the write: one side is new.FIELD, old.FIELD, \"OBJECT\".FIELD, \
  request.FACT or count(…)"
def underRule : String := "law by reference is under \"OBJECT\", the object's id in quotes"
def wantsRule : String := "another thing's want is \"OBJECT\" wants NAME"
def placeRule : String := "membership is in [INT, …], SIDE.FIELD or SIDE.FIELD.COLUMN; SIDE is new, old or \"OBJECT\""
def objectRule : String := "a cited object is 1..128 bytes of letters, digits and . _ : / -"
def ruleRule : String := "a rule takes one top-level field: " ++ ", ".intercalate (LawRule.all.map fun r => r.name ++ "(FIELD)")
def changedRule : String := "changed reads one column of a relation: changed(new.FIELD.COLUMN) by a field, \
  request.subject, request.caller, request.pin, request.method, request.verb, request.object or a text constant"
def changedTermRule : String := "changed(TERM) compares a state term before and after the write; its term reads no request facts"
def kindRule : String := "a kind is write, reprogram, amend, proposed, rule, or its number"
def textRule : String := "a text constant compares with ==, against a field, request.subject, request.caller, \
  request.pin, request.method, request.verb or request.object"
def memberRule : String := "membership in a field reads a field, request.subject, request.caller, request.pin, \
  request.method, request.verb, request.object or a text constant; a number is a member of [INT, …]"
def sumRule : String := "+ adds numbers"
def modRule : String := "a remainder is TERM % INT, a number by an integer at least 1"
def tokenRule : String := "a clause compares with ==, <= and >=, adds with + and %, and combines with and, or, not, implies"
def joinRule : String := "then ends a rule's condition (rule NAME \"reading\": EXPR then SPELL); asks ends a want's \
  (want NAME \"reading\": EXPR asks SPELL); a law refuses and never causes"
def clauseRule : String := "a clause is law NAME \"reading\": EXPR, rule NAME \"reading\": EXPR then SPELL, \
  or want NAME \"reading\": EXPR asks SPELL"
def nameRule : String := "a clause's name is a letter or _, then letters, digits and _"
def readingRule : String := "a reading is a JSON string literal after the clause's name"
def ruleLineRule : String := "a rule is rule NAME \"reading\": EXPR then SPELL"
def wantLineRule : String := "a want is want NAME \"reading\": EXPR asks SPELL"
def spellRule : String := "a spell is one line, delvetalk CARD VERB and its fields, with holes {TERM}"
def holeRule : String := "a hole is {TERM}, a term reading new.FIELD, old.FIELD, \"OBJECT\".FIELD, request.FACT or count(…)"
def wantRule : String := "a want reads the thing as it stands: new.FIELD, \"OBJECT\".FIELD, request.clock, \
  request.object, request.laws, request.refusedBy, counts and remainders of them, and other things' wants"

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

/-- A token as written. -/
def Tok.text : Tok → String
  | .ident name => name
  | .int value => toString value
  | .str text => "\"" ++ text ++ "\""
  | .sym text => text

/-- What a refusal found at this point of the token stream. -/
def found : List Tok → String
  | t :: _ => t.render
  | [] => "the end of the condition"

def digit (c : Char) : Bool := '0' ≤ c && c ≤ '9'

def digitsValue (digits : List Char) : Nat :=
  digits.foldl (fun n c => 10 * n + (c.toNat - '0'.toNat)) 0

/-- The tokens of a condition, up to the identifier `stop` (`then` after a rule's, `asks` after a
want's; "" for none) where it is not a field's name: the tokens before it and the characters after
it, if it was met. `dot` says the previous token was `.`. -/
def tokenize (stop : String) : Nat → Bool → List Char → Except String (List Tok × Option (List Char))
  | _, _, [] => .ok ([], none)
  | 0, _, _ => refuse "a clause" "longer than the tokenizer's capacity"
  | fuel + 1, dot, c :: rest => do
    if c == ' ' then tokenize stop fuel dot rest
    else if identStart c then
      let name := String.ofList ((c :: rest).takeWhile identChar)
      let more := (c :: rest).dropWhile identChar
      if !dot && !stop.isEmpty && name == stop then return ([], some more)
      let (toks, tail) ← tokenize stop fuel false more
      return (Tok.ident name :: toks, tail)
    else if digit c then
      let digits := (c :: rest).takeWhile digit
      let (toks, tail) ← tokenize stop fuel false ((c :: rest).dropWhile digit)
      return (Tok.int (digitsValue digits) :: toks, tail)
    else if c == '"' then
      let body := rest.takeWhile (fun d => d != '"')
      match rest.dropWhile (fun d => d != '"') with
      | _ :: more =>
        if body.any (fun d => d == '\\' || d.toNat < 32) then
          refuse ("\"" ++ String.ofList body ++ "\"") "a text constant holds no backslash or control character"
        else
          let (toks, tail) ← tokenize stop fuel false more
          return (Tok.str (String.ofList body) :: toks, tail)
      | [] => refuse ("\"" ++ String.ofList body) "a text constant ends with \""
    else
      let sym : Option (String × List Char) := match c, rest with
        | '=', '=' :: more => some ("==", more)
        | '<', '=' :: more => some ("<=", more)
        | '>', '=' :: more => some (">=", more)
        | _, _ => if "()[],.+-%".toList.contains c then some (String.singleton c, rest) else none
      match sym with
      | some (text, more) =>
        let (toks, tail) ← tokenize stop fuel (text == ".") more
        return (Tok.sym text :: toks, tail)
      | none => refuse ("`" ++ String.singleton c ++ "`") tokenRule

/-! ## The condition parser -/

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

/-- The kinds of request a condition tells apart by `request.kind`, by name: 0 a write by the
object's own method, 1 reprogram, 2 amend, 3 proposed (a state write not from the object's own
method), 4 rule (the placing of a rule or a want on the object, judged by its law). -/
def kinds : List (String × Nat) := [("write", 0), ("reprogram", 1), ("amend", 2), ("proposed", 3), ("rule", 4)]

/-- `request.kind == proposed` is `request.kind == 3`. -/
def kindNumber (name : String) : Option Int := (kinds.lookup name).map Int.ofNat

/-- Whether a term reads as text: a field, the principals, the pin, the method, the verb, the
object, or a text constant. -/
def LawTerm.textual : LawTerm → Bool
  | .field _ _ | .text _ => true
  | .fact f => f == .subject || f == .caller || f == .pin || f == .method || f == .verb || f == .object
  | _ => false

/-- Whether a term reads the write: a field, a fact or a count somewhere in it. -/
def LawTerm.refers : LawTerm → Bool
  | .field _ _ | .fact _ | .count _ _ _ => true
  | .int _ | .text _ => false
  | .sum left right => left.refers || right.refers
  | .mod term _ => term.refers

/-- Whether a term may be added or divided: anything but a text constant. -/
def LawTerm.addable : LawTerm → Bool
  | .text _ => false
  | _ => true

/-- `new`, `old` or `"OBJECT"`, and the tokens after it. -/
def parseSide : List Tok → Except String (LawSide × List Tok)
  | .ident "new" :: rest => .ok (.new, rest)
  | .ident "old" :: rest => .ok (.old, rest)
  | .str object :: rest => if plainObject object then .ok (.cited object, rest) else refuse ("\"" ++ object ++ "\"") objectRule
  | toks => refuse (found toks) termRule

/-- `SIDE.FIELD`, top-level. -/
def parseRef (toks : List Tok) : Except String ((LawSide × String) × List Tok) :=
  match toks with
  | .ident "new" :: _ | .ident "old" :: _ | .str _ :: _ => do
    let (side, rest) ← parseSide toks
    match rest with
    | .sym "." :: .ident field :: .sym "." :: _ => refuse ("`" ++ side.render ++ "." ++ field ++ ".…`") pathRule
    | .sym "." :: .ident field :: after => .ok ((side, field), after)
    | _ => refuse (found toks) pathRule
  | _ => refuse (found toks) termRule

/-- `% INT` after an operand, to the left. -/
def parseMods : LawTerm → List Tok → Except String (LawTerm × List Tok)
  | acc, .sym "%" :: .int n :: more =>
    if n == 0 then refuse "`% 0`" modRule
    else if !acc.addable then refuse "a text constant beside %" modRule
    else parseMods (.mod acc n) more
  | _, .sym "%" :: rest => refuse ("`%" ++ (match rest with | t :: _ => " " ++ t.text | [] => "") ++ "`") modRule
  | acc, toks => .ok (acc, toks)

mutual
/-- One term without `+` or `%`: a reference, an integer or a text constant. -/
def parseOperand : Nat → List Tok → Except String (LawTerm × List Tok)
  | 0, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, toks =>
    match toks with
    | .str _ :: .sym "." :: _ => do
      let ((side, field), rest) ← parseRef toks
      return (.field side field, rest)
    | .str text :: rest => .ok (.text text, rest)
    | .ident "request" :: .sym "." :: .ident fact :: rest =>
      match factNamed fact with
      | some f => .ok (.fact f, rest)
      | none => refuse ("`request." ++ fact ++ "`") factRule
    | .ident "count" :: .sym "(" :: rest => do
      let ((side, field), after) ← parseRef rest
      match after with
      | .sym ")" :: more => return (.count side field .all, more)
      | .ident "where" :: more =>
        let (filter, after') ← parseFilter fuel more
        return (.count side field filter, ← expectSym ")" after')
      | _ => refuse (found after) countRule
    | .ident "count" :: _ => refuse (found toks) countRule
    | _ =>
      if startsInt toks then do
        let (value, rest) ← parseInt toks
        return (.int value, rest)
      else do
        let ((side, field), rest) ← parseRef toks
        return (.field side field, rest)
/-- Equality tests joined by `and` inside a count's `where`, all on the same row. -/
def parseFilter : Nat → List Tok → Except String (LawFilter × List Tok)
  | 0, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, .ident column :: .sym "==" :: more => do
    let (value, rest) ← parseTerm fuel more
    match rest with
    | .ident "and" :: tail =>
      let (next, after) ← parseFilter fuel tail
      return (.and (.eq column value) next, after)
    | _ => return (.eq column value, rest)
  | _, toks => refuse (found toks) countRule
/-- A term: operands, each with its remainders, joined by `+`, to the left. -/
def parseTerm : Nat → List Tok → Except String (LawTerm × List Tok)
  | 0, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, toks => do
    let (first, rest) ← parseOperand fuel toks
    let (first, rest) ← parseMods first rest
    parseSum fuel first rest
def parseSum : Nat → LawTerm → List Tok → Except String (LawTerm × List Tok)
  | 0, _, toks => refuse (found toks) "nested deeper than the parser's capacity"
  | fuel + 1, acc, toks =>
    match toks with
    | .sym "+" :: more => do
      let (next, after) ← parseOperand fuel more
      let (next, after) ← parseMods next after
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
  | .ident "new" :: _ | .ident "old" :: _ | .str _ :: _ => do
    let (side, rest) ← parseSide toks
    match rest with
    | .sym "." :: .ident field :: .sym "." :: .ident column :: after =>
      match after with
      | .sym "." :: _ => refuse ("`" ++ side.render ++ "." ++ field ++ "." ++ column ++ ".…`") placeRule
      | _ => .ok (.column side field column, after)
    | .sym "." :: .ident field :: .sym "." :: _ => refuse ("`" ++ side.render ++ "." ++ field ++ ".`") placeRule
    | .sym "." :: .ident field :: after => .ok (.list side field, after)
    | _ => refuse (found toks) placeRule
  | _ => refuse (found toks) placeRule

/-- An atom that starts with a term: a comparison or a membership. -/
def parseComparison (fuel : Nat) (toks : List Tok) : Except String (LawExpr × List Tok) := do
  let (left, rest) ← parseTerm fuel toks
  match rest with
  | .sym op :: more =>
    if op != "==" && op != "<=" && op != ">=" then refuse (found rest) atomRule
    else
      let (right, after) ← match left, more with
        | .fact .kind, .ident name :: after =>
          if name == "new" || name == "old" || name == "request" || name == "count" then parseTerm fuel more
          else match kindNumber name with
            | some n => pure (LawTerm.int n, after)
            | none => refuse ("`request.kind " ++ op ++ " " ++ name ++ "`") kindRule
        | _, _ => parseTerm fuel more
      let shown := "`" ++ left.render ++ " " ++ op ++ " " ++ right.render ++ "`"
      match left, right with
      | .text _, other | other, .text _ =>
        if op != "==" || !other.textual then refuse shown textRule
        else if !other.refers then refuse shown compareRule
        else return (.eq left right, after)
      | _, _ =>
        if !left.refers && !right.refers then refuse shown compareRule
        else return (if op == "==" then .eq left right else if op == "<=" then .le left right else .ge left right, after)
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
    | .ident "changed" :: .sym "(" :: more => do
      let (term, after) ← parseTerm fuel more
      let rest ← expectSym ")" after
      if !term.facts.isEmpty then refuse ("`changed(" ++ term.render ++ ")`") changedTermRule
      match rest with
      | .ident "by" :: _ => refuse ("`changed(" ++ term.render ++ ") by`") changedRule
      | _ => return (.changedTerm term, rest)
    | .ident "changed" :: _ => refuse (found toks) changedRule
    | .ident "under" :: .str object :: after =>
      if plainObject object then .ok (.under object, after) else refuse ("\"" ++ object ++ "\"") objectRule
    | .ident "under" :: rest => refuse (found rest) underRule
    | .str object :: .ident "wants" :: .ident name :: after =>
      if plainObject object then .ok (.wants object name, after) else refuse ("\"" ++ object ++ "\"") objectRule
    | .str _ :: .ident "wants" :: rest => refuse (found rest) wantsRule
    | .ident name :: .sym "(" :: .ident field :: .sym ")" :: after =>
      match ruleNamed name with
      | some rule => .ok (.rule rule field, after)
      | none => parseComparison fuel toks
    | .ident name :: _ =>
      if (ruleNamed name).isSome then refuse (found toks) ruleRule else parseComparison fuel toks
    | _ => parseComparison fuel toks
end

/-- A whole condition from its tokens. -/
def parseCondition (toks : List Tok) : Except String LawExpr := do
  if toks.isEmpty then refuse "an empty condition" "a condition is one expression"
  let (e, rest) ← parseImplies (8 * (toks.length + 2)) toks
  match rest with
  | [] => return e
  | .ident "then" :: _ | .ident "asks" :: _ => refuse (found rest) joinRule
  | _ => refuse (found rest) "after a complete condition"

/-- Parse a condition alone: the text after a clause's `:` (a package's `law NAME: EXPR`). -/
def parse (text : String) : Except String LawExpr := do
  let (toks, _) ← tokenize "" (text.length + 1) false text.toList
  parseCondition toks

/-! ## Spells and their holes -/

def spaces (cs : List Char) : List Char := cs.dropWhile Char.isWhitespace
def trimChars (cs : List Char) : List Char := (spaces (spaces cs).reverse).reverse

/-- A hole's term: it parses whole and reads the write. -/
def parseHole (body : List Char) : Except String LawTerm :=
  let named := "`{" ++ String.ofList body ++ "}`"
  match tokenize "" (body.length + 1) false body with
  | .error _ => refuse named holeRule
  | .ok (toks, _) => match parseTerm (8 * (toks.length + 2)) toks with
    | .ok (term, []) => if term.refers then .ok term else refuse named holeRule
    | _ => refuse named holeRule

def textPart (acc : List Char) : List SpellPart :=
  if acc.isEmpty then [] else [.text (String.ofList acc.reverse)]

/-- A spell's text and holes; `acc` is the text so far, reversed. -/
def spellParts : Nat → List Char → List Char → Except String (List SpellPart)
  | 0, _, _ => refuse "a spell" "longer than the parser's capacity"
  | _ + 1, acc, [] => .ok (textPart acc)
  | fuel + 1, acc, '{' :: rest => do
    let body := rest.takeWhile fun c => c != '}' && c != '{'
    match rest.drop body.length with
    | '}' :: more =>
      let term ← parseHole body
      return textPart acc ++ .hole term :: (← spellParts fuel [] more)
    | _ => refuse ("`{" ++ String.ofList body ++ "`") holeRule
  | _ + 1, _, '}' :: _ => refuse "`}`" holeRule
  | fuel + 1, acc, c :: rest => spellParts fuel (c :: acc) rest

/-- What a refusal found at the head of some characters: the first word, or the end. -/
def foundWord (cs : List Char) (where_ : String) : String :=
  match cs with
  | [] => "the end of the " ++ where_
  | _ => "`" ++ String.ofList (cs.takeWhile fun c => !c.isWhitespace) ++ "`"

/-- A spell: one `delvetalk` line with holes. -/
def parseSpell (chars : List Char) : Except String Spell := do
  let cs := trimChars chars
  unless cs.take 10 == "delvetalk ".toList && !(spaces (cs.drop 10)).isEmpty do
    refuse (foundWord cs "spell") spellRule
  return ⟨← spellParts (cs.length + 1) [] cs⟩

/-! ## Clauses -/

/-- The JSON string literal that opens `chars`: its length, if it closes. -/
def closeQuote : List Char → Nat → Option Nat
  | [], _ => none
  | '\\' :: _ :: more, n => closeQuote more (n + 2)
  | '"' :: _, n => some n
  | _ :: more, n => closeQuote more (n + 1)

/-- The reading that opens `chars` (a JSON string literal) and the characters after it. -/
def parseReading (chars : List Char) : Except String (String × List Char) :=
  match closeQuote (chars.drop 1) 1 with
  | none => refuse ("`" ++ String.ofList chars ++ "`") readingRule
  | some n =>
    let literal := String.ofList (chars.take (n + 1))
    match Lean.Json.parse literal with
    | .ok (.str reading) => .ok (reading, chars.drop (n + 1))
    | _ => refuse ("`" ++ literal ++ "`") readingRule

/-- The reading after a clause's name, as text: the reading and the rest after it, or none when the
text does not open with one. -/
def splitReading (rest : String) : Except String (Option (String × String)) :=
  match rest.toList with
  | chars@('"' :: _) => (parseReading chars).map fun (reading, more) => some (reading, String.ofList more)
  | _ => .ok none

def keywords : List String := ["law", "rule", "want"]

/-- The text after a clause's `:`, in its modality: the condition, then for a rule `then SPELL` and
for a want `asks SPELL`. -/
def parseBody (keyword : String) (body : String) : Except String (Modality × LawExpr) := do
  let stop := if keyword == "rule" then "then" else if keyword == "want" then "asks" else ""
  let (toks, tail) ← tokenize stop (body.length + 1) false body.toList
  let condition ← parseCondition toks
  match keyword, tail with
  | "law", _ => return (.law, condition)
  | "rule", some spell => return (.rule (← parseSpell spell), condition)
  | "want", some spell => return (.want (← parseSpell spell), condition)
  | "rule", none => refuse "the end of the rule" ruleLineRule
  | "want", none => refuse "the end of the want" wantLineRule
  | _, _ => refuse ("`" ++ keyword ++ "`") clauseRule

/-- A line split into its clause, before its modality's own check; with the text after `:`. -/
def parseRawClause (line : String) : Except String (Clause × String) := do
  let chars := trimChars line.toList
  let word := chars.takeWhile identChar
  let keyword := String.ofList word
  unless keywords.contains keyword && (chars.drop word.length).head? == some ' ' do
    refuse (foundWord chars "clause") clauseRule
  let afterKeyword := spaces (chars.drop word.length)
  let name := afterKeyword.takeWhile identChar
  unless identName (String.ofList name) do refuse (foundWord afterKeyword "clause") nameRule
  let afterName := spaces (afterKeyword.drop name.length)
  let (reading, rest) ← match afterName with
    | '"' :: _ => parseReading afterName
    | _ => pure ("", afterName)
  match spaces rest with
  | ':' :: body =>
    let source := String.ofList (spaces body)
    let (modality, condition) ← parseBody keyword source
    return ({ modality, name := String.ofList name, reading, condition }, source)
  | more => refuse (foundWord more "clause") clauseRule

/-- A clause stands when its modality reads what it may: a want, the thing as it stands. -/
def admit (c : Clause) : Except String Clause :=
  match c.atRead with
  | some what => refuse ("`" ++ what ++ "` in a want") wantRule
  | none => .ok c

/-- One line of a thing's text, with the text after its `:` as written (a package keeps it). -/
def parseClauseSource (line : String) : Except String (Clause × String) := do
  let (raw, source) ← parseRawClause line
  return (← admit raw, source)

def parseClause (line : String) : Except String Clause := (·.1) <$> parseClauseSource line

/-- Clause names are unique across a text: a receipt, a firing and a want name one. -/
def checkNames (names : List String) : Except String Unit :=
  -- The first name (in order) that occurs twice, from one count of each.
  let counts := names.foldl (fun (m : Std.HashMap String Nat) n => m.insert n (m.getD n 0 + 1)) {}
  match names.find? fun n => counts.getD n 0 > 1 with
  | some n => refuse ("`" ++ n ++ "` twice") "a clause's name is unique across its text"
  | none => .ok ()

/-- A thing's text: one clause a line, blank lines aside. -/
def parseText (text : String) : Except String (List Clause) := do
  let lines := ((text.splitOn "\n").map fun l => String.ofList (trimChars l.toList)).filter (!·.isEmpty)
  let clauses ← lines.mapM parseClause
  checkNames (clauses.map (·.name))
  return clauses

/-- The law clauses of some clauses, as the host's `Law` holds them. -/
def lawsOf (clauses : List Clause) : List (String × LawExpr) :=
  clauses.filterMap fun c => if c.modality == .law then some (c.name, c.condition) else none

/-! ## A parsed want reads the thing as it stands (for every line) -/

theorem admit_ok {c c' : Clause} (h : admit c = .ok c') : c' = c ∧ c.atRead = none := by
  unfold admit at h
  split at h
  · simp [refuse] at h
  · rename_i hn
    simp at h
    exact ⟨h.symm, hn⟩

theorem parseClauseSource_reads_now {line : String} {c : Clause} {source : String}
    (h : parseClauseSource line = .ok (c, source)) : c.atRead = none := by
  unfold parseClauseSource at h
  cases hr : parseRawClause line with
  | error e => simp [hr, bind, Except.bind] at h
  | ok p =>
    obtain ⟨raw, src⟩ := p
    cases ha : admit raw with
    | error e => simp [hr, ha, bind, Except.bind] at h
    | ok c' =>
      simp [hr, ha, bind, Except.bind, pure, Except.pure] at h
      obtain ⟨rfl, -⟩ := h
      have := admit_ok ha
      rw [this.1]
      exact this.2

/-- Every clause the parser accepts reads what its modality may: a want's condition and holes read
the thing as it stands. -/
theorem parsed_want_reads_as_it_stands {line : String} {c : Clause} (h : parseClause line = .ok c) :
    c.atRead = none := by
  unfold parseClause at h
  cases hs : parseClauseSource line with
  | error e => simp [hs, Functor.map, Except.map] at h
  | ok p =>
    simp [hs, Functor.map, Except.map] at h
    subst h
    exact parseClauseSource_reads_now hs

/-! ## The grammar decides (compiled evaluation of string functions; named, not `#guard`)

One family: what parses and to what, what refuses, that rendering reads back, and what a clause
names; for conditions alone and for clauses of each modality. -/

/-- Conditions and what they parse to. -/
def accepted : List (String × LawExpr) := [
  ("new.total <= 1000 and monotone(total)",
    .and (.le (.field .new "total") (.int 1000)) (.rule .monotone "total")),
  ("not new.a == 1 or new.b in [1, -2] implies request.caller == new.c and new.d <= new.e + 3",
    .implies (.or (.not (.eq (.field .new "a") (.int 1))) (.member (.field .new "b") (.ints [1, -2])))
      (.and (.eq (.fact .caller) (.field .new "c")) (.le (.field .new "d") (.sum (.field .new "e") (.int 3))))),
  ("insertOnly(rains) and count(new.subs) <= 64 and count(new.rains) <= count(old.rains) + 1 and request.subject in new.greeted.principal",
    .and (.and (.and (.rule .insertOnly "rains") (.le (.count .new "subs" .all) (.int 64)))
      (.le (.count .new "rains" .all) (.sum (.count .old "rains" .all) (.int 1))))
      (.member (.fact .subject) (.column .new "greeted" "principal"))),
  ("request.kind == proposed", .eq (.fact .kind) (.int 3)),
  ("request.kind == write or request.kind == 2", .or (.eq (.fact .kind) (.int 0)) (.eq (.fact .kind) (.int 2))),
  ("unchanged(owner) and (request.kind == 0 or request.subject == new.owner)",
    .and (.rule .unchanged "owner") (.or (.eq (.fact .kind) (.int 0)) (.eq (.fact .subject) (.field .new "owner")))),
  ("writeOnce(closed) and appendOnly(entries) and request.subject in new.parties",
    .and (.and (.rule .writeOnce "closed") (.rule .appendOnly "entries")) (.member (.fact .subject) (.list .new "parties"))),
  -- LAW §4 A, E, H: METAPHYSICS `alive` in clock minutes; the three-term bound; old and the object.
  ("request.method == \"tend\" or request.clock <= old.tended + 1440",
    .or (.eq (.fact .method) (.text "tend")) (.le (.fact .clock) (.sum (.field .old "tended") (.int 1440)))),
  ("request.clock <= old.tended + new.gap", .le (.fact .clock) (.sum (.field .old "tended") (.field .new "gap"))),
  ("new.ticks <= old.ticks or old.last <= request.clock",
    .or (.le (.field .new "ticks") (.field .old "ticks")) (.le (.field .old "last") (.fact .clock))),
  ("request.object == \"tide\" and request.subject == request.object",
    .and (.eq (.fact .object) (.text "tide")) (.eq (.fact .subject) (.fact .object))),
  -- LAW §4 B: the rows a write changed are the requester's (Tide's `self`, Deal's `signer`).
  ("changed(new.subs.who) by request.subject", .changed "subs" "who" (.fact .subject)),
  ("insertOnly(signatures) and changed(new.signatures.principal) by request.caller",
    .and (.rule .insertOnly "signatures") (.changed "signatures" "principal" (.fact .caller))),
  ("changed(new.made.owner) by new.owner", .changed "made" "owner" (.field .new "owner")),
  -- LAW §4 C, G: filtered counts (SEEDING folkway 3), their growth, the quorum.
  ("count(new.lines where verb == \"rain\" and author == new.maker) >= 1",
    .ge (.count .new "lines" (.and (.eq "verb" (.text "rain")) (.eq "author" (.field .new "maker")))) (.int 1)),
  ("count(new.lines where author == request.subject) <= 1",
    .le (.count .new "lines" (.eq "author" (.fact .subject))) (.int 1)),
  ("count(new.votes where vote == \"yes\") <= 3 and count(new.votes where n == -1) <= 0",
    .and (.le (.count .new "votes" (.eq "vote" (.text "yes"))) (.int 3))
      (.le (.count .new "votes" (.eq "n" (.int (-1)))) (.int 0))),
  ("count(new.lines where author == request.subject) <= count(old.lines where author == request.subject) + 1",
    .le (.count .new "lines" (.eq "author" (.fact .subject)))
      (.sum (.count .old "lines" (.eq "author" (.fact .subject))) (.int 1))),
  ("count(new.members) <= count(new.votes where vote == \"yes\") + 0",
    .le (.count .new "members" .all) (.sum (.count .new "votes" (.eq "vote" (.text "yes"))) (.int 0))),
  ("count(new.subs) <= new.cap and new.owner in new.parties",
    .and (.le (.count .new "subs" .all) (.field .new "cap")) (.member (.field .new "owner") (.list .new "parties"))),
  -- LAW §4 D: membership in another object's relation, the object a root.
  ("request.subject in \"circle/porch\".members.principal",
    .member (.fact .subject) (.column (.cited "circle/porch") "members" "principal")),
  ("request.subject in \"bond/anthology\".signatures.principal or new.owner in \"circle/porch\".members.principal",
    .or (.member (.fact .subject) (.column (.cited "bond/anthology") "signatures" "principal"))
      (.member (.field .new "owner") (.column (.cited "circle/porch") "members" "principal"))),
  -- LAW §4 F: law by reference (a kind's instance under its kind's law).
  ("under \"kind/bell\"", .under "kind/bell"),
  ("old.last + old.gap <= request.clock", .le (.sum (.field .old "last") (.field .old "gap")) (.fact .clock)),
  ("under \"kind/bell\" and request.subject == new.maker",
    .and (.under "kind/bell") (.eq (.fact .subject) (.field .new "maker"))),
  ("count(new.a where b == count(old.a)) == 0",
    .eq (.count .new "a" (.eq "b" (.count .old "a" .all))) (.int 0)),
  -- OVERHAUL §2 and FOUNDATION §10: `>=`, a comparison reading the write on either side, another
  -- object's field as a reference, membership before the write, `%`, the verb, the kind `rule`,
  -- another thing's want.
  ("count(new.presence) >= 3 and count(old.presence) <= 2",
    .and (.ge (.count .new "presence" .all) (.int 3)) (.le (.count .old "presence" .all) (.int 2))),
  ("request.method == \"tend\" and old.tended + 1 <= new.tended and 0 + 1 <= old.tended",
    .and (.and (.eq (.fact .method) (.text "tend")) (.le (.sum (.field .old "tended") (.int 1)) (.field .new "tended")))
      (.le (.sum (.int 0) (.int 1)) (.field .old "tended"))),
  ("request.method == \"tick\" and request.clock <= \"garden\".tended + 1440",
    .and (.eq (.fact .method) (.text "tick")) (.le (.fact .clock) (.sum (.field (.cited "garden") "tended") (.int 1440)))),
  ("\"done\" in new.marks.name and not \"done\" in old.marks.name",
    .and (.member (.text "done") (.column .new "marks" "name")) (.not (.member (.text "done") (.column .old "marks" "name")))),
  ("request.subject in old.parties", .member (.fact .subject) (.list .old "parties")),
  ("request.subject in \"circle/porch\".keepers", .member (.fact .subject) (.list (.cited "circle/porch") "keepers")),
  ("new.ticks % 24 == 0", .eq (.mod (.field .new "ticks") 24) (.int 0)),
  ("new.a % 7 % 3 + 1 <= new.b", .le (.sum (.mod (.mod (.field .new "a") 7) 3) (.int 1)) (.field .new "b")),
  ("request.verb == \"water\" or request.kind == rule",
    .or (.eq (.fact .verb) (.text "water")) (.eq (.fact .kind) (.int 4))),
  ("\"garden\" wants rain", .wants "garden" "rain"),
  ("request.method == \"tick\" and not \"garden\" wants rain",
    .and (.eq (.fact .method) (.text "tick")) (.not (.wants "garden" "rain"))),
  ("count(\"circle/porch\".members where role == \"keeper\") >= 2",
    .ge (.count (.cited "circle/porch") "members" (.eq "role" (.text "keeper"))) (.int 2)),
  ("\"tide\" == request.object and 1 == new.a",
    .and (.eq (.text "tide") (.fact .object)) (.eq (.int 1) (.field .new "a"))),
  ("request.laws >= 2 and request.refusedBy >= 1",
    .and (.ge (.fact .laws) (.int 2)) (.ge (.fact .refusedBy) (.int 1)))]

/-- Conditions that refuse. -/
def refused : List String := [
  "new.a.b == 1", "old.a.b == 1", "old == 1", "new.a > 1", "witnessed(x)", "new.a == 1 claim",
  "request.target == 1", "new.a == proposed", "request.kind == proposal", "request.clock == \"noon\"",
  "request.clock <= old.a.b + 1", "new.a <= \"x\"", "new.a <= new.b + \"x\"", "1 == 2", "\"a\" == \"b\"",
  "insertOnly(a.b)", "monotone(a", "count(new.a) == ", "count(new.a.b) <= 1", "count(a) <= 1",
  "count(request.subject) <= 1", "request.subject in new.a.b.c", "request.subject in new.a.",
  "request.subject in old", "request.height in new.members", "count(new.a) in new.b", "changed(new.subs) by request.subject", "changed(new.subs.who.x) by request.subject",
  "changed(old.subs.who) by request.subject", "changed(new.subs.who)", "changed(new.subs.who) by request.height", "count(new.l where a.b == 1) <= 1",
  "count(new.l where a <= 1) <= 1", "count(new.l where a == 1 <= 1", "count(new.l where == 1) <= 1",
  "\"x\" <= request.subject", "request.subject in \"circle porch\".members.principal", "request.subject in \"\".members.principal",
  "request.subject in \"c\".members.principal.x", "request.height in \"c\".members.principal",
  "request.subject in \"c\".a/b.principal", "\"g\".a.b == 1", "\"g h\".a == 1", "count(\"g h\".a) <= 1",
  "under kind", "under", "under \"kind bell\"", "under \"kind/bell\".law",  "under (\"kind/bell\")",
  "new.a == \"x", "new.a == 1 ; new.b == 2", "",
  "new.a % 0 == 0", "new.a % -1 == 0", "new.a % new.b == 0", "\"x\" % 2 == 0", "new.a % == 0",
  "\"g\" wants", "\"g\" wants 3", "\"g h\" wants rain", "request.kind == rules",
  "new.a == 1 then delvetalk x ring", "new.a == 1 asks delvetalk x ring", "new.a == {new.b}"]

/-- Conditions whose rendering is their own text. -/
def canonical : List String := [
  "request.clock <= old.tended + new.gap",
  "old.last + old.gap <= request.clock",
  "(changed(new.lines.author) by request.subject) and (insertOnly(lines))",
  "count(new.lines where author == request.subject) <= 1",
  "count(new.votes where n == -1) <= count(old.votes where n == -1) + 2",
  "count(new.members) <= count(new.votes where vote == \"yes\") + 0",
  "request.subject in new.greeted.principal", "new.b in [1, -2]",
  "request.subject in \"circle/porch\".members.principal",
  "(under \"kind/bell\") and (request.subject == new.maker)",
  "count(new.presence) >= 3", "request.clock <= \"garden\".tended + 1440",
  "\"done\" in old.marks.name", "new.ticks % 24 == 0", "\"garden\" wants rain", "request.verb == \"water\"",
  "count(\"circle/porch\".members where role == \"keeper\") >= 2"]

theorem parse_accepts : accepted.all (fun (law, e) => (parse law).toOption == some e) = true := by native_decide

theorem parse_refuses : refused.all (fun law => (parse law).toBool == false) = true := by native_decide

theorem render_reads_back :
    accepted.all (fun (_, e) => (parse e.render).toOption == some e) = true ∧
    canonical.all (fun law => (parse law).toOption.map LawExpr.render == some law) = true := by native_decide

private def law' (name : String) (condition : LawExpr) (reading : String := "") : Clause :=
  { modality := .law, name, reading, condition }
private def rule' (name : String) (condition : LawExpr) (spell : List SpellPart) (reading : String := "") : Clause :=
  { modality := .rule ⟨spell⟩, name, reading, condition }
private def want' (name : String) (condition : LawExpr) (spell : List SpellPart) (reading : String := "") : Clause :=
  { modality := .want ⟨spell⟩, name, reading, condition }

/-- Clauses of each modality and what they parse to: FOUNDATION §10's six rules as typed from a card,
the kind's rules and wants OVERHAUL §3 names, and the holes. -/
def clauses : List (String × Clause) := [
  ("law owner \"the owner amends\": request.kind == write or request.subject == new.owner",
    law' "owner" (.or (.eq (.fact .kind) (.int 0)) (.eq (.fact .subject) (.field .new "owner"))) "the owner amends"),
  ("law plain: new.a <= 1", law' "plain" (.le (.field .new "a") (.int 1))),
  ("law placed \"a rule is the maker's to place\": request.kind == rule implies request.subject == new.maker",
    law' "placed" (.implies (.eq (.fact .kind) (.int 4)) (.eq (.fact .subject) (.field .new "maker"))) "a rule is the maker's to place"),
  ("rule three: count(new.presence) >= 3 and count(old.presence) <= 2 then delvetalk sluice knock",
    rule' "three" (.and (.ge (.count .new "presence" .all) (.int 3)) (.le (.count .old "presence" .all) (.int 2)))
      [.text "delvetalk sluice knock"]),
  ("rule twice: request.method == \"tend\" and old.tended + 1 <= new.tended and 0 + 1 <= old.tended then delvetalk garden/bell/2 ring",
    rule' "twice" (.and (.and (.eq (.fact .method) (.text "tend")) (.le (.sum (.field .old "tended") (.int 1)) (.field .new "tended")))
      (.le (.sum (.int 0) (.int 1)) (.field .old "tended"))) [.text "delvetalk garden/bell/2 ring"]),
  ("rule seven: count(new.lines) >= 7 then delvetalk anchor/1 adopt / law: law sealed \"seven lines and no more\": count(new.lines) <= 7",
    rule' "seven" (.ge (.count .new "lines" .all) (.int 7))
      [.text "delvetalk anchor/1 adopt / law: law sealed \"seven lines and no more\": count(new.lines) <= 7"]),
  ("rule company: request.method == \"tick\" and request.clock <= \"garden\".tended + 1440 then delvetalk weather rain",
    rule' "company" (.and (.eq (.fact .method) (.text "tick")) (.le (.fact .clock) (.sum (.field (.cited "garden") "tended") (.int 1440))))
      [.text "delvetalk weather rain"]),
  ("rule next: \"done\" in new.marks.name and not \"done\" in old.marks.name then delvetalk quest/1 door / label: next / to: quest/2",
    rule' "next" (.and (.member (.text "done") (.column .new "marks" "name")) (.not (.member (.text "done") (.column .old "marks" "name"))))
      [.text "delvetalk quest/1 door / label: next / to: quest/2"]),
  ("rule two: count(new.lines) >= 2 and count(old.lines) <= 1 then delvetalk me note / text: bell/2 has two rains",
    rule' "two" (.and (.ge (.count .new "lines" .all) (.int 2)) (.le (.count .old "lines" .all) (.int 1)))
      [.text "delvetalk me note / text: bell/2 has two rains"]),
  ("rule rings \"rings at its seventh rain\": count(new.lines) >= 7 and count(old.lines) <= 6 then delvetalk {request.object} ring",
    rule' "rings" (.and (.ge (.count .new "lines" .all) (.int 7)) (.le (.count .old "lines" .all) (.int 6)))
      [.text "delvetalk ", .hole (.fact .object), .text " ring"] "rings at its seventh rain"),
  ("rule rang: \"rung\" in new.marks.name and not \"rung\" in old.marks.name then delvetalk me note / text: {request.object} rang for {new.maker}",
    rule' "rang" (.and (.member (.text "rung") (.column .new "marks" "name")) (.not (.member (.text "rung") (.column .old "marks" "name"))))
      [.text "delvetalk me note / text: ", .hole (.fact .object), .text " rang for ", .hole (.field .new "maker")]),
  ("rule water: request.verb == \"water\" then delvetalk {request.object} tend / by: {request.subject}",
    rule' "water" (.eq (.fact .verb) (.text "water"))
      [.text "delvetalk ", .hole (.fact .object), .text " tend / by: ", .hole (.fact .subject)]),
  ("rule daily: request.method == \"tick\" and new.ticks % 24 == 0 then delvetalk weather rain / count: {count(new.ticks) + 1}",
    rule' "daily" (.and (.eq (.fact .method) (.text "tick")) (.eq (.mod (.field .new "ticks") 24) (.int 0)))
      [.text "delvetalk weather rain / count: ", .hole (.sum (.count .new "ticks" .all) (.int 1))]),
  ("rule rests: request.method == \"tick\" and not \"garden\" wants rain then delvetalk weather rest",
    rule' "rests" (.and (.eq (.fact .method) (.text "tick")) (.not (.wants "garden" "rain"))) [.text "delvetalk weather rest"]),
  ("want second \"wants rain from a second hand\": count(new.lines) <= 1 asks delvetalk {request.object} rain / text: <words>",
    want' "second" (.le (.count .new "lines" .all) (.int 1))
      [.text "delvetalk ", .hole (.fact .object), .text " rain / text: <words>"] "wants rain from a second hand"),
  ("want tending \"untended a day\": new.tended + 1440 <= request.clock asks delvetalk {request.object} tend",
    want' "tending" (.le (.sum (.field .new "tended") (.int 1440)) (.fact .clock))
      [.text "delvetalk ", .hole (.fact .object), .text " tend"] "untended a day"),
  ("want five: count(new.things) <= 4 and not \"garden/bell/1\" wants tending asks delvetalk {request.object} plant / colour: amber",
    want' "five" (.and (.le (.count .new "things" .all) (.int 4)) (.not (.wants "garden/bell/1" "tending")))
      [.text "delvetalk ", .hole (.fact .object), .text " plant / colour: amber"]),
  ("want company: request.clock <= \"garden\".tended + 1440 asks delvetalk garden write / text: {\"garden\".tended}",
    want' "company" (.le (.fact .clock) (.sum (.field (.cited "garden") "tended") (.int 1440)))
      [.text "delvetalk garden write / text: ", .hole (.field (.cited "garden") "tended")]),
  ("want tried \"a law and a second hand's try\": request.laws >= 2 and request.refusedBy <= 0 asks delvetalk {request.object} seal / laws: {request.laws}",
    want' "tried" (.and (.ge (.fact .laws) (.int 2)) (.le (.fact .refusedBy) (.int 0)))
      [.text "delvetalk ", .hole (.fact .object), .text " seal / laws: ", .hole (.fact .laws)] "a law and a second hand's try")]

/-- Clauses that refuse. -/
def clausesRefused : List String := [
  "rule r: new.a == 1", "want w: new.a == 1", "rule r: new.a == 1 then", "rule r: new.a == 1 then delvetalk",
  "rule r: new.a == 1 then ring the bell", "rule r: then delvetalk x ring",
  "rule r: new.a == 1 then delvetalk {object} ring", "rule r: new.a == 1 then delvetalk {request.target} ring",
  "rule r: new.a == 1 then delvetalk {new.a.b} ring", "rule r: new.a == 1 then delvetalk {1} ring",
  "rule r: new.a == 1 then delvetalk {\"x\"} ring", "rule r: new.a == 1 then delvetalk {new.a ring",
  "rule r: new.a == 1 then delvetalk } ring", "rule r: new.a == 1 then delvetalk {new.a} {}",
  "rule r: new.a == 1 then delvetalk {{new.a}} ring",
  "want w: old.a == 1 asks delvetalk x y", "want w: request.subject == \"a\" asks delvetalk x y",
  "want w: insertOnly(lines) asks delvetalk x y", "want w: count(old.lines) <= 1 asks delvetalk x y",
  "want w: under \"kind/bell\" asks delvetalk x y", "want w: new.a == 1 asks delvetalk {request.subject} y",
  "want w: \"o\" in old.a.b asks delvetalk x y", "want w: changed(new.a.b) by request.subject asks delvetalk x y",
  "law l: new.a == 1 then delvetalk x ring", "want w: new.a == 1 then delvetalk x y",
  "rules r: new.a == 1", "law", "law: new.a == 1", "law 1x: new.a == 1", "law l \"unterminated: new.a == 1",
  "law l \"bad \\q\": new.a == 1", "law l new.a == 1", "law l \"r\" new.a == 1", "law l:", "law l \"r\":"]

/-- Clauses whose rendering is their own line. -/
def clausesCanonical : List String := [
  "law owner \"the owner amends\": (request.kind == 0) or (request.subject == new.owner)",
  "law plain: new.a <= 1",
  "rule rings \"rings at its seventh rain\": (count(new.lines) >= 7) and (count(old.lines) <= 6) then delvetalk {request.object} ring",
  "want second \"wants rain from a \\\"second\\\" hand\": count(new.lines) <= 1 asks delvetalk {request.object} rain / text: <words>",
  "rule daily: new.ticks % 24 == 0 then delvetalk weather rain / count: {count(new.ticks) + 1} / at: {\"garden\".tended}"]

theorem parse_clauses : clauses.all (fun (line, c) => (parseClause line).toOption == some c) = true := by native_decide

theorem parse_clauses_refuse : clausesRefused.all (fun line => (parseClause line).toBool == false) = true := by
  native_decide

theorem clause_render_reads_back :
    clauses.all (fun (_, c) => (parseClause c.render).toOption == some c) = true ∧
    clausesCanonical.all (fun line => (parseClause line).toOption.map Clause.render == some line) = true := by
  native_decide

/-- One text holds all three modalities, each clause keeping its own; `under` is an atom of every
modality's condition, and names are unique across the text. -/
def town : String :=
  "law kind \"the kind's law holds\": under \"kind/bell\"\n\n" ++
  "  rule rings \"rings at its seventh rain\": count(new.lines) >= 7 and count(old.lines) <= 6 then delvetalk {request.object} ring\n" ++
  "want second \"wants rain from a second hand\": count(new.lines) <= 1 asks delvetalk {request.object} rain / text: <words>\n" ++
  "rule lawful: under \"kind/bell\" and request.verb == \"water\" then delvetalk me note / text: watered {request.object}\n" ++
  "want kept: \"kind/bell\" wants second asks delvetalk kind/bell tend\n" ++
  "law owner: request.kind == rule implies request.subject == new.maker"

theorem text_holds_three_modalities :
    ((parseText town).toOption.map fun cs => cs.map fun c => (c.modality.keyword, c.name)) =
      some [("law", "kind"), ("rule", "rings"), ("want", "second"), ("rule", "lawful"), ("want", "kept"), ("law", "owner")] ∧
    ((parseText town).toOption.map fun cs => (lawsOf cs).map (·.1)) = some ["kind", "owner"] ∧
    ((parseText town).toOption.map fun cs => cs.map Clause.reads) =
      some [["kind/bell"], [], [], ["kind/bell"], ["kind/bell"], []] ∧
    (parseText "law a: new.x == 1\nrule a: new.x == 2 then delvetalk x ring").toBool = false ∧
    (parseText "law a: new.x == 1\nwant b: old.x == 1 asks delvetalk x ring").toBool = false := by
  native_decide

/-- The refusal a condition meets, if any. -/
def refusalOf (law : String) : Option String :=
  match parse law with
  | .error message => some message
  | .ok _ => none

/-- The refusal a clause meets, if any. -/
def clauseRefusalOf (line : String) : Option String :=
  match parseClause line with
  | .error message => some message
  | .ok _ => none

/-- The refusal a text meets, if any. -/
def textRefusalOf (text : String) : Option String :=
  match parseText text with
  | .error message => some message
  | .ok _ => none

theorem refusals_name_what_and_why :
    refusalOf "request.kind == proposal" = some (refusal "`request.kind == proposal`" kindRule) ∧
    refusalOf "new.a.b == 1" = some (refusal "`new.a.…`" pathRule) ∧
    refusalOf "\"g\".a.b == 1" = some (refusal "`\"g\".a.…`" pathRule) ∧
    refusalOf "request.clock == \"noon\"" = some (refusal "`request.clock == \"noon\"`" textRule) ∧
    refusalOf "request.height in new.members" = some (refusal "`request.height in new.members`" memberRule) ∧
    refusalOf "request.subject in \"circle porch\".members.principal" = some (refusal "\"circle porch\"" objectRule) ∧
    refusalOf "under kind" = some (refusal "`kind`" underRule) ∧
    refusalOf "under \"kind bell\"" = some (refusal "\"kind bell\"" objectRule) ∧
    refusalOf "\"g\" wants 3" = some (refusal "`3`" wantsRule) ∧
    refusalOf "insertOnly(a.b)" = some (refusal "`insertOnly`" ruleRule) ∧
    refusalOf "1 + 2 <= 3" = some (refusal "`1 + 2 <= 3`" compareRule) ∧
    refusalOf "new.a % 0 == 0" = some (refusal "`% 0`" modRule) ∧
    refusalOf "new.a % new.b == 0" = some (refusal "`% new`" modRule) ∧
    refusalOf "new.a > 1" = some (refusal "`>`" tokenRule) ∧
    refusalOf "new.a == 1 then delvetalk x ring" = some (refusal "`then`" joinRule) ∧
    clauseRefusalOf "rule r: new.a == 1" = some (refusal "the end of the rule" ruleLineRule) ∧
    clauseRefusalOf "want w: new.a == 1" = some (refusal "the end of the want" wantLineRule) ∧
    clauseRefusalOf "want w: new.a == 1 then delvetalk x y" = some (refusal "`then`" joinRule) ∧
    clauseRefusalOf "rule r: new.a == 1 then delvetalk {object} ring" = some (refusal "`{object}`" holeRule) ∧
    clauseRefusalOf "rule r: new.a == 1 then delvetalk {request.target} ring" =
      some (refusal "`{request.target}`" holeRule) ∧
    clauseRefusalOf "rule r: new.a == 1 then ring the bell" = some (refusal "`ring`" spellRule) ∧
    clauseRefusalOf "want w: old.a == 1 asks delvetalk x y" = some (refusal "`old.a` in a want" wantRule) ∧
    clauseRefusalOf "want w: new.a == 1 asks delvetalk {request.subject} y" =
      some (refusal "`request.subject` in a want" wantRule) ∧
    clauseRefusalOf "want w: insertOnly(lines) asks delvetalk x y" = some (refusal "`insertOnly(lines)` in a want" wantRule) ∧
    clauseRefusalOf "rules r: new.a == 1" = some (refusal "`rules`" clauseRule) ∧
    clauseRefusalOf "law 1x: new.a == 1" = some (refusal "`1x:`" nameRule) ∧
    clauseRefusalOf "law l \"bad \\q\": new.a == 1" = some (refusal "`\"bad \\q\"`" readingRule) ∧
    clauseRefusalOf "law l new.a == 1" = some (refusal "`new.a`" clauseRule) ∧
    (parseText "law a: new.x == 1\nrule a: new.x == 2 then delvetalk x ring").toOption.isNone ∧
    textRefusalOf "law a: new.x == 1\nlaw a: new.x == 2" =
      some (refusal "`a` twice" "a clause's name is unique across its text") := by
  native_decide

theorem names_walk :
    (LawExpr.le (.count .new "members" .all) (.sum (.count .new "votes" (.eq "vote" (.field .new "choice"))) (.int 0))).fields =
      ["members", "votes", "choice"] ∧
    (LawExpr.changed "subs" "who" (.fact .subject)).names = [.field "subs", .column "who"] ∧
    (LawExpr.changed "subs" "a/b" (.fact .subject)).fieldsPlain = false ∧
    (LawExpr.le (.count .new "lines" (.eq "a/b" (.text "x"))) (.int 1)).fieldsPlain = false ∧
    (LawExpr.member (.fact .subject) (.column .new "greeted" "principal")).fieldsPlain = true ∧
    (LawExpr.or (.member (.fact .subject) (.column (.cited "circle/porch") "members" "principal"))
      (.and (.member (.field .new "owner") (.column (.cited "bond/a") "signatures" "principal"))
        (.member (.fact .caller) (.column (.cited "circle/porch") "members" "principal")))).reads = ["circle/porch", "bond/a"] ∧
    (LawExpr.member (.field .new "owner") (.column (.cited "bond/a") "signatures" "principal")).fields = ["owner"] ∧
    (LawExpr.member (.fact .subject) (.column (.cited "bond/a") "signatures" "principal")).fields = [] ∧
    (LawExpr.member (.fact .subject) (.column (.cited "bond a") "signatures" "principal")).fieldsPlain = false ∧
    (LawExpr.and (.under "kind/bell") (.or (.member (.fact .subject) (.column (.cited "circle/porch") "members" "principal"))
      (.under "kind/bell"))).reads = ["kind/bell", "circle/porch"] ∧
    (LawExpr.and (.under "kind/bell") (.eq (.fact .subject) (.field .new "maker"))).fields = ["maker"] ∧
    -- Another object's field, count and want are roots; never the written object's fields.
    (LawExpr.and (.le (.fact .clock) (.sum (.field (.cited "garden") "tended") (.field .old "gap")))
      (.and (.ge (.count (.cited "porch") "here" .all) (.int 3)) (.not (.wants "garden" "rain")))).reads = ["garden", "porch"] ∧
    (LawExpr.and (.le (.fact .clock) (.sum (.field (.cited "garden") "tended") (.field .old "gap")))
      (.ge (.count (.cited "porch") "here" .all) (.int 3))).fields = ["gap"] ∧
    (LawExpr.wants "garden" "rain one").fieldsPlain = false ∧
    (LawExpr.eq (.mod (.field .new "ticks") 24) (.int 0)).fields = ["ticks"] ∧
    -- A clause's spell holes are read as its condition is.
    (rule' "r" (.eq (.fact .verb) (.text "water")) [.text "delvetalk ", .hole (.field (.cited "garden") "tended"),
      .text " x ", .hole (.field .new "maker")]).reads = ["garden"] ∧
    (rule' "r" (.eq (.fact .verb) (.text "water")) [.text "delvetalk ", .hole (.field (.cited "garden") "tended"),
      .text " x ", .hole (.field .new "maker")]).fields = ["maker"] := by
  native_decide

#guard (parse "changed(new.a)").toOption == some (.changedTerm (.field .new "a"))
#guard (parse "changed(count(new.lines where verb == \"rain\"))").toOption ==
  some (.changedTerm (.count .new "lines" (.eq "verb" (.text "rain"))))
#guard (parse "changed(new.a + count(new.lines) % 2)").toOption ==
  some (.changedTerm (.sum (.field .new "a") (.mod (.count .new "lines" .all) 2)))
#guard (parse "changed(new.lines.author) by request.subject").toOption ==
  some (.changed "lines" "author" (.fact .subject))
#guard ["changed(new.a)", "changed(count(new.lines where verb == \"rain\"))",
    "changed(new.a + count(new.lines) % 2)", "changed(new.lines.author) by request.subject"].all
  (fun text => (parse text).toOption.map LawExpr.render == some text)
#guard ["changed(new.a", "changed()", "changed(new.a == 1)", "changed(request.clock)",
    "changed(new.a + request.height)", "changed(count(new.lines where author == request.subject))",
    "changed(new.lines.author)", "changed(new.a) by request.subject"].all
  (fun text => (parse text).toBool == false)
#guard (clauseRefusalOf "want w: changed(new.a) asks delvetalk x y") ==
  some (refusal "`changed(new.a)` in a want" wantRule)
#guard (clauseRefusalOf "want w: not changed(new.a) asks delvetalk x y") ==
  some (refusal "`changed(new.a)` in a want" wantRule)
#guard (parseClause "rule r: changed(count(new.lines)) then delvetalk x y").toOption.map Clause.render ==
  some "rule r: changed(count(new.lines)) then delvetalk x y"
#guard (LawExpr.changedTerm (.sum (.field .new "a") (.count .new "lines" (.eq "verb" (.field (.cited "garden") "verb"))))).fields ==
  ["a", "lines"]
#guard (LawExpr.changedTerm (.count .new "lines" (.eq "verb" (.field (.cited "garden") "verb")))).reads == ["garden"]
#guard (LawExpr.changedTerm (.field .new "a/b")).fieldsPlain == false

end Delvetalk.Compiler.ObjectiveBendLaw

#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.parse_accepts
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.parse_refuses
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.render_reads_back
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.parse_clauses
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.parse_clauses_refuse
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.clause_render_reads_back
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.text_holds_three_modalities
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.refusals_name_what_and_why
#assert_compiled Delvetalk.Compiler.ObjectiveBendLaw.names_walk
#assert_axioms Delvetalk.Compiler.ObjectiveBendLaw.admit_ok
#assert_axioms Delvetalk.Compiler.ObjectiveBendLaw.parseClauseSource_reads_now
#assert_axioms Delvetalk.Compiler.ObjectiveBendLaw.parsed_want_reads_as_it_stands
