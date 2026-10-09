# Source desk

**A desk stores proposals; atomic adoption installs their exact results.**
The [ordinary protocol](../protocols/source-desk/protocol.json) has one-shot
submission/completion: `empty → pending → ready|failed`. `adopt` leaves it ready
and records the releasing principal. Only the transaction receipt and target
root establish installation.

Build world/transactions first; Spween also needs its pinned Rust bridge.
[Desk API/CLI](../scripts/desk.py) exposes these commands:

| Command | Additional flags |
| --- | --- |
| `create` | `--law` |
| `submit` | `--syntax --source --scenarios --migration --target` |
| `check` | None |
| `adopt` | `--target --target-root` |
| `inspect` | None |

Run `python3 scripts/desk.py --database WORLD --artifacts DIR COMMAND`.
Every command takes `--object`; mutations take `--principal --intent`, and
mutations except creation take `--expected-root`. File flags consume JSON,
except exact source/scenario bytes. Operator-selected `--profile` defaults to
`transactions`; `compiled` enables packages and governs validation through
adoption. Proposals cannot select runtime.

Submission binds syntax, source, scenarios, target and complete migration state.
Migration is **not revision-bound**: the adopter reviews it against their supplied
exact target root. Adoption invokes the desk, then reprograms the existing target
from its exact `{protocol,state}` result. Both current laws and roots must pass;
late failure rolls everything back. Compiler rights confer no programming rights. A programmer may bypass this
workflow through ordinary reprogramming; the desk adds no veto.
Local CLI principals remain assertions; hashes cannot establish compiler honesty.

The trusted worker uses [propose](../scripts/propose.py), with 45-second wall,
30-second per-process CPU and 8 MiB file limits; failed groups are killed.
This is no OS sandbox or complete memory bound. Immutable `builds/` retain
candidate-bound results/diagnostics; `attempts/` retain requests before admission.
Pending retries require artifacts and unchanged runtime pins. Completed exact
receipts survive missing artifacts and changed runtimes without recompilation.
Spween `rooms/` artifacts bind source/AST into installed `roomArtifact` metadata.

64 KiB request/16 MiB frame limits include roots and candidates; oversized
transport requests create no semantic receipt.
Check: `python3 conformance/test_desk.py` ([lifecycle and adversity](../conformance/test_desk.py)).

[Compiler queue](COMPILER-QUEUE.md): bounded, restartable checks without adoption.
