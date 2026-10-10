/- Collection of the Core4 demand heap at a yield (design B4/T5).

A yielded activity's checkpoint is its exact machine state, and the demand machine
only ever allocates: every cell a finished demand left behind stays in the heap, so an
activity that loops through yields grows its checkpoint without bound. `collect` keeps
exactly the cells traced from the roots (the control, including the yielded Plan cell,
and every stack frame), numbers them in a canonical order from the roots (a sum's payload
in a later round, so how far a turn walked a list moves no other cell; address order when
the traversal does not check out), and renames every address. Addresses past the heap (never present in a lexically valid state) are
renamed by the shift that keeps them past the compacted heap, so collection is total and
its behaviour theorem needs no validity premise.

Costs: marking is a worklist over an `Array Bool` (each cell is traced once, each edge
pushed once), ranking is one `Array.foldl`, compaction one `Array.zip`/`filterMap`, and
renaming touches each kept address once: linear in heap + edges, no list lookups over the
heap.

The behaviour theorem (a renaming simulation: lockstep `stepRaw`, `resume`, bounded and
hosted runs, Plan/result extraction, `checkpoint_resume_segment`) is in
`Theory.ObjectiveBendDemandCollectProofs`. A new frame, cell or control that holds
addresses must be added to `frameAddresses`/`cellAddresses`/`controlAddresses` and the
renamings, or `related_stepRaw` stops building. -/
import Theory.ObjectiveBendDemandMachine
import Theory.AxiomPin
namespace Minidregg.Theory.ObjectiveBendDemandCollect
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendDemandMachine
set_option autoImplicit false

/-! ## The addresses a machine object holds -/

def valueAddresses : RuntimeValue → List Nat
  | .closure _ environment => environment
  | .natural _ | .boolean _ | .label _ => []
  | .record fields => fields.map Prod.snd
  | .specification metadata extension => [metadata, extension]
  | .prototype specification target => [specification, target]
  | .variant _ payload => [payload]

def cellAddresses : Cell → List Nat
  | .suspended origin | .evaluating origin => origin.environment
  | .cached origin value => origin.environment ++ valueAddresses value
  | .native _ => []
  | .nativeCached _ value => valueAddresses value

def frameAddresses : Frame → List Nat
  | .argument _ environment | .extend _ environment | .condition _ _ environment
  | .binaryLeft _ _ environment | .case _ environment | .ifBool _ _ environment => environment
  | .update address => [address]
  | .field _ | .reflect | .metadata | .project | .nativeArgument _ | .unary _ => []
  | .binaryRight _ value => valueAddresses value
  | .joinSeparator _ environment => environment
  | .joinList .. | .joinCons .. => []
  | .joinHead _ _ _ tail => [tail]

def controlAddresses : Control → List Nat
  | .evaluate _ environment => environment
  | .enter address | .blackhole address | .yielded address => [address]
  | .nativeApplication _ _ _ => []
  | .returned value | .complete value => valueAddresses value
  | .refused _ => []

