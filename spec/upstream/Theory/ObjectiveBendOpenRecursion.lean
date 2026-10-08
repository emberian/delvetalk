/- Reference runtime core for Objective Bend's own language edition.
Core scalar edition 2 distinguishes Booleans from arbitrary String labels.
Weak-head call-by-name gives an independent partial meaning to lazy mix/fix.
A sharing implementation must prove representation adequacy; this reference
relation does not claim a heap machine, type safety, termination, proof
consistency, or authority. -/
import Lean
import Theory.AxiomPin
namespace Minidregg.Theory.ObjectiveBendOpenRecursion
set_option autoImplicit false

/-- The scalar primitives, each one machine transition on unbounded naturals.
`subtract` is truncated at zero, `divide` is floor division with `a / 0 = 0`,
`modulo` is Lean's `%` (`a % 0 = a`, so `(a / b) * b + a % b = a` for every `b`),
`less`/`lessEqual` are the order on Nat; the surface `>`/`>=` are their negations. -/
inductive Primitive where
  | add | multiply | equal | conjunction | labelEqual
  | subtract | divide | less | lessEqual | modulo
  deriving Repr, DecidableEq

inductive Term where
  | bound (index : Nat)
  | lam (body : Term)
  | app (function argument : Term)
  | mix (inheritedExtension wrappingExtension : Term)
  | fix (specification inherited : Term)
  | specification (metadata extension : Term)
  | prototype (specification target : Term)
  | reflect (prototype : Term)
  | metadata (specification : Term)
  | project (prototype : Term)
  | nat (value : Nat)
  | boolean (value : Bool)
  | label (value : String)
  | binary (primitive : Primitive) (left right : Term)
  | extend (inherited : Term) (fields : List (String × Term))
  | record (fields : List (String × Term))
  | get (target : Term) (name : String)
  | ifZero (value zero successorBody : Term)
  /-- A sum injection: a weak-head value whose payload stays an unforced computation. -/
  | inject (label : String) (payload : Term)
  /-- Sum elimination; every arm body binds the payload at de Bruijn index 0. -/
  | case (scrutinee : Term) (arms : List (String × Term))
  /-- The Boolean eliminator. Booleans are not labels, so this is not a case. -/
  | ifBool (condition whenTrue whenFalse : Term)
  /-- Yield a typed Plan to the kernel. Not a value and never a reduction: a
  program stuck here has yielded, and continues only when resumed (`Yields`). -/
  | perform (plan : Term)
  /-- A pure value where an activity is expected (return). Reduces to its value. -/
  | done (value : Term)
  deriving Repr

def liftRename (rename : Nat → Nat) : Nat → Nat
  | 0 => 0 | n + 1 => rename n + 1

def Term.rename (rename : Nat → Nat) : Term → Term
  | .bound index => .bound (rename index)
  | .lam body => .lam (body.rename (liftRename rename))
  | .app function argument => .app (function.rename rename) (argument.rename rename)
  | .mix first second => .mix (first.rename rename) (second.rename rename)
  | .fix spec inherited => .fix (spec.rename rename) (inherited.rename rename)
  | .specification descriptor extension => .specification (descriptor.rename rename) (extension.rename rename)
  | .prototype spec target => .prototype (spec.rename rename) (target.rename rename)
  | .reflect target => .reflect (target.rename rename)
  | .metadata spec => .metadata (spec.rename rename)
  | .project target => .project (target.rename rename)
  | .nat value => .nat value
  | .boolean value => .boolean value
  | .label value => .label value
  | .binary primitive left right => .binary primitive (left.rename rename) (right.rename rename)
  | .extend inherited fields => .extend (inherited.rename rename)
      (fields.map fun field => (field.1,field.2.rename rename))
  | .record fields => .record (fields.map fun field => (field.1,field.2.rename rename))
  | .get target name => .get (target.rename rename) name
  | .ifZero value zero successorBody =>
      .ifZero (value.rename rename) (zero.rename rename)
        (successorBody.rename (liftRename rename))
  | .inject tag payload => .inject tag (payload.rename rename)
  | .case scrutinee arms => .case (scrutinee.rename rename)
      (arms.map fun field => (field.1,field.2.rename (liftRename rename)))
  | .ifBool condition whenTrue whenFalse =>
      .ifBool (condition.rename rename) (whenTrue.rename rename) (whenFalse.rename rename)
  | .perform plan => .perform (plan.rename rename)
  | .done value => .done (value.rename rename)

