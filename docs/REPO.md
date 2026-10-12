# The repository: the journal as a signed AT Protocol repository

One repository per world. The town's is `did:web:<origin host>` (deployed: `did:web:gsb.fg-goose.online`);
under federation (FEDERATION §1) each further world is `did:web:<world>.<origin host>` (`ring.gsb.fg-goose.online`),
its document at `https://<world>.<origin host>/.well-known/did.json` and its key `/etc/delvetalk/repo/<world>.key`
(`repo.world_origin`; a front serves one world, `--world`). An atproto did:web is a hostname, never a path
("only hostname-level did:web DIDs are supported", atproto.com/specs/did), so `did:web:<host>:<world>` is not one;
nor are worlds collections of one repository, since a commit is a function of one journal, its key and its epoch ledger, and two
journals' heights do not interleave. A world's hostname needs the wildcard DNS record and certificate of
docs/ATPROTO.md §4 (L7) before its document resolves. `transport/repo.py` is mounted by the front (`transport/http.py`) at `/xrpc/<nsid>` and
`/.well-known/did.json`; the primitives are `transport/atproto/` (DAG-CBOR, CIDs and CAR in `cbor.py`, the
MST in `mst.py`, keys, TIDs and commits in `sign.py`; standard library and `cryptography`). Record types are
in `lexicons/`. Tests: `tests/test_repo.py` (the interop vectors, a fake world on loopback, a real serve).

The transport decides nothing: it renders the journal, and the signature is over bytes the host produced or
over their CIDs. Two layers: the **signed repository** (below), the same for every reader; and the
**façade** (after it), the host's per-reader projections of entries, objects, sources and laws.

The next carry re-derives every MST key and commit CID from the journal under `online.fg-goose.gsb.*`,
and the front serves records and projection queries under this namespace. Residents' mirror readers must list these collections;
the posting account's orphaned old records are deleted by the owner's authorized mirror run (DEPLOY "A new binary").

## The signed repository

