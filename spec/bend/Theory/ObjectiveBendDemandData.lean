/- Full Core4 data extraction through the same bounded demand machine. Global
node/tick/canonical encoded output budgets are shared across all fields. Budget suspension
retains the exact graph, never a partial successful Plan or invalid-program claim. -/
import Theory.ObjectiveBendDemandMachine
import Theory.ObjectiveBendDemandMachineFast
import Theory.ObjectiveBendTypes
namespace Minidregg.Theory.ObjectiveBendDemandData
open ObjectiveBendDemandMachine
def lengthBytes (n : Nat) : List UInt8 := (toString n).toUTF8.toList ++ [0]
def encoded : Nat → Data → Option (List UInt8)
  | 0,_ => none
  | _+1,.natural n => some ([0] ++ lengthBytes n)
  | _+1,.boolean b => some [1,if b then 1 else 0]
  | _+1,.label s => some ([2] ++ lengthBytes s.utf8ByteSize ++ s.toUTF8.toList)
  | depth+1,.record fields => do
      let children ← fields.mapM fun field => do
        pure (lengthBytes field.1.utf8ByteSize ++ field.1.toUTF8.toList ++ (← encoded depth field.2))
      pure ([3] ++ lengthBytes fields.length ++ children.flatten)
  | depth+1,.variant label payload => do
      pure ([4] ++ lengthBytes label.utf8ByteSize ++ label.toUTF8.toList ++ (← encoded depth payload))
inductive Failure where
  /-- Only machine tick suspension: forceWith exhausted its countdown. -/
  | tickExhausted
  | budget | duplicateField | executableValue
  /-- Capacity/policy suspension or an extraction called on the wrong control shape.
  This does not denote tick exhaustion; that is exclusively tickExhausted. -/
  | suspended
  | divergent | refused
  /-- The program yielded a Plan: it is an activity, not a pure value. -/
  | yielded
  deriving Repr
/-- Tick exhaustion is distinct from capacity/policy suspension. -/
def suspensionFailure : Suspension → Failure
  | .ticks => .tickExhausted
  | .capacity => .suspended
structure Budget where
  nodes : Nat
  ticks : Nat
  bytes : Nat
  deriving Repr
structure Result where
  value : Data
  state : State
  remaining : Budget
  deriving Repr
/-- One-tick calls consume one global allowance; terminal inspection is free.
No field receives a fresh allowance. Heap/stack limits stay common throughout. -/
def forceWith (policy : State → Bool) (limits : Limits) : Nat → State → Outcome × Nat
  | 0,state => (runBounded limits 0 state,0)
  | ticks+1,state => match state.control with
    | .complete _ | .refused _ | .blackhole _ | .yielded _ => (runBounded limits 0 state,ticks+1)
    | _ => if !policy state then (.suspended .capacity state,ticks+1) else
      match runBounded limits 1 state with
      | .suspended .ticks next => forceWith policy limits ticks next
      | other => (other,ticks)

/-- Compiled code runs `forceWithFast` (depth carried, one transition per
allowance); this is `forceWith` exactly (ObjectiveBendDemandMachineFast). -/
@[csimp] theorem forceWith_eq_fast : @forceWith = @ObjectiveBendDemandMachineFast.forceWithFast :=
  ObjectiveBendDemandMachineFast.forceWithFast_unique forceWith (fun _ _ _ => rfl) (fun _ _ _ _ => rfl)
/--
info: 'Minidregg.Theory.ObjectiveBendDemandData.forceWith_eq_fast' depends on axioms: [propext, Classical.choice, Quot.sound]
-/
#guard_msgs in
#print axioms forceWith_eq_fast

/-- Preflight is itself bounded by the available work. Each scalar visit pays
for two passes (preflight and evaluation), each with a conservative full-alphabet
membership walk plus input advancement. No string is allocated by the scan. -/
def textPrefixCost (text alphabet : String) (member : Bool) (ticks : Nat) : Nat × Nat :=
  let perScalar := 2 * (alphabet.utf8ByteSize + 2)
  let result := ObjectiveBendOpenRecursion.textPrefixScan alphabet member
    ((ticks - 1) / perScalar) (String.Legacy.iter text) 0 0
  if result.2.2 then (1 + perScalar * result.2.1, 0) else (ticks + 1, 0)

