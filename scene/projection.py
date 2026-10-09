#!/usr/bin/env python3
"""Pure Bend views through Lean; rendering and request framing grant no authority."""
from __future__ import annotations
import copy
import hashlib
import html
import importlib.util
from pathlib import Path
import re
import subprocess
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
DATA_MENU_PROFILE = 'delvetalk-obend-data-menu-v1'
DATA_PROFILES = (DATA_MENU_PROFILE,)
SOURCE_PROFILES = DATA_PROFILES
FORMAT = 'delvetalk-projection-view-v1'
_spec = importlib.util.spec_from_file_location('projection_world', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(world)
_spec = importlib.util.spec_from_file_location('projection_runtime', ROOT / 'scripts/runtime_profile.py')
runtime_profile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime_profile)
_spec = importlib.util.spec_from_file_location('projection_source_packages', ROOT / 'scripts/source_packages.py')
source_packages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(source_packages)


class ProjectionError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(world.wire_dumps(value).encode('utf-8')).hexdigest()


def _canonical(value):
    def ordered(item):
        if isinstance(item, dict):
            return {key: ordered(item[key]) for key in sorted(item)}
        if isinstance(item, list):
            return [ordered(child) for child in item]
        return item
    return world.wire_dumps(ordered(value))


def _validate(data, root):
    if not isinstance(data, dict) or set(data) != {'title', 'prose', 'actions'}:
        raise ProjectionError('ViewData requires exactly title, prose and actions')
    if not isinstance(data['title'], str) or not isinstance(data['prose'], str):
        raise ProjectionError('ViewData title and prose must be strings')
    if not isinstance(data['actions'], dict) or len(data['actions']) > 64:
        raise ProjectionError('ViewData actions must be a record of at most 64 entries')
    for key, action in data['actions'].items():
        if not isinstance(key, str) or not key or not isinstance(action, dict) or set(action) != {'text', 'command', 'input'}:
            raise ProjectionError('invalid action descriptor')
        if not isinstance(action['text'], str) or not isinstance(action['command'], str) or not isinstance(action['input'], dict):
            raise ProjectionError('invalid action descriptor fields')
        if action['command'] not in root['protocol']['commands']:
            raise ProjectionError('action names an absent command')
    return data


def _visible_actions(raw, root):
    """Check the complete eager source result, then expose its offered actions.

    Visibility is presentation over state/panel, never caller authentication or
    an invocation guard. Hidden descriptors have the same structural contract.
    """
    if not isinstance(raw, dict) or set(raw) != {'title', 'prose', 'actions'}:
        raise ProjectionError('MenuData requires exactly title, prose and actions')
    if not isinstance(raw['actions'], dict) or len(raw['actions']) > 64:
        raise ProjectionError('MenuData actions must be a record of at most 64 entries')
    actions = {}
    for key, descriptor in raw['actions'].items():
        if (not isinstance(descriptor, dict)
                or set(descriptor) != {'visible', 'text', 'command', 'input'}
                or type(descriptor['visible']) is not bool):
            raise ProjectionError('menu action requires visible Bool, text, command and input')
        actions[key] = {name: value for name, value in descriptor.items() if name != 'visible'}
    # Validate hidden entries too; filtering must not conceal a malformed menu.
    normalized = _validate({'title': raw['title'], 'prose': raw['prose'], 'actions': actions}, root)
    normalized['actions'] = {key: action for key, action in actions.items() if raw['actions'][key]['visible']}
    return normalized


def _wire_record(value):
    if (not isinstance(value, dict) or set(value) != {'tag', 'fields'}
            or value['tag'] != 'record' or not isinstance(value['fields'], list)):
        raise ProjectionError('typed view requires a DataWire record')
    fields = {}
    for field in value['fields']:
        if (not isinstance(field, dict) or set(field) != {'name', 'value'}
                or not isinstance(field['name'], str) or field['name'] in fields):
            raise ProjectionError('invalid or duplicate typed view field')
        fields[field['name']] = field['value']
    return fields


