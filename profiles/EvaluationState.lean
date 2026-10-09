/- Per-turn computation custody. This module knows neither source compilation
nor world authority: the receiving compiler alone may retain checked artifacts. -/
import Lean

namespace World
open Lean

structure CheckedArtifact where
  compilerNamespace : String
  /-- Full source descriptor: module names, source/aliases, entry and limits. -/
  specification : Json
  artifact : Json
  bytes : Nat

structure ProgramFingerprint where
  program : Json
  hash : String
  bytes : Nat

structure EvaluationState where
  remaining : Nat
  checkedArtifacts : List CheckedArtifact := []
  programFingerprints : List ProgramFingerprint := []

abbrev Evaluation := StateT EvaluationState (Except String)

/-- Existing logical-budget code accesses only the same Nat allowance. -/
instance : MonadStateOf Nat Evaluation where
  get := fun state => .ok (state.remaining, state)
  set remaining := fun state => .ok ((), { state with remaining })
  modifyGet f := fun state =>
    let (value, remaining) := f state.remaining
    .ok (value, { state with remaining })

/-- Existing bounded data work retains precisely its errors and fuel charges. -/
instance : MonadLift (StateT Nat (Except String)) Evaluation where
  monadLift action := fun state => do
    let (value, remaining) ← action.run state.remaining
    return (value, { state with remaining })

namespace Evaluation

/-- Every top-level run starts with empty custody. The returned logical allowance
and external result are unchanged; artifacts cannot survive to another turn. -/
def run (action : Evaluation α) (remaining : Nat) : Except String (α × Nat) := do
  let (value, state) ← StateT.run action { remaining := remaining }
  return (value, state.remaining)

def artifactLimit : Nat := 8 * 1024 * 1024

def fitArtifacts : Nat → List CheckedArtifact → List CheckedArtifact
  | _, [] => []
  | capacity, entry :: rest =>
    if entry.bytes ≤ capacity then entry :: fitArtifacts (capacity - entry.bytes) rest else []

/-- Exact descriptor equality includes every source namespace and assumption
preimage. This cache is scoped to one run of one linked receiving compiler, so
compiler closure/version identity is fixed by construction and cannot drift. -/
def checkedArtifact (compilerNamespace : String) (compile : Json → Except String Json) (specification : Json) : Evaluation Json := do
  let state ← getThe EvaluationState
  if let some entry := state.checkedArtifacts.find? (fun entry => entry.compilerNamespace == compilerNamespace && entry.specification == specification) then
    return entry.artifact
  let artifact ← compile specification
  let bytes := compilerNamespace.utf8ByteSize + specification.compress.utf8ByteSize + artifact.compress.utf8ByteSize
  if bytes ≤ artifactLimit then
    set { state with checkedArtifacts :=
      ⟨compilerNamespace, specification, artifact, bytes⟩ :: fitArtifacts (artifactLimit - bytes) (state.checkedArtifacts.take 7) }
  return artifact

end Evaluation
end World
