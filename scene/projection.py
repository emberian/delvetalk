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
PROFILE = 'delvetalk-bend-view-v1'
SOURCE_PROFILE = 'delvetalk-obend-view-v1'
MENU_PROFILE = 'delvetalk-obend-menu-v1'
DATA_MENU_PROFILE = 'delvetalk-obend-data-menu-v1'
DATA_OFFERS_PROFILE = 'delvetalk-obend-data-offers-v1'
DATA_PROFILES = (DATA_MENU_PROFILE, DATA_OFFERS_PROFILE)
SOURCE_PROFILES = (SOURCE_PROFILE, MENU_PROFILE, *DATA_PROFILES)
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


def _menu_data(raw, root):
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


def _typed_menu(raw, root):
    fields = _wire_record(raw)
    expected = {'title', 'prose', 'actions', 'children'}
    if root['protocol']['viewProgram']['profile'] == DATA_OFFERS_PROFILE:
        expected.add('offers')
    if set(fields) != expected:
        raise ProjectionError('typed menu fields differ from its declared profile')
    budget = [100000]
    data = _menu_data({name: _plain_data(fields[name], budget) for name in ('title', 'prose', 'actions')}, root)
    sequence, entries = fields['children'], []
    while True:
        if (not isinstance(sequence, dict) or set(sequence) != {'tag', 'label', 'payload'}
                or sequence['tag'] != 'variant'):
            raise ProjectionError('children require typed nil/cons variants')
        payload = _wire_record(sequence['payload'])
        if sequence['label'] == 'nil' and not payload:
            break
        if sequence['label'] != 'cons' or set(payload) != {'head', 'tail'}:
            raise ProjectionError('invalid typed children alternative or payload')
        if len(entries) == 32:
            raise ProjectionError('view children exceed 32 entries')
        entries.append(_plain_data(payload['head'], budget))
        sequence = payload['tail']
    return data, _validate_children(entries)


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


