#!/usr/bin/env python3
"""Pure Bend views through Lean; rendering and request framing grant no authority."""
from __future__ import annotations
import copy
import hashlib
import html
import importlib.util
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'delvetalk-bend-view-v1'
SOURCE_PROFILE = 'delvetalk-obend-view-v1'
MENU_PROFILE = 'delvetalk-obend-menu-v1'
SOURCE_PROFILES = (SOURCE_PROFILE, MENU_PROFILE)
FORMAT = 'delvetalk-projection-view-v1'
_spec = importlib.util.spec_from_file_location('projection_world', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(world)
_spec = importlib.util.spec_from_file_location('projection_runtime', ROOT / 'scripts/runtime_profile.py')
runtime_profile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime_profile)


class ProjectionError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(world.wire_dumps(value).encode('utf-8')).hexdigest()


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
        if source_view:
            if set(program) != {'profile', 'package'}:
                raise ProjectionError('unsupported source view program')
            package = program['package']
            if (not isinstance(package, dict) or set(package) != {'modules', 'entry'}
                    or not isinstance(package['entry'], str)
                    or not isinstance(package['modules'], list)
                    or not 1 <= len(package['modules']) <= 64
                    or any(not isinstance(module, dict) or set(module) != {'name', 'source'}
                           or not all(isinstance(module[key], str) for key in ('name', 'source'))
                           for module in package['modules'])):
                raise ProjectionError('source view requires source-only modules and entry')
        elif set(program) != {'profile', 'term'} or program['profile'] != PROFILE:
            raise ProjectionError('unsupported view program')
        state = snapshot['state']
        if not isinstance(state, dict): raise ProjectionError('committed state must be a record')
        # Reuse the actual Lean materializer, without making a request against
        # the live object, acquiring authority, or persisting a synthetic world.
        expression = ['package', program['package']] if source_view else ['bend', program['term']]
        command = {'require': [], 'set': {}, 'outbox': [],
                   'result': expression + [[['literal', state], ['literal', panel]]]}
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'project': command}}
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
        data = _menu_data(raw, snapshot) if menu_view else _validate(raw, snapshot)
        view = {'format': FORMAT, 'mode': 'projection', 'object': object_id, 'root': snapshot,
                'panel': panel, 'source': copy.deepcopy(program), 'programSha256': _digest(program),
                'runtimeSha256': runtime, 'data': data, 'actions': copy.deepcopy(data['actions'])}
        if source_view:
            view['runtimeProfile'] = {'profile': host, 'files': pins}
        if menu_view:
            view['rawData'] = copy.deepcopy(raw)
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
    esc = lambda value: html.escape(str(value), quote=True)
    data = view['data']
    items = ''.join('<li>' + esc(k) + ': ' + esc(a['text']) + '</li>'
                    for k, a in data['actions'].items())
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + esc(data['title']) + '</title></head><body><h1>' + esc(data['title']) +
            '</h1><p>' + esc(data['prose']) + '</p><ul>' + items + '</ul><p>Object: ' +
            esc(view['object']) + '</p><details><summary>Exact view program</summary><pre>' +
            esc(world.wire_dumps(view['source'])) + '</pre></details></body></html>')
