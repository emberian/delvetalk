/- The checkpoint codec round trip: every machine State, in particular every
quiescent yielded activity, is restored exactly from its token encoding.
Fuel is the token count, so no separate depth bound is assumed. Ported from
Mini and extended to this edition's codec: unary primitives (`Term.unary`,
`Frame.unary`), finite Data tokens, native cells (`Cell.native`,
`Cell.nativeCached`), `Frame.nativeArgument` and `Control.nativeApplication`. -/
import Theory.ObjectiveBendCheckpoint
import Theory.AxiomPin
namespace Minidregg.Theory.ObjectiveBendCheckpointRoundTrip
open ObjectiveBendOpenRecursion ObjectiveBendDemandMachine ObjectiveBendCheckpoint
open Minidregg.Theory.ObjectiveBendDemandData (Data)
set_option autoImplicit false

theorem primitive_roundTrip (primitive : Primitive) : primitiveOf (primitiveCode primitive) = some primitive := by
  cases primitive <;> rfl

theorem unary_roundTrip (primitive : UnaryPrimitive) : unaryOf (unaryCode primitive) = some primitive := by
  cases primitive <;> rfl

theorem refusal_roundTrip (reason : Refusal) : refusalOf (refusalCode reason) = some reason := by
  cases reason <;> rfl

mutual
theorem term_roundTrip : ∀ (term : Term) (fuel : Nat) (rest : Tokens),
    (encodeTerm term).length ≤ fuel → decodeTerm fuel (encodeTerm term ++ rest) = some (term,rest)
  | .bound index, fuel+1, rest, _ => by simp [encodeTerm,decodeTerm]
  | .lam body, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons] at h
      simp [encodeTerm,decodeTerm,term_roundTrip body fuel rest (by omega)]
  | .app f a, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons,List.length_append] at h
      simp [encodeTerm,decodeTerm,List.append_assoc,term_roundTrip f fuel _ (by omega),term_roundTrip a fuel rest (by omega)]
  | .mix f a, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons,List.length_append] at h
      simp [encodeTerm,decodeTerm,List.append_assoc,term_roundTrip f fuel _ (by omega),term_roundTrip a fuel rest (by omega)]
  | .fix f a, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons,List.length_append] at h
      simp [encodeTerm,decodeTerm,List.append_assoc,term_roundTrip f fuel _ (by omega),term_roundTrip a fuel rest (by omega)]
  | .specification f a, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons,List.length_append] at h
      simp [encodeTerm,decodeTerm,List.append_assoc,term_roundTrip f fuel _ (by omega),term_roundTrip a fuel rest (by omega)]
  | .prototype f a, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons,List.length_append] at h
      simp [encodeTerm,decodeTerm,List.append_assoc,term_roundTrip f fuel _ (by omega),term_roundTrip a fuel rest (by omega)]
  | .reflect t, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons] at h
      simp [encodeTerm,decodeTerm,term_roundTrip t fuel rest (by omega)]
  | .metadata t, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons] at h
      simp [encodeTerm,decodeTerm,term_roundTrip t fuel rest (by omega)]
  | .project t, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons] at h
      simp [encodeTerm,decodeTerm,term_roundTrip t fuel rest (by omega)]
  | .nat value, fuel+1, rest, _ => by simp [encodeTerm,decodeTerm]
  | .boolean value, fuel+1, rest, _ => by cases value <;> simp [encodeTerm,decodeTerm]
  | .label value, fuel+1, rest, _ => by simp [encodeTerm,decodeTerm]
  | .binary p l r, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons,List.length_append] at h
      simp [encodeTerm,decodeTerm,List.append_assoc,primitive_roundTrip,
        term_roundTrip l fuel _ (by omega),term_roundTrip r fuel rest (by omega)]
  | .extend t fields, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons,List.length_append] at h
      simp [encodeTerm,decodeTerm,List.append_assoc,term_roundTrip t fuel _ (by omega),
        fields_roundTrip fields fuel rest (by omega)]
  | .record fields, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons] at h
      simp [encodeTerm,decodeTerm,fields_roundTrip fields fuel rest (by omega)]
  | .get t name, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons] at h
      simp [encodeTerm,decodeTerm,term_roundTrip t fuel rest (by omega)]
  | .ifZero v z s, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons,List.length_append] at h
      simp [encodeTerm,decodeTerm,List.append_assoc,term_roundTrip v fuel _ (by omega),
        term_roundTrip z fuel _ (by omega),term_roundTrip s fuel rest (by omega)]
  | .inject label payload, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons] at h
      simp [encodeTerm,decodeTerm,term_roundTrip payload fuel rest (by omega)]
  | .case s arms, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons,List.length_append] at h
      simp [encodeTerm,decodeTerm,List.append_assoc,term_roundTrip s fuel _ (by omega),
        fields_roundTrip arms fuel rest (by omega)]
  | .ifBool c t f, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons,List.length_append] at h
      simp [encodeTerm,decodeTerm,List.append_assoc,term_roundTrip c fuel _ (by omega),
        term_roundTrip t fuel _ (by omega),term_roundTrip f fuel rest (by omega)]
  | .perform p, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons] at h
      simp [encodeTerm,decodeTerm,term_roundTrip p fuel rest (by omega)]
  | .done v, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons] at h
      simp [encodeTerm,decodeTerm,term_roundTrip v fuel rest (by omega)]
  | .unary p t, fuel+1, rest, h => by
      simp only [encodeTerm,List.length_cons] at h
      simp [encodeTerm,decodeTerm,unary_roundTrip,term_roundTrip t fuel rest (by omega)]
  | term, 0, rest, h => by cases term <;> simp [encodeTerm] at h
