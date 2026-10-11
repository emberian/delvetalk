/- Meaning of the enforced law fragment (`Compiler/ObjectiveBendLaw.lean`) over
   old and new state `Data` plus request facts: the one judge of every clause.
   A principal is text: `subject` and `caller` read as a number when the principal
   is a decimal numeral and as text otherwise, so `request.subject ==
   request.caller` holds for any principal while order and constants need
   numerals. Absent or mistyped readings fail closed. -/
import Delvetalk.Host.Store
import Delvetalk.Canonical
import Compiler.ObjectiveBendDataWire

namespace Delvetalk.Host

def renderLaw (law : Law) : String :=
  "\n".intercalate (law.map fun (name, clause) => s!"law {name}: {clause.render}")

/-- The `"reading"` after a law's name, as the compiler's grammar has it (`law NAME "reading": EXPR`,
    a JSON string literal): the reading and the rest after it, or none when the line has none. -/
def lawReading (rest : String) : Except String (Option (String × String)) := do
  let chars := rest.toList
  unless chars.head? == some '"' do return none
  let rec close : List Char → Nat → Option Nat
    | [], _ => none
    | '\\' :: _ :: more, n => close more (n + 2)
    | '"' :: _, n => some n
    | _ :: more, n => close more (n + 1)
  let some n := close (chars.drop 1) 1 | throw "a law reading is an unterminated string"
  let literal := String.ofList (chars.take (n + 1))
  let reading ← (Lean.Json.parse literal >>= (·.getStr?)).mapError fun _ => s!"a law reading must be a JSON string, found {literal}"
  return some (reading, String.ofList (chars.drop (n + 1)))

/-- Law text: one `law NAME: EXPR` or `law NAME "reading": EXPR` per line, the grammar the compiler
    accepts at the top of a package; the readings beside the law, by clause name. -/
def parseLawTextReadings (text : String) : Except String (Law × List (String × String)) := do
  if text.utf8ByteSize > Limits.maxLawBytes then throw "law text exceeds its byte capacity"
  let lines := (text.splitOn "\n").map String.trimAscii |>.filter (!·.isEmpty) |>.map (·.toString)
  if lines.length > Limits.maxLawClauses then throw "law has too many clauses"
  let parsed ← lines.mapM fun line => do
    let some rest := line.dropPrefix? "law " | throw s!"expected `law NAME: EXPR`, found `{line}`"
    let rest := rest.toString
    let name := (rest.takeWhile fun c => c.isAlphanum || c == '_').toString
    unless Delvetalk.Compiler.ObjectiveBendParse.isIdent name.toList do throw s!"invalid law name in `{line}`"
    let after := (rest.drop name.length).toString.trimAsciiStart.toString
    let (reading, after) ← match ← lawReading after with
      | some (r, more) => pure (some r, more.trimAsciiStart.toString)
      | none => pure (none, after)
    let some expr := after.dropPrefix? ":" | throw s!"expected `law NAME: EXPR`, found `{line}`"
    pure ((name, ← Delvetalk.Compiler.ObjectiveBendLaw.parse expr.toString), reading.map (name, ·))
  let law := parsed.map (·.1)
  Delvetalk.Compiler.ObjectiveBendLaw.checkNames law
  return (law, parsed.filterMap (·.2) |>.filter (!·.2.isEmpty))

/-- Law text: one `law NAME: EXPR` per line (a reading after the name allowed), as at the top of a package. -/
def parseLawText (text : String) : Except String Law := do
  return (← parseLawTextReadings text).1

end Delvetalk.Host

namespace Delvetalk.Host.Law
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
open Delvetalk.Compiler.ObjectiveBendLaw (LawExpr LawTerm)

