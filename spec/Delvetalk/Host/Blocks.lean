/- The block store: every journal entry is a canonical record (the DAG-CBOR of the entry without its
   `hash`) under its CID, appended to `<journal>.blocks`; the journal file itself is the ordered chain,
   one line per entry naming its height, the previous entry's CID, its own and where its record lies
   (`{height, previous, hash, at, bytes}`). A world holds the chain and reads a record only when asked
   (`Entries.get?`), so what stays in memory is the live state and its indexes, not the journal. -/
import Delvetalk.Canonical
import Lean.Data.PersistentArray
import Lean.Data.PersistentHashMap
import Std.Data.HashMap

namespace Delvetalk.Host
open Lean (Json toJson)

/-- `pread` of `length` bytes at `offset` (`spec/native/sync.c`). -/
@[extern "delvetalk_handle_pread"]
opaque preadHandle (handle : @& IO.FS.Handle) (offset length : UInt64) : IO ByteArray

/-- The bytes a record occupies. The store is append-only and every record is named by the CID of
    its bytes, so what lies at an offset already written never changes: the read is a function of its
    arguments, and a failed read is `none`. -/
unsafe def readAtImpl (handle : IO.FS.Handle) (offset length : Nat) : Option ByteArray :=
  match unsafeBaseIO (preadHandle handle offset.toUInt64 length.toUInt64).toBaseIO with
  | .ok b => if b.size == length then some b else none
  | .error _ => none

@[implemented_by readAtImpl]
opaque readAt (handle : IO.FS.Handle) (offset length : Nat) : Option ByteArray

