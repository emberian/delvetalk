import Delvetalk.Typed
open Lean (Json)

/-- One diagnostic per input line; a malformed/refused job does not kill a batch. -/
def main : IO UInt32 := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    let parsed := if !Delvetalk.scalarEscapes line.toList then
        Except.error "malformed Unicode escape"
      else Json.parse line
    let result := match parsed with
      | .error e => Delvetalk.Typed.malformed .null e
      | .ok j => match Delvetalk.Typed.job j with
        | .ok receipt => receipt
        | .error e => Delvetalk.Typed.malformed
            ((j.getObjValAs? String "name").toOption.map Json.str |>.getD .null) e
    output.putStrLn result.compress
  return 0
