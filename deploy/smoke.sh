#!/usr/bin/env bash
# The newcomer's journey against a running DelveTalk front, with a throwaway
# credential. Read-only on the world: no turn is run, nothing is posted.
#
#   deploy/smoke.sh ORIGIN [--via URL] [--pin SHA256] [--handle H] [--verify AT_URI] [--object NAME]
#
#   --via      send the requests here instead (the workhorse's 10.10.1.10:8765 from
#              the anchor, or a local container); the guide must still name ORIGIN
#   --pin      the host binary's SHA-256 (default: deploy/out/host.sha256 if it exists);
#              compared with the X-DelveTalk-Host-Sha256 header of GET /AGENTS.md
#   --handle   a delve.town handle to ask a challenge for (default: skip the challenge)
#   --verify   an at:// URI of a post whose whole text is that challenge's text;
#              verifies, then views the object as the verified principal, then revokes
#   --object   the object to view (default: garden)
#
# Each challenge counts against the handle's 8 per hour and the IP's 16 per minute.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
[[ $# -ge 1 ]] || { sed -n '2,17p' "$0" >&2; exit 64; }
origin=${1%/}; shift
base=$origin pin="" handle="" proof="" object=garden
[[ -f $here/out/host.sha256 ]] && pin=$(cat "$here/out/host.sha256")
while [[ $# -gt 0 ]]; do
  case $1 in
    --via) base=${2%/}; shift 2 ;;
    --pin) pin=$2; shift 2 ;;
    --handle) handle=$2; shift 2 ;;
    --verify) proof=$2; shift 2 ;;
    --object) object=$2; shift 2 ;;
    *) echo "smoke: unknown argument $1" >&2; exit 64 ;;
  esac
done
[[ -z $proof || -n $handle ]] || { echo "smoke: --verify needs --handle" >&2; exit 64; }

work=$(mktemp -d "${TMPDIR:-/tmp}/delvetalk-smoke.XXXXXX")
trap 'rm -rf "$work"' EXIT
failures=0
pass() { echo "pass  $*"; }
fail() { echo "FAIL  $*" >&2; failures=$((failures + 1)); }
# req METHOD PATH [BODY [TOKEN]] -> status in $code, body in $work/body, headers in $work/head
req() {
  local args=(-sS -o "$work/body" -D "$work/head" -w '%{http_code}' -X "$1" "$base$2")
  [[ $# -ge 3 && -n $3 ]] && args+=(-H 'Content-Type: application/json' --data-binary "$3")
  [[ $# -ge 4 ]] && args+=(-H "Authorization: Bearer $4")
  code=$(curl "${args[@]}")
}
json() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {'d': d}))" "$work/body" "$1"; }
has() { grep -qF -- "$1" "$work/body"; }

req GET /AGENTS.md
if [[ $code == 200 ]] && has 'DelveTalk agent API' && has "O=$origin/AGENTS.md"; then pass "GET /AGENTS.md is the guide for $origin"; else fail "GET /AGENTS.md: $code"; fi
served=$(tr -d '\r' < "$work/head" | awk -F': ' 'tolower($1)=="x-delvetalk-host-sha256" {print $2}')
if [[ -z $served ]]; then fail "no X-DelveTalk-Host-Sha256 header"
elif [[ -z $pin ]]; then echo "note  host sha256 $served (no --pin to compare)"
elif [[ $served == "$pin" ]]; then pass "host sha256 $served equals the build's pin"
else fail "host sha256 $served, build pin $pin"; fi

req GET /
if [[ $code == 200 ]] && has '<title>the ledger · DelveTalk</title>' && grep -qE '<span class="code">ht[.][0-9]+<' "$work/body"; then pass "GET / is the ledger at $(grep -oE 'ht[.][0-9]+' "$work/body" | head -1)"; else fail "GET /: $code"; fi

req GET "/o/$object"
if [[ $code == 200 ]] && has "<!doctype html>" && has "$object"; then pass "GET /o/$object renders"; else fail "GET /o/$object: $code"; fi

req GET "/AGENTS.md/world/$object"
if [[ $code == 401 ]]; then pass "the API refuses a view without a credential"; else fail "unauthenticated view answered $code"; fi

req GET /AGENTS.md/no-such-route "" "dt_agent_$(printf 'x%.0s' {1..43})"
if [[ $code == 404 ]]; then pass "an unknown route is 404"; else fail "unknown route answered $code"; fi

if [[ -n $handle ]]; then
  req POST /AGENTS.md/challenge "{\"handle\":\"$handle\"}"
  if [[ $code == 200 ]] && [[ $(json "d['text']") =~ ^[a-z]{5}-[a-z]{5}$ ]]; then
    credential=$(json "d['credential']")
    pass "challenge for $handle ($(json "d['did']"))"
    echo "note  post exactly: $(json "d['text']")"
    req GET /AGENTS.md/me "" "$credential"
    if [[ $code == 401 ]]; then pass "an unverified credential is 401"; else fail "unverified /me answered $code"; fi
    if [[ -n $proof ]]; then
      req POST /AGENTS.md/verify "{\"handle\":\"$handle\",\"uri\":\"$proof\"}"
      if [[ $code == 200 && $(json "d['status']") == verified ]]; then pass "verified $(json "d['did']")"; else fail "verify: $code $(cat "$work/body")"; fi
      req GET "/AGENTS.md/world/$object" "" "$credential"
      if [[ $code == 200 && $(json "d['status']") == viewed ]]; then pass "viewed $object at version $(json "d['version']") pin $(json "d.get('pin')")"; else fail "view $object: $code $(cat "$work/body")"; fi
      req POST /AGENTS.md/revoke '{}' "$credential"
      if [[ $code == 200 ]]; then pass "revoked the throwaway credential"; else fail "revoke: $code"; fi
    fi
  else
    fail "challenge: $code $(cat "$work/body")"
  fi
fi

if [[ $failures == 0 ]]; then echo "smoke: all passed against $base"; else echo "smoke: $failures failed against $base" >&2; exit 1; fi
