/-
# Pred.HashEqDigest — the commitment the `hashEq` atom opens

`Pred.hashEq values blinder commit` (Pred/Core) is true iff the `commit` slot holds the
cSHAKE256 digest of the canonical encoding of an `Opening`: the cell the step is about (the
`request/target` slot), the slot names (the value slots in order, then blinder and commit), and
the values at the value slots and `blinder`. One commitment opens a whole tuple at once.

Encoding, all big-endian and fixed-width, so a client rebuilds it with `int.to_bytes`:

| part        | bytes                         | domain                         |
|-------------|-------------------------------|--------------------------------|
| cell        | 8                             | `0 ≤ cell < 2^64`              |
| n           | 4, the number of value slots  | `n < 2^32`                     |
| name ×(n+2) | 4-byte length ‖ UTF-8 bytes   | length `< 2^32`                |
| value ×n    | 32 each, of `value + 2^255`   | `-2^255 ≤ value < 2^255`       |
| blinder     | 32                            | `0 ≤ blinder < 2^256`          |

The digest is the 32 output bytes of `cSHAKE256(N = "", S = "DREGG.PRED.HASHEQ/v2")`, read
big-endian as a natural. The function is `Compiler.Sp800185Cshake256.cshake256Bytes`, the same
executable cSHAKE256 the kernel's request digests use, under this atom's own customization string:
the one-customization-per-purpose discipline of the private-cell envelope
(`native/resource-client/src/private.rs`, `DREGG.PRIVATE-CELL.COMMIT/v1`). The blinder is the
envelope's 32-byte uniform `r`. (`/v1` was the single-value encoding of K-HASHEQ, retired with
its codec tag: a `/v1` commitment opens nothing here.) Outside the domain an opening is undefined and the atom fails
closed (Pred/Core).

Imports: Init and the leaf `Theory.Sp800185Cshake256Core` (itself Init only, no candidate
code). The cSHAKE256 definition lives in the Theory tier, so `Pred` imports no `Compiler` module
(the Pred row of scripts/check-import-boundary.sh no longer admits one).
-/
import Theory.Sp800185Cshake256Core
import Theory.HashBytes

namespace Minidregg.Pred.HashEqDigest

open Minidregg.Theory.HashBytes

set_option autoImplicit false

/-! ## §1. Fixed-width big-endian bytes: `Theory.HashBytes` (`be`, `ofBE`, `be_injective`) -/

/-! ## §2. Names -/

/-- The UTF-8 bytes of a string. -/
def utf8 (s : String) : List UInt8 := s.toUTF8.data.toList

theorem utf8_injective {s t : String} (h : utf8 s = utf8 t) : s = t := by
  simp only [utf8, String.toUTF8_eq_toByteArray] at h
  exact String.toByteArray_inj.mp (ByteArray.ext (Array.toList_inj.mp h))

/-- A length-prefixed name: 4-byte big-endian UTF-8 length, then the bytes. -/
def name (s : String) : List UInt8 := be 4 (utf8 s).length ++ utf8 s

