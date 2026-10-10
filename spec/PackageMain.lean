import Delvetalk.PackageSession
open Lean (Json toJson)

/-- With `DELVETALK_TIMING=1`, one stderr line per op: its name, what it names (object, method,
    principal), the milliseconds from reading the request to writing the reply, and how many
    turns the settling pass after it resumed and delivered. -/
def timingLine (request : Json) (reply : Json) (ms : Nat) : String :=
  let text := fun (k : String) => (request.getObjValAs? String k).toOption.getD ""
  let count := fun (k : String) => ((reply.getObjVal? k).toOption.bind (·.getArr?.toOption)).map (·.size) |>.getD 0
  s!"timing\t{text "op"}\t{ms}\tobject={text "object"}\tmethod={text "method"}\tprincipal={text "principal"}\tresumed={count "resumed"}\tdelivered={count "delivered"}"

def main : IO UInt32 := do
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
    if timing then
      let request := (Json.parse line).toOption.getD Json.null
      errors.putStrLn (timingLine request reply ((← IO.monoMsNow) - started))
      errors.flush
  return 0
