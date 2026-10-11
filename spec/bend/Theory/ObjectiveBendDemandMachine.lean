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
import Theory.ObjectiveBendFiniteData
import Theory.AxiomPin
namespace Delvetalk.Theory.ObjectiveBendDemandMachine
open Delvetalk.Theory.ObjectiveBendOpenRecursion
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
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
/-- A part of an object's state the host holds (KERNEL-HANDOFF §15). It names no address:
forcing it allocates only its immediate children, as native data or further stored parts, and
only a `row` is fetched from the host (by the hosted runner, `forceHostedFrom`). Positions are
a relation's canonical (key) order at the turn's read height; `size` is its row count there.
The shapes are the kernel's: `Relation<T> = rows {items: List<T>}` and `nil`/`cons {head, tail}`. -/
inductive Stored where
  /-- The object's state record: a field named in `stored` is a stored relation of that many
  rows, any other the native data `state` holds for it. -/
  | object (state : List (String × Data)) (stored : List (String × Nat))
  /-- A relation field's value, `rows {items}`. -/
  | relation (field : String) (size : Nat)
  /-- The payload `{items}` of a relation. -/
  | items (field : String) (size : Nat)
  /-- The rows from `position` on: `nil` at `size`, else `cons`. -/
  | spine (field : String) (position size : Nat)
  /-- The payload `{head, tail}` of the spine cell at `position`. -/
  | cons (field : String) (position size : Nat)
  /-- The row at `position`, fetched from the host. -/
  | row (field : String) (position : Nat)
  /-- The row at `position` projected onto the columns `key` (`relationLookup`'s probe), fetched
  from the host, which answers only when `key` is the relation's declared key. -/
  | key (field : String) (position : Nat) (key : List String)
  /-- What a lookup found at `position`: the payload `{value}` of its `some`, the row unforced. -/
  | found (field : String) (position : Nat)
  /-- What a lookup found absent: the payload `{}` of its `none`; the sought key lies below
  the row at `position` (at `size`: past every row). -/
  | absent (field : String) (position : Nat)
  /-- A relation's row count (`relationCount`), read from its handle. -/
  | size (field : String) (size : Nat)
  deriving Repr
inductive Cell where
  | suspended (origin : Closure)
  | evaluating (origin : Closure)
  | cached (origin : Closure) (value : RuntimeValue)
  /-- Admitted finite data is already pure. Forcing allocates only its immediate
  children and caches WHNF in one real transition, without a source update. -/
  | native (origin : Data)
  | nativeCached (origin : Data) (value : RuntimeValue)
  /-- A stored part of the turn's state (`Stored`): `none` unforced, `some` its WHNF once
  forced, kept with its provenance so a turn's reads are read off its heap. -/
  | stored (part : Stored) (value : Option RuntimeValue)
  deriving Repr
/-- What a relation walk (`relationCount`, `relationLookup`) is doing. -/
inductive Walk where
  /-- Counting: the cons cells passed so far. -/
  | count (counted : Nat)
  /-- Looking up by the columns `key`; `probe` is the probe's cell. -/
  | lookup (key : List String) (probe : Address)
  deriving Repr
inductive Frame where
  | argument (term : Term) (environment : Environment)
  | nativeArgument (value : Data)
  | update (address : Address)
  | field (name : String)
  | reflect | metadata | project
  | extend (fields : List (String × Term)) (environment : Environment)
  | condition (zero successorBody : Term) (environment : Environment)
  | unary (primitive : UnaryPrimitive)
  | binaryLeft (primitive : Primitive) (right : Term) (environment : Environment)
  | binaryRight (primitive : Primitive) (left : RuntimeValue)
  | case (arms : List (String × Term)) (environment : Environment)
  | ifBool (whenTrue whenFalse : Term) (environment : Environment)
  /-- `textJoin`: the separator is being evaluated; the list comes next. -/
  | joinSeparator (list : Term) (environment : Environment)
  /-- `textJoin`: the list cell (nil or cons) is being forced. `first` holds
  until the first head is appended. -/
  | joinList (separator accumulated : String) (first : Bool)
  /-- `textJoin`: a cons payload (the record of head and tail) is being forced. -/
  | joinCons (separator accumulated : String) (first : Bool)
  /-- `textJoin`: a head is being forced; the tail cell is next. -/
  | joinHead (separator accumulated : String) (first : Bool) (tail : Address)
  /-- A relation is being forced to `rows payload`; a stored one answers from its handle. -/
  | relationRows (walk : Walk)
  /-- A relation's list cell (nil or cons) is being forced. -/
  | relationList (walk : Walk)
  /-- A walked row's projection is being probed; `payload` is its cons payload. -/
  | relationProbe (key : List String) (probe payload : Address)
  /-- The stored key at the middle of positions `low` to `high` is being probed. -/
  | relationSearch (key : List String) (probe : Address) (field : String) (low high : Nat)
  /-- `refuse`: its reason is being evaluated; the label it returns is the refusal. -/
  | refuse
  deriving Repr
inductive Refusal where
  | unbound | missingCell | missingField | wrongValue | invalidUpdate | capacity | missingArm
  /-- A perform reached while forcing a shared cell (an `update` frame is on the
  stack): its effect would be cached and shared, so it is refused. Typed programs
  never reach it (computation types are never cell types). -/
  | sharedEffect
  /-- The program refused its turn by name (`Term.refuse`), with the text its reason evaluated to. -/
  | program (reason : String)
  /-- A stored row was entered with no host store to fetch it from (`stepRaw` alone, or the
  store has no such row). -/
  | unfetched
  deriving Repr
inductive Control where
  | evaluate (term : Term) (environment : Environment)
  /-- Nonempty reversed arguments preserve nested application order without
  constructing applications/literals in the executable source term. -/
  | nativeApplication (function : Term) (argument : Data) (remaining : List Data)
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
/-- No input cell is allocated before its function actually binds that argument.
This preserves laziness for unused large inputs and specification wrappers. -/
def initialDataArguments (term : Term) (arguments : List Data) : State :=
  match arguments.reverse with
  | [] => initial term
  | argument :: remaining => ⟨#[], .nativeApplication term argument remaining, []⟩

/-- Allocate only one record layer. Child cells retain finite Data, never terms. -/
def allocateNativeFields (heap : Array Cell) (fields : List (String × Data)) :
    Array Cell × List (String × Address) :=
  let pair := fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
    let address := prior.1.size
    (prior.1.push (.native field.2), (field.1, address) :: prior.2)) (heap, [])
  (pair.1, pair.2.reverse)

