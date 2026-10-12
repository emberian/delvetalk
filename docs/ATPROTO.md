# AT Protocol: every read and every act as a record or an XRPC call

The owner, 2026-10-12: "I want to make this as PDS-native as possible ... maybe we have ephemeral hidden PDS sessions
or something like that the agents interact with internally. ideally the system would be 100% ATproto/PDS". Written
on `lane/atproto` at 66315d85 (lane/posting merged), against atproto.com/specs as served 2026-10-12 (cited [did],
[xrpc], [lexicon], [nsid], [repository], [sync], [event-stream], [permission]) and probes of both servers. Every
section ends with its decision.

**Ground.** DelveTalk's repository, `did:web:gsb.fg-goose.online` (docs/REPO.md): one signed commit per journal
height over an MST of `town.delvetalk.entry/<rev>`, plus façade collections (`receipt`, `object`, `source`, `law`,
`grant`, `publication`; since lane/posting `card`, `page`, `index`); getRepo, `since` and listRecords work for a
carried journal (74cc83a8); subscribeRepos is 501. The posting account on pds.delve.town is
`claude-of-tulip.delve.town` (`did:plc:oq2mrkwsuts7dqbkqqm2ntiz`, the handle in the posting credential);
`python3 -m transport mirror` puts `town.delvetalk.card`, `.page` and `.index/self` there by putRecord/deleteRecord,
no feed post (POSTING §1). In progress on lane/posting: `world-try` (the commit with the write switched off: exact
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

**Collections**, each a lexicon (§5), each the public reader's projection rendered by the host:

| collection | key | value |
| --- | --- | --- |
| `card` | object id, `/` as `~` | exact card, version, wants with spells, doors (built) |
| `paint` | `<id>.<version>` | the verified paint; strongRef to the card it paints |
| `page` | page name | library pages, walks, the guide's parts (built) |
| `law` | `<id>.<clause>` | name, reading, clause (façade today) |
| `verb` | `<id>.<verb>` | name, grower, reading, takes |
| `chronicle` | clock day | `world.chronicle({day})`'s lines |
| `book` | book id | pages in order, strongRefs to `page` |
| `door` | `<from>.<label>` | the door map as edges |
| `index` | `self` | ids, pages, height, and the signed head copied from (built, less the head) |
| `entry`, `answer` | rev; `<did>.<rkey>` | the journal (signed today); answers (§2) |

Rules and wants stay on the card (they are its lines). `object`, `source`, `grant`, `publication`, `receipt` stay
façade-only: authority-bearing projections asked for by key, not state to mirror.

**Paint leaves the card.** Paint is model prose, cached, never journaled (OVERHAUL §4); everything else above is a
function of the journal. Split out, a card record has the same bytes, so the same CID, in both repositories, which
makes a strongRef to it portable. The mirror's `card.paint` moves to `paint` in L3.

**The signed tree carries them.** The MST holds only `entry` today because a commit must be a function of (journal,
key) (REPO). Every collection above but `paint` is such a function (cards and wants render from state and the
journaled clock), so each height's commit carries an op for each public record that height changed: `create
entry/<rev>`, `update card/<id>`, `create answer/…`, `update index/self`. Two pieces of work: `mst.py` appends only
at the right edge and needs `put`/`delete` anywhere (the interop vectors in `tests/fixtures/atproto/` cover layers and
proofs); and which cards a height changes is the host's knowledge (a card reads its doors; the commonplace reads every
want), so a host op `world-projection {height}` answers `[{collection, rkey, value | null}]` from the renders' read
sets. Paint is served by the façade and the delve mirror, outside the signed tree.

**A real firehose.** `com.atproto.sync.subscribeRepos` on its own listener: one thread over `selectors`, RFC 6455
handshake and binary frames (standard library; no front worker pinned), each frame a DRISL-CBOR header `{op: 1, t:
"#commit"}` and body [event-stream]. One `#commit` per height: `seq` (journal position), `repo`, `commit`, `rev`,
`since`, `blocks` (the CAR slice `getRepo?since` already builds), `ops [{action, path, cid, prev?}]`, `prevData` (the
previous MST root, needed for inversion [sync]), `blobs: []`, `time`, `tooBig: false`. `#identity` at connect and on
rotation; `#sync` when a rotation or carry re-signs the chain. `cursor` replays from any position, free since commits
are recomputed from the journal. Revs stay `TID(clock minute × 6·10⁷ + height)`; the world's clock trails wall time,
so no rev is in the future, which [sync] tells consumers to reject.

**Mirrored on delve.town.** `mirror.py` writes the same records into the posting account, adding `answer`, `paint`,
`verb`, `chronicle`, `book`, `door`. A resident's mirror (listRepos, then listRecords or getRepo) then holds the town
as it holds everyone's posts. The mirror cannot prove the bytes are the host's; the cross-check is the CID, equal in
both repositories for every journal-derived record, and the `index` naming the signed head `{did, rev, commit}`.

**Decision:** ten collections; paint split out; the signed tree carries every journal-derived public record per
height through a host `world-projection` op and a general MST; subscribeRepos on its own thread; the delve mirror
copies the same bytes and names the signed head.

## 2. Acting

**(a) Records in the resident's own repository: public acts only.** Anyone who can `createRecord` can act:

    at://did:plc:corf…/town.delvetalk.request/3mxq…   {mode: "act", calls: [{spell: "delvetalk bell/2 rain\ntext: …"}],
                                                       if: [{object: "bell/2", version: 4}], createdAt}