termination_by source => sizeOf source
decreasing_by
  all_goals simp_wf
  all_goals first
    | omega
    | (rename_i hmem
       have hlist := List.sizeOf_lt_of_mem hmem
       have hpair : sizeOf field.snd < sizeOf field := by
         cases field
         simp +arith
       omega)

def liftSubstitution (substitution : Nat → Term) : Nat → Term
  | 0 => .bound 0
  | n + 1 => (substitution n).rename Nat.succ

def Term.substitute (substitution : Nat → Term) : Term → Term
  | .bound index => substitution index
  | .lam body => .lam (body.substitute (liftSubstitution substitution))
  | .app function argument => .app (function.substitute substitution) (argument.substitute substitution)
  | .mix first second => .mix (first.substitute substitution) (second.substitute substitution)
  | .fix spec inherited => .fix (spec.substitute substitution) (inherited.substitute substitution)
  | .specification descriptor extension => .specification (descriptor.substitute substitution) (extension.substitute substitution)
  | .prototype spec target => .prototype (spec.substitute substitution) (target.substitute substitution)
  | .reflect target => .reflect (target.substitute substitution)
  | .metadata spec => .metadata (spec.substitute substitution)
  | .project target => .project (target.substitute substitution)
  | .nat value => .nat value
  | .boolean value => .boolean value
  | .label value => .label value
  | .binary primitive left right => .binary primitive (left.substitute substitution) (right.substitute substitution)
  | .extend inherited fields => .extend (inherited.substitute substitution)
      (fields.map fun field => (field.1,field.2.substitute substitution))
  | .record fields => .record (fields.map fun field => (field.1,field.2.substitute substitution))
  | .get target name => .get (target.substitute substitution) name
  | .ifZero value zero successorBody =>
      .ifZero (value.substitute substitution) (zero.substitute substitution)
        (successorBody.substitute (liftSubstitution substitution))
  | .inject tag payload => .inject tag (payload.substitute substitution)
  | .case scrutinee arms => .case (scrutinee.substitute substitution)
      (arms.map fun field => (field.1,field.2.substitute (liftSubstitution substitution)))
  | .ifBool condition whenTrue whenFalse =>
      .ifBool (condition.substitute substitution) (whenTrue.substitute substitution)
        (whenFalse.substitute substitution)
  | .perform plan => .perform (plan.substitute substitution)
  | .done value => .done (value.substitute substitution)

termination_by source => sizeOf source
decreasing_by
  all_goals simp_wf
  all_goals first
    | omega
    | (rename_i hmem
       have hlist := List.sizeOf_lt_of_mem hmem
       have hpair : sizeOf field.snd < sizeOf field := by
         cases field
         simp +arith
       omega)

def instantiate (body argument : Term) : Term :=
  body.substitute (fun index => match index with | 0 => argument | n + 1 => .bound n)

/-- `λself. λsuper. upper self (lower self super)`: the inherited target is a
computation; both extensions receive the identical final self expression. -/
def mixBody (lower upper : Term) : Term :=
  .lam (.lam (.app (.app (upper.rename (fun n => n + 2)) (.bound 1))
    (.app (.app (lower.rename (fun n => n + 2)) (.bound 1)) (.bound 0))))

inductive Value : Term → Prop where
  | function (body : Term) : Value (.lam body)
  | natural (n : Nat) : Value (.nat n)
  | boolean (value : Bool) : Value (.boolean value)
  | label (name : String) : Value (.label name)
  | record (fields : List (String × Term)) : Value (.record fields)
  | specification (metadata extension : Term) : Value (.specification metadata extension)
  | prototype (spec target : Term) : Value (.prototype spec target)
  | inject (label : String) (payload : Term) : Value (.inject label payload)