def forceNative (heap : Array Cell) (value : Data) : Array Cell × RuntimeValue :=
  match value with
  | .natural n => (heap, .natural n)
  | .boolean b => (heap, .boolean b)
  | .label s => (heap, .label s)
  | .record fields =>
    let (heap, fields) := allocateNativeFields heap fields
    (heap, .record fields)
  | .variant label payload =>
    let address := heap.size
    (heap.push (.native payload), .variant label address)

/-- The object's state record: a field named in `stored` becomes a stored relation of that
size, any other native data. Each address is read before its push. -/
def objectCell (stored : List (String × Nat)) (field : String × Data) : Cell :=
  match stored.lookup field.1 with
  | some size => .stored (.relation field.1 size) none
  | none => .native field.2

def allocateObjectFields (heap : Array Cell) (stored : List (String × Nat))
    (fields : List (String × Data)) : Array Cell × List (String × Address) :=
  let pair := fields.foldl (fun (prior : Array Cell × List (String × Address)) field =>
    let address := prior.1.size
    (prior.1.push (objectCell stored field), (field.1, address) :: prior.2)) (heap, [])
  (pair.1, pair.2.reverse)

/-- Force a stored part other than a row: its WHNF, allocating only its immediate children.
A row is fetched by the hosted runner, so it has none here. -/
def forceStored (heap : Array Cell) : Stored → Option (Array Cell × RuntimeValue)
  | .object state stored =>
    let (heap, fields) := allocateObjectFields heap stored state
    some (heap, .record fields)
  | .relation field size =>
    let address := heap.size
    some (heap.push (.stored (.items field size) none), .variant "rows" address)
  | .items field size =>
    let address := heap.size
    some (heap.push (.stored (.spine field 0 size) none), .record [("items", address)])
  | .spine field position size =>
    let address := heap.size
    if position < size then some (heap.push (.stored (.cons field position size) none), .variant "cons" address)
    else some (heap.push (.native (.record [])), .variant "nil" address)
  | .cons field position size =>
    let address := heap.size
    some ((heap.push (.stored (.row field position) none)).push (.stored (.spine field (position + 1) size) none),
      .record [("head", address), ("tail", address + 1)])
  | .found field position =>
    let address := heap.size
    some (heap.push (.stored (.row field position) none), .record [("value", address)])
  | .absent _ _ => some (heap, .record [])
  | .size _ size => some (heap, .natural size)
  | .row _ _ | .key _ _ _ => none

/-- The stored parts the hosted runner fetches (`ObjectiveBendDemandData.fetchable`): exactly those `forceStored` cannot force. -/
def Stored.fetched : Stored → Bool
  | .row _ _ | .key _ _ _ => true
  | _ => false

