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

## Keep one owner

Keep behavior in Bend, admission in the native host, and physical custody in the
adapters. Component moves must update imports, build registration, runtime closure
paths, tests and links together. Exact source pins continue to bind actual bytes.

Preserve licenses, upstream attribution and independent core evaluators. The
[compact descriptions](../../capsules/README.md) are reading material. Keep dated
qualification bundles outside the public tree unless they are reusable fixtures or
proof dependencies. [Posting drafts](../previews/README.md) serve current authoring;
they do not establish deployment. [BACKLOG](../../BACKLOG.md) owns remaining work.
