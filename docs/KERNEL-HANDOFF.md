# Kernel handoff (lane/turn)

For the next agent changing the language, the turn machinery or the wire. Paths are relative to
the repository root; line numbers are for foundation 62b7dfd and drift. Everything below was read
from source or measured; "unproved" means I left it so, and says what would prove it.

## 0. Working rules that bite

- Build: `LEAN_NUM_THREADS=2 lake build 2>&1 | tail -30` (one Lean process). The only binary is
  `.lake/build/bin/delvetalk-obend`. Never rebuild while a test run is using it: `tests/host.py`
  copies the binary into a temp dir per run for exactly this reason (`DELVETALK_OBEND` names the
  source, `DELVETALK_OBEND_COPY` shares one copy across workers; `tests/run.py` is the parallel
  runner). A suite started before a rebuild with a bare path races it.
- Narrow tests first: `python3 -m unittest tests.test_turn` (23, 1 s), `tests.test_canonical` (12),
  `tests.test_conformance` (3, 10 s), `tests.test_document`. The whole discover run is ~240 s,
  314 tests: `DELVETALK_OBEND=$PWD/.lake/build/bin/delvetalk-obend python3 -m unittest discover -s tests -t . -p "test_*.py"`.
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

Pipeline for `compile`: source text -> `FrontEnd.parseSource` -> (generics, document templates)
-> `ObjectiveBendElaborate` -> typed packet JSON -> `Typing.check` (the checker) -> artifact.

| Stage | Where | Notes |
|---|---|---|
| Surface parser | `spec/bend/Compiler/ObjectiveBendParse.lean` (884) | AST = JSON, `kind` + `span {start,end,line}` on every expression node. `Diagnostic{message,span}`. Strings use JSON escapes (`json.dumps` is a valid literal). Declarations: `record`, `sum`, `type`, `def` (kind `function`; `signature.name`, `body.span`), `law`, generics `<T>`. |
| Hosted front end | `spec/Delvetalk/FrontEnd.lean`, `Generics.lean` (398), `DocumentTemplate.lean` (218) | `parseSource name src` = parse + template expansion; `lowerWithInstances` runs `Generics.run` (rank-1 specialization: generic *sums* and *defs*; generic *records* do not parse), then imports/lowering. Doc literals need an explicit `import ./Document.obend as X`. |
| Elaborator | `spec/bend/Compiler/ObjectiveBendElaborate.lean` (2340) | Source -> annotated core (`ATerm`). Errors are bare strings in `StateT St (Except String)` (`fail`, `typeError`): NO position. That is why `Package.localize` exists. `Activity<P,R,A>` is parsed at ~l.756; `perform`/effect-mode lowering l.1137, 1537; `noActivity` (l.1234) is the "effect in shared position" refusal. Recursive record/sum = `Ty.variable i` + a bound. |
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

Proof guards. `lake build` passes only if every theorem still checks; there is no `sorry` in
`spec/` (the AxiomPin files pin axiom sets in Fast/Cshake files). What each change must keep:
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

What I did NOT prove or port (honest list):
- From Mini's `ObjectiveBendDemandCollectProofs.lean` (1787 lines) and the Settle/RoundTrip/typing
  transfer files I ported none: the collector's behaviour-preservation simulation, `typed_settle`,
  `settle_resume_segment` ("a checkpoint resumes exactly as the live state would"), and the round
  trip theorem `decodeState (encodeState s) = some s`. Their only evidence here is tests
  (`tests/test_turn.py`: restart, tamper, resume in a fresh process) plus the digest binding.
  I adapted the codec by hand for `native`, `nativeCached`, `nativeArgument`, `unary`,
  `nativeApplication`, the five text primitives (codes 11-15) and `Term.unary` (tag 23); a new
  machine constructor needs a new token tag in BOTH Checkpoint and Collect (addresses!) or it is
  silently dropped from tracing: `collect` would then free live cells.
- Admitting recursive sums changed `perform`'s side conditions to
  `isPlanUnder assumptions.bounds assumptions.rigid` / `isDataUnder ...`. All 73 Typing theorems
  still check unchanged, so nothing was weakened. Not proved: that `Data.conformsFuel` agrees with
  `isDataUnder` (soundness of runtime conformance w.r.t. the type), and that fuel is never the
  cause of a false negative (fuel = `(size+1)*(bounds+3)+2`; `Ty.dataFuel` 4096 caps type depth).
- `Data.conforms` once accepted `{}` for any non-row type; fixed (requires `.field`/`.emptyRow`).
- Shared-effect refusal is proved for the machine (`perform_under_update_refused`) but the
  elaborator's `noActivity` is the only static guard; no theorem links them.

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
either order). `decodeData` accepts `list` and the legacy `nil|cons` chain ("one release" window;
nothing enforces the end of it: delete the `nil|cons` reading and re-run everything). Decode depth
is by NESTING: `decodeData fuel` spends one fuel per record/variant/list level, not per element
(`Bounds.dataWireDepth = 256`; chains still cost 2 levels per cell, arrays do not). A decoded list
becomes a `cons` chain in memory (deep structure; fine to 5,000+, functions over Data are `partial`).
`dataJsonBytes` must equal `(dataJson d).compress.utf8ByteSize` (checked by hand; keep in sync).
Tests that read replies through `tests/host.py`/`test_world.py`/`test_turn.py` see the chain because
`tests/wire.py:relist` converts arrays back; `tests/test_canonical.py` uses a raw host.

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

