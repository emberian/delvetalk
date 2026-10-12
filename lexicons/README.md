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
| `online.fg-goose.gsb.answer` | `<did>.<rkey>` | bridge's public answer to a request |
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
| `online.fg-goose.gsb.defs` | defs | call, pin, moved, outcome, receipt, version, trace, answerView | n/a |
| `online.fg-goose.gsb.request` | record, key `tid` | the author's own repository | yes: public acts only; no try mode |
| `online.fg-goose.gsb.answer` | record, key `<did>.<rkey>` | public bridge answer files, served by the front and copied by the mirror; signed paths planned in L3 | yes |
| `online.fg-goose.gsb.paint` | record, key `<object, / as ~>.<version>` | façade and posting account, outside the signed tree | yes |
| `online.fg-goose.gsb.act`, `.try`, `.plan` | procedure | `/xrpc/` under inter-service auth (`aud` `did:web:gsb.fg-goose.online#delvetalk`) | the response is the caller's; an act's public projection becomes an `answer`; a try's never does |
| `online.fg-goose.gsb.getEntry` | query, CAR out (L5) | service auth; the entry's principal only | no |
| `online.fg-goose.gsb.openSession`, `.getSession`, `.listSessionRecords` | procedure, queries | service auth; the holder and named readers | no: returned, never written |

Authority: the NSIDs belong to whoever controls `gsb.fg-goose.online`, which the owner does; publication is
`_lexicon.gsb.fg-goose.online` TXT pointing at the posting account `ember.delve.town`
(`did:plc:6amo7col5h4ciq2gpm5eur7b`) and `com.atproto.lexicon.schema/<nsid>` records there (docs/ATPROTO.md §5).
