# Automatafl, executed from Objective Bend

Mini's parser, checker and demand machine execute the byte-exact two-player
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

[Validated.obend](Validated.obend) checks dimensions 2–9, one correctly indexed
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
stationary destinations and failed-move sources. This work retains those differences;
it did not rerun Rust. Measured costs are not universal bounds. Existing machine
proofs do not establish complete source adequacy or universal game termination.
[Upstream metadata](../../spec/upstream.json) records compatibility projections;
[adversarial tests](../../conformance/test_package_adversarial.py) cover substitution
and axiom/`sorry` rejection.
