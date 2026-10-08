# Compact-context reconstruction

This second experiment gives fresh, instruction-isolated agents only a single
2 KB capsule and the 852-byte `WIRE.txt`. They do not receive the first trial's
6,664-byte AST document, existing implementations, reference source, tests,
other capsules, prior experiment reports, or semantic help from peers.
Isolation is a task instruction, not an operating-system access restriction.

| Candidate | Capsule bytes | Wire bytes | Total supplied text |
| --- | ---: | ---: | ---: |
| Machine | 1,995 | 852 | 2,847 |
| Algebra | 1,994 | 852 | 2,846 |
| Rewrite | 1,945 | 852 | 2,797 |

The directory name is shorthand: these are capsule **plus compact wire**
reconstructions. All counted supplied text fits below 3,000 bytes. The wire
still specifies some semantics, including fuel and free reply insertion;
its full cost is included rather than treated as free background knowledge.

After authors declare their candidates complete, run:

```sh
python3 experiments/capsule-only/run.py --candidates-ready
```

`--styles algebra` examines only that completed candidate; `--timeout` changes
the default two-second per-job deadline. The examiner reuses the first trial's
process isolation and exact result comparison, including residual contexts,
duplicate-field ordering, and Boolean-versus-number distinctions. Each case
runs in its own process, so a divergence or exception cannot hide later cases.
No candidate is repaired after examination. `results.json` retains precise
inputs and hashes, observations, and execution failures. The semantic benchmark
is the same 263 source-derived cases: 68 shared plus 195 adversarial cases.

Full-wire malformed-input checks are reported **informationally**, separately
from semantic performance. The compact wire does not state all first-trial
validation rules (canonical Nat spelling, unknown members, unused-response
validation, Unicode scalar restrictions, or the 2^53-1 interchange ceiling).
Different behavior on those checks is not automatically a compact-contract
failure and does not affect the examiner's exit status. In particular,
accepting indices above the first trial's ceiling can be appropriate here.
The zero-fuel large-index semantic fixtures remain legitimate observations:
an unapplied rewrite must leave the residual term unchanged.

The examiner exits nonzero on a semantic observation mismatch or execution
failure. It does not prove refinement or complete reconstruction of the
capsule's object/authority prose; the supplied runner interface exercises only
pure core evaluation with explicit replies. Candidate implementation mistakes,
underspecified wire behavior, and capsule omissions must be distinguished by
reading the actual supplied text and source rules, not by majority vote.

## Results

| Candidate | Total input bytes | Exact semantic matches | Semantic mismatches | Execution failures |
| --- | ---: | ---: | ---: | ---: |
| Machine | 2,847 | 103/263 | 160 | 0 |
| Algebra | 2,846 | 263/263 | 0 | 0 |
| Rewrite | 2,797 | 263/263 | 0 | 0 |

The machine candidate charges one step for encountering `perform`. At zero
fuel it therefore reports `exhausted` before recording the plan or inserting a
reply. All 160 differences occur at that boundary: three shared zero-fuel
cases, 121 nested yield/resumption cases, and 36 zero-fuel resumption cases
whose next contraction must remain unapplied. For example, a zero-fuel
`perform(query)` should yield with the raw plan recorded; the candidate instead
returns `exhausted` with an empty plan list. There were no crashes, timeouts,
missing output fields, or residual-order errors classified separately.

The machine author's frozen notes explicitly identify charging a perform
encounter as an assumption. Its coroutine capsule does not enumerate a
small-step relation, and the compact wire says replies are free without
explicitly saying that reaching a yield is free. This is a specification
ambiguity exposed by the tighter context, rather than evidence of a bug in
the source semantics. Algebra and rewrite capsules distinguish the reduction
relation from yielding, and their reconstructions matched every observation.
The experiment therefore locates a specific missing clarification for the
machine presentation; it does not justify silently repairing that candidate
or claiming the original text was unambiguous. No capsule or candidate was
changed for this examination.

All three candidates rejected 16 of the 21 informational full-wire probes.
That count is not a compact-contract score: the original interface's stricter
validation requirements were deliberately omitted. Exact accepted inputs and
diagnostics are retained in `results.json`.

The two passing reconstructions provide bounded evidence that their full
supplied context, under 3 KB including the interface, communicates the pure
core behavior exercised here. Object authority, durable activity, transactions,
and host semantics remain outside this experiment. These are three individual
agent runs, not a statistical comparison of representational styles.
