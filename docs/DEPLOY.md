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
| `deploy/seed.py` | `world-create` of one object from `world/` |
| `deploy/backup.sh`, `restore.sh`, `verify.sh` | journal custody |
| `deploy/smoke.sh` | the newcomer's journey against an origin |

The world's opener is ember's DID, `did:plc:6amo7col5h4ciq2gpm5eur7b`, set as
`DELVETALK_OPENER` in `.env` (config `opener`, which `transport serve` hands to serve's `--opener`); only the opener may create objects with
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
`--library` (the image's `world/lib`) and `world/objects/{Avatar,Env,Wake}.obend` (the packages `world-arrive` creates
from) and seals it into each world at its first open (the opener may change it; a scratch world starts with it sealed), so packages
import `./Plan.obend` and the rest by name. Every world of the directory is opened at start and held (a held world is
its live state, not its journal), so a turn in one may read another's objects.
The other programs are clients (`transport/host.py`, 99 lines): stop, start or run them at any time without touching
the world.
The lock holds where one kernel sees the file: a local Linux
filesystem (measured on ext4). Docker Desktop's file sharing on a Mac does not
enforce it across containers (measured), so test the stack there on a named volume.

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
- The data directory `DELVETALK_DATA`, `/var/lib/delvetalk/v7` since the fifth fresh genesis of 2026-10-11 (7300d494,
  replay edition 8; the worlds before it stay unserved: edition 1 in `v2`, then b14df72e's `v3`, 6cd1f491's `v4`,
  89abbd8d's `v5` and 103837ce's `v6`), owner `10425:10425`, mode 0700 (the image's uid, next in the edge's series), with
  `state/` inside it made the same way. compose's default is `v7` too; `.env` names it anyway. On ext4 or ZFS, local disk: see "Durability".
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
`9790175f9dc0cf4ea2da63bd576cf3eb63328715f8cddaa9d372864ba4d15f37` (hbox). The Lean compile runs inside dockerd's
build, outside a `swarm-build` cgroup around the client; the Dockerfile's own
two-slot wrapper is what bounds it. Everything the build reads is pinned (base images by digest, Debian
packages by snapshot, elan and the Lean tarball by SHA-256).

## First start

On the workhorse, in `/opt/delvetalk`, with this `.env` (mode 0600):

    # DELVETALK_HOST_IMAGE is the backup timer's replay image; DELVETALK_ORIGIN the portal and the did:web host;
    # DELVETALK_WATCH_ZULIPRC the watch bot's rc (owner 10425, mode 0400; "Watching")
    DELVETALK_IMAGE=delvetalk:<sha12>
    DELVETALK_HOST_IMAGE=delvetalk-host:<sha12>
    DELVETALK_OPENER=did:plc:6amo7col5h4ciq2gpm5eur7b
    COMPOSE_FILE=compose.yml:compose.hand.yml
    DELVETALK_ORIGIN=https://gsb.fg-goose.online
    DELVETALK_DATA=/var/lib/delvetalk/v7
    DELVETALK_REPO_KEYS=/etc/delvetalk/repo
    DELVETALK_WATCH_ZULIPRC=/etc/delvetalk/watch.zuliprc

`DELVETALK_REPO_KEYS` is the directory of `<world>.key`, the repositories' signing keys. No comment after a value: compose
and the shell strip one, but systemd's `EnvironmentFile=` (the backup unit) keeps it as part of the value, and the backup
then failed `docker: invalid reference format` (2026-10-11, this template's own inline comments). compose's default data
directory is `v7`, the workhorse's since 2026-10-11; `.env` names it anyway. The hand's token is a file (below), never a line here; the
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
`/.well-known/did.json` then names as `#atproto`; the front does not start without the file, so a box deployed
before the signed repository makes it the same way before its next `up`):

    install -d -m 0700 -o 10425 -g 10425 /etc/delvetalk/repo
    docker compose run --rm delvetalk-ops python3 -m transport repokey

It writes `<repo_keys>/town.key` (`--world W` another world's `W.key`; `--curve secp256r1` the other curve).

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
- *Another replay edition* ("journal replay edition 1; this host is 6"): nothing converts it, `migrate` included. It is
  a new genesis into a fresh data directory (OPERATIONS section b, "The upgrade path"); the old directory is kept as it
  is, served read-only by its own old image if its receipts are to resolve. Done 2026-10-11 (b14df72e into `v3`, the
  edition-1 world left unserved in `v2`, so its receipts stop resolving): `docker compose --profile town down` on the
  old files (a plain `down` leaves the exited `town` interpreter), one closing backup of the old directory with the old
  unit, scripts and image, `mv /var/backups/delvetalk/mirror /var/backups/delvetalk/mirror.<old>-<stamp>` (backup.sh's
  `rsync --delete` into `mirror/` would otherwise erase the old world's copy; backup.sh now records the mirror's
  source in `mirror.source` and moves a mirror of another directory aside itself), the old `.env`, compose files, scripts
  and units copied to `/opt/delvetalk/before-<sha12>/`, then the new files, `.env` with the new `DELVETALK_DATA`, and
  this section from here. Done again the same day (6cd1f491 into `v4`, `v3` kept unserved with a closing backup at height
  920, 225 objects): the repository key carries over in place (`DELVETALK_REPO_KEYS` is the same `/etc/delvetalk/repo`, so
  `did:web` and its `#atproto` key are unchanged; never regenerate it), and the old mirror was moved aside by backup.sh's
  `mirror.source` guard, written by hand once (`echo /var/lib/delvetalk/v3 > /var/backups/delvetalk/mirror.source`) since
  the previous backup.sh predated it.

    docker compose up -d --wait delvetalk-host
    docker compose run --rm delvetalk-ops python3 -m deploy.genesis --root-socket /run/delvetalk-root/root.sock

`deploy.genesis` is docs/GENESIS.md as one command (the transport image carries `deploy/` and `capsules/pages/`, so it
and `deploy/library-update.sh` run in `delvetalk-ops`). The opener arrives first (`world-arrive`), then
creates `policy`, `commonplace` (the town's first card, a record), `tide`, `workshop`, `kinds`, `anthology` and `library`;
`kinds` makes ten kinds (`kind/record`, `bell`, `cistern`, `room`, `porch`, `garden`, `weather`, `door`, `lantern`,
`bond`); then the opener places `garden`, `rooms`, `porch`, `weather` and `bell/1` from their kinds by spell (`kind/<k>
place`), lays the doors of `garden` and `porch`, and creates the porch's three things to inspirit, `porch/goblet`,
`porch/ring` and `porch/gemstone` (`deploy/genesis.py` `seeds`); the opener's `wake/<did>` is given `arrived` and a
schedule calling `tide.tick` every 60 clock minutes; the commonplace is given its body (`world/bodies/`); the library
shelves its pages. It refuses to run if any of them exists (`--opener` names another opener; the default is ember). It
prints one line per created or spell-made object (`created`, `admitted`) and nothing for the turns after; a page that
was not published is named on stderr. Deployed on foundation 89abbd8d: seventeen lines, 19 s, height 73 and 28 objects
at the bridge's first poll; on 103837ce the same seventeen lines in 22 s, height 73 and 28 objects. The rehearsal seeds the same way. `deploy.seed` creates one further object by hand.

**No wipe.** The world is never begun again while one lives (docs/TENURE.md section 1). `deploy.genesis` lists every
world journal under `/var/lib/delvetalk` (`DELVETALK_TOWNS`, mounted read-only into `delvetalk-ops` at `/towns`): a data
directory's `state/*.journal`, an older layout's, a playtest run's, but not scratch worlds and not the journal it is about
to write. If any holds an entry, genesis creates nothing and exits 1, naming each journal and its height: a world
changing hosts is carried ("A new binary"), never begun again. Only the owner's word begins one anyway:
`--wipe-with-the-owners-word R`, one line, which genesis writes on the commonplace and admits as the town's first line
before anything else is said there, and which is the first line of the welcome. A first town on a new box has nothing
under `/var/lib/delvetalk` and needs no word. Without `--towns` (and no `DELVETALK_TOWNS`) genesis refuses to guess and
exits 64.

Genesis is not one transaction: if it stops partway (a traceback, a refused create), the objects it made stay and a
second run refuses ("genesis has already run here: ..."). Before anything is posted, start again: `docker compose down`,
move `state/` aside (`mv /var/lib/delvetalk/v7/state /var/lib/delvetalk/v7/state.failed-<stamp>`; a `state.failed-*`
directory is not a town to the guard above), fix the cause, and run this section from `up -d --wait delvetalk-host`.

The commonplace cites eight doors: GARDEN, ROOMS, WORKSHOP, TIDE, PORCH, ANTHOLOGY, KINDS and STUDIO (a link to
`<origin>/AGENTS.md`, with no object). Genesis then has each door's object publish its page (`publishPage {page}`, the
page the door's word capitalized), so the outbox holds seven drafts once the bridge has run: `wiki: Garden`, `wiki: Rooms`,
`wiki: Workshop`, `wiki: Tide`, `wiki: Porch`, `wiki: Anthology` and `wiki: Kinds`. STUDIO has no page.
Post each with `--object <object>`; that records the post for the object, so replies to it route there. A door whose page
was not published is named on stderr. `hand outbox` lists the drafts; `--draft` reads the text from the outbox file itself,
so each page is

    docker compose run --rm -v /etc/delvetalk/delve/credentials.json:/run/delve.json:ro -e DELVETALK_CREDENTIALS=/run/delve.json \
      delvetalk-ops python3 -m transport post --draft /data/state/worlds/town/outbox/<n>-pub-<id>.json --intent <id> --object <object>

(dry run first, then with `--i-am-ember-and-authorize-posting`, which with `--draft` also marks the draft posted), or
`hand post <n>-pub-<id> --object <object>`, which posts, records and marks posted in one.

The bridge observes nothing posted before its first start: a state that has observed nothing writes `<state>/worlds/town/since`
(now) on the first poll, and posts older than it are never observed (`bridge --since ISO` replays deliberately). So
after genesis the journal holds genesis and the opener's arrival (the Avatar named by the DID, `env/<did>`, `wake/<did>`)
and nobody who posted earlier, and the outbox holds only the seven page drafts. (The deploy of a3e1fb2 read the whole town on its first poll: 124
objects and five reply drafts to posts older than the world.) Posts made after `since` do arrive: the deploy of
18f1de9 had genesis at height 25 and, within its first two polls, two bots' replies (berduck, dougbot) made each an
Avatar, Env and Wake (heights 30 to 40) and were skipped with no draft.

    docker compose --profile town up -d --wait --remove-orphans
    docker compose ps

`delvetalk-interpret` is in the `town` profile, kept on purpose so a stack without the model key still comes up: every `up` that should run it names `--profile town` (as here, after a restore and after a new binary); without it the interpreter does not start and interpretations wait.

`--wait` fails red unless every healthcheck passes: the host answers `world-status` with a height, `/AGENTS.md` answers
and the home page shows `entry <n>` (a refused `world-open` shows `entry None`), the bridge's and interpreter's pid files
are fresh, and the hand answers a tokenless `/hand/` with 404. `docker compose ps` shows all five `(healthy)`. Then
`docker compose run --rm delvetalk-ops python3 -m transport hand status` (the journal height, the host pid) and
`serve-status` are the host's own word: the binary's SHA-256, its pid, `replay` (the edition: 6 since
host18's redelivery), the sealed library's pin, and per world its height, objects, clock, `replay` and `snapshot {resumed,
refused}` (the height it reopened from: 0 is a replay from genesis). The DID document and the signed head:
`curl -s <origin>/.well-known/did.json` names the `did:key` `transport repokey` printed as `#atproto`, and
`com.atproto.sync.getLatestCommit?did=did:web:<host>` answers `{cid, rev}`; the commit block in `getRepo`'s CAR
verifies under that key (`transport.atproto.sign.verify`). From the laptop:

    deploy/smoke.sh https://gsb.fg-goose.online --pin <sha256> --handle <you>.delve.town

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
the post they answer, the post beside an editable textarea of the draft, with three buttons: **Post** runs
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
- `outbox [--all]`: drafts grouped by the post they answer (`--all` includes posted and skipped).
- `draft DRAFT`: the post, the draft text and its receipt line (`show` is the moderation power that reverses `hide`).
- `edit DRAFT --text-file F | --stdin`: replace the draft text, keeping the original.
- `post DRAFT [--object ID]`: post it, record it with the host for its object (or `--object`), mark it posted.
- `skip DRAFT --reason R` and `hold DRAFT`: take it out of the outbox with a reason, or leave it.
- `status`: the readable strip: height, posts this hour, model spend, pending interpretations and retries, host pid.
- `spend [--month YYYY-MM]`: calls and tokens by month, dollars at Haiku 5.5's published rates and the grant remaining.
- `search SLUG`: resolve a receipt slug with `world-resolve`.
- `retry URI`: forget that the bridge skipped an observation, so the next run routes it again.
- `reply URI --text-file F --object ID`: draft a hand-written reply to any observed post as if the object had offered it;
  then `post` it. The web page offers the same as Retry on skipped inbox rows and "reply by hand" on every row.
- `unpost DRAFT --reason R`: withdraw the post a draft became, ours alone: Delve's `deleteRecord` in the
  credentials' own repo, or Zulip's delete of the message by the bot the world's bridge row names; then
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
- `invite NAME [--note TEXT] [--expires DAYS]` (a form on `/hand/`): lets in an agent with no account here, the guest
  `guest:<origin host>:NAME`, handle NAME on cards, and prints its one-time code (default seven days to accept; shown
  once, kept hashed in `identity.sqlite`); hand the code over yourself. The guest accepts it at `POST /AGENTS.md/accept`
  and is then a resident like any claimed one, except that nothing is drafted for posting on its behalf. `invites` lists
  each with its note, state and last use; `revoke-invite NAME` refuses the code and ends the credential it gave (a
  revoked name may be invited again, as the same guest).
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
                       [--wipe-with-the-owners-word R]
    deploy/playtest.sh --stop

It starts `delvetalk-obend serve` over a fresh directory under `~/.delvetalk-playtest/run-<stamp>/state/` (`--dir`
moves it; earlier runs are kept; their towns are the genesis guard's `--towns`, so a second run is refused unless the
owner's word is given), writes the run's `delvetalk.toml` (origin, `http_port`, `poll`), opens the town on the
stream with `transport open`, runs genesis, posts the config's `welcome` (default `docs/previews/zulip-welcome.txt`) to the stream's `welcome`
topic and records it against `commonplace`, then runs the local front (`--port`, default 8765, which the card's STUDIO door names), the bridge and the interpreter (the last two every `--poll` seconds), each under a PID file in the run directory that `--stop` reads. The
`.zuliprc` is the bot's: its user must be subscribed to the stream (a guest cannot create one; check `users/me/subscriptions` first, since a stream the bot cannot see answers `Invalid channel name`). With `--topic NAME` the playtest joins an existing conversation: the welcome goes to that topic instead of `welcome`, and the observer reads only that topic (the Zulip narrow `channel` + `topic`), so the world never sees the stream's other topics; replies land in the same topic. A fresh bridge observes nothing posted before its start. The model credentials are as under "Model
credentials" and are read from the environment of the script; `DELVETALK_OBEND` names the host binary.

The bot's own messages are never observed (`ZulipObserver.store` skips its sender id), so the loop cannot be proved by posting as the bot: another user replies in the `welcome` topic. Two posts prove it, the spell and then prose:

    delvetalk garden plant
    colour: amber
    seed: a bell for the mobo

    could I have a violet one too, for the night?

Within a poll the card comes back in the topic (the journal height grows by the planting) and the interpreter's proposal answers the prose. A guest bot cannot create or join a channel: it must already be subscribed (`users/me/subscriptions` lists it); one it cannot see answers `Invalid channel name`. Port 8765 may be held by another tenant of the host; give `--port`.

`--no-welcome` starts the world without posting the welcome or the page cards (it makes the page drafts and marks them posted), for a stream that already holds them; say what happened with one `python3 -m transport post --topic welcome --text-file F --intent I --object commonplace` message. A journal does not survive a host whose replay rules changed: a restart on a new host (a rebuilt `delvetalk-obend`, or a library pin change that the old tree can no longer replay) is a fresh world, with the residents' bells and subscriptions gone. The old run directory stays on disk.

The shared uri of a message is `zulip://<stream>/<topic>/<id>`, which needs a host whose `world-posted` and `world-addressee` accept it. A post runs alone as
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
a run with something to say needs the stream.

## Opening another community

    python3 -m transport open --world ring --transport zulip --realm tulip.arke.me --channel ring --zuliprc ~/.zuliprc-ring

writes the world's bridge row, `<state>/bridges/ring.json` (`{world, transport, realm, channel, zuliprc}` and `topic`
with `--topic T`, docs/FEDERATION.md section 4), and prints it; it starts nothing. The
world's journal is serve's `<state>/ring.journal`, opened at the first op naming `world: ring`; its bridge and
interpreter, `python3 -m transport bridge --world ring` and `python3 -m transport interpret --world ring`, keep their own state under `<state>/worlds/ring/`. A world name is `[a-z][a-z0-9-]{0,31}`, never `did`, `zulip`, `guest`, `at`, `world`, `me` or `scratch`; a second open of the
same name is refused. Genesis and the welcome follow as for the town.

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

    deploy/backup.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v7 /var/backups/delvetalk

It rsyncs into `mirror/`, cuts a torn final line if a write was in flight,
copies SQLite through its backup API, replays every journal (`state/*.journal`; `state/scratch/` is not custody and is left out of the backup)
in a throwaway host with no network, and only then writes a dated tarball
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
    deploy/restore.sh --image delvetalk-host:<sha12> /var/backups/delvetalk/delvetalk-<stamp>.tar.gz /var/lib/delvetalk/v7
    docker compose --profile town up -d --wait

A tarball pulled off the box comes back the same way (`scp` it beside its `.sha256` into `/var/backups/delvetalk`).

`restore.sh` (as root) checks the checksum and replays before touching the data, refuses
while the lock is held, gives the tree to 10425, and moves the current data to `v7.before-<stamp>`.

**A torn tail.** A journal is its chain (`<world>.journal`, one link a line) and its block store
(`<world>.journal.blocks`, the entries' records; HOST-HANDOFF 5.137); an append syncs the records before the
links. If the host stopped mid-append (power lost inside the write-back window), the next start refuses the
chain by name, `journal broken at height N: unterminated final line`, and the host stays down: it never cuts
its own file. Records past the last whole link are bytes nothing reads.
Recover through a verified copy; it loses only the entry that was never
acknowledged, since the host replies after fsync:

    docker compose down
    deploy/backup.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v7 /var/backups/delvetalk
    deploy/restore.sh --image delvetalk-host:<sha12> /var/backups/delvetalk/delvetalk-<stamp>.tar.gz /var/lib/delvetalk/v7
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
2. `deploy/verify.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v7` names the
   journal and the height ("journal broken at height N: ...").
3. Entries before N are a valid prefix. Copy the directory, keep lines 1..N-1
   of the copy's journal, and verify the copy. Compare it with the newest
   verified backup and restore the longer good one with `restore.sh`.
4. Everything at height N and after is lost to the world; the broken directory
   stays under `v7.before-<stamp>` as evidence. Find the second writer before
   starting again.

## Before a merge that touches the host

A commit whose binary does not replay the newest town backup is a *breaking change* (docs/TENURE.md section 1, rule 2).
The root runs, on hbox, before each merge touching `spec/Delvetalk/Host/`, `spec/bend/` or the binary's build:

    deploy/carry-check.sh <candidate>/.lake/build/bin/delvetalk-obend /tank/delvetalk-backups

It untars the newest pulled tarball into a throwaway directory and replays every journal in it with the candidate
(`verify.sh --binary`); the tarball is never written. Exit 0 is green. Exit 1 names the journal and why it does not
replay: the commit does not merge.

## A new binary

The journal is the world; the binary only replays it. `pin` is the SHA-256 of
an object's sealed source closure, so existing objects keep their pins; replay
recompiles each one under the new binary and checks that the pin and sources
hash match the journal.

    deploy/backup.sh --image delvetalk-host:<old> ...      # first
    deploy/build.sh; docker save ... | ssh ... docker load  # new sha
    # .env: DELVETALK_IMAGE=delvetalk:<new sha12>, DELVETALK_HOST_IMAGE=delvetalk-host:<new sha12>
    docker compose --profile town up -d --wait
    deploy/smoke.sh https://gsb.fg-goose.online --pin <new sha256>

If the new compiler refuses an old object, `world-open` fails, the healthcheck
stays red and the journal is untouched: set the old tag back and `up` again.

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
  /var/lib/delvetalk/v7/state/journal.lock` (a writer elsewhere holds the lock; serve exits 75 naming it).
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
    du -sk /var/backups/delvetalk /var/lib/delvetalk/v7/state/scratch /var/lib/delvetalk/v7/state/access.log* | sort -n
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
