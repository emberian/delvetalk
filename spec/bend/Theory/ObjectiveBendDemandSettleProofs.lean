/- Settling and trimming a checkpoint change no transition. Definitions: `settle`, `trim`,
`checkpoint` in `Theory.ObjectiveBendDemandCollect`. Ported from Mini's
ObjectiveBendDemandSettleProofs to this edition's machine (native cells, the hosted
text tariff `forceHostedFrom`, the compiled `stepRawFast`), and extended to environments.

The machine reads a cached cell's VALUE only (an origin is read only from an `evaluating`
cell, at its update frame), and a closure reads its environment only at the de Bruijn
indices free in its term (`Term.freeIn`): every transition copies an environment only into a
closure over a subterm, or a body under one more binder (`freeIn_rename` covers the renamed
bodies `fix` and `mix` build). So two states that differ only in cached origins and in
environment slots their closures never read take the same transitions. The relation is
`Agree s t`: erasing both (`eraseState`, in cells, control and frames) makes them equal.

* `erase_stepRaw` / `agree_stepRaw`: one transition agrees.
* `agree_forceHostedFrom`: hosted forcing (the turn's runner: text tariff, byte
  admission, capacity check from `sizesAfter`) agrees EXACTLY, with the same remaining
  ticks, capacity suspensions included.
* `agree_materializeWith`, `agree_completeWith`, `agree_yieldedPlanWith`: extraction gives
  the same Data and budget.
