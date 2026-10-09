/- Meaning of the enforced law fragment (`Compiler/ObjectiveBendLaw.lean`) over
   old and new state `Data` plus request facts. Ported from Mini's
   `Kernel/ObjectLaw.lean` `LawExpr.denote`; the one extension is that a
   principal is text: `subject` and `caller` read as a number when the principal
   is a decimal numeral and as text otherwise, so `request.subject ==
   request.caller` holds for any principal while order and constants need
   numerals. Absent or mistyped readings fail closed. -/
import Delvetalk.Host.Store

namespace Delvetalk.Host.Law
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Compiler.ObjectiveBendLaw (LawExpr LawRef)

structure Facts where
  subject : String
  caller : String
  height : Nat
  turn : Nat

inductive Reading where
  | num (n : Int)
  | text (s : String)
  deriving BEq

def scalarOf : Data → Option Int
  | .natural n => some (Int.ofNat n)
  | .boolean b => some (if b then 1 else 0)
  | _ => none

/-- The first scalar field called `name` of a record. -/
def firstScalar (name : String) : List (String × Data) → Option Int
  | [] => none
  | (field, value) :: rest =>
      if field == name then (scalarOf value).orElse fun _ => firstScalar name rest
      else firstScalar name rest

def fieldOf (name : String) : Data → Option Int
  | .record fields => firstScalar name fields
  | _ => none

def principalReading (principal : String) : Reading :=
  if !principal.isEmpty && principal.all Char.isDigit then
    match principal.toNat? with
    | some n => .num n
    | none => .text principal
  else .text principal

def read (facts : Facts) (new : Data) : LawRef → Option Reading
  | .field name => (fieldOf name new).map .num
  | .subject => some (principalReading facts.subject)
  | .caller => some (principalReading facts.caller)
  | .height => some (.num facts.height)
  | .turn => some (.num facts.turn)

def number (reading : Option Reading) : Option Int :=
  match reading with
  | some (.num n) => some n
  | _ => none

def denote (facts : Facts) (old : Option Data) (new : Data) : LawExpr → Bool
  | .eqC ref value => number (read facts new ref) == some value
  | .leC ref value => match number (read facts new ref) with
      | some x => decide (x ≤ value)
      | none => false
  | .inC ref values => match number (read facts new ref) with
      | some x => values.contains x
      | none => false
  | .eqR left right => match read facts new left, read facts new right with
      | some x, some y => x == y
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
private def facts : Facts := ⟨"7", "7", 3, 0⟩

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
#guard !denote ⟨"a", "b", 1, 0⟩ none (rec1 3) (parsed "request.subject == request.caller")
#guard denote facts none (rec1 3) (parsed "request.height == 3")
#guard denote facts none (rec1 3) (parsed "request.subject == 7")
#guard !denote ⟨"ember", "ember", 1, 0⟩ none (rec1 3) (parsed "request.subject == 7")
#guard denote facts none (rec1 3) (parsed "new.open == 1 and not new.count <= 2")
#guard denote facts none (rec1 3) (parsed "new.count <= 2 implies new.open == 0")
#guard !denote facts none (rec1 3) (parsed "new.missing == 0")
#guard refusedBy [("a", parsed "new.count <= 5"), ("b", parsed "new.count <= 2")] facts none (rec1 3) == some "b"

end Delvetalk.Host.Law