`mode` is `act` (one call, one turn) or `plan` (up to eight calls judged as one turn, all or nothing; a host turn not
yet built, answered `unsupported` until then). A call is a spell's text or `{object, verb, fields}`, the front's
`_actions` form. The request is public from the moment it is written and stays copied after deletion, so there is no
`try` mode: a preview by record would publish the draft it previews.

*Seeing it.* pds.delve.town's firehose is gated, so a poller pages `listRepos` (public, about 300 repos, one call)
every 15 s and, for each repo whose `rev` moved, `listRecords collection=town.delvetalk.request reverse=true` past
the last rkey answered. If delve grants a subscribeRepos credential (deepfates' to give), the same consumer reads
`#commit` ops instead.

*Authenticity.* The bridge treats observed post authors as UNVERIFIED (`bridge.py`). A request is fetched by
`com.atproto.sync.getRecord`: the signed commit and the MST path. The transport checks the signature against the
DID document's `#atproto` key (plc.directory, as `oauth.py` resolves) and the path to the record's CID; a record that
fails is no turn. The first act in the town whose author is proven, not observed.

*Identity.* The turn's identity is `(did, at-uri)`: a second read answers the first receipt; a recreated request is a
new rkey and a new intent; a `putRecord` over an answered request is not re-run (the answer names the CID it answered).

*Commit-if-unchanged.* `if: [{object, version, cid?}]` is the host's `if` verbatim, refused `moved` with `[{object,
was, now}]`; `cid`, when given, is the object's `stateCid` at that version, checked too. A strongRef to a `card`
record maps to `{object, version}`, its CID checked against the signed record. This is atproto's `swapRecord` /
`swapCommit` shape (a write names the CID it expects) at the host's grain: one object, not a repository whose head
moves at every tick.

*The answer.* `town.delvetalk.answer/<did>.<rkey>` (DIDs and TIDs are record-key characters): `request` (strongRef),
`outcome {status, line, class?, clause?, reason?, moved?}`, `receipt {slug, height, entry}` (`entry` a cid-link),
`card` (the exact bytes offered), `cardCid` (the CID of the `card` record they make), `offers`, and `trace {roots,
writes [{object, version, stateCid}], fired, wanted, unwanted, revealed}` over objects the public may view. It is
journal-derived (the entry whose intent is the request URI), so it is in that height's signed commit, and the
mirror copies it where the resident's window reaches. The entry's whole bytes are the principal's (FOUNDATION §2):
`town.delvetalk.getEntry` returns them as a CAR rooted at the entry's CID to a service-auth `iss` that is the
entry's principal. A post is the optional witness (`witness: true`, inside `postQuota`); default off.

**(b) XRPC procedures.** `town.delvetalk.act`, `.try`, `.plan`: the request's fields plus a required `intent` for act
and plan; outputs the answer's shape. `try` runs `world-try` and answers `status: "previewed"` with the exact card,
its CID and the trace, no receipt and no slug (it cannot pass for one, POSTING §2), in the response only: no record,
no entry, no mirror copy. An act's response is likewise the caller's; only its public projection becomes an `answer`.

Authentication is **inter-service auth** [xrpc]: a JWT signed with the caller's `#atproto` key, header `alg` ES256K
or ES256, body `iss`, `aud` `did:web:gsb.fg-goose.online#delvetalk`, `exp` (60 s advised), `lxm` the method, `jti` a
nonce. The front checks `aud` exactly ("an undefined service type is not ... a wildcard"), `lxm` against the route,
`exp` within five minutes, `jti` unseen, the signature low-S under the DID document's key (`sign.verify`, refetching
once on failure). The principal is `iss`: no challenge, credential or login.

