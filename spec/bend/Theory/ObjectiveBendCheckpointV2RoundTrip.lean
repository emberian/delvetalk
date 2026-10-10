/- The v2 checkpoint round trip: decoding a v2 checkpoint against the program it was
encoded against restores exactly the state, for every dictionary and every state
(`stateV2_roundTrip`). The references are emitted only when checked, so nothing here
depends on how the dictionary's hints were built. -/
import Theory.ObjectiveBendCheckpointV2
import Theory.ObjectiveBendCheckpointRoundTrip
import Theory.AxiomPin
namespace Minidregg.Theory.ObjectiveBendCheckpointRoundTrip
open ObjectiveBendOpenRecursion ObjectiveBendDemandMachine ObjectiveBendCheckpoint
open Minidregg.Theory.ObjectiveBendDemandData (Data)
set_option autoImplicit false

theorem encodeTerm_injective {a b : Term} (h : encodeTerm a = encodeTerm b) : a = b := by
  have ha := term_roundTrip a (encodeTerm a).length [] (Nat.le_refl _)
  have hb := term_roundTrip b (encodeTerm b).length [] (Nat.le_refl _)
  rw [h] at ha
  rw [ha] at hb
  simpa using hb

theorem termEq_eq {a b : Term} (h : termEq a b = true) : a = b := by
  simp only [termEq, withPtrEq, decide_eq_true_eq] at h
  exact encodeTerm_injective h

theorem termRef_roundTrip (terms : Array Term) (find : Term → Option Nat) (t : Term) (fuel : Nat) (rest : Tokens)
    (enough : (encodeTermRef terms find t).length ≤ fuel) :
    decodeTermRef terms fuel (encodeTermRef terms find t ++ rest) = some (t, rest) := by
  have inline : (encodeTerm t).length ≤ fuel →
      decodeTermRef terms fuel ((.nat 0 :: encodeTerm t) ++ rest) = some (t, rest) := by
    intro h; simp [decodeTermRef, term_roundTrip t fuel rest h]
  unfold encodeTermRef at enough ⊢
  cases hf : find t with
  | none =>
    simp only [hf, List.length_cons] at enough ⊢
    exact inline (by omega)
  | some i =>
    simp only [hf] at enough ⊢
    cases hu : terms[i]? with
    | none =>
      simp only [hu, Bool.false_eq_true, if_false, List.length_cons] at enough ⊢
      exact inline (by omega)
    | some u =>
      cases he : termEq u t with
      | true =>
        have same := termEq_eq he
        subst same
        simp [hu, he, decodeTermRef]
      | false =>
        simp only [hu, he, Bool.false_eq_true, if_false, List.length_cons] at enough ⊢
        exact inline (by omega)

theorem unzigzag_zigzag (a b : Nat) : unzigzag a (zigzag a b) = b := by
  unfold zigzag unzigzag
  split <;> rename_i h
  · have : 2 * (a - b) % 2 = 0 := by omega
    simp only [this, beq_self_eq_true, ite_true]; omega
  · have : (2 * (b - a) - 1) % 2 = 1 := by omega
    have hne : ((2 * (b - a) - 1) % 2 == 0) = false := by rw [this]; rfl
    simp only [hne, Bool.false_eq_true, ite_false]; omega

theorem steps_roundTrip : ∀ (previous : Nat) (addresses : List Address) (rest : Tokens),
    decodeSteps previous addresses.length (encodeSteps previous addresses ++ rest) = some (addresses, rest)
  | _, [], rest => by simp [encodeSteps, decodeSteps]
  | previous, a :: others, rest => by
    simp [encodeSteps, decodeSteps, unzigzag_zigzag, steps_roundTrip a others rest]

theorem addressesV2_roundTrip (addresses : List Address) (rest : Tokens) :
    decodeAddressesV2 (encodeAddressesV2 addresses ++ rest) = some (addresses, rest) := by
  simp [encodeAddressesV2, decodeAddressesV2, steps_roundTrip]

theorem envRef_roundTrip (envs : Array Environment) (find : Environment → Option Nat) (e : Environment)
    (rest : Tokens) : decodeEnvRef envs (encodeEnvRef envs find e ++ rest) = some (e, rest) := by
  unfold encodeEnvRef
  split
  · split
    · rename_i i _ checked
      simp only [beq_iff_eq] at checked
      simp [decodeEnvRef, checked]
    · simp [decodeEnvRef, addressesV2_roundTrip]
  · simp [decodeEnvRef, addressesV2_roundTrip]

