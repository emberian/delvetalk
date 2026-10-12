# Lexicons: `online.fg-goose.gsb.*`

The record types of DelveTalk's read-only repository (`docs/REPO.md`). Each record is a host reply
carried verbatim with `$type` set to its collection's NSID; the lexicon describes that reply, it does
not reshape it. Files sit at `online/fg-goose/gsb/<name>.json`, `defs.main` a `record`.

| Collection | Record key | Record `cid` | Host op (get / list) | Journal fields (FOUNDATION section 2 table) |
| --- | --- | --- | --- | --- |
| `online.fg-goose.gsb.entry` | the rev (a TID) | the record's own | `getRecord` / `listRecords` by height; the only collection in the signed MST | `height`, `hash` as a link: every reader's projection |
| `online.fg-goose.gsb.receipt` | slug, or the CID | `hash` | `world-resolve` (slug), `world-entry` (CID) / `world-entries` | the entry: `height`, `previous` and `hash` (chain links), `identity`, `turn`, `roots [{object, version}]`, `outcome`; a public refusal is `{class, root, reason?}` |
| `online.fg-goose.gsb.object` | `<object, / as ~>.<version>` | `stateCid` | `world-object` / `world-objects` then `world-object` | `pin` (content name: `created.pin`, `creates[].pin`, `reprograms[].newPin`), `library.pin`, the state named by `writes[].cid` or a created seed |
| `online.fg-goose.gsb.source` | the module CID | the module CID | `world-source` / `world-sources` | `sources[].cid` with its text, compile inputs' `{name, cid}` |
| `online.fg-goose.gsb.publication` | the publication id | the retaining entry's `hash` | (list only) `world-publications` | `publishes [{id, object, page, section, text}]` (id: derived) |
| `online.fg-goose.gsb.grant` | the grant id | the installing entry's `hash` | (list only) `world-grants` | `grants [{id, grantor, holder, to, object, method, until}]`, `revokes [id]` (ids: derived) |
| `online.fg-goose.gsb.law` | `<object, / as ~>.<clause>` | none | (list only) `laws` of `world-object` | `created.law`, `amendments [{object, old, new}]`; readings from the package (`law NAME "reading": EXPR`) |
| `online.fg-goose.gsb.card` | the object id, `/` as `~` | the record's own | `place`: `world-view`, `world-card`, `world-render`, `world-wants` (transport/mirror.py) / `world-objects` | none: a rendering, written to the PDS by `mirror` and answered here alike |
| `online.fg-goose.gsb.page` | the page's name | the record's own | the library's `pages` (`world-view`) | none: the library's state |
| `online.fg-goose.gsb.index` | `self` | the record's own | `world-objects`, the library, `world-status` | none |

Every key is in record-key syntax. An object id maps to a key by writing each `/` as `~` and appending
`.` and the version (`garden/bell/1` v2: `garden~bell~1.2`); it reads back by the last dot and `~` to `/`.
The host creates ids only in `[A-Za-z0-9._:/-]`, so every object has a key. Slugs and CIDs (entries, modules, publication and grant ids) are keys as they are.

What the table does not carry: request digests (`request`, `turnRequest`), checkpoint names
(`blocks[].cid`, `activity.checkpoint`) and `sends[].id` appear only inside a whole receipt, read by the
identity's own principal; there is no collection for checkpoints or pending sends.

CIDs inside records are strings (`format: cid`), as the journal stores them, not DAG-CBOR links
(tag 42): an entry's canonical bytes, and so its CID, are the journal's own. The exception is
`online.fg-goose.gsb.entry`, the signed repository's record, which the transport builds: its `entry` is a link.

## Acting and sessions (docs/ATPROTO.md)

| NSID | Type | Where | Public? |
| --- | --- | --- | --- |
| `online.fg-goose.gsb.defs` | defs | call, pin, moved, outcome, receipt, version, trace, answerView | n/a |
| `online.fg-goose.gsb.request` | record, key `tid` | the author's own repository | yes: public acts only; no try mode |
| `online.fg-goose.gsb.answer` | record, key `<did>.<rkey>` | the world's signed repository, mirrored to the posting account | yes |
| `online.fg-goose.gsb.paint` | record, key `<object, / as ~>.<version>` | façade and posting account, outside the signed tree | yes |
| `online.fg-goose.gsb.act`, `.try`, `.plan` | procedure | `/xrpc/` under inter-service auth (`aud` `did:web:gsb.fg-goose.online#delvetalk`) | the response is the caller's; an act's public projection becomes an `answer`; a try's never does |
| `online.fg-goose.gsb.getEntry` | query, CAR out | service auth; the entry's principal only | no |
| `online.fg-goose.gsb.openSession`, `.getSession`, `.listSessionRecords` | procedure, queries | service auth; the holder and named readers | no: returned, never written |

Authority: the NSIDs belong to whoever controls `gsb.fg-goose.online`, which the owner does; publication is
`_lexicon.gsb.fg-goose.online` TXT pointing at the posting account `ember.delve.town`
(`did:plc:6amo7col5h4ciq2gpm5eur7b`) and `com.atproto.lexicon.schema/<nsid>` records there (docs/ATPROTO.md §5).
