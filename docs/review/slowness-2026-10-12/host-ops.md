**The strongest suspects in this facet are repeated compilation, repeated law/rule/want derivation, and uncached block-store reads.** Recent changes added these costs to ordinary turns and genesis setup. I cannot establish which accounts for the full 30-second → 10-minute regression without measurements.

No builds or tests were run; no files were changed. Estimates below are **hypotheses for wall time saved on the 16-core suite**, including its serial property/rehearsal paths. They overlap and must not be added together. Confidence describes the time estimate; the code mechanisms are directly visible.

Notation: **O** objects, **H** journal height, **R** rows in a relation, **C** source closure size, **B** bytes processed, **J** distinct judgments of a written object, **Q/W** rules/wants, **P/S** pending/suspended activities.

1. **Cold compilation is repeated across fresh serve processes and worlds.**  
   **Where:** `spec/Delvetalk/Host/Ops.lean:1406`, `:3464`; `spec/Delvetalk/Serve.lean:151`.  
   **Cost / frequency:** Each cold package invokes closure preparation, compilation, packet decoding, and compilation/evaluation of declared forms/views/methods. Cost is the compiler’s cost over **C**, multiplied by distinct packages per fresh world. Serve opens worlds through `PackageSession.stepIO {}`, without the caches of already held worlds. Fresh `Town` fixtures repeat genesis; `tests/run.py` and ordinary fixtures do not themselves enable the optional disk cache.  
   **Fix:** Share immutable, content-addressed compilation caches across worlds in one serve; give the suite a shared cache stamped by compiler identity. Reuse a validated genesis snapshot for tests that require identical initial worlds, retaining dedicated genesis tests.  
   **Estimated saving:** **60–180 seconds; medium confidence.** Historical commit `985d042d` recorded cold creation at 265–459 ms versus 66–135 ms with a warm cache; those are historical measurements, not measurements of this head.

2. **Definition compilation returns results without retaining them; cache overflow also discards every entry.**  
   **Where:** `Ops.lean:1901`, `:1936`, `:1952`.  
   **Cost / frequency:** `compileDef` returns `(c, w)` without inserting `c`, including disk hits. Callers that discard the returned world repeat compilation or disk reading and packet checking. The concrete read-path consumer is `TurnLoop.readerActions:1148`, used by offered forms and inspection. Prepared requests reset wholesale at 1,024 entries; compiled definitions reset wholesale at 256. Cost is **definition compile/check(C)** per affected read or turn; broad method coverage can repeatedly cross the cache limit.  
   **Fix:** Make the cache-owning operation retain successful definitions and propagate that world through reads. Cache immutable failures too. Replace wholesale clearing with bounded eviction.  
   **Estimated saving:** **30–120 seconds; medium confidence.**

3. **Every write repeatedly parses and traverses its law, carried clauses, and citations.**  
   **Where:** `Ops.lean:1982`, `:1988`, `:2012`, `:2064`, `:2077`, `:2544`, `:3104`, `:3261`.  
   **Cost / frequency:** `carried` reparses `o.lawText` and follows cited text. `objectCitations` calls it again; `wantFacts` calls `objectCitations` and `carriedWants`; `posing` calls `carriedWants` again. Reactions pose wants before and after every updated object. Judgment constructs standings for self and cited objects, each retraversing its own closure. Roughly **O(J × closure work + Q × J × condition cost + W × condition cost)** per written object, with repeated parses and list-based deduplication. Citation diamonds repeat traversal before deduplication.  
   **Fix:** Retain parsed clauses; cache citation closures and followed clauses by relevant object versions. Construct one reusable facts bundle per object/judgment. Derive standings only when referenced. Skip want work when no own or inherited wants exist.  
   **Estimated saving:** **20–90 seconds; medium confidence.** `1d39839e` added reactions on October 11; `02b83db6` added standings and refusal-want reevaluation on October 12.

