# Blind algebra reconstruction

This independent Python tree evaluator was written using exactly these semantic/wire inputs:

| Input | Bytes |
| --- | ---: |
| `capsules/algebra-2k.txt` | 1,994 |
| `conformance/AST.md` | 6,664 |
| Combined | 8,658 |

Sizes are raw filesystem byte counts. The capsule and wire schema are separately counted. No existing implementation, normative source, held-out corpus, repository tests, other capsule, history, network source, or peer semantic answer was consulted.

Run from the repository root:

```sh
python3 experiments/blind/algebra/evaluator.py < jobs.jsonl
```

The executable uses only Python's standard library. Each input line produces one compact JSON result. Malformed input or execution failure produces a line-numbered diagnostic on stderr and exits nonzero. Successful preceding lines remain emitted.

## Reconstruction decisions

- The algebra supplies the reductions and permitted evaluation contexts. The AST document supplies constructor/primitive spellings, binder positions, validation constraints, and the complete fuel/reply/result protocol.
- `equal` compares Naturals only; `labelEqual` compares labels only. Boolean equality has no primitive in the supplied list.
- All source weak-head values count as values for binary context selection. Thus the right operand runs after a wrong-typed left value before the primitive becomes stuck.
- `mix(a,b)` takes one source step to two lambdas whose body is `b s (a s p)`. Both original components shift by two, preserving references underneath their own binders. No component is evaluated during construction.
- `fix(e,p)` takes one step to `(e (fix(e,p))) p`. The repeated extension and seed are copied structurally without implicit prototype construction.
- Beta reduction, successor matching, and case matching remove one binder through capture-avoiding substitution. All lazy components participate in substitution, while only lambda bodies, successor bodies, and case arms increase binder depth.
- Unanswered yields retain the entire context, and their plans are recorded. A supplied reply replaces only the selected perform node and consumes no source fuel. Replies may yield again.
- Zero fuel still permits reply insertion and terminal classification. A pending source reduction yields `exhausted` with the unreduced residual.
- Duplicate record fields and case arms retain their order. Lookup selects the first match; extension retains every new field and filters every inherited field whose key occurs among the new fields.

## Ambiguities and assumptions

The supplied documents were sufficient to choose reductions without an unresolved semantic branch. The job schema requires `name` but does not explicitly state its type; this implementation requires a Unicode scalar string, matching the example and the term “name.” Duplicate JSON object member names use Python's last-member normalization, expressly permitted outside the shared wire profile. Blank input lines are malformed jobs rather than silently skipped lines.

Output terms and every emitted plan are validated against the same wire profile. Free indices use Python's unbounded integers internally; an emitted index above `2^53-1` explicitly fails the run. Natural arithmetic uses Python integers and disables Python's decimal conversion digit cap when that API exists.

## Local checks and fidelity limits

Only hand-authored examples were checked: 25 evaluation cases covering value/stuck/yield/exhausted, exact fuel, lazy fields, strict conjunction, wrong-typed operands, duplicate keys, three binder constructs, extraction, recursive extension, specification application, and repeated replies; one direct free-variable shifting check for mix; and five invalid-wire checks including unused replies and output index overflow. All passed. These checks were run inline; no repository test files were read or changed.

This is an executable reconstruction of the pure core, not a proof of correspondence. No held-out or differential evaluation was performed by this author. Evaluation-context traversal is iterative; AST validation and binder traversals are recursive and can fail on sufficiently deep inputs. Natural size, copying, and recursive expansion remain limited by host resources; such failures are execution errors, never semantic stuck/divergence results. Exhaustion is only a finite observation. The capsule's host skeleton is outside the AST runner: this program does not implement authority, protected reads, transactions, scheduling, durable turns, receipts, slots, or budgets/tariffs.
