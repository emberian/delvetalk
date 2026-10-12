The strongest suspect in this facet is **discarded compilation caches during spell routing and metadata reads**, compounded by **repeated law/citation evaluation introduced with rules, wants, and standing facts**. Normal execution retains its compiled method; several helpers around it discard theirs.

Reviewed `b1fbdded`, read-only, without running builds or tests. The savings below are **rough estimates of suite wall time on the described 16-core machine**, with low confidence unless stated otherwise. They overlap and must not be added. This inspection cannot conclusively attribute the entire additional ~570 seconds.

Notation: **O** objects; **R** relation rows; **A** actions/forms; **U** rules; **V** wants; **C** cited objects; **K** source-closure size; **P** activity segments; **H** machine heap cells; **S** suspensions; **D** pending deliveries; **Jₒ** journal entries touching one object; **B** bytes traversed/encoded. Paths below are relative to `spec/Delvetalk/` unless otherwise specified.

1. **Metadata and routing helpers discard newly compiled definitions.**
   
   **Locations:** `Host/TurnLoop.lean:1116`, `1187`, `1146`, `1110`, `3694`; `Host/Ops.lean:1936`.
   
   **Cost/call:** On an in-memory miss, compilation/lowering/checking of an entry from closure **K**; a disk hit still reads, decodes, checks, and constructs its dictionary. `spellFormsData` runs `views` and `forms` in separate scratch states and retains neither. `declaredLenses`, `heardFits`, `readerActions`, and `cardRendered` likewise discard updated caches. Repeated missing-definition attempts are uncached too.
   
   **Frequency:** Per routed spell, inspection, offered-card lookup, and interpretation card rendering; repeated throughout fresh-town test setup.
   
   **Fix:** Thread the resulting world/cache through these helpers. Cache successful and absent definitions by package inputs and name; cache zero-argument declaration results by package.
   
   **Estimated saving:** **60–180 seconds. Confidence:** high mechanism, low timing.

2. **Successful spells eagerly compute other actions’ admission and failure hints.**
   
   **Locations:** `Host/TurnLoop.lean:1387`, especially `1397`, `1413–1417`; `4011`, `4050`, `4052`; `3395`, `3421`.
   
   **Cost/call:** `castSpell` builds the current card’s usage, target forms, all target action admissions, lenses, and `set` admission before fitting the requested action. When current and target card coincide, much repeats. Inspection independently computes filtered forms twice, plus method admissions. A successful spell in a multi-spell post is routed by `misfitOf`, then routed again by `runOne`.
   
   **Frequency:** Per spell, per inspection; twice per successful segment of a multi-spell request.
   
   **Fix:** Route and fit the named action first. Build usage and hints only on branches returning them. Compute metadata/admission once per card/read context. Have pre-routing return the route for execution.
   
   **Estimated saving:** **30–120 seconds. Confidence:** high mechanism, low timing; overlaps #1 and #3.

3. **Standing facts and citation closures are rebuilt at every judging site.**
   
   **Locations:** `Host/TurnLoop.lean:1134`, `1322`; `Host/Ops.lean:1982`, `1988`, `2007`, `2012`, `2017`, `2544`, `3104`.
   
   **Cost/call:** Citation traversal reparses cited texts and uses list membership/deduplication. `standings` then traverses each of the **C** cited objects’ own closures again. `methodAdmits` and `kindAdmits` explicitly compute `citedStates` twice. These facts are constructed even when the evaluated conditions never read `request.laws` or `request.refusedBy`.
   
   **Frequency:** Per action admission, change judgment, want evaluation, amendment, and creation.
   
   **Fix:** Cache parsed cited text and citation closure by immutable law text plus dependency versions. Compute one facts context per object/world view; populate standing facts only when referenced.
   
   **Estimated saving:** **20–90 seconds. Confidence:** high mechanism, low timing.
   
   **Regression:** `02b83db6` added standing construction at every facts site on October 12.

