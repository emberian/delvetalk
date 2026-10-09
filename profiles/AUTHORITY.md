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
depth 64. Any incompatible field refuses, even unused. Without predicates,
state/input retain unrestricted JSON. Programming incompatible state can lock out
future operations.

**One budget covers policy and execution:** 10,000 ticks normally; 100,000 in
[compiled](COMPILED.md). Transactions share it across all steps, conversions,
bodies, results and outboxes. Every callee checks the global principal against
its staged law/state; prior results transfer data, never authority. Structural
validation and grant membership are envelope-bounded, not a complete resource tariff.

Check: `python3 conformance/test_authority.py`.
[Cases](../conformance/test_authority.py) cover lockout, migration, current grants,
historical retries, staged policies, shared budgets and atomic desk adoption.
