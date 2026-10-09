import Delvetalk.PackageSession
open Lean (Json toJson)

def main : IO UInt32 := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  let mut cache : Delvetalk.PackageSession.Cache := []
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    let result := do
      if line.utf8ByteSize > 16777216 then throw "package frame exceeds 16 MiB"
      if !Delvetalk.scalarEscapes line.toList then throw "malformed Unicode escape"
      Json.parse line
    let (next, result) := match result with
      | .ok request => Delvetalk.PackageSession.step cache request
      | .error error => (cache, .error error)
    cache := next
    let reply := match result with
      | .ok j => j
      | .error e => Json.mkObj [("status", toJson "error"), ("message", toJson e)]
    output.putStrLn reply.compress
    output.flush
  return 0
