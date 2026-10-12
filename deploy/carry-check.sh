#!/usr/bin/env bash
# The merge check for a commit that touches the host (docs/FOUNDATION.md §2, docs/OVERHAUL.md section 5 step 0):
# the candidate binary against the newest town backup, run by the root before the merge, on hbox, where the backups
# are pulled (/tank/delvetalk-backups). The world is never wiped, so a candidate must either replay the backup or carry
# it: a commit whose binary does not replay it is a breaking change, and merges only if it carries it.
#
#   deploy/carry-check.sh [--old-binary PATH | --old-image IMAGE] [--library LIB] [--leave [WORLD=]OBJ]... BINARY BACKUP
#
# BACKUP is a delvetalk-<stamp>.tar.gz, or a directory of them (the newest is checked). In a throwaway copy:
#   1. replay every journal under BINARY from its genesis (deploy/verify.sh --full; a snapshot is not trusted here),
#      and compare LIB (default this tree's world/lib, what the candidate image seals) with the library each journal
#      sealed, as serve does at its start: a replay under another library is not a restart in place;
#   2. carry the state to BINARY (`python3 -m transport carry`): every object at the state CID the backup's head
#      snapshot holds and rendering for its owner, every old receipt resolving by its slug, a new entry admitted.
# The carry reads each journal's snapshot at its head, which backup.sh writes into every tarball with the binary
# that replayed it (verify.sh --snapshot). A tarball from before that takes --old-binary or --old-image: the binary
# of the backup's own edition writes the snapshot first. --leave is the carry's: an object carried retired.
# Exit 0: green (the backup replays under LIB and the image moves no object; or the image moves some, "green, moving:
# the deploy must carry"; or it does not replay and carries: "green, breaking: the deploy must carry").
# Exit 1: red, named.
# The backup is never written.
set -euo pipefail
usage() { echo "usage: $0 [--old-binary PATH | --old-image IMAGE] [--library LIB] [--leave [WORLD=]OBJ]... BINARY BACKUP" >&2; exit 64; }
here="$(cd "$(dirname "$0")" && pwd)"
old=() leave=() library=$here/../world/lib
while [[ $# -gt 2 ]]; do
  case $1 in
    --old-binary) old=(--binary "$2"); shift 2 ;;
    --old-image) old=(--image "$2"); shift 2 ;;
    --library) library=$2; shift 2 ;;
    --leave) leave+=(--leave "$2"); shift 2 ;;
    *) usage ;;
  esac
done
[[ $# == 2 ]] || usage
binary=$1 backup=$2
library=$(cd "$library" && pwd)
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
"$here/verify.sh" --full --library "$library" --binary "$binary" "$work/old" >/dev/null 2>"$work/replay.err" || replays=0
# A journal that replays but sealed another library opens in serve only after a carry (Session.lean: "the bytes differ").
sealed=$(grep -o 'library at [^"]*the bytes differ' "$work/replay.err" | head -n 1 || true)
unreplayed=$(grep '^BROKEN' "$work/replay.err" | grep -vc 'the bytes differ' || true)  # journals that broke for another reason
# The replay above took no snapshot of its own: what the carry reads is the backup's, from its own binary.
if ! (cd "$here/.." && DELVETALK_LIBRARY=$library python3 -m transport carry --from "$work/old/state" --to "$work/new" --obend "$binary" \
        --reason "carry-check of $(basename "$backup")" ${leave[@]+"${leave[@]}"}) >"$work/carry.out" 2>&1; then
  cat "$work/carry.out" >&2
  [[ $replays == 1 ]] || cat "$work/replay.err" >&2
  echo "carry-check: RED: the backup does not carry under this binary" >&2
  exit 1
fi
grep -v '^hob:' "$work/carry.out"
# The objects the image's packages and bodies move (each world line's `moved`): a restart in place keeps each at the code
# its journal sealed, so only a carry brings them the image's.
moving=$(python3 -c '
import json, sys
ids = [m["object"] for line in sys.stdin if line.startswith("{") for j in [json.loads(line)] if "check" in j for m in j.get("moved", [])]
print("%d objects (%s%s)" % (len(ids), ", ".join(ids[:8]), ", ..." if len(ids) > 8 else "") if ids else "")' <"$work/carry.out")
if [[ $replays == 1 && -z $moving ]]; then
  echo "carry-check: green: the backup replays under this binary and its library, and carries"
elif [[ $replays == 1 ]]; then
  echo "carry-check: green, moving: the deploy must carry: the backup replays under this binary and its library, but the image moves $moving, which a restart in place keeps at the code they had; it carries"
elif [[ -n $sealed && $unreplayed == 0 ]]; then
  echo "carry-check: green, breaking: the deploy must carry: the backup replays under this binary, but $sealed, so serve refuses it at start; it carries"
else
  sed 's/^/  /' "$work/replay.err"
  echo "carry-check: green, breaking: the deploy must carry: the backup does not replay under this binary; it carries"
fi