**What the tree holds.** One record per journal entry, at MST key `online.fg-goose.gsb.entry/<rev>`
(`lexicons/online/fg-goose/gsb/entry.json`), the signed tree's only collection:

    {$type: "online.fg-goose.gsb.entry", entry: <link: the entry's hash>, height: h}

The entry's own block is not the leaf. An entry is whole only to its identity's principal (FOUNDATION §2,
"Receipt"); `getRepo` is unauthenticated and must be complete; and the public projection is not a fixed byte
string (it follows who may view which object now), so it cannot be signed once. Height and hash are in every
reader's projection, so the record is the same for everyone, and its `entry` is a real tag-42 link: the
signature commits to the entry's CID, the CID to the bytes. A reader who sees an entry whole gets its block
beside the proof (`sync.getRecord`) and checks it hashes to the signed link; nobody else gets the block.
Receipts are per-reader projections served by `online.fg-goose.gsb.getProjection`, outside the tree.

**Record keys are revs.** Slugs collide (32 bits) and entry CIDs sort at random, so an append would rewrite a
random path. A TID increases with height, so an append touches only the tree's right edge, and the subtree over
key positions `[i, j)` at layer L is one block for every later tree: `mst.Tree` caches nodes under `(L, i, j)`
and drops those no longer in the tree. The slug and entry CID are keys for the same receipt projection in `getProjection`.

**Commits.** One per height, plus a sync commit at each key rotation: `{did, version: 3, data: <MST root>, rev, prev, sig}`:

- `rev` = TID(clock × 60,000,000 + height, clock id 0), the clock the latest `advance:<minute>` entry set
  (`world-advance`'s intent; minutes since the epoch; 0 before the first tick, so a fresh world's first revs
  read as 1970). The epoch ledger supplies a clock floor across carries and rotations. The clock never goes
  back and the height always goes up; 60,000,000 exceeds any journal height, so raising the floor one minute
  puts the new epoch above every earlier rev. The same TID is the entry record's key.
- A carried journal begins at the height the world before reached (HOST-HANDOFF 5.182; the live v10 town's first
  entry is 447). A changed journal base starts a `carry` epoch at its first height, with a clock floor of the
  ledger's last head clock + 1 and `prev` null. Its tree begins empty and holds only this journal's records:
  pre-carry entry records leave the tree, a deliberate reconciliation requiring a full `getRepo`. `since` and
  the cursors count from the carried journal's start; pre-carry revs are not cursors in this tree.
- `prev` = the last signed commit (null at the journal's start and at a rotation's sync commit). The spec allows it and
  most repositories leave it null.
- `sig` = ECDSA over sha-256 of the unsigned commit's DAG-CBOR: k256, deterministic (RFC 6979), low-S, 64 raw
  bytes. Deterministic signing makes the chain a function of (journal, key, ledger): a restart recomputes
  byte-identical commits, and two processes with these inputs agree (tested).

**Chain epochs.** `State.repo_ledger`, `<state>/worlds/<world>/repo.json`, holds `key` (the last epoch's did:key),
`base` (first journal height − 1), `epochs` (`{height, clock, cause}`, cause `carry` or `rotation`), and `head`
(`{height, rev, clock}`, null until the first commit). The first signed read compares key and base once. A carry
starts a new tree under the current key, including when the key changed too. A rotation on the same journal
starts after the last served height H: that height's records retain their revs, then a sync commit signs the
same MST root with `rev = TID((head.clock + 1) × 60,000,000)`, `prev` null. Height H+1 uses the raised clock floor
and chains from the sync commit. Earlier commit blocks are not rebuilt with the replacement key; their record
revs and rotation sync revs remain cursors for `getRepo?since`. Proofs and exports serve only the current head commit.
Epochs stay in the ledger across carries; only those belonging to the current journal affect its reconstruction.
Writes use atomic `State.write` inside `Signed.lock`, after the commits exist; an unchanged key, journal and
head leave the ledger bytes untouched. The carry copies the ledger with the transport files, and state backups
must keep it. Deleting the ledger is the one way to regress revs: the next start writes a new ledger from the
journal and key, and followers must re-sync.

**Cache.** Per height: rev, entry hash, record block, commit block (absent before the current signing epoch);
the served head, which can be a rotation's sync commit; the current tree's nodes, each with the height that
made it (what `since` filters on). Every signed read first pages
`world-entries` (as `anonymous`, `after` the last height, 100 a page) and appends what is new. Cost on the
Mac: 0.2 ms of MST and 0.23 ms of signing a height, so a cold 10,000-entry journal is about 4.5 s on its first
read; about 3,300 nodes live per 10,000 entries.

**The key.** One per world: k256, PKCS#8 PEM, `/etc/delvetalk/repo/<world>.key`, mode 0400, owner 10425, in
a 0700 directory owned by 10425. `python3 -m transport repokey` makes it at first start (DEPLOY "First start"), refuses an
existing file, prints its path and public `did:key`. `DELVETALK_REPO_KEYS` names the directory; compose mounts it
read-only into the front and read-write into the ops container that runs `repokey`. The host holds no key, and
state backup tarballs exclude this directory. The DID document names the key as `#atproto`, a `Multikey`.
Rotation or key loss: replace the key out of band and restart the front (DEPLOY); the first signed read records
a rotation epoch and signs one higher-rev sync commit over the same tree. Entry records keep their keys and CIDs,
and old-rev deltas still work within this journal. Loss of the ledger requires a full re-sync. Without a key the signed routes answer
`RepoNotServed`; projection queries and the four mirrored record collections remain available.

**Who signs, and what that is worth.** The front signs; the host holds no key. A commit therefore says "the
front of this origin served this chain", the trust did:web already gives (whoever controls the origin's
`did.json`). It adds a portable, offline-checkable export: a mirror cannot alter it, and a fork is evidence
(two signed commits at one rev, or a `prev` that does not lead back). It adds nothing about content the
journal's own chain does not say, and a taken front could sign a chain of invented CIDs; readers holding real
entries would see them disagree. A host-held key would move the signature to the journal's writer: the host
would build the MST and sign in the same step that seals and fsyncs an entry, so the front could not forge,
and the key would leave the internet-facing container. The op it needs (host lane, not stubbed: the
transport-signed design needs no host change): `world-commit {height?}` → `{status: "commit", height, rev,
data, prev, sig, bytes}`, the host's own commit for that height under the key the front reads at start (`State.repo_key`), and
`Signed` would serve those bytes instead of signing. Signing a commit the transport built would add nothing.

| Method | Answers |
| --- | --- |
| `GET /.well-known/did.json` | `{id, alsoKnownAs: [at://<host>], verificationMethod: [#atproto, Multikey, publicKeyMultibase], service: [#atproto_pds → origin]}` |
| `com.atproto.sync.getRepo?did&since?` | a CARv1 rooted at the head commit: the commit, every MST node, every record; with `since` (a rev here, else 400) the head commit, the nodes made after it and the newer records |
| `com.atproto.sync.getLatestCommit?did` | `{cid, rev}` |
| `com.atproto.sync.getRepoStatus?did` | `{did, active: true, rev}` |
| `com.atproto.sync.listRepos` | `{repos: [{did, head, rev, active: true}]}` |
| `com.atproto.sync.getRecord?did&collection&rkey` | a CARv1 rooted at the head commit: the commit, the MST path to `online.fg-goose.gsb.entry/<rev>`, the record, and the entry's block when the reader sees it whole; `collection` is `online.fg-goose.gsb.entry`, `rkey` its record rev. No other collection has a signed path here |
| `com.atproto.sync.listBlobs?did` | `{cids: []}`: the journal holds no blobs |
| `com.atproto.repo.getRecord?…&collection=online.fg-goose.gsb.entry&rkey=<rev>` | `{uri, cid, value}`, the signed record itself, `entry` as `{$link}` |
| `com.atproto.repo.listRecords?…&collection=online.fg-goose.gsb.entry` | those records by height (`reverse`; the cursor is the last rev listed) |
| `com.atproto.repo.describeRepo` | `collections` lists `card`, `page`, `index`, `answer`, plus `online.fg-goose.gsb.entry` when signed |
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

## Records and projections

`com.atproto.repo.getRecord` and `listRecords` serve only public records. Their `cid` is always
`str(block(from_json(value))[0])`, including `$type` and DAG-CBOR links. The signed `entry` record is in the
MST. `card`, `page`, `index` and `answer` are rendered by `transport/mirror.py`, exactly the values the mirror
writes to the posting account. These four are read as PUBLIC even with a credential; they have no signed
paths yet, so `sync.getRecord` accepts only `entry/<rev>`. `describeRepo.collections` lists the four and, on a
signing box, `entry`. No projection kind is accepted as a repository collection.

| Public record | Key | Source; listing order |
| --- | --- | --- |
| `online.fg-goose.gsb.entry` | rev | signed height/hash link; journal height, cursor the last rev |
| `online.fg-goose.gsb.card` | object id, `/` as `~` | `mirror.card_record` (`place`); object id |
| `online.fg-goose.gsb.page` | page name | `mirror.library_pages`; shelf order |
| `online.fg-goose.gsb.index` | `self` | `mirror.index_record`; one record |
| `online.fg-goose.gsb.answer` | `<did>.<request rkey>` | bridge answer files (`bridge.answer_turn`); key order |

`repo.getRecord?repo&collection&rkey&cid?` returns `{uri, cid, value}`; a differing `cid` is `RecordNotFound`.
`repo.listRecords?repo&collection&limit&cursor&reverse` returns `{records: [...], cursor?}`. Limits are 1..100,
default 50. `identity.resolveHandle?handle=<host>` returns `{did}`; another handle is `HandleNotFound`.

**Projection queries.** `online.fg-goose.gsb.getProjection?kind&key&cid?` returns `{kind, key, of?, value, signed?}`.
`online.fg-goose.gsb.listProjections?kind&limit&cursor&reverse` returns `{projections: [the same shape], cursor?}`;
limit is 1..100, default 50. `value` is the host's reply for this reader, verbatim, without `$type`.
`of` is the CID of the thing projected, not of `value`. The optional `cid` filter compares `of`; a mismatch
is `RecordNotFound` (a law has no `of`, so any filter mismatches).

| Kind | Key | `of` | Host read; listing cursor |
| --- | --- | --- | --- |
| `receipt` | slug or entry CID | entry's `hash` | `world-resolve` or `world-entry`; `world-entries`, opaque host cursor |
| `object` | `<id, / as ~>.<version>` | `stateCid` | `world-object`; `world-objects` then `world-object`, object-id cursor |
| `source` | module CID | module CID | `world-source`; `world-sources`, opaque host cursor |
| `publication` | publication id | retaining entry's hash | look up in `world-publications`; opaque host cursor |
| `grant` | grant id | installing entry's hash | look up in `world-grants`; opaque host cursor |
| `law` | `<id, / as ~>.<clause>` | absent | clause in `world-object.laws`; object-id cursor or `<id>#<n>` within its clauses |

Host-paged kinds support `reverse`; objects and laws reject it because `world-objects` lists ids in ascending
byte order. A receipt's `signed`, on a signing box when its entry is in the current tree, is
`at://<did>/online.fg-goose.gsb.entry/<rev>`: the record whose `entry` link names `of`. A receipt retained
from before a carry can still resolve without a record in the current tree.

Read authority is the host's: no credential reads as `anonymous` (PUBLIC); `Authorization: Bearer <credential>`
from `/AGENTS.md/challenge` and `verify` reads as that DID; a bad bearer is 401. Anonymous reads are limited
per client address (32 a minute). Publication/grant lookup pages the same host listing under that principal,
so fetching by id reveals no more than listing. A private object and its law remain private.

Keys use `[A-Za-z0-9._~:-]{1,512}`, excluding `.` and `..`. Object ids use `[A-Za-z0-9._:/-]`; encode `/` as
`~`, then append a dot and version or clause (`garden~bell~1.2`, `garden~bell~1.owner`). Decode by the last
dot and `~` to `/`. Replayed ids outside the host's creation alphabet may have no key in this syntax.

Host statuses become XRPC errors carrying the reply: `unknown` → 400 `RecordNotFound`, `denied` → 403
`Denied`, `ambiguous` → 400 `AmbiguousSlug`; unavailable/mute host → 503 `HostUnavailable`/504 `HostTimeout`;
other failures → 400 `InvalidRequest`. The front adds 401 `InvalidToken` and 429 `RateLimitExceeded`
(`Retry-After`). The catalogue's `xrpcErrors` is the error source.

## What the town can cite

A post cites a receipt by its slug, e.g. `tulun-huzif`. A reader resolves it with
`online.fg-goose.gsb.getProjection?kind=receipt&key=tulun-huzif`. Slugs are 32 bits: a collision answers
`AmbiguousSlug`, and the entry CID as `key` is exact. The projection's `of` names that entry; its `signed`
gives the provable at-uri `at://did:web:gsb.fg-goose.online/online.fg-goose.gsb.entry/<rev>`. Fetch that record
with `repo.getRecord` or its path proof with `sync.getRecord`. A principal who sees the entry whole also
gets its canonical block beside the proof, hashing to the record's `entry` link.

Object versions and sources are projections: `getProjection?kind=object&key=garden~bell~1.0` and
`getProjection?kind=source&key=<module CID>`. Their `of` names the state or module, not a repository record
of the returned JSON. Public card/page/index/answer at-uris name actual records with value-derived CIDs.

## Not served

- **Writes.** No `createRecord`, `putRecord`, `deleteRecord`, `applyWrites`, `uploadBlob`: the journal is
  written by turns at the host, never through this façade. Unknown methods are 501
  `MethodNotImplemented`; a non-GET answers 405 `InvalidRequest`.
- **`getBlocks`, `getBlob`, `getRepo` of another DID.** One repository, no blobs.
- **Checkpoints and pending sends.** `blocks[].cid`, `activity.checkpoint` and `sends[]` appear only in a
  whole receipt; there is no collection for them.

Whole entry bytes outside a signed proof belong to `online.fg-goose.gsb.getEntry`, whose lexicon exists;
its service-auth verifier and route are L5 work. An unsigned box serves projections, not a whole-entry CAR.
Inside an entry, CIDs are strings as the journal stores them; its block has no `$type`. Changing them to
links would change the entry bytes and every CID. The signed entry record carries the real link.

## Host ops this calls

`world-resolve` and `world-objects`, and these, which the host lane added for the façade (host7). In every
op `principal` is the reader; `anonymous` is the public reader in every host read op.

1. **`world-entry {principal, hash, bytes?}`** → `{status: "receipt", receipt, bytes?}`: the entry whose
   `hash` it is, projected as `projectEntry` (a public refusal with its `height` and `hash`, as there);
   `bytes` (with `bytes: true`) is the lowercase hex of the entry's canonical DAG-CBOR without `hash`,
   present only when the reader sees it whole (the identity's principal). `{status: "unknown", message}`
   otherwise. Receipts by CID and the sync CAR rest on it.
2. **`world-entries {principal, after?, before?, cursor?, reverse?, limit?}`** → `{status: "entries", entries, more}`:
   every journal entry, each `projectEntry`'d, ascending after height `after` (exclusive), with an opaque host cursor when paged, or with
   `reverse: true` descending below `before` (exclusive; from the head when absent); `limit` 1..100.
3. **`world-object {principal, object, version?}`** → `{status: "object", record: {object, version, pin,
   pinSlug, law, readings [{name, reading}], laws [{object, version, pin, name, clause, reading?}], stateCid,
   library?}}`, everything as of `version` (default current): the pin and law in force at it, and the state
   CID `world-state-cid` names. `denied` and `unknown` as `world-state-cid` answers them.
4. **`world-source {principal, cid}`** → `{status: "source", record: {cid, name, text, height}}`: a module
   from `world.modules`, named as the compile inputs that introduced it name it, `height` the entry that
   carried it; `denied` unless some object the reader may view has it in its closure (or it is the library's).
5. **`world-sources {principal, after?, before?, cursor?, reverse?, limit?}`** → `{status: "sources", sources: [as
   record], more}`, paged by `height` like `world-entries`, under the same authority.
6. **`world-grants {principal, after?, before?, cursor?, reverse?, limit?}`** → `{status: "grants", grants: [{id,
   grantor, holder, to, object, method, until, revoked, height, hash}], more}`: the grants of `world.grants`
   whose object the reader may view, paged by installing height.
7. **`world-publications`** for every reader (a publication is posted publicly), with `hash` (the retaining
   entry's) on each item, and `limit`, `before`, `reverse` as above.

The object-id alphabet settles record keys: the host creates ids only in `[A-Za-z0-9._:/-]`, Zulip principals
are `zulip:<numeric id>` (no `@`), and `/` written `~` is then a key for every id, read back without
ambiguity since no id holds `~`.
