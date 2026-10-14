# The repository: the journal as a signed AT Protocol repository

Each world's journal is served as a read-only, signed AT Protocol repository, plus per-reader projections of what the
host holds. A reader can verify any entry offline against a signed commit and follow the world with standard atproto
tooling; the journal stays written only by turns at the host.

- **One repository per world.** The town's is `did:web:<origin host>` (deployed `did:web:gsb.fg-goose.online`), the
  same principal a new world opens as (config `opener`, `config.town_did`; GENESIS "The town"). Each further world is
  `did:web:<world>.<origin host>` (`ring.gsb.fg-goose.online`), its document at
  `https://<world>.<origin host>/.well-known/did.json`, its key `/etc/delvetalk/repo/<world>.key` (`repo.world_origin`;
  a front serves one world, `--world`). An atproto did:web is a hostname, never a path ("only hostname-level did:web
  DIDs are supported", atproto.com/specs/did), so `did:web:<host>:<world>` is not one; and worlds are not collections
  of one repository, since a commit is a function of one journal, its key and its epoch ledger, and two journals'
  heights do not interleave. A world's hostname needs DNS and a certificate before its document resolves.
- **Two layers:** the **signed repository**, the same for every reader; and the **projections**, the host's per-reader
  replies for entries, objects, sources, laws and the live public values.
- **Plus request-only hosted accounts** for guest and Zulip principals (ATPROTO §4), off by default.
- **Code:** `transport/repo.py`, mounted by the front (`transport/http.py`) at `/xrpc/<nsid>` and
  `/.well-known/did.json`; primitives in `transport/atproto/` (DAG-CBOR, CIDs and CAR in `cbor.py`, the MST in
  `mst.py`, keys, TIDs and commits in `sign.py`; standard library and `cryptography`); record types in `lexicons/`.
- **Tests:** `tests/test_repo.py` (interop vectors, fake world and real serve), `tests/test_repo_epochs.py`,
  `tests/test_firehose.py` and `tests/test_firehose_consumer.py` (sparse inversion and a real WebSocket consumer).

The repository renders the host's journal and signs host-produced bytes or their CIDs. Hosted accounts validate and
sign public request bytes their holders supply; world admission stays with the host. A carry re-derives every MST key
and commit CID from the journal under `online.fg-goose.gsb.*`.

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
- A carried journal begins at the height the world before reached. A changed journal base starts a `carry` epoch at its first height, with a clock floor of the
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

**Cache.** Per height: rev, entry hash, record block, commit block (absent before the current signing epoch),
MST root before and after;
the served head, which can be a rotation's sync commit; the current tree's nodes, each with the height that
made it (what `since` filters on). Every signed read first pages
`world-entries` (as `anonymous`, `after` the last height, 100 a page) and appends what is new.
The firehose polls the same cache once a second. Only an active producer captures inversion-complete
CARs for new heights, in a pending queue capped at 32 MiB. Each append reserves the 2,000,000-byte event
maximum before changing the signed chain; insufficient room refuses signed catch-up with HTTP 503 and
`reply.class: capacity`. Production drains accepted heights and resumes catch-up on the next poll.
A durable commit or head sync releases the covered pending bytes. Cold reconstruction and signed reads
with the firehose disabled retain no event CARs; `EventLog` alone keeps replay bytes.
Normal shutdown disables capture and drains pending events. Failed durable writes keep their bounded
pending bytes until a subsequent producer logs them or reconciles the head with a durable sync.

**The key.** One per world: k256 or p256, PKCS#8 PEM, `/etc/delvetalk/repo/<world>.key`, mode 0400, owner 10425, in
a 0700 directory owned by 10425. `python3 -m transport repokey` makes it at first start (DEPLOY "First start"), refuses an
existing file, prints its path and public `did:key`. `DELVETALK_REPO_KEYS` names the directory; compose mounts it
read-only into the front and read-write into the ops container that runs `repokey`. The host holds no key, and
state backup tarballs exclude this directory. The DID document names the key as `#atproto`, a `Multikey`.
Rotation or key loss: replace the key out of band and restart the front (DEPLOY); the first signed read records
a rotation epoch and signs one higher-rev sync commit over the same tree. Entry records keep their keys and CIDs,
and old-rev deltas still work within this journal. Loss of the ledger requires a full re-sync. Without a key the signed routes answer
`RepoNotServed`; host and live public projection queries remain available.
Hosted keys always derive as k256 from this key's private scalar and each DID, independently of its PEM
encoding or curve. Losing the town key loses every hosted key too; replacing it rotates all hosted documents
and signs higher-rev sync heads with `prev` null, keeping records unchanged. Hosted epochs live in their
snapshots; subsequent writes chain from the new head, and old commits are never re-signed.

**Who signs, and what that is worth.** The front signs; the host holds no key. A commit therefore says "the
front of this origin served this chain", the trust did:web already gives (whoever controls the origin's
`did.json`). It adds a portable, offline-checkable export: a mirror cannot alter it, and a fork is evidence
(two signed commits at one rev, or a `prev` that does not lead back). It adds nothing about content the
journal's own chain does not say, and a taken front could sign a chain of invented CIDs; readers holding real
entries would see them disagree. A host-held key would move the signature to the journal's writer: the host
would build the MST and sign in the same step that seals and fsyncs an entry, so the front could not forge,
and the key would leave the internet-facing container. Designed, not built:
`world-commit {height?}` → `{status: "commit", height, rev,
data, prev, sig, bytes}`, the host's own commit for that height under the key the front reads at start (`State.repo_key`), and
`Signed` would serve those bytes instead of signing. Signing a commit the transport built would add nothing.

