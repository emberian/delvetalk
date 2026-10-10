#!/usr/bin/env bash
# Playtest DelveTalk in the owner's own Zulip, before it goes to delve.town. No Delve credential is read.
#
#   deploy/playtest.sh --zuliprc PATH [--stream delvetalk] [--topic NAME] [--poll 20] [--post-quota N] [--port 8765] [--dir DIR]
#   deploy/playtest.sh --stop [--dir DIR]
#
# Starts hostd on a FRESH journal (DIR/run-<stamp>/, DIR/current points at it; older runs are left in place),
# runs genesis, posts docs/previews/zulip-welcome-v2.txt (STUDIO pointing at the local front on --port) to the stream's `welcome` topic (or --topic NAME, the only topic then observed and answered in) and records it against
# `directory`, then runs the local front, the bridge (--source zulip: observe, turn, post drafts back automatically) and the
# interpreter, each every --poll seconds. The bot is the .zuliprc's user; it must be subscribed to the stream.
# DELVETALK_OBEND names the host binary; the interpreter needs the model credentials docs/DEPLOY.md describes.
set -euo pipefail
cd "$(dirname "$0")/.."
stream=delvetalk topic= quota= poll=20 port=8765 dir=${DELVETALK_PLAYTEST_DIR:-$HOME/.delvetalk-playtest} rc= stop=
while [[ $# -gt 0 ]]; do
  case $1 in
    --zuliprc) rc=$2; shift 2;;
    --stream) stream=$2; shift 2;;
    --topic) topic=$2; shift 2;;
    --poll) poll=$2; shift 2;;
    --post-quota) quota=$2; shift 2;;
    --port) port=$2; shift 2;;
    --dir) dir=$2; shift 2;;
    --stop) stop=1; shift;;
    *) sed -n '2,12p' "$0" >&2; exit 64;;
  esac
done

if [[ -n $stop ]]; then
  [[ -L $dir/current ]] || { echo "playtest: nothing running under $dir" >&2; exit 1; }
  state=$(cd "$dir/current" && pwd -P)/state
  for name in bridge interpret front hostd; do  # the host last: the clients are its tenants
    pidfile=$state/$name.pid
    [[ -f $pidfile ]] || continue
    pid=$(cat "$pidfile")
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
export PYTHONPATH=$PWD
log() { echo "$run/$1.log"; }

python3 -m transport.hostd --state "$state" --journal "$run/world.journal" ${quota:+--post-quota "$quota"} --opener "$(python3 -c 'from deploy.genesis import OPENER; print(OPENER)')" >"$(log hostd)" 2>&1 &
for _ in $(seq 100); do [[ -S $state/host.sock ]] && break; sleep 0.2; done
[[ -S $state/host.sock ]] || { echo "playtest: hostd did not come up; see $(log hostd)" >&2; exit 1; }

python3 -m deploy.genesis --host-socket "$state/host.sock"
sed "s#http://127.0.0.1:8765#http://127.0.0.1:$port#" docs/previews/zulip-welcome-v2.txt >"$run/welcome.txt"
python3 -m transport.zulip post --state "$state" --zuliprc "$rc" --stream "$stream" --topic "${topic:-welcome}" \
  --text-file "$run/welcome.txt" --object directory --host-socket "$state/host.sock"

nohup python3 -m transport.bridge run --state "$state" --source zulip --zuliprc "$rc" --stream "$stream" ${topic:+--topic "$topic"} --poll "$poll" --origin "http://127.0.0.1:$port" >"$(log bridge)" 2>&1 &
nohup python3 -m transport.http --state "$state" --port "$port" --origin "http://127.0.0.1:$port" >"$(log front)" 2>&1 &
echo $! >"$state/front.pid"
nohup python3 -m transport.interpret run --state "$state" --poll "$poll" >"$(log interpret)" 2>&1 &
echo "playtest: running in #$stream${topic:+ > $topic}; state $state; logs $run/*.log; stop with: deploy/playtest.sh --stop"
