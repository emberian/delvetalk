# Kernel handoff (lane/turn, lane/kernel2, lane/kernel3)

For the next agent changing the language, the turn machinery or the wire. Paths are relative to
the repository root; line numbers are for foundation 62b7dfd and drift. Everything below was read
from source or measured; "unproved" means I left it so, and says what would prove it.

## 0. Working rules that bite

- Build: `LEAN_NUM_THREADS=2 lake build 2>&1 | tail -30` (one Lean process). The only binary is
  `.lake/build/bin/delvetalk-obend`. Never rebuild while a test run is using it: `tests/host.py`
  copies the binary into a temp dir per run for exactly this reason (`DELVETALK_OBEND` names the
  source, `DELVETALK_OBEND_COPY` shares one copy across workers; `tests/run.py` is the parallel
  runner). A suite started before a rebuild with a bare path races it.
- Narrow tests first: `python3 -m unittest tests.test_turn`, `tests.test_canonical`,
  `tests.test_conformance` (10 s), `tests.test_document`, `tests.test_data_type`. The whole suite is
  576 tests: `DELVETALK_OBEND=$PWD/.lake/build/bin/delvetalk-obend python3 -W ignore -m tests.run`
  (parallel, 91 s wall on hbox at 9246901), or `python3 -m unittest discover -s tests -t . -p "test_*.py"`
  (serial, ~300 s).
- Builds may run on `hbox` (24 cores): rsync the tree without `.lake` to `~/scratch/<dir>`,
  `swarm-build lake build`, run the tests there with `DELVETALK_OBEND` pointing at its binary.
