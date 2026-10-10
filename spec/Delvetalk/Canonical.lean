/- The canonical binary form of Data and of JSON, and the identity of either: DAG-CBOR as the
   AT Protocol uses it (RFC 8949 deterministic encoding: definite lengths, shortest integer
   heads, map keys sorted by length and then bytes, no floats, no tags), and its CID
   (CIDv1, dag-cbor 0x71, sha2-256 0x12, base32 lower with the multibase prefix `b`).

   Data:   natural  -> unsigned integer, or a big-endian byte string at 2^64 and above
           boolean  -> true / false          label -> text string
           record   -> map (keys sorted; the first of a repeated field name is kept)
           variant  -> a one-key map {label: payload}
           a proper list (nil / cons chain) -> array
   Decoding is canonical-only and bounded by `Delvetalk.Bounds`. A one-key map decodes as a
   record: a variant is told from a one-field record only by its type, so `decodeAs` re-tags
   a decoded value against a type. An array decodes as the list chain. -/
import Lean.Data.Json
import Compiler.Sha256
import Compiler.ObjectiveBendDataWire
import Theory.ObjectiveBendDemandData
import Theory.ObjectiveBendTypes
import Delvetalk.Limits

namespace Delvetalk.Canonical
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data rowMember)
open Minidregg.Theory.ObjectiveBendTypes (Ty DataBounds)
open Minidregg.Compiler.ObjectiveBendDataWire (listItems? listData)

/-! ## Writing -/

/-- A CBOR head: major type and argument, in the shortest form. -/
def head (out : ByteArray) (major : UInt8) (n : Nat) : ByteArray :=
  let m := major <<< 5
  let be := fun (width k : Nat) (o : ByteArray) =>
    (List.range width).foldl (fun o i => o.push (UInt8.ofNat ((k >>> (8 * (width - 1 - i))) % 256))) o
  if n < 24 then out.push (m ||| UInt8.ofNat n)
  else if n < 256 then be 1 n (out.push (m ||| 24))
  else if n < 65536 then be 2 n (out.push (m ||| 25))
  else if n < 4294967296 then be 4 n (out.push (m ||| 26))
  else be 8 n (out.push (m ||| 27))

def bigEndian (n : Nat) : ByteArray := Id.run do
  let mut bytes : List UInt8 := []
  let mut k := n
  while k > 0 do
    bytes := UInt8.ofNat (k % 256) :: bytes
    k := k / 256
  return ByteArray.mk bytes.toArray

def text (out : ByteArray) (s : String) : ByteArray :=
  (head out 3 s.utf8ByteSize).append s.toUTF8

def twoTo64 : Nat := 18446744073709551616

def natural (out : ByteArray) (n : Nat) : ByteArray :=
  if n < twoTo64 then head out 0 n else
  let b := bigEndian n
  (head out 2 b.size).append b

/-- Keys by byte length, then bytewise: the DAG-CBOR order. UTF-8 orders bytes as code
points, so for keys of one byte length the bytewise order is `String`'s. -/
def keyLess (a b : String) : Bool :=
  if a.utf8ByteSize != b.utf8ByteSize then a.utf8ByteSize < b.utf8ByteSize else a < b

/-- Entries sorted into canonical order; a repeated key keeps its first value. -/
def sortedUnique {α : Type} (entries : List (String × α)) : List (String × α) :=
  let unique := entries.foldl (fun acc (k, v) => if acc.any (·.1 == k) then acc else acc ++ [(k, v)]) []
  (unique.toArray.qsort fun a b => keyLess a.1 b.1).toList

partial def writeData (out : ByteArray) (d : Data) : ByteArray :=
  match listItems? d with
  | some items => items.foldl writeData (head out 4 items.size)
  | none => match d with
  | .natural n => natural out n
  | .boolean b => out.push (if b then 0xf5 else 0xf4)
  | .label s => text out s
  | .record fields =>
      let sorted := sortedUnique fields
      sorted.foldl (fun o (k, v) => writeData (text o k) v) (head out 5 sorted.length)
  | .variant label payload => writeData (text (head out 5 1) label) payload

/-- The canonical bytes of Data. -/
def encode (d : Data) : ByteArray := writeData ByteArray.empty d

