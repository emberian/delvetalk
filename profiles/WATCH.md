# Observe LiveDelveTalk

**Watch retains public observations; publication remains paused.** `livedelvetalk.delve.town` is a literal coordination label, not an account this tool resolves or creates. No credentials, posting, request parsing or admission occurs.

```sh
python3 scripts/watch.py --feed-pages 20 --search-pages 2
```

Each scan overlaps feed head, separate `livedelvetalk` and `#gsb` searches, and the anchor thread (depth 3, at most 200 nodes). Pages contain 50 posts; bounds 1–20, defaults 3 feed pages and 1 page per search. `--anchor` overrides the thread. Discovery is case-insensitive: either the literal label or the `#gsb` hashtag retains a feed observation. Returned search context is retained too: AppView search may return related text without the literal markers. Available parents and replies connected by record references are also retained regardless of page order; previously observed posts survive marker removal. Context absent from the fetched pages is not inferred.

The advertised fresh-session convention is **both** `@livedelvetalk.delve.town`
and `#gsb`. Reports mark that textual pair `summonCandidate`; this can include
quotes, discussion or instructions that are not requests. Welcome is a signpost,
not a captured world root. An operator reviews intent and context, selects a
configured source factory, and uses the receiving path to verify the original
URI/CID and repository author before any session creation. The watch never
parses/adopts an executable request or authenticates a principal. Other meaningful
intent can still be noticed manually; lacking the pair is not an admission rule.
Hosted worlds remain disposable previews; publication remains paused.

Reports include `new`, `changed`, exact URI/CID/content hash, retained files, coverage/cursors/truncation, errors and conflicting AppView versions. `newSelectionCounts` separates marked observations, search context and reply context; `summonCandidates` indexes only newly observed/changed paired-marker candidates. These aid triage without suppressing retained context. A broader scan can discover old discussion: newly retained does not mean newly posted. Partial sources preserve other observations. This trusts AppView; it cannot guarantee history completeness or independently verify CID/signatures. Absence never establishes deletion; metrics alone are not record changes.

Keep handled `(URI, CID, content hash)` identities and concise intent decisions in
private triage separately from the observation index. Repeated observations do
not justify repeated alerts or another session. A changed observation needs
review; its CID is an observed claim, not proof of authorship or custody.

Private state defaults to `~/claude_state/delvetalk/watch`; override with `--state`. Locked, atomic fsynced files retain history, `index.json` and `latest-report.json`. Repeated observations produce no delta; inconsistent caches do not establish CID ordering.

Exit: 0 success, 1 partial-source errors, 2 local/configuration failure; truncation alone succeeds. Scheduling belongs to callers: notify meaningful changes/actionable failures, stay quiet otherwise.

[Implementation](../scripts/watch.py), [deterministic coverage/retention tests](../conformance/test_watch.py).

## Private read archive

Every scan now retains the complete fetched public AppView responses in
`STATE/archive` (override with `--archive-state`). This includes unrelated feed
rows and the full returned anchor thread, not only the watch's selected posts.
`captures/<sha256>.json` identifies endpoint, parameters and raw response content;
overlapping identical captures share a file. Each scan has a separately retained
`manifests/<run-id>.json` with per-request progress, observed URI/CID/record hashes,
coverage, errors and byte/request bounds. The report names `archiveManifest`.
Existing observation identities, index and triage state keep their meaning.

Archive transport accepts only the watch's three public AppView GET endpoints.
It accepts no tokens or headers, stores no credentials, and records error classes
rather than transport messages. Captures are **observed AppView testimony**, not
independently verified CIDs, signatures, repository commits or proof of custody.
No incoming content executes or confers authority. Publication remains paused.

For a bounded historical feed crawl, use the same HTTP helper through:

```sh
python3 scripts/town_archive.py --pages 3
```

Default custody is `~/claude_state/delvetalk/watch/archive`; `--state` overrides it.
The separate `backfill.json` cursor advances only after a raw capture is durable.
Rerunning resumes it; a completed backfill performs no more requests. Continuous
watch scans always start at the head and do not consume this cursor. A crash leaves
an unfinished manifest; replay may repeat a page, safely deduplicated by capture
identity. Partial failure preserves prior pages and the next cursor. A cursor is
an AppView pagination hint, not a snapshot or completeness guarantee; late arrivals
and historical gaps remain possible. Keep dated bounds and thread truncation when
making claims about coverage.

Each run permits at most 20 backfill pages, or the configured feed pages plus
twice the per-search page bound plus one thread request, and at most 64 MiB of retained encoded captures. This bounds archive storage per
run, not the underlying HTTP helper’s response memory usage. A capture exceeding the byte
bound is explicitly unretained and the source reports failure. These are per-run
bounds, not a total disk quota. Nothing silently deletes historical captures,
manifests, observations or other sessions' files. Retention pruning and scheduling
require separate decisions. This is a private partial read mirror, not a PDS, town
server or automatic activity receiver.

[Archive implementation](../scripts/town_archive.py),
[restart/overlap/failure tests](../conformance/test_town_archive.py).
