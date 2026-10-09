/- Read-only diagnostic of the actual source receiving Evaluation.run result,
including the final logical allowance. Use against immutable native snapshots. -/
import Compiled
open Lean World

private def probe : IO Unit := do
  let some path ← IO.getEnv "DELVETALK_COUNTER_PROBE"
    | throw (IO.userError "DELVETALK_COUNTER_PROBE requires an exact world/request frame")
  let text ← IO.FS.readFile path
  let .ok frame := Json.parse text | throw (IO.userError "invalid probe JSON")
  let evaluate (frame : Json) : Json :=
    let result := do
      let world ← field frame "world"
      let request ← field frame "request"
      let ((next, receipt), remaining) ←
        (World.transitionEvaluationWith Compiled.runtime world request (← str request "principal")).run Compiled.runtime.budget
      return obj [("world", next), ("receipt", receipt), ("remaining", toJson remaining)]
    match result with
    | .ok output => output
    | .error error => obj [("error", .str error)]
  match frame.getArr? with
  | .ok frames => IO.println (Json.arr (frames.map evaluate)).compress
  | .error _ => IO.println (evaluate frame).compress

#eval probe
