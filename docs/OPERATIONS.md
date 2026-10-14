# Operations

The transport's shape, the production tooling around it, and the bounds that would end a town. docs/DEPLOY.md is the
procedure: build, ship, carry, backups, the playbooks.

## a. The transport's shape

The host decides; the Python is adapters. Every decision the transport review found Python making (routing reach,
reservations, retries, the spell classifier, the post quota per source) moved into the host, and that is the rule for
new code: a Python program that decides admission is a bug.

| Role | Modules | What it still decides |
| --- | --- | --- |
| adapters: Delve, Zulip, the town's feed, the model, the classifier | `delve.py`, `observe.py`, `zulip.py`, `feed.py`, `post.py`, `model.py`, `automod.py` | nothing: reservations, retries and spell parsing are the host's (`world-post-reserve`, `attempted`, `spell-parse`) |
| the front: routes, pages, the claim, the login, the repository façade, the firehose | `http.py`, `pages.py`, `atlas.py`, `views.py`, `identity.py`, `oauth.py`, `repo.py`, `hosted.py`, `firehose.py` | rate limits per credential and address, body limits, the 30 s deadline, which page renders; the claim's challenge (`identity.sqlite`) |
| the bridge: routing and drafting | `bridge.py`, `interpret.py`, `requests.py` | where a post is offered (the host checks `reach`), when to draft, the deliver rounds |
| the hand | `hand.py`, `overview.py`, `byhand.py`, `root.py` | nothing: every action is a click or a verb |
| one state, one config, one entry point | `state.py`, `config.py`, `__main__.py`, `host.py`, `carry.py`, `watch.py` | where each file lives, what each setting is |

`serve` (the host) holds the journal lock, every world, the scratch worlds and both sockets; there is no Python process
manager. The front stays Python: a Lean front would need an HTTP/1.1 server and an AT Protocol OAuth client with DPoP
ES256 (unverified C in the TCB, or a Lean P-256) to save one socket hop (0.077 ms, DEPLOY "Costs"). It earns its place
only if the claim must become a journaled fact or the hop shows in the access log; neither is true.

**Decision:** Python as adapters under one `State`, one `Config`, one entry point; no Lean front.

## b. Production tooling

### One state, one config, one entry point

**`transport/config.py`: one `Config`.** A frozen dataclass; every setting the programs share is a field with a
default and a one-line description, and nothing else holds a default. `Config.load(state)` reads
`<state>/delvetalk.toml` (`tomllib`; optional; an unknown key or a value of the wrong type is refused by name), then
the environment: `DELVETALK_<FIELD>` overrides `<field>`. Precedence: default, file, environment. Compose's environment
carries only what is a fact of the container (mount paths, secret files, the bind address); the operator's choices live
in the file. A world's bridge (Delve, a Zulip channel, or the town's own feed) is not a field: it is the world's row,
which `open` writes. `lexicon_authority` is the schema publication DID, default `did:plc:6amo7col5h4ciq2gpm5eur7b`,
named by the live `_lexicon.gsb.fg-goose.online` TXT; an authorized `lexicons` step requires `credentials` to
authenticate as that DID before any record write (ATPROTO §5).

