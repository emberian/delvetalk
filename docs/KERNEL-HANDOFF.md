# Kernel

The kernel is the Objective Bend edition: source text to a checked typed packet, a demand machine with a tick
tariff, a checkpoint codec, stored state cells, and the wire and canonical forms. The host (HOST-HANDOFF) calls it
through `Turn.lean` and `Package.lean`; JSON exists only at the process boundary.

- Language: `spec/bend/Compiler/` and `spec/bend/Theory/` (§1); Delvetalk side `spec/Delvetalk/`; driver
  `spec/PackageMain.lean`. Binary `.lake/build/bin/delvetalk-obend`. No `sorry` in `spec/`.
- One dialect (§9): an activity is `Activity<A>` = `computation Message Data A`; its only yields are world calls
  `world.X(arg)` against `world/lib/World.obend`'s `protocol world`, each resumed at its site's type.
- The State is the schema (§10): `Edits`/`keep()` and a form block's input record are derived from `record State`.
- Relations (§12, §15): law atoms, `insert`/`upsert`/`retract`, `canonicalCompare`, `relationCount`,
  `relationLookup`; a state's relations are stored cells the machine fetches row by row.
- Wire (§3): Data JSON on the process boundary; canonical form DAG-CBOR, CID `bafyrei…`.
- Checkpoints (§7): edition v3 only; a checkpoint resumes only against the digest its resumer issued.
- Pins: a world object's pin is the CID of its source closure (host), not `packetSha256`.
  `tests/test_artifact_pins.py` guards that world sources keep compiling (§13).
- Kernel-narrow tests: `test_turn`, `test_canonical`, `test_conformance`, `test_document`, `test_data_type`,
  `test_tariff`, `test_sugar`, `test_layers`, `test_protocols`, `test_stored`, `test_relation`,
  `test_artifact_pins`.
- Open work: §16.

## 0. Working rules

- Build: `LEAN_NUM_THREADS=2 lake build` (one Lean process); on hbox `swarm-build lake build`. `make build` also
  builds the proof-only modules (`PROOF_ONLY`: `Delvetalk.PackageDataAdmission`, `PackageDataNormalization`,
  `PackageDataSchemaProofs`, `Theory.ObjectiveBendNativeDataSimulation`), which are outside the default target;
  build them after touching anything they import.
- Never rebuild while a run uses the binary: `tests/host.py` copies it per run (`DELVETALK_OBEND` names the
  source, `DELVETALK_OBEND_COPY` shares one copy across workers; `tests/run.py` is the parallel runner).
- Run: `DELVETALK_OBEND=$PWD/.lake/build/bin/delvetalk-obend python3 -W ignore -m tests.run [module …]`; whole
  suite `make check`.
- Lean 4.34: `if_pos`/`if_true` deprecation warnings in old Mini files are noise. A doc comment (`/-- -/`) directly
  before `mutual` is a parse error; use `/- -/`. In a file that opens `ObjectiveBendTypes`, a pattern variable
  `label` reads as `Ty.label`; inside `def LawTerm.x`/`LawName.x` a pattern variable `field` reads as the
  constructor `field`: name it otherwise. `x.isDataUnder a b c d` puts `x` at the first `Ty`-typed parameter.
- Host files (`spec/Delvetalk/Host/*`) belong to the host lane; `Journal.lean` is shared.
- A change that moves packets re-records `tests/fixtures/pins/artifacts.json` (§13) with the reason; a change
  that moves tick counts updates the `test_tariff` pin with the reason.

## 1. Map

Pipeline for `compile`: source -> (document templates, text) -> `ObjectiveBendParse` -> `Surface.Module` ->
generics (derivation, inference, specialization) -> `ObjectiveBendElaborate.ofSurface` -> `ATerm` + typing
proposal (`propose`) -> closure check on the direct source (once per package) -> per entry: packet JSON ->
`decodePacket` -> `Typing.check` -> artifact.

| Stage | Where | Notes |
|---|---|---|
| Surface AST | `Compiler/ObjectiveBendSurface.lean` | Typed AST, a `Span` on every node. `Module.json` renders the module JSON (`source-imports-v1`, import transcripts, interface labels, diagnostics). Type annotations are source text. `Module.mapSpans` keeps every field (`layerOver` included). |
| Parser | `Compiler/ObjectiveBendParse.lean` | Declarations `record`, `sum`, `type`, `def`, `protocol`, `law`/`rule`/`want`, `form`, generics `<T>`. Strings use JSON escapes. |
| Front end | `Delvetalk/FrontEnd.lean`, `Generics.lean`, `DocumentTemplate.lean` | `parseSource` = template expansion + parse (spans mapped back by `Expansion.remap`). Generics: rank-1 specialization of sums and defs (generic records do not parse). Doc literals need an explicit `import ./Document.obend as X`. `FrontEnd.Prepared` (parse once, generics, `elaboratePackage`, closure check) is entry-independent; `Prepared.lower` runs per entry. |
| Elaborator | `Compiler/ObjectiveBendElaborate.lean` | Surface to a span-keeping core AST to `ATerm`. Core errors are `Refusal {message, loc, hint, expected, found}`. Recursive record/sum = `Ty.variable i` + a bound. `noActivity` is the "effect in shared position" refusal. |
| Layers | `Compiler/ObjectiveBendC4.lean`, `ObjectiveBendContract.lean` | C4 linearization of a specification chain (published vectors are compiled theorems); the composition contract of a layer chain (`assumes`, `consumes`, `provides`). |
| Driver / `accept` | `Compiler/ObjectiveBendFrontEnd.lean` | `Diagnostic {stage, message, span, sourceModule, hint, definition, expected, found}`. Stages: `objective-source-parse`, `objective-core-elaboration`, `objective-typed-check`, `document-template`, `package-request`. |
| Blame | `Compiler/ObjectiveBendBlame.lean` | `explain`, `locate`, `Naming.render`: diagnostics only; acceptance is `check`'s. |
| Term wire | `Compiler/ObjectiveBendTermWire.lean` | `ATerm.json` <-> `Typing.decodeTerm`. The evaluators' array form differs (§6). |
| Core terms | `Theory/ObjectiveBendOpenRecursion.lean` | `Term` (incl. `unary`, `inject`, `case`, `ifBool`, `perform`, `done`, `toData`, `textJoin`, `refuse`, `relationCount`, `relationLookup`), `Primitive` (with `textHasAny`, `textCanonicalCompare`), `UnaryPrimitive` (natText, textLength, sha256Text), `Step`, `Value`. Text prims, `unary`, `toData`, `textJoin`, `refuse` and the relation forms are hosted extensions, not upstream. |
| Types | `Theory/ObjectiveBendTypes.lean` | `Ty`. `isDataUnder bounds rigid fuel seen` / `isPlanUnder`: non-rigid variables unfold through the packet's `bounds` as a greatest fixed point. `Ty.dataFuel` 4096; `Ty.dataFuelFor bounds type` = max of that and the type's size plus its bounds'. |
| Typing | `Theory/ObjectiveBendTyping.lean` | `PartialTyping`, `infer`, `check`, `decodePacket`, `decodeTerm` (`termNestingCapacity` 4096), `Assumptions {bounds, shareableVariables, rigid}`, `AnnotationTree`, `checkAt`. The `decide`d rule examples at the end are the regression suite for effect rules. |
| Machine | `Theory/ObjectiveBendDemandMachine.lean`, `…MachineFast.lean` | `State {heap, control, stack}`, `Cell` (incl. `native`, `stored`), `Frame`, `Control` (incl. `yielded`, `nativeApplication`, `refused`), `stepRaw`, `runBounded`, `resume`. `Fast` is a proved-equal faster stepper. |
| Data, tariff | `Theory/ObjectiveBendDemandData.lean` | `textStepCost`, `naturalStepCost`, `fetchCost`, `forceHostedFrom` (tick + byte admission and the stored-row fetch before each step), `materializeWith`, `executeStateWith`, `yieldedPlanWith`, `Data.conformsFuel`/`conformsUnder`/`size`. `Data` is in `ObjectiveBendFiniteData.lean`. |
| Checkpoint | `Theory/ObjectiveBendCheckpoint.lean` (the token codec), `…CheckpointV3.lean` (the written edition), `…DemandCollect.lean` | §7. |
| Clauses | `Compiler/ObjectiveBendLaw.lean`, `Delvetalk/Host/Law.lean` | `law`, `rule` and `want` lines over declared state, one grammar (§11); the pure profile refuses laws ("host law adapter"). |
| Typed data/schema | `Delvetalk/PackageData*.lean` | `run-data-v1`, compact codec, schema certificates. Depth is `Bounds.dataWireDepth`. |
| Package, session | `Delvetalk/Package.lean`, `PackageSession.lean`, `Memo.lean`, `spec/PackageMain.lean` | JSON-lines driver (§2); bounded caches (`Memo.boundedInsert` evicts one key, never the map). |
| Turn | `Delvetalk/Turn.lean`, `Entry.lean` | Start, resume, stored cells, reads, state cells (§2, §15). |
| Serve | `Delvetalk/Serve.lean` | `delvetalk-obend serve`: one process holding a directory of worlds (FEDERATION §1). |
| Line check | `Delvetalk/JsonLine.lean` | a driver line's `\uXXXX` escapes are Unicode scalar values. |
| Profiler | `spec/CompileProfile.lean` | `lake build compile-profile`; not a default target (§14). |

Proof obligations by change:
- `Term`/`Primitive`/`Step`: the `Step` lemmas in OpenRecursion (`lazy_fixed_function`, `case_selects_injected_arm`,
  primitive exactness) and `Value` ones; Typing's `PartialTyping` mirrors every constructor; the checkpoint codec
  needs a case (the round trips fail the build otherwise).
- Typing rule: `checked_erasure`, `agree_sameType`, `partial_beta_law`, `reusable_lambda_capture_rule`,
  `sameType_isComputation`, the decided examples.
- Machine: `resume_requires_yield`, `resume_keeps_heap_and_stack`, `perform_under_update_refused`, `perform_yields`,
  and the `Fast` equivalence (`stepRawFast_eq_stepRaw`, `runFrom_eq_runBounded`, `sizesAfter_eq`): a change to
  `stepRaw` needs the matching `stepRawFast`/`sizesAfter` change.
- Collector: a new frame, cell or control holding addresses must be added to
  `frameAddresses`/`cellAddresses`/`controlAddresses` and the renamings, or `related_stepRaw` stops building;
  trimming and erasure (`trimCell`, `eraseCell`, `erase_stepRaw`) need its case; `Term.freeIn`/`markFree` must
  read a new term's variables.
- Schema/compact codec: `PackageDataSchemaProofs.lean`. Native cells: `ObjectiveBendNativeDataSimulation.lean`,
  `ObjectiveBendFiniteDataTyping.lean`. Per-cell conformance: `ObjectiveBendCellConformance.lean`.
- New theorems carry `#assert_axioms` (`Theory/AxiomPin.lean`: `propext`, `Classical.choice`, `Quot.sound`) or,
  for `native_decide` tables, `#assert_compiled`.

Proved:
- `plainV3_roundTrip`, `stateV3_roundTrip` for every dictionary and state; the token codec round trips of terms,
  values, data, frames, controls, walks and stored parts (`ObjectiveBendCheckpointRoundTrip`, `stored_roundTrip`,
  `cellV3_roundTrip`, `frameV3_roundTrip`, `walk_roundTrip`); `refusal_roundTrip`; `encodeTerm_injective`.
- `settle_resume_segment` and the agreement lemmas on the hosted runner (`agree_forceHostedFrom`,
  `agree_materializeWith`, `agree_yieldedPlanWith`, `agree_completeWith`, `agree_trim`, `agree_fetchStep`).
  `typed_settle` is not ported (no state-typing judgment).
