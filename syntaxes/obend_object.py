"""Bind one ordinary Bend module's description, methods and contextual view.

Lean parses, checks and evaluates. This adapter only decodes first-order data,
checks the declared host ABI, and frames source-only host descriptors.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import affordances
import runtime_profile
import process_custody

RUNNER = ROOT / '.lake/build/bin/delvetalk-obend'
LIMITS = {'ticks': '100000', 'heap': '100000', 'stack': '10000', 'typeFuel': '16384'}
MAX_FRAME = 8 * 1024 * 1024


def _native(request, deadline):
    wire = json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'
    if len(wire) > MAX_FRAME:
        raise ValueError('Bend object package exceeds 8 MiB')
    remaining = min(10, deadline - time.monotonic())
    if remaining <= 0:
        raise ValueError('Bend object description/type checking exceeded 30 seconds')
    try:
        done = process_custody.run([str(RUNNER)], input=wire, timeout=remaining,
            cpu_seconds=10, stdout_limit=MAX_FRAME, stderr_limit=MAX_FRAME, file_limit=MAX_FRAME, cwd=ROOT)
    except subprocess.TimeoutExpired as error:
        raise ValueError('Bend object package timed out') from error
    except process_custody.OutputLimitExceeded as error:
        raise ValueError('Bend object package exceeded its output limit') from error
    raw = done.stdout
    if done.returncode:
        raise ValueError('Bend object package failed or exceeded its output limit')
    try:
        reply = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ValueError('Bend object package returned invalid framing') from error
    if reply.get('status') not in ('compiled', 'finished'):
        raise ValueError('Bend object: ' + str(reply.get('message', reply.get('failure', 'package refused'))))
    return reply


def _data(value, depth=64):
    """Decode the native Data wire; no terms, closures or effects cross here."""
    if depth == 0 or not isinstance(value, dict):
        raise ValueError('Bend description exceeds data depth')
    tag = value.get('tag')
    if tag == 'natural':
        number = value.get('value')
        if not isinstance(number, str) or len(number) > 4096 or not re.fullmatch(r'0|[1-9][0-9]*', number):
            raise ValueError('invalid Bend natural data')
        return int(number)
    if tag == 'boolean' and type(value.get('value')) is bool:
        return value['value']
    if tag == 'label' and isinstance(value.get('value'), str):
        return value['value']
    if tag == 'record' and isinstance(value.get('fields'), list):
        result = {}
        for field in value['fields']:
            name = field.get('name')
            if not isinstance(name, str) or name in result:
                raise ValueError('invalid or duplicate Bend data field')
            result[name] = _data(field['value'], depth - 1)
        return result
    raise ValueError('description must contain only Nat, Bool, String and records')


def _type(value, depth=64):
    """Read compiler-produced first-order ABI shapes, independent of row order."""
    if depth == 0 or not isinstance(value, dict):
        raise ValueError('Bend object ABI exceeds type depth')
    tag = value.get('tag')
    if tag in ('natural', 'boolean', 'label'):
        return tag
    fields = {}
    while value.get('tag') == 'field':
        name = value['name']
        if name in fields:
            raise ValueError('Bend object ABI requires unique row fields')
        fields[name] = _type(value['member'], depth - 1)
        value = value['tail']
    if value.get('tag') != 'emptyRow':
        raise ValueError('Bend object ABI requires closed first-order data')
    return fields


def _signature(value, count):
    parameters = []
    for _ in range(count):
        if (value.get('tag'), value.get('reuse'), value.get('parameter')) != ('arrow', 'reusable', 'unrestricted'):
            raise ValueError('Bend object export requires ' + str(count) + ' unrestricted arguments')
        parameters.append(_type(value['domain']))
        value = value['codomain']
    return parameters, _type(value)


def _exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(label + ' requires exactly ' + ', '.join(keys))


def lower(source):
    if not isinstance(source, str) or not source.strip() or len(source.encode('utf-8')) > 512 * 1024:
        raise ValueError('Bend object requires nonempty source of at most 512 KiB')
    return lower_modules([{'name': 'Main', 'source': source}])


def lower_modules(modules):
    """Compile one ordered, explicitly supplied package; native code owns imports."""
    if not isinstance(modules, list) or not 1 <= len(modules) <= 64:
        raise ValueError('Bend object requires 1..64 supplied modules')
    total = 0
    for entry in modules:
        _exact(entry, ('name', 'source'), 'Bend module')
        if not isinstance(entry['name'], str) or not 1 <= len(entry['name']) <= 128:
            raise ValueError('Bend module requires a bounded name')
        source = entry['source']
        if not isinstance(source, str) or not source.strip() or len(source.encode('utf-8')) > 512 * 1024:
            raise ValueError('Bend module requires nonempty source of at most 512 KiB')
        total += len(source.encode('utf-8'))
    if total > 1024 * 1024:
        raise ValueError('Bend modules exceed 1 MiB aggregate source')
    modules = deepcopy(modules)
    pins = runtime_profile.file_hashes('compiled')
    native = hashlib.sha256(RUNNER.read_bytes()).hexdigest()
    deadline = time.monotonic() + 30

    def compile_entry(name):
        return _native({'op': 'compile', 'modules': modules, 'entry': name, 'limits': LIMITS}, deadline)['artifact']

    artifact = compile_entry('describe')
    declared = _type(artifact['type'])
    description = _data(_native({'op': 'run', 'artifact': artifact, 'arguments': [], 'limits': LIMITS}, deadline)['value'])
    _exact(description, ('name', 'initial', 'methods', 'panels'), 'describe()')
    affordances._string(description['name'], 'object name', 256, nonempty=True)
    if not isinstance(description['initial'], dict):
        raise ValueError('describe.initial must be a record')
    methods, panels = description['methods'], description['panels']
    if not isinstance(methods, dict) or not 1 <= len(methods) <= 32:
        raise ValueError('describe.methods requires 1..32 methods')
    if not isinstance(panels, dict) or len(panels) > 8:
        raise ValueError('describe.panels requires at most eight named labels')
    forms, commands = {}, {}
    state_type = declared['initial']
    context_type = {'object': 'label', 'principal': 'label'}
    for name, form in methods.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) or name in ('describe', 'view'):
            raise ValueError('method must name a distinct Bend definition: ' + name)
        _exact(form, ('label', 'fields'), 'method ' + name)
        form = deepcopy(form)
        if not isinstance(form['fields'], dict):
            raise ValueError('method fields must be a record')
        for field in form['fields'].values():
            if isinstance(field, dict) and field.get('type') == 'enum':
                options = field.get('options')
                if not isinstance(options, dict):
                    raise ValueError('Bend enum options must be a named record of strings')
                field['options'] = [options[key] for key in sorted(options)]
        # Reuse actual form validation; descriptions are not a second checker.
        fields = affordances._metadata({'commands': {name: {}}, 'affordances': {name: form}})[name]['fields']
        expected_input = {field['name']: {'string': 'label', 'enum': 'label', 'nat': 'natural', 'bool': 'boolean'}[field['type']]
                          for field in fields}
        parameters, decision = _signature(compile_entry(name)['type'], 3)
        if parameters != [state_type, expected_input, context_type]:
            raise ValueError(name + ': state/input/context signature differs from describe()')
        if (not isinstance(decision, dict) or set(decision) != {'accepted', 'reason', 'state', 'result'}
                or decision['accepted'] != 'boolean' or decision['reason'] != 'label' or decision['state'] != state_type):
            raise ValueError(name + ': decision must preserve the declared state type')
        forms[name] = form
        commands[name] = {'transition': {'profile': 'delvetalk-source-transition-v1',
            'package': {'modules': deepcopy(modules), 'entry': name}}}
    parameters, view = _signature(compile_entry('view')['type'], 2)
    if parameters != [state_type, 'label'] or not isinstance(view, dict) or set(view) != {'title', 'prose', 'actions'}:
        raise ValueError('view must receive the declared state and panel String and return title/prose/actions')
    if view['title'] != 'label' or view['prose'] != 'label' or not isinstance(view['actions'], dict) or len(view['actions']) > 64:
        raise ValueError('view requires text title/prose and at most 64 actions')
    for action in view['actions'].values():
        if (not isinstance(action, dict) or set(action) != {'visible', 'text', 'command', 'input'}
                or action['visible'] != 'boolean' or action['text'] != 'label' or action['command'] != 'label'
                or not isinstance(action['input'], dict)):
            raise ValueError('view action requires visible Bool, text/command String and record input')
    for name, label in panels.items():
        affordances._string(name, 'panel id', 128, nonempty=True)
        affordances._string(label, 'panel label', 128, nonempty=True)
    if runtime_profile.file_hashes('compiled') != pins or hashlib.sha256(RUNNER.read_bytes()).hexdigest() != native:
        raise ValueError('Bend object runtime changed during translation')
    return {'profile': 'delvetalk-local-v1', 'runtimeProfile': 'compiled', 'name': description['name'],
            'initial': description['initial'], 'commands': commands, 'affordances': forms,
            'viewPanels': [{'id': name, 'label': label} for name, label in sorted(panels.items())],
            'viewProgram': {'profile': 'delvetalk-obend-menu-v1',
                            'package': {'modules': deepcopy(modules), 'entry': 'view'}}}
