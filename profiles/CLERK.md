# Live clerk

**The clerk admits explicit public requests through Lean into a durable local world.** It runs on demand, publishes nothing, and accepts invocation, reprogramming and bounded [transactions](TRANSACTION-INTAKE.md). Remote authors cannot call bootstrap `create`, change law or load adapters; authorized factory commands support [governed allocation](ALLOCATION.md).

Build `delvetalk-world`; keep custody outside Git:

```sh
STATE="$HOME/claude_state/delvetalk-clerk"
python3 scripts/clerk.py --state "$STATE" bootstrap \
  --object counter:live --protocol protocols/counter/protocol.json \
  --repository AUTHOR_DID --law AUTHOR_DID
python3 scripts/clerk.py --state "$STATE" snapshot counter:live > /tmp/root.json
python3 scripts/clerk.py --state "$STATE" receive \
  at://AUTHOR_DID/org.delvetalk.request/KEY --cid RECORD_CID
```

`--repository` enrolls transport; `--law` grants initial Lean authority. Repeat either; empty law is permitted. `--law-file` supplies complete scoped law instead. Exact bootstrap retries recover the create receipt; different bootstrap cannot overwrite custody. [Management](MANAGEMENT.md) adds reviewed objects.

## Attach an existing workspace

`attach` enrolls an existing generic workspace without creating another object
or changing its world, law or receipts:

```sh
python3 scripts/clerk.py --state /private/path/receiver attach \
  --workspace /private/path/shared-world --runtime-profile transactions \
  --genesis EXACT_GENESIS_SHA256 --seed-head EXACT_SEED_HEAD_SHA256 \
  --expected-roots /private/path/selected-roots.json --repository AUTHOR_DID
```

The roots file maps selected object IDs to **complete current root objects**,
for example `{"entry:one": FULL_ROOT, "desk:one": FULL_ROOT}`. Its keys select
initial remote enrollment. Select genesis and seed head from workspace
initialization evidence; the command requires its `manifest.json`, `seed.json`
and `seed-history/`, not arbitrary world JSON. The Python API is
`Clerk.attach(workspace, expected_roots, repositories, expected_genesis=...,
expected_seed_head=..., runtime_profile=...)` with the last three arguments
keyword-only.

Attachment verifies namespace, runtime and anchors, replays the exact seed
through the selected Lean host, and checks that current history extends that
seed prefix. Later admissions are replayed in temporary custody; the full world
and selected roots must reconstruct exactly. Runtime pins must remain stable.
No external HTTP or workspace world write occurs. Repository and object
enrollment confer no authority.

Configuration binds the canonical absolute `world.json` path, with no copy or
symlink. Restarted receiving, snapshots, management and upgrades use that path
and its stable world lock; lock order remains clerk, then world. A different
existing clerk, local world or orphaned journal cannot be overwritten or
rebound. Retargeting the bound path through a symlink is refused.

The only commit is atomic clerk configuration replacement after verification.
Interruption before it permits repeating verification. A lost reply after it
is recovered by repeating the original selection: `already-attached` returns
historical attachment evidence even after later admissions advance the world.
It neither claims those original roots are current nor resets later enrollment.
Different selections refuse rather than silently rebinding custody.

The selected `transactions` or `compiled` runtime remains explicit for all
operations, including single-object requests. Default `world` preserves legacy
world/transaction dispatch. Runtime changes still require quiescent upgrade.
[Attachment tests](../conformance/test_clerk_attach.py) cover actual Lean replay,
fake-PDS receiving, unchanged law, restart/retry, mismatched anchors/roots,
forged state, interruption and canonical-path custody.

## Wire

An author's own `org.delvetalk.request` record contains exactly:

```json
{"$type":"org.delvetalk.request","profile":"delvetalk-live-v1","requestJson":"..."}
```

The string preserves arbitrary JSON numbers. Its invocation payload is:

```json
{"object":"counter:live","command":"add","input":{"amount":1},"expected":{}}
```

