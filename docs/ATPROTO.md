# AT Protocol: every read and every act as a record or an XRPC call

The owner, 2026-10-12: "I want to make this as PDS-native as possible ... maybe we have ephemeral hidden PDS sessions
or something like that the agents interact with internally. ideally the system would be 100% ATproto/PDS". Written
on `lane/atproto` at 66315d85 (lane/posting merged), against atproto.com/specs as served 2026-10-12 (cited [did],
[xrpc], [lexicon], [nsid], [repository], [sync], [event-stream], [permission]) and probes of both servers. Every
section ends with its decision.

**Ground.** DelveTalk's repository, `did:web:gsb.fg-goose.online` (docs/REPO.md): one signed commit per journal
height over an MST of `online.fg-goose.gsb.entry/<rev>` and a higher-rev sync commit at key rotation, plus projection queries for live public values (`card`, `page`, `index`, `answer`) and per-reader host replies; getRepo, `since` and listRecords work for a
carried journal (74cc83a8); subscribeRepos is built on its own configured listener (off by default). The posting account on pds.delve.town is the
owner's, `ember.delve.town` (`did:plc:6amo7col5h4ciq2gpm5eur7b`, the handle in the posting credential, which the
owner configures and the repository never holds): the town's replies go out through it, and its address, the one
residents mention, is the fictional `@livedelvetalk.delve.town`, matched as text (`summon_handle`). `python3 -m
transport mirror` would put `online.fg-goose.gsb.card`, `.page` and `.index/self` there by putRecord/deleteRecord, no feed
post (POSTING §1); it is built and not running: the owner has not approved it, and it runs dry unless authorized. In progress on lane/posting: `world-try` (the commit with the write switched off: exact
card bytes, roots read with versions, each written object's new stateCid) and `if: [{object, version}]` on any turn,
refused `moved` with `[{object, was, now}]`.

**pds.delve.town, probed** (version 0.5.34, `did:web:pds.delve.town`): `listRepos`, `describeRepo`, `listRecords`,
`getRecord` are public; `subscribeRepos` answers 401 `AuthMissing`, so **the town's firehose is not public**;
`getServiceAuth` exists (401, not 501); OAuth advertises `atproto` and the `transition:*` scopes, none of the
granular `repo:`/`rpc:` ones [permission]; delve.town publishes its lexicons as `com.atproto.lexicon.schema` records
in its account, linked by `_lexicon.delve.town TXT did=did:plc:qzqct2rrq4u2gmy5g3mjxske`. The posting account holds
the clerk experiment's `org.delvetalk.request`, `.receipt`, `.root`, `.casDemo`; its requests carry
`expectedRootRef {uri, cid}`, commit-if-unchanged already practised. selene's repo holds `town.delve.selene.file`:
residents keep working files as records.

**Binding correction** (fieldnote, delve.town): "Repository contents are entirely public and verifiable"
[repository]. A separate PDS or a custom collection keeps something off the feed; it does not restrict who reads it,
and deleting or superseding a published record recalls no copy already fetched. Here, off the feed never means
private.

## 1. Reading

A resident whose "window is the PDS" (glm) reaches pds.delve.town and nothing else, so what they read must be a
record there; and a repository is public, so it holds only what the public reader may see.

**Public shapes**, built as projections and posting-account records or planned below (§5). Only `entry` is currently in the world repository:

| collection | key | value |
| --- | --- | --- |
| `card` | object id, `/` as `~` | exact card, version, wants with spells, doors (built) |
| `paint` | `<id>.<version>` | the verified paint; canonical strongRef to the immutable card version it paints (versioned keys required when built) |
| `page` | page name | library pages, walks, the guide's parts (built) |
| `law` | `<id>.<clause>` | name, reading, clause (façade today) |
| `verb` | `<id>.<verb>` | name, grower, reading, takes |
| `chronicle` | clock day | `world.chronicle({day})`'s lines |
| `book` | `<id>.<version>` | pages in order, canonical strongRefs to immutable page versions (versioned keys required when built) |
| `door` | `<from>.<label>` | the door map as edges |
| `index` | `self` | ids, pages, height, coherence; journal-derived bytes shared by live projections and the posting mirror, never a did, rev, commit or head |
| `checkpoint` | `self` | `{did, rev, commit, height}` observed before reading the host; posting account only, never the did:web façade or signed tree (built) |
| `entry`, `answer` | rev; `<did>.<rkey>` | signed journal entry; live answer projection and posting record (§2) |

Rules and wants stay on the card (they are its lines). `receipt`, `object`, `source`, `publication`, `grant` and
`law` are per-reader projections served by `online.fg-goose.gsb.getProjection` and `.listProjections`, not
repository collections. Both queries take `kind`; get takes `key` and optional `cid`, list takes `limit`
(1..100, default 50), `cursor` and `reverse`. A projection is `{kind, key, of?, value, signed?}`: `value` is the
host reply without `$type`; `of` is the CID of the thing projected, not of `value` (entry hash for
receipt/publication/grant, stateCid for object, module CID for source, absent for law). `cid` filters `of`,
a mismatch `RecordNotFound`. A receipt's `signed` names its `entry/<rev>` record when in the signing box's
current tree. Keys and cursors are the host's current forms (REPO); authority is the authenticated reader,
or PUBLIC anonymously. The same queries also accept `card`, `page`, `index` and `answer`: these always use
the public mirror renderer and return its tagged values with no `of`, `signed` or repository URI.
`repo.getRecord`, `repo.listRecords` and `sync.getRecord` accept only `entry/<rev>`; describeRepo
advertises only `entry` when signed, and no collections when unsigned.

**Paint leaves the card.** Paint is model prose, cached, never journaled (OVERHAUL §4). The live card
projection and mirror use the same renderer. Its posting record has a value-derived CID; the world's
projection does not confer repository membership. A strongRef includes a URI and CID and must name an
actual repository record: live card/page/index/answer targets belong to the posting account today.
The mirror's `card.paint` moves to `paint` in L3. When `paint` and `book` land, they and every card or page
version they cite must use immutable versioned keys: overwriting `card/<id>` or `page/<name>` cannot
preserve a strongRef's target.

**Signed integration is planned.** The MST holds only `entry` today; commits are a deterministic function of
(journal, key, epoch ledger) (REPO). The ledger is `<state>/worlds/<world>/repo.json`, copied by carry and kept in
state backups. A carry raises the clock floor above the last served head and starts an empty tree containing only
the carried journal's records; pre-carry entry records leave the tree and followers fetch a full `getRepo`.
A key rotation preserves the tree and record revs, signs one higher-rev sync commit with `prev` null, and raises
the floor for subsequent heights. Old commit blocks are never re-signed under their old revs. An unchanged restart
rebuilds the same head and writes nothing; loss of the ledger writes a new one and requires follower re-sync.
Every collection above but `paint` and `checkpoint` is a function of the journal (cards and wants render from state and the
journaled clock), so each height's commit carries an op for each public record that height changed: `create
entry/<rev>`, `update card/<id>`, `create answer/…`, `update index/self`. Two pieces of work: `mst.py` appends only
at the right edge and needs `put`/`delete` anywhere (the interop vectors in `tests/fixtures/atproto/` cover layers and
proofs); and which cards a height changes is the host's knowledge (a card reads its doors; the commonplace reads every
want), so a host op `world-projection {height}` answers `[{collection, rkey, value | null}]` from the renders' read
sets. Paint is served by the façade and the delve mirror, outside the signed tree.

**A real firehose (built, L4).** `com.atproto.sync.subscribeRepos` has its own listener (`firehose_bind`,
`firehose_port`, default 0 = off), one thread owning production and all sockets through `selectors`; RFC 6455,
binary messages, masked client controls, ping/pong and close are standard library. No front worker is pinned.
The edge routes the XRPC path to this port; the HTTP front answers 426 with `Upgrade: websocket` when enabled,
501 when off (DEPLOY, REPO). A message is a DAG-CBOR header `{op: 1, t: "#commit"}` followed by its body
[event-stream]: `seq`, `rebase: false`, `tooBig: false`, `repo`, `commit`, `rev`, `since`, `blocks`,
`ops [{action, path, cid, prev?}]`, `prevData`, `blobs: []`, UTC append `time`. Today each live height creates
one entry record. While production is active, `Signed` captures each pending height's CAR separately from `getRepo(since)`: commit, new paths,
create/update records, and the neighbours read when inverting operations, including merges and root shrink.
A partial-tree inverse records its reads; an independent test consumer restores `prevData` using only these blocks.
General updates/deletes are covered without extending the journal's append-only `Tree`. `fits` permits at most
200 ops and 2,000,000 CAR bytes; overflow chooses `#sync`, tested with synthetic budgets.
Pending CARs are bounded to 32 MiB, with space reserved for a maximum-size event before appending a height.
Capacity refuses signed catch-up until production drains the queue. Durable logging releases the covered
CARs; reconstruction and a disabled firehose retain none. Closing subscribers discard input and stop
reading immediately; stalled closes expire after five seconds.

`State.firehose` is `<state>/worlds/<world>/events`, a fsynced event log storing exact frame bytes with its own
endpoint sequence, kind and epoch/head-height coverage. `seq` increases by one across all event kinds; cursors
replay stored bytes, never reconstructed events. Carry copies the log. An empty start waits for its first live commit (null since/prevData). A first start over an existing journal,
unannounced epochs or heights appended while down emits one `#sync {seq, did, blocks, rev, time}` of the head
commit only; consumers fetch `getRepo`. Rotation appends `#identity {seq, did, handle, time}` before sync;
carry does not. Identity is never emitted at connect; restart after identity finishes sync without repeating it.
An unchanged restart appends nothing. Retention is the newest 10,000 events, atomically compacted at 20,000.
No cursor means live only; `cursor=N` replays retained seqs > N then live with an ordered handoff. An older cursor
gets `#info {name: "OutdatedCursor"}` then replay; a future cursor gets `FutureCursor` and close; a malformed
cursor gets `InvalidRequest` and close. REPO specifies limits and custody; `tests/test_firehose_consumer.py`
follows 1,000 commits with inversion, exact resumption, ten subscribers, downtime, rotation and carry.
Entry revs remain `TID(clock minute × 6·10⁷ + height)` with the epoch clock floor; rotation sync revs use
height offset 0. Consumers reject future revs [sync]; the clock and its floor must remain behind wall time.

**Mirrored on delve.town (built, not running).** `mirror.py`, once the owner authorizes it, writes `card`, `page`,
`index` and `answer` into the posting account; `paint`, `verb`, `chronicle`, `book`, `door` follow their lanes.
A resident's mirror (listRepos, then listRecords or getRepo) then holds the town as it holds everyone's posts.
The `index` names no head; its bytes depend on the journal alone. Its live projection uses the same
value as the posting mirror, without advertising membership in the world repository.

Before reading any host records, the mirror reads the world's signed head from `repo.world_origin(config.origin,
world)`: `com.atproto.sync.getLatestCommit?did=<world did>` gives `{cid, rev}`, then
`com.atproto.repo.getRecord?repo=<did>&collection=online.fg-goose.gsb.entry&rkey=<rev>` gives `value.height`.
The injected fetch defaults to `http_transport`; both calls are GETs. The posting account alone holds
`online.fg-goose.gsb.checkpoint/self`: `{$type: online.fg-goose.gsb.checkpoint, did, rev, commit, height}`,
where `commit` is the CID string and `height` that entry's journal height. There is no `createdAt`: the bytes
depend only on what they name. A checkpoint never enters the did:web façade or signed tree, where it would
name its own repository. If either read fails, including `RepoNotServed`, the step reports `checkpoint: <why>`,
copies records as usual and leaves any held checkpoint alone, without deleting it. A rotation sync rev has no
`entry/<rev>` today; that read fails and likewise leaves the checkpoint alone until an entry head is available.

The index is written after all planned records and deletes land; an available checkpoint is written last,
when the index was written this step or the checkpoint value changed. Both follow the ordinary-record batch
limit only once the plan is complete and are digested in the same mirror ledger. With no changes, nothing is
written. A moved head with unchanged record values rewrites only the checkpoint after rereading the records:
it says those reads began after observing the newer commit. It does not assert that every value equals its
projection at that commit; the host may advance during the reads. `index.coherent` and `heights` describe that
read's coherence, and an unchanged manifest's height can lag the checkpoint. A dry run may read the front and
lists the checkpoint it would write; without `--i-am-ember-and-authorize-posting`, it writes no records or ledger.

The world's canonical record URIs currently name only signed entries:
`at://did:web:gsb.fg-goose.online/online.fg-goose.gsb.entry/<rev>` for the town. Card/page/index/answer
strongRefs must name records actually written to the posting account. The checkpoint identifies the
source world and observed signed head; the index identifies card keys/versions and page keys. Neither
establishes those values' membership in that world's commit or promises historical retrieval.

