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
FORMAT = 'delvetalk-projection-view-v1'
_spec = importlib.util.spec_from_file_location('projection_world', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(world)


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


def project(root, object_id, panel='main'):
    """Evaluate the exact installed view term against this committed snapshot.

    The isolated Lean job has no writes/outbox and never touches a world file.
    Lean performs reduction, materialization, purity rejection and one shared
    10,000-tick budget. Python only checks the display schema and binds identity.
    """
    if not isinstance(object_id, str) or not object_id or not isinstance(panel, str):
        raise ProjectionError('object identity and panel must be strings')
    snapshot = copy.deepcopy(root)
    try:
        program = snapshot['protocol']['viewProgram']
        if not isinstance(program, dict) or set(program) != {'profile', 'term'} or program['profile'] != PROFILE:
            raise ProjectionError('unsupported view program')
        state = snapshot['state']
        if not isinstance(state, dict): raise ProjectionError('committed state must be a record')
        # Reuse the actual Lean materializer, without making a request against
        # the live object, acquiring authority, or persisting a synthetic world.
        command = {'require': [], 'set': {}, 'outbox': [],
                   'result': ['bend', program['term'], [['literal', state], ['literal', panel]]]}
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'project': command}}
        local = {'protocol': protocol, 'law': ['projection'], 'version': 0, 'state': {}}
        job = {'world': {'objects': {'projection': local}, 'receipts': []},
               'request': {'op': 'invoke', 'object': 'projection', 'principal': 'projection',
                           'intent': 'projection', 'expected': local, 'command': 'project', 'input': {}}}
        wire = world.wire_dumps(job)
        if len(wire.encode('utf-8')) > 65536: raise ProjectionError('view input exceeds 64 KiB')
        executable = ROOT / '.lake/build/bin/delvetalk-world'
        if not executable.is_file(): raise ProjectionError('build delvetalk-world before projecting')
        runtime = hashlib.sha256(executable.read_bytes()).hexdigest()
        result = subprocess.run([str(executable)], input=wire + '\n', text=True,
                                capture_output=True, timeout=10, cwd=ROOT)
        if result.returncode: raise ProjectionError('Lean view evaluation failed')
        if len(result.stdout.encode('utf-8')) > 1048576: raise ProjectionError('view output exceeds 1 MiB')
        if hashlib.sha256(executable.read_bytes()).hexdigest() != runtime:
            raise ProjectionError('view runtime changed during evaluation')
        response = world.wire_loads(result.stdout)
        if 'error' in response: raise ProjectionError(str(response['error']))
        receipt = response['reply']
        if receipt['kind'] != 'committed': raise ProjectionError('view refused: ' + str(receipt['data']))
        data = _validate(receipt['data']['result'], snapshot)
        return {'format': FORMAT, 'mode': 'projection', 'object': object_id, 'root': snapshot,
                'panel': panel, 'source': copy.deepcopy(program), 'programSha256': _digest(program),
                'runtimeSha256': runtime, 'data': data, 'actions': copy.deepcopy(data['actions'])}
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
