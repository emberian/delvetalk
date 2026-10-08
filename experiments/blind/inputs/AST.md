# Conformance AST and runner protocol

This is a test interchange format for the pure Objective Bend core, not a
surface-language parser, typechecker, serialization of host authority, or
production application protocol. The pinned Lean source defines the semantics.
Implementations may evaluate open and ill-typed terms; `stuck` is observable.

Each term is a JSON array. Constructor names match the Lean `Term` constructors.
Here `t,u,v` are terms; `k` is a Unicode scalar string; `i` is a nonnegative JSON
integer; `fs`/`arms` are arrays of `[k,t]` pairs, **not JSON objects**. Preserve
their order and duplicate keys. Lookup selects the first matching key.

| Term | Meaning |
| --- | --- |
| `["bound",i]` | De Bruijn index; nearest binder is 0 |
| `["lam",t]` | Lambda; body binds one variable |
| `["app",t,u]` | Call by name application |
| `["mix",t,u]` | Lower extension followed by upper extension |
| `["fix",t,u]` | Recursive extension, inherited seed |
| `["specification",t,u]` | Unevaluated metadata and extension |
| `["prototype",t,u]` | Unevaluated specification and target |
| `["reflect",t]` | Extract prototype specification |
| `["metadata",t]` | Extract specification metadata |
| `["project",t]` | Extract prototype target |
| `["nat","123"]` | Arbitrary precision natural, canonical decimal string |
| `["boolean",true]` | Boolean, distinct from labels and naturals |
| `["label","text"]` | String label; no Boolean reserved words |
| `["binary",primitive,t,u]` | Strict left-to-right scalar operation |
| `["extend",t,fs]` | New fields followed by unshadowed inherited fields |
| `["record",fs]` | Lazy record value |
| `["get",t,k]` | Field lookup |
| `["ifZero",t,u,v]` | Zero branch `u`; successor body `v` binds predecessor |
| `["inject",k,t]` | Sum value with lazy payload |
| `["case",t,arms]` | Each arm body binds the selected payload |
| `["ifBool",t,u,v]` | Boolean conditional |
| `["perform",t]` | Yield raw plan `t`, without evaluating the plan |
| `["done",t]` | Reduce to `t` in one source step |

Primitive names: `add`, `multiply`, `equal`, `conjunction`, `labelEqual`,
`subtract`, `divide`, `less`, `lessEqual`, `modulo`. Nat uses arbitrary precision;
subtraction saturates, division floors, `n/0=0`, `n%0=n`. Conjunction is strict
on both operands, even when the left is false. The right operand is evaluated
after **any** left value, even one with the wrong scalar type.

Only `lam`, the successor body of `ifZero`, and every arm body of `case` bind.
`mix` inserts two fresh binders and must shift free variables. Substitution must
avoid capture beneath all three binding constructs. Record fields, injection
payloads, specification components and prototype components remain unforced
until selected by evaluation. No implicit prototype wrapping occurs at `fix`.

## JSONL jobs and results

Each stdin line is a job; each stdout line is its result. No banner or log text
appears on stdout. A malformed job produces a diagnostic on stderr and a
nonzero process exit; it is not a semantic `stuck` result.

```json
{"name":"example","term":["binary","add",["nat","2"],["perform",["label","input"]]],"responses":[["nat","3"]],"fuel":10000}
```

```json
{"name":"example","status":"value","term":["nat","5"],"plans":[["label","input"]]}
```

`name` and `term` are required. `responses` defaults to `[]`; `fuel` defaults to
10000. Job object member names must be unique; duplicate JSON object members
are outside the shared wire profile and may be normalized by JSON parsers.
No other job keys are accepted. Every response is validated before the
run, even if unused. Unused responses do not affect the result. Strings contain
Unicode scalar values: reject lone surrogates. Nat literals match exactly
`0|[1-9][0-9]*`; signs, leading zeroes and JSON numeric Nat values are invalid.
Input indices and fuel are integers in `0..2^53-1`, excluding JSON Booleans;
this interchange bound does not change the source's unbounded Nat semantics.
Host memory/stack limits can still cause an execution error; they are not
semantic results. Implementations must not silently round integer arithmetic.
If capture-avoiding renaming grows a free index beyond `2^53-1`, an output
containing it cannot be represented by this wire profile: fail the run explicitly
rather than emit an inexact index or call it `stuck`. The supported common
profile requires all emitted residual terms and plans to satisfy the same bound.

`status` has four meanings:

- `value`: whole residual term is a source weak-head value.
- `stuck`: no source step, no yield and no source value.
- `yield`: evaluation has reached `E[perform P]` without another supplied reply.
  The residual `term` is the **entire** `E[perform P]`, preserving its context.
- `exhausted`: the term has another source step, but no remaining step fuel.
  This is a bounded observation, **not a proof of divergence**.

`plans` records each raw plan encountered, in order, including the final
unanswered plan if any. A reply replaces the selected `perform` in its retained
context, with no evaluation or substitution into the plan. Replies may themselves
be computations or yields; this untyped evaluator imposes no host reply schema.

Fuel counts exactly source reductions, not evaluation-context descent, plan
yielding or reply insertion. At fuel zero, still classify value/stuck/yield and
consume available replies; never take an additional source step. Thus a zero-fuel
`perform` replied to with a Nat returns `value`, but replied to with `done(Nat)`
returns `exhausted`. A finite supplied reply list prevents free reply cycling.

## Fixtures and limits

`cases.json` is an array of jobs augmented with
`expected: {"status":...,"term":...,"plans":...}`. Harnesses remove `expected`
before sending the job. Compare parsed JSON structurally, retaining field/arm
order; ignore JSON whitespace and object member order. Expected results are
explicit examples derived from the source rules, not generated by an evaluator.

The Python implementation is a separate tree interpreter using capture-avoiding
substitution and evaluation-context frames. It calls no Lean evaluator. Tests
exercise ordinary and ill-typed terms, duplicate keys, lazy divergence,
self/super composition, fresh binders, large naturals, resumptions and fuel
boundaries. Passing examples is differential evidence, not a general refinement
proof. The runner does not model sharing, type admission, durable objects,
authentication, transactions, scheduling, networking, or budgets/tariffs.

Run the Python suite with `python3 conformance/test_python.py`; run jobs directly
with `python3 impl/python/evaluator.py < jobs.jsonl`.
