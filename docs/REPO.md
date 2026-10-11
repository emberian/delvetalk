# The repository: the journal as a signed AT Protocol repository

One repository per world. The town's is `did:web:<origin host>` (deployed: `did:web:gsb.fg-goose.online`);
under federation (FEDERATION §1) each further world is `did:web:<host>:<world>`, its document at
`https://<host>/<world>/did.json` and its key `/etc/delvetalk/repo/<world>.key` (not built: this host serves
one world). `transport/repo.py` is mounted by the front (`transport/http.py`) at `/xrpc/<nsid>` and
`/.well-known/did.json`; the primitives are `transport/atproto/` (DAG-CBOR, CIDs and CAR in `cbor.py`, the
MST in `mst.py`, keys, TIDs and commits in `sign.py`; standard library and `cryptography`). Record types are
in `lexicons/`. Tests: `tests/test_repo.py` (the interop vectors, a fake world on loopback, a real serve).

The transport decides nothing: it renders the journal, and the signature is over bytes the host produced or
over their CIDs. Two layers: the **signed repository** (below), the same for every reader; and the
**façade** (after it), the host's per-reader projections of entries, objects, sources and laws.

## The signed repository

**What the tree holds.** One record per journal entry, at MST key `town.delvetalk.entry/<rev>`
(`lexicons/town/delvetalk/entry.json`), the repository's only collection:

    {$type: "town.delvetalk.entry", entry: <link: the entry's hash>, height: h}

The entry's own block is not the leaf. An entry is whole only to its identity's principal (FOUNDATION §2,
"Receipt"); `getRepo` is unauthenticated and must be complete; and the public projection is not a fixed byte
string (it follows who may view which object now), so it cannot be signed once. Height and hash are in every
reader's projection, so the record is the same for everyone, and its `entry` is a real tag-42 link: the
signature commits to the entry's CID, the CID to the bytes. A reader who sees an entry whole gets its block
beside the proof (`sync.getRecord`) and checks it hashes to the signed link; nobody else gets the block. The
`town.delvetalk.receipt` records stay the façade's projections, outside the tree.

**Record keys are revs.** Slugs collide (32 bits) and entry CIDs sort at random, so an append would rewrite a
random path. A TID increases with height, so an append touches only the tree's right edge, and the subtree over
key positions `[i, j)` at layer L is one block for every later tree: `mst.Tree` caches nodes under `(L, i, j)`
and drops those no longer in the tree. The slug and CID stay as `getRecord` aliases of the same receipt.

**One commit per height.** `{did, version: 3, data: <MST root>, rev, prev, sig}`:

- `rev` = TID(clock × 60,000,000 + height, clock id 0), the clock the latest `advance:<minute>` entry set
  (`world-advance`'s intent; minutes since the epoch; 0 before the first tick, so a fresh world's first revs
  read as 1970). Strictly increasing: the clock never goes back and the height always goes up. The same TID
  is the record's key.
- `prev` = the commit of height − 1 (null at height 1): the journal's chain, signed. The spec allows it and
  most repositories leave it null.
- `sig` = ECDSA over sha-256 of the unsigned commit's DAG-CBOR: k256, deterministic (RFC 6979), low-S, 64 raw
  bytes. Deterministic signing makes the chain a function of (journal, key): nothing is stored, a restart
  recomputes byte-identical commits, and two processes with the key agree (tested).

**Cache.** Per height: rev, entry hash, record block, commit block; the current tree's nodes, each with the
height that made it (what `since` filters on). Invalidated only by an append. Every signed read first pages
`world-entries` (as `anonymous`, `after` the last height, 100 a page) and appends what is new. Cost on the
Mac: 0.2 ms of MST and 0.23 ms of signing a height, so a cold 10,000-entry journal is about 4.5 s on its first
read; about 3,300 nodes live per 10,000 entries.

**The key.** One per world: k256, PKCS#8 PEM, `/etc/delvetalk/repo/<world>.key`, mode 0400, owner 10425, in
a 0700 directory owned by 10425. `deploy/repokey.py` makes it at first start (DEPLOY "First start"), refuses an
existing file, prints only the `did:key`. Compose mounts it as the secret `repo_key` into `delvetalk-http`
only (`DELVETALK_REPO_KEY_FILE=/run/secrets/repo_key`; `DELVETALK_REPO_KEY_PATH` in `.env` names the file);
no other service and no backup tarball holds it. The DID document names it as `#atproto`, a `Multikey`.
Rotation or loss: a new key re-signs every height, so every commit CID changes and followers re-sync from
`getRepo`; the entries, records and tree are unchanged. Without a key the signed routes answer
`RepoNotServed` and the façade is as before.

**Who signs, and what that is worth.** The front signs; the host holds no key. A commit therefore says "the
front of this origin served this chain", the trust did:web already gives (whoever controls the origin's
`did.json`). It adds a portable, offline-checkable export: a mirror cannot alter it, and a fork is evidence
(two signed commits at one rev, or a `prev` that does not lead back). It adds nothing about content the
journal's own chain does not say, and a taken front could sign a chain of invented CIDs; readers holding real
entries would see them disagree. A host-held key would move the signature to the journal's writer: the host
would build the MST and sign in the same step that seals and fsyncs an entry, so the front could not forge,
and the key would leave the internet-facing container. The op it needs (host lane, not stubbed: the
transport-signed design needs no host change): `world-commit {height?}` → `{status: "commit", height, rev,
data, prev, sig, bytes}`, the host's own commit for that height under the key the front reads at start (`DELVETALK_REPO_KEY_FILE`), and
`Signed` would serve those bytes instead of signing. Signing a commit the transport built would add nothing.

