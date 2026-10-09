# Local microprotocol workbench

The `world` profile runs JSON protocols through one Lean interpreter. It provides
local durable admission; caller-supplied principal names are trusted assertions.

## Run one object

From the repository root:

```sh
LEAN_NUM_THREADS=1 lake build delvetalk-world
python3 - <<'PY'
import json, tempfile
from pathlib import Path
from scripts.world import exchange
p = json.loads(Path('protocols/welcome-once/protocol.json').read_text())
db = Path(tempfile.mkdtemp()) / 'world.json'
r = exchange(db, dict(op='create', principal='operator', intent='create',
    object='door:example', protocol=p, law=['scanner']))
r = exchange(db, dict(op='invoke', principal='scanner', intent='welcome',
    object='door:example', expected=r['data']['root'], command='knock',
    input={'message':'Welcome!'}))
print(db, r)
PY
python3 conformance/test_world.py
```

`inspect` returns the whole root: version, state, protocol and law. Invocations,
`law` revisions and [reprogramming](../profiles/PROGRAMMING.md) require that exact
root and current authority. Empty laws deliberately lock out management; no
recovery bypass exists. Creation requires a fresh object ID.

## Definition language

A `delvetalk-local-v1` definition contains object-valued `initial` and `commands`.
Commands contain equality `require` pairs, simultaneous `set` writes, `result`,
and `outbox`. Every expression reads old state. Constructors are `literal`,
`state`, `input`, `principal`, `record`, `array`, and `bend`; see
[counter](counter/protocol.json), [the interpreter](../profiles/World.lean), and
[tests](../conformance/test_world.py) for schemas and refusals.

### Objective Bend inside a turn

`bend` accepts a syntax-validated, untyped core AST. Its pure boundary admits
naturals, booleans, strings and records; other JSON values remain available to
ordinary expressions. Effects, stuckness, unsupported results and exhaustion
refuse atomically. A shared 10,000-tick budget covers evaluation and conversion;
expression depth is 64. Fuel bounds reduction, not arithmetic cost or memory.
This trusted workbench is not a code sandbox.

## Receipts, aliases and authority

`(principal,intent)` identifies one complete request forever. Exact replay returns
its original terminal receipt, even after authority changes. A changed request
under that identity refuses. After stale-root refusal, read again and use a new
intent. Failed turns retain refusal receipts without state or outbox changes.

Aliases share one object's state. A second object is independent; external door
identity needs a canonical mapping. Outbox entries are durable intents and do
not establish external delivery.

## Durability and trust boundary

[Transport](../scripts/world.py) preserves decimal preimages and serializes local
writers with `flock`, write/fsync/rename/directory-fsync. Durability depends on
local filesystem guarantees; power-loss injection is untested. Database access
permits impersonation and storage edits. No authentication, remote transport,
expiry, pruning or whole-host proof is supplied. Normalized requests exceed
capacity at 64 KiB; frames at 16 MiB. Envelope errors create no receipt.

## Propose a protocol

Copy an [example package](welcome-once/scenarios.json); give scenarios unique
names and cover success, stale roots, duplicate actions and unauthorized calls.
The runner discovers packages. Tests establish their cases, not universal safety.
