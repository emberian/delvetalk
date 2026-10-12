**The main problem in this facet is repeated work over retained state:** entry reads rehash and decode whole records; segments rescan their accumulated heap; writes re-encode whole edited relations; suspensions repeatedly walk closure terms.

I did not run builds or tests or modify files. The savings below are **rough estimates for suite wall time, not measurements**, and overlap. Confidence is shown as **mechanism / timing**. This facet alone does not establish where all of the roughly **570 additional seconds** went.

Notation: **H** journal height; **O** objects; **R** relation rows; **D** data nodes; **B** encoded bytes; **K** heap cells; **Y** segments/yields; **C** closure term nodes; **S** call sites; **M** source modules; **U** distinct package pins; **W** served worlds.

1. **Uncached journal reads amplify source and checkpoint resolution — estimated saving: 10–40 s; confidence: high / low.**  
   **Locations:** `Host/Blocks.lean:89–96`; callers `Host/Snapshot.lean:311`, `Host/Carry.lean:111`, `Host/Snapshot.lean:375`; underlying resolvers `Host/Ops.lean:1568–1575`.  
   **Cost/frequency:** Every stored-entry lookup performs synchronous `pread`, SHA-256 over **B**, and a complete CBOR decode. Resolving one source additionally checks **every source in its containing entry**; resolving one checkpoint block checks every block there. Snapshot installation repeats this per object/module: shared inputs can cause **O×M** reads of the same records. Runs per receipt/history lookup, checkpoint expansion, reopen, and carry.  
   **Fix:** Add a bounded, byte-budgeted cache of verified decoded entries, plus source-CID→text and block-CID→tokens caches. Cache successful immutable reads; retain explicit verification paths for corruption tests.

2. **Every segment rescans the entire accumulated heap — 10–35 s; high / low.**  
   **Locations:** `Turn.lean:478–483`, `593`; callees `ObjectiveBendDemandData.lean:284–297`.  
   **Cost/frequency:** `forcedRows` converts/scans **K** cells; `storedReach` scans them again with list lookups costing up to **K×relation-count**. Previously forced rows are fetched and measured again. Runs after **every segment**, including turns with no stored relations. Since in-process resumptions retain their heap, growing segments can incur **ΣKᵢ**, or **Θ(Y²)** for constant heap growth.  
   **Fix:** Record forced rows and maximum reaches as transitions happen. Emit segment deltas and merge them into the host’s root set. Immediately return empty reads when the store has no relations.

3. **Yield identification serializes mismatching call-site terms — 5–30 s; high / low.**  
   **Locations:** `Turn.lean:296–300`, `381`; equality implementation `ObjectiveBendCheckpointV3.lean:35`.  
   **Cost/frequency:** Every message yield searches up to **S** sites. Pointer equality helps the matching term; mismatches encode both terms before comparing. Worst cost is **Θ(S×C)** term work and temporary tokens per yield, hence **Θ(Y×S×C)** per turn.  
   **Fix:** Give each perform a stable site identifier carried into its yielded cell, or index sites by a precomputed term identifier/hash with equality checking only inside the matching bucket.

4. **Cell bounds and storage charging repeatedly encode whole edited relations — 5–25 s; high / low.**  
   **Locations:** `Turn.lean:517–538`; callers `Host/Ops.lean:2478`, `3187–3191`.  
   **Cost/frequency:** The bound encodes every row of each edited relation. Storage charging then encodes all old rows into a hash set and all new rows again, plus scalar encodings. One-row insertion costs **Θ(R + relation bytes)**, rather than the inserted row’s size. Appending **N** rows individually costs **Θ(N²)** cumulative row processing. Runs per admitted write, creation, and replayed write.  
   **Fix:** Maintain canonical bytes/size per immutable cell. Derive changed rows from admitted edits and retention evictions; validate and charge those cells only. Use the exact size function for bounds instead of allocating encoded byte arrays.

