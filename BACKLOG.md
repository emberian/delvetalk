# Work to drain

This is the single work queue. [TRACKING](TRACKING.md) describes current capability;
[design documents](docs/INDEX.md) explain contracts. Neither owns another backlog.
IDs remain stable. Every review finding gets a row, an owner, and a refuting example.
`Queued · root` means retained for dispatch, **not** implicitly accepted or completed.
`Qualify` means implemented with focused evidence; combined receiving/deployment is
still separate. Owners report additional findings here rather than closing over them.

Drain each row by implementing its consumers, deleting superseded owners, running
the smallest refuting check, and linking its scoped commit/check. Remove completed
rows after their commit supplies that record; Git retains history. Review stays open
through integration. Do not close a row merely because another milestone is green.

## Durable interaction

| ID | Outcome; dependency | Status / owner | Refuting acceptance |
| --- | --- | --- | --- |
| DT-01 | Bounded source emission collections and receive-to-send ABI. | In flight · `resident_activity` | A receive emits a real next delivery; malformed/over-capacity emission rolls back all effects. |
| DT-02 | Retained causal depth/work/storage ledger for reactive chains; DT-01. | In flight · `resident_activity` | Cyclic fanout exhausts its named budget without minting fresh capacity on relay/restart/retry. |
| DT-03 | Current-law terminal settlement of obsolete-program events, distinct from send revocation. | In flight · `resident_activity` | Replaced recipient declines old payload without executing it; concurrent consume/settle yields one terminal result, preserved after restart. |
| DT-04 | Two inhabitants create, exchange, schedule, inspect and revise separately governed objects through one conversational document; DT-01–05, DT-24. | Queued · root | Actual source-authored chain + later appointment survives restart; unauthorized neighbor edits and stale completion refuse. Town, browser and API show the same offered meaning. |
| DT-05 | Physical clock observation custody plus source-authored appointment relationship. Driver supplies observations; Bend owns monotonicity, missed intervals and due-work policy. | In flight · `governed_allocation` | Persist request before submit; lost reply retries unchanged. Large jump/equal-time sweeps and 32-entry queue follow source policy; revoked driver cannot advance. |
| DT-06 | Bell selects retained recipient observation and bounded source emissions; no typed-in program hash or fixed a–d UI; DT-01. | In flight · `inhabit_builder` | Offered recipient produces authenticated exact pin; changed recipient refuses stale action. Multiple recipients work without adding host fields. |
| DT-07 | Governed object/history acquisition at native `World.readObject`, distinct from effect authority and physical private heaps. | In flight · `fareoo_semantic_gap` | Capture, catalogue, historical roots and views cannot reveal denied state; copied locator/identity does not grant reads. Existing shared-public behavior is explicit. |
| DT-08 | Typed cross-object completion/origin facts and room-local relationship/verb resolution; [composition](docs/design/COMPOSITION.md). | Queued · root | Placement → room arrival consumes actual typed result with authenticated producer program; ambiguous local name yields alternatives, never ambient reads. |

## Bend owns behavior

| ID | Outcome; dependency | Status / owner | Refuting acceptance |
| --- | --- | --- | --- |
| DT-09 | Source Commons presence/crossing policies; cut over workshop seed and delete Python unrolled policy. | In flight · `town_conformance_room` | Real authenticated door origin passes; spoofed/wrong predecessor refuses. Presence remains distinct from containment. |
| DT-10 | Source commit/reveal orchestration around existing two-player Automatafl; keep nonce custody physical. | In flight · `inhabit_game`; DT-36 | Both commitments precede reveal; wrong round/seat/domain refuses; restart/retry preserves canonical 11×11 match. Advertised seed uses source table. |
| DT-11 | Collapse prelaunch law/spell version ladders and remove application JSON-expression evaluator after actual consumers move; DT-09–10. | In flight · `receiving_review` | Source seed, law invariants, amendments, allocation and messaging pass one current profile. No advertised CLI/bootstrap silently installs legacy expressions. AUTHORITY matches native relation. |
| DT-12 | Generic sums **and functions**, bounded native specialization; [design](docs/design/GENERICS.md). | In flight · `template_language` | Names/Children and Document-list consumers lose duplicate algorithms; polymorphic recursion/expansion overflow refuse with original source locations. |
| DT-13 | Explicit shared prelude ABI at remaining matching consumers; keep authenticated, preparation and rendering contexts distinct. | In flight · `document_semantics` | No duplicate definition of the same ABI; sealed imports retain exact modules; context-specific fields are not coerced away. |
| DT-14 | Required dynamic-value accessors return explicit absence/refusal; typed envelopes avoid unnecessary dynamic decoding. | In flight · `document_semantics` | Missing/wrong recipient, count or observation cannot become empty text/zero/default root. Typed inputs replace envelope checking; heterogeneous fields retain checked variants. |
| DT-15 | Align typed source-value transport with admitted single-module capacity without loosening presentation/identity bounds. | In flight · `backlog_archaeology` | Candidate inspect → prepare → release of >64 KiB module succeeds; genuinely oversized module/payload refuses before expensive work. |
| DT-16 | Source export forwarding/reexports eliminate manual wrapper exports. | Queued · root | Composed ContractCandidate exposes intended signatures without nine forwarding definitions; shadowing/collisions and provenance are checked. |
| DT-17 | Notebook validates configured offered references, not demonstration moth names. | In flight · `document_semantics` | A newly configured child works; invented or unoffered reference refuses without editing Notebook source. |
| DT-18 | One Bend formatting tool/style with source-location fidelity. | Queued · root | Formatting is idempotent; representative templates/comments/source parse identically and diagnostic ranges remain correct. |