theorem fields_roundTrip : ∀ (fields : List (String × Term)) (fuel : Nat) (rest : Tokens),
    (encodeFields fields).length ≤ fuel → decodeFields fuel (encodeFields fields ++ rest) = some (fields,rest)
  | [], fuel+1, rest, _ => by simp [encodeFields,decodeFields]
  | (name,body) :: others, fuel+1, rest, h => by
      simp only [encodeFields,List.length_cons,List.length_append] at h
      simp [encodeFields,decodeFields,List.append_assoc,term_roundTrip body fuel _ (by omega),
        fields_roundTrip others fuel rest (by omega)]
  | fields, 0, rest, h => by cases fields <;> simp [encodeFields] at h
end

theorem addressesN_roundTrip : ∀ (addresses : List Address) (rest : Tokens),
    decodeAddressesN addresses.length (addresses.map Token.nat ++ rest) = some (addresses,rest)
  | [], rest => by simp [decodeAddressesN]
  | address :: others, rest => by simp [decodeAddressesN,addressesN_roundTrip others rest]

theorem addresses_roundTrip (addresses : List Address) (rest : Tokens) :
    decodeAddresses (encodeAddresses addresses ++ rest) = some (addresses,rest) := by
  simp [encodeAddresses,decodeAddresses,addressesN_roundTrip]

theorem namedN_roundTrip : ∀ (fields : List (String × Address)) (rest : Tokens),
    decodeNamedN fields.length (fields.flatMap (fun field => [Token.text field.1, Token.nat field.2]) ++ rest) =
      some (fields,rest)
  | [], rest => by simp [decodeNamedN]
  | (name,address) :: others, rest => by simp [decodeNamedN,namedN_roundTrip others rest]

theorem named_roundTrip (fields : List (String × Address)) (rest : Tokens) :
    decodeNamed (encodeNamed fields ++ rest) = some (fields,rest) := by
  simp [encodeNamed,decodeNamed,namedN_roundTrip]

theorem closure_roundTrip (closure : Closure) (fuel : Nat) (rest : Tokens)
    (enough : (encodeClosure closure).length ≤ fuel) :
    decodeClosure fuel (encodeClosure closure ++ rest) = some (closure,rest) := by
  simp only [encodeClosure,List.length_append] at enough
  simp [encodeClosure,decodeClosure,List.append_assoc,term_roundTrip closure.term fuel _ (by omega),
    addresses_roundTrip]

