/- The composition contract of an Objective Bend specification chain (GPT-6 row D).

A layer of `fix(compose(L₁, …, Lₙ), seed)` makes three kinds of claim about rows:

* `assumes`  — members it reads from the FINAL self `S` (its `Self has {...}` bound and its
  `requires`), at the types it reads them;
* `consumes` — members it reads from the row BENEATH it (`Super has {...}`);
* `provides` — the members it defines.

`F_L(S, I) = provides ++ I` is the row a layer leaves (the first entry of a name wins, as Core4
`overlay` after `extend`), and its contract is `C_L(S, I) = assumes ⊆ S ∧ consumes ⊆ I ∧
no provided member changes the type of a member of I`. The contract of a composition is

    C_{A;B}(S, I) = C_A(S, I) ∧ C_B(S, F_A(S, I)),    F_{A;B}(S, I) = F_B(S, F_A(S, I)),

which is `run_append` below. `discharge` is that contract checked at `fix`: thread the seed
through every layer, then require the final row to be exactly the final self. The elaborator's
`chainFix` decides every one of its contract refusals by calling `checkLayer` and `close` here,
so the theorems are about the checks that run.

Rows are lists of `(name, type)`; the elaborator passes canonical types, so `==` on a type is
the elaborator's `sameTy`. -/
import Theory.AssertAxioms
namespace Minidregg.Compiler.ObjectiveBendContract
set_option autoImplicit false

abbrev Row (τ : Type) := List (String × τ)

variable {τ : Type} [BEq τ]

/-- The type a row gives `name`: its first entry of that name. -/
def get? (row : Row τ) (name : String) : Option τ :=
  (row.find? (·.1 == name)).map (·.2)

/-- The members of `required` that `actual` lacks or has at another type. -/
def missing (actual required : Row τ) : List String :=
  required.filterMap fun (n, t) => if get? actual n == some t then none else some n

/-- The members a layer provides at a type other than the one the row beneath gives them:
a REPLACEMENT. An addition (absent beneath) and an override (same type) are not listed. -/
def replaced (beneath provides : Row τ) : List String :=
  provides.filterMap fun (n, t) => match get? beneath n with
    | some t' => if t' == t then none else some n
    | none => none