structure Facts where
  subject : String
  caller : String
  height : Nat
  turn : Nat
  /-- Pin of the package the object runs after this write. -/
  pin : String := ""
  /-- 0 write (the object's own method), 1 reprogram, 2 amend, 3 proposed (`kindNames`). -/
  kind : Nat := 0
  /-- The method whose run made the change; "" for an op. -/
  method : String := ""
  /-- The rows the declared retention dropped while the write's edits were applied, by field
      (`Ops.applyEditsEvicting`): `insertOnly` does not count them, and nothing else. -/
  evicted : List (String × Data) := []
  /-- The world clock the turn read, in minutes (`request.clock`, LAW §4 A). -/
  clock : Nat := 0
  /-- The written object's id (`request.object`, LAW §4 H). -/
  object : String := ""
  /-- The state of every object the law cites (`"O".F.COL`, `under "O"`), transitively through `under`,
      at the version the write records as its root (`Ops.citedStates`). -/
  reads : List (String × Data) := []

/-- The kinds of change a law tells apart by `request.kind`, by name. `proposed` is a state write
    that does not come from the object's own method: a `world-propose`, or the state a reprogram's
    migration makes. So a law admitting `request.kind == 0` admits only the object's own method's
    writes, and one that wants proposals says `request.kind == 3` (or `proposed`, once the law
    grammar reads the name). -/
def kindNames : List (String × Nat) := [("write", 0), ("reprogram", 1), ("amend", 2), ("proposed", 3)]

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

/-- Byte order of canonical encodings: the order `canonicalRows` sorts keys in. -/
def bytesLt (a b : ByteArray) : Bool := Id.run do
  for i in [0:min a.size b.size] do
    if a[i]! != b[i]! then return a[i]! < b[i]!
  return a.size < b.size

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

/-- A top-level field of a state as a law reads it: text, or a scalar as a number. -/
def fieldReading (name : String) (state : Data) : Option Reading :=
  (rawField name state).bind fun
    | .label s => some (.text s)
    | d => (scalarOf d).map .num

/-- `old.F` at creation: the empty value of the field's kind as the new state has it ("" for text, 0
    for a scalar), as `writeOnce` reads an empty field. -/
def emptyReading (name : String) (new : Data) : Option Reading :=
  (fieldReading name new).map fun
    | .text _ => .text ""
    | .num _ => .num 0

/-- The rows a count reads: of `new.F`, or of `old.F` (none before a creation: no rows). -/
def rowsAt (old : Option Data) (new : Data) : LawTerm → Option (List Data)
  | .field name => (rawField name new).bind rowsOf
  | .old name => match old with
    | none => some []
    | some before => (rawField name before).bind rowsOf
  | _ => none

def number (reading : Option Reading) : Option Int :=
  match reading with
  | some (.num n) => some n
  | _ => none

mutual
partial def read (facts : Facts) (old : Option Data) (new : Data) : LawTerm → Option Reading
  | .field name => fieldReading name new
  | .old name => match old with
    | some o => fieldReading name o
    | none => emptyReading name new
  | .fact .subject => some (principalReading facts.subject)
  | .fact .caller => some (principalReading facts.caller)
  | .fact .height => some (.num facts.height)
  | .fact .turn => some (.num facts.turn)
  | .fact .pin => some (.text facts.pin)
  | .fact .kind => some (.num facts.kind)
  | .fact .method => some (.text facts.method)
  | .fact .clock => some (.num facts.clock)
  | .fact .object => some (.text facts.object)
  | .count of .all => (rowsAt old new of).map fun rows => .num rows.length
  | .int value => some (.num value)
  | .text text => some (.text text)
  | .sum left right => match number (read facts old new left), number (read facts old new right) with
    | some x, some y => some (.num (x + y))
    | _, _ => none
  -- The rows whose column holds the value, by canonical bytes (docs/LAW.md §4 C).
  | .count of (.eq col value) => do
    let rows ← rowsAt old new of
    let want := canon (← memberData facts old new value)
    return .num (rows.filter fun r => (rawField col r).map canon == some want).length

/-- The exact text a term reads as: a principal as given, a text field, a constant. -/
partial def textOf (facts : Facts) (old : Option Data) (new : Data) : LawTerm → Option String
  | .fact .subject => some facts.subject
  | .fact .caller => some facts.caller
  | .fact .pin => some facts.pin
  | .fact .method => some facts.method
  | .fact .object => some facts.object
  | .text text => some text
  | term => match read facts old new term with
    | some (.text s) => some s
    | _ => none

/-- The value a term stands for in a membership, a filter or `changed ... by`, compared by canonical
    bytes: a field as it is, a numeric reading as a natural, text as a label. -/
partial def memberData (facts : Facts) (old : Option Data) (new : Data) : LawTerm → Option Data
  | .field name => rawField name new
  | .old name => old.bind (rawField name)
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

/-- The rows of `F` in `rows`'s column `C`, as `.column` reads them. -/
def columnHas (rows : List Data) (col : String) (w : Data) : Bool :=
  rows.any fun r => (rawField col r).map canon == some (canon w)

/-- The rows a write changed in relation (or list) `field`: those of `old` gone from `new` by canonical
    bytes, less the ones the declared retention dropped, and those of `new` not in `old`. -/
