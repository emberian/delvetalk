# A bell that opens a listening door

`Bell.obend` and `Door.obend` are independently authored Objective Bend objects.
They each provide `describe` and `view`, and install through
`objective-bend-spell@3`. The focused acceptance submits, checks and adopts both
through the source desk, then plays the bell and delivers its retained sound to
the door. The bell decides what to emit; the door decides which sound to accept.
Python does not implement either decision.

Run `python3 -m unittest conformance.test_resident_messages -v` after building
`delvetalk-compiled`. The two `.binding.json` files also bind the same sources
directly to the plain record ABI for focused host tests. Scenarios remain data;
the source desk checks their view and refusal assertions before adoption.

Before creating objects, trusted custody initializes the immutable lineage:

```json
{"op":"messages-init","principal":"bootstrap","intent":"messages-v1","lineage":"courtyard-1","pendingLimit":128}
```

Initialization requires an empty object table and no existing registry. Each
successful source effects decision has four named emission slots, `a` through
`d`. A slot contains `enabled`, `to`, `command`, `recipientProgram` and record
`payload`. Disabled slots are still validated. The exact protocol digest comes
from the native expression `["program-digest", expression]`; metadata and JSON
number representations are included. The enabled recipient must currently have
that exact program and a receive-only command.

The host stamps each enabled slot with its actual source preimage, protocol
digest, originating principal, admission principal/intent, call index and slot.
The event ID hashes the immutable lineage and admission/call/slot identity.
Creation commits atomically with source state and the receipt's `data.messages`.
Emission descriptors never enter ordinary external outboxes.

Delivery supplies only the reference, explicit recipient and current root:

```json
{"op":"deliver","principal":"relay","intent":"stable-attempt","object":"door","event":{"lineage":"courtyard-1","id":"<native-event-id>"},"expected":"<complete-current-root>"}
```

Native admission resolves the stored payload and separately supplies fourth
argument `EventFacts {id, source, sourceProgram, originatingPrincipal}`. The
current recipient law must authorize the relay for the stored command, and its
program must still match the bound digest. Direct calls cannot supply these
facts. Source revocation or revision after sending cannot unsend a message.
Refusal leaves it pending. Accepted delivery changes the recipient and records
consumption atomically; an accepted no-op can explicitly decline it. Exact retry
returns the original receipt before checking current roots or permission. A
fresh attempt cannot consume it again. Receive-only methods cannot emit
additional messages.

Plain profiles are `delvetalk-source-effects-v1` and
`delvetalk-source-receive-v1`; typed `@3` uses the corresponding
`delvetalk-source-data-*` profiles and retains state as `model` DataWire.
Both use Context2; the source player is evidence, never the relay's authority.

Pending capacity is at most 128 globally and 32 per emitter or recipient. Each
payload is at most 4 KiB and each captured source root at most 64 KiB; validation,
source execution and staging share the host budget. Exhaustion rolls back the
entire admission, including earlier batch calls. Consumed evidence stays
retained; a bounded `pending` index avoids scanning terminal history. Read-only
`messages-pending` and `message-event` queries serve the relay without expanding
receipt history. Physical custody still needs storage capacity. Exporting and
forking a world creates separate custody branches, not global exactly-once
execution across copies.
