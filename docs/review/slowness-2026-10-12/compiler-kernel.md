**The compiler repeatedly pays for whole closures and entry validation. The strongest recent regression candidate is uncached type inference, introduced by `0e3d3bf6` on October 9.** Warm host methods are cached; I did **not** find compilation on every ordinary warm turn.

No builds or tests were run. Estimates below are **wall-time savings for the parallel suite**, inferred from code, not measured. They overlap and must not be added. Confidence concerns the timing estimate; the repeated work itself is directly visible. This facet alone does not establish the cause of all ~570 additional seconds.

Notation: **M** modules, **S** source bytes, **D** expanded declarations, **N** expanded AST nodes, **P** reached entry nodes, **A** annotations, **H** layers, **R** row width, **Q** type nodes. `Prep` means parsing, specialization, elaboration and whole-closure checking; `Entry` means selection, packet construction, checking and pinning.

1. **Inference’s “on demand” types are recomputed actions.**
   - **Locations:** `spec/Delvetalk/Generics.lean:565`, `:590`, `:826`, `:879`, `:905`, `:921`, `:927`, `:937`.
   - **Cost/cadence:** Every demand executes an `M IType` again. A local used **u** times costs **u × synthesis(initializer)**; each demanded record field repeats its expected-type action. Nested inferred dependencies can multiply this work rather than sharing it. Runs throughout every cold closure specialization, including generated instances.
   - **Fix:** Give local bindings and expected types stable IDs and memoize their inference results within the specialization state, including `unknown`. Preserve the current lazy demand order.
   - **Estimated saving:** **30–120 seconds; low confidence.** Git confirms `0e3d3bf6` introduced these action-valued bindings and inference traversal.

2. **Object creation prepares a closure, then the first method prepares it again. Shared library prefixes are repeatedly compiled.**
   - **Locations:** `spec/Delvetalk/Package.lean:213`, `:769`; consumers `spec/Delvetalk/Host/Ops.lean:1411`, `:1907`.
   - **Cost/cadence:** `compileObject` creates a local prepared request without placing it in `w.requests`. The first method subsequently pays another `Prep`. Different packages containing the same library modules each prepare that library again. Repeats per cold package creation, reprogram, replay reconstruction and method warm-up; fresh test processes multiply it.
   - **Fix:** Return and retain the prepared request from object compilation using the same normalized key as method compilation. Cache dependency-bound module preparation and specialization, with entry-specific layer resolution retained.
   - **Estimated saving:** **20–90 seconds; low confidence.**

3. **Every selected entry repeats packet rendering, decoding and type checking after whole-closure checking.**
   - **Locations:** `spec/Delvetalk/Package.lean:364`, `:365`; `spec/bend/Compiler/ObjectiveBendFrontEnd.lean:471`, `:563`, `:571`, `:582`, `:615`.
   - **Cost/cadence:** Once per compiled entry: erase and traverse **P**, build annotations/types and JSON, decode that JSON, then check the reached knot again. Whole-closure checking already checked those declarations. The pin fixture contains **591 entries across 25 modules**; `tests/test_artifact_pins.py:35` explicitly compiles each.
   - **Fix:** First cache compiled entries by prepared-closure key plus entry. Then carry checked declaration evidence through selection, proving the pruning/projection operation, and construct internal checked entries directly. Keep decoder validation at external packet boundaries.
   - **Estimated saving:** **15–60 seconds; low confidence.** `5b078551` introduced the whole-closure-plus-selected-entry arrangement while improving other caching.

4. **Spanless diagnostics can trigger a compilation storm.**
   - **Locations:** `spec/Delvetalk/Package.lean:457`, `:463`, `:467`, `:480`.
   - **Cost/cadence:** `localize` reparses modules and compiles each function against its module prefix until an identical diagnostic appears. Worst case: **Σ functions-in-module × Prep(prefix)**, plus entry work where preparation succeeds. Missing-entry and package-wide refusals can exhaust the search without finding a useful location. Runs per spanless rejected `check-package` or host check.
   - **Fix:** Remove speculative recompilation. Attach declaration locations where failures originate; give package-wide failures a package/module location. A missing entry should immediately name the requested entry.
   - **Estimated saving:** **10–45 seconds; low confidence.** Added by `befd7fb0`; it remains despite subsequent located-diagnostic work.