| Method | Answers |
| --- | --- |
| `GET /.well-known/did.json` | `{id, alsoKnownAs: [at://<host>], verificationMethod: [#atproto, Multikey, publicKeyMultibase], service: [#atproto_pds → origin, #delvetalk (DelvetalkWorld) → origin]}`; the service entries are present even without a signing key |
| `POST online.fg-goose.gsb.act` | `{call, intent, if?, world?}` under method-bound service auth; caller answerView, public answer keyed by issuer and hashed intent |
| `POST online.fg-goose.gsb.try` | `{call, intent?, if?, world?}` under service auth; previewView with exact card/CID/trace, no receipt or persisted record |
| `POST online.fg-goose.gsb.plan` | `{calls, intent, if?, world?}` under service auth; 1..8 spells in one all-or-nothing host turn, caller answerView and anonymous answer |
| `online.fg-goose.gsb.getEntry?entry&world?` | service-auth query: the entry's identity principal receives a CARv1 rooted at the entry CID holding its one canonical block; another reader 403 `Denied`, unknown 400 `RecordNotFound`. Optional world must equal this front's world, else 400 `InvalidRequest`. No signing key required; authentication policy is ATPROTO §2(b) |
| `com.atproto.sync.getRepo?did&since?` | a CARv1 rooted at the head commit: the commit, every MST node, every record; with `since` (a rev here, else 400) the head commit, the nodes made after it and the newer records |
| `com.atproto.sync.getLatestCommit?did` | `{cid, rev}` |
| `com.atproto.sync.getRepoStatus?did` | `{did, active: true, rev}` |
| `com.atproto.sync.listRepos` | `{repos: [{did, head, rev, active: true}]}` |
| `com.atproto.sync.getRecord?did&collection&rkey` | a CARv1 rooted at the head commit: the commit, the MST path to `online.fg-goose.gsb.entry/<rev>`, the record, and the entry's block when the reader sees it whole; `collection` is `online.fg-goose.gsb.entry`, `rkey` its record rev. No other collection has a signed path here |
| `com.atproto.sync.listBlobs?did` | `{cids: []}`: the journal holds no blobs |
| `com.atproto.repo.getRecord?…&collection=online.fg-goose.gsb.entry&rkey=<rev>` | `{uri, cid, value}`, the signed record itself, `entry` as `{$link}` |
| `com.atproto.repo.listRecords?…&collection=online.fg-goose.gsb.entry` | those records by height (`reverse`; the cursor is the last rev listed) |
| `com.atproto.repo.describeRepo` | `collections` lists only `online.fg-goose.gsb.entry` when signed; empty when unsigned |
| `com.atproto.sync.subscribeRepos?cursor?` | binary WebSocket event stream on `firehose_port`; the HTTP front answers 426 `UpgradeRequired` with `Upgrade: websocket`, or 501 when the port is off |

