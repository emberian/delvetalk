# Ordered local transactions

**All calls commit together or retain one refusal.** `delvetalk-transactions`
uses [shared Lean admission](TransactionsCore.lean); Python supplies file custody.
Principals are local assertions. This profile establishes no distributed consensus.

```sh
LEAN_NUM_THREADS=1 lake build delvetalk-transactions
python3 scripts/world.py --profile transactions /path/to/world.json request.json
```

```json
{"op":"transaction","principal":"alice","intent":"transfer-17",
 "reads":{"savings":"<complete root>","checking":"<complete root>"},
 "calls":[{"object":"savings","command":"debit","input":{"amount":7}},
          {"object":"checking","command":"credit","inputFrom":0}]}
```

Replace roots with complete protocol/law/version/state records. All targets must
appear in `reads`; extra roots guard commits. Lean checks every initial root
before any call. Calls are nonempty and ordered; each checks the global
principal's current staged target authority. No delegation occurs.
For [governed allocation](ALLOCATION.md), a `null` read asserts initial absence;
factory calls may create that child for subsequent calls in the same transaction.

Invocation permits only `object`, `command`, exactly one of record `input` or
`inputFrom`, and optional `op:"invoke"`. `inputFrom` selects an earlier call's
whole record result. Programming permits `op:"reprogram",object,protocol,state`
or `op:"reprogram",object,inputFrom`; the latter requires exactly
`{protocol,state}`, without overrides. [Programming](PROGRAMMING.md) preserves
law/identity and emits nothing; compiled hosts return a checked program receipt.
Law revision permits exactly `op:"law",object,law`: current management authority,
old constraints and proposed constraints must all admit the staged program/state.
It advances the version, returns null and emits nothing. Later calls use the new
law immediately. A deliberate lockout may commit; a subsequent unauthorized call
refuses the whole batch. Programming and law revision can commit together only
when each ordered intermediate candidate satisfies its current constraints.

`["input-origin"]` returns host-derived
`{present,object,command,immediatelyPrevious}`. For `inputFrom`, it names the
successful earlier invocation supplying the whole result; the Boolean says
whether that invocation immediately precedes this call. Intervening calls,
including reprogramming, break adjacency; read-set guards do not. Direct input and
standalone calls return `{present:false,object:"",command:"",immediatelyPrevious:false}`.
Callers cannot supply this context. It conveys provenance, never authority;
each callee still checks the global principal. A [gated commons move](../conformance/test_guarded_movement.py) can require
its input from the immediately preceding named door command. This expression
is separate from the source-transition context `{object,principal}`.

Later calls see staged state, programs and laws. Each success increments version once.
Within a legacy call, require/set/result/outbox expressions all read its original
state; writes are simultaneous. Compiled [source transitions](COMPILED.md) instead
replace the whole state from one evaluated decision, retaining the same atomicity.

Receipt data is `{roots,results,outbox}` with optional `allocated` creation roots:
final roots cover the entire read set, preserving unused absence as `null`;
results follow call order; outbox entries are `{object,step,payload}` in emission
order. Outboxes establish intent, not delivery. Any semantic failure discards
all staged effects. Malformed envelopes remain transport errors.

One 10,000-tick budget includes every call and evaluator operation; 64 KiB
requests still apply. The legacy framed CLI additionally caps each whole-world
frame at 16 MiB. Normal file custody sends only the request; retained history
has no wire-frame quota. These are not complete resource limits.
Exact `(principal,intent)` retries recover retained success/refusal before
current checks; changed requests, including metadata, refuse. Choose the profile
on the first attempt: the default host can retain an unknown-operation refusal.

The [custody wrapper](../scripts/world.py) locks through admission, replacement
and directory synchronization, including unchanged retries after uncertain writes.
Lean reads the snapshot and writes the candidate; Python performs custody only.
Decimal mantissa/exponent are preserved by this route. Whole-history parsing,
receipt lookup and snapshot replacement remain linear. Cooperating callers serialize; lost replies
require exact retries. This does not establish universal power-loss durability. Check races, rollback, budgets and retries with
`python3 conformance/test_transactions.py` ([cases](../conformance/test_transactions.py)).