* `agree_settle`: `Agree s (settle s)`; `agree_trim`: `Agree s (trim s)`.
* `agree_resume_segment`, `settle_resume_segment`, `trim_resume_segment`: the turn's segment
  (`executeStateWith`, then the Plan's `yieldedPlanWith` on a yield) from a resumed agreeing
  state agrees with the segment from the original.

Not ported: `typed_settle` (this edition has no state-typing judgment,
Mini's ObjectiveBendDemandTyping). The `collect` stages of
`checkpoint = collect ∘ trim ∘ collect ∘ settle` are `Theory.ObjectiveBendDemandCollectProofs`
(`checkpoint_resume_segment`). -/
import Theory.ObjectiveBendDemandCollect
import Theory.ObjectiveBendDemandData
namespace Minidregg.Theory.ObjectiveBendDemandCollect
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData
set_option autoImplicit false

/-! ## Free variables and trimmed environments -/

theorem trimEnv_length (keep : Nat → Bool) (dummy : Nat) :
    ∀ env : Environment, (trimEnv keep dummy env).length = env.length
  | [] => rfl
  | _ :: rest => by simp [trimEnv, trimEnv_length _ dummy rest]

theorem trimEnv_getElem?_of_keep (dummy : Nat) :
    ∀ (env : Environment) (keep : Nat → Bool) (i : Nat), keep i = true →
      (trimEnv keep dummy env)[i]? = env[i]?
  | [], _, _, _ => rfl
  | a :: rest, keep, 0, kept => by simp [trimEnv, kept]
  | a :: rest, keep, i + 1, kept => by
    simpa [trimEnv] using trimEnv_getElem?_of_keep dummy rest (fun i => keep (i + 1)) i kept

/-- Trimming to fewer slots after trimming to more is trimming to fewer. -/
theorem trimEnv_absorb (dummy : Nat) :
    ∀ (env : Environment) (p q : Nat → Bool), (∀ i, p i = true → q i = true) →
      trimEnv p dummy (trimEnv q dummy env) = trimEnv p dummy env
  | [], _, _, _ => rfl
  | a :: rest, p, q, le => by
    simp only [trimEnv]
    rw [trimEnv_absorb dummy rest (fun i => p (i + 1)) (fun i => q (i + 1)) (fun i => le (i + 1))]
    cases hp : p 0
    · rfl
    · simp [le 0 hp]

@[simp] theorem trimEnv_idem (keep : Nat → Bool) (dummy : Nat) (env : Environment) :
    trimEnv keep dummy (trimEnv keep dummy env) = trimEnv keep dummy env :=
  trimEnv_absorb dummy env keep keep (fun _ h => h)

theorem trimEnv_congr (dummy : Nat) (env : Environment) {p q : Nat → Bool} (same : ∀ i, p i = q i) :
    trimEnv p dummy env = trimEnv q dummy env := by
  have : p = q := funext same
  rw [this]

theorem fieldsFreeIn_of_mem {name : String} {t : Term} {j : Nat} :
    ∀ {fields : List (String × Term)}, (name, t) ∈ fields → t.freeIn j = true → Term.fieldsFreeIn fields j = true
  | [], member, _ => by cases member
  | (n, u) :: rest, member, free => by
    rcases List.mem_cons.mp member with same | member
    · cases same; simp [Term.fieldsFreeIn, free]
    · simp [Term.fieldsFreeIn, fieldsFreeIn_of_mem member free]

theorem liftRename_eq_succ {rename : Nat → Nat} {i j : Nat} (h : liftRename rename i = j + 1) :
    ∃ k, i = k + 1 ∧ rename k = j := by
  cases i with
  | zero => simp [liftRename] at h
  | succ k => exact ⟨k, rfl, by simpa [liftRename] using h⟩

mutual
/-- A free index of a renamed term is the image of a free index of the term. -/
theorem freeIn_rename : ∀ (t : Term) (rename : Nat → Nat) (j : Nat),
    (t.rename rename).freeIn j = true → ∃ i, rename i = j ∧ t.freeIn i = true
  | .bound i, rename, j, h => by
    simp [Term.rename, Term.freeIn] at h; exact ⟨i, h, by simp [Term.freeIn]⟩
  | .lam body, rename, j, h => by
    simp only [Term.rename, Term.freeIn] at h
    obtain ⟨i, hi, free⟩ := freeIn_rename body (liftRename rename) (j + 1) h
    obtain ⟨k, rfl, hk⟩ := liftRename_eq_succ hi
    exact ⟨k, hk, by simpa [Term.freeIn] using free⟩
  | .app a b, rename, j, h | .mix a b, rename, j, h | .fix a b, rename, j, h
  | .specification a b, rename, j, h | .prototype a b, rename, j, h
  | .binary _ a b, rename, j, h | .textJoin a b, rename, j, h => by
    simp only [Term.rename, Term.freeIn, Bool.or_eq_true] at h
    rcases h with h | h
    · obtain ⟨i, hi, free⟩ := freeIn_rename a rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
    · obtain ⟨i, hi, free⟩ := freeIn_rename b rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
  | .reflect a, rename, j, h | .metadata a, rename, j, h | .project a, rename, j, h
  | .unary _ a, rename, j, h | .get a _, rename, j, h | .inject _ a, rename, j, h
  | .perform a, rename, j, h | .done a, rename, j, h | .toData a, rename, j, h => by
    simp only [Term.rename, Term.freeIn] at h
    obtain ⟨i, hi, free⟩ := freeIn_rename a rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
  | .nat _, _, _, h | .boolean _, _, _, h | .label _, _, _, h | .refuse _, _, _, h => by
    simp [Term.rename, Term.freeIn] at h
  | .extend a fields, rename, j, h => by
    simp only [Term.rename, Term.freeIn, Bool.or_eq_true] at h
    rcases h with h | h
    · obtain ⟨i, hi, free⟩ := freeIn_rename a rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
    · obtain ⟨i, hi, free⟩ := fieldsFreeIn_rename fields rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
  | .record fields, rename, j, h => by
    simp only [Term.rename, Term.freeIn] at h
    obtain ⟨i, hi, free⟩ := fieldsFreeIn_rename fields rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
  | .ifZero a b c, rename, j, h => by
    simp only [Term.rename, Term.freeIn, Bool.or_eq_true] at h
    rcases h with (h | h) | h
    · obtain ⟨i, hi, free⟩ := freeIn_rename a rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
    · obtain ⟨i, hi, free⟩ := freeIn_rename b rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
    · obtain ⟨i, hi, free⟩ := freeIn_rename c (liftRename rename) (j + 1) h
      obtain ⟨k, rfl, hk⟩ := liftRename_eq_succ hi
      exact ⟨k, hk, by simp [Term.freeIn, free]⟩
  | .case a arms, rename, j, h => by
    simp only [Term.rename, Term.freeIn, Bool.or_eq_true] at h
    rcases h with h | h
    · obtain ⟨i, hi, free⟩ := freeIn_rename a rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
    · obtain ⟨i, hi, free⟩ := fieldsFreeIn_rename arms (liftRename rename) (j + 1) h
      obtain ⟨k, rfl, hk⟩ := liftRename_eq_succ hi
      exact ⟨k, hk, by simp [Term.freeIn, free]⟩
  | .ifBool a b c, rename, j, h => by
    simp only [Term.rename, Term.freeIn, Bool.or_eq_true] at h
    rcases h with (h | h) | h
    · obtain ⟨i, hi, free⟩ := freeIn_rename a rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
    · obtain ⟨i, hi, free⟩ := freeIn_rename b rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
    · obtain ⟨i, hi, free⟩ := freeIn_rename c rename j h; exact ⟨i, hi, by simp [Term.freeIn, free]⟩
theorem fieldsFreeIn_rename : ∀ (fields : List (String × Term)) (rename : Nat → Nat) (j : Nat),
    Term.fieldsFreeIn (fields.map fun field => (field.1, field.2.rename rename)) j = true →
      ∃ i, rename i = j ∧ Term.fieldsFreeIn fields i = true
  | [], _, _, h => by simp [Term.fieldsFreeIn] at h
  | (n, t) :: rest, rename, j, h => by
    simp only [List.map_cons, Term.fieldsFreeIn, Bool.or_eq_true] at h
    rcases h with h | h
    · obtain ⟨i, hi, free⟩ := freeIn_rename t rename j h
      exact ⟨i, hi, by simp [Term.fieldsFreeIn, free]⟩
    · obtain ⟨i, hi, free⟩ := fieldsFreeIn_rename rest rename j h
      exact ⟨i, hi, by simp [Term.fieldsFreeIn, free]⟩
end

theorem freeIn_rename_succ {t : Term} {j : Nat} (h : (t.rename Nat.succ).freeIn (j + 1) = true) :
    t.freeIn j = true := by
  obtain ⟨i, hi, free⟩ := freeIn_rename t Nat.succ (j + 1) h
  cases hi; exact free

theorem freeIn_rename_add_two {t : Term} {j : Nat} (h : (t.rename (fun n => n + 2)).freeIn (j + 2) = true) :
    t.freeIn j = true := by
  obtain ⟨i, hi, free⟩ := freeIn_rename t (fun n => n + 2) (j + 2) h
  have : i = j := by omega
  subst this; exact free

/-! ## Erasure: cached origins and unread environment slots

The machine reads a cached cell's VALUE only; a cached cell's origin is never read again
(`stepRaw` reads an origin only from an `evaluating` cell, at its update frame, and a
native cell's Data, which settling leaves alone). And a closure reads its environment only at
the indices free in its term. So two states that differ only in cached origins and in
environment slots their closures never read take the same transitions. The relation is
`Agree s t`: erasing both (`eraseState`; an unread slot becomes 0) makes them equal. -/

/-- Forget a cached cell's origin and every environment slot its closures do not read. -/
def eraseCell : Cell → Cell
  | .suspended origin => .suspended (trimClosure 0 origin)
  | .evaluating origin => .evaluating (trimClosure 0 origin)
  | .cached _ value => .cached ⟨.nat 0, []⟩ (trimValue 0 value)
  | .native origin => .native origin
  | .nativeCached origin value => .nativeCached origin (trimValue 0 value)

/-- A frame with every environment slot it never reads replaced by 0. -/
def eraseFrame : Frame → Frame
  | .argument term environment => .argument term (trimEnv term.freeIn 0 environment)
  | .extend fields environment => .extend fields (trimEnv (Term.fieldsFreeIn fields) 0 environment)
  | .condition zero successor environment =>
    .condition zero successor (trimEnv (fun i => zero.freeIn i || successor.freeIn (i + 1)) 0 environment)
  | .binaryLeft primitive right environment => .binaryLeft primitive right (trimEnv right.freeIn 0 environment)
  | .binaryRight primitive left => .binaryRight primitive (trimValue 0 left)
  | .case arms environment => .case arms (trimEnv (fun i => Term.fieldsFreeIn arms (i + 1)) 0 environment)
  | .ifBool whenTrue whenFalse environment =>
    .ifBool whenTrue whenFalse (trimEnv (fun i => whenTrue.freeIn i || whenFalse.freeIn i) 0 environment)
  | .joinSeparator list environment => .joinSeparator list (trimEnv list.freeIn 0 environment)
  | frame => frame

def eraseControl : Control → Control
  | .evaluate term environment => .evaluate term (trimEnv term.freeIn 0 environment)
  | .returned value => .returned (trimValue 0 value)
  | .complete value => .complete (trimValue 0 value)
  | control => control

@[simp] theorem trimValue_trimValue (value : RuntimeValue) : trimValue 0 (trimValue 0 value) = trimValue 0 value := by
  cases value <;> simp [trimValue]

@[simp] theorem eraseCell_eraseCell (cell : Cell) : eraseCell (eraseCell cell) = eraseCell cell := by
  cases cell <;> simp [eraseCell, trimClosure]

@[simp] theorem eraseFrame_eraseFrame (frame : Frame) : eraseFrame (eraseFrame frame) = eraseFrame frame := by
  cases frame <;> simp [eraseFrame]

@[simp] theorem eraseControl_eraseControl (control : Control) : eraseControl (eraseControl control) = eraseControl control := by
  cases control <;> simp [eraseControl]

@[simp] theorem eraseCell_comp : eraseCell ∘ eraseCell = eraseCell := by
  funext cell; simp

@[simp] theorem eraseFrame_comp : eraseFrame ∘ eraseFrame = eraseFrame := by
  funext frame; simp

def eraseState (state : State) : State :=
  ⟨state.heap.map eraseCell, eraseControl state.control, state.stack.map eraseFrame⟩

/-- Two states agree up to cached origins and unread environment slots. -/
def Agree (s t : State) : Prop := eraseState s = eraseState t

theorem Agree.refl (s : State) : Agree s s := rfl
theorem Agree.symm {s t : State} (agree : Agree s t) : Agree t s := Eq.symm agree
theorem Agree.trans {s t u : State} (one : Agree s t) (two : Agree t u) : Agree s u := Eq.trans one two

theorem Agree.control {s t : State} (agree : Agree s t) : eraseControl s.control = eraseControl t.control := by
  have same := congrArg State.control (show eraseState s = eraseState t from agree)
  simpa [eraseState] using same
theorem Agree.stack {s t : State} (agree : Agree s t) : s.stack.map eraseFrame = t.stack.map eraseFrame := by
  have same := congrArg State.stack (show eraseState s = eraseState t from agree)
  simpa [eraseState] using same
theorem Agree.heap {s t : State} (agree : Agree s t) : s.heap.map eraseCell = t.heap.map eraseCell :=
  congrArg State.heap (show eraseState s = eraseState t from agree)
theorem Agree.size {s t : State} (agree : Agree s t) : s.heap.size = t.heap.size := by
  have := congrArg Array.size agree.heap
  simpa using this

theorem Agree.mk' {s t : State} (heap : s.heap.map eraseCell = t.heap.map eraseCell)
    (control : eraseControl s.control = eraseControl t.control)
    (stack : s.stack.map eraseFrame = t.stack.map eraseFrame) : Agree s t := by
  unfold Agree eraseState; rw [heap, control, stack]

theorem agree_eraseState (s : State) : Agree (eraseState s) s := by
  unfold Agree eraseState; simp [Array.map_map, List.map_map]

theorem eraseState_eraseState (s : State) : eraseState (eraseState s) = eraseState s :=
  agree_eraseState s

/-! ## One transition -/

theorem erase_set! (heap : Array Cell) (address : Nat) (cell : Cell) :
    (heap.set! address cell).map eraseCell = (heap.map eraseCell).set! address (eraseCell cell) := by
  simp [Array.set!_eq_setIfInBounds, Array.map_setIfInBounds]

/-- Allocating a record's fields over an environment trimmed to (at least) the slots its
fields read allocates the same cells, up to erasure. -/
theorem erase_allocateFields (heap : Array Cell) (environment : Environment) (fields : List (String × Term))
    (keep : Nat → Bool) (covers : ∀ i, Term.fieldsFreeIn fields i = true → keep i = true) :
    ((allocateFields (heap.map eraseCell) (trimEnv keep 0 environment) fields).1.map eraseCell,
      (allocateFields (heap.map eraseCell) (trimEnv keep 0 environment) fields).2) =
    ((allocateFields heap environment fields).1.map eraseCell, (allocateFields heap environment fields).2) := by
  have loop : ∀ (rest : List (String × Term)), (∀ field ∈ rest, field ∈ fields) →
      ∀ (heap heap' : Array Cell) (names : List (String × Address)), heap'.map eraseCell = heap.map eraseCell →
      (rest.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.suspended ⟨field.2,trimEnv keep 0 environment⟩),(field.1,prior.1.size)::prior.2)) (heap', names)).1.map eraseCell =
      (rest.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,prior.1.size)::prior.2)) (heap, names)).1.map eraseCell ∧
      (rest.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.suspended ⟨field.2,trimEnv keep 0 environment⟩),(field.1,prior.1.size)::prior.2)) (heap', names)).2 =
      (rest.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,prior.1.size)::prior.2)) (heap, names)).2 := by
    intro rest
    induction rest with
    | nil => intro _ heap heap' names same; exact ⟨same, rfl⟩
    | cons field rest ih =>
      intro inFields heap heap' names same
      have sizes : heap'.size = heap.size := by
        have := congrArg Array.size same; simpa using this
      simp only [List.foldl_cons]
      rw [sizes]
      apply ih (fun f m => inFields f (List.mem_cons_of_mem _ m))
      simp only [Array.map_push, same, eraseCell, trimClosure]
      congr 2
      have member := inFields field List.mem_cons_self
      exact congrArg (Closure.mk field.2)
        (trimEnv_absorb 0 environment _ keep fun i free => covers i (fieldsFreeIn_of_mem member free))
  have := loop fields (fun _ m => m) heap (heap.map eraseCell) [] (by simp [Array.map_map])
  simp only [allocateFields]
  rw [this.1, this.2]

