# Silence and settlement: scoped audit

2026-10-08 source inspection; no tests/builds or deployment verification performed.
DelveTalk HEAD: `4169f086bdb25f139df28c7e5b949cee9b21b6c5`.

**Observation timeout does not establish application failure.** The
[service recovery test](../conformance/test_service.py),
`test_lost_receiving_reply_keeps_same_uri_and_reconciles_without_duplicate_admission`,
commits, raises `TimeoutError`, then recovers the receipt without another admission.
The [world adversarial test](../conformance/test_world_adversarial.py),
`test_post_replace_fsync_failure_is_uncertain_but_retry_recovers`, likewise covers
persistence followed by an error. Preserve the original attempt and recover its
receipt; killing a timed-out process cannot undo a prior commit.

**Admission budget refusal is different.** [Compiled.evaluateExtra](../profiles/Compiled.lean)
converts non-finished package execution into refusal;
[WorldCore.handleWith](../profiles/WorldCore.lean) retains that outcome.
[`test_package_calls_share_one_budget_and_failure_is_retained`](../conformance/test_compiled.py)
asserts `tickExhausted`, unchanged application state and identical replay.
Exhaustion being distinct from calculus stuckness does not preclude authoritative
host refusal.

**Slot safety does not imply liveness.** Mini's
[ObjectiveActivity](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Kernel/ObjectiveActivity.lean)
proves single-decider and consume-once safety conditional on admitted installation.
Below-cap exhaustion preserves the await; resumed exhaustion at the turn cap
becomes `faulted`. [ObjectiveResumeContract](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Kernel/ObjectiveResumeContract.lean)
binds generation advancement to the installed record. These establish neither
scheduler progress nor eventual settlement. A host's authoritative deadline is
separate from a caller's observation deadline.

**Profiles remain separate.** DelveTalk's [raw evaluator](../spec/Delvetalk/Core.lean)
distinguishes `stuck`, `yield` and `exhausted`; its
[typed adapter](../spec/Delvetalk/Typed.lean) checks without evaluating or admitting.
Its synchronous receipt host does not implement Mini's durable activity lifecycle.
Consequently a complete evaluator-context/slot integration claim is unsupported;
that is a scope limit, not evidence of a broken Mini slot.

Two operational bounds gaps remain:

- [Worker.run](../scripts/worker.py) stores `TimeoutExpired` as text but can leave
  `deadlineReached` false on the final entry. Repair diagnostic classification
  and deadline accounting while preserving phase/identity. Existing
  [worker tests](../conformance/test_worker.py) cover pre-entry deadline checks
  and process-group termination, not this final-entry reporting case.
- [world.exchange](../scripts/world.py) and [Clerk.receive](../scripts/clerk.py)
  use blocking locks; world invocation has no subprocess timeout. The outer
  worker/service production launcher supplies the execution bound; direct and
  injected in-process calls do not. [Town.receive](../scripts/town.py)'s own lock
  deadline also does not bound its direct clerk call.
