#!/bin/sh
# The offline rehearsal, run on a remote box (default hbox) with no network:
#   rehearsal/run.sh [--keep] [HOST]
# Copies this tree and the built host binary to ~/scratch/dt-rehearsal on HOST, runs
# rehearsal/rehearse.py there, brings rehearsal/out/results.json back, writes
# rehearsal/out/summary.md, and removes the remote directory unless --keep.
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
DIR=scratch/dt-rehearsal
BIN=${DELVETALK_REHEARSAL_BINARY:-scratch/dt-foundation/.lake/build/bin/delvetalk-obend}
cd "$(dirname "$0")/.."
mkdir -p rehearsal/out
rsync -a --delete --exclude .git --exclude rehearsal/out --exclude .lake --exclude __pycache__ ./ "$HOST:$DIR/"
ssh "$HOST" "cd $DIR && cp ~/$BIN ./delvetalk-obend && sha256sum delvetalk-obend && rm -rf rehearsal/out && \
  python3 rehearsal/rehearse.py --binary ./delvetalk-obend --out rehearsal/out && du -sh rehearsal/out" \
  | tee rehearsal/out/remote.log
rsync -a "$HOST:$DIR/rehearsal/out/results.json" "$HOST:$DIR/rehearsal/out/programs.log" "$HOST:$DIR/rehearsal/out/hostd.stderr" rehearsal/out/
python3 rehearsal/summary.py rehearsal/out/results.json > rehearsal/out/summary.md
[ "$KEEP" = 1 ] || ssh "$HOST" "rm -rf ~/$DIR"
echo rehearsal/out/summary.md
