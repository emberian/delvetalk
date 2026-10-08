import Theory.ObjectiveBendTypes
import Theory.ObjectiveBendOpenRecursion
import Theory.AxiomPin
namespace Minidregg.Theory.ObjectiveBendTyping
open ObjectiveBendTypes ObjectiveBendOpenRecursion
set_option autoImplicit false

structure Assumptions where
  bounds : Bounds := []
  shareableVariables : List Nat := []
  /-- Rigid variables (OB-LTUO LT2 D2): a template's `Self`, checked once against its
  declared bound. A rigid variable's bound is a LOWER bound: members are looked up
  through it (`Ty.lookup`, `Ty.isRow`), but it is never an alias, so no conversion
  equates the variable with its bound row. Emitted programs have `rigid = []`, where
  `alias` is `bounds.lookup` and the checker is the alias checker. -/
  rigid : List Nat := []

/-- The declared head a variable unfolds to in a conversion: its bound unless it is rigid. -/
def Assumptions.alias (assumptions : Assumptions) (index : Nat) : Option Ty :=
  if assumptions.rigid.contains index then none else assumptions.bounds.lookup index

theorem Assumptions.alias_bound {assumptions : Assumptions} {index : Nat} {bound : Ty}
    (found : assumptions.alias index = some bound) : assumptions.bounds.lookup index = some bound := by
  unfold Assumptions.alias at found
  split at found
  · cases found
  · exact found

theorem Assumptions.alias_of_rigid_nil {assumptions : Assumptions} (open_ : assumptions.rigid = [])
    (index : Nat) : assumptions.alias index = assumptions.bounds.lookup index := by
  simp [Assumptions.alias, open_]

theorem Assumptions.alias_rigid {assumptions : Assumptions} {index : Nat}
    (rigid : assumptions.rigid.contains index = true) : assumptions.alias index = none := by
  unfold Assumptions.alias; rw [if_pos rigid]