def _plain_data(value, budget, depth=64):
    """Decode framing at the explicit typed view boundary, never execute source."""
    budget[0] -= 1
    if budget[0] < 0 or depth == 0 or not isinstance(value, dict):
        raise ProjectionError('typed view data bound exceeded')
    tag = value.get('tag')
    if tag == 'record':
        return {name: _plain_data(child, budget, depth - 1) for name, child in _wire_record(value).items()}
    if set(value) != {'tag', 'value'}:
        raise ProjectionError('malformed plain typed view data')
    scalar = value['value']
    if tag == 'label' and isinstance(scalar, str):
        return scalar
    if tag == 'boolean' and type(scalar) is bool:
        return scalar
    if tag == 'natural' and isinstance(scalar, str) and len(scalar) <= 4096 and re.fullmatch(r'0|[1-9][0-9]*', scalar):
        return int(scalar)
    raise ProjectionError('menu metadata requires plain Nat, Bool, String and records')


def _text_bound(value, limit, name, *, identity=False):
    if not isinstance(value, str) or not value or len(value.encode('utf-8')) > limit:
        raise ProjectionError(f'{name} requires 1..{limit} UTF-8 bytes')
    if identity and (len(value) > 256 or any(unicodedata.category(c) in ('Cc', 'Cs') for c in value)):
        raise ProjectionError(f'{name} contains an invalid local identity')
    return value


def _validate_children(values):
    if not isinstance(values, list) or len(values) > 32:
        raise ProjectionError('view children require a list of at most 32 entries')
    seen = set()
    for descriptor in values:
        if not isinstance(descriptor, dict) or set(descriptor) != {'key', 'label', 'object', 'panel'}:
            raise ProjectionError('child requires exactly key, label, object and panel')
        for name, limit in [('key', 128), ('label', 256), ('object', 512), ('panel', 128)]:
            _text_bound(descriptor[name], limit, 'child ' + name, identity=name != 'label')
        if descriptor['key'] in seen:
            raise ProjectionError('duplicate child key')
        seen.add(descriptor['key'])
    return values


def _typed_list(sequence, maximum, name):
    """Decode the canonical source nil/cons data shape; never choose behavior."""
    entries = []
    while True:
        if (not isinstance(sequence, dict) or set(sequence) != {'tag', 'label', 'payload'}
                or sequence['tag'] != 'variant'):
            raise ProjectionError(name + ' require typed nil/cons variants')
        payload = _wire_record(sequence['payload'])
        if sequence['label'] == 'nil' and not payload:
            return entries
        if sequence['label'] != 'cons' or set(payload) != {'head', 'tail'}:
            raise ProjectionError('invalid typed ' + name + ' alternative or payload')
        if len(entries) == maximum:
            raise ProjectionError('view ' + name + ' exceed ' + str(maximum) + ' entries')
        entries.append(payload['head'])
        sequence = payload['tail']


def _typed_actions(value, budget):
    if isinstance(value, dict) and value.get('tag') == 'record':
        # Existing fixed source rows remain readable during source migration.
        return _plain_data(value, budget)
    actions = {}
    for item in _typed_list(value, 64, 'actions'):
        if isinstance(item, dict) and item.get('tag') == 'variant':
            if (set(item) != {'tag', 'label', 'payload'}
                    or not isinstance(item['label'], str) or not item['label']):
                raise ProjectionError('invalid action alternative envelope')
            # Its constructor distinguishes ordinary source input types. It
            # grants no dispatch authority; command and current law still apply.
            item = item['payload']
        descriptor = _plain_data(item, budget)
        if not isinstance(descriptor, dict) or set(descriptor) != {'key', 'text', 'command', 'input', 'visible'}:
            raise ProjectionError('listed action requires key, text, command, input and visible')
        key = _text_bound(descriptor['key'], 128, 'action key')
        if key in actions:
            raise ProjectionError('duplicate action key')
        actions[key] = {name: value for name, value in descriptor.items() if name != 'key'}
    return actions


