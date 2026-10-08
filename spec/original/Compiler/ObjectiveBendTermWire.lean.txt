/- The checker's decoder inverts the front end's rendering of a term.

The front end renders the elaborator's annotated term as JSON (`ATerm.json`) inside the
typing packet, and the checker reads that packet with its own decoder
(`ObjectiveBendTyping.decodeTerm`). `decode_json` proves the two meet: on a term of nesting
depth at most the decoder's fuel, decoding the rendering yields exactly the erasure
(`ATerm.erase`) of the elaborator's term. `decodePacket_term` says the term a decoded
packet carries is the decoding of its `term` field. Together they let
`ObjectiveBendFrontEnd.accept` carry `packet.source.term = erased` as a proof.

The JSON object lookups go through `Std.TreeMap.Raw.getElem?_ofList_of_mem`: every
rendered object has literally distinct keys. -/
import Compiler.ObjectiveBendElaborate
import Theory.ObjectiveBendTyping
import Theory.AxiomPin
namespace Minidregg.Compiler.ObjectiveBendTermWire
open Lean
open Minidregg.Compiler.ObjectiveBendElaborate
open Minidregg.Theory.ObjectiveBendTyping (DecodedPacket decodePacket decodeTerm decodePrimitive jsonNat
  termNestingCapacity requireSome)
set_option autoImplicit false

mutual
/-- The nesting depth of an elaborated term: what `decodeTerm`'s fuel must cover. -/
def depth : ATerm → Nat
  | .bound _ | .nat _ | .boolean _ | .label _ => 1
  | .lam _ b | .reflect b | .metadata b | .project b | .inject _ _ _ b | .perform _ _ b | .done _ _ b => depth b + 1
  | .app a b | .mix a b | .fix a b | .specification a b | .prototype a b | .binary _ a b => max (depth a) (depth b) + 1
  | .ifZero a b c | .ifBool a b c => max (depth a) (max (depth b) (depth c)) + 1
  | .extend a fs | .case a fs => max (depth a) (fieldsDepth fs) + 1
  | .record fs => fieldsDepth fs + 1
  | .get a _ => depth a + 1
def fieldsDepth : List (String × ATerm) → Nat
  | [] => 0
  | (_, v) :: rest => max (depth v) (fieldsDepth rest)
end


/-- A rendered object answers each of its (distinct) keys with the value it was built with. -/
theorem getObjVal_mkObj {l : List (String × Json)} {k : String} {v : Json}
    (distinct : (l.map Prod.fst).Nodup) (mem : (k, v) ∈ l) :
    (Json.mkObj l).getObjVal? k = .ok v := by
  have pairwise : l.Pairwise (fun a b => ¬ compare a.1 b.1 = .eq) := by
    have := List.pairwise_map.mp distinct
    exact this.imp fun h e => h (Std.LawfulEqCmp.eq_of_compare e)
  simp only [Json.mkObj, Json.getObjVal?, Std.TreeMap.Raw.get?_eq_getElem?]
  rw [Std.TreeMap.Raw.getElem?_ofList_of_mem (k := k) (Std.ReflCmp.compare_self) pairwise mem]
  rfl

theorem getObjValD_mkObj {l : List (String × Json)} {k : String} {v : Json}
    (distinct : (l.map Prod.fst).Nodup) (mem : (k, v) ∈ l) :
    (Json.mkObj l).getObjValD k = v := by
  simp [Json.getObjValD, getObjVal_mkObj distinct mem, Except.toOption]
theorem bind_ok {α β : Type} {x : Except String α} {f : α → Except String β} {b : β} :
    (x >>= f) = .ok b ↔ ∃ a, x = .ok a ∧ f a = .ok b := by
  cases x <;> simp [bind, Except.bind]

attribute [local simp] getObjVal_mkObj getObjValD_mkObj Json.getObjValAs? fromJson? Json.getStr? Json.getBool?
  Json.getArr? pure Except.pure bind Except.bind

theorem depth_pos (t : ATerm) : 1 ≤ depth t := by cases t <;> simp [depth]

theorem primitive_round {p : String} {prim : CorePrimitive} (h : primitiveOf p = .ok prim) :
    decodePrimitive (Json.str p) = .ok prim := by
  unfold primitiveOf at h
  split at h <;> simp_all [decodePrimitive]

