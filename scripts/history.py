#!/usr/bin/env python3
"""Local hash-linked admission history bundles. Hashes identify; they do not authorize."""
import argparse
from decimal import Decimal
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world
import runtime_profile

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'delvetalk-history-v1'
EMPTY = {'objects': {}, 'receipts': []}
SHA = re.compile('[0-9a-f]{64}\\Z')


def loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('invalid JSON number: ' + value)
    return json.loads(text, parse_float=Decimal, object_pairs_hook=pairs, parse_constant=invalid)


def canonical(value):
    def order(item):
        if isinstance(item, dict):
            return {key: order(item[key]) for key in sorted(item)}
        if isinstance(item, list):
            return [order(child) for child in item]
        return item
    return world.wire_dumps(order(value)).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(label + ' has missing or unknown fields')


def runtime(profile):
    if profile not in world.PROFILES:
        raise ValueError('unknown profile')
    return {'name': profile, 'platform': {'system': platform.system(), 'machine': platform.machine()},
            'files': runtime_profile.file_hashes(profile, root=ROOT)}


def check_runtime(pinned, local, policy):
    if policy not in ('exact', 'same-sources'):
        raise ValueError('unknown runtime policy')
    exact(pinned, ['name', 'platform', 'files'], 'pinned runtime')
    exact(pinned['platform'], ['system', 'machine'], 'pinned platform')
    if policy == 'exact':
        if canonical(pinned) != canonical(local):
            raise ValueError('local runtime/source/platform does not match pinned profile')
        return
    binary = '.lake/build/bin/' + world.PROFILES[local['name']][0]
    if (pinned['name'] != local['name'] or not isinstance(pinned['files'], dict)
            or set(pinned['files']) != set(local['files']) or binary not in pinned['files']
            or canonical({k: v for k, v in pinned['files'].items() if k != binary})
            != canonical({k: v for k, v in local['files'].items() if k != binary})):
        raise ValueError('local runtime sources/toolchain/closure do not match pinned profile')


def blob_path(bundle, sha):
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ValueError('invalid blob SHA256')
    return Path(bundle) / 'blobs' / sha


def store_bytes(bundle, raw):
    sha = hashlib.sha256(raw).hexdigest()
    path = blob_path(bundle, sha)
    if not path.exists():
        path.write_bytes(raw)
    elif file_hash(path) != sha:
        raise ValueError('existing blob digest mismatch')
    return sha


def store_file(bundle, path):
    sha = file_hash(path)
    target = blob_path(bundle, sha)
    if not target.exists():
        shutil.copyfile(path, target)
        with target.open('rb') as stream:
            os.fsync(stream.fileno())
    if file_hash(target) != sha:
        raise ValueError('source changed while copying artifact')
    return sha


def read_blob(bundle, sha):
    path = blob_path(bundle, sha)
    if file_hash(path) != sha:
        raise ValueError('blob digest mismatch: ' + sha)
    return path


def journal_attachments(directory):
    """Only matching request journals are included, not unrelated directory state."""
    result = {}
    if directory is None:
        return result
    for path in sorted(Path(directory).glob('*.json')):
        entry = loads(path.read_bytes())
        if isinstance(entry, dict) and isinstance(entry.get('request'), dict):
            result.setdefault(digest(entry['request']), []).append(path)
    return result


def declared_files(value):
    """Known source envelopes declare file custody, never executable permission."""
    result = {}
    def walk(item):
        if isinstance(item, list):
            for child in item:
                walk(child)
        if not isinstance(item, dict):
            return
        pins = {}
        if item.get('format') == 'delvetalk-lowered-v1':
            translation = item['translation']
            pins = {**translation['files'], 'syntaxes/registry.json': translation['registry_sha256']}
        elif item.get('format') == 'delvetalk-room-artifact-v1' and 'content' in item:
            pins = item['content']['pins']
        if 'bridge_binary_sha256' in item:
            pins = {**pins, 'scene/spween-bridge/target/debug/delvetalk-spween': item['bridge_binary_sha256']}
        for name, sha in pins.items():
            if name in result and result[name] != sha:
                raise ValueError('conflicting source dependency pins')
            result[name] = sha
        for child in item.values():
            walk(child)
    walk(value)
    return result


