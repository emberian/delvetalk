The strongest explanation in this facet is **workload multiplication combined with serial execution**: fresh towns repeat genesis and compilation; the archive now includes a large replay matrix; and several request paths multiply one logical operation into many host reads.

I ran no builds or tests. Counts below come from source and fixture inspection. Savings are **static estimates for a 16-core run**, overlap, and should not be added. Confidence refers to the timing estimate; the cited work is present in the code. This facet alone does not conclusively attribute all ten minutes.

Notation: `O` objects, `H` journal height, `Vᵢ` versions of object `i`, `Tᵢ` entries touching it, `C` modules in a closure, `S` source bytes, `R` relation rows, `D` drafts, `A` awaiting files, `P` principals, `W` worlds.

1. **Archive replay matrix repeats expensive work serially — estimated 30–120 s saved; medium confidence.**  
   **Locations:** `tests/test_archive.py:57`; `rehearsal/rehearse.py:388`, `:401`, `:423`, `:564`.  
   **Cost / frequency:** Once per Archive class, after the archive itself finishes: **13 host processes** for straight replay, the live snapshot, four prefix/snapshot/tail cases, a settling cut and verification. The four ordinary cuts collectively replay approximately `4H` entries; straight, settling and verification add roughly another `3H`. Eight cases collect the entire world’s state/history. Each new process loses its in-memory compiler cache. All run sequentially inside `setUpClass`, so extra suite workers cannot shorten this tail.  
   **Fix:** Preserve every replay assertion, but schedule the independent cases as separate jobs over one immutable captured journal, with the runner enforcing the overall worker limit. Share compiled packages between those jobs.

2. **Compiler reuse stops at each test-worker/process boundary — estimated 30–90 s saved when the disk cache is unset; medium confidence.**  
   **Locations:** `tests/run.py:76`, `:111`; `tests/host.py:153`, `:192`, `:196`; `tests/town.py:66`; `spec/Delvetalk/Host/DiskCache.lean:19`.  
   **Cost / frequency:** Each class/chunk gets a Python process; its `_checker`, compile memo and host caches are private. Fresh serves, replay hosts and carry subprocesses recompile common closures and methods: approximately `Σ compile(C, S)` per process. Sharing the binary does not share compilation. Neither the runner nor Makefile establishes `DELVETALK_COMPILE_CACHE`; external configuration may supply it.  
   **Fix:** Establish a shared cache for the exact copied binary and source digests, warm common fixture packages once, and retain loaded checked packets within each process. Keep compilation/cache-integrity tests explicitly isolated.

3. **Full genesis is repeated for tests needing only a small fixture — estimated 15–60 s saved; medium confidence.**  
   **Locations:** `tests/town.py:56`, `:71`, `:74`; `deploy/genesis.py:281`; `tests/test_scenarios.py:32`; `tests/test_rules.py:22`; `tests/test_properties.py:385`, `:400`; `tests/test_http.py:652`.  
   **Cost / frequency:** An empty-town genesis issues **51 synchronous host requests**; furnishing adds **8**, before the test’s own actions. This includes twelve kind-making turns, body installation, eleven shelving turns and four publications, plus resulting deliveries. Rules’ nine tests each build that town; four RandomHour seeds build eight towns. Play and Quota each seed a separate class town. Cost scales with seeded objects/kinds/pages and their closure compilation, rows, rules and wants.  
   **Fix:** Generate and snapshot a baseline once per binary/library/genesis digest, then give tests private journal/snapshot copies. Keep dedicated genesis tests executing the full production sequence. Reuse the same host process across fresh private worlds where appropriate.

4. **Parallelism depends on an absent timing file; fresh-world Arc tests never opt into splitting — estimated 15–60 s saved on a cold runner; medium confidence.**  
   **Locations:** `tests/run.py:55`, `:63`, `:105`, `:118`; `tests/test_scenarios.py:31`; `tests/test_properties.py:380`; `tests/test_rules.py:44`.  
   **Cost / frequency:** Missing timings yield `known={}`, making every class one job. This worktree has no `.timings.json`. Consequently four 200-move RandomHour seeds run sequentially initially. Arc-derived rule tests have fresh worlds but lack `independent=True`, so their classes stay serial even after timing information exists. A class containing one substantial test, such as EveryMethod, also remains indivisible.  
   **Fix:** Supply deterministic initial scheduling weights; split independent seeds immediately; mark Arc tests independent. Partition EveryMethod by object groups while retaining its complete coverage.