5. **Checkpoint preparation repeats collection, term analysis, and overlapping row materialization — 5–25 s; high / low.**  
   **Locations:** `Turn.lean:336–337`, `651–673`; caller `Host/TurnLoop.lean:288–293`.  
   **Cost/frequency:** `materializeStored` calls `checkpoint`, then `Suspension.checkpoint` calls it again. Each invokes settle→collect→trim→collect. Trimming walks each retained closure’s term; encoding hashes closure terms again through dictionary lookup. Cost includes heap/edges plus **Σ retained-term sizes**, potentially **K×C**. Each unforced stored part is also measured, fetched again, and rebuilt; overlapping spines repeat the same rows. Runs per durable suspension and externally returned checkpoint.  
   **Fix:** Represent a prepared checkpoint explicitly and reuse it. Cache term hashes/free-variable masks by program term ID. Memoize materialized relation slices and row sizes; deduplicate repeated field collection with a set.

6. **Sealing and appending independently canonicalize each entry — 3–15 s; high / low.**  
   **Locations:** `Host/Journal.lean:15–19`; `Host/Blocks.lean:61–62`; `Host/Session.lean:167–170`.  
   **Cost/frequency:** Sealing builds canonical bytes to compute the CID, then discards them. Durability encodes the same body again for storage. Each encoding traverses **B** and sorts JSON-object keys. Runs for every journaled entry, including settling deliveries and suspensions.  
   **Fix:** Seal into `{entry, canonicalRecord, cid}` and carry those bytes through the fresh-entry queue to append. Keep the public JSON representation separate from the retained record bytes.

7. **Carry does not retain the old build when an object moves — 3–15 s; high / low.**  
   **Locations:** `Host/Carry.lean:87–88`, `271`, `327–347`.  
   **Cost/frequency:** A moved object caches **b′**, its new build, but not **b**, its old build. Subsequent objects sharing the old package repeat `compileObject`: cold compilation or disk-cache packet decoding/type checking. Cost can approach **O×old-build cost**, instead of **U×old-build cost**. Failed new builds and migrations also repeat across matching objects. Runs per carry test/command.  
   **Fix:** Cache the old build immediately after `rebuilt`, before attempting the move. Maintain carry-local caches for transformed inputs, new builds, failed builds, and compiled migrations; keep state-dependent migration execution per object.

8. **Whole-state CIDs traverse unchanged rows and are recomputed at several boundaries — 3–15 s; high / low.**  
   **Locations:** `Host/Snapshot.lean:181`, `315`, `502`; `Host/Carry.lean:94`, `304`, `487–488`; producer `Host/Ops.lean:423`, `3357`.  
   **Cost/frequency:** `stateCid` constructs tagged wire JSON, canonicalizes it, and hashes the **entire state**. Snapshot installation hashes a state, then anchor checking hashes it again. Carry hashes canonical/original states and later hashes them again for validation. Ordinary writes also hash every retained row. Cost **Θ(state B)** per invocation; cumulative growing-state writes are quadratic.  
   **Fix:** Cache each version’s state CID and reuse the already-validated snapshot CID during anchor comparison. Stream the existing tagged encoding directly into hashing. Sublinear changed-cell hashing would require an explicitly versioned Merkle representation; substituting `Canonical.cidOf` would change existing identities.

9. **JSON turn endpoints rebuild the program dictionary per request — 2–10 s; high / low.**  
   **Locations:** `Turn.lean:722`, `744`, `777`, `798`, `801`.  
   **Cost/frequency:** `startEntryJson` and `resumeEntryJson` do not supply the optional dictionary, so each constructs it over **C** program nodes. A profiled resume constructs it again. Runs per stateless `turn-start`/`turn-resume`, including checkpoint-adversary tests. The ordinary hosted path already supplies a cached dictionary.  
   **Fix:** Store the dictionary alongside the checked entry in `PackageSession`, and pass it into both JSON endpoints.

10. **Admission and conformance perform repeated data walks — 2–10 s; high / low.**  
    **Locations:** `Turn.lean:364`, `374`, `420`, `561–568`, `707–721`, `735`, `746`.  
    **Cost/frequency:** Admission walks **D** nodes; `conformsUnder` separately walks them for size and then validation. Universal `Data` arguments additionally repeat well-formedness after conformance already checked it. Record validation uses pairwise name checks and linear type-field lookup: **Θ(Σ field-count²)**. Runs per frame start, response, extracted Plan, and result.  
    **Fix:** Combine bounded size/admission and validation into one traversal. Remove the duplicate universal-Data check; prepare type-field indexes once. Reuse trusted validation results for internal immutable values.