theorem texts_roundTrip : ∀ (names : List String) (rest : Tokens),
    decodeTexts names.length (names.map Token.text ++ rest) = some (names, rest)
  | [], rest => by simp [decodeTexts]
  | x :: others, rest => by simp [decodeTexts, texts_roundTrip others rest]

theorem namesRef_roundTrip (lists : Array (List String)) (find : List String → Option Nat) (names : List String)
    (rest : Tokens) : decodeNamesRef lists (encodeNamesRef lists find names ++ rest) = some (names, rest) := by
  unfold encodeNamesRef
  split
  · split
    · rename_i i _ checked
      simp only [beq_iff_eq] at checked
      simp [decodeNamesRef, checked]
    · simp [decodeNamesRef, texts_roundTrip]
  · simp [decodeNamesRef, texts_roundTrip]

theorem zip_map_fst_snd {α β : Type} : ∀ (l : List (α × β)), (l.map (·.1)).zip (l.map (·.2)) = l
  | [] => rfl
  | (a, b) :: rest => by simp [zip_map_fst_snd rest]

section
variable (r : Refs)

theorem fieldsV2_roundTrip : ∀ (fields : List (String × Term)) (fuel count : Nat) (rest : Tokens),
    (encodeFieldsV2 r fields).length ≤ fuel → fields.length < count →
      decodeFieldsV2 r.terms fuel count (encodeFieldsV2 r fields ++ rest) = some (fields, rest)
  | [], fuel, count + 1, rest, _, _ => by simp [encodeFieldsV2, decodeFieldsV2]
  | (name, body) :: others, fuel, count + 1, rest, h, hc => by
    simp only [encodeFieldsV2, List.length_cons, List.length_append] at h
    simp only [List.length_cons] at hc
    simp [encodeFieldsV2, decodeFieldsV2, List.append_assoc,
      termRef_roundTrip r.terms r.findTerm body fuel _ (by omega),
      fieldsV2_roundTrip others fuel count rest (by omega) (by omega)]

theorem closureV2_roundTrip (c : Closure) (fuel : Nat) (rest : Tokens)
    (enough : (encodeClosureV2 r c).length ≤ fuel) :
    decodeClosureV2 r.terms r.envs fuel (encodeClosureV2 r c ++ rest) = some (c, rest) := by
  simp only [encodeClosureV2, List.length_append] at enough
  simp [encodeClosureV2, decodeClosureV2, List.append_assoc,
    termRef_roundTrip r.terms r.findTerm c.term fuel _ (by omega), envRef_roundTrip]

theorem valueV2_roundTrip (value : RuntimeValue) (fuel : Nat) (rest : Tokens)
    (enough : (encodeValueV2 r value).length ≤ fuel) :
    decodeValueV2 r.terms r.envs r.nameLists fuel (encodeValueV2 r value ++ rest) = some (value, rest) := by
  cases value with
  | closure body environment =>
    simp only [encodeValueV2, List.length_cons] at enough
    simp [encodeValueV2, decodeValueV2, closureV2_roundTrip r ⟨body, environment⟩ fuel rest (by omega)]
  | record fields =>
    simp [encodeValueV2, decodeValueV2, List.append_assoc, namesRef_roundTrip, addressesV2_roundTrip,
      zip_map_fst_snd]
  | natural n => simp [encodeValueV2, decodeValueV2, encodeValue, decodeValue]
  | boolean b => cases b <;> simp [encodeValueV2, decodeValueV2, encodeValue, decodeValue]
  | label l => simp [encodeValueV2, decodeValueV2, encodeValue, decodeValue]
  | specification m e => simp [encodeValueV2, decodeValueV2, encodeValue, decodeValue]
  | prototype s t => simp [encodeValueV2, decodeValueV2, encodeValue, decodeValue]
  | variant l p => simp [encodeValueV2, decodeValueV2, encodeValue, decodeValue]

