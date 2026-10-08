# Clerk operator enrollment, current law and programming

`scripts/manage.py` manages an existing [live clerk](CLERK.md) in a trusted local
state directory. It uses the existing Lean executable through `world.exchange`;
Python manages custody and transport only. It makes no network requests, reads
no credentials and publishes nothing.

Transport enrollment and semantic authority are independent:

- `register DID` allows the clerk to observe **new** request records from that
  repository. It grants no authority in Lean.
- `unregister DID` stops new observations. It does not revoke law, cancel a
  previously retained attempt, delete receipts or prevent historical replay.
- `law` submits a complete replacement law to Lean, under a supplied current
  authority principal and exact expected root. It does not change enrollment.
- `reprogram` submits a translated protocol and explicit complete replacement
  state under the same current authority and exact-root checks. It preserves law.

The local operator asserts `--principal`; this CLI does not authenticate that
identity. The trusted state directory already allows direct `world.py` custody.
The clerk's remote receiving path instead derives the principal from its pinned
HTTPS PDS repository observation. Neither enrolling a DID nor naming it as a
local principal overrides Lean's current-law check. V1 operator identities and
law members use `did:plc` identifiers. An authority principal need not itself be
enrolled for remote observation.

## Enroll, then grant authority

Use your clerk state path and actual DID values below. `--allow` lists the
**entire** replacement law, so retain each principal that should remain allowed.
The same law controls invocations and future management; there is no separate
owner role or rescue bypass.

```sh
STATE="$HOME/claude_state/delvetalk-clerk"
OPERATOR=did:plc:aaaaaaaaaaaaaaaaaaaaaaaa
AUTHOR=did:plc:bbbbbbbbbbbbbbbbbbbbbbbb
python3 scripts/manage.py --state "$STATE" register "$AUTHOR"
python3 scripts/clerk.py --state "$STATE" snapshot counter:live > /tmp/before-law.json
python3 scripts/manage.py --state "$STATE" law \
  --object counter:live --principal "$OPERATOR" --intent enroll-author-001 \
  --expected-root /tmp/before-law.json --allow "$OPERATOR" --allow "$AUTHOR"
```

The example DIDs are placeholders. `--expected-root` accepts either the complete
raw root JSON or an intact clerk snapshot envelope with matching object and
checksum. It never replaces a supplied preimage with a newer snapshot. A
concurrent commit can therefore produce a durable `stale read root` refusal.
Lean checks authorization before the preimage; a revoked principal receives
`unauthorized`, even with a stale preimage.

These are **two separate commits**, not a transaction across enrollment and
law. If enrollment succeeds and law fails, the author remains enrolled without
new authority. Inspect `status`, recover the law attempt if uncertain, then
choose a fresh intent and snapshot for a revised attempt or explicitly
`unregister` the author. No automatic rollback rewrites law or custody.

For revocation, replace law without the author, then independently unregister
its repository if desired. A law commit can succeed even if a later enrollment
change fails. `status` reports current enrollment and retained law-attempt
outcomes; use `clerk.py snapshot` to inspect current law.

## Install an explicitly selected program

An agent can prepare source and exercise it with the isolated
[proposal workflow](../protocols/PROPOSALS.md). Passing those scenarios does not
grant authority or install the proposal. An authorized local operator can select
that exact source, choose the complete replacement state, and request installation:

```sh
python3 scripts/clerk.py --state "$STATE" snapshot counter:live > /tmp/before-program.json
python3 scripts/manage.py --state "$STATE" reprogram \
  --object counter:live --principal "$OPERATOR" --intent install-welcome-001 \
  --expected-root /tmp/before-program.json \
  --source protocols/welcome-once/protocol.json --syntax protocol-json@1 \
  --state /tmp/welcome-state.json
```

In that example `/tmp/welcome-state.json` must explicitly contain
`{"welcome":null}` (or another complete state chosen by the operator). The first
`--state`, before the subcommand, selects clerk custody; the subcommand's
`--state` selects the replacement state file. No implicit migration expression
runs and the protocol's `initial` field does not reset existing state. An empty
object means deliberately empty state, not “retain the old state.”

Syntax is always explicit. `protocol-json@1`, `protocol-markdown@1` and the
reviewed `spween-scene-i64@1` lowering can supply executable protocols. A raw core
term or parse-only Spween source cannot. This uses the same `translate.py`
registry and adapters as proposals; Python selects the protocol from the
translation artifact, while Lean validates the protocol and complete state,
checks current law and the exact root, and atomically replaces protocol/state
with version incremented once. Object identity and law remain unchanged. New
remote requests run the newly installed commands; historical receipts still
describe the program and state used for their original attempts.