11. **Snapshot writing rehashes shared sources and uses quadratic type deduplication — 1–8 s; high / low.**  
    **Locations:** `Host/Snapshot.lean:54–67`, `170–193`.  
    **Cost/frequency:** `knownByCid` hashes each source in `compactInputs`, then hashes it again when checking membership. This repeats per object even for shared packages. `types.any` costs **O×U**, and `types ++ [...]` costs **U²**. Laws are reparsed per object. Runs per snapshot and fork/carry genesis.  
    **Fix:** Cache compact inputs by `inputsKey`; retain source CIDs. Use a pin-keyed map for types, sorting once at output. Reuse a text-keyed law parse while preserving the round-trip consistency check.

12. **Reopen reads every replayed record twice, and repeated open requests replay again — 1–8 s; high / low.**  
    **Locations:** `Host/Snapshot.lean:532–560`, `569–573`, `694–701`; `Host/Session.lean:260–294`.  
    **Cost/frequency:** Ignore discovery calls `checkedEntry` for every tail record, then replay calls it again: approximately **2×tail bytes**, hashes, decodes, and synchronous reads. Without a snapshot the tail is **H**. Reopening the already-open path still performs the work. Runs per serve start/world, explicit reopen, verify, and ignore rederivation.  
    **Fix:** Retain a journal-derived ignore-act index, or share decoded records between discovery and replay. Provide a separate explicit reload operation so an ordinary repeated open can reuse the held world.

13. **Snapshot anchors repeatedly scan object rows inside a shared genesis — 0.5–5 s; high / low.**  
    **Locations:** `Host/Snapshot.lean:487–505`; helpers `Host/Ops.lean:2794–2796`.  
    **Cost/frequency:** The local `read` map correctly avoids duplicate record reads. However, version, state CID, pin, and law lookup each scan the genesis’s object array. For **O** objects anchored in one fork/carry genesis this is **Θ(O²)** row searching. Created seeds also get rehashed when deriving their anchor CID. Runs per snapshot reopen and carry.  
    **Fix:** Build an object-ID→anchor-facts map once per distinct anchor entry, and reuse cached seed/state CIDs.

14. **Stored lookup probes measure whole rows before projecting their keys — 0.5–5 s; high / low.**  
    **Locations:** `Turn.lean:456–462`, `479–482`.  
    **Cost/frequency:** Each key probe computes `canonicalBytes` of the entire row, then projects its key. Binary search therefore performs **Θ(log R × row-node-count)** work, even for narrow keys. Fetch charging and later read extraction measure rows again. Runs per forced row/key, including profiled executions.  
    **Fix:** Keep validated row sizes and key projections in the committed store. Fetch the key directly; validate a row’s bound when inserting/updating it.

15. **Creating a stored handle first walks every relation — 0.5–5 s; high / low.**  
    **Locations:** `Turn.lean:507–510`, `755–764`; hosted caller `Host/TurnLoop.lean:259–274`.  
    **Cost/frequency:** Relations are stored as list-shaped `Data`; constructing a handle materializes each list into an array to obtain rows/counts. Cost **Θ(total R)** before even a constant-time count or single-row lookup. Runs per frame/card/derived read and JSON stored request.  
    **Fix:** Retain row arrays, counts, and field indexes with the object version; create handles from that representation.

16. **Snapshots serialize the entire growing history index synchronously — 0.5–4 s; high / low.**  
    **Locations:** `Host/Snapshot.lean:88–116`, `221–225`, `264–274`; cadence `Host/Store.lean:198`.  
    **Cost/frequency:** Snapshot creation serializes all receipts, touches, changes, blocks, modules, and live state, then hashes/writes the result before replying. Index size grows with **H**. At cadence **q**, cumulative historical-index serialization is roughly **Θ(H²/q)**. Runs every 1,000 entries by default, explicit snapshots, and after ignores.  
    **Fix:** Separate append-only history indexes from the live-state snapshot, storing immutable index chunks and a manifest. Keep snapshot publication ordered with the journal; avoid rebuilding all history to capture a new live state.

17. **Carry builds full indexes only to discard most of them — 0.2–3 s; high / low.**  
    **Locations:** `Host/Carry.lean:387`, `397–398`; `Host/Snapshot.lean:404–407`.  
    **Cost/frequency:** Carry serializes all `indexJson` indexes, then selects `carriedKeys`. Separately it constructs **H** receipt-hash mappings and flattens every object’s sources, repeatedly hashing shared modules. Runs per carry.  
    **Fix:** Add a serializer for only carried keys; deduplicate inputs before source expansion. Preserve old receipt lookup through immutable origin-index chunks rather than rebuilding a large genesis map.

