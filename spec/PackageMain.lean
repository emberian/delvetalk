import Delvetalk.Package
open Lean (Json toJson)

def main : IO UInt32 := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    let result := do
      if line.utf8ByteSize > 16777216 then throw "package frame exceeds 16 MiB"
      if !Delvetalk.scalarEscapes line.toList then throw "malformed Unicode escape"
      Delvetalk.Package.job (← Json.parse line)
    let reply := match result with
      | .ok j => j
      | .error e => Json.mkObj [("status", toJson "error"), ("message", toJson e)]
    output.putStrLn reply.compress
  return 0
