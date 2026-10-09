/- Direct checks of local verdict reuse in the actual candidate admission hook.
   The instrumented guard spends one unit and checks its complete context. -/
import WorldCore
open Lean World

private def authority (config : String) : Json := obj [
  ("profile", .str "delvetalk-scoped-law"),
  ("amendment", obj [("config", .str config)])]

private def root (config : String) : Json := obj [("law", authority config), ("state", obj [])]

private def request : Json := obj [("op", .str "law"), ("object", .str "object")]

private def counted (before after : Json) : Runtime := {
  checkSourceAmendment := fun amendment actualBefore actualAfter actualRequest principal => do
    unless actualBefore == before && actualAfter == after && actualRequest == request && principal == "caller" do
      throw "amendment context changed"
    if (← str amendment "config") == "refuse" then throw "old guard refused"
    tick }

private def acceptedWith (result : Except String (Unit × Nat)) (remaining : Nat) : Bool :=
  match result with
  | .ok (_, rest) => rest == remaining
  | .error _ => false

def amendmentReuseChecks : IO Unit := do
  let before := root "same"
  let after ← IO.ofExcept (put before "version" (toJson (1 : Nat)))
  let action := checkCandidateWith (counted before after) before after request "caller"
  unless acceptedWith (action.run 1) 0 do
    throw (IO.userError "identical amendment must consume exactly one guard evaluation")
  let changed := root "changed"
  let actionChanged := checkCandidateWith (counted before changed) before changed request "caller"
  unless acceptedWith (actionChanged.run 2) 0 do
    throw (IO.userError "changed amendment must evaluate both guards against the same context")
  if (actionChanged.run 1).isOk then
    throw (IO.userError "changed amendment cannot reuse the old verdict")
  let refused := root "refuse"
  if ((checkCandidateWith (counted refused refused) refused refused request "caller").run 1).isOk then
    throw (IO.userError "identical amendment cannot bypass an old refusal")
  let twice : Evaluation Unit := do action; action
  unless acceptedWith (twice.run 2) 0 do
    throw (IO.userError "verdict reuse cannot cross candidate checks")
  if ((checkCandidateWith {} before after request "caller").run 2).isOk then
    throw (IO.userError "default runtime cannot reuse an unchecked verdict")

#eval amendmentReuseChecks
