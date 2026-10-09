/- Runtime conformance (`Data.conformsUnder`, the check the host runs on every
argument, response, Plan and result) against a declarative typing of finite Data
under a packet's declared bounds.

`HasType bounds d ty` is the relation: scalars at their types; a record at a
closed row with exactly the row's field count, distinct names and every field
typed at its row member; a variant at a sum whose row names its label, payload
typed at the member; and data at a variable when it has the variable's bound
type (one unfolding of a recursive sum).

* `conformsFuel_sound`: a `true` answer at any fuel is a `HasType` derivation.
* `conformsUnder_complete`: every `HasType` derivation is accepted at the fuel the
  code uses, `(size+1)*(bounds+3)+2`. Fuel is therefore never the cause of a false
  negative. The proof bounds the work per data node by `bounds.length + 3`: an
  unfolding chain between two structural types visits each declared variable at
  most once (`short_chain`, a pigeonhole over the bounds' keys: a chain that
  revisits a variable cycles and never reaches data), one step for the node, and
  one step per earlier sibling field, charged to that sibling's own size.
* `conformsUnder_iff`: the two together.

No `isDataUnder` hypothesis is needed: completeness holds for every type, and
`isDataUnder` is the static side's decision that the type admits only such data. -/
import Theory.ObjectiveBendDemandData
import Theory.AxiomPin
namespace Minidregg.Theory.ObjectiveBendDataConformance
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendDemandData
set_option autoImplicit false

def isVariable : Ty → Bool
  | .variable _ => true
  | _ => false

def isRow : Ty → Bool
  | .field .. | .emptyRow => true
  | _ => false

/-- Declarative typing of finite Data under declared bounds. -/
inductive HasType (bounds : DataBounds) : Data → Ty → Prop
  | natural (n : Nat) : HasType bounds (.natural n) .natural
  | boolean (b : Bool) : HasType bounds (.boolean b) .boolean
  | label (s : String) : HasType bounds (.label s) .label
  | record (fields : List (String × Data)) (row : Ty)
      (shape : isRow row = true)
      (count : fields.length = (rowNames row).length)
      (distinct : (fields.map Prod.fst).eraseDups.length = fields.length)
      (declared : ∀ field ∈ fields, (rowMember row field.1).isSome = true)
      (members : ∀ name value, (name, value) ∈ fields → ∀ member, rowMember row name = some member →
        HasType bounds value member) :
      HasType bounds (.record fields) row
  | variant (tag : String) (payload : Data) (row member : Ty)
      (found : rowMember row tag = some member) (typed : HasType bounds payload member) :
      HasType bounds (.variant tag payload) (.variant row)
  | unfold (data : Data) (index : Nat) (bound : Ty)
      (found : bounds.lookup index = some bound) (typed : HasType bounds data bound) :
      HasType bounds data (.variable index)

/-! ## Unfolding chains -/

/-- Follow a type's variable chain `k` steps through the bounds. -/
def follow (bounds : DataBounds) : Nat → Ty → Ty
  | 0, type => type
  | k + 1, .variable index => match bounds.lookup index with
    | some bound => follow bounds k bound
    | none => .variable index
  | _ + 1, type => type

theorem follow_nonvar (bounds : DataBounds) {type : Ty} (structural : isVariable type = false) :
    ∀ k, follow bounds k type = type := by
  intro k
  cases k with
  | zero => rfl
  | succ k => cases type <;> simp_all [follow, isVariable]

theorem follow_stuck (bounds : DataBounds) {index : Nat} (missing : bounds.lookup index = none) :
    ∀ k, follow bounds k (.variable index) = .variable index := by
  intro k
  cases k with
  | zero => rfl
  | succ k => simp [follow, missing]

theorem follow_add (bounds : DataBounds) :
    ∀ (a b : Nat) (type : Ty), follow bounds (a + b) type = follow bounds b (follow bounds a type) := by
  intro a
  induction a with
  | zero => intro b type; simp [follow]
  | succ a ih =>
    intro b type
    cases type with
    | «variable» index =>
      cases found : bounds.lookup index with
      | none => simp [follow, found, follow_stuck bounds found]
      | some bound =>
        rw [show a + 1 + b = (a + b) + 1 by omega]
        simp [follow, found, ih]
    | _ =>
      rw [show a + 1 + b = (a + b) + 1 by omega]
      cases b <;> simp [follow]

