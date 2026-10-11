import Delvetalk.PackageSession
import Delvetalk.Serve
import Delvetalk.Host.RootEdit
import Delvetalk.Host.Carry
open Lean (Json toJson)

/-- The JSON-lines driver on stdin and stdout; `serve …` holds a directory of worlds behind its
    sockets instead (`Delvetalk.Serve`). -/
def main (args : List String) : IO UInt32 := do
  if args.head? == some "serve" then return ← Delvetalk.Serve.main args.tail
  if args.head? == some "root-edit" then return ← Delvetalk.Host.RootEdit.main args.tail
  if args.head? == some "migrate" then return ← Delvetalk.Host.Migrate.main args.tail
  if args.head? == some "carry" then return ← Delvetalk.Host.Carry.main args.tail
  let input ← IO.getStdin
  let output ← IO.getStdout
  let errors ← IO.getStderr
  let timing := (← IO.getEnv "DELVETALK_TIMING") == some "1"
  let mut session : Delvetalk.PackageSession.Session := {}
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    let started ← IO.monoMsNow
    let result := do
      if line.utf8ByteSize > Delvetalk.Bounds.maxFrameBytes then throw s!"package frame exceeds maxFrameBytes ({Delvetalk.Bounds.maxFrameBytes} bytes)"
      if !Delvetalk.scalarEscapesText line then throw "malformed Unicode escape"
      Json.parse line
    let (next, result) ← match result with
      | .ok request => Delvetalk.PackageSession.stepIO session request
      | .error error => pure (session, .error error)
    session := next
    let reply := match result with
      | .ok j => j
      | .error e => Json.mkObj [("status", toJson "error"), ("message", toJson e)]
    output.putStrLn reply.compress
    output.flush
    if timing then
      let request := (Json.parse line).toOption.getD Json.null
      errors.putStrLn (Delvetalk.Serve.timingLine request reply ((← IO.monoMsNow) - started))
      errors.flush
  return 0