4. **Law row-difference and retention checks are quadratic.**
   
   **Locations:** `Host/Law.lean:265`, `339`, `349`.
   
   **Cost/call:** `changedRows` compares every old row against a list of new row encodings and vice versa: **O(Rold × Rnew)** comparisons, plus encoding and eviction comparisons. `insertOnly` similarly searches all new row encodings for each old row. Growing a relation through **R** individual writes therefore accumulates approximately **O(R³)** comparisons.
   
   **Frequency:** Per matching law judgment; also when these expressions occur in rules, action admission, or wants.
   
   **Fix:** Build canonical row hash sets once per old/new relation, or use the validated edit delta. Preserve actual retention-eviction semantics.
   
   **Estimated saving:** **5–60 seconds. Confidence:** high mechanism, low timing; larger if large-row tests exercise these atoms.
   
   **Regression:** `0d517ed1`, October 10, added `changedRows`.

5. **Relation edits re-key and re-sort the entire existing relation.**
   
   **Locations:** `Host/Ops.lean:763`, `793`, `818`; reached from `Host/TurnLoop.lean:302`, `1939` and commit judgment.
   
   **Cost/call:** One insert/upsert first encodes all **R** keys, then `kept` encodes them again and sorts **R+1** rows: **O(R log R)** plus key encoding. **E** edits repeat this **E** times; building a relation one row at a time costs **O(R² log R)** cumulatively.
   
   **Frequency:** Per relation edit during staged reads, dry judgments, commits, and historical reconstruction.
   
   **Fix:** Maintain an ordered relation representation with cached canonical keys; insert/search by key and apply retention incrementally. Validate/sort whole relations at external replacement boundaries.
   
   **Estimated saving:** **5–45 seconds. Confidence:** high mechanism, low timing.

6. **Bend laws, handlers, and action filters admit whole states repeatedly.**
   
   **Locations:** `Host/TurnLoop.lean:1146`, `935`; `Host/Ops.lean:1958`, `2179`, `1189`; `Package.lean:703`.
   
   **Cost/call:** `runPure` computes argument wire sizes and normalizes native arguments. `actions` receives the whole state; a Bend law receives both old/new states and full cited states; a handler receives its whole state on every Plan. Even a scalar-only predicate pays traversal of those states. `lawReads()` also runs during root expansion and again during each Bend judgment.
   
   **Frequency:** Per offered-action filter, per applicable write judgment, per intercepted Plan.
   
   **Fix:** Cache zero-argument `lawReads`; use trusted, already-admitted state arguments or a stored-state execution interface. Memoize `actions` by package, state/version, reader, and context dependencies.
   
   **Estimated saving:** **5–40 seconds. Confidence:** high mechanism, low timing.

7. **Every write scans and encodes existing state in several independent passes.**
   
   **Locations:** `Host/Ops.lean:2472`, `2478`, `3357`, `3370`; `Turn.lean:517`, `528`; `Host/TurnLoop.lean:2462`.
   
   **Cost/call:** Whole-state conformance, all-row checks in edited relations, state CID generation, and changed-cell accounting each traverse state/rows. `changedCellBytes` encodes every old and new row of an edited relation. A sending turn computes `childLedger` again in `sendsJson`.
   
   **Frequency:** Per admitted write; changed-cell accounting twice when sends are emitted.
   
   **Fix:** Carry validated edit deltas, row encodings/sizes, and resulting state CID through judgment. Validate new/changed cells incrementally. Compute the child ledger once and share it with sends and reactions.
   
   **Estimated saving:** **5–35 seconds. Confidence:** high mechanism, low timing.

8. **Interpretation polling reconstructs every pending item from scratch.**
   
   **Locations:** `Host/TurnLoop.lean:4127`, `4132`, `4145`, `4147`, `4152`, `4155`, `4159`.
   
   **Cost/call:** Scans **S** suspensions; expands an interpretation twice; decodes offers; renders a complete card before clipping to 1,400 characters; evaluates wants; walks library pages; executes the policy prompt. All pending items incur this work on every poll, including items whose retry `next` is still in the future.
   
   **Frequency:** Per `world-interpretations` request, until interpretations settle.
   
   **Fix:** Expand once. Cache rendered/prompt material by suspension ID and relevant state/context dependencies. Skip prompt construction for backoff-ineligible items. Support changed-item polling.
   
   **Estimated saving:** **3–30 seconds. Confidence:** high mechanism, low timing.