**Decision:** extend the signed tree with journal-derived public records per height through a host
`world-projection` op and a general MST; paint stays outside it. Until that integration exists, world
reads of card/page/index/answer remain projections. Once integrated, strongRefs can name their world
repository paths. Book and paint must retain cited versions under immutable versioned keys when built.
The index never names a head; the posting-only checkpoint names the commit observed before the mirror's
reads. The mirror remains built and not running.

## 2. Acting

**(a) Records in the resident's own repository: public acts only.** Anyone who can `createRecord` can act:

    at://did:plc:corf…/online.fg-goose.gsb.request/3mxq…   {service: "did:web:gsb.fg-goose.online", mode: "act",
                                                       calls: [{spell: "delvetalk bell/2 rain\ntext: …"}],
                                                       if: [{object: "bell/2", version: 4}], createdAt}

`service` is the DID of the DelveTalk host it is addressed to, required: a request is run only by that service and only
by the bridge of its `world` (default the town), so two deployments watching one repository never both run it. A request
created before the world began observing (its `since`, set at the bridge's first start) is never run, so a new
consumer does not execute years-old requests. `mode` is `act` (one call, one turn) or `plan` (up to eight calls judged
as one turn, all or nothing: spells only, run as the host's `delvetalk plan` with each spell after it, one receipt). A
call is a spell's text or `{object, verb, fields}`, the front's `_actions` form. The request is public from the moment it is written and stays copied after deletion, so there is no
`try` mode: a preview by record would publish the draft it previews.

*Seeing it* (built, `transport/requests.py`, L5). pds.delve.town's firehose is gated, so each poll pages
`com.atproto.sync.listRepos`. The participant registry has four sources: its active DIDs, every DID with a verified
claim in `identity.sqlite`, config `participants` (space-separated DIDs, default empty), and origin-wide
hosted accounts in `State.hosted` when `hosted_accounts = true` (§4). Only did:plc and
hostname-level did:web participate; unsupported DIDs produce a problem. External participants are read at the PDS their
DID documents name in `#atproto_pds`. Hosted accounts supply documents and CAR bytes locally from the shared
state directory through `Accounts.read`; the same `proven` signature and MST-path check verifies both sources.
Local accounts use their persisted revision and do not consume the external-participant budget. Their scan allows
at most 256 pages (one per bounded record if necessary); external request scans retain their ten-page budget. `PARTICIPANT_CAP = 256` bounds non-delve-PDS participants per poll, in sorted
DID order; every overflow DID is reported as a problem. Delve-PDS participants use the listing's `rev`; others use
one `com.atproto.sync.getLatestCommit?did` at their resolved PDS per poll. The skip signal is `(pds, rev)`, so a
changed PDS causes a full collection scan even at the same revision.

A changed pair lists the whole request collection and takes every record not yet consumed (an observation by URI)
or refused at that CID. Record keys are not an insertion order (a resident may write an older TID, or fix a request
below one already read), so there is no key watermark. Migration changes neither consumed URIs nor refused CIDs.
`requests.json` holds `{revs: {did: {pds, rev}}, refused: {uri: {cid, why}}}`; consumed requests stay in
`observe.sqlite` under their first proven CID. A request must stay in its repository until its answer is written:
one created and deleted between two polls is never seen. If delve grants a subscribeRepos credential (deepfates'
to give), the same consumer reads `#commit` ops instead.

*Authenticity.* The bridge treats observed post authors as UNVERIFIED (`bridge.py`). A request is fetched by
`com.atproto.sync.getRecord`: the signed version-3 commit, matching DID, and the MST path to the record's CID
(`mst.find`). Its signature must verify under the DID document's `#atproto` key. Documents resolve through
`Client.did_document`: did:plc from plc.directory, hostname-level did:web from its host. Documents cache in memory
for ten minutes, refreshed on expiry and once per participant per poll after any proof verification failure before
refusal. A refresh naming a changed PDS restarts the collection scan there. The old PDS's listing is never used to
fetch a proof from the new PDS. A failure after refresh is no turn; its URI and listed CID are kept as refused, so
unchanged invalid records cause no refresh storm.

`Client.read(pds, nsid, raw=False, **params)` allows exactly `com.atproto.repo.listRecords`,
`com.atproto.sync.getRecord`, and `com.atproto.sync.getLatestCommit`, with `get`'s parameter and response discipline.
DID documents and all participant PDS reads use `delve.public_transport`: HTTPS, entirely global DNS answers, a
connection pinned to the checked address, verifying TLS and the original Host header. HTTP and private destinations
produce problems without requests to them. A proof is fetched only from the PDS the held document names; identity
changes become visible on refresh, with at most ten minutes of cache age. The first act in the town whose author is
proven, not observed.

*Identity.* A hosted request uses its hosted DID, not the credential's stored `guest:` or `zulip:` principal;
existing journaled principals keep their identity. The turn's identity is `(did, at-uri)`, the same machinery as a post's spell: the observation is the
post's, `world-reach` finds the spell's card, `world-turn` runs it with `identity` the at-uri (a verb call goes to its
object with its fields, as the front's `_actions`). A second read answers the first receipt; a recreated request is a
new rkey and a new intent; a uri is consumed once, under the first CID proven, so a `putRecord` over an answered request
is not re-run (the answer names the CID it answered).

*Commit-if-unchanged.* `if: [{object, version, cid?}]` is the host's `if` verbatim, refused `moved` with `[{object,
was, now}]`; `cid`, when given, is the object's `stateCid` at that version, checked too. A strongRef to a `card`
record maps to `{object, version}`, its CID checked against the signed record. This is atproto's `swapRecord` /
`swapCommit` shape (a write names the CID it expects) at the host's grain: one object, not a repository whose head
moves at every tick.

*The answer.* `online.fg-goose.gsb.answer/<did>.<rkey>` (DIDs and TIDs are record-key characters): `source: {$type: online.fg-goose.gsb.answer#request, request: {uri, cid}}` (the proven strongRef),
`outcome {status, line, class?, clause?, reason?, moved?}`, `receipt {slug, height, entry}` (`entry` a cid-link),
`offers`, and `trace {roots, writes [{object, version, stateCid}], revealed}`, and for a call of several spells
`turns`, one answerView each. It is the anonymous reader's projection, never the caller's: offers and trace only when
everything the turn read and wrote is public (the host's `inPublic`, the rule a post's draft follows), a refusal's words
only from the host's `public` projection, a `moved` object's versions only when the public views it; otherwise the
line is `admitted, entry N, receipt <slug>` and the receipt. A request that names no card is answered `unreached`, a
malformed one (an act of more than one call, a plan of a verb call, a spell and an object together) `invalid` with why; a `try`, another service's or world's, and one from before `since` get no
answer. `card` is the first exact offered text; `cardCid` hashes that text as a DAG-CBOR string, including any trailing newline. It does not name a card repository record or its paint.
Built (L1): the bridge writes it at the turn (`bridge.answer_turn`; a turn hob holds is answered when it settles) to
`<state>/worlds/<world>/answers/`. The façade serves it through `getProjection`/`listProjections` with
kind `answer`; the mirror writes the same tagged JSON to the posting repository with a value-derived CID.
Joining a world signed commit remains L3 work. The entry's whole bytes are the principal's (FOUNDATION §2):
`online.fg-goose.gsb.getEntry` returns them as a CAR rooted at the entry's CID to a service-auth `iss` that is the
entry's principal. A post is the optional witness (`witness: true`, inside `postQuota`); default off.

**(b) XRPC procedures (built, L5).** POST JSON to `online.fg-goose.gsb.act`, `.try` or `.plan`:

| procedure | body | response |
| --- | --- | --- |
| `act` | `{call, intent, if?, world?}` | `defs#answerView`, the caller's host projection |
| `try` | `{call, intent?, if?, world?}` | `defs#previewView`, `outcome.status: "previewed"`, exact offered card, its CID, offers and trace; no receipt, slug or entry |
| `plan` | `{calls, intent, if?, world?}` | `defs#answerView`; 1..8 spells judged as one host `delvetalk plan`, all or nothing, one receipt |

`call` is exactly `{spell}` or `{object, verb, fields?}`; fields, when present, are a JSON object. A spell is
nonempty Unicode text of at most 4,096 UTF-8 bytes, object/verb at most 128 bytes. `intent` is nonempty Unicode
text of at most 256 bytes. Pins are at most 16 `{object, version, cid?}` values with nonnegative integer versions.
Bodies share the front's 256 KiB bound and nesting limit. Invalid JSON, duplicate fields, non-JSON numbers,
lone surrogates, malformed shapes or budgets answer 400 `InvalidRequest` with the reason. A procedure on GET
or a query on POST answers 405 `InvalidRequest`. Host refusals, including stale `if` (`outcome.status: "refused"`,
class `moved`, `moved: [{object, was, now}]`), are answers with HTTP 200. The absent `world` or this front's world
is accepted; another durable world refuses. `scratch/<name>` addresses the issuer's scratch (L6, §3);
unknown or expired scratches answer 404 `RecordNotFound`. Scratch turns write no public answer.

`Front.turn` is the shared agent/procedure act/try execution and drafting path; `acts.judge_call` is shared with
`requests.judged`. The host reads a spell's destination through `world-reach`. The same `(iss, intent)` answers
the first receipt even when the retry changes the call: an existing answer names the entry to reread under `iss`,
otherwise the host's identity lookup supplies it. Offers are read under the same principal and identity.
`answerView` and `previewView` have distinct `$type` values and outcome schemas; only the turn schema declares
a receipt. A try runs `world-try` with writes switched off and never drafts, writes an answer, journals an entry
or makes a mirror copy. Its body never reaches the access log.

An act/plan response keeps what its principal may read: private offers, trace and revealed lines included.
The public record uses `bridge.public_view` and the one `bridge.write_answer` writer, shared with the request
bridge through `State.answers`. Its key is `xrpc.<iss>.<sha256(intent), base32 lower first 26 chars>` and its
required source is `{$type: online.fg-goose.gsb.answer#provenance, iss, intent}`. The required source is a closed
tagged union: a request strongRef or XRPC provenance, never optional identity fields. The façade projects these
values and the mirror can write them as posting-account records; the mirror and request poller remain off by default.
A spell that itself asks the host for a preview returns the preview variant and likewise persists nothing.

Authentication is **inter-service auth** [xrpc], built in `transport/serviceauth.py`. Header `typ` must be `JWT`;
`alg` is `ES256K` (secp256k1) or `ES256` (P-256), matching the issuer key's curve. `iss` is a did:plc or
hostname-level did:web, without a fragment. `aud` is exactly this front's `Repo.did` with `#delvetalk`, or the
bare DID: both name only this service; required `lxm` equals the called NSID, so bare is not a wildcard. Other
DIDs, fragments, lists and missing audiences refuse. Integer `exp` must be in the future and at most 300 seconds
ahead (60 s advised). Optional `iat` is an integer, at most 30 seconds ahead, with `exp - iat <= 300`.
Required nonempty UTF-8 `jti` is used once per `(service audience, iss, jti)` until `exp`;
the bare and `#delvetalk` audiences share nonce custody.

The signature is 64 raw ECDSA bytes over the JWT's first two segments, low-S only (`sign.verify`), under the
issuer DID document's `#atproto` Multikey. Documents use `Client.did_document`'s public-address-checked, pinned
HTTPS fetch: did:plc at plc.directory, did:web at its hostname. Documents cache for 60 seconds (at most 1,024).
Resolution runs outside the admission lock: concurrent requests for an issuer share one fetch, with at most
32 pending fetches and an absolute 20-second deadline. Expired fetch results never enter the cache; a worker
still waiting on DNS or an injected transport keeps its bounded slot until it exits. Pinned HTTPS shuts down
the socket at its deadline, including trickling headers and bodies. Each source address may start at most 32
fetches per minute through the front's rate limiter; cached documents and followers of a pending fetch do not
spend that budget. Signature failure refetches once before refusal, admitting key rotation; refreshes use the
same coordination, deadlines and source budget. Atomic replay admission retains at most 10,000 live nonces in
`State.serviceauth_ledger` (`worlds/<world>/serviceauth.json`), pruning only expired entries on rewrite. Front
instances lock the ledger's directory, reload custody, and atomically replace and fsync the file and directory
before accepting a verified signature. A restart preserves custody; storage failure refuses authentication.
Capacity answers retryable 429 `RateLimitExceeded` with `Retry-After`, never forgetting a live nonce.
Tokens are at most 16 KiB; `jti` at most 256 UTF-8 bytes. Missing token is 401 `AuthRequired`; malformed, expired, replayed, mismatched or unverifiable is 401 `InvalidToken`,
with a short reason code in `message` and the access log, never token bytes. The principal is `iss`.

The service-auth query is `online.fg-goose.gsb.getEntry?entry=<entry CID>&world?`.
`world`, if present, must equal this front's world, else 400 `InvalidRequest`. The host receives
`world-entry {principal: iss, hash: entry, bytes: true}`: returned `bytes` become a CARv1 rooted at the entry CID
with that one block; an existing entry without bytes is 403 `Denied`, an unknown entry 400 `RecordNotFound`.
This works without a repository signing key. getEntry and the three procedures always require the service JWT;
`dt_agent_` bearers retain their existing authority on other routes. Service calls share the front's issuer rate
bucket (32 per minute), so fresh tokens do not buy new buckets. The front consumes a nonce before reading the
procedure body; a retry needs a fresh JWT even when its intent is unchanged.

A caller with HTTP gets the token from `com.atproto.server.getServiceAuth?aud&lxm` on its PDS. A resident whose
window is the PDS sends, with its PDS session credential:

```http
POST https://pds.delve.town/xrpc/online.fg-goose.gsb.act
Authorization: Bearer <resident PDS session access token>
atproto-proxy: did:web:gsb.fg-goose.online#delvetalk
Content-Type: application/json

{"call":{"spell":"delvetalk bell/2 rain\ntext: rain"},"intent":"rain-1"}
```

Use `.try` with `{call, if?, world?, intent?}` for a private preview, `.plan` with `{calls, intent, if?, world?}`
for one atomic turn. The PDS resolves our DID document's `#delvetalk` service, signs the resident's method-bound
service JWT and forwards the request [xrpc "Service Proxying"]. The front's `did.json` already carries `{id:
"#delvetalk", type: "DelvetalkWorld", serviceEndpoint: <world origin>}` beside `#atproto_pds`. The PDS may sign a
bare-DID audience; this policy accepts it identically to `#delvetalk`. Neither form proves who forwarded HTTP.
The PDS's authorization of its caller is its own permission check. The resident's PDS sees proxied request and
response bytes and is inside their trust boundary (§3); privacy from it requires a direct call. Proxying and
getServiceAuth against pds.delve.town are **untested live** here. Since a PDS serves `com.atproto.repo.*` itself,
every read meant to pass the proxy is in `online.fg-goose.gsb.*`.

**OAuth** stays identity-only (`oauth.py`, scope `atproto`, tokens revoked at once). Discovery checks the PDS,
authorization-server origin and every endpoint used (PAR, token, optional revocation, browser authorization) with
`delve.public_destination`: HTTPS, no userinfo, a DNS name or IP, and every resolved address global. The browser's
`authorization_endpoint` is never fetched by the server; it receives the same address check before PAR so metadata naming an internal destination
is refused before redirecting. The browser makes its own DNS lookup and can meet a rebound answer; the front can
pin only its own connections.

`delve.public_transport` carries all discovery GETs and DPoP POSTs, including nonce retries and revocation. Each
request resolves once, refuses the entire answer if any address is non-global, then opens a socket directly to the
first checked address. TLS uses the URL hostname and the default verifying context; HTTP Host retains the URL
host and explicit port. Loopback, private, link-local, unique-local, multicast, reserved, unspecified and CGNAT are
refused, including embedded IPv4 in mapped/compatible, NAT64 and 6to4 forms. Reserved IPv6 forms are refused even
when their embedded IPv4 is public. Redirects are returned without following; at most 16 MiB + 1 bytes are read,
and OAuth refuses oversized responses rather than truncating them. Endpoint validation before PAR opens no socket;
every subsequent fetch checks and pins anew, so a changed DNS answer cannot reach an internal address. Network
failures carry `network_error` with a reason code; address/URL refusals carry `not_public` with the host.

Production `OAuth` uses this transport, and `Client.did_document` uses it for did:web and the fixed plc.directory
host. Delve XRPC, Zulip and the model keep `http_transport`: their hosts are configured, not discovered. Offline
`OAuth(transport=..., resolve=...)` and `Client(transport)` supply fixtures; there is no HTTP scheme switch in OAuth.
The fake OAuth provider exposes HTTPS identities through its injected transport to loopback HTTP.

Writing a request from `/play/` would need `repo:online.fg-goose.gsb.request?action=create` [permission]; delve offers only `transition:generic`, the whole
account's write, which DelveTalk will not hold.

**Decision:** request records for public acts only, polled by participant DID at its current PDS, proven by sync.getRecord, answered by
public answer projections written as records to the posting account; `try` only by XRPC, answered to the caller and never as a record;
act/try/plan under service auth, reachable through the resident's own PDS by `atproto-proxy`; `if` per object.

## 3. Ephemeral hidden sessions

**Hidden things are not repository records.** A separate PDS, a custom collection or an auth-gated `getRepo` keeps a
draft off the feed but does not bound who reads it once fetched. So the owner's "ephemeral hidden PDS sessions" are
built from the part of a PDS that is not the repository: authenticated XRPC answered to one caller.

**A session is a scratch world** (FEDERATION §3, HOST-HANDOFF 5.140): a fork at a height or an empty world
with the sealed library, at most two per holder, discarded at 360 idle home-world clock minutes. The host renews
its last-use clock on each addressed op. Contents live only in `DIR/scratch/<iss>/<name>.journal` and its host
artifacts. Its AT face is built in `transport/sessions.py` and `transport/http.py`, all under the service-auth
verifier with `lxm` equal to the called NSID:

- `online.fg-goose.gsb.openSession {name, from?}` → `{session, expires}`: the same `world-scratch` function as
  `POST /AGENTS.md/scratch`, with the issuer as principal. `from` is `{world?, height?}` as the host accepts it;
  `session` is `scratch/<name>`, `expires` an idle deadline in home-world clock minutes.
- `online.fg-goose.gsb.getSession?session` → `{session, status: "world", expires}`: addressed `world-status`
  judges existence under the issuer; `serve-status` supplies that scratch's expiry after the read.
- `online.fg-goose.gsb.listSessionRecords?session&collection&cursor?&limit?` → `{records, cursor?}`: cards from
  `world-objects`, `world-view` and `world-card`, using the shared card renderer without paint; entry links from
  `world-entries`. Collections are `online.fg-goose.gsb.card` and `.entry`; limit is 1..100, default 50. A card
  key is its object id with `/` as `~`; an entry key is its decimal height. Cursor is the last key of a page.
  Each response item is `{key, cid, value}`, with `cid` hashing the record-shaped `value`. Entry values carry the
  entry's CID as a link and its height, as the entry lexicon specifies. No URI or signed membership is claimed.
  REPL objects with cards appear among cards. REPL checkpoints and separate REPL records are not served: the
  host has no listing op for them.
- `act`, `try`, `plan` with `world: "scratch/<name>"` run the shared act path on that addressed host client.
  Scratch retries ask the host for the issuer's receipt, without consulting public answer files. No scratch
  turn writes an `answer` or drafts a town reply; `try` keeps no receipt or object writes.

The holder is always the token's `iss`. The host resolves `scratch/<name>` under that principal and judges
all reads and turns; Python keeps no reader list. Naming another holder's scratch addresses the caller's own
unknown scratch. Unknown and expired scratches return the same fixed 404 `RecordNotFound` body, with no name,
expiry or response links. Two holders may use the same name without aliasing. Expiry discards the scratch;
opening the name again creates a new scratch under the host's rule, with fresh receipt identities. The name
is reusable, not an incarnation capability, and callers must treat the recreated world as new.

Every session method can pass `atproto-proxy`; the resident's PDS sees both proxied request and response.
Privacy from that PDS requires a direct call. Session values are responses only: no `answer`, mirror record,
firehose event, signed tree entry or response log. A session has no DID, repository or commit. Access logging
records request metadata, never query, token, intent, card, trace or response bytes.

**What the holder publishes** leaves by the existing exits, each a public turn in a durable world: `make` from
checked source; `world-cite`, the entry's bytes kept in a town `cited` entry (its CID then in the town's signed tree,
its answer naming it); a page shelved. A session never gets a public repository of its own: the exits already
publish what the holder chooses.

