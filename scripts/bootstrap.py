#!/usr/bin/env python3
"""A local inhabited repair cafe: participants improve the world they share."""
import argparse
import ctypes
import fcntl
import importlib.util
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples/inhabited-bootstrap'
CAFE, TABLE, CANDIDATE = 'cafe:repair', 'table:empty', 'proposal:open-window'
SIGN, SIGN_CANDIDATE = 'sign:shared-lamp', 'proposal:teaching-sign'
PARTICIPANTS = ['iris', 'moss']


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


room = module('bootstrap_room', 'scene/room.py')
projection = module('bootstrap_projection', 'scene/projection.py')
desk_module = module('bootstrap_desk', 'scripts/desk.py')
history = module('bootstrap_history', 'scripts/history.py')
loads, canonical = desk_module.loads, desk_module.canonical


def scoped(commands, *, managers=()):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': {command: PARTICIPANTS for command in commands},
            'reprogram': list(managers), 'law': ['local-operator']}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def save_new(path, value):
    with Path(path).open('xb') as stream:
        stream.write(canonical(value) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())



def preserve_dependencies(directory, artifact):
    custody = Path(directory) / 'artifacts/pins'
    (custody / 'blobs').mkdir(parents=True, exist_ok=True)
    for name, sha in history.declared_files(artifact).items():
        if history.blob_path(custody, sha).is_file():
            history.read_blob(custody, sha)
            continue
        source = (ROOT / name).resolve()
        if not source.is_relative_to(ROOT) or history.file_hash(source) != sha:
            raise ValueError('original source dependency missing or changed: ' + name)
        if history.store_file(custody, source) != sha:
            raise ValueError('source dependency changed during preservation: ' + name)