Replace `{}` with the complete snapshot root. Optional `op:"invoke"` is accepted. Reprogramming uses exactly `{op:"reprogram",object,protocol,state,expected}`: lowered protocol and complete replacement state. Lean validates and installs both atomically, preserves law and increments version. No implicit migration runs.

Factory invocations may add `absent:["factory/child"]` (at most 16 identities).
Unregistered absences must name direct children of registered objects. Only
committed children become remotely addressable; enrollment grants no child authority.

Either operation may replace `expected` with `expectedRootRef:{uri,cid}`. The reference must name `org.delvetalk.root` in custodian repository `did:plc:oq2mrkwsuts7dqbkqqm2ntiz`. The clerk verifies PDS identity, exact URI/CID, envelope/digest, object and version, then retains the resolved record. Lean still checks currentness; a historical root can yield a terminal stale-root refusal.

Social requests use `town.delve.feed.post` with this LF-delimited grammar:

````text
delvetalk-request v1
```delvetalk-request
{"object":"counter:live","command":"add","input":{"amount":1},"expected":{}}
```
````

The first line is exact; optional whitespace precedes one tagged fence. Trailing plain text is allowed; preceding prose or additional backticks are refused. Duplicate members, unknown fields, nonfinite numbers and caller-supplied principal/intent are rejected.

## Trust and recovery

The pinned `https://pds.delve.town` supplies public `describeRepo`/`getRecord` observations. Repository DID, DID-document PDS service and returned URI/CID must match. Only `did:plc` identities are supported; redirects and arbitrary endpoints are refused. This trusts HTTPS PDS testimony, local custody and operator; it does not verify CAR/MST proofs or reconstruct CIDs. Responses cap at 1 MiB; requests, including expanded roots and derived identity, at 64 KiB. Invalid/oversized transport reserves no attempt.

Principal is the repository DID; intent is `delve:` plus the entire URI. Before admission, a lock-protected, fsynced journal binds that URI to one CID and exact derived request. Lean checks current law, exact preimage and semantics, retaining either commit or refusal under `(principal,intent)`. Enrollment confers no authority.

Retry the **same URI/CID** after uncertainty. Pending recovery replays retained bytes under original implementation pins; completed retries return saved receipts without refetching. Editing a record cannot replace an attempt. A revised attempt needs a fresh key and root. Receipts retain source identity, exact request, Lean reply and source/binary profiles. Pins identify what ran; they are not a refinement proof. Local fsync custody is not a distributed transaction.

## Upgrade

```sh
python3 scripts/clerk.py --state "$STATE" profile
python3 scripts/clerk.py --state "$STATE" upgrade --from-profile EXACT_OLD_SHA256
```

New admissions refuse changed pins. Recover every pending remote/management request with its old implementation before upgrading. Upgrade holds clerk/world locks, records old/new profiles and unchanged world digest, and leaves world/history intact. Exact upgrade retries are idempotent; completed historical receipts keep original pins.

Bootstrap or quiescent upgrade accepts `--runtime-profile transactions` or `compiled`; omission preserves the default/configured runtime. Only the operator selects it. Compiled source execution stays inside Lean; journals bind the selected admission host. Returning explicitly to `world` makes installed compiled expressions refuse there.

Publication remains separate and paused; see [receipts](RECEIPTS.md). An outbox intent is not delivery.

[Implementation](../scripts/clerk.py), [runtime closure](../scripts/runtime_profile.py), [Lean/mock-PDS tests](../conformance/test_clerk.py), [compiled tests](../conformance/test_clerk_compiled.py).

## Operator interpretation of ordinary posts

Participants may speak naturally. The local service operator can supply a named,
explicit interpretation through `receive --interpretation FILE`, retaining the
GET-verified original post separately from the exact derived request. This shares
the existing URI/CID binding and Lean admission path; it does not auto-parse prose
or grant interpreter authority. Clarification creates no semantic attempt, while
an uncertain attempted action retains its identity. See
[MANUAL-INTAKE.md](MANUAL-INTAKE.md) for the internal tool input, provenance and
Town response integration. Participants are not asked to author these JSON files.
