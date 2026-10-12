/- The IO layer: the journal file and the session ops. -/
import Delvetalk.Host.Ops
import Delvetalk.Host.TurnLoop
import Delvetalk.Host.Snapshot
import Delvetalk.Host.Root
import Delvetalk.Host.Enchant

namespace Delvetalk.Host
open Lean (Json toJson)

/-- Flush and fsync; with `full`, F_FULLFSYNC where the OS has it (macOS). See `spec/native/sync.c`. -/
@[extern "delvetalk_handle_sync"]
opaque syncHandle (handle : @& IO.FS.Handle) (full : Bool) : IO Unit

/-- How appends are made durable, per process and never journaled (`world-open {sync}`):
    `none` only flushes (test journals), `fsync` (the default) asks the OS to write the bytes
    out, `full` adds the drive-cache barrier (F_FULLFSYNC on macOS), which stalls every other
    writer on the disk. -/
inductive Durability | none | fsync | full
  deriving BEq, Repr

def Durability.name : Durability → String
  | .none => "none" | .fsync => "fsync" | .full => "full"

/-- `sync` of `world-open`: one of the three names. Absent is `fsync`. -/
def Durability.ofJson? : Option Lean.Json → Except String Durability
  | Option.none => .ok .fsync
  | Option.some (.str "none") => .ok .none
  | Option.some (.str "fsync") => .ok .fsync
  | Option.some (.str "full") => .ok .full
  | Option.some _ => .error "sync must be \"none\", \"fsync\" or \"full\""

/-! ## Session and journal file -/

structure Open where
  world : World
  /-- The journal's chain (`Blocks`), held open for appends and locked for the session's life. -/
  path : String
  handle : IO.FS.Handle
  /-- The block store beside it (`<path>.blocks`), open for appends. -/
  store : IO.FS.Handle
  /-- The directory the library was loaded from, for `world-library`. -/
  libraryPath : Option String := none
  /-- Height of the newest snapshot written or resumed from; the next is written once the
      journal is `every` entries past it. -/
  snapshotAt : Nat := 0
  /-- The snapshot cadence (`world-open {snapshotEvery}`, default `Limits.snapshotEvery`). Per process. -/
  every : Nat := Limits.snapshotEvery
  /-- What the open did with snapshots, for the `world-open` reply. -/
  report : Snapshot.Report := {}
  /-- How appends are made durable (`Durability`). Per process, never journaled. -/
  sync : Durability := .fsync
  /-- The bound the journal's bytes (chain and block store) meet at append (`Limits.maxJournalBytes`,
      or lower for this process: `world-open {maxJournalBytes}`). -/
  bound : Nat := Limits.maxJournalBytes
  /-- Paints of this world's cards by key (`Enchant.Cache`). Per process, never journaled. -/
  renders : Enchant.Cache := {}

abbrev Session := Option Open

def isWorldOp (op : String) : Bool := op.startsWith "world-"

/-- Seal every `*.obend` under `path` as a library (module name = file name without extension). -/
def loadLibrary (path : String) : IO (Except String Library) := do
  try
    unless ← System.FilePath.isDir path do return .error s!"library path {path} is not a directory"
    let files ← System.FilePath.walkDir path
    let mut modules : List (String × String) := []
    let mut names : List String := []
    for f in files.qsort (fun a b => a.toString < b.toString) do
      if f.extension == some "obend" then
        let name := f.fileStem.getD ""
        if names.contains name then return .error s!"library has two modules named {name}"
        names := names ++ [name]
        modules := modules ++ [(name, ← IO.FS.readFile f)]
    return sealLibrary modules
  catch e => return .error s!"library unreadable: {e}"

/-- The size of a file, 0 when there is none. -/
def fileSize (path : String) : IO Nat := do
  if ← System.FilePath.pathExists path then return (← System.FilePath.metadata path).byteSize.toNat else return 0

/-- The bytes of a journal: its chain and its block store. -/
def journalBytes (path : String) : IO Nat := return (← fileSize path) + (← fileSize (Snapshot.storeOf path))

