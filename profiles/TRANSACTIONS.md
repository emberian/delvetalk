# Ordered local transactions

`delvetalk-transactions` is an opt-in local host profile. It imports
`WorldCore.lean`, sharing the default host's protocol evaluator, exact JSON
roots, authority checks, and retained receipt lifecycle. `delvetalk-world`
continues to provide its existing single-object interface. This profile is
local admission evidence, not a Mini source change or a distributed transaction
protocol. Principal strings remain assertions by the local caller.

Build with `LEAN_NUM_THREADS=1 lake build delvetalk-transactions`. Run through
the existing durable custody wrapper:

```sh
python3 scripts/world.py --profile transactions /path/to/world.json request.json
```

The Python API is `world.exchange(database, request, profile='transactions')`.
The profile selector is a static executable allowlist. Python still only locks,
transports JSON, and persists the world returned by Lean. Create, inspect, law,
and single-object invoke requests retain the default host's behavior.

## Request and result

```json
{
  "op": "transaction",
  "principal": "alice",
  "intent": "transfer-17",
  "reads": {"savings": "<complete saved root>", "checking": "<complete saved root>"},
  "calls": [
    {"object": "savings", "command": "debit", "input": {"amount": 7}},
    {"object": "checking", "command": "credit", "inputFrom": 0}
  ]
}
```

The root placeholders above stand for complete JSON object roots, including
protocol, law, version, and state. `reads` contains known objects; there is at
least one call. Every target must occur in `reads`. Additional roots are allowed
as read-only commit guards. Lean compares **all** roots against the initial
world before executing a call, including read-only guards.

Calls run in array order. Each call checks the global principal against its
target's current law. There is no caller impersonation, automatic delegation,
object creation, or law change inside a transaction. Call fields are restricted
to `object`, `command`, and exactly one of `input` or `inputFrom`; unsupported
fields are refused. `input` is a JSON record. `inputFrom` is a zero-based index
of an earlier call whose entire result becomes this call's input, and therefore
must also be a record. This transfers pure data without transferring authority.

Repeated calls to an object see the state staged by earlier calls, and each
successful call increments its version once. Within a single call, all require,
set, result, and outbox expressions still read that call's original state,
preserving the default host's simultaneous field-write semantics. Results and
outboxes therefore do not implicitly read that call's newly written state.

Successful receipt data has this shape:

```json
{
  "roots": {"savings": "<final root>", "checking": "<final root>"},
  "results": [{"amount": 7}, {"amount": 7}],
  "outbox": [
    {"object": "savings", "step": 0, "payload": {"debit": 7}},
    {"object": "checking", "step": 1, "payload": {"credit": 7}}
  ]
}
```

`roots` covers the complete read set at commit; `results` is ordered by call;
outbox entries preserve call order and each command's emission order. The
ordinary receipt envelope has `intent`, `object` (normally null for a
transaction), `kind`, and `data`. There are no per-call durable receipts.
Outbox payloads are committed intents, not proof of external delivery.

## Atomicity, budget, and retries

All staged object writes, results, and outboxes commit in one returned world.
Any failure discards all of them and retains one refused receipt, with an error
string. A missing or stale read, unauthorized later target, bad result reference,
late outbox failure, and exhausted budget all take that path. Envelope errors
such as a missing principal remain transport-level errors as in the default
profile.

One budget of 10,000 evaluation ticks covers the entire transaction, including
one tick per call and all shared evaluator work. The budget never resets between
calls or objects. Existing 64 KiB request and 16 MiB input frame bounds apply.
These are deterministic evaluator bounds, not wall-clock, output-size, or memory
limits.

The same `(principal, intent)` identity binds the entire original request,
including roots, calls, and extra top-level metadata. An exact retry returns its
retained success or refusal before rechecking roots or authority. A changed
request under that identity is refused. Retention shares the world's existing
receipt namespace with single-object operations and has no expiration.

The custody wrapper holds one stable file lock across read, Lean admission,
atomic replacement, and directory synchronization. Cooperating callers using
the same database therefore serialize. A post-replace lost reply remains
uncertain to that caller; retrying the original request recovers its retained
receipt. This is a local filesystem contract, not multi-host consensus or a
claim about power-loss durability on every filesystem. Using the default world
profile to attempt a transaction can retain an unknown-operation refusal under
that intent; select the transaction profile from the first attempt.

`python3 conformance/test_transactions.py` checks two-object transfer with
data-dependent calls, exact stale reads before execution, current authority on
a later callee, late failure rollback, repeated-object sequencing, retained
receipts after an injected uncertain reply, racing transfers, and a budget that
fits one call but refuses two. It requires the built executable so concurrency
checks do not start additional Lean compilers.
