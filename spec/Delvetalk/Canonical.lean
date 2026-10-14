/- The canonical binary form of Data and of JSON, and the identity of either: DAG-CBOR as the
   AT Protocol uses it (RFC 8949 deterministic encoding: definite lengths, shortest integer
   heads, map keys sorted by length and then bytes, no floats, no tags), and its CID
   (CIDv1, dag-cbor 0x71, sha2-256 0x12, base32 lower with the multibase prefix `b`).

   Data:   natural  -> unsigned integer, or a big-endian byte string at 2^64 and above
           boolean  -> true / false          label -> text string
           record   -> map (keys sorted; the first of a repeated field name is kept)
           a proper list (nil / cons chain) -> array
           any other variant -> the array [null, label, payload]
   No Data item is null, so a variant's array is no list's, and a variant is never a map: the bytes
   alone tell every value from every other, whatever its type (`encode_injective`).
   Decoding is canonical-only and bounded by `Delvetalk.Bounds`; `decode (encode d)` is
   `normalize d`. -/
import Lean.Data.Json
import Compiler.Sha256
import Compiler.ObjectiveBendDataWire
import Theory.ObjectiveBendDemandData
import Delvetalk.Limits
import Theory.AxiomPin

namespace Delvetalk.Canonical
open Lean (Json toJson)
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
open Delvetalk.Compiler.ObjectiveBendDataWire (listItems? listData)

/-! ## Writing

Every writer is total and has a list-of-bytes specification (`headList`, `textList`, `naturalList`,
`encodeList`), so `encode_injective` below is a theorem about the bytes the host compares. -/

/-- The low `width` bytes of `k`, big-endian. -/
def beBytes : Nat → Nat → List UInt8
  | 0, _ => []
  | w + 1, k => beBytes w (k / 256) ++ [UInt8.ofNat (k % 256)]

/-- A head's additional information for argument `n`: `n` itself below 24, else 24 to 27 for one,
two, four or eight argument bytes. -/
def headInfo (n : Nat) : Nat :=
  if n < 24 then n else if n < 256 then 24 else if n < 65536 then 25 else if n < 4294967296 then 26 else 27

/-- The argument bytes after the initial byte, by the additional information. -/
def widthOf (info : Nat) : Nat :=
  if info < 24 then 0 else if info = 24 then 1 else if info = 25 then 2 else if info = 26 then 4 else 8

def headWidth (n : Nat) : Nat := widthOf (headInfo n)

/-- A CBOR head's bytes: major type and argument, in the shortest form. An argument at 2^64 or
above has no head; it would keep its low eight bytes, which is why `encode_injective` asks that
the encoding be shorter than 2^64 bytes (every argument written is at most its length). -/
def headList (major n : Nat) : List UInt8 :=
  UInt8.ofNat (32 * major + headInfo n) :: beBytes (headWidth n) n

def pushAll (out : ByteArray) (bytes : List UInt8) : ByteArray := bytes.foldl ByteArray.push out

/-- A CBOR head: major type and argument, in the shortest form. -/
def head (out : ByteArray) (major : UInt8) (n : Nat) : ByteArray := pushAll out (headList major.toNat n)

/-- The big-endian bytes of `n`, none for zero. -/
def bigEndianList (n : Nat) : List UInt8 :=
  if n = 0 then [] else bigEndianList (n / 256) ++ [UInt8.ofNat (n % 256)]
termination_by n
decreasing_by omega

def bigEndian (n : Nat) : ByteArray := ⟨(bigEndianList n).toArray⟩

def textList (s : String) : List UInt8 := headList 3 s.utf8ByteSize ++ s.toUTF8.data.toList

def text (out : ByteArray) (s : String) : ByteArray :=
  head out 3 s.utf8ByteSize ++ s.toUTF8

def twoTo64 : Nat := 18446744073709551616

/-- A natural: an unsigned integer below 2^64, else a byte string of its big-endian magnitude. -/
def naturalList (n : Nat) : List UInt8 :=
  if n < twoTo64 then headList 0 n else headList 2 (bigEndianList n).length ++ bigEndianList n

def natural (out : ByteArray) (n : Nat) : ByteArray := pushAll out (naturalList n)

/-- Keys by byte length, then bytewise: the DAG-CBOR order. UTF-8 orders bytes as code
points, so for keys of one byte length the bytewise order is `String`'s. -/
def keyLess (a b : String) : Bool :=
  if a.utf8ByteSize != b.utf8ByteSize then a.utf8ByteSize < b.utf8ByteSize else a < b

/-- Bytewise order, a proper prefix first: the order of canonical encodings, and so of a relation's
keys (FOUNDATION §9). -/
def bytesLt (a b : ByteArray) : Bool := go 0
where
  go (i : Nat) : Bool :=
    if h : i < a.size ∧ i < b.size then
      let x := a[i]'h.1
      let y := b[i]'h.2
      if x == y then go (i + 1) else x < y
    else a.size < b.size
  termination_by a.size - i

#guard bytesLt ⟨#[1, 2]⟩ ⟨#[1, 3]⟩ && bytesLt ⟨#[1]⟩ ⟨#[1, 0]⟩ && !bytesLt ⟨#[1, 0]⟩ ⟨#[1]⟩ &&
  !bytesLt ⟨#[2]⟩ ⟨#[1, 9]⟩ && !bytesLt ⟨#[1, 2]⟩ ⟨#[1, 2]⟩

/-- The first entry of each key, in order. -/
def firstOfEach {α : Type} (entries : List (String × α)) : List (String × α) :=
  entries.foldl (fun acc (k, v) => if acc.any (·.1 == k) then acc else acc ++ [(k, v)]) []

