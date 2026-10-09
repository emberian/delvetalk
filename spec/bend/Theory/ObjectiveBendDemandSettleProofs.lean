/- Settling a checkpoint changes no transition. Definitions: `settle`, `checkpoint` in
`Theory.ObjectiveBendDemandCollect`. Ported from Mini's
ObjectiveBendDemandSettleProofs to this edition's machine (native cells, the hosted
text tariff `forceHostedFrom`, the compiled `stepRawFast`).

The machine reads a cached cell's VALUE only; a cached cell's origin is never read again
(`stepRaw` reads an origin only from an `evaluating` cell, at its update frame, and a
native cell's Data, which settling leaves alone). So two states that differ only in the
origins of cached cells take the same transitions. The relation is `Agree s t`: erasing
every cached origin (`eraseState`) makes them equal.

* `erase_stepRaw` / `agree_stepRaw`: one transition agrees.
* `agree_forceHostedFrom`: hosted forcing (the turn's runner: text tariff, byte
  admission, capacity check from `sizesAfter`) agrees EXACTLY, with the same remaining
  ticks, capacity suspensions included.
* `agree_materializeWith`, `agree_completeWith`, `agree_yieldedPlanWith`,
  `agree_executeStateWith`: extraction gives the same Data and budget.
* `agree_settle`: `Agree s (settle s)`.
* `settle_resume_segment`: the turn's segment (`executeStateWith`, then the Plan's
  `yieldedPlanWith` on a yield) from a resumed settled state agrees with the segment
  from the state it settled.

Not ported: `typed_settle` (this edition has no state-typing judgment,
Mini's ObjectiveBendDemandTyping), and the collector's renaming simulation
(Mini's ObjectiveBendDemandCollectProofs), so `checkpoint = collect ∘ settle` is
covered here for its `settle` half only. -/
import Theory.ObjectiveBendDemandCollect
import Theory.ObjectiveBendDemandData
namespace Minidregg.Theory.ObjectiveBendDemandCollect
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData
set_option autoImplicit false

/-! ## Erasing cached origins -/

/-- Forget a cached cell's origin. -/
def eraseCell : Cell → Cell
  | .cached _ value => .cached ⟨.nat 0, []⟩ value
  | cell => cell

@[simp] theorem eraseCell_eraseCell (cell : Cell) : eraseCell (eraseCell cell) = eraseCell cell := by
  cases cell <;> rfl

@[simp] theorem eraseCell_suspended (origin : Closure) : eraseCell (.suspended origin) = .suspended origin := rfl
@[simp] theorem eraseCell_evaluating (origin : Closure) : eraseCell (.evaluating origin) = .evaluating origin := rfl
@[simp] theorem eraseCell_native (origin : Data) : eraseCell (.native origin) = .native origin := rfl
@[simp] theorem eraseCell_nativeCached (origin : Data) (value : RuntimeValue) :
    eraseCell (.nativeCached origin value) = .nativeCached origin value := rfl
@[simp] theorem eraseCell_cached (origin : Closure) (value : RuntimeValue) :
    eraseCell (.cached origin value) = .cached ⟨.nat 0, []⟩ value := rfl

@[simp] theorem eraseCell_comp : eraseCell ∘ eraseCell = eraseCell := by
  funext cell; simp

def eraseState (state : State) : State := ⟨state.heap.map eraseCell, state.control, state.stack⟩

/-- Two states agree up to the origins of cached cells. -/
def Agree (s t : State) : Prop := eraseState s = eraseState t

theorem Agree.refl (s : State) : Agree s s := rfl
theorem Agree.symm {s t : State} (agree : Agree s t) : Agree t s := Eq.symm agree
theorem Agree.trans {s t u : State} (one : Agree s t) (two : Agree t u) : Agree s u := Eq.trans one two

theorem Agree.control {s t : State} (agree : Agree s t) : s.control = t.control := by
  have same := congrArg State.control (show eraseState s = eraseState t from agree)
  simpa [eraseState] using same
theorem Agree.stack {s t : State} (agree : Agree s t) : s.stack = t.stack := by
  have same := congrArg State.stack (show eraseState s = eraseState t from agree)
  simpa [eraseState] using same
theorem Agree.heap {s t : State} (agree : Agree s t) : s.heap.map eraseCell = t.heap.map eraseCell :=
  congrArg State.heap (show eraseState s = eraseState t from agree)
theorem Agree.size {s t : State} (agree : Agree s t) : s.heap.size = t.heap.size := by
  have := congrArg Array.size agree.heap
  simpa using this

theorem Agree.mk' {s t : State} (heap : s.heap.map eraseCell = t.heap.map eraseCell)
    (control : s.control = t.control) (stack : s.stack = t.stack) : Agree s t := by
  unfold Agree eraseState; rw [heap, control, stack]

theorem agree_eraseState (s : State) : Agree (eraseState s) s := by
  unfold Agree eraseState; simp [Array.map_map]

theorem eraseState_eraseState (s : State) : eraseState (eraseState s) = eraseState s :=
  agree_eraseState s

/-! ## One transition -/

theorem erase_set! (heap : Array Cell) (address : Nat) (cell : Cell) :
    (heap.set! address cell).map eraseCell = (heap.map eraseCell).set! address (eraseCell cell) := by
  simp [Array.set!_eq_setIfInBounds, Array.map_setIfInBounds]

theorem erase_allocateFields (heap : Array Cell) (environment : Environment) (fields : List (String × Term)) :
    allocateFields (heap.map eraseCell) environment fields =
      ((allocateFields heap environment fields).1.map eraseCell, (allocateFields heap environment fields).2) := by
  have loop : ∀ (fields : List (String × Term)) (heap : Array Cell) (names : List (String × Address)),
      fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,prior.1.size)::prior.2)) (heap.map eraseCell, names) =
      ((fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,prior.1.size)::prior.2)) (heap, names)).1.map eraseCell,
       (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,prior.1.size)::prior.2)) (heap, names)).2) := by
    intro fields
    induction fields with
    | nil => intro heap names; rfl
    | cons field rest ih =>
      intro heap names
      simp only [List.foldl_cons, Array.size_map]
      have := ih (heap.push (.suspended ⟨field.2,environment⟩)) ((field.1, heap.size) :: names)
      rw [← this]
      simp [Array.map_push]
  simp only [allocateFields]
  rw [loop]

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
      simp [Array.map_push]
  simp only [allocateNativeFields]
  rw [loop]

