/- The IO layer: the journal file and the session ops. -/
import Delvetalk.Host.Ops
import Delvetalk.Host.TurnLoop

namespace Delvetalk.Host
open Lean (Json toJson)

/-- Flush and fsync (F_FULLFSYNC on macOS); see `spec/native/sync.c`. -/
@[extern "delvetalk_handle_sync"]
opaque syncHandle (handle : @& IO.FS.Handle) : IO Unit

/-! ## Session and journal file -/

structure Open where
  world : World
  path : String
  handle : IO.FS.Handle
  /-- The directory the library was loaded from, for `world-library`. -/
  libraryPath : Option String := none

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

def openWorld (path : String) : IO (Except String Open) := do
  try
    let exists_ ← System.FilePath.pathExists path
    let content ← if exists_ then do
        let info ← System.FilePath.metadata path
        if info.byteSize.toNat > Limits.maxJournalBytes then
          return .error "journal exceeds byte capacity"
        IO.FS.readFile path
      else pure ""
    match replay content with
    | .error e => return .error e
    | .ok world =>
      let handle ← IO.FS.Handle.mk path IO.FS.Mode.append
      return .ok { world, path, handle }
  catch e => return .error s!"journal unreadable: {e}"

/-- Run a pure world step and make its entry durable before the reply exists. -/
def durable (s : Open) (step : World → Except String (World × Json)) : IO (Session × Except String Json) := do
  -- A step, then whatever it let go on: resumptions follow in the same durable write.
  let settled := fun (w : World) => w.suspended.isEmpty && w.pending.isEmpty
  match (do
      let (w', r) ← step s.world
      if settled w' then return (w', r, #[], #[])
      let (w'', resumed, delivered) ← settleAll w'
      return (w'', r, resumed, delivered) : Except String (World × Json × Array Json × Array Json)) with
  | .error e => return (some s, .error e)
  | .ok (w', r0, resumed, delivered) =>
    let r := if resumed.isEmpty then r0 else r0.setObjVal! "resumed" (Json.arr resumed)
    let r := if delivered.isEmpty then r else r.setObjVal! "delivered" (Json.arr delivered)
    if w'.height == s.world.height then return (some { s with world := w' }, .ok r)
    let fresh := w'.entries.extract s.world.height w'.height
    if fresh.any (·.compress.utf8ByteSize > Limits.maxEntryBytes) then
      return (some s, .error "journal entry exceeds capacity")
    if w'.height > Limits.maxJournalEntries then
      return (some s, .error "journal is full")
    try
      for entry in fresh do s.handle.putStr (entry.compress ++ "\n")
      syncHandle s.handle
      return (some { s with world := w' }, .ok r)
    catch e => return (some s, .error s!"journal write failed: {e}")

def stepWorld (session : Session) (request : Json) : IO (Session × Except String Json) := do
  let op ← match request.getObjValAs? String "op" with
    | .ok op => pure op
    | .error _ => return (session, .error "missing op")
  if op == "world-open" then
    match request.getObjValAs? String "path" with
    | .error e => return (session, .error e)
    | .ok path =>
      match ← openWorld path with
      | .error e => return (session, .error e)
      | .ok o =>
        -- The first open naming a clock principal or a posting quota journals them.
        let o ← match (do
            let quota ← match request.getObjVal? "postQuota" with
              | .ok q => some <$> natOf q
              | .error _ => pure none
            return ((request.getObjValAs? String "clock").toOption, quota) : Except String _) with
          | .error e => return (session, .error e)
          | .ok (none, none) => pure o
          | .ok (clock, quota) =>
            let (s', r) ← durable o (fun w => settingsOp w clock quota)
            match r, s' with
            | .ok _, some o' => pure o'
            | .error e, _ => return (session, .error e)
            | _, none => return (session, .error "world-open failed")
        let opened := fun (o : Open) (extra : List (String × Json)) => Json.mkObj ([("status", toJson "opened"),
          ("height", toJson o.world.height), ("head", toJson o.world.head),
          ("objects", toJson o.world.objects.size)] ++ extra ++
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
              let (s', r) ← durable o (fun w => libraryOp w who s!"library:{lib.pin}" lib law)
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
      match op with
      | "world-create" => durable s (fun w => create w request)
      | "world-turn" => durable s (fun w => do runTurn w (← parseTurn request))
      | "world-deliver" => durable s (fun w => do
          let limit := match request.getObjVal? "limit" with
            | .ok l => (natOf l).toOption.getD Limits.deliveriesPerCall
            | .error _ => Limits.deliveriesPerCall
          deliver w limit)
      | "world-pending" => return (session, .ok (pendingReply s.world))
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
        | .ok lib => durable s (fun w => libraryOp w principal intent lib none)
      | "world-inspect" => return (session, inspectOp s.world request)
      | "world-interpretations" => return (session, .ok (interpretationsReply s.world))
      | "world-interpretation" => durable s (fun w => interpretationOp w request)
      | "world-reprogram" => durable s (fun w => reprogramOp w request)
      | "world-amend" => durable s (fun w => amendOp w request)
      | "world-advance" => durable s (fun w => advance w request)
      | "world-propose" => durable s (fun w => do return commit w (← parseProposal request))
      | "world-view" => return (session, view s.world request)
      | "world-receipt" => return (session, receipt s.world request)
      | "world-history" => return (session, history s.world request)
      | "world-status" => return (session, .ok (Json.mkObj [("status", toJson "world"),
          ("height", toJson s.world.height), ("head", toJson s.world.head),
          ("objects", toJson s.world.objects.size), ("clock", toJson s.world.clock),
          ("postQuota", toJson s.world.postQuota)]))
      | "world-posted" => durable s (fun w => postedOp w request)
      | "world-addressee" => return (session, addressee s.world request)
      | "world-objects" => return (session, objectsOp s.world request)
      | "world-card" => return (session, cardOp s.world request)
      | _ => return (session, .error s!"unknown world operation {op}")

end Delvetalk.Host
