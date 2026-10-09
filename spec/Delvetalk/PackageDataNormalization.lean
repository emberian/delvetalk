import Delvetalk.PackageDataAdmission
import Delvetalk.PackageDataSchemaProofs
namespace Delvetalk.PackageData
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendDemandData
set_option autoImplicit false

theorem dereference_matches {a : Assumptions} {graph : SchemaGraph} {schema target : Schema}
    {declared : Ty} {fuel remaining : Nat}
    (matched : SchemaMatches a graph schema declared)
    (success : (dereference graph schema).run fuel = .ok (target,remaining)) :
    ∃ actual, SchemaMatches a graph target actual ∧ sameType a actual declared = true := by
  cases matched with
  | natural =>
      have eq := work_pure_output _ success
      subst target
      exact ⟨.natural,.natural,by simp [sameType]⟩
  | boolean =>
      have eq := work_pure_output _ success
      subst target
      exact ⟨.boolean,.boolean,by simp [sameType]⟩
  | label =>
      have eq := work_pure_output _ success
      subst target
      exact ⟨.label,.label,by simp [sameType]⟩
  | data =>
      have eq := work_pure_output _ success
      subst target
      exact ⟨.data,.data,by simp [sameType]⟩
  | record fields =>
      have eq := work_pure_output _ success
      subst target
      exact ⟨_,.record fields,by simp [sameType]⟩
  | variant found =>
      have eq := work_pure_output _ success
      subst target
      exact ⟨_,.variant found,by simp [sameType]⟩
  | reference alias found row sameRow =>
      simp only [dereference] at success
      obtain ⟨unit,middle,_,rest⟩ := work_bind_ok _ _ success
      simp only [found] at rest
      have eq := work_pure_output _ rest
      subst target
      exact ⟨_,.variant row,SchemaMatches.reference_conversion alias found row sameRow⟩

@[simp] theorem finishNative_finishNative (value : Data) : finishNative (finishNative value) = value := by
  cases value <;> simp [finishNative]

theorem work_throw_ne_ok {α : Type} (message : String) {fuel remaining : Nat} {output : α}
    (success : ((throw message : Work α).run fuel) = .ok (output,remaining)) : False := by
  change Except.error message = Except.ok (output,remaining) at success
  cases success

mutual
theorem quoteSchema_native_admitted {a : Assumptions} {graph : SchemaGraph}
    (sound : GraphSound a graph) (depth : Nat) (input : Data) (declared : Ty) (schema : Schema)
    (matched : SchemaMatches a graph schema declared) {fuel remaining : Nat} {output : Data}
    (success : (quoteSchema nativeSink graph depth input declared schema).run fuel = .ok (output,remaining)) :
    Admitted a (finishNative output) declared := by
  cases depth with
  | zero =>
      simp only [quoteSchema, failDepth] at success
      exact False.elim (work_throw_ne_ok _ success)
  | succ depth =>
    simp only [quoteSchema] at success
    obtain ⟨_,middle,_,rest⟩ := work_bind_ok _ _ success
    obtain ⟨target,last,targetOk,rest⟩ := work_bind_ok _ _ rest
    obtain ⟨actual,targetMatched,conversion⟩ := dereference_matches matched targetOk
    apply Admitted.conversion (expected := declared) (actual := actual) _ conversion
    cases targetMatched with
    | natural =>
      cases input <;> try exact False.elim (work_throw_ne_ok _ rest)
      have eq := work_pure_output _ rest
      subst output
      exact .natural _
    | boolean =>
      cases input <;> try exact False.elim (work_throw_ne_ok _ rest)
      have eq := work_pure_output _ rest
      subst output
      exact .boolean _
    | label =>
      cases input <;> try exact False.elim (work_throw_ne_ok _ rest)
      have eq := work_pure_output _ rest
      subst output
      exact .label _
    | @record types row fieldsMatched =>
      cases input <;> try exact False.elim (work_throw_ne_ok _ rest)
      dsimp only at rest
      split at rest
      · obtain ⟨_,_,impossible,_⟩ := work_bind_ok _ _ rest
        exact False.elim (work_throw_ne_ok _ impossible)
      · obtain ⟨indexed,afterIndex,_,rest⟩ := work_bind_ok _ _ rest
        obtain ⟨fields,typed,eq⟩ := quoteRecordFields_native_admitted sound depth indexed _ [] fieldsMatched rest
        rw [eq]
        simpa [finishNative] using Admitted.record typed
    | @variant index types found =>
      cases input with
      | variant tag payload =>
        dsimp only at rest
        obtain ⟨_,afterSpend,_,rest⟩ := work_bind_ok _ _ rest
        simp only [found] at rest
        cases lookup : types.members[tag]? with
        | none => simp only [lookup] at rest; exact False.elim (work_throw_ne_ok _ rest)
        | some memberSchema =>
          rcases memberSchema with ⟨member,childSchema⟩
          simp only [lookup] at rest
          obtain ⟨child,afterChild,childOk,rest⟩ := work_bind_ok _ _ rest
          obtain ⟨rowFuel,rowLookup,pure,childMatched⟩ := sound.members index types tag member childSchema found lookup
          have childTyped := quoteSchema_native_admitted sound depth payload member childSchema childMatched childOk
          have eq := work_pure_output _ rest
          subst output
          exact .variant childTyped rowLookup pure
      | natural n => exact False.elim (work_throw_ne_ok _ rest)
      | boolean b => exact False.elim (work_throw_ne_ok _ rest)
      | label label => exact False.elim (work_throw_ne_ok _ rest)
      | record fields => exact False.elim (work_throw_ne_ok _ rest)
    | data =>
      dsimp only at rest
      obtain ⟨_,afterSpend,_,rest⟩ := work_bind_ok _ _ rest
      by_cases wf : input.wellFormed = true
      · simp only [wf, if_true] at rest
        have eq := work_pure_output _ rest
        subst output
        simpa [nativeSink, finishNative_finishNative] using (Admitted.universal (a := a) wf)
      · simp only [wf, Bool.false_eq_true, if_false] at rest
        exact False.elim (work_throw_ne_ok _ rest)
    | reference alias target row sameRow =>
      cases input <;> exact False.elim (work_throw_ne_ok _ rest)
