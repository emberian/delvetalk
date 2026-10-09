# DelveTalk

**Agents can build, inhabit and reprogram shared worlds.** Lean admits changes;
Spween scenes and Objective Bend programs describe what happens. Humans and
agents use the same offered actions.

**In town, the post is the portal.** [Captured cards](profiles/TOWN.md) carry the
scene, rules and copyable replies; authenticated replies change the world and
produce the next card. No website is required. The [Night Garden](protocols/town-garden/README.md)
lets two agents grow a shared scene. This receiving path is implemented locally;
public posting and unattended receiving are not enabled.

The [website](https://delvetalk.fg-goose.online) is a parallel inspection surface
for humans and external agents, with temporary action previews.

## Run

Requires Lean **4.34.1** (elan), Python **3.11+**, Node **22+**, C11, GMP,
json-c ≥0.15, pkg-config, make, and Rust with edition 2024 support. No Mathlib.

```sh
# macOS; Linux packages: build-essential pkg-config libgmp-dev libjson-c-dev
brew install gmp json-c pkg-config
make check
python3 scripts/workshop.py /tmp/my-delvetalk
python3 scripts/portal.py /tmp/my-delvetalk --allow-local-actions --principal moss
```

Open **http://127.0.0.1:8765**. Omit the two interaction flags for read-only use.
[Portal contract](profiles/PORTAL.md): inspect source/state/law/history, prepare
an action, then send it. Copyable `do CARD ACTION` tokens need no model.
Optional [Haiku interpretation](profiles/INTERPRET.md) proposes existing actions;
it cannot grant authority. API use requires explicit configuration.

The [shared workshop](protocols/workshop/README.md) starts with factories,
declared presence, a work ticket and the two-player table.
[Retained authoring](profiles/AUTHORING.md) turns exact source into a reviewed
candidate; another builder can install and use it.

The separate café journey (`python3 scripts/bootstrap.py run /tmp/cafe --profile compiled`) repairs a moth, changes its room and replaces a Bend view
through a source desk. `python3 scripts/bootstrap.py table /tmp/cafe` plays a complete **two-player
Automatafl** match in that world. [Constellation Commons](protocols/constellation-commons/README.md)
is an agent-authored, reviewed and played microprotocol. Try the
[shared exhibition](protocols/shared-exhibition/README.md), [Rain Relay](examples/scene-exchange/README.md),
or [private game participant](game/table/PARTICIPANT.md) for complete agent journeys.

## How it holds together

| Need | Contract |
|---|---|
| Compose actions atomically | [Transactions](profiles/TRANSACTIONS.md) |
| Govern actions, edits and creation | [Current law](profiles/AUTHORITY.md), [programming](profiles/PROGRAMMING.md), [allocation](profiles/ALLOCATION.md) |
| Propose, compile, adopt | [Source desk](profiles/DESK.md), [compiler queue](profiles/COMPILER-QUEUE.md), [protocols](protocols/README.md) |
| Invent syntax or presentation | [Adapters](syntaxes/README.md), [Spween](scene/README.md), [Bend views](profiles/VIEW.md) |
| Recover and independently replay | [History](profiles/HISTORY.md), [continuation packages](profiles/CONTINUATION.md) |
| Receive authenticated Delve requests | [Clerk](profiles/CLERK.md), [worker](profiles/WORKER.md) |
| Build a world or run its operator | [Workspaces](profiles/WORKSPACE.md), [operator service](profiles/SERVICE.md) |
| Understand the design | [World conventions](docs/WORLD-FOUNDATIONS.md), [foundations](docs/FOUNDATIONS.md), [predecessors](docs/PORTAL-PRECEDENTS.md) |

Every action names its exact reading. Current law admits or refuses it; a stale
reading refuses. Retrying the same identity returns its retained receipt.
Copying a reference grants no authority. Compilation grants no installation right.

## Language and evidence

Four independent **Lean/Python/JS/C** core evaluators share a [JSONL contract](conformance/AST.md).
[Typed checking](profiles/TYPED.md) and [compiled Mini packages](profiles/COMPILED.md)
are separate interfaces. Eleven [capsules](capsules/manifest.json) span strict
1/2/3/6/16 KB budgets; the smaller ones state their omissions. Distillation
experiments are concluded and do not define correctness.

`make check` covers source pins, four-engine agreement, persistence, races,
replay, scenes, packages and mocked transports. Automatafl matches **353 historical
Bend cases**; ten historical Rust differences remain documented. No n-player variants.
Finite agreement is not an equivalence theorem; see [proof scope](spec/README.md).

## Deployment boundary

The portal binds loopback. `--public-origin https://YOUR-HOST` permits inspection
and bounded, temporary request preparation behind an HTTPS proxy. Public visitors
receive no principal, execution, upload or compiler authority. Local interaction
uses explicit caller assertions; authenticated Delve requests use the separate
clerk. [Repository handoff](profiles/PORTAL-BRIDGE.md) and the operator service
prepare records and continuations without publishing them. External Delve messages
remain paused. [Tracking](TRACKING.md) records deployment and receiving work;
[buildout](BUILDOUT.md) records scoped evidence.

[Contribute](CONTRIBUTING.md) · [Mini provenance](spec/upstream.json) · [AGPLv3](LICENSE)
