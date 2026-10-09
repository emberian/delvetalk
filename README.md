# DelveTalk

DelveTalk is a world of durable, programmable objects. Objective Bend defines
behavior; Spween defines scenes and choices; Lean admits changes under each
object's current law. Objects retain state, source revisions and outcomes so that
people and agents can build together, inspect what happened and continue later.

**Start with [the textual interaction guide](docs/TEXTUAL-INTERACTION.md): actual
replies, source submissions and adoption syntax.** No v1 has launched. Every
hosted world is a disposable preview; fresh seeds replace earlier demonstrations.
Runtime durability remains a property of each running world.

## Participate

In town, a published post can carry the interface. Reply to its card in ordinary
language for [explicit operator interpretation](profiles/MANUAL-INTAKE.md), or use
its offered literal spell:

```text
delvetalk garden-1 plant
seed: fern
colour: silver
```

Use the actual card name and fields on the post you answer. This is post content,
not a shell command. JSON and a website are optional. The receiver authenticates
the reply author; the card's exact reading and current law decide admission.
If the world changed, request a fresh card. If no result arrived, recover the
original reply rather than reposting it.

The [portal](profiles/PORTAL.md) provides another view of source, state, law and
history. Public inspection does not grant execution authority or publish replies.

## Build locally

Use Lean **4.34.1** through elan, Python **3.11+**, Rust with edition 2024 support,
a C11 compiler, GMP, json-c ≥0.15, pkg-config and make. The full checks also use
Node **22+**. Run from the repository root; choose a workshop path that does not
already exist:

```sh
# macOS dependencies; Linux: libgmp-dev libjson-c-dev pkg-config build-essential
brew install gmp json-c pkg-config
make build scene-build
python3 scripts/workshop.py /tmp/my-delvetalk
python3 scripts/portal.py /tmp/my-delvetalk --allow-local-actions --principal moss
```

Open **http://127.0.0.1:8765**. This seeds a [shared workshop](protocols/workshop/README.md)
with two local builders, factories, a work ticket and the canonical two-player
table. `moss` is a trusted local caller assertion, not a Delve login. Omit both
interaction flags for inspection and draft preparation. `make check` runs the
broader conformance suite.

Builders submit exact source and examples to a [source desk](profiles/AUTHORING.md),
inspect the retained compiler report, then explicitly adopt a revision. Compilation
grants no installation right; adoption preserves current law and checks exact roots.

## Current construction

Local receiving paths support typed source objects, sealed modules, atomic
transactions, observation, governed revisions, retained messages and exact retry
recovery. Scenes, source panels and post cards expose those objects. The
[tracker](TRACKING.md) distinguishes checked foundations from active integration:
scene handlers, editors, storage and daemon consumers, containment, clocks,
reusable resident behavior, reflection and source contracts. The workshop is one
integration example within that broader construction.

The [documentation map](docs/INDEX.md) leads to current contracts and active work.
Git history retains superseded plans and reports.

| Read for | Start here |
| --- | --- |
| Current interaction and language | [Textual guide](docs/TEXTUAL-INTERACTION.md), [typed objects](profiles/TYPED-SOURCE-OBJECTS.md), [Spween](scene/README.md) |
| Receiving contracts | [Authority](profiles/AUTHORITY.md), [transactions](profiles/TRANSACTIONS.md), [history](profiles/HISTORY.md) |
| Intended completed design | [Design previews](docs/previews/README.md), explicitly written from an imagined completed system |

[Contribute](CONTRIBUTING.md) · [Mini origin](spec/bend/origin.json) · [AGPLv3](LICENSE)
