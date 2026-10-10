import Lean
namespace Minidregg.Theory.ObjectiveBendTypes
set_option autoImplicit false

/-- Quantities are obligations of this edition. -/
inductive Quantity where
  | erased | affine | linear | unrestricted
  deriving Repr, DecidableEq
inductive Reuse where
  | once | reusable
  deriving Repr, DecidableEq

/-- Rigid variables stand for future self/super types. A row tail is retained,
not flattened to the currently known methods. Ordinary arrows and scalar targets
are first-class. This is an annotated equality/row fragment, not general F-sub. -/
inductive Ty where
  | natural | label | boolean
  | variable (index : Nat)
  | arrow (reuse : Reuse) (parameter : Quantity) (domain codomain : Ty)
  | emptyRow
  | field (name : String) (member tail : Ty)
  | specification (metadata extension : Ty)
  | prototype (specification target : Ty)
  | custody (identity : Nat)
  /-- A sum over the labels of an ordinary field row. A `.emptyRow` tail is a
  closed (exhaustively eliminable) sum; a variable tail is an open sum. -/
  | variant (row : Ty)
  /-- An activity: a computation that may yield Plans of type `plan`, is resumed
  with responses of type `response`, and finishes with `result`. Only a direct
  (never suspended) position may hold it: it is not shareable, and every
  cell-allocating typing rule refuses it. Surface: `Activity<Plan, Response, Result>`. -/
  | computation (plan response result : Ty)
  /-- Hosted extension: the universal first-order type, inhabited by any
  well-formed finite data. Only `Term.toData` produces it; Bend has no
  elimination (the host decodes it against a callee's declared type). -/
  | data
  deriving Repr, DecidableEq

/-- A reusable closure is shareable only after its captures have been checked.
Custody is never hidden by a record/prototype/specification wrapper. -/
def Ty.shareable : Ty → Bool
  | .natural | .label | .boolean | .emptyRow => true
  | .variable _ | .custody _ => false
  | .arrow reuse _ _ _ => reuse == .reusable
  | .field _ member tail => member.shareable && tail.shareable
  | .specification metadata extension => metadata.shareable && extension.shareable
  | .prototype spec target => spec.shareable && target.shareable
  | .variant row => row.shareable
  | .computation _ _ _ => false
  | .data => true

/-- Rigid variables may be quantified over shareable future types explicitly.
Every instantiation must discharge this finite premise; an unknown row is never
implicitly pure merely because its currently visible fields are immutable. -/
def Ty.shareableUnder (variables : List Nat) : Ty → Bool
  | .variable index => variables.contains index
  | .field _ member tail => member.shareableUnder variables && tail.shareableUnder variables
  | .specification metadata extension => metadata.shareableUnder variables && extension.shareableUnder variables
  | .prototype spec target => spec.shareableUnder variables && target.shareableUnder variables
  | .variant row => row.shareableUnder variables
  | other => other.shareable

@[simp] theorem Ty.shareableUnder_empty (type : Ty) : type.shareableUnder [] = type.shareable := by
  induction type <;> simp_all [Ty.shareableUnder, Ty.shareable]

/-- The head of an activity type. Only the head is inspected: canonical row
equality preserves it, and bounds never name an activity (`Assumptions.valid`),
so this is invariant under every checked type agreement. -/
def Ty.isComputation : Ty → Bool
  | .computation _ _ _ => true
  | _ => false

/-- Declared bounds are defined below `Ty.lookup`; data admission needs them to
unfold a closed recursive sum, which the elaborator represents as a rigid-free
variable whose bound is the sum's unfolding (`List<T>` is `variable i` with
`bounds i = variant (nil: {}, cons: {head: T, tail: variable i})`). -/
abbrev DataBounds := List (Nat × Ty)

/-- First-order data: what a Plan, a response and a checkpointed reply can be.
No closures, specifications, prototypes, custody and no activities. A variable is
data when it is not rigid and its bound is data under the assumption that the
variable itself (and every variable already being unfolded, `seen`) is data: a
closed recursive sum is a greatest fixed point. `fuel` only bounds the walk. -/
def Ty.isDataUnder (bounds : DataBounds) (rigid : List Nat) : Nat → List Nat → Ty → Bool
  | 0, _, _ => false
  | _ + 1, _, .natural | _ + 1, _, .boolean | _ + 1, _, .label | _ + 1, _, .emptyRow
  | _ + 1, _, .data => true
  | fuel + 1, seen, .field _ member tail =>
      member.isDataUnder bounds rigid fuel seen && tail.isDataUnder bounds rigid fuel seen
  | fuel + 1, seen, .variant row => row.isDataUnder bounds rigid fuel seen
  | fuel + 1, seen, .variable index =>
      if rigid.contains index then false
      else if seen.contains index then true
      else match bounds.lookup index with
        | some bound => bound.isDataUnder bounds rigid fuel (index :: seen)
        | none => false
  | _, _, _ => false