/-- One chain line: the entry at `height` names `previous`, is `hash`, and its record is the `bytes`
    bytes at `offset` in the block store (the line's `at`). -/
structure Link where
  height : Nat
  previous : String
  hash : String
  offset : Nat
  bytes : Nat

def Link.json (l : Link) : Json :=
  Json.mkObj [("height", toJson l.height), ("previous", toJson l.previous), ("hash", toJson l.hash),
    ("at", toJson l.offset), ("bytes", toJson l.bytes)]

/-- The link an entry whose record is `bytes` bytes at `offset` makes. -/
def Link.of (entry : Json) (offset bytes : Nat) : Link :=
  { height := (entry.getObjValAs? Nat "height").toOption.getD 0
    previous := (entry.getObjValAs? String "previous").toOption.getD ""
    hash := (entry.getObjValAs? String "hash").toOption.getD ""
    offset, bytes }

/-- A chain line read without building JSON: a flat object of five fields whose values are naturals
    or CIDs (no comma, colon or escape in any of them), in any order. -/
def Link.ofLine (line : String) : Option Link := do
  let bare := fun (s : String) (c : Char) => ((s.dropWhile (· == c)).dropEndWhile (· == c)).toString
  let fields ← ((bare (bare line '{') '}').splitOn ",").mapM fun kv => match kv.splitOn ":" with
    | [k, v] => some (bare k '"', bare v '"')
    | _ => none
  unless fields.length == 5 do none
  let text := fun (k : String) => fields.lookup k
  let nat := fun (k : String) => (fields.lookup k).bind String.toNat?
  return { height := ← nat "height", previous := ← text "previous", hash := ← text "hash", offset := ← nat "at", bytes := ← nat "bytes" }

/-- The canonical record of an entry: its bytes without `hash`, whose CID is the `hash`. -/
def recordBytes (entry : Json) : Except String ByteArray :=
  Delvetalk.Canonical.encodeJson (Json.mkObj (((entry.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "hash")))

/-- The entry a record holds, its `hash` restored. -/
def entryOfRecord (bytes : ByteArray) (hash : String) (depth : Nat) : Except String Json := do
  return (← Delvetalk.Canonical.decodeJson bytes depth).setObjVal! "hash" (toJson hash)

/-- A world's journal: every entry's CID in height order (entry `h` at index `h - 1`), where each
    record lies in the store, and the entries a step made that are not yet written (`fresh`, the
    last ones). `count` is how many this world holds: a replay holds a prefix of the store it reads.
    The chain is persistent (`PersistentArray`, `PersistentHashMap`): a step extends the world the
    session still holds, so a flat array would be copied whole on every append. -/
structure Entries where
  store : Option IO.FS.Handle := none
  hashes : Lean.PersistentArray String := {}
  spans : Lean.PersistentArray (Nat × Nat) := {}
  fresh : Array Json := #[]
  byHash : Lean.PersistentHashMap String Nat := {}
  count : Nat := 0
  /-- The nesting bound a record is decoded under (`Limits.dataDepth`). -/
  depth : Nat := 8192

instance : Inhabited Entries := ⟨{}⟩

/-- The record bytes the process keeps decoded (`recordMemo`), at most. -/
def recordMemoBytes : Nat := 64 * 1024 * 1024

/-- Stored entries this process has read, verified and decoded, by CID and decoding depth, with the
    bytes of their records: a record is immutable and named by its CID, so it is checked once
    (`stateCidAt`, `stateAt`, a source or block lookup each walk an object's entries again).
    A constant, not an `initialize`, as the other memos of modules with `#guard`s. -/
@[noinline] unsafe def recordMemo : IO.Ref (Std.HashMap String (Json × Nat) × Nat) :=
  unsafeBaseIO (IO.mkRef ({}, 0))

/-- The entry a stored record holds, when its bytes are its CID's; none otherwise. -/
def storedEntryCold (handle : IO.FS.Handle) (offset length : Nat) (hash : String) (depth : Nat) : Option Json := do
  let bytes ← readAt handle offset length
  if Delvetalk.Canonical.cid bytes != hash then none
  (entryOfRecord bytes hash depth).toOption

unsafe def storedEntryImpl (handle : IO.FS.Handle) (offset length : Nat) (hash : String) (depth : Nat) : Option Json :=
  unsafeBaseIO do
    let key := s!"{depth}/{hash}"
    if let some (j, _) := (← recordMemo.get).1[key]? then return some j
    let some j := storedEntryCold handle offset length hash depth | return none
    recordMemo.modify fun (m, bytes) => Id.run do
      if m.contains key || length > recordMemoBytes then return (m, bytes)
      let mut m := m
      let mut bytes := bytes
      -- Room for this record: drop others until it fits.
      while bytes + length > recordMemoBytes do
        match m.fold (init := none) fun (acc : Option (String × Nat)) k (_, n) => acc <|> some (k, n) with
        | some (k, n) => m := m.erase k; bytes := bytes - n
        | none => break
      return (m.insert key (j, length), bytes + length)
    return some j

/-- `storedEntryCold`, verified and decoded once per process for a CID. -/
@[implemented_by storedEntryImpl]
def storedEntry (handle : IO.FS.Handle) (offset length : Nat) (hash : String) (depth : Nat) : Option Json :=
  storedEntryCold handle offset length hash depth

namespace Entries

/-- The entry at index `i` (height `i + 1`), read from the store (none unless its record is its CID's)
    or from what this step made. -/
def get? (e : Entries) (i : Nat) : Option Json :=
  if i ≥ e.count then none
  else if i < e.spans.size then do
    let (offset, length) := e.spans.get! i
    storedEntry (← e.store) offset length (e.hashes.get! i) e.depth
  else e.fresh[i - e.spans.size]?

def getD (e : Entries) (i : Nat) : Json := (e.get? i).getD Json.null

def hashAt? (e : Entries) (i : Nat) : Option String := if i < e.count then some (e.hashes.get! i) else none

/-- The index of the entry whose CID is `hash`. -/
def indexOf? (e : Entries) (hash : String) : Option Nat :=
  (e.byHash.find? hash).bind fun i => if i < e.count then some i else none

/-- The first `n` entries: the same store and arrays, fewer held. -/
def upTo (e : Entries) (n : Nat) : Entries := { e with count := min n e.hashes.size }

/-- Append an entry a step made, dropping any the store holds past `count` (a prefix extended). -/
def push (e : Entries) (entry : Json) : Entries :=
  let hash := (entry.getObjValAs? String "hash").toOption.getD ""
  let e := if e.count == e.hashes.size then e else Id.run do
    let mut e := e
    while e.hashes.size > e.count do
      e := { e with byHash := e.byHash.erase (e.hashes.get! (e.hashes.size - 1)), hashes := e.hashes.pop }
    while e.spans.size > e.count do e := { e with spans := e.spans.pop }
    return { e with fresh := e.fresh.extract 0 (e.count - e.spans.size) }
  { e with hashes := e.hashes.push hash, fresh := e.fresh.push entry, byHash := e.byHash.insert hash e.count,
           count := e.count + 1 }

/-- An entry the store already holds at `span`, appended to the chain (opening, migrating). -/
def pushStored (e : Entries) (hash : String) (span : Nat × Nat) : Entries :=
  { e with hashes := e.hashes.push hash, spans := e.spans.push span, byHash := e.byHash.insert hash e.count,
           count := e.count + 1 }

/-- The entries not yet in the store, from height `stored + 1`. -/
def unwritten (e : Entries) : Array Json := e.fresh

/-- The unwritten entries are now in the store at `spans`. -/
def written (e : Entries) (spans : Array (Nat × Nat)) : Entries :=
  { e with spans := spans.foldl (·.push ·) e.spans, fresh := #[] }

/-- Entries held in memory only, none in a store (an offline tool's journal before it is written). -/
def ofArray (entries : Array Json) : Entries := entries.foldl push {}

/-- Every held entry, in height order, one read at a time. -/
def foldl {α : Type} (e : Entries) (f : α → Nat → Json → α) (init : α) : α := Id.run do
  let mut acc := init
  for i in [0:e.count] do
    if let some entry := e.get? i then acc := f acc i entry
  return acc

end Entries

end Delvetalk.Host
