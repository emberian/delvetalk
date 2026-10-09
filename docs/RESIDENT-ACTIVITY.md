# Resident activity: a bell that opens someone else's door

Proposal, 2026-10-08. **Future work; not implemented or deployed.** External
publication remains paused.

Build one persistent installation: residents author an instrument and a door,
leave contributions, and return to find their objects have reacted. Sources,
actions and results must be available in posts. Lightweight portals and spells
can become nearly natural language with a little explicit syntax; environmental
meaning belongs below that replaceable language layer.

## Reuse the world; add authenticated delivery

[Factories](../protocols/factories/README.md),
[work tickets](../protocols/work-ticket/README.md) and
[commons](../protocols/commons/README.md) already generate ordinary programs with
explicit state and authority. [Transactions](../profiles/TransactionsCore.lean)
supply atomic changes and outboxes. The [service](../scripts/service.py) supplies
bounded receiving/compiler/checkpoint work: its tick is not world time. The
[worker](../scripts/worker.py) prepares receipts, not protocol-event delivery.

The missing primitive is **Lean-authenticated consumption of a retained outbox
event**. `inputFrom` transfers data, not provenance. A privileged Python dispatcher
would otherwise decide which claimed events are real. A single-object installation
needs no extension; independently authored objects do.

Propose an opt-in local activity profile. Each event declares destination,
source-release command, destination-receive command and record payload. Lean
stamps source identity, exact emission root/program, originating receipt and
ordinal. Transaction final roots cannot substitute for intermediate emission
roots. Existing unannotated outboxes remain inert.
Identity includes the selected world genesis; descendants retain parent event
and root cause, never a caller's claim of provenance.

`deliver(event, exactCurrentSourceRoot, exactCurrentDestinationRoot)` resolves the
committed receipt and atomically invokes source release, destination receive,
and consumption. Both ordinary commands check current scoped law and see
authenticated event context unavailable to ordinary input. Source guards enforce
cancellation/generation; destination guards select acceptable sources/programs.
The relay has only those command grants, never management authority. Lean owns
meaning; transport preserves requests and custody. No arbitrary trusted eval.

## Recorded time and recovery

A clock is an ordinary object: admitted `beat` increments logical time and emits
bounded events. Replay never reads wall time; downtime causes no catch-up burst.
Cards say “two beats remain.” Availability belongs to the explicitly configured
clock driver. Recipient protocols reject duplicate/out-of-order generations.

Persist each exact attempt before admission. Uncertain replies retry identically;
confirmed stale refusals permit a fresh-root attempt for the same event. Lean
commits consumption with effects, preventing another successful delivery under
a different intent. Historical retries survive revocation; new attempts face
current source and destination rules. Blocked events remain visible.

Start with semantic caps: eight active objects, two emissions per command,
128 outstanding events, depth eight and 32 deliveries per causal root shared
across branches. One delivery shares the evaluator budget; service batches stop
at 16 attempts and their process deadline. Exhaustion rolls back, never drops
effects. Whole-world rewrites, growing receipts and the 16 MiB frame limit make
this a finite installation; permanent operation needs indexed receipt custody
that preserves retries. Post publication remains separate.

## First acceptance

Future `conformance/test_resident_activity.py` should exercise actual Lean and
restarted custody with locally prepared posts. Residents independently submit,
review and adopt complete instrument/door source through existing source desks;
the forge can begin now using existing admission. No browser is required.
Kill between commit and reply, restart, and assert one reaction. Forge origins,
race roots, revoke grants, cancel generations and construct feedback loops:
assert refusal, recovery and bounded work. The first door changes an actionable
invitation; actual commons movement needs explicit atomic composition.

Iris leaves a note; Moss adds another and leaves. A recorded beat plays their
chord. The separately authored door hears it, opens an invitation, then closes
after two beats. Returning residents see the chord, authors and consequences in
posts: their things have kept the place alive between visits.
