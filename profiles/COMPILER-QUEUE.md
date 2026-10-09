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
exist. `--json` before the command returns complete machine-readable output;
ordinary output uses short labels. `inspect JOB` and `retry JOB` take the full ID
from JSON output or the job filename. Python callers use
`CompilerQueue(state, database, artifacts, profile='transactions')` with `enqueue`,
`run`, `inspect`, and `retry`.

Immutable `jobs/` records retain the exact read root, source/scenario strings,
principal/intent, target/migration and runtime/compiler dependency hashes.
The content-derived job ID is stable; one principal/intent cannot be rebound.
`compiled/` links a job to its retained build. Existing desk `builds/`, `rooms/`
and `attempts/` preserve artifacts, diagnostics and exact admission requests.
Mutable `status/` records retain attempts, recent transport errors and receipts.
Retained records are never automatically pruned.

`run` defaults to ten jobs, sixty seconds and three attempts; configurable maxima
are 100 jobs, 300 seconds and twenty attempts. Queues retain at most 10,000 jobs.
The existing worker command API bounds subprocess wall time, inherited CPU and
Linux address space (default 1024 MiB per process); it kills the process group on
interruption. Queue lock waits and child world locks share the deadline. macOS has
no address-space limit. This is local custody, not an OS sandbox or aggregate
memory/output quota.

Restart repeats unfinished work with the original identity. A saved build avoids
recompilation; an exact retained receipt wins even after candidate/runtime changes.
Otherwise changed candidates, missing binaries and changed runtime/compiler pins
refuse before admission. `retry` resets the attempt budget without changing pins
or source. Runtime hashes identify bytes, not compiler correctness or authority.

Check: `python3 conformance/test_compiler_queue.py` (uses the built transactions
host; mocks only a lost transport reply).