def program_targets(request, reply):
    """Extract preservation obligations, never evaluate a program or admit it.

    A committed inputFrom's exact candidate is already in Lean's retained result.
    Refused transactions install nothing and do not retain intermediate results.
    """
    if not isinstance(request, dict):
        raise ValueError('history request must be an object')
    targets = []
    if reply.get('kind') == 'committed':
        data = reply.get('data', {})
        allocated = data.get('allocated', {})
        for root in allocated.values():
            targets.append((root.get('protocol'), False))
        if request.get('op') == 'transaction':
            # An exact null preimage plus a non-null resulting root identifies a
            # newly allocated child without interpreting factory expressions.
            for object_id, expected in request.get('reads', {}).items():
                root = data.get('roots', {}).get(object_id)
                if expected is None and isinstance(root, dict):
                    targets.append((root.get('protocol'), False))
            for call in request.get('calls', []):
                if (isinstance(call, dict) and call.get('op') == 'reprogram'
                        and call.get('object') in request.get('reads', {})
                        and request['reads'][call['object']] is None):
                    if call['object'] not in allocated:
                        # Older receipts expose only final roots; their original
                        # intermediate source custody cannot be invented.
                        raise ValueError('allocation followed by reprogram requires a retained allocation trace')
    if request.get('op') != 'transaction':
        return [(request.get('protocol'), request.get('op') == 'reprogram'), *targets]
    for call in request.get('calls', []):
        if not isinstance(call, dict) or call.get('op') != 'reprogram':
            continue
        if 'inputFrom' not in call:
            targets.append((call.get('protocol'), True))
        elif reply.get('kind') == 'committed':
            index = call['inputFrom']
            results = reply.get('data', {}).get('results', [])
            if type(index) is not int or index < 0 or index >= len(results) or not isinstance(results[index], dict):
                raise ValueError('retained transaction has no reprogram candidate result')
            targets.append((results[index].get('protocol'), True))
    return targets


def lowered_protocol(artifact, bundle):
    """Check source/provenance integrity without executing its claimed adapter."""
    exact(artifact, ['format', 'syntax', 'source', 'translation', 'target', 'lowered', 'lowered_sha256'], 'lowering artifact')
    source = artifact['source']
    exact(source, ['encoding', 'text', 'sha256'], 'lowering source')
    if (source['encoding'] != 'utf-8' or not isinstance(source['text'], str)
            or hashlib.sha256(source['text'].encode('utf-8')).hexdigest() != source['sha256']):
        raise ValueError('lowering source digest mismatch')
    translation = artifact['translation']
    exact(translation, ['syntax', 'adapter', 'validator', 'registry_sha256', 'files', 'pin'], 'translation pin')
    if translation['syntax'] != artifact['syntax'] or translation['pin'] != digest({
            key: value for key, value in translation.items() if key != 'pin'}):
        raise ValueError('translation identity mismatch')
    if artifact['lowered_sha256'] != digest(artifact['lowered']):
        raise ValueError('lowered value digest mismatch')
    registry = loads(read_blob(bundle, translation['registry_sha256']).read_bytes())
    adapter = registry['syntaxes'][artifact['syntax']]
    validator = registry['targets'][artifact['target']]
    if (canonical(adapter) != canonical(translation['adapter'])
            or canonical(validator) != canonical(translation['validator'])
            or adapter.get('reviewed') is not True or adapter['target'] != artifact['target']):
        raise ValueError('translation does not match pinned registry')
    closure = set(registry['closure'] + adapter.get('closure', []) + validator.get('closure', []) + ['scripts/translate.py'])
    if set(translation['files']) != closure:
        raise ValueError('translation dependency closure mismatch')
    for sha in translation['files'].values():
        read_blob(bundle, sha)
    if artifact['target'] == 'local-protocol-v1':
        return artifact['lowered']
    if artifact['target'] == 'spween-protocol-bundle-v1':
        return artifact['lowered']['protocol']
    return None