def Ty.dataFuel : Nat := 4096

/-- The constructors of a type. -/
def Ty.size : Ty → Nat
  | .arrow _ _ domain codomain => 1 + domain.size + codomain.size
  | .field _ member tail => 1 + member.size + tail.size
  | .specification metadata extension => 1 + metadata.size + extension.size
  | .prototype spec target => 1 + spec.size + target.size
  | .variant row => 1 + row.size
  | .computation plan response result => 1 + plan.size + response.size + result.size
  | _ => 1

/-- A walk fuel for `isDataUnder` that grows with the type and its bounds, never below
`Ty.dataFuel`. Along any path the walk spends one step per constructor of the type and of
each bound it unfolds, and unfolds a bound at most once (`seen`), so this fuel never runs
out before the walk decides. A value's own shape type (a `Data` literal) is as deep as the
value, so a fixed fuel would refuse a long list that the runtime admits. -/
def Ty.dataFuelFor (bounds : DataBounds) (type : Ty) : Nat :=
  max Ty.dataFuel (type.size + (bounds.map fun (_, bound) => bound.size).sum + 1)

/-- No bounds: the closed, non-recursive first-order types. -/
def Ty.isData (type : Ty) : Bool := type.isDataUnder [] [] Ty.dataFuel []

/-- A Plan is a sum of typed actions over first-order data; a recursive sum
may itself be a Plan. -/
def Ty.isPlanUnder (bounds : DataBounds) (rigid : List Nat) : Ty → Bool
  | .variant row => row.isDataUnder bounds rigid Ty.dataFuel []
  | .variable index =>
      !rigid.contains index &&
      match bounds.lookup index with
      | some (.variant row) => row.isDataUnder bounds rigid Ty.dataFuel [index]
      | _ => false
  | _ => false

def Ty.isPlan : Ty → Bool := Ty.isPlanUnder [] []

theorem Ty.shareable_not_computation (type : Ty) (shareable : type.shareable = true) :
    type.isComputation = false := by
  cases type <;> simp_all [Ty.shareable, Ty.isComputation]

theorem Ty.shareableUnder_not_computation (variables : List Nat) (type : Ty)
    (shareable : type.shareableUnder variables = true) : type.isComputation = false := by
  cases type <;> simp_all [Ty.shareableUnder, Ty.shareable, Ty.isComputation]


/-- Shadowing changes this field only; unknown future tail stays present. -/
def Ty.put (row : Ty) (name : String) (member : Ty) : Ty :=
  match row with
  | .field prior old tail =>
      if prior = name then .field name member tail else .field prior old (tail.put name member)
  | tail => .field name member tail

def Ty.tail : Ty → Ty
  | .field _ _ rest => rest.tail
  | other => other

theorem put_preserves_future_tail (row : Ty) (name : String) (member : Ty) :
    (row.put name member).tail = row.tail := by
  induction row with
  | field prior old rest ih₁ ih₂ =>
    simp only [Ty.put]
    split <;> simp_all [Ty.tail]
  | _ => rfl

/-- Canonical finite named-row equality preserves a rigid unknown tail and
first-field shadowing. It is equality, not width/depth subtyping or a solver. -/
def Ty.insertCanonical (row : Ty) (name : String) (member : Ty) : Ty :=
  match row with
  | .field prior old tail =>
      if name = prior then .field name member tail
      else if name < prior then .field name member row
      else .field prior old (tail.insertCanonical name member)
  | tail => .field name member tail

def Ty.canonical : Ty → Ty
  | .arrow reuse quantity domain codomain => .arrow reuse quantity domain.canonical codomain.canonical
  | .field name member tail => tail.canonical.insertCanonical name member.canonical
  | .specification metadata extension => .specification metadata.canonical extension.canonical
  | .prototype spec target => .prototype spec.canonical target.canonical
  | .variant row => .variant row.canonical
  | .computation plan response result =>
      .computation plan.canonical response.canonical result.canonical
  | other => other

