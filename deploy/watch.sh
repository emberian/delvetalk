#!/usr/bin/env bash
# The five-minute watch (docs/OPERATIONS.md section b; docs/DEPLOY.md "Watching"), run by
# deploy/delvetalk-watch.timer from /opt/delvetalk: the compose services not running or unhealthy,
# then one probe (transport.hand status --json) and deploy.watch's thresholds, in the ops container.
# .env names the bot's rc: DELVETALK_WATCH_ZULIPRC (mode 0400, owner 10425).
set -euo pipefail
cd "${DELVETALK_HOME:-/opt/delvetalk}"
set -a; . ./.env; set +a
rc=${DELVETALK_WATCH_ZULIPRC:?set DELVETALK_WATCH_ZULIPRC in .env}
backups=${DELVETALK_BACKUPS:-/var/backups/delvetalk}
# The town's daemons: anything not running, or running and unhealthy.
mapfile -t unhealthy < <(docker compose ps -a --format '{{.Service}} {{.State}} {{.Health}}' \
  | awk '$1 != "delvetalk-ops" && ($2 != "running" || $3 == "unhealthy") {print $1}')
docker compose --profile ops run --rm -T -v "$backups:/backups:ro" -v "$rc:/run/watch/zuliprc:ro" -e DELVETALK_BACKUPS=/backups \
  delvetalk-ops sh -c 'python3 -m transport.hand status --json --state /data/state > /data/state/probe.json &&
    exec python3 -m deploy.watch --state /data/state --probe /data/state/probe.json --zuliprc /run/watch/zuliprc --unhealthy "$@"' \
  watch "${unhealthy[@]}"
