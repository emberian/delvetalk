# lane/fast-suite: where it stands (2026-10-12, second session)

Target: the whole suite under 30 s wall on hbox. Last full run (6f5a8843, `tests.run --baseline`, load ~8-13 from
other lanes): 1068 tests, 30.2 s wall, green; user 6m17s, sys 3m37s (at the 6e5103b2 merge: 45.1 s, 10m08s, 3m52s).
Critical path now: test_archive.Archive 30.2 s, CarryCheck#1/2 21.4 s, Conformance 14.3 s.

## How to measure (hbox, `~/scratch/dt-fast-suite`)

- `tip/` is an rsync of the tracked files (`git ls-files | rsync --files-from`), built with `swarm-build lake build`.
  Copy each built binary to `bin-<name>`: perf resolves symbols from the file, and a rebuilt `tip` binary makes an
  older profile unreadable.
- Wall time on hbox moves 30% with other lanes' load. Compare binaries by `perf stat -e instructions:u` (sum both
  core types: the i9-12900 reports cpu_atom and cpu_core lines). `ab.sh A B [rounds] [seed]` alternates RandomHour
  (`hour3.py`: serve's instructions over 200 moves and the cards); `warm.sh BIN tests...` runs classes twice over a
  fresh compile cache and counts the second pass.
- `DELVETALK_TIMING_FILE=<path>` (serve) appends every op's timing line; a whole suite run's serves share one file.
- Profiles: `perf record -F 149 --call-graph dwarf,16384` with `DELVETALK_OBEND_COPY=<bin copy>`, then
  `perf script -F comm,ip,sym` (slow: run it nohup with a PID file) and `stacks.py` / `under.py` (inclusive share,
  callers of a symbol, what lies under it).

## Done this session (commits since 5cccc3c7)

Spell turns lazy, citations gathered once (#5); law texts parsed once (#6, parsing half); insertOnly/changedRows
by set (#8; host29 made the same change, its version kept); module parse + source SHA memo, an object's prepared
closure shared with its definitions; journal records verified/decoded once, source CIDs hashed once (#11); every
version's state CID from one walk (#16/#31); every compiled package reaches the disk cache; EveryMethod in four
groups; the Python evaluator's `reach` short-cut (Conformance 50 s -> 14 s in the suite).

## Next, ranked by what the last profiles showed

1. Archive (30 s, the critical path): not profiled this session. Start with its rehearsal phases' wall
   (rehearsal/rehearse.py) and a `perf` of one run.
2. A warm process still pays ~22% of serve CPU reading definitions from the disk cache: Lean's JSON parser on
   packet text (13%) and the packet re-check (`compiledOfPacket`, 11%, required). A binary (canonical CBOR)
   disk form would cut the parse. Many serve processes per class each pay it once per definition.
3. `checkDiagnostics` (workshop check/propose drafts) ~14% in authoring classes: owner's row 5, compile only
   the layer over the base package's prepared closure (Generics.run and elaboration are whole-closure today;
   needs the kernel lane for an incremental elaborate).
4. The C evaluator has the Python one's shape (impl/c/evaluator.c `walk` shifts a closed argument at each use):
   5 s on relation-2048-count. A reach kept per node (json-c userdata) is the same fix.
5. Owner's rows not started: #6 facts built once per object/version/clock (only the parse is memoized); #15
   whole-state Bend law/handler calls; insertOnly judged from the write's own edits (`Turn.Changes`) instead of
   both sides' rows (a 2,048-row relation still costs ~12 ms a judged write).
6. Pure-Lean SHA-256 (spec/bend/Compiler/Sha256.lean) was 15-20% of serve CPU before the CID memos: a native
   implementation behind the Lean model is the kernel lane's call.

## Open item for Ember

Two processes of mine on hbox outlived a stopped ssh (no PID file, so not killed): PID 4153477
`python3 -W ignore ../conf_py.py` and its child 4153484 `impl/python/evaluator.py`, orphaned and idle.
