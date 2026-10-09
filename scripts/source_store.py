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
MODULE_PROPOSAL = 'delvetalk-module-proposal-v1'
INLINE_MODULE_PROPOSAL = 'delvetalk-inline-module-proposal-v1'
MODULE_MANIFEST = 'delvetalk-module-manifest-v1'
MODULE_MATERIAL = 'delvetalk-module-material-v1'
MAX_MODULE_BYTES = 1024 * 1024
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
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError('source custody requires a regular file')
        stream = os.fdopen(descriptor, 'rb')
    except BaseException:
        os.close(descriptor)
        raise
    with stream:
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
    files = translate.closure_files(registry, adapter, validator, root=ROOT)
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
            if item.get('format') in (PROPOSAL, MODULE_PROPOSAL):
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


def seal_modules(entries):
    """Seal explicit ordered names/refs; no paths, imports or authority are resolved."""
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise ValueError('module manifest requires 1..64 ordered entries')
    names, total = set(), 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'name', 'sourceRef'}:
            raise ValueError('module entry requires name and sourceRef')
        name = entry['name']
        if not isinstance(name, str) or not 1 <= len(name) <= 128 or name in names:
            raise ValueError('module names must be bounded and distinct')
        names.add(name)
        validate_ref(entry['sourceRef'], kind='source')
        total += entry['sourceRef']['bytes']
    if total > MAX_MODULE_BYTES:
        raise ValueError('module manifest exceeds 1 MiB aggregate source')
    # Roundtrip through the lossless JSON framing gives callers no mutable aliases.
    value = loads(canonical({'format': MODULE_MANIFEST, 'modules': entries}))
    return {**value, 'sha256': hashlib.sha256(canonical(value)).hexdigest()}


def validate_manifest(manifest):
    if (not isinstance(manifest, dict) or set(manifest) != {'format', 'modules', 'sha256'}
            or manifest['format'] != MODULE_MANIFEST or seal_modules(manifest['modules']) != manifest):
        raise ValueError('invalid sealed module manifest or changed module order')
    return manifest


def validate_module_material(material):
    if (not isinstance(material, dict) or set(material) != {'format', 'manifest', 'modules'}
            or material['format'] != MODULE_MATERIAL):
        raise ValueError('invalid resolved module material')
    manifest = validate_manifest(material['manifest'])
    modules = material['modules']
    if not isinstance(modules, list) or len(modules) != len(manifest['modules']):
        raise ValueError('resolved modules differ from sealed manifest')
    for supplied, declared in zip(modules, manifest['modules']):
        if (not isinstance(supplied, dict) or set(supplied) != {'name', 'sourceRef', 'source'}
                or not isinstance(supplied['source'], str)
                or {key: supplied[key] for key in ('name', 'sourceRef')} != declared
                or reference(supplied['source'].encode('utf-8'), kind='source') != declared['sourceRef']):
            raise ValueError('resolved module source/name/order does not match exact reference')
    return material


def resolve_modules(artifact_store, manifest):
    validate_manifest(manifest)
    modules = [{**entry, 'source': read_bytes(artifact_store, entry['sourceRef'], kind='source').decode('utf-8')}
               for entry in manifest['modules']]
    return validate_module_material({'format': MODULE_MATERIAL, 'manifest': manifest, 'modules': modules})


def inline_module_material(modules, artifact_store=None):
    """Bind explicit retained module bytes; never author or resolve source."""
    if not isinstance(modules, list) or not 1 <= len(modules) <= 64:
        raise ValueError('inline module custody requires 1..64 modules')
    entries = []
    for module in modules:
        if (not isinstance(module, dict) or set(module) != {'name', 'source'}
                or not isinstance(module['name'], str) or not isinstance(module['source'], str)):
            raise ValueError('inline module custody requires exact name and source')
        raw = module['source'].encode('utf-8')
        ref = reference(raw) if artifact_store is None else store_bytes(artifact_store, raw)
        entries.append({'name': module['name'], 'sourceRef': ref})
    manifest = seal_modules(entries)
    return validate_module_material({'format': MODULE_MATERIAL, 'manifest': manifest,
                                     'modules': [{**entry, 'source': module['source']} for entry, module in zip(entries, modules)]})


def prepare_module_proposal(artifact_store, manifest, scenarios, *, syntax='objective-bend-object'):
    """Opt-in resident assembly; the final module supplies the host bindings."""
    resolve_modules(artifact_store, manifest)
    if syntax not in ('objective-bend-object',):
        raise ValueError('module proposal requires explicit source object syntax')
    proposal = {'format': MODULE_PROPOSAL, 'syntax': syntax,
                'manifest': loads(canonical(manifest)),
                'scenariosRef': store_bytes(artifact_store, scenarios, kind='scenarios'),
                'adapterPin': adapter_pin(syntax)}
    preserve_dependencies(artifact_store, proposal)
    return proposal


def validate_module_proposal(artifact_store, proposal, *, check_adapter=True):
    if (not isinstance(proposal, dict)
            or set(proposal) != {'format', 'syntax', 'manifest', 'scenariosRef', 'adapterPin'}
            or proposal['format'] != MODULE_PROPOSAL
            or proposal['syntax'] not in ('objective-bend-object',)):
        raise ValueError('invalid module reference proposal')
    declared_dependencies(proposal)
    material = resolve_modules(artifact_store, proposal['manifest'])
    scenarios = read_bytes(artifact_store, proposal['scenariosRef'], kind='scenarios')
    if check_adapter and canonical(proposal['adapterPin']) != canonical(adapter_pin(proposal['syntax'])):
        raise ValueError('module proposal adapter pins changed')
    return material, scenarios


def verify_bound_material(bindings, material):
    """Recheck compiler custody against queued refs, without evaluating source."""
    if not isinstance(material, dict) or not isinstance(material.get('scenarios'), str):
        raise ValueError('compiler build lacks retained exact source material')
    scenarios = reference(material['scenarios'].encode('utf-8'), kind='scenarios')
    if {key: scenarios[key] for key in bindings['scenariosRef']} != bindings['scenariosRef']:
        raise ValueError('compiler retained scenarios differ from queued source binding')
    if 'manifest' in bindings:
        source = {key: value for key, value in material.items() if key != 'scenarios'}
        validate_module_material(source)
        if source['manifest'] != bindings['manifest']:
            raise ValueError('compiler retained modules differ from queued manifest')
        return source
    if not isinstance(material.get('source'), str):
        raise ValueError('compiler build lacks retained exact source')
    ref = reference(material['source'].encode('utf-8'), kind='source')
    if {key: ref[key] for key in bindings['sourceRef']} != bindings['sourceRef']:
        raise ValueError('compiler retained source differs from queued source binding')
    return {'encoding': 'utf-8', 'text': material['source'], 'sha256': ref['sha256']}


def validate_translation_source(source):
    """Old lowering sources remain byte-exact; assemblies use an explicit tag."""
    if isinstance(source, dict) and source.get('format') == MODULE_MATERIAL:
        return validate_module_material(source)
    if (not isinstance(source, dict) or set(source) != {'encoding', 'text', 'sha256'}
            or source['encoding'] != 'utf-8' or not isinstance(source['text'], str)
            or hashlib.sha256(source['text'].encode('utf-8')).hexdigest() != source['sha256']):
        raise ValueError('lowering source digest mismatch')
    return source
