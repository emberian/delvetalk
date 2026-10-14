# atproto Spaces: private channels to the witness

DelveTalk uses Spaces for **inbound private intent** and **outbound per-audience views**. It never uses them for
authority. Each town's own did:web is its space authority. Each resident gets a *desk*, a space of one in which they write
spell requests that nobody else reads. Each audience of a hidden-state object gets a *seat*, a space the town writes
that audience's view into. Admission, law and receipts stay in the Lean host. Every turn, whichever channel it came
by, gets a public **digest** in the signed tree.

Why it matters:
- A request becomes a turn with no post, mention or public `answer`: no ping lists, no ledgerslop, and `try` by record.
- Hidden game state (fog, hands) reaches the right players as syncable records. Its truth stays in the journal.
- The digest makes "anyone can verify a refusal" true; the public tree holds only CIDs and heights today.

Design only; nothing is built. Sources: proposal 0016 (P§); atproto `permissioned-data` @ 5b95b2f2 (PR 5187).

## 1. Spaces, as specified

- A space is `(authority DID, type NSID, skey)`, addressed `at://{authority}/space/{type}/{skey}`, and its records
  are `…/{author}/{collection}/{rkey}` (P§Addressing). The `skey` has rkey syntax, so a DID is a valid skey.
- Each author keeps one space repo per space on their own PDS. A commit is a signed LtHash set digest (BLAKE3 XOF).
  The signature covers only a nonce, so a leaked commit is **deniable** (P§Commit signature).
- To read, an app takes `com.atproto.space.getDelegationToken` from the user's PDS to the authority's
  `getSpaceCredential`. The authority alone decides, and the protocol carries no member list (P§Access control).
  A credential lasts ≤60 minutes (default 10), bound to a P-256 key by RFC 9421; `notifyCredentialRevoked` revokes by `jti`.
- Read access is all or nothing at the space boundary (P§Read access).
- No relay: syncers call `listRepoOps`, `getRepo` and `getLatestCommit` on each author's host. The writer's PDS sends
  `notifyWrite` (service auth, `iss` the writer) to `#atproto_space_host` (`packages/pds/src/space-notifications.ts`).
- The authority resolves its `#atproto_space` key (falling back to `#atproto`) and its `#atproto_space_host`
  service (falling back to `#atproto_pds`); did:web works (`auth-verifier.ts` `resolveSpaceKey`). A PDS accepts a
  write to a foreign authority's space without asking it.
- **Access control, not confidentiality.** PDSes and admitted apps read everything (P§Introduction).

## 2. The mapping