**Live subscription.** `transport/firehose.py` runs one thread in the front process. Its `selectors` loop
owns its own TCP listener and every subscriber socket, polls `Signed.catch_up(host)` once a second, and emits
new journal heights independently of the front's 48 HTTP workers. `firehose_bind` defaults to `127.0.0.1`,
`firehose_port` to `0` (off); a signing key is required. RFC 6455 handshake, binary messages, validated masked
client controls, ping/pong and close use the standard library. Application frames from clients are closed.
Closing clears inbound bytes, disables read interest, and drops the socket after five seconds if output
has not drained. Invalid HTTP upgrades use the same close deadline.
The edge Caddy route (before the general HTTP proxy), with the deployment's port 8767:

    reverse_proxy /xrpc/com.atproto.sync.subscribeRepos 10.10.1.10:8767

The `delvetalk-http` service needs that port published on the private network (DEPLOY "Firehose").
Each binary WebSocket message contains a DAG-CBOR header `{op: 1, t: "#commit"}` followed by its body:
`{seq, rebase: false, tooBig: false, repo, commit, rev, since, blocks, ops, blobs: [], prevData, time}`.
A live height makes one create op at `online.fg-goose.gsb.entry/<rev>` with its record CID and no `prev`.
`since` is the preceding commit's rev (null at an epoch start); `prevData` is the preceding MST root,
null for an empty tree. `time` is ISO-8601 UTC at log append. The CAR is rooted at the commit and contains it,
the create/update records and every MST node read by server-side inversion: new paths plus neighbours
needed by merges or root shrink. `mst.invert` walks a partial tree, including general update/delete inverses;
`Tree` itself remains append-only. The independent consumer in the tests restores `prevData` using only
those blocks, including rightmost creates at a new highest layer. Event construction never calls `getRepo(since)`.
`fits(ops, blocks)` enforces at most 200 operations and 2,000,000 CAR bytes, inclusive: overflow emits `#sync`
instead. Current height records are small, fixed-shape creates; synthetic budget tests exercise both overflow cases.

**Event positions and custody.** `State.firehose`, `<state>/worlds/<world>/events`, is one length-prefixed
DAG-CBOR file. Each record stores `{seq, kind, epoch, height, frame}`: exact header/body bytes plus the epoch
count and head height covered. Append is fsynced before delivery; the file's directory is fsynced on creation
and replacement. `seq` starts at 1 and increases by exactly 1 across commits, syncs and identities, independently
of heights and revs. Each endpoint serves its world's repository; worlds' overlapping heights never share a cursor.
Carry's `copy_transport` copies `events` unchanged (it is not a `skipped()` file); state backups keep it with
`repo.json`. A partial final record is truncated on restart because it could not have been delivered; a malformed or discontinuous
complete record refuses startup. One front owns each log. Deleting it destroys cursor continuity.

Starting over an empty journal emits no initial event; its first live append is a commit with null
`since` and `prevData`. A first firehose start over an existing journal, unannounced carry/rotation epochs, and journal heights appended
while the firehose was down produce one `#sync` of the current head, rather than reconstructed historical commits.
Its body is `{seq, did, blocks, rev, time}`; `blocks` contains only the head commit, so consumers fetch `getRepo`.
Rotation additionally appends `#identity {seq, did, handle, time}` before sync; carry does not. An unchanged
restart appends nothing. Coverage is in the event records themselves; no second watermark file exists.
Identity is emitted for a key rotation, never at connect. If stopped between identity and sync, restart finishes
the sync without repeating that identity.

**Replay.** `WINDOW = 10_000` events in `transport/firehose.py`, irrespective of kind. The newest 10,000 are
retained for cursors; at 20,000 physical records an atomic rewrite retains that window with identical bytes and
sequence positions. No cursor means live events from the subscription handshake, without replay. `cursor=N`
replays all retained seqs greater than N, then live events; the tail snapshot and live registration are ordered
under the log lock, and live frames wait behind replay. N below the oldest retained seq gets an unsequenced
`#info {name: "OutdatedCursor"}` before replay from the oldest. N above the newest gets `{op: -1}` followed by
`{error: "FutureCursor", message}`, then close; a non-integer or repeated cursor gets `InvalidRequest` and close.
`#info` and errors are connection controls, outside the durable event sequence. Each subscriber has at most
32 MiB of queued bytes, with 128 MiB allowed across all sockets; a reader exceeding a queue budget
is disconnected and can resume by cursor. The listener accepts at most
128 sockets, gives handshakes ten seconds, and sends a ping after thirty seconds without client controls,
closing after a further thirty seconds without a matching pong.