/-- A record-target fragment only. Other target kinds use ordinary extensions.
New fields shadow inherited fields; the inherited computation remains super. -/
def extendFields (inherited fields : List (String × Term)) : List (String × Term) :=
  fields ++ inherited.filter (fun prior => !(fields.any fun field => field.1 == prior.1))

def primitiveResult : Primitive → Term → Term → Option Term
  | .add, .nat a, .nat b => some (.nat (a + b))
  | .multiply, .nat a, .nat b => some (.nat (a * b))
  | .equal, .nat a, .nat b => some (.boolean (a == b))
  | .conjunction, .boolean a, .boolean b => some (.boolean (a && b))
  | .labelEqual, .label a, .label b => some (.boolean (a == b))
  | .subtract, .nat a, .nat b => some (.nat (a - b))
  | .divide, .nat a, .nat b => some (.nat (a / b))
  | .less, .nat a, .nat b => some (.boolean (decide (a < b)))
  | .lessEqual, .nat a, .nat b => some (.boolean (decide (a ≤ b)))
  | .modulo, .nat a, .nat b => some (.nat (a % b))
  | _, _, _ => none

/-- All String labels, including true/false, are excluded from Boolean operations. -/
theorem conjunction_labels_refused (left right : String) :
    primitiveResult .conjunction (.label left) (.label right) = none := rfl

theorem conjunction_boolean_exact (left right : Bool) :
    primitiveResult .conjunction (.boolean left) (.boolean right) =
      some (.boolean (left && right)) := rfl

theorem equality_boolean_exact (left right : Nat) :
    primitiveResult .equal (.nat left) (.nat right) = some (.boolean (left == right)) := rfl

theorem label_equality_boolean_exact (left right : String) :
    primitiveResult .labelEqual (.label left) (.label right) = some (.boolean (left == right)) := rfl

/-- Labels compare only with labels: a Boolean is never a reserved label. -/
theorem label_equality_booleans_refused (left right : Bool) :
    primitiveResult .labelEqual (.boolean left) (.boolean right) = none := rfl

/-- Subtraction is truncated: `left - right` is `0` whenever `right ≥ left`. -/
theorem subtract_truncated_exact (left right : Nat) :
    primitiveResult .subtract (.nat left) (.nat right) = some (.nat (left - right)) ∧
      (left ≤ right → primitiveResult .subtract (.nat left) (.nat right) = some (.nat 0)) :=
  ⟨rfl, fun below => by simp [primitiveResult, Nat.sub_eq_zero_of_le below]⟩

/-- Division is floor division, total: a zero divisor gives `0`, never a refusal. -/
theorem divide_floor_exact (left right : Nat) :
    primitiveResult .divide (.nat left) (.nat right) = some (.nat (left / right)) ∧
      primitiveResult .divide (.nat left) (.nat 0) = some (.nat 0) ∧
      (0 < right → ∀ quotient, primitiveResult .divide (.nat left) (.nat right) = some (.nat quotient) →
        quotient * right ≤ left ∧ left < (quotient + 1) * right) := by
  refine ⟨rfl, by simp [primitiveResult], fun positive quotient found => ?_⟩
  simp only [primitiveResult, Option.some.injEq, Term.nat.injEq] at found
  subst found
  refine ⟨Nat.div_mul_le_self left right, ?_⟩
  rw [Nat.add_mul, Nat.one_mul]
  exact Nat.lt_div_mul_add positive

/-- `modulo` is the remainder of `divide`: the two reconstruct the dividend for every
divisor, zero included (`a / 0 = 0`, `a % 0 = a`), and the remainder is below a
positive divisor. -/
theorem divide_modulo_reconstruct (left right quotient remainder : Nat)
    (divided : primitiveResult .divide (.nat left) (.nat right) = some (.nat quotient))
    (reduced : primitiveResult .modulo (.nat left) (.nat right) = some (.nat remainder)) :
    quotient * right + remainder = left ∧ (0 < right → remainder < right) ∧
      (right = 0 → remainder = left) := by
  simp only [primitiveResult, Option.some.injEq, Term.nat.injEq] at divided reduced
  subst divided; subst reduced
  refine ⟨?_, Nat.mod_lt left, fun zero => by simp [zero]⟩
  rw [Nat.mul_comm]; exact Nat.div_add_mod left right

