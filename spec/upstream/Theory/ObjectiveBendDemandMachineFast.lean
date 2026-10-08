/- Compiled implementation of the Core4 demand machine for unique (linear) use.

`stepRaw`/`step`/`runBounded` (Theory/ObjectiveBendDemandMachine) stay the
specification; every theorem is about them. This module gives them faster
implementations and proves each equal to its specification, installed with
`@[csimp]`, so compiled code (admission re-execution, the preview) runs the
implementation while the statements are untouched.

What made the specification slow when compiled (lane FASTMACHINE DIAGNOSIS.md):
* `step` keeps the pre-transition State alive for its capacity branch, so the heap
  `Array` is shared inside `stepRaw` and every `set!`/`push` copies the whole heap;
* `step` recomputes `List.length` of the stack every tick;
* three `stepRaw` cases (argument binding, successor binding, case arm) and
  `allocateFields` read the OLD heap's size after the push, so even a uniquely
  held heap is copied at those pushes;
* `forceWith` re-enters `runBounded` one tick at a time.

The implementation: the capacity check is decided BEFORE the transition from the
pre-state (`sizesAfter`, proved equal to the sizes of `stepRaw`'s result), so no
pre-state is retained on the success path; the stack depth is carried as a
counter; the four push sites read the size before pushing. -/
import Theory.ObjectiveBendDemandMachine
namespace Minidregg.Theory.ObjectiveBendDemandMachineFast
open ObjectiveBendOpenRecursion ObjectiveBendDemandMachine
set_option autoImplicit false

/-! ## Allocation and the transition -/

/-- `allocateFields` with each field's address read before its push. -/
def allocateFieldsFast (heap : Array Cell) (environment : Environment)
    (fields : List (String × Term)) : Array Cell × List (String × Address) :=
  let pair := fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
    let address := prior.1.size
    (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,address)::prior.2)) (heap,[])
  (pair.1,pair.2.reverse)

theorem allocateFieldsFast_eq : @allocateFieldsFast = @allocateFields := rfl

/-- `stepRaw`, with the four push sites that read the old heap's size after
pushing (argument, successor and case-arm bindings; record allocation) reading
it first. Every other case is `stepRaw`'s own compiled code. -/
def stepRawFast (state : State) : State :=
  match state with
  | ⟨heap,.returned (.closure body captured),.argument argument environment::rest⟩ =>
    let address := heap.size
    ⟨heap.push (.suspended ⟨argument,environment⟩),.evaluate body (address::captured),rest⟩
  | ⟨heap,.returned (.natural (n+1)),.condition _ successorBody environment::rest⟩ =>
    let address := heap.size
    ⟨heap.push (.cached ⟨.nat n,[]⟩ (.natural n)),.evaluate successorBody (address::environment),rest⟩
  | ⟨heap,.returned (.variant tag payload),.case arms environment::rest⟩ =>
    match arms.find? (fun arm => arm.1 == tag) with
    | some (_,body) =>
      let address := heap.size
      ⟨heap.push (.suspended ⟨.bound 0,[payload]⟩),.evaluate body (address::environment),rest⟩
    | none => ⟨heap,.refused .missingArm,rest⟩
  | ⟨heap,.evaluate (.record fields) environment,stack⟩ =>
    let allocated := allocateFieldsFast heap environment fields
    ⟨allocated.1,.returned (.record allocated.2),stack⟩
  | ⟨heap,.returned (.record inherited),.extend fields environment::rest⟩ =>
    let allocated := allocateFieldsFast heap environment fields
    let retained := inherited.filter (fun prior => !(fields.any fun field => field.1 == prior.1))
    ⟨allocated.1,.returned (.record (allocated.2++retained)),rest⟩
  | state => stepRaw state

theorem stepRawFast_eq_stepRaw (state : State) : stepRawFast state = stepRaw state := by
  unfold stepRawFast
  split
  · simp [stepRaw]
  · simp [stepRaw]
  · rename_i heap tag payload arms environment rest
    simp only [stepRaw]
    split <;> rename_i h <;> simp [h]
  · simp [stepRaw, allocateFieldsFast_eq]
  · simp [stepRaw, allocateFieldsFast_eq]
  · rfl