/-- The byte size of the first `n` scalars, scanning at most `fuel` of them
(`none` once the scan would pass `fuel`). No string is allocated. -/
def scalarPrefixBytes : Nat → Nat → String.Legacy.Iterator → Option Nat
  | _, 0, cursor => some cursor.i.byteIdx
  | 0, _ + 1, _ => none
  | fuel + 1, n + 1, cursor => if cursor.atEnd then some cursor.i.byteIdx else scalarPrefixBytes fuel n cursor.next

/-- `textTake`/`textDrop` by `n` scalars of `text`: the exact byte size of the
prefix they traverse, when `ticks` can pay for it. The scan is bounded by what
the work allowance could pay (each scalar costs at least two ticks), so an
unaffordable prefix is refused after at most `ticks / 2` scalars. -/
def prefixCost (text : String) (n ticks : Nat) : Option Nat :=
  scalarPrefixBytes ((ticks - 1) / 2 + 1) n (String.Legacy.iter text)

/-- Hosted text work and exact result allocation bound, checked before
`stepRaw` constructs a String. Ordinary pinned transitions retain unit cost.
Unicode operations traverse scalar sequences; their UTF-8 size bounds both the
scalar traversal and copied bytes. `textTake` and `textDrop` are charged by the
prefix they traverse (the taken, respectively the dropped, scalars), measured in
bytes by a bounded scan (`prefixCost`), not by the whole input and not by the
four-bytes-per-scalar upper bound. Each reserves what it allocates: `textTake`
copies the taken prefix; `textDrop` retains nothing of the dropped prefix and
copies the suffix (`B - prefix` bytes). (The runtime's `String.Slice.toString`
is `lean_string_utf8_extract`, a fresh string: the suffix is copied, not shared.
That copy is the one text work not charged in ticks, so that a drop-by-one walk
stays linear; its bytes are bounded here.) Decimal conversion uses a conservative
quadratic bit-work allowance and bit-count allocation bound. -/
def textStepCost (state : State) (ticks : Nat) : Nat × Nat :=
  match state.control,state.stack with
  | .returned (.label alphabet), .binaryRight .textSpan (.label text) :: _ => textPrefixCost text alphabet true ticks
  | .returned (.label alphabet), .binaryRight .textBreak (.label text) :: _ => textPrefixCost text alphabet false ticks
  | .returned (.label right), .binaryRight .textConcat (.label left) :: _ =>
      let bytes := left.utf8ByteSize + right.utf8ByteSize
      (1 + 2 * bytes, bytes)
  | .returned (.natural n), .binaryRight .textTake (.label text) :: _ =>
      if n == 0 || n >= text.utf8ByteSize then (1, 0)
      else match prefixCost text n ticks with
        | some bytes => (1 + 2 * bytes, bytes)
        | none => (ticks + 1, 0)
  | .returned (.natural n), .binaryRight .textDrop (.label text) :: _ =>
      if n == 0 || n >= text.utf8ByteSize then (1, 0)
      else match prefixCost text n ticks with
        | some dropped => (1 + 2 * dropped, text.utf8ByteSize - dropped)
        | none => (ticks + 1, 0)
  | .returned (.label head), .joinHead separator accumulated first _ :: _ =>
      -- Appending onto the join's own accumulator: charged by the bytes added, so a
      -- join is linear in its output; it reserves the whole new accumulator.
      let added := if first then head.utf8ByteSize else separator.utf8ByteSize + head.utf8ByteSize
      (1 + 2 * added, if first then added else accumulated.utf8ByteSize + added)
  | .returned (.label text), .unary .textLength :: _ => (1 + text.utf8ByteSize, 0)
  | .returned (.label text), .unary .sha256Text :: _ =>
      let bytes := text.utf8ByteSize
      let blocks := (bytes + 72) / 64
      -- Prepay input copying/padding, all compression blocks and hex output.
      -- Reserve padded input plus bounded SHA schedule/state/hex workspace.
      (65 + 8 * ((bytes + 63) / 64) + 32 * blocks, 64 * blocks + 4096)
  | .returned (.natural n), .unary .natText :: _ =>
      let bits := n.log2 + 1
      (1 + bits * bits, bits)
  | _,_ => (1,0)