9. **Want evaluation repeatedly constructs the same carried clauses and facts.**
   
   **Locations:** `Host/Ops.lean:2064`, `2077`, `3104`, `3111`, `3128`, `3294`, `4851`; `Host/TurnLoop.lean:2382`, `3715`.
   
   **Cost/call:** A `posing` call constructs facts through `objectCitations` and `carriedWants`, then reconstructs `carriedWants` for evaluation. `wantRows` constructs facts separately from `posing`. `revealed` calls `wantRows` for each opened want, giving approximately **O(V²)** evaluations when several wants open together. `cardAnswer` checks `wantRows`, then `wantsText` computes it again.
   
   **Frequency:** Twice per updated object at commit; twice per law refusal; again on wants reads, revealing replies, and unanswered prose.
   
   **Fix:** Build one carried-clause/facts bundle and evaluate once. Reuse resulting want rows for filling and rendering. Compare against the retained wanting index where valid; track dependencies for clock/cited-object changes.
   
   **Estimated saving:** **3–25 seconds. Confidence:** high mechanism, low timing.
   
   **Regressions:** `1d39839e` added commit reactions; `02b83db6` added refusal wants; `d2b6c062` added wants to unanswered-card replies.

10. **Stored frames eagerly materialize arrays for every relation.**
    
    **Locations:** `Host/TurnLoop.lean:259`, `272`, `773`, `1610`; `Turn.lean:507`.
    
    **Cost/call:** Walks every relation’s list into an array, **O(total R)**, before knowing which relation or row the method needs. Fetch then linearly searches the relation declarations.
    
    **Frequency:** Every method frame and stored pure render/view.
    
    **Fix:** Keep versioned row arrays/indexes with the object; reuse across frames. Index relation stores by field.
    
    **Estimated saving:** **2–15 seconds. Confidence:** high mechanism, low timing.

11. **Read tracking repeatedly scans the complete growing heap and old reads.**
    
    **Locations:** `Turn.lean:478`, `581`; `spec/bend/Theory/ObjectiveBendDemandData.lean:284`, `291`; `Host/TurnLoop.lean:1718`.
    
    **Cost/call:** Each segment scans **H** cells for forced rows and again for reach. It fetches and sizes all previously forced rows again. Across **P** segments, cost is **O(Σ Hsegment + Σ bytes of previously forced rows)** rather than incremental new reads.
    
    **Frequency:** Every yield and completion, including each immediate Plan response.
    
    **Fix:** Maintain incremental read/reach summaries as stored cells are forced; report only the segment delta.
    
    **Estimated saving:** **1–12 seconds. Confidence:** high mechanism, low timing.

12. **Root/read accumulation performs repeated list scans and quadratic deduplication.**
    
    **Locations:** `Host/TurnLoop.lean:229`, `232`, `242`, `463`; `Host/Ops.lean:224`, `243`, `2092`.
    
    **Cost/call:** Root recording searches, filters, appends, and recounts root/cell lists. `Cells.join` compares accumulated row keys pairwise and repeatedly canonical-encodes them. Across **P** segments and **Q** retained row reads, repeated merging can approach **O(P × Q²)**. Root expansion also searches the root list per citation.
    
    **Frequency:** Per frame, stored segment, explicit view, write, and law-root expansion.
    
    **Fix:** Use ordered hash maps/sets for roots and canonical row keys; maintain root counts incrementally and merge read deltas.
    
    **Estimated saving:** **1–10 seconds. Confidence:** high mechanism, low timing.