/-- Following a chain of variables spends exactly one fuel per unfolding. -/
theorem conformsFuel_follow (bounds : DataBounds) (data : Data) :
    ∀ (k : Nat) (type : Ty) (fuel : Nat), (∀ j < k, isVariable (follow bounds j type) = true) →
      Data.conformsFuel bounds (fuel + k) data type = Data.conformsFuel bounds fuel data (follow bounds k type) := by
  intro k
  induction k with
  | zero => intro type fuel _; rfl
  | succ k ih =>
    intro type fuel variables
    have head := variables 0 (by omega)
    cases type with
    | «variable» index =>
      cases found : bounds.lookup index with
      | none =>
        rw [follow_stuck bounds found]
        rw [show fuel + (k + 1) = (fuel + k) + 1 by omega]
        cases fuel <;> cases data <;> simp [Data.conformsFuel, found]
      | some bound =>
        rw [show fuel + (k + 1) = (fuel + k) + 1 by omega]
        have rest : ∀ j < k, isVariable (follow bounds j bound) = true := by
          intro j lt
          have := variables (j + 1) (by omega)
          simpa [follow, found] using this
        have step : Data.conformsFuel bounds (fuel + k + 1) data (.variable index) =
            Data.conformsFuel bounds (fuel + k) data bound := by
          cases data <;> simp [Data.conformsFuel, found]
        rw [step, ih bound fuel rest]
        simp [follow, found]
    | _ => simp [follow, isVariable] at head

/-- A derivation reaches a structural type through some unfolding chain. -/
theorem HasType.chain {bounds : DataBounds} {data : Data} {type : Ty} (typed : HasType bounds data type) :
    ∃ k, isVariable (follow bounds k type) = false ∧ HasType bounds data (follow bounds k type) := by
  induction typed with
  | unfold data index bound found typed ih =>
    obtain ⟨k, structural, typedAt⟩ := ih
    exact ⟨k + 1, by simpa [follow, found] using structural, by simpa [follow, found] using typedAt⟩
  | natural n => exact ⟨0, rfl, .natural n⟩
  | boolean b => exact ⟨0, rfl, .boolean b⟩
  | label s => exact ⟨0, rfl, .label s⟩
  | record fields row shape count distinct declared members _ =>
    refine ⟨0, ?_, .record fields row shape count distinct declared members⟩
    cases row <;> simp_all [isRow, isVariable, follow]
  | variant tag payload row member found typed _ =>
    exact ⟨0, rfl, .variant tag payload row member found typed⟩

/-- Pigeonhole: a duplicate-free list inside another is no longer than it. -/
theorem nodup_length_le : ∀ (small large : List Nat), small.Nodup → (∀ x ∈ small, x ∈ large) →
    small.length ≤ large.length := by
  intro small
  induction small with
  | nil => intro _ _ _; simp
  | cons x rest ih =>
    intro large nodup inside
    rw [List.nodup_cons] at nodup
    have member : x ∈ large := inside x (by simp)
    have := ih (large.erase x) nodup.2 (by
      intro y yIn
      have ne : y ≠ x := fun same => nodup.1 (same ▸ yIn)
      exact (List.mem_erase_of_ne ne).mpr (inside y (by simp [yIn])))
    rw [List.length_erase_of_mem member] at this
    have : large.length ≥ 1 := List.length_pos_of_mem member
    simp only [List.length_cons]; omega

def variableIndex : Ty → Nat
  | .variable index => index
  | _ => 0

theorem lookup_key {bounds : DataBounds} {index : Nat} {bound : Ty} (found : bounds.lookup index = some bound) :
    index ∈ bounds.map Prod.fst := by
  obtain ⟨front, back, split, _⟩ := List.lookup_eq_some_iff.mp found
  subst split
  simp