structure Layer (τ : Type) where
  name : String
  assumes : Row τ
  consumes : Row τ
  provides : Row τ
  /-- A layer whose result row is exactly `provides` (an extension declaring its whole result
  type), rather than `provides` over the row beneath (a specification's methods). -/
  whole : Bool := false

/-- The named refusals of a composition contract. The elaborator renders each with the text
the `refused (...)` cohort rows pin. -/
inductive Refusal where
  | selfBound (layer : String) (missing : List String)
  | inheritedUnprovided (layer : String) (missing beneath : List String)
  | replaceUndeclared (layer : String) (members : List String)
  | requiresUnprovided (missing : List String)
  | seedExtra (extra : List String)
  | providedMismatch
  deriving Repr, BEq

/-- `F_L(S, I)`. -/
def Layer.leaves (layer : Layer τ) (beneath : Row τ) : Row τ :=
  if layer.whole then layer.provides else layer.provides ++ beneath

/-- The clauses of `C_L(S, I)` about what the layer READS: its assumptions about the final self,
then what it consumes from the row beneath. -/
def checkBounds (self beneath : Row τ) (layer : Layer τ) : Except Refusal Unit :=
  let unmetSelf := missing self layer.assumes
  if !unmetSelf.isEmpty then .error (.selfBound layer.name unmetSelf) else
  let unmetSuper := missing beneath layer.consumes
  if !unmetSuper.isEmpty then .error (.inheritedUnprovided layer.name unmetSuper (beneath.map (·.1))) else
  .ok ()

/-- The clause of `C_L(S, I)` about what the layer WRITES: an addition needs the member absent
beneath, an override needs it at the same type, and a type change is a replacement, which no
source form declares, so it is refused by name. On success, `F_L(S, I)`. -/
def checkProvides (beneath : Row τ) (layer : Layer τ) : Except Refusal (Row τ) :=
  let changed := replaced beneath layer.provides
  if !changed.isEmpty then .error (.replaceUndeclared layer.name changed) else
  .ok (layer.leaves beneath)

/-- `C_L(S, I)`, deciding which clause fails first; on success, `F_L(S, I)`. -/
def checkLayer (self beneath : Row τ) (layer : Layer τ) : Except Refusal (Row τ) :=
  (checkBounds self beneath layer).bind fun _ => checkProvides beneath layer

/-- The chain's contract threaded from `seed`: the row every layer leaves, or the first refusal. -/
def run (self : Row τ) : Row τ → List (Layer τ) → Except Refusal (Row τ)
  | beneath, [] => .ok beneath
  | beneath, layer :: rest => (checkLayer self beneath layer).bind fun next => run self next rest

/-- The final row against the final self: exact, else what is missing, else what is extra,
else a type mismatch. `names` lists a row's member names without repetition. -/
def names (row : Row τ) : List String := (row.map (·.1)).eraseDups

def close (self final : Row τ) : Except Refusal Unit :=
  if missing final self |>.isEmpty then
    if (names final).all (fun n => (get? self n).isSome) then .ok ()
    else .error (.seedExtra ((names final).filter fun n => (get? self n).isNone))
  else
    let absent := (names self).filter fun n => (get? final n).isNone
    if !absent.isEmpty then .error (.requiresUnprovided absent)
    else
      let extra := (names final).filter fun n => (get? self n).isNone
      if !extra.isEmpty then .error (.seedExtra extra) else .error .providedMismatch

/-- The composition contract discharged at `fix`. -/
def discharge (self seed : Row τ) (chain : List (Layer τ)) : Except Refusal Unit :=
  (run self seed chain).bind (close self)

/-! ## The composition law -/

/-- **`C_{A;B}(S,I) = C_A(S,I) ∧ C_B(S, F_A(S,I))` and `F_{A;B} = F_B ∘ F_A`**: checking the
composition of two chains is checking the first from the seed, then the second from the row the
first leaves. Associativity of composition is therefore the associativity of `++` on chains:
`run_assoc`. -/
theorem run_append (self : Row τ) (seed : Row τ) (first second : List (Layer τ)) :
    run self seed (first ++ second) = (run self seed first).bind fun mid => run self mid second := by
  induction first generalizing seed with
  | nil => rfl
  | cons layer rest ih =>
    simp only [List.cons_append, run]
    cases checkLayer self seed layer with
    | error _ => rfl
    | ok next => exact ih next

theorem run_assoc (self seed : Row τ) (a b c : List (Layer τ)) :
    run self seed ((a ++ b) ++ c) = run self seed (a ++ (b ++ c)) := by
  rw [List.append_assoc]

/-- An admitted layer met every clause of its contract, and left `F_L(S, I)`. -/
theorem checkLayer_ok {self beneath next : Row τ} {layer : Layer τ}
    (admitted : checkLayer self beneath layer = .ok next) :
    missing self layer.assumes = [] ∧ missing beneath layer.consumes = [] ∧
      replaced beneath layer.provides = [] ∧ next = layer.leaves beneath := by
  unfold checkLayer checkBounds checkProvides at admitted
  by_cases a : (missing self layer.assumes).isEmpty
  · by_cases b : (missing beneath layer.consumes).isEmpty
    · by_cases r : (replaced beneath layer.provides).isEmpty
      · simp only [a, b, r, Bool.not_true, Bool.false_eq_true, if_false, Except.bind] at admitted
        cases admitted
        exact ⟨List.isEmpty_iff.mp a, List.isEmpty_iff.mp b, List.isEmpty_iff.mp r, rfl⟩
      · simp [a, b, r, Except.bind] at admitted
    · simp [a, b, Except.bind] at admitted
  · simp [a, Except.bind] at admitted

theorem missing_nil_get {actual required : Row τ} (h : missing actual required = []) :
    ∀ n t, (n, t) ∈ required → get? actual n == some t := by
  intro n t mem
  unfold missing at h
  have := List.filterMap_eq_nil_iff.mp h (n, t) mem
  by_cases e : (get? actual n == some t) = true
  · exact e
  · simp [e] at this

/-- A discharged composition: every layer's assumptions hold in the final self, and the row the
chain leaves gives every member of the final self its declared type and declares nothing else. -/
theorem discharge_ok {self seed : Row τ} {chain : List (Layer τ)}
    (admitted : discharge self seed chain = .ok ()) :
    ∃ final, run self seed chain = .ok final ∧
      (∀ n t, (n, t) ∈ self → get? final n == some t) ∧
      (∀ n, n ∈ names final → (get? self n).isSome) := by
  unfold discharge at admitted
  cases h : run self seed chain with
  | error e => rw [h] at admitted; cases admitted
  | ok final =>
    rw [h] at admitted
    refine ⟨final, rfl, ?_⟩
    simp only [Except.bind] at admitted
    unfold close at admitted
    by_cases m : (missing final self).isEmpty
    · simp only [m, if_true] at admitted
      by_cases x : (names final).all (fun n => (get? self n).isSome)
      · refine ⟨missing_nil_get (List.isEmpty_iff.mp m), fun n mem => ?_⟩
        exact (List.all_eq_true.mp x) n mem
      · simp [x] at admitted
    · revert admitted
      simp only [m, Bool.false_eq_true, if_false]
      split <;> (try split) <;> simp

#assert_axioms run_append run_assoc checkLayer_ok missing_nil_get discharge_ok

end Minidregg.Compiler.ObjectiveBendContract
