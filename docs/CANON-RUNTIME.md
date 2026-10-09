# History preserves evidence; admission selects the head

**An append-only chain does not decide current authority.** Two authorized successors of one head can both exist. Timestamps, fresh keys and supersession links do not serialize them. Select the head and each terminal outcome through a named exclusive admission rule. Safety—at most one outcome—does not establish eventual completion.

## Identity is not currentness

An [AT URI](https://atproto.com/specs/at-uri-scheme) names a DID-owned record path; URI+CID pins content. Neither establishes current application authority or continued availability. [Repositories](https://atproto.com/specs/repository) permit updates/deletions; fresh revision keys are application discipline. [Account migration](https://atproto.com/guides/account-migration) can preserve identity, but the [v1 clerk](../profiles/CLERK.md) requires its configured PDS and exact returned URI/CID. It does not follow migration.

## Commit against current authority

[WorldCore](../profiles/WorldCore.lean) checks `authorizeRequest` against the stored law, then `rootCheck` against the complete protocol/law/version/state root. Proposed law cannot authorize itself. Deliberate lockout has no owner bypass. If policy and data later become separate objects, both dependencies must remain in the atomic read set; historical references alone are insufficient.

Exact retries recover retained terminal receipts, including refusals. The clerk binds a source URI to its first admitted CID and derives its intent from that URI. Two new URIs remain two intents. Domain uniqueness requires state guards: [welcome-once](../protocols/welcome-once/protocol.json) consumes one empty slot regardless of request identity. An outbox intent does not prove delivery.

## Publication is a separate boundary

[Receipt publication](../profiles/RECEIPTS.md) uses create-only intent keys for requests/receipts and a stable object key with increasing version and previous-CID CAS for current roots. AT's [`putRecord`](https://docs.bsky.app/docs/api/com-atproto-repo-put-record) supplies conditional writes. This adapter refuses a losing CAS; it does not automatically rebase or bind other repository writers.

Runtime commit, receipt publication and root publication are separate operations. Missing publication does not imply failure; a fetched root need not be the runtime head. Retain uncertain bytes for exact reconciliation. Immutable evidence and mutable discovery pointers are compatible.

[History replay](../profiles/HISTORY.md) reconstructs local admissions from trusted genesis/head anchors and a separately trusted matching engine. It does not authenticate public authorship or establish distributed consensus. Independent hosts still need explicit head selection, authority, recovery and delivery contracts.