5. **`--profile` defeats the binary-pin shortcut — estimated 10–55 s saved in profile runs only; high confidence.**  
   **Locations:** `tests/run.py:81`, `:116`; `deploy/serve.py:27`, `:91`; `spec/Delvetalk/Serve.lean:84`, `:561`.  
   **Cost / frequency:** Every served fixture hashes the tiny counting-wrapper executable and writes its metadata into `binary-pin`. The wrapper then execs the real binary. Serve compares against `IO.appPath`, finds different metadata, and hashes the real binary again: `Θ(binary bytes)` per serve start. The existing comment records **3.3 s for Lean hashing versus 0.2 s for hashlib** on hbox. An unsplit RandomHour class starts sixteen serves across its four seeds.  
   **Fix:** Give `pin_cache` the real binary path independently of the counting executable, or count spawns without wrapping the executable. This is a measurement distortion, not an ordinary-run regression.

6. **Archive launches a new transport interpreter for every window — estimated 8–25 s saved; medium confidence.**  
   **Locations:** `rehearsal/rehearse.py:98`, `:209`, `:211`, `:514`; `tests/test_archive.py:45`.  
   **Cost / frequency:** The fixture produces **98 windows including the three empty tail windows**. Each starts a Python bridge process; windows containing interpretations start another interpreter process. Each pays interpreter/import/configuration/connection setup and discards process-local state. All subprocesses are awaited serially.  
   **Fix:** Call the production bridge/interpreter functions through persistent instances during rehearsal. Keep a small separate CLI test covering subprocess entry points.

7. **Archive performs real durability barriers throughout an offline integration test — estimated 3–20 s saved; low–medium confidence.**  
   **Locations:** `rehearsal/rehearse.py:114`; `transport/state.py:60`, `:69`; `transport/interpret.py:49`, `:57`; `deploy/genesis.py:478`.  
   **Cost / frequency:** Archive explicitly starts serve with `sync='fsync'`. Each journal append synchronizes both blocks and chain (`Session.lean:140`, `:142`). Transport JSON writes also fsync; an interpretation ordinarily writes its cache twice. Unlike `tests.host.Host.send`, the standalone carried-genesis refresh opens without specifying `sync='none'`. Cost is proportional to append/write count, with storage barriers serializing otherwise cheap work.  
   **Fix:** Inject a test durability policy through these paths; use unsynced private journals/files for semantic integration tests and retain focused durability tests using real barriers.

8. **Quota’s no-op sleep still performs 1,488 receipt polls — estimated 2–15 s saved; medium confidence.**  
   **Locations:** `tests/test_http.py:844`; `transport/http.py:87`, `:96`, `:884`.  
   **Cost / frequency:** Forty-eight suspended prose replies each execute all **31 trace iterations**, even though `self.front.sleep` does nothing: **48 × 31 = 1,488 receipt requests**. Each also reads offers and subsequently renders the page. General trace cost is `Θ((wait/step) × unresolved intents)` host requests, plus repeated watch-set sorting.  
   **Fix:** Make trace’s wait budget configurable independently of sleep and use `wait=0` in this quota test. Exercise the quota with the same real turns, inspect the final browser refusal, and test long polling separately.

9. **Complete CID-history checks produce quadratic touched-entry scans — estimated 2–15 s saved; medium confidence.**  
   **Locations:** `tests/test_properties.py:237`, `:392`, `:394`, `:397`; `rehearsal/rehearse.py:360`, `:379`; `spec/Delvetalk/Host/Ops.lean:4646`.  
   **Cost / frequency:** A state comparison sends `Θ(O + ΣVᵢ)` synchronous requests. For each historical version, `stateCidAt` walks that object’s touched entries again: `Θ(Σ VᵢTᵢ)`, commonly quadratic in versions. Current versions additionally hash complete state bytes, including rows. RandomHour repeats comparison three times per seed; Archive repeats it eight times.  
   **Fix:** Maintain a `(object, version) → CID` index during commit/replay and expose a paged bulk history manifest. Continue comparing every version.

