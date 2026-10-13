# Lexicons: `online.fg-goose.gsb.*`

Public records and per-reader queries for DelveTalk (`docs/REPO.md`), at
`online/fg-goose/gsb/<name>.json`. Each public record has `$type` and a CID hashing its value.
Projection values are the host's untagged replies. `getProjection` contains their six definitions and
one shared envelope; `listProjections` references that envelope. `kind` selects the value's required fields.

| Served record | Key | Source |
| --- | --- | --- |
| `online.fg-goose.gsb.entry` | rev (TID) | height and entry hash as a link; the signed MST's one collection |
| `online.fg-goose.gsb.card` | object id, `/` as `~` | `mirror.card_record`: public exact card, wants, doors |
| `online.fg-goose.gsb.page` | page name | public library pages |
| `online.fg-goose.gsb.index` | `self` | journal-derived public manifest with height and card versions; never names a head |
| `online.fg-goose.gsb.answer` | `<did>.<rkey>` or `xrpc.<iss>.<intent hash>` | bridge/front anonymous answer, required tagged request strongRef or XRPC provenance |
| `online.fg-goose.gsb.checkpoint` | `self` | mirror's `{did, rev, commit, height}` from the signed front before host reads; posting account only, never the did:web façade or signed tree |

| Projection kind | Key | `of` | Host source |
| --- | --- | --- | --- |
| `receipt` | slug or entry CID | entry hash | world-resolve/world-entry/world-entries |
| `object` | `<id, / as ~>.<version>` | stateCid | world-object, world-objects |
| `source` | module CID | module CID | world-source/world-sources |
| `publication` | publication id | retaining entry hash | world-publications |
| `grant` | grant id | installing entry hash | world-grants |
| `law` | `<id, / as ~>.<clause>` | absent | world-object.laws |

`getProjection?kind&key&cid?` returns `{kind, key, of?, value, signed?}`. `of` is the CID of the thing
projected, not of `value`; `cid` filters it. `listProjections?kind&limit&cursor&reverse` returns
`{projections: [...], cursor?}`. No `$type` is added to a projection value. Queries read under the front's
authenticated principal (PUBLIC anonymously). A receipt's `signed` points to the signed `entry/<rev>`
record when present in the current tree; that is the path `sync.getRecord` proves.

Object ids map to keys by `/` → `~`, then a dot and version or clause. The host creates ids only in
`[A-Za-z0-9._:/-]`. A slug, CID, publication or grant id is a key as it stands. Activity checkpoints, request
digests and pending sends appear only inside an entry when the host lets its principal see it whole;
they have no collections. CIDs inside host replies are strings, as the journal stores them. The signed
entry record's `entry` is a DAG-CBOR link; the journal block keeps its own bytes without `$type`.

Journal-derived strongRef targets use the canonical did:web URI (ATPROTO §1). The mirror's checkpoint + index map
a copy by collection and unchanged rkey; equal CIDs verify the bytes against that repository, without retargeting
the reference. Book and paint must retain their cited versions under immutable versioned keys when built.

## Acting and sessions (docs/ATPROTO.md)

| NSID | Type | Where | Public? |
| --- | --- | --- | --- |
| `online.fg-goose.gsb.defs` | defs | call, planCall, pin, moved, outcome, receipt, version, trace, answerView, previewView | n/a |
| `online.fg-goose.gsb.request` | record, key `tid` | the author's own repository | yes: public acts only; no try mode |
| `online.fg-goose.gsb.answer` | record, request or XRPC key | public bridge/front answer files, served by the front and copied by the mirror; signed paths planned in L3 | yes |
| `online.fg-goose.gsb.paint` | record, key `<object, / as ~>.<version>` | façade and posting account, outside the signed tree | yes |
| `online.fg-goose.gsb.act`, `.try`, `.plan` | procedure (built, L5) | POST `/xrpc/` under service auth (bare service DID or `#delvetalk` audience) | the response is the caller's; a durable-world act's public projection becomes an `answer`; scratch turns and previews write no answer |
| `online.fg-goose.gsb.getEntry` | query, CAR out (built, L5) | service auth; the entry's principal only; one entry block rooted at its CID | no |
| `online.fg-goose.gsb.openSession`, `.getSession`, `.listSessionRecords` | procedure, queries (built, L6) | method-bound service auth; the holder is `iss`, judged by the host | no: returned, never written |

Authority: the NSIDs belong to whoever controls `gsb.fg-goose.online`, which the owner does; publication is
`_lexicon.gsb.fg-goose.online` TXT pointing at the posting account `ember.delve.town`
(`did:plc:6amo7col5h4ciq2gpm5eur7b`) and `com.atproto.lexicon.schema/<nsid>` records there (docs/ATPROTO.md §5).

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
