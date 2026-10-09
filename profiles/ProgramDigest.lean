/- Canonical program fingerprints under the receiving turn's shared work ledger.
   Prices are explicit host work units, not an instruction-count semantics.
   See docs/design/PROGRAM-DIGEST.md for calibration and bounds. -/
import FileCustody
import Compiler.Sha256
open Lean World

namespace ProgramDigest

def maxBytes : Nat := 1048576
def maxDepth : Nat := 256

def charge (amount : Nat) : Evaluation Unit := do
  let left ← get
  if amount > left then throw "invocation budget exhausted"
  set (left - amount)

def bounded (bytes : Nat) : Except String Nat :=
  if bytes > maxBytes then .error "program digest exceeds 1 MiB" else .ok bytes

-- The extra state counts scanned string bytes across the entire value. Rounding
-- once across strings avoids pricing many short field names as full blocks.
abbrev Measure := StateT Nat Evaluation

def scanString (s : String) : Measure Nat := do
  let raw := s.utf8ByteSize
  let scanned ← get
  let total ← bounded (scanned + raw)
  charge (2 * ((total + 63) / 64 - (scanned + 63) / 64))
  set total
  let mut bytes := raw + 2
  for i in [:raw] do
    if h : i < s.utf8ByteSize then
      let c := (s.getUTF8Byte ⟨i⟩ h).toNat
      bytes := bytes + (if c == 34 || c == 92 || c == 10 || c == 13 then 1
        else if c < 32 then 5 else 0)
  bounded bytes

def numberSize (number : JsonNumber) : Measure Nat := do
  -- Decimal conversion of a b-bit integer is at most quadratic in its limb
  -- count. Charge both renderings before either toString allocation occurs.
  let words := (number.mantissa.natAbs.log2 + 64) / 64
  let exponentWords := if number.exponent == 0 then 0 else (number.exponent.log2 + 64) / 64
  charge (2 * (words * words + exponentWords * exponentWords))
  let rendered := toString number.mantissa ++
    (if number.exponent == 0 then "" else "e-" ++ toString number.exponent)
  bounded rendered.utf8ByteSize

def measure : Nat → Json → Measure Nat
  | 0, _ => throw "program digest nesting exceeds 256"
  | depth + 1, value => do
    charge 1
    match value with
    | .str s => scanString s
    | .num n => numberSize n
    | .null => pure 4
    | .bool true => pure 4
    | .bool false => pure 5
    | .arr values =>
      let mut size := 2
      let mut first := true
      for value in values do
        size ← bounded (size + (if first then 0 else 1) + (← measure depth value))
        first := false
      return size
    | .obj values =>
      -- Pay for the key traversal before allocating the ordered entry list.
      charge values.size
      let mut size := 2
      let mut first := true
      for (key, value) in values.toList do
        let keySize ← scanString key
        size ← bounded (size + (if first then 0 else 1) + keySize + 1 + (← measure depth value))
        first := false
      return size

def digest (value : Json) : Evaluation String := do
  let (size, _) ← (measure maxDepth value).run 0
  -- Eight units per rendered 64-byte block; SHA-256 adds padding then performs
  -- one compression per block, charged at 32 units. Charge before allocation.
  charge (8 * ((size + 63) / 64) + 32 * ((size + 72) / 64))
  let bytes := FileCustody.encode value
  if bytes.utf8ByteSize != size then throw "program digest size mismatch"
  return Minidregg.Compiler.Sha256.hexString bytes

end ProgramDigest
