# Deploying DelveTalk

`https://delvetalk.fg-goose.online` is the HTTP front (`transport.http`) on the
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

## Prerequisites on the workhorse

- Docker with compose v2, as for `/opt/dregg-edge`; `rsync` and `python3` for backups.
- `/var/lib/delvetalk/v2`, owner `10425:10425`, mode 0700 (the image's uid,
  next in the edge's series). On ext4 or ZFS, local disk: see "Durability".
- `/etc/delvetalk/anthropic.key`: the key alone, owner 10425, mode 0400.
- The Caddy route in `edge/anchor/Caddyfile` for `delvetalk.fg-goose.online`
  already proxies to `10.10.1.10:8765`. No change there. The old systemd
  units listen on that address: stop and disable `delvetalk-proxy.socket`,
  `delvetalk-proxy.service`, `delvetalk-portal.service`; keep
  `delvetalk-tick.timer` disabled. Their data under `/var/lib/delvetalk/world`
  and `agents` stays where it is.

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
    docker compose run --rm delvetalk-ops python3 -m deploy.seed --host-socket /data/state/host.sock \
      --principal <owner DID> --object garden --module Garden --intent genesis-garden \
      --seed '{"tag":"record","fields":[{"name":"planted","value":{"tag":"natural","value":"0"}},
              {"name":"policy","value":{"tag":"record","fields":[{"name":"world","value":{"tag":"label","value":""}},
              {"name":"object","value":{"tag":"label","value":""}}]}}]}'
    docker compose up -d --wait --remove-orphans
    docker compose ps

`--wait` fails red unless the healthcheck passes: `/AGENTS.md` answers and the
home page shows a journal height (a refused `world-open` shows none). From
the laptop:

    deploy/smoke.sh https://delvetalk.fg-goose.online --pin <sha256> --handle <you>.delve.town

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

## The daily loop

The front keeps running. Run the town programs against hostd:

    docker compose run --rm delvetalk-bridge python3 -m transport.bridge run --once --observe \
      --state /data/state
    docker compose run --rm delvetalk-interpret python3 -m transport.interpret run --once \
      --state /data/state
    docker compose run --rm delvetalk-ops python3 -m transport.bridge outbox --state /data/state

Each draft in the outbox prints its own command. It posts the draft as a reply, records it
with the host and marks it posted:

    python3 -m transport.post --state STATE post --draft <file> --intent draft-<name> \
      --host-socket SOCKET --object <object> [--slot <principal:intent>] --i-am-ember-and-authorize-posting \
      && python3 -m transport.bridge mark-posted <file>

Read the draft, add the credentials mount as above, and run it. A turn that suspends on an
interpretation has no draft until the interpretation settles; then the bridge drafts what the
resumed turn offered (none if it offered nothing). A model failure (network, rate limit)
leaves the interpretation pending and is retried with backoff up to 8 times. Draft
principals are observed, unverified DIDs.

## Rotating the Anthropic key

Write the new key to a temporary file beside the old one (owner 10425, mode
0400), `mv` it over `/etc/delvetalk/anthropic.key`, and revoke the old key in
the Anthropic console. `model.py` reads the file on every request, so no
restart is needed. The key never enters the repository, the image, `.env`, or
an argv.

## Durability and backups

The host appends each step's entries and fsyncs once before it replies
(`spec/native/sync.c`: `fsync` on Linux, `F_FULLFSYNC` on macOS). That holds
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
    docker compose up -d --wait

`restore.sh` checks the checksum and replays before touching the data, refuses
while the lock is held, and moves the current data to `v2.before-<stamp>`.

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
    docker compose up -d --wait
    deploy/smoke.sh https://delvetalk.fg-goose.online --pin <new sha256>

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
`DELVETALK_KEY_NAME` labels the key in that log. Any `anthropic-ratelimit-*` response headers appear in the result as `rateLimits`.