theorem value_roundTrip (value : RuntimeValue) (fuel : Nat) (rest : Tokens)
    (enough : (encodeValue value).length ≤ fuel) :
    decodeValue fuel (encodeValue value ++ rest) = some (value,rest) := by
  cases value with
  | closure body environment =>
      simp only [encodeValue,List.length_cons,List.length_append] at enough
      have := closure_roundTrip ⟨body,environment⟩ fuel rest
        (by simp only [encodeClosure,List.length_append]; omega)
      simp only [encodeClosure,List.append_assoc] at this
      simp [encodeValue,decodeValue,List.append_assoc,this]
  | boolean b => cases b <;> simp [encodeValue,decodeValue]
  | record fields => simp [encodeValue,decodeValue,named_roundTrip]
  | _ => simp [encodeValue,decodeValue]

mutual
theorem data_roundTrip : ∀ (data : Data) (fuel : Nat) (rest : Tokens),
    (encodeData data).length ≤ fuel → decodeData fuel (encodeData data ++ rest) = some (data,rest)
  | .natural value, fuel+1, rest, _ => by simp [encodeData,decodeData]
  | .boolean value, fuel+1, rest, _ => by cases value <;> simp [encodeData,decodeData]
  | .label value, fuel+1, rest, _ => by simp [encodeData,decodeData]
  | .record fields, fuel+1, rest, h => by
      simp only [encodeData,List.length_cons] at h
      simp [encodeData,decodeData,dataFields_roundTrip fields fuel rest (by omega)]
  | .variant label payload, fuel+1, rest, h => by
      simp only [encodeData,List.length_cons] at h
      simp [encodeData,decodeData,data_roundTrip payload fuel rest (by omega)]
  | data, 0, rest, h => by cases data <;> simp [encodeData] at h
theorem dataFields_roundTrip : ∀ (fields : List (String × Data)) (fuel : Nat) (rest : Tokens),
    (encodeDataFields fields).length ≤ fuel →
      decodeDataFields fuel fields.length (encodeDataFields fields ++ rest) = some (fields,rest)
  | [], fuel, rest, _ => by simp [encodeDataFields,decodeDataFields]
  | (name,value) :: others, fuel, rest, h => by
      simp only [encodeDataFields,List.length_cons,List.length_append] at h
      simp [encodeDataFields,decodeDataFields,List.append_assoc,data_roundTrip value fuel _ (by omega),
        dataFields_roundTrip others fuel rest (by omega)]
end

theorem cell_roundTrip (cell : Cell) (fuel : Nat) (rest : Tokens)
    (enough : (encodeCell cell).length ≤ fuel) :
    decodeCell fuel (encodeCell cell ++ rest) = some (cell,rest) := by
  cases cell with
  | suspended origin =>
      simp only [encodeCell,List.length_cons] at enough
      simp [encodeCell,decodeCell,closure_roundTrip origin fuel rest (by omega)]
  | evaluating origin =>
      simp only [encodeCell,List.length_cons] at enough
      simp [encodeCell,decodeCell,closure_roundTrip origin fuel rest (by omega)]
  | cached origin value =>
      simp only [encodeCell,List.length_cons,List.length_append] at enough
      simp [encodeCell,decodeCell,List.append_assoc,closure_roundTrip origin fuel _ (by omega),
        value_roundTrip value fuel rest (by omega)]
  | native origin =>
      simp only [encodeCell,List.length_cons] at enough
      simp [encodeCell,decodeCell,data_roundTrip origin fuel rest (by omega)]
  | nativeCached origin value =>
      simp only [encodeCell,List.length_cons,List.length_append] at enough
      simp [encodeCell,decodeCell,List.append_assoc,data_roundTrip origin fuel _ (by omega),
        value_roundTrip value fuel rest (by omega)]