/-- Entries sorted into canonical order; a repeated key keeps its first value. The keys are
distinct and `keyLess` is total on distinct keys, so the order is the one sorted order. -/
def sortedUnique {α : Type} (entries : List (String × α)) : List (String × α) :=
  (firstOfEach entries).mergeSort fun a b => keyLess a.1 b.1

/-- A proper `nil` / `cons` chain's items (a list, which encodes as an array); none otherwise.
Tail-recursive: a list may be long. -/
def listViewFrom : Data → List Data → Option (List Data)
  | .variant "nil" (.record []), acc => some acc.reverse
  | .variant "cons" (.record [("head", h), ("tail", t)]), acc => listViewFrom t (h :: acc)
  | .variant "cons" (.record [("tail", t), ("head", h)]), acc => listViewFrom t (h :: acc)
  | _, _ => none

def listView (d : Data) : Option (List Data) := listViewFrom d []

/-- What a variant that is not a list begins with: a three-item array whose first item is null.
No Data item is null, so this is neither a list's array nor a record's map: a variant `{x: 1}`
and a record `{x: 1}` have different bytes, whatever their type. -/
def variantPrefix : List UInt8 := [0x83, 0xf6]

theorem listViewFrom_mem (d : Data) (acc : List Data) : ∀ items, listViewFrom d acc = some items →
    ∀ x ∈ items, x ∈ acc ∨ sizeOf x < sizeOf d := by
  fun_induction listViewFrom d acc with
  | case1 acc =>
    intro items h x hx
    simp only [Option.some.injEq] at h; subst h; exact .inl (List.mem_reverse.mp hx)
  | case2 hd t acc ih | case3 hd t acc ih =>
    intro items h x hx
    rcases ih items h x hx with m | m
    · rcases List.mem_cons.mp m with rfl | m
      · exact .inr (by simp; omega)
      · exact .inl m
    · exact .inr (by simp; omega)
  | case4 => intro items h; simp at h

theorem listView_mem {d : Data} {items : List Data} (h : listView d = some items) {x : Data}
    (hx : x ∈ items) : sizeOf x < sizeOf d :=
  (listViewFrom_mem d [] items h x hx).resolve_left (by simp)

theorem firstOfEach_mem {α : Type} (entries : List (String × α)) (p : String × α)
    (h : p ∈ firstOfEach entries) : p ∈ entries := by
  suffices ∀ (acc : List (String × α)), p ∈ entries.foldl
      (fun acc (k, v) => if acc.any (·.1 == k) then acc else acc ++ [(k, v)]) acc → p ∈ acc ∨ p ∈ entries by
    rcases this [] h with m | m
    · simp at m
    · exact m
  clear h
  intro acc
  induction entries generalizing acc with
  | nil => exact .inl
  | cons e rest ih =>
    intro m
    simp only [List.foldl_cons] at m
    rcases ih _ m with m | m
    · split at m
      · exact .inl m
      · rcases List.mem_append.mp m with m | m
        · exact .inl m
        · simp at m; subst m; exact .inr (by simp)
    · exact .inr (List.mem_cons_of_mem _ m)

theorem sortedUnique_mem {α : Type} {entries : List (String × α)} {p : String × α}
    (h : p ∈ sortedUnique entries) : p ∈ entries :=
  firstOfEach_mem entries p (List.mem_mergeSort.mp h)

theorem sortedUnique_value_size {fields : List (String × Data)} {p : String × Data}
    (h : p ∈ sortedUnique fields) : sizeOf p.2 < sizeOf (Data.record fields) := by
  have := List.sizeOf_lt_of_mem (sortedUnique_mem h)
  rcases p with ⟨k, v⟩
  simp only [Prod.mk.sizeOf_spec, Data.record.sizeOf_spec] at *
  omega

/-- The canonical bytes of Data, as a list: the specification `writeData` meets (`writeData_spec`). -/
def encodeList (d : Data) : List UInt8 :=
  match _h : listView d with
  | some items => headList 4 items.length ++ items.attach.flatMap fun x => encodeList x.1
  | none => match d with
    | .natural n => naturalList n
    | .boolean b => [if b then 0xf5 else 0xf4]
    | .label s => textList s
    | .record fields =>
      headList 5 (sortedUnique fields).length ++
        (sortedUnique fields).attach.flatMap fun x => textList x.1.1 ++ encodeList x.1.2
    | .variant label payload => variantPrefix ++ textList label ++ encodeList payload
termination_by sizeOf d
decreasing_by
  · exact listView_mem _h x.2
  · exact sortedUnique_value_size x.2
  · simp; omega

def writeData (out : ByteArray) (d : Data) : ByteArray :=
  match _h : listView d with
  | some items => items.attach.foldl (fun o x => writeData o x.1) (head out 4 items.length)
  | none => match d with
    | .natural n => natural out n
    | .boolean b => out.push (if b then 0xf5 else 0xf4)
    | .label s => text out s
    | .record fields =>
      let sorted := sortedUnique fields
      sorted.attach.foldl (fun o x => writeData (text o x.1.1) x.1.2) (head out 5 sorted.length)
    | .variant label payload => writeData (text (pushAll out variantPrefix) label) payload
termination_by sizeOf d
decreasing_by
  · exact listView_mem _h x.2
  · exact sortedUnique_value_size x.2
  · simp; omega

/-- The canonical bytes of Data. -/
def encode (d : Data) : ByteArray := writeData ByteArray.empty d

/-- A variant's opening bytes, for a writer that writes its payload itself. -/
def variantHead (out : ByteArray) (label : String) : ByteArray := text (pushAll out variantPrefix) label

