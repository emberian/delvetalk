# Observing the LiveDelveTalk label

`livedelvetalk.delve.town` is an imaginary handle used as a coordination label.
`scripts/watch.py` observes literal text and the selected discussion thread. It
neither resolves nor creates an account for that label. It reads public AppView
records without credentials, posts nothing, and never parses requests or makes
admission decisions. A matching post is material for review, not authorization.

```sh
python3 scripts/watch.py --feed-pages 20 --search-pages 2
```

One invocation overlaps three sources:

- The town feed, starting at its current head, up to the selected page bound.
- Search for `livedelvetalk`, used as a supplement even when its index returns no
  matches found in the feed.
- The configured anchor thread, depth three, with at most 200 nodes. Replies
  count as discussion context even when they contain no label.

The literal match is case-insensitive `livedelvetalk.delve.town` anywhere in post
text. It does not rely on a mention facet or account lookup. Posts observed in a
previous scan are also retained when a later version removes the label. Each
feed/search request asks for 50 posts; bounds are 1–20 pages, defaulting to three
feed pages and one search page. `--anchor` overrides the default discussion URI.

The single JSON report contains `new` and `changed` post observations, exact
source URI/CID, record-content SHA256, text, source names and a retained-file
path. It also contains per-source `coverage`, continuation cursors, truncation
indicators and `errors`. Thread reply counts expose known omitted replies;
AppView may omit material without reporting it. Bounded scans cannot guarantee a
complete timeline, especially when feed activity exceeds a polling interval.
A source error preserves observations already collected and does not prevent the
other sources from being scanned. The CLI exits 1 for partial source errors,
2 for local/configuration failure, and 0 otherwise; truncation alone is not an
error.

State defaults to `~/claude_state/delvetalk/watch`, outside Git. `--state` selects
another private directory. Atomic, fsynced files retain exact JSON record values
under URI/CID/content-hash identities. `index.json` tracks observations;
`latest-report.json` retains the latest run. Each run starts at the feed head,
so overlap is deliberate. Repeated observations produce no new delta. Absence
never means deletion and never removes historical files. Changed content under
the same claimed CID is retained and reported, rather than trusted as immutable.
Simultaneously inconsistent versions from different AppView surfaces appear in
`conflicts`; an already-observed version is retained without inferring CID
ordering or oscillating between caches. Metrics outside the record do not create
content-change notifications. This is trusted AppView observation, not independent
CID/signature verification.

A scan lock serializes overlapping invocations. The module imports only the
existing public HTTP and durable save/lock helpers; it does not import the clerk
or participate in its semantic pins. Scheduling belongs to the caller. A monitor
should notify about meaningful new/changed observations or newly actionable
failures, and stay quiet while its observed state is unchanged.

`python3 conformance/test_watch.py` uses deterministic mocks only. It checks
feed hits despite empty search, contextual replies, repeated-scan deduplication,
CID/content changes, label removal, historical retention, page bounds, partial
failures, conflicting cache versions and explicit thread truncation.
