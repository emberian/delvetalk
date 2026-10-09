/-
# Theory.Sp800185Cshake256Spec -- the cSHAKE256 specification

This module is the definition of the concrete cSHAKE256 backend: every theorem
about Mini's roots, digests and authenticators is about these functions.  It
states, in Lean:

* Keccak-f[1600], with twenty-four rounds over twenty-five 64-bit lanes;
* the 1088-bit (136-byte) SHAKE256/cSHAKE256 sponge rate;
* SP 800-185 `left_encode`, `encode_string`, and `bytepad` framing;
* the empty-customization SHAKE256 suffix and nonempty cSHAKE suffix; and
* the first 32 squeezed bytes selected by the controller.

The definitions are written for clarity, over lists and `BitVec 64` lanes.
The compiled Host does not run them: `Sp800185Cshake256Fast` proves a word-
and byte-array implementation equal to `absorbPadded` and `cshake256Bytes` for
every input and attaches it with `@[csimp]`.  Import `Sp800185Cshake256Core`
(both modules) rather than this one, so that compiled callers get the
substitution.  Like the fast path, this module imports only `Init`.

The module deliberately has no controller, digest carrier, codec proof, or
build-time conformance vectors.  Keeping this exact computation below those
surfaces lets the vectors run independently and keeps executable definitions
out of the heavy controller module's elaboration unit.  No collision
resistance or random-oracle claim is made here.

SP 800-185 bounds `left_encode` inputs to values whose byte width fits in one
byte.  The total Lean function extends framing outside that standard domain by
truncating the width byte with `UInt8.ofNat`; ordinary finite protocol frames
are far inside the standard bound.
-/


namespace Minidregg.Compiler.Sp800185Cshake256

set_option autoImplicit false

/-! ## SP 800-185 byte framing -/

/-- The base-256 digits of `value`, least significant first, with `fuel` bounding the recursion
(structural, so `decide` evaluates it). `fuel ≥ value` always suffices: each step divides by 256. -/
def natBytesLEAux : Nat → Nat → List UInt8
  | 0, _ => []
  | fuel + 1, value => if value = 0 then [] else UInt8.ofNat (value % 256) :: natBytesLEAux fuel (value / 256)

