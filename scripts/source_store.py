#!/usr/bin/env python3
"""Bounded immutable UTF-8 source custody; references grant no authority."""
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('source_store_translate', ROOT / 'scripts/translate.py')
translate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(translate)
canonical, loads = translate.canonical, translate.load_json
REF = 'delvetalk-source-ref-v1'
PROPOSAL = 'delvetalk-source-proposal-v1'
LIMITS = {'source': 512 * 1024, 'scenarios': 1024 * 1024}
MAX_BLOBS, MAX_TOTAL_BYTES = 10000, 128 * 1024 * 1024
SHA = re.compile(r'[0-9a-f]{64}\Z')


def limit(kind):
    if kind not in LIMITS:
        raise ValueError('source kind must be source or scenarios')
    return LIMITS[kind]


def validate_ref(ref, *, kind='scenarios'):
    if (not isinstance(ref, dict) or set(ref) != {'format', 'sha256', 'bytes', 'encoding'}
            or ref['format'] != REF or not isinstance(ref['sha256'], str) or not SHA.fullmatch(ref['sha256'])
            or type(ref['bytes']) is not int or not 0 <= ref['bytes'] <= limit(kind)
            or ref['encoding'] != 'utf-8'):
        raise ValueError('invalid bounded UTF-8 source reference')
    return ref


def reference(raw, *, kind='source'):
    if not isinstance(raw, bytes) or len(raw) > limit(kind):
        raise ValueError('source bytes exceed ' + kind + ' bound')
    raw.decode('utf-8')  # Preserve all bytes, including CRLF and BOM; never normalize.
    return {'format': REF, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'encoding': 'utf-8'}


def blob_path(artifact_store, sha):
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ValueError('invalid source blob identity')
    root = Path(artifact_store).expanduser().resolve()
    path = root / 'sources/blobs' / sha
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise ValueError('source blob escapes explicit artifact store or is a symlink')
    return path


def _read(path, maximum):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('source custody requires a regular file')
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('stored source exceeds byte bound')
    return raw


def read_bytes(artifact_store, ref, *, kind='source'):
    validate_ref(ref, kind=kind)
    raw = _read(blob_path(artifact_store, ref['sha256']), limit(kind))
    if reference(raw, kind=kind) != ref:
        raise ValueError('stored source does not match exact reference')
    return raw


def ref_for(artifact_store, sha, *, kind='source'):
    raw = _read(blob_path(artifact_store, sha), limit(kind))
    ref = reference(raw, kind=kind)
    if ref['sha256'] != sha:
        raise ValueError('stored source digest mismatch')
    return ref


def _publish(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        if _read(path, len(raw)) != raw:
            raise ValueError('immutable source custody content mismatch')
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink()


def store_bytes(artifact_store, raw, *, kind='source'):
    ref = reference(raw, kind=kind)
    path = blob_path(artifact_store, ref['sha256'])
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent.parent / '.source.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('source store busy; retry') from None
        if path.exists():
            read_bytes(artifact_store, ref, kind=kind)
            return ref
        files = list(path.parent.iterdir())
        if len(files) >= MAX_BLOBS or sum(p.stat().st_size for p in files) + len(raw) > MAX_TOTAL_BYTES:
            raise ValueError('source store retention bound reached; preserve existing blobs')
        _publish(path, raw)
    return ref


def adapter_pin(syntax):
    registry_raw = (ROOT / 'syntaxes/registry.json').read_bytes()
    registry = loads(registry_raw)
    adapter = registry['syntaxes'].get(syntax)
    if adapter is None or adapter.get('reviewed') is not True:
        raise ValueError('source references require a reviewed registered syntax')
    validator = registry['targets'][adapter['target']]
    paths = set(registry['closure'] + adapter.get('closure', []) + validator.get('closure', []) + ['scripts/translate.py'])
    files = {}
    for name in sorted(paths):
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('adapter dependency escapes repository')
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    identity = {'syntax': syntax, 'adapter': adapter, 'validator': validator,
                'registry_sha256': hashlib.sha256(registry_raw).hexdigest(), 'files': files}
    return {**identity, 'pin': hashlib.sha256(canonical(identity)).hexdigest()}


def validate_proposal(artifact_store, proposal, *, check_adapter=True):
    if (not isinstance(proposal, dict)
            or set(proposal) != {'format', 'syntax', 'sourceRef', 'scenariosRef', 'adapterPin'}
            or proposal['format'] != PROPOSAL):
        raise ValueError('invalid source reference proposal')
    declared_dependencies(proposal)
    source = read_bytes(artifact_store, proposal['sourceRef'], kind='source')
    scenarios = read_bytes(artifact_store, proposal['scenariosRef'], kind='scenarios')
    if check_adapter and canonical(proposal['adapterPin']) != canonical(adapter_pin(proposal['syntax'])):
        raise ValueError('source proposal adapter pins changed')
    return source, scenarios


def collect_references(value):
    found = {}
    def walk(item):
        if isinstance(item, dict):
            if item.get('format') == REF:
                validate_ref(item)
                key = item['sha256']
                if key in found and found[key] != item:
                    raise ValueError('conflicting source reference metadata')
                found[key] = item
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return [found[key] for key in sorted(found)]


def declared_dependencies(value):
    files = {}
    def walk(item):
        if isinstance(item, dict):
            if item.get('format') == PROPOSAL:
                pin = item['adapterPin']
                identity = {key: val for key, val in pin.items() if key != 'pin'}
                if (set(pin) != {'syntax', 'adapter', 'validator', 'registry_sha256', 'files', 'pin'}
                        or pin['syntax'] != item['syntax']
                        or pin['pin'] != hashlib.sha256(canonical(identity)).hexdigest()):
                    raise ValueError('invalid source adapter pin')
                for name, sha in {**pin['files'], 'syntaxes/registry.json': pin['registry_sha256']}.items():
                    if not isinstance(name, str) or not isinstance(sha, str) or not SHA.fullmatch(sha):
                        raise ValueError('invalid source adapter dependency')
                    if name in files and files[name] != sha:
                        raise ValueError('conflicting source adapter dependency')
                    files[name] = sha
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return files


def preserve_dependencies(artifact_store, proposal):
    root = Path(artifact_store).expanduser().resolve()
    for name, sha in declared_dependencies(proposal).items():
        original = (ROOT / name).resolve()
        destination = root / 'pins/blobs' / sha
        if not original.is_relative_to(ROOT) or not destination.resolve().is_relative_to(root) or destination.is_symlink():
            raise ValueError('source dependency escapes custody')
        raw = original.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('source adapter dependency changed during preservation')
        _publish(destination, raw)


def prepare_proposal(artifact_store, syntax, source, scenarios):
    pin = adapter_pin(syntax)
    reference(source, kind='source')
    reference(scenarios, kind='scenarios')
    proposal = {'format': PROPOSAL, 'syntax': syntax,
                'sourceRef': store_bytes(artifact_store, source, kind='source'),
                'scenariosRef': store_bytes(artifact_store, scenarios, kind='scenarios'),
                'adapterPin': pin}
    preserve_dependencies(artifact_store, proposal)
    return proposal
