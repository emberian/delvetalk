# Blind reconstruction: rewrite capsule

This is an independent Python standard-library interpreter constructed using
only these two supplied semantic/wire inputs:

| Input | Bytes |
| --- | ---: |
| `capsules/rewrite-2k.txt` | 1,945 |
| `conformance/AST.md` | 6,664 |
| Total supplied text | 8,609 |

The AST wire document is separately counted: this experiment therefore does
not reconstruct execution from 1,945 bytes alone. In particular, that document
supplies observable fuel, reply, residual-context, validation, binding, and
strictness details. Sizes were measured with `wc -c` on the supplied files.
No existing evaluator, normative specification, fixture corpus, other capsule,
repository history, or agent semantic advice was consulted.

## Running

From the repository root:

```sh
python3 experiments/blind/rewrite/evaluator.py < jobs.jsonl
```

The script reads JSONL and emits one compact JSON result per successful job.
A malformed job or host execution failure prints a diagnostic to stderr and
exits nonzero; it does not emit a semantic result for that job. Successfully
processed earlier lines may already have been emitted.

## Interpretations and remaining ambiguity

- `name` is interpreted as a Unicode scalar string. The wire text requires the
  member but does not explicitly state its type; its example uses a string.
- `equal` is Nat equality and `labelEqual` is string equality; Boolean equality
  is not an operation. This follows the capsule's disjoint scalar operation
  lists and the wire document's separate primitive names.
- Source values are recognized solely by their outer constructor. Their lazy
  components are nevertheless syntactically validated before execution.
- A failed eliminator on an already available wrong-kind value is stuck. A
  binary operation still evaluates its right operand after any left value,
  as explicitly required by the wire document.
- De Bruijn substitution removes the selected binder and decrements indices
  above it, including open references. It shifts substituted free references
  under lambdas, successor bodies, and case arms. `mix` shifts both supplied
  extensions by two before inserting final-self and inherited-result binders.
- Each listed rewrite counts as one reduction, including `mix`, `fix`, scalar
  calculation, projection, field extension, and `done`. Detecting a reduction
  with no fuel does not execute it. Yield selection and reply replacement do
  not use reduction fuel.
- Duplicate JSON object members use Python JSON's last-member normalization,
  permitted outside the common wire profile. Ordered duplicate record and arm
  keys are preserved, and lookup takes the first occurrence.
- Empty lines are malformed JSON jobs. Unknown job keys, constructors, and
  primitives are rejected. All responses are validated even when unused.
- Internal free indices use unbounded Python integers. Every emitted residual
  and plan is validated against the wire bound. A run whose emitted AST would
  exceed that bound fails explicitly. An unexecuted zero-fuel rewrite does not
  perform renaming merely to decide that its status is `exhausted`.

## Checks and fidelity limits

Twenty-eight hand-written semantic checks passed, covering beta reduction,
open substitution under all binder forms, `mix` shifting and composition,
`fix`, lazy metadata/prototype access, ordered duplicate fields and arms,
strict conjunction, wrong-type binary operands, retained yield contexts,
repeated replies, exact fuel boundaries, division/modulo by zero, saturation,
and a natural with more than 5,000 decimal digits. Five validation checks
covered noncanonical naturals, invalid unused replies, Boolean fuel, lone
surrogates, and unrepresentable output indices. JSONL subprocess checks also
verified multiple job results and malformed-job stderr/nonzero behavior.

These are author-created examples, not held-out conformance results. No
existing test suite was read or run, and no proof of equivalence is claimed.
The interpreter is a tree evaluator without memoization. Traversal,
substitution, JSON parsing/printing, and validation can encounter host recursion
or memory limits; such failures are execution errors. Arbitrary-precision Nat
arithmetic uses Python integers with the decimal conversion digit cap disabled
where that API exists.

The capsule's durable object/admission/law prose is not implemented: the wire
format describes only pure terms and supplied plan replies. This reconstruction
does not implement typing, sharing, authority, storage, effect admission,
transactions, receipt/retry protocols, scheduling, networking, or host budgets.
