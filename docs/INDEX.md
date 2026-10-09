# Documentation

Start with the [runnable quickstart](../README.md) or
[writing and acting through text](TEXTUAL-INTERACTION.md).
[TRACKING](../TRACKING.md) records current capability. Profile documents define
interfaces; source and conformance tests define their executable scope. A passing
local case does not establish deployment or a general proof.

[Bend owns behavior](design/BEND.md); [durable objects compose](design/COMPOSITION.md)
and [author encounters](design/ENCOUNTERS.md). The [repository map](design/REPOSITORY.md)
locates their source, receiving hosts, physical adapters and tests.
[BACKLOG](../BACKLOG.md) owns remaining work.

| Task | Contract |
| --- | --- |
| Understand the system | [Architecture](SEMANTIC-INTEGRATION.md), [source/proof boundary](../spec/README.md) |
| Write Bend | [Authoring](../profiles/AUTHORING.md), [typed objects](../profiles/TYPED-SOURCE-OBJECTS.md), [sealed modules](../profiles/MODULE-AUTHORING.md) |
| Understand the language | [Construction and reflection](FOUNDATIONS.md), [static row contracts](SPEC-BINDING.md), [executable reflection](../profiles/REFLECTION.md), [data wire](../profiles/PACKAGE-DATA.md) |
| Write a scene or adapter | [Spween](../scene/README.md), [syntax registry](../syntaxes/README.md) |
| Govern and compose objects | [Authority](../profiles/AUTHORITY.md), [transactions](../profiles/TRANSACTIONS.md), [allocation](../profiles/ALLOCATION.md), [programming](../profiles/PROGRAMMING.md) |
| Propose, check and adopt | [Source desks](../profiles/DESK.md), [compiler queue](../profiles/COMPILER-QUEUE.md), [composite offers](../profiles/COMPOSITE-OFFERS.md) |
| Build resident interfaces | [Views](../profiles/VIEW.md), [forms](../profiles/AFFORDANCES.md), [Town cards](../profiles/TOWN.md), [manual interpretation](../profiles/MANUAL-INTAKE.md), [portal](../profiles/PORTAL.md) |
| Run and recover a world | [Workspace](../profiles/WORKSPACE.md), [resident custody](../profiles/RESIDENT-STORE.md), [history](../profiles/HISTORY.md), [continuation](../profiles/CONTINUATION.md) |
| Read governed state | [Object reads](../profiles/READS.md), [catalogue](../profiles/CATALOGUE.md) |
| Receive and schedule work | [Clerk](../profiles/CLERK.md), [worker](../profiles/WORKER.md), [service](../profiles/SERVICE.md), [resident messages](RESIDENT-ACTIVITY.md) |
| Publish selected records | [Publication custody](../profiles/DELVE.md), [receipts](../profiles/RECEIPTS.md) |

Executable examples include [the workshop](../protocols/workshop/README.md),
[editable source](../protocols/editor/README.md),
[PlaceIndex](../protocols/place-index/README.md),
[containment](../protocols/containment/README.md),
[appointments](../protocols/appointments/README.md),
[work tickets](../protocols/work-ticket/README.md),
[shared exhibitions](../protocols/shared-exhibition/README.md), and
[Automatafl](../protocols/automatafl/README.md). Their linked receiving tests state
what was exercised; presence, ownership, references and command authority differ.

[Contribution guidance](../CONTRIBUTING.md) explains how to add source and
adversarial cases. [Posting drafts](previews/README.md) contain Ember’s current welcome and session
menu, with availability checked against the running world.
