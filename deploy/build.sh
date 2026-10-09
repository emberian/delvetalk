#!/usr/bin/env bash
# Build the host image and the transport image for linux/amd64, then print the
# host binary's SHA-256. The same sources on any machine give the same hash:
# compare it with another build, with the header GET /AGENTS.md answers
# (X-DelveTalk-Host-Sha256) and with deploy/smoke.sh --pin.
#
#   deploy/build.sh            # tags delvetalk-host:<sha12> and :current, delvetalk:<sha12> and :current
#
# Writes deploy/out/host.sha256 and deploy/out/delvetalk-obend (the extracted binary).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/deploy/out"
PLATFORM=linux/amd64
mkdir -p "$OUT"
cd "$ROOT"

docker build --platform "$PLATFORM" -f deploy/Dockerfile.host -t delvetalk-host:current .

cid=$(docker create --platform "$PLATFORM" delvetalk-host:current)
trap 'docker rm -f "$cid" >/dev/null' EXIT
docker cp "$cid:/usr/local/bin/delvetalk-obend" "$OUT/delvetalk-obend"
if command -v sha256sum >/dev/null; then hash=(sha256sum); else hash=(shasum -a 256); fi
sha=$("${hash[@]}" "$OUT/delvetalk-obend" | cut -d' ' -f1)
printf '%s\n' "$sha" > "$OUT/host.sha256"
docker tag delvetalk-host:current "delvetalk-host:${sha:0:12}"

docker build --platform "$PLATFORM" -f deploy/Dockerfile.transport \
  --build-arg HOST_IMAGE="delvetalk-host:${sha:0:12}" -t delvetalk:current -t "delvetalk:${sha:0:12}" .

if git -C "$ROOT" rev-parse HEAD >/dev/null 2>&1; then
  dirty=$(git -C "$ROOT" diff --quiet HEAD -- spec lakefile.lean lean-toolchain lake-manifest.json || echo ' (spec has uncommitted changes)')
  echo "source:  $(git -C "$ROOT" rev-parse HEAD)$dirty"
else
  echo "source:  not a git checkout"
fi
echo "images:  delvetalk-host:${sha:0:12} delvetalk:${sha:0:12}"
echo "sha256:  $sha  delvetalk-obend (linux/amd64)"