-- A variant is not the one-field record of its label, whatever their type (review 2026-10-12
-- kernel 1: a grant fixing `.variant "x" 1` admitted `{x: 1}`); a list is not a variant either.
#guard encode (.variant "x" (.natural 1)) != encode (.record [("x", .natural 1)])
#guard encode (.variant "nil" (.record [("x", .natural 1)])) != encode (.record [("nil", .record [("x", .natural 1)])])
#guard (encode (.variant "ok" (.record []))).toList == [0x83, 0xf6, 0x62, 0x6f, 0x6b, 0xa0]
#guard encode (.variant "cons" (.record [("head", .label "a"), ("tail", .variant "nil" (.record []))])) !=
  encode (.variant "c" (.record [("head", .label "a"), ("tail", .variant "nil" (.record []))]))

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
    .variant "tree" (.record [("kids", listData #[.variant "leaf" (.record [])])]),
    .variant "x" (.natural 1), .record [("x", .natural 1)], .variant "ok" (.record [])]
  cases.all fun d => d.canonicalBytes == (encode d).size

/-! ## The encoding is injective

Equal bytes are equal values up to what a map cannot hold: record field order, and a repeated
field (a map keeps the first). `normalize` is that quotient, the value `decode` answers. The one
hypothesis is that the bytes are fewer than 2^64: a head holds an argument below 2^64 only, and
every argument written (a length, a count) is at most the number of bytes. -/

/-- The value the bytes of `d` stand for: record fields in canonical order, repeats dropped. -/
def normalize (d : Data) : Data :=
  match _h : listView d with
  | some items => listData (items.attach.map fun x => normalize x.1).toArray
  | none => match d with
    | .record fields => .record ((sortedUnique fields).attach.map fun x => (x.1.1, normalize x.1.2))
    | .variant label payload => .variant label (normalize payload)
    | other => other
termination_by sizeOf d
decreasing_by
  · exact listView_mem _h x.2
  · exact sortedUnique_value_size x.2
  · simp; omega

theorem pushAll_data (out : ByteArray) (l : List UInt8) :
    (pushAll out l).data.toList = out.data.toList ++ l := by
  induction l generalizing out with
  | nil => simp [pushAll]
  | cons b l ih =>
    simp only [pushAll, List.foldl_cons] at ih ⊢
    rw [ih]; simp [ByteArray.data_push]

theorem head_data (out : ByteArray) (major : UInt8) (n : Nat) :
    (head out major n).data.toList = out.data.toList ++ headList major.toNat n := pushAll_data ..

theorem text_data (out : ByteArray) (s : String) :
    (text out s).data.toList = out.data.toList ++ textList s := by
  simp [text, textList, head_data, ByteArray.data_append]

theorem foldl_attach_data {α : Type} (l : List α) (F : ByteArray → α → ByteArray) (E : α → List UInt8)
    (hF : ∀ x ∈ l, ∀ o, (F o x).data.toList = o.data.toList ++ E x) (out : ByteArray) :
    (l.attach.foldl (fun o x => F o x.1) out).data.toList = out.data.toList ++ l.attach.flatMap (fun x => E x.1) := by
  rw [List.foldl_attach (f := F), List.flatMap_subtype (g := E) (fun _ _ => rfl), List.unattach_attach]
  induction l generalizing out with
  | nil => simp
  | cons x l ih =>
    simp only [List.foldl_cons, List.flatMap_cons]
    rw [ih (fun y hy => hF y (List.mem_cons_of_mem _ hy)), hF x (by simp)]
    simp

theorem writeData_spec (out : ByteArray) (d : Data) :
    (writeData out d).data.toList = out.data.toList ++ encodeList d := by
  rw [writeData, encodeList]
  split
  · rename_i items h
    rw [foldl_attach_data items writeData encodeList (fun x _ o => writeData_spec o x), head_data]
    simp
  · split
    · exact pushAll_data ..
    · simp [ByteArray.data_push]
    · exact text_data ..
    · simp only
      rw [foldl_attach_data _ (fun o (p : String × Data) => writeData (text o p.1) p.2)
        (fun (p : String × Data) => textList p.1 ++ encodeList p.2)
        (fun p _ o => by rw [writeData_spec, text_data, List.append_assoc]), head_data]
      simp
    · rw [writeData_spec, text_data, pushAll_data]
      simp
termination_by sizeOf d
decreasing_by
  all_goals (try subst_vars); first
    | exact listView_mem (by assumption) (by assumption)
    | exact sortedUnique_value_size (by assumption)
    | (simp; omega)

theorem encode_data (d : Data) : (encode d).data.toList = encodeList d := by
  simp [encode, writeData_spec]

theorem beBytes_length : ∀ (w k : Nat), (beBytes w k).length = w
  | 0, _ => rfl
  | w + 1, k => by simp [beBytes, beBytes_length w]

/-- Big-endian bytes read back. -/
def fromBE (l : List UInt8) : Nat := l.foldl (fun acc b => acc * 256 + b.toNat) 0

theorem fromBE_append (l : List UInt8) (b : UInt8) : fromBE (l ++ [b]) = fromBE l * 256 + b.toNat := by
  simp [fromBE, List.foldl_append]

theorem fromBE_beBytes : ∀ (w k : Nat), fromBE (beBytes w k) = k % 256 ^ w
  | 0, k => by simp [fromBE, beBytes, Nat.mod_one]
  | w + 1, k => by
    rw [beBytes, fromBE_append, fromBE_beBytes w, UInt8.toNat_ofNat']
    have e : (2 : Nat) ^ 8 = 256 := rfl
    rw [e, Nat.mod_mod, show 256 ^ (w + 1) = 256 * 256 ^ w by rw [Nat.pow_succ, Nat.mul_comm], Nat.mod_mul]
    generalize k / 256 % 256 ^ w = q
    omega

theorem fromBE_bigEndianList (n : Nat) : fromBE (bigEndianList n) = n := by
  rw [bigEndianList]
  split
  · simp_all [fromBE]
  · rw [fromBE_append, fromBE_bigEndianList (n / 256), UInt8.toNat_ofNat']
    have : (2 : Nat) ^ 8 = 256 := rfl
    rw [this]
    omega
termination_by n
decreasing_by omega

theorem beBytes_prefix {w k k' : Nat} {r s : List UInt8} (h : beBytes w k ++ r = beBytes w k' ++ s) :
    k % 256 ^ w = k' % 256 ^ w ∧ r = s := by
  obtain ⟨h1, h2⟩ := List.append_inj h (by simp [beBytes_length])
  exact ⟨by rw [← fromBE_beBytes, h1, fromBE_beBytes], h2⟩

theorem headInfo_lt (n : Nat) : headInfo n < 28 := by
  unfold headInfo; repeat' (first | omega | split)

theorem headInfo_cases (n : Nat) (hn : n < twoTo64) : (n < 24 ∧ 0 ≤ n ∧ headInfo n = n) ∨
    (24 ≤ n ∧ n < 256 ∧ headInfo n = 24) ∨ (256 ≤ n ∧ n < 65536 ∧ headInfo n = 25) ∨
    (65536 ≤ n ∧ n < 4294967296 ∧ headInfo n = 26) ∨ (4294967296 ≤ n ∧ n < twoTo64 ∧ headInfo n = 27) := by
  unfold headInfo; unfold twoTo64 at *; repeat' (first | omega | split)

theorem headList_prefix {m m' n n' : Nat} {r s : List UInt8} (hm : m < 8) (hm' : m' < 8)
    (hn : n < twoTo64) (hn' : n' < twoTo64) (h : headList m n ++ r = headList m' n' ++ s) :
    m = m' ∧ n = n' ∧ r = s := by
  simp only [headList, List.cons_append, List.cons.injEq] at h
  obtain ⟨h0, h1⟩ := h
  have b0 := congrArg UInt8.toNat h0
  have i1 := headInfo_lt n
  have i2 := headInfo_lt n'
  have : (2 : Nat) ^ 8 = 256 := rfl
  simp only [UInt8.toNat_ofNat', this] at b0
  rw [Nat.mod_eq_of_lt (by omega), Nat.mod_eq_of_lt (by omega)] at b0
  have hmm : m = m' := by omega
  have hi : headInfo n = headInfo n' := by omega
  subst hmm
  have hw : headWidth n = headWidth n' := by unfold headWidth; rw [hi]
  rw [hw] at h1
  obtain ⟨hk, hrs⟩ := beBytes_prefix h1
  refine ⟨rfl, ?_, hrs⟩
  rcases headInfo_cases n hn with ⟨a1, a2, a3⟩ | ⟨a1, a2, a3⟩ | ⟨a1, a2, a3⟩ | ⟨a1, a2, a3⟩ | ⟨a1, a2, a3⟩ <;>
  rcases headInfo_cases n' hn' with ⟨b1, b2, b3⟩ | ⟨b1, b2, b3⟩ | ⟨b1, b2, b3⟩ | ⟨b1, b2, b3⟩ | ⟨b1, b2, b3⟩ <;>
  (try omega) <;>
  (simp [headWidth, b3, widthOf] at hk; unfold twoTo64 at *; omega)

theorem textList_length (t : String) : t.utf8ByteSize ≤ (textList t).length := by
  simp [textList, String.size_toByteArray]

theorem textList_prefix {t t' : String} {r s : List UInt8} (hl : (textList t ++ r).length < twoTo64)
    (h : textList t ++ r = textList t' ++ s) : t = t' ∧ r = s := by
  have hl' : (textList t' ++ s).length < twoTo64 := h ▸ hl
  have a := textList_length t
  have b := textList_length t'
  simp only [List.length_append] at hl hl'
  simp only [textList, List.append_assoc] at h
  obtain ⟨-, hsz, h⟩ := headList_prefix (by omega) (by omega) (by omega) (by omega) h
  obtain ⟨hb, hrs⟩ := List.append_inj h (by simp [String.size_toByteArray, hsz])
  refine ⟨?_, hrs⟩
  apply String.toByteArray_inj.mp
  simp only [String.toUTF8_eq_toByteArray] at hb
  exact ByteArray.ext (Array.toList_inj.mp hb)

/-- The first byte of a value's encoding, as a number. -/
def firstByte (d : Data) : Nat :=
  match listView d with
  | some items => 128 + headInfo items.length
  | none => match d with
    | .natural n => if n < twoTo64 then headInfo n else 64 + headInfo (bigEndianList n).length
    | .boolean b => if b then 245 else 244
    | .label s => 96 + headInfo s.utf8ByteSize
    | .record fields => 160 + headInfo (sortedUnique fields).length
    | .variant _ _ => 131

theorem listView_atom : (∀ n, listView (.natural n) = none) ∧ (∀ b, listView (.boolean b) = none) ∧
    (∀ s, listView (.label s) = none) ∧ (∀ f, listView (.record f) = none) := by
  refine ⟨?_, ?_, ?_, ?_⟩ <;> intros <;> simp [listView, listViewFrom]

theorem encodeList_list {d : Data} {items : List Data} (h : listView d = some items) :
    encodeList d = headList 4 items.length ++ items.flatMap encodeList := by
  rw [encodeList]
  split
  · rename_i h'
    rw [h] at h'; cases h'
    rw [List.flatMap_subtype (g := encodeList) (fun _ _ => rfl), List.unattach_attach]
  · rename_i h'; rw [h] at h'; cases h'

theorem encodeList_variant {label : String} {payload : Data} (h : listView (.variant label payload) = none) :
    encodeList (.variant label payload) = variantPrefix ++ textList label ++ encodeList payload := by
  rw [encodeList]
  split
  · rename_i h'; rw [h] at h'; cases h'
  · rfl

theorem encodeList_record (fields : List (String × Data)) :
    encodeList (.record fields) = headList 5 (sortedUnique fields).length ++
      (sortedUnique fields).flatMap fun p => textList p.1 ++ encodeList p.2 := by
  rw [encodeList]
  split
  · rename_i h'; rw [listView_atom.2.2.2] at h'; cases h'
  · dsimp only
    rw [List.flatMap_subtype (g := fun (p : String × Data) => textList p.1 ++ encodeList p.2) (fun _ _ => rfl),
      List.unattach_attach]

theorem encodeList_natural (n : Nat) : encodeList (.natural n) = naturalList n := by
  rw [encodeList]; split
  · rename_i h'; rw [listView_atom.1] at h'; cases h'
  · rfl

theorem encodeList_boolean (b : Bool) : encodeList (.boolean b) = [if b then 0xf5 else 0xf4] := by
  rw [encodeList]; split
  · rename_i h'; rw [listView_atom.2.1] at h'; cases h'
  · rfl

theorem encodeList_label (t : String) : encodeList (.label t) = textList t := by
  rw [encodeList]; split
  · rename_i h'; rw [listView_atom.2.2.1] at h'; cases h'
  · rfl

theorem headList_cons (m n : Nat) : ∃ rest, headList m n = UInt8.ofNat (32 * m + headInfo n) :: rest :=
  ⟨_, rfl⟩

/-- Every encoding begins with `firstByte`, which is never null's 0xf6. -/
theorem encodeList_first (d : Data) : ∃ rest, encodeList d = UInt8.ofNat (firstByte d) :: rest := by
  cases h : listView d with
  | some items =>
    rw [encodeList_list h]; simp only [firstByte, h]
    exact ⟨_, rfl⟩
  | none =>
    cases d with
    | natural n =>
      rw [encodeList_natural]; simp only [firstByte, h, naturalList]
      split
      · exact ⟨beBytes (headWidth n) n, by simp [headList]⟩
      · exact ⟨_, rfl⟩
    | boolean b =>
      rw [encodeList_boolean]; simp only [firstByte, h]
      cases b
      · exact ⟨[], rfl⟩
      · exact ⟨[], rfl⟩
    | label t => rw [encodeList_label]; simp only [firstByte, h]; exact ⟨_, rfl⟩
    | record f => rw [encodeList_record]; simp only [firstByte, h]; exact ⟨_, rfl⟩
    | variant l p => rw [encodeList_variant h]; simp only [firstByte, h]; exact ⟨_, rfl⟩

theorem firstByte_lt (d : Data) : firstByte d < 246 := by
  unfold firstByte
  cases h : listView d with
  | some items => have := headInfo_lt items.length; simp only; omega
  | none =>
    cases d with
    | natural n =>
      simp only
      split
      · have := headInfo_lt n; omega
      · have := headInfo_lt (bigEndianList n).length; omega
    | boolean b => cases b <;> simp
    | label t => have := headInfo_lt t.utf8ByteSize; simp only; omega
    | record f => have := headInfo_lt (sortedUnique f).length; simp only; omega
    | variant => simp

theorem encodeList_ne_nil (d : Data) : 1 ≤ (encodeList d).length := by
  obtain ⟨rest, h⟩ := encodeList_first d; simp [h]

theorem le_flatMap_length {α : Type} (l : List α) (f : α → List UInt8) (h : ∀ x ∈ l, 1 ≤ (f x).length) :
    l.length ≤ (l.flatMap f).length := by
  induction l with
  | nil => simp
  | cons x l ih =>
    simp only [List.flatMap_cons, List.length_append, List.length_cons]
    have := h x (by simp)
    have := ih (fun y hy => h y (List.mem_cons_of_mem _ hy))
    omega

/-- Two encodings that agree on their first bytes begin with the same byte. -/
theorem firstByte_eq {a b : Data} {r s : List UInt8} (h : encodeList a ++ r = encodeList b ++ s) :
    firstByte a = firstByte b := by
  obtain ⟨x, hx⟩ := encodeList_first a
  obtain ⟨y, hy⟩ := encodeList_first b
  rw [hx, hy] at h
  have := congrArg UInt8.toNat (List.cons.inj h).1
  have : (2 : Nat) ^ 8 = 256 := rfl
  simp only [UInt8.toNat_ofNat', this] at *
  have := firstByte_lt a
  have := firstByte_lt b
  rw [Nat.mod_eq_of_lt (by omega), Nat.mod_eq_of_lt (by omega)] at *
  assumption

theorem normalize_list {d : Data} {items : List Data} (h : listView d = some items) :
    normalize d = listData (items.map normalize).toArray := by
  rw [normalize]
  split
  · rename_i h'; rw [h] at h'; cases h'; rw [List.attach_map_val]
  · rename_i h'; rw [h] at h'; cases h'

theorem normalize_record (fields : List (String × Data)) :
    normalize (.record fields) = .record ((sortedUnique fields).map fun p => (p.1, normalize p.2)) := by
  rw [normalize]
  split
  · rename_i h'; rw [listView_atom.2.2.2] at h'; cases h'
  · dsimp only; rw [List.attach_map_val (f := fun (p : String × Data) => (p.1, normalize p.2))]

theorem normalize_variant {label : String} {payload : Data} (h : listView (.variant label payload) = none) :
    normalize (.variant label payload) = .variant label (normalize payload) := by
  rw [normalize]
  split
  · rename_i h'; rw [h] at h'; cases h'
  · rfl

theorem normalize_atom : (∀ n, normalize (.natural n) = .natural n) ∧ (∀ b, normalize (.boolean b) = .boolean b) ∧
    (∀ t, normalize (.label t) = .label t) := by
  refine ⟨fun n => ?_, fun b => ?_, fun t => ?_⟩ <;> rw [normalize] <;> split <;>
    first | rfl | (rename_i h'; simp [listView, listViewFrom] at h')

theorem items_prefix (la lb : List Data)
    (P : ∀ x ∈ la, ∀ (y : Data) (r s : List UInt8), encodeList x ++ r = encodeList y ++ s →
      (encodeList x ++ r).length < twoTo64 → normalize x = normalize y ∧ r = s)
    (hl : la.length = lb.length) (r s : List UInt8) (h : la.flatMap encodeList ++ r = lb.flatMap encodeList ++ s)
    (fits : (la.flatMap encodeList ++ r).length < twoTo64) :
    la.map normalize = lb.map normalize ∧ r = s := by
  induction la generalizing lb r s with
  | nil => cases lb with
    | nil => simpa using h
    | cons => simp at hl
  | cons x la ih => cases lb with
    | nil => simp at hl
    | cons y lb =>
      simp only [List.flatMap_cons, List.append_assoc] at h fits
      obtain ⟨hx, hrest⟩ := P x (by simp) y _ _ h fits
      obtain ⟨hm, hrs⟩ := ih lb (fun x hx => P x (List.mem_cons_of_mem _ hx)) (by simpa using hl) r s hrest
        (by simp only [List.length_append] at fits ⊢; omega)
      simp [hx, hm, hrs]

theorem fields_prefix (fa fb : List (String × Data))
    (P : ∀ p ∈ fa, ∀ (y : Data) (r s : List UInt8), encodeList p.2 ++ r = encodeList y ++ s →
      (encodeList p.2 ++ r).length < twoTo64 → normalize p.2 = normalize y ∧ r = s)
    (hl : fa.length = fb.length) (r s : List UInt8)
    (h : fa.flatMap (fun p => textList p.1 ++ encodeList p.2) ++ r = fb.flatMap (fun p => textList p.1 ++ encodeList p.2) ++ s)
    (fits : (fa.flatMap (fun p => textList p.1 ++ encodeList p.2) ++ r).length < twoTo64) :
    fa.map (fun p => (p.1, normalize p.2)) = fb.map (fun p => (p.1, normalize p.2)) ∧ r = s := by
  induction fa generalizing fb r s with
  | nil => cases fb with
    | nil => simpa using h
    | cons => simp at hl
  | cons x fa ih => cases fb with
    | nil => simp at hl
    | cons y fb =>
      simp only [List.flatMap_cons, List.append_assoc] at h fits
      obtain ⟨hk, h⟩ := textList_prefix fits h
      obtain ⟨hx, hrest⟩ := P x (by simp) y.2 _ _ h (by simp only [List.length_append] at fits ⊢; omega)
      obtain ⟨hm, hrs⟩ := ih fb (fun x hx => P x (List.mem_cons_of_mem _ hx)) (by simpa using hl) r s hrest
        (by simp only [List.length_append] at fits ⊢; omega)
      simp [hk, hx, hm, hrs]

theorem firstByte_list {d : Data} {items : List Data} (h : listView d = some items) :
    firstByte d = 128 + headInfo items.length := by
  simp [firstByte, h]

/-- Where each kind of value's first byte lies: the majors are disjoint, but for a list of three
items and a variant, whose second bytes differ instead. -/
theorem firstByte_range (d : Data) (h : listView d = none) : match d with
    | .natural _ => firstByte d < 28 ∨ (64 ≤ firstByte d ∧ firstByte d < 92)
    | .boolean _ => 244 ≤ firstByte d
    | .label _ => 96 ≤ firstByte d ∧ firstByte d < 124
    | .record _ => 160 ≤ firstByte d ∧ firstByte d < 188
    | .variant _ _ => firstByte d = 131 := by
  cases d with
  | natural n =>
    simp only [firstByte, h]
    split
    · have := headInfo_lt n; omega
    · have := headInfo_lt (bigEndianList n).length; omega
  | boolean b => simp only [firstByte, h]; cases b <;> simp
  | label t => simp only [firstByte, h]; have := headInfo_lt t.utf8ByteSize; omega
  | record f => simp only [firstByte, h]; have := headInfo_lt (sortedUnique f).length; omega
  | variant => simp only [firstByte, h]

/-- A list of three items is not a variant: its second byte is its first item's, never null. -/
theorem list_not_variant {d : Data} {items : List Data} {l : String} {p : Data} {r s : List UInt8}
    (ha : listView d = some items) (hb : listView (.variant l p) = none)
    (h : encodeList d ++ r = encodeList (.variant l p) ++ s) : False := by
  have fb := firstByte_eq h
  rw [firstByte_list ha, (firstByte_range _ hb : firstByte (.variant l p) = 131)] at fb
  have l3 : items.length = 3 := by
    have := headInfo_cases items.length
    unfold headInfo at fb; revert fb; repeat' (first | omega | split)
  match items, l3 with
  | [x, y, z], _ =>
    rw [encodeList_list ha, encodeList_variant hb] at h
    have e : headList 4 [x, y, z].length = [0x83] := rfl
    obtain ⟨rest, hx⟩ := encodeList_first x
    rw [e] at h
    simp only [List.flatMap_cons, hx, variantPrefix, List.cons_append, List.nil_append, List.append_assoc] at h
    have h2 := congrArg UInt8.toNat (List.cons.inj (List.cons.inj h).2).1
    have := firstByte_lt x
    have e8 : (2 : Nat) ^ 8 = 256 := rfl
    simp only [UInt8.toNat_ofNat', e8] at h2
    rw [Nat.mod_eq_of_lt (by omega)] at h2
    simp at h2
    omega

/-- The prefix property: an encoding followed by anything determines its value (up to `normalize`)
and where it ends. -/
theorem encodeList_prefix (a : Data) : ∀ (b : Data) (r s : List UInt8), encodeList a ++ r = encodeList b ++ s →
    (encodeList a ++ r).length < twoTo64 → normalize a = normalize b ∧ r = s := by
  intro b r s h fits
  have fits' : (encodeList b ++ s).length < twoTo64 := h ▸ fits
  have fb := firstByte_eq h
  cases ha : listView a with
  | some la =>
    have lena : la.length < twoTo64 := by
      have := le_flatMap_length la encodeList (fun x _ => encodeList_ne_nil x)
      rw [encodeList_list ha] at fits; simp only [List.length_append] at fits; omega
    cases hb : listView b with
    | some lb =>
      have lenb : lb.length < twoTo64 := by
        have := le_flatMap_length lb encodeList (fun x _ => encodeList_ne_nil x)
        rw [encodeList_list hb] at fits'; simp only [List.length_append] at fits'; omega
      rw [encodeList_list ha, encodeList_list hb, List.append_assoc, List.append_assoc] at h
      obtain ⟨-, hlen, h⟩ := headList_prefix (by omega) (by omega) lena lenb h
      rw [encodeList_list ha, List.append_assoc] at fits
      obtain ⟨hm, hrs⟩ := items_prefix la lb (fun x hx => encodeList_prefix x) hlen r s h
        (by simp only [List.length_append] at fits ⊢; omega)
      rw [normalize_list ha, normalize_list hb, hm]
      exact ⟨rfl, hrs⟩
    | none =>
      exfalso
      cases b with
      | variant l p => exact list_not_variant ha hb h
      | _ =>
        have rb := firstByte_range _ hb
        simp only at rb
        rw [firstByte_list ha] at fb
        have := headInfo_lt la.length
        omega
  | none =>
    cases hb : listView b with
    | some lb =>
      exfalso
      cases a with
      | variant l p => exact list_not_variant hb ha h.symm
      | _ =>
        have ra := firstByte_range _ ha
        simp only at ra
        rw [firstByte_list hb] at fb
        have := headInfo_lt lb.length
        omega
    | none =>
      have ra := firstByte_range _ ha
      have rb := firstByte_range _ hb
      cases a <;> cases b <;> simp only at ra rb
      all_goals first
        | (exfalso; omega)
        | skip
      case natural.natural n n' =>
        rw [encodeList_natural, encodeList_natural] at h
        rw [encodeList_natural] at fits; rw [encodeList_natural] at fits'
        rw [normalize_atom.1, normalize_atom.1]
        simp only [firstByte, ha, hb] at fb
        unfold naturalList at h fits fits'
        by_cases c1 : n < twoTo64 <;> by_cases c2 : n' < twoTo64 <;>
          simp only [c1, c2, ↓reduceIte] at h fits fits' fb
        · obtain ⟨-, e, hrs⟩ := headList_prefix (by omega) (by omega) c1 c2 h
          exact ⟨by rw [e], hrs⟩
        · exfalso; have := headInfo_lt n; have := headInfo_lt (bigEndianList n').length; omega
        · exfalso; have := headInfo_lt n'; have := headInfo_lt (bigEndianList n).length; omega
        · rw [List.append_assoc, List.append_assoc] at h
          simp only [List.length_append] at fits fits'
          obtain ⟨-, e, h⟩ := headList_prefix (by omega) (by omega) (by omega) (by omega) h
          obtain ⟨hb, hrs⟩ := List.append_inj h e
          refine ⟨?_, hrs⟩
          rw [← fromBE_bigEndianList n, ← fromBE_bigEndianList n', hb]
      case boolean.boolean x y =>
        rw [encodeList_boolean, encodeList_boolean] at h
        rw [normalize_atom.2.1, normalize_atom.2.1]
        cases x <;> cases y <;> simp_all
      case label.label t t' =>
        rw [encodeList_label, encodeList_label] at h
        rw [encodeList_label] at fits
        obtain ⟨e, hrs⟩ := textList_prefix fits h
        rw [normalize_atom.2.2, normalize_atom.2.2, e]
        exact ⟨rfl, hrs⟩
      case record.record fa fb' =>
        rw [encodeList_record, encodeList_record, List.append_assoc, List.append_assoc] at h
        rw [encodeList_record, List.append_assoc] at fits
        rw [encodeList_record, List.append_assoc] at fits'
        have la := le_flatMap_length (sortedUnique fa) (fun p => textList p.1 ++ encodeList p.2)
          (fun p _ => by simp only [List.length_append]; have := encodeList_ne_nil p.2; omega)
        have lb := le_flatMap_length (sortedUnique fb') (fun p => textList p.1 ++ encodeList p.2)
          (fun p _ => by simp only [List.length_append]; have := encodeList_ne_nil p.2; omega)
        simp only [List.length_append] at fits fits'
        obtain ⟨-, hlen, h⟩ := headList_prefix (by omega) (by omega) (by omega) (by omega) h
        obtain ⟨hm, hrs⟩ := fields_prefix (sortedUnique fa) (sortedUnique fb')
          (fun p _ => encodeList_prefix p.2) hlen r s h (by simp only [List.length_append]; omega)
        rw [normalize_record, normalize_record, hm]
        exact ⟨rfl, hrs⟩
      case variant.variant l p l' p' =>
        rw [encodeList_variant ha, encodeList_variant hb] at h
        rw [encodeList_variant ha] at fits
        simp only [variantPrefix, List.append_assoc, List.cons_append, List.nil_append] at h fits
        have h := (List.cons.inj (List.cons.inj h).2).2
        simp only [List.length_cons] at fits
        obtain ⟨e, h⟩ := textList_prefix (by simp only [List.length_append] at fits ⊢; omega) h
        obtain ⟨hp, hrs⟩ := encodeList_prefix p p' r s h (by simp only [List.length_append] at fits ⊢; omega)
        rw [normalize_variant ha, normalize_variant hb, e, hp]
        exact ⟨rfl, hrs⟩
termination_by sizeOf a
decreasing_by
  all_goals (try subst_vars); first
    | exact listView_mem (by assumption) (by assumption)
    | exact sortedUnique_value_size (by assumption)
    | (simp; omega)

/-- **The canonical encoding is injective**: values with the same canonical bytes are the same
value, up to record field order and repeated fields (`normalize`). A variant is told from a record,
and a list from a variant, by the bytes alone (review 2026-10-12, kernel 1). -/
theorem encode_injective {a b : Data} (h : encode a = encode b) (fits : (encode a).size < twoTo64) :
    normalize a = normalize b := by
  have h' : encodeList a ++ [] = encodeList b ++ [] := by rw [← encode_data, ← encode_data, h]
  refine (encodeList_prefix a b [] [] h' ?_).1
  rw [← encode_data]; simpa using fits

#assert_axioms writeData_spec encode_injective

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

/-- A head's argument at `pos` (after the initial byte), and the position after it. -/
def readArg (b : ByteArray) (pos info : Nat) : Except String (Nat × Nat) := do
  let be := fun (width : Nat) => do
    if pos + width > b.size then throw "truncated canonical bytes"
    return ((List.range width).foldl (fun acc i => acc * 256 + (b.get! (pos + i)).toNat) 0, pos + width)
  if info < 24 then return (info, pos)
  else if info == 24 then be 1
  else if info == 25 then be 2
  else if info == 26 then be 4
  else if info == 27 then be 8
  else throw "an indefinite or reserved length"

/-- The JSON `writeJson` wrote, read back from `pos`: unsigned and negative integers, big naturals
(byte strings), text, arrays, maps with text keys, true, false, null. -/
partial def readJson (b : ByteArray) (pos depth : Nat) : Except String (Json × Nat) := do
  if depth == 0 then throw "nesting capacity"
  if pos ≥ b.size then throw "truncated canonical bytes"
  let ib := (b.get! pos).toNat
  let major := ib / 32
  let info := ib % 32
  if major == 7 then
    if info == 20 then return (Json.bool false, pos + 1)
    else if info == 21 then return (Json.bool true, pos + 1)
    else if info == 22 then return (Json.null, pos + 1)
    else throw "a simple value outside JSON"
  let (n, p) ← readArg b (pos + 1) info
  match major with
  | 0 => return (toJson n, p)
  | 1 => return (toJson (-(Int.ofNat n) - 1), p)
  | 2 =>
    if p + n > b.size then throw "truncated canonical bytes"
    return (toJson ((b.extract p (p + n)).foldl (fun acc x => acc * 256 + x.toNat) 0), p + n)
  | 3 =>
    if p + n > b.size then throw "truncated canonical bytes"
    let some s := String.fromUTF8? (b.extract p (p + n)) | throw "text is not UTF-8"
    return (Json.str s, p + n)
  | 4 =>
    let mut items : Array Json := #[]
    let mut at_ := p
    for _ in [0:n] do
      let (j, q) ← readJson b at_ (depth - 1)
      items := items.push j
      at_ := q
    return (Json.arr items, at_)
  | 5 =>
    let mut fields : Array (String × Json) := #[]
    let mut at_ := p
    for _ in [0:n] do
      let (k, q) ← readJson b at_ (depth - 1)
      let .str key := k | throw "a map key is not text"
      let (v, r) ← readJson b q (depth - 1)
      fields := fields.push (key, v)
      at_ := r
    return (Json.mkObj fields.toList, at_)
  | _ => throw "a CBOR item outside JSON"

/-- `encodeJson`'s inverse over its whole input. -/
def decodeJson (b : ByteArray) (depth : Nat) : Except String Json := do
  let (j, p) ← readJson b 0 depth
  unless p == b.size do throw "trailing bytes"
  return j

/-! ## Identity -/

def digestBytes (message : ByteArray) : ByteArray :=
  ByteArray.mk ((Delvetalk.Compiler.Sha256.digest message).toList.flatMap fun w =>
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
      if n == 3 && r.bytes[r.pos]! == 0xf6 then
        -- [null, label, payload]: a variant (`variantPrefix`)
        set { r with pos := r.pos + 1 }
        count
        let (km, kn) ← readHead
        if km != 3 then throw "CBOR variant label is not text"
        if kn > Bounds.bytesMax then throw "CBOR exceeds the byte bound"
        let label ← utf8 (← takeBytes kn)
        let v := Data.variant label (← readItem (depth - 1))
        if (listView v).isSome then throw "non-canonical CBOR: a list is an array, not a variant"
        return v
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

-- Decoding is `normalize`, and a variant comes back a variant, whatever its label.
#guard [Data.variant "x" (.natural 1), .record [("x", .natural 1)], .variant "ok" (.record []),
    .variant "nil" (.record [("x", .natural 1)]), .variant "cons" (.record [("head", .natural 1), ("tail", .natural 2)]),
    listData #[.variant "some" (.label "a"), .record [("b", .boolean true), ("a", .natural 300)]]].all fun d =>
  match decode (encode d) with
  | .ok back => encode back == encode d && (repr back).pretty == (repr (normalize d)).pretty
  | .error _ => false
-- A list written as a variant is not canonical.
#guard (decode ⟨#[0x83, 0xf6, 0x63, 0x6e, 0x69, 0x6c, 0xa0]⟩).toOption.isNone

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

open Delvetalk.Compiler.ObjectiveBendDataWire (decodeData dataJson)

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