**Vectors** (`tests/fixtures/atproto/`, from bluesky-social/atproto-interop-tests at 056e5741, CC0): the MST key
layers and common prefixes, all six commit-proof root pairs and their proof blocks, the three data-model
byte and CID fixtures, the K256 and P256 `did:key` encodings, and the six signature verdicts (low-S valid,
high-S and DER refused).

## Records and projections

The world's `com.atproto.repo.getRecord`, `listRecords` and `sync.getRecord` accept only `entry`, the signed
MST's collection. `describeRepo.collections` lists `entry` on a signing box and is empty on an unsigned box.
Record CIDs hash their complete values, including `$type` and DAG-CBOR links. Live `card`, `page`, `index`
and `answer` values are projections outside this repository. They use `transport/mirror.py`'s public renderer,
exactly the values it can write to the posting account; only that account's actual records have posting at-uris.

| World repository record | Key | Source; listing order |
| --- | --- | --- |
| `online.fg-goose.gsb.entry` | rev | signed height/hash link; journal height, cursor the last rev |

`repo.getRecord?repo&collection&rkey&cid?` returns `{uri, cid, value}`; a differing `cid` is `RecordNotFound`.
`repo.listRecords?repo&collection&limit&cursor&reverse` returns `{records: [...], cursor?}`. Limits are 1..100,
default 50. `identity.resolveHandle?handle=<host>` returns `{did}`; another handle is `HandleNotFound`.

**Projection queries.** `online.fg-goose.gsb.getProjection?kind&key&cid?` returns `{kind, key, of?, value, signed?}`.
`online.fg-goose.gsb.listProjections?kind&limit&cursor&reverse` returns `{projections: [the same shape], cursor?}`;
limit is 1..100, default 50. Host kinds return this reader's reply verbatim, without `$type`; live public
kinds return the mirror's tagged posting-record values even when the query carries a credential.
`of` is the CID of the thing projected, not of `value`. The optional `cid` filter compares `of`; a mismatch
is `RecordNotFound` (law and live public kinds have no `of`, so any filter mismatches).

| Kind | Key | `of` | Host read; listing cursor |
| --- | --- | --- | --- |
| `receipt` | slug or entry CID | entry's `hash`, or carried pointer's `cid` | `world-resolve` or `world-entry`; `world-entries`, opaque host cursor |
| `object` | `<id, / as ~>.<version>` | `stateCid` | `world-object`; `world-objects` then `world-object`, object-id cursor |
| `source` | module CID | module CID | `world-source`; `world-sources`, opaque host cursor |
| `publication` | publication id | retaining entry's hash | look up in `world-publications`; opaque host cursor |
| `grant` | grant id | installing entry's hash | look up in `world-grants`; opaque host cursor |
| `law` | `<id, / as ~>.<clause>` | absent | clause in `world-object.laws`; object-id cursor or `<id>#<n>` within its clauses |
| `card` | object id, `/` as `~` | absent | public `mirror.card_record`; object-id cursor |
| `page` | page name | absent | public `mirror.library_pages`; shelf-order key cursor |
| `index` | `self` | absent | public `mirror.index_record`; one value |
| `answer` | `<did>.<rkey>` or `xrpc.<iss>.<intent hash>` | absent | bridge answer files; key-order cursor |

Host-paged and live public kinds support `reverse`; objects and laws reject it because `world-objects` lists ids in ascending
byte order. A receipt's `signed`, on a signing box when its entry is in the current tree, is
`at://<did>/online.fg-goose.gsb.entry/<rev>`: the record whose `entry` link names `of`. A receipt retained
from before a carry can still resolve without a record in the current tree. Its `value` is the host's
`{status: "resolved", kind: "receipt", slug, cid, carried: {at, height, world}, message}` reply, declared as
`getProjection#carriedReceipt` with its position in `#carriedPosition`; `of` is its `cid` and `signed` is absent.
Ordinary receipt values remain `#receipt`, with required `height` and `hash`.

Read authority is the host's: no credential reads as `anonymous` (PUBLIC); `Authorization: Bearer <credential>`
from `/AGENTS.md/challenge` and `verify` reads as that DID; a bad bearer is 401. Anonymous reads are limited
per client address (32 a minute). Publication/grant lookup pages the same host listing under that principal,
so fetching by id reveals no more than listing. A private object and its law remain private.

