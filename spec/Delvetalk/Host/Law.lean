/- Meaning of the enforced law fragment (`Compiler/ObjectiveBendLaw.lean`) over
   old and new state `Data` plus request facts. Ported from Mini's
   `Kernel/ObjectLaw.lean` `LawExpr.denote`; the one extension is that a
   principal is text: `subject` and `caller` read as a number when the principal
   is a decimal numeral and as text otherwise, so `request.subject ==
   request.caller` holds for any principal while order and constants need
   numerals. Absent or mistyped readings fail closed. -/
import Delvetalk.Host.Store
import Delvetalk.Canonical
import Compiler.ObjectiveBendDataWire

namespace Delvetalk.Host.Law
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Compiler.ObjectiveBendLaw (LawExpr LawRef)

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
  /-- The relations the object's code declares: `insertOnly` does not count a row its declared
      retention dropped. -/
  relations : List RelDecl := []

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
def canon (d : Data) : String := (Minidregg.Compiler.ObjectiveBendDataWire.dataJson d).compress

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

/-- The canonical bytes of a row's key under `d`, none when a key column is missing. -/
def keyBytes (d : RelDecl) (row : Data) : Option ByteArray :=
  match row with
  | .record cols => (d.key.mapM fun k => (cols.lookup k).map (k, ·)).map fun ks => Delvetalk.Canonical.encode (.record ks)
  | _ => none

/-- Was `row` dropped by the declared retention of relation `field`, which now holds `after`? The
    relation is full (`RelDecl.cap`) and the row's key sorts before every kept key (the first rows
    in key order go), so no row with its key is kept: an altered row keeps its key and counts. -/
def retentionDropped (decls : List RelDecl) (field : String) (after : List Data) (row : Data) : Bool :=
  match decls.find? (·.field == field) with
  | none => false
  | some d =>
    after.length == d.cap &&
    match keyBytes d row, after.mapM (keyBytes d) with
    | some k, some kept => kept.all fun c => bytesLt k c
    | _, _ => false

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

def read (facts : Facts) (new : Data) : LawRef → Option Reading
  | .field name => (rawField name new).bind fun
      | .label s => some (.text s)
      | d => (scalarOf d).map .num
  | .subject => some (principalReading facts.subject)
  | .caller => some (principalReading facts.caller)
  | .height => some (.num facts.height)
  | .turn => some (.num facts.turn)
  | .pin => some (.text facts.pin)
  | .kind => some (.num facts.kind)
  | .method => some (.text facts.method)

def number (reading : Option Reading) : Option Int :=
  match reading with
  | some (.num n) => some n
  | _ => none

/-- Text form for comparing a numeral principal with a numeric reading. -/
def Reading.render : Reading → String
  | .num n => toString n
  | .text s => s

def denote (facts : Facts) (old : Option Data) (new : Data) : LawExpr → Bool
  | .eqC ref value => number (read facts new ref) == some value
  | .leC ref value => match number (read facts new ref) with
      | some x => decide (x ≤ value)
      | none => false
  | .eqS ref text => match ref with
      | .subject => facts.subject == text
      | .caller => facts.caller == text
      | .pin => facts.pin == text
      | .method => facts.method == text
      | _ => false
  | .inC ref values => match number (read facts new ref) with
      | some x => values.contains x
      | none => false
  | .eqR left right => match read facts new left, read facts new right with
      | some x, some y => x == y || x.render == y.render
      | _, _ => false
  | .leR left right => match number (read facts new left), number (read facts new right) with
      | some x, some y => decide (x ≤ y)
      | _, _ => false
  | .leROff left right offset => match number (read facts new left), number (read facts new right) with
      | some x, some y => decide (x ≤ y + offset)
      | _, _ => false
  | .monotone field => match old.bind (fieldOf field), fieldOf field new with
      | some before, some after => decide (before ≤ after)
      | _, _ => false
  | .writeOnce field => match old with
      | none => true
      | some before => match rawField field before, rawField field new with
        | some a, some b => emptyValue a || canon a == canon b
        | _, _ => false
  | .appendOnly field => match old with
      | none => (listItems [] ((rawField field new).getD (.boolean false))).isSome
      | some before => match (rawField field before).bind (listItems []),
          (rawField field new).bind (listItems []) with
        | some a, some b => isPrefix a b
        | _, _ => false
  | .unchanged field => match old with
      | none => true
      | some before => match rawField field before, rawField field new with
        | some a, some b => canon a == canon b
        | _, _ => false
  | .member ref field =>
    let who := match ref with
      | .subject => some facts.subject
      | .caller => some facts.caller
      | _ => none
    match who, (rawField field new).bind (listItems []) with
    | some w, some items => items.contains (canon (.label w))
    | _, _ => false
  -- Relations (RELATIONAL §5). Rows are compared whole by canonical bytes: a relation holds no
  -- key twice, so "every old row is in new" is "new ⊇ old by key, every old row unchanged".
  -- A row the declared retention dropped (`dropOldest`: the relation is full and the row's key
  -- sorts before every key it kept) was not retracted by the write, so it does not count.
  | .insertOnly field => match (rawField field new).bind rowsOf with
    | none => false
    | some after => match old with
      | none => true
      | some before => match (rawField field before).bind rowsOf with
        | some rows =>
          let now := after.map canon
          rows.all fun r => now.contains (canon r) || retentionDropped facts.relations field after r
        | none => false
  | .countLe field bound => match (rawField field new).bind rowsOf with
    | some rows => decide ((rows.length : Int) ≤ bound)
    | none => false
  -- At creation there is no old relation: it counts as empty.
  | .countGrowth field offset =>
    let before := match old with
      | none => some 0
      | some o => ((rawField field o).bind rowsOf).map (·.length)
    match before, ((rawField field new).bind rowsOf).map (·.length) with
    | some b, some a => decide ((a : Int) ≤ b + offset)
    | _, _ => false
  | .memberColumn ref field column =>
    let who := match ref with
      | .subject => some facts.subject
      | .caller => some facts.caller
      | _ => none
    match who, (rawField field new).bind rowsOf with
    | some w, some rows => rows.any fun r => (rawField column r).map canon == some (canon (.label w))
    | _, _ => false
  | .not body => !denote facts old new body
  | .and left right => denote facts old new left && denote facts old new right
  | .or left right => denote facts old new left || denote facts old new right
  | .implies premise conclusion => !denote facts old new premise || denote facts old new conclusion

