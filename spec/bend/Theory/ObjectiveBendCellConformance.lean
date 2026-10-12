/- Conformance of a state is per cell. A list conforms to a list type exactly when
every item conforms to the item type (`chain_typed_iff`); a relation's `rows {items}`
conforms to a relation type exactly when every row conforms to the row type
(`relation_typed_iff`); and a record conforms to a closed row exactly when it
conforms with one field's value replaced by any conforming value and that field's
own value conforms (`field_typed_iff`). So when every row a write leaves as it was
conformed, the state after it conforms exactly when its scalar part and the rows it
changed do: what lets the host check a write by the cells it changes (KERNEL-HANDOFF
§15, `Turn.Changes.checked`) instead of the whole state. -/
import Theory.ObjectiveBendDataConformance
import Theory.ObjectiveBendTypes
import Theory.AxiomPin
namespace Delvetalk.Theory.ObjectiveBendCellConformance
open Delvetalk.Theory.ObjectiveBendTypes
open Delvetalk.Theory.ObjectiveBendDemandData
open Delvetalk.Theory.ObjectiveBendDataConformance
set_option autoImplicit false

/-- A list's items as the `nil` / `cons {head, tail}` chain. -/
def chain : List Data → Data
  | [] => .variant "nil" (.record [])
  | x :: xs => .variant "cons" (.record [("head", x), ("tail", chain xs)])

/-- `fields` with the value of `name` replaced by `value`. -/
def replaceField (fields : List (String × Data)) (name : String) (value : Data) : List (String × Data) :=
  fields.map fun (k, v) => if k == name then (k, value) else (k, v)

/-! ## Bridging and record inversion -/

theorem rowMember_eq (row : Ty) (s : String) : rowMember row s = Ty.rowMember row s := by
  induction row <;> simp_all [rowMember, Ty.rowMember]

theorem rowMember_isRow {row member : Ty} {name : String} (h : rowMember row name = some member) :
    isRow row = true := by
  cases row <;> simp_all [rowMember, isRow]

theorem record_iff {bounds : DataBounds} {fields : List (String × Data)} {row : Ty}
    (shape : isRow row = true) :
    HasType bounds (.record fields) row ↔
      (fields.length = (rowNames row).length ∧
        (fields.map Prod.fst).eraseDups.length = fields.length ∧
        (∀ field ∈ fields, (rowMember row field.1).isSome = true) ∧
        (∀ name value, (name, value) ∈ fields → ∀ member, rowMember row name = some member →
          HasType bounds value member)) := by
  constructor
  · intro h
    cases h with
    | record _ _ _ count distinct declared members =>
      exact ⟨count, distinct, declared, members⟩
    | universal => simp [isRow] at shape
    | unfold => simp [isRow] at shape
  · rintro ⟨count, distinct, declared, members⟩
    exact HasType.record fields row shape count distinct declared members

/-- A two-field record `{head, tail}` against a closed two-field row. -/
theorem pair_typed_iff {bounds : DataBounds} {a b : String} {m1 m2 : Ty} {x t : Data}
    {headTy tailTy : Ty}
    (hh : rowMember (.field a m1 (.field b m2 .emptyRow)) "head" = some headTy)
    (ht : rowMember (.field a m1 (.field b m2 .emptyRow)) "tail" = some tailTy) :
    HasType bounds (.record [("head", x), ("tail", t)]) (.field a m1 (.field b m2 .emptyRow)) ↔
      HasType bounds x headTy ∧ HasType bounds t tailTy := by
  rw [record_iff (by simp [isRow])]
  constructor
  · rintro ⟨_, _, _, members⟩
    exact ⟨members "head" x (by simp) _ hh, members "tail" t (by simp) _ ht⟩
  · rintro ⟨hx, ht'⟩
    refine ⟨by simp [rowNames], by simp [List.eraseDups, List.eraseDupsBy, List.eraseDupsBy.loop], ?_, ?_⟩
    · intro field hf
      simp only [List.mem_cons, List.not_mem_nil, or_false] at hf
      rcases hf with rfl | rfl
      · simp [hh]
      · simp [ht]
    · intro name value hmem member hm
      simp only [List.mem_cons, List.not_mem_nil, or_false, Prod.mk.injEq] at hmem
      rcases hmem with ⟨rfl, rfl⟩ | ⟨rfl, rfl⟩
      · rw [hh] at hm; cases hm; exact hx
      · rw [ht] at hm; cases hm; exact ht'