## Cost and physical boundaries

| ID | Outcome; dependency | Status / owner | Refuting acceptance |
| --- | --- | --- | --- |
| DT-19 | Persistent pure evaluator/compiler session with bounded physical custody and exact-source cache identity. | In flight · `authored_action_examples` | Repeated small calls remove measured process-start floor; changed source/dependencies never reuse stale compiled result; crash/timeout/oversized output remain bounded. |
| DT-20 | Replace validation-only output `quote` allocation using shared/proved equivalent validation. | Coordinating · `authored_action_examples` | Same accepted/rejected Data and same restriction rules; materialized large output avoids constructing discarded term tree. |
| DT-21 | Measure and repair record-extension/composition allocation costs without changing row semantics. | In flight · `bend_language` | `Node { value: Nat, next: Link }` / `Link = none | some Node`: `extend(node,{value:1n})` checks and evaluates; base shared once, rigid Super stays rigid, scaling measured. |
| DT-22 | Named consistent native limits, distinguishing text presentation, source modules, identity, lists, work and transport. | Queued · root | Boundary ±1 checks agree across writer/reader/host; source capacity no longer fails through unrelated text limit; limits remain resource-enforced. |
| DT-23 | Atomic source enrollment includes Garden, owned objects/desks and open sandbox within the existing work budget. | Qualify · `world_foundations`, `card_affordance_pass`; amendment 8 + membership 5 pass in isolated guard-reuse build | Four-target transaction passes; reprogram only sandbox/owned child, never neighbor/law management. Stale/revoked grants refuse. Identical amendment checks may share only deterministic same-candidate verdict. |

## Joined interaction and recovery

| ID | Outcome; dependency | Status / owner | Refuting acceptance |
| --- | --- | --- | --- |
| DT-24 | Typed interpretation envelope through native codecs, physical model adapter and actual authenticated HTTP. | Qualify · `model_encounters`, `portal_adversarial` | Bare/whole fenced replies admit only offered typed proposal; malformed reply retains provider-error. Exact retry makes no second provider request; render/GET spends none. |
| DT-25 | Source Candidate/Contract release and Desk pending custody recover before compiler/runtime revalidation. | In flight · `world_design_critique`; contract source `welcome_semantics_review` qualified | Lost reply + changed current runtime still returns original receipt; complete release/adoption/law revision is atomic, including >64 KiB package. |
| DT-26 | Account/bootstrap/session exact retry joins across receipt, presentation and membership custody. | Qualify · root; implementations `core_audit`, `protocol_workflow`, `town_spells` | Crash at each retained/commit boundary yields same native result, one session; full presentation quota cannot hide committed receipt; retry never regrants revoked membership. |
| DT-27 | Living document unifies prose, partial forms, offered actions and REPL; bounded catalogue and current selection preserved. | Qualify · root; implementations `document_semantics`, `delvetalk_js`, `core_audit` | A simple note needs one field; typed partial contribution asks its missing question; offered child navigation and full catalogue paging preserve pending intent. Recorded supplied result is never labeled executed. |
| DT-28 | Inspectable scratch edits/repeated editor generations and governed promotion use one authored workflow. | In flight · `world_design_critique`, root | Authorized private/open-workshop edit executes immediately; shared proposal has a real scoped steward-acceptance path despite distinct maker/target authorities; restart/revision preserves exact dependencies and tested transition. |
| DT-29 | Physical adapters stay small: split remaining welcome/bootstrap responsibilities where they obscure custody; no behavioral twins. | Queued · root | Identity, interpretation, welcome and native receipt boundaries have explicit interfaces; policy remains Bend, not refactored into another Python dispatcher. |

