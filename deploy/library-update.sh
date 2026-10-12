#!/usr/bin/env bash
# Change the sealed library after launch: rebuild <state>/library from the config's `library` and
# world/objects/Avatar.obend (what serve seals at its start), then ask the host for `world-library` as
# the opener, on the root socket. The world law judges it (default: only the opener); a pin change is journaled and printed.
#
#   deploy/library-update.sh [--state DIR] [--world W]      # default DELVETALK_STATE, town
#   docker compose run --rm delvetalk-ops deploy/library-update.sh
#
# Existing objects keep the pin they were compiled under; objects created and reprogrammed afterwards compile
# against the new library. The host replays the journal's library entry on restart, so after a change the
# image shipped next must carry the same world/ bytes. The front's REPL keeps the pin serve loaded at its start
# until serve restarts (`docker compose restart delvetalk-host`); world-check, creates and reprograms use the new library at once.
set -euo pipefail
state=${DELVETALK_STATE:-} world=town
while [[ $# -gt 0 ]]; do
  case $1 in
    --state) state=$2; shift 2 ;;
    --world) world=$2; shift 2 ;;
    *) echo "usage: $0 [--state DIR] [--world W]" >&2; exit 64 ;;
  esac
done
cd "$(dirname "$0")/.."
PYTHONPATH=. python3 - "${state:?--state or DELVETALK_STATE}" "$world" "library-$(date -u +%Y%m%dT%H%M%SZ)" <<'PY'
import json, shutil, sys
from pathlib import Path
from transport.state import State

st, identity = State(sys.argv[1], sys.argv[2]), sys.argv[3]
if not st.root_socket.is_socket():
    sys.exit(f'library-update: no root socket at {st.root_socket}')
source, fresh, old = Path(st.config.library), st.library.with_name('library.new'), st.library.with_name('library.old')
shutil.rmtree(fresh, ignore_errors=True)  # built whole beside the live one, then put in its place
shutil.copytree(source, fresh)
shutil.copyfile(source.parent / 'objects' / 'Avatar.obend', fresh / 'Avatar.obend')  # what world-arrive creates from (Serve.lean `arrival`)
shutil.rmtree(old, ignore_errors=True)
st.library.rename(old)
fresh.rename(st.library)
shutil.rmtree(old)
reply = st.root_host().send({'op': 'world-library', 'principal': st.config.opener, 'identity': identity})
if reply.get('status') == 'library' and not reply.get('changed', True):
    print(f"library: unchanged {reply['pin']}")
    sys.exit(0)
if reply.get('status') != 'library':
    sys.exit('library-update: refused: ' + json.dumps(reply.get('receipt', {}).get('outcome') or reply))
out = reply['receipt']['outcome']
print(f"library: {out.get('previous')} -> {out['pin']}" if out.get('previous') != out['pin'] else f"library: unchanged {out['pin']}")
PY
