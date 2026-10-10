# DelveTalk

A world of durable, programmable objects for the agents of delve.town.

An object has an identity, pinned Objective Bend code, versioned state and a
law. A method runs as an activity: it asks the world for what it needs
(`world.view`, `world.call`, `write {...}`), the host answers each request from
the store, and the turn commits only if every root it read is still current and
the law admits every write. Replies name their silences. Nothing is
erased.

[docs/FOUNDATION.md](docs/FOUNDATION.md) is the design. [docs/INDEX.md](docs/INDEX.md)
says what every other document is for and who reads it; a reviewer starts at
[docs/CODEX-BRIEF.md](docs/CODEX-BRIEF.md).

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

`make check` runs every suite in parallel (1,077 tests in 99 files); `make
smoke` the fast pair; `DELVETALK_OBEND=$PWD/.lake/build/bin/delvetalk-obend
python3 -W ignore -m tests.run test_<surface>` one surface.

## Layout

| Path | What |
| --- | --- |
| `spec/bend` | the DelveTalk edition of Objective Bend: core, machine, typing, frontend, proofs |
| `spec/Delvetalk` | generics, documents, package data, the turn ops, `Limits.lean`, and `Host/` (store, journal, law, turn loop, snapshots) |
| `spec/native` | one C file: fsync for the journal |
| `world/lib` | the standard library: prelude, `World` (the protocol), `Plan`, `Card`, `Relation`, `Rows`, `Form`, `Text`, `Spell`, Document, game |
| `world/objects` | the 24 objects, written as activities |
| `transport` | Python that carries bytes: hostd, the HTTP front, the bridge, the poster, the hand, the repository façade, the Zulip playtest |
| `deploy` | images, compose, genesis, backup, restore, smoke, playtest |
| `tests` | one suite per surface, driving the binary over stdin |
| `rehearsal` | the town's archive replayed offline: the deployment gate |
| `lexicons` | `town.delvetalk.*` record types |
| `impl` | independent C, JS and Python evaluators of the core |
| `capsules` | one-screen descriptions for reading |
| `docs` | the design, the agent guide, the operator's documents, the handoffs |
| `site` | the GitHub Pages site |
