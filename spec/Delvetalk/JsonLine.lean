/- The driver's line check. Lean's JSON decoder substitutes U+FFFD for a lone surrogate escape;
   a line whose `\uXXXX` escapes are not Unicode scalar values is refused before decoding, so the
   wire keeps strings exact. -/
namespace Delvetalk

private def hex4 (a b c d : Char) : Option Nat := do
  let digit (c : Char) : Option Nat :=
    if c >= '0' && c <= '9' then some (c.toNat - 48)
    else if c >= 'a' && c <= 'f' then some (c.toNat - 87)
    else if c >= 'A' && c <= 'F' then some (c.toNat - 55)
    else none
  return (← digit a)*4096 + (← digit b)*256 + (← digit c)*16 + (← digit d)

def scalarEscapes : List Char → Bool
  | '\\' :: 'u' :: a :: b :: c :: d :: rest =>
    match hex4 a b c d with
    | none => false
    | some n =>
      if 55296 <= n && n <= 56319 then
        match rest with
        | '\\' :: 'u' :: e :: f :: g :: h :: tail =>
          match hex4 e f g h with
          | some m => 56320 <= m && m <= 57343 && scalarEscapes tail
          | none => false
        | _ => false
      else if 56320 <= n && n <= 57343 then false
      else scalarEscapes rest
  | '\\' :: _ :: rest => scalarEscapes rest
  | _ :: rest => scalarEscapes rest
  | [] => true

private def hexByte (b : UInt8) : Option Nat :=
  if b >= 48 && b <= 57 then some (b.toNat - 48)
  else if b >= 97 && b <= 102 then some (b.toNat - 87)
  else if b >= 65 && b <= 70 then some (b.toNat - 55)
  else none

private def hex4At (bytes : ByteArray) (i : Nat) : Option Nat := do
  return (← hexByte bytes[i]!)*4096 + (← hexByte bytes[i+1]!)*256 + (← hexByte bytes[i+2]!)*16 + (← hexByte bytes[i+3]!)

/-- `scalarEscapes` over the UTF-8 bytes of a line from byte `i` (every byte it inspects is
ASCII, and a multi-byte character inside a `\uXXXX` window makes both refuse). -/
def scalarEscapesFrom (bytes : ByteArray) (i : Nat) : Bool :=
  if h : i < bytes.size then
    if bytes[i] != 92 then scalarEscapesFrom bytes (i + 1)
    else if i + 1 < bytes.size && bytes[i+1]! == 117 && i + 5 < bytes.size then
      match hex4At bytes (i + 2) with
      | none => false
      | some n =>
        if 55296 <= n && n <= 56319 then
          if i + 11 < bytes.size && bytes[i+6]! == 92 && bytes[i+7]! == 117 then
            match hex4At bytes (i + 8) with
            | some m => 56320 <= m && m <= 57343 && scalarEscapesFrom bytes (i + 12)
            | none => false
          else false
        else if 56320 <= n && n <= 57343 then false
        else scalarEscapesFrom bytes (i + 6)
    else scalarEscapesFrom bytes (i + 2)
  else true
termination_by bytes.size - i

/-- `scalarEscapes line.toList`, without building the list. -/
def scalarEscapesText (line : String) : Bool := scalarEscapesFrom line.toUTF8 0
end Delvetalk
