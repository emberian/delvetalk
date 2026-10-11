#!/usr/bin/env bash
# Pull the workhorse's verified backup tarballs to this machine, keep them 7/56/forever, and replay the newest
# (docs/OPERATIONS.md section b; docs/DEPLOY.md "Durability and backups"). Run on the owner's machine, hourly.
#
#   deploy/pull-backups.sh [--from HOST] [--key KEY] [--keep-only] (--binary PATH | --image IMAGE) DEST
#
# A pull, not a push: KEY is a key the workhorse accepts only for a read-only rsync of /var/backups/delvetalk
# (authorized_keys: `restrict,command="rrsync -ro /var/backups/delvetalk" ssh-ed25519 ...`), and the workhorse
# holds no credential to DEST, so a box that is taken cannot reach its own backups.
# Retention in DEST: every tarball 7 days; the first of each UTC day 56 days; the first of each UTC month always.
# The newest tarball is then untarred into a throwaway directory and replayed by verify.sh; exit 1 if it is broken.
# --keep-only applies the retention to DEST and stops (no network, no replay).
set -euo pipefail
usage() { echo "usage: $0 [--from HOST] [--key KEY] [--keep-only] (--binary PATH | --image IMAGE) DEST" >&2; exit 64; }
from=root@workhorse key=$HOME/.ssh/delvetalk-backups keep_only=0 mode= host=
while [[ $# -gt 1 ]]; do
  case $1 in
    --from) from=$2; shift 2 ;;
    --key) key=$2; shift 2 ;;
    --keep-only) keep_only=1; shift ;;
    --binary|--image) mode=$1 host=$2; shift 2 ;;
    *) usage ;;
  esac
done
[[ $# == 1 ]] || usage
dest=${1%/}
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$dest"
chmod 700 "$dest"

if [[ $keep_only == 0 ]]; then
  [[ -n $mode ]] || usage
  # rrsync roots the remote path at the backup directory: "HOST:" is /var/backups/delvetalk.
  rsync -a --ignore-existing --include 'delvetalk-*.tar.gz' --include 'delvetalk-*.tar.gz.sha256' --exclude '*' \
    -e "ssh -i $key -o IdentitiesOnly=yes -o BatchMode=yes" "$from:" "$dest/"
  if command -v sha256sum >/dev/null; then sum=(sha256sum -c --quiet); else sum=(shasum -a 256 -c --quiet); fi
  (cd "$dest" && for s in delvetalk-*.tar.gz.sha256; do [[ -e $s ]] && "${sum[@]}" "$s"; done)
fi

# Retention: stamps are delvetalk-YYYYMMDDTHHMMSSZ.tar.gz; the first of a day or month is the earliest stamp in it.
python3 - "$dest" ${DELVETALK_NOW:+"$DELVETALK_NOW"} <<'PY'  # DELVETALK_NOW: the clock retention reads (ISO, UTC), for a test
import datetime, pathlib, sys
dest = pathlib.Path(sys.argv[1])
now = datetime.datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.datetime.now(datetime.timezone.utc)
tars = sorted(dest.glob('delvetalk-*.tar.gz'))
stamp = lambda p: datetime.datetime.strptime(p.name[10:26], '%Y%m%dT%H%M%SZ').replace(tzinfo=datetime.timezone.utc)
first_of = lambda fmt: {min((t for t in tars if stamp(t).strftime(fmt) == k), key=stamp) for k in {stamp(t).strftime(fmt) for t in tars}}
days, months = first_of('%Y%m%d'), first_of('%Y%m')
for t in tars:
    age = now - stamp(t)
    if age <= datetime.timedelta(days=7) or (t in days and age <= datetime.timedelta(days=56)) or t in months:
        continue
    for p in (t, t.with_name(t.name + '.sha256')):
        p.unlink(missing_ok=True)
    print(f'pull-backups: dropped {t.name} ({age.days} days)')
PY
[[ $keep_only == 1 ]] && exit 0

newest=$(ls "$dest"/delvetalk-*.tar.gz 2>/dev/null | sort | tail -n 1)
[[ -n $newest ]] || { echo "pull-backups: no tarball in $dest" >&2; exit 66; }
work=$(mktemp -d "${TMPDIR:-/tmp}/delvetalk-pulled.XXXXXX")
trap 'rm -rf "$work"' EXIT
tar -xzf "$newest" -C "$work"
"$here/verify.sh" "$mode" "$host" "$work"
echo "pull-backups: $(basename "$newest") replays"
