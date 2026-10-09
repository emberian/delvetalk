# Bounded receiving worker

**Default runs admit requests and prepare receipts locally. External publication is paused; no deployment or scheduler is implied.** Discovery accepts only explicit machine envelopes, never conversational instructions; the [clerk](CLERK.md) refetches exact URI/CID and delegates current-law/preimage admission to Lean.

```sh
python3 scripts/worker.py --state /private/worker --clerk-state /private/clerk \
  discover --watch-state /private/watch --limit 1000
python3 scripts/worker.py --state /private/worker --clerk-state /private/clerk \
  enqueue at://AUTHOR/org.delvetalk.request/KEY --cid CID
python3 scripts/worker.py --state /private/worker --clerk-state /private/clerk \
  run --limit 10 --deadline-seconds 60 --max-attempts 3
python3 scripts/worker.py --state /private/worker --clerk-state /private/clerk \
  retry at://AUTHOR/org.delvetalk.request/KEY
```

Discovery reads retained watch files offline, newest first (1–10,000). The queue binds its clerk directory and each URI to one CID, retains at most 10,000 entries, and never automatically prunes identities.

Admission or semantic refusal is terminal. Transport/pin errors remain retryable; timeouts leave uncertain outcomes. Retry preserves URI/CID and original clerk recovery profile. After interrupted admission, clerk replay recovers the retained receipt. Worker receipt/outbox persistence is atomic, with exact canonical bytes and stable publication intent.

Runs process 1–100 entries; deadline defaults to 60 seconds, maximum 300; per-phase attempts default to 3, maximum 20. Blocked entries require explicit `retry`. Lock waits share the deadline. POSIX subprocess timeouts kill/reap the inherited process group, not escaped descendants. CPU limits are per-process; Linux adds 1 GiB per-process address-space limit (`--memory-mib` 64–8192). Linux also caps Lean thread-stack reservations at 64 MiB or one quarter of the address-space budget: [Lean 4.34 reserves 1 GiB even for its main thread by default](https://github.com/leanprover/lean4/blob/v4.34.1/src/runtime/thread.cpp), which otherwise exhausts the unchanged 1 GiB cap before admission. Neither bounds aggregate memory/CPU; macOS claims no memory cap. Non-POSIX production launching refuses.

Future explicit `run --allow-publication` publishes only previously prepared immutable receipts through account custody; newly admitted entries wait for another run. Lost replies reconcile fixed keys/bytes. Preparation loads no credentials.

Committed entries also atomically prepare `publicationArtifacts`: immutable `org.delvetalk.rootSnapshot` per resulting root and `org.delvetalk.admissionHead` linking them to receipt/source. Refusals produce none. Exact JSON strings survive restart. These describe one admission boundary, not current pointers or a replay chain; their publication path is disabled. Mutable roots and outbox delivery remain separate. Publication requires renewed external-write authorization and a public world.

Reports expose phases, errors, blocked entries and deadlines. Exit 1 means operational errors; 2 configuration failure. [Transactions](TRANSACTION-INTAKE.md) remain indivisible.

[Implementation](../scripts/worker.py), [Lean/mock-PDS/process-limit tests](../conformance/test_worker.py).
