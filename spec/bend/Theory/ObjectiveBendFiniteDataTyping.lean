import Theory.ObjectiveBendFiniteData
import Theory.ObjectiveBendTyping
namespace Minidregg.Theory.ObjectiveBendDemandData
open ObjectiveBendTypes ObjectiveBendTyping ObjectiveBendOpenRecursion
set_option autoImplicit false

/- Proof-only admission evidence. Neither the literal erasure nor this evidence
is needed in the executable heap representation. -/
mutual
inductive Admitted (a : Assumptions) : Data → Ty → Prop where
  | natural (n : Nat) : Admitted a (.natural n) .natural
  | boolean (b : Bool) : Admitted a (.boolean b) .boolean
  | label (s : String) : Admitted a (.label s) .label
  | record {fields : List (String × Data)} {row : Ty} :
      AdmittedFields a fields row → Admitted a (.record fields) row
  | variant {tag : String} {payload : Data} {payloadTy row : Ty} {fuel : Nat} :
      Admitted a payload payloadTy → row.lookup a.bounds fuel tag = some payloadTy →
      payloadTy.isComputation = false → Admitted a (.variant tag payload) (.variant row)
  | conversion {data : Data} {actual expected : Ty} :
      Admitted a data actual → sameType a actual expected = true → Admitted a data expected
inductive AdmittedFields (a : Assumptions) : List (String × Data) → Ty → Prop where
  | nil : AdmittedFields a [] .emptyRow
  | cons {name : String} {value : Data} {rest : List (String × Data)} {member row : Ty} :
      Admitted a value member → AdmittedFields a rest row → member.isComputation = false →
      AdmittedFields a ((name,value)::rest) (.field name member row)
end

theorem Admitted.typing {a : Assumptions} {data : Data} {ty : Ty}
    (h : Admitted a data ty) : PartialTyping a [] data.term ty [] := by
  induction h using Admitted.rec
      (motive_2 := fun fields row _ => FieldsTyping a [] (fieldsTerm fields) row []) with
  | natural n => exact .natural [] n
  | boolean b => exact .boolean [] b
  | label s => exact .label [] s
  | record _ ih => exact .record ih
  | variant _ lookup pure ih => exact .inject ih lookup pure
  | conversion _ agreement ih => exact .conversion ih agreement
  | nil => exact .nil []
  | cons _ _ pure valueIH restIH => exact .cons valueIH restIH pure

theorem checked_closed_uses {source : AnnotatedTerm} (checked : Checked source []) :
    checked.uses = [] := by
  cases huses : checked.uses with
  | nil => rfl
  | cons head tail =>
      have h := checked.safe
      simp [safeUses, huses] at h

theorem transparent_sum_conversion {a : Assumptions} {index : Nat} {row : Ty}
    (alias : a.alias index = some (.variant row)) :
    sameType a (.variant row) (.variable index) = true := by
  simp [sameType, alias, Ty.isComputation]

/-- The application rule retains the actual quantity/capture gate. A finite
native argument cannot supply a computation, closure, or executable capture. -/
theorem Admitted.application {a : Assumptions} {function : Term} {data : Data}
    {functionTy domain codomain : Ty} {uses : Uses} {reuse : Reuse} {quantity : Quantity}
    (functionTyped : PartialTyping a [] function functionTy uses)
    (argumentTyped : Admitted a data domain)
    (arrow : callable functionTy = .arrow reuse quantity domain codomain)
    (allowed : argumentAllowed a quantity [] domain [] = true) :
    PartialTyping a [] (.app function data.term) codomain (addUses uses []) :=
  .application functionTyped argumentTyped.typing arrow rfl allowed

inductive AdmittedArguments (a : Assumptions) : Ty → List Data → Ty → Prop where
  | nil (ty : Ty) : AdmittedArguments a ty [] ty
  | cons {functionTy domain codomain result : Ty} {reuse : Reuse} {quantity : Quantity}
      {data : Data} {rest : List Data} :
      callable functionTy = .arrow reuse quantity domain codomain →
      Admitted a data domain → argumentAllowed a quantity [] domain [] = true →
      AdmittedArguments a codomain rest result →
      AdmittedArguments a functionTy (data::rest) result

/-- Literal applications occur only in the proof/reference view. -/
def literalApplications (function : Term) (arguments : List Data) : Term :=
  arguments.foldl (fun function argument => .app function argument.term) function

theorem AdmittedArguments.typing {a : Assumptions} {functionTy result : Ty}
    {arguments : List Data} (admitted : AdmittedArguments a functionTy arguments result)
    {function : Term} (typed : PartialTyping a [] function functionTy []) :
    PartialTyping a [] (literalApplications function arguments) result [] := by
  induction admitted generalizing function with
  | nil ty => exact typed
  | cons arrow data allowed rest ih =>
      apply ih
      exact Admitted.application typed data arrow allowed

/-- Finite closed rows have the same first-match lookup as their source list.
The linear row-depth bound is established once, not rescanned for every value. -/
def finiteRow : List (String × Ty) → Ty
  | [] => .emptyRow
  | (name,ty)::rest => .field name ty (finiteRow rest)

theorem finiteRow_lookup (bounds : Bounds) (members : List (String × Ty)) (name : String) :
    (finiteRow members).lookup bounds (members.length + 1) name = members.lookup name := by
  induction members with
  | nil => simp [finiteRow, Ty.lookup]
  | cons head rest ih =>
      rcases head with ⟨label,ty⟩
      simp only [finiteRow, List.length_cons, Ty.lookup, ih, List.lookup]
      by_cases h : label = name
      · subst label; simp
      · simp [h, show (name == label) = false from beq_eq_false_iff_ne.mpr (Ne.symm h)]
end Minidregg.Theory.ObjectiveBendDemandData
