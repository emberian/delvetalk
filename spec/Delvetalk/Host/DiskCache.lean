/- The on-disk compile cache (HOST-HANDOFF 5.66): compiled packages and definitions kept across
   processes (hostd's heaps), under `$DELVETALK_COMPILE_CACHE/<stamp>`, where the stamp names this
   binary (the size and modification time of `IO.appPath`), so a new compiler never reads an old
   one's packets. Off unless the variable names a directory.

   A read is a memo of a pure function: `read kind key` is `none` in the model (compile as if
   cold), and in this process the file's JSON when one of `kind` names `key`. Every packet read is
   decoded and re-checked by Mini before it is used (`Ops.builtOf`, `Ops.compiledOfPacket`), so a
   damaged file fails closed to a compile. The directory is in the TCB as the binary is: a forged
   packet that type-checks need not be its source's. Writes are the session's (IO), after a step. -/
import Lean.Data.Json
import Std.Data.HashSet
import Delvetalk.Host.Journal

namespace Delvetalk.Host.DiskCache
open Lean (Json toJson)

/-- `<DELVETALK_COMPILE_CACHE>/<stamp>`, or none when the variable is unset or empty. -/
def locate : IO (Option System.FilePath) := do
  let some dir ← IO.getEnv "DELVETALK_COMPILE_CACHE" | return none
  if dir.isEmpty then return none
  let md ← (← IO.appPath).metadata
  return some (System.FilePath.mk dir / s!"{md.byteSize}-{md.modified.sec}-{md.modified.nsec}")

initialize directory : IO.Ref (Option (Option System.FilePath)) ← IO.mkRef none
/-- Files read and used, and files this process wrote (`world-status.compileCache`). -/
initialize hits : IO.Ref Nat ← IO.mkRef 0
initialize written : IO.Ref (Std.HashSet String) ← IO.mkRef {}

def dir : IO (Option System.FilePath) := do
  match ← directory.get with
  | some d => return d
  | none =>
    let d ← locate
    directory.set (some d)
    return d

/-- The file of `key` among `kind`'s (`build`, `def`): named by the key's CID. -/
def fileName (kind key : String) : String := s!"{kind}-{Journal.bodyHash (toJson key)}.json"

def readIO (kind key : String) : IO (Option Json) := do
  let some d ← dir | return none
  let path := d / fileName kind key
  unless ← path.pathExists do return none
  match Json.parse (← IO.FS.readFile path) with
  | .ok j => return if (j.getObjValAs? String "key").toOption == some key then some j else none
  | .error _ => return none

unsafe def readImpl (kind key : String) : Option Json :=
  unsafeBaseIO ((readIO kind key).catchExceptions fun _ => pure none)

/-- The cached JSON of `key` among `kind`'s; `none` in the model (see the module comment). -/
@[implemented_by readImpl]
def read (_kind _key : String) : Option Json := none

/-- Count a read the caller decoded and used. -/
unsafe def hitImpl {α : Type} (value : α) : α :=
  unsafeBaseIO (do hits.modify (· + 1); return value)

@[implemented_by hitImpl]
def hit {α : Type} (value : α) : α := value

/-- Write `body` (which carries `key`) for `key` unless this process wrote or read it, or the file exists.
    Written to a fresh name and renamed, so a concurrent reader sees a whole file or none. -/
def write (kind key : String) (body : Lean.Json) : IO Unit := do
  let some d ← dir | return
  let seen := kind ++ "/" ++ key
  if (← written.get).contains seen then return
  written.modify (·.insert seen)
  let name := fileName kind key
  let path := d / name
  if ← path.pathExists then return
  try
    IO.FS.createDirAll d
    let tmp := d / s!"{name}.{← IO.monoNanosNow}.tmp"
    IO.FS.writeFile tmp body.compress
    IO.FS.rename tmp path
  catch _ => pure ()

def status : IO Json := do
  match ← dir with
  | none => return Json.null
  | some d => return Json.mkObj [("dir", toJson d.toString), ("hits", toJson (← hits.get)),
      ("known", toJson (← written.get).size)]

end Delvetalk.Host.DiskCache
