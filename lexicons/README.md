# Lexicons: `online.fg-goose.gsb.*`

Public records and per-reader queries for DelveTalk (`docs/REPO.md`), at
`online/fg-goose/gsb/<name>.json`. Each public record has `$type` and a CID hashing its value.
Host projection values are untagged replies. Live card/page/index/answer projections use the mirror's
tagged posting-record schemas. `getProjection` contains the host definitions, live schema references and
one shared envelope; `listProjections` references it. `kind` selects the value's required fields.

| Record schema | Key | Repository or live source |
| --- | --- | --- |
| `online.fg-goose.gsb.entry` | rev (TID) | height and entry hash as a link; the signed MST's one collection |
| `online.fg-goose.gsb.card` | object id, `/` as `~` | posting account record; live public projection from `mirror.card_record` |
| `online.fg-goose.gsb.page` | page name | posting account record; live public library projection |
| `online.fg-goose.gsb.index` | `self` | posting account record; live manifest projection with height and card versions; never names a head |
| `online.fg-goose.gsb.answer` | `<did>.<rkey>` or `xrpc.<iss>.<intent hash>` | posting account record; live bridge/front answer projection with request strongRef or XRPC provenance |
| `online.fg-goose.gsb.checkpoint` | `self` | mirror's `{did, rev, commit, height}` from the signed front before host reads; posting account only, never the did:web façade or signed tree |

| Projection kind | Key | `of` | Host source |
| --- | --- | --- | --- |
| `receipt` | slug or entry CID | entry hash | world-resolve/world-entry/world-entries |
| `object` | `<id, / as ~>.<version>` | stateCid | world-object, world-objects |
| `source` | module CID | module CID | world-source/world-sources |
| `publication` | publication id | retaining entry hash | world-publications |
| `grant` | grant id | installing entry hash | world-grants |
| `law` | `<id, / as ~>.<clause>` | absent | world-object.laws |
| `card` | object id, `/` as `~` | absent | public mirror renderer |
| `page` | page name | absent | public library pages, shelf order |
| `index` | `self` | absent | public mirror manifest |
| `answer` | answer key | absent | public bridge/front answer files |

`getProjection?kind&key&cid?` returns `{kind, key, of?, value, signed?}`. `of` is the CID of the thing
projected, not of `value`; `cid` filters it. `listProjections?kind&limit&cursor&reverse` returns
`{projections: [...], cursor?}`. Host values have no `$type`; live kinds retain their posting-record `$type`.
Host queries read under the front's authenticated principal (PUBLIC anonymously); live kinds always read
as PUBLIC and confer no world repository membership. A receipt's `signed` points to the signed `entry/<rev>`
record when present in the current tree; that is the path `sync.getRecord` proves.

Object ids map to keys by `/` → `~`, then a dot and version or clause. The host creates ids only in
`[A-Za-z0-9._:/-]`. A slug, CID, publication or grant id is a key as it stands. Activity checkpoints, request
digests and pending sends appear only inside an entry when the host lets its principal see it whole;
they have no collections. CIDs inside host replies are strings, as the journal stores them. The signed
entry record's `entry` is a DAG-CBOR link; the journal block keeps its own bytes without `$type`.

World strongRef targets use actual signed MST paths (`entry` today). Live card/page/index/answer targets
must name actual records in the posting account. Checkpoint and index describe source provenance without
proving world membership. Book and paint must retain cited versions under immutable versioned keys when built.

## Acting and sessions (docs/ATPROTO.md)

| NSID | Type | Where | Public? |
| --- | --- | --- | --- |
| `online.fg-goose.gsb.defs` | defs | call, planCall, pin, moved, outcome, receipt, version, trace, answerView, previewView | n/a |
| `online.fg-goose.gsb.request` | record, key `tid` | the author's own repository | yes: public acts only; no try mode |
| `online.fg-goose.gsb.answer` | record schema, request or XRPC key | public files projected by the front, written as records by the mirror; world signed paths planned in L3 | yes |
| `online.fg-goose.gsb.paint` | planned record, key `<object, / as ~>.<version>` | posting account, outside the world signed tree | yes |
| `online.fg-goose.gsb.act`, `.try`, `.plan` | procedure (built, L5) | POST `/xrpc/` under service auth (bare service DID or `#delvetalk` audience) | the response is the caller's; a durable-world act's public projection becomes an `answer`; scratch turns and previews write no answer |
| `online.fg-goose.gsb.getEntry` | query, CAR out (built, L5) | service auth; the entry's principal only; one entry block rooted at its CID | no |
| `online.fg-goose.gsb.openSession`, `.getSession`, `.listSessionRecords` | procedure, queries (built, L6) | method-bound service auth; the holder is `iss`, judged by the host | no: returned, never written |

Authority: the owner controls `gsb.fg-goose.online`. The live, verified `_lexicon.gsb.fg-goose.online` TXT is
`"did=did:plc:6amo7col5h4ciq2gpm5eur7b"`, naming the posting account `ember.delve.town`.
`python3 -m transport lexicons` reads every schema file fresh, in NSID order, and prints the TXT check command,
canonical JSON lines `{collection, rkey, cid, bytes}`, then `{count, did}`; `bytes` is the DAG-CBOR block length.
It exits 2, reads no credentials, writes no ledger and opens no socket. Each publication value preserves the
complete document and adds `$type: "com.atproto.lexicon.schema"`; `id` equals the NSID record key.
The owner chooses when to add `--authorized` with `--state DIR` or `DELVETALK_STATE`. The credential session must
match `lexicon_authority` (default the TXT's DID) before any putRecord in its own repo. The account-wide ledger
`<state>/lexicons/<URL-encoded authority DID>.json` records successful value digests and skips unchanged values.
Publication never deletes: a removed file stays published. No service starts publication, the mirror or request
poller (docs/ATPROTO.md §5, docs/POSTING.md).

`act` and `try` take one untagged `defs#call`, exactly `{spell}` or `{object, verb, fields?}`;
`plan` takes 1..8 `defs#planCall` spells. The shared wire judge enforces exclusive call forms and
fields as a JSON object. Lexicon v1 forbids named union definitions. Spell/intent byte and pin/count
budgets are validated at ingress. `answerView` and `previewView` have distinct `$type` and outcome
schemas; previews declare no receipt. Procedure output unions are closed. `cardCid` hashes the exact
offered text as a DAG-CBOR string, including any trailing newline, independently of a repository card.
`answer.source` is a required closed union of `answer#request {request: strongRef}` and
`answer#provenance {iss, intent}`. The bridge and front use one anonymous projection and writer;
previews are response-only. Tests validate both source variants and the separate response shapes.

Sessions use `scratch/<name>`, relative to `iss`, with expiry in home-world clock minutes.
`openSession {name, from?}` shares the HTTP `world-scratch` path; `getSession` returns
`{session, status, expires}`. `listSessionRecords` serves `.card` and `.entry` values as
`{records: [{key, cid, value}], cursor?}` (nested `sessionRecord` by ref), limit 1..100/default 50.
Cards include card-rendering REPL objects; entry records contain height and entry CID link. No at-uri
or signed membership exists. No checkpoint collection is served. Unknown/expired scratch errors are
fixed `RecordNotFound` responses. Reopening an expired name creates a new scratch. Named readers and
separate read/write/share/publish permissions need the host-owned op and L6 completion check in ATPROTO.
`tests/test_lexicons.py` validates session samples, required status/expiry and record fields; runtime
session tests validate actual responses and record values. Responses never enter public answer files.
