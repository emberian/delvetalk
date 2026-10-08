/- Executable demand/sharing candidate for the NEW Objective Bend runtime core.
It consumes actual elaborated Objective terms, not a linked method dictionary.
Thunk identity is stable through evaluating→cached update; Fix uses one tied
heap address. Values are effect-free. The one effect is a yield: `perform`
outside every shared-thunk update suspends the WHOLE program as `yielded`, with
its plan as one lazy cell; only `resume` continues it, with the same heap and
stack. A perform reached while a shared cell is being forced is refused, never
run once-for-all or once-per-demand. Native authority and affine continuations
are not constructors and cannot be minted/copied by this machine.
Weak-head reference adequacy, graph/capture ownership and new type metatheory
remain obligations. -/
import Theory.ObjectiveBendOpenRecursion
import Theory.AxiomPin
namespace Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendOpenRecursion
set_option autoImplicit false

abbrev Address := Nat
abbrev Environment := List Address
inductive RuntimeValue where
  | closure (body : Term) (environment : Environment)
  | natural (value : Nat)
  | boolean (value : Bool)
  | label (value : String)
  | record (fields : List (String × Address))
  | specification (metadata extension : Address)
  | prototype (specification target : Address)
  /-- An injected label with the address of its (lazy) payload cell. -/
  | variant (label : String) (payload : Address)
  deriving Repr
structure Closure where
  term : Term
  environment : Environment
  deriving Repr
inductive Cell where
  | suspended (origin : Closure)
  | evaluating (origin : Closure)
  | cached (origin : Closure) (value : RuntimeValue)
  deriving Repr
inductive Frame where
  | argument (term : Term) (environment : Environment)
  | update (address : Address)
  | field (name : String)
  | reflect | metadata | project
  | extend (fields : List (String × Term)) (environment : Environment)
  | condition (zero successorBody : Term) (environment : Environment)
  | binaryLeft (primitive : Primitive) (right : Term) (environment : Environment)
  | binaryRight (primitive : Primitive) (left : RuntimeValue)
  | case (arms : List (String × Term)) (environment : Environment)
  | ifBool (whenTrue whenFalse : Term) (environment : Environment)
  deriving Repr
inductive Refusal where
  | unbound | missingCell | missingField | wrongValue | invalidUpdate | capacity | missingArm
  /-- A perform reached while forcing a shared cell (an `update` frame is on the
  stack): its effect would be cached and shared, so it is refused. Typed programs
  never reach it (computation types are never cell types). -/
  | sharedEffect
  deriving Repr
inductive Control where
  | evaluate (term : Term) (environment : Environment)
  | enter (address : Address)
  | blackhole (address : Address)
  | returned (value : RuntimeValue)
  | complete (value : RuntimeValue)
  | refused (reason : Refusal)
  /-- The program yielded the plan stored at this address; it waits for `resume`. -/
  | yielded (plan : Address)
  deriving Repr
structure State where
  heap : Array Cell
  control : Control
  stack : List Frame
  deriving Repr
structure Limits where
  heap : Nat
  stack : Nat
  deriving Repr

def initial (term : Term) : State := ⟨#[],.evaluate term [],[]⟩
def allocateFields (heap : Array Cell) (environment : Environment)
    (fields : List (String × Term)) : Array Cell × List (String × Address) :=
  let pair := fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
    (prior.1.push (.suspended ⟨field.2,environment⟩),(field.1,prior.1.size)::prior.2)) (heap,[])
  (pair.1,pair.2.reverse)
def valueTerm : RuntimeValue → Option Term
  | .natural n => some (.nat n) | .boolean value => some (.boolean value)
  | .label name => some (.label name) | _ => none
def scalarValue : Term → Option RuntimeValue
  | .nat n => some (.natural n) | .boolean value => some (.boolean value)
  | .label name => some (.label name) | _ => none

/-- A shared cell is being forced exactly when an update frame is on the stack. -/
def forcingShared (stack : List Frame) : Bool :=
  stack.any fun frame => match frame with | .update _ => true | _ => false

