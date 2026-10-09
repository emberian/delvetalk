import Theory.ObjectiveBendFiniteData
import Theory.ObjectiveBendTyping
namespace Minidregg.Theory.ObjectiveBendDemandData
open ObjectiveBendTypes ObjectiveBendTyping ObjectiveBendOpenRecursion
set_option autoImplicit false

/- Proof-only literal view of finite data: the closed literal syntax of a value,
possibly wrapped (at any depth) in the administrative `toData` injection, which
steps to its operand (`Step.toData`) and is erased by the machine. -/
mutual
inductive Literal : Term → Data → Prop where
  | natural (n : Nat) : Literal (.nat n) (.natural n)
  | boolean (b : Bool) : Literal (.boolean b) (.boolean b)
  | label (s : String) : Literal (.label s) (.label s)
  | record {terms : List (String × Term)} {fields : List (String × Data)} :
      LiteralFields terms fields → Literal (.record terms) (.record fields)
  | inject {tag : String} {term : Term} {payload : Data} :
      Literal term payload → Literal (.inject tag term) (.variant tag payload)
  | toData {term : Term} {data : Data} : Literal term data → Literal (.toData term) data
inductive LiteralFields : List (String × Term) → List (String × Data) → Prop where
  | nil : LiteralFields [] []
  | cons {name : String} {term : Term} {value : Data} {terms : List (String × Term)}
      {fields : List (String × Data)} :
      Literal term value → LiteralFields terms fields →
      LiteralFields ((name,term) :: terms) ((name,value) :: fields)
end

mutual
theorem Data.term_literal : (data : Data) → Literal data.term data
  | .natural n => .natural n
  | .boolean b => .boolean b
  | .label s => .label s
  | .record fields => .record (fieldsTerm_literal fields)
  | .variant _ payload => .inject payload.term_literal
theorem fieldsTerm_literal : (fields : List (String × Data)) → LiteralFields (fieldsTerm fields) fields
  | [] => .nil
  | (_, value) :: rest => .cons value.term_literal (fieldsTerm_literal rest)
end

/- The singleton type of closed data: records at their own row, each variant at
the one-label sum naming exactly its own label. A value of the universal type
`Data` is checked at this type inside its `toData` injection. -/
mutual
def Data.shapeType : Data → Ty
  | .natural _ => .natural
  | .boolean _ => .boolean
  | .label _ => .label
  | .record fields => Data.shapeFields fields
  | .variant tag payload => .variant (.field tag payload.shapeType .emptyRow)
def Data.shapeFields : List (String × Data) → Ty
  | [] => .emptyRow
  | (name, value) :: rest => .field name value.shapeType (Data.shapeFields rest)
end

/- Walk fuel that suffices for `isDataUnder` over a shape type. -/
mutual
def Data.shapeSize : Data → Nat
  | .natural _ | .boolean _ | .label _ => 1
  | .record fields => Data.shapeFieldsSize fields
  | .variant _ payload => payload.shapeSize + 2
def Data.shapeFieldsSize : List (String × Data) → Nat
  | [] => 1
  | (_, value) :: rest => value.shapeSize + Data.shapeFieldsSize rest + 1
end

theorem Data.shapeFieldsSize_pos : (fields : List (String × Data)) → 1 ≤ Data.shapeFieldsSize fields
  | [] => by simp [Data.shapeFieldsSize]
  | (_, _) :: _ => by simp [Data.shapeFieldsSize]

theorem Data.shapeSize_pos : (data : Data) → 1 ≤ data.shapeSize
  | .natural _ | .boolean _ | .label _ => by simp [Data.shapeSize]
  | .record fields => by simpa [Data.shapeSize] using Data.shapeFieldsSize_pos fields
  | .variant _ _ => by simp [Data.shapeSize]

theorem Data.shapeType_not_computation (data : Data) : data.shapeType.isComputation = false := by
  cases data with
  | record fields => cases fields <;> simp [Data.shapeType, Data.shapeFields, Ty.isComputation]
  | _ => simp [Data.shapeType, Ty.isComputation]

