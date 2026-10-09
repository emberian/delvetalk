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

abbrev Session := Option Open

def isWorldOp (op : String) : Bool := op.startsWith "world-"

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
      return .ok ⟨world, path, handle⟩
  catch e => return .error s!"journal unreadable: {e}"

/-- Run a pure world step and make its entry durable before the reply exists. -/
def durable (s : Open) (step : World → Except String (World × Json)) : IO (Session × Except String Json) := do
  -- A step, then whatever it let go on: resumptions follow in the same durable write.
  let settled := fun (w : World) => w.suspended.isEmpty
  match (do
      let (w', r) ← step s.world
      if settled w' then return (w', r, #[])
      let (w'', resumed) ← settle w'
      return (w'', r, resumed) : Except String (World × Json × Array Json)) with
  | .error e => return (some s, .error e)
  | .ok (w', r0, resumed) =>
    let r := if resumed.isEmpty then r0 else r0.setObjVal! "resumed" (Json.arr resumed)
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
      | .ok o => return (some o, .ok (Json.mkObj [("status", toJson "opened"),
          ("height", toJson o.world.height), ("head", toJson o.world.head),
          ("objects", toJson o.world.objects.size)]))
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
      | "world-reprogram" => durable s (fun w => reprogramOp w request)
      | "world-amend" => durable s (fun w => amendOp w request)
      | "world-advance" => durable s (fun w => advance w request)
      | "world-propose" => durable s (fun w => do return commit w (← parseProposal request))
      | "world-view" => return (session, view s.world request)
      | "world-receipt" => return (session, receipt s.world request)
      | "world-history" => return (session, history s.world request)
      | "world-status" => return (session, .ok (Json.mkObj [("status", toJson "world"),
          ("height", toJson s.world.height), ("head", toJson s.world.head),
          ("objects", toJson s.world.objects.size)]))
      | _ => return (session, .error s!"unknown world operation {op}")

end Delvetalk.Host