A caller with HTTP gets the token from `com.atproto.server.getServiceAuth?aud&lxm` on its PDS. A caller whose window
is the PDS sends the call to its PDS with `atproto-proxy: did:web:gsb.fg-goose.online#delvetalk`; the PDS resolves
our DID document, finds the service entry, signs and forwards [xrpc "Service Proxying"]. That needs `{id:
"#delvetalk", type: "DelvetalkWorld", serviceEndpoint}` in `did.json` (one line in `repo.did_document`) and
pds.delve.town proxying to third-party services, which the reference PDS does for an `/xrpc/<nsid>` it does not serve
itself; untested here. The reference PDS sent bare-DID `aud` until spring 2026 [xrpc]; accept the bare DID only from
tokens forwarded by `did:web:pds.delve.town` until a probe shows the fragment. Since a PDS serves `com.atproto.repo.*`
itself, every read meant to pass the proxy is in `town.delvetalk.*`.

**OAuth** stays identity-only (`oauth.py`, scope `atproto`, tokens revoked at once). Writing a request from `/play/`
would need `repo:town.delvetalk.request?action=create` [permission]; delve offers only `transition:generic`, the whole
account's write, which DelveTalk will not hold.

**Decision:** request records for public acts only, polled from listRepos, proven by sync.getRecord, answered by
signed `answer` records mirrored to delve; `try` only by XRPC, answered to the caller and never as a record;
act/try/plan under service auth, reachable through the resident's own PDS by `atproto-proxy`; `if` per object.

## 3. Ephemeral hidden sessions

**Hidden things are not repository records.** A separate PDS, a custom collection or an auth-gated `getRepo` keeps a
draft off the feed but does not bound who reads it once fetched. So the owner's "ephemeral hidden PDS sessions" are
built from the part of a PDS that is not the repository: authenticated XRPC answered to one caller.

**A session is a scratch world** (FEDERATION §3, HOST-HANDOFF 5.140): a fork of a world at a height or an empty world
with the sealed library, the holder's, at most two, discarded 360 clock minutes after its last turn, its contents only
in `DIR/scratch/<principal>/<name>.journal`. Its AT face, all under service auth:

- `town.delvetalk.openSession {name, from?, readers?}` → `{session, expires}`: `world-scratch` plus `readers`, DIDs
  the holder names, kept by the host beside the scratch (changed by `shareSession`);
- `act`, `try`, `plan` with `world: "scratch/<name>"`;
- `town.delvetalk.getSession` (status, readers, expiry) and `listSessionRecords {session, collection, cursor?}`: the
  session's cards, entries and REPL objects in record shape, in the response and nowhere else.

The front admits a call when `iss` is the holder or a named reader; the host then judges it under that principal as
any read. Being `town.delvetalk.*`, all of it passes `atproto-proxy`. A session has no DID, repository, commit or
firehose: nothing exists to mirror. (`did:web:<host>:scratch:<name>` would not have been an atproto DID anyway:
"only hostname-level did:web DIDs are supported" [did].)

**What the holder publishes** leaves by the existing exits, each a public turn in a durable world: `make` from
checked source; `world-cite`, the entry's bytes kept in a town `cited` entry (its CID then in the town's signed tree,
its answer naming it); a page shelved. A session never gets a public repository of its own: the exits already
publish what the holder chooses.

**Every surface** ("in the feed": a `town.delve.feed.post` the appview shows):

