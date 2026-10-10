# Kernel handoff

State on 2026-10-09 (foundation f178383).

## Summary

The kernel is the Objective Bend edition: source text to a checked typed packet, a demand machine with a tick tariff, a checkpoint codec, and the wire/canonical forms. The host (HOST-HANDOFF) calls it through `Turn.lean` and `Package.lean`; JSON exists only at the process boundary.

- Language: `spec/bend/Compiler/` (Surface, Parse, Elaborate, FrontEnd, Blame, Law, TermWire, DataWire, Sha256) and `spec/bend/Theory/` (OpenRecursion, Types, Typing, DemandMachine, DemandMachineFast, DemandData, Checkpoint, CheckpointV2, DemandCollect and proofs).
- Delvetalk side: `spec/Delvetalk/` `FrontEnd`, `Generics`, `DocumentTemplate`, `Hints`, `Package`, `PackageSession`, `Turn`, `Entry`, `Limits`, `Canonical`, `Document`, `Profile`, `EvaluateTerm`, `PackageData*`; driver `spec/PackageMain.lean`.
- Binary: `.lake/build/bin/delvetalk-obend` (`lake build`; `make build` also builds the proof-only modules in `PROOF_ONLY`). No `sorry` in `spec/`.
- Needed first: ops (section 2), `Bounds` limits (section 4), tariff (section 5), `Data` universal type, `textJoin`, `refuse`, `form` blocks, `write {…}`, string interpolation, `layer over` (section 8).
- Wire: Data JSON `{"tag":"natural","value":"123"}`, lists as `{"tag":"list","items":[…]}`; canonical form is DAG-CBOR, CID = `b` + base32lower(`01 71 12 20` + sha256).
- Checkpoints: edition v2 for new suspensions, v1 still decodes (`decodeStateAny`).
- Pins: a world object's pin is the CID of its source closure (host), not `packetSha256`. `tests/test_artifact_pins.py` guards that world sources keep compiling.
- Tests: 896 `def test_` across `tests/test_*.py`. Kernel-narrow: `test_turn`, `test_canonical`, `test_conformance`, `test_document`, `test_data_type`, `test_tariff`, `test_sugar`, `test_located`, `test_hints`, `test_layers`, `test_artifact_pins`.
- Open: section 9.

## 0. Working rules

- Build: `LEAN_NUM_THREADS=2 lake build` (one Lean process). Never rebuild while a run uses the binary: `tests/host.py` copies it per run (`DELVETALK_OBEND` names the source, `DELVETALK_OBEND_COPY` shares one copy across workers; `tests/run.py` is the parallel runner). Builds may run on hbox with `swarm-build lake build`.
- Run: `DELVETALK_OBEND=$PWD/.lake/build/bin/delvetalk-obend python3 -W ignore -m tests.run [module …]`; whole suite `make check`.
- Proof-only modules (`Delvetalk.PackageDataAdmission`, `PackageDataNormalization`, `PackageDataSchemaProofs`, `Delvetalk.Typed`, `Theory.ObjectiveBendNativeDataSimulation`) are outside the default target; `make build` builds them. Build them after touching anything they import.
- Lean 4.34: `if_pos`/`if_true` deprecation warnings in old Mini files are noise. A doc comment (`/-- -/`) directly before `mutual` is a parse error; use `/- -/`. In a file that opens `ObjectiveBendTypes`, a pattern variable `label` reads as `Ty.label`. `x.isDataUnder a b c d` puts `x` at the first `Ty`-typed parameter.
- Host files belong to the host lane (`spec/Delvetalk/Host/*`); `Journal.lean` is shared.

## 1. Map

Pipeline for `compile`: source -> (document templates, text) -> `ObjectiveBendParse` -> `Surface.Module` -> generics -> `ObjectiveBendElaborate.ofSurface` -> elaboration -> `ATerm` + typing proposal (`propose`) -> closure check on the direct source (once per package) -> per entry: packet JSON -> `decodePacket` -> `Typing.check` -> artifact.

| Stage | Where | Notes |
|---|---|---|
| Surface AST | `Compiler/ObjectiveBendSurface.lean` | Typed AST, a `Span` on every node. `Module.json` renders the old module JSON byte for byte (used by `source-imports-v1`, import transcripts, interface labels, diagnostics). Type annotations are source text. |
| Parser | `Compiler/ObjectiveBendParse.lean` | Declarations `record`, `sum`, `type`, `def`, `law`, generics `<T>`. Strings use JSON escapes. |
| Front end | `Delvetalk/FrontEnd.lean`, `Generics.lean`, `DocumentTemplate.lean` | `parseSource` = template expansion + parse (spans mapped back by `Expansion.remap`). Generics: rank-1 specialization of sums and defs (generic records do not parse). Doc literals need an explicit `import ./Document.obend as X`. `FrontEnd.Prepared` (parse once, generics, `elaboratePackage`, closure check) is entry-independent; `Prepared.lower` runs per entry. |
| Elaborator | `Compiler/ObjectiveBendElaborate.lean` | Surface to a span-keeping core AST to `ATerm`. Core errors are `Refusal {message, loc, hint, expected, found}`. Recursive record/sum = `Ty.variable i` + a bound. `noActivity` is the "effect in shared position" refusal. |
| Driver / `accept` | `Compiler/ObjectiveBendFrontEnd.lean` | `Diagnostic {stage, message, span, sourceModule, hint, definition, expected, found}`. Stages: `objective-source-parse`, `objective-core-elaboration`, `objective-typed-check`, `document-template`, `package-request`. |
| Blame | `Compiler/ObjectiveBendBlame.lean` | `explain`, `locate`, `Naming.render`: diagnostics only; acceptance is `check`'s. |
| Term wire | `Compiler/ObjectiveBendTermWire.lean` | `ATerm.json` <-> `Typing.decodeTerm`. The evaluators' array form differs (section 6). |
| Core terms | `Theory/ObjectiveBendOpenRecursion.lean` | `Term` (27 constructors, incl. `unary`, `inject`, `case`, `ifBool`, `perform`, `done`, `toData`, `textJoin`, `refuse`), `Primitive` (15), `UnaryPrimitive` (3: natText, textLength, sha256Text), `Step`, `Value`. Text prims, `unary`, `toData`, `textJoin`, `refuse` are hosted extensions, not upstream. |
| Types | `Theory/ObjectiveBendTypes.lean` | `Ty`. `isDataUnder bounds rigid fuel seen` / `isPlanUnder`: non-rigid variables unfold through the packet's `bounds` as a greatest fixed point. `Ty.dataFuel` 4096; `Ty.dataFuelFor bounds type` = max of that and the type's size plus its bounds'. |
| Typing | `Theory/ObjectiveBendTyping.lean` | `PartialTyping`, `infer`, `check`, `decodePacket`, `decodeTerm` (`termNestingCapacity` 4096), `Assumptions {bounds, shareableVariables, rigid}`. The `decide`d rule examples at the end are the regression suite for effect rules. |
| Machine | `Theory/ObjectiveBendDemandMachine.lean`, `…MachineFast.lean` | `State {heap, control, stack}`, `Cell`, `Frame`, `Control` (incl. `yielded`, `nativeApplication`, `refused`), `stepRaw`, `runBounded`, `resume`. `Fast` is a proved-equal faster stepper. |
| Data, tariff | `Theory/ObjectiveBendDemandData.lean` | `textStepCost`, `forceHostedFrom` (tick + byte admission before each step), `materializeWith`, `executeStateWith`, `yieldedPlanWith`, `Data.conformsFuel/conformsUnder/size`. `Data` is in `ObjectiveBendFiniteData.lean`. |
| Checkpoint | `Theory/ObjectiveBendCheckpoint.lean` (v1), `…CheckpointV2.lean`, `…DemandCollect.lean` | See section 7. |
| Laws | `Compiler/ObjectiveBendLaw.lean`, `Delvetalk/Host/Law.lean` | `law NAME: EXPR` over declared state; the pure profile refuses laws ("host law adapter"). |
| Typed data/schema | `Delvetalk/PackageData*.lean` | `run-data-v1`, compact codec, schema certificates, `inspect-spec-v1`, `compare-data-types-v1`. Depth is `Bounds.dataWireDepth`. |
| Package, session | `Delvetalk/Package.lean`, `PackageSession.lean`, `spec/PackageMain.lean` | JSON-lines driver; section 2. |
| Source evaluator | `Delvetalk/Core.lean`, `Typed.lean` | Older step-by-step evaluator with evidence; not on the turn path. |