/-- A clause that reads a non-plain field name refuses every write. -/
def admits (facts : Facts) (old : Option Data) (new : Data) (clause : LawExpr) : Bool :=
  clause.fieldsPlain && denote facts old new clause

/-- The first law, in source order, that refuses this write. -/
def refusedBy (law : Law) (facts : Facts) (old : Option Data) (new : Data) : Option String :=
  (law.find? fun (_, clause) => !admits facts old new clause).map Prod.fst

/-! Small tests. Parsed laws go through the real parser. -/

private def parsed (text : String) : LawExpr :=
  match Minidregg.Compiler.ObjectiveBendLaw.parse text with
  | .ok e => e
  | .error _ => .or (.eqC .height 0) (.not (.eqC .height 0))

private def rec1 (n : Nat) : Data := .record [("count", .natural n), ("open", .boolean true)]
private def facts : Facts := ⟨"7", "7", 3, 0, "", 0, "", []⟩

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
#guard !denote ⟨"a", "b", 1, 0, "", 0, "", []⟩ none (rec1 3) (parsed "request.subject == request.caller")
#guard denote facts none (rec1 3) (parsed "request.height == 3")
#guard denote ⟨"a", "a", 1, 0, "", 2, "", []⟩ none (rec1 3) (parsed "request.kind == 2")
#guard !denote facts none (rec1 3) (parsed "request.kind == 1")
#guard !denote ⟨"a", "a", 1, 0, "", proposedKind, "", []⟩ none (rec1 3) (parsed "request.kind == 0 or request.subject == \"b\"")
#guard denote ⟨"a", "a", 1, 0, "", proposedKind, "", []⟩ none (rec1 3) (parsed "request.kind == 3")
#guard denote facts none (rec1 3) (parsed "request.subject == \"7\"")
#guard denote ⟨"ember", "ember", 1, 0, "abc", 0, "", []⟩ none (rec1 3) (parsed "request.subject == \"ember\" and request.pin == \"abc\"")
#guard !denote ⟨"kim", "kim", 1, 0, "abc", 0, "", []⟩ none (rec1 3) (parsed "request.subject == \"ember\"")
#guard !denote facts none (rec1 3) (parsed "request.subject == \"ember\"")
#guard denote facts none (rec1 3) (parsed "request.subject == 7")
#guard !denote ⟨"ember", "ember", 1, 0, "", 0, "", []⟩ none (rec1 3) (parsed "request.subject == 7")
#guard denote facts none (rec1 3) (parsed "new.open == 1 and not new.count <= 2")
#guard denote facts none (rec1 3) (parsed "new.count <= 2 implies new.open == 0")
#guard !denote facts none (rec1 3) (parsed "new.missing == 0")
private def lst (xs : List String) : Data :=
  xs.foldr (fun x tail => .variant "cons" (.record [("head", .label x), ("tail", tail)])) (.variant "nil" (.record []))