@[csimp] theorem stepRaw_eq_fast : @stepRaw = @stepRawFast :=
  funext fun state => (stepRawFast_eq_stepRaw state).symm

/-! ## Sizes after a transition, read off the pre-state -/

theorem allocateFields_size (heap : Array Cell) (environment : Environment)
    (fields : List (String × Term)) :
    (allocateFields heap environment fields).1.size = heap.size + fields.length := by
  unfold allocateFields
  suffices general : ∀ (fields : List (String × Term)) (init : Array Cell × List (String × Address)),
      (fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
        (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,prior.1.size)::prior.2)) init).1.size =
        init.1.size + fields.length by
    simpa using general fields (heap,[])
  intro fields
  induction fields with
  | nil => intro init; simp
  | cons field rest ih => intro init; simp [List.foldl, ih]; omega

/-- The heap size and stack length `stepRaw` produces, computed without building
its result; `depth` stands for the pre-state's stack length. -/
def sizesAfter (state : State) (depth : Nat) : Nat × Nat :=
  let size := state.heap.size
  match state.control with
  | .complete _ | .refused _ | .blackhole _ | .yielded _ => (size,depth)
  | .enter address => match state.heap[address]? with
    | some (.suspended _) => (size,depth+1)
    | _ => (size,depth)
  | .evaluate term _ => match term with
    | .fix _ _ | .inject _ _ => (size+1,depth)
    | .specification _ _ | .prototype _ _ => (size+2,depth)
    | .record fields => (size+fields.length,depth)
    | .app _ _ | .reflect _ | .metadata _ | .project _ | .get _ _ | .extend _ _
    | .ifZero _ _ _ | .binary _ _ _ | .case _ _ | .ifBool _ _ _ => (size,depth+1)
    | .perform _ => if forcingShared state.stack then (size,depth) else (size+1,depth)
    | .bound _ | .lam _ | .nat _ | .boolean _ | .label _ | .mix _ _ | .done _ => (size,depth)
  | .returned value => match state.stack with
    | [] => (size,depth)
    | frame::_ => match frame,value with
      | .argument _ _,.specification _ _ => (size,depth)
      | .argument _ _,.closure _ _ => (size+1,depth-1)
      | .extend fields _,.record _ => (size+fields.length,depth-1)
      | .condition _ _ _,.natural (_+1) => (size+1,depth-1)
      | .case arms _,.variant tag _ => match arms.find? (fun arm => arm.1 == tag) with
        | some _ => (size+1,depth-1)
        | none => (size,depth-1)
      | .binaryLeft _ _ _,_ => (size,depth)
      | _,_ => (size,depth-1)