4. **Looking up one source or checkpoint block validates every sibling in its containing entry.**  
   **Where:** `Ops.lean:1550`, `:1559`, `:1568`, `:1573`, `:1763`, `:1805`.  
   **Cost / frequency:** `sourceText` calls `entrySources`, which hashes **all sources** before selecting one. `blockItems` similarly hashes **all blocks**. Each `Entries.get?` also performs `pread`, hashes the record, and decodes CBOR; it has no decoded-record cache. Resolving **C** sources or **K** blocks from one record costs approximately **O((C or K) × B_record)** rather than O(B_record). Runs during replay, snapshot installation, carry, checkpoint expansion, and resumption.  
   **Fix:** Cache verified records and their source/block maps in a bounded process cache. Validate each immutable record once; address members directly afterward.  
   **Estimated saving:** **10–60 seconds; medium confidence.** The October 10 block-store change `e28b0deb` makes formerly memory-resident lookups actual reads, hashes, and decodes.

5. **Historical-version queries repeatedly walk the same object history.**  
   **Where:** `Ops.lean:4646`, `:4674`, `:5034`, `:5053`.  
   **Cost / frequency:** Historical CID lookup scans up to **H_object** touched entries. Historical state lookup reapplies edits and hashes each intermediate state. `pinAndLawAt` walks the complete reverse history even when requesting the current version. Asking for all **V** versions costs **O(V²)** record visits, plus state reconstruction. `test_properties.Run.states` explicitly requests every version and repeats that after reopening.  
   **Fix:** Index `(object, version)` to state CID and state-changing entry; retain versioned pin/law anchors. Return current pin/law immediately for current-version queries. Reconstruct states from nearby checkpoints.  
   **Estimated saving:** **5–40 seconds; medium confidence.**

6. **Small writes still validate and hash the entire resulting state.**  
   **Where:** `Ops.lean:423`, `:2472`, `:2478`, `:3187`, `:3356`, `:4552`.  
   **Cost / frequency:** Each written object undergoes whole-state type conformance and whole-state CID generation. Edited relations also scan rows for cell bounds and encode old/new rows for storage accounting. Cost is **O(B_state + B_edited_relations)** per commit, even for one changed row or scalar; replay repeats much of it. Growing a relation through N writes produces quadratic aggregate work.  
   **Fix:** Validate changed cells against the already validated state; reuse encoded rows and row sizes. Cache state CIDs by version. Removing whole-state hashing from each mutation requires an explicit cell/Merkle commitment design and compatible replay migration.  
   **Estimated saving:** **5–30 seconds; medium confidence.**

7. **Source, grant, and slug reads scan the journal before answering a small request.**  
   **Where:** `Ops.lean:5144`, `:5175`, `:5187`, `:5198`, `:5207`, `:5250`, `:5291`.  
   **Cost / frequency:** `sourceRecords` makes **two complete H-entry passes**. `readableSources` scans all **O** objects and libraries and rehashes their source text. Grants scan **H** entries. Slug resolution scans **H** entries plus carried-generation hashes, rehashes creation seeds, and decodes every candidate CID. Every page or lookup repeats this work. Block-store reads make these expensive scans.  
   **Fix:** Maintain source metadata, source ownership, grant creation locations, and slug candidate indexes during record/install. Apply current read permissions at lookup.  
   **Estimated saving:** **5–30 seconds; low-to-medium confidence.**

8. **Compile-cache persistence walks and constructs representations of the full cache after every request.**  
   **Where:** `spec/Delvetalk/Host/Session.lean:466`, `:473`; `Ops.lean:1365`.  
   **Cost / frequency:** With disk caching enabled, every op—including status and reads—enumerates all cached builds and definitions. `builtJson` renders laws, clauses, relation metadata, and exposed methods before `DiskCache.write` checks whether the key was already handled. Cost is at least **O(builds + definitions)** per request, plus repeated build representation work.  
   **Fix:** Keep dirty-key queues. Persist newly cached entries only; check whether persistence is needed before constructing their bodies.  
   **Estimated saving:** **5–30 seconds when enabled; 0 seconds when disabled; low-to-medium confidence.** Added by `985d042d`.

9. **A nonempty waiting set triggers settling after every durable op, including no-ops.**  
   **Where:** `Session.lean:148`, `:150`, `:157`, `:166`.  
   **Cost / frequency:** The shortcut tests whether **P/S are empty**, rather than whether anything became ready. Settling happens before the unchanged-height shortcut. A tide waiting for its deadline or unresolved interpretation therefore causes repeated settling scans after unrelated settings, posting, duplicate, or no-op clock operations. Cost includes the settling pass over **P/S**, even when it makes no progress.  
   **Fix:** Track readiness changes: clock movement, new delivery, resolved slot, or changed dependency. Run settling when such an event occurs; index deadline and slot waiters.  
   **Estimated saving:** **3–20 seconds; low-to-medium confidence.**

