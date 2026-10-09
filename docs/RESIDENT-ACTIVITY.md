# Resident activity: a bell that opens someone else’s door

**Next receiving primitive; not implemented or deployed.** Residents should be
able to leave contributions and return to find independently authored objects
have reacted. Posts expose the source, invitation and consequence. Publication
remains separate and paused.

## Retained messages first

Transactions already provide atomic changes and inert outboxes; `inputFrom`
authenticates earlier results within one transaction. Neither authenticates a
retained event or prevents its consumption under another intent. Source
transitions currently emit no outbox. A Python dispatcher must not invent that
missing semantic authority.

Add an opt-in source effect ABI with bounded, addressed messages: destination,
command and record payload. Lean stamps each emission with its originating
receipt, call/slot ordinal, source identity and actual source preimage at the
emitting call. Transaction-final roots cannot replace that intermediate evidence.
Event identity is local to the receiving world; public references also retain
its custody identity.

`deliver(eventRef, expectedRecipientRoot)` resolves committed evidence. Callers
cannot substitute source, destination, command or payload. The relay still needs
the recipient’s current grant; provenance confers no authority. The method sees
host-authenticated event context separately from supplied input. Successful
recipient effects and terminal consumption commit together. A new intent cannot
consume the same event again. Refusal leaves it pending; exact retries recover
the original receipt before changed rules are checked.

An admitted ordinary send has happened. Do not require a fresh source-release
invocation for every message. **Retractable offers are a separate protocol**:
explicit source release/cancellation and destination acceptance may compose under
both current laws. Their stronger commitment must be visible to their authors.

Initially delivery should emit no descendants. Bound message count, pending
capacity and delivery batches explicitly; refuse atomically rather than discard
emissions. This gives a useful mailbox before choosing causal-tree accounting.
A clock can later be an ordinary object with an explicitly granted driver;
service ticks and wall time are not replayable world time.

## Custody and acceptance

Persist the exact attempt before admission. After an uncertain reply, retry that
identity; after a confirmed stale refusal, a fresh-root attempt may address the
same still-pending event. Interrupted delivery must not become a second effect.
Expose blocked events and reasons to operators and residents.

The first joined journey: two residents author a bell and door through separate
desks. Ringing emits a real message; delivery changes the door’s offered action.
A forged payload fails. Kill after commit and before reply, restart, recover one
reaction, then reconstruct from history. Revise either program with an event
pending and exercise its specified revision policy; do not silently move a
captured continuation to new code.

Local file custody removes the whole-world wire ceiling. Parsing, receipt scans
and snapshot rewriting remain linear; sustained activity still needs measured
capacity and a receiving-owned indexed/journal representation. Arbitrary saved
language stacks, terminal linear obligations and exactly-once external delivery
are further contracts, not consequences of this mailbox.
