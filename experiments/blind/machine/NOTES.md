# Blind machine-capsule reconstruction

The sole semantic input was `capsules/machine-2k.txt` (1,995 bytes). The separately
counted wire/protocol input was `conformance/AST.md` (6,664 bytes). Total supplied
text: 8,659 bytes. No existing evaluator, normative specification, conformance
fixtures, other capsule, history, or held-out corpus was consulted. No other
agent supplied semantic information.

Run from the project directory:

```sh
python3 experiments/blind/machine/evaluator.py < jobs.jsonl
```

This is a Python standard-library-only tree evaluator. It uses capture-avoiding
De Bruijn substitution and explicit evaluation-context frames. It does not
implement a surface parser or host authority, storage, delivery, or transactions.

## Choices where the supplied text needs interpretation

- The coroutine capsule describes weak-head results rather than enumerating
  small-step rules. I count beta substitution, specification application
  forwarding, mix expansion, fix unfolding, each projection/selection, record
  extension, conditional/case selection, primitive execution, and `done`
  elimination as one source reduction each. Descending into contexts, yielding,
  and inserting replies consume no fuel. Exact agreement with an unseen source
  reduction relation is an unproved assumption.
- Mix expands to `lambda s. lambda p. b s (a s p)` in one step, shifting both
  original operands by two under the new binders. Fix unfolds in one step to
  `(e (fix(e,p))) p`, with no extra wrapping.
- `equal` is Nat equality and `labelEqual` is String equality. There is no general
  equality operation or Boolean equality in the supplied primitive inventory.
- A wrong-shaped weak-head value stops the selecting operation. For `binary`,
  both operands reach weak-head values before checking operand types, as the wire
  document explicitly requires. An actually stuck left operand still prevents
  right evaluation.
- The wire description requires `name` but does not expressly give its type.
  This implementation requires a Unicode scalar string, following the example
  and the usual interpretation of a job name.
- Duplicate JSON object member names are normalized by Python's JSON parser
  (last value wins), as expressly permitted outside the shared profile. Ordered
  field and case lists retain every duplicate and use first-match selection.
- Index bounds are checked on all inputs and on every emitted residual and raw
  plan. An internal shifted index can temporarily exceed the wire bound, but any
  result or encountered plan containing it fails explicitly. A zero-fuel mix
  with maximal legal free indices is `exhausted`, because no expansion occurred
  and its emitted original residual is representable.

## Validation and fidelity limits

Eighteen independently constructed hand examples checked arithmetic, a 5,001-digit
natural, specification-independent lambda behavior, substitution under lambdas,
successor and case binders, strict right operands after wrong-typed left values,
unanswered contexts, repeated yields, zero-fuel reply handling, duplicate field
order, mix shifting, fix unfolding, division by zero, modulo by zero, and
saturating subtraction. Five malformed-job checks covered unused malformed
responses, Boolean indices/fuel, lone surrogates, and unknown job keys. Two
additional checks covered emitted index overflow and its zero-fuel boundary.
The large-number test initially hit the test driver's own Python decimal digit
limit; rerunning with that driver limit disabled passed. The evaluator disables
the decimal conversion limit itself.

These are hand-example checks, not held-out conformance results or proof of
refinement. Substitution, structural validation, JSON parsing, and serialization
can exceed Python's recursion/memory limits; such failures exit nonzero with a
stderr diagnostic rather than manufacture a semantic status. Reduction-context
descent itself is iterative. No production deployment claim is made.