/-- **Short chains.** A chain that reaches a structural type reaches it within
`bounds.length` unfoldings, through variables only. -/
theorem short_chain (bounds : DataBounds) :
    ∀ (k : Nat) (type : Ty), isVariable (follow bounds k type) = false →
      ∃ k', k' ≤ bounds.length ∧ follow bounds k' type = follow bounds k type ∧
        ∀ j < k', isVariable (follow bounds j type) = true := by
  intro k
  induction k using Nat.strongRecOn with
  | ind k ih =>
  intro type structural
  by_cases earlier : ∃ j < k, isVariable (follow bounds j type) = false
  · obtain ⟨j, lt, structuralJ⟩ := earlier
    obtain ⟨k', le, same, variables⟩ := ih j lt type structuralJ
    refine ⟨k', le, ?_, variables⟩
    rw [same, show k = j + (k - j) by omega, follow_add, follow_nonvar bounds structuralJ]
  · have variables : ∀ j < k, isVariable (follow bounds j type) = true := by
      intro j lt
      cases h : isVariable (follow bounds j type)
      · exact absurd ⟨j, lt, h⟩ earlier
      · rfl
    by_cases small : k ≤ bounds.length
    · exact ⟨k, small, rfl, variables⟩
    · -- Every visited variable is declared: an undeclared one would be stuck forever.
      have isVar : ∀ j < k, follow bounds j type = .variable (variableIndex (follow bounds j type)) := by
        intro j lt
        have := variables j lt
        generalize follow bounds j type = t at this ⊢
        cases t <;> simp_all [isVariable, variableIndex]
      have declared : ∀ j < k, variableIndex (follow bounds j type) ∈ bounds.map Prod.fst := by
        intro j lt
        cases found : bounds.lookup (variableIndex (follow bounds j type)) with
        | some bound => exact lookup_key found
        | none =>
          have stuck := follow_stuck bounds found (k - j)
          rw [← isVar j lt, ← follow_add, show j + (k - j) = k by omega] at stuck
          have isVarJ := variables j lt
          rw [stuck] at structural
          rw [structural] at isVarJ
          cases isVarJ
      let visited := (List.range k).map fun j => variableIndex (follow bounds j type)
      have notNodup : ¬ visited.Nodup := by
        intro nodup
        have := nodup_length_le visited _ nodup (by
          intro x member
          simp only [visited, List.mem_map, List.mem_range] at member
          obtain ⟨j, lt, rfl⟩ := member
          exact declared j lt)
        simp [visited] at this
        omega
      unfold List.Nodup at notNodup
      rw [List.pairwise_iff_getElem] at notNodup
      simp only [Classical.not_forall, Classical.not_not] at notNodup
      obtain ⟨a, b, ha, hb, lt, same⟩ := notNodup
      simp only [visited, List.length_map, List.length_range] at ha hb
      simp only [visited, List.getElem_map, List.getElem_range] at same
      have equal : follow bounds a type = follow bounds b type := by
        rw [isVar a ha, isVar b hb, same]
      obtain ⟨k', le, sameK, variablesK⟩ := ih (a + (k - b)) (by omega) type (by
        rw [follow_add, equal, ← follow_add, show b + (k - b) = k by omega]; exact structural)
      refine ⟨k', le, ?_, variablesK⟩
      rw [sameK, follow_add, equal, ← follow_add, show b + (k - b) = k by omega]

/-! ## Completeness -/

theorem fieldsSize_member : ∀ (fields : List (String × Data)) (name : String) (value : Data),
    (name, value) ∈ fields → value.size ≤ Data.fieldsSize fields := by
  intro fields
  induction fields with
  | nil => intro _ _ member; simp at member
  | cons field rest ih =>
    intro name value member
    obtain ⟨n, v⟩ := field
    simp only [List.mem_cons] at member
    simp only [Data.fieldsSize]
    rcases member with same | member
    · cases same; omega
    · have := ih name value member; omega

theorem length_le_fieldsSize : ∀ (fields : List (String × Data)), fields.length ≤ Data.fieldsSize fields := by
  intro fields
  induction fields with
  | nil => simp [Data.fieldsSize]
  | cons field rest ih =>
    obtain ⟨n, v⟩ := field
    have : 1 ≤ v.size := by cases v <;> simp [Data.size]; all_goals omega
    simp [Data.fieldsSize]; omega

