/-
# Pred.Core — the ONE predicate algebra (ATLAS §7), syntactic AST end-to-end.

This is the foundational policy object of minidregg: a decidable predicate AST over a
name-keyed state/step. It is AST-only by design law — *no opaque functions anywhere in the
policy path*; every policy object is a syntactic tree from day one, so it is serializable,
comparable (`DecidableEq`, kernel-computable), and admits a faithful second reading (circuit,
cost, explainer).

## Why syntactic-only — the N3 trap this file refuses

`Compiler/Signature.lean` proves the converse of N3 (`N3_opaque_payloads_forbid_second_reading`,
faces `OpaqueConflation` / `NoFaithfulSyntacticReading`): a signature whose leaves carry OPAQUE
semantic payloads (`σ → Bool` closures) admits interpretations (`opaqueRun`) with **no faithful
compositional second reading** into any countable/syntactic target — there are `2^ℵ₀` guard
closures and only countably many descriptors, so some pair the executor separates gets one
circuit. Breadstuffs paid for this negatively (`RecStmt.guard : RecordKernelState → Bool` closures
⇒ `compile_not_a_seq_hom`). The law is: guards enter as countable CODES + an eval, never as
function payloads. So **every leaf of `Pred` is first-order data** (slot names, `Int` literals,
finite `Int` sets, a `Vk` identifier). A reviewer may grep this file for `→ Bool` / `→ Prop`
FUNCTION payloads inside the `Pred`/`PredList` inductive: there are NONE. The only arrows are the
`evalWith` oracle argument and the eval functions themselves — never stored in the AST.

## The witnessed escape hatch (four-polarity design)