/-- The order primitives decide `<` and `≤` on Nat exactly. -/
theorem order_exact (left right : Nat) :
    primitiveResult .less (.nat left) (.nat right) = some (.boolean (decide (left < right))) ∧
      primitiveResult .lessEqual (.nat left) (.nat right) = some (.boolean (decide (left ≤ right))) :=
  ⟨rfl, rfl⟩

/-- The arithmetic and order primitives take naturals only: a label or Boolean operand refuses. -/
theorem nat_primitives_refuse_labels (primitive : Primitive) (left right : String)
    (natural : primitive = .subtract ∨ primitive = .divide ∨ primitive = .less ∨ primitive = .lessEqual ∨
      primitive = .modulo) :
    primitiveResult primitive (.label left) (.label right) = none ∧
      primitiveResult primitive (.boolean (decide (left = right))) (.nat 0) = none := by
  rcases natural with rfl | rfl | rfl | rfl | rfl <;> exact ⟨rfl, rfl⟩

inductive Step : Term → Term → Prop where
  | beta (body argument : Term) : Step (.app (.lam body) argument) (instantiate body argument)
  | application {function next : Term} (argument : Term) :
      Step function next → Step (.app function argument) (.app next argument)
  | mix (lower upper : Term) : Step (.mix lower upper) (mixBody lower upper)
  | fix (spec inherited : Term) :
      Step (.fix spec inherited) (.app (.app spec (.fix spec inherited)) inherited)
  | applySpecification (metadata extension argument : Term) :
      Step (.app (.specification metadata extension) argument) (.app extension argument)
  | reflectPrototype (spec target : Term) : Step (.reflect (.prototype spec target)) spec
  | metadataSpecification (metadata extension : Term) : Step (.metadata (.specification metadata extension)) metadata
  | projectPrototype (spec target : Term) : Step (.project (.prototype spec target)) target
  | reflectStep {term next : Term} : Step term next → Step (.reflect term) (.reflect next)
  | metadataStep {term next : Term} : Step term next → Step (.metadata term) (.metadata next)
  | projectStep {term next : Term} : Step term next → Step (.project term) (.project next)
  | target {target next : Term} (name : String) :
      Step target next → Step (.get target name) (.get next name)
  | field (fields : List (String × Term)) (name : String) (body : Term) :
      fields.find? (fun field => field.1 == name) = some (name,body) →
      Step (.get (.record fields) name) body
  | extendTarget {inherited next : Term} (fields : List (String × Term)) :
      Step inherited next → Step (.extend inherited fields) (.extend next fields)
  | extendRecord (inherited fields : List (String × Term)) :
      Step (.extend (.record inherited) fields) (.record (extendFields inherited fields))
  | binaryLeft {left next : Term} (primitive : Primitive) (right : Term) :
      Step left next → Step (.binary primitive left right) (.binary primitive next right)
  | binaryRight {right next : Term} (primitive : Primitive) (left : Term) :
      Value left → Step right next → Step (.binary primitive left right) (.binary primitive left next)
  | primitive (primitive : Primitive) (left right result : Term) :
      Value left → Value right → primitiveResult primitive left right = some result →
      Step (.binary primitive left right) result
  | condition {value next : Term} (zero successorBody : Term) :
      Step value next → Step (.ifZero value zero successorBody) (.ifZero next zero successorBody)
  | zero (zero successorBody : Term) : Step (.ifZero (.nat 0) zero successorBody) zero
  | successor (n : Nat) (zero successorBody : Term) :
      Step (.ifZero (.nat (n + 1)) zero successorBody) (instantiate successorBody (.nat n))
  | caseTarget {scrutinee next : Term} (arms : List (String × Term)) :
      Step scrutinee next → Step (.case scrutinee arms) (.case next arms)
  /-- The first arm carrying the injected label is selected, exactly as field
  lookup selects the first field; the payload is substituted unevaluated. -/
  | caseInject (label : String) (payload : Term) (arms : List (String × Term)) (body : Term) :
      arms.find? (fun arm => arm.1 == label) = some (label,body) →
      Step (.case (.inject label payload) arms) (instantiate body payload)
  | ifCondition {condition next : Term} (whenTrue whenFalse : Term) :
      Step condition next → Step (.ifBool condition whenTrue whenFalse) (.ifBool next whenTrue whenFalse)
  | ifTrue (whenTrue whenFalse : Term) : Step (.ifBool (.boolean true) whenTrue whenFalse) whenTrue
  | ifFalse (whenTrue whenFalse : Term) : Step (.ifBool (.boolean false) whenTrue whenFalse) whenFalse
  /-- `done` is administrative: the activity returns its pure value. -/
  | done (value : Term) : Step (.done value) value