def _typed_menu(raw, root):
    fields = _wire_record(raw)
    expected = {'title', 'prose', 'actions', 'children'}
    if 'invitations' in fields:
        expected.add('invitations')
    if 'document' in fields:
        expected.add('document')
    if 'interpretation' in fields:
        expected.add('interpretation')
    if set(fields) != expected:
        raise ProjectionError('typed menu fields differ from its declared profile')
    budget = [100000]
    values = {name: _plain_data(fields[name], budget) for name in ('title', 'prose')}
    values['actions'] = _typed_actions(fields['actions'], budget)
    data = _visible_actions(values, root)
    entries = [_plain_data(item, budget) for item in _typed_list(fields['children'], 32, 'children')]
    return data, _validate_children(entries)



def _document_data(raw):
    """Decode the declared Document algebra; no evaluation or action dispatch."""
    budget = [4096]
    def value(wire, depth=48):
        budget[0] -= 1
        if depth <= 0 or budget[0] < 0 or not isinstance(wire, dict):
            raise ProjectionError('document data bound exceeded')
        tag = wire.get('tag')
        if tag == 'record':
            return {k: value(v, depth - 1) for k, v in _wire_record(wire).items()}
        if tag == 'natural':
            _plain_data(wire, budget)
            return wire['value']  # Exact decimal text, including large source Nat values.
        return _plain_data(wire, budget, depth)
    def variant(wire, fields):
        if (not isinstance(wire, dict) or set(wire) != {'tag', 'label', 'payload'}
                or wire['tag'] != 'variant' or not isinstance(wire['label'], str) or wire['label'] not in fields):
            raise ProjectionError('unknown document alternative')
        payload = _wire_record(wire['payload'])
        if set(payload) != set(fields[wire['label']]):
            raise ProjectionError('document alternative fields differ')
        return wire['label'], payload
    def capture(wire):
        fields = _wire_record(wire)
        if not isinstance(fields.get('revision'), dict) or fields['revision'].get('tag') != 'natural':
            raise ProjectionError('document revision requires a source Nat')
        result = value(wire)
        if (not isinstance(result, dict) or set(result) != {'object', 'revision', 'meaning', 'entry', 'token'}
                or any(not isinstance(result[k], str) for k in result)
                or not re.fullmatch(r'0|[1-9][0-9]*', result['revision'])):
            raise ProjectionError('invalid document source capture')
        for name in ('object', 'entry', 'token'):
            _text_bound(result[name], 512, 'document capture ' + name, identity=True)
        return result
    def scalar(wire, kind):
        if not isinstance(wire, dict) or wire.get('tag') != kind:
            raise ProjectionError('document scalar type differs')
        return value(wire)
    def fields(wire, depth):
        result, seen = [], set()
        for item in _typed_list(wire, 128, 'document fields'):
            parts = _wire_record(item)
            if set(parts) != {'name', 'value'}:
                raise ProjectionError('document field requires name and value')
            name = scalar(parts['name'], 'label')
            if not name or name in seen:
                raise ProjectionError('duplicate or empty document field')
            seen.add(name)
            result.append({'name': name, 'value': contribution(parts['value'], depth - 1)})
        return result
    def contribution(wire, depth):
        budget[0] -= 1
        if depth <= 0 or budget[0] < 0:
            raise ProjectionError('document value bound exceeded')
        kind, parts = variant(wire, {'none': [], 'retained': ['object', 'key'], 'text': ['value'],
            'natural': ['value'], 'boolean': ['value'], 'number': ['encoded'],
            'array': ['values'], 'record': ['fields']})
        if kind == 'array':
            result = {'values': [contribution(item, depth - 1) for item in _typed_list(parts['values'], 128, 'document values')]}
        elif kind == 'record':
            result = {'fields': fields(parts['fields'], depth)}
        elif kind in ('text', 'natural', 'boolean'):
            result = {'value': scalar(parts['value'], {'text': 'label', 'natural': 'natural', 'boolean': 'boolean'}[kind])}
        else:
            result = {k: scalar(v, 'label') for k, v in parts.items()}
        return {'kind': kind, **result}
    def node(wire, depth=32):
        budget[0] -= 1
        if depth <= 0 or budget[0] < 0:
            raise ProjectionError('document tree bound exceeded')
        kind, parts = variant(wire, {'text': ['value'], 'sequence': ['items'], 'quote': ['attribution', 'body'],
            'reference': ['key', 'label', 'object', 'panel'], 'offer': ['label', 'capture'],
            'fields': ['capture', 'values', 'needs'], 'source': ['language', 'code', 'revision'],
            'result': ['status', 'body'], 'continuation': ['key', 'after', 'limit', 'label']})
        if kind == 'sequence':
            result = {'items': [node(item, depth - 1) for item in _typed_list(parts['items'], 256, 'document items')]}
        elif kind in ('quote', 'result'):
            name = 'attribution' if kind == 'quote' else 'status'
            result = {name: scalar(parts[name], 'label'), 'body': node(parts['body'], depth - 1)}
        elif kind in ('offer', 'fields'):
            result = {'capture': capture(parts['capture'])}
            if kind == 'offer':
                result['label'] = scalar(parts['label'], 'label')
            else:
                result['values'] = fields(parts['values'], depth)
                result['needs'] = [scalar(item, 'label') for item in _typed_list(parts['needs'], 128, 'document needs')]
        else:
            result = {k: scalar(v, 'natural' if kind == 'continuation' and k in ('after', 'limit') else 'label')
                      for k, v in parts.items()}
            if kind == 'reference':
                _validate_children([result])
        return {'kind': kind, **result}
    result = node(raw)
    if len(world.wire_dumps(result).encode('utf-8')) > 512 * 1024:
        raise ProjectionError('document exceeds 512 KiB')
    return result


