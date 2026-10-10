/- Slugs: names for people. A slug is the proquint (Wilkerson's pronounceable quintuplets) of the
   first 32 bits of a CID's multihash digest: two five-letter words, consonant-vowel-consonant-
   vowel-consonant, 16 bits each, joined by a hyphen (`lusab-babad`). CIDs are names for machines;
   a post carries slugs, never CIDs. A slug is not unique: `world-resolve` refuses one that names
   two things. -/
namespace Delvetalk.Host.Slug

def consonants : Array Char := "bdfghjklmnprstvz".toList.toArray
def vowels : Array Char := "aiou".toList.toArray

/-- One proquint word of 16 bits: 4 consonant bits, 2 vowel bits, 4, 2, 4, high bits first. -/
def word (n : Nat) : String :=
  String.ofList [consonants[(n >>> 12) % 16]!, vowels[(n >>> 10) % 4]!, consonants[(n >>> 6) % 16]!,
    vowels[(n >>> 4) % 4]!, consonants[n % 16]!]

/-- The 16 bits a proquint word spells, if it is one. -/
def ofWord (w : String) : Option Nat := do
  let [c1, v1, c2, v2, c3] := w.toList | none
  let c := fun (ch : Char) => consonants.findIdx? (· == ch)
  let v := fun (ch : Char) => vowels.findIdx? (· == ch)
  return ((← c c1) <<< 12) ||| ((← v v1) <<< 10) ||| ((← c c2) <<< 6) ||| ((← v v2) <<< 4) ||| (← c c3)

/-- The slug of 32 bits. -/
def ofBits (n : Nat) : String := word ((n >>> 16) % 65536) ++ "-" ++ word (n % 65536)

/-- The 32 bits a slug spells, if it is one. -/
def decode (slug : String) : Option Nat := do
  let [a, b] := slug.splitOn "-" | none
  return ((← ofWord a) <<< 16) ||| (← ofWord b)

/-- RFC 4648 base32 (lowercase, unpadded) to bytes. -/
def unbase32 (s : String) : Option ByteArray := do
  let alphabet := "abcdefghijklmnopqrstuvwxyz234567".toList
  let mut out := ByteArray.empty
  let mut buffer := 0
  let mut bits := 0
  for ch in s.toList do
    let some v := alphabet.findIdx? (· == ch) | none
    buffer := (buffer <<< 5) ||| v
    bits := bits + 5
    if bits ≥ 8 then
      out := out.push (UInt8.ofNat ((buffer >>> (bits - 8)) % 256))
      bits := bits - 8
      buffer := buffer % (2 ^ bits)
  return out

/-- An unsigned varint at `i`: its value and the index after it. -/
partial def varint (b : ByteArray) (i : Nat) (shift : Nat := 0) (acc : Nat := 0) : Option (Nat × Nat) := do
  let byte ← b[i]?
  let acc := acc ||| ((byte.toNat % 128) <<< shift)
  if byte.toNat < 128 then return (acc, i + 1) else varint b (i + 1) (shift + 7) acc

/-- The slug of a text CID (`b` + base32 of version, codec, multihash code, length, digest): the
    first 32 bits of the digest. None for a string that is not such a CID. -/
def ofCid (cid : String) : Option String := do
  let some rest := cid.dropPrefix? "b" | none
  let bytes ← unbase32 rest.toString
  let (version, i) ← varint bytes 0
  guard (version == 1)
  let (_, i) ← varint bytes i          -- codec
  let (_, i) ← varint bytes i          -- multihash function
  let (length, i) ← varint bytes i
  guard (length ≥ 4 && i + 4 ≤ bytes.size)
  return ofBits ((bytes[i]!.toNat <<< 24) ||| (bytes[i+1]!.toNat <<< 16) ||| (bytes[i+2]!.toNat <<< 8) ||| bytes[i+3]!.toNat)

#guard ofBits 0x7f000001 == "lusab-babad"
#guard decode "lusab-babad" == some 0x7f000001
#guard decode "lusab" == none

end Delvetalk.Host.Slug
