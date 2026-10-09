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


def load(modules, *, syntax, constructor=None, arguments=None):
    if syntax not in ('objective-bend-object', 'objective-bend-spell@3'):
        raise ValueError('configured source object requires explicit typed source syntax')
    captured = pins(syntax)
    if (captured['loader'] != _LOADED_SELF or
            {name: sha for name, sha in captured['adapter']['files'].items() if name.endswith('.py')}
            != _LOADED_PYTHON):
        raise ValueError('source object Python custody code changed; use a fresh process')
    modules = deepcopy(adapter.source_packages.table(modules)['modules'])
    arguments = deepcopy(arguments)
    protocol = adapter.lower_data_modules(modules)
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
    protocol['initial'] = {'model': value}
    # The exact evaluated initial value is operative configuration. Original
    # constructor inputs belong to caller custody, not a second executable copy.
    protocol['sourceConfiguration'] = {'entry': constructor}
    if captured != pins(syntax):
        raise ValueError('source object runtime changed during configuration')
    return protocol
