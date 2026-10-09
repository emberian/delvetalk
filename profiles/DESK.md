# Source desk

**A desk stores proposals; atomic adoption installs their exact results.**
The [ordinary protocol](../protocols/source-desk/protocol.json) is one-shot:
`empty → pending → ready|failed`. `adopt` leaves it ready and records the releasing
principal. Only the transaction receipt and target root establish installation.

Build world/transactions first; Spween also needs its pinned Rust bridge.
Run `python3 scripts/desk.py --database WORLD --artifacts DIR COMMAND`:

| Command | Additional flags |
| --- | --- |
| `create` | `--law` |
| `submit` | `--syntax --source --scenarios --migration --target [--references]` |
| `check` | None |
| `adopt` | `--target --target-root` |
| `inspect` | None |

Every command takes `--object`; mutations take `--principal --intent`, and all
except creation take `--expected-root`. Files contain JSON except exact
source/scenario bytes. Operator-selected `--profile` defaults to `transactions`;
`compiled` enables packages. Proposals cannot select runtime.

`submit --references` retains source/scenario bytes in immutable local custody
and submits compact `delvetalk-source-proposal-v1` metadata. References bind
SHA-256, byte length, UTF-8 encoding and reviewed adapter pins; resolution only
uses the explicitly selected artifact store. No URL/path lookup is accepted.
[Source store](../scripts/source_store.py) exposes `prepare_proposal`, `store_bytes`,
`read_bytes`, and `ref_for`; `Desk.submit_refs` admits a prepared proposal.
Legacy inline `submit` remains supported.

Source is bounded to 512 KiB, scenarios to 1 MiB; source custody retains at most
10,000 blobs/128 MiB without automatic pruning. Original adapter dependencies
are preserved before submission. History exports must include referenced bytes
and pins even for pending or refused submissions; restoring a world restores
those sources. Missing/tampered bytes or changed adapter pins block pending work.

Submission binds syntax, source, scenarios, target and complete migration state.
Migration is **not revision-bound**: the adopter reviews it against their exact
target root. Adoption invokes the desk, then reprograms the target from its exact
`{protocol,state}` result. Both current laws/roots must pass; late failure rolls
back everything. Compiler rights confer no programming rights. Local principals
remain caller assertions.

Immutable `builds/` retain source material/results/diagnostics; `attempts/` retain
requests before admission. Exact historical receipts recover before missing
sources/artifacts or changed runtime checks. Spween `rooms/` bind source/AST.
The direct compiler has 45-second wall, 30-second CPU and 8 MiB file bounds;
[compiler queue](COMPILER-QUEUE.md) adds durable bounded scheduling.

**References do not enlarge compiled-output limits:** roots, protocols and
adoption still face 64 KiB requests/16 MiB frames.

Checks: [desk](../conformance/test_desk.py), [references](../conformance/test_source_store.py).
