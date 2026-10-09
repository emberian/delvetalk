# Repository map

Bend owns object behavior and encounters. Lean owns the source relation and host
admission. Platform adapters retain bytes, authenticate callers, drive processes
and render offered meaning. Start with [the quickstart](../../README.md) to run a
local workshop, or [the documentation map](../INDEX.md) to find a contract.

## Find the owner

| Work | Current location |
| --- | --- |
| Bend frontend, semantics and evaluator | [Editable language edition](../../spec/bend/), [DelveTalk package runtime](../../spec/Delvetalk/) |
| Admission, roots, authority and effects | [Native host and proofs](../../profiles/), with interface contracts beside them |
| Reusable source definitions | [World library](../../world/lib/), including preparation, encounters and documents |
| Authored objects and examples | [Protocols](../../protocols/), [joined examples](../../examples/) |
| Scenes and games | [Spween](../../scene/README.md), [Automatafl](../../game/automatafl/README.md), [table](../../game/table/README.md) |
| Physical custody and surfaces | [Scripts](../../scripts/), [portal contract](../../profiles/PORTAL.md), [Town contract](../../profiles/TOWN.md) |
| Refuting cases and independent evaluators | [Conformance](../../conformance/), [core implementations](../../impl/) |
| Capability and remaining work | [TRACKING](../../TRACKING.md), [BACKLOG](../../BACKLOG.md) |

Read the source before inferring responsibility from a filename.
[Commons packaging](../../protocols/commons/generate.py) loads
[Commons](../../protocols/commons/Commons.obend);
[table packaging](../../game/table/protocol.py) loads
[CommitRevealTable](../../game/table/CommitRevealTable.obend) around the original
11×11 two-player game. The [workshop seed](../../scripts/workshop.py) uses these
loaders and source factories. Packaging transports configuration and exact source;
its receiving tests separately establish behavior under a matching native host.

Likewise, [editor packaging](../../protocols/editor/generate.py) loads source
modules, and [scene packaging](../../scene/handlers.py) serializes scene data for
a source runtime. A Python filename is not evidence of a behavioral generator.
A generator that authors commands, guards or transitions is a competing source
owner and must be replaced with its consumers.

## Component moves

The intended layout separates `language/`, `host/native/`, `host/platform/`,
`world/lib/`, `world/objects/`, `world/scenes/`, `world/games/`, `surfaces/`,
`tests/`, `docs/` and `tools/`. These directories are a destination, not the current
filesystem. Move each component with its imports, build registrations, runtime
closure paths, tests and links. Keep one source owner rather than an old-directory
facade. Source pins continue to bind exact bytes.

Preserve current source dependencies, attribution, licenses and useful independent
oracles. Retire superseded behavior only after its consumers move. Source and
retained compiled artifacts have different custody roles; their coexistence is
not automatically duplication. Preserve tests for desired behavior, and replace
assertions whose only purpose is fidelity to an obsolete representation.

## Remove finished experiments

Frozen reconstruction studies, result bundles, superseded deployment reports and
duplicated status pages belong in Git history. Keep upstream-source verification
as a build gate independently of concluded capsule-size experiments. The requested
compact language descriptions need a usefulness review; they are not runtime
dependencies and do not justify retaining experiment machinery.

The [source constellation instrument](../../protocols/constellation-commons/README.md)
is an ordinary collaborative Bend object: twelve attributed lights, own-author
revision and a shared offered encounter. Its dedicated receiving test replaces
the obsolete fixed two-slot preview and empty migration twin.

Keep dated qualification bundles outside the public tree unless they are reusable
fixtures or proof dependencies. [Posting drafts](../previews/README.md) serve a
current authoring purpose; they do not establish running-world availability.
Track cleanup in [BACKLOG](../../BACKLOG.md), alongside implementation, rather
than maintaining a second queue here.