/-- A one-field record against the closed one-field row it names. -/
theorem single_typed_iff {bounds : DataBounds} {n : String} {m : Ty} {v : Data} :
    HasType bounds (.record [(n, v)]) (.field n m .emptyRow) ↔ HasType bounds v m := by
  rw [record_iff (by simp [isRow])]
  constructor
  · rintro ⟨_, _, _, members⟩
    exact members n v (by simp) m (by simp [rowMember])
  · intro hv
    refine ⟨by simp [rowNames], by simp [List.eraseDups, List.eraseDupsBy, List.eraseDupsBy.loop], ?_, ?_⟩
    · intro field hf
      simp only [List.mem_cons, List.not_mem_nil, or_false] at hf
      subst hf
      simp [rowMember]
    · intro name value hmem member hm
      simp only [List.mem_cons, List.not_mem_nil, or_false, Prod.mk.injEq] at hmem
      obtain ⟨rfl, rfl⟩ := hmem
      simp [rowMember] at hm
      subst hm
      exact hv

theorem closed_two {row : Ty} (h : row.closedRowCount = some 2) :
    ∃ a m1 b m2, row = .field a m1 (.field b m2 .emptyRow) := by
  cases row <;> simp [Ty.closedRowCount] at h
  case field a m1 tail =>
    cases tail <;> simp [Ty.closedRowCount] at h
    case field b m2 tail2 =>
      cases tail2 <;> simp [Ty.closedRowCount] at h
      exact ⟨a, m1, b, m2, rfl⟩

theorem closed_one {row : Ty} (h : row.closedRowCount = some 1) :
    ∃ a m1, row = .field a m1 .emptyRow := by
  cases row <;> simp [Ty.closedRowCount] at h
  case field a m1 tail =>
    cases tail <;> simp [Ty.closedRowCount] at h
    exact ⟨a, m1, rfl⟩

/-- The facts `Ty.listItem` extracts. -/
theorem listItem_spec {bounds : DataBounds} {index : Nat} {item : Ty}
    (list : Ty.listItem bounds (.variable index) = some item) :
    ∃ row cons, bounds.lookup index = some (.variant row) ∧
      row.closedRowCount = some 2 ∧ Ty.rowMember row "nil" = some .emptyRow ∧
      Ty.rowMember row "cons" = some cons ∧ cons.closedRowCount = some 2 ∧
      Ty.rowMember cons "tail" = some (.variable index) ∧ Ty.rowMember cons "head" = some item := by
  unfold Ty.listItem at list
  rcases hlk : bounds.lookup index with _ | bound
  · simp [hlk] at list
  · cases bound <;> simp only [hlk] at list <;> try (simp at list; done)
    rename_i row
    split at list
    · rename_i hc
      simp only [Bool.and_eq_true, beq_iff_eq] at hc
      split at list
      · rename_i cons hcons
        split at list
        · rename_i hc2
          simp only [Bool.and_eq_true, beq_iff_eq] at hc2
          exact ⟨row, cons, rfl, hc.1, hc.2, hcons, hc2.1, hc2.2, list⟩
        · simp at list
      · simp at list
    · simp at list