`witnessed (vk : Vk)` is the third-party-discharged claim leaf — the escape hatch a caveat/intent
polarity needs when a fact is proved OUTSIDE this cell (a credential, a finalized cross-cell read).
It carries an opaque IDENTIFIER (`Vk`, a code/key), NOT a function. The first-party evaluator
`eval` FAILS CLOSED on it (a third-party claim has no first-party discharge). To admit it you must
supply a discharge oracle EXPLICITLY to `evalWith` — the oracle is an argument, never embedded in
the tree, so the AST stays first-order and serializable. (Conceptually the oracle is the trusted,
decidable `Verify` side of `Theory.Knowledge`'s verify/find seam, applied to `vk`.)

## Shape note — why `PredList`, not `List Pred`, inside the node

`all`/`any` are n-ary. To keep evaluation STRUCTURAL (so `decide`/`rfl` reduce in the kernel — no
`native_decide` axiom) and `DecidableEq` DERIVABLE, the recursive children live in a mutually
inductive `PredList` (an inlined `List Pred`), not a nested `List Pred` (whose eval falls to
well-founded recursion, which the kernel will not reduce, and for which `deriving DecidableEq` does
not apply at this Lean pin). `PredList ≃ List Pred` is exhibited (`toList`/`ofList` mutually
inverse), and the user-facing constructors `Pred.all`/`Pred.any` take a genuine `List Pred`, so the
serializable API and the Boolean laws are stated over real lists (`List.all`/`List.any`).

## Faithfulness

The atoms transcribe the SHAPE of breadstuffs' `StateConstraint`/`SimpleConstraint` catalog
(`~/dev/breadstuffs/metatheory/Dregg2/Exec/Program.lean:67+`) — a faithful MINIMAL core:
`fieldEquals` → `eq`, `fieldLe` → `le`, `memberOf` → `memberOf`, `writeOnce` → `writeOnce`,
`monotonic` → `monotone`. Reads are name-keyed and FAIL CLOSED (a missing slot ⇒ the atom is
`false`, except `writeOnce` whose absent-old is the first-write case), mirroring `Value.scalar`.

## Boundary

Core Lean (Init) plus `Pred.HashEqDigest`, whose one import is the leaf cSHAKE256 module
`Theory.Sp800185Cshake256Core` (Init only, no candidate code): the `hashEq` atom evaluates a
hash, and this is the kernel's one executable cSHAKE256. Pred imports no `Compiler` module.
-/
import Pred.HashEqDigest

namespace Minidregg.Pred

/-! ## §1. The state substrate — a name-keyed scalar record, fail-closed reads.

`State` is the concrete record substrate (faithful to breadstuffs' `Value.record`/`Value.scalar`):
a slot is a `String` name, a value is an `Int` scalar, and a read of an absent slot returns `none`
(the fail-closed `Option Int`). `eval` reads OLD and NEW states; the (old, new) pair IS the step. -/

/-- A named slot (a `FieldName` analog). -/
abbrev Slot := String

/-- A state is a name-keyed record of `Int` scalars. Concrete and serializable so the keystone
witnesses are genuine values and `#guard`/`decide` compute on them. -/
structure State where
  /-- The name-keyed scalar cells. -/
  slots : List (Slot × Int)
deriving Repr, DecidableEq

/-- Fail-closed read: the scalar at `k`, or `none` if absent (mirrors `Value.scalar`). -/
def State.get (s : State) (k : Slot) : Option Int :=
  (s.slots.find? (fun p => p.1 == k)).map (·.2)

/-! ### The `hashEq` opening — read from the new state, fail-closed.

The context of a commitment is the cell the step is about. Every policy projection names it
`request/target` (`CanonicalRuntimeProfile.requestSlots`), so the atom reads it there; the slot
names it was given are the field half of the context. -/

/-- The slot carrying the id of the cell a step is about. -/
def hashEqCellSlot : Slot := "request/target"

/-- Fail-closed read of several slots, in order: `none` if any one is absent. -/
def State.getAll (s : State) : List Slot → Option (List Int)
  | [] => some []
  | v :: vs => match s.get v, s.getAll vs with
    | some x, some xs => some (x :: xs)
    | _, _ => none

/-- Two states that read alike read every list of slots alike. -/
theorem State.getAll_congr {s s' : State} (h : ∀ k, s.get k = s'.get k) :
    ∀ vs : List Slot, s.getAll vs = s'.getAll vs
  | [] => rfl
  | v :: vs => by simp only [State.getAll, h v, State.getAll_congr h vs]

/-- The opening of `hashEq values blinder commit` on a state: `none` if the cell, any value or the
blinder is absent, or the encoding's domain is exceeded. -/
def hashEqOpening (s : State) (values : List Slot) (blinder commit : Slot) :
    Option HashEqDigest.Opening :=
  match s.get hashEqCellSlot, s.getAll values, s.get blinder with
  | some cell, some xs, some r =>
      let o : HashEqDigest.Opening := ⟨cell, values, blinder, commit, xs, r⟩
      if o.Admissible then some o else none
  | _, _, _ => none

/-- The `hashEq` decision under a hash `H`: the opening exists, the commit slot is present, and it
holds the opening's digest. The deployed atom is this at `HashEqDigest.deployed`. -/
def hashEqHolds (H : Theory.HashBytes.Hash) (s : State) (values : List Slot) (blinder commit : Slot) :
    Bool :=
  match hashEqOpening s values blinder commit, s.get commit with
  | some o, some c => decide (HashEqDigest.digestWith H o = c)
  | _, _ => false

/-! ## §2. The witnessed leaf's identifier — a code/key, NOT a function.

`Vk` is an opaque IDENTIFIER (a verification-key / claim code). It is the ONLY thing the
`witnessed` leaf carries, which is what keeps the AST first-order: a third-party claim is named
by a code and discharged by an oracle passed to `evalWith`, never by a closure in the tree. -/

/-- An opaque claim/verification-key identifier for a third-party-discharged `witnessed` leaf. -/
structure Vk where
  /-- The identifier code (a content-address / verification-key string). -/
  id : String
deriving Repr, DecidableEq

/-- The slot the resource controller projects when a command's writes were checked by
re-executing the program whose `programId` value is `program` (`Kernel.Run`):
`run/program/<decimal id>` holds `1`. No cell field, request or content projection is
named under `run/`; only the controller writes this namespace. -/
def ranSlot (program : Nat) : Slot := "run/program/" ++ toString program

/-- Beside `ranSlot`, the evaluator the checked run was re-executed on (K-EVAL, EVAL
§1.4): `run/evaluator/<decimal evaluator id>` holds `1`. The law atom stays `ran P`
(the program's id already covers its evaluator); a room that wants one evaluator only
says so with `eq (evaluatorSlot id) 1`. Absent that leaf, any registered, enabled
evaluator is admitted. -/
def evaluatorSlot (evaluator : Nat) : Slot := "run/evaluator/" ++ toString evaluator

/-- The slot naming the Objective method artifact that produced a command's writes
(`Kernel.DeclaredResourceController.objectiveSlots`). The controller projects it FIRST in
every invocation's law state and always: the claimed artifact's identity
(`ObjectiveBendSourceArtifact.identity`, which commits the package, the declaration and the
typed core) when the command carries an Objective claim, and `-1`, which is never an identity,
when it does not. Being first, no later projection can shadow it (`State.get` reads the first
occurrence). Acceptance requires that the executed artifact IS the claimed one
(`AcceptedInvocation.objective_artifact_slot_sound`), so a law reading this slot reads which
code produced the writes. -/
def objectiveArtifactSlot : Slot := "objective/artifact"

/-! ## §3. The AST — the ONE predicate algebra.

Decidable atoms over named slots + the Boolean closure (`not`/`all`/`any`) + the `witnessed`
escape hatch. EVERY payload is first-order data — no `→ Bool` / `→ Prop` function anywhere. -/

mutual
/-- **`Pred`** — the ONE predicate algebra, a first-order syntactic AST over an (old, new) step.

Atoms (fail-closed on absent slots): `eq`/`le`/`memberOf`/`monotone` read `new` (`monotone` also
`old`); `writeOnce` reads both. Boolean closure: `not`/`allL`/`anyL` (the latter two over the
inlined `PredList`; use the list-facing smart constructors `Pred.all`/`Pred.any`). Escape hatch:
`witnessed vk`, a third-party claim named by an opaque code, discharged only under an oracle. -/
inductive Pred where
  /-- `new[slot] = value`. -/
  | eq        (slot : Slot) (value : Int)
  /-- `new[slot] ≤ value`. -/
  | le        (slot : Slot) (value : Int)
  /-- `new[slot] ∈ set` (membership in a finite `Int` set). -/
  | memberOf  (slot : Slot) (set : List Int)
  /-- Write-once / register-once: absent-old or `old[slot] = 0` ⇒ any; else `new[slot] = old[slot]`. -/
  | writeOnce (slot : Slot)
  /-- Monotone: `old[slot] ≤ new[slot]` (append-only counter). -/
  | monotone  (slot : Slot)
  /-- Slot-to-slot equality: `new[a] = new[b]`, both present. -/
  | eqSlots   (a b : Slot)
  /-- Slot-to-slot order: `new[a] ≤ new[b]`, both present. -/
  | leSlots   (a b : Slot)
  /-- Slot-to-slot order with a constant offset: `new[a] ≤ new[b] + k`, both present. -/
  | leSlotsOff (a b : Slot) (k : Int)
  /-- **Sum equality**: `Σ new[l] for l ∈ left = Σ new[r] for r ∈ right`, every named slot present
  (fails closed on any absent one). An empty side sums to `0`; a slot named twice counts twice.
  `sumEq [reserve] [a/balance, b/balance]` is "the reserve backs every balance". -/
  | sumEq     (left right : List Slot)
  /-- **The escape hatch** — a third-party-discharged claim named by the opaque code `vk`.
  First-party `eval` FAILS CLOSED; admission requires an explicit oracle via `evalWith`. -/
  | witnessed (vk : Vk)
  /-- **Commit–reveal of a tuple**: `new[commit]` is the cSHAKE256 digest of the opening
  (`request/target`, the slot names, `new[v]` for each value slot `v` in order, `new[blinder]`);
  see `Pred.HashEqDigest`. One commitment opens every value slot at once. Fails closed on any
  absent slot or out-of-domain value. -/
  | hashEq    (values : List Slot) (blinder commit : Slot)
  /-- **`ran program`** — this step's writes ARE the product of the Nock program
  `program` (its `programId` value), re-executed by the kernel on its own sample
  (NOCK §2.4). A first-party read of the controller-projected `ranSlot program`
  (`= 1`), not an oracle: re-execution is a controller fact the policy consumes. -/
  | ran       (program : Nat)
  /-- Boolean negation. -/
  | not       (p : Pred)
  /-- Conjunction over the inlined child list (raw constructor; prefer `Pred.all`). -/
  | allL      (ps : PredList)
  /-- Disjunction over the inlined child list (raw constructor; prefer `Pred.any`). -/
  | anyL      (ps : PredList)
/-- An inlined `List Pred` (mutually inductive with `Pred`) — the recursive-child carrier that
keeps evaluation structural and `DecidableEq` derivable. `PredList ≃ List Pred` (see `toList`). -/
inductive PredList where
  /-- Empty. -/
  | nil
  /-- Cons. -/
  | cons (p : Pred) (ps : PredList)
end

deriving instance Repr for Pred, PredList
deriving instance DecidableEq for Pred, PredList

/-- Forget the inlining: `PredList → List Pred`. -/
def PredList.toList : PredList → List Pred
  | .nil       => []
  | .cons p ps => p :: ps.toList

/-- Re-inline: `List Pred → PredList`. -/
def PredList.ofList : List Pred → PredList
  | []      => .nil
  | p :: ps => .cons p (PredList.ofList ps)

/-- A standalone (non-mutual) structural eliminator for `PredList`: the `induction` tactic does
not apply to a mutually-inductive type, so this single-type recursor (recursing on the child list
alone) is provided for proofs/definitions by recursion on a `PredList`. -/
def PredList.rec' {motive : PredList → Sort _} (nil : motive .nil)
    (cons : (p : Pred) → (ps : PredList) → motive ps → motive (.cons p ps)) :
    (ps : PredList) → motive ps
  | .nil       => nil
  | .cons p ps => cons p ps (PredList.rec' nil cons ps)

/-- `toList ∘ ofList = id` — the list view is faithful. -/
@[simp] theorem PredList.toList_ofList (l : List Pred) : (PredList.ofList l).toList = l := by
  induction l with
  | nil => rfl
  | cons p ps ih => simp only [PredList.ofList, PredList.toList, ih]

/-- `ofList ∘ toList = id` — the inlining loses nothing (so `PredList ≃ List Pred`). -/
@[simp] theorem PredList.ofList_toList (ps : PredList) : PredList.ofList ps.toList = ps := by
  induction ps using PredList.rec' with
  | nil => rfl
  | cons p rest ih => simp only [PredList.toList, PredList.ofList, ih]

/-- **`Pred.all`** — the list-facing n-ary conjunction (empty ⇒ `true`). The serializable API. -/
def Pred.all (ps : List Pred) : Pred := .allL (PredList.ofList ps)

/-- **`Pred.any`** — the list-facing n-ary disjunction (empty ⇒ `false`). The serializable API. -/
def Pred.any (ps : List Pred) : Pred := .anyL (PredList.ofList ps)

/-! ## §4. The discharge oracle — an ARGUMENT, never a field.

The oracle is how a `witnessed` claim gets discharged. It lives OUTSIDE the AST: it is a parameter
of `evalWith`. This is the whole point of the escape hatch being an identifier rather than a
closure — the tree stays first-order and serializable; only evaluation consults a discharger. -/

/-- A discharge oracle: given a claim code and the (old, new) step, did a third party discharge it?
Passed EXPLICITLY to `evalWith`; NEVER stored in a `Pred`. -/
abbrev Oracle := Vk → State → State → Bool

/-- The fail-closed oracle: no third-party claim is discharged. The first-party `eval` uses it. -/
def failClosed : Oracle := fun _ _ _ => false

/-! ## §5. Evaluation — decidable `Bool`, STRUCTURAL over the AST (so the kernel reduces it).

`evalWith` is the general evaluator (takes an oracle); the mutual `evalWith{All,Any}` recurse
structurally through `PredList`. `eval` is the first-party fragment: `evalWith failClosed`. -/

/-- The sum of `state`'s values at `slots`, or `none` when any is absent (`sumEq`'s operand). -/
def sumOf (state : State) : List Slot → Option Int
  | [] => some 0
  | slot :: rest => do
    let x ← state.get slot
    let y ← sumOf state rest
    pure (x + y)

/-- `sumOf` is `some` of the sum exactly when every slot is present. -/
theorem sumOf_eq_some (state : State) (slots : List Slot) (total : Int) :
    sumOf state slots = some total ↔
      ∃ values : List Int, slots.mapM state.get = some values ∧ values.sum = total := by
  induction slots generalizing total with
  | nil => simp [sumOf, eq_comm]
  | cons slot rest ih =>
    simp only [sumOf, List.mapM_cons, Option.bind_eq_bind, Option.bind_eq_some_iff,
      Option.pure_def, Option.some.injEq]
    constructor
    · rintro ⟨x, hx, y, hy, rfl⟩
      obtain ⟨values, hv, rfl⟩ := (ih y).mp hy
      exact ⟨x :: values, ⟨x, hx, values, hv, rfl⟩, by simp⟩
    · rintro ⟨_, ⟨x, hx, values, hv, rfl⟩, rfl⟩
      exact ⟨x, hx, values.sum, (ih _).mpr ⟨values, hv, rfl⟩, by simp⟩

/-- `sumOf` reads the state only through `get`. -/
theorem sumOf_congr {s s' : State} (h : ∀ k, s.get k = s'.get k) (slots : List Slot) :
    sumOf s slots = sumOf s' slots := by
  induction slots with
  | nil => rfl
  | cons slot rest ih => simp only [sumOf, h, ih]

mutual
  /-- The general evaluator: a decidable `Bool` reading of the AST against an (old, new) step,
  with `witnessed` discharged by the supplied oracle `O`. Every atom fails closed on absent slots. -/
  def evalWith (O : Oracle) (p : Pred) (old new : State) : Bool :=
    match p with
    | .eq s v        => decide (new.get s = some v)
    | .le s v        => match new.get s with
                        | some x => decide (x ≤ v)
                        | none   => false
    | .memberOf s xs => match new.get s with
                        | some x => xs.contains x
                        | none   => false
    | .writeOnce s   => match old.get s with
                        | none   => true
                        | some o => o == 0 || decide (new.get s = some o)
    | .monotone s    => match old.get s, new.get s with
                        | some o, some n => decide (o ≤ n)
                        | _,      _      => false
    | .eqSlots a b   => match new.get a, new.get b with
                        | some x, some y => decide (x = y)
                        | _,      _      => false
    | .leSlots a b   => match new.get a, new.get b with
                        | some x, some y => decide (x ≤ y)
                        | _,      _      => false
    | .leSlotsOff a b k => match new.get a, new.get b with
                        | some x, some y => decide (x ≤ y + k)
                        | _,      _      => false
    | .sumEq l r     => match sumOf new l, sumOf new r with
                        | some x, some y => decide (x = y)
                        | _,      _      => false
    | .witnessed vk  => O vk old new
    | .hashEq vs b c => hashEqHolds HashEqDigest.deployed new vs b c
    | .ran program   => decide (new.get (ranSlot program) = some 1)
    | .not q         => !(evalWith O q old new)
    | .allL ps       => evalWithAll O ps old new
    | .anyL ps       => evalWithAny O ps old new
  /-- Conjunction fold over `PredList` (empty ⇒ `true`). -/
  def evalWithAll (O : Oracle) (ps : PredList) (old new : State) : Bool :=
    match ps with
    | .nil        => true
    | .cons q rest => evalWith O q old new && evalWithAll O rest old new
  /-- Disjunction fold over `PredList` (empty ⇒ `false`). -/
  def evalWithAny (O : Oracle) (ps : PredList) (old new : State) : Bool :=
    match ps with
    | .nil        => false
    | .cons q rest => evalWith O q old new || evalWithAny O rest old new
end

/-- **`eval`** — the first-party fragment: `witnessed` fails closed (no oracle). -/
def eval (p : Pred) (old new : State) : Bool :=
  evalWith failClosed p old new

/-! ## §6. The Boolean structure — `not`/`all`/`any` denote `!`/`List.all`/`List.any`. -/

/-- The conjunction fold over `ofList l` IS `List.all` of the evaluated children. -/
theorem evalWithAll_ofList (O : Oracle) (l : List Pred) (old new : State) :
    evalWithAll O (PredList.ofList l) old new = l.all (fun q => evalWith O q old new) := by
  induction l with
  | nil => rfl
  | cons q rest ih => simp only [PredList.ofList, evalWithAll, List.all_cons, ih]

/-- The disjunction fold over `ofList l` IS `List.any` of the evaluated children. -/
theorem evalWithAny_ofList (O : Oracle) (l : List Pred) (old new : State) :
    evalWithAny O (PredList.ofList l) old new = l.any (fun q => evalWith O q old new) := by
  induction l with
  | nil => rfl
  | cons q rest ih => simp only [PredList.ofList, evalWithAny, List.any_cons, ih]

/-- `evalWith (not p) = !evalWith p`. -/
@[simp] theorem evalWith_not (O : Oracle) (p : Pred) (old new : State) :
    evalWith O (.not p) old new = !(evalWith O p old new) := by
  simp only [evalWith]

/-- **`evalWith (Pred.all ps) = List.all`** of the evaluated children. -/
@[simp] theorem evalWith_all (O : Oracle) (ps : List Pred) (old new : State) :
    evalWith O (Pred.all ps) old new = ps.all (fun q => evalWith O q old new) := by
  simp only [Pred.all, evalWith, evalWithAll_ofList]

/-- **`evalWith (Pred.any ps) = List.any`** of the evaluated children. -/
@[simp] theorem evalWith_any (O : Oracle) (ps : List Pred) (old new : State) :
    evalWith O (Pred.any ps) old new = ps.any (fun q => evalWith O q old new) := by
  simp only [Pred.any, evalWith, evalWithAny_ofList]

/-- **`eval (not p) = !eval p`** — the first-party Boolean law. -/
theorem eval_not (p : Pred) (old new : State) :
    eval (.not p) old new = !(eval p old new) :=
  evalWith_not failClosed p old new

/-- **`eval (Pred.all ps) = List.all`** — the first-party Boolean law. -/
theorem eval_all (ps : List Pred) (old new : State) :
    eval (Pred.all ps) old new = ps.all (fun q => eval q old new) :=
  evalWith_all failClosed ps old new

/-- **`eval (Pred.any ps) = List.any`** — the first-party Boolean law. -/
theorem eval_any (ps : List Pred) (old new : State) :
    eval (Pred.any ps) old new = ps.any (fun q => eval q old new) :=
  evalWith_any failClosed ps old new

/-- **The package pin clause**: the step's writes are the product of one of the named
Objective method artifacts (`objectiveArtifactSlot`). A command without an Objective claim reads
`-1` there and is refused; installed on an object's state cells, the clause makes the object's
package pin a law that the ordinary resource route cannot bypass. -/
def objectivePin (artifacts : List Nat) : Pred :=
  .memberOf objectiveArtifactSlot (artifacts.map Int.ofNat)

/-- The pin accepts exactly the steps whose artifact slot names a pinned artifact. -/
theorem eval_objectivePin (artifacts : List Nat) (old new : State) :
    eval (objectivePin artifacts) old new = true ↔
      ∃ a ∈ artifacts, new.get objectiveArtifactSlot = some (Int.ofNat a) := by
  unfold eval objectivePin
  simp only [evalWith]
  cases new.get objectiveArtifactSlot with
  | none => simp
  | some x =>
      simp only [List.contains_iff_mem, List.mem_map, Option.some.injEq]
      constructor
      · rintro ⟨a, member, rfl⟩; exact ⟨a, member, rfl⟩
      · rintro ⟨a, member, rfl⟩; exact ⟨a, member, rfl⟩

/-- An unclaimed step (the slot reads `-1`) is refused by every pin. -/
theorem objectivePin_refuses_unclaimed (artifacts : List Nat) (old new : State)
    (unclaimed : new.get objectiveArtifactSlot = some (-1)) :
    eval (objectivePin artifacts) old new = false := by
  cases accepts : eval (objectivePin artifacts) old new with
  | false => rfl
  | true =>
      obtain ⟨a, _, read⟩ := (eval_objectivePin artifacts old new).mp accepts
      rw [unclaimed] at read
      cases read

/-- **Pin teeth**: a step naming artifact 7 passes the pin `[7]`, the same step fails the pin
`[8]`, and an unclaimed step fails both. -/
theorem objectivePin_teeth :
    eval (objectivePin [7]) ⟨[]⟩ ⟨[(objectiveArtifactSlot, 7)]⟩ = true ∧
      eval (objectivePin [8]) ⟨[]⟩ ⟨[(objectiveArtifactSlot, 7)]⟩ = false ∧
      eval (objectivePin [7, 8]) ⟨[]⟩ ⟨[(objectiveArtifactSlot, -1), (objectiveArtifactSlot, 7)]⟩ = false := by
  decide +kernel

/-! ## §7. The KEYSTONE — non-vacuity + teeth (ATLAS design-law 2).

A keystone that cannot exhibit both poles does not compile. We do NOT assert non-vacuity; we
BUILD the witnesses (the 2026-08-07 audit-discipline lesson): a concrete satisfying step, a
concrete state pair where a specific atom fires TRUE, and a hostile pair where the SAME atom fires
FALSE — so the atoms genuinely decide (they are neither vacuously true nor constant), each
discharged by `decide` so the decidability is a KERNEL computation, not a claim. -/

/-- A pre-state: `x = 3`, `y = 10`. -/
def sX3 : State := ⟨[("x", 3), ("y", 10)]⟩

/-- A post-state: `x = 5`, `y = 10` (x grew). -/
def sX5 : State := ⟨[("x", 5), ("y", 10)]⟩

/-- A compound policy exercising every closure and four atoms:
`y` pinned to 10, `x ≤ 5`, `x ∈ {3,5,7}`, and `x` monotone across the step. -/
def demoPred : Pred :=
  Pred.all [.eq "y" 10, .le "x" 5, .memberOf "x" [3, 5, 7], .monotone "x"]

/-- **Satisfiable** (non-vacuity): the algebra ACCEPTS a concrete step (`sX3 → sX5`). Built,
not asserted — `decide` runs the evaluator to `true`. -/
theorem demo_satisfiable : eval demoPred sX3 sX5 = true := by decide

/-- **Hostile pole**: on the SWAPPED (hostile) step `sX5 → sX3`, `x` decreases, so `monotone`
fails and the whole conjunction REJECTS — the same policy discriminates. -/
theorem demo_rejects_hostile : eval demoPred sX5 sX3 = false := by decide

/-- **Tooth — fires TRUE**: `monotone "x"` on `sX3 → sX5` (3 ≤ 5). -/
theorem monotone_tooth_fires : eval (.monotone "x") sX3 sX5 = true := by decide

/-- **Tooth — refuses on the hostile pair**: the SAME atom `monotone "x"` on the swapped step
`sX5 → sX3` (5 ≤ 3 is false). One atom, both poles: genuine decision, not a vacuous constant. -/
theorem monotone_tooth_refuses : eval (.monotone "x") sX5 sX3 = false := by decide

/-- **Witnessed escape-hatch tooth — first party fails closed**: with no oracle, a third-party
claim is refused. -/
theorem witnessed_firstparty_refuses : eval (.witnessed ⟨"vk-1"⟩) sX3 sX5 = false := by decide

/-- **Witnessed escape-hatch tooth — a granting oracle discharges it**: the SAME AST leaf admits
under a discharging oracle supplied to `evalWith`. The oracle toggles the outcome and is never in
the tree — exactly the escape hatch's design. -/
theorem witnessed_discharged_fires :
    evalWith (fun _ _ _ => true) (.witnessed ⟨"vk-1"⟩) sX3 sX5 = true := by decide

/-- **`ran` tooth — fires** on a step whose projection names the checked run. -/
theorem ran_tooth_fires : eval (.ran 7) sX3 ⟨[(ranSlot 7, 1)]⟩ = true := by decide +kernel

/-- **`ran` tooth — refuses** the same step without the projection, and a run of a
different program. -/
theorem ran_tooth_refuses :
    eval (.ran 7) sX3 sX5 = false ∧ eval (.ran 8) sX3 ⟨[(ranSlot 7, 1)]⟩ = false := by
  decide +kernel

/-- **The keystone** (ATLAS design-law 2): the algebra is non-vacuous (a concrete step is
accepted) AND a single atom exhibits BOTH poles (fires on one step, refuses on the hostile one)
AND the witnessed escape hatch genuinely toggles (fail-closed vs. discharged). All fields are
BUILT witnesses, discharged by `decide`. -/
def keystone : Prop :=
  (∃ old new, eval demoPred old new = true) ∧          -- satisfiable (non-vacuous)
  (eval (.monotone "x") sX3 sX5 = true) ∧              -- tooth fires
  (eval (.monotone "x") sX5 sX3 = false) ∧             -- SAME atom, hostile pair refuses
  (eval (.witnessed ⟨"vk-1"⟩) sX3 sX5 = false) ∧       -- escape hatch: first-party fail-closed
  (evalWith (fun _ _ _ => true) (.witnessed ⟨"vk-1"⟩) sX3 sX5 = true)  -- discharged by oracle

/-- The keystone holds — witnesses supplied, not asserted. -/
theorem keystone_holds : keystone := by
  refine ⟨⟨sX3, sX5, ?_⟩, ?_, ?_, ?_, ?_⟩ <;> decide

/-! ## §8. Genuine decidability — the evaluator and the derived `DecidableEq` decide
concrete instances beyond §7, as named kernel-checked theorems. -/

-- The demo step, the monotone tooth and the witnessed escape hatch are the theorems of §7.
-- fail-closed reads: absent slot ⇒ atom false
theorem eval_eq_absent : eval (.eq "absent" 0) sX3 sX5 = false := by decide
theorem eval_le_absent : eval (.le "absent" 99) sX3 sX5 = false := by decide
-- write-once: absent old ⇒ first write admitted; changing a set nonzero value ⇒ refused
theorem eval_writeOnce_first : eval (.writeOnce "x") ⟨[]⟩ sX5 = true := by decide
theorem eval_writeOnce_change : eval (.writeOnce "x") sX3 sX5 = false := by decide
-- membership atom, both poles
theorem eval_memberOf_in : eval (.memberOf "x" [3, 5, 7]) sX3 sX5 = true := by decide
theorem eval_memberOf_out : eval (.memberOf "x" [1, 2]) sX3 sX5 = false := by decide

/-- **What `sumEq` decides**: every slot on both sides is present in the new state, and the two
sides' values sum to the same integer. -/
theorem eval_sumEq (left right : List Slot) (old new : State) :
    eval (.sumEq left right) old new = true ↔
      ∃ xs ys : List Int, left.mapM new.get = some xs ∧ right.mapM new.get = some ys ∧
        xs.sum = ys.sum := by
  simp only [eval, evalWith]
  constructor
  · intro h
    split at h
    · rename_i x y hx hy
      obtain ⟨xs, hxs, rfl⟩ := (sumOf_eq_some _ _ _).mp hx
      obtain ⟨ys, hys, rfl⟩ := (sumOf_eq_some _ _ _).mp hy
      exact ⟨xs, ys, hxs, hys, of_decide_eq_true h⟩
    · exact absurd h (by simp)
  · rintro ⟨xs, ys, hxs, hys, hsum⟩
    rw [(sumOf_eq_some _ _ _).mpr ⟨xs, hxs, rfl⟩, (sumOf_eq_some _ _ _).mpr ⟨ys, hys, rfl⟩]
    exact decide_eq_true hsum

/-- A reserve of 8 backs balances 3 + 5; a reserve of 8 does not back 3 + 6; an absent balance
backs nothing. -/
theorem sumEq_backs : eval (.sumEq ["r"] ["a", "b"]) ⟨[]⟩ ⟨[("r", 8), ("a", 3), ("b", 5)]⟩ = true := by
  decide
theorem sumEq_minted : eval (.sumEq ["r"] ["a", "b"]) ⟨[]⟩ ⟨[("r", 8), ("a", 3), ("b", 6)]⟩ = false := by
  decide
theorem sumEq_absent : eval (.sumEq ["r"] ["a", "b"]) ⟨[]⟩ ⟨[("r", 3), ("a", 3)]⟩ = false := by
  decide
-- the derived DecidableEq on the AST decides syntactic equality:
theorem pred_eq_self : decide (demoPred = demoPred) = true := by decide
theorem pred_eq_distinct_const : decide (Pred.eq "x" 5 = Pred.eq "x" 6) = false := by decide
theorem pred_witnessed_distinct :
    decide (Pred.witnessed ⟨"a"⟩ = Pred.witnessed ⟨"b"⟩) = false := by decide

/-- The derived `DecidableEq Pred` is exercised by the kernel too. -/
example : (demoPred = demoPred) := by decide

/-- Distinct atoms are decidably distinct. -/
example : (Pred.eq "x" 5 ≠ Pred.eq "x" 6) := by decide

end Minidregg.Pred

/-- info: 'Minidregg.Pred.ran_tooth_fires' depends on axioms: [propext, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms Minidregg.Pred.ran_tooth_fires
/-- info: 'Minidregg.Pred.ran_tooth_refuses' depends on axioms: [propext, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms Minidregg.Pred.ran_tooth_refuses
