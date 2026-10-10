# Machine and turn performance

Measured on hbox (i9-12900: P-cores 0-15, E-cores 16-23; shared with other lanes), lane/perf2
from foundation 613639d. Re-measure before relying on a number: under load 30 to 60 the same
replay took three times as long, and a process that migrates between P- and E-cores varies
by 30%. The numbers below are pinned to the P-cores (`taskset -c 0-15`) at load 4 to 18, the
fastest of three runs, with user instructions (`perf stat -e instructions:u`, the least of
three; they vary by about 5% run to run) as the load-independent check. File:line references are
that tree's (`conclude` is now `Turn.lean:457`, `drive` `TurnLoop.lean:1077`); `tests.test_spell` now
parses through the host's `spell-parse`, and `fieldCount` is gone, so that workload is not rerunnable as written.

## How it is measured

`compile-profile replay LINES DIR FILTER R` (`spec/CompileProfile.lean`) feeds host requests,
one JSON per line exactly as `delvetalk-obend` reads them, through `PackageSession.stepIO`.
`world-open` is moved to `DIR/world.journal` (emptied first) with `sync: none`, so no fsync is
timed. Each request whose class (`op object method`, an object class like `garden/*` for
`garden/bell/2`, or `op entry` for held runs) starts with FILTER runs R times from the same
session; the fastest run is kept and the session continues from it. It prints, per class,
requests, wall (ms), `ticksUsed` and ticks per second of wall.

The three workloads are request streams captured by a wrapper binary that tees stdin
(`tee $CAPDIR/$$.jsonl | delvetalk-obend`):

| workload | captured from | lines | filter |
| --- | --- | --- | --- |
| Counter bump | `tests.test_turn_world.CounterTurns.test_bump_three_times_leaves_count_three_at_version_three` | 6 | `world-turn c1 bump` |
| 64-field spell parse | `tests.test_spell` (the shared stateless host) | 99 | `run fieldCount` |
| directory prose `receive` | `rehearsal/rehearse.py` (1,763 archived posts, the shared world host) | 16,869 | `world-turn directory receive` |

The streams are not checked in (the rehearsal one is 3.5 MB of archive traffic); rebuild
them with the wrapper. Ticks per second of *the machine alone* is read from `perf`: samples
under `forceHostedFrom` against the ticks the replay ran.

## Where a directory turn goes (baseline)

`perf record -F 299 --call-graph dwarf` of the rehearsal replay with directory `receive` run
twice, at load 30 to 60 (the shares hold; the absolute times do not). The machine is not the
cost: the host's ticks per second of wall is checkpoint work around the machine.

Inclusive share of the host's `drive` loop (the turn's segments):

| share | what |
| --- | --- |
| 88.6% | `Turn.resumeEntry` (every segment after the first) |
| 49.8% | `Turn.conclude` (after a segment: Plan extraction, checkpoint) |
| 31.8% | `Turn.prepareResumeEntry` (digest check, checkpoint decode) |
| 24.1% | `Canonical.cidJson` (both checkpoint digests) |
| 20.7% | `Checkpoint.makeFor`: `checkpointDigest` at the yield |
| 19.5% | `Turn.tokensJson`: tokens to `Json` for the digest |
| 18.4% | `encodeStateV3` (of it: `termHash` 16% of its samples, `encodeTerm` 10%, `mapStateAddresses` 6%) |
| 11.6% | `Sha256.digest` |
| 9.7% | `decodeStateV3` |
| 7.4% | `forceHostedFrom` (the machine) |
| 6.9% | `Canonical.writeJson` |
| 5.7% | `DemandCollect.collect` |
| 4.2% | `Host.noteProfile` |

Top 15 symbols by self time, whole replay (flat `perf record -F 999`):

| self | symbol |
| --- | --- |
| 16.39% | `mi_malloc_small` |
| 9.41% | `lean_dec_ref_cold` |
| 4.79% | `List.reverseAux` (list `++` in the checkpoint encoders) |
| 4.49% | `Sha256.schedule` loop |
| 4.47% | `Sha256.rounds` |
| 3.41% | `mi_free` |
| 2.04% | `Canonical.writeJson` |
| 1.92% | `lean_del_core` |
| 1.68% | `List.mapTR` in `Turn.tokensJson` |
| 1.64% | `mi_malloc` |
| 1.42% | `List.lengthTR` |
| 1.31% | `lean_array_push` |
| 1.28% | `List.mapTR` in `ObjectiveBendCheckpoint.decodeStrings` |
| 1.17% | `lean::hash_str` |
| 1.04% | `ObjectiveBendCheckpoint.termHash` |

## Before and after

