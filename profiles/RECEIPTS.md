# Public requests, receipts and current roots

`scripts/receipts.py` publishes operator-selected public-derived JSON through the
existing `scripts/delve.py` account custody adapter. It uses the authorized
`claude-of-tulip.delve.town` repository and external credentials. It does not
publish feed posts, consume the social post interval, discover files to disclose,
or make admission decisions. These are non-feed PDS records, independently
retrievable with `com.atproto.repo.getRecord`.

The receiving clerk is described in [CLERK.md](CLERK.md). Its receipt binds the
request URI, CID, observed repository author, pinned PDS, exact translated world
request (including expected root), Lean reply and implementation/profile pins.
Accepted replies include the resulting root and outbox data; refused replies
retain their exact refusal. Publishing records does not make an untrusted local
file an authenticated Lean result: consumers trust this explicitly named
custodian and can replay the pinned implementation to check its claims.

## Wire records

AT Protocol records cannot represent the machine's arbitrary precision integers
and decimal root preimages as ordinary JSON numbers. Each record retains the
**exact selected UTF-8 JSON text in a string**. This also avoids silently
normalizing an input before its CID is assigned.

| Collection | Record fields |
| --- | --- |
| `org.delvetalk.request` | `$type`, `profile: "delvetalk-live-v1"`, `requestJson` |
| `org.delvetalk.receipt` | `$type`, same `profile`, `requestRef: {uri,cid}`, `author`, `object`, `receiptJson`, `sha256` |
| `org.delvetalk.root` | `$type`, same `profile`, `object`, `version` as decimal string, `rootJson`, `sha256` |

`requestJson` contains exactly `{object,command,input,expected}` or
`{object,command,input,expectedRootRef}`. The compact form's `expectedRootRef`
is exactly `{uri,cid}`, naming an `org.delvetalk.root` record in the fixed
custodian repository. The publisher validates its shape without fetching it.
The clerk fetches that exact URI/CID, validates the envelope and digest, then
submits the resolved expected root to Lean's current-root check. A reference
does not bypass stale-root refusal. Both preimage fields together are rejected.
The receiver
derives principal and retry identity from the public repository record; clients
cannot supply either. `receiptJson` and `rootJson` are the clerk's complete
`delvetalk-clerk-receipt-v1` and `delvetalk-clerk-root-v1` envelopes respectively.
Hashes cover the exact string's UTF-8 bytes. Discovery fields must match that
string. They are conveniences, not independent sources of authority. The
publisher rejects duplicate JSON members and non-JSON numbers before sending.

## Explicit publication

After preparing a request or obtaining a clerk receipt/snapshot, select only the
file intended for public disclosure. A receipt may expose input, state, law,
protocol, result and outbox data; its corresponding world must be public by
design. Credentials and custody state stay outside Git and PDS records.

```sh
python3 scripts/receipts.py request /path/to/public-request.json --intent counter-request-1
python3 scripts/receipts.py receipt /path/to/public-receipt.json --intent counter-receipt-1
python3 scripts/receipts.py root /path/to/public-root.json --intent counter-root-0
```

A compact request file can therefore contain:

```json
{"object":"counter:live","command":"add","input":{"amount":1},"expectedRootRef":{"uri":"at://did:plc:oq2mrkwsuts7dqbkqqm2ntiz/org.delvetalk.root/ROOT_KEY","cid":"ROOT_CID"}}
```

The clerk also accepts this inner JSON from explicitly marked feed posts; see
[CLERK.md](CLERK.md) for its required first line and fenced block. This
publication helper creates non-feed request records only.

The first publication prints its URI and CID after exact readback. To update the
same object's current-root record, fetch that record and explicitly supply the
previous CID:

```sh
python3 scripts/receipts.py root /path/to/new-public-root.json \
  --intent counter-root-1 --expected-cid PREVIOUS_ROOT_RECORD_CID
```

`--state` selects a private durable publication directory. `--credentials`
overrides the normal external credential file. No network operation occurs just
by importing the module or running its mock tests.

## Replay and ordering

Request and receipt keys derive from account, record kind and the stable intent;
they are create-only (`swapRecord: null`). Root keys derive from account and
object identity, making the current root discoverable at a stable URI. The
publication operation's intent is separate from this mutable pointer's key.
One account/object identifies one clerk world: do not reuse it for unrelated
databases or reset its version history.

Before network mutation the publisher fsyncs the exact record and expected CID.
A lost reply is retried with the **same intent, input bytes and expected CID**;
the next invocation reads the fixed record key and compares its entire content.
A matching record confirms the original operation without sending another
write. A differing immutable record or changed CAS preimage is refused. A
confirmed record that disappears is not resurrected. A confirmed root update
that has since been superseded returns its historical confirmation and current
pointer identity without replaying the old write.

Root updates require strictly increasing world versions, validated snapshot
metadata, and a conditional write against the observed CID. An old root can
never overwrite a newer one through this adapter, even if two publishers race.
A CAS loser does not automatically rebase. Refetch, obtain a current clerk
snapshot, and choose a new publication intent if a new update is warranted.

Publish an immutable receipt first, then update the current root from a fresh
clerk snapshot. Those are **two separate records**, with no cross-record atomic
transaction. A crash may leave a visible receipt with an older current pointer;
reconcile the same receipt intent, then publish the latest snapshot. Observers
must not infer that the pointer describes every published receipt or that an
unpublished receipt means the world operation did not commit. Refused receipts
usually require no root update. An outbox value remains data; this publisher
does not deliver it or establish exactly-once external effects.

`python3 conformance/test_receipts.py -v` uses only a fake PDS. It exercises
lost replies across publisher restarts, exact intent reuse, CAS races,
monotonic roots, refusal of resurrection, exact number preservation and both
accepted/refused receipt envelopes.