/-- More fuel never turns an accepted row into a refused one. -/
theorem Ty.isRow_mono {bounds : Bounds} : ∀ {fuel fuel' : Nat} {type : Ty},
    type.isRow bounds fuel = true → fuel ≤ fuel' → type.isRow bounds fuel' = true
  | 0, _, _, h, _ => by simp [Ty.isRow] at h
  | fuel + 1, fuel', type, h, le => by
    obtain ⟨f, rfl⟩ : ∃ f, fuel' = f + 1 := ⟨fuel' - 1, by omega⟩
    cases type with
    | emptyRow => rfl
    | field _ _ tail => simp only [Ty.isRow] at h ⊢; exact Ty.isRow_mono h (by omega)
    | «variable» index =>
      simp only [Ty.isRow] at h ⊢
      split at h
      · exact Ty.isRow_mono h (by omega)
      · cases h
    | _ => simp [Ty.isRow] at h

/-- More fuel never changes a successful lookup. -/
theorem Ty.lookup_mono {bounds : Bounds} : ∀ {fuel fuel' : Nat} {type : Ty} {name : String} {member : Ty},
    type.lookup bounds fuel name = some member → fuel ≤ fuel' → type.lookup bounds fuel' name = some member
  | 0, _, _, _, _, h, _ => by simp [Ty.lookup] at h
  | fuel + 1, fuel', type, name, member, h, le => by
    obtain ⟨f, rfl⟩ : ∃ f, fuel' = f + 1 := ⟨fuel' - 1, by omega⟩
    cases type with
    | field prior m tail =>
      simp only [Ty.lookup] at h ⊢
      split at h
      · rw [if_pos ‹_›]; exact h
      · rw [if_neg ‹_›]; exact Ty.lookup_mono h (by omega)
    | «variable» index =>
      simp only [Ty.lookup, Option.bind_eq_bind] at h ⊢
      cases found : bounds.lookup index with
      | none => simp [found] at h
      | some bound => simp only [found, Option.bind_some] at h ⊢; exact Ty.lookup_mono h (by omega)
    | _ => simp [Ty.lookup] at h

/-- Finite guarded shareability premises are checked from the declared bounds.
A recursive immutable row may refer to itself; a custody/once member rejects
its shareability even when hidden under that recursive row. -/
def Assumptions.valid (assumptions : Assumptions) : Bool :=
  assumptions.shareableVariables.all (fun index =>
    match assumptions.bounds.lookup index with
    | none => false
    | some bound => bound.shareableUnder assumptions.shareableVariables) &&
  -- No rigid variable names an activity, so a type agreement never turns an
  -- activity into a suspendable type or back (`Ty.isComputation` is invariant).
  assumptions.bounds.all (fun bound => !bound.2.isComputation)

/-- Annotated recursive aliases unfold one declared head only. This explicit
fragment supports the generated global-record knot without an arbitrary subtype
oracle or unrestricted recursive definitional conversion. An alias never names
an activity, so no agreement crosses between an activity and a suspendable type
(`sameType_isComputation`), whatever the bounds say. -/
def sameType (assumptions : Assumptions) (actual expected : Ty) : Bool :=
  actual.canonical == expected.canonical ||
    (match actual with
      | .variable index => !expected.isComputation &&
          (assumptions.alias index).map Ty.canonical == some expected.canonical
      | _ => false) ||
    (match expected with
      | .variable index => !actual.isComputation &&
          (assumptions.alias index).map Ty.canonical == some actual.canonical
      | _ => false)

theorem sameType_isComputation {assumptions : Assumptions} {actual expected : Ty}
    (agreement : sameType assumptions actual expected = true) :
    actual.isComputation = expected.isComputation := by
  simp only [sameType,Bool.or_eq_true] at agreement
  rcases agreement with (canonical | aliasActual) | aliasExpected
  · rw [← Ty.canonical_isComputation actual, ← Ty.canonical_isComputation expected]
    simpa using congrArg Ty.isComputation (by simpa using canonical : actual.canonical = expected.canonical)
  · cases actual <;> simp at aliasActual
    simp_all [Ty.isComputation]
  · cases expected <;> simp at aliasExpected
    simp_all [Ty.isComputation]

/-- The checker converts an inferred type to a declared one only when the two
agree AND the conversion does not manufacture shareability. `Ty.canonical`
forgets a shadowed member (first-field shadowing), so a row hiding a custody or
a once closure behind a later field of the same name is canonically equal to a
row that is shareable; `sameType` alone would let such a value be bound
unrestricted and duplicated. Every conversion the checker inserts goes through
this; the relation `PartialTyping.conversion` keeps plain `sameType` because the
machine proofs rebuild conversions from canonical equality alone. -/
def agree (assumptions : Assumptions) (actual expected : Ty) : Bool :=
  sameType assumptions actual expected &&
    (!expected.shareableUnder assumptions.shareableVariables ||
      actual.shareableUnder assumptions.shareableVariables)

theorem agree_sameType {assumptions : Assumptions} {actual expected : Ty}
    (agreement : agree assumptions actual expected = true) :
    sameType assumptions actual expected = true :=
  (Bool.and_eq_true_iff.mp agreement).1

/-- A checked conversion never turns a non-shareable type into a shareable one. -/
theorem agree_shareable {assumptions : Assumptions} {actual expected : Ty}
    (agreement : agree assumptions actual expected = true)
    (expectedShareable : expected.shareableUnder assumptions.shareableVariables = true) :
    actual.shareableUnder assumptions.shareableVariables = true := by
  have second := (Bool.and_eq_true_iff.mp agreement).2
  simpa [expectedShareable] using second

/-- Source positions address the annotation of each actual lambda. Missing
annotations are refused, not guessed or silently replaced by Data types. An
injection's position carries the type of its constructor function: domain is
the declared payload type, codomain the declared variant; a sum type is never
guessed from one label. -/
abbrev Annotations := List Nat → Option LambdaAnnotation
structure AnnotatedTerm where
  term : Term
  annotations : Annotations
  assumptions : Assumptions := {}
def AnnotatedTerm.erase (source : AnnotatedTerm) : Term := source.term

def callable : Ty → Ty
  | .specification _ extension => callable extension
  | other => other

def reusableAllowed (assumptions : Assumptions) (reuse : Reuse)
    (context : Context) (uses : Uses) : Bool :=
  reuse != .reusable || reusableCaptures assumptions.shareableVariables context uses

/-- An argument becomes a shared heap thunk, so it is never an activity (rule
`effect-as-argument`); an unrestricted one must also be shareable. -/
def argumentAllowed (assumptions : Assumptions) (quantity : Quantity)
    (context : Context) (type : Ty) (uses : Uses) : Bool :=
  !type.isComputation && (quantity != .unrestricted ||
    (type.shareableUnder assumptions.shareableVariables &&
      reusableCaptures assumptions.shareableVariables context uses))

def overlay : Ty → Ty → Ty
  | .field name member rest, inherited => .field name member (overlay rest inherited)
  | _, inherited => inherited

def primitiveTypes : Primitive → Ty × Ty
  | .add | .multiply | .subtract | .divide | .modulo => (.natural, .natural)
  | .equal | .less | .lessEqual => (.natural, .boolean)
  | .conjunction => (.boolean, .boolean)
  | .labelEqual => (.label, .boolean)

def literalType (_value : String) : Ty := .label

mutual
/-- A derivation over the independent runtime syntax. This judges partial
computations only: Fix is not evaluated by Lean's definitional conversion. -/
inductive PartialTyping (assumptions : Assumptions) : Context → Term → Ty → Uses → Prop where
  | bound {context : Context} {index : Nat} {binding : Binding} :
      context[index]? = some binding →
      PartialTyping assumptions context (.bound index) binding.type (variableUses context index)
  | natural (context : Context) (value : Nat) :
      PartialTyping assumptions context (.nat value) .natural (zeroUses context)
  | boolean (context : Context) (value : Bool) :
      PartialTyping assumptions context (.boolean value) .boolean (zeroUses context)
  | label (context : Context) (value : String) :
      PartialTyping assumptions context (.label value) (literalType value) (zeroUses context)
  | lambda {context : Context} {body : Term} {annotation : LambdaAnnotation} {uses : Uses} :
      PartialTyping assumptions (⟨annotation.domain, annotation.parameter⟩ :: context)
        body annotation.codomain uses →
      safeUses (⟨annotation.domain, annotation.parameter⟩ :: context) uses = true →
      validContext assumptions.shareableVariables (⟨annotation.domain, annotation.parameter⟩ :: context) = true →
      reusableAllowed assumptions annotation.reuse context uses.tail = true →
      PartialTyping assumptions context (.lam body)
        (.arrow annotation.reuse annotation.parameter annotation.domain annotation.codomain) uses.tail
  | conversion {context : Context} {term : Term} {actual expected : Ty} {uses : Uses} :
      PartialTyping assumptions context term actual uses → sameType assumptions actual expected = true →
      PartialTyping assumptions context term expected uses
  | application {context : Context} {function argument : Term} {functionType argumentType domain codomain : Ty}
      {functionUses argumentUses : Uses} {reuse : Reuse} {quantity : Quantity} :
      PartialTyping assumptions context function functionType functionUses →
      PartialTyping assumptions context argument argumentType argumentUses →
      callable functionType = .arrow reuse quantity domain codomain → argumentType = domain →
      argumentAllowed assumptions quantity context argumentType argumentUses = true →
      PartialTyping assumptions context (.app function argument) codomain (addUses functionUses argumentUses)
  | record {context : Context} {fields : List (String × Term)} {row : Ty} {uses : Uses} :
      FieldsTyping assumptions context fields row uses →
      PartialTyping assumptions context (.record fields) row uses
  | get {context : Context} {target : Term} {targetType member : Ty} {uses : Uses} {name : String} {fuel : Nat} :
      PartialTyping assumptions context target targetType uses →
      targetType.lookup assumptions.bounds fuel name = some member →
      PartialTyping assumptions context (.get target name) member uses
  | extend {context : Context} {target : Term} {fields : List (String × Term)}
      {targetType row : Ty} {targetUses fieldUses : Uses} {fuel : Nat} :
      PartialTyping assumptions context target targetType targetUses →
      FieldsTyping assumptions context fields row fieldUses →
      targetType.isRow assumptions.bounds fuel = true →
      PartialTyping assumptions context (.extend target fields) (overlay row targetType) (addUses targetUses fieldUses)
  | specification {context : Context} {metadata extension : Term} {metadataType extensionType : Ty} {mu eu : Uses} :
      PartialTyping assumptions context metadata metadataType mu →
      PartialTyping assumptions context extension extensionType eu →
      metadataType.isComputation = false → extensionType.isComputation = false →
      PartialTyping assumptions context (.specification metadata extension)
        (.specification metadataType extensionType) (addUses mu eu)
  | prototype {context : Context} {spec target : Term} {specType targetType : Ty} {su tu : Uses} :
      PartialTyping assumptions context spec specType su → PartialTyping assumptions context target targetType tu →
      specType.isComputation = false → targetType.isComputation = false →
      PartialTyping assumptions context (.prototype spec target) (.prototype specType targetType) (addUses su tu)
  | reflect {context : Context} {target : Term} {specType targetType : Ty} {uses : Uses} :
      PartialTyping assumptions context target (.prototype specType targetType) uses →
      PartialTyping assumptions context (.reflect target) specType uses
  | metadata {context : Context} {target : Term} {metadataType extensionType : Ty} {uses : Uses} :
      PartialTyping assumptions context target (.specification metadataType extensionType) uses →
      PartialTyping assumptions context (.metadata target) metadataType uses
  | project {context : Context} {target : Term} {specType targetType : Ty} {uses : Uses} :
      PartialTyping assumptions context target (.prototype specType targetType) uses →
      PartialTyping assumptions context (.project target) targetType uses
  | mix {context : Context} {lower upper : Term} {lowerType upperType self inherited middle provided : Ty} {lu uu : Uses} :
      PartialTyping assumptions context lower lowerType lu →
      PartialTyping assumptions context upper upperType uu →
      callable lowerType = .arrow .reusable .unrestricted self (.arrow .reusable .unrestricted inherited middle) →
      callable upperType = .arrow .reusable .unrestricted self (.arrow .reusable .unrestricted middle provided) →
      reusableCaptures assumptions.shareableVariables context (addUses lu uu) = true →
      self.shareableUnder assumptions.shareableVariables = true →
      inherited.shareableUnder assumptions.shareableVariables = true →
      middle.shareableUnder assumptions.shareableVariables = true →
      PartialTyping assumptions context (.mix lower upper)
        (.arrow .reusable .unrestricted self (.arrow .reusable .unrestricted inherited provided)) (addUses lu uu)
  | fix {context : Context} {spec inheritedTerm : Term} {specType inherited target : Ty} {su iu : Uses} :
      PartialTyping assumptions context spec specType su →
      callable specType = .arrow .reusable .unrestricted target (.arrow .reusable .unrestricted inherited target) →
      PartialTyping assumptions context inheritedTerm inherited iu →
      target.shareableUnder assumptions.shareableVariables = true →
      argumentAllowed assumptions .unrestricted context inherited iu = true →
      reusableCaptures assumptions.shareableVariables context su = true →
      PartialTyping assumptions context (.fix spec inheritedTerm) target (addUses su iu)
  | binary {context : Context} {primitive : Primitive} {left right : Term} {input output : Ty} {lu ru : Uses} :
      primitiveTypes primitive = (input, output) →
      PartialTyping assumptions context left input lu → PartialTyping assumptions context right input ru →
      PartialTyping assumptions context (.binary primitive left right) output (addUses lu ru)
  | ifZero {context : Context} {value zero successor : Term} {result : Ty} {vu zu su : Uses} :
      PartialTyping assumptions context value .natural vu → PartialTyping assumptions context zero result zu →
      PartialTyping assumptions (⟨.natural,.unrestricted⟩ :: context) successor result su →
      safeUses (⟨.natural,.unrestricted⟩ :: context) su = true →
      PartialTyping assumptions context (.ifZero value zero successor) result (addUses vu (addUses zu su.tail))
  | inject {context : Context} {tag : String} {payload : Term} {payloadType row : Ty} {uses : Uses} {fuel : Nat} :
      PartialTyping assumptions context payload payloadType uses →
      row.lookup assumptions.bounds fuel tag = some payloadType →
      payloadType.isComputation = false →
      PartialTyping assumptions context (.inject tag payload) (.variant row) uses
  | case {context : Context} {scrutinee : Term} {arms : List (String × Term)} {row result : Ty} {su au : Uses} :
      PartialTyping assumptions context scrutinee (.variant row) su →
      ArmsTyping assumptions context arms row result au →
      PartialTyping assumptions context (.case scrutinee arms) result (addUses su au)
  | ifBool {context : Context} {condition whenTrue whenFalse : Term} {result : Ty} {cu tu fu : Uses} :
      PartialTyping assumptions context condition .boolean cu →
      PartialTyping assumptions context whenTrue result tu →
      PartialTyping assumptions context whenFalse result fu →
      PartialTyping assumptions context (.ifBool condition whenTrue whenFalse) result (addUses cu (addUses tu fu))
  /-- Yield a Plan (a sum of first-order actions); the response is data. -/
  | perform {context : Context} {plan : Term} {planType response : Ty} {uses : Uses} :
      PartialTyping assumptions context plan planType uses →
      planType.isPlan = true → response.isData = true →
      PartialTyping assumptions context (.perform plan) (.computation planType response response) uses
  /-- A pure value where an activity is expected. -/
  | done {context : Context} {value : Term} {planType response result : Ty} {uses : Uses} :
      PartialTyping assumptions context value result uses → result.isComputation = false →
      PartialTyping assumptions context (.done value) (.computation planType response result) uses
  /-- Sequencing: the activity's result selects an arm; every arm is an activity
  over the same plan/response types. This is the only `bind`. -/
  | effectCase {context : Context} {scrutinee : Term} {arms : List (String × Term)}
      {planType response row result : Ty} {su au : Uses} :
      PartialTyping assumptions context scrutinee (.computation planType response (.variant row)) su →
      ArmsTyping assumptions context arms row (.computation planType response result) au →
      result.isComputation = false →
      PartialTyping assumptions context (.case scrutinee arms) (.computation planType response result) (addUses su au)
inductive FieldsTyping (assumptions : Assumptions) : Context → List (String × Term) → Ty → Uses → Prop where
  | nil (context : Context) : FieldsTyping assumptions context [] .emptyRow (zeroUses context)
  | cons {context : Context} {name : String} {body : Term} {rest : List (String × Term)} {type row : Ty} {bu ru : Uses} :
      PartialTyping assumptions context body type bu → FieldsTyping assumptions context rest row ru →
      type.isComputation = false →
      FieldsTyping assumptions context ((name,body) :: rest) (.field name type row) (addUses bu ru)
/-- Arms in source order build a CLOSED row: with the scrutinee at that variant
row, every label has exactly the arm the machine's first-match lookup selects.
Each body binds the payload unrestricted (so its type must be shareable). -/
inductive ArmsTyping (assumptions : Assumptions) : Context → List (String × Term) → Ty → Ty → Uses → Prop where
  | nil (context : Context) (result : Ty) : ArmsTyping assumptions context [] .emptyRow result (zeroUses context)
  | cons {context : Context} {name : String} {body : Term} {rest : List (String × Term)} {payload row result : Ty} {bu ru : Uses} :
      PartialTyping assumptions (⟨payload,.unrestricted⟩ :: context) body result bu →
      safeUses (⟨payload,.unrestricted⟩ :: context) bu = true →
      payload.shareableUnder assumptions.shareableVariables = true →
      ArmsTyping assumptions context rest row result ru →
      ArmsTyping assumptions context ((name,body) :: rest) (.field name payload row) result (addUses bu.tail ru)
end

structure Inferred (assumptions : Assumptions) (context : Context) (term : Term) where
  type : Ty
  uses : Uses
  derivation : PartialTyping assumptions context term type uses
structure InferredFields (assumptions : Assumptions) (context : Context) (fields : List (String × Term)) where
  type : Ty
  uses : Uses
  derivation : FieldsTyping assumptions context fields type uses
structure InferredArms (assumptions : Assumptions) (context : Context) (arms : List (String × Term)) where
  row : Ty
  result : Ty
  uses : Uses
  derivation : ArmsTyping assumptions context arms row result uses

/-- The scrutinee's row guides arm binder types; one declared variable head
unfolds, as in sameType. The final sameType premise is what is trusted. -/
def variantRow (assumptions : Assumptions) : Ty → Option Ty
  | .variant row => some row
  | .variable index => match assumptions.alias index with
    | some (.variant row) => some row
    | _ => none
  | _ => none

mutual
/-- Fuel bounds only the checker, never the runtime or meaning of Fix. Failure
means outside this annotated fragment/budget; it is not a proof of ill-typing in
any stronger language. The result carries a runtime-syntax derivation. -/
def infer (assumptions : Assumptions) (annotations : Annotations) (context : Context)
    (position : List Nat) : Nat → (term : Term) → Option (Inferred assumptions context term)
  | 0, _ => none
  | fuel + 1, .bound index => do
      let binding ← context[index]?
      if h : context[index]? = some binding then
        some ⟨binding.type, variableUses context index, .bound h⟩ else none
  | _ + 1, .nat value => some ⟨.natural, zeroUses context, .natural context value⟩
  | _ + 1, .boolean value => some ⟨.boolean, zeroUses context, .boolean context value⟩
  | _ + 1, .label value => some ⟨literalType value, zeroUses context, .label context value⟩
  | fuel + 1, .lam body => do
      let annotation ← annotations position
      let result ← infer assumptions annotations (⟨annotation.domain, annotation.parameter⟩ :: context) (position ++ [0]) fuel body
      if ht : agree assumptions result.type annotation.codomain = true then
        if hs : safeUses (⟨annotation.domain, annotation.parameter⟩ :: context) result.uses = true then
          if hv : validContext assumptions.shareableVariables (⟨annotation.domain, annotation.parameter⟩ :: context) = true then
            if hc : reusableAllowed assumptions annotation.reuse context result.uses.tail = true then
              some ⟨.arrow annotation.reuse annotation.parameter annotation.domain annotation.codomain, result.uses.tail,
                .lambda (.conversion result.derivation (agree_sameType ht)) hs hv hc⟩
            else none
          else none
        else none
      else none
  | fuel + 1, .app function argument => do
      let fn ← infer assumptions annotations context (position ++ [0]) fuel function
      let arg ← infer assumptions annotations context (position ++ [1]) fuel argument
      match hft : callable fn.type with
      | .arrow reuse quantity domain codomain =>
          if hat : agree assumptions arg.type domain = true then
            if hc : argumentAllowed assumptions quantity context domain arg.uses = true then
              some ⟨codomain, addUses fn.uses arg.uses, .application fn.derivation (.conversion arg.derivation (agree_sameType hat)) hft rfl hc⟩
            else none
          else none
      | _ => none
  | fuel + 1, .record fields => do
      let result ← inferFields assumptions annotations context position 0 fuel fields
      some ⟨result.type, result.uses, .record result.derivation⟩
  | fuel + 1, .get target name => do
      let result ← infer assumptions annotations context (position ++ [0]) fuel target
      let member ← result.type.lookup assumptions.bounds (fuel + 1) name
      if hm : result.type.lookup assumptions.bounds (fuel + 1) name = some member then
        some ⟨member, result.uses, .get result.derivation hm⟩ else none
  | fuel + 1, .extend target fields => do
      let prior ← infer assumptions annotations context (position ++ [0]) fuel target
      let members ← inferFields assumptions annotations context (position ++ [1]) 0 fuel fields
      if hr : prior.type.isRow assumptions.bounds (fuel + 64) = true then
        some ⟨overlay members.type prior.type, addUses prior.uses members.uses,
          .extend prior.derivation members.derivation hr⟩ else none
  | fuel + 1, .specification metadata extension => do
      let descriptor ← infer assumptions annotations context (position ++ [0]) fuel metadata
      let body ← infer assumptions annotations context (position ++ [1]) fuel extension
      if hm : descriptor.type.isComputation = false then
        if he : body.type.isComputation = false then
          some ⟨.specification descriptor.type body.type, addUses descriptor.uses body.uses,
            .specification descriptor.derivation body.derivation hm he⟩
        else none
      else none
  | fuel + 1, .prototype spec target => do
      let code ← infer assumptions annotations context (position ++ [0]) fuel spec
      let value ← infer assumptions annotations context (position ++ [1]) fuel target
      if hs : code.type.isComputation = false then
        if ht : value.type.isComputation = false then
          some ⟨.prototype code.type value.type, addUses code.uses value.uses,
            .prototype code.derivation value.derivation hs ht⟩
        else none
      else none
  | fuel + 1, .reflect target => do
      let result ← infer assumptions annotations context (position ++ [0]) fuel target
      match ht : result.type with
      | .prototype specType targetType =>
          some ⟨specType, result.uses, .reflect (ht ▸ result.derivation)⟩
      | _ => none
  | fuel + 1, .metadata target => do
      let result ← infer assumptions annotations context (position ++ [0]) fuel target
      match ht : result.type with
      | .specification metadataType extensionType =>
          some ⟨metadataType, result.uses, .metadata (ht ▸ result.derivation)⟩
      | _ => none
  | fuel + 1, .project target => do
      let result ← infer assumptions annotations context (position ++ [0]) fuel target
      match ht : result.type with
      | .prototype specType targetType =>
          some ⟨targetType, result.uses, .project (ht ▸ result.derivation)⟩
      | _ => none
  | fuel + 1, .mix lower upper => do
      let first ← infer assumptions annotations context (position ++ [0]) fuel lower
      let second ← infer assumptions annotations context (position ++ [1]) fuel upper
      match ht : callable first.type, hs : callable second.type with
      | .arrow .reusable .unrestricted self (.arrow .reusable .unrestricted inherited middle),
        .arrow .reusable .unrestricted self' (.arrow .reusable .unrestricted middle' provided) =>
          if hc : self' = self then
            if hm : middle' = middle then
              if captures : reusableCaptures assumptions.shareableVariables context (addUses first.uses second.uses) = true then
                if shareSelf : self.shareableUnder assumptions.shareableVariables = true then
                  if shareInherited : inherited.shareableUnder assumptions.shareableVariables = true then
                    if shareMiddle : middle.shareableUnder assumptions.shareableVariables = true then
                      some ⟨.arrow .reusable .unrestricted self (.arrow .reusable .unrestricted inherited provided),
                        addUses first.uses second.uses,
                        .mix first.derivation second.derivation ht (by simpa [hc, hm] using hs)
                          captures shareSelf shareInherited shareMiddle⟩
                    else none
                  else none
                else none
              else none
            else none
          else none
      | _, _ => none
  | fuel + 1, .fix spec inheritedTerm => do
      let code ← infer assumptions annotations context (position ++ [0]) fuel spec
      let base ← infer assumptions annotations context (position ++ [1]) fuel inheritedTerm
      match ht : callable code.type with
      | .arrow .reusable .unrestricted target (.arrow .reusable .unrestricted inherited output) =>
          if ho : output = target then
            if hb : agree assumptions base.type inherited = true then
              if hs : target.shareableUnder assumptions.shareableVariables = true then
                if ha : argumentAllowed assumptions .unrestricted context inherited base.uses = true then
                  if hc : reusableCaptures assumptions.shareableVariables context code.uses = true then
                    some ⟨target, addUses code.uses base.uses,
                      .fix code.derivation (by simpa [ho] using ht) (.conversion base.derivation (agree_sameType hb)) hs ha hc⟩
                  else none
                else none
              else none
            else none
          else none
      | _ => none
  | fuel + 1, .binary primitive left right => do
      let l ← infer assumptions annotations context (position ++ [0]) fuel left
      let r ← infer assumptions annotations context (position ++ [1]) fuel right
      if hl : l.type = (primitiveTypes primitive).1 then
        if hr : r.type = (primitiveTypes primitive).1 then
          some ⟨(primitiveTypes primitive).2, addUses l.uses r.uses,
            .binary (Prod.eta _) (hl ▸ l.derivation) (hr ▸ r.derivation)⟩
        else none
      else none
  | fuel + 1, .ifZero value zero successor => do
      let condition ← infer assumptions annotations context (position ++ [0]) fuel value
      let z ← infer assumptions annotations context (position ++ [1]) fuel zero
      let s ← infer assumptions annotations (⟨.natural,.unrestricted⟩ :: context) (position ++ [2]) fuel successor
      if ht : condition.type = .natural then
        if hb : s.type = z.type then
          if hu : safeUses (⟨.natural,.unrestricted⟩ :: context) s.uses = true then
            some ⟨z.type, addUses condition.uses (addUses z.uses s.uses.tail),
              .ifZero (ht ▸ condition.derivation) z.derivation (hb ▸ s.derivation) hu⟩
          else none
        else none
      else none
  | fuel + 1, .inject tag payload => do
      let annotation ← annotations position
      let value ← infer assumptions annotations context (position ++ [0]) fuel payload
      if hk : annotation.parameter = .unrestricted ∧ annotation.reuse = .reusable then
        match annotation.codomain with
        | .variant row =>
            if hm : row.lookup assumptions.bounds (fuel + 1) tag = some annotation.domain then
              if hs : agree assumptions value.type annotation.domain = true then
                if hp : annotation.domain.isComputation = false then
                  some ⟨.variant row, value.uses, .inject (.conversion value.derivation (agree_sameType hs)) hm hp⟩
                else none
              else none
            else none
        | .variable index =>
          -- A recursive sum is declared as its bounded variable: inject at the
          -- bound's row, then convert to the variable (one declared head unfolds),
          -- so a nested injection already carries the sum's declared name.
          match assumptions.alias index with
          | some (.variant row) =>
            if hm : row.lookup assumptions.bounds (fuel + 1) tag = some annotation.domain then
              if hs : agree assumptions value.type annotation.domain = true then
                if hp : annotation.domain.isComputation = false then
                  if hc : sameType assumptions (.variant row) (.variable index) = true then
                    some ⟨.variable index, value.uses,
                      .conversion (.inject (.conversion value.derivation (agree_sameType hs)) hm hp) hc⟩
                  else none
                else none
              else none
            else none
          | _ => none
        | _ => none
      else none
  | fuel + 1, .case scrutinee arms => do
      let value ← infer assumptions annotations context (position ++ [0]) fuel scrutinee
      match value.type with
      | .computation _ _ produced =>
        let row ← variantRow assumptions produced
        let typed ← inferArms assumptions annotations context (position ++ [1]) 0 row none fuel arms
        match hr : typed.result with
        | .computation planType response result =>
          if hc : agree assumptions value.type (.computation planType response (.variant typed.row)) = true then
            if hn : result.isComputation = false then
              some ⟨.computation planType response result, addUses value.uses typed.uses,
                .effectCase (.conversion value.derivation (agree_sameType hc)) (hr ▸ typed.derivation) hn⟩
            else none
          else none
        | _ => none
      | _ =>
      let row ← variantRow assumptions value.type
      let typed ← inferArms assumptions annotations context (position ++ [1]) 0 row none fuel arms
      if hc : agree assumptions value.type (.variant typed.row) = true then
        some ⟨typed.result, addUses value.uses typed.uses, .case (.conversion value.derivation (agree_sameType hc)) typed.derivation⟩
      else none
  | fuel + 1, .ifBool condition whenTrue whenFalse => do
      let c ← infer assumptions annotations context (position ++ [0]) fuel condition
      let t ← infer assumptions annotations context (position ++ [1]) fuel whenTrue
      let f ← infer assumptions annotations context (position ++ [2]) fuel whenFalse
      if hc : c.type = .boolean then
        if hb : f.type = t.type then
          some ⟨t.type, addUses c.uses (addUses t.uses f.uses),
            .ifBool (hc ▸ c.derivation) t.derivation (hb ▸ f.derivation)⟩
        else none
      else none
  | fuel + 1, .perform plan => do
      -- The annotation at a perform's position is its effect signature:
      -- domain = the Plan sum, codomain = the response data type.
      let annotation ← annotations position
      let value ← infer assumptions annotations context (position ++ [0]) fuel plan
      if hs : agree assumptions value.type annotation.domain = true then
        if hp : annotation.domain.isPlan = true then
          if hr : annotation.codomain.isData = true then
            some ⟨.computation annotation.domain annotation.codomain annotation.codomain, value.uses,
              .perform (.conversion value.derivation (agree_sameType hs)) hp hr⟩
          else none
        else none
      else none
  | fuel + 1, .done inner => do
      -- The annotation at `done` names the activity's Plan and response types.
      let annotation ← annotations position
      let value ← infer assumptions annotations context (position ++ [0]) fuel inner
      if hn : value.type.isComputation = false then
        some ⟨.computation annotation.domain annotation.codomain value.type, value.uses,
          .done value.derivation hn⟩
      else none

def inferFields (assumptions : Assumptions) (annotations : Annotations) (context : Context)
    (position : List Nat) (index : Nat) : Nat → (fields : List (String × Term)) → Option (InferredFields assumptions context fields)
  | 0, _ => none
  | _ + 1, [] => some ⟨.emptyRow, zeroUses context, .nil context⟩
  | fuel + 1, (name,body) :: rest => do
      let first ← infer assumptions annotations context (position ++ [index]) fuel body
      let later ← inferFields assumptions annotations context position (index + 1) fuel rest
      if hc : first.type.isComputation = false then
        some ⟨.field name first.type later.type, addUses first.uses later.uses, .cons first.derivation later.derivation hc⟩
      else none

/-- Every arm body is checked under its label's payload type in the scrutinee
row; all arms must agree exactly on the result type. Empty arm lists have no
result type to infer and are refused here (the relation itself permits them). -/
def inferArms (assumptions : Assumptions) (annotations : Annotations) (context : Context)
    (position : List Nat) (index : Nat) (scrutineeRow : Ty) (expected : Option Ty) :
    Nat → (arms : List (String × Term)) → Option (InferredArms assumptions context arms)
  | 0, _ => none
  | _ + 1, [] => match expected with
    | some result => some ⟨.emptyRow, result, zeroUses context, .nil context result⟩
    | none => none
  | fuel + 1, (name,body) :: rest => do
      let payload ← scrutineeRow.lookup assumptions.bounds (fuel + 1) name
      if hs : payload.shareableUnder assumptions.shareableVariables = true then
        let first ← infer assumptions annotations (⟨payload,.unrestricted⟩ :: context) (position ++ [index]) fuel body
        if hu : safeUses (⟨payload,.unrestricted⟩ :: context) first.uses = true then
          let later ← inferArms assumptions annotations context position (index + 1) scrutineeRow (some first.type) fuel rest
          if hl : later.result = first.type then
            some ⟨.field name payload later.row, first.type, addUses first.uses.tail later.uses,
              .cons first.derivation hu hs (hl ▸ later.derivation)⟩
          else none
        else none
      else none
end

structure Checked (source : AnnotatedTerm) (context : Context) where
  type : Ty
  uses : Uses
  derivation : PartialTyping source.assumptions context source.erase type uses
  safe : safeUses context uses = true
  contextValid : validContext source.assumptions.shareableVariables context = true
  assumptionsValid : source.assumptions.valid = true

def check (source : AnnotatedTerm) (context : Context) (fuel : Nat) : Option (Checked source context) := do
  let result ← infer source.assumptions source.annotations context [] fuel source.term
  if hs : safeUses context result.uses = true then
    if hv : validContext source.assumptions.shareableVariables context = true then
      if ha : source.assumptions.valid = true then
        some ⟨result.type, result.uses, result.derivation, hs, hv, ha⟩ else none
    else none
  else none

/-- Successful checking constructs a derivation for exactly the consumed runtime
term, together with capture/usage premises. This is not preservation/adequacy. -/
theorem checked_erasure (source : AnnotatedTerm) (context : Context)
    (result : Checked source context) :
    PartialTyping source.assumptions context source.erase result.type result.uses := result.derivation

/-- Total proof judgments inhabit Lean Prop, including laws of partial runtime
syntax. No Typing constructor can convert arbitrary Fix into a total proof. -/
def TotalProof (law : Prop) := law

theorem partial_beta_law (body argument : Term) :
    TotalProof (Step (.app (.lam body) argument) (instantiate body argument)) := .beta body argument

/-- Inherited/required/provided annotations all feed checking. Requirements are
finite structural row contracts, independently checked against future Self;
provider type is the heterogeneous two-arrow family, not a subtype oracle. -/
structure CheckedExtension (source : AnnotatedTerm) (context : Context)
    (family : ExtensionFamilies) (futureSelf : Ty) where
  checked : Checked source context
  shape : checked.type = family.functionType futureSelf
  required : futureSelf.supports source.assumptions.bounds 64 family.required = true

def checkExtension (source : AnnotatedTerm) (context : Context) (fuel : Nat)
    (family : ExtensionFamilies) (futureSelf : Ty) : Option (CheckedExtension source context family futureSelf) := do
  let result ← check source context fuel
  if ht : result.type = family.functionType futureSelf then
    if hr : futureSelf.supports source.assumptions.bounds 64 family.required = true then
      some ⟨result,ht,hr⟩ else none
  else none

/-- Reusability is justified by a checked capture premise, not by the immutable
shape of a closure/record wrapper. This holds for every lambda derivation. -/
theorem reusable_lambda_capture_rule {assumptions : Assumptions} {context : Context}
    {body : Term} {annotation : LambdaAnnotation} {uses : Uses}
    (_bodyTyped : PartialTyping assumptions (⟨annotation.domain,annotation.parameter⟩ :: context)
      body annotation.codomain uses)
    (_safe : safeUses (⟨annotation.domain,annotation.parameter⟩ :: context) uses = true)
    (_valid : validContext assumptions.shareableVariables (⟨annotation.domain,annotation.parameter⟩ :: context) = true)
    (captures : reusableAllowed assumptions annotation.reuse context uses.tail = true)
    (reusable : annotation.reuse = .reusable) :
    reusableCaptures assumptions.shareableVariables context uses.tail = true := by
  simpa [reusableAllowed, reusable] using captures

/-- Total logic proves a contextual reduction law despite the discarded
argument being any partial computation, including a divergent Fix. -/
theorem ignores_any_partial_argument (argument : Term) :
    TotalProof (Evaluates (.app (.lam (.nat 7)) argument) (.nat 7)) :=
  by
    refine ⟨.next (.beta _ _) ?_, .natural 7⟩
    simpa [instantiate, Term.substitute] using (Steps.refl (.nat 7))

def reusableNaturalCapture : AnnotatedTerm :=
  ⟨.lam (.bound 1), fun _ => some ⟨.natural,.natural,.erased,.reusable⟩, {}⟩
def custodyCapture (reuse : Reuse) : AnnotatedTerm :=
  ⟨.lam (.bound 1), fun _ => some ⟨.natural,.custody 17,.erased,reuse⟩, {}⟩

theorem reusable_lexical_capture_accepted :
    (check reusableNaturalCapture [⟨.natural,.unrestricted⟩] 8).isSome = true := by decide

theorem custody_in_reusable_closure_refused :
    (check (custodyCapture .reusable) [⟨.custody 17,.linear⟩] 8).isNone = true := by decide

theorem custody_in_once_closure_accepted :
    (check (custodyCapture .once) [⟨.custody 17,.linear⟩] 8).isSome = true := by decide

def duplicateAffine : AnnotatedTerm :=
  ⟨.binary .add (.bound 0) (.bound 0), fun _ => none, {}⟩
theorem duplicate_affine_refused :
    (check duplicateAffine [⟨.natural,.affine⟩] 8).isNone = true := by decide

def hiddenCustody : AnnotatedTerm := ⟨.bound 0, fun _ => none, {}⟩
theorem record_wrapper_does_not_hide_custody :
    (check hiddenCustody [⟨.field "authority" (.custody 17) .emptyRow,.unrestricted⟩] 8).isNone = true := by decide

/-- Independently typed Unit-row→Nat and Nat→Label extensions compose under
one final Nat self; neither targets only records nor homogeneous endomorphisms. -/
def heterogeneousSource : AnnotatedTerm :=
  ⟨.mix (.lam (.lam (.nat 7))) (.lam (.lam (.label "done"))),
    fun position =>
      if position = [0] then some ⟨.natural,.arrow .reusable .unrestricted .emptyRow .natural,.unrestricted,.reusable⟩
      else if position = [0,0] then some ⟨.emptyRow,.natural,.unrestricted,.reusable⟩
      else if position = [1] then some ⟨.natural,.arrow .reusable .unrestricted .natural .label,.unrestricted,.reusable⟩
      else if position = [1,0] then some ⟨.natural,.label,.unrestricted,.reusable⟩ else none, {}⟩
theorem heterogeneous_runtime_mix_accepted :
    (check heterogeneousSource [] 16).isSome = true := by decide

/-- Symbolic future Self has a self-dependent binary method bound; future Super
is passed through as an unknown row and receives a new field. No closed record
or fixed C→V(C) is substituted into this independent source derivation. -/
def futureRowSource : AnnotatedTerm :=
  ⟨.lam (.lam (.extend (.bound 0) [("answer",.nat 42)])),
    fun position =>
      if position = [] then some ⟨.variable 0,
        .arrow .reusable .unrestricted (.variable 1) (.field "answer" .natural (.variable 1)),.unrestricted,.reusable⟩
      else if position = [0] then some ⟨.variable 1,.field "answer" .natural (.variable 1),.unrestricted,.reusable⟩
      else none,
    ⟨[(0,.field "combine" (.arrow .reusable .unrestricted (.variable 0) (.variable 0)) .emptyRow),
       (1,.emptyRow)], [0,1], []⟩⟩

theorem independently_checked_future_rows :
    (check futureRowSource [] 16).isSome = true := by decide

def futureRowChecked : Checked futureRowSource [] :=
  (check futureRowSource [] 16).get independently_checked_future_rows

/-- This source can be separately instantiated at EVERY future Self/Super type
in the declared shareable fragment. Unknown members stay in Super itself, not
in a fixed closed record chosen during extension compilation. -/
def futureRowInstantiation (self super : Ty) : AnnotatedTerm :=
  ⟨futureRowSource.term, fun position =>
    if position = [] then some ⟨self,
      .arrow .reusable .unrestricted super (.field "answer" .natural super),.unrestricted,.reusable⟩
    else if position = [0] then some ⟨super,.field "answer" .natural super,.unrestricted,.reusable⟩
    else none, {}⟩

theorem future_row_instantiation_accepted (self super : Ty)
    (selfShareable : self.shareable = true) (superShareable : super.shareable = true)
    (superRow : super.isRow [] 64 = true) :
    (check (futureRowInstantiation self super) [] 16).isSome = true := by
  simp [check, infer, inferFields, futureRowInstantiation, futureRowSource, agree,
    sameType, Assumptions.alias, Assumptions.valid, overlay, zeroUses, variableUses, addUses, safeUses, safeQuantity,
    validContext, reusableAllowed, reusableCaptures,
    List.range_succ, List.zipWith, selfShareable, superShareable, (Ty.isRow_mono superRow (by omega) : super.isRow [] 77 = true),
    Ty.isComputation]

/-- A total law provider proves a law ABOUT the partial runtime term; source
law names alone cannot construct this evidence. Compatible retention is chosen
explicitly rather than asserted as a universal consequence of inheritance. -/
structure LawProvider (source : AnnotatedTerm) (law : Term → Prop) where
  evidence : law source.erase

structure RetainedContracts (source : AnnotatedTerm) (laws : List (Term → Prop)) where
  providers : ∀ law ∈ laws, LawProvider source law

def FutureRowTyped (source : Ty → Ty → AnnotatedTerm) : Prop :=
  ∀ self super, self.shareable = true → super.shareable = true → super.isRow [] 64 = true →
    ∃ checked : Checked (source self super) [],
      checked.type = .arrow .reusable .unrestricted self
        (.arrow .reusable .unrestricted super (.field "answer" .natural super))


def futureRowInstanceChecked (self super : Ty)
    (selfShareable : self.shareable = true) (superShareable : super.shareable = true)
    (superRow : super.isRow [] 64 = true) : Checked (futureRowInstantiation self super) [] :=
  (check (futureRowInstantiation self super) [] 16).get
    (future_row_instantiation_accepted self super selfShareable superShareable superRow)

theorem future_row_typed : FutureRowTyped futureRowInstantiation := by
  intro self super hs ht hr
  refine ⟨futureRowInstanceChecked self super hs ht hr, ?_⟩
  simp [futureRowInstanceChecked, check, infer, inferFields, futureRowInstantiation,
    futureRowSource, Assumptions.alias, Assumptions.valid, overlay, zeroUses, variableUses, addUses, safeUses, safeQuantity,
    validContext, reusableAllowed, reusableCaptures,
    List.range_succ, List.zipWith, hs, ht, (Ty.isRow_mono hr (by omega) : super.isRow [] 77 = true), Ty.isComputation]

/-- Independently authored code changes a self-sensitive method type at every
future Self instantiation, including negative arrow occurrences. -/
def futureBinaryInstantiation (self super : Ty) : AnnotatedTerm :=
  ⟨.lam (.lam (.extend (.bound 0) [("combine",.lam (.bound 0))])),
    fun position =>
      if position = [] then some ⟨self,
        .arrow .reusable .unrestricted super
          (.field "combine" (.arrow .reusable .unrestricted self self) super),.unrestricted,.reusable⟩
      else if position = [0] then some ⟨super,
        .field "combine" (.arrow .reusable .unrestricted self self) super,.unrestricted,.reusable⟩
      else if position = [0,0,1,0] then some ⟨self,self,.unrestricted,.reusable⟩
      else none, {}⟩

theorem future_binary_instantiation_accepted (self super : Ty)
    (selfShareable : self.shareable = true) (superShareable : super.shareable = true)
    (superRow : super.isRow [] 64 = true) :
    (check (futureBinaryInstantiation self super) [] 20).isSome = true := by
  simp [check, infer, inferFields, futureBinaryInstantiation, agree, sameType, Assumptions.alias, Assumptions.valid, overlay,
    zeroUses, variableUses, addUses, safeUses, safeQuantity,
    validContext, reusableAllowed, reusableCaptures,
    List.range_succ, List.zipWith, selfShareable, superShareable,
    (Ty.isRow_mono superRow (by omega) : super.isRow [] 81 = true), Ty.isComputation]

def scalarExtend : AnnotatedTerm :=
  ⟨.extend (.nat 3) [("answer",.nat 42)], fun _ => none, {}⟩
theorem scalar_record_extend_refused : (check scalarExtend [] 8).isNone = true := by decide


/-- Mix's generated reusable closure owns both captured operands. The previous
rule accepted this affine free binding despite ordinary lambda refusing it. -/
def extensionNaturalType : Ty :=
  .arrow .reusable .unrestricted .natural (.arrow .reusable .unrestricted .natural .natural)
def capturedMixSource : AnnotatedTerm :=
  ⟨.mix (.bound 0) (.lam (.lam (.bound 0))), fun position =>
    if position = [1] then some ⟨.natural,.arrow .reusable .unrestricted .natural .natural,.unrestricted,.reusable⟩
    else if position = [1,0] then some ⟨.natural,.natural,.unrestricted,.reusable⟩ else none, {}⟩
theorem affine_mix_capture_refused :
    (check capturedMixSource [⟨extensionNaturalType,.affine⟩] 16).isNone = true := by decide

theorem reusable_mix_capture_accepted :
    (check capturedMixSource [⟨extensionNaturalType,.unrestricted⟩] 16).isSome = true := by decide

def recursiveGlobalKnot : AnnotatedTerm :=
  ⟨.get (.fix (.lam (.lam (.record [("answer",.nat 42)]))) (.record [])) "answer",
    fun position =>
      if position = [0,0] then some ⟨.variable 0,
        .arrow .reusable .unrestricted .emptyRow (.variable 0),.unrestricted,.reusable⟩
      else if position = [0,0,0] then some ⟨.emptyRow,.variable 0,.unrestricted,.reusable⟩
      else none,
    ⟨[(0,.field "answer" .natural .emptyRow)],[0],[]⟩⟩
theorem recursive_global_knot_accepted : (check recursiveGlobalKnot [] 16).isSome = true := by decide

def dishonestRecursiveCustody : AnnotatedTerm :=
  ⟨.nat 7, fun _ => none, ⟨[(0,.field "authority" (.custody 17) (.variable 0))],[0],[]⟩⟩
theorem recursive_alias_does_not_hide_custody :
    (check dishonestRecursiveCustody [] 8).isNone = true := by decide

def stringConjunction : AnnotatedTerm :=
  ⟨.binary .conjunction (.label "hello") (.label "world"), fun _ => none, {}⟩
theorem arbitrary_labels_are_not_booleans : (check stringConjunction [] 8).isNone = true := by decide

def reservedStringConjunction : AnnotatedTerm :=
  ⟨.binary .conjunction (.label "true") (.label "false"), fun _ => none, {}⟩
theorem reserved_strings_are_not_booleans :
    (check reservedStringConjunction [] 8).isNone = true := by decide
theorem reserved_string_has_string_type :
    (check ⟨.label "true", fun _ => none, {}⟩ [] 8).map (fun checked => checked.type) = some .label := by decide
theorem explicit_boolean_has_boolean_type :
    (check ⟨.boolean true, fun _ => none, {}⟩ [] 8).map (fun checked => checked.type) = some .boolean := by decide
theorem explicit_boolean_conjunction_accepted :
    (check ⟨.binary .conjunction (.boolean true) (.boolean false), fun _ => none, {}⟩ [] 8).isSome = true := by decide


def independentlyAuthoredFamily : ExtensionFamilies :=
  ⟨.variable 1,
    .field "combine" (.arrow .reusable .unrestricted (.variable 0) (.variable 0)) .emptyRow,
    .field "answer" .natural (.variable 1)⟩

theorem independent_requirements_checked :
    (checkExtension futureRowSource [] 16 independentlyAuthoredFamily (.variable 0)).isSome = true := by decide

def unmetFamily : ExtensionFamilies :=
  { independentlyAuthoredFamily with required := .field "absent" .natural .emptyRow }
theorem absent_future_requirement_refused :
    (checkExtension futureRowSource [] 16 unmetFamily (.variable 0)).isNone = true := by decide


/-- A closed two-label sum; arms checked against it in any source order. -/
def shapeRow : Ty := .field "circle" .natural (.field "square" .natural .emptyRow)
def shapeInjection : LambdaAnnotation := ⟨.natural,.variant shapeRow,.unrestricted,.reusable⟩
def shapeCase (arms : List (String × Term)) (tag : String) : AnnotatedTerm :=
  ⟨.case (.inject tag (.nat 4)) arms, fun position => if position = [0] then some shapeInjection else none, {}⟩
def shapeArms : List (String × Term) := [("circle",.bound 0),("square",.binary .add (.bound 0) (.nat 1))]

theorem exhaustive_case_accepted :
    (check (shapeCase shapeArms "square") [] 16).map (fun checked => checked.type) = some .natural := by decide
theorem reordered_arms_accepted :
    (check (shapeCase shapeArms.reverse "circle") [] 16).isSome = true := by decide
theorem missing_arm_refused :
    (check (shapeCase [("circle",.bound 0)] "circle") [] 16).isNone = true := by decide
theorem extra_arm_refused :
    (check (shapeCase (shapeArms ++ [("triangle",.bound 0)]) "circle") [] 16).isNone = true := by decide
theorem undeclared_injection_refused :
    (check (shapeCase shapeArms "triangle") [] 16).isNone = true := by decide
theorem unannotated_injection_refused :
    (check ⟨.inject "circle" (.nat 4), fun _ => none, {}⟩ [] 16).isNone = true := by decide
theorem arm_results_must_agree :
    (check (shapeCase [("circle",.bound 0),("square",.label "four")] "circle") [] 16).isNone = true := by decide

/-- Natural equality drives a Boolean branch; a label is not a condition. -/
theorem equality_branch_accepted :
    (check ⟨.ifBool (.binary .equal (.nat 2) (.nat 2)) (.label "same") (.label "different"),
      fun _ => none, {}⟩ [] 16).map (fun checked => checked.type) = some .label := by decide
theorem label_condition_refused :
    (check ⟨.ifBool (.label "true") (.nat 1) (.nat 0), fun _ => none, {}⟩ [] 16).isNone = true := by decide
theorem label_equality_accepted :
    (check ⟨.binary .labelEqual (.label "a") (.label "b"), fun _ => none, {}⟩ [] 8).map
      (fun checked => checked.type) = some .boolean := by decide
theorem boolean_label_equality_refused :
    (check ⟨.binary .labelEqual (.boolean true) (.boolean true), fun _ => none, {}⟩ [] 8).isNone = true := by decide

/-- Truncated subtraction, floor division and remainder are Nat-to-Nat; the order primitives are
Nat-to-Bool and drive a Boolean branch; none takes a label or a Boolean operand. -/
theorem nat_primitive_types :
    ∀ primitive, primitive = .subtract ∨ primitive = .divide ∨ primitive = .modulo →
      (check ⟨.binary primitive (.nat 9) (.nat 4), fun _ => none, {}⟩ [] 8).map
        (fun checked => checked.type) = some .natural := by
  intro primitive choice; rcases choice with rfl | rfl | rfl <;> decide
theorem order_primitive_branch_accepted :
    ∀ primitive, primitive = .less ∨ primitive = .lessEqual →
      (check ⟨.ifBool (.binary primitive (.nat 3) (.nat 4)) (.label "below") (.label "above"),
        fun _ => none, {}⟩ [] 16).map (fun checked => checked.type) = some .label := by
  intro primitive choice; rcases choice with rfl | rfl <;> decide
theorem nat_primitive_label_operand_refused :
    ∀ primitive, primitive = .subtract ∨ primitive = .divide ∨ primitive = .less ∨ primitive = .lessEqual ∨
      primitive = .modulo →
      (check ⟨.binary primitive (.label "9") (.nat 4), fun _ => none, {}⟩ [] 8).isNone = true ∧
      (check ⟨.binary primitive (.nat 9) (.boolean true), fun _ => none, {}⟩ [] 8).isNone = true := by
  intro primitive choice; rcases choice with rfl | rfl | rfl | rfl | rfl <;> decide

/-- An affine binding used in two arms counts twice: arms are additive. -/
theorem affine_in_two_arms_refused :
    (check ⟨.case (.inject "circle" (.nat 4)) [("circle",.bound 1),("square",.bound 1)],
      fun position => if position = [0] then some shapeInjection else none, {}⟩
      [⟨.natural,.affine⟩] 16).isNone = true := by decide
theorem affine_in_one_arm_accepted :
    (check ⟨.case (.inject "circle" (.nat 4)) [("circle",.bound 1),("square",.nat 0)],
      fun position => if position = [0] then some shapeInjection else none, {}⟩
      [⟨.natural,.affine⟩] 16).isSome = true := by decide

/-! ## A recursive sum is injected at its declared bounded variable

`Sums.obend`'s `total` builds `List.cons({head, tail: List.cons(..)})`. The
recursive sum `List` is the bounded variable 0 (bound: the variant row, whose
`tail` member is variable 0); an injection's codomain is that variable, so the
nested payload `tail` agrees with its declared member (cv 01a10564-84a1: the
checker refused this before the injection rule carried the variable codomain,
W3.EVENTS 6b2616db; refused/accepted logs in the W25 evidence). -/

def listRow : Ty :=
  .field "nil" .emptyRow (.field "cons" (.field "head" .natural (.field "tail" (.variable 0) .emptyRow)) .emptyRow)
def listAssumptions : Assumptions := ⟨[(0, .variant listRow)], [0], []⟩
def listAnnotations : Annotations := fun position =>
  if position = [] then
    some ⟨.field "head" .natural (.field "tail" (.variable 0) .emptyRow), .variable 0, .unrestricted, .reusable⟩
  else if position = [0,1] then some ⟨.emptyRow, .variable 0, .unrestricted, .reusable⟩
  else none
def listCons (tail : Term) : AnnotatedTerm :=
  ⟨.inject "cons" (.record [("head", .nat 1), ("tail", tail)]), listAnnotations, listAssumptions⟩

theorem recursive_sum_list_accepted :
    (check (listCons (.inject "nil" (.record []))) [] 32).map (fun checked => checked.type) = some (.variable 0) := by
  decide

/-- Planted ill-typed control: a Nat where the recursive tail belongs. -/
theorem recursive_sum_ill_typed_tail_refused :
    (check (listCons (.nat 3)) [] 32).isNone = true := by decide

/-! ## Canonical shadowing must not manufacture shareability

AUDIT (W25, cv 01a10505-46cf). `Ty.canonical` forgets a shadowed member, so
`{a: Nat, a: custody}` agrees with `{a: Nat}` although only the second is
shareable. Before this change the checker ACCEPTED `shadowProgram (.bound 0)` in
a context holding a linear custody: the custody is built into the second `a` of
a record that is injected at the declared shareable row `{a: Nat}`, and the
arm binds that payload unrestricted. So the judgement labelled a value that
carries a custody (or a once closure) shareable: hole = YES at the type level.
What it did not do: the machine's field lookup is first-match, so the hidden
member is unreachable by `get`/`case`; no program could duplicate the custody
itself. The defect was a mislabelled type that every shareability rule trusts.
Conversions the checker inserts now go through `agree`, which refuses to
manufacture shareability (`shadowed_*_refused` below). -/

def shadowRow : Ty := .field "a" .natural .emptyRow
def shadowSum : Ty := .variant (.field "l" shadowRow .emptyRow)

/-- `case (inject l {a = 1, a = <hidden>}) of l(p) => p.a + p.a`, the payload
declared at the shareable row `{a: Nat}`. -/
def shadowProgram (hidden : Term) (hiddenAnnotation : Annotations) : AnnotatedTerm :=
  ⟨.case (.inject "l" (.record [("a", .nat 1), ("a", hidden)]))
      [("l", .binary .add (.get (.bound 0) "a") (.get (.bound 0) "a"))],
   fun position => if position = [0] then some ⟨shadowRow, shadowSum, .unrestricted, .reusable⟩
     else hiddenAnnotation position, {}⟩

/-- Agreement holds, shareability differs: the exact gap `agree` closes. -/
theorem canonical_agreement_loses_shareability :
    sameType {} (.field "a" .natural (.field "a" (.custody 17) .emptyRow)) shadowRow = true ∧
    (Ty.field "a" .natural (.field "a" (.custody 17) .emptyRow)).shareable = false ∧
    shadowRow.shareable = true ∧
    agree {} (.field "a" .natural (.field "a" (.custody 17) .emptyRow)) shadowRow = false := by decide

/-- REFUSED (was accepted): a linear custody hidden behind a shadowing field. -/
theorem shadowed_custody_laundering_refused :
    (check (shadowProgram (.bound 0) (fun _ => none)) [⟨.custody 17,.linear⟩] 32).isNone = true := by decide

/-- REFUSED (was accepted): a once closure hidden behind a shadowing field. -/
theorem shadowed_once_closure_laundering_refused :
    (check (shadowProgram (.lam (.bound 0))
      (fun position => if position = [0,0,1] then some ⟨.natural,.natural,.unrestricted,.once⟩ else none))
      [] 32).isNone = true := by decide

/-- Control: the same program with a shareable hidden member is accepted. -/
theorem shadowed_shareable_member_accepted :
    (check (shadowProgram (.bound 0) (fun _ => none)) [⟨.natural,.linear⟩] 32).map
      (fun checked => checked.type) = some .natural := by decide

/-- Control: overriding a field through `extend` (the shadowing's purpose) still
agrees at the shareable row. -/
theorem shadowed_override_accepted :
    (check ⟨.case (.inject "l" (.extend (.record [("a", .nat 0)]) [("a", .nat 1)]))
      [("l", .binary .add (.get (.bound 0) "a") (.get (.bound 0) "a"))],
      fun position => if position = [0] then some ⟨shadowRow, shadowSum, .unrestricted, .reusable⟩ else none, {}⟩
      [] 32).map (fun checked => checked.type) = some .natural := by decide

/-- A conversion never turns a non-shareable type shareable, whatever the rows. -/
theorem agree_never_manufactures_shareability (assumptions : Assumptions) (actual expected : Ty)
    (agreement : agree assumptions actual expected = true)
    (expectedShareable : expected.shareableUnder assumptions.shareableVariables = true) :
    actual.shareableUnder assumptions.shareableVariables = true :=
  agree_shareable agreement expectedShareable

open Lean (Json toJson)

def requireSome {α : Type} (message : String) : Option α → Except String α
  | some value => .ok value
  | none => .error message

def jsonNat (value : Json) : Except String Nat :=
  match value.getNat? with
  | .ok result => .ok result
  | .error _ => do
      let text ← value.getStr?
      let result ← requireSome "canonical natural required" text.toNat?
      if toString result = text then .ok result else .error "canonical natural required"

def decodeQuantity (value : Json) : Except String Quantity := do
  match ← value.getStr? with
  | "erased" => pure .erased | "affine" => pure .affine
  | "linear" => pure .linear | "unrestricted" => pure .unrestricted
  | _ => .error "explicit Objective quantity required"

def decodeReuse (value : Json) : Except String Reuse := do
  match ← value.getStr? with
  | "once" => pure .once | "reusable" => pure .reusable
  | _ => .error "explicit Objective closure reuse required"

/-- A type on the wire, with its depth. A type is an object `{tag, ...}` whose children
are types, or `{tag:"ref", index}` naming an EARLIER entry of the packet's type table
(`decodeTypeTable`). A ref stands for exactly the type the entry decoded to, depth
included: `decodeTypeWith table fuel` accepts a tree iff the fully inlined JSON of that
tree is accepted by `decodeTypeWith #[] fuel`, and decodes it to the same `Ty`. The table
only shares storage; it changes neither which types a proposal may name nor the
nesting capacity. -/
def decodeTypeWith (table : Array (Ty × Nat)) : Nat → Json → Except String (Ty × Nat)
  | 0, _ => .error "type nesting capacity"
  | fuel + 1, value => do
    match ← value.getObjValAs? String "tag" with
    | "ref" =>
        let index ← jsonNat (← value.getObjVal? "index")
        let some (entry, depth) := table[index]? | .error "type reference names no earlier table entry"
        if depth > fuel + 1 then throw "type nesting capacity"
        pure (entry, depth)
    | "natural" => pure (.natural, 1) | "label" => pure (.label, 1)
    | "boolean" => pure (.boolean, 1) | "emptyRow" => pure (.emptyRow, 1)
    | "variable" => return (.variable (← jsonNat (← value.getObjVal? "index")), 1)
    | "custody" => return (.custody (← jsonNat (← value.getObjVal? "identity")), 1)
    | "field" =>
        let (member, dm) ← decodeTypeWith table fuel (← value.getObjVal? "member")
        let (tail, dt) ← decodeTypeWith table fuel (← value.getObjVal? "tail")
        return (.field (← value.getObjValAs? String "name") member tail, max dm dt + 1)
    | "arrow" =>
        let (domain, dd) ← decodeTypeWith table fuel (← value.getObjVal? "domain")
        let (codomain, dc) ← decodeTypeWith table fuel (← value.getObjVal? "codomain")
        return (.arrow (← decodeReuse (← value.getObjVal? "reuse"))
          (← decodeQuantity (← value.getObjVal? "parameter")) domain codomain, max dd dc + 1)
    | "specification" =>
        let (metadata, dm) ← decodeTypeWith table fuel (← value.getObjVal? "metadata")
        let (extension, de) ← decodeTypeWith table fuel (← value.getObjVal? "extension")
        return (.specification metadata extension, max dm de + 1)
    | "prototype" =>
        let (spec, ds) ← decodeTypeWith table fuel (← value.getObjVal? "spec")
        let (target, dt) ← decodeTypeWith table fuel (← value.getObjVal? "target")
        return (.prototype spec target, max ds dt + 1)
    | "variant" =>
        let (row, dr) ← decodeTypeWith table fuel (← value.getObjVal? "row")
        return (.variant row, dr + 1)
    | "computation" =>
        let (plan, dp) ← decodeTypeWith table fuel (← value.getObjVal? "plan")
        let (response, dr) ← decodeTypeWith table fuel (← value.getObjVal? "response")
        let (result, da) ← decodeTypeWith table fuel (← value.getObjVal? "result")
        return (.computation plan response result, max dp (max dr da) + 1)
    | _ => .error "unknown Objective type constructor"

/-- The type nesting capacity of every type a proposal names, tabled or inline. -/
def typeNestingCapacity : Nat := 256

def decodeType (table : Array (Ty × Nat)) (value : Json) : Except String Ty := do
  return (← decodeTypeWith table typeNestingCapacity value).1

/-- The packet's type table: entry k is decoded against entries 0..k-1 only, so a ref can
never point forward or at itself and every entry is a finite tree. -/
def decodeTypeTable (value : Json) : Except String (Array (Ty × Nat)) := do
  let entries ← value.getArr?
  if entries.size > 1048576 then throw "type table capacity"
  entries.foldlM (fun table entry => do
    pure (table.push (← decodeTypeWith table typeNestingCapacity entry))) #[]

def decodePrimitive (value : Json) : Except String Primitive := do
  match ← value.getStr? with
  | "add" => pure .add | "multiply" => pure .multiply
  | "equal" => pure .equal | "conjunction" => pure .conjunction
  | "labelEqual" => pure .labelEqual
  | "subtract" => pure .subtract | "divide" => pure .divide
  | "less" => pure .less | "lessEqual" => pure .lessEqual | "modulo" => pure .modulo
  | _ => .error "unknown Objective primitive"

/-- Decodes exactly the existing world lowerer's runtime core wire; no second
source translator or alternate fixture term is introduced by the type checker. -/
def decodeTerm : Nat → Json → Except String Term
  | 0, _ => .error "term nesting capacity"
  | fuel + 1, value => do
    let sub := fun key => do decodeTerm fuel (← value.getObjVal? key)
    let fields := fun (_ : Unit) => do
      let array ← (← value.getObjVal? "fields").getArr?
      array.toList.mapM fun field => do
        return (← field.getObjValAs? String "name", ← decodeTerm fuel (← field.getObjVal? "value"))
    match ← value.getObjValAs? String "tag" with
    | "bound" => return .bound (← jsonNat (← value.getObjVal? "index"))
    | "nat" => return .nat (← jsonNat (← value.getObjVal? "value"))
    | "boolean" => return .boolean (← value.getObjValAs? Bool "value")
    | "label" => return .label (← value.getObjValAs? String "value")
    | "lam" => return .lam (← sub "body")
    | "app" => return .app (← sub "fn") (← sub "arg")
    | "mix" => return .mix (← sub "lower") (← sub "upper")
    | "fix" => return .fix (← sub "spec") (← sub "seed")
    | "specification" => return .specification (← sub "metadata") (← sub "extension")
    | "prototype" => return .prototype (← sub "spec") (← sub "target")
    | "reflect" => return .reflect (← sub "value")
    | "metadata" => return .metadata (← sub "value")
    | "project" => return .project (← sub "value")
    | "binary" => return .binary (← decodePrimitive (← value.getObjVal? "primitive")) (← sub "left") (← sub "right")
    | "record" => return .record (← fields ())
    | "extend" => return .extend (← sub "inherited") (← fields ())
    | "get" => return .get (← sub "target") (← value.getObjValAs? String "name")
    | "ifZero" => return .ifZero (← sub "value") (← sub "zero") (← sub "successor")
    | "inject" => return .inject (← value.getObjValAs? String "label") (← sub "payload")
    | "case" => do
        let array ← (← value.getObjVal? "arms").getArr?
        let arms ← array.toList.mapM fun arm => do
          return (← arm.getObjValAs? String "label", ← decodeTerm fuel (← arm.getObjVal? "body"))
        return .case (← sub "scrutinee") arms
    | "ifBool" => return .ifBool (← sub "condition") (← sub "whenTrue") (← sub "whenFalse")
    | "perform" => return .perform (← sub "plan")
    | "done" => return .done (← sub "value")
    | _ => .error "unknown Objective runtime constructor"

def decodeLambda (table : Array (Ty × Nat)) (value : Json) : Except String LambdaAnnotation := do
  return ⟨← decodeType table (← value.getObjVal? "domain"),
    ← decodeType table (← value.getObjVal? "codomain"),
    ← decodeQuantity (← value.getObjVal? "parameter"),
    ← decodeReuse (← value.getObjVal? "reuse")⟩

structure DecodedPacket where
  source : AnnotatedTerm
  context : Context
  fuel : Nat

/-- Everything a packet carries besides its term. -/
structure PacketParts where
  annotations : List Nat → Option LambdaAnnotation
  assumptions : Assumptions
  context : Context
  fuel : Nat

/-- The term nesting capacity of a packet's term (`decodeTerm`'s fuel). -/
def termNestingCapacity : Nat := 4096

def decodePacketParts (value : Json) (table : Array (Ty × Nat)) : Except String PacketParts := do
  let annotations ← (← (← value.getObjVal? "annotations").getArr?).toList.mapM fun entry => do
    let path ← (← (← entry.getObjVal? "path").getArr?).toList.mapM jsonNat
    return (path, ← decodeLambda table entry)
  if !decide (annotations.map Prod.fst).Nodup then throw "duplicate lambda annotation path"
  let bounds ← (← (← value.getObjVal? "bounds").getArr?).toList.mapM fun entry => do
    return (← jsonNat (← entry.getObjVal? "index"), ← decodeType table (← entry.getObjVal? "type"))
  if !decide (bounds.map Prod.fst).Nodup then throw "duplicate future type bound"
  let shareable ← (← (← value.getObjVal? "shareableVariables").getArr?).toList.mapM jsonNat
  if !decide shareable.Nodup then throw "duplicate shareability premise"
  let context ← match value.getObjVal? "context" with
    | .error _ => pure []
    | .ok context => (← context.getArr?).toList.mapM fun entry => do
        return (⟨← decodeType table (← entry.getObjVal? "type"),
          ← decodeQuantity (← entry.getObjVal? "quantity")⟩ : Binding)
  let fuel ← match value.getObjVal? "fuel" with
    | .error _ => pure 4096
    | .ok fuel => jsonNat fuel
  if fuel > 16384 then throw "checker fuel capacity"
  return ⟨fun path => (annotations.find? (fun entry => entry.1 == path)).map Prod.snd,
      ⟨bounds,shareable,[]⟩,context,fuel⟩

/-- Schema, type table, term, then the rest (`decodePacketParts`), in that order. -/
def decodePacket (value : Json) : Except String DecodedPacket := do
  if (← value.getObjValAs? String "schema") != "dregg.objective-bend.typed-core.v3" then
    throw "Objective typed core edition required"
  let table ← decodeTypeTable (← value.getObjVal? "types")
  let term ← decodeTerm termNestingCapacity (← value.getObjVal? "term")
  let parts ← decodePacketParts value table
  return ⟨⟨term, parts.annotations, parts.assumptions⟩, parts.context, parts.fuel⟩

def quantityJson : Quantity → Json
  | .erased => toJson "erased" | .affine => toJson "affine"
  | .linear => toJson "linear" | .unrestricted => toJson "unrestricted"
def reuseJson : Reuse → Json
  | .once => toJson "once" | .reusable => toJson "reusable"

def typeJson : Ty → Json
  | .natural => Json.mkObj [("tag",toJson "natural")]
  | .label => Json.mkObj [("tag",toJson "label")]
  | .boolean => Json.mkObj [("tag",toJson "boolean")]
  | .emptyRow => Json.mkObj [("tag",toJson "emptyRow")]
  | .variable index => Json.mkObj [("tag",toJson "variable"),("index",toJson (toString index))]
  | .custody identity => Json.mkObj [("tag",toJson "custody"),("identity",toJson (toString identity))]
  | .field name member tail => Json.mkObj [("tag",toJson "field"),("name",toJson name),
      ("member",typeJson member),("tail",typeJson tail)]
  | .arrow reuse quantity domain codomain => Json.mkObj [("tag",toJson "arrow"),
      ("reuse",reuseJson reuse),("parameter",quantityJson quantity),
      ("domain",typeJson domain),("codomain",typeJson codomain)]
  | .specification metadata extension => Json.mkObj [("tag",toJson "specification"),
      ("metadata",typeJson metadata),("extension",typeJson extension)]
  | .prototype spec target => Json.mkObj [("tag",toJson "prototype"),
      ("spec",typeJson spec),("target",typeJson target)]
  | .variant row => Json.mkObj [("tag",toJson "variant"),("row",typeJson row)]
  | .computation plan response result => Json.mkObj [("tag",toJson "computation"),
      ("plan",typeJson plan),("response",typeJson response),("result",typeJson result)]

/-- Every quantity in a type made `unrestricted` (arrow parameters at any depth). -/
def unrestrictedTy : Ty → Ty
  | .arrow reuse _ domain codomain => .arrow reuse .unrestricted (unrestrictedTy domain) (unrestrictedTy codomain)
  | .field name member tail => .field name (unrestrictedTy member) (unrestrictedTy tail)
  | .specification metadata extension => .specification (unrestrictedTy metadata) (unrestrictedTy extension)
  | .prototype spec target => .prototype (unrestrictedTy spec) (unrestrictedTy target)
  | .variant row => .variant (unrestrictedTy row)
  | .computation plan response result =>
      .computation (unrestrictedTy plan) (unrestrictedTy response) (unrestrictedTy result)
  | other => other

/-- The kind of rule a refused packet broke. -/
inductive RefusalKind where
  | budget | ownership | typing
  deriving Repr, DecidableEq

/-- Type fuel that bounds only the checker's depth, generous enough that a
program refused with it was not refused for depth. -/
def ampleFuel (fuel : Nat) : Nat := max (fuel * 4) 65536

/-- The same packet with every quantity relaxed to `unrestricted`: lambda
parameters, every arrow in the declared types and bounds, and the context. -/
def relaxQuantities (packet : DecodedPacket) : DecodedPacket :=
  let relaxAnnotation := fun (annotation : LambdaAnnotation) =>
    ({ domain := unrestrictedTy annotation.domain, codomain := unrestrictedTy annotation.codomain,
       parameter := .unrestricted, reuse := annotation.reuse } : LambdaAnnotation)
  { source :=
      { term := packet.source.term,
        annotations := fun position => (packet.source.annotations position).map relaxAnnotation,
        assumptions := { packet.source.assumptions with
          bounds := packet.source.assumptions.bounds.map fun entry => (entry.1, unrestrictedTy entry.2) } },
    context := packet.context.map fun binding =>
      ({ type := unrestrictedTy binding.type, quantity := .unrestricted } : Binding),
    fuel := packet.fuel }

/-- The checker answers accepted or refused; it does not name the rule. To say
which KIND of rule refused, this re-runs the SAME checker on two variations of
the same packet, in order: (1) ample fuel — if that accepts, the refusal was
the checker budget; (2) every quantity relaxed to `unrestricted` — if that
accepts, the refusal was ownership (an affine or linear binding used more than
once, or captured by a closure that may run again). Otherwise it was a typing
or activity rule. No second checker is written: the classification is what the
real checker says about the variations. Meaningful only for a packet `check`
refused. -/
def refusalKind (packet : DecodedPacket) : RefusalKind :=
  if (check packet.source packet.context (ampleFuel packet.fuel)).isSome then .budget
  else
    let relaxed := relaxQuantities packet
    if (check relaxed.source relaxed.context relaxed.fuel).isSome then .ownership else .typing

def refusalReason (packet : DecodedPacket) : String :=
  match refusalKind packet with
  | .budget => s!"checker budget refused: typeFuel {packet.fuel} is too small for this program (it checks with {ampleFuel packet.fuel}); raise limits.typeFuel"
  | .ownership => "ownership refused: an affine or linear parameter is used more than once (both mean at most once), or one is captured by a closure that may run again (the program checks with every quantity unrestricted)"
  | .typing => "typing refused: types disagree, a custody value is shared or captured, or an activity rule (an Activity is refused as an argument, record/extend field, specification or prototype component, or sum payload; a Plan must be a sum of first-order data; a response must be first-order data)"

/-- The classification on this module's own refused fixtures, each also refused
by `check` above: an affine binding used twice is ownership, an accepted
program given too little fuel is the budget, a conjunction of labels is typing,
and capturing custody in a reusable closure is typing (relaxing quantities
cannot make custody shareable). -/
theorem refusal_kind_duplicate_affine :
    refusalKind ⟨duplicateAffine, [⟨.natural,.affine⟩], 8⟩ = .ownership := by decide +kernel
theorem refusal_kind_starved_fuel :
    (check (custodyCapture .once) [⟨.custody 17,.linear⟩] 1).isNone = true ∧
      refusalKind ⟨custodyCapture .once, [⟨.custody 17,.linear⟩], 1⟩ = .budget := by decide +kernel
theorem refusal_kind_label_conjunction :
    refusalKind ⟨stringConjunction, [], 8⟩ = .typing := by decide +kernel
theorem refusal_kind_custody_in_reusable_closure :
    refusalKind ⟨custodyCapture .reusable, [⟨.custody 17,.linear⟩], 8⟩ = .typing := by decide +kernel
/--
info: 'Minidregg.Theory.ObjectiveBendTyping.refusal_kind_duplicate_affine' depends on axioms: [propext,
 Classical.choice,
 Quot.sound]
-/
#guard_msgs in
#print axioms refusal_kind_duplicate_affine
/--
info: 'Minidregg.Theory.ObjectiveBendTyping.refusal_kind_starved_fuel' depends on axioms: [propext,
 Classical.choice,
 Quot.sound]
-/
#guard_msgs in
#print axioms refusal_kind_starved_fuel
/--
info: 'Minidregg.Theory.ObjectiveBendTyping.refusal_kind_label_conjunction' depends on axioms: [propext,
 Classical.choice,
 Quot.sound]
-/
#guard_msgs in
#print axioms refusal_kind_label_conjunction
/--
info: 'Minidregg.Theory.ObjectiveBendTyping.refusal_kind_custody_in_reusable_closure' depends on axioms: [propext,
 Classical.choice,
 Quot.sound]
-/
#guard_msgs in
#print axioms refusal_kind_custody_in_reusable_closure

def packetReceipt (value : Json) : Except String Json := do
  let packet ← decodePacket value
  let result ← requireSome (refusalReason packet) (check packet.source packet.context packet.fuel)
  return Json.mkObj [
    ("schema", toJson "dregg.objective-bend.typing-receipt.v1"),
    ("status", toJson "accepted"),
    ("type", typeJson result.type), ("uses", toJson result.uses),
    ("typingScope", toJson "compiled proof-producing annotated partial checker; preservation and demand adequacy separate"),
    ("laws", toJson "undischarged unless independent total law providers are supplied"),
    ("authority", toJson "no current native authority granted")]

/-- Native entry point for the exact core packet produced by the world lowerer.
Its executable result relies on Lean compilation; it is not a kernel certificate
for the parsed bytes or an executor/authority qualification. -/
def checkPacketFile (path : String) : IO UInt32 := do
  let input ← IO.FS.readFile path
  let result := do
    let parsed ← Json.parse input
    packetReceipt parsed
  match result with
  | .ok receipt => IO.println receipt.compress; return 0
  | .error message =>
      IO.eprintln (Json.mkObj [("schema",toJson "dregg.objective-bend.typing-receipt.v1"),
        ("status",toJson "refused"),("stage",toJson "objective-source-type-check"),("message",toJson message)]).compress
      return 2



/-! ## Activities: effects as a type, never in a shared position -/

def planRow : Ty := .field "write" (.field "after" .natural .emptyRow) .emptyRow
def planType : Ty := .variant planRow
def responseType : Ty := .variant (.field "written" .emptyRow (.field "refused" .emptyRow .emptyRow))
def writeAction : LambdaAnnotation := ⟨.field "after" .natural .emptyRow,planType,.unrestricted,.reusable⟩
def effectSignature : LambdaAnnotation := ⟨planType,responseType,.unrestricted,.reusable⟩
def writePlan : Term := .inject "write" (.record [("after",.nat 1)])
/-- Annotations for a perform at `site` (its plan injection one level down). -/
def performAt (site : List Nat) (rest : Annotations) : Annotations := fun position =>
  if position = site then some effectSignature else if position = site ++ [0] then some writeAction
  else rest position
def writeActivity (written refused : Term) : Term :=
  .case (.perform writePlan) [("written",written),("refused",refused)]
def armsDone : Annotations := fun position =>
  if position = [1,0] ∨ position = [1,1] then some effectSignature else none

/-- Perform a write, resume with its outcome, select the arm: an activity. -/
theorem effect_case_accepted :
    (check ⟨writeActivity (.done (.nat 1)) (.done (.nat 0)),performAt [0] armsDone,{}⟩ [] 32).map
      (fun checked => checked.type) = some (.computation planType responseType .natural) := by decide
/-- Every arm of an effect case is an activity; a pure arm needs `done`. -/
theorem pure_arm_without_done_refused :
    (check ⟨writeActivity (.nat 1) (.nat 0),performAt [0] armsDone,{}⟩ [] 32).isNone = true := by decide
/-- Rule effect-as-argument: an argument is a shared thunk, so an activity is
refused there even for an affine (non-shareable) parameter... -/
theorem effect_as_argument_refused :
    (check ⟨.app (.lam (.nat 0)) (.perform writePlan),
      performAt [1] (fun position => if position = [0] then
        some ⟨.computation planType responseType responseType,.natural,.affine,.reusable⟩ else none),{}⟩ [] 32).isNone = true := by decide
/-- ...while the same affine parameter accepts a pure argument. -/
theorem pure_affine_argument_accepted :
    (check ⟨.app (.lam (.nat 0)) (.nat 3),
      fun position => if position = [0] then some ⟨.natural,.natural,.affine,.reusable⟩ else none,{}⟩ [] 32).map
      (fun checked => checked.type) = some .natural := by decide
/-- Rule effect-in-field: a record field is a shared cell. -/
theorem effect_in_record_field_refused :
    (check ⟨.record [("next",.perform writePlan)],performAt [0] (fun _ => none),{}⟩ [] 32).isNone = true := by decide
/-- Rule effect-in-payload: a sum payload is a shared cell. -/
theorem effect_in_payload_refused :
    (check ⟨.inject "later" (.perform writePlan),
      performAt [0] (fun position => if position = [] then
        some ⟨.computation planType responseType responseType,
          .variant (.field "later" (.computation planType responseType responseType) .emptyRow),
          .unrestricted,.reusable⟩ else none),{}⟩ [] 32).isNone = true := by decide
/-- Rule effect-in-specification: specification components are shared cells. -/
theorem effect_in_specification_refused :
    (check ⟨.specification (.perform writePlan) (.nat 0),performAt [0] (fun _ => none),{}⟩ [] 32).isNone = true := by decide
/-- Rule plan-is-a-sum: a perform's plan is a sum of first-order actions. -/
theorem scalar_plan_refused :
    (check ⟨.perform (.nat 1),fun position => if position = [] then
      some ⟨.natural,responseType,.unrestricted,.reusable⟩ else none,{}⟩ [] 32).isNone = true := by decide
/-- Rule response-is-data: a closure cannot be a response. -/
theorem closure_response_refused :
    (check ⟨.perform writePlan,fun position =>
      if position = [] then some ⟨planType,.arrow .reusable .unrestricted .natural .natural,.unrestricted,.reusable⟩
      else if position = [0] then some writeAction else none,{}⟩ [] 32).isNone = true := by decide
/-- An activity is never shareable, so it is never a fix target, mix operand or
unrestricted binder either. -/
theorem computation_not_shareable (plan response result : Ty) (variables : List Nat) :
    (Ty.computation plan response result).shareableUnder variables = false := rfl

#assert_axioms exhaustive_case_accepted reordered_arms_accepted missing_arm_refused
  extra_arm_refused undeclared_injection_refused unannotated_injection_refused
  arm_results_must_agree equality_branch_accepted label_condition_refused label_equality_accepted
  boolean_label_equality_refused nat_primitive_types order_primitive_branch_accepted
  nat_primitive_label_operand_refused affine_in_two_arms_refused affine_in_one_arm_accepted
  effect_case_accepted pure_arm_without_done_refused effect_as_argument_refused
  pure_affine_argument_accepted effect_in_record_field_refused effect_in_payload_refused
  effect_in_specification_refused scalar_plan_refused closure_response_refused
#assert_axioms recursive_sum_list_accepted recursive_sum_ill_typed_tail_refused
#assert_axioms canonical_agreement_loses_shareability shadowed_custody_laundering_refused
  shadowed_once_closure_laundering_refused shadowed_shareable_member_accepted
  shadowed_override_accepted agree_never_manufactures_shareability

end Minidregg.Theory.ObjectiveBendTyping