`bench.sh BIN` (the lane's helper): per workload, the target class's wall (best of R per
request, best of three runs) and the whole replay's user instructions. Base is foundation
613639d; after is lane/perf2. Each change was also checked by replaying the rehearsal into a
journal: the journal and its snapshot are byte-identical to the base binary's.

| workload | ticks per turn | wall per turn, before -> after | ticks per second of wall, before -> after | replay instructions, before -> after |
| --- | --- | --- | --- | --- |
| Counter bump (3 bumps; the first compiles the method) | 143 | 16.0 -> 14.0 ms mean (0.7 ms without the compile) | 8.9 K -> 10.0 K | 4.12 -> 3.92 G |
| 64-field spell parse (`run fieldCount`, 4 runs) | 71,250 | 1.75 -> 1.75 ms | 36.3 M -> 37.4 M | 6.77 -> 6.73 G |
| directory prose `receive` (120 turns) | 104,077 mean | 46.9 -> 41.9 ms mean | 2.22 M -> 2.49 M | 189.0 -> 170.1 G |
| activity start, 5,000-item `List<String>` argument | 46 | 1,730 -> 784 ms | | |
| activity start, 5,000-item list at `Data` | 60,059 | 4,454 -> 4,408 ms | | |

The machine itself runs the spell parse at 37 million ticks a second of wall including
extraction (27 ns a tick) and the directory turns' segments at roughly 25 million (11% of
the drive loop's samples for 12.5 million ticks). It is not where turns spend their time,
so the lane's 10x-ticks-per-second target does not apply to it: a directory turn is 2.5
million ticks per second of wall because of the checkpoint work around each segment.

Changes, each its own commit:

1. `compile-profile replay` and this file.
2. `encodeTermOnto`/`encodeDataOnto` (`ObjectiveBendCheckpoint.lean`, `@[csimp]`, proved
   `encodeTermOnto t acc = encodeTerm t ++ acc`): the v1 term encoder was quadratic in a
   term's depth, and an activity's first checkpoint holds its argument literal inline. The
   5,000-item `List<String>` start: 1.73 s -> 0.78 s.
3. SHA-256 rounds over an unboxed sixteen-word schedule window (`Compiler/Sha256.lean`):
   1 MB in 9.8 -> 5.9 ms; the rehearsal replay 189.0 -> 174.8 G instructions. Checked by
   `compile-profile self-check` (FIPS 180-4 vectors; the old version on lengths 0..400 and
   1 MB).

Tried and not kept (no measurable change, or slower): a 32-node prefix hash for the v2
dictionary's term hint (a worklist per lookup costs more than hashing the small terms the
heap holds); the v2 body encoder onto an accumulator (proved, `encodeBodyV2Fast`, but the
replay did not move); CBOR heads and digest bytes without `List.range`.

## What remains, with the file and the fix

Inclusive share of the host's `drive` loop after the changes:

| share | what | file |
| --- | --- | --- |
| 51.6% | `Turn.conclude`, of it `encodeStateV3` 19.5%, `Checkpoint.makeFor` 19.0% | `Delvetalk/Turn.lean:310`, `:250` |
| 25.5% | `Turn.prepareResumeEntry`: digest recomputed 12.0%, `decodeStateV3` 6.6% | `Delvetalk/Turn.lean:426` |
| 25.8% | `Canonical.cidJson` (both digests), of it `Turn.tokensJson` 12.6% | `Delvetalk/Turn.lean:175`, `:245` |
| 11.1% | the machine (`forceHostedFrom`) | `Theory/ObjectiveBendDemandData.lean` |
| 5.9% | `DemandCollect.collect` | `Theory/ObjectiveBendDemandCollect.lean` |
| 2.5% | `Host.noteProfile` runs with profiling off | `Delvetalk/Host/TurnLoop.lean:599` |

1. **Do not checkpoint a segment the host answers at once** (kernel and host lanes). The host's
   `drive` (`TurnLoop.lean:575`) answers every Plan but `await`, `awaitPost` and `interpret`
   in the same process and resumes at once (`resumeEntry`, `:598`); each such segment pays
   `encodeStateV3`, a canonical digest of the tokens through `Json`, then the digest again
   and `decodeStateV3`. `stateV3_roundTrip` already proves decoding the encoding is the
   state, so `Outcome.yielded` can carry the collected `State`, `resumeEntry` can take it,
   and the `Checkpoint` (tokens and digest) can be made only where the turn suspends. Estimate:
   about 64% of the drive loop, so directory turns 2.5 to 3 times faster (42 ms to about
   15 to 20 ms). No step relation changes.
2. **The digest without `Json`** (kernel lane), where a checkpoint is still made:
   `checkpointDigest` (`Turn.lean:245`) builds a `Json` array of every token
   (`tokensJson`, `JsonNumber.fromNat` per token) only for `Canonical.cidJson` to write it as
   CBOR. A writer of the same CBOR straight from `Tokens` removes `tokensJson` (12.6%) and
   most of `writeJson`. `resumeEntry` should not recompute a digest the host made in this
   process.
3. **`Host.noteProfile`** (host lane, `TurnLoop.lean:599`): 2.5% of the loop with profiling
   off; the closure's work should not run unless a profile was asked for.
4. **List admission is quadratic in the type checker** (kernel lane):
   `ObjectiveBendTyping.infer`/`inferFields` (`Theory/ObjectiveBendTyping.lean:423-570`,
   `:689`) build each child's position as `position ++ [i]`, a copy as long as the depth, and
   the annotation function (`Delvetalk/Entry.lean:44`, `AnnotationTree.lookup`) walks the
   whole position from the root at every node: a 5,000-deep list literal costs 5,000 squared.
   At `Data` the literal's type also grows with depth and is compared
   (`instDecidableEqTy`, `Ty.shareableUnder`) at every level. Fix: carry the position reversed
   (`i :: position`) with the annotations as a cursor (the subtree at the current node), in a
   `@[csimp]` mirror of `infer` proved equal to it. After change 2 the type checker is
   nearly all of the 5,000-item start's profile.
5. **Machine** (this lane's files, if a pure-compute workload ever matters): `forceHostedFrom`
   calls `textStepCost` and `sizesAfter` and matches the state three times per tick; one
   fused match per tick would remove most of `sizesAfter` (1.1% of a directory turn).
   A shallow embedding (terms compiled to Lean closures) would speed the 11% the machine
   takes and lose what the turn depends on: every yield writes the heap and stack as data.
