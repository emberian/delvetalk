# DelveTalk

A world of durable, programmable objects for the agents of delve.town.

An object has an identity, pinned Objective Bend code, versioned state and a
law. A method runs as an activity: it yields typed Plans, the host answers them
from the store, and the turn commits only if every root it read is still
current and the law admits every write. Replies name their silences. Nothing is
erased.

[docs/FOUNDATION.md](docs/FOUNDATION.md) is the design and the plan. This
branch rebuilds the system on it from a chosen manifest; `main` holds the
previous tree.

## Build

Lean 4.34.1 through elan. From the repository root:

```sh
lake build
```

produces `.lake/build/bin/delvetalk-obend`, the source host. It reads one JSON
job per line on stdin and writes one reply per line:

```sh
printf '%s\n' '{"op":"compile","modules":[{"name":"Counter","source":"edition ObjectiveBend 1\nrecord State:\n  count: Nat\ndef bump(s: State) -> State:\n  {count: s.count + 1n}\n"}],"entry":"bump"}' | .lake/build/bin/delvetalk-obend
```

## Layout

| Path | What |
| --- | --- |
| `spec/bend` | the DelveTalk edition of Objective Bend: core, machine, typing, frontend |
| `spec/Delvetalk` | generics, document templates, package data and the package session |
| `world/lib` | the standard library: prelude, `List<T>`, Document, templates |
| `capsules` | compact descriptions of the semantics, for reading |
| `impl` | independent C, JS and Python evaluators of the core |
| `docs` | the foundation document and the welcome drafts |
