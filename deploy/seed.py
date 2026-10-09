#!/usr/bin/env python3
"""Create one object in a world journal from a module in world/ and its imports.

Run as `python3 -m deploy.seed` from the repository root. Carries bytes: the operator names the object, the module, the creating principal
and the typed seed; the host compiles, judges and journals. Through hostd's socket.

The seed is PARTIAL: only the fields the operator means. The host lays it over the package's own
initial() (mergeSeed), refuses a field the state does not have by name, and fills an unset text
`owner` with `--owner` (opener only) or the creating principal. A genesis script never carries a
full state by hand: a hand-written full state stops conforming when the state type gains a field.

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


def main(argv=None):
    ap = argparse.ArgumentParser(prog='seed.py')
    ap.add_argument('--host-socket', required=True, help='hostd socket')
    for flag in ('--principal', '--object', '--module', '--intent', '--seed'):
        ap.add_argument(flag, required=True)
    ap.add_argument('--law', help='law text; default: the host default law')
    ap.add_argument('--owner', help="the object's owner, when the opener creates it for another principal")
    a = ap.parse_args(argv)
    req = {'op': 'world-create', 'principal': a.principal, 'identity': a.intent, 'object': a.object,
           'modules': closure(a.module, modules_on_disk()), 'entry': 'initial', 'seed': json.loads(a.seed)}
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
