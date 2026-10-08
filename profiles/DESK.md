# An ordinary source desk

A source desk is an ordinary `delvetalk-local-v1` object. Its source is
[`protocols/source-desk/protocol.json`](../protocols/source-desk/protocol.json).
There is no special source-desk admission case in the host. Participants submit
exact source, an explicit syntax version, separately authored scenarios, a target
object identity, and a complete migration state. Those remain data in the world.
A trusted compiler worker publishes an immutable build artifact and a compilation
result through an ordinary command. An adopter separately asks the current law
to release the compiled program and atomically reprogram its target.

The four stages are visible through ordinary object roots:

```
empty --submit--> pending --compiled--> ready --adopt--> ready
                         \--failed--> failed
```

Submission and completion are each one-shot. A ready object retains its source,
compiler identity, artifact identity, lowered protocol and migration. `adopt`
records the last principal who released those values; it does **not** set an
`adopted` flag. A caller could invoke that ordinary command alone. Actual target
replacement is established by the atomic transaction receipt and current target
root, not by a desk label.

## Local API and commands

Build `delvetalk-transactions` and `delvetalk-world` first. Spween proposals also
need the pinned Rust bridge. The reusable API is `scripts/desk.py`:

```python
desk = Desk(database, artifact_store, profile="transactions")
created = desk.create(candidate_id, principal, intent, law)
submitted = desk.submit(candidate_id, principal, intent, exact_root,
                        syntax, source_bytes, scenarios_bytes,
                        complete_migration_state, target_id)
compiled = desk.check(candidate_id, compiler_principal, intent, pending_root)
adopted = desk.adopt(candidate_id, target_id, adopter_principal, intent,
                     ready_root, exact_target_root)
current = desk.inspect(candidate_id)
```

The operator selects an allowlisted host with `profile=` or CLI `--profile`.
The default is `transactions`; `compiled` enables the source-package profile.
Candidate validation, all scenarios, compilation-result admission and adoption
use that selected host. Proposal text cannot choose or increase its runtime.
The retained attempt pins the selected profile and its full source/binary closure.

CLI equivalents are `create`, `submit`, `check`, `adopt` and `inspect`:

```sh
python3 scripts/desk.py --database /tmp/world.json --artifacts /tmp/desk-artifacts \
  create --object proposal:1 --principal owner --intent make-proposal-1 --law law.json
python3 scripts/desk.py --database /tmp/world.json --artifacts /tmp/desk-artifacts \
  inspect --object proposal:1 > /tmp/empty-root.json
python3 scripts/desk.py --database /tmp/world.json --artifacts /tmp/desk-artifacts \
  submit --object proposal:1 --principal author --intent submit-1 \
  --expected-root /tmp/empty-root.json --syntax protocol-json@1 \
  --source protocols/counter/protocol.json --scenarios protocols/counter/scenarios.json \
  --migration migration.json --target room:1
```

`migration.json` is an explicit complete state object, for example `{"count":41}`.
Inspect again to save the pending root, then `check --object proposal:1
--principal compiler --intent compile-1 --expected-root pending-root.json`.
For adoption provide `--object proposal:1 --target room:1 --principal reviewer
--intent adopt-1 --expected-root ready-root.json --target-root room-root.json`.
All commands also take the same `--database` and `--artifacts` options. The target
must already exist. An existing program is never silently reset to its `initial`
state; migration is caller-authored data. State semantics remain the target
program's concern.

A practical scoped law for the candidate is:

```json
{"profile":"delvetalk-scoped-law-v1",
 "invoke":{"submit":["author"],"compiled":["compiler"],"failed":["compiler"],"adopt":["reviewer"]},
 "reprogram":[],"law":["owner"]}
```

The target independently grants `reprogram` to `reviewer`. Compiling a program
provides no target authority, and the compiler is never impersonated as an
adopter. Law owners can revise these rules, including deliberate lockout.
Principal strings remain local assertions: filesystem/CLI access is trusted,
not authenticated by these names. A deliberately broad legacy list law grants
all listed principals the legacy operations; use scoped laws for role separation.

