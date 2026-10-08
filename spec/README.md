# Source relation and executable reference

`upstream/Theory/ObjectiveBendOpenRecursion.lean` and `AxiomPin.lean` are
byte-for-byte copies from Mini. `upstream.json` pins their origin and SHA-256.
They define the normative finite-tree source terms, substitution, weak-head
call-by-name `Step`, values, evaluation contexts, `Yields`, and interaction.
They do not define the complete typed surface or hosted object protocol.

`Delvetalk/Core.lean` implements a computable inspection of those source terms. The
`View` result carries an upstream `Step t next`, `Value t`, or
`Yields t plan frames` proof for every positive result. These evidence fields
are kernel-checked and erased by code generation. A `stuck` result currently
carries no negative proof: completeness of inspection is not established.
The wire parser and bounded runner are executable code, not a verified parser
or a proof of whole-run equivalence. The source uses only Lean's standard
axioms; this driver introduces no axioms or sorry placeholders.

`Main.lean` is the JSONL command-line wrapper; host profiles may import
`Delvetalk.Core` to reuse the same evaluator and term codecs.

This is not the demand machine relabeled as a source trace. Each fuel tick
executes one actual source `Step`. A yield records its raw, unforced plan and
consumes no fuel. A supplied response is plugged into the innermost-first
source context without consuming fuel. Terminal classification precedes the
fuel check, so a zero-budget value/stuck/yield can still be reported accurately.
Resource exhaustion means a next source step exists but has no remaining fuel.

Build with Lean 4.34.1 as pinned in `lean-toolchain` (narrow dependency chain,
no Mathlib). The upstream Mini files remain byte-identical to their source
pin; the newer compiler requires no semantic or proof compatibility edits:

```sh
LEAN_NUM_THREADS=1 lake build
printf '%s\n' '{"name":"identity","term":["app",["lam",["bound",0]],["nat","42"]],"fuel":1}' | .lake/build/bin/delvetalk
python3 scripts/crosscheck.py --engines lean python
```

The default `python3 scripts/crosscheck.py` requires all four implementations.
A selected-engine development run is explicitly scoped in its JSON report.
Compiled C emitted by Lean's build is not the independently authored C engine.