/-- Open a journal (`Snapshot.openJournal`). The chain's handle takes an exclusive advisory lock
    (`flock`, through `IO.FS.Handle.tryLock`) for the life of the session, so a second process cannot
    append to (or replay) a journal another holds. `held` is this process's own handle on the same path. -/
def openWorld (path : String) (held : Option (IO.FS.Handle × IO.FS.Handle) := none) (verify : Bool := false)
    (caches : Caches := {}) (bound : Nat := Limits.maxJournalBytes) : IO (Except String Open) := do
  try
    let handle ← match held with
      | some (h, _) => pure h
      | none => IO.FS.Handle.mk path IO.FS.Mode.append
    if held.isNone then
      unless ← handle.tryLock (exclusive := true) do return .error "journal is open in another process"
    let store ← match held with
      | some (_, s) => pure s
      | none => IO.FS.Handle.mk (Snapshot.storeOf path) IO.FS.Mode.append
    let bytes ← journalBytes path
    if bytes > bound then
      return .error s!"journal exceeds byte capacity: {bytes} bytes, past maxJournalBytes ({bound})"
    match ← Snapshot.openJournal path verify caches with
    | .error e => return .error e
    | .ok (world, report) => return .ok { world, path, handle, store, report, snapshotAt := report.resumed, bound }
  catch e => return .error s!"journal unreadable: {e}"

/-- Write a snapshot of the open world now: `{height}`, or `{refused}` naming why not. -/
def snapshotNow (s : Open) : IO (Open × Json) := do
  match ← Snapshot.write s.path s.world with
  | .ok h => return ({ s with snapshotAt := h }, Json.mkObj [("height", toJson h)])
  | .error e => return ({ s with snapshotAt := s.world.height }, Json.mkObj [("refused", toJson e)])

/-- Make a handle's appends durable as the session says (`Durability`). -/
def syncAs (sync : Durability) (h : IO.FS.Handle) : IO Unit :=
  match sync with
  | .none => h.flush
  | .fsync => syncHandle h false
  | .full => syncHandle h true

/-- The chain lines and the spans of entries whose records are appended to a store `start` bytes long. -/
def linksAt (entries : Array Json) (records : Array ByteArray) (start : Nat) : String × Array (Nat × Nat) := Id.run do
  let mut at_ := start
  let mut spans : Array (Nat × Nat) := #[]
  let mut lines := ""
  for (entry, r) in entries.zip records do
    spans := spans.push (at_, r.size)
    lines := lines ++ (Link.of entry at_ r.size).json.compress ++ "\n"
    at_ := at_ + r.size
  return (lines, spans)

