# Offline continuation

**Prepare a world for another reader without publishing it.** The package joins
exact root snapshots to the existing replay history and original source custody.
Lean reconstructs every retained admission, including refusals.

```sh
python3 scripts/continuation.py bootstrap /PRIVATE/cafe /PRIVATE/continuation
python3 scripts/continuation.py verify /PRIVATE/continuation \
  --genesis KNOWN_GENESIS --head EXPECTED_HEAD
```

For a clerk, first export with `history.py export --journals` and the selected
runtime profile. Then use `continuation.py prepare HISTORY DESTINATION --genesis
KNOWN_GENESIS --head EXPECTED_HEAD`. Both prepare and verify accept `--base-head`
to require a known earlier admission. Bootstrap export preserves its retained
prefix through the existing source catalog; inline-only reprogramming refuses.

Open `index.html` for object names and versions. `index.json` contains exact roots,
history anchors, and all clerk receipts found in the anchored source artifacts.
Their request/reply must match replay. Existing worker code prepares immutable
root snapshots and admission heads from those receipts. Removing roots, receipts
or prepared records fails verification. Hashes live in the details panel.

The unchanged `history/` directory works with `history.py verify` and, for inhabited
bootstrap worlds, `bootstrap.py restore`. Its manifest and dependency bytes remain
intact. A caller supplies trusted genesis/head; the package never authenticates
source authors or grants authority.

Preparation copies to private staging, replays, fsyncs, and exposes the complete
directory atomically without replacement. Retry the same call after interruption
or a lost reply. An existing destination must replay and match the same contents;
changed destinations refuse. Later admissions need a new destination.

No credentials, network requests, publication, builds, or live admissions occur.
Bootstrap preparation retains its normal local history checkpoint. History may
contain private source and request journals: preparation is not publication consent.

Check: `python3 conformance/test_continuation.py` using prebuilt host binaries.
