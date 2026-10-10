# Deploying DelveTalk

`https://gsb.fg-goose.online` is the HTTP front (`transport.http`) on the
workhorse, behind native Caddy on the anchor. Everything in `deploy/` is an
artifact the owner runs; nothing here deploys itself.

| File | What |
| --- | --- |
| `deploy/Dockerfile.host` | the host binary for linux/amd64; final image is the binary and glibc |
| `deploy/Dockerfile.transport` | python 3.13 slim + the binary + `transport/`, `world/`, the guide |
| `deploy/build.sh` | builds both, prints the binary's SHA-256, writes `deploy/out/host.sha256` |
| `deploy/compose.yml` | `delvetalk-hostd`, `delvetalk-http`, `delvetalk-bridge`; `delvetalk-interpret` (profile `town`); `delvetalk-ops` |
| `deploy/compose.hand.yml` | laid over compose.yml: the front with `--hand-token` and the Delve credentials directory |
| `deploy/seed.py` | `world-create` of one object from `world/` |
| `deploy/backup.sh`, `restore.sh`, `verify.sh` | journal custody |
| `deploy/smoke.sh` | the newcomer's journey against an origin |

The world's opener is ember's DID, `did:plc:6amo7col5h4ciq2gpm5eur7b`, set as
`DELVETALK_OPENER` on the hostd service (hostd's `--opener` takes it from there); only the opener may create objects with
a named owner at genesis, change the library, and make the newcomers' objects that `world-arrive` creates.

## One writer

Two host processes on one journal write two entries at the same height and break
the chain ("journal broken at height N: height out of sequence"). So exactly one
program, `delvetalk-hostd`, spawns the host and opens the journal. It holds
`/data/journal.lock` for its life (exit 75 if taken), restarts the host on death
by replaying the journal, and serves the front, the bridge, the interpreter,
`post --object` and `deploy.seed` over `/data/state/host.sock` (mode 0600). Private
heaps live in the same daemon, addressed by a `heap: <did>` field. At a journal's first open hostd seals
`world/lib` into it as the library (`--library`; the opener may change it, each heap's owner theirs),
so packages import `./Plan.obend` and the rest by name. hostd seals `world/lib` together with `world/objects/{Avatar,Env,Wake}.obend` (the packages `world-arrive` creates from, `ARRIVAL` in `transport/hostproc.py`; copied to `<state>/library` at each start), or arrival creates nothing. Those programs
are clients: stop, start or run them at any time without touching the world.
The lock holds where one kernel sees the file: a local Linux
filesystem (measured on ext4). Docker Desktop's file sharing on a Mac does not
enforce it across containers (measured), so test the stack there on a named volume.

## Costs

The boundary between the Python programs and the host process, measured on hbox with `deploy/bench-boundary.py` (median
per-op round trip, 1,000 `world-status` ops and 200 Counter bumps, two runs):

| Path | `world-status` | Counter bump |
| --- | --- | --- |
| (a) hostd's socket, a connection per op | 0.43 to 0.46 ms | 1.27 to 1.29 ms |
| (b) hostd's socket, one persistent connection | 0.21 ms | 1.03 to 1.08 ms |
| (c) the raw pipe to the host process | 0.13 to 0.15 ms | 0.87 to 0.94 ms |

`HostClient` now keeps one connection per thread, so production runs path (b) (measured through `HostClient` itself: 0.20 ms and 0.99 ms). A connection per op cost about 0.25 ms; hostd's own dispatch and the pipe add about 0.07 ms; the rest of a bump is the host.

## Prerequisites on the workhorse

- Docker with compose v2, as for `/opt/dregg-edge`; `rsync` and `python3` for backups.
- `/var/lib/delvetalk/v2`, owner `10425:10425`, mode 0700 (the image's uid,
  next in the edge's series). On ext4 or ZFS, local disk: see "Durability".
- `/etc/delvetalk/anthropic.key`: the key alone, owner 10425, mode 0400.
- The portal is `https://gsb.fg-goose.online` (`DELVETALK_ORIGIN` overrides it for every program; the front's `--origin` in
  `compose.yml` and `compose.hand.yml` is `${DELVETALK_ORIGIN:-https://gsb.fg-goose.online}`, not a fixed string, and compose passes `DELVETALK_ORIGIN` from `.env` into every service). The Caddy route for
  `gsb.fg-goose.online`, and the old `delvetalk.fg-goose.online` route, both proxy to `10.10.1.10:8765` until the town
  has moved; then the old one goes. The installed config is `/etc/caddy/Caddyfile` on the anchor (native Caddy, no
  checkout there; dregg-infra's `edge/anchor/Caddyfile` is its source and had drifted from it on 2026-10-10). Install as
  that file's header says: write `Caddyfile.new`, `caddy validate`, `mv`, `systemctl reload caddy`. Both names answer
  `respond @hand 404` for `path /hand /hand/*`, a belt only: the port Caddy proxies never serves the owner's console,
  which has its own listener on workhorse's loopback (below). The gsb route as installed:

      gsb.fg-goose.online {
      	import baseline_headers
      	encode zstd gzip
      	@hand path /hand /hand/*
      	respond @hand 404
      	request_body {
      		max_size 65536
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
- Log in with delve.town (`transport/oauth.py`) names the front by `--origin`: the client id is
  `<origin>/oauth/client-metadata.json` and the callback `<origin>/oauth/callback`. The account's PDS fetches the
  document itself, so it must answer 200 `application/json` over HTTPS at exactly that URL (no redirect); Caddy needs
  nothing new, since the gsb route already proxies every path but `/hand`. A login started on another name is first
  sent to the origin's, where its one-time cookie lives. Check it after a deploy:
  `curl -s https://gsb.fg-goose.online/oauth/client-metadata.json` shows `client_id` equal to that URL. pds.delve.town
  is its own authorization server (PAR, PKCE S256, DPoP ES256, `client_id_metadata_document_supported`; checked
  2026-10-10). The image installs `cryptography` for ES256 from `deploy/requirements-transport.txt`, pinned by hash.
- Firewall :8765 on the workhorse to Caddy's host (the anchor, 10.10.1.5) only: `--trust-proxy` believes the last
  `X-Forwarded-For` entry from whoever connects, so anything else on 10.10.1.0/24 that reaches the port can choose it.
  Measured 2026-10-10: the workhorse has no host firewall to add this to (no ufw; `nftables.service` disabled and
  `/etc/nftables.conf` an empty accept skeleton; Docker's `DOCKER-USER` chain empty), and the Hetzner Cloud firewall
  `dregg-edge` filters public interfaces only. The private network `dregg-edge-fsn1` holds the anchor and the workhorse
  and nothing else, so today the open path is containers on the workhorse itself (the edge's bridge, 172.18.0.0/16).
  A published port is filtered in `DOCKER-USER`, not `INPUT`; choosing and persisting that rule is dregg-infra's.

## Build and ship

On hbox (or any machine with Docker; the images are linux/amd64):

    deploy/build.sh            # last line: sha256:  <64 hex>  delvetalk-obend (linux/amd64)
    docker save delvetalk:<sha12> delvetalk-host:<sha12> | gzip -1 | ssh root@workhorse 'gunzip | docker load'
    scp deploy/compose.yml deploy/compose.hand.yml root@workhorse:/opt/delvetalk/
    scp deploy/backup.sh deploy/verify.sh deploy/restore.sh root@workhorse:/opt/delvetalk/deploy/

(From hbox, which has no key for the workhorse, pipe through the laptop: `ssh hbox 'docker save ... | gzip -1' | ssh
root@workhorse 'gunzip | docker load'`.) The backup scripts run on the host, not in a container, so they are shipped
beside compose.yml; `/opt/delvetalk/deploy/` is the copy the timer runs.

Two builds of one commit must print the same SHA-256; record it with the
commit. (Measured: foundation 1cc552a gives `6604098861d4…` on an arm64 Mac
under emulation and natively on hbox; foundation a3e1fb2, deployed 2026-10-10, gives
`1efaa90465860427c46672497aad25b2c7bd265b9e841c1a27a0ec324d5774e7` on both; foundation 18f1de9, deployed 2026-10-10 on hbox,
gives `523ea05d7dca284f5119ed6a23cf33841c821e44347fd5a137775841d7bdc12f`.) The image id after `docker load` on the
workhorse differs from hbox's (the two daemons' image stores); compare the binary instead:
`docker run --rm --entrypoint sha256sum delvetalk:<sha12> /usr/local/bin/delvetalk-obend`. The Lean compile runs inside dockerd's
build, outside a `swarm-build` cgroup around the client; the Dockerfile's own
two-slot wrapper is what bounds it. Everything the build reads is pinned (base images by digest, Debian
packages by snapshot, elan and the Lean tarball by SHA-256).

## First start

On the workhorse, in `/opt/delvetalk`, with this `.env` (mode 0600):

    DELVETALK_IMAGE=delvetalk:<sha12>
    DELVETALK_HOST_IMAGE=delvetalk-host:<sha12>     # the backup timer's replay image
    DELVETALK_OPENER=did:plc:6amo7col5h4ciq2gpm5eur7b
    COMPOSE_FILE=compose.yml:compose.hand.yml       # once the hand is opened (below)
    DELVETALK_HAND_TOKEN=<secret>



    docker compose up -d --wait delvetalk-hostd
    docker compose run --rm delvetalk-ops python3 -m deploy.genesis --host-socket /data/state/host.sock

`deploy.genesis` is docs/GENESIS.md as one command (the transport image carries `deploy/`, so it, `deploy/library-update.sh` and
`deploy.spend` run in `delvetalk-ops`). The opener arrives first (`world-arrive`), then creates `policy`,
`directory`, `garden`, `tide`, `workshop`, `anthology`, `cistern`, `commons`, `rooms` and `play`, in that order. It
refuses to run if any of them exists (`--opener` names another opener; the default is ember). The cistern is created
with its law (`law owner`, `law level: monotone(level)`; `world-inspect cistern` shows it), and the opener's
`wake/<did>` is given `arrived` and a schedule calling `tide.tick` every 60 clock minutes (its `triggers` in
`world-view`). Genesis prints one line per object; a page that was not published is named on stderr. The rehearsal seeds the
same way. `deploy.seed` creates one further object by hand.

The welcome card's menu has six doors: GARDEN, ROOMS, WORKSHOP, TIDE, ANTHOLOGY and STUDIO (a link to
`<origin>/AGENTS.md`, with no object). Genesis then has each door's object publish its page (`publishPage {page}`, the
page the door's word capitalized). After the bridge runs, its outbox holds one draft each: `wiki: Garden`, `wiki: Rooms`,
`wiki: Workshop`, `wiki: Tide` and `wiki: Anthology`. Garden writes its own page; the others get the host's default page
(the card, then how to reply). STUDIO has no page.
Post each with `transport.post ... --object <object>` as `python3 -m transport.bridge outbox` prints it; that records the
post for the object, so replies to it route there. A door whose page was not published is named on stderr. The outbox
prints `--text-file TEXT` for a page; `--draft` reads the text from the outbox file itself, so each page is

    docker compose run --rm -v /etc/delvetalk/delve/credentials.json:/run/delve.json:ro delvetalk-ops \
      python3 -m transport.post --state /data/state post --draft /data/state/outbox/<n>-pub-<id>.json --intent <id> \
      --host-socket /data/state/host.sock --object <object> --credentials /run/delve.json
    docker compose run --rm delvetalk-ops python3 -m transport.bridge mark-posted /data/state/outbox/<n>-pub-<id>.json

(dry run first, then with `--i-am-ember-and-authorize-posting`), or `transport.hand post <n>-pub-<id> --object <object>`.

The bridge observes nothing posted before its first start: a state that has observed nothing writes `<state>/since`
(now) on the first poll, and posts older than it are never observed (`bridge run --since ISO` replays deliberately). So
after genesis the journal holds genesis and the opener's arrival (the Avatar named by the DID, `env/<did>`, `wake/<did>`)
and nobody who posted earlier, and the outbox holds only the five page drafts. (The deploy of a3e1fb2 read the whole town on its first poll: 124
objects and five reply drafts to posts older than the world.) Posts made after `since` do arrive: the deploy of
18f1de9 had genesis at height 25 and, within its first two polls, two bots' replies (berduck, dougbot) made each an
Avatar, Env and Wake (heights 30 to 40) and were skipped with no draft.

    docker compose --profile town up -d --wait --remove-orphans
    docker compose ps

`delvetalk-interpret` is in the `town` profile, kept on purpose so a stack without the model key still comes up: every `up` that should run it names `--profile town` (as here, after a restore and after a new binary); without it the interpreter does not start and interpretations wait.

`--wait` fails red unless the healthcheck passes: `/AGENTS.md` answers and the
home page shows a journal height, `entry <n>` (a refused `world-open` shows `entry None`). From
the laptop:

    deploy/smoke.sh https://gsb.fg-goose.online --pin <sha256> --handle <you>.delve.town

Post the challenge text it prints from that account, then rerun with
`--verify at://<did>/town.delve.feed.post/<rkey>` to view as the verified DID
and revoke the throwaway credential.

## The first welcome card

Posting is a human command and is never in a container's `up`. The Delve
account's credentials file is mounted for that one command only:

    docker compose run --rm -v /etc/delvetalk/delve/credentials.json:/run/delve.json:ro delvetalk-ops \
      python3 -m transport.post --state /data/state post --text-file /data/welcome.txt \
      --intent welcome-1 --host-socket /data/state/host.sock --object directory --credentials /run/delve.json

`/data/welcome.txt` is `docs/previews/gsb-welcome-v4.txt` at the deployed commit, placed in the data directory by hand
(owner 10425, mode 0400); compare its SHA-256 with the repository's after any edit of the preview, since a re-genesis that
carries the old data directory's copy forward carries the old text. `--state /data/state` is
the hand's (its `posting/` ledger keeps each intent's record key). The host reserves every post before it is sent
(`world-post-reserve`, source `delve`, counted against `postQuota` per clock hour; Zulip's are journaled, never refused),
releases it only when the post certainly did not leave, and settles it with `world-posted {intent}`; the dry run shows
`world-status.posts`. Without
`--i-am-ember-and-authorize-posting` it prints the request and exits 2;
read it, then add the flag. `--object` names the object the card addresses: after a
confirmed post, post.py calls the host's `world-posted` for it, so every card posted
is recorded in the same step (replies to it then route to that object). Post a card
without `--object` only if no object should hear its replies. An intent posts once: `<state>/posting/` keeps, per
intent, the record key chosen before the first send (Zulip: the stream's newest id) and the post that came back, so a
rerun after a crash adopts the post instead of writing again. A draft whose `world-posted` failed keeps `sent` and is
recorded by the bridge's next run, never posted twice.

## Open the hand

The front keeps running, and the bridge and interpreter run against hostd (`bridge run --poll`, `interpret run --poll`, or
`--once` by hand as in "First start"). The owner works the town from the hand, a console the front serves at `/hand/`
only when it is started with a secret, and only on a listener of its own (`--hand-bind`, default 127.0.0.1, and
`--hand-port`, default 8766), which serves nothing else; the public port never serves `/hand/`:

    python3 -m transport.http --state /data/state --hand-token <secret> --credentials /run/delve.json

(in compose that is `deploy/compose.hand.yml`, named by `COMPOSE_FILE` in `.env` with `DELVETALK_HAND_TOKEN`; it mounts
`/etc/delvetalk/delve/` (owner 10425, mode 0700) read-only, where the owner puts `credentials.json`, read only at a
Post, and publishes the hand's port on workhorse's loopback only, `127.0.0.1:8766`, so reach it by a forward):

    ssh -L 8766:127.0.0.1:8766 root@workhorse     # then open http://127.0.0.1:8766/hand/?token=<secret>

The token is asked once (query, then a cookie scoped to `/hand/`); without it every `/hand/` path is a 404. The page
has a status strip (journal height, posts this hour of the quota, model spend this month, pending interpretations and
retries, hostd pid), a search by receipt slug (`world-resolve`), the OUTBOX and the INBOX. The outbox groups drafts by
the post they answer, the post beside an editable textarea of the draft, with three buttons: **Post** runs
`post.post_draft`, the code `post.py --draft` runs (the edited text, the owner's credentials file, `world-posted` for the
draft's object, the draft marked posted); **Skip** marks it `skipped` with a reason and it leaves the outbox; **Hold**
leaves it. Nothing is posted without a click, and every action is a line in `<state>/hand-log.jsonl`
(what, who, when, draft id). A turn that suspends on an interpretation has no draft until the interpretation settles; a
model failure leaves it pending and retried with backoff up to 8 times. Draft principals are observed, unverified DIDs.
The same operations have a command-line face for the owner's assistant over ssh: `python3 -m transport.hand <verb>
--state /data/state [--credentials FILE] [--json]` (`DELVETALK_STATE` and `DELVETALK_CREDENTIALS` stand in for the
flags; `--json` prints one JSON document, otherwise readable text; each action is logged with `who: "cli"`):

- `inbox [--since HEIGHT] [--kind summon|reply|post|wiki-page|wiki-edit|wiki-merge]`: observations newest first, with
  what became of each (whether a post is a spell is the host's reading, shown in its fate).
- `outbox [--all]`: drafts grouped by the post they answer (`--all` includes posted and skipped).
- `show DRAFT`: the post, the draft text and its receipt line.
- `edit DRAFT --text-file F | --stdin`: replace the draft text, keeping the original.
- `post DRAFT [--object ID]`: post it, record it with the host for its object (or `--object`), mark it posted.
- `skip DRAFT --reason R` and `hold DRAFT`: take it out of the outbox with a reason, or leave it.
- `status`: height, posts this hour, model spend, pending interpretations and retries, hostd pid.
- `search SLUG`: resolve a receipt slug with `world-resolve`.
- `retry URI`: forget that the bridge skipped an observation, so the next run routes it again.
- `reply URI --text-file F --object ID`: draft a hand-written reply to any observed post as if the object had offered it;
  then `post` it. The web page offers the same as Retry on skipped inbox rows and "reply by hand" on every row.
- `log [--tail N]`: the last actions in `hand-log.jsonl`.

The command-line way remains: `python3 -m transport.bridge outbox --state STATE` prints each draft with its own
`post.py` command.

## Playtesting in Zulip

Before DelveTalk goes to delve.town, residents can play it in the owner's own Zulip. `transport/zulip.py` is a second
transport: an observer of one stream and a poster. Every message of the stream becomes the observation a Delve post
would (principal `zulip:<sender id>`, the full name as handle, `replyTo` the previous message of its topic, kind
by `observe.classify`; mentioning the bot, whose name `users/me` gives, summons the directory), and the bridge routes
it as ever: a reply is its parent's address, and a post with no recorded ancestor goes to the card of its spell as the
host's parser reads it (`spell-parse`; Python only skips text without the word `delvetalk`). Because this is
the owner's Zulip, `bridge run --source zulip` posts drafts back itself (`@**Name**` first, in the draft's topic),
with no hourly cap (the host's `postQuota` is delve.town etiquette and does not apply to the owner's own Zulip), and records each post with
`world-posted`, so a reply to it routes. The delve.town rule against automatic posting does not apply here and nothing
in this path reads Delve credentials.

    deploy/playtest.sh --zuliprc PATH [--stream delvetalk] [--topic NAME] [--poll 20]
    deploy/playtest.sh --stop

It starts hostd on a fresh journal under `~/.delvetalk-playtest/run-<stamp>/` (`--dir` or `DELVETALK_PLAYTEST_DIR`
moves it; earlier runs are kept), runs genesis, posts `docs/previews/zulip-welcome-v2.txt` (its `<bot name>` filled in) to the stream's `welcome`
topic and records it against `directory`, then runs the local front (`--port`, default 8765, which the card's STUDIO door names), the bridge and the interpreter (the last two every `--poll` seconds). The
`.zuliprc` is the bot's: its user must be subscribed to the stream (a guest cannot create one; check `users/me/subscriptions` first, since a stream the bot cannot see answers `Invalid channel name`). With `--topic NAME` the playtest joins an existing conversation: the welcome goes to that topic instead of `welcome`, and the observer reads only that topic (the Zulip narrow `channel` + `topic`), so the world never sees the stream's other topics; replies land in the same topic. A fresh bridge observes nothing posted before its start. The model credentials are as under "Model
credentials" and are read from the environment of the script; `DELVETALK_OBEND` names the host binary.

The bot's own messages are never observed (`ZulipObserver.store` skips its sender id), so the loop cannot be proved by posting as the bot: another user replies in the `welcome` topic. Two posts prove it, the spell and then prose:

    delvetalk garden plant
    colour: amber
    seed: a bell for the mobo

    could I have a violet one too, for the night?

Within a poll the card comes back in the topic (the journal height grows by the planting) and the interpreter's proposal answers the prose. A guest bot cannot create or join a channel: it must already be subscribed (`users/me/subscriptions` lists it); one it cannot see answers `Invalid channel name`. Port 8765 may be held by another tenant of the host; give `--port`.

The shared uri of a message is `zulip://<stream>/<topic>/<id>`, which needs a host whose `world-posted` and `world-addressee` accept it. The pieces run alone as
`python3 -m transport.zulip observe|post`; the mocked Zulip is `tests/test_zulip.py`.

## Rotating the Anthropic key

Write the new key to a temporary file beside the old one (owner 10425, mode
0400), `mv` it over `/etc/delvetalk/anthropic.key`, and revoke the old key in
the Anthropic console. `model.py` reads the file on every request, so no
restart is needed. The key never enters the repository, the image, `.env`, or
an argv.

## Durability and backups

The host appends each step's entries and fsyncs once before it replies
(`spec/native/sync.c`: `fsync`; `F_FULLFSYNC` only when `world-open` asks for `sync: full`, which hostd does not). That holds
only if fsync reaches the disk: use a bind mount of a local ext4 or ZFS
directory, as here. Not NFS, not a network volume driver. Docker Desktop's
file sharing on a Mac is for testing, not custody.

    deploy/backup.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v2 /var/backups/delvetalk

It rsyncs into `mirror/`, cuts a torn final line if a write was in flight,
copies SQLite through its backup API, replays every journal (world and heaps)
in a throwaway host with no network, and only then writes a dated tarball
and its `.sha256`. Exit 1 means a journal is broken: the tarball is not made.
Run it from a timer and copy the tarballs off the box. The timer installed on the workhorse:

    # /etc/systemd/system/delvetalk-v2-backup.service
    [Service]
    Type=oneshot
    EnvironmentFile=/opt/delvetalk/.env
    WorkingDirectory=/opt/delvetalk
    ExecStart=/opt/delvetalk/deploy/backup.sh --image ${DELVETALK_HOST_IMAGE} /var/lib/delvetalk/v2 /var/backups/delvetalk
    Nice=10
    IOSchedulingClass=idle
    # /etc/systemd/system/delvetalk-v2-backup.timer
    [Timer]
    OnCalendar=*-*-* 00/6:17:00
    RandomizedDelaySec=5m
    Persistent=true
    [Install]
    WantedBy=timers.target

`systemctl enable --now delvetalk-v2-backup.timer`. The off-box copy is not set up: the workhorse has no trusted key or
host key for hbox, and hbox has no `/tank/delvetalk-backups/` (and `/tank` was 92% full on 2026-10-10). Restore:

    docker compose down
    deploy/restore.sh --image delvetalk-host:<sha12> /var/backups/delvetalk/delvetalk-<stamp>.tar.gz /var/lib/delvetalk/v2
    docker compose --profile town up -d --wait

`restore.sh` checks the checksum and replays before touching the data, refuses
while the lock is held, and moves the current data to `v2.before-<stamp>`.

## Changing the library after launch

    docker compose run --rm delvetalk-ops deploy/library-update.sh

It rebuilds `<state>/library` from the image's `world/` (the library plus the arrival packages) and asks the host for
`world-library` as the opener; the world law judges it, the new pin is journaled and printed. Ship the new `world/`
first (a new image), since replay re-seals from the same bytes. Existing objects keep the pin they were compiled
under; objects created or reprogrammed afterwards compile against the new library. The front's REPL keeps the pin it
loaded at hostd's start until `docker compose restart delvetalk-hostd`.

## When the chain breaks

The healthcheck goes red and every host reply is "host unavailable".

1. `docker compose down`. Never edit the journal in place.
2. `deploy/verify.sh --image delvetalk-host:<sha12> /var/lib/delvetalk/v2` names the
   journal and the height ("journal broken at height N: ...").
3. Entries before N are a valid prefix. Copy the directory, keep lines 1..N-1
   of the copy's journal, and verify the copy. Compare it with the newest
   verified backup and restore the longer good one with `restore.sh`.
4. Everything at height N and after is lost to the world; the broken directory
   stays under `v2.before-<stamp>` as evidence. Find the second writer before
   starting again.

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

## What is not automated, and why

- **Posting.** Every post is a human decision under the owner's authority;
  repository authorization does not authorize posting. No service holds the
  Delve credentials.
- **Key custody.** The Anthropic key and Delve credentials are placed by the
  owner outside the repository; `.gitignore` refuses `*.key`, `.env`,
  `credentials.json`.
- **DNS and TLS.** The anchor's Caddy and the DNS record are dregg-infra's.
- **Genesis.** Which objects exist, under which DID and policy, is the owner's.
- **Backup schedule and off-box copy.** The owner picks the timer and the target.

## Model credentials

`transport/model.py` has two auth modes, chosen by `DELVETALK_MODEL_AUTH`.

- `key` (default, primary): a plain Console API key from `DELVETALK_ANTHROPIC_KEY` or the file at `DELVETALK_ANTHROPIC_KEY_FILE`, sent as `x-api-key` with no special headers.
  A Max plan includes ordinary API credits ($100 or $200 a month, expiring each billing cycle). To claim them:
  1. In claude.ai, open Settings, Billing, API credits, and link the organization.
  2. Create an API key in that organization.
  3. Put the key in the key file (mode 600).
- `oauth` (fallback): runs on subscription extra usage. Reads tokeman's `~/.config/tokeman/tokens.toml` (override with `DELVETALK_TOKENS_TOML`) and refuses it if group or other can read it.
  The account is `DELVETALK_MODEL_ACCOUNT`, or else the one `tokeman --json` shows with the most seven-day headroom for the model's bucket (Haiku uses the general window).
  If every account is spent it prefers one with extra usage enabled. Sent as `Authorization: Bearer` with `anthropic-beta: oauth-2025-04-20`.
  On 429 or 529 it rotates once to the next account. Results carry the account name, `rotated` and `overageInUse`, never a token.

Both modes: only `model`, `max_tokens`, `system` and `messages` are sent (never `temperature`, `top_p` or `top_k`).
`DELVETALK_MODEL_THINKING=off` adds `thinking: {"type": "disabled"}` for cheap deterministic JSON calls.
With a state directory, each replied call appends `{at, model, inputTokens, outputTokens, account}` to `<state>/model-spend.jsonl`; total it against the monthly grant, since no balance endpoint exists.
`DELVETALK_KEY_NAME` labels the key in that log. Total it with `python3 -m deploy.spend --state /data/state [--month YYYY-MM] [--grant 200]`: calls and tokens by month, dollars at Haiku 5.5's published rates ($0.10 per million input tokens, $0.50 output), and the grant remaining. Any `anthropic-ratelimit-*` response headers appear in the result as `rateLimits`.

## The front's access log

`transport.http` writes one line per request to `<state>/access.log`: `<time> <method> <path> <status> <bytes> <did or ->`,
the path without its query, never a credential or a body. Past 16 MB the file becomes `access.log.1` (one generation kept).
Zero 500s is `awk '$4 == 500' access.log access.log.1`.