10. **Relation insert/upsert re-encodes every key and sorts an already sorted relation.**  
    **Where:** `Ops.lean:763`, `:793`, `:818`.  
    **Cost / frequency:** `relationEdit` encodes all **R** existing keys, scans for the target, then `canonicalRowsDropping` encodes the keys again and sorts them. Cost is **O(R × keyBytes + R log R × comparison cost)** per insertion/upsert. N successive inserts cost roughly **O(N² log N)**. Creation also canonicalizes the state at `:3544` and again through `buildObjectIn`.  
    **Fix:** Preserve canonical order with ordered insertion/merge; batch edits while preserving step semantics. Retain encoded keys. Canonicalize a trusted intermediate creation state once.  
    **Estimated saving:** **3–20 seconds; medium confidence.**

11. **Want reads recompute facts twice and world wanting sorts everything before pagination.**  
    **Where:** `Ops.lean:4851`, `:4875`.  
    **Cost / frequency:** `wantRows` constructs `wantFacts`, then `posing` constructs it again. World wanting repeats that per indexed object, reevaluates wants before checking each row’s cursor, uses linear name matching, and sorts all surviving wants. Cost is **sum(object fact work + W² matching + W × condition cost) + O(totalW log totalW)** per read, regardless of page size. Empty lists left in the index still incur object work.  
    **Fix:** Reuse facts and posed clauses; remove empty index buckets; maintain ordered wanting rows and dependency invalidation. Inspect eligible heights before expensive filling.  
    **Estimated saving:** **2–15 seconds; low-to-medium confidence.** Introduced by `9a8696a7`.

12. **Serve scans crossings across all worlds after every request.**  
    **Where:** `spec/Delvetalk/Serve.lean:405`, `:595`; `Ops.lean:3924`, `:3984`.  
    **Cost / frequency:** Each request scans every held world’s **P/S**. Outbound sends resolve their originating receipt through journal reads. A crossing round can repeat up to 64 times; `crossOp` reconstructs outbound items again to locate one ID. Completing X crossings can add **O(X × (P+S))** work. The work occurs after sending the reply but blocks the next request.  
    **Fix:** Maintain an outbound queue/index and dirty-world worklist. Locate crossing IDs directly and retry blocked crossings only when dependencies change.  
    **Estimated saving:** **1–10 seconds; low confidence.** Added by `e0fb9e7d` on October 12.

13. **Snapshots synchronously rebuild and encode the whole world.**  
    **Where:** `Session.lean:109`, `:198`, `:369`.  
    **Cost / frequency:** Each snapshot sorts objects, reparses every law, computes every state CID, serializes all state/indexes, writes the result, then scans the directory for retention. The callee’s type deduplication is list-based: up to **O(O × distinctPins)**. Runs every 1,000 entries, after ignore operations, and explicitly in snapshot/fork/carry tests. An explicit repeat at the same height recomputes everything.  
    **Fix:** Reuse validated law parses, cached state encodings/CIDs, and hash-map type deduplication. Reuse an existing snapshot at unchanged height. Expose snapshot cadence through serve.  
    **Estimated saving:** **1–10 seconds; low-to-medium confidence.**

14. **Opening a world replays it even when the same session already holds its handles.**  
    **Where:** `Session.lean:89`, `:260`, `:294`; `Ops.lean:4310`, `:4532`, `:4563`.  
    **Cost / frequency:** Reusing handles avoids reopening files, but `openWorld` still calls `Snapshot.openJournal`. Without a valid snapshot, it repeats compilation, judgment, state hashes, reactions, and indexes across **H** entries. With a snapshot, it still reads the chain, installs/checks the snapshot, and replays the tail. Runs per reopen, serve restart, historical fork, and ignore reconstruction.  
    **Fix:** Use retained sessions for ordinary access. Add an explicit inexpensive operation for changing process settings without requesting replay. Preserve intentional reopen/verification semantics; bound replay tails with snapshots.  
    **Estimated saving:** **1–10 seconds; low confidence**, overlapping compilation and record-read savings.