- Collector (`DemandCollectProofs`): `related_collect`, `related_stepRaw`, `related_forceHostedFrom` (exact under
  `ExactRoom`, which `limitsPast` gives), `related_fetchStep`, `checkpoint_resume_segment`: resuming
  `checkpoint s` decides the same verdict, spends the same ticks and extracts the same Plan/result Data as resuming
  `s`, for every `fetch`.
- `conformsUnder_iff : d.conformsUnder bounds ty = true ↔ HasType bounds d ty`
  (`ObjectiveBendDataConformance.lean`); fuel is never a false negative.
- Per-cell conformance (`ObjectiveBendCellConformance`: `field_typed_iff`, `relation_typed_iff`,
  `chain_typed_iff`).
- `encode_injective` (§3); `Turn.Site.matches_eq` (§9); `parsed_want_reads_as_it_stands` (§11).
- `sameTypeShared_eq`, `lawTable_names`, `Data.shapeType`/`shape_typing`/`universal_typing`, `SchemaMatches.data`,
  `Admitted.universal`.

Not proved: §16.

## 2. Ops

Wire: one JSON object per line on stdin, one per line out. Errors: `{"status":"error","message":s}`.
`PackageSession.step` keeps two per-process caches: prepared closures (bounded by `Bounds.frontCacheSourceBytes`,
8 MiB of source) and held entries indexed by `packetSha256` (bounded by `Bounds.entryCacheBytes`, 64 MiB of
artifact); a closure or artifact larger than its cache is compiled and not held, never refused. `run`,
`run-data-v1`, `turn-start`, `turn-resume` take `artifact` as the whole artifact (held if equal to the one this
process compiled under that pin, else recompiled and compared) or `{"packetSha256": pin}` alone (held entries
only; "unknown packetSha256: …" otherwise). `world-*` ops go to `Host.stepWorld`. `library-load {path}` and
`library: <pin>` are in HOST-HANDOFF.