5. **Declaration tables and emitted knots are assembled quadratically before their hash indexes exist.**
   - **Locations:** `spec/bend/Compiler/ObjectiveBendElaborate.lean:2926`, `:2933`, `:2940`, `:2947`, `:2657`, `:2658`, `:2854`; also `:230`.
   - **Cost/cadence:** Duplicate/target searches repeatedly scan accumulated declarations; `fields ++ [field]` and `rowFields ++ [field]` repeatedly copy growing lists. Approximately **O(D²)** list work per cold elaboration. Generated instances enlarge **D**, up to the 1,024-instance bound.
   - **Fix:** Build indexes during collection and append into arrays or reversed lists. Preserve declaration order with one final conversion.
   - **Estimated saving:** **5–30 seconds; low confidence.**

6. **`check-package` bypasses the prepared and held-entry caches entirely.**
   - **Locations:** `spec/Delvetalk/PackageSession.lean:193`; `spec/Delvetalk/Package.lean:474`, `:479`, `:864`.
   - **Cost/cadence:** Every check pays **Prep + Entry**, even immediately after an identical compile or check. `tests/host.py:202` memoizes only `compile`. The package-bound test checks and then compiles the same large source separately (`tests/test_package_bounds.py:58`, `:60`).
   - **Fix:** Route checks through a shared cached compilation result that retains laws and structured diagnostics. Apply the pure-profile refusal policy after compilation.
   - **Estimated saving:** **5–20 seconds; low confidence.**

7. **The elaborator repeatedly synthesizes subtrees and remaining let bodies.**
   - **Locations:** `spec/bend/Compiler/ObjectiveBendElaborate.lean:1202`, `:1322`, `:1487`, `:1504`, `:1506`, `:1935`, `:2025`, `:2039`, `:2147`.
   - **Cost/cadence:** Effect guards synthesize expressions that elaboration or coercion then synthesizes again. Each nested let synthesizes the remaining body to obtain its codomain; a chain of **k** lets can incur **O(k²)** body visits. Runs per cold closure elaboration.
   - **Fix:** Retain synthesis results by expression ID and binding context, or return type/effect information with elaborated terms. Compute let-tail types once.
   - **Estimated saving:** **3–15 seconds; low confidence.** This machinery predates the newest changes, so it is an amplifier rather than a newly isolated regression.

8. **Cache exhaustion causes wholesale loss of reusable compiler work.**
   - **Locations:** `spec/Delvetalk/PackageSession.lean:62`, `:96`; consumers `spec/Delvetalk/Host/Ops.lean:1908`, `spec/Delvetalk/Host/TurnLoop.lean:398`, `:408`.
   - **Cost/cadence:** The host clears its entire method cache at **256 packets**, and its prepared-request cache at **1,024 requests**. Afterwards previously warm definitions pay `Entry`, potentially `Prep`, again. Stateless caches evict oldest insertions without refreshing hits, allowing hot closures to be displaced.
   - **Fix:** Use bounded LRU eviction of individual entries, with hits refreshing recency. Share immutable compiler caches across serve worlds; currently new world sessions start with `{}` (`Serve.lean:151`).
   - **Estimated saving:** **2–15 seconds; very low confidence.** Requires tests actually crossing these bounds or repeatedly warming separate worlds.

9. **Compiled artifacts repeatedly scan, encode and transport closure-wide material.**
   - **Locations:** `spec/Delvetalk/Package.lean:380`, `:383`, `:385`; `spec/Delvetalk/PackageSession.lean:86`, `:129`.
   - **Cost/cadence:** Every entry hashes its packet, sizes the full artifact, and returns all original sources and all generic-instance metadata. Full-artifact runs then structurally compare the artifact with the held copy: **O(S + packet bytes + instance metadata)** per request. Pin tests repeat full artifact responses across their 591 entries.
   - **Fix:** Keep closure-wide metadata once, reuse its cached sizes/bindings, and use the existing pin-only execution path after compilation. Add a compact compilation-observation response for pin tests.
   - **Estimated saving:** **2–12 seconds; low confidence.** Packet hashing itself is necessary; repeating surrounding material is avoidable.

