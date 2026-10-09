#!/bin/sh
# Run a command that opens the world journal, holding the journal's writer lock.
#
# Each transport program spawns its own host process, and each host keeps the
# world in memory and appends to the journal file. Two of them on one journal
# write two different entries at the same height and the chain is broken
# ("journal broken at height N: height out of sequence"; reproduced in
# docs/DEPLOY.md). Until the host refuses a second opener itself, this lock is
# what keeps the second writer from starting. It fails closed: exit 75, no wait.
#
#   one-writer python3 -m transport.http ...      (lock held for the process)
#   ONE_WRITER=skip one-writer python3 -m transport.bridge outbox ...   (no journal)
set -eu
LOCK=${DELVETALK_LOCK:-/data/journal.lock}
if [ "${ONE_WRITER:-}" = skip ]; then exec "$@"; fi
exec 9>>"$LOCK"
if ! flock -n 9; then
  echo "one-writer: $LOCK is held: another process owns the journal; refusing to start a second writer" >&2
  exit 75
fi
# A filesystem that accepts flock and enforces nothing would make this lock a
# fiction; probe with a second open of the same file and go on only if it is
# refused. The probe cannot see a lock enforced per mount but not across
# containers, which is what Docker Desktop's file sharing on a Mac does
# (measured): there the guard does not hold. On the workhorse the data
# directory is a local Linux filesystem and one kernel enforces the lock for
# every container (measured on ext4).
if flock -n "$LOCK" true; then
  echo "one-writer: the filesystem under $LOCK does not enforce flock; refusing to run unguarded" >&2
  exit 75
fi
exec "$@"
