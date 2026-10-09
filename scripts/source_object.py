"""Physical loading and native compilation of an explicit sealed source object.

Configuration is typed data evaluated by a supplied source constructor. This
module authors no methods, guards, views, laws or workflow plans.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import time
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
with Path(__file__).open('rb') as _stream:
    _LOADED_SELF = hashlib.file_digest(_stream, 'sha256').hexdigest()
_spec = importlib.util.spec_from_file_location('source_object_adapter', ROOT / 'syntaxes/obend_object.py')
adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(adapter)
sys.path.insert(0, str(ROOT / 'scripts'))
import source_store
import runtime_profile
import process_custody
_LOADED_PYTHON = {name: sha for name, sha in source_store.adapter_pin('objective-bend-object')['files'].items()
                  if name.endswith('.py')}


def pins(syntax):
    with Path(__file__).open('rb') as stream:
        loader = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'adapter': source_store.adapter_pin(syntax), 'loader': loader}


def data(value):
    """Encode plain physical input as DataWire, without selecting a source type."""
    if type(value) is bool:
        return {'tag': 'boolean', 'value': value}
    if type(value) is int and value >= 0:
        return {'tag': 'natural', 'value': str(value)}
    if isinstance(value, str):
        return {'tag': 'label', 'value': value}
    if isinstance(value, dict):
        return record({key: data(item) for key, item in value.items()})
    raise ValueError('plain input requires Nat, Bool, String or a record')


def record(fields):
    """Frame named DataWire values; the native constructor checks their types."""
    return {'tag': 'record', 'fields': [{'name': key, 'value': value} for key, value in fields.items()]}


def variant(label, payload):
    return {'tag': 'variant', 'label': label, 'payload': payload}


def list_data(items):
    """Frame a source List of already encoded elements; native checks its type."""
    result = variant('nil', record({}))
    for item in reversed(list(items)):
        result = variant('cons', record({'head': item, 'tail': result}))
    return result


def state_data(root, *, binary=None):
    """Materialize caller-held typed custody through the shared native resolver.

    Acquisition/current-read authorization stays with the caller; this physical
    helper never guesses a schema from model fields or rewrites the root.
    """
    captured = runtime_profile.hash_paths(runtime_profile.paths('compiled'), root=ROOT)
    empty = {'objects': {}, 'receipts': []}
    wire = source_store.canonical({'world': empty,
        'request': {'op': 'source-state', 'root': root}}) + b'\n'
    if len(wire) > 1024 * 1024:
        raise ValueError('native state query frame exceeds 1 MiB')
    done = process_custody.run_native(
        [str(binary or ROOT / '.lake/build/bin/delvetalk-compiled')], input=wire,
        cwd=ROOT, timeout=30, cpu_seconds=25, stdout_limit=8 * 1024 * 1024,
        stderr_limit=1024 * 1024, file_limit=8 * 1024 * 1024)
    if done.returncode:
        raise ValueError('native state query process failed')
    reply = source_store.loads(done.stdout)
    if (not isinstance(reply, dict) or set(reply) != {'world', 'reply'}
            or reply['world'] != empty or not isinstance(reply['reply'], dict)
            or reply['reply'].get('status') != 'decoded'
            or set(reply['reply']) != {'status', 'value', 'conversionNodes'}):
        raise ValueError('native state query returned invalid framing: ' + str(reply))
    if captured != runtime_profile.hash_paths(runtime_profile.paths('compiled'), root=ROOT):
        raise ValueError('Bend runtime changed during native state query')
    return reply['reply']['value']


def values(operation, items):
    """Use the native shared Value codec; retain exact JSON number framing."""
    if operation not in ('encode', 'decode', 'digest') or not isinstance(items, list):
        raise ValueError('native value codec requires an operation and values array')
    captured = runtime_profile.hash_paths(runtime_profile.paths('compiled'), root=ROOT)
    empty = {'objects': {}, 'receipts': []}
    wire = source_store.canonical({'world': empty, 'request': {
        'op': 'value-codec', 'direction': operation, 'values': items}}) + b'\n'
    if len(wire) > 1024 * 1024:
        raise ValueError('native value codec frame exceeds 1 MiB')
    done = process_custody.run_native([str(ROOT / '.lake/build/bin/delvetalk-compiled')],
        input=wire, cwd=ROOT, timeout=15, cpu_seconds=10,
        stdout_limit=8 * 1024 * 1024, stderr_limit=1024 * 1024,
        file_limit=8 * 1024 * 1024)
    if done.returncode:
        raise ValueError('native value codec process failed')
    reply = source_store.loads(done.stdout)
    if (not isinstance(reply, dict) or set(reply) != {'world', 'reply'}
            or reply['world'] != empty or not isinstance(reply['reply'], dict)
            or set(reply['reply']) != {'status', 'values'}
            or reply['reply']['status'] != {'encode': 'encoded', 'decode': 'decoded', 'digest': 'digested'}[operation]
            or len(reply['reply']['values']) != len(items)):
        raise ValueError('native value codec returned invalid framing: ' + str(reply))
    if captured != runtime_profile.hash_paths(runtime_profile.paths('compiled'), root=ROOT):
        raise ValueError('native value codec runtime changed during conversion')
    return reply['reply']['values']


def value(item):
    """Encode an ordinary JSON value as the shared source Preparation.Value."""
    return values('encode', [item])[0]


def plain(value):
    """Read DataWire for physical display; variant identity remains explicit."""
    if value['tag'] == 'record':
        return {field['name']: plain(field['value']) for field in value['fields']}
    if value['tag'] == 'variant':
        return {'variant': value['label'], 'payload': plain(value['payload'])}
    if value['tag'] == 'natural':
        return int(value['value'])
    if value['tag'] in ('label', 'boolean'):
        return value['value']
    raise ValueError('unknown physical DataWire tag')


def read_modules(files):
    """Read only explicit (name,path) pairs; never resolve source imports here."""
    return [{'name': name, 'source': Path(path).read_bytes().decode('utf-8')} for name, path in files]


def read_closure(files, *, roots=None):
    """Assemble named roots against explicit supplied sources and shared library.

    The shared library is a physical allowlist, not a compiler prelude. Native
    parsed imports select the exact retained dependency closure. Callers can use
    source_closure.read directly to choose a different confined allowlist.
    """
    import source_closure
    files = list(files)
    if not files:
        raise ValueError('source closure requires an explicit entry source')
    allowed = dict(source_closure.LIBRARY)
    for name, path in files:
        if name in allowed and (ROOT / allowed[name]).resolve() != (ROOT / path if not Path(path).is_absolute() else Path(path)).resolve():
            raise ValueError('source overrides shared allowlist identity: ' + name)
        if sum(key == name for key, _ in files) != 1:
            raise ValueError('duplicate explicit source identity: ' + name)
        allowed[name] = path
    return source_closure.read([files[-1][0]] if roots is None else roots, list(allowed.items()), root=ROOT)


def evaluate(modules, entry, arguments):
    """Execute a captured pure source export; native code checks argument types."""
    captured = pins('objective-bend-object')
    modules = deepcopy(adapter.source_packages.table(modules)['modules'])
    if not isinstance(entry, str) or not entry or not isinstance(arguments, list):
        raise ValueError('pure source export requires an entry and DataWire arguments')
    deadline = time.monotonic() + 30
    artifact = adapter._native({'op': 'compile', 'modules': modules, 'entry': entry,
                                'limits': adapter.LIMITS}, deadline)['artifact']
    result = adapter._native({'op': 'run-data-v1', 'artifact': artifact,
                              'arguments': deepcopy(arguments), 'limits': adapter.LIMITS}, deadline)['value']
    if captured != pins('objective-bend-object'):
        raise ValueError('source export runtime changed during execution')
    return result


def _compact_state(model, artifact, path, deadline):
    selector = adapter.source_packages.selector(artifact['entry'])
    encoded = adapter._native({'op': 'encode-compact',
        'selection': {'artifact': artifact, 'path': deepcopy(path)},
        'value': deepcopy(model), 'bytes': adapter.MAX_FRAME}, deadline)
    return {'format': 'delvetalk-compact-state', 'value': encoded['value'],
            'schema': {'package': selector, 'path': deepcopy(path),
                       'packetSha256': encoded['schemaPacketSha256'],
                       'sourcesSha256': artifact['sourcesSha256']}}


def compact_state(protocol, model, *, entry, path):
    """Frame state using the native codec and an exact retained source schema."""
    captured = pins('objective-bend-object')
    packages = adapter.source_packages.validate_tables(protocol)
    selector = adapter.source_packages.selector(entry)
    modules = packages[selector['name']]['modules']
    deadline = time.monotonic() + 30
    artifact = adapter._native({'op': 'compile', 'modules': modules, 'entry': entry,
                                'limits': adapter.LIMITS}, deadline)['artifact']
    result = _compact_state(model, artifact, path, deadline)
    if captured != pins('objective-bend-object'):
        raise ValueError('source state runtime changed during encoding')
    return result


def load(modules, *, syntax, constructor=None, arguments=None):
    if syntax != 'objective-bend-object':
        raise ValueError('configured source object requires explicit typed source syntax')
    captured = pins(syntax)
    if (captured['loader'] != _LOADED_SELF or
            {name: sha for name, sha in captured['adapter']['files'].items() if name.endswith('.py')}
            != _LOADED_PYTHON):
        raise ValueError('source object Python custody code changed; use a fresh process')
    modules = deepcopy(adapter.source_packages.table(modules)['modules'])
    arguments = deepcopy(arguments)
    protocol = adapter._lower_modules(modules, _capture=captured['adapter']['files'])
    if constructor is None:
        if arguments is not None:
            raise ValueError('configuration arguments require a named source constructor')
        if captured != pins(syntax):
            raise ValueError('source object runtime changed during loading')
        return protocol
    if not isinstance(constructor, str) or not constructor or not isinstance(arguments, list):
        raise ValueError('source configuration requires an entry and typed argument array')
    deadline = time.monotonic() + 30
    compiled = adapter._native({'op': 'compile', 'modules': modules, 'entry': constructor,
                                'limits': adapter.LIMITS}, deadline)['artifact']
    description = adapter._native({'op': 'compile', 'modules': modules, 'entry': 'describe',
                                  'limits': adapter.LIMITS}, deadline)['artifact']
    comparison = adapter._native({'op': 'compare-data-types-v1',
        'left': {'artifact': compiled, 'path': ['codomain'] * len(arguments)},
        'right': {'artifact': description, 'path': [{'field': 'initial'}]}, 'work': '100000'}, deadline)
    if comparison.get('equal') is not True:
        raise ValueError('source constructor differs from the checked object state schema')
    value = adapter._native({'op': 'run-data-v1', 'artifact': compiled,
                             'arguments': arguments, 'limits': adapter.LIMITS}, deadline)['value']
    if value.get('tag') != 'record':
        raise ValueError('source constructor must produce a record state')
    protocol['initial'] = {'model': _compact_state(value, compiled,
        ['codomain'] * len(arguments), deadline)}
    # The exact evaluated initial value is operative configuration. Original
    # constructor inputs belong to caller custody, not a second executable copy.
    protocol['sourceConfiguration'] = {'entry': constructor}
    if captured != pins(syntax):
        raise ValueError('source object runtime changed during configuration')
    return protocol


def seed_material(protocol):
    """Retain exact source and recode the supplied state with its source schema.

    This records a caller-held initial state, not proof that an arbitrary caller
    supplied it by executing the declared constructor.
    """
    packages = adapter.source_packages.validate_tables(protocol)
    if set(packages) != {'resident'}:
        raise ValueError('one current source object seed requires its resident package')
    model = state_data({'protocol': protocol, 'state': protocol['initial']})
    initial = {'model': compact_state(protocol, model, entry='describe', path=[{'field': 'initial'}])}
    material = {'modules': deepcopy(packages['resident']['modules']), 'initial': initial}
    if 'sourceConfiguration' in protocol:
        material['sourceConfiguration'] = deepcopy(protocol['sourceConfiguration'])
    return material