## Why adoption is atomic

The CLI sends the ordinary transaction request:

```json
{"op":"transaction","principal":"reviewer","intent":"adopt-1",
 "reads":{"proposal:1":"<exact ready root>","room:1":"<exact target root>"},
 "calls":[
   {"object":"proposal:1","command":"adopt","input":{"target":"room:1"}},
   {"op":"reprogram","object":"room:1","inputFrom":0}
 ]}
```

The desk's Lean-interpreted command checks readiness and the stored target, then
returns exactly `{"protocol": storedProtocol, "state": storedMigration}`.
The reprogram operation consumes that exact result. There is no second caller
argument from which to substitute another program. Lean checks both initial
roots, each current law, the compiled program schema and the complete migration
record; all effects commit or refuse together. A late denial leaves the desk's
release record unchanged. Every request has a stable `(principal, intent)`:
retrying an identical adoption retrieves its retained receipt even after later
root/law changes. Reusing the identity for different inputs refuses.

The submitted migration is **not bound to a target revision**. The adopter must
review it against the exact target root they supply. A target change before
commit refuses; an authorized adopter may deliberately supply a newer root and
apply the same complete migration. Neither compilation tests nor source hashes
prove that this migration preserves application invariants. A caller already
authorized to reprogram can use that operation directly; the desk is a workflow,
not a hidden veto or a new source of authority.

## Compiler custody and diagnostics

The worker reuses `scripts/propose.py`, the explicit syntax registry, and the same
Lean admission fixture. It runs in a separate local process group with a 45-second
wall limit, a 30-second per-process CPU limit, and an 8 MiB per-file limit. A timed
out, cancelled or failed process group is killed and its direct child reaped. Source is never executed as Python, shell or Rust;
only reviewed adapters and the host binaries execute. These bounds do not create
an operating-system security sandbox or a complete memory bound.

Both successful and failed builds are stored by SHA-256 of exact canonical
artifact bytes under `builds/`. Each binds the observed candidate root. Successful
artifacts retain the full proposal report, exact source and adapter/host evidence;
failures retain diagnostics. Worker transport failures/timeouts become explicit
failed build diagnostics. The world's `compiled`/`failed` command still checks
the original pending root and the caller's current command authority. Stale
compilations cannot complete a changed candidate.

`attempts/` stores the immutable compiler-produced request before attempting its
world transition. This is custody for uncertain replies: a retry reuses the same
artifact and request instead of rerunning a possibly changed compiler. It is not
a second proposal database. The world alone owns proposal status and terminal
success/refusal receipts. A retry reads an exact retained receipt before checking
current runtime pins; it never reruns completed work under a new engine. A pending
attempt refuses changed or missing runtime pins before admission. Pending compiler
attempts need their artifact directory; completed exact receipts remain readable
even when the compiler artifact is unavailable. Artifact hashes detect substitution, not dishonesty by a trusted
compiler. Keep compiler command grants narrow.

For Spween, the worker wraps the already translated bundle using
`scene/room.py` without recompiling it. The room wrapper binds exact source and
AST into the adopted protocol's `roomArtifact` metadata. Its content-addressed
artifact is saved under `rooms/`; the ready desk exposes `roomArtifact` as that
artifact ID. After adoption a room view can load this ID and inspect the target's
actual root. JSON protocols carry no room artifact.

The host's existing 64 KiB request and 16 MiB frame limits still apply, including
exact roots and compiled protocols in adoption requests. Oversized transport
requests produce no semantic receipt; compiler result publication may therefore
need a smaller proposal. This prototype does not introduce references that
silently evade those limits. Source desks are world objects now; replacing the
external compiler service with a Bend implementation is a later compatible
producer of the same bounded result commands.

`python3 conformance/test_desk.py` covers the complete lifecycle, lost-reply
compiler/adoption retries, failed compilation, scoped roles, late rollback,
stale roots, retained timeout diagnostics and source-bound Spween room rendering.