termination_by (depth, 0, 0)

theorem quoteRecordFields_native_admitted {a : Assumptions} {graph : SchemaGraph}
    (sound : GraphSound a graph) (depth : Nat) (indexed : Std.HashMap String Data)
    (types : List (String × Ty × Schema)) (initial : List (String × Data))
    {row : Ty} (matched : SchemaFieldsMatch a graph types row) {fuel remaining : Nat} {output : Data}
    (success : (quoteRecordFields nativeSink graph depth indexed types (.record initial)).run fuel = .ok (output,remaining)) :
    ∃ fields, AdmittedFields a fields row ∧ output = .record (fields.reverse ++ initial) := by
  cases matched with
  | nil =>
    simp only [quoteRecordFields] at success
    have eq := work_pure_output _ success
    exact ⟨[],.nil,eq⟩
  | @cons name member row schema rest childMatched restMatched pure =>
    simp only [quoteRecordFields] at success
    obtain ⟨_,middle,_,success⟩ := work_bind_ok _ _ success
    cases found : indexed[name]? with
    | none => simp only [found] at success; exact False.elim (work_throw_ne_ok _ success)
    | some input =>
      simp only [found] at success
      obtain ⟨child,last,childOk,success⟩ := work_bind_ok _ _ success
      have typed := quoteSchema_native_admitted sound depth input member schema childMatched childOk
      obtain ⟨tail,tailTyped,eq⟩ := quoteRecordFields_native_admitted sound depth indexed rest
        ((name,finishNative child)::initial) restMatched success
      refine ⟨(name,finishNative child)::tail,.cons typed tailTyped pure,?_⟩
      simpa only [List.reverse_cons, List.append_assoc, List.singleton_append] using eq
termination_by (depth, 1, types.length)
end

/-- The actual receiving normalizer cannot return data without a Mini literal
admission derivation. The graph premise is supplied by the executed builder. -/
theorem normalizeNative_admitted {a : Assumptions} {depth : Nat} {input output : Data}
    {declared : Ty} {fuel remaining : Nat}
    (success : (normalizeNative a depth input declared).run fuel = .ok (output,remaining)) :
    Admitted a output declared := by
  simp only [normalizeNative] at success
  obtain ⟨raw,afterQuote,quoted,finished⟩ := work_bind_ok _ _ success
  simp only [quoteWith] at quoted
  obtain ⟨graph,afterGraph,built,normalized⟩ := work_bind_ok _ _ quoted
  obtain ⟨sound,matched⟩ := schemaGraph_sound built
  have typed := quoteSchema_native_admitted sound depth input declared graph.root matched normalized
  have eq := work_pure_output _ finished
  rw [eq]
  exact typed

theorem normalizeNative_typing {a : Assumptions} {depth : Nat} {input output : Data}
    {declared : Ty} {fuel remaining : Nat}
    (success : (normalizeNative a depth input declared).run fuel = .ok (output,remaining)) :
    ∃ term, Literal term output ∧
      Minidregg.Theory.ObjectiveBendTyping.PartialTyping a [] term declared [] :=
  (normalizeNative_admitted success).typing

