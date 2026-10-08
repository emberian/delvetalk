# Public canon, current authority, and runtime commitment

An append-only public history and a mutable authoritative head can work together. The important question is which operation selects the head, under whose current authority, against which exact preimage. This document distinguishes AT Protocol guarantees, the implemented DelveTalk v1 profiles, and design obligations for a richer canon/runtime protocol. It does not claim a distributed commit protocol or authorize publication.

## Identity, content, and currentness

A DID-based AT URI identifies a record location in an account's repository, not a particular PDS hostname. The account's current PDS is located through its DID document; ordinary account migration can preserve the DID and record path. A URI alone does not pin record contents. Pair it with a CID when identifying an exact version. Neither the URI nor URI+CID establishes that this version is the current authoritative application head or that its bytes remain available. These are the official [AT URI](https://atproto.com/specs/at-uri-scheme), [repository](https://atproto.com/specs/repository), and [migration](https://atproto.com/guides/account-migration) distinctions.

The implemented clerk is narrower: [`verify_repository`](../scripts/clerk.py) requires the DID document's PDS service to equal the configured Delve PDS, and `fetch_record` reads there and requires the exact returned URI/CID. **This v1 profile does not follow PDS migration.** A migration-capable receiver would require deliberate identity resolution, endpoint validation and custody/recovery behavior; a durable-looking DID URI does not implement those steps for it. See [CLERK](../profiles/CLERK.md).

Creating every revision under a fresh rkey is an application append-only discipline. AT Protocol itself permits record updates and deletions. Replacing a record at the same URI supersedes the mapping to its former version; it does not logically imply all copies of the former content were erased, nor promise that any copy remains retrievable. The official [repository specification](https://atproto.com/specs/repository) describes a mutable mapping of record paths to content-addressed records. Retaining receipts and exact source records locally therefore has an independent purpose.

## A chain is not a head-selection rule

Suppose two authorized writers both read head `H0` and append:

```text
A: previous = H0, proposed law = LA
B: previous = H0, proposed law = LB
```

Both events can be validly authored, immutable and content-addressed. Neither append proves that its law became the one current law. Selecting “latest” needs a specified ordering and admission rule; timestamps, fresh rkeys and a `supersedes` edge do not themselves serialize concurrent transitions. An application can select one head with an authorized compare-and-swap, or define another explicit adjudication protocol. If it permits branches, consumers need to know how branches affect authority.

The same issue applies to terminal events. Two records can both say they supersede a pending request with a different terminal outcome. Append-only storage preserves the disagreement; it does not prevent it. A terminal slot must be selected by the receiving state machine or some other defined exclusive admission mechanism. “At most one terminal result” is a safety property; “every admitted request eventually gets a terminal result” adds liveness assumptions about scheduling, storage and recovery. A slot alone proves neither eventual execution nor external delivery.

For law changes, admission must check the **current law before the change** and atomically advance the selected law/head. A record declaring its own author authorized under its newly proposed law is not sufficient. DelveTalk's local implementation calls `authorized` on the stored object before changing `law`; it permits deliberate lockout and supplies no owner recovery bypass. See [`World.transition`](../profiles/WorldCore.lean).

## What must be in a read set

A proposal that depends on data root `D0` and authority root `L0` must be refused or re-evaluated if either relevant preimage changed before commitment. Guarding only `D0` permits a proposal prepared under old authority to commit under a new authority state without checking that change. The read set must include policy/authority dependencies as well as application data dependencies, and the receiver must check their current values in its commitment operation.

DelveTalk's local object root already contains protocol, law, version and state. [`World.rootCheck`](../profiles/WorldCore.lean) compares the complete expected object, while current authorization is checked independently. A future design splitting policy and data into separate objects must preserve this coverage rather than merely adding separate historical URI+CID references. A reference establishes an exact historical input; an atomic preimage check establishes that it was still acceptable when the transition committed.

## Retry identity is not domain uniqueness

The clerk binds a source URI to its first admitted CID, derives a durable request intent from that URI, and replays its retained terminal result on retry. This prevents a lost reply from turning the same request into a second execution. It does not prevent two fresh request URIs from asking for the same semantic action. See [CLERK's replay contract](../profiles/CLERK.md).

For a door that should welcome only once, “one result per request” is insufficient. The object needs a guarded state transition such as `welcome = null` to `welcome = entry`. The actual [welcome-once protocol](../protocols/welcome-once/protocol.json) does this. Under serialized admission, two independent intents cannot both pass that guard against the same current object. The retained outbox records an intent to deliver a welcome; an external messaging system still needs its own delivery/reconciliation contract.

## The existing hybrid design

The [receipt publisher](../scripts/receipts.py) and its [profile](../profiles/RECEIPTS.md) implement a useful hybrid:

| Item | Identity and update discipline | What it establishes |
| --- | --- | --- |
| Request / receipt | Intent-derived key, create-only through this adapter | Stable bytes for a particular publication intent |
| Current-root publication | Object-derived stable key, increasing world version, previous-CID CAS | Ordered publication updates through this adapter |
| Local object | Custodied state, current-law check, exact-root check, retained reply | Local admission and retry behavior |

The AT API supports conditional writes using `swapRecord` and `swapCommit`; see the official [`putRecord` reference](https://docs.bsky.app/docs/api/com-atproto-repo-put-record). DelveTalk uses the record guard and refuses a losing CAS rather than automatically rebasing. This is a protocol enforced by its adapter and named custodian, not a claim that all writers to the AT repository obey it.

A mutable current-root publication does not undermine immutable receipts: it is a discovery pointer to current published state. Updating it may leave earlier content available elsewhere, and historical receipts retain their own content references. Conversely, appending immutable events would not remove the need for an authoritative head-selection rule.

Publication of a receipt and publication of the root are separate operations. A crash can leave a valid receipt visible while the public pointer is behind; the runtime may also commit before any receipt is published. The publisher retains uncertain operation bytes for exact reconciliation. Observers must not infer “did not commit” from a missing publication or “current runtime state” from the newest snapshot they happen to have fetched.

These points support append-only evidence plus serialized mutable heads as a viable architecture. Extending the local profile to independent hosts still requires a named authority model, conflict-selection protocol, read-set admission boundary, crash recovery assumptions and external delivery semantics. None follows merely from recording a chain of CIDs.
