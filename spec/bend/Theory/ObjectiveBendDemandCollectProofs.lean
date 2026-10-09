/- The behaviour theorem for collecting the demand heap at a yield, for this edition's
machine (native cells, `nativeApplication`, `unary`, `toData`, `textJoin` and its join
frames) and its hosted runner (`forceHostedFrom`: the text tariff and exact heap
admission). Ported from Mini's `ObjectiveBendDemandCollectProofs`; definitions:
`Theory.ObjectiveBendDemandCollect`.

The relation is a renaming simulation. `Related f D s t` says `t` is `s` renamed by `f`
on a domain `D` that contains the roots and everything past `s`'s heap and is closed
under the heap: same control, same stack, and every `D`-cell of `s` is, renamed, the
`f`-image cell of `t`; `f` is injective on `D` and shifts the addresses past the heap.
Cells outside `D` (the garbage) are unconstrained. Because `f` and `D` never change,
lockstep allocation needs no extension of the renaming: both machines allocate at their
heap ends and `f` maps one end to the other.

* `liveMarks_spec`, `related_collect`: marking reaches every root and is closed, so
  `Related (collectRenaming s) (liveDomain s) s (collect s)`: no address reachable from
  the control or the stack dangles after collection.
* `related_stepRaw`: one transition of the whole machine, every constructor.
* `related_runBounded`, `related_runBounded_exact`, `related_resume` (the unit-cost runner).
* `related_forceHostedFrom`: the hosted runner agrees exactly, remaining ticks and
  capacity suspensions included, when the collected state is given exactly the room it
  had (`ExactRoom`, which `limitsPast` provides: `collect_exactRoom`).
* `related_materializeWith`, `related_completeWith`, `related_yieldedPlanWith`: extracted
  Data and remaining budgets agree.
* `collect_resume_segment`, and `checkpoint_resume_segment` for what a yield stores,
  `checkpoint = collect (settle s)` (composed with `settle_resume_segment`).

Not ported: Mini's typing transfer (`typed_collect`), as this edition has no
state-typing judgment. -/
import Theory.ObjectiveBendDemandCollect
import Theory.ObjectiveBendDemandSettleProofs
namespace Minidregg.Theory.ObjectiveBendDemandCollect
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData (Data)
set_option autoImplicit false

/-! ## Marking is sound: the marks contain the roots and are closed -/

theorem pending_nil {marks : Array Bool} {work : List Nat} (drained : pending marks work = []) :
    ∀ x ∈ work, marks[x]? ≠ some false := by
  induction work with
  | nil => intro x member; cases member
  | cons head rest ih =>
    intro x member
    simp only [pending] at drained
    split at drained
    · cases drained
    · rename_i notFalse
      rcases List.mem_cons.mp member with rfl | member
      · exact notFalse
      · exact ih drained x member

theorem pending_cons {marks : Array Bool} {work rest : List Nat} {address : Nat}
    (next : pending marks work = address :: rest) :
    marks[address]? = some false ∧ ∀ x ∈ work, marks[x]? ≠ some false ∨ x ∈ address :: rest := by
  induction work with
  | nil => simp [pending] at next
  | cons head tail ih =>
    simp only [pending] at next
    split at next
    · rename_i isFalse
      cases next
      exact ⟨isFalse, fun x member => .inr member⟩
    · rename_i notFalse
      obtain ⟨first, others⟩ := ih next
      refine ⟨first, fun x member => ?_⟩
      rcases List.mem_cons.mp member with rfl | member
      · exact .inl notFalse
      · exact others x member

theorem bound_of_some {α : Type} {xs : Array α} {i : Nat} {v : α} (found : xs[i]? = some v) :
    i < xs.size := (Array.getElem?_eq_some_iff.mp found).1

theorem count_false_set {marks : Array Bool} {address : Nat}
    (unmarked : marks[address]? = some false) :
    (marks.set! address true).count false + 1 = marks.count false := by
  have bound : address < marks.size := bound_of_some unmarked
  have entry : marks[address] = false := by simpa [Array.getElem?_eq_getElem bound] using unmarked
  have positive : 0 < marks.count false := by
    have member : false ∈ marks := Array.mem_of_getElem? unmarked
    exact Nat.pos_of_ne_zero (fun h => (Array.count_eq_zero.mp h) member)
  simp only [Array.set!_eq_setIfInBounds, Array.setIfInBounds, bound, dite_true]
  rw [Array.count_set bound]
  simp [entry]
  omega

theorem all_marked {marks : Array Bool} (none : marks.count false = 0) (address : Nat) :
    marks[address]? ≠ some false := by
  intro isFalse
  have member : false ∈ marks := Array.mem_of_getElem? isFalse
  exact (Array.count_eq_zero.mp none) member

/-- The marking invariant: every unmarked child of a marked cell is still to be traced. -/
def Traced (heap : Array Cell) (marks : Array Bool) (work : List Nat) : Prop :=
  ∀ a x : Nat, marks[a]? = some true → x ∈ children heap a → marks[x]? = some false → x ∈ work

theorem markFrom_spec (heap : Array Cell) :
    ∀ (fuel : Nat) (marks : Array Bool) (work : List Nat),
      marks.size = heap.size → marks.count false ≤ fuel → Traced heap marks work →
      (markFrom heap fuel marks work).size = heap.size ∧
      (∀ a : Nat, marks[a]? = some true → (markFrom heap fuel marks work)[a]? = some true) ∧
      (∀ x ∈ work, (markFrom heap fuel marks work)[x]? ≠ some false) ∧
      (∀ a x : Nat, (markFrom heap fuel marks work)[a]? = some true → x ∈ children heap a →
        (markFrom heap fuel marks work)[x]? ≠ some false) := by
  intro fuel
  induction fuel with
  | zero =>
    intro marks work size count _
    have none : marks.count false = 0 := by omega
    simp only [markFrom]
    exact ⟨size, fun _ h => h, fun x _ => all_marked none x, fun _ x _ _ => all_marked none x⟩
  | succ fuel ih =>
    intro marks work size count traced
    simp only [markFrom]
    split
    · rename_i drained
      have done := pending_nil drained
      refine ⟨size, fun _ h => h, done, ?_⟩
      intro a x marked child isFalse
      exact done x (traced a x marked child isFalse) isFalse
    · rename_i address rest next
      obtain ⟨unmarked, covered⟩ := pending_cons next
      have bound : address < marks.size := bound_of_some unmarked
      have setAt : ∀ b, (marks.set! address true)[b]? = if address = b then some true else marks[b]? := by
        intro b; simp [Array.getElem?_setIfInBounds, bound]
      have size' : (marks.set! address true).size = heap.size := by simpa using size
      have count' : (marks.set! address true).count false ≤ fuel := by
        have := count_false_set unmarked; omega
      have traced' : Traced heap (marks.set! address true) (children heap address ++ rest) := by
        intro b x marked child isFalse
        rw [setAt] at marked isFalse
        by_cases same : address = b
        · subst same; exact List.mem_append_left _ child
        · rw [if_neg same] at marked
          by_cases sameX : address = x
          · rw [if_pos sameX] at isFalse; cases isFalse
          · rw [if_neg sameX] at isFalse
            have inWork := traced b x marked child isFalse
            rcases covered x inWork with notFalse | member
            · exact absurd isFalse notFalse
            · rcases List.mem_cons.mp member with rfl | member
              · exact absurd rfl sameX
              · exact List.mem_append_right _ member
      obtain ⟨outSize, monotone, drains, closed⟩ := ih _ _ size' count' traced'
      refine ⟨outSize, ?_, ?_, closed⟩
      · intro a marked
        apply monotone
        rw [setAt]; split
        · rfl
        · exact marked
      · intro x member
        rcases covered x member with notFalse | member
        · intro isFalse
          by_cases sameX : address = x
          · subst sameX
            have := monotone address (by rw [setAt]; simp)
            rw [this] at isFalse; cases isFalse
          · cases hx : marks[x]? with
            | none =>
              have : x ≥ marks.size := Array.getElem?_eq_none_iff.mp hx
              have : (markFrom heap fuel (marks.set! address true) (children heap address ++ rest))[x]? = none :=
                Array.getElem?_eq_none (by rw [outSize, ← size]; exact this)
              rw [this] at isFalse; cases isFalse
            | some value =>
              cases value with
              | false => exact notFalse hx
              | true =>
                have := monotone x (by rw [setAt, if_neg sameX]; exact hx)
                rw [this] at isFalse; cases isFalse
        · rcases List.mem_cons.mp member with same | member
          · have := monotone address (by rw [setAt]; simp)
            rw [same, this]; simp
          · exact drains x (List.mem_append_right _ member)

/-- **Marking soundness.** The live marks cover the heap, contain every root in the
heap, and are closed: a marked cell's in-heap children are marked. -/
theorem liveMarks_spec (state : State) :
    (liveMarks state).size = state.heap.size ∧
    (∀ x ∈ rootAddresses state, (liveMarks state)[x]? ≠ some false) ∧
    (∀ a x : Nat, (liveMarks state)[a]? = some true → x ∈ children state.heap a →
      (liveMarks state)[x]? ≠ some false) := by
  have initial := markFrom_spec state.heap state.heap.size (Array.replicate state.heap.size false)
    (rootAddresses state) (by simp) (by simp)
    (by intro a x marked; simp [Array.getElem?_replicate] at marked)
  exact ⟨initial.1, initial.2.2.1, initial.2.2.2⟩


/-! ## Ranks and compaction -/

theorem foldl_rankStep (l : List Bool) : ∀ (acc : Array Nat) (c : Nat),
    (l.foldl rankStep (acc, c)).2 = c + l.count true ∧
    (l.foldl rankStep (acc, c)).1.size = acc.size + l.length ∧
    (∀ i, i < acc.size → (l.foldl rankStep (acc, c)).1[i]? = acc[i]?) ∧
    (∀ i, i < l.length → (l.foldl rankStep (acc, c)).1[acc.size + i]? = some (c + (l.take i).count true)) := by
  induction l with
  | nil => intro acc c; simp
  | cons m rest ih =>
    intro acc c
    obtain ⟨count, size, prefix_, entries⟩ := ih (acc.push c) (if m then c + 1 else c)
    simp only [List.foldl_cons, rankStep]
    refine ⟨?_, ?_, ?_, ?_⟩
    · rw [count]; cases m <;> simp <;> omega
    · rw [size]; simp; omega
    · intro i bound
      rw [prefix_ i (by simp; omega)]
      simp [Array.getElem?_push, show i ≠ acc.size by omega]
    · intro i bound
      cases i with
      | zero =>
        simpa [Array.getElem?_push] using prefix_ acc.size (by simp)
      | succ j =>
        have := entries j (by simpa using bound)
        rw [show acc.size + (j + 1) = (acc.push c).size + j by simp; omega, this]
        cases m <;> simp <;> omega

theorem rankTable_spec (marks : Array Bool) :
    (rankTable marks).2 = marks.count true ∧
    (rankTable marks).1.size = marks.size ∧
    ∀ i, i < marks.size → (rankTable marks).1[i]? = some ((marks.toList.take i).count true) := by
  have spec := foldl_rankStep marks.toList #[] 0
  simp only [rankTable, ← Array.foldl_toList]
  refine ⟨by simpa using spec.1, by simpa using spec.2.1, ?_⟩
  intro i bound
  simpa using spec.2.2.2 i (by simpa using bound)

theorem filterMap_zip_getElem {α β : Type} (h : α → β) :
    ∀ (L : List α) (M : List Bool) (i : Nat) (c : α), L[i]? = some c → M[i]? = some true →
      ((L.zip M).filterMap fun entry => if entry.2 then some (h entry.1) else none)[(M.take i).count true]? =
        some (h c) := by
  intro L
  induction L with
  | nil => intro M i c found; simp at found
  | cons a L ih =>
    intro M i c found marked
    cases M with
    | nil => simp at marked
    | cons m M =>
      cases i with
      | zero =>
        simp at found marked
        subst found; subst marked
        simp
      | succ j =>
        simp only [List.getElem?_cons_succ] at found marked
        have := ih M j c found marked
        cases m <;> simpa [List.count_cons] using this

