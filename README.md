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

The first card is the commonplace, whose doors open the rest. The furniture is kinds anyone instantiates (a garden
of bells, a room, the weather, a door, a bond): `delvetalk kinds make / name: lamp / of: record` makes a kind, its
law read at once and cited by everything it makes; the porch holds three things waiting to be inspirited.

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

`make check` runs every suite in parallel (870 `def test` in 119 files at b3855b91); `make
smoke` the fast pair; `DELVETALK_OBEND=$PWD/.lake/build/bin/delvetalk-obend
python3 -W ignore -m tests.run test_<surface>` one surface.

## Layout

| Path | What |
| --- | --- |
| `spec/bend` | the DelveTalk edition of Objective Bend: core, machine, typing, frontend, proofs |
| `spec/Delvetalk` | generics, documents, package data, the turn ops, `Limits.lean`, `Serve.lean` (one writer over a directory of worlds), and `Host/` (block store, journal, law, spells, turn loop, snapshots, root) |
| `spec/native` | two C files: fsync for the journal (`sync.c`) and serve's sockets (`serve.c`) |
| `world/lib` | the standard library: prelude, `World` (the protocol), `Plan`, `Card`, `Relation`, `Rows`, `Form`, `Forms`, `Text`, `Spell`, `Menu`, `Mentions`, `Event`, `Policies`, `Scenes`, `Spween`, Document |
| `world/objects` | the packages (10): Record, Thing, Wake, Kind; Avatar, Env, Library, Policy, Tide, Workshop |
| `world/bodies` | the layers a kind lays on each record it makes (9): bell, bond, cistern, commonplace, door, garden, lantern, room, weather |
| `transport` | Python that carries bytes, one entry point (`python3 -m transport <command> --state DIR`): the host's client, the HTTP front and the delve.town login, the bridge, the poster, the hand, the signed repository, the Zulip playtest |
| `deploy` | images, compose, genesis, backup, restore, smoke, playtest, token counts |
| `tests` | one suite per surface, driving the binary over stdin |
| `rehearsal` | the town's archive replayed offline: the deployment gate |
| `lexicons` | `town.delvetalk.*` record types |
| `impl` | independent C, JS and Python evaluators of the core |
| `capsules` | one-screen descriptions for reading |
| `docs` | the design, the agent guide, the operator's documents, the handoffs |
| `site` | the GitHub Pages site |
