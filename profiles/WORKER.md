# Bounded receiving worker

`scripts/worker.py` connects observed machine requests, the existing clerk and a
private receipt-publication queue. Its ordinary `run` mode admits local requests
and **prepares receipts without publishing**. External publication is currently
paused; no worker has been deployed by these changes. The explicit future
publication flag is an operator interface, not a scheduled or enabled action.

The worker interprets no conversational prose. Discovery only accepts the exact
`delvetalk-request v1` first line, its `delvetalk-request` JSON fence and the shared
request-envelope shape. A suggestion in ordinary discussion remains material for
an agent to interpret and propose separately. Discovery grants no authority:
processing fetches the exact public URI/CID again through the clerk, which derives
the author and invokes Lean admission under current law and exact root.

## Local queue interface

Choose private state directories outside Git:

```sh
python3 scripts/worker.py --state /private/worker --clerk-state /private/clerk \
  discover --watch-state /private/watch --limit 1000
python3 scripts/worker.py --state /private/worker --clerk-state /private/clerk \
  enqueue at://AUTHOR/org.delvetalk.request/KEY --cid RECORD_CID
python3 scripts/worker.py --state /private/worker --clerk-state /private/clerk \
  run --limit 10 --deadline-seconds 60 --max-attempts 3
```

`discover` reads retained watch observations; it performs no network activity.
It examines up to the selected count, newest observed first, and reports skipped
prose, structural errors and truncation. The limit is 1–10,000. `enqueue` allows
an operator to select a custom request record or social post explicitly. Each URI
is durably bound to one CID; repeated discovery is harmless and an edited record
cannot silently replace its queued attempt. The queue itself is bound to the
chosen clerk directory. It retains at most 10,000 request entries and never prunes
historical identities automatically.

`run` uses the existing clerk subprocess. A successful host admission or semantic
refusal becomes a terminal receipt. Transport errors and implementation-pin
mismatches remain retryable queue entries; they do not manufacture host refusals.
A retry uses the same source URI/CID, allowing the clerk to recover a previously
committed outcome even if the source is gone. Pending clerk attempts retain their
old profile rules; the worker cannot bypass a pin mismatch or upgrade boundary.

The entry and its outbox are atomically persisted together. The outbox contains the
exact canonical receipt text and a stable publication intent derived from the
request URI. A process interruption after admission but before worker persistence
is recovered by asking the clerk for the same retained request receipt. No game,
scene format or object command is hardcoded into this flow.

## Bounds and future publication

A run processes at most 1–100 eligible entries, defaults to ten, and has a wall-time
budget of at most 300 seconds. Its CLI subprocess calls receive the remaining
budget as their timeout. Each command starts a fresh POSIX session/process group;
timeout or interrupted waiting kills the whole group and reaps its direct child,
including a spawned Lean process rather than only the Python clerk parent. A
killed call has an uncertain outcome and retains its retry identity. This boundary
covers trusted helper descendants remaining in their inherited process group;
it is not a sandbox against a process deliberately escaping with `setsid`.

A fresh Python launcher sets inherited `RLIMIT_CPU` to the ceiling of the remaining
seconds before exec. This is a **per-process** CPU limit, not aggregate CPU across
the process tree. On Linux it additionally sets per-process `RLIMIT_AS` to 1 GiB
by default; `--memory-mib` selects 64–8192 MiB. Address-space limits include virtual
mappings and may refuse programs that reserve large address regions. They do not
bound aggregate tree RSS. On macOS the worker applies CPU and wall/process-group
bounds but makes no memory-cap claim. Non-POSIX production launching is refused.
Reports state the selected platform resource profile. Injected in-process test
functions must obey their own time bounds. The default deadline is 60 seconds.
Per-phase attempt counts default to three and are bounded at twenty. Entries at
the limit appear in `blocked`; an operator can explicitly re-enable an attempt:

```sh
python3 scripts/worker.py --state /private/worker --clerk-state /private/clerk \
  retry at://AUTHOR/org.delvetalk.request/KEY
```

The worker lock serializes runs, enqueue and retry operations. Run uses nonblocking
lock acquisition with short bounded retries: waiting for another process cannot
extend the declared deadline indefinitely. A lock timeout reports
`deadlineReached` and `lockTimedOut` without processing an entry. Discovery has
its separate item bound.
Resource exhaustion or transport errors do not alter Lean authority or the
meaning of a request.

Only a future explicit `run --allow-publication` enables external receipt writes.
This mode processes previously prepared entries using `receipts.Publisher` and
its existing external account custody. Newly admitted entries become prepared;
a subsequent publication run handles them. Lost successful network replies are
reconciled against the same prepared record key and exact bytes. A restart between
remote publication and local confirmation therefore cannot silently create a
second receipt. No credentials are needed or loaded during discovery/preparation.

The future publication mode writes immutable receipts only. In addition, every
committed entry prepares `publicationArtifacts`: one immutable
`org.delvetalk.rootSnapshot` record for each resulting root and an
`org.delvetalk.admissionHead` record linking snapshot IDs/record digests to the
receipt ID and source. A transaction produces one snapshot per read-set root;
a single-object operation produces one. Refusals produce no root/head artifacts.
All records are prepared atomically with the worker receipt; restart cannot
substitute newer roots. `snapshotJson`/`headJson` retain exact JSON as strings.
These heads describe an admission boundary, not a globally ordered replay chain
or a latest-root assertion. Root/head artifacts have no enabled publication
path in this cycle. Mutable current-root pointers and protocol outbox effects
remain separate explicit operations; it neither delivers
arbitrary outbox values nor infers exactly-once external effects. Prepared receipts
can reveal request input and world state, so enabling publication presupposes an
operator-selected public world and renewed authorization for external writes.

Reports contain processed phases, retry errors, blocked entries and deadline
status. Exit 1 reports operational errors; exit 2 reports local/configuration
failure. No background scheduler is installed by this command.

`python3 conformance/test_worker.py` uses mock PDS transport with the actual Lean
clerk. It checks explicit machine-only discovery, default no-publication behavior,
crash recovery after admission, publication lost-reply reconciliation, source
binding, retry/deadline/batch bounds and terminal stale-root refusal. A POSIX
process test launches an actual grandchild heartbeat writer, times out its parent,
and verifies the descendant stops executing; another inspects the limits installed
in a real subprocess.

Remote multiobject calls use the same queue and source identity; see
[TRANSACTION-INTAKE.md](TRANSACTION-INTAKE.md). The worker does not split an atomic
request into separately admitted calls.