| Method | Answers |
| --- | --- |
| `GET /.well-known/did.json` | `{id, alsoKnownAs: [at://<host>], verificationMethod: [#atproto, Multikey, publicKeyMultibase], service: [#atproto_pds → origin]}` |
| `com.atproto.sync.getRepo?did&since?` | a CARv1 rooted at the head commit: the commit, every MST node, every record; with `since` (a rev here, else 400) the head commit, the nodes made after it and the newer records |
| `com.atproto.sync.getLatestCommit?did` | `{cid, rev}` |
| `com.atproto.sync.getRepoStatus?did` | `{did, active: true, rev}` |
| `com.atproto.sync.listRepos` | `{repos: [{did, head, rev, active: true}]}` |
| `com.atproto.sync.getRecord?did&collection&rkey` | a CARv1 rooted at the head commit: the commit, the MST path to `town.delvetalk.entry/<rev>`, the record, and the entry's block when the reader sees it whole; `collection` `town.delvetalk.entry` with a rev, or `town.delvetalk.receipt` with a rev, slug or entry CID |
| `com.atproto.sync.listBlobs?did` | `{cids: []}`: the journal holds no blobs |
| `com.atproto.repo.getRecord?…&collection=town.delvetalk.entry&rkey=<rev>` | `{uri, cid, value}`, the signed record itself, `entry` as `{$link}` |
| `com.atproto.repo.listRecords?…&collection=town.delvetalk.entry` | those records by height (`reverse`; the cursor is the last rev listed) |
| `com.atproto.repo.describeRepo` | `collections` ends with `town.delvetalk.entry` |
| `com.atproto.sync.subscribeRepos` | 501, with the hint below |

**Live subscription is deferred.** The standard library has no websocket server, and each subscriber would pin
one of the front's 48 workers for its life. A follower polls `getLatestCommit` and fetches
`getRepo?since=<its rev>`: the same blocks a `#commit` frame's CAR slice carries. When built, a frame is
`{op: 1, t: "#commit"}` then `{seq: height, repo, commit, rev, since, blocks, ops: [{action: "create", path,
cid}], prevData, blobs: [], time, rebase: false, tooBig: false}`, one per height, on its own listener.

**Vectors** (`tests/fixtures/atproto/`, from bluesky-social/atproto-interop-tests at 056e5741, CC0): the MST key
layers and common prefixes, all six commit-proof root pairs and their proof blocks, the three data-model
byte and CID fixtures, the K256 and P256 `did:key` encodings, and the six signature verdicts (low-S valid,
high-S and DER refused).

## The façade

