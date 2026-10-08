# Remote atomic transactions through the clerk

The existing clerk receiving path accepts a bounded transaction request. Its
source record, PDS identity checks, journal, URI/CID binding, exact retries and
receipt envelope are the same as single-object invocation. The operation selects
the pinned Lean `transactions` host against the same durable world. Python only
validates wire structure, resolves root references and constrains transport to
operator-enrolled objects; Lean checks current law, complete read sets, exact
roots, prior-result indices, execution and atomic commit/rollback.

The inner `requestJson` or explicitly marked social request is:

```json
{"op":"transaction","reads":{"desk":{"expected":{}},"room":{"expectedRootRef":{"uri":"at://did:plc:oq2mrkwsuts7dqbkqqm2ntiz/org.delvetalk.root/ROOM_ROOT","cid":"ROOT_CID"}}},"calls":[{"object":"desk","command":"candidate","input":{"name":"welcome"}},{"op":"reprogram","object":"room","inputFrom":0}]}
```

Replace embedded `{}` with the entire expected desk root. Each read descriptor
contains exactly `expected` or `expectedRootRef`, never both. A referenced root
uses the same fixed custodian, exact CID, digest and envelope checks as an ordinary
clerk request. The journal retains every resolved source record before admission.
All read guards and call targets must be enrolled in `clerk.json.objects`; the
author's repository must also be enrolled. Enrollment is only a transport exposure
boundary, not an authority grant. A single principal is derived from the source
repository DID for every call. There is no call-specific principal override.

Calls use the existing Lean transaction forms:

- Invocation: `{object,command,input}` or `{object,command,inputFrom}`, with
  optional `op:"invoke"`.
- Reprogramming: `{op:"reprogram",object,protocol,state}` or
  `{op:"reprogram",object,inputFrom}`. A prior pure result must contain exactly
  the protocol/state candidate expected by Lean.

The wrapper permits 1–16 read descriptors and 1–32 calls. It rejects unknown
fields, remote create/law operations, forged principal/intent fields and malformed
indices. Root resolution happens before journal reservation. After expansion,
the complete derived request must fit 64 KiB; an oversized request cannot strand
a pending attempt. Lean checks each call against current staged law and requires
its target in the initial read set. Any late refusal rolls back earlier calls.
A prior result conveys data, never the earlier object's authority.

On commit the receipt contains `data.roots`, `data.results` and `data.outbox`;
its legacy singular `object` field is null. The clerk envelope retains the entire
derived request and source identity. Receipt publication encoding uses an
`objects` array of read-set identities rather than a singular discovery `object`.
These convenience fields do not grant authority. Nothing is published by intake.

`Transactions.lean`, its actual executable and `transaction_intake.py` join the
clerk's implementation pins. New pending entries retain `admissionProfile`, so
recovery uses the selected host and cannot reinterpret a transaction as a
single-object request. A pin upgrade still requires a quiescent request journal;
completed historical receipts remain retrievable independently of later policy
or source changes.

The worker prepares the immutable receipt plus root snapshots and an admission
head linking those snapshots to that receipt. These records describe one admitted
boundary, not a current mutable pointer or a complete hash-linked replay history.
Preparation is local only; external publication remains paused. See
[WORKER.md](WORKER.md) for the prepared artifact layout.

`python3 conformance/test_transaction_intake.py` exercises actual Lean with mock
PDS records: multiobject commit, compact roots, stale and policy refusals, rollback,
read-set completeness, forged principals, bounded wire/enrollment checks,
prior-result program adoption and crash recovery after admission. No live network
calls or account mutations are involved.

A clerk explicitly configured with `runtimeProfile:"compiled"` routes these same
transactions to the compiled host; the source author cannot change that choice.
The journal's retained `admissionProfile` and complete runtime pins bind recovery.
Standard clerks continue to use the ordinary transaction host and its budget.
