# Lexicons: `town.delvetalk.*`

The record types of DelveTalk's read-only repository (`docs/REPO.md`). Each record is a host reply
carried verbatim with `$type` set to its collection's NSID; the lexicon describes that reply, it does
not reshape it. Files sit at `town/delvetalk/<name>.json`, `defs.main` a `record`.

| Collection | Record key | Record `cid` | Host op (get / list) | Journal fields (FOUNDATION section 2 table) |
| --- | --- | --- | --- | --- |
| `town.delvetalk.receipt` | slug, or the CID | `hash` | `world-resolve` (slug), `world-entry` (CID) / `world-entries` | the entry: `height`, `previous` and `hash` (chain links), `identity`, `turn`, `roots [{object, version}]`, `outcome`; a public refusal is `{class, root, reason?}` |
| `town.delvetalk.object` | `<object>/<version>` | `stateCid` | `world-object` / `world-objects` then `world-object` | `pin` (content name: `created.pin`, `creates[].pin`, `reprograms[].newPin`), `library.pin`, the state named by `writes[].cid` or a created seed |
| `town.delvetalk.source` | the module CID | the module CID | `world-source` / `world-sources` | `sources[].cid` with its text, compile inputs' `{name, cid}` |
| `town.delvetalk.publication` | the publication id | the retaining entry's `hash` | (list only) `world-publications` | `publishes [{id, object, page, section, text}]` (id: derived) |
| `town.delvetalk.grant` | the grant id | the installing entry's `hash` | (list only) `world-grants` | `grants [{id, grantor, holder, to, object, method, until}]`, `revokes [id]` (ids: derived) |
| `town.delvetalk.law` | `<object>/<clause>` | none | (list only) `laws` of `world-object` | `created.law`, `amendments [{object, old, new}]`; readings from the package (`law NAME "reading": EXPR`) |

What the table does not carry: request digests (`request`, `turnRequest`), checkpoint names
(`blocks[].cid`, `activity.checkpoint`) and `sends[].id` appear only inside a whole receipt, read by the
identity's own principal; there is no collection for checkpoints or pending sends.

CIDs inside records are strings (`format: cid`), as the journal stores them, not DAG-CBOR links
(tag 42): an entry's canonical bytes, and so its CID, are the journal's own.