10. **Bridge rereads and sorts all historical observations on every poll — estimated 1–8 s saved; medium confidence.**  
    **Locations:** `transport/bridge.py:318`, `:328`, `:333`, `:335`, `:337`; `transport/state.py:98`; `transport/bridge.py:155`, `:231`.  
    **Cost / frequency:** Each poll decodes all observations, sorts them, builds three dictionaries, revisits mention-bearing posts and tests old completion markers. Archive performs a cumulative **95,575 observation visits** for 1,763 posts. Per poll: `Θ(N log N)` observation work, plus repeated principal/mentioned-file reads and up to `Θ(ND)` directory-glob work for draft lookup. `register` rereads the principal set once per principal.  
    **Fix:** Persist a processed-observation cursor/status table; query only unfinished/new rows in creation order. Keep indexed ancestor/author data and load completion/principal sets once per poll.

11. **Carry repeats rebuild, replay and checking in separate processes — estimated 1–8 s saved; medium confidence.**  
    **Locations:** `tests/test_carry.py:62`, `:72`, `:255`, `:290`, `:479`; `transport/carry.py:91`, `:177`, `:194`; `deploy/genesis.py:472`.  
    **Cost / frequency:** Each carry test snapshots, runs an external carry, then opens another fresh verifying host. State-directory carry adds a throwaway checking host and a further refresh host. Per world, checking sends two requests per object and one per old receipt: `Θ(O + H)` serial RPCs, plus package rebuilds and state/row checking. Production carries worlds sequentially. Moves also copies the full image library twice per test.  
    **Fix:** Share the compile cache, batch the object/receipt manifest check, and reuse a checking process across independent private journals. Schedule independent worlds within a bounded worker budget; preserve crash/restart cases using fresh processes.

12. **Public-draft authorization transfers whole states merely to check visibility — estimated 1–6 s saved; low–medium confidence.**  
    **Locations:** `transport/bridge.py:114`, `:194`, `:401`; `transport/http.py:344`, `:353`; `transport/hand.py:247`.  
    **Cost / frequency:** Each public draft makes one `world-view` request per distinct read/written object. Checking `status == viewed` still constructs, serializes, transfers and decodes each complete state: `Θ(Σ state bytes)`, including all relation rows, plus serial RPCs. Runs per admitted draft/HTTP write/resumed offer.  
    **Fix:** Have the host supply the public projection/visibility verdict for the receipt’s offers. Do not replace this with an indefinitely cached authorization decision. Commit `8829c021` introduced the necessary broader checks on October 12 and explicitly identifies host projection as the replacement.

13. **Browser pages eagerly perform several expensive reads; history revisits overlapping windows — estimated 0.5–5 s saved; medium confidence.**  
    **Locations:** `transport/http.py:889`, `:898`, `:917`, `:920`, `:925`, `:928`; `transport/host.py:91`.  
    **Cost / frequency:** Every play page reads card, full state, render and wants. Every object page adds inspect, status and history. History expands windows `20, 80, 320, …`, rereading overlapping suffixes until twenty matches appear or the entire journal is covered. Paint can add **12 further render requests and 3 s waiting** when pending; no-op sleep still leaves those requests.  
    **Fix:** Return one host-owned page projection and add reverse object-history paging capped at twenty matches. Expose a wait budget for painting; ordinary tests should request the immediate result. The unattended-worker guard means the 3 s paint wait is **conditional**, not universal.