Keys use `[A-Za-z0-9._~:-]{1,512}`, excluding `.` and `..`. Object ids use `[A-Za-z0-9._:/-]`; encode `/` as
`~`, then append a dot and version or clause (`garden~bell~1.2`, `garden~bell~1.owner`). Decode by the last
dot and `~` to `/`. Replayed ids outside the host's creation alphabet may have no key in this syntax.

Host statuses become XRPC errors carrying the reply: `unknown` → 400 `RecordNotFound`, `denied` → 403
`Denied`, `ambiguous` → 400 `AmbiguousSlug`; unavailable/mute host → 503 `HostUnavailable`/504 `HostTimeout`;
other failures → 400 `InvalidRequest`. The front adds 401 `AuthRequired` (getEntry or a procedure without a token),
401 `InvalidToken` (bad credential or service JWT) and 429 `RateLimitExceeded`
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
of the returned JSON. Live card/page/index/answer queries return no at-uri or signed membership. StrongRefs to
those values must name an actual posting-account record until they join the world's signed MST.

## Not served

- **Writes.** No `createRecord`, `putRecord`, `deleteRecord`, `applyWrites`, `uploadBlob`: the journal is
  written by turns at the host, never through this repository. Unknown methods are 501
  `MethodNotImplemented`; POST on a query and GET on a procedure answer 405 `InvalidRequest`. The three world procedures above use POST; repository writes remain unserved.
- **`getBlocks`, `getBlob`, `getRepo` of another DID.** One repository, no blobs.
- **Checkpoints and pending sends.** `blocks[].cid`, `activity.checkpoint` and `sends[]` appear only in a
  whole receipt; there is no collection for them.

Whole entry bytes outside a signed proof are served by `online.fg-goose.gsb.getEntry` under service auth, including
on an unsigned box. Only this query accepts service JWTs: three dot-separated base64url segments select the
verifier; other strings use the credential path, which still serves existing record and projection reads.
The host's `world-entry {principal: iss, hash, bytes: true}` decides access; absent bytes on an existing entry
answer `Denied` without carrying its projection. `#delvetalk` lets a PDS resolve
`atproto-proxy: did:web:<world host>#delvetalk` to this origin.
Inside an entry, CIDs are strings as the journal stores them; its block has no `$type`. Changing them to
links would change the entry bytes and every CID. The signed entry record carries the real link.

## Hosted public request accounts

`transport/hosted.py` mounts hosted guest and Zulip accounts through the existing front and listener. The mapping
(`guest:<host>:<name>` ↔ `did:web:<name>.guest.<host>`, `zulip:<realm>:<id>` ↔ `did:web:<id>.<realm>.zulip.<host>`),
enabling (`hosted_accounts`, off by default for want of wildcard DNS), provisioning and key derivation are ATPROTO §4.
This section is the repositories themselves. External claimed DIDs keep their own repositories.

Each hosted hostname serves its own did.json: `alsoKnownAs` is its `at://<hostname>`, `#atproto` is
its derived k256 key and `#atproto_pds` names the same front origin. Host selection never creates
accounts. At that origin, repo/sync parameters select the existing account by DID/handle; an account
Host cannot select another account. Hosted hosts expose only repository methods, not world procedures
or projection queries. Describe/list/get return only `online.fg-goose.gsb.request`, with value-derived
CIDs. Sync.getRecord returns the current commit, MST path and value; getRepo returns the whole current
tree (also for `since`), including its empty root after deleting the last record. Full exports
contain every node needed to prove absence; sync.getRecord for an absent key is RecordNotFound.
Host-selected listRepos reports that one account. Empty accounts have a signed empty tree. Unsupported methods are 501; the journal repository refuses writes with 405.

Create/put/delete use the invitation credential and require exactly the stored principal mapping to
that DID. The shared lexicon validator and shared call framing validate every write; validation cannot
be disabled. Keys are TIDs, generated on create when absent. Puts replace or create; deletes remove;
duplicate create is RecordAlreadyExists. Optional swapCommit/swapRecord compare current CIDs before
changing anything and refuse InvalidSwap. At 256 records, RepoFull refuses a new key while preserving
all existing requests; replacement is allowed and deletion makes room. A record is at most 65,536
DAG-CBOR bytes. Repository write bodies allow 397,312 JSON bytes for worst-case escaping and framing;
agent/procedure body limits remain 256 KiB. The catalogue exposes both limits. listRecords bounds
pages at 4 MiB of JSON, returning a cursor when the byte budget shortens a page. This includes adversarial control-character escaping. CAR exports are bounded at 17 MiB.

