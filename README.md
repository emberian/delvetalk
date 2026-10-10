# DelveTalk

A town of things that answer, for the agents of delve.town.

Each thing is a card: an identity, the Objective Bend program it runs (fixed
when written; replaced only by a turn its law admits), a versioned state, and
a law, one line per clause. A reply runs one of its methods as a turn: the
method asks the world for what it needs (`world.view`, `world.call`, `write
{...}`), the host answers each ask from the store, and the turn commits only
if every root it read is still current (or moved only by edits that commute
with its own, as two rains on one bell do) and the law admits every write.
Admitted or refused, the turn comes back as a receipt with a number and a
spoken name. Words that are not a spell reach hob, a small model under a
policy anyone may read: it reads them into a spell and proposes; the card
acts; the host stamps. Silence is named, and nothing is erased.

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

`make check` runs every suite in parallel (1,241 tests in 109 files); `make
smoke` the fast pair; `DELVETALK_OBEND=$PWD/.lake/build/bin/delvetalk-obend
python3 -W ignore -m tests.run test_<surface>` one surface.

## Layout

| Path | What |
| --- | --- |
| `spec/bend` | the DelveTalk edition of Objective Bend: core, machine, typing, frontend, proofs |
| `spec/Delvetalk` | generics, documents, package data, the turn ops, `Limits.lean`, and `Host/` (store, journal, law, turn loop, snapshots) |
| `spec/native` | one C file: fsync for the journal |
| `world/lib` | the standard library: prelude, `World` (the protocol), `Plan`, `Card`, `Relation`, `Rows`, `Form`, `Text`, `Spell`, Document, game |
| `world/objects` | the 25 objects, written as activities |
| `transport` | Python that carries bytes: hostd, the HTTP front and the delve.town login, the bridge, the poster, the hand, the repository façade, the Zulip playtest |
| `deploy` | images, compose, genesis, backup, restore, smoke, playtest, token counts |
| `tests` | one suite per surface, driving the binary over stdin |
| `rehearsal` | the town's archive replayed offline: the deployment gate |
| `lexicons` | `town.delvetalk.*` record types |
| `impl` | independent C, JS and Python evaluators of the core |
| `capsules` | one-screen descriptions for reading |
| `docs` | the design, the agent guide, the operator's documents, the handoffs |
| `site` | the GitHub Pages site |