theorem fieldsConformFuel_complete (bounds : DataBounds) (row : Ty) (cost : Nat) :
    ∀ (fields : List (String × Data)) (fuel : Nat),
      (∀ field ∈ fields, (rowMember row field.1).isSome = true) →
      (∀ name value, (name, value) ∈ fields → ∀ member, rowMember row name = some member →
        ∀ fuel, fuel ≥ cost * value.size → Data.conformsFuel bounds fuel value member = true) →
      cost ≥ 1 → fuel ≥ cost * Data.fieldsSize fields + 1 →
      Data.fieldsConformFuel bounds fuel fields row = true := by
  intro fields
  induction fields with
  | nil => intro fuel _ _ _ enough; cases fuel <;> simp_all [Data.fieldsConformFuel]
  | cons field rest ih =>
    intro fuel declared members positive enough
    obtain ⟨name, value⟩ := field
    obtain ⟨fuel, rfl⟩ : ∃ f, fuel = f + 1 := ⟨fuel - 1, by omega⟩
    simp only [Data.fieldsSize, Nat.mul_add] at enough
    have isSome := declared (name, value) (by simp)
    obtain ⟨member, found⟩ := Option.isSome_iff_exists.mp isSome
    simp only [Data.fieldsConformFuel, found, Bool.and_eq_true]
    refine ⟨members name value (by simp) member found fuel (by omega), ?_⟩
    have : cost * value.size ≥ 1 := by
      have : 1 ≤ value.size := by cases value <;> simp [Data.size]; all_goals omega
      exact Nat.le_trans this (Nat.le_mul_of_pos_left _ positive)
    exact ih fuel (fun f m => declared f (by simp [m]))
      (fun n v m => members n v (by simp [m])) positive (by omega)

/-- **Completeness at every sufficient fuel**: `(bounds.length + 3)` per data node. -/
theorem conformsFuel_complete (bounds : DataBounds) :
    ∀ (n : Nat) (data : Data), data.size ≤ n → ∀ (type : Ty), HasType bounds data type →
      ∀ fuel, fuel ≥ (bounds.length + 3) * data.size → Data.conformsFuel bounds fuel data type = true := by
  intro n
  induction n using Nat.strongRecOn with
  | ind n ih =>
  intro data sized type typed fuel enough
  obtain ⟨k0, structural0, typed0⟩ := typed.chain
  obtain ⟨k, short, same, variables⟩ := short_chain bounds k0 type structural0
  rw [← same] at structural0 typed0
  obtain ⟨rest, rfl⟩ : ∃ r, fuel = r + k := ⟨fuel - k, by
    have : 1 ≤ data.size := by cases data <;> simp [Data.size]; all_goals omega
    have := Nat.le_mul_of_pos_right (bounds.length + 3) this
    omega⟩
  rw [conformsFuel_follow bounds data k type rest variables]
  generalize follow bounds k type = head at structural0 typed0
  cases typed0 with
  | unfold => simp [isVariable] at structural0
  | natural m =>
    obtain ⟨r, rfl⟩ : ∃ r, rest = r + 1 := ⟨rest - 1, by simp [Data.size] at enough; omega⟩
    simp [Data.conformsFuel]
  | boolean b =>
    obtain ⟨r, rfl⟩ : ∃ r, rest = r + 1 := ⟨rest - 1, by simp [Data.size] at enough; omega⟩
    simp [Data.conformsFuel]
  | label s =>
    obtain ⟨r, rfl⟩ : ∃ r, rest = r + 1 := ⟨rest - 1, by simp [Data.size] at enough; omega⟩
    simp [Data.conformsFuel]
  | variant tag payload row member found typedPayload =>
    simp only [Data.size, Nat.mul_add] at enough sized
    obtain ⟨r, rfl⟩ : ∃ r, rest = r + 1 := ⟨rest - 1, by omega⟩
    simp only [Data.conformsFuel, found]
    exact ih payload.size (by omega) payload (Nat.le_refl _) member typedPayload r (by omega)
  | record =>
    rename_i fields distinct shape count declared members
    simp only [Data.size, Nat.mul_add] at enough sized
    obtain ⟨r, rfl⟩ : ∃ r, rest = r + 1 := ⟨rest - 1, by omega⟩
    have fieldsOk := fieldsConformFuel_complete bounds head (bounds.length + 3) fields r declared
      (fun name value member m found fuel enoughField =>
        ih value.size (by have := fieldsSize_member fields name value member; omega) value
          (Nat.le_refl _) m (members name value member m found) fuel enoughField)
      (by omega) (by omega)
    cases head with
    | field fieldName fieldMember tail =>
      simp [Data.conformsFuel, count, distinct, fieldsOk]
    | emptyRow =>
      simp [Data.conformsFuel, count, distinct, fieldsOk]
    | _ => simp [isRow] at shape