14. **Awaiting/outbox maintenance rescans settled files and historical offers — estimated 0.5–3 s saved; medium confidence.**  
    **Locations:** `transport/bridge.py:179`, `:181`, `:184`, `:190`, `:203`, `:279`; `transport/post.py:161`; `transport/state.py:110`.  
    **Cost / frequency:** Every bridge poll reads each awaiting JSON **twice**, including settled files; loads observations again when waiting exists; partitions waiting rows with `Θ(PA)` filtering; rereads offers from each principal’s oldest pending height; and performs repeated outbox globs. `record_sent` and publication handling each load/sort all drafts again.  
    **Fix:** Index awaiting/draft status in SQLite, query unresolved rows once, use direct draft keys, and retain per-principal offer cursors or ask the host for completion by waiting identities.

15. **Fixture/source closures are rebuilt from disk repeatedly — estimated 0.3–2 s saved; medium confidence.**  
    **Locations:** `tests/bend.py:29`; `deploy/seed.py:28`, `:44`; `transport/tables.py:51`; `deploy/genesis.py:263`; `tests/test_properties.py:331`.  
    **Cost / frequency:** Each closure rereads and regex-scans `C` source modules: `Θ(S + import edges)`. Seed creation additionally rediscovers all world modules each call. Genesis repeats this for its creates. EveryMethod reads the complete world source tree twice to collect helper names.  
    **Fix:** Cache the module index, source text/import graph and immutable closures by source digest; make returned structures safe for callers to modify. Read the helper-source corpus once.

16. **Hand pages repeatedly load complete files before applying small limits — estimated 0.2–2 s saved; low–medium confidence.**  
    **Locations:** `transport/hand.py:115`, `:119`, `:153`, `:173`, `:204`, `:289`, `:342`, `:345`, `:454`; `transport/state.py:77`.  
    **Cost / frequency:** A draft lookup parses all `D` draft files. Inbox reads/sorts all observations and resolves their status before retaining forty. `tail(n)` reads the entire hand log before slicing. Spoken loads drafts twice. Object watch fetches **every history page**, then keeps thirty. World listing loads every world’s outbox. Runs per console request/refresh.  
    **Fix:** Direct keyed draft lookup; indexed/paged inbox and log queries; bounded reverse history; materialize shared request data once. Use lightweight per-world pending counts.

17. **Journal helpers read entire chains/stores for small or repeated reads — estimated 0.2–2 s saved; medium confidence.**  
    **Locations:** `transport/journal.py:12`, `:29`, `:53`, `:67`, `:77`; `transport/root.py:92`; `deploy/genesis.py:370`, `:468`.  
    **Cost / frequency:** `records` reads the whole block store and copies every named record; `entries` additionally decodes everything. Historical `tail(before)` parses all `H` links. Snapshot tests copy the whole block store even for prefix journals. Genesis ancestry/opener reads all links merely to obtain the first entry.  
    **Fix:** Stream full traversals; use `pread` for selected records; index chain heights/offsets; read the first complete link directly. Copy only the block prefix needed by a truncated journal.

18. **Identity queries scan growing tables under one lock, with synchronous SQLite writes — estimated 0.1–1.5 s saved; medium confidence.**  
    **Locations:** `transport/identity.py:28`, `:76`, `:94`, `:115`, `:206`, `:250`, `:281`.  
    **Cost / frequency:** Only nonce/name primary-key indexes exist. Authentication scans challenge rows per authenticated request; challenge counts scan by handle/address/time; `_rows` scans and sorts handle history, then filters the credential in Python. Invitation code/principal lookups also scan. Guest authentication writes `used` on every request. Database transactions run under a shared lock; no test durability seam is supplied.  
    **Fix:** Add credential, handle/address/created, invitation-code and principal indexes. Select the supplied credential in SQL. Configure test database durability separately; coalesce last-used updates where the console’s precision permits.

19. **Rate limiting grows its list even for rejected requests — estimated 0.05–0.5 s saved; high confidence.**  
    **Location:** `transport/http.py:362`.  
    **Cost / frequency:** Each request scans and copies every hit within the window, then appends another timestamp even when rejected. `N` requests in one window produce `Θ(N²)` timestamp work under one lock. Runs on every limited request.  
    **Fix:** Use a deque with expiry removal and bounded admission accounting; rejected traffic should not cause an unbounded window-sized allocation.

