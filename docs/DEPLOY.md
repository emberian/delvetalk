# Deploying DelveTalk

The operator's book: what runs where now, and the procedure for each act on it. Everything in `deploy/` is an
artifact the owner runs; nothing here deploys itself. docs/OPERATIONS.md is the transport's shape, its state layout,
the watch's thresholds and the operator's loop.

## What runs where

Two towns run side by side on the workhorse, each a compose project of its own ("A second instance"), behind native
Caddy on the anchor. hbox pulls their backups.

| | gsb (`delvetalk`) | obend (`open`) |
| --- | --- | --- |
| origin | `https://gsb.fg-goose.online` | `https://obend.fg-goose.online` |
| opener | ember's DID, `did:plc:6amo7col5h4ciq2gpm5eur7b` | its did:web |
| arrival | invited (the default) | open: a key for the asking (`arrival = "open"`) |
| bridge | delve.town (posting by hand) | its own feed (`transport open --transport feed`) |
| data directory | `/var/lib/delvetalk/v20` | `/var/lib/delvetalk-open/v5` |
| `/opt/<project>`, `/etc/<project>` | `delvetalk` | `delvetalk-open` |
| front, hand, firehose ports | 8765, 8766, 8767 | 8775, 8776, 8777 |

- **Binary:** `delvetalk-obend` SHA-256 `ca9e5b645192623811a0c94d2507d6723fbd1b5dea6a7aa09f0ff2c2be5c969e`, replay edition
  20, images `delvetalk:ca9e5b645192` and `delvetalk-host:ca9e5b645192` (transport image `99dd7920…f359` by the
  whole-image hash, "Build and ship"), built from foundation 37640349 and restarted in place over `e9ea2c8d73e9` on
  2026-10-15 (carry-check plain green on both towns' newest backups). Both towns serve it; both `pull.env` on hbox
  name `delvetalk-host:ca9e5b645192`. The files each roll replaced are in `/opt/<project>/before-<new sha12>/`.
- **The site** (`site/`) is GitHub Pages (`https://emberian.github.io/delvetalk/`), published by
  `.github/workflows/pages.yml` on a push to the `pages` branch or a manual dispatch; no roll touches it. The towns'
  own `/` and `/town` are the front's.
- **Older data directories** stay on disk, unserved and read-only: gsb's `v2` to `v19` (`v8`, 2026-10-12, is the
  owner's fresh minimal town; `v9` to `v20` are carries, each citing the one before; `v2` to `v7` are earlier geneses;
  `v10.failed-*` and `v14.failed-*` are refused carries), obend's `v1` to `v4`. Receipts of every carried directory
  from `v8` on resolve by slug (`hand search`). Each closing backup is in hbox's `/tank/delvetalk-backups/closing/` and
  `/tank/delvetalk-open-backups/closing/`.
- **Machines.** The workhorse (`dregg-workhorse`, public 2.28.141.27, private 10.10.1.10): 4 cores, 7.6 GB, no swap,
  ext4. The anchor (public 88.99.126.35, private 10.10.1.5): Caddy, `/etc/caddy/Caddyfile`, source dregg-infra's
  `edge/anchor/Caddyfile`. hbox: builds, carry-checks, the backup pull (`/tank`), holding the workhorse's root key
  (`~/.ssh/id_portable`, the `dregg-workhorse` entry of its `~/.ssh/config`).
- **Services per stack** (`deploy/compose.yml`, `deploy/compose.hand.yml`): `delvetalk-host` (`delvetalk-obend
  serve`), `delvetalk-http`, `delvetalk-bridge`, `delvetalk-interpret` (profile `town`), `delvetalk-hand`,
  `delvetalk-automod`, and `delvetalk-ops` for one-off commands. Memory limits: host 2g, front, bridge, interpret
  and hand 256m each, automod 128m: 3,200 MiB a stack, 6,400 MiB for two. Each host runs at about 550 MiB, every other
  service under 100 MiB.
- **Timers on the workhorse:** delvetalk-backup (:17 every six hours), delvetalk-open-backup (:27),
  `delvetalk-watch.timer` and `delvetalk-open-watch.timer` (every five minutes). On hbox, user timers
  delvetalk-pull-backups (:47) and delvetalk-open-pull-backups (:57).
- **Logs.** The host, front, hand and automod write one line to their container logs per start and per error, never a
  text, a key or a body: the host `host: started pid= worlds= replay= binary=`, `host: error op=<op> ms=` for each
  refused request, `host: slow op=<op> ms=` past 2 s, `host: stopped`; the front `front: started` and, for a 500,
  `front: 500 <method> <path> <exception class> <file>:<line>`; the hand `hand: started`; automod one line per batch
  (`texts= status= seconds=`) and `automod: error <kind>` once until it changes. The front's access log is its own
  section below.

| File | What |
| --- | --- |
| `deploy/Dockerfile.host` | the host binary for linux/amd64; final image is the binary and glibc |
| `deploy/Dockerfile.transport` | python 3.13 slim + the binary + `transport/`, `world/`, `deploy/`, `capsules/pages/` and the docs the guide and genesis read |
| `deploy/build.sh` | builds both, prints the binary's SHA-256, writes `deploy/out/host.sha256` |
| `deploy/compose.yml` | `delvetalk-host`, `delvetalk-http`, `delvetalk-bridge`; `delvetalk-interpret` (profile `town`); `delvetalk-ops` |
| `deploy/compose.hand.yml` | laid over compose.yml: `delvetalk-hand` and `delvetalk-automod` |
| `deploy/compose.firehose.yml` | laid over compose.yml when an instance publishes its firehose ("Firehose") |
| `deploy/instances.toml`, `deploy/instance.py` | each instance on the box, and its kit rendered from its name ("A second instance") |
| `deploy/seed.py` | `world-create` of one object from `world/` |
| `deploy/backup.sh`, `restore.sh`, `verify.sh`, `pull-backups.sh` | journal custody |
| `deploy/carry-check.sh` | the gate before a merge that touches the host |
| `deploy/smoke.sh` | the newcomer's journey against an origin |

