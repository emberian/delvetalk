# A repository for the system we are building

**Decision.** Organize by semantic responsibility, not by implementation episodes.
There is no launched v1 to preserve. Superseded designs and experiments belong in
Git history. Current source dependencies, licenses and useful independent oracles
remain because they serve the system, not because they are old.

`profiles/` currently mixes native host implementation, proofs, language ABI
descriptions and operator manuals. `protocols/` mixes source objects, generated
behavior, static seeds and journeys. `scripts/` mixes platform I/O with application
workflows. Renaming these drawers without eliminating the competing meanings
would accomplish little. The replacements in [Bend](BEND.md) are part of the layout.

## Destination

| Directory | Responsibility |
| --- | --- |
| `language/` | Bend frontend, semantics, typed evaluator and narrowly pinned upstream dependencies; Spween parsing/data schema |
| `host/native/` | Admission, roots, authority, effects, source/service boundaries, native receiving proofs |
| `host/platform/` | Durable byte custody, process/socket I/O, physical compiler/clock/relay drivers |
| `world/lib/` | Reusable Bend definitions: preparation, encounters, agreement, placement, conversations, lifecycle |
| `world/objects/` | Inspectable Bend workshop, editor, candidate/factory, mailbox and clock objects |
| `world/scenes/`, `world/games/` | Scene data/handlers and games, including the original two-player Automatafl |
| `surfaces/town/`, `surfaces/web/` | Authentication/platform adaptation and rendering of the common encounter |
| `tests/` | Current behavior/composition tests and independent reference engines; no historical result museum |
| `docs/` | Getting started, language/host contracts, these active design decisions and useful authored examples |
| `tools/` | Development/build/source-pin checks; no world policy |

This is a destination map, not a claim that these moves have already happened.
Move a component with its consumers, build paths, runtime-closure paths, tests
and links. Keep one source owner; do not retain an old directory as an API facade
merely to avoid updating imports. Source pins still verify exact bytes/projections.

## Disposition rules

Remove frozen blind/capsule reconstruction studies and their result bundles.
Separate upstream source verification from the concluded capsule-size experiment;
source verification remains a build gate. The explicitly requested compact
language descriptions need a separate decision about which remain useful current
documentation; they are not runtime dependencies or a reason to keep experiments.

Replace the legacy generated command DSL at its authored-object consumers rather
than blessing it as another resident language. Retire old scene implementations
when the source runtime covers the desired language. Preserve tests that express
desired behavior; rewrite tests whose only assertion is fidelity to an obsolete
representation. A test's existence is not a product requirement.

Keep qualification evidence scoped in CI/results outside the public source tree
unless it is a small reusable fixture or an actual proof dependency. Remove
superseded deployment reports, duplicated status documents and historical variants.
Maintain one tracker of present work. Design previews are explicitly hypothetical,
not a second current specification.

## Cut over consumers, then delete the duplicate

The [workshop entry point](../../scripts/workshop.py) still imports generated
commons and table behavior and loads JSON object/desk factories. A source-only
example elsewhere does not remove those actual bootstrap dependencies.

| Boundary | Consumers to move together | Replacement and retained meaning |
| --- | --- | --- |
| Candidate and factory | [Town forge](../../protocols/town-forge/generate.py), stateful workshop, Spween handler workshop, workshop seed factories, desk recognition and authoring catalog | Ordinary source Candidate/Factory/Editor, explicit configuration and current authority. Remove JSON twins, scalar migration templates and recipe-based submissions after callers use source preparation. |
| Presence and crossings | [Commons](../../protocols/commons/generate.py), workshop seed, crossing journeys | Source-owned participant/path policy. Preserve the immediately preceding door's authenticated origin and each receiver's own law. Declared presence and containment are different relations; choose their intended composition explicitly. |
| Commit/reveal table | [Table](../../game/table/protocol.py), table participant/journey, workshop seed, Automatafl companion | Source `CommitRevealTable` around the existing Bend game. Preserve round/seat/domain binding, both commitments before reveal, private nonce custody and original 11×11 rules. |
| Contract release | [Contract authoring](../../scripts/contract_authoring.py) and its receiving journey | Source-owned candidate eligibility and atomic adoption/law amendment. Retain physical source/build custody, exact reviewed roots and uncertain-reply recovery. |
| Workspace custody | [Bootstrap](../../scripts/bootstrap.py), workspace export/restore, example journeys | Separate generic physical custody from the old cafe fixture, then replace fixture behavior. Preserve seed enrollment, runtime/source binding and no-clobber restore. |

The fixed two-slot [constellation preview](../../protocols/constellation-commons/README.md)
has no dedicated production importer; generic scenario discovery still finds it.
Do not retain its representation merely to satisfy that discovery. Either author
its desired collaborative-art behavior as an ordinary source object or remove the
preview and its migration together.

Source files and retained compiled artifacts have different custody roles; their
coexistence is not automatically duplication. A checked-in generated behavior twin
and the generator that owns its policy are a competing authoring path. Likewise,
[editor packaging](../../protocols/editor/generate.py) now loads source modules;
[scene packaging](../../scene/handlers.py) serializes scene data for a source
runtime. Their Python filenames do not make them behavior owners.

Tickets and exhibitions already have ordinary source modules and package loaders.
Their remaining journey/bootstrap dependencies must be cut over without restoring
the deleted behavior generators. Source preparation already replaces the client
recipe interpreter; remove remaining old recipe callers and update
[the offer contract](../../profiles/COMPOSITE-OFFERS.md) with that cutover.

## Work without another bottleneck

Ports of tickets, agreements, places, scenes and contribution objects proceed in
parallel with native preparation and allocation. Physical directory moves happen
at component boundaries as their owners finish, not during another lane's edit.
Use captured source/build snapshots for long checks; a shared source file changing
must not force every lane to restart its entire journey repeatedly.

Commit small useful checkpoints with clear scope. Qualification and convergence
are independent activities; a checkpoint need not claim release readiness. Batch
cross-component tests when shared contracts change. Track deletion of replaced
code as part of each implementation task, not as indefinitely deferred cleanup.