def document(view):
    """Return only source-authored structure, checking retained raw evidence."""
    if view.get('mode') == 'raw':
        return None
    profile = view.get('root', {}).get('protocol', {}).get('viewProgram', {}).get('profile')
    if profile not in DATA_PROFILES:
        if 'document' in view:
            raise ProjectionError('document requires a typed source view')
        return None
    children(view)
    raw = _wire_record(view['rawData'])
    if 'document' not in raw:
        if 'document' in view:
            raise ProjectionError('retained document has no source result')
        return None
    checked = _document_data(raw['document'])
    if _canonical(view.get('document')) != _canonical(checked):
        raise ProjectionError('retained document differs from its raw source result')
    return copy.deepcopy(checked)


def _contribution_codec(metadata):
    if 'contributionCodec' in metadata and metadata['contributionCodec'] not in ('value', 'data'):
        raise ProjectionError('contributionCodec requires value or data')


def _typed_interpretation(raw):
    fields = _wire_record(_wire_record(raw)['interpretation'])
    if not {'request', 'prepare'} <= set(fields) or set(fields) - {'request', 'prepare', 'contributionCodec'}:
        raise ProjectionError('interpretation requires request and prepare exports with optional contributionCodec')
    result = {key: _plain_data(value, [1000]) for key, value in fields.items()}
    _contribution_codec(result)
    for key in ('request', 'prepare'):
        entry = result[key]
        if not isinstance(entry, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', entry):
            raise ProjectionError('interpretation requires source export names')
    return result


def interpretation(view):
    """Retain source-selected entry names; native compilation validates exports."""
    if view.get('mode') == 'raw':
        return None
    profile = view.get('root', {}).get('protocol', {}).get('viewProgram', {}).get('profile')
    if profile not in DATA_PROFILES:
        if 'interpretation' in view:
            raise ProjectionError('interpretation requires a typed source view')
        return None
    children(view)
    raw = _wire_record(view['rawData'])
    if 'interpretation' not in raw:
        if 'interpretation' in view:
            raise ProjectionError('retained interpretation has no source result')
        return None
    checked = _typed_interpretation(view['rawData'])
    if _canonical(view.get('interpretation')) != _canonical(checked):
        raise ProjectionError('retained interpretation differs from its source result')
    return copy.deepcopy(checked)


def bound_document(view, actions, offers):
    """Attach only existing captured invitation/child identities to source nodes."""
    result = document(view)
    if result is None:
        return None
    declared, catalogue = invitations(view), children(view)
    bindings = {}
    for action in actions:
        key, identity = action.get('offer'), action.get('id')
        offer = offers.get(identity)
        if (key in declared and offer is not None and action.get('available')
                and offer['object'] == view['object'] and offer['entry'] == declared[key]['prepare']):
            bindings[(view['object'], key, offer['entry'])] = identity
    def bind(node):
        if node['kind'] in ('offer', 'fields'):
            capture = node['capture']
            identity = bindings.get((capture['object'], capture['token'], capture['entry']))
            if identity is not None:
                node['actionId'] = identity
        elif node['kind'] == 'reference':
            descriptor = {k: node[k] for k in ('key', 'label', 'object', 'panel')}
            if descriptor in catalogue:
                node['childKey'] = descriptor['key']
        elif node['kind'] == 'sequence':
            for child in node['items']:
                bind(child)
        elif node['kind'] in ('quote', 'result'):
            bind(node['body'])
    bind(result)
    return result


def action_order(view):
    """Source list order survives canonical custody; fixed rows keep their order rule."""
    source = view.get('root', {}).get('protocol', {}).get('viewProgram', {})
    if view.get('mode') == 'projection' and source.get('profile') in DATA_PROFILES:
        fields = _wire_record(view['rawData'])
        if fields['actions'].get('tag') == 'variant':
            children(view)  # Recheck the retained normalized data against raw source.
            data, _ = _typed_menu(view['rawData'], view['root'])
            return list(data['actions'])
    return sorted(view['data']['actions'])


def children(view):
    """Read a retained source-authored catalogue, checking its exact typed origin."""
    if view.get('mode') == 'raw':
        # Recovery inspection has no evaluated catalogue, even if a retained
        # raw record happens to contain fields named children or rawData.
        return []
    program = view.get('root', {}).get('protocol', {}).get('viewProgram', {})
    if not isinstance(program, dict) or program.get('profile') not in DATA_PROFILES:
        if view.get('children', []) != []:
            raise ProjectionError('children require an explicit typed menu profile')
        return []
    if view.get('mode') != 'projection' or 'rawData' not in view:
        raise ProjectionError('typed menu observation is unavailable')
    data, descriptors = _typed_menu(view['rawData'], view['root'])
    for actual, expected in ((view.get('data'), data), (view.get('actions'), data['actions']),
                             (view.get('children'), descriptors)):
        if _canonical(actual) != _canonical(expected):
            raise ProjectionError('typed menu observation differs from its raw source result')
    return copy.deepcopy(descriptors)


def inspection_only(view):
    program = view.get('root', {}).get('protocol', {}).get('viewProgram', {})
    return (view.get('mode') == 'raw' and isinstance(program, dict)
            and program.get('profile') in DATA_PROFILES)


def _typed_invitations(raw):
    """Decode source presentation only; do not fetch observations or prepare turns."""
    rows = _wire_record(_wire_record(raw)['invitations'])
    if len(rows) > 16:
        raise ProjectionError('view invitations exceed 16 entries')
    spec = importlib.util.spec_from_file_location('invitation_affordances', ROOT / 'scripts/affordances.py')
    forms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(forms)
    result, budget = {}, [100000]
    for key in sorted(rows):
        _text_bound(key, 128, 'invitation key')
        fields = _wire_record(rows[key])
        required = {'visible', 'text', 'prepare', 'fields', 'observations'}
        if not required <= set(fields) or set(fields) - required - {'contributionCodec', 'definitions'}:
            raise ProjectionError('invitation requires visible, text, prepare, fields and observations with optional contributionCodec')
        item = {name: _plain_data(value, budget) for name, value in fields.items() if name not in ('observations', 'definitions')}
        _contribution_codec(item)
        if type(item['visible']) is not bool:
            raise ProjectionError('invitation visible requires Bool')
        _text_bound(item['text'], 4096, 'invitation text')
        _text_bound(item['prepare'], 128, 'preparation export')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', item['prepare']):
            raise ProjectionError('preparation requires a source export name')
        metadata = item['fields']
        if not isinstance(metadata, dict) or len(metadata) > 32:
            raise ProjectionError('invitation fields require a bounded record')
        for name, field in metadata.items():
            value = copy.deepcopy(field)
            if isinstance(value, dict) and value.get('type') == 'enum' and isinstance(value.get('options'), dict):
                value['options'] = [value['options'][key] for key in sorted(value['options'])]
            forms._normalize_field(name, value)
        observations = [_plain_data(value, budget) for value in _typed_list(fields['observations'], 16, 'observations')]
        names = []
        for observation in observations:
            if (not isinstance(observation, dict) or set(observation) != {'object', 'inspectState', 'inspectLaw'}
                    or type(observation['inspectState']) is not bool or type(observation['inspectLaw']) is not bool):
                raise ProjectionError('observation requires object and explicit inspection booleans')
            names.append(_text_bound(observation['object'], 512, 'observed object', identity=True))
        if len(set(names)) != len(names):
            raise ProjectionError('duplicate observation identity')
        if 'definitions' in fields:
            definitions = [_plain_data(value, budget) for value in
                           _typed_list(fields['definitions'], 16, 'definitions')]
            selected = []
            for definition in definitions:
                if not isinstance(definition, dict) or set(definition) != {'object', 'package'}:
                    raise ProjectionError('definition selection requires object and package')
                _text_bound(definition['object'], 512, 'definition object', identity=True)
                _text_bound(definition['package'], 128, 'definition package', identity=True)
                if definition['object'] not in names:
                    raise ProjectionError('definition selection requires its captured observation')
                selection = (definition['object'], definition['package'])
                if selection in selected:
                    raise ProjectionError('duplicate definition selection')
                selected.append(selection)
            item['definitions'] = definitions
        item['observations'] = observations
        if item['visible']:
            result[key] = item
    return result


def invitations(view):
    """Retained source invitations; capture separately binds explicit observations."""
    if view.get('mode') == 'raw':
        return {}
    profile = view.get('root', {}).get('protocol', {}).get('viewProgram', {}).get('profile')
    if profile not in DATA_PROFILES:
        if view.get('invitations', {}) != {}:
            raise ProjectionError('invitations require a typed source view')
        return {}
    if view.get('mode') != 'projection' or 'rawData' not in view:
        raise ProjectionError('typed invitation observation is unavailable')
    fields = _wire_record(view['rawData'])
    if 'invitations' not in fields:
        if view.get('invitations', {}) != {}:
            raise ProjectionError('retained invitations have no source result')
        return {}
    children(view)
    try:
        checked = _typed_invitations(view['rawData'])
    except (KeyError, ValueError, TypeError) as error:
        raise ProjectionError('invalid source invitation: ' + str(error)) from error
    if _canonical(view.get('invitations')) != _canonical(checked):
        raise ProjectionError('retained invitations differ from their source result')
    return copy.deepcopy(checked)


def child(view, key):
    for descriptor in children(view):
        if descriptor['key'] == key:
            return descriptor
    raise ProjectionError('unknown captured child key')


def validate_panel(root, panel):
    """Only main and explicitly declared panels are navigation destinations."""
    _text_bound(panel, 128, 'panel', identity=True)
    declared = root['protocol'].get('viewPanels', [])
    if not isinstance(declared, list) or len(declared) > 8:
        raise ProjectionError('viewPanels must contain at most eight declarations')
    seen = set()
    for entry in declared:
        if not isinstance(entry, dict) or set(entry) != {'id', 'label'}:
            raise ProjectionError('invalid declared panel')
        _text_bound(entry['id'], 128, 'panel id', identity=True)
        _text_bound(entry['label'], 128, 'panel label')
        if entry['id'] in seen:
            raise ProjectionError('duplicate declared panel')
        seen.add(entry['id'])
    if panel != 'main' and (panel not in seen or 'viewProgram' not in root['protocol']):
        raise ProjectionError('panel is not declared by this object')


def _assert_source_runtime(observed, binary_digest, expected_runtime):
    if (not isinstance(expected_runtime, dict) or expected_runtime.get('name') != 'compiled'
            or not isinstance(expected_runtime.get('files'), dict)
            or not isinstance(observed, dict) or observed.get('profile') != 'compiled'
            or observed.get('files') != expected_runtime['files']
            or not isinstance(binary_digest, str)
            or binary_digest != expected_runtime['files'].get('.lake/build/bin/delvetalk-compiled')):
        raise ProjectionError('source view runtime does not match expected compiled runtime')


def assert_runtime(view, expected_runtime):
    """Bind a retained source-view observation to its custodian's retained pins.

    No current files are read: historical observations keep their original runtime.
    This check authenticates no caller and grants no authority; it prevents silently relabeling observations.
    """
    if inspection_only(view):
        return  # Retained source/state inspection makes no evaluation claim.
    program = view.get('root', {}).get('protocol', {}).get('viewProgram', {})
    source = view.get('source', {})
    if ((isinstance(program, dict) and program.get('profile') in SOURCE_PROFILES)
            or (isinstance(source, dict) and source.get('profile') in SOURCE_PROFILES)):
        _assert_source_runtime(view.get('runtimeProfile'), view.get('runtimeSha256'), expected_runtime)


def project(root, object_id, panel='main', *, expected_runtime=None):
    """Evaluate the exact installed view term against this committed snapshot.

    The isolated Lean job has no writes/outbox and never touches a world file.
    Lean performs reduction, materialization, purity rejection and one shared
    100,000 tick budget through the compiled host's pure package evaluator.
    Python only checks framing/display schema and binds identity. This
    isolated observation does not establish termination or constancy of a program.
    World-bound callers supply their retained runtime ({} if absent); None permits
    a standalone observation under the explicitly returned current runtime pins.
    """
    if not isinstance(object_id, str) or not object_id or not isinstance(panel, str):
        raise ProjectionError('object identity and panel must be strings')
    snapshot = copy.deepcopy(root)
    try:
        program = snapshot['protocol']['viewProgram']
        if not isinstance(program, dict):
            raise ProjectionError('unsupported view program')
        if set(program) != {'profile', 'package'} or program['profile'] != DATA_MENU_PROFILE:
            raise ProjectionError('projection requires the current typed source view')
        package = program['package']
        if isinstance(package, dict) and package.get('format') == source_packages.REF:
            source_packages.validate_selector(package)
            source_packages.validate_tables(snapshot['protocol'])
        elif (not isinstance(package, dict) or set(package) != {'modules', 'entry'}
                or not isinstance(package['entry'], str) or not isinstance(package['modules'], list)
                or not 1 <= len(package['modules']) <= 64):
            raise ProjectionError('source view requires modules and entry or a local package reference')
        state = snapshot['state']
        if not isinstance(state, dict): raise ProjectionError('committed state must be a record')
        # Observation of the actual caller-held root. Governed custodians acquire
        # and recheck it before this call; no protocol, law or world is invented.
        job = {'root': snapshot, 'panel': panel}
        wire = world.wire_dumps(job)
        if len(wire.encode('utf-8')) > 64 * 1024 * 1024:
            raise ProjectionError('expanded view input exceeds observation capacity')
        host = 'compiled'
        binary = runtime_profile.PROFILES[host][0]
        binary_path = '.lake/build/bin/' + binary
        executable = ROOT / binary_path
        if not executable.is_file(): raise ProjectionError('build ' + binary + ' before projecting')
        pins = runtime_profile.file_hashes(host, root=ROOT)
        runtime = pins[binary_path]
        if expected_runtime is not None:
            _assert_source_runtime({'profile': host, 'files': pins}, runtime, expected_runtime)
        result = world.process_custody.run_native([str(executable), '--project-source'],
            input=(wire + '\n').encode('utf-8'), timeout=10, cpu_seconds=10, cwd=ROOT,
            stdout_limit=1048576, stderr_limit=1048576)
        if result.returncode: raise ProjectionError('Lean view evaluation failed')
        if len(result.stdout) > 1048576: raise ProjectionError('view output exceeds 1 MiB')
        after = runtime_profile.file_hashes(host, root=ROOT)
        if after[binary_path] != runtime:
            raise ProjectionError('view runtime changed during evaluation')
        if after != pins:
            raise ProjectionError('view runtime dependencies changed during evaluation')
        response = world.wire_loads(result.stdout)
        if 'error' in response: raise ProjectionError(str(response['error']))
        raw = response['result']
        data, descriptors = _typed_menu(raw, snapshot)
        view = {'format': FORMAT, 'mode': 'projection', 'object': object_id, 'root': snapshot,
                'panel': panel, 'source': copy.deepcopy(program), 'programSha256': _digest(program),
                'runtimeSha256': runtime, 'data': data, 'actions': copy.deepcopy(data['actions'])}
        view['runtimeProfile'] = {'profile': host, 'files': pins}
        view['rawData'] = copy.deepcopy(raw)
        view['children'] = copy.deepcopy(descriptors)
        if 'invitations' in _wire_record(raw):
            view['invitations'] = _typed_invitations(raw)
        if 'document' in _wire_record(raw):
            view['document'] = _document_data(_wire_record(raw)['document'])
        if 'interpretation' in _wire_record(raw):
            view['interpretation'] = _typed_interpretation(raw)
        return view
    except ProjectionError:
        raise
    except subprocess.TimeoutExpired as error:
        raise ProjectionError('view process deadline exceeded') from error
    except world.process_custody.OutputLimitExceeded as error:
        raise ProjectionError('view process output limit exceeded') from error
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise ProjectionError('malformed view or snapshot: ' + str(error)) from error


def request(view, action_id, principal, intent):
    """Prepare a normal request. Current-law/preimage admission remains in Lean."""
    if view.get('format') != FORMAT or view.get('mode') != 'projection':
        raise ProjectionError('expected a projected view')
    _validate(view['data'], view['root'])
    children(view)
    invitations(view)
    if not isinstance(principal, str) or not principal or not isinstance(intent, str) or not intent:
        raise ProjectionError('principal and intent must be nonempty strings')
    try: action = view['data']['actions'][action_id]
    except KeyError as error: raise ProjectionError('unknown view action') from error
    return {'op': 'invoke', 'object': view['object'], 'principal': principal, 'intent': intent,
            'expected': copy.deepcopy(view['root']), 'command': action['command'],
            'input': copy.deepcopy(action['input'])}


def html_view(view):
    """Static, escaped data only. No scripts, remote assets, or auto-invocation."""
    _validate(view['data'], view['root'])
    catalogue = children(view)
    esc = lambda value: html.escape(str(value), quote=True)
    data = view['data']
    source = view['source']
    if 'sourcePackages' in view['root']['protocol']:
        source = {'program': source, 'sourcePackages': view['root']['protocol']['sourcePackages']}
        if 'spweenSource' in view['root']['protocol']:
            source['spweenSource'] = view['root']['protocol']['spweenSource']
    items = ''.join('<li>' + esc(k) + ': ' + esc(a['text']) + '</li>'
                    for k in action_order(view) for a in [data['actions'][k]])
    exhibits = ('<h2>Look around</h2><ol>' + ''.join('<li>' + esc(child['label']) + '</li>'
                for child in catalogue) + '</ol>') if catalogue else ''
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + esc(data['title']) + '</title></head><body><h1>' + esc(data['title']) +
            '</h1><p>' + esc(data['prose']) + '</p><ul>' + items + '</ul>' + exhibits + '<p>Object: ' +
            esc(view['object']) + '</p><details><summary>Exact view program</summary><pre>' +
            esc(world.wire_dumps(source)) + '</pre></details></body></html>')
