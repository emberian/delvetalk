# Authenticated local receiving

The clerk authenticates a public repository record, retains its exact request,
and submits it to Lean. Lean decides current authority, exact preimages and the
result. The clerk supports invocation, reprogramming, law revision and bounded
transactions. It publishes nothing. For participant-facing replies, start with
[the textual interaction guide](../docs/TEXTUAL-INTERACTION.md).

## Enroll a workspace

Create a [workspace](WORKSPACE.md) first. For resident custody, start its explicit
[receiver daemon](RESIDENT-STORE.md) and keep it running while using the clerk:

```sh
python3 scripts/resident_server.py "/path/to/workspace/world.json"
```

Run subsequent commands in another terminal. Stop the daemon with Ctrl-C when
finished; restart it on the same configured path to recover durable custody.
File-backed workspaces remain supported and need no daemon. A resident
`world.json` is a logical binding, not a JSON file to read or copy. There is no
automatic daemon startup or fallback to file custody.

Set `AUTHOR_DID`, `GENESIS` and `SEED_HEAD` to the selected repository and workspace
anchors. The roots file must map enrolled object IDs to complete current roots.

```sh
python3 scripts/clerk.py --state "/path/to/clerk" attach \
  --workspace "/path/to/workspace" --runtime-profile compiled \
  --genesis "$GENESIS" --seed-head "$SEED_HEAD" \
  --expected-roots "/path/to/selected-roots.json" --repository "$AUTHOR_DID"
python3 scripts/clerk.py --state "/path/to/clerk" snapshot "counter"
python3 scripts/clerk.py --state "/path/to/clerk" receive \
  "at://$AUTHOR_DID/org.delvetalk.request/request-key" --cid "$RECORD_CID"
```

Attachment checks namespace, runtime, seed anchors and selected roots, then
reconstructs the captured admissions through Lean in independent custody. It
writes clerk configuration without changing the workspace. Repeating the exact
selection returns its retained attachment; a different selection refuses.
Repository and object enrollment grant no command authority.

## Identity, requests and recovery

The pinned `https://pds.delve.town` supplies GET-only repository observations.
Repository DID, DID-document service, URI and CID must match. This trusts HTTPS
PDS testimony; it does not verify repository proofs. Responses are bounded at
1 MiB and derived native requests at 64 KiB. Caller-supplied principal or intent,
unknown fields, duplicate members and nonfinite numbers are rejected.

A machine record has type `org.delvetalk.request`, profile `delvetalk-live-v1`
and a `requestJson` string. An invocation contains `object`, `command`, `input`
and the complete `expected` root. Reprogramming supplies `op:"reprogram"`,
`object`, `protocol`, `state`, `expected`; law revision supplies `op:"law"`,
`object`, `law`, `expected`. [Transactions](TRANSACTION-INTAKE.md), captured
[Town cards](TOWN.md) and [manual interpretation](MANUAL-INTAKE.md) use the same
receiving boundary. Interpretation retains the original post and a separate
operator decision; prose does not supply authority.

Principal comes from the authenticated repository DID; intent is `delve:` plus
the full source URI. Before admission, a durable journal binds that URI to one
CID and exact request. Retry the **same URI/CID** after uncertainty. A saved
receipt returns immediately. Otherwise native exact receipt lookup runs before
current implementation-pin checks: a committed or refused admission can repair
a lost journal reply without executing again. If no receipt exists, changed
pins block execution. Editing a source record cannot replace the attempt.

Clerk operations serialize their own journals. Backend accessors own world
access: the resident daemon holds its SQLite writer lock, while file admissions
use their file lock. Snapshot export is explicit; ordinary resident receiving
uses indexed receipt lookup without expanding history.

## Change operator configuration

```sh
python3 scripts/clerk.py --state "/path/to/clerk" profile
python3 scripts/clerk.py --state "/path/to/clerk" upgrade --from-profile "$PROFILE_SHA256"
```

Resolve pending journals before upgrade. Upgrade records exact prior/new
profiles and the unchanged world snapshot digest. Completed receipts retain
original profiles; exact upgrade retries are idempotent. This does not migrate
a resident database to another native runtime; see [resident custody](RESIDENT-STORE.md).

[Implementation](../scripts/clerk.py) · [receiving tests](../conformance/test_clerk.py)
· [resident integration tests](../conformance/test_message_relay.py)
· [documentation map](../docs/INDEX.md)
