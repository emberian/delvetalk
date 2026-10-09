/- Pure observation of an exact caller-held root. This endpoint owns no world,
   identity or grant: custodians must acquire/recheck roots through governed reads.
   The installed source chooses the view; no command, law or state is invented. -/
import SourceState
import FileCustody
import SourcePackages
import Delvetalk.Package

namespace SourceProjection
open Lean World

/-- Execute only the compiled host's shared pure package path. -/
abbrev Execute := Json → Json → Array Json → Except String Json

def project (execute : Execute) (request : Json) : Except String Json := do
  let keys := (← pairs request).map Prod.fst
  if keys.length != 2 || !keys.all (["root", "panel"].contains) then
    throw "source projection requires exact root and panel"
  let root ← field request "root"
  let panel ← str request "panel"
  let protocol ← field root "protocol"
  let view ← field protocol "viewProgram"
  let profile ← str view "profile"
  if profile != "delvetalk-obend-data-menu-v1" then
    throw "unsupported source view profile"
  let state ← field root "state"
  if (← pairs state).map Prod.fst != ["model"] then
    throw "typed source view state requires exactly model"
  let (data, _) ← (SourceState.read protocol (← field state "model")).run 100000
  let arguments := #[Minidregg.Compiler.ObjectiveBendDataWire.dataJson data, obj [("tag", .str "label"), ("value", .str panel)]]
  return obj [("result", ← execute protocol (← field view "package") arguments)]

-- Captured roots may be larger than mutation requests; the process remains
-- read-only with an explicit input cap matching retained read custody.
def readObservation : IO Json := do
  let stdin ← IO.getStdin
  let mut bytes := ByteArray.empty
  repeat
    let chunk ← stdin.read 4096
    if chunk.isEmpty then break
    if bytes.size + chunk.size > 64 * 1024 * 1024 then
      throw (IO.userError "source projection observation exceeds 64 MiB")
    bytes := bytes ++ chunk
  let some line := String.fromUTF8? bytes | throw (IO.userError "source projection is not UTF-8")
  IO.ofExcept (Json.parse line)

def main (execute : Execute) : IO Unit := do
  let response ← try
    pure (← IO.ofExcept (project execute (← readObservation)))
  catch error => pure (obj [("error", .str error.toString)])
  (← IO.getStdout).putStrLn (FileCustody.encode response)
end SourceProjection