20. **Merkle-tree root selection scans all previous heights — estimated 0.05–0.5 s saved; medium confidence.**  
    **Locations:** `transport/atproto/mst.py:51`, `:54`, `:97`, `:102`; `transport/repo.py:98`.  
    **Cost / frequency:** Despite cached tree nodes, `top()` computes `max(self.layers)` over all `H` keys. It runs for every appended/signed entry and again during root/export/proof operations. Catching up from empty therefore includes `Θ(H²)` layer comparisons. Incremental `blocks(since)` also walks the whole live tree before filtering.  
    **Fix:** Maintain the highest layer on append and track newly created/replaced blocks for incremental export.

21. **Repository object/law pages make one full object read per candidate — estimated 0.05–0.5 s saved; medium confidence.**  
    **Locations:** `transport/repo.py:266`, `:273`, `:283`; `spec/Delvetalk/Host/Ops.lean:4607`.  
    **Cost / frequency:** Each page performs object listing followed by serial object reads, including an extra lookahead record. Law listing can traverse many objects with no applicable laws before filling a page. Underneath, every `world-objects` page filters all objects and sorts the remaining IDs: `Θ(O log O)` per page.  
    **Fix:** Host-owned paged object/law projections over an ordered ID index; keep authorization in that projection.

22. **Property moves repeatedly request full object/method listings — estimated 0.05–0.5 s saved; medium confidence.**  
    **Locations:** `tests/test_properties.py:231`, `:255`, `:268`, `:270`, `:272`.  
    **Cost / frequency:** Rain/ring/rule moves call `bells()` twice, each issuing `world-objects(methods=True)` and filtering all IDs. That incurs sorting plus method-list construction for objects whose methods the move never uses. Repeated across 200 moves per seed.  
    **Fix:** Fetch bells once per move and omit methods. Maintain the known-object list from committed creations where useful.

23. **Test journal construction repeatedly concatenates immutable bytes — estimated 0.01–0.3 s saved; high confidence.**  
    **Locations:** `tests/wire.py:113`, `:122`; `tests/test_carry.py:175`, `:184`.  
    **Cost / frequency:** `store += raw` copies the complete accumulated block store for every entry: `Θ(HB)` copied bytes, quadratic for equal-size entries. Runs whenever tests forge/rewrite a journal.  
    **Fix:** Write records directly while tracking offsets, or collect chunks and join once. `tests/wire.py:54` also builds a complete matching-field list for each lookup; use a short-circuit lookup or one field dictionary for repeated row extraction.

24. **Measures recompute historical aggregates and cross-product searches — estimated 0.01–0.3 s saved; low confidence.**  
    **Locations:** `transport/measure.py:103`, `:182`, `:192`, `:97`.  
    **Cost / frequency:** Every measures request rereads the journal, observations, drafts, hand log and interpretation files. Each write checks its text against all previously resident-made objects; each answered want checks all hand posts. Group counts repeatedly scan their rows. Cost includes `Θ(writes × made objects × text bytes)` and `Θ(answered wants × hand posts)`.  
    **Fix:** Incrementally maintain aggregates by journal height; index object-name mentions and hand-post time ranges; use counters for grouping.

25. **Watch probes repeatedly parse entire logs — estimated 0.01–0.2 s saved; medium confidence.**  
    **Locations:** `transport/watch.py:25`, `:27`, `:36`, `:38`, `:146`; `transport/model.py:89`.  
    **Cost / frequency:** Each probe reparses access timestamps three times, totals the whole spend ledger twice, loads observations just to count them, and reads the whole watch log before keeping 48 records. Every status/watch invocation pays work proportional to retained log history.  
    **Fix:** Parse timestamps once; calculate hour/day totals together; use database counts and bounded tail reads or incremental counters.