15. **Library files are copied, reread, and resealed repeatedly.**  
    **Where:** `Serve.lean:99`, `:557`; `Session.lean:64`, `:329`, `:381`; `Ops.lean:914`.  
    **Cost / frequency:** Every serve start deletes/recreates the sealed directory and copies all files. Startup loads it once, then each world-open with that library loads it again. Loading uses quadratic list accumulation/name checking; topological sealing repeatedly reparses imports and scans placed/ready lists. Cost includes **O(library bytes)** IO plus repeated graph/list work per start/world/open.  
    **Fix:** Retain the sealed `Library` in `Server`; pass it to world initialization. Parse imports once and topologically sort using adjacency maps. Reuse an unchanged sealed directory.  
    **Estimated saving:** **1–8 seconds; medium confidence.**

16. **Package initialization rechecks a packet already checked during compilation.**  
    **Where:** `Ops.lean:1373`, `:1406`, `:3512`, `:3539`.  
    **Cost / frequency:** `initialState` runs through `executeDataValues`, which prepares the packet rather than using a held checked entry. Every creation repeats packet admission over its reachable program. `builtOf` calls `CheckedEntry.ofPacket` and then separately `decodePacket`; cold `compileObject` also decodes the freshly compiled packet.  
    **Fix:** Store the checked initial entry in `Built`; use `executeDataEntry`. Obtain assumptions from the held entry instead of decoding its packet again. Memoize validated initial values where initialization is pure.  
    **Estimated saving:** **1–8 seconds; medium confidence**, overlapping item 1.

17. **Layer-stack compilation does not retain newly compiled lower layers.**  
    **Where:** `Ops.lean:1423`, `:1470`, `:3464`.  
    **Cost / frequency:** `compileObject w lower` recurses with the same world and returns only a `Built`; newly compiled lower builds/prepared closures are lost. The outer caller caches only the requested build. Reprogram preparation similarly retains a `Program`, not the intermediate builds. Different bodies over a common base repeat lower compilation; a cold L-layer stack compiles multiple growing closures.  
    **Fix:** Return and retain cache updates through recursive compilation. Prepare each closure once; reuse compiled lower shapes.  
    **Estimated saving:** **1–8 seconds; medium confidence**, overlapping item 1. Introduced by `311e82de`.

18. **Carried/forked genesis anchor construction is quadratic in objects.**  
    **Where:** `Ops.lean:2794`, `:2800`, `:2819`, `:2839`, `:2887`.  
    **Cost / frequency:** `anchorsAfter` enumerates installed objects, then calls version/pin/law lookup separately for each. Every lookup scans the genesis object array. Approximately **3 × O²** row examinations per install. Snapshot anchor checking invokes these helpers again, adding another quadratic pass. Ordinary multi-object admitted entries similarly rescan write/create arrays.  
    **Fix:** Derive all anchors in one pass over each entry’s rows. Build a genesis row map once and reuse it during anchor checking.  
    **Estimated saving:** **0.2–5 seconds; low confidence** for current small worlds; much larger at the 10,000-object bound.

19. **Stale-root admission rereads the same intervening edits for each cell or edit.**  
    **Where:** `Ops.lean:2250`, `:2258`, `:2343`, `:2371`, `:2398`.  
    **Cost / frequency:** `cellsCurrent` computes changed fields, then recomputes `editsSince` for each read row/span. `editsAdmit` repeats it per upsert/retract; `rootAdmits` can repeat changed-field work. Cost is **O((readCells + writes) × interveningHistory)** record reads/decodes plus repeated canonical key encoding. Runs during resumed/concurrent commit and replay.  
    **Fix:** Compute one change summary per `(object, seenVersion)` per judgment: changed fields, encoded keys, and span bounds.  
    **Estimated saving:** **0.2–5 seconds; low-to-medium confidence.**

20. **Pagination scans full retained indexes even for an empty newest page.**  
    **Where:** `Ops.lean:5106`, `:5241`, `:5332`, `:5369`, `:5408`.  
    **Cost / frequency:** `pageByHeight` assigns ordinals to every item, reverses/filters the entire array, then extracts a page. Entries first allocate an H-sized range. History/offers/publications filter complete retained arrays. Publication reads additionally rebuild `pagePosts` by scanning every recorded post. Polling a caught-up cursor still costs **O(index length + posts)**.  
    **Fix:** Binary-search ordered heights/cursors; iterate only enough items for the page and `more`. Maintain newest whole-page post references at `postIndex`.  
    **Estimated saving:** **0.2–5 seconds; medium confidence.**