Proof obligations by change:
- `Term`/`Primitive`/`Step`: the `Step` lemmas in OpenRecursion (`lazy_fixed_function`, `case_selects_injected_arm`, primitive exactness) and `Value` ones; Typing's `PartialTyping` mirrors every constructor; checkpoint codec needs a case (`state_roundTrip` fails the build otherwise).
- Typing rule: `checked_erasure`, `agree_sameType`, `partial_beta_law`, `reusable_lambda_capture_rule`, `sameType_isComputation`, the decided examples.
- Machine: `resume_requires_yield`, `resume_keeps_heap_and_stack`, `perform_under_update_refused`, `perform_yields`, and the `Fast` equivalence (`stepRawFast_eq_stepRaw`, `runFrom_eq_runBounded`): a change to `stepRaw` needs the matching `stepRawFast`/`sizesAfter` change.
- Collector: a new frame, cell or control holding addresses must be added to `frameAddresses`/`cellAddresses`/`controlAddresses` and the renamings, or `related_stepRaw` stops building.
- Schema/compact codec: `PackageDataSchemaProofs.lean`. Native cells: `ObjectiveBendNativeDataSimulation.lean`, `ObjectiveBendFiniteDataTyping.lean`.

Proved:
- `state_roundTrip : decodeState (encodeState s) = some s` (v1 codec); `stateV2_roundTrip` for every dictionary and state; `refusal_roundTrip`; `encodeTerm_injective`.
- `settle_resume_segment` and the agreement lemmas on the hosted runner (`agree_forceHostedFrom`, `agree_materializeWith`, `agree_yieldedPlanWith`, `agree_completeWith`). `typed_settle` is not ported (no state-typing judgment).
- Collector (`DemandCollectProofs`): `related_collect`, `related_stepRaw`, `related_forceHostedFrom` (exact under `ExactRoom`, which `limitsPast` gives), `checkpoint_resume_segment`: resuming `checkpoint s = collect (settle s)` decides the same verdict, spends the same ticks and extracts the same Plan/result Data as resuming `s`.
- `conformsUnder_iff : d.conformsUnder bounds ty = true ↔ HasType bounds d ty` (`ObjectiveBendDataConformance.lean`); fuel is never a false negative.
- `sameTypeShared_eq`, `lawTable_names`, `Data.shapeType`/`shape_typing`/`universal_typing`, `SchemaMatches.data`, `Admitted.universal`.

Not proved: that `noActivity` is the static guard matching `perform_under_update_refused`; that `textJoinExpansion` and the machine's join frames agree (conformance tests values only); that an activity typed by the `refuse` rule refuses only through `refuse`; the canonical-CBOR round trip.

## 2. Ops

Wire: one JSON object per line on stdin, one per line out. Errors: `{"status":"error","message":s}`. `PackageSession.step` keeps two per-process caches: prepared closures (bounded by `Bounds.frontCacheSourceBytes`, 8 MiB of source) and held entries indexed by `packetSha256` (bounded by `Bounds.entryCacheBytes`, 64 MiB of artifact); `{"op":"packet-cache-status"}` answers `{fronts, frontSourceBytes, maxFrontSourceBytes, entries, entryBytes, maxEntryBytes, hits, misses}`. `run`, `run-data-v1`, `turn-start`, `turn-resume` take `artifact` as the whole artifact (held if equal to the one this process compiled under that pin, else recompiled and compared) or `{"packetSha256": pin}` alone (held entries only; "unknown packetSha256: …" otherwise). `world-*` ops go to `Host.stepWorld`. `library-load {path}` and `library: <pin>` are in HOST-HANDOFF.

| op | takes | returns |
|---|---|---|
| `compile` | `modules:[{name,source}]` or `source`, `entry`, `limits?`, `library?` | `{status:"compiled", artifact}`; artifact = `{schema, modules, sourcesSha256 (CID), entry, genericInstances, limits, packet, packetSha256 (CID), type, methods, law, laws?}`. Compiler refusals: error message is the diagnostic JSON text. |
| `check-package` | as compile | `{status:"checked", artifact}` or `{status:"refused", diagnostic}`. `Package.checkPackage` is the pure entry. Spanless refusals are localized by `localize` (recompiles each function alone; first with the same stage+message wins). |
| `run` | `artifact`, `arguments`, `limits` | `{status:"finished", value, type, ticksUsed, heapCells, nodesUsed}` or `{status:"refused", failure, …}`. Entry type must be first-order data ("package result must have first-order data type"). |
| `turn-start` | `artifact`, `arguments`, `limits?`, `object`, `principal`, `intent`, `roots` (all required) | `finished`, `yielded {plan, planType, responseType, checkpoint, ticksUsed}`, `exhausted {resource, ticksUsed}` (resource: ticks heap stack nodes bytes), or `error`. The entry must type as `Activity<P,R,A>` with P a sum, R and A data. |
| `turn-resume` | `artifact`, `checkpoint`, `response`, `limits?`, same binding | same replies. Checks in order: entry is an activity; `packetSha256`; digest; object; principal; intent; roots ("checkpoint belongs to another package / digest mismatch / another object / another principal / another intent / was taken under different roots"); decode ("checkpoint does not decode"); response conforms; control is yielded. The response type is re-derived from the artifact. |
| `evaluate-term` | `term` (array wire), `responses?`, `ticks?` | `{schema, result:{status: value\|yield\|exhausted\|stuck, shape, plans}}`. Pure reference for conformance. |
| `render-document` | `document` (Data wire) | `{status:"rendered", text, lines, bytes}`. |
| `canonical-encode` / `canonical-decode` | `data` or `json`, `repeat?` / `hex` | `{cid, hex, bytes, checksum}` / `{data, cid}`; decode is canonical-only. |
| `source-imports-v1`, `template-expand` | modules / source | import edges; expanded document-literal source. |
| `run-data-v1`, `run-compact`, `encode-compact`, `decode-compact`, `inspect-spec-v1`, `compare-data-types-v1`, `allocation-data-types-v1` | typed-schema family | see `PackageData.lean` headers. |

`"profile": true` on `run`, `turn-start`, `turn-resume` returns a tick profile (`Delvetalk/Profile.lean`).

Turn API in Lean (`spec/Delvetalk/Turn.lean`): `startActivity packet args binding budgets : Except String Outcome`, `resumeActivity packet checkpoint binding response budgets`, held-entry forms `Turn.startEntry`/`resumeEntry`. `Outcome = finished | yielded | exhausted resource ticks`. `Binding.make object principal intent roots`. A checkpoint carries its binding and resumes only under the same one; the roots digest is the roots at the start of the activity. `exhaustedResource` classifies failures: ticks; capacity suspension -> heap/stack by simulating one more `stepRaw`, else bytes; `nodes`/`bytes` on a yielded Plan is exact, on a finished result a heuristic that can mislabel. `Budgets {ticks, heap, stack, nodes, bytes}`; on resume, heap is counted past the checkpoint's own heap (`limitsPast`).