- Commits: name files (`git add <paths>`), message via `git commit -F file` (zsh eats backticks),
  end with the Co-Authored-By line. 1Password sometimes refuses to sign ("failed to fill whole
  buffer"): commit unsigned with `git -c commit.gpgsign=false commit ...`; unsigned means
  "made while ember was away". Never stash, never `git add -A`, never push.
- Host files belong to the host lane (`spec/Delvetalk/Host/*`). I touched `TurnLoop.lean`,
  `Store.lean` (one comment) and `Journal.lean` only because signatures or hashing changed; expect
  the host lane to have moved the rest. `Journal.lean` is the one I own.
- Lean 4.34: `if_pos`/`if_true`/`if_false` deprecation warnings in old Mini files are noise. A
  doc comment (`/-- -/`) directly before `mutual` is a parse error: use `/- -/`. Inside a file
  that has `open ...ObjectiveBendTypes`, a pattern variable called `label` is read as the `Ty.label`
  constructor ("Not enough arguments to `label`"): rename it. `x.isDataUnder a b c d` puts `x`
  at the FIRST `Ty`-typed parameter; with several `Ty` parameters call it explicitly. macOS
  `sed -i` needs `-i ''`; I used python for edits.
- Background/timeouts: a foreground command dies at 120 s; run suites with `&` into a file under the
  scratchpad and poll the file once.

## 1. Map of the language (spec/bend, spec/Delvetalk)

Pipeline for `compile`: source text -> (document templates, text) -> `ObjectiveBendParse` ->
`Surface.Module` -> generics (on Surface) -> `ObjectiveBendElaborate.ofSurface` -> elaboration
-> `ATerm` + typing proposal (`propose`, Lean data) -> closure check on the direct source
(once per package) -> per entry: packet JSON -> `decodePacket` -> `Typing.check` -> artifact.
JSON exists only at the process boundary and in the entry packet (see §10).

| Stage | Where | Notes |
|---|---|---|
| Surface AST | `spec/bend/Compiler/ObjectiveBendSurface.lean` | Typed AST with a `Span` on every node; `Module.json` renders the old `dregg.objective-bend.module.v1` JSON byte for byte (only `source-imports-v1`, import transcripts, interface labels and diagnostics use it). Type annotations are still source TEXT (the elaborator and generics parse type text with their own refusals). |
| Surface parser | `spec/bend/Compiler/ObjectiveBendParse.lean` (884) | Produces `Surface.Module`. `Diagnostic{message,span}`. Strings use JSON escapes (`json.dumps` is a valid literal). Declarations: `record`, `sum`, `type`, `def` (kind `function`; `signature.name`, `body.span`), `law`, generics `<T>`. |
| Hosted front end | `spec/Delvetalk/FrontEnd.lean`, `Generics.lean` (398), `DocumentTemplate.lean` (218) | `parseSource name src` = template expansion (a text pass) + parse, spans mapped back by `Expansion.remap` (`Surface.Module.mapSpans`); `lowerWithInstances` runs `Generics.run` (rank-1 specialization: generic *sums* and *defs*; generic *records* do not parse), then imports/lowering. Doc literals need an explicit `import ./Document.obend as X`. |
| Elaborator | `spec/bend/Compiler/ObjectiveBendElaborate.lean` (2340) | `ofSurface` reads a `Surface.Module` into the elaborator's span-free core AST (`Expr`/`Body`/`Decl`; `Param` and `Pattern` are the Surface types). Source -> annotated core (`ATerm`). Errors are bare strings in `StateT St (Except String)` (`fail`, `typeError`): NO position. That is why `Package.localize` exists. `Activity<P,R,A>` is parsed at ~l.756; `perform`/effect-mode lowering l.1137, 1537; `noActivity` (l.1234) is the "effect in shared position" refusal. Recursive record/sum = `Ty.variable i` + a bound. |
| Front-end driver / `accept` | `spec/bend/Compiler/ObjectiveBendFrontEnd.lean` (336) | `Diagnostic{stage,message,span,sourceModule}`; stages: `objective-source-parse`, `objective-core-elaboration`, `objective-typed-check` ("the checker refused the front end's typed packet": no detail), `document-template`. `accept` (l.~300-329) decodes the packet and calls `check`. |
| Term wire | `spec/bend/Compiler/ObjectiveBendTermWire.lean` | `ATerm.json` <-> `Typing.decodeTerm` (object form `{tag,...}`). The evaluators' array form is different (see 6). |
| Core terms & reference relation | `spec/bend/Theory/ObjectiveBendOpenRecursion.lean` (660) | `Term` (23 constructors incl. `unary`, `inject`, `case`, `ifBool`, `perform`, `done`), `Primitive` (15), `UnaryPrimitive` (3: natText textLength sha256Text), `primitiveResult`, `unaryResult`, `inductive Step`/`Steps`/`Yields`, `Value`. The DelveTalk-only parts (text prims, `unary`) are marked "hosted extension, not upstream". |
| Types | `spec/bend/Theory/ObjectiveBendTypes.lean` (318) | `Ty` (variable, arrow, row `field`/`emptyRow`, variant, computation...). `isDataUnder bounds rigid fuel seen` / `isPlanUnder` (mine): non-rigid variables unfold through the packet's `bounds` as a greatest fixed point (`seen`). `Ty.isData`/`isPlan` = empty bounds. `Ty.dataFuel = 4096`. |
| Typing rules + checker | `spec/bend/Theory/ObjectiveBendTyping.lean` (1486) | `inductive PartialTyping` (l.199: the rules; `perform` l.~306), `infer` (l.369), `check` (l.657), `decodePacket`/`decodeTerm`. `Assumptions{bounds, shareableVariables, rigid}`. `typeJson` l.~1263. |
| Demand machine | `spec/bend/Theory/ObjectiveBendDemandMachine.lean` (343) | `State{heap,control,stack}`, `Cell` (suspended/evaluating/cached/native/nativeCached), `Frame`, `Control` (incl. `yielded`, `nativeApplication`), `stepRaw` (l.134), `runBounded`, `resume`. `Fast.lean` is a proved-equal faster stepper (`stepRawFast_eq_stepRaw`, `runFrom_eq_runBounded`). |
| Data extraction, tariff | `spec/bend/Theory/ObjectiveBendDemandData.lean` (358) | `Data`, `textStepCost` (l.84), `forceHostedFrom` (l.~110: tick+byte admission before each step), `materializeWith`, `executeStateWith`, `yieldedPlanWith`, `Data.conformsFuel/conformsUnder/size` (mine). `Data` itself is in `ObjectiveBendFiniteData.lean`. |
| Checkpoint codec | `spec/bend/Theory/ObjectiveBendCheckpoint.lean` (366), `ObjectiveBendDemandCollect.lean` (237) | Ported from `/Users/ember/dev/minidregg/Theory/`. `encodeState/decodeState` (tokens), `settle`/`collect`/`checkpoint = collect (settle s)`. Token = `.nat n | .text s`, JSON `{"n":"3"}` / `{"s":"x"}`. Edition tag `dregg.objective-bend.checkpoint.v1`. |
| Laws | `spec/bend/Compiler/ObjectiveBendLaw.lean`, `spec/Delvetalk/Host/Law.lean` | `law NAME: EXPR` over declared state; pure profile refuses laws ("host law adapter"). |
| Typed data/schema | `spec/Delvetalk/PackageData*.lean` | `run-data-v1`, compact codec, schema certificates, `inspect-spec-v1`, `compare-data-types-v1`. Separate from Turn; its depth is `Bounds.dataWireDepth`. |
| Package / session / main | `spec/Delvetalk/Package.lean` (552), `PackageSession.lean`, `spec/PackageMain.lean` | JSON-lines driver; see 2. |
| Source evaluator (executable relation) | `spec/Delvetalk/Core.lean`, `Typed.lean` | Older step-by-step evaluator with evidence; not on the turn path. |

Proof guards. `lake build` builds the default target, which is ONLY what `PackageMain`
imports: `Delvetalk.PackageDataAdmission`, `PackageDataNormalization`,
`PackageDataSchemaProofs`, `Delvetalk.Typed` and `Theory.ObjectiveBendNativeDataSimulation` are
not built by it; name them (`lake build delvetalk-obend Delvetalk.PackageDataAdmission ...`)
after touching anything they import. There is no `sorry` in `spec/` (the AxiomPin files pin
axiom sets in Fast/Cshake files). What each change must keep:
- Changing `Term`/`Primitive`/`Step` (OpenRecursion): `Step` lemmas there (`lazy_fixed_function`,
  `case_selects_injected_arm`, the primitive-exactness lemmas) and the `Value` ones; then Typing's
  `PartialTyping` mirrors every constructor.
- Changing a typing rule (Typing, 73 theorems): `checked_erasure`, `agree_sameType`,
  `partial_beta_law`, `reusable_lambda_capture_rule`, `sameType_isComputation`, and the `decide`d
  rule examples at the end of the file (l.~1418-1480: `perform` outside an activity, in a field,
  in a let, plan-is-a-sum...). Those examples are the regression suite for effect rules.
- Changing the machine: `resume_requires_yield`, `resume_keeps_heap_and_stack`,
  `perform_under_update_refused`, `perform_yields` (Machine) and the whole `Fast` equivalence file
  (any change to `stepRaw` needs the matching `stepRawFast`/`sizesAfter` change or `stepFast_eq_step` fails).
- Native cells: `ObjectiveBendNativeDataSimulation.lean`, `FiniteDataTyping.lean`.
- Schema/compact codec: `PackageDataSchemaProofs.lean` (7 theorems).

What is proved now (kernel lane 2, see also section 8), and what is not:
- `state_roundTrip : decodeState (encodeState s) = some s` for this edition's codec
  (`Theory/ObjectiveBendCheckpointRoundTrip.lean`; native cells, native frames,
  `nativeApplication`, unary, `toData`, `textJoin` and the join frames all have cases). A new
  machine constructor without its codec case now fails the build.
- `settle_resume_segment` and the agreement lemmas behind it on the hosted runner
  (`agree_forceHostedFrom`, `agree_materializeWith`, `agree_yieldedPlanWith`, `agree_completeWith`;
  `Theory/ObjectiveBendDemandSettleProofs.lean`). NOT ported: `typed_settle` (no state-typing
  judgment in this edition).
- The collector (kernel lane 3, `Theory/ObjectiveBendDemandCollectProofs.lean`): `related_collect`
  (no reachable address dangles), `related_stepRaw` (every constructor of this machine),
  `related_forceHostedFrom` (the hosted runner, exact under `ExactRoom`, which `limitsPast`
  gives), extraction agreement, and `checkpoint_resume_segment`: resuming
  `checkpoint s = collect (settle s)` decides the same verdict, spends the same ticks and extracts
  the same Plan/result Data as resuming `s`. A new frame, cell or control holding addresses must be
  added to `frameAddresses`/`cellAddresses`/`controlAddresses` and the renamings, or
  `related_stepRaw` stops building. Mini's typing transfer is not ported (no state typing).
- `conformsUnder_iff : d.conformsUnder bounds ty = true ↔ HasType bounds d ty`
  (`Theory/ObjectiveBendDataConformance.lean`): runtime conformance is sound and complete at the
  fuel the code uses; fuel is never a false negative (`short_chain`, a pigeonhole over the bounds'
  keys). No `isDataUnder` hypothesis is needed.
- Not proved: that the elaborator's `noActivity` is the static guard matching
  `perform_under_update_refused`; that `textJoinExpansion` and the machine's join frames agree
  (tested by conformance on values only).
- `Data.conforms` once accepted `{}` for any non-row type; fixed (requires `.field`/`.emptyRow`).

## 2. Ops (spec/Delvetalk/Package.lean `job`, PackageSession.lean `step`, Host/Session.lean)

Wire: one JSON object per line on stdin, one per line out. Errors: `{"status":"error","message":s}`.
`PackageSession.step` caches compiled artifacts per process (8 MiB, `compile` memoized by request).
For a request whose `artifact` equals a cached one, `run`, `run-data-v1`, `turn-start`,
`turn-resume` skip recompilation (`*Verified` entry points); otherwise `job` calls `verifyArtifact`
(recompile and compare). `world-*` ops go to `Host.stepWorld` (Session.lean) when a world is open.

| op | takes | returns |
|---|---|---|
| `compile` | `modules:[{name,source}]` (or `source`), `entry`, `limits?` | `{status:"compiled", artifact}`; artifact = `{schema, modules, sourcesSha256 (CID), entry, genericInstances, limits, packet, packetSha256 (CID), type}`. Error message is the diagnostic JSON text for compiler refusals, plain text for request refusals. |
| `check-package` | as compile | `{status:"checked", artifact}` or `{status:"refused", diagnostic:{stage,message,module?,span?}}`. Structured; `Package.checkPackage modules entry` is the pure Lean entry. Spanless refusals are localized by `localize` (recompiles each function alone; first with the same stage+message wins; span = that function's BODY start line). |
| `run` | `artifact`, `arguments:[Data wire]`, `limits` | `{status:"finished", value, type, ticksUsed, heapCells, nodesUsed}` or `{status:"refused", failure, ...}`. Entry type must be first-order data (activities refused: "package result must have first-order data type"). Arguments: scalars/records/lists, variants refused in `run` (not in turn-start). |
| `turn-start` | `artifact`, `arguments`, `limits?`, binding: `object`, `principal`, `intent`, `roots:[{object,version}]` (ALL required) | `{status:"finished", value, type, ticksUsed}` / `{status:"yielded", plan, planType, responseType, checkpoint, ticksUsed}` / `{status:"exhausted", resource, ticksUsed}` (resource in ticks heap stack nodes bytes) / `{status:"error"}`. Entry must type as `Activity<P,R,A>` after applying arguments with P a sum, R and A data (recursive sums allowed). |
| `turn-resume` | `artifact`, `checkpoint`, `response` (Data wire, variants allowed), `limits?`, the same binding | same replies. Checks in order: entry is an activity; `packetSha256`; digest; object; principal; intent; roots ("checkpoint belongs to another package / digest mismatch / another object / another principal / another intent / was taken under different roots"); decode ("checkpoint does not decode"); response conforms; control is yielded. Response type is re-derived from the artifact, never taken from the client. |
| `evaluate-term` | `term` (array wire, see 6), `responses?`, `ticks?` | `{result:{status: value\|yield\|exhausted\|stuck, shape, plans}}`. Pure reference for conformance. |
| `render-document` | `document` (Data wire) | `{status:"rendered", text, lines, bytes}`; exactly Bend `Document.plain`/`lines`; limits documentDepth/Nodes/OutputBytes. |
| `canonical-encode` | `data` (Data wire) or `json`; `repeat?` | `{cid, hex, bytes, checksum}`. `repeat` re-encodes n times (timing without JSON framing). |
| `canonical-decode` | `hex` | `{data, cid}`; canonical-only. |
| `source-imports-v1`, `template-expand` | modules / source | import edges; expanded document-literal source. |
| `run-data-v1`, `run-compact`, `encode-compact`, `decode-compact`, `inspect-spec-v1`, `compare-data-types-v1`, `allocation-data-types-v1` | typed-schema family (PackageData*) | see PackageData.lean headers; the host uses them for allocation/schema admission. |

Turn API in Lean (`spec/Delvetalk/Turn.lean`, the host calls these, not JSON):
`startActivity packet args binding budgets : Except String Outcome`,
`resumeActivity packet checkpoint binding response budgets`. `Outcome = finished | yielded |
exhausted resource ticks`. `Binding.make object principal intent roots`. A checkpoint carries the
binding it was made under and resumes only under the same one; the roots digest is the roots at
the START of the activity, not at the latest yield. `exhaustedResource` classifies machine
failures: ticks; capacity suspension -> heap/stack by simulating one more `stepRaw`, else bytes;
`budget` on a yielded Plan is exact (re-extracts with unlimited nodes), on a finished result it is
a heuristic (nodes if none left, else bytes) and can mislabel. Budget fields: `Budgets{ticks,heap,
stack,nodes,bytes}`, parsed from `limits` strings or numbers with ceilings from Limits.lean.
Resume limits: heap is counted PAST the checkpoint's own heap (`limitsPast`).

Annotations: injecting a variant argument/response needs per-injection lambda annotations
(`annotateData`, Turn.lean); the checker rejects an unannotated `inject`. `dataTerm` turns Data into
a Term; `Data.variant l p` -> `Term.inject l p`.

## 3. The wire and the canonical form

Data JSON (`spec/bend/Compiler/ObjectiveBendDataWire.lean`): `{"tag":"natural","value":"123"}`
(decimal STRING), `boolean`, `label` (value), `record {fields:[{name,value}]}`,
`variant {label,payload}`, and lists: `{"tag":"list","items":[...]}`. `dataJson` emits `list`
whenever `listItems?` finds a proper chain (`nil{}` / `cons{head,tail}` ending in nil, fields in
either order). `decodeData` accepts `list` and refuses a variant chain that forms a proper list:
"cons chains are no longer accepted on the wire; send a list" (`consChainRefusal`); a `cons` whose
tail is not a list stays an ordinary variant. PackageData's strict wire (`PackageData.decode`)
applies the same rule and reads `list` too. Decode depth
is by NESTING: `decodeData fuel` spends one fuel per record/variant/list level, not per element
(`Bounds.dataWireDepth = 256`; chains still cost 2 levels per cell, arrays do not). A decoded list
becomes a `cons` chain in memory (deep structure; fine to 5,000+, functions over Data are `partial`).
`dataJsonBytes` must equal `(dataJson d).compress.utf8ByteSize` (checked by hand; keep in sync).
The tests send and read arrays; the `relist` shim is gone.

Canonical bytes (`spec/Delvetalk/Canonical.lean`, DAG-CBOR as AT Protocol):
- unsigned int, shortest head (24/25/26/27 widths); Nat >= 2^64 -> byte string, big-endian, no
  leading zero; false/true = f4/f5; label = text; JSON null = f6; list = definite array;
  record = definite map, keys sorted by UTF-8 byte LENGTH then bytes, a repeated field keeps the
  first; variant = one-key map `{label: payload}`.
- Untyped decode turns every one-key map into a RECORD (a variant and a one-field record are
  indistinguishable in bytes); `decodeAs bounds ty bytes` re-tags against a type (`retype`).
  Round trip is therefore `decode (encode d) = normalize d` for variant-free `d`, and byte
  fixed-point (`encode (decode b) = b`) for everything. Not exposed on the wire; not proved.
- `decode` refuses non-shortest heads, unsorted/duplicate keys, indefinite lengths, tags, floats,
  null, negative ints, non-canonical bignums, bad UTF-8, trailing bytes: by-name messages
  ("non-canonical CBOR: ...", "CBOR nesting capacity", "CBOR exceeds the node bound").
- JSON as CBOR (`encodeJson`): objects->maps, arrays, strings, bools, null, ints; a fraction is
  refused; negative ints are major 1.
- CID = `"b" ++ base32lower(0x01 0x71 0x12 0x20 ++ sha256(bytes))`, 59 chars, `bafyrei...`.
  `cidJson` is total (falls back to the CID of the printed text on an unencodable value).
- Verified: all 166 `record`/`cid` pairs in `tests/fixtures/delve/*.json` encode to the AppView's CID,
  and `tests/wire.py` holds an independent Python encoder used to recompute journal CIDs.

Where digests are made and checked:
- Journal: `Host/Journal.lean` `bodyHash = cidJson`; `sealEntry` sets `hash` = CID of the body
  (height, previous, fields) without `hash`; `verify height previous entry` names
  "journal broken at height N: hash mismatch | height out of sequence | previous hash does not chain".
  `previous` of height 1 is `Limits.genesis` = 64 zeros (Store.lean; not a CID).
  The host also uses `bodyHash` for request digests, retry identities, seed digests (all CIDs now).
- Artifact: `packetSha256`, `sourcesSha256` (Package.compileStructured). Per-module source hash
  inside the packet is still hex SHA-256 of the raw source (frontend-owned, `Package.modulesOfStructured`).
  Names say Sha256, values are CIDs: field names were kept on purpose.
- Checkpoint: `Turn.checkpointDigest` = CID of JSON `{packetSha256, object, principal, intent,
  rootsDigest, tokens}`; `rootsDigest` = CID of `[{object,version}]`; `tokensDigest` = CID of the
  token JSON. Verified in `resumeActivity` before any decoding.
- Pins (`Host/Ops.lean`) = `packetSha256`.

## 4. Limits (spec/Delvetalk/Limits.lean, namespace `Delvetalk.Bounds`)

Per machine segment (default / ceiling): `ticks` 100k/1M (work); `heap` 100k/1M (cells);
`stack` 10k/100k (frames); `nodes` 100k/1M (Data nodes materialized for a result or Plan);
`bytes` 1 MiB/16 MiB (encoded result/Plan bytes AND the largest single text-primitive allocation
reserve per step). `typeFuelDefault` 16384 (checker fuel stored in the artifact).
Wire: `dataWireDepth` 256 (args/responses/CBOR nesting), `plainJsonDepth` 64 (`jsonData`/`dataPlain`),
`documentWireDepth` 8192 (documents and canonical-encode input), `entryArrowDepth` 64 (parameters
peeled to find the activity). Packages: `maxModules` 64, `maxModuleBytes` 512 KiB,
`maxPackageSourceBytes` 1 MiB (import scan only). Documents: `documentDepth` 64, `documentNodes`
65,536, `documentOutputBytes` 1 MiB, `offersPerTurn` 16 (their text shares the 1 MiB).
Not yet in the file: `PackageMain` 16 MiB line frame, `PackageSession` 8 MiB cache,
`EvaluateTerm` (nesting 4096, 200k ticks), `Canonical` reuses `nodesMax`/`bytesMax`, and the host's
own `Host.Limits` (Store.lean) still holds its copies (`dataDepth` 64, `maxTurnTicks`, `maxPackageBytes`
32 KiB for reprogram). `Document.maxOffersPerTurn`/`maxOutputBytes` are aliases kept because
`TurnLoop.lean` reads those names. Fuel parameters that are not budgets: `Typing.check` fuel
(packet `fuel`), `Ty.dataFuel` 4096, `termNestingCapacity` 4096 (`decodeTerm`), `conformsFuel`,
`runBounded` ticks in `evaluate-term`, `go 64` yields cap in `EvaluateTerm`, `peelArrows`.
A fuel exhaustion is a refusal, never a wrong answer, but it looks like a type error.

## 5. The tariff (what costs what) — `textStepCost` / `forceHostedFrom`, DemandData

Every machine transition costs 1 tick. Before a text primitive runs, `forceHostedFrom` admits
`(ticks, bytes)` from `textStepCost` and suspends (`ticks` or `capacity`) if either exceeds what is
left; the state is retained exactly. Charges (B = byte size of the operand, n = count, p = exact
bytes of the first n scalars, found by a scan bounded by what the allowance can pay, `prefixCost`):
- `textConcat a b`: `1 + 2(|a|+|b|)`, reserves `|a|+|b|`.
- `textTake t n`: `1` if n=0 or n>=B; else `1 + 2p`, reserves `p`.
- `textDrop t n`: `1` if n=0 or n>=B; else `1 + 2p`, reserves `B - p` (the suffix is COPIED:
  `String.Slice.toString` is `lean_string_utf8_extract`; that copy is bounded in bytes, not charged
  in ticks, so a drop-by-one walk stays linear).
- `textJoin list sep` (each element): `1 + 2*(bytes appended)`, reserves the new accumulator. The
  accumulator lives in the `joinList`/`joinHead` frame and is appended in place when unique.
- `textSpan/textBreak`: `1 + perScalar*visited`, perScalar = `2*(|alphabet|+2)`; refused up front
  if the cap cannot cover the scan (spends the allowance, returns 0 credit).
- `textLength`: `1+B`. `sha256Text`: `65 + 8*ceil(B/64) + 32*blocks`. `natText n`: `1 + bits^2`.
- Everything else: 1 tick.

Measured (`tests/test_tariff.py` pins them exactly; update with a reason when they move):
bump turn 56 + 10; 64-field spell parse 97,355 -> 56,957 (19,971 transitions either way: take/drop
were 4 bytes per scalar); `Document.plain` over 1,025 leaves 336,659 -> 129,272 (9,235 beyond a
`Document.size` walk of the same document); 1,025-rain Bell card 848,680 -> 333,209.
Profile any run with `"profile": true` on `run`, `turn-start`, `turn-resume` (`Delvetalk/Profile.lean`:
ticks per `evaluate.<term>` / `enter.<cell>` / `returned.<frame>`, primitives named). The spell
parse was 81% text primitives and 19% interpretation, so interpreter tricks (argument frames, field
lookup caches, rename) cannot buy 30% there; check the profile before optimizing the interpreter.

Remaining quadratic idioms: `Lists.append xs x` in a loop; `Lists.length` in a loop; left folds of
`textConcat` (use `textJoin`); character walks with `textDrop` copy the suffix each step (bytes,
not ticks).

## 6. Evaluators and conformance (impl/, tests/conformance, tests/test_conformance.py)

`impl/python/evaluator.py`, `impl/js/evaluator.mjs`, `impl/c/evaluator.c` are independent
small-step, call-by-name interpreters of the core. Input line: `{"name","term","responses","fuel"}`
(no other keys); output `{"name","status": value|yield|exhausted|stuck,"term","plans"}`. Term
array wire: `["bound",i] ["nat","12"] ["boolean",b] ["label",s] ["lam",b] ["app",f,a] ["mix",l,u]
["fix",s,i] ["specification",m,e] ["prototype",s,t] ["reflect"|"metadata"|"project"|"perform"|"done",x]
["unary",prim,x] ["binary",prim,l,r] ["get",x,name] ["inject",label,x] ["ifZero",v,z,s] ["ifBool",c,t,f]
["record",[[n,t]..]] ["extend",x,fields] ["case",x,arms]`. An evaluator that rejects a line STOPS its
stream (nonzero exit); the runner restarts after it and counts the line as `rejected`.
I added `unary` and the five text binary primitives to all three (code-point semantics; `textTake`/
`textDrop` use the byte-size guard `n >= byteSize`; C has its own SHA-256). `perform` yields:
`status:"yield"` with `plans`, resumed from `responses` in order.

Harness: `tests/conformance/generate.py` (seeded, kind-directed generator; kinds: term, activity,
stuck, diverge, shared-effect, exotic-value, chain; sizes to ~990 nodes; asserts every tag and
primitive occurs), `tests/test_conformance.py` (runs `evaluate-term` on the machine and each evaluator,
compares status, weak-head shape (record: field names only), and Plans when literal data). Report:
agree counts per evaluator and the smallest disagreeing case per constructor.
`python3 -m tests.test_conformance 1500 [IMPL_DIR]` prints the report for another copy of impl/.
Before my fixes 202/400 agreed (every text/unary term was rejected); after, 390/400 with 10
`KNOWN_DIVERGENCE["shared-effect"]` cases and 0 unexpected (1455/1500 on a larger run).
Kernel lane 2 added `toData` (identity) and `textJoin` (stepped to `textJoinExpansion` by all
three evaluators; the generator emits joins over list literals, some malformed): 377/400 agree,
23 known shared-effect, 0 unexpected; 1436/1500 on the larger run.
Known divergence: a `perform` reached while forcing a SHARED argument cell. The machine refuses it
(`Refusal.sharedEffect`, `perform_under_update_refused`); call-by-name evaluators substitute and
perform at each use. Typed programs cannot reach it (`noActivity`). Machine `divergent` (blackhole)
and tick/capacity suspension all map to `exhausted`. Not compared: step counts, deep values
(record fields), plans that are not literal data, Nat formatting beyond canonical decimal.
When adding a Term form: extend `generate.py` (and its tag assertion), `EvaluateTerm.termOf`, the three
evaluators' validators/arity tables/`reducible`, run the report, and decide fix vs `KNOWN_DIVERGENCE`.

## 7. Other facts worth knowing

- `Package.localize` assumes functions are independently compilable as entries; a generic entry
  fails differently and is skipped. It costs one compile per function and only runs in `check-package`.
- `EvaluateTerm` and `Turn` run pure `Except` code; timing a pure op needs the `repeat` trick (see
  `canonical-encode`) or an IO wrapper in `PackageMain`.
- Host-side resume of suspended activities rebuilds the `Checkpoint` from journaled tokens plus the
  activity's object/principal/intent/roots (`resumeOne` in TurnLoop); if you change `Checkpoint`'s
  fields, journals written before the change stop resuming (no migration exists).
- Checkpoints contain the whole program heap (hundreds of tokens even for `bump`); `collect` only drops
  unreachable cells. A size-aware checkpoint (share the program, store only mutable cells) would cut
  journal bytes a lot but changes the binding story.
- `Outcome.exhausted` is a silence, not an error; the host currently maps it to a refused turn with
  message "turn refused: <resource> budget exhausted"; journaling class `budget` is host work.
- Related docs: `docs/FOUNDATION.md` (design), `docs/HOST-HANDOFF.md`, `docs/OBJECTS-HANDOFF.md`.

## 8. Kernel lane 2 additions (2026-10-09)

- Universal type `Data` (`Ty.data`, `Term.toData`, surface `Data.of::<T>(value)`): any well-formed
  first-order data (`Data.wellFormed`: distinct record names at every depth). The only producer is
  `toData` (value typed at T, T data); there is no elimination in Bend (`data_not_eliminated`).
  Runtime: `toData` is its value (one transition). Turn arguments at `Data` are injected at their
  own shape (`shapeType`); every data-typed argument is checked with `conformsUnder` first:
  "turn refused: argument does not conform to its type" (host: map to `typeMismatch`). Canonical
  bytes: a Data value is encoded as itself; untyped decode cannot tell a variant from a one-field
  record, so never `decodeAs` against `.data` expecting variants back. `PackageData` schema
  certificates support `.data` since lane 3 (§9).
  Plan.obend's `call`/`send`/`create` payloads are still `A` (objects lane).
- `textJoin(list, sep)`: `Term.textJoin`, frames `joinSeparator/joinList/joinCons/joinHead`, typing
  `Ty.isTextList` (a variable bound to `nil: {} | cons: {head: String, tail: itself}`), reference
  meaning `textJoinExpansion` (Step.textJoin), checkpoint term tag 25, frames 14-17.
- Dialect hints: `Diagnostic.hint` (Delvetalk/Hints.lean), only on refusals, ten habits.
- Artifact `methods` and `law` (Package.methodTable / lawShape); `Limits.lawTicks`.
- Checkpoint edition is still `v1` although term tags 24-25 and frames 14-17 were added: old
  checkpoints decode unchanged (only additions); a checkpoint using the new tags does not decode
  on an older binary.

## 9. Kernel lane 3 additions (2026-10-09)

- `Data` in state: the typed-data schema has `Schema.data`; `buildSchema`, the certificates,
  `quoteSchema` (every sink: `termSink` wraps `toData` with `shapeAnnotations`, `nativeSink` passes
  the value through), the compact codec (a Data field carries its own typed-data wire value) and
  `equivalent` handle it. Admission charges `admissionWork` (nodes plus each record's width squared,
  for `eraseDups`) and refuses "typed data value at Data repeats a record field". Proofs:
  `SchemaMatches.data`, `Admitted.universal`, `Data.shapeType`/`shape_typing`/`universal_typing`.
  `Admitted.typing`, `normalizeNative_typing` and `prepareNativeWith_typing` now give an existential
  `Literal` term (the value's literal with `toData` at universal positions), not `data.term`.
  The declarative `toData` rule takes any `isDataUnder` fuel (the checker still uses `Ty.dataFuel`).
- Turn arguments are quoted by their declared type (`Turn.quoteAt`), so a state record with a Data
  field is wrapped at that field. Still true: a turn argument is applied as a literal and the whole
  applied program re-checked (`prepareStart`), so a Data value whose shape type is deeper than
  `Ty.dataFuel` (a list of a few thousand) is refused by the checker on the activity path; the
  pure-method path (`prepareNative`) has no such bound. Moving `startActivity` to native arguments
  (`initialDataArguments`) removes it, at the price of changed tick pins.
- `forceHostedFrom`'s refund of a failed text preflight is the named `preflightRemaining`.
- The package knot holds only what the entry reaches (`Elaborated.select`, `Output.knotRow`;
  `globalRow` stays whole for the method table and law shape), and the whole closure is checked
  once per package (`ObjectiveBendFrontEnd.checkClosure`: every template and the knot of every
  declaration as one term), so pruning skips no checking. The type decoder charges a row's tail to
  row width (`typeRowCapacity`), not nesting, so an entry may reach any number of definitions
  (3,000 measured; before, 254).
- Compile is split: `FrontEnd.Prepared` (parse once, generics, `elaboratePackage`, closure check:
  entry-independent) and `Prepared.lower` per entry. Speedups: `sourceType` memo (`St.typeMemo`),
  generics index and rewrite memo, proposal/packet built once (`Lowering.make`), annotations
  indexed by path in `decodePacket`, `PTy.intern` subtree memo.
- Held entries, for the host: `Delvetalk.CheckedEntry {pin, source, checked, fuel}`
  (`Delvetalk/Entry.lean`; `.type`, `.ofPacket packet`, `.apply term annotations`). API:
  `Package.prepareRequest j : Except Diagnostic PreparedRequest` (cache it per package, keyed by
  modules and limits), `Package.compileEntryFrom request entry : Except Diagnostic EntryCompiled`
  (`{artifact, entry : CheckedEntry, laws}`), `Package.compileEntry j`,
  `Package.executeDataEntry entry (args : Array Data) limits : Except String DataExecution`,
  `Package.executeEntry entry argsJson limits`, `Turn.startEntry entry args binding budgets`,
  `Turn.resumeEntry entry checkpoint binding value budgets`. None decodes the packet or re-checks
  the package; arguments are checked alone and composed (`Checked.apply`). The artifact and pin
  are unchanged (`packetSha256` = CID of the entry packet JSON), so journals and checkpoints are
  unaffected.
- Wire session: prepared-closure cache (bounded by `Bounds.frontCacheSourceBytes` of source) and
  held-entry cache indexed by `packetSha256` (bounded by `Bounds.entryCacheBytes` of artifact).
  `run`, `run-data-v1`, `turn-start`, `turn-resume` take `artifact` as the whole artifact (held if
  equal to the one this process compiled under that pin, else recompiled and compared) or as
  `{"packetSha256": pin}` alone (held entries only; "unknown packetSha256: ..." otherwise).
  `{"op":"packet-cache-status"}` answers `{fronts, frontSourceBytes, maxFrontSourceBytes, entries,
  entryBytes, maxEntryBytes, hits, misses}`.
- Measured on hbox at 5b07855 (Garden, 11 modules): first compile 285 ms, further entries 7-47 ms;
  `run initial` held 4.6 ms with the whole artifact, under 0.1 ms by pin; a fresh process's first
  run of a known artifact 195 ms; `tests.run test_await test_turn_world test_http` 32.5 s; objects
  suite 8.9 s; whole suite 581 tests, 47.7 s wall.
- Wrong in this file before lane 3: §1 "collect half tested, not proved"; §3 "`decodeData` accepts
  the legacy chain" and the `relist` note; §8 "`PackageData` schema certificates do not support
  `.data`" and "Turn arguments at Data are injected at their own shape" (now type-directed at every
  depth); §7's `test_http` failures (the suite passes); the test counts in §0.

## 10. Kernel lane 4 (lane/kernel3, 2026-10-09): a typed IR, measured

Every artifact is byte-identical to before (see "Checks" below); only compile time moved.

- Surface (`Compiler/ObjectiveBendSurface.lean`): the parser's output, rewritten by the
  generics pass and read by `ObjectiveBendElaborate.ofSurface`. The generics pass visits
  children in the order of the old JSON's SORTED KEYS (`args` before `callee`, `inherited`
  before `specification`, `whenFalse` before `whenTrue`, a method's `body` before its
  signature, a spec's claims, methods, requirements, then target): instances are numbered in
  first-encounter order and the numbers are in packets. Change that order and every pin with
  a generic instance moves. Its node budget now counts Surface nodes, not JSON nodes.
  Fresh `__generic_N` names avoid identifier runs of every AST string as JSON prints it
  (`Generics.moduleNames`), exactly the old rule.
- Typing proposal as data: `ObjectiveBendElaborate.propose : Output -> Except String Proposed`
  (annotations, knot row, sorted sum bounds). `proposalJson` renders it for an entry packet.
  The whole-closure check (`ObjectiveBendFrontEnd.checkClosure`, and every template) never
  renders a packet: `directSource` builds the `AnnotatedTerm` from `Proposed` with types
  hash-consed by the packet table's node keys, `checkDirect` refuses in `accept`'s order and
  messages. Not repeated there: the packet decoder's type-nesting (256) and row-width
  capacities, which bind only entry packets. An entry still goes JSON -> `decodePacket` ->
  `check` under `accept`'s theorems, since its packet leaves the process.
- Interning: `PTy.internSlot` keys a node by constructor, strings and child slots
  (`InternKey`, constant-time hash). The derived `Hashable PTy` the brief suggested is what was
  slow: it rehashes the whole subtree per lookup, quadratic along a row. Both
  `PTy.internSlot` and `tyOf` are `@[implemented_by]` a version that memoizes by object
  address (`ptrAddrUnsafe`) within one walk: a walk allocates no `PTy`, so an address names
  one object throughout. The definitions are the plain walks.
- Checker: `agree` decides through `sameTypeShared` = `withPtrEq` + tree equality before
  canonicalizing; `sameTypeShared_eq` proves it is `sameType`, so derivations and the decided
  examples are untouched. Canonicalization (insertion sort of rows) was half of checking.
- Elaborator: context lookups by HashMap (`Ctx.declIndex/recordIndex/sumIndex`,
  `St.globalTypes`); `splitTop`/`trimStr` scan bytes; `knotNames` walks `ATerm`.
- Parser: `tokenLength` replaces the `tokenRe` matcher (`compile-profile self-check` compares
  them, and `splitTop` with its List definition, on 300,000 random strings); regex matches
  take their subject length instead of measuring it per token. The line regexes remain; parse
  is now the largest front-end stage (13 ms for Garden's 78 KB) and the next target: a
  direct scanner per line regex, checked the same way against the `Re` values.
- SHA-256 (`Compiler/Sha256.lean`): rounds as a recursive function over unboxed words, blocks
  compressed in place: 17 -> 10 ms/MiB. Canonical `keyLess` no longer copies keys.
- Wire: `scalarEscapesText` scans the request's bytes (was 1 ms per 78 KB line as a List),
  `PreparedRequest.sourcesCid` is computed once per package, held-entry size is
  `PackageSession.compressedSize` (= `compress` length, not rendered).
- Hints (`Delvetalk/Hints.lean`) fire only where the refusal points: the named line for a
  parse refusal (text), the Surface declaration holding the named line otherwise (or, without
  a line, declarations the message names, else a trigger word the message contains); never
  for a typed-packet checker refusal. `tests/test_hints.py` covers a typed-packet refusal, a
  multi-line `if` and an unbalanced `(` beside a qualified `Lists.Maybe<T>`.
- `compile-profile` (`spec/CompileProfile.lean`, `lake build compile-profile`): stage timings
  of a compile request, a loop mode for `perf record`, `self-check`, `sha`. On hbox,
  `perf` needs `kernel.perf_event_paranoid` <= 1 (it was 4; this lane set it to 1 with
  `sudo sysctl`, not persistent).

Checks. `tests/test_artifact_pins.py` compiles all 578+ non-generic entries of every world
closure and compares status, `packetSha256` and an artifact digest with
`tests/fixtures/pins/artifacts.json` (recorded with the foundation binary BEFORE any compiler
change; re-record it from a foundation binary when world sources change, never from a lane's
own binary). Beyond it, this lane captured every request/reply of a full suite run of the
foundation binary (a `tee` shim as `DELVETALK_OBEND`) and replayed the 2,464 non-world requests
against each build: byte-identical, except one reply whose hint misfire was removed.

Measured on hbox (load 9-17 from other tenants; same requests, foundation 7d90f1b binary vs
this lane):

| | before | after | target |
|---|---|---|---|
| Garden (11 modules, 78 KB) first entry `compile`, fresh process | 235 ms | 48 ms | < 60 |
| further entries, median (render, page, door / plant / receive, heard) | 15.8 ms (7-11 / 33 / 135, 56) | 8.6 ms (4.6-6 / 10.5 / 20, 18) | < 5 |
| `check-package` Garden | 227 ms | 45 ms | < 60 |
| `tests.run test_objects test_spell test_policy test_workshop` | 16.6 s | 6.1 s | < 15 s |
| `make check` (whole suite, 696 tests) | 58.6 s | 29.9 s | < 40 s |

Stages now (Garden, warm): parse 13 ms, generics 6.7, elaboration 7.5, closure check 12
(direct source 1.9, checker 9), entry `initial` 0.8 ms in Lean; entry `receive` 11 ms
(selection and packet 1.8, packet render 2.4, decode 1.2, check 3.6, CID 4.3 = CBOR 2.2 +
SHA 2.3). Further entries miss 5 ms for two reasons: a request carries the whole 78 KB
package (reading the line and parsing it, rendering a reply that repeats it, and the client's
own JSON work cost about 4 ms with no compilation at all), and an activity entry's packet is
200-250 KB that must be rendered, hashed, decoded and checked. Removing the first needs a
protocol change (name a prepared package by its sources CID instead of resending it); the
second is the artifact itself.

Wrong in this file before lane 4: §0/§1 "`lake build` passes only if every theorem still
checks" (five modules are outside the default target); §1 "AST = JSON"; §9's 285 ms first
compile (173 ms on hbox at 81ea9ec; the cost was the whole-closure proposal, 77 ms, and
generics, 60 ms, not packet decoding: the closure's packet decoded in 3.6 ms and an entry's in
under 1.5 ms).


## 11. Kernel lane 5 (lane/kernel4, 2026-10-09): surface sugar, no new semantics

Each form lowers to its explicit spelling; `tests/test_sugar.py` compiles both and
compares the packet without `sourceModules` (the only field that names source bytes).
Every world artifact is byte-identical (`tests/test_artifact_pins.py` against the
fixture recorded by the foundation binary).

- Implicit `Data` injection (`ObjectiveBendElaborate.coerceAt`/`coerceArgs`/`coerceGo`).
  Where the expected type is `Data` and the expression synthesizes a type `T` other
  than `Data`, the elaborated term is wrapped `toData T`, exactly as `Data.of::<T>(e)`
  wraps it. Expected types come from a sum payload, a call's parameter (the callee's
  synthesized arrow), an extended field and a definition's result (pure, or the `A` of
  an activity tail), and descend through record literals and both branches of `if`.
  The probe runs AFTER the ordinary elaboration and restores the elaborator state unless
  it injected, so a program with nothing to inject elaborates as before (recursive-sum
  variable numbering is a side effect of type resolution and is in packets). A value
  whose synthesized type holds an arrow or a computation is refused by name
  ("refused (data-injection): this value is a function|an Activity, ..."); a value whose
  type does not synthesize is left alone for the checker. All 11 `Data.of` in world/
  are unnecessary: stripped, every one of the 717 entries compiles to the same packet
  (minus source hashes).
- Rank-1 type-argument inference (`Generics.lean`, "Type-argument inference"). A call of a
  generic definition or constructor without `::<...>` gets the type arguments its explicit
  spelling would name, and is then rewritten exactly as that spelling: arguments first,
  then the instance, its arguments instantiated left to right with nested sums first (as
  `typeOf` does a type text), so instance numbers and packets agree. Inference never
  instantiates: `IType` keeps a generic sum as an application (`app`) and opens an
  existing instance back into one (`ofG`, `State.instanceByName`); `itypeOf` mirrors
  `typeOf` without side effects; `synthI` synthesizes over the surface with locals typed
  on demand (`List (String × M IType)`), and expected types travel the same way
  (`rewriteExpr`/`rewriteBody` take `M IType`: a call's parameter, a record field, an
  extended field, a definition's result, `perform`'s Plan, `if` and `match` arms, `let`
  annotations, a lambda's result). `inferArguments` binds from declared argument types,
  then the expected type (an activity callee's result against the expected activity, a
  pure one against its result `A`), then record literals (weak: a literal never beats a
  declared type, so `{head: {..}, tail: xs}` names `xs`'s record, as the explicit spelling
  does). A parameter left unbound is refused: "cannot infer the type argument U of
  Lists.kept (line N) from its arguments or the type its position expects; write
  Lists.kept::<T, Rain>(...) naming T" (inferred ones are shown). A nested call whose
  own argument is unknown makes the OUTER call the one named. Inference steps have their
  own budget (`maxInferenceSteps`), so the node budget refuses exactly as before. All 537
  type-argument lists in world/ (548 `::<` outside comments, 11 of them `Data.of`) are
  unnecessary: stripped (both forms), every one of the 717 entries compiles to the same
  packet minus source hashes. Pins test 8.3-8.9 s with either binary.
- `let label(x) = perform(P)` then the rest of the block: performs, binds the payload of
  the one named response, continues; any other response refuses the turn by name. The
  parser (`letCaseRe`) lowers it to `match perform(P): case label(x): <rest>` plus one
  `Pattern.unexpected` branch; the elaborator expands that branch, like a wildcard, into
  one arm per label the match does not name, in row order, each exactly
  `case l(_): refuse("unexpected response l")` (`tests/test_sugar.py` compares the
  packets). The scrutinee must be a `perform` ("refused (let-response)"). Typing of the
  form is the match's; the refusal arms need the new core term:
- `Term.refuse (reason : String)` (hosted extension, not upstream). Surface
  `refuse("why")` (one string literal) stands only where an activity finishes (a tail,
  both branches of a tail `if`, a match arm): "refused (refuse-outside-tail)" elsewhere,
  "refused (refuse-outside-activity)" in a pure definition. Typing rule
  `PartialTyping.refuse`: any `.computation P R A` with P a Plan sum, R data, A not a
  computation, using nothing; the checker reads that type from the annotation at the
  term's position (its codomain; `ATerm.refuse` carries it, `annotate` emits domain =
  codomain = the activity type). No `Step` rule: the reference relation is stuck there.
  Machine: `evaluate (.refuse r)` -> `control := .refused (.program r)` (new `Refusal`
  constructor, one tick); `Turn.refusalText` turns it into "turn refused: <reason>"
  (`evaluate-term` reports it as `stuck`, as every refusal). Checkpoint term tag 26
  `[26, text]`; a refusal is now encoded `encodeRefusal` (`[8, text]` for `program`), and
  `refusal_roundTrip` is stated on token lists. Proofs touched: CheckpointRoundTrip (term
  and refusal cases), CollectProofs (`related_stepRaw` case), Fast (`sizesAfter`),
  TermWire (`decode_json` case); every other proof stood unchanged. Checkpoints taken
  before this change decode unchanged (only additions); one holding a `refuse` term does
  not decode on an older binary. Not proved: that an activity typed by the new rule
  refuses only through `refuse` (there is no progress theorem here to extend).
- Hints: `halt(` now suggests the statement form (both the line and the parsed-declaration
  hint); the list-literal hint spells lists without `::<T>`.
- Evaluators: `["refuse", text]` is a stuck leaf in all three (arity 2, string argument);
  the generator emits it bare, as an operand, in taken and untaken `ifBool` arms, under a
  lambda and in a `case` arm, and now keeps `textJoin` separators well formed (a
  malformed separator inside a separator was an old divergence the shifted stream
  exposed). 1500-case report: 1445/1500 agree per evaluator, 55 known shared-effect,
  0 unexpected (120 cases hold a `refuse`).