inductive Steps : Term → Term → Prop where
  | refl (term : Term) : Steps term term
  | next {initial middle result : Term} : Step initial middle → Steps middle result → Steps initial result

def Evaluates (initial result : Term) : Prop := Steps initial result ∧ Value result

/-! ## Activities: a perform in evaluation position is a yield

The pure reference `Step` has no rule for `perform`: a program whose next redex
is a perform has YIELDED its plan to the kernel. Evaluation contexts are data,
one frame per congruence rule of `Step`, innermost first. Resuming plugs the
kernel's response into the context. A turn is one segment from a resume (or the
start) to the next yield or value. -/

inductive SourceFrame where
  | application (argument : Term)
  | field (name : String)
  | extend (fields : List (String × Term))
  | binaryLeft (primitive : Primitive) (right : Term)
  | binaryRight (primitive : Primitive) (left : Term)
  | condition (zero successorBody : Term)
  | case (arms : List (String × Term))
  | ifBool (whenTrue whenFalse : Term)
  | reflect | metadata | project
  deriving Repr

def SourceFrame.plug : SourceFrame → Term → Term
  | .application argument, hole => .app hole argument
  | .field name, hole => .get hole name
  | .extend fields, hole => .extend hole fields
  | .binaryLeft primitive right, hole => .binary primitive hole right
  | .binaryRight primitive left, hole => .binary primitive left hole
  | .condition zero successorBody, hole => .ifZero hole zero successorBody
  | .case arms, hole => .case hole arms
  | .ifBool whenTrue whenFalse, hole => .ifBool hole whenTrue whenFalse
  | .reflect, hole => .reflect hole
  | .metadata, hole => .metadata hole
  | .project, hole => .project hole

/-- Plug a hole into a context listed innermost first. -/
def plug (context : List SourceFrame) (hole : Term) : Term :=
  context.foldl (fun term frame => frame.plug term) hole

/-- `Yields term plan context`: the next redex of `term` is `perform plan` in
`context`. Each constructor mirrors exactly one congruence rule of `Step`. -/
inductive Yields : Term → Term → List SourceFrame → Prop where
  | perform (plan : Term) : Yields (.perform plan) plan []
  | application {function plan : Term} {context : List SourceFrame} (argument : Term) :
      Yields function plan context → Yields (.app function argument) plan (context ++ [.application argument])
  | field {target plan : Term} {context : List SourceFrame} (name : String) :
      Yields target plan context → Yields (.get target name) plan (context ++ [.field name])
  | extend {inherited plan : Term} {context : List SourceFrame} (fields : List (String × Term)) :
      Yields inherited plan context → Yields (.extend inherited fields) plan (context ++ [.extend fields])
  | binaryLeft {left plan : Term} {context : List SourceFrame} (primitive : Primitive) (right : Term) :
      Yields left plan context →
      Yields (.binary primitive left right) plan (context ++ [.binaryLeft primitive right])
  | binaryRight {left right plan : Term} {context : List SourceFrame} (primitive : Primitive) :
      Value left → Yields right plan context →
      Yields (.binary primitive left right) plan (context ++ [.binaryRight primitive left])
  | condition {value plan : Term} {context : List SourceFrame} (zero successorBody : Term) :
      Yields value plan context →
      Yields (.ifZero value zero successorBody) plan (context ++ [.condition zero successorBody])
  | case {scrutinee plan : Term} {context : List SourceFrame} (arms : List (String × Term)) :
      Yields scrutinee plan context → Yields (.case scrutinee arms) plan (context ++ [.case arms])
  | ifBool {condition plan : Term} {context : List SourceFrame} (whenTrue whenFalse : Term) :
      Yields condition plan context →
      Yields (.ifBool condition whenTrue whenFalse) plan (context ++ [.ifBool whenTrue whenFalse])
  | reflect {target plan : Term} {context : List SourceFrame} :
      Yields target plan context → Yields (.reflect target) plan (context ++ [.reflect])
  | metadata {target plan : Term} {context : List SourceFrame} :
      Yields target plan context → Yields (.metadata target) plan (context ++ [.metadata])
  | project {target plan : Term} {context : List SourceFrame} :
      Yields target plan context → Yields (.project target) plan (context ++ [.project])

