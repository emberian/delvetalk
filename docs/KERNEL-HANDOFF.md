# Kernel handoff

State on 2026-10-10 (foundation after lane/kernel9; the queue is §16).

## Summary

The kernel is the Objective Bend edition: source text to a checked typed packet, a demand machine with a tick tariff, a checkpoint codec, and the wire and canonical forms. The host (HOST-HANDOFF) calls it through `Turn.lean` and `Package.lean`; JSON exists only at the process boundary.

- Language: `spec/bend/Compiler/` (Surface, Parse, Elaborate, FrontEnd, Blame, Law, TermWire, DataWire, Sha256) and `spec/bend/Theory/` (OpenRecursion, Types, Typing, DemandMachine, DemandMachineFast, DemandData, Checkpoint, CheckpointV2, DemandCollect and the proofs). Delvetalk side: `spec/Delvetalk/` `FrontEnd`, `Generics`, `DocumentTemplate`, `Hints`, `Package`, `PackageSession`, `Turn`, `Entry`, `Limits`, `Canonical`, `Document`, `Profile`, `EvaluateTerm`, `PackageData*`; driver `spec/PackageMain.lean`.
- Binary: `.lake/build/bin/delvetalk-obend` (`lake build`; `make build` also builds the proof-only modules in `PROOF_ONLY`). No `sorry` in `spec/`.
- One dialect (§21): an activity is `Activity<A>` = `computation Message Data A`; its only yields are world calls `world.X(arg)` / `world.X::<T>(arg)` against `world/lib/World.obend`'s `protocol world` (§17), each resumed at its site's type. Surface `perform` and `Activity<P, R, A>` are refused by name.
- The State is the schema (§23): `Edits`/`keep()` derived from `record State` (a `fixed` field has no edit); a `form` block declares its method's input record `NameInput` and, absent a hand-written one, `forms()`.
- Relations (§14, §22): law atoms `insertOnly`, `count`, column membership; `insert`/`upsert`/`retract` in `write {...}`; `canonicalCompare`; the artifact's `relations: [{field, key, limit, retain?}]`, evaluated once per package.
- Wire: Data JSON `{"tag":"natural","value":"123"}`, lists as `{"tag":"list","items":[…]}`; canonical form is DAG-CBOR, CID = `b` + base32lower(`01 71 12 20` + sha256).
- Checkpoints: edition v3 only (`decodeCheckpoint`); v1 and v2 no longer decode (day 4, §21).
- Pins: a world object's pin is the CID of its source closure (host), not `packetSha256`. `tests/test_artifact_pins.py` guards that world sources keep compiling.
- Tests: 1,079 `def test_` across `tests/test_*.py` (lane/kernel9). Kernel-narrow: `test_turn`, `test_canonical`, `test_conformance`, `test_document`, `test_data_type`, `test_tariff`, `test_sugar`, `test_located`, `test_hints`, `test_layers`, `test_artifact_pins`.
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
| Core terms | `Theory/ObjectiveBendOpenRecursion.lean` | `Term` (27 constructors, incl. `unary`, `inject`, `case`, `ifBool`, `perform`, `done`, `toData`, `textJoin`, `refuse`), `Primitive` (17, with `textHasAny` and `textCanonicalCompare`), `UnaryPrimitive` (3: natText, textLength, sha256Text), `Step`, `Value`. Text prims, `unary`, `toData`, `textJoin`, `refuse` are hosted extensions, not upstream. |
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
- `plainV2_roundTrip` and `stateV3_roundTrip` for every dictionary and state (the v1 and v2 state codecs and their round trips are deleted, §21); the token codec round trips of terms, values, data, frames and controls (`ObjectiveBendCheckpointRoundTrip`); `refusal_roundTrip`; `encodeTerm_injective`.
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
| `turn-start` | `artifact`, `arguments`, `limits?`, `object`, `principal`, `intent`, `roots` (all required) | `finished`, `yielded {plan, planType, responseType, checkpoint, ticksUsed}`, `exhausted {resource, ticksUsed}` (resource: ticks heap stack nodes bytes), or `error`. The entry must type as `Activity<A>` (plan `World.Message`, a record of data; response `Data`; each yield resumes at its site's type, §17). |
| `turn-resume` | `artifact`, `checkpoint`, `response`, `limits?`, same binding | same replies. Checks in order: entry is an activity; `packetSha256`; digest; object; principal; intent; roots ("checkpoint belongs to another package / digest mismatch / another object / another principal / another intent / was taken under different roots"); decode ("checkpoint does not decode"); response conforms; control is yielded. The response type is re-derived from the artifact. |
| `evaluate-term` | `term` (array wire), `responses?`, `ticks?` | `{schema, result:{status: value\|yield\|exhausted\|stuck, shape, plans}}`. Pure reference for conformance. |
| `render-document` | `document` (Data wire) | `{status:"rendered", text, lines, bytes}`. |
| `canonical-encode` / `canonical-decode` | `data` or `json`, `repeat?` / `hex` | `{cid, hex, bytes, checksum}` / `{data, cid}`; decode is canonical-only. |
| `source-imports-v1`, `template-expand` | modules / source | import edges; expanded document-literal source. |
| `run-data-v1`, `run-compact`, `encode-compact`, `decode-compact`, `inspect-spec-v1`, `compare-data-types-v1`, `allocation-data-types-v1` | typed-schema family | see `PackageData.lean` headers. |

`"profile": true` on `run`, `turn-start`, `turn-resume` returns a tick profile (`Delvetalk/Profile.lean`).

Turn API in Lean (`spec/Delvetalk/Turn.lean`): `startActivity packet args binding budgets : Except String Outcome`, `resumeActivity packet checkpoint binding response budgets`, held-entry forms `Turn.startEntry`/`resumeEntry`. `Outcome = finished | yielded | exhausted resource ticks`. `Binding.make object principal intent roots`. A checkpoint carries its binding and resumes only under the same one; the roots digest is the roots at the start of the activity. `exhaustedResource` classifies failures: ticks; capacity suspension -> heap/stack by simulating one more `stepRaw`, else bytes; `nodes`/`bytes` on a yielded Plan is exact, on a finished result a heuristic that can mislabel. `Budgets {ticks, heap, stack, nodes, bytes}`; on resume, heap is counted past the checkpoint's own heap (`limitsPast`).

Held entries (`Delvetalk/Entry.lean`): `CheckedEntry {pin, source, checked, fuel}` (`.type`, `.ofPacket`, `.apply`). `Package.prepareRequest j`, `Package.compileEntryFrom request entry` (`{artifact, entry, laws}`), `Package.compileEntry`, `Package.executeDataEntry entry args limits`, `Package.executeEntry`. None decodes the packet or re-checks the package.

Annotations: injecting a variant argument or response needs per-injection annotations (an `AnnotationTree` shaped like the literal, built by `Turn.quoteAt`/`shapeTree`); the checker rejects an unannotated `inject`. A turn argument is checked at `Delvetalk.argumentFuel` = the entry's fuel plus twice the literal's `Term.nodes`. Every data-typed argument is checked with `conformsUnder` first: "turn refused: argument does not conform to its type" (the host maps it to `typeMismatch`).

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

`tests/test_tariff.py` pins the bump turn (73 + 10 ticks since day 4) and `Document.plain` over 1,025 leaves (129,272); library workloads are bounded where that code is tested (`test_hub`: glm's 1,788-character reply under a bell under 20,000 ticks, the directory's reading under 250,000). Update a pin with a reason when it moves. Profile before optimizing the interpreter: the Bend spell parse was 81% text primitives, and the host parses spells now.

Quadratic idioms to avoid: `Lists.append xs x` in a loop; `Lists.length` in a loop; left folds of `textConcat` (use `textJoin`); character walks with `textDrop` (copies the suffix each step, in bytes).

## 6. Evaluators and conformance

`impl/python/evaluator.py`, `impl/js/evaluator.mjs`, `impl/c/evaluator.c` are independent small-step, call-by-name interpreters of the core. Input line `{"name","term","responses","fuel"}`; output `{"name","status": value|yield|exhausted|stuck,"term","plans"}`. Term array wire: `["bound",i] ["nat","12"] ["boolean",b] ["label",s] ["lam",b] ["app",f,a] ["mix",l,u] ["fix",s,i] ["specification",m,e] ["prototype",s,t] ["reflect"|"metadata"|"project"|"perform"|"done",x] ["unary",prim,x] ["binary",prim,l,r] ["get",x,name] ["inject",label,x] ["ifZero",v,z,s] ["ifBool",c,t,f] ["record",[[n,t]..]] ["extend",x,fields] ["case",x,arms] ["refuse",text]`, plus `toData` and `textJoin`. An evaluator that rejects a line stops its stream; the runner restarts it and counts the line `rejected`. Text and unary primitives use code-point semantics; `textTake`/`textDrop` use the byte-size guard `n >= byteSize`; C has its own SHA-256. `perform` yields `status:"yield"` with `plans`, resumed from `responses` in order; `["refuse", text]` is a stuck leaf.

Harness: `tests/conformance/generate.py` (seeded; kinds term, activity, stuck, diverge, shared-effect, exotic-value, chain; asserts every tag and primitive occurs) and `tests/test_conformance.py` (compares status, weak-head shape, and Plans when literal data). `python3 -m tests.test_conformance 1500 [IMPL_DIR]` prints the report. Last recorded (kernel lane, 1500 cases): 1445 agree per evaluator, 55 known shared-effect, 0 unexpected.

Known divergence (`KNOWN_DIVERGENCE["shared-effect"]`): a `perform` reached while forcing a shared argument cell. The machine refuses it (`Refusal.sharedEffect`); call-by-name evaluators perform at each use. Typed programs cannot reach it (`noActivity`). Machine `divergent` and tick/capacity suspension map to `exhausted`. Not compared: step counts, deep values, non-literal plans.

Adding a Term form: extend `generate.py` (and its tag assertion), `EvaluateTerm.termOf`, the three evaluators' validators/arity tables/`reducible`, run the report, and decide fix vs `KNOWN_DIVERGENCE`.

## 7. Checkpoints

- Tokens: `.nat n | .text s | .str i`, JSON bare (`3`, `"x"`, `-(i+1)`). Term tags 24 (`toData`), 25 (`textJoin`), 26 (`refuse`, `[26, text]`); join frames 14-17; a refusal is `encodeRefusal` (`[8, text]` for `program`). Only additions: a checkpoint using a new tag does not decode on an older binary.
- Edition v3 (`ObjectiveBendCheckpointV2.lean`, `…checkpoint.v3`, §14): the dictionary encoding below of the state with every address relative to its holder. Written against a `Dictionary` rebuilt from the entry's term (`Dictionary.ofProgram entry.source.term`): a term is one token `i+1` for the program's `i`th subterm in preorder, environments of two or more addresses are a table listed once, strings are `Token.str` references. Every reference is emitted only after a check that it names exactly the value, so `stateV3_roundTrip` holds for every dictionary. `Dictionary.ofProgram` runs per start/resume.
- Collector: `collect` numbers live cells by `canonicalOrder` (depth first from the roots; a list spine put off to the next round), so a reading that walks further does not renumber every later cell. `orderValid` checks the order; otherwise `collectByAddress` (the allocation-order collector) is used.
- Host side: `resumeOne` rebuilds the `Checkpoint` from journaled tokens plus the activity's object/principal/intent/roots; changing `Checkpoint` fields stops older journals resuming. Block encoding of tokens is the host's (HOST-HANDOFF 5.6); v2 strings are bare or `str` references, so an utterance is no longer cut into its own leaf.
- Measured at the kernel lane (Garden prose suspension, `tests.test_policy` scenario): v1 248,006 bytes, v2 6,984 bytes.

## 8. Language features added since the lane-2 map

- `Data` (`Ty.data`, `Term.toData`, `Data.of::<T>(value)`): any well-formed first-order data (`Data.wellFormed`), produced only by `toData`; no elimination (`data_not_eliminated`). Runtime: `toData` is its value. Turn arguments are quoted by their declared type at every depth (`Turn.quoteAt`). Implicit injection (`coerceAt`/`coerceArgs`/`coerceGo`): where `Data` is expected and the expression has type `T`, the term is wrapped `toData T`; a value whose type holds an arrow or computation is refused by name ("refused (data-injection): …"). `Plan.obend`'s `call`/`send`/`create` payloads are `Data`. The typed-data schema has `Schema.data`; admission charges `admissionWork` and refuses "typed data value at Data repeats a record field".
- `textJoin(list, sep)`: `Term.textJoin`, frames `joinSeparator/joinList/joinCons/joinHead`, typing `Ty.isTextList`, meaning `textJoinExpansion`.
- Type-argument inference (`Generics.lean`, `inferArguments`, `synthI`): a call of a generic without `::<…>` gets the arguments its explicit spelling names, then is rewritten exactly as that spelling (instance numbers and packets agree; the generics pass visits children in the old JSON's sorted-key order, and changing that order moves every pin with a generic instance). A parameter left unbound is refused: "cannot infer the type argument U of Lists.kept …; write Lists.kept::<T, Rain>(…)". `maxInferenceSteps` bounds it. `world/` writes `::<T>` only where a world call's result type cannot be inferred (`world.view::<S>`, `world.call::<R>`, `world.interpret::<R>`) and never `Data.of`.
- `let label(x) = world.METHOD(arg)` then the rest of the block: lowers to `match world.METHOD(arg): case label(x): …` plus a `Pattern.unexpected` branch expanded to `case l(_): refuse("unexpected response l")` per other label. The scrutinee must be a world call ("refused (let-response)").
- `Term.refuse (reason)`, surface `refuse("why")`: stands only where an activity finishes ("refused (refuse-outside-tail)", "refused (refuse-outside-activity)"). Typing rule `PartialTyping.refuse`; machine `control := .refused (.program r)`, `Turn.refusalText` = "turn refused: <reason>". `evaluate-term` reports `stuck`.
- Law readings: `law NAME "reading": EXPR`; `Surface.Decl.law name source reading`.
- String interpolation (`interpolationPieces`/`joinPieces`): `{expr}` in a string; up to four pieces lower to nested `textConcat`, more to `textJoin(TextPieces…, "")`. `{{`/`}}` are literal braces; a lone `}`, an unclosed `{` and two expressions in one pair of braces are refused by name. Document templates quote braces as `{`/`}`.
- `form ACTION [as NAME]:` blocks (`formRe`/`formKind`): fields `name: text A..B | natural A..B | source | a | b | c` (`source` is `F.Kind.source({})`, Bend source the host reads as text of 1 to `Host.Limits.formSourceMax` 16,384 characters and fills from a reply's ```obend fence; the Workshop's `check` and `propose` declare it) declare `def NAME() -> F.Form` (default `ACTIONForm`) from the module's alias `F` of `Form.obend`; refused by name without a Form import or with an unknown kind.
- `write {field: op value, …}`: the world call `world.write(extend(keep(), {…}))` with ops `add`, `set`, `append`, `remove`, `amend ITEM with CHANGE`, `removeItem`, `insert`, `upsert`, `retract` (`remove` and `amend` as §22 says). Needs a nullary `keep()`; `P` is the module's alias of Plan.obend (placeholder `$plans`, replaced by `Surface.Decl.mapVars`).
- `layer over ./X.obend` must be a module's first line (else refused "…is the module's first line"); it imports `X` as `Super`. Every declaration is a field of one knot, so a layer's `L.f` overrides `B.f`: `B.f` holds `self.L.f`, the old body moves to a hygienic `B.f#below`, and a layer's `Super.f` resolves to the key below. `checkOverrides` refuses a retyped override ("refused (layer-override): L.f is …, but it overrides B.f, which is …"). Unlayered packets are byte-identical. `Elaborated.select` takes an entry the top layer lacks from the topmost layer defining it. Tests: `test_layers`.
- Located refusals: every refusal of an elaborated package names `definition`, `module`, `span`; a type refusal `expected` and `found` in surface syntax, with `hint` (`blameHint`: a record where its field was expected, a function waiting for arguments, too many arguments, a missing field, an unknown case). Core `Expr`/`Body` carry the surface span as an implicit `{span}` field; `ATerm.located` is transparent to `json`, `erase`, `annotate`, `mapTypes`, `knotNames`. Generic instances are placed at their generic declaration (`Origins`, `FrontEnd.originsOf`). Test: `test_located`.
- Dialect hints (`Delvetalk/Hints.lean`, `Diagnostic.hint`): only on refusals, at the named line for a parse refusal, at the Surface declaration holding the named line otherwise. `Hints.hintFor` never fires on a typed-packet checker refusal; `blameHint` does. Test: `test_hints`.
- Compile performance structure: package knot holds only what the entry reaches (`Elaborated.select`, `Output.knotRow`; `globalRow` stays whole for the method table and law shape); the whole closure is checked once per package (`checkClosure`: every template and the knot of every declaration as one term) without rendering a packet (`directSource`/`checkDirect`); an entry goes JSON -> `decodePacket` -> `check`. Row width is charged by `typeRowCapacity`, so an entry may reach any number of definitions. Interning: `PTy.internSlot` keyed by constructor, strings and child slots (`InternKey`); the derived `Hashable PTy` rehashes subtrees and is quadratic. `agree` decides through `sameTypeShared` before canonicalizing. `compile-profile` (`spec/CompileProfile.lean`, `lake build compile-profile`) gives stage timings, a loop mode for `perf`, `self-check`, `sha`.
- `tests/test_artifact_pins.py` compiles every non-generic entry of every world closure and compares against `tests/fixtures/pins/artifacts.json` (`{module: {pin, entries: {def: {status, packet?}}}}`, 43 modules and 1,036 defs at 189b534). It fails only when a module's source pin changes or a def that compiled stops compiling; packets that recompile differently are counted and printed. Re-record only when `world/` changes: `DELVETALK_OBEND=… python3 -m tests.test_artifact_pins --record`.
- `Package.localize` still localizes spanless refusals in `check-package`; located refusals make it rare.

Compile timings measured on hbox (foundation 7d90f1b and 5b07855, under load): Garden (11 modules, 78 KB) first entry 48 ms, further entries about 9 ms, `check-package` 45 ms. Re-measure before relying on them.

## 9. Open

- Name a prepared package by its sources CID instead of resending it per request (a request carries the whole 78 KB Garden package: about 4 ms of line reading, parsing and reply rendering with no compilation). Closes when the wire accepts `{sourcesSha256}` alone.
- Parse is the largest front-end stage (13 ms for Garden at 7d90f1b): a direct scanner per line regex, checked against the `Re` values the way `tokenLength` was (`compile-profile self-check`).
- An activity entry's packet is 200-250 KB that must be rendered, hashed, decoded and checked per entry.
- A checkpoint-local term table was built and measured: no gain on forced literal lists, worse nine-prose dedup; not committed (the edition name v3 now means relative addresses, §14).
- The `Not proved` list in section 1.
- Turn performance: docs/PERF.md (lane/perf2). The machine runs 25 to 37 million ticks a second; a directory turn spends about two thirds of its drive loop encoding, digesting, re-digesting and decoding a checkpoint per segment the host answers in process. Its items 1, 2 and 4 are this lane's (`Turn.lean`, `ObjectiveBendTyping.infer`).

## 14. Surface types (lane/kernel5 after foundation 99c6dff)

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
  `tests.test_extend.LateBinding` (Louder grafted over Bell through the host, Bell's
  `receive` rendering Louder's card) was an expected failure and passes.
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
  (`ObjectiveBendCheckpointV2RoundTrip.lean`); v2 decoded beside it until day 4 (§21). Measured then:
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
`checkpoint_resume_segment` stays true for any fixed `fetch` (both runs ask the same function): its proof gains a parameter, not an idea. `stateV3_roundTrip` gains one
codec case each.

**Across a suspension.** A yield happens only at a `perform`, never at `awaitingStore`
(the runner answers before continuing), so a checkpoint never stops mid-fetch. A turn
that forced half a list checkpoints forced rows as `nativeCached` (their data inline,
the "forced cells only" the brief asks) and unforced ones as handles naming the version
read at the turn's start. On resume an unforced row is fetched at that version: the host
must answer old versions (it can: `world-object {version}`, HOST-HANDOFF 5.7, and `viewAt`, 5.47) or, more
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

## 16. Queue for the successor (lane/kernel9, after foundation 3f743e2)

Done: items 1-6 (kernel7, kernel8: §19-§22); item 8, the State is the schema (kernel9, §23):
`Edits`/`keep()` derived from `State` and a hand-written pair refused, `fixed` State fields, form
blocks declaring `NameInput` and `forms()` with the method's input enforced, `form` on method
rows, `fixed` and `declares` in the artifact. Item 8b needed nothing in the kernel. Remaining:

7. `textWords(s) -> List<String>`, only if an object asks (§14: a new term form allocating a
   native list cell, the `textJoin`-scale change across core, machine, Fast, collector and both
   codecs).
9. Located refusals from the generics pass: the derived-edits, fixed, form-kind and
   derived-forms refusals are strings (stage `source-specialization`, no span); a
   `Generics` error type with a span (the State's, the write's, the form block's) would place them.
10. `Form.obend` `type Forms = Lists.List<Form>` (objects lane) would let the derived `forms()`
   be `F.Forms` and drop its List.obend requirement (Counter, Loop).
11. The host reads `declares` (TurnLoop `declaredForms`, Ops `packageDeclares`) and `fixed`
   (actions, inspect, the Workshop's `set`): host lane.

## 17. World calls (WHOLENESS §1, lane/kernel6)

Day 4 (§21) deleted every sum-Plan half described below: what stands is the message dialect.

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
  `Checkpoint` field changed. The site table is built once per held entry
  (`CheckedEntry.make`, field `sites`, `Entry.lean`), so the host's per-method
  `Compiled.entry` and the package session's held entries carry it; only the packet path
  (`startActivity`/`resumeActivity`) walks per call. Measured on hbox, interleaved, a
  three-segment message turn on a held entry reaching N helpers: N=300 (251 KB packet)
  5.0 -> 3.9 ms, N=1000 (791 KB) 16.7 -> 13.7 ms.
  Artifact (message activities only): `dialect: "message"`, `world` (methods the entry's
  sites name, first occurrence), `worldProtocol` (the World module's source SHA-256 hex).
  Tests: `tests/test_world_calls.py` `SiteTypes`.

## 18. Turn performance (docs/PERF.md items, lane/kernel6)

- In-process yields carry the state. `concludeStep` returns a `Step` whose yield holds a
  `Suspension {pin, binding, dictionary, site, state}`: the state as the machine left it,
  neither collected nor encoded. `Suspension.checkpoint` makes the `Checkpoint`
  (`encodeStateV3` of `checkpoint state`, site prefix, digest) only when asked.
  `resumeSuspended entry suspension binding value budgets` resumes it with the same
  refusals as `resumeEntry` (activity shape, package, binding) and no encode, digest or
  decode. Invariant, from theorems that exist: resuming `checkpoint state` (what
  `resumeEntry` decodes, `stateV3_roundTrip`) decides the same verdict, spends the same ticks
  and extracts the same Plan or result as resuming `state`, each under `limitsPast` of its own
  heap (`checkpoint_resume_segment`). Runners: `startEntryStep`, `resumeEntryStep`,
  `resumeSuspended` (Step), with `startEntry`/`resumeEntry` their `Step.outcome`. The host's
  `drive` switches by taking a `Step`, passing `suspension.checkpoint` only to the `await*`
  and `interpret` paths, and resuming every other Plan with `resumeSuspended` (the host
  lane's change). Measured with that change applied on hbox (`compile-profile replay` of
  the rehearsal stream, directory `receive`, 120 turns, `taskset -c 0-15`, load ~16): 5,102
  to 5,505 ms before, 2,123 to 2,474 ms after (2.2 to 2.6x); the whole replay's user
  instructions 322 G to 160 G; ticks identical (12,489,187).
- The checkpoint digest without `Json`. `checkpointPreimage` writes the canonical CBOR of
  `{packetSha256, object, principal, intent, rootsDigest, tokens}` straight from the tokens
  (`writeToken`: v1 one-key maps, else naturals, texts and negative string references), the
  bytes `encodeJson` wrote for the `tokensJson` map; `checkpointDigestJson` keeps the old
  definition and a `#guard` compares them over v1, v3 and site-prefixed tokens, a natural
  past 2^64, every CBOR head width and non-ASCII text. Not a theorem: `writeJson` is
  `partial`. Measured as above with the host unchanged: whole replay 322 G to 286 G user
  instructions; directory `receive` 5.9-6.3 s to 4.9-5.1 s.

## 19. Checkpoint trimming (lane/kernel7, §16 item 1)

- Why ~2,000 cells were live at a directory `interpret` yield: closures keep whole lexical
  environments, so every `let` of `receive` stayed live through every thunk built under it.
  Measured on the run 10 rehearsal journal with an offline decoder of journaled v3 tokens and
  the entry's free variables (`compile-profile REQUEST dictionary ENTRY` prints, per subterm in
  `Dictionary.ofProgram` preorder, its constructor and free de Bruijn indices): tracing only
  free slots leaves ~860 of ~1,900 cells. The rest of the scatter (env-table indices,
  local-string indices, long relative edges into later rounds) was mostly edges into that dead
  half. Simulated alternatives that did not pay: pure DFS numbering (worse), roots reversed
  (±2%), the arguments-as-prefix change kernel6 tried. Inline local strings would cut the
  blocks a further 6% median, 26% total; not done.
- `checkpoint s = collect (trim (collect (settle s)))`. `trim` points every environment slot
  a cell's closures do not read (`Term.freeIn`; a closure value `λ.body` reads `i` when `body`
  reads `i + 1`) at the cell itself; the first collect bounds trimming's work by the live
  cells. Compiled through `trimCellFast` (one `Term.markFree` traversal per closure,
  `@[csimp] trimCell_eq_fast`); without it the rehearsal took 55 s instead of 30 s, since
  the host still checkpoints every in-process yield (the host lane's `drive` change in §16).
- Proof: the settle relation is extended rather than a new one. `eraseState` now also
  replaces unread slots by 0 in cells, control and frames; `erase_stepRaw` (every transition
  copies an environment only into a closure over a subterm or a body under one more binder;
  `freeIn_rename` covers the renamed bodies of `fix` and `mix`), `agree_forceHostedFrom`,
  `agree_materializeWith` (values equal up to erasure), `agree_completeWith`,
  `agree_yieldedPlanWith`, `agree_trim`, and `agree_resume_segment` with `settle_` and
  `trim_resume_segment` as instances. `checkpoint_resume_segment` composes four stages,
  statement unchanged. The collector, codecs, machine and Fast proofs are untouched.
- Measured (hbox, `rehearsal/rehearse.py`, same fixtures): journal 4,719,653 -> 2,813,175
  bytes; suspensions 2,706,683 -> 800,205; median suspension 46,390 -> 10,077 bytes; new
  blocks per suspension median 74 -> 6; wall 31.8 s -> 30.2 s. Of a median suspension now,
  5.7 KB is blocks and 4.4 KB the host's fields (`activity.argument` 1.2 KB,
  `interpretation.utterance` 1.0 KB, inline per entry): run 8's 9.5 KB median is within reach
  only by moving those into blocks, which is the host's file. Packets do not move (pins: 0).

## 20. Checker cost (lane/kernel8, §16 item 2)

- `inferAt`/`inferFieldsAt`/`inferArmsAt` are the checker over any annotation cursor
  (`here : α → Option LambdaAnnotation`, `child : α → Nat → α`); `infer`/`inferFields`/`inferArms`
  are it at source positions (`child p i = p ++ [i]`, annotations a function of the whole path)
  and stay the reference, so `check`, the decided examples and the packet path are unchanged.
  `inferAt_view`: two cursors related by a map preserving `here` and `child` infer alike.
  `AnnotationTree` moved from `Entry.lean` into `ObjectiveBendTyping` (`here`, `child` with the
  empty tree past the children, `subtree`, `lookup := (subtree path).here`); `checkAt term tree`
  is `check` over the tree, `checkAt_eq : checkAt term tree a c f = check ⟨term, tree.lookup, a⟩ c f`.
  `CheckedEntry.apply` (every turn argument) calls `checkAt`.
- Type equality as compiled is by shared subtrees: `Ty.eqSharedCore` (structural, `withPtrEq` at
  every child, its property `r = true ↔ a = b`) behind `@[csimp]` on both `instDecidableEqTy` and
  `instDecidableEqTy.decEq` (`ObjectiveBendTypes.lean`), so every `=`/`==` on `Ty` compiled after
  it stops at one object in memory. `agree` compiles to `agreeFast` (`@[csimp]
  agree_eq_agreeFast`): equal trees agree at once, and only differing ones pay for canonical forms
  and both shareability walks. At `Data` an injection's payload type is the rest of the list's
  shape, so each of these was linear per node.
- Measured on hbox (turn-start on a held entry, best of three, load 16-33, so noisy):
  5,000-item list at `Data` 2,320 -> 26 ms; 5,000-item `List<String>`-shaped sum 705 -> 9 ms;
  1,000 three-column rows 48 -> 7 ms. Packets do not move (pins: 0).

## 21. Day 4: the message dialect alone (lane/kernel8, §16 item 6)

- Refused by name: `Activity<Plan, Response, Result>` ("refused (old-dialect): ... is withdrawn",
  at the declaration in `emitDecl` and in `sourceType`), surface `perform(...)` ("refused
  (perform): surface perform is withdrawn", `isSurfacePerform`). `isPerform` is a world call
  only. `write {…}` parses straight to `world.write(extend(keep(), {…}))`: `writeMarker`,
  `writeLowered` and the `object`/`context` requirement are gone.
- Deleted: the typed-view rewrite (`typedViews`, `viewAs`, `viewed:M.S` arms; `world.view::<S>` is
  the facility); the generics pass's `perform` handling and `Site.result`; the dead
  JSON-argument path (`legacyArgument`, `typedArgument`, `exactKeys`, the
  `argument-values.v1` envelope, `argumentCodec`, selection `mode`, projections,
  `Lowering.core`): `Elaborated.select e module entry`, `lower* … limits`, `options limits`.
- Types: `Ty.isPlanUnder` is a record of data only; `Ty.performResponse` is gone and
  `PartialTyping.perform` concludes `computation plan .data T`. The decided activity examples
  are restated over a message Plan (`doneSignature` for `done`), `sum_plan_refused` added,
  `message_then_sum_plan_refused`/`sum_plan_response_unchanged` deleted.
- Checkpoints: v1 `encodeState`/`decodeState`/`encodeCell`/`decodeCell`/`roundTrips`/
  `checkpointEdition`/`tokenJson` and `state_roundTrip`/`cell_roundTrip`; v2
  `encodeStateV2`/`decodeStateV2`/`checkpointEditionV2` and `stateV2_roundTrip` deleted;
  `decodeCheckpoint` (v3) replaces `decodeStateAny`. The v1 module stays as the token codec v3
  builds on. `Turn`: tokens JSON is bare only, `writeToken` has no v1 form, a checkpoint with
  no site prefix does not resume.
- Host (this one item, at the coordinator's request): `messagePlan` returns `Except`
  (anything not a message is `noMethod`), the sum-Plan pass-through in `drive`, the
  `viewData`/`viewDataField` arm, `isMessageDialect` and the sum-Plan branch of
  `interpretVerdict` deleted; `speaksMessages` is "its `receive` compiles".
- Tests: `tests/fixtures/obend/Variant.obend` and `tests/test_typed_view.py` deleted; 34 test
  files moved to the message dialect (two helpers, reviewed). `def test_` count 1,058 at
  foundation 17b1767 -> 1,052: deleted as old-dialect-only: writing another object
  (`notSelf`, three tests: `world.write` names no object), a non-Plan sum as the Plan, the
  `denied` interpretation (World's `Interpreted` had no `denied` then; it has one again, the host
  answers it, and Garden and the Directory refuse it as policy), the two typed-view tests; added: the two refusals above.
  `test_tariff` bump: 56 + 10 -> 73 + 10 ticks (a `Message` record and a `Data` injection
  where a sum injection was).
- Pins re-recorded once (`tests/fixtures/pins/artifacts.json`): every world source had moved
  with the objects lane's deletion pass; 44 modules, 1,207 -> 1,132 defs (Card, Deal,
  Directory and Spell lost defs in that pass), every def compiles.


## 22. Relations in the artifact (lane/kernel8, §16 items 3-5)

- `relationsOf` once per package: `PreparedRequest.relations` is a `Thunk` that
  `prepareRequest` sets (`prepareCore` is the closure without it), so the package session's
  front cache and the host's prepared-closure cache evaluate `relations()` at most once per
  package and every later entry's artifact reads it. Measured on hbox (load ~12, interleaved,
  best of 8 rounds of every Cistern entry in one session): 126-130 ms -> 101-102 ms for 13
  entries.
- The artifact's `relations` entries are `{field, key, limit, retain?}`: `limit` the Decl's
  Nat (0, the host's default, when the Decl has none), `retain` the Decl's retention as text
  (a String field or a case label) only when it declares one; a non-Nat limit is refused
  "relations(): a limit is a Nat". The host reads them from the artifact (`declsOfArtifact`, Ops.lean; host11). Test:
  `test_sugar.Relations`.
- `write {f: remove v}` is `removeItem {item: v}`, or `retract {key: v}` when the module's
  `State` types `f` as a `Relation<…>` (the parser emits the marker `$remove` and
  `parseObjective` lowers it once the declarations are read, `lowerRemove` over
  `Decl.mapExpr`); `write {f: amend v with c}` is `amendItem {item: v, change: c}`. An index
  (`remove {index: …}`, `amend {index: …} with …`) is refused by name ("names a position, and
  edits name items: write `f: remove ITEM` …"). Tests: `test_sugar.Writes`.


## 23. The State is the schema (lane/kernel9, §16 item 8)

- 8a, derivation. `Generics.deriveEdits` (a probe pass over the package whose state is dropped)
  resolves each State field's type with `typeOf` and writes, for a module declaring `State` (a
  record, or `type State = M.S` naming one) that imports Plan.obend and declares neither `Edits`
  nor `keep`, the source of §16's pair, parsed by `parseObjective` at the State's span. A list or
  relation is recognised by its instance (`entriesItem`: a one-parameter sum named `List` with
  cases `nil`, `cons`, or `Relation` with the one case `rows`); a type the module did not write
  is spelled through its own imports (`spell`), refused by name when a module it needs is not
  imported ("refused (derived-edits): State.f holds items of a type from a module M does not
  import"). The pair ends its module and is specialized after every module's own declarations,
  so it numbers no instance before one the package spells: no packet of any other entry moves
  (pins: 0 recompiled, including Places and Seats, which gain an unused pair). A module with a
  State, no Plan import and a `keep()` call (every `write {…}`) is refused by the parser
  ("refused (derived-edits): write {...} and keep() derive Edits from State through the Plan
  library"). Since commit 3 a declared `record Edits` or nullary `keep() -> Edits` beside a State
  is refused by the parser ("refused (derived-edits): Edits is derived from State; delete this
  declaration", at the declaration); any other `keep` (a method) only stops the derivation.
  Tests: `test_sugar.DerivedEdits` (derived = the same module with State renamed, so nothing is
  derived, and the pair written at its end, for a write, `keep` and `initial`; `keep()` runs
  to a keep per field in State order; `type State = Lib.State`; the two refusals).
- With every hand-written `record Edits` and `def keep() -> Edits` deleted from world/objects (a
  scratch copy), every module checks except: Appointment (its `keep` is a method, so nothing is
  derived and `Edits` is unknown; Appointments imports it), Bell/Garden (`doorWritten` and
  Card's `DoorEdit` type `Entries<Doorway, {}>`, now `Entries<Doorway, Doorway>`), Policy
  (`asked` returns `Entries<String, {}>`), Wake (`world.write::<Edits>({…})` names two fields
  of a record that now has all of them). Those are the review lane's edits.
- 8c, form blocks. The parser keeps each block as `Surface.FormBlock {action, value, fields:
  [{name, kind: FormKind}]}` in `Module.forms` beside the Form value it writes in place
  (unchanged); a new kind `T` (an identifier or `Alias.T`) stands in the value as the marker
  `$formChoice(F, T)`. `Generics.deriveForms`, in the same probe as the Edits: resolves `T` to
  the labels of a closed sum of empty cases ("refused (form-kind): form water offers shade:
  Mixed, which is not a closed sum of empty cases"), replaces the marker by the choice, and
  derives, at the end of the module, `record NameInput` (`type NameInput = {}` for a block
  without fields; text and source String, natural Nat, `a | b | c` the generated `sum
  NameField` of empty cases, `T` itself) and, when the module declares no `forms`,
  `def forms() -> L.List<F.Form>` of the values in source order (needs an import of List.obend,
  else "refused (derived-forms)"). A declaration named like a generated one is "refused
  (form-input): form plant declares PlantInput, its method's input, and so does the module".
  `Elaborate.Module.forms` carries the resolved blocks; a method row with a block gains `form:
  [{name, kind}]`, kind the `Form.Kind` value on the Data wire (`source` is `{"tag":"variant",
  "label":"source","payload":{"tag":"record","fields":[]}}`). Pins: 0 recompiled (every world
  object hand-writes `forms()`, and the input types number no instance). A derived `forms()`
  that instantiates `List<F.Form>` for the first time adds a bound to every packet of the
  package (bounds are package-wide), so a module that drops its `forms()` moves its packets
  only if nothing else names that list. Tests: `test_sugar.FormInputs`; `test_sugar.Forms`'s
  explicit spellings now include the `forms()` the block derives.
- Enforced since commit 3 (`checkFormInputs`, after `checkProtocols`): "refused (form-input):
  plant has a form block, so its input is PlantInput", with `expected`/`found`, by `sameTy` of the
  method's input parameter (between State and context) and `NameInput`; a block without fields
  admits no input or `{}`. Structurally Garden's `Planting` equals `PlantInput` (`amber | violet
  | silver` is `Bell.Colour`). Counter and Loop import no List.obend, so they keep a hand-written
  `forms()` until they import it.
- `fixed` State fields (coordinator's addition before commit 3). `colour: fixed Colour` in
  `record State` (`Surface.Field.fixed`; anywhere else "refused (fixed): only a State field is
  fixed") is a field the derived `Edits`/`keep()` omit, set only by `initial()` or a seed.
  `Generics.checkFixed` (in the probe, also through `type State = M.S`) refuses a hand-written
  `Edits` field or any `world.write(...)` argument (a record, or `extend(keep(), {...})`, so every
  `write {...}`) naming one: "refused (fixed): colour is fixed; no edit names it". The artifact of
  an entry whose State has fixed fields lists them, `fixed: [names]` in State order (absent
  otherwise; `Package.fixedFields`), for the host's actions, inspect and the Workshop's `set`.
  Pins: 0 recompiled. Tests: `test_sugar.FixedFields` (the packet equals the State-renamed module
  whose hand-written pair omits the fixed fields; the refusals).
- Commit 3 moved 36 test files' fixtures off hand-written pairs (deleted; `test_relation`'s own
  `RowEdit` sum became `Plans.Entries<Rain, Rain>`, `test_protocols`' line moved 19 -> 15,
  `test_sugar`'s explicit spellings `Entries<X, {}>` -> `Entries<X, X>`). Pins: 0 recompiled.
- `declares` (for the host, which scanned the entry source for `def forms(` and so never saw a
  derived `forms()`): every artifact lists which of `Package.conventionalNames` (forms, methods,
  relations, views, lenses, law, lawReads, initial, render, receive, blurb, page, publishPage,
  set) the entry module declares, derived declarations included (`declaredNames` over the
  generics pass's decoded modules), in that order. The host lane switches `declaredForms` and
  `packageDeclares` to it. Test: `test_sugar.Declares`.
