# Blind reconstruction notes

Only the following two files supplied semantic and interface information:

- `/Users/ember/dev/delvetalk/capsules/machine-2k.txt`: 1995 bytes; SHA-256 `6cd2d0e5a7e8deb1eae7c8b54f2292d295efd63d0aaceb724b340746698779de`.
- `/Users/ember/dev/delvetalk/experiments/capsule-only/WIRE.txt`: 852 bytes; SHA-256 `a59335e3c227b48b110bbb329580cc4f90574d6a47176a752e1b277d4a27b741`.

Total input: 2,847 bytes. No other implementation, tests, documentation, capsules, network data, or semantic consultation was used.

## Interpretations and ambiguities

- Fuel counts one successful source contraction: beta, specification application, mix expansion, fix unfolding, destructor/projection, record extension, branch/case selection, primitive operation, done elimination, or perform encounter. Traversal to find the next contraction, value recognition, stuck recognition, and inserting a supplied reply are free. This operational meaning of “source steps” is an assumption because neither input enumerates charged transitions.
- A pending yield remains represented as its original `perform` node in the whole reduced context. WIRE has no separate hole/suspension constructor. The plan is appended only when its perform step is charged; zero remaining fuel before that step yields exhausted and no additional plan. After the step, a supplied reply is inserted even if fuel has become zero.
- Exhaustion applies when a further source step is required. A value or stuck term is recognized with zero fuel. A stuck result preserves the complete residual evaluation context.
- All constructor children stay raw. Binary operators evaluate both arguments left to right before checking operand types, including strict conjunction.
- The Nat equal operator is `equal`; string equality is `labelEqual`. Scalars remain disjoint. `project` is the wire spelling for capsule target; `reflect` returns the prototype's first component.
- De Bruijn index zero is the nearest binder. Only lambda bodies, ifZero's third term (successor body), and case-arm terms add binders. Substitution traverses unevaluated children and lifts free indices under binders.
- Open bound terms become stuck when evaluated. Records and arms retain order and duplicate keys; extension preserves all new fields, dropping all old fields whose keys occur among the new fields.
- Host authority, commits, receipts, and sponsorship are outside this pure term/reply wire; no host state protocol is invented.
- Valid jobs stream as one output line each. Malformed input diagnoses stderr and terminates nonzero. Finite Python memory/stack limits remain physical limits on arbitrarily large terms, despite unbounded natural arithmetic and an iterative weak-head reduction loop.

## Checks

Ten hand-created examples passed: beta/arithmetic, raw record children, yield context, reply consumption, fuel boundary, capture avoidance, case binding, successor binding, strict conjunction, and ordered extension. No held-out cases or existing tests were read. Evaluator is frozen before the examiner runs.
