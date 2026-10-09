import Delvetalk.PackageSession
open Lean (Json toJson)

def main : IO UInt32 := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  let mut session : Delvetalk.PackageSession.Session := {}
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    let result := do
      if line.utf8ByteSize > 16777216 then throw "package frame exceeds 16 MiB"
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
  return 0
