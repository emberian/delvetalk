#!/usr/bin/env bash
# Snapshot the DelveTalk data directory: rsync into DEST/mirror, cut a torn
# final line if a write was in flight, copy SQLite files through SQLite's own
# backup, verify every journal by replay (deploy/verify.sh), then write
# DEST/delvetalk-<UTC stamp>.tar.gz. Exit non-zero if any journal is broken;
# a broken snapshot is kept in DEST/mirror for inspection but never tarred.
#
#   deploy/backup.sh (--binary PATH | --image IMAGE) DATA DEST
#
# The stack may keep running: the journal is append-only, so a prefix ending
# at a newline is a chain the host has written. Each run is one prefix.
set -euo pipefail
usage() { echo "usage: $0 (--binary PATH | --image IMAGE) DATA DEST" >&2; exit 64; }
[[ $# == 4 ]] || usage
mode=$1 host=$2 data=${3%/} dest=${4%/}
here="$(cd "$(dirname "$0")" && pwd)"
[[ -f $data/world.journal ]] || { echo "backup: no $data/world.journal" >&2; exit 66; }
mkdir -p "$dest/mirror"
chmod 700 "$dest"

rsync -a --delete --exclude journal.lock --exclude '*.pid' --exclude '*.tmp' --exclude host.sock --exclude /state/library "$data/" "$dest/mirror/"

# A torn tail: the host was mid-append when rsync read the file.
shopt -s nullglob
for j in "$dest/mirror/world.journal" "$dest"/mirror/state/heaps/*.journal; do
  if [[ -s $j && $(tail -c 1 "$j" | od -An -c | tr -d ' ') != '\n' ]]; then
    keep=$(( $(wc -c < "$j") - $(tail -n 1 "$j" | wc -c) ))
    echo "backup: ${j#"$dest"/mirror/}: cut a torn final line at byte $keep" >&2
    python3 - "$j" "$keep" <<'PY'
import os, sys
with open(sys.argv[1], 'r+b') as f:
    f.truncate(int(sys.argv[2]))
PY
  fi
done

# SQLite files copied while open may be mid-transaction; take SQLite's backup instead.
for db in "$data"/state/*.sqlite; do
  python3 - "$db" "$dest/mirror/state/${db##*/}" <<'PY'
import sqlite3, sys
src = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True)
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()
src.close()
PY
done

"$here/verify.sh" "$mode" "$host" "$dest/mirror"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
tar -czf "$dest/delvetalk-$stamp.tar.gz.part" -C "$dest/mirror" .
mv "$dest/delvetalk-$stamp.tar.gz.part" "$dest/delvetalk-$stamp.tar.gz"
if command -v sha256sum >/dev/null; then sum=(sha256sum); else sum=(shasum -a 256); fi
(cd "$dest" && "${sum[@]}" "delvetalk-$stamp.tar.gz" > "delvetalk-$stamp.tar.gz.sha256")
echo "backup: $dest/delvetalk-$stamp.tar.gz $(cut -d' ' -f1 "$dest/delvetalk-$stamp.tar.gz.sha256")"