| op | takes | returns |
|---|---|---|
| `compile` | `modules:[{name,source}]` or `source`, `entry`, `limits?`, `library?` | `{status:"compiled", artifact}`; artifact = `{schema, modules, sourcesSha256 (CID), entry, genericInstances, limits, packet, packetSha256 (CID), type, methods, law, laws?, …}` (extras below). Compiler refusals: error message is the diagnostic JSON text. |
| `check-package` | as compile | `{status:"checked", artifact}` or `{status:"refused", diagnostic}`. `Package.checkPackage` is the pure entry. A refusal is placed where it arises (a declaration's own at its body, `elaboratePackageM`); nothing is recompiled to place one. A missing entry names itself: `missing selected entry: Kind defines no nope`. |
| `run` | `artifact`, `arguments`, `limits`, `stored?` | `{status:"finished", value, type, ticksUsed, heapCells, nodesUsed, reads?}` or `{status:"refused", failure, …}`. Entry type must be first-order data ("package result must have first-order data type"). |
| `turn-start` | `artifact`, `arguments`, `limits?`, `object`, `principal`, `intent`, `roots` (all required), `stored?` | `finished`, `yielded {plan, planType, responseType, checkpoint, ticksUsed}`, `refused {reason, ticksUsed}` (the program's `refuse`, §8), `exhausted {resource, ticksUsed}` (resource: ticks heap stack nodes bytes), or `error`; each with `reads` on the stored path. The entry must type as `Activity<A>` (§9). |
| `turn-resume` | `artifact`, `checkpoint`, `response`, `limits?`, same binding, `stored?`, `state?` | same replies. Resumes only a checkpoint this process issued (its session keeps the digests it handed out, `Bounds.issuedCheckpoints` 65,536, oldest leaving; else "checkpoint was not issued by this process": a fresh process, or a digest recomputed over edited tokens). Then in order: entry is an activity; `packetSha256`; the tokens hash to the issued digest; object; principal; intent; roots ("checkpoint belongs to another package / digest mismatch / another object / another principal / another intent / was taken under different roots"); decode ("checkpoint does not decode"); response conforms; control is yielded. The response type is re-derived from the artifact. |
| `evaluate-term` | `term` (array wire), `responses?`, `ticks?`, `stored?: {state, relations}` | `{schema, result:{status: value\|yield\|exhausted\|stuck, shape, plans, forced?}}`. Pure reference for conformance; with `stored` it holds the named relation fields as stored cells and answers `forced: [[field, position]]`. |
| `render-document` | `document` (Data wire) | `{status:"rendered", text, lines, bytes}`. |
| `canonical-encode` / `canonical-decode` | `data` or `json`, `repeat?` / `hex` | `{cid, hex, bytes, checksum}` / `{data, cid}`; decode is canonical-only. |
| `source-imports-v1` | modules | import edges. |
| `run-data-v1`, `encode-compact`, `decode-compact` | typed-schema family | see `PackageData.lean` headers. |

`stored: [{field, key}]` (tests and the evaluators' harness; the host calls the Lean functions) holds the first
argument's named relations as stored cells over its own rows (`storeOfState`). `"profile": true` on `run`,
`turn-start`, `turn-resume` returns a tick profile (`Delvetalk/Profile.lean`); not computed on the stored path.

Turn API in Lean (`spec/Delvetalk/Turn.lean`; signatures in §15):
- `startEntry`, `resumeSuspended` (a yield held in process: no encode, digest or decode), `resumeEntry` (a
  `Checkpoint` and `issued`, the digest its caller recorded when it was made: the host's journal or a session's
  issued table; the digest field beside the tokens is never trusted). Each answers `Except String (Step × Reads)`.
- `Step` = `finished | yielded suspension | refused reason ticksUsed | exhausted resource ticks`;
  `Suspension {pin, binding, dictionary, site, state}` holds the machine's state as left, and
  `Suspension.checkpoint` makes the `Checkpoint` only when asked (§7). `Outcome` mirrors `Step`.
- `Binding.make object principal intent roots`. A checkpoint carries its binding and resumes only under the same
  one; the roots digest is the roots at the start of the activity.
- `exhaustedResource` classifies failures: ticks; capacity suspension -> heap/stack by simulating one more
  `stepRaw`, else bytes; `Failure.nodes` (every node check of `materializeWith`) is `exhausted nodes`, apart from
  `Failure.budget` (bytes), so a Plan is never re-materialized to classify. `Budgets {ticks, heap, stack, nodes,
  bytes}`; on resume, heap is counted past the checkpoint's own heap (`limitsPast`).
- Argument admission: every argument is taken natively (`nativeApplication`); each data-typed one is admitted by
  `conformsUnder` ("turn refused: argument does not conform to its type", which the host maps to `typeMismatch`;
  at `Data`, "…does not conform to Data (repeated field)"). `admissionLeft` bounds the conformance and
  well-formedness walks (a visit per node per check, a record's names pairwise) by the turn's ticks and answers
  `exhausted ticks` without the walk; it does not deduct them (§16).
- `refusalText` renders the machine's failures only; a program's refusal is `Step.refused`.

Held entries (`Delvetalk/Entry.lean`): `CheckedEntry {pin, source, checked, fuel, sites}` (`.type`, `.ofPacket`,
`.apply`; `sites` the message call sites, built once, §9). `CheckedEntry.apply` checks a quoted argument term with
`checkAt` at `argumentFuel` = the entry's fuel plus twice the literal's `Term.nodes`; injecting a variant needs a
per-injection `AnnotationTree` shaped like the literal (the checker rejects an unannotated `inject`).
`Package.prepareRequest j`, `Package.compileEntryFrom request entry` (`{artifact, entry, laws}`),
`Package.compileEntry`, `Package.executeDataEntry`, `Package.executeDataEntryStored entry arguments store limits :
Except String (DataExecution × Reads)` (cards and views), `Package.executeEntry`. None decodes the packet or
re-checks the package.

Artifact extras:
- `methods` (`Package.methodTable`; `stackMethodTable` for a layer stack: every layer's methods, top first); a
  method row with a form block carries `form: [{name, kind}]` (§10), a protocol method `protocol: P`.
- `law` shape; `laws: [{name, reading}]` (`Package.lawTable`, one per enforced law, source order, absent without
  laws); `Limits.lawTicks`.
- `relations: [{field, key, limit, retain?}]` (§12); `fixed: [names]` (§10); `declares` (§10); `protocols: [P]`
  (§8); for a message activity `dialect: "message"`, `world`, `worldProtocol` (§9).
- Entry selection, methods, `declares` and law readings follow the entry module's own layer chain
  (`layerAncestry`), not the closure-wide stack; the context's stack still decides package-wide overrides.

## 3. Wire and canonical form

Data JSON (`Compiler/ObjectiveBendDataWire.lean`): `natural` (decimal string), `boolean`, `label`, `record
{fields:[{name,value}]}`, `variant {label,payload}`, `list {items}`; e.g. `{"tag":"natural","value":"123"}`.
`dataJson` emits `list` whenever `listItems?` finds a proper `nil`/`cons` chain. `decodeData` refuses a variant
chain that forms a proper list ("cons chains are no longer accepted on the wire; send a list", `consChainRefusal`);
`PackageData.decode` applies the same rule. Decode depth is nesting, not elements (`Bounds.dataWireDepth` 256;
chains cost 2 levels per cell, arrays do not). A decoded list is a `cons` chain in memory. `dataJsonBytes` must
equal `(dataJson d).compress.utf8ByteSize` (kept in sync by hand).

Canonical bytes (`Delvetalk/Canonical.lean`, DAG-CBOR as AT Protocol):
- Unsigned int, shortest head; Nat >= 2^64 a big-endian byte string; false/true = f4/f5; label = text; JSON null =
  f6; list = definite array; record = definite map with keys sorted by UTF-8 byte length then bytes (a repeated
  field keeps the first); any other variant = the array `[null, label, payload]` (`variantPrefix` 83 f6;
  `variantHead` for a writer that writes the payload itself). No Data item is null, so the bytes tell a variant
  from a record and from a list whatever the type: at `Data` a one-field record cannot pass for a variant.
- `encode_injective` (`#assert_axioms`): `encode a = encode b` and fewer than 2^64 bytes give
  `normalize a = normalize b` (field order, repeated fields), through `writeData_spec` (the ByteArray writer meets
  `encodeList`) and the prefix property `encodeList_prefix`. Decode is untyped and canonical-only (a list written
  as a variant is refused); `decode (encode d) = normalize d` is `#guard`ed, not proved.
- `decode` refuses non-shortest heads, unsorted/duplicate keys, indefinite lengths, tags, floats, null, negative
  ints, non-canonical bignums, bad UTF-8, trailing bytes, by name ("non-canonical CBOR: …", "CBOR nesting
  capacity", "CBOR exceeds the node bound").
- `encodeJson`: objects->maps, arrays, strings, bools, null, ints; a fraction is refused, and so is a negative
  integer below -2^64 ("a negative integer below -2^64 has no canonical form": DAG-CBOR has no negative bignum).
  `cidJson` is total (falls back to the CID of the printed text on an unencodable value).
- CID = `"b" ++ base32lower(0x01 0x71 0x12 0x20 ++ sha256(bytes))`, 59 chars, `bafyrei…`. All 166
  `record`/`cid` pairs in `tests/fixtures/delve/*.json` encode to the AppView's CID; `tests/wire.py` is an
  independent Python encoder.

Digests:
- Journal: `Host/Journal.lean` `bodyHash = cidJson`; `verify` names "journal broken at height N: hash mismatch |
  height out of sequence | previous hash does not chain". Request digests, retry identities, seed digests and
  delivery ids are CIDs too.
- Artifact: `packetSha256` and `sourcesSha256` are CIDs (the names kept). Per-module source hash inside the packet
  is hex SHA-256 of the raw source.
- Checkpoint: `Turn.checkpointDigest` = CID of `{packetSha256, object, principal, intent, rootsDigest, tokens}`,
  written straight from the tokens (§7); `rootsDigest` = CID of `[{object,version}]`. Checked against `issued` in
  `resumeEntry` before decoding.
- State: the CID of the state's block (§15).

## 4. Limits (`spec/Delvetalk/Limits.lean`, namespace `Delvetalk.Bounds`)

Each refusal names its bound and number ("module M exceeds maxModuleBytes (524288 bytes)").

Per machine segment (default / ceiling): `ticks` 100,000 / 1,000,000; `heap` 100,000 / 1,000,000 (cells);
`stack` 10,000 / 100,000 (frames); `nodes` 100,000 / 1,000,000 (Data nodes materialized for a result or Plan);
`bytes` 1 MiB / 16 MiB (the canonical DAG-CBOR size of a result or Plan, `Data.canonicalBytes`, `#guard`ed
against `Canonical.encode`; and the largest single text-primitive or fetch reserve per step). Materialization
spends each scalar's canonical bytes as it is reached and checks the whole value's size once it is whole (a list's
cells cost nothing but its array head). `lawTicks` 100,000. `typeFuelDefault` 16384.

State: `maxCellBytes` 262,144, the canonical bytes of one state cell (§15): the scalar part, or one relation row.

Wire: `dataWireDepth` 256, `plainJsonDepth` 64, `documentWireDepth` 8192, `entryArrowDepth` 64, `maxFrameBytes`
16 MiB (a driver request line, which also holds the artifact a `run` sends back), `issuedCheckpoints` 65,536.

Packages:
- `maxPackageBytes` 128 KiB: one module offered as a program (reprogram, extend, create of source, a `check` Plan,
  a form's `source`). The host's `Host.Limits.maxPackageBytes` and `formSourceMax` are this bound; its refusals
  read "package source exceeds maxPackageBytes (131072 bytes)". The bound is the scale rule, not compile cost: a
  program is also data held whole in one state cell (a kind's body, a Workshop draft, a form's reply), and 128 KiB
  leaves its row the other half of `maxCellBytes`. Every measured size compiles under a second (§14).
- `maxModules` 64, `maxModuleBytes` 512 KiB, `maxPackageSourceBytes` 1 MiB (import scan only),
  `frontCacheSourceBytes` 8 MiB, `entryCacheBytes` 64 MiB.
- `Generics.maxInstances` 1,024 generic instances: the most whose check and compile stay under a second together
  (§14). The refusal names the count, the bound and the declaration that asked, at that declaration: "refused
  (generic-instances): the package needs more than 1024 generic instances; Many.use92 asks for instance 1025,
  removeWhere at Many.R92 (Generics.maxInstances)". `tests/test_package_bounds.py`: a 131,072-byte module
  checks, compiles and runs; the module, import-scan and instance bounds refuse by name.

Documents: `documentDepth` 64, `documentNodes` 65,536, `documentOutputBytes` 1 MiB, `offersPerTurn` 16 (their
text shares the 1 MiB). `Document.maxOffersPerTurn`/`maxOutputBytes` are aliases that `TurnLoop.lean` reads.

Outside `Limits.lean`: `PackageMain` 16 MiB line frame; `EvaluateTerm` nesting 4096, default 200,000 ticks,
`go 64` yields cap; `Canonical` reuses `nodesMax`/`bytesMax`; the host's own `Host.Limits` (`dataDepth` 8192,
`plainDepth` 64, `maxTurnTicks` 1,000,000, `maxCheckpointBytes`, `maxRefusalBytes` 4096, `lawDepth` 4,
`maxLawClauses` 16, `rulesPerCommit` 8, `rulesPerObject` 32; HOST-HANDOFF). Fuel parameters that are not
budgets: `Typing.check` fuel, `Ty.dataFuel`, `termNestingCapacity` 4096, `conformsFuel`, `peelArrows`,
`maxInferenceSteps`. A fuel exhaustion is a refusal, never a wrong answer, but it looks like a type error.

## 5. Tariff

Every machine transition costs 1 tick. Before a text primitive, a large natural operation or a stored-row fetch,
`forceHostedFrom` admits `(ticks, bytes)` and suspends (`ticks` or `capacity`) if either exceeds what is left;
the state is retained exactly. B = byte size of the operand, p = exact bytes of the first n scalars (`prefixCost`,
a scan bounded by what the allowance can pay).

| operation | ticks | reserves |
|---|---|---|
| `textConcat a b` | `1 + 2(|a|+|b|)` | `|a|+|b|` |
| `textTake t n` | 1 if n=0 or n>=B; else `1 + 2p` | `p` |
| `textDrop t n` | 1 if n=0 or n>=B; else `1 + 2p` | `B - p` (the suffix copy is bounded in bytes, not charged in ticks, so a drop-by-one walk stays linear) |
| `textJoin list sep`, each element | `1 + 2*(bytes appended)` | the new accumulator (appended in place when unique) |
| `textSpan`, `textBreak` | `1 + perScalar*visited`, perScalar = `2*(|alphabet|+2)`; refused up front if the cap cannot cover the scan | |
| `textHasAny text words` | `1 + 3(|text|+|words|)` | twice those bytes: a pass over each, then a hash set of the wanted words (`textHasAnyWordFast`, `@[csimp]` equal to the list-membership reference `textHasAnyWord`) probed once per word of the text |
| `labelEqual a b` (text `==`) | `1 + min(|a|,|b|)` | |
| `textLength` | `1+B` | |
| `sha256Text` | `65 + 8*ceil(B/64) + 32*blocks` | |
| `natText n` | `1 + bits^2` | |
| natural `+ - * / %` (`naturalStepCost`) | 1 while both operands are below 2^64; past a word, with x, y the operands' bytes (`log2/8 + 1`), `1 + 2(x+y)` plus `(x/8+1)(y/8+1)` for multiply, divide and modulo | the result's bound (`max+1`, `x`, `x+y`, `x`) |
| a fetched stored row or key (`fetchCost`) | `1 + 2b`, b its canonical bytes | `b` |
| `relationCount` | stored: one transition (the `relationRows` frame); walked: about five a cons cell | |
| `relationLookup` | stored and keyed by its columns: per probe, the key fetch and the probe's `canonicalCompare` (linear in the key), at most `⌊log2 n⌋ + 1` probes, the found row's fetch only when read; walked: the probe per row passed | |
| everything else | 1 | |

A take or drop whose prefix scan cannot be paid spends the whole allowance, as a failed span/break does
(`preflightRemaining`): the scan ran. Repeated squaring is refused at the first unaffordable operand, never built.
A `refuse` of a literal is three transitions.

`tests/test_tariff.py` pins the charges: `NaturalArithmetic`, `CanonicalBytes` (each result and Plan runs under
exactly its canonical size), `LabelEqual`, `FailedPreflight`. Library workloads are bounded where that code is
tested (`test_inhabitants`: the whole town read in one turn under 250,000 ticks). Update a pin with a reason when
it moves. Profile before optimizing the interpreter (§14).

Quadratic idioms to avoid in Bend: `Lists.append xs x` in a loop; `Lists.length` in a loop (use
`relationCount` on a relation); left folds of `textConcat` (use `textJoin` or interpolation); character walks with
`textDrop` (copies the suffix each step, in bytes; use `textHasAny`, `textSpan`/`textBreak`); a Bend walk to find
a row (use `Relations.lookup(r, key)`, which is `relationLookup`).

## 6. Evaluators and conformance

`impl/python/evaluator.py`, `impl/js/evaluator.mjs`, `impl/c/evaluator.c` are independent small-step,
call-by-name interpreters of the core; each runs its stream with a deep stack (Python a 512 MiB thread, JS a
worker with 256 MiB, C a json-c depth of 65,536) so a 2,048-row literal relation (about 8,000 deep) parses and
walks. Input line `{"name","term","responses","fuel"}`; output `{"name","status": value|yield|exhausted|stuck,
"term","plans"}`.

Term array wire: `["bound",i] ["nat","12"] ["boolean",b] ["label",s] ["lam",b] ["app",f,a] ["mix",l,u]
["fix",s,i] ["specification",m,e] ["prototype",s,t] ["reflect"|"metadata"|"project"|"perform"|"done",x]
["unary",prim,x] ["binary",prim,l,r] ["get",x,name] ["inject",label,x] ["ifZero",v,z,s] ["ifBool",c,t,f]
["record",[[n,t]..]] ["extend",x,fields] ["case",x,arms] ["refuse",reason]`, plus `toData`, `textJoin`,
`["relationCount", r]` and `["relationLookup", r, [column…], probe]` (each contracted to its expansion:
`textJoinExpansion`, `relationCountExpansion`, `relationLookupExpansion`). Packet form of a refusal:
`{"tag":"refuse","reason":TERM}`.

- An evaluator that rejects a line stops its stream; the runner restarts it and counts the line `rejected`.
- Text and unary primitives use code-point semantics; `textTake`/`textDrop` use the byte-size guard
  `n >= byteSize`; C has its own SHA-256. All three look `textHasAny`'s wanted words up in a set (C: an FNV-1a
  open-addressing table), linear as the kernel's.
- `perform` yields `status:"yield"` with `plans`, resumed from `responses` in order; `["refuse", reason]` steps
  its reason and is stuck at a value.
- A stored cell is not a term form: a term run with stored state is, by definition, the term applied to the
  substituted Data, so the evaluators run the substitution.

Harness: `tests/conformance/generate.py` (seeded; kinds term, activity, stuck, diverge, shared-effect,
exotic-value, chain, stored; asserts every tag and primitive occurs; `stored_cases`: 32 terms over a state
holding a relation, reading none, some or all rows; `relation_cases`: 16 small stored relations counted and looked
up, then a count, a hit and a miss over 2,048 rows; `refusal_cases`: a literal reason, one computed from literals,
from a bound value, read from a stored row, past a yield, not a String, one that never ends) and
`tests/test_conformance.py` (compares status, weak-head shape, and Plans when literal data;
`StoredCells` checks stored against literal runs and the forced rows). `python3 -m tests.test_conformance 1500
[IMPL_DIR]` prints the report: 1500 seeded cases plus the fixed ones gave 1,493 of 1,561 agreeing per evaluator,
68 known shared-effect, 0 unexpected. The 2,048-row walks are the slowest cases (Python about 13 s for the count).

Known divergence (`KNOWN_DIVERGENCE["shared-effect"]`): a `perform` reached while forcing a shared argument cell.
The machine refuses it (`Refusal.sharedEffect`); call-by-name evaluators perform at each use. Typed programs
cannot reach it (`noActivity`). Machine `divergent` and tick/capacity suspension map to `exhausted`. Not
compared: step counts, costs, deep values, non-literal plans. A join of one non-text item is that item in the
reference expansion but refused by the machine (untyped only), so the generator never gives a join's first item a
non-text head.

Adding a Term form: extend `generate.py` (and its tag assertion), `EvaluateTerm.termOf`, the three evaluators'
validators/arity tables/`reducible`, run the report, and decide fix vs `KNOWN_DIVERGENCE`.

## 7. Checkpoints

A checkpoint is the tokens of a collected, trimmed state plus its binding and digest. It is made only where a turn
suspends past the process (the host's `await*` and `interpret` paths); every other yield the host answers in
process is resumed from the `Suspension` itself (§2).

- Tokens: `.nat n | .text s | .str i`, JSON bare (`3`, `"x"`, `-(i+1)`). Term tags include 24 (`toData`),
  25 (`textJoin`), 26 (`refuse`, `[26] ++ reason`), 27-28 (`relationCount`, `relationLookup`); frame tags include
  14-17 (join), 18-21 (relation walk), 22 (`refuse`); stored parts tags 0-9; a refusal is `encodeRefusal` (`[8,
  text]` for `program`; 9 `unfetched`). Tags are additions only: a checkpoint using a new tag does not decode on an
  older binary.
- Site prefix: a message checkpoint's tokens begin `["delvetalk.checkpoint.site.v1", i]` (inside the digest);
  resume (`resumeType`) strips it, checks the response against site `i`'s type and decodes the rest. A checkpoint
  without the prefix does not resume.
- Edition v3 (`ObjectiveBendCheckpointV3.lean`, `…checkpoint.v3`), the only edition (`decodeCheckpoint`):
  - A dictionary encoding of the state written against a `Dictionary` rebuilt from the entry's term
    (`Dictionary.ofProgram entry.source.term`, per start/resume): a term is one token `i+1` for the program's
    `i`th subterm in preorder, environments of two or more addresses are a table listed once, strings are
    `Token.str` references. Every reference is emitted only after a check that it names exactly the value, so
    `stateV3_roundTrip` holds for every dictionary.
  - Addresses relative to their holder: `relativeState` renames each cell's addresses by `toRelative i` (i the
    cell's number), the control's and stack's by the heap size; decode applies `absoluteState`. `toRelative i a`
    is `2*zigzag(i,a)+1` when that is shorter than `2*a`, else `2*a`: the skeleton the collector numbers first
    (knot, state) is written absolute from everywhere, data near its holder relative, so a region that moved as a
    whole encodes the same. Proofs: `ofRelative_toRelative`, `mapValue_inverse`/`mapCell_inverse`/
    `mapFrame_inverse`/`mapControl_inverse`, `absolute_relative`, `stateV3_roundTrip`
    (`ObjectiveBendCheckpointV3RoundTrip.lean`).
  - Cell tag 5 is `stored`: its `Stored` part and an option (`0`, or `1` and the value). An unforced row is its
    handle `(f, j)`, never its data; a forced row is its value.
- `checkpoint s = collect (trim (collect (settle s)))`.
  - `collect` numbers live cells by `canonicalOrder` (depth first from the roots; a list spine put off to the next
    round), so a reading that walks further does not renumber every later cell. `orderValid` checks the order;
    otherwise `collectByAddress` (allocation order) is used.
  - `trim` points every environment slot a cell's closures do not read (`Term.freeIn`; a closure value `λ.body`
    reads `i` when `body` reads `i + 1`) at the cell itself; closures otherwise keep whole lexical environments,
    so every `let` of a long method stays live through every thunk built under it. The first collect bounds
    trimming's work by the live cells. Compiled through `trimCellFast` (one `Term.markFree` traversal per
    closure, `@[csimp] trimCell_eq_fast`).
  - Proof: `eraseState` replaces unread slots by 0 in cells, control and frames; `erase_stepRaw` (every
    transition copies an environment only into a closure over a subterm or a body under one more binder;
    `freeIn_rename` covers the renamed bodies of `fix` and `mix`), the `agree_*` lemmas, `agree_trim`, and
    `agree_resume_segment` with `settle_` and `trim_resume_segment` as instances; `checkpoint_resume_segment`
    composes the four stages.
- Digest without `Json`: `checkpointPreimage` writes the canonical CBOR of the digest map straight from the
  tokens (`writeToken`: naturals, texts and negative string references); `checkpointDigestJson` keeps the `Json`
  definition and a `#guard` compares them over v3 and site-prefixed tokens, a natural past 2^64, every CBOR head
  width and non-ASCII text. Not a theorem: `writeJson` is `partial`.
- Host side: `resumeOne` rebuilds the `Checkpoint` from journaled tokens plus the activity's object, principal,
  intent and roots; changing `Checkpoint` fields stops older journals resuming. Block encoding of tokens is the
  host's (HOST-HANDOFF). `expandSuspended` recomputes a digest a compacted journal entry lacks: the journal is the
  trust root, so that is sound; a host that ever resumes a checkpoint from outside its journal must look its
  digest up there. A checkpoint kept past the process has its unforced stored cells made native
  (`materializeStored store state allowance`, measured row by row against `Limits.maxCheckpointBytes` before it is
  built).
- `compile-profile REQUEST dictionary ENTRY` prints, per subterm in `Dictionary.ofProgram` preorder, its
  constructor and free de Bruijn indices: the tool for reading what a journaled checkpoint keeps live.

## 8. Language

Beyond upstream Mini Bend. World calls and the dialect are §9; State derivation and forms §10; clauses §11;
relations §12.

- **`Data`** (`Ty.data`, `Term.toData`, `Data.of::<T>(value)`): any well-formed first-order data
  (`Data.wellFormed`), produced only by `toData`; no elimination (`data_not_eliminated`). Runtime: `toData` is its
  value. Implicit injection (`coerceAt`/`coerceArgs`/`coerceGo`): where `Data` is expected and the expression has
  type `T`, the term is wrapped `toData T`; a value whose type holds an arrow or computation is refused by name
  ("refused (data-injection): …"). `Plan.obend`'s `call`/`send`/`create` payloads are `Data`. The typed-data
  schema has `Schema.data`; admission charges `admissionWork` and refuses "typed data value at Data repeats a
  record field".
- **`textJoin(list, sep)`**: `Term.textJoin`, frames `joinSeparator`, `joinList`, `joinCons`, `joinHead`, typing
  `Ty.listItem … = some .label`, meaning `textJoinExpansion`. Not proved: that the expansion and the machine's
  join frames agree.
- **`textHasAny(text, words: List<String>) -> Bool`** (`Primitive.textHasAny`, checkpoint code 16): whether a word
  of the list is a whole word of the text. Words are maximal runs of ASCII letters, digits and non-ASCII scalars
  (`textWordChar`), ASCII letters lowercased (`textWordsOf`); whitespace and ASCII punctuation separate. The
  elaborator lowers the call to `binary textHasAny text (textJoin words " ")`, so the list is walked once.
  `tests/test_text_words.py`.
- **`canonicalCompare(a, b) -> Nat`**: 0/1/2 by the canonical DAG-CBOR bytes of two values of one first-order
  type. Not a core form: the elaborator writes the comparison out from the type as Bend (`cmpTerm`,
  `canonicalComparator`), mirroring `Delvetalk.Canonical`: Nat numerically, `false < true`, text by UTF-8 byte
  length then bytes (scalar primitive `textCanonicalCompare`, checkpoint code 17), a record field by field in
  map-key order, a sum by label (same order) then payload, a list-shaped sum (`nil: {}`, `cons: {head, tail:
  itself}`) by length first, then item by item; recursive types are a `fix` per type variable. Refused by name:
  `Data` (Bend cannot read its shape), functions, activities, a sum with nil/cons beside other cases. A generic
  `Relation<T>` is monomorphised before elaboration, so `T` is always known. Ticks are the generated term's,
  linear in the values' size. `tests/test_canonical_compare.py` (random records against `canonical-encode`).
- **Type-argument inference** (`Generics.lean`, `inferArguments`, `synthI`): a call of a generic without `::<…>`
  gets the arguments its explicit spelling names, then is rewritten exactly as that spelling (instance numbers and
  packets agree; the generics pass visits children in sorted-key order, and changing that order moves every pin
  with a generic instance). A parameter left unbound is refused: "cannot infer the type argument U of Lists.kept
  …; write Lists.kept::<T, Rain>(…)". `maxInferenceSteps` bounds it. `world/` writes `::<T>` only where a world
  call's result type cannot be inferred (`world.view::<S>`, `world.call::<R>`, `world.interpret::<R>`) and never
  `Data.of`.
- **`let label(x) = world.METHOD(arg)`** then the rest of the block: lowers to `match world.METHOD(arg): case
  label(x): …` plus a `Pattern.unexpected` branch expanded to `case l(_): refuse("unexpected response l")` per
  other label. The scrutinee must be a world call ("refused (let-response)").
- **`refuse(line)`**, `Term.refuse (reason : Term)`, the line any String computed by the program: a refusal is the
  card's class, not a told message.
  - Stands only where an activity finishes ("refused (refuse-outside-tail)", "refused (refuse-outside-activity)");
    a reason of another type "refused (refuse-reason): refuse takes a String, the reason; this is Nat".
  - Reference: `Step.refuseReason` evaluates the reason; no rule moves `refuse (label s)`: the program has refused
    with `s` (`refusal_reason_computed`; `SourceFrame.refuse`, `Yields.refuse`, `yields_no_step`,
    `yields_deterministic`). Typing `PartialTyping.refuse` takes the reason at `String`
    (`computed_refusal_accepted`, `natural_refusal_reason_refused`).
  - Machine: pushes `Frame.refuse` and evaluates the reason; a label returned to it stops with `.refused (.program
    s)`, any other value `.refused .wrongValue` (`refuse_evaluates_its_reason`). The frame holds no address.
  - Turn: `Step.refused reason ticksUsed`, wire `{status: "refused", reason, ticksUsed}`; `evaluate-term` reports
    `stuck`. The host journals `cardRefused` (HOST-HANDOFF): `Ops.cardRefusal` parses `refused <clause>:
    <reading>`, else clause `card`; a callee's refusal refuses the whole turn; the reading is kept within
    `Limits.maxRefusalBytes`; `publicRefusal` shows the class and root only, since a computed reading may carry
    state. Card's `refusing` refuses this way when the caller is the world. `tests/test_card_refusal.py`.
  - Not proved: that an activity typed by the `refuse` rule refuses only through `refuse`.
- **Law readings**: `law NAME "reading": EXPR` (§11).
- **String interpolation** (`interpolationPieces`/`joinPieces`): `{expr}` in a string; up to four pieces lower to
  nested `textConcat`, more to `textJoin(TextPieces…, "")`. `{{`/`}}` are literal braces; a lone `}`, an unclosed
  `{` and two expressions in one pair of braces are refused by name. Document templates quote braces as
  `{`/`}`.
- **`write {field: op value, …}`** (§12): the world call `world.write(extend(keep(), {…}))` with ops `add`, `set`,
  `append`, `remove`, `amend ITEM with CHANGE`, `removeItem`, `insert`, `upsert`, `retract`. Needs a nullary
  `keep()` (derived, §10); `P` is the module's alias of Plan.obend (placeholder `$plans`, replaced by
  `Surface.Decl.mapVars`).
- **Layers**: `layer over ./X.obend` must be a module's first line (else refused "…is the module's first line"); it
  imports `X` as `Super`. Every declaration is a field of one knot, so a layer's `L.f` overrides `B.f`: `B.f`
  holds `self.L.f`, the old body moves to a hygienic `B.f#below`, and a layer's `Super.f` resolves to the key
  below. `checkOverrides` refuses a retyped override ("refused (layer-override): L.f is …, but it overrides B.f,
  which is …"). Unlayered packets are byte-identical. `Elaborated.select` takes an entry the top layer lacks from
  the topmost layer defining it. A layer's clauses add to its ancestry's (lowest first, names unique across them),
  never override; a clause in a module the entry only imports is refused. `tests/test_layers.py`.
- **Protocols**: `protocol P:` (indented `name: TYPE` lines; `(A, B) -> R` is read `A -> B -> R`, `() -> R` as
  `R`) and `implements P` (or `implements Alias.P`; `P` alone is looked up in the module, the import aliased `P`,
  then any import). State, Plan and Response in a protocol's types are the implementer's: the generics pass leaves
  them as names, and `checkProtocols` (after every declaration is typed) resolves them as placeholder variables
  that `matchProtocol` binds once per claim, so every method must agree on them. Missing method: "refused
  (protocol): M implements P but defines no m", at the `implements` line; mistyped: "refused (protocol): M.m is
  ..., but protocol P declares m: ...", at the method's body, `expected` the declared text, `found` the method's
  type; both hint the protocol. The artifact gains `protocols: [P]` and protocol methods' rows `protocol: P`, only
  for a module that claims one. `Decl.protocol` keeps the declared texts (`shown`) for messages.
  `tests/test_protocols.py`.
- **Located refusals**: every refusal of an elaborated package names `definition`, `module`, `span`; a type
  refusal `expected` and `found` in surface syntax, with `hint` (`blameHint`: a record where its field was
  expected, a function waiting for arguments, too many arguments, a missing field, an unknown case). Core
  `Expr`/`Body` carry the surface span as an implicit `{span}` field; `ATerm.located` is transparent to `json`,
  `erase`, `annotate`, `mapTypes`, `knotNames`. Generic instances are placed at their generic declaration
  (`Origins`, `FrontEnd.originsOf`). A refusal `emitDecl` raises without a place is placed at the declaration's
  body (`Decl.bodySpan?`). The generics pass's error is `Generics.Refusal {message, module?, span?}`: text thrown
  anywhere in the pass is placed by `rewriteTop` at the declaration being rewritten, and the derivation probe's
  refusals carry their own place (`derivedAt`, §10). `Package.localize` is the identity. Tested by the Workshop scenario (a flawed block checked with a diagnostic
  naming its line) and `test_sugar.Sugar.test_each_derived_refusal_names_its_source_line`.
- **Dialect hints** (`Delvetalk/Hints.lean`, `Diagnostic.hint`): only on refusals, at the named line for a parse
  refusal, at the Surface declaration holding the named line otherwise. `Hints.hintFor` never fires on a
  typed-packet checker refusal; `blameHint` does. A hint never changes acceptance.

## 9. World calls and the message dialect

The only effect is a world call. Surface `Activity<A>` is `computation Message Data A`, `Message` the record of the
module named `World` ("…yields World.Message, but no module named World is in this package").

- **Refused by name**: `Activity<Plan, Response, Result>` ("refused (old-dialect): ... is withdrawn", at the
  declaration in `emitDecl` and in `sourceType`); surface `perform(...)` ("refused (perform): surface perform is
  withdrawn", `isSurfacePerform`). `isPerform` is a world call only.
- **Types**: `Ty.isPlanUnder` is a record of data only; `PartialTyping.perform` concludes `computation plan .data
  T`, the checker taking `T` from the perform's annotation codomain. The decided activity examples are over a
  message Plan (`doneSignature` for `done`); `sum_plan_refused`.
- **The protocol**: `protocol world:` lines are signature form `name<Ps>(INPUT) -> RESULT` (`protocolSignature`;
  one input, refused by name otherwise), stored as `Field {name, type := "INPUT -> RESULT", typeParameters}`; the
  generics pass leaves such methods unrewritten and instantiates them at each call.
- **Lowering**: `world.X::<T>(arg)` / `world.X(arg)` (`world` not a local, declaration or alias) lowers in the
  generics pass (`worldCallOf`, `worldMethod`) to the Surface node `worldCall method input result arg` with both
  types rendered for the calling module; `T` is inferred only when the input is exactly the one type parameter
  (`write<E>`, `judge<E>`). The elaborator makes it `ATerm.perform Message RESULT {object: {world: "", object:
  "world"}, method, argument: toData INPUT arg}`, the argument injected where the input has `Data` fields
  (`coerceGo`), else refused with `expected`/`found`. `let label(x) = world.X(...)` and the shared-position rules
  hold. `write {...}` parses straight to `world.write(extend(keep(), {…}))`.
- **Site types**: the machine keeps no positions, so a site is named by its plan term. `Entry.performsOf` walks the
  entry term at the checker's positions and reads each perform's annotation codomain; `messageSites` keeps one
  `Entry.Site {term, type, hash}` per distinct plan and refuses, at compile (`Package.messageFields`), an entry in
  which two performs build the same plan term at different types ("refused (world-call-site)"). The table is built
  once per held entry (`CheckedEntry.make`, field `sites`). At a yield, `conclude` finds the site from the plan
  cell's origin in the extracted state (before `checkpoint` settles it) by `Site.matches` (the site's `termHash`,
  then `termEq`; exactly `termEq` by `Turn.Site.matches_eq`, and sites are pairwise distinct, so at most one
  matches), reports its `T` as `responseType`, and prefixes a checkpoint's tokens (§7).
- **Artifact** (message activities only): `dialect: "message"`, `world` (methods the entry's sites name, first
  occurrence), `worldProtocol` (the World module's source SHA-256 hex).
- **Host**: `messagePlan` returns `Except` (anything not a message is `noMethod`); `speaksMessages` is "its
  `receive` compiles". World's `Interpreted` has `denied`; the host answers it, and Garden and the Directory
  refuse it as policy.
- Tests: `tests/test_world_calls.py`, `tests/test_turn.py`.

## 10. The State is the schema

A module's `record State` declares its edits, its forms' inputs and which fields never change.

- **Derived `Edits`/`keep()`**: `Generics.deriveEdits` (a probe pass over the package whose state is dropped)
  resolves each State field's type with `typeOf` and writes, for a module declaring `State` (a record, or `type
  State = M.S` naming one) that imports Plan.obend and declares no `keep`, the source of the pair, parsed by
  `parseObjective` at the State's span. A list or relation is recognised by its instance (`entriesItem`: a
  one-parameter sum named `List` with cases `nil`, `cons`, or `Relation` with the one case `rows`); a type the
  module did not write is spelled through its own imports (`spell`). Refusals: "refused (derived-edits): State.f
  holds items of a type from a module M does not import"; a module with a State, no Plan import and a `keep()`
  call (every `write {…}`): "refused (derived-edits): write {...} and keep() derive Edits from State through the
  Plan library"; a declared `record Edits` or nullary `keep() -> Edits` beside a State: "refused (derived-edits):
  Edits is derived from State; delete this declaration", at the declaration. Any other `keep` (a method) only stops
  the derivation. `test_sugar`.
- **Form blocks** `form ACTION [as NAME]:` (`formRe`/`formKind`): fields `name: text A..B | natural A..B |
  source | a | b | c | T`. `source` is `F.Kind.source({})`, Bend source the host reads as text of 1 to
  `Host.Limits.formSourceMax` (= `Bounds.maxPackageBytes`, 131,072) characters and fills from a reply's
  ```obend fence (the Workshop's `check` and `propose` declare it). A block declares `def NAME() -> F.Form`
  (default `ACTIONForm`) from the module's alias `F` of `Form.obend`; refused by name without a Form import or with
  an unknown kind. The parser keeps each block as `Surface.FormBlock {action, value, fields: [{name, kind}]}` in
  `Module.forms`; a kind `T` (an identifier or `Alias.T`) stands as the marker `$formChoice(F, T)`.
  `Generics.deriveForms`, in the same probe: resolves `T` to the labels of a closed sum of empty cases ("refused
  (form-kind): form water offers shade: Mixed, which is not a closed sum of empty cases"), replaces the marker by
  the choice, and derives `record NameInput` (`type NameInput = {}` without fields; text and source String,
  natural Nat, `a | b | c` the generated `sum NameField` of empty cases, `T` itself) and `def forms() ->
  L.List<F.Form>` of the values in source order (needs an import of List.obend, else "refused
  (derived-forms)"). A hand-written `forms()` beside form blocks is refused at its declaration ("refused
  (derived-forms)"). A declaration named like a generated one: "refused (form-input): form plant declares
  PlantInput, its method's input, and so does the module". `checkFormInputs` (after `checkProtocols`): "refused
  (form-input): plant has a form block, so its input is PlantInput", with `expected`/`found`, by `sameTy` of the
  method's input parameter (between State and context) and `NameInput`; a block without fields admits no input or
  `{}`. A method row with a block carries `form: [{name, kind}]`, kind the `Form.Kind` value on the Data wire.
  `test_sugar`.
- **Order** of the derived declarations: they end their module as `forms()`, then `Edits` and `keep()`, then the
  form inputs and choice sums, and are specialized after every module's own declarations, so they number no
  instance before one the package spells. Knot fields are numbered and their types interned in declaration order:
  a module that writes `forms()` at its end compiles to the same packets. A derived `forms()` that instantiates
  `List<F.Form>` for the first time adds a bound to every packet of the package (bounds are package-wide).
- **`fixed` fields**: `colour: fixed Colour` in `record State` (`Surface.Field.fixed`; anywhere else "refused
  (fixed): only a State field is fixed") is omitted from the derived `Edits`/`keep()`, set only by `initial()` or
  a seed. `Generics.checkFixed` refuses any `world.write(...)` argument (a record, or `extend(keep(), {...})`, so
  every `write {...}`) naming one: "refused (fixed): colour is fixed; no edit names it". The artifact lists them,
  `fixed: [names]` in State order (absent otherwise; `Package.fixedFields`), for the host's actions, inspect and
  the Workshop's `set`. Both follow the effective State: `Package.stateRecordAt`/`recordAt` walk `type` alias
  chains and, in a layer that declares no State, the State below (`Super`), on fuel equal to the package's alias
  declarations and modules; running out is a cycle and refused, as is an alias naming an import its module lacks
  ("refused (fixed)"); `Generics.effectiveStateFields` makes `checkFixed` refuse a layer's write naming an
  inherited fixed field. `test_sugar` (a 64-alias chain among them).
- **`declares`**: every artifact lists which of `Package.conventionalNames` (forms, methods, relations, views,
  lenses, law, lawReads, initial, render, receive, blurb, page, publishPage, set) the entry module declares,
  derived declarations included (`declaredNames` over the generics pass's decoded modules), in that order; for a
  layer, every module of its ancestry. The host reads it, never the source text. `test_sugar`.
- **Re-exports**: `Package.signaturesAt` reads `export Alias.f [as g]` as the function it names (through imports);
  a re-exported parameter typed `State` keeps the name only if the exporting module's State is the defining
  module's, else `law` is refused by shape. Methods and `relations()` read it too. `test_methods`.
- The derivation probe's refusals carry `module` and `span`: `fixed` at the declaration whose write names the
  field; `derived-edits` at the State field whose type the module cannot spell, or at the State; `form-kind` at
  the form field; `form-input` "declares" at the clashing declaration; `derived-forms` and a form-input parse
  failure at the first form block.

## 11. Clause language: law, rule, want

One grammar for every clause on a thing's text; its definition is `Compiler/ObjectiveBendLaw.lean`'s module
comment. The host judges, fires and poses them (`Host/Law.lean`, HOST-HANDOFF).

- **One AST.** A line is a `Clause {modality, name, reading, condition}`; `Modality` is `law`, `rule (spell)` or
  `want (spell)`; a `Spell` is `parts`, each `text` or `hole TERM`. The three share one condition language
  (`LawExpr`), so a rule's `when` and a want's condition are laws' conditions. Readings: `law NAME "reading":
  EXPR`.
- **Terms** (`LawTerm`, mutual with `LawFilter`): `SIDE.F` with `LawSide` `new`, `old` or `cited "O"`;
  `request.FACT` (`subject`, `caller`, `method`, `kind`, `verb`, `clock` (the world clock at the write, in
  minutes), `object` (the written object's id, text-comparable)); `count(SIDE.F)` and `count(SIDE.F where COL ==
  TERM)`; INT; `"TEXT"`; `TERM + TERM`; `TERM % INT` (the integer at least 1; binds tighter than `+`). At creation
  `old.F` is the empty value; `old.a.b` is refused by name. A count is a reference, so filtered counts, growth
  (`count(new.F) <= count(old.F) + INT`) and quorum (`count(new.G) <= count(new.F where C == V) + INT`) are
  comparisons.
- **Atoms**: `eq`, `le`, `ge`, `member` (`LawPlace`: `[INT, …]`, `SIDE.F`, `SIDE.F.COL`: `TERM in old.F.COL`,
  `TERM in "O".F` are one arm on another side), `rule` (`LawRule`: monotone, writeOnce, appendOnly, unchanged,
  insertOnly), `changed(new.F.COL) by TERM`, `under "OBJECT"`, `"O" wants NAME`. A comparison needs one side
  reading the write (`compareRule`): `0 + 1 <= old.tended` and `"tide" == request.object` parse, `1 + 2 <= 3`
  refuses. Request kinds are one table, `ObjectiveBendLaw.kinds` (`kindNumber`, the host's `Law.kindNames`;
  `proposed`, write, reprogram, amend, `rule` 4).
- **Holes** are `{TERM}`, a term of the grammar that reads the write (`refers`); anything else refuses by name with
  the hole quoted (`holeRule`): `{request.object}`, not `{object}`. `me` is not a hole; the host resolves it. A
  spell is one line starting `delvetalk `.
- **A want reads the thing as it stands** (`Clause.atRead`): no `old`, no request fact but `clock` and `object`,
  no rule over old and new, no `changed`, no `under`; `admit` refuses the first such construct (`wantRule`).
  `parsed_want_reads_as_it_stands` proves it of every line `parseClause` accepts.
- **One parser**: `parseClause`, `parseClauseSource` (the clause and the text after its `:` as written),
  `parseText` (blank lines aside; names unique across all three modalities, `checkNames`), `parseBody`,
  `splitReading`. `tokenize` stops at `then` (a rule) or `asks` (a want) where it is not a field name; a leftover
  `then`/`asks` names the modality that takes it (`joinRule`). The Surface decl is `.clause keyword name source
  reading`; its JSON `kind` is the keyword. `ObjectiveBendElaborate.Module.clauses`/`Lowering.clauses` carry the
  entry module's text, every modality (the host places a package's rules and wants from them);
  `Module.laws`/`Lowering.laws` are its law projection (`lawsOf`).
- **One renderer** (`Clause.render`; `Lean.Json` quotes the reading; `Host.renderLaw` renders through it) and **one
  walk** (`Clause.names`: the condition's names then the holes'; `fields` (the written object's), `fieldsPlain`,
  `reads` (the cited objects, each once) project it; `LawName.cited object field`, `LawName.want object name`).
- **One refusal shape**: `law outside the enforced fragment: FOUND (RULE)`.
- **Theorems** (`native_decide`, `#assert_compiled`): `parse_accepts`, `parse_refuses`, `render_reads_back`,
  `parse_clauses` (FOUNDATION §10's rules, the bell's `rings`/`rang`, OVERHAUL's `water`, `daily`, `rests`, four
  wants), `parse_clauses_refuse`, `clause_render_reads_back`, `text_holds_three_modalities`,
  `refusals_name_what_and_why`, `names_walk`, `parse_clock_old_object`; `#assert_axioms` on the want theorems
  (`parsed_want_reads_as_it_stands`, `admit_ok`, `parseClauseSource_reads_now`).
- **The host's half** (`Host/Law.lean`): `Facts` (built by named fields) with `verb`, `clock`, `object`, `reads`
  (the state of every object the law cites, transitively through `under`, at the version recorded as its root),
  `wants`, `evicted`; `read` over every side and `%`; `denote` for every atom, `under` parsed by the kernel's
  parser at depth − 1 (`Limits.lawDepth` 4); `fires`, `poses`, `fill`, `followed`, `citations`. Absent or
  mistyped readings fail closed. `tests/test_law.py`, `tests/test_rules.py`.

## 12. Relations

A relation is a State field typed `Relation<T>` (`rows {items: List<T>}`, FOUNDATION §9) that its module declares
in `relations()`. The kernel stores it as cells (§15) and reads it by count and lookup.

- **Declaration**: `Package.relationsOf`: when the entry module declares a nullary `relations()`, it is compiled
  and run once per package (`PreparedRequest.relations` is a `Thunk` that `prepareRequest` sets; `prepareCore` is
  the closure without it, check-package's path), and the artifact carries `relations: [{field, key, limit,
  retain?}]`: `key` the columns, `limit` the declaration's Nat (0, the host's default, when it has none),
  `retain` the retention as text (a String field or a case label) only when declared. Refusals name
  `relations():` ("relations(): a limit is a Nat"). The host reads them from the artifact (`declsOfArtifact`).
  `test_sugar`.
- **Writes**: `write {f: insert row}`, `upsert row`, `retract key` (`Plans.Entries.insert({row})`,
  `.upsert({row})`, `.retract({key})`). `write {f: remove v}` is `removeItem {item: v}`, or `retract {key: v}`
  when the effective State types `f` as a `Relation<…>` (the parser emits `$remove`; the generics pass lowers it
  with `lowerRemove` once `Generics.relationFields` has resolved the effective State and each field's type, so
  `type State = Lib.State`, an aliased field type and a layer's inherited relation retract by key). `write {f:
  amend v with c}` is `amendItem {item: v, change: c}`. An index (`remove {index: …}`, `amend {index: …} with
  …`) is refused by name ("names a position, and edits name items: write `f: remove ITEM` …").
  `test_sugar`.
- **Reads**: `relationCount(r)` and `relationLookup(r, key)` (§15). `Relations.lookup(r, key)` in
  `world/lib/Relation.obend` is the lookup every object uses. `relationLookup(r, key)` is
  `(λk. relationLookup r columns (λx. canonicalCompare(x, k))) key`, the columns being the key record's fields,
  each refused by name unless a column of the row type of the same type ("refused (relation-lookup): …").
- **Law atoms** over relations (`insertOnly(F)`, counts, column membership, `changed`) are §11.
- Data compared by consumers (`Ops.attenuate`, `relationEdit`, `keyAtMost`) is compared by canonical bytes; with
  `encode_injective` that is equality up to `normalize`.

## 13. Compile structure and checker costs

- **What is compiled**: the package knot holds only what the entry reaches (`Elaborated.select`,
  `Output.knotRow`; `globalRow` stays whole for the method table and law shape); the whole closure is checked
  once per package (`checkClosure`: every template and the knot of every declaration as one term) without
  rendering a packet (`directSource`/`checkDirect`); an entry goes JSON -> `decodePacket` -> `check`. Row width is
  charged by `typeRowCapacity`, so an entry may reach any number of definitions.
- **Interning**: `PTy.internSlot` keyed by constructor, strings and child slots (`InternKey`); the derived
  `Hashable PTy` rehashes subtrees and is quadratic.
- **Type equality** is by shared subtrees: `Ty.eqSharedCore` (structural, `withPtrEq` at every child, `r = true ↔
  a = b`) behind `@[csimp]` on `instDecidableEqTy` and `instDecidableEqTy.decEq`, so every `=`/`==` on `Ty`
  stops at one object in memory. `agree` compiles to `agreeFast` (`@[csimp] agree_eq_agreeFast`): equal trees
  agree at once; only differing ones pay for canonical forms and both shareability walks (`sameTypeShared`).
- **The checker over a cursor**: `inferAt`/`inferFieldsAt`/`inferArmsAt` check over any annotation cursor
  (`here : α → Option LambdaAnnotation`, `child : α → Nat → α`); `infer`/`inferFields`/`inferArms` are it at
  source positions (`child p i = p ++ [i]`) and stay the reference, so `check`, the decided examples and the packet
  path are unchanged. `inferAt_view`: two cursors related by a map preserving `here` and `child` infer alike.
  `AnnotationTree` (`here`, `child` (the empty tree past the children), `subtree`, `lookup := (subtree
  path).here`); `checkAt_eq : checkAt term tree a c f = check ⟨term, tree.lookup, a⟩ c f`.
- **Generics pass**: `Generics.demand` runs a binding's `M IType` (local, parameter, case binder, expected type,
  record base) at most once and keeps its answer in the pass state (a refusal is not kept; `tryCatch` rollback
  drops ids and answers together). `itypeOf` keeps each unbound type text's reading by (origin, text); `skeleton`
  keeps each callee's (type parameters, parameter and result types) by (origin, name, label). Synthesis reads only
  what a state never changes (sources, declaration keys, instances), so answers are a rerun's. `candidate` passes a
  string without `_` at once. Instances are indexed by `instanceOf`.
- **Linear structures**: `context` collects declarations, records and sums into arrays with a key index;
  `emitDecl`'s fields and the row are arrays; `annotateOnto` carries the path reversed and pushes onto one array
  (preorder kept); `reachable` splits only keys holding `#`; `splitTopAt` keeps its piece reversed (`#guard`s);
  `checkNames` counts once; `Store.readsOf` is one heap pass pushing onto arrays.
- **Pins** (`tests/test_artifact_pins.py`): compiles every non-generic entry of every world closure and compares
  against `tests/fixtures/pins/artifacts.json` (`{module: {pin, entries: {def: {status, packet?}}}}`). It fails
  only when a module's source pin changes or a def that compiled stops compiling; packets that recompile
  differently are counted and printed. Re-record only when `world/` changes or a kernel change moves packets
  (state why): `DELVETALK_OBEND=… python3 -m tests.test_artifact_pins --record`. Packets move when a term's wire
  form changes (every entry reaching it) or instance numbering or knot order changes.

## 14. Performance: how to measure, what was measured

Profile before optimizing. The machine is not where turns spend their time; checkpoint work, compiles and state
walks were.

**Method.** On hbox (i9-12900: P-cores 0-15, E-cores 16-23) pin to the P-cores (`taskset -c 0-15`, inside
`swarm-build`): a process that migrates between P- and E-cores varies by 30%, and under load 30 to 60 the same
replay took three times as long. Report the fastest of three runs for wall and user instructions (`perf stat -e
instructions:u`, the least of three; about 5% run-to-run) as the load-independent check. Check an optimization by
replaying into a journal: the journal and its snapshot must be byte-identical to the base binary's, and pins must
not move.

**Tools.**
- `compile-profile` (`spec/CompileProfile.lean`, `lake build compile-profile`; usage in its header):
  `REQUEST.json [entry …]` stage timings over three rounds; `REQUEST.json loop STAGE N` (parse, generics,
  elaborate, lower, check) for `perf`; `self-check` (`tokenLength` vs `tokenRe`, `splitTop`, SHA-256 on the FIPS
  180-4 vectors and against the stored-schedule reference); `sha` (throughput on 1 MB); `stored REQUEST ROWS R`
  (a relation of ROWS rows read for one row, held as stored cells); `REQUEST dictionary ENTRY` (§7);
  `replay LINES DIR FILTER R`.
- `replay` feeds host requests, one JSON per line exactly as `delvetalk-obend` reads them, through
  `PackageSession.stepIO`, with `world-open` moved to `DIR/world.journal` (emptied first, `sync: none`, so no
  fsync is timed). Each request whose class (`op object method`, an object class like `garden/*` for
  `garden/bell/2`, or `op entry` for held runs) starts with FILTER runs R times from the same session; the fastest
  run is kept and the session continues from it. It prints per class: requests, wall, `ticksUsed`, ticks per
  second of wall.
- Request streams are captured by a wrapper binary that tees stdin (`tee $CAPDIR/$$.jsonl | delvetalk-obend`) and
  are not checked in; rebuild them. The two used: the Counter bump
  (`tests.test_turn_world.CounterTurns`, filter `world-turn c1 bump`) and the rehearsal (`rehearsal/rehearse.py` over its archived posts, filter `world-turn
  directory receive`).
- `perf record -F 299 --call-graph dwarf` for inclusive shares of the host's `drive` loop; flat `perf record -F 999`
  for self time. Ticks per second of the machine alone: samples under `forceHostedFrom` against the ticks run.
- `deploy/bench-write.py`: N `upsert` turns replacing the middle row of a relation of ROWS rows through the pipe to
  one host. `deploy/bench-boundary.py`: per-op round trip across the transport boundary.

**Measurements** (each with its method; re-measure before relying on one).
- The machine: 25 to 37 million ticks a second of wall including extraction (a 64-field spell parse at 37 M, 27
  ns a tick; the directory's segments about 25 M). `forceHostedFrom` calls `textStepCost` and `sizesAfter` and
  matches the state three times per tick.
- Directory `receive`, 120 turns of the rehearsal replay, P-cores, load ~16: 2,123 to 2,474 ms with in-process
  yields resumed from the `Suspension` (5,102 to 5,505 ms when every segment was checkpointed); the whole replay
  160 G user instructions (322 G); ticks identical (12,489,187). The digest written from tokens rather than through
  `Json` took the replay from 322 G to 286 G alone.
- Counter bump replay (R = 50, best of three): 120 us a bump, 102 ticks.
- Stored cells, 2,048 rows (`k15`-style, one process, best of 15, `world/lib/Relation.obend` through `run` and
  `turn-start`/`turn-resume` with `stored`): a lookup hit 270 ticks and 1 row fetched (a Bend walk: 292,448 ticks,
  1,537 rows); a miss 744 ticks, 0 rows (390,559, 2,048); a count 51 ticks (49,238); a write then count across a
  resume 26 ticks (49,213). Wall there is the 2,048-row state on the wire. `compile-profile stored`: the start and
  resume of a write then one row's text take 45 us stored against 2,853 us quoted (0 rows: 29 against 32 us); the
  suspension's checkpoint 540 canonical bytes stored against 45,357 quoted. A turn that reads no row, or one row,
  spends the same ticks over 0 or 2,048 rows (`tests/test_stored.py`).
- A one-row write (`deploy/bench-write.py`, 200 turns, median, best in brackets, 120 ticks a turn): 16 rows
  0.72-0.81 ms (0.49), 256 rows 0.90-0.94 ms (0.58), 2,048 rows 0.84-0.93 ms (0.57): flat in the relation's size.
  A whole-state walk per write took 43-48 ms at 2,048 rows; a flat spine of row links instead of chunks 2.7 ms.
- Checkpoints (`rehearsal/rehearse.py`): after trimming, median suspension 10,077 bytes (46,390 untrimmed), new
  blocks per suspension median 6 (74); journal 2.8 MB (4.7 MB). Of a median suspension, 5.7 KB is blocks and
  4.4 KB the host's inline fields (`activity.argument` 1.2 KB, `interpretation.utterance` 1.0 KB).
- Checker (turn-start on a held entry, best of three): a 5,000-item list at `Data` 26 ms (2,320 ms before shared
  type equality and `agreeFast`); a 5,000-item `List<String>`-shaped sum 9 ms; 1,000 three-column rows 7 ms.
- Compile (`compile-profile`, one process): a world package's preparation is 50-170 ms (Kind's closure, 16
  modules, 135 KB: parse 53, generics 60, elaborate 30, whole-closure check 26) and every entry 2-7 ms on top
  (select ~25%, packet rendering ~20%, decode and re-check ~20-25%, packet CID ~40%). Everything is linear-ish at
  world sizes; the suite's minutes are compiles multiplied. Parse is about a third of preparation at ~370 ns a
  character (the parser works on `List Char`; `sourceLines` alone is a quarter of it). User instructions per
  iteration (`loop STAGE 20`): generics on Kind 207M, elaborate on Kind 143M, the whole lowering 189M, an Avatar
  entry 50.5M; decode and re-check 0.3-1.6 ms an entry (Avatar). Garden (11 modules, 78 KB): first entry 48 ms,
  further entries about 9 ms, `check-package` 45 ms; a request carrying the whole package spends about 4 ms on line
  reading, parsing and reply rendering with no compilation. An activity entry's packet is 200-250 KB.
- Package and instance scale (generated packages, one process, best of two or three): Garden-derived packages of
  31.7, 61, 117 and 258 KB (140, 161, 203, 308 instances) compile `initial` + 10 methods in 0.34, 0.35, 0.42,
  0.64 s at 106-127 MB resident; Card's declarations alone (30 to 255 KB, `check-package` and 20 entries) 0.09 to
  0.27 s and 0.17 to 0.54 s. Instances, `check-package` then one entry reaching all of them: 178 0.09 + 0.06 s
  (0.35 MB packet, 87 MB), 354 0.15 + 0.11, 706 0.27 + 0.23, 1,025 0.39 + 0.35 (2.04 MB, 107 MB), 1,410 0.57 +
  0.55, 2,818 1.38 + 1.33 (5.63 MB, 167 MB): linear, about 0.37 ms of check and 2 KB of packet an instance. A
  `run` reply holds the artifact: 1 MB for the 258 KB Garden, 2.6 MB for an entry reaching 1,024 instances.
- `relations()` once per package: 13 Cistern entries in one session 101-102 ms (126-130 ms evaluating it per
  entry).
- `encodeTermOnto`/`encodeDataOnto` (`@[csimp]`, proved `encodeTermOnto t acc = encodeTerm t ++ acc`): the term
  encoder is linear in a term's depth. SHA-256 rounds over an unboxed sixteen-word schedule window
  (`Compiler/Sha256.lean`): 1 MB in 5.9 ms. Tried and not kept (no measurable change, or slower): a 32-node prefix
  hash for the dictionary's term hint, the body encoder onto an accumulator (`encodeBodyV2Fast`), CBOR heads and
  digest bytes without `List.range`, a checkpoint-local term table (no gain on forced literal lists, worse
  nine-prose dedup).

## 15. Stored cells: lazy state

An object's state enters a turn as one stored cell; the machine forces only what the program reads and fetches a
relation row only when forced. A turn that reads nothing of a relation pays nothing for it, in ticks or host work:
the kernel holds `(field, n)` and nothing else.

**The cell.** `Cell.stored (s : Stored) (value : Option RuntimeValue)`: `none` unforced, `some v` forced (its WHNF,
kept with its provenance). `Stored` holds no address. Entering `stored s (some v)` returns `v`.

| `Stored` | forcing it (one transition) | allocates |
|---|---|---|
| `object (state : List (String × Data)) (stored : List (String × Nat))` | `.record` of the state's fields in order: a field named in `stored` with size n is `stored (relation f n)`, any other `native d` | one cell a field |
| `relation f n` | `.variant "rows" a` | `a = stored (items f n)` |
| `items f n` | `.record [("items", b)]` | `b = stored (spine f 0 n)` |
| `spine f j n` | `j < n`: `.variant "cons" c`; else `.variant "nil" e` | `c = stored (cons f j n)`; `e = native (.record [])` |
| `cons f j n` | `.record [("head", h), ("tail", t)]` | `h = stored (row f j)`, `t = stored (spine f (j+1) n)` |
| `row f j` | the host's row j of f, forced as `native` forces it (fetched) | its fields, `native` |
| `key f j columns` | the row's projection onto the lookup's columns (fetched) | |
| `found f j` | `{value: row}` with the row unforced, so a presence test fetches nothing | |
| `absent f low` | `{}` | |
| `size f n` | the count `n` | |

Every part but `row` and `key` is forced by `stepRaw` alone (`forceStored`, `objectCell`,
`allocateObjectFields`). Positions are the relation's canonical order (key order) at the turn's read height; `n`
is its row count there.

**The fetch.** `stepRaw` cannot fetch: entering an unfetched `row`/`key` is `.refused .unfetched` (checkpoint
refusal code 9, reached only by a runner without a store). The hosted runner fetches: `forceHostedFrom policy
fetch limits bytes ticks state depth` takes `fetch : Fetch` (`Fetch := Stored → Option Data`, answering `row`
and `key`, `Stored.fetched`), threaded through `forceHostedWith`, `materializeWith`, `completeWith`,
`yieldedPlanWith`, `executeStateWith`. It charges `fetchCost d = (1 + 2 * b, b)` with `b = d.canonicalBytes`
exactly as a text primitive is charged (ticks first, `b` reserved against `bytes`, suspension retaining the state
when either fails), then `fetchStep d state`: `(heap', v) := forceNative heap d`, the cell becomes `stored s (some
v)`, `control := .returned v`. A row is fetched once per segment it is forced in; forced, it is native data like
any other. `fetchable` is `@[inline]`, so a run without stored cells pays nothing for the test.

**The relation primitives.** `Term.relationCount relation` and `Term.relationLookup relation key probe` (`key` the
columns, `probe` a function of a row's projection onto them to 0 below / 1 equal / more above the sought key).
Their meaning is a walk (`relationCountExpansion`, `relationLookupExpansion`, Step rules), which the evaluators
implement literally. `Walk = count n | lookup key probe`.

| frame | on | does |
|---|---|---|
| `relationRows walk` | `rows payload` | payload a stored `items f n`: a count pushes `stored (size f n) (some n)` and returns `n` (one transition, no row); a lookup starts `searchStep … 0 n`. Else enters the payload under `field "items"`, `relationList walk` |
| `relationList walk` | `nil` / `cons p` | count: the tally / enter `p` under `field "tail"`, tally + 1. Lookup: `none` / push `⟨keyProjectionTerm key, [p]⟩` and apply the probe |
| `relationProbe key probe p` | `0` / `1` / more | walk on to `p.tail` / `some {value: p.head}` / `none` |
| `relationSearch key probe f low high` | `0` / `1` / more | search the upper half / push `stored (found f mid) none`, `some` / the lower half |

`searchStep` probes the middle by pushing `stored (key f mid key) none` and applying the probe to it; an empty range
pushes `stored (absent f low) none` and answers `none`. `Turn.Store.bounded` answers a key only when the lookup's
columns are the relation's declared key as a set (rows are in that key's order alone), so a search by other
columns is refused `unfetched`, never answered wrong; a literal relation has no declared key and walks.

Typing: `Ty.relationItem` (the closed one-case sum `rows {items: List<T>}`), `Ty.listItem`, `Ty.projection` (the
key's record type), `Ty.maybe`; rules `PartialTyping.relationCount` and `.relationLookup` (the probe a reusable
shareable arrow from the projection to `Nat`, `argumentAllowed … .unrestricted`). Proofs, each with
`#assert_axioms`: `sizesAfter_eq`, `related_stepRaw` (`searchStep_related`, `storedItems_rename`),
`forceStored_related`, `erase_stepRaw` (`storedItems_erase`), `erase_forceStored`, `fetchable_spec`,
`fetchable_agree`, `agree_fetchStep`, `related_fetchable`, `related_fetchStep`, `term_roundTrip`,
`frame_roundTrip`, `walk_roundTrip`, `frameV3_roundTrip`, `mapWalk_inverse`, `decode_json`, `stored_roundTrip`.
`agree_*`, `related_*`, the three `*_resume_segment` theorems and `checkpoint_resume_segment` hold for every
`fetch` (both runs ask the same function). Tests: `test_stored.RelationPrimitives`, `test_conformance`
(`relation_cases`, `StoredCells`).

**The runner** (`Delvetalk.Turn`):
- `structure StoredRelation where field : String; size : Nat; key : List String`
- `structure Store where relations : List StoredRelation; fetch : Fetch` (`Store.empty`: no relations, every fetch
  `none`; `Store.bounded`: rows within `Bounds.maxCellBytes`, keys only by the declared key).
- `startEntry (entry : CheckedEntry) (arguments : List Data) (store : Store) (binding : Binding) (b : Budgets)
  (dictionary : Option Dictionary := none) : Except String (Step × Reads)`
- `resumeSuspended (entry) (suspension : Suspension) (store : Store) (binding) (value : Data) (b) : Except String
  (Step × Reads)`
- `resumeEntry (entry) (checkpoint : Checkpoint) (issued : String) (binding) (value : Data) (b) (store : Store)
  (dictionary := none) : Except String (Step × Reads)`
- `materializeStored store state allowance` (§7), `Package.executeDataEntryStored` for cards and views,
  `keyProjection`, `scalarPart`, `relationRows`, `storeOfState state [{field, key}]` (a `Store` over a state's own
  rows, as the tests, the evaluators' harness and the profile build it).

Every argument is taken natively (`nativeApplication`); each data argument is admitted by `conformsUnder`, which
`conformsUnder_iff` makes `HasType`. The first argument is the state: before the check, each field named in
`store.relations` is replaced by the empty relation `rows {items: []}` (so the check walks the scalars only), and
the state enters as one `stored (object fields stored) none` cell. Rows are not re-checked: the host checked each
when it was written.

**Reads.** `structure Read where field : String; key : Data; bytes : Nat` (a forced row: its key projection onto
`StoredRelation.key` and its canonical bytes) and `structure Reads where rows : List Read; spans : List (String ×
Nat); found : List (String × Data); gaps : List (String × Option Data × Option Data)`, read off a segment's final
state before any collection (`Store.readsOf`, one heap pass):
- every `stored (row f j) (some _)` cell is a row read;
- `spans` gives, per field, the prefix a walk or a count observed (`j + 1` for `spine f j n` forced, `n + 1` for a
  `size` or the forced `nil`: the whole key set);
- a lookup that hit (`found f j`) reads its key, row forced or not (`found`); one that missed (`absent f low`)
  reads the gap its key falls in, between the keys at `low - 1` and `low` (`gaps`, none past an end). A lookup's
  probes read nothing: where the sought key falls decides it.

The host journals them on the root as `rows [{field, key}]`, `spans [{field, through?}]` and `gaps [{field,
after?, before?}]` (`Ops.Cells`, `cellsOf`) and judges (`cellsCurrent`, WHOLENESS §3a): stale when a write since
touched a read key, any key at or before a span's last, or a key strictly inside a gap; a write below or above a
looked-up key leaves the lookup current (`test_relation.Lookups`). A turn's reads are the union over its segments
(`Cells.join`: a span covers the rows and gaps below its last key). `Reads.toJson` is the wire form.

**The invariant.** A forced row is `store.fetch` for the turn's store, and the host builds that store from the
object's state at the turn's read height (the version `recordRoot` records): a fetch on a resumed segment must
answer the same version (the host keeps it, or refuses `staleRoot` and re-runs the turn). The binding's roots
digest names that version, so a checkpoint resumed under another one is refused before any fetch.

**The state as cells.** The host holds an object's state as its cells, `Object.cells : Turn.StateCells {scalar,
relations, cid, whole}`: the scalar part (`scalarPart`), each declared relation's rows in key order
(`RelationCells {field, key, rows : Array RowCell, chunks}`, a `RowCell {row, key, bytes, cid}` holding the row,
its key projection's canonical bytes, its canonical size and its block's CID), the state's CID, and the whole state
as a `Thunk` made from the cells when something reads it whole (`Object.state`; a law and rules read
`Ops.viewFor`: every scalar field and only the relations their clauses name, the whole state when one cites
another's law by `under`). The host's frame store is its object's cells (`Held.of`, `StateCells.store`), kept for
the turn's resumed segments. A write never walks the state:
- *Edits* (`Ops.applyEdits` over `Editing`, `relationEdit`): a relation edit is a binary search on the key bytes
  (`RelationCells.position`, `Canonical.bytesLt`) and one `insertAt`/`setAt`/`eraseAt`; retention is `eraseAt 0`
  past the limit (`withinLimit`); a relation `set` is the whole relation, made canonical. It answers `Applied
  {cells, evicted, changes}`, `changes : Changes {scalar, rows}` the cells it changed (`Changes.of`: the rows put
  that the state after holds and the state before did not, the scalar part when its bytes moved).
- *Check*: `Changes.checked` (the scalar part, each relation holding only its changed rows) conforms. Exact: with
  every untouched row conforming, the state after conforms iff the checked one does
  (`ObjectiveBendCellConformance`; `Turn.listData_chain`). The host declares a relation only over a genuine
  `Relation<T>` (`Ops.relationItemOf` in `rowColumns`), where per-row conformance holds.
- *Bound and charge*: a cell, not an object, is bounded. `Bounds.maxCellBytes` (262,144) bounds a fetched row (the
  kernel refuses a larger one as unfetched) and, at write, each changed cell (`Turn.Changes.overBound`: the scalar
  part when it changed, each row put), refused `capacity`, clause `maxCellBytes`, naming the cell; a seed and a
  migration's result are bounded by every cell (`Changes.all`). A write is charged the canonical bytes of the
  cells it changes (`Changes.bytes`, `Ops.chargedBytes`: the storage ledger). FOUNDATION: "State is bounded per
  cell: the scalar fields together and each relation row are at most 256 KiB of canonical bytes, a relation's
  length is its declared limit, and a write pays for the cells it changes." `tests/test_relation_limits.py`.
- *Name*: the state's block is the scalar part's canonical encoding with each relation (the variant `rows`, written
  by `Canonical.variantHead`) holding as its `items` the links (DAG-CBOR tag 42) of its chunks; a chunk is a run of
  rows in key order ending at a row whose CID's last byte is below 4 (about one in 64) or at the last row, its block
  the array of its rows' links (`stateBlock`, `chunkOf`). Chunk ends depend only on the rows, so an edit re-forms
  the chunk it falls in and keeps the rest (`RelationCells.edited`; a `#guard` checks inserts, replacements and
  erasures at the front, inside, at chunk ends and at the end against a fresh chunking). A one-row write hashes its
  row, its chunk and the state block. `tests/wire.py` `state_cid` is an independent encoder;
  `test_relation.StateCid` compares it with every journaled `cid` over random edits and retention. Every creation
  journals its `cid`, so `stateCidIn`, `stateCidAt` and slugs read no seed. A carry reads an earlier edition's world
  by its naming (`Ops.Naming.ofEdition`) and lists each state's two names (`renamed [{object, before, after}]`;
  `transport/carry.py` checks them).
- *Store*: `StateCells.store` fetches row `j` from the array; `storedState` is `cells.scalar`.

**Checkpoints** of stored state: §7 (cell tag 5; stored part tags; an unforced row is its handle).

## 16. Open

Each item names its owner and what closes it.

1. (Kernel, then host; replay edition.) Charge argument admission to the turn: `admissionLeft` bounds the
   conformance and well-formedness walks by the turn's ticks but does not deduct them, so `ticksUsed` excludes
   them, where a card's preparation deducts (`executePreparedNativeFrom`). Charging moves every turn's ticks:
   re-record `test_tariff` and a replay edition. Closes when `startEntry` deducts the work `admissionLeft` counts
   and `ticksUsed` includes it.
2. (Host.) `Host.Ops.checkModules` still calls `Package.localize`, the identity: drop the calls, then delete
   `localize`. Closes when `grep -rn localize spec` is empty.
3. What still reads a whole state per write, each made once per version from the cells when it does: a Bend law
   (`predicate`: `bendLaw` runs `law(old, new, request)` on whole states natively; through the stored path it
   would fetch only the rows it forces), a text law citing another's by `under` (`viewFor` gives it the whole
   state), `posing` (wants), `revealed`'s "first by the speaker" (a scan of the rows' `author`), a reprogram's
   migration and a whole-relation `set` (inherent: every cell is new). Measure on a law-bearing object
   (`deploy/bench-write.py` with a package declaring `law`) before building.
4. A Lean statement over `applyEdits` (the rows after are the rows before, less the removed, plus `put`) would
   close the argument that `Changes.of` holds every row a write put; today it is by construction (`applyStep`,
   `relationEdit`, `withinLimit`) with `test_relation.StateCid` and the chunking `#guard` as evidence.
5. `Theory.storedReach` now serves only `EvaluateTerm`'s `reach` in the evaluators' harness; the host reads
   `Store.readsOf`. Fold the harness onto `Reads` (found, gaps) when the conformance generator next moves, and
   delete `storedReach`.
6. (Kernel.) `Generics.run` builds `initialState` twice (derivation, then rewriting after the derived
   declarations): reuse the sealed identities and extend the first state's indexes by the derived declarations;
   the fresh-name set must stay exactly the final sources' strings (instance names are in every packet). Closes
   with generics on Kind below 190M instructions and 0 packets moved.
7. (Kernel.) The elaborator synthesizes a let's remaining body at every let of a chain (O(k^2)), and effect guards
   synthesize what elaboration synthesizes again. A synth memo would skip repeated `typeError` pushes and so
   could change a refusal's text: return the type with the elaborated term instead. Closes with elaborate on Kind
   measured and every refusal text unchanged (`test_sugar`, `test_layers`, `test_protocols`).
8. (Host or session.) `encode-compact`/`decode-compact` go to `Package.job` (`compactCodec`), which recompiles the
   artifact's closure (`verifyArtifact`) and re-checks its packet: route them through `PackageSession.entryOf`
   and the held entry's assumptions and type. Closes when `test_data_type`'s three codec calls compile once.
9. (Kernel.) `sourceType`'s memo is bypassed under `seen` (all nested record and sum expansion) and type bindings.
   Closes with a memo keyed by what the answer depends on, argued against the sum variables it allocates, and 0
   packets moved.
10. (Kernel.) Entries are decoded and re-checked after the closure check (a fifth of an entry's compile). Removing
    that soundly needs a pruning theorem (the whole knot checked implies every selected knot checks, annotation
    paths renumbered) or a packet round trip for the type table and annotations (`decodePacket (packetJson …) =
    .ok (directSource …)`; only the term half, `decode_json`, exists).
11. (Host, session.) Every package re-parses its library modules: a parse cache by module (name, sha256) in the
    session would remove most of parse. Parse itself: a direct scanner per line regex, checked against the `Re`
    values as `tokenLength` is (`compile-profile self-check`).
12. Name a prepared package by its sources CID instead of resending it per request (about 4 ms a request of
    line reading, parsing and reply rendering for Garden). Closes when the wire accepts `{sourcesSha256}` alone.
13. (Host.) A test of a grant fixing a Data-typed variant and a holder supplying the one-field record (refused
    `grantConflict`) belongs in `test_grants`.
14. Machine, only if a pure-compute workload ever matters: one fused match per tick in `forceHostedFrom` would
    remove most of `sizesAfter`. A shallow embedding (terms compiled to Lean closures) would lose what the turn
    depends on: every yield writes the heap and stack as data.
15. (Host.) The disk compile cache (`Host/DiskCache.lean`) stores packets as JSON: a warm serve process spent
    ~22% of its CPU reading definitions (Lean's JSON parser 13%, the required re-check `compiledOfPacket` 11%). A
    binary (canonical CBOR) disk form would cut the parse.
16. (Host.) Law `Facts` are built per judgment (only the parse is memoized): build them once per object, version
    and clock.
17. (Host.) `insertOnly` is judged over both sides' rows (`Host/Law.lean`; a 2,048-row relation costs ~12 ms a
    judged write): judge it from the write's own edits (`Turn.Changes`).
18. (Kernel.) SHA-256 is pure Lean (`Compiler/Sha256.lean`), 15-20% of serve CPU before the CID memos: a native
    implementation behind the Lean model.
19. (Evaluators.) `impl/c/evaluator.c` `walk` shifts a closed argument at each use, as the Python one does (5 s on
    the 2,048-row count): keep a reach per node.
20. `textWords(s) -> List<String>`: only if an object asks; none does. A primitive returning a list needs a new
    term form (the machine allocating a native list cell, typed by its annotation like `refuse`), the full
    `textJoin`-scale change across core, machine, Fast and collector proofs and both codecs.

Not proved: that `noActivity` is the static guard matching `perform_under_update_refused`; that
`textJoinExpansion` and the machine's join frames agree (conformance tests values only); that an activity typed by
the `refuse` rule refuses only through `refuse`; the canonical-CBOR round trip (`#guard`ed).