Held entries (`Delvetalk/Entry.lean`): `CheckedEntry {pin, source, checked, fuel}` (`.type`, `.ofPacket`, `.apply`). `Package.prepareRequest j`, `Package.compileEntryFrom request entry` (`{artifact, entry, laws}`), `Package.compileEntry`, `Package.executeDataEntry entry args limits`, `Package.executeEntry`. None decodes the packet or re-checks the package.

Annotations: injecting a variant argument or response needs per-injection annotations (`annotateData`, an `AnnotationTree` shaped like the literal, built by `Turn.quoteAt`/`shapeTree`); the checker rejects an unannotated `inject`. A turn argument is checked at `Delvetalk.argumentFuel` = the entry's fuel plus twice the literal's `Term.nodes`. Every data-typed argument is checked with `conformsUnder` first: "turn refused: argument does not conform to its type" (the host maps it to `typeMismatch`).

Artifact extras: `methods` (`Package.methodTable`; `stackMethodTable` for a layer stack: every layer's methods, top first), `law` shape, `laws: [{name, reading}]` (`Package.lawTable`, one per enforced law, source order, key absent without laws), `Limits.lawTicks`.

## 3. Wire and canonical form

Data JSON (`Compiler/ObjectiveBendDataWire.lean`): `natural` (decimal string), `boolean`, `label`, `record {fields:[{name,value}]}`, `variant {label,payload}`, `list {items}`. `dataJson` emits `list` whenever `listItems?` finds a proper `nil`/`cons` chain. `decodeData` refuses a variant chain that forms a proper list ("cons chains are no longer accepted on the wire; send a list", `consChainRefusal`); `PackageData.decode` applies the same rule. Decode depth is nesting, not elements (`Bounds.dataWireDepth` 256; chains cost 2 levels per cell, arrays do not). A decoded list is a `cons` chain in memory. `dataJsonBytes` must equal `(dataJson d).compress.utf8ByteSize` (keep in sync by hand).

Canonical bytes (`Delvetalk/Canonical.lean`, DAG-CBOR as AT Protocol):
- Unsigned int, shortest head; Nat >= 2^64 a big-endian byte string; false/true = f4/f5; label = text; JSON null = f6; list = definite array; record = definite map with keys sorted by UTF-8 byte length then bytes (a repeated field keeps the first); variant = one-key map `{label: payload}`.
- Untyped decode turns every one-key map into a record; `decodeAs bounds ty bytes` re-tags against a type. Round trip is `decode (encode d) = normalize d` for variant-free `d`, and `encode (decode b) = b` for everything; not exposed on the wire; not proved. Never `decodeAs` against `.data` expecting variants back.
- `decode` refuses non-shortest heads, unsorted/duplicate keys, indefinite lengths, tags, floats, null, negative ints, non-canonical bignums, bad UTF-8, trailing bytes, by name ("non-canonical CBOR: …", "CBOR nesting capacity", "CBOR exceeds the node bound").
- `encodeJson`: objects->maps, arrays, strings, bools, null, ints; a fraction is refused. `cidJson` is total (falls back to the CID of the printed text on an unencodable value).
- CID = `"b" ++ base32lower(0x01 0x71 0x12 0x20 ++ sha256(bytes))`, 59 chars, `bafyrei…`. All 166 `record`/`cid` pairs in `tests/fixtures/delve/*.json` encode to the AppView's CID; `tests/wire.py` is an independent Python encoder.

Digests:
- Journal: `Host/Journal.lean` `bodyHash = cidJson`; `verify` names "journal broken at height N: hash mismatch | height out of sequence | previous hash does not chain". Request digests, retry identities, seed digests and delivery ids are CIDs too.
- Artifact: `packetSha256` and `sourcesSha256` are CIDs (the names kept). Per-module source hash inside the packet is hex SHA-256 of the raw source.
- Checkpoint: `Turn.checkpointDigest` = CID of `{packetSha256, object, principal, intent, rootsDigest, tokens}`; `rootsDigest` = CID of `[{object,version}]`; `tokensDigest` = CID of the token JSON. Verified in `resumeActivity` before decoding.

## 4. Limits (`spec/Delvetalk/Limits.lean`, namespace `Delvetalk.Bounds`)

Per machine segment (default / ceiling): `ticks` 100,000 / 1,000,000; `heap` 100,000 / 1,000,000 (cells); `stack` 10,000 / 100,000 (frames); `nodes` 100,000 / 1,000,000 (Data nodes materialized for a result or Plan); `bytes` 1 MiB / 16 MiB (encoded result/Plan bytes and the largest single text-primitive reserve per step). `lawTicks` 100,000. `typeFuelDefault` 16384.

Wire: `dataWireDepth` 256, `plainJsonDepth` 64, `documentWireDepth` 8192, `entryArrowDepth` 64. Packages: `maxModules` 64, `maxModuleBytes` 512 KiB, `maxPackageSourceBytes` 1 MiB (import scan only), `frontCacheSourceBytes` 8 MiB, `entryCacheBytes` 64 MiB. Documents: `documentDepth` 64, `documentNodes` 65,536, `documentOutputBytes` 1 MiB, `offersPerTurn` 16 (their text shares the 1 MiB). `Document.maxOffersPerTurn`/`maxOutputBytes` are aliases that `TurnLoop.lean` reads.

Outside `Limits.lean`: `PackageMain` 16 MiB line frame; `EvaluateTerm` nesting 4096, default 200,000 ticks, `go 64` yields cap; `Canonical` reuses `nodesMax`/`bytesMax`; the host's own `Host.Limits` (`dataDepth` 8192, `plainDepth` 64, `maxTurnTicks` 1,000,000, `maxPackageBytes` 32768 …). Fuel parameters that are not budgets: `Typing.check` fuel, `Ty.dataFuel`, `termNestingCapacity` 4096, `conformsFuel`, `peelArrows`. A fuel exhaustion is a refusal, never a wrong answer, but it looks like a type error.

## 5. Tariff

Every machine transition costs 1 tick. Before a text primitive runs, `forceHostedFrom` admits `(ticks, bytes)` from `textStepCost` and suspends (`ticks` or `capacity`) if either exceeds what is left; the state is retained exactly. B = byte size of the operand, p = exact bytes of the first n scalars (`prefixCost`, a scan bounded by what the allowance can pay).
- `textConcat a b`: `1 + 2(|a|+|b|)`, reserves `|a|+|b|`.
- `textTake t n`: 1 if n=0 or n>=B; else `1 + 2p`, reserves `p`.
- `textDrop t n`: 1 if n=0 or n>=B; else `1 + 2p`, reserves `B - p` (the suffix copy is bounded in bytes, not charged in ticks, so a drop-by-one walk stays linear).
- `textJoin list sep` (each element): `1 + 2*(bytes appended)`, reserves the new accumulator (appended in place when unique).
- `textSpan/textBreak`: `1 + perScalar*visited`, perScalar = `2*(|alphabet|+2)`; refused up front if the cap cannot cover the scan.
- `textLength`: `1+B`. `sha256Text`: `65 + 8*ceil(B/64) + 32*blocks`. `natText n`: `1 + bits^2`. Everything else: 1 tick.

`tests/test_tariff.py` pins the numbers (bump turn 56 + 10; 64-field spell parse 79,583; `Document.plain` over 1,025 leaves 129,272; 1,025-rain Bell card 76,485); update them with a reason when they move. Profile before optimizing the interpreter: the spell parse was 81% text primitives.

Quadratic idioms to avoid: `Lists.append xs x` in a loop; `Lists.length` in a loop; left folds of `textConcat` (use `textJoin`); character walks with `textDrop` (copies the suffix each step, in bytes).

## 6. Evaluators and conformance

`impl/python/evaluator.py`, `impl/js/evaluator.mjs`, `impl/c/evaluator.c` are independent small-step, call-by-name interpreters of the core. Input line `{"name","term","responses","fuel"}`; output `{"name","status": value|yield|exhausted|stuck,"term","plans"}`. Term array wire: `["bound",i] ["nat","12"] ["boolean",b] ["label",s] ["lam",b] ["app",f,a] ["mix",l,u] ["fix",s,i] ["specification",m,e] ["prototype",s,t] ["reflect"|"metadata"|"project"|"perform"|"done",x] ["unary",prim,x] ["binary",prim,l,r] ["get",x,name] ["inject",label,x] ["ifZero",v,z,s] ["ifBool",c,t,f] ["record",[[n,t]..]] ["extend",x,fields] ["case",x,arms] ["refuse",text]`, plus `toData` and `textJoin`. An evaluator that rejects a line stops its stream; the runner restarts it and counts the line `rejected`. Text and unary primitives use code-point semantics; `textTake`/`textDrop` use the byte-size guard `n >= byteSize`; C has its own SHA-256. `perform` yields `status:"yield"` with `plans`, resumed from `responses` in order; `["refuse", text]` is a stuck leaf.

Harness: `tests/conformance/generate.py` (seeded; kinds term, activity, stuck, diverge, shared-effect, exotic-value, chain; asserts every tag and primitive occurs) and `tests/test_conformance.py` (compares status, weak-head shape, and Plans when literal data). `python3 -m tests.test_conformance 1500 [IMPL_DIR]` prints the report. Last recorded (kernel lane, 1500 cases): 1445 agree per evaluator, 55 known shared-effect, 0 unexpected.

Known divergence (`KNOWN_DIVERGENCE["shared-effect"]`): a `perform` reached while forcing a shared argument cell. The machine refuses it (`Refusal.sharedEffect`); call-by-name evaluators perform at each use. Typed programs cannot reach it (`noActivity`). Machine `divergent` and tick/capacity suspension map to `exhausted`. Not compared: step counts, deep values, non-literal plans.

Adding a Term form: extend `generate.py` (and its tag assertion), `EvaluateTerm.termOf`, the three evaluators' validators/arity tables/`reducible`, run the report, and decide fix vs `KNOWN_DIVERGENCE`.

## 7. Checkpoints

- Tokens: `.nat n | .text s` (v1 JSON `{"n":"3"}` / `{"s":"x"}`); v1 edition `dregg.objective-bend.checkpoint.v1`. Term tags 24 (`toData`), 25 (`textJoin`), 26 (`refuse`, `[26, text]`); join frames 14-17; a refusal is `encodeRefusal` (`[8, text]` for `program`). Only additions: old checkpoints decode unchanged; a checkpoint using a new tag does not decode on an older binary.
- v2 (`ObjectiveBendCheckpointV2.lean`, edition `…checkpoint.v2`): written against a `Dictionary` rebuilt from the entry's term (`Dictionary.ofProgram entry.source.term`): a term is one token `i+1` for the program's `i`th subterm in preorder, environments of two or more addresses are a table listed once, strings are `Token.str` references. JSON is bare (`3`, `"x"`, `-(i+1)`). Every reference is emitted only after a check that it names exactly the value, so `stateV2_roundTrip` holds for every dictionary. `Dictionary.ofProgram` runs per start/resume.
- Collector: `collect` numbers live cells by `canonicalOrder` (depth first from the roots; a list spine put off to the next round), so a reading that walks further does not renumber every later cell. `orderValid` checks the order; otherwise `collectByAddress` (the allocation-order collector) is used.
- Host side: `resumeOne` rebuilds the `Checkpoint` from journaled tokens plus the activity's object/principal/intent/roots; changing `Checkpoint` fields stops older journals resuming. Block encoding of tokens is the host's (HOST-HANDOFF 5.6); v2 strings are bare or `str` references, so an utterance is no longer cut into its own leaf.
- Measured at the kernel lane (Garden prose suspension, `tests.test_policy` scenario): v1 248,006 bytes, v2 6,984 bytes.

## 8. Language features added since the lane-2 map

- `Data` (`Ty.data`, `Term.toData`, `Data.of::<T>(value)`): any well-formed first-order data (`Data.wellFormed`), produced only by `toData`; no elimination (`data_not_eliminated`). Runtime: `toData` is its value. Turn arguments are quoted by their declared type at every depth (`Turn.quoteAt`). Implicit injection (`coerceAt`/`coerceArgs`/`coerceGo`): where `Data` is expected and the expression has type `T`, the term is wrapped `toData T`; a value whose type holds an arrow or computation is refused by name ("refused (data-injection): …"). `Plan.obend`'s `call`/`send`/`create` payloads are `Data`. The typed-data schema has `Schema.data`; admission charges `admissionWork` and refuses "typed data value at Data repeats a record field".
- `textJoin(list, sep)`: `Term.textJoin`, frames `joinSeparator/joinList/joinCons/joinHead`, typing `Ty.isTextList`, meaning `textJoinExpansion`.
- Type-argument inference (`Generics.lean`, `inferArguments`, `synthI`): a call of a generic without `::<…>` gets the arguments its explicit spelling names, then is rewritten exactly as that spelling (instance numbers and packets agree; the generics pass visits children in the old JSON's sorted-key order, and changing that order moves every pin with a generic instance). A parameter left unbound is refused: "cannot infer the type argument U of Lists.kept …; write Lists.kept::<T, Rain>(…)". `maxInferenceSteps` bounds it. `world/` uses no `::<` and no `Data.of`.
- `let label(x) = perform(P)` then the rest of the block: lowers to `match perform(P): case label(x): …` plus a `Pattern.unexpected` branch expanded to `case l(_): refuse("unexpected response l")` per other label. The scrutinee must be a `perform` ("refused (let-response)").
- `Term.refuse (reason)`, surface `refuse("why")`: stands only where an activity finishes ("refused (refuse-outside-tail)", "refused (refuse-outside-activity)"). Typing rule `PartialTyping.refuse`; machine `control := .refused (.program r)`, `Turn.refusalText` = "turn refused: <reason>". `evaluate-term` reports `stuck`.
- Law readings: `law NAME "reading": EXPR`; `Surface.Decl.law name source reading`.
- String interpolation (`interpolationPieces`/`joinPieces`): `{expr}` in a string; up to four pieces lower to nested `textConcat`, more to `textJoin(TextPieces…, "")`. `{{`/`}}` are literal braces; a lone `}`, an unclosed `{` and two expressions in one pair of braces are refused by name. Document templates quote braces as `{`/`}`.
- `form ACTION [as NAME]:` blocks (`formRe`/`formKind`): fields `name: text A..B | natural A..B | a | b | c` declare `def NAME() -> F.Form` (default `ACTIONForm`) from the module's alias `F` of `Form.obend`; refused by name without a Form import or with an unknown kind.
- `write {field: op value, …}`: the Plan `Plan.write({object: P.self(context), edits: extend(keep(), {…})})` with ops `add`, `set`, `append`, `remove`, `removeItem`. Needs a local `type Plan`, a nullary `keep()`, a parameter named `context`; `P` is the module's alias of Plan.obend (placeholder `$plans`, replaced by `Surface.Decl.mapVars`).
- `layer over ./X.obend` must be a module's first line (else refused "…is the module's first line"); it imports `X` as `Super`. Every declaration is a field of one knot, so a layer's `L.f` overrides `B.f`: `B.f` holds `self.L.f`, the old body moves to a hygienic `B.f#below`, and a layer's `Super.f` resolves to the key below. `checkOverrides` refuses a retyped override ("refused (layer-override): L.f is …, but it overrides B.f, which is …"). Unlayered packets are byte-identical. `Elaborated.select` takes an entry the top layer lacks from the topmost layer defining it. Tests: `test_layers`.
- Located refusals: every refusal of an elaborated package names `definition`, `module`, `span`; a type refusal `expected` and `found` in surface syntax, with `hint` (`blameHint`: a record where its field was expected, a function waiting for arguments, too many arguments, a missing field, an unknown case). Core `Expr`/`Body` carry the surface span as an implicit `{span}` field; `ATerm.located` is transparent to `json`, `erase`, `annotate`, `mapTypes`, `knotNames`. Generic instances are placed at their generic declaration (`Origins`, `FrontEnd.originsOf`). Test: `test_located`.
- Dialect hints (`Delvetalk/Hints.lean`, `Diagnostic.hint`): only on refusals, at the named line for a parse refusal, at the Surface declaration holding the named line otherwise. `Hints.hintFor` never fires on a typed-packet checker refusal; `blameHint` does. Test: `test_hints`.
- Compile performance structure: package knot holds only what the entry reaches (`Elaborated.select`, `Output.knotRow`; `globalRow` stays whole for the method table and law shape); the whole closure is checked once per package (`checkClosure`: every template and the knot of every declaration as one term) without rendering a packet (`directSource`/`checkDirect`); an entry goes JSON -> `decodePacket` -> `check`. Row width is charged by `typeRowCapacity`, so an entry may reach any number of definitions. Interning: `PTy.internSlot` keyed by constructor, strings and child slots (`InternKey`); the derived `Hashable PTy` rehashes subtrees and is quadratic. `agree` decides through `sameTypeShared` before canonicalizing. `compile-profile` (`spec/CompileProfile.lean`, `lake build compile-profile`) gives stage timings, a loop mode for `perf`, `self-check`, `sha`.
- `tests/test_artifact_pins.py` compiles every non-generic entry of every world closure and compares against `tests/fixtures/pins/artifacts.json` (`{module: {pin, entries: {def: {status, packet?}}}}`, 43 modules, 1124 defs on 2026-10-09). It fails only when a module's source pin changes or a def that compiled stops compiling; packets that recompile differently are counted and printed. Re-record only when `world/` changes: `DELVETALK_OBEND=… python3 -m tests.test_artifact_pins --record`.
- `Package.localize` still localizes spanless refusals in `check-package`; located refusals make it rare.

Compile timings measured on hbox (foundation 7d90f1b and 5b07855, under load): Garden (11 modules, 78 KB) first entry 48 ms, further entries about 9 ms, `check-package` 45 ms. Re-measure before relying on them.

## 9. Open

- Name a prepared package by its sources CID instead of resending it per request (a request carries the whole 78 KB Garden package: about 4 ms of line reading, parsing and reply rendering with no compilation). Closes when the wire accepts `{sourcesSha256}` alone.
- Parse is the largest front-end stage (13 ms for Garden at 7d90f1b): a direct scanner per line regex, checked against the `Re` values the way `tokenLength` was (`compile-profile self-check`).
- An activity entry's packet is 200-250 KB that must be rendered, hashed, decoded and checked per entry.
- A checkpoint-local term table was built and measured: no gain on forced literal lists, worse nine-prose dedup; not committed (the edition name v3 now means relative addresses, §14).
- The `Not proved` list in section 1.

## 14. Surface types (lane/kernel5 after foundation 99c6dff)

- Typed foreign views. `P.view::<S>({object})` (P the object's Plan alias; S any type its
  closure names) is lowered by the generics pass (`rewriteExpr`, `Generics.State.typedViews`)
  to `P.viewAs({object, as: "viewed:M.S"})`, and a match on that perform has its `viewed`
  arm renamed to `viewed:M.S` (also through `let viewed(v) = ...`). At the end of the pass
  the package's instances of the Plan sum gain `viewAs: View with {as: String}` and its
  module's `Response` instances gain `viewed:M.S: {version: Nat, state: S}` per viewed type,
  so the arm is typed by S everywhere it reaches and the activity's response type (which the
  host re-derives from the artifact) holds it. One activity's response type has one arm per
  viewed type; no core rule changed (no per-perform response types). A package without
  typed views is untouched (pins: 0 recompiled). Plan.obend is unchanged: the untyped
  `view`/`viewed` (the viewer's own state) and `viewData` stay. For the host lane: answer
  `viewAs {object, as}` by looking `as` up in the activity's response row, checking the
  object's state with `conformsUnder` against that arm's `state` type, and answering the
  variant `as` {version, state}, `typeMismatch` when it does not conform (the kernel
  refuses a non-conforming response anyway: "response does not conform"). Test:
  `tests/test_typed_view.py`.
- Protocols. `protocol P:` (a declaration, indented `name: TYPE` lines; `(A, B) -> R` is
  read `A -> B -> R`, `() -> R` as `R`) and `implements P` (or `implements Alias.P`; `P`
  alone is looked up in the module, the import aliased `P`, then any import). State, Plan
  and Response in a protocol's types are the implementer's: the generics pass leaves them
  as names, and `checkProtocols` (after every declaration is typed) resolves them as
  placeholder variables that `matchProtocol` binds once per claim, so every method must
  agree on them. Missing method: "refused (protocol): M implements P but defines no m",
  at the `implements` line; mistyped: "refused (protocol): M.m is ..., but protocol P
  declares m: ...", at the method's body, `expected` the declared text, `found` the
  method's type; both hint the protocol. The artifact gains `protocols: [P]` and the
  method rows of protocol methods `protocol: P`, only for a module that claims one
  (others unchanged; pins: 0 recompiled). Surface `Decl.protocol` keeps the declared texts
  (`shown`) for messages beside the rewritten ones. The objects lane writes `protocol
  Card` into Card.obend and `implements Card` into objects (world/ is theirs); the host can
  then refuse a door to a module whose artifact lacks `Card`. Test: `tests/test_protocols.py`.
- Fixed on the way: `Surface.Module.mapSpans` (document-literal span remapping) rebuilt
  the module from imports and decls only, dropping `layerOver`; it keeps every field now.
  `tests.test_extend.LouderBell` (Louder grafted over Bell through the host, Bell's
  `receive` rendering Louder's card) was marked an expected failure and now passes; the
  marker is removed.
- `textHasAny(text, words: List<String>) -> Bool` (hosted primitive `Primitive.textHasAny`,
  checkpoint code 16): whether a word of the list is a whole word of the text. Words are
  maximal runs of ASCII letters, digits and non-ASCII scalars (`textWordChar`), ASCII
  letters lowercased (`textWordsOf`); whitespace and ASCII punctuation separate. The
  elaborator lowers the call to `binary textHasAny text (textJoin words " ")`, so the
  list is walked once by the join (linear) and the primitive makes one pass over each text;
  tariff `1 + 2 * (bytes of both)`, reserving those bytes. An 1,800-character reply checked
  against ten words: 3,942 ticks (the Bend walk the objects lane measured: ~200,000).
  Python, JS and C evaluators and the generator have it; the generator no longer gives the
  FIRST item of a generated join a non-text head (a join of one non-text item is that item
  in the reference expansion but refused by the machine, an untyped-only divergence the
  new primitive's shifted random stream exposed). Conformance 1500: 1435 agree per
  evaluator, 65 known, 0 unexpected. Test: `tests/test_text_words.py`.
  Not done: `textWords(s) -> List<String>`. A primitive returning a list needs a new term
  form (the machine allocating a native list cell, typed by its annotation like `refuse`),
  the full `textJoin`-scale change across the core, machine, Fast and collector proofs and
  both codecs; the directory check only needs `textHasAny`. Queued for decision.
- Checkpoint edition v3 (rehearsal run 9, finding 1): v2 with every address written
  relative to its holder. `relativeState` renames each cell's addresses by `toRelative i`
  (i the cell's number), the control's and stack's by the heap size; v3 encodes that state
  as v2 and decodes with `absoluteState` after. `toRelative i a` is `2*zigzag(i,a)+1` when
  that is shorter than `2*a`, else `2*a`: the skeleton the collector numbers first (knot,
  state) is written absolute from everywhere, data near its holder relative, so a region
  that moved as a whole encodes the same. Proofs: `ofRelative_toRelative`,
  `mapValue/Cell/Frame/Control_inverse`, `absolute_relative`, `stateV3_roundTrip`
  (`ObjectiveBendCheckpointV2RoundTrip.lean`); v2 still decodes. Measured:
  `tests.test_suspension_size` nine speakers median 11,440 -> 10,223 bytes, edit runs
  between consecutive checkpoints 21-107 -> 15-22; one speaker 7,101 -> 8,161 (the
  same 4-6 edits; checkpoints are 8% more tokens, so its fresh blocks are larger). The
  offline rehearsal (`rehearsal/rehearse.py`, same fixtures, both binaries): journal
  6,130,497 -> 5,454,097 bytes, suspended entries median 52,050 -> 41,023. What keeps them
  large: every suspension is the directory's `receive`, and its word check walks the
  reply with `textDrop`, leaving every SUFFIX of the reply as a cached string in the
  heap (the local string table holds them all, quadratic in the reply); a 1,500-character
  reply is ~1 MB of suffixes in the worst case, and the addresses of everything after
  the walk shift by the walk's cell count. `textHasAny` (above) removes both once the
  objects lane switches the check to it; measure the rehearsal again then.
- Relational day 1 (docs/RELATIONAL.md §2, §3, §5). Law grammar (`ObjectiveBendLaw`):
  `insertOnly(F)`, `count(new.F) <= INT`, `count(new.F) <= count(old.F) + INT` (the two
  fields must be the same) and `REF in new.F.COL` (subject or caller; one column), as
  `LawExpr.insertOnly/countLe/countGrowth/memberColumn`, each refused by name when
  misshapen, compiled to `Pred.any []` like `appendOnly`/`member`; `parse_relational` and
  `parse_refuses_relational` (native_decide) are the parse tests. `Host/Law.lean` gained
  fail-closed cases (false) for the four so the tree builds: the host lane denotes them
  (day 2). The `write {...}` atom takes `insert row`, `upsert row`, `retract key`
  (`Plans.Entries.insert({row})`, `.upsert({row})`, `.retract({key})`; the Plan.obend
  constructors are the objects lane's, `test_sugar ...test_relation_edits_are_their_plans`
  compares against a Plan library that has them). `Package.relationsOf`: when the entry
  module declares a nullary `relations()`, `compileEntryFrom` compiles and runs it once and
  the artifact carries `relations: [{field, key: [columns]}]` (refusals name
  `relations():`); `compileEntryCore` is the compile without it (check-package's path).
  Test: `test_sugar.Relations`.

- `canonicalCompare(a, b) -> Nat` (relational day 1): 0/1/2 by the canonical DAG-CBOR
  bytes of two values of ONE first-order type. Not a core form: the elaborator writes the
  comparison out from the type as Bend (`cmpTerm`, `canonicalComparator`), mirroring
  `Delvetalk.Canonical`: Nat numerically (shortest heads and big-endian bignums order so),
  `false < true`, text by UTF-8 byte length then bytes (the new scalar primitive
  `textCanonicalCompare`, checkpoint code 17, all three evaluators and the generator), a
  record field by field in map-key order, a sum by label (same order) then payload, a
  list-shaped sum (`nil: {}`, `cons: {head, tail: itself}`, an array on the wire) by
  length first, then item by item (one `fix` with an accumulator); recursive types are a
  `fix` per type variable. Refused by name: `Data` (Bend cannot read its shape), functions,
  activities, a sum with nil/cons beside other cases (its nil values encode as arrays).
  So the machine, codecs and proofs are untouched; the tariff is the generated term's
  ticks, linear in the values' size. The Data signature the brief named is refused: a Data
  value has no shape Bend can read, and a generic `Relation<T>` is monomorphised before
  elaboration, so `T` is always known where `canonicalCompare` is written. Test:
  `tests/test_canonical_compare.py` (a hundred random records against `canonical-encode`).
  Conformance 1500: 1432 agree per evaluator, 68 known, 0 unexpected.

## 15. Design note: lazy state (RELATIONAL §11 item 4)

**Today.** A turn's state argument is admitted whole as native cells: `Cell.native d` holds
admitted Data, and forcing it allocates its immediate children as native cells and caches
the WHNF (`nativeCached d v`). That is lazy in conversion, not in loading: the host has already materialised every row. `nativeCached` is not a host thunk: its origin is the Data.

**What the machine needs.** One cell kind and one control, no change to `stepRaw`'s
signature: `Cell.stored (h : Handle)`, `Handle = {object, version, field, row : Option key,
size : Nat}`. Entering a stored cell sets `control := .awaitingStore h addr` (one tick),
exactly as `perform` yields, but the *runner* answers it inside the segment:
`forceHostedFrom` calls the host's `fetch : Handle → Option Data` (a parameter, like
`policy`), charges the row, and `supply h d state` overwrites the cell with `native d`
and re-enters it. A relation's `items` becomes a stored spine: forcing the spine cell of
position k yields `cons {head: stored row k, tail: stored spine k+1}` without the row's
data; forcing `head` fetches that row. Two primitives answer from the handle without
forcing: `relationCount(r)` (the handle's `size`; on an ordinary list a walk, as
`textJoin` walks) and `relationLookup(r, key)` (the host's canonical index: one fetch).
`fetch` reads the version the turn read, so replay is deterministic.

**What the proofs say.** `stepRaw`, `resume`, `settle` and the collector see a stored cell
as a leaf holding no address (as `native`): `cellAddresses (.stored _) = []`,
`renameCell` the identity, a codec tag in v2/v3 (`Handle` encodes as its fields).
`related_stepRaw` gains the enter case (control changes, heap does not);
`supply` needs its own lemma `related_supply` (heap agreement after overwriting one
cell with the same Data on both sides), the shape of `related_resume`.
`checkpoint_resume_segment` stays true for any fixed `fetch` (both runs ask the same function): its proof gains a parameter, not an idea. `stateV2/V3_roundTrip` gain one
codec case each. `state_roundTrip` (v1) is untouched: v1 never holds a stored cell.

**Across a suspension.** A yield happens only at a `perform`, never at `awaitingStore`
(the runner answers before continuing), so a checkpoint never stops mid-fetch. A turn
that forced half a list checkpoints forced rows as `nativeCached` (their data inline,
the "forced cells only" the brief asks) and unforced ones as handles naming the version
read at the turn's start. On resume an unforced row is fetched at that version: the host
must answer old versions (it can: `world-object {version}`, HOST-HANDOFF 5.42) or, more
simply, treat a resumed fetch of a row changed since as a stale root and refuse/re-run
the turn, as a moved root does today.

**Roots.** The host records each fetch `(object, field, key, version)`: a turn conflicts only with writes to the keys it forced (or any insert/retract if it called `relationCount`), §3's `keysChangedSince` rule applied to reads.

**Evaluators.** None see stores: a term with a stored state is, by definition, the term
with the Data substituted, which is what they evaluate today. They gain the two
primitives over list literals (`relationCount` = length, `relationLookup` = first row
whose key projection equals the key, by canonical bytes), the generator emits them, and
`evaluate-term` gains an optional `store` table so the machine path with stored cells is
compared against the substituted term.

**Cost per forced row.** One tick to enter, one to supply, and the row's admission work
(`nodes + bytes`, as `prepareNative` charges) plus `1 + 2 * bytes` for the copy, so a
lookup of a 200-byte row is about 450 ticks against today's whole-relation load. A
`count` is one tick. Only forced rows are allocated.

**Estimate.** Kernel: cell, control, `supply`, runner, two primitives, codec cases, the
Fast mirror, collector and settle lemmas, evaluators and generator: 3 lane-days.
Host: `Handle` minting on admission, `fetch` over the store with the canonical key index,
row roots in `judge`, the version-or-stale rule: 3 lane-days. Objects: `Relation.obend`
`count`/`lookup` onto the primitives: half a day. About 6.5 lane-days, after launch as
§11 says; nothing in it changes a pin of an object that does not declare relations.

## 17. World calls (WHOLENESS §1, lane/kernel6)

- Day 1. `Ty.isPlanUnder` admits a record row of data (a message) beside a variant;
  `Ty.performResponse plan T` is `Data` for a record plan, else `T`, and
  `PartialTyping.perform` concludes `computation plan (plan.performResponse T) T`, the checker
  taking `T` from the perform's annotation codomain. A sum-Plan activity is unchanged
  (`sum_plan_response_unchanged`); `message_sites_accepted` sequences a view and a write with
  different result types in one `computation Message Data Nat`;
  `message_then_sum_plan_refused` keeps the dialects apart. Surface `Activity<A>` is
  `computation Message Data A`, `Message` the record of the module named `World` ("…yields
  World.Message, but no module named World is in this package"). The `protocol world:`
  lines are signature form `name<Ps>(INPUT) -> RESULT` (`protocolSignature`; one input,
  refused by name otherwise), stored as `Field {name, type := "INPUT -> RESULT",
  typeParameters}`; the generics pass leaves such methods unrewritten and instantiates them
  at each call. `world.X::<T>(arg)` / `world.X(arg)` (`world` not a local, declaration or
  alias) lowers in the generics pass (`worldCallOf`, `worldMethod`) to the Surface node
  `worldCall method input result arg` with both types rendered for the calling module; `T`
  is inferred only when the input is exactly the one type parameter (`write<E>`,
  `judge<E>`). The elaborator makes it `ATerm.perform Message RESULT {object: {world: "",
  object: "world"}, method, argument: toData INPUT arg}`, the argument injected where the
  input has `Data` fields (`coerceGo`), else refused with `expected`/`found`. `isPerform`
  accepts it, so `let label(x) = world.X(...)` and the shared-position rules hold.
  `write {...}` emits the marker callee `$write` (`writeMarker`); the generics pass makes it
  `world.write(edits)` in an `Activity<R>` definition, `Plan.write({object, edits})`
  otherwise. Surface `perform` in an `Activity<R>` and a world call in an
  `Activity<P, R, A>` are refused by name. Old-dialect packets are byte-identical (pins: 0
  recompiled). Test: `tests/test_world_calls.py` (its `WORLD` is a stand-in for the objects
  lane's World.obend).

- Day 2. Site types at a yield and a resume, without touching the machine, collector or
  codecs (those files are lane perf2's): the machine keeps no positions, so a site is named
  by its plan term. `Turn.performsOf` walks the entry term at the checker's positions and
  reads each perform's annotation codomain; `messageSites` keeps one `(plan term, T)` per
  distinct plan (`termEq`) and refuses an entry in which two performs build the same plan
  term at different types ("refused (world-call-site)", at compile: `Package.messageFields`,
  so no such artifact exists). At a message yield `conclude` finds the site from the plan
  cell's origin in the extracted state (before `checkpoint` settles it), reports its `T` as
  `responseType`, and prefixes the checkpoint tokens with `["delvetalk.checkpoint.site.v1",
  i]`; resume (`resumeType`) strips the prefix (inside the digest), checks the response
  against `T` and decodes the rest. A sum-Plan checkpoint carries no prefix and is
  byte-identical; a prefix on one, or none on a message checkpoint, is refused. No
  `Checkpoint` field changed. The site walk runs per start/resume of a message entry only
  (cache it beside the host lane's per-method dictionary when message objects are common).
  Artifact (message activities only): `dialect: "message"`, `world` (methods the entry's
  sites name, first occurrence), `worldProtocol` (the World module's source SHA-256 hex).
  Tests: `tests/test_world_calls.py` `SiteTypes`.

## 16. Queue for the successor (lane/kernel6, after foundation e9d8ca9)

Done on lane/kernel6 (§17): Wholeness kernel day 1 (c6033f7) and day 2 (9d65553). Remaining,
in order:

1. **Day 4 (after the objects lane has moved every object to `Activity<R>`):** refuse
   `Activity<P, R, A>` and a sum Plan by name (`sourceType`'s three-argument case and
   `Ty.isPlanUnder`'s variant case; the decided examples at Typing ~1545-1600 move to the
   message form), delete the `$write` Plan branch (`writeLowered`), surface `perform`, the
   typed-view rewrite (`typedViews`, `viewAs`) and `Package.methodTable`'s old rows, then
   re-record the pins once with the relational re-record (WHOLENESS §4, RELATIONAL §9).
2. **`textWords(s) -> List<String>`**, only if an object still needs it once the objects
   lane uses `textHasAny` (no `world/` source does yet). Shape as the old §16 item 1: a
   list-producing term form, which touches the machine, collector and checkpoint codecs,
   now lane perf2's files; route through the root.
3. Cache `Turn.messageSites` per held entry beside the host's per-method dictionary
   (e01f1e5) when message objects are common: today it is one term walk per start/resume
   of a message entry.

Contract notes. WHOLENESS §1 says the yield's site is "the annotation at the preorder index
of the yielded perform (the index `Dictionary.ofProgram` assigns)": the dictionary indexes
terms, not positions, and identical perform terms share an index, so a site is named by its
plan term and an entry whose world calls build one message at two result types is refused
(`refused (world-call-site)`). The old §16's route to the term at resume (keep the plan
cell's origin in `settleCell`) is in DemandCollect, now lane perf2's; the site index rides
as a checkpoint token prefix instead (§17). "No `Checkpoint` field changes" holds; the
token stream of a message checkpoint gains two leading tokens.

## 17. World calls (WHOLENESS §1, lane/kernel6)

- Day 1. `Ty.isPlanUnder` admits a record row of data (a message) beside a variant;
  `Ty.performResponse plan T` is `Data` for a record plan, else `T`, and
  `PartialTyping.perform` concludes `computation plan (plan.performResponse T) T`, the checker
  taking `T` from the perform's annotation codomain. A sum-Plan activity is unchanged
  (`sum_plan_response_unchanged`); `message_sites_accepted` sequences a view and a write with
  different result types in one `computation Message Data Nat`;
  `message_then_sum_plan_refused` keeps the dialects apart. Surface `Activity<A>` is
  `computation Message Data A`, `Message` the record of the module named `World` ("…yields
  World.Message, but no module named World is in this package"). The `protocol world:`
  lines are signature form `name<Ps>(INPUT) -> RESULT` (`protocolSignature`; one input,
  refused by name otherwise), stored as `Field {name, type := "INPUT -> RESULT",
  typeParameters}`; the generics pass leaves such methods unrewritten and instantiates them
  at each call. `world.X::<T>(arg)` / `world.X(arg)` (`world` not a local, declaration or
  alias) lowers in the generics pass (`worldCallOf`, `worldMethod`) to the Surface node
  `worldCall method input result arg` with both types rendered for the calling module; `T`
  is inferred only when the input is exactly the one type parameter (`write<E>`,
  `judge<E>`). The elaborator makes it `ATerm.perform Message RESULT {object: {world: "",
  object: "world"}, method, argument: toData INPUT arg}`, the argument injected where the
  input has `Data` fields (`coerceGo`), else refused with `expected`/`found`. `isPerform`
  accepts it, so `let label(x) = world.X(...)` and the shared-position rules hold.
  `write {...}` emits the marker callee `$write` (`writeMarker`); the generics pass makes it
  `world.write(edits)` in an `Activity<R>` definition, `Plan.write({object, edits})`
  otherwise. Surface `perform` in an `Activity<R>` and a world call in an
  `Activity<P, R, A>` are refused by name. Old-dialect packets are byte-identical (pins: 0
  recompiled). Test: `tests/test_world_calls.py` (its `WORLD` is a stand-in for the objects
  lane's World.obend).

- Day 2. Site types at a yield and a resume, without touching the machine, collector or
  codecs (those files are lane perf2's): the machine keeps no positions, so a site is named
  by its plan term. `Turn.performsOf` walks the entry term at the checker's positions and
  reads each perform's annotation codomain; `messageSites` keeps one `(plan term, T)` per
  distinct plan (`termEq`) and refuses an entry in which two performs build the same plan
  term at different types ("refused (world-call-site)", at compile: `Package.messageFields`,
  so no such artifact exists). At a message yield `conclude` finds the site from the plan
  cell's origin in the extracted state (before `checkpoint` settles it), reports its `T` as
  `responseType`, and prefixes the checkpoint tokens with `["delvetalk.checkpoint.site.v1",
  i]`; resume (`resumeType`) strips the prefix (inside the digest), checks the response
  against `T` and decodes the rest. A sum-Plan checkpoint carries no prefix and is
  byte-identical; a prefix on one, or none on a message checkpoint, is refused. No
  `Checkpoint` field changed. The site walk runs per start/resume of a message entry only
  (cache it beside the host lane's per-method dictionary when message objects are common).
  Artifact (message activities only): `dialect: "message"`, `world` (methods the entry's
  sites name, first occurrence), `worldProtocol` (the World module's source SHA-256 hex).
  Tests: `tests/test_world_calls.py` `SiteTypes`.

## 16. Queue for the successor (lane/kernel5 at 9a29080, after foundation b47046b)

Done on this lane and committed (each green on hbox, details in §14 and §15): typed views
(9c5af54), protocols (b1fe9f8), `textHasAny` (d8929d9), checkpoint v3 relative addresses
(e6b6b86), relational grammar atoms + `write` insert/upsert/retract + `relations` in the
artifact (b05234d), the lazy-state note §15 (b00b32d), `canonicalCompare` (5994055).
Nothing of the Wholeness kernel work is started; the tree is clean. Run in this order:

1. **`textWords(s) -> List<String>`** (not done). Needs a list-producing term form: on a
   label value the machine allocates one native cell holding the words' Data list and
   enters it; typed by its annotation's codomain (`isTextList`), like `refuse`; checkpoint
   tag in v1 and v2/v3 codecs, `related_stepRaw` case (a native allocation, as
   `forceNative`), Fast `sizesAfter`, the three evaluators (`["textWords", x]` steps to a
   list literal), the generator. Words as `textWordsOf` (OpenRecursion). Only if the
   objects lane still needs it after switching to `textHasAny`.
2. **Wholeness kernel day 1** (WHOLENESS §1, §4). Fixed shapes and what the contract gets
   wrong or leaves open, as found reading the code:
   - `Ty.isPlanUnder` admits a record row of data (`.field`/`.emptyRow`, or a variable
     bound to one) beside a variant.
   - `PartialTyping.perform` concludes `computation planType (performResponse planType T) T`
     with `performResponse` = `.data` when the plan type is a row (message dialect), else
     `T` (old dialect: `T` is the activity's `R`, so every old packet and the decided
     examples at Typing ~1550-1600 are unchanged). The checker's perform case already takes
     `T` from the annotation's codomain; only the conclusion's middle type changes.
   - Surface `Activity<A>` = `computation Message .data A`, `Message` resolved as the record
     `Message` of the module named `World` (refuse by name when the closure has none).
     `St.effect` is then `(Message, .data)`.
   - World calls: lower in the generics pass (it is the only place type arguments
     instantiate): `world.X::<T>(arg)` / `world.X(arg)` → a NEW Surface/core Expr
     `typedPerform (resultType : String) (plan : Expr)` with plan
     `{object: {world: "", object: "world"}, method: "X", argument: Data.of::<Input[T]>(arg)}`
     and `resultType` the rendered `Result[T]`; the elaborator emits
     `ATerm.perform Message ResultT planTerm` (its `response` field becomes the site type,
     `annotate` already writes it as the codomain). `isPerform` must accept it (for
     `let label(x) =` and `noActivity`). Infer `T` only when the method's input is exactly
     the type parameter (`write<E>`, `judge<E>`); otherwise require `::<T>`.
   - The `protocol world:` lines are SIGNATURE form `name<Ps>(INPUT) -> RESULT`, unlike
     this lane's `name: TYPE` protocol lines: extend `Surface.Decl.protocol` with per-method
     type parameters, parse both line forms, and in `Generics.rewriteDecl` bind each
     method's parameters (and State/Plan/Response) as atoms. `implements` (this lane)
     stays for the `name: TYPE` form.
   - `write {…}` relowering to `world.write(extend(keep(), {...}))`: decide by dialect (the
     parser does not know it); suggested: the parser emits a marker callee and the generics
     pass picks `Plan.write` when the module has a `Plan` type alias, else `world.write`.
   - Surface `perform(...)` inside an `Activity<A>` body: refuse by name ("an Activity<A>
     yields only world calls"); keep it for the old dialect until day 4.
3. **Wholeness kernel day 2.** Site types at a yield and a resume (the contract's
   "annotation at the preorder index of the yielded perform"): at a yield the plan cell
   holds the perform's argument subterm, but `settle` replaces every cached origin with a
   self origin, so the term is gone in the checkpoint. Fix found: make `settleCell` keep,
   for the yielded plan cell only, `⟨planTerm, []⟩` (environment emptied, so collection
   retains nothing); `settle_heap_erased`/`agree_settle` hold unchanged because `Agree` is
   equality up to cached origins (`eraseCell`). Then `Turn.conclude` and
   `resumeActivity`/`resumeEntry` find the site: plan cell origin term → its index by
   `Dictionary.findTerm` → a map index → `T` built once per entry by walking the entry
   term in `Dictionary.addTerm`'s preorder with the checker's positions (`lam [0]`, `app
   [0][1]`, record field `i`, `extend`/`case` `[1, i]`, …) and reading each `perform`'s
   annotation codomain. Report it as the yield's `responseType` and check the response
   against it (message dialect only; old dialect keeps `R`).
   Artifact: `dialect: "message"` when the entry's activity is `computation Message …`
   (absent otherwise, so old artifacts are byte-identical), `world: [method names]` the
   entry's packet performs (scan its `ATerm.perform` plans for the `method` label), and
   the World module's source sha256 as `worldProtocol`. Tests: `test_sugar` (world-call
   lowering against the explicit `typedPerform` spelling is impossible in source, so
   compare packets of `world.view::<S>` with a hand-built expected plan JSON), new
   `test_world_calls` (turn-start yields the Message; `responseType` is `Viewed<S>`;
   turn-resume with `viewed {version, state}` finishes; a non-conforming response is
   refused). Re-record `tests/fixtures/pins/artifacts.json` only if a world packet moves
   (it should not until objects migrate). KERNEL-HANDOFF gets the section.
4. **Day 4 (after the objects lane):** refuse `Activity<P, R, A>` and variant Plans by
   name; delete the old perform dialect.

Contract notes. `canonicalCompare` was asked as `(Data, Data)`; it is `(T, T)` for one
first-order `T` (Data has no shape Bend can read; generic `Relation<T>` is monomorphised).
RELATIONAL §5's atoms compile to `Pred.any []`; the host's `Law.lean` fails closed on them
until it denotes them. The rehearsal's large suspensions come mostly from the directory's
word walk leaving every suffix of the reply in the heap (§14), which `textHasAny` removes
once the objects lane switches.