theorem filterMap_zip_length {α β : Type} (h : α → β) :
    ∀ (L : List α) (M : List Bool), L.length = M.length →
      ((L.zip M).filterMap fun entry => if entry.2 then some (h entry.1) else none).length = M.count true := by
  intro L
  induction L with
  | nil => intro M same; cases M <;> simp_all
  | cons a L ih =>
    intro M same
    cases M with
    | nil => simp at same
    | cons m M =>
      have := ih M (by simpa using same)
      cases m <;> simp [this]

theorem count_take_le (M : List Bool) {a b : Nat} (le : a ≤ b) :
    (M.take a).count true ≤ (M.take b).count true := by
  have : (M.take b).take a = M.take a := by rw [List.take_take]; congr 1; omega
  rw [← this]
  exact (List.take_sublist _ _).count_le _

theorem count_take_succ (M : List Bool) {i : Nat} (marked : M[i]? = some true) :
    (M.take (i + 1)).count true = (M.take i).count true + 1 := by
  rw [List.take_add_one, marked]; simp

theorem count_take_lt (M : List Bool) {i j : Nat} (lt : i < j) (marked : M[i]? = some true) :
    (M.take i).count true < (M.take j).count true := by
  have := count_take_le M (show i + 1 ≤ j by omega)
  rw [count_take_succ M marked] at this; omega

theorem count_take_lt_count (M : List Bool) {i : Nat} (marked : M[i]? = some true) :
    (M.take i).count true < M.count true := by
  have bound : i < M.length := (List.getElem?_eq_some_iff.mp marked).1
  have := count_take_lt M bound marked
  rwa [List.take_length] at this

theorem compact_size (f : Nat → Nat) (heap : Array Cell) (marks : Array Bool)
    (size : marks.size = heap.size) : (compact f heap marks).size = marks.count true := by
  rw [← Array.length_toList, compact, Array.toList_filterMap, Array.toList_zip, ← Array.count_toList]
  exact filterMap_zip_length _ _ _ (by simpa using size.symm)

theorem compact_getElem (f : Nat → Nat) (heap : Array Cell) (marks : Array Bool)
    {a : Nat} {c : Cell} (found : heap[a]? = some c) (marked : marks[a]? = some true) :
    (compact f heap marks)[(marks.toList.take a).count true]? = some (renameCell f c) := by
  rw [← Array.getElem?_toList, compact, Array.toList_filterMap, Array.toList_zip]
  exact filterMap_zip_getElem _ _ _ _ _ (by simpa using found) (by simpa using marked)

/-! ## The renaming simulation -/

def AllIn (D : Nat → Prop) (addresses : List Nat) : Prop := ∀ x ∈ addresses, D x

/-- Two heaps agree under a renaming `f` on a domain `D`: `D` contains everything past
the first heap (where `f` is the shift between the two ends), `f` is injective on `D`,
and every `D`-cell of the first heap is, renamed, the `f`-image cell of the second, with
its addresses again in `D`. Nothing is said about cells outside `D` (the garbage). -/
structure HeapRel (f : Nat → Nat) (D : Nat → Prop) (heap heap' : Array Cell) : Prop where
  size_le : heap'.size ≤ heap.size
  beyond : ∀ a, heap.size ≤ a → D a ∧ f a + heap.size = a + heap'.size
  inj : ∀ a b, D a → D b → f a = f b → a = b
  cells : ∀ a, D a → a < heap.size →
    ∃ c, heap[a]? = some c ∧ heap'[f a]? = some (renameCell f c) ∧ AllIn D (cellAddresses c)

/-- **The simulation relation.** `t` is `s` renamed by `f` on everything `s` can reach
(`D` is closed under the heap and contains the roots): same control, same stack, and
the `D`-cells agree. -/
structure Related (f : Nat → Nat) (D : Nat → Prop) (s t : State) : Prop where
  heap : HeapRel f D s.heap t.heap
  controlIn : AllIn D (controlAddresses s.control)
  control : t.control = renameControl f s.control
  stackIn : ∀ frame ∈ s.stack, AllIn D (frameAddresses frame)
  stack : t.stack = s.stack.map (renameFrame f)

/-- The domain `collect` traces: the live cells and everything past the heap. -/
def liveDomain (state : State) (a : Nat) : Prop :=
  state.heap.size ≤ a ∨ (liveMarks state)[a]? = some true

theorem liveDomain_of_not_false {state : State} {x : Nat}
    (notFalse : (liveMarks state)[x]? ≠ some false) : liveDomain state x := by
  by_cases bound : x < state.heap.size
  · right
    have size := (liveMarks_spec state).1
    have : x < (liveMarks state).size := by omega
    rw [Array.getElem?_eq_getElem this] at notFalse ⊢
    cases value : (liveMarks state)[x]
    · rw [value] at notFalse; exact absurd rfl notFalse
    · rfl
  · left; omega

theorem collectRenaming_live {state : State} {a : Nat} (marked : (liveMarks state)[a]? = some true) :
    collectRenaming state a = ((liveMarks state).toList.take a).count true := by
  have size := (liveMarks_spec state).1
  have bound : a < state.heap.size := by rw [← size]; exact bound_of_some marked
  have ranks := rankTable_spec (liveMarks state)
  simp only [collectRenaming, relocate, bound, if_true]
  rw [Array.getD_eq_getD_getElem?, ranks.2.2 a (by omega)]
  rfl

theorem collectRenaming_beyond {state : State} {a : Nat} (past : state.heap.size ≤ a) :
    collectRenaming state a = a - state.heap.size + (liveMarks state).count true := by
  have ranks := rankTable_spec (liveMarks state)
  simp only [collectRenaming, relocate, show ¬ a < state.heap.size by omega, if_false]
  rw [ranks.1]

theorem collect_heap_size (state : State) :
    (collect state).heap.size = (liveMarks state).count true :=
  compact_size _ _ _ (liveMarks_spec state).1

/-- **Collection is a renaming of the state it collects.** -/
theorem related_collect (state : State) :
    Related (collectRenaming state) (liveDomain state) state (collect state) := by
  obtain ⟨size, roots, closed⟩ := liveMarks_spec state
  have live_lt : ∀ a, (liveMarks state)[a]? = some true →
      collectRenaming state a < (liveMarks state).count true := by
    intro a marked
    rw [collectRenaming_live marked, ← Array.count_toList]
    exact count_take_lt_count _ (by simpa using marked)
  have count_le : (liveMarks state).count true ≤ state.heap.size := by
    rw [← size, ← Array.count_toList, ← Array.length_toList]; exact List.count_le_length
  refine ⟨⟨?_, ?_, ?_, ?_⟩, ?_, rfl, ?_, rfl⟩
  · rw [collect_heap_size]; exact count_le
  · intro a past
    refine ⟨.inl past, ?_⟩
    rw [collectRenaming_beyond past, collect_heap_size]; omega
  · intro a b inA inB same
    rcases inA with pastA | markedA <;> rcases inB with pastB | markedB
    · rw [collectRenaming_beyond pastA, collectRenaming_beyond pastB] at same; omega
    · have := live_lt b markedB; rw [collectRenaming_beyond pastA] at same; omega
    · have := live_lt a markedA; rw [collectRenaming_beyond pastB] at same; omega
    · rw [collectRenaming_live markedA, collectRenaming_live markedB] at same
      rcases Nat.lt_trichotomy a b with lt | eq | gt
      · have := count_take_lt (liveMarks state).toList lt (by simpa using markedA); omega
      · exact eq
      · have := count_take_lt (liveMarks state).toList gt (by simpa using markedB); omega
  · intro a inA bound
    have marked : (liveMarks state)[a]? = some true := by
      rcases inA with past | marked
      · omega
      · exact marked
    obtain ⟨c, found⟩ : ∃ c, state.heap[a]? = some c := ⟨_, Array.getElem?_eq_getElem bound⟩
    refine ⟨c, found, ?_, ?_⟩
    · rw [collectRenaming_live marked]
      exact compact_getElem _ _ _ found marked
    · intro x member
      apply liveDomain_of_not_false
      exact closed a x marked (by simp [children, found, member])
  · intro x member
    exact liveDomain_of_not_false (roots x (List.mem_append_left _ member))
  · intro frame member x inFrame
    exact liveDomain_of_not_false (roots x (List.mem_append_right _ (List.mem_flatMap.mpr ⟨frame, member, inFrame⟩)))


/-! ## Heap agreement is preserved by allocation and update -/

namespace HeapRel
variable {f : Nat → Nat} {D : Nat → Prop} {heap heap' : Array Cell}

theorem lookup (hr : HeapRel f D heap heap') {a : Nat} (inD : D a) :
    heap'[f a]? = (heap[a]?).map (renameCell f) := by
  by_cases bound : a < heap.size
  · obtain ⟨c, found, found', _⟩ := hr.cells a inD bound
    rw [found, found']; rfl
  · have shift := (hr.beyond a (Nat.le_of_not_lt bound)).2
    rw [Array.getElem?_eq_none (Nat.le_of_not_lt bound), Array.getElem?_eq_none (by omega)]
    rfl

theorem cellIn (hr : HeapRel f D heap heap') {a : Nat} {c : Cell} (inD : D a)
    (found : heap[a]? = some c) : AllIn D (cellAddresses c) := by
  obtain ⟨c', found', _, inC⟩ := hr.cells a inD (bound_of_some found)
  rw [found] at found'; cases found'; exact inC

theorem image_size (hr : HeapRel f D heap heap') : f heap.size = heap'.size ∧ D heap.size := by
  have := hr.beyond heap.size (Nat.le_refl _); exact ⟨by omega, this.1⟩

theorem image_size_succ (hr : HeapRel f D heap heap') :
    f (heap.size + 1) = heap'.size + 1 ∧ D (heap.size + 1) := by
  have := hr.beyond (heap.size + 1) (Nat.le_succ _); exact ⟨by omega, this.1⟩

theorem push (hr : HeapRel f D heap heap') {c : Cell} (cIn : AllIn D (cellAddresses c)) :
    HeapRel f D (heap.push c) (heap'.push (renameCell f c)) := by
  have sizeLe := hr.size_le
  refine ⟨by simp; omega, ?_, hr.inj, ?_⟩
  · intro a past
    simp at past
    have := hr.beyond a (by omega)
    exact ⟨this.1, by simp; omega⟩
  · intro a inD bound
    simp at bound
    by_cases old : a < heap.size
    · obtain ⟨c', found, found', inC⟩ := hr.cells a inD old
      have lt : f a < heap'.size := bound_of_some found'
      refine ⟨c', ?_, ?_, inC⟩
      · simp [Array.getElem?_push, Nat.ne_of_lt old, found]
      · simp [Array.getElem?_push, Nat.ne_of_lt lt, found']
    · have eq : a = heap.size := by omega
      subst eq
      refine ⟨c, by simp, ?_, cIn⟩
      rw [hr.image_size.1]; simp

theorem set (hr : HeapRel f D heap heap') {a : Nat} {c : Cell} (inD : D a) (bound : a < heap.size)
    (cIn : AllIn D (cellAddresses c)) :
    HeapRel f D (heap.set! a c) (heap'.set! (f a) (renameCell f c)) := by
  obtain ⟨_, _, found', _⟩ := hr.cells a inD bound
  have lt : f a < heap'.size := bound_of_some found'
  refine ⟨by simp; exact hr.size_le, ?_, hr.inj, ?_⟩
  · intro b past; simp at past; have := hr.beyond b past; exact ⟨this.1, by simp; exact this.2⟩
  · intro b inB boundB
    simp at boundB
    by_cases same : a = b
    · subst same
      exact ⟨c, by simp [bound],
        by simp [lt], cIn⟩
    · obtain ⟨c', found, found'', inC⟩ := hr.cells b inB boundB
      have diff : f a ≠ f b := fun h => same (hr.inj a b inD inB h)
      exact ⟨c', by simp [same, found],
        by simp [diff, found''], inC⟩

end HeapRel

theorem allocateFields_foldl {f : Nat → Nat} {D : Nat → Prop} (environment : List Nat)
    (environmentIn : AllIn D environment) (fields : List (String × Term)) :
    ∀ (heap heap' : Array Cell) (acc : List (String × Nat)),
      HeapRel f D heap heap' → AllIn D (acc.map Prod.snd) →
      HeapRel f D
          (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,prior.1.size)::prior.2)) (heap,acc)).1
          (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.suspended ⟨field.2,environment.map f⟩),(field.1,prior.1.size)::prior.2))
            (heap',acc.map fun field => (field.1, f field.2))).1 ∧
        (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.suspended ⟨field.2,environment.map f⟩),(field.1,prior.1.size)::prior.2))
            (heap',acc.map fun field => (field.1, f field.2))).2 =
          (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,prior.1.size)::prior.2))
            (heap,acc)).2.map (fun field => (field.1, f field.2)) ∧
        AllIn D ((fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,prior.1.size)::prior.2))
            (heap,acc)).2.map Prod.snd) := by
  induction fields with
  | nil => intro heap heap' acc hr accIn; exact ⟨hr, rfl, accIn⟩
  | cons field rest ih =>
    intro heap heap' acc hr accIn
    have ⟨image, sizeIn⟩ := hr.image_size
    have pushed := hr.push (c := .suspended ⟨field.2, environment⟩) environmentIn
    have accIn' : AllIn D (((field.1, heap.size) :: acc).map Prod.snd) := by
      intro x member
      simp only [List.map_cons, List.mem_cons] at member
      rcases member with rfl | member
      · exact sizeIn
      · exact accIn x member
    have := ih _ _ _ pushed accIn'
    simp only [List.foldl_cons]
    simp only [List.map_cons, image] at this
    exact this

theorem allocateFields_related {f : Nat → Nat} {D : Nat → Prop} {heap heap' : Array Cell}
    (hr : HeapRel f D heap heap') {environment : List Nat} (environmentIn : AllIn D environment)
    (fields : List (String × Term)) :
    HeapRel f D (allocateFields heap environment fields).1
        (allocateFields heap' (environment.map f) fields).1 ∧
      (allocateFields heap' (environment.map f) fields).2 =
        (allocateFields heap environment fields).2.map (fun field => (field.1, f field.2)) ∧
      AllIn D ((allocateFields heap environment fields).2.map Prod.snd) := by
  obtain ⟨hr', same, inside⟩ := allocateFields_foldl environment environmentIn fields heap heap' []
    hr (fun _ member => by cases member)
  refine ⟨hr', ?_, ?_⟩
  · simp only [allocateFields]
    simp only [List.map_nil] at same
    rw [same, List.map_reverse]
  · intro x member
    simp only [allocateFields, List.map_reverse, List.mem_reverse] at member
    exact inside x member


/-! ## Lockstep: one machine transition -/

theorem forcingShared_rename (f : Nat → Nat) (stack : List Frame) :
    forcingShared (stack.map (renameFrame f)) = forcingShared stack := by
  induction stack with
  | nil => rfl
  | cons frame rest ih =>
    simp only [forcingShared, List.map_cons, List.any_cons] at ih ⊢
    rw [ih]; cases frame <;> rfl

theorem valueTerm_rename (f : Nat → Nat) (value : RuntimeValue) :
    valueTerm (renameValue f value) = valueTerm value := by
  cases value <;> rfl

theorem scalarValue_rename {f : Nat → Nat} {result : Term} {next : RuntimeValue}
    (scalar : scalarValue result = some next) : renameValue f next = next ∧ valueAddresses next = [] := by
  cases result <;> simp [scalarValue] at scalar <;> subst scalar <;> exact ⟨rfl, rfl⟩

theorem allIn_nil (D : Nat → Prop) : AllIn D [] := fun _ member => by cases member

theorem allIn_cons {D : Nat → Prop} {a : Nat} {rest : List Nat} (head : D a) (tail : AllIn D rest) :
    AllIn D (a :: rest) := by
  intro x member
  rcases List.mem_cons.mp member with rfl | member
  · exact head
  · exact tail x member

theorem allIn_append {D : Nat → Prop} {first second : List Nat} (one : AllIn D first)
    (two : AllIn D second) : AllIn D (first ++ second) := by
  intro x member
  rcases List.mem_append.mp member with member | member
  · exact one x member
  · exact two x member

theorem frames_cons {D : Nat → Prop} {frame : Frame} {rest : List Frame}
    (head : AllIn D (frameAddresses frame)) (tail : ∀ frame ∈ rest, AllIn D (frameAddresses frame)) :
    ∀ frame' ∈ frame :: rest, AllIn D (frameAddresses frame') :=
  List.forall_mem_cons.mpr ⟨head, tail⟩

theorem allocateNativeFields_foldl {f : Nat → Nat} {D : Nat → Prop} (fields : List (String × Data)) :
    ∀ (heap heap' : Array Cell) (acc : List (String × Nat)),
      HeapRel f D heap heap' → AllIn D (acc.map Prod.snd) →
      HeapRel f D
          (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.native field.2), (field.1, prior.1.size) :: prior.2)) (heap,acc)).1
          (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.native field.2), (field.1, prior.1.size) :: prior.2))
            (heap',acc.map fun field => (field.1, f field.2))).1 ∧
        (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.native field.2), (field.1, prior.1.size) :: prior.2))
            (heap',acc.map fun field => (field.1, f field.2))).2 =
          (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.native field.2), (field.1, prior.1.size) :: prior.2))
            (heap,acc)).2.map (fun field => (field.1, f field.2)) ∧
        AllIn D ((fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.native field.2), (field.1, prior.1.size) :: prior.2))
            (heap,acc)).2.map Prod.snd) ∧
        heap.size ≤ (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
            (prior.1.push (.native field.2), (field.1, prior.1.size) :: prior.2)) (heap,acc)).1.size := by
  induction fields with
  | nil => intro heap heap' acc hr accIn; exact ⟨hr, rfl, accIn, Nat.le_refl _⟩
  | cons field rest ih =>
    intro heap heap' acc hr accIn
    have ⟨image, sizeIn⟩ := hr.image_size
    have pushed := hr.push (c := .native field.2) (fun _ member => by cases member)
    have accIn' : AllIn D (((field.1, heap.size) :: acc).map Prod.snd) := by
      intro x member
      simp only [List.map_cons, List.mem_cons] at member
      rcases member with rfl | member
      · exact sizeIn
      · exact accIn x member
    have := ih _ _ _ pushed accIn'
    simp only [List.foldl_cons]
    simp only [List.map_cons, image, renameCell] at this
    refine ⟨this.1, this.2.1, this.2.2.1, ?_⟩
    have := this.2.2.2
    simp at this ⊢
    omega