/-- The base-256 digits of `value`, least significant first; `[]` for `0`. This is `Nat.digits 256`
read as bytes (`natBytesLE_eq_digits`, in `Compiler.Sp800185Cshake256`, where Mathlib is in scope):
the executable core stays on `Init`, so every runtime closure that hashes (the channel library a
member's phone loads) carries no Mathlib initializers. -/
def natBytesLE (value : Nat) : List UInt8 := natBytesLEAux value value

/-- Minimal nonempty big-endian base-256 representation. -/
def natBytesBE (value : Nat) : List UInt8 :=
  let little := natBytesLE value
  let nonempty := if little = [] then [0] else little
  nonempty.reverse

/-- SP 800-185 `left_encode`, totalized beyond the standard's 255-byte-width
domain by `UInt8.ofNat`. -/
def leftEncode (value : Nat) : List UInt8 :=
  let bytes := natBytesBE value
  UInt8.ofNat bytes.length :: bytes

/-- SP 800-185 `encode_string`: encode the bit length, then the bytes. -/
def encodeString (bytes : List UInt8) : List UInt8 :=
  leftEncode (8 * bytes.length) ++ bytes

/-- SP 800-185 `bytepad`.  The `width = 0` branch totalizes the helper; the
cSHAKE256 specialization below always selects width 136. -/
def bytepad (bytes : List UInt8) (width : Nat) : List UInt8 :=
  if width = 0 then [] else
    let prefixed := leftEncode width ++ bytes
    let zeroCount := (width - prefixed.length % width) % width
    prefixed ++ List.replicate zeroCount 0

/-! ## Keccak-f[1600] -/

abbrev Lane := BitVec 64
abbrev State := Array Lane

def zeroLane : Lane := BitVec.ofNat 64 0
def zeroState : State := Array.replicate 25 zeroLane

/-- Keccak's lane index is `x + 5*y`.  Modulo indexing makes the helper total;
all round callers pass coordinates in `[0,5)`. -/
def lane (state : State) (x y : Nat) : Lane :=
  state.getD (x % 5 + 5 * (y % 5)) zeroLane

def xorColumn (state : State) (x : Nat) : Lane :=
  (List.range 5).foldl (fun acc y => acc ^^^ lane state x y) zeroLane

def theta (state : State) : State :=
  Array.ofFn fun index : Fin 25 =>
    let x := index.val % 5
    let y := index.val / 5
    lane state x y ^^^ xorColumn state (x + 4) ^^^
      (xorColumn state (x + 1)).rotateLeft 1

/-- Executable sharing for theta: each of the five column parities and
rotation deltas is computed once, before producing the twenty-five lanes. -/
def thetaCached (state : State) : State :=
  let columns := Array.ofFn fun x : Fin 5 => xorColumn state x.val
  let deltas := Array.ofFn fun x : Fin 5 =>
    columns[(x.val + 4) % 5]'(by simp [columns]; exact Nat.mod_lt _ (by decide)) ^^^
      (columns[(x.val + 1) % 5]'(by simp [columns]; exact Nat.mod_lt _ (by decide))).rotateLeft 1
  Array.ofFn fun index : Fin 25 =>
    lane state (index.val % 5) (index.val / 5) ^^^
      deltas[index.val % 5]'(by simp [deltas]; exact Nat.mod_lt _ (by decide))

theorem xorColumn_mod (state : State) (x : Nat) :
    xorColumn state (x % 5) = xorColumn state x := by
  simp only [xorColumn, lane, Nat.mod_mod]

/-- Theta with shared column parities is theta, for every array, including
short arrays under the default-lane convention.  `Sp800185Cshake256Fast`
starts its word-level refinement from this shape. -/
theorem theta_eq_thetaCached : theta = thetaCached := by
  funext state
  unfold theta thetaCached
  congr 1
  funext index
  simp only [Array.getElem_ofFn, xorColumn_mod]
  exact BitVec.xor_assoc _ _ _

/-- info: 'Minidregg.Compiler.Sp800185Cshake256.theta_eq_thetaCached' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs (whitespace := lax) in
#print axioms theta_eq_thetaCached

/-- FIPS 202 rotation offsets, indexed by `x + 5*y`. -/
def rotationOffsets : Array Nat := #[
   0,  1, 62, 28, 27,
  36, 44,  6, 55, 20,
   3, 10, 43, 25, 39,
  41, 45, 15, 21,  8,
  18,  2, 61, 56, 14
]

def rotationOffset (x y : Nat) : Nat :=
  rotationOffsets.getD (x % 5 + 5 * (y % 5)) 0

/-- The fused rho/pi step writes every source lane `(x,y)` to
`(y, 2*x+3*y mod 5)`. -/
def rhoPi (state : State) : State :=
  (List.range 25).foldl (fun output source =>
    let x := source % 5
    let y := source / 5
    let target := y + 5 * ((2 * x + 3 * y) % 5)
    output.setIfInBounds target ((lane state x y).rotateLeft (rotationOffset x y)))
    zeroState

def chi (state : State) : State :=
  Array.ofFn fun index : Fin 25 =>
    let x := index.val % 5
    let y := index.val / 5
    lane state x y ^^^ ((~~~lane state (x + 1) y) &&& lane state (x + 2) y)

/-- FIPS 202 round constants. -/
def roundConstants : List Lane := [
  BitVec.ofNat 64 0x0000000000000001,
  BitVec.ofNat 64 0x0000000000008082,
  BitVec.ofNat 64 0x800000000000808a,
  BitVec.ofNat 64 0x8000000080008000,
  BitVec.ofNat 64 0x000000000000808b,
  BitVec.ofNat 64 0x0000000080000001,
  BitVec.ofNat 64 0x8000000080008081,
  BitVec.ofNat 64 0x8000000000008009,
  BitVec.ofNat 64 0x000000000000008a,
  BitVec.ofNat 64 0x0000000000000088,
  BitVec.ofNat 64 0x0000000080008009,
  BitVec.ofNat 64 0x000000008000000a,
  BitVec.ofNat 64 0x000000008000808b,
  BitVec.ofNat 64 0x800000000000008b,
  BitVec.ofNat 64 0x8000000000008089,
  BitVec.ofNat 64 0x8000000000008003,
  BitVec.ofNat 64 0x8000000000008002,
  BitVec.ofNat 64 0x8000000000000080,
  BitVec.ofNat 64 0x000000000000800a,
  BitVec.ofNat 64 0x800000008000000a,
  BitVec.ofNat 64 0x8000000080008081,
  BitVec.ofNat 64 0x8000000000008080,
  BitVec.ofNat 64 0x0000000080000001,
  BitVec.ofNat 64 0x8000000080008008
]

def round (state : State) (constant : Lane) : State :=
  let mixed := chi (rhoPi (theta state))
  mixed.setIfInBounds 0 (lane mixed 0 0 ^^^ constant)

/-- The exact twenty-four-round Keccak-f[1600] permutation. -/
def keccakF1600 (state : State) : State :=
  roundConstants.foldl round state

/-! ## The 1088-bit-rate sponge and cSHAKE256 -/

def rateBytes : Nat := 136
def rateLanes : Nat := 17
def outputBytes : Nat := 32

def laneFromBlock (block : List UInt8) (laneIndex : Nat) : Lane :=
  (List.range 8).foldl (fun acc offset =>
    acc ^^^ BitVec.ofNat 64
      ((block.getD (8 * laneIndex + offset) 0).toNat * 2 ^ (8 * offset)))
    zeroLane

def xorRateBlock (state : State) (block : List UInt8) : State :=
  Array.ofFn fun index : Fin 25 =>
    if index.val < rateLanes then
      state.getD index.val zeroLane ^^^ laneFromBlock block index.val
    else state.getD index.val zeroLane

/-- Multi-rate padding for a byte-aligned delimited suffix. -/
def padForRate (bytes : List UInt8) (suffix : UInt8) : List UInt8 :=
  let count := rateBytes - bytes.length % rateBytes
  if count = 1 then
    bytes ++ [suffix ^^^ (128 : UInt8)]
  else
    bytes ++ [suffix] ++ List.replicate (count - 2) 0 ++ [128]

/-- The original indexed specification of block absorption. Retained as the
equivalence target for the linear executable below. -/
def absorbPaddedIndexed (padded : List UInt8) : State :=
  (List.range (padded.length / rateBytes)).foldl (fun state blockIndex =>
    let block := (padded.drop (blockIndex * rateBytes)).take rateBytes
    keccakF1600 (xorRateBlock state block)) zeroState

/-- Carry the unconsumed suffix forward, so each block is visited once. -/
def absorbFrom : Nat → State → List UInt8 → State
  | 0, state, _ => state
  | count + 1, state, rest =>
      absorbFrom count (keccakF1600 (xorRateBlock state (rest.take rateBytes)))
        (rest.drop rateBytes)

theorem absorbFrom_eq_indexed (padded : List UInt8) (count start : Nat)
    (state : State) :
    absorbFrom count state (padded.drop (start * rateBytes)) =
      (List.range' start count).foldl (fun state blockIndex =>
        keccakF1600 (xorRateBlock state
          ((padded.drop (blockIndex * rateBytes)).take rateBytes))) state := by
  induction count generalizing start state with
  | zero => simp [absorbFrom]
  | succ count ih =>
      rw [absorbFrom, List.range'_succ, List.foldl_cons]
      have hdrop :
          (padded.drop (start * rateBytes)).drop rateBytes =
            padded.drop ((start + 1) * rateBytes) := by
        rw [List.drop_drop]
        congr 1
        simp [Nat.add_mul, rateBytes]
      rw [hdrop]
      exact ih (start + 1) _

/-- Every padded block is absorbed by xor followed by Keccak-f. The input
is normally a multiple of the rate; both implementations also agree for every
short or malformed byte list. -/
def absorbPadded (padded : List UInt8) : State :=
  absorbFrom (padded.length / rateBytes) zeroState padded

theorem absorbPadded_eq_indexed (padded : List UInt8) :
    absorbPadded padded = absorbPaddedIndexed padded := by
  simpa only [absorbPadded, absorbPaddedIndexed, List.range'_zero,
    Nat.zero_mul, List.drop_zero, List.range_eq_range'] using
    absorbFrom_eq_indexed padded (padded.length / rateBytes) 0 zeroState

def stateByte (state : State) (index : Nat) : UInt8 :=
  UInt8.ofNat
    ((state.getD (index / 8) zeroLane).toNat / 2 ^ (8 * (index % 8)) % 256)

/-- The first 256 output bits, in Keccak's little-endian lane convention. -/
def squeeze32 (state : State) : List UInt8 :=
  (List.range outputBytes).map (stateByte state)

/-- The SP 800-185 prefix for empty function-name and caller customization. -/
def customizationPrefix (customization : List UInt8) : List UInt8 :=
  bytepad (encodeString [] ++ encodeString customization) rateBytes

/-- cSHAKE256 with empty function-name and a 256-bit output.  SP 800-185
requires the empty-customization case to be exactly SHAKE256. -/
def cshake256Bytes (customization input : List UInt8) : List UInt8 :=
  let shakeCompatible := customization = []
  let framed := if shakeCompatible then input else customizationPrefix customization ++ input
  let suffix : UInt8 := if shakeCompatible then 0x1f else 0x04
  squeeze32 (absorbPadded (padForRate framed suffix))

/-- The linear absorber leaves every cSHAKE output identical to the original
indexed definition, for every customization and input byte list. -/
theorem cshake256Bytes_eq_indexed (customization input : List UInt8) :
    cshake256Bytes customization input =
      let shakeCompatible := customization = []
      let framed := if shakeCompatible then input else customizationPrefix customization ++ input
      let suffix : UInt8 := if shakeCompatible then 0x1f else 0x04
      squeeze32 (absorbPaddedIndexed (padForRate framed suffix)) := by
  simp only [cshake256Bytes, absorbPadded_eq_indexed]

@[simp] theorem squeeze32_length (state : State) :
    (squeeze32 state).length = 32 := by
  simp [squeeze32, outputBytes]

@[simp] theorem cshake256Bytes_length (customization input : List UInt8) :
    (cshake256Bytes customization input).length = 32 := by
  simp [cshake256Bytes]

end Minidregg.Compiler.Sp800185Cshake256
