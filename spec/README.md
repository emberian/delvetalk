# Source relation and executable reference

DelveTalk maintains its own Objective Bend edition in `bend/`. Mini supplies
its attributed upstream baseline; local semantics, typing, compiler and demand
machine are editable source. [origin.json](bend/origin.json) records the upstream
repository, commit and original-file hashes. That inventory is attribution, not a
constraint on current files, and need not change when local modules change.

The edition includes hosted text semantics and local frontend changes. It is not
a byte-exact Mini release. [Hosted text](../docs/design/TEXT.md) specifies its
Unicode and resource behavior. Runtime source pins bind the actual local closure;
there is no replacement-reconstruction requirement for editing the fork.

The core relation defines finite-tree terms, substitution, weak-head call-by-name
`Step`, values, evaluation contexts, `Yields` and interaction. It does not by itself
define the complete typed surface or hosted object protocol.

`Delvetalk/Core.lean` implements a computable inspection of those source terms. The
`View` result carries an edition `Step t next`, `Value t`, or
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

Build with Lean 4.34.1 as pinned in `lean-toolchain` (no Mathlib). Proofs and
source inspection refer to this edition. Independent Python/C/JS evaluators cover
their shared fragment; their agreement does not qualify extensions they lack.

```sh
LEAN_NUM_THREADS=1 lake build
printf '%s\n' '{"name":"identity","term":["app",["lam",["bound",0]],["nat","42"]],"fuel":1}' | .lake/build/bin/delvetalk
python3 scripts/crosscheck.py --engines lean python
```

The default `python3 scripts/crosscheck.py` requires all four implementations.
A selected-engine development run is explicitly scoped in its JSON report.
Compiled C emitted by Lean's build is not the independently authored C engine.