mutual
theorem Data.shapeType_isData (bounds : DataBounds) (rigid : List Nat) :
    (data : Data) → (fuel : Nat) → (seen : List Nat) → data.shapeSize ≤ fuel →
      data.shapeType.isDataUnder bounds rigid fuel seen = true
  | .natural _, fuel + 1, _, _ => by simp [Data.shapeType, Ty.isDataUnder]
  | .boolean _, fuel + 1, _, _ => by simp [Data.shapeType, Ty.isDataUnder]
  | .label _, fuel + 1, _, _ => by simp [Data.shapeType, Ty.isDataUnder]
  | .natural _, 0, _, h | .boolean _, 0, _, h | .label _, 0, _, h => by simp [Data.shapeSize] at h
  | .record fields, fuel, seen, h => by
      simpa [Data.shapeType] using Data.shapeFields_isData bounds rigid fields fuel seen (by simpa [Data.shapeSize] using h)
  | .variant _ payload, fuel + 2, seen, h => by
      have p := Data.shapeType_isData bounds rigid payload fuel seen (by simp [Data.shapeSize] at h; omega)
      have one := Data.shapeSize_pos payload
      simp [Data.shapeSize] at h
      obtain ⟨f, rfl⟩ : ∃ f, fuel = f + 1 := ⟨fuel - 1, by omega⟩
      simp [Data.shapeType, Ty.isDataUnder, p]
  | .variant _ _, 0, _, h | .variant _ _, 1, _, h => by simp [Data.shapeSize] at h
theorem Data.shapeFields_isData (bounds : DataBounds) (rigid : List Nat) :
    (fields : List (String × Data)) → (fuel : Nat) → (seen : List Nat) → Data.shapeFieldsSize fields ≤ fuel →
      (Data.shapeFields fields).isDataUnder bounds rigid fuel seen = true
  | [], fuel + 1, _, _ => by simp [Data.shapeFields, Ty.isDataUnder]
  | (_, value) :: rest, fuel + 1, seen, h => by
      simp [Data.shapeFieldsSize] at h
      simp [Data.shapeFields, Ty.isDataUnder,
        Data.shapeType_isData bounds rigid value fuel seen (by omega),
        Data.shapeFields_isData bounds rigid rest fuel seen (by omega)]
  | [], 0, _, h | _ :: _, 0, _, h => by simp [Data.shapeFieldsSize] at h
end

mutual
/-- Every finite value has a literal typed at its own shape. -/
theorem Data.shape_typing (a : Assumptions) :
    (data : Data) → ∃ term, Literal term data ∧ PartialTyping a [] term data.shapeType []
  | .natural n => ⟨_, .natural n, .natural [] n⟩
  | .boolean b => ⟨_, .boolean b, .boolean [] b⟩
  | .label s => ⟨_, .label s, .label [] s⟩
  | .record fields => by
      obtain ⟨terms, literal, typed⟩ := Data.shapeFields_typing a fields
      exact ⟨_, .record literal, .record typed⟩
  | .variant tag payload => by
      obtain ⟨term, literal, typed⟩ := Data.shape_typing a payload
      refine ⟨_, .inject literal, .inject (fuel := 1) typed ?_ (Data.shapeType_not_computation payload)⟩
      simp [Ty.lookup]
theorem Data.shapeFields_typing (a : Assumptions) :
    (fields : List (String × Data)) →
      ∃ terms, LiteralFields terms fields ∧ FieldsTyping a [] terms (Data.shapeFields fields) []
  | [] => ⟨_, .nil, .nil []⟩
  | (name, value) :: rest => by
      obtain ⟨term, literal, typed⟩ := Data.shape_typing a value
      obtain ⟨terms, literals, typedRest⟩ := Data.shapeFields_typing a rest
      exact ⟨_, .cons literal literals, .cons typed typedRest (Data.shapeType_not_computation value)⟩
end

