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
so packages import `./Plan.obend` and the rest by name. hostd seals `world/lib` together with `world/objects/{Avatar,Env,Wake,Place}.obend` (the packages `world-arrive` creates from; copied to `<state>/library` at each start), or arrival creates nothing. Those programs
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
  `compose.yml` names it too). The Caddy route in `edge/anchor/Caddyfile` for `gsb.fg-goose.online`, and the old
  `delvetalk.fg-goose.online` route, both proxy to `10.10.1.10:8765` until the town has moved; then the old one goes.
  No other change there. The old systemd
  units listen on that address: stop and disable `delvetalk-proxy.socket`,
  `delvetalk-proxy.service`, `delvetalk-portal.service`; keep
  `delvetalk-tick.timer` disabled. Their data under `/var/lib/delvetalk/world`
  and `agents` stays where it is.
- Firewall :8765 on the workhorse to Caddy's host (the anchor) only: `--trust-proxy` believes the last
  `X-Forwarded-For` entry from whoever connects, so anything else on 10.10.1.0/24 that reaches the port can choose it.

## Build and ship

On hbox (or any machine with Docker; the images are linux/amd64):

    deploy/build.sh            # last line: sha256:  <64 hex>  delvetalk-obend (linux/amd64)
    docker save delvetalk:<sha12> delvetalk-host:<sha12> | gzip -1 | ssh root@workhorse 'gunzip | docker load'
    scp deploy/compose.yml root@workhorse:/opt/delvetalk/compose.yml

Two builds of one commit must print the same SHA-256; record it with the
commit. (Measured: foundation 1cc552a gives `6604098861d4…` on an arm64 Mac
under emulation and natively on hbox.) The Lean compile runs inside dockerd's
build, outside a `swarm-build` cgroup around the client; the Dockerfile's own
two-slot wrapper is what bounds it. Everything the build reads is pinned (base images by digest, Debian
packages by snapshot, elan and the Lean tarball by SHA-256).

## First start

On the workhorse, in `/opt/delvetalk`, with `DELVETALK_IMAGE=delvetalk:<sha12>` in `.env`:

    docker compose up -d --wait delvetalk-hostd
    docker compose run --rm delvetalk-ops python3 -m deploy.genesis --host-socket /data/state/host.sock

`deploy.genesis` is docs/GENESIS.md as one command. The opener arrives first (`world-arrive`), then creates `policy`,
`directory`, `garden`, `tide`, `workshop`, `anthology`, `cistern`, `commons`, `rooms` and `play`, in that order. It
refuses to run if any of them exists (`--opener` names another opener; the default is ember). The rehearsal seeds the
same way. `deploy.seed` creates one further object by hand.

Genesis then has each door's object publish its page (`publishPage`). After the bridge runs, its outbox holds one
`wiki: <Door>` draft each for GARDEN, ROOMS, WORKSHOP and ANTHOLOGY. Tide has no `publishPage`, so TIDE's is
named on stderr as not published; STUDIO is a link, with no page.
Post each with `transport.post ... --object <object>` as `python3 -m transport.bridge outbox` prints it; that records the
post for the object, so replies to it route there. A door whose page was not published is named on stderr.

    docker compose --profile town up -d --wait --remove-orphans
    docker compose ps

`delvetalk-interpret` is in the `town` profile, kept on purpose so a stack without the model key still comes up: every `up` that should run it names `--profile town` (as here, after a restore and after a new binary); without it the interpreter does not start and interpretations wait.

`--wait` fails red unless the healthcheck passes: `/AGENTS.md` answers and the
home page shows a journal height (a refused `world-open` shows none). From
the laptop:

    deploy/smoke.sh https://gsb.fg-goose.online --pin <sha256> --handle <you>.delve.town

Post the challenge text it prints from that account, then rerun with
`--verify at://<did>/town.delve.feed.post/<rkey>` to view as the verified DID
and revoke the throwaway credential.

## The first welcome card

Posting is a human command and is never in a container's `up`. The Delve
account's credentials file is mounted for that one command only:

    docker compose run --rm -v /etc/delvetalk/delve-credentials.json:/run/delve.json:ro delvetalk-ops \
      python3 -m transport.post --state /data/state/post post --text-file /data/welcome.txt \
      --intent welcome-1 --host-socket /data/state/host.sock --object directory --credentials /run/delve.json

Without `--i-am-ember-and-authorize-posting` it prints the request and exits 2;
read it, then add the flag. `--object` names the object the card addresses: after a
confirmed post, post.py calls the host's `world-posted` for it, so every card posted
is recorded in the same step (replies to it then route to that object). Post a card
without `--object` only if no object should hear its replies.

## Open the hand

The front keeps running, and the bridge and interpreter run against hostd (`bridge run --poll`, `interpret run --poll`, or
`--once` by hand as in "First start"). The owner works the town from the hand, a console the front serves at `/hand/`
only when it is started with a secret:

    python3 -m transport.http --state /data/state --hand-token <secret> --credentials /run/delve.json

(in compose, add those arguments and the credentials mount to `delvetalk-http`; the front's port is not public, so
reach it by a forward):

    ssh -L 8765:10.10.1.10:8765 root@workhorse     # then open http://127.0.0.1:8765/hand/?token=<secret>

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

- `inbox [--since HEIGHT] [--kind spell|summon|reply|post]`: observations newest first, with what became of each.
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
it as ever: a reply is its parent's address, a card word applies to a post with no recorded ancestor. Because this is
the owner's Zulip, `bridge run --source zulip` posts drafts back itself (`@**Name**` first, in the draft's topic),
inside the host's `postQuota` per hour (a draft over it waits for the next round), and records each post with
`world-posted`, so a reply to it routes. The delve.town rule against automatic posting does not apply here and nothing
in this path reads Delve credentials.

    deploy/playtest.sh --zuliprc PATH [--stream delvetalk] [--poll 20]
    deploy/playtest.sh --stop

It starts hostd on a fresh journal under `~/.delvetalk-playtest/run-<stamp>/` (`--dir` or `DELVETALK_PLAYTEST_DIR`
moves it; earlier runs are kept), runs genesis, posts `docs/previews/zulip-welcome-v2.txt` (its `<bot name>` filled in) to the stream's `welcome`
topic and records it against `directory`, then runs the local front (`--port`, default 8765, which the card's STUDIO door names), the bridge and the interpreter (the last two every `--poll` seconds). The
`.zuliprc` is the bot's: its user must be subscribed to the stream. The model credentials are as under "Model
credentials" and are read from the environment of the script; `DELVETALK_OBEND` names the host binary.

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
Run it from a timer and copy the tarballs off the box. Restore:

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
    # .env: DELVETALK_IMAGE=delvetalk:<new sha12>
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
