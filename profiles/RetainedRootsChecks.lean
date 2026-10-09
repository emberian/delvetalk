/- Direct adversarial checks of the same resolver used by receiving. A forced
   digest collision is constructed here; no testing mutation exists in the host. -/
import RetainedRoots
open Lean World RetainedRoots

private def refused (result : Except String Json) (reason : String) : Bool :=
  match result with
  | .error error => error == reason
  | .ok _ => false

def checks : IO Unit := do
  let reference := obj [("profile", .str profile), ("object", .str "object"), ("key", .str "forced")]
  let collision : Index := ({} : Index).insert ("object", "forced") #[.str "first", .str "second"]
  unless refused (resolve collision "object" reference) "ambiguous retained root reference" do
    throw (IO.userError "collision must refuse")
  let retained : Index := ({} : Index).insert ("object", "forced") #[.str "exact"]
  unless (resolve retained "object" reference).toOption == some (Json.str "exact") do
    throw (IO.userError "locator must return the full retained Json")
  unless refused (resolve retained "other" reference) "retained root reference object differs" do
    throw (IO.userError "object binding must refuse")
  unless (resolve retained "object" .null).toOption == some Json.null do
    throw (IO.userError "absence must remain distinct")

#eval checks
