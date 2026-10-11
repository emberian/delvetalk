#!/usr/bin/env bash
# Replay every journal under a DelveTalk data directory in a throwaway host
# process and exit non-zero unless each one opens. The journals are copied first:
# world-open opens its file for appending, and the copy is the one at risk.
#
#   deploy/verify.sh [--full] [--snapshot] --binary PATH DIR       a host binary on this machine
#   deploy/verify.sh [--full] [--snapshot] --image IMAGE DIR       the host image, with no network
#
# DIR holds state/<world>.journal (town.journal at least), serve's layout in the compose volume. <state>/scratch/ holds scratch worlds, which are not custody: not backed up, not verified.
# An open resumes from the newest snapshot that passes its checks; with --full every journal is replayed from its
# genesis and every snapshot compared with the replayed world (`world-open {verify: true}`): the merge check's replay.
# With --snapshot each replayed world's snapshot at its head is written beside its journal in DIR: what a carry to
# another binary reads (`delvetalk-obend carry`, docs/TENURE.md section 1), written by the binary that replays it.
set -euo pipefail
usage() { echo "usage: $0 [--full] [--snapshot] (--binary PATH | --image IMAGE) DIR" >&2; exit 64; }
snapshot=0 full=
while [[ ${1:-} == --full || ${1:-} == --snapshot ]]; do
  [[ $1 == --full ]] && full=',"verify":true' || snapshot=1
  shift
done
[[ $# == 3 ]] || usage
mode=$1 host=$2 dir=$3
[[ $mode == --binary || $mode == --image ]] || usage
[[ -f $dir/state/town.journal ]] || { echo "verify: no $dir/state/town.journal" >&2; exit 66; }

work=$(mktemp -d "${TMPDIR:-/tmp}/delvetalk-verify.XXXXXX")
trap 'rm -rf "$work"' EXIT
shopt -s nullglob
journals=("$dir"/state/*.journal)
requests=""
i=0
for j in "${journals[@]}"; do
  cp "$j" "$work/$i.journal"
  cp "$j.blocks" "$work/$i.journal.blocks"  # the block store the chain's links point into
  chmod a+rw "$work/$i.journal" "$work/$i.journal.blocks"
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
  requests+="{\"op\":\"world-open\",\"path\":\"$inside/$k.journal\"$full}"$'\n'
  # A snapshot of the world the open replayed (of the last world opened: one session at a time).
  [[ $snapshot == 1 ]] && requests+='{"op":"world-snapshot"}'$'\n'
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
  if [[ $snapshot == 1 ]]; then
    IFS= read -r taken
    height=$(sed -n 's/.*"height":\([0-9]*\).*/\1/p' <<< "$taken")
    if [[ $taken == *'"status":"snapshot"'* && -n $height && -f $work/$k.journal.snapshot.$height.cbor ]]; then
      cp "$work/$k.journal.snapshot.$height.cbor" "${journals[$k]}.snapshot.$height.cbor"
      echo "snapshot $name at $height"
    elif [[ $reply == *'"status":"opened"'* ]]; then
      echo "NO SNAPSHOT $name $taken" >&2; status=1
    fi
  fi
  k=$((k + 1))
done <<< "$replies"
[[ $k == "$i" ]] || { echo "verify: host answered $k of $i journals" >&2; exit 1; }
exit $status
