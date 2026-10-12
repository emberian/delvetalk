The strongest recent suspect in this facet is **rules and wants adding repeated law parsing, citation traversal, and relation scans to every commit and replay**. RECORD also imposes quadratic admission checks and repeatedly scans relations to render short replies.

I read the assigned files and relevant host implementations and Git history. **No builds or tests were run; no files were changed.** The savings below are rough estimates for the 16-core suite, not measurements. Confidence is high in the identified work, generally low in its wall-time contribution. Estimates overlap and should not be added. This facet alone does **not** establish where all of the additional ~570 seconds went.

Notation: `N` = objects considered; `R` = relation rows; `Q` = rules; `W` = wants; `H` = journal/change height; `C` = citation/package closure size; `B` = text bytes; `F` = fields/forms; `P` = people/parties; `E` = effects.

1. **Inherited laws, rules, and wants are repeatedly parsed and traversed.**
   - **Location:** `world/objects/Kind.obend:119`; `world/objects/Record.obend:145`. Backing paths: `spec/Delvetalk/Host/Ops.lean:2064`, `:3104`, `:3111`, `:3261`; `spec/Delvetalk/Host/Law.lean:353`, `:430`, `:442`.
   - **Cost/call:** Each `carriedRules`/`carriedWants` reconstructs clauses, reparses the object's text, and follows its kind's text. `posing` builds facts and obtains carried wants again. Reactions pose wants before **and** after a write. Admission independently parses `under` text. Cost is repeated `O(B + C)` traversal before condition evaluation; citation lists introduce additional linear searches. Shared citation paths can be traversed repeatedly before final deduplication.
   - **Frequency:** Every affected commit, delivery commit, law refusal that poses wants, and replayed entry; also wants reads.
   - **Fix:** Keep parsed clauses by text digest and resolved inherited clauses by dependency versions. Build facts once per object/version/clock and share them across admission, firing, posing, and spell filling. Traverse citation DAGs with a visited set.
   - **Estimated suite saving:** **30–90 seconds; low timing confidence, high code confidence.**
   - **Regression evidence:** `1d39839e` added commit-time reactions on October 11; `67c5e2cb` and `a02ca9ab` spread rules/wants through the world and inherited kind text. The existing handoff explicitly acknowledges per-commit parsing at `docs/HOST-HANDOFF.md:2085`.

2. **RECORD's `insertOnly` law makes ordinary admission quadratic.**
   - **Location:** `world/objects/Record.obend:145`; backing implementation `spec/Delvetalk/Host/Law.lean:339`.
   - **Cost/call:** For each of `lines`, `admitted`, and `marks`, the host serializes new rows, then searches that linear list for **every old row**. Approximately `O(Rold × Rnew × comparison bytes)`, plus serialization. Even an unchanged relation receives this check. A 768-row bell can require roughly **295,000 membership comparisons** for its lines alone.
   - **Frequency:** Every admitted write to a RECORD and its bodies, including tending, doors, presence changes, and deliveries; replay repeats admission.
   - **Fix:** Fast-path equal field roots. Otherwise merge canonical keyed rows, or judge the actual edits and recorded evictions. Retain verification that replaced/retracted rows are refused.
   - **Estimated suite saving:** **15–60 seconds; low timing confidence, high code confidence.**
   - **History:** RECORD inherited this check with `7b53d7af`; the current list-membership implementation appears in `0d517ed1`. It predates the newest regression but becomes more expensive as more surfaces become RECORD bodies.

3. **RECORD scans the entire remaining relation repeatedly to render eight lines.**
   - **Location:** `world/objects/Record.obend:288`, `:289`, `:318`.
   - **Cost/call:** `Lists.length(rest)` occurs twice per displayed/overflow row. With `s ≤ 9` inspected rows, this walks approximately `2Σ(R−i)` suffix cells, plus filtering all eligible rows. This is `O(sR)`—up to about eighteen suffix passes—not unbounded quadratic because the display cap is fixed.
   - **Frequency:** Every card, `lines`, successful inscription, and body response using `Super.render`.
   - **Fix:** Compute the eligible count once and decrement it while rendering. For `from: 0`, use the relation's stored count. Add an indexed range/page read for other starting numbers.
   - **Estimated suite saving:** **10–30 seconds; low timing confidence, high code confidence.**