13. **Later frames replay the entire staged-write prefix.**
    
    **Locations:** `Host/TurnLoop.lean:300`, `1599`.
    
    **Cost/call:** Reapplies all previously staged edits whenever the object is called again. For **F** frames each staging a write, earlier edits are applied **O(F²)** times; relation-edit cost from #5 multiplies that.
    
    **Frequency:** Per repeated call/frame on an already-written object within a turn.
    
    **Fix:** Maintain a turn-local staged state and update it as writes are staged; retain the edit log separately for commit.
    
    **Estimated saving:** **1–10 seconds. Confidence:** high mechanism, low timing.
    
    **Regression:** `65bcb8e3`, October 12.

14. **Dry judgments repeat complete proposal validation.**
    
    **Locations:** `Host/TurnLoop.lean:967`, `1535`, `1924`, `1976`, `2032`.
    
    **Cost/call:** `world.judge` re-applies all accumulated writes and validates them. Placements and cross-object amendment/reprogram checks run `judge` immediately, then commit judges again. Repeated checks over a growing proposal multiply edit, state, law, and compilation costs.
    
    **Frequency:** Per judge Plan, placement, and cross-object code/law change; again at commit.
    
    **Fix:** Retain validated intermediate states/results keyed by proposal prefix and dependency roots. Reuse at commit only when those dependencies remain valid.
    
    **Estimated saving:** **1–10 seconds. Confidence:** high mechanism, low timing.

15. **Settling repeatedly searches and filters whole queues.**
    
    **Locations:** `Host/TurnLoop.lean:1558`, `3811`, `3825`, `3912`, `3925`; `Host/Ops.lean:2975`, `3044`, `3232`.
    
    **Cost/call:** Searches **S** suspensions from the start per resumption and **D** deliveries per delivery. Consuming a delivery filters the whole pending array; retries and rule-depth lookup search it again. `settleAll` scans suspensions again after each delivered turn.
    
    **Frequency:** After durable requests while queues are nonempty; per delivery/resumption. Up to 64 deliveries and 1,024 resumptions per pass.
    
    **Fix:** Index waiters by slot; order deadlines/backoffs in queues; index deliveries by ID; wake relevant waiters when a slot settles.
    
    **Estimated saving:** **1–10 seconds. Confidence:** high mechanism, low timing.

16. **Moved-root validation reconstructs the same intervening edits repeatedly.**
    
    **Locations:** `Host/Ops.lean:2250`, `2258`, `2280`, `2332`, `2371`; `Host/TurnLoop.lean:3578`.
    
    **Cost/call:** Reads/decodes intervening journal records, then repeats that history walk for individual edits, row roots, and spans. For **Q** checked keys over **ΔJₒ** changes: **O(Q × ΔJₒ)** record work plus key comparisons. Resume prechecking and final judgment may both do it.
    
    **Frequency:** Per moved root during resumption/commit.
    
    **Fix:** Derive one intervening-change summary per object/version pair, with encoded touched-key sets shared across all checks.
    
    **Estimated saving:** **1–8 seconds. Confidence:** high mechanism, low timing.

17. **Journal-backed entries and blocks have no decoded read cache.**
    
    **Locations:** `Host/Blocks.lean:89`; `Host/Ops.lean:1568`, `1573`, `1763`; `Host/TurnLoop.lean:512`, `4122`, `4354`.
    
    **Cost/call:** Each old-entry access performs synchronous `pread`, CID hashing, decoding, and conversion. Every checkpoint block lookup reads its containing entry and validates *all* blocks in that entry. Several requested blocks from one entry therefore repeat the same work.
    
    **Frequency:** Per history/receipt/block lookup and interpretation expansion, including repeated polls.
    
    **Fix:** Add bounded immutable caches keyed by entry CID and block CID; group block requests by containing entry.
    
    **Estimated saving:** **1–8 seconds. Confidence:** high mechanism, low timing.

