Read-only review of `foundation` at `a3e1fb2`. No edits, builds, or tests were run. Ranked by impact:

1. **P1 — Natural arithmetic can allocate enormous values before any resource refusal.**  
   Evidence: [primitiveResult](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendOpenRecursion.lean:261), [tariff fallback](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendDemandData.lean:141).  
   Forty successive squarings starting at `2` attempt to construct a natural requiring roughly 128 GiB, while each multiplication costs one tick and reserves no bytes. Forcing that computation before returning a Boolean can exhaust the host’s memory despite a small result and ample remaining budget.  
   Smallest fix: preflight natural operations using operand bit lengths, charging work and bounding result allocation before computing. **Owner: kernel.**

2. **P1 — Artifact generation loses fixed-field protection through layers and alias chains.**  
   Evidence: [fixedFields](/Users/ember/dev/delvetalk2/spec/Delvetalk/Package.lean:271), [artifact assignment](/Users/ember/dev/delvetalk2/spec/Delvetalk/Package.lean:357), [host replacement](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1924).  
   A layer without its own `State` inherits `initial()` but emits no `fixed` fields; likewise, `type State = Lib.Shared` loses them when `Shared` aliases `Lib.State`. The host installs that empty list, so subsequent writes lose the fixed-field admission check.  
   Smallest fix: derive fixed fields from the effective State declaration, following layer inheritance and recursively resolving aliases. **Owner: kernel.**

3. **P1 — `turn-resume` accepts an invented continuation with a recomputed digest.**  
   Evidence: [checkpoint validation](/Users/ember/dev/delvetalk2/spec/Delvetalk/Turn.lean:563), [inline checkpoint terms](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendCheckpointV2.lean:166), [resume](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendDemandMachine.lean:342).  
   For an activity with a Nat response site, a caller can encode an empty heap, `yielded 0`, and a condition frame whose branches return `99`, then recompute the public digest and resume with `0`. The kernel returns `99` regardless of the compiled continuation, because it checks neither state provenance nor the yielded address; this is a kernel API failure, not a demonstrated world endpoint bypass.  
   Smallest fix: require a trusted expected checkpoint digest or retained suspension, rather than trusting the digest supplied alongside the tokens. **Owner: kernel.**

4. **P1 — `textHasAny` performs quadratic work under a linear tariff.**  
   Evidence: [membership search](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendOpenRecursion.lean:274), [tariff](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendDemandData.lean:109).  
   A text containing 2,000 `a` words against 2,000 `b` words performs four million failed list-membership comparisons. The primitive charges only roughly 16,000 ticks, contradicting its claimed single-pass cost and allowing substantial work beyond the declared allowance.  
   Smallest fix: build a set of wanted words and charge its construction and lookups. **Owner: kernel.**

5. **P2 — Layered artifacts omit inherited declarations used to determine the public surface.**  
   Evidence: [top-module declares](/Users/ember/dev/delvetalk2/spec/Delvetalk/Package.lean:355), [publicMethods](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1007), [declaredForms](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:490).  
   Creating a layered package whose base declares `methods()` exposing `bump`, while its top layer declares neither `methods()` nor `forms()`, marks the inherited `bump` as a helper. Extending an existing object preserves exposed names separately, but still loses inherited form bounds and source-field metadata because the declaration gate rejects the inherited `forms()`.  
   Smallest fix: compute `declares` from effective declarations across the layer stack, consistent with entry selection. **Owner: kernel.**

6. **P2 — Relation removal sugar changes meaning when the State or field type is aliased.**  
   Evidence: [textual relation detection](/Users/ember/dev/delvetalk2/spec/bend/Compiler/ObjectiveBendParse.lean:1272), [lowerRemove](/Users/ember/dev/delvetalk2/spec/bend/Compiler/ObjectiveBendParse.lean:467).  
   With `type State = Lib.State` containing a keyed relation, `write {rows: remove {id: 1n}}` lowers to `removeItem` rather than `retract`. If rows also contain another column, compilation demands the complete row and refuses the key-only argument that the equivalent explicit `retract` accepts.  
   Smallest fix: lower the removal marker after resolving State field types, using the same relation recognition as derived Edits. **Owner: kernel.**

7. **P2 — Oversized negative JSON integers collide in canonical encoding.**  
   Evidence: [negative integer encoding](/Users/ember/dev/delvetalk2/spec/Delvetalk/Canonical.lean:107), [eight-byte head](/Users/ember/dev/delvetalk2/spec/Delvetalk/Canonical.lean:38).  
   `canonical-encode` gives both `-18446744073709551617` and `-36893488147419103233` the bytes `3b0000000000000000`, because the eight-byte writer discards higher bits. Distinct inputs therefore receive the same CID, and the emitted representation is itself rejected as non-shortest by the decoder.  
   Smallest fix: refuse negative integers outside CBOR’s supported range before calling `head`. **Owner: kernel.**

8. **P2 — The byte budget measures an obsolete encoding rather than canonical bytes.**  
   Evidence: [Boolean materialization](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendDemandData.lean:195), [canonical Boolean encoding](/Users/ember/dev/delvetalk2/spec/Delvetalk/Canonical.lean:73), [budget contract](/Users/ember/dev/delvetalk2/spec/Delvetalk/Limits.lean:24).  
   A pure function returning `true` with `bytes: 1` is refused even though its canonical representation is exactly one byte. Materialization requires two bytes for a Boolean and similarly uses decimal-length accounting for other constructors, so advertised canonical byte limits produce incorrect refusals.  
   Smallest fix: replace materialization’s legacy size accounting with canonical encoded sizes. **Owner: kernel.**

9. **P2 — String equality bypasses the byte-sensitive text tariff.**  
   Evidence: [string equality primitive](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendOpenRecursion.lean:264), [default tariff](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendDemandData.lean:141).  
   Comparing two distinct, equal-length strings differing only in their final byte requires scanning their common prefix. Nevertheless, `labelEqual` costs one tick regardless of string length, so repeated comparisons escape the work accounting applied to other text primitives.  
   Smallest fix: add an operand-byte tariff for `labelEqual`. **Owner: kernel.**

10. **P2 — Failed take/drop preflights return spent scanning work as unused ticks.**  
    Evidence: [prefix scan](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendDemandData.lean:88), [preflightRemaining](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendDemandData.lean:147), [failure branch](/Users/ember/dev/delvetalk2/spec/bend/Theory/ObjectiveBendDemandData.lean:168).  
    At a `textTake` step with nine ticks, requesting 100 scalars from a sufficiently long string scans five scalars before failing preflight. The runner returns all nine ticks unchanged, so reported usage omits that work; only span/break failures consume their preflight allowance.  
    Smallest fix: account for take/drop preflight scans on failure, as span/break already do. **Owner: kernel.**