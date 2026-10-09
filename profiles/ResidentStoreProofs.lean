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

/-- The same principal/intent key extracted from a retained admission. -/
def admissionKey (entry : Json) : Option Key :=
  ((field entry "request").bind requestKey).toOption

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
    (keyed : admissionKey admission = some key) :
    IndexCorrect (remember state key admission base head) := by
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

end ResidentStore
