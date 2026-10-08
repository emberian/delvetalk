# Automatafl, executed from Objective Bend

`Automatafl.obend` is the byte-exact two-player game package from Mini commit
`dcab86da8f6153ed2b522fc61c5064608694fd83`. DelveTalk compiles it with Mini's
actual parser, elaborator, affine/shareability checker and packet acceptor, then
executes its lowered term with Mini's demand machine and data materializer.
Neither the Python bridge nor the world host implements movement rules.

From the repository root, after `lake build delvetalk-obend`:

```sh
python3 game/automatafl/bridge.py export --output /tmp/play.package.json
python3 game/automatafl/bridge.py play /tmp/play.package.json game/automatafl/example-round.json
python3 -m unittest conformance/test_automatafl.py
```

The example is a simultaneous pair of independent moves on a 5×5 board. It
returns board `50856960`, automaton position `12`, no marks, status `0` and no
winner. The checked-in artifacts reproduce exactly from source. Running an
artifact recompiles its claimed modules, entry and compile limits and compares
the complete artifact before execution. Source and packet hashes alone are
never accepted as evidence of compilation.

## Wire and input domain

`play(w,h,board,automaton,marks,s0,t0,s1,t1)` takes nine naturals. Board digits
are row-major base four: empty `0`, attractor `1`, repulsor `2`, automaton `3`.
Marks use base two. A move is its source and target index. This is the original
two-player revealed-move function; it is not an n-player extension or a
commit/reveal protocol.

The hosted `Validated.obend` wrapper checks dimensions 2 through 9, exactly
one automaton at the declared index, no board digits outside the declared
rectangle, and no out-of-range mark bits. It then calls the unchanged game
function. Invalid representation returns unchanged data with status `2` and
winner `0`; a type error or exhausted execution budget is instead an external
`error` or `refused` diagnostic and yields no game result.

Results contain `board`, `automaton`, `marks`, `status`, and `winner`. Statuses
are `0` completed, `1` conflicting simultaneous moves, `2` illegal input/move,
and `3` already terminal. Winners are `0` none, `1` top-corner player, `2`
bottom-corner player. Both terminal wins and the next already-terminal round
are exercised by the conformance suite.

The JSONL executable supports `compile` with `{modules:[{name,source}],entry}`
and `run` with `{artifact,arguments,limits}`. Arguments and results use Mini's
explicit tagged data wire (`{tag:"natural",value:"123"}`, booleans, labels,
records); variant arguments are outside this initial profile. Imports must
refer to an earlier explicitly supplied module, e.g. `./Automatafl.obend`.
There are no filesystem imports. Package laws are refused by this pure bridge.

World consumers can store the smaller source bundle and call the same pure
Lean `Package.compile`, then `executeJsonPacket` with ordinary JSON data.
They supply their remaining shared tick allowance, charge both returned
`ticksUsed` and `conversionNodes`, and abort without committing on refusal.
Plain JSON conversion admits naturals, booleans, strings and records to depth
64; it refuses arrays, null, negatives and fractions. Compiler work is bounded
by the source/frame capacities but is not counted in demand ticks.

## Qualification and limits

`execution.jsonl` and `qualification.json` record an actual DelveTalk run of
all 353 original inputs. All 353 results exactly match the historical Bend
results. The largest raw execution used 15,628 ticks. A legal validated 9×9
round used 25,188 ticks and 1,724 heap cells. The suite checks that the exact
measured tick allowance succeeds and one fewer tick refuses. These are
measurements, not an exhaustive cost bound for every admitted board.

The historical Rust oracle agrees on 343 cases and disagrees on ten. The
original `reference-report.json` preserves the concrete boards and outputs:
nine cases concern stationary destination occupancy and one concerns a failed
move's source remaining an obstacle. Those differences are neither hidden nor
silently resolved in favor of the Rust oracle. The Rust evidence was copied
from the original qualified snapshot; this lane did not rerun that oracle.
`cases.json` and `jobs.json` reproduce the exact hashes recorded by the original
run. Tests also check one automaton, attractor/repulsor conservation, malformed
boards, representative conflicts, both wins and terminal stability.

The demand machine and its existing proof statements are reused; this work
adds no claim of a complete source-to-machine adequacy proof or universal game
termination. Two Lean 4.34 build projections are recorded centrally in
`spec/upstream.json`: the audit helper's Lean import and two TermWire proof
scripts. Original files are preserved under `spec/original`; no game or
semantic definition changes are hidden in those projections. Independent
adversarial tests cover source/packet substitution and direct/transitive axiom
and `sorry` rejection.