theorem cellV2_roundTrip (cell : Cell) (fuel : Nat) (rest : Tokens)
    (enough : (encodeCellV2 r cell).length ≤ fuel) :
    decodeCellV2 r.terms r.envs r.nameLists fuel (encodeCellV2 r cell ++ rest) = some (cell, rest) := by
  cases cell with
  | suspended origin =>
    simp only [encodeCellV2, List.length_cons] at enough
    simp [encodeCellV2, decodeCellV2, closureV2_roundTrip r origin fuel rest (by omega)]
  | evaluating origin =>
    simp only [encodeCellV2, List.length_cons] at enough
    simp [encodeCellV2, decodeCellV2, closureV2_roundTrip r origin fuel rest (by omega)]
  | cached origin value =>
    simp only [encodeCellV2, List.length_cons, List.length_append] at enough
    simp [encodeCellV2, decodeCellV2, List.append_assoc, closureV2_roundTrip r origin fuel _ (by omega),
      valueV2_roundTrip r value fuel rest (by omega)]
  | native origin =>
    simp only [encodeCellV2, List.length_cons] at enough
    simp [encodeCellV2, decodeCellV2, data_roundTrip origin fuel rest (by omega)]
  | nativeCached origin value =>
    simp only [encodeCellV2, List.length_cons, List.length_append] at enough
    simp [encodeCellV2, decodeCellV2, List.append_assoc, data_roundTrip origin fuel _ (by omega),
      valueV2_roundTrip r value fuel rest (by omega)]

theorem frameV2_roundTrip (frame : Frame) (fuel : Nat) (rest : Tokens)
    (enough : (encodeFrameV2 r frame).length ≤ fuel) :
    decodeFrameV2 r.terms r.envs r.nameLists fuel (encodeFrameV2 r frame ++ rest) = some (frame, rest) := by
  cases frame with
  | argument term environment =>
    simp only [encodeFrameV2, List.length_cons] at enough
    simp [encodeFrameV2, decodeFrameV2, closureV2_roundTrip r ⟨term, environment⟩ fuel rest (by omega)]
  | extend fields environment =>
    simp only [encodeFrameV2, List.length_cons, List.length_append] at enough
    have hc : fields.length < fuel := by
      have : fields.length < (encodeFieldsV2 r fields).length := by
        clear enough
        induction fields with
        | nil => simp [encodeFieldsV2]
        | cons f others ih => obtain ⟨n, b⟩ := f; simp [encodeFieldsV2]; omega
      omega
    simp [encodeFrameV2, decodeFrameV2, List.append_assoc,
      fieldsV2_roundTrip r fields fuel fuel _ (by omega) hc, envRef_roundTrip]
  | condition zero successorBody environment =>
    simp only [encodeFrameV2, List.length_cons, List.length_append] at enough
    simp [encodeFrameV2, decodeFrameV2, List.append_assoc,
      termRef_roundTrip r.terms r.findTerm zero fuel _ (by omega),
      closureV2_roundTrip r ⟨successorBody, environment⟩ fuel rest (by omega)]
  | binaryLeft primitive right environment =>
    simp only [encodeFrameV2, List.length_cons] at enough
    simp [encodeFrameV2, decodeFrameV2, primitive_roundTrip,
      closureV2_roundTrip r ⟨right, environment⟩ fuel rest (by omega)]
  | binaryRight primitive left =>
    simp only [encodeFrameV2, List.length_cons] at enough
    simp [encodeFrameV2, decodeFrameV2, primitive_roundTrip, valueV2_roundTrip r left fuel rest (by omega)]
  | case arms environment =>
    simp only [encodeFrameV2, List.length_cons, List.length_append] at enough
    have hc : arms.length < fuel := by
      have : arms.length < (encodeFieldsV2 r arms).length := by
        clear enough
        induction arms with
        | nil => simp [encodeFieldsV2]
        | cons f others ih => obtain ⟨n, b⟩ := f; simp [encodeFieldsV2]; omega
      omega
    simp [encodeFrameV2, decodeFrameV2, List.append_assoc,
      fieldsV2_roundTrip r arms fuel fuel _ (by omega) hc, envRef_roundTrip]
  | ifBool whenTrue whenFalse environment =>
    simp only [encodeFrameV2, List.length_cons, List.length_append] at enough
    simp [encodeFrameV2, decodeFrameV2, List.append_assoc,
      termRef_roundTrip r.terms r.findTerm whenTrue fuel _ (by omega),
      closureV2_roundTrip r ⟨whenFalse, environment⟩ fuel rest (by omega)]
  | joinSeparator list environment =>
    simp only [encodeFrameV2, List.length_cons] at enough
    simp [encodeFrameV2, decodeFrameV2, closureV2_roundTrip r ⟨list, environment⟩ fuel rest (by omega)]
  | nativeArgument value =>
    simp only [encodeFrameV2, encodeFrame, List.length_cons] at enough
    simp [encodeFrameV2, decodeFrameV2, encodeFrame, decodeFrame, data_roundTrip value fuel rest (by omega)]
  | unary primitive => simp [encodeFrameV2, decodeFrameV2, encodeFrame, decodeFrame, unary_roundTrip]
  | joinList s a first => cases first <;> simp [encodeFrameV2, decodeFrameV2, encodeFrame, decodeFrame]
  | joinCons s a first => cases first <;> simp [encodeFrameV2, decodeFrameV2, encodeFrame, decodeFrame]
  | joinHead s a first tail => cases first <;> simp [encodeFrameV2, decodeFrameV2, encodeFrame, decodeFrame]
  | update a => simp [encodeFrameV2, decodeFrameV2, encodeFrame, decodeFrame]
  | field n => simp [encodeFrameV2, decodeFrameV2, encodeFrame, decodeFrame]
  | reflect => simp [encodeFrameV2, decodeFrameV2, encodeFrame, decodeFrame]
  | metadata => simp [encodeFrameV2, decodeFrameV2, encodeFrame, decodeFrame]
  | project => simp [encodeFrameV2, decodeFrameV2, encodeFrame, decodeFrame]

