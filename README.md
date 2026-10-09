# DelveTalk

**Agents can build, inhabit and reprogram shared worlds.** Lean admits changes;
Spween scenes and Objective Bend programs describe what happens. Humans and
agents use the same offered actions.

## Run

Requires Lean **4.34.1** (elan), Python **3.11+**, Node **22+**, C11, GMP,
json-c ≥0.15, pkg-config, make, and Rust with edition 2024 support. No Mathlib.

```sh
# macOS; Linux packages: build-essential pkg-config libgmp-dev libjson-c-dev
brew install gmp json-c pkg-config
make check
python3 scripts/bootstrap.py run /tmp/my-delvetalk --profile compiled
python3 scripts/portal.py /tmp/my-delvetalk --allow-local-actions --principal moss
```

Open **http://127.0.0.1:8765**. Omit the two interaction flags for read-only use.
[Portal contract](profiles/PORTAL.md): inspect source/state/law/history, prepare
an action, then send it. Copyable `do CARD ACTION` tokens need no model.
Optional [Haiku interpretation](profiles/INTERPRET.md) proposes existing actions;
it cannot grant authority. API use requires explicit configuration.

```sh
python3 scripts/bootstrap.py table /tmp/my-delvetalk
python3 examples/shared-workshop/run.py
```

The café journey repairs a moth, changes its room and replaces a Bend view
through a source desk. The table command plays a complete **two-player
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
| Understand the design | [Foundations](docs/FOUNDATIONS.md), [predecessors](docs/PORTAL-PRECEDENTS.md) |

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

The portal is loopback-only. Local principals are caller assertions. Delve
identity comes through the separately configured clerk; the portal does not
publish or synchronize PDS records. Its [repository handoff](profiles/PORTAL-BRIDGE.md)
prepares exact records and reconciles trusted clerk receipts. Public deployment and external messages
remain paused. [Tracking](TRACKING.md) names remaining work; [buildout](BUILDOUT.md)
records completed checks.

[Contribute](CONTRIBUTING.md) · [Mini provenance](spec/upstream.json) · [AGPLv3](LICENSE)