theorem frame_roundTrip (frame : Frame) (fuel : Nat) (rest : Tokens)
    (enough : (encodeFrame frame).length ≤ fuel) :
    decodeFrame fuel (encodeFrame frame ++ rest) = some (frame,rest) := by
  cases frame with
  | argument term environment =>
      simp only [encodeFrame,List.length_cons,List.length_append] at enough
      simp [encodeFrame,decodeFrame,List.append_assoc,term_roundTrip term fuel _ (by omega),addresses_roundTrip]
  | extend fields environment =>
      simp only [encodeFrame,List.length_cons,List.length_append] at enough
      simp [encodeFrame,decodeFrame,List.append_assoc,fields_roundTrip fields fuel _ (by omega),addresses_roundTrip]
  | condition zero successorBody environment =>
      simp only [encodeFrame,List.length_cons,List.length_append] at enough
      simp [encodeFrame,decodeFrame,List.append_assoc,term_roundTrip zero fuel _ (by omega),
        term_roundTrip successorBody fuel _ (by omega),addresses_roundTrip]
  | binaryLeft primitive right environment =>
      simp only [encodeFrame,List.length_cons,List.length_append] at enough
      simp [encodeFrame,decodeFrame,List.append_assoc,primitive_roundTrip,
        term_roundTrip right fuel _ (by omega),addresses_roundTrip]
  | binaryRight primitive left =>
      simp only [encodeFrame,List.length_cons] at enough
      simp [encodeFrame,decodeFrame,primitive_roundTrip,value_roundTrip left fuel rest (by omega)]
  | case arms environment =>
      simp only [encodeFrame,List.length_cons,List.length_append] at enough
      simp [encodeFrame,decodeFrame,List.append_assoc,fields_roundTrip arms fuel _ (by omega),addresses_roundTrip]
  | ifBool whenTrue whenFalse environment =>
      simp only [encodeFrame,List.length_cons,List.length_append] at enough
      simp [encodeFrame,decodeFrame,List.append_assoc,term_roundTrip whenTrue fuel _ (by omega),
        term_roundTrip whenFalse fuel _ (by omega),addresses_roundTrip]
  | nativeArgument value =>
      simp only [encodeFrame,List.length_cons] at enough
      simp [encodeFrame,decodeFrame,data_roundTrip value fuel rest (by omega)]
  | unary primitive => simp [encodeFrame,decodeFrame,unary_roundTrip]
  | _ => simp [encodeFrame,decodeFrame]

theorem length_le_flatMap {α : Type} (encode : α → Tokens) :
    ∀ (items : List α) (item : α), item ∈ items → (encode item).length ≤ (items.flatMap encode).length
  | [], _, member => by simp at member
  | first :: others, item, member => by
      simp only [List.mem_cons] at member
      rcases member with rfl | member
      · simp
      · have := length_le_flatMap encode others item member
        simp only [List.flatMap_cons,List.length_append]; omega

theorem many_roundTrip {α : Type} (decode : Tokens → Option (α × Tokens)) (encode : α → Tokens) :
    ∀ (items : List α) (rest : Tokens),
      (∀ item ∈ items, ∀ rest, decode (encode item ++ rest) = some (item,rest)) →
      decodeMany decode items.length (items.flatMap encode ++ rest) = some (items,rest)
  | [], rest, _ => by simp [decodeMany]
  | first :: others, rest, each => by
      simp only [List.flatMap_cons,List.length_cons,List.append_assoc,decodeMany]
      rw [each first (by simp)]
      simp [many_roundTrip decode encode others rest (fun item member => each item (by simp [member]))]