private def withList (xs : List String) (by_ : String) : Data :=
  .record [("entries", lst xs), ("lastBy", .label by_), ("count", .natural 1)]

#guard denote ⟨"kim", "", 1, 0, "", 0, "", []⟩ none (withList [] "kim") (parsed "new.lastBy == request.subject")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", []⟩ none (withList [] "bob") (parsed "new.lastBy == request.subject")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", []⟩ none (withList [] "kim") (parsed "new.entries == request.subject")
#guard denote ⟨"7", "", 1, 0, "", 0, "", []⟩ none (.record [("n", .natural 7)]) (parsed "new.n == request.subject")
#guard denote facts (some (withList ["a"] "x")) (withList ["a", "b", "c"] "x") (parsed "appendOnly(entries)")
#guard denote facts (some (withList ["a"] "x")) (withList ["a"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a", "b"] "x")) (withList ["a", "c"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a", "b"] "x")) (withList ["a"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a"] "x")) (rec1 3) (parsed "appendOnly(entries)")
#guard denote facts (some (withList ["a"] "x")) (withList ["a"] "y") (parsed "unchanged(entries)")
#guard !denote facts (some (withList ["a"] "x")) (withList ["a"] "y") (parsed "unchanged(lastBy)")
#guard !denote facts (some (withList ["a"] "x")) (withList ["a", "b"] "x") (parsed "unchanged(entries)")
#guard denote facts (some (rec1 3)) (.record [("open", .boolean true), ("count", .natural 3)]) (parsed "new.count == 3")
#guard denote ⟨"kim", "", 1, 0, "", 0, "", []⟩ none (withList ["ann", "kim"] "x") (parsed "request.subject in new.entries")
#guard !denote ⟨"bob", "", 1, 0, "", 0, "", []⟩ none (withList ["ann", "kim"] "x") (parsed "request.subject in new.entries")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", []⟩ none (withList ["ann", "kim"] "x") (parsed "request.subject in new.lastBy")
#guard denote ⟨"a", "forge", 1, 0, "", 0, "", []⟩ none (withList ["forge"] "x") (parsed "request.caller in new.entries")
#guard denote ⟨"a", "", 1, 0, "", 0, "ring", []⟩ none (rec1 1) (parsed "request.method == \"ring\"")
#guard !denote ⟨"a", "", 1, 0, "", 0, "toll", []⟩ none (rec1 1) (parsed "request.method == \"ring\"")
#guard (Minidregg.Compiler.ObjectiveBendLaw.parse "request.height in new.entries").toBool == false
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
-- Retention: with `limit: 2` keyed by `at`, a full relation drops its first row by key; that row
-- does not count against insertOnly, but a retraction or an alteration still does.
private def limited : Facts := { facts with relations := [{ field := "rains", key := ["at"], limit := 2 }] }
#guard denote limited (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "kim" 2 "b", rain "eve" 3 "c"]) (parsed "insertOnly(rains)")
#guard !denote facts (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "kim" 2 "b", rain "eve" 3 "c"]) (parsed "insertOnly(rains)")
#guard !denote limited (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "ann" 1 "a"]) (parsed "insertOnly(rains)")
#guard !denote limited (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "ann" 1 "a", rain "eve" 3 "c"]) (parsed "insertOnly(rains)")
#guard !denote limited (some (rel [rain "ann" 1 "a", rain "kim" 2 "b"])) (rel [rain "ann" 1 "x", rain "kim" 2 "b"]) (parsed "insertOnly(rains)")
#guard denote facts none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "count(new.rains) <= 2")
#guard !denote facts none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "count(new.rains) <= 1")
#guard denote facts (some (rel [rain "ann" 1 "a"])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "count(new.rains) <= count(old.rains) + 1")
#guard !denote facts (some (rel [])) (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "count(new.rains) <= count(old.rains) + 1")
#guard denote facts none (rel [rain "ann" 1 "a"]) (parsed "count(new.rains) <= count(old.rains) + 1")
#guard denote ⟨"kim", "", 1, 0, "", 0, "", []⟩ none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "request.subject in new.rains.author")
#guard !denote ⟨"bob", "", 1, 0, "", 0, "", []⟩ none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "request.subject in new.rains.author")
#guard !denote ⟨"kim", "", 1, 0, "", 0, "", []⟩ none (rel [rain "ann" 1 "a", rain "kim" 2 "b"]) (parsed "request.subject in new.rains.text")
#guard denote ⟨"a", "forge", 1, 0, "", 0, "", []⟩ none (rel [rain "forge" 1 "a"]) (parsed "request.caller in new.rains.author")

end Delvetalk.Host.Law