4. **Reply rendering reconstructs edits already performed by the host.**
   - **Location:** `world/objects/Record.obend:160`; `world/objects/Thing.obend:75`; `world/bodies/room.obend:128`; `world/bodies/bond.obend:70`. Shared implementation: `world/lib/Relation.obend:150–161`.
   - **Cost/call:** Bend's insertion/upsert walks and reconstructs the preceding rows, performing canonical key comparisons. Retraction uses a full `removeWhere`. These synthetic relations also lose the stored handle's fast count/lookup behavior. Filling a relation through successive writes therefore adds `O(R²)` cumulative traversal before retention.
   - **Frequency:** Every inscription/gesture; room entry, move, departure; bond signatures and withdrawal.
   - **Fix:** Render from the staged state through a host read that preserves stored relation handles, or provide persistent relation edit primitives. Reuse the host's retention result so the reply also reflects rows actually retained.
   - **Estimated suite saving:** **5–20 seconds; low timing confidence, high code confidence.**

5. **`world.check` bypasses compile caches; several workflows compile the same source twice.**
   - **Location:** `world/objects/Workshop.obend:86`, `:101`, `:115`, `:165`, `:181`; `world/objects/Kind.obend:142`.
   - **Cost/call:** Backing `checkSource`/`checkObject` invokes `Package.checkPackage` directly (`Host/Ops.lean:1003–1039`). It parses/elaborates the package closure, rather than using the prepared/build caches. Workshop `propose` checks, then reprograms; a draft checks, then adoption compiles again. Kind creation checks law source repeatedly during genesis.
   - **Frequency:** Each check/proposal/draft/adoption; each nonempty kind-law validation; repeated fixture genesis.
   - **Fix:** Cache diagnostics and prepared compilations by compiler/bounds/library/source digest. Let successful checks supply the prepared artifact to creation/reprogramming. Cache failure diagnostics too.
   - **Estimated suite saving:** **5–20 seconds; low timing confidence, high code confidence.**

6. **The commonplace's eight wants require a world-wide rejudgment and sort.**
   - **Location:** `world/bodies/commonplace.obend:83`; backing `spec/Delvetalk/Host/Ops.lean:4875`.
   - **Cost/call:** Visits every object in the wanting index, reposes all its wants, rebuilds facts again, finds each indexed name in the holding list, fills asks, then sorts **all** surviving rows before applying `limit: 8`. Roughly `O(ΣN[parsing/citations + want conditions + W²] + Wtotal log Wtotal)`. `after` is checked after posing, so pagination does not avoid that evaluation.
   - **Frequency:** Every blank commonplace reply and `since` request. Its pure `render` does not take this path.
   - **Fix:** Maintain wants in height order, invalidate by changed dependencies and clock, and evaluate/cache rows as pages need them. Share facts between posing and ask filling; index holding clauses by name.
   - **Estimated suite saving:** **3–15 seconds; low timing confidence, high code confidence.**
   - **Regression evidence:** `e30dba74` added this call October 12; `7dcad42b` retained it while rearranging the card.

7. **Avatar prose resolution renders every thing in the room sequentially.**
   - **Location:** `world/objects/Avatar.obend:253`, `:257`, `:262`, `:267`, `:284`.
   - **Cost/call:** `T` things cause **T serial `world.card` evaluations**, followed by flattening each complete document merely to get its first line. Each candidate word then scans the name list: `O(ΣT render cost + ΣT document bytes + words×T)`. Fallback additionally issues up to one `inspect` per remaining word.
   - **Frequency:** Every own-avatar prose request except the `look` branch, even when no noun matches.
   - **Fix:** Expose a cheap noun/name projection and cache it by object version. Maintain room name/suffix indexes, preserve ambiguity checks, and inspect only the selected target.
   - **Estimated suite saving:** **2–10 seconds; low timing confidence, high code confidence.**
   - **History:** This structure already existed before `818ff463`; it is an amplification path, not a demonstrated new regression.

8. **KIND and garden render whole collections before displaying eight rows.**
   - **Location:** `world/objects/Kind.obend:242`, `:253`; `world/bodies/garden.obend:90`; `world/lib/Card.obend:120`.
   - **Cost/call:** KIND sorts all instances by `n`, reverses them, then clipping walks the entire mapped list spine to count it: `O(R log R)` comparisons plus `O(R)` traversal; up to 1,024 instances. Garden reverses all its things and clipping counts them, despite showing eight; up to 256.
   - **Frequency:** Every corresponding card/request that renders it.
   - **Fix:** Maintain an index matching the displayed order and read eight rows plus the stored count. Let clipping accept a known total.
   - **Estimated suite saving:** **1–8 seconds; low timing confidence, high code confidence.** Lazy `map` means this does **not** necessarily render every hidden row's text.

