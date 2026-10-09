# Automatafl, executed from Objective Bend

DelveTalk's Bend parser, checker and demand machine execute the byte-exact two-player
[Automatafl.obend](Automatafl.obend). The bridge implements no movement rules.

```sh
LEAN_NUM_THREADS=1 lake build delvetalk-obend
python3 game/automatafl/bridge.py export --output /tmp/play.package.json
python3 game/automatafl/bridge.py play /tmp/play.package.json game/automatafl/example-round.json
python3 conformance/test_automatafl.py
```

Execution recompiles claimed sources and compares the complete artifact. Hashes
alone cannot establish compilation.

## Wire and input domain

`play(w,h,board,automaton,marks,s0,t0,s1,t1)` accepts nine naturals. Board digits
are row-major base four: empty/attractor/repulsor/automaton = 0/1/2/3; marks are
binary. Each player supplies source/target indices.

[Validated.obend](Validated.obend) checks dimensions 2–11, one correctly indexed
automaton, bounded board digits and marks. Results contain `board`, `automaton`,
`marks`, `status`, `winner`. Statuses: 0 completed, 1 conflict, 2 illegal input/move,
3 already terminal. Winners: 0 none, 1 top corners, 2 bottom corners. Representation
failure preserves data; execution refusal returns no game result.

[Package.lean](../../spec/Delvetalk/Package.lean) specifies compile/run wire, explicit
imports and conversion limits; [bridge.py](bridge.py) supplies the CLI. Imports
cannot read arbitrary files. Package laws refuse in this pure bridge.

## Qualification and limits

[Qualification](qualification.json) reproduces all 353 historical Bend outputs.
The stored [Rust comparison](reference-report.json) differs on ten cases involving
stationary destinations and failed-move sources. Those historical records remain unchanged; that comparison used the newer
`logic/` implementation, not the original `rust/` crate. Measured costs are not universal bounds. Existing machine
proofs do not establish complete source adequacy or universal game termination.
[Mini origin](../../spec/bend/origin.json) records the local semantics fork’s upstream baseline;
[adversarial tests](../../conformance/test_package_adversarial.py) cover substitution
and axiom/`sorry` rejection.

## Original opening and actual match

The offered game is only the original tuned 11×11, two-player opening, recorded in
[original-opening.json](original-opening.json). It contains 12 attractors,
24 repulsors and the automaton at F6 (index 60). Both original Rust
`stock_two_player()` and the original Python `DEFAULT_SETUP` store **columns**:
Rust's original `Coord.ix()` returns `(x,y)`. Converting to this package's row-major
encoding preserves that geometry. The newer `logic/` crate stores the identical
nested array with `(y,x)` indexing, which transposes the opening; it is not used
for this layout. Python corroborates the layout only; its older tie behavior and
goal configuration are not imported. The qualified Bend rules remain byte-exact.
Small boards in the retained corpus and 9×9 budget test are algorithm fixtures,
not alternative games offered by the table or companion.

[Original-opening qualification](original-opening-qualification.json) records an
unchanged-board opening probe and ten successive completed rounds through both
the actual Lean executable and the original Rust rule core. Every full board,
automaton location, mark, status and winner agrees; round ten reaches A1 for
North. Maximum measured Lean cost is 31,862 ticks, within the existing 100,000
budget. This is finite execution evidence, not a universal bound or equivalence
proof. Existing general machine proofs do not establish source adequacy or full
game termination on the 11×11 board.

The original Rust crate's locked `smallvec` version lacks `drain_filter`.
[The explicit compatibility patch](original-rust-compatibility.patch) replaces
that one call with ordered collection/removal of exactly the same matches.
[The I/O adapter](original-rust-oracle.rs) starts each revealed pair with the
retained board (including automaton and marks), fresh input slots and explicit
y=0/y=10 corner goals. The old constructor leaves goals empty and its completed
round leaves pending moves uncleared. This comparison exercises completed rounds,
not that old interactive transport or its conflict/terminal recovery. Source,
patched-source and adapter hashes are retained in the qualification.

To reproduce the Rust comparison, copy the original `rust/Cargo.toml`,
`Cargo.lock`, `src/lib.rs` and `src/support.rs` to a private directory, verify the
recorded source hashes, apply `original-rust-compatibility.patch`, and copy the
adapter to `src/main.rs`. Run `cargo build --offline --locked -j 1` there (fetch
the exact locked dependencies first if absent). Feed the resulting `automatafl`
binary each round's last four `arguments` as a space-separated line. The adapter
emits the complete row-major cells and result. `test_automatafl.py` reruns Lean
against those recorded Rust results; it does not build a Rust dependency in CI.