-- The byte budget's measure (`Data.canonicalBytes`, in the machine's module) is the size of
-- these bytes: every head width, a bignum, a list, a chain that is not one, a repeated field.
#guard
  let cases : List Data := [.natural 0, .natural 23, .natural 24, .natural 255, .natural 256,
    .natural 65535, .natural 65536, .natural 4294967296, .natural 18446744073709551615,
    .natural 18446744073709551616, .natural (2 ^ 300), .boolean true, .label "", .label "Grüße ✾",
    .label (String.ofList (List.replicate 300 'x')), listData #[], listData #[.natural 1, .label "a"],
    listData ((List.range 30).map Data.natural).toArray,
    .variant "cons" (.record [("head", .natural 1), ("tail", .natural 2)]),
    .variant "cons" (.record [("tail", listData #[]), ("head", .boolean false)]),
    .variant "nil" (.record [("x", .natural 1)]),
    .record [("bb", .natural 1), ("a", .label "x"), ("bb", .natural 99999)],
    .record ((List.range 30).map fun i => (toString i, .boolean true)),
    .variant "tree" (.record [("kids", listData #[.variant "leaf" (.record [])])])]
  cases.all fun d => d.canonicalBytes == (encode d).size

/-- As `encode`, refusing a record that repeats a field name (a map cannot). -/
partial def encodeChecked (d : Data) : Except String ByteArray :=
  let rec unique : Data → Bool
    | .record fields => (fields.map Prod.fst).eraseDups.length == fields.length && fields.all (fun f => unique f.2)
    | .variant _ p => unique p
    | other => match listItems? other with
        | some items => items.all unique
        | none => true
  if unique d then .ok (encode d) else .error "record repeats a field name"

/-- JSON as CBOR: objects are maps, arrays arrays, numbers integers (a fraction is refused),
`null` is CBOR null. This is the form a journal entry is identified by. -/
partial def writeJson (out : ByteArray) (j : Json) : Except String ByteArray :=
  match j with
  | .null => pure (out.push 0xf6)
  | .bool b => pure (out.push (if b then 0xf5 else 0xf4))
  | .str s => pure (text out s)
  | .num n =>
      let rec scale (m : Int) (e : Nat) : Except String Int :=
        match e with
        | 0 => pure m
        | k + 1 => if m % 10 == 0 then scale (m / 10) k else throw "a fraction has no canonical form here"
      do
        let m ← scale n.mantissa n.exponent
        if m ≥ 0 then pure (natural out m.toNat)
        else if m.natAbs - 1 < twoTo64 then pure (head out 1 (m.natAbs - 1))
        -- DAG-CBOR has no negative bignum (tag 3 is refused), and the eight-byte head would
        -- keep only the low 64 bits, giving two integers one encoding.
        else throw "a negative integer below -2^64 has no canonical form"
  | .arr items => items.foldlM writeJson (head out 4 items.size)
  | .obj fields =>
      let sorted := (fields.toArray.qsort fun a b => keyLess a.1 b.1).toList
      sorted.foldlM (fun o (k, v) => writeJson (text o k) v) (head out 5 sorted.length)

def encodeJson (j : Json) : Except String ByteArray := writeJson ByteArray.empty j

/-! ## Identity -/

def digestBytes (message : ByteArray) : ByteArray :=
  ByteArray.mk ((Minidregg.Compiler.Sha256.digest message).toList.flatMap fun w =>
    [UInt8.ofNat (w.toNat >>> 24 % 256), UInt8.ofNat (w.toNat >>> 16 % 256),
     UInt8.ofNat (w.toNat >>> 8 % 256), UInt8.ofNat (w.toNat % 256)]).toArray

def base32Alphabet : Array Char := "abcdefghijklmnopqrstuvwxyz234567".toList.toArray

/-- RFC 4648 base32, lowercase, unpadded. -/
def base32 (bytes : ByteArray) : String := Id.run do
  let mut out := ""
  let mut buffer : Nat := 0
  let mut bits := 0
  for b in bytes do
    buffer := buffer * 256 + b.toNat
    bits := bits + 8
    while bits ≥ 5 do
      out := out.push base32Alphabet[(buffer >>> (bits - 5)) % 32]!
      bits := bits - 5
    buffer := buffer % (1 <<< bits)
  if bits > 0 then out := out.push base32Alphabet[(buffer <<< (5 - bits)) % 32]!
  return out

/-- The binary CID: version 1, dag-cbor, sha2-256 of `bytes`. -/
def cidBytes (bytes : ByteArray) : ByteArray :=
  (ByteArray.mk #[0x01, 0x71, 0x12, 0x20]).append (digestBytes bytes)

/-- The text CID: multibase `b` (base32 lower) of the binary CID. -/
def cid (bytes : ByteArray) : String := "b" ++ base32 (cidBytes bytes)

def cidOf (d : Data) : String := cid (encode d)

def cidOfJson (j : Json) : Except String String := return cid (← encodeJson j)

/-- The CID of a JSON value. Total: a value with no canonical form (a fraction) is
identified by the CID of its printed text instead, which is distinct from any canonical one
only by being of a different value; the kernel's own JSON never has one. -/
def cidJson (j : Json) : String :=
  match cidOfJson j with
  | .ok c => c
  | .error _ => cid j.compress.toUTF8

/-! ## Reading -/

structure Reader where
  bytes : ByteArray
  pos : Nat := 0
  nodes : Nat := 0

abbrev R := StateT Reader (Except String)

def need (n : Nat) : R Unit := do
  let r ← get
  if r.pos + n > r.bytes.size then throw "truncated CBOR"

def byte : R UInt8 := do
  need 1
  let r ← get
  set { r with pos := r.pos + 1 }
  return r.bytes[r.pos]!

def takeBytes (n : Nat) : R ByteArray := do
  need n
  let r ← get
  set { r with pos := r.pos + n }
  return r.bytes.extract r.pos (r.pos + n)

/-- Major type and argument, refusing a head that is not the shortest form. -/
def readHead : R (Nat × Nat) := do
  let b ← byte
  let major := (b >>> 5).toNat
  let info := (b &&& 31).toNat
  let width := fun (n : Nat) => do
    let bs ← takeBytes n
    return bs.foldl (fun acc x => acc * 256 + x.toNat) 0
  if major == 7 && info ≥ 24 then throw "CBOR float or extended simple value is not in the Data model"
  else if info < 24 then return (major, info)
  else if info == 24 then
    let v ← width 1
    if v < 24 then throw "non-canonical CBOR: integer is not in its shortest form"
    return (major, v)
  else if info == 25 then
    let v ← width 2
    if v < 256 then throw "non-canonical CBOR: integer is not in its shortest form"
    return (major, v)
  else if info == 26 then
    let v ← width 4
    if v < 65536 then throw "non-canonical CBOR: integer is not in its shortest form"
    return (major, v)
  else if info == 27 then
    let v ← width 8
    if v < 4294967296 then throw "non-canonical CBOR: integer is not in its shortest form"
    return (major, v)
  else throw "CBOR is not definite-length"

def count : R Unit := do
  let r ← get
  if r.nodes ≥ Bounds.nodesMax then throw "CBOR exceeds the node bound"
  set { r with nodes := r.nodes + 1 }

def utf8 (b : ByteArray) : R String :=
  match String.fromUTF8? b with
  | some s => pure s
  | none => throw "CBOR text is not UTF-8"

mutual
/-- One item. `depth` counts nesting of arrays and maps, never their length. -/
partial def readItem (depth : Nat) : R Data := do
  if depth == 0 then throw "CBOR nesting capacity"
  count
  let (major, n) ← readHead
  match major with
  | 0 => return .natural n
  | 2 =>
      if n > Bounds.bytesMax then throw "CBOR exceeds the byte bound"
      let b ← takeBytes n
      if b.size < 8 || b[0]! == 0 then throw "non-canonical CBOR: byte string is not a big natural"
      let v := b.foldl (fun acc x => acc * 256 + x.toNat) 0
      if v < twoTo64 then throw "non-canonical CBOR: big natural fits in 64 bits"
      return .natural v
  | 3 =>
      if n > Bounds.bytesMax then throw "CBOR exceeds the byte bound"
      return .label (← utf8 (← takeBytes n))
  | 4 =>
      let r ← get
      if n > r.bytes.size - r.pos then throw "truncated CBOR"
      let mut items : Array Data := #[]
      for _ in [0:n] do items := items.push (← readItem (depth - 1))
      return listData items
  | 5 =>
      let r ← get
      if n > r.bytes.size - r.pos then throw "truncated CBOR"
      let mut fields : List (String × Data) := []
      let mut last : Option String := none
      for _ in [0:n] do
        count
        let (km, kn) ← readHead
        if km != 3 then throw "CBOR map key is not text"
        let key ← utf8 (← takeBytes kn)
        if let some prior := last then
          unless keyLess prior key do throw "non-canonical CBOR: map keys are not sorted or repeat"
        last := some key
        fields := fields ++ [(key, ← readItem (depth - 1))]
      return .record fields
  | 7 =>
      if n == 20 then return .boolean false
      else if n == 21 then return .boolean true
      else throw "CBOR simple value not in the Data model"
  | _ => throw "CBOR item not in the Data model"
end

/-- Canonical bytes to Data. An array is a list chain, a map a record (see the header). -/
def decode (bytes : ByteArray) : Except String Data := do
  if bytes.size > Bounds.bytesMax then throw "CBOR exceeds the byte bound"
  let (d, r) ← (readItem Bounds.dataWireDepth).run { bytes }
  if r.pos != bytes.size then throw "trailing bytes after CBOR item"
  return d

/-- Re-tag a decoded value against its type: a one-key map is a variant where the type says
variant. Recursive types unfold through the bounds. -/
partial def retype (bounds : DataBounds) (ty : Ty) (d : Data) : Except String Data :=
  match ty, d with
  | .variable i, _ => match bounds.lookup i with
      | some bound => retype bounds bound d
      | none => throw "type variable without a bound"
  | .variant row, .record [(k, v)] => match rowMember row k with
      | some member => return .variant k (← retype bounds member v)
      | none => throw s!"variant {k} is not in the type"
  | .variant row, .variant k v => match rowMember row k with
      | some member => return .variant k (← retype bounds member v)
      | none => throw s!"variant {k} is not in the type"
  | .field .., .record fields => do
      let fields ← fields.mapM fun (k, v) => do
        match rowMember ty k with
        | some member => return (k, ← retype bounds member v)
        | none => return (k, v)
      return .record fields
  | _, d => pure d

def decodeAs (bounds : DataBounds) (ty : Ty) (bytes : ByteArray) : Except String Data := do
  retype bounds ty (← decode bytes)

/-- The value `decode (encode d)` yields: record fields in canonical order, repeats dropped. -/
partial def normalize : Data → Data
  | .record fields => .record ((sortedUnique fields).map fun (k, v) => (k, normalize v))
  | .variant "nil" (.record []) => .variant "nil" (.record [])
  | .variant l p => .variant l (normalize p)
  | other => other

/-! ## Hex, for the wire ops -/

def hex (bytes : ByteArray) : String :=
  String.ofList (bytes.toList.flatMap fun b =>
    ["0123456789abcdef".toList[b.toNat / 16]!, "0123456789abcdef".toList[b.toNat % 16]!])

def unhex (s : String) : Except String ByteArray := do
  let cs := s.toList
  if cs.length % 2 != 0 then throw "odd hex"
  let digit := fun (c : Char) => if '0' ≤ c && c ≤ '9' then some (c.toNat - 48)
    else if 'a' ≤ c && c ≤ 'f' then some (c.toNat - 87) else none
  let rec go : List Char → Except String (List UInt8)
    | a :: b :: rest => do
        let some x := digit a | throw "bad hex"
        let some y := digit b | throw "bad hex"
        return UInt8.ofNat (x * 16 + y) :: (← go rest)
    | _ => pure []
  return ByteArray.mk (← go cs).toArray

/-! ## Wire ops -/

open Minidregg.Compiler.ObjectiveBendDataWire (decodeData dataJson)

/-- `canonical-encode {data | json, repeat?}` -> `{cid, hex, bytes}`. `repeat` re-encodes that
many times (each with a distinct tag so none can be shared) and reports the checksum, so a
caller can time the encoder without the JSON framing. -/
def encodeOp (j : Json) : Except String Json := do
  let bytes ← match j.getObjVal? "json" with
    | .ok v => encodeJson v
    | .error _ => encodeChecked (← decodeData Bounds.documentWireDepth (← j.getObjVal? "data"))
  let reps := (j.getObjValAs? Nat "repeat").toOption.getD 0
  let data? := (j.getObjVal? "data").toOption.bind (fun d => (decodeData Bounds.documentWireDepth d).toOption)
  let sum := match data? with
    | some d => (List.range reps).foldl (fun acc i =>
        acc + (encode (Data.record [("i", .natural i), ("d", d)])).size) 0
    | none => 0
  return Json.mkObj [("status", toJson "encoded"), ("cid", toJson (cid bytes)), ("hex", toJson (hex bytes)),
    ("bytes", toJson bytes.size), ("checksum", toJson sum)]

/-- `canonical-decode {hex}` -> `{data}`. -/
def decodeOp (j : Json) : Except String Json := do
  let bytes ← unhex (← j.getObjValAs? String "hex")
  return Json.mkObj [("status", toJson "decoded"), ("data", dataJson (← decode bytes)), ("cid", toJson (cid bytes))]

end Delvetalk.Canonical
