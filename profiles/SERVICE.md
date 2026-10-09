# Bounded local service

The service composes authenticated receiving, local message delivery, source
compilation and offline continuation preparation. Lean owns admission. The
service has no external publication phase or credentials; `publication: paused`
means prepared local material, not a delivered public record. Participant input
is described in [the textual guide](../docs/TEXTUAL-INTERACTION.md).

## Configure and run

Initialize a [workspace](WORKSPACE.md) and [attach its clerk](CLERK.md). Local
messages require the `compiled` profile and messaging initialization **before
seed admissions**; workspace initialization provides `--messaging`. For resident
custody, run the explicit daemon in a separate terminal:

```sh
python3 scripts/resident_server.py "/path/to/workspace/world.json"
```

Keep it running for service operations; Ctrl-C stops it. Restarting on the same
path reconstructs durable state. File custody also works and needs no daemon.
The backend is explicit; unavailable resident custody never falls back to a file.

```sh
python3 scripts/service.py --state "/path/to/service" init \
  --world "/path/to/workspace" --clerk-state "/path/to/clerk" \
  --compiler-principal "compiler" --relay-principal "relay" --genesis "$GENESIS"
python3 scripts/service.py --state "/path/to/service" enqueue \
  "at://$AUTHOR_DID/org.delvetalk.request/request-key" --cid "$RECORD_CID"
python3 scripts/service.py --state "/path/to/service" tick --limit 10 --deadline-seconds 60
python3 scripts/service.py --state "/path/to/service" status
```

Initialization binds the workspace's genesis, exact admission prefix, clerk,
artifact store and runtime epoch. Omit `--relay-principal` to disable delivery.
Optional `--watch-state` reads retained observations; it does not poll feeds or
turn arbitrary prose into authenticated requests.

A Python caller can instead own the daemon lifetime explicitly:

```python
import sys
sys.path.insert(0, "scripts")
import world
from service import Service

with world.resident_session("/path/to/workspace/world.json", profile="compiled"):
    result = Service("/path/to/service").tick()
```

Use either the session or the standalone daemon, not both for one world.

## Work and recovery

Each tick receives requests, delivers pending native events when configured,
checks registered source-desk candidates, and prepares a replayable continuation.
The named relay must have the recipient's **current** command grant. Delivery
sends only the native event reference and exact recipient root; Lean resolves
source and payload, validates recipient program identity, and atomically consumes
the event. It never sends a PDS, Delve or network message. Pending/event queries
and exact receipt lookup avoid per-delivery history export.

Relay attempts survive lost replies with the same identity. Confirmed stale-root
refusal can produce a traced fresh attempt; other blocked deliveries require
explicit retry. Consumed events never create another delivery. Compiler jobs
record results without installing proposals or granting adoption authority.

Defaults are ten entries per phase, sixty seconds and three attempts; delivery
is capped at sixteen per tick. Worker subprocesses have bounded time/output and
a default 2048 MiB Linux address-space budget; this is not a memory cap on a
separately running daemon. See [resident resource limits](RESIDENT-STORE.md).

Initialization, candidate discovery and checkpoints explicitly expand world
snapshots; local delivery does not. A frozen checkpoint retains source journals and resumes after uncertainty before
new work. Runtime epoch changes block the service. `status` reports blocked
reasons, deadlines and the latest continuation.

[Service tests](../conformance/test_service.py) · [resident relay journeys](../conformance/test_message_relay.py)
· [compiler queue](COMPILER-QUEUE.md) · [documentation map](../docs/INDEX.md)
