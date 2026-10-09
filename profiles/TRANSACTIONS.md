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
principal's current target authority. No creation, law change or delegation occurs.

Invocation permits only `object`, `command`, exactly one of record `input` or
`inputFrom`, and optional `op:"invoke"`. `inputFrom` selects an earlier call's
whole record result. Programming permits `op:"reprogram",object,protocol,state`
or `op:"reprogram",object,inputFrom`; the latter requires exactly
`{protocol,state}`, without overrides. [Programming](PROGRAMMING.md) preserves
law/identity, returns null and emits nothing.

Later calls see staged state/programs. Each success increments version once.
Within a call, require/set/result/outbox expressions all read its original
state; writes are simultaneous.

Receipt data is `{roots,results,outbox}`: final roots cover the entire read set;
results follow call order; outbox entries are `{object,step,payload}` in emission
order. Outboxes establish intent, not delivery. Any semantic failure discards
all staged effects. Malformed envelopes remain transport errors.

One 10,000-tick budget includes every call and evaluator operation; 64 KiB
requests and 16 MiB frames still apply. These are not complete resource limits.
Exact `(principal,intent)` retries recover retained success/refusal before
current checks; changed requests, including metadata, refuse. Choose the profile
on the first attempt: the default host can retain an unknown-operation refusal.

The [custody wrapper](../scripts/world.py) locks through admission, replacement
and directory synchronization. Cooperating callers serialize; lost replies
require exact retries. This does not establish universal power-loss durability. Check races, rollback, budgets and retries with
`python3 conformance/test_transactions.py` ([cases](../conformance/test_transactions.py)).