theorem erase_allocateNativeFields (heap : Array Cell) (fields : List (String × Data)) :
    allocateNativeFields (heap.map eraseCell) fields =
      ((allocateNativeFields heap fields).1.map eraseCell, (allocateNativeFields heap fields).2) := by
  have loop : ∀ (fields : List (String × Data)) (heap : Array Cell) (names : List (String × Address)),
      fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.native field.2),(field.1,prior.1.size)::prior.2)) (heap.map eraseCell, names) =
      ((fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.native field.2),(field.1,prior.1.size)::prior.2)) (heap, names)).1.map eraseCell,
       (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.native field.2),(field.1,prior.1.size)::prior.2)) (heap, names)).2) := by
    intro fields
    induction fields with
    | nil => intro heap names; rfl
    | cons field rest ih =>
      intro heap names
      simp only [List.foldl_cons, Array.size_map]
      have := ih (heap.push (.native field.2)) ((field.1, heap.size) :: names)
      rw [← this]
      simp [Array.map_push, eraseCell]
  simp only [allocateNativeFields]
  rw [loop]

theorem trimValue_forceNative (heap : Array Cell) (value : Data) :
    trimValue 0 (forceNative heap value).2 = (forceNative heap value).2 := by
  cases value <;> simp [forceNative, trimValue]

theorem erase_forceNative (heap : Array Cell) (value : Data) :
    forceNative (heap.map eraseCell) value =
      ((forceNative heap value).1.map eraseCell, (forceNative heap value).2) := by
  cases value <;> simp [forceNative, erase_allocateNativeFields, Array.map_push, eraseCell]

theorem forcingShared_erase (stack : List Frame) : forcingShared (stack.map eraseFrame) = forcingShared stack := by
  induction stack with
  | nil => rfl
  | cons frame rest ih =>
    simp only [forcingShared, List.map_cons, List.any_cons] at ih ⊢
    rw [ih]; cases frame <;> rfl

theorem valueTerm_trimValue (value : RuntimeValue) : valueTerm (trimValue 0 value) = valueTerm value := by
  cases value <;> rfl

@[simp] theorem trimValue_closure (dummy : Nat) (body : Term) (environment : Environment) :
    trimValue dummy (.closure body environment) =
      .closure body (trimEnv (fun i => body.freeIn (i + 1)) dummy environment) := rfl
@[simp] theorem trimValue_natural (dummy n : Nat) : trimValue dummy (.natural n) = .natural n := rfl
@[simp] theorem trimValue_boolean (dummy : Nat) (b : Bool) : trimValue dummy (.boolean b) = .boolean b := rfl
@[simp] theorem trimValue_label (dummy : Nat) (l : String) : trimValue dummy (.label l) = .label l := rfl
@[simp] theorem trimValue_record (dummy : Nat) (fields : List (String × Address)) :
    trimValue dummy (.record fields) = .record fields := rfl
@[simp] theorem trimValue_specification (dummy a b : Nat) :
    trimValue dummy (.specification a b) = .specification a b := rfl
@[simp] theorem trimValue_prototype (dummy a b : Nat) : trimValue dummy (.prototype a b) = .prototype a b := rfl
@[simp] theorem trimValue_variant (dummy : Nat) (l : String) (p : Nat) :
    trimValue dummy (.variant l p) = .variant l p := rfl