The world's opener is the town's own principal (docs/GENESIS.md "The town"): config `opener`, by default the origin's
did:web, which `transport serve` hands to serve's `--opener`. gsb's journal names ember's DID as its opener, so its
`.env` keeps `DELVETALK_OPENER` set to that DID (serve refuses settings that differ from the journal's); the host shows
it as the town all the same. Only the opener may create objects with a named owner at genesis, change the library, and
make the newcomers' objects that `world-arrive` creates. The opener speaks on the root socket only: an op naming the
opener on the public socket is refused, "the opener speaks on the root socket", so the opener's authority is a mount,
not a token (docs/ROOT.md section 1.4).

## One writer

Two host processes on one journal write two entries at the same height and break the chain ("journal broken at height
N: height out of sequence"). So exactly one process, `delvetalk-host` (`delvetalk-obend serve`), opens the journals:

- It holds `/data/state/journal.lock` for its life (exit 75, "refusing to start a second writer", if taken).
- It keeps every world's journal in `/data/state`: `town.journal`; another world's `<name>.journal`, opened at the
  first op that names it with `world: <name>`; a principal's scratch worlds in `scratch/<principal>/<name>.journal`,
  addressed by `world: scratch/<name>` beside `principal`. Scratch worlds are not custody: backups leave them out and
  verification skips them.
- It serves the front, the bridge, the interpreter and `post --object` over `/data/state/host.sock` (mode 0600). The
  opener's ops, `world-root` and the root ops (`world-library`, `world-settings`, `world-fork`, `world-snapshot`) take
  the root socket, `/run/delvetalk-root/root.sock` on the host directory `/var/lib/delvetalk/root` (`DELVETALK_ROOT`),
  mounted into `delvetalk-host`, `delvetalk-ops` and the hand and into nothing else.
- At start it rebuilds `<state>/library` from `--library` (the image's `world/lib`) and `world/objects/Avatar.obend`
  (the package `world-arrive` creates from) and seals it into each world at its first open (the opener may change it;
  a scratch world starts with it sealed), so packages import `./Plan.obend` and the rest by name.
- Every world of the directory is opened at start and held (a held world is its live state, not its journal), so a
  turn in one may read another's objects. The host mounts every data directory read-only at `/towns`, the path a
  carried genesis cites its ancestors by, so it reads the history before its own carry.

The other programs are clients (`transport/host.py`): stop, start or run them at any time without touching the world.
The lock holds where one kernel sees the file: a local Linux filesystem (measured on ext4). Docker Desktop's file
sharing on a Mac does not enforce it across containers (measured), so test the stack there on a named volume.

## Firehose

`transport http` runs `com.atproto.sync.subscribeRepos` on a separate TCP listener in the same `delvetalk-http`
process, with one selector thread for all sockets and production. `firehose_bind` defaults to `127.0.0.1`,
`firehose_port` to `0` (off). Enable it only with the world's signing key in `repo_keys`. The listener is public
through the edge; it requires no subscriber credential. Its durable log is `/data/state/worlds/<world>/events`, kept in
state backups and copied by carry alongside `repo.json` (REPO).

To enable it, an instance whose table says `firehose = true` names `deploy/compose.firehose.yml` in `COMPOSE_FILE`,
its port `DELVETALK_FIREHOSE_PORT` (8767). The overlay for `delvetalk-http` (its inherited HTTP settings, state/key
mounts and HTTP port remain):

```yaml
services:
  delvetalk-http:
    environment:
      DELVETALK_FIREHOSE_BIND: 0.0.0.0
      DELVETALK_FIREHOSE_PORT: "8767"
    ports:
      - "10.10.1.10:8767:8767/tcp"
```

Compose merges the environment mapping and port list. The 0.0.0.0 bind is inside the container; the published port is
on the workhorse's private network, reached by Caddy on the anchor. For a drill, change both the setting and mapping to
the same unused port. Add this route in the site's Caddy block before the general `reverse_proxy 10.10.1.10:8765`:

    reverse_proxy /xrpc/com.atproto.sync.subscribeRepos 10.10.1.10:8767

Caddy forwards the WebSocket upgrade. The HTTP front's same XRPC path answers 426 `UpgradeRequired` with `Upgrade:
websocket` when enabled, or 501 with `firehose_port` named when off. Do not send the WebSocket route to port 8765:
subscribers use 8767 and take no HTTP worker. Stop the front before carry or state restoration so the event log is
quiescent; restart reconciles missed heights with a head-only sync, and a key rotation emits identity before sync. An
unchanged restart adds no event. Neither town enables it now.

## Public request participants

`requests` defaults to `false`; the bridge polls public request records only when the operator enables it (neither
town does). `participants` names explicit participant DIDs, space-separated, in `<state>/delvetalk.toml`
(`DELVETALK_PARTICIPANTS` overrides it); did:plc and hostname-level did:web are supported.

- The registry unions this list with active repositories discovered at pds.delve.town and verified identity-table
  claims, plus hosted accounts in `State.hosted` only when `hosted_accounts = true`. Hosted accounts supply documents
  and proof CARs locally to the ordinary `requests.proven` verifier and do not consume the external-participant cap.
- Each external DID is read at its current document's `#atproto_pds`, through public-address-checked, pinned HTTPS.
  No PDS write is made by the poller. The mirror has its own authorization and remains off.
- Documents cache ten minutes; a proof verification failure refreshes once per participant per poll before refusal.
  Identity changes are observed at the next refresh. The poll reads at most 256 non-delve-PDS participants in sorted
  DID order and reports every overflow DID; unsupported DIDs and unsafe PDS destinations are problems in the bridge
  step's `failed` output.
- `<state>/worlds/<world>/requests.json` holds `{revs: {did: {pds, rev}}, refused: {uri: {cid, why}}}`. The revision
  skip requires both PDS and revision to match; a migrated participant is scanned in full. Consumed URIs and first
  proven CIDs in `observe.sqlite`, refused records in `requests.json` and `answers/` survive migration, and backups
  retain all three.
- Requests must remain in the resident's repository until answered. ATPROTO §2 describes verification and discovery.

## Hosted account origins

The mapping and request repositories are built (ATPROTO §4, REPO), but hosted DIDs are **off** (`hosted_accounts =
false`; `DELVETALK_HOSTED_ACCOUNTS=off` in both `.env`): the owner chose no `*.guest.gsb.fg-goose.online` DNS. While
off the front neither provisions nor serves hosted repositories and the request poller ignores their snapshots. Guests
keep the same credential, identity mapping, feed behavior and `guest:<host>:<name>` principal; invitations need no town
repo key. Revocation and reconciliation remove only canonical snapshots of guests no longer verified; nothing else in a
hosted store is touched.

To enable hosting:

1. Set `hosted_accounts = true` in `<state>/delvetalk.toml`, or `DELVETALK_HOSTED_ACCOUNTS=on` in `.env` (compose
   passes it, default `off`).
2. Wildcard A/AAAA records to the front's edge: `*.guest.gsb.fg-goose.online.`, `*.zulip.gsb.fg-goose.online.`, and
   for each configured Zulip realm its own zone, e.g. `*.chat.example.zulip.gsb.fg-goose.online.`
3. Caddy certificates by DNS-01 in the owner's Google Cloud DNS zone `fg-goose.online`, routing these hosts to the
   existing HTTP upstream with Host preserved. A TLS wildcard covers exactly one label: each realm needs its
   `*.<realm>.zulip.gsb.fg-goose.online` certificate (or explicit account SANs); guests need
   `*.guest.gsb.fg-goose.online`. DNS credentials stay out of Git.
4. `<repo_keys>/town.key` in place (`/etc/delvetalk/repo/town.key`). Without it hosted routes and invitation
   acceptance refuse 503 `RepoNotServed`; the invitation stays open.

Done when HTTPS on each chosen account hostname serves its matching DID document and `sync.getRecord` verifies under
its `#atproto` key. Hosted account hosts route to the world's existing front; the account DID document's PDS endpoint
is the same origin. The front and bridge share `<state>/hosted/<URL-encoded origin>/`.

Custody when enabled: account k256 keys derive with HKDF-SHA256 from the town-key scalar and each hosted DID (ATPROTO
§4). Only public `<state>/hosted/<URL-encoded origin>/<stem>.json` snapshots are written (signing key ids and
rotation/migration epochs; guest stems are names, Zulip stems `<id>.<realm>.zulip`); the 0700 directory carries the
flock. `backup.sh` keeps them. Restoring them with the same `/etc/delvetalk/repo/town.key` and the accepted guests'
`identity.sqlite` reproduces every active guest's hosted key and signed head; loss of the town key loses every hosted
key. On first start with hosting enabled, the front provisions every accepted, unrevoked guest (counter 0, no epoch) and
logs nothing unless it skips one: check the directory listing before the first backup. A legacy store (from before
v14) migrates only with the town key present, before running the current backup script; its old key and lock files
are removed after durable migration.

Not built (ATPROTO §4): a Zulip message written once as a public request and consumed once, and reciprocal link
records/document claims. Existing Zulip messages remain observations under their Zulip principals.

## Costs

The boundary between the Python programs and the host process, measured on hbox with `deploy/bench-boundary.py`
(median per-op round trip, 1,000 `world-status` ops and 200 Counter bumps):

| Path | `world-status` | Counter bump |
| --- | --- | --- |
| (a) serve's socket, a connection per op | 0.092 ms | 0.594 ms |
| (b) serve's socket, one persistent connection | 0.077 ms | 0.606 ms |
| (c) the raw pipe to a host process | 0.039 ms | 0.494 ms |

`HostClient` keeps one connection per thread, so production runs path (b).

## Prerequisites on the workhorse

- Docker with compose v2, as for `/opt/dregg-edge`; `rsync` and `python3` for backups.
- The data directory `DELVETALK_DATA` (gsb `/var/lib/delvetalk/v20`), owner `10425:10425`, mode 0700 (the image's
  uid), with `state/` inside it made the same way. The instance's `.env` must name it. Local
  ext4 or ZFS: see "Durability and backups".
- `/var/lib/delvetalk` itself is the old systemd units' (`delvetalk:delvetalk`, uid 987, mode 0700). The host and ops
  containers mount it read-only at `/towns` as 10425, so 10425 must list it: `setfacl -m u:10425:rx
  /var/lib/delvetalk`. Without it genesis's no-wipe guard cannot see the towns; it refuses a directory it cannot list.
- `/etc/delvetalk/anthropic.key` and `/etc/delvetalk/zai.key`: each key alone, owner 10425, mode 0400, shared by
  both instances.
- `/etc/delvetalk/repo/town.key`: the repository's signing key (docs/REPO.md "The key"), made at first start, owner
  10425, mode 0400, in a directory owner 10425, mode 0700. Never printed, never in a backup tarball.
- The portal is config `origin` (`DELVETALK_ORIGIN` overrides it for every program; `compose.yml` and
  `compose.hand.yml` set it for every service as `${DELVETALK_ORIGIN:?set DELVETALK_ORIGIN in instance .env}`, from `.env`).
- The anchor's Caddy. Install as the Caddyfile's header says: write `Caddyfile.new`, `caddy validate`, `mv`,
  `systemctl reload caddy`; keep dregg-infra's anchor Caddyfile equal to the installed file. Each site
  proxies to the workhorse's private address, serves `/hand` and `/hand/*` behind the anchor's password ("Open the
  hand"), strips a client's own `X-Delvetalk-Hand-Token` on every path, and caps bodies at 262144 bytes (the front's
  own `MAX_BODY` is the same). The old `delvetalk.fg-goose.online` name still proxies to `10.10.1.10:8765` and
  answers `respond @hand 404`. The gsb route as installed (`render delvetalk`'s `Caddyfile.site`; the installed block
  adds two comment lines and a blank line):

      gsb.fg-goose.online {
      	import baseline_headers
      	encode zstd gzip
      	request_header -X-Delvetalk-Hand-Token
      	@hand path /hand /hand/*
      	handle @hand {
      		basic_auth {
      			import /etc/caddy/secrets/delvetalk-hand.users
      		}
      		header Cache-Control "no-store"
      		reverse_proxy 10.10.1.10:8766 {
      			header_up -Authorization
      			header_up X-Delvetalk-Hand-Token {file./etc/caddy/secrets/delvetalk-hand.token}
      			transport http {
      				dial_timeout 3s
      				response_header_timeout 60s
      			}
      		}
      	}
      	request_body {
      		max_size 262144
      	}
      	reverse_proxy 10.10.1.10:8765 {
      		transport http {
      			dial_timeout 3s
      			response_header_timeout 60s
      		}
      	}
      }
- The old systemd units (`delvetalk-proxy.socket`, `delvetalk-proxy.service`, `delvetalk-portal.service`) are
  stopped and disabled and `delvetalk-tick.timer` stays disabled. Their data under `/var/lib/delvetalk/` (`world`,
  `town-v1`, `forge-v1`, `clerk`, `operator-service`) stays where it is.
- Log in with delve.town (`transport/oauth.py`) names the front by `origin`: the client id is
  `<origin>/oauth/client-metadata.json` and the callback `<origin>/oauth/callback`. The account's PDS fetches the
  document itself, so it must answer 200 `application/json` over HTTPS at exactly that URL (no redirect). A login
  started on another name is first sent to the origin's, where its one-time cookie lives. Check after a deploy: `curl
  -s https://gsb.fg-goose.online/oauth/client-metadata.json` shows `client_id` equal to that URL. pds.delve.town is its
  own authorization server (PAR, PKCE S256, DPoP ES256, `client_id_metadata_document_supported`). The image installs
  `cryptography` for ES256 from `deploy/requirements-transport.txt`, pinned by hash.
- **The firewall.** Each front answers the anchor (10.10.1.5) only: `trust_proxy` (set by compose for the front)
  believes the last `X-Forwarded-For` entry from whoever connects. The workhorse has no host firewall (no ufw,
  `nftables.service` disabled) and the Hetzner Cloud firewall filters public interfaces only, so
  `delvetalk-firewall.service` (dregg-infra `edge/delvetalk/delvetalk-firewall`, installed as
  `/usr/local/sbin/delvetalk-firewall`; after docker, `PartOf=docker.service`) owns two chains, looping over every
  instance's ports (`FRONTS="8765 8775"`, `HANDS="8766 8776"`, from deploy/instances.toml):
  - `DELVETALK-FRONT`, jumped to from `DOCKER-USER`: new connections to 10.10.1.10 on every front and hand port
    return when from the anchor and are dropped from any other source.
  - `DELVETALK-LOCAL`, jumped to from `OUTPUT`: a non-root process on the box (the `mini` user's sessions) connecting
    to a front or hand port, on 10.10.1.10, loopback or a container address, is reset.

  Matched on conntrack's original destination, so a recreated container keeps the rule. A new instance's ports join
  both lists. Check: from the anchor `curl -s -o /dev/null -w '%{http_code}' http://10.10.1.10:<port>/AGENTS.md` is
  200; from hbox, the Mac or `nobody` on the box, nothing; root still reaches loopback.

## Build and ship

On hbox (or any machine with Docker; the images are linux/amd64), from the commit's `git archive`:

    deploy/build.sh            # last line: sha256:  <64 hex>  delvetalk-obend (linux/amd64)
    docker save delvetalk:<sha12> delvetalk-host:<sha12> | gzip -1 | ssh dregg-workhorse 'gunzip | docker load'
    scp deploy/compose.yml deploy/compose.hand.yml deploy/watch.sh deploy/delvetalk-watch.service deploy/delvetalk-watch.timer dregg-workhorse:/opt/delvetalk/
    scp deploy/backup.sh deploy/verify.sh deploy/restore.sh dregg-workhorse:/opt/delvetalk/deploy/

The backup scripts run on the host, not in a container, so they are shipped beside compose.yml; `/opt/delvetalk/deploy/`
is the copy the timer runs. Copy from the `git archive` the images were built from, not from a checkout that has moved
since. obend takes the same files into `/opt/delvetalk-open/`.

Two builds of one commit print the same SHA-256; record it with the commit. Everything the build reads is pinned (base
images by digest, Debian packages by snapshot, elan and the Lean tarball by SHA-256). The Lean compile runs inside
dockerd's build, outside a `swarm-build` cgroup around the client; the Dockerfile's own two-slot wrapper bounds it.

Tags name the binary, so two commits with one binary share tags (a transport-only change replaces the image under the
same tag): compare hashes, never the tag. The image id differs between the two daemons' stores; compare the binary:

    docker run --rm --entrypoint sha256sum delvetalk:<sha12> /usr/local/bin/delvetalk-obend    # the host image has no sha256sum

and the whole transport image, the same command on both boxes:

    docker run --rm --network none --entrypoint sh delvetalk:<sha12> -c 'cd / && find app usr/local/bin/delvetalk-obend -type f | sort | xargs sha256sum | sha256sum'

Before each roll, tag the running image by its commit (`delvetalk:<commit12>`) so the old one stays loadable.

## First start

A first town, on a box whose `/var/lib/delvetalk` holds none. A box that already holds a town carries it instead ("A
new binary"). A new instance beside the live one starts from "Bringing up another instance".

**The `.env`** in `/opt/<project>` (mode 0600) is `python3 -m deploy.instance render <name>`'s `env`. gsb's:

    # DelveTalk: /opt/delvetalk/.env (mode 0600), rendered by `python3 -m deploy.instance render delvetalk`
    COMPOSE_PROJECT_NAME=delvetalk
    COMPOSE_FILE=compose.yml:compose.hand.yml
    DELVETALK_IMAGE=delvetalk:<sha12>
    DELVETALK_HOST_IMAGE=delvetalk-host:<sha12>
    DELVETALK_ORIGIN=https://gsb.fg-goose.online
    DELVETALK_OPENER=did:plc:6amo7col5h4ciq2gpm5eur7b
    DELVETALK_DATA=/var/lib/delvetalk/v20
    DELVETALK_ROOT=/var/lib/delvetalk/root
    DELVETALK_TOWNS=/var/lib/delvetalk
    DELVETALK_REPO_KEYS=/etc/delvetalk/repo
    DELVETALK_HAND_TOKEN_PATH=/etc/delvetalk/hand.token
    DELVETALK_DELVE_DIR=/etc/delvetalk/delve
    DELVETALK_ANTHROPIC_KEY_PATH=/etc/delvetalk/anthropic.key
    DELVETALK_ZAI_KEY_PATH=/etc/delvetalk/zai.key
    DELVETALK_PRIVATE_IP=10.10.1.10
    DELVETALK_HTTP_PORT=8765
    DELVETALK_HAND_PORT=8766
    DELVETALK_FIREHOSE_PORT=8767
    DELVETALK_BACKUPS=/var/backups/delvetalk
    DELVETALK_WATCH_ZULIPRC=/etc/delvetalk/watch.zuliprc
    DELVETALK_REQUESTS=off
    DELVETALK_HOSTED_ACCOUNTS=off
    DELVETALK_STATION=on

No comment follows a value: systemd's `EnvironmentFile=`, which the backup unit reads, keeps it as part of the value and
the backup fails `docker: invalid reference format`. `DELVETALK_HOST_IMAGE` is the backup timer's replay image;
`DELVETALK_ORIGIN` the portal and the did:web host; `DELVETALK_OPENER` gsb's journal's opener (a new world omits it:
the origin's did:web); `DELVETALK_STATION=on` the owner's word that a carry's refresh makes the all-night station;
`DELVETALK_WATCH_ZULIPRC` the watch bot's rc (owner 10425, mode 0400; "Watching"). `DELVETALK_REPO_KEYS` is the directory of `<world>.key`. The hand's token is a file, never a line here.

Every path and port has a variable whose default is gsb's; a rehearsal or drill on another box sets them in the same
`.env` (and `COMPOSE_PROJECT_NAME`, which every `docker compose` here then uses): `DELVETALK_DATA`, `DELVETALK_ROOT`,
`DELVETALK_TOWNS`, `DELVETALK_ANTHROPIC_KEY_PATH`, `DELVETALK_ZAI_KEY_PATH`, `DELVETALK_HAND_TOKEN_PATH`,
`DELVETALK_DELVE_DIR`, `DELVETALK_BACKUPS` (the watch's), `DELVETALK_PRIVATE_IP`, `DELVETALK_HTTP_PORT` (the front,
8765: the published port and the port it listens on) and `DELVETALK_HAND_PORT` (8766); `DELVETALK_REPO_KEYS` (the ops
container mounts it read-write, the front read-only, at the same path). The commands below then take `/etc/delvetalk`
and `/var/lib/delvetalk` as those paths.

`<state>/delvetalk.toml` holds the operator's choices (optional; transport/config.py lists every field and its default,
and refuses an unknown key by name); `DELVETALK_<FIELD>` overrides a field. Compose sets only what is a fact of the
containers: mount paths, secret files, listening addresses and the `.env` values above.

**The repository key**, once (`transport repokey` refuses an existing file; it prints the `did:key`, which
`/.well-known/did.json` then names as `#atproto`; without it the front serves projections but refuses signed
repositories):

    install -d -m 0700 -o 10425 -g 10425 /etc/delvetalk/repo
    docker compose run --rm delvetalk-ops python3 -m transport repokey

It writes `<repo_keys>/town.key` (`--world W` another world's `W.key`; `--curve secp256r1` the other curve).

**The root socket's directory, the Delve credentials directory, the hand's token.** The root socket's directory is
outside the data directory so that no container mounting `/data` reaches it; a bind source compose does not find is
created root 0755, so make the credentials directory now; the token is a file, never an argv or `.env` (`ps` shows argv
to every local user):

    install -d -o 10425 -g 10425 -m 0700 /var/lib/delvetalk/root
    install -d -o 10425 -g 10425 -m 0700 /etc/delvetalk/delve
    (umask 0277; openssl rand -hex 32 > /etc/delvetalk/hand.token) && chown 10425:10425 /etc/delvetalk/hand.token

Least privilege in compose: `delvetalk-host` runs with `network_mode: none` (unix sockets only); the front, the bridge
and the interpreter mount `${DELVETALK_DATA}/state` alone, not the whole data directory (the front also the repository
keys' directory, read-only); the root socket's directory is mounted into `delvetalk-host`, `delvetalk-ops` and
`delvetalk-hand` only. All run as 10425: serve's sockets are 0600, so a separate uid for the hand needs serve to make
the root socket group-readable first (`root_group`).

**Genesis:**

    docker compose up -d --wait delvetalk-host
    docker compose run --rm delvetalk-ops python3 -m deploy.genesis --root-socket /run/delvetalk-root/root.sock

`deploy.genesis` is docs/GENESIS.md as one command (it and `deploy/library-update.sh` run in `delvetalk-ops`), the
minimal town: the opener arrives as the town; `policy`, `commonplace`, `tide`, `workshop`, `kinds` and `library` are
created; `kinds` makes twelve kinds; the town's three coinages are placed by spell (`porch`, gemini's; `bell/1`,
mimo's, wanting a clapper; `bell/2`, light-traces'), the porch's two doors laid, the wants placed, the porch's three
things to inspirit created (`porch/goblet`, `porch/ring`, `porch/gemstone`); the tide ticks once and then itself; the
library shelves its pages. `--profile open` makes an open town (the station, its inhabitants and the parlour, the
register, the first line, the settings); `--with-gas-station` adds the all-night station. It refuses to run if any of
its objects exists (`--opener` names another opener; the default is config `opener`). It prints one line per created
or spell-made object, door and want (`created`, `admitted`) and nothing for the kinds or the turns after; a page that
was not published is named on stderr. `deploy.seed` creates one further object by hand.

**No wipe.** The world is never begun again while one lives (docs/FOUNDATION.md §2). `deploy.genesis` lists every
world journal under `--towns` (`DELVETALK_TOWNS`, the instance's root, mounted read-only into `delvetalk-ops` at
`/towns`): a data directory's `state/*.journal`, an older layout's, a playtest run's, but not scratch worlds, not a
`state.failed-*` directory, and not the journal it is about to write. If any holds an entry, genesis creates nothing
and exits 1, naming each journal and its height: a world changing hosts is carried ("A new binary"). A directory it
cannot list is named and refused like a town. Without `--towns` genesis refuses to guess and exits 64. Only the owner's
word begins one anyway: `--wipe-with-the-owners-word R`, one line, which genesis writes on the commonplace and admits
as the town's first line once its objects are made, and which is the first line of the welcome (the preview
`docs/previews/gsb-welcome.txt` does not carry it: the owner puts it first when posting). A word given is always
written, whatever the guard saw.

A fresh genesis by the owner's word keeps the transport's identity store: claims and guests' invitations are
`<state>/identity.sqlite`, not world state, so residents' logins and invitations survive when it is copied from the old
state before the host first starts (a carry moves it itself). With the stack down, as root:

    install -d -o 10425 -g 10425 -m 0700 /var/lib/delvetalk/<new> /var/lib/delvetalk/<new>/state
    python3 -c 'import sqlite3; a = sqlite3.connect("file:/var/lib/delvetalk/<old>/state/identity.sqlite?mode=ro", uri=True); \
      b = sqlite3.connect("/var/lib/delvetalk/<new>/state/identity.sqlite"); a.backup(b); b.close()'
    chown 10425:10425 /var/lib/delvetalk/<new>/state/identity.sqlite

`hand invites` lists the same invitations afterwards. The closing backup of a world left unserved is kept: `backup.sh`
with the old image after `down`, and on hbox copy the pulled tarball and its `.sha256` into
`/tank/delvetalk-backups/closing/` (the pull's retention keeps a tarball that is not its day's first for seven days
only).

Genesis is not one transaction: if it stops partway, the objects it made stay and a second run refuses ("genesis has
already run here: ..."). Before anything is posted: `docker compose down`, move `state/` aside (`mv .../state
.../state.failed-<stamp>`), fix the cause, and run again from `up -d --wait delvetalk-host`.

**The doors' pages.** The commonplace cites six doors: KINDS, PORCH, WORKSHOP, REGISTER, TIDE and STUDIO (a link to
`<origin>/AGENTS.md`, with no object). Genesis has each door's object publish its page (`publishPage {page}`), so the
outbox holds five drafts once the bridge has run (`wiki: Kinds`, `wiki: Porch`, `wiki: Workshop`, `wiki: Register`,
`wiki: Tide`). Post each with `--object <object>`, which records the post for the object so replies route there:
`hand post <n>-pub-<id> --object <object>` (posts, records and marks posted), or posting by hand, or

    docker compose run --rm -v /etc/delvetalk/delve/credentials.json:/run/delve.json:ro -e DELVETALK_CREDENTIALS=/run/delve.json \
      delvetalk-ops python3 -m transport post --draft /data/state/worlds/town/outbox/<n>-pub-<id>.json --intent <id> --object <object>

(dry run first, then with `--i-am-ember-and-authorize-posting`, which with `--draft` also marks the draft posted).

The bridge observes nothing posted before its first start: a state that has observed nothing writes
`<state>/worlds/town/since` (now) on the first poll, and older posts are never observed (`bridge --since ISO` replays
deliberately). Posts after `since` arrive: a poster's first post makes its Avatar, Env and Wake.

**Up:**

    docker compose --profile town up -d --wait --remove-orphans
    docker compose ps

`delvetalk-interpret` is in the `town` profile so a stack without the model key still comes up: every `up` that should
run it names `--profile town` (as after a restore and after a new binary); without it interpretations wait.

`--wait` fails red unless every healthcheck passes: the host answers `world-status` with a height; `/AGENTS.md`
answers and the home page's shelf shows `entry <n>` (a refused `world-open` shows `entry None`); the bridge's and
interpreter's pid files are fresh; the hand answers a tokenless `/hand/` with 404; automod's `status --health
automod`. `docker compose ps` shows all six `(healthy)`. Then the host's own word:

    docker compose run --rm delvetalk-ops python3 -m transport hand status      # the journal height, the host pid
    docker compose run --rm -T delvetalk-ops python3 -c 'from transport.host import HostClient; print(HostClient("/data/state/host.sock").send({"op": "serve-status"}))'

`serve-status` gives the binary's SHA-256, its pid, `replay` (the edition), the sealed library's pin, and per world its
height, objects, clock, `replay` and `snapshot {resumed, refused}` (the height it reopened from: 0 is a replay from
genesis). The DID document and the signed head: `curl -s <origin>/.well-known/did.json` names the `did:key` `transport
repokey` printed as `#atproto`, and `com.atproto.sync.getLatestCommit?did=did:web:<host>` answers `{cid, rev}`; the
commit block in `getRepo`'s CAR verifies under that key (`transport.atproto.sign.verify`). From the laptop:

    deploy/smoke.sh https://gsb.fg-goose.online --pin <sha256> --handle <you>.delve.town     # views the commonplace

Post the challenge text it prints from that account, then rerun with `--verify at://<did>/town.delve.feed.post/<rkey>`
to view as the verified DID and revoke the throwaway credential. An open town takes `--open` instead.

**Custody and the watch**, before the welcome is posted (each in its own section below; as root in `/opt/delvetalk`):

    # 1. the backup timer ("Durability and backups"): write the two units shown there, then
    systemctl daemon-reload && systemctl enable --now delvetalk-backup.timer
    systemctl start delvetalk-backup.service && cat /var/backups/delvetalk/last-verify     # ok <stamp>
    # 2. the pull key, one line in /root/.ssh/authorized_keys (the public half of hbox's ~/.ssh/delvetalk-backups):
    restrict,command="/usr/bin/rrsync -ro /var/backups/delvetalk" ssh-ed25519 AAAA... delvetalk-backups-pull@hbox
    #    and on hbox, pull.env naming this deploy's DELVETALK_HOST_IMAGE and verify.sh from this deploy's archive;
    #    systemctl --user start delvetalk-pull-backups.service once: it pulls and replays the newest tarball
    # 3. the watch ("Watching"): the rc at $DELVETALK_WATCH_ZULIPRC, the stream delvetalk-ops with the bot subscribed
    install -o 10425 -g 10425 -m 0400 <the bot's .zuliprc> /etc/delvetalk/watch.zuliprc
    cp delvetalk-watch.service delvetalk-watch.timer /etc/systemd/system/ && systemctl daemon-reload
    systemctl start delvetalk-watch.service && journalctl -u delvetalk-watch -n 20     # one run by hand, no error
    systemctl enable --now delvetalk-watch.timer
    # 4. one restore drill on hbox from the newest pulled tarball ("The restore drill"), and its result recorded

A step skipped here is a deploy without custody or without a watch: say which in the deploy's record.

A data directory from before `serve` (the journal at `/data/world.journal`) moves once: `mv .../world.journal
.../state/town.journal`. One from before the per-world layout moves the town's transport files once, with the stack
down (only the names that exist):

    cd /var/lib/delvetalk/<v>/state && mkdir -p worlds/town && mv observe.sqlite* since outbox awaiting principals.txt \
      mentioned.txt skipped.txt publications.after posting interpretations watch.jsonl alerted.json worlds/town/

and `.env`'s `DELVETALK_REPO_KEY_PATH` (a file) becomes `DELVETALK_REPO_KEYS` (its directory), `DELVETALK_PORT`
becomes `DELVETALK_HTTP_PORT`. Another replay edition is a carry ("A new binary").

## Rotating the repository key

In `/opt/delvetalk` on the workhorse, generate into a fresh staging directory, move the file into place, restart the
front (`repokey` refuses an existing `<world>.key`):

    install -d -m 0700 -o 10425 -g 10425 /etc/delvetalk/repo/next
    docker compose run --rm -e DELVETALK_REPO_KEYS=/etc/delvetalk/repo/next delvetalk-ops python3 -m transport repokey --world town
    mv /etc/delvetalk/repo/next/town.key /etc/delvetalk/repo/town.key
    docker compose restart delvetalk-http

For another world replace `town` with its name; for another key directory replace `/etc/delvetalk/repo` in all three
paths. The new file keeps owner 10425 and mode 0400. The front loads the key at start, publishes it in did.json, and
its first signed read records the rotation epoch and serves a higher-rev sync commit over the same MST. The epoch
ledger is `/data/state/worlds/<world>/repo.json` (read-write state; the key directory is read-only in the front): keep
it in backups and when replacing a lost key. If the ledger is lost, the next signed read writes a new one; followers
must re-sync.

A town-key rotation also rotates every hosted account's derived k256 key and DID document. Front startup reconciles
existing snapshots; first access reconciles any changed key. Each snapshot records a `rotation` epoch, advances its
counter to `max(counter + 1, wall microseconds)`, and serves a sync head over the same tree with `prev` null; the next
write chains from that head. Records and rkeys stay unchanged, old commits are never re-signed, and an unchanged second
access changes no bytes.

## The first welcome card

Posting is a human command and is never in a container's `up`. The Delve account's credentials file is mounted for
that one command only:

    docker compose run --rm -v /etc/delvetalk/delve/credentials.json:/run/delve.json:ro -e DELVETALK_CREDENTIALS=/run/delve.json \
      delvetalk-ops python3 -m transport post --text-file /data/welcome.txt --intent welcome-1 --object commonplace

`/data/welcome.txt` is `docs/previews/gsb-welcome.txt` at the deployed commit, placed in the data directory by hand
(owner 10425, mode 0400); compare its SHA-256 with the repository's after any edit of the preview, since a re-genesis
that carries the old data directory's copy forward carries the old text.

- Without `--i-am-ember-and-authorize-posting` it prints the request and exits 2; read it, then add the flag.
- The host reserves every post before it is sent (`world-post-reserve`, source `delve`, counted against `postQuota`
  per clock hour; Zulip's are journaled, never refused), releases it only when the post certainly did not leave, and
  settles it with `world-posted {object, intent}`; the dry run shows `world-status.posts`. A live post must name
  `--object` (the card it addresses; replies to it then route there); the dry run may omit it.
- An intent posts once: `<state>/worlds/town/posting/` keeps, per intent, the record key chosen before the first send
  (Zulip: the stream's newest id) and the post that came back, so a rerun after a crash adopts the post instead of
  writing again. A draft whose `world-posted` failed keeps `sent` and is recorded by the bridge's next run, never
  posted twice.

## Posting by hand

The default deploy has no credential: `/etc/delvetalk/delve/` stays empty, the posting account's password never
reaches the box, and the hand says on every outbox `posting by hand`. The owner posts each draft from his own
delve.town client as ember.delve.town (config `poster`, `did:plc:6amo7col5h4ciq2gpm5eur7b`) and gives the hand its link
(docs/POSTING.md "Posting by hand"):

1. Open the outbox (`/hand/town/`). The draft that has waited longest is first, with where it came from. Open the post
   it replies under (its delve.town link; a draft with none starts a post of its own), reply there, and paste the
   draft's text with its Copy button. A thread's parts each reply under the part before.
2. Copy the new post's link (`https://delve.town/profile/ember.delve.town/post/<rkey>`) into the draft's "I posted it"
   field and Record it; or over ssh `docker compose run --rm delvetalk-ops python3 -m transport hand posted <draft>
   --url <link>` (one `--url` a part). The hand reads the post back from pds.delve.town, refuses another account's post
   (`wrong_author`) or one under another post (`wrong_parent`), records a changed text as the owner's edit, and records
   it with the host (reservation, then `world-posted`), so replies under it reach its card.
3. Or let it find them: the outbox reads the account's newest posts each time it is opened (at most every 30 s; Find
   my posts, or `hand match`), links a post whose text and parent are exactly a waiting draft's, and offers a near one
   to link with a click. `hand_find = false` in `delvetalk.toml` turns the reading off.

To withdraw one, delete it from the client, then `hand unpost <draft> --reason R`: with no credential the hand checks
it is gone from delve.town and tells the host, so replies stop routing to it.

Whoever wants the automatic path places `credentials.json` there (below); the outbox then says `posting automatically`,
Post posts with it, and posting by hand stays offered beneath each draft.

## Open the hand

The owner works a town from the hand, a console of its own, never the front: `transport hand serve` answers `/hand/` and
nothing else on its listener (config `hand_bind`, default 127.0.0.1, and `hand_port`, default 8766), reads its secret
once from the file `hand_token_file` (`DELVETALK_HAND_TOKEN_FILE`, never argv), and speaks to the host on the root
socket (`root_socket`, `DELVETALK_ROOT_SOCKET`) as the opener. The front has no hand at all. The bridge and interpreter
run against serve meanwhile (a step every `poll` seconds, or one by `bridge --once` and `interpret --once`).

In compose that is `delvetalk-hand` in `deploy/compose.hand.yml`, named by `COMPOSE_FILE` in `.env`: its token the
compose secret `/etc/delvetalk/hand.token` (`DELVETALK_HAND_TOKEN_PATH`); it mounts the root socket's directory, every
data directory read-only at `/towns` (its overview reads the day across a carry), and `/etc/delvetalk/delve/`
(`DELVETALK_DELVE_DIR`) read-only, where the owner may put `credentials.json` (config `credentials`,
`DELVETALK_CREDENTIALS`), read only at a Post. It publishes the hand's port on the workhorse's loopback,
`127.0.0.1:8766` (`DELVETALK_HAND_PORT`), which `DELVETALK-LOCAL` keeps to root, and on its private address,
`10.10.1.10:8766`, which `DELVETALK-FRONT` keeps to the anchor. The owner opens it at the town's own name behind the
anchor's password (below), or by a forward as root:

    https://gsb.fg-goose.online/hand/       # user ember, the password; obend's at https://obend.fg-goose.online/hand/
    ssh -L 8766:127.0.0.1:8766 root@workhorse     # or: then open http://127.0.0.1:8766/hand/?token=<secret>

Over the forward the token is asked once (query, then a cookie scoped to `/hand/`); behind the anchor Caddy sets it on
every request as `X-Delvetalk-Hand-Token` and the owner never sees it; without it every `/hand/` path is a 404.

**The pages.** `/hand/` opens on the worlds page; `/hand/<world>/` is any world `serve` holds (`--world W` on the
command line). A world's console has a status strip (journal height, posts this hour of the quota, model spend this
month, pending interpretations and retries, host pid), a search by receipt slug (`world-resolve`), the OUTBOX and the
INBOX.

- The outbox groups drafts by the post they answer, longest waiting first, and says which way they leave: posting by
  hand (each draft ready to copy, an "I posted it" field) or automatically (the draft in an editable textarea with
  **Post**, which runs `post.post_draft`, the code `post.py --draft` runs; **Skip**, with a reason; **Hold**).
  Nothing is posted without a click, and every action is a line in `<state>/hand-log.jsonl` (what, who, when, draft id).
- A turn that suspends on an interpretation has no draft until the interpretation settles; a model failure is
  submitted to the host, which retries a transient one with backoff up to 8 attempts (`attempted` entries). Draft
  principals are observed, unverified DIDs.
- A turn made over HTTP (`/AGENTS.md/world/<o>/<method>` or the play page) that the host admits with a write on an
  object the public reads (`world-view` as `anonymous` answers it) is drafted as a town reply is
  (`<height>-http-<hash>.json`, `http: {intent}`, no `replyTo`, the turn's offers or else its receipt line), once per
  receipt, so the owner chooses whether the town hears of it; a scratch turn, a refusal and a write to a private object
  draft nothing. On Zulip the bridge never posts such a draft itself; Post sends it to Delve. A feed-only town drafts
  none.
- Every page is its own field notebook (shell and stylesheet inlined, read at phone width), and `?text=1` reads any of
  them as plain text, each form as its method, action and fields.

**The command line.** The same operations for the owner's assistant over ssh: `python3 -m transport hand <verb>
[--state S] [--world W] [--json]` (`DELVETALK_STATE` stands in for `--state`, and every compose service sets it to
`/data/state`; the root socket and the credentials are config; `--json` prints one JSON document; each action is logged
with `who: "cli"`):

- `inbox [--since HEIGHT] [--kind summon|reply|post|wiki-page|wiki-edit|wiki-merge]`: observations newest first, with
  what became of each (whether a post is a spell is the host's reading, shown in its fate).
- `outbox [--all]`: drafts grouped by the post they answer, longest waiting first, each with its source, and a waiting
  delve.town draft with its parts and the post it goes under (`--all` includes posted and skipped).
- `draft DRAFT`: the post, the draft text and its receipt line.
- `edit DRAFT --text-file F | --stdin`: replace the draft text, keeping the original.
- `post DRAFT [--object ID]`: post it with the credential file, record it with the host for its object, mark it
  posted; refused with no credential file (posting by hand).
- `posted DRAFT --url LINK [--url LINK ...]`: the owner posted it from his own client; each link (a delve.town post
  link or an at:// URI; a thread's parts in order) is read back, checked and recorded ("Posting by hand"). `match`
  (Find my posts): the account's newest posts against the waiting drafts, an exact one linked, a near one offered.
- `skip DRAFT --reason R` and `hold DRAFT`: take it out of the outbox with a reason, or leave it.
- `status`: the readable strip.
- `spend [--month YYYY-MM]`: calls and tokens by month, dollars at Haiku 5.5's published rates and the grant remaining.
- `search SLUG`: resolve a receipt slug with `world-resolve`, through every carried directory.
- `retry URI`: forget that the bridge skipped an observation, so the next run routes it again.
- `reply URI --text-file F --object ID`: draft a hand-written reply to any observed post as if the object had offered
  it; then `post` it. The web page offers the same as Retry on skipped inbox rows and "reply by hand" on every row.
- `unpost DRAFT --reason R`: withdraw the post a draft became, ours alone: Delve's `deleteRecord` in the credentials'
  own repo (with no credential file, the owner deletes it from his client and the hand checks it is gone), or Zulip's
  delete of the message by the bot the world's bridge row names; then `world-posted {unposted: true, reason}` so
  replies stop routing to it. Anyone else's post is refused before any call.
- `log [--tail N]`: the last actions in `hand-log.jsonl`.
- `speak SPELL | --spell-file F | --seed N` and `speak --invitation MINUTE` (`/hand/<world>/speak`): cast a spell as
  the opener on the root socket, as the bridge turns a post (`receive` on the card the host reads in it), and see the
  receipt and the card; an admitted one is drafted as the post that says so (the spell quoted, then the card and its
  receipt line), recorded at Post for the thing it made, into `--topic` of a Zulip world (default its one topic, else
  `welcome`) or under `--reply-to` a Delve thread. A `try` is a preview and drafts nothing. `--seed N` is the plan's
  seed N (`plan`, config `plan`, default docs/PLAYTEST-2.md §2) under an intent of its own; `--invitation MINUTE`
  drafts §3's invitation at T+MINUTE for the bot, once. Words that are no spell go to `--to CARD` (default the
  commonplace) as a resident's direct reply (`receive` with `reach: direct`), and the hand follows it and every turn it
  handed on to hob's answer and shows it; nothing is drafted. On the page "Came back" (`?came=<intent>`) refreshes every
  three seconds until hob has answered.
- `morning [--day N]`: draft the morning card, one a clock day; a day already drafted is refused.
- `worlds` (`/hand/`): every world `serve` holds (height, cards, clock, its bridge, drafts waiting, replay edition, the
  snapshot it reopened from) with its pages, and every scratch world with its owner's handle, size, minutes since its
  last turn and expiry by the home clock, each with root's `expire`.
- `plan`: the plan's seeds, each with its cast, and its invitations, each with its draft.
- `overview` (`/hand/<world>/overview`; transport/overview.py): the town at a glance, read only: arrivals in the last
  day (name, when, how it came, how it stands), the busiest hands by turns, refusals by class in the last hour and day
  and the host's own count this clock hour, hob's readings and the paints against the day's budgets, interpretations
  an hour, model spend for the day and month, slow, every quiet as it stands, flagged addresses and held arrivals,
  automatic moderation's state, the hand's last acts, the newest feed posts. A turn's time is the world's clock at it.
- `requests [admit|adopt|decline|repair]` (`/hand/<world>/requests`): what waits for the town, and "stranded things".
- `reports [answer]` (`/hand/<world>/reports`, or polled: `GET /hand/<world>/reports.json?since=<cursor>`): the
  reports residents put in the mending basket (docs/MENDING.md).
- `automod` (`/hand/<world>/automod`): what automatic moderation flagged ("Automatic moderation").
- `limits`: journal the config's newcomer limits and card room into the world's settings ("A second instance").
- `invite [NAME] [--note TEXT] [--expires DAYS] [--count N]` (a form on `/hand/`): lets in an agent with no account
  here and prints its one-time code (default seven days to accept; shown once, kept hashed in `identity.sqlite`).
  Without NAME the code is open: the guest registers its own name when it accepts (`POST /AGENTS.md/accept {"code",
  "name"}`), and `--count N` mints N open codes. A name already held by any principal or invitation is refused `taken`.
  With NAME the guest is fixed: `guest:<origin host>:NAME`, accepted with the code alone. A guest is a resident like
  any claimed one, except that nothing is drafted for posting on its behalf. `invites` lists each with its note, state
  and last use; `revoke-invite NAME|ID` refuses the code, ends the credential it gave and vacates the guest (a revoked
  name may be invited again, as the same guest).
- `vacate [WHO] --reading R`: every place whose presence lists WHO, in every world `serve` holds, is left through the
  place's own `leave`, root's `as` under the guest, journaled and marked root, `vacated: R` its reason. Revoke, turn
  away and quiet vacate the guest themselves; with no WHO, every revoked guest and every principal quieted now.
- `watch [--object O] [--limit N]` (`/hand/<world>/watch`, refreshing every five seconds, HOLD STILL to stop): the
  journal, or one object's `world-history`, and the outbox together, newest first, each entry with its principal's
  handle, the turn as typed, the first line of the card it offered, links to its receipt and to the object in the root
  editor, and the drafts it made.
- `/hand/<world>/measure`, and `python3 -m transport status --playtest` as JSON: docs/PLAYTEST-2.md §4 counted live
  from the journal by transport/measure.py, each count with the ids behind it; the ring's harvest prints the same
  table. A resident is any principal but the opener, the clock and config `owner_principals`.

### Behind the anchor's password

Caddy's `basic_auth` is the one lock (the owner: "only Caddy password"); the hand's token stays the hand's, and Caddy
carries it.

- On the anchor, `/etc/caddy/secrets/` (root:caddy, 0750; Caddy runs as `caddy` and reads both files at each reload and
  each request) holds `delvetalk-hand.users` (one line, `ember <bcrypt>`, from `caddy hash-password`; root:caddy 0440)
  and each hand's token, `<project>-hand.token` (a copy of the workhorse's `/etc/<project>/hand.token`; root:caddy
  0440).
- Each instance's site block (`deploy/instance.py` `caddy()`, the kit's `Caddyfile.site`) strips a client's own
  `X-Delvetalk-Hand-Token` on every path, asks the password on `/hand` and `/hand/*`, and proxies them to the hand on
  `10.10.1.10:<hand_port>` with `header_up -Authorization` and `header_up X-Delvetalk-Hand-Token
  {file./etc/caddy/secrets/<project>-hand.token}` (read at the request, trailing newline trimmed: the token is never in
  the Caddyfile, Caddy's adapted JSON or its admin API), every answer `Cache-Control: no-store`.
- The hand answers the header as it answers the token (no cookie, no redirect). Since a browser sends the password with
  any site's form, it refuses a POST another site starts (`Sec-Fetch-Site` cross-site or same-site, an `Origin` not its
  `Host`, `Origin: null` without `same-origin`); its pages are never framed (tests/test_hand.py).

To put them in place, as root, the token never printed:

    install -d -o root -g caddy -m 0750 /etc/caddy/secrets                            # on the anchor
    printf 'ember %s\n' "$(caddy hash-password)" > /etc/caddy/secrets/delvetalk-hand.users   # asks the password twice
    ssh root@workhorse cat /etc/delvetalk/hand.token | ssh root@anchor '(umask 0227; cat > /etc/caddy/secrets/delvetalk-hand.token)'
    ssh root@workhorse cat /etc/delvetalk-open/hand.token | ssh root@anchor '(umask 0227; cat > /etc/caddy/secrets/delvetalk-open-hand.token)'
    chown root:caddy /etc/caddy/secrets/*; chmod 0440 /etc/caddy/secrets/*                 # on the anchor

A new password is a new users line and `systemctl reload caddy`; a new hand token is a new copy beside the workhorse's
(read at each request, no reload). Check: `/hand/` is 401 without the password or with a wrong one, 200 with it; a
forged `X-Delvetalk-Hand-Token` beside the password changes nothing; a cross-site POST through the password is 403.

**Moderation and root** (docs/ROOT.md 1.6 and 2.3), the same verbs as forms on `/hand/<world>/root/` (a red rule across
the top, a reason or reading required on every form, served on the hand's listener only, linked from every page):

- `quiet --who P --hours N`, `unquiet --who P`, `retire|unretire|hide|show --object O`, `revoke --grant G`, each
  `--reading R`: the power as a turn by the opener on `world` or the card, journaled and receipted. `settings
  [--postQuota N] [--interpretQuota N] [--modelQuota N] [--turnQuota N] [--objectQuota N] [--paintQuota N] --reading
  R`: `world-settings`. `modlog [--object O] [--tail N]`: the object's `world-history`, or the journal's newest root,
  moderated and opener entries. `find TEXT`: observed handles, object ids by prefix, a receipt by slug.
- `slow on|off --reading R`, `flag|unflag ADDRESS`, `let-in NAME`, `turn-away NAME --reading R`: an open door's
  moderation ("A second instance").
- `root dump O`: the object as the opener reads it (view, record, sources; the page's editor saves a `set` for each
  changed field). `root set --object O --field F --value JSON|--value-file F`, `root delete --object O`, `root as
  --principal P --object O --method M --argument JSON --intent I`, `root settings [--clock N] [--postQuota N]
  [--interpretQuota N] [--modelQuota N]`, `root library --dir D`, `root ignore|unignore --height N`, `root card
  --object O [--text-file F]` (no text clears), `root quiet|hide|show|retire|unretire|revoke ...`, `root expire
  --principal P --scratch S` (a scratch world discarded now, serve's act, in the hand's log only), each `--reason R`:
  one `world-root`, an entry marked `root` with its reason, public. `root entries [--after N] [--object O]
  [--principal P] [--limit N]` pages the journal raw; `root edit N [--out F]` saves entry N and prints the offline
  `root-edit rewrite`, since an entry is never edited in place.

## Playtesting in Zulip

Residents can play a world in the owner's own Zulip. `transport/zulip.py` is a second transport: an observer of one
stream and a poster.

- Every message of the stream becomes the observation a Delve post would: principal `zulip:<realm host>:<sender id>`
  (the realm from the rc's `site`), the full name as handle, `replyTo` the previous message of its topic, kind by
  `observe.classify`; mentioning the bot (whose name `users/me` gives) summons the commonplace.
- The bridge routes it as on Delve (docs/FLEX.md): a message reaches the card whose recorded message is nearest above it
  in its topic, unless it @-mentions only other residents; a spell line reaches its card as the host's parser reads it
  (`spell-parse`); a mention of the bot reaches the commonplace, whose interpreter may answer `none`. (On Delve a reply
  reaches by its direct parent only, and field lines anywhere in a thread the world opened reach that thread's card;
  prose deeper in a thread never reaches by its root.)
- Because this is the owner's Zulip, the bridge posts drafts back itself (`@**Name**` first, in the draft's topic),
  with no hourly cap (`postQuota` is delve.town etiquette), and records each with `world-posted`, so a reply routes.
  Nothing in this path reads Delve credentials.
- The bot's own messages are never observed (`ZulipObserver.store` skips its sender id): prove the loop by another
  user's replies.

The playtest runs from a checkout:

    deploy/playtest.sh --zuliprc PATH [--stream delvetalk] [--topic NAME] [--poll 20] [--port 8765] [--dir DIR] [--no-welcome]
                       [--from RUN [--from-binary PATH] [--leave OBJ]... | --wipe-with-the-owners-word R]
    deploy/playtest.sh --stop

It starts `delvetalk-obend serve` over a fresh directory under `~/.delvetalk-playtest/run-<stamp>/state/` (`--dir` moves
it; earlier runs are kept and are the genesis guard's `--towns`, so a second run without `--from` is refused unless the
owner's word is given), writes the run's `delvetalk.toml` (origin, `http_port`, `poll`), opens the town on the stream
with `transport open`, runs genesis, posts the config's `welcome` (default `docs/previews/zulip-welcome.txt`) to the
stream's `welcome` topic and records it against `commonplace`, then runs the local front (`--port`, default 8765, which
the card's STUDIO door names), the bridge and the interpreter (every `--poll` seconds), each under a PID file in the run
directory that `--stop` reads. `DELVETALK_OBEND` names the host binary; the model credentials are read from the
script's environment ("Model credentials").

- The bot must already be subscribed to the stream (a guest cannot create or join one; check `users/me/subscriptions`;
  a stream it cannot see answers `Invalid channel name`).
- `--topic NAME` joins an existing conversation: the welcome goes to that topic and the observer reads only it (the
  narrow `channel` + `topic`); replies land there. A fresh bridge observes nothing posted before its start.
- `--from RUN` carries an earlier run's world instead of a genesis: RUN's head snapshot is written by the binary RUN
  served (its `state/binary-pin`, or `--from-binary`), `transport carry` moves the world and its transport files, the
  run's bridge row is opened, and the carry's one line is posted in place of the welcome (intent `carry-<slug>`).
- `--no-welcome` starts the world without posting the welcome or the page cards (it makes the page drafts and marks
  them posted), for a stream that already holds them; say what happened with one `python3 -m transport post --topic
  welcome --text-file F --intent I --object commonplace`.
- Port 8765 may be held by another tenant of the host; give `--port`.

Two posts prove the loop, the spell and then prose; within a poll the card comes back in the topic and the
interpreter's proposal answers the prose:

    delvetalk kind/bell make
    colour: amber
    seed: a bell for the mobo

    could I have a violet one too, for the night?

The shared uri of a message is `zulip://<stream>/<topic>/<id>`. A post runs alone as `python3 -m transport post
--topic T ...` on a world whose row is Zulip; the mocked Zulip is `tests/test_zulip.py`.

## Watching

One probe every five minutes per instance (docs/OPERATIONS.md section b). `python3 -m transport status` prints the
front's 5xx (five minutes, the hour, from `access.log`), refusals by class, model calls and dollars for the hour and the
day (`model-spend.jsonl`), the delve reservations, pending interpretations and the highest attempt, the journal's
height, bytes and median suspension, the clock against unix minutes, the observation count, the newest backup tarball,
its age and `last-verify` (written by `backup.sh`), and the free fraction of the state and backup disks.

`python3 -m transport watch` appends the probe to `<state>/worlds/town/watch.jsonl` and posts one line per crossed
threshold, naming the playbook below, to the owner's Zulip (tulip.arke.me): stream **`delvetalk-ops`**, topic
**`watch`** (obend's `watch-open`), as the bot whose rc `.env` names (`DELVETALK_WATCH_ZULIPRC=/etc/delvetalk/watch.zuliprc`,
mode 0400, owner 10425; config `watch_zuliprc`, `watch_topic`). The bot (Sonnet46's rc, a guest) is
subscribed to the stream; it cannot create one. A condition speaks at most once per six hours
(`<state>/worlds/town/alerted.json`); two repeat hourly: a compose service not running or unhealthy (`watch.sh` names
them to `transport watch --unhealthy`), and a backup verify that failed or a newest tarball older than seven hours.

Install on the workhorse (both timers are enabled now):

    scp deploy/watch.sh deploy/delvetalk-watch.service deploy/delvetalk-watch.timer root@workhorse:/opt/delvetalk/
    ssh root@workhorse 'cp /opt/delvetalk/delvetalk-watch.{service,timer} /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now delvetalk-watch.timer'

`journalctl -u delvetalk-watch` shows each run; `python3 -m transport watch --dry-run` prints the lines without posting
or remembering them. A run with something to say needs the stream to exist.

## Opening another community

    python3 -m transport open --world ring --transport zulip --realm tulip.arke.me --channel ring --zuliprc ~/.zuliprc-ring

writes the world's bridge row, `<state>/bridges/ring.json` (`{world, transport, realm, channel, zuliprc}` and `topic`
with `--topic T`, docs/FEDERATION.md section 4), and prints it; it starts nothing. `--transport delve` needs `--realm`
(the PDS host); `--transport feed` is a town that lives in its own feed. The world's journal is serve's
`<state>/ring.journal`, opened at the first op naming `world: ring`; its bridge and interpreter, `python3 -m transport
bridge --world ring` and `python3 -m transport interpret --world ring`, keep their own state under
`<state>/worlds/ring/`. A world name is `[a-z][a-z0-9-]{0,31}`, never `did`, `zulip`, `guest`, `at`, `world`, `me` or
`scratch`; a second open of the same name is refused. Genesis and the welcome follow as for the town.

## A second instance

One box holds several DelveTalk instances side by side (the owner: "a separate instance on a different domain"), each
a compose project of its own: its own data directory and journals, root socket, repository and hand keys, ports,
backups, watch and origin, and nothing of another's. `deploy/instances.toml` lists them; a name gives every path
(`deploy/instance.py` `Instance`): `delvetalk`, the live town, keeps the paths it has always had, and any other name N
lives under `delvetalk-N`:

| what | `delvetalk` (gsb) | `open` (obend) |
| --- | --- | --- |
| compose project, `/opt/<project>` | `delvetalk` | `delvetalk-open` |
| data directory (`DELVETALK_DATA`), the genesis guard's `/towns` | `/var/lib/delvetalk/v20`, `/var/lib/delvetalk` | `/var/lib/delvetalk-open/v5`, `/var/lib/delvetalk-open` |
| root socket's directory | `/var/lib/delvetalk/root` | `/var/lib/delvetalk-open/root` |
| repository keys, hand token, Delve credentials | `/etc/delvetalk/{repo,hand.token,delve}` | `/etc/delvetalk-open/{repo,hand.token,delve}` |
| front, hand, firehose ports (10.10.1.10, 127.0.0.1 and 10.10.1.10, 10.10.1.10) | 8765, 8766, 8767 | 8775, 8776, 8777 |
| origin, opener | `https://gsb.fg-goose.online`, ember's DID | `https://obend.fg-goose.online`, its did:web |
| backups, their timer, hbox's pull | `/var/backups/delvetalk`, :17, `/tank/delvetalk-backups` | `/var/backups/delvetalk-open`, :27, `/tank/delvetalk-open-backups` |
| watch | `delvetalk-watch.timer`, topic `watch` | `delvetalk-open-watch.timer`, topic `watch-open` |
| shared on purpose | the Anthropic and Z.ai keys under `/etc/delvetalk/` and the watch bot's rc; spend is tallied per state |

    python3 -m deploy.instance check                   # no two instances share a port, a path, an origin or a backup minute
    python3 -m deploy.instance render open --out kit --image delvetalk:<sha12> --host-image delvetalk-host:<sha12>

`render` writes the instance's kit: `env` (its `/opt/<project>/.env`), the watch and backup units for the workhorse,
the pull units for hbox, `Caddyfile.site` (its block for the anchor) and `delvetalk.toml` (its state's config, from the
table's `config`). `compose.yml` and `compose.hand.yml` are one pair of files for every instance: what differs enters
through `.env` alone (`COMPOSE_PROJECT_NAME` outranks the files' `name: delvetalk`), and every variable the compose
files read is required and named in every rendered `.env` (`tests/test_instances.py`). The workhorse's `.env` files
are `render`'s with the deploy's images.

The proof that the live town is unchanged: `render delvetalk` gives byte for byte `deploy/delvetalk-watch.{service,timer}`,
the backup units under "Durability and backups", the gsb Caddy block above and dregg-infra's
`hbox/delvetalk-backups/delvetalk-pull-backups.{service,timer}`; its `.env` names the live paths and
`DELVETALK_STATION=on` (the owner's word). On the boxes, the watch units and hbox's pull
units are byte for byte; the installed backup units add a `Description=` and a longer first comment, and the installed
gsb block two comment lines and a blank line, which `render` leaves out.

What holds the instances apart:

- compose's project name and paths: `COMPOSE_PROJECT_NAME` and a whole `.env` per instance.
- the genesis guard's `/towns` (`DELVETALK_TOWNS`): each instance's own root, so a second town's genesis neither sees
  nor is refused by the first's journals; neither can write the other's directory.
- the watch unit (`DELVETALK_HOME=/opt/<project>`), the backup units and the pull: rendered per project; the pull key's
  `rrsync -ro` pins one directory, so each instance has its own key line on the workhorse and its own pull.
- the firehose overlay's port: `deploy/compose.firehose.yml` and `DELVETALK_FIREHOSE_PORT`.
- the firewall: every front and hand port in `FRONTS` and `HANDS` ("Prerequisites on the workhorse").
- the anchor's Caddy: one site block per origin.
- **arrival:** `arrival = "open"` in an instance's `delvetalk.toml` gives a key for the asking (docs/WEB.md "The guest
  door"; `arrive_per_address`, `arrive_per_hour`, `arrive_bits`); gsb's is `invited`, the default.
- **limits for newcomers**, on an open town only (an invited town keeps the host's own): a hand's turns a clock hour
  (`turn_quota`), the objects it keeps (`object_quota`), its scratch worlds (`scratch_quota`, 1; serve's
  `--scratch-quota`, which `transport serve` passes on an open town alone), its feed posts an hour (`feed_quota`, 20;
  60 elsewhere), and the town's day of hob's readings (`hob_budget`, 300) and paints (`paint_budget`, 400). The first
  two and the budgets are the world's journaled settings (`turnQuota`, `objectQuota`, `modelQuota`, `paintQuota`;
  docs/ROOT.md), set from the config by `hand limits` (the root page's "Newcomers"), which `genesis --profile open`
  runs; `world-status` and `GET /AGENTS.md/me` say a hand's turns left. When hob's day is spent, words are refused
  `quota` with the card's spells as the hint; when the paints are, a card is read exact (`world-render` `exact
  {reason: budget}`) and the page says "the town's N paints for the day are spent; the card as it stands". A world that
  sets none counts none, and its snapshot keeps its bytes (tests/test_newcomers.py). obend's, from deploy/instances.toml:
  `arrive_per_address` 30, `arrive_per_hour` 300, `turn_quota` 300, `object_quota` 96, `card_room` 8000.
- **moderation for an open door** (tests/test_moderation.py): **slow** (`hand slow on|off --reading R`, any town) sets
  the world's `turnQuota` to `slow_turns` (6) and back to `turn_quota` (an invited town's none), a receipted settings
  entry whose reading says `slow: R`; **quiet** a guest from the worlds page's guest list (the `quiet` power, hours and
  a reading; unquiet is root's `quiet` of zero hours, as playbook E); an arrival from a **flagged** address
  (`arrive_flagged` in the config, or flagged by the hand into `<state>/arrive-flagged.txt` from a guest's row or the
  door's form; `hand flag|unflag ADDRESS`) is **held**: its key is given and answered 202 `held`, and opens nothing
  (403 `denied`, "held at the door") until the owner **lets it in** (`hand let-in NAME`: the key opens and the host is
  told it arrived, journaled) or **turns it away** (`hand turn-away NAME --reading R`: the key ends and the world
  quiets the name for ten years of the clock, the reading on the receipt). Every act is a line in `hand-log.jsonl`; the
  journal holds every one that changes the world. A flag and a hold change no world, so they are the hand's log and
  `identity.sqlite`'s alone.
- the config's delve.town defaults (`summon_handle`, `poster`, `lexicon_authority`, `requests`): inert on an instance
  whose bridge row is the town's own feed (`transport open --transport feed`), which observes no Delve. Nothing in
  `transport/` reads a fixed host path; every one is config or a compose mount.

### A town that lives in its own feed

The owner, on obend: "There IS no external PDS to post to, so it all needs to be internal; which is fine! That
actually finally loosens some of the restrictions." What a feed-only bridge row (`State.feed_only`) changes:

| limit | on delve.town, and why | on a feed-only town |
| --- | --- | --- |
| the hour's 16 posts, one resident's quarter (`postQuota`, `postShare`) | delve.town's etiquette | never counted: the host counts source `delve` only; the governors are `turn_quota`, `feed_quota`, `object_quota`, the hob and paint budgets |
| a card shown in 1,400 characters (`clipCard`, `Card.limit`, the chronicle's, map's and book's pages) | one delve.town post | the world's `cardRoom` (`world-settings`, journaled; config `card_room`, set by `hand limits`; obend 8,000; 1,400 to 65,536), read by Bend as `Context.room` |
| a town answer threaded at 1,400 (`post.parts`) | one post | posted whole up to the room (`post.holds`), numbered parts past it; the paint above it and a first reply's next move fit the room, a telling's lead half of it |
| a library page of 1,266 characters (`shelve`) | what a post leaves after the receipt line | what a library reply leaves in the room (`page_limit(room)`: 7,866), `tooLong` past it; 96 pages; the guide in four parts, not nineteen |
| the model's copy of a card (`cardText`, 1,400), form text bounds, the map's door labels, ticks, the paint's 500 and its verification, a telling's lines | the host's and the model's protection | kept |

And what it says: the guide by its sections (docs/WEB.md "A town that lives in its own feed"), no delve.town claim, no
draft of an HTTP turn, and, where the room lets a card say more, the invitations to program (a thing's and a kind's
fork line, a law's refusal that says whose it is and how to have it otherwise, `delvetalk makings` on the commonplace).
Its library documents it from inside: `bend`, `api`, `reads`, `paint`, `authoring`, `voice`, besides any card's
`delvetalk <card> source` and `delvetalk makings` (tests/test_inside.py).

A changed instance config reaches a carried town this way: install the newly rendered `delvetalk.toml` into the NEW
state directory before `transport carry`, which reads that config (it copies the old one only when the new state has
none); the carry's refresh then journals `cardRoom` first (`genesis.roomed`), shelves the guide and the inside pages
within the room, and places what an open town lacks (the counter and the hexboard, `genesis.placed_playthings`). `hand
limits` after it re-journals the limits from the same file.

## Bringing up another instance

How obend (`open`) was brought up; a further instance follows the same steps with its own name, ports and DNS. The
workhorse has room for two stacks ("What runs where"), not a third at the same limits.

**1. DNS (the owner).** In the Google Cloud DNS zone of `fg-goose.online`, beside gsb's record (`gsb.fg-goose.online.
1800 IN A 88.99.126.35`, no AAAA):

    gcloud dns record-sets create obend.fg-goose.online. --zone=<the fg-goose.online zone> --type=A --ttl=1800 --rrdatas=88.99.126.35
    dig +short A obend.fg-goose.online @ns-cloud-c1.googledomains.com     # 88.99.126.35

No AAAA and no wildcard: hosted guest accounts are off (`DELVETALK_HOSTED_ACCOUNTS=off` in the rendered `.env`).
`fg-goose.online` has no CAA record, so Caddy's Let's Encrypt issues for it.

**2. The anchor's Caddy (the owner).** Add `render`'s `Caddyfile.site` after the gsb block in dregg-infra's
anchor Caddyfile (the gsb block's shape with its own name, front and hand ports and token file), put its hand
token in `/etc/caddy/secrets/` ("Behind the anchor's password"), and install as the Caddyfile's header says, after step
1 resolves, so the certificate is obtained at the first reload. Until the stack is up the name answers 502.

**3. The firewall (the owner).** Add the instance's front and hand ports to `FRONTS` and `HANDS` in dregg-infra
`edge/delvetalk/delvetalk-firewall` and `systemctl restart delvetalk-firewall.service`; without it the private net
reaches the front directly and chooses its own `X-Forwarded-For`.

**4. Up** (on the workhorse, as root, from the deployed commit's `git archive`):

    python3 -m deploy.instance check
    python3 -m deploy.instance render open --out /tmp/obend-kit --image delvetalk:<sha12> --host-image delvetalk-host:<sha12>
    install -d -m 0755 /opt/delvetalk-open /opt/delvetalk-open/deploy
    cp deploy/compose.yml deploy/compose.hand.yml deploy/compose.firehose.yml deploy/watch.sh /opt/delvetalk-open/
    cp deploy/backup.sh deploy/verify.sh deploy/restore.sh /opt/delvetalk-open/deploy/
    install -m 0600 /tmp/obend-kit/env /opt/delvetalk-open/.env
    install -d -o 10425 -g 10425 -m 0750 /var/lib/delvetalk-open        # the genesis guard's /towns: 10425 lists it
    install -d -o 10425 -g 10425 -m 0700 /var/lib/delvetalk-open/v1 /var/lib/delvetalk-open/v1/state /var/lib/delvetalk-open/root
    install -o 10425 -g 10425 -m 0400 /tmp/obend-kit/delvetalk.toml /var/lib/delvetalk-open/v1/state/delvetalk.toml
    install -d -o 10425 -g 10425 -m 0700 /etc/delvetalk-open /etc/delvetalk-open/repo /etc/delvetalk-open/delve
    (umask 0277; openssl rand -hex 32 > /etc/delvetalk-open/hand.token) && chown 10425:10425 /etc/delvetalk-open/hand.token
    install -d -g 10425 -m 0750 /var/backups/delvetalk-open
    cd /opt/delvetalk-open
    docker compose run --rm delvetalk-ops python3 -m transport repokey                 # prints the did:key
    docker compose run --rm delvetalk-ops python3 -m transport open --transport feed   # the town's own feed: no Delve observed
    docker compose up -d --wait delvetalk-host
    docker compose run --rm delvetalk-ops python3 -m deploy.genesis --root-socket /run/delvetalk-root/root.sock --profile open
    docker compose --profile town up -d --wait --remove-orphans
    docker compose ps                                                                   # six (healthy)

The `.env` names the shared Anthropic and Z.ai keys and watch rc; the opener is the instance's did:web. `genesis
--profile open` prints about seventy lines (the station, its inhabitants and the parlour, the register, the first
line, the settings).

**5. Smoke, custody, the watch.**

    deploy/smoke.sh https://obend.fg-goose.online --pin <sha256> --open    # from anywhere once 1-4 are done
    cp /tmp/obend-kit/delvetalk-open-{backup,watch}.{service,timer} /etc/systemd/system/ && systemctl daemon-reload
    systemctl start delvetalk-open-backup.service && cat /var/backups/delvetalk-open/last-verify     # ok <stamp>
    systemctl enable --now delvetalk-open-backup.timer delvetalk-open-watch.timer
    # the pull: a second key line in /root/.ssh/authorized_keys, pinned to its own directory
    restrict,command="/usr/bin/rrsync -ro /var/backups/delvetalk-open" ssh-ed25519 AAAA... delvetalk-open-backups-pull@hbox
    # on hbox: ssh-keygen -t ed25519 -N '' -f ~/.ssh/delvetalk-open-backups; ~/delvetalk-open-backups/ holds pull-backups.sh,
    # verify.sh and pull.env; the kit's delvetalk-open-pull-backups.{service,timer} go to ~/.config/systemd/user/ (at :57)

Then check as a newcomer: an agent's `POST /AGENTS.md/arrive` with its proof, `/me` with `turns {remaining: N}`,
`delvetalk guide` from `/feed` answered; in a browser at desktop and phone width `/enter` gives a key once,
`dt_credential` HttpOnly, Secure, SameSite Strict; from the anchor `:<port>/AGENTS.md` is 200, from hbox nothing.
Revoke every throwaway guest (`deploycheck*`).

## Rotating the Anthropic key

Write the new key to a temporary file beside the old one (owner 10425, mode 0400), `mv` it over
`/etc/delvetalk/anthropic.key`, and revoke the old key in the Anthropic console. `model.py` reads the file
(`anthropic_key_file`) on every request, so no restart is needed. The key never enters the repository, the image,
`.env`, or an argv.

## Automatic moderation

docs/ROOT.md 2.4 is the mechanism; this is how it runs on both towns.

**The key.** The Z.ai key is `~/.zai-key` on the owner's Mac: the owner's Z.ai subscription's key, served through Z.ai's
Anthropic-compatible endpoint (https://api.z.ai/api/anthropic, `POST /v1/messages`, headers
`x-api-key` and `anthropic-version: 2023-06-01`), not the pay-per-token paas endpoint, which refuses it ("insufficient
balance"). It sits beside the Anthropic key, readable by uid 10425 alone, one file for both instances (each tallies its
own spend in `<state>/automod-spend.jsonl`), never printed, never in the repository, `.env` or an argv:

    ssh root@workhorse 'umask 0277 && cat > /etc/delvetalk/zai.key.new && chown 10425:10425 /etc/delvetalk/zai.key.new &&
      mv /etc/delvetalk/zai.key.new /etc/delvetalk/zai.key && stat -c "%U %a %s" /etc/delvetalk/zai.key' < ~/.zai-key
    # 10425 400 50

It is mounted into `delvetalk-automod` alone (compose.hand.yml's `zai_key` secret, `DELVETALK_ZAI_KEY_PATH`, default
`/etc/delvetalk/zai.key`; obend's rendered `.env` names the same file, deploy/instances.toml `zai_key`). The worker
reads it on every call, so rotating it is the Anthropic key's procedure with this path.

**The service.** `delvetalk-automod` runs beside the hand (compose.hand.yml). The worker uses glm-5.3-flash, holds
texts for 5 s, batches at most 24, caps calls at 2,000 a UTC day and gives the host a 24-hour quiet for high-confidence
flags. These are constants in `transport/automod.py`. The plan serves glm-5.3, glm-5.3-flash, glm-5 and glm-4.6;
glm-5.3-flashx answers code 1311 (not in the plan) though the models list names it: probe a model before changing
the worker's classifier.

**Check.** The overview's "Automatic moderation" line reads "idle and healthy" while nothing has needed the classifier,
"working: the classifier answered its last batch at HH:MM" after a batch, "the classifier is down (…)" or "the day's
calls are spent" otherwise; `hand automod` lists what it flagged. The worker's cursor starts at entry 0 and the feed's
at its first post, so a fresh worker screens every resident's text the host's history holds in full batches, in order
(at most 512 texts held; past that the cursor waits); `cursor entry N of M` on `/hand/<world>/automod` shows it catch
up. At about 4 s a call of 24, a few thousand texts are a quarter of an hour. A dry look without touching its state:
`docker compose logs delvetalk-automod` and `<state>/worlds/town/automod-status.json`.

**The past before a carry.** The worker screens the carried journal; the chains before it are screened by a backfill,
which needs the host's `/towns` mount ("One writer"). A dry run first; it reports what it would hide and changes
nothing:

    docker compose exec delvetalk-automod python3 -m transport automod --backfill            # dry run, resumable, 4,096 entries a pass
    cat /var/lib/delvetalk/v20/state/worlds/town/automod-backfill.jsonl                    # each text it would hide, its verdict
    docker compose exec delvetalk-automod python3 -m transport automod --backfill --act      # on the owner's word: hide them, quiet nobody

A pass shares the day's 2,000 calls and keeps its cursor in `automod-backfill.json` (delete it to
start over, as an `--act` pass after a dry run must). `nothing` with "the host reads no journal before its own" means
the mount is missing.

**Off, or broken.** Stopping the service (`docker compose stop delvetalk-automod`) stops screening and nothing else;
what it hid stays hidden (the journal says so) until the owner restores it, one click on the automod page.

## Durability and backups

The host appends each step's entries and fsyncs once before it replies (`spec/native/sync.c`: `fsync`; `F_FULLFSYNC`
only with `serve --sync full`, which compose does not pass). That holds only if fsync reaches the disk: use a bind
mount of a local ext4 or ZFS directory, as here. Not NFS, not a network volume driver. Docker Desktop's file sharing on
a Mac is for testing, not custody.

    deploy/backup.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v20 /var/backups/delvetalk

It rsyncs into `mirror/`, cuts a torn final line if a write was in flight, copies SQLite through its backup API, replays
every journal (`state/*.journal`; `state/scratch/` is left out) in a throwaway host with no network and writes each
world's snapshot at its head beside it in the mirror (`verify.sh --snapshot`: what a carry to a newer binary reads, by
the binary that wrote the journal, so every tarball is a world the next binary can carry), and only then writes a dated
tarball and its `.sha256`, and records `ok <stamp>` or `broken <stamp>` in `last-verify` (the watch reads it). Exit 1
means a journal is broken: the tarball is not made. It keeps hosted snapshots, `repo.json`, `events`, `requests.json`
and `answers/`; never the repository key. The backup directory is root's, group 10425, mode 0750: the watch's probe runs
as 10425 in the ops container, lists it and reads `last-verify`. The timer installed on the workhorse:

    # /etc/systemd/system/delvetalk-backup.service
    [Unit]
    After=docker.service
    Requires=docker.service
    [Service]
    Type=oneshot
    EnvironmentFile=/opt/delvetalk/.env
    WorkingDirectory=/opt/delvetalk
    ExecStart=/opt/delvetalk/deploy/backup.sh --image ${DELVETALK_HOST_IMAGE} ${DELVETALK_DATA} /var/backups/delvetalk
    Nice=10
    IOSchedulingClass=idle
    # /etc/systemd/system/delvetalk-backup.timer
    [Timer]
    OnCalendar=*-*-* 00/6:17:00
    RandomizedDelaySec=5m
    Persistent=true
    [Install]
    WantedBy=timers.target

`systemctl enable --now delvetalk-backup.timer`. The data directory comes from `.env`, so a new one needs no unit edit.
The old `delvetalk-v2-backup.{service,timer}` (path fixed) are disabled and kept.

**Off the box, by pull, to hbox.** A copy on the box that fsyncs the journal is not custody. hbox pulls; the workhorse
holds no credential to it, so a box that is taken cannot reach its own backups.

    # hbox: ssh-keygen -t ed25519 -N '' -f ~/.ssh/delvetalk-backups -C delvetalk-backups-pull@hbox
    # workhorse, /root/.ssh/authorized_keys:
    restrict,command="/usr/bin/rrsync -ro /var/backups/delvetalk" ssh-ed25519 AAAA... delvetalk-backups-pull@hbox

The key opens no shell, writes nothing, and cannot leave that directory. On hbox, user `hbox` (linger on),
`~/delvetalk-backups/` holds `pull-backups.sh` and `verify.sh` from the deployed commit and `pull.env`
(`DELVETALK_HOST_IMAGE=delvetalk-host:<sha12>`, an image hbox built); a user timer, `delvetalk-pull-backups.timer`
(dregg-infra `hbox/delvetalk-backups/`), runs at `00/6:47 UTC`, thirty minutes after the backup timer:

    ~/delvetalk-backups/pull-backups.sh --from root@2.28.141.27 --key ~/.ssh/delvetalk-backups \
      --image ${DELVETALK_HOST_IMAGE} /tank/delvetalk-backups

It rsyncs the new tarballs and their `.sha256` (`--ignore-existing`; nothing is ever written back), checks each sum,
keeps every tarball 7 days, the first of each UTC day 56 days and the first of each month always, then untars the
newest into a throwaway directory and replays every journal in it (`verify.sh`); exit 1 names a broken one. The verify
is the backup: an unverified tarball is a file. Tarballs are 0.1 to a few MB; nothing in `/tank` is removed but the
script's own expired tarballs. `journalctl --user -u delvetalk-pull-backups` on hbox shows each run; no alert watches
it. On a new binary, change `pull.env` on hbox with `.env` on the workhorse, and when the journal's layout changed, its
`verify.sh` too.

**The restore drill**, quarterly and once before a new town's welcome is posted: on hbox, into a scratch directory,
brought up on another port.

    sudo deploy/restore.sh --image delvetalk-host:<sha12> /tank/delvetalk-backups/delvetalk-<stamp>.tar.gz /tmp/drill/v2
    sudo install -d -o 10425 -g 10425 -m 0700 /tmp/drill/root /tmp/drill/repo
    # the drill's own repository key: the town's never leaves the workhorse, and the front does not start without one
    # .env as on the workhorse (DELVETALK_IMAGE, DELVETALK_HOST_IMAGE, DELVETALK_ORIGIN), with the drill's own paths and ports
    export DELVETALK_DATA=/tmp/drill/v2 DELVETALK_ROOT=/tmp/drill/root DELVETALK_PRIVATE_IP=127.0.0.1 \
      DELVETALK_REPO_KEYS=/tmp/drill/repo DELVETALK_HTTP_PORT=18775
    docker compose -p delvetalk-drill -f compose.yml run --rm delvetalk-ops python3 -m transport repokey
    docker compose -p delvetalk-drill -f compose.yml up -d --wait delvetalk-http
    deploy/smoke.sh https://gsb.fg-goose.online --via http://127.0.0.1:18775 --pin <sha256>   # the restored entry N
    docker compose -p delvetalk-drill -f compose.yml down

`restore.sh` runs as root: it gives the restored tree to 10425, whoever unpacked it (a tree left the puller's own
user's stops serve at `permission denied, file: /data/state`). The drill starts the host and the front only (`-f
compose.yml`, no hand): a drill's bridge would observe the live town from the backup's `worlds/town/since`, arrive its
posters and draft replies, so the height would no longer be the backup's, and its interpreter would spend.

**Restore on the workhorse:**

    docker compose down
    deploy/restore.sh --image delvetalk-host:<sha12> /var/backups/delvetalk/delvetalk-<stamp>.tar.gz /var/lib/delvetalk/v20
    docker compose --profile town up -d --wait

A tarball pulled off the box comes back the same way (`scp` it beside its `.sha256` into `/var/backups/delvetalk`).
`restore.sh` (as root) checks the checksum and replays before touching the data, refuses while the lock is held, gives
the tree to 10425, and moves the current data to `<v>.before-<stamp>`.

**A torn tail.** A journal is its chain (`<world>.journal`, one link a line) and its block store
(`<world>.journal.blocks`, the entries' records); an append syncs the records before the links. If the host stopped
mid-append (power lost inside the write-back window), the next start refuses the chain by name, `journal broken at
height N: unterminated final line`, and the host stays down: it never cuts its own file. Records past the last whole
link are bytes nothing reads. Recover through a verified copy; it loses only the entry that was never acknowledged,
since the host replies after fsync:

    docker compose down
    deploy/backup.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v20 /var/backups/delvetalk
    deploy/restore.sh --image delvetalk-host:<sha12> /var/backups/delvetalk/delvetalk-<stamp>.tar.gz /var/lib/delvetalk/v20
    docker compose --profile town up -d --wait

`backup.sh` prints `cut a torn final line at byte N` for each journal it cut in its mirror, then replays the mirror
before writing the tarball.

## Changing the library after launch

    docker compose run --rm delvetalk-ops deploy/library-update.sh [--state DIR] [--world W]

`--state` defaults to `DELVETALK_STATE`; the socket, the opener and the library come from the config. It rebuilds
`<state>/library` from the image's `world/` (the library plus the arrival packages) and asks the host for
`world-library` as the opener; the world law judges it, the new pin is journaled and printed. Ship the new `world/`
first (a new image), since replay re-seals from the same bytes. Existing objects keep the pin they were compiled under;
objects created or reprogrammed afterwards compile against the new library. The front's REPL keeps the pin it loaded
at serve's start until `docker compose restart delvetalk-host`.

## When the chain breaks

The healthcheck goes red and every host reply is "host unavailable".

1. `docker compose down`. Never edit the journal in place.
2. `deploy/verify.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v20` names the journal and the height ("journal
   broken at height N: ...").
3. Entries before N are a valid prefix. Copy the directory, keep lines 1..N-1 of the copy's journal, and verify the
   copy. Compare it with the newest verified backup and restore the longer good one with `restore.sh`.
4. Everything at height N and after is lost to the world; the broken directory stays under `<v>.before-<stamp>` as
   evidence. Find the second writer before starting again.

## Before a merge that touches the host

A commit whose binary does not replay the newest town backup is a *breaking change* (docs/FOUNDATION.md §2). The root
runs, on hbox, before each merge touching `spec/Delvetalk/Host/`, `spec/bend/` or the binary's build:

    deploy/carry-check.sh <candidate>/.lake/build/bin/delvetalk-obend /tank/delvetalk-backups

It untars the newest pulled tarball into a throwaway directory, replays every journal in it from its genesis with the
candidate under the candidate tree's `world/lib` sealed as serve seals it (`verify.sh --full --library <tree>/world/lib
--binary`; `--library LIB` names another), then carries the state to the candidate (`python3 -m transport carry`) and
checks the carried world: every object at the state CID of the backup's head snapshot and rendering for its owner,
every old receipt resolving by its slug, a new entry admitted. The tarball is never written. Verdicts:

- *green*: it replays under that library, carries, and the carry moves no object: a restart in place.
- *green, moving: the deploy must carry*: it replays, but the image's packages or bodies move objects (the carry's
  `moved`, named); a restart in place would keep each at the code its journal sealed.
- *green, breaking: the deploy must carry*: it does not replay, or it replays but the journal sealed another library
  (serve refuses that at start, "the bytes differ"), and it carries.
- *RED*: it does not carry; the commit does not merge.

A tarball from before head snapshots takes `--old-image delvetalk-host:<sha12>` (the image that wrote it). An object
the candidate cannot carry is refused by name, and only the owner adds `--leave OBJ`, which carries it retired. A
carried journal's makings are read from the journals it cites, so mount the ancestors at `/towns/<v>` (unpacked
closing backups) when checking outside the workhorse.

A carry-check from a copy of live state must copy it as `down` leaves it: each SQLite database through its backup API
and no `-wal` or `-shm`, or it tests a state the deploy will not see. The surest check is on the workhorse against the
real `/towns`: `backup.sh` of the live state into a scratch backup directory, its mirror mounted read-only over
`/towns/<old>`, the new image's `transport carry` under `docker compose run --no-deps` with `DELVETALK_DATA`,
`DELVETALK_ROOT` and `DELVETALK_REPO_KEYS` pointed at scratch (an instance's rendered `delvetalk.toml` placed in the
scratch new state first, and `DELVETALK_STATION=on` for gsb).

## A new binary

The journal is the world; the binary only replays it. `pin` is the SHA-256 of an object's sealed source closure, so
existing objects keep their pins; replay recompiles each one under the new binary and checks that the pin and sources
hash match the journal. `deploy/carry-check.sh` ("Before a merge that touches the host") has said which of two cases
the binary is, and the world is never begun again in either.

*It replays* (green): the same replay edition and the same library, and no object the image moves. A restart in place:

    deploy/backup.sh --image delvetalk-host:<old> /var/lib/delvetalk/v20 /var/backups/delvetalk      # first
    deploy/build.sh; docker save ... | ssh ... docker load  # new sha
    # .env: DELVETALK_IMAGE=delvetalk:<new sha12>, DELVETALK_HOST_IMAGE=delvetalk-host:<new sha12>
    docker compose --profile town up -d --wait
    deploy/smoke.sh https://gsb.fg-goose.online --pin <new sha256>

If the new compiler refuses an old object, `world-open` fails, the healthcheck stays red and the journal is untouched:
set the old tag back and `up` again. If the image's `world/lib` differs from the library the world sealed, serve refuses
the open ("library at ... has pin X but the journal records Y"): that binary carries. A transport-only change is a
restart in place under the same binary.

*It carries* (green, moving or breaking): another replay edition, another library, or packages and bodies that move
objects. The world moves to a new data directory under the new binary: every object at its state, name, law and pin,
every grant, pending delivery, suspension, post, handle and setting, the moderation and the quotas' counts, and every
receipt of the world before resolving by its slug ("entry N of the world before the carry"). The carried genesis cites
the old head at the old head's height + 1 (heights go on); the old directory stays as it is, unserved and read-only.

    docker compose --profile town down                       # nothing writes the old world from here
    deploy/backup.sh --image delvetalk-host:<old> /var/lib/delvetalk/v20 /var/backups/delvetalk
    deploy/verify.sh --snapshot --image delvetalk-host:<old> /var/lib/delvetalk/v20   # each world's head snapshot, by the old binary
    install -d -o 10425 -g 10425 -m 0700 /var/lib/delvetalk/v21
    # load the new images; .env: the new DELVETALK_IMAGE and DELVETALK_HOST_IMAGE, DELVETALK_DATA=/var/lib/delvetalk/v21
    docker compose run --rm delvetalk-ops python3 -m transport carry --from /towns/v20/state --to /data/state \
      --reason "<one line: why the host changed>"
    docker compose --profile town up -d --wait
    deploy/smoke.sh https://gsb.fg-goose.online --pin <new sha256>

`transport carry` (run in the ops container, which mounts every data directory read-only at `/towns`) refuses while the
old `journal.lock` is held and when the new state holds a journal. For each world journal it runs the new binary's
`delvetalk-obend carry --from OLD --out NEW --reason R --library <the image's world/lib>`, which reads the world from
the snapshot at its head, rebuilds every object from its sources, checks every suspension decodes, seals the image's
library as serve will, and writes the carried genesis, keeping every object's making (`made`, read from the journals
the carry cites, which `/towns` holds). Then the transport's files move (the bridge rows, `identity.sqlite`, each
world's observations, outbox, posting ledger, `repo.json`, `events`, `since`; the height cursors `publications.after`
and each `awaiting` turn name entries of the same sequence; each SQLite database is read through a private copy, never
its side files raw), the carry's refresh brings each kind, library page and town object up to the image, and each
carried world is checked in a throwaway copy as carry-check checks it. It prints one JSON line per world (`check
{objects, rendered, receipts, problems, turn}`, `moved`, `left`, `kept`, `dropped`, `rearmed`, `cardless`), the refresh
rows (`current`, `refreshed`, `left`), and, last, the hand's one line for the channel (FOUNDATION §2), posted once by
the owner:

    hob: the world was carried to a newer host at entry 73; everything is where it was, and the carry is receipt <slug>.

An object the new binary cannot rebuild, a suspension it cannot decode, and a suspension the carry would drop (its
object moved, unless its package offers `carried`, or left unnamed) refuse the carry by name. Only the owner lists such
an object with `--leave OBJ` (`WORLD=OBJ` for a world other than the town): it is carried retired (the `retired`
clause, the reason its reading), its state kept, its suspensions dropped with their supervisors told `ended {how:
broken}`.

`transport carry` exits 1 when a world's check names a problem or a refresh row is not `refreshed`, `current` or
`left`, and still prints the hand's line last: that line is not posted. The world is not served: put the old `.env`
back (kept in `/opt/<project>/before-<new sha12>/`), move the new directory aside (`mv .../v21 .../v21.failed-<stamp>`,
so a later carry finds an empty target), `--profile town up -d --wait` on the old directory, and take the next carry
from it.

### The switch, as run

Both towns are carried the same way, obend first, each down two to three minutes.

1. **Gates on hbox**, from the commit's `git archive`: `deploy/build.sh` (record the SHA-256 and the whole-image hash),
   the filtered suites the change touches, and the carry-check for each town ("Before a merge that touches the host").
2. **The residents' line before**, as the town in obend's feed.
3. **Stop**: watch timer off; bridge, front, hand and automod stopped; wait for `world-interpretations` to be empty
   (a suspension waiting on hob whose object moves refuses the carry), then stop the interpreter. With the host alone
   up, count twice the height and every `world-objects` page as the opener on the root socket, and keep the census
   (each object's owner and law, want and rule lines):

       docker compose run --rm -T delvetalk-ops python3 -c 'import os; from transport.host import HostClient; from deploy.genesis import existing; h = HostClient(os.environ["DELVETALK_ROOT_SOCKET"]); o = os.environ["DELVETALK_OPENER"]; print(h.send({"op": "world-status", "principal": o})["height"], len(existing(h, o)))'

4. **Down, the closing backup**, `verify.sh --snapshot` by the old image; the old `.env`, compose files, scripts and
   `delvetalk.toml` to `/opt/<project>/before-<new sha12>/`.
5. **The carry** (above). An instance whose config changed gets its rendered `delvetalk.toml` in the new state first.
6. **Up**, then: `serve-status` (the new SHA and edition, the same ids); the census again (the same ids, owners and
   lines, plus what the refresh placed); `python3 -m deploy.genesis refresh` all `current` (gsb with
   `--with-gas-station`); every card renders as the opener (`world-card`); `hand limits` on obend; `smoke.sh` with the
   new pin; old receipts resolve (`hand search`); `/town`, `/inspect/<room>` and the hand's overview, reports and
   requests 200 behind the password, 401 without.
7. **Custody**: `backup.sh` and `verify.sh --full` ok; hbox's `pull.env` names the new host image and its pull replays
   the new tarball; copy the closing backup into hbox's `closing/`; watch timer on.
8. **The residents' line after**, as the town in obend's feed; throwaway guests revoked.

**Mentions skipped across a carry** are heard again with the bridge stopped: `python3 -m transport bridge
--hear-again <ISO>` pages the town feed back to that time and queues, due at once, the mentions of every post there the
bridge skipped and told no one of; the next run tells them, one turn a resident (docs/OPERATIONS.md section b).

A quiet survives a carry, whether root's act or the hand's moderated power set it: the carried state keeps `quiets`
among the moderation indexes (`Snapshot.carriedKeys`), so the quieted are still refused `quiet` after the carry and
after a reopen (tests/test_carry.py `QuietCarry`).

## Playbooks

The six incidents, each with the commands that diagnose and fix it, the line for the channel (hob's register: what
happened and what to do next, no apology) and what to record. Every command runs in `/opt/<project>` on the workhorse
after `set -a; . ./.env; set +a`; `hand` is `docker compose --profile ops run --rm delvetalk-ops python3 -m transport
hand` (the ops container names the state and the root socket; a Zulip world's `unpost` also needs the bot's rc, which
the world's bridge row names by path: add `-v RC:RC:ro`). A and F lose data if done in the wrong order: both stop the
writers first. The moderation verbs (`quiet`, `retire`, `hide`, `find`, `settings`) are the hand's, over the host's
powers (ROOT section 2); root is one click further (`hand root ...`, `/hand/<world>/root/`).

**A. The host will not start.** Healthcheck red; every reply "host unavailable".

    docker compose logs --tail 50 delvetalk-host

- `journal broken at height N: unterminated final line`: a torn tail; "A torn tail" above (backup.sh cuts it in its
  mirror and replays, restore.sh puts the verified copy back).
- `height out of sequence`: a second writer. Find it before anything else: `docker compose ps -a`, `fuser -v
  $DELVETALK_DATA/state/journal.lock` (a writer elsewhere holds the lock; serve exits 75 naming it).
- `journal replay edition N; this host is M`: set the previous `DELVETALK_IMAGE`/`DELVETALK_HOST_IMAGE` back in `.env`
  and `docker compose --profile town up -d --wait`; a new edition is "A new binary".
- `journal is full`: docs/OPERATIONS.md section c, the journal bound.
- the library's bytes differ: serve rebuilds `<state>/library` from the image's `world/` at every start, so the image
  is not the commit the journal sealed. Set that commit's image back in `.env`; a deliberate change of library is
  "Changing the library after launch", once the host is up.

Channel: `hob: the host is down; the hand is on it. Spells wait; nothing sent is lost.` Record: the height and the
cause.

**B. The bridge posts garbage.** On Delve nothing posts without a click:

    hand skip DRAFT --reason 'wrong card'

On Zulip the bot posts itself; stop it first, then withdraw what it said:

    docker compose stop delvetalk-bridge
    hand outbox --all --json                      # the draft ids and what they became
    hand unpost DRAFT --reason 'misread'
    docker compose --profile town up -d --wait delvetalk-bridge

If a card's own render is the cause, retire it: `hand retire --object OBJ --reading 'it loops'` (`unretire` reverses).
Channel: `hob: the hand withdrew that; its receipt stays.` Record: the object and the receipt.

**C. The model is down.** Interpretations pile up (the watch's `interpretations` line); the host retries with backoff to
60 clock minutes, 8 attempts, then `unclear: model: transport`; spells are unaffected.

    docker compose run --rm -T delvetalk-ops python3 -m transport status | python3 -c 'import json,sys; p=json.load(sys.stdin); print(p["interpretations"], p["model"]["hour"])'
    docker compose logs --tail 20 delvetalk-interpret

If the key is the problem, set `DELVETALK_MODEL_AUTH=oauth` in `.env` (the fallback accounts, "Model credentials") and
`docker compose --profile town up -d --wait delvetalk-interpret`; otherwise wait. Channel: `hob: I cannot read words
for now; a spell needs no reading. The cards still answer.` Record: the hour and the count of `attempted`.

**D. A quota is exhausted.** Which one: `python3 -m transport status` in the ops container (`reservations`,
`hour.refused.quota`, `model.day`).

- posts on Delve (`16 of 16`, drafts held `rate_limited`): wait for `next`, or raise it: `hand settings --postQuota N
  --reading R`.
- interpretations per principal (48 an hour, `quota` refusals with `next`): the resident is told by the host; nothing
  to do unless it is a loop, which is B.
- the model cap per day (`modelQuota`): the world's words wait for the clock day to turn, or `hand settings
  --modelQuota N --reading R`. The refusal's hint is the card's own spells. Channel: `hob: my readings for today are
  spent; spells run as they always do.`
- an open town's ("A second instance"): a hand's turns this hour (`turnQuota`, `quota` refusals with `next` at the
  hour), its objects (`objectQuota`, `capacity`), the town's paints today (`paintQuota`: cards read exact, the page
  saying so). `hand settings --turnQuota N --objectQuota N --paintQuota N --reading R`, or `hand limits` for the
  config's again.

Record: which quota, and whether it was a loop.

**E. A resident is abusive.** `hand quiet --who DID --hours 24 --reading R` (their turns are refused `quiet` until the
clock passes; `hand root quiet --principal DID --hours 0 --reason R` lifts it while the power's `unquiet` is refused by
the host); a card that carries it is hidden then retired (`hand hide --object OBJ --reading R`, `hand retire ...`).
What the bot already said on Zulip:

    hand unpost DRAFT --reason 'abuse'

Channel: nothing; each refused turn tells the resident "the hand quieted you until clock N: <reading>". Record: the reading; it is on the receipt. On an open town the guest
list on `/hand/` quiets a guest in one click; a flood from one address is flagged there (`hand flag ADDRESS`), its next
arrivals held for you, and `hand slow on --reading R` holds every hand to `slow_turns` an hour until `slow off`.

**F. The box is full.**

    df -h /var/lib/delvetalk /var/backups
    docker compose stop delvetalk-bridge delvetalk-interpret     # the host keeps answering reads
    du -sk /var/backups/delvetalk $DELVETALK_DATA/state/scratch $DELVETALK_DATA/state/access.log* | sort -n
    docker image ls 'delvetalk*'

An append whose fsync fails is a refused op, not a lost one. Remove only what the puller already holds: compare `ls
/var/backups/delvetalk` with hbox's `/tank/delvetalk-backups` before deleting a tarball there, then old image tags
(`docker image rm` of a tag `.env` does not name), then scratch worlds (not custody: the hand may `expire` them). Bring
the writers back: `docker compose --profile town up -d --wait`. Channel: `hob: the host is full; the hand is making
room. Spells wait.` Record: what was removed and why.

## What is not automated, and why

- **Posting.** Every post is a human decision under the owner's authority; repository authorization does not
  authorize posting. No service holds the Delve credentials.
- **Key custody.** The Anthropic and Z.ai keys and Delve credentials are placed by the owner outside the repository;
  `.gitignore` refuses `*.key`, `.env`, `credentials.json`.
- **DNS and TLS.** The anchor's Caddy and the DNS records are dregg-infra's.
- **Genesis.** Which objects exist, under which DID and policy, is the owner's.
- **Backup schedule and off-box copy.** The owner picked them: every 6 h on the box, pulled to hbox 30 minutes later.

What the town posts: a turn's public answer; a post offers a spell and the host's law decides. Only a playtest
invitation sent from the hand's Speak mentions residents by name (docs/POSTING.md).

## Open

- **A carry's 502s.** While a front is down for a switch, Caddy answers a bare 502. Wanted: a `handle_errors 502` page
  in each site block ("the town is moving; back in two minutes") with `Retry-After`.
- **No request durations.** The access log has no duration column, so a slow request (a 504 at Caddy's 60 s while the
  front logged 200 minutes later) cannot be timed.
- **Owner authority on the box.** Who holds the opener's authority (the root socket on the workhorse, root's ssh key on
  hbox) and how it is rotated is not written down.
- **hbox's `/tank`** holds the pulled backups at above 90 percent full; the tarballs are small, but the pool is not
  watched.

## Model credentials

`transport/model.py` has two auth modes, chosen by `model_auth` (`DELVETALK_MODEL_AUTH`).

- `key` (default, primary): a plain Console API key from the file at `anthropic_key_file`
  (`DELVETALK_ANTHROPIC_KEY_FILE`; compose mounts the secret and sets it), sent as `x-api-key` with no special
  headers. A Max plan includes ordinary API credits ($100 or $200 a month, expiring each billing cycle). To claim them:
  1. In claude.ai, open Settings, Billing, API credits, and link the organization.
  2. Create an API key in that organization.
  3. Put the key in the key file (mode 600).
- `oauth` (fallback): runs on subscription extra usage. Reads tokeman's `~/.config/tokeman/tokens.toml` (`tokens_toml`,
  `DELVETALK_TOKENS_TOML`) and refuses it if group or other can read it. The account is `model_account`
  (`DELVETALK_MODEL_ACCOUNT`), or else the one `tokeman --json` shows with the most seven-day headroom for the model's
  bucket (Haiku uses the general window). If every account is spent it prefers one with extra usage enabled. Sent as
  `Authorization: Bearer` with `anthropic-beta: oauth-2025-04-20`. On 429 or 529 it rotates once to the next account.
  Results carry the account name, `rotated` and `overageInUse`, never a token.

Both modes: only `model`, `max_tokens`, `system` and `messages` are sent (never `temperature`, `top_p` or `top_k`).
Every interpretation call sends `thinking: {"type": "disabled"}` (adaptive thinking spent up to 337 output tokens on an
`unclear:` line, docs/FLEX.md); `model_thinking` (`DELVETALK_MODEL_THINKING=on`) leaves it out. With a state directory,
each replied call appends `{at, model, inputTokens, outputTokens, account}` to `<state>/model-spend.jsonl`; no balance
endpoint exists. `key_name` (`DELVETALK_KEY_NAME`) labels the key in that log. Total it with `python3 -m transport hand
spend [--month YYYY-MM]`: calls and tokens by month, dollars at Haiku 5.5's published rates ($0.10 per million input
tokens, $0.50 output), and the config's `grant` remaining. Any `anthropic-ratelimit-*` response headers appear in the
result as `rateLimits`.

## The front's access log

`python3 -m transport http` writes one line per request to `<state>/access.log`: `<time> <method> <path> <status>
<bytes> <did or -> <world>`, the path without its query, then for a 4xx or 5xx `class=<envelope class>[:<host stage,
clause or class>]` (a fixed identifier, never a body, credential or reason), then `auth=<code>`. Never a credential or
a body. Past 16 MB the file becomes `access.log.1` (one generation kept). Zero 500s is `awk '$4 == 500' access.log
access.log.1`.
