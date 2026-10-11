#!/usr/bin/env bash
# The merge check for a commit that touches the host (docs/TENURE.md section 1, docs/OVERHAUL.md section 5 step 0):
# the candidate binary against the newest town backup, run by the root before the merge, on hbox, where the backups
# are pulled (/tank/delvetalk-backups). The world is never wiped, so a candidate must either replay the backup or carry
# it: a commit whose binary does not replay it is a breaking change, and merges only if it carries it.
#
#   deploy/carry-check.sh [--old-binary PATH | --old-image IMAGE] [--leave [WORLD=]OBJ]... BINARY BACKUP
#
# BACKUP is a delvetalk-<stamp>.tar.gz, or a directory of them (the newest is checked). In a throwaway copy:
#   1. replay every journal under BINARY from its genesis (deploy/verify.sh --full; a snapshot is not trusted here);
#   2. carry the state to BINARY (`python3 -m transport carry`): every object at the state CID the backup's head
#      snapshot holds and rendering for its owner, every old receipt resolving by its slug, a new entry admitted.
# The carry reads each journal's snapshot at its head, which backup.sh writes into every tarball with the binary
# that replayed it (verify.sh --snapshot). A tarball from before that takes --old-binary or --old-image: the binary
# of the backup's own edition writes the snapshot first. --leave is the carry's: an object carried retired.
# Exit 0: green (the backup replays, or it does not and carries: then the deploy carries). Exit 1: red, named.
# The backup is never written.
set -euo pipefail
usage() { echo "usage: $0 [--old-binary PATH | --old-image IMAGE] [--leave [WORLD=]OBJ]... BINARY BACKUP" >&2; exit 64; }
old=() leave=()
while [[ $# -gt 2 ]]; do
  case $1 in
    --old-binary) old=(--binary "$2"); shift 2 ;;
    --old-image) old=(--image "$2"); shift 2 ;;
    --leave) leave+=(--leave "$2"); shift 2 ;;
    *) usage ;;
  esac
done
[[ $# == 2 ]] || usage
binary=$1 backup=$2
here="$(cd "$(dirname "$0")" && pwd)"
[[ -x $binary ]] || { echo "carry-check: $binary is not an executable" >&2; exit 66; }
if [[ -d $backup ]]; then
  backup=$(ls "$backup"/delvetalk-*.tar.gz 2>/dev/null | sort | tail -n 1)
  [[ -n $backup ]] || { echo "carry-check: no delvetalk-*.tar.gz in $2" >&2; exit 66; }
fi
[[ -f $backup ]] || { echo "carry-check: no $backup" >&2; exit 66; }

work=$(mktemp -d "${TMPDIR:-/tmp}/delvetalk-carry-check.XXXXXX")
trap 'rm -rf "$work"' EXIT
mkdir "$work/old"
tar -xzf "$backup" -C "$work/old"
chmod -R u+rwX,a+rwX "$work/old/state"  # an image writes its snapshot as its own user
echo "carry-check: $(basename "$backup") under $binary"
if [[ ${#old[@]} -gt 0 ]]; then
  "$here/verify.sh" --snapshot "${old[@]}" "$work/old" >/dev/null || { echo "carry-check: RED: the backup does not replay under its own binary" >&2; exit 1; }
fi

replays=1
"$here/verify.sh" --full --binary "$binary" "$work/old" >/dev/null 2>"$work/replay.err" || replays=0
# The replay above took no snapshot of its own: what the carry reads is the backup's, from its own binary.
if ! (cd "$here/.." && python3 -m transport carry --from "$work/old/state" --to "$work/new" --obend "$binary" \
        --reason "carry-check of $(basename "$backup")" ${leave[@]+"${leave[@]}"}) >"$work/carry.out" 2>&1; then
  cat "$work/carry.out" >&2
  [[ $replays == 1 ]] || cat "$work/replay.err" >&2
  echo "carry-check: RED: the backup does not carry under this binary" >&2
  exit 1
fi
grep -v '^hob:' "$work/carry.out"
if [[ $replays == 1 ]]; then
  echo "carry-check: green: the backup replays and carries"
else
  sed 's/^/  /' "$work/replay.err"
  echo "carry-check: green, breaking: the backup does not replay under this binary and carries; the deploy carries"
fi
