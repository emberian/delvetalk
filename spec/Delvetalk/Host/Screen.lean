/- The automatic moderation's pure half (docs/ROOT.md §2.4): a text's key, the wordlist that acts at once, and the
   redaction every public projection passes through. What the host journals and the ops are `Moderation.lean`;
   the index is `World.screened`, derived by `Ops.recordActs` from `screen` entries.

   A screened text is named by its key, the CID of the text as canonical data, so a restore or a confirm names it
   without the bytes again; the first `screen` entry of a text carries the bytes once, and its public projection
   elides them (`Ops.projectEntry`). -/
import Delvetalk.Host.Journal

namespace Delvetalk.Host.Screen
open Lean (Json toJson)
open Delvetalk.Host

/-- What every public surface shows in place of a hidden text. -/
def placeholder : String := "[hidden by moderation]"

/-- A text's key: the CID of its canonical bytes as a string. -/
def textKey (text : String) : String := Journal.bodyHash (toJson text)

/-- The states of a screened text: `hidden` (shown nowhere public), `review` (a low-confidence flag, hidden from
    nothing, waiting for the owner), `confirmed` (the owner kept it hidden), `restored` (the owner showed it again; a
    text restored is never screened again). -/
def states : List String := ["hidden", "review", "confirmed", "restored"]

def stateOf (item : Json) : String := (item.getObjValAs? String "state").toOption.getD ""

/-- Whether a screened text is kept from every public projection. -/
def masks (item : Json) : Bool := ["hidden", "confirmed"].contains (stateOf item)

/-- The texts `w` keeps from public projections, longest first (a longer hidden text that contains a shorter one is
    replaced whole). -/
def maskedTexts (w : World) : Array String :=
  (w.screened.fold (fun acc _ item =>
    if masks item then match item.getObjValAs? String "text" with
      | .ok t => if t.isEmpty then acc else acc.push t
      | .error _ => acc
    else acc) (#[] : Array String)).qsort (fun (a b : String) => a.utf8ByteSize > b.utf8ByteSize)

def wordChar (c : Char) : Bool := c.isAlphanum || c == '_'

/-- A short one-word text (a name, a single slur) is replaced only where it stands as a word, so a hidden `ass` leaves
    `class` alone; any other text wherever it occurs (a sentence; a text in a script written without spaces). -/
def needsBoundary (m : String) : Bool :=
  m.utf8ByteSize < 16 && !(m.toList.any Char.isWhitespace) && m.toList.all (fun (c : Char) => c.toNat < 128)

/-- `s` with every occurrence of `m` replaced by the placeholder (`needsBoundary`: only where it stands as a word). -/
def replaceText (s m : String) : String :=
  let parts := if m.isEmpty then [s] else s.splitOn m
  if parts.length ≤ 1 then s else
  let bounded := needsBoundary m
  Id.run do
    let mut out := parts.head!
    let mut prev := parts.head!
    for p in parts.tail! do
      let before := prev.back
      let after := p.front
      let isWord := bounded && ((!prev.isEmpty && wordChar before) || (!p.isEmpty && wordChar after))
      out := out ++ (if isWord then m else placeholder) ++ p
      prev := p
    return out

/-- `s` with every hidden text replaced. -/
def redactWith (texts : Array String) (s : String) : String :=
  texts.foldl (fun acc m => if acc.utf8ByteSize < m.utf8ByteSize then acc else replaceText acc m) s

/-- A reply with every string redacted, keys left alone (they are field names, ids and hashes, never residents'
    words). -/
partial def redactJson (texts : Array String) : Json → Json
  | .str s => .str (redactWith texts s)
  | .arr a => .arr (a.map (redactJson texts))
  | j@(.obj _) => Json.mkObj (((j.getObj?.toOption.map (·.toList)).getD []).map fun (k, v) => (k, redactJson texts v))
  | j => j

/-- `w`'s public text redaction (the identity when nothing is hidden). -/
def redact (w : World) (s : String) : String :=
  let texts := maskedTexts w
  if texts.isEmpty then s else redactWith texts s

/-! ## The wordlist: the unmistakable worst, acting before any model reads the text

Kept to words whose every use in this town would be a slur or sexual content involving children. Words with innocent
or reclaimed uses (`chink` of light, `fag` for a cigarette, `coon`, casual profanity) are the model's to judge, never
the list's: the list errs toward missing, never toward hiding a dark story. -/

/-- A token as the list reads it: lower case, the usual digit and symbol stand-ins read as letters. -/
def fold (c : Char) : Char :=
  match c.toLower with
  | '0' => 'o' | '1' => 'i' | '3' => 'e' | '4' => 'a' | '5' => 's' | '7' => 't' | '@' => 'a' | '$' => 's' | '!' => 'i'
  | c => c

/-- (stem, whole word only, category). A stem that is not whole-word-only also matches a word it begins. -/
def wordlist : List (String × Bool × String) :=
  [("nigger", false, "hate"), ("niggaz", true, "hate"), ("kike", false, "hate"), ("faggot", false, "hate"),
   ("wetback", false, "hate"), ("raghead", false, "hate"), ("towelhead", false, "hate"), ("spic", true, "hate"),
   ("spics", true, "hate"), ("gook", true, "hate"), ("gooks", true, "hate"), ("beaner", true, "hate"),
   ("beaners", true, "hate"), ("childporn", false, "sexual-minors"), ("kiddieporn", false, "sexual-minors"),
   ("kiddyporn", false, "sexual-minors")]

/-- Two-word phrases read as one word (`child porn` as `childporn`). -/
def joined : List (String × String) := [("child", "porn"), ("kiddie", "porn"), ("kiddy", "porn")]

/-- The text's words as the list reads them; a run of single letters (`n i g g e r`) is also read as one word. -/
def tokens (text : String) : List String := Id.run do
  let folded := text.toList.map fold
  let mut words : Array String := #[]
  let mut cur := ""
  for c in folded do
    if c.isAlphanum then cur := cur.push c
    else
      unless cur.isEmpty do words := words.push cur
      cur := ""
  unless cur.isEmpty do words := words.push cur
  let mut out := words.toList
  -- runs of single letters, joined
  let mut run := ""
  for w in words do
    if w.length == 1 then run := run ++ w
    else
      if run.length > 2 then out := out ++ [run]
      run := ""
  if run.length > 2 then out := out ++ [run]
  -- adjacent pairs a phrase names
  for (a, b) in words.toList.zip (words.toList.drop 1) do
    if joined.contains (a, b) then out := out ++ [a ++ b]
  return out

/-- The category the wordlist finds in `text`, if any. -/
def prefilter (text : String) : Option String :=
  (tokens text).findSome? fun t => (wordlist.find? fun (stem, whole, _) =>
    if whole then t == stem else t.startsWith stem).map (·.2.2)

end Delvetalk.Host.Screen
