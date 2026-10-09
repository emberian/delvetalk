# Local compiler queue

The queue checks exact pending source-desk candidates and records their `compiled`
or `failed` admission. It never adopts or reprograms targets. Lean still decides
current authority and exact-preimage admission; local principal names are caller
assertions. No network access or credentials are used.

```sh
python3 scripts/compiler_queue.py --state QUEUE --database WORLD --artifacts ARTIFACTS \
  enqueue --object CANDIDATE --principal compiler --intent UNIQUE --expected-root ROOT.json
python3 scripts/compiler_queue.py --state QUEUE --database WORLD --artifacts ARTIFACTS run
```

Select `--profile compiled` for the compiled host. The chosen binary must already
exist. `--json` before the command returns machine-readable output.
`inspect JOB` and `retry JOB` take the full ID
from JSON output or the job filename. Python callers use
`CompilerQueue(state, database, artifacts, profile='transactions')` with `enqueue`,
`run`, `inspect`, and `retry`.

Immutable `jobs/` retain exact roots, principal/intent, target/migration, runtime
pins and source bindings. Inline proposals retain their strings; reference
proposals bind exact source/scenario hashes, byte lengths, UTF-8 encoding and
adapter pins without duplicating large input text.
One principal/intent cannot be rebound to another content-derived job.
`compiled/` links a job to its retained build. Existing desk `builds/`, `rooms/`
and `attempts/` preserve artifacts, diagnostics and exact admission requests.
Mutable `status/` retains attempts, transport errors and receipts; nothing is
automatically pruned.

`run` defaults to ten jobs, sixty seconds and three attempts; configurable maxima
are 100 jobs, 300 seconds and twenty attempts. Queues retain at most 10,000 jobs.
The existing worker command API bounds subprocess wall time, inherited CPU and
Linux address space (default 2048 MiB per process); it kills the process group on
interruption. Linux reserves a 128 MiB initial allocator arena; Lean’s early libuv thread still needs a 1 GiB stack. Explicit memory budgets remain exact. Queue lock waits and child world locks share the deadline. macOS has
no address-space limit. This is local custody, not an OS sandbox or aggregate
memory/output quota.

Restart repeats unfinished work with the original identity. A saved build avoids
recompilation; an exact retained receipt wins even after candidate/runtime changes.
Otherwise changed candidates, missing/tampered source references, missing binaries
and changed adapter/runtime pins refuse before admission. Sources resolve only
from the selected artifact store; history must preserve them even before compilation.
References do not bypass the 64 KiB compiled-request/16 MiB frame limits. `retry` resets the attempt budget without changing pins
or source. Runtime hashes identify bytes, not compiler correctness or authority.

Check: `python3 conformance/test_compiler_queue.py` (uses the built transactions
host; mocks only a lost transport reply).
