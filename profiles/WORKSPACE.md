# Independent builder workspaces

A workspace holds a world database, exact source artifacts, pinned receiving
runtime and entry index. Lean admits seed creations and subsequent actions.

Save `entry.json`:

```json
{"profile":"delvetalk-local-v1","name":"entry","initial":{"message":"Welcome"},
 "commands":{"write":{"require":[],"set":{"message":["input","message"]},
 "result":["state","message"],"outbox":[]}}}
```

Save `plan.json` beside it:

```json
{"title":"Our first world","entryObjects":["home"],"defaultObject":"home",
 "objects":[{"id":"home","syntax":"protocol-json@1","source":"entry.json","law":["builder"]}]}
```

With receiving binaries built:

```sh
python3 scripts/workspace.py init /tmp/our-world --plan plan.json --principal builder
python3 scripts/workspace.py inspect /tmp/our-world --object home --html
python3 scripts/portal.py /tmp/our-world
```

The default profile is `transactions`; select `--profile compiled` at creation
for compiled programs. Paths resolve relative to the plan. Syntax must lower to
a protocol or executable Spween bundle; parse-only source refuses.

Initialization translates sources, admits listed creations, renders entries and
exports history in staging, then publishes atomically without replacing an
existing destination. Failure publishes nothing. Laws are explicit; empty law
permits lockout. Creators receive no bypass. Principals remain local assertions.

## Manifest and public genesis

`manifest.json` records format `delvetalk-workspace-v1`, `worldId`, title,
`entryObjects`, `defaultObject`, exact runtime and genesis. Entries are distinct
seed IDs; the default must be an entry. Selection grants no authority or inspection
restriction. IDs never become filesystem paths. The index is anchored in the
first admission's artifact links; mutable index administration is not implemented.

`genesis.json` identifies the empty world under that runtime. `seed.json` records
the populated head and world hash; `seed-history/` retains its replay bundle.
Worlds sharing a runtime share empty genesis: trust **genesis and head together**.
Seeds copy no demonstration or private history.

Fresh `worldId` values are `urn:uuid:` namespaces; `--world-id`/`world_id=` can
supply one. Seed intents bind namespace and ordered index. Export/restore check
those admitted intents; rehashing metadata cannot relabel the world. Copies retain
identity; fork policy and automatic cross-world lookup are unspecified.

## Inspect, export and reconstruct

```sh
python3 scripts/workspace.py export /tmp/our-world /tmp/our-world-bundle
python3 scripts/workspace.py verify /tmp/our-world-bundle --genesis KNOWN_GENESIS --head KNOWN_HEAD
python3 scripts/workspace.py restore /tmp/our-world-bundle /tmp/another-custody \
  --genesis KNOWN_GENESIS --head KNOWN_HEAD
```

Supply trusted hashes; `--base-head` optionally requires a known prefix. Hashes
authenticate no author. Verification replays receipts and state hashes through
the matching trusted Lean runtime. Restore checks source custody and entries,
renders views, then publishes into an absent destination.

Inspection matches rooms by exact admitted protocol, evaluates admitted projections,
or displays raw state. Existing bootstrap demos and `continuation.py bootstrap`
share this generic export path.

## Shared APIs

[workspace.py](../scripts/workspace.py) defines `initialize` with explicit
`{id,syntax,source,law}` seeds (`source` is UTF-8 bytes), entry IDs and principal.
[bootstrap.py](../scripts/bootstrap.py) exposes `default_object`, `entry_objects`,
`world_id`, `bound_room_artifact`, and `inspect_view`. Legacy demos return no world ID.

Export retains referenced source/scenario blobs and original adapter dependencies
from every request, including pending/refused proposals. Restore recreates their
store before compilation. Large source cards can use immutable references; the
64 KiB receiving envelope and trusted-adapter requirement remain unchanged.

`export_bootstrap(..., extra_attachments={request_digest:[paths]})` attaches
explicit service evidence only to retained requests. It preserves historical
prefix links and never scans private state.

[Tests](../conformance/test_workspace.py) cover independent identity, seed rollback,
CLI plans, generic restoration/actions and pending source above 64 KiB after
original custody deletion. These are executed cases, not universal proofs.

Current workspace manifests bind `seedObjects`, the exact ordered seed object
IDs, alongside their namespace-bound creation intents. Restoration uses that
fixed extent to recreate `seed.json`, `seed-history/` and `genesis.json` with the
original seed head, even when later admissions exist. A restored workspace can
therefore attach a clerk and initialize an operator service using the original
anchors. Later creation requests cannot silently enlarge or rebase the seed.
Earlier private manifests without `seedObjects` remain inspectable and
reconstructable, but restoration reports `operatorEnrollmentReady: false` and
does not invent seed custody; operator enrollment remains unavailable until an
explicit compatible construction is supplied.

Command names are local to a protocol. Export recognizes compiler-result build
artifacts only for the exact source-desk protocol, so an unrelated object's
`compiled` or `failed` command does not acquire a hidden artifact-store obligation.
