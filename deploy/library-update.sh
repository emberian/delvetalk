#!/usr/bin/env bash
# Change the sealed library after launch: rebuild <state>/library from this tree's world/lib and
# world/objects/{Avatar,Env,Wake}.obend (what serve seals at its start), then ask the host for `world-library` as
# the opener, on the root socket. The world law judges it (default: only the opener); a pin change is journaled and printed.
#
#   deploy/library-update.sh [--state DIR] [--root-socket PATH] [--opener DID]
#       # defaults: /data/state, /run/delvetalk-root/root.sock, $DELVETALK_OPENER
#   docker compose run --rm delvetalk-ops deploy/library-update.sh
#
# Existing objects keep the pin they were compiled under; objects created and reprogrammed afterwards compile
# against the new library. The host replays the journal's library entry on restart, so after a change the
# image shipped next must carry the same world/ bytes. The front's REPL keeps the pin serve loaded at its start
# until serve restarts (`docker compose restart delvetalk-host`); world-check, creates and reprograms use the new library at once.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
state=/data/state root=/run/delvetalk-root/root.sock opener=${DELVETALK_OPENER:-did:plc:6amo7col5h4ciq2gpm5eur7b}
while [[ $# -gt 0 ]]; do
  case $1 in
    --state) state=$2; shift 2 ;;
    --root-socket) root=$2; shift 2 ;;
    --opener) opener=$2; shift 2 ;;
    *) echo "usage: $0 [--state DIR] [--root-socket PATH] [--opener DID]" >&2; exit 64 ;;
  esac
done
[[ -S $root ]] || { echo "library-update: no root socket at $root" >&2; exit 66; }
cd "$here/.."
PYTHONPATH=. python3 - "$state" "$root" "$opener" "library-$(date -u +%Y%m%dT%H%M%SZ)" <<'PY'
import json, shutil, sys
from pathlib import Path
from deploy.serve import LIBRARY
from transport.host import HostClient

state, root, opener, identity = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
shutil.rmtree(state / 'library', ignore_errors=True)
shutil.copytree(LIBRARY, state / 'library')
for name in ('Avatar', 'Env', 'Wake'):  # the packages world-arrive creates from, as serve seals them
    shutil.copyfile(LIBRARY.parent / 'objects' / f'{name}.obend', state / 'library' / f'{name}.obend')
reply = HostClient(root).send({'op': 'world-library', 'principal': opener, 'identity': identity})
if reply.get('status') == 'library' and not reply.get('changed', True):
    print(f"library: unchanged {reply['pin']}")
    sys.exit(0)
if reply.get('status') != 'library':
    sys.exit('library-update: refused: ' + json.dumps(reply.get('receipt', {}).get('outcome') or reply))
out = reply['receipt']['outcome']
print(f"library: {out.get('previous')} -> {out['pin']}" if out.get('previous') != out['pin'] else f"library: unchanged {out['pin']}")
PY
