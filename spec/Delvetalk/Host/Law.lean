/- Meaning of the enforced law fragment (`Compiler/ObjectiveBendLaw.lean`) over
   old and new state `Data` plus request facts: the one judge of every clause.
   A principal is text: `subject` and `caller` read as a number when the principal
   is a decimal numeral and as text otherwise, so `request.subject ==
   request.caller` holds for any principal while order and constants need
   numerals. Absent or mistyped readings fail closed. -/
import Delvetalk.Host.Store
import Delvetalk.Host.Spell
import Delvetalk.Canonical
import Compiler.ObjectiveBendDataWire

namespace Delvetalk.Host

open Delvetalk.Compiler.ObjectiveBendLaw (Clause) in
/-- A law as text, one `law NAME: EXPR` a line (the one renderer's form, without readings). -/
def renderLaw (law : Law) : String :=
  "\n".intercalate (law.map fun (name, condition) => ({ modality := .law, name, condition } : Clause).render)

/-- A thing's text, every modality: one clause a line (`law`, `rule`, `want`), as the kernel parses
    it, within the text's byte and clause bounds. -/
def parseClausesCold (text : String) : Except String (List Delvetalk.Compiler.ObjectiveBendLaw.Clause) := do
  if text.utf8ByteSize > Limits.maxLawBytes then throw "law text exceeds its byte capacity"
  let clauses ← Delvetalk.Compiler.ObjectiveBendLaw.parseText text
  if clauses.length > Limits.maxLawClauses then throw "law has too many clauses"
  return clauses

/-- This process's parsed texts, by the text: a kind's text is read at every judgement of every thing
    under it (`under`, `followed`, `carried`, a cited want), and parsing is a function of the text alone.
    A constant, not an `initialize`: this module's own `#guard`s evaluate `parseClauses`. -/
@[noinline] unsafe def clauseMemo : IO.Ref (Std.HashMap String (Except String (List Delvetalk.Compiler.ObjectiveBendLaw.Clause))) :=
  unsafeBaseIO (IO.mkRef {})

unsafe def parseClausesImpl (text : String) : Except String (List Delvetalk.Compiler.ObjectiveBendLaw.Clause) :=
  unsafeBaseIO do
    if let some r := (← clauseMemo.get)[text]? then return r
    let r := parseClausesCold text
    clauseMemo.modify fun m => boundedInsert m Limits.maxBuilds text r
    return r

/-- `parseClausesCold`, once per process for a text. -/
@[implemented_by parseClausesImpl]
def parseClauses (text : String) : Except String (List Delvetalk.Compiler.ObjectiveBendLaw.Clause) :=
  parseClausesCold text

/-- A text's laws and their readings, by clause name: its `law` clauses (its rules and wants are
    `parseClauses`'). -/
def parseLawTextReadings (text : String) : Except String (Law × List (String × String)) := do
  let laws := (← parseClauses text).filter (·.modality == .law)
  return (laws.map fun c => (c.name, c.condition), laws.filterMap fun c => if c.reading.isEmpty then none else some (c.name, c.reading))

/-- A text's laws: its `law` clauses, by name. -/
def parseLawText (text : String) : Except String Law := do
  return (← parseLawTextReadings text).1

end Delvetalk.Host

namespace Delvetalk.Host.Law
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
open Delvetalk.Compiler.ObjectiveBendLaw (LawExpr LawTerm LawFilter LawSide Clause Modality Spell)

/-- What a thing stands at, as a law, a rule or a want reads it (`request.laws`, `request.refusedBy`): the
    count of its law clauses, its own and those its `under` citations' texts hold (`lawClauses`), and the
    count of writes its law has refused (the journal's `lawRefused` entries naming it). -/
structure Standing where
  laws : Nat
  refusedBy : Nat
  deriving BEq

structure Facts where
  subject : String
  caller : String
  height : Nat
  turn : Nat
  /-- Pin of the package the object runs after this write. -/
  pin : String := ""
  /-- 0 write (the object's own method), 1 reprogram, 2 amend, 3 proposed, 4 rule (`kindNames`). -/
  kind : Nat := 0
  /-- The method whose run made the change; "" for an op. -/
  method : String := ""
  /-- The rows the declared retention dropped while the write's edits were applied, by field
      (`Ops.applyEdits`): `insertOnly` does not count them, and nothing else. -/
  evicted : List (String × Data) := []
  /-- The world clock the turn read, in minutes (`request.clock`, LAW §4 A). -/
  clock : Nat := 0
  /-- The written object's id (`request.object`, LAW §4 H). -/
  object : String := ""
  /-- The state of every object the law cites (`"O".F`, `under "O"`, `"O" wants N`), transitively
      through `under` and `wants`, as the write leaves them (`Ops.citing`). -/
  reads : List (String × Data) := []
  /-- The verb the act named (`request.verb`): a declared method's name, or a grown verb's under
      `act` (docs/FOUNDATION.md §10); "" for an op. -/
  verb : String := ""
  /-- The want clauses of every object cited by `"O" wants N`: its placed wants, then those its
      `under` citations carry (`followed`), by object. -/
  wants : List (String × List Clause) := []
  /-- What the written object and each object it cites stand at, by object (`Standing`): read for
      `object`, so a cited want (`asItStands`) reads its own thing's. -/
  standing : List (String × Standing) := []

/-- The kinds of change a law tells apart by `request.kind`, by name. `proposed` is a state write
    that does not come from the object's own method: a `world-propose`, or the state a reprogram's
    migration makes. So a law admitting `request.kind == 0` admits only the object's own method's
    writes, and one that wants proposals says `request.kind == 3` (or `proposed`). `rule` is the
    placing of a rule or a want on the object, judged by its law (docs/OVERHAUL.md §2 conflict 8).
    The grammar's table, so a name reads one way everywhere. -/
def kindNames : List (String × Nat) := Delvetalk.Compiler.ObjectiveBendLaw.kinds

def proposedKind : Nat := 3

/-- A kind whose change is edits of state: the object's own write, or a proposed one. -/
def editKind (k : Nat) : Bool := k == 0 || k == proposedKind

inductive Reading where
  | num (n : Int)
  | text (s : String)
  deriving BEq

def scalarOf : Data → Option Int
  | .natural n => some (Int.ofNat n)
  | .boolean b => some (if b then 1 else 0)
  | _ => none

/-- The field called `name` of a record, whatever its type. -/
def rawField (name : String) : Data → Option Data
  | .record fields => fields.lookup name
  | _ => none

/-- The natural or boolean field called `name`; any other field has no numeric reading. -/
def fieldOf (name : String) (d : Data) : Option Int := (rawField name d).bind scalarOf

/-- Canonical form of a value: the compressed wire JSON. -/
def canon (d : Data) : String := (Delvetalk.Compiler.ObjectiveBendDataWire.dataJson d).compress

/-- The items of a `List<T>` on the wire (`nil {} | cons {head, tail}`), as canonical text. -/
partial def listItems (acc : List String) : Data → Option (List String)
  | .variant "nil" _ => some acc.reverse
  | .variant "cons" (.record f) => do
    let head ← f.lookup "head"
    let tail ← f.lookup "tail"
    listItems (canon head :: acc) tail
  | _ => none

/-- The empty value of a field, whatever its type: 0, false, "", the empty list, or a record of
    empty values. `writeOnce(F)` admits exactly one change of F, away from it. -/
partial def emptyValue : Data → Bool
  | .natural n => n == 0
  | .boolean b => !b
  | .label s => s.isEmpty
  | .variant "nil" _ => true
  | .record fields => fields.all fun (_, v) => emptyValue v
  | _ => false

/-- The rows of a relation field (`rows {items: List<T>}`, RELATIONAL §2), or of a plain list. -/
partial def rowsOf : Data → Option (List Data)
  | .variant "rows" (.record f) => (f.lookup "items").bind rowsOf
  | .variant "nil" _ => some []
  | .variant "cons" (.record f) => do
    let head ← f.lookup "head"
    return head :: (← rowsOf (← f.lookup "tail"))
  | _ => none

/-- `old` is a prefix of `new`. -/
def isPrefix : List String → List String → Bool
  | [], _ => true
  | _ :: _, [] => false
  | a :: as, b :: bs => a == b && isPrefix as bs

def principalReading (principal : String) : Reading :=
  if !principal.isEmpty && principal.all Char.isDigit then
    match principal.toNat? with
    | some n => .num n
    | none => .text principal
  else .text principal

/-- The value of the row named `name` in a list of `{name, value}` rows (a made thing's `fields`). -/
partial def namedValue (name : String) : Data → Option Data
  | .variant "cons" (.record f) => match f.lookup "head", f.lookup "tail" with
    | some (.record row), some tail => match row.lookup "name" with
      | some (.label n) => if n == name then row.lookup "value" else namedValue name tail
      | _ => namedValue name tail
    | _, _ => none
  | _ => none

/-- A top-level field of a state as a law reads it: text, or a scalar as a number. A name the state
    has no field for is a form field of a made thing, when it has `fields` (the values its kind's make
    took: `ringAt: natural 1..768`): its text, digits read as a number (docs/AUTHORING.md §3 (a)). -/
def fieldReading (name : String) (state : Data) : Option Reading :=
  match rawField name state with
  | some (.label s) => some (.text s)
  | some d => (scalarOf d).map .num
  | none => ((rawField "fields" state).bind (namedValue name)).bind fun
    | .label s => some (if !s.isEmpty && s.all Char.isDigit then .num s.toNat! else .text s)
    | _ => none

/-- `old.F` at creation: the empty value of the field's kind as the new state has it ("" for text, 0
    for a scalar), as `writeOnce` reads an empty field. -/
def emptyReading (name : String) (new : Data) : Option Reading :=
  (fieldReading name new).map fun
    | .text _ => .text ""
    | .num _ => .num 0

/-- The state a side reads: the new one, the old one (none at creation), or a cited object's as the
    write's root recorded it (none when absent or unviewable). -/
def sideState (facts : Facts) (old : Option Data) (new : Data) : LawSide → Option Data
  | .new => some new
  | .old => old
  | .cited object => facts.reads.lookup object

/-- The rows a count or a membership reads in `SIDE.F`: none before a creation is no rows; an absent
    cited object has none to read. -/
def rowsAt (facts : Facts) (old : Option Data) (new : Data) (side : LawSide) (field : String) : Option (List Data) :=
  match side, old with
  | .old, none => some []
  | _, _ => (sideState facts old new side).bind fun state => (rawField field state).bind rowsOf

def number (reading : Option Reading) : Option Int :=
  match reading with
  | some (.num n) => some n
  | _ => none

mutual
partial def read (facts : Facts) (old : Option Data) (new : Data) : LawTerm → Option Reading
  | .field .new name => fieldReading name new
  | .field .old name => match old with
    | some o => fieldReading name o
    | none => emptyReading name new
  | .field (.cited object) name => (facts.reads.lookup object).bind (fieldReading name)
  | .fact .subject => some (principalReading facts.subject)
  | .fact .caller => some (principalReading facts.caller)
  | .fact .height => some (.num facts.height)
  | .fact .turn => some (.num facts.turn)
  | .fact .pin => some (.text facts.pin)
  | .fact .kind => some (.num facts.kind)
  | .fact .method => some (.text facts.method)
  | .fact .verb => some (.text facts.verb)
  | .fact .clock => some (.num facts.clock)
  | .fact .object => some (.text facts.object)
  | .fact .laws => (facts.standing.lookup facts.object).map fun s => .num s.laws
  | .fact .refusedBy => (facts.standing.lookup facts.object).map fun s => .num s.refusedBy
  | .int value => some (.num value)
  | .text text => some (.text text)
  | .sum left right => match number (read facts old new left), number (read facts old new right) with
    | some x, some y => some (.num (x + y))
    | _, _ => none
  -- The remainder by a positive modulus, never negative (docs/OVERHAUL.md §2 conflict 5).
  | .mod term modulus => match number (read facts old new term) with
    | some x => if modulus == 0 then none else some (.num (x % Int.ofNat modulus))
    | none => none
  -- The rows whose column holds the value, by canonical bytes (docs/LAW.md §4 C).
  | .count side field filter => do
    let rows ← rowsAt facts old new side field
    return .num (← filterRows facts old new rows filter).length

partial def filterRows (facts : Facts) (old : Option Data) (new : Data) (rows : List Data) : LawFilter → Option (List Data)
  | .all => some rows
  | .eq col value => do
    let want := canon (← memberData facts old new value)
    return rows.filter fun (r : Data) => (rawField col r).map canon == some want
  | .and left right => do
    let selected ← filterRows facts old new rows left
    filterRows facts old new selected right

/-- The exact text a term reads as: a principal as given, a text field, a constant. -/
partial def textOf (facts : Facts) (old : Option Data) (new : Data) : LawTerm → Option String
  | .fact .subject => some facts.subject
  | .fact .caller => some facts.caller
  | .fact .pin => some facts.pin
  | .fact .method => some facts.method
  | .fact .verb => some facts.verb
  | .fact .object => some facts.object
  | .text text => some text
  | term => match read facts old new term with
    | some (.text s) => some s
    | _ => none

/-- The value a term stands for in a membership, a filter or `changed ... by`, compared by canonical
    bytes: a field as it is, a numeric reading as a natural, text as a label. -/
partial def memberData (facts : Facts) (old : Option Data) (new : Data) : LawTerm → Option Data
  | .field side name => (sideState facts old new side).bind (rawField name)
  | term => match textOf facts old new term with
    | some s => some (.label s)
    | none => match read facts old new term with
      | some (.num n) => if n < 0 then none else some (.natural n.toNat)
      | some (.text s) => some (.label s)
      | none => none
end

/-- Text form for comparing a numeral principal with a numeric reading. -/
def Reading.render : Reading → String
  | .num n => toString n
  | .text s => s

/-- Equality of term readings, including a numeric reading and its decimal text. -/
def Reading.same (left right : Reading) : Bool := left == right || left.render == right.render

/-- The rows of `F` in `rows`'s column `C`, as `.column` reads them. -/
def columnHas (rows : List Data) (col : String) (w : Data) : Bool :=
  let cw := canon w
  rows.any fun r => (rawField col r).map canon == some cw

/-- Rows as the set of their canonical bytes: membership in one pass, never a row against every row. -/
def canonSet (rows : List Data) : Std.HashSet String := rows.foldl (fun s r => s.insert (canon r)) {}

/-- The rows of `field` the declared retention dropped while the write was applied (`Facts.evicted`). -/
def evictedIn (facts : Facts) (field : String) : Std.HashSet String :=
  canonSet (facts.evicted.filterMap fun (f, x) => if f == field then some x else none)

/-- The rows a write changed in relation (or list) `field`: those of `old` gone from `new` by canonical
    bytes, less the ones the declared retention dropped, and those of `new` not in `old`. -/
def changedRows (facts : Facts) (old : Option Data) (new : Data) (field : String) : Option (List Data) := do
  let after ← (rawField field new).bind rowsOf
  let before ← match old with
    | none => some []
    | some o => (rawField field o).bind rowsOf
  let now := canonSet after
  let was := canonSet before
  let evicted := evictedIn facts field
  let gone := before.filter fun r => let c := canon r; !now.contains c && !evicted.contains c
  return gone ++ after.filter fun r => !was.contains (canon r)

def isWant (c : Clause) : Bool := match c.modality with | .want _ => true | _ => false
def isRule (c : Clause) : Bool := match c.modality with | .rule _ => true | _ => false

/-- The want `name` of a cited object (`Facts.wants`). -/
def wantNamed (facts : Facts) (object name : String) : Option Clause :=
  ((facts.wants.lookup object).getD []).find? fun c => isWant c && c.name == name

/-- The facts a want of `object` is judged by: the clock, the object, and what the write cites; no
    principal, kind, method or verb (a want is judged at a read, by nobody). -/
def asItStands (facts : Facts) (object : String) : Facts :=
  { facts with subject := "", caller := "", kind := 0, method := "", verb := "", evicted := [], object }

/-- What a condition read as it stands, by a reader (`holds`, a scene's guard), cannot read: `old`, a rule
    over old and new, `changed`, `under`; rendered, or none. Unlike a want it reads every request fact. -/
def standingRefusal (e : LawExpr) : Option String :=
  let oldTerm : LawTerm → Bool := fun t => (t.atRead.map (·.startsWith "old.") |>.getD false) || (t.atRead.map (·.startsWith "count(old.") |>.getD false)
  let rec go : LawExpr → Option String
    | e@(.eq l r) | e@(.ne l r) | e@(.lt l r) | e@(.le l r) | e@(.gt l r) | e@(.ge l r) =>
      if oldTerm l || oldTerm r then some e.render else none
    | .member t p => if oldTerm t || p.atRead.isSome then some (LawExpr.member t p).render else none
    | e@(.rule _ _) | e@(.changed _ _ _) | e@(.changedTerm _) | e@(.under _) => some e.render
    | .wants _ _ => none
    | .not b => go b
    | .and l r | .or l r | .implies l r => go l <|> go r
  go e

/-- An amendment of a thing by its own owner (its state's text `owner`): what no cited law refuses, so a
    kind's owner, amending the text every instance follows, cannot lock an instance's owner out of their
    own thing; they can always amend it out from under the kind (docs/review/astra-2026-10-12 world 2). -/
def ownerAmends (facts : Facts) (new : Data) : Bool :=
  facts.kind == 2 && match rawField "owner" new with
    | some (.label owner) => !owner.isEmpty && owner == facts.subject
    | _ => false

/-- The meaning of a clause. `under "O"` reads the `law` text of the cited object's state and judges
    this write by each of its clauses at `depth - 1`; at depth 0 it is false, so a cycle of citations
    ends (`Limits.lawDepth`). It holds of the owner's own amendment whatever O says (`ownerAmends`). -/
partial def denote (facts : Facts) (old : Option Data) (new : Data) (e : LawExpr) (depth : Nat := Limits.lawDepth) : Bool :=
  match e with
  | .eq left right => match left, right with
    | other, .text text | .text text, other => textOf facts old new other == some text
    | other, .int value | .int value, other => number (read facts old new other) == some value
    | _, _ => match read facts old new left, read facts old new right with
      | some x, some y => x.same y
      | _, _ => false
  -- Both sides read and differ: false when either reads nothing, as every comparison is.
  | .ne left right => match left, right with
    | other, .text text | .text text, other => match textOf facts old new other with
      | some t => t != text
      | none => false
    | other, .int value | .int value, other => match number (read facts old new other) with
      | some x => x != value
      | none => false
    | _, _ => match read facts old new left, read facts old new right with
      | some x, some y => !x.same y
      | _, _ => false
  | .lt left right => match number (read facts old new left), number (read facts old new right) with
    | some x, some y => decide (x < y)
    | _, _ => false
  | .le left right => match number (read facts old new left), number (read facts old new right) with
    | some x, some y => decide (x ≤ y)
    | _, _ => false
  | .gt left right => match number (read facts old new left), number (read facts old new right) with
    | some x, some y => decide (y < x)
    | _, _ => false
  | .ge left right => match number (read facts old new left), number (read facts old new right) with
    | some x, some y => decide (y ≤ x)
    | _, _ => false
  | .member term (.ints values) => match number (read facts old new term) with
    | some x => values.contains x
    | none => false
  -- Membership in a list or a relation's column of either side, or of a cited object as it stood
  -- at the root the write records (§4 D); none before a creation, absent or unviewable holds none.
  | .member term (.list side field) => match memberData facts old new term,
      ((sideState facts old new side).bind (rawField field)).bind (listItems []) with
    | some w, some items => items.contains (canon w)
    | _, _ => false
  | .member term (.column side field col) => match memberData facts old new term, rowsAt facts old new side field with
    | some w, some rows => columnHas rows col w
    | _, _ => false
  | .rule .monotone field => match old.bind (fieldOf field), fieldOf field new with
    | some before, some after => decide (before ≤ after)
    | _, _ => false
  | .rule .writeOnce field => match old with
    | none => true
    | some before => match rawField field before, rawField field new with
      | some a, some b => emptyValue a || canon a == canon b
      | _, _ => false
  | .rule .appendOnly field => match old with
    | none => (listItems [] ((rawField field new).getD (.boolean false))).isSome
    | some before => match (rawField field before).bind (listItems []), (rawField field new).bind (listItems []) with
      | some a, some b => isPrefix a b
      | _, _ => false
  | .rule .unchanged field => match old with
    | none => true
    | some before => match rawField field before, rawField field new with
      | some a, some b => canon a == canon b
      | _, _ => false
  -- Relations (RELATIONAL §5). Rows are compared whole by canonical bytes: a relation holds no
  -- key twice, so "every old row is in new" is "new ⊇ old by key, every old row unchanged".
  -- A row the declared retention dropped while this write was applied (`Facts.evicted`, as the
  -- edits ran: codex host 8) was not retracted by the write, so it does not count.
  | .rule .insertOnly field => match (rawField field new).bind rowsOf with
    | none => false
    | some after => match old with
      | none => true
      | some before => match (rawField field before).bind rowsOf with
        | some rows =>
          let now := canonSet after
          let evicted := evictedIn facts field
          rows.all fun r => let c := canon r; now.contains c || evicted.contains c
        | none => false
  -- Every row the write changed carries `who` in its column (docs/LAW.md §4 B).
  | .changed field col who => match changedRows facts old new field, memberData facts old new who with
    | some rows, some w => rows.all fun r => (rawField col r).map canon == some (canon w)
    | _, _ => false
  | .changedTerm term => match old with
    | none => false
    | some before => match read facts old before term, read facts old new term with
      | some a, some b => !(a.same b)
      | _, _ => false
  -- The cited object's law text judges this write too (§4 F).
  | .under object => depth > 0 && (ownerAmends facts new || match (facts.reads.lookup object).bind (rawField "law") with
    | some (.label text) => match parseLawText text with
      | .ok law => law.all fun (_, clause) => clause.fieldsPlain && denote facts old new clause (depth - 1)
      | .error _ => false
    | _ => false)
  -- Another thing's want holds of it as it stands: its condition judged on the cited state, with
  -- no state before and only the clock and the object to read (a want reads nothing else).
  | .wants object name => depth > 0 && match facts.reads.lookup object, wantNamed facts object name with
    | some state, some want => want.fieldsPlain && denote (asItStands facts object) none state want.condition (depth - 1)
    | _, _ => false
  | .not body => !denote facts old new body depth
  | .and left right => denote facts old new left depth && denote facts old new right depth
  | .or left right => denote facts old new left depth || denote facts old new right depth
  | .implies premise conclusion => !denote facts old new premise depth || denote facts old new conclusion depth

mutual
/-- What reading `t` walks: one for the term, and a row for each row a count reads. -/
partial def termWork (facts : Facts) (old : Option Data) (new : Data) : LawTerm → Nat
  | .count side field filter => 1 + filterWork facts old new (((rowsAt facts old new side field).map (·.length)).getD 0) filter
  | .sum l r => 1 + termWork facts old new l + termWork facts old new r
  | .mod t _ => 1 + termWork facts old new t
  | _ => 1
partial def filterWork (facts : Facts) (old : Option Data) (new : Data) (rows : Nat) : LawFilter → Nat
  | .all => rows
  | .eq _ value => rows + termWork facts old new value
  | .and left right => filterWork facts old new rows left + filterWork facts old new rows right
end

/-- What judging `e` reads, as `denote` reads it: a step per atom and a row (or list item) per row it walks, on
    each side; through `under` and `wants`, what the cited clauses read. A judgment's clauses together are
    bounded by `Bounds.lawTicks` (`Facts` the host meters with; codex host 13), as a Bend law's ticks are. -/
partial def work (facts : Facts) (old : Option Data) (new : Data) (e : LawExpr) (depth : Nat := Limits.lawDepth) : Nat :=
  let rows := fun (side : LawSide) (field : String) => ((rowsAt facts old new side field).map (·.length)).getD 0
  let both := fun (field : String) => rows .old field + rows .new field
  match e with
  | .eq l r | .ne l r | .lt l r | .le l r | .gt l r | .ge l r => 1 + termWork facts old new l + termWork facts old new r
  | .member t (.list side field) => 1 + termWork facts old new t +
      ((((sideState facts old new side).bind (rawField field)).bind (listItems [])).map (·.length)).getD 0
  | .member t (.column side field _) => 1 + termWork facts old new t + rows side field
  | .member t _ => 1 + termWork facts old new t
  | .rule _ field => 1 + both field
  | .changed field _ who => 1 + both field + termWork facts old new who
  | .changedTerm term => 1 + termWork facts old (old.getD new) term + termWork facts old new term
  | .under object => if depth == 0 then 1 else 1 + match (facts.reads.lookup object).bind (rawField "law") with
    | some (.label text) => match parseLawText text with
      | .ok law => law.foldl (fun n (_, c) => n + work facts old new c (depth - 1)) 0
      | .error _ => 0
    | _ => 0
  | .wants object name => if depth == 0 then 1 else 1 + match facts.reads.lookup object, wantNamed facts object name with
    | some state, some want => work (asItStands facts object) none state want.condition (depth - 1)
    | _, _ => 0
  | .not b => 1 + work facts old new b depth
  | .and l r | .or l r | .implies l r => 1 + work facts old new l depth + work facts old new r depth

/-- A clause that reads a non-plain field name refuses every write. -/
def admits (facts : Facts) (old : Option Data) (new : Data) (clause : LawExpr) : Bool :=
  clause.fieldsPlain && denote facts old new clause

/-- Through a clause that is `under "O"`, the first of O's clauses that refuses (and through its own
    `under`, innermost first), with its reading in O's law text; else the clause itself, no reading. -/
partial def innermost (facts : Facts) (old : Option Data) (new : Data) (name : String) (reading : Option String)
    (clause : LawExpr) (depth : Nat) : String × Option String :=
  match clause with
  | .under object => match (facts.reads.lookup object).bind (rawField "law") with
    | some (.label text) => match parseLawTextReadings text with
      | .ok (law, readings) =>
        match law.find? fun (_, c) => !(c.fieldsPlain && denote facts old new c (depth - 1)) with
        | some (n, c) => innermost facts old new n (readings.lookup n) c (depth - 1)
        | none => (name, reading)
      | .error _ => (name, reading)
    | _ => (name, reading)
  | _ => (name, reading)

/-- The first law, in source order, that refuses this write, as the clause that failed: a kind's
    `under "kind/x"` names the kind's clause (`level`), with that clause's reading in the kind's law. -/
def refusal (law : Law) (facts : Facts) (old : Option Data) (new : Data) : Option (String × Option String) :=
  (law.find? fun (_, clause) => !admits facts old new clause).map fun (name, clause) =>
    innermost facts old new name none clause Limits.lawDepth

def refusedBy (law : Law) (facts : Facts) (old : Option Data) (new : Data) : Option String :=
  (refusal law facts old new).map Prod.fst

/-! Rules and wants: the same conditions, the same `denote`. A law refuses at commit; the host fires
a rule's spell when its condition holds at a write, and poses a want while it holds of the thing
as it stands (docs/OVERHAUL.md §2; KERNEL-HANDOFF §27 is the host's step). -/

/-- The rules among `clauses` whose condition holds of this write, in order. How many it casts, under
    whom and how deep is the host's (`rulesPerCommit`, the rule's owner, `ruleDepth`). -/
def fires (facts : Facts) (old : Option Data) (new : Data) (clauses : List Clause) : List Clause :=
  clauses.filter fun c => isRule c && c.fieldsPlain && denote facts old new c.condition

/-- The wants among `clauses` that hold of `object`'s `state` as it stands, at `facts.clock`. -/
def poses (facts : Facts) (object : String) (state : Data) (clauses : List Clause) : List Clause :=
  clauses.filter fun c => isWant c && c.fieldsPlain && denote (asItStands facts object) none state c.condition

/-- The terms a condition reads of the written thing's own state (`new.F`, `count(new.F…)`), in order; `rules`'
    readback shows each with its value now (Kestrel, gsb 10-11: a watch counted in the dark, with nothing to check it
    against). -/
def stateTerms : LawExpr → List LawTerm
  | .eq l r | .ne l r | .lt l r | .le l r | .gt l r | .ge l r => termsOf l ++ termsOf r
  | .member t _ => termsOf t
  | .changedTerm t => termsOf t
  | .not b => stateTerms b
  | .and l r | .or l r | .implies l r => stateTerms l ++ stateTerms r
  | _ => []
where
  termsOf : LawTerm → List LawTerm
    | t@(.count .new _ _) => [t]
    | t@(.field .new _) => [t]
    | .sum l r => termsOf l ++ termsOf r
    | .mod t _ => termsOf t
    | _ => []

/-- `now: count(new.lines) = 4, new.tended = 10`: each state term of `cond` (`stateTerms`, each once) as `state`
    reads now, a write that changed nothing; "" when it reads none. -/
def nowLine (state : Data) (cond : LawExpr) (height : Nat) : String :=
  let facts : Facts := { subject := "", caller := "", height, turn := 0 }
  let terms := (stateTerms cond).foldl (fun acc t => if acc.any (·.render == t.render) then acc else acc ++ [t]) []
  let shown := terms.filterMap fun t => (read facts (some state) state t).map fun
    | .num n => s!"{t.render} = {n}"
    | .text v => s!"{t.render} = {v.quote}"
  if shown.isEmpty then "" else "now: " ++ ", ".intercalate shown

/-- What a hole reads as spell text: text as it is, a number in decimal; none when it reads nothing. -/
def holeText (facts : Facts) (old : Option Data) (new : Data) (term : LawTerm) : Option String :=
  match textOf facts old new term with
  | some t => some t
  | none => (read facts old new term).map Reading.render

/-- What filling a spell came to: a hole read nothing, the filled text is not one spell, or the spell. -/
inductive Filled where
  | hole
  | notSpell
  | text (spell : String)
  deriving DecidableEq, Repr

/-- The placeholder prefix: lower case letters (a valid card name and identifier) that the template's
    own text, folded as `Delvetalk.Host.Spell.parse` folds actions and names, does not contain. -/
def placeholderPrefix (spell : Spell) : String :=
  let literal := String.join (spell.parts.filterMap fun | .text t => some t.toLower | .hole _ => none)
  ((List.range (literal.length + 1)).map fun n => String.join (List.replicate (n + 1) "qzx")).find?
    (fun pre => (literal.splitOn pre).length == 1) |>.getD "qzx"

/-- `s` with each placeholder `<pre><i>z` replaced by `texts[i]` in a single left-to-right pass (a
    reading is never rescanned); none when a placeholder is malformed or names no hole. -/
def substHoles (pre : String) (texts : List String) (s : String) : Option String :=
  match s.splitOn pre with
  | [] => some s
  | first :: rest => rest.foldlM (init := first) fun acc piece =>
      let chars := piece.toList
      let digits := chars.takeWhile Char.isDigit
      match chars.drop digits.length, (Delvetalk.Host.Spell.str digits).toNat? with
      | 'z' :: tail, some i => (texts[i]?).map fun t => acc ++ t ++ Delvetalk.Host.Spell.str tail
      | _, _ => none

/-- A spell with its holes filled at this write (a want's: at the read, `old` none). The holes are
    filled as data: the template, each hole a placeholder, is parsed once as a spell; each reading
    replaces its placeholder in a field's VALUE as plain text (in the card or action it must leave a
    card name or an action, in a field name it is refused), and `Delvetalk.Host.Spell.renderChecked` writes the
    result so that parsing it gives back exactly that card, action and fields. A reading therefore
    never opens a field, a block, a second spell or another card. `me` is the host's, after. -/
def filled (facts : Facts) (old : Option Data) (new : Data) (spell : Spell) : Filled :=
  let readings := spell.parts.filterMap fun | .hole term => some (holeText facts old new term) | .text _ => none
  if readings.any Option.isNone then .hole else
  let texts := readings.filterMap id
  let pre := placeholderPrefix spell
  let template := (spell.parts.foldl (fun (acc, i) part =>
    match part with
    | .text t => (acc ++ t, i)
    | .hole _ => (acc ++ s!"{pre}{i}z", i + 1)) ("", 0)).1
  let result : Option String := do
    let Delvetalk.Host.Spell.Parsed.spell card action fields := Delvetalk.Host.Spell.parse template | none
    guard (fields.all fun b => (b.name.splitOn pre).length == 1)
    let card ← substHoles pre texts card
    let action ← substHoles pre texts action
    guard (Delvetalk.Host.Spell.isCardName card.toList && Delvetalk.Host.Spell.isAction action.toList)
    let fields ← fields.mapM fun b => (substHoles pre texts b.value).map fun v => { b with value := v }
    Delvetalk.Host.Spell.renderChecked card action fields
  match result with
  | some t => .text t
  | none => .notSpell

/-- `filled`, as the text of the spell; none when a hole reads nothing or the result is not a spell. -/
def fill (facts : Facts) (old : Option Data) (new : Data) (spell : Spell) : Option String :=
  match filled facts old new spell with
  | .text t => some t
  | _ => none

/-- The objects a law cites by `under`, each once. -/
def citations (law : Law) : List String :=
  (law.flatMap fun (_, c) => c.names.filterMap fun | .law o => some o | _ => none).eraseDups

/-- The rules and wants a law's `under` citations carry, each with the object whose text holds it,
    followed through the cited texts' own `under` to `depth` (`Limits.lawDepth`), each once: a kind
    carries its rules and wants to every instance under it, as it carries its laws (whose meaning
    `denote` gives). The host owns each by the carrying object's owner. -/
partial def followed (reads : List (String × Data)) (law : Law) (depth : Nat := Limits.lawDepth) : List (String × Clause) :=
  if depth == 0 then [] else
  ((citations law).flatMap fun object => match (reads.lookup object).bind (rawField "law") with
    | some (.label text) => match parseClauses text with
      | .ok clauses =>
        (clauses.filter fun c => isRule c || isWant c).map (object, ·) ++
          followed reads (Delvetalk.Compiler.ObjectiveBendLaw.lawsOf clauses) (depth - 1)
      | .error _ => []
    | _ => []).eraseDups

/-- The law clauses a law's `under` citations carry, each with the object whose text holds it, followed
    through the cited texts' own `under` to `depth`, each once, as `followed` follows rules and wants. -/
partial def followedLaws (reads : List (String × Data)) (law : Law) (depth : Nat := Limits.lawDepth) : List (String × String) :=
  if depth == 0 then [] else
  ((citations law).flatMap fun object => match (reads.lookup object).bind (rawField "law") with
    | some (.label text) => match parseLawText text with
      | .ok cited => cited.map (fun (name, _) => (object, name)) ++ followedLaws reads cited (depth - 1)
      | .error _ => []
    | _ => []).eraseDups

/-- `request.laws` of a thing whose law is `law`: its own clauses and those `followedLaws` carries. -/
def lawClauses (reads : List (String × Data)) (law : Law) : Nat := law.length + (followedLaws reads law).length

/-! Small tests. Parsed laws go through the real parser. -/

private def parsed (text : String) : LawExpr :=
  match Delvetalk.Compiler.ObjectiveBendLaw.parse text with
  | .ok e => e
  | .error _ => .or (.eq (.fact .height) (.int 0)) (.not (.eq (.fact .height) (.int 0)))

private def rec1 (n : Nat) : Data := .record [("count", .natural n), ("open", .boolean true)]
private def facts : Facts := ⟨"7", "7", 3, 0, "", 0, "", [], 0, "", [], "", [], []⟩

-- A made thing's form field reads as `new.F` when the state has no field F; digits are a number.
private def made1 (n : Nat) (ringAt : String) : Data :=
  .record [("count", .natural n), ("fields", .variant "cons" (.record [("head", .record [("name", .label "ringAt"), ("value", .label ringAt)]),
    ("tail", .variant "nil" (.record []))]))]
#guard denote facts none (made1 3 "3") (parsed "new.count == new.ringAt")
#guard !denote facts none (made1 2 "3") (parsed "new.count == new.ringAt")
#guard denote facts none (made1 2 "3") (parsed "new.count + 1 == new.ringAt")
#guard !denote facts none (made1 3 "three") (parsed "new.count == new.ringAt")
#guard denote facts none (made1 3 "three") (parsed "new.ringAt == \"three\"")
#guard !denote facts none (made1 3 "four") (parsed "new.ringAt == \"three\"")
#guard !denote facts none (made1 1 "3") (parsed "new.count + 1 == new.ringAt")
#guard !denote facts none (made1 3 "3") (parsed "new.count == new.absent")
#guard denote facts (some (rec1 3)) (rec1 4) (parsed "monotone(count)")
#guard !denote facts (some (rec1 3)) (rec1 2) (parsed "monotone(count)")
#guard !denote facts none (rec1 2) (parsed "monotone(count)")
#guard denote facts none (rec1 2) (parsed "writeOnce(count)")
#guard !denote facts (some (rec1 3)) (rec1 4) (parsed "writeOnce(count)")
#guard denote facts (some (rec1 0)) (rec1 4) (parsed "writeOnce(count)")
#guard denote facts (some (.record [("name", .label "")])) (.record [("name", .label "ann")]) (parsed "writeOnce(name)")
#guard !denote facts (some (.record [("name", .label "ann")])) (.record [("name", .label "bob")]) (parsed "writeOnce(name)")
#guard denote facts (some (.record [("name", .label "ann")])) (.record [("name", .label "ann")]) (parsed "writeOnce(name)")
#guard !denote facts (some (.record [("name", .label "ann")])) (.record [("name", .label "")]) (parsed "writeOnce(name)")
#guard !denote facts (some (.record [("x", .natural 1)])) (.record [("y", .natural 1)]) (parsed "writeOnce(x)")
#guard denote facts none (rec1 2) (parsed "new.count <= 2")
#guard !denote facts none (rec1 3) (parsed "new.count <= 2")
#guard denote facts none (rec1 3) (parsed "new.count in [1, 3]")
#guard denote facts none (rec1 3) (parsed "request.subject == request.caller")
#guard !denote ⟨"a", "b", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (rec1 3) (parsed "request.subject == request.caller")
#guard denote facts none (rec1 3) (parsed "request.height == 3")
#guard denote ⟨"a", "a", 1, 0, "", 2, "", [], 0, "", [], "", [], []⟩ none (rec1 3) (parsed "request.kind == 2")
#guard !denote facts none (rec1 3) (parsed "request.kind == 1")
#guard !denote ⟨"a", "a", 1, 0, "", proposedKind, "", [], 0, "", [], "", [], []⟩ none (rec1 3) (parsed "request.kind == 0 or request.subject == \"b\"")
#guard denote ⟨"a", "a", 1, 0, "", proposedKind, "", [], 0, "", [], "", [], []⟩ none (rec1 3) (parsed "request.kind == 3")
#guard denote facts none (rec1 3) (parsed "request.subject == \"7\"")
#guard denote ⟨"ember", "ember", 1, 0, "abc", 0, "", [], 0, "", [], "", [], []⟩ none (rec1 3) (parsed "request.subject == \"ember\" and request.pin == \"abc\"")
#guard !denote ⟨"kim", "kim", 1, 0, "abc", 0, "", [], 0, "", [], "", [], []⟩ none (rec1 3) (parsed "request.subject == \"ember\"")
#guard !denote facts none (rec1 3) (parsed "request.subject == \"ember\"")
#guard denote facts none (rec1 3) (parsed "request.subject == 7")
#guard !denote ⟨"ember", "ember", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (rec1 3) (parsed "request.subject == 7")
#guard denote facts none (rec1 3) (parsed "new.open == 1 and not new.count <= 2")
#guard denote facts none (rec1 3) (parsed "new.count <= 2 implies new.open == 0")
#guard !denote facts none (rec1 3) (parsed "new.missing == 0")
-- Strict comparisons and inequality (playtest 5); a side that reads nothing makes each false.
#guard denote facts none (rec1 2) (parsed "new.count < 3") && !denote facts none (rec1 3) (parsed "new.count < 3")
#guard denote facts none (rec1 4) (parsed "new.count > 3") && !denote facts none (rec1 3) (parsed "new.count > 3")
#guard denote facts none (rec1 4) (parsed "new.count != 3") && !denote facts none (rec1 3) (parsed "new.count != 3")
#guard !denote facts none (rec1 3) (parsed "new.missing != 0") && !denote facts none (rec1 3) (parsed "new.missing < 9")
#guard denote facts none (rec1 3) (parsed "not new.missing == 0")
#guard denote facts none (rec1 3) (parsed "request.subject != \"ember\"") && !denote facts none (rec1 3) (parsed "request.subject != \"7\"")
#guard denote facts (some (rec1 2)) (rec1 3) (parsed "new.count > old.count") && !denote facts (some (rec1 3)) (rec1 3) (parsed "new.count > old.count")
private def lst (xs : List String) : Data :=
  xs.foldr (fun x tail => .variant "cons" (.record [("head", .label x), ("tail", tail)])) (.variant "nil" (.record []))
private def withList (xs : List String) (by_ : String) : Data :=
  .record [("entries", lst xs), ("lastBy", .label by_), ("count", .natural 1)]

#guard denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (withList [] "kim") (parsed "new.lastBy == request.subject")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (withList [] "bob") (parsed "new.lastBy == request.subject")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (withList [] "kim") (parsed "new.entries == request.subject")
#guard denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (withList [] "bob") (parsed "new.lastBy != request.subject")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (withList [] "kim") (parsed "new.lastBy != request.subject")
#guard denote ⟨"7", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (.record [("n", .natural 7)]) (parsed "new.n == request.subject")
#guard denote facts (some (withList ["a"] "x")) (withList ["a", "b", "c"] "x") (parsed "appendOnly(entries)")
#guard denote facts (some (withList ["a"] "x")) (withList ["a"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a", "b"] "x")) (withList ["a", "c"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a", "b"] "x")) (withList ["a"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a"] "x")) (rec1 3) (parsed "appendOnly(entries)")
#guard denote facts (some (withList ["a"] "x")) (withList ["a"] "y") (parsed "unchanged(entries)")
#guard !denote facts (some (withList ["a"] "x")) (withList ["a"] "y") (parsed "unchanged(lastBy)")
#guard !denote facts (some (withList ["a"] "x")) (withList ["a", "b"] "x") (parsed "unchanged(entries)")
#guard denote facts (some (rec1 3)) (.record [("open", .boolean true), ("count", .natural 3)]) (parsed "new.count == 3")
#guard denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (withList ["ann", "kim"] "x") (parsed "request.subject in new.entries")
#guard !denote ⟨"bob", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (withList ["ann", "kim"] "x") (parsed "request.subject in new.entries")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (withList ["ann", "kim"] "x") (parsed "request.subject in new.lastBy")
#guard denote ⟨"a", "forge", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (withList ["forge"] "x") (parsed "request.caller in new.entries")
#guard denote ⟨"a", "", 1, 0, "", 0, "ring", [], 0, "", [], "", [], []⟩ none (rec1 1) (parsed "request.method == \"ring\"")
#guard !denote ⟨"a", "", 1, 0, "", 0, "toll", [], 0, "", [], "", [], []⟩ none (rec1 1) (parsed "request.method == \"ring\"")
#guard (Delvetalk.Compiler.ObjectiveBendLaw.parse "request.height in new.entries").toBool == false
#guard denote facts none (withList ["a", "x"] "x") (parsed "new.lastBy in new.entries")
#guard !denote facts none (withList ["a"] "x") (parsed "new.lastBy in new.entries")
#guard refusedBy [("a", parsed "new.count <= 5"), ("b", parsed "new.count <= 2")] facts none (rec1 3) == some "b"

private def rain (a : String) (t : Nat) (x : String) : Data :=
  .record [("author", .label a), ("at", .natural t), ("text", .label x)]
private def rel (rows : List Data) : Data :=
  .record [("rains", .variant "rows" (.record [("items",
    rows.foldr (fun x tail => .variant "cons" (.record [("head", x), ("tail", tail)])) (.variant "nil" (.record [])))]))]

#guard denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "insertOnly(rains)")
#guard denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a"]) (parsed "insertOnly(rains)")
#guard denote facts none (rel [rain "ann" 1 "a"]) (parsed "insertOnly(rains)")
#guard !denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "kim" 2 "b"]) (parsed "insertOnly(rains)")
#guard !denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "changed"]) (parsed "insertOnly(rains)")
#guard !denote facts (some (rec1 1)) (rec1 1) (parsed "insertOnly(count)")
-- Retention: a row the write's insert evicted does not count against insertOnly, but a retraction
-- or an alteration still does, and a full relation is no evidence of eviction (codex host 8).
private def limited : Facts := { facts with evicted := [("rains", rain "ann" 1 "a")] }
#guard denote limited (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "kim" 2 "b", rain "eve" 3 "c"]) (parsed "insertOnly(rains)")
#guard !denote facts (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "kim" 2 "b", rain "eve" 3 "c"]) (parsed "insertOnly(rains)")
#guard !denote limited (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "ann" 1 "a"]) (parsed "insertOnly(rains)")
#guard !denote limited (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "ann" 1 "a", rain "eve" 3 "c"]) (parsed "insertOnly(rains)")
#guard !denote limited (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "kim" 2 "x", rain "eve" 3 "c"]) (parsed "insertOnly(rains)")
#guard denote facts none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "count(new.rains) <= 2")
#guard !denote facts none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "count(new.rains) <= 1")
#guard denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "count(new.rains) <= count(old.rains) + 1")
#guard !denote facts (some (rel [])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "count(new.rains) <= count(old.rains) + 1")
#guard denote facts none (rel [rain "ann" 1 "a"]) (parsed "count(new.rains) <= count(old.rains) + 1")
#guard denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "request.subject in new.rains.author")
#guard !denote ⟨"bob", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "request.subject in new.rains.author")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "request.subject in new.rains.text")
#guard denote ⟨"a", "forge", 1, 0, "", 0, "", [], 0, "", [], "", [], []⟩ none (rel [rain "forge" 1 "a"]) (parsed "request.caller in new.rains.author")

#guard denote facts (some (rec1 3)) (rec1 4) (parsed "changed(new.count)")
#guard denote facts (some (rec1 4)) (rec1 3) (parsed "changed(new.count)")
#guard !denote facts (some (rec1 3)) (rec1 3) (parsed "changed(new.count)")
#guard !denote facts (some (.record [])) (rec1 3) (parsed "changed(new.count)")
#guard !denote facts (some (rec1 3)) (.record []) (parsed "changed(new.count)")
#guard !denote facts none (rec1 3) (parsed "changed(new.count)")
#guard !denote facts (some (.record [("count", .boolean true)])) (rec1 1) (parsed "changed(new.count)")
#guard denote facts (some (rec1 3)) (rec1 4) (parsed "changed(new.count + -10)")
#guard !denote facts (some (rec1 3)) (rec1 5) (parsed "changed(new.count % 2)")
#guard denote facts (some (withList [] "ann")) (withList [] "kim") (parsed "changed(new.lastBy)")
#guard !denote facts (some (withList [] "ann")) (withList [] "ann") (parsed "changed(new.lastBy)")
#guard denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"])
  (parsed "changed(count(new.rains))")
#guard denote facts (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "ann" 1 "a"])
  (parsed "changed(count(new.rains))")
#guard !denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "kim" 2 "b"])
  (parsed "changed(count(new.rains))")
#guard denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"])
  (parsed "changed(count(new.rains where author == \"kim\"))")
#guard !denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"])
  (parsed "changed(count(new.rains where author == \"ann\"))")
#guard !denote facts (some (.record [])) (rel []) (parsed "changed(count(new.rains))")
#guard !denote facts (some (rel [])) (.record []) (parsed "changed(count(new.rains))")
private def selected (who : String) : Data :=
  match rel [rain "ann" 1 "a", rain "kim" 2 "b", rain "kim" 3 "c"] with
  | .record fields => .record (("selected", .label who) :: fields)
  | _ => .record []
#guard denote facts (some (selected "ann")) (selected "kim")
  (parsed "changed(count(new.rains where author == new.selected))")
#guard work facts (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"])
  (parsed "changed(count(new.rains))") == 6
#guard work facts (some (rec1 3)) (rec1 4) (parsed "changed(new.count + 1)") == 7
#guard standingRefusal (parsed "changed(new.count)") == some "changed(new.count)"

-- The clock, the written object and `old.F` (LAW §4 A, E, H): METAPHYSICS's `alive` clause, admitted
-- for a tend or within 1440 minutes of the last tending, refused past it; `old.F` at creation is the
-- field kind's empty value; the three-slot bound reads the new state's gap.
private def tended (t gap : Nat) : Data := .record [("tended", .natural t), ("gap", .natural gap), ("name", .label "fern")]
private def when (clock : Nat) (method object : String) : Facts := { facts with clock, method, object }
private def alive : String := "request.method == \"tend\" or request.clock <= old.tended + 1440"
#guard (Delvetalk.Compiler.ObjectiveBendLaw.parse alive).toBool
#guard denote (when 1500 "rain" "bell") (some (tended 100 0)) (tended 100 0) (parsed alive)
#guard !denote (when 1600 "rain" "bell") (some (tended 100 0)) (tended 100 0) (parsed alive)
#guard denote (when 1600 "tend" "bell") (some (tended 100 0)) (tended 1600 0) (parsed alive)
#guard !denote (when 1441 "rain" "bell") none (tended 0 0) (parsed alive)
#guard denote (when 1440 "rain" "bell") none (tended 0 0) (parsed alive)
#guard denote (when 0 "" "tide") none (tended 0 0) (parsed "request.object == \"tide\"")
#guard !denote (when 0 "" "bell") none (tended 0 0) (parsed "request.object == \"tide\"")
#guard denote (when 0 "" "fern") none (tended 0 0) (parsed "request.object == new.name")
#guard denote (when 200 "" "x") (some (tended 100 0)) (tended 100 100) (parsed "request.clock <= old.tended + new.gap")
#guard !denote (when 201 "" "x") (some (tended 100 0)) (tended 100 100) (parsed "request.clock <= old.tended + new.gap")
#guard denote (when 0 "" "x") (some (tended 5 0)) (tended 5 0) (parsed "old.name == new.name")
#guard !denote (when 0 "" "x") none (tended 5 0) (parsed "old.name == new.name")
#guard denote (when 0 "" "x") none (tended 5 0) (parsed "old.tended == 0")

-- The relational atoms (docs/LAW.md §4 B, C, D, F): a filtered count and the quorum it makes, a
-- change of rows by whom, membership in a cited object's relation, and a cited object's law.
#guard denote facts none (rel [rain "ann" 1 "a", rain "kim" 2 "b", rain "ann" 3 "c"]) (parsed "count(new.rains where author == \"ann\" and at == 3) == 1")
#guard denote facts none (rel [rain "ann" 1 "a", rain "kim" 2 "b", rain "ann" 3 "c"]) (parsed "count(new.rains where author == \"kim\" and at == 3) == 0")
#guard !denote facts none (rel [rain "ann" 1 "a"]) (parsed "count(new.rains where author == \"ann\" and at == new.absent) == 0")
private def as (who : String) : Facts := { facts with subject := who }
#guard denote facts none (rel [rain "ann" 1 "a", rain "kim" 2 "b", rain "ann" 3 "c"]) (parsed "count(new.rains where author == \"ann\") <= 2")
#guard !denote facts none (rel [rain "ann" 1 "a", rain "kim" 2 "b", rain "ann" 3 "c"]) (parsed "count(new.rains where author == \"ann\") <= 1")
#guard denote (as "kim") none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "count(new.rains) <= count(new.rains where author == request.subject) + 1")
#guard !denote (as "eve") none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "count(new.rains) <= count(new.rains where author == request.subject) + 1")
#guard denote (as "kim") (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "changed(new.rains.author) by request.subject")
#guard !denote (as "ann") (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "changed(new.rains.author) by request.subject")
#guard denote (as "kim") (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "ann" 1 "a"]) (parsed "changed(new.rains.author) by request.subject")
#guard !denote (as "kim") (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "x"]) (parsed "changed(new.rains.author) by request.subject")
#guard denote { as "kim" with evicted := [("rains", rain "ann" 1 "a")] } (some (rel [rain "ann" 1 "a"])) (rel [rain "kim" 2 "b"]) (parsed "changed(new.rains.author) by request.subject")
private def roster : Facts := { as "kim" with reads := [("roster", rel [rain "kim" 1 "x"])] }
#guard denote roster none (rec1 1) (parsed "request.subject in \"roster\".rains.author")
#guard !denote { roster with subject := "eve" } none (rec1 1) (parsed "request.subject in \"roster\".rains.author")
#guard !denote (as "kim") none (rec1 1) (parsed "request.subject in \"roster\".rains.author")
private def kindOf (law : String) : Facts := { facts with reads := [("kind/x", .record [("law", .label law)])] }
#guard denote (kindOf "law small: new.count <= 2") none (rec1 2) (parsed "under \"kind/x\"")
#guard !denote (kindOf "law small: new.count <= 2") none (rec1 3) (parsed "under \"kind/x\"")
#guard refusal [("kind", parsed "under \"kind/x\"")] (kindOf "law small \"two at most\": new.count <= 2") none (rec1 3) ==
  some ("small", some "two at most")
#guard !denote (kindOf "law small: new.count <= 2") none (rec1 2) (parsed "under \"kind/x\"") 0
#guard !denote (kindOf "law loop: under \"kind/x\"") none (rec1 2) (parsed "under \"kind/x\"")
#guard !denote (kindOf "not a law") none (rec1 2) (parsed "under \"kind/x\"")
#guard !denote facts none (rec1 2) (parsed "under \"kind/x\"")
-- A cited law never refuses its owner's amendment of their own thing, and refuses everyone else's.
private def owned (who : String) : Data := .record [("owner", .label who), ("count", .natural 3)]
private def amending (who : String) : Facts := { kindOf "law lock: request.subject == \"bob\"" with subject := who, kind := 2 }
#guard denote (amending "alice") (some (owned "alice")) (owned "alice") (parsed "under \"kind/x\"")
#guard !denote (amending "carol") (some (owned "alice")) (owned "alice") (parsed "under \"kind/x\"")
#guard !denote { amending "alice" with kind := 0 } (some (owned "alice")) (owned "alice") (parsed "under \"kind/x\"")
#guard !denote (amending "") (some (owned "")) (owned "") (parsed "under \"kind/x\"")

-- The arms OVERHAUL §3 adds to the one language: another object's field as a reference (absent, it
-- fails closed), `>=` and FOUNDATION §10's crossing, membership before the write (nothing at
-- creation), `%`, the verb, the kind `rule`, and a comparison whose constant comes first.
private def garden (tended : Nat) : Data := .record [("tended", .natural tended)]
private def atClock (clock : Nat) : Facts := { facts with clock, reads := [("garden", garden 100)] }
private def company : String := "request.clock <= \"garden\".tended + 1440"
#guard denote (atClock 1540) none (rec1 0) (parsed company)
#guard !denote (atClock 1541) none (rec1 0) (parsed company)
#guard !denote { facts with clock := 0 } none (rec1 0) (parsed company)
#guard denote (atClock 0) none (rec1 0) (parsed "count(\"garden\".tended) <= 0") == false
#guard denote facts none (rel [rain "ann" 1 "a", rain "kim" 2 "b", rain "eve" 3 "c"]) (parsed "count(new.rains) >= 3")
#guard !denote facts none (rel [rain "ann" 1 "a"]) (parsed "count(new.rains) >= 3")
private def two : String := "count(new.rains) >= 2 and count(old.rains) <= 1"
#guard denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed two)
#guard !denote facts (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b", rain "eve" 3 "c"]) (parsed two)
private def marks (names : List String) : Data :=
  .record [("marks", .variant "rows" (.record [("items",
    names.foldr (fun n tail => .variant "cons" (.record [("head", .record [("name", .label n)]), ("tail", tail)])) (.variant "nil" (.record [])))]))]
private def next : String := "\"done\" in new.marks.name and not \"done\" in old.marks.name"
#guard denote facts (some (marks [])) (marks ["done"]) (parsed next)
#guard !denote facts (some (marks ["done"])) (marks ["done"]) (parsed next)
#guard denote facts none (marks ["done"]) (parsed next)
#guard !denote facts none (marks ["done"]) (parsed "\"done\" in old.marks.name")
#guard denote (as "kim") (some (withList ["kim"] "x")) (withList [] "x") (parsed "request.subject in old.entries")
#guard !denote (as "kim") none (withList ["kim"] "x") (parsed "request.subject in old.entries")
#guard denote facts none (.record [("ticks", .natural 48)]) (parsed "new.ticks % 24 == 0")
#guard !denote facts none (.record [("ticks", .natural 49)]) (parsed "new.ticks % 24 == 0")
#guard denote facts none (.record [("ticks", .natural 49)]) (parsed "new.ticks % 24 + 1 == 2 and new.ticks % 7 % 4 == 0")
#guard denote { facts with method := "act", verb := "water" } none (rec1 0) (parsed "request.verb == \"water\" and request.method == \"act\"")
#guard !denote { facts with method := "rain", verb := "rain" } none (rec1 0) (parsed "request.verb == \"water\"")
#guard denote { facts with kind := 4 } none (rec1 0) (parsed "request.kind == rule")
#guard denote facts none (rec1 3) (parsed "3 == new.count and \"7\" == request.subject and 0 + 1 <= new.count")
#guard !denote facts none (rec1 3) (parsed "\"8\" == request.subject")

-- Another thing's want (`"O" wants N`): its condition judged on the cited state as it stands; a want
-- it does not have, a state not read, or the depth spent reads false.
private def clausesOf (text : String) : List Clause :=
  match parseClauses text with
  | .ok clauses => clauses
  | .error _ => []
private def bellText : String :=
  "law kept: insertOnly(rains)\n" ++
  "rule two \"two rains\": count(new.rains) >= 2 and count(old.rains) <= 1 then delvetalk me note / text: {request.object} has {count(new.rains)} rains, the last by {request.subject}\n" ++
  "want second \"a second hand\": count(new.rains) <= 1 asks delvetalk {request.object} rain\n" ++
  "want tended: new.tended + 1440 <= request.clock asks delvetalk {request.object} tend"
private def wanting (state : Data) : Facts := { facts with reads := [("bell", state)], wants := [("bell", clausesOf bellText)] }
#guard denote (wanting (rel [rain "ann" 1 "a"])) none (rec1 0) (parsed "\"bell\" wants second")
#guard !denote (wanting (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) none (rec1 0) (parsed "\"bell\" wants second")
#guard !denote (wanting (rel [rain "ann" 1 "a"])) none (rec1 0) (parsed "\"bell\" wants third")
#guard !denote (wanting (rel [rain "ann" 1 "a"])) none (rec1 0) (parsed "\"bell\" wants two")
#guard !denote { facts with wants := [("bell", clausesOf bellText)] } none (rec1 0) (parsed "\"bell\" wants second")
#guard !denote (wanting (rel [])) none (rec1 0) (parsed "\"bell\" wants second") 0
#guard denote { wanting (tended 0 0) with clock := 1440 } none (rec1 0) (parsed "\"bell\" wants tended")
#guard !denote { wanting (tended 1 0) with clock := 1440 } none (rec1 0) (parsed "\"bell\" wants tended")

-- One text, three modalities: its laws are the law; a write fires the rules whose condition it makes
-- hold, with their holes filled at the write; the wants pose while they hold, by the clock.
#guard (parseLawText bellText).toOption.map (·.map (·.1)) == some ["kept"]
#guard (clausesOf bellText).map (·.name) == ["kept", "two", "second", "tended"]
private def kim2 : Facts := { as "kim" with object := "bell/2" }
private def oneRain : Data := rel [rain "ann" 1 "a"]
private def twoRains : Data := rel [rain "ann" 1 "a", rain "kim" 2 "b"]
#guard (fires kim2 (some oneRain) twoRains (clausesOf bellText)).map (·.name) == ["two"]
#guard (fires kim2 (some twoRains) (rel [rain "ann" 1 "a", rain "kim" 2 "b", rain "eve" 3 "c"]) (clausesOf bellText)).isEmpty
-- What a thing stands at: its clauses, own and followed (a kind cited twice counts once), and its refusals.
private def kindTexts : List (String × Data) :=
  [("kind/x", .record [("law", .label "law a: new.count <= 3\nlaw b: under \"kind/base\"")]),
   ("kind/base", .record [("law", .label "law c: new.open == 1")])]
#guard lawClauses kindTexts [("own", parsed "under \"kind/x\""), ("too", parsed "under \"kind/base\"")] == 5
#guard lawClauses [] [("own", parsed "new.count <= 3")] == 1
private def standing (laws refusedBy : Nat) : Facts := { facts with object := "seal", standing := [("seal", { laws, refusedBy })] }
#guard denote (standing 2 1) none (rec1 0) (parsed "request.laws >= 2 and request.refusedBy >= 1")
#guard !denote (standing 2 0) none (rec1 0) (parsed "request.laws >= 2 and request.refusedBy >= 1")
#guard !denote facts none (rec1 0) (parsed "request.laws >= 0")
-- A cited want reads its own thing's standing.
private def citing : Facts :=
  { standing 2 1 with object := "bell", reads := [("seal", rec1 0)],
                      wants := [("seal", clausesOf "want tried: request.refusedBy >= 1 asks delvetalk {request.object} seal")] }
#guard denote citing none (rec1 0) (parsed "\"seal\" wants tried")
#guard !denote { citing with standing := [("seal", { laws := 2, refusedBy := 0 })] } none (rec1 0) (parsed "\"seal\" wants tried")
#guard (poses { facts with clock := 2000 } "bell/2" (.record [("rains", (rawField "rains" oneRain).getD (.boolean false)), ("tended", .natural 100)]) (clausesOf bellText)).map (·.name) == ["second", "tended"]
#guard (poses { facts with clock := 2000 } "bell/2" (.record [("rains", (rawField "rains" twoRains).getD (.boolean false)), ("tended", .natural 1000)]) (clausesOf bellText)).isEmpty
#guard (((clausesOf bellText)[1]?.bind (·.modality.spell?)).bind (fill kim2 (some oneRain) twoRains)) ==
  some "delvetalk me note / text: bell/2 has 2 rains, the last by kim"
#guard (((clausesOf bellText)[2]?.bind (·.modality.spell?)).bind (fill (asItStands facts "bell/2") none oneRain)) ==
  some "delvetalk bell/2 rain"
#guard (((clausesOf "rule r: new.count == 1 then delvetalk x / y: {new.missing}")[0]?.bind (·.modality.spell?)).bind
  (fill facts none (rec1 1))) == none

-- A hole's reading is data: a resident's text never opens a field, a block, a second spell or a card.
private def noteFill (reading : String) : Option String :=
  (((clausesOf "rule r: new.count == 1 then delvetalk me note / text: {new.message}")[0]?.bind (·.modality.spell?)).bind
    (fill facts none (.record [("count", .natural 1), ("message", .label reading)])))
#guard noteFill "bell/2 has 2 rains" == some "delvetalk me note / text: bell/2 has 2 rains"
#guard ["x\ndelvetalk policy set / owner: eve", "a / to: eve", "<<END", "END", "  lead", "", "tail  ", "---", "a, b: c",
    "END\nEND_0\nEND_1\nEND_2", "```\ndelvetalk x y", "r\r\nEND\r"].all fun v =>
  match noteFill v with
  | some t => Delvetalk.Host.Spell.parse t == Delvetalk.Host.Spell.Parsed.spell "me" "note" [⟨"text", v⟩] && (Delvetalk.Host.Spell.segments t).length == 1
  | none => false
