# Local microprotocol workbench

Agents can propose `protocols/<name>/protocol.json` and `scenarios.json`; the same
Lean interpreter runs every protocol. Run `lake build delvetalk-world`, then
`python3 conformance/test_world.py`. The test runner discovers scenario packages.
The examples are `section-edit`, `welcome-once` and `counter`; the host has no
branches on those names. `counter` runs Objective Bend inside its atomic turn. This is a local, durable **host fixture profile**, separate from the
Objective Bend expression language. It is a small usable admission laboratory,
not a deployed Mini receiver or an authenticated social network service.

## Run one object

```sh
python3 - <<'PY'
import json
from pathlib import Path
p=json.loads(Path('protocols/welcome-once/protocol.json').read_text())
Path('/tmp/create-door.json').write_text(json.dumps({
  'op':'create','principal':'operator','intent':'create-door','object':'door:example',
  'protocol':p,'law':['scanner-a','scanner-b']}))
PY
python3 scripts/world.py /tmp/delvetalk-world.json /tmp/create-door.json
```

The committed reply includes `data.root`. Copy that whole JSON value into the
`expected` field of an invocation:

```json
{"op":"invoke","principal":"scanner-a","intent":"welcome-1",
 "object":"door:example","expected":"REPLACE WITH data.root OBJECT",
 "command":"knock","input":{"message":"Welcome!"}}
```

Use `{"op":"inspect","principal":"local","object":"door:example"}` to
read a current root. Inspection is unrestricted in this local profile. An object
ID, section title, or version number alone is **not** an exact read root. Root
comparison covers version, full state, exact protocol definition and current law.
The version also prevents accepting a stale state after it changes back.

`law` operations contain `expected`, `law` (a string array), `principal`, `intent`,
and `object`. A currently admitted principal may change the law. Empty laws are
allowed and there is no recovery bypass. A law revision increments the version.
Creation is open to the local operator with a fresh object ID.
[Reprogramming](../profiles/PROGRAMMING.md) replaces an existing object's protocol
and explicit state under its current law and exact root, preserving its identity
and law. The [shared workshop](../examples/shared-workshop/README.md) exercises
proposal, replacement and use by another participant.

## Definition language

A definition has `profile: "delvetalk-local-v1"`, an object-valued `initial`, and
an object-valued `commands`. `name` and other metadata do not affect execution,
but remain part of the exact pinned definition/root. Each command has:

* `require`: pairs of expressions whose evaluated JSON values must be equal;
* `set`: field names mapped to expressions, evaluated simultaneously in old state;
* `result`: one expression returned in the committed receipt;
* `outbox`: expression array materialized in the same durable receipt.

Expressions are JSON arrays:

| Expression | Meaning |
| --- | --- |
| `["literal", value]` | Any JSON constant |
| `["state", "key"]` | Required old-state field |
| `["input", "key"]` | Required command-input field |
| `["principal"]` | Calling principal string |
| `["record", {"key": expression, ...}]` | Construct an object |
| `["array", [expression, ...]]` | Construct an array |
| `["bend", coreAST, [argumentExpression, ...]]` | Apply a pinned pure Objective Bend program |

Normalized requests are capped at 64 KiB and input frames (world plus request) at
16 MiB; exceeding a request/frame envelope returns an error without a
receipt. This limits total history in this snapshot-based laboratory.
Expression depth is bounded at 64; missing fields, bad expressions and failed
requirements refuse the turn. Installation validates all expression shapes.
The admission DSL has no iteration, network access, implicit clock, random source
or subcalls. The `bend` operation uses the same Lean kernel evaluator as the four
core implementations; its pinned core program can express recursion. User-supplied
text remains JSON data and is never parsed as program source. State and
inputs are JSON objects; values may be arbitrary JSON. There is no application
schema/type system beyond these checks. Duplicate JSON object keys should never
be authored; the JSON parser normalizes them before semantic comparison.

### Objective Bend inside a turn

`bend` programs use the array AST decoded by `spec/Delvetalk/Core.lean` (also exercised by
`counter/protocol.json`). Programs are syntax-validated at installation; this raw
core path does **not** run Mini's surface typechecker. The returned state/output
still passes through the profile's atomic root/authority/receipt checks.