mutual
theorem decode_json : (t : ATerm) → (n : Nat) → (e : CoreTerm) → depth t ≤ n → t.erase = .ok e →
    decodeTerm n t.json = .ok e
  | t, 0, _, hd, _ => absurd hd (by have := depth_pos t; omega)
  | .bound i, n+1, e, _, he => by
    simp [ATerm.erase] at he; subst he; rw [decodeTerm]; simp [ATerm.json, jsonNat, toJson, Json.getNat?, JsonNumber.fromNat]
  | .lam _ b, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨eb, hb, he⟩ := he
    simp only [depth] at hd
    have db := decode_json b n eb (by omega) hb
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, db]

  | .reflect b, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨eb, hb, he⟩ := he
    simp only [depth] at hd
    have db := decode_json b n eb (by omega) hb
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, db]

  | .metadata b, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨eb, hb, he⟩ := he
    simp only [depth] at hd
    have db := decode_json b n eb (by omega) hb
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, db]

  | .project b, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨eb, hb, he⟩ := he
    simp only [depth] at hd
    have db := decode_json b n eb (by omega) hb
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, db]

  | .perform _ _ b, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨eb, hb, he⟩ := he
    simp only [depth] at hd
    have db := decode_json b n eb (by omega) hb
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, db]

  | .done _ _ b, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨eb, hb, he⟩ := he
    simp only [depth] at hd
    have db := decode_json b n eb (by omega) hb
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, db]

  | .app f a, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨ef, hf, ea, ha, he⟩ := he
    simp only [depth] at hd
    have df := decode_json f n ef (by omega) hf
    have da := decode_json a n ea (by omega) ha
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, df, da]

  | .mix f a, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨ef, hf, ea, ha, he⟩ := he
    simp only [depth] at hd
    have df := decode_json f n ef (by omega) hf
    have da := decode_json a n ea (by omega) ha
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, df, da]

  | .fix f a, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨ef, hf, ea, ha, he⟩ := he
    simp only [depth] at hd
    have df := decode_json f n ef (by omega) hf
    have da := decode_json a n ea (by omega) ha
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, df, da]

  | .specification f a, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨ef, hf, ea, ha, he⟩ := he
    simp only [depth] at hd
    have df := decode_json f n ef (by omega) hf
    have da := decode_json a n ea (by omega) ha
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, df, da]

  | .prototype f a, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨ef, hf, ea, ha, he⟩ := he
    simp only [depth] at hd
    have df := decode_json f n ef (by omega) hf
    have da := decode_json a n ea (by omega) ha
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, df, da]

  | .ifZero f a b, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨ef, hf, ea, ha, eb, hb, he⟩ := he
    simp only [depth] at hd
    have df := decode_json f n ef (by omega) hf
    have da := decode_json a n ea (by omega) ha
    have db := decode_json b n eb (by omega) hb
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, df, da, db]

  | .ifBool f a b, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨ef, hf, ea, ha, eb, hb, he⟩ := he
    simp only [depth] at hd
    have df := decode_json f n ef (by omega) hf
    have da := decode_json a n ea (by omega) ha
    have db := decode_json b n eb (by omega) hb
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, df, da, db]

  | .inject l _ _ b, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨eb, hb, he⟩ := he
    simp only [depth] at hd
    have db := decode_json b n eb (by omega) hb
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, db]

  | .get b name, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨eb, hb, he⟩ := he
    simp only [depth] at hd
    have db := decode_json b n eb (by omega) hb
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, db]

  | .binary p f a, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨prim, hp, ef, hf, ea, ha, he⟩ := he
    have dp := primitive_round hp
    simp only [depth] at hd
    have df := decode_json f n ef (by omega) hf
    have da := decode_json a n ea (by omega) ha
    simp at he; subst he
    rw [decodeTerm]; simp [ATerm.json, df, da, dp]

  | .nat v, n+1, e, _, he => by
    unfold ATerm.erase at he
    split at he
    · rename_i k hk
      split at he
      · rename_i canonical
        simp at he; subst he; rw [decodeTerm]
        simp only [toString] at canonical
        simp [ATerm.json, jsonNat, Json.getNat?, hk, requireSome, canonical, throw, throwThe, MonadExceptOf.throw]
      · simp at he
    · simp at he
  | .boolean b, n+1, e, _, he => by
    simp [ATerm.erase] at he; subst he; rw [decodeTerm]; simp [ATerm.json, toJson]
  | .label s, n+1, e, _, he => by
    simp [ATerm.erase] at he; subst he; rw [decodeTerm]; simp [ATerm.json]
  | .record fs, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨es, hs, he⟩ := he
    simp only [depth] at hd
    have ds := decode_fields fs n es (by omega) hs
    simp at he ds; subst he
    rw [decodeTerm]; simp [ATerm.json, fieldsJson, ds]
  | .extend f fs, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨ef, hf, es, hs, he⟩ := he
    simp only [depth] at hd
    have df := decode_json f n ef (by omega) hf
    have ds := decode_fields fs n es (by omega) hs
    simp at he ds; subst he
    rw [decodeTerm]; simp [ATerm.json, fieldsJson, df, ds]
  | .case f fs, n+1, e, hd, he => by
    simp only [ATerm.erase, bind_ok] at he
    obtain ⟨ef, hf, es, hs, he⟩ := he
    simp only [depth] at hd
    have df := decode_json f n ef (by omega) hf
    have ds := decode_arms fs n es (by omega) hs
    simp at he ds; subst he
    rw [decodeTerm]; simp [ATerm.json, armsJson, df, ds]