**Authority.** Each town hosts its own spaces under its own did:web (`did:web:gsb.fg-goose.online`,
`did:web:obend.fg-goose.online`), with no PDS account and no `simplespace`. Its DID document gains `#atproto_space`
(a dedicated key) and `#atproto_space_host` (the town's origin), so space URIs name the town as entry URIs do.

**Desk** (`online.fg-goose.gsb.desk`, skey = the resident's DID). One per resident; only
that resident and the town read it. No creation, no `putMember`: the host admits the skey's DID and nobody else.
Arrival changes nothing: the first desk request is judged like any first act, and the avatar comes from the first
admitted turn. Revocation: the host's admit op refuses, transport mints no credential and tracks no writes, and
held credentials die within 10 minutes or at once by `notifyCredentialRevoked`.

**Seat** (`online.fg-goose.gsb.seat`, skey = `<object>.<audience>` with `/` written as `~`). One per audience the
object's read policy distinguishes (a side's fog, a player's hand). Only the town writes there; resident writes are
never tracked. Membership is **derived from host state** (who holds the seat); a height that changes an audience
revokes, locally and at once, since seat repos live on the town alone. Membership never flows back: no law reads it.

| DelveTalk state | Where |
| --- | --- |
| cards, pages, law, chronicle, entries, digests | public: the signed tree and the posting mirror, as now |
| a resident's private request, plan, `try`, whisper | their desk, as a `deskRequest` |
| the answer to a desk request | the town's repo in that desk (the caller's projection); also by `getProjection`, proxied or direct |
| fog of war, a hand of cards | host state under read policy; its view is copied into each audience's seat |
| workshop drafts | the author's desk as a `draft`, read only when a request cites it by strongRef |
| the mending drawer | **never a space**: direct service-auth XRPC only (§3) |
| scratch sessions | unchanged: holder-only XRPC, no repository |

No shared room space holds requests: read is all or nothing, so an opponent would read a move before it was judged.

## 3. The boundary

A space admits **reading**. Only the host admits **acting**. Transport custody lives in `transport/spaces.py`, a
sibling of `requests.py`. Python verifies, carries and mints. It decides nothing:

1. `notifyWrite` is verified as service auth (`serviceauth.py` accepts `aud` `<town>#atproto_space_host` for that
   `lxm` alone) and only queues `(did, space, rev)`; a bounded `getLatestCommit` sweep covers lost notifications.
2. The syncer reads the desk at the PDS the resident's DID document names, with a self-minted credential and
   `Atproto-Space-Audience: <did>`: `listRepoOps?since`, or `getRepo` when the oplog is gone. It verifies the commit
   signature (`#atproto`), the MAC and its own LtHash fold, never trusting TLS.
3. Each new `deskRequest` takes the path a public request takes: shared `judged` framing, then `world-reach`, then
   `world-turn`, with identity `(author DID, space at-uri)`. An at-uri is consumed once, under its first verified
   CID, and requests created before the desk's `since` are never run.
4. `getSpaceCredential` checks the delegation JWT and its RFC 9421 signature, asks the host `space-admit {space,
   principal, access}`, and mints only on `admit`.

Nothing in a space bypasses admission: a record's presence grants nothing; membership is no principal, grant or
clause; another DID's write in your desk is never read; desk turns meet the same law and pace as posted ones.

**Never in a space**, since the PDS operator, its admins and every admitted app read it: credentials, keys, tokens,
invitation codes, bearer nonces; security reports (the drawer); another person's private data; anything hidden from
some reader of that space; during the alpha, anything one would not lose or show a stranger. A space is transport:
losing one loses only requests not yet synced.

## 4. Receipts and the public digest

**A space-born turn** is one journal entry, like every turn. The resident's commit is deniable; the town's signed
chain is the non-repudiable record. The `deskRequest`'s required `nonce` is journaled in the
entry. Without it, the entry CID of a low-entropy act ("move 7 to 41") could be confirmed by guessing.

**The digest** is `online.fg-goose.gsb.digest/<rev>`, beside `entry/<rev>` in the signed tree, one per height. Its
value is computed by a host op from the state at that height and is never revised. It begins at the next carry and
covers the whole carried journal, every height from the first, not just the heights after the carry.

| field | when present |
| --- | --- |
| `height`, `entry` (cid-link), `at` (clock minute), `principal` (DID, or the stored principal where none maps), `status` (`admitted` / `refused` / …), `via` (`post` / `record` / `xrpc` / `desk` / `root`) | always |
| `object`, `act` | when the host's public projection shows them (`inPublic`) |
| `clause` (the id only) | when the clause's law is public |
| `withheld` | the names of the fields left out |

Never text, fields, trace, offers, intent or the clause's reading (a reading interpolates state: "{to} is not
here"). The read policy, never the channel, decides what is public: a desk ring on a public
bell shows its object, and a fogged move shows only its principal and status.

It proves that no turn, refused or not, can be skipped: heights are consecutive and signed. A principal can hand
anyone its entry bytes (`getEntry`) to check against the signed CID, disclosing what the witness wrote.

**The principal is bound in every digest, desk-born ones included.** A desk hides what was asked, never who asked.
The digest therefore leaks who acted, when, and whether they were refused. That is the price of accountability, and
every other channel already makes it public.

## 5. Lexicons

All are under `online.fg-goose.gsb.*`, published like the rest (ATPROTO §5). No new authority is needed.

| NSID | kind | shape |
| --- | --- | --- |
| `desk` | space type | `key: any`, `name: "DelveTalk desk"`, `collections: [deskRequest, draft]` |
| `seat` | space type | `key: any`, `name: "DelveTalk seat"`, `collections: [seatView]` |
| `deskRequest` | record (resident, desk) | `request` without `service`/`witness`; `mode` `act`/`plan`/`try`; required `nonce` (16–64 bytes, base32); `world?`, `calls`, `if?`, `createdAt` |
| `draft` | record (resident, desk) | `{name, source, createdAt}` |
| `deskAnswer` | record (town, desk) | `source` strongRef to the deskRequest; `view`: `defs#answerView` or `#previewView` (the caller's projection) |
| `seatView` | record (town, seat), key `literal:self` | `{object, version, height, view}`: `world-derived` under the audience |
| `digest` | record (town, signed tree) | §4 |

A web client writing desk requests would need `space:online.fg-goose.gsb.desk?authority=<town>&skey=<did>&action=create&action=read`
(P§OAuth scopes), which only a PDS that offers granular scopes can grant.

## 6. Dependencies and blockers

- **Residents' PDSes.** A desk works for any DID whose PDS implements spaces, wherever it is hosted. The plan
  assumes nothing about any particular PDS, pds.delve.town included. A resident whose PDS lacks spaces keeps every
  existing channel, and their turns, digests and seats work the same.
- **Host ops**: `space-admit`; per-height seat audience changes (with L3 `world-projection`); the digest op; a
  journaled request `nonce`.
- **Transport**: the `blake3` package, added to `deploy/requirements-transport.txt`; P-256 HTTP signatures (the curve
  already exists in `atproto/sign.py`); a space repo host (LtHash, HMAC commit, two-root CAR, oplog) for desks and
  seats.
- **The digest changes the signed tree**, so it starts at the next carry, as L3 does, and covers that carry's whole
  journal.
- **Alpha caveats** (`pds-spaces-alpha`), for the builder verbatim: no production use; no security review; no
  backups, destructive migrations; protocol, SDK and schemas not final; never point non-developers at it.

## 7. obend's path to ATproto-native

obend (`did:web:obend.fg-goose.online`) is an open town. Its residents arrive by key at `/enter` as
`guest:obend.fg-goose.online:<name>` and have no PDS. Hosted accounts are off, and there is no wildcard DNS. A desk
needs a DID with a spaces repo, and there are three ways to give an obend resident one:

| | cost | fit with no wildcard DNS and hosting off |
| --- | --- | --- |
| **A. Bring any spaces PDS** | Nothing beyond §3. The resident needs an account somewhere that has spaces, and must link it to their key once (the `link` remainder, ATPROTO §4). | Fits fully. |
| **B. obend runs a spaces PDS**: `pds.obend.fg-goose.online`, did:plc accounts, no handle subdomains | One A record and certificate; a TypeScript service to run, back up and moderate, holding each account's signing key. Each arrival publishes a permanent did:plc operation. Handles under obend would need per-name DNS, so accounts go without (`handle.invalid`) unless the resident brings a domain. No relay crawlers. Test accounts only until the spaces release. | No wildcard. `hosted_accounts` stays false: these are PDS accounts, not DelveTalk's derived did:web repos. |
| **C. A town-held desk by API** | Least work: the town authors records for the guest. | Fits, but it is the `dt_agent_` channel renamed: no resident key or repo, not ATproto-native. Rejected. |

**Recommendation: A now, then B.** The town's desk code serves both, since A and B differ only in where the PDS runs.
In B, `/enter` provisions an account at arrival and hands the resident its rotation key, so they can leave
(credible exit). From then on, an obend resident's principal is their did:plc. Existing `guest:` principals keep
their journal identity, and nothing merges without a link.

**Flags for ember:**
- B makes obend an account host again, for a different reason than the one behind turning `hosted_accounts` off. It
  reverses no decision, but it is a new custody and moderation commitment.
- Any handle under `obend.fg-goose.online` per resident would reverse the no-wildcard decision. B avoids that.
- did:plc registration is public and permanent, unlike a guest name, which lives only in our journal.

## 8. Staged plan (on ember's go)

| # | Stage | Done when |
| --- | --- | --- |
| 1 | hbox: alpha PDS, local PLC, two test accounts, a scratch town on a test TLS hostname; desk inbound only | A's `deskRequest` gives exactly one entry; re-notify, restart and a second sync give none. B writing in A's desk gives no turn. A commit under a wrong key gives no turn. B's `getSpaceCredential` for A's desk returns `UserNotAuthorized` from `space-admit`. A desk `try` writes no entry (its preview is delivered from stage 2). The digest shows principal, status and `via: desk`, and no text |
| 2 | one game room on hbox: a fogged hexboard or a hand of cards; desk answers and seat views from the town's space repo | Two players finish a game by desk. Each seat credential is refused to the other player. Every move's digest withholds hidden fields. Deleting every space and replaying the journal reproduces each state CID |
| 3 | live desks on gsb and obend for any resident with a spaces PDS (the owner's deploy) | One real resident's desk request is answered with no post and no public `answer`, and its digest is in the town's signed tree |
| 4 | obend's PDS (§7), after the spaces release | An obend arrival gets a did:plc account with no new DNS name; their first desk request runs under that DID; they hold a rotation key and can move away |
