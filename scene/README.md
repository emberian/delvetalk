# Spween scenes as DelveTalk protocols

The pinned Rust parser supplies Spween's AST. `lower.py` compiles supported scenes
into Objective Bend protocols; Lean evaluates them and owns admission.

```sh
CARGO_BUILD_JOBS=2 cargo build --locked --manifest-path scene/spween-bridge/Cargo.toml
LEAN_NUM_THREADS=1 lake build delvetalk-world
python3 scene/lower.py scene/examples/door.scene > /tmp/door-bundle.json
python3 conformance/test_scene.py
```

Bundles retain source, AST, provenance, initial configuration and `protocol`.
`--protocol-only` emits the definition; `--state FILE` supplies initial variables
and membership. Narrative text remains data.

## A durable run

After building above:

```sh
python3 - <<'PY'
import json, tempfile
from pathlib import Path
from scripts.world import exchange
p = json.loads(Path('/tmp/door-bundle.json').read_text())['protocol']
db = Path(tempfile.mkdtemp()) / 'world.json'
r = exchange(db, dict(op='create', object='scene:door', principal='operator',
    intent='create', protocol=p, law=['visitor']))
for i, command in enumerate(['start', 'choose:0:0']):
    assert r['kind'] == 'committed', r
    r = exchange(db, dict(op='invoke', object='scene:door', principal='visitor',
        intent=str(i), expected=r['data']['root'], command=command, input={}))
    print(r)
print(db)
PY
```

`start` admits initialization once. Choices use passage/choice indices; guards,
current passage, whole root and law must match. Exact retries recover receipts;
new choices need fresh intents. Principals are local assertions.

## Executable profile: `spween-scene-i64-v1`

Supported values are Null, Boolean, signed i64 and String. The profile supports
ordered effects, comparisons, membership, guarded navigation and termination.
Entry effects run once per passage per session. Requirements are reported, not
initialization gates. Spween equality includes `true == 1` and `false == 0`.
Membership is fixed; metadata creates no scheduler. Unknown targets and duplicate
passage names refuse before installation.

Overflow refuses, even before a later overwrite. Executable Float values refuse;
unevaluated metadata survives. Calls become ordered `spween-call-batch` outbox
intents, including empty batches; delivery needs a separate authorization/retry
contract. No caller-supplied handler executes.

## Evidence

[Tests](../conformance/test_scene.py) compare successful transitions and guard
refusals against pinned Rust, including 384 guard observations, ordering, replay
and overflow. Upstream can partially mutate before errors; Lean refuses atomically.
This is cross-validation, not general refinement. Host fuel and 64 KiB request
limits apply. [UPSTREAM.md](UPSTREAM.md) defines interchange; [lower.py](lower.py)
defines tagged state/values; [protocols](../protocols/README.md) defines custody.