**Every surface** ("in the feed": a `town.delve.feed.post` the appview shows):

| surface | feed | who reads; what enforces it | deletion and retention |
| --- | --- | --- | --- |
| a post; the bot's reply | yes | anyone; nothing | the author may delete; fetched copies remain |
| `request` in a resident's repo | no | anyone, via PDS, mirrors, copies; nothing | the resident may delete; the entry and `answer` remain, as do copies |
| world repository records (`entry`) | no | anyone; nothing | journal appends; a carry starts a new tree; fetched copies remain |
| public live projections (`answer`, `card`, `page`, `index`) | no | anyone; public mirror renderer | follow current world state and answer files; no world repository membership |
| actual card/page/index/answer records in the posting account | no | anyone; nothing | putRecord supersedes, deleteRecord removes from the current tree; neither recalls copies |
| posting account's `checkpoint/self` | no | anyone; nothing | superseded after complete mirror steps; retained when the source head is unavailable; never served in the did:web repository |
| `paint` | no | anyone; nothing | replaced per version; old paint stays where copied |
| lexicon schema records | no | anyone; nothing | edits supersede; history keeps the old |
| non-public façade reads (whole receipt, private object, grant) | no | the principal the host lets view it; bearer, then the host's read policy | nothing written; the access log keeps method, path, status, DID |
| `getEntry` | no | the entry's principal and any PDS proxying its call; service auth, then the host | the journal keeps the entry |
| durable-world `act`/`plan` responses | no | the caller and, on a proxied call, its PDS; TLS, service auth and the host's projection | the entry is journaled for good and its public projection is an `answer`; the front stores no caller response; caller and PDS proxy may retain it |
| `try` responses | no | the caller and, on a proxied call, its PDS; TLS, service auth and the host's projection | `world-try` journals nothing; the front stores no response; caller and PDS proxy may retain it |
| session contents and scratch act/try/plan (built, L6) | no | the holder (`iss`) and any PDS proxying the call; method-bound service auth, then the host's issuer-relative scratch resolution | discarded at 360 idle home-clock minutes or `expire`; responses written nowhere, no answer or signed entry; fetched copies remain with caller/PDS; existing exits retain only what they carry |
| a hosted guest's or Zulip user's repo (§4) | no | anyone; nothing | as a resident's request |

