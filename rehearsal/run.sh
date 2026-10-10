#!/bin/sh
# The offline rehearsal, run on a remote box (default hbox) with no network. One command:
#   rehearsal/run.sh [--keep] [HOST]
# 1. Refuses a stale binary: the host binary ($DELVETALK_REHEARSAL_BINARY, default hbox's
#    dt-foundation build) must come from a tree ($DELVETALK_REHEARSAL_SOURCE, default
#    scratch/dt-foundation) whose spec/ is this tree's, file for file, unless
#    DELVETALK_REHEARSAL_ANY_BINARY=1.
# 2. Copies this tree and the binary to ~/$DELVETALK_REHEARSAL_DIR (default scratch/dt-rehearsal)
#    on HOST and runs rehearsal/rehearse.py there under swarm-build with a 3 GB memory cap,
#    printing the cgroup's peak. The run replays the archive, probes, and replays the journal
#    from snapshots against its straight replay.
# 3. Brings back results.json, programs.log and hostd.stderr, writes rehearsal/out/summary.md
#    (REPORT.md's measured half), and removes the remote directory unless --keep.
# remote.log keeps this tree's commit, whether it is clean, and the binary's SHA-256.
# Fixtures: rehearsal/fixtures/posts.json (rebuilt by rehearsal/fixtures.py from the archive
# listed in rehearsal/fixtures/SOURCES.txt) and rehearsal/fixtures/model-answers.json.
set -eu
KEEP=0 HOST=hbox
for arg in "$@"; do
  case "$arg" in
    --keep) KEEP=1 ;;
    *) HOST=$arg ;;
  esac
done
DIR=${DELVETALK_REHEARSAL_DIR:-scratch/dt-rehearsal}
BIN=${DELVETALK_REHEARSAL_BINARY:-scratch/dt-foundation/.lake/build/bin/delvetalk-obend}
cd "$(dirname "$0")/.."
mkdir -p rehearsal/out
SRC=${DELVETALK_REHEARSAL_SOURCE:-scratch/dt-foundation}
# The digest of spec/'s Lean and C sources, file by file, in path order.
SPECSUM='find spec -type f \( -name "*.lean" -o -name "*.c" -o -name "*.h" \) | LC_ALL=C sort | while read -r f; do printf "%s %s\n" "$f" "$(SUM < "$f" | cut -c1-64)"; done | SUM | cut -c1-16'
if [ "${DELVETALK_REHEARSAL_ANY_BINARY:-0}" != 1 ]; then
  ours=$(sh -c "$(echo "$SPECSUM" | sed 's/SUM/shasum -a 256/g')")
  # A spec file newer than the binary means a sync after the build: stale whatever the digest says.
  theirs=$(ssh "$HOST" "cd ~/$SRC && if [ -n \"\$(find spec -type f -newer ~/$BIN | head -n 1)\" ]; then echo 'newer than the binary'; else $(echo "$SPECSUM" | sed 's/SUM/sha256sum/g'); fi")
  if [ "$ours" != "$theirs" ]; then
    echo "run.sh: the binary's spec/ (~/$SRC on $HOST, $theirs) is not this tree's ($ours): rebuild it there, or set DELVETALK_REHEARSAL_ANY_BINARY=1" >&2
    exit 2
  fi
fi
{ echo "tree $(git rev-parse HEAD)$(git diff --quiet HEAD -- . 2>/dev/null || echo ' (with uncommitted changes)')"; } > rehearsal/out/remote.log
rsync -a --delete --exclude .git --exclude rehearsal/out --exclude .lake --exclude __pycache__ ./ "$HOST:$DIR/"
ssh "$HOST" "export PATH=\$HOME/.local/bin:\$PATH; cd $DIR && cp ~/$BIN ./delvetalk-obend && sha256sum delvetalk-obend && rm -rf rehearsal/out && \
  SWARM_MEM_MAX=3G swarm-build sh -c 'python3 rehearsal/rehearse.py --binary ./delvetalk-obend --out rehearsal/out && \
  echo peak memory \$(cat /sys/fs/cgroup\$(cut -d: -f3 /proc/self/cgroup)/memory.peak) bytes' && du -sh rehearsal/out" \
  | tee -a rehearsal/out/remote.log
rsync -a "$HOST:$DIR/rehearsal/out/results.json" "$HOST:$DIR/rehearsal/out/programs.log" "$HOST:$DIR/rehearsal/out/hostd.stderr" rehearsal/out/
python3 rehearsal/summary.py rehearsal/out/results.json > rehearsal/out/summary.md
[ "$KEEP" = 1 ] || ssh "$HOST" "rm -rf ~/$DIR"
echo rehearsal/out/summary.md
