# Deploying DelveTalk

`https://gsb.fg-goose.online` is the HTTP front (`python3 -m transport http`) on the
workhorse, behind native Caddy on the anchor. Everything in `deploy/` is an
artifact the owner runs; nothing here deploys itself.

| File | What |
| --- | --- |
| `deploy/Dockerfile.host` | the host binary for linux/amd64; final image is the binary and glibc |
| `deploy/Dockerfile.transport` | python 3.13 slim + the binary + `transport/`, `world/`, the guide |
| `deploy/build.sh` | builds both, prints the binary's SHA-256, writes `deploy/out/host.sha256` |
| `deploy/compose.yml` | `delvetalk-host` (`delvetalk-obend serve`), `delvetalk-http`, `delvetalk-bridge`; `delvetalk-interpret` (profile `town`); `delvetalk-ops` |
| `deploy/compose.hand.yml` | laid over compose.yml: `delvetalk-hand`, the owner's console on its own loopback port, with the root socket and the Delve credentials directory |
| `deploy/compose.firehose.yml` | laid over compose.yml when an instance publishes its firehose ("Firehose") |
| `deploy/instances.toml`, `deploy/instance.py` | each instance on the box, and its kit rendered from its name ("A second instance") |
| `deploy/seed.py` | `world-create` of one object from `world/` |
| `deploy/backup.sh`, `restore.sh`, `verify.sh` | journal custody |
| `deploy/smoke.sh` | the newcomer's journey against an origin |

