#!/usr/bin/env python3
"""Create one object in a world journal from a module in world/ and its imports.

Run as `python3 -m deploy.seed` from the repository root. Carries bytes: the operator names the object, the module, the creating principal
and the typed seed; the host compiles, judges and journals. Through hostd's socket.

The seed is PARTIAL: only the fields the operator means, laid over the package's own initial(). A genesis
script never carries a full state by hand: when an object's state type gains a field, a hand-written full
state stops conforming and genesis fails (it did, 2026-10-09: Directory and Garden gained owner, greeted,
pageCheckpoint, confirm). Until world-create overlays a partial seed itself, full_state() runs initial()
through the host's stateless process and overlays the given top-level fields here; a field the state does
not have is refused by name. `--owner DID` (opener only) creates the object for that owner.

  python3 -m deploy.seed --host-socket /data/state/host.sock --principal did:plc:... \
      --object garden --module Garden --intent mk-garden \
      --seed '{"tag":"record","fields":[...]}'
"""
import argparse
import json
import re
import sys
from pathlib import Path

from transport.hostproc import HostClient

ROOT = Path(__file__).resolve().parent.parent
IMPORT = re.compile(r'^import \./(\w+)\.obend', re.M)


def modules_on_disk():
    return {p.stem: p for sub in ('lib', 'objects') for p in sorted((ROOT / 'world' / sub).rglob('*.obend'))}


def closure(name, found, seen=None, out=None):
    """The module and its imports, imports first."""
    seen, out = (set(), []) if seen is None else (seen, out)
    if name not in seen:
        seen.add(name)
        source = found[name].read_text()
        for dep in IMPORT.findall(source):
            closure(dep, found, seen, out)
        out.append({'name': name, 'source': source})
    return out


class SeedError(Exception):
    pass


LAW_LINE = re.compile(r'^law .*$', re.M)


def initial_state(stateless, modules):
    """The package's initial() as typed data, run by the host (never written by hand). The stateless
    process is the pure profile, which refuses packages that declare laws; a law judges writes and
    never enters initial(), so its lines are blanked for this one evaluation. The object itself is
    created from the unmodified modules."""
    pure = [dict(m, source=LAW_LINE.sub('', m['source'])) for m in modules]
    compiled = stateless.send({'op': 'compile', 'modules': pure, 'entry': 'initial'})
    if compiled.get('status') != 'compiled':
        raise SeedError('initial() does not compile: ' + json.dumps(compiled)[:2000])
    ran = stateless.send({'op': 'run-data-v1', 'arguments': [], 'artifact': compiled['artifact']})
    if ran.get('status') != 'finished':
        raise SeedError('initial() did not finish: ' + json.dumps(ran)[:2000])
    return ran['value']


def overlay(state, partial):
    """Top-level fields of `partial` replace the same fields of `state`; an unknown field is refused."""
    if partial.get('tag') != 'record' or state.get('tag') != 'record':
        raise SeedError('a seed and a state are records')
    names = [f['name'] for f in state['fields']]
    given = {f['name']: f['value'] for f in partial['fields']}
    unknown = [n for n in given if n not in names]
    if unknown:
        raise SeedError('the state has no field ' + ', '.join(unknown) + '; it has ' + ', '.join(names))
    return {'tag': 'record', 'fields': [{'name': f['name'], 'value': given.get(f['name'], f['value'])} for f in state['fields']]}


def full_state(socket_path, modules, partial):
    return overlay(initial_state(HostClient(socket_path, stateless=True), modules), partial)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='seed.py')
    ap.add_argument('--host-socket', required=True, help='hostd socket')
    for flag in ('--principal', '--object', '--module', '--intent', '--seed'):
        ap.add_argument(flag, required=True)
    ap.add_argument('--law', help='law text; default: the host default law')
    ap.add_argument('--owner', help="the object's owner, when the opener creates it for another principal")
    a = ap.parse_args(argv)
    modules = closure(a.module, modules_on_disk())
    try:
        seed = full_state(a.host_socket, modules, json.loads(a.seed))
    except SeedError as e:
        print(json.dumps({'status': 'error', 'message': str(e)}, sort_keys=True))
        return 1
    req = {'op': 'world-create', 'principal': a.principal, 'identity': a.intent, 'object': a.object,
           'modules': modules, 'entry': 'initial', 'seed': seed}
    if a.law:
        req['law'] = a.law
    if a.owner:
        req['owner'] = a.owner
    host = HostClient(a.host_socket)
    try:
        reply = host.send(req)
    finally:
        host.close()
    print(json.dumps(reply, sort_keys=True))
    return 0 if reply.get('status') == 'created' else 1


if __name__ == '__main__':
    sys.exit(main())