theorem decode_fields : (fs : List (String × ATerm)) → (n : Nat) → (es : List (String × CoreTerm)) →
    fieldsDepth fs ≤ n → eraseFields fs = .ok es →
    (fieldsArray fs).mapM (fun field => do
        return (← field.getObjValAs? String "name", ← decodeTerm n (← field.getObjVal? "value"))) = .ok es
  | [], _, es, _, he => by simp [eraseFields] at he; subst he; simp [fieldsArray]
  | (name, v) :: rest, n, es, hd, he => by
    simp only [eraseFields, bind_ok] at he
    obtain ⟨ev, hv, er, hr, he⟩ := he
    simp only [fieldsDepth] at hd
    have dv := decode_json v n ev (by omega) hv
    have dr := decode_fields rest n er (by omega) hr
    simp at he dr; subst he
    simp [fieldsArray, List.mapM_cons, dv, dr]
theorem decode_arms : (fs : List (String × ATerm)) → (n : Nat) → (es : List (String × CoreTerm)) →
    fieldsDepth fs ≤ n → eraseFields fs = .ok es →
    (armsArray fs).mapM (fun arm => do
        return (← arm.getObjValAs? String "label", ← decodeTerm n (← arm.getObjVal? "body"))) = .ok es
  | [], _, es, _, he => by simp [eraseFields] at he; subst he; simp [armsArray]
  | (name, v) :: rest, n, es, hd, he => by
    simp only [eraseFields, bind_ok] at he
    obtain ⟨ev, hv, er, hr, he⟩ := he
    simp only [fieldsDepth] at hd
    have dv := decode_json v n ev (by omega) hv
    have dr := decode_arms rest n er (by omega) hr
    simp at he dr; subst he
    simp [armsArray, List.mapM_cons, dv, dr]
end

/-- The term a decoded packet carries is the checker's decoding of the packet's `term` field. -/
theorem decodePacket_term {v j : Json} {p : DecodedPacket} (decoded : decodePacket v = .ok p)
    (term : v.getObjVal? "term" = .ok j) : decodeTerm termNestingCapacity j = .ok p.source.term := by
  unfold decodePacket at decoded
  simp only [bind_ok] at decoded
  obtain ⟨_, _, rest⟩ := decoded
  split at rest
  · simp [bind, Except.bind] at rest
  · simp only [bind_ok, term, pure, Except.pure] at rest
    obtain ⟨_, _, _, _, _, _, j', hj, t, ht, _, _, rest⟩ := rest
    cases hj; cases rest; exact ht

#assert_axioms getObjVal_mkObj
#assert_axioms decode_json
#assert_axioms decodePacket_term
end Minidregg.Compiler.ObjectiveBendTermWire
