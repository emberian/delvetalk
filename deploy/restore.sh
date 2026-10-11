#!/usr/bin/env bash
# Restore a DelveTalk data directory from a backup tarball. Verifies the
# tarball's checksum and every journal in it before touching DATA; moves the
# current DATA aside to DATA.before-<UTC stamp> (never deletes it); refuses
# while any process holds DATA/state/journal.lock, i.e. while serve is up.
# Run as root: the restored tree is given to uid 10425 (compose's `user:`), whoever ran the restore; a tree
# owned by anyone else stops serve at "permission denied, file: /data/state".
#
#   sudo deploy/restore.sh (--binary PATH | --image IMAGE) TARBALL DATA
set -euo pipefail
usage() { echo "usage: $0 (--binary PATH | --image IMAGE) TARBALL DATA" >&2; exit 64; }
[[ $# == 4 ]] || usage
mode=$1 host=$2 tarball=$3 data=${4%/}
here="$(cd "$(dirname "$0")" && pwd)"
[[ -f $tarball ]] || { echo "restore: no $tarball" >&2; exit 66; }
[[ $(id -u) == 0 ]] || { echo "restore: run as root, so the restored files belong to uid 10425, the stack's" >&2; exit 77; }
if [[ -f $tarball.sha256 ]]; then
  if command -v sha256sum >/dev/null; then sum=(sha256sum -c); else sum=(shasum -a 256 -c); fi
  (cd "$(dirname "$tarball")" && "${sum[@]}" "$(basename "$tarball").sha256")
else
  echo "restore: no $tarball.sha256; restoring unchecked bytes" >&2
fi
if [[ -e $data/state/journal.lock ]] && command -v flock >/dev/null; then
  exec 9>>"$data/state/journal.lock"
  flock -n 9 || { echo "restore: $data/state/journal.lock is held; stop the stack first" >&2; exit 75; }
fi

stage="$data.restore-$$"
mkdir -p "$stage"
tar -xzf "$tarball" -C "$stage"
"$here/verify.sh" "$mode" "$host" "$stage"
chown -R 10425:10425 "$stage"
chmod 0700 "$stage"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
if [[ -e $data ]]; then
  mv "$data" "$data.before-$stamp"
  echo "restore: previous data kept at $data.before-$stamp"
fi
mv "$stage" "$data"
echo "restore: $data now holds $(basename "$tarball")"