def preserve_lowering(directory, source):
    artifact = desk_module.translate.translate('protocol-json@1', source)
    identity = history.digest(artifact)
    path = Path(directory) / 'artifacts/lowerings' / (identity + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    value = desk_module.immutable(path, artifact)
    if history.digest(value) != identity:
        raise ValueError('stored lowering artifact mismatch')
    preserve_dependencies(directory, artifact)
    return artifact


def preserve_build(directory, identity):
    artifact = desk_module.load_artifact(Path(directory) / 'artifacts', identity)
    preserve_dependencies(directory, artifact)
    return artifact


def run_bootstrap(directory, *, profile='transactions'):
    directory = Path(directory).resolve()
    if profile not in ('transactions', 'compiled'):
        raise ValueError('bootstrap requires transactions or compiled admission')
    selected_binary = desk_module.world.PROFILES[profile][0]
    for name in ('delvetalk-world', selected_binary):
        require((ROOT / '.lake/build/bin' / name).is_file(), 'Build ' + name + ' first')
    require(room.lower.BRIDGE.is_file() if hasattr(room.lower, 'BRIDGE') else
            (ROOT / 'scene/spween-bridge/target/debug/delvetalk-spween').is_file(), 'Build the pinned Spween bridge first')
    directory.mkdir(parents=True, exist_ok=True)
    require(not any(directory.iterdir()), 'bootstrap requires an empty directory; keep existing worlds and receipts')
    runtime = history.runtime(profile)
    observations = directory / 'observations'
    observations.mkdir()
    artifacts = directory / 'artifacts'
    desk = desk_module.Desk(directory / 'world.json', artifacts, profile=profile)
    events = []

    def record(label, receipt, expected='committed'):
        events.append({'label': label, 'receipt': receipt})
        with (directory / 'events.jsonl').open('ab') as stream:
            stream.write(canonical(events[-1]) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        require(receipt.get('kind') == expected, label + ': ' + str(receipt))
        return receipt

    def send(label, request, expected='committed'):
        return record(label, desk.exchange(request), expected)

    def inspect(object_id=CAFE):
        return desk.inspect(object_id)

    def view(artifact, filename=None):
        result = room.room_view(inspect(), artifact, CAFE)
        require(result['mode'] == 'room', str(result))
        if filename:
            save_new(observations / filename, result)
        return result

    initial_artifact = room.compile_artifact((EXAMPLES / 'cafe.scene').read_text())
    initial_id = room.store_artifact(artifacts / 'rooms', initial_artifact)
    preserve_dependencies(directory, initial_artifact)
    preserve_lowering(directory, (EXAMPLES / 'table.json').read_bytes())
    preserve_lowering(directory, (ROOT / 'protocols/source-desk/protocol.json').read_bytes())
    # Explicit future command grants keep authority unchanged across adoption.
    command_names = ['start', 'choose:0:0', 'choose:0:1', 'choose:0:2', 'choose:1:0']
    send('The repair cafe opens', {'op': 'create', 'object': CAFE, 'principal': 'local-operator',
                                  'intent': 'open-cafe', 'protocol': initial_artifact['protocol'],
                                  'law': scoped(command_names, managers=['moss'])})
    send('An empty table reserves a place for another activity', {'op': 'create', 'object': TABLE,
         'principal': 'local-operator', 'intent': 'reserve-table',
         'protocol': loads((EXAMPLES / 'table.json').read_bytes()), 'law': scoped([], managers=PARTICIPANTS)})
    record('Iris opens a source desk', desk.create(CANDIDATE, 'iris', 'open-source-desk', {
        'profile': 'delvetalk-scoped-law-v1',
        'invoke': {'submit': ['iris'], 'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': ['moss']},
        'reprogram': [], 'law': ['local-operator']}))
    send('Iris enters the cafe', room.start_request(view(initial_artifact), 'iris', 'enter-cafe'))
    shared_before = view(initial_artifact, 'shared-before-repair.json')
    send('Iris aligns the wing', room.choice_request(shared_before, 0, 'iris', 'align-wing'))
    stale = send('Moss tries the spring from an old view', room.choice_request(shared_before, 1, 'moss', 'wind-stale'), 'refused')
    require(stale['data'] == 'stale read root', 'old view should be refused for its exact root')
    send('Moss reads again and winds the spring', room.choice_request(view(initial_artifact), 1, 'moss', 'wind-fresh'))
    repaired = view(initial_artifact, 'repaired-before-improvement.json')
    require(repaired['variables']['wing_aligned'] == ['bool', True] and
            repaired['variables']['spring_wound'] == ['bool', True], 'both repairs must be committed')
    # This migration is a participant-authored artifact, never an inferred reset.
    migration = loads((EXAMPLES / 'migration.json').read_bytes())
    pending = record('Iris proposes opening a window', desk.submit(
        CANDIDATE, 'iris', 'propose-window', inspect(CANDIDATE), 'spween-scene-i64@1',
        (EXAMPLES / 'cafe-improved.scene').read_bytes(),
        (EXAMPLES / 'improvement-scenarios.json').read_bytes(), migration, CAFE))['data']['root']
    compiled = record('The compiler checks the proposal without adopting it',
                      desk.check(CANDIDATE, 'compiler', 'compile-window', pending))
    ready = compiled['data']['root']
    require(ready['state']['status'] == 'ready', 'proposal compilation failed: ' + str(ready['state']['diagnostics']))
    preserve_build(directory, ready['state']['artifact'])
    require(inspect()['protocol'] == initial_artifact['protocol'], 'compiling must not change the cafe')
    adopted = record('Moss reviews the migration and adopts the window atomically',
                     desk.adopt(CANDIDATE, CAFE, 'moss', 'adopt-window', ready, repaired['root']))
    improved_id = ready['state']['roomArtifact']
    improved_artifact = room.load_artifact(artifacts / 'rooms', improved_id)
    improved = view(improved_artifact, 'after-adoption.json')
    require(improved['variables']['wing_aligned'] == ['bool', True] and
            improved['variables']['spring_wound'] == ['bool', True], 'migration must preserve both repairs')
    stale_program = send('A pre-improvement view cannot dispatch into the new cafe',
                         room.choice_request(repaired, 1, 'moss', 'old-program-view'), 'refused')
    require(stale_program['data'] == 'stale read root', 'old program root must be refused')
    send('Moss reads the new source-bound view and releases the moth',
         room.choice_request(improved, 2, 'moss', 'release-moth'))
    send('Moss leaves a chalk star using the newly proposed action',
         room.choice_request(view(improved_artifact), 0, 'moss', 'chalk-star'))
    final_view = view(improved_artifact, 'iris-sees-the-chalk-star.json')
    require(final_view['variables']['chalk_star'] == ['bool', True], 'the second participant must use the improvement')
    # A second improvement changes the view program itself, in pure Bend.
    sign_lowering = preserve_lowering(directory, (ROOT / 'scene/projections/sign-v1.json').read_bytes())
    sign_protocol = sign_lowering['lowered']
    sign_created = send('A shared lamp sign joins the cafe', {
        'op': 'create', 'object': SIGN, 'principal': 'local-operator', 'intent': 'create-sign',
        'protocol': sign_protocol, 'law': scoped(['light'], managers=['iris'])})
    sign_before = projection.project(sign_created['data']['root'], SIGN)
    save_new(observations / 'sign-before-improvement.json', sign_before)
    record('Moss opens a proposal to improve the sign itself', desk.create(
        SIGN_CANDIDATE, 'moss', 'open-sign-desk', {
            'profile': 'delvetalk-scoped-law-v1',
            'invoke': {'submit': ['moss'], 'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': ['iris']},
            'reprogram': [], 'law': ['local-operator']}))
    sign_pending = record('Moss proposes a pure Bend view program', desk.submit(
        SIGN_CANDIDATE, 'moss', 'propose-sign', inspect(SIGN_CANDIDATE), 'protocol-json@1',
        (ROOT / 'scene/projections/sign-v2.json').read_bytes(),
        (EXAMPLES / 'sign-scenarios.json').read_bytes(), sign_before['root']['state'], SIGN))['data']['root']
    sign_ready = record('The compiler checks the sign proposal',
                        desk.check(SIGN_CANDIDATE, 'compiler', 'compile-sign', sign_pending))['data']['root']
    require(sign_ready['state']['status'] == 'ready', 'sign proposal did not compile')
    preserve_build(directory, sign_ready['state']['artifact'])
    record('Iris adopts the proposed view program', desk.adopt(
        SIGN_CANDIDATE, SIGN, 'iris', 'adopt-sign', sign_ready, sign_before['root']))
    sign_after = projection.project(inspect(SIGN), SIGN)
    save_new(observations / 'sign-after-improvement.json', sign_after)
    require(sign_after['source'] != sign_before['source'], 'a different pure view program must be installed')
    require(sign_after['data']['prose'] != sign_before['data']['prose'], 'the new view must be visible')
    send('The old sign view is refused after its program changes',
         projection.request(sign_before, 'light', 'iris', 'old-sign-view'), 'refused')
    send('Iris uses the action offered by the new Bend view',
         projection.request(sign_after, 'light', 'iris', 'light-from-new-view'))
    sign_final = projection.project(inspect(SIGN), SIGN, 'details')
    require(sign_final['data']['prose'] == 'The lamp is lit.', 'the new view action must reach Lean admission')
    save_new(observations / 'sign-lamp-lit.json', sign_final)
    manifest = {'format': 'delvetalk-inhabited-bootstrap-v1', 'cafe': CAFE, 'table': TABLE,
                'candidate': CANDIDATE, 'sign': SIGN, 'signCandidate': SIGN_CANDIDATE, 'participants': PARTICIPANTS,
                'runtime': runtime, 'initialCafeArtifact': initial_id, 'currentCafeArtifact': improved_id,
                'extension': {'object': TABLE, 'status': 'empty', 'meaning': 'A separately admitted future activity; no game is installed'}}
    require(history.canonical(runtime) == history.canonical(history.runtime(profile)),
            'runtime changed during bootstrap; do not label mixed-runtime history')
    save_new(directory / 'manifest.json', manifest)
    report = {'format': 'delvetalk-inhabited-journey-v1', 'manifest': manifest, 'events': events,
              'adoption': adopted, 'finalView': final_view, 'tableRoot': inspect(TABLE),
              'sourceProposalRoot': inspect(CANDIDATE), 'signFinalView': sign_final,
              'signProposalRoot': inspect(SIGN_CANDIDATE)}
    save_new(directory / 'report.json', report)
    with (directory / 'cafe.html').open('x') as stream:
        stream.write(room.html_view(final_view))
    with (directory / 'sign.html').open('x') as stream:
        stream.write(projection.html_view(sign_final))
    return report


def inspect_view(directory, object_id=None, panel='main'):
    directory = Path(directory)
    manifest = loads((directory / 'manifest.json').read_bytes())
    object_id = object_id or manifest['cafe']
    desk = desk_module.Desk(directory / 'world.json', directory / 'artifacts',
                            profile=manifest.get('runtime', {}).get('name', 'transactions'))
    root = desk.inspect(object_id)
    artifact = None
    if object_id == manifest['cafe']:
        artifact = room.load_artifact(directory / 'artifacts/rooms', manifest['currentCafeArtifact'])
    if hasattr(room, 'inspect_object'):
        return room.inspect_object(root, object_id, artifact, panel=panel)
    if 'viewProgram' in root['protocol']:
        return projection.project(root, object_id, panel)
    return room.room_view(root, artifact, object_id)



def artifact_envelopes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from artifact_envelopes(child)
    elif isinstance(value, list):
        for child in value:
            yield from artifact_envelopes(child)


def artifact_programs(value):
    result = []
    for item in artifact_envelopes(value):
        if item.get('format') == 'delvetalk-room-artifact-v1' and 'content' in item:
            room.validate_artifact(item)
            result.append(item['protocol'])
        elif item.get('format') == 'delvetalk-lowered-v1':
            if item['target'] == 'local-protocol-v1':
                result.append(item['lowered'])
            elif item['target'] == 'spween-protocol-bundle-v1':
                result.append(item['lowered']['protocol'])
    return result


def artifact_catalog(directory):
    directory = Path(directory)
    artifacts = []
    for family in ('rooms', 'builds', 'lowerings'):
        for path in sorted((directory / 'artifacts' / family).glob('*.json')):
            if family == 'rooms':
                value = room.load_artifact(path.parent, path.stem)
            elif family == 'builds':
                value = desk_module.load_artifact(directory / 'artifacts', path.stem)
            else:
                value = loads(path.read_bytes())
                if history.digest(value) != path.stem:
                    raise ValueError('lowering artifact identity mismatch')
            artifacts.append((path, value, [canonical(program) for program in artifact_programs(value)]))
    return artifacts



def remember_history(directory, bundle, evidence):
    """Retain the verified prefix bytes independently of the exchange directory."""
    bundle = Path(bundle)
    manifest = history.loads((bundle / 'manifest.json').read_bytes())
    if manifest['head'] != evidence['head'] or manifest['genesis']['id'] != evidence['genesis']:
        raise ValueError('history checkpoint does not match verified evidence')
    checkpoint = Path(directory) / 'artifacts/history' / evidence['head']
    (checkpoint / 'blobs').mkdir(parents=True, exist_ok=True)
    blobs = set(manifest['genesis']['profile']['files'].values())
    blobs.update(ref['sha256'] for entry in manifest['entries'] for ref in entry['artifacts'])
    for sha in sorted(blobs):
        if history.store_file(checkpoint, history.read_blob(bundle, sha)) != sha:
            raise ValueError('checkpoint blob changed during preservation')
    retained = desk_module.immutable(checkpoint / 'manifest.json', manifest)
    if canonical(retained) != canonical(manifest):
        raise ValueError('existing history checkpoint differs')


def retained_prefix(directory, snapshot):
    checkpoints = []
    for path in (Path(directory) / 'artifacts/history').glob('*/manifest.json'):
        manifest = history.loads(path.read_bytes())
        if path.parent.name != manifest['head']:
            raise ValueError('checkpoint directory does not name its exact head')
        checkpoints.append((len(manifest['entries']), path.parent, manifest))
    if not checkpoints:
        return {}
    checkpoints.sort(key=lambda entry: (entry[0], str(entry[1])))
    length, path, manifest = checkpoints[-1]
    if len([entry for entry in checkpoints if entry[0] == length]) != 1:
        raise ValueError('multiple incomparable retained heads require an explicit custody decision')
    retained = snapshot['receipts']
    if length > len(retained) or any(canonical(entry['request']) != canonical(item['request']) or
                                   canonical(entry['reply']) != canonical(item['receipt'])
                                   for entry, item in zip(manifest['entries'], retained)):
        raise ValueError('world no longer extends its retained history checkpoint')
    return {'prefix_bundle': path, 'expected_prefix_genesis': manifest['genesis']['id'],
            'expected_prefix_head': manifest['head']}


def export_bootstrap(directory, bundle):
    """Export exact source-bound history, never silently substitute inline provenance."""
    directory, bundle = Path(directory).resolve(), Path(bundle).resolve()
    metadata = loads((directory / 'manifest.json').read_bytes())
    pinned = metadata.get('runtime')
    if not pinned or canonical(pinned) != canonical(history.runtime(pinned['name'])):
        raise ValueError('bootstrap runtime was not recorded or no longer matches the trusted installation')
    with open(str(directory / 'world.json') + '.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        snapshot = loads((directory / 'world.json').read_bytes())
    prefix = retained_prefix(directory, snapshot)
    artifacts = artifact_catalog(directory)
    attachments = {}
    prefix_length = (len(history.loads((prefix['prefix_bundle'] / 'manifest.json').read_bytes())['entries'])
                     if prefix else 0)
    for index, retained in enumerate(snapshot['receipts']):
        if index < prefix_length:
            continue  # Retained byte-identical source links come from the anchored checkpoint.
        request, reply = retained['request'], retained['receipt']
        paths = []
        for protocol, is_reprogram in history.program_targets(request, reply):
            if protocol is None:
                continue
            matches = [(path, value) for path, value, programs in artifacts if canonical(protocol) in programs]
            if not matches:
                if request.get('op') == 'create' or is_reprogram or 'roomArtifact' in protocol:
                    raise ValueError('missing original source artifact for request: ' + str(request.get('intent')))
                # A generated ordinary child is reproducible from the retained
                # receiving factory program and exact input. Do not invent a
                # separately authored source artifact for that derived program.
                continue
            # One stable source envelope is enough; duplicate wrappers are not new evidence.
            for path, value in sorted(matches, key=lambda pair: str(pair[0]))[:1]:
                paths.append(path)
                for sha in history.declared_files(value).values():
                    paths.append(history.read_blob(directory / 'artifacts/pins', sha))
        if request.get('op') == 'invoke' and request.get('command') in ('compiled', 'failed'):
            identity = request.get('input', {}).get('artifact')
            if identity:
                artifact = desk_module.load_artifact(directory / 'artifacts', identity)
                paths.append(directory / 'artifacts/builds' / (identity + '.json'))
                paths.extend(history.read_blob(directory / 'artifacts/pins', sha)
                             for sha in history.declared_files(artifact).values())
        attachments[history.digest(request)] = sorted(set(paths))
    if not snapshot['receipts']:
        raise ValueError('inhabited bootstrap has no retained creation history')
    first = history.digest(snapshot['receipts'][0]['request'])
    # The index is descriptive, but its bytes must be in the checked chain too.
    if not prefix:
        attachments[first].append(directory / 'manifest.json')
    result = history.export_history(directory / 'world.json', bundle, profile=pinned['name'],
                                    attachments=attachments, inline_reprogram=False, **prefix)
    if result['worldSha256'] != history.digest(snapshot):
        raise ValueError('world changed while preparing export; retry into a fresh destination')
    remember_history(directory, bundle, result)
    return {**result, 'bundle': str(bundle), 'inlineReprogram': False}


def _restore_contents(bundle, directory, *, expected_genesis, expected_head, base_head=None):
    """Populate private staging custody only after actual Lean replay succeeds."""
    bundle, directory = Path(bundle), Path(directory)
    result = history.verify_history(bundle, expected_genesis=expected_genesis,
                                    expected_head=expected_head, base_head=base_head,
                                    output=directory / 'world.json')
    manifest = history.loads((bundle / 'manifest.json').read_bytes())
    if manifest['inlineReprogram'] is not False:
        raise ValueError('inhabited reconstruction requires original source artifacts; inline-only bundles refuse')
    roots = loads((directory / 'world.json').read_bytes())['objects']
    metadata_by_hash = {}
    restored_rooms, restored_builds, restored_lowerings = set(), set(), set()
    source_values = []
    seen = set()
    for entry in manifest['entries']:
        for ref in entry['artifacts']:
            if ref['sha256'] in seen:
                continue
            seen.add(ref['sha256'])
            path = history.read_blob(bundle, ref['sha256'])
            try:
                value = history.loads(path.read_bytes())
            except (ValueError, UnicodeError):
                continue
            if not isinstance(value, dict):
                continue
            if value.get('format') == 'delvetalk-inhabited-bootstrap-v1':
                metadata_by_hash[history.digest(value)] = value
            source_values.append(value)
            if value.get('format') == 'delvetalk-desk-build-v1':
                restored_builds.add(desk_module.store_artifact(directory / 'artifacts', value))
            for item in artifact_envelopes(value):
                if item.get('format') == 'delvetalk-room-artifact-v1' and 'content' in item:
                    restored_rooms.add(room.store_artifact(directory / 'artifacts/rooms', item))
                elif item.get('format') == 'delvetalk-lowered-v1':
                    identity = history.digest(item)
                    path = directory / 'artifacts/lowerings' / (identity + '.json')
                    desk_module.immutable(path, item)
                    restored_lowerings.add(identity)
    if len(metadata_by_hash) != 1:
        raise ValueError('history must bind exactly one unambiguous inhabited-world index')
    metadata = next(iter(metadata_by_hash.values()))
    if canonical(metadata.get('runtime')) != canonical(manifest['genesis']['profile']):
        raise ValueError('inhabited index runtime differs from replay genesis')
    for key in ('cafe', 'table', 'candidate', 'sign', 'signCandidate'):
        if not isinstance(metadata.get(key), str) or metadata[key] not in roots:
            raise ValueError('inhabited index references a missing object: ' + key)
    if metadata['initialCafeArtifact'] not in restored_rooms or metadata['currentCafeArtifact'] not in restored_rooms:
        raise ValueError('inhabited index room artifact is absent from verified history')
    for key in ('candidate', 'signCandidate'):
        identity = roots[metadata[key]]['state'].get('artifact')
        if identity not in restored_builds:
            raise ValueError('candidate build artifact is absent from verified history')
    # Preserve original dependency bytes as custody, never as executable code.
    pins = directory / 'artifacts/pins'
    (pins / 'blobs').mkdir(parents=True, exist_ok=True)
    for value in source_values:
        for sha in history.declared_files(value).values():
            if history.store_file(pins, history.read_blob(bundle, sha)) != sha:
                raise ValueError('dependency changed during restore')
    save_new(directory / 'manifest.json', metadata)
    cafe = inspect_view(directory)
    sign = inspect_view(directory, metadata['sign'], 'details')
    if cafe['mode'] != 'room' or sign['mode'] != 'projection':
        raise ValueError('restored objects cannot render from restored artifact custody')
    with (directory / 'cafe.html').open('x') as stream:
        stream.write(room.html_view(cafe))
    with (directory / 'sign.html').open('x') as stream:
        stream.write(projection.html_view(sign))
    evidence = {**result, 'format': 'delvetalk-inhabited-reconstruction-v1',
                'rooms': sorted(restored_rooms), 'builds': sorted(restored_builds),
                'lowerings': sorted(restored_lowerings), 'cafe': metadata['cafe'], 'sign': metadata['sign'],
                'authority': 'none; caller-supplied genesis and head are identity anchors, not signatures'}
    save_new(directory / 'reconstruction.json', evidence)
    remember_history(directory, bundle, evidence)
    return evidence


def verify_bootstrap(bundle, *, expected_genesis, expected_head, base_head=None):
    with tempfile.TemporaryDirectory(prefix='delvetalk-bootstrap-verify-') as temporary:
        return _restore_contents(bundle, Path(temporary), expected_genesis=expected_genesis,
                                 expected_head=expected_head, base_head=base_head)


def _publish_directory(source, target):
    """Atomic OS no-replace publication, including protection for empty directories."""
    libc = ctypes.CDLL(None, use_errno=True)
    src, dst = os.fsencode(source), os.fsencode(target)
    if sys.platform == 'darwin':
        operation = libc.renamex_np
        operation.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        status = operation(src, dst, 4)  # RENAME_EXCL
    elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        operation = libc.renameat2
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        status = operation(-100, src, -100, dst, 1)  # AT_FDCWD, RENAME_NOREPLACE
    else:
        raise ValueError('atomic directory no-replace publication is unavailable on this platform')
    if status != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))
    fd = os.open(Path(target).parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def restore_bootstrap(bundle, directory, *, expected_genesis, expected_head, base_head=None):
    directory = Path(directory).absolute()
    if directory.exists() or directory.is_symlink():
        raise ValueError('restore destination already exists; use a fresh path')
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.bootstrap-restore-', dir=directory.parent) as temporary:
        result = _restore_contents(bundle, Path(temporary), expected_genesis=expected_genesis,
                                   expected_head=expected_head, base_head=base_head)
        _publish_directory(Path(temporary), directory)
    return {**result, 'directory': str(directory), 'view': str(directory / 'cafe.html')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    table = commands.add_parser('table', help='play a complete two-player match at an existing compiled cafe table')
    table.add_argument('directory', type=Path)
    export = commands.add_parser('export', help='bundle retained history and original source custody')
    export.add_argument('directory', type=Path)
    export.add_argument('bundle', type=Path)
    verify = commands.add_parser('verify', help='replay a caller-anchored bundle and check restored views')
    restore = commands.add_parser('restore', help='reconstruct world and artifacts into a fresh directory')
    for command in (verify, restore):
        command.add_argument('bundle', type=Path)
        command.add_argument('--genesis', required=True)
        command.add_argument('--head', required=True)
        command.add_argument('--base-head')
    restore.add_argument('directory', type=Path)
    run = commands.add_parser('run', help='perform the local journey in an empty directory')
    run.add_argument('directory', type=Path)
    run.add_argument('--profile', choices=('transactions', 'compiled'), default='transactions')
    view = commands.add_parser('view', help='read current committed state and exact source')
    view.add_argument('directory', type=Path)
    view.add_argument('--object')
    view.add_argument('--panel', default='main')
    view.add_argument('--html', action='store_true')
    act = commands.add_parser('act', help='dispatch one action from an explicitly saved view')
    act.add_argument('directory', type=Path)
    act.add_argument('--view', required=True, type=Path)
    act.add_argument('--principal', required=True)
    act.add_argument('--intent', required=True)
    action = act.add_mutually_exclusive_group(required=True)
    action.add_argument('--choice', type=int)
    action.add_argument('--start', action='store_true')
    action.add_argument('--action', help='action ID from a pure Bend projection')
    args = parser.parse_args()
    try:
        if args.command == 'table':
            journey = module('bootstrap_table_journey', 'scripts/table_journey.py')
            result = journey.run(args.directory)
            output = {'status': 'completed', 'object': result['object'], 'rounds': len(result['rounds']),
                      'view': journey.client.public_view(result['finalRoot']),
                      'report': str(args.directory.absolute() / 'table-journey/report.json')}
        elif args.command == 'export':
            output = export_bootstrap(args.directory, args.bundle)
        elif args.command in ('verify', 'restore'):
            arguments = {'expected_genesis': args.genesis, 'expected_head': args.head, 'base_head': args.base_head}
            result = (verify_bootstrap(args.bundle, **arguments) if args.command == 'verify' else
                      restore_bootstrap(args.bundle, args.directory, **arguments))
            output = {key: result[key] for key in ('genesis', 'head', 'entries', 'worldSha256')}
            output.update(status='verified' if args.command == 'verify' else 'restored',
                          artifacts={key: len(result[key]) for key in ('rooms', 'builds', 'lowerings')})
            if args.command == 'restore':
                output.update(directory=result['directory'], view=result['view'],
                              reconstruction=str(args.directory.absolute() / 'reconstruction.json'))
        elif args.command == 'run':
            result = run_bootstrap(args.directory, profile=args.profile)
            output = {'status': 'completed', 'directory': str(args.directory.resolve()),
                      'events': len(result['events']), 'participants': PARTICIPANTS,
                      'cafe': CAFE, 'table': TABLE, 'sourceProposal': CANDIDATE,
                      'view': str(args.directory.resolve() / 'cafe.html')}
        elif args.command == 'view':
            output = inspect_view(args.directory, args.object, args.panel)
            if args.html:
                print(projection.html_view(output) if output.get('mode') == 'projection' else room.html_view(output))
                return 0
        else:
            retained = loads(args.view.read_bytes())
            if args.action is not None:
                request = projection.request(retained, args.action, args.principal, args.intent)
            else:
                request = (room.start_request(retained, args.principal, args.intent) if args.start else
                           room.choice_request(retained, args.choice, args.principal, args.intent))
            metadata = loads((args.directory / 'manifest.json').read_bytes())
            if 'runtime' in metadata and canonical(metadata['runtime']) != canonical(history.runtime(metadata['runtime']['name'])):
                raise ValueError('world runtime pins changed; do not append admissions under an unrecorded runtime')
            desk = desk_module.Desk(args.directory / 'world.json', args.directory / 'artifacts',
                                    profile=metadata.get('runtime', {}).get('name', 'transactions'))
            output = desk.exchange(request)
        sys.stdout.buffer.write(canonical(output) + b'\n')
        return 1 if output.get('kind') == 'refused' else 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print('bootstrap: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
