/- The append-only chain. An entry is a JSON object whose `hash` is the CID of its
   canonical DAG-CBOR bytes without that field (Canonical.lean), and whose `previous`
   is the previous entry's `hash`. The field names are unchanged; the values are CIDs,
   so an entry can be published verbatim as a record and cited by that CID. -/
import Delvetalk.Host.Store
import Delvetalk.Canonical

namespace Delvetalk.Host.Journal
open Lean (Json toJson)

/-- The CID of `body`'s canonical bytes. -/
def bodyHash (body : Json) : String := Delvetalk.Canonical.cidJson body

/-- `fields` must not include `height`, `previous` or `hash`. -/
def sealEntry (height : Nat) (previous : String) (fields : List (String × Json)) : Json :=
  let body := Json.mkObj ([("height", toJson height), ("previous", toJson previous)] ++ fields)
  body.setObjVal! "hash" (toJson (bodyHash body))

/-- Check one entry's hash, chain link and height; the error names the height. -/
def verify (height : Nat) (previous : String) (entry : Json) : Except String Unit := do
  let fail {α : Type} (what : String) : Except String α := throw s!"journal broken at height {height}: {what}"
  let some fields := entry.getObj?.toOption | fail "entry is not an object"
  let hash ← match entry.getObjValAs? String "hash" with
    | .ok h => pure h
    | .error _ => fail "missing hash"
  let body := Json.mkObj (fields.toList.filter (·.1 != "hash"))
  if bodyHash body != hash then fail "hash mismatch"
  match entry.getObjValAs? Nat "height" with
  | .ok h => if h != height then fail "height out of sequence"
  | .error _ => fail "missing height"
  match entry.getObjValAs? String "previous" with
  | .ok p => if p != previous then fail "previous hash does not chain"
  | .error _ => fail "missing previous"

end Delvetalk.Host.Journal