## 5. The tariff (what costs what) — `textStepCost` / `forceHostedFrom`, DemandData l.84-135

Every machine transition costs 1 tick. Before a text primitive runs, `forceHostedFrom` admits
`(ticks, bytes)` from `textStepCost` and suspends (`ticks` or `capacity`) if either exceeds what is
left; the state is retained exactly. Charges (B = byte size of the operand, n = count):
- `textConcat a b`: `1 + 2(|a|+|b|)` ticks, reserves `|a|+|b|` bytes.
- `textTake t n`: `1` if n=0 or n>=B; else `1 + 2*min(B, 4n)`; reserves `min(B,4n)`.
- `textDrop t n`: same rule on the DROPPED prefix (changed by me from `1+B+min(B,4n)`); still
  reserves B bytes. Real copying cost is B-n and is not charged: honest remaining under-charge.
- `textSpan/textBreak`: `1 + perScalar*visited`, perScalar = `2*(|alphabet|+2)`; refused up front
  if the cap cannot cover the scan (spends the allowance, returns 0 credit).
- `textLength`: `1+B`. `sha256Text`: `65 + 8*ceil(B/64) + 32*blocks`, blocks = `(B+72)/64`; reserves
  `64*blocks+4096`. `natText n`: `1 + bits^2` (quadratic in bit length), reserves `bits`.
- Arithmetic, comparison, record/variant steps: 1 tick; no size charge on big Nats (a 2^64-bit
  multiply costs 1). Materialization: forcing costs ticks like any step; each node costs 1 `nodes`
  and its encoded size in `bytes`.
Measured: an interpreted loop step costs ~50 ticks (match + add + call + args) of which the text
primitives are ~20 (`tests/test_turn.py::TextTariffTests`: 4096 one-char take/drop steps = 213k
ticks, linear). Plan/result extraction runs on a scratch copy.

Quadratic idioms and why:
1. Left-fold `textConcat acc x`: each step re-charges the whole accumulator (`2*|acc|`). Document.plain
   avoids it by flattening leaves then joining adjacent pairs in rounds (O(n log n) bytes).
2. `Lists.append xs x` in a loop (Bell rains): O(n) per append, O(n^2) total; 1,025 rains cost ~850k
   ticks for `plain`, 316k for just building. `Entries.append` edits at the host are the escape.
3. `Lists.length` inside a loop; `Lists.concat` of long left operand.
4. Character walks: `textDrop` by 1 is now cheap in ticks, but still allocates B bytes of reserve
   each step against the per-step `bytes` cap.
5. `natText` on big numbers; `sha256Text` per item on large lists.
6. Rendering: the 1,025-rain card in Bend is 300k+ ticks; the host renders Documents natively
   (`Delvetalk/Document.lean`, zero ticks, 11 ms) — the `offer` Plan is how to use it.

Two changes I judge most valuable next:
- A text join primitive (or a rope/builder value): `textJoin : List String -> String` charging
  `1 + 2*total bytes` once (and a `Strings` builder type), replacing the pairwise-round trick in
  `Document.plain` and every left fold. It needs: a `Primitive` or new `Term` form (OpenRecursion,
  Typing `PartialTyping`, Checkpoint code, `evaluate-term`, all three evaluators + conformance
  generator), a tariff line, and a typing rule over `List<String>` (a sum, so it must unfold the
  recursive bound: use `Ty.lookup` like `isDataUnder`). Cheaper alternative: a host-side `textJoin`
  of a `Strings` Data in the same way Document is rendered, avoiding a new Term.
- Interpretive overhead (~50 ticks/step): look first at (a) `Frame.argument`/`update` thunk traffic for
  lambda-bound variables that are used once (strictness annotation or a "cheap value" fast path in
  `stepRaw`), (b) `case` on a variant allocating a payload cell, (c) charging `app` of a known
  closure as one tick. Any change to `stepRaw` must be mirrored in `stepRawFast` and re-prove
  `stepRawFast_eq_stepRaw`/`sizesAfter_eq`, and must keep the evaluators' small-step semantics in
  agreement on values (tariffs are not compared, so conformance will not catch cost regressions:
  add ticks assertions like the text-walk test).

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
- `tests/test_http.py::test_repl_*` fail on foundation: `transport/http.py` calls `turn-start` without the
  binding (`roots` etc.). Not kernel; the transport lane owns it.
- Host-side resume of suspended activities rebuilds the `Checkpoint` from journaled tokens plus the
  activity's object/principal/intent/roots (`resumeOne` in TurnLoop); if you change `Checkpoint`'s
  fields, journals written before the change stop resuming (no migration exists).
- Checkpoints contain the whole program heap (hundreds of tokens even for `bump`); `collect` only drops
  unreachable cells. A size-aware checkpoint (share the program, store only mutable cells) would cut
  journal bytes a lot but changes the binding story.
- `Outcome.exhausted` is a silence, not an error; the host currently maps it to a refused turn with
  message "turn refused: <resource> budget exhausted"; journaling class `budget` is host work.
- Related docs: `docs/FOUNDATION.md` (design), `docs/HOST-HANDOFF.md`, `docs/OBJECTS-HANDOFF.md`.
