# atproto Spaces: private channels to the witness

DelveTalk uses Spaces for **inbound private intent** and **outbound per-audience views**. It never uses them for
authority. The town's DID is the space authority. Each resident gets a *desk*, a space of one in which they write
spell requests that nobody else reads. Each audience of a hidden-state object gets a *seat*, a space the town writes
that audience's view into. Admission, law and receipts stay in the Lean host. Every turn, whichever channel it came
by, gets a public **digest** in the signed tree.

Why it matters:
- A request becomes a turn without a post, a mention or a public `answer`. That ends the ping lists and
  ledgerslop, and it gives a PDS resident `try` by record.
- Hidden game state (fog, hands) reaches the right players as syncable records. Its truth stays in the journal.
- The digest makes "anyone can verify a refusal" true; the public tree holds only CIDs and heights today.

Design only; nothing is built. Sources: proposal 0016 (P§) and atproto branch `permissioned-data` @ 5b95b2f2
(PR 5187), lexicons `lexicons/com/atproto/{space,simplespace}/*.json`.

## 1. Spaces, as specified

- A space is `(authority DID, type NSID, skey)`, addressed `at://{authority}/space/{type}/{skey}`, and its records
  are `…/{author}/{collection}/{rkey}` (P§Addressing). The `skey` has rkey syntax, so a DID is a valid skey.
- Each author keeps one space repo per space on their own PDS. A commit is a signed LtHash set digest (BLAKE3 XOF).
  The signature covers only a nonce, so a leaked commit is **deniable** (P§Commit signature).
- To read, an app takes `com.atproto.space.getDelegationToken` from the user's PDS to the authority's
  `getSpaceCredential`. The authority alone decides, and the protocol carries no member list (P§Access control).
  A credential lasts ≤60 minutes (default 10), bound to a P-256 key by RFC 9421; `notifyCredentialRevoked` revokes by `jti`.
- Read access is all or nothing at the space boundary (P§Read access).
- Sync has no relay: `listRepoOps`, `getRepo` and `getLatestCommit` on each author's host. The writer's PDS sends
  `notifyWrite` to the authority's `#atproto_space_host`, signed with service auth whose `iss` is the writer
  (`packages/pds/src/space-notifications.ts`). `listRepos` is the writer set.
- The authority resolves its `#atproto_space` key (falling back to `#atproto`) and its `#atproto_space_host`
  service (falling back to `#atproto_pds`); did:web works (`auth-verifier.ts` `resolveSpaceKey`). A PDS accepts a
  write to a foreign authority's space without asking it.
- **Access control, not confidentiality.** PDSes and admitted apps read everything (P§Introduction).

## 2. The mapping

**Authority.** The town's `did:web:gsb.fg-goose.online` is a bespoke space host. Its DID document gains
`#atproto_space` (a dedicated key beside the repository key) and `#atproto_space_host` (the town's origin), so space
URIs name the town as entry URIs do. The alternative, a town account on a spaces PDS whose `managingAppPolicy` calls
`com.atproto.simplespace.checkUserAccess` on `#delvetalk`, is less code on an alpha account (§8 Q2).

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
| the answer to a desk request | town's repo in that desk (the caller's projection); PDS-only residents get it by proxied `getProjection` |
| fog of war, a hand of cards | host state under read policy; its view is copied into each audience's seat |
| workshop drafts | the author's desk as a `draft`, read only when a request cites it by strongRef |
| the mending drawer | **never a space**: direct service-auth XRPC only (§3) |
| scratch sessions | unchanged: holder-only XRPC, no repository |

No shared room space holds requests: read is all or nothing, so an opponent would read a move before it was judged.

## 3. The boundary

A space admits **reading**. Only the host admits **acting**. Transport custody lives in `transport/spaces.py`, a
sibling of `requests.py`. Python verifies, carries and mints. It decides nothing:

1. `POST com.atproto.space.notifyWrite` is verified like service auth (`lxm` notifyWrite, `aud` =
   `<town>#atproto_space_host`; `serviceauth.py` gains this audience for that `lxm` alone). It is a hint that
   queues `(did, space, rev)`. A bounded `getLatestCommit` sweep of known desks covers lost notifications.
2. The syncer reads the desk at the PDS the resident's DID document names, with a self-minted credential and
   `Atproto-Space-Audience: <did>`: `listRepoOps?since`, or `getRepo` when the oplog is gone. It verifies the commit
   signature (`#atproto`), the MAC and its own LtHash fold, never trusting TLS.
3. Each new `deskRequest` takes the path a public request takes: shared `judged` framing, then `world-reach`, then
   `world-turn`, with identity `(author DID, space at-uri)`. An at-uri is consumed once, under its first verified
   CID, and requests created before the desk's `since` are never run.
4. `getSpaceCredential` checks the delegation JWT (`typ atproto-space-delegation+jwt`, `sub` the space, `aud` the
   space host) and its RFC 9421 signature. It then asks the host `space-admit {space, principal, access}` and mints
   only on `admit`. Seat audiences come from the host as well.

