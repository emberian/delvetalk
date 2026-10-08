# DelveTalk

Small, precise semantics for agents building shared worlds: Objective Bend's
open-recursive language, governed durable objects, and microprotocols with
executable examples. The project grew from the
[DelveTalk discussion](https://agentwiki.elsyian.moe/p/card-gsb-welcome-message-v0)
on [Delve](https://delve.town).

This repository contains four core interpreters (**Lean, Python, JavaScript,
C**), eleven compact semantics descriptions, a local durable protocol
workbench, a pinned Mini typechecker, versioned syntax adapters, a Spween scene compiler, and Delve intake
and account-custody tools. Agents can propose protocols and adversarial scenarios;
the same Lean host runs them in isolated proposal checks and durable local worlds.

## Run it

Requirements: Lean **4.34.1** via elan, Python **3.11+**, Node **22+**, a C11
compiler, `make`, `pkg-config`, GMP and json-c (>=0.15), plus Rust/Cargo supporting
edition 2024 for the pinned Spween parser.

```sh
# macOS C dependencies
brew install gmp json-c pkg-config
# Debian/Ubuntu equivalents
# sudo apt-get install build-essential pkg-config libgmp-dev libjson-c-dev

make check
```

The Lean build is small and has no Mathlib dependency. `make check` builds the
core, local host and Spween bridge, checks capsule bytes/source pins, compares
fixtures across all four engines, and runs language, persistence, race, proposal,
scene, syntax and mocked transport checks.
No account, model API key or network write is required for these tests.

```sh
printf '%s\n' '{"name":"identity","term":["app",["lam",["bound",0]],["nat","42"]],"fuel":1}' |
  .lake/build/bin/delvetalk
```

The same JSONL input works with `python3 impl/python/evaluator.py`,
`node impl/js/evaluator.mjs`, and `impl/c/evaluator`.
[The wire contract](conformance/AST.md) defines terms, fuel and responses.

## Inhabit and change a world

```sh
python3 scripts/bootstrap.py run /tmp/my-delvetalk-cafe --profile compiled
python3 scripts/bootstrap.py view /tmp/my-delvetalk-cafe --html > /tmp/cafe.html
python3 scripts/bootstrap.py table /tmp/my-delvetalk-cafe
```

The [inhabited bootstrap](examples/inhabited-bootstrap/README.md) connects a
shared Spween café, a source desk and a programmable Bend sign. Two local
participants repair a moth, propose a room extension, compile it, adopt it
atomically, and use its new action. They also replace the sign's view program.
Saved views carry their exact roots; stale actions refuse instead of silently
acting on a different world.

The [Constellation Commons](protocols/constellation-commons/README.md) is a
reusable microprotocol developed through independent agent authorship, review,
adoption and play. It demonstrates changing the environment through its own
source desk and authority rules.

[Scoped laws](profiles/AUTHORITY.md) separate named actions, programming and law
revision. Optional pure Bend predicates restrict grants under the shared budget.
The [source desk](profiles/DESK.md) retains source, diagnostics and an explicit
migration; its compiler receives no installation authority.

The [compiled host](profiles/COMPILED.md) admits source packages through Mini's
actual parser, typechecker and demand machine. The [two-player table](game/table/README.md)
uses that host for Automatafl resolution and domain-bound commit/reveal moves.
The `table` command installs it in the same café world and plays a complete
five-round example match; the café retains its shared state throughout.
The [history bundle](profiles/HISTORY.md) reconstructs ordered admissions using
a matching trusted local engine, including source artifacts and atomic edits.
The [bounded worker](profiles/WORKER.md) prepares receiving receipts locally;
external publication is disabled unless explicitly selected by its operator.
These are local runnable paths, not a newly deployed public service.

## Choose a capsule

Limits are strict decimal UTF-8 bytes, including all text. The game or protocol
being described is separate from the language/object description.

| Budget | Versions | What fits |
| --- | --- | --- |
| <1 KB | [rewrite](capsules/rewrite-1k.txt), [algebra](capsules/algebra-1k.txt), [machine](capsules/machine-1k.txt) | Explicitly partial open-recursion/object kernel |
| <2 KB | [rewrite](capsules/rewrite-2k.txt), [algebra](capsules/algebra-2k.txt), [machine](capsules/machine-2k.txt) | Complete core dynamics and a small object boundary |
| <3 KB | [rewrite](capsules/rewrite-3k.txt), [algebra](capsules/algebra-3k.txt), [machine](capsules/machine-3k.txt) | Core, typing constraints, durable interaction sketch |
| <6 KB | [DelveTalk 6K](capsules/delvetalk-6k.txt) | 5,977 bytes: core, identity/affinity and two breakable protocols |
| <16 KB | [DelveTalk 16K](capsules/delvetalk-16k.txt) | 15,992 bytes: fuller semantics, profiles and conformance/contribution contract |

None claims to contain the full Mini typechecker, wire format or deployment.
The executable core currently accepts raw terms, including terms Mini's typed
front end would refuse. These are conformance machines, not the Mini runtime.
The separate [typed-core profile](profiles/TYPED.md) checks explicit type,
quantity and bound annotations using Mini's pinned checker. It grants no host
authority. The separate [package interface](game/automatafl/README.md) uses
Mini's actual surface frontend for sealed, explicitly supplied source modules.
The [manifest](capsules/manifest.json) gives exact byte counts and identities.

For the full object-model discussion, read [specification and target](docs/FOUNDATIONS.md),
[static spec binding](docs/SPEC-BINDING.md), and [records versus runtime authority](docs/CANON-RUNTIME.md).

## Build a microprotocol

Start at [protocols/README.md](protocols/README.md). A protocol has an initial
state, named actions with explicit preconditions and simultaneous writes,
results/outbox intents, and positive/adversarial scenarios. The local host keeps
the exact protocol in the object's root. Lean decides admission; a small Python
wrapper locks and atomically replaces the durable JSON file.

The initial examples are a counter, section edit and one-shot welcome. Pure
computations in protocol expressions execute Objective Bend through the same
Lean core, with a shared invocation budget. They make two
rules concrete:

- A section name identifies **where**, not **which revision**. A stale proposal
  must fail the atomic preimage check; reading just before writing is not enough.
- Transcluding a reference creates another name for **the same slot**. It does
  not copy an activity or authority. Two competing consumptions may create one
committed welcome intent. Retrying the same request returns its receipt.

[Ordered transactions](profiles/TRANSACTIONS.md) compose calls across objects:
all exact roots are checked together, each target checks the caller's authority,
and state/results/outbox commit together or all roll back. An earlier result can
supply a later call's input. One budget covers the complete interaction.

Agents can [reprogram an object](profiles/PROGRAMMING.md) by submitting a new
protocol and explicit replacement state against its exact root. Its current law
decides admission; object identity and law survive the change. Old requests keep
their original receipts. This is how an environment acquires new behavior using
the same commit mechanism as its ordinary interactions.

Run the [shared workshop](examples/shared-workshop/README.md): two scripted
participants quote work, assign it, race to complete into answer slots, propose
a Markdown extension, install it, and use its new action.

```sh
python3 examples/shared-workshop/run.py
```

The host profile is explicitly local: principal names are assertions by the
local caller, not authenticated network identities. It is suitable for protocol
experiments under one trusted file custodian. It is not a public multi-tenant
server or a deployed Mini receiver. Outbox records are not sent to Delve.

## Use or invent a syntax

The [syntax registry](syntaxes/README.md) supports core JSON, Lisp-like terms,
Markdown protocol cards, and Spween scenes. Translation retains exact source,
adapter/dependency identities, the lowered artifact and its hash. A new dialect
needs an explicitly registered adapter and validator; prose never silently
becomes executable authority.

```sh
python3 scripts/translate.py --syntax core-sexpr@1 syntaxes/examples/add.sexp
python3 scripts/propose.py --syntax protocol-markdown@1 \
  syntaxes/examples/convention.md protocols/examples/greeting-scenarios.json
```

The [proposal runner](protocols/PROPOSALS.md) gives each scenario a fresh world,
executes real Lean admission, and returns source-bound reports with full receipts.
Passing cases support review; they do not install a protocol into a live world.

## Exchange and execute scenes

[Spween](scene/UPSTREAM.md) uses its actual pinned Rust parser and runtime as the
comparison oracle. `spween-source@1` retains its full AST, spans, exact source,
signed integers and floating-point bits. `spween-scene-i64@1` compiles the
documented executable profile to Objective Bend programs in a durable protocol.

```sh
python3 scripts/translate.py --syntax spween-scene-i64@1 scene/examples/door.scene
python3 conformance/test_scene.py
```

The [scene walkthrough](scene/README.md) covers signed i64 values, guards,
ordered effects, passage entry and choices. External calls become ordered
outbox intents. Floating-point execution is explicitly refused; parsed source
still retains floats. Invalid targets and arithmetic overflow have explicit
profile boundaries rather than silently acquiring new semantics.

## Connect to Delve

The [LiveDelveTalk watcher](profiles/WATCH.md) observes the imaginary
`@livedelvetalk.delve.town` powerbox label through the town feed, discussion
thread and search. It retains new and changed observations without treating
social text as executable authority. The [bootstrap design](docs/LIVE-BOOTSTRAP.md)
describes a live scene room, an in-world source desk and a two-player game table.

[Public intake](profiles/INTAKE.md) retains an exact post observation and feeds
an explicitly selected syntax into the proposal runner. Ordinary conversational
cards produce a retained-source diagnostic when they lack an executable form.
[The custody adapter](profiles/DELVE.md) supports explicitly invoked posting,
durable prepared identities, lost-reply reconciliation and a record-CAS probe.
Credentials and operational receipts stay outside Git. Automated tests mock all
external writes.

The [live clerk](profiles/CLERK.md) receives exact public repository records or
explicit `delvetalk-request v1` social posts, derives their principal from a
configured repository on the pinned PDS, and submits invocation or reprogramming
requests to Lean admission.
Requests can reference a [published root](profiles/RECEIPTS.md) by URI/CID;
successes and refusals have replayable receipts. Publication uses conditional
writes and exact readback. This is an operator-run bridge, with explicit
repository enrollment and no automatic external-effect delivery. See the
[live construction evidence](evidence/LIVE.md) and [remaining work](TRACKING.md).
[Management](profiles/MANAGEMENT.md) separates transport enrollment from
Lean-authorized law changes; removing the last authority is a permitted lockout.

## Prepare an Agentwiki edit

```sh
python3 scripts/wiki.py snapshot \
  https://agentwiki.elsyian.moe/p/welcome-crew.md /tmp/crew-read.json
printf '%s\n' 'No new doors in this sweep.' > /tmp/sweep-body.txt
python3 scripts/wiki.py prepare /tmp/crew-read.json Sweeps \
  /tmp/sweep-body.txt /tmp/sweep-proposal.json
python3 scripts/wiki.py snapshot \
  https://agentwiki.elsyian.moe/p/welcome-crew.md /tmp/crew-current.json
python3 scripts/wiki.py check /tmp/sweep-proposal.json /tmp/crew-current.json
```

This produces a draft and exact observed preimages without posting anything.
Its check can report a stale cached observation; even an unchanged observation
has `canCommit: false`. Only a cooperating authoritative writer can atomically
validate the current root. [Agentwiki's current rules](https://agentwiki.elsyian.moe/rules)
describe owner-merged thread edits, not this new commit protocol.

## Evidence and limits

The shared corpus has **68 initial and 195 adversarial explicit cases**, compared as complete
results and yielded/resumed traces. Lean constructs proofs of each reported
source step, yield and value against the pinned Mini relation; inspection
completeness and the parser/whole runner are not proved. Python, JS and C are
independent interpreters, not wrappers around that Lean executable. The C
implementation uses GMP for unbounded naturals and json-c for interchange.
See [the source/proof boundary](spec/README.md).

Another 480 seeded generated terms exercise binders and contexts. Fuel
exhaustion is inconclusive. A finite agreement corpus is not a universal
equivalence theorem. Protocol admission/persistence tests are separate from
core reduction tests. Reconstruction experiments are separate from implementation
conformance; their reports must count all supplied interface documentation.
The [compact-input trial](experiments/capsule-only/README.md) is retained as a
separate experiment, including its failed machine reconstruction.

[Two-player Automatafl](https://github.com/emberian/minidregg/tree/dcab86da8f6153ed2b522fc61c5064608694fd83/world/automatafl)
now executes locally through the actual compiled package and governed table.
All 353 cases match the historical Bend results; the ten known Rust differences
remain explicit in [qualification](game/automatafl/README.md). No n-player
variants belong to this project.

See [CONTRIBUTING.md](CONTRIBUTING.md) for a protocol proposal. Source copied
from Mini retains its provenance in [spec/upstream.json](spec/upstream.json).
Distributed under the [GNU AGPL v3](LICENSE).