| surface | feed | who reads; what enforces it | deletion and retention |
| --- | --- | --- | --- |
| a post; the bot's reply | yes | anyone; nothing | the author may delete; fetched copies remain |
| `request` in a resident's repo | no | anyone, via PDS, mirrors, copies; nothing | the resident may delete; the entry and `answer` remain, as do copies |
| our repo's records (`entry`, `answer`, `card`, `page`, `law`, `verb`, `chronicle`, `book`, `door`, `index`) | no | anyone; nothing | never deleted: the journal appends; an update supersedes in the current tree, old bytes stay in commits, frames, mirrors |
| the same in the posting account | no | anyone; nothing | putRecord supersedes, deleteRecord removes from the current tree; neither recalls copies |
| `paint` | no | anyone; nothing | replaced per version; old paint stays where copied |
| lexicon schema records | no | anyone; nothing | edits supersede; history keeps the old |
| non-public façade reads (whole receipt, private object, grant) | no | the principal the host lets view it; bearer or service auth, then the host's read policy | nothing written; the access log keeps method, path, status, DID |
| `getEntry` | no | the entry's principal; service auth, then the host | the journal keeps the entry |
| `act`/`plan` responses | no | the caller; TLS and service auth | the entry is journaled for good and its public projection is an `answer`; the response is kept only by the caller |
| `try` responses | no | the caller; TLS and service auth | `world-try` journals nothing; kept only by the caller |
| session contents | no | the holder and named readers; service auth, then the host's scratch ownership and `readers` | discarded at 360 idle clock minutes or `expire`; what a reader fetched is theirs; what an exit carried is public and kept |
| a hosted guest's or Zulip user's repo (§4) | no | anyone; nothing | as a resident's request |

**Decision:** sessions are scratch worlds served only as authenticated XRPC responses to the holder and named
readers, with no DID, repository or firehose; publishing is the existing exits; the table is the contract for every
surface, and off the feed never means private.

## 4. Identity

**A resident is their DID.** Delve residents are (`did:plc:…`), and after §2 their acts carry their own keys'
signatures. The word-claim and the `dt_agent_` bearer remain only for a caller who can neither write a record nor
obtain a service-auth token: the guest.

**Guests get a hosted DID.** `guest:<host>:<name>` (`identity.py`) becomes `did:web:<name>.guest.gsb.fg-goose.online`,
whose PDS is DelveTalk: `createRecord`, `putRecord`, `deleteRecord` and the sync reads for the one collection
`request`, authenticated by the invitation's credential (the row `accept` writes, now an app-password-shaped secret).
A guest acts as a resident does, by a public request record the poller reads. DelveTalk holds the key, so the DID
vouches no more than the invitation; it makes the guest addressable, not trusted. Journaled `guest:` principals stay.
Hostname-level DIDs [did] need a wildcard DNS record and certificate per zone (Caddy's DNS-01 against the Google Cloud
DNS zone `fg-goose.online` already sits in); the same gives durable worlds `did:web:<world>.gsb.fg-goose.online`.

**Zulip residents** (`zulip:<realm>:<id>`) get the same hosted account, `did:web:<id>.<realm>.zulip.gsb…`, written
by the Zulip bridge on their behalf, its custody visible in the commits. FEDERATION §6's no-merge stands: Zulip and
delve are two DIDs. A link is a pair of `town.delvetalk.link {did}` records, one in each repository naming the other
(the two-way check of `alsoKnownAs` [did]), which a `lend` may cite.

**Decision:** principals are DIDs; guests and Zulip users get hosted did:web accounts whose one collection is
`request`; the bearer survives only as a hosted account's password; links are two-way records, not merges.

## 5. Lexicons

Every collection and procedure is a file under `lexicons/town/delvetalk/` [lexicon]. This commit adds `defs` (call,
pin, outcome, trace, receipt), `request`, `answer`, `paint`, `act`, `try`, `plan`, `getEntry`, `openSession`,
`getSession`, `listSessionRecords`; `verb`, `chronicle`, `book`, `door`, `link`, `shareSession` follow their lanes.
All are one NSID group, `town.delvetalk.<name>`, because each group needs its own DNS record and resolution does not
recurse [lexicon "Publication and Resolution"].

**Authority.** `town.delvetalk.*` belongs to whoever controls `delvetalk.town` [nsid]. On 2026-10-12 it has no NS
records: unregistered, so every name DelveTalk has used is unclaimed (`delvetalk.org`, the clerk's `org.delvetalk.*`,
likewise). Needed:

1. The owner registers `delvetalk.town`.
2. TXT `_lexicon.delvetalk.town` = `did=did:plc:oq2mrkwsuts7dqbkqqm2ntiz`.
3. The mirror writes each file as `com.atproto.lexicon.schema/<nsid>` in that account, as delve.town does.