**`transport/state.py`: one `State(root, world, config)`.** Every path is an attribute named once; no other module
joins a path under `<state>/`. One directory per world for everything that is the world's, the town's included:

    <state>/delvetalk.toml            the config
    <state>/<world>.journal(.blocks)  serve's, with journal.lock, serve.pid, binary-pin, library/, scratch/
    <state>/host.sock, root/root.sock serve's sockets (host_socket, root_socket move them)
    <state>/identity.sqlite           claims and invitations: a principal is global
    <state>/access.log(.1)            the front's (DEPLOY "The front's access log")
    <state>/hand-log.jsonl            the hand's actions, each with its world
    <state>/model-spend.jsonl         one line per replied model call, with its world
    <state>/automod-spend.jsonl       one line per classifier call
    <state>/arrive-flagged.txt        addresses the hand flagged (an open door)
    <state>/lexicons/<URL-encoded authority DID>.json  account-wide published schema digests, never deletes
    <state>/bridges/<world>.json      a world's bridge row
    <state>/hosted/<URL-encoded origin>/*.json  optional public request snapshots, signing key ids and epochs;
                                      keys derived from the town key and DID, directory fd flock
    <state>/worlds/<world>/           observe.sqlite, since; outbox/, awaiting/;
                                      principals.txt, mentioned.txt, skipped.txt,
                                      publications.after; posting/; interpretations/;
                                      bridge.pid, interpret.pid; watch.jsonl, alerted.json;
                                      repo.json (chain epochs), events (durable firehose log);
                                      requests.json (participant revisions and refused CIDs), answers/;
                                      automod.json, automod-status.json, automod-backfill.json(l)
    <repo_keys>/<world>.key           the repository's signing key

`State` also hands out the host clients (`host()`, `root()`), `write` (atomic, the one `write_atomic`), the outbox
reads, the daemon loop with its pid heartbeat, and the bridge row.

- **`events`** is fsynced before emission; its independent seq survives carry and front restart. Backups keep it with
  `repo.json`. The newest 10,000 events are replayable, compacted by atomic rewrite at 20,000; loss of `events` loses
  cursor continuity. `firehose_port = 0` disables the listener (DEPLOY "Firehose").
- **Requests and hosted accounts** are off by default (`requests = false`, `hosted_accounts = false`); DEPLOY "Public
  request participants" and "Hosted account origins" are what each does when on, and its custody.
- **`observe.sqlite` is a working set, not an archive** (observe.py's docstring). A skipped post (the host's
  `world-reach` answered `unreached`) is dropped 15 minutes after it was written, to an 8-byte URI hash so the feed
  never offers it again; a skipped reply also leaves a (uri, author, replyTo) stub for 3 days, the ancestor `reach` is
  shown. A post that reached a card or was drafted, turned or answered is kept whole 7 days after it was written, then
  dropped to its hash; a post awaiting an interpretation or a draft is kept until answered. Every author seen stays
  (`authors`: an @handle resolves long after their posts are gone). Ages are measured on the newest post observed,
  never later than the clock. A day of 6,000 observed posts adds about 0.5 MB (the week's reached posts accumulate to
  about 4 MB and then stop); carry copies the file through SQLite's backup, so a carry is that size. Dropped posts are
  gone from the hand's inbox, `retry` and `reply`, and from `measure` and `watch` counts. An old store is migrated on
  its first open.
- **Mentions.** Whoever a post mentions hears it, reached or not: each mention of an arrived resident is queued in the
  store as its note (`mentions`: the author, their handle, the post's URI, its first 280 characters, the avatar's own
  bound), and once a resident's oldest note is an hour old (`bridge.MENTION_MINUTES`) the town tells their avatar every
  note queued since in one turn (`<did>.mentions {notes}` as the opener, 16 notes a turn), so the journal holds at most
  a turn per resident an hour. A resident told more than 64 notes keeps the newest 64 (the inbox's bound). Mentions
  the bridge skipped are heard again by `python3 -m transport bridge --hear-again <ISO>` (with the bridge stopped): it
  pages the town feed back to that time and queues, due at once, the mentions of every post there that the bridge
  skipped and told no one of; it asks reach nothing and turns nothing, and the next run tells them.

**`python3 -m transport <command> --state DIR --world W`.** `--state` defaults to `DELVETALK_STATE`, `--world` to
`town`. Commands take only what the config does not hold:

| command | its own arguments |
| --- | --- |
| `serve` | none: execs `delvetalk-obend serve` with the config's sockets, opener, library and sync |
| `bridge` | `--once`, `--since ISO`, `--now SECONDS`, `--hear-again ISO`; the source comes from the world's row |
| `interpret` | `--once` |
| `automod` | `--once`, `--backfill [--act] [--entries N]` (DEPLOY "Automatic moderation") |
| `post` | what to post (`--draft` or `--text-file`; an agentwiki post is its header line), `--intent`, `--object`, `--slot`, `--reply-to`, `--mention`, `--topic`, the authorizing flag; the world's row says where it goes |
| `mirror` | `--once`, `--limit N`, the authorizing flag: the world's readable state as records in the posting account's repository |
| `lexicons` | `--authorized`; the default offline inventory needs no state; publication requires state and the authority credential (ATPROTO §5) |
| `hand` | its verbs (DEPLOY "Open the hand") |
| `http` | none |
| `open` | the row: `--transport zulip\|delve\|feed`, `--realm`, `--channel`, `--topic`, `--zuliprc` |
| `watch` | `--unhealthy SERVICE…`, `--dry-run`; probes itself |
| `repokey` | `--curve` |
| `carry` | `--from OLD --to NEW --reason R [--leave [WORLD=]OBJ] [--obend BIN]` (DEPLOY "A new binary") |
| `tables` | `--port`, `--obend`, `--dealer`: the dealer's local Automatafl tables |
| `status` | `--health host\|http\|hand\|bridge\|interpret\|automod` (exit status), `--playtest` |

`deploy/` keeps the shell, compose, genesis and seed, `serve.py` (serve as a child for tests and scripts, its argv
from `State`), the instance template and the measurement tools. `transport/` imports from it only genesis (the carry's refresh) and
`serve.py` (the local tables).

**Decision:** one `Config` (file, then `DELVETALK_*`), one `State` that owns every path, one `python3 -m transport`;
the town is a world like any other.

### Monitoring

One probe, `python3 -m transport watch --world W` per world, run by a systemd timer every 5 minutes: it probes
(`status`), appends the probe to the world's `watch.jsonl` and reads the thresholds from it. No agent, no exporter.

| Watch | Source | Trouble |
| --- | --- | --- |
| 5xx answered by the front | `access.log`, `awk '$4 >= 500'` | any in 5 minutes |
| refusals by class | `world-status.hour.refused` | `capacity` ≥ 1; `quota` > 5/h; `staleRoot` > 10% of turns |
| model readings and spend per hour | `model-spend.jsonl` summed by hour, `use=paint` lines counted apart (`paints`) | > 120 readings/h (not paints), paints over twice `paint_budget` in 24 h, or the day past `modelQuota` |
| reservations held | `world-status.posts.sources[delve]`: `used` of `quota`, `next` | 16 of 16 for two hours (the hand is not clicking, or a loop is drafting) |
| scratch worlds | `world-status.scratches {open, expiring}` | open > 40, or any over 16 MiB |
| journal height and size | `world-status.height`; the chain's bytes | height unchanged for an hour while posts were observed; bytes > 200 MiB |
| suspension median | the journal's last 4,000 suspended entries | > 8 KB |
| the clock advancing | `world-status.clock` against `now // 60` | behind by > 3 minutes: the bridge is dead (its `tick` is the only clock) |
| pending interpretations | `world-interpretations`: count and the oldest's `attempts` | > 20, or any at attempt 8 |
| the backup verify | `last-verify` and the newest tarball's age in the backups directory | `broken`, or age > 7 h |
| the processes | compose healthchecks (`watch.sh` passes the unhealthy) | any unhealthy |
| disk | the state and backup filesystems | < 20% free |

**Decision:** one probe, one JSONL file, one timer per instance.

### Alerting

The watch posts to the owner's Zulip (the config's `watch_zuliprc`, stream `delvetalk-ops`, topic `watch` or the
instance's own), which reaches the phone through Zulip's own push; nothing else is installed. One message per condition
per 6 hours (the world's `alerted.json` of condition to last-sent), naming the number and the playbook (DEPLOY
"Playbooks") by letter. Two conditions repeat hourly: a service unhealthy, and the backup verify failed or stale. The
rest are the daily loop's.

**Decision:** Zulip is the pager; two conditions repeat, the rest wait for the morning.

### Backups off-box

`backup.sh` every 6 h into the instance's `/var/backups/<project>` (`verify.sh` replays every journal in a throwaway
host with no network before the tarball is written); hbox pulls 30 minutes later into `/tank/<project>-backups` and
replays the newest (DEPLOY "Durability and backups"). A backup on the box that holds the journal is a copy of a torn
tail, not custody.

- **Pull, not push:** hbox holds a read-only key (`rrsync -ro`, one directory) to the workhorse; the workhorse holds no
  credential to hbox, so a box that is taken cannot reach its own backups.
- **Retention** on the puller: every tarball 7 days, the first of each UTC day 56 days, the first of each month always.
  Each closing backup of a carried directory is kept in `closing/`.
- **Drills:** every pull replays the newest tarball; once a quarter `restore.sh` into a scratch directory with the
  stack brought up against it on another port (DEPLOY "The restore drill"). The verify is the backup; an unverified
  tarball is a file.

**Decision:** pull every six hours with a read-only key; retention 7/56/forever; the replay on every pull, the restore
drill quarterly.

### The upgrade path

- *The same edition and library:* a restart in place under the new image, the journal untouched (DEPLOY "A new
  binary", *It replays*). If the new compiler refuses an old object, `world-open` fails and the old tag goes back.
- *A new edition, a new library, or objects that move:* the world is carried, never begun again (FOUNDATION §2), into
  a new data directory under the new image (DEPLOY "A new binary", *It carries*). Kept: every object, name, receipt (by
  its old slug), post address, grant, suspension and setting. Lost: chain continuity (the carried genesis cites the old
  head; entries before it are not re-judged) and whatever the owner lists under `--leave`, carried retired.
- *No wipe.* A genesis while a town journal lives under the instance's root is refused, naming each journal, unless
  `--wipe-with-the-owners-word R` (DEPLOY "First start"). A commit whose binary neither replays nor carries the newest
  town backup does not merge: `deploy/carry-check.sh` on hbox before each merge touching the host (DEPLOY "Before a
  merge that touches the host").

**Decision:** same edition and library is a restart in place; anything else is a carry; a genesis over a living town
only with the owner's word; no commit merges that does not carry the newest backup.

### The operator's loop

*Daily, 10 to 15 minutes:* the watch's lines in Zulip; the outbox (posting on Delve is a human click: at ~30 s a draft,
a hundred drafts is 50 minutes, the real cost of the town); `hand log` for the night's refusals; the day's spend; the
reports residents put in the mending basket (`/hand/<world>/reports`, or polled: `GET
/hand/<world>/reports.json?since=<cursor>`; docs/MENDING.md); `hand automod` for what automatic moderation flagged.

*Weekly, 30 minutes:* `deploy/ring/harvest.py --run <data directory>` (its layout, journal beside `state/`, is the run
directory's), read for recurring refusals per principal, cards drafted and never quoted, no-reply posts; the newest
tarball replayed on hbox; `df`; the anchor's installed Caddyfile against dregg-infra's anchor Caddyfile; the
key's age (rotate quarterly).

**Decision:** the daily cost is the outbox, not the machine.

### Spend caps

Haiku at $0.10 per million input tokens and $0.50 output; a reading is 800 to 1,200 tokens in and 35 to 378 out, about
$0.0002 a call. Interpretations are capped per principal per hour (`interpretQuota`, 48). Forty residents at that cap
are 1,920 calls an hour, $0.40 an hour: the money is not the risk; the behaviour is (a loop, a card that reads
everything).

So the world has a **hard cap per day on model calls, as a host quota**: `modelQuota` in `settings` (journaled; moved by
`world-settings`), counted from the clock day's suspended-with-`interpretation` entries plus `attempted` retries; an
`interpret` past it refuses `quota` with `next` the next day's first minute, and the opener and the clock are not
exempt (the loop case is theirs). The host's default is 2,000 (`Limits.modelQuota`, about $0.45); an open town sets it
from `hob_budget` and its paints from `paint_budget` (`hand limits`). Automatic moderation has its own day,
`automod_daily_calls` (2,000). `hand spend` is the monthly total against the grant.

**Decision:** `modelQuota` per world per day in the host, opener included.

### What the ring's harvest already gives

`deploy/ring/harvest.py` over a run directory, no network: journal outcomes and refusals by class, drafts (posted,
skipped, usage, offerless, over 1,400, refused without a voice line), bridge steps and holds, interpretations settled
and pending, model calls and tokens, hand actions, the access log's 4xx, 5xx and top paths, addressed posts with no
reply, journal height, bytes and median suspension; per principal, posts, spells, prose, `?`, Bend, refusals and
recurring refusals, minutes to first spell; the three arcs; cards quoted and never quoted. It runs unchanged on a live
data directory. What it does not give: anything per hour, the clock, the backup, the disk, spend in dollars, scratches;
those are the watch's.

**Decision:** the harvest is the weekly report; the watch is the 5-minute one; neither grows into the other.

## c. The bounds that end a town

1. **The journal bound.** `Limits.maxJournalBytes` is 4 GiB (the chain and its block store). An open holds the chain
   and reads only the snapshot and the entries after it, so the bound is the disk's, not memory's. It is met at
   append (`durable`), never first at a restart: an append that would come within `Limits.journalHeadroom` (1 MiB)
   of it is refused `capacity` naming the bound, journaled into the headroom, so the operator sees it while the host
   still runs (tests/test_journal_bound.py). The watch speaks at 200 MiB.
