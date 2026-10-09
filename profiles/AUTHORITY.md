# Scoped local authority

**Current law admits each new operation; retained receipts answer exact retries.**
[WorldCore](WorldCore.lean) owns both checks. Legacy laws such as `["alice","bob"]`
grant every listed principal invocation, programming and law revision. Creator
and `owner` names confer nothing implicitly.

```json
{"profile":"delvetalk-scoped-law-v1",
 "invoke":{"play":["alice","bob"],"review":["reviewer"]},
 "reprogram":["programmer"],"law":["steward"]}
```

All four fields are required; only optional `predicate` is additional.
Command names match exactly: missing names grant nobody, `*` is literal,
and an invocation named `reprogram` grants no management right. Grants may
precede command installation. Current law governs replacement of either law
representation; proposed law cannot authorize itself. Replacement increments
version. Programming preserves law. Empty grants deliberately lock out mutations
without recovery. Reads and snapshots remain public. Local principals are caller
assertions; the live clerk supplies repository-derived identities.

**Predicates restrict grants.** `predicate` is a decoded core-array Bend term
applied to `{principal,op,command,state,input}`. Invocation supplies the actual
command, complete staged state and resolved input. Management supplies command
`""` and input `{}`; candidates are absent. The old predicate governs replacement.
Only Boolean true admits; false, wrong kinds, effects, stuck evaluation or
exhaustion refuse atomically. Exact retries bypass reevaluation, even after
changed grants; a formerly refused request needs a new intent.

Predicate contexts accept only Nat, Bool, String and records, recursively to
depth 64. Any incompatible field refuses, even unused. Without a predicate or
invariant, state/input retain unrestricted JSON. A predicate alone checks the old
state during programming; installing incompatible state can lock out future operations.

**One budget covers policy and execution:** 10,000 ticks normally; 100,000 in
[compiled](COMPILED.md). Transactions share it across all steps, conversions,
bodies, results and outboxes. Every callee checks the global principal against
its staged law/state; prior results transfer data, never authority. Structural
validation and grant membership are envelope-bounded, not a complete resource tariff.

**Receiving invariants survive programming.** Opt into `delvetalk-scoped-law-v2`
with the same grants, optional `predicate`, and required `invariant`: a pure
core Bend function over `{object,principal,op,command,state,nextState,input}`.
It checks every candidate state before staging. Unlike a command guard, it lives
in law; installing new code cannot remove it. The core term is an operator
representation, not a required resident spelling. Reusing the existing pure
evaluator keeps one budget and avoids giving a law its own compiler or effects.

Invocations use actual staged state, resolved input and their receiving command;
`nextState` is the complete proposed state, including source-transition results.
Programming checks its explicit replacement against installed law. Creation,
including factory children, uses `state = nextState = initial`, `op = "create"`,
the new object's identity and actual caller. Management/creation use `command =
""` and `input = {}`. Conversion restrictions above apply to both states and input.

Law revision requires the **old and proposed invariants** to accept the unchanged
state under `op = "law"`; old grants/predicate authorize it first. An authorized
manager can deliberately remove an invariant by installing v1 if the old
invariant admits that revision. There is no owner bypass. Schema evolution can
first install a bridging invariant, migrate, then tighten it. State acceptance
does not certify compatibility of replacement code or all future states.

Only Boolean true admits. False, non-Boolean, stuck/effectful evaluation and
budget exhaustion retain refusal without object changes, allocated children or
outboxes—even after earlier transaction steps. Historical retries still recover
before reevaluation. V1 and principal-array laws add no invariant check.

Checks: `python3 conformance/test_authority.py` and
`python3 conformance/test_state_invariant.py`.
[Cases](../conformance/test_authority.py) cover lockout, migration, current grants,
historical retries, staged policies, shared budgets and atomic desk adoption.