def stepRaw (state : State) : State :=
  match state.control with
  | .complete _ | .refused _ | .blackhole _ | .yielded _ => state
  | .enter address => match state.heap[address]? with
    | none => {state with control:=.refused .missingCell}
    | some (.evaluating _) => {state with control:=.blackhole address}
    | some (.cached _ value) => {state with control:=.returned value}
    | some (.suspended origin) =>
      {state with heap:=state.heap.set! address (.evaluating origin), control:=.evaluate origin.term origin.environment,stack:=.update address::state.stack}
  | .evaluate term environment => match term with
    | .bound index => match environment[index]? with
      | some address => {state with control:=.enter address}
      | none => {state with control:=.refused .unbound}
    | .lam body => {state with control:=.returned (.closure body environment)}
    | .nat n => {state with control:=.returned (.natural n)}
    | .boolean value => {state with control:=.returned (.boolean value)}
    | .label name => {state with control:=.returned (.label name)}
    | .app function argument => {state with control:=.evaluate function environment, stack:=.argument argument environment::state.stack}
    | .mix lower upper => {state with control:=.evaluate (mixBody lower upper) environment}
    | .fix spec inherited =>
      let address := state.heap.size
      let body := Term.app (Term.app (spec.rename Nat.succ) (.bound 0)) (inherited.rename Nat.succ)
      {state with heap:=state.heap.push (.suspended ⟨body,address::environment⟩),control:=.enter address}
    | .specification descriptor extension =>
      let address := state.heap.size
      {state with heap:= (state.heap.push (.suspended ⟨descriptor,environment⟩)).push (.suspended ⟨extension,environment⟩), control:=.returned (.specification address (address+1))}
    | .prototype spec target =>
      let address := state.heap.size
      {state with heap:= (state.heap.push (.suspended ⟨spec,environment⟩)).push (.suspended ⟨target,environment⟩), control:=.returned (.prototype address (address+1))}
    | .reflect term => {state with control:=.evaluate term environment,stack:=.reflect::state.stack}
    | .metadata term => {state with control:=.evaluate term environment,stack:=.metadata::state.stack}
    | .project term => {state with control:=.evaluate term environment,stack:=.project::state.stack}
    | .record fields =>
      let allocated := allocateFields state.heap environment fields
      {state with heap:=allocated.1,control:=.returned (.record allocated.2)}
    | .get target name => {state with control:=.evaluate target environment,stack:=.field name::state.stack}
    | .extend inherited fields => {state with control:=.evaluate inherited environment, stack:=.extend fields environment::state.stack}
    | .ifZero value zero successorBody => {state with control:=.evaluate value environment, stack:=.condition zero successorBody environment::state.stack}
    | .binary primitive left right => {state with control:=.evaluate left environment, stack:=.binaryLeft primitive right environment::state.stack}
    | .inject tag payload =>
      let address := state.heap.size
      {state with heap:=state.heap.push (.suspended ⟨payload,environment⟩),control:=.returned (.variant tag address)}
    | .case scrutinee arms => {state with control:=.evaluate scrutinee environment, stack:=.case arms environment::state.stack}
    | .ifBool condition whenTrue whenFalse => {state with control:=.evaluate condition environment, stack:=.ifBool whenTrue whenFalse environment::state.stack}
    | .done value => {state with control:=.evaluate value environment}
    | .perform plan =>
      if forcingShared state.stack then {state with control:=.refused .sharedEffect} else
      let address := state.heap.size
      {state with heap:=state.heap.push (.suspended ⟨plan,environment⟩),control:=.yielded address}
  | .returned value => match state.stack with
    | [] => {state with control:=.complete value}
    | frame::rest => match frame with
      | .update address => match state.heap[address]? with
        | some (.evaluating origin) =>
          {state with heap:=state.heap.set! address (.cached origin value),stack:=rest}
        | _ => {state with control:=.refused .invalidUpdate,stack:=rest}
      | .reflect => match value with
        | .prototype spec _ => {state with control:=.enter spec,stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .metadata => match value with
        | .specification descriptor _ => {state with control:=.enter descriptor,stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .project => match value with
        | .prototype _ target => {state with control:=.enter target,stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .argument argument environment => match value with
        | .specification _ extension => {state with control:=.enter extension}

        | .closure body captured => {state with heap:=state.heap.push (.suspended ⟨argument,environment⟩), control:=.evaluate body (state.heap.size::captured),stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .field name => match value with
        | .record fields => match fields.find? (fun field => field.1 == name) with
          | some (_,address) => {state with control:=.enter address,stack:=rest}
          | none => {state with control:=.refused .missingField,stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .extend fields environment => match value with
        | .record inherited =>
          let allocated := allocateFields state.heap environment fields
          let retained := inherited.filter (fun prior => !(fields.any fun field => field.1 == prior.1))
          {state with heap:=allocated.1,control:=.returned (.record (allocated.2++retained)),stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .condition zero successorBody environment => match value with
        | .natural 0 => {state with control:=.evaluate zero environment,stack:=rest}
        | .natural (n+1) => {state with heap:=state.heap.push (.cached ⟨.nat n,[]⟩ (.natural n)), control:=.evaluate successorBody (state.heap.size::environment),stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .binaryLeft primitive right environment =>
        {state with control:=.evaluate right environment,stack:=.binaryRight primitive value::rest}
      | .binaryRight primitive left =>
        match (valueTerm left).bind (fun l => (valueTerm value).bind (primitiveResult primitive l)) with
        | some result => match scalarValue result with
          | some next => {state with control:=.returned next,stack:=rest}
          | none => {state with control:=.refused .wrongValue,stack:=rest}
        | none => {state with control:=.refused .wrongValue,stack:=rest}
      | .case arms environment => match value with
        | .variant tag payload => match arms.find? (fun arm => arm.1 == tag) with
          | some (_,body) =>
            {state with heap:=state.heap.push (.suspended ⟨.bound 0,[payload]⟩), control:=.evaluate body (state.heap.size::environment),stack:=rest}
          | none => {state with control:=.refused .missingArm,stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .ifBool whenTrue whenFalse environment => match value with
        | .boolean true => {state with control:=.evaluate whenTrue environment,stack:=rest}
        | .boolean false => {state with control:=.evaluate whenFalse environment,stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}

/-- A blackhole is a non-result divergence observation, not a catchable language
exception. Tick exhaustion and allocation capacity suspend with the EXACT
pre-transition state, so raising bounds never loses control/environment/stack. -/
inductive Suspension where
  | ticks | capacity
  deriving Repr
inductive Outcome where
  | finished (value : RuntimeValue) (state : State)
  | suspended (reason : Suspension) (state : State)
  | divergent (address : Address) (state : State)
  | refused (reason : Refusal) (state : State)
  /-- The exact yielded state; the plan cell's address is reported. -/
  | yielded (plan : Address) (state : State)
  deriving Repr

def step (limits : Limits) (state : State) : Outcome :=
  match state.control with
  | .complete value => .finished value state
  | .blackhole address => .divergent address state
  | .refused reason => .refused reason state
  | .yielded plan => .yielded plan state
  | _ =>
    let next := stepRaw state
    if next.heap.size ≤ limits.heap && next.stack.length ≤ limits.stack then
      .suspended .ticks next
    else .suspended .capacity state

def runBounded (limits : Limits) : Nat → State → Outcome
  | 0,state => match state.control with
    | .complete value => .finished value state
    | .blackhole address => .divergent address state
    | .refused reason => .refused reason state
    | .yielded plan => .yielded plan state
    | _ => .suspended .ticks state
  | ticks+1,state => match step limits state with
    | .suspended .ticks next => runBounded limits ticks next
    | other => other

/-- Compatibility projection for inspecting retained state; Outcome must be
used when distinguishing completion, suspension and divergence matters. -/
def run (limits : Limits) (ticks : Nat) (state : State) : State :=
  match runBounded limits ticks state with
  | .finished _ retained | .suspended _ retained | .divergent _ retained | .refused _ retained
  | .yielded _ retained => retained

/-- Resume a yielded program with the kernel's response, a closed term (decoded
data). Heap and stack are unchanged: the yielded state IS the checkpoint.
Any other state cannot be resumed. -/
def resume (response : Term) (state : State) : Option State :=
  match state.control with
  | .yielded _ => some {state with control:=.evaluate response []}
  | _ => none

theorem resume_requires_yield (response : Term) (state : State)
    (resumed : (resume response state).isSome = true) : ∃ plan, state.control = .yielded plan := by
  unfold resume at resumed
  split at resumed
  · rename_i plan h; exact ⟨plan,h⟩
  · simp at resumed

theorem resume_keeps_heap_and_stack (response : Term) (state next : State)
    (resumed : resume response state = some next) :
    next.heap = state.heap ∧ next.stack = state.stack ∧ next.control = .evaluate response [] := by
  unfold resume at resumed
  split at resumed
  · cases resumed; exact ⟨rfl,rfl,rfl⟩
  · simp at resumed

/-- The shared-thunk rule, exactly: a perform under an update frame is refused. -/
theorem perform_under_update_refused (heap : Array Cell) (plan : Term) (environment : Environment)
    (address : Address) (rest : List Frame) :
    (stepRaw ⟨heap,.evaluate (.perform plan) environment,.update address :: rest⟩).control =
      .refused .sharedEffect := by
  simp [stepRaw, forcingShared]

/-- Outside every shared cell a perform yields, allocating its plan lazily. -/
theorem perform_yields (heap : Array Cell) (plan : Term) (environment : Environment)
    (stack : List Frame) (direct : forcingShared stack = false) :
    stepRaw ⟨heap,.evaluate (.perform plan) environment,stack⟩ =
      ⟨heap.push (.suspended ⟨plan,environment⟩),.yielded heap.size,stack⟩ := by
  simp [stepRaw, direct]

#assert_axioms perform_yields perform_under_update_refused resume_requires_yield

end Minidregg.Theory.ObjectiveBendDemandMachine
