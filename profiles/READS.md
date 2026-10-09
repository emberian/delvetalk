# Governed acquisition

Current scoped law accepts `read: "public"` or `read: ["principal", ...]`.
Missing `read` preserves the public commons. An empty array denies everyone,
including the creator and law manager. Read permission is separate from mutation
grants and their predicate; a copied identity, root or retained locator grants
nothing. Law changes face the existing current management rules.

Native `World.readObject` governs inspection, catalogue inclusion, paired root
capture, transaction observation, and source preparation. Preparation authorizes
against **current** laws while evaluating the exact **captured** source/state.
Its declared observations use the authenticated participant's identity, not a
service identity. An offline pure job supplied entirely by its caller is a
simulation; it is not access to live custody.

The current whole-root receipt profile also checks acquisition before fresh
operations on existing objects: direct invocation, programming, law revision,
message delivery/settlement, and every non-absence transaction read. These
operations otherwise return complete roots, including unused transaction guards.
Effect grants remain necessary. Creation and allocation return their admitted
creation facts. A law revision may revoke the caller's future reads without
concealing that caller's own committed result.

Exact retries return the already admitted receipt for the authenticated
principal, intent and identical request before checking current permission.
Another participant cannot select that receipt by reusing its intent. New
inspection, preparation and cached-card acquisition check current permission.
Already delivered data and published Town posts cannot be recalled.

Message observations check both current sender and recipient read permissions.
Pending queries omit denied events; event queries refuse before expanding the
retained sender preimage. Event authentication and delivery authority are distinct
from this disclosure check.

`authorize-reads` is a bounded read-only query with exactly `op`, `principal`, and
`objects` (1–17 identities). It checks current permissions without retransmitting
roots. Its verdict is not a reusable grant. Portal uses it when serving a saved
card and its source-declared dependencies.

`object-history` has exactly `op`, `principal`, `object`, `before`, `offset`, and
`limit`. `before` selects a retained prefix; offsets are admission positions.
Each query scans at most 256 entries and returns at most 32 complete admissions,
within 60 KiB. `nextOffset` continues that prefix. An admission involving an
unreadable native-bound object is omitted whole: targets, transaction peers,
allocations and message endpoints are checked. Oversized/malformed entries are
also omitted. A page is not a redacted replay bundle. Arbitrary authored data is
not automatically taint-tracked; copying secret data into a readable object is an
author's disclosure.

Saved derived payloads also reacquire their dependencies when served. Draft wires
check their object and every existing transaction peer; source preparation and
interpretation records check the originating card and its source-declared peers.
This includes public preview drafts and Account interpreted drafts. Executing an
exact previously admitted request and looking up its authenticated own receipt
remain separate paths, so revoked reads cannot strand receipt recovery.

Object workshops now author explicit child read policy. Ordinary scene children
use `read: "public"`; configured workshops can supply a principal array or `[]`.
The array is used exactly, without automatically inserting the maker. Child
invoke grants name its existing commands, while maker/participant management
grants remain separate. Teaching a new command requires a corresponding current
law grant before that command can run.

Full backup/export and replay remain trusted physical custodian operations. A
read-only OS custody socket is not an authenticated participant endpoint: it can
assert principals and may export snapshots. Do not expose it publicly. Portal
history uses the native guarded query, never a Python filter over full snapshots.
A mixed-private world does not have a generally publishable full replay bundle.

This whole-root limitation is not the intended endpoint for private objects.
[Opaque interaction](../docs/design/OPAQUE-INTERACTION.md) specifies the next
result-only invocation/view path, preserving current authority and exact retry.

Check: `conformance/test_governed_reads.py`; message evidence cases accompany the
actual source messaging suite. These are receiving-path checks, not a general
noninterference theorem.
