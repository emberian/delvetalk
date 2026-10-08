# Capsule-only reconstruction

Semantic and wire inputs read, and no other project material:

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| `/Users/ember/dev/delvetalk/capsules/rewrite-2k.txt` | 1945 | `c1a6fad2b4ef95e3e6d9de2756ffe70ea351f2b9f6f69624113832928c81cc10` |
| `/Users/ember/dev/delvetalk/experiments/capsule-only/WIRE.txt` | 852 | `a59335e3c227b48b110bbb329580cc4f90574d6a47176a752e1b277d4a27b741` |

Total input size: 2797 bytes. Implementation uses Python standard library only.
Run `python3 evaluator.py` with JSONL on stdin. Each successful job produces
one JSONL result. Malformed input terminates at that line with a diagnostic on
stderr and exit code 1.

## Interpretations and ambiguities

- `project` is the wire spelling of capsule `target`; `ifZero` is `natcase`,
  including a binding successor body; `label` represents String.
- `equal` is Nat equality and `labelEqual` is String equality. No Boolean
  equality is specified. `conjunction` requires both Boolean operands and
  evaluates both through the given strict binary context.
- Fuel is a limit on completed rewrite steps. At zero fuel, an already
  terminal value or stuck term is reported as such. A reachable `perform`
  is recorded and may receive a free reply even with zero fuel; a pending
  rewrite is reported as exhausted. Replies do not evaluate their payload
  before insertion. Unused responses are ignored.
- Plans are recorded when reached, whether or not a response is available.
  The recorded plan is its raw term at encounter time (including substitutions
  already performed), with no evaluation of the plan. An unanswered yield
  returns the complete residual term containing `perform` and its context.
- Record field lists and case arms retain order and duplicate keys; lookup
  selects the first matching entry. Extension removes every inherited field
  with a key present in the added list, preserving all added entries.
- Bound variables may be open. They are stuck when evaluated alone. Binder
  removal and insertion use capture-free De Bruijn substitution, traversing
  even lazy components. No alpha renaming is necessary in this representation.
- Noncanonical decimal strings containing leading zeros are accepted. Existing
  literals are preserved until operated upon; computed naturals are emitted
  in canonical decimal notation. Python's decimal conversion digit cap is
  disabled where supported to retain unbounded-natural semantics.
- Object admission, authentication, durable effects, and scheduling have no
  wire constructors or operational profile here. No implementation for them
  is inferred. Evaluation can yield plans but does not commit effects.
- Runtime resource exhaustion remains possible for sufficiently large terms;
  source-step exhaustion is represented separately by the specified status.

## Local validation before freeze

Eleven independently constructed hand checks exercised capture avoidance,
successor-body substitution, zero and exact fuel, contextual yield, reply
resumption, raw plans, lazy application, duplicate field lookup, case
substitution, and scalar type disjointness. No existing tests or held-out
test cases were read or run. No examiner output was consulted.