theorem control_roundTrip (control : Control) (fuel : Nat) (rest : Tokens)
    (enough : (encodeControl control).length ≤ fuel) :
    decodeControl fuel (encodeControl control ++ rest) = some (control,rest) := by
  cases control with
  | evaluate term environment =>
      simp only [encodeControl,List.length_cons,List.length_append] at enough
      simp [encodeControl,decodeControl,List.append_assoc,term_roundTrip term fuel _ (by omega),addresses_roundTrip]
  | returned value =>
      simp only [encodeControl,List.length_cons] at enough
      simp [encodeControl,decodeControl,value_roundTrip value fuel rest (by omega)]
  | complete value =>
      simp only [encodeControl,List.length_cons] at enough
      simp [encodeControl,decodeControl,value_roundTrip value fuel rest (by omega)]
  | refused reason => simp [encodeControl,decodeControl,refusal_roundTrip]
  | nativeApplication function argument remaining =>
      simp only [encodeControl,List.length_cons,List.length_append] at enough
      have each : ∀ item ∈ remaining, ∀ rest,
          decodeData fuel (encodeData item ++ rest) = some (item,rest) := by
        intro item member rest
        apply data_roundTrip
        have := length_le_flatMap encodeData remaining item member
        omega
      simp [encodeControl,decodeControl,List.append_assoc,term_roundTrip function fuel _ (by omega),
        data_roundTrip argument fuel _ (by omega),many_roundTrip (decodeData fuel) encodeData remaining rest each]
  | _ => simp [encodeControl,decodeControl]

/-- **The checkpoint round trip.** Decoding the encoding of ANY machine state
restores exactly that state: heap cells (with closures, phases and cached
values), control (including a yield) and every continuation frame. -/
theorem state_roundTrip (state : State) : decodeState (encodeState state) = some state := by
  obtain ⟨heap,control,stack⟩ := state
  have shape : encodeState ⟨heap,control,stack⟩ = Token.text checkpointEdition :: Token.nat heap.size ::
      (heap.toList.flatMap encodeCell ++ (encodeControl control ++
        (Token.nat stack.length :: stack.flatMap encodeFrame))) := by
    simp [encodeState]
  have size : (encodeState ⟨heap,control,stack⟩).length =
      2 + ((heap.toList.flatMap encodeCell).length + ((encodeControl control).length +
        (1 + (stack.flatMap encodeFrame).length))) := by
    rw [shape]; simp; omega
  have cells : ∀ cell ∈ heap.toList, ∀ rest,
      decodeCell ((encodeState ⟨heap,control,stack⟩).length+1) (encodeCell cell ++ rest) = some (cell,rest) := by
    intro cell member rest
    apply cell_roundTrip
    have := length_le_flatMap encodeCell _ cell member
    omega
  have frames : ∀ frame ∈ stack, ∀ rest,
      decodeFrame ((encodeState ⟨heap,control,stack⟩).length+1) (encodeFrame frame ++ rest) = some (frame,rest) := by
    intro frame member rest
    apply frame_roundTrip
    have := length_le_flatMap encodeFrame _ frame member
    omega
  have controlOk : ∀ rest, decodeControl ((encodeState ⟨heap,control,stack⟩).length+1)
      (encodeControl control ++ rest) = some (control,rest) := by
    intro rest
    apply control_roundTrip
    omega
  have heapDecoded := many_roundTrip (decodeCell ((encodeState ⟨heap,control,stack⟩).length+1)) encodeCell
    heap.toList (encodeControl control ++ (Token.nat stack.length :: stack.flatMap encodeFrame)) cells
  have stackDecoded := many_roundTrip (decodeFrame ((encodeState ⟨heap,control,stack⟩).length+1)) encodeFrame
    stack [] frames
  rw [List.append_nil] at stackDecoded
  unfold decodeState
  simp only []
  generalize (encodeState ⟨heap,control,stack⟩).length + 1 = fuel at heapDecoded stackDecoded controlOk ⊢
  rw [shape]
  simp only [checkpointEdition,bne_self_eq_false,Bool.false_eq_true,if_false]
  rw [show heap.size = heap.toList.length by simp,heapDecoded]
  simp [controlOk,stackDecoded]

#assert_axioms state_roundTrip data_roundTrip

end Minidregg.Theory.ObjectiveBendCheckpointRoundTrip