/-- Explicit hosted extension of forcing. No primitive is entered before its
whole work/allocation allowance is admitted. Insufficient work retains the
pre-step graph. The pinned unit-cost `forceWith` and its fast proof stay intact. -/
def forceHostedFrom (policy : State → Bool) (limits : Limits) (bytes : Nat)
    (ticks : Nat) (state : State) (depth : Nat) : Outcome × Nat :=
  match ticks with
  | 0 => (runBounded limits 0 state,0)
  | remaining+1 =>
    let ticks := remaining+1
    match state.control with
    | .complete _ | .refused _ | .blackhole _ | .yielded _ => (runBounded limits 0 state,ticks)
    | _ =>
      let cost := textStepCost state ticks
      if !policy state || cost.2 > bytes then (.suspended .capacity state,ticks)
      else if cost.1 > ticks then
        -- A failed prefix preflight already spent its bounded allowance; it may
        -- not return that work to a caller as unused execution credit.
        let remaining := match state.control, state.stack with
          | .returned (.label _), .binaryRight .textSpan (.label _) :: _
          | .returned (.label _), .binaryRight .textBreak (.label _) :: _ => 0
          | _, _ => ticks
        (.suspended .ticks state, remaining)
      else
        let sizes := ObjectiveBendDemandMachineFast.sizesAfter state depth
        if sizes.1 ≤ limits.heap && sizes.2 ≤ limits.stack then
          forceHostedFrom policy limits bytes (ticks - max 1 cost.1)
            (ObjectiveBendDemandMachineFast.stepRawFast state) sizes.2
        else (.suspended .capacity state,ticks - max 1 cost.1)
termination_by ticks
decreasing_by
  simp_wf
  omega

def forceHostedWith (policy : State → Bool) (limits : Limits) (bytes ticks : Nat) (state : State) : Outcome × Nat :=
  forceHostedFrom policy limits bytes ticks state state.stack.length

/-- Materialization threads the remaining budget through failures as well as successes.
Tick counts come directly from forceWith; failed children retain all earlier field spend. -/
def materializeWith (policy : State → Bool) (limits : Limits) : Nat → Budget → RuntimeValue → State → Except (Failure × State × Budget) Result
  | 0, budget, _, state => .error (.budget,state,budget)
  | depth+1, budget, value, state => do
    if budget.nodes = 0 then throw (.budget,state,budget)
    let remaining := {budget with nodes:=budget.nodes-1}
    match value with
    | .natural n =>
      let bytes := (toString n).utf8ByteSize + 2
      if bytes > remaining.bytes then throw (.budget,state,remaining)
      pure ⟨.natural n,state,{remaining with bytes:=remaining.bytes-bytes}⟩
    | .boolean b =>
      if remaining.bytes < 2 then throw (.budget,state,remaining)
      pure ⟨.boolean b,state,{remaining with bytes:=remaining.bytes-2}⟩
    | .label s =>
      let bytes := s.utf8ByteSize + (toString s.utf8ByteSize).utf8ByteSize + 2
      if bytes > remaining.bytes then throw (.budget,state,remaining)
      pure ⟨.label s,state,{remaining with bytes:=remaining.bytes-bytes}⟩
    | .record fields =>
      let headerBytes := (toString fields.length).utf8ByteSize+2
      if headerBytes > remaining.bytes then throw (.budget,state,remaining)
      let remaining := {remaining with bytes:=remaining.bytes-headerBytes}
      if (fields.map Prod.fst).eraseDups.length != fields.length then throw (.duplicateField,state,remaining)
      if fields.length > remaining.nodes then throw (.budget,state,remaining)
      let pair ← fields.foldlM (fun (prior : List (String × Data) × State × Budget) field => do
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
        | .yielded _ retained => throw (.yielded,retained,nextBudget)) ([],state,remaining)
      pure ⟨.record pair.1.reverse,pair.2.1,pair.2.2⟩
    | .variant label payload =>
      let bytes := label.utf8ByteSize+(toString label.utf8ByteSize).utf8ByteSize+2
      if bytes > remaining.bytes || remaining.nodes = 0 then throw (.budget,state,remaining)
      let entered : State := {state with control:=.enter payload,stack:=[]}
      let (outcome,ticks) := forceHostedWith policy limits remaining.bytes remaining.ticks entered
      let nextBudget := {remaining with ticks:=ticks,bytes:=remaining.bytes-bytes}
      match outcome with
      | .finished forced retained =>
        let child ← materializeWith policy limits depth nextBudget forced retained
        pure ⟨.variant label child.value,child.state,child.remaining⟩
      | .suspended reason retained => throw (suspensionFailure reason,retained,nextBudget)
      | .divergent _ retained => throw (.divergent,retained,nextBudget)
      | .refused _ retained => throw (.refused,retained,nextBudget)
      | .yielded _ retained => throw (.yielded,retained,nextBudget)
    | .closure _ _ | .specification _ _ | .prototype _ _ => throw (.executableValue,state,remaining)