10. **Package metadata is recomputed for every entry, with recursive re-export scans.**
    - **Locations:** `spec/Delvetalk/Package.lean:307`, `:321`, `:322`, `:368`, `:375`, `:377`, `:395`, `:417`.
    - **Cost/cadence:** Each entry rebuilds signatures, methods, forms, fixed fields, ancestry and law readings. Each re-export recursively computes the origin’s *entire* signature list; sibling exports repeat it. State resolution rescans declarations and aliases. Cost grows with re-export paths, **M**, **D**, **H** and method count; repeated across every entry in a package.
    - **Fix:** Resolve declaration signatures and State identities once in dependency order; cache entry-module metadata in `PreparedRequest`.
    - **Estimated saving:** **1–10 seconds; low confidence.** Recent `78ab4421` and `1de9fd52` extended this metadata work.

11. **Generic call signatures, world methods and inference type texts have no memoization.**
    - **Locations:** `spec/Delvetalk/Generics.lean:331`, `:417`, `:424`, `:504`, `:535`, `:811`.
    - **Cost/cadence:** Each call reparses its declaration’s parameter/result type texts. Every world-method lookup rescans modules, World declarations and protocol methods; input/result texts are resolved again at each site. Roughly **calls × signature-text work**, plus **world-call sites × (M + World declarations + protocol width)**.
    - **Fix:** Cache inference signature skeletons, parsed type texts with binding-sensitive keys, and an indexed world protocol.
    - **Estimated saving:** **1–8 seconds; low confidence.**

12. **Generic derivation initializes and walks the closure twice.**
    - **Locations:** `spec/Delvetalk/Generics.lean:1330`, `:1463`, `:1479`, `:1487`, `:1491`; `:1264`, `:1278`, `:1285`.
    - **Cost/cadence:** Derivation builds names, declarations, sealed identities and indexes; rewriting builds them again after adding derived declarations. Additional passes walk every AST for generic detection and remove lowering. State ancestry/type resolution repeats for fixed checks, derived edits and relation fields. At least several **O(N + S + D)** passes per generic-containing closure.
    - **Fix:** Reuse initial state and dependency identities, extending indexes for derived declarations. Cache effective State fields; use predicates instead of constructing a modified AST solely to detect markers.
    - **Estimated saving:** **1–8 seconds; low confidence.**

13. **Argument byte sizing walks complete materialized values before execution.**
    - **Locations:** `spec/Delvetalk/Package.lean:705`, `:715`, `:716`, `:786`; `spec/bend/Compiler/ObjectiveBendDataWire.lean:47`.
    - **Cost/cadence:** Every native execution traverses all materialized argument rows, fields and strings to compute wire size. JSON-wire execution renders arguments merely to measure them. Stored execution also derives a scalar projection. Cost is **O(materialized rows + fields + text bytes)** per run; sizing cannot benefit from the evaluator ignoring an argument.
    - **Fix:** Carry checked physical sizes with immutable admitted values and scalar projections; use a bounded streaming size calculation at wire admission. Keep the actual byte limit.
    - **Estimated saving:** **1–8 seconds; low confidence.** Stored relation rows are excluded here, so this is not a scan of every stored row.

14. **Library loading and closure assembly repeatedly perform synchronous scans.**
    - **Locations:** `spec/Delvetalk/PackageSession.lean:207`, `:216`; consumers `spec/Delvetalk/Host/Session.lean:64`, `:332`; `Host/Ops.lean:898`, `:931`, `:939`, `:957`.
    - **Cost/cadence:** Every load walks/sorts the directory, reads all library bytes and seals it. Sealing rescans source imports each topological round and searches placed-module lists. Every library expansion scans sources for imports and performs linear module lookups. Blocking work scales with **library bytes**, modules, dependency edges and depth; repeats per library-load, world-open with library, and expanded compile/check request.
    - **Fix:** Seal once per process/library snapshot; retain indexed module sources, import edges and closure results. Explicit library updates should refresh the snapshot.
    - **Estimated saving:** **1–5 seconds; low confidence.** Loading seals sources; it does not itself type-compile the whole library.

