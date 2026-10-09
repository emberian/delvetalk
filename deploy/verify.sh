#!/usr/bin/env bash
# Replay every journal under a DelveTalk data directory in a throwaway host
# process and exit non-zero unless each one opens. The journals are copied first:
# world-open opens its file for appending, and the copy is the one at risk.
#
#   deploy/verify.sh --binary PATH DIR       a host binary on this machine
#   deploy/verify.sh --image IMAGE DIR       the host image, with no network
#
# DIR holds world.journal and state/heaps/*.journal (the compose volume layout).
set -euo pipefail
usage() { echo "usage: $0 (--binary PATH | --image IMAGE) DIR" >&2; exit 64; }
[[ $# == 3 ]] || usage
mode=$1 host=$2 dir=$3
[[ $mode == --binary || $mode == --image ]] || usage
[[ -f $dir/world.journal ]] || { echo "verify: no $dir/world.journal" >&2; exit 66; }

work=$(mktemp -d "${TMPDIR:-/tmp}/delvetalk-verify.XXXXXX")
trap 'rm -rf "$work"' EXIT
journals=("$dir/world.journal")
shopt -s nullglob
journals+=("$dir"/state/heaps/*.journal)
requests=""
i=0
for j in "${journals[@]}"; do
  cp "$j" "$work/$i.journal"
  chmod a+rw "$work/$i.journal"
  i=$((i + 1))
done
chmod a+rwx "$work"
if [[ $mode == --image ]]; then
  inside=/verify
  run=(docker run --rm -i --network none -v "$work:/verify" "$host")
else
  inside=$work
  run=("$host")
fi
for ((k = 0; k < i; k++)); do
  requests+="{\"op\":\"world-open\",\"path\":\"$inside/$k.journal\"}"$'\n'
done
replies=$(printf '%s' "$requests" | "${run[@]}")

status=0
k=0
while IFS= read -r reply; do
  name=${journals[$k]#"$dir"/}
  case $reply in
    *'"status":"opened"'*) echo "ok      $name $reply" ;;
    *) echo "BROKEN  $name $reply" >&2; status=1 ;;
  esac
  k=$((k + 1))
done <<< "$replies"
[[ $k == "$i" ]] || { echo "verify: host answered $k of $i journals" >&2; exit 1; }
exit $status
