# Reconstructible admission history

**History replays retained admissions through trusted local Lean.** Python
handles custody/hashes. No network access or implicit build occurs.
Full export is a trusted-custodian operation, not a participant disclosure API.
Mixed-private worlds cannot publish a full replay bundle without disclosing those
private admissions. Participant history uses [native acquisition](READS.md),
which omits whole inaccessible admissions and makes no full-replay claim.

```sh
python3 scripts/history.py export /PRIVATE/world.json /PRIVATE/history-001 \
  --profile compiled --journals /PRIVATE/clerk/requests
python3 scripts/history.py verify /PRIVATE/history-001 \
  --genesis KNOWN_GENESIS_SHA256 --head EXPECTED_HEAD_SHA256 \
  --output /PRIVATE/reconstructed-world.json
```

Run `make build` for the source host first. Destinations must
be new; import fsyncs and publishes under lock without clobbering. Failed export
directories are unusable until verified. Obtain genesis/head through a trusted
channel: self-consistent hashes authenticate neither authors nor external events.

`manifest.json` contains `format,genesis,entries,head,worldSha256,inlineReprogram`;
`blobs/` address exact bytes. Genesis pins empty world and one replay edition's
binary/source/helper/configuration/platform closure. Entries bind
`index,previous,request,reply,worldSha256,artifacts,id`. Transactions have one
commit, including refusals. Replay compares every receipt and complete world,
requires one new admission per entry and checks final state. Inspections,
duplicate deliveries and changed-request intent collisions are absent.

IDs hash canonical JSON excluding `id`: sorted keys, ordered arrays, exact
Unicode/decimals, compact separators, no duplicate members/nonfinite numbers.
Numeric spelling equivalence is not promised. Trusted head detects truncation.

Default `--runtime-policy exact` requires local matching pins and executes only
the local binary. Explicit `same-sources` permits binary/platform differences
while matching every other dependency and reproducing all results; original
binary provenance remains. Neither proves compilation correctness, original
per-event runtime, or portable bootstrap; runtime libraries/compiler sources are
outside custody.

`--journals` selects matching admissions; journals may disclose private operational
details. `--attachments mapping.json` maps request digests to file-path arrays.
Missing dependencies fail; names never become import destinations. Reprogramming
requires matching lowering/room provenance. `--inline-reprogram` permits missing
surface source, but never missing `roomArtifact`. Every committed transaction
programming step is checked, including overwritten candidates; `inputFrom`
candidates come from Lean receipts. Binding checks do not rerun compilers.

Generated children are reconstructed from the retained receiving factory and
exact input; they need no fictional separately authored source. Room-bearing
children still require complete matching room artifacts. Allocation receipts
retain each original creation root separately from final transaction roots, so
even an allocated-then-reprogrammed room retains its content obligation. Older
receipts lacking that trace refuse export of this ambiguous case. Every child
participates in full-world replay, whether or not an inhabited index names it.

Extend with export flags `--prefix-bundle OLD --prefix-genesis GENESIS
--prefix-head OLD_HEAD`; verification also takes `--base-head OLD_HEAD`.
Export replays and preserves exact prefix entries/artifacts under the origin
runtime. Shorter/conflicting snapshots refuse. Without prefix preservation,
changed attachments create alternate annotation history. No delivery evidence
or second live journal is implied.

[Wire/custody implementation](../scripts/history.py);
[runtime closure](../scripts/runtime_profile.py).
Check: `python3 conformance/test_history.py`; optional Spween/compiled cases
require prebuilt binaries.

[Continuation packages](CONTINUATION.md) join verified roots, history and source custody.
