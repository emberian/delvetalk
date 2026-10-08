# Capsule reconstruction experiment

Three isolated agent lanes each receive one 2 KB capsule (`machine`, `algebra`,
or `rewrite`) and `conformance/AST.md`, and independently implement a Python
JSONL evaluator. The capsule and the wire document have separate byte counts;
this is **not** a claim that the entire executable specification fits in 2 KB.
The wire document includes semantic guidance as well as serialization rules.

Isolation is enforced by task instructions, not an operating-system sandbox.
Candidate authors must not inspect source implementations, other candidates,
fixtures, or examiner reports while constructing their evaluator. The examiner
waits until authors declare completion before reading or executing candidates.
It supplies no corrective semantic hints and does not repair candidate code.
The candidates remain the original experimental artifacts, including failures.

After all authors have finished:

```sh
python3 experiments/blind/run.py --candidates-ready \
  --cases conformance/cases.json --cases conformance/adversarial-cases.json
```

Use repeated `--cases` arguments to evaluate the shared corpus and additional
source-backed adversarial fixtures together. `--styles machine` selects a
completed candidate without reading unfinished candidates. Each job runs in a
fresh process with a two-second deadline; one divergent candidate cannot block
the rest of the corpus. `--timeout` changes that deadline. Reports retain exact
mismatches, including missing residual fields and reordered duplicate fields.
JSON object member order and whitespace are ignored, while array order and
Boolean/numeric distinctions are preserved.

`results.json` records source, capsule, wire-document and implementation hashes,
byte counts, per-case outcomes, and separate malformed-wire results. A timeout
or exception is an execution failure, not a semantic `stuck` observation.
Malformed inputs must produce a nonzero exit and a diagnostic, not a semantic
result. Duplicate JSON object keys are outside the wire profile and are not
tested. The examiner exits nonzero if any candidate fails; this experiment is
not part of `make check` and should not be made green by editing candidates.

## First examination

All three frozen candidates passed all **263 semantic cases** (68 shared and
195 held-out source-derived cases) and **21 malformed-wire cases**. No candidate
was repaired or given examiner feedback before completion. The exact supplied
wire document is retained at `inputs/AST.md` (6,664 bytes), independently of
later clarifications to the repository's current wire documentation.

| Candidate | Capsule bytes | Wire bytes | Total supplied text | Semantic | Malformed wire |
| --- | ---: | ---: | ---: | ---: | ---: |
| Machine | 1,995 | 6,664 | 8,659 | 263/263 | 21/21 |
| Algebra | 1,994 | 6,664 | 8,658 | 263/263 | 21/21 |
| Rewrite | 1,945 | 6,664 | 8,609 | 263/263 | 21/21 |

There are no observed failures to attribute to capsule omissions or candidate
implementation errors in this corpus. The authors independently identified one
wire ambiguity: the required job `name` field has no explicit type declaration;
all chose a Unicode scalar string. That agreement is an assumption, not a
deduction from a stated field type. The machine author also identified that
counting each coroutine equation as one source reduction is an interpretation
needed to recover the precise fuel observations. The held-out cases support
that interpretation without making it a proof for every term.

This result does **not** establish reconstruction from a 2 KB capsule alone:
the 6,664-byte wire document supplies binding, strictness, fuel, reply,
validation, and retained-context details. Nor does this experiment exercise the
durable object skeleton that each capsule also describes. A next compression
experiment should hold a genuinely syntax-only wire schema fixed, then compare
reconstruction from different capsule sizes; removing supplied semantic hints
would create a different experiment and needs new blinded implementations.

Passing these examples supports reconstruction of the pure core under this
particular supplied context. It proves neither completeness of a capsule nor
correctness of the object model, typechecker, host, or deployment. Failure
analysis must distinguish capsule omissions from mistakes implementing rules
that the capsule or wire document actually states. Read the pinned source when
settling that distinction; do not infer a normative rule from majority vote.
