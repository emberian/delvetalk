/-
# Theory.HashBytes — fixed-width big-endian bytes, byte hashes, and their collisions

The byte vocabulary the tree's commitments are built from. Pred's `hashEq` atom
(`Pred.HashEqDigest`) and Core4's `digest` primitive (`Theory.ObjectiveBendDigest`) both read a
hash's 32 output bytes with `ofBE` and state binding as "equal, or a `Collision` of the hash", so
the two layers share one carrier for the hash's failure rather than two that agree by accident.

* `be w n` — the low `w` bytes of `n`, big-endian; `be_injective` below `256 ^ w`, and `ofBE_be`
  reads them back.
* `ofBE` — big-endian bytes as a natural; `ofBE_lt` bounds it by the byte count.
* `Hash`, `Collision` — a byte hash and a collision of it at the integer reading of its output.

Init only: the channel library and the C differential link this module's compiled object.
-/

namespace Minidregg.Theory.HashBytes

set_option autoImplicit false

/-- The low `w` bytes of `n`, big-endian. -/
def be : Nat → Nat → List UInt8
  | 0, _ => []
  | w + 1, n => be w (n / 256) ++ [UInt8.ofNat (n % 256)]

/-- Big-endian bytes read back as a natural. -/
def ofBE (bytes : List UInt8) : Nat :=
  bytes.foldl (fun acc b => acc * 256 + b.toNat) 0

@[simp] theorem length_be (w n : Nat) : (be w n).length = w := by
  induction w generalizing n with
  | zero => rfl
  | succ w ih => simp [be, ih]

theorem be_injective {w n m : Nat} (hn : n < 256 ^ w) (hm : m < 256 ^ w)
    (h : be w n = be w m) : n = m := by
  induction w generalizing n m with
  | zero => simp at hn hm; omega
  | succ w ih =>
    simp only [be] at h
    obtain ⟨hhi, hlo⟩ := List.append_inj h (by simp)
    have hbyte : (UInt8.ofNat (n % 256)).toNat = (UInt8.ofNat (m % 256)).toNat := by
      rw [List.cons.inj hlo |>.1]
    simp only [UInt8.toNat_ofNat'] at hbyte
    have hpow : 256 ^ (w + 1) = 256 ^ w * 256 := Nat.pow_succ ..
    have hn' : n / 256 < 256 ^ w := (Nat.div_lt_iff_lt_mul (by decide)).mpr (hpow ▸ hn)
    have hm' : m / 256 < 256 ^ w := (Nat.div_lt_iff_lt_mul (by decide)).mpr (hpow ▸ hm)
    have hq := ih hn' hm' hhi
    have h8 : (2 : Nat) ^ 8 = 256 := by decide
    rw [h8] at hbyte
    omega

/-- Appending one byte shifts the reading by a byte. -/
theorem ofBE_append_single (bytes : List UInt8) (b : UInt8) :
    ofBE (bytes ++ [b]) = ofBE bytes * 256 + b.toNat := by
  simp [ofBE, List.foldl_append]

/-- `be` is read back exactly below `256 ^ w`. -/
theorem ofBE_be {w n : Nat} (hn : n < 256 ^ w) : ofBE (be w n) = n := by
  induction w generalizing n with
  | zero => simp at hn; subst hn; rfl
  | succ w ih =>
    have hpow : 256 ^ (w + 1) = 256 ^ w * 256 := Nat.pow_succ ..
    have hn' : n / 256 < 256 ^ w := (Nat.div_lt_iff_lt_mul (by decide)).mpr (hpow ▸ hn)
    simp only [be, ofBE_append_single, ih hn', UInt8.toNat_ofNat']
    have h8 : (2 : Nat) ^ 8 = 256 := by decide
    rw [h8]
    omega

/-- A `w`-byte reading is below `256 ^ w`. -/
theorem ofBE_lt_aux : ∀ (bytes : List UInt8) (acc : Nat),
    bytes.foldl (fun acc b => acc * 256 + b.toNat) acc < (acc + 1) * 256 ^ bytes.length
  | [], acc => by simp
  | b :: rest, acc => by
    have hb : b.toNat < 256 := b.toNat_lt
    have ih := ofBE_lt_aux rest (acc * 256 + b.toNat)
    simp only [List.foldl_cons, List.length_cons]
    have hle : (acc * 256 + b.toNat + 1) ≤ (acc + 1) * 256 := by omega
    have hmono := Nat.mul_le_mul_right (256 ^ rest.length) hle
    rw [Nat.pow_succ, Nat.mul_comm (256 ^ rest.length) 256, ← Nat.mul_assoc]
    omega

theorem ofBE_lt (bytes : List UInt8) : ofBE bytes < 256 ^ bytes.length := by
  have := ofBE_lt_aux bytes 0
  simpa [ofBE] using this

/-- A byte hash. -/
abbrev Hash := List UInt8 → List UInt8

/-- A collision of `H` at the integer reading of its output. -/
def Collision (H : Hash) : Prop := ∃ a b : List UInt8, a ≠ b ∧ ofBE (H a) = ofBE (H b)

end Minidregg.Theory.HashBytes