theorem prepareNativeArguments_admitted {α : Type}
    (read : Assumptions → Ty → α → Work Data) (a : Assumptions)
    (type : Ty) (arguments : List α) {resultType : Ty} {values : List Data}
    {fuel remaining : Nat}
    (success : (prepareNativeArguments read a type arguments).run fuel = .ok ((resultType,values),remaining)) :
    AdmittedArguments a type values resultType := by
  induction arguments generalizing type fuel remaining resultType values with
  | nil =>
    simp only [prepareNativeArguments] at success
    have eq := work_pure_output _ success
    cases eq
    exact .nil type
  | cons argument rest ih =>
    simp only [prepareNativeArguments] at success
    cases arrow : callable type <;> simp only [arrow] at success <;>
      try exact False.elim (work_throw_ne_ok _ success)
    rename_i reuse quantity domain codomain
    by_cases allowed : argumentAllowed a quantity [] domain [] = true
    · simp only [allowed, Bool.true_eq, if_false, if_true] at success
      obtain ⟨value,afterRead,_,success⟩ := work_bind_ok _ _ success
      obtain ⟨normalized,afterNormalize,normalizedOk,success⟩ := work_bind_ok _ _ success
      obtain ⟨tail,afterTail,tailOk,success⟩ := work_bind_ok _ _ success
      rcases tail with ⟨tailType,tailValues⟩
      have eq := work_pure_output _ success
      cases eq
      exact .cons arrow (normalizeNative_admitted normalizedOk) allowed (ih _ tailOk)
    · simp only [allowed, if_true, if_false] at success
      obtain ⟨_,_,impossible,_⟩ := work_bind_ok _ _ success
      exact False.elim (work_throw_ne_ok _ impossible)

/-- A successful actual package preparation retains a checked closed source and
an admission derivation for every selected argument/domain in application order. -/
theorem prepareNativeWith_admitted {α : Type}
    (read : Assumptions → Ty → α → Work Data) (packet : Lean.Json)
    (arguments : Work (Array α)) {prepared : NativePreparation} {fuel remaining : Nat}
    (success : (prepareNativeWith read packet arguments).run fuel = .ok (prepared,remaining)) :
    ∃ initial : Checked prepared.source [],
      AdmittedArguments prepared.source.assumptions initial.type prepared.arguments.toList prepared.resultType := by
  simp only [prepareNativeWith] at success
  obtain ⟨decoded,afterDecode,_,rest⟩ := work_bind_ok _ _ success
  split at rest
  · cases checked : check decoded.source [] decoded.fuel with
    | none => simp only [checked] at rest; exact False.elim (work_throw_ne_ok _ rest)
    | some initial =>
      simp only [checked] at rest
      obtain ⟨inputs,afterInputs,_,rest⟩ := work_bind_ok _ _ rest
      obtain ⟨pair,afterPrepared,preparedOk,rest⟩ := work_bind_ok _ _ rest
      rcases pair with ⟨resultType,values⟩
      obtain ⟨_,afterShape,_,rest⟩ := work_bind_ok _ _ rest
      have admitted := prepareNativeArguments_admitted read decoded.source.assumptions initial.type inputs.toList preparedOk
      have eq := work_pure_output _ rest
      rw [eq]
      refine ⟨initial,?_⟩
      simpa using admitted
  · obtain ⟨_,_,impossible,_⟩ := work_bind_ok _ _ rest
    exact False.elim (work_throw_ne_ok _ impossible)

/-- The receiving preparation is connected to the complete core application
judgment, without reconstructing or rechecking its erased literal syntax. Each
argument is a literal of its native value, with `toData` exactly at the
universal positions (administrative: the machine erases it). -/
theorem prepareNativeWith_typing {α : Type}
    (read : Assumptions → Ty → α → Work Data) (packet : Lean.Json)
    (arguments : Work (Array α)) {prepared : NativePreparation} {fuel remaining : Nat}
    (success : (prepareNativeWith read packet arguments).run fuel = .ok (prepared,remaining)) :
    ∃ terms, Literals terms prepared.arguments.toList ∧
      PartialTyping prepared.source.assumptions []
        (literalApplications prepared.source.term terms) prepared.resultType [] := by
  obtain ⟨initial,admitted⟩ := prepareNativeWith_admitted read packet arguments success
  have typed := initial.derivation
  rw [checked_closed_uses initial] at typed
  exact admitted.typing typed

/-- A selected package entry's native preparation is typed in the same sense: the
checked entry applied to literals of its admitted arguments. -/
theorem prepareNativeChecked_typing {source : AnnotatedTerm} {initial : Checked source []} {fuel : Nat}
    {arguments : Array Data} {prepared : NativePreparation} {work remaining : Nat}
    (success : (prepareNativeChecked source initial fuel arguments).run work = .ok (prepared, remaining)) :
    prepared.source = source ∧ ∃ terms, Literals terms prepared.arguments.toList ∧
      PartialTyping prepared.source.assumptions []
        (literalApplications prepared.source.term terms) prepared.resultType [] := by
  simp only [prepareNativeChecked] at success
  obtain ⟨pair, afterPrepared, preparedOk, rest⟩ := work_bind_ok _ _ success
  rcases pair with ⟨resultType, values⟩
  obtain ⟨_, afterShape, _, rest⟩ := work_bind_ok _ _ rest
  have admitted := prepareNativeArguments_admitted (fun _ _ value => pure value) source.assumptions initial.type
    arguments.toList preparedOk
  have eq := work_pure_output _ rest
  subst eq
  refine ⟨rfl, ?_⟩
  have typed := initial.derivation
  rw [checked_closed_uses initial] at typed
  simpa [AnnotatedTerm.erase] using admitted.typing typed

#print axioms prepareNativeWith_typing
#print axioms normalizeNative_typing
#print axioms prepareNativeChecked_typing
end Delvetalk.PackageData
