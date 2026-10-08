# Capsule-only algebra reconstruction

Semantic/interface input inventory:

- `/Users/ember/dev/delvetalk/capsules/algebra-2k.txt`: 1994 bytes; SHA-256 `c56fd3579526f88d1d3f7a892647f47618142474491a11375545c682874a1442`.
- `/Users/ember/dev/delvetalk/experiments/capsule-only/WIRE.txt`: 852 bytes; SHA-256 `a59335e3c227b48b110bbb329580cc4f90574d6a47176a752e1b277d4a27b741`.

Total input bytes: 2846.

## Interpretations and ambiguities

- The host skeleton supplies no executable JSONL host operations. This evaluator implements all exposed term dynamics and suspensions; it does not invent storage, authority, or commit inputs.
- Wire `project` means algebra `target`; `ifZero` means `natcase`, whose third argument binds the predecessor. Each case arm binds the injected payload.
- Source fuel counts each primitive rewrite exactly once, including `mix`, `fix`, `done`, selectors, and beta reduction. Context traversal, reporting terminal states, and reply insertion cost no steps.
- With zero remaining fuel, values and stuck terms are classified directly and yields may still consume available replies; an available source reduction reports `exhausted` without taking it. The texts do not explicitly specify tie-breaking between exhaustion and free observations.
- Each reached `perform` contributes its raw, unevaluated plan once, including the final unanswered yield. An unanswered yield returns the whole residual with its context; replies replace the perform hole verbatim.
- Values retain all unevaluated components. Application never evaluates the argument. Strict binary evaluation visits its left operand, then its right only when the left is a value, before checking scalar types.
- Fields and arms preserve order and duplicates. Lookup uses the first match; extension prepends every supplied field, filtering all old occurrences of supplied keys.
- Naturals accept nonempty ASCII digit strings, preserving their spelling until a rule computes a new natural. Scalar results use canonical decimal spelling. No fixed integer limit is imposed.
- Well-formed open De Bruijn terms are accepted and are stuck when a free bound variable is reached. Substitution traverses all suspended components and accounts for lambda, successor-body, and case-arm binders.
- Unused responses are ignored. Blank JSONL lines are malformed. Malformed input produces a stderr diagnostic and nonzero process exit.

## Local verification

Only self-authored smoke examples were used; no existing implementation, tests, docs, other capsules, or held-out cases were read. No external dependencies are used.