def changedRows (facts : Facts) (old : Option Data) (new : Data) (field : String) : Option (List Data) := do
  let after ← (rawField field new).bind rowsOf
  let before ← match old with
    | none => some []
    | some o => (rawField field o).bind rowsOf
  let now := after.map canon
  let was := before.map canon
  let gone := before.filter fun r => !now.contains (canon r) &&
    !(facts.evicted.any fun (f, x) => f == field && canon x == canon r)
  return gone ++ after.filter fun r => !was.contains (canon r)

/-- The meaning of a clause. `under "O"` reads the `law` text of the cited object's state and judges
    this write by each of its clauses at `depth - 1`; at depth 0 it is false, so a cycle of citations
    ends (`Limits.lawDepth`). -/
partial def denote (facts : Facts) (old : Option Data) (new : Data) (e : LawExpr) (depth : Nat := Limits.lawDepth) : Bool :=
  match e with
  | .eq left right => match right with
    | .text text => textOf facts old new left == some text
    | .int value => number (read facts old new left) == some value
    | _ => match read facts old new left, read facts old new right with
      | some x, some y => x == y || x.render == y.render
      | _, _ => false
  | .le left right => match number (read facts old new left), number (read facts old new right) with
    | some x, some y => decide (x ≤ y)
    | _, _ => false
  | .member term (.ints values) => match number (read facts old new term) with
    | some x => values.contains x
    | none => false
  | .member term (.list field) => match memberData facts old new term, (rawField field new).bind (listItems []) with
    | some w, some items => items.contains (canon w)
    | _, _ => false
  | .member term (.column field col) => match memberData facts old new term, (rawField field new).bind rowsOf with
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
          let now := after.map canon
          rows.all fun r => now.contains (canon r) || facts.evicted.any fun (f, x) => f == field && canon x == canon r
        | none => false
  -- Every row the write changed carries `who` in its column (docs/LAW.md §4 B).
  | .changed field col who => match changedRows facts old new field, memberData facts old new who with
    | some rows, some w => rows.all fun r => (rawField col r).map canon == some (canon w)
    | _, _ => false
  -- Membership in a cited object's relation, as it stood at the root the write records (§4 D).
  | .member term (.cited object field col) => match memberData facts old new term,
      ((facts.reads.lookup object).bind (rawField field)).bind rowsOf with
    | some w, some rows => columnHas rows col w
    | _, _ => false
  -- The cited object's law text judges this write too (§4 F).
  | .under object => depth > 0 && match (facts.reads.lookup object).bind (rawField "law") with
    | some (.label text) => match parseLawText text with
      | .ok law => law.all fun (_, clause) => clause.fieldsPlain && denote facts old new clause (depth - 1)
      | .error _ => false
    | _ => false
  | .not body => !denote facts old new body depth
  | .and left right => denote facts old new left depth && denote facts old new right depth
  | .or left right => denote facts old new left depth || denote facts old new right depth
  | .implies premise conclusion => !denote facts old new premise depth || denote facts old new conclusion depth

/-- A clause that reads a non-plain field name refuses every write. -/
def admits (facts : Facts) (old : Option Data) (new : Data) (clause : LawExpr) : Bool :=
  clause.fieldsPlain && denote facts old new clause

/-- The first law, in source order, that refuses this write. -/
def refusedBy (law : Law) (facts : Facts) (old : Option Data) (new : Data) : Option String :=
  (law.find? fun (_, clause) => !admits facts old new clause).map Prod.fst

/-! Small tests. Parsed laws go through the real parser. -/

private def parsed (text : String) : LawExpr :=
  match Delvetalk.Compiler.ObjectiveBendLaw.parse text with
  | .ok e => e
  | .error _ => .or (.eq (.fact .height) (.int 0)) (.not (.eq (.fact .height) (.int 0)))

