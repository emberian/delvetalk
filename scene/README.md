# Spween scenes as DelveTalk protocols

A `.scene` can carry prose, choices, guards, state changes, and navigation between
agents. The Rust bridge uses the **actual pinned Spween parser and runtime**;
`lower.py` compiles an executable scene profile into Objective Bend programs in a
generic DelveTalk protocol. Lean evaluates those programs and owns admission.
Python does compilation and file/process transport. No scene admission rule is
implemented in a Python wrapper.

Build the small bridge and host, then run the comparison suite:

```sh
CARGO_BUILD_JOBS=2 cargo build --locked --manifest-path scene/spween-bridge/Cargo.toml
LEAN_NUM_THREADS=1 lake build delvetalk-world
python3 conformance/test_scene.py
python3 scene/lower.py scene/examples/door.scene > /tmp/door-bundle.json
```

The output bundle retains the exact source string, the complete parsed AST,
upstream revision, initial handler configuration, source SHA256, compiler SHA256,
and compiled `protocol`. The AST contains spans and narrative text for renderers.
None of that text is evaluated as Python, JavaScript, shell, or Lean source.
Use `--protocol-only` for the installable definition, or `--state state.json`
for tagged initial variables and membership as described in [UPSTREAM.md](UPSTREAM.md).

## A durable run

This example installs the scene, enters it, visits the gallery, returns to the
porch, visits again, and ends with a signed negative token balance. Every turn
receives a durable receipt. Choose a fresh database path for a fresh run.

```sh
python3 - <<'PY'
import importlib.util, json
from pathlib import Path
spec = importlib.util.spec_from_file_location('world', 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)
bundle = json.loads(Path('/tmp/door-bundle.json').read_text())
db = Path('/tmp/delvetalk-door-world.json')
receipt = world.exchange(db, {
    'op': 'create', 'object': 'scene:door', 'principal': 'operator',
    'intent': 'door:create', 'protocol': bundle['protocol'], 'law': ['visitor']})
for i, command in enumerate(['start', 'choose:0:0', 'choose:1:0',
                             'choose:0:0', 'choose:1:1']):
    if receipt['kind'] != 'committed':
        raise RuntimeError(receipt)
    request = {'op': 'invoke', 'object': 'scene:door', 'principal': 'visitor',
               'intent': f'door:turn:{i}', 'expected': receipt['data']['root'],
               'command': command, 'input': {}}
    receipt = world.exchange(db, request)
    print(json.dumps(receipt, ensure_ascii=False))
PY
```

`start` is an explicit atomic initialization turn: entry effects and their outbox
intents need the same custody/receipt boundary as later choices. Spween's
`Runtime::new` does these effects immediately; the post-start state is the
comparison point. `start` can commit once. Choice commands are
`choose:<passage-index>:<choice-index>`; prose and effects do not increment choice
indices. Lean checks the current passage, guard, exact read root, and current law.
An object can represent a shared scene session or one participant's scene session,
depending on its identity and law. Shared references observe the same session.

Replay the identical request and intent to recover its retained receipt after a
lost reply. A new logical choice uses a new intent and the current whole root.
The local caller's principal name is trusted; this is not network authentication.

## Executable profile: `spween-scene-i64-v1`

The compiler supports:

- Null, Boolean, full signed i64, and String values; ordered set/modify effects;
  missing variables read as Null, and modifying a Boolean or String preserves it.
- All comparison operators, including Spween's `true == 1` / `false == 0` equality;
  string ordering; conjunction, disjunction, negated clauses, and membership.
- Guarded choices, END/absent-target termination, named passage navigation, and
  entry effects that run once per passage for the session's lifetime.
- Scene requirements as a reported Boolean. The upstream runtime does not gate
  scene initialization on this condition, and neither does this profile.
- Ordered calls as durable outbox data. The oracle's handler likewise records
  calls and does not let them mutate variables or membership.

The initial `vars` and `has` handler configuration is fixed in the compiled
protocol. Choices can update variables through scene effects. There is no
arbitrary variable-setting command, new string input, dynamic membership update,
or runtime jump operation. Metadata weight/cooldown and custom fields are retained
for a scene selector; they do not create a scheduler or ambient authority.
Unknown targets and duplicate passage names are rejected before installation.

Integers are represented at the core boundary as
`{"kind":"int","value":integer + 2^63}`. Checked arithmetic rejects values
outside signed i64, including an overflowing modification later overwritten by
an assignment. **Negative integers are not saturated to natural zero.** Strings
carry their exact text and a rank in the closed program's lexically ordered string
set, allowing Rust-compatible ordering through Nat primitives. Null and Boolean
have distinct tags. `decode_value` in `lower.py` is a presentation helper.

The full parser interchange retains Float as exact IEEE-754 bits. This executable
profile rejects Float in initial variables, conditions, effects, or call arguments
with an explicit diagnostic. Float metadata that is never evaluated is retained.
A future Float profile needs its own identifier and conformance evidence; it must
not reinterpret these values as Nat or quietly round them.

State stores `session.vars`, `visited`, `passage`, `started`, `ended`, current
`choices`, and `requirements`. Ordered sequences use
`{"length":n,"items":{"0":item,...}}`, so the core uses its existing record
boundary rather than inventing an array constructor. Unmentioned variables may
appear as explicit Null in the lowered state; comparisons treat omitted oracle
variables as Null, matching `get_var`.

Every committed turn emits one `spween-call-batch` outbox item, possibly empty.
Its `calls` sequence contains choice calls followed by the new passage's entry
calls, with each call's argument sequence in source order. Returning to a visited
passage emits none of its entry calls. A call batch is **an intent**, not a delivered
notification or an arbitrary external function invocation. The caller supplies
no executable handler. A delivery adapter needs its own authorization and retry
contract.

The original runtime can partially mutate state before errors and can panic on
overflow; the host refuses failed turns atomically. We prevalidate navigation and
compare successful transitions plus guard refusals, not arbitrary error-state
equivalence. The shared host evaluation budget and request-size limits also bound
the executable profile. Large generated scenes may exceed the 64 KiB request
envelope; the host reports an error rather than changing their semantics.

## Evidence

`conformance/test_scene.py` compares compiled execution inside the actual Lean
world with the pinned Rust runtime. It exercises 48 combinations of input value
kind and comparison operator, covering 384 guard observations, plus branching,
return visits, ordered effects, negative arithmetic, membership, requirements,
and call order. It also checks stale roots, wrong passage, unauthorized turns,
restart/replay receipts, initialization once, upper/lower i64 overflow, and
explicit unsupported-value diagnostics. The overflow test ensures a later
overwrite cannot hide an earlier failure in the lazy core.

This is executable cross-validation of a declared profile, not a refinement proof
of every Spween embedding. See [UPSTREAM.md](UPSTREAM.md) for the exact parser/oracle
wire format and upstream failure behavior, and [protocols](../protocols/README.md)
for the custody boundary.