/-- **Fuel never causes a false negative**: well-typed data passes the runtime check
at the fuel `Data.conformsUnder` supplies. -/
theorem conformsUnder_complete {bounds : DataBounds} {data : Data} {type : Ty}
    (typed : HasType bounds data type) : data.conformsUnder bounds type = true := by
  unfold Data.conformsUnder
  apply conformsFuel_complete bounds data.size data (Nat.le_refl _) type typed
  have := Nat.mul_le_mul_left (bounds.length + 3) (Nat.le_add_right data.size 1)
  rw [Nat.mul_comm (data.size + 1)]
  omega

/-! ## Soundness -/

theorem fieldsConformFuel_sound (bounds : DataBounds) (row : Ty) :
    ∀ (fields : List (String × Data)) (fuel : Nat), Data.fieldsConformFuel bounds fuel fields row = true →
      (∀ field ∈ fields, (rowMember row field.1).isSome = true) ∧
      ∀ name value, (name, value) ∈ fields → ∀ member, rowMember row name = some member →
        ∃ smaller, smaller < fuel ∧ Data.conformsFuel bounds smaller value member = true := by
  intro fields
  induction fields with
  | nil => intro fuel _; simp
  | cons field rest ih =>
    intro fuel accepted
    obtain ⟨name, value⟩ := field
    cases fuel with
    | zero => simp [Data.fieldsConformFuel] at accepted
    | succ fuel =>
      simp only [Data.fieldsConformFuel, Bool.and_eq_true] at accepted
      obtain ⟨here, others⟩ := accepted
      obtain ⟨declared, typed⟩ := ih fuel others
      cases found : rowMember row name with
      | none => simp [found] at here
      | some member =>
        simp only [found] at here
        refine ⟨?_, ?_⟩
        · intro f member'
          simp only [List.mem_cons] at member'
          rcases member' with rfl | inside
          · simp [found]
          · exact declared f inside
        · intro n v inside m foundM
          simp only [List.mem_cons] at inside
          rcases inside with same | inside
          · cases same
            rw [found] at foundM; cases foundM
            exact ⟨fuel, by omega, here⟩
          · obtain ⟨smaller, lt, ok⟩ := typed n v inside m foundM
            exact ⟨smaller, by omega, ok⟩

theorem conformsFuel_sound (bounds : DataBounds) :
    ∀ (fuel : Nat) (data : Data) (type : Ty), Data.conformsFuel bounds fuel data type = true →
      HasType bounds data type := by
  intro fuel
  induction fuel using Nat.strongRecOn with
  | ind fuel ih =>
  intro data type accepted
  cases fuel with
  | zero => simp [Data.conformsFuel] at accepted
  | succ fuel =>
    cases type
    case «variable» index =>
      cases found : bounds.lookup index with
      | none => cases data <;> simp [Data.conformsFuel, found] at accepted
      | some bound =>
        have : Data.conformsFuel bounds fuel data bound = true := by
          cases data <;> simp_all [Data.conformsFuel]
        exact .unfold data index bound found (ih fuel (by omega) data bound this)
    all_goals cases data
    all_goals first
      | exact .natural _ | exact .boolean _ | exact .label _
      | (simp [Data.conformsFuel] at accepted; done)
      | skip
    case emptyRow.record | field.record =>
      rename_i fields
      simp only [Data.conformsFuel, Bool.and_eq_true, beq_iff_eq] at accepted
      obtain ⟨⟨⟨_, count⟩, distinct⟩, fieldsOk⟩ := accepted
      obtain ⟨declared, typed⟩ := fieldsConformFuel_sound bounds _ fields fuel fieldsOk
      exact .record fields _ rfl count distinct declared (fun n v inside m found =>
        let ⟨smaller, lt, ok⟩ := typed n v inside m found
        ih smaller (by omega) v m ok)
    case variant.variant =>
      rename_i row tag payload
      cases found : rowMember row tag with
      | none => simp [Data.conformsFuel, found] at accepted
      | some member =>
        simp only [Data.conformsFuel, found] at accepted
        exact .variant tag payload row member found (ih fuel (by omega) _ _ accepted)

#assert_axioms conformsUnder_complete conformsFuel_sound short_chain

theorem conformsUnder_iff {bounds : DataBounds} {data : Data} {type : Ty} :
    data.conformsUnder bounds type = true ↔ HasType bounds data type :=
  ⟨conformsFuel_sound bounds _ data type, conformsUnder_complete⟩

end Minidregg.Theory.ObjectiveBendDataConformance