18. **World wanting pagination evaluates and sorts the complete candidate index.**
    
    **Location:** `Host/Ops.lean:4875`; called by `Host/TurnLoop.lean:2010`.
    
    **Cost/call:** Re-evaluates wants and constructs facts for every readable indexed object before cursor filtering, then sorts all candidate want rows: **O(objects-with-wants × evaluation cost + Vtotal log Vtotal)**. Each indexed want searches the holding-clause list.
    
    **Frequency:** Every `world.wanting`/`world-wanting` page.
    
    **Fix:** Maintain an ordered wanting index; apply cursor/permission filtering before expensive filling. Rejudge through explicit state/clock dependency invalidation.
    
    **Estimated saving:** **1–5 seconds. Confidence:** high mechanism, low timing.

19. **Object enumeration repeatedly scans and sorts the entire world.**
    
    **Locations:** `Host/TurnLoop.lean:1353`, `3079`; `Host/Ops.lean:2672`, `4607`.
    
    **Cost/call:** Listings cost **O(O + matches log matches)** even for a small page. `heardOffers` invokes a listing per door and takes only three results afterward. Folded-ID fallback case-folds every object ID.
    
    **Frequency:** Per listing, per interpreted card’s door, per unresolved/case-folded spell target.
    
    **Fix:** Maintain ordered object IDs and an ambiguity-preserving folded-ID index; range-seek prefixes and stop at the requested limit.
    
    **Estimated saving:** **1–5 seconds. Confidence:** high mechanism, low timing.

20. **Offer construction serializes growing collections and deduplicates quadratically.**
    
    **Locations:** `Host/TurnLoop.lean:3072`, `3084`, `3167`.
    
    **Cost/call:** Serializes the entire accumulated offer list after each added card. Deduplication compares each form against earlier forms, serializing both inside comparisons: approximately **O(A² × form bytes)**. It also invokes the action-filter path inside each form predicate.
    
    **Frequency:** Per prose/misfit interpretation setup.
    
    **Fix:** Encode/hash each form once, deduplicate with a set, maintain cumulative encoded size, and hoist the per-card action filter.
    
    **Estimated saving:** **1–5 seconds. Confidence:** high mechanism, low timing; overlaps #1–3.

21. **History views reconstruct object state from its first retained touch.**
    
    **Locations:** `Host/TurnLoop.lean:2129`; `Host/Ops.lean:4674`.
    
    **Cost/call:** **O(Jₒ)** history records plus accumulated edit application and state hashing. Every repeated historical read reconstructs again; large growing relations magnify the cost.
    
    **Frequency:** Per historical `viewAt` request/Plan.
    
    **Fix:** Cache immutable `(object, version)` states; use periodic object checkpoints and seek the nearest preceding checkpoint.
    
    **Estimated saving:** **1–5 seconds. Confidence:** high mechanism, low timing.

22. **Checkpoint persistence performs several full traversals and repeated encoding.**
    
    **Locations:** `Host/TurnLoop.lean:288`, `1782`, `2586`; `Turn.lean:336`, `651`; `Host/Ops.lean:1595`, `1588`.
    
    **Cost/call:** Collect/settle/trim/collect the heap, measure then materialize stored rows, collect again when constructing checkpoint tokens, serialize tokens for capacity checking, then compact/hash them. Block cutting compresses each item directly and again through `cutHash`.
    
    **Frequency:** Per persisted await/interpret/cross-world suspension.
    
    **Fix:** Carry a collected/materialized checkpoint representation through encoding and sizing; reuse token/item encodings and hashes. Preserve pre-allocation capacity checks.
    
    **Estimated saving:** **1–5 seconds. Confidence:** high mechanism, low timing.

23. **Package checks, closure resolution, and source identities repeat uncached work.**
    
    **Locations:** `Host/TurnLoop.lean:2146`, `2154`; `Host/Ops.lean:939`, `966`, `1003`, `1015`, `1037`, `1902`, `1530`, `1543`.
    
    **Cost/call:** Source/object checks compile the closure anew. `compileEntryIn` resolves library imports and hashes the resolved closure *before* checking the prepared-request cache. Import lookup scans library module lists. Creation paths repeatedly hash source text for compact inputs and source deduplication.
    
    **Frequency:** Per check Plan, definition-cache miss, and creation/reprogram; frequently during test setup.
    
    **Fix:** Cache checks and resolved/prepared requests by existing inputs key plus library pin. Retain module import adjacency and source CIDs.
    
    **Estimated saving:** **1–5 seconds independently**, potentially much more combined with #1. **Confidence:** high mechanism, low timing.

