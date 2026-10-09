# Remote atomic transactions

**One public request admits all calls atomically through Lean.** [Clerk](CLERK.md) identity, pins, journal and retry rules apply unchanged.

```json
{"op":"transaction","reads":{"desk":{"expected":{}},"room":{"expectedRootRef":{"uri":"at://CUSTODIAN/org.delvetalk.root/KEY","cid":"CID"}}},"calls":[{"object":"desk","command":"candidate","input":{"name":"welcome"}},{"op":"reprogram","object":"room","inputFrom":0}]}
```

Replace placeholders with the complete root and fixed custodian reference. Each read has exactly `expected` or `expectedRootRef`. Bounds: 1–16 reads, 1–32 calls, 64 KiB after expansion. Reads/targets and the author repository must be enrolled, except `expected:null` may name a direct child of an enrolled object. This asserts initial absence for [governed allocation](ALLOCATION.md); later calls may use the staged child. Only committed children become enrolled; enrollment grants no authority.

Invocation uses `{object,command,input}` or `inputFrom`; optional `op:"invoke"`. Reprogramming uses `{op:"reprogram",object,protocol,state}` or `inputFrom`. Indices select prior pure results; program candidates contain protocol/state. Results convey data, never authority. Remote create/law and principal/intent overrides refuse.

Lean checks current staged law, complete initial read set, exact roots and execution; any refusal rolls back all calls. Standard custody selects `transactions`; operator-configured compiled custody selects its pinned compiled host. Sources cannot override runtime. Pending recovery retains that admission profile.

Committed receipts contain `data.roots/results/outbox`, optional `data.allocated` creation roots, singular `object:null` and publication read-set `objects`. Unused absence roots stay `null`. [Worker](WORKER.md) prepares receipt-linked snapshots/head locally; publication remains paused.

[Implementation](../scripts/transaction_intake.py), [actual-Lean/mock-PDS tests](../conformance/test_transaction_intake.py).