private def rec1 (n : Nat) : Data := .record [("count", .natural n), ("open", .boolean true)]
private def facts : Facts := ⟨"7", "7", 3, 0, "", 0, "", [], 0, "", []⟩

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
#guard !denote ⟨"a", "b", 1, 0, "", 0, "", [], 0, "", []⟩ none (rec1 3) (parsed "request.subject == request.caller")
#guard denote facts none (rec1 3) (parsed "request.height == 3")
#guard denote ⟨"a", "a", 1, 0, "", 2, "", [], 0, "", []⟩ none (rec1 3) (parsed "request.kind == 2")
#guard !denote facts none (rec1 3) (parsed "request.kind == 1")
#guard !denote ⟨"a", "a", 1, 0, "", proposedKind, "", [], 0, "", []⟩ none (rec1 3) (parsed "request.kind == 0 or request.subject == \"b\"")
#guard denote ⟨"a", "a", 1, 0, "", proposedKind, "", [], 0, "", []⟩ none (rec1 3) (parsed "request.kind == 3")
#guard denote facts none (rec1 3) (parsed "request.subject == \"7\"")
#guard denote ⟨"ember", "ember", 1, 0, "abc", 0, "", [], 0, "", []⟩ none (rec1 3) (parsed "request.subject == \"ember\" and request.pin == \"abc\"")
#guard !denote ⟨"kim", "kim", 1, 0, "abc", 0, "", [], 0, "", []⟩ none (rec1 3) (parsed "request.subject == \"ember\"")
#guard !denote facts none (rec1 3) (parsed "request.subject == \"ember\"")
#guard denote facts none (rec1 3) (parsed "request.subject == 7")
#guard !denote ⟨"ember", "ember", 1, 0, "", 0, "", [], 0, "", []⟩ none (rec1 3) (parsed "request.subject == 7")
#guard denote facts none (rec1 3) (parsed "new.open == 1 and not new.count <= 2")
#guard denote facts none (rec1 3) (parsed "new.count <= 2 implies new.open == 0")
#guard !denote facts none (rec1 3) (parsed "new.missing == 0")
private def lst (xs : List String) : Data :=
  xs.foldr (fun x tail => .variant "cons" (.record [("head", .label x), ("tail", tail)])) (.variant "nil" (.record []))
private def withList (xs : List String) (by_ : String) : Data :=
  .record [("entries", lst xs), ("lastBy", .label by_), ("count", .natural 1)]

#guard denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", []⟩ none (withList [] "kim") (parsed "new.lastBy == request.subject")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", []⟩ none (withList [] "bob") (parsed "new.lastBy == request.subject")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", []⟩ none (withList [] "kim") (parsed "new.entries == request.subject")
#guard denote ⟨"7", "", 1, 0, "", 0, "", [], 0, "", []⟩ none (.record [("n", .natural 7)]) (parsed "new.n == request.subject")
#guard denote facts (some (withList ["a"] "x")) (withList ["a", "b", "c"] "x") (parsed "appendOnly(entries)")
#guard denote facts (some (withList ["a"] "x")) (withList ["a"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a", "b"] "x")) (withList ["a", "c"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a", "b"] "x")) (withList ["a"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a"] "x")) (rec1 3) (parsed "appendOnly(entries)")
#guard denote facts (some (withList ["a"] "x")) (withList ["a"] "y") (parsed "unchanged(entries)")
#guard !denote facts (some (withList ["a"] "x")) (withList ["a"] "y") (parsed "unchanged(lastBy)")
#guard !denote facts (some (withList ["a"] "x")) (withList ["a", "b"] "x") (parsed "unchanged(entries)")
#guard denote facts (some (rec1 3)) (.record [("open", .boolean true), ("count", .natural 3)]) (parsed "new.count == 3")
#guard denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", []⟩ none (withList ["ann", "kim"] "x") (parsed "request.subject in new.entries")
#guard !denote ⟨"bob", "", 1, 0, "", 0, "", [], 0, "", []⟩ none (withList ["ann", "kim"] "x") (parsed "request.subject in new.entries")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", []⟩ none (withList ["ann", "kim"] "x") (parsed "request.subject in new.lastBy")
#guard denote ⟨"a", "forge", 1, 0, "", 0, "", [], 0, "", []⟩ none (withList ["forge"] "x") (parsed "request.caller in new.entries")
#guard denote ⟨"a", "", 1, 0, "", 0, "ring", [], 0, "", []⟩ none (rec1 1) (parsed "request.method == \"ring\"")
#guard !denote ⟨"a", "", 1, 0, "", 0, "toll", [], 0, "", []⟩ none (rec1 1) (parsed "request.method == \"ring\"")
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
#guard denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", []⟩ none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "request.subject in new.rains.author")
#guard !denote ⟨"bob", "", 1, 0, "", 0, "", [], 0, "", []⟩ none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "request.subject in new.rains.author")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", [], 0, "", []⟩ none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "request.subject in new.rains.text")
#guard denote ⟨"a", "forge", 1, 0, "", 0, "", [], 0, "", []⟩ none (rel [rain "forge" 1 "a"]) (parsed "request.caller in new.rains.author")

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
#guard !denote (kindOf "law small: new.count <= 2") none (rec1 2) (parsed "under \"kind/x\"") 0
#guard !denote (kindOf "law loop: under \"kind/x\"") none (rec1 2) (parsed "under \"kind/x\"")
#guard !denote (kindOf "not a law") none (rec1 2) (parsed "under \"kind/x\"")
#guard !denote facts none (rec1 2) (parsed "under \"kind/x\"")

end Delvetalk.Host.Law
