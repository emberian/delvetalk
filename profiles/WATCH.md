# Observe LiveDelveTalk

**Watch retains public observations; publication remains paused.** `livedelvetalk.delve.town` is a literal coordination label, not an account this tool resolves or creates. No credentials, posting, request parsing or admission occurs.

```sh
python3 scripts/watch.py --feed-pages 20 --search-pages 2
```

Each scan overlaps feed head, supplemental `livedelvetalk` search and anchor thread (depth 3, at most 200 nodes). Pages contain 50 posts; bounds 1–20, defaults 3/1. `--anchor` overrides the thread. Matching is case-insensitive literal text; contextual replies and previously observed posts survive label removal.

Reports include `new`, `changed`, exact URI/CID/content hash, retained files, coverage/cursors/truncation, errors and conflicting AppView versions. Partial sources preserve other observations. This trusts AppView; it cannot guarantee history completeness or independently verify CID/signatures. Absence never establishes deletion; metrics alone are not record changes.

Private state defaults to `~/claude_state/delvetalk/watch`; override with `--state`. Locked, atomic fsynced files retain history, `index.json` and `latest-report.json`. Repeated observations produce no delta; inconsistent caches do not establish CID ordering.

Exit: 0 success, 1 partial-source errors, 2 local/configuration failure; truncation alone succeeds. Scheduling belongs to callers: notify meaningful changes/actionable failures, stay quiet otherwise.

[Implementation](../scripts/watch.py), [deterministic coverage/retention tests](../conformance/test_watch.py).
