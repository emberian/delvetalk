# Machine and turn performance

Measured on hbox (24 cores, shared with other lanes at load 20 to 30), lane/perf2 from
foundation 613639d. Re-measure before relying on a number.

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
twice. The machine is not the cost: it runs about 5 million ticks a second (200 ns a tick)
inside a turn and 13 million on the spell parse. The host's 0.73 million ticks per second
of wall is checkpoint work around the machine.

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

| workload | ticks per turn | wall per turn | ticks per second of wall |
| --- | --- | --- | --- |
| Counter bump (2nd and 3rd) | 143 | 0.73 ms | 0.2 M |
| 64-field spell parse | 71,250 | 5.3 ms | 13.2 M |
| directory `receive` (120 turns) | 104,077 mean | 142.5 ms mean | 0.73 M |
