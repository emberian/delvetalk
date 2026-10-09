# Local compiler queue

The Candidate's offered Check action records a durable source request. Its
`prepareCompilerWork` export chooses readiness and the generation-bound intent.
An outstanding request hides Check and refuses distinct duplicate invocations,
so repeated clicks preserve the root held by queued or running work. Exact
request replay returns its retained receipt. Both successful and failed reports
remain bound to that full root, including its check generation.
The configured service acquires that source offer under its actual compiler
principal and carries it through `CompilerQueue.enqueue_offered`; Python does not
choose a pending-state policy or synthesize the work intent. The queue performs
bounded native compilation and authored examples and admits `compiled` or
`failed` against that exact captured root. It never adopts or reprograms targets. Lean checks current
authority and exact preimages; a local compiler principal name grants nothing.
The offered work record carries the proposal, migration, target, and declared
success/failure report methods. Jobs, builds, and admission attempts retain this
exact record with the root. Compatible authored residents may revise their
behavior; the custodian does not compare their programs to repository bodies.
No network access or credentials are used. Start with [source desks](DESK.md), or
[the textual guide](../docs/TEXTUAL-INTERACTION.md) for participant interaction.

```sh
python3 scripts/compiler_queue.py --state "/path/to/queue" \
  --database "/path/to/workspace/world.json" --artifacts "/path/to/workspace/artifacts" \
  --profile compiled enqueue --object "candidate" --principal "compiler" \
  --intent "source-compile:candidate:1" --expected-root "/path/to/candidate-root.json"
python3 scripts/compiler_queue.py --state "/path/to/queue" \
  --database "/path/to/workspace/world.json" --artifacts "/path/to/workspace/artifacts" \
  --profile compiled run --limit 10 --deadline-seconds 60
```

The selected native binaries must already exist. Resident workspaces require an
explicit running [receiver daemon or session](RESIDENT-STORE.md); the queue never
starts one or falls back to file custody. File-backed workspaces are also
supported. The current source host is `compiled`. `--json` before the subcommand returns full machine-readable identities;
`inspect JOB` and `retry JOB` use that full job ID.

Immutable jobs bind exact candidate roots, principal/intent, migration, target,
source/scenario digests, byte lengths, encoding, adapter pins and runtime pins.
Inline proposals retain their strings; reference proposals resolve only from the
selected artifact store. Builds retain diagnostics and executable dependencies;
rooms and exact admission attempts remain available for replay. One
principal/intent cannot bind another job. Custody is not automatically pruned.

Restart keeps the original attempt. Native exact receipt lookup precedes current
candidate, source and runtime checks, so a confirmed admission repairs a lost
reply without recompilation or reexecution. Without a receipt, changed roots,
missing/tampered references and changed pins refuse. `retry` resets the attempt
budget without replacing identity or pins. A changed proposal needs a fresh
intent and reading.

Defaults are ten jobs, sixty seconds and three attempts; maxima are 100 jobs,
300 seconds, twenty attempts and 10,000 retained jobs. Queue locks and subprocess
work share a deadline. Worker processes bound output, CPU and Linux address space
(default 2048 MiB); macOS has no address-space cap. A separate resident daemon
has its own lifecycle and resource budget.

References preserve large original sources; they do not bypass native work,
source-package or transport bounds. Resident RPC frames are bounded separately from exported history
files. See [resident custody](RESIDENT-STORE.md) for exact storage limits.

[Queue tests](../conformance/test_compiler_queue.py) · [file/resident desk tests](../conformance/test_desk.py)
· [service composition](SERVICE.md) · [documentation map](../docs/INDEX.md)
