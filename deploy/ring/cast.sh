#!/usr/bin/env bash
# Start, stop or list the ring's residents (allgame harnesses) against one stream. Decides nothing: the roster is --roles.
#   deploy/ring/cast.sh start --stream ring --roles deploy/ring/roles [--state ~/.ring] [--allgame ~/dev/allgame]
#   deploy/ring/cast.sh stop   [--state ~/.ring]
#   deploy/ring/cast.sh status [--state ~/.ring]
# A role is a directory under --roles with brief.md (-> identity.md, written once), resident.env (HARNESS, ZULIPRC, HANDLE;
# optional MODEL, ARCS, RESIDENT_BASE_URL, RESIDENT_KEY_FILE) and the shared roles/RULES.md (-> sysadmin_inbox.md, once).
# The zuliprc is passed to the harness as a path and never read here. docs/RING-OF-FIRE.md section 6.
set -euo pipefail
cmd=${1:-status}; [[ $# -gt 0 ]] && shift
stream=ring roles= state=${RING_STATE:-$HOME/.ring} allgame=${ALLGAME_DIR:-$HOME/dev/allgame}
while [[ $# -gt 0 ]]; do
  case $1 in
    --stream) stream=$2; shift 2;; --roles) roles=$2; shift 2;; --state) state=$2; shift 2;; --allgame) allgame=$2; shift 2;;
    *) sed -n '2,8p' "$0" >&2; exit 64;;
  esac
done
alive() { [[ -f $1 ]] && kill -0 -- "-$(cat "$1")" 2>/dev/null; }  # the pid is a process group leader (see start)
case $cmd in
start)
  [[ -n $roles && -d $roles && -f $roles/RULES.md ]] || { echo "cast: --roles DIR with RULES.md is required" >&2; exit 64; }
  for dir in "$roles"/*/; do
    role=$(basename "$dir"); home=$state/$role; mkdir -p -m 700 "$home"
    if alive "$home/cast.pid"; then echo "cast: $role already running ($(cat "$home/cast.pid"))"; continue; fi
    unset HARNESS ZULIPRC HANDLE MODEL ARCS RESIDENT_BASE_URL RESIDENT_KEY_FILE
    set -a; . "$dir/resident.env"; set +a
    [[ -n ${HARNESS:-} && -n ${ZULIPRC:-} && -n ${HANDLE:-} ]] || { echo "cast: $role: resident.env needs HARNESS, ZULIPRC, HANDLE" >&2; exit 64; }
    [[ -r $ZULIPRC ]] || { echo "cast: $role: no readable zuliprc at $ZULIPRC" >&2; exit 1; }
    [[ -f $home/identity.md ]] || cp "$dir/brief.md" "$home/identity.md"
    [[ -f $home/sysadmin_inbox.md ]] || cp "$roles/RULES.md" "$home/sysadmin_inbox.md"
    printf '{"role":"%s","harness":"%s","model":"%s","handle":"%s","arcs":"%s","stream":"%s","started":%s}\n' \
      "$role" "$HARNESS" "${MODEL:-}" "$HANDLE" "${ARCS:-}" "$stream" "$(date +%s)" >"$home/cast.json"
    args=(--zuliprc "$ZULIPRC")
    [[ -n ${MODEL:-} ]] && args+=(--model "$MODEL")
    if [[ $HARNESS == kimi_resident ]]; then args+=(--stream "$stream"); else args+=(--state-dir "$home" --standing-streams "$stream"); fi
    # Its own session and process group, so stop can end the harness, its supervisor and the supervised child together.
    (cd "$allgame" && RESIDENT_STATE_DIR=$home YUE_STATE_DIR=$home RESIDENT_BG_CONTAINER=ring-$role \
      nohup python3 -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
      uv run python -m "$HARNESS" "${args[@]}" >>"$home/cast.log" 2>&1 & echo $! >"$home/cast.pid")
    echo "cast: started $role ($HARNESS, pid $(cat "$home/cast.pid")) -> $home"
  done;;
stop)
  for pidfile in "$state"/*/cast.pid; do
    [[ -f $pidfile ]] || continue
    role=$(basename "$(dirname "$pidfile")"); pid=$(cat "$pidfile")
    if kill -0 -- "-$pid" 2>/dev/null; then kill -TERM -- "-$pid"; for _ in $(seq 150); do kill -0 -- "-$pid" 2>/dev/null || break; sleep 0.2; done; fi
    kill -0 -- "-$pid" 2>/dev/null && { echo "cast: $role ($pid) did not stop" >&2; continue; }
    rm -f "$pidfile"; echo "cast: stopped $role ($pid)"
  done;;
status)
  for home in "$state"/*/; do
    [[ -f $home/cast.json ]] || continue
    if alive "$home/cast.pid"; then up="up $(cat "$home/cast.pid")"; else up=down; fi
    printf '%-12s %-10s %s\n' "$(basename "$home")" "$up" "$(tail -n 1 "$home/cast.log" 2>/dev/null | cut -c1-100)"
  done;;
*) sed -n '2,8p' "$0" >&2; exit 64;;
esac