mutual
/-- Injection annotations of a closed value checked at its own shape
(`Data.shapeType`): each variant at the one-label sum naming its label. Paths
are relative to the value (an injection's payload is child 0, field `i` child `i`). -/
def shapeAnnotations : Data → List Nat → List (List Nat × LambdaAnnotation)
  | .variant tag payload, path =>
    (path, ⟨payload.shapeType, (Data.variant tag payload).shapeType, .unrestricted, .reusable⟩) ::
      shapeAnnotations payload (path ++ [0])
  | .record fields, path => shapeFieldAnnotations fields path 0
  | _, _ => []
def shapeFieldAnnotations : List (String × Data) → List Nat → Nat → List (List Nat × LambdaAnnotation)
  | [], _, _ => []
  | (_, value) :: rest, path, index =>
    shapeAnnotations value (path ++ [index]) ++ shapeFieldAnnotations rest path (index + 1)
end

/-- Every finite value, injected by `toData`, has the universal type. -/
theorem Data.universal_typing (a : Assumptions) (data : Data) :
    ∃ term, Literal term data ∧ PartialTyping a [] term .data [] := by
  obtain ⟨term, literal, typed⟩ := Data.shape_typing a data
  exact ⟨_, .toData literal,
    .toData typed (Data.shapeType_isData a.bounds a.rigid data data.shapeSize [] (Nat.le_refl _))⟩

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
  /-- The universal type admits exactly the well-formed values
  (`Data.conformsUnder _ _ .data` is `wellFormed`). -/
  | universal {data : Data} : data.wellFormed = true → Admitted a data .data
inductive AdmittedFields (a : Assumptions) : List (String × Data) → Ty → Prop where
  | nil : AdmittedFields a [] .emptyRow
  | cons {name : String} {value : Data} {rest : List (String × Data)} {member row : Ty} :
      Admitted a value member → AdmittedFields a rest row → member.isComputation = false →
      AdmittedFields a ((name,value)::rest) (.field name member row)
end

/-- An admitted value has a typed literal: its own literal syntax, with `toData`
injections exactly at universal positions. -/
theorem Admitted.typing {a : Assumptions} {data : Data} {ty : Ty}
    (h : Admitted a data ty) : ∃ term, Literal term data ∧ PartialTyping a [] term ty [] := by
  induction h using Admitted.rec
      (motive_2 := fun fields row _ => ∃ terms, LiteralFields terms fields ∧ FieldsTyping a [] terms row []) with
  | natural n => exact ⟨_, .natural n, .natural [] n⟩
  | boolean b => exact ⟨_, .boolean b, .boolean [] b⟩
  | label s => exact ⟨_, .label s, .label [] s⟩
  | record _ ih =>
      obtain ⟨terms, literal, typed⟩ := ih
      exact ⟨_, .record literal, .record typed⟩
  | variant _ lookup pure ih =>
      obtain ⟨term, literal, typed⟩ := ih
      exact ⟨_, .inject literal, .inject typed lookup pure⟩
  | conversion _ agreement ih =>
      obtain ⟨term, literal, typed⟩ := ih
      exact ⟨_, literal, .conversion typed agreement⟩
  | universal _ => exact Data.universal_typing a _
  | nil => exact ⟨_, .nil, .nil []⟩
  | cons _ _ pure valueIH restIH =>
      obtain ⟨term, literal, typed⟩ := valueIH
      obtain ⟨terms, literals, typedRest⟩ := restIH
      exact ⟨_, .cons literal literals, .cons typed typedRest pure⟩

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
    ∃ term, Literal term data ∧ PartialTyping a [] (.app function term) codomain (addUses uses []) := by
  obtain ⟨term, literal, typed⟩ := argumentTyped.typing
  exact ⟨term, literal, .application functionTyped typed arrow rfl allowed⟩

/-- Argument-wise `Literal`. -/
inductive Literals : List Term → List Data → Prop where
  | nil : Literals [] []
  | cons {term : Term} {data : Data} {terms : List Term} {values : List Data} :
      Literal term data → Literals terms values → Literals (term :: terms) (data :: values)

inductive AdmittedArguments (a : Assumptions) : Ty → List Data → Ty → Prop where
  | nil (ty : Ty) : AdmittedArguments a ty [] ty
  | cons {functionTy domain codomain result : Ty} {reuse : Reuse} {quantity : Quantity}
      {data : Data} {rest : List Data} :
      callable functionTy = .arrow reuse quantity domain codomain →
      Admitted a data domain → argumentAllowed a quantity [] domain [] = true →
      AdmittedArguments a codomain rest result →
      AdmittedArguments a functionTy (data::rest) result

/-- Literal applications occur only in the proof/reference view. -/
def literalApplications (function : Term) (arguments : List Term) : Term :=
  arguments.foldl (fun function argument => .app function argument) function

theorem AdmittedArguments.typing {a : Assumptions} {functionTy result : Ty}
    {arguments : List Data} (admitted : AdmittedArguments a functionTy arguments result)
    {function : Term} (typed : PartialTyping a [] function functionTy []) :
    ∃ terms, Literals terms arguments ∧
      PartialTyping a [] (literalApplications function terms) result [] := by
  induction admitted generalizing function with
  | nil ty => exact ⟨[], .nil, typed⟩
  | cons arrow data allowed rest ih =>
      obtain ⟨term, literal, applied⟩ := Admitted.application typed data arrow allowed
      obtain ⟨terms, literals, final⟩ := ih applied
      exact ⟨term :: terms, .cons literal literals, final⟩

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
