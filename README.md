# DelveTalk

DelveTalk is a world of durable, programmable objects. Objective Bend defines
behavior; Spween defines scenes and choices; Lean admits changes under each
object's current law. Objects retain state, source revisions and outcomes so that
people and agents can build together, inspect what happened and continue later.

**Start with [the textual interaction guide](docs/TEXTUAL-INTERACTION.md):
replies, source submissions and adoption.** The public opening is under
construction; hosted previews may be replaced with fresh seeds.

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

## Make and revise

Inspect an object's source and its offered encounter. A [Writing object or
editor](profiles/AUTHORING.md) lets you submit a variation with examples. Follow
the Candidate to inspect those exact bytes, choose **Check source and examples**,
and read its retained report. A checked variation offers release or adoption
under the target's current law. If the target changed, make a fresh variation to
rebase; earlier attempts remain inspectable.

The [repeated editing example](protocols/editor/README.md) includes a small
Counter instrument. These are authored object encounters, available through the
same text, portal and API surfaces as other offered actions.

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

The [documentation map](docs/INDEX.md) leads to contracts and examples.
[TRACKING](TRACKING.md) records current capability and [BACKLOG](BACKLOG.md) owns
remaining work, including qualification against a matching native build.

| Read for | Start here |
| --- | --- |
| Current interaction and language | [Textual guide](docs/TEXTUAL-INTERACTION.md), [typed objects](profiles/TYPED-SOURCE-OBJECTS.md), [Spween](scene/README.md) |
| Receiving contracts | [Authority](profiles/AUTHORITY.md), [transactions](profiles/TRANSACTIONS.md), [history](profiles/HISTORY.md) |
| Build or change a component | [Repository map](docs/design/REPOSITORY.md), [contribution guidance](CONTRIBUTING.md) |

[Contribute](CONTRIBUTING.md) · [Mini origin](spec/bend/origin.json) · [AGPLv3](LICENSE)
