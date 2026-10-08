# Compiled source host

`delvetalk-compiled` is an opt-in local executable using the same authority,
exact-root, retained-receipt, programming, and transaction machinery as the
default hosts. Select it through `world.exchange(..., profile='compiled')` or
`scripts/world.py --profile compiled`. The selected executable fixes one
100,000-tick evaluation budget per request. Neither a request nor a protocol can
increase it or create a fresh budget for a nested call. The existing `world` and
`transactions` profiles keep their 10,000-tick budgets and reject these extra
expression tags.

## Source-package expressions

```json
["package", {
  "modules": [{"name": "Example", "source": "edition ObjectiveBend 1\ndef run(x: Nat, y: Nat) -> Nat:\n  x + y\n"}],
  "entry": "run"
}, [["input", "x"], ["input", "y"]]]
```

The source descriptor is static protocol data. It requires `modules` and
`entry`; each module has exactly `name` and `source`. Imports can only name
earlier supplied modules, never filesystem paths fetched by the host. An
optional `limits` is accepted only if exactly equal to the package adapter's
default compilation descriptor:

```json
{"ticks":"100000","heap":"100000","stack":"10000","typeFuel":"16384"}
```

Omitting `limits` is simplest. This compatibility field cannot change the
runtime's resource allowance. Claimed packets, compilation artifacts, source
hashes, and extra descriptor fields are refused at this boundary.

The existing Mini frontend compiles and type-checks the source when installing
or reprogramming a protocol, including expressions in unused commands. At
execution it recompiles the exact stored source, then runs the resulting packet
with Mini's shared-demand machine and materializes its result. No independently
supplied executable packet can replace that source. No game rules are embedded
in the host. Package-level laws are refused by the pure package adapter; object
authority remains the shared host law.

Arguments and results are exact naturals, booleans, strings, and records
recursively, with a depth bound of 64. Null, arrays, negative or fractional
numbers, variants, and effectful or non-data results are not this interface's
data domain. The result is ordinary JSON usable by another expression or a
later transaction step.

The demand machine receives the host's remaining ticks, with fixed capacities
of 100,000 heap cells, 10,000 stack frames, 100,000 materialized nodes, and
1,048,576 materialized bytes. Actual demand and materialization ticks, plus
input/output conversion nodes, are charged against the enclosing evaluation
budget before a result can be used. A refusal or an aggregate charge exceeding
the remaining budget aborts the entire operation or transaction. Policies,
ordinary Bend expressions, package calls, results, and outboxes share that
same budget. Source parsing, type checking, and compilation are structurally
bounded by the source/frame and checker limits; their work is not charged as
demand ticks. This is not a complete CPU or memory tariff.

## Generic digest expressions

`["object"]` returns the actual receiving object's ID bound by Lean admission.
It is not read from state or input. Each transaction callee gets its own actual
ID; cloning an equal protocol and state under another ID does not clone this
identity. Object-bound commitments should include this expression in their
domain rather than trusting a descriptive `state.table` field.

`["sha256", expression]` hashes the canonical UTF-8 JSON encoding of its
evaluated argument and returns 64 lowercase hexadecimal characters.
`["sha256-valid", expression]` returns a Boolean indicating whether its argument
is exactly such a 64-character lowercase hexadecimal string. The latter checks
shape only, not the existence or meaning of a preimage.

The hash data domain is natural numbers, booleans, strings, arrays, and records,
recursively to depth 64. Null and negative/fractional numbers are refused.
Encoding is defined explicitly:

- No whitespace; natural numbers use ordinary decimal digits without leading
  zeroes; booleans are `true` and `false`.
- Arrays retain order. Object keys are sorted lexicographically by Unicode
  scalar values; no Unicode normalization is performed.
- Strings retain non-ASCII characters as UTF-8. Quote and backslash are escaped;
  slash is not. Backspace, tab, newline, form feed, and carriage return use
  `\b`, `\t`, `\n`, `\f`, and `\r`; other controls below U+0020 use lowercase
  `\u00xx` escapes.

For values in this domain, the interoperable Python client computation is:

```python
hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')).hexdigest()
```

The host uses an explicit serializer; Lean's default JSON printer has different
spellings for some control characters. Tests cover Unicode, controls, quotes,
slashes, large naturals, nested objects, and arrays. Hashing charges one tick per
data node and per canonical UTF-8 byte, in addition to expression evaluation.
Digest shape checks charge the candidate string's UTF-8 size.

Domain separation, nonce generation, player/round binding, and when a reveal is
allowed belong to the userspace protocol. These expressions do not themselves
establish a commitment workflow or give an object new authority.

## Validation and scope

Build serially with `LEAN_NUM_THREADS=1 lake build delvetalk-compiled`; run
`python3 conformance/test_compiled.py`. Tests exercise actual source execution,
source/packet substitution refusal, large exact naturals, default-profile
isolation, digest interoperability, transaction rollback, and one package call
that fits while two calls exhaust their shared budget.

The source-only descriptor avoids copying a large compiled packet into every
exact object root. Existing request and frame limits still apply. Repeated
source compilation is intentional at this boundary; a later cache must preserve
the exact source-to-packet binding. Actual hosted-game receiving journeys and
external deployment are separate evidence from these generic host tests.
