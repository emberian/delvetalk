# Suite profile

Measured on hbox (24 cores, load 17 from other lanes) at foundation 171ebef with
`python3 -W ignore -m tests.run --profile`: 952 tests in 221 classes, 100 s wall,
1,431 class-seconds, 579 host processes and 94 hostd daemons started. `hosts`
counts every exec of `delvetalk-obend` (the two or more each hostd starts included);
`hostd` counts daemons.

| class | tests | secs | hosts | hostd | cause |
| --- | ---: | ---: | ---: | ---: | --- |
| test_http.HttpFront | 37 | 95.0 | 84 | 37 | a hostd per test method; each start seals the library and spawns two hosts, each stop waits out socketserver's 0.5 s poll twice (Front and hostd); hostd journals with fsync. It is the whole suite's critical path. |
| test_objects.Objects | 8 | 57.1 | 1 | 0 | `test_activities_are_computations` compiles each of about 100 activity entries against its whole closure, one full package check each (20 s alone). test_artifact_pins compiles the same entries again. |
| test_places (module) | 2 | 56.4 | 7 | 0 | runner defect: the module imports `Chain`, a TestCase with tests, so it is not "named" and the runner runs the whole module a second time. |
| test_places.Floor | 20 | 55.1 | 1 | 0 | a fresh world per test method: the compile cache is per world, so each test recompiles Place, Thing, Avatar and a Maker creator per object (39 make turns, 53 creates: 60 % of the class); it also inherits Chain's two tests (a 200-round delivery loop) and builds a 248-note inbox. |
| test_await (module) | 2 | 42.7 | 13 | 0 | runner defect: whole module run twice. |
| test_policy.PolicyObject | 22 | 42.6 | 5 | 0 | fresh world per test; inherits Chain's two tests; one test suspends 64 interpretations. |
| test_policy (module) | 2 | 36.1 | 6 | 0 | runner defect: whole module run twice. |
| test_conformance.Conformance | 3 | 35.9 | 2 | 0 | 400 generated terms through the Lean machine twice (setUpClass's report, then `test_the_machine_evaluates_every_generated_term` again), three evaluators, a `cc -O2` build. |
| test_data_type (module) | 2 | 28.9 | 13 | 0 | runner defect: whole module run twice. |
| test_wakes (module) | 2 | 26.5 | 4 | 0 | runner defect: whole module run twice. |
| test_receive (module) | 2 | 25.5 | 4 | 0 | runner defect: whole module run twice. |
| test_workshop (module) | 2 | 24.2 | 3 | 0 | runner defect: whole module run twice. |
| test_receive.Cards | 16 | 23.6 | 3 | 0 | fresh world per test; inherits Chain's two tests. |
| test_wakes.Wakes | 15 | 23.4 | 3 | 0 | fresh world per test, three to five law-bearing objects created in each. |
| test_genesis.Genesis | 2 | 22.5 | 2 | 2 | a hostd and the whole genesis per test, one of them an `expectedFailure` whose stated reason (Card.publishPage missing) no longer holds. |
| test_data_type.DataTypeTests | 6 | 22.5 | 6 | 0 | a host process per test method, nothing shared. |
| test_zulip.Bridging | 5 | 22.0 | 5 | 5 | a hostd per test method, plus a fake Zulip server per test; 0.5 s shutdown polls. |
| test_hostd.Hostd | 11 | 20.2 | 21 | 15 | a hostd per test method and a second one in four tests. |
| test_artifact_pins.PinsC | 1 | 19.9 | 1 | 0 | compiles every top-level def of eleven modules (about 280 full package checks). |
| test_artifact_pins.PinsB | 1 | 19.8 | 1 | 0 | the same, the next shard. |

The thirteen module re-runs cost 313 class-seconds; `Chain`'s two tests ran in 23
classes that inherit it, `test_outbound.Offers` and `ReplyIsAddress` again inside
test_bridge. Classes named `Maximum` (wall-clock bounds) ran after everything else,
three at a time, which serialised the tail of the run.