theorem sizesAfter_eq (state : State) :
    sizesAfter state state.stack.length = ((stepRaw state).heap.size,(stepRaw state).stack.length) := by
  rcases state with ⟨heap,control,stack⟩
  cases control with
  | complete | refused | blackhole | yielded => simp [sizesAfter, stepRaw]
  | enter address =>
    simp only [sizesAfter, stepRaw]
    cases h : heap[address]? with
    | none => simp
    | some cell => cases cell <;> simp
  | evaluate term environment =>
    cases term <;> simp [sizesAfter, stepRaw, allocateFields_size]
    · rename_i index; cases environment[index]? <;> simp
    · split <;> simp
  | returned value =>
    cases stack with
    | nil => simp [sizesAfter, stepRaw]
    | cons frame rest =>
      cases frame
      case condition =>
        cases value with
        | natural n => cases n <;> simp [sizesAfter, stepRaw]
        | _ => simp [sizesAfter, stepRaw]
      all_goals cases value <;> simp [sizesAfter, stepRaw, allocateFields_size]
      all_goals (repeat' split) <;> simp_all

/-! ## One step and the bounded run -/

/-- `step`, deciding capacity from the pre-state: on the success path the
pre-state is consumed by the transition instead of being kept alive. -/
def stepFast (limits : Limits) (state : State) : Outcome :=
  match state.control with
  | .complete value => .finished value state
  | .blackhole address => .divergent address state
  | .refused reason => .refused reason state
  | .yielded plan => .yielded plan state
  | _ =>
    let sizes := sizesAfter state state.stack.length
    if sizes.1 ≤ limits.heap && sizes.2 ≤ limits.stack then .suspended .ticks (stepRawFast state)
    else .suspended .capacity state

theorem stepFast_eq_step (limits : Limits) (state : State) :
    stepFast limits state = step limits state := by
  cases h : state.control <;> simp [stepFast, step, h, sizesAfter_eq, stepRawFast_eq_stepRaw]

@[csimp] theorem step_eq_fast : @step = @stepFast :=
  funext fun limits => funext fun state => (stepFast_eq_step limits state).symm

/-- `runBounded` with the stack depth carried as a counter (`depth` stands for
`state.stack.length`) and capacity decided before each transition. -/
def runFrom (limits : Limits) : Nat → State → Nat → Outcome
  | 0, state, _ => match state.control with
    | .complete value => .finished value state
    | .blackhole address => .divergent address state
    | .refused reason => .refused reason state
    | .yielded plan => .yielded plan state
    | _ => .suspended .ticks state
  | ticks+1, state, depth => match state.control with
    | .complete value => .finished value state
    | .blackhole address => .divergent address state
    | .refused reason => .refused reason state
    | .yielded plan => .yielded plan state
    | _ =>
      let sizes := sizesAfter state depth
      if sizes.1 ≤ limits.heap && sizes.2 ≤ limits.stack then
        runFrom limits ticks (stepRawFast state) sizes.2
      else .suspended .capacity state

def runBoundedFast (limits : Limits) (ticks : Nat) (state : State) : Outcome :=
  runFrom limits ticks state state.stack.length

theorem runFrom_eq_runBounded (limits : Limits) :
    ∀ (ticks : Nat) (state : State),
      runFrom limits ticks state state.stack.length = runBounded limits ticks state
  | 0, state => by cases h : state.control <;> simp [runFrom, runBounded, h]
  | ticks+1, state => by
    have next := runFrom_eq_runBounded limits ticks (stepRaw state)
    cases h : state.control <;> simp only [runFrom, runBounded, step, h, sizesAfter_eq,
      stepRawFast_eq_stepRaw]
    all_goals split <;> simp_all

@[csimp] theorem runBounded_eq_fast : @runBounded = @runBoundedFast :=
  funext fun limits => funext fun ticks => funext fun state =>
    (runFrom_eq_runBounded limits ticks state).symm

/-! ## One-tick forcing under a policy (`ObjectiveBendDemandData.forceWith`) -/

/-- `forceWith` with the depth carried: one transition per allowance instead of
re-entering `runBounded` for one tick. -/
def forceFrom (policy : State → Bool) (limits : Limits) : Nat → State → Nat → Outcome × Nat
  | 0, state, _ => (runBounded limits 0 state,0)
  | ticks+1, state, depth => match state.control with
    | .complete _ | .refused _ | .blackhole _ | .yielded _ => (runBounded limits 0 state,ticks+1)
    | _ => if !policy state then (.suspended .capacity state,ticks+1) else
      let sizes := sizesAfter state depth
      if sizes.1 ≤ limits.heap && sizes.2 ≤ limits.stack then
        forceFrom policy limits ticks (stepRawFast state) sizes.2
      else (.suspended .capacity state,ticks)

def forceWithFast (policy : State → Bool) (limits : Limits) (ticks : Nat) (state : State) :
    Outcome × Nat :=
  forceFrom policy limits ticks state state.stack.length

/-- The controls at which the machine has stopped (no transition is taken). -/
def stopped : Control → Bool
  | .complete _ | .refused _ | .blackhole _ | .yielded _ => true
  | _ => false

theorem step_of_moving (limits : Limits) (state : State) (moving : stopped state.control = false) :
    step limits state =
      if (stepRaw state).heap.size ≤ limits.heap && (stepRaw state).stack.length ≤ limits.stack then
        .suspended .ticks (stepRaw state)
      else .suspended .capacity state := by
  unfold step
  split <;> simp_all [stopped]

theorem runBounded_zero_of_moving (limits : Limits) (state : State)
    (moving : stopped state.control = false) :
    runBounded limits 0 state = .suspended .ticks state := by
  unfold runBounded
  split <;> simp_all [stopped]

theorem runBounded_zero_of_stopped (limits : Limits) (state : State)
    (halted : stopped state.control = true) (next : State) :
    runBounded limits 0 state ≠ .suspended .ticks next := by
  unfold runBounded
  split <;> simp_all [stopped]

/-- Any function with `forceWith`'s two defining equations is `forceWithFast`.
`ObjectiveBendDemandData` instantiates it with `forceWith` itself for its
`@[csimp]` lemma (this module cannot import that one: it imports this). -/
theorem forceWithFast_unique (F : (State → Bool) → Limits → Nat → State → Outcome × Nat)
    (zero : ∀ policy limits state, F policy limits 0 state = (runBounded limits 0 state,0))
    (succ : ∀ policy limits ticks state, F policy limits (ticks+1) state =
      match state.control with
      | .complete _ | .refused _ | .blackhole _ | .yielded _ => (runBounded limits 0 state,ticks+1)
      | _ => if !policy state then (.suspended .capacity state,ticks+1) else
        match runBounded limits 1 state with
        | .suspended .ticks next => F policy limits ticks next
        | other => (other,ticks)) :
    F = forceWithFast := by
  funext policy limits ticks state
  -- a stopped state keeps its whole allowance
  have halt : ∀ ticks (state : State), stopped state.control = true →
      F policy limits ticks state = (runBounded limits 0 state,ticks) := by
    intro ticks state halted
    cases ticks with
    | zero => exact zero policy limits state
    | succ ticks =>
      rw [succ]
      cases h : state.control <;> simp_all [stopped]
  induction ticks generalizing state with
  | zero => simp [zero, forceWithFast, forceFrom]
  | succ ticks ih =>
    rw [succ]
    unfold forceWithFast
    cases h : state.control <;> simp only [forceFrom, h]
    all_goals try rfl
    all_goals
      have moving : stopped state.control = false := by simp [h, stopped]
      have one : runBounded limits 1 state =
          match step limits state with
          | .suspended .ticks next => runBounded limits 0 next
          | other => other := rfl
      rw [one, step_of_moving limits state moving, sizesAfter_eq, stepRawFast_eq_stepRaw]
      by_cases allowed : policy state = true <;> simp only [allowed, Bool.not_true, Bool.not_false]
      · by_cases fitsHeap : (stepRaw state).heap.size ≤ limits.heap <;>
        by_cases fitsStack : (stepRaw state).stack.length ≤ limits.stack <;>
        simp only [fitsHeap, fitsStack, decide_true, decide_false, Bool.and_true, Bool.and_false,
          Bool.false_eq_true, ↓reduceIte]
        rw [← forceWithFast, ← ih]
        cases moved : stopped (stepRaw state).control
        · rw [runBounded_zero_of_moving limits _ moved]
        · rw [halt ticks _ moved]
          split
          · rename_i next equation
            exact absurd equation (runBounded_zero_of_stopped limits _ moved next)
          · rfl
      · simp_all

/-! ## Axiom pins: exact sets (no Classical.choice, no compiler trust, no sorry) -/

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.allocateFieldsFast_eq' does not depend on any axioms
-/
#guard_msgs in
#print axioms allocateFieldsFast_eq

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.stepRawFast_eq_stepRaw' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms stepRawFast_eq_stepRaw

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.stepRaw_eq_fast' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms stepRaw_eq_fast

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.allocateFields_size' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms allocateFields_size

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.sizesAfter_eq' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms sizesAfter_eq

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.stepFast_eq_step' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms stepFast_eq_step

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.step_eq_fast' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms step_eq_fast

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.runFrom_eq_runBounded' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms runFrom_eq_runBounded

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.runBounded_eq_fast' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms runBounded_eq_fast

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.step_of_moving' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms step_of_moving

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.runBounded_zero_of_moving' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms runBounded_zero_of_moving

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.runBounded_zero_of_stopped' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms runBounded_zero_of_stopped

/--
info: 'Minidregg.Theory.ObjectiveBendDemandMachineFast.forceWithFast_unique' depends on axioms: [propext, Quot.sound]
-/
#guard_msgs in
#print axioms forceWithFast_unique

end Minidregg.Theory.ObjectiveBendDemandMachineFast
