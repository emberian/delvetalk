#!/usr/bin/env bash
# Restore a DelveTalk data directory from a backup tarball. Verifies the
# tarball's checksum and every journal in it before touching DATA; moves the
# current DATA aside to DATA.before-<UTC stamp> (never deletes it); refuses
# while any process holds DATA/journal.lock, i.e. while the stack is up.
#
#   deploy/restore.sh (--binary PATH | --image IMAGE) TARBALL DATA
set -euo pipefail
usage() { echo "usage: $0 (--binary PATH | --image IMAGE) TARBALL DATA" >&2; exit 64; }
[[ $# == 4 ]] || usage
mode=$1 host=$2 tarball=$3 data=${4%/}
here="$(cd "$(dirname "$0")" && pwd)"
[[ -f $tarball ]] || { echo "restore: no $tarball" >&2; exit 66; }
if [[ -f $tarball.sha256 ]]; then
  if command -v sha256sum >/dev/null; then sum=(sha256sum -c); else sum=(shasum -a 256 -c); fi
  (cd "$(dirname "$tarball")" && "${sum[@]}" "$(basename "$tarball").sha256")
else
  echo "restore: no $tarball.sha256; restoring unchecked bytes" >&2
fi
if [[ -e $data/journal.lock ]] && command -v flock >/dev/null; then
  exec 9>>"$data/journal.lock"
  flock -n 9 || { echo "restore: $data/journal.lock is held; stop the stack first" >&2; exit 75; }
fi

stage="$data.restore-$$"
mkdir -p "$stage"
tar -xzf "$tarball" -C "$stage"
"$here/verify.sh" "$mode" "$host" "$stage"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
if [[ -e $data ]]; then
  mv "$data" "$data.before-$stamp"
  echo "restore: previous data kept at $data.before-$stamp"
fi
mv "$stage" "$data"
echo "restore: $data now holds $(basename "$tarball")"
