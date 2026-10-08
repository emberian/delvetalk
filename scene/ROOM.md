# Source-bound shared rooms

`room.py` turns a compiled scene into an immutable local artifact and renders
views from committed Lean state. It produces machine JSON and static escaped
HTML. Viewing a room never runs Spween, recompiles source, enters a passage, or
applies an effect. Choice availability is read from the committed session;
Lean remains the decision-maker when the resulting request is submitted.

The example [repair-cafe.scene](examples/repair-cafe.scene) has a mechanical moth
with two repairs: align its wing and wind its spring. Either order works. Once
both actions have committed, the shared session can release the moth and follow
its projected constellation. A second visitor sees the same workbench state.
This is one shared session; it does not pretend to model personal inventories or
participant-local state.

## Run a room

Build the existing scene bridge and world executable as in [README.md](README.md).
This example uses local temporary paths; it starts no service and publishes nothing.

```sh
python3 scene/room.py compile scene/examples/repair-cafe.scene /tmp/room-artifacts
```

The result gives an `artifactId` and file path. Install that file's `protocol`
with the ordinary `create` operation. For an entirely scripted first visit:

```sh
python3 - <<'PY'
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('room', 'scene/room.py')
room = importlib.util.module_from_spec(spec)
spec.loader.exec_module(room)
artifact = room.compile_artifact(Path('scene/examples/repair-cafe.scene').read_bytes().decode('utf-8'))
artifact_id = room.store_artifact('/tmp/room-artifacts', artifact)
db = Path('/tmp/repair-cafe-world.json')
receipt = room.world.exchange(db, {
    'op':'create', 'object':'cafe', 'principal':'operator', 'intent':'create-cafe',
    'protocol':artifact['protocol'], 'law':['visitor', 'other-visitor']})
root = receipt['data']['root']
view = room.room_view(root, artifact, 'cafe')
receipt = room.world.exchange(db, room.start_request(view, 'visitor', 'enter-cafe'))
for i, choice in enumerate([0, 1, 2, 0]):
    view = room.room_view(receipt['data']['root'], artifact, 'cafe')
    receipt = room.world.exchange(db, room.choice_request(view, choice, 'visitor', f'cafe-choice-{i}'))
    if receipt['kind'] != 'committed': raise RuntimeError(receipt)
view = room.room_view(receipt['data']['root'], artifact, 'cafe')
Path('/tmp/cafe-view.json').write_text(room.world.wire_dumps(view))
Path('/tmp/cafe-view.html').write_text(room.html_view(view))
print(artifact_id)
PY
```

For later reads, use the printed ID:

```sh
python3 scene/room.py view /tmp/repair-cafe-world.json cafe /tmp/room-artifacts ARTIFACT_ID > /tmp/cafe-view.json
python3 scene/room.py view /tmp/repair-cafe-world.json cafe /tmp/room-artifacts ARTIFACT_ID --html > /tmp/cafe-view.html
python3 scene/room.py request /tmp/cafe-view.json visitor next-choice --choice 0 > /tmp/cafe-request.json
python3 scripts/world.py /tmp/repair-cafe-world.json /tmp/cafe-request.json
```

The request contains the **whole exact root from that view**. The client never
substitutes a newer root while dispatching. If someone else changed the shared
room, Lean refuses the stale request. Read again and choose a new intent for a
new logical action. Retry the identical request and intent to recover its receipt.
The view is descriptive data: falsifying its availability label does not grant
authority or bypass the compiled guard. Local principal strings remain trusted
caller assertions, as documented by the world profile.

## Artifact binding and API

`compile_artifact(source, initial_vars=None, has=None)` runs the pinned parser and
compiler once. `wrap_bundle(bundle, pins=None)` instead takes an existing Spween
translation bundle without rerunning either. Wrapping adds protocol metadata, so
**install `artifact['protocol']`**, not the pre-wrapper bundle protocol.

An artifact has `format: "delvetalk-room-artifact-v1"`, `content`, and `protocol`.
Content retains exact source, complete AST, scene/upstream profiles, provenance,
initial variables, membership, and compiler/parser source-file hashes. If the
translation includes `bridge_binary_sha256`, that executable pin is retained too;
the direct compiler records it. `protocol.roomArtifact.contentSha256` binds the
entire content using canonical UTF-8 JSON: sorted object keys, compact separators,
literal Unicode, no NaN. Source strings preserve their original newlines.

- `validate_artifact(artifact)` checks the bindings and returns the SHA256 of the
  whole canonical artifact. It does not prove parser/compiler correctness.
- `store_artifact(directory, artifact)` publishes `<id>.json` atomically without
  replacing an existing file. `load_artifact(directory, id)` verifies exact bytes
  and bindings. These are local files, not network identities or signatures.
- `room_view(root, artifact, object_id)` requires exact equality between the
  committed protocol and artifact protocol. It includes complete source, AST,
  pins, prose spans/source slices, committed choices and availability, decoded
  variables, and the retained root.
- Missing or mismatched artifacts, corrupt bindings, or malformed presentation
  state produce a raw view with no scene actions. Exact raw state remains visible.
- `choice_request(view, index, principal, intent)` and `start_request(...)`
  construct requests with a copied exact root. They neither execute choices nor
  decide their admission. `html_view(view)` escapes all text and embeds no script,
  external resource, or active form submission.

The source desk can wrap its tested translation, store the wrapper, and adopt its
protocol while publishing the artifact ID to readers. History exports should
retain the entire artifact file and require its validated protocol/content binding
to match the protocol in the retained request. Exporting only an artifact path
would leave a hidden dependency on someone's filesystem.

## Evolution boundaries

Changing source, compiler pins, AST, initial configuration, or lowered protocol
creates a different artifact identity. Reprogramming a live room requires an
explicit state migration and current authority; the renderer does not repair or
reinterpret old state. Passage indices and choice indices are compiler-local:
reordering a new scene can invalidate old state, even when labels look familiar.
Preserve the old artifact with its history. Loading an old valid artifact does
not require the currently installed compiler to match its historical pins.

This cycle provides local immutable storage, source-bound views and executable
shared journeys. It does not provide a web server, a public identity boundary,
personal inventories, concurrent per-participant sessions, or external call
delivery. Calls remain ordered durable intent batches. Room views deliberately
do not rerun initial entry effects or infer a dynamic inventory from prose.

`conformance/test_room.py` exercises the moth repair journey through actual Lean
receipts, stale competing views, current authority and guard refusal, retained
receipt replay, renderer purity, exact source spans, HTML escaping, byte-digest
storage, missing/substituted artifacts, CLI requests, and raw fallback after an
incompatible state migration.
