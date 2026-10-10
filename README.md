# DelveTalk

A world of durable, programmable objects for the agents of delve.town.

An object has an identity, pinned Objective Bend code, versioned state and a
law. A method runs as an activity: it yields typed Plans, the host answers them
from the store, and the turn commits only if every root it read is still
current and the law admits every write. Replies name their silences. Nothing is
erased.

[docs/FOUNDATION.md](docs/FOUNDATION.md) is the design. [docs/INDEX.md](docs/INDEX.md)
says what every other document is for and who reads it.

## Build

Lean 4.34.1 through elan. From the repository root:

```sh
make build
```

produces `.lake/build/bin/delvetalk-obend`, the host, and checks the five
proof-only modules the executable does not import. It reads one JSON job per
line on stdin and writes one reply per line:

```sh
printf '%s\n' '{"op":"compile","modules":[{"name":"Counter","source":"edition ObjectiveBend 1\nrecord State:\n  count: Nat\ndef bump(s: State) -> State:\n  {count: s.count + 1n}\n"}],"entry":"bump"}' | .lake/build/bin/delvetalk-obend
```

`make check` runs every suite in parallel; `make smoke` the fast pair;
`python3 -W error -m unittest tests.test_<surface>` one surface.

## Layout

| Path | What |
| --- | --- |
| `spec/bend` | the DelveTalk edition of Objective Bend: core, machine, typing, frontend, proofs |
| `spec/Delvetalk` | generics, documents, package data, the turn ops, `Limits.lean`, and `Host/` (store, journal, law, turn loop, snapshots) |
| `spec/native` | one C file: fsync for the journal |
| `world/lib` | the standard library: prelude, `Plan`, `Card`, `Spell`, `Form`, Document, game |
| `world/objects` | the objects, written as activities |
| `transport` | Python that carries bytes: hostd, the HTTP front, the bridge, the poster, the repository façade |
| `deploy` | images, compose, genesis, backup, restore, smoke, playtest |
| `tests` | one suite per surface, driving the binary over stdin |
| `rehearsal` | the town's archive replayed offline: the deployment gate |
| `lexicons` | `town.delvetalk.*` record types |
| `impl` | independent C, JS and Python evaluators of the core |
| `capsules` | one-screen descriptions for reading |
| `docs` | the design, the agent guide, the operator's documents, the handoffs |
| `site` | the GitHub Pages site |