theorem erase_forceNative (heap : Array Cell) (value : Data) :
    forceNative (heap.map eraseCell) value =
      ((forceNative heap value).1.map eraseCell, (forceNative heap value).2) := by
  cases value <;> simp [forceNative, erase_allocateNativeFields, Array.map_push]

/-- **Erasure commutes with a transition** (up to the erasure of its result): the
machine never reads a cached cell's origin. -/
theorem erase_stepRaw (s : State) : eraseState (stepRaw (eraseState s)) = eraseState (stepRaw s) := by
  obtain ⟨heap, control, stack⟩ := s
  cases control with
  | complete value => simp [stepRaw, eraseState, Array.map_map]
  | refused reason => simp [stepRaw, eraseState, Array.map_map]
  | blackhole address => simp [stepRaw, eraseState, Array.map_map]
  | yielded plan => simp [stepRaw, eraseState, Array.map_map]
  | nativeApplication function argument remaining =>
    cases remaining <;> simp [stepRaw, eraseState, Array.map_map]
  | enter address =>
    cases found : heap[address]? with
    | none => simp [stepRaw, eraseState, Array.getElem?_map, found, Array.map_map]
    | some cell =>
      cases cell <;>
        simp [stepRaw, eraseState, Array.getElem?_map, found, Array.map_map, erase_forceNative]
  | evaluate term environment =>
    cases term <;> simp [stepRaw, eraseState, Array.map_map, Array.map_push, erase_allocateFields] <;>
      (try split) <;> simp [Array.map_map, Array.map_push]
  | returned value =>
    cases stack with
    | nil => simp [stepRaw, eraseState, Array.map_map]
    | cons frame rest =>
      cases frame with
      | update address =>
        cases found : heap[address]? with
        | none => simp [stepRaw, eraseState, Array.getElem?_map, found, Array.map_map]
        | some cell =>
          cases cell <;>
            simp [stepRaw, eraseState, Array.getElem?_map, found, Array.map_map]
      | _ =>
        simp [stepRaw, eraseState, Array.map_map, erase_allocateFields] <;>
          (repeat' split) <;> simp [Array.map_map, Array.map_push]

theorem agree_stepRaw {s t : State} (agree : Agree s t) : Agree (stepRaw s) (stepRaw t) := by
  unfold Agree
  rw [← erase_stepRaw s, ← erase_stepRaw t, agree]

/-! ## Bounded runs and hosted forcing agree exactly -/

def eraseOutcome : Outcome → Outcome
  | .finished value state => .finished value (eraseState state)
  | .suspended reason state => .suspended reason (eraseState state)
  | .divergent address state => .divergent address (eraseState state)
  | .refused reason state => .refused reason (eraseState state)
  | .yielded plan state => .yielded plan (eraseState state)

/-- Outcomes agree: same constructor, same payload, agreeing retained states. -/
def OutcomeAgree (o o' : Outcome) : Prop := eraseOutcome o = eraseOutcome o'

theorem agree_runBounded_zero (limits : Limits) {s t : State} (agree : Agree s t) :
    OutcomeAgree (runBounded limits 0 s) (runBounded limits 0 t) := by
  unfold runBounded
  rw [agree.control]
  split <;> simp only [OutcomeAgree, eraseOutcome] <;> exact congrArg _ agree

theorem agree_resume {s t : State} (agree : Agree s t) (response : Term) {s' : State}
    (resumed : resume response s = some s') :
    ∃ t', resume response t = some t' ∧ Agree s' t' := by
  obtain ⟨plan, yielded⟩ := resume_requires_yield response s (by rw [resumed]; rfl)
  have controlT : t.control = .yielded plan := by rw [← agree.control, yielded]
  simp only [resume, yielded] at resumed
  cases resumed
  refine ⟨{t with control := .evaluate response []}, by simp [resume, controlT], ?_⟩
  exact Agree.mk' agree.heap rfl agree.stack

/-- The hosted tariff reads only control and stack. -/
theorem textStepCost_agree {s t : State} (agree : Agree s t) (ticks : Nat) :
    textStepCost s ticks = textStepCost t ticks := by
  unfold textStepCost; rw [agree.control, agree.stack]

theorem sizesAfter_erase (s : State) (depth : Nat) :
    ObjectiveBendDemandMachineFast.sizesAfter (eraseState s) depth =
      ObjectiveBendDemandMachineFast.sizesAfter s depth := by
  obtain ⟨heap, control, stack⟩ := s
  cases control with
  | enter address =>
    simp only [ObjectiveBendDemandMachineFast.sizesAfter, eraseState, Array.getElem?_map, Array.size_map]
    cases heap[address]? with
    | none => rfl
    | some cell => cases cell <;> rfl
  | _ => simp [ObjectiveBendDemandMachineFast.sizesAfter, eraseState]

theorem sizesAfter_agree {s t : State} (agree : Agree s t) (depth : Nat) :
    ObjectiveBendDemandMachineFast.sizesAfter s depth = ObjectiveBendDemandMachineFast.sizesAfter t depth := by
  rw [← sizesAfter_erase s, ← sizesAfter_erase t]
  exact congrArg (fun state => ObjectiveBendDemandMachineFast.sizesAfter state depth) agree

/-- **Hosted forcing agrees**, for any policy that agreeing states pass alike: the
same outcome (up to cached origins) and the same remaining ticks. -/
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
  have hc := agree.control
  have hs := agree.stack
  have cost := textStepCost_agree agree ticks
  have sizes := sizesAfter_agree agree depth
  have allowed := respects s t agree
  have next : Agree (ObjectiveBendDemandMachineFast.stepRawFast s)
      (ObjectiveBendDemandMachineFast.stepRawFast t) := by
    rw [ObjectiveBendDemandMachineFast.stepRawFast_eq_stepRaw,
      ObjectiveBendDemandMachineFast.stepRawFast_eq_stepRaw]
    exact agree_stepRaw agree
  rw [forceHostedFrom.eq_def (state := s), forceHostedFrom.eq_def (state := t)]
  cases ticks with
  | zero => exact ⟨agree_runBounded_zero limits agree, rfl⟩
  | succ remaining =>
    simp only []
    rw [← hc, ← hs, ← cost, ← sizes, ← allowed]
    have same : OutcomeAgree (.suspended .capacity s) (.suspended .capacity t) := by
      simp only [OutcomeAgree, eraseOutcome]; exact congrArg _ agree
    have sameTicks : OutcomeAgree (.suspended .ticks s) (.suspended .ticks t) := by
      simp only [OutcomeAgree, eraseOutcome]; exact congrArg _ agree
    split <;> (try exact ⟨agree_runBounded_zero limits agree, rfl⟩)
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
  rw [← agree.stack]
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
  let bytes := field.1.utf8ByteSize+(toString field.1.utf8ByteSize).utf8ByteSize+1
  if bytes > prior.2.2.bytes || prior.2.2.nodes = 0 then throw (.budget,prior.2.1,prior.2.2)
  let entered : State := {prior.2.1 with control:=.enter field.2,stack:=[]}
  let (outcome,ticks) := forceHostedWith policy limits prior.2.2.bytes prior.2.2.ticks entered
  let nextBudget := {prior.2.2 with ticks:=ticks,bytes:=prior.2.2.bytes-bytes}
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
      let headerBytes := (toString fields.length).utf8ByteSize+2
      if headerBytes > remaining.bytes then throw (.budget,state,remaining)
      let remaining := {remaining with bytes:=remaining.bytes-headerBytes}
      if (fields.map Prod.fst).eraseDups.length != fields.length then throw (.duplicateField,state,remaining)
      if fields.length > remaining.nodes then throw (.budget,state,remaining)
      let pair ← fields.foldlM (recordStep policy limits depth) ([],state,remaining)
      pure ⟨.record pair.1.reverse,pair.2.1,pair.2.2⟩) := rfl

/-- The four admission checks a record passes before its fields are forced. -/
def RecordGate (budget : Budget) (fields : List (String × Nat)) : Prop :=
  ¬budget.nodes = 0 ∧ ¬(toString fields.length).utf8ByteSize + 2 > budget.bytes ∧
    ¬((fields.map Prod.fst).eraseDups.length != fields.length) = true ∧ ¬fields.length > budget.nodes - 1

def recordStart (budget : Budget) (fields : List (String × Nat)) : Budget :=
  {nodes := budget.nodes - 1, ticks := budget.ticks,
   bytes := budget.bytes - ((toString fields.length).utf8ByteSize+2)}

theorem materializeWith_record_gate {policy : State → Bool} {limits : Limits} {depth : Nat} {budget : Budget}
    {fields : List (String × Nat)} {state : State} (gate : RecordGate budget fields) :
    materializeWith policy limits (depth+1) budget (.record fields) state =
      (fields.foldlM (recordStep policy limits depth) ([],state,recordStart budget fields) >>= fun pair =>
        pure (⟨.record pair.1.reverse,pair.2.1,pair.2.2⟩ : Result)) := by
  obtain ⟨c1, c2, c3, c4⟩ := gate
  rw [materializeWith_record]
  simp only [c1, c2, c3, c4, ↓reduceIte, Bool.false_eq_true, recordStart]

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
    by_cases c2 : (toString fields.length).utf8ByteSize + 2 > budget.bytes
    · simp only [c1, c2, ↓reduceIte] at found; cases found
    by_cases c3 : ((fields.map Prod.fst).eraseDups.length != fields.length) = true
    · simp only [c1, c2, c3, ↓reduceIte] at found; cases found
    by_cases c4 : fields.length > budget.nodes - 1
    · simp only [c1, c2, c3, c4, ↓reduceIte] at found; cases found
    exact ⟨c1, c2, c3, c4⟩
  refine ⟨gate, ?_⟩
  rw [materializeWith_record_gate gate] at found
  obtain ⟨pair, folded, done⟩ := (except_bind_ok _ _ _).mp found
  exact ⟨pair, folded, ((except_pure_ok _ _).mp done).symm⟩

/-- **Materialization agrees.** -/
theorem agree_materializeWith {policy : State → Bool}
    (respects : ∀ s t, Agree s t → policy s = policy t) (limits : Limits) :
    ∀ (depth : Nat) (budget : Budget) (value : RuntimeValue) (s t : State) (r : Result),
      Agree s t → materializeWith policy limits depth budget value s = .ok r →
      ∃ r', materializeWith policy limits depth budget value t = .ok r' ∧ ResultAgree r r' := by
  intro depth
  induction depth with
  | zero => intro budget value s t r _ found; simp [materializeWith] at found
  | succ depth ih =>
    intro budget value s t r agree found
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
          · rw [← found]; simp [materializeWith, c1, c2]
          · rw [← found]; exact agree
    | boolean b =>
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
    | closure body environment => simp [materializeWith] at found; split at found <;> simp at found
    | specification metadata extension => simp [materializeWith] at found; split at found <;> simp at found
    | prototype spec target => simp [materializeWith] at found; split at found <;> simp at found
    | variant label payload =>
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
            obtain ⟨valueEq, retainedAgree⟩ := rel
            subst valueEq
            simp at found
            obtain ⟨a, materialized, rfl⟩ := found
            obtain ⟨a', materialized', aValue, aRemaining, aAgree⟩ := ih _ _ _ _ _ retainedAgree materialized
            refine ⟨⟨.variant label a'.value, a'.state, a'.remaining⟩, ?_, by simp [aValue], aRemaining, aAgree⟩
            simp [materializeWith, c1, c2, forcedT, ticksEq, materialized']
          | _ => rw [forced] at found; simp at found
    | record fields =>
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
            subst valueEq
            obtain ⟨a, materialized, done⟩ := (except_bind_ok _ _ _).mp stepped
            have := (except_pure_ok _ _).mp done
            subst this
            obtain ⟨a', materialized', aValue, aRemaining, aAgree⟩ := ih _ _ _ _ _ retainedAgree materialized
            refine ⟨((field.1, a'.value) :: acc, a'.state, a'.remaining), ?_, by simp [aValue],
              aRemaining, aAgree⟩
            simp only [forcedT, ticksEq, materialized']
            rfl
          | _ => rw [forced] at stepped; cases stepped

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
    have controlEq := agree.control
    have stackEq := agree.stack
    unfold completeWith at found ⊢
    simp only [allowed, allowedT, Bool.not_true, Bool.false_eq_true, if_false] at found ⊢
    rw [← controlEq, ← stackEq]
    split at found
    · rename_i value _ _
      simp only [except_bind_ok] at found
      obtain ⟨a, materialized, rest⟩ := found
      obtain ⟨a', materialized', aValue, aRemaining, aAgree⟩ :=
        agree_materializeWith respects limits _ _ _ _ _ _ agree materialized
      split at rest
      · rename_i bytes encodedAt
        split at rest
        · simp at rest
        · rename_i small
          simp at rest; subst rest
          refine ⟨a', ?_, aValue, aRemaining, aAgree⟩
          simp [materialized', aValue, encodedAt, small]
      · simp at rest
    · simp at found

/-- **Plan extraction agrees.** -/
theorem agree_yieldedPlanWith {policy : State → Bool}
    (respects : ∀ s t, Agree s t → policy s = policy t) (limits : Limits)
    (budget : Budget) {s t : State} {r : Result} (agree : Agree s t)
    (found : yieldedPlanWith policy limits budget s = .ok r) :
    ∃ r', yieldedPlanWith policy limits budget t = .ok r' ∧ ResultAgree r r' := by
  have controlEq := agree.control
  have stackEq := agree.stack
  unfold yieldedPlanWith at found ⊢
  rw [← controlEq, ← stackEq]
  split at found
  · rename_i plan yielded
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
          subst valueEq
          simp at found
          obtain ⟨a, materialized, rfl⟩ := found
          obtain ⟨a', materialized', aValue, aRemaining, aAgree⟩ :=
            agree_materializeWith respects limits _ _ _ _ _ _ retainedAgree materialized
          refine ⟨{a' with state := {a'.state with control := s.control, stack := s.stack}},
            ?_, aValue, aRemaining, Agree.mk' aAgree.heap rfl rfl⟩
          simp [materialized', yielded]
      | _ => simp at found
  · simp at found

/-! ## Settling agrees -/

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

/-! ## The turn's segment from a settled state -/

/-- **The turn's segment from a settled state** agrees with the segment from the state it
settled. `Turn.resumeActivity` resumes the decoded checkpoint and runs
`forceHostedWith` (inside `executeStateWith`) under limits counted past the
checkpoint's heap, which settling does not change (`settle_size`); then it extracts the
result (`completeWith`) or, at a yield, the Plan (`yieldedPlanWith`). For every
response, limits, byte allowance and tick budget:
* the hosted run ends in the same outcome (same value, Plan address, divergence,
  refusal, or tick/capacity suspension) with agreeing retained states and EXACTLY the
  same remaining ticks;
* a Plan that extracts from the original extracts from the settled run as the same
  Data with the same remaining budget;
* a result that extracts from the original extracts from the settled run as the same
  Data with the same remaining budget. -/
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
        ∃ y' r', (forceHostedWith (fun _ => true) limits bytes ticks resumed').1 = .finished value y' ∧
          complete limits budget y' = .ok r' ∧ ResultAgree r r') := by
  obtain ⟨resumed', again, agree⟩ := agree_resume (agree_settle state) response yielded
  have always : ∀ s t, Agree s t → (fun _ => true : State → Bool) s = (fun _ => true : State → Bool) t :=
    fun _ _ _ => rfl
  have ⟨ran, sameTicks⟩ := agree_forceHostedWith always limits bytes ticks agree
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
    obtain ⟨same, yAgree⟩ := ran
    subst same
    obtain ⟨r', completed', resultAgree⟩ := agree_completeWith always limits budget yAgree completed
    exact ⟨_, r', rfl, completed', resultAgree⟩

#assert_axioms settle_resume_segment agree_forceHostedFrom erase_stepRaw

end Minidregg.Theory.ObjectiveBendDemandCollect