## Converge and inhabit

| ID | Outcome; dependency | Status / owner | Refuting acceptance |
| --- | --- | --- | --- |
| DT-30 | Qualify/install one matching native/source/consumer closure, preserving at most two Lean compiler seats. | In flight · root, `compiler_queue`, `backlog_archaeology` | Exact closure includes typed Data, digest tariff, catalogue, row/text/template fixes. Targeted cross-boundary checks run against those actual binaries; no result borrowed from earlier snapshot. |
| DT-31 | Fresh source world with Garden, rooms/workshops, session factory, enrollment, private heaps, Spween and original Automatafl. | Queued · root; DT-09–11, DT-23, DT-30 | Two real accounts and operator-verified Town post reach same shared world, retain isolated heaps, create owned objects and cannot program unrelated shared objects. Canonical 11×11 opening installed. |
| DT-32 | Deploy/rehearse actual HTTPS `/AGENTS.md`, portal and Town intake; DT-31. | Queued · root, `live_clerk` | Public route registration/proof, restart, concurrent edit, uncertain reply, model-disabled literal path and browser light/dark/system work under qualified Linux caps. No social publication is implied. |
| DT-33 | Component-wise repository cleanup/moves, current docs and compact descriptions; [destination](docs/design/REPOSITORY.md). | Queued · root | Moved source has all imports/build/closure/tests updated; obsolete preview/generator/profile copies deleted, links resolve, fresh reader needs no archaeology. Preserve useful attributed source/oracles. |
| DT-34 | Read-only Town observation archive/triage and session signpost remain aligned with manual facilitation. | Qualify · root; implementation `gsb_silence_audit` | Independent feed/anchor/search coverage; retained identity differs from handled identity. Both markers discover candidate, never execute. Recurring prompt matches this; no external messages. |
| DT-35 | Source collaborative poetry/art instrument replacing fixed constellation preview, separate from Commons presence policy. | Queued · root | Two authors compose, inspect and revise actual source-owned instrument; obsolete fixed two-slot preview removed from discovery. |
| DT-36 | Bounded native `sha256Text` exposed to source commit/reveal; source owns canonical preimage, not caller-asserted verification. | In flight · `bend_execution`, `inhabit_game` | Source constructs canonical preimage with exact seat/round/domain/nonce binding; altered values refuse; malformed/large input exhausts named bounds before expensive work. |
| DT-37 | Distinguish resolved object identity, arbitrary text and authenticated provenance through typed source/profile references; justify any core primitive. | Queued · root; coordinate DT-07 | Mint/serialize/revalidate a reference; typed-in string cannot masquerade as observed object. Copying reference confers no authority; exact-code relationship checks current authenticated facts. |
| DT-38 | In-world multiobject behavior examples beside authored objects; retain physical/adversarial boundary tests separately. | Queued · root | Inhabitant inspects and runs an example from current source; multiobject refusal/revision reproduces behavior without a Python policy author. |
| DT-39 | Replace remaining fixed Mailbox/consent arities with bounded source collections and useful library operations; DT-12. | Queued · root | Capacity is configured data; multi-party messages/consents work without code generation or new slot fields. Work/storage overflow and revoked authority refuse atomically. |
| DT-40 | Native sum wildcard elaboration, or explicit unsupported-syntax diagnostic; parser recognition alone is insufficient. | Queued · root | A typed eight-variant sum with one named arm plus `case _` handles remaining variants without unrestricted-value leakage; duplicate/missing-arm errors retain source positions. |
| DT-41 | Opaque invocation/view results permit method use without disclosing private roots; DT-07. | Design · `fareoo_semantic_gap`; implementation queued after ACL closure | Invoke authority permits only source-selected output; full state/history stays private. Opaque version references and caller-projected receipts preserve exact retry without conferring read authority. |

## Reviews already resolved

These decisions are not reopened by an older critique: editable Bend fork
`bf9a288`; system-following light/dark with override `d282576`; deliberate welcome
signpost instead of embedded terminal `0fbb7fb`. Fresh sessions carry the root menu.

Focused repairs waiting only on DT-30 include boundary-length text routes/token
validation (13 tests), checked match/row conversions, template hygiene and linear
fresh-name scanning, direct native Data receiving, bounded catalogue, and factory
digest accounting (122,447-byte reprogram under unchanged 100,000 budget). Their
remaining consumer/deployment obligations are rows above, not claims of launch.
Ticket, exhibition, Forge, Spween and contract workflow source replacements are
implemented; DT-25/30 retain qualification, DT-09/10 the remaining behavioral ports.