18. **Carry dependency and result bookkeeping uses repeated list scans — 0.1–2 s; high / low.**  
    **Locations:** `Host/Carry.lean:193–212`, `244–255`, `323–364`, `487`.  
    **Cost/frequency:** Dependency lookup repeatedly searches library/image/own/needed lists: approximately **dependency-edges×module-count**, repeated per object. Appending `moved`, `left`, `dropped`, and `refused` costs quadratic list copying; suspension checks scan moved/left lists; final validation searches moved objects per object. Placed-row matching repeatedly scans and renders old/new clauses.  
    **Fix:** Prepare name-keyed module maps and memoized transformed closures. Use maps/sets for object decisions and arrays or reverse-built lists for output. Compare cached rendered clauses by name.

19. **Every open scans the whole chain and snapshot directory — 0.1–2 s; high / low.**  
    **Locations:** `Host/Snapshot.lean:246–257`, `583–616`, `659`, `688`.  
    **Cost/frequency:** Even with a current snapshot, opening reads/splits/parses **H** chain links and rebuilds the CID index. Snapshot discovery scans all directory entries separately for each world: **W×directory-size**, plus sorting matches. Snapshot pruning scans again. Runs per serve start, reopen, snapshot write, and carry.  
    **Fix:** Persist a validated chain-index checkpoint and read only appended links. Discover snapshot files once per directory at serve start, and maintain each open world’s snapshot list.

20. **Profiling executes the machine a second time — 0.1–1 s; high / medium.**  
    **Locations:** `Profile.lean:58–85`; `Turn.lean:779–781`, `800–805`.  
    **Cost/frequency:** A profiled segment reruns its **transition count**, repeats fetches, allocates kind strings, and updates a tally each step. Profiled resume additionally rechecks/hashes/decodes its checkpoint. Runs only with `profile: true`; I found three explicit test requests.  
    **Fix:** Attribute transitions in the original execution through an optional observer, using enum-indexed counters and formatting names afterward.

21. **Append has two blocking durability barriers and duplicate metadata/link work — 0–1 s in this suite; high / medium.**  
    **Locations:** `Host/Session.lean:135–142`, `177–179`; native reads `Host/Blocks.lean:20–22`; native sync `native/sync.c:13–22`.  
    **Cost/frequency:** A durable request waits for block-store sync, then chain sync. Append also repeats file-size queries and constructs links once for capacity accounting and again for writing. Runs per durable request, batching its settling entries.  
    **Fix:** Retain file lengths and prepared links in the open session. Preserve required durability ordering; use group commit where the API allows it. **This is unlikely to explain the suite regression:** `tests/host.py:122–123` and served-test defaults select `sync: "none"`.

22. **Small bounded scans and allocations still run repeatedly — under 1 s combined; high / low.**  
    **Locations:** `Host/Store.lean:309–311`, `699–700`; `Turn.lean:133–135`, `146`, `184–188`, `495`, `669–673`; `Host/Blocks.lean:113–118`, `138–141`; `Host/Snapshot.lean:542–543`, `702–703`.  
    **Cost/frequency:** Read-policy checks scan allowed principals per access; identity/root bindings rebuild JSON and hashes per lookup/frame; checkpoint preimages walk tokens for lengths and reserve `64×token-count` bytes; scalar extraction scans relation names per field; materialization appends/deduplicates field names; ignore sets use list membership; verification searches snapshot heights. Extending a journal prefix trims **H−prefix-height** entries; `Entries.foldl` reads all **H** records.  
    **Fix:** Use prepared permission/field sets, retained binding digests, a sized token buffer, hash sets for ignore heights, and indexed snapshot heights. Avoid full folds where an existing object/height index answers the request; represent prefix extension without repeatedly trimming a retained suffix.

History limits the attribution: **`ebf68dbe` already removed the original quadratic old-row search**, replacing it with the current hash set. **`e28b0deb` introduced uncached block reads**, but its commit records faster snapshot-based reopening and only a modest append slowdown. **`55ede329` recently added admission and checkpoint-size preflight**, adding traversals on successful paths while removing a duplicate failed-Plan execution. The best first fixes from this facet are **entry/source/block caching, incremental segment-read accounting, and stable call-site IDs**.