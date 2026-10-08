/-
# Theory.Sp800185Cshake256Fast -- the compiled cSHAKE256, proved equal to the spec

`Sp800185Cshake256Spec` defines cSHAKE256 over lists and `BitVec 64` lanes;
every theorem in the repository is about those definitions.  This module is
what the compiled Host runs instead, and it is proved equal to them for every
input:

* `KState`: the Keccak state as twenty-five unboxed `UInt64` fields.  One round
  (`roundS`) is straight-line word code — theta, rho/pi, chi, iota — with no
  arrays, lists or closures.  `keccakF_fast_eq` proves the twenty-four rounds
  equal `keccakF1600` on the lane representation `KState.toState`, stage by
  stage and lane by lane.  The proof is symbolic (each lane is an XOR/AND/NOT/
  rotate term over the input lanes); the permutation is never evaluated by
  the kernel.
* absorption reads rate blocks straight out of a `ByteArray` (`absorbLoop`,
  `absorb_fast_eq` against the spec's `absorbFrom`), padding is built in the
  array (`padBA_data` against `padForRate`), and the 32 output bytes are read
  from the words (`squeeze_fast_eq` against `squeeze32`).
* `cshake256Fast_eq`: for all customizations and inputs, `cshake256Fast` is
  `cshake256Bytes`.  `absorbPadded_fast_eq`: for every byte list,
  `absorbPaddedFast` is `absorbPadded`.

Both equalities are attached with `@[csimp]`, so every compiled caller of
`cshake256Bytes` or `absorbPadded` (the KMAC, the hash-equality atom, the
world root, the Store codec, ...) runs the fast code.  A `@[csimp]` lemma is a
proved rewrite of the compiler's input — no `@[implemented_by]`, no
`@[extern]`, no native code is trusted.  The remaining trust is the one every
compiled Lean definition already carries: the Lean compiler and runtime
implement `UInt64`/`ByteArray` primitives as their Lean definitions say.

`Sp800185Cshake256Core` imports this module and the spec; import Core.
-/

import Theory.Sp800185Cshake256Spec

namespace Minidregg.Compiler.Sp800185Cshake256.Fast
open Minidregg.Compiler.Sp800185Cshake256

set_option autoImplicit false
set_option linter.unusedSimpArgs false

/-! ## Word helpers -/

/-- Rotate a word left by `r` bits (`r` taken mod 64). -/
@[inline] def rotl (x : UInt64) (r : Nat) : UInt64 :=
  let n := r % 64
  if n = 0 then x
  else (x <<< UInt64.ofNat n) ||| (x >>> UInt64.ofNat (64 - n))

theorem rotl_toBitVec (x : UInt64) (r : Nat) :
    (rotl x r).toBitVec = x.toBitVec.rotateLeft r := by
  simp only [rotl, BitVec.rotateLeft_def]
  by_cases h : r % 64 = 0
  · simp [h, BitVec.ushiftRight_eq_zero]
  · simp [h, UInt64.toBitVec_or, UInt64.toBitVec_shiftLeft,
      UInt64.toBitVec_shiftRight]
    have hlt : r % 64 < 64 := Nat.mod_lt _ (by decide)
    have hrange : 64 - r % 64 < 64 := by omega
    rw [Nat.mod_eq_of_lt hrange]

/-- Rotate left by a constant: `rotlK x k (64 - k)`.  Callers pass both shift
amounts as `UInt64` literals, so the compiled round is shifts and ORs on
constants, with no branch and no run-time `Nat` arithmetic. -/
@[inline] def rotlK (x : UInt64) (k j : UInt64) : UInt64 := (x <<< k) ||| (x >>> j)

theorem rotlK_toBitVec (x : UInt64) (k j : Nat) (hk : 0 < k) (hk64 : k < 64) (hj : k + j = 64) :
    (rotlK x (UInt64.ofNat k) (UInt64.ofNat j)).toBitVec = x.toBitVec.rotateLeft k := by
  have hr := rotl_toBitVec x k
  have hkm : k % 64 = k := Nat.mod_eq_of_lt hk64
  have hne : k % 64 ≠ 0 := by omega
  have hk0 : k ≠ 0 := by omega
  simp only [rotl, hne, if_false, hkm, hk0] at hr
  rw [← hr]
  have hjk : j = 64 - k := by omega
  subst hjk
  rfl

theorem bv_rotateLeft_zero (x : BitVec 64) : x.rotateLeft 0 = x := by
  have hr := rotl_toBitVec (UInt64.ofBitVec x) 0
  simp only [rotl, Nat.zero_mod, if_true, UInt64.toBitVec_ofBitVec] at hr
  exact hr.symm

/-- Byte `j` of `b`, or zero past the end. -/
@[inline] def byteOr0 (b : ByteArray) (j : Nat) : UInt8 :=
  if h : j < b.size then b[j]'h else 0

/-- Byte `j` of `b` as a word, or zero past the end. -/
@[inline] def byteAt (b : ByteArray) (j : Nat) : UInt64 := (byteOr0 b j).toUInt64


/-! ### Rotations by each constant offset -/

theorem rotlK_1 (x : UInt64) : (rotlK x 1 63).toBitVec = x.toBitVec.rotateLeft 1 :=
  rotlK_toBitVec x 1 63 (by decide) (by decide) (by decide)
theorem rotlK_2 (x : UInt64) : (rotlK x 2 62).toBitVec = x.toBitVec.rotateLeft 2 :=
  rotlK_toBitVec x 2 62 (by decide) (by decide) (by decide)
theorem rotlK_3 (x : UInt64) : (rotlK x 3 61).toBitVec = x.toBitVec.rotateLeft 3 :=
  rotlK_toBitVec x 3 61 (by decide) (by decide) (by decide)
theorem rotlK_6 (x : UInt64) : (rotlK x 6 58).toBitVec = x.toBitVec.rotateLeft 6 :=
  rotlK_toBitVec x 6 58 (by decide) (by decide) (by decide)
theorem rotlK_8 (x : UInt64) : (rotlK x 8 56).toBitVec = x.toBitVec.rotateLeft 8 :=
  rotlK_toBitVec x 8 56 (by decide) (by decide) (by decide)
theorem rotlK_10 (x : UInt64) : (rotlK x 10 54).toBitVec = x.toBitVec.rotateLeft 10 :=
  rotlK_toBitVec x 10 54 (by decide) (by decide) (by decide)
theorem rotlK_14 (x : UInt64) : (rotlK x 14 50).toBitVec = x.toBitVec.rotateLeft 14 :=
  rotlK_toBitVec x 14 50 (by decide) (by decide) (by decide)
theorem rotlK_15 (x : UInt64) : (rotlK x 15 49).toBitVec = x.toBitVec.rotateLeft 15 :=
  rotlK_toBitVec x 15 49 (by decide) (by decide) (by decide)
theorem rotlK_18 (x : UInt64) : (rotlK x 18 46).toBitVec = x.toBitVec.rotateLeft 18 :=
  rotlK_toBitVec x 18 46 (by decide) (by decide) (by decide)
theorem rotlK_20 (x : UInt64) : (rotlK x 20 44).toBitVec = x.toBitVec.rotateLeft 20 :=
  rotlK_toBitVec x 20 44 (by decide) (by decide) (by decide)
theorem rotlK_21 (x : UInt64) : (rotlK x 21 43).toBitVec = x.toBitVec.rotateLeft 21 :=
  rotlK_toBitVec x 21 43 (by decide) (by decide) (by decide)
theorem rotlK_25 (x : UInt64) : (rotlK x 25 39).toBitVec = x.toBitVec.rotateLeft 25 :=
  rotlK_toBitVec x 25 39 (by decide) (by decide) (by decide)
theorem rotlK_27 (x : UInt64) : (rotlK x 27 37).toBitVec = x.toBitVec.rotateLeft 27 :=
  rotlK_toBitVec x 27 37 (by decide) (by decide) (by decide)
theorem rotlK_28 (x : UInt64) : (rotlK x 28 36).toBitVec = x.toBitVec.rotateLeft 28 :=
  rotlK_toBitVec x 28 36 (by decide) (by decide) (by decide)
theorem rotlK_36 (x : UInt64) : (rotlK x 36 28).toBitVec = x.toBitVec.rotateLeft 36 :=
  rotlK_toBitVec x 36 28 (by decide) (by decide) (by decide)
theorem rotlK_39 (x : UInt64) : (rotlK x 39 25).toBitVec = x.toBitVec.rotateLeft 39 :=
  rotlK_toBitVec x 39 25 (by decide) (by decide) (by decide)
theorem rotlK_41 (x : UInt64) : (rotlK x 41 23).toBitVec = x.toBitVec.rotateLeft 41 :=
  rotlK_toBitVec x 41 23 (by decide) (by decide) (by decide)
theorem rotlK_43 (x : UInt64) : (rotlK x 43 21).toBitVec = x.toBitVec.rotateLeft 43 :=
  rotlK_toBitVec x 43 21 (by decide) (by decide) (by decide)
theorem rotlK_44 (x : UInt64) : (rotlK x 44 20).toBitVec = x.toBitVec.rotateLeft 44 :=
  rotlK_toBitVec x 44 20 (by decide) (by decide) (by decide)
theorem rotlK_45 (x : UInt64) : (rotlK x 45 19).toBitVec = x.toBitVec.rotateLeft 45 :=
  rotlK_toBitVec x 45 19 (by decide) (by decide) (by decide)
theorem rotlK_55 (x : UInt64) : (rotlK x 55 9).toBitVec = x.toBitVec.rotateLeft 55 :=
  rotlK_toBitVec x 55 9 (by decide) (by decide) (by decide)
theorem rotlK_56 (x : UInt64) : (rotlK x 56 8).toBitVec = x.toBitVec.rotateLeft 56 :=
  rotlK_toBitVec x 56 8 (by decide) (by decide) (by decide)
theorem rotlK_61 (x : UInt64) : (rotlK x 61 3).toBitVec = x.toBitVec.rotateLeft 61 :=
  rotlK_toBitVec x 61 3 (by decide) (by decide) (by decide)
theorem rotlK_62 (x : UInt64) : (rotlK x 62 2).toBitVec = x.toBitVec.rotateLeft 62 :=
  rotlK_toBitVec x 62 2 (by decide) (by decide) (by decide)
/-! ## The word state and one round -/

/-- The Keccak state as twenty-five machine words, unboxed in one object.
Field `a(x+5y)` is lane `(x, y)`. -/
structure KState where
  a0 : UInt64
  a1 : UInt64
  a2 : UInt64
  a3 : UInt64
  a4 : UInt64
  a5 : UInt64
  a6 : UInt64
  a7 : UInt64
  a8 : UInt64
  a9 : UInt64
  a10 : UInt64
  a11 : UInt64
  a12 : UInt64
  a13 : UInt64
  a14 : UInt64
  a15 : UInt64
  a16 : UInt64
  a17 : UInt64
  a18 : UInt64
  a19 : UInt64
  a20 : UInt64
  a21 : UInt64
  a22 : UInt64
  a23 : UInt64
  a24 : UInt64

/-- The spec's lane array of a word state (lane `x + 5*y` is field `a(x+5y)`). -/
def KState.toState (s : KState) : State :=
  #[s.a0.toBitVec, s.a1.toBitVec, s.a2.toBitVec, s.a3.toBitVec, s.a4.toBitVec, s.a5.toBitVec, s.a6.toBitVec, s.a7.toBitVec, s.a8.toBitVec, s.a9.toBitVec, s.a10.toBitVec, s.a11.toBitVec, s.a12.toBitVec, s.a13.toBitVec, s.a14.toBitVec, s.a15.toBitVec, s.a16.toBitVec, s.a17.toBitVec, s.a18.toBitVec, s.a19.toBitVec, s.a20.toBitVec, s.a21.toBitVec, s.a22.toBitVec, s.a23.toBitVec, s.a24.toBitVec]

/-- The all-zero state. -/
def zeroS : KState := ⟨0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0⟩

/-- Theta on words, in `thetaCached`'s shape: five column parities, five deltas. -/
@[inline] def thetaS (s : KState) : KState :=
  let c0 := (0 : UInt64) ^^^ s.a0 ^^^ s.a5 ^^^ s.a10 ^^^ s.a15 ^^^ s.a20
  let c1 := (0 : UInt64) ^^^ s.a1 ^^^ s.a6 ^^^ s.a11 ^^^ s.a16 ^^^ s.a21
  let c2 := (0 : UInt64) ^^^ s.a2 ^^^ s.a7 ^^^ s.a12 ^^^ s.a17 ^^^ s.a22
  let c3 := (0 : UInt64) ^^^ s.a3 ^^^ s.a8 ^^^ s.a13 ^^^ s.a18 ^^^ s.a23
  let c4 := (0 : UInt64) ^^^ s.a4 ^^^ s.a9 ^^^ s.a14 ^^^ s.a19 ^^^ s.a24
  let d0 := c4 ^^^ rotlK c1 1 63
  let d1 := c0 ^^^ rotlK c2 1 63
  let d2 := c1 ^^^ rotlK c3 1 63
  let d3 := c2 ^^^ rotlK c4 1 63
  let d4 := c3 ^^^ rotlK c0 1 63
  ⟨s.a0 ^^^ d0, s.a1 ^^^ d1, s.a2 ^^^ d2, s.a3 ^^^ d3, s.a4 ^^^ d4, s.a5 ^^^ d0, s.a6 ^^^ d1, s.a7 ^^^ d2, s.a8 ^^^ d3, s.a9 ^^^ d4, s.a10 ^^^ d0, s.a11 ^^^ d1, s.a12 ^^^ d2, s.a13 ^^^ d3, s.a14 ^^^ d4, s.a15 ^^^ d0, s.a16 ^^^ d1, s.a17 ^^^ d2, s.a18 ^^^ d3, s.a19 ^^^ d4, s.a20 ^^^ d0, s.a21 ^^^ d1, s.a22 ^^^ d2, s.a23 ^^^ d3, s.a24 ^^^ d4⟩

/-- Fused rho and pi: target lane `t` takes the rotated source lane. -/
@[inline] def rhoPiS (s : KState) : KState :=
  ⟨s.a0, rotlK s.a6 44 20, rotlK s.a12 43 21, rotlK s.a18 21 43, rotlK s.a24 14 50, rotlK s.a3 28 36, rotlK s.a9 20 44, rotlK s.a10 3 61, rotlK s.a16 45 19, rotlK s.a22 61 3, rotlK s.a1 1 63, rotlK s.a7 6 58, rotlK s.a13 25 39, rotlK s.a19 8 56, rotlK s.a20 18 46, rotlK s.a4 27 37, rotlK s.a5 36 28, rotlK s.a11 10 54, rotlK s.a17 15 49, rotlK s.a23 56 8, rotlK s.a2 62 2, rotlK s.a8 55 9, rotlK s.a14 39 25, rotlK s.a15 41 23, rotlK s.a21 2 62⟩

/-- Chi on words. -/
@[inline] def chiS (s : KState) : KState :=
  ⟨s.a0 ^^^ ((~~~s.a1) &&& s.a2),
   s.a1 ^^^ ((~~~s.a2) &&& s.a3),
   s.a2 ^^^ ((~~~s.a3) &&& s.a4),
   s.a3 ^^^ ((~~~s.a4) &&& s.a0),
   s.a4 ^^^ ((~~~s.a0) &&& s.a1),
   s.a5 ^^^ ((~~~s.a6) &&& s.a7),
   s.a6 ^^^ ((~~~s.a7) &&& s.a8),
   s.a7 ^^^ ((~~~s.a8) &&& s.a9),
   s.a8 ^^^ ((~~~s.a9) &&& s.a5),
   s.a9 ^^^ ((~~~s.a5) &&& s.a6),
   s.a10 ^^^ ((~~~s.a11) &&& s.a12),
   s.a11 ^^^ ((~~~s.a12) &&& s.a13),
   s.a12 ^^^ ((~~~s.a13) &&& s.a14),
   s.a13 ^^^ ((~~~s.a14) &&& s.a10),
   s.a14 ^^^ ((~~~s.a10) &&& s.a11),
   s.a15 ^^^ ((~~~s.a16) &&& s.a17),
   s.a16 ^^^ ((~~~s.a17) &&& s.a18),
   s.a17 ^^^ ((~~~s.a18) &&& s.a19),
   s.a18 ^^^ ((~~~s.a19) &&& s.a15),
   s.a19 ^^^ ((~~~s.a15) &&& s.a16),
   s.a20 ^^^ ((~~~s.a21) &&& s.a22),
   s.a21 ^^^ ((~~~s.a22) &&& s.a23),
   s.a22 ^^^ ((~~~s.a23) &&& s.a24),
   s.a23 ^^^ ((~~~s.a24) &&& s.a20),
   s.a24 ^^^ ((~~~s.a20) &&& s.a21)⟩

/-- Iota: the round constant enters lane `(0,0)`. -/
@[inline] def iotaS (s : KState) (c : UInt64) : KState :=
  { s with a0 := s.a0 ^^^ c }

/-- Little-endian lane read at byte offset `p`; bytes past the end read 0. -/
@[inline] def laneAt (b : ByteArray) (p : Nat) : UInt64 :=
  (0 : UInt64) ^^^ (byteAt b (p + 0) <<< 0) ^^^ (byteAt b (p + 1) <<< 8) ^^^ (byteAt b (p + 2) <<< 16) ^^^ (byteAt b (p + 3) <<< 24) ^^^ (byteAt b (p + 4) <<< 32) ^^^ (byteAt b (p + 5) <<< 40) ^^^ (byteAt b (p + 6) <<< 48) ^^^ (byteAt b (p + 7) <<< 56)

/-- XOR one rate block of `b`, starting at byte `off`, into the seventeen rate lanes. -/
@[inline] def xorBlockS (s : KState) (b : ByteArray) (off : Nat) : KState :=
  ⟨s.a0 ^^^ laneAt b (off + 0), s.a1 ^^^ laneAt b (off + 8), s.a2 ^^^ laneAt b (off + 16), s.a3 ^^^ laneAt b (off + 24), s.a4 ^^^ laneAt b (off + 32), s.a5 ^^^ laneAt b (off + 40), s.a6 ^^^ laneAt b (off + 48), s.a7 ^^^ laneAt b (off + 56), s.a8 ^^^ laneAt b (off + 64), s.a9 ^^^ laneAt b (off + 72), s.a10 ^^^ laneAt b (off + 80), s.a11 ^^^ laneAt b (off + 88), s.a12 ^^^ laneAt b (off + 96), s.a13 ^^^ laneAt b (off + 104), s.a14 ^^^ laneAt b (off + 112), s.a15 ^^^ laneAt b (off + 120), s.a16 ^^^ laneAt b (off + 128), s.a17, s.a18, s.a19, s.a20, s.a21, s.a22, s.a23, s.a24⟩


/-- The spec's rho/pi target index for a source lane. -/
def rpTarget (source : Nat) : Nat :=
  source / 5 + 5 * ((2 * (source % 5) + 3 * (source / 5)) % 5)

/-- The spec's rho/pi value for a source lane. -/
def rpValue (st : State) (source : Nat) : Lane :=
  (lane st (source % 5) (source / 5)).rotateLeft (rotationOffset (source % 5) (source / 5))

/-! ### Per-lane access lemmas (all definitional) -/

theorem toState_size (s : KState) : s.toState.size = 25 := rfl

theorem toState_getElem_0 (s : KState) (h : 0 < s.toState.size) :
    s.toState[0] = s.a0.toBitVec := rfl
theorem toState_getElem_1 (s : KState) (h : 1 < s.toState.size) :
    s.toState[1] = s.a1.toBitVec := rfl
theorem toState_getElem_2 (s : KState) (h : 2 < s.toState.size) :
    s.toState[2] = s.a2.toBitVec := rfl
theorem toState_getElem_3 (s : KState) (h : 3 < s.toState.size) :
    s.toState[3] = s.a3.toBitVec := rfl
theorem toState_getElem_4 (s : KState) (h : 4 < s.toState.size) :
    s.toState[4] = s.a4.toBitVec := rfl
theorem toState_getElem_5 (s : KState) (h : 5 < s.toState.size) :
    s.toState[5] = s.a5.toBitVec := rfl
theorem toState_getElem_6 (s : KState) (h : 6 < s.toState.size) :
    s.toState[6] = s.a6.toBitVec := rfl
theorem toState_getElem_7 (s : KState) (h : 7 < s.toState.size) :
    s.toState[7] = s.a7.toBitVec := rfl
theorem toState_getElem_8 (s : KState) (h : 8 < s.toState.size) :
    s.toState[8] = s.a8.toBitVec := rfl
theorem toState_getElem_9 (s : KState) (h : 9 < s.toState.size) :
    s.toState[9] = s.a9.toBitVec := rfl
theorem toState_getElem_10 (s : KState) (h : 10 < s.toState.size) :
    s.toState[10] = s.a10.toBitVec := rfl
theorem toState_getElem_11 (s : KState) (h : 11 < s.toState.size) :
    s.toState[11] = s.a11.toBitVec := rfl
theorem toState_getElem_12 (s : KState) (h : 12 < s.toState.size) :
    s.toState[12] = s.a12.toBitVec := rfl
theorem toState_getElem_13 (s : KState) (h : 13 < s.toState.size) :
    s.toState[13] = s.a13.toBitVec := rfl
theorem toState_getElem_14 (s : KState) (h : 14 < s.toState.size) :
    s.toState[14] = s.a14.toBitVec := rfl
theorem toState_getElem_15 (s : KState) (h : 15 < s.toState.size) :
    s.toState[15] = s.a15.toBitVec := rfl
theorem toState_getElem_16 (s : KState) (h : 16 < s.toState.size) :
    s.toState[16] = s.a16.toBitVec := rfl
theorem toState_getElem_17 (s : KState) (h : 17 < s.toState.size) :
    s.toState[17] = s.a17.toBitVec := rfl
theorem toState_getElem_18 (s : KState) (h : 18 < s.toState.size) :
    s.toState[18] = s.a18.toBitVec := rfl
theorem toState_getElem_19 (s : KState) (h : 19 < s.toState.size) :
    s.toState[19] = s.a19.toBitVec := rfl
theorem toState_getElem_20 (s : KState) (h : 20 < s.toState.size) :
    s.toState[20] = s.a20.toBitVec := rfl
theorem toState_getElem_21 (s : KState) (h : 21 < s.toState.size) :
    s.toState[21] = s.a21.toBitVec := rfl
theorem toState_getElem_22 (s : KState) (h : 22 < s.toState.size) :
    s.toState[22] = s.a22.toBitVec := rfl
theorem toState_getElem_23 (s : KState) (h : 23 < s.toState.size) :
    s.toState[23] = s.a23.toBitVec := rfl
theorem toState_getElem_24 (s : KState) (h : 24 < s.toState.size) :
    s.toState[24] = s.a24.toBitVec := rfl
theorem toState_getD_0 (s : KState) : s.toState.getD 0 zeroLane = s.a0.toBitVec := rfl
theorem toState_getD_1 (s : KState) : s.toState.getD 1 zeroLane = s.a1.toBitVec := rfl
theorem toState_getD_2 (s : KState) : s.toState.getD 2 zeroLane = s.a2.toBitVec := rfl
theorem toState_getD_3 (s : KState) : s.toState.getD 3 zeroLane = s.a3.toBitVec := rfl
theorem toState_getD_4 (s : KState) : s.toState.getD 4 zeroLane = s.a4.toBitVec := rfl
theorem toState_getD_5 (s : KState) : s.toState.getD 5 zeroLane = s.a5.toBitVec := rfl
theorem toState_getD_6 (s : KState) : s.toState.getD 6 zeroLane = s.a6.toBitVec := rfl
theorem toState_getD_7 (s : KState) : s.toState.getD 7 zeroLane = s.a7.toBitVec := rfl
theorem toState_getD_8 (s : KState) : s.toState.getD 8 zeroLane = s.a8.toBitVec := rfl
theorem toState_getD_9 (s : KState) : s.toState.getD 9 zeroLane = s.a9.toBitVec := rfl
theorem toState_getD_10 (s : KState) : s.toState.getD 10 zeroLane = s.a10.toBitVec := rfl
theorem toState_getD_11 (s : KState) : s.toState.getD 11 zeroLane = s.a11.toBitVec := rfl
theorem toState_getD_12 (s : KState) : s.toState.getD 12 zeroLane = s.a12.toBitVec := rfl
theorem toState_getD_13 (s : KState) : s.toState.getD 13 zeroLane = s.a13.toBitVec := rfl
theorem toState_getD_14 (s : KState) : s.toState.getD 14 zeroLane = s.a14.toBitVec := rfl
theorem toState_getD_15 (s : KState) : s.toState.getD 15 zeroLane = s.a15.toBitVec := rfl
theorem toState_getD_16 (s : KState) : s.toState.getD 16 zeroLane = s.a16.toBitVec := rfl
theorem toState_getD_17 (s : KState) : s.toState.getD 17 zeroLane = s.a17.toBitVec := rfl
theorem toState_getD_18 (s : KState) : s.toState.getD 18 zeroLane = s.a18.toBitVec := rfl
theorem toState_getD_19 (s : KState) : s.toState.getD 19 zeroLane = s.a19.toBitVec := rfl
theorem toState_getD_20 (s : KState) : s.toState.getD 20 zeroLane = s.a20.toBitVec := rfl
theorem toState_getD_21 (s : KState) : s.toState.getD 21 zeroLane = s.a21.toBitVec := rfl
theorem toState_getD_22 (s : KState) : s.toState.getD 22 zeroLane = s.a22.toBitVec := rfl
theorem toState_getD_23 (s : KState) : s.toState.getD 23 zeroLane = s.a23.toBitVec := rfl
theorem toState_getD_24 (s : KState) : s.toState.getD 24 zeroLane = s.a24.toBitVec := rfl
theorem lane_toState_0_0 (s : KState) : lane s.toState 0 0 = s.a0.toBitVec := rfl
theorem lane_toState_1_0 (s : KState) : lane s.toState 1 0 = s.a1.toBitVec := rfl
theorem lane_toState_2_0 (s : KState) : lane s.toState 2 0 = s.a2.toBitVec := rfl
theorem lane_toState_3_0 (s : KState) : lane s.toState 3 0 = s.a3.toBitVec := rfl
theorem lane_toState_4_0 (s : KState) : lane s.toState 4 0 = s.a4.toBitVec := rfl
theorem lane_toState_5_0 (s : KState) : lane s.toState 5 0 = s.a0.toBitVec := rfl
theorem lane_toState_6_0 (s : KState) : lane s.toState 6 0 = s.a1.toBitVec := rfl
theorem lane_toState_0_1 (s : KState) : lane s.toState 0 1 = s.a5.toBitVec := rfl
theorem lane_toState_1_1 (s : KState) : lane s.toState 1 1 = s.a6.toBitVec := rfl
theorem lane_toState_2_1 (s : KState) : lane s.toState 2 1 = s.a7.toBitVec := rfl
theorem lane_toState_3_1 (s : KState) : lane s.toState 3 1 = s.a8.toBitVec := rfl
theorem lane_toState_4_1 (s : KState) : lane s.toState 4 1 = s.a9.toBitVec := rfl
theorem lane_toState_5_1 (s : KState) : lane s.toState 5 1 = s.a5.toBitVec := rfl
theorem lane_toState_6_1 (s : KState) : lane s.toState 6 1 = s.a6.toBitVec := rfl
theorem lane_toState_0_2 (s : KState) : lane s.toState 0 2 = s.a10.toBitVec := rfl
theorem lane_toState_1_2 (s : KState) : lane s.toState 1 2 = s.a11.toBitVec := rfl
theorem lane_toState_2_2 (s : KState) : lane s.toState 2 2 = s.a12.toBitVec := rfl
theorem lane_toState_3_2 (s : KState) : lane s.toState 3 2 = s.a13.toBitVec := rfl
theorem lane_toState_4_2 (s : KState) : lane s.toState 4 2 = s.a14.toBitVec := rfl
theorem lane_toState_5_2 (s : KState) : lane s.toState 5 2 = s.a10.toBitVec := rfl
theorem lane_toState_6_2 (s : KState) : lane s.toState 6 2 = s.a11.toBitVec := rfl
theorem lane_toState_0_3 (s : KState) : lane s.toState 0 3 = s.a15.toBitVec := rfl
theorem lane_toState_1_3 (s : KState) : lane s.toState 1 3 = s.a16.toBitVec := rfl
theorem lane_toState_2_3 (s : KState) : lane s.toState 2 3 = s.a17.toBitVec := rfl
theorem lane_toState_3_3 (s : KState) : lane s.toState 3 3 = s.a18.toBitVec := rfl
theorem lane_toState_4_3 (s : KState) : lane s.toState 4 3 = s.a19.toBitVec := rfl
theorem lane_toState_5_3 (s : KState) : lane s.toState 5 3 = s.a15.toBitVec := rfl
theorem lane_toState_6_3 (s : KState) : lane s.toState 6 3 = s.a16.toBitVec := rfl
theorem lane_toState_0_4 (s : KState) : lane s.toState 0 4 = s.a20.toBitVec := rfl
theorem lane_toState_1_4 (s : KState) : lane s.toState 1 4 = s.a21.toBitVec := rfl
theorem lane_toState_2_4 (s : KState) : lane s.toState 2 4 = s.a22.toBitVec := rfl
theorem lane_toState_3_4 (s : KState) : lane s.toState 3 4 = s.a23.toBitVec := rfl
theorem lane_toState_4_4 (s : KState) : lane s.toState 4 4 = s.a24.toBitVec := rfl
theorem lane_toState_5_4 (s : KState) : lane s.toState 5 4 = s.a20.toBitVec := rfl
theorem lane_toState_6_4 (s : KState) : lane s.toState 6 4 = s.a21.toBitVec := rfl
theorem rotationOffset_0_0 : rotationOffset 0 0 = 0 := rfl
theorem rotationOffset_1_0 : rotationOffset 1 0 = 1 := rfl
theorem rotationOffset_2_0 : rotationOffset 2 0 = 62 := rfl
theorem rotationOffset_3_0 : rotationOffset 3 0 = 28 := rfl
theorem rotationOffset_4_0 : rotationOffset 4 0 = 27 := rfl
theorem rotationOffset_0_1 : rotationOffset 0 1 = 36 := rfl
theorem rotationOffset_1_1 : rotationOffset 1 1 = 44 := rfl
theorem rotationOffset_2_1 : rotationOffset 2 1 = 6 := rfl
theorem rotationOffset_3_1 : rotationOffset 3 1 = 55 := rfl
theorem rotationOffset_4_1 : rotationOffset 4 1 = 20 := rfl
theorem rotationOffset_0_2 : rotationOffset 0 2 = 3 := rfl
theorem rotationOffset_1_2 : rotationOffset 1 2 = 10 := rfl
theorem rotationOffset_2_2 : rotationOffset 2 2 = 43 := rfl
theorem rotationOffset_3_2 : rotationOffset 3 2 = 25 := rfl
theorem rotationOffset_4_2 : rotationOffset 4 2 = 39 := rfl
theorem rotationOffset_0_3 : rotationOffset 0 3 = 41 := rfl
theorem rotationOffset_1_3 : rotationOffset 1 3 = 45 := rfl
theorem rotationOffset_2_3 : rotationOffset 2 3 = 15 := rfl
theorem rotationOffset_3_3 : rotationOffset 3 3 = 21 := rfl
theorem rotationOffset_4_3 : rotationOffset 4 3 = 8 := rfl
theorem rotationOffset_0_4 : rotationOffset 0 4 = 18 := rfl
theorem rotationOffset_1_4 : rotationOffset 1 4 = 2 := rfl
theorem rotationOffset_2_4 : rotationOffset 2 4 = 61 := rfl
theorem rotationOffset_3_4 : rotationOffset 3 4 = 56 := rfl
theorem rotationOffset_4_4 : rotationOffset 4 4 = 14 := rfl
/-- The rho/pi source of each target lane (the inverse of `rpTarget`). -/
def rpSource : Nat → Nat
  | 0 => 0
  | 1 => 6
  | 2 => 12
  | 3 => 18
  | 4 => 24
  | 5 => 3
  | 6 => 9
  | 7 => 10
  | 8 => 16
  | 9 => 22
  | 10 => 1
  | 11 => 7
  | 12 => 13
  | 13 => 19
  | 14 => 20
  | 15 => 4
  | 16 => 5
  | 17 => 11
  | 18 => 17
  | 19 => 23
  | 20 => 2
  | 21 => 8
  | 22 => 14
  | 23 => 15
  | 24 => 21
  | _ => 0

theorem rpSource_0 : rpSource 0 = 0 := rfl
theorem rpSource_1 : rpSource 1 = 6 := rfl
theorem rpSource_2 : rpSource 2 = 12 := rfl
theorem rpSource_3 : rpSource 3 = 18 := rfl
theorem rpSource_4 : rpSource 4 = 24 := rfl
theorem rpSource_5 : rpSource 5 = 3 := rfl
theorem rpSource_6 : rpSource 6 = 9 := rfl
theorem rpSource_7 : rpSource 7 = 10 := rfl
theorem rpSource_8 : rpSource 8 = 16 := rfl
theorem rpSource_9 : rpSource 9 = 22 := rfl
theorem rpSource_10 : rpSource 10 = 1 := rfl
theorem rpSource_11 : rpSource 11 = 7 := rfl
theorem rpSource_12 : rpSource 12 = 13 := rfl
theorem rpSource_13 : rpSource 13 = 19 := rfl
theorem rpSource_14 : rpSource 14 = 20 := rfl
theorem rpSource_15 : rpSource 15 = 4 := rfl
theorem rpSource_16 : rpSource 16 = 5 := rfl
theorem rpSource_17 : rpSource 17 = 11 := rfl
theorem rpSource_18 : rpSource 18 = 17 := rfl
theorem rpSource_19 : rpSource 19 = 23 := rfl
theorem rpSource_20 : rpSource 20 = 2 := rfl
theorem rpSource_21 : rpSource 21 = 8 := rfl
theorem rpSource_22 : rpSource 22 = 14 := rfl
theorem rpSource_23 : rpSource 23 = 15 := rfl
theorem rpSource_24 : rpSource 24 = 21 := rfl

/-- The last rho/pi write to each target comes from `rpSource`. -/
theorem rhoPi_find (t : Nat) (ht : t < 25) :
    (List.range 25).reverse.find? (fun s => rpTarget s == t) = some (rpSource t) := by
  revert t
  decide

/-! ### The permutation, stage by stage -/

theorem xorColumn_five (st : State) (x : Nat) :
    xorColumn st x = zeroLane ^^^ lane st x 0 ^^^ lane st x 1 ^^^ lane st x 2 ^^^
      lane st x 3 ^^^ lane st x 4 := rfl

theorem u64_zero_toBitVec : (0 : UInt64).toBitVec = zeroLane := rfl

/-- Lanewise equality against the twenty-five-lane literal. -/
theorem toState_ext (s : KState) (st : State) (hsize : st.size = 25)
    (h0 : s.toState[0]'(by rw [toState_size]; decide) = st[0]'(by rw [hsize]; decide))
    (h1 : s.toState[1]'(by rw [toState_size]; decide) = st[1]'(by rw [hsize]; decide))
    (h2 : s.toState[2]'(by rw [toState_size]; decide) = st[2]'(by rw [hsize]; decide))
    (h3 : s.toState[3]'(by rw [toState_size]; decide) = st[3]'(by rw [hsize]; decide))
    (h4 : s.toState[4]'(by rw [toState_size]; decide) = st[4]'(by rw [hsize]; decide))
    (h5 : s.toState[5]'(by rw [toState_size]; decide) = st[5]'(by rw [hsize]; decide))
    (h6 : s.toState[6]'(by rw [toState_size]; decide) = st[6]'(by rw [hsize]; decide))
    (h7 : s.toState[7]'(by rw [toState_size]; decide) = st[7]'(by rw [hsize]; decide))
    (h8 : s.toState[8]'(by rw [toState_size]; decide) = st[8]'(by rw [hsize]; decide))
    (h9 : s.toState[9]'(by rw [toState_size]; decide) = st[9]'(by rw [hsize]; decide))
    (h10 : s.toState[10]'(by rw [toState_size]; decide) = st[10]'(by rw [hsize]; decide))
    (h11 : s.toState[11]'(by rw [toState_size]; decide) = st[11]'(by rw [hsize]; decide))
    (h12 : s.toState[12]'(by rw [toState_size]; decide) = st[12]'(by rw [hsize]; decide))
    (h13 : s.toState[13]'(by rw [toState_size]; decide) = st[13]'(by rw [hsize]; decide))
    (h14 : s.toState[14]'(by rw [toState_size]; decide) = st[14]'(by rw [hsize]; decide))
    (h15 : s.toState[15]'(by rw [toState_size]; decide) = st[15]'(by rw [hsize]; decide))
    (h16 : s.toState[16]'(by rw [toState_size]; decide) = st[16]'(by rw [hsize]; decide))
    (h17 : s.toState[17]'(by rw [toState_size]; decide) = st[17]'(by rw [hsize]; decide))
    (h18 : s.toState[18]'(by rw [toState_size]; decide) = st[18]'(by rw [hsize]; decide))
    (h19 : s.toState[19]'(by rw [toState_size]; decide) = st[19]'(by rw [hsize]; decide))
    (h20 : s.toState[20]'(by rw [toState_size]; decide) = st[20]'(by rw [hsize]; decide))
    (h21 : s.toState[21]'(by rw [toState_size]; decide) = st[21]'(by rw [hsize]; decide))
    (h22 : s.toState[22]'(by rw [toState_size]; decide) = st[22]'(by rw [hsize]; decide))
    (h23 : s.toState[23]'(by rw [toState_size]; decide) = st[23]'(by rw [hsize]; decide))
    (h24 : s.toState[24]'(by rw [toState_size]; decide) = st[24]'(by rw [hsize]; decide))
    : s.toState = st := by
  apply Array.ext
  · rw [toState_size, hsize]
  · intro i hi _
    match i, hi with
    | 0, _ => exact h0
    | 1, _ => exact h1
    | 2, _ => exact h2
    | 3, _ => exact h3
    | 4, _ => exact h4
    | 5, _ => exact h5
    | 6, _ => exact h6
    | 7, _ => exact h7
    | 8, _ => exact h8
    | 9, _ => exact h9
    | 10, _ => exact h10
    | 11, _ => exact h11
    | 12, _ => exact h12
    | 13, _ => exact h13
    | 14, _ => exact h14
    | 15, _ => exact h15
    | 16, _ => exact h16
    | 17, _ => exact h17
    | 18, _ => exact h18
    | 19, _ => exact h19
    | 20, _ => exact h20
    | 21, _ => exact h21
    | 22, _ => exact h22
    | 23, _ => exact h23
    | 24, _ => exact h24
    | n + 25, h => exact absurd h (by rw [toState_size]; omega)

set_option maxHeartbeats 4000000 in
theorem thetaS_toState (s : KState) : (thetaS s).toState = thetaCached s.toState := by
  apply toState_ext _ _ (by simp [thetaCached]) <;>
    simp only [thetaCached, Array.getElem_ofFn, xorColumn_five, thetaS, toState_getElem_0, toState_getElem_1, toState_getElem_2, toState_getElem_3, toState_getElem_4, toState_getElem_5, toState_getElem_6, toState_getElem_7, toState_getElem_8, toState_getElem_9, toState_getElem_10, toState_getElem_11, toState_getElem_12, toState_getElem_13, toState_getElem_14, toState_getElem_15, toState_getElem_16, toState_getElem_17, toState_getElem_18, toState_getElem_19, toState_getElem_20, toState_getElem_21, toState_getElem_22, toState_getElem_23, toState_getElem_24,
      UInt64.toBitVec_xor, rotlK_1, rotlK_2, rotlK_3, rotlK_6, rotlK_8, rotlK_10, rotlK_14, rotlK_15, rotlK_18, rotlK_20, rotlK_21, rotlK_25, rotlK_27, rotlK_28, rotlK_36, rotlK_39, rotlK_41, rotlK_43, rotlK_44, rotlK_45, rotlK_55, rotlK_56, rotlK_61, rotlK_62, u64_zero_toBitVec, Nat.reduceMod, Nat.reduceDiv,
      Nat.reduceAdd, Nat.zero_mod, Nat.zero_div, lane_toState_0_0, lane_toState_1_0, lane_toState_2_0, lane_toState_3_0, lane_toState_4_0, lane_toState_5_0, lane_toState_6_0, lane_toState_0_1, lane_toState_1_1, lane_toState_2_1, lane_toState_3_1, lane_toState_4_1, lane_toState_5_1, lane_toState_6_1, lane_toState_0_2, lane_toState_1_2, lane_toState_2_2, lane_toState_3_2, lane_toState_4_2, lane_toState_5_2, lane_toState_6_2, lane_toState_0_3, lane_toState_1_3, lane_toState_2_3, lane_toState_3_3, lane_toState_4_3, lane_toState_5_3, lane_toState_6_3, lane_toState_0_4, lane_toState_1_4, lane_toState_2_4, lane_toState_3_4, lane_toState_4_4, lane_toState_5_4, lane_toState_6_4]

set_option maxHeartbeats 4000000 in
theorem chiS_toState (s : KState) : (chiS s).toState = chi s.toState := by
  apply toState_ext _ _ (by simp [chi]) <;>
    simp only [chi, Array.getElem_ofFn, chiS, toState_getElem_0, toState_getElem_1, toState_getElem_2, toState_getElem_3, toState_getElem_4, toState_getElem_5, toState_getElem_6, toState_getElem_7, toState_getElem_8, toState_getElem_9, toState_getElem_10, toState_getElem_11, toState_getElem_12, toState_getElem_13, toState_getElem_14, toState_getElem_15, toState_getElem_16, toState_getElem_17, toState_getElem_18, toState_getElem_19, toState_getElem_20, toState_getElem_21, toState_getElem_22, toState_getElem_23, toState_getElem_24,
      UInt64.toBitVec_xor, UInt64.toBitVec_and, UInt64.toBitVec_not, Nat.reduceMod,
      Nat.reduceDiv, Nat.reduceAdd, Nat.zero_mod, Nat.zero_div, lane_toState_0_0, lane_toState_1_0, lane_toState_2_0, lane_toState_3_0, lane_toState_4_0, lane_toState_5_0, lane_toState_6_0, lane_toState_0_1, lane_toState_1_1, lane_toState_2_1, lane_toState_3_1, lane_toState_4_1, lane_toState_5_1, lane_toState_6_1, lane_toState_0_2, lane_toState_1_2, lane_toState_2_2, lane_toState_3_2, lane_toState_4_2, lane_toState_5_2, lane_toState_6_2, lane_toState_0_3, lane_toState_1_3, lane_toState_2_3, lane_toState_3_3, lane_toState_4_3, lane_toState_5_3, lane_toState_6_3, lane_toState_0_4, lane_toState_1_4, lane_toState_2_4, lane_toState_3_4, lane_toState_4_4, lane_toState_5_4, lane_toState_6_4]

/-- A fold of in-bounds writes, read back at one index: the last write to that
index wins, else the initial array's entry. -/
theorem foldl_setIfInBounds_getElem? {α : Type} (g : Nat → Nat) (f : Nat → α)
    (l : List Nat) (a : Array α) (t : Nat) :
    (l.foldl (fun o s => o.setIfInBounds (g s) (f s)) a)[t]? =
      match l.reverse.find? (fun s => g s == t) with
      | some s => if t < a.size then some (f s) else none
      | none => a[t]? := by
  induction l generalizing a with
  | nil => simp
  | cons x xs ih =>
      rw [List.foldl_cons, ih, List.reverse_cons, List.find?_append]
      rw [Array.size_setIfInBounds]
      cases hfind : xs.reverse.find? (fun s => g s == t) with
      | some s => simp
      | none =>
          simp only [Option.none_or, List.find?_cons, List.find?_nil]
          rw [Array.getElem?_setIfInBounds]
          by_cases hgt : g x = t
          · subst hgt
            by_cases hlt : g x < a.size <;> simp [hlt]
          · have hb : (g x == t) = false := by simp [hgt]
            simp only [hb, hgt, if_false]

theorem rhoPi_eq_fold (st : State) :
    rhoPi st = (List.range 25).foldl
      (fun o s => o.setIfInBounds (rpTarget s) (rpValue st s)) zeroState := rfl

theorem zeroState_size : zeroState.size = 25 := rfl

theorem rhoPi_getElem? (st : State) (t : Nat) (ht : t < 25) :
    (rhoPi st)[t]? = some (rpValue st (rpSource t)) := by
  rw [rhoPi_eq_fold, foldl_setIfInBounds_getElem?, rhoPi_find t ht]
  simp [zeroState_size, ht]

theorem rhoPi_size (st : State) : (rhoPi st).size = 25 := by
  rw [rhoPi_eq_fold]
  generalize List.range 25 = l
  have : ∀ (a : State), (l.foldl (fun o s => o.setIfInBounds (rpTarget s) (rpValue st s)) a).size
      = a.size := by
    induction l with
    | nil => intro a; rfl
    | cons x xs ih => intro a; rw [List.foldl_cons, ih, Array.size_setIfInBounds]
  rw [this, zeroState_size]

theorem rhoPi_getElem (st : State) (t : Nat) (ht : t < 25) (h : t < (rhoPi st).size) :
    (rhoPi st)[t] = rpValue st (rpSource t) := by
  apply Option.some.inj
  rw [← Array.getElem?_eq_getElem h, rhoPi_getElem? st t ht]

set_option maxHeartbeats 4000000 in
theorem rhoPiS_toState (s : KState) : (rhoPiS s).toState = rhoPi s.toState := by
  apply toState_ext _ _ (rhoPi_size _) <;> rw [rhoPi_getElem _ _ (by decide)] <;>
    simp only [rpSource_0, rpSource_1, rpSource_2, rpSource_3, rpSource_4, rpSource_5, rpSource_6, rpSource_7, rpSource_8, rpSource_9, rpSource_10, rpSource_11, rpSource_12, rpSource_13, rpSource_14, rpSource_15, rpSource_16, rpSource_17, rpSource_18, rpSource_19, rpSource_20, rpSource_21, rpSource_22, rpSource_23, rpSource_24, rpValue, rhoPiS, toState_getElem_0, toState_getElem_1, toState_getElem_2, toState_getElem_3, toState_getElem_4, toState_getElem_5, toState_getElem_6, toState_getElem_7, toState_getElem_8, toState_getElem_9, toState_getElem_10, toState_getElem_11, toState_getElem_12, toState_getElem_13, toState_getElem_14, toState_getElem_15, toState_getElem_16, toState_getElem_17, toState_getElem_18, toState_getElem_19, toState_getElem_20, toState_getElem_21, toState_getElem_22, toState_getElem_23, toState_getElem_24, rotlK_1, rotlK_2, rotlK_3, rotlK_6, rotlK_8, rotlK_10, rotlK_14, rotlK_15, rotlK_18, rotlK_20, rotlK_21, rotlK_25, rotlK_27, rotlK_28, rotlK_36, rotlK_39, rotlK_41, rotlK_43, rotlK_44, rotlK_45, rotlK_55, rotlK_56, rotlK_61, rotlK_62, bv_rotateLeft_zero,
      Nat.reduceMod, Nat.reduceDiv, Nat.reduceAdd, Nat.zero_mod, Nat.zero_div,
      lane_toState_0_0, lane_toState_1_0, lane_toState_2_0, lane_toState_3_0, lane_toState_4_0, lane_toState_5_0, lane_toState_6_0, lane_toState_0_1, lane_toState_1_1, lane_toState_2_1, lane_toState_3_1, lane_toState_4_1, lane_toState_5_1, lane_toState_6_1, lane_toState_0_2, lane_toState_1_2, lane_toState_2_2, lane_toState_3_2, lane_toState_4_2, lane_toState_5_2, lane_toState_6_2, lane_toState_0_3, lane_toState_1_3, lane_toState_2_3, lane_toState_3_3, lane_toState_4_3, lane_toState_5_3, lane_toState_6_3, lane_toState_0_4, lane_toState_1_4, lane_toState_2_4, lane_toState_3_4, lane_toState_4_4, lane_toState_5_4, lane_toState_6_4, rotationOffset_0_0, rotationOffset_1_0, rotationOffset_2_0, rotationOffset_3_0, rotationOffset_4_0, rotationOffset_0_1, rotationOffset_1_1, rotationOffset_2_1, rotationOffset_3_1, rotationOffset_4_1, rotationOffset_0_2, rotationOffset_1_2, rotationOffset_2_2, rotationOffset_3_2, rotationOffset_4_2, rotationOffset_0_3, rotationOffset_1_3, rotationOffset_2_3, rotationOffset_3_3, rotationOffset_4_3, rotationOffset_0_4, rotationOffset_1_4, rotationOffset_2_4, rotationOffset_3_4, rotationOffset_4_4]

theorem iotaS_toState (s : KState) (c : UInt64) :
    (iotaS s c).toState = s.toState.setIfInBounds 0 (lane s.toState 0 0 ^^^ c.toBitVec) := by
  apply toState_ext _ _ (by rw [Array.size_setIfInBounds, toState_size])
  · simp only [Array.getElem_setIfInBounds_self, iotaS, toState_getElem_0, UInt64.toBitVec_xor,
      lane_toState_0_0]
  all_goals
    rw [Array.getElem_setIfInBounds_ne (by rw [toState_size]; decide) (by decide)]
    rfl

/-- One word round. -/
@[inline] def roundS (s : KState) (c : UInt64) : KState :=
  iotaS (chiS (rhoPiS (thetaS s))) c

theorem roundS_toState (s : KState) (c : UInt64) :
    (roundS s c).toState = round s.toState c.toBitVec := by
  simp only [roundS, round, iotaS_toState, chiS_toState, rhoPiS_toState, thetaS_toState,
    theta_eq_thetaCached]

/-- The round constants as machine words. -/
def roundConstantsS : List UInt64 := roundConstants.map UInt64.ofBitVec

/-- Keccak-f[1600] on the word state: the spec's twenty-four rounds, in order. -/
def keccakS (s : KState) : KState := roundConstantsS.foldl roundS s

/-- **The permutation refinement**: the word permutation is the spec's
Keccak-f[1600] on the lane representation, for every state. -/
theorem keccakF_fast_eq (s : KState) : (keccakS s).toState = keccakF1600 s.toState := by
  have hfold (constants : List Lane) (initial : KState) :
      ((constants.map UInt64.ofBitVec).foldl roundS initial).toState =
        constants.foldl round initial.toState := by
    induction constants generalizing initial with
    | nil => rfl
    | cons constant rest ih =>
        simp only [List.map_cons, List.foldl_cons]
        rw [ih, roundS_toState, UInt64.toBitVec_ofBitVec]
  exact hfold roundConstants s


/-! ### Absorption over a byte array -/

theorem laneAt_eq_fold (b : ByteArray) (p : Nat) :
    laneAt b p = (List.range 8).foldl
      (fun acc t => acc ^^^ (byteAt b (p + t) <<< UInt64.ofNat (8 * t))) 0 := rfl

theorem toUInt64_eq_ofNat (v : UInt8) : v.toUInt64 = UInt64.ofNat v.toNat := by
  apply UInt64.toNat_inj.mp
  rw [UInt8.toNat_toUInt64, UInt64.toNat_ofNat']
  exact (Nat.mod_eq_of_lt (Nat.lt_trans v.toNat_lt (by decide))).symm

theorem shl_byte (v : UInt8) (t : Nat) (ht : t < 8) :
    (v.toUInt64 <<< UInt64.ofNat (8 * t)).toBitVec =
      BitVec.ofNat 64 (v.toNat * 2 ^ (8 * t)) := by
  rw [toUInt64_eq_ofNat]
  simp only [UInt64.toBitVec_shiftLeft, UInt64.toBitVec_ofNat']
  have hs : 8 * t < 64 := by omega
  have hs64 : 8 * t < 2 ^ 64 := by omega
  rw [BitVec.shiftLeft_eq']
  simp only [BitVec.toNat_umod, BitVec.toNat_ofNat]
  have h64 : (64 : BitVec 64).toNat = 64 := by decide
  rw [h64, Nat.mod_eq_of_lt hs64, Nat.mod_eq_of_lt hs]
  rw [BitVec.shiftLeft_eq_mul_twoPow]
  have hpow : BitVec.twoPow 64 (8 * t) = BitVec.ofNat 64 (2 ^ (8 * t)) := by
    apply BitVec.eq_of_toNat_eq
    simp only [BitVec.toNat_twoPow, BitVec.toNat_ofNat]
  rw [hpow, ← BitVec.ofNat_mul]

theorem getD_take_drop (l : List UInt8) (off q : Nat) (hq : q < 136) :
    ((l.drop off).take 136).getD q 0 = l.getD (off + q) 0 := by
  simp only [List.getD_eq_getElem?_getD, List.getElem?_take, hq, if_true,
    List.getElem?_drop]

theorem getD_data (b : ByteArray) (j : Nat) : b.data.toList.getD j 0 = byteOr0 b j := by
  unfold byteOr0
  by_cases h : j < b.size
  · rw [dif_pos h, List.getD_eq_getElem?_getD, Array.getElem?_toList]
    have h' : j < b.data.size := h
    rw [Array.getElem?_eq_getElem h']
    rfl
  · rw [dif_neg h, List.getD_eq_getElem?_getD, Array.getElem?_toList]
    have h' : ¬ j < b.data.size := h
    rw [Array.getElem?_eq_none (by omega)]
    rfl

theorem laneAt_eq (b : ByteArray) (off i : Nat) (hi : i < 17) :
    laneFromBlock ((b.data.toList.drop off).take 136) i =
      (laneAt b (off + 8 * i)).toBitVec := by
  have hfold (offsets : List Nat) (h : ∀ t ∈ offsets, t < 8) (acc : UInt64) :
      (offsets.foldl (fun a t => a ^^^ (byteAt b (off + 8 * i + t) <<< UInt64.ofNat (8 * t)))
        acc).toBitVec =
      offsets.foldl (fun a t => a ^^^ BitVec.ofNat 64
        ((((b.data.toList.drop off).take 136).getD (8 * i + t) 0).toNat * 2 ^ (8 * t)))
        acc.toBitVec := by
    induction offsets generalizing acc with
    | nil => rfl
    | cons t rest ih =>
        simp only [List.foldl_cons]
        rw [ih (fun x hx => h x (List.mem_cons_of_mem _ hx))]
        have ht : t < 8 := h t (by simp)
        rw [UInt64.toBitVec_xor, byteAt, shl_byte _ _ ht,
          getD_take_drop _ _ _ (by omega), getD_data, Nat.add_assoc]
  rw [laneAt_eq_fold, hfold (List.range 8) (fun t ht => List.mem_range.mp ht) 0]
  rfl

set_option maxHeartbeats 4000000 in
theorem xorBlockS_toState (s : KState) (b : ByteArray) (off : Nat) :
    (xorBlockS s b off).toState = xorRateBlock s.toState ((b.data.toList.drop off).take 136) := by
  apply toState_ext _ _ (by simp [xorRateBlock]) <;>
    simp (config := { decide := true }) only [xorRateBlock, Array.getElem_ofFn, rateLanes,
      xorBlockS, toState_getElem_0, toState_getElem_1, toState_getElem_2, toState_getElem_3, toState_getElem_4, toState_getElem_5, toState_getElem_6, toState_getElem_7, toState_getElem_8, toState_getElem_9, toState_getElem_10, toState_getElem_11, toState_getElem_12, toState_getElem_13, toState_getElem_14, toState_getElem_15, toState_getElem_16, toState_getElem_17, toState_getElem_18, toState_getElem_19, toState_getElem_20, toState_getElem_21, toState_getElem_22, toState_getElem_23, toState_getElem_24, toState_getD_0, toState_getD_1, toState_getD_2, toState_getD_3, toState_getD_4, toState_getD_5, toState_getD_6, toState_getD_7, toState_getD_8, toState_getD_9, toState_getD_10, toState_getD_11, toState_getD_12, toState_getD_13, toState_getD_14, toState_getD_15, toState_getD_16, toState_getD_17, toState_getD_18, toState_getD_19, toState_getD_20, toState_getD_21, toState_getD_22, toState_getD_23, toState_getD_24, UInt64.toBitVec_xor, laneAt_eq, Nat.reduceMul, Nat.add_zero, if_true,
      if_false]

/-- Absorb `count` full rate blocks of `b`, starting at byte `off`. -/
def absorbLoop (b : ByteArray) : Nat → Nat → KState → KState
  | 0, _, s => s
  | count + 1, off, s => absorbLoop b count (off + 136) (keccakS (xorBlockS s b off))

theorem absorb_fast_eq (b : ByteArray) (count off : Nat) (s : KState) :
    (absorbLoop b count off s).toState =
      absorbFrom count s.toState (b.data.toList.drop off) := by
  induction count generalizing off s with
  | zero => rfl
  | succ count ih =>
      rw [absorbLoop, absorbFrom, ih, keccakF_fast_eq, xorBlockS_toState, List.drop_drop]
      simp only [rateBytes, Nat.add_comm]

theorem zeroS_toState : zeroS.toState = zeroState := rfl

/-! ### Byte-array builders, proved against their list readings -/

/-- Append every byte of a list. -/
def pushList (b : ByteArray) (l : List UInt8) : ByteArray := l.foldl ByteArray.push b

theorem push_data (b : ByteArray) (x : UInt8) :
    (b.push x).data.toList = b.data.toList ++ [x] := by
  cases b
  simp [ByteArray.push]

theorem pushList_data (b : ByteArray) (l : List UInt8) :
    (pushList b l).data.toList = b.data.toList ++ l := by
  induction l generalizing b with
  | nil => simp [pushList]
  | cons x xs ih =>
      simp only [pushList, List.foldl_cons] at ih ⊢
      rw [ih, push_data, List.append_assoc, List.singleton_append]

/-- Append `n` zero bytes. -/
def pushZeros (b : ByteArray) : Nat → ByteArray
  | 0 => b
  | n + 1 => pushZeros (b.push 0) n

theorem pushZeros_data (b : ByteArray) (n : Nat) :
    (pushZeros b n).data.toList = b.data.toList ++ List.replicate n 0 := by
  induction n generalizing b with
  | zero => simp [pushZeros]
  | succ n ih =>
      rw [pushZeros, ih, push_data, List.append_assoc, List.replicate_succ, List.singleton_append]

theorem size_eq_length (b : ByteArray) : b.size = b.data.toList.length := by
  rw [Array.length_toList]
  rfl

/-- `padForRate` on a byte array. -/
def padBA (b : ByteArray) (suffix : UInt8) : ByteArray :=
  let count := rateBytes - b.size % rateBytes
  if count = 1 then b.push (suffix ^^^ (128 : UInt8))
  else (pushZeros (b.push suffix) (count - 2)).push 128

theorem padBA_data (b : ByteArray) (suffix : UInt8) :
    (padBA b suffix).data.toList = padForRate b.data.toList suffix := by
  unfold padBA padForRate
  rw [size_eq_length]
  dsimp only
  by_cases hc : rateBytes - b.data.toList.length % rateBytes = 1
  · rw [if_pos hc, if_pos hc, push_data]
  · rw [if_neg hc, if_neg hc, push_data, pushZeros_data, push_data]

/-- The padded sponge over a byte array, before squeezing. -/
def spongeS (b : ByteArray) (suffix : UInt8) : KState :=
  let padded := padBA b suffix
  absorbLoop padded (padded.size / rateBytes) 0 zeroS

theorem spongeS_toState (b : ByteArray) (suffix : UInt8) :
    (spongeS b suffix).toState = absorbPadded (padForRate b.data.toList suffix) := by
  unfold spongeS absorbPadded
  rw [absorb_fast_eq, zeroS_toState, size_eq_length, padBA_data, List.drop_zero]

/-! ### Squeezing the first 256 bits -/

/-- Lane `j` of the rate, `j < 4`. -/
def outLane (s : KState) : Nat → UInt64
  | 0 => s.a0
  | 1 => s.a1
  | 2 => s.a2
  | 3 => s.a3
  | _ => 0

/-- The first thirty-two output bytes, read straight from the words. -/
def squeezeS (s : KState) : List UInt8 :=
  (List.range outputBytes).map fun k => (outLane s (k / 8) >>> UInt64.ofNat (8 * (k % 8))).toUInt8

theorem shr_byte (x : UInt64) (t : Nat) (ht : t < 8) :
    (x >>> UInt64.ofNat (8 * t)).toUInt8 = UInt8.ofNat (x.toBitVec.toNat / 2 ^ (8 * t) % 256) := by
  apply UInt8.toNat_inj.mp
  simp only [UInt64.toNat_toUInt8, UInt64.toNat_shiftRight, UInt64.toNat_ofNat',
    Nat.shiftRight_eq_div_pow, UInt8.toNat_ofNat']
  have hs : 8 * t < 64 := by omega
  have hs64 : 8 * t < 2 ^ 64 := by omega
  rw [Nat.mod_eq_of_lt hs64, Nat.mod_eq_of_lt hs]
  simp

theorem squeeze_fast_eq (s : KState) : squeezeS s = squeeze32 s.toState := by
  unfold squeezeS squeeze32
  apply List.map_congr_left
  intro k hk
  have hk32 : k < 32 := List.mem_range.mp hk
  have hlane : s.toState.getD (k / 8) zeroLane = (outLane s (k / 8)).toBitVec := by
    have : k / 8 < 4 := by omega
    generalize k / 8 = j at this ⊢
    match j, this with
    | 0, _ => rfl
    | 1, _ => rfl
    | 2, _ => rfl
    | 3, _ => rfl
    | j + 4, h => exact absurd h (by omega)
  unfold stateByte
  rw [hlane, shr_byte _ _ (Nat.mod_lt _ (by decide))]

/-! ### The fast cSHAKE256 and the sponge entry point -/

/-- `absorbPadded` through the word permutation over a byte array. -/
def absorbPaddedFast (padded : List UInt8) : State :=
  (absorbLoop (pushList ByteArray.empty padded) (padded.length / rateBytes) 0 zeroS).toState

theorem empty_data : ByteArray.empty.data.toList = [] := rfl

theorem absorbPadded_fast_eq (padded : List UInt8) :
    absorbPaddedFast padded = absorbPadded padded := by
  unfold absorbPaddedFast absorbPadded
  rw [absorb_fast_eq, pushList_data, empty_data, List.nil_append, List.drop_zero,
    zeroS_toState]

/-- The 32-byte squeeze of the padded sponge of a byte array. -/
def spongeBytes (b : ByteArray) (suffix : UInt8) : List UInt8 :=
  squeezeS (spongeS b suffix)

theorem sponge_fast_eq (b : ByteArray) (suffix : UInt8) :
    spongeBytes b suffix = squeeze32 (absorbPadded (padForRate b.data.toList suffix)) := by
  rw [spongeBytes, squeeze_fast_eq, spongeS_toState]

/-- cSHAKE256 (empty function name, 256-bit output) on the fast path: the
input list is copied once into a byte array; framing, padding, absorption and
squeezing never return to lists. -/
def cshake256Fast (customization input : List UInt8) : List UInt8 :=
  if customization = [] then spongeBytes (pushList ByteArray.empty input) 0x1f
  else spongeBytes (pushList (pushList ByteArray.empty (customizationPrefix customization)) input)
    0x04

theorem cshake256Fast_eq (customization input : List UInt8) :
    cshake256Fast customization input = cshake256Bytes customization input := by
  unfold cshake256Fast cshake256Bytes
  by_cases h : customization = []
  · simp only [h, if_true, sponge_fast_eq, pushList_data, empty_data, List.nil_append]
  · simp only [h, if_false, sponge_fast_eq, pushList_data, empty_data, List.nil_append]


/-! ## Attachment -/

/-- The compiled Host absorbs through the word permutation. -/
@[csimp] theorem absorbPadded_eq_fast : absorbPadded = absorbPaddedFast := by
  funext padded
  exact (absorbPadded_fast_eq padded).symm

/-- The compiled Host's cSHAKE256 is the fast path. -/
@[csimp] theorem cshake256Bytes_eq_fast : cshake256Bytes = cshake256Fast := by
  funext customization input
  exact (cshake256Fast_eq customization input).symm

end Minidregg.Compiler.Sp800185Cshake256.Fast

/-! Axiom pins: the standard three at most; no `sorryAx`, no `native_decide`. -/
/-- info: 'Minidregg.Compiler.Sp800185Cshake256.Fast.keccakF_fast_eq' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms Minidregg.Compiler.Sp800185Cshake256.Fast.keccakF_fast_eq
/-- info: 'Minidregg.Compiler.Sp800185Cshake256.Fast.absorb_fast_eq' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms Minidregg.Compiler.Sp800185Cshake256.Fast.absorb_fast_eq
/-- info: 'Minidregg.Compiler.Sp800185Cshake256.Fast.squeeze_fast_eq' depends on axioms: [propext, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms Minidregg.Compiler.Sp800185Cshake256.Fast.squeeze_fast_eq
/-- info: 'Minidregg.Compiler.Sp800185Cshake256.Fast.sponge_fast_eq' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms Minidregg.Compiler.Sp800185Cshake256.Fast.sponge_fast_eq
/-- info: 'Minidregg.Compiler.Sp800185Cshake256.Fast.absorbPadded_fast_eq' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms Minidregg.Compiler.Sp800185Cshake256.Fast.absorbPadded_fast_eq
/-- info: 'Minidregg.Compiler.Sp800185Cshake256.Fast.cshake256Fast_eq' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms Minidregg.Compiler.Sp800185Cshake256.Fast.cshake256Fast_eq
/-- info: 'Minidregg.Compiler.Sp800185Cshake256.Fast.absorbPadded_eq_fast' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms Minidregg.Compiler.Sp800185Cshake256.Fast.absorbPadded_eq_fast
/-- info: 'Minidregg.Compiler.Sp800185Cshake256.Fast.cshake256Bytes_eq_fast' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs (whitespace := lax) in #print axioms Minidregg.Compiler.Sp800185Cshake256.Fast.cshake256Bytes_eq_fast