theorem name_split {s t : String} {rest rest' : List UInt8}
    (hs : (utf8 s).length < 2 ^ 32) (ht : (utf8 t).length < 2 ^ 32)
    (h : name s ++ rest = name t ++ rest') : s = t ∧ rest = rest' := by
  simp only [name, List.append_assoc] at h
  obtain ⟨hlen, htail⟩ := List.append_inj h (by simp)
  have h32 : (2 : Nat) ^ 32 = 256 ^ 4 := by decide
  rw [h32] at hs ht
  have hl := be_injective hs ht hlen
  obtain ⟨hu, hr⟩ := List.append_inj htail hl
  exact ⟨utf8_injective hu, hr⟩

/-! ## §3. The opening and its preimage

An opening is a TUPLE: one commitment binds `n ≥ 0` value slots at once (an order's price and
quantity, say), under one blinder. The count is in the encoding, so the value list is read back
whole: there is no partial opening of a tuple commitment, and a commitment to `[price, qty]` is
not an opening of `[qty, price]` or of `[price]` (`preimage_injective`). -/

/-- Everything a commitment binds: the cell, the value slots' names in order, the blinder and
commit slots' names, the values and the blinder. -/
structure Opening where
  cell : Int
  valueSlots : List String
  blinderSlot : String
  commitSlot : String
  values : List Int
  blinder : Int
deriving DecidableEq, Repr

/-- The encoding's domain. -/
def Opening.Admissible (o : Opening) : Prop :=
  0 ≤ o.cell ∧ o.cell < 2 ^ 64 ∧
  o.valueSlots.length < 2 ^ 32 ∧ o.values.length = o.valueSlots.length ∧
  (∀ s ∈ o.valueSlots, (utf8 s).length < 2 ^ 32) ∧
  (utf8 o.blinderSlot).length < 2 ^ 32 ∧ (utf8 o.commitSlot).length < 2 ^ 32 ∧
  (∀ x ∈ o.values, -2 ^ 255 ≤ x ∧ x < 2 ^ 255) ∧
  0 ≤ o.blinder ∧ o.blinder < 2 ^ 256

instance (o : Opening) : Decidable o.Admissible := by
  unfold Opening.Admissible; infer_instance

/-- The length-prefixed names of a list of slots, in order. -/
def names : List String → List UInt8
  | [] => []
  | s :: l => name s ++ names l

/-- One value as 32 big-endian bytes of `value + 2^255`. -/
def word (x : Int) : List UInt8 := be 32 (x + 2 ^ 255).toNat

/-- The values, each one fixed 32-byte word, in order. -/
def words : List Int → List UInt8
  | [] => []
  | x :: l => word x ++ words l

/-- The canonical preimage: `cell:8 ‖ n:4 ‖ (len:4 ‖ name)×n ‖ blinder name ‖ commit name ‖
(value + 2^255):32 × n ‖ blinder:32`. -/
def Opening.preimage (o : Opening) : List UInt8 :=
  be 8 o.cell.toNat ++ be 4 o.valueSlots.length ++ names o.valueSlots ++ name o.blinderSlot ++
    name o.commitSlot ++ words o.values ++ be 32 o.blinder.toNat

private theorem toNat_eq {a b : Int} (ha : 0 ≤ a) (hb : 0 ≤ b) (h : a.toNat = b.toNat) :
    a = b := by
  have := congrArg (fun n : Nat => (n : Int)) h
  simp only [Int.toNat_of_nonneg ha, Int.toNat_of_nonneg hb] at this
  exact this

private theorem toNat_lt {a : Int} {k : Nat} (ha : 0 ≤ a) (hk : a < (k : Int)) : a.toNat < k := by
  omega

theorem names_split {l l' : List String} {rest rest' : List UInt8}
    (hl : ∀ s ∈ l, (utf8 s).length < 2 ^ 32) (hl' : ∀ s ∈ l', (utf8 s).length < 2 ^ 32)
    (hlen : l.length = l'.length) (h : names l ++ rest = names l' ++ rest') :
    l = l' ∧ rest = rest' := by
  induction l generalizing l' rest rest' with
  | nil =>
    cases l' with
    | nil => exact ⟨rfl, by simpa only [names, List.nil_append] using h⟩
    | cons _ _ => exact (Nat.succ_ne_zero _ hlen.symm).elim
  | cons s l ih =>
    cases l' with
    | nil => exact (Nat.succ_ne_zero _ hlen).elim
    | cons s' l' =>
      simp only [names, List.append_assoc] at h
      obtain ⟨hs, h⟩ := name_split (hl s (List.Mem.head _)) (hl' s' (List.Mem.head _)) h
      obtain ⟨htl, hr⟩ := ih (fun t ht => hl t (List.Mem.tail _ ht))
        (fun t ht => hl' t (List.Mem.tail _ ht)) (Nat.succ.inj hlen) h
      exact ⟨by rw [hs, htl], hr⟩

theorem word_injective {x y : Int} (hx0 : -2 ^ 255 ≤ x) (hx1 : x < 2 ^ 255)
    (hy0 : -2 ^ 255 ≤ y) (hy1 : y < 2 ^ 255) (h : word x = word y) : x = y := by
  have p32 : ((256 ^ 32 : Nat) : Int) = 2 ^ 256 := by decide
  have e : x + 2 ^ 255 = y + 2 ^ 255 :=
    toNat_eq (by omega) (by omega)
      (be_injective (toNat_lt (by omega) (by rw [p32]; omega))
        (toNat_lt (by omega) (by rw [p32]; omega)) h)
  omega

theorem words_split {l l' : List Int} {rest rest' : List UInt8}
    (hl : ∀ x ∈ l, -2 ^ 255 ≤ x ∧ x < 2 ^ 255) (hl' : ∀ x ∈ l', -2 ^ 255 ≤ x ∧ x < 2 ^ 255)
    (hlen : l.length = l'.length) (h : words l ++ rest = words l' ++ rest') :
    l = l' ∧ rest = rest' := by
  induction l generalizing l' rest rest' with
  | nil =>
    cases l' with
    | nil => exact ⟨rfl, by simpa only [words, List.nil_append] using h⟩
    | cons _ _ => exact (Nat.succ_ne_zero _ hlen.symm).elim
  | cons x l ih =>
    cases l' with
    | nil => exact (Nat.succ_ne_zero _ hlen).elim
    | cons y l' =>
      simp only [words, List.append_assoc] at h
      obtain ⟨hw, h⟩ := List.append_inj h (by simp only [word, length_be])
      obtain ⟨hx0, hx1⟩ := hl x (List.Mem.head _)
      obtain ⟨hy0, hy1⟩ := hl' y (List.Mem.head _)
      have hxy := word_injective hx0 hx1 hy0 hy1 hw
      obtain ⟨htl, hr⟩ := ih (fun t ht => hl t (List.Mem.tail _ ht))
        (fun t ht => hl' t (List.Mem.tail _ ht)) (Nat.succ.inj hlen) h
      exact ⟨by rw [hxy, htl], hr⟩

/-- **The encoding is injective on its domain.** Distinct admissible openings — differing in the
cell, in any slot name, in the arity or order of the tuple, in any value, or in the blinder — have
distinct preimages, so any digest equality between distinct openings is a collision of the hash. -/
theorem preimage_injective {a b : Opening} (ha : a.Admissible) (hb : b.Admissible)
    (h : a.preimage = b.preimage) : a = b := by
  obtain ⟨ac0, ac1, an, alen, av, ab, acm, ax, ar0, ar1⟩ := ha
  obtain ⟨bc0, bc1, bn, blen, bv, bb, bcm, bx, br0, br1⟩ := hb
  simp only [Opening.preimage, List.append_assoc] at h
  obtain ⟨hcell, h⟩ := List.append_inj h (by simp)
  obtain ⟨hn, h⟩ := List.append_inj h (by simp)
  have h32 : (2 : Nat) ^ 32 = 256 ^ 4 := by decide
  have hlen : a.valueSlots.length = b.valueSlots.length :=
    be_injective (by rw [← h32]; exact an) (by rw [← h32]; exact bn) hn
  obtain ⟨hv, h⟩ := names_split av bv hlen h
  obtain ⟨hbl, h⟩ := name_split ab bb h
  obtain ⟨hcm, h⟩ := name_split acm bcm h
  obtain ⟨hx, hr⟩ := words_split ax bx (by rw [alen, blen, hlen]) h
  have p8 : ((256 ^ 8 : Nat) : Int) = 2 ^ 64 := by decide
  have p32 : ((256 ^ 32 : Nat) : Int) = 2 ^ 256 := by decide
  have hc : a.cell = b.cell :=
    toNat_eq ac0 bc0 (be_injective (toNat_lt ac0 (p8 ▸ ac1)) (toNat_lt bc0 (p8 ▸ bc1)) hcell)
  have hr' : a.blinder = b.blinder :=
    toNat_eq ar0 br0 (be_injective (toNat_lt ar0 (p32 ▸ ar1)) (toNat_lt br0 (p32 ▸ br1)) hr)
  cases a; cases b
  simp only [Opening.mk.injEq]
  exact ⟨hc, hv, hbl, hcm, hx, hr'⟩

theorem words_length (l : List Int) : (words l).length = 32 * l.length := by
  induction l with
  | nil => rfl
  | cons x l ih => simp [words, word, ih]; omega

/-- For fixed names and arity the preimage length is fixed: the value and blinder widths are
fixed. (This is what a length hash cannot see past.) -/
theorem preimage_length (o : Opening) :
    o.preimage.length =
      8 + 4 + (names o.valueSlots).length + (4 + (utf8 o.blinderSlot).length) +
        (4 + (utf8 o.commitSlot).length) + 32 * o.values.length + 32 := by
  simp [Opening.preimage, name, words_length]
  omega

/-! ## §4. The digest, generic in the hash, and its deployed instance -/

/-- The digest an opening commits to under `H`, as the integer the commit slot holds. -/
def digestWith (H : Hash) (o : Opening) : Int := (ofBE (H o.preimage) : Int)

/-- The customization string of this atom's cSHAKE256. -/
def customization : List UInt8 := utf8 "DREGG.PRED.HASHEQ/v2"

open Minidregg.Compiler.Sp800185Cshake256 (customizationPrefix cshake256Bytes squeeze32
  absorbPadded padForRate natBytesBE bytepad encodeString leftEncode rateBytes) in
/-- The SP 800-185 prefix `bytepad(encode_string("") ‖ encode_string(S), 136)` for this `S`,
spelled out (`left_encode 136`, `encode_string ""`, `left_encode 160`, the 20 bytes of `S`, 110
zero bytes). `frame_eq` proves it is the cSHAKE module's own `customizationPrefix`; it is spelled
out so the evaluator's definition stays a literal (the core's `natBytesBE` is structural since
CH-CLIENT-1 and no longer reaches `Nat.digits`), which keeps `Pred.eval`'s axiom closure at
`[propext, Quot.sound]`. -/
def frame : List UInt8 := [1, 136, 1, 0, 1, 160] ++ customization ++ List.replicate 110 0

open Minidregg.Compiler.Sp800185Cshake256 (squeeze32 absorbPadded padForRate) in
/-- **The deployed hash**: cSHAKE256 (SP 800-185, empty function name, 256-bit output) under
this atom's customization, through the kernel's executable Keccak-f[1600] sponge. Equal to
`cshake256Bytes customization` (`deployed_eq_cshake256Bytes`). -/
def deployed : Hash := fun input => squeeze32 (absorbPadded (padForRate (frame ++ input) 0x04))

theorem customization_length : customization.length = 20 := by decide

open Minidregg.Compiler.Sp800185Cshake256 in
theorem frame_eq : customizationPrefix customization = frame := by
  decide

open Minidregg.Compiler.Sp800185Cshake256 in
/-- The spelled-out sponge **is** the kernel's cSHAKE256 at this customization: one function, not
a second implementation. -/
theorem deployed_eq_cshake256Bytes : deployed = cshake256Bytes customization := by
  funext input
  have hne : (customization = []) = False := by
    apply propext; constructor
    · intro h; have := congrArg List.length h; rw [customization_length] at this; cases this
    · intro h; cases h
  simp only [deployed, cshake256Bytes, hne, if_false, frame_eq]

open Minidregg.Compiler.Sp800185Cshake256 (absorbPadded padForRate squeeze32) in
open Minidregg.Compiler.Sp800185Cshake256.Fast in
/-- The deployed hash on the compiled path: frame and input pushed once into a
byte array, absorbed by the word permutation (`Theory.Sp800185Cshake256Fast`). -/
def deployedFast : Hash := fun input =>
  spongeBytes (pushList (pushList ByteArray.empty frame) input) 0x04

open Minidregg.Compiler.Sp800185Cshake256.Fast in
theorem deployedFast_eq : deployedFast = deployed := by
  funext input
  simp only [deployedFast, deployed, sponge_fast_eq, pushList_data, empty_data, List.nil_append]

/-- The compiled `hashEq` atom runs the fast path; `deployed` stays the definition. -/
@[csimp] theorem deployed_eq_fast : deployed = deployedFast := deployedFast_eq.symm

/-- **Binds or collides.** Two admissible openings with equal digests are equal, or `H` has a
collision. Nothing about cSHAKE is assumed here; the disjunct is where its collision resistance
enters. -/
theorem binds_or_collides (H : Hash) {a b : Opening} (ha : a.Admissible) (hb : b.Admissible)
    (h : digestWith H a = digestWith H b) : a = b ∨ Collision H := by
  by_cases hab : a = b
  · exact .inl hab
  · refine .inr ⟨a.preimage, b.preimage, fun hp => hab (preimage_injective ha hb hp), ?_⟩
    simpa [digestWith, Int.ofNat_inj] using h

/-! ## §5. The refutable pole: a length hash -/

/-- The weakest hash that still reads its input: the 32-byte length. -/
def lengthHash : Hash := fun bytes => be 32 bytes.length

/-- The collision disjunct is not vacuous: the length hash has one. -/
theorem lengthHash_collides : Collision lengthHash :=
  ⟨[0], [1], by decide, rfl⟩

/-- **Under a length hash, binding fails for every opening**: changing the values (keeping the
arity) or the blinder inside the domain never changes the digest. So `binds_or_collides` is
carried by the hash, not by the encoding. -/
theorem lengthHash_binding_fails (o : Opening) (values : List Int) (blinder : Int)
    (arity : values.length = o.values.length) :
    digestWith lengthHash { o with values := values, blinder := blinder } =
      digestWith lengthHash o := by
  simp only [digestWith, lengthHash, preimage_length, arity]

/-! ## §6. Axiom pins — `deployed` (and so `Pred.eval`) reaches no `Classical.choice`. -/

/-- info: 'Minidregg.Pred.HashEqDigest.deployed' depends on axioms: [propext, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms deployed
/-- info: 'Minidregg.Pred.HashEqDigest.deployed_eq_cshake256Bytes' depends on axioms: [propext, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms deployed_eq_cshake256Bytes
/-- info: 'Minidregg.Pred.HashEqDigest.preimage_injective' depends on axioms: [propext, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms preimage_injective
/-- info: 'Minidregg.Pred.HashEqDigest.names_split' depends on axioms: [propext, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms names_split
/-- info: 'Minidregg.Pred.HashEqDigest.words_split' depends on axioms: [propext, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms words_split
/-- info: 'Minidregg.Pred.HashEqDigest.binds_or_collides' depends on axioms: [propext, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms binds_or_collides
/-- info: 'Minidregg.Pred.HashEqDigest.lengthHash_binding_fails' depends on axioms: [propext, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms lengthHash_binding_fails
/-- info: 'Minidregg.Pred.HashEqDigest.lengthHash_collides' does not depend on any axioms -/
#guard_msgs (whitespace := lax) in #print axioms lengthHash_collides
/-- info: 'Minidregg.Pred.HashEqDigest.deployed_eq_fast' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms deployed_eq_fast

end Minidregg.Pred.HashEqDigest