21. **Checkpoint compaction prints tokens repeatedly and deduplicates blocks quadratically.**  
    **Where:** `Ops.lean:1588`, `:1595`, `:1625`, `:1639`, `:1670`.  
    **Cost / frequency:** `cutBlocks` compresses each token for size, then `cutHash` compresses it again. Blocks receive canonical hashes afterward. `blocksField` checks fresh blocks with linear `acc.any`, giving **O(K²)** comparisons for K newly encountered blocks. `blockField` fully prints values just to measure their size. Runs per suspension and compacted interpretation.  
    **Fix:** Compute token size/hash once; use nonprinting size calculation and a hash set for fresh block IDs. Cache reusable checkpoint fragments by program/site.  
    **Estimated saving:** **0.2–5 seconds; low confidence.**

22. **Object and principal name resolution scan and normalize the entire registry.**  
    **Where:** `Ops.lean:2110`, `:2672`, `:4607`.  
    **Cost / frequency:** Folded object resolution normalizes every ID; handle resolution lowercases every registered handle; object listings scan all objects and sort all matching IDs before returning 64. Costs **O(total name bytes)** or **O(O + matches log matches)** per lookup/page. Spell fallback, rule targets, and genesis `existing` queries use these paths.  
    **Fix:** Maintain normalized-name-to-candidate indexes, including ambiguity; retain an ordered object-ID index and filter permissions during traversal.  
    **Estimated saving:** **0.1–3 seconds; medium confidence.**

23. **Quota/status queries scan reservations from every previous hour.**  
    **Where:** `Ops.lean:3800`, `:3804`, `:3857`; `Session.lean:428`.  
    **Cost / frequency:** `postsUsed` scans every retained reservation. Status discovers current sources, then scans all reservations again per source, including another quota scan. Costs **O(reservations × currentSources)** per status; counted reservations cost O(reservations) each. Property tests request status repeatedly around turns.  
    **Fix:** Maintain `(hour, source)` counts during reserve/release and an index of current-hour sources.  
    **Estimated saving:** **0.1–3 seconds; medium confidence.**

24. **Commits repeatedly build and deduplicate list-based proposal/index data.**  
    **Where:** `Ops.lean:228`, `:362`, `:2092`, `:2530`, `:2564`, `:2592`, `:2993`, `:3007`, `:3116`.  
    **Cost / frequency:** Cell joins repeatedly encode keys during pairwise comparisons; `allWrites` rescans placements and accumulated writes and is recomputed by several consumers; root insertion scans existing roots; judgment deduplication serializes arguments and scans prior judgments; each placement filters the full placement list; rule/want updates scan their per-object lists. Costs include **O(cells² × keyBytes + placements² + judgments² + roots² + wantFlips × W)** per turn/commit. Bounds limit size but do not remove repeated work.  
    **Fix:** Compute `allWrites` once; use maps/sets with precomputed encoded keys and judgment keys; batch rule/want index updates.  
    **Estimated saving:** **0.1–3 seconds; low-to-medium confidence.**

25. **Chronicle reads reconstruct the whole day before applying the 48-line limit.**  
    **Where:** `Ops.lean:4953`, `:5014`.  
    **Cost / frequency:** Each read locates the day by linear search, reads/decodes all **H_day** entries, retains every event, and deduplicates hands with linear membership checks. Cost is **O(dayCount + journal bytes for day + H_day × distinctHands)** per chronicle read or morning-card derivation.  
    **Fix:** Keep derived day aggregates/event indexes keyed by height; apply permissions when reading. At minimum retain only the first 48 displayed events while counting the remainder, and use a hand set.  
    **Estimated saving:** **0.1–3 seconds; low confidence.**

26. **Foreign card reads discard newly warmed compilation caches.**  
    **Where:** `Serve.lean:315`, `:323`, `:328`, `:497`.  
    **Cost / frequency:** `Host.cardOp` returns an updated world, but `readForeign` keeps only the reply. Repeated foreign reads can recompile render definitions. Every citation also recomputes the target’s whole-state CID.  
    **Fix:** Return and store the updated foreign session; reuse its versioned state CID.  
    **Estimated saving:** **0.1–2 seconds; low confidence** because current federation test coverage is limited.