/-- How far into a stored relation's key order a cell shows the run looked: one past the furthest
position whose key it depends on, `size + 1` for the whole key set. A forced spine cell at `j`
(it saw whether row `j` exists, `size + 1` for the `nil`); a lookup's `found` or `absent` at
`j`, forced or not (the sought key is row `j`'s, or lies below it, or past every row at
`size`); a `size` (a count reads the whole key set). Probed keys say nothing more: the lookup's
answer depends only on where the sought key falls. -/
def Cell.reach : Cell → Option (String × Nat)
  | .stored (.spine field position _) (some _) => some (field, position + 1)
  | .stored (.found field position) _ | .stored (.absent field position) _ => some (field, position + 1)
  | .stored (.size field size) _ => some (field, size + 1)
  | _ => Option.none

/-- A relation's `rows` payload held by the host: its field and row count. -/
def storedItems : Option Cell → Option (String × Nat)
  | some (.stored (.items field size) _) => some (field, size)
  | _ => none

/-- One move of the binary search over positions `low` to `high` of a stored relation: probe the
key in the middle (a stored `key` cell, fetched by the hosted runner), or, the range empty,
answer `none` with the position the sought key lies below (`absent`). -/
def searchStep (heap : Array Cell) (key : List String) (probe : Address) (field : String)
    (low high : Nat) (rest : List Frame) : State :=
  let address := heap.size
  if low < high then
    ⟨heap.push (.stored (.key field ((low + high) / 2) key) none), .enter probe,
      .argument (.bound 0) [address] :: .relationSearch key probe field low high :: rest⟩
  else ⟨heap.push (.stored (.absent field low) none), .returned (.variant "none" address), rest⟩

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
    | some (.cached _ value) | some (.nativeCached _ value) => {state with control:=.returned value}
    | some (.native origin) =>
      let (heap, value) := forceNative state.heap origin
      {state with heap := heap.set! address (.nativeCached origin value), control := .returned value}
    | some (.stored _ (some value)) => {state with control:=.returned value}
    | some (.stored part none) => match forceStored state.heap part with
      | some (heap, value) => {state with heap := heap.set! address (.stored part (some value)), control := .returned value}
      | none => {state with control := .refused .unfetched}
    | some (.suspended origin) =>
      {state with heap:=state.heap.set! address (.evaluating origin), control:=.evaluate origin.term origin.environment,stack:=.update address::state.stack}
  | .nativeApplication function argument remaining =>
    let control := match remaining with
      | [] => .evaluate function []
      | next :: rest => .nativeApplication function next rest
    {state with control, stack := .nativeArgument argument :: state.stack}
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
    | .unary primitive argument => {state with control:=.evaluate argument environment,stack:=.unary primitive::state.stack}
    | .binary primitive left right => {state with control:=.evaluate left environment, stack:=.binaryLeft primitive right environment::state.stack}
    | .inject tag payload =>
      let address := state.heap.size
      {state with heap:=state.heap.push (.suspended ⟨payload,environment⟩),control:=.returned (.variant tag address)}
    | .case scrutinee arms => {state with control:=.evaluate scrutinee environment, stack:=.case arms environment::state.stack}
    | .ifBool condition whenTrue whenFalse => {state with control:=.evaluate condition environment, stack:=.ifBool whenTrue whenFalse environment::state.stack}
    | .done value | .toData value => {state with control:=.evaluate value environment}
    | .refuse reason => {state with control:=.evaluate reason environment, stack:=.refuse::state.stack}
    | .textJoin list separator =>
      {state with control:=.evaluate separator environment, stack:=.joinSeparator list environment::state.stack}
    | .relationCount relation =>
      {state with control:=.evaluate relation environment, stack:=.relationRows (.count 0)::state.stack}
    | .relationLookup relation key probe =>
      let address := state.heap.size
      {state with heap:=state.heap.push (.suspended ⟨probe,environment⟩), control:=.evaluate relation environment, stack:=.relationRows (.lookup key address)::state.stack}
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
      | .nativeArgument argument => match value with
        | .specification _ extension => {state with control := .enter extension}
        | .closure body captured =>
          let address := state.heap.size
          {state with heap := state.heap.push (.native argument), control := .evaluate body (address :: captured), stack := rest}
        | _ => {state with control := .refused .wrongValue, stack := rest}
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
      | .unary primitive =>
        match (valueTerm value).bind (unaryResult primitive) with
        | some result => match scalarValue result with
          | some next => {state with control:=.returned next,stack:=rest}
          | none => {state with control:=.refused .wrongValue,stack:=rest}
        | none => {state with control:=.refused .wrongValue,stack:=rest}
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
      | .joinSeparator list environment => match value with
        | .label separator => {state with control:=.evaluate list environment,stack:=.joinList separator "" true::rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .joinList separator accumulated first => match value with
        | .variant tag payload =>
          if tag == "nil" then {state with control:=.returned (.label accumulated),stack:=rest}
          else if tag == "cons" then {state with control:=.enter payload,stack:=.joinCons separator accumulated first::rest}
          else {state with control:=.refused .missingArm,stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .joinCons separator accumulated first => match value with
        | .record fields =>
          match fields.find? (fun field => field.1 == "head"), fields.find? (fun field => field.1 == "tail") with
          | some head, some tail =>
            {state with control:=.enter head.2,stack:=.joinHead separator accumulated first tail.2::rest}
          | _, _ => {state with control:=.refused .missingField,stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .joinHead separator accumulated first tail => match value with
        | .label head =>
          let joined := if first then head else accumulated ++ separator ++ head
          {state with control:=.enter tail,stack:=.joinList separator joined false::rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .relationRows walk => match value with
        | .variant tag payload =>
          if tag == "rows" then
            match walk, storedItems state.heap[payload]? with
            | .count counted, some (field, size) =>
              {state with heap:=state.heap.push (.stored (.size field size) (some (.natural size))), control:=.returned (.natural (counted + size)), stack:=rest}
            | .lookup key probe, some (field, size) => searchStep state.heap key probe field 0 size rest
            | _, _ => {state with control:=.enter payload, stack:=.field "items"::.relationList walk::rest}
          else {state with control:=.refused .missingArm,stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .relationList walk => match value with
        | .variant tag payload =>
          if tag == "nil" then match walk with
            | .count counted => {state with control:=.returned (.natural counted),stack:=rest}
            | .lookup _ _ =>
              let address := state.heap.size
              {state with heap:=state.heap.push (.native (.record [])), control:=.returned (.variant "none" address), stack:=rest}
          else if tag == "cons" then match walk with
            | .count counted =>
              {state with control:=.enter payload, stack:=.field "tail"::.relationList (.count (counted + 1))::rest}
            | .lookup key probe =>
              let address := state.heap.size
              {state with heap:=state.heap.push (.suspended ⟨keyProjectionTerm key,[payload]⟩), control:=.enter probe, stack:=.argument (.bound 0) [address]::.relationProbe key probe payload::rest}
          else {state with control:=.refused .missingArm,stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .relationProbe key probe payload => match value with
        | .natural 0 =>
          {state with control:=.enter payload, stack:=.field "tail"::.relationList (.lookup key probe)::rest}
        | .natural 1 =>
          let address := state.heap.size
          {state with heap:=state.heap.push (.suspended ⟨.record [("value", .get (.bound 0) "head")],[payload]⟩), control:=.returned (.variant "some" address), stack:=rest}
        | .natural _ =>
          let address := state.heap.size
          {state with heap:=state.heap.push (.native (.record [])), control:=.returned (.variant "none" address), stack:=rest}
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .relationSearch key probe field low high => match value with
        | .natural 0 => searchStep state.heap key probe field ((low + high) / 2 + 1) high rest
        | .natural 1 =>
          let address := state.heap.size
          {state with heap:=state.heap.push (.stored (.found field ((low + high) / 2)) none), control:=.returned (.variant "some" address), stack:=rest}
        | .natural _ => searchStep state.heap key probe field low ((low + high) / 2) rest
        | _ => {state with control:=.refused .wrongValue,stack:=rest}
      | .refuse => match value with
        | .label reason => {state with control:=.refused (.program reason),stack:=rest}
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

/-- A refusal evaluates its reason before the turn ends: `refuse (a ++ b)` stops, seven
transitions on, refused with the text `a ++ b`, the heap and the stack as they were. -/
theorem refuse_evaluates_its_reason (heap : Array Cell) (a b : String) (environment : Environment)
    (stack : List Frame) :
    Nat.repeat stepRaw 7 ⟨heap,.evaluate (.refuse (.binary .textConcat (.label a) (.label b))) environment,stack⟩ =
      ⟨heap,.refused (.program (a ++ b)),stack⟩ := by
  simp [Nat.repeat, stepRaw, valueTerm, scalarValue, primitiveResult]

#assert_axioms perform_yields perform_under_update_refused resume_requires_yield refuse_evaluates_its_reason

end Delvetalk.Theory.ObjectiveBendDemandMachine
