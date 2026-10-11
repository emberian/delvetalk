/- `delvetalk-obend root-edit` (docs/ROOT.md §1.5): what cannot be journaled, done to a closed journal.
   A new file every time, the old kept; the first re-sealed entry carries `rootEdit {command, reason,
   oldHead, at}` inside its hash; the old-to-new hash table and the count of slugs changed printed; the
   new journal replayed in full before it is written.

   Re-sealing carries what replay checks (HOST-HANDOFF §7 item 1): every `previous` and `hash` from the
   edit on (entry 1 keeps `replay`; a fork's genesis keeps the `previous` it was forked from); an entry's
   `turn` that was its height becomes its new height; an `ended` id hashes the height, so it is
   recomputed, and the ids that hash an identity whose intent was such an id (sends, changes,
   publishes, interpretations) with it; every later string naming an old entry hash or an old id
   (`resumes`, `delivery.id`, `identity.intent`, a slot's intent) is rewritten through the tables; a
   root `ignore`'s height follows its entry. Snapshots past the edit are not copied. -/
import Delvetalk.Host.Snapshot

namespace Delvetalk.Host.RootEdit
open Lean (Json toJson)

abbrev Fields := List (String × Json)

def fieldsOf (entry : Json) : Fields :=
  ((entry.getObj?.toOption.map (·.toList)).getD []).filter fun (k, _) => k != "hash" && k != "height" && k != "previous"

def lookup (fs : Fields) (k : String) : Option Json := (fs.find? (·.1 == k)).map (·.2)

def put (fs : Fields) (k : String) (v : Json) : Fields :=
  if fs.any (·.1 == k) then fs.map fun (k', v') => if k' == k then (k, v) else (k', v') else fs ++ [(k, v)]

def erase (fs : Fields) (k : String) : Fields := fs.filter (·.1 != k)

/-- Every string equal to a key of `m`, anywhere in `j`, replaced by its value. -/
partial def subst (m : Std.HashMap String String) : Json → Json
  | .str s => .str (m.getD s s)
  | .arr a => .arr (a.map (subst m))
  | .obj kvs => Json.mkObj (kvs.toList.map fun (k, v) => (k, subst m v))
  | j => j

/-- The hashed id an identity's `n`th item of a kind carries, by the host's formulas. -/
def idOf (kind : String) (principal intent : String) (n : Nat) : String :=
  match kind with
  | "delivery" => deliveryId principal intent n
  | "publish" => Journal.bodyHash (Json.arr #[toJson "publish", toJson principal, toJson intent, toJson n])
  | _ => Journal.bodyHash (Json.arr #[toJson principal, toJson intent, toJson n])

/-- What a command keeps and what it re-seals: entries 1..`kept` as they are, then `rest`, each with
    its old height (none for an inserted entry). -/
structure Edit where
  kept : Nat
  rest : Array (Fields × Option Nat)
  command : Json

structure Sealed where
  entries : Array Json
  /-- Old height, old hash, new height, new hash, for every re-sealed entry that had one. -/
  table : Array (Nat × String × Nat × String)

/-- Re-seal `e.rest` after the kept prefix of `old`, the marker inside the first. -/
def reseal (old : Array Json) (e : Edit) (marker : Json) : Except String Sealed := do
  let firstPrevious := ((old[0]?).bind fun x => (x.getObjValAs? String "previous").toOption).getD Limits.genesis
  let mut prev := if e.kept == 0 then firstPrevious else ((old[e.kept - 1]!).getObjValAs? String "hash").toOption.getD ""
  let mut out := old.extract 0 e.kept
  -- Old height to new, for every entry the new journal holds.
  let mut heights : Std.HashMap Nat Nat := {}
  for h in List.range e.kept do heights := heights.insert (h + 1) (h + 1)
  for ((_, oh), i) in e.rest.toList.zipIdx do
    if let some h := oh then heights := heights.insert h (e.kept + i + 1)
  let mut names : Std.HashMap String String := {}
  let mut table : Array (Nat × String × Nat × String) := #[]
  for ((fields, oldHeight), i) in e.rest.toList.zipIdx do
    let newHeight := e.kept + i + 1
    -- Every name an earlier re-sealed entry changed, first: identity, delivery, resumes, slots.
    let mut fs := fields.map fun (k, v) => (k, subst names v)
    let identity := (lookup fields "identity").getD Json.null
    let principal := (identity.getObjValAs? String "principal").toOption.getD ""
    let oldIntent := (identity.getObjValAs? String "intent").toOption.getD ""
    let intent := names.getD oldIntent oldIntent
    -- The ids an identity hashes, again under its new intent (and an `ended`, under its new height).
    if intent != oldIntent then
      for (k, kind) in [("sends", "delivery"), ("changes", "delivery"), ("publishes", "publish")] do
        let items := ((lookup fs k).bind (·.getArr?.toOption)).getD #[]
        let offset := if k == "changes" then (((lookup fs "sends").bind (·.getArr?.toOption)).map (·.size)).getD 0 else 0
        for (item, n) in items.toList.zipIdx do
          if let .ok id := item.getObjValAs? String "id" then
            if id == idOf kind principal oldIntent (n + offset) then names := names.insert id (idOf kind principal intent (n + offset))
      if let some i := (lookup fs "outcome").bind (·.getObjVal? "interpretation" |>.toOption) then
        if let .ok id := i.getObjValAs? String "id" then
          if let some n := (List.range 64).find? (fun n => id == idOf "interpretation" principal oldIntent n) then
            names := names.insert id (idOf "interpretation" principal intent n)
    if let (some e', some h) := ((lookup fields "ended"), oldHeight) then
      if let .ok id := e'.getObjValAs? String "id" then
        if id == endedId principal oldIntent h then names := names.insert id (endedId principal intent newHeight)
    fs := fs.map fun (k, v) => (k, subst names v)
    -- A turn that was its height is its new height; entry 1 alone names the replay edition.
    if let (some (.num t), some h) := (lookup fs "turn", oldHeight) then
      if t.mantissa.toNat == h && t.exponent == 0 then fs := put fs "turn" (toJson newHeight)
    fs := if newHeight == 1 then (if (lookup fs "replay").isSome then fs else fs ++ [("replay", toJson Limits.replayEdition)])
      else erase fs "replay"
    -- A root ignore names an entry by height: it follows the entry.
    if let some outcome := lookup fs "outcome" then
      if (outcome.getObjValAs? String "tag").toOption == some "root" &&
          ["ignore", "unignore"].contains ((outcome.getObjValAs? String "kind").toOption.getD "") then
        let h ← outcome.getObjValAs? Nat "height"
        let some h' := heights[h]? | throw s!"the {(outcome.getObjValAs? String "kind").toOption.getD ""} at old height {(oldHeight.map toString).getD "?"} names entry {h}, which the edit removes"
        fs := put fs "outcome" (outcome.setObjVal! "height" (toJson h'))
    if i == 0 then fs := fs ++ [("rootEdit", marker.setObjVal! "at" (toJson newHeight))]
    let body := Json.mkObj ([("height", toJson newHeight), ("previous", toJson prev)] ++ fs)
    let hash := Journal.bodyHash body
    let entry := body.setObjVal! "hash" (toJson hash)
    if let some h := oldHeight then
      let oldHash := ((old[h - 1]!).getObjValAs? String "hash").toOption.getD ""
      names := names.insert oldHash hash
      table := table.push (h, oldHash, newHeight, hash)
    out := out.push entry
    prev := hash
  return { entries := out, table }

def natArg (args : List String) (flag : String) : Except String Nat := do
  match args.dropWhile (· != flag) with
  | _ :: v :: _ => match v.toNat? with
    | some n => pure n
    | none => throw s!"{flag} takes a number, not {v}"
  | _ => throw s!"{flag} is required"

def textArg (args : List String) (flag : String) : Option String :=
  match args.dropWhile (· != flag) with
  | _ :: v :: _ => some v
  | _ => none

/-- The entries of a file: one JSON object per line, or one array of them. -/
def entriesFile (path : String) : IO (Except String (Array Fields)) := do
  let text ← IO.FS.readFile path
  match Json.parse text with
  | .ok (.arr a) => return .ok (a.map fieldsOf)
  | .ok j@(.obj _) => return .ok #[fieldsOf j]
  | _ =>
    let lines := (text.splitOn "\n").filter (!·.trimAscii.isEmpty)
    match lines.mapM Json.parse with
    | .ok js => return .ok (js.toArray.map fieldsOf)
    | .error e => return .error s!"{path}: {e}"

def usage : String :=
  "usage: delvetalk-obend root-edit --journal J --out J2 --reason R (truncate --height N | drop --height N | " ++
  "rewrite --height N --entry FILE | splice --at N --entries FILE)\n" ++
  "       delvetalk-obend root-edit --state DIR --reason R delete-world --name W"

/-- The edit a command asks of `old`. -/
def editOf (old : Array Json) (command : String) (args : List String) : IO (Except String Edit) := do
  let n := old.size
  let rest := fun (from_ : Nat) => (old.extract from_ n).toList.zipIdx.toArray.map fun (x, i) => (fieldsOf x, some (from_ + i + 1))
  let height := natArg args "--height"
  match command with
  | "truncate" => return do
    let h ← height
    unless 1 ≤ h && h ≤ n do throw s!"--height must be 1..{n}"
    pure { kept := h, rest := #[], command := Json.mkObj [("command", toJson "truncate"), ("height", toJson h)] }
  | "drop" => return do
    let h ← height
    unless 1 ≤ h && h ≤ n do throw s!"--height must be 1..{n}"
    pure { kept := h - 1, rest := rest h, command := Json.mkObj [("command", toJson "drop"), ("height", toJson h)] }
  | "rewrite" =>
    let some file := textArg args "--entry" | return .error "rewrite takes --entry FILE"
    match height, ← entriesFile file with
    | .error e, _ | _, .error e => return .error e
    | .ok h, .ok files =>
      unless 1 ≤ h && h ≤ n do return .error s!"--height must be 1..{n}"
      let some fields := files[0]? | return .error s!"{file} holds no entry"
      unless files.size == 1 do return .error s!"{file} holds {files.size} entries; rewrite takes one"
      return .ok { kept := h - 1, rest := #[(fields, some h)] ++ rest h,
                   command := Json.mkObj [("command", toJson "rewrite"), ("height", toJson h)] }
  | "splice" =>
    let some file := textArg args "--entries" | return .error "splice takes --entries FILE"
    match natArg args "--at", ← entriesFile file with
    | .error e, _ | _, .error e => return .error e
    | .ok at_, .ok inserted =>
      unless at_ ≤ n do return .error s!"--at must be 0..{n}"
      if inserted.isEmpty then return .error s!"{file} holds no entry"
      return .ok { kept := at_, rest := inserted.map (·, none) ++ rest at_,
                   command := Json.mkObj [("command", toJson "splice"), ("at", toJson at_), ("entries", toJson inserted.size)] }
  | c => return .error s!"no command {c}\n{usage}"

def printJson (j : Json) : IO Unit := do
  let out ← IO.getStdout
  out.putStrLn j.compress
  out.flush

def fail (message : String) (code : UInt32 := 1) : IO UInt32 := do
  let errors ← IO.getStderr
  errors.putStrLn s!"root-edit: {message}"
  return code

/-- `delete-world --name W`: `<dir>/W.journal` and its snapshots to `<dir>/deleted/W-<stamp>.*`, with
    `W-<stamp>.json` saying why and from what head. `serve` must be stopped: its lock is checked. -/
def deleteWorld (state : System.FilePath) (name reason : String) : IO UInt32 := do
  unless validWorldName name do return ← fail s!"no world name {name}"
  let journal := state / s!"{name}.journal"
  unless ← journal.pathExists do return ← fail s!"no journal {journal}"
  let lock ← IO.FS.Handle.mk (state / "journal.lock") .append
  unless ← lock.tryLock (exclusive := true) do return ← fail s!"{state} is held by a running serve; stop it first" 75
  let head := match ← Snapshot.openEntries journal.toString with
    | .ok es => (es.hashAt? (es.count - 1)).getD Limits.genesis
    | .error _ => ""
  let stamp := toString (← IO.monoMsNow)
  let deleted := state / "deleted"
  IO.FS.createDirAll deleted
  let target := deleted / s!"{name}-{stamp}.journal"
  IO.FS.rename journal target
  let mut moved : Array String := #[target.toString]
  let store := Snapshot.storeOf journal.toString
  if ← System.FilePath.pathExists store then
    let to := Snapshot.storeOf target.toString
    IO.FS.rename store to
    moved := moved.push to
  for (_, path) in ← Snapshot.files journal.toString do
    let base := ((path : System.FilePath).fileName.getD path)
    let to := deleted / s!"{name}-{stamp}{(base.drop (name.length + ".journal".length)).toString}"
    IO.FS.rename path to
    moved := moved.push to.toString
  let note := Json.mkObj [("command", toJson "delete-world"), ("name", toJson name), ("reason", toJson reason),
    ("oldHead", toJson head), ("moved", toJson moved)]
  IO.FS.writeFile (deleted / s!"{name}-{stamp}.json") (note.compress ++ "\n")
  lock.unlock
  printJson (note.setObjVal! "status" (toJson "deleted"))
  return 0

def main (args : List String) : IO UInt32 := do
  let some reason := textArg args "--reason" | return ← fail usage 64
  if reason.isEmpty || reason.any (· == '\n') then return ← fail "a reason is one line" 64
  if args.contains "delete-world" then
    let some state := textArg args "--state" | return ← fail usage 64
    let some name := textArg args "--name" | return ← fail usage 64
    return ← deleteWorld state name reason
  let some journal := textArg args "--journal" | return ← fail usage 64
  let some outPath := textArg args "--out" | return ← fail usage 64
  let commands := ["truncate", "drop", "rewrite", "splice"]
  let some command := args.find? (commands.contains ·) | return ← fail usage 64
  if ← (outPath : System.FilePath).pathExists then return ← fail s!"{outPath} exists: root-edit writes a new file"
  let handle ← IO.FS.Handle.mk journal .read
  unless ← handle.tryLock (exclusive := true) do return ← fail s!"{journal} is open in another process: close it first" 75
  let old ← match ← Snapshot.journalEntries journal with
    | .ok es => pure es
    | .error e => return ← fail s!"{journal} does not verify: {e}"
  let oldHead := ((old.back?).bind fun e => (e.getObjValAs? String "hash").toOption).getD Limits.genesis
  let edit ← match ← editOf old command (args.dropWhile (· != command)) with
    | .ok e => pure e
    | .error e => return ← fail e 64
  let marker := Json.mkObj [("command", edit.command), ("reason", toJson reason), ("oldHead", toJson oldHead)]
  let sealed ← match reseal old edit marker with
    | .ok s => pure s
    | .error e => return ← fail e
  -- The new journal chains and replays in full, or nothing is written.
  let mut previous := ((sealed.entries[0]?).bind fun e => (e.getObjValAs? String "previous").toOption).getD Limits.genesis
  for (e, i) in sealed.entries.zipIdx do
    if let .error err := Journal.verify (i + 1) previous e then
      return ← fail s!"the edited journal does not chain: {err}"
    previous := (e.getObjValAs? String "hash").toOption.getD ""
  if let .error e := Snapshot.replayAll (Entries.ofArray sealed.entries) then
    return ← fail s!"the edited journal does not replay: {e}"
  if let .error e ← Snapshot.writeJournal outPath sealed.entries then return ← fail e
  -- Snapshots before the edit still describe the new journal's prefix.
  let mut copied : Array Nat := #[]
  for (h, path) in ← Snapshot.files journal do
    if h ≤ edit.kept then
      IO.FS.writeBinFile (Snapshot.fileOf outPath h) (← IO.FS.readBinFile path)
      copied := copied.push h
  handle.unlock
  let newHead := ((sealed.entries.back?).bind fun e => (e.getObjValAs? String "hash").toOption).getD Limits.genesis
  printJson (Json.mkObj [("status", toJson "edited"), ("out", toJson outPath), ("command", edit.command),
    ("oldHead", toJson oldHead), ("newHead", toJson newHead), ("height", toJson sealed.entries.size),
    ("at", toJson (if edit.rest.isEmpty then Json.null else toJson (edit.kept + 1))),
    ("slugsChanged", toJson sealed.table.size),
    ("snapshots", toJson copied),
    ("table", Json.arr (sealed.table.map fun (oh, o, nh, n) => Json.mkObj [("oldHeight", toJson oh), ("old", toJson o),
      ("height", toJson nh), ("new", toJson n), ("oldSlug", toJson ((Slug.ofCid o).getD "")), ("slug", toJson ((Slug.ofCid n).getD ""))]))])
  return 0

end Delvetalk.Host.RootEdit

namespace Delvetalk.Host.Migrate
open Lean (Json toJson)

/-- The one reader of the line format (every entry inline, one per line, before the block store):
    each line parsed and checked against the chain. -/
def lineEntries (content : String) : Except String (Array Json) := do
  let lines := content.splitOn "\n"
  let (complete, tail) := (lines.dropLast, lines.getLast?.getD "")
  let mut out : Array Json := #[]
  let mut head := Limits.genesis
  for line in complete do
    let height := out.size + 1
    let entry ← match Json.parse line with
      | .ok e => pure e
      | .error _ => throw s!"journal broken at height {height}: unparsable line"
    -- A fork's genesis chains to the forked world's entry, which it names.
    if height == 1 && tagOf entry == "forked" then head := (entry.getObjValAs? String "previous").toOption.getD ""
    Journal.verify height head entry
    head := (entry.getObjValAs? String "hash").toOption.getD ""
    out := out.push entry
  unless tail.isEmpty do throw s!"journal broken at height {out.size + 1}: unterminated final line"
  return out

/-- `delvetalk-obend migrate --journal OLD --out NEW`: a journal in the line format written as a chain
    and a block store (`Snapshot.writeJournal`), every entry and hash as it was. OLD is never written;
    NEW must not exist. Its snapshots are not carried: the first open replays NEW and writes them. -/
def main (args : List String) : IO UInt32 := do
  let fail := fun (m : String) (code : UInt32) => do (← IO.getStderr).putStrLn s!"migrate: {m}"; return code
  let some journal := RootEdit.textArg args "--journal" | fail "usage: migrate --journal OLD --out NEW" 64
  let some out := RootEdit.textArg args "--out" | fail "usage: migrate --journal OLD --out NEW" 64
  let entries ← match lineEntries (← IO.FS.readFile journal) with
    | .ok es => pure es
    | .error e => return ← fail s!"{journal} does not verify: {e}" 1
  if let .error e ← Snapshot.writeJournal out entries then return ← fail e 1
  RootEdit.printJson (Json.mkObj [("status", toJson "migrated"), ("out", toJson out), ("height", toJson entries.size),
    ("head", toJson ((entries.back?.bind fun e => (e.getObjValAs? String "hash").toOption).getD Limits.genesis))])
  return 0

end Delvetalk.Host.Migrate