27. **Journal appends duplicate encoding, link construction, and metadata IO.**  
    **Where:** `Ops.lean:3141`; `Session.lean:122`, `:135`, `:167`, `:177`.  
    **Cost / frequency:** Sealing hashes canonical entry bytes; durability separately encodes the same entry into `recordBytes`. `linksAt` runs for capacity calculation and again for append. Append checks file sizes again, flushes the store, writes records, then flushes both files. Cost is repeated **O(newEntryBytes)** processing plus several filesystem operations per mutating request.  
    **Fix:** Carry sealed record bytes through commit to append; construct links once; maintain known byte offsets under the held writer lock.  
    **Estimated saving:** **0.1–2 seconds; medium confidence.** Actual fsync barriers are discussed separately below.

28. **Serve writes housekeeping files on every request.**  
    **Where:** `Serve.lean:171`, `:346`, `:506`, `:585`; `:184`, `:222`, `:516`.  
    **Cost / frequency:** PID-file truncation/write occurs even on malformed requests. Every scratch read rewrites its last-use file, even at an unchanged home clock. Scratch creation, expiration, and status scan all scratches. Costs one or more blocking filesystem operations per request, plus **O(scratches)** for those scans.  
    **Fix:** Write the PID once. Persist scratch use only when its clock changes, with an explicit restart-preserving policy. Index scratch owners and expiry deadlines.  
    **Estimated saving:** **0.1–2 seconds; medium confidence.**

29. **Startup binary hashing has a large conditional cost, already bypassed by ordinary fixtures.**  
    **Where:** `Serve.lean:84`, `:92`, `:561`.  
    **Cost / frequency:** A cache miss reads and hashes the entire executable per fresh state directory. `deploy.serve.pin_cache` normally supplies the pin. However, `tests/run.py --profile` passes a shell wrapper; the seeded wrapper path/metadata do not identify the actual executable that serve hashes, potentially defeating this bypass.  
    **Fix:** Key the pin by the real executable even when using a counting wrapper; use a process-wide/compiler-identity pin cache.  
    **Estimated saving:** **0 seconds in normal cached starts; roughly 3.3 seconds per miss historically, potentially 10–60 seconds of suite wall time with repeated misses; low confidence.**

30. **Socket output backpressure blocks the sole host thread for up to 30 seconds per wait.**  
    **Where:** `spec/native/serve.c:214`, `:227`, `:229`.  
    **Cost / frequency:** A client that stops reading a sufficiently large reply makes the single server thread poll only that socket. Each unsuccessful writable wait can cost **30 seconds**; partial progress can extend total blocking further. Signal interruption can drop the connection, but normal output backpressure stalls all other clients/worlds.  
    **Fix:** Queue bounded output per connection; poll `POLLOUT` in the main event loop with an absolute deadline. Keep other connections progressing.  
    **Estimated saving:** **0 seconds for normally draining clients; 30 seconds or more per triggered stall; low confidence as a suite explanation.**

31. **Socket intake drains one connection without a work budget; poll/reply routing scans all connections.**  
    **Where:** `serve.c:128`, `:183`, `:198`, `:216`; `Serve.lean:581`.  
    **Cost / frequency:** `take` reads until EAGAIN and queues every complete line before returning, so a continuously writing client can starve queued requests. Connection polling and reply lookup cost **O(connections)** each; framing copies request bytes several times, and Lean splits the entire line to recover two envelope fields.  
    **Fix:** Bound bytes/lines accepted per connection per pass; maintain connection-ID lookup and bounded queues; parse only the envelope prefix.  
    **Estimated saving:** **under 1 second normally; unbounded starvation under sustained input; low confidence.** The 1,000-ms `poll` timeout is **not** a fixed one-second delay—ready sockets wake it immediately.

32. **Durability barriers serialize mutations, but ordinary tests explicitly disable them.**  
    **Where:** `Session.lean:115`, `:140`, `:142`.  
    **Cost / frequency:** Default durability performs **two fsync barriers per durable batch**, ordered store then chain. `full` adds drive-cache barriers. Cost depends on storage latency rather than O/H/R; the server cannot process another request meanwhile.  
    **Fix:** Keep test journals on `sync: "none"` except dedicated durability tests. Production optimization requires group commit while preserving the store-before-chain durability ordering.  
    **Estimated saving:** **approximately 0–1 second for ordinary suite execution; potentially minutes if a broad fixture accidentally uses fsync/full; high confidence that current normal helpers use `none`.**