def completeWith (policy : State → Bool) (limits : Limits) (budget : Budget) (state : State) : Except (Failure × State × Budget) Result :=
  if !policy state then .error (.suspended,state,budget) else
  match state.control,state.stack with
  | .complete value,[] => do
    let result ← materializeWith policy limits budget.nodes budget value state
    let some bytes := encoded budget.nodes result.value | throw (.budget,result.state,result.remaining)
    if bytes.length > budget.bytes then throw (.budget,result.state,result.remaining)
    pure result
  | _,_ => .error (.suspended,state,budget)
/-- A receiver keeps this exact graph-to-full-data correspondence alongside
its independently checked source/state-origin evidence. -/
structure ExtractionWith (policy : State → Bool) (limits : Limits) (budget : Budget) (state : State) where
  private mk ::
  result : Result
  exact : completeWith policy limits budget state = .ok result

def extractWith (policy : State → Bool) (limits : Limits) (budget : Budget) (state : State) :
    Except (Failure × State × Budget) (ExtractionWith policy limits budget state) :=
  match equation : completeWith policy limits budget state with
  | .error failure => .error failure
  | .ok result => .ok ⟨result,equation⟩
/-- One whole source-and-materialization allowance; native callers do not need
an untrusted source tick estimate or a fresh budget at WHNF completion. -/
structure StateExecutionWith (policy : State → Bool) (limits : Limits) (budget : Budget)
    (initialState : State) where
  private mk ::
  value : RuntimeValue
  state : State
  remainingTicks : Nat
  runExact : forceHostedWith policy limits budget.bytes budget.ticks initialState =
    (.finished value state,remainingTicks)
  extraction : ExtractionWith policy limits {budget with ticks:=remainingTicks} state

def executeStateWith (policy : State → Bool) (limits : Limits) (budget : Budget)
    (initialState : State) :
    Except (Failure × State × Budget) (StateExecutionWith policy limits budget initialState) :=
  match equation : forceHostedWith policy limits budget.bytes budget.ticks initialState with
  | (.finished value state,ticks) => do
    let extraction ← extractWith policy limits {budget with ticks:=ticks} state
    pure ⟨value,state,ticks,equation,extraction⟩
  | (.suspended reason state,ticks) => .error (suspensionFailure reason,state,{budget with ticks := ticks})
  | (.divergent _ state,ticks) => .error (.divergent,state,{budget with ticks := ticks})
  | (.refused _ state,ticks) => .error (.refused,state,{budget with ticks := ticks})
  | (.yielded _ state,ticks) => .error (.yielded,state,{budget with ticks := ticks})

abbrev ExecutionWith (policy : State → Bool) (limits : Limits) (budget : Budget)
    (term : Minidregg.Theory.ObjectiveBendOpenRecursion.Term) :=
  StateExecutionWith policy limits budget (initial term)

def executeWith (policy : State → Bool) (limits : Limits) (budget : Budget)
    (term : Minidregg.Theory.ObjectiveBendOpenRecursion.Term) :
    Except (Failure × State × Budget) (ExecutionWith policy limits budget term) :=
  executeStateWith policy limits budget (initial term)

/-- Native arguments must already have finite-data/type/quantity admission.
They enter lazily as closed pure data cells; source thunk forcing and activities
retain their existing semantics. Actual data construction uses one transition,
so removed AST evaluation/update instructions consume no artificial ticks. -/
def executeDataArgumentsWith (policy : State → Bool) (limits : Limits) (budget : Budget)
    (term : Minidregg.Theory.ObjectiveBendOpenRecursion.Term) (arguments : List Data) :=
  executeStateWith policy limits budget (initialDataArguments term arguments)

def executeDataArguments := executeDataArgumentsWith (fun _ => true)
/-- Existing clear preview behavior remains the unrestricted raw language. -/
def force := forceWith (fun _ => true)
def materialize := materializeWith (fun _ => true)
def complete := completeWith (fun _ => true)
abbrev Extraction := ExtractionWith (fun _ => true)
def extract := extractWith (fun _ => true)
abbrev Execution := ExecutionWith (fun _ => true)
def execute := executeWith (fun _ => true)

/-! ## Activities: the yielded Plan is data; the response is typed data -/

