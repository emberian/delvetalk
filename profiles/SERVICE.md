# Public-world operator tick

The service composes existing clerk, receiving worker, compiler queue, source
custody and continuation replay. It never publishes; no credentials or writer
are configured. Repository requests obtain identity only through the clerk's
verified source URI/CID. Names, aliases and natural language grant nothing.

```sh
python3 scripts/service.py --state SERVICE init --world PUBLIC_WORLD \
  --clerk-state CLERK --compiler-principal compiler --genesis PUBLIC_GENESIS
python3 scripts/service.py --state SERVICE enqueue at://AUTHOR/org.delvetalk.request/KEY --cid CID
python3 scripts/service.py --state SERVICE tick --limit 10 --deadline-seconds 60
python3 scripts/service.py --state SERVICE status
```

Initialize an independent [workspace](WORKSPACE.md) with explicit public sources
first. `PUBLIC_GENESIS` must match its manifest and seed; the configured clerk
must share that exact database. Initialization binds the selected admission
prefix, compiler principal, source custody and exact runtime epoch. Private
rehearsals are not discovered or copied. Optional `--watch-state` consumes only
already retained observations and explicit request envelopes; no feed polling
or alias authentication is introduced.

Each tick receives a bounded batch, finds pending objects whose **complete
protocol** matches the registered source desk, queues stable root-bound compiler
jobs, and prepares an offline continuation. Lean decides compiler authority;
compilation never installs the candidate or grants adoption rights. Requests,
jobs and terminal refusals keep their original identities across restart.

A frozen checkpoint retains matching request/source journals and the selected
world snapshot. Export preserves the seed and prior continuation prefix, replays
Lean, and atomically exposes an offline directory. Lost replies resume this
checkpoint before receiving more work. Public records remain prepared bytes;
`publication: paused` never means delivered.

Ticks bound queue work and subprocess wall time with the existing process-group
custody; defaults are 60 seconds, ten entries per phase, three attempts and
2048 MiB Linux address space per process. macOS has no memory cap. Filesystem
custody is trusted, not an OS sandbox. Runtime changes block the service rather
than reinterpret pending work; preserve its checkout/custody and resolve epochs
explicitly. `status` exposes phase, errors, deadlines and the last continuation.

Check: `python3 -m unittest conformance.test_service` uses actual Lean and a
GET-only fake repository transport, including interrupted-reply recovery.