/-- Discharges `∀ i, p i = true → q i = true` between free-index predicates, and
`keep i = true` for one index. -/
macro "free_le" : tactic => `(tactic| first
  | (intro i h; simp only [Term.freeIn, Term.fieldsFreeIn, mixBody, Bool.or_eq_true, beq_iff_eq] at h ⊢;
     grind [freeIn_rename_succ, freeIn_rename_add_two])
  | simp [Term.freeIn])

theorem trimEnv_absorb' {p q : Nat → Bool} (le : ∀ i, p i = true → q i = true) (dummy : Nat) (env : Environment) :
    trimEnv p dummy (trimEnv q dummy env) = trimEnv p dummy env :=
  trimEnv_absorb dummy env p q le

theorem trimEnv_getElem?_of_keep' {keep : Nat → Bool} {i : Nat} (kept : keep i = true) (dummy : Nat) (env : Environment) :
    (trimEnv keep dummy env)[i]? = env[i]? :=
  trimEnv_getElem?_of_keep dummy env keep i kept

theorem erase_allocateFields_fst {heap : Array Cell} {environment : Environment} {fields : List (String × Term)}
    {keep : Nat → Bool} (covers : ∀ i, Term.fieldsFreeIn fields i = true → keep i = true) :
    (allocateFields (heap.map eraseCell) (trimEnv keep 0 environment) fields).1.map eraseCell =
      (allocateFields heap environment fields).1.map eraseCell :=
  (Prod.mk.inj (erase_allocateFields heap environment fields keep covers)).1

theorem erase_allocateFields_snd {heap : Array Cell} {environment : Environment} {fields : List (String × Term)}
    {keep : Nat → Bool} (covers : ∀ i, Term.fieldsFreeIn fields i = true → keep i = true) :
    (allocateFields (heap.map eraseCell) (trimEnv keep 0 environment) fields).2 =
      (allocateFields heap environment fields).2 :=
  (Prod.mk.inj (erase_allocateFields heap environment fields keep covers)).2

/-- **Erasure commutes with a transition** (up to the erasure of its result): the
machine never reads a cached cell's origin, nor an environment slot its term does not
name. -/
theorem erase_stepRaw (s : State) : eraseState (stepRaw (eraseState s)) = eraseState (stepRaw s) := by
  obtain ⟨heap, control, stack⟩ := s
  cases control with
  | complete value => simp [stepRaw, eraseState, eraseControl, Array.map_map, List.map_map]
  | refused reason => simp [stepRaw, eraseState, eraseControl, Array.map_map, List.map_map]
  | blackhole address => simp [stepRaw, eraseState, eraseControl, Array.map_map, List.map_map]
  | yielded plan => simp [stepRaw, eraseState, eraseControl, Array.map_map, List.map_map]
  | nativeApplication function argument remaining =>
    cases remaining <;> simp [stepRaw, eraseState, eraseControl, eraseFrame, trimEnv, Array.map_map, List.map_map]
  | enter address =>
    cases found : heap[address]? with
    | none => simp [stepRaw, eraseState, eraseControl, Array.getElem?_map, found, Array.map_map, List.map_map]
    | some cell =>
      cases cell <;>
        simp [stepRaw, eraseState, eraseControl, eraseCell, Array.getElem?_map, found, Array.map_map,
          List.map_map, erase_forceNative, erase_set!, trimValue_forceNative, trimClosure]
  | evaluate term environment =>
    cases term <;>
      simp (disch := free_le) [stepRaw, eraseState, eraseControl, eraseFrame, eraseCell, trimClosure,
        Array.map_map, List.map_map, Array.map_push, forcingShared_erase, trimEnv_absorb',
        trimEnv_getElem?_of_keep', erase_allocateFields_fst, erase_allocateFields_snd, trimEnv] <;>
      (repeat' split) <;> (try simp at *) <;>
      simp (disch := free_le) [eraseControl, eraseFrame, eraseCell, trimClosure, Array.map_map, List.map_map,
        Array.map_push, trimEnv_absorb', trimEnv]
  | returned value =>
    cases stack with
    | nil => simp [stepRaw, eraseState, eraseControl, Array.map_map, List.map_map]
    | cons frame rest =>
      cases frame with
      | update address =>
        cases found : heap[address]? with
        | none => simp [stepRaw, eraseState, eraseControl, eraseFrame, Array.getElem?_map, found, Array.map_map, List.map_map]
        | some cell =>
          cases cell <;>
            simp [stepRaw, eraseState, eraseControl, eraseCell, eraseFrame, Array.getElem?_map, found,
              Array.map_map, List.map_map, erase_set!]
      | case arms environment =>
        cases value <;> simp [stepRaw, eraseState, eraseControl, eraseFrame, Array.map_map, List.map_map]
        rename_i tag payload
        cases found : arms.find? (fun arm => arm.1 == tag) with
        | none => simp [found, eraseControl, eraseFrame, Array.map_map, List.map_map]
        | some arm =>
          have member := List.mem_of_find?_eq_some found
          simp [found, eraseControl, eraseCell, trimClosure, Array.map_map, List.map_map, Array.map_push, trimEnv]
          exact trimEnv_absorb 0 environment _ _ fun i free => fieldsFreeIn_of_mem member free
      | condition zero successor environment =>
        cases value <;> simp [stepRaw, eraseState, eraseControl, eraseFrame, Array.map_map, List.map_map]
        rename_i n
        cases n <;> simp [eraseControl, eraseCell, Array.map_map, List.map_map, Array.map_push, trimEnv]
        · exact trimEnv_absorb 0 environment _ _ fun i h => by simp [h]
        · exact trimEnv_absorb 0 environment _ _ fun i h => by simp [h]
      | ifBool whenTrue whenFalse environment =>
        cases value <;> simp [stepRaw, eraseState, eraseControl, eraseFrame, Array.map_map, List.map_map]
        rename_i b
        cases b <;> simp [eraseControl, Array.map_map, List.map_map]
        · exact trimEnv_absorb 0 environment _ _ fun i h => by simp [h]
        · exact trimEnv_absorb 0 environment _ _ fun i h => by simp [h]
      | binaryRight primitive left =>
        cases value <;> cases left <;>
          simp [stepRaw, eraseState, eraseControl, eraseFrame, valueTerm, Array.map_map, List.map_map] <;>
          (repeat' split) <;>
          simp_all [eraseControl, valueTerm, Array.map_map, List.map_map]
      | _ =>
        cases value <;>
          simp [stepRaw, eraseState, eraseControl, eraseFrame, eraseCell, trimClosure, valueTerm,
            Array.map_map, List.map_map, Array.map_push, erase_set!, erase_allocateFields_fst,
            erase_allocateFields_snd, trimEnv] <;>
          (repeat' split) <;>
          simp_all [eraseControl, eraseFrame, eraseCell, trimClosure, valueTerm, Array.map_map, List.map_map,
            Array.map_push, trimEnv]

theorem agree_stepRaw {s t : State} (agree : Agree s t) : Agree (stepRaw s) (stepRaw t) := by
  unfold Agree
  rw [← erase_stepRaw s, ← erase_stepRaw t, agree]

/-! ## Bounded runs and hosted forcing agree exactly -/

def eraseOutcome : Outcome → Outcome
  | .finished value state => .finished (trimValue 0 value) (eraseState state)
  | .suspended reason state => .suspended reason (eraseState state)
  | .divergent address state => .divergent address (eraseState state)
  | .refused reason state => .refused reason (eraseState state)
  | .yielded plan state => .yielded plan (eraseState state)

/-- Outcomes agree: same constructor, same payload up to erasure, agreeing retained states. -/
def OutcomeAgree (o o' : Outcome) : Prop := eraseOutcome o = eraseOutcome o'

theorem erase_runBounded_zero (limits : Limits) (s : State) :
    OutcomeAgree (runBounded limits 0 s) (runBounded limits 0 (eraseState s)) := by
  obtain ⟨heap, control, stack⟩ := s
  cases control <;>
    simp [runBounded, OutcomeAgree, eraseOutcome, eraseState, eraseControl, Array.map_map, List.map_map]

theorem agree_runBounded_zero (limits : Limits) {s t : State} (agree : Agree s t) :
    OutcomeAgree (runBounded limits 0 s) (runBounded limits 0 t) := by
  unfold OutcomeAgree
  rw [erase_runBounded_zero limits s, show eraseState s = eraseState t from agree]
  exact (erase_runBounded_zero limits t).symm

theorem eraseControl_eq_yielded {control : Control} {plan : Nat} :
    eraseControl control = .yielded plan ↔ control = .yielded plan := by
  cases control <;> simp [eraseControl]

theorem agree_resume {s t : State} (agree : Agree s t) (response : Term) {s' : State}
    (resumed : resume response s = some s') :
    ∃ t', resume response t = some t' ∧ Agree s' t' := by
  obtain ⟨plan, yielded⟩ := resume_requires_yield response s (by rw [resumed]; rfl)
  have controlT : t.control = .yielded plan := by
    have := agree.control
    rw [yielded] at this
    exact eraseControl_eq_yielded.mp (by simpa [eraseControl] using this.symm)
  simp only [resume, yielded] at resumed
  cases resumed
  refine ⟨{t with control := .evaluate response []}, by simp [resume, controlT], ?_⟩
  exact Agree.mk' agree.heap rfl agree.stack

theorem textStepCost_erase (s : State) (ticks : Nat) : textStepCost (eraseState s) ticks = textStepCost s ticks := by
  obtain ⟨heap, control, stack⟩ := s
  cases control with
  | returned value =>
    cases stack with
    | nil => cases value <;> simp [textStepCost, eraseState, eraseControl]
    | cons frame rest =>
      cases frame with
      | binaryRight primitive left =>
        cases primitive <;> cases left <;> cases value <;> simp [textStepCost, eraseState, eraseControl, eraseFrame]
      | unary primitive => cases primitive <;> cases value <;> simp [textStepCost, eraseState, eraseControl, eraseFrame]
      | _ => cases value <;> simp [textStepCost, eraseState, eraseControl, eraseFrame]
  | _ => simp [textStepCost, eraseState, eraseControl]

/-- The hosted tariff reads only control and stack, and no environment. -/
theorem textStepCost_agree {s t : State} (agree : Agree s t) (ticks : Nat) :
    textStepCost s ticks = textStepCost t ticks := by
  rw [← textStepCost_erase s, ← textStepCost_erase t]
  exact congrArg (fun state => textStepCost state ticks) agree

theorem preflightRemaining_erase (control : Control) (stack : List Frame) (ticks : Nat) :
    preflightRemaining (eraseControl control) (stack.map eraseFrame) ticks = preflightRemaining control stack ticks := by
  cases control with
  | returned value =>
    cases stack with
    | nil => cases value <;> simp [preflightRemaining, eraseControl]
    | cons frame rest =>
      cases frame with
      | binaryRight primitive left =>
        cases primitive <;> cases left <;> cases value <;> simp [preflightRemaining, eraseControl, eraseFrame]
      | _ => cases value <;> simp [preflightRemaining, eraseControl, eraseFrame]
  | _ => simp [preflightRemaining, eraseControl]

theorem preflightRemaining_agree {s t : State} (agree : Agree s t) (ticks : Nat) :
    preflightRemaining s.control s.stack ticks = preflightRemaining t.control t.stack ticks := by
  rw [← preflightRemaining_erase s.control, ← preflightRemaining_erase t.control, agree.control, agree.stack]

theorem sizesAfter_erase (s : State) (depth : Nat) :
    ObjectiveBendDemandMachineFast.sizesAfter (eraseState s) depth =
      ObjectiveBendDemandMachineFast.sizesAfter s depth := by
  obtain ⟨heap, control, stack⟩ := s
  cases control with
  | enter address =>
    simp only [ObjectiveBendDemandMachineFast.sizesAfter, eraseState, eraseControl, Array.getElem?_map, Array.size_map]
    cases heap[address]? with
    | none => rfl
    | some cell => cases cell <;> rfl
  | evaluate term environment =>
    cases term <;> simp [ObjectiveBendDemandMachineFast.sizesAfter, eraseState, eraseControl, forcingShared_erase]
  | returned value =>
    cases stack with
    | nil => cases value <;> simp [ObjectiveBendDemandMachineFast.sizesAfter, eraseState, eraseControl]
    | cons frame rest =>
      cases frame with
      | condition zero successor environment =>
        cases value with
        | natural n => cases n <;> simp [ObjectiveBendDemandMachineFast.sizesAfter, eraseState, eraseControl, eraseFrame]
        | _ => simp [ObjectiveBendDemandMachineFast.sizesAfter, eraseState, eraseControl, eraseFrame]
      | _ => cases value <;> simp [ObjectiveBendDemandMachineFast.sizesAfter, eraseState, eraseControl, eraseFrame]
  | _ => simp [ObjectiveBendDemandMachineFast.sizesAfter, eraseState, eraseControl]

theorem sizesAfter_agree {s t : State} (agree : Agree s t) (depth : Nat) :
    ObjectiveBendDemandMachineFast.sizesAfter s depth = ObjectiveBendDemandMachineFast.sizesAfter t depth := by
  rw [← sizesAfter_erase s, ← sizesAfter_erase t]
  exact congrArg (fun state => ObjectiveBendDemandMachineFast.sizesAfter state depth) agree

/-- Whether a control has stopped (a result, a refusal, a divergence or a yield). -/
def halted : Control → Bool
  | .complete _ | .refused _ | .blackhole _ | .yielded _ => true
  | _ => false

theorem halted_erase (control : Control) : halted (eraseControl control) = halted control := by
  cases control <;> rfl

theorem halted_agree {s t : State} (agree : Agree s t) : halted s.control = halted t.control := by
  rw [← halted_erase s.control, ← halted_erase t.control, agree.control]

theorem forceHostedFrom_succ (policy : State → Bool) (limits : Limits) (bytes remaining : Nat)
    (state : State) (depth : Nat) :
    forceHostedFrom policy limits bytes (remaining + 1) state depth =
      if halted state.control then (runBounded limits 0 state, remaining + 1) else
      let cost := textStepCost state (remaining + 1)
      if !policy state || cost.2 > bytes then (.suspended .capacity state, remaining + 1)
      else if cost.1 > remaining + 1 then
        (.suspended .ticks state, preflightRemaining state.control state.stack (remaining + 1))
      else
        let sizes := ObjectiveBendDemandMachineFast.sizesAfter state depth
        if sizes.1 ≤ limits.heap && sizes.2 ≤ limits.stack then
          forceHostedFrom policy limits bytes (remaining + 1 - max 1 cost.1)
            (ObjectiveBendDemandMachineFast.stepRawFast state) sizes.2
        else (.suspended .capacity state, remaining + 1 - max 1 cost.1) := by
  rw [forceHostedFrom.eq_def]
  cases h : state.control <;> simp [halted]

/-- **Hosted forcing agrees**, for any policy that agreeing states pass alike: the
same outcome (up to erasure) and the same remaining ticks. -/
theorem agree_forceHostedFrom {policy : State → Bool}
    (respects : ∀ s t, Agree s t → policy s = policy t) (limits : Limits) (bytes : Nat) :
    ∀ (ticks : Nat) (s t : State) (depth : Nat), Agree s t →
      OutcomeAgree (forceHostedFrom policy limits bytes ticks s depth).1
          (forceHostedFrom policy limits bytes ticks t depth).1 ∧
        (forceHostedFrom policy limits bytes ticks t depth).2 =
          (forceHostedFrom policy limits bytes ticks s depth).2 := by
  intro ticks
  induction ticks using Nat.strongRecOn with
  | ind ticks ih =>
  intro s t depth agree
  have halt := halted_agree agree
  have cost := textStepCost_agree agree ticks
  have pre := preflightRemaining_agree agree ticks
  have sizes := sizesAfter_agree agree depth
  have allowed := respects s t agree
  have next : Agree (ObjectiveBendDemandMachineFast.stepRawFast s)
      (ObjectiveBendDemandMachineFast.stepRawFast t) := by
    rw [ObjectiveBendDemandMachineFast.stepRawFast_eq_stepRaw,
      ObjectiveBendDemandMachineFast.stepRawFast_eq_stepRaw]
    exact agree_stepRaw agree
  cases ticks with
  | zero =>
    rw [forceHostedFrom.eq_def (state := s), forceHostedFrom.eq_def (state := t)]
    exact ⟨agree_runBounded_zero limits agree, rfl⟩
  | succ remaining =>
    rw [forceHostedFrom_succ, forceHostedFrom_succ]
    rw [← halt, ← cost, ← allowed, ← pre, ← sizes]
    have same : OutcomeAgree (.suspended .capacity s) (.suspended .capacity t) := by
      simp only [OutcomeAgree, eraseOutcome]; exact congrArg _ agree
    have sameTicks : OutcomeAgree (.suspended .ticks s) (.suspended .ticks t) := by
      simp only [OutcomeAgree, eraseOutcome]; exact congrArg _ agree
    split
    · exact ⟨agree_runBounded_zero limits agree, rfl⟩
    simp only []
    split
    · exact ⟨same, rfl⟩
    split
    · exact ⟨sameTicks, rfl⟩
    split
    · exact ih _ (by omega) _ _ _ next
    · exact ⟨same, rfl⟩

theorem agree_forceHostedWith {policy : State → Bool}
    (respects : ∀ s t, Agree s t → policy s = policy t) (limits : Limits) (bytes ticks : Nat)
    {s t : State} (agree : Agree s t) :
    OutcomeAgree (forceHostedWith policy limits bytes ticks s).1 (forceHostedWith policy limits bytes ticks t).1 ∧
      (forceHostedWith policy limits bytes ticks t).2 = (forceHostedWith policy limits bytes ticks s).2 := by
  unfold forceHostedWith
  have depth : s.stack.length = t.stack.length := by
    have := congrArg List.length agree.stack; simpa using this
  rw [← depth]
  exact agree_forceHostedFrom respects limits bytes ticks s t _ agree

section ExceptLemmas
variable {ε α β : Type}
@[simp] theorem except_bind_ok (x : Except ε α) (k : α → Except ε β) (r : β) :
    (x >>= k) = .ok r ↔ ∃ a, x = .ok a ∧ k a = .ok r := by
  cases x <;> simp [bind, Except.bind]
@[simp] theorem except_map_ok (g : α → β) (x : Except ε α) (r : β) :
    (g <$> x) = .ok r ↔ ∃ a, x = .ok a ∧ g a = r := by
  cases x <;> simp [Functor.map, Except.map]
@[simp] theorem except_pure_ok (a b : α) : ((pure a : Except ε α) = .ok b) ↔ a = b := by
  simp [pure, Except.pure]
@[simp] theorem except_throw_ok (e : ε) (a : α) : ((throw e : Except ε α) = .ok a) ↔ False := by
  constructor <;> intro h <;> cases h
@[simp] theorem except_error_ok (e : ε) (a : α) : ((Except.error e : Except ε α) = .ok a) ↔ False := by
  constructor <;> intro h <;> cases h
end ExceptLemmas

/-- Extraction results agree: same Data, same remaining budget, agreeing states. -/
def ResultAgree (r r' : Result) : Prop :=
  r'.value = r.value ∧ r'.remaining = r.remaining ∧ Agree r.state r'.state

theorem foldlM_agree
    {step : List (String × Data) × State × Budget → String × Nat →
      Except (Failure × State × Budget) (List (String × Data) × State × Budget)}
    (stepAgree : ∀ (acc : List (String × Data)) (st st' : State) (b : Budget) (field : String × Nat)
        (out : List (String × Data) × State × Budget),
      Agree st st' → step (acc, st, b) field = .ok out →
      ∃ out', step (acc, st', b) field = .ok out' ∧ out'.1 = out.1 ∧ out'.2.2 = out.2.2 ∧
        Agree out.2.1 out'.2.1) :
    ∀ (fields : List (String × Nat)) (acc : List (String × Data)) (st st' : State) (b : Budget)
      (out : List (String × Data) × State × Budget),
      Agree st st' → fields.foldlM step (acc, st, b) = .ok out →
      ∃ out', fields.foldlM step (acc, st', b) = .ok out' ∧
        out'.1 = out.1 ∧ out'.2.2 = out.2.2 ∧ Agree out.2.1 out'.2.1 := by
  intro fields
  induction fields with
  | nil =>
    intro acc st st' b out agree folded
    simp [List.foldlM] at folded
    subst folded
    exact ⟨_, rfl, rfl, rfl, agree⟩
  | cons field rest ih =>
    intro acc st st' b out agree folded
    simp only [List.foldlM_cons, except_bind_ok] at folded
    obtain ⟨mid, first, restFolded⟩ := folded
    obtain ⟨mid', first', same1, same2, midAgree⟩ := stepAgree acc st st' b field mid agree first
    obtain ⟨out', folded', outSame1, outSame2, outAgree⟩ :=
      ih mid.1 mid.2.1 mid'.2.1 mid.2.2 out midAgree restFolded
    refine ⟨out', ?_, outSame1, outSame2, outAgree⟩
    simp only [List.foldlM_cons, except_bind_ok]
    refine ⟨mid', first', ?_⟩
    have shape : mid' = (mid.1, mid'.2.1, mid.2.2) := by
      obtain ⟨a, b, c⟩ := mid'
      simp only at same1 same2
      rw [same1, same2]
    rw [shape]; exact folded'

theorem agree_entered {s t : State} (agree : Agree s t) (address : Nat) :
    Agree ⟨s.heap, .enter address, []⟩ ⟨t.heap, .enter address, []⟩ :=
  Agree.mk' agree.heap rfl rfl

/-- One field of a record's materialization (the body of `materializeWith`'s fold). -/
def recordStep (policy : State → Bool) (limits : Limits) (depth : Nat)
    (prior : List (String × Data) × State × Budget) (field : String × Nat) :
    Except (Failure × State × Budget) (List (String × Data) × State × Budget) := do
  if prior.2.2.nodes = 0 then throw (.budget,prior.2.1,prior.2.2)
  let entered : State := {prior.2.1 with control:=.enter field.2,stack:=[]}
  let (outcome,ticks) := forceHostedWith policy limits prior.2.2.bytes prior.2.2.ticks entered
  let nextBudget := {prior.2.2 with ticks:=ticks}
  match outcome with
  | .finished forced retained =>
    let child ← materializeWith policy limits depth nextBudget forced retained
    pure ((field.1,child.value)::prior.1,child.state,child.remaining)
  | .suspended reason retained => throw (suspensionFailure reason,retained,nextBudget)
  | .divergent _ retained => throw (.divergent,retained,nextBudget)
  | .refused _ retained => throw (.refused,retained,nextBudget)
  | .yielded _ retained => throw (.yielded,retained,nextBudget)

theorem materializeWith_record (policy : State → Bool) (limits : Limits) (depth : Nat) (budget : Budget)
    (fields : List (String × Nat)) (state : State) :
    materializeWith policy limits (depth+1) budget (.record fields) state = (do
      if budget.nodes = 0 then throw (.budget,state,budget)
      let remaining := {budget with nodes:=budget.nodes-1}
      if (fields.map Prod.fst).eraseDups.length != fields.length then throw (.duplicateField,state,remaining)
      if fields.length > remaining.nodes then throw (.budget,state,remaining)
      let pair ← fields.foldlM (recordStep policy limits depth) ([],state,remaining)
      pure ⟨.record pair.1.reverse,pair.2.1,pair.2.2⟩) := rfl

/-- The three admission checks a record passes before its fields are forced. -/
def RecordGate (budget : Budget) (fields : List (String × Nat)) : Prop :=
  ¬budget.nodes = 0 ∧
    ¬((fields.map Prod.fst).eraseDups.length != fields.length) = true ∧ ¬fields.length > budget.nodes - 1

def recordStart (budget : Budget) (_fields : List (String × Nat)) : Budget :=
  {nodes := budget.nodes - 1, ticks := budget.ticks, bytes := budget.bytes}

theorem materializeWith_record_gate {policy : State → Bool} {limits : Limits} {depth : Nat} {budget : Budget}
    {fields : List (String × Nat)} {state : State} (gate : RecordGate budget fields) :
    materializeWith policy limits (depth+1) budget (.record fields) state =
      (fields.foldlM (recordStep policy limits depth) ([],state,recordStart budget fields) >>= fun pair =>
        pure (⟨.record pair.1.reverse,pair.2.1,pair.2.2⟩ : Result)) := by
  obtain ⟨c1, c3, c4⟩ := gate
  rw [materializeWith_record]
  simp only [c1, c3, c4, ↓reduceIte, Bool.false_eq_true, recordStart]

theorem materializeWith_record_ok {policy : State → Bool} {limits : Limits} {depth : Nat} {budget : Budget}
    {fields : List (String × Nat)} {state : State} {r : Result}
    (found : materializeWith policy limits (depth+1) budget (.record fields) state = .ok r) :
    RecordGate budget fields ∧ ∃ pair,
      fields.foldlM (recordStep policy limits depth) ([],state,recordStart budget fields) = .ok pair ∧
      r = ⟨.record pair.1.reverse,pair.2.1,pair.2.2⟩ := by
  have gate : RecordGate budget fields := by
    rw [materializeWith_record] at found
    by_cases c1 : budget.nodes = 0
    · simp only [c1, ↓reduceIte] at found; cases found
    by_cases c3 : ((fields.map Prod.fst).eraseDups.length != fields.length) = true
    · simp only [c1, c3, ↓reduceIte] at found; cases found
    by_cases c4 : fields.length > budget.nodes - 1
    · simp only [c1, c3, c4, ↓reduceIte] at found; cases found
    exact ⟨c1, c3, c4⟩
  refine ⟨gate, ?_⟩
  rw [materializeWith_record_gate gate] at found
  obtain ⟨pair, folded, done⟩ := (except_bind_ok _ _ _).mp found
  exact ⟨pair, folded, ((except_pure_ok _ _).mp done).symm⟩

/-- A value that is not a closure is its own erasure. -/
theorem trimValue_eq_of_not_closure {value value' : RuntimeValue} (same : trimValue 0 value = trimValue 0 value')
    (notClosure : ∀ body environment, value ≠ .closure body environment) : value' = value := by
  cases value <;> cases value' <;> simp_all

/-- **Materialization agrees**, for values that agree up to erasure. -/
theorem agree_materializeWith {policy : State → Bool}
    (respects : ∀ s t, Agree s t → policy s = policy t) (limits : Limits) :
    ∀ (depth : Nat) (budget : Budget) (value value' : RuntimeValue) (s t : State) (r : Result),
      trimValue 0 value = trimValue 0 value' → Agree s t → materializeWith policy limits depth budget value s = .ok r →
      ∃ r', materializeWith policy limits depth budget value' t = .ok r' ∧ ResultAgree r r' := by
  intro depth
  induction depth with
  | zero => intro budget value value' s t r _ _ found; simp [materializeWith] at found
  | succ depth ih =>
    intro budget value value' s t r sameValue agree found
    cases value with
    | closure body environment => simp [materializeWith] at found; split at found <;> simp at found
    | specification metadata extension => simp [materializeWith] at found; split at found <;> simp at found
    | prototype spec target => simp [materializeWith] at found; split at found <;> simp at found
    | natural n =>
      have := trimValue_eq_of_not_closure sameValue (by intros; simp); subst this
      simp [materializeWith] at found
      split at found
      · simp at found
      · split at found
        · simp at found
        · rename_i c1 c2
          simp at found
          refine ⟨{ r with state := t }, ?_, rfl, rfl, ?_⟩
          · rw [← found]; simp [materializeWith, c1, c2]
          · rw [← found]; exact agree
    | boolean b =>
      have := trimValue_eq_of_not_closure sameValue (by intros; simp); subst this
      simp [materializeWith] at found
      split at found
      · simp at found
      · split at found
        · simp at found
        · rename_i c1 c2
          simp at found
          refine ⟨{ r with state := t }, ?_, rfl, rfl, ?_⟩
          · rw [← found]; simp [materializeWith, c1, c2]
          · rw [← found]; exact agree
    | label l =>
      have := trimValue_eq_of_not_closure sameValue (by intros; simp); subst this
      simp [materializeWith] at found
      split at found
      · simp at found
      · split at found
        · simp at found
        · rename_i c1 c2
          simp at found
          refine ⟨{ r with state := t }, ?_, rfl, rfl, ?_⟩
          · rw [← found]; simp [materializeWith, c1, c2]
          · rw [← found]; exact agree
    | variant label payload =>
      have := trimValue_eq_of_not_closure sameValue (by intros; simp); subst this
      simp [materializeWith] at found
      split at found
      · simp at found
      · split at found
        · simp at found
        · rename_i c1 c2
          cases forced : (forceHostedWith policy limits budget.bytes budget.ticks ⟨s.heap, .enter payload, []⟩).1 with
          | finished value retained =>
            rw [forced] at found
            have ⟨rel, ticksEq⟩ := agree_forceHostedWith respects limits budget.bytes budget.ticks (agree_entered agree payload)
            rw [forced] at rel
            cases forcedT : (forceHostedWith policy limits budget.bytes budget.ticks ⟨t.heap, .enter payload, []⟩).1 <;>
              rw [forcedT] at rel <;>
              simp only [OutcomeAgree, eraseOutcome, Outcome.finished.injEq, reduceCtorEq] at rel
            rename_i valueT retainedT
            obtain ⟨valueEq, retainedAgree⟩ := rel
            simp at found
            obtain ⟨a, materialized, rfl⟩ := found
            obtain ⟨a', materialized', aValue, aRemaining, aAgree⟩ := ih _ _ _ _ _ _ valueEq retainedAgree materialized
            refine ⟨⟨.variant label a'.value, a'.state, a'.remaining⟩, ?_, by simp [aValue], aRemaining, aAgree⟩
            simp [materializeWith, c1, c2, forcedT, ticksEq, materialized']
          | _ => rw [forced] at found; simp at found
    | record fields =>
      have := trimValue_eq_of_not_closure sameValue (by intros; simp); subst this
      obtain ⟨gate, out, folded, rfl⟩ := materializeWith_record_ok found
      have key := foldlM_agree ?_ fields [] s t _ out agree folded
      · obtain ⟨out', folded', same1, same2, outAgree⟩ := key
        refine ⟨⟨.record out'.1.reverse, out'.2.1, out'.2.2⟩, ?_, by simp [same1], by simp [same2], outAgree⟩
        rw [materializeWith_record_gate gate, folded']
        rfl
      · intro acc st st' b field out stAgree stepped
        unfold recordStep at stepped ⊢
        simp only at stepped ⊢
        split at stepped
        · cases stepped
        · rename_i cond
          simp only [cond, ↓reduceIte, Bool.false_eq_true]
          have ⟨rel, ticksEq⟩ := agree_forceHostedWith respects limits b.bytes b.ticks
            (agree_entered stAgree field.2)
          cases forced : (forceHostedWith policy limits b.bytes b.ticks ⟨st.heap, .enter field.2, []⟩).1 with
          | finished value retained =>
            rw [forced] at stepped rel
            cases forcedT : (forceHostedWith policy limits b.bytes b.ticks ⟨st'.heap, .enter field.2, []⟩).1 <;>
              rw [forcedT] at rel <;>
              simp only [OutcomeAgree, eraseOutcome, Outcome.finished.injEq, reduceCtorEq] at rel
            obtain ⟨valueEq, retainedAgree⟩ := rel
            obtain ⟨a, materialized, done⟩ := (except_bind_ok _ _ _).mp stepped
            have := (except_pure_ok _ _).mp done
            subst this
            obtain ⟨a', materialized', aValue, aRemaining, aAgree⟩ := ih _ _ _ _ _ _ valueEq retainedAgree materialized
            refine ⟨((field.1, a'.value) :: acc, a'.state, a'.remaining), ?_, by simp [aValue],
              aRemaining, aAgree⟩
            simp only [forcedT, ticksEq, materialized']
            rfl
          | _ => rw [forced] at stepped; cases stepped

theorem stack_nil_of_agree {s t : State} (agree : Agree s t) (empty : s.stack = []) : t.stack = [] := by
  have := congrArg List.length agree.stack
  simp [empty] at this
  exact List.eq_nil_of_length_eq_zero this.symm

theorem eraseControl_eq_complete {control : Control} {value : RuntimeValue}
    (same : eraseControl control = .complete (trimValue 0 value)) :
    ∃ value', control = .complete value' ∧ trimValue 0 value' = trimValue 0 value := by
  cases control <;> simp [eraseControl] at same
  exact ⟨_, rfl, same⟩

/-- **Completion agrees.** -/
theorem agree_completeWith {policy : State → Bool}
    (respects : ∀ s t, Agree s t → policy s = policy t) (limits : Limits)
    (budget : Budget) {s t : State} {r : Result} (agree : Agree s t)
    (found : completeWith policy limits budget s = .ok r) :
    ∃ r', completeWith policy limits budget t = .ok r' ∧ ResultAgree r r' := by
  cases allowed : policy s with
  | false => simp [completeWith, allowed] at found
  | true =>
    have allowedT : policy t = true := by rw [← respects s t agree]; exact allowed
    unfold completeWith at found ⊢
    simp only [allowed, allowedT, Bool.not_true, Bool.false_eq_true, if_false] at found ⊢
    split at found
    · rename_i value control stack hcontrol hstack
      have tStack := stack_nil_of_agree agree hstack
      have controlEq := agree.control
      rw [hcontrol] at controlEq
      obtain ⟨value', tControl, sameValue⟩ := eraseControl_eq_complete (by simpa [eraseControl] using controlEq.symm)
      rw [tControl, tStack]
      simp only [except_bind_ok] at found
      obtain ⟨a, materialized, rest⟩ := found
      obtain ⟨a', materialized', aValue, aRemaining, aAgree⟩ :=
        agree_materializeWith respects limits _ _ _ _ _ _ _ sameValue.symm agree materialized
      split at rest
      · simp at rest
      · rename_i small
        simp at rest; subst rest
        refine ⟨a', ?_, aValue, aRemaining, aAgree⟩
        have small' : ¬ budget.bytes < a'.value.canonicalBytes := by rw [aValue]; exact small
        simp [materialized', small']
    · simp at found

/-- **Plan extraction agrees.** -/
theorem agree_yieldedPlanWith {policy : State → Bool}
    (respects : ∀ s t, Agree s t → policy s = policy t) (limits : Limits)
    (budget : Budget) {s t : State} {r : Result} (agree : Agree s t)
    (found : yieldedPlanWith policy limits budget s = .ok r) :
    ∃ r', yieldedPlanWith policy limits budget t = .ok r' ∧ ResultAgree r r' := by
  unfold yieldedPlanWith at found ⊢
  split at found
  · rename_i plan yielded
    have controlT : t.control = .yielded plan := by
      have := agree.control
      rw [yielded] at this
      exact eraseControl_eq_yielded.mp (by simpa [eraseControl] using this.symm)
    rw [controlT]
    have ⟨rel, ticksEq⟩ := agree_forceHostedWith respects limits budget.bytes budget.ticks (agree_entered agree plan)
    simp only at found rel ticksEq ⊢
    cases forced : forceHostedWith policy limits budget.bytes budget.ticks ⟨s.heap, .enter plan, []⟩ with
    | mk outcome ticks =>
      rw [forced] at found rel ticksEq
      cases outcome with
      | finished value retained =>
        cases forcedT : forceHostedWith policy limits budget.bytes budget.ticks ⟨t.heap, .enter plan, []⟩ with
        | mk outcome' ticks' =>
          rw [forcedT] at rel ticksEq
          simp only at rel ticksEq
          subst ticksEq
          cases outcome' <;>
            simp only [OutcomeAgree, eraseOutcome, Outcome.finished.injEq, reduceCtorEq] at rel
          obtain ⟨valueEq, retainedAgree⟩ := rel
          simp only [except_bind_ok] at found
          obtain ⟨a, materialized, rest⟩ := found
          by_cases small : a.value.canonicalBytes > budget.bytes
          · simp [small] at rest
          simp [small] at rest
          subst rest
          obtain ⟨a', materialized', aValue, aRemaining, aAgree⟩ :=
            agree_materializeWith respects limits _ _ _ _ _ _ _ valueEq retainedAgree materialized
          refine ⟨{a' with state := {a'.state with control := t.control, stack := t.stack}},
            ?_, aValue, aRemaining, Agree.mk' aAgree.heap agree.control agree.stack⟩
          have small' : ¬ budget.bytes < a'.value.canonicalBytes := by rw [aValue]; exact small
          simp [materialized', controlT, small']
      | _ => simp at found
  · simp at found

/-! ## Settling and trimming agree -/

theorem settle_heap_erased (state : State) :
    (settle state).heap.map eraseCell = state.heap.map eraseCell := by
  apply Array.ext_getElem?
  intro i
  simp only [settle, Array.getElem?_map, Array.getElem?_mapIdx, Option.map_map]
  cases state.heap[i]? with
  | none => rfl
  | some cell => cases cell <;> rfl

/-- **A settled state agrees with the state it settled.** -/
theorem agree_settle (state : State) : Agree state (settle state) :=
  Agree.mk' (settle_heap_erased state).symm rfl rfl

@[simp] theorem settle_size (state : State) : (settle state).heap.size = state.heap.size := by
  simp [settle]

/-- Trimming to a predicate with one dummy, then erasing with another, is erasing. -/
theorem trimEnv_redummy (dummy dummy' : Nat) :
    ∀ (env : Environment) (keep : Nat → Bool),
      trimEnv keep dummy (trimEnv keep dummy' env) = trimEnv keep dummy env
  | [], _ => rfl
  | a :: rest, keep => by
    simp only [trimEnv]
    rw [trimEnv_redummy dummy dummy' rest]
    cases keep 0 <;> rfl

theorem trimValue_redummy (dummy : Nat) (value : RuntimeValue) : trimValue 0 (trimValue dummy value) = trimValue 0 value := by
  cases value <;> simp [trimValue, trimEnv_redummy]

theorem trim_heap_erased (state : State) :
    (trim state).heap.map eraseCell = state.heap.map eraseCell := by
  apply Array.ext_getElem?
  intro i
  simp only [trim, Array.getElem?_map, Array.getElem?_mapIdx, Option.map_map]
  cases state.heap[i]? with
  | none => rfl
  | some cell =>
    cases cell <;> simp [trimCell, eraseCell, trimClosure, trimEnv_redummy, trimValue_redummy]

/-- **A trimmed state agrees with the state it trimmed.** -/
theorem agree_trim (state : State) : Agree state (trim state) :=
  Agree.mk' (trim_heap_erased state).symm rfl rfl

@[simp] theorem trim_size (state : State) : (trim state).heap.size = state.heap.size := by
  simp [trim]

/-! ## The turn's segment from an agreeing state -/

/-- **The turn's segment from an agreeing state** (settled, trimmed) agrees with the segment
from the state itself. `Turn.resumeActivity` resumes the decoded checkpoint and runs
`forceHostedWith` (inside `executeStateWith`) under limits counted past the checkpoint's
heap, which neither settling nor trimming changes; then it extracts the result
(`completeWith`) or, at a yield, the Plan (`yieldedPlanWith`). For every response, limits,
byte allowance and tick budget:
* the hosted run ends in the same outcome (same Plan address, divergence, refusal, or
  tick/capacity suspension; a value equal up to erasure) with agreeing retained states and
  EXACTLY the same remaining ticks;
* a Plan that extracts from the original extracts from the other run as the same Data with
  the same remaining budget;
* a result that extracts from the original extracts from the other run as the same Data
  with the same remaining budget. -/
theorem agree_resume_segment {state state' resumed : State} {response : Term} (agree : Agree state state')
    (yielded : resume response state = some resumed) (limits : Limits) (bytes ticks : Nat) (budget : Budget) :
    ∃ resumed', resume response state' = some resumed' ∧
      OutcomeAgree (forceHostedWith (fun _ => true) limits bytes ticks resumed).1
        (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 ∧
      (forceHostedWith (fun _ => true) limits bytes ticks resumed').2 =
        (forceHostedWith (fun _ => true) limits bytes ticks resumed).2 ∧
      (∀ plan y r, (forceHostedWith (fun _ => true) limits bytes ticks resumed).1 = .yielded plan y →
        yieldedPlan limits budget y = .ok r →
        ∃ y' r', (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 = .yielded plan y' ∧
          Agree y y' ∧ yieldedPlan limits budget y' = .ok r' ∧ ResultAgree r r') ∧
      (∀ value y r, (forceHostedWith (fun _ => true) limits bytes ticks resumed).1 = .finished value y →
        complete limits budget y = .ok r →
        ∃ value' y' r', (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 = .finished value' y' ∧
          complete limits budget y' = .ok r' ∧ ResultAgree r r') := by
  obtain ⟨resumed', again, agreeR⟩ := agree_resume agree response yielded
  have always : ∀ s t, Agree s t → (fun _ => true : State → Bool) s = (fun _ => true : State → Bool) t :=
    fun _ _ _ => rfl
  have ⟨ran, sameTicks⟩ := agree_forceHostedWith always limits bytes ticks agreeR
  refine ⟨resumed', again, ran, sameTicks, ?_, ?_⟩
  · intro plan y r run extracted
    rw [run] at ran
    cases runT : (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 <;> rw [runT] at ran <;>
      simp only [OutcomeAgree, eraseOutcome, Outcome.yielded.injEq, reduceCtorEq] at ran
    obtain ⟨same, yAgree⟩ := ran
    subst same
    obtain ⟨r', extracted', resultAgree⟩ := agree_yieldedPlanWith always limits budget yAgree extracted
    exact ⟨_, r', rfl, yAgree, extracted', resultAgree⟩
  · intro value y r run completed
    rw [run] at ran
    cases runT : (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 <;> rw [runT] at ran <;>
      simp only [OutcomeAgree, eraseOutcome, Outcome.finished.injEq, reduceCtorEq] at ran
    obtain ⟨_, yAgree⟩ := ran
    obtain ⟨r', completed', resultAgree⟩ := agree_completeWith always limits budget yAgree completed
    exact ⟨_, _, r', rfl, completed', resultAgree⟩

theorem settle_resume_segment {state resumed : State} {response : Term}
    (yielded : resume response state = some resumed) (limits : Limits) (bytes ticks : Nat) (budget : Budget) :
    ∃ resumed', resume response (settle state) = some resumed' ∧
      OutcomeAgree (forceHostedWith (fun _ => true) limits bytes ticks resumed).1
        (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 ∧
      (forceHostedWith (fun _ => true) limits bytes ticks resumed').2 =
        (forceHostedWith (fun _ => true) limits bytes ticks resumed).2 ∧
      (∀ plan y r, (forceHostedWith (fun _ => true) limits bytes ticks resumed).1 = .yielded plan y →
        yieldedPlan limits budget y = .ok r →
        ∃ y' r', (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 = .yielded plan y' ∧
          Agree y y' ∧ yieldedPlan limits budget y' = .ok r' ∧ ResultAgree r r') ∧
      (∀ value y r, (forceHostedWith (fun _ => true) limits bytes ticks resumed).1 = .finished value y →
        complete limits budget y = .ok r →
        ∃ value' y' r', (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 = .finished value' y' ∧
          complete limits budget y' = .ok r' ∧ ResultAgree r r') :=
  agree_resume_segment (agree_settle state) yielded limits bytes ticks budget

theorem trim_resume_segment {state resumed : State} {response : Term}
    (yielded : resume response state = some resumed) (limits : Limits) (bytes ticks : Nat) (budget : Budget) :
    ∃ resumed', resume response (trim state) = some resumed' ∧
      OutcomeAgree (forceHostedWith (fun _ => true) limits bytes ticks resumed).1
        (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 ∧
      (forceHostedWith (fun _ => true) limits bytes ticks resumed').2 =
        (forceHostedWith (fun _ => true) limits bytes ticks resumed).2 ∧
      (∀ plan y r, (forceHostedWith (fun _ => true) limits bytes ticks resumed).1 = .yielded plan y →
        yieldedPlan limits budget y = .ok r →
        ∃ y' r', (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 = .yielded plan y' ∧
          Agree y y' ∧ yieldedPlan limits budget y' = .ok r' ∧ ResultAgree r r') ∧
      (∀ value y r, (forceHostedWith (fun _ => true) limits bytes ticks resumed).1 = .finished value y →
        complete limits budget y = .ok r →
        ∃ value' y' r', (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 = .finished value' y' ∧
          complete limits budget y' = .ok r' ∧ ResultAgree r r') :=
  agree_resume_segment (agree_trim state) yielded limits bytes ticks budget

#assert_axioms agree_resume_segment agree_forceHostedFrom erase_stepRaw freeIn_rename

end Minidregg.Theory.ObjectiveBendDemandCollect