26. **Tables repeatedly load/save complete match history — estimated 0.01–0.2 s saved; low confidence.**  
    **Locations:** `transport/tables.py:168`, `:174`, `:253`, `:261`, `:324`, `:339`, `:352`, `:570`.  
    **Cost / frequency:** A match operation repeatedly loads the same full JSON history, linearly searches rounds, sorts rounds for the latest resolution, and rewrites/fsyncs the complete history at several substeps. Across `Q` rounds, cumulative history serialization is `Θ(Q²)`. A newly displayed board also makes eleven serial row-evaluator requests.  
    **Fix:** Index rounds and latest resolution; load custody once per operation; persist round deltas; expose one board-render operation. Keep necessary crash-consistent intermediate records.

27. **Genesis administration scans unrelated history and repeats input loading — estimated under 0.1 s saved in the current suite; medium confidence.**  
    **Locations:** `deploy/genesis.py:362`, `:376`, `:425`, `:430`, `:438`, `:486`, `:514`; `transport/carry.py:56`.  
    **Cost / frequency:** Refresh reads complete ancestral journals; ancestry repeatedly scans chains for their first entry and prepends to a list. Refresh repeatedly filters all slots and reloads every body/page for each newly missing kind. The no-wipe guard counts every journal line. Carry’s `rglob` descends into library/scratch directories before excluding their files. Runs per refresh/carry/genesis CLI invocation.  
    **Fix:** Direct first-link reads, an indexed last-genesis-text record, slots grouped by object, one inputs load, and directory traversal that prunes excluded subtrees.

28. **Small quadratic text processing remains on posting/rendering paths — estimated under 0.1 s saved; high confidence.**  
    **Locations:** `transport/post.py:31`, `:40`; `transport/pages.py:102`, `:115`.  
    **Cost / frequency:** Mention facets encode the whole preceding text separately for each mention, costing up to `Θ(mentions × text bytes)`, and repeatedly resolve duplicate handles. Card speech repeatedly searches backward through accumulated prose for a spell’s label, worst-case quadratic in lines.  
    **Fix:** Compute byte offsets in one pass, resolve each distinct handle once per post, and maintain the last usable prose-label position while parsing.

29. **Blocking paths can turn one stalled operation into a minute-scale suite tail — normal-run saving approximately 0 s; conditional bounds are large, high confidence.**  
    **Locations:** `tests/run.py:76`; `tests/host.py:114`, `:136`; `transport/host.py:39`, `:65`; `deploy/serve.py:100`, `:109`, `:129`; `tests/test_carry.py:68`, `:297`; `tests/test_http.py:679`, `:935`, `:942`.  
    **Cost / frequency:** The runner has no subprocess deadline; pipe reads have no response deadline. Socket operations allow 150 s; carry tests allow **600 s**; serve startup/shutdown allow 120/60 s. Startup’s nominal 30 s readiness budget can be exceeded by a blocking client call before its next deadline check. Play’s answer polling can sleep 30 s when its expected pending item never appears. The worker-bound test unconditionally sleeps 0.6 s.  
    **Fix:** Apply remaining-time deadlines to reads/connects, impose per-job watchdogs with useful diagnostics, and replace test readiness sleeps with explicit events. No evidence here establishes that a timeout actually caused this particular ten-minute run.

30. **Live model/post workers serialize network latency — estimated suite saving 0 s with the existing mocks; high confidence.**  
    **Locations:** `transport/interpret.py:41`, `:68`, `:81`; `transport/model.py:150`, `:179`; `transport/post.py:95`, `:117`, `:133`; `transport/zulip.py:195`, `:202`; `transport/oauth.py:116`, `:157`.  
    **Cost / frequency:** Every live OAuth model call rereads accounts and invokes `tokeman` with a 60 s timeout; interpretations and paints are asked sequentially, with paints behind all interpretations. Posting holds one world-wide lock across session creation/network calls; Zulip also performs an adoption search on a first attempt. Login repeatedly discovers metadata and scans pending expirations.  
    **Fix:** Cache quota probes/metadata with bounded lifetimes, ask models through a bounded worker pool while submitting results in deterministic order, and use per-intent posting locks with durable reservations.

The most relevant history is `88309087` adding whole-town properties and Archive, `6e5f6a98` multiplying RandomHour into fixed seeds, and `d6571236` adding the post-rehearsal replay matrix. The harness invokes the **Bend compiler inside the host**; I found no per-class Lean build invocation.