/-- The roots: the control (a yielded state's Plan address among them) and every frame. -/
def rootAddresses (state : State) : List Nat :=
  controlAddresses state.control ++ state.stack.flatMap frameAddresses

/-! ## Renaming every address -/

def renameValue (f : Nat → Nat) : RuntimeValue → RuntimeValue
  | .closure body environment => .closure body (environment.map f)
  | .natural value => .natural value
  | .boolean value => .boolean value
  | .label value => .label value
  | .record fields => .record (fields.map fun field => (field.1, f field.2))
  | .specification metadata extension => .specification (f metadata) (f extension)
  | .prototype specification target => .prototype (f specification) (f target)
  | .variant label payload => .variant label (f payload)

def renameClosure (f : Nat → Nat) (closure : Closure) : Closure :=
  ⟨closure.term, closure.environment.map f⟩

def renameCell (f : Nat → Nat) : Cell → Cell
  | .suspended origin => .suspended (renameClosure f origin)
  | .evaluating origin => .evaluating (renameClosure f origin)
  | .cached origin value => .cached (renameClosure f origin) (renameValue f value)
  | .native origin => .native origin
  | .nativeCached origin value => .nativeCached origin (renameValue f value)

def renameFrame (f : Nat → Nat) : Frame → Frame
  | .argument term environment => .argument term (environment.map f)
  | .update address => .update (f address)
  | .field name => .field name
  | .reflect => .reflect
  | .metadata => .metadata
  | .project => .project
  | .extend fields environment => .extend fields (environment.map f)
  | .condition zero successorBody environment => .condition zero successorBody (environment.map f)
  | .binaryLeft primitive right environment => .binaryLeft primitive right (environment.map f)
  | .binaryRight primitive left => .binaryRight primitive (renameValue f left)
  | .case arms environment => .case arms (environment.map f)
  | .ifBool whenTrue whenFalse environment => .ifBool whenTrue whenFalse (environment.map f)
  | .nativeArgument value => .nativeArgument value
  | .unary primitive => .unary primitive
  | .joinSeparator list environment => .joinSeparator list (environment.map f)
  | .joinList separator accumulated first => .joinList separator accumulated first
  | .joinCons separator accumulated first => .joinCons separator accumulated first
  | .joinHead separator accumulated first tail => .joinHead separator accumulated first (f tail)

def renameControl (f : Nat → Nat) : Control → Control
  | .evaluate term environment => .evaluate term (environment.map f)
  | .enter address => .enter (f address)
  | .blackhole address => .blackhole (f address)
  | .returned value => .returned (renameValue f value)
  | .complete value => .complete (renameValue f value)
  | .refused reason => .refused reason
  | .yielded plan => .yielded (f plan)
  | .nativeApplication function argument remaining => .nativeApplication function argument remaining

/-! ## Marking -/

/-- The addresses the cell at `address` holds; nothing past the heap. -/
def children (heap : Array Cell) (address : Nat) : List Nat :=
  match heap[address]? with
  | some cell => cellAddresses cell
  | none => []

/-- Drop the worklist prefix that needs no tracing: marked addresses and addresses
past the heap (those are renamed by the shift, never traced). -/
def pending (marks : Array Bool) : List Nat → List Nat
  | [] => []
  | address :: rest => match marks[address]? with
    | some false => address :: rest
    | _ => pending marks rest

/-- Worklist marking. `fuel` bounds the cells still unmarked (each mark spends one
unit); the worklist is drained between marks, so the recursion is structural and the
fuel provably never runs out first (`markFrom_spec`). -/
def markFrom (heap : Array Cell) : Nat → Array Bool → List Nat → Array Bool
  | 0, marks, _ => marks
  | fuel+1, marks, work => match pending marks work with
    | [] => marks
    | address :: rest =>
      markFrom heap fuel (marks.set! address true) (children heap address ++ rest)

/-- Which cells are live: traced from the roots. -/
def liveMarks (state : State) : Array Bool :=
  markFrom state.heap state.heap.size (Array.replicate state.heap.size false) (rootAddresses state)

/-! ## Compaction -/

/-- One rank step: record the live count so far, count this cell if it is live. -/
def rankStep (acc : Array Nat × Nat) (marked : Bool) : Array Nat × Nat :=
  (acc.1.push acc.2, if marked then acc.2 + 1 else acc.2)

/-- Each old address's new address (the number of live cells before it), and the
number of live cells. -/
def rankTable (marks : Array Bool) : Array Nat × Nat :=
  marks.foldl rankStep (#[], 0)

/-- The renaming: a heap address goes to its rank; an address past the heap keeps
its distance past the end. -/
def relocate (size live : Nat) (table : Array Nat) (address : Nat) : Nat :=
  if address < size then table.getD address 0 else address - size + live

/-- The live cells in increasing old-address order, renamed. -/
def compact (f : Nat → Nat) (heap : Array Cell) (marks : Array Bool) : Array Cell :=
  (heap.zip marks).filterMap fun entry => if entry.2 then some (renameCell f entry.1) else none

/-- The renaming `collectByAddress` applies to `state`. -/
def addressRenaming (state : State) : Nat → Nat :=
  let ranked := rankTable (liveMarks state)
  relocate state.heap.size ranked.2 ranked.1

/-- Collect keeping the live cells in increasing old-address order. -/
def collectByAddress (state : State) : State :=
  let marks := liveMarks state
  let ranked := rankTable marks
  let f := relocate state.heap.size ranked.2 ranked.1
  ⟨compact f state.heap marks, renameControl f state.control, state.stack.map (renameFrame f)⟩

/-! ## Canonical order

Allocation order makes a checkpoint's addresses depend on how far a turn happened to force
a structure: a reading that walks a list one cell further allocates there, and every cell
allocated after it moves. `collect` instead numbers the live cells by a traversal from the
roots that depends only on the reachable structure: depth first, children in order, except
that a sum's payload (a list's spine is `cons` payloads) is put off to a later round. The
skeleton the roots reach without entering data comes first and keeps its numbers however
far any list was walked; each round of nested data follows. The traversal is not trusted:
its order is used only when `orderValid` confirms it numbers every live cell exactly once,
and otherwise the cells keep address order (`collectByAddress`). -/

/-- A cell's children: those followed now, and a sum value's payload, put off. -/
def splitChildren : Cell → List Nat × List Nat
  | .cached origin (.variant _ payload) => (origin.environment, [payload])
  | .nativeCached _ (.variant _ payload) => ([], [payload])
  | cell => (cellAddresses cell, [])

/-- One round, depth first: number what `work` reaches without entering a payload; the
payloads met are the next round. `fuel` bounds the steps (a short fuel only leaves the order
incomplete, which `orderValid` then refuses). -/
def orderRound (heap : Array Cell) (marks : Array Bool) :
    Nat → Array Bool → Array Nat → List Nat → Array Nat → Array Bool × Array Nat × Array Nat
  | 0, seen, order, _, next => (seen, order, next)
  | _ + 1, seen, order, [], next => (seen, order, next)
  | fuel + 1, seen, order, a :: rest, next =>
    if marks[a]? != some true || seen[a]?.getD true then orderRound heap marks fuel seen order rest next
    else
      let (now, later) := match heap[a]? with
        | some cell => splitChildren cell
        | none => ([], [])
      orderRound heap marks fuel (seen.set! a true) (order.push a) (now ++ rest) (next ++ later.toArray)

def orderRounds (heap : Array Cell) (marks : Array Bool) (fuel : Nat) :
    Nat → Array Bool → Array Nat → List Nat → Array Nat
  | 0, _, order, _ => order
  | rounds + 1, seen, order, round =>
    if round.isEmpty then order
    else
      let (seen, order, next) := orderRound heap marks fuel seen order round #[]
      orderRounds heap marks fuel rounds seen order next.toList

/-- Depth-first rounds from `roots`: each round numbers what it reaches without entering a
payload; the payloads it met start the next round. -/
def canonicalOrder (heap : Array Cell) (marks : Array Bool) (roots : List Nat) : Array Nat :=
  let edges := heap.foldl (fun n cell => n + (cellAddresses cell).length) 0
  orderRounds heap marks (roots.length + edges + heap.size + 1) (heap.size + 1)
    (Array.replicate heap.size false) #[] roots

/-- Each old address's position in `order`. -/
def rankOf (size : Nat) (order : Array Nat) : Array Nat :=
  (order.foldl (fun (acc : Array Nat × Nat) a => (acc.1.set! a acc.2, acc.2 + 1)) (Array.replicate size 0, 0)).1

/-- `order` numbers every live cell exactly once (`rank` is its inverse on them). -/
def orderValid (marks : Array Bool) (order rank : Array Nat) : Bool :=
  order.size == marks.count true &&
  (List.range marks.size).all fun a => marks[a]? != some true ||
    (match rank[a]? with
      | some i => decide (i < order.size) && order[i]? == some a
      | none => false)

/-- The renaming by an order: a live cell to its position, an address past the heap by
the shift past the compacted heap. -/
def orderRenaming (size live : Nat) (rank : Array Nat) (address : Nat) : Nat :=
  if address < size then rank.getD address 0 else address - size + live

/-- The cells in `order`, renamed. -/
def compactInOrder (f : Nat → Nat) (heap : Array Cell) (order : Array Nat) : Array Cell :=
  order.map fun a => renameCell f (heap[a]?.getD (.native (.natural 0)))

structure Ordered where
  marks : Array Bool
  order : Array Nat
  rank : Array Nat

def ordered (state : State) : Ordered :=
  let marks := liveMarks state
  let order := canonicalOrder state.heap marks (rootAddresses state)
  ⟨marks, order, rankOf state.heap.size order⟩

/-- The renaming `collect` applies to `state`. -/
def collectRenaming (state : State) : Nat → Nat :=
  let o := ordered state
  if orderValid o.marks o.order o.rank then orderRenaming state.heap.size o.order.size o.rank
  else addressRenaming state

/-- Collect the heap: keep the cells reachable from the roots, number them canonically,
rename. A yielded state stays yielded (at its Plan cell's new address); heap and stack keep
their meaning under the renaming (`Theory.ObjectiveBendDemandCollectProofs`). -/
def collect (state : State) : State :=
  let o := ordered state
  if orderValid o.marks o.order o.rank then
    let f := orderRenaming state.heap.size o.order.size o.rank
    ⟨compactInOrder f state.heap o.order, renameControl f state.control, state.stack.map (renameFrame f)⟩
  else collectByAddress state

/-! ## Settling: a cached cell's origin is no longer a root

A cached cell keeps the closure it was forced from (`Cell.cached origin value`). The
machine never reads it again: entering a cached cell returns its value, and only an
`evaluating` cell's origin is read (by its update frame). It is ghost data, kept by the
running machine because the source-correspondence proofs (`ObjectiveBendDemandAdequacy`)
name a cell's meaning by it. In a checkpoint it is worse than dead: `collect` traces it,
so a forced accumulator keeps alive every environment it was ever computed from (a
`tally` holds its whole history through its total's origin).

`settle` gives every cached cell the SELF origin `⟨.bound 0, [address]⟩` ("read this
cell"): it retains nothing but the cell itself, it is lexically valid wherever the cell
is, and it is typed at the cell's own assigned type, so a settled state is typed exactly
when the state was (Mini's `typed_settle`; this edition has no state-typing judgment
to port it to). Suspended and evaluating cells are untouched (their
origin is what they will run). Settling changes no transition (`settle_resume_segment`
in `Theory.ObjectiveBendDemandSettleProofs`: every bounded run, extraction and resume
agrees exactly, capacity suspensions included, because heap sizes are unchanged). -/

/-- The origin a settled cached cell keeps: itself. -/
def selfOrigin (address : Nat) : Closure := ⟨.bound 0, [address]⟩

def settleCell (address : Nat) : Cell → Cell
  | .cached _ value => .cached (selfOrigin address) value
  | cell => cell

/-- Replace every cached cell's origin by its self origin. -/
def settle (state : State) : State :=
  {state with heap := state.heap.mapIdx settleCell}

/-- What a yield stores: the settled state, collected. -/
def checkpoint (state : State) : State := collect (settle state)

/-- Limits counted from `start`'s own heap end: `limits.heap` cells beyond the heap it
starts with, and the same stack. A checkpoint resumes under these
(`Kernel.ObjectiveActivity.segmentLimits`): forcing and collection change the size of the
state a segment starts from, never the room it has past it. -/
def limitsPast (limits : Limits) (start : State) : Limits :=
  ⟨start.heap.size + limits.heap, limits.stack⟩

/-! ## Measurement: collection drops garbage

A yielded state whose heap holds a finished demand's leftovers: cell 1 (a spent argument
thunk) and cell 3 (a cached intermediate) are unreachable; the Plan cell 2 captures cell
0, and the stack's argument frame captures cell 4. -/

def garbageExample : State :=
  ⟨#[.cached ⟨.nat 1, []⟩ (.natural 1), .suspended ⟨.nat 7, []⟩,
     .suspended ⟨.bound 0, [0]⟩, .cached ⟨.nat 9, []⟩ (.natural 9),
     .suspended ⟨.nat 5, []⟩],
   .yielded 2, [.argument (.bound 0) [4]]⟩

theorem garbageExample_heap_size : garbageExample.heap.size = 5 := rfl

/-- Two of five cells are garbage: the collected heap has three. -/
theorem collect_garbageExample_heap_size : (collect garbageExample).heap.size = 3 := by decide +kernel

/-- Numbered from the roots: the yielded Plan cell (the first root) moved from 2 to 0, the
cell it captures from 0 to 1, and the frame's capture from 4 to 2. -/
theorem collect_garbageExample_roots :
    (match (collect garbageExample).control with | .yielded plan => plan | _ => 99) = 0 ∧
    (collect garbageExample).stack.flatMap frameAddresses = [2] := by decide

#assert_axioms collect_garbageExample_heap_size
#assert_axioms collect_garbageExample_roots

end Minidregg.Theory.ObjectiveBendDemandCollect