def _typed_offers(raw):
    descriptors = _plain_data(_wire_record(raw)['offers'], [100000])
    # This shared validator checks framing, never reads other objects or executes
    # source. Validate hidden descriptors before applying authored visibility.
    spec = importlib.util.spec_from_file_location('projection_source_offers', ROOT / 'scripts/source_offers.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    checked = helper.validate_descriptors(descriptors)
    return {key: value for key, value in checked.items() if value['visible']}


def offers(view):
    """Read validated source-owned plans; capture resolves their declared reads."""
    if view.get('mode') == 'raw':
        return {}
    profile = view.get('root', {}).get('protocol', {}).get('viewProgram', {}).get('profile')
    if profile != DATA_OFFERS_PROFILE:
        if view.get('offers', {}) != {}:
            raise ProjectionError('offers require an explicit source offers profile')
        return {}
    if view.get('mode') != 'projection' or 'rawData' not in view:
        raise ProjectionError('typed offers observation is unavailable')
    children(view)
    try:
        checked = _typed_offers(view['rawData'])
    except (KeyError, ValueError, TypeError) as error:
        raise ProjectionError('invalid source offers: ' + str(error)) from error
    if _canonical(view.get('offers')) != _canonical(checked):
        raise ProjectionError('retained offers differ from their raw source result')
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
    Legacy core views retain their existing contract. This check authenticates no
    caller and grants no authority; it prevents silently relabeling observations.
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
    tick budget (10,000 for core views; the compiled host's 100,000 for source
    views). Python only checks framing/display schema and binds identity. This
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
        source_view = program.get('profile') in SOURCE_PROFILES
        menu_view = program.get('profile') == MENU_PROFILE
        data_menu = program.get('profile') in DATA_PROFILES
        if source_view:
            if set(program) != {'profile', 'package'}:
                raise ProjectionError('unsupported source view program')
            package = program['package']
            if isinstance(package, dict) and package.get('format') == source_packages.REF:
                source_packages.validate_selector(package)
                source_packages.validate_tables(snapshot['protocol'])
            elif (not isinstance(package, dict) or set(package) != {'modules', 'entry'}
                    or not isinstance(package['entry'], str)
                    or not isinstance(package['modules'], list)
                    or not 1 <= len(package['modules']) <= 64
                    or any(not isinstance(module, dict) or set(module) != {'name', 'source'}
                           or not all(isinstance(module[key], str) for key in ('name', 'source'))
                           for module in package['modules'])):
                raise ProjectionError('source view requires source-only modules and entry or a local package reference')
        elif set(program) != {'profile', 'term'} or program['profile'] != PROFILE:
            raise ProjectionError('unsupported view program')
        state = snapshot['state']
        if not isinstance(state, dict): raise ProjectionError('committed state must be a record')
        # Reuse the actual Lean materializer, without making a request against
        # the live object, acquiring authority, or persisting a synthetic world.
        arguments = [state, panel]
        expression = ['package', program['package']] if source_view else ['bend', program['term']]
        if data_menu:
            if set(state) != {'model'}:
                raise ProjectionError('typed view state requires exactly model')
            expression = ['package-data-v1', program['package']]
            arguments = [state['model'], {'tag': 'label', 'value': panel}]
        command = {'require': [], 'set': {}, 'outbox': [],
                   'result': expression + [[['literal', argument] for argument in arguments]]}
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'project': command}}
        if source_view and 'sourcePackages' in snapshot['protocol']:
            # Preserve the owning source context. Only the native receiver resolves
            # the selector; Python must not expand or choose executable modules.
            protocol['sourcePackages'] = copy.deepcopy(snapshot['protocol']['sourcePackages'])
        local = {'protocol': protocol, 'law': ['projection'], 'version': 0, 'state': {}}
        job = {'world': {'objects': {'projection': local}, 'receipts': []},
               'request': {'op': 'invoke', 'object': 'projection', 'principal': 'projection',
                           'intent': 'projection', 'expected': local, 'command': 'project', 'input': {}}}
        wire = world.wire_dumps(job)
        if len(wire.encode('utf-8')) > 65536: raise ProjectionError('view input exceeds 64 KiB')
        host = 'compiled' if source_view else 'world'
        binary = runtime_profile.PROFILES[host][0]
        binary_path = '.lake/build/bin/' + binary
        executable = ROOT / binary_path
        if not executable.is_file(): raise ProjectionError('build ' + binary + ' before projecting')
        pins = runtime_profile.file_hashes(host, root=ROOT) if source_view else None
        runtime = (pins if source_view else runtime_profile.hash_paths([binary_path], root=ROOT))[binary_path]
        if source_view and expected_runtime is not None:
            _assert_source_runtime({'profile': host, 'files': pins}, runtime, expected_runtime)
        result = subprocess.run([str(executable)], input=wire + '\n', text=True,
                                capture_output=True, timeout=10, cwd=ROOT)
        if result.returncode: raise ProjectionError('Lean view evaluation failed')
        if len(result.stdout.encode('utf-8')) > 1048576: raise ProjectionError('view output exceeds 1 MiB')
        after = (runtime_profile.file_hashes(host, root=ROOT) if source_view else
                 runtime_profile.hash_paths([binary_path], root=ROOT))
        if after[binary_path] != runtime:
            raise ProjectionError('view runtime changed during evaluation')
        if source_view and after != pins:
            raise ProjectionError('view runtime dependencies changed during evaluation')
        response = world.wire_loads(result.stdout)
        if 'error' in response: raise ProjectionError(str(response['error']))
        receipt = response['reply']
        if receipt['kind'] != 'committed': raise ProjectionError('view refused: ' + str(receipt['data']))
        raw = receipt['data']['result']
        if data_menu:
            data, descriptors = _typed_menu(raw, snapshot)
        else:
            data = _menu_data(raw, snapshot) if menu_view else _validate(raw, snapshot)
        view = {'format': FORMAT, 'mode': 'projection', 'object': object_id, 'root': snapshot,
                'panel': panel, 'source': copy.deepcopy(program), 'programSha256': _digest(program),
                'runtimeSha256': runtime, 'data': data, 'actions': copy.deepcopy(data['actions'])}
        if source_view:
            view['runtimeProfile'] = {'profile': host, 'files': pins}
        if menu_view or data_menu:
            view['rawData'] = copy.deepcopy(raw)
        if data_menu:
            view['children'] = copy.deepcopy(descriptors)
        if program['profile'] == DATA_OFFERS_PROFILE:
            view['offers'] = _typed_offers(raw)
        return view
    except ProjectionError:
        raise
    except subprocess.TimeoutExpired as error:
        raise ProjectionError('view process deadline exceeded') from error
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise ProjectionError('malformed view or snapshot: ' + str(error)) from error


def request(view, action_id, principal, intent):
    """Prepare a normal request. Current-law/preimage admission remains in Lean."""
    if view.get('format') != FORMAT or view.get('mode') != 'projection':
        raise ProjectionError('expected a projected view')
    _validate(view['data'], view['root'])
    children(view)
    offers(view)
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
                    for k, a in data['actions'].items())
    exhibits = ('<h2>Look around</h2><ol>' + ''.join('<li>' + esc(child['label']) + '</li>'
                for child in catalogue) + '</ol>') if catalogue else ''
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + esc(data['title']) + '</title></head><body><h1>' + esc(data['title']) +
            '</h1><p>' + esc(data['prose']) + '</p><ul>' + items + '</ul>' + exhibits + '<p>Object: ' +
            esc(view['object']) + '</p><details><summary>Exact view program</summary><pre>' +
            esc(world.wire_dumps(source)) + '</pre></details></body></html>')