/-- Append the entries a step made: every record to the block store, made durable, then their links
    (`linksAt`, from the store's size now) to the chain, made durable. A crash between leaves records
    no link names, which nothing reads. -/
def appendJournal (s : Open) (w : World) (records : Array ByteArray) : IO (Except String Open) := do
  try
    s.store.flush
    let (lines, spans) := linksAt w.entries.unwritten records (← fileSize (Snapshot.storeOf s.path))
    for r in records do s.store.write r
    syncAs s.sync s.store
    s.handle.putStr lines
    syncAs s.sync s.handle
    return .ok { s with world := { w with entries := w.entries.written spans } }
  catch e => return .error s!"journal write failed: {e}"

/-- A world step, then whatever it let go on (resumptions and deliveries in the same pass), the world it
    leaves and its reply; the turns the settling pass ran are shown as `reader` (the request's principal) may
    see them (`settledFor`). What `durableIO` makes durable and `world-try` drops. -/
def settledStep (s : Open) (reader : String) (step : World → IO (Except String (World × Json))) : IO (Except String (World × Json × Json)) := do
  let settled := fun (w : World) => w.suspended.isEmpty && w.pending.isEmpty
  let stepped ← step s.world
  return do
    let (w', r0) ← stepped
    -- What the settling pass runs is no request's: no turn of it is the public socket's.
    let w' := { w' with resident := false }
    let (w', resumed, delivered) ← if settled w' then pure (w', #[], #[]) else settleAll w'
    -- Turns the settling pass ran belong to their own principals: whoever caused the pass sees
    -- another's only as its projection, and nobody's offers (`world-offers` reads them).
    let quiet := fun (rs : Array Json) => rs.map (settledFor w' reader)
    let r := if resumed.isEmpty then r0 else r0.setObjVal! "resumed" (Json.arr (quiet resumed))
    let r := if delivered.isEmpty then r else r.setObjVal! "delivered" (Json.arr (quiet delivered))
    return (w', r0, r)

/-- Run a world step and make its entries durable before the reply exists (`settledStep`). -/
def durableIO (s : Open) (reader : String) (step : World → IO (Except String (World × Json))) : IO (Session × Except String Json) := do
  match ← settledStep s reader step with
  | .error e => return (some s, .error e)
  | .ok (w', r0, r) =>
    if w'.height == s.world.height then return (some { s with world := w' }, .ok r)
    let recordsOf := fun (w : World) => w.entries.unwritten.mapM recordBytes
    let records ← match recordsOf w' with
      | .ok rs => pure rs
      | .error e => return (some s, .error s!"journal entry has no canonical form: {e}")
    if records.any (·.size > Limits.maxEntryBytes) then
      return (some s, .error "journal entry exceeds capacity")
    if w'.height - w'.entries.base > Limits.maxJournalEntries then
      return (some s, .error "journal is full")
    let full := s!"journal is full: appending would pass maxJournalBytes ({s.bound} bytes)"
    -- What an append adds: the records, and their links as the chain will hold them.
    let start ← fileSize (Snapshot.storeOf s.path)
    let bytes := start + (← fileSize s.path)
    let size := fun (w : World) (rs : Array ByteArray) => rs.foldl (· + ·.size) (linksAt w.entries.unwritten rs start).1.utf8ByteSize
    -- Near the bound only a refusal is written (OPERATIONS §c 1): a turn is refused `capacity` naming
    -- the bound, journaled into the headroom, so the operator sees it before any restart would.
    let (w', r, records) ← if bytes + size w' records + Limits.journalHeadroom ≤ s.bound then pure (w', r, records) else
      let identity := (r0.getObjVal? "receipt").toOption.bind (·.getObjVal? "identity" |>.toOption)
      match identity.bind (·.getObjValAs? String "principal" |>.toOption), identity.bind (·.getObjValAs? String "intent" |>.toOption) with
      | some principal, some intent =>
        let p : Proposal := { principal, intent, roots := [], writes := [], turn := s.world.height + 1 }
        let (wR, rR) := commit s.world p [] (some { cls := "capacity", reason := some "maxJournalBytes" })
        let some rs := (recordsOf wR).toOption | return (some s, .error full)
        if bytes + size wR rs > s.bound then return (some s, .error full)
        pure (wR, turnReply wR rR, rs)
      | _, _ => return (some s, .error full)
    let ignored := w'.entries.unwritten.any isIgnoreAct
    let s ← match ← appendJournal s w' records with
      | .ok s => pure s
      | .error e => return (some s, .error e)
    -- The entries are durable; a snapshot is derived from them and its failure refuses nothing. After
    -- an `ignore`, one is written at once, so the next open need not replay from before it.
    if !ignored && w'.height < s.snapshotAt + s.every then return (some s, .ok r)
    let (o, note) ← snapshotNow s
    return (some o, .ok (r.setObjVal! "snapshot" note))

/-- `if: [{object, version}]` on a turn or a try: the versions the asker last read (a try's `roots`). Each
    that moved, `{object, was, now}`, `now` null when the object is gone or the principal may not view it. -/
def movedRoots (w : World) (j : Json) : Except String (List Json) := do
  let some given := (j.getObjVal? "if").toOption | return []
  let .ok roots := given.getArr? | throw "the if: line does not read: it is `if: <card> v<n>, <card> v<n>`, as a try ends"
  if roots.size > Limits.maxRoots then throw s!"if names at most {Limits.maxRoots} roots"
  let principal := (j.getObjValAs? String "principal").toOption.getD ""
  roots.toList.filterMapM fun a => do
    let id ← a.getObjValAs? String "object"
    let was ← a.getObjValAs? Nat "version"
    let now := (w.objects[id]?).bind fun o => if o.read.permits principal then some o.version else none
    return if now == some was then none else
      some (Json.mkObj [("object", toJson id), ("was", toJson was), ("now", match now with | some v => toJson v | none => Json.null)])

/-- The answer to an act whose `if` no longer holds: nothing ran and nothing is journaled; read again and resend. -/
def movedReply (moved : List Json) : Json :=
  let said := moved.map fun m =>
    let id := (m.getObjValAs? String "object").toOption.getD ""
    let was := (m.getObjValAs? Nat "was").toOption.getD 0
    match (m.getObjValAs? Nat "now").toOption with
    | some now => s!"{id} is at v{now}, not v{was}"
    | none => s!"{id} is gone, not at v{was}"
  Json.mkObj [("status", toJson "refused"), ("class", toJson "moved"), ("moved", Json.arr moved.toArray),
    ("line", toJson s!"refused moved: {"; ".intercalate said}")]

/-- `world-try`: a turn exactly as `world-turn` runs it, with its settling pass, and the world it leaves dropped:
    the commit with the write switched off (docs/POSTING.md §2). The reply is the turn's own, its receipt the entry
    that would be journaled (its writes' state CIDs, its roots with their versions), its offers the exact cards,
    `tried: true`, `against {height, hash}`, the head it ran on, and `unresolved {pending, suspended}`: what the
    settling pass left for later (sends not yet delivered, turns waiting on hob), which a preview does not foresee.
    Nothing is journaled. -/
def tryTurn (s : Open) (reader : String) (request : Json) : IO (Session × Except String Json) := do
  match ← settledStep s reader (fun w => pure (do runTurn w (← parseTurn request))) with
  | .error e => return (some s, .error e)
  | .ok (w', _, r) =>
    let head := (s.world.entries.hashAt? (s.world.height - 1)).getD ""
    -- Where the preview stops: sends still pending and turns waiting on hob would run after, on a world that may
    -- have moved, so they are counted, never foreseen.
    return (some s, .ok (((r.setObjVal! "tried" (Json.bool true)).setObjVal! "against"
      (Json.mkObj [("height", toJson s.world.height), ("hash", toJson head)])).setObjVal! "unresolved"
      (Json.mkObj [("pending", toJson w'.pending.size), ("suspended", toJson w'.suspended.size)])))

/-- `durableIO` of a pure step. -/
def durable (s : Open) (reader : String) (step : World → Except String (World × Json)) : IO (Session × Except String Json) :=
  durableIO s reader (fun w => pure (step w))

/-- `world-fork {principal, height?, into}`: write a new journal at `into` (a path that does not
    exist) whose genesis is the open world's store at `height` (default the head; an earlier height
    is replayed to), carrying only what `principal` may view (`Snapshot.forkGenesis`), with the
    principal as its opener and clock. The open world is untouched and nothing is journaled here.
    Answers `{status: "forked", into, forkedFrom {world, height, cid}, carried, omitted}`. -/
def forkWorld (s : Open) (j : Json) : IO (Except String Json) := do
  let .ok principal := j.getObjValAs? String "principal" | return .error "world-fork needs a principal"
  if principal.isEmpty || principal.utf8ByteSize > Limits.maxPrincipalBytes then
    return .error s!"principal must be 1..{Limits.maxPrincipalBytes} bytes"
  let .ok into := j.getObjValAs? String "into" | return .error "world-fork needs `into`, the new journal's path"
  let height ← match optNat j "height" with
    | .ok h => pure (h.getD s.world.height)
    | .error e => return .error e
  if height == 0 || height > s.world.height then return .error s!"height must be 1..{s.world.height}"
  if into == s.path || (← System.FilePath.pathExists into) then return .error s!"{into} already exists"
  -- An earlier height is the world from the newest snapshot at or below it.
  let w ← if height == s.world.height then pure s.world else
    match ← Snapshot.reopen s.path (s.world.entries.upTo height) s.world.caches with
    | .ok (w, _) => pure w
    | .error e => return .error e
  let cid := (s.world.entries.hashAt? (height - 1)).getD ""
  match Snapshot.forkGenesis w principal s.path height cid with
  | .error e => return .error e
  | .ok (entry, omitted) =>
    if let .error e ← Snapshot.writeJournal into #[entry] then return .error s!"fork write failed: {e}"
    return .ok (Json.mkObj [("status", toJson "forked"), ("into", toJson into),
      ("forkedFrom", Json.mkObj [("world", toJson s.path), ("height", toJson height), ("cid", toJson cid)]),
      ("carried", toJson (w.objects.size - omitted.length)), ("omitted", toJson omitted)])

/-- `world-status`'s interpretation quota: the cap, and for a named principal how many it may still
    start this clock hour and the clock at which the count starts again (`exempt` for the opener and
    the clock principal). -/
def interpretStatus (w : World) (r : Json) (principal : Option String) : Json :=
  let r := r.setObjVal! "interpretQuota" (toJson w.interpretQuota)
  match principal with
  | none => r
  | some p =>
    if p == w.opener || p == w.clockPrincipal then r.setObjVal! "interpretations" (toJson "exempt") else
    let hour := w.clock / 60
    let used := match w.interpretsStarted[p]? with
      | some (h, n) => if h == hour then n else 0
      | none => 0
    r.setObjVal! "interpretations" (Json.mkObj [("remaining", toJson (w.interpretQuota - used)),
      ("next", toJson ((hour + 1) * 60))])

def stepWorldCore (session : Session) (request : Json) (foreign : Foreign := {}) : IO (Session × Except String Json) := do
  let op ← match request.getObjValAs? String "op" with
    | .ok op => pure op
    | .error _ => return (session, .error "missing op")
  let reader := (request.getObjValAs? String "principal").toOption.getD ""
  if op == "world-open" then
    match request.getObjValAs? String "path" with
    | .error e => return (session, .error e)
    | .ok path =>
      let held := match session with
        | some o => if o.path == path then some (o.handle, o.store) else none
        | none => none
      let verify ← match request.getObjVal? "verify" with
        | .ok (.bool b) => pure b
        | .ok _ => return (session, .error "verify must be true or false")
        | .error _ => pure false
      let sync ← match Durability.ofJson? (request.getObjVal? "sync").toOption with
        | .ok d => pure d
        | .error e => return (session, .error e)
      -- A lower journal bound for this process (an operator's rehearsal, a test); never a higher one.
      let bound ← match optNat request "maxJournalBytes" with
        | .ok none => pure Limits.maxJournalBytes
        | .ok (some b) =>
          if b > Limits.maxJournalBytes then
            return (session, .error s!"maxJournalBytes may lower the bound ({Limits.maxJournalBytes}), never raise it")
          pure b
        | .error e => return (session, .error e)
      -- A lower object bound for this process (a scratch world's); never a higher one.
      let objectBound ← match optNat request "maxObjects" with
        | .ok none => pure Limits.maxObjects
        | .ok (some n) =>
          if n > Limits.maxObjects then
            return (session, .error s!"maxObjects may lower the bound ({Limits.maxObjects}), never raise it")
          pure n
        | .error e => return (session, .error e)
      -- How many entries apart this process writes snapshots.
      let every ← match optNat request "snapshotEvery" with
        | .ok none => pure Limits.snapshotEvery
        | .ok (some n) =>
          if n == 0 then return (session, .error "snapshotEvery must be at least 1")
          pure n
        | .error e => return (session, .error e)
      -- What this process compiled for the world it had open stays compiled for the next.
      match ← openWorld path held verify ((session.map (·.world.caches)).getD {}) bound with
      | .error e => return (session, .error e)
      | .ok o =>
        let o := { o with sync, every, world := { o.world with objectBound } }
        -- The first open naming a clock principal or a posting quota journals them.
        let o ← match (do
            let quota ← match request.getObjVal? "postQuota" with
              | .ok q => some <$> natOf q
              | .error _ => pure none
            let interpretQuota ← optNat request "interpretQuota"
            return ((request.getObjValAs? String "clock").toOption, quota,
              (request.getObjValAs? String "opener").toOption, interpretQuota) : Except String _) with
          | .error e => return (session, .error e)
          | .ok (none, none, none, none) => pure o
          | .ok (clock, quota, opener, interpretQuota) =>
            let (s', r) ← durable o reader (fun w => settingsOp w clock quota opener interpretQuota)
            match r, s' with
            | .ok _, some o' => pure o'
            | .error e, _ => return (session, .error e)
            | _, none => return (session, .error "world-open failed")
        -- The world's name, journaled once (`named`); another name than the journal holds is refused.
        let o ← match request.getObjValAs? String "name" with
          | .error _ => pure o
          | .ok name =>
            let (s', r) ← durable o reader (fun w => nameOp w name)
            match r, s' with
            | .ok _, some o' => pure o'
            | .error e, _ => return (session, .error e)
            | _, none => return (session, .error "world-open failed")
        let opened := fun (o : Open) (extra : List (String × Json)) => Json.mkObj ([("status", toJson "opened"),
          ("height", toJson o.world.height), ("head", toJson o.world.head)] ++
          (if o.world.name.isEmpty then [] else [("name", toJson o.world.name)]) ++ [
          ("objects", toJson o.world.objects.size), ("snapshot", o.report.json)] ++ extra ++
          (if o.world.shadowed.isEmpty then [] else [("shadowed", Json.arr o.world.shadowed)]) ++
          (o.world.library.map fun l => [("library", toJson l.pin)]).getD [])
        match request.getObjValAs? String "library" with
        | .error _ => return (some o, .ok (opened o []))
        | .ok libPath =>
          match ← loadLibrary libPath with
          | .error e => return (session, .error e)
          | .ok lib =>
            let o := { o with libraryPath := some libPath }
            match o.world.library with
            | some recorded =>
              if recorded.pin != lib.pin then
                return (session, .error s!"library at {libPath} has pin {lib.pin} but the journal records {recorded.pin}; the bytes differ")
              return (some o, .ok (opened o []))
            | none =>
              let some who := (request.getObjValAs? String "principal").toOption
                | return (session, .error "world-open with a library needs the opening principal")
              let law := (request.getObjValAs? String "libraryLaw").toOption
              let (s', r) ← durable o reader (fun w => libraryOp w who s!"library:{lib.pin}" lib law)
              match r with
              | .error e => return (session, .error e)
              | .ok reply =>
                if (reply.getObjValAs? String "status").toOption == some "refused" then
                  return (session, .ok reply)
                return (s', .ok ((opened (s'.getD o) []).setObjVal! "receipt"
                  ((reply.getObjVal? "receipt").toOption.getD Json.null)))
  else match session with
    | none => return (none, .error "no world is open; send world-open first")
    | some s =>
      -- `serve` marks a public-socket request naming the opener (`World.resident`); every request sets it.
      let s := { s with world := { s.world with resident := (request.getObjValAs? Bool "resident").toOption == some true, foreign } }
      -- The mark is the socket's, not the request's: no digest or field reading sees it.
      let request := Json.mkObj (((request.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "resident"))
      match op with
      | "world-create" => durable s reader (fun w => create w request)
      | "world-turn" | "world-try" =>
        match movedRoots s.world request with
        | .error e => return (session, .ok (Json.mkObj [("status", toJson "refused"), ("class", toJson "moved"),
            ("moved", Json.arr #[]), ("line", toJson s!"refused moved: {e}")]))  -- a guard that does not read fails closed
        | .ok moved@(_ :: _) => return (session, .ok (movedReply moved))
        | .ok [] => if op == "world-try" then tryTurn s reader request else durable s reader (fun w => do runTurn w (← parseTurn request))
      | "world-deliver" => durable s reader (fun w => do
          let limit := (← optNat request "limit").getD Limits.deliveriesPerCall
          if limit == 0 || limit > Limits.deliveriesPerCall then
            throw s!"limit must be 1..{Limits.deliveriesPerCall}"
          deliver w limit reader)
      | "world-pending" => return (session, .ok (pendingReply s.world))
      | "world-snapshot" =>
        let (o, note) ← snapshotNow s
        return (some o, .ok ((note.setObjVal! "status" (toJson "snapshot"))))
      | "world-library" => do
        let path? := (request.getObjValAs? String "library").toOption <|> s.libraryPath
        let some libPath := path? | return (session, .error "this world was opened without a library")
        let principal ← match request.getObjValAs? String "principal" with
          | .ok p => pure p
          | .error e => return (session, .error e)
        let intent ← match request.getObjValAs? String "identity" with
          | .ok p => pure p
          | .error e => return (session, .error e)
        match ← loadLibrary libPath with
        | .error e => return (session, .error e)
        | .ok lib => durable s reader (fun w => libraryOp w principal intent lib none)
      | "world-inspect" => return (session, inspectOp s.world request)
      | "world-check" => return (session, worldCheck s.world request)
      | "world-interpretations" =>
        let (w, r) := interpretationsReply s.world
        return (some { s with world := w }, .ok r)
      | "world-interpretation" => durable s reader (fun w => interpretationOp w request)
      | "world-reprogram" => durable s reader (fun w => reprogramOp w request)
      | "world-amend" => durable s reader (fun w => amendOp w request)
      | "world-revoke" => durable s reader (fun w => revokeOp w request)
      | "world-root" => durableIO s reader (fun w => do
          match rootOp w request with
          | .error e => return .error e
          | .ok (w2, r) =>
            -- An ignore changes what every later entry did: the store is the journal's under the new
            -- set, from the newest snapshot before the height it names (`Snapshot.reopen`).
            unless w2.entries.unwritten.any isIgnoreAct do return .ok (w2, r)
            match ← Snapshot.reopen s.path w2.entries w2.caches with
            | .error e => return .error e
            | .ok (w3, _) =>
              let w3 := w3.withCachesOf w2
              return .ok ({ w3 with entries := w2.entries, objectBound := w2.objectBound }, if w3.shadowed.isEmpty then r else r.setObjVal! "shadowed" (Json.arr w3.shadowed)))
      | "world-settings" => durable s reader (fun w => worldSettingsOp w request)
      | "world-advance" => durable s reader (fun w => advance w request)
      | "world-propose" => durable s reader (fun w => do return commit w (← parseProposal request))
      | "world-view" => return (session, view s.world request)
      | "world-state-cid" => return (session, stateCidOp s.world request)
      | "world-fork" => return (session, ← forkWorld s request)
      | "world-resolve" => return (session, resolveOp s.world request)
      | "world-entry" => return (session, entryOp s.world request)
      | "world-entries" => return (session, entriesOp s.world request)
      | "world-object" => return (session, objectOp s.world request)
      | "world-dump" => return (session, dumpOp s.world request)
      | "world-source" => return (session, sourceOp s.world request)
      | "world-sources" => return (session, sourcesOp s.world request)
      | "world-grants" => return (session, grantsOp s.world request)
      | "world-rules" => return (session, rulesOp s.world request false)
      | "world-wants" => return (session, rulesOp s.world request true)
      | "world-chronicle" => return (session, chronicleOp s.world request)
      | "world-wanting" => return (session, wantingOp s.world request)
      | "world-receipt" => return (session, receipt s.world request)
      | "world-history" => return (session, history s.world request)
      | "world-status" => return (session, .ok (Json.mkObj [("status", toJson "world"),
          ("height", toJson s.world.height), ("head", toJson s.world.head),
          ("objects", toJson s.world.objects.size), ("clock", toJson s.world.clock),
          ("postQuota", toJson s.world.postQuota), ("posts", postsStatus s.world),
          ("modelQuota", Json.mkObj [("quota", toJson s.world.modelQuota), ("used", toJson
            (if s.world.modelDay.1 == s.world.clock / Limits.clockDay then s.world.modelDay.2 else 0)), ("next", toJson ((s.world.clock / Limits.clockDay + 1) * Limits.clockDay))]),
          ("hour", (if s.world.hourCounts.hour == s.world.clock / 60 then s.world.hourCounts else { hour := s.world.clock / 60 }).json),
          ("shadowed", Json.arr s.world.shadowed), ("ignored", toJson s.world.ignored), ("replay", toJson Limits.replayEdition), ("locked", toJson true), ("sync", toJson s.sync.name),
          ("recompiledDifferently", toJson s.world.recompiledDifferently), ("renders", s.renders.counts),
          -- What this process holds compiled (carried from world to world it opens).
          ("compiled", Json.mkObj [("packages", toJson s.world.builds.size), ("closures", toJson s.world.requests.size),
            ("methods", toJson s.world.compiled.size)])] |>
          -- A fork or a carry names where it came from (its genesis's `forkedFrom` or `carriedFrom`).
          fun r => (match s.world.entries.genesis?.bind genesisOrigin with
            | some (key, origin) => r.setObjVal! key (originShown origin)
            | none => r) |> fun r => interpretStatus s.world r (request.getObjValAs? String "principal").toOption))
      | "world-posted" => durable s reader (fun w => postedOp w request)
      | "world-cite" => durable s reader (fun w => citeOp w request)
      | "world-relay" => durable s reader (fun w => relayOp w request)
      | "world-cross" => durable s reader (fun w => crossOp w request)
      | "world-post-reserve" => durable s reader (fun w => postReserveOp w request)
      | "world-post-release" => durable s reader (fun w => postReleaseOp w request)
      | "world-principal" => durable s reader (fun w => principalOp w request)
      | "world-arrive" => durable s reader (fun w => arriveOp w request)
      | "world-reach" => return (session, reachOp s.world request)
      | "world-publications" => return (session, publicationsOp s.world request)
      | "world-objects" => return (session, objectsOp s.world request)
      | "world-offers" => return (session, offersOp s.world request)
      | "world-strokes" => return (session, Enchant.strokesOp s.world request)
      | "world-render-check" => return (session, Enchant.checkOp s.world request)
      | "world-render" | "world-renders" | "world-render-submit" => match ← Enchant.op op s.renders s.world request with
        | .ok (renders, w, r) => return (some { s with renders, world := w }, .ok r)
        | .error e => return (session, .error e)
      | "world-card" => match cardOp s.world request with
        | .ok (w, r) => return (some { s with world := w }, .ok r)
        | .error e => return (session, .error e)
      | _ => return (session, .error s!"unknown world operation {op}")

/-- Write what this process compiled and the disk cache lacks (`DiskCache`, when
    `DELVETALK_COMPILE_CACHE` names a directory): packages by build key, definitions by object
    inputs and name. Each key is written once per process; an existing file is left alone. -/
def persistCaches (w : World) : IO Unit := do
  if (← DiskCache.dir).isNone then return
  for (key, b) in w.builds.toList do DiskCache.write "build" key (builtJson key b)
  for (key, c) in w.compiled.toList do DiskCache.write "def" key (compiledJson key c)

/-- One op (`stepWorldCore`), then the compile cache written to disk; `world-status` reports it as
    `compileCache {dir, hits, known}` (null when off). -/
def stepWorld (session : Session) (request : Json) (foreign : Foreign := {}) : IO (Session × Except String Json) := do
  let (session, r) ← stepWorldCore session request foreign
  -- The other worlds were this request's to read; the session does not keep them.
  let session := session.map fun s => { s with world := { s.world with foreign := {} } }
  if let some s := session then persistCaches s.world
  if (request.getObjValAs? String "op").toOption == some "world-status" then
    if let .ok j := r then return (session, .ok (j.setObjVal! "compileCache" (← DiskCache.status)))
  return (session, r)

end Delvetalk.Host