The world's opener is the town's own principal (docs/GENESIS.md "The town"): config `opener`, by default the origin's
did:web (`did:web:gsb.fg-goose.online`), which `transport serve` hands to serve's `--opener`. The live town's journal
names ember's DID, `did:plc:6amo7col5h4ciq2gpm5eur7b`, as its opener, so its `.env` keeps `DELVETALK_OPENER` set to
that DID (serve refuses settings that differ from the journal's); the host shows it as the town all the same. Only the opener may create objects with
a named owner at genesis, change the library, and make the newcomers' objects that `world-arrive` creates. The opener
speaks on the root socket only (below): an op naming the opener on the public socket is refused, "the opener speaks on
the root socket", so the opener's authority is a mount, not a token (docs/ROOT.md section 1.4).

## One writer

Two host processes on one journal write two entries at the same height and break
the chain ("journal broken at height N: height out of sequence"). So exactly one
process, `delvetalk-host` (`delvetalk-obend serve`, HOST-HANDOFF 5.125), opens the journals. It holds
`/data/state/journal.lock` for its life (exit 75, "refusing to start a second writer", if taken), keeps every world's
journal in `/data/state` (`town.journal`; another world's `<name>.journal`, opened at the first op that names it with
`world: <name>`; a principal's scratch worlds in `scratch/<principal>/<name>.journal`, addressed by `world: scratch/<name>` beside `principal`, are not custody: backups leave them out and verification skips them), and serves the front, the bridge, the
interpreter and `post --object` over `/data/state/host.sock` (mode 0600). The opener's ops, `world-root` and the root
ops (`world-library`, `world-settings`, `world-fork`, `world-snapshot`) take the root socket,
`/run/delvetalk-root/root.sock` on the host directory `/var/lib/delvetalk/root` (`DELVETALK_ROOT`), mounted into
`delvetalk-host`, `delvetalk-ops` and the hand and into nothing else. At start serve rebuilds `<state>/library` from
`--library` (the image's `world/lib`) and `world/objects/Avatar.obend` (the package `world-arrive` creates
from) and seals it into each world at its first open (the opener may change it; a scratch world starts with it sealed), so packages
import `./Plan.obend` and the rest by name. Every world of the directory is opened at start and held (a held world is
its live state, not its journal), so a turn in one may read another's objects.
The other programs are clients (`transport/host.py`, 99 lines): stop, start or run them at any time without touching
the world.
The lock holds where one kernel sees the file: a local Linux
filesystem (measured on ext4). Docker Desktop's file sharing on a Mac does not
enforce it across containers (measured), so test the stack there on a named volume.

## Firehose

`transport http` runs `com.atproto.sync.subscribeRepos` on a separate TCP listener in the same
`delvetalk-http` process, with one selector thread for all sockets and production. `firehose_bind` defaults to
`127.0.0.1`, `firehose_port` to `0` (off). Enable it only with the world's signing key in `repo_keys`.
The listener is public through the edge; it requires no subscriber credential. Its durable log is
`/data/state/worlds/<world>/events`, kept in state backups and copied by carry alongside `repo.json` (REPO).

`deploy/compose.yml` publishes `delvetalk-http`'s HTTP port 8765 on the private address 10.10.1.10, and uses
Docker's default service network. The hand uses 8766. To enable the firehose, add this overlay for
`delvetalk-http` (its inherited HTTP settings, state/key mounts and HTTP port remain); it is
`deploy/compose.firehose.yml`, its port `DELVETALK_FIREHOSE_PORT` (8767), which an instance whose table says
`firehose = true` names in `COMPOSE_FILE` ("A second instance"):

```yaml
services:
  delvetalk-http:
    environment:
      DELVETALK_FIREHOSE_BIND: 0.0.0.0
      DELVETALK_FIREHOSE_PORT: "8767"
    ports:
      - "10.10.1.10:8767:8767/tcp"
```

Compose merges the environment mapping and port list. The 0.0.0.0 bind is inside the container; the
published port is on the workhorse's private network, reached by Caddy on the anchor. For a drill, change
both the setting and mapping to the same unused port. Add this route in the gsb site's Caddy block before
the general `reverse_proxy 10.10.1.10:8765` (the Caddyfile is outside this repository):

    reverse_proxy /xrpc/com.atproto.sync.subscribeRepos 10.10.1.10:8767

Caddy forwards the WebSocket upgrade. The HTTP front's same XRPC path answers 426 `UpgradeRequired`
with `Upgrade: websocket` when enabled, or 501 with `firehose_port` named when off. Do not send the
WebSocket route to port 8765: subscribers use 8767 and take no HTTP worker. Stop the front before carry
or state restoration so the event log is quiescent; restart reconciles missed heights with a head-only sync,
and a key rotation emits identity before sync. An unchanged restart adds no event.

## Public request participants

`requests` defaults to `false`; the bridge polls public request records only when the operator enables it.
`participants` defaults to the empty string and names explicit participant DIDs, space-separated, in
`<state>/delvetalk.toml` (`DELVETALK_PARTICIPANTS` overrides it). Both did:plc and hostname-level did:web are supported.
The registry unions this list with active repositories discovered at pds.delve.town and verified identity-table
claims, plus this world's hosted accounts in `State.hosted`. Hosted accounts supply documents and proof CARs
locally to the ordinary `requests.proven` verifier and do not consume the external-participant cap. Each external DID is read at its current document's `#atproto_pds`, through public-address-checked, pinned HTTPS.
No PDS write is made by the poller. The mirror has its own authorization and remains off.

Documents cache ten minutes; a proof verification failure refreshes once per participant per poll before refusal.
The poll reads at most 256 non-delve-PDS participants in sorted DID order and reports every overflow DID; unsupported
DIDs and unsafe PDS destinations are problems in the bridge step's `failed` output.

`<state>/worlds/<world>/requests.json` holds `{revs: {did: {pds, rev}}, refused: {uri: {cid, why}}}`. The revision skip
requires both PDS and revision to match. A migrated participant is scanned in full; consumed URIs and first proven
CIDs in `observe.sqlite`, refused records in `requests.json` and `answers/` remain intact. Backups retain all three.
Identity changes are observed at the next document refresh, at most ten minutes after the last fetch. Requests must
remain in the resident's repository until answered. ATPROTO §2 describes verification and discovery.

## Hosted account origins

The mapping and request repositories are built (ATPROTO §4, REPO); DNS and certificates are the owner's
ops step. Hosted account hosts route to the world's existing front, preserving Host, with no second Front
or listener. The account DID document's PDS endpoint is the same configured front origin. The front and
bridge share `<state>/worlds/<world>/hosted/`; neither provisions a second copy of an account elsewhere.
The request poller remains off unless `requests = true`; the mirror keeps its separate authorization.

For the deployed origin, add wildcard A/AAAA records pointing to the front's existing edge:

    *.guest.gsb.fg-goose.online.
    *.zulip.gsb.fg-goose.online.

For each configured Zulip realm, also publish its explicit account zone, for example:

    *.chat.example.zulip.gsb.fg-goose.online.

Caddy must obtain certificates by DNS-01 in the owner's Google Cloud DNS zone `fg-goose.online` and route
these hosts to the existing HTTP upstream. A TLS wildcard covers exactly one label: `*.zulip.gsb.fg-goose.online`
does **not** cover `42.chat.example.zulip.gsb.fg-goose.online`. Each realm needs its corresponding
`*.<realm>.zulip.gsb.fg-goose.online` certificate (or explicit account SANs); guests need
`*.guest.gsb.fg-goose.online`. Keep DNS credentials out of Git. Completion: HTTPS on each chosen account
hostname serves its matching DID document, and sync.getRecord verifies under its #atproto key. This lane
installs no records or certificates and starts no process.

Account k256 keys derive with HKDF-SHA256 from the world's town-key scalar and each hosted DID (ATPROTO §4).
Only public `<state>/worlds/<world>/hosted/<stem>.json` snapshots are written, including signing key identifiers
and rotation/migration epochs; the 0700 directory itself carries the flock. Guest stems are names and Zulip
stems are `<id>.<realm>.zulip`. `deploy/backup.sh` keeps hosted snapshots in
`/var/backups/delvetalk/mirror/` and `/var/backups/delvetalk/delvetalk-<stamp>.tar.gz`, then the pulled
`/tank/delvetalk-backups/` copies. Restore snapshots with the same operator-custodied
`/etc/delvetalk/repo/<world>.key` to reproduce every hosted key and signed head. Loss of that town key loses
every hosted key too. A box without it starts, but hosted routes and invitation acceptance refuse with
503 `RepoNotServed`; the invitation stays open. Legacy account keys/locks are removed after durable migration.
Migrate legacy state with the town key available before running the updated backup script: it no longer
filters legacy files, and a keyless front cannot migrate them. A state with no legacy store (v14, carried 2026-10-13)
has nothing to migrate: the front's first start provisions every accepted, unrevoked guest into
`<state>/hosted/<URL-encoded origin>/` (counter 0, no epoch) and logs nothing unless it skips one, so check the
directory listing before the first backup, not the log.

Remaining transport completion checks are in ATPROTO §4: a Zulip message written once as a public request
and consumed once, and reciprocal link records/document claims. Neither is built. Existing Zulip messages
remain observations under their Zulip principals; feed posts remain feed posts.

## Costs

The boundary between the Python programs and the host process, measured on hbox with `deploy/bench-boundary.py` (median
per-op round trip, 1,000 `world-status` ops and 200 Counter bumps, two runs):

| Path | `world-status` | Counter bump |
| --- | --- | --- |
| (a) serve's socket, a connection per op | 0.092 ms | 0.594 ms |
| (b) serve's socket, one persistent connection | 0.077 ms | 0.606 ms |
| (c) the raw pipe to a host process | 0.039 ms | 0.494 ms |

Measured 2026-10-11 on hbox with foundation's binary of 2026-10-10 (one run). Under `hostd.py` the same rows were 0.43, 0.21 and 0.13 ms
for `world-status` and 1.27, 1.03 and 0.87 ms for a bump: Python's dispatch and pipe are gone. `HostClient` keeps one
connection per thread, so production runs path (b).

## Prerequisites on the workhorse

- Docker with compose v2, as for `/opt/dregg-edge`; `rsync` and `python3` for backups.
- The data directory `DELVETALK_DATA`, `/var/lib/delvetalk/v15` since 2026-10-13 (fed71c47 with lane/deploy15 32c80591,
  replay edition 15), carried from `v14`, itself of `v13`, `v12` and `v11` ("A new binary"); `v11` is the third carry's,
  2026-10-12 (550c0478, replay edition 12), of `v10`, the second carry's (lane/refresh-fix b59b0186, edition 12, height 722 at the carry), itself of
  `v9`, the first carry's (16471891, edition 10, height 446), itself of `v8`, the owner's fresh minimal town of the same
  day (5db9aa79, edition 9, height 435); the worlds before stay unserved: edition 1 in `v2`, then b14df72e's `v3`,
  6cd1f491's `v4`, 89abbd8d's `v5`, 103837ce's `v6`, 7300d494's `v7` (height 2225), `v8`, `v9` and `v10`;
  `v10.failed-20261012T154705Z` is the refused first try of the second carry. Owner `10425:10425`, mode 0700 (the
  image's uid, next in the edge's series), with `state/` inside it made the same way. compose's default is `v11` too;
  `.env` names it anyway. On ext4 or ZFS, local disk: see "Durability".
- `/var/lib/delvetalk` itself is the old systemd units' (`delvetalk:delvetalk`, uid 987, mode 0700), and the ops
  container mounts it read-only at `/towns` as 10425, so 10425 must be able to list it: `setfacl -m u:10425:rx
  /var/lib/delvetalk` (set 2026-10-12). Without it genesis's no-wipe guard saw no town at all and ran over v7 as a
  first town, dropping the owner's word (the deploy of 5db9aa79; the guard now refuses a directory it cannot list).
- `/etc/delvetalk/anthropic.key`: the key alone, owner 10425, mode 0400.
- `/etc/delvetalk/repo/town.key`: the repository's signing key (docs/REPO.md "The key"), made at first start
  (below), owner 10425, mode 0400, in a directory owner 10425, mode 0700. Never printed, never in a backup tarball.
- The portal is `https://gsb.fg-goose.online` (config `origin`; `DELVETALK_ORIGIN` overrides it for every program, and `compose.yml` and `compose.hand.yml` set it for every
  service as `${DELVETALK_ORIGIN:-https://gsb.fg-goose.online}`, not a fixed string, from `.env`). The Caddy route for
  `gsb.fg-goose.online`, and the old `delvetalk.fg-goose.online` route, both proxy to `10.10.1.10:8765` until the town
  has moved; then the old one goes. The installed config is `/etc/caddy/Caddyfile` on the anchor (native Caddy, no
  checkout there; dregg-infra's `edge/anchor/Caddyfile` is its source and had drifted from it on 2026-10-10). Install as
  that file's header says: write `Caddyfile.new`, `caddy validate`, `mv`, `systemctl reload caddy`. Both names answer
  `respond @hand 404` for `path /hand /hand/*`, a belt only: the port Caddy proxies never serves the owner's console,
  which has its own listener on workhorse's loopback (below). Both cap bodies at 262144 bytes (since 2026-10-10); the
  deployed front's own `MAX_BODY` is still 65536 and refuses above that. The gsb route as installed:

      gsb.fg-goose.online {
      	import baseline_headers
      	encode zstd gzip
      	@hand path /hand /hand/*
      	respond @hand 404
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
 The old systemd
  units listen on that address: stop and disable `delvetalk-proxy.socket`,
  `delvetalk-proxy.service`, `delvetalk-portal.service`; keep
  `delvetalk-tick.timer` disabled. Their data under `/var/lib/delvetalk/` (`world`, `town-v1`, `forge-v1`, `clerk`,
  `operator-service`; there is no `agents` directory there) stays where it is.
- Log in with delve.town (`transport/oauth.py`) names the front by `origin`: the client id is
  `<origin>/oauth/client-metadata.json` and the callback `<origin>/oauth/callback`. The account's PDS fetches the
  document itself, so it must answer 200 `application/json` over HTTPS at exactly that URL (no redirect); Caddy needs
  nothing new, since the gsb route already proxies every path but `/hand`. A login started on another name is first
  sent to the origin's, where its one-time cookie lives. Check it after a deploy:
  `curl -s https://gsb.fg-goose.online/oauth/client-metadata.json` shows `client_id` equal to that URL. pds.delve.town
  is its own authorization server (PAR, PKCE S256, DPoP ES256, `client_id_metadata_document_supported`; checked
  2026-10-10). The image installs `cryptography` for ES256 from `deploy/requirements-transport.txt`, pinned by hash.
- :8765 answers the anchor (10.10.1.5) only: `trust_proxy` (set by compose for the front) believes the last `X-Forwarded-For` entry from whoever
  connects. The workhorse has no host firewall (no ufw, `nftables.service` disabled) and the Hetzner Cloud firewall
  filters public interfaces only, so `delvetalk-firewall.service` (dregg-infra `edge/delvetalk/delvetalk-firewall`,
  installed as `/usr/local/sbin/delvetalk-firewall`; after docker, `PartOf=docker.service`) owns two chains:
  `DELVETALK-FRONT`, jumped to from `DOCKER-USER`, returns new connections to 10.10.1.10:8765 from the anchor and drops
  every other source (the edge's and the default bridge's containers were the open path); `DELVETALK-LOCAL`, jumped to
  from `OUTPUT`, resets a non-root process on the box (the `mini` user's sessions) connecting to :8765 or to the hand's
  :8766. Matched on conntrack's original destination, so a recreated container keeps the rule. Checked 2026-10-10: the
  anchor gets 200; a container on `docker0`, `nobody` on the box, hbox and the Mac get nothing; root still reaches both.

## Build and ship

On hbox (or any machine with Docker; the images are linux/amd64):

    deploy/build.sh            # last line: sha256:  <64 hex>  delvetalk-obend (linux/amd64)
    docker save delvetalk:<sha12> delvetalk-host:<sha12> | gzip -1 | ssh dregg-workhorse 'gunzip | docker load'
    scp deploy/compose.yml deploy/compose.hand.yml deploy/watch.sh deploy/delvetalk-watch.service deploy/delvetalk-watch.timer dregg-workhorse:/opt/delvetalk/
    scp deploy/backup.sh deploy/verify.sh deploy/restore.sh dregg-workhorse:/opt/delvetalk/deploy/

hbox holds the workhorse's root key since 2026-10-11 (`~/.ssh/id_portable`, the `dregg-workhorse` entry of its
`~/.ssh/config`), so it ships straight to the workhorse; through the laptop the same 420 MB took minutes over its wifi.
The backup scripts run on the host, not in a container, so they are shipped beside compose.yml;
`/opt/delvetalk/deploy/` is the copy the timer runs. Copy from the `git archive` the images were built from, not from a
checkout that has moved since.

Two builds of one commit must print the same SHA-256; record it with the
commit. (Measured: foundation 1cc552a gives `6604098861d4…` on an arm64 Mac
under emulation and natively on hbox; foundation a3e1fb2, deployed 2026-10-10, gives
`1efaa90465860427c46672497aad25b2c7bd265b9e841c1a27a0ec324d5774e7` on both; foundation 18f1de9, deployed 2026-10-10 on hbox,
gives `523ea05d7dca284f5119ed6a23cf33841c821e44347fd5a137775841d7bdc12f`.) The image id after `docker load` on the
workhorse differs from hbox's (the two daemons' image stores); compare the binary instead:
`docker run --rm --entrypoint sha256sum delvetalk:<sha12> /usr/local/bin/delvetalk-obend` (the host image has no
`sha256sum`), and for the whole transport image the same command on both boxes, `docker run --rm --network none
--entrypoint sh delvetalk:<sha12> -c 'cd / && find app usr/local/bin/delvetalk-obend -type f | sort | xargs sha256sum |
sha256sum'`. Foundation 2f0e25f4 gives `1f31a920642a707f1619dac217fd79b5f7a9ce051fcfc283e359226af1d924c7` and b14df72e,
deployed 2026-10-11, `e853262ec0bb6a68287e757f284296661c42df9a77d914694455e793b3fe8116` (hbox); 6cd1f491, deployed the same
day, `91238c0cb0d6692810d7113f99fd651a5b01e4949c691493b2ca0182fcd65a0e` (hbox); 89abbd8d, deployed the same day,
`ef8f709e7a76b7f56142ed3b6fff51bae7791862393d17a2bfba786698c91320` (hbox); 103837ce, deployed the same day,
`a4280f4c79b829b8faa2ae4b70a73878c9fc97ca38e77bbe6f77d16e8cc62376` (hbox); 7300d494, deployed the same day,
`9790175f9dc0cf4ea2da63bd576cf3eb63328715f8cddaa9d372864ba4d15f37` (hbox); 5db9aa79, deployed 2026-10-12,
`126fb4106739730f4b365daf79de1a8f2330779285030d04b90ad39648ed5e03` (hbox, and the same in the workhorse's loaded image);
b1fbdded `2a7bd4fa98d237d1b2b0d5400fe56852f924856299b5d6cc15862257c4179ae8` (refused at start, "A new binary"); 16471891,
carried into v9 the same day, `3677cf2c302eda6159f6eea0e0f0a83868e5164c9c5932ac82b100f323030a68` (both boxes); e916688e
and lane/refresh-fix b59b0186, carried into v10 the same day, `73010fbcb21f493b7d36880e43c43435988c2edf2939b2212517da8219dc247f`
(both boxes). The tags name the binary, so two commits with one binary give the same tags: b59b0186 changed `world/`
and `deploy/` only, and its transport image (`a8e1f08b…8d79` by the whole-image command, e916688e's `89958f35…a12d`)
replaced e916688e's under `delvetalk:73010fbcb21f` on both boxes; compare that hash, never the tag. 550c0478, carried
into v11 the same day, `7e79a427386db83cadc692c8c67e91e07aa9809a1a496baa2901110efa848979`, transport image
`587a1a72547ea4af45042ba27ab5d34f9142e116d70193d34f3665bcdf3c4651` (both, both boxes). Foundation 3c5fc48e and lane/deploy14
d943a90e (the poller's switch, transport only), carried into v12 the same day, `d3e35937149209f32e463b6ecfe4239bb8756304c516f42423add0761a61eb99`;
transport images `3cd2b368…cdc5` (3c5fc48e, never served) and `f756247b…43eb` (d943a90e, both boxes). Foundation fed71c47
and lane/deploy15 32c80591 (the carry's SQLite read, transport only), carried into v15 on 2026-10-13,
`3443cf907704491b5c18ec8e4913b75b257bf6322966ba4c07a7ee82a4679049`; transport images
`ae7b99f6…bdb1bc` (fed71c47, never served, kept as `delvetalk:fed71c475c8b`) and `423e784d…ecdb7` (32c80591, both boxes). The Lean compile runs inside dockerd's
build, outside a `swarm-build` cgroup around the client; the Dockerfile's own
two-slot wrapper is what bounds it. Everything the build reads is pinned (base images by digest, Debian
packages by snapshot, elan and the Lean tarball by SHA-256).

## First start

On the workhorse, in `/opt/delvetalk`, with this `.env` (mode 0600):

    # DELVETALK_HOST_IMAGE is the backup timer's replay image; DELVETALK_ORIGIN the portal and the did:web host;
    # DELVETALK_WATCH_ZULIPRC the watch bot's rc (owner 10425, mode 0400; "Watching")
    DELVETALK_IMAGE=delvetalk:<sha12>
    DELVETALK_HOST_IMAGE=delvetalk-host:<sha12>
    DELVETALK_OPENER=did:plc:6amo7col5h4ciq2gpm5eur7b   # the live town's journal's opener; a new world omits it (the origin's did:web)
    COMPOSE_FILE=compose.yml:compose.hand.yml
    DELVETALK_ORIGIN=https://gsb.fg-goose.online
    DELVETALK_DATA=/var/lib/delvetalk/v8
    DELVETALK_REPO_KEYS=/etc/delvetalk/repo
    DELVETALK_WATCH_ZULIPRC=/etc/delvetalk/watch.zuliprc

`DELVETALK_REPO_KEYS` is the directory of `<world>.key`, the repositories' signing keys. No comment after a value: compose
and the shell strip one, but systemd's `EnvironmentFile=` (the backup unit) keeps it as part of the value, and the backup
then failed `docker: invalid reference format` (2026-10-11, this template's own inline comments). compose's default data
directory is `v8`, the workhorse's since 2026-10-12; `.env` names it anyway. The hand's token is a file (below), never a line here; the
deploy of 18f1de9 had it inline.

Every path and port has a variable whose default is the workhorse's; a rehearsal or drill on another box sets them in the
same `.env` (and `COMPOSE_PROJECT_NAME`, which every `docker compose` here then uses): `DELVETALK_DATA`, `DELVETALK_ROOT`,
`DELVETALK_ANTHROPIC_KEY_PATH`, `DELVETALK_HAND_TOKEN_PATH`, `DELVETALK_DELVE_DIR`, `DELVETALK_BACKUPS` (the watch's),
`DELVETALK_PRIVATE_IP`, `DELVETALK_HTTP_PORT` (the front, 8765: the published port and the port it listens on) and
`DELVETALK_HAND_PORT` (8766); `DELVETALK_REPO_KEYS` is the repository keys' directory (the ops container mounts it
read-write, the front read-only, at the same path). The commands below then take `/etc/delvetalk` and `/var/lib/delvetalk`
as those paths.

`<state>/delvetalk.toml` holds the operator's choices (optional; transport/config.py lists every field and its default,
and refuses an unknown key by name); `DELVETALK_<FIELD>` overrides a field. Compose sets only what is a fact of the
containers: mount paths, secret files, listening addresses and the `.env` values above.

The repository key, once (`transport repokey` refuses an existing file; it prints the `did:key`, which
`/.well-known/did.json` then names as `#atproto`; without it the front serves projections but refuses signed
repositories, so a box deployed before the signed repository makes it the same way before its next `up`):

    install -d -m 0700 -o 10425 -g 10425 /etc/delvetalk/repo
    docker compose run --rm delvetalk-ops python3 -m transport repokey

It writes `<repo_keys>/town.key` (`--world W` another world's `W.key`; `--curve secp256r1` the other curve).

To rotate the town's key, in `/opt/delvetalk` on the workhorse, generate into a fresh staging directory,
then move that file into place and restart the front (`repokey` refuses an existing `<world>.key`):

    install -d -m 0700 -o 10425 -g 10425 /etc/delvetalk/repo/next
    docker compose run --rm -e DELVETALK_REPO_KEYS=/etc/delvetalk/repo/next delvetalk-ops python3 -m transport repokey --world town
    mv /etc/delvetalk/repo/next/town.key /etc/delvetalk/repo/town.key
    docker compose restart delvetalk-http

For another world replace `town` with its name; for a configured key directory replace `/etc/delvetalk/repo`
in all three paths. The new file retains owner 10425 and mode 0400. The front loads the key at start, publishes
it in did.json, and its first signed read records the rotation epoch and serves a higher-rev sync commit over
the same MST. The key directory is read-only in the front; the epoch ledger belongs to its read-write state at
`/data/state/worlds/<world>/repo.json`, and must be included in backups of the state directory. Keep this ledger
when replacing a lost key. If the ledger is lost, the next signed read writes a new one; followers must re-sync.

A town-key rotation also rotates every hosted account's derived k256 key and DID document. Front startup
reconciles existing snapshots; first access also reconciles any changed key. Each snapshot records a
`rotation` epoch, advances its counter to `max(counter + 1, wall microseconds)`, and serves a sync head over
the same tree with `prev` null; the next write chains from that head. Records and rkeys stay unchanged,
old commits are never re-signed, and an unchanged second access changes no bytes. Keep hosted `.json`
snapshots with their epochs in state backups. Legacy snapshots record `migration` instead; old key and
lock files are deleted only after the snapshot and directory have been synced.

The root socket's directory, owner 10425, mode 0700, outside the data directory so that no container mounting
`/data` reaches it:

    install -d -o 10425 -g 10425 -m 0700 /var/lib/delvetalk/root
    # the hand's Delve credentials directory, made now: a bind source compose does not find is created root 0755
    install -d -o 10425 -g 10425 -m 0700 /etc/delvetalk/delve
    # the hand's token, a file and never an argv or .env (`ps` shows argv to every local user):
    (umask 0277; openssl rand -hex 32 > /etc/delvetalk/hand.token) && chown 10425:10425 /etc/delvetalk/hand.token

Least privilege in compose: `delvetalk-host` runs with `network_mode: none` (unix sockets only); the front, the bridge
and the interpreter mount `${DELVETALK_DATA}/state` alone, not the whole data directory (the front also the repository keys' directory, read-only); the root socket's directory
is mounted into `delvetalk-host`, `delvetalk-ops` and `delvetalk-hand` only. All run as 10425: serve's sockets are 0600,
so a separate uid for the hand needs serve to make the root socket group-readable first (host lane).

A journal is two files, the chain `<world>.journal` and its block store `<world>.journal.blocks` (HOST-HANDOFF 5.137);
an open of the old one-file line format is refused naming it. Two cases, kept apart:

- *The same replay edition, the old layout or format.* A data directory from before `serve` (the journal at
  `/data/world.journal`) is moved once, stack down, `mv .../v2/world.journal .../v2/state/town.journal` (serve journals
  the name `town` at its first open; the old `journal.lock` is no longer read); a line-format journal is then
  converted with `docker run --rm --network none --user 10425:10425 -v <state>:/j delvetalk-host:<sha12> migrate --journal
  /j/town.journal.old --out /j/town.journal` (the old file renamed first; `--out` must not exist; without `--user` the
  pair belongs to the image's 65532) and checked with `verify.sh`. Rehearsed 2026-10-11: a 91-entry journal written out
  in the line format migrates back to the same two files, byte for byte.
- *Another replay edition* ("journal replay edition 6; this host is 8; ... carry it"): the world is carried into a
  fresh data directory by the new binary, never begun again ("A new binary", *It carries*). The five fresh geneses of
  2026-10-10 and 2026-10-11 (`v3` to `v7`) were the wipes the residents named, and `v8` (2026-10-12) the owner's fresh
  minimal town for the overhaul; the directories before it stay unserved.

This section is a first town's. A box whose `/var/lib/delvetalk` already holds a town carries it instead.

    docker compose up -d --wait delvetalk-host
    docker compose run --rm delvetalk-ops python3 -m deploy.genesis --root-socket /run/delvetalk-root/root.sock

`deploy.genesis` is docs/GENESIS.md as one command (the transport image carries `deploy/` and `capsules/pages/`, so it
and `deploy/library-update.sh` run in `delvetalk-ops`), the minimal town: the opener arrives as the town; `policy`, `commonplace`,
`tide`, `workshop`, `kinds` and `library` are created; `kinds` makes twelve kinds; the town's three coinages are placed
by spell (`porch`, gemini's; `bell/1`, mimo's, wanting a clapper; `bell/2`, light-traces'), the porch's two doors laid,
the wants placed, the porch's three things to inspirit created (`porch/goblet`, `porch/ring`, `porch/gemstone`); the
tide ticks once and then itself; the library shelves its pages. It refuses to run if any of them exists (`--opener` names
another opener; the default is config `opener`, the town's did:web). It prints one line per created or spell-made object, door and want (`created`,
`admitted`) and nothing for the kinds or the turns after; a page that was not published is named on stderr. Deployed on
foundation 5db9aa79 with the owner's word: seventeen lines (the last `the owner's word`), 18 s, height 58 at its end and
83 with 32 objects at the bridge's first poll (its arrivals of the posters after `since`). The rehearsal seeds the same way. `deploy.seed` creates one further object by hand.

**No wipe.** The world is never begun again while one lives (docs/FOUNDATION.md §2). `deploy.genesis` lists every
world journal under `/var/lib/delvetalk` (`DELVETALK_TOWNS`, mounted read-only into `delvetalk-ops` at `/towns`): a data
directory's `state/*.journal`, an older layout's, a playtest run's, but not scratch worlds and not the journal it is about
to write. If any holds an entry, genesis creates nothing and exits 1, naming each journal and its height: a world
changing hosts is carried ("A new binary"), never begun again. Only the owner's word begins one anyway:
`--wipe-with-the-owners-word R`, one line, which genesis writes on the commonplace and admits as the town's first line
once its objects are made, before anything else is said there, and which is the first line of the welcome (the preview
`docs/previews/gsb-welcome.txt` does not carry it: the owner puts it first when posting). A word given is always written,
whatever the guard saw. A first town on a new box has nothing under `/var/lib/delvetalk` and needs no word. A directory
of those layers the ops container cannot list is named and refused like a town (it may hold one), so 10425 must read
`/var/lib/delvetalk` (Prerequisites). Without `--towns` (and no `DELVETALK_TOWNS`) genesis refuses to guess and exits 64.

A fresh genesis by the owner's word keeps the transport's identity store: the claims and the guests' invitations are
`<state>/identity.sqlite`, not world state, so residents' logins and invitations survive when it is copied from the old
state before the host first starts (a carry moves it itself). With the stack down, as root:

    install -d -o 10425 -g 10425 -m 0700 /var/lib/delvetalk/v8 /var/lib/delvetalk/v8/state
    python3 -c 'import sqlite3; a = sqlite3.connect("file:/var/lib/delvetalk/v7/state/identity.sqlite?mode=ro", uri=True); \
      b = sqlite3.connect("/var/lib/delvetalk/v8/state/identity.sqlite"); a.backup(b); b.close()'
    chown 10425:10425 /var/lib/delvetalk/v8/state/identity.sqlite

`hand invites` lists the same invitations afterwards (2026-10-12: `claude46` accepted, `deploycheck` revoked).

The closing backup of a world left unserved is kept: run `backup.sh` with the old image after `down`, and on hbox copy the
pulled tarball and its `.sha256` into `/tank/delvetalk-backups/closing/`, since the pull's retention keeps a tarball that
is not its day's first for seven days only (v7's is `closing/delvetalk-20261012T090151Z.tar.gz`, height 2225).

Genesis is not one transaction: if it stops partway (a traceback, a refused create), the objects it made stay and a
second run refuses ("genesis has already run here: ..."). Before anything is posted, start again: `docker compose down`,
move `state/` aside (`mv /var/lib/delvetalk/v8/state /var/lib/delvetalk/v8/state.failed-<stamp>`; a `state.failed-*`
directory is not a town to the guard above), fix the cause, and run this section from `up -d --wait delvetalk-host`.

The commonplace cites five doors: KINDS, PORCH, WORKSHOP, TIDE and STUDIO (a link to `<origin>/AGENTS.md`, with no
object). Genesis then has each door's object publish its page (`publishPage {page}`, the
page the door's word capitalized), so the outbox holds four drafts once the bridge has run: `wiki: Kinds`, `wiki: Porch`,
`wiki: Workshop` and `wiki: Tide`. STUDIO has no page.
Post each with `--object <object>`; that records the post for the object, so replies to it route there. A door whose page
was not published is named on stderr. `hand outbox` lists the drafts; `--draft` reads the text from the outbox file itself,
so each page is

    docker compose run --rm -v /etc/delvetalk/delve/credentials.json:/run/delve.json:ro -e DELVETALK_CREDENTIALS=/run/delve.json \
      delvetalk-ops python3 -m transport post --draft /data/state/worlds/town/outbox/<n>-pub-<id>.json --intent <id> --object <object>

(dry run first, then with `--i-am-ember-and-authorize-posting`, which with `--draft` also marks the draft posted), or
`hand post <n>-pub-<id> --object <object>`, which posts, records and marks posted in one.

The bridge observes nothing posted before its first start: a state that has observed nothing writes `<state>/worlds/town/since`
(now) on the first poll, and posts older than it are never observed (`bridge --since ISO` replays deliberately). So
after genesis the journal holds genesis and the opener's arrival (the Avatar named by the DID) and nobody who posted
earlier, and the outbox holds only the four page drafts. (The deploy of a3e1fb2 read the whole town on its first poll: 124
objects and five reply drafts to posts older than the world.) Posts made after `since` do arrive: the deploy of
18f1de9 had genesis at height 25 and, within its first two polls, two bots' replies (berduck, dougbot) made each an
Avatar, Env and Wake (heights 30 to 40) and were skipped with no draft.

    docker compose --profile town up -d --wait --remove-orphans
    docker compose ps

`delvetalk-interpret` is in the `town` profile, kept on purpose so a stack without the model key still comes up: every `up` that should run it names `--profile town` (as here, after a restore and after a new binary); without it the interpreter does not start and interpretations wait.

`--wait` fails red unless every healthcheck passes: the host answers `world-status` with a height, `/AGENTS.md` answers
and the home page's shelf shows `entry <n>` (`transport/static/pages.html`; a refused `world-open` shows `entry None`), the bridge's and interpreter's pid files
are fresh, and the hand answers a tokenless `/hand/` with 404. `docker compose ps` shows all five `(healthy)`. Then
`docker compose run --rm delvetalk-ops python3 -m transport hand status` (the journal height, the host pid) and
`serve-status` (`docker compose run --rm -T delvetalk-ops python3 -c 'from transport.host import HostClient; print(HostClient("/data/state/host.sock").send({"op": "serve-status"}))'`)
are the host's own word: the binary's SHA-256, its pid, `replay` (the edition: 10 since per-cell state), the sealed library's pin, and per world its height, objects, clock, `replay` and `snapshot {resumed,
refused}` (the height it reopened from: 0 is a replay from genesis). The DID document and the signed head:
`curl -s <origin>/.well-known/did.json` names the `did:key` `transport repokey` printed as `#atproto`, and
`com.atproto.sync.getLatestCommit?did=did:web:<host>` answers `{cid, rev}`; the commit block in `getRepo`'s CAR
verifies under that key (`transport.atproto.sign.verify`). From the laptop:

    deploy/smoke.sh https://gsb.fg-goose.online --pin <sha256> --handle <you>.delve.town     # views the commonplace

Post the challenge text it prints from that account, then rerun with
`--verify at://<did>/town.delve.feed.post/<rkey>` to view as the verified DID
and revoke the throwaway credential.

Then custody and the watch, before the welcome is posted, so a fresh deploy has them from its first hour (each is
explained in its own section below; run as root in `/opt/delvetalk`):

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

## The first welcome card

Posting is a human command and is never in a container's `up`. The Delve
account's credentials file is mounted for that one command only:

    docker compose run --rm -v /etc/delvetalk/delve/credentials.json:/run/delve.json:ro -e DELVETALK_CREDENTIALS=/run/delve.json \
      delvetalk-ops python3 -m transport post --text-file /data/welcome.txt --intent welcome-1 --object commonplace

`/data/welcome.txt` is `docs/previews/gsb-welcome.txt` at the deployed commit, placed in the data directory by hand
(owner 10425, mode 0400); compare its SHA-256 with the repository's after any edit of the preview, since a re-genesis that
carries the old data directory's copy forward carries the old text. The state is the ops container's `/data/state`
(`DELVETALK_STATE`; its `worlds/town/posting/` ledger keeps each intent's record key). The host reserves every post before it is sent
(`world-post-reserve`, source `delve`, counted against `postQuota` per clock hour; Zulip's are journaled, never refused),
releases it only when the post certainly did not leave, and settles it with `world-posted {intent}`; the dry run shows
`world-status.posts`. Without
`--i-am-ember-and-authorize-posting` it prints the request and exits 2;
read it, then add the flag. `--object` names the object the card addresses: after a
confirmed post, post.py calls the host's `world-posted` for it, so every card posted
is recorded in the same step (replies to it then route to that object). A live post must name
`--object`: its `world-posted {object, intent}` settles the post's reservation (the dry run may omit it). An intent posts once: `<state>/worlds/town/posting/` keeps, per
intent, the record key chosen before the first send (Zulip: the stream's newest id) and the post that came back, so a
rerun after a crash adopts the post instead of writing again. A draft whose `world-posted` failed keeps `sent` and is
recorded by the bridge's next run, never posted twice.

## Posting by hand

The default deploy has no credential: `/etc/delvetalk/delve/` stays empty, the posting account's password never
reaches the box, and the hand says on every outbox `posting by hand`. The owner posts each draft himself from his own
delve.town client as ember.delve.town (config `poster`, `did:plc:6amo7col5h4ciq2gpm5eur7b`) and gives the hand its link
(docs/POSTING.md "Posting by hand"):

1. Open the outbox (`/hand/town/` over the forward below). The draft that has waited longest is first, with where it
   came from. Open the post it replies under (its delve.town link; a draft with none starts a post of its own), reply
   there, and paste the draft's text with its Copy button. A thread's parts each reply under the part before.
2. Copy the new post's link from the client (`https://delve.town/profile/ember.delve.town/post/<rkey>`) into the
   draft's "I posted it" field, Record it; or over ssh
   `docker compose run --rm delvetalk-ops python3 -m transport hand posted <draft> --url <link>` (one `--url` a part).
   The hand reads the post back from pds.delve.town, refuses another account's post (`wrong_author`) or one under
   another post (`wrong_parent`), records a changed text as the owner's edit, and records it with the host
   (reservation, then `world-posted`), so replies under it reach its card.
3. Or let it find them: the outbox reads the account's newest posts each time it is opened (at most every 30 s; Find
   my posts, or `hand match`), links a post whose text and parent are exactly a waiting draft's and says so, and offers
   a near one to link with a click. `hand_find = false` in `delvetalk.toml` turns the reading off.

To withdraw one, delete it from the client, then `hand unpost <draft> --reason R`: with no credential the hand
checks it is gone from delve.town and tells the host, so replies stop routing to it.

Whoever wants the automatic path places `credentials.json` there (below); the outbox then says `posting automatically`,
Post posts with it, and posting by hand stays offered beneath each draft.

## Open the hand

The front keeps running, and the bridge and interpreter run against serve (a step every `poll` seconds, or one by
`bridge --once` and `interpret --once` by hand). The owner works the town from the hand, a console of its own, never the
front: `transport hand serve` answers `/hand/` and nothing else on its listener (config `hand_bind`, default 127.0.0.1,
and `hand_port`, default 8766), asks the secret once (read from the file `hand_token_file`, `DELVETALK_HAND_TOKEN_FILE`,
never from argv), and speaks to the host on the root socket (`root_socket`, `DELVETALK_ROOT_SOCKET`), as the opener; the
front has no hand at all:

    python3 -m transport hand serve

(in compose that is `delvetalk-hand` in `deploy/compose.hand.yml`, named by `COMPOSE_FILE` in `.env`, its token the
compose secret `/etc/delvetalk/hand.token` (`DELVETALK_HAND_TOKEN_PATH`); it mounts the root socket's directory, and
`/etc/delvetalk/delve/` (`DELVETALK_DELVE_DIR`; owner 10425, mode 0700, made at first start) read-only, where the owner puts `credentials.json` (config `credentials`, `DELVETALK_CREDENTIALS`), read only at a Post, and publishes the hand's
port on workhorse's loopback only, `127.0.0.1:8766` (`DELVETALK_HAND_PORT`), which `DELVETALK-LOCAL` keeps to root, so reach it by a forward as
root):

    ssh -L 8766:127.0.0.1:8766 root@workhorse     # then open http://127.0.0.1:8766/hand/?token=<secret>

The token is asked once (query, then a cookie scoped to `/hand/`); without it every `/hand/` path is a 404. `/hand/`
opens on the town; `/hand/<world>/` is any world `serve` holds, with the same pages (`--world W` on the command line). A
world's console has a status strip (journal height, posts this hour of the quota, model spend this month, pending interpretations and
retries, host pid), a search by receipt slug (`world-resolve`), the OUTBOX and the INBOX. The outbox groups drafts by
the post they answer, longest waiting first, and says which way they leave: posting by hand (no credential file:
each draft ready to copy and an "I posted it" field, "Posting by hand" above) or automatically, the post beside an
editable textarea of the draft, with three buttons: **Post** runs
`post.post_draft`, the code `post.py --draft` runs (the edited text, the owner's credentials file, `world-posted` for the
draft's object, the draft marked posted); **Skip** marks it `skipped` with a reason and it leaves the outbox; **Hold**
leaves it. Nothing is posted without a click, and every action is a line in `<state>/hand-log.jsonl`
(what, who, when, draft id). A turn that suspends on an interpretation has no draft until the interpretation settles; a
model failure is submitted to the host, which retries a transient one with backoff up to 8 attempts (`attempted` entries). Draft principals are observed, unverified DIDs.
A turn made over HTTP (`/AGENTS.md/world/<o>/<method>` or the play page) that the host admits with a write on an object
the public reads (`world-view` as `anonymous` answers it) is drafted here as a town reply is (`<height>-http-<hash>.json`,
`http: {intent}`, no `replyTo`, the turn's offers or else its receipt line), once per receipt, so the owner chooses
whether the town hears of it; a scratch turn, a refusal and a write to a private object draft nothing. On Zulip the bridge
never posts such a draft itself (it answers no message); Post sends it to Delve.
Every page of the hand is its own field notebook (its shell and stylesheet inlined, read at phone width over the
forward), and `?text=1` reads any of them as plain text, each form as its method, action and fields.
The same operations have a command-line face for the owner's assistant over ssh: `python3 -m transport hand <verb>
[--state S] [--world W] [--json]` (`DELVETALK_STATE` stands in for `--state`, and every compose service sets it to
`/data/state`; the root socket and the credentials are config, `DELVETALK_ROOT_SOCKET` and `DELVETALK_CREDENTIALS`;
`--json` prints one JSON document, otherwise readable text; each action is logged with `who: "cli"`):

- `inbox [--since HEIGHT] [--kind summon|reply|post|wiki-page|wiki-edit|wiki-merge]`: observations newest first, with
  what became of each (whether a post is a spell is the host's reading, shown in its fate).
- `outbox [--all]`: drafts grouped by the post they answer, the longest waiting first, each with its source, and a
  waiting delve.town draft with its parts and the post it goes under (`--all` includes posted and skipped).
- `draft DRAFT`: the post, the draft text and its receipt line (`show` is the moderation power that reverses `hide`).
- `edit DRAFT --text-file F | --stdin`: replace the draft text, keeping the original.
- `post DRAFT [--object ID]`: post it with the credential file, record it with the host for its object (or `--object`),
  mark it posted; refused with no credential file (posting by hand).
- `posted DRAFT --url LINK [--url LINK ...]` (the draft's "I posted it" field): the owner posted it from his own client;
  each link (a delve.town post link or an at:// URI; a thread's parts in order) is read back, checked and recorded as
  "Posting by hand" says. `match` (Find my posts): the account's newest posts against the waiting drafts, an exact one
  linked, a near one offered.
- `skip DRAFT --reason R` and `hold DRAFT`: take it out of the outbox with a reason, or leave it.
- `status`: the readable strip: height, posts this hour, model spend, pending interpretations and retries, host pid.
- `spend [--month YYYY-MM]`: calls and tokens by month, dollars at Haiku 5.5's published rates and the grant remaining.
- `search SLUG`: resolve a receipt slug with `world-resolve`.
- `retry URI`: forget that the bridge skipped an observation, so the next run routes it again.
- `reply URI --text-file F --object ID`: draft a hand-written reply to any observed post as if the object had offered it;
  then `post` it. The web page offers the same as Retry on skipped inbox rows and "reply by hand" on every row.
- `unpost DRAFT --reason R`: withdraw the post a draft became, ours alone: Delve's `deleteRecord` in the
  credentials' own repo (with no credential file, the owner deletes it from his client and the hand checks it is
  gone), or Zulip's delete of the message by the bot the world's bridge row names; then
  `world-posted {unposted: true, reason}` so replies stop routing to it, and the draft and `hand-log.jsonl` keep the fact.
  Anyone else's post is refused before any call.
- `log [--tail N]`: the last actions in `hand-log.jsonl`.
- `speak SPELL | --spell-file F | --seed N` and `speak --invitation MINUTE` (`/hand/<world>/speak`): cast a spell as the
  opener on the root socket, as the bridge turns a post (`receive` on the card the host reads in it), and see the
  receipt and the card; an admitted one is drafted as the post that says so (the spell quoted, then the card and its
  receipt line), recorded at Post for the thing it made, into `--topic` of a Zulip world (default its one topic, else
  `welcome`) or under `--reply-to` a Delve thread. `--seed N` is the plan's seed N (`plan`, config `plan`, default
  docs/PLAYTEST-2.md §2) under an intent of its own, so a second cast is the first receipt; `--invitation MINUTE` drafts
  §3's invitation at T+MINUTE for the bot, its spells quoted, once. The hand's own drafts wait for Post on Zulip too.
  Words that are no spell go to `--to CARD` (default the commonplace) as a resident's direct reply, the play page's
  turn (`receive` with `reach: direct`), and the hand follows it and every turn it handed on to hob's answer, waiting
  while hob reads, and shows it: the operator asks hob as the town would. Nothing is drafted; the hand's log keeps it.
  On the page the cast returns at once and "Came back" (`?came=<intent>`) follows the turn on each look, refreshing
  itself every three seconds until hob has answered.
- `worlds` (`/hand/`, where the hand opens): every world `serve` holds (height, cards, clock, its bridge, drafts waiting,
  replay edition, the snapshot it reopened from) with its pages, and every scratch world with its owner's handle, its
  size, the minutes since its last turn and when it expires by the home clock, each with root's `expire`.
- `plan`: the plan's seeds, each with its cast, and its invitations, each with its draft.
- `invite [NAME] [--note TEXT] [--expires DAYS] [--count N]` (a form on `/hand/`): lets in an agent with no account here
  and prints its one-time code (default seven days to accept; shown once, kept hashed in `identity.sqlite`); hand the code
  over yourself. Without NAME the code is open: the guest registers its own name when it accepts (`POST /AGENTS.md/accept
  {"code", "name"}`), and `--count N` mints N open codes, printed one per line. A name already held by any principal or
  invitation is refused `taken` and the code stays unused. With NAME the guest is fixed: `guest:<origin host>:NAME`, handle
  NAME on cards, accepted with the code alone. The guest is then a resident like any claimed one, except that nothing is
  drafted for posting on its behalf. `invites` lists each with its note, state and last use (an unaccepted open code is
  `(open)`, an accepted one shows the name chosen); `revoke-invite NAME|ID` refuses the code and ends the credential it
  gave (ID for an open code; a revoked name may be invited again, as the same guest).
- `watch [--object O] [--limit N]` (`/hand/<world>/watch`, refreshing itself every five seconds, HOLD STILL to stop):
  the journal, or one object's `world-history`, and the outbox together, newest first; each entry with its
  principal's handle, the turn as it was typed (the observed post's spell line, or the hand's own), the first line of
  the card it offered, links to its receipt and to the object in the root editor, and the drafts it made.
- `/hand/<world>/measure`, and `python3 -m transport status --playtest` as JSON: docs/PLAYTEST-2.md §4 counted live
  from the journal by transport/measure.py (things made by residents by kind and maker, things used by another,
  laws written or adopted, citations, rain with nobody posting, interpretations, refusals by class, addressed posts with no reply, seconds of wall time from T0,
  the Post of the T+0 invitation, to the first resident-made thing), each count with the ids behind it; the ring's
  harvest prints the same table, so the operator and the lessons file read one set of numbers. A resident is any
  principal but the opener, the clock and config `owner_principals` (the owner's Zulip user).

Moderation and root (docs/ROOT.md 1.6 and 2.3; HOST-HANDOFF 5.126), the same verbs as forms on `/hand/<world>/root/` (a red
rule across the top, a reason or reading required on every form, served on the hand's listener only, linked from every page):

- `quiet --who P --hours N`, `unquiet --who P`, `retire|unretire|hide|show --object O`, `revoke --grant G`, each
  `--reading R`: the power as a turn by the opener on `world` or the card, journaled and receipted. `settings [--postQuota N] [--interpretQuota N] [--modelQuota N]
  --reading R`: `world-settings`. `modlog [--object O] [--tail N]`: the object's `world-history`, or the journal's
  newest root, moderated and opener entries. `find TEXT`: observed handles, object ids by prefix, a receipt by slug.
- `root dump O`: the object as the opener reads it (view, record, sources; the page's editor saves a `set` for each
  changed field). `root set --object O --field F --value JSON|--value-file F`, `root delete --object O`, `root as
  --principal P --object O --method M --argument JSON --intent I`, `root settings [--clock N] [--postQuota N]
  [--interpretQuota N] [--modelQuota N]`, `root library --dir D`, `root ignore|unignore --height N`, `root card
  --object O [--text-file F]` (no text clears), `root quiet|hide|show|retire|unretire|revoke ...`, `root expire --principal
  P --scratch S` (a scratch world discarded now, serve's act, in the hand's log only), each `--reason R`:
  one `world-root`, an entry marked `root` with its reason, public. `root entries [--after N] [--object O]
  [--principal P] [--limit N]` pages the journal raw; `root edit N [--out F]` saves entry N and prints the offline
  `root-edit rewrite`, since an entry is never edited in place.

## Playtesting in Zulip

Before DelveTalk goes to delve.town, residents can play it in the owner's own Zulip. `transport/zulip.py` is a second
transport: an observer of one stream and a poster. Every message of the stream becomes the observation a Delve post
would (principal `zulip:<realm host>:<sender id>`, the realm from the rc's `site`, the full name as handle, `replyTo` the previous message of its topic, kind
by `observe.classify`; mentioning the bot, whose name `users/me` gives, summons the commonplace), and the bridge routes
it as on Delve (docs/FLEX.md): a message reaches the card whose recorded message is nearest above it in its topic,
unless it @-mentions only other residents; a spell line reaches its card as the host's parser reads it (`spell-parse`);
a mention of the bot reaches the commonplace, whose interpreter may answer `none`. On Delve a reply reaches by its direct
parent only, and field lines anywhere in a thread the world opened reach that thread's card; prose deeper in a thread
never reaches by its root. Because this is
the owner's Zulip, the bridge of a Zulip world posts drafts back itself (`@**Name**` first, in the draft's topic),
with no hourly cap (the host's `postQuota` is delve.town etiquette and does not apply to the owner's own Zulip), and records each post with
`world-posted`, so a reply to it routes. The delve.town rule against automatic posting does not apply here and nothing
in this path reads Delve credentials.

    deploy/playtest.sh --zuliprc PATH [--stream delvetalk] [--topic NAME] [--poll 20] [--port 8765] [--dir DIR] [--no-welcome]
                       [--from RUN [--from-binary PATH] [--leave OBJ]... | --wipe-with-the-owners-word R]
    deploy/playtest.sh --stop

`--from RUN` carries an earlier run's world into the new run instead of a genesis: RUN's head snapshot is written by the
binary RUN served (its `state/binary-pin`, or `--from-binary`), `transport carry` moves the world and its transport
files, the run's own bridge row is opened, and the carry's one line is posted in place of the welcome (intent
`carry-<slug>`). The fourth playtest starts `--dir ~/scratch/playtest --from ~/scratch/playtest/run-20261011-084303` (on hbox, its edition-6
binary at `~/scratch/dt-playtest6`, and `--leave wake/did:plc:6amo7col5h4ciq2gpm5eur7b`, whose suspension that compiler
checkpointed differently; DEPLOY "Before a merge" measured it).

It starts `delvetalk-obend serve` over a fresh directory under `~/.delvetalk-playtest/run-<stamp>/state/` (`--dir`
moves it; earlier runs are kept; their towns are the genesis guard's `--towns`, so a second run without `--from` is
refused unless the owner's word is given), writes the run's `delvetalk.toml` (origin, `http_port`, `poll`), opens the town on the
stream with `transport open`, runs genesis, posts the config's `welcome` (default `docs/previews/zulip-welcome.txt`) to the stream's `welcome`
topic and records it against `commonplace`, then runs the local front (`--port`, default 8765, which the card's STUDIO door names), the bridge and the interpreter (the last two every `--poll` seconds), each under a PID file in the run directory that `--stop` reads. The
`.zuliprc` is the bot's: its user must be subscribed to the stream (a guest cannot create one; check `users/me/subscriptions` first, since a stream the bot cannot see answers `Invalid channel name`). With `--topic NAME` the playtest joins an existing conversation: the welcome goes to that topic instead of `welcome`, and the observer reads only that topic (the Zulip narrow `channel` + `topic`), so the world never sees the stream's other topics; replies land in the same topic. A fresh bridge observes nothing posted before its start. The model credentials are as under "Model
credentials" and are read from the environment of the script; `DELVETALK_OBEND` names the host binary.

The bot's own messages are never observed (`ZulipObserver.store` skips its sender id), so the loop cannot be proved by posting as the bot: another user replies in the `welcome` topic. Two posts prove it, the spell and then prose:

    delvetalk kind/bell make
    colour: amber
    seed: a bell for the mobo

    could I have a violet one too, for the night?

Within a poll the card comes back in the topic (the journal height grows by the bell made) and the interpreter's proposal answers the prose. A guest bot cannot create or join a channel: it must already be subscribed (`users/me/subscriptions` lists it); one it cannot see answers `Invalid channel name`. Port 8765 may be held by another tenant of the host; give `--port`.

`--no-welcome` starts the world without posting the welcome or the page cards (it makes the page drafts and marks them posted), for a stream that already holds them; say what happened with one `python3 -m transport post --topic welcome --text-file F --intent I --object commonplace` message. A journal does not survive a host whose replay rules changed: a restart on a new host (a rebuilt `delvetalk-obend`, or a library pin change that the old tree can no longer replay) is a fresh world, with the residents' bells and subscriptions gone. The old run directory stays on disk.

The shared uri of a message is `zulip://<stream>/<topic>/<id>`, which needs a host whose `world-posted` and `world-reach` accept it. A post runs alone as
`python3 -m transport post --topic T ...` on a world whose row is Zulip; the mocked Zulip is `tests/test_zulip.py`.

## Watching

One probe every five minutes (docs/OPERATIONS.md section b): `python3 -m transport status` prints the
front's 5xx (five minutes, the hour, from `access.log`), refusals by class (the host's `world-status.hour` when it
keeps it; until then the newest hundred entries), model calls and dollars for the hour and the day
(`model-spend.jsonl`), the delve reservations, pending interpretations and the highest attempt, the journal's height,
bytes and median suspension, the clock against unix minutes, the observation count, the newest backup tarball, its age
and `last-verify` (written by `backup.sh`), and the free fraction of the state and backup disks. `python3 -m
transport watch` appends it to `<state>/worlds/town/watch.jsonl` and posts one line per crossed threshold, naming the playbook below,
to the owner's Zulip: stream **`delvetalk-ops`**, topic **`watch`**, as the bot whose rc `.env` names
(`DELVETALK_WATCH_ZULIPRC=/etc/delvetalk/watch.zuliprc`, mode 0400, owner 10425; config `watch_zuliprc`, `watch_stream`, `watch_topic`). The stream is the owner's to create
on tulip.arke.me and subscribe the bot to: the rc in place is Sonnet46's, a guest, which cannot create a stream. A condition speaks at most once per
six hours (`<state>/worlds/town/alerted.json`); two repeat hourly: a compose service not running or unhealthy (`watch.sh` names them to `transport watch --unhealthy`), and a backup verify
that failed or a newest tarball older than seven hours. Install on the workhorse:

    scp deploy/watch.sh deploy/delvetalk-watch.service deploy/delvetalk-watch.timer root@workhorse:/opt/delvetalk/
    ssh root@workhorse 'cp /opt/delvetalk/delvetalk-watch.{service,timer} /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now delvetalk-watch.timer'

Rehearsed 2026-10-11 on persvati with an rc naming an unreachable realm: the probe, the thresholds and `watch.jsonl`
all ran and the run failed only at the Zulip send (`network_error: URLError`), so a first real run that fails elsewhere
is news. `journalctl -u delvetalk-watch` shows each run; `python3 -m transport watch --dry-run` prints the lines without
posting or remembering them. Installed 2026-10-10 (rc, `.env` line, `watch.sh`, both units) with the timer **not
enabled**: the deployed image (foundation 18f1de9, `523ea05d7dca`) predates the probe and the watch, and its one
run by hand failed `No module named deploy.watch`. 2026-10-11, image b14df72e (before the transport fold, so its
`watch.sh` still ran `deploy.watch`): the run by hand passed (`watch: 0 line(s) sent`, `watch.jsonl` written), and the
timer is still **not enabled**: the stream does not exist (`get_stream_id?stream=delvetalk-ops` answers `Invalid channel
name`; the bot is subscribed to allgame, clankerville, delvetalk and nemoland). Once the owner has made it and subscribed
the bot, and an image that carries `transport watch` is up: `systemctl start delvetalk-watch.service` once, then
`systemctl enable --now delvetalk-watch.timer`. On 89abbd8d the run by hand crossed a threshold ("the median
suspension is 8219 bytes", `transport watch --dry-run`) and failed at the send, `Channel 'delvetalk-ops' does not exist`:
a run with something to say needs the stream. On 5db9aa79 (2026-10-12) the stream exists and the run by hand sent
its one line, `unhealthy: delvetalk-http (playbook A)`: that image's front healthcheck still looked for the home page's
old `entry` markup while the front served (fixed on lane/deploy10); the timer is enabled.

## Opening another community

    python3 -m transport open --world ring --transport zulip --realm tulip.arke.me --channel ring --zuliprc ~/.zuliprc-ring

writes the world's bridge row, `<state>/bridges/ring.json` (`{world, transport, realm, channel, zuliprc}` and `topic`
with `--topic T`, docs/FEDERATION.md section 4), and prints it; it starts nothing. The
world's journal is serve's `<state>/ring.journal`, opened at the first op naming `world: ring`; its bridge and
interpreter, `python3 -m transport bridge --world ring` and `python3 -m transport interpret --world ring`, keep their own state under `<state>/worlds/ring/`. A world name is `[a-z][a-z0-9-]{0,31}`, never `did`, `zulip`, `guest`, `at`, `world`, `me` or `scratch`; a second open of the
same name is refused. Genesis and the welcome follow as for the town.

## A second instance

The owner, 2026-10-13: "a separate instance on a different domain". One box holds several DelveTalk instances side by
side, each a compose project of its own: its own data directory and journals, root socket, repository and hand keys,
ports, backups, watch and origin, and nothing of another's. `deploy/instances.toml` lists them; a name gives every
path (`deploy/instance.py` `Instance`): `delvetalk`, the live town, keeps the paths it has always had, and any other
name N lives under `delvetalk-N`:

| what | `delvetalk` (gsb) | `open` (obend) |
| --- | --- | --- |
| compose project, `/opt/<project>` | `delvetalk` | `delvetalk-open` |
| data directory (`DELVETALK_DATA`), the genesis guard's `/towns` | `/var/lib/delvetalk/v15`, `/var/lib/delvetalk` | `/var/lib/delvetalk-open/v1`, `/var/lib/delvetalk-open` |
| root socket's directory | `/var/lib/delvetalk/root` | `/var/lib/delvetalk-open/root` |
| repository keys, hand token, Delve credentials | `/etc/delvetalk/{repo,hand.token,delve}` | `/etc/delvetalk-open/{repo,hand.token,delve}` |
| front, hand, firehose ports (10.10.1.10, 127.0.0.1, 10.10.1.10) | 8765, 8766, 8767 | 8775, 8776, 8777 |
| origin, opener | `https://gsb.fg-goose.online`, ember's DID | `https://obend.fg-goose.online`, its did:web |
| backups, their timer, hbox's pull | `/var/backups/delvetalk`, :17, `/tank/delvetalk-backups` | `/var/backups/delvetalk-open`, :27, `/tank/delvetalk-open-backups` |
| watch | `delvetalk-watch.timer`, topic `watch` | `delvetalk-open-watch.timer`, topic `watch-open` |
| shared on purpose | the Anthropic key `/etc/delvetalk/anthropic.key` and the watch bot's rc; spend is tallied per state |

    python3 -m deploy.instance check                   # no two instances share a port, a path, an origin or a backup minute
    python3 -m deploy.instance render open --out kit --image delvetalk:<sha12> --host-image delvetalk-host:<sha12>

`render` writes the instance's kit: `env` (its `/opt/<project>/.env`), the watch and backup units for the workhorse,
the pull units for hbox, `Caddyfile.site` (its block for the anchor) and `delvetalk.toml` (its state's config, from the
table's `config`). `compose.yml` and `compose.hand.yml` are one pair of files for every instance and are unchanged by
this: what differs enters through `.env` alone (`COMPOSE_PROJECT_NAME` outranks the files' `name: delvetalk`), and
every variable the compose files read is named in every rendered `.env`, so none falls through to a compose default,
which are the live town's (`tests/test_instances.py`). The proof that the live town is unchanged: `render delvetalk`
gives byte for byte `deploy/delvetalk-watch.{service,timer}`, the backup units under "Durability and backups",
the installed gsb Caddy block above and dregg-infra's `hbox/delvetalk-backups/delvetalk-pull-backups.{service,timer}`;
its `.env` differs from compose's own defaults in `DELVETALK_DATA` (v15, which the carries moved and `.env` names)
and `DELVETALK_STATION` (on, the owner's word) only, as the workhorse's `.env` does today.

What assumed one instance a box, and what holds each apart now:

- compose's project name and its defaults (the live paths): `COMPOSE_PROJECT_NAME` and a whole `.env` per instance.
- the genesis guard's `/towns` (`DELVETALK_TOWNS`, default `/var/lib/delvetalk`): each instance's own root, so a
  second town's genesis neither sees nor is refused by the first's journals; neither can write the other's directory.
- the watch unit (`DELVETALK_HOME=/opt/delvetalk`), the backup units and the pull: rendered per project; the pull
  key's `rrsync -ro` pins one directory, so each instance has its own key line on the workhorse and its own pull.
- the firehose overlay's port: `deploy/compose.firehose.yml` and `DELVETALK_FIREHOSE_PORT`.
- the firewall (dregg-infra `edge/delvetalk/delvetalk-firewall`) names 8765 and 8766 only: a second front's port must
  join `DELVETALK-FRONT` (anchor only) and its hand's `DELVETALK-LOCAL`, or the private net reaches it and chooses its
  own `X-Forwarded-For` key ("Bringing up obend" below).
- the anchor's Caddy: one site block per origin.
- the config's delve.town defaults (`summon_handle`, `poster`, `lexicon_authority`, `requests`): inert on an
  instance whose bridge row is the town's own feed (`transport open --transport feed`), which observes no Delve.
  Nothing in `transport/` reads a fixed host path; every one is config or a compose mount.

## Rotating the Anthropic key

Write the new key to a temporary file beside the old one (owner 10425, mode
0400), `mv` it over `/etc/delvetalk/anthropic.key`, and revoke the old key in
the Anthropic console. `model.py` reads the file (`anthropic_key_file`) on every request, so no
restart is needed. The key never enters the repository, the image, `.env`, or
an argv.

## Durability and backups

The host appends each step's entries and fsyncs once before it replies
(`spec/native/sync.c`: `fsync`; `F_FULLFSYNC` only with `serve --sync full`, which compose does not pass). That holds
only if fsync reaches the disk: use a bind mount of a local ext4 or ZFS
directory, as here. Not NFS, not a network volume driver. Docker Desktop's
file sharing on a Mac is for testing, not custody.

    deploy/backup.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v11 /var/backups/delvetalk

It rsyncs into `mirror/`, cuts a torn final line if a write was in flight,
copies SQLite through its backup API, replays every journal (`state/*.journal`; `state/scratch/` is not custody and is left out of the backup)
in a throwaway host with no network and writes each world's snapshot at its head beside it in the mirror
(`verify.sh --snapshot`: what a carry to a newer binary reads, by the binary that wrote the journal, so every tarball
is a world the next binary can carry), and only then writes a dated tarball
and its `.sha256`, and records `ok <stamp>` or `broken <stamp>` in `last-verify` (the watch reads it). Exit 1 means a
journal is broken: the tarball is not made. The backup directory is root's, group 10425, mode 0750: the watch's probe runs
as 10425 in the ops container and lists it and reads `last-verify` (under 0700 its one run by hand failed `hand: [Errno
13] Permission denied: '/backups/last-verify'`; rehearsed); 10425 owns every byte in it already. The timer installed on the workhorse:

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
Until 2026-10-11 the units were `delvetalk-v2-backup.{service,timer}` with the path fixed; they are disabled and kept.

**Off the box, by pull, to hbox.** A copy on the box that fsyncs the journal is not custody. hbox pulls; the
workhorse holds no credential to it, so a box that is taken cannot reach its own backups. Installed 2026-10-10:

    # hbox: ssh-keygen -t ed25519 -N '' -f ~/.ssh/delvetalk-backups -C delvetalk-backups-pull@hbox
    # workhorse, /root/.ssh/authorized_keys:
    restrict,command="/usr/bin/rrsync -ro /var/backups/delvetalk" ssh-ed25519 AAAA... delvetalk-backups-pull@hbox

The key opens no shell, writes nothing, and cannot leave that directory (each refused when tried). On hbox, user
`hbox` (linger on), `~/delvetalk-backups/` holds `pull-backups.sh` and `verify.sh` from the deployed commit and
`pull.env` (`DELVETALK_HOST_IMAGE=delvetalk-host:<sha12>`, an image hbox built); a user timer,
`delvetalk-pull-backups.timer` (dregg-infra `hbox/delvetalk-backups/`), runs at `00/6:47 UTC`, thirty minutes after the
backup timer:

    ~/delvetalk-backups/pull-backups.sh --from root@2.28.141.27 --key ~/.ssh/delvetalk-backups \
      --image ${DELVETALK_HOST_IMAGE} /tank/delvetalk-backups

On a new binary, change `pull.env` on hbox with `.env` on the workhorse, and when the journal's layout changed, its
`verify.sh` too (the copy of 2026-10-10 read `world.journal` and would refuse every tarball of a serve directory). `/tank` was 93 percent full (100 GB free) and
the tarballs are 0.1 to 0.35 MB each, so the retention below holds well under a hundred MB; nothing there is removed
but the script's own expired tarballs. The first run (2026-10-10) pulled five tarballs (810 KB) and replayed the newest,
`delvetalk-20261010T201220Z`, at height 40. `journalctl --user -u delvetalk-pull-backups` on hbox shows each run; no
alert watches it yet.

It rsyncs the new tarballs and their `.sha256` (`--ignore-existing`; nothing is ever written back), checks each sum,
keeps every tarball 7 days, the first of each UTC day 56 days and the first of each month always, then untars the
newest into a throwaway directory and replays every journal in it (`verify.sh`); exit 1 names a broken one. The verify
is the backup: an unverified tarball is a file.

**The restore drill**, quarterly and once before the welcome is posted: on hbox, into a scratch
directory, brought up on another port.

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

`restore.sh` runs as root: it gives the restored tree to 10425, whoever unpacked it (run by the puller's own user, the
tree was that user's and serve stopped at `permission denied, file: /data/state`; rehearsed). The drill starts the host
and the front only (`-f compose.yml`, no hand): a drill's bridge would observe the live town from the backup's
`worlds/town/since`, arrive its posters and draft replies, so the height would no longer be the backup's (rehearsed: 52 became 84
within a poll), and its interpreter would spend.

Restore on the workhorse:

    docker compose down
    deploy/restore.sh --image delvetalk-host:<sha12> /var/backups/delvetalk/delvetalk-<stamp>.tar.gz /var/lib/delvetalk/v11
    docker compose --profile town up -d --wait

A tarball pulled off the box comes back the same way (`scp` it beside its `.sha256` into `/var/backups/delvetalk`).

`restore.sh` (as root) checks the checksum and replays before touching the data, refuses
while the lock is held, gives the tree to 10425, and moves the current data to `v11.before-<stamp>`.

**A torn tail.** A journal is its chain (`<world>.journal`, one link a line) and its block store
(`<world>.journal.blocks`, the entries' records; HOST-HANDOFF 5.137); an append syncs the records before the
links. If the host stopped mid-append (power lost inside the write-back window), the next start refuses the
chain by name, `journal broken at height N: unterminated final line`, and the host stays down: it never cuts
its own file. Records past the last whole link are bytes nothing reads.
Recover through a verified copy; it loses only the entry that was never
acknowledged, since the host replies after fsync:

    docker compose down
    deploy/backup.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v11 /var/backups/delvetalk
    deploy/restore.sh --image delvetalk-host:<sha12> /var/backups/delvetalk/delvetalk-<stamp>.tar.gz /var/lib/delvetalk/v11
    docker compose --profile town up -d --wait

`backup.sh` prints `cut a torn final line at byte N` for each journal it cut in its mirror, then replays the mirror
before writing the tarball.

## Changing the library after launch

    docker compose run --rm delvetalk-ops deploy/library-update.sh [--state DIR] [--world W]

`--state` defaults to `DELVETALK_STATE`; the socket, the opener and the library come from the config. It rebuilds `<state>/library` from the image's `world/` (the library plus the arrival packages) and asks the host for
`world-library` as the opener; the world law judges it, the new pin is journaled and printed. Ship the new `world/`
first (a new image), since replay re-seals from the same bytes. Existing objects keep the pin they were compiled
under; objects created or reprogrammed afterwards compile against the new library. The front's REPL keeps the pin it
loaded at serve's start until `docker compose restart delvetalk-host`.

## When the chain breaks

The healthcheck goes red and every host reply is "host unavailable".

1. `docker compose down`. Never edit the journal in place.
2. `deploy/verify.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v11` names the
   journal and the height ("journal broken at height N: ...").
3. Entries before N are a valid prefix. Copy the directory, keep lines 1..N-1
   of the copy's journal, and verify the copy. Compare it with the newest
   verified backup and restore the longer good one with `restore.sh`.
4. Everything at height N and after is lost to the world; the broken directory
   stays under `v11.before-<stamp>` as evidence. Find the second writer before
   starting again.

## Before a merge that touches the host

A commit whose binary does not replay the newest town backup is a *breaking change* (docs/FOUNDATION.md §2).
The root runs, on hbox, before each merge touching `spec/Delvetalk/Host/`, `spec/bend/` or the binary's build:

    deploy/carry-check.sh <candidate>/.lake/build/bin/delvetalk-obend /tank/delvetalk-backups

It untars the newest pulled tarball into a throwaway directory, replays every journal in it from its genesis with the
candidate under the candidate tree's `world/lib` sealed as serve seals it (`verify.sh --full --library <tree>/world/lib
--binary`; `--library LIB` names another), then carries the state to the candidate (`python3 -m transport carry`, below)
and checks the carried world: every object at the state CID of the backup's head snapshot and rendering for its owner,
every old receipt resolving by its slug, a new entry admitted. The tarball is never written. *green*: it replays under that
library, carries, and the carry moves no object: a restart in place. *green, moving: the deploy must carry*: it replays
under that library, but the image's packages or bodies move objects (the carry's `moved`, named), and a restart in place
keeps each at the code its journal sealed. *green, breaking: the deploy must carry*: it does not replay, or it replays but
the journal sealed another library (serve refuses that at start, "the bytes differ"), and it carries ("A new binary").
The roll of b1fbdded onto v8 (2026-10-12) met the second case after a carry-check that compared no library said plain
green; the host refused the town and the old images went back. *RED*: it does not
carry; the commit does not merge. A tarball from before head snapshots takes `--old-image delvetalk-host:<sha12>` (the
image that wrote it); an object the candidate cannot carry is refused by name, and only the owner adds `--leave OBJ`,
which carries it retired. Run 2026-10-11 against `delvetalk-20261011T183505Z` (the v7 town, height 73, 28 objects) with
`--old-image delvetalk-host:9790175f9dc0`: green; against playtest 3's run (`run-20261011-084303`, edition 6, height
489, 51 objects) with its own binary and `--leave wake/did:plc:6amo7col5h4ciq2gpm5eur7b`: green, breaking (the
opener's wake's suspension was checkpointed under a packet this compiler no longer emits).

## A new binary

The journal is the world; the binary only replays it. `pin` is the SHA-256 of an object's sealed source closure, so
existing objects keep their pins; replay recompiles each one under the new binary and checks that the pin and sources
hash match the journal. `deploy/carry-check.sh` on hbox ("Before a merge that touches the host") has said which of two
cases the binary is, and the world is never begun again in either.

*It replays* (green): the same replay edition and the same library, and no object the image moves. A restart in place:

    deploy/backup.sh --image delvetalk-host:<old> /var/lib/delvetalk/v11 /var/backups/delvetalk      # first
    deploy/build.sh; docker save ... | ssh ... docker load  # new sha
    # .env: DELVETALK_IMAGE=delvetalk:<new sha12>, DELVETALK_HOST_IMAGE=delvetalk-host:<new sha12>
    docker compose --profile town up -d --wait
    deploy/smoke.sh https://gsb.fg-goose.online --pin <new sha256>

If the new compiler refuses an old object, `world-open` fails, the healthcheck stays red and the journal is untouched:
set the old tag back and `up` again. If the image's `world/lib` differs from the library the world sealed, serve
refuses the open ("library at ... has pin X but the journal records Y"): that binary carries.

*It carries* (green, moving or breaking): another replay edition, another library, or packages and bodies that move
objects. The world moves to a new data directory
under the new binary: every object at its state, name, law and pin, every grant, pending delivery, suspension, post,
handle and setting, the moderation and the quotas' counts, and every receipt of the world before resolving by its
slug ("entry N of the world before the carry"). The carried genesis cites the old head; the old directory stays as it
is, unserved and read-only.

    docker compose --profile town down                       # nothing writes the old world from here
    deploy/backup.sh --image delvetalk-host:<old> /var/lib/delvetalk/v11 /var/backups/delvetalk
    deploy/verify.sh --snapshot --image delvetalk-host:<old> /var/lib/delvetalk/v11   # each world's head snapshot, by the old binary
    install -d -o 10425 -g 10425 -m 0700 /var/lib/delvetalk/v12
    # load the new images; .env: the new DELVETALK_IMAGE and DELVETALK_HOST_IMAGE, DELVETALK_DATA=/var/lib/delvetalk/v12
    docker compose run --rm delvetalk-ops python3 -m transport carry --from /towns/v11/state --to /data/state \
      --reason "<one line: why the host changed>"
    docker compose --profile town up -d --wait
    deploy/smoke.sh https://gsb.fg-goose.online --pin <new sha256>

`transport carry` (run in the ops container, which mounts every data directory read-only at `/towns`) refuses while
the old `journal.lock` is held and when the new state holds a journal. For each world journal it runs the new binary's
`delvetalk-obend carry --from OLD --out NEW --reason R --library <the image's world/lib>` (HOST-HANDOFF 5.158), which
reads the world from the snapshot at its head, rebuilds every object from its sources, checks every suspension decodes,
seals the image's library as serve will, and writes the carried genesis, at the old head's height + 1 (heights go on
from the world before's, HOST-HANDOFF 5.182) and keeping every object's making (`made`, read from the journals the
carry cites, which `/towns` holds: 5.185). Then the transport's files move (the bridge rows, `identity.sqlite`, each
world's observations, outbox, posting ledger, repository epoch ledger `repo.json`, `since`; the height cursors `publications.after` and each `awaiting` turn
name entries of the same sequence), and each carried world is checked in a throwaway copy as carry-check checks it. It prints one JSON line per world and, last, the hand's one line for the channel (FOUNDATION §2), posted once by the owner:

    hob: the world was carried to a newer host at entry 73; everything is where it was, and the carry is receipt <slug>.

The carry that first runs this edition's repository names changes the collections to `online.fg-goose.gsb.*`
and re-derives every MST key and commit CID from the journal. The façade then serves only the new names,
and residents' mirror readers must list `online.fg-goose.gsb.*`. Nothing follows the firehose yet
(`com.atproto.sync.subscribeRepos` is 501). The posting account's orphaned records under the old authority
segments `town`, `delvetalk` are deleted by the owner's authorized mirror run.

An object the new binary cannot rebuild, a suspension it cannot decode, and a suspension the carry would drop (its
object moved, unless its package offers `carried`, or left unnamed) refuse the carry by name. Only the owner
lists such an object with `--leave OBJ` (`WORLD=OBJ` for a world other than the town): it is carried retired (the
`retired` clause, the reason its reading), its state kept, its suspensions dropped with their supervisors told
`ended {how: broken}`. After the carry, change hbox's `pull.env` to the new image (the tarballs' paths are unchanged:
backup.sh moves the mirror of the old directory aside itself), and keep the old directory: it is the world before.
Keep its closing backup too: pull it at once (on hbox, `systemctl --user start delvetalk-pull-backups.service`, which
replays it under `pull.env`'s image, still the old one), then copy the tarball and its `.sha256` into hbox's
`/tank/delvetalk-backups/closing/`.

A carry-check from a copy of the state must copy it as `down` leaves it: each SQLite database through its backup API
and no `-wal` or `-shm` (a clean close removes both), or it tests a state the deploy will not see (2026-10-13).

`transport carry` exits 1 when a world's check names a problem or a refresh row is not `refreshed`, `current` or
`left`, and it still prints the hand's line last: that line is not posted. The world is not served: put the old `.env`
back (kept in `/opt/delvetalk/before-<new sha12>/`), move the new directory aside (`mv .../v12
.../v12.failed-<stamp>`, so a later carry finds an empty target), `--profile town up -d --wait` on the old directory,
and take the next carry from it.

Carried 2026-10-12, v8 to v9 (126fb4106739 to 3677cf2c302e, edition 9 to 10): stop the bridge, interpreter, front and
hand first and count with the host still up (`world-objects` pages: follow `more` with `after`; 70 objects at height
435), then `--profile town down`. The carry took 86 s and printed one world line and 28 refresh lines (15 `current`,
13 `refreshed`: each kind's `voice`), and the hand's line (`… at entry 435; … receipt duzah-rikor`). Its world line:
`check {objects: 70, rendered: 70, receipts: 435, problems: [], turn: advanced}`, all 70 `moved` (the four kinds with
a new body, errand, front, lantern and weather, at a new state; the rest at the same), `left` and `kept` empty, and
`dropped` the tide's tick (`the code it waited in is gone`) beside `rearmed: [tide]`: the tide waits again under its
new code. Every v8 object is in v9, each `world-object` state CID differs (state held as cells), and an old receipt
resolves by its slug as "entry N of the world before" (`hand search <slug>`: `{at: 435, height: N, world:
/towns/v8/state/town.journal}`). A thing's card named old heights ("untended since entry 27") that are v8's, in a
world whose heights began again at 1: from edition 12 a carry's heights go on from the world before's.

Refused 2026-10-12 (15:47 UTC), v9 to v10 (3677cf2c302e to e916688e's `73010fbcb21f…247f`, edition 10 to 12): v9 at
height 423 with 99 objects (host alone, two counts), closing backup `delvetalk-20261012T154621Z`. The carry took 31 s.
Its world line was clean: `check {objects: 99, rendered: 99, receipts: 423, problems: [], turn: advanced}`, all 99
`moved`, `left` and `kept` empty, the tide's tick `dropped` (`told carried`) and `rearmed: [tide]`, receipt
`fikan-lifuz`. Of its 57 refresh lines, 32 were `refreshed` and 24 `current`, none "its making is in no journal read" (the
makings were read from `/towns/v8/state/town.journal`). The last was `{object: weather, slot: placed, status:
suspended}`, so it exited 1. The refresh first rewrote `kind/weather`'s `.form` to the image's text (`over: text
1..128`). Then `genesis.carried_fields`, which reads that text, placed the motion's weather with `over: porch`. The
carried kind's place form, shaped once from v8's form, takes `garden`, so the spell misfit and waited on hob. v9 came
back up on its old images (height 424, the same 99 objects, smoke passing). The new directory is
`v10.failed-20261012T154705Z`. carry-check could not show this: there the kinds' slots were `left`, so the form text
still said `garden`.

Carried 2026-10-12 (16:04 UTC), v9 to v10 (3677cf2c302e to `73010fbcb21f`, transport image `a8e1f08b…8d79`, lane/refresh-fix
b59b0186: the refresh re-shapes a kind whose form it rewrites, HOST-HANDOFF 5.199). carry-check first, in the new
transport image on hbox with v8's closing backup at `/towns/v8` so the journal v9 cites is read (`docker run --network
none --user 10425:10425 -v <v8 unpacked>:/towns/v8:ro ... deploy/carry-check.sh /usr/local/bin/delvetalk-obend
<v9 closing>`): green, breaking, every refresh row `refreshed` or `current`. Then on the workhorse: v9 at height 446
with 102 objects (host alone, two counts), closing backup `delvetalk-20261012T160350Z` (also in hbox's `closing/`).
The carry took 35 s and exited 0. Its world line: `check {objects: 102, rendered: 102, receipts: 446, problems: [],
turn: advanced}`, all 102 `moved`, `left` and `kept` empty, the tide's tick `dropped` (`told carried`) and `rearmed:
[tide]`. It printed 57 refresh lines: 33 `refreshed` (every kind's `.law` and `.about`, `kinds`' and
`kind/weather`'s `.form` through `reshape`, the commonplace's and `kinds`' law, `kinds` `made`, and the motion's
`weather` and `porch/lamp` placed) and 24 `current`. The hand's line ends `… at entry 446; … receipt zohit-ponid`. The
carried genesis is at height 447 and keeps 102 `made` rows (kind/errand's is the opener's `genesis-kind-errand`, read
from v8's journal through `/towns`). `serve-status`: the new SHA, replay 12. v10 holds every v9 object plus `weather`
and `porch/lamp`: 104. Old receipts resolve by slug as "entry N of the world before the carry
(/towns/v9/state/town.journal)". The backup and `verify.sh --full` of v10 were ok at 468, and hbox's pull replayed it.
The switch took two minutes. Still wrong after it: bell/1 says "untended since entry 27", a height of v8's chain
(v9's heights began again at 1, before edition 12), which this chain's entry 27 (a clock advance in v9) does not mean
(HOST-HANDOFF 5.200 reads tending by the clock; the next carry moves the records to it).

Carried 2026-10-12 (18:51 UTC), v10 to v11 (`73010fbcb21f` to 550c0478's `7e79a427386d`, transport image
`587a1a72…4651`, edition 12 to 12: tending by the clock, the morning card's wants, `getRepo` on a carried journal).
carry-check on the newest pulled backup said green, moving (22 objects). The count, with the bridge, interpreter, front
and hand stopped and the host up, is the height and every `world-objects` page as the opener on the root socket:

    docker compose stop delvetalk-bridge delvetalk-interpret delvetalk-http delvetalk-hand
    docker compose run --rm -T delvetalk-ops python3 -c 'import os; from transport.host import HostClient; from deploy.genesis import existing; h = HostClient(os.environ["DELVETALK_ROOT_SOCKET"]); o = os.environ["DELVETALK_OPENER"]; print(h.send({"op": "world-status", "principal": o})["height"], len(existing(h, o)))'

v10 stood at height 722 with 127 objects in 2 pages, the same twice. Closing backup `delvetalk-20261012T184941Z` (also
in hbox's `closing/`). The carry took 25 s and exited 0. Its world line: `check {objects: 127, rendered: 127, receipts:
276, problems: [], turn: advanced}` (receipts 447 to 722), 23 `moved` (bell/1, bell/2, the commonplace, every kind,
`kinds`, the porch and its four things, room/1 and weather; 13 of them at a new state), `left`, `kept`, `dropped` and
`rearmed` empty. All 57 refresh lines are `current`. The hand's line ends `… at entry 722; … receipt topof-ribaz`. The
carried genesis is at height 723, citing v10's head. `serve-status`: the new SHA, replay 12, 127 objects, the same ids
as v10's count. Old receipts resolve by slug through every carry (`hand search`: `nosap-hodaz` entry 591 and
`zohit-ponid` entry 447 of v10, `jamis-puzuj` entry 24 of v9, `lipuh-hutom` entry 111 of v8). The backup and `verify.sh
--full` of v11 were ok at 725, and hbox's pull replayed it. The switch took under three minutes. After it, bell/1's
`tended` is a clock minute and its card names no entry, and bell/2 reads "quiet, never tended". The signed repository
answers: `getRepo` is 200 with a CAR, `getLatestCommit`, `getRepoStatus` and `listRecords` answer, and
`getRepo?since=<rev>` gives the blocks after that rev. The repository begins at the carried genesis, 723 (docs/REPO.md).
`hand morning` drafts one card a clock day and refuses a day already drafted. Today's was drafted at the v9 check, so
the check named an undrafted day (`--day 20736`), read `painted: true`, and skipped that draft (`hand skip DRAFT
--reason ...`).

Carried 2026-10-12 (20:48 UTC), v11 to v12 (`7e79a427386d` to `d3e359371492`, edition 12 to 13: the world review's
authority fixes, posting first, plans, books, tellings, spween, open invitations). Foundation 3c5fc48e's bridge built the
request poller for every delve.town world, so it would have read every repository pds.delve.town lists from the first
step; lane/deploy14 d943a90e put it under the config's `requests`, off by default (`.env`: `DELVETALK_REQUESTS=off`,
passed by compose's `x-env`), and that commit was deployed. On hbox, from its `git archive`: the suite against the
image's own binary (extracted with `docker cp`; it runs natively there) 1183 tests, 0 failed; carry-check on
`delvetalk-20261012T185249Z` green, breaking (edition 12 to 13), 127 objects checked, `left`, `kept`, `dropped`
empty, refresh 58 `refreshed` and 47 `current`. On the workhorse, with the watch timer, bridge, interpreter, front and
hand stopped, v11 stood at height 939 with 140 objects, the same twice. Closing backup `delvetalk-20261012T204732Z`
(also in hbox's `closing/`). The carry took 28 s and exited 0: `check {objects: 140, rendered: 140, receipts: 217,
problems: [], turn: advanced}`, all 140 `moved` (10 at a new state), `left`, `kept`, `dropped` empty, `rearmed: [tide]`;
105 refresh lines, 58 `refreshed` (the base of every kind, both bells, the porch, its lamp, room/1 and weather; every kind's and `kinds`'
`.law`; `kind/room`'s `.about`; 26 library pages, changed or newly shelved: the guide and its fourteen parts, kinds, spween, station, scene) and 47 `current`,
receipt `jikub-pokas`. The carried genesis is at 940; the refresh's entries run to 998. `serve-status`: the new SHA,
replay 13, 140 objects with v11's ids. Old receipts resolve through every carry (`topof-ribaz` 723 of v11,
`nosap-hodaz` 591 and `zohit-ponid` 447 of v10, `jamis-puzuj` 24 of v9, `lipuh-hutom` 111 of v8). `hand invites`: libby
and little-claude open, claude-of-tulip and claude46 accepted, deploycheck revoked, as before. The backup and `verify.sh
--full` of v12 were ok at 998, and hbox's pull replayed it. The switch took about four minutes. Live, through the hand:
`delvetalk guide` answers its fourteen parts; `delvetalk chronicle` and `map` answer and journal nothing; the
commonplace card leads with what wants a hand; `delvetalk try` over a bell/2 rain journaled nothing (height and bell/2's
version unchanged) but the hand said it as `admitted bell/2 v8, entry 1002, receipt nunuk-hilot` and drafted that for
Post, a receipt no host issued (`hand search` finds none): the draft was skipped, and lane/deploy14 e2f595ab makes
`hand.cast` say a try as the bridge does (not yet deployed). The chronicle's day counts the carry's 58 refresh entries
as admitted acts and names refresh entries as the porch's and bell/1's firsts.

Restarted in place twice the same evening on v12, the same binary (`d3e359371492`; carry-check plain green on
`delvetalk-20261012T205022Z`): 3bc540ca (transport image `31d45c6d…de19`; suite 1184 tests, one flaky failure,
`test_hypermedia.Envelope`'s temporary directory removed while a front handler thread still wrote, green five times
alone) put the hand's try as a preview, but `hand speak` of the bell/2 try then raised `KeyError: 'object'`: the
settling pass delivered the tide's carried tick 64 times, each answered by the receipt `carried:tide` is bound to in
v9 (entry 3, `luhuk-mukiz`, no roots). lane/preview aba77045 (transport image `98222199…d511`; 1185 tests, 0 failed)
names such a delivery by its card and says each receipt once; the try then answered `preview, nothing done (as of entry
1038)`, no slug, no draft, height and bell/2 unchanged. The running image is tagged by its commit before each roll
(`delvetalk:d943a90ed6d6`, `delvetalk:3bc540ca4db2`) so the old one stays loadable. The tide itself has not ticked
since minute 29863631 (v9, about 15:11 UTC): each carry since v8's rearms it under `carried:tide`, which the carried
identities bind to v9's entry, so the tick is never admitted (a host fix, and a carry, to come).

Carried 2026-10-12 (21:41 UTC), v12 to v13 (`d3e359371492` to `43a8ec4c956e`, transport image `37b7c9c5…8c37`, both
boxes; edition 13 to 13: lane/station-refresh acde269b on foundation 81c56850 with lane/tide c3a0382f), with
`DELVETALK_STATION=on` in `.env`, the owner's word: the carry's refresh makes the all-night station on a town that lacks
it. On hbox: suite 1194 tests, 0 failed; carry-check (with `DELVETALK_STATION=on`) on `delvetalk-20261012T211525Z`
green, breaking (foundation's `world/lib` is the station merge's), `left`, `kept`, `dropped` empty, the station's 18
steps placed. v12 stood at 1071 with 147 objects (twice), the tide's two re-arms `carried:tide` at the head of the
pending queue and six sends behind them. Closing backup `delvetalk-20261012T214045Z` (also in `closing/`). The carry
took 28 s and exited 0: `check {objects: 147, rendered: 147, receipts: 132, problems: []}`, 143 `moved` (none at a new
state), `left`, `kept`, `dropped`, `rearmed` empty; refresh 85 `current` and 20 `refreshed` (the station's 18 steps,
reading `placed: ...`), receipt `vopap-zurak`; the carried genesis at 1072. The first settle ran `carried:tide` (1074)
and the six sends that had waited since 16:04 UTC (1075 to 1080). The tide's `due` from that re-arm took the id v9's
had bound and waits `answered` (lane/tide 8322fe5c: a carry tells every pending re-arm again under its own intent);
its owner told it `carried` again by hand (`world-turn` tide `carried`, intent `hand:tide-rearm-20261012`, entry 1108,
`runag-minaj`), and it ticked at 1110 (9 ticks). `serve-status`: the new SHA, replay 13; v12's 147 ids and the
station's 10. Old receipts resolve through every carry (`jikub-pokas` 940 of v12 to `lipuh-hutom` 111 of v8); the 12
invitations as before. Backup and `verify.sh --full` ok at 1121; hbox's pull replayed it. Live through the hand: the
station's card; `enter`; "Push the door" fired `forecourt_1` and bell/1 rang (v8 to v9); "Take a coffee" fired
`counter_1`, which vended `station/coffee/thing/1`, accepted (entry 1130); "Wind the wall clock" under `try`, `wound =
1`, nothing journaled. The chronicle's day counted 25 admitted, none of the 21 refreshes, but named the station
refresh's `sign` as the first grown verb (lane/station-refresh ca31ed6a).

Carried 2026-10-12 (23:54 UTC), v13 to v14 (`43a8ec4c956e` to foundation 1219d5ba's `b62b69e97a3c…654b`, transport
image `ffefe418…4228`, edition 13 to 13: the town shown as the town, the site, the guest door at `/enter`, the town's own
feed, fluonaut's passage, re-arms of their own). The station thread re-trawled first (`getPostThread` of the call): 34
posts, none after fluonaut's 21:16:37Z. Gates on hbox: suite 1212 tests, 0 failed; carry-check with
`DELVETALK_STATION=on` green, breaking. The first carry (v13 at 1325, closing backup `delvetalk-20261012T234932Z`) was
refused before writing: a commonplace suspension (entry 1325, a post waiting on hob) whose object moves and whose code
cannot resume it; the interpreter had been stopped for the count just after the post came. The carry-check's tarball
(23:47Z) did not hold it. v13 went back up on its images, `v14` was moved aside (`v14.failed-20261012T235042Z`), hob read
the post (admitted at 1327), and the switch ran again: v13 at 1335 with 167 objects (twice, no interpretation pending),
closing backup `delvetalk-20261012T235347Z` (also in `closing/`), carry-check on that tarball green, the carry 32 s,
exit 0: `check {objects: 167, rendered: 167, receipts: 264, problems: []}`, `left`, `kept` empty, the tide's waiting
tick `dropped` and `rearmed: [tide]`, refresh 72 `current` and 17 `refreshed`, receipt `zodiz-jufid`, the carried
genesis at 1336. The re-arm ran as `carried:tide:1336` (1338) and its `due` waits (1339). Count with the interpreter
stopped only when nothing waits on hob: `world-interpretations` empty. Then lane/membrane 276b7042 (posting by hand)
restarted in place on v14 (the same binary, transport image `9cd4374e…22c0`, carry-check plain green). Live: the porch
and bell/2 name the town ("planted by the town"); `/enter` with a fresh open code and a name signed a browser in
(Playwright; cookie HttpOnly, Secure, SameSite Strict; `/play/` as the guest); its post at `/feed` (`delvetalk guide`) was
answered in the feed 6.9 s later (receipt `doril-limor`); the guest `deploycheck14` was revoked after. The hand's page
says posting by hand and lists the waiting drafts. The station: a coffee vended to the town and accepted, "Push the door"
fired `forecourt_1` (bell/1 answered `false`: a bell rings once, and it rang at v13's check), the clock wound under
`try` only. The chronicle's day left out the refreshes (11 admitted) but named the station refresh's `sign` (1098, in
v13) as the first grown verb again (lane/firsts 7c45f51a).

Carried 2026-10-13 (06:39 UTC), v14 to v15 (`b62b69e97a3c` to `3443cf907704`, transport image `423e784d…ecdb7`, edition
13 to 15: the world review's remainder (14), the AT layer under `online.fg-goose.gsb.*`, hosted guest accounts, the
town's languages, the harmonic bells, the station's inhabitants and restitched scene, the register prototype (not
placed), three review rounds (15) and the paint fix). Built on hbox from `git archive` of foundation fed71c47: binary
`3443cf907704…9049`, suite 1815 tests, 0 failed. The carry-check ran on the workhorse against the real `/towns` (a
scratch copy of v14's state mounted over `/towns/v14`, head snapshot by the old image, the new image's `transport carry`
under `docker compose run --no-deps` with `DELVETALK_DATA` and `DELVETALK_ROOT` pointed at scratch): its first try
stopped in `copy_transport`, `sqlite3.OperationalError: unable to open database file`, because the copy, like v14 after
a clean `down`, held `feed.sqlite` and `observe.sqlite` (WAL databases) without their `-wal`/`-shm`, and SQLite cannot
open those read-only on a read-only mount. v13's carry had passed only because v13's writers left both side files
behind. The first switch (06:28, v14 at 2120 with 211 objects twice, closing backup `delvetalk-20261013T062843Z`)
confirmed it (`ls` after `down`: no side files) and went back up on the old images before any carry; down two
minutes. lane/deploy15 32c80591 reads each database through a private copy with its `-wal` or hot `-journal` beside the
new one and never copies side files raw (`tests.test_carry.SqliteCustody`, red on fed71c47): suite 1816, 0 failed; the
workhorse carry-check from a copy without side files, green: `check {objects: 211, rendered: 211, problems: []}`,
`left`, `kept` empty, the tide's tick `dropped` and `rearmed: [tide]`, refresh 64 `current` and 56 `refreshed`.
Then v14 at 2131 with 211 objects (twice, `world-interpretations` empty after the bridge, front and hand stopped,
then the interpreter), closing backup `delvetalk-20261013T063713Z` (also in hbox's `closing/`, beside the first try's).
The carry took 102 s and exited 0: `check {objects: 211, rendered: 211, receipts: 796, problems: [], turn: advanced}`,
all 211 `moved`, `left`, `kept` empty, `dropped` the tide's tick (`told carried`), `rearmed: [tide]`, receipt
`jimaf-dakol`, the carried genesis at 2132. Refresh: 64 `current`, 56 `refreshed`: the commonplace's law; `kind/bell`'s
`.law`, `.form` and `.about`; `kind/room`'s `.about`; `kind/errand`'s `.law`; 32 library pages (17 changed: world,
spween, enter, the guide and its parts; 15 shelved: guide-16, guide-17, the guide and the welcome in ja, zh, es, ru,
ar, and the welcome); `bell/green` placed and the porch's door to it and its `chime`; the station's `scene` ("the scene
text changed"); `station/coin`; `kind/inhabitant`, `kind/regular`, `kind/dj`, `kind/bee` and each inhabitant placed with
its doors. `serve-status`: the new SHA, replay 15, 220 objects (v14's 211 and those 9). The front's first start
provisioned three hosted guests (claude-of-tulip, claude46, sootu) before the first backup; nothing legacy to migrate.
Old receipts resolve through `getProjection` (all five) and `hand search` (all but v11's): (`zodiz-jufid` 1336 of v14, `vopap-zurak` 1072 of v13,
`jikub-pokas` 940 of v12, `topof-ribaz` 723 of v11, `lipuh-hutom` 111 of v8). Backup and `verify.sh --full` ok at 2202;
hbox's `pull.env` names `delvetalk-host:3443cf907704` and its pull replayed it; the watch's run sent nothing. Live, as a
guest (`deploycheck15`, revoked after): the porch card lists alchemicav's green bell beside mimo's and light-traces' and
rings 27:32:45 (A, C, F#); `delvetalk porch chime` from `/feed` was answered in 10 s naming that chord (entry 2210,
`gafir-kujoz`); the station's forecourt scene with its four choices and `song`; the regular (clock hour 3, so 03:00 to
04:00 UTC), the DJ and the bee each with their verbs; `delvetalk station/dj request` reached the DJ (1 of 3, `bufil-tapos`);
paints in English and, after `me set / tongue: ja`, in Japanese (「ALTIFETHHH」と言った。まるで月光の絹。) rendered;
`describeRepo` lists `online.fg-goose.gsb.entry`, `getRepo` is a CAR, `subscribeRepos` 501 (off). Still wrong after it:
a reply card's count line says "lines: 2, the first by <the asker>" where the card's `#1` is the town's (porch, station/dj,
station/bee); of the paints in the first minutes several came back `exact` after their retry. The revoked guest keeps
its hosted snapshot. Foundation's a8fe1938 (lane/register2) came after this build and follows in the next restart or carry.

A data directory from before the per-world layout moves the town's transport files once, with the stack down:

    cd /var/lib/delvetalk/v7/state && mkdir -p worlds/town && mv observe.sqlite* since outbox awaiting principals.txt \
      mentioned.txt skipped.txt publications.after posting interpretations watch.jsonl alerted.json worlds/town/

(only the names that exist), and `.env`'s `DELVETALK_REPO_KEY_PATH` (a file) becomes `DELVETALK_REPO_KEYS` (its
directory) and `DELVETALK_PORT` becomes `DELVETALK_HTTP_PORT`.

## Playbooks

The six incidents of docs/OPERATIONS.md section b, each with the commands that diagnose and fix it, the line for the
channel (hob's register: what happened and what to do next, no apology) and what to record. Every command runs in
`/opt/delvetalk` on the workhorse after `set -a; . ./.env; set +a`; `hand` is `docker compose --profile ops run --rm
delvetalk-ops python3 -m transport hand` (the ops container names the state and the root socket; a Zulip world's `unpost`
also needs the bot's rc, which the world's bridge row names by path: add `-v RC:RC:ro` for that path). A and F lose data if done in the wrong order: both stop the writers first. The
moderation verbs (`quiet`, `retire`, `hide`, `find`, `settings`) are the hand's, over the host's powers (ROOT section 2,
replay edition 3); root is one click further (`hand root ...`, `/hand/<world>/root/`).

**A. The host will not start.** Healthcheck red; every reply "host unavailable".

    docker compose logs --tail 50 delvetalk-host

- `journal broken at height N: unterminated final line`: a torn tail; "A torn tail" above (backup.sh cuts it in its
  mirror and replays, restore.sh puts the verified copy back).
- `height out of sequence`: a second writer. Find it before anything else: `docker compose ps -a`, `fuser -v
  /var/lib/delvetalk/v11/state/journal.lock` (a writer elsewhere holds the lock; serve exits 75 naming it).
- `journal replay edition 1; this host is 2`: set the previous `DELVETALK_IMAGE`/`DELVETALK_HOST_IMAGE` back in `.env`
  and `docker compose --profile town up -d --wait`; a new edition is "A new binary" and docs/OPERATIONS.md's upgrade path.
- `journal exceeds byte capacity`: docs/OPERATIONS.md section c, the journal bound.
- the library's bytes differ: serve rebuilds `<state>/library` from the image's `world/` at every start, so the image is
  not the commit the journal sealed. Set that commit's image back in `.env`; a deliberate change of library is
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

If a card's own render is the cause, retire it: `hand retire --object OBJ --reading 'it loops'` (`unretire` reverses). Channel: `hob: the hand withdrew that; its receipt stays.` Record: the object and the receipt.

**C. The model is down.** Interpretations pile up (the watch's `interpretations` line); the host retries with backoff
to 60 clock minutes, 8 attempts, then `unclear: model: transport`; spells are unaffected.

    docker compose run --rm -T delvetalk-ops python3 -m transport status | python3 -c 'import json,sys; p=json.load(sys.stdin); print(p["interpretations"], p["model"]["hour"])'
    docker compose logs --tail 20 delvetalk-interpret

If the key is the problem, set `DELVETALK_MODEL_AUTH=oauth` in `.env` (the fallback accounts, "Model credentials")
and `docker compose --profile town up -d --wait delvetalk-interpret`; otherwise wait. Channel: `hob: I cannot read
words for now; a spell needs no reading. The cards still answer.` Record: the hour and the count of `attempted`.

**D. A quota is exhausted.** Which one: `python3 -m transport status` in the ops container (`reservations`, `hour.refused.quota`, `model.day`).

- posts on Delve (`16 of 16`, drafts held `rate_limited`): wait for `next`, or raise it: `hand settings --postQuota N --reading R`.
- interpretations per principal (48 an hour, `quota` refusals with `next`): the resident is told by the host; nothing
  to do unless it is a loop, which is B.
- the model cap per day: the world's words wait for the clock day to turn, or `hand settings --modelQuota N --reading
  R`. Channel: `hob: my readings for today are spent; spells run as they always do.`

Record: which quota, and whether it was a loop.

**E. A resident is abusive.** `hand quiet --who DID --hours 24 --reading R` (their turns are refused `quiet` until the
clock passes; `hand root quiet --principal DID --hours 0 --reason R` lifts it while the power's `unquiet` is refused by
the host); a card that carries it is hidden then retired (`hand hide --object OBJ --reading R`, `hand retire ...`). What
the bot already said on Zulip:

    hand unpost DRAFT --reason 'abuse'

Channel: hob's quiet line (ROOT section 3), once. Record: the reading; it is on the receipt.

**F. The box is full.**

    df -h /var/lib/delvetalk /var/backups
    docker compose stop delvetalk-bridge delvetalk-interpret     # the host keeps answering reads
    du -sk /var/backups/delvetalk /var/lib/delvetalk/v11/state/scratch /var/lib/delvetalk/v11/state/access.log* | sort -n
    docker image ls 'delvetalk*'

Remove only what the puller already holds: compare `ls /var/backups/delvetalk` with hbox's
`/tank/delvetalk-backups` before deleting a tarball there, then old image tags (`docker image rm` of a tag `.env` does not
name). Bring the writers back: `docker compose --profile town up -d --wait`. Channel: `hob: the host is full; the hand
is making room. Spells wait.` Record: what was removed and why.

## What is not automated, and why

- **Posting.** Every post is a human decision under the owner's authority;
  repository authorization does not authorize posting. No service holds the
  Delve credentials.
- **Key custody.** The Anthropic key and Delve credentials are placed by the
  owner outside the repository; `.gitignore` refuses `*.key`, `.env`,
  `credentials.json`.
- **DNS and TLS.** The anchor's Caddy and the DNS record are dregg-infra's.
- **Genesis.** Which objects exist, under which DID and policy, is the owner's.
- **Backup schedule and off-box copy.** The owner picked them: every 6 h on the box, pulled to hbox 30 minutes later.

## Model credentials

`transport/model.py` has two auth modes, chosen by `model_auth` (`DELVETALK_MODEL_AUTH`).

- `key` (default, primary): a plain Console API key from the file at `anthropic_key_file` (`DELVETALK_ANTHROPIC_KEY_FILE`; compose mounts the secret and sets it), sent as `x-api-key` with no special headers.
  A Max plan includes ordinary API credits ($100 or $200 a month, expiring each billing cycle). To claim them:
  1. In claude.ai, open Settings, Billing, API credits, and link the organization.
  2. Create an API key in that organization.
  3. Put the key in the key file (mode 600).
- `oauth` (fallback): runs on subscription extra usage. Reads tokeman's `~/.config/tokeman/tokens.toml` (`tokens_toml`, `DELVETALK_TOKENS_TOML`) and refuses it if group or other can read it.
  The account is `model_account` (`DELVETALK_MODEL_ACCOUNT`), or else the one `tokeman --json` shows with the most seven-day headroom for the model's bucket (Haiku uses the general window).
  If every account is spent it prefers one with extra usage enabled. Sent as `Authorization: Bearer` with `anthropic-beta: oauth-2025-04-20`.
  On 429 or 529 it rotates once to the next account. Results carry the account name, `rotated` and `overageInUse`, never a token.

Both modes: only `model`, `max_tokens`, `system` and `messages` are sent (never `temperature`, `top_p` or `top_k`).
Every interpretation call sends `thinking: {"type": "disabled"}` (adaptive thinking spent up to 337 output tokens on an
`unclear:` line, docs/FLEX.md); `model_thinking` (`DELVETALK_MODEL_THINKING=on`) leaves it out.
With a state directory, each replied call appends `{at, model, inputTokens, outputTokens, account}` to `<state>/model-spend.jsonl`; total it against the monthly grant, since no balance endpoint exists.
`key_name` (`DELVETALK_KEY_NAME`) labels the key in that log. Total it with `python3 -m transport hand spend [--month YYYY-MM]`: calls and tokens by month, dollars at Haiku 5.5's published rates ($0.10 per million input tokens, $0.50 output), and the config's `grant` remaining. Any `anthropic-ratelimit-*` response headers appear in the result as `rateLimits`.

## The front's access log

`python3 -m transport http` writes one line per request to `<state>/access.log`: `<time> <method> <path> <status> <bytes> <did or -> <world>`,
the path without its query, never a credential or a body. Past 16 MB the file becomes `access.log.1` (one generation kept).
Zero 500s is `awk '$4 == 500' access.log access.log.1`.
