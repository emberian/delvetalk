#!/usr/bin/env bash
# The merge check for a commit that touches the host (docs/TENURE.md section 1, docs/OVERHAUL.md section 5 step 0):
# the candidate binary against the newest town backup, run by the root before the merge, on hbox, where the backups
# are pulled (/tank/delvetalk-backups). A commit whose binary does not replay the backup is a breaking change; it does
# not merge.
#
#   deploy/carry-check.sh BINARY BACKUP
#
# BACKUP is a delvetalk-<stamp>.tar.gz, or a directory of them (the newest is checked). Exit 0: the backup replays
# under BINARY. Exit 1: it does not, and the reason is printed. The backup is never written.
set -euo pipefail
usage() { echo "usage: $0 BINARY BACKUP" >&2; exit 64; }
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
echo "carry-check: $(basename "$backup") under $binary"

if "$here/verify.sh" --binary "$binary" "$work/old"; then
  echo "carry-check: green: the backup replays"
else
  echo "carry-check: RED: a breaking change; the backup does not replay under this binary" >&2
  exit 1
fi