/-- An activity's run against a list of turns: each turn yields a plan and is
resumed with the kernel's response; the last segment finishes with a value.
One list entry is one admitted turn. -/
inductive Interaction : Term → List (Term × Term) → Term → Prop where
  | finish {term value : Term} : Evaluates term value → Interaction term [] value
  | turn {term yielded plan response value : Term} {context : List SourceFrame}
      {rest : List (Term × Term)} :
      Steps term yielded → Yields yielded plan context →
      Interaction (plug context response) rest value →
      Interaction term ((plan,response) :: rest) value

/-- Refinement is a substantive consumer obligation over independently defined
source steps. It cannot be discharged by naming a resolved method a new Eval. -/
inductive PositiveSteps : Term → Term → Prop where
  | begin {initial middle result : Term} : Step initial middle → Steps middle result → PositiveSteps initial result

/- This contract rules out an always-stuttering evaluator. Shared heap updates
may correspond to several reference reductions; cyclic heaps require a graph
logical relation, not naive finite-tree unfolding. A concrete implementation
must inhabit all fields before any adequacy claim is made. -/
/-- Ground observations only: closure/record contextual approximation needs a
separate relation and is not syntactic equality of residual lambda bodies. -/
inductive Observation where
  | natural (value : Nat)
  | boolean (value : Bool)
  | label (value : String)
  deriving Repr, DecidableEq
inductive Observes : Term → Observation → Prop where
  | natural (value : Nat) : Observes (.nat value) (.natural value)
  | boolean (value : Bool) : Observes (.boolean value) (.boolean value)
  | label (value : String) : Observes (.label value) (.label value)

inductive Transition (State : Type) where
  | advanced (next : State)
  | finished (result : Observation)
  | suspended (retained : State)
  | refused (diagnostic : String)
  /-- The program yielded: no pure result exists; only a resume (a turn)
  continues it. The waiting state is retained exactly. -/
  | yielded (waiting : State)

inductive MachineSteps {State : Type} (step : State → Transition State) : State → State → Prop where
  | refl (state : State) : MachineSteps step state state
  | next {initial middle result : State} : step initial = .advanced middle →
      MachineSteps step middle result → MachineSteps step initial result

/-- Supported is fixed by the intended source edition/domain, not chosen by an
implementation to make initialization/completeness vacuous. Administrative
progress applies only to running transitions. Final values and capacity
suspension have separate observations. Completeness is an explicit obligation
for the supported adequately provisioned domain; no instance is claimed here. -/
structure Representation (State : Type) (Supported : Term → Prop) where
  represents : State → Term → Prop
  start : Term → Option State
  initializesSupported : ∀ source, Supported source → ∃ state, start source = some state
  initialized : ∀ source state, start source = some state → represents state source
  step : State → Transition State
  administrativeRank : State → Nat
  simulation : ∀ state successor source, represents state source → step state = .advanced successor →
    ∃ next, represents successor next ∧
      ((next = source ∧ administrativeRank successor < administrativeRank state) ∨
        PositiveSteps source next)
  valueAdequacy : ∀ state source result, represents state source → step state = .finished result →
    ∃ value, Steps source value ∧ Value value ∧ Observes value result
  suspensionExact : ∀ state retained, step state = .suspended retained → retained = state
  evaluationComplete : ∀ source value result, Supported source → Evaluates source value → Observes value result →
    ∃ initial final, start source = some initial ∧ MachineSteps step initial final ∧
      step final = .finished result