15. **Protocol type splitting is quadratic in text length.**
    - **Locations:** `spec/bend/Compiler/ObjectiveBendParse.lean:969`, `:981`, `:986`, `:987`.
    - **Cost/cadence:** `current := current ++ [c]` copies the prefix for every character; `current.getLast?` scans it again at closing brackets. Approximately **O(length²)** per protocol type/parameter text; part accumulation is also quadratic in part count. Runs whenever such source is parsed.
    - **Fix:** Accumulate characters in reverse or use byte offsets/substring ranges; track the preceding character separately.
    - **Estimated saving:** **0.5–5 seconds; low confidence**, especially for maximum-length cases. History traces this path to `b1fe9f80`.

16. **Annotation assembly repeatedly copies paths and annotation prefixes.**
    - **Locations:** `spec/bend/Compiler/ObjectiveBendElaborate.lean:3007`, `:3027`, `:3029`, `:3046`; `ObjectiveBendFrontEnd.lean:289`.
    - **Cost/cadence:** `path ++ [child]` costs current depth at every node: **O(P × depth)**. Concatenating annotation lists can become **O(A²)** on left-heavy trees. Bounds are also accumulated with repeated list append. Runs for whole-closure checking, templates and every entry proposal.
    - **Fix:** Use a reversed path stack and an annotation builder/array; construct bound lists in reverse.
    - **Estimated saving:** **0.5–4 seconds; low confidence.**

17. **Compact encode/decode recompiles the source, then decodes and checks the packet again.**
    - **Locations:** `spec/Delvetalk/Package.lean:600`, `:801`, `:803`, `:804`, `:805`; `PackageSession.lean:193`.
    - **Cost/cadence:** Each `encode-compact` or `decode-compact` falls through to `Package.job`: **Prep + Entry + another packet decode/check**, independently of the held-entry cache. `tests/test_data_type.py:268`–`:272` performs an encode, decode and bad decode against one artifact.
    - **Fix:** Resolve the selection through cached exact-artifact verification and the held entry’s assumptions/type.
    - **Estimated saving:** **0.2–3 seconds; medium confidence.**

18. **Failure explanation repeats inference and resolves all naming types.**
    - **Locations:** `spec/bend/Compiler/ObjectiveBendBlame.lean:68`, `:73`, `:83`, `:345`; `ObjectiveBendFrontEnd.lean:317`, `:320`, `:323`, `:412`, `:416`, `:422`.
    - **Cost/cadence:** After a failed check, explanation re-infers subtrees, then descends and re-infers their descendants: up to **O(N × depth)**. Naming resolves every declared type and compares candidate names for each rendered diagnostic type. Template failures can run multiple checker variants before explanation.
    - **Fix:** Return structured failure evidence from checking; cache naming tables per prepared closure and diagnostic module.
    - **Estimated saving:** **0.2–3 seconds; low confidence.**

19. **Hints reparse every source after a compilation refusal.**
    - **Locations:** `spec/Delvetalk/Package.lean:92`, `:95`, `:96`.
    - **Cost/cadence:** Any non-request refusal without a hint reparses the whole supplied closure, even though preparation already parsed it. **O(S)** plus parser costs per such refusal; some call chains apply `withHint` again if no hint was found.
    - **Fix:** Pass existing ASTs to hint generation and retain an explicit “hint search completed” result.
    - **Estimated saving:** **0.1–2 seconds; low confidence.**

20. **Row comparison and coercion repeatedly normalize or traverse complete types.**
    - **Locations:** `spec/bend/Compiler/ObjectiveBendElaborate.lean:257`, `:264`, `:274`, `:1744`, `:1766`, `:1890`.
    - **Cost/cadence:** `sameTy` canonicalizes both types each time; insertion-based row normalization is worst-case **O(R²)** plus nested types. Each coercion tests `mentionsData` again. Each canonical comparison site generates a fresh type-directed comparator, including sorting row fields.
    - **Fix:** Cache canonical type forms and `containsData` facts; share closed comparator definitions by resolved type and bounds.
    - **Estimated saving:** **0.1–2 seconds; low confidence.**

