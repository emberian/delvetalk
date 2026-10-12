# Kernel handoff

State on 2026-10-11 (lane/kernel17 after foundation 57d1c580: one clause language, `law`, `rule` and `want` on a thing's text, OVERHAUL §5 step 2, §27; before it lane/kernel16 after foundation 1de640d7: a computed refusal, `refuse(line)`, §26; before it lane/kernel15 after foundation 8f69bd7e: the relation primitives `relationCount` and `relationLookup`, §15 "Two primitives", §16 item 15; before it lane/kernel14 after foundation 3c96c27d: the law grammar as one term language with LAW §4 B, C, D, F/G, §25 item M; the fungus deletions K1, K2 (item N), K3, K6; before it lane/kernel13: honest bounds, located generics refusals, LAW §4 A/E/H; the queue is §16).

## Summary

The kernel is the Objective Bend edition: source text to a checked typed packet, a demand machine with a tick tariff, a checkpoint codec, and the wire and canonical forms. The host (HOST-HANDOFF) calls it through `Turn.lean` and `Package.lean`; JSON exists only at the process boundary.

- Language: `spec/bend/Compiler/` (Surface, Parse, Elaborate, FrontEnd, Blame, Law, TermWire, DataWire, Sha256) and `spec/bend/Theory/` (OpenRecursion, Types, Typing, DemandMachine, DemandMachineFast, DemandData, Checkpoint, CheckpointV3, DemandCollect and the proofs). Delvetalk side: `spec/Delvetalk/` `FrontEnd`, `Generics`, `DocumentTemplate`, `Hints`, `Package`, `PackageSession`, `Turn`, `Entry`, `Limits`, `Canonical`, `Document`, `Profile`, `EvaluateTerm`, `PackageData*`; driver `spec/PackageMain.lean`.
- Binary: `.lake/build/bin/delvetalk-obend` (`lake build`; `make build` also builds the proof-only modules in `PROOF_ONLY`). No `sorry` in `spec/`.
- One dialect (§21): an activity is `Activity<A>` = `computation Message Data A`; its only yields are world calls `world.X(arg)` / `world.X::<T>(arg)` against `world/lib/World.obend`'s `protocol world` (§17), each resumed at its site's type. Surface `perform` and `Activity<P, R, A>` are refused by name.
- The State is the schema (§23): `Edits`/`keep()` derived from `record State` (a `fixed` field has no edit); a `form` block declares its method's input record `NameInput` and, absent a hand-written one, `forms()`; a hand-written one beside blocks is not yet refused (§9).
- Relations (§14, §22, §15): law atoms `insertOnly`, `count`, column membership; `insert`/`upsert`/`retract` in `write {...}`; `canonicalCompare`; `relationCount(r)` and `relationLookup(r, key)` (core forms: a stored relation answers a count from its handle and a lookup by its declared key by binary search); the artifact's `relations: [{field, key, limit, retain?}]`, evaluated once per package.
- Wire: Data JSON `{"tag":"natural","value":"123"}`, lists as `{"tag":"list","items":[…]}`; canonical form is DAG-CBOR, CID = `b` + base32lower(`01 71 12 20` + sha256).
- Checkpoints: edition v3 only (`decodeCheckpoint`); v1 and v2 no longer decode (day 4, §21).
- Pins: a world object's pin is the CID of its source closure (host), not `packetSha256`. `tests/test_artifact_pins.py` guards that world sources keep compiling.
- Tests: 1,241 `def test_` across 109 files (foundation b0f3618). Kernel-narrow: `test_turn`, `test_canonical`, `test_conformance`, `test_document`, `test_data_type`, `test_tariff`, `test_sugar`, `test_located`, `test_hints`, `test_layers`, `test_artifact_pins`.
- Open: section 9; queue §16.

## 0. Working rules

- Build: `LEAN_NUM_THREADS=2 lake build` (one Lean process). Never rebuild while a run uses the binary: `tests/host.py` copies it per run (`DELVETALK_OBEND` names the source, `DELVETALK_OBEND_COPY` shares one copy across workers; `tests/run.py` is the parallel runner). Builds may run on hbox with `swarm-build lake build`.
- Run: `DELVETALK_OBEND=$PWD/.lake/build/bin/delvetalk-obend python3 -W ignore -m tests.run [module …]`; whole suite `make check`.
- Proof-only modules (`Delvetalk.PackageDataAdmission`, `PackageDataNormalization`, `PackageDataSchemaProofs`, `Theory.ObjectiveBendNativeDataSimulation`) are outside the default target; `make build` builds them. Build them after touching anything they import.
- Lean 4.34: `if_pos`/`if_true` deprecation warnings in old Mini files are noise. A doc comment (`/-- -/`) directly before `mutual` is a parse error; use `/- -/`. In a file that opens `ObjectiveBendTypes`, a pattern variable `label` reads as `Ty.label`. Likewise inside `def LawTerm.x`/`LawName.x` a pattern variable `field` reads as the constructor `field`: name it otherwise. `x.isDataUnder a b c d` puts `x` at the first `Ty`-typed parameter.
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
| Checkpoint | `Theory/ObjectiveBendCheckpoint.lean` (the token codec), `…CheckpointV3.lean` (the written edition), `…DemandCollect.lean` | See section 7. |
| Clauses | `Compiler/ObjectiveBendLaw.lean`, `Delvetalk/Host/Law.lean` | `law`, `rule` and `want` lines over declared state, one grammar (§27); the pure profile refuses laws ("host law adapter"). |
| Typed data/schema | `Delvetalk/PackageData*.lean` | `run-data-v1`, compact codec, schema certificates. Depth is `Bounds.dataWireDepth`. |
| Package, session | `Delvetalk/Package.lean`, `PackageSession.lean`, `spec/PackageMain.lean` | JSON-lines driver; section 2. |
| Line check | `Delvetalk/JsonLine.lean` | a driver line's `\uXXXX` escapes are Unicode scalar values. |

Proof obligations by change:
- `Term`/`Primitive`/`Step`: the `Step` lemmas in OpenRecursion (`lazy_fixed_function`, `case_selects_injected_arm`, primitive exactness) and `Value` ones; Typing's `PartialTyping` mirrors every constructor; checkpoint codec needs a case (`state_roundTrip` fails the build otherwise).
- Typing rule: `checked_erasure`, `agree_sameType`, `partial_beta_law`, `reusable_lambda_capture_rule`, `sameType_isComputation`, the decided examples.
- Machine: `resume_requires_yield`, `resume_keeps_heap_and_stack`, `perform_under_update_refused`, `perform_yields`, and the `Fast` equivalence (`stepRawFast_eq_stepRaw`, `runFrom_eq_runBounded`): a change to `stepRaw` needs the matching `stepRawFast`/`sizesAfter` change.
- Collector: a new frame, cell or control holding addresses must be added to `frameAddresses`/`cellAddresses`/`controlAddresses` and the renamings, or `related_stepRaw` stops building.
- Schema/compact codec: `PackageDataSchemaProofs.lean`. Native cells: `ObjectiveBendNativeDataSimulation.lean`, `ObjectiveBendFiniteDataTyping.lean`.

Proved:
- `plainV3_roundTrip` and `stateV3_roundTrip` for every dictionary and state (the v1 and v2 state codecs and their round trips are deleted, §21); the token codec round trips of terms, values, data, frames and controls (`ObjectiveBendCheckpointRoundTrip`); `refusal_roundTrip`; `encodeTerm_injective`.
- `settle_resume_segment` and the agreement lemmas on the hosted runner (`agree_forceHostedFrom`, `agree_materializeWith`, `agree_yieldedPlanWith`, `agree_completeWith`). `typed_settle` is not ported (no state-typing judgment).
- Collector (`DemandCollectProofs`): `related_collect`, `related_stepRaw`, `related_forceHostedFrom` (exact under `ExactRoom`, which `limitsPast` gives), `checkpoint_resume_segment`: resuming `checkpoint s = collect (settle s)` decides the same verdict, spends the same ticks and extracts the same Plan/result Data as resuming `s`.
- `conformsUnder_iff : d.conformsUnder bounds ty = true ↔ HasType bounds d ty` (`ObjectiveBendDataConformance.lean`); fuel is never a false negative.
- `sameTypeShared_eq`, `lawTable_names`, `Data.shapeType`/`shape_typing`/`universal_typing`, `SchemaMatches.data`, `Admitted.universal`.

Not proved: that `noActivity` is the static guard matching `perform_under_update_refused`; that `textJoinExpansion` and the machine's join frames agree (conformance tests values only); that an activity typed by the `refuse` rule refuses only through `refuse`; the canonical-CBOR round trip.

## 2. Ops

Wire: one JSON object per line on stdin, one per line out. Errors: `{"status":"error","message":s}`. `PackageSession.step` keeps two per-process caches: prepared closures (bounded by `Bounds.frontCacheSourceBytes`, 8 MiB of source) and held entries indexed by `packetSha256` (bounded by `Bounds.entryCacheBytes`, 64 MiB of artifact). `run`, `run-data-v1`, `turn-start`, `turn-resume` take `artifact` as the whole artifact (held if equal to the one this process compiled under that pin, else recompiled and compared) or `{"packetSha256": pin}` alone (held entries only; "unknown packetSha256: …" otherwise). `world-*` ops go to `Host.stepWorld`. `library-load {path}` and `library: <pin>` are in HOST-HANDOFF.

| op | takes | returns |
|---|---|---|
| `compile` | `modules:[{name,source}]` or `source`, `entry`, `limits?`, `library?` | `{status:"compiled", artifact}`; artifact = `{schema, modules, sourcesSha256 (CID), entry, genericInstances, limits, packet, packetSha256 (CID), type, methods, law, laws?}`. Compiler refusals: error message is the diagnostic JSON text. |
| `check-package` | as compile | `{status:"checked", artifact}` or `{status:"refused", diagnostic}`. `Package.checkPackage` is the pure entry. Spanless refusals are localized by `localize` (recompiles each function alone; first with the same stage+message wins). |
| `run` | `artifact`, `arguments`, `limits` | `{status:"finished", value, type, ticksUsed, heapCells, nodesUsed}` or `{status:"refused", failure, …}`. Entry type must be first-order data ("package result must have first-order data type"). |
| `turn-start` | `artifact`, `arguments`, `limits?`, `object`, `principal`, `intent`, `roots` (all required) | `finished`, `yielded {plan, planType, responseType, checkpoint, ticksUsed}`, `exhausted {resource, ticksUsed}` (resource: ticks heap stack nodes bytes), or `error`. The entry must type as `Activity<A>` (plan `World.Message`, a record of data; response `Data`; each yield resumes at its site's type, §17). |
| `turn-resume` | `artifact`, `checkpoint`, `response`, `limits?`, same binding | same replies. Resumes only a checkpoint this process issued (its session keeps the digests it handed out, `Bounds.issuedCheckpoints` 65,536, oldest leaving; else "checkpoint was not issued by this process": a fresh process, or a digest recomputed over edited tokens). Then in order: entry is an activity; `packetSha256`; the tokens hash to the issued digest; object; principal; intent; roots ("checkpoint belongs to another package / digest mismatch / another object / another principal / another intent / was taken under different roots"); decode ("checkpoint does not decode"); response conforms; control is yielded. The response type is re-derived from the artifact. |
| `evaluate-term` | `term` (array wire), `responses?`, `ticks?` | `{schema, result:{status: value\|yield\|exhausted\|stuck, shape, plans}}`. Pure reference for conformance. |
| `render-document` | `document` (Data wire) | `{status:"rendered", text, lines, bytes}`. |
| `canonical-encode` / `canonical-decode` | `data` or `json`, `repeat?` / `hex` | `{cid, hex, bytes, checksum}` / `{data, cid}`; decode is canonical-only. |
| `source-imports-v1` | modules | import edges. |
| `run-data-v1`, `encode-compact`, `decode-compact` | typed-schema family | see `PackageData.lean` headers. |

`"profile": true` on `run`, `turn-start`, `turn-resume` returns a tick profile (`Delvetalk/Profile.lean`).

Turn API in Lean (`spec/Delvetalk/Turn.lean`): `startActivity packet args binding budgets : Except String Outcome`, held-entry forms `Turn.startEntry`/`resumeEntry entry checkpoint issued binding response budgets`. A checkpoint resumes only against `issued`, the digest its caller recorded when it was made (the host's journal; a session's issued table): the digest field beside the tokens is never trusted (review kernel 3, kernel10); the other resumption is `resumeSuspended`, a yield held in process. The packet-path `resumeActivity` is deleted. `Outcome = finished | yielded | exhausted resource ticks`. `Binding.make object principal intent roots`. A checkpoint carries its binding and resumes only under the same one; the roots digest is the roots at the start of the activity. `exhaustedResource` classifies failures: ticks; capacity suspension -> heap/stack by simulating one more `stepRaw`, else bytes; `nodes`/`bytes` on a yielded Plan is exact, on a finished result a heuristic that can mislabel. `Budgets {ticks, heap, stack, nodes, bytes}`; on resume, heap is counted past the checkpoint's own heap (`limitsPast`).

Held entries (`Delvetalk/Entry.lean`): `CheckedEntry {pin, source, checked, fuel}` (`.type`, `.ofPacket`, `.apply`). `Package.prepareRequest j`, `Package.compileEntryFrom request entry` (`{artifact, entry, laws}`), `Package.compileEntry`, `Package.executeDataEntry entry args limits`, `Package.executeEntry`. None decodes the packet or re-checks the package.

Annotations: injecting a variant argument or response needs per-injection annotations (an `AnnotationTree` shaped like the literal, built by `Turn.quoteAt`/`shapeTree`); the checker rejects an unannotated `inject`. A turn argument is checked at `Delvetalk.argumentFuel` = the entry's fuel plus twice the literal's `Term.nodes`. Every data-typed argument is checked with `conformsUnder` first: "turn refused: argument does not conform to its type" (the host maps it to `typeMismatch`).

Artifact extras: `methods` (`Package.methodTable`; `stackMethodTable` for a layer stack: every layer's methods, top first), `law` shape, `laws: [{name, reading}]` (`Package.lawTable`, one per enforced law, source order, key absent without laws), `Limits.lawTicks`.

## 3. Wire and canonical form

Data JSON (`Compiler/ObjectiveBendDataWire.lean`): `natural` (decimal string), `boolean`, `label`, `record {fields:[{name,value}]}`, `variant {label,payload}`, `list {items}`. `dataJson` emits `list` whenever `listItems?` finds a proper `nil`/`cons` chain. `decodeData` refuses a variant chain that forms a proper list ("cons chains are no longer accepted on the wire; send a list", `consChainRefusal`); `PackageData.decode` applies the same rule. Decode depth is nesting, not elements (`Bounds.dataWireDepth` 256; chains cost 2 levels per cell, arrays do not). A decoded list is a `cons` chain in memory. `dataJsonBytes` must equal `(dataJson d).compress.utf8ByteSize` (keep in sync by hand).

Canonical bytes (`Delvetalk/Canonical.lean`, DAG-CBOR as AT Protocol):
- Unsigned int, shortest head; Nat >= 2^64 a big-endian byte string; false/true = f4/f5; label = text; JSON null = f6; list = definite array; record = definite map with keys sorted by UTF-8 byte length then bytes (a repeated field keeps the first); variant = one-key map `{label: payload}`.
- Untyped decode turns every one-key map into a record; `decodeAs bounds ty bytes` re-tags against a type. Round trip is `decode (encode d) = normalize d` for variant-free `d`, and `encode (decode b) = b` for everything; not exposed on the wire; not proved. Never `decodeAs` against `.data` expecting variants back.
- `decode` refuses non-shortest heads, unsorted/duplicate keys, indefinite lengths, tags, floats, null, negative ints, non-canonical bignums, bad UTF-8, trailing bytes, by name ("non-canonical CBOR: …", "CBOR nesting capacity", "CBOR exceeds the node bound").
- `encodeJson`: objects->maps, arrays, strings, bools, null, ints; a fraction is refused, and so is a negative integer below -2^64 ("a negative integer below -2^64 has no canonical form": DAG-CBOR has no negative bignum, and the eight-byte head kept only the low 64 bits, so -2^64-1 and -2^65-1 shared `3b0000000000000000`; kernel10). `cidJson` is total (falls back to the CID of the printed text on an unencodable value).
- CID = `"b" ++ base32lower(0x01 0x71 0x12 0x20 ++ sha256(bytes))`, 59 chars, `bafyrei…`. All 166 `record`/`cid` pairs in `tests/fixtures/delve/*.json` encode to the AppView's CID; `tests/wire.py` is an independent Python encoder.

Digests:
- Journal: `Host/Journal.lean` `bodyHash = cidJson`; `verify` names "journal broken at height N: hash mismatch | height out of sequence | previous hash does not chain". Request digests, retry identities, seed digests and delivery ids are CIDs too.
- Artifact: `packetSha256` and `sourcesSha256` are CIDs (the names kept). Per-module source hash inside the packet is hex SHA-256 of the raw source.
- Checkpoint: `Turn.checkpointDigest` = CID of `{packetSha256, object, principal, intent, rootsDigest, tokens}`; `rootsDigest` = CID of `[{object,version}]`; `tokensDigest` = CID of the token JSON. Verified in `resumeActivity` before decoding.

## 4. Limits (`spec/Delvetalk/Limits.lean`, namespace `Delvetalk.Bounds`)

Per machine segment (default / ceiling): `ticks` 100,000 / 1,000,000; `heap` 100,000 / 1,000,000 (cells); `stack` 10,000 / 100,000 (frames); `nodes` 100,000 / 1,000,000 (Data nodes materialized for a result or Plan); `bytes` 1 MiB / 16 MiB (the canonical DAG-CBOR size of a result or Plan, `Data.canonicalBytes`, `#guard`ed against `Canonical.encode` in Canonical.lean; and the largest single text-primitive reserve per step). Materialization spends each scalar's canonical bytes as it is reached and checks the whole value's size once it is whole (a list's cells cost nothing but its array head); before kernel10 it charged a legacy decimal-length encoding, so `true` needed 2 bytes (`test_tariff.CanonicalBytes`). `lawTicks` 100,000. `typeFuelDefault` 16384.

Wire: `dataWireDepth` 256, `plainJsonDepth` 64, `documentWireDepth` 8192, `entryArrowDepth` 64, `maxFrameBytes` 16 MiB (a driver request line). Packages: `maxModules` 64, `maxModuleBytes` 512 KiB, `maxPackageSourceBytes` 1 MiB (import scan only), `maxPackageBytes` 128 KiB (one module offered as a program: reprogram, extend, create of source, a `check` Plan, a form's `source`; the host's `maxPackageBytes`/`formSourceMax` read it, §25), `frontCacheSourceBytes` 8 MiB, `entryCacheBytes` 64 MiB. Each refusal names its bound and number ("module M exceeds maxModuleBytes (524288 bytes)"). Documents: `documentDepth` 64, `documentNodes` 65,536, `documentOutputBytes` 1 MiB, `offersPerTurn` 16 (their text shares the 1 MiB). `Document.maxOffersPerTurn`/`maxOutputBytes` are aliases that `TurnLoop.lean` reads.

Outside `Limits.lean`: `PackageMain` 16 MiB line frame; `EvaluateTerm` nesting 4096, default 200,000 ticks, `go 64` yields cap; `Canonical` reuses `nodesMax`/`bytesMax`; the host's own `Host.Limits` (`dataDepth` 8192, `plainDepth` 64, `maxTurnTicks` 1,000,000, `maxPackageBytes` 32768 until the host reads `Bounds.maxPackageBytes` …). Fuel parameters that are not budgets: `Typing.check` fuel, `Ty.dataFuel`, `termNestingCapacity` 4096, `conformsFuel`, `peelArrows`. A fuel exhaustion is a refusal, never a wrong answer, but it looks like a type error.

## 5. Tariff

Every machine transition costs 1 tick. Before a text primitive runs, `forceHostedFrom` admits `(ticks, bytes)` from `textStepCost` and suspends (`ticks` or `capacity`) if either exceeds what is left; the state is retained exactly. B = byte size of the operand, p = exact bytes of the first n scalars (`prefixCost`, a scan bounded by what the allowance can pay).
- `textConcat a b`: `1 + 2(|a|+|b|)`, reserves `|a|+|b|`.
- `textTake t n`: 1 if n=0 or n>=B; else `1 + 2p`, reserves `p`.
- `textDrop t n`: 1 if n=0 or n>=B; else `1 + 2p`, reserves `B - p` (the suffix copy is bounded in bytes, not charged in ticks, so a drop-by-one walk stays linear).
- A take or drop whose prefix scan cannot be paid spends the whole allowance, as a failed span/break does (`preflightRemaining`; kernel10, `test_tariff.FailedPreflight`): the scan ran.
- `textJoin list sep` (each element): `1 + 2*(bytes appended)`, reserves the new accumulator (appended in place when unique).
- `textSpan/textBreak`: `1 + perScalar*visited`, perScalar = `2*(|alphabet|+2)`; refused up front if the cap cannot cover the scan.
- `textHasAny text words`: `1 + 3(|text|+|words|)`, reserves twice those bytes: a pass over each, then a hash set of the wanted words (`textHasAnyWordFast`, `@[csimp]` equal to the list-membership reference `textHasAnyWord`) probed once per word of the text. Before kernel10 the search was list membership, 30,000 words against 30,000 took 6.8 s under a 160,001-tick charge (`test_text_words.ManyWords`).
- `labelEqual a b` (text `==`): `1 + min(|a|,|b|)` (kernel10; it was one tick whatever the length, `test_tariff.LabelEqual`).
- `textLength`: `1+B`. `sha256Text`: `65 + 8*ceil(B/64) + 32*blocks`. `natText n`: `1 + bits^2`.
- Natural arithmetic (`naturalStepCost`, kernel10): 1 tick while both operands are below 2^64; past a word, with x, y the operands' bytes (`log2/8 + 1`), `1 + 2(x+y)` plus `(x/8+1)(y/8+1)` for multiply, divide and modulo, reserving the result's bound (`max+1`, `x`, `x+y`, `x`). Before it, forty squarings of 2 cost one tick each and built a 128 GiB natural; now they are refused at the first unaffordable operand (`test_tariff.NaturalArithmetic`).
- A fetched stored row or key (`fetchCost`): `1 + 2b`, reserving `b`, its canonical bytes.
- `relationCount` of a stored relation: one transition (the `relationRows` frame); of a walked one, about five a cons cell.
- `relationLookup` of a stored relation keyed by its columns: per probe, the key fetch (`1 + 2 * keyBytes`) and the probe's comparator (a `canonicalCompare`, linear in the key), at most `⌊log2 n⌋ + 1` probes; the found row's fetch only when it is read. Walked: the probe per row passed.
- Everything else: 1 tick.

`tests/test_tariff.py` pins the bump turn (73 + 10 ticks since day 4) and `Document.plain` over 1,025 leaves (129,272); library workloads are bounded where that code is tested (`test_hub`: glm's 1,788-character reply under a bell under 20,000 ticks, the directory's reading under 250,000). Update a pin with a reason when it moves. Profile before optimizing the interpreter: the Bend spell parse was 81% text primitives, and the host parses spells now.

Quadratic idioms to avoid: `Lists.append xs x` in a loop; `Lists.length` in a loop; left folds of `textConcat` (use `textJoin`); character walks with `textDrop` (copies the suffix each step, in bytes).

## 6. Evaluators and conformance

`impl/python/evaluator.py`, `impl/js/evaluator.mjs`, `impl/c/evaluator.c` are independent small-step, call-by-name interpreters of the core; each runs its stream with a deep stack (Python a 512 MiB thread, JS a worker with 256 MiB, C a json-c depth of 65,536) so a 2,048-row literal relation (about 8,000 deep) parses and walks. Input line `{"name","term","responses","fuel"}`; output `{"name","status": value|yield|exhausted|stuck,"term","plans"}`. Term array wire: `["bound",i] ["nat","12"] ["boolean",b] ["label",s] ["lam",b] ["app",f,a] ["mix",l,u] ["fix",s,i] ["specification",m,e] ["prototype",s,t] ["reflect"|"metadata"|"project"|"perform"|"done",x] ["unary",prim,x] ["binary",prim,l,r] ["get",x,name] ["inject",label,x] ["ifZero",v,z,s] ["ifBool",c,t,f] ["record",[[n,t]..]] ["extend",x,fields] ["case",x,arms] ["refuse",reason]`, plus `toData`, `textJoin`, `["relationCount", r]` and `["relationLookup", r, [column…], probe]` (each contracted to its expansion, as `textJoin`). An evaluator that rejects a line stops its stream; the runner restarts it and counts the line `rejected`. Text and unary primitives use code-point semantics; `textTake`/`textDrop` use the byte-size guard `n >= byteSize`; C has its own SHA-256. `perform` yields `status:"yield"` with `plans`, resumed from `responses` in order; `["refuse", reason]` evaluates its reason and is stuck at a value (§26).

Harness: `tests/conformance/generate.py` (seeded; kinds term, activity, stuck, diverge, shared-effect, exotic-value, chain, stored; asserts every tag and primitive occurs; `relation_cases`: 16 small stored relations counted and looked up, then a count, a hit and a miss over 2,048 rows) and `tests/test_conformance.py` (compares status, weak-head shape, and Plans when literal data). `python3 -m tests.test_conformance 1500 [IMPL_DIR]` prints the report. Last recorded (kernel15, 1500 cases plus the fixed `textHasAny`, stored and relation cases): 1486 of 1554 agree per evaluator, 68 known shared-effect, 0 unexpected. The 2,048-row walks are the slowest cases (Python about 13 s for the count). All three evaluators look `textHasAny`'s wanted words up in a set (C: an FNV-1a open-addressing table), linear as the kernel's.

Known divergence (`KNOWN_DIVERGENCE["shared-effect"]`): a `perform` reached while forcing a shared argument cell. The machine refuses it (`Refusal.sharedEffect`); call-by-name evaluators perform at each use. Typed programs cannot reach it (`noActivity`). Machine `divergent` and tick/capacity suspension map to `exhausted`. Not compared: step counts, deep values, non-literal plans.

Adding a Term form: extend `generate.py` (and its tag assertion), `EvaluateTerm.termOf`, the three evaluators' validators/arity tables/`reducible`, run the report, and decide fix vs `KNOWN_DIVERGENCE`.

## 7. Checkpoints

- Tokens: `.nat n | .text s | .str i`, JSON bare (`3`, `"x"`, `-(i+1)`). Term tags 24 (`toData`), 25 (`textJoin`), 26 (`refuse`, `[26] ++ reason`, §26); join frames 14-17, `refuse` frame 22; a refusal is `encodeRefusal` (`[8, text]` for `program`). Only additions: a checkpoint using a new tag does not decode on an older binary.
- Edition v3 (`ObjectiveBendCheckpointV3.lean`, `…checkpoint.v3`, §14): the dictionary encoding below of the state with every address relative to its holder. Written against a `Dictionary` rebuilt from the entry's term (`Dictionary.ofProgram entry.source.term`): a term is one token `i+1` for the program's `i`th subterm in preorder, environments of two or more addresses are a table listed once, strings are `Token.str` references. Every reference is emitted only after a check that it names exactly the value, so `stateV3_roundTrip` holds for every dictionary. `Dictionary.ofProgram` runs per start/resume.
- Collector: `collect` numbers live cells by `canonicalOrder` (depth first from the roots; a list spine put off to the next round), so a reading that walks further does not renumber every later cell. `orderValid` checks the order; otherwise `collectByAddress` (the allocation-order collector) is used.
- Host side: `resumeOne` rebuilds the `Checkpoint` from journaled tokens plus the activity's object/principal/intent/roots; changing `Checkpoint` fields stops older journals resuming. Block encoding of tokens is the host's (HOST-HANDOFF 5.6); v2 strings are bare or `str` references, so an utterance is no longer cut into its own leaf.
- Measured at the kernel lane (Garden prose suspension, `tests.test_policy` scenario): v1 248,006 bytes, v2 6,984 bytes.

## 8. Language features added since the lane-2 map

- `Data` (`Ty.data`, `Term.toData`, `Data.of::<T>(value)`): any well-formed first-order data (`Data.wellFormed`), produced only by `toData`; no elimination (`data_not_eliminated`). Runtime: `toData` is its value. Turn arguments are quoted by their declared type at every depth (`Turn.quoteAt`). Implicit injection (`coerceAt`/`coerceArgs`/`coerceGo`): where `Data` is expected and the expression has type `T`, the term is wrapped `toData T`; a value whose type holds an arrow or computation is refused by name ("refused (data-injection): …"). `Plan.obend`'s `call`/`send`/`create` payloads are `Data`. The typed-data schema has `Schema.data`; admission charges `admissionWork` and refuses "typed data value at Data repeats a record field".
- `textJoin(list, sep)`: `Term.textJoin`, frames `joinSeparator/joinList/joinCons/joinHead`, typing `Ty.listItem … = some .label`, meaning `textJoinExpansion`.
- Type-argument inference (`Generics.lean`, `inferArguments`, `synthI`): a call of a generic without `::<…>` gets the arguments its explicit spelling names, then is rewritten exactly as that spelling (instance numbers and packets agree; the generics pass visits children in the old JSON's sorted-key order, and changing that order moves every pin with a generic instance). A parameter left unbound is refused: "cannot infer the type argument U of Lists.kept …; write Lists.kept::<T, Rain>(…)". `maxInferenceSteps` bounds it. `world/` writes `::<T>` only where a world call's result type cannot be inferred (`world.view::<S>`, `world.call::<R>`, `world.interpret::<R>`) and never `Data.of`.
- `let label(x) = world.METHOD(arg)` then the rest of the block: lowers to `match world.METHOD(arg): case label(x): …` plus a `Pattern.unexpected` branch expanded to `case l(_): refuse("unexpected response l")` per other label. The scrutinee must be a world call ("refused (let-response)").
- `Term.refuse (reason : Term)`, surface `refuse(line)`, the line any String (§26): stands only where an activity finishes ("refused (refuse-outside-tail)", "refused (refuse-outside-activity)"; a reason of another type "refused (refuse-reason)"). Typing rule `PartialTyping.refuse`; machine frame `refuse`, then `control := .refused (.program s)`; `Turn.Step.refused` (wire `{status: "refused", reason, ticksUsed}`); the host journals `cardRefused`. `evaluate-term` reports `stuck`.
- Law readings: `law NAME "reading": EXPR`; `Surface.Decl.law name source reading`.
- String interpolation (`interpolationPieces`/`joinPieces`): `{expr}` in a string; up to four pieces lower to nested `textConcat`, more to `textJoin(TextPieces…, "")`. `{{`/`}}` are literal braces; a lone `}`, an unclosed `{` and two expressions in one pair of braces are refused by name. Document templates quote braces as `{`/`}`.
- `form ACTION [as NAME]:` blocks (`formRe`/`formKind`): fields `name: text A..B | natural A..B | source | a | b | c` (`source` is `F.Kind.source({})`, Bend source the host reads as text of 1 to `Host.Limits.formSourceMax`, which is `Bounds.maxPackageBytes`, 131,072 characters and fills from a reply's ```obend fence; the Workshop's `check` and `propose` declare it) declare `def NAME() -> F.Form` (default `ACTIONForm`) from the module's alias `F` of `Form.obend`; refused by name without a Form import or with an unknown kind.
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
- A hand-written `forms()` beside form blocks is accepted, and wins over the derived one (`Generics.lean`, the `forms` check); refusing it by name closes FOUNDATION §12's row. Closed by a diagnostic in `test_sugar`.
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
  tariff `1 + 2 * (bytes of both)`, reserving those bytes (since kernel10 `1 + 3 *` and a hash set, §5). An 1,800-character reply checked
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
  (`ObjectiveBendCheckpointV3RoundTrip.lean`); v2 decoded beside it until day 4 (§21). Measured then:
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

## 15. Lazy state: stored cells (RELATIONAL §11 item 4; the specification lane/kernel11 builds)

**Today.** A card or view (a pure entry) takes its arguments natively (`prepareNativeChecked`:
admission walks every node, `Cell.native d` per argument, forcing allocates one layer). An
activity quotes every argument as a term (`Turn.quoteAt`), checks it (`CheckedEntry.apply`,
`checkAt`) and evaluates it lazily. Either way the whole state is walked per turn, outside
the tick tariff for activities, and a turn records only `{object, version}`.

**The cell.** One new heap cell, `Cell.stored (s : Stored) (value : Option RuntimeValue)`:
`none` unforced, `some v` forced (its WHNF, kept with its provenance). `Stored` holds no
address:

| `Stored` | forcing it (one transition) | allocates |
|---|---|---|
| `object (state : List (String × Data)) (stored : List (String × Nat))` | `.record` of the state's fields in order: a field named in `stored` with size n is `stored (relation f n)`, any other `native d` | one cell a field |
| `relation f n` | `.variant "rows" a` | `a = stored (items f n)` |
| `items f n` | `.record [("items", b)]` | `b = stored (spine f 0 n)` |
| `spine f j n` | `j < n`: `.variant "cons" c`; else `.variant "nil" e` | `c = stored (cons f j n)`; `e = native (.record [])` |
| `cons f j n` | `.record [("head", h), ("tail", t)]` | `h = stored (row f j)`, `t = stored (spine f (j+1) n)` |
| `row f j` | the host's row j of f, forced as `native` forces it | its fields, `native` |

Every kind but `row` is forced by `stepRaw` alone (the shape is the kernel's: `Relation<T> =
rows {items: List<T>}`, FOUNDATION §9, and `nil`/`cons {head, tail}`); the cell becomes
`stored s (some v)`. Entering `stored s (some v)` returns `v`. Positions are the relation's
canonical order (key order) at the turn's read height; `n` is its row count there.

**The fetch.** `stepRaw` cannot fetch: entering `stored (row f j) none` is `.refused
.unfetched` (a new `Refusal`, reached only by a runner without a store). The hosted runner
fetches: `forceHostedFrom policy fetch limits bytes ticks state depth` gains `fetch : Fetch`
(`Fetch := String → Nat → Option Data`, beside `policy`, threaded through `forceHostedWith`,
`materializeWith`, `completeWith`, `yieldedPlanWith`, `executeStateWith`). When the control is
`.enter a` and `heap[a] = stored (row f j) none`, it calls `fetch f j` (none: `.refused
.unfetched`), charges `fetchCost d = (1 + 2 * b, b)` with `b = d.canonicalBytes` exactly as a
text primitive is charged (ticks first, `b` reserved against `bytes`, suspension retaining
the state when either fails), and takes `fetchStep d state`: `(heap', v) := forceNative heap
d`, `heap'[a] := stored (row f j) (some v)`, `control := .returned v`. A row is fetched once
per segment it is forced in; forced, it is native data like any other.

**Tariff.** Every non-row stored force is one tick (as `native`). A row is `1 + 2b` ticks and
reserves `b`, its canonical bytes. A turn that forces nothing of a relation pays nothing for
it, in ticks or in host work: the kernel holds `(field, n)` and nothing else. `count` over
`Lists.length` forces spine and cons cells only (no fetch, no bytes); a `rows` scan, `where`,
`joinOn` and a card render fetch exactly the rows whose fields they read; `lookup` (a Bend
walk) fetches the rows before the one it finds, since it compares their keys.

**The runner.** The entry points in `Turn.lean` (host16 switched the host and deleted the quoted
ones, `quoteAt` and their preparation, renaming these from `…Stored`):
- `structure StoredRelation where field : String; size : Nat; key : List String`
- `structure Store where relations : List StoredRelation; fetch : String → Nat → Option Data`
  (`Store.empty`: no relations, every fetch `none`).
- `startEntry (entry : CheckedEntry) (arguments : List Data) (store : Store) (binding : Binding) (b : Budgets) (dictionary : Option Dictionary := none) : Except String (Step × Reads)`
- `resumeSuspended (entry) (suspension : Suspension) (store : Store) (binding) (value : Data) (b) : Except String (Step × Reads)`
- `resumeEntry (entry) (checkpoint : Checkpoint) (issued : String) (binding) (value : Data) (b) (store : Store) (dictionary := none) : Except String (Step × Reads)`

The stored path takes every argument natively, like a card (`nativeApplication`; no
`quoteAt`, no `checkAt` per turn: each data argument is admitted by `conformsUnder`, which
`conformsUnder_iff` makes `HasType`, as `prepareNativeChecked` admits a card's). The first
argument is the state: before the check, each field named in `store.relations` is replaced by
the empty relation `rows {items: []}` (so the check walks the scalars only), and the state
enters as one `stored (object fields stored) none` cell. The rows themselves are not
re-checked: the host checked each when it was written (RELATIONAL §11 item 2). Ticks of the
stored path differ from the quoted path's (a native argument is one tick a node where a
quoted one is three); no `test_tariff` pin moved when the host switched (host16).

**Reads.** `structure Read where field : String; key : Data; bytes : Nat` (a forced row: its key
projection onto `StoredRelation.key`, a record of those columns, and its canonical bytes) and
`structure Reads where rows : List Read; spans : List (String × Nat); found : List (String × Data);
gaps : List (String × Option Data × Option Data)`, read off a segment's final state before any
collection (`Store.readsOf`): every `stored (row f j) (some _)` cell is a row read; `spans` gives, per
field, the prefix a walk or a count observed (`j + 1` for `spine f j n` forced, `n + 1` for a `size` or
the forced `nil`: the whole key set); a lookup that hit (`found f j`) reads its key, row forced or not
(`found`); one that missed (`absent f low`) reads the gap its key falls in, between the keys at
`low - 1` and `low` (`gaps`, none past an end). A lookup's probes read nothing: where the sought key
falls decides it. The host journals them on the root as `rows [{field, key}]` (found keys among them),
`spans [{field, through?}]` and `gaps [{field, after?, before?}]` (`Ops.Cells`, `cellsOf`) and judges
(`cellsCurrent`, WHOLENESS §3a): stale when a write since touched a read key, any key at or before a
span's last, or a key strictly inside a gap; a write below or above a looked-up key leaves the lookup
current (`test_relation.Lookups`). A turn's reads are the union over its segments (`Cells.join`: a span
covers the rows and gaps below its last key).

**The invariant.** A forced row is `store.fetch f j` for the turn's store, and the host builds that
store from the object's state at the turn's read height (the version `recordRoot` records):
a fetch on a resumed segment must answer the same version (the host keeps it, or refuses
`staleRoot` and re-runs the turn, as a moved root does today). The binding's roots digest
already names that version, so a checkpoint resumed under another one is refused before any
fetch.

**Checkpoints.** v3 gains cell tag 5: `stored`, its `Stored` (tag 0-5 and fields: strings,
naturals, `encodeData` for the object's state) and an option (`0`, or `1` and the value).
An unforced row is its handle `(f, j)`, never its data; a forced row is its value (addresses
of native columns, which the checkpoint holds as `native`). Nothing else changes; a
checkpoint with tag 5 does not decode on an older binary.

**What the proofs gain.** Cases, not ideas: `cellAddresses (stored _ v) = v`'s addresses
(none unforced), `renameCell`, `trimCell`, `eraseCell` map the value; `stepRawFast`,
`sizesAfter` gain the enter-stored cases; `related_stepRaw` and `erase_stepRaw` the enter
cases (a stored force allocates address-free cells, as `forceNative` does); the runner's fetch
branch gets `related_fetchStep` and `erase_fetchStep` (both sides read the same handle, so the
same row, and `forceNative_related` does the rest); `agree_*` and `related_*` take `fetch` as
a parameter, and `checkpoint_resume_segment` holds for every `fetch` (both runs ask the same
function); `stateV3_roundTrip` gains the tag-5 case. `#assert_axioms` on each.

**Evaluators.** A stored cell is not a term form, so the three evaluators do not change: a
term run with stored state is, by definition, the term applied to the substituted Data. The
conformance generator gains a `stored` kind (a term over a state record holding a relation,
reading none, some or all of its rows) which `evaluate-term` runs with `{arguments, stored}`
(the named relation fields held as stored cells, fetched from the argument's own rows) and the
evaluators run substituted; both must agree on status, shape and plans.

**Bounds.** A cell, not an object, is bounded: `Bounds.maxCellBytes` (262,144) bounds a fetched row
(the kernel refuses a larger one as unfetched) and, at write, each changed cell (`Turn.Changes.overBound`:
the scalar part when it changed, each row put), refused `capacity`, clause `maxCellBytes`, naming the
cell; a seed and a migration's result are bounded by every cell (`Changes.all`). A write is charged the
canonical bytes of the cells it changes (`Changes.bytes`, `Ops.chargedBytes`: the storage ledger). FOUNDATION's
sentence: "State is bounded per cell: the scalar fields together and each relation row are at most 256 KiB
of canonical bytes, a relation's length is its declared limit, and a write pays for the cells it changes."

**Two primitives (built, lane/kernel15).** `Term.relationCount relation` and `Term.relationLookup
relation key probe` (`key` the columns, `probe` a function of a row's projection onto them to 0
below / 1 equal / more above the sought key). Their meaning is a walk, `relationCountExpansion` and
`relationLookupExpansion` (Step rules), which the three evaluators implement literally. The machine:

| frame | on | does |
|---|---|---|
| `relationRows walk` | `rows payload` | payload a stored `items f n`: a count pushes `stored (size f n) (some n)` and returns `n` (one transition, no row); a lookup starts `searchStep … 0 n`. Else enters the payload under `field "items"`, `relationList walk` |
| `relationList walk` | `nil` / `cons p` | count: the tally / enter `p` under `field "tail"`, tally + 1. Lookup: `none` / push `⟨keyProjectionTerm key, [p]⟩` and apply the probe |
| `relationProbe key probe p` | `0` / `1` / more | walk on to `p.tail` / `some {value: p.head}` / `none` |
| `relationSearch key probe f low high` | `0` / `1` / more | search the upper half / push `stored (found f mid) none`, `some` / the lower half |

`searchStep` probes the middle by pushing `stored (key f mid key) none` and applying the probe to it;
an empty range pushes `stored (absent f low) none` and answers `none`. `Walk = count n | lookup key
probe`. New `Stored` parts: `key` (fetched: the row's projection onto the lookup's columns), `found`
(forced: `{value: row}` with the row unforced, so a presence test fetches nothing), `absent` (`{}`),
`size` (the count). `Fetch := Stored → Option Data` answers `row` and `key` (`Stored.fetched`);
`Turn.Store.bounded` answers a key only when the lookup's columns are the relation's declared key
as a set (rows are in that key's order alone), so a search by other columns is refused `unfetched`,
never answered wrong; the walk of a literal relation has no declared key and walks. The probe is
written by the elaborator: `relationLookup(r, key)` is `(λk. relationLookup r columns (λx.
canonicalCompare(x, k))) key`, the columns being the key record's fields, each refused by name
unless a column of the row type of the same type ("refused (relation-lookup): …").

Reads: a hit reads its key and a miss its gap (**Reads** above); probed keys add nothing.

Typing: `Ty.relationItem` (the closed one-case sum `rows {items: List<T>}`, `Ty.listItem` for the
list, which `isTextList` folded into), `Ty.projection` (the key's record type), `Ty.maybe`; rules
`PartialTyping.relationCount` and `.relationLookup` (the probe a reusable shareable arrow from the
projection to `Nat`, `argumentAllowed … .unrestricted`), `infer` cases, `decodeTexts_arr`. Codecs:
term tags 27-28, stored tags 6-9, frame tags 18-21 (additions only). Proofs, each with
`#assert_axioms`: `sizesAfter_eq` (so `stepRawFast_eq_stepRaw`, `runFrom_eq_runBounded`), `related_stepRaw`
(`searchStep_related`, `storedItems_rename`), `forceStored_related`, `erase_stepRaw`
(`storedItems_erase`), the fetch lemmas over parts, `term_roundTrip`, `frame_roundTrip`,
`walk_roundTrip`, `frameV3_roundTrip`, `mapWalk_inverse`, `decode_json`. Tests:
`test_stored.RelationPrimitives`, `test_conformance` (`relation_cases`).

Measured on hbox (one process, best of 15, `k15_measure.py` in the lane's scratchpad: the tree's own
`world/lib/Relation.obend`, `run` and `turn-start`/`turn-resume` with `stored`, 2,048 rows):

| | before (foundation 8f69bd7e) | after |
|---|---|---|
| card: a hit (row 1,536) | 292,448 ticks, 1,537 rows fetched, 347 ms | 270 ticks, 1 row, 18 ms |
| card: a miss | 390,559 ticks, 2,048 rows, 568 ms | 744 ticks, 0 rows, 14 ms |
| card: a count | 49,238 ticks, 85 ms | 51 ticks, 15 ms |
| turn: write then count (resume) | 49,213 ticks, 120 ms start+resume | 26 ticks, 37 ms |

The milliseconds after are the 2,048-row state on the wire.

**Built (lane/kernel11).** Step 2: `Stored`, `Cell.stored`, `Refusal.unfetched` (checkpoint
refusal code 9), `objectCell`/`allocateObjectFields`/`forceStored` (Machine); `storedChildren`,
`forceStored_size` (Fast); `Fetch`, `fetchable`, `fetchStep`, `fetchCost`, `fetchable_spec`,
`storedInitial`, `forcedRows`, `spineReach` (now `storedReach`) and the fetch branch of `forceHostedFrom` (Data);
`encodeStored`/`decodeStored`, `stored_roundTrip`, v3 cell tag 5 (`cellV3_roundTrip`); collector,
trim and erase cases; `erase_forceStored`, `fetchable_agree`, `agree_fetchStep`,
`forceStored_related`, `related_fetchable`, `related_fetchStep`; `agree_*`, `related_*`, the three
`*_resume_segment` theorems and `checkpoint_resume_segment` take `{fetch}`. `yieldedPlan` and
`complete` take a `Fetch`. `evaluate-term` takes `stored: {state, relations}` and answers
`forced: [[field, position]]`; the generator appends 32 `stored` cases from their own stream
(`stored_cases`), and `test_conformance.StoredCells` checks stored against literal runs and the
forced rows. Conformance 1500: 1467 of 1535 agree per evaluator, 68 known, 0 unexpected (the 32
stored cases all agree). No packet or pinned tick moved.

Step 3 (runner): `Turn.Store`, `StoredRelation`, `Store.bounded` (rows within
`Bounds.maxCellBytes`), `Read`, `Reads` (`Reads.toJson`: `{rows: [{field, key, bytes}], spans:
[{field, reach}]}`), `keyProjection`, `scalarPart`, `storedStart`, `runStored`,
`startEntryStored`, `resumeSuspendedStored`, `resumeEntryStepStored` exactly as specified above,
and for cards and views `Package.executeDataEntryStored entry arguments store limits :
Except String (DataExecution × Reads)`. `exhaustedResource` names `heap` for a fetch that would
not fit. Wire (tests and the evaluators' harness only; the host calls the Lean functions):
`turn-start`/`run` take `stored: [{field, key}]` (the first argument's named relations held as
stored cells over its own rows) and `turn-resume` `stored` and `state`; each reply carries
`reads`. `profile` is not computed on the stored path. Measured in `tests/test_stored.py`: a turn
that reads no row, or one row, spends the same ticks over 0 or 2,048 rows; a row of 101 more
canonical bytes costs exactly 202 more ticks; a card render, a scan and a merge join report
exactly the rows they read (the join none past the shorter relation's end).

Step 5 (measured on hbox, P-cores, lane against foundation f7865b0). `compile-profile stored
REQUEST ROWS R` runs `tests/test_stored.py`'s `third` (a write, then row 3's text) from a state of
ROWS rains, quoted and stored. At 2,048 rows the start and resume take 2,853 us quoted and 45 us
stored (0 rows: 32 and 29 us); ticks 81 + 168 quoted, 79 + 208 stored (the fetched row is
`1 + 2b`); one row forced; the suspension's checkpoint is 45,357 canonical bytes quoted and 540
stored (557 and 538 at 0 rows). Before host16 switched the host, the rehearsal replay
(18,183 captured requests, `compile-profile replay … "world-turn directory receive" 1`) writes a
byte-identical journal on both binaries (median suspension entry 3,895 bytes over its 43, the
same ticks per class) in 84.75 G user instructions against 84.53 G (within the 5% run-to-run
noise; directory `receive` 1,501 ms against 1,511). The Counter bump replay (R = 50, best of
three): 120 us a bump on both, 102 ticks, 21.73 G instructions on both. `fetchable` is
`@[inline]` so the hosted runner's fetch test costs nothing on a run without stored cells.

**The host's entry points.** All in `Delvetalk.Turn` unless named: `Store`, `StoredRelation`,
`Store.bounded`, `startEntry`, `resumeSuspended`, `resumeEntry`, `materializeStored` (a checkpoint kept
past the process, its unforced stored cells made native) (each `Except String (Step × Reads)`),
`Package.executeDataEntryStored` for cards and views, `Read`/`Reads`/`Reads.toJson`, `keyProjection`,
`scalarPart`, `relationRows`, `StateCells` and its parts below, `Bounds.maxCellBytes`, and
`storeOfState state [{field, key}]` (a `Store` over a state's own rows, as the tests, the evaluators'
harness and the profile build it). The host's frame store is its object's cells (`Held.of`,
`StateCells.store`), kept for the turn's resumed segments.

**The state as cells (lane/kernel18).** The host holds an object's state as its cells, `Object.cells :
Turn.StateCells {scalar, relations, cid, whole}`: the scalar part (`scalarPart`), each declared relation's
rows in key order (`RelationCells {field, key, rows : Array RowCell, chunks}`, a `RowCell {row, key, bytes,
cid}` holding the row, its key projection's canonical bytes, its own canonical size and its block's binary
CID), the state's CID, and the whole state as a `Thunk` made from the cells when something reads it whole
(`Object.state`; a law and rules read `Ops.viewFor`: every scalar field and only the relations their
clauses name, the whole state when one cites another's law by `under`). A write never walks the state:
- *Edits* (`Ops.applyEdits` over `Editing`, `relationEdit`): a relation edit is a binary search on the
  key bytes (`RelationCells.position`, `Canonical.bytesLt`) and one `insertAt`/`setAt`/`eraseAt`; retention
  is `eraseAt 0` past the limit (`withinLimit`); a relation `set` is the whole relation, made canonical. It
  answers `Applied {cells, evicted, changes}`, `changes : Changes {scalar, rows}` being the cells it changed
  (`Changes.of`: the rows put that the state after holds and the state before did not, the scalar part when
  its bytes moved).
- *Check*: `Changes.checked` (the scalar part, each relation holding only its changed rows) conforms. This
  is exact: with every row left as it was conforming, the state after conforms iff the checked one does
  (`Theory.ObjectiveBendCellConformance`: `field_typed_iff` per field, `relation_typed_iff` per row,
  `chain_typed_iff` per item; `Turn.listData_chain`; each `#assert_axioms`). The host declares a relation
  only over a genuine `Relation<T>` (`Ops.relationItemOf` in `rowColumns`), where per-row conformance holds.
- *Bound and charge*: `Changes.overBound`, `Changes.bytes` (**Bounds** above).
- *Name*: the state's block is the scalar part's canonical encoding with each relation's `items` the links
  (DAG-CBOR tag 42) of its chunks, a chunk being a run of rows in key order ending at a row whose CID's last
  byte is below 4 (about one in 64) or at the last row, its block the array of its rows' links
  (`stateBlock`, `chunkOf`). Chunk ends depend only on the rows, so an edit re-forms the chunk it falls in
  and the rest are kept (`RelationCells.edited`; a `#guard` checks inserts, replacements and erasures at
  the front, inside, at chunk ends and at the end against a fresh chunking). A one-row write hashes its
  row, its chunk and the state block (32 chunk links at 2,048 rows). `tests/wire.py` `state_cid` is an
  independent encoder; `test_relation.StateCid` compares it with every journaled `cid` over random edits
  and retention. Every creation journals its `cid` too (the replay checks it), so `stateCidIn`,
  `stateCidAt` and slugs read no seed. Replay edition 10: a carry reads an edition-9 world by its naming
  (`Ops.Naming.ofEdition`: the CID of the wire JSON, a creation by its seed) and lists each state's two
  names (`renamed [{object, before, after}]`; `transport/carry.py` checks them). `deploy/carry-check.sh` on
  `delvetalk-20261012T090950Z.tar.gz` (edition 9): green, breaking (the deploy carries).
- *Store*: `StateCells.store` fetches row `j` from the array; `storedState` is `cells.scalar`.

Measured on hbox under load (`deploy/bench-write.py`: 200 turns of `upsert` replacing the middle row of a
relation of ROWS rows through the pipe to one host, two runs interleaved with foundation 5db9aa79's binary;
median, best in brackets; 120 ticks a turn on both):

| rows | foundation 5db9aa79 | kernel18 |
|---|---|---|
| 16 | 0.72-1.02 ms (0.66) | 0.72-0.81 ms (0.49) |
| 256 | 4.45-4.57 ms (2.69) | 0.90-0.94 ms (0.58) |
| 2,048 | 43.2-48.1 ms (25.2) | 0.84-0.93 ms (0.57) |

On a quieter box the foundation's 2,048 rows took 17.6 ms. Before content-defined chunks, a flat spine of
row links made 2,048 rows 2.7 ms against 0.8 (its 84 KB block hashed per write).

## 16. Queue for the successor (lane/kernel15, after foundation 8f69bd7e)

Done: items 1-6 (kernel7, kernel8: §19-§22); item 8 (kernel9, §23); the codex findings (kernel10,
§24); lazy cells (kernel11, §15); the package and instance bounds, located generics refusals and
LAW §4 A/E/H (kernel13, §25); the law term language (kernel14, §25 M, N); item 15, the relation
primitives (kernel15, §15 "Two primitives"). Remaining, in order:

15a. (Objects lane.) `Relation.obend`'s `count` and `lookup` are the primitives now, so every caller
   already pays the stored tariff; what is left is theirs, by site:
   - drop `keyOf` from every `Relations.lookup(r, key, keyOf)` (the primitive reads the key's own
     columns; the parameter is unused until then, and then `lookup`'s signature is `(relation, key)`):
     Library 56 and 82, commonplace 43 and 275, room 38, Workshop 124, Record 123 and 128, Deal 76,
     Garden 206, Rows 96 (`presentAs`). Each was a walk of every row before the key (about 190 ticks a
     row passed: 292,448 for row 1,536); it is now at most twelve probes over 2,048 rows and one row.
   - Tide 94 `Relations.exists(state.subs, fn(s) -> s.who == sub.who)` is a lookup by the key `{who}`:
     `relationLookup(state.subs, {who: sub.who})` (a presence test, no row fetched) instead of a scan.
   - the `Relations.count` callers (Tide 94, room 69/79/287-292, Avatar 84/105/106/142/152/163/356/362,
     Workshop 121/234, Garden 377, Env 61/62) already moved: about 24 ticks a row to one tick.
15b. (Host and kernel.) Interval spans: a lookup reads the gap its key falls in (a miss) or one key (a
   hit), not the prefix below it. `Reads.spans` as `{field, from, reach}`, the host's judging rule over
   key intervals; the kernel's `found`/`absent` cells already name the positions. Closes when a write
   below a looked-up key no longer conflicts with the lookup.
7. `textWords(s) -> List<String>`: only if an object asks; none does (kernel13 grep of docs/, world/).
10. `Form.obend` `type Forms = Lists.List<Form>` (objects lane) would let the derived `forms()`
   be `F.Forms` and drop its List.obend requirement (Counter, Loop).
12. (Done; the standing caveat.) `expandSuspended` recomputes a digest a compacted journal entry lacks:
   the journal is the trust root, so that is sound, but a host that ever resumes a checkpoint from
   outside its journal must look its digest up there.
16. Host requests from kernel14 (§25 item M): the law's denotation of every atom that still fails
   closed in `Host/Law.lean`: `Facts.reads`, filtered counts, `changed`, cited membership, `under`,
   the roots and the acceptance check.
17. `Package.localize` (check-package) still recompiles each function alone for a spanless refusal:
   2.5 s on a 32 KB package. With the generics pass located (§25 items 2, 4) its remaining callers
   are elaborator refusals without a span; find them by making `localize` count its calls in
   `test_sugar` and `test_located`-style fixtures, then delete it when none is left.
19. A card's stored refusal answers the `Failure` name (`…Failure.refused`), not `Turn.refusalText`
   (a turn's does): `Package.executeDataEntryStored` should say why, as the turn path does.

Done since kernel10 and no longer queued: 9 (located generics refusals, kernel13), 13 (`52ad1b2`),
18 (LAW §6 items 2 and 3, kernel halves, kernel14: §25 item M), 15 (kernel15).

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
  `State` types `f` as a `Relation<…>` (the parser emits the marker `$remove`; since kernel10 the
  generics pass lowers it with `lowerRemove` once `Generics.relationFields` has resolved the
  effective State and each field's type, the relation recognised as derived Edits recognise it, so
  `type State = Lib.State`, an aliased field type and a layer's inherited relation retract by key;
  a marker makes a declaration take the generics pass, `declGenerics`); `write {f: amend v with c}` is `amendItem {item: v, change: c}`. An index
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
- Order of the derived declarations (canonical): they end their module as `forms()`, then
  `Edits` and `keep()`, then the form inputs and choice sums, and are specialized after every
  module's own declarations. Knot fields (`forms`, `keep`) are numbered and their types interned
  in declaration order, so this is the order in which a module that writes `forms()` at its end
  (everything else derived) compiles to the same packets; with `keep` first, 10 entries of Env,
  Garden, Policy, Scene and Workshop differed in their annotations' type indices. Pins
  re-recorded for exactly those 10 (source pins unchanged). Test: `tests/test_derived_forms.py`
  (every entry of Deal, Env, Garden, Policy, Scene, Workshop against `forms()` written at the end).
- `fixed` State fields (coordinator's addition before commit 3). `colour: fixed Colour` in
  `record State` (`Surface.Field.fixed`; anywhere else "refused (fixed): only a State field is
  fixed") is a field the derived `Edits`/`keep()` omit, set only by `initial()` or a seed.
  `Generics.checkFixed` (in the probe, also through `type State = M.S`) refuses a hand-written
  `Edits` field or any `world.write(...)` argument (a record, or `extend(keep(), {...})`, so every
  `write {...}`) naming one: "refused (fixed): colour is fixed; no edit names it". The artifact of
  an entry whose State has fixed fields lists them, `fixed: [names]` in State order (absent
  otherwise; `Package.fixedFields`), for the host's actions, inspect and the Workshop's `set`. Since kernel10
  both follow the effective State: `Package.stateRecordAt` resolves `type` alias chains of any length and,
  in a layer that declares no State, the State below (`Super`); `Generics.effectiveStateFields` makes
  `checkFixed` refuse a layer's write naming an inherited fixed field (`test_sugar.FixedFields`).
  Pins: 0 recompiled. Tests: `test_sugar.FixedFields` (the packet equals the State-renamed module
  whose hand-written pair omits the fixed fields; the refusals).
- Commit 3 moved 36 test files' fixtures off hand-written pairs (deleted; `test_relation`'s own
  `RowEdit` sum became `Plans.Entries<Rain, Rain>`, `test_protocols`' line moved 19 -> 15,
  `test_sugar`'s explicit spellings `Entries<X, {}>` -> `Entries<X, X>`). Pins: 0 recompiled.
- `declares` (for the host, which scanned the entry source for `def forms(` and so never saw a
  derived `forms()`): every artifact lists which of `Package.conventionalNames` (forms, methods,
  relations, views, lenses, law, lawReads, initial, render, receive, blurb, page, publishPage,
  set) the entry module declares, derived declarations included (`declaredNames` over the
  generics pass's decoded modules), in that order; for a layer, every module of its stack (kernel10:
  a layer that wrote no `methods()` or `forms()` declared neither, so the host took inherited methods
  for helpers and refused inherited forms). The host lane switches `declaredForms` and
  `packageDeclares` to it. Test: `test_sugar.Declares`.

## 24. The codex review's kernel findings (lane/kernel10, after foundation 534b92c)

One commit each, each with its failing input as a test first (all ten failed before their fix):
1. Natural arithmetic past 2^64 is charged before the result is built (`naturalStepCost`, §5);
   forty squarings of 2 are refused, not a 128 GiB natural. `test_tariff.NaturalArithmetic`.
3. A checkpoint resumes only against a digest its resumer recorded (`issued`; §2, §16 item 12);
   a stateless session keeps the digests it handed out. The packet-path `resumeActivity` is
   deleted. `test_turn`.
4. `textHasAny` looks words up in a hash set (`textHasAnyWordFast`, `@[csimp]` to the list
   reference, axioms pinned) and pays a tick a byte more. `test_text_words.ManyWords`.
7. `encodeJson` refuses a negative integer below -2^64. `test_canonical`.
8. The byte budget is the canonical DAG-CBOR size (`Data.canonicalBytes`, §4), for results and,
   newly, Plans; the legacy `encoded` is gone. `test_tariff.CanonicalBytes`.
9. `labelEqual` costs `1 + min` of its operands' bytes. `test_tariff.LabelEqual`.
10. A take/drop preflight that cannot pay spends its allowance. `test_tariff.FailedPreflight`.
2. `fixed` follows alias chains and a layer's inherited State; `checkFixed` refuses a layer's
   write of an inherited fixed field. `test_sugar.FixedFields`.
5. `declares` covers a layer's stack. `test_sugar.Declares`.
6. `write {f: remove v}` is lowered in the generics pass after the State and field types resolve.
   `test_sugar.Writes`.
Also, for the host lane: `request.kind == proposed` (and write, reprogram, amend) in the law
fragment (`kindNumber`, `parse_kind_names`).
No pinned tick count and no packet moved (pins: 0 recompiled). The three evaluators and the
conformance generator needed nothing: no term form or primitive meaning changed, and conformance
compares values, never costs. Full suite on hbox at the end: 1,148 tests, 0 failed.

## 25. Honest bounds (lane/kernel13, after foundation 2cb6fd5)

Measured on persvati (24 cores, load ~9, best of two or three; scripts `kernel13.sh`,
`k13_gen*.py`, `k13_many.py` in the lane's scratchpad, the packages are generated):

| package | instances | host-shaped compile (`initial` + 10 methods, one process) | resident |
|---|---|---|---|
| Garden, 31.7 KB | 140 | 0.34 s | 114 MB |
| Garden + Card, 61 KB | 161 | 0.35 s | 116 MB |
| Garden + Card + 2 copies, 117 KB | 203 | 0.42 s | 106 MB |
| Garden + Card + 7 copies, 258 KB | 308 | 0.64 s (refused at 256 instances before item 2) | 127 MB |

Card's declarations alone (one entry module, `check-package`, 20 entries in one process): 30 KB
0.09 s / 0.17 s, 58 KB 0.11 / 0.24, 114 KB 0.15 / 0.27, 255 KB 0.27 / 0.54 s, 93-112 MB.

1. The package bound. `Bounds.maxPackageBytes` = 128 KiB: every measured size compiles under a
   second, so compile cost does not decide; the scale rule does. A program is also data held whole
   in one state cell (a kind's body, a Workshop draft, a form's reply), a cell is `maxCellBytes`
   (256 KiB), and 128 KiB leaves its row the other half. Every bound a package meets: the host's
   `maxPackageBytes` (reprogram, extend, create of source, `check`; host request below) and
   `formSourceMax` (a form's `source` field, the same bound), the kernel's `maxModuleBytes`
   (512 KiB a module), `maxPackageSourceBytes` (1 MiB, the import scan), `maxFrameBytes` (16 MiB a
   driver line, which holds the artifact a `run` sends back: 1 MB for the 258 KB Garden, 2.6 MB for an
   entry reaching 1,024 instances), `frontCacheSourceBytes` and `entryCacheBytes` (caches: a closure
   or artifact larger than its cache is compiled and not held, never refused). Each kernel refusal
   names its bound. `tests/test_package_bounds.py`: a 131,072-byte module checks, compiles and runs;
   the module and import-scan bounds refuse by name.
   Landed (lane/host15, HOST-HANDOFF 134; `spec/Delvetalk/Host/Store.lean`): `def maxPackageBytes : Nat :=
   Bounds.maxPackageBytes` and `def formSourceMax : Nat := Bounds.maxPackageBytes`; the four
   refusals (TurnLoop `creationInputs` and `buildCreated`, Ops `checkSource` and `prepareProgram`)
   read "package source exceeds maxPackageBytes (131072 bytes)"; `tests/test_form_bounds.py`,
   `world/lib/Card.obend` and `world/objects/Policy.obend` read 131072 too. Until the per-cell bound (§15 step 4) replaces `maxStateBytes`, the Workshop's
   `held` (12 drafts) cannot hold 12 full-size packages in 256 KiB: `test_relation_limits` fills it
   with 16,384-byte packages and must keep doing so until that switch.

2. The generic-instance bound. `Generics.maxInstances` 256 -> 1,024. Measured (`k13_many.py`: N row
   types, each used through Relation insert, count, retract and rows, about eleven instances each;
   `check-package` then the compile of an entry reaching all of them, one process):

   | instances | check | compile | packet | resident |
   |---|---|---|---|---|
   | 178 | 0.09 s | 0.06 s | 0.35 MB | 87 MB |
   | 354 | 0.15 | 0.11 | 0.70 | |
   | 706 | 0.27 | 0.23 | 1.40 | |
   | 1,025 | 0.39 | 0.35 | 2.04 | 107 MB |
   | 1,410 | 0.57 | 0.55 | 2.81 | |
   | 2,818 | 1.38 | 1.33 | 5.63 | 167 MB |

   Linear (about 0.37 ms of check and 2 KB of packet an instance); 1,024 is the most whose check and
   compile stay under a second together. World closures today: Kind 197, Directory 190, Garden and
   Place 140; the 258 KB Garden of item 1 needs 308. The refusal names the count, the bound and the
   declaration that asked, at that declaration: "refused (generic-instances): the package needs more
   than 1024 generic instances; Many.use92 asks for instance 1025, removeWhere at Many.R92
   (Generics.maxInstances)", `module`, `span`. Mechanism: the pass's error is `Generics.Refusal
   {message, module?, span?}`; text thrown anywhere in the pass is placed by `rewriteTop` at the
   declaration being rewritten (so `Package.localize`'s recompile-each-function search, 2.5 s on a
   32 KB package, no longer runs for a specialization refusal), and `throwThe Refusal (refusalAt …)`
   places one more precisely. The dead linear `instances.find?` by key (a key is a hash of the pair
   `instanceOf` already indexes) is gone. Packets do not move (pins: 0 recompiled).
   `test_package_bounds.InstanceBound`.
L. (Coordinator's insertion, docs/LAW.md §4 A, E, H; §6 item 1, kernel half.) `ObjectiveBendLaw`:
   `LawRef.clock` (`request.clock`, the world clock at the write in minutes), `LawRef.object`
   (`request.object`, the written object's id; text-comparable: `request.object == "tide"`),
   `LawRef.old F` (`old.F` as a reference; at creation the empty value, as `writeOnce` reads an empty
   field; `old.a.b` refused by name), and `LawExpr.leRSum` (`REF <= REF + REF`, so
   `request.clock <= old.tended + new.gap` is one atom). `compile`: clock and object are the slots
   `request/clock`, `request/object`; an atom reading `old.F` and the three-slot bound are `any []`
   (host-judged, as relations). `fields`, `fieldsPlain`, `render`, the parser and its refusals cover
   them. Theorems `parse_clock_old_object` (METAPHYSICS `alive` as `request.method == "tend" or
   request.clock <= old.tended + 1440`) and `compile_clock_old_object`, `native_decide`,
   `#assert_compiled`. `Host/Law.lean` first gained only fail-closed arms; the host lane then added
   `Facts.clock`, `Facts.object` and `read` over `old` (HOST-HANDOFF 133), so a law using them is judged.
M. (lane/kernel14, docs/LAW.md §4 B, C, D, F, G; §6 items 2 and 3, kernel half.) The law grammar is
   one term language (`Compiler/ObjectiveBendLaw.lean`, its module comment is the grammar):
   `LawTerm` (`new.F`, `old.F`, `request.FACT`, `count(SIDE.F)` and `count(SIDE.F where COL == TERM)`,
   INT, `"TEXT"`, `TERM + TERM`) mutual with `LawFilter`; atoms `eq`, `le`, `member` (`LawPlace`:
   `[INT, …]`, `new.F`, `new.F.COL`, `"OBJECT".F.COL`), `rule` (`LawRule`: monotone, writeOnce,
   appendOnly, unchanged, insertOnly), `changed(new.F.COL) by TERM`, `under "OBJECT"`. A count is a
   reference, so the filtered count, its growth form and the quorum
   (`count(new.G) <= count(new.F where C == V) + INT`) are comparisons. One refusal shape,
   `law outside the enforced fragment: FOUND (RULE)`; one name walk (`LawExpr.names`), projected as
   `fields` (the written object's), `fieldsPlain` and `reads` (the cited objects, each once); one
   theorem family over tables (`parse_accepts`, `parse_refuses`, `render_reads_back`,
   `refusals_name_what_and_why`, `names_walk`; `native_decide`, `#assert_compiled`). Renders of every
   law that parsed before are byte-identical; packets and pins do not move. Deleted: `compile`,
   `packageLaw`, `LawRef.slot` and the `Pred` library (892 lines; nothing called them, and the
   agreement theorem `Kernel.ObjectLaw.compile_sound` the module cited does not exist in this tree,
   so no proved fact went). `Host/Law.lean` was ported arm for arm; what it does not yet denote fails
   closed. **The host lane's request (lane/host15), done by lane/host17 (HOST-HANDOFF 5.139):**
   - `Facts` gains `reads : List (String × Data)`: the state of every object the law cites,
     transitively through `under`, at the version recorded as its root. (`clock`, `object` and `read`
     over `old` landed with HOST-HANDOFF 133 and are carried through the port.)
   - `read (.count of (.eq col value))`: the rows of `rowsAt old new of` whose `rawField col` canons to
     the value's data. Generalize `memberData` to every term (a numeric reading as `.natural`), and use
     it for the filter, membership and `changed`.
   - `denote (.changed F C who)`: with `before` the rows of `old.F` (none at creation) and `after` of
     `new.F`, the rows of `before` absent from `after` by canonical bytes, less `facts.evicted` for F,
     and the rows of `after` absent from `before`; every one has `rawField C` equal to `who`'s data.
   - `denote (.member t (.cited O F C))`: as `.column F C` over `facts.reads.lookup O`; absent is false.
   - `denote (.under O)`: the `law` field of `facts.reads.lookup O`, a label, parsed by the law-text
     parser (`Ops.parseLawText`, which moves beside `denote` so `Law.lean` can call it), every clause
     admitted at depth − 1; `denote` takes a depth, `Limits.lawDepth` = 4; depth 0, absent, not a
     label, or unparsable is false.
   - Roots: every clause's `LawExpr.reads`, closed under the `under` citations of the cited laws,
     joins the write's roots at the version read (`withLawReads` generalized), within `maxRoots`, each
     viewable by the subject or the write refuses `lawRefused lawReads`; journaled, so replay re-judges
     from them; a cited object moved since the read is `staleRoot`.
   - Acceptance (create, amend, reprogram, the default law aside): every `under` resolves to an existing
     object whose `law` parses; a cycle within `lawDepth` refuses naming the cycle; the composed law
     passes the metarule (`amendable`). `world-inspect` lists the citations.
   - Then the objects lane: Tide's `self` and its five helpers become `law self "only you change your
     own subscription": changed(new.subs.who) by request.subject`; Deal's `def law` becomes `law signer
     "a party countersigns only for themselves": changed(new.signatures.principal) by request.subject`;
     Record gains `changed(new.lines.author) by request.subject`; Kind's `lawOf` and `{maker}` holes
     become `under "kind/<name>"` and `request.subject == new.maker`.
N. (lane/kernel14, docs/review/fungus-2026-10-11.md K1, K2.) Deleted with their reasons in the
   commits: the cSHAKE tower and `HashBytes` that hung from `Pred` (1,290 lines); the ops no caller
   sends (`run-compact`, `inspect-spec-v1`, `compare-data-types-v1`, `allocation-data-types-v1`,
   `template-expand`, `packet-cache-status`) and what only they reached: the quoted-argument data
   path (`executeQuotedDataValue`, `PackageData.prepare*` but the native ones, `quote`, `termSink`,
   `apply`, `shapeAnnotations`), the allocation family, `Reflection.lean`, `Typed.lean`, `Core.lean`'s
   evaluator (its line check is `Delvetalk/JsonLine.lean`), the cache's hit counters and
   `FrontEnd.Parsed.expandedSource`. Kept: `Theory.ObjectiveBendNativeDataSimulation`, whose three
   theorems are about the live machine's native cells. PROOF_ONLY is four modules.
4. Located refusals from the generics pass (§16 item 9). Every `refused (…)` of the derivation probe
   now carries `module` and `span` (`derivedAt`, `throwThe Refusal`): `fixed` at the declaration whose
   write names the field; `derived-edits` at the State field whose type the module cannot spell, or at
   the State; `form-kind` at the form field; `form-input` "declares" at the module's clashing
   declaration; `derived-forms` and a form-input parse failure at the first form block. Every other
   refusal of the pass (world calls, inference, unknown types, the instance bound) is placed at the
   declaration being rewritten (item 2). `test_sugar.Sugar.test_each_derived_refusal_names_its_source_line`
   checks through `compile`, which does not localize, so the span is the pass's own.
5. `textWords`: no object or design document asks for it (grep of docs/ and world/); not built.

## 26. A computed refusal (lane/kernel16, after foundation 1de640d7; playtest 2's D6, HOST-HANDOFF 5.157)

`refuse(...)` took one string literal, so a card could not refuse with the reading it computes: Card's
`refusing` said `refused <clause>: <reading>` with `tell` and the turn was admitted (the post read
refused and `● admitted` at once). Now the reason is a term and the refusal is the card's class:

- **Term.** `Term.refuse (reason : Term)`; `refuse("why")` is `.refuse (.label "why")`. The literal-only
  path is gone. No hidden world call: the refusal belongs to the term.
- **Reference.** `Step.refuseReason` evaluates the reason under `refuse`; no rule moves `refuse (label s)`:
  the program has refused with `s` (`refusal_reason_computed`). `SourceFrame.refuse` and `Yields.refuse`
  mirror the congruence (`yields_no_step`, `yields_deterministic` cover it).
- **Typing.** `PartialTyping.refuse` takes the reason's derivation at `String` and its uses
  (`computed_refusal_accepted`, `natural_refusal_reason_refused`). The elaborator refuses a reason of
  another type by name: "refused (refuse-reason): refuse takes a String, the reason; this is Nat".
- **Machine.** `evaluate (.refuse r)` pushes `Frame.refuse` and evaluates `r`; a label returned to it
  stops with `.refused (.program s)`, any other value `.refused .wrongValue`
  (`refuse_evaluates_its_reason`: seven transitions for `a ++ b`). A literal refusal costs three
  transitions where it cost one. The frame holds no address; the collector, erasure, both checkpoint
  codecs (frame tag 22; term tag 26 is `[26] ++ reason`), V3's structural term hash, the round trips,
  the collector's simulation and the fast machine's `sizesAfter` cover it; `Term.freeIn`/`markFree`
  read the reason's variables.
- **Wire.** Packet `{"tag":"refuse","reason":TERM}`; evaluator array `["refuse", TERM]`: the three
  evaluators step the reason and are stuck at a value. Conformance `refusal_cases`: a literal, a reason
  computed from literals, one from a bound value, one read from a stored row (the machine holds the
  state stored and forces that one row), one past a yield, one not a String, one that never ends.
  1500 cases: 1493 of 1561 agree per evaluator, 68 known shared-effect, 0 unexpected.
- **Turn.** `Turn.Step.refused (reason) (ticksUsed)` and `Outcome.refused`: a program's refusal is an
  outcome, not an error string, so the host tells it from a kernel failure; `turn-start`/`turn-resume`
  answer `{status: "refused", reason, ticksUsed}`. `refusalText` keeps the machine's failures only.
- **Host.** Class `cardRefused` (binding, as `lawRefused`; HOST-HANDOFF 5.157): `Ops.cardRefusal` parses
  `refused <clause>: <reading>` (the clause one word, split at the first `: `), else clause `card` and the
  line whole; `object` is the card that refused (a callee's refusal refuses the whole turn); the reading
  is kept within `Limits.maxRefusalBytes` (4096, a law reading's size; `withinBytes` keeps the whole
  characters that fit, then `…`). Not `evaluation` (a kernel or host failure, transient, which a
  supervisor hears as `broken`) and not `lawRefused` (a law's or the host's authority clause, whose reading
  is public law text): a card's reading is computed and may carry state, so `publicRefusal` shows the
  class and root only. Replay edition 8.
- **Pins.** 174 of 788 compiled world entries moved packet (every one reaching a `refuse`, the
  `let label(x) =` expansions among them: the reason is a term on the wire); re-recorded. Source pins
  did not move.
- **Measured** (hbox, the base binary built from foundation 1de640d7 beside this one, alternated, three
  runs each): compiling all 788 world entries 7.8 to 8.8 s either way, artifacts 47,526,904 to 47,532,223
  bytes (+0.011%); `test_artifact_pins` with `test_tariff` 9.4 to 11.6 s base, 9.5 to 10.1 s new;
  `test_turn_world`, `test_chain` and `test_hub` 20.3 to 24.1 s base, 20.3 to 22.0 s new. No tariff pin
  moved.
- **Next (the objects lane, OBJECTS-HANDOFF D6).** `Card.refusing` becomes `refuse(refusalLine(refusal))`
  and every method that answers a refusal by `tell` refuses instead; `bell`'s `refused text: …` and
  Kind's `refused body: …` already parse; Record's "Only a weather …" is clause `card`.

## 27. One clause language: law, rule, want (lane/kernel17, after foundation 57d1c580; OVERHAUL §5 step 2)

The grammar is `Compiler/ObjectiveBendLaw.lean`'s module comment; this is what changed and what the host
does next.

- **One AST.** A line is a `Clause {modality, name, reading, condition}`; `Modality` is `law`, `rule
  (spell)` or `want (spell)`; a `Spell` is `parts`, each `text` or `hole TERM`. The three keywords share
  one condition language (`LawExpr`), so a rule's `when` and a want's condition are laws' conditions.
- **One reference arm per side.** `LawSide` is `new`, `old` or `cited "O"`: `LawTerm.field side F`
  (`new.F`, `old.F`, `"O".F`), `count side F filter` (`count("O".F where …)` too), and
  `LawPlace.list side F` / `.column side F C`, so `TERM in old.F.COL` (REACTION §4), `TERM in old.F` and
  `TERM in "O".F` are the same arm on another side. The former `LawTerm.old`, `LawTerm.count (of :
  LawTerm)` and `LawPlace.cited` are gone into it.
- **Added.** `TERM % INT` (`LawTerm.mod`, the integer at least 1, never negative; binds tighter than
  `+`); `>=` (`LawExpr.ge`); `"O" wants NAME` (`LawExpr.wants`, a root); `request.verb`
  (`LawFact.verb`); the kind `rule` 4 (`ObjectiveBendLaw.kinds` is the one table: `kindNumber` and the
  host's `Law.kindNames` read it, so `world-inspect`'s `requestKinds` lists `rule`). A comparison now
  needs one side reading the write rather than a reference first, so REACTION §5's `0 + 1 <= old.tended`
  and `"tide" == request.object` parse; `1 + 2 <= 3` and `"a" == "b"` refuse (`compareRule`).
- **Holes** are `{TERM}`, a term of the grammar that reads the write (`refers`); anything else refuses
  by name with the hole quoted: `` `{object}` `` and `` `{request.target}` `` (`holeRule`). OVERHAUL's
  `{object}` is spelled `{request.object}`: a hole is a reference of the one grammar, not a second
  vocabulary. `me` is not a hole; the host resolves it. A spell is one line starting `delvetalk `.
- **A want reads the thing as it stands.** `Clause.atRead` (over the condition and the holes): no
  `old`, no request fact but `clock` and `object`, no rule over old and new, no `changed`, no `under`;
  `admit` refuses the first such construct, `` `old.a` in a want `` (`wantRule`).
  `parsed_want_reads_as_it_stands` proves it of every line `parseClause` accepts (`#assert_axioms`,
  with `admit_ok` and `parseClauseSource_reads_now`).
- **One parser.** `parseClause`, `parseClauseSource` (the clause and the text after its `:` as written),
  `parseText` (blank lines aside; names unique across all three modalities, `checkNames` over names),
  `parseBody` (the text after `:` in a modality), `splitReading`. `tokenize` stops at `then` (a rule) or
  `asks` (a want) where it is not a field name, so a spell is never tokenized as a condition; a
  leftover `then`/`asks` names the modality that takes it (`joinRule`). The package parser's `lawRe`
  and the host's own line splitter (`parseLawTextReadings`) are deleted: both call the kernel. The
  Surface decl `.law` is `.clause keyword name source reading`; its JSON `kind` is the keyword, so a law
  decl's JSON is byte-identical. `ObjectiveBendElaborate.Module.clauses` and `Lowering.clauses` carry
  the entry module's text; `Module.laws`/`Lowering.laws` are its law projection (`lawsOf`).
- **One renderer.** `Clause.render` (`Lean.Json` quotes the reading); `Host.renderLaw` renders through it,
  byte-identical (`law NAME: EXPR`).
- **One walk.** `Clause.names` is the condition's names then the holes'; `fields`, `reads`,
  `fieldsPlain` project it for `LawExpr` and `Clause` alike. `LawName.cited object field` (its column
  is a `.column`), `LawName.want object name`.
- **Theorems** (`native_decide`, `#assert_compiled`): `parse_accepts`, `parse_refuses`,
  `render_reads_back` (conditions, the new arms among them); `parse_clauses` (REACTION §5's six rules as
  typed from a card, the bell's `rings`/`rang`, OVERHAUL's `water`, `daily`, `rests`, four wants),
  `parse_clauses_refuse` (35 malformed lines), `clause_render_reads_back`; `text_holds_three_modalities`
  (one text: laws, rules and wants keep their modalities, `under` an atom of each, `lawsOf` the laws,
  duplicate names refused); `refusals_name_what_and_why` (every new rule in the one shape);
  `names_walk`. `#assert_axioms`: the three above.
- **`Host/Law.lean`.** `Facts.verb` and `Facts.wants` (the want clauses of each object cited by `"O"
  wants`); `read` over every side and `%`; `denote` for `>=`, the sided memberships, `"O" wants N`
  (the want's condition on the cited state, `old` none, `asItStands` facts, depth − 1) and a text
  constant on either side of `==`. Rules and wants are judged by the same `denote`: `fires` (the rules a
  write makes hold), `poses` (the wants that hold of a state as it stands), `fill` (a spell's holes at
  the write; none when a hole reads nothing), `followed` (the rules and wants a law's `under` citations
  carry, with the carrying object, through the cited texts' own `under`, each once), `citations`.
  `parseClauses` is the text with its bounds; `parseLawText`/`parseLawTextReadings` its law clauses, so
  every existing caller judges laws only. `#guard`s for each arm, REACTION §5's `two`, `next` and
  `company`, a want's clock, a filled spell, and a kind carrying its rules through `under`.
- **Host files touched**, mechanically: the five `Law.Facts` built by anonymous constructor (Ops
  `amendable`, `libraryRefusal`; TurnLoop layer, `methodAdmits`, `kindAdmits`) are named-field
  instances, so a growing `Facts` never breaks them again; `judge` and `methodAdmits` set `verb :=
  method` (a declared method is its own verb). `tests/test_law.py`: `requestKinds` lists `rule`;
  `Atoms.test_one_text_holds_laws_rules_and_wants_and_its_laws_judge` (a kind's text and an instance's
  holding all three; `%` and `request.verb` refuse by name at a real write; a want reading `old` refuses
  the text).
- **Pins unmoved**: grammar only; no packet or source pin changed (`test_artifact_pins` green). Rules
  and wants written in a text today parse, render, round-trip and are carried; nothing fires or poses
  until step 3.

**The host's step 3, exactly** (lane/host after host21; HOST-HANDOFF):

1. `Object.rules`, `Object.wants : List {name, owner, since, line}`. `world.rule {object, name, when,
   then}` builds `rule NAME: WHEN then THEN` and parses it with `ObjectiveBendLaw.parseClause` (`want`:
   `want NAME: WHEN asks ASKS`), refusing by the parser's message; the name unique against the text's
   clauses and the placed rows (`checkNames`). The placement is judged by the object's law with `Facts
   {kind := 4, subject, caller, verb := "", …}` (`request.kind == rule`). `unrule`/`unwant` by the
   placer or the owner. Rows journaled; replay re-parses them.
2. Following: the rules and wants an object carries are its placed rows, then `Law.followed (reads)
   o.law` (the kind's lines through `under`, owned by the carrying object's owner). `Ops.lawCitations`
   closes over `Clause.reads` of every carried rule and want too (their `"O".F`, `"O" wants`, holes), so
   their states are roots of the write; `Facts.wants` is, for every object a carried clause or a law
   cites by `"O" wants`, that object's placed wants then its `followed` wants.
3. Commit, after `judge` admits each written object: `Law.fires facts (some old) new rules` with the
   same `Facts` as its law (so `request.verb`, `request.kind`, `request.clock` read alike); for each,
   `Law.fill facts (some old) new spell`: none is `unfired` (a hole read nothing), else `me` resolved to
   the owner's avatar and `receive {text}` staged under the owner, identity
   `rule:<object>:<name>:<height>`; `rulesPerCommit` 8, `rulesPerObject` 32, `ruleDepth` 4, judged
   under `ruleTicks` = `lawTicks`. `fired`/`unfired` journaled and re-derived on replay.
4. Wants: `Law.poses facts object state wants` at the clock, on the old state and on the new at commit
   (the `wanted`/`unwanted` diff, `since` the height that made each true) and on the state as it stands
   at every read (`wants {object}`); a want's spell filled with `Law.fill (Law.asItStands facts object)
   none state spell`.
5. `request.verb`: `act {verb, text}` sets `verb` to the grown verb (method `act`); every other write
   already sets it to the method.
6. Delete `Law.lawReading` and `Ops.lawClauses`' line splitter: `lawRows` reads `parseClauses o.lawText`
   and lists every clause with its keyword, so `world-inspect` and `rules`/`wants` show rules and wants.
7. `Limits.maxLawClauses` (16) now counts a text's rules and wants; a kind carrying laws, rules and wants
   may need it raised (placed rules are bounded by `rulesPerObject`, not by it).
8. A package's top-level `rule`/`want` lines are parsed, checked and carried to `Lowering.clauses`;
   `Package.EntryCompiled` should carry them to `Built` so `makeObject` places them (owner the
   creator) when no law text is given. (Objects lane: `Kind.obend`'s `lawChecked` still refuses lines
   not starting `law `; `world.check` accepts `rule` and `want` lines now.)