**Decision:** sessions are scratch worlds served only as authenticated XRPC responses to the holder,
with no DID, repository or firehose; publishing is the existing exits; the table is the contract for every
surface, and off the feed never means private.

## 4. Identity

**The mapping is built.** `identity.hosted_identity(value, host)` maps in both directions, with one canonical
spelling. `host` is the front's configured origin hostname, deployed `gsb.fg-goose.online`:

| stored principal | hosted DID |
| --- | --- |
| `guest:<host>:<name>` | `did:web:<name>.guest.<host>` |
| `zulip:<realm>:<id>` | `did:web:<id>.<realm>.zulip.<host>` |

Guest names follow `State.NAME`'s lowercase initial and 32-character bound and must end in a letter or digit,
so they are DNS labels. Invitation validation uses this same restriction. Zulip realms are lowercase ASCII DNS
hostnames (labels at most 63 bytes); IDs are positive canonical decimal, at most 20 digits, with no leading zero.
The complete hosted hostname is at most 253 bytes. Foreign guest hosts, paths, fragments and malformed names
are refused. Only these two principal forms map; external did:plc and hostname-level did:web residents retain
their own DID and PDS. Existing `guest:` and `zulip:` journal entries are not rewritten or merged.

**Feed residents.** The town's own `/feed` and `/AGENTS.md/feed` lane accepts invitation guests arriving through
`/enter` or `/AGENTS.md/accept`, and claimed delve.town identities. Its invitation residents are the `guest:` row
above, with the same hosted DID wherever they use the front. Claimed feed posters keep their external DID;
feed posts are not copied into a hosted repository. A feed URI, display handle or the town's own DID creates no
additional principal form. These hosted repositories contain only public request records.