21. **Closure selection and layer resolution rescan package-wide tables.**
    - **Locations:** `spec/bend/Compiler/ObjectiveBendElaborate.lean:2711`, `:2878`, `:2901`, `:2902`, `:2960`, `:2975`; `ObjectiveBendFrontEnd.lean:504`, `:509`.
    - **Cost/cadence:** Each entry filters all **D** fields/types/templates despite a small reachable knot; reconstructs the full global row; and repeats ancestry/module searches. Layer override collection repeatedly extracts declaration lists for earlier layers. Costs include **O(D)** per entry, **O(HM + H²)** ancestry work and repeated layer declaration scans.
    - **Fix:** Retain the global row, module index, ancestry and function-name sets. Retrieve reached fields by indexed declaration IDs while preserving declaration order.
    - **Estimated saving:** **0.1–2 seconds; low confidence.** Reachability already uses a hash-set worklist; the redundant package scans follow it.

22. **Clause parsing, name checks and readings repeat avoidable work.**
    - **Locations:** `spec/bend/Compiler/ObjectiveBendParse.lean:1236`; `ObjectiveBendElaborate.lean:226`, `:231`; `ObjectiveBendLaw.lean:919`; `spec/Delvetalk/Package.lean:246`.
    - **Cost/cadence:** A source law/rule/want is parsed once by the parser, discarded into source text, and parsed again during conversion. Name validation performs **O((laws + rules + wants)²)** counting, repeated for modules and selected layer stacks. Reading lookup scans the readings list for each law.
    - **Fix:** Preserve parsed clauses in the surface AST; validate names with a set; cache stack clauses and indexed readings.
    - **Estimated saving:** **0.1–1 second; low confidence.**

23. **Remaining bounded quadratic paths.**
    - **Locations:** `spec/Delvetalk/Package.lean:62`, `:67`, `:70`, `:73`; `spec/Delvetalk/Generics.lean:175`, `:187`, `:308`, `:483`, `:702`, `:1517`; `spec/bend/Compiler/ObjectiveBendContract.lean:36`, `:41`, `:98`; `ObjectiveBendC4.lean:139`, `:153`, `:156`, `:165`.
    - **Cost/cadence:** Package assembly repeatedly scans/appends module and import lists; generic resolution scans aliases/modules and serializes argument identities even on instance hits; row unification performs nested field lookup; composition contracts repeatedly compare list-backed rows; C4 repeatedly scans candidates and appends growing output/candidate lists. Per cold preparation: **O(M² + imports×M)**, **O(R²)** unification/contracts, and roughly **O(output² + output×candidate-count²)** C4 list work.
    - **Fix:** Build indexed modules/imports/rows incrementally; cache type-argument identities; use builders and a ready-candidate structure for C4.
    - **Estimated saving:** **under 1 second combined; low confidence.** These matter more at adversarial bounds than in ordinary small packages.

24. **Malformed list-shaped data causes repeated suffix scans.**
    - **Locations:** `spec/bend/Compiler/ObjectiveBendDataWire.lean:17`, `:33`, `:47`, `:84`.
    - **Cost/cadence:** `listItems?` walks a `cons` chain before discovering an improper tail. Rendering/sizing then recursively visits the payload and repeats classification on each suffix: **O(rows²)** for a malformed chain. Proper lists are linear. Runs during argument sizing, result rendering and variant decoding.
    - **Fix:** Classify list-shaped chains once, retaining failed suffix classifications, or combine classification and encoding in one traversal.
    - **Estimated saving:** **under 0.5 second; low confidence.**

The existing reuse mechanisms are real: held runs avoid packet checking, generic instances are indexed, type interning walks shared subtrees once, and `relations()` is memoized by a thunk. The highest-value fixes are to **memoize inference demands, retain prepared closures across creation and method compilation, and eliminate diagnostic recompilation**. Ordinary warm turns should remain compilation-free.