theorem chain_typed_iff {bounds : DataBounds} {index : Nat} {item : Ty}
    (list : Ty.listItem bounds (.variable index) = some item) :
    ∀ xs : List Data, HasType bounds (chain xs) (.variable index) ↔ ∀ x ∈ xs, HasType bounds x item := by
  obtain ⟨row, cons, hl, hrow, hnil, hcons, hc2, htail, hhead⟩ := listItem_spec list
  obtain ⟨a, m1, b, m2, rfl⟩ := closed_two hc2
  intro xs
  induction xs with
  | nil =>
    simp only [List.not_mem_nil, false_imp_iff, implies_true, iff_true]
    refine HasType.unfold _ index (.variant row) hl (HasType.variant _ _ row .emptyRow ?_ ?_)
    · rw [rowMember_eq]; exact hnil
    · exact (record_iff (by simp [isRow])).2 ⟨by simp [rowNames], by simp, by simp, by simp⟩
  | cons x xs ih =>
    rw [List.forall_mem_cons, ← ih]
    have hh : rowMember (.field a m1 (.field b m2 .emptyRow)) "head" = some item := by
      rw [rowMember_eq]; exact hhead
    have ht : rowMember (.field a m1 (.field b m2 .emptyRow)) "tail" = some (.variable index) := by
      rw [rowMember_eq]; exact htail
    have hcm : rowMember row "cons" = some (.field a m1 (.field b m2 .emptyRow)) := by
      rw [rowMember_eq]; exact hcons
    constructor
    · intro h
      cases h with
      | unfold _ _ bound found typed =>
        rw [hl] at found
        cases found
        cases typed with
        | variant _ _ _ member found2 typed2 =>
          have := hcm.symm.trans found2
          cases this
          exact (pair_typed_iff hh ht).1 typed2
    · intro h
      exact HasType.unfold _ index (.variant row) hl
        (HasType.variant _ _ row _ hcm ((pair_typed_iff hh ht).2 h))

theorem relation_typed_iff {bounds : DataBounds} {relation item : Ty}
    (rows : Ty.relationItem bounds relation = some item) (xs : List Data) :
    HasType bounds (.variant "rows" (.record [("items", chain xs)])) relation ↔ ∀ x ∈ xs, HasType bounds x item := by
  cases relation <;> simp only [Ty.relationItem] at rows <;> try cases rows
  rename_i row
  split at rows
  · rename_i hrow
    simp only [beq_iff_eq] at hrow
    split at rows
    · rename_i payload hp
      split at rows
      · rename_i hpc
        simp only [beq_iff_eq] at hpc
        obtain ⟨an, am, rfl⟩ := closed_one hpc
        simp only [Option.bind_eq_some_iff] at rows
        obtain ⟨listTy, hitems, hli⟩ := rows
        have hitems' : Ty.rowMember (.field an am .emptyRow) "items" = some listTy := hitems
        have hn : an = "items" ∧ am = listTy := by
          simp [Ty.rowMember] at hitems'
          exact hitems'
        obtain ⟨rfl, rfl⟩ := hn
        cases am <;> first | (simp [Ty.listItem] at hli; done) | skip
        rename_i index
        rw [← chain_typed_iff hli xs]
        have hrm : rowMember row "rows" = some (.field "items" (.variable index) .emptyRow) := by
          rw [rowMember_eq]; exact hp
        constructor
        · intro h
          cases h with
          | variant _ _ _ member found typed =>
            have := hrm.symm.trans found
            cases this
            exact single_typed_iff.1 typed
        · intro h
          exact HasType.variant _ _ row _ hrm (single_typed_iff.2 h)
      · cases rows
    · cases rows
  · cases rows

/-! ## Per-field conformance -/

theorem replaceField_keys (fields : List (String × Data)) (name : String) (value : Data) :
    (replaceField fields name value).map Prod.fst = fields.map Prod.fst := by
  induction fields with
  | nil => rfl
  | cons p rest ih =>
    obtain ⟨k, v⟩ := p
    simp only [replaceField] at ih ⊢
    simp only [List.map_cons]
    rw [ih]
    by_cases h : k == name <;> simp [h]

