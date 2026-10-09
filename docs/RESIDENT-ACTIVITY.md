# Resident activity: a bell that opens a listening door

**Ordinary retained messages are implemented locally.** The
[receiving tests](../conformance/test_resident_messages.py) cover real compiled
admission, source-desk adoption, forgery refusal, current law, capacity, interrupted
replies and history restoration. This is not deployment evidence; broader consumer
integration continues. [Bell and Door](../protocols/resident-messages/README.md)
provide the executable source and exact ABI.

## Send and receive

Trusted custody initializes an immutable lineage before creating objects. Opt-in
source effects expose four validated emission slots containing destination, command,
recipient program digest and record payload. Lean stamps enabled slots with the
actual emitting call's source preimage, originating principal and admission/call/slot
identity. Source changes, events and receipt commit atomically. These messages do
not become ordinary external outboxes.

Delivery supplies an event reference, explicit recipient and complete current root.
Lean resolves the retained payload and supplies authenticated event facts separately
from input. The recipient's current law must authorize the relay for the stored
command, and its current program must match the bound digest. Direct invocation
cannot impersonate delivery. **Source revision or revocation cannot unsend an
admitted ordinary message.** No new source-release invocation is required.

Recipient effects and consumption commit together. Refusal leaves the event pending;
an accepted no-op can explicitly decline it. An exact retry recovers its original
receipt before current-root or permission checks; a fresh attempt cannot consume
that event again. Initial receive-only profiles cannot emit descendants.

Pending capacity is at most 128 globally and 32 per emitter or recipient. Payloads
are bounded to 4 KiB and captured source roots to 64 KiB. Capacity or budget failure
rolls back the entire admission, including earlier transaction calls. Consumed
evidence remains retained; the bounded pending index supports discovery without
scanning terminal history.

## Local custody and further composition

The [local relay](../scripts/message_relay.py) retains the exact attempt before
admission and retries it after uncertainty. A confirmed stale refusal permits a
fresh-root attempt for the same pending event. It exposes blocked deliveries and
performs no external posting. Exported/forked custody branches do not establish
global exactly-once execution across copies.

Retractable offers are separate protocol behavior: cancellation, release and
acceptance need their own visible commitments. [Recorded clocks and appointments](../protocols/appointments/README.md)
are ordinary source objects driven by explicit logical-time admissions;
service wall time is not recorded world time. Saved language stacks and exactly-once
external delivery are also separate contracts. No external Delve/PDS/wiki messages
are authorized.
