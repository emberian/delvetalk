1. **[P1] Canonical Data collisions let grant holders change fixed arguments.**  
   **Evidence:** `spec/Delvetalk/Canonical.lean:75`, `spec/Delvetalk/Canonical.lean:78`; consumer: `spec/Delvetalk/Host/Ops.lean:1877`.  
   **Failure scenario:** A grant fixes `payload : Data` to `.variant "x" (.natural 1)`. Its holder supplies `.record [("x", .natural 1)]`. Both are well-formed Data and encode as the same CBOR map. Attenuation accepts the substitution and preserves the holder’s value; a method storing the payload receives a different constructor from the one the grantor fixed. Relation edits also treat these values as equal (`Host/Ops.lean:807`), silently dropping replacements.  
   **Smallest fix:** Use constructor-preserving, tagged Data equality for grant attenuation and relation edits.  
   **Owning lane:** kernel, with host consumers.

2. **[P1] Re-exporting a Bend law silently disables its enforcement.**  
   **Evidence:** `spec/Delvetalk/Package.lean:102`, `spec/Delvetalk/Package.lean:180`, `spec/Delvetalk/Package.lean:333`; export resolution: `spec/bend/Compiler/ObjectiveBendElaborate.lean:2914`.  
   **Failure scenario:** Base defines a correctly shaped `law` that refuses strangers’ writes. A wrapper aliases Base’s State, writes `export Base.law`, and defines a public mutating method. The export compiles, but `signaturesOf` ignores every re-export. `lawShape` therefore emits `present: false`, and the wrapper’s object admits writes without running its exported predicate. Exported callable methods similarly disappear from the method table.  
   **Smallest fix:** Collect signatures from resolved declarations, including re-exports, before computing predicate and method metadata.  
   **Owning lane:** kernel.

3. **[P1] A sufficiently long State alias chain removes fixed-field protection.**  
   **Evidence:** `spec/Delvetalk/Package.lean:265`, `spec/Delvetalk/Package.lean:285`; enforcement consumer: `spec/Delvetalk/Host/Ops.lean:2463`.  
   **Failure scenario:** In an M-module package, State reaches an imported record with fixed fields through more than `4*M+4` aliases, while remaining within the generics pass’s 256-level capacity. Compilation resolves the type, but `stateRecordAt` exhausts its smaller fuel and `fixedFields` returns `[]`. After creation, an otherwise law-admitted proposal changes a supposedly fixed field because the host received no fixed-field metadata.  
   **Smallest fix:** Bound resolution by the alias declarations being traversed and refuse unresolved metadata instead of treating it as empty.  
   **Owning lane:** kernel.

4. **[P2] Saving a continuation materializes unread relations before enforcing checkpoint capacity.**  
   **Evidence:** `spec/Delvetalk/Turn.lean:600`, `spec/Delvetalk/Turn.lean:631`; host ordering: `spec/Delvetalk/Host/TurnLoop.lean:1642`, `spec/Delvetalk/Host/TurnLoop.lean:1704`.  
   **Failure scenario:** An object holds 1,024 individually valid 4 KiB rows. Its activity awaits an unresolved slot while retaining the relation for later use. `materializeStored` fetches every unread row and constructs the complete native list without spending ticks or bytes; checkpoint encoding and digesting then process it. Only afterward does `mayWait` reject the checkpoint against its 512 KiB limit. Large stored worlds can impose substantial allocation and work on turns that should refuse early.  
   **Smallest fix:** Apply a shared work and size allowance while materializing, stopping before constructing an oversized checkpoint.  
   **Owning lane:** kernel.

5. **[P2] A layer elsewhere in the closure supplies metadata for an unrelated entry module.**  
   **Evidence:** `spec/bend/Compiler/ObjectiveBendElaborate.lean:2946`, `spec/Delvetalk/Package.lean:334`, `spec/Delvetalk/Package.lean:353`.  
   **Failure scenario:** Supply Base, a layer over Base, then an ordinary Counter module importing that layer. Compile Counter’s own `initial`; its executable is selected correctly, but the artifact’s methods and `declares` come from Base’s layer stack. Counter’s declared `bump` disappears, so its object refuses `bump` as `noMethod`. If Counter lacks a requested entry, selection can instead silently take it from that unrelated stack (`ObjectiveBendElaborate.lean:2882`).  
   **Smallest fix:** Derive the stack from the selected entry module’s ancestry and use it consistently for selection and metadata.  
   **Owning lane:** kernel.

6. **[P2] Diagnosing node exhaustion performs a second, uncharged execution with a trillion-node allowance.**  
   **Evidence:** `spec/Delvetalk/Turn.lean:365`, `spec/Delvetalk/Turn.lean:369`, `spec/Delvetalk/Turn.lean:374`.  
   **Failure scenario:** A yielded message contains a large list of empty records, with `nodes: 1` and ample ticks and bytes. Initial Plan extraction immediately exhausts nodes. To classify the failure, `concludeStep` repeats extraction with `nodes := 1 <<< 40`, walking and allocating the large value despite the requested node limit. The returned `ticksUsed` comes from the first extraction and excludes this diagnostic work.  
   **Smallest fix:** Return the exhausted resource directly from materialization instead of re-executing to infer it.  
   **Owning lane:** kernel.

7. **[P2] Activity argument conformance performs quadratic work outside the turn tariff.**  
   **Evidence:** `spec/Delvetalk/Turn.lean:569`, `spec/Delvetalk/Turn.lean:640`; implementation: `spec/bend/Theory/ObjectiveBendFiniteData.lean:30`.  
   **Failure scenario:** Call an activity accepting Data with a wide record of distinct fields and a tiny tick allowance. Before execution starts, `storedStart` checks conformance and then checks `wellFormed` again. Both traverse the value; record uniqueness uses quadratic `eraseDups`. This work is neither limited nor deducted from the supplied ticks, so even a turn immediately exhausting its machine budget can monopolize the host during admission.  
   **Smallest fix:** Meter activity argument admission, using the bounded admission machinery already available in PackageData.  
   **Owning lane:** kernel.

8. **[P2] Top-level laws, rules and wants make a package impossible to extend by layering.**  
   **Evidence:** `spec/bend/Compiler/ObjectiveBendFrontEnd.lean:502`.  
   **Failure scenario:** Create a package with `rule ring: … then delvetalk …`, then extend it with a layer overriding only `render`. The original package becomes an imported module, and lowering rejects its clause solely because it is outside the final entry module. The same failure occurs for top-level laws and wants, preventing an otherwise type-compatible extension.  
   **Smallest fix:** Permit clauses on the selected layer ancestry and carry their inherited enforcement and ownership explicitly.  
   **Owning lane:** kernel.

9. **[P2] A handwritten `forms()` can silently erase a form block’s bounds.**  
   **Evidence:** `spec/Delvetalk/Generics.lean:1422`; consumers: `spec/Delvetalk/Host/TurnLoop.lean:655`, `spec/Delvetalk/Host/TurnLoop.lean:677`.  
   **Failure scenario:** Declare a public action with a form field `text 0..4`, expose it through `methods()`, and also define `forms()` returning an empty list. Compilation retains the block and its input type but skips deriving the aggregate forms. Runtime validation reads only the handwritten list, so a direct action with five characters is admitted despite the block’s four-character maximum.  
   **Smallest fix:** Refuse handwritten `forms()` alongside form blocks.  
   **Owning lane:** kernel.