Arguments and materialized results support JSON natural numbers, booleans,
strings and records. `null`, arrays, negative/fractional numbers, functions,
prototypes, specifications, variants and duplicate-label record results are not
representable at this boundary. Use an explicit record encoding if needed. The
more general JSON values remain available to the ordinary admission expressions.

One shared 10,000-tick budget covers a whole invocation's conditions, writes,
result and outbox: expression nodes, converted argument nodes, and every kernel
WHNF inspection consume ticks. Materializing each lazy record field uses the same
budget. An effect yield, stuck computation, exhaustion or nonmaterializable result
refuses the whole turn. Unforced code is not executed; this is a dynamic pure
boundary, not a static effect or affine typechecker. Kernel steps come from the
Lean relation through `Delvetalk.inspect`; the host materializer/admission logic
has tests but no corresponding whole-host proof.

Fuel bounds reduction counts, not arbitrary-precision arithmetic cost or peak
memory. This is a local trusted workbench, not an untrusted code sandbox.

All expressions see old state, including `result` and `outbox`. A failed turn
changes no object state and creates no outbox entries. The host durably records
its refusal receipt, so a retry with the same identity cannot later commit.

## Receipts, aliases and authority

`(principal, intent)` identifies a request for the lifetime of the database.
The first complete request, including its exact `expected` root, is retained
alongside its terminal receipt. Repeating that same JSON request returns that
receipt after any number of later state/law changes. Reusing the identity for a
different request refuses. A stale turn must read anew and use a new intent.
Receipts are checked before current authority; retrieving an old receipt is not
new write admission. JSON object key ordering/whitespace is irrelevant.

A welcome object represents **one stable door identity**. References to that
object share its state. Two scanners, different request IDs, a quoted alias,
or a fresh root cannot consume the welcome twice: `welcome == null` is a
current-state precondition. Creating a second object for the same external door
would evade this, so a real integration needs a canonical external-door-to-object
mapping. The local test does not infer external identities.

The outbox is durable **intent data**, not a delivered external effect. This
harness never posts welcomes. An eventual adapter must address uncertain external
outcomes and remote idempotence; one local commit does not establish exactly-once
network delivery. This is a runnable design for shared durable one-use slots;
it does not decide what arbitrary transclusion or shared effectful thunks mean
throughout Mini.

## Durability and trust boundary

`profiles/World.lean` owns evaluation, roots, current authority, revision and
receipt decisions. `scripts/world.py` supplies only lossless JSON framing (decimal preimages never round through binary floats, and Python decimal conversion
limits do not truncate Lean naturals),
process transport, a stable adjacent `flock`, and same-directory write/fsync/rename/
directory-fsync before replying. Competing local processes serialize on that
lock. Restart/lost-reply and twelve-process competing-scanner tests exercise the
boundary. A crash before replacement commits nothing; after replacement a retry
can retrieve the retained receipt. This relies on ordinary local filesystem
rename/fsync guarantees; power-loss fault injection has not been performed.

Principal strings are asserted by the local caller. Anyone with database/CLI
access is trusted to name principals or edit storage; this is **not authentication**
or tamper evidence. There are no signatures, secrets, privacy protection, remote
transport, delegation, resource metering, external execution, expiry/deadlines or
receipt pruning. Database replacement and replies are complete JSON snapshots;
this is intentionally small and unoptimized. The interpreter is implemented in
Lean but its transactional invariants are tested, not formally proved.

## Propose a protocol

Copy an example package and give its scenarios a unique `name`. Each scenario
contains `law` and `steps`; each step supplies `principal`, `command`, `input`,
`root` (`initial` or `current`), and expected receipt `kind`. Optional `state`
asserts the complete resulting application state; optional `error` asserts the
refusal reason. Every scenario gets a fresh world/object. Include a successful
turn, a stale-root attempt, a duplicate semantic action, and an unauthorized
attempt where relevant. A proposal's tests establish those cases, not universal
safety. For host invariants the suite separately exercises identity replay,
revision/lockout, exact preimages, atomic failure, simultaneous writes and races.
