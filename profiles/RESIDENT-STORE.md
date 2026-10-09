# Resident receiving

**One receiver, one durable journal.** The native Lean process retains current
world data, a `(principal,intent)` receipt index, and reverse ordered history.
SQLite stores native preparations; Python neither selects receipts nor admits
requests. The indexed route uses the same receiving transitions as file custody.

## Commit

1. Native `prepare` checks the envelope, exact retry identity, current authority
   and read roots. A retained retry or inspection returns without a new entry.
2. A fresh admission prepares its exact request, reply and structural delta,
   chained to the previous entry by SHA-256. Refusals are admissions too.
3. SQLite commits that entry with `synchronous=FULL` before native `finalize` and
   before returning the reply. The lifetime writer lock excludes another owner.
4. An uncertain attempt blocks subsequent work until reconstruction and exact
   retry reconcile it. A process lost before commit leaves no admission; a lost
   reply after commit finds the retained admission. Recovery never guesses from
   the reply's absence.

Native `lookup` returns only an exact retained request's receipt. Read-only
profile queries and inspections still run in Lean. Messages query pending IDs or
one event without expanding the receipt history.

## Storage and recovery

`ResidentStore.lean` owns the balanced receipt index, candidate state and exact
replay. `resident_store.py` owns the subprocess, SQLite transactions and local
files. A checkpoint contains an expanded native snapshot with its digest and
journal anchor. Reopening validates that seal, rebuilds the index in Lean, then
reexecutes each later entry and compares its entire native preparation. `audit`
reexecutes from genesis; `export_world` explicitly expands ordered history.

Checkpoints are trusted local custody, not signatures. Their digest detects byte
corruption, not a malicious custodian rewriting both bytes and metadata. Runtime
and profile pins must match; this preview format promises no migration. Keep the
SQLite database and its WAL together on a local POSIX filesystem.

Numeric mantissa and exponent survive the native file/pipe serializer. Decimal
scale remains part of exact request/root equality. Legacy framed JSON output is
not the decimal-preserving export oracle; native file custody is.

## Cost and bounds

Each live turn performs an indexed receipt lookup and appends one history cell.
No turn parses or serializes prior receipts. Structural deltas recurse through
objects, including message event/pending maps; unchanged history is not copied
into each journal row. Arrays and scalars are atomic replacements.

This is not an O(1) world. Admission and delta comparison can traverse current
objects and retained event maps; roots, authored state, payloads and individual
replies can grow. Index/history occupy memory. Checkpoints, full export and full
audit deliberately scale with history. RPC frames are bounded at 64 MiB; native
expanded native requests are bounded at 1 MiB; authored intake remains 64 KiB.
The frame bound is not a limit
on checkpoint/export file size.

`ResidentStoreProofs.lean` connects the actual index selection and `remember`
helper to first-match ordered history under valid fresh keys, proves ordered
export/history-count preservation, and proves that successful native checkpoint
reconstruction rebuilds that same index invariant. It does not establish arbitrary admission
functions independent of receipts: the selected host transitions must have that
property. The message registry initializes only before objects exist and before
a registry exists; it does not consult receipt history.

Run `python3 -m unittest conformance.test_resident_store` after building the three
native hosts. Tests compare receiving profiles with exact file custody, exercise
five uncertain boundaries, checkpoint/tail/audit, corruption, writer exclusion,
exact Decimal retries, and 100 actual source message send/consume cycles whose
journal deltas do not serialize accumulated events.
