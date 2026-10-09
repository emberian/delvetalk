/- Receipt-index correctness for the representation used by ResidentStore.
   These lemmas concern lookup and append order, not arbitrary admission
   functions, checkpoint authenticity, or physical SQLite durability. -/
import ResidentStore
import Std.Data.TreeMap.Lemmas

open Lean World

namespace ResidentStore

private theorem compareKey_eq_lex :
    compareKey = compareLex (compareOn (Prod.fst : Key → String))
      (compareOn (Prod.snd : Key → String)) := by
  funext a b
  simp only [compareKey, compareLex, compareOn]
  cases compare a.1 b.1 <;> rfl

private instance : Std.TransCmp compareKey := by
  rw [compareKey_eq_lex]
  infer_instance

private theorem compareKey_eq_iff (a b : Key) :
    compareKey a b = .eq ↔ a = b := by
  rw [compareKey_eq_lex]
  simp only [compareLex_eq_eq, compareOn, Std.compare_eq_iff_eq]
  exact Prod.ext_iff.symm

/-- The oldest matching receipt in the actual reverse-ordered history. -/
def firstReceipt (history : List Json) (key : Key) : Option Json :=
  history.reverse.find? (fun entry => admissionKey entry == some key)

/-- Every lookup in the actual tree agrees with chronological first-match lookup. -/
def IndexCorrect (state : State) : Prop :=
  ∀ key, state.index[key]? = firstReceipt state.history key

/-- Fresh native state starts with an empty index and history. -/
theorem indexCorrect_empty : IndexCorrect ({} : State) := by
  intro key
  change (∅ : Index)[key]? = ([] : List Json).reverse.find? _
  simp

/-- The empty selected array used by prepare is exactly the fresh-key premise. -/
theorem selected_empty_iff (state : State) (request : Json) (key : Key)
    (valid : requestKey request = .ok key) :
    (selected state request).isEmpty = true ↔ state.index[key]? = none := by
  simp only [selected, valid, Except.toOption, Option.bind_some]
  cases state.index[key]? <;> simp

/-- The optimized selection is the oldest matching retained receipt, not a
    caller-supplied answer or a later receipt with the same identity. -/
theorem selected_eq_first (state : State) (request : Json) (key : Key)
    (correct : IndexCorrect state) (valid : requestKey request = .ok key) :
    selected state request =
      match firstReceipt state.history key with
      | some entry => #[entry]
      | none => #[] := by
  simp [selected, valid, Except.toOption, Option.bind, correct key] <;> rfl

/-- Actual insertion preserves first-match selection when prepare has established
    absence and the retained admission has the request's actual key. -/
theorem indexCorrect_remember (state : State) (key : Key)
    (admission base : Json) (head : String)
    (correct : IndexCorrect state)
    (fresh : state.index[key]? = none)
    (keyed : admissionKey admission = some key) (trackChanges : Bool := true) :
    IndexCorrect (remember state key admission base head trackChanges) := by
  intro query
  change (state.index.insert key admission)[query]? =
    firstReceipt (admission :: state.history) query
  rw [Std.TreeMap.getElem?_insert]
  simp only [firstReceipt, List.reverse_cons, List.find?_append, List.find?_singleton]
  have lookup := correct query
  unfold firstReceipt at lookup
  rw [← lookup]
  by_cases equal : key = query
  · subst query
    simp [compareKey_eq_iff, fresh, keyed]
  · simp [compareKey_eq_iff, equal, keyed]

/-- The ordinal used by bounded history queries stores this exact appended fact. -/
theorem ordered_remember_current (state : State) (key : Key)
    (admission base : Json) (head : String) :
    (remember state key admission base head).ordered[state.sequence]? = some admission := by
  simp [remember]

/-- Appending an admission cannot rewrite an earlier retained ordinal. -/
theorem ordered_remember_before (state : State) (key : Key)
    (admission base : Json) (head : String) (ordinal : Nat)
    (earlier : ordinal < state.sequence) :
    (remember state key admission base head).ordered[ordinal]? = state.ordered[ordinal]? := by
  simp [remember, Std.TreeMap.getElem?_insert, Nat.ne_of_gt earlier]

/-- The reversed-list storage exports new admissions at the chronological end. -/
theorem remember_history_order (state : State) (key : Key)
    (admission base : Json) (head : String) :
    (remember state key admission base head).history.reverse =
      state.history.reverse ++ [admission] := by
  simp [remember]