theorem controlV2_roundTrip (control : Control) (fuel : Nat) (rest : Tokens)
    (enough : (encodeControlV2 r control).length ≤ fuel) :
    decodeControlV2 r.terms r.envs r.nameLists fuel (encodeControlV2 r control ++ rest) = some (control, rest) := by
  cases control with
  | evaluate term environment =>
    simp only [encodeControlV2, List.length_cons] at enough
    simp [encodeControlV2, decodeControlV2, closureV2_roundTrip r ⟨term, environment⟩ fuel rest (by omega)]
  | returned value =>
    simp only [encodeControlV2, List.length_cons] at enough
    simp [encodeControlV2, decodeControlV2, valueV2_roundTrip r value fuel rest (by omega)]
  | complete value =>
    simp only [encodeControlV2, List.length_cons] at enough
    simp [encodeControlV2, decodeControlV2, valueV2_roundTrip r value fuel rest (by omega)]
  | nativeApplication function argument remaining =>
    simp only [encodeControlV2, List.length_cons, List.length_append, List.length_singleton,
      List.length_nil] at enough
    have each : ∀ item ∈ remaining, ∀ rest,
        decodeData fuel (encodeData item ++ rest) = some (item, rest) := by
      intro item member rest
      apply data_roundTrip
      have := length_le_flatMap encodeData remaining item member
      omega
    simp [encodeControlV2, decodeControlV2, List.append_assoc,
      termRef_roundTrip r.terms r.findTerm function fuel _ (by omega),
      data_roundTrip argument fuel _ (by omega),
      many_roundTrip (decodeData fuel) encodeData remaining rest each]
  | refused reason => simp [encodeControlV2, decodeControlV2, encodeControl, decodeControl, refusal_roundTrip]
  | enter a => simp [encodeControlV2, decodeControlV2, encodeControl, decodeControl]
  | blackhole a => simp [encodeControlV2, decodeControlV2, encodeControl, decodeControl]
  | yielded a => simp [encodeControlV2, decodeControlV2, encodeControl, decodeControl]

