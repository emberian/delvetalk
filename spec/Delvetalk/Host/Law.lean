/- Meaning of the enforced law fragment (`Compiler/ObjectiveBendLaw.lean`) over
   old and new state `Data` plus request facts. Ported from Mini's
   `Kernel/ObjectLaw.lean` `LawExpr.denote`; the one extension is that a
   principal is text: `subject` and `caller` read as a number when the principal
   is a decimal numeral and as text otherwise, so `request.subject ==
   request.caller` holds for any principal while order and constants need
   numerals. Absent or mistyped readings fail closed. -/
import Delvetalk.Host.Store
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
  /-- 0 write, 1 reprogram, 2 amend. -/
  kind : Nat := 0

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
  | .writeOnce field => match old.bind (fieldOf field) with
      | none => true
      | some before => before == 0 || fieldOf field new == some before
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
private def facts : Facts := ⟨"7", "7", 3, 0, "", 0⟩

#guard denote facts (some (rec1 3)) (rec1 4) (parsed "monotone(count)")
#guard !denote facts (some (rec1 3)) (rec1 2) (parsed "monotone(count)")
#guard !denote facts none (rec1 2) (parsed "monotone(count)")
#guard denote facts none (rec1 2) (parsed "writeOnce(count)")
#guard !denote facts (some (rec1 3)) (rec1 4) (parsed "writeOnce(count)")
#guard denote facts (some (rec1 0)) (rec1 4) (parsed "writeOnce(count)")
#guard denote facts none (rec1 2) (parsed "new.count <= 2")
#guard !denote facts none (rec1 3) (parsed "new.count <= 2")
#guard denote facts none (rec1 3) (parsed "new.count in [1, 3]")
#guard denote facts none (rec1 3) (parsed "request.subject == request.caller")
#guard !denote ⟨"a", "b", 1, 0, "", 0⟩ none (rec1 3) (parsed "request.subject == request.caller")
#guard denote facts none (rec1 3) (parsed "request.height == 3")
#guard denote ⟨"a", "a", 1, 0, "", 2⟩ none (rec1 3) (parsed "request.kind == 2")
#guard !denote facts none (rec1 3) (parsed "request.kind == 1")
#guard denote facts none (rec1 3) (parsed "request.subject == \"7\"")
#guard denote ⟨"ember", "ember", 1, 0, "abc", 0⟩ none (rec1 3) (parsed "request.subject == \"ember\" and request.pin == \"abc\"")
#guard !denote ⟨"kim", "kim", 1, 0, "abc", 0⟩ none (rec1 3) (parsed "request.subject == \"ember\"")
#guard !denote facts none (rec1 3) (parsed "request.subject == \"ember\"")
#guard denote facts none (rec1 3) (parsed "request.subject == 7")
#guard !denote ⟨"ember", "ember", 1, 0, "", 0⟩ none (rec1 3) (parsed "request.subject == 7")
#guard denote facts none (rec1 3) (parsed "new.open == 1 and not new.count <= 2")
#guard denote facts none (rec1 3) (parsed "new.count <= 2 implies new.open == 0")
#guard !denote facts none (rec1 3) (parsed "new.missing == 0")
private def lst (xs : List String) : Data :=
  xs.foldr (fun x tail => .variant "cons" (.record [("head", .label x), ("tail", tail)])) (.variant "nil" (.record []))
private def withList (xs : List String) (by_ : String) : Data :=
  .record [("entries", lst xs), ("lastBy", .label by_), ("count", .natural 1)]

#guard denote ⟨"kim", "", 1, 0, "", 0⟩ none (withList [] "kim") (parsed "new.lastBy == request.subject")
#guard !denote ⟨"kim", "", 1, 0, "", 0⟩ none (withList [] "bob") (parsed "new.lastBy == request.subject")
#guard !denote ⟨"kim", "", 1, 0, "", 0⟩ none (withList [] "kim") (parsed "new.entries == request.subject")
#guard denote ⟨"7", "", 1, 0, "", 0⟩ none (.record [("n", .natural 7)]) (parsed "new.n == request.subject")
#guard denote facts (some (withList ["a"] "x")) (withList ["a", "b", "c"] "x") (parsed "appendOnly(entries)")
#guard denote facts (some (withList ["a"] "x")) (withList ["a"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a", "b"] "x")) (withList ["a", "c"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a", "b"] "x")) (withList ["a"] "x") (parsed "appendOnly(entries)")
#guard !denote facts (some (withList ["a"] "x")) (rec1 3) (parsed "appendOnly(entries)")
#guard denote facts (some (withList ["a"] "x")) (withList ["a"] "y") (parsed "unchanged(entries)")
#guard !denote facts (some (withList ["a"] "x")) (withList ["a"] "y") (parsed "unchanged(lastBy)")
#guard !denote facts (some (withList ["a"] "x")) (withList ["a", "b"] "x") (parsed "unchanged(entries)")
#guard denote facts (some (rec1 3)) (.record [("open", .boolean true), ("count", .natural 3)]) (parsed "new.count == 3")
#guard refusedBy [("a", parsed "new.count <= 5"), ("b", parsed "new.count <= 2")] facts none (rec1 3) == some "b"

end Delvetalk.Host.Law
