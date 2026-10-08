import Delvetalk.Core
open Lean (Json)

def main : IO UInt32 := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  let errors ← IO.getStderr
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    if line.trimAscii.toString.isEmpty then
      errors.putStrLn "delvetalk: empty JSONL job"; return 1
    if !Delvetalk.scalarEscapes line.toList then
      errors.putStrLn "delvetalk: malformed Unicode escape"; return 1
    match Json.parse line >>= Delvetalk.job with
    | .ok j => output.putStrLn j.compress
    | .error e => errors.putStrLn s!"delvetalk: {e}"; return 1
  return 0