theorem Ty.insertCanonical_not_computation (row : Ty) (name : String) (member : Ty) :
    (row.insertCanonical name member).isComputation = false := by
  cases row <;> simp only [Ty.insertCanonical]
  all_goals repeat' first | split
  all_goals rfl

theorem Ty.canonical_isComputation (type : Ty) : type.canonical.isComputation = type.isComputation := by
  cases type <;> try rfl
  exact Ty.insertCanonical_not_computation _ _ _

/-- Explicit finite bounds disclose the members available on a rigid self/super
variable. Recursive bounds are explored only to the requested finite depth. -/
abbrev Bounds := List (Nat × Ty)
def Ty.lookup (bounds : Bounds) : Nat → Ty → String → Option Ty
  | 0, _, _ => none
  | fuel + 1, .field prior member tail, name =>
      if prior = name then some member else tail.lookup bounds fuel name
  | fuel + 1, .variable index, name => do
      let bound ← bounds.lookup index
      bound.lookup bounds fuel name
  | _, _, _ => none

def Ty.rowMember : Ty → String → Option Ty
  | .field name member tail, query => if name = query then some member else tail.rowMember query
  | _, _ => none

/-- The field count of a closed row (`none` for an open one). -/
def Ty.closedRowCount : Ty → Option Nat
  | .emptyRow => some 0
  | .field _ _ tail => tail.closedRowCount.map (· + 1)
  | _ => none

/-- `List<String>`: a variable whose declared bound is the closed sum
`nil: {} | cons: {head: String, tail: <the variable>}` (in either order). -/
def Ty.isTextList (bounds : Bounds) : Ty → Bool
  | .variable index => match bounds.lookup index with
    | some (.variant row) =>
      row.closedRowCount == some 2 && row.rowMember "nil" == some .emptyRow &&
      match row.rowMember "cons" with
      | some cons => cons.closedRowCount == some 2 && cons.rowMember "head" == some .label &&
          cons.rowMember "tail" == some (.variable index)
      | none => false
    | _ => false
  | _ => false

def Ty.isRow (bounds : Bounds) : Nat → Ty → Bool
  | 0, _ => false
  | _ + 1, .emptyRow => true
  | fuel + 1, .field _ _ tail => tail.isRow bounds fuel
  | fuel + 1, .variable index =>
      match bounds.lookup index with
      | some type => type.isRow bounds fuel
      | none => false
  | _, _ => false

/-- A decidable annotated structural interface check. Fields are looked up in
the actual row/bounds and checked by exact type equality; arbitrary subtyping,
variance, associated-type search and unbounded recursive conversion are absent. -/
def Ty.supports (bounds : Bounds) : Nat → Ty → Ty → Bool
  | 0, _, _ => false
  | fuel + 1, actual, .emptyRow => actual.isRow bounds (fuel + 1)
  | fuel + 1, actual, .field name member tail =>
      actual.lookup bounds (fuel + 1) name == some member && actual.supports bounds fuel tail
  | _ + 1, actual, required => actual == required

def Quantity.fits : Quantity → Nat → Bool
  | .erased, count => count == 0
  | .affine, count => count <= 1
  | .linear, count => count == 1
  | .unrestricted, _ => true

structure Binding where
  type : Ty
  quantity : Quantity
  deriving Repr, DecidableEq
abbrev Context := List Binding
abbrev Uses := List Nat

def zeroUses (context : Context) : Uses := List.replicate context.length 0
def variableUses (context : Context) (index : Nat) : Uses :=
  (List.range context.length).map (fun position => if position = index then 1 else 0)
def addUses (first second : Uses) : Uses := List.zipWith (· + ·) first second

/-- Partial computations may retain a linear obligation forever. Thus this
safety checker enforces at-most-once use; exact discharge is checked separately
for terminal ownership protocols, never inferred from arbitrary recursion. -/
def safeQuantity : Quantity → Nat → Bool
  | .erased, count => count == 0
  | .affine, count | .linear, count => count <= 1
  | .unrestricted, _ => true

def safeUses (context : Context) (uses : Uses) : Bool :=
  uses.length == context.length &&
    (context.zip uses).all (fun pair => safeQuantity pair.1.quantity pair.2)

def reusableCaptures (variables : List Nat) (context : Context) (uses : Uses) : Bool :=
  uses.length == context.length && (context.zip uses).all (fun pair =>
    pair.2 == 0 || (pair.1.quantity == .unrestricted && pair.1.type.shareableUnder variables))