theorem mem_replaceField (fields : List (String × Data)) (name : String) (value : Data)
    (k : String) (v : Data) :
    (k, v) ∈ replaceField fields name value ↔
      (k ≠ name ∧ (k, v) ∈ fields) ∨ (k = name ∧ v = value ∧ name ∈ fields.map Prod.fst) := by
  induction fields with
  | nil => simp [replaceField]
  | cons p rest ih =>
    obtain ⟨k0, v0⟩ := p
    simp only [replaceField] at ih ⊢
    simp only [List.map_cons, List.mem_cons, List.mem_map] at ih ⊢
    by_cases h0 : k0 = name
    · subst h0
      simp only [beq_self_eq_true, ite_true, Prod.mk.injEq]
      constructor
      · rintro (⟨rfl, rfl⟩ | h)
        · simp
        · rcases ih.1 h with ⟨hne, hm⟩ | ⟨rfl, rfl, hk⟩
          · exact Or.inl ⟨hne, Or.inr hm⟩
          · exact Or.inr ⟨rfl, rfl, Or.inr hk⟩
      · rintro (⟨hne, (⟨rfl, rfl⟩ | hm)⟩ | ⟨rfl, rfl, _⟩)
        · exact absurd rfl hne
        · exact Or.inr (ih.2 (Or.inl ⟨hne, hm⟩))
        · exact Or.inl ⟨rfl, rfl⟩
    · have hb : (k0 == name) = false := by simpa using h0
      simp only [hb, Bool.false_eq_true, ite_false, Prod.mk.injEq]
      constructor
      · rintro (⟨rfl, rfl⟩ | h)
        · exact Or.inl ⟨h0, Or.inl ⟨rfl, rfl⟩⟩
        · rcases ih.1 h with ⟨hne, hm⟩ | ⟨rfl, rfl, hk⟩
          · exact Or.inl ⟨hne, Or.inr hm⟩
          · exact Or.inr ⟨rfl, rfl, Or.inr hk⟩
      · rintro (⟨hne, (⟨rfl, rfl⟩ | hm)⟩ | ⟨rfl, rfl, (hk | hk)⟩)
        · exact Or.inl ⟨rfl, rfl⟩
        · exact Or.inr (ih.2 (Or.inl ⟨hne, hm⟩))
        · exact absurd hk.symm h0
        · exact Or.inr (ih.2 (Or.inr ⟨rfl, rfl, hk⟩))

theorem field_typed_iff {bounds : DataBounds} {fields : List (String × Data)} {row member : Ty}
    {name : String} {value other : Data}
    (present : name ∈ fields.map Prod.fst) (found : rowMember row name = some member)
    (otherTyped : HasType bounds other member) :
    HasType bounds (.record (replaceField fields name value)) row ↔
      HasType bounds (.record (replaceField fields name other)) row ∧ HasType bounds value member := by
  have keys := replaceField_keys fields name
  have lenEq : ∀ v, (replaceField fields name v).length = fields.length := fun v => by
    simpa using congrArg List.length (keys v)
  have declKeys : ∀ (L : List (String × Data)),
      (∀ field ∈ L, (rowMember row field.1).isSome = true) ↔
        ∀ k ∈ L.map Prod.fst, (rowMember row k).isSome = true := by
    intro L
    simp only [List.mem_map, forall_exists_index, and_imp, forall_apply_eq_imp_iff₂]
  have hrow := rowMember_isRow found
  rw [record_iff hrow, record_iff hrow]
  simp only [lenEq, keys, declKeys]
  constructor
  · rintro ⟨c, d, dc, mem⟩
    refine ⟨⟨c, d, dc, ?_⟩, ?_⟩
    · intro k v hkv m hm
      rcases (mem_replaceField _ _ _ k v).1 hkv with ⟨hne, hk⟩ | ⟨rfl, rfl, _⟩
      · exact mem k v ((mem_replaceField _ _ _ k v).2 (Or.inl ⟨hne, hk⟩)) m hm
      · rw [found] at hm; cases hm; exact otherTyped
    · exact mem name value ((mem_replaceField _ _ _ name value).2 (Or.inr ⟨rfl, rfl, present⟩))
        member found
  · rintro ⟨⟨c, d, dc, mem⟩, hv⟩
    refine ⟨c, d, dc, ?_⟩
    intro k v hkv m hm
    rcases (mem_replaceField _ _ _ k v).1 hkv with ⟨hne, hk⟩ | ⟨rfl, rfl, _⟩
    · exact mem k v ((mem_replaceField _ _ _ k v).2 (Or.inl ⟨hne, hk⟩)) m hm
    · rw [found] at hm; cases hm; exact hv

#assert_axioms rowMember_eq rowMember_isRow record_iff pair_typed_iff single_typed_iff closed_two closed_one
  listItem_spec chain_typed_iff relation_typed_iff replaceField_keys mem_replaceField
  field_typed_iff

end Delvetalk.Theory.ObjectiveBendCellConformance