/-- Generic Fix returns the target, never implicitly wraps it in a prototype.
Prototype conflation is an explicit library knot whose spec can be inspected
without demanding the recursive target. `self` here is the whole prototype. -/
def instantiatePrototype (spec seed : Term) : Term :=
  .fix (.lam (.lam (.prototype (spec.rename (fun n => n + 2))
    (.app (.app (spec.rename (fun n => n + 2)) (.bound 1)) (.bound 0))))) seed

theorem prototype_metadata_unforced (spec divergent : Term) :
    Step (.reflect (.prototype spec divergent)) spec := .reflectPrototype _ _

theorem specification_metadata_unforced (metadata divergent : Term) :
    Step (.metadata (.specification metadata divergent)) metadata := .metadataSpecification _ _

theorem lazy_fixed_function :
    Evaluates (.fix (.lam (.lam (.lam (.bound 0)))) (.nat 7)) (.lam (.bound 0)) := by
  constructor
  · refine .next (.fix _ _) ?_
    have first : Step
        (.app (.app (.lam (.lam (.lam (.bound 0))))
          (.fix (.lam (.lam (.lam (.bound 0)))) (.nat 7))) (.nat 7))
        (.app (.lam (.lam (.bound 0))) (.nat 7)) := by
      simpa [instantiate, Term.substitute, liftSubstitution, Term.rename, liftRename] using
        (Step.application (.nat 7) (Step.beta (.lam (.lam (.bound 0)))
          (.fix (.lam (.lam (.lam (.bound 0)))) (.nat 7))))
    have second : Step (.app (.lam (.lam (.bound 0))) (.nat 7)) (.lam (.bound 0)) := by
      simpa [instantiate, Term.substitute, liftSubstitution, Term.rename, liftRename] using
        (Step.beta (.lam (.bound 0)) (.nat 7))
    exact .next first (.next second (.refl _))
  · exact .function _

/-- The injected label selects its arm and the unevaluated payload is
substituted; a divergent payload in an unselected position is never demanded. -/
theorem case_selects_injected_arm (unused : Term) :
    Evaluates (.case (.inject "some" (.nat 7)) [("none",unused),("some",.bound 0)]) (.nat 7) := by
  refine ⟨.next (.caseInject "some" (.nat 7) _ (.bound 0) rfl) ?_,.natural 7⟩
  simpa [instantiate, Term.substitute] using Steps.refl (Term.nat 7)

/-- Natural equality drives control flow through the Boolean eliminator. -/
theorem equality_drives_branch (left right : Nat) :
    Evaluates (.ifBool (.binary .equal (.nat left) (.nat right)) (.label "same") (.label "different"))
      (.label (if left == right then "same" else "different")) := by
  refine ⟨.next (.ifCondition _ _ (.primitive .equal _ _ _ (.natural _) (.natural _) rfl)) ?_,.label _⟩
  cases h : left == right
  · exact .next (.ifFalse _ _) (by simp; exact .refl _)
  · exact .next (.ifTrue _ _) (by simp; exact .refl _)

theorem yields_plug {term plan : Term} {context : List SourceFrame}
    (yielded : Yields term plan context) : term = plug context (.perform plan) := by
  induction yielded <;> simp_all [plug, List.foldl_append, SourceFrame.plug]

theorem value_no_step {term next : Term} (value : Value term) : ¬ Step term next := by
  intro step; cases value <;> cases step

theorem yields_not_value {term plan : Term} {context : List SourceFrame}
    (yielded : Yields term plan context) : ¬ Value term := by
  intro value; cases yielded <;> cases value