/-- Forcing a native cell allocates the same immediate children at both heap ends. -/
theorem forceNative_related {f : Nat → Nat} {D : Nat → Prop} {heap heap' : Array Cell}
    (hr : HeapRel f D heap heap') (origin : Data) :
    HeapRel f D (forceNative heap origin).1 (forceNative heap' origin).1 ∧
      (forceNative heap' origin).2 = renameValue f (forceNative heap origin).2 ∧
      AllIn D (valueAddresses (forceNative heap origin).2) ∧
      heap.size ≤ (forceNative heap origin).1.size := by
  have ⟨image, sizeIn⟩ := hr.image_size
  cases origin with
  | natural n => exact ⟨hr, rfl, allIn_nil D, Nat.le_refl _⟩
  | boolean b => exact ⟨hr, rfl, allIn_nil D, Nat.le_refl _⟩
  | label s => exact ⟨hr, rfl, allIn_nil D, Nat.le_refl _⟩
  | variant tag payload =>
    have pushed := hr.push (c := .native payload) (fun _ member => by cases member)
    refine ⟨pushed, ?_, allIn_cons sizeIn (allIn_nil D), by simp [forceNative]⟩
    simp [forceNative, renameValue, image]
  | record fields =>
    obtain ⟨hr', same, inside, grows⟩ := allocateNativeFields_foldl fields heap heap' [] hr
      (fun _ member => by cases member)
    simp only [List.map_nil] at same
    refine ⟨hr', ?_, ?_, grows⟩
    · simp only [forceNative, allocateNativeFields, renameValue]
      rw [same, List.map_reverse]
    · intro x member
      simp only [forceNative, allocateNativeFields, valueAddresses, List.map_reverse, List.mem_reverse] at member
      exact inside x member

/-- **Lockstep.** A related pair steps to a related pair: the renaming and its domain
are fixed, and the two machines allocate at the two heap ends (`f heap.size = heap'.size`). -/
theorem related_stepRaw {f : Nat → Nat} {D : Nat → Prop} {s t : State} (related : Related f D s t) :
    Related f D (stepRaw s) (stepRaw t) := by
  obtain ⟨hr, controlIn, controlEq, stackIn, stackEq⟩ := related
  obtain ⟨heap, control, stack⟩ := s
  obtain ⟨heap', control', stack'⟩ := t
  simp only at hr controlIn controlEq stackIn stackEq
  subst controlEq stackEq
  have ⟨image, sizeIn⟩ := hr.image_size
  have ⟨image1, sizeIn1⟩ := hr.image_size_succ
  cases control with
  | complete v => exact ⟨hr, controlIn, rfl, stackIn, rfl⟩
  | refused r => exact ⟨hr, controlIn, rfl, stackIn, rfl⟩
  | blackhole a => exact ⟨hr, controlIn, rfl, stackIn, rfl⟩
  | yielded p => exact ⟨hr, controlIn, rfl, stackIn, rfl⟩
  | nativeApplication function argument remaining =>
    cases remaining <;> exact ⟨hr, allIn_nil D, rfl, frames_cons (allIn_nil D) stackIn, rfl⟩
  | enter a =>
    have inA : D a := controlIn a (List.mem_singleton_self a)
    simp only [stepRaw, renameControl]
    rw [hr.lookup inA]
    cases found : heap[a]? with
    | none => exact ⟨hr, allIn_nil D, rfl, stackIn, rfl⟩
    | some cell =>
      have cellIn := hr.cellIn inA found
      cases cell with
      | evaluating o => exact ⟨hr, controlIn, rfl, stackIn, rfl⟩
      | cached o v => exact ⟨hr, fun x member => cellIn x (List.mem_append_right _ member), rfl, stackIn, rfl⟩
      | nativeCached o v => exact ⟨hr, cellIn, rfl, stackIn, rfl⟩
      | native o =>
        obtain ⟨hr', same, valueIn, grows⟩ := forceNative_related hr o
        have bound : a < (forceNative heap o).1.size := Nat.lt_of_lt_of_le (bound_of_some found) grows
        have set := hr'.set inA bound (c := .nativeCached o (forceNative heap o).2) valueIn
        refine ⟨?_, valueIn, ?_, stackIn, rfl⟩
        · show HeapRel f D ((forceNative heap o).1.set! a (.nativeCached o (forceNative heap o).2))
            ((forceNative heap' o).1.set! (f a) (.nativeCached o (forceNative heap' o).2))
          rw [same]; exact set
        · show Control.returned (forceNative heap' o).2 = renameControl f (.returned (forceNative heap o).2)
          rw [same]; rfl
      | suspended o =>
        exact ⟨hr.set inA (bound_of_some found) (c := .evaluating o) cellIn, cellIn, rfl,
          frames_cons (allIn_cons inA (allIn_nil D)) stackIn, rfl⟩
  | evaluate term env =>
    have envIn : AllIn D env := controlIn
    cases term with
    | bound i =>
      simp only [stepRaw, renameControl]
      rw [List.getElem?_map]
      cases found : env[i]? with
      | none => exact ⟨hr, allIn_nil D, rfl, stackIn, rfl⟩
      | some a => exact ⟨hr, allIn_cons (envIn a (List.mem_of_getElem? found)) (allIn_nil D), rfl, stackIn, rfl⟩
    | lam body => exact ⟨hr, envIn, rfl, stackIn, rfl⟩
    | nat n => exact ⟨hr, allIn_nil D, rfl, stackIn, rfl⟩
    | boolean b => exact ⟨hr, allIn_nil D, rfl, stackIn, rfl⟩
    | label l => exact ⟨hr, allIn_nil D, rfl, stackIn, rfl⟩
    | app fn arg => exact ⟨hr, envIn, rfl, frames_cons envIn stackIn, rfl⟩
    | mix lower upper => exact ⟨hr, envIn, rfl, stackIn, rfl⟩
    | fix spec inherited =>
      have pushed := hr.push (c := .suspended ⟨Term.app (Term.app (spec.rename Nat.succ) (.bound 0))
        (inherited.rename Nat.succ), heap.size :: env⟩) (allIn_cons sizeIn envIn)
      simp only [renameCell, renameClosure, List.map_cons, image] at pushed
      refine ⟨pushed, allIn_cons sizeIn (allIn_nil D), ?_, stackIn, rfl⟩
      simp [stepRaw, renameControl, image]
    | specification descriptor extension =>
      have pushed := (hr.push (c := .suspended ⟨descriptor, env⟩) envIn).push
        (c := .suspended ⟨extension, env⟩) envIn
      refine ⟨pushed, allIn_cons sizeIn (allIn_cons sizeIn1 (allIn_nil D)), ?_, stackIn, rfl⟩
      simp [stepRaw, renameControl, renameValue, image, image1]
    | prototype spec target =>
      have pushed := (hr.push (c := .suspended ⟨spec, env⟩) envIn).push
        (c := .suspended ⟨target, env⟩) envIn
      refine ⟨pushed, allIn_cons sizeIn (allIn_cons sizeIn1 (allIn_nil D)), ?_, stackIn, rfl⟩
      simp [stepRaw, renameControl, renameValue, image, image1]
    | reflect body => exact ⟨hr, envIn, rfl, frames_cons (allIn_nil D) stackIn, rfl⟩
    | metadata body => exact ⟨hr, envIn, rfl, frames_cons (allIn_nil D) stackIn, rfl⟩
    | project body => exact ⟨hr, envIn, rfl, frames_cons (allIn_nil D) stackIn, rfl⟩
    | record fields =>
      obtain ⟨hr', same, inside⟩ := allocateFields_related hr envIn fields
      refine ⟨hr', inside, ?_, stackIn, rfl⟩
      simp only [stepRaw, renameControl, renameValue, same]
    | get target name => exact ⟨hr, envIn, rfl, frames_cons (allIn_nil D) stackIn, rfl⟩
    | extend inherited fields => exact ⟨hr, envIn, rfl, frames_cons envIn stackIn, rfl⟩
    | ifZero value zero successorBody => exact ⟨hr, envIn, rfl, frames_cons envIn stackIn, rfl⟩
    | binary primitive left right => exact ⟨hr, envIn, rfl, frames_cons envIn stackIn, rfl⟩
    | inject tag payload =>
      have pushed := hr.push (c := .suspended ⟨payload, env⟩) envIn
      refine ⟨pushed, allIn_cons sizeIn (allIn_nil D), ?_, stackIn, rfl⟩
      simp [stepRaw, renameControl, renameValue, image]
    | case scrutinee arms => exact ⟨hr, envIn, rfl, frames_cons envIn stackIn, rfl⟩
    | ifBool condition whenTrue whenFalse => exact ⟨hr, envIn, rfl, frames_cons envIn stackIn, rfl⟩
    | done value => exact ⟨hr, envIn, rfl, stackIn, rfl⟩
    | toData value => exact ⟨hr, envIn, rfl, stackIn, rfl⟩
    | unary primitive argument => exact ⟨hr, envIn, rfl, frames_cons (allIn_nil D) stackIn, rfl⟩
    | textJoin list separator => exact ⟨hr, envIn, rfl, frames_cons envIn stackIn, rfl⟩
    | perform plan =>
      simp only [stepRaw, renameControl, forcingShared_rename]
      cases shared : forcingShared stack with
      | true => exact ⟨hr, allIn_nil D, rfl, stackIn, rfl⟩
      | false =>
        have pushed := hr.push (c := .suspended ⟨plan, env⟩) envIn
        refine ⟨pushed, allIn_cons sizeIn (allIn_nil D), ?_, stackIn, rfl⟩
        simp [renameControl, image]
  | returned v =>
    have valueIn : AllIn D (valueAddresses v) := controlIn
    cases stack with
    | nil => exact ⟨hr, valueIn, rfl, stackIn, rfl⟩
    | cons frame rest =>
      have ⟨frameIn, restIn⟩ := List.forall_mem_cons.mp stackIn
      cases frame with
      | update a =>
        have inA : D a := frameIn a (List.mem_singleton_self a)
        simp only [stepRaw, renameControl, List.map_cons, renameFrame]
        rw [hr.lookup inA]
        cases found : heap[a]? with
        | none => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
        | some cell =>
          have cellIn := hr.cellIn inA found
          cases cell with
          | suspended o => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
          | cached o w => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
          | native o => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
          | nativeCached o w => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
          | evaluating o =>
            exact ⟨hr.set inA (bound_of_some found) (c := .cached o v) (allIn_append cellIn valueIn),
              valueIn, rfl, restIn, rfl⟩
      | reflect =>
        cases v with
        | prototype spec target =>
          exact ⟨hr, allIn_cons (valueIn spec (by simp [valueAddresses])) (allIn_nil D), rfl, restIn, rfl⟩
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | metadata =>
        cases v with
        | specification descriptor extension =>
          exact ⟨hr, allIn_cons (valueIn descriptor (by simp [valueAddresses])) (allIn_nil D), rfl, restIn, rfl⟩
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | project =>
        cases v with
        | prototype spec target =>
          exact ⟨hr, allIn_cons (valueIn target (by simp [valueAddresses])) (allIn_nil D), rfl, restIn, rfl⟩
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | argument argument environment =>
        cases v with
        | specification descriptor extension =>
          exact ⟨hr, allIn_cons (valueIn extension (by simp [valueAddresses])) (allIn_nil D), rfl, stackIn, rfl⟩
        | closure body captured =>
          have environmentIn : AllIn D environment := frameIn
          have capturedIn : AllIn D captured := valueIn
          have pushed := hr.push (c := .suspended ⟨argument, environment⟩) environmentIn
          refine ⟨pushed, allIn_cons sizeIn capturedIn, ?_, restIn, rfl⟩
          simp [stepRaw, renameControl, renameValue, renameFrame, image]
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | field name =>
        cases v with
        | record fields =>
          simp only [stepRaw, renameControl, renameValue, List.map_cons, renameFrame, List.find?_map,
            Function.comp_def]
          cases found : fields.find? (fun field => field.1 == name) with
          | none => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
          | some entry =>
            have member := List.mem_of_find?_eq_some found
            exact ⟨hr, allIn_cons (valueIn entry.2 (List.mem_map_of_mem member)) (allIn_nil D), rfl, restIn, rfl⟩
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | extend fields environment =>
        cases v with
        | record inherited =>
          have environmentIn : AllIn D environment := frameIn
          obtain ⟨hr', same, inside⟩ := allocateFields_related hr environmentIn fields
          refine ⟨hr', ?_, ?_, restIn, rfl⟩
          · have retainedIn : AllIn D ((inherited.filter
                (fun prior => !(fields.any fun field => field.1 == prior.1))).map Prod.snd) := by
              intro x member
              obtain ⟨entry, kept, eq⟩ := List.mem_map.mp member
              rw [← eq]; exact valueIn _ (List.mem_map_of_mem (List.mem_filter.mp kept).1)
            have := allIn_append inside retainedIn
            rw [← List.map_append] at this
            exact this
          · simp only [stepRaw, renameControl, renameValue, List.map_cons, renameFrame, same,
              List.filter_map, Function.comp_def, List.map_append]
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | condition zero successorBody environment =>
        cases v with
        | natural n =>
          cases n with
          | zero => exact ⟨hr, frameIn, rfl, restIn, rfl⟩
          | succ n =>
            have environmentIn : AllIn D environment := frameIn
            have pushed := hr.push (c := .cached ⟨.nat n, []⟩ (.natural n)) (allIn_nil D)
            refine ⟨pushed, allIn_cons sizeIn environmentIn, ?_, restIn, rfl⟩
            simp [stepRaw, renameControl, renameFrame, renameValue, image]
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | binaryLeft primitive right environment =>
        exact ⟨hr, frameIn, rfl, frames_cons valueIn restIn, rfl⟩
      | binaryRight primitive left =>
        simp only [stepRaw, renameControl, List.map_cons, renameFrame, valueTerm_rename]
        cases computed : (valueTerm left).bind (fun l => (valueTerm v).bind (primitiveResult primitive l)) with
        | none => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
        | some result =>
          dsimp only
          cases scalar : scalarValue result with
          | none => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
          | some next =>
            have ⟨renamed, empty⟩ := scalarValue_rename (f := f) scalar
            refine ⟨hr, ?_, ?_, restIn, rfl⟩
            · show AllIn D (valueAddresses next); rw [empty]; exact allIn_nil D
            · simp [renameControl, renamed]
      | case arms environment =>
        cases v with
        | variant tag payload =>
          simp only [stepRaw, renameControl, renameValue, List.map_cons, renameFrame]
          cases found : arms.find? (fun arm => arm.1 == tag) with
          | none => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
          | some arm =>
            have environmentIn : AllIn D environment := frameIn
            have pushed := hr.push (c := .suspended ⟨.bound 0, [payload]⟩) valueIn
            refine ⟨pushed, allIn_cons sizeIn environmentIn, ?_, restIn, rfl⟩
            simp [renameControl, image]
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | ifBool whenTrue whenFalse environment =>
        cases v with
        | boolean b => cases b <;> exact ⟨hr, frameIn, rfl, restIn, rfl⟩
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | nativeArgument argument =>
        cases v with
        | specification descriptor extension =>
          exact ⟨hr, allIn_cons (valueIn extension (by simp [valueAddresses])) (allIn_nil D), rfl, stackIn, rfl⟩
        | closure body captured =>
          have capturedIn : AllIn D captured := valueIn
          have pushed := hr.push (c := .native argument) (fun _ member => by cases member)
          refine ⟨pushed, allIn_cons sizeIn capturedIn, ?_, restIn, rfl⟩
          simp [stepRaw, renameControl, renameValue, renameFrame, image]
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | unary primitive =>
        simp only [stepRaw, renameControl, List.map_cons, renameFrame, valueTerm_rename]
        cases computed : (valueTerm v).bind (unaryResult primitive) with
        | none => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
        | some result =>
          dsimp only
          cases scalar : scalarValue result with
          | none => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
          | some next =>
            have ⟨renamed, empty⟩ := scalarValue_rename (f := f) scalar
            refine ⟨hr, ?_, ?_, restIn, rfl⟩
            · show AllIn D (valueAddresses next); rw [empty]; exact allIn_nil D
            · simp [renameControl, renamed]
      | joinSeparator list environment =>
        cases v with
        | label separator => exact ⟨hr, frameIn, rfl, frames_cons (allIn_nil D) restIn, rfl⟩
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | joinList separator accumulated first =>
        cases v with
        | variant tag payload =>
          simp only [stepRaw, renameControl, renameValue, List.map_cons, renameFrame]
          by_cases isNil : (tag == "nil") = true
          · simp only [isNil, if_true]
            exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
          · simp only [isNil, Bool.false_eq_true, if_false]
            by_cases isCons : (tag == "cons") = true
            · simp only [isCons, if_true]
              exact ⟨hr, allIn_cons (valueIn payload (by simp [valueAddresses])) (allIn_nil D), rfl,
                frames_cons (allIn_nil D) restIn, rfl⟩
            · simp only [isCons, Bool.false_eq_true, if_false]
              exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | joinCons separator accumulated first =>
        cases v with
        | record fields =>
          simp only [stepRaw, renameControl, renameValue, List.map_cons, renameFrame, List.find?_map,
            Function.comp_def]
          cases foundHead : fields.find? (fun field => field.1 == "head") with
          | none => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
          | some head =>
            cases foundTail : fields.find? (fun field => field.1 == "tail") with
            | none => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
            | some tail =>
              have headIn := valueIn head.2 (List.mem_map_of_mem (List.mem_of_find?_eq_some foundHead))
              have tailIn := valueIn tail.2 (List.mem_map_of_mem (List.mem_of_find?_eq_some foundTail))
              exact ⟨hr, allIn_cons headIn (allIn_nil D), rfl,
                frames_cons (allIn_cons tailIn (allIn_nil D)) restIn, rfl⟩
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩
      | joinHead separator accumulated first tail =>
        cases v with
        | label head =>
          exact ⟨hr, frameIn, rfl, frames_cons (allIn_nil D) restIn, rfl⟩
        | _ => exact ⟨hr, allIn_nil D, rfl, restIn, rfl⟩


/-! ## Bounded runs, resumption and composition -/

/-- Outcomes agree under the renaming: same constructor, same reason, renamed payload,
related retained states. -/
def OutcomeRel (f : Nat → Nat) (D : Nat → Prop) : Outcome → Outcome → Prop
  | .finished value s, .finished value' t =>
    value' = renameValue f value ∧ AllIn D (valueAddresses value) ∧ Related f D s t
  | .suspended reason s, .suspended reason' t => reason' = reason ∧ Related f D s t
  | .divergent address s, .divergent address' t => address' = f address ∧ Related f D s t
  | .refused reason s, .refused reason' t => reason' = reason ∧ Related f D s t
  | .yielded plan s, .yielded plan' t => plan' = f plan ∧ Related f D s t
  | _, _ => False

/-- The one outcome a collected state may improve on: running out of heap. -/
def ranOutOfHeap : Outcome → Bool
  | .suspended .capacity _ => true
  | _ => false

theorem Related.stack_length {f : Nat → Nat} {D : Nat → Prop} {s t : State} (related : Related f D s t) :
    t.stack.length = s.stack.length := by
  rw [related.stack, List.length_map]

/-- The gap between the two heap ends is fixed by the renaming: every pair related by
`f` has the same gap (allocation is lockstep). -/
theorem Related.gap {f : Nat → Nat} {D : Nat → Prop} {s t s' t' : State} (one : Related f D s t)
    (two : Related f D s' t') : s.heap.size - t.heap.size = s'.heap.size - t'.heap.size := by
  have a := (one.heap.beyond (s.heap.size + s'.heap.size) (by omega)).2
  have b := (two.heap.beyond (s.heap.size + s'.heap.size) (by omega)).2
  have c := one.heap.size_le
  have d := two.heap.size_le
  omega

theorem runBounded_zero_related {f : Nat → Nat} {D : Nat → Prop} {s t : State} (related : Related f D s t)
    (limits limits' : Limits) : OutcomeRel f D (runBounded limits 0 s) (runBounded limits' 0 t) := by
  have controlEq := related.control
  cases control : s.control <;> rw [control] at controlEq <;>
    simp only [runBounded, control, controlEq, renameControl, OutcomeRel, true_and] <;>
    first
      | exact related
      | exact ⟨by have inside := related.controlIn; rw [control] at inside; exact inside, related⟩

/-- An active control is the only one `step` advances. -/
def active : Control → Bool
  | .evaluate _ _ | .enter _ | .returned _ | .nativeApplication _ _ _ => true
  | _ => false

theorem runBounded_succ_active {limits : Limits} {ticks : Nat} {s : State} (isActive : active s.control = true) :
    runBounded limits (ticks + 1) s =
      if (stepRaw s).heap.size ≤ limits.heap ∧ (stepRaw s).stack.length ≤ limits.stack then
        runBounded limits ticks (stepRaw s) else .suspended .capacity s := by
  have stepEq : step limits s =
      if (stepRaw s).heap.size ≤ limits.heap ∧ (stepRaw s).stack.length ≤ limits.stack then
        .suspended .ticks (stepRaw s) else .suspended .capacity s := by
    cases control : s.control <;> rw [control] at isActive <;> simp [active] at isActive <;>
      simp [step, control]
  simp only [runBounded, stepEq]
  by_cases fits : (stepRaw s).heap.size ≤ limits.heap ∧ (stepRaw s).stack.length ≤ limits.stack <;>
    simp [fits]

theorem runBounded_succ_inactive {limits : Limits} {ticks : Nat} {s : State} (inactive : active s.control = false) :
    runBounded limits (ticks + 1) s = runBounded limits 0 s := by
  cases control : s.control <;> rw [control] at inactive <;> simp [active] at inactive <;>
    simp [runBounded, step, control]

theorem active_rename (f : Nat → Nat) (control : Control) :
    active (renameControl f control) = active control := by
  cases control <;> rfl

/-- `limits'` gives the related state `t` at least the room `limits` gives `s`: a heap
limit short by at most the gap between the two heaps (the cells collection freed), and
no smaller a stack limit. The gap is the same for every pair one renaming relates
(`Related.gap`), so the room is too (`RoomFor.shift`). Two instances: the same limits
(`RoomFor.same`), and limits counted from each state's own heap end
(`collect_resume_segment`'s use in `Kernel.ObjectiveResumeContract`). -/
structure RoomFor (limits limits' : Limits) (s t : State) : Prop where
  heap : limits.heap ≤ limits'.heap + (s.heap.size - t.heap.size)
  stack : limits.stack ≤ limits'.stack

theorem RoomFor.same (limits : Limits) (s t : State) : RoomFor limits limits s t :=
  ⟨Nat.le_add_right _ _, Nat.le_refl _⟩

theorem RoomFor.shift {f : Nat → Nat} {D : Nat → Prop} {limits limits' : Limits} {s t s' t' : State}
    (one : Related f D s t) (two : Related f D s' t') (room : RoomFor limits limits' s t) :
    RoomFor limits limits' s' t' :=
  ⟨by rw [← one.gap two]; exact room.heap, room.stack⟩

/-- `RoomFor`'s refuting pole: one more cell of limit than the related side gets, with no gap
to cover it (its satisfying pole is `RoomFor.same`). -/
theorem not_roomFor_short : ¬ RoomFor ⟨1, 0⟩ ⟨0, 0⟩ (initial (.nat 0)) (initial (.nat 0)) := by
  intro room
  have := room.heap
  simp [initial] at this

/-- **Bounded runs agree**, except where the original ran out of heap, for any limits that
give the related state at least the original's room (`RoomFor`: the collected state, whose
heap is no larger, may go further). -/
theorem related_runBounded {f : Nat → Nat} {D : Nat → Prop} (limits limits' : Limits) :
    ∀ (ticks : Nat) (s t : State), Related f D s t → RoomFor limits limits' s t →
      ranOutOfHeap (runBounded limits ticks s) = false →
      OutcomeRel f D (runBounded limits ticks s) (runBounded limits' ticks t) := by
  intro ticks
  induction ticks with
  | zero => intro s t related _ _; exact runBounded_zero_related related limits limits'
  | succ ticks ih =>
    intro s t related room notCapacity
    have activeT : active t.control = active s.control := by rw [related.control, active_rename]
    cases isActive : active s.control with
    | false =>
      rw [runBounded_succ_inactive isActive, runBounded_succ_inactive (by rw [activeT, isActive])]
      exact runBounded_zero_related related limits limits'
    | true =>
      have next := related_stepRaw related
      have gap := related.gap next
      have nextLe := next.heap.size_le
      have heapRoom := room.heap
      rw [runBounded_succ_active isActive] at notCapacity ⊢
      rw [runBounded_succ_active (by rw [activeT, isActive])]
      by_cases fits : (stepRaw s).heap.size ≤ limits.heap ∧ (stepRaw s).stack.length ≤ limits.stack
      · have fitsT : (stepRaw t).heap.size ≤ limits'.heap ∧ (stepRaw t).stack.length ≤ limits'.stack :=
          ⟨by have := fits.1; omega, by rw [next.stack_length]; exact Nat.le_trans fits.2 room.stack⟩
        rw [if_pos fits] at notCapacity ⊢
        rw [if_pos fitsT]
        exact ih _ _ next (room.shift related next) notCapacity
      · rw [if_neg fits] at notCapacity
        simp [ranOutOfHeap] at notCapacity

/-- **Exact agreement.** Given back the heap it freed (the gap `s.heap.size - t.heap.size`),
the collected run takes exactly the original's transitions, capacity suspensions included. -/
theorem related_runBounded_exact {f : Nat → Nat} {D : Nat → Prop} (limits : Limits) :
    ∀ (ticks : Nat) (s t : State), Related f D s t → s.heap.size ≤ limits.heap →
      OutcomeRel f D (runBounded limits ticks s)
        (runBounded ⟨limits.heap - (s.heap.size - t.heap.size), limits.stack⟩ ticks t) := by
  intro ticks
  induction ticks with
  | zero => intro s t related _; exact runBounded_zero_related related _ _
  | succ ticks ih =>
    intro s t related fitsNow
    have activeT : active t.control = active s.control := by rw [related.control, active_rename]
    cases isActive : active s.control with
    | false =>
      rw [runBounded_succ_inactive isActive, runBounded_succ_inactive (by rw [activeT, isActive])]
      exact runBounded_zero_related related _ _
    | true =>
      have next := related_stepRaw related
      have gap := related.gap next
      have sizeLe := related.heap.size_le
      have nextLe := next.heap.size_le
      rw [runBounded_succ_active isActive, runBounded_succ_active (by rw [activeT, isActive])]
      by_cases fits : (stepRaw s).heap.size ≤ limits.heap ∧ (stepRaw s).stack.length ≤ limits.stack
      · have fitsT : (stepRaw t).heap.size ≤ limits.heap - (s.heap.size - t.heap.size) ∧
            (stepRaw t).stack.length ≤ limits.stack := ⟨by omega, by rw [next.stack_length]; exact fits.2⟩
        rw [if_pos fits, if_pos fitsT]
        have := ih _ _ next fits.1
        rwa [← gap] at this
      · have notT : ¬ ((stepRaw t).heap.size ≤ limits.heap - (s.heap.size - t.heap.size) ∧
            (stepRaw t).stack.length ≤ limits.stack) := by
          intro fitsT; apply fits
          exact ⟨by omega, by rw [← next.stack_length]; exact fitsT.2⟩
        rw [if_neg fits, if_neg notT]
        exact ⟨rfl, related⟩

/-- **Resumption agrees**, with any response term (a response captures no address). -/
theorem related_resume {f : Nat → Nat} {D : Nat → Prop} {s t : State} (related : Related f D s t)
    (response : Term) {s' : State} (resumed : resume response s = some s') :
    ∃ t', resume response t = some t' ∧ Related f D s' t' := by
  obtain ⟨plan, yielded⟩ := resume_requires_yield response s (by rw [resumed]; rfl)
  have controlT : t.control = .yielded (f plan) := by rw [related.control, yielded]; rfl
  simp only [resume, yielded] at resumed
  cases resumed
  refine ⟨{t with control := .evaluate response []}, by simp [resume, controlT], ?_⟩
  exact ⟨related.heap, allIn_nil D, rfl, related.stackIn, related.stack⟩


/-! ## Hosted forcing agrees exactly under the room the collector freed

`forceHostedFrom` (the runner a turn uses) admits each transition against the hosted
tariff (`textStepCost`, which reads only scalars of the control and the top frame) and
against the heap limit. A collected state's heap is smaller by the gap `collect` freed;
given limits short by exactly that gap (`ExactRoom`, which `limitsPast` provides), both
runs take the same transitions and spend the same ticks, capacity suspensions included. -/

open Minidregg.Theory.ObjectiveBendDemandData

/-- `limits'` gives the related state exactly the room `limits` gives the original: the
heap limit short by the gap between the two heaps, the same stack limit. -/
structure ExactRoom (limits limits' : Limits) (s t : State) : Prop where
  heap : limits.heap = limits'.heap + (s.heap.size - t.heap.size)
  stack : limits.stack = limits'.stack

theorem ExactRoom.shift {f : Nat → Nat} {D : Nat → Prop} {limits limits' : Limits} {s t s' t' : State}
    (one : Related f D s t) (two : Related f D s' t') (room : ExactRoom limits limits' s t) :
    ExactRoom limits limits' s' t' :=
  ⟨by rw [← one.gap two]; exact room.heap, room.stack⟩

theorem textStepCost_rename (f : Nat → Nat) (heap heap' : Array Cell) (control : Control)
    (stack : List Frame) (ticks : Nat) :
    textStepCost ⟨heap', renameControl f control, stack.map (renameFrame f)⟩ ticks =
      textStepCost ⟨heap, control, stack⟩ ticks := by
  cases control with
  | returned value =>
    cases stack with
    | nil => cases value <;> rfl
    | cons frame rest =>
      cases frame with
      | binaryRight p left => cases left <;> cases value <;> cases p <;> rfl
      | unary p => cases value <;> cases p <;> rfl
      | _ => cases value <;> rfl
  | _ => rfl

theorem preflightRemaining_rename (f : Nat → Nat) (control : Control) (stack : List Frame) (ticks : Nat) :
    preflightRemaining (renameControl f control) (stack.map (renameFrame f)) ticks =
      preflightRemaining control stack ticks := by
  cases control with
  | returned value =>
    cases stack with
    | nil => cases value <;> rfl
    | cons frame rest =>
      cases frame with
      | binaryRight p left => cases left <;> cases value <;> cases p <;> rfl
      | _ => cases value <;> rfl
  | _ => rfl

theorem related_textStepCost {f : Nat → Nat} {D : Nat → Prop} {s t : State} (related : Related f D s t)
    (ticks : Nat) : textStepCost t ticks = textStepCost s ticks := by
  obtain ⟨heap', control', stack'⟩ := t
  have hc := related.control
  have hs := related.stack
  simp only at hc hs
  subst hc hs
  exact textStepCost_rename f s.heap heap' s.control s.stack ticks

theorem related_preflightRemaining {f : Nat → Nat} {D : Nat → Prop} {s t : State} (related : Related f D s t)
    (ticks : Nat) : preflightRemaining t.control t.stack ticks = preflightRemaining s.control s.stack ticks := by
  rw [related.control, related.stack]
  exact preflightRemaining_rename f s.control s.stack ticks

/-- The size check `forceHostedFrom` makes before a transition: the related state's next
heap is the original's less the gap; the next stack depth is the same. -/
theorem related_sizesAfter {f : Nat → Nat} {D : Nat → Prop} {s t : State} (related : Related f D s t) :
    (ObjectiveBendDemandMachineFast.sizesAfter t t.stack.length).1 + (s.heap.size - t.heap.size) =
        (ObjectiveBendDemandMachineFast.sizesAfter s s.stack.length).1 ∧
      (ObjectiveBendDemandMachineFast.sizesAfter t t.stack.length).2 =
        (ObjectiveBendDemandMachineFast.sizesAfter s s.stack.length).2 := by
  rw [ObjectiveBendDemandMachineFast.sizesAfter_eq, ObjectiveBendDemandMachineFast.sizesAfter_eq]
  have next := related_stepRaw related
  have gap := related.gap next
  have le := next.heap.size_le
  exact ⟨by simp only; omega, by simp only; exact next.stack_length⟩

theorem forceHostedFrom_inactive {policy : State → Bool} {limits : Limits} {bytes ticks depth : Nat}
    {s : State} (inactive : active s.control = false) :
    forceHostedFrom policy limits bytes (ticks + 1) s depth = (runBounded limits 0 s, ticks + 1) := by
  rw [forceHostedFrom.eq_def]
  cases control : s.control <;> rw [control] at inactive <;> simp [active] at inactive <;> simp [control]

theorem forceHostedFrom_active {policy : State → Bool} {limits : Limits} {bytes ticks depth : Nat}
    {s : State} (isActive : active s.control = true) :
    forceHostedFrom policy limits bytes (ticks + 1) s depth =
      if !policy s || (textStepCost s (ticks + 1)).2 > bytes then (.suspended .capacity s, ticks + 1)
      else if (textStepCost s (ticks + 1)).1 > ticks + 1 then
        (.suspended .ticks s, preflightRemaining s.control s.stack (ticks + 1))
      else if (ObjectiveBendDemandMachineFast.sizesAfter s depth).1 ≤ limits.heap &&
          (ObjectiveBendDemandMachineFast.sizesAfter s depth).2 ≤ limits.stack then
        forceHostedFrom policy limits bytes (ticks + 1 - max 1 (textStepCost s (ticks + 1)).1)
          (ObjectiveBendDemandMachineFast.stepRawFast s) (ObjectiveBendDemandMachineFast.sizesAfter s depth).2
      else (.suspended .capacity s, ticks + 1 - max 1 (textStepCost s (ticks + 1)).1) := by
  rw [forceHostedFrom.eq_def]
  cases control : s.control <;> rw [control] at isActive <;> simp [active] at isActive <;>
    simp only [control]

/-- **Hosted forcing agrees**: under exactly the room collection freed, the related run
ends in the related outcome with exactly the same remaining ticks, for any policy that
related states pass alike. -/
theorem related_forceHostedFrom {f : Nat → Nat} {D : Nat → Prop} {policy : State → Bool}
    (respects : ∀ s t, Related f D s t → policy t = policy s) (limits limits' : Limits) (bytes : Nat) :
    ∀ (ticks : Nat) (s t : State), Related f D s t → ExactRoom limits limits' s t →
      OutcomeRel f D (forceHostedFrom policy limits bytes ticks s s.stack.length).1
          (forceHostedFrom policy limits' bytes ticks t t.stack.length).1 ∧
        (forceHostedFrom policy limits' bytes ticks t t.stack.length).2 =
          (forceHostedFrom policy limits bytes ticks s s.stack.length).2 := by
  intro ticks
  induction ticks using Nat.strongRecOn with
  | ind ticks ih =>
  intro s t related room
  cases ticks with
  | zero =>
    rw [forceHostedFrom.eq_def (state := s), forceHostedFrom.eq_def (state := t)]
    exact ⟨runBounded_zero_related related limits limits', rfl⟩
  | succ n =>
    have activeT : active t.control = active s.control := by rw [related.control, active_rename]
    cases isActive : active s.control with
    | false =>
      rw [forceHostedFrom_inactive isActive, forceHostedFrom_inactive (by rw [activeT, isActive])]
      exact ⟨runBounded_zero_related related limits limits', rfl⟩
    | true =>
      rw [forceHostedFrom_active isActive, forceHostedFrom_active (by rw [activeT, isActive])]
      rw [related_textStepCost related, respects s t related, related_preflightRemaining related]
      have ⟨sizeHeap, sizeStack⟩ := related_sizesAfter related
      have next : Related f D (ObjectiveBendDemandMachineFast.stepRawFast s)
          (ObjectiveBendDemandMachineFast.stepRawFast t) := by
        rw [ObjectiveBendDemandMachineFast.stepRawFast_eq_stepRaw,
          ObjectiveBendDemandMachineFast.stepRawFast_eq_stepRaw]
        exact related_stepRaw related
      have nextDepth : ∀ u, (ObjectiveBendDemandMachineFast.sizesAfter u u.stack.length).2 =
          (ObjectiveBendDemandMachineFast.stepRawFast u).stack.length := by
        intro u
        rw [ObjectiveBendDemandMachineFast.sizesAfter_eq, ObjectiveBendDemandMachineFast.stepRawFast_eq_stepRaw]
      have fitsEq : ((ObjectiveBendDemandMachineFast.sizesAfter t t.stack.length).1 ≤ limits'.heap &&
            (ObjectiveBendDemandMachineFast.sizesAfter t t.stack.length).2 ≤ limits'.stack) =
          ((ObjectiveBendDemandMachineFast.sizesAfter s s.stack.length).1 ≤ limits.heap &&
            (ObjectiveBendDemandMachineFast.sizesAfter s s.stack.length).2 ≤ limits.stack) := by
        have roomHeap := room.heap
        have roomStack := room.stack
        rw [sizeStack, ← roomStack]
        congr 1
        apply Bool.eq_iff_iff.mpr
        simp only [decide_eq_true_eq]
        omega
      have same : OutcomeRel f D (.suspended .capacity s) (.suspended .capacity t) := ⟨rfl, related⟩
      have sameTicks : OutcomeRel f D (.suspended .ticks s) (.suspended .ticks t) := ⟨rfl, related⟩
      split
      · exact ⟨same, rfl⟩
      split
      · exact ⟨sameTicks, rfl⟩
      rw [fitsEq]
      split
      · rw [nextDepth s, nextDepth t]
        exact ih _ (by omega) _ _ next (room.shift related next)
      · exact ⟨same, rfl⟩

theorem related_forceHostedWith {f : Nat → Nat} {D : Nat → Prop} {policy : State → Bool}
    (respects : ∀ s t, Related f D s t → policy t = policy s) (limits limits' : Limits) (bytes ticks : Nat)
    {s t : State} (related : Related f D s t) (room : ExactRoom limits limits' s t) :
    OutcomeRel f D (forceHostedWith policy limits bytes ticks s).1 (forceHostedWith policy limits' bytes ticks t).1 ∧
      (forceHostedWith policy limits' bytes ticks t).2 = (forceHostedWith policy limits bytes ticks s).2 :=
  related_forceHostedFrom respects limits limits' bytes ticks s t related room

/-! ## Extracted Data agrees -/

/-- Extraction results agree: same Data, same remaining budget, related states. -/
def ResultRel (f : Nat → Nat) (D : Nat → Prop) (r r' : Result) : Prop :=
  r'.value = r.value ∧ r'.remaining = r.remaining ∧ Related f D r.state r'.state

theorem related_entered {f : Nat → Nat} {D : Nat → Prop} {s t : State} (related : Related f D s t)
    {address : Nat} (inside : D address) :
    Related f D ⟨s.heap, .enter address, []⟩ ⟨t.heap, .enter (f address), []⟩ :=
  ⟨related.heap, allIn_cons inside (allIn_nil D), rfl, by simp, rfl⟩

theorem foldlM_related {f : Nat → Nat} {D : Nat → Prop}
    {step step' : List (String × Data) × State × Budget → String × Nat →
      Except (Failure × State × Budget) (List (String × Data) × State × Budget)}
    (stepRel : ∀ (acc : List (String × Data)) (st st' : State) (b : Budget) (field : String × Nat)
        (out : List (String × Data) × State × Budget),
      Related f D st st' → D field.2 → step (acc, st, b) field = .ok out →
      ∃ out', step' (acc, st', b) (field.1, f field.2) = .ok out' ∧ out'.1 = out.1 ∧ out'.2.2 = out.2.2 ∧
        Related f D out.2.1 out'.2.1) :
    ∀ (fields : List (String × Nat)) (acc : List (String × Data)) (st st' : State) (b : Budget)
      (out : List (String × Data) × State × Budget),
      Related f D st st' → AllIn D (fields.map Prod.snd) → fields.foldlM step (acc, st, b) = .ok out →
      ∃ out', (fields.map fun field => (field.1, f field.2)).foldlM step' (acc, st', b) = .ok out' ∧
        out'.1 = out.1 ∧ out'.2.2 = out.2.2 ∧ Related f D out.2.1 out'.2.1 := by
  intro fields
  induction fields with
  | nil =>
    intro acc st st' b out related _ folded
    simp [List.foldlM] at folded
    subst folded
    exact ⟨_, rfl, rfl, rfl, related⟩
  | cons field rest ih =>
    intro acc st st' b out related inside folded
    simp only [List.foldlM_cons, except_bind_ok] at folded
    obtain ⟨mid, first, restFolded⟩ := folded
    obtain ⟨mid', first', same1, same2, midRel⟩ :=
      stepRel acc st st' b field mid related (inside field.2 (by simp)) first
    obtain ⟨out', folded', outSame1, outSame2, outRel⟩ :=
      ih mid.1 mid.2.1 mid'.2.1 mid.2.2 out midRel (fun x member => inside x (by simp [member]))
        restFolded
    refine ⟨out', ?_, outSame1, outSame2, outRel⟩
    simp only [List.map_cons, List.foldlM_cons, except_bind_ok]
    refine ⟨mid', first', ?_⟩
    have shape : mid' = (mid.1, mid'.2.1, mid.2.2) := by
      obtain ⟨a, b, c⟩ := mid'
      simp only at same1 same2
      rw [same1, same2]
    rw [shape]; exact folded'

/-- **Materialization agrees**: a related state and the renamed value materialize the
same Data with the same remaining budget, whenever the original succeeds. -/
theorem related_materializeWith {f : Nat → Nat} {D : Nat → Prop} {policy : State → Bool}
    (respects : ∀ s t, Related f D s t → policy t = policy s) (limits limits' : Limits) :
    ∀ (depth : Nat) (budget : Budget) (value : RuntimeValue) (s t : State) (r : Result),
      Related f D s t → ExactRoom limits limits' s t → AllIn D (valueAddresses value) →
      materializeWith policy limits depth budget value s = .ok r →
      ∃ r', materializeWith policy limits' depth budget (renameValue f value) t = .ok r' ∧
        ResultRel f D r r' := by
  intro depth
  induction depth with
  | zero => intro budget value s t r _ _ _ found; simp [materializeWith] at found
  | succ depth ih =>
    intro budget value s t r related room valueIn found
    cases value with
    | natural n =>
      simp [materializeWith] at found
      split at found
      · simp at found
      · split at found
        · simp at found
        · rename_i c1 c2
          simp at found
          refine ⟨{ r with state := t }, ?_, rfl, rfl, ?_⟩
          · rw [← found]; simp [materializeWith, renameValue, c1, c2]
          · rw [← found]; exact related
    | boolean b =>
      simp [materializeWith] at found
      split at found
      · simp at found
      · split at found
        · simp at found
        · rename_i c1 c2
          simp at found
          refine ⟨{ r with state := t }, ?_, rfl, rfl, ?_⟩
          · rw [← found]; simp [materializeWith, renameValue, c1, c2]
          · rw [← found]; exact related
    | label l =>
      simp [materializeWith] at found
      split at found
      · simp at found
      · split at found
        · simp at found
        · rename_i c1 c2
          simp at found
          refine ⟨{ r with state := t }, ?_, rfl, rfl, ?_⟩
          · rw [← found]; simp [materializeWith, renameValue, c1, c2]
          · rw [← found]; exact related
    | closure body environment => simp [materializeWith] at found; split at found <;> simp at found
    | specification metadata extension => simp [materializeWith] at found; split at found <;> simp at found
    | prototype spec target => simp [materializeWith] at found; split at found <;> simp at found
    | variant label payload =>
      have payloadIn : D payload := valueIn payload (by simp [valueAddresses])
      simp [materializeWith] at found
      split at found
      · simp at found
      · split at found
        · simp at found
        · rename_i c1 c2
          have enteredRel := related_entered related payloadIn
          have enteredRoom : ExactRoom limits limits' ⟨s.heap, .enter payload, []⟩ ⟨t.heap, .enter (f payload), []⟩ :=
            ⟨room.heap, room.stack⟩
          cases forced : (forceHostedWith policy limits budget.bytes budget.ticks ⟨s.heap, .enter payload, []⟩).1 with
          | finished value retained =>
            rw [forced] at found
            have ⟨rel, ticksEq⟩ := related_forceHostedWith respects limits limits' budget.bytes budget.ticks
              enteredRel enteredRoom
            rw [forced] at rel
            cases forcedT : (forceHostedWith policy limits' budget.bytes budget.ticks ⟨t.heap, .enter (f payload), []⟩).1 <;>
              rw [forcedT] at rel <;> simp only [OutcomeRel] at rel
            obtain ⟨valueEq, valueIn', retainedRel⟩ := rel
            simp at found
            obtain ⟨a, materialized, rfl⟩ := found
            obtain ⟨a', materialized', aValue, aRemaining, aRel⟩ :=
              ih _ _ _ _ _ retainedRel (enteredRoom.shift enteredRel retainedRel) valueIn' materialized
            refine ⟨⟨.variant label a'.value, a'.state, a'.remaining⟩, ?_, by simp [aValue], aRemaining, aRel⟩
            rw [show renameValue f (.variant label payload) = .variant label (f payload) from rfl]
            simp [materializeWith, c1, c2, forcedT, ticksEq, valueEq, materialized']
          | _ => rw [forced] at found; simp at found
    | record fields =>
      have fieldsIn : AllIn D (fields.map Prod.snd) := valueIn
      obtain ⟨gate, out, folded, rfl⟩ := materializeWith_record_ok found
      have key := foldlM_related (f := f) (D := D) (step := recordStep policy limits depth)
        (step' := recordStep policy limits' depth) ?_ fields [] s t _ out related fieldsIn folded
      · obtain ⟨out', folded', same1, same2, outRel⟩ := key
        refine ⟨⟨.record out'.1.reverse, out'.2.1, out'.2.2⟩, ?_, by simp [same1], by simp [same2], outRel⟩
        have gate' : RecordGate budget (fields.map fun field => (field.1, f field.2)) := by
          obtain ⟨c1, c2, c3, c4⟩ := gate
          refine ⟨c1, by simpa using c2, ?_, by simpa using c4⟩
          simpa [List.map_map, Function.comp_def] using c3
        rw [show renameValue f (.record fields) = .record (fields.map fun field => (field.1, f field.2)) from rfl,
          materializeWith_record_gate gate']
        have start : recordStart budget (fields.map fun field => (field.1, f field.2)) = recordStart budget fields := by
          simp [recordStart]
        rw [start, folded']
        rfl
      · intro acc st st' b field out stRel inField stepped
        unfold recordStep at stepped ⊢
        simp only at stepped ⊢
        split at stepped
        · cases stepped
        · rename_i cond
          simp only [cond, ↓reduceIte, Bool.false_eq_true]
          have enteredRel := related_entered stRel inField
          have stRoom : ExactRoom limits limits' st st' := room.shift related stRel
          have enteredRoom : ExactRoom limits limits' ⟨st.heap, .enter field.2, []⟩ ⟨st'.heap, .enter (f field.2), []⟩ :=
            ⟨stRoom.heap, stRoom.stack⟩
          have ⟨rel, ticksEq⟩ := related_forceHostedWith respects limits limits' b.bytes b.ticks enteredRel enteredRoom
          cases forced : (forceHostedWith policy limits b.bytes b.ticks ⟨st.heap, .enter field.2, []⟩).1 with
          | finished value retained =>
            rw [forced] at stepped rel
            cases forcedT : (forceHostedWith policy limits' b.bytes b.ticks ⟨st'.heap, .enter (f field.2), []⟩).1 <;>
              rw [forcedT] at rel <;> simp only [OutcomeRel] at rel
            obtain ⟨valueEq, valueIn', retainedRel⟩ := rel
            obtain ⟨a, materialized, done⟩ := (except_bind_ok _ _ _).mp stepped
            have := (except_pure_ok _ _).mp done
            subst this
            obtain ⟨a', materialized', aValue, aRemaining, aRel⟩ :=
              ih _ _ _ _ _ retainedRel (enteredRoom.shift enteredRel retainedRel) valueIn' materialized
            refine ⟨((field.1, a'.value) :: acc, a'.state, a'.remaining), ?_, by simp [aValue],
              aRemaining, aRel⟩
            simp only [forcedT, ticksEq, valueEq, materialized']
            rfl
          | _ => rw [forced] at stepped; cases stepped

/-- **Completion agrees**: a finished related state completes to the same Data. -/
theorem related_completeWith {f : Nat → Nat} {D : Nat → Prop} {policy : State → Bool}
    (respects : ∀ s t, Related f D s t → policy t = policy s) (limits limits' : Limits)
    (budget : Budget) {s t : State} {r : Result} (related : Related f D s t) (room : ExactRoom limits limits' s t)
    (found : completeWith policy limits budget s = .ok r) :
    ∃ r', completeWith policy limits' budget t = .ok r' ∧ ResultRel f D r r' := by
  cases allowed : policy s with
  | false => simp [completeWith, allowed] at found
  | true =>
    have allowedT : policy t = true := by rw [respects s t related]; exact allowed
    obtain ⟨hr, controlIn, controlEq, stackIn, stackEq⟩ := related
    obtain ⟨heap, control, stack⟩ := s
    obtain ⟨heap', control', stack'⟩ := t
    simp only at hr controlIn controlEq stackIn stackEq allowed allowedT
    subst controlEq stackEq
    have related : Related f D ⟨heap, control, stack⟩ ⟨heap', renameControl f control, stack.map (renameFrame f)⟩ :=
      ⟨hr, controlIn, rfl, stackIn, rfl⟩
    cases control with
    | complete value =>
      cases stack with
      | nil =>
        simp [completeWith, allowed] at found
        obtain ⟨a, materialized, rest⟩ := found
        obtain ⟨a', materialized', aValue, aRemaining, aRel⟩ :=
          related_materializeWith respects limits limits' _ _ _ _ _ _ related room controlIn materialized
        split at rest
        · rename_i bytes encodedAt
          split at rest
          · simp at rest
          · rename_i small
            simp at rest; subst rest
            refine ⟨a', ?_, aValue, aRemaining, aRel⟩
            simp only [renameControl, List.map_nil] at allowedT materialized'
            simp [completeWith, allowedT, renameControl, materialized', aValue, encodedAt, small]
        · simp at rest
      | cons frame rest => simp [completeWith, allowed] at found
    | _ => simp [completeWith, allowed] at found

/-- **Plan extraction agrees**: a yielded related state's Plan is the same Data. -/
theorem related_yieldedPlanWith {f : Nat → Nat} {D : Nat → Prop} {policy : State → Bool}
    (respects : ∀ s t, Related f D s t → policy t = policy s) (limits limits' : Limits)
    (budget : Budget) {s t : State} {r : Result} (related : Related f D s t) (room : ExactRoom limits limits' s t)
    (found : yieldedPlanWith policy limits budget s = .ok r) :
    ∃ r', yieldedPlanWith policy limits' budget t = .ok r' ∧ ResultRel f D r r' := by
  obtain ⟨hr, controlIn, controlEq, stackIn, stackEq⟩ := related
  obtain ⟨heap, control, stack⟩ := s
  obtain ⟨heap', control', stack'⟩ := t
  simp only at hr controlIn controlEq stackIn stackEq
  subst controlEq stackEq
  cases control with
  | yielded plan =>
    have planIn : D plan := controlIn plan (List.mem_singleton_self plan)
    have enteredRel : Related f D ⟨heap, .enter plan, []⟩ ⟨heap', .enter (f plan), []⟩ :=
      ⟨hr, controlIn, rfl, by simp, rfl⟩
    have enteredRoom : ExactRoom limits limits' ⟨heap, .enter plan, []⟩ ⟨heap', .enter (f plan), []⟩ :=
      ⟨room.heap, room.stack⟩
    simp only [yieldedPlanWith, renameControl] at found ⊢
    have ⟨rel, ticksEq⟩ := related_forceHostedWith respects limits limits' budget.bytes budget.ticks enteredRel enteredRoom
    cases forced : forceHostedWith policy limits budget.bytes budget.ticks ⟨heap, .enter plan, []⟩ with
    | mk outcome ticks =>
      rw [forced] at found rel ticksEq
      cases outcome with
      | finished value retained =>
        cases forcedT : forceHostedWith policy limits' budget.bytes budget.ticks ⟨heap', .enter (f plan), []⟩ with
        | mk outcome' ticks' =>
          rw [forcedT] at rel ticksEq
          simp only at rel ticksEq
          subst ticksEq
          cases outcome' <;> simp only [OutcomeRel] at rel
          obtain ⟨valueEq, valueIn, retainedRel⟩ := rel
          subst valueEq
          simp at found
          obtain ⟨a, materialized, rfl⟩ := found
          obtain ⟨a', materialized', aValue, aRemaining, aRel⟩ :=
            related_materializeWith respects limits limits' _ _ _ _ _ _ retainedRel
              (enteredRoom.shift enteredRel retainedRel) valueIn materialized
          refine ⟨{a' with state := {a'.state with control := .yielded (f plan), stack := stack.map (renameFrame f)}},
            ?_, aValue, aRemaining, aRel.heap, controlIn, rfl, stackIn, rfl⟩
          simp [materialized']
      | _ => simp at found
  | _ => simp [yieldedPlanWith] at found


/-! ## The turn's segment from a collected checkpoint -/

/-- What a run decided, without its states or payload addresses. -/
inductive Verdict where
  | finished
  | suspended (reason : Suspension)
  | divergent
  | refused (reason : Refusal)
  | yielded

def _root_.Minidregg.Theory.ObjectiveBendDemandMachine.Outcome.verdict : Outcome → Verdict
  | .finished _ _ => .finished
  | .suspended reason _ => .suspended reason
  | .divergent _ _ => .divergent
  | .refused reason _ => .refused reason
  | .yielded _ _ => .yielded

theorem OutcomeRel.verdict {f : Nat → Nat} {D : Nat → Prop} {o o' : Outcome} (rel : OutcomeRel f D o o') :
    o'.verdict = o.verdict := by
  cases o <;> cases o' <;> simp only [OutcomeRel] at rel <;> simp only [Outcome.verdict] <;>
    first | rfl | rw [rel.1] | exact rel.elim

theorem OutcomeAgree.verdict {o o' : Outcome} (agree : OutcomeAgree o o') : o'.verdict = o.verdict := by
  cases o <;> cases o' <;> simp [OutcomeAgree, eraseOutcome] at agree <;> simp [Outcome.verdict, agree]

/-- Collection never grows the heap. -/
theorem collect_heap_le (state : State) : (collect state).heap.size ≤ state.heap.size :=
  (related_collect state).heap.size_le

/-- A yielded state stays yielded, at its Plan cell's new address. -/
theorem collect_yielded {state : State} {plan : Nat} (yielded : state.control = .yielded plan) :
    (collect state).control = .yielded (collectRenaming state plan) := by
  rw [(related_collect state).control, yielded]; rfl

/-- `limitsPast` gives a collected state exactly the room its original had. -/
theorem collect_exactRoom {state resumed resumed' : State} (limits : Limits)
    (sameHeap : resumed.heap = state.heap) (sameHeap' : resumed'.heap = (collect state).heap) :
    ExactRoom (limitsPast limits state) (limitsPast limits (collect state)) resumed resumed' := by
  have le := collect_heap_le state
  refine ⟨?_, rfl⟩
  simp only [limitsPast, sameHeap, sameHeap']
  omega

/-- **The turn's segment from a collected state** agrees with the segment from the state
it collected. `Turn.resumeActivity` resumes a checkpoint and runs `forceHostedWith`
under `limitsPast` of the checkpoint's own heap; collecting changes that heap, never the
room past it. For every response, limits, byte allowance and tick budget the hosted runs
end in related outcomes (same constructor and reason, renamed payload, related retained
state) with EXACTLY the same remaining ticks, capacity suspensions included, and a Plan
or result that extracts from the original extracts from the collected run as the same
Data with the same remaining budget. -/
theorem collect_resume_segment {state resumed : State} {response : Term}
    (yielded : resume response state = some resumed) (limits : Limits) (bytes ticks : Nat) (budget : Budget) :
    ∃ resumed', resume response (collect state) = some resumed' ∧
      OutcomeRel (collectRenaming state) (liveDomain state)
        (forceHostedWith (fun _ => true) (limitsPast limits state) bytes ticks resumed).1
        (forceHostedWith (fun _ => true) (limitsPast limits (collect state)) bytes ticks resumed').1 ∧
      (forceHostedWith (fun _ => true) (limitsPast limits (collect state)) bytes ticks resumed').2 =
        (forceHostedWith (fun _ => true) (limitsPast limits state) bytes ticks resumed).2 ∧
      (∀ plan y r, (forceHostedWith (fun _ => true) (limitsPast limits state) bytes ticks resumed).1 = .yielded plan y →
        yieldedPlan (limitsPast limits state) budget y = .ok r →
        ∃ y' r', (forceHostedWith (fun _ => true) (limitsPast limits (collect state)) bytes ticks resumed').1 =
            .yielded (collectRenaming state plan) y' ∧
          yieldedPlan (limitsPast limits (collect state)) budget y' = .ok r' ∧ ResultRel (collectRenaming state) (liveDomain state) r r') ∧
      (∀ value y r, (forceHostedWith (fun _ => true) (limitsPast limits state) bytes ticks resumed).1 = .finished value y →
        complete (limitsPast limits state) budget y = .ok r →
        ∃ y' r', (forceHostedWith (fun _ => true) (limitsPast limits (collect state)) bytes ticks resumed').1 =
            .finished (renameValue (collectRenaming state) value) y' ∧
          complete (limitsPast limits (collect state)) budget y' = .ok r' ∧ ResultRel (collectRenaming state) (liveDomain state) r r') := by
  obtain ⟨resumed', again, related⟩ := related_resume (related_collect state) response yielded
  have room := collect_exactRoom limits (resume_keeps_heap_and_stack _ _ _ yielded).1
    (resume_keeps_heap_and_stack _ _ _ again).1
  have always : ∀ s t, Related (collectRenaming state) (liveDomain state) s t →
      (fun _ => true : State → Bool) t = (fun _ => true : State → Bool) s := fun _ _ _ => rfl
  have ⟨ran, sameTicks⟩ := related_forceHostedWith always _ _ bytes ticks related room
  refine ⟨resumed', again, ran, sameTicks, ?_, ?_⟩
  · intro plan y r run extracted
    rw [run] at ran
    cases runT : (forceHostedWith (fun _ => true) (limitsPast limits (collect state)) bytes ticks resumed').1 <;>
      rw [runT] at ran <;> simp only [OutcomeRel] at ran
    obtain ⟨same, yRel⟩ := ran
    subst same
    have yRoom := room.shift related yRel
    obtain ⟨r', extracted', resultRel⟩ := related_yieldedPlanWith always _ _ budget yRel yRoom extracted
    exact ⟨_, r', rfl, extracted', resultRel⟩
  · intro value y r run completed
    rw [run] at ran
    cases runT : (forceHostedWith (fun _ => true) (limitsPast limits (collect state)) bytes ticks resumed').1 <;>
      rw [runT] at ran <;> simp only [OutcomeRel] at ran
    obtain ⟨same, _, yRel⟩ := ran
    subst same
    have yRoom := room.shift related yRel
    obtain ⟨r', completed', resultRel⟩ := related_completeWith always _ _ budget yRel yRoom completed
    exact ⟨_, r', rfl, completed', resultRel⟩

/-- **The checkpoint a turn stores resumes as the yielded state itself.** A yield stores
`checkpoint state = collect (settle state)`; resuming it under `limitsPast` of its own
heap (what `Turn.resumeActivity` does) decides the same outcome, spends exactly the same
ticks, and a Plan or result that extracts from the uncollected run extracts from the
checkpoint's run as the same Data with the same remaining budget. -/
theorem checkpoint_resume_segment {state resumed : State} {response : Term}
    (yielded : resume response state = some resumed) (limits : Limits) (bytes ticks : Nat) (budget : Budget) :
    ∃ resumed', resume response (checkpoint state) = some resumed' ∧
      (forceHostedWith (fun _ => true) (limitsPast limits (checkpoint state)) bytes ticks resumed').1.verdict =
        (forceHostedWith (fun _ => true) (limitsPast limits state) bytes ticks resumed).1.verdict ∧
      (forceHostedWith (fun _ => true) (limitsPast limits (checkpoint state)) bytes ticks resumed').2 =
        (forceHostedWith (fun _ => true) (limitsPast limits state) bytes ticks resumed).2 ∧
      (∀ plan y r, (forceHostedWith (fun _ => true) (limitsPast limits state) bytes ticks resumed).1 = .yielded plan y →
        yieldedPlan (limitsPast limits state) budget y = .ok r →
        ∃ plan' y' r', (forceHostedWith (fun _ => true) (limitsPast limits (checkpoint state)) bytes ticks resumed').1 =
            .yielded plan' y' ∧
          yieldedPlan (limitsPast limits (checkpoint state)) budget y' = .ok r' ∧
          r'.value = r.value ∧ r'.remaining = r.remaining) ∧
      (∀ value y r, (forceHostedWith (fun _ => true) (limitsPast limits state) bytes ticks resumed).1 = .finished value y →
        complete (limitsPast limits state) budget y = .ok r →
        ∃ value' y' r', (forceHostedWith (fun _ => true) (limitsPast limits (checkpoint state)) bytes ticks resumed').1 =
            .finished value' y' ∧
          complete (limitsPast limits (checkpoint state)) budget y' = .ok r' ∧
          r'.value = r.value ∧ r'.remaining = r.remaining) := by
  unfold checkpoint
  have sameLimits : limitsPast limits (settle state) = limitsPast limits state := by
    simp [limitsPast]
  obtain ⟨settled, againS, agreeS, ticksS, plansS, resultsS⟩ :=
    settle_resume_segment yielded (limitsPast limits state) bytes ticks budget
  obtain ⟨collected, againC, relC, ticksC, plansC, resultsC⟩ :=
    collect_resume_segment againS limits bytes ticks budget
  rw [sameLimits] at relC ticksC plansC resultsC
  refine ⟨collected, againC, ?_, ?_, ?_, ?_⟩
  · rw [OutcomeRel.verdict relC, OutcomeAgree.verdict agreeS]
  · rw [ticksC, ticksS]
  · intro plan y r run extracted
    obtain ⟨yS, rS, runS, _, extractedS, valueS, remainingS, _⟩ := plansS plan y r run extracted
    obtain ⟨yC, rC, runC, extractedC, valueC, remainingC, _⟩ := plansC plan yS rS runS extractedS
    exact ⟨_, yC, rC, runC, extractedC, by rw [valueC, valueS], by rw [remainingC, remainingS]⟩
  · intro value y r run completed
    obtain ⟨yS, rS, runS, completedS, valueS, remainingS, _⟩ := resultsS value y r run completed
    obtain ⟨yC, rC, runC, completedC, valueC, remainingC, _⟩ := resultsC value yS rS runS completedS
    exact ⟨_, yC, rC, runC, completedC, by rw [valueC, valueS], by rw [remainingC, remainingS]⟩

#assert_axioms related_collect related_stepRaw related_forceHostedFrom related_materializeWith
#assert_axioms collect_resume_segment checkpoint_resume_segment

end Minidregg.Theory.ObjectiveBendDemandCollect