Nothing in a space bypasses admission: a record's presence grants nothing; membership is no principal, grant or
clause; another DID's write in your desk is never read; desk turns meet the same law and pace as posted ones.

**Never in a space**, because spaces are readable by the PDS operator, its admins and every admitted app:
- credentials, keys, tokens, invitation codes, bearer nonces
- security reports (the drawer)
- another person's private data
- anything that must stay hidden from some reader of that space

During the alpha, also nothing one would not lose or show a stranger ("do not upload sensitive information"). A
space is transport: losing one loses only requests not yet synced.

## 4. Receipts and the public digest

**A space-born turn** is one journal entry, like every turn. The resident's commit is deniable; the town's signed
chain is the non-repudiable record. The `deskRequest`'s required `nonce` is journaled in the
entry. Without it, the entry CID of a low-entropy act ("move 7 to 41") could be confirmed by guessing.

**The digest** is `online.fg-goose.gsb.digest/<rev>`, beside `entry/<rev>` in the signed tree, one per height. Its
value is computed by a host op from the state at that height and is never revised:

| field | when present |
| --- | --- |
| `height`, `entry` (cid-link), `at` (clock minute), `principal` (DID), `status` (`admitted` / `refused` / …), `via` (`post` / `record` / `xrpc` / `desk` / `root`) | always |
| `object`, `act` | when the host's public projection shows them (`inPublic`) |
| `clause` (the id only) | when the clause's law is public |
| `withheld` | the names of the fields left out |

Never text, fields, trace, offers, intent or the clause's reading (a reading interpolates state: "{to} is not
here"). The read policy, never the channel, decides what is public: a desk ring on a public
bell shows its object, and a fogged move shows only its principal and status.

What this proves: heights are consecutive and signed, so no turn (and no refusal) can be skipped. A principal can
hand anyone its entry bytes (`getEntry`), and they check against the signed CID. That is selective disclosure by
the actor of what the witness wrote.

A space-born digest leaks who acted, when, and whether refused: the price of accountability, already public for
every other channel (§8 Q1).

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

`/play/` would need `space:online.fg-goose.gsb.desk?authority=<town>&skey=<did>&action=create&action=read` (P§OAuth
scopes); pds.delve.town offers no granular scopes today.

## 6. Dependencies and blockers

- **pds.delve.town** (0.5.34) must run spaces before any delve resident has a desk. The alpha image
  `ghcr.io/bluesky-social/atproto:pds-spaces-alpha` is not a production option, so in practice this waits for the
  general release and for delve's operators to adopt it.
- **obend residents have no PDS** (`hosted_accounts = false`). Their web and `dt_agent_` channel is already private,
  and desks add nothing for them.
- **Host ops**: `space-admit`; per-height seat audience changes (with L3 `world-projection`); the digest op; a
  journaled request `nonce`.
- **Transport**: BLAKE3, which neither the stdlib nor `cryptography` provides; P-256 HTTP signatures (the curve
  already exists in `atproto/sign.py`); a space repo host (LtHash, HMAC commit, two-root CAR, oplog) for desks and
  seats.
- **The digest changes the signed tree**, so it starts with a key epoch or a carry, like L3.
- **Alpha caveats**, for the builder verbatim: no production use; no security review; no backups and destructive
  migrations; schemas, SDK and protocol not final; the hosted alpha PDS is deleted at the end; never point
  non-developers at it. Builds land on Thursdays (announcements thread on discourse.atmosphere.community).

## 7. Staged plan (on ember's go)

| # | Stage | Done when |
| --- | --- | --- |
| 1 | hbox: the alpha PDS and a local PLC in compose, two test accounts, a scratch town on a test TLS hostname, desk inbound only | A's `deskRequest` gives exactly one entry; re-notify, restart and a second sync give none. B writing in A's desk gives no turn. A commit under a wrong key gives no turn. B's `getSpaceCredential` for A's desk returns `UserNotAuthorized` from `space-admit`. A desk `try` writes no entry (its preview is delivered from stage 2). The digest shows principal, status and `via: desk`, and no text |
| 2 | one game room on hbox: a fogged hexboard or a hand of cards; desk answers and seat views from the town's space repo | Two players finish a game by desk. Each seat credential is refused to the other player. Every move's digest withholds hidden fields. Deleting every space and replaying the journal reproduces each state CID |
| 3 | live desks for delve residents (needs §6 and the owner's deploy) | One real resident's desk request is answered with no post and no public `answer`, and its digest is in the town's signed tree |

## 8. Open questions for ember, ranked

1. Does a desk-born digest name its `principal`? Default yes; without it, accountability is lost.
2. Should the authority be the town's did:web as a bespoke host (recommended), or a town account on a spaces PDS
   with `checkUserAccess`?
3. Should the digest also cover the pre-digest journal at the next carry, or only heights after it?
4. BLAKE3: the `blake3` wheel in `requirements-transport.txt`, or a small vendored pure-Python XOF?
5. Who asks delve's operators about spaces, and when? Their PDS gates stage 3.