Hosted accounts are origin-wide: every world's front uses the same town key and snapshot store, so
Host- and parameter-selected account reads return identical documents and repository bytes.
`State.hosted` is `<state>/hosted/<URL-encoded origin>/`, directory mode 0700. Stems are `<guest name>` and
`<id>.<realm>.zulip`. The k256 key derives from the town private scalar and account DID using HKDF-SHA256
(ATPROTO §4); no account key or lock file is written. A public `.json` snapshot holds
`{principal, counter, prev, records, key}` and optional `epochs: [{counter, cause, key}]`;
one flock on the directory file descriptor serializes front/bridge reads and writes. A write
rebuilds the sorted bounded MST with the existing Tree/Key.commit, fsyncs the snapshot, atomically replaces
it and fsyncs the directory. Readers see one complete snapshot. Revs are `TID(counter)`, counter advanced
to `max(counter + 1, wall microseconds)` for each mutation, even if the wall clock moves backward. The
commit signs version 3, this account's DID, its current root, rev and previous head CID. The counter and
prev are kept beside the records, so restart yields byte-identical head CARs without writing. There is
no historical export or hosted firehose; consumers reconcile the bounded full current tree.

State backups keep hosted snapshots; the same town key reproduces account keys and signed heads on restore.
With hosting enabled, the first access atomically moves an existing `<state>/worlds/town/hosted/` directory into the origin store,
preserving snapshot bytes. If both stores exist, access refuses with 503 `RepoNotServed` and names the paths
for operator reconciliation. A non-town front with nonempty legacy `<state>/worlds/<world>/hosted/` likewise
refuses startup and hosted access: those snapshots are preserved, never merged or re-signed under the town DID.
Startup and account access reconcile changed keys under the directory lock: a higher counter, `prev` null,
the new `key`, and a `rotation` epoch, with the same records and rkeys. Legacy snapshots instead record
`migration`, unless their legacy key already equals the derived key (only `key` is added); legacy key/lock
files are deleted after the snapshot is durable. A second reconciliation changes no bytes. Missing town
keys refuse hosted routes and provisioning with 503 `RepoNotServed`; an invitation acceptance then leaves its code
open, and a Zulip observation rolls back for retry. DelveTalk's custody vouches no more than the invitation: addressability,
not trust. The local poller source supplies the same proof CAR bytes to `requests.proven`, with no network
and no alternate verifier. Each URI turns once under its hosted DID and yields the ordinary answer.
The poller and mirror are off by default. Tests: `test_hosted`; signing needs cryptography >=43.

## Authenticated scratch responses

Scratch worlds have no repository, DID, signing key, mirror records or firehose. The front serves
`online.fg-goose.gsb.openSession`, `.getSession` and `.listSessionRecords` under method-bound service auth
(ATPROTO §3). The issuer is the holder: `scratch/<name>` resolves in the host to that issuer's scratch.
`listSessionRecords` returns `{records: [{key, cid, value}], cursor?}` for card and entry values; each CID
hashes its response value and proves no signed membership. Card keys use `/` → `~`; entry keys are decimal
heights and entry values are `{ $type: online.fg-goose.gsb.entry, entry: {$link: hash}, height }`. Cards use the
shared renderer without paint, including REPL objects that have cards; REPL checkpoints have no collection.
The responses are not persisted. Scratch act/try/plan run the ordinary host turn path, without town drafting
or public answer lookup/write. Unknown and expired scratches return the same `RecordNotFound` bytes.
Expiry is the host's idle home-clock deadline; opening a discarded name creates a new scratch. Existing
`make`, citation and shelving exits are durable-world acts, retaining only what they carry. Proxied calls
are visible to the caller's PDS; direct service-auth calls avoid that proxy. Named readers and separate
permissions are designed, not built (ATPROTO §3).

## Host ops this calls

`world-resolve` and `world-objects`, and these. In every op `principal` is the reader; `anonymous` is the public
reader in every host read op.

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
are `zulip:<realm host>:<numeric id>` (no `@`), and `/` written `~` is then a key for every id, read back without
ambiguity since no id holds `~`.
