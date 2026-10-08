# Reconstructible local admission history

`scripts/history.py` exports a local world into an immutable directory containing
`manifest.json` and content-addressed `blobs/`. It verifies and optionally imports
the history by executing the existing Lean admission binary. Python performs
custody, hashing and comparisons; it does not decide admission or implement a
second protocol evaluator. These commands perform no network operations.

```sh
python3 scripts/history.py export /PRIVATE/world.json /PRIVATE/history-001 \
  --profile transactions --journals /PRIVATE/clerk/requests
python3 scripts/history.py verify /PRIVATE/history-001 \
  --genesis KNOWN_GENESIS_SHA256 --head EXPECTED_HEAD_SHA256 \
  --output /PRIVATE/reconstructed-world.json
```

Build the selected `delvetalk-world`, `delvetalk-transactions`, or optional
`delvetalk-compiled` executable first.
Export and verification never compile. The output database must not exist;
publication into local custody uses a complete fsynced temporary file and an
atomic no-clobber link under the normal database lock. Existing custody is never
replaced. An export destination must also be new. Failed exports may leave an
incomplete directory for inspection; without a valid manifest and successful
verification it is not a usable history bundle.

## Trust and exact scope

Supply a genesis and head obtained through a channel you trust. Hashes identify
content and detect substitutions relative to those anchors; they do not
authenticate an author, grant authority, prove global consensus or establish
that an event occurred externally. Principals remain assertions of this local
host profile. An attacker can invent a completely different, internally valid
history and compute its hashes. The checker cannot decide whose history to trust.

The genesis contains an explicit empty world and a pinned replay profile: selected
Lean executable, its source closure, transport source, build configuration and
platform. The shared `scripts/runtime_profile.py` defines that complete reviewed
closure, including `TransactionsCore` and, for `compiled`, the source frontend,
package and demand-machine dependencies. Those exact artifacts are included as
blobs. Default verification compares all pins with the caller's local installation
and invokes only that matching local executable. It never executes downloaded
or bundled executable bytes.
Platform runtime libraries and the installed Lean compiler's own sources are
outside this bundle; the executable is a host-specific replay artifact, not a
portable or independently verified compiler bootstrap.

One replay edition applies to the entire v1 bundle. Reconstructing an existing
database establishes that its retained results reproduce under this pinned
edition. It does **not** establish which binary originally produced each result.
Original clerk and management source profiles remain in supplied journals.
Preserving multiple original runtime editions with per-entry replay is a future
profile, not something this exporter infers from current files.

### Explicit cross-platform source-matched replay

`verify --runtime-policy same-sources` is an explicit alternative to the default
`exact` policy. It requires identical profile name, complete dependency-path set,
and every source, toolchain, helper and configuration hash. Only the selected
executable hash and platform may differ. The original executable blob must still
exist and match its recorded hash; it is retained as provenance and never run.
The caller's trusted local engine replays every admission and must reproduce
every receipt and world digest. There is no automatic fallback to this policy.

The report includes `runtimePolicy`, the complete `localRuntime` identity, its
digest, the origin runtime digest and a `proofScope` of either
`exact-artifact-replay` or `source-matched-local-replay`. Neither scope proves
that an executable was built from the recorded source or establishes compiler
adequacy. Source-matched replay permits a Linux agent to test a Darwin-origin
history using its separately trusted build. Import remains no-clobber. Prefix
export currently requires the exact origin runtime; cross-platform verification
does not silently rewrite the genesis into a different runtime edition.

## Wire and commit boundary

The manifest has exactly these fields:

```text
format = delvetalk-history-v1
genesis = { id, profile: {name, platform, files: {path: SHA256}}, world }
entries = [ { index, previous, request, reply, worldSha256, artifacts, id }, ... ]
head = last entry id, or genesis id for an empty history
worldSha256 = final complete custody database digest
inlineReprogram = explicit acceptance of missing original program-source artifacts
```

Canonical JSON sorts object keys, preserves array order and exact Unicode, uses
compact separators, rejects duplicate members and nonfinite numbers, and retains
decimal values without conversion through binary floating point. IDs are SHA256
of this UTF-8 encoding with the object's `id` field omitted. Blob IDs hash exact
bytes. Decimal spellings in a retained database are preserved by the encoding;
the format does not promise equivalence of every numeric spelling.

Each entry binds the preceding commit, complete request, retained result, exact
complete post-admission world and all source artifact references. A transaction
touching several objects has **one entry and one commit ID** covering its complete
result and resulting world. Ordered indices and previous hashes reject gaps,
reordering and substitutions. The externally expected head detects truncation.

