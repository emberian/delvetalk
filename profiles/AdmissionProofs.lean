/- Small proofs connected to the actual host commit boundary. These quantify over
   the selected admission callback, including Compiled.transition, rather than
   specializing the default runtime whose source hooks deliberately refuse.
   Authorization and typed source correctness remain their separate obligations. -/
import WorldCore
open Lean World

namespace World
set_option autoImplicit false

/-- Any failing admission (including a failure after staged source calls, guard
    evaluation, allocation or message staging) keeps the complete original world
    at the actual commit boundary and emits only its refusal. -/
theorem admissionOutcome_error (world request : Json) (error : String) :
    admissionOutcome world request (.error error) =
      (world, receipt request "refused" (.str error)) := rfl

/-- The same boundary commits exactly a successful admission's returned pair. -/
theorem admissionOutcome_ok (world request next outcome : Json) :
    admissionOutcome world request (.ok (next, outcome)) = (next, outcome) := rfl

/-- Callback-parametric rollback: executable retirement cannot make this theorem
    vacuous by replacing its source evaluator with a refusing default runtime.
    handleWith calls this exact helper before appending the retained receipt. -/
theorem admission_callback_rollback
    (admit : Json → Json → String → Except String (Json × Json))
    (world request : Json) (principal error : String)
    (refused : admit world request principal = .error error) :
    (admissionOutcome world request (admit world request principal)).1 = world := by
  rw [refused]
  rfl

/-- Successful exact-preimage checking used by the receiving path observes the
    actual expected field and its complete Json comparison, not a version only. -/
theorem rootCheck_success (root request : Json)
    (accepted : rootCheck root request = .ok ()) :
    ∃ expected, field request "expected" = .ok expected ∧ (root != expected) = false := by
  unfold rootCheck at accepted
  cases parsed : field request "expected" with
  | error error =>
      rw [parsed] at accepted
      change (Except.error error : Except String Unit) = .ok () at accepted
      cases accepted
  | ok expected =>
      cases compared : (root != expected) with
      | false => exact ⟨expected, rfl, compared⟩
      | true =>
          rw [parsed] at accepted
          change (if (root != expected) = true then (Except.error "stale read root" : Except String Unit) else .ok ()) = .ok () at accepted
          simp only [compared] at accepted
          cases accepted

end World

#print axioms World.admission_callback_rollback
#print axioms World.rootCheck_success