open Minidregg.Theory.ObjectiveBendTypes in
/-- The member type of a first-order row (no rigid variables in data types). -/
def rowMember : Ty → String → Option Ty
  | .field name member tail, query => if name = query then some member else rowMember tail query
  | _, _ => none

open Minidregg.Theory.ObjectiveBendTypes in
def rowNames : Ty → List String
  | .field name _ tail => name :: rowNames tail
  | _ => []


open Minidregg.Theory.ObjectiveBendTypes in
mutual
/-- Exact first-order conformance of data to a data type: every record field
is declared once and every declared field is present; a variant's label is one
of the sum's labels and its payload conforms. A variable (a closed recursive
sum) conforms as its bound: one unfolding per constructor it is matched
against. `fuel` only bounds the walk; `Data.conforms` supplies enough for the
data's own size and the number of bounds. -/
def Data.conformsFuel (bounds : DataBounds) : Nat → Data → Ty → Bool
  | 0, _, _ => false
  | fuel + 1, .natural _, .natural | fuel + 1, .boolean _, .boolean
  | fuel + 1, .label _, .label => true
  | fuel + 1, data, .variable index => match bounds.lookup index with
      | some bound => Data.conformsFuel bounds fuel data bound
      | none => false
  | _ + 1, data, .data => data.wellFormed
  | fuel + 1, .record fields, row =>
      (match row with | .field .. | .emptyRow => true | _ => false) &&
      fields.length == (rowNames row).length &&
      (fields.map Prod.fst).eraseDups.length == fields.length && Data.fieldsConformFuel bounds fuel fields row
  | fuel + 1, .variant tag payload, .variant row => match rowMember row tag with
      | some member => Data.conformsFuel bounds fuel payload member
      | none => false
  | _, _, _ => false
def Data.fieldsConformFuel (bounds : DataBounds) : Nat → List (String × Data) → Ty → Bool
  | 0, _, _ => false
  | _ + 1, [], _ => true
  | fuel + 1, (name,value) :: rest, row =>
      (match rowMember row name with
        | some member => Data.conformsFuel bounds fuel value member
        | none => false) && Data.fieldsConformFuel bounds fuel rest row
end

mutual
def Data.size : Data → Nat
  | .natural _ | .boolean _ | .label _ => 1
  | .record fields => 1 + Data.fieldsSize fields
  | .variant _ payload => 1 + payload.size
def Data.fieldsSize : List (String × Data) → Nat
  | [] => 0
  | (_, value) :: rest => value.size + Data.fieldsSize rest
end

open Minidregg.Theory.ObjectiveBendTypes in
/-- Conformance under the declared bounds of a checked packet. The walk is
bounded by the data's size times the bounds that one node may unfold through. -/
def Data.conformsUnder (bounds : DataBounds) (data : Data) (type : Ty) : Bool :=
  Data.conformsFuel bounds ((data.size + 1) * (bounds.length + 3) + 2) data type

open Minidregg.Theory.ObjectiveBendTypes in
def Data.conforms (data : Data) (type : Ty) : Bool := data.conformsUnder [] type

/-- Extract the Plan of a yielded state through the same budgeted
materialization as every other Data: enter its cell with an empty stack. -/
def yieldedPlanWith (policy : State → Bool) (limits : Limits) (budget : Budget) (state : State) :
    Except (Failure × State × Budget) Result :=
  match state.control with
  | .yielded plan =>
    let entered : State := {state with control:=.enter plan,stack:=[]}
    match forceHostedWith policy limits budget.bytes budget.ticks entered with
    | (.finished forced retained,ticks) => do
      -- Materialization runs on the scratch copy; the checkpoint keeps its stack.
      let result ← materializeWith policy limits budget.nodes {budget with ticks:=ticks} forced retained
      pure {result with state:={result.state with control:=state.control,stack:=state.stack}}
    | (.suspended reason retained,ticks) => .error (suspensionFailure reason,retained,{budget with ticks := ticks})
    | (.divergent _ retained,ticks) => .error (.divergent,retained,{budget with ticks := ticks})
    | (.refused _ retained,ticks) => .error (.refused,retained,{budget with ticks := ticks})
    | (.yielded _ retained,ticks) => .error (.yielded,retained,{budget with ticks := ticks})
  | _ => .error (.suspended,state,budget)
def yieldedPlan := yieldedPlanWith (fun _ => true)

end Minidregg.Theory.ObjectiveBendDemandData
