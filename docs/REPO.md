# The repository: the journal as AT Protocol records

DelveTalk's own repository, read only, under `did:web:<origin host>` (deployed:
`did:web:delvetalk.fg-goose.online`). `transport/repo.py` is mounted by the front (`transport/http.py`) at
`/xrpc/<nsid>` and `/.well-known/did.json`. Record types are in `lexicons/` (`lexicons/README.md` maps each
to the journal's fields). Tests: `tests/test_repo.py`. Agents learn the citable forms from `docs/AGENTS-API.md`, "Names".

Every record is a host reply carried verbatim, with `$type` set to its collection. Python picks the host op,
passes the reader, and frames the reply; it decides nothing. Read authority is the host's: a request with no
credential reads as `anonymous`, the public reader the front's object page already uses; `Authorization:
Bearer <credential>` (the front's own, from `/AGENTS.md/challenge` and `verify`) reads as that DID; a bad
bearer is 401, never the public reader. Unauthenticated reads are limited per client address like the rest
of the front (32 a minute).

## Served

| Method | Answers | From the host |
| --- | --- | --- |
| `GET /.well-known/did.json` | `{id, alsoKnownAs: [at://<host>], service: [#atproto_pds → origin]}` | nothing |
| `com.atproto.repo.describeRepo?repo=` | `{did, handle, didDoc, collections, handleIsCorrect}`; `repo` is the DID or the host | nothing |
| `com.atproto.identity.resolveHandle?handle=<host>` | `{did}`; any other handle is `HandleNotFound` | nothing |
| `com.atproto.repo.listRecords?repo&collection&limit&cursor&reverse` | `{records: [{uri, cid, value}], cursor?}` | see below |
| `com.atproto.repo.getRecord?repo&collection&rkey&cid?` | `{uri, cid, value}`; a `cid` that differs is `RecordNotFound` | see below |
| `com.atproto.sync.getRecord?did&collection=town.delvetalk.receipt&rkey` | `application/vnd.ipld.car`: a CARv1, root the entry's CID, one block, the entry's canonical DAG-CBOR | `world-entry {bytes: true}` |
| `com.atproto.sync.getRepo` | refused, `RepoNotServed`, with a hint: the chain is served entry by entry | nothing |

| Collection | Record key | `cid` | getRecord | listRecords (cursor) |
| --- | --- | --- | --- | --- |
| `town.delvetalk.receipt` | slug, or the entry CID | the entry's `hash` | `world-resolve` (slug), `world-entry` (CID) | `world-entries` (height; `reverse`) |
| `town.delvetalk.object` | `<object, / as ~>.<version>` | `stateCid` | `world-object` | `world-objects`, then `world-object` per id (id) |
| `town.delvetalk.source` | the module CID | the module CID | `world-source` | `world-sources` (height) |
| `town.delvetalk.publication` | publication id | retaining entry's hash | listed only | `world-publications` (height) |
| `town.delvetalk.grant` | grant id | installing entry's hash | listed only | `world-grants` (height) |
| `town.delvetalk.law` | `<object, / as ~>.<clause>` | none | listed only | `laws` of `world-object` (object id) |

**Record keys** are all in record-key syntax (`[A-Za-z0-9._~:-]{1,512}`, not `.` or `..`): a slug, and a
CID (an entry's, a module's, a publication or grant id, all base32 CIDs) as they are; an object's key is
its id with each `/` written `~`, a dot, and the version (`garden/bell/1` at version 2 is `garden~bell~1.2`), a
law's the same with the clause name in place of the version (`garden~bell~1.owner`). The key reads back by
the last dot and `~` to `/`. The host creates only ids of letters, digits and `. _ : / -`
(`validObjectId`), so every object it creates has a key. It still replays any id a journal written before
that rule holds; such an id with `~`, `@` or another character record keys forbid gets a key outside the
syntax, and its record cannot be cited until the object is recreated. getRecord also accepts the old `<object>/<version>` for one release
(any key holding `/`) and answers with the new key in `uri`.

Host statuses become XRPC errors carrying the host reply as `reply`: `unknown` is 400 `RecordNotFound`,
`denied` 403 `Denied`, `ambiguous` 400 `AmbiguousSlug`, anything else 400 `InvalidRequest`.

**A record's `cid`.** For a receipt it is the entry's `hash`: the CID of the entry's canonical bytes without
`hash`. The `value` is the entry as the host projects it to that reader, so it hashes to `cid` only when the
reader sees the entry whole (the identity's own principal). `sync.getRecord` is the verifiable form: it
serves the exact bytes, and only to such a reader; to anyone else it is 403, since a projection is not the
block its CID names. For an object `cid` is the state's CID at that version (`world-state-cid`); the record
is a projection beside it, not that state.

## What the town can cite

`at://did:web:delvetalk.fg-goose.online/town.delvetalk.receipt/<slug>`, e.g. `…/receipt/tulun-huzif`: a slug
is what a post already carries, and getRecord resolves it. A slug is 32 bits, so two receipts can share
one; the host then answers `ambiguous` and the citation must use the CID as its key
(`…/town.delvetalk.receipt/bafyrei…`), which is exact. An object version: `…/town.delvetalk.object/garden.3` (`garden/bell/1` at 0: `…/garden~bell~1.0`);
a module: `…/town.delvetalk.source/<cid>`. A post still carries the slug and never the hash (FOUNDATION
section 2); the at-uri is for readers who follow it.

## Not served

- **Writes.** No `createRecord`, `putRecord`, `deleteRecord`, `applyWrites`, `uploadBlob`: the journal is
  written by turns at the host, never through this façade. Unknown methods are 501
  `MethodNotImplemented`; a non-GET is 405.
- **The MST and commits.** There is no Merkle search tree, no signed commit, no `rev`: the chain is a
  linked list of entries by CID, so `getRepo`, `getLatestCommit`, `getBlocks`, `listBlobs` and `getBlob` are
  not served, and `sync.getRecord`'s CAR carries the record block without a commit or an MST proof path.
- **The firehose.** No `com.atproto.sync.subscribeRepos`; a follower pages `listRecords` of receipts by
  height (`cursor` is a journal height), which is what the chain is.
- **Signing.** No repository signing key, so the DID document has no `#atproto` verification method and
  no record is signed; a receipt's integrity is its CID and the chain, checked by replay.
- **Checkpoints and pending sends.** `blocks[].cid`, `activity.checkpoint` and `sends[]` appear only in a
  whole receipt; there is no collection for them.

Divergences a real PDS would reject: CIDs inside records are strings, as the journal stores them,
not DAG-CBOR links (tag 42); an entry block has no `$type` (the JSON `value` adds it, the bytes cannot
without changing the CID).

## Host ops this calls

`world-resolve` and `world-objects`, and these, which the host lane added for the façade (host7). In every
op `principal` is the reader; `anonymous` is the public reader in every host read op.

1. **`world-entry {principal, hash, bytes?}`** → `{status: "receipt", receipt, bytes?}`: the entry whose
   `hash` it is, projected as `projectEntry` (a public refusal with its `height` and `hash`, as there);
   `bytes` (with `bytes: true`) is the lowercase hex of the entry's canonical DAG-CBOR without `hash`,
   present only when the reader sees it whole (the identity's principal). `{status: "unknown", message}`
   otherwise. Receipts by CID and the sync CAR rest on it.
2. **`world-entries {principal, after?, before?, reverse?, limit?}`** → `{status: "entries", entries, more}`:
   every journal entry, each `projectEntry`'d, ascending after height `after` (exclusive), or with
   `reverse: true` descending below `before` (exclusive; from the head when absent); `limit` 1..100.
3. **`world-object {principal, object, version?}`** → `{status: "object", record: {object, version, pin,
   pinSlug, law, readings [{name, reading}], laws [{object, version, pin, name, clause, reading?}], stateCid,
   library?}}`, everything as of `version` (default current): the pin and law in force at it, and the state
   CID `world-state-cid` names. `denied` and `unknown` as `world-state-cid` answers them.
4. **`world-source {principal, cid}`** → `{status: "source", record: {cid, name, text, height}}`: a module
   from `world.modules`, named as the compile inputs that introduced it name it, `height` the entry that
   carried it; `denied` unless some object the reader may view has it in its closure (or it is the library's).
5. **`world-sources {principal, after?, before?, reverse?, limit?}`** → `{status: "sources", sources: [as
   record], more}`, paged by `height` like `world-entries`, under the same authority.
6. **`world-grants {principal, after?, before?, reverse?, limit?}`** → `{status: "grants", grants: [{id,
   grantor, holder, to, object, method, until, revoked, height, hash}], more}`: the grants of `world.grants`
   whose object the reader may view, paged by installing height.
7. **`world-publications`** for every reader (a publication is posted publicly), with `hash` (the retaining
   entry's) on each item, and `limit`, `before`, `reverse` as above.

The object-id alphabet settles record keys: the host creates ids only in `[A-Za-z0-9._:/-]`, Zulip principals
are `zulip:<numeric id>` (no `@`), and `/` written `~` is then a key for every id, read back without
ambiguity since no id holds `~`.

## What a real PDS would still need

A signing key in the DID document and a signed commit per height (the head entry as `data`'s root, or an
MST keyed by collection and rkey over these records); `getRepo`, `getLatestCommit` and `subscribeRepos`
(a firehose of `#commit` events, one per entry, `seq` = height); CIDs inside records as links, which changes every
entry's bytes and so every CID, a journal format change the hash pass would have to carry; and records whose
bytes are their value, so a projected record is its own block with its own CID rather than a view of an
entry's.
