#!/usr/bin/env bash
# Playtest DelveTalk in the owner's own Zulip, before it goes to delve.town. No Delve credential is read.
#
#   deploy/playtest.sh --zuliprc PATH [--stream delvetalk] [--topic NAME] [--poll 20] [--no-welcome] [--port 8765] [--dir DIR]
#   deploy/playtest.sh --stop [--dir DIR]
#
# A FRESH state directory (DIR/run-<stamp>/state; DIR/current points at it; older runs are left in place) whose
# delvetalk.toml names the local front's origin and port and the poll, and whose town is opened on the stream
# (`transport open --transport zulip`, its bridge row). Then serve, genesis, the config's `welcome` (STUDIO pointing at
# the local front) posted to the stream's `welcome` topic (or --topic NAME, the only topic then observed and answered
# in) and recorded against `commonplace`, then the front, the bridge (observe, turn, post drafts back) and the
# interpreter. Each detached job writes DIR/run-<stamp>/<name>.pid, which --stop reads. The bot is the .zuliprc's
# user; it must be subscribed to the stream. DELVETALK_OBEND names the host binary; the interpreter needs the model
# credentials docs/DEPLOY.md describes.
set -euo pipefail
cd "$(dirname "$0")/.."
stream=delvetalk topic= nowelcome= poll=20 port=8765 dir=$HOME/.delvetalk-playtest rc= stop=
while [[ $# -gt 0 ]]; do
  case $1 in
    --zuliprc) rc=$2; shift 2;;
    --stream) stream=$2; shift 2;;
    --topic) topic=$2; shift 2;;
    --poll) poll=$2; shift 2;;
    --port) port=$2; shift 2;;
    --dir) dir=$2; shift 2;;
    --no-welcome) nowelcome=1; shift;;
    --stop) stop=1; shift;;
    *) sed -n 2,15p "$0" >&2; exit 64;;
  esac
done

if [[ -n $stop ]]; then
  [[ -L $dir/current ]] || { echo "playtest: nothing running under $dir" >&2; exit 1; }
  run=$(cd "$dir/current" && pwd -P)
  for name in bridge interpret front host; do  # the host last: the clients are its tenants
    [[ -f $run/$name.pid ]] || continue
    pid=$(cat "$run/$name.pid")
    if kill -0 "$pid" 2>/dev/null; then kill "$pid"; for _ in $(seq 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done; fi
    echo "playtest: stopped $name ($pid)"
  done
  rm -f "$dir/current"
  exit 0
fi

[[ -n $rc && -r $rc ]] || { echo "playtest: --zuliprc PATH (readable) is required" >&2; exit 64; }
[[ -e $dir/current ]] && { echo "playtest: already started under $dir; run --stop first" >&2; exit 1; }
run=$dir/run-$(date +%Y%m%d-%H%M%S)
state=$run/state
mkdir -p -m 700 "$state"
ln -sfn "$run" "$dir/current"
export PYTHONPATH=$PWD DELVETALK_STATE=$state
log() { echo "$run/$1.log"; }
start() { local name=$1; shift; nohup "$@" >"$(log "$name")" 2>&1 & echo $! >"$run/$name.pid"; }

printf 'origin = "http://127.0.0.1:%s"\nhttp_port = %s\npoll = %s\n' "$port" "$port" "$poll" >"$state/delvetalk.toml"
realm=$(sed -n 's#^site *= *https*://\([^/]*\).*#\1#p' "$rc")
python3 -m transport open --transport zulip --realm "$realm" --channel "$stream" --zuliprc "$rc" ${topic:+--topic "$topic"} >/dev/null
start host python3 -m transport serve
for _ in $(seq 600); do [[ -S $state/host.sock && -S $state/root/root.sock ]] && break; sleep 0.2; done
[[ -S $state/root/root.sock ]] || { echo "playtest: serve did not come up; see $(log host)" >&2; exit 1; }

python3 -m deploy.genesis --root-socket "$state/root/root.sock"
if [[ -z $nowelcome ]]; then
  welcome=$(python3 -c 'from transport.config import Config; import sys; print(Config.load(sys.argv[1]).welcome)' "$state")
  sed "s#http://127.0.0.1:8765#http://127.0.0.1:$port#" "$welcome" >"$run/welcome.txt"
  python3 -m transport post --topic "${topic:-welcome}" --text-file "$run/welcome.txt" --object commonplace --intent welcome-1
else  # the stream already holds the welcome and the page cards: make the page drafts, mark them posted, post nothing
  python3 - <<'PY'
import os
from transport.bridge import publication_drafts
from transport.state import State
st = State(os.environ['DELVETALK_STATE'])
publication_drafts(st, st.host())
for path, d in st.unposted():
    if 'publication' in d:
        st.mark_posted(path)
PY
fi

start bridge python3 -m transport bridge
start front python3 -m transport http
start interpret python3 -m transport interpret
echo "playtest: running in #$stream${topic:+ > $topic}; state $state; logs $run/*.log; stop with: deploy/playtest.sh --stop"