def verify_sources(request, refs, bundle, inline_reprogram, reply):
    # The request itself is a complete inline protocol. Original surface syntax
    # is a separate artifact; do not claim to have reconstructed missing text.
    targets = program_targets(request, reply)
    programs, rooms = [], []
    def envelopes(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from envelopes(child)
        elif isinstance(value, list):
            for child in value:
                yield from envelopes(child)
    for ref in refs:
        exact(ref, ['sha256', 'name'], 'artifact reference')
        path = read_blob(bundle, ref['sha256'])
        try:
            value = loads(path.read_bytes())
        except (ValueError, UnicodeError):
            continue  # Opaque binary artifacts do not assert a source binding.
        if isinstance(value, dict):
            for sha in declared_files(value).values():
                read_blob(bundle, sha)
            for item in envelopes(value):
                if item.get('format') == 'delvetalk-lowered-v1':
                    programs.append(canonical(lowered_protocol(item, bundle)))
                if item.get('format') == 'delvetalk-room-artifact-v1' and 'content' in item:
                    spec = importlib.util.spec_from_file_location('history_room', ROOT / 'scene/room.py')
                    room = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(room)
                    room.validate_artifact(json.loads(canonical(item)))
                    rooms.append(canonical(item['protocol']))
    for protocol, reprogram in targets:
        encoded = canonical(protocol)
        if reprogram and not inline_reprogram and encoded not in programs + rooms:
            raise ValueError('reprogram has no matching source artifact; supply its journal or explicitly select inline-only provenance')
        if isinstance(protocol, dict) and 'roomArtifact' in protocol and encoded not in rooms:
            raise ValueError('protocol references a missing or mismatched room artifact')


def replay(manifest, bundle, database, *, expected_genesis, expected_head, base_head=None, runtime_policy='exact'):
    exact(manifest, ['format', 'genesis', 'entries', 'head', 'worldSha256', 'inlineReprogram'], 'history manifest')
    if manifest['format'] != FORMAT or type(manifest['inlineReprogram']) is not bool:
        raise ValueError('unsupported history format')
    genesis = manifest['genesis']
    exact(genesis, ['id', 'profile', 'world'], 'history genesis')
    genesis_id = digest({key: value for key, value in genesis.items() if key != 'id'})
    if genesis['id'] != genesis_id or genesis_id != expected_genesis:
        raise ValueError('trusted genesis mismatch')
    if manifest['head'] != expected_head:
        raise ValueError('trusted head mismatch')
    if canonical(genesis['world']) != canonical(EMPTY):
        raise ValueError('v1 requires explicit empty genesis')
    pinned = genesis['profile']
    local_runtime = runtime(pinned['name'])
    check_runtime(pinned, local_runtime, runtime_policy)
    for sha in pinned['files'].values():
        read_blob(bundle, sha)
    if not isinstance(manifest['entries'], list):
        raise ValueError('entries must be ordered array')
    previous = genesis_id
    base_seen = base_head is None or base_head == genesis_id
    # Never execute a binary from the bundle. Only the explicitly matching local
    # trusted installation is used, with a new isolated custody database.
    Path(database).write_bytes(canonical(EMPTY))
    for index, entry in enumerate(manifest['entries']):
        exact(entry, ['index', 'previous', 'request', 'reply', 'worldSha256', 'artifacts', 'id'], 'history entry')
        if type(entry['index']) is not int or entry['index'] != index or entry['previous'] != previous:
            raise ValueError('history order or gap mismatch')
        if entry['id'] != digest({key: value for key, value in entry.items() if key != 'id'}):
            raise ValueError('history commit digest mismatch')
        if not isinstance(entry['artifacts'], list):
            raise ValueError('artifact references must be an array')
        verify_sources(entry['request'], entry['artifacts'], bundle, manifest['inlineReprogram'], entry['reply'])
        reply = world.exchange(database, entry['request'], profile=pinned['name'])
        if canonical(reply) != canonical(entry['reply']):
            raise ValueError('Lean receipt mismatch at entry ' + str(index))
        state = loads(Path(database).read_bytes())
        # Retained admission history has precisely one receipt per new intent.
        # Repeated reads/retries/conflicting intent uses are not new commits.
        if len(state['receipts']) != index + 1:
            raise ValueError('entry is not a new retained admission attempt')
        if digest(state) != entry['worldSha256']:
            raise ValueError('Lean world mismatch at entry ' + str(index))
        previous = entry['id']
        base_seen = base_seen or previous == base_head
    if previous != expected_head:
        raise ValueError('history truncated or final head mismatch')
    if not base_seen:
        raise ValueError('known base head is not a prefix of this history')
    final = loads(Path(database).read_bytes())
    if digest(final) != manifest['worldSha256']:
        raise ValueError('final world digest mismatch')
    if canonical(runtime(pinned['name'])) != canonical(local_runtime):
        raise ValueError('runtime changed during history verification')
    return {'format': FORMAT, 'genesis': genesis_id, 'head': previous,
            'entries': len(manifest['entries']), 'worldSha256': digest(final),
            'runtimePolicy': runtime_policy, 'localRuntime': local_runtime,
            'localRuntimeSha256': digest(local_runtime), 'originRuntimeSha256': digest(pinned),
            'proofScope': 'exact-artifact-replay' if runtime_policy == 'exact' else 'source-matched-local-replay'}


def export_history(database, bundle, *, profile='transactions', attachments=None, journals=None, inline_reprogram=False,
                   prefix_bundle=None, expected_prefix_genesis=None, expected_prefix_head=None):
    database, bundle = Path(database).resolve(), Path(bundle).resolve()
    if bundle.exists():
        raise ValueError('export destination already exists')
    supplied = (prefix_bundle is not None, expected_prefix_genesis is not None, expected_prefix_head is not None)
    if any(supplied) and not all(supplied):
        raise ValueError('prefix bundle requires explicit trusted genesis and head')
    with open(str(database) + '.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        snapshot = loads(database.read_bytes())
    exact(snapshot, ['objects', 'receipts'], 'world snapshot')
    if not isinstance(snapshot['receipts'], list):
        raise ValueError('snapshot receipts must be ordered array')
    prefix = None
    if prefix_bundle is not None:
        prefix_bundle = Path(prefix_bundle).resolve()
        prefix = loads((prefix_bundle / 'manifest.json').read_bytes())
        with tempfile.TemporaryDirectory(prefix='delvetalk-history-prefix-') as directory:
            replay(prefix, prefix_bundle, Path(directory) / 'world.json',
                   expected_genesis=expected_prefix_genesis, expected_head=expected_prefix_head)
        if prefix['inlineReprogram'] != inline_reprogram:
            raise ValueError('prefix source provenance policy differs')
        if len(prefix['entries']) > len(snapshot['receipts']):
            raise ValueError('snapshot is shorter than trusted prefix')
        for entry, retained in zip(prefix['entries'], snapshot['receipts']):
            if (canonical(entry['request']) != canonical(retained['request'])
                    or canonical(entry['reply']) != canonical(retained['receipt'])):
                raise ValueError('snapshot admission does not match trusted prefix')
    bundle.mkdir(parents=True, mode=0o700)
    (bundle / 'blobs').mkdir(mode=0o700)
    pinned = runtime(profile)
    for name, sha in pinned['files'].items():
        if store_file(bundle, ROOT / name) != sha:
            raise ValueError('runtime changed during export')
    attached = journal_attachments(journals)
    for request_sha, paths in (attachments or {}).items():
        if not SHA.fullmatch(request_sha) or not isinstance(paths, list):
            raise ValueError('attachments map request SHA256 to file path arrays')
        attached.setdefault(request_sha, []).extend(Path(path) for path in paths)
    genesis = {'profile': pinned, 'world': EMPTY}
    genesis['id'] = digest(genesis)
    if prefix is not None:
        if canonical(prefix['genesis']) != canonical(genesis):
            raise ValueError('prefix replay profile or genesis differs')
        # Copy only referenced and declared content, never an unrelated blob
        # merely placed in the source directory. Rehash every copied byte.
        required = set(prefix['genesis']['profile']['files'].values())
        for entry in prefix['entries']:
            for ref in entry['artifacts']:
                required.add(ref['sha256'])
                try:
                    artifact = loads(read_blob(prefix_bundle, ref['sha256']).read_bytes())
                except (ValueError, UnicodeError):
                    continue
                required.update(declared_files(artifact).values())
        for sha in required:
            if store_file(bundle, read_blob(prefix_bundle, sha)) != sha:
                raise ValueError('prefix blob changed while copying')
    manifest = {'format': FORMAT, 'genesis': genesis, 'entries': [], 'head': genesis['id'],
                'worldSha256': digest(snapshot), 'inlineReprogram': inline_reprogram}
    with tempfile.TemporaryDirectory(prefix='delvetalk-history-export-') as directory:
        reconstructed = Path(directory) / 'world.json'
        reconstructed.write_bytes(canonical(EMPTY))
        used = set()
        for index, retained in enumerate(snapshot['receipts']):
            exact(retained, ['request', 'receipt'], 'retained admission')
            request = retained['request']
            request_sha = digest(request)
            used.add(request_sha)
            prior = prefix['entries'][index] if prefix is not None and index < len(prefix['entries']) else None
            if prior is not None:
                # Catalog growth, source discovery and mutable local file paths
                # must not annotate already accepted commits differently.
                refs = prior['artifacts']
            else:
                refs = [{'name': Path(path).name, 'sha256': store_file(bundle, path)}
                        for path in attached.get(request_sha, [])]
                for ref in list(refs):
                    try:
                        artifact = loads(read_blob(bundle, ref['sha256']).read_bytes())
                    except (ValueError, UnicodeError):
                        continue
                    for name, sha in declared_files(artifact).items():
                        if blob_path(bundle, sha).is_file():
                            read_blob(bundle, sha)
                            refs.append({'name': name, 'sha256': sha})
                            continue
                        dependency = (ROOT / name).resolve()
                        if not dependency.is_relative_to(ROOT) or file_hash(dependency) != sha:
                            raise ValueError('source dependency missing or changed: ' + name)
                        refs.append({'name': name, 'sha256': store_file(bundle, dependency)})
            verify_sources(request, refs, bundle, inline_reprogram, retained['receipt'])
            reply = world.exchange(reconstructed, request, profile=profile)
            if canonical(reply) != canonical(retained['receipt']):
                raise ValueError('snapshot receipt does not replay at entry ' + str(index))
            state = loads(reconstructed.read_bytes())
            if len(state['receipts']) != index + 1:
                raise ValueError('snapshot contains duplicate/nonretained admission')
            entry = {'index': index, 'previous': manifest['head'], 'request': request,
                     'reply': reply, 'worldSha256': digest(state), 'artifacts': refs}
            entry['id'] = digest(entry)
            if prior is not None:
                if canonical(entry) != canonical(prior):
                    raise ValueError('replayed prefix commit differs')
                entry = prior
            manifest['entries'].append(entry)
            manifest['head'] = entry['id']
        if canonical(loads(reconstructed.read_bytes())) != canonical(snapshot):
            raise ValueError('snapshot state cannot be reconstructed from retained admissions')
        unknown = set(attachments or {}) - used
        if unknown:
            raise ValueError('attachment request digest absent from retained history')
    # This final check ensures compilation/source edits during export cannot be
    # mislabeled as the initially pinned runtime. No silent fallback compilation.
    if canonical(runtime(profile)) != canonical(pinned):
        raise ValueError('runtime changed during history reconstruction')
    with (bundle / 'manifest.json').open('xb') as stream:
        stream.write(canonical(manifest) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    for directory in (bundle / 'blobs', bundle, bundle.parent):
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return {'genesis': genesis['id'], 'head': manifest['head'], 'entries': len(manifest['entries']),
            'worldSha256': manifest['worldSha256']}


def verify_history(bundle, *, expected_genesis, expected_head, output=None, base_head=None, runtime_policy='exact'):
    bundle = Path(bundle).resolve()
    manifest = loads((bundle / 'manifest.json').read_bytes())
    with tempfile.TemporaryDirectory(prefix='delvetalk-history-verify-') as directory:
        database = Path(directory) / 'world.json'
        result = replay(manifest, bundle, database, expected_genesis=expected_genesis,
                        expected_head=expected_head, base_head=base_head, runtime_policy=runtime_policy)
        if output is not None:
            # Exclusive creation: an import must never silently replace custody.
            output = Path(output).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            with open(str(output) + '.lock', 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile('wb', dir=output.parent, delete=False) as target:
                        temporary = target.name
                        target.write(database.read_bytes())
                        target.flush()
                        os.fsync(target.fileno())
                    os.link(temporary, output)  # Atomic visibility and no replacement.
                finally:
                    if temporary is not None:
                        os.unlink(temporary)
                fd = os.open(output.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export')
    export.add_argument('database', type=Path)
    export.add_argument('bundle', type=Path)
    export.add_argument('--profile', choices=world.PROFILES, default='transactions')
    export.add_argument('--attachments', type=Path, help='JSON map of canonical request SHA256 to exact artifact file paths')
    export.add_argument('--journals', type=Path, help='include exact matching request journals as source artifacts')
    export.add_argument('--inline-reprogram', action='store_true', help='explicitly accept missing original syntax; retain only inline protocol')
    export.add_argument('--prefix-bundle', type=Path)
    export.add_argument('--prefix-genesis', help='trusted genesis of preserved prefix')
    export.add_argument('--prefix-head', help='trusted head of preserved prefix')
    verify = commands.add_parser('verify')
    verify.add_argument('bundle', type=Path)
    verify.add_argument('--genesis', required=True)
    verify.add_argument('--head', required=True)
    verify.add_argument('--base-head', help='additionally require this previously accepted commit as a prefix')
    verify.add_argument('--output', type=Path, help='exclusively create reconstructed local custody database')
    verify.add_argument('--runtime-policy', choices=('exact', 'same-sources'), default='exact',
                        help='explicitly permit a different local binary/platform only when all source pins match')
    args = parser.parse_args()
    try:
        if args.command == 'export':
            result = export_history(args.database, args.bundle, profile=args.profile,
                                    attachments=loads(args.attachments.read_bytes()) if args.attachments else None,
                                    journals=args.journals, inline_reprogram=args.inline_reprogram,
                                    prefix_bundle=args.prefix_bundle, expected_prefix_genesis=args.prefix_genesis,
                                    expected_prefix_head=args.prefix_head)
        else:
            result = verify_history(args.bundle, expected_genesis=args.genesis, expected_head=args.head,
                                    output=args.output, base_head=args.base_head, runtime_policy=args.runtime_policy)
        print(world.wire_dumps(result))
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        print('history: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