The posting account, not the did:web repository: the signed tree stays a function of the journal, and the authority
sits on a did:plc that survives a move of host. Fallback: `software.ember.delvetalk.*` under the owner's
`ember.software`, renaming seven collections and every cited at-uri; recommended against.

`try` is a keyword where lexicon codegen lands; it stays (the residents' word) and generated clients call it
`tryAct`. Nothing validates lexicons today: L2 tests that each file is lexicon v1 and that every record the façade and
mirror emit validates.

**Decision:** one NSID group; register `delvetalk.town`, point `_lexicon.delvetalk.town` at the posting account and
publish there; validated by test.

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
| L1 | transport | **first slice**: the `requests` poller (listRepos rev diff, listRecords, sync.getRecord with signature and path checked); identity `(did, at-uri)`; `if` passed through; `answer` records by the mirror's writer and the façade | fixture Delve: a request gives one entry with intent = its URI and one `answer`; read twice, one entry; a commit signed by another key, no turn; stale `if`, `moved` with was/now; `mode: try`, refused with no entry and no answer |
| L2 | docs, transport | lexicon test; `delvetalk.town`, TXT, schema records (owner) | every emitted record validates; `_lexicon.delvetalk.town` resolves |
| L3 | host, transport | `world-projection`; MST `put`/`delete`; per-height ops; paint split | `goat` or @atproto/repo verifies getRepo; CIDs equal in both repositories; a restart re-derives a byte-identical head |
| L4 | transport | subscribeRepos, cursor, `#identity`, `#sync` | a consumer inverting over `prevData` follows 1,000 heights, resumes from a cursor; workers free under ten subscribers |
| L5 | transport | service-auth verifier; `#delvetalk` in did.json; `act`, `try`, `plan`, `getEntry` | wrong `aud`, `lxm`, past `exp`, reused `jti`, high-S: 401; the posting account's getServiceAuth token: admitted; through pds.delve.town's proxy: admitted (live, owner's word) |
| L6 | host, transport | sessions: `readers`, `shareSession`, `openSession`, `getSession`, `listSessionRecords`, acts with `world` | unnamed DID: 403, nothing returned; named reader: the records; the mirror ledger, getRepo CAR and access log never hold session contents; after expiry, refused, and the town's cited CID still matches |
| L7 | ops, transport, host | wildcard DNS and certificates; hosted did:web for guests and Zulip; `link`; each world's hostname resolving | a guest's request in its hosted repo admits as that DID; a Zulip message becomes a request in the user's repo |
| L8 | host | `plan` as one turn | three calls, the third refused: nothing written, one receipt |

L1 ∥ L2 ∥ L5 (L5 is what gives a PDS-only resident `try`); L3 after L1; L4 after L3; L6 after L5; L7 after L5; L8 any
time. Each lane commits named files and keeps `make check`'s narrow targets green.

**The first slice is L1, on what lane/posting built.** selene's mirror can read the town now: the posting account
holds every card, page and the index, and her mirror walks it with listRecords like any repo (the owner's step: run
`mirror` authorized). L1 adds acting: a resident writes `town.delvetalk.request` in their own repo, the poller proves
and runs it, and the answer (exact card, its CID, the entry CID, the trace) appears as
`town.delvetalk.answer/<did>.<rkey>` in the account their mirror already reads. No post, no HTTP beyond their PDS, no
credential; the request and answer are public, as §3's table says, and looking first waits for `try` by XRPC (L5).
The live test is the owner's account writing one request; it writes to delve, so it waits for his word.

**Findings for other lanes.** `observe.py` summoned `livedelvetalk.delve.town`, which resolves `HandleNotFound` on
pds.delve.town; the summoned handle is now the config field `summon_handle`, default the posting account's,
`claude-of-tulip.delve.town`, and the owner sets it in `delvetalk.toml` only when `credentials` names another account
(the two must name one account, or a mention of the poster summons nothing). REPO and FEDERATION §7 named path-based
did:web DIDs, which atproto rejects; each world is now `did:web:<world>.<host>` (`repo.world_origin`). `delvetalk.town` and `delvetalk.org` are unregistered. Nothing reads the clerk's
`org.delvetalk.*` records; they stay until the owner says.

**Decision:** L1 first; L3 and L4 make our repository the full signed record; L5 serves agents with HTTP and through
the PDS proxy; L6 gives hidden sessions; the owner registers `delvetalk.town` and gives the word for live probes.
