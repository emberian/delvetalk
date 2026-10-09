# The Night Garden

Two participants grow one imaginary flower: one plants a seed under amber, violet
or silver light; another adds rain. Each season preserves the last completed
flower and both admitted authors.

[Garden.obend](Garden.obend) owns behavior and views. Typed `plantTurn`/`rainTurn`
receive `(state,input,{object,principal})` and return `{accepted,reason,state,result}`.
One compiled Lean execution decides complete state replacement or atomic refusal.
Identity comes from admission; current law, exact roots and retained receipts apply.

[binding.json](binding.json) supplies bindings, initial data, forms and panels;
[protocol.json](protocol.json) bundles exact source. Rebuild with
`syntaxes.source_bundle.load(binding_path, [('Garden', source_path)])` and serialize
its result. Use the **compiled** profile. [law.json](law.json) supplies local fixture
grants, not public enrollment; choose actual instance grants explicitly. Management
authority grants no play rights.

Plant accepts `{seed,colour}`; rain accepts `{line}` from someone other than the
planter. Typed inputs reject extra fields. Forms limit seed/rain to 80/240
characters; these are presentation bounds, **not raw-call length checks**. Raw
calls retain the host request limit. Panels share one captured root; `next` follows
the phase. Uncertain replies retry the identical request/intent, including its root.

## Migrate explicitly

State now lives under `state.value`; `hasCompleted` distinguishes an empty, fixed-shape
`lastCompleted`. [migration.json](migration.json) seeds a **new** garden, never an
inhabited replacement. [legacy-v1.json](legacy-v1.json) preserves old protocol bytes.

Select `migrateEmpty` for an old empty completion or `migrateComplete` for a full
one. Evaluate that source export through the compiled host, review its preserved
contributions/authors against the exact old root, then submit authorized `reprogram`.
[The inhabited example](migration-example.json) shows before/after. No implicit
reset occurs. Old receipts remain recoverable; migration stales uncommitted cards.

With the host prebuilt, run `python3 conformance/test_garden_source.py` for
[receiving/migration checks](../../conformance/test_garden_source.py). This new source
profile is local and **not deployed**; it introduces no scheduler or external effects.