9. **A posted scene is parsed up to three times during one creation.**
   - **Location:** `world/bodies/room.obend:251`; `world/objects/Kind.obend:163`, `:93`.
   - **Cost/call:** Room validates the block; KIND validates it again; seed construction parses it again. Each pass scans text, builds passages/choices, and checks targets.
   - **Frequency:** Each room carved from a posted Spween block; ordinary kind scene creation parses twice.
   - **Fix:** Thread the parsed seed through the internal creation path. Retain one validation at the trust boundary.
   - **Estimated suite saving:** **1–5 seconds; low timing confidence, high code confidence.**

10. **Spween accumulates lists and prose quadratically, with limits checked afterward.**
    - **Location:** `world/lib/Spween.obend:132`, `:152`, `:201`, `:206`, `:210`, `:242`, `:257`, `:259`.
    - **Cost/call:** Repeated `Lists.append` makes guards, choices, effects, and passages `O(G² + choices² + E² + passages²)` to construct. Prose concatenation copies the growing passage. Target validation searches all passages per choice: `O(choices×passages)`. Passage/choice/text bounds are checked after construction.
    - **Frequency:** Every scene parse, including oversized adversarial input.
    - **Fix:** Prepend/reverse list accumulators; accumulate prose fragments and join once; enforce bounds while parsing; index passage ids; return nested block and remainder from one traversal instead of `deeper` and `beyond` separately.
    - **Estimated suite saving:** **0.5–4 seconds; low timing confidence, high code confidence.**

11. **Text helpers repeatedly traverse or copy shrinking suffixes.**
    - **Location:** `world/lib/Text.obend:16`, `:22`, `:35`, `:43`, `:51`; `world/lib/Forms.obend:17`; `world/lib/Spween.obend:38`.
    - **Cost/call:** `trimEndOf` removes one trailing character per iteration: `O(B×trailing characters)`. Repeated suffix drops/lengths make splitting `O(B×tokens)` worst case. `indexFrom` can become quadratic with many failed candidate positions; recursive case folding/escaping repeatedly copies suffixes and joined results.
    - **Frequency:** Parsing receives, forms, scenes, library queries, clause lines, and generated rule names.
    - **Fix:** Add cursor-based split/find/trim/case-fold primitives; traverse once and assemble output once. Locally bind repeated break/trim results.
    - **Estimated suite saving:** **0.5–4 seconds; low timing confidence, high code confidence.** These estimates overlap scene/form parsing findings.

12. **Commonplace “what changed” starts from the entire history on every request.**
    - **Location:** `world/bodies/commonplace.obend:76`; backing `spec/Delvetalk/Host/Ops.lean:2308`.
    - **Cost/call:** Walks changes backward, deduplicating objects until 64 readable objects are found or `since` is reached. Worst case `O(H)` when changes repeatedly concern few objects. The Bend card subsequently excludes own cards and keeps eight rows.
    - **Frequency:** Each blank reply and `since` request; blank replies always ask `since: 0`.
    - **Fix:** Maintain latest-change-per-object ordered by height. Push exclusion and requested display size into the query; retain paging semantics.
    - **Estimated suite saving:** **0.5–3 seconds; low timing confidence, high code confidence.** This scans the in-memory change index, not journal bytes.

13. **Room choices produce one yield/write per effect.**
    - **Location:** `world/bodies/room.obend:115`, `:121`, `:138`, `:143`.
    - **Cost/call:** Each effect searches/maps up to 16 variables and appends to the growing edit list: `O(E×vars + E²)`. Applying the result adds `E` sequential `world.write` yields, besides presence/departure writes.
    - **Frequency:** Every choice with effects; repeated scene/property scenarios.
    - **Fix:** Build edits by prepend/reverse and batch the ordered edits into one write operation, preserving sequential effect semantics and whole-turn atomicity.
    - **Estimated suite saving:** **0.5–3 seconds; low timing confidence, high code confidence.**

