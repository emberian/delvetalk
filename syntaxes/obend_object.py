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
import source_packages

RUNNER = ROOT / '.lake/build/bin/delvetalk-obend'
LIMITS = {'ticks': '100000', 'heap': '100000', 'stack': '10000', 'typeFuel': '16384'}
MAX_FRAME = 8 * 1024 * 1024
CHILDREN_SOURCE = '''edition ObjectiveBend 1
record Child:
  key: String
  label: String
  object: String
  panel: String
sum Children:
  nil: {}
  cons: {head: Child, tail: Children}
def children() -> Children:
  Children.nil()
'''


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
    if reply.get('status') not in ('compiled', 'finished', 'compared'):
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


def _offers_type(offers):
    """Check the plain source ABI; capture helpers validate descriptor values."""
    if not isinstance(offers, dict) or len(offers) > 16:
        raise ValueError('view offers require a record of at most 16 entries')
    for offer in offers.values():
        _exact(offer, ('visible', 'title', 'label', 'command', 'reads', 'calls', 'fields',
                       'bindings', 'absentChildren', 'captures'), 'view offer')
        if offer['visible'] != 'boolean' or any(offer[key] != 'label' for key in ('title', 'label', 'command')):
            raise ValueError('view offer requires visible Bool and title/label/command String')
        for key, maximum in [('reads', 8), ('calls', 8), ('fields', 32),
                             ('bindings', 32), ('absentChildren', 8), ('captures', 32)]:
            if not isinstance(offer[key], dict) or len(offer[key]) > maximum:
                raise ValueError('view offer ' + key + ' requires a bounded record')
        if any(value != {'object': 'label', 'child': 'label'} for value in offer['reads'].values()):
            raise ValueError('view offer read references require object/child Strings')
        for call in offer['calls'].values():
            _exact(call, ('op', 'object', 'command', 'input', 'fromResult', 'inputFrom'), 'view offer call')
            if (any(call[key] != 'label' for key in ('op', 'object', 'command'))
                    or call['fromResult'] != 'boolean' or call['inputFrom'] != 'natural'
                    or not isinstance(call['input'], dict)):
                raise ValueError('view offer call requires text selectors, record input and Bool/Nat result selector')
        shapes = {
            'bindings': {'field': 'label', 'call': 'natural', 'input': 'label'},
            'absentChildren': {'factory': 'label', 'field': 'label'},
            'captures': {'read': 'label', 'call': 'natural', 'input': 'label', 'rootField': 'label'},
        }
        for key, shape in shapes.items():
            if any(value != shape for value in offer[key].values()):
                raise ValueError('view offer ' + key + ' has an invalid descriptor type')
        if any(not isinstance(field, dict) or field.get('type') != 'label' for field in offer['fields'].values()):
            raise ValueError('view offer fields require scalar field descriptor records')


def _signature(value, count):
    parameters = []
    for _ in range(count):
        if (value.get('tag'), value.get('reuse'), value.get('parameter')) != ('arrow', 'reusable', 'unrestricted'):
            raise ValueError('Bend object export requires ' + str(count) + ' unrestricted arguments')
        parameters.append(_type(value['domain']))
        value = value['codomain']
    return parameters, _type(value)


def _row_members(value):
    fields = {}
    while isinstance(value, dict) and value.get('tag') == 'field':
        if value['name'] in fields:
            raise ValueError('Bend object ABI requires unique row fields')
        fields[value['name']] = value['member']
        value = value['tail']
    if not isinstance(value, dict) or value.get('tag') != 'emptyRow':
        raise ValueError('Bend object ABI requires a closed record root')
    return fields


def _raw_signature(value, count):
    parameters = []
    for _ in range(count):
        if (value.get('tag'), value.get('reuse'), value.get('parameter')) != ('arrow', 'reusable', 'unrestricted'):
            raise ValueError('Bend object export requires unrestricted reusable arguments')
        parameters.append(value['domain'])
        value = value['codomain']
    return parameters, value


