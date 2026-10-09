/- SHA-256 (FIPS 180-4) over bytes, for byte FINGERPRINTS: the captured source
fingerprints of the Objective front end and the front-end identity. Not an
identity hash of the protocol (those are cSHAKE256, `Sp800185Cshake256`). The
known-answer vectors are FIPS 180-4 / NIST CAVP values, asserted as compiled
theorems in `Compiler.Sha256Vectors` (kept out of this module so the front end's
run-time closure stays free of the audit machinery and Mathlib). -/
namespace Minidregg.Compiler.Sha256
set_option autoImplicit false

def k : Array UInt32 := #[
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]

def initial : Array UInt32 :=
  #[0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]

@[inline] def rotr (x : UInt32) (n : UInt32) : UInt32 := (x >>> n) ||| (x <<< (32 - n))

/-- The message padded to a whole number of 64-byte blocks. -/
def pad (message : ByteArray) : ByteArray := Id.run do
  let bits := message.size * 8
  let mut out := message.push 0x80
  while out.size % 64 != 56 do out := out.push 0
  for i in [0:8] do out := out.push (UInt8.ofNat ((bits >>> (8 * (7 - i))) % 256))
  return out

def word (bytes : ByteArray) (at_ : Nat) : UInt32 :=
  (bytes.get! at_).toUInt32 <<< 24 ||| (bytes.get! (at_ + 1)).toUInt32 <<< 16 |||
  (bytes.get! (at_ + 2)).toUInt32 <<< 8 ||| (bytes.get! (at_ + 3)).toUInt32

def compress (state : Array UInt32) (bytes : ByteArray) (offset : Nat) : Array UInt32 := Id.run do
  let mut w : Array UInt32 := Array.mkEmpty 64
  for t in [0:16] do w := w.push (word bytes (offset + 4 * t))
  for t in [16:64] do
    let x := w[t - 15]!
    let y := w[t - 2]!
    let s0 := rotr x 7 ^^^ rotr x 18 ^^^ (x >>> 3)
    let s1 := rotr y 17 ^^^ rotr y 19 ^^^ (y >>> 10)
    w := w.push (w[t - 16]! + s0 + w[t - 7]! + s1)
  let mut a := state[0]!
  let mut b := state[1]!
  let mut c := state[2]!
  let mut d := state[3]!
  let mut e := state[4]!
  let mut f := state[5]!
  let mut g := state[6]!
  let mut h := state[7]!
  for t in [0:64] do
    let t1 := h + (rotr e 6 ^^^ rotr e 11 ^^^ rotr e 25) + ((e &&& f) ^^^ (~~~e &&& g)) + k[t]! + w[t]!
    let t2 := (rotr a 2 ^^^ rotr a 13 ^^^ rotr a 22) + ((a &&& b) ^^^ (a &&& c) ^^^ (b &&& c))
    h := g; g := f; f := e; e := d + t1; d := c; c := b; b := a; a := t1 + t2
  return #[state[0]! + a, state[1]! + b, state[2]! + c, state[3]! + d,
    state[4]! + e, state[5]! + f, state[6]! + g, state[7]! + h]

def digest (message : ByteArray) : Array UInt32 := Id.run do
  let padded := pad message
  let mut state := initial
  for block in [0:padded.size / 64] do state := compress state padded (64 * block)
  return state

def hexDigit (n : Nat) : Char := "0123456789abcdef".toList[n % 16]!

/-- Lowercase hexadecimal, 64 characters. -/
def hex (message : ByteArray) : String :=
  String.ofList ((digest message).toList.flatMap fun w =>
    (List.range 8).map fun i => hexDigit ((w.toNat >>> (4 * (7 - i))) % 16))

def hexString (text : String) : String := hex text.toUTF8

end Minidregg.Compiler.Sha256