14. **Library cards sort the same pages twice; fallback lookup retokenizes per page.**
    - **Location:** `world/objects/Library.obend:55`, `:64`, `:66`, `:118`, `:131`, `:132`.
    - **Cost/call:** Rendering and `shelfLine` independently sort pages for walks and ordinary pages: two `O(R log R)` sorts. Failed exact lookup sorts, then reparses `Text.words(said)` inside each page predicate: `O(R×query parsing)`. Shelving a new name scans every page to find the next place.
    - **Frequency:** Every library render, fallback read, failed-read shelf hint, and new shelf operation.
    - **Fix:** Bind one ordered list and partition it; tokenize once; retain an ordered page index and next-place counter.
    - **Estimated suite saving:** **0.5–2 seconds; low timing confidence, high code confidence.** Pages are capped at 32.

15. **Avatar inbox/holding cards scan hidden rows; custody searches an ordinary list.**
    - **Location:** `world/objects/Avatar.obend:129`, `:134`, `:309`, `:314`, `:331`, `:333`.
    - **Cost/call:** Inbox rendering filters/reverses all 64 notes, counts news, then clipping counts again. Holding clipping traverses all held items. Hold/release independently search the holding list; the host's append/removal subsequently traverses it again.
    - **Frequency:** Own-avatar cards and `seen` replies; every custody transfer.
    - **Fix:** Read the newest unread page/count from the existing inbox key; represent holding as a keyed relation; provide counts to clipping.
    - **Estimated suite saving:** **0.3–2 seconds; low timing confidence, high code confidence.**

16. **THING reverses all gesture lines to display three.**
    - **Location:** `world/objects/Thing.obend:280`.
    - **Cost/call:** `take(reverse(rows), 3)` forces a complete traversal before returning anything: `O(R)`, capped at 32 rows.
    - **Frequency:** Every THING card and successful operation that includes its card.
    - **Fix:** Read the last three rows through an ordered relation range; preserve the stored handle.
    - **Estimated suite saving:** **0.2–1 second; low timing confidence, high code confidence.**

17. **Front clocks repeatedly count fill history, in both Bend and rule evaluation.**
    - **Location:** `world/bodies/front.obend:55`, `:65`, `:73`, `:77`, `:79`.
    - **Cost/call:** A fill scans all retained lines. A clock card calls `fills` twice. Its `move` condition can scan new fill lines twice and old fill lines once. Plain law counts also walk rows (`Host/Law.lean:213`); filtered counts allocate/filter them (`:224`).
    - **Frequency:** Every fill, clock render, and commit evaluating its move rule; replay repeats rule evaluation.
    - **Fix:** Maintain/query an aggregate fill count once per state version and share it across condition subexpressions and rendering.
    - **Estimated suite saving:** **0.2–1 second; low timing confidence, high code confidence.**
    - **Regression evidence:** Front introduced in `5e2fea80`, October 12.

18. **Weather reads the entire garden relation and sends rain serially.**
    - **Location:** `world/bodies/weather.obend:72`, `:73`, `:78`, `:79`, `:86`.
    - **Cost/call:** Whole-field view transfers all garden things; filtering can examine all `R` references to find 32 bells. Forecast plus bell sends are sequential yields, and each delivered rain runs admission/reactions. The two `Lists.length(things)` calls repeat a bounded traversal.
    - **Frequency:** Every weather rain triggered by the tide, then each downstream delivery.
    - **Fix:** Query bell references by indexed kind and limit; bind the count once; batch enqueue while preserving per-bell delivered turns and budgets. The intended fan-out itself remains necessary.
    - **Estimated suite saving:** **0.2–1 second; low timing confidence, high code confidence.**

19. **Room cooldown and whisper paths bypass available keyed access.**
    - **Location:** `world/bodies/room.obend:44`, `:69`, `:74`, `:149`, `:191`.
    - **Cost/call:** Entry searches departures by person, searches again to explain refusal, and may filter/count all cooling departures. Leaving searches again. Whisper scans presence for id-or-handle despite its id key. Costs `O(departures + presence)` per operation.
    - **Frequency:** Every entry/departure and whisper; cooldown tests populate 63 departures.
    - **Fix:** Keep departure lookup by person plus a time index; query cooling count by time range; bind found departures; resolve whisper id directly, with a handle index/fallback.
    - **Estimated suite saving:** **0.2–1 second; low timing confidence, high code confidence.**