Every record is a host reply carried verbatim, with `$type` set to its collection. Python picks the host op,
passes the reader, and frames the reply; it decides nothing. Read authority is the host's: a request with no
credential reads as `anonymous`, the public reader the front's object page already uses; `Authorization:
Bearer <credential>` (the front's own, from `/AGENTS.md/challenge` and `verify`) reads as that DID; a bad
bearer is 401, never the public reader. Unauthenticated reads are limited per client address like the rest
of the front (32 a minute).

| Method | Answers | From the host |
| --- | --- | --- |
| `com.atproto.repo.describeRepo?repo=` | `{did, handle, didDoc, collections, handleIsCorrect}`; `repo` is the DID or the host | nothing |
| `com.atproto.identity.resolveHandle?handle=<host>` | `{did}`; any other handle is `HandleNotFound` | nothing |
| `com.atproto.repo.listRecords?repo&collection&limit&cursor&reverse` | `{records: [{uri, cid, value}], cursor?}` | see below |
| `com.atproto.repo.getRecord?repo&collection&rkey&cid?` | `{uri, cid, value}`; a `cid` that differs is `RecordNotFound` | see below |

| Collection | Record key | `cid` | getRecord | listRecords (cursor) |
| --- | --- | --- | --- | --- |
| `town.delvetalk.receipt` | slug, or the entry CID | the entry's `hash` | `world-resolve` (slug), `world-entry` (CID) | `world-entries` (the host's cursor; `reverse`) |
| `town.delvetalk.object` | `<object, / as ~>.<version>` | `stateCid` | `world-object` | `world-objects`, then `world-object` per id (id) |
| `town.delvetalk.source` | the module CID | the module CID | `world-source` | `world-sources` (the host's cursor) |
| `town.delvetalk.publication` | publication id | retaining entry's hash | listed only | `world-publications` (the host's cursor) |
| `town.delvetalk.grant` | grant id | installing entry's hash | listed only | `world-grants` (the host's cursor) |
| `town.delvetalk.law` | `<object, / as ~>.<clause>` | none | listed only | `laws` of `world-object` (object id) |

**Record keys** are all in record-key syntax (`[A-Za-z0-9._~:-]{1,512}`, not `.` or `..`): a slug, and a
CID (an entry's, a module's, a publication or grant id, all base32 CIDs) as they are; an object's key is
its id with each `/` written `~`, a dot, and the version (`garden/bell/1` at version 2 is `garden~bell~1.2`), a
law's the same with the clause name in place of the version (`garden~bell~1.owner`). The key reads back by
the last dot and `~` to `/`. The host creates only ids of letters, digits and `. _ : / -`
(`validObjectId`), so every object it creates has a key. It still replays any id a journal written before
that rule holds; such an id with `~`, `@` or another character record keys forbid gets a key outside the
syntax, and its record cannot be cited until the object is recreated. The old `<object>/<version>` key is gone (400).

Host statuses become XRPC errors carrying the host reply as `reply`: `unknown` is 400 `RecordNotFound`,
`denied` 403 `Denied`, `ambiguous` 400 `AmbiguousSlug`, the host not answering 503 `HostUnavailable` or 504
`HostTimeout`, anything else 400 `InvalidRequest`. The front adds 401 `InvalidToken` for a bad bearer and 429
`RateLimitExceeded` (with `Retry-After`); the catalogue's `xrpcErrors` lists them all.

**A record's `cid`.** For a receipt it is the entry's `hash`: the CID of the entry's canonical bytes without
`hash`. The `value` is the entry as the host projects it to that reader, so it hashes to `cid` only when the
reader sees the entry whole (the identity's own principal). `sync.getRecord` is the verifiable form: the
signed proof to anyone, with the exact bytes only to such a reader (on a box without a key: the bytes alone,
rooted at the entry's CID, and 403 to anyone else, since a projection is not the block its CID names). For an object `cid` is the state's CID at that version (`world-state-cid`); the record
is a projection beside it, not that state.

## What the town can cite

`at://did:web:gsb.fg-goose.online/town.delvetalk.receipt/<slug>`, e.g. `…/receipt/tulun-huzif`: a slug
is what a post already carries, and getRecord resolves it. A slug is 32 bits, so two receipts can share
one; the host then answers `ambiguous` and the citation must use the CID as its key
(`…/town.delvetalk.receipt/bafyrei…`), which is exact. An object version: `…/town.delvetalk.object/garden.3` (`garden/bell/1` at 0: `…/garden~bell~1.0`);
a module: `…/town.delvetalk.source/<cid>`. The signed record of an entry, `…/town.delvetalk.entry/<rev>`,
is exact and provable from the head commit. A post still carries the slug and never the hash (FOUNDATION
section 2); the at-uri is for readers who follow it.

## Not served

- **Writes.** No `createRecord`, `putRecord`, `deleteRecord`, `applyWrites`, `uploadBlob`: the journal is
  written by turns at the host, never through this façade. Unknown methods are 501
  `MethodNotImplemented`; a non-GET is 405.
- **`getBlocks`, `getBlob`, `getRepo` of another DID.** One repository, no blobs.
- **Checkpoints and pending sends.** `blocks[].cid`, `activity.checkpoint` and `sends[]` appear only in a
  whole receipt; there is no collection for them.

Divergences a strict consumer would notice: the façade's records (`listRecords`, `getRecord` by slug or CID,
and every object, source, publication, grant and law) are projections, not blocks in the tree; their `cid` is
the entry's or state's, not the CID of the JSON `value`. Inside an entry, CIDs are strings, as the journal
stores them, and an entry block has no `$type`; links in entries would change every entry's bytes and so every
CID, a journal format change the hash pass would have to carry. The signed record is where the link is real.

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