#guard noteFill "a / to: eve" == some "delvetalk me note\ntext: <<END\na / to: eve\nEND"
private def cardFill (reading : String) : Option String :=
  (((clausesOf "rule r: new.count == 1 then delvetalk {new.message} ring")[0]?.bind (·.modality.spell?)).bind
    (fill facts none (.record [("count", .natural 1), ("message", .label reading)])))
#guard cardFill "bell/2" == some "delvetalk bell/2 ring"
#guard cardFill "bell/2 ring\ndelvetalk x" == none
#guard cardFill "" == none
private def nameFill (reading : String) : Option String :=
  (((clausesOf "rule r: new.count == 1 then delvetalk me note / {new.message}: x")[0]?.bind (·.modality.spell?)).bind
    (fill facts none (.record [("count", .natural 1), ("message", .label reading)])))
#guard nameFill "text" == none

-- `under` follows all three: an instance under a kind is judged by the kind's laws (`denote`) and
-- carries the kind's rules and wants (`followed`), through the kind's own `under`, each once.
private def kinds : List (String × Data) :=
  [("kind/bell", .record [("law", .label ("law kind: under \"kind/thing\"\n" ++ bellText))]),
   ("kind/thing", .record [("law", .label "want named: new.name == \"\" asks delvetalk {request.object} name")])]
#guard (followed kinds [("kind", parsed "under \"kind/bell\"")]).map (fun (o, c) => (o, c.name)) ==
  [("kind/bell", "two"), ("kind/bell", "second"), ("kind/bell", "tended"), ("kind/thing", "named")]
#guard (followed kinds [("kind", parsed "under \"kind/bell\""), ("again", parsed "under \"kind/bell\"")]).length == 4
#guard (followed kinds [("kind", parsed "under \"kind/bell\"")] 1).map (·.1) == ["kind/bell", "kind/bell", "kind/bell"]
#guard denote { facts with reads := kinds } (some oneRain) twoRains (parsed "under \"kind/bell\"")
#guard !denote { facts with reads := kinds } (some twoRains) oneRain (parsed "under \"kind/bell\"")

end Delvetalk.Host.Law