/-- A yielded program is stuck for the pure reference: only a resume moves it. -/
theorem yields_no_step {term plan : Term} {context : List SourceFrame}
    (yielded : Yields term plan context) : ∀ next, ¬ Step term next := by
  induction yielded with
  | perform plan => intro next step; cases step
  | application argument inner ih =>
      intro next step; cases step with
      | beta => cases inner
      | application _ prior => exact ih _ prior
      | applySpecification => cases inner
  | field name inner ih =>
      intro next step; cases step with
      | target _ prior => exact ih _ prior
      | field => cases inner
  | extend fields inner ih =>
      intro next step; cases step with
      | extendTarget _ prior => exact ih _ prior
      | extendRecord => cases inner
  | binaryLeft primitive right inner ih =>
      intro next step; cases step with
      | binaryLeft _ _ prior => exact ih _ prior
      | binaryRight _ _ value _ => exact yields_not_value inner value
      | primitive _ _ _ _ value _ _ => exact yields_not_value inner value
  | binaryRight primitive leftValue inner ih =>
      intro next step; cases step with
      | binaryLeft _ _ prior => exact value_no_step leftValue prior
      | binaryRight _ _ _ prior => exact ih _ prior
      | primitive _ _ _ _ _ value _ => exact yields_not_value inner value
  | condition zero successorBody inner ih =>
      intro next step; cases step with
      | condition _ _ prior => exact ih _ prior
      | zero => cases inner
      | successor => cases inner
  | case arms inner ih =>
      intro next step; cases step with
      | caseTarget _ prior => exact ih _ prior
      | caseInject => cases inner
  | ifBool whenTrue whenFalse inner ih =>
      intro next step; cases step with
      | ifCondition _ _ prior => exact ih _ prior
      | ifTrue => cases inner
      | ifFalse => cases inner
  | reflect inner ih =>
      intro next step; cases step with
      | reflectPrototype => cases inner
      | reflectStep prior => exact ih _ prior
  | metadata inner ih =>
      intro next step; cases step with
      | metadataSpecification => cases inner
      | metadataStep prior => exact ih _ prior
  | project inner ih =>
      intro next step; cases step with
      | projectPrototype => cases inner
      | projectStep prior => exact ih _ prior

/-- The yielded plan and its continuation are unique. -/
theorem yields_deterministic {term plan plan' : Term} {context context' : List SourceFrame}
    (first : Yields term plan context) (second : Yields term plan' context') :
    plan = plan' ∧ context = context' := by
  induction first generalizing plan' context' with
  | perform plan => cases second; exact ⟨rfl,rfl⟩
  | application argument inner ih =>
      cases second with
      | application _ inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩
  | field name inner ih =>
      cases second with
      | field _ inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩
  | extend fields inner ih =>
      cases second with
      | extend _ inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩
  | binaryLeft primitive right inner ih =>
      cases second with
      | binaryLeft _ _ inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩
      | binaryRight _ value _ => exact absurd value (yields_not_value inner)
  | binaryRight primitive leftValue inner ih =>
      cases second with
      | binaryLeft _ _ inner' => exact absurd leftValue (yields_not_value inner')
      | binaryRight _ _ inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩
  | condition zero successorBody inner ih =>
      cases second with
      | condition _ _ inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩
  | case arms inner ih =>
      cases second with
      | case _ inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩
  | ifBool whenTrue whenFalse inner ih =>
      cases second with
      | ifBool _ _ inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩
  | reflect inner ih =>
      cases second with
      | reflect inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩
  | metadata inner ih =>
      cases second with
      | metadata inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩
  | project inner ih =>
      cases second with
      | project inner' => obtain ⟨h1,h2⟩ := ih inner'; exact ⟨h1,by rw [h2]⟩

/-- A one-turn activity: perform a write, resume with `written`, select the arm.
The plan and the response are both ordinary injected data. -/
theorem one_turn_interaction (plan : Term) :
    Interaction (.case (.perform plan) [("written",.done (.nat 1)),("refused",.done (.nat 0))])
      [(plan,.inject "written" (.record []))] (.nat 1) := by
  refine .turn (.refl _) (.case _ (.perform plan)) ?_
  refine .finish ⟨.next (.caseInject "written" (.record []) _ (.done (.nat 1)) rfl) ?_,.natural 1⟩
  simpa [instantiate, Term.substitute] using Steps.next (Step.done (.nat 1)) (.refl _)

#assert_axioms label_equality_boolean_exact label_equality_booleans_refused
  case_selects_injected_arm equality_drives_branch yields_no_step yields_deterministic yields_plug
  one_turn_interaction subtract_truncated_exact divide_floor_exact order_exact nat_primitives_refuse_labels
  divide_modulo_reconstruct

end Minidregg.Theory.ObjectiveBendOpenRecursion
