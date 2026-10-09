# Bounded current catalogue

`catalogue-page` is a native read-only query with exactly `op`, `principal`,
`limit` and `cursor`. Limit is 1–64. Initial cursor is null; continuation uses
exactly `{after,sequence,head}` returned by the receiver. Any custody revision
change, including a refused admission, rejects continuation as stale. Consumers
must explicitly restart listing rather than combine revisions.

The result is `{objects,nextCursor,sequence,head}`. Rows contain exact `object`
identity and `version`, plus a `name` preview of at most 256 Unicode characters
and an explicit `nameTruncated` flag. The receiver applies current `readObject`
to each selected identity. Full roots, protocols, state and admission history are
not returned; object inspection and atomic retained-root capture remain separate
queries. Pages reserve cursor and envelope bytes within a 60 KiB budget and
enforce a final 64 KiB response limit; an individual identity that cannot fit
refuses explicitly. Pages stop at either the row limit or the byte budget.

File custody uses receipt count and a null head. Resident custody uses its
committed sequence and journal head without expanding history. The current
implementation traverses the current object map to find the page; it does not
claim constant-time pagination or a history-independent file parser. File
read-only transport creates no lock, candidate or rewritten snapshot.