def validContext (variables : List Nat) (context : Context) : Bool :=
  context.all (fun binding => binding.quantity != .unrestricted || binding.type.shareableUnder variables)

/-- No affine/linear binding can occur twice in a checked computation. This
is syntactic safety; machine conservation and terminal discharge are separate. -/
theorem safe_use_bound (context : Context) (uses : Uses) (binding : Binding) (count : Nat)
    (safe : safeUses context uses = true) (member : (binding,count) ∈ context.zip uses)
    (quantity : binding.quantity = .affine ∨ binding.quantity = .linear) : count ≤ 1 := by
  have all := (Bool.and_eq_true_iff.mp safe).2
  have checked := (List.all_eq_true.mp all) (binding,count) member
  rcases quantity with affine | linear
  · simpa [safeQuantity, affine] using checked
  · simpa [safeQuantity, linear] using checked

/-- Every USED reusable capture is both quantity-unrestricted and transitively
shareable under the explicitly checked future-type premises. -/
theorem reusable_capture_member (variables : List Nat) (context : Context) (uses : Uses)
    (binding : Binding) (count : Nat)
    (qualified : reusableCaptures variables context uses = true)
    (member : (binding,count) ∈ context.zip uses) (used : count ≠ 0) :
    binding.quantity = .unrestricted ∧ binding.type.shareableUnder variables = true := by
  have all := (Bool.and_eq_true_iff.mp qualified).2
  have checked := (List.all_eq_true.mp all) (binding,count) member
  simpa [used] using checked

/-- An annotation connects source binders to actual checking. `default` must be
resolved by the source frontend using the type/capture discipline. -/
structure LambdaAnnotation where
  domain : Ty
  codomain : Ty
  parameter : Quantity
  reuse : Reuse
  deriving Repr, DecidableEq

/-- Type substitution instantiates future row/type parameters, including their
negative occurrences in binary methods. No variance/subtype oracle is hidden. -/
def Ty.instantiate (arguments : Nat → Ty) : Ty → Ty
  | .variable index => arguments index
  | .arrow reuse quantity domain codomain =>
      .arrow reuse quantity (domain.instantiate arguments) (codomain.instantiate arguments)
  | .field name member tail => .field name (member.instantiate arguments) (tail.instantiate arguments)
  | .specification metadata extension =>
      .specification (metadata.instantiate arguments) (extension.instantiate arguments)
  | .prototype spec target => .prototype (spec.instantiate arguments) (target.instantiate arguments)
  | .variant row => .variant (row.instantiate arguments)
  | .computation plan response result =>
      .computation (plan.instantiate arguments) (response.instantiate arguments)
        (result.instantiate arguments)
  | other => other

/-- Families are independently authored expressions over future type variables.
`required` is a bound/interface of future Self, not the final closed Self type. -/
structure ExtensionFamilies where
  inherited : Ty
  required : Ty
  provided : Ty
  deriving Repr, DecidableEq

def ExtensionFamilies.functionType (family : ExtensionFamilies) (futureSelf : Ty) : Ty :=
  .arrow .reusable .unrestricted futureSelf
    (.arrow .reusable .unrestricted family.inherited family.provided)

/-- Heterogeneous composition: inherited→middle→provided. Requirements from
both independently authored extensions remain explicit obligations. -/
structure FamilyMix where
  earlier : ExtensionFamilies
  later : ExtensionFamilies
  intermediate : earlier.provided = later.inherited
  required : List Ty := [earlier.required, later.required]

/-- A recursively constrained binary method keeps the future Self parameter in
both argument and result; a future row remains in the provided target. -/
def binaryMethodFamily : ExtensionFamilies :=
  ⟨.variable 1,
    .field "combine" (.arrow .reusable .unrestricted (.variable 0) (.variable 0)) (.variable 2),
    .field "combine" (.arrow .reusable .unrestricted (.variable 0) (.variable 0)) (.variable 1)⟩

theorem binary_method_changes_with_future_self (first second : Ty) :
    (Ty.arrow .reusable .unrestricted (.variable 0) (.variable 0)).instantiate
      (fun _ => first) = Ty.arrow .reusable .unrestricted first first ∧
    (Ty.arrow .reusable .unrestricted (.variable 0) (.variable 0)).instantiate
      (fun _ => second) = Ty.arrow .reusable .unrestricted second second := ⟨rfl, rfl⟩

end Minidregg.Theory.ObjectiveBendTypes