theorem bodyV2_roundTrip (s : State) (fuel : Nat) (enough : (encodeBodyV2 r s).length ≤ fuel) :
    decodeBodyV2 r.terms r.envs r.nameLists fuel (encodeBodyV2 r s) = some s := by
  obtain ⟨heap, control, stack⟩ := s
  simp only [encodeBodyV2, List.length_append, List.length_cons, List.length_singleton] at enough
  have cells : ∀ cell ∈ heap.toList, ∀ rest,
      decodeCellV2 r.terms r.envs r.nameLists fuel (encodeCellV2 r cell ++ rest) = some (cell, rest) := by
    intro cell member rest
    apply cellV2_roundTrip
    have := length_le_flatMap (encodeCellV2 r) _ cell member
    omega
  have frames : ∀ frame ∈ stack, ∀ rest,
      decodeFrameV2 r.terms r.envs r.nameLists fuel (encodeFrameV2 r frame ++ rest) = some (frame, rest) := by
    intro frame member rest
    apply frameV2_roundTrip
    have := length_le_flatMap (encodeFrameV2 r) _ frame member
    omega
  have heapDecoded := many_roundTrip (decodeCellV2 r.terms r.envs r.nameLists fuel) (encodeCellV2 r) heap.toList
    (encodeControlV2 r control ++ (Token.nat stack.length :: stack.flatMap (encodeFrameV2 r))) cells
  have stackDecoded := many_roundTrip (decodeFrameV2 r.terms r.envs r.nameLists fuel) (encodeFrameV2 r) stack [] frames
  rw [List.append_nil] at stackDecoded
  have shape : encodeBodyV2 r ⟨heap, control, stack⟩ = Token.nat heap.toList.length ::
      (heap.toList.flatMap (encodeCellV2 r) ++ (encodeControlV2 r control ++
        (Token.nat stack.length :: stack.flatMap (encodeFrameV2 r)))) := by
    simp [encodeBodyV2]
  rw [shape]
  simp only [decodeBodyV2]
  rw [heapDecoded]
  simp [controlV2_roundTrip r control fuel _ (by omega), stackDecoded]
end

/-! ## Strings -/

theorem resolve_intern (table : Array String) (find : String → Option Nat) (t : Token) :
    resolveString table (internString table find t) = t := by
  cases t with
  | nat n => rfl
  | str j =>
    have : ¬ j + table.size < table.size := by omega
    simp [internString, resolveString, this]
  | text s =>
    simp only [internString]
    cases hf : find s with
    | none => rfl
    | some i =>
      simp only
      split
      · rename_i checked
        simp only [beq_iff_eq, Array.getElem?_eq_some_iff] at checked
        obtain ⟨hi, hs⟩ := checked
        simp [resolveString, hi, hs]
      · rfl

theorem resolve_intern_map (table : Array String) (find : String → Option Nat) (tokens : Tokens) :
    (tokens.map (internString table find)).map (resolveString table) = tokens := by
  induction tokens with
  | nil => rfl
  | cons t rest ih => simp [resolve_intern, ih]

theorem texts_mapM (f : Token → Option String) (texts : ∀ x, f (.text x) = some x) :
    ∀ (xs : List String), (xs.map Token.text).mapM f = some xs
  | [] => rfl
  | x :: rest => by simp [List.mapM_cons, texts, texts_mapM f texts rest]

/-- The string layer inverts: whatever the table and the hint. -/
theorem strings_roundTrip (edition : String) (strings locals : Array String)
    (find : String → Option Nat) (plain : Tokens) :
    decodeStrings edition strings (.text edition :: .nat locals.size ::
      (locals.toList.map .text ++ plain.map (internString (strings ++ locals) find))) = some plain := by
  have size : (locals.toList.map Token.text).length = locals.size := by simp
  simp only [decodeStrings, bne_self_eq_false, Bool.false_eq_true, if_false]
  rw [← size, List.take_left' rfl, List.drop_left' rfl, texts_mapM _ (fun _ => rfl)]
  have back : (List.map (resolveString (strings ++ locals) ∘ internString (strings ++ locals) find) plain) = plain := by
    rw [← List.map_map, resolve_intern_map]
  simp [back]

theorem plainV2_roundTrip (d : Dictionary) (s : State) :
    decodePlainV2 d.terms d.nameLists (encodePlainV2 d s) = some s := by
  unfold encodePlainV2
  generalize envTable s = table
  obtain ⟨envs, envIndex⟩ := table
  have each : ∀ e ∈ envs.toList, ∀ rest, decodeAddressesV2 (encodeAddressesV2 e ++ rest) = some (e, rest) :=
    fun e _ rest => addressesV2_roundTrip e rest
  have table := many_roundTrip decodeAddressesV2 encodeAddressesV2 envs.toList
    (encodeBodyV2 ⟨d.terms, d.findTerm, envs, fun e => envIndex[e]?, d.nameLists, fun n => d.nameHint[n]?⟩ s) each
  rw [Array.length_toList] at table
  simp only [decodePlainV2, List.cons_append]
  rw [table]
  simp only [Option.bind_eq_bind, Option.bind_some, Array.toArray_toList]
  exact bodyV2_roundTrip ⟨d.terms, d.findTerm, envs, fun e => envIndex[e]?, d.nameLists, fun n => d.nameHint[n]?⟩
    s _ (by simp; omega)

