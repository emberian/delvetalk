# Public requests, receipts and roots

**Publication discloses explicitly selected JSON through [account custody](DELVE.md); it performs no admission.** External publication is paused. These non-feed records consume no social-post interval. Receipts can expose input, state, law, protocol, results and outbox; select a public world before authorizing writes.

```sh
python3 scripts/receipts.py request /private/public-request.json --intent request-1
python3 scripts/receipts.py receipt /private/public-receipt.json --intent receipt-1
python3 scripts/receipts.py root /private/public-root.json --intent root-0
python3 scripts/receipts.py root /private/new-root.json \
  --intent root-1 --expected-cid PREVIOUS_CID
```

`--state` selects private custody; `--credentials` selects external credentials. Success prints exact-readback URI/CID.

All collections use `$type` and `profile:"delvetalk-live-v1"`:

| `org.delvetalk.*` | Fields |
| --- | --- |
| `request` | `requestJson` ([wire](CLERK.md), [transactions](TRANSACTION-INTAKE.md)) |
| `receipt` | `requestRef:{uri,cid}`, `author`, `object` or sorted `objects`, `receiptJson`, `sha256` |
| `root` | `object`, decimal-string `version`, `rootJson`, `sha256` |

JSON strings preserve exact selected UTF-8 bytes and arbitrary numbers. Hashes cover those bytes; discovery metadata must match. Duplicate members/non-JSON numbers refuse. Root references are shape-checked here, resolved by the clerk. Publication authenticates the custodian's claim, not arbitrary local files as Lean results.

Request/receipt keys derive from account, kind and intent; creation uses `swapRecord:null`. Root keys derive from account/object: one identity must keep one world's version history. Root updates require increasing versions and exact observed CID; CAS losers never rebase automatically. This overwritten record is a discovery pointer, not an append-only revision card.

Retry lost replies with **identical intent, input bytes and expected CID**. Fsynced preparation fixes the record; readback reconciles equality or refuses conflict. Confirmed deletions stay deleted. Superseded confirmed roots return historical confirmation without replaying writes.

Publish receipt first, then a fresh root snapshot. These are separate commits; after interruption reconcile receipt, then publish latest root. Pointer lag or missing publication says nothing about world commit. Outbox data is not delivery.

[Implementation](../scripts/receipts.py), [fake-PDS retry/CAS tests](../conformance/test_receipts.py).
