# Building a small world that its inhabitants can improve

Research/design checkpoint, 2026-10-08. The recommendations below are implementation proposals for the buildout cycles, not claims of deployment. All external posting and publication are suspended. “Public replay” here means preparing and testing an export that is suitable for public verification; it does not mean publishing that export.

The highest-value increment is a complete loop: **enter a place → act together → inspect its actual program → propose and test a change → adopt it under current authority → use the changed behavior → reconstruct the history**. More rooms or decorative entities should follow that loop rather than substitute for it.

## Five primary precedents, and the specific mechanism to borrow

| Primary system/source | Observed mechanism | DelveTalk recommendation |
| --- | --- | --- |
| Self/Morphic: Maloney and Smith, [*Directness and Liveness in the Morphic User Interface Construction Environment* (1995)](https://bibliography.selflanguage.org/directness.html); [Self handbook](https://handbook.selflanguage.org/2024.1/intro.html) | A represented component is also an entry point to examine or change its structure and behavior. Self's programming environment is built in Self and presents objects through expandable outliners. | Every room, table, and tool gets the same inspect/source/actions/history affordance. Preserve object identity while changing views. A text-based object card is enough; a spatial desktop is optional. |
| Sun Labs [Lively Kernel original project account](https://lively-kernel.org/repository/lively-kernel/trunk/doc/website-index.html), 2008 | The running environment includes tools for editing applications and the environment itself, using a deliberately small underlying technology set. | Make the source desk itself an inspectable, versioned artifact. Avoid maintaining a separate privileged “builder app” with a second semantics. A trusted bootstrap may remain, but ordinary construction should use ordinary governed operations. |
| Klokmose et al., [*Webstrates: Shareable Dynamic Media* (2015), pp. 3–5](https://www.klokmose.net/clemens/wp-content/uploads/2015/08/webstrates.pdf) | Shared documents can be manipulated through different personal editors. Transclusion shares the referenced substrate. Instrument code and instance-specific editor state have separate homes; not all local browser state is shared. | One room/table identity can have multiple views. Separate shared program/state from each participant's selected panel, draft and presentation. Transcluding a table must not clone its match or authority. |
| Pavel Curtis et al., [*LambdaMOO Programmer's Manual*, §2.2.3](https://www.wrog.net/moo/pm1.8.3/ProgrammersManual.pdf); [HTML rendering of the section](https://moosaico.com/docs/lambdamoo/manual/html/ProgrammersManual_7.html) | Objects carry named verbs that can be called by players or programs; read and write permissions distinguish inspecting code from changing it. Verb ownership determines execution authority, with dangerous consequences for powerful owners. | Give room objects a small discoverable action vocabulary and readable code. Separate reading, playing, programming and law management; do not reproduce implicit execution under a powerful verb owner's identity. |
| Mark S. Miller, [*Robust Composition* (2006), chapter 21](https://erights.org/talks/thesis/markm-thesis.pdf), [author's dissertation page](https://www.erights.org/talks/thesis/) | The CapDesk/Polaris discussion connects usable least authority to designating the particular resource being used, and distinguishes a small trusted platform from the authority of its applications. | A tool receives a specific object/action binding, not ambient world administration. Copying a tool's code or a reference must not mint the binding. Keep the grant visible and test its refusal boundary. |

These are observations about the cited systems, followed by our design choices. They do not establish that importing their surface metaphors reproduces their security, persistence, or collaboration semantics. In particular, the Webstrates paper describes script changes taking effect after reload; “live” does not justify promising arbitrary hot replacement without a version boundary.

## The three additions, in build order

### 1. A room with a working source desk

The source desk should be reachable from the same room card used for play. It shows the committed source artifact, syntax/compiler identities, current object revision, available actions and a compact recent history. A draft belongs to its author until proposed; viewing or editing a draft does not alter the room. A proposal binds exact source bytes, the compiled artifact, scenario results, expected object root and explicit replacement state.

Reuse [source-preserving adapters](../syntaxes/adapters.py), [scene lowering](../scene/lower.py), [proposal checks](../protocols/PROPOSALS.md), and [reprogram admission](../profiles/PROGRAMMING.md). `scene/lower.py` already retains source, AST, source/compiler hashes and the compiled protocol. The missing product connection is a durable association between the room's committed program revision and its matching source artifact, then a participant-facing route through proposal and adoption.

**Acceptance journey:** Alice and Bob enter the repair café. Alice uses a choice to repair the moth; Bob sees the resulting shared state. Alice opens the room source, adds a constellation branch, previews it in an isolated scenario and submits a proposal. Her play-only identity cannot install it. An authorized programmer installs it against the exact root and an explicit passage/state migration; Bob then invokes the new branch. A choice prepared before installation is refused as stale. Retrying the install returns the old receipt, without applying the migration twice.

**Concrete interface:** keep the visible verbs to `look`, `act`, `source`, `propose`, `adopt`, `history`; these are view-level names over typed requests, not six new kernel primitives. `source` must resolve the installed artifact, not whatever is newest in a source directory. The view distinguishes a draft, a checked proposal and an adopted revision through their actual lifecycle, without turning the room into a log dashboard.

**Avoid:** silently reusing old numeric passage indices after reordering scenes; copying a source label without its exact artifact; a preview that mutates the real object; a compiler service that adopts using its own authority. The room is a concrete connection of existing facilities, not permission to add a Python world interpreter.

### 2. Versioned tools with narrow authority

A participant should be able to pick up a useful instrument—a scene annotator, move chooser, proposal reviewer—and see what object and actions it can use. The reusable program and its granted authority are separate. Tool version `v1` can be copied and inspected as pure data/code; an invocation still checks a current binding to the target, principal, permitted command and any governing root. A URI naming an object is designation alone until the receiving authority model says otherwise.

The buildout's [shared Lean host](../profiles/WorldCore.lean) now contains an opt-in `delvetalk-scoped-law-v1` source implementation: named invocation grants plus separate reprogram and law grants, while legacy arrays retain their all-operation behavior. That is a useful first receiver boundary. This source observation is not a claim that it already implements transferable, attenuable object capabilities or that all scoped-law tests have passed; consult the current tracker/evidence before making either claim.

**Acceptance journey:** Alice can play at the café and operate a table's `choose` action, but cannot reprogram either or alter law. Bob can adopt café proposals but cannot manage its grants. Alice copies Bob's proposal-tool artifact; the copy remains useful for preparing proposals but cannot adopt them. After a law revision, a fresh request under the former grant refuses; an exact retry of a previously terminal request still retrieves its historical receipt. A multiobject instrument refuses atomically when even its last callee lacks authority.

**Small implementable scope:** initially expose these scoped grants as selected action bindings in the room/tool view, with no bearer-token claim. Record which program version prepared a request as provenance. Keep operation admission in Lean. A later capability design can add delegation/revocation semantics explicitly; do not pretend a JSON descriptor already has unforgeable reference semantics.

**Avoid:** using a program hash as an authority token; treating the compiler's approval as permission to install; hiding all grants behind an owner role; letting a tool impersonate its author; automatically upgrading a running match's rules because the tool library changed.

### 3. A two-player table with inspectable replay

Use one actual two-player game as the stress test for shared state, concurrency, secrecy, source pinning and replay. Reuse the pinned Mini Automatafl package as described in [LIVE-BOOTSTRAP](LIVE-BOOTSTRAP.md), after qualifying its actual receiving path. The table should share the same object-card and source/history interfaces as the room. A spectator can inspect rules and completed play without acquiring a seat or administration rights.

**Acceptance journey:** Alice and Bob take distinct seats. Each commits a move for the same match/rules epoch/round/conflict attempt; reveals become admissible only after both commitments. A copied commitment for another seat or round refuses. A stale conflicting request changes neither board nor terminal result. A valid round resolves through the pinned game program, and a complete match reaches its terminal result. After a receiver restart, retries recover the same results. Carol reconstructs the match from a locally exported genesis, exact program/source artifacts and ordered admissions; a changed artifact, missing transition or changed preimage is detected.

The commitment must include a high-entropy nonce and all its domain fields. Before reveal, the public candidate transcript cannot contain the secret moves or nonce merely because the general history UI wants to show “everything.” The table needs no invented timeout winner: absence of the second player is a separate liveness policy.

**Replay interface:** export a closed package containing genesis, runtime/profile identity, source/program artifacts and complete admitted requests with receipts in authoritative order. The replay command re-executes the sequence under that named implementation and compares roots/results. Refused requests can be retained as evidence but must not be counted as state-changing turns. A transaction has one commit identity and its whole read set. This initially demonstrates a verifiable local export; independent verification of PDS authorship or distributed head selection remains a different obligation.

**Avoid:** a second game implementation in the renderer; comparing tick budgets between unrelated evaluators; publishing secret moves early; “newest CID” as a consensus rule; calling an exported view the authoritative head; inferring external delivery from an outbox record. Public posting remains suspended even when export tests pass.

## A pure Objective Bend userspace path

The minimal coherent substrate is a small trusted evaluator/admission boundary plus ordinary versioned programs and artifacts above it. The source desk, view constructor, proposal analyzer and game decision procedure should converge on Objective Bend programs where the required pure representation exists. Custody, process transport and rendering can remain host adapters; they must not secretly decide rules.

A useful first userspace contract is a pure projection:

```text
view(programRevision, committedState, selectedPanel) -> ViewData
```

`ViewData` contains prose, object references, action descriptors and provenance links. It does not contain ambient executable host code. Rendering the same projection through a terminal, room card or browser keeps one semantic view while permitting different presentation. Selecting an action prepares a request bound to the observed root; actual authority is checked again at admission. Personal layout and unsubmitted drafts need not become shared world state.

The following bootstrap remains explicit until replaced by a demonstrated implementation: parsing/lowering source, materializing the bounded view, validating artifacts, and installing the trusted runtime. Current JSON protocol expressions and the Python Spween lowerer are not a self-hosted Objective Bend compiler. The next meaningful proof of progress is to replace one actual userspace computation with a checked Bend program and connect its consumers, not to rename the existing wrapper “pure userspace.”

This path borrows the self-supporting tools of Self/Lively, the shared substrate/personal instrument split of Webstrates, MOO's objects with meaningful verbs, and E's narrow authority. It requires very few new concepts: stable object identity, exact program revisions, explicit admission, and inspectable transitions.

## Research method and limits

Primary references above were inspected through public web results and source documents on 2026-10-08. Scry was used through the configured HTTPS MCP endpoint: discover tools, inspect `crawl.pages` schema, then one bounded host-scoped query for `powerbox`, `transclusion`, and `outliner`. Its returned Self handbook observations confirmed the outliner/environment lead; repeated URL versions were not counted as independent evidence. That query reported a $0.25 charge and incomplete corpus-coverage knowledge, so no absence claim was inferred. Authentication was read in memory; no credential was written to this repository or displayed.

This document changes no application code. Its journeys are proposed acceptance targets, and current executable status belongs in [TRACKING](../TRACKING.md). The bibliography supports the interaction mechanisms; it does not certify our proposed implementation.