def _wire_record(value, keys):
    if not isinstance(value, dict) or set(value) != {'tag', 'fields'} or value['tag'] != 'record':
        raise ValueError('typed description requires a record')
    fields = {}
    for item in value['fields']:
        _exact(item, ('name', 'value'), 'typed description field')
        if not isinstance(item['name'], str) or item['name'] in fields:
            raise ValueError('typed description requires distinct named fields')
        fields[item['name']] = item['value']
    _exact(fields, keys, 'typed description')
    return fields


def _exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(label + ' requires exactly ' + ', '.join(keys))


def lower(source):
    if not isinstance(source, str) or not source.strip() or len(source.encode('utf-8')) > 512 * 1024:
        raise ValueError('Bend object requires nonempty source of at most 512 KiB')
    return lower_modules([{'name': 'Main', 'source': source}])


def lower_data(source):
    if not isinstance(source, str) or not source.strip() or len(source.encode('utf-8')) > 512 * 1024:
        raise ValueError('Bend object requires nonempty source of at most 512 KiB')
    return lower_data_modules([{'name': 'Main', 'source': source}])


def lower_modules(modules):
    return _lower_modules(modules, typed=False)


def lower_data_modules(modules):
    return _lower_modules(modules, typed=True)


def _lower_modules(modules, *, typed):
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
    def compare(left, left_path, right, right_path, label):
        reply = _native({'op': 'compare-data-types-v1',
            'left': {'artifact': left, 'path': left_path},
            'right': {'artifact': right, 'path': right_path}, 'work': '100000'}, deadline)
        if reply.get('equal') is not True:
            raise ValueError(label + ': incompatible serializable state schema')

    described = _native({'op': 'run-data-v1' if typed else 'run',
                         'artifact': artifact, 'arguments': [], 'limits': LIMITS}, deadline)['value']
    if typed:
        values = _wire_record(described, ('name', 'initial', 'methods', 'panels'))
        initial = deepcopy(values['initial'])
        if initial.get('tag') != 'record':
            raise ValueError('describe.initial must have a closed record root')
        # The selected native route checked every alternative, even unused ones.
        description = {name: _data(value) for name, value in values.items() if name != 'initial'}
        description['initial'] = {'model': initial}
        declared = None
    else:
        declared = _type(artifact['type'])
        description = _data(described)
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
    state_type = None if typed else declared['initial']
    context1 = {'object': 'label', 'principal': 'label'}
    context2 = {**context1, 'inputOrigin': {'kind': 'label', 'object': 'label',
                                         'command': 'label', 'immediatelyPrevious': 'boolean'}}
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
        method = compile_entry(name)
        raw_parameters, raw_decision = _raw_signature(method['type'], 3)
        receiving = raw_decision.get('tag') == 'arrow'
        argument_count = 4 if receiving else 3
        if receiving:
            raw_parameters, raw_decision = _raw_signature(method['type'], 4)
            event_type = {'id': 'label', 'source': 'label', 'sourceProgram': 'label',
                          'originatingPrincipal': 'label'}
            if _type(raw_parameters[3]) != event_type:
                raise ValueError(name + ': receive requires exact authenticated EventFacts argument')
        decision_fields = _row_members(raw_decision)
        effects = 'emissions' in decision_fields
        if receiving and effects:
            raise ValueError(name + ': receive cannot emit new messages in this profile')
        _exact(decision_fields, ('accepted', 'reason', 'state', 'result', 'emissions') if effects
               else ('accepted', 'reason', 'state', 'result'), name + ' decision')
        if effects:
            slots = _type(decision_fields['emissions'])
            _exact(slots, ('a', 'b', 'c', 'd'), name + ' emissions')
            for slot in slots.values():
                _exact(slot, ('enabled', 'to', 'command', 'recipientProgram', 'payload'), name + ' emission')
                if (slot['enabled'] != 'boolean' or any(slot[key] != 'label'
                        for key in ('to', 'command', 'recipientProgram')) or not isinstance(slot['payload'], dict)):
                    raise ValueError(name + ': emissions require Bool, String addresses and plain record payload')
        transition_profile = 'delvetalk-source-transition-v1'
        if typed:
            compare(artifact, [{'field': 'initial'}], method, ['domain'], name + ' state input')
            compare(artifact, [{'field': 'initial'}], method,
                    ['codomain'] * argument_count + [{'field': 'state'}], name + ' state output')
            if [_type(raw_parameters[1]), _type(raw_parameters[2])] != [expected_input, context2]:
                raise ValueError(name + ': input/context signature differs from describe()')
            decision = {key: _type(value) for key, value in decision_fields.items() if key not in ('state', 'emissions')}
            if decision['accepted'] != 'boolean' or decision['reason'] != 'label':
                raise ValueError(name + ': decision requires accepted Bool and reason String')
            transition_profile = ('delvetalk-source-data-receive-v1' if receiving else
                                  'delvetalk-source-data-effects-v1' if effects else 'delvetalk-source-data-transition-v1')
        else:
            parameters, decision = _signature(method['type'], argument_count)
            if parameters[:2] != [state_type, expected_input] or parameters[2] not in (context1, context2):
                raise ValueError(name + ': state/input/context signature differs from describe()')
            if (not isinstance(decision, dict)
                    or decision['accepted'] != 'boolean' or decision['reason'] != 'label' or decision['state'] != state_type):
                raise ValueError(name + ': decision must preserve the declared state type')
            if parameters[2] == context2:
                transition_profile = 'delvetalk-source-transition-v2'
            if effects or receiving:
                if parameters[2] != context2:
                    raise ValueError(name + ': effects and receive require Context2')
                transition_profile = 'delvetalk-source-receive-v1' if receiving else 'delvetalk-source-effects-v1'
        forms[name] = form
        commands[name] = {'transition': {'profile': transition_profile,
            'package': source_packages.selector(name)}}
    view_artifact = compile_entry('view')
    if typed:
        raw_parameters, raw_view = _raw_signature(view_artifact['type'], 2)
        compare(artifact, [{'field': 'initial'}], view_artifact, ['domain'], 'view state input')
        if _type(raw_parameters[1]) != 'label':
            raise ValueError('view requires panel String')
        members = _row_members(raw_view)
        if set(members) not in ({'title', 'prose', 'actions', 'children'},
                                {'title', 'prose', 'actions', 'children', 'offers'}):
            raise ValueError('typed view requires title/prose/actions/children and optional offers')
        if 'offers' in members:
            _offers_type(_type(members['offers']))
        child_contract = _native({'op': 'compile', 'modules': [{'name': 'ChildrenContract', 'source': CHILDREN_SOURCE}],
                                 'entry': 'children', 'limits': LIMITS}, deadline)['artifact']
        compare(view_artifact, ['codomain', 'codomain', {'field': 'children'}], child_contract, [], 'view children')
        view = {key: _type(value) for key, value in members.items() if key not in ('children', 'offers', 'actions')}
        try:
            view['actions'] = _type(members['actions'])
        except ValueError:
            # Native schema traversal checks every alternative for serializability.
            # Structural list/descriptor framing is checked on the actual output;
            # Python does not resolve recursive source aliases or interpret them.
            actions_path = ['codomain', 'codomain', {'field': 'actions'}]
            compare(view_artifact, actions_path, view_artifact, actions_path, 'view actions')
            view['actions'] = {}
        parameters = [state_type, 'label']
    else:
        parameters, view = _signature(view_artifact['type'], 2)
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
            'sourcePackages': {source_packages.NAME: source_packages.table(modules)},
            'initial': description['initial'], 'commands': commands, 'affordances': forms,
            'viewPanels': [{'id': name, 'label': label} for name, label in sorted(panels.items())],
            'viewProgram': {'profile': ('delvetalk-obend-data-offers-v1' if 'offers' in members else
                                        'delvetalk-obend-data-menu-v1') if typed else 'delvetalk-obend-menu-v1',
                            'package': source_packages.selector('view')}}