Verification starts at empty genesis, sends each request to the selected Lean
profile through `world.exchange`, compares the complete receipt and world hash,
and checks that exactly one new retained admission was added. It also checks the
final world. Refused admissions are retained and replayed. The exporter refuses
a database whose object state cannot be reconstructed from its receipt sequence.

The source database retains first admission attempts, including semantic
refusals. It does not retain inspections, repeated delivery of identical intents,
or attempts to reuse an existing intent with different content. These events
cannot be recovered from `world.json` and are not invented in the export.

## Sources and artifact custody

Every request already retains its complete inline protocol and exact input or
state. Original surface syntax, lowering provenance and room presentation are
additional artifacts. `--journals` includes only files with requests matching
retained admissions. Management journals retain exact source, state source and
lowering artifacts; clerk journals retain original public records. They may also
contain local operational details: select disclosure deliberately. Exporting a
local directory does not publish it.

For other files, supply `--attachments mapping.json`, where each key is
`history.digest(request)` and each value is an array of exact file paths. Unknown
request digests and missing files fail export. Artifact references record the
basename or declared dependency path and exact blob digest; import never follows
those names as filesystem destinations.

Known lowering envelopes cause their declared adapter, registry and compiler
dependencies to be copied into the bundle and checked against their recorded
hashes. Room artifacts also include a declared parser binary when present.
Missing or changed dependencies fail instead of silently substituting today's
files. Verification reads those artifacts from the bundle, not from an ambient
source-artifact store, and never executes their source.

Reprogram requests normally require a validated matching lowering or room
artifact, either directly attached or retained inside a journal. An empty
`artifact` field or a raw public request record does not discharge this
requirement. Lowering validation checks the exact source digest, lowered-value
digest, translation identity, pinned registry entries and dependency closure;
it does not rerun the claimed adapter or prove compiler correctness.
`--inline-reprogram` explicitly permits reconstruction when original surface
syntax is unavailable; it does not manufacture that provenance. A
protocol with `roomArtifact` always requires the complete matching room artifact,
even with this flag. Room validation checks its source/content bindings and
requires exact equality with the installed protocol. It does not certify that a
compiler implements its claimed language.

These checks also cover direct reprogram calls inside transactions. For
`inputFrom` programming in a committed transaction, the installed candidate is
read from the earlier result in Lean's retained receipt. History never evaluates
the candidate-producing program in Python. A refused transaction installed no
candidate and retains no intermediate results to reconstruct. Every committed
programming step is checked, including one subsequently overwritten by another
step in the same transaction.

## Comparing an extension

Preserve a previously accepted bundle explicitly when exporting a later snapshot:

```sh
python3 scripts/history.py export /PRIVATE/world.json /PRIVATE/history-002 \
  --prefix-bundle /PRIVATE/history-001 \
  --prefix-genesis KNOWN_GENESIS_SHA256 --prefix-head PREVIOUSLY_ACCEPTED_HEAD
```

Both prefix anchors are required. Export independently replays the prefix,
requires its exact genesis/runtime and provenance policy, and compares every
prefix request and receipt with the new custody snapshot. It copies verified
referenced blobs and preserves the original entries and artifact references
exactly. Catalog growth, later equivalent programs and now-missing ambient
source paths cannot relabel old admissions. New attachment selection applies
only after the accepted prefix. A shorter or conflicting snapshot is refused.

Verify the new expected head and additionally supply
`--base-head PREVIOUSLY_ACCEPTED_HEAD`. The checker requires that exact previous
head as a prefix. Without an explicit prefix bundle, changing earlier source
attachments also changes commit IDs; that is an alternate history annotation,
not an append-only extension. Generic Python callers use `prefix_bundle`,
`expected_prefix_genesis` and `expected_prefix_head` on `export_history`.

This prototype exports an append-only *logical history* from custody snapshots.
It does not add a second write-ahead journal to the live host, publish records,
or infer that an outbox intent was delivered. Host atomicity remains owned by
the selected Lean admission and `world.exchange` custody boundary.

```sh
python3 conformance/test_history.py
```

Tests use real Lean admission for multiobject commits and cover reconstruction,
no-clobber import, modified receipts even after rehashing, order/gap/truncation,
known-base mismatch, exact runtime pins, missing artifacts, source-less program
changes and unreconstructible state. The room integration case runs when the
optional Spween bridge is already built; the compiled-profile case likewise
requires its existing binary. Neither case builds implicitly.