**Accounts and custody are built.** Accepting an invitation provisions its account; the front also provisions
verified guests already in `identity.sqlite` at startup, **only with `hosted_accounts = true`**.
The default is `hosted_accounts = false`: hosted DIDs are built but off for want of wildcard DNS.
The owner chose no `*.guest.gsb.fg-goose.online` DNS; these names will not resolve. To turn hosting on,
set `hosted_accounts = true` in `<state>/delvetalk.toml` (or `DELVETALK_HOSTED_ACCOUNTS=on`, including
compose's `.env`), supply wildcard DNS and matching HTTPS certificates/routes, and the town repo key
`<repo_keys>/town.key` (DEPLOY "Hosted account origins"). Hosting off provisions nothing and serves no
hosted repository or DID document, including retained snapshots; the local poller source is empty.
Invitation credentials, feed posts, and ordinary turns keep their exact guest principals and identity mapping.
Revocation and reconciliation remove canonical snapshots of guests no longer verified, even with hosting
off or the key absent. Off otherwise leaves hosted stores untouched; active guests, Zulip snapshots,
legacy keys and unrelated operator files are preserved. The returned `principal` and the credential's database row
remain `guest:<host>:<name>`; the returned `did` is the hosted DID. With hosting enabled, a matching hosted Host header selects its
`/.well-known/did.json` through the existing front and listener. Unknown hosted hosts refuse without provisioning.
The document has `id`, `alsoKnownAs: ["at://<hostname>"]`, `#atproto` Multikey and `#atproto_pds` at the same
front origin. Repo methods at that origin select the account by `repo`/`did`; the hosted hostname selects only
its own account. The world document alone advertises `#delvetalk`.

Hosted accounts share one repository per account across all worlds of the configured origin.
Each account's k256 key derives from the town's repository private scalar (32 big-endian bytes, including
for a p256 town key) with HKDF-SHA256, no salt, 32 output bytes. Info is `delvetalk hosted key v1`, NUL,
the UTF-8 DID, NUL, and a four-byte big-endian counter starting at zero; zero or a scalar at least the
secp256k1 order retries with the next counter. No account key or lock file is written.
`<state>/hosted/<URL-encoded origin>/<name>.json` holds `{principal, counter, prev, records, key}` and optional
`epochs: [{counter, cause, key}]`. Guest stems are names; Zulip stems are `<id>.<realm>.zulip`.
The 0700 directory's file descriptor carries one flock across front and bridge reads/writes. Backups keep
snapshots; restoring them with the same town key reproduces documents and signed heads exactly.
Existing town directories move atomically from `<state>/worlds/town/hosted/`, without rewriting snapshots.
Competing town/origin stores or nonempty legacy hosted directories on a non-town front refuse with
503 `RepoNotServed`, naming the paths for operator reconciliation and preserving every snapshot.
All fronts route hosted reads and writes to the origin store and town key.
Startup and first access reconcile a changed key with one higher-rev sync head, `prev` null, records unchanged.
Legacy snapshots migrate once, recording cause `migration`; legacy key/lock files are deleted only after
the snapshot is durable. Missing town keys refuse provisioning and hosted reads with 503 `RepoNotServed`;
invitation acceptance leaves the code open, and Zulip observations roll back for retry. Loss of the town
key loses every hosted key too. DelveTalk's custody vouches no more than the invitation: addressability, not trust.

**Request repositories are built.** The sole collection is `online.fg-goose.gsb.request`. Public describeRepo,
listRecords/getRecord, getRepo/getRecord/getLatestCommit, getRepoStatus/listBlobs, and hostname-selected
listRepos use Repo's framing. `getRepo` exports the complete current signed MST, including after deletions;
`since` receives a full export, including every node of the empty tree; absent keys can be
checked with the full export. sync.getRecord for a deleted key returns RecordNotFound. Tree is rebuilt in
sorted key order on each write and signed read using existing `Tree`
and `Key.commit`, without changing the journal tree's append caching. Value-derived CIDs and proof CARs use
these same blocks. The persistent per-account counter advances to `max(counter + 1, wall microseconds)`;
`rev = TID(counter)`. `prev` names the previous head, including the initial empty tree. Restart reconstructs
byte-identical head bytes and performs no snapshot write.

POST createRecord/putRecord/deleteRecord requires the invitation's `dt_agent_…` bearer, authenticating exactly
the stored principal this hosted DID maps from. A different account's credential is Denied; missing, invalid,
expired or revoked credentials cannot write. Only the request collection and TID keys are accepted; create
without rkey allocates a TID, put replaces or creates, delete removes. `swapRecord` and `swapCommit` reject a
moved value/head with InvalidSwap. Structural validation uses `transport/lexicon.py`, shared with lexicon tests,
and the shared `acts.judge_call` framing; it cannot be disabled. The poller's `judged` retains service/world,
observation-start and mode semantics. Repository write bodies allow 397,312 JSON bytes (six bytes per
possible control-byte escape plus framing); agent/procedure bodies retain the front's 256 KiB limit.
The catalogue exposes both limits. Each record is at most 65,536 DAG-CBOR bytes; 256 current requests at most. Capacity retains existing requests oldest first and refuses a new key with RepoFull; deletion makes
room, replacement does not need room. Hosted CAR replies are bounded at 17 MiB; listRecords pages are bounded at 4 MiB JSON including escaping,
with a cursor when this shortens a page. Other write methods answer
501; the world's repository stays read-only, 405.

With `hosted_accounts = true`, the poller registry's fourth source is the hosted snapshots. It reads them locally, verifies their signed
commit through the same `proven` function and CAR bytes as HTTP, and consumes each at-uri once under its first
proven CID. The bridge turns under `(hosted DID, at-uri)` and writes the ordinary public answer. The front and
bridge must share the same state directory. The poller and mirror remain off by default; provisioning starts neither.

**Zulip remainder.** With hosting enabled, the Zulip observer provisions the same hosted account when it observes a resident's message,
but continues to store message observations under `zulip:<realm>:<id>`. It does not turn messages into request
records or write that account's repository. Completion: a message chosen as a request creates one validated
public request in its resident's hosted repo, proven by the ordinary local poller and answered once; a second
read creates no turn. Existing message observation/turn behavior must not execute the request a second time.

**Links remainder.** Zulip and delve identities are distinct; nothing merges. `online.fg-goose.gsb.link` records
and the two-way `alsoKnownAs` check are not built. Completion: reciprocal link records and DID documents name
each other; a missing/reversed/mismatched claim refuses the link, without changing either principal's authority.

**Ops remainder (owner).** Wildcard DNS and certificates are not installed, and the owner has decided against
guest wildcard DNS. Hosting stays off unless that decision changes and `hosted_accounts` is enabled. Completion: the guest
and each configured Zulip realm's account hostname resolve to this front, HTTPS serves the exact account DID
and public key, and its sync proof verifies. DEPLOY gives the DNS names and the DNS-01 certificate boundary.

**Decision:** hosted accounts make guest and Zulip principals addressable with one request-only repository each,
local signed verification and invitation-authenticated writes. DNS/certificates, Zulip request writing and links
remain completion checks; custody confers no trust or identity merge.

## 5. Lexicons

Every collection and procedure is a file under `lexicons/online/fg-goose/gsb/` [lexicon]. This commit adds `defs` (call,
pin, outcome, trace, receipt), `request`, `answer`, `paint`, `checkpoint`, `act`, `try`, `plan`, `getEntry`, `openSession`,
`getSession`, `listSessionRecords`; `verb`, `chronicle`, `book`, `door`, `link` follow their lanes.
All are one NSID group, `online.fg-goose.gsb.<name>`, because each group needs its own DNS record and resolution does not
recurse [lexicon "Publication and Resolution"].

**Authority.** The group `online.fg-goose.gsb.*` belongs to whoever controls `gsb.fg-goose.online` [nsid],
which the owner does. Hyphens are allowed inside authority segments; the final names here are alphabetic.
The TXT record is live and verified (2026-10-12), pointing to the posting account `ember.delve.town`:

    _lexicon.gsb.fg-goose.online.   TXT   "did=did:plc:6amo7col5h4ciq2gpm5eur7b"

`python3 -m transport lexicons` prepares every JSON file under `lexicons/online/fg-goose/gsb/`, sorted by NSID,
as `com.atproto.lexicon.schema/<nsid>` in that account [lexicon "Publication and Resolution"]. Each value is the
complete lexicon document with `$type: "com.atproto.lexicon.schema"` added; `id` equals its record key. Publication
uses the posting account; the did:web signed tree stays a function of the journal and epoch ledger, and the authority
sits on a did:plc that survives a move of host.

The default is an offline dry run, exit 2. It reads files, opens no socket, reads no credential and writes no ledger.
It prints the exact TXT check command (without running it), then one canonical JSON line per schema and a final
count/DID summary. `cid` hashes the value's canonical DAG-CBOR through `transport.atproto.cbor`; `bytes` is that
block's byte length. The full local inventory is printed every dry run, including schemas already in the ledger.
Example first record and final summary for the current 18 files (the intervening 17 record lines are omitted here):

```text
dig +short TXT _lexicon.gsb.fg-goose.online
{"bytes":1184,"cid":"bafyreictrvq6zusqkmjxnehvjpsm7lhkno2ydluzadraip2nr4ekcveyq4","collection":"com.atproto.lexicon.schema","rkey":"online.fg-goose.gsb.act"}
{"count":18,"did":"did:plc:6amo7col5h4ciq2gpm5eur7b"}
```

The owner decides when to publish, after reviewing that dry run and TXT. Publication requires `--authorized` and
`--state DIR` (or `DELVETALK_STATE`); no deploy, compose service, timer, test or document step invokes publication
against a live account. `lexicon_authority` defaults to `did:plc:6amo7col5h4ciq2gpm5eur7b`, overridden by
`<state>/delvetalk.toml` or `DELVETALK_LEXICON_AUTHORITY`. `credentials` selects the posting credential. Before any
record write, `post.record_writer` authenticates and refuses unless the session DID equals that authority, even
on an unchanged run. Every putRecord addresses only the session's own repo.

The mirror and publication share `transport.records.plan` and `put_records`: canonical-value SHA-256 digests,
with the ledger saved atomically after each successful write. Publication's account-wide ledger is
`<state>/lexicons/<URL-encoded authority DID>.json`; selecting another world shares it, selecting another authority
uses its own ledger. The first publication writes every file, a second writes none, and changed values alone
are rewritten. A failed record remains pending for retry. **Publication never deletes:** removing a file leaves
its published record and digest held. Authorized output reports the written keys, remaining count and authority.
This command starts no daemon; the mirror and request poller remain off by default.

Owner decision, 2026-10-12: `delvetalk.town` cannot be bought; the group moved to `online.fg-goose.gsb`.

`try` is a keyword where lexicon codegen lands; it stays (the residents' word) and generated clients call it
`tryAct`. Tests check lexicon v1 definitions, nested refs, and the records and projection values the front and mirror emit.
The host projection value definitions and references to four live posting-record schemas live in `getProjection`; `kind` selects their required fields without
adding a `$type` to host replies. The list query references the same projection definition.

**Decision:** one NSID group, `online.fg-goose.gsb.*`, under the owner's `gsb.fg-goose.online`;
the TXT is live and publication is prepared for that account; the owner chooses when to authorize it.

## 6. What stays non-AT

- **The Lean host.** Admission, law, rules, wants, projection and rendering are the host's (AGENTS.md). AT Protocol
  carries and stores signed public state; it has no law judging a write (a PDS takes any record its owner signs).
  XRPC framing in the host would add protocol to the trusted core for nothing.
- **The journal's format.** `J` and `J.blocks`, canonical DAG-CBOR without `hash` (HOST-HANDOFF §3). The tree links
  the entry CID; the entry block is not a record, because its whole bytes are the principal's and getRepo must be the
  same for everyone (REPO).
- **Private reads.** Whatever only some readers may see is a façade or service-authed XRPC response, never a record.
- **The model.** hob and the paint stay behind the host; their output reaches AT only as journaled interpretations or
  the verified, unsigned `paint`.
- **Delve's feed.** Posts stay `town.delve.feed.post`: the public witness.

**Decision:** the host, the block format, private projections and model calls stay behind the transport; everything
public is a record; every act is a record or an XRPC call.

## 7. The order of work

| # | Lane | Work | Control |
| --- | --- | --- | --- |
| L1 | transport | **first slice**: the `requests` poller (listRepos rev diff, listRecords, sync.getRecord with signature and path checked); identity `(did, at-uri)`; `if` passed through; `answer` records by the mirror's writer and the façade | fixture Delve: a request gives one entry with intent = its URI and one `answer`; read twice, one entry; a commit signed by another key, no turn; stale `if`, `moved` with was/now; `mode: try`, refused with no entry and no answer. **Built** (`tests/test_requests.py`), every control on a real host; a `delvetalk try` spell by record is likewise never answered |
| L2 | docs, transport | lexicon test; `_lexicon.gsb.fg-goose.online` TXT, schema records (owner) | every emitted record validates; `_lexicon.gsb.fg-goose.online` resolves to the posting account |
| L3 | host, transport | `world-projection`; MST `put`/`delete`; per-height ops; paint split | `goat` or @atproto/repo verifies getRepo; CIDs equal in both repositories; a restart re-derives a byte-identical head |
| L4 | transport | **Built**: subscribeRepos, durable event seq/log, bounded cursor replay, rotation `#identity` and epoch/downtime `#sync` | a consumer inverting over `prevData` follows 1,000 heights, resumes from a cursor; workers free under ten subscribers |
| L5 | transport | **Built**: service-auth verifier, `#delvetalk` in did.json, `getEntry`, POST `act`, `try`, `plan`, caller projections, anonymous provenance-keyed answers and private previews | `tests/test_serviceauth.py`: wrong audience/method/time/header/curve, high-S and replay: 401 with no host call; bare and fragment audiences accepted; rotation refresh once; bounded nonce custody, issuer rate limit and one-block CAR. `tests/test_xrpc_acts.py`: retries, private/public projections, no-write exact previews, atomic plans, malformed bodies, HTTP methods and issuer rate limits; real-host composition. getServiceAuth/proxy untested live |
| L6 | transport; host remainder | **Built:** holder-only `openSession`, `getSession`, `listSessionRecords`, scratch act/try/plan; **remainder:** named readers and separate read/write/share/publish permissions require a host-owned `world-scratch` readers op | `tests/test_xrpc_sessions.py`: changed scratch card, identical town journal/answers/mirror plan/getRepo, unknown-holder and nonexistent response bytes equal, invalid tokens call no host, preview writes nothing, expiry refuses every scratch read/turn, response content absent from access log; existing `/scratch` controls retained. Host remainder completion: the host admits a named reader, distinguishes each permission and refuses unnamed principals; transport forwards that host judgement with no reader custody |
| L7 | transport; ops owner | **Built:** bidirectional guest/Zulip mapping, hosted documents and derived k256 keys, request-only signed repos, invitation writes, local verified polling, backup restoration, rotation and legacy migration. **Remainder:** wildcard DNS/certificates (owner), Zulip bridge request write, two-way links | `tests/test_hosted.py`: derivation vectors/rejection, JSON-only restore, rotation/migration epochs, keyless refusals, Host/proof/credential isolation, replace/delete/restart, bounds, concurrent writers and one answered turn per URI. §4 records the remaining completion checks |
| L8 | host | `plan` as one turn (built, lane/plan; by record since L1) | three calls, the third refused: nothing written, one receipt |

L1 ∥ L2 ∥ L5 (L5 is what gives a PDS-only resident `try`); L3 after L1; L4 serves the signed entry tree today; L6 after L5; L7 after L5; L8 any
time. Each lane commits named files and keeps `make check`'s narrow targets green.

**The first slice is L1, on what lane/posting built.** selene's mirror can read the town now: the posting account
holds every card, page and the index, and her mirror walks it with listRecords like any repo (the owner's step: run
`mirror` authorized). L1 adds acting: a resident writes `online.fg-goose.gsb.request` in their own repo, the poller proves
and runs it, and the answer (the receipt with its entry CID, and the offers and trace when all of it is public) appears as
`online.fg-goose.gsb.answer/<did>.<rkey>` in the account their mirror already reads. No post, no HTTP beyond their PDS, no
credential; the request and answer are public, as §3's table says, and looking first waits for `try` by XRPC (L5).
The live test is the owner's account writing one request; it writes to delve, so it waits for his word. The bridge runs the poller only under the config's `requests` (`DELVETALK_REQUESTS=on` in the workhorse's `.env`), off by default: it reads the participant registry at each DID's current PDS, so starting it is the owner's step too.

**Findings for other lanes.** `observe.py` summoned `livedelvetalk.delve.town`, which resolves `HandleNotFound` on
pds.delve.town; the summoned handle is the config field `summon_handle`. The owner's decision (2026-10-12): it stays
`livedelvetalk.delve.town`, a fictional address matched as the post's text, never resolved to a DID, while the
replies go out through the owner's account (`credentials`); the two need not be one account. REPO and FEDERATION §7 named path-based
did:web DIDs, which atproto rejects; each world is now `did:web:<world>.<host>` (`repo.world_origin`). Our NSIDs use the owner's `gsb.fg-goose.online` (§5). Nothing reads the clerk's
`org.delvetalk.*` records; they stay until the owner says.

**Decision:** L1 first; L3 and L4 make our repository the full signed record; L5 serves agents with HTTP and through
the PDS proxy; L6 gives hidden sessions; the owner adds `_lexicon.gsb.fg-goose.online` TXT and gives the word for live probes.

## 8. The review of 2026-10-12, decided

docs/review/astra-2026-10-12/atproto.md, each finding checked against the code and the cited spec. Fixed in L1:

| # | Finding | Decision |
| --- | --- | --- |
| 1 | requests bound to no service; old requests replayable | fixed: `service` (our DID) required, `world` matched by the bridge, `createdAt` before the world's `since` never run; a uri consumed once under its first proven CID |
| 2 | the answer discloses what only the caller reads | fixed: the answer is the anonymous projection (§2 "The answer"); `answerView` stays the shape of an authenticated XRPC response (L5) |
| 6 | three lexicons nest objects inline | fixed: `card#door`, `openSession#fork`, `listSessionRecords#sessionRecord`; `tests/test_lexicons.py` checks every document and every answer the bridge writes |
| 7 | a key watermark loses requests | fixed: a moved rev re-reads the whole collection; consumed and refused are kept by uri and CID, apart from scan progress; a request stays until answered |

Fixed in L3:

| # | Finding | Decision |
| --- | --- | --- |
| 4 | carry and key rotation break rev continuity | fixed: one durable epoch ledger at `State.repo_ledger` (`worlds/<world>/repo.json`), atomic writes inside `Signed.lock`; `{key, base, epochs: [{height, clock, cause}], head: {height, rev, clock}}`. A changed base raises the floor to `head.clock + 1` at the first carried height, tree empty, `prev` null, pre-carry entries reconciled away. A changed key on the same journal raises the floor after head height H, signs the same root once at `TID((head.clock + 1) × 60,000,000)`, `prev` null; H+1 chains from it. Old commits are not rebuilt, old record revs remain `since` cursors. Restart depends only on journal, key and ledger and changes no bytes. Carry copies the ledger with state; deletion requires follower re-sync. L4 announces epochs with `#sync`, and rotations with `#identity` before it |
| 5 | the façade answers non-record CIDs under `com.atproto.repo.*` | fixed: one pair of queries, `online.fg-goose.gsb.getProjection`/`listProjections`, for receipt/object/source/publication/grant/law and public live card/page/index/answer; `{kind, key, of?, value, signed?}` with host values untagged, `of` the subject CID. Receipt `signed` points to `entry/<rev>` when in the current tree. Repo record methods accept only signed entry records, each `cid` hashes `value`; sync.getRecord proves only the requested entry path and includes whole bytes for its principal. `getEntry` is built in L5 |
| 12 | the signed index naming its own head is a cycle | fixed: `index` never carries did/rev/commit/head in projections or posting records; its bytes depend on the journal alone. The posting-only `online.fg-goose.gsb.checkpoint/self` names `{did, rev, commit, height}`, fetched from the world's front before host reads, written after the index or alone when the source head changes, through the same plan/digest/ledger. Unavailable source: records proceed, reason reported, held checkpoint retained. No timestamp; no did:web façade or signed-tree checkpoint; dry run only reads (§1, `tests/test_mirror.py`) |
| 14 | canonical strongRef URI and mirror mapping | world at-uris name only records actually in its signed MST (`entry` today). Live card/page/index/answer values are projections; strongRefs to those values name the posting account's actual records. Checkpoint + index describe provenance, never world membership. World canonical paths for these kinds require signed integration; version retention remains below |

Fixed in L4:

| # | Finding | Decision |
| --- | --- | --- |
| 10 | height cannot be the firehose `seq` | fixed: `State.firehose` (`worlds/<world>/events`) stores each exact frame once, fsynced, with endpoint-wide consecutive seq and epoch/head-height coverage. Carry copies it; restart reconciles downtime with one head sync. Rotation identity precedes sync, never connect. Newest 10,000 retained, atomic compaction at 20,000; live-only without cursor, ordered replay > cursor, OutdatedCursor then oldest replay, FutureCursor/InvalidRequest then close |
| 11 | one commit event per height can overflow; deltas need inversion context | fixed: one `fits` decision enforces ≤200 ops and ≤2,000,000 CAR bytes, otherwise head-only sync; `rebase: false`, `tooBig: false`, empty blobs. Per-height CARs contain nodes read by partial-tree inversion, separate from getRepo slices. Independent inversion tests cover creates, new layers/root shrink, updates and deletes; real consumer follows 1,000 commits and resumes identical bytes |

Fixed in L5:

| # | Finding | Decision |
| --- | --- | --- |
| 3 | OAuth discovery reaches internal addresses; did:web DNS can rebind between check and connect | fixed: one global-address policy for discovered URLs, including browser authorization and optional revocation; `delve.public_transport` resolves once per request and connects to the first checked IP, with verifying TLS for the URL host and its original Host header. All DNS answers must be public; mapped/compatible/NAT64/6to4 private forms are refused. OAuth discovery and DPoP POSTs and `Client.did_document` use it by default; configured XRPC, Zulip and model hosts keep `http_transport`. Injected fixture transports preserve the loopback tests without an HTTP scheme switch; `test_netsafe` and `test_oauth` name the attacks (§2) |
| 8 | discovery tied to one PDS and DID method | Fixed in L5: participant DID registry = active delve repos ∪ verified claim DIDs ∪ config `participants` ∪ local hosted accounts (L7); did:plc and hostname-level did:web only. Documents cache ten minutes, one verification-failure refresh per participant per poll. Every read uses the document's public HTTPS PDS; `(pds, rev)` skip, full scan after migration, consumed URIs and refused CIDs retained. Hosted accounts supply documents and the same signed CAR locally to `proven`; external participants use one getLatestCommit per resolved PDS per poll, cap 256, overflow reported by DID. `tests/test_requests.py` covers two PDSes, migration/stale copies, did:web, rotation, skip and destination/cap refusals (§2, §4) |
| 9 | the bare-audience exception cannot know the forwarder | Fixed in L5: our bare DID and `#delvetalk` audiences are treated identically; no forwarder inference. `typ` JWT; matching ES256K/ES256 curve, integer `exp` within 300 s and optional `iat` within 30 s skew and lifetime 300 s; required method-bound `lxm` and atomic, bounded `(iss, jti)` custody. Public DID fetch, 60 s cache, one signature-failure refresh; getEntry and act/try/plan consume the verifier (§2(b), `tests/test_serviceauth.py`, `tests/test_xrpc_acts.py`) |

For the next slices, each with its decision:

| # | Finding | Decision | Lane |
| --- | --- | --- | --- |
| 13 | proxied calls are visible to the resident's PDS | stated in §3's table for getEntry, act/plan, try and built sessions: the resident's PDS is inside the trust boundary of every proxied call; privacy from it needs a direct call | L5, L6 |
| 14 | retrieving versions cited by book or paint | required when those records land: immutable versioned keys for book/paint and every card/page version they cite; no claim of historical retrieval from overwritten singleton keys (§1) | L3 |
| 15 | sessions have no unambiguous address | built: `scratch/<name>` resolves under the service token's `iss` to `DIR/scratch/<iss>/<name>.journal`; holders cannot alias one another. Expired/recreated names are new scratches by the host's rule, not retained incarnations. Named readers and separate read/write/share/publish permissions await the host-owned `world-scratch` readers op with the L6 completion check | L6 |
| 16 | XRPC acts cannot make request-keyed answers | built: key `xrpc.<iss>.<sha256(intent), base32 lower 26 chars>`, required tagged source selects request strongRef or provenance `{iss, intent}`; one public projection and writer, shared state directory | L5 |
| 17 | constraints only in prose | built for procedures: shared exclusive call/plan/pin judgement, byte/count budgets, required tagged answer provenance, distinct turn/preview schemas and discriminants; malformed bodies 400 InvalidRequest. Lexicon v1 cannot declare a named union, so the untagged defs#call exclusivity and fields-object constraint are enforced in acts.judge_call. Other record budgets remain L2 | L5, L2 |
| 18 | labels on the canonical record do not reach the copy | moderation subjects must name actual repository records; world URIs for live kinds require signed integration. Label propagation to posting records remains L2 work | L2 |
