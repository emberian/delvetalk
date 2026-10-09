# Governed programming

**`reprogram` atomically replaces protocol and complete state under current law.**
World and transaction hosts share [the implementation](WorldCore.lean).

```json
{"op":"reprogram","object":"document","principal":"alice","intent":"v2",
 "expected":"<complete current JSON root>",
 "protocol":"<valid delvetalk-local-v1 protocol>","state":{"body":"preserved"}}
```

Replace placeholders with JSON values. Only these seven fields are accepted.
Lean checks current authority, exact root, every proposed command (including
unused bodies), and record-valued state. Success preserves identity/law,
increments version once, and returns `{root,result:null,outbox:[]}` in the
ordinary committed receipt.

State replaces rather than merges; `{}` clears it. Required `protocol.initial`
does not initialize existing objects. No migration code, command or outbox runs.
Validation establishes neither migration invariants nor termination or client
compatibility. Command preconditions cannot veto management; scoped laws can.

Failures preserve the object and retain refusal. Exact `(principal,intent)`
retries recover history before current checks; changed requests refuse. Earlier
invocations never rerun under new code. Upgrades stale old roots/read sets.
Transactions may consume an earlier exact `{protocol,state}` result through
`inputFrom`; see [TRANSACTIONS](TRANSACTIONS.md).

Build serially and check both paths:

```sh
LEAN_NUM_THREADS=1 lake build delvetalk-world
LEAN_NUM_THREADS=1 lake build delvetalk-transactions
python3 conformance/test_reprogram.py
```

[Tests](../conformance/test_reprogram.py) cover execution after upgrade, atomic
refusal, exact decimal preimages, preserved authority and historical receipts.
