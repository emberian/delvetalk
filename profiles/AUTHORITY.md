# Scoped local authority

The world and transaction hosts share one Lean authority engine. Existing laws
of the form `["alice", "bob"]` retain their original meaning: each listed
principal may invoke any command, replace the protocol, or replace the law.
There is no implicit authority for the creator or a principal named `owner`.

Objects can opt into `delvetalk-scoped-law-v1`:

```json
{
  "profile": "delvetalk-scoped-law-v1",
  "invoke": {
    "play": ["alice", "bob"],
    "review": ["reviewer"]
  },
  "reprogram": ["programmer"],
  "law": ["steward"]
}
```

These four fields are required. An optional `predicate` may further restrict
these grants; other fields are refused. `invoke` is a
record mapping exact command names to arrays of principal strings. Both
management fields are also arrays of principal strings. A missing command
grants nobody permission. There is no wildcard or default: a `"*"` entry grants
only a command literally named `*`. Grants may name commands absent from the
current protocol; they become usable only if that command is later installed.
A command named `reprogram` is still an invocation and does not confer
management authority.

Use either law representation in an ordinary `create` or `law` request.
`World.validateLaw` checks both representations. `World.authorizeRequest` checks
the existing object's current law against the actual operation, command, and
authenticated caller supplied by the host. The proposed law cannot authorize
its own installation. The current `law` grant authorizes replacement, while the
current `reprogram` grant authorizes programming. The law's shape can be changed
in either direction by an authorized law replacement against an exact root.

All successful replacements increment the object version, so old exact roots
become stale. A fresh request faces current authority; an exact retry still
returns its retained historical receipt before new authority or root checks.
An earlier refusal remains refused after a grant. A new request needs a new
intent. Protocol replacement preserves the current law, including scoped grants.

An empty invocation map and empty management arrays deliberately lock out all
future mutations. Granting a programmer no `law` permission does not let that
programmer edit grants through a protocol or state replacement. There is no
recovery bypass. This profile does not add read protection: local `inspect` and
published snapshots remain public. Principal strings at the local JSON boundary
are caller assertions; the live clerk supplies repository-derived identities.

## Transaction composition

Every transaction step uses the same authority engine against the staged target
and global principal. Invocation rights are checked for each actual command,
including repeated calls to the same object. Earlier results transfer only data.
They do not delegate the earlier object's authority or impersonate its author.

The transaction profile also permits explicit programming steps. A source desk
can first invoke `adopt`, returning exactly `{protocol, state}`, and pass that
result to `{op: "reprogram", object: "target", inputFrom: 0}`. The target checks
the global caller's current programming grant. Adoption, replacement, any later
invocation, results, and outboxes all commit together or all roll back. A later
invocation sees the newly installed program but still needs that command's
current grant. The full wire contract is in [TRANSACTIONS.md](TRANSACTIONS.md).

## Pure Objective Bend policy

A scoped law may include `predicate`, a raw core-array Objective Bend term that
is applied to one context record. Installation checks the term's syntax using
the existing core decoder. Policy evaluation uses the existing proof-backed
source evaluator, not a transport-side policy interpreter or a new language.
The ordinary operation/command grant is checked first. A predicate can only
restrict that grant; returning true cannot authorize an unlisted principal.

The context has exactly these fields:

```json
{
  "principal": "the host-supplied caller",
  "op": "invoke",
  "command": "add",
  "state": {"count": 1},
  "input": {"amount": 2}
}
```

`state` is the current object's complete state. For an invocation, `input` is
its actual record, including resolved `inputFrom` data in a transaction.
`command` is the actual command name, not a caller-supplied field inside input.
For `law` and `reprogram`, `command` is the empty string and `input` is `{}`;
`state` still comes from the current object. The context does not expose a
proposed new law or protocol, so candidate inspection is not this version's
policy interface. The old law's predicate governs its own replacement.

For example, this predicate limits `add`-style invocation state transitions to
`state.count + input.amount <= 3`, while leaving management operations subject
to their ordinary scoped grants:

```json
["lam", ["ifBool",
  ["binary", "labelEqual", ["get", ["bound", 0], "op"], ["label", "invoke"]],
  ["binary", "lessEqual",
    ["binary", "add",
      ["get", ["get", ["bound", 0], "state"], "count"],
      ["get", ["get", ["bound", 0], "input"], "amount"]],
    ["nat", "3"]],
  ["boolean", true]]]
```

Only a successfully evaluated Boolean true admits the operation. False returns
`authority predicate refused`; another value returns
`authority predicate must return Bool`. Effects, stuck terms, and exhaustion
return the existing evaluator error. Every such failure rolls back the entire
operation or transaction and retains one refusal receipt. Exact historical
retries recover their receipts without executing the predicate again.

Context conversion is strict and bounded to depth 64. Its data domain is
natural numbers, booleans, strings, and records recursively. Negative or
fractional numbers, nulls, and arrays are refused when a predicate is present,
even if its body would not select that field. There is no lossy coercion or
omission. Laws without predicates retain the existing unrestricted JSON
state/input behavior. Choosing an incompatible state through reprogramming can
therefore deliberately or accidentally prevent future policy-guarded operations;
there is no recovery bypass.

`World.authorizeRequest` runs in `Evaluation`. Single-object policy and body
execution share the executable profile's fixed budget, including management
operations: 10,000 ticks for the default hosts, 100,000 for the opt-in
[compiled host](COMPILED.md).
Transactions use one budget across every call, policy, context conversion, body,
result, and outbox. A repeated-object policy reads the state staged by previous
calls. Each transaction step still costs its existing tick. A predicate never
gets a fresh private budget. Definition validation and finite grant membership
remain structural checks bounded by the existing request/frame envelopes, not
a wall-clock or complete memory tariff.

The compiled host passes remaining ticks into package demand evaluation and
charges its actual execution, materialization, and conversion cost against this
same `Evaluation` budget. The default hosts do not import that frontend or
enable its expression tags. Read protection, candidate-aware policies, and
additional JSON data encodings remain separate future interfaces.

`python3 conformance/test_authority.py` exercises separation of playing,
programming, and law changes; exact command names; old-law admission; lockout;
legacy migration; malformed-law atomic refusals; current grants versus retained
history; per-callee and repeated-object transaction checks; and an atomic source
desk adoption that installs its exact prior result before invoking the new code.
It also checks a bounded counter policy, staged-state/prior-result context,
caller and command binding, old-law management checks, wrong-kind/effect/stuck
refusals, divergence, and budgets shared between policy and body, between
invocations, and between programming operations.