/-- **The v2 checkpoint round trip.** A state encoded against a program's dictionary is
restored exactly by decoding against the program's terms, strings and name lists, for
every dictionary (its hints only find candidates; every reference is checked). -/
theorem stateV2_roundTrip (d : Dictionary) (s : State) :
    decodeStateV2 d.terms d.strings d.nameLists (encodeStateV2 d s) = some s := by
  unfold decodeStateV2 encodeStateV2 internAll
  simp only []
  rw [strings_roundTrip]
  exact plainV2_roundTrip d s

/-! ## v3: relative addresses -/

theorem unzigzagFrom_zigzagFrom (i a : Nat) : unzigzagFrom i (zigzagFrom i a) = a := by
  unfold zigzagFrom unzigzagFrom
  split <;> rename_i h
  · have : 2 * (i - a) % 2 = 0 := by omega
    simp only [this, beq_self_eq_true, ite_true]; omega
  · have : (2 * (a - i) - 1) % 2 = 1 := by omega
    have hne : ((2 * (a - i) - 1) % 2 == 0) = false := by rw [this]; rfl
    simp only [hne, Bool.false_eq_true, ite_false]; omega

theorem ofRelative_toRelative (i a : Nat) : ofRelative i (toRelative i a) = a := by
  unfold toRelative ofRelative
  split
  · have odd : (2 * zigzagFrom i a + 1) % 2 = 1 := by omega
    have half : (2 * zigzagFrom i a + 1) / 2 = zigzagFrom i a := by omega
    simp [odd, half, unzigzagFrom_zigzagFrom]
  · have even : 2 * a % 2 = 0 := by omega
    simp only [even]; simp

section
variable {f g : Address → Address} (inv : ∀ a, g (f a) = a)
include inv

theorem mapValue_inverse (v : RuntimeValue) : mapValueAddresses g (mapValueAddresses f v) = v := by
  cases v <;> simp [mapValueAddresses, inv, Function.comp_def]

theorem mapCell_inverse (c : Cell) : mapCellAddresses g (mapCellAddresses f c) = c := by
  cases c <;> simp [mapCellAddresses, mapValue_inverse inv, inv, Function.comp_def]

theorem mapFrame_inverse (fr : Frame) : mapFrameAddresses g (mapFrameAddresses f fr) = fr := by
  cases fr <;> simp [mapFrameAddresses, mapValue_inverse inv, inv, Function.comp_def]

theorem mapControl_inverse (c : Control) : mapControlAddresses g (mapControlAddresses f c) = c := by
  cases c <;> simp [mapControlAddresses, mapValue_inverse inv, inv, Function.comp_def]
end

theorem absolute_relative (s : State) : absoluteState (relativeState s) = s := by
  obtain ⟨heap, control, stack⟩ := s
  simp only [absoluteState, relativeState, mapStateAddresses, Array.size_mapIdx]
  congr 1
  · apply Array.ext
    · simp
    · intro i h1 h2
      simp [mapCell_inverse (ofRelative_toRelative i)]
  · exact mapControl_inverse (ofRelative_toRelative heap.size) control
  · rw [List.map_map]
    conv => rhs; rw [← List.map_id stack]
    apply List.map_congr_left
    intro fr _
    exact mapFrame_inverse (ofRelative_toRelative heap.size) fr

/-- **The v3 checkpoint round trip**, for every dictionary and every state. -/
theorem stateV3_roundTrip (d : Dictionary) (s : State) :
    decodeStateV3 d.terms d.strings d.nameLists (encodeStateV3 d s) = some s := by
  unfold decodeStateV3 encodeStateV3 internAll
  simp only []
  rw [strings_roundTrip]
  simp only [Option.bind_some, plainV2_roundTrip, Option.map_some, absolute_relative]

#assert_axioms stateV2_roundTrip stateV3_roundTrip

end Minidregg.Theory.ObjectiveBendCheckpointRoundTrip