/-- The native append keeps checkpoint sequence equal to retained history size. -/
theorem remember_history_length (state : State) (key : Key)
    (admission base : Json) (head : String)
    (counted : state.history.length = state.sequence) :
    (remember state key admission base head).history.length =
      (remember state key admission base head).sequence := by
  simp [remember, counted]

/-- The existing expanded-world exporter uses that same chronological append. -/
theorem expand_remember (state : State) (key : Key)
    (admission base : Json) (head : String) :
    expand (remember state key admission base head) =
      put base "receipts" (.arr (state.history.reverse ++ [admission]).toArray) := by
  simp [expand, remember]

private theorem bind_success {α β : Type} {first : Except String α}
    {next : α → Except String β} {result : β}
    (success : first.bind next = .ok result) :
    ∃ value, first = .ok value ∧ next value = .ok result := by
  cases computed : first with
  | error error =>
      rw [computed] at success
      cases success
  | ok value =>
      rw [computed] at success
      exact ⟨value, rfl, success⟩

/-- Successful checkpoint admission uses the actual parser, rejects an occupied
    index key, and performs exactly the same remember operation as live admission. -/
theorem checkedAppend_success (state final : State) (entry : Json)
    (success : checkedAppend state entry = .ok final) :
    ∃ key, admissionKey entry = some key ∧ state.index[key]? = none ∧
      final = remember state key entry state.base state.head false := by
  unfold checkedAppend at success
  cases keyed : admissionKey entry with
  | none => simp [keyed] at success
  | some key =>
      simp only [keyed] at success
      obtain ⟨validated, _, success⟩ := bind_success success
      cases validated
      cases fresh : state.index[key]? with
      | none =>
          rw [fresh] at success
          change Except.ok (remember state key entry state.base state.head false) = Except.ok final at success
          have output : remember state key entry state.base state.head false = final := by
            exact Except.ok.inj success
          exact ⟨key, rfl, fresh, output.symm⟩
      | some prior =>
          rw [fresh] at success
          change (Except.error "duplicate checkpoint receipt identity" : Except String State) = .ok final at success
          cases success

/-- A successful checked checkpoint append preserves the real receipt index. -/
theorem indexCorrect_checkedAppend (state final : State) (entry : Json)
    (correct : IndexCorrect state)
    (success : checkedAppend state entry = .ok final) : IndexCorrect final := by
  obtain ⟨key, keyed, fresh, rfl⟩ := checkedAppend_success state final entry success
  exact indexCorrect_remember state key entry state.base state.head correct fresh keyed false

private theorem indexCorrect_listFold (entries : List Json) (state final : State)
    (correct : IndexCorrect state)
    (success : entries.foldlM checkedAppend state = .ok final) : IndexCorrect final := by
  induction entries generalizing state final with
  | nil =>
      simp only [List.foldlM_nil] at success
      cases success
      exact correct
  | cons entry entries ih =>
      rw [List.foldlM_cons] at success
      obtain ⟨next, appended, success⟩ := bind_success success
      exact ih next final (indexCorrect_checkedAppend state next entry correct appended) success

/-- Native checkpoint reconstruction uses Array.foldlM. The list induction is a
    proof transport only; the receiver need not allocate an intermediate list. -/
theorem indexCorrect_checkpointFold (entries : Array Json) (state final : State)
    (correct : IndexCorrect state)
    (success : entries.foldlM checkedAppend state = .ok final) : IndexCorrect final := by
  apply indexCorrect_listFold entries.toList state final correct
  simpa only [Array.foldlM_toList] using success

/-- Every successful loadCheckpoint rebuilds an index agreeing with chronological
    first-match history. This does not authenticate the checkpoint's custodian. -/
theorem indexCorrect_loadCheckpoint (world : Json) (sequence : Nat) (head : String)
    (state : State) (success : loadCheckpoint world sequence head = .ok state) :
    IndexCorrect state := by
  unfold loadCheckpoint at success
  obtain ⟨objects, _, success⟩ := bind_success success
  obtain ⟨objectFields, _, success⟩ := bind_success success
  obtain ⟨receipts, _, success⟩ := bind_success success
  obtain ⟨history, _, success⟩ := bind_success success
  split at success
  · cases success
  · obtain ⟨base, _, success⟩ := bind_success success
    obtain ⟨currentObjects, _, success⟩ := bind_success success
    apply indexCorrect_checkpointFold history { base, head, roots := RetainedRoots.collect {} currentObjects } state ?_ success
    intro key
    change (∅ : Index)[key]? = ([] : List Json).reverse.find? _
    simp

end ResidentStore