20. **Bond actions and cards repeatedly parse parties and check every signature.**
    - **Location:** `world/bodies/bond.obend:31`, `:37`, `:45`, `:71`, `:95`, `:100`, `:105`, `:107`.
    - **Cost/call:** Each `party`/`unsigned`/`atRest` reparses parties; each unsigned computation checks all parties' mark keys. A card independently does this through standing, yours, and party lines. Approximately repeated `O(Bparties + P log marks)` on stored relations, potentially `O(P×marks)` after synthetic insertion.
    - **Frequency:** Every bond card/action inspection/signature/withdrawal and `atRest` derived view.
    - **Fix:** Parse fixed parties once; compute signed/unsigned/withdrawn status once per version and reuse it within rendering and action selection.
    - **Estimated suite saving:** **0.1–0.8 second; low timing confidence, high code confidence.** Parties are capped at 15.

21. **The commonplace's menu repeatedly compares every door with every other door.**
    - **Location:** `world/lib/Menu.obend:44`, `:71`, `:73`.
    - **Cost/call:** `isArc(all,d)` scans all doors for each door; each branch scans all doors again to find children: `O(doors²×id bytes)`, followed by branch sizing.
    - **Frequency:** Every pure commonplace card and changed/wants reply.
    - **Fix:** Build the parent/arc grouping once, then render it. Cache the structural part by cites digest.
    - **Estimated suite saving:** **0.1–0.5 second; low timing confidence, high code confidence.** Ordinary cards cap doors at eight.

22. **Default answers inspect the card again and use nested form/field membership scans.**
    - **Location:** `world/lib/Card.obend:247`, `:251`, `:259`, `:275`.
    - **Cost/call:** A usage/incomplete-spell answer yields an `inspect` of itself, then filters forms with `forms×offered` comparisons. Missing-field calculation uses `fields×bindings`. It constructs and sizes complete usage text before deciding whether only the short usage hint fits.
    - **Frequency:** Default blank/incomplete-spell receives across the objects.
    - **Fix:** Reuse the host's already computed offered forms; use membership sets; render usage under a remaining-byte budget and stop early.
    - **Estimated suite saving:** **0.1–0.5 second; low timing confidence, high code confidence.** Silent prose does not force this rendering branch.

23. **Document line extraction has quadratic fragmented-line cases.**
    - **Location:** `world/lib/document/Document.obend:55`, `:61`; caller `world/objects/Policy.obend:112`.
    - **Cost/call:** Splitting repeatedly measures/drops shrinking suffixes. Multiple leaves without newlines repeatedly glue each prefix onto the entire accumulated suffix: `O(B²)` for a long line distributed across many leaves.
    - **Frequency:** `Document.lines`, including policy example indentation and document tests.
    - **Fix:** Split with a cursor and collect fragments for each line, joining once.
    - **Estimated suite saving:** **0.1–0.5 second; low timing confidence, high code confidence.** `Document.plain` already uses linear leaf collection plus `textJoin`; I found no corresponding quadratic plain-text accumulator.

24. **Form/head/diagnostic metadata is reparsed or searched repeatedly.**
    - **Location:** `world/lib/Forms.obend:72`, `:82`, `:91`, `:98`; `world/lib/Card.obend:199`, `:206`; `world/objects/Kind.obend:108`, `:123`, `:230`, `:249`; `world/objects/Workshop.obend:61`, `:65`, `:67`.
    - **Cost/call:** `makeUnder` reparses form text and searches supplied fields once per spec (`O(specs×fields)`). Choice options and ranges are parsed repeatedly. Head filling searches captures per hole and copies suffixes. Kind seeding repeatedly searches the same field list. Diagnostic counting scans for hint markers, and rendering repeats those searches, sometimes twice for one hint.
    - **Frequency:** Every make-under/seed/render, generated kind layer, and failed workshop check.
    - **Fix:** Store parsed fixed metadata; build a field lookup once; bind parsed options/ranges/captures and diagnostic classification. Use cursor/template fragments for head filling.
    - **Estimated suite saving:** **0.1–0.5 second; low timing confidence, high code confidence.**

There are no wall-clock sleeps in the assigned Bend files. Tide's `awaitUntil` and Workshop's interpretation suspend activities; they are not blocking sleeps. Likewise, KIND's create-then-extend performs a second creation preparation, but the backing compiler has build caches, so I would not label every instance an uncached compilation. The primary investigation targets from this facet are **items 1–6**, especially the newly multiplied commit/replay work.