The private management journal retains exact UTF-8 source, syntax identity,
translation artifact, registry and adapter pins, lowered protocol, and exact
state-file text/hash. These provenance fields stay outside the Lean request,
whose fields are exactly `op`, `object`, `principal`, `intent`, `expected`,
`protocol`, and `state`. Receipt envelopes retain this program evidence too;
they are not public clerk-receipt envelopes and are not automatically published.
Source is limited to 512 KiB and the state file to 64 KiB. The complete derived
management request, including expected root, must fit the host's 64 KiB request
envelope; oversized encoded requests are refused before reserving an intent.

Retry the same command with the original inputs or use `resume` with its
principal and intent. Recovery submits the retained Lean request without
rerunning adapters or reading the original source files. Different source bytes,
syntax, state-file bytes, object or root cannot replace a bound attempt, even
when the new source would lower to the same protocol. Use a fresh intent for a
new attempt. Pending recovery requires the original management, clerk and
translation pins (including the Spween bridge executable when used). Completed
receipts remain readable even when those implementations later change.

## Recovery, refusal and deliberate lockout

Every law or reprogram command requires an explicit stable `--intent`. Its Lean
intent is `operator-law:` or `operator-reprogram:` followed by that value; local
management reserves the pair of asserted principal and supplied intent across
both operations. Reusing that pair with a different operation, object, preimage,
law or program input is rejected. A refusal is terminal just like a success: fix the
request with a fresh intent rather than changing the retained attempt.

The exact request and implementation profiles are atomically retained before
admission. If the process stops before returning a receipt, use:

```sh
python3 scripts/manage.py --state "$STATE" status
python3 scripts/manage.py --state "$STATE" resume \
  --principal "$OPERATOR" --intent enroll-author-001
```

`resume` replays the stored request and returns its retained receipt. It does
not reconstruct the request from current law, re-read a preimage file, or need
the original command-line arguments. After a world commit but before receipt
export, Lean's retained `(principal,intent)` receipt prevents another revision.
Completed receipts remain available after law changes, unenrollment and source
pin changes. CLI exit status is 0 for completion, 2 for a retained Lean refusal,
and 1 for a custody/transport error (argument parsing uses argparse's status 2).
Inspect the JSON reply to distinguish semantic outcome from CLI misuse.

An empty replacement is explicit, using `--empty-law` instead of `--allow`.
This deliberately removes **all** invocation and management authority for the
object. The command remains authorized only if its supplied principal belongs
to the prior current law. After it commits, no local operator command can grant
authority again under this profile. Enrollment changes do not rescue it; the
old successful receipt remains readable.

## Custody and pending attempts

Management holds the same stable `clerk.lock` as receiving and upgrading. Semantic
submission acquires the world lock through `world.exchange`, always after the
clerk lock. Enrollment atomically replaces only `repositories` in `clerk.json`,
retaining all other configuration fields. It does not write the world. Empty
transport enrollment is permitted. Repeating an already-satisfied enrollment
command is harmless.

Management journals live at `requests/management-<digest>.json`, separately named from
remote URI journals. This deliberately makes the existing clerk upgrade's
quiescence scan include uncertain management attempts. Management receipts retain the
clerk's implementation profile plus the SHA256 of `scripts/manage.py` as a
separate management profile; adding management does not silently repin the
existing clerk. A pending attempt must finish with both pinned implementations.
An edited management source cannot reinterpret an uncertain attempt. Completed
management receipts remain historical and can be read with newer source.

A remote request already retained before unenrollment remains bound to its
original URI, CID, principal and preimage. If it has not committed, its retry
still faces current Lean law and the exact root at admission. If it committed
before a later revocation, recovery returns that historical committed receipt.
Removing enrollment never erases either case. Management and receiving are
serialized; direct `world.py` callers also serialize admission on the world
lock, and a raced law request may correctly receive a stale-root refusal.

Run `python3 conformance/test_management.py` after building `delvetalk-world`.
The tests use a mock PDS and the actual Lean executable, covering enrollment
without authority, authorized law addition, retained receipts after revocation,
empty-law lockout, stable intents, interrupted receipt export, upgrade
quiescence, pending requests after unenrollment, current-law checks after
revocation, concurrent receiving, governed reprogramming, immutable source
binding, adapter-free recovery, and the operator CLI. This is local receiving
and custody evidence, not authentication of local operators or public delivery.