24. **Caches either flush wholesale or stop admitting new entries.**
    
    **Locations:** `Host/TurnLoop.lean:398`, `408`, `4093`; `Host/Ops.lean:1908`, `1952`, `1516`, `3464`; `Host/Store.lean:81`, `163`.
    
    **Cost/call:** Crossing 256 compiled definitions clears the entire definition cache. Prepared requests similarly clear at their bound; build/program caches stop accepting entries when full. A working set over the cap repeatedly incurs closure compilation or disk packet checking.
    
    **Frequency:** Per miss after cache capacity; shared across worlds/caches held in the process.
    
    **Fix:** Use bounded eviction with useful recency/frequency retention rather than clearing or freezing the cache.
    
    **Estimated saving:** **0 seconds unless caps are crossed; 10–60 seconds if they are. Confidence:** high mechanism, low occurrence. Ranked low because this checkout supplies no evidence of actual cap crossing.

25. **Small bounded collections still accumulate quadratic work.**
    
    **Locations:** `Host/TurnLoop.lean:469`, `485`, `643`, `1742`, `2240`, `2255`, `2305`, `2308`; `Host/Ops.lean:2551`, `2564`; `Host/Law.lean:227`, `260`; `Host/TurnLoop.lean:2399`.
    
    **Cost/call:** Repeated list appends, searches, and recomputed totals across writes/sends/awaits/grants/offers; quadratic judgment deduplication with serialized arguments. Count/membership predicates repeatedly convert and scan **R** rows, and some re-encode the comparison value per row. Revealing replies scan rows again for counts and first authors.
    
    **Frequency:** Per corresponding Plan, judgment, predicate, or turn reply.
    
    **Fix:** Use append-efficient builders, retained counters, encoded-key sets, and shared per-evaluation row/count/column summaries.
    
    **Estimated saving:** **0.5–3 seconds. Confidence:** high mechanism, low timing.

26. **Profiling executes each activity segment again.**
    
    **Locations:** `Host/TurnLoop.lean:428`, `1650`, `1719`.
    
    **Cost/call:** With `profile: true`, the normal segment executes, then a profiling run executes its start/resumption again: roughly an additional segment’s evaluation cost.
    
    **Frequency:** Per segment of explicitly profiled turns; the suite’s host integration test exercises this.
    
    **Fix:** Collect the profile during the real execution.
    
    **Estimated saving:** **0–1 second for the current suite. Confidence:** high mechanism, medium estimate.

27. **Adversarial citation graphs can multiply work or block refusal rendering.**
    
    **Locations:** `Host/Law.lean:353`, `374`, `430`, `442`; `Host/Ops.lean:2024`.
    
    **Cost/call:** `followed`, `followedLaws`, and citation validation traverse paths before deduplicating output; a branching graph can revisit shared nodes along **O(branching^depth)** paths, with depth currently four. More seriously, `innermost` recursively follows failing `under` clauses without checking `depth == 0`. If reachable cited state contains a cycle, the depth saturates at zero and refusal explanation can recurse indefinitely.
    
    **Frequency:** Per inherited-law/standing/carried-clause evaluation or citation validation; the blocking case requires cyclic cited text.
    
    **Fix:** Memoize graph traversal with visited nodes/path-cycle detection. Bound `innermost` explicitly and retain the failure trace from the initial evaluation rather than evaluating again.
    
    **Estimated saving:** **~0 seconds for ordinary suite inputs; potentially prevents an indefinite hang for the cyclic input. Confidence:** high code-path finding, low evidence that it affects this slowdown.

The first concrete change I would make is to **retain compilation and declaration caches across routing helpers**, then make `castSpell` build usage only when needed. Next I would consolidate carried clauses/citation facts per judgment and replace the quadratic relation-law comparisons. Those changes target the broadest repeated costs without changing the world’s semantics.