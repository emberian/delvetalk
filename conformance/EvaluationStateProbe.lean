import EvaluationState
import ProgramDigest
open Lean World

private def require (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw (IO.userError message)

private def spec (n : Nat) : Json := toJson n
private def compiler (source : Json) : Except String Json := pure source
private def unavailable (_ : Json) : Except String Json := throw "compiled twice"
private def errorIs (result : Except String α) (expected : String) : Bool :=
  match result with
  | .error error => error == expected
  | .ok _ => false

private def cached := Evaluation.checkedArtifact "source-v1"

private def probe : IO Unit := do
  let action : Evaluation (Json × Nat) := do
    let first ← cached compiler (spec 42)
    set (97 : Nat)
    let hit ← cached unavailable (spec 42)
    unless first == hit do throw "artifact changed"
    let (_ : Unit) ← (do
      let remaining ← get
      set (remaining - 3) : StateT Nat (Except String) Unit)
    return (hit, ← get)
  require (match action.run 100 with
    | .ok ((value, inside), remaining) => value == spec 42 && inside == 94 && remaining == 94
    | .error _ => false) "budget or cached artifact drift"
  -- A fresh run cannot inherit prior custody, including when its fuel matches.
  require (errorIs ((cached unavailable (spec 42)).run 100) "compiled twice") "cross-turn cache"
  let isolation : Evaluation Unit := do
    discard (cached compiler (spec 42))
    discard (Evaluation.checkedArtifact "source-v2" unavailable (spec 42))
  require (errorIs (isolation.run 100) "compiled twice") "compiler namespace alias"
  let changed : Evaluation Unit := do
    discard (cached compiler (spec 42))
    discard (cached unavailable (spec 43))
  require (errorIs (changed.run 100) "compiled twice") "source identity alias"
  let bounded : Evaluation Unit := do
    for n in List.range 20 do discard (cached compiler (spec n))
  let .ok (_, state) := StateT.run bounded { remaining := 100 } | throw (IO.userError "bounded compile failed")
  require (state.checkedArtifacts.length == 8) "entry ceiling"
  require ((state.checkedArtifacts.map CheckedArtifact.bytes).foldl (· + ·) 0 ≤ Evaluation.artifactLimit) "byte ceiling"
  let large := Json.str (String.join (List.replicate 8193 (String.ofList (List.replicate 1024 'x'))))
  let .ok (_, largeState) := StateT.run (cached compiler large) { remaining := 100 }
    | throw (IO.userError "large uncached compilation failed")
  require largeState.checkedArtifacts.isEmpty "oversized artifact entered custody"
  let program := Json.str (String.ofList (List.replicate 4096 'x'))
  let allowance := 100000
  let .ok (firstHash, firstLeft) := (ProgramDigest.digest program).run allowance
    | throw (IO.userError "fingerprint miss failed")
  let firstCost := allowance - firstLeft
  require (firstCost > 0) "fingerprint miss restored fuel"
  require (errorIs ((ProgramDigest.digest program).run (firstCost - 1)) "invocation budget exhausted")
    "fingerprint miss ignored fuel"
  let twice : Evaluation (String × String) := do
    let first ← ProgramDigest.digest program
    let second ← ProgramDigest.digest program
    pure (first, second)
  let .ok ((first, second), twiceLeft) := twice.run allowance
    | throw (IO.userError "fingerprint hit failed")
  let hitCost := firstLeft - twiceLeft
  require (first == firstHash && second == firstHash) "fingerprint hit changed identity"
  require (hitCost > 0 && hitCost < firstCost) "fingerprint hit uncharged or rehashed"
  require (errorIs (twice.run (firstCost + hitCost - 1)) "invocation budget exhausted")
    "fingerprint hit restored or ignored fuel"
  -- A fresh turn pays a miss even after an identical successful prior turn.
  require (errorIs ((ProgramDigest.digest program).run hitCost) "invocation budget exhausted")
    "fingerprint leaked across turns"
  let changedPrograms : Evaluation Unit := do
    discard (ProgramDigest.digest program)
    discard (ProgramDigest.digest (.str (String.ofList (List.replicate 4096 'y'))))
  require (errorIs (changedPrograms.run (firstCost + hitCost)) "invocation budget exhausted")
    "different exact protocol reused a fingerprint"
  let scales : Evaluation (String × String) := do
    let first ← ProgramDigest.digest (.num ⟨120, 2⟩)
    let second ← ProgramDigest.digest (.num ⟨12, 1⟩)
    pure (first, second)
  let .ok ((scaledA, scaledB), _) := scales.run allowance
    | throw (IO.userError "exact scale digest failed")
  require (scaledA != scaledB) "fingerprint equality erased exact decimal scale"
  let fingerprints : Evaluation Unit := do
    for n in List.range 20 do discard (ProgramDigest.digest (toJson n))
  let .ok (_, fingerprintState) := StateT.run fingerprints { remaining := allowance }
    | throw (IO.userError "bounded fingerprints failed")
  require (fingerprintState.programFingerprints.length == 8) "fingerprint entry ceiling"
  require ((fingerprintState.programFingerprints.map ProgramFingerprint.bytes).foldl (· + ·) 0 ≤ ProgramDigest.fingerprintLimit)
    "fingerprint byte ceiling"
  IO.println "per-turn artifact/fingerprint custody, exact identity, bounded memory and charged miss/hit fuel pass"

#eval probe
