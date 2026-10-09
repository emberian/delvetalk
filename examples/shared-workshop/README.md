# A shared workshop that participants can reprogram

Iris and Moss share a task, offer and two answer slots. The `transactions` host
admits their work in Lean; scripted callers assert principal names locally.
Nothing is delivered externally.

```sh
make build
python3 examples/shared-workshop/run.py --output /tmp/workshop-example-1
python3 conformance/test_workshop.py
```

The output directory must not exist. It retains world/request/receipt history,
`report.json` and `proposal-report.json`. Omit `--output` for a temporary run.

## One continuous interaction

1. Moss computes six benches × seven boards with [typed Bend](boards.typed.json).
2. Iris atomically accepts the offer and passes its result to task assignment.
3. A wrong destination in the last completion call refuses the entire transaction.
4. Iris and Moss race from identical roots. One completion commits both answers;
   the other retains a stale-root refusal. Scheduling chooses the winner.
5. Exact retries recover both receipts. Fresh requests still cannot refill slots.
6. Moss proposes [task-v2.md](task-v2.md), adding a one-use reflection action.
7. Iris reprograms from the exact root with explicit migrated state. Moss's stale
   edit refuses; a fresh reflection commits.
8. Iris installs an empty law. Lockout blocks future management; historical
   receipts remain retrievable without undoing it.

The two answer slots are distinct inboxes. Aliases would share one slot. Ordered
`answer-ready` outbox entries are durable intents, not delivered messages.

## What is being checked

The standalone typecheck establishes `Nat → Nat → Nat` for the exact installed
term. Host installation still checks syntax; invocation dynamically refuses
effects, stuckness, unsupported values and exhaustion.

Command expressions read old state. Ordered transaction calls see prior staged
writes. Lean owns preconditions, roots, authority and atomic rollback.
[Runner](run.py), [scenarios](task-v2-scenarios.json), and
[conformance](../../conformance/test_workshop.py) specify inputs and observed cases;
these are not universal transaction proofs or distributed consensus.

## Different syntax, the same admission boundary

Reviewed syntax adapters retain source and lowering identity. Proposal tests confer
no installation authority. Reprogramming separately checks current law, exact root,
validated protocol and explicit replacement state. It preserves law. This example
supplies migration directly; arbitrary prose and source-only Spween cannot execute.
