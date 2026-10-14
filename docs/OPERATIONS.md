# Operations

The transport's shape and the tooling for after the town, written 2026-10-10
against foundation dd5cd2f, DEPLOY (the runbook as it stands), FEDERATION
(`serve`, scratch worlds), RING-OF-FIRE §4 to §6, the codex review of the
transport and the Zulip playtest. Every section ends with its decision.

## a. The transport's shape

**Measured** at dd5cd2f: `transport/` is 4,271 lines in 15 files (FOUNDATION
§7 said 4,233 on 10-10 against a ceiling of 4,400); `deploy/` is 1,443 lines
of Python in 8 files plus 594 of shell and compose. By role:

| Role | Files | Lines | What it decides |
| --- | --- | --- | --- |
| adapters: Delve, Zulip, the model | `delve.py` 148, `observe.py` 172, `zulip.py` 282, `post.py` 285, `model.py` 225 | 1,112 | nothing since host12: reservations, retries and the spell classifier moved into the host (5.107, 118, `spell-parse`) |
| the front: routes, pages, the claim, the login, the repository façade | `http.py` 941, `pages.py` 269, `identity.py` 193, `oauth.py` 241, `repo.py` 209 | 1,853 | rate limits per credential and address, body limits, the 30 s deadline, which page renders; the claim's challenge is Python's (identity.sqlite) |
| the bridge: routing and drafting | `bridge.py` 550, `interpret.py` 86 | 636 | where a post reaches (`route`; the host now checks `reach`), when to draft, the deliver rounds |
| the hand | `hand.py` 289 | 289 | nothing; every action is a click or a verb |
| process management (deleted since: `serve` holds the lock, every world, the scratch worlds and both sockets) | `hostd.py` 162, `hostproc.py` 219 | 381 | the lock, a pool of 8 per-principal host processes, the socket |

The state the Python keeps beside the journal is 20 kinds under `<state>/`:
`access.log`, `awaiting/`, `binary-pin`, `bridges/`, `hand-log.jsonl`,
`scratch/`, `host.sock`, `serve.pid`, `identity.sqlite`, `interpretations/`,
`journal.lock`, `library/`, `mentioned.txt`, `model-spend.jsonl`,
`observe.sqlite`, `outbox/`, `posting/`, `principals.txt`,
`publications.after`, `since`, `skipped.txt`, `worlds/`. Configuration is 95
`add_argument` flags across the programs and 18 `DELVETALK_*` environment
variables. Three daemon loops share one `daemon()`; `write_atomic` is
imported from `bridge` by four modules; `canonical` from `delve` by all.

The review's 15 transport findings: 4 were Python deciding (7, 9, 10, 11),
closed by moving the decision into the host; the rest were races in the file
state (2, 3), limits (4, 6), a lost field (8, 13, 14) and the claim (15). The
playtest's five live failures: the post quota applied to the owner's Zulip
(43 silent minutes; now per source in the host), the model's reasoning in the
`needs` slot (hob's three answers, 5.117), a journal that did not survive a
rebuilt host (the replay edition rule), a stale tree on hbox, `127.0.0.1`
links in posts (`reachable()`). Four of five moved into the host or a rule;
one was a deploy habit.

**Three shapes.**

*Keep Python as adapters.* FEDERATION 1 lands `serve` and deletes the daemon
(−381); the host owns the socket and the lock; the front's pages stay Python.
Cost: nothing new. What stays: 20 state kinds in ad-hoc formats, each with its
own race (review 3: a backup can carry `settled: true` beside a pending
request; the `since` cursor; `skipped.txt` as a set), and 95 flags.

*The front in Lean.* One binary serving HTTP. Lean has no HTTP server in
`std`: an HTTP/1.1 reader with the deadline and the worker bound (420 lines
of the front today) is ~800 lines of Lean; the login needs an AT Protocol
OAuth client with DPoP ES256, `cryptography` today, so a C FFI (unverified C
in the TCB) or a Lean P-256; the pages are a 269-line renderer; the Delve
and Zulip clients and the SQLite observer follow. Roughly 3,500 lines of Lean
for 1,853 of Python, plus the crypto. Gain: one process, one state (the claim
a journaled fact), no socket hop (0.21 ms). Loss: the voice lanes re-cut
pages weekly; the host's TCB grows by a public-facing HTTP parser.

*One coherent Python program.* A `delvetalk` entry point with subcommands
(`serve`, `bridge`, `interpret`, `post`, `hand`, `open`, `genesis`, `backup`,
`spend`, `harvest`, `watch`) over one `HostClient`, one `State` class that
owns the layout above (every path and format in one file, so a race is fixed
once), and one `delvetalk.toml` (origin, worlds and bridges, key file,
credentials path, quotas, the opener) replacing the flags and variables.
Net lines about the same; the gain is one place for the file state and the
config. The risk is a rewrite re-breaking the 15 fixes; `test_hypermedia`,
`test_zulip`, `test_bridge`, `test_hand` and `test_post_reserve` pin the
behaviour, so this is a refactor under them, file by file.

**Recommendation.** The pile is fine as adapters. The bug class the review
found was Python deciding, and the fix for that class is moving decisions
into the host, which is done for every finding that named one; reshaping the
Python would not have found any of them. The one real smell is the file
state: 20 kinds, no owner. So: keep Python as adapters (FEDERATION 1 deletes
the daemon), then fold the state and config into one `State` and one
`delvetalk` entry point as a refactor under the existing tests, in the first
month after launch, deleting `write_atomic`'s four imports and the three
`--once/--poll` arg sets on the way. The Lean front is not before the town
and not for its own sake: it earns its place only if the claim must become a
journaled fact or the socket hop shows in the access log, and neither is true
now.

**Decision:** adapters now; one `State` and one entry point after launch as a
refactor; no Lean front.

## b. Production tooling after launch

### One state, one config, one entry point (lane/transport6)

§a's verdict, done now rather than after launch: the 20 state kinds, 95
flags and 18 variables become one layout, one config and one command.

**`transport/config.py`: one `Config`.** A frozen dataclass; every setting
the programs share is a field with a default and a one-line description,
and nothing else holds a default. `Config.load(state)` reads
`<state>/delvetalk.toml` (`tomllib`; optional; an unknown key or a value of
the wrong type is refused by name), then the environment: `DELVETALK_<FIELD>`
overrides `<field>` (`DELVETALK_ORIGIN`, `DELVETALK_ROOT_SOCKET`, …).
Precedence: default, file, environment. Compose's environment carries only
what is a fact of the container (mount paths, secret files, the bind address);
the operator's choices live in the file. Fields: `origin`, `opener`,
`host_socket`, `root_socket`, `root_group`, `library`, `sync`, `obend`,
`poll`, `http_bind`, `http_port`, `firehose_bind`, `firehose_port`, `trust_proxy`, `hand_bind`, `hand_port`,
`hand_token_file`, `summon_handle`, `requests`, `hosted_accounts`, `participants`, `credentials`, `lexicon_authority`, `poster`, `hand_find`, `repo_keys`, `backups`,
`anthropic_key_file`, `model_auth`, `model_thinking`, `model_account`,
`key_name`, `tokens_toml`, `delve_mock`, `model_mock`, `watch_zuliprc`,
`watch_stream`, `watch_topic`, `grant`. A world's bridge (Delve or a Zulip
channel, its rc) is not a field: it is the world's row, which `open` writes.
`lexicon_authority` is the schema publication DID, default `did:plc:6amo7col5h4ciq2gpm5eur7b`, named by the live
`_lexicon.gsb.fg-goose.online` TXT. `DELVETALK_LEXICON_AUTHORITY` overrides it. An authorized `lexicons` step
requires `credentials` to authenticate as that DID before any record write (ATPROTO §5).

**`transport/state.py`: one `State(root, world, config)`.** Every path is an
attribute named once; no other module joins a path under `<state>/`. One
directory per world for everything that is the world's, the town's included
(it was the top level, every other world `worlds/<w>/`):

    <state>/delvetalk.toml            the config
    <state>/<world>.journal(.blocks)  serve's, with journal.lock, serve.pid, binary-pin, library/, scratch/
    <state>/host.sock, root/root.sock serve's sockets (host_socket, root_socket move them)
    <state>/identity.sqlite           claims: a principal is global
    <state>/access.log(.1)            the front's, `... <did or -> <world>`, then for a 4xx or 5xx `class=<envelope class>[:<host stage, clause or class>]` (a fixed identifier, never a body, credential or reason), then `auth=<code>`
    <state>/hand-log.jsonl            the hand's actions, each with its world
    <state>/model-spend.jsonl         one line per replied model call, with its world
    <state>/lexicons/<URL-encoded authority DID>.json  account-wide published schema digests, never deletes
    <state>/bridges/<world>.json      a world's bridge row
    <state>/hosted/<URL-encoded origin>/*.json  optional public request snapshots, signing key ids and epochs;
                                      keys derived from the town key and DID, directory fd flock
    <state>/worlds/<world>/           observe.sqlite, since; outbox/, awaiting/;
                                      principals.txt, mentioned.txt, skipped.txt,
                                      publications.after; posting/; interpretations/;
                                      bridge.pid, interpret.pid; watch.jsonl, alerted.json;
                                      repo.json (chain epochs), events (durable firehose log);
                                      requests.json (participant revisions and refused CIDs), answers/
    <repo_keys>/<world>.key           the repository's signing key

`events` is fsynced before emission; its independent seq survives carry and front restart. Backups keep it
with `repo.json`. The newest 10,000 events are replayable, compacted by atomic rewrite at 20,000; loss of
`events` loses cursor continuity. `firehose_port = 0` disables the listener; enabling it requires the world's
signing key, a private port mapping on `delvetalk-http` and the edge WebSocket route (DEPLOY "Firehose").

`requests = false` disables public request polling. `participants = ""` is the owner's explicit space-separated
list of did:plc or hostname-level did:web DIDs; `DELVETALK_PARTICIPANTS` overrides it. The registry unions that list
with active pds.delve.town repositories and verified DIDs in `identity.sqlite`. Every participant is read at its DID
document's PDS through pinned public HTTPS. Documents cache for ten minutes, with one refresh on verification
failure per participant per poll; 256 non-delve-PDS participants may be read in a poll, every overflow DID reported.

`hosted_accounts = false` disables guest/Zulip repository provisioning, serving and the local poller source;
it preserves guest principals and the identity mapping. The front only removes canonical snapshots of guests
no longer verified, leaving active guests and other operator data alone. Enable it with `hosted_accounts = true`;
`DELVETALK_HOSTED_ACCOUNTS=on` is the environment override (compose passes `.env`, default `off`).
Enabling hosting also requires wildcard DNS, HTTPS routes/certificates and `<repo_keys>/town.key` (DEPLOY).

`worlds/<world>/requests.json` is `{revs: {did: {pds, rev}}, refused: {uri: {cid, why}}}`. A matching PDS and revision
skips listing; a changed PDS scans the whole collection. Consumed URIs and their first proven CIDs remain in
`observe.sqlite`; neither consumed nor refused state is cleared at migration. Unread participants keep their last
pair for retry. Keep both files and `answers/` in backups. ATPROTO §2 gives the proof and revision rules.

`State` also hands out the host clients (`host()`, `root()`),
`write` (atomic, the one `write_atomic`), the outbox reads, the daemon loop
with its pid heartbeat, and the bridge row.

**`python3 -m transport <command> --state DIR --world W`.** `--state`
defaults to `DELVETALK_STATE`, `--world` to `town`. Commands take only what
the config does not hold:

| command | its own arguments | replaces |
| --- | --- | --- |
| `serve` | none: execs `delvetalk-obend serve` with the config's sockets, opener, library and sync | compose's argv, `DELVETALK_OPENER` in two places |
| `bridge` | `--once`, `--since ISO`, `--now SECONDS` | `transport.bridge run` and its 13 flags; `--source/--zuliprc/--stream/--topic` come from the row |
| `lexicons` | `--authorized`; default offline inventory needs no state; publication requires state and the authority credential | schema publication (ATPROTO §5), never a daemon |
| `interpret` | `--once` | `transport.interpret run` |
| `post` | what to post (`--draft` or `--text-file`; an agentwiki post is its header line), `--intent`, `--object`, `--slot`, `--reply-to`, `--mention`, `--topic`, the authorizing flag | `transport.post post` and `transport.zulip post`: the world's row says where the post goes |
| `hand` | its verbs, as now, plus `spend [--month]` | `transport.hand`, `deploy.spend` |
| `http` | none | `transport.http` and its 6 flags |
| `open` | the row: `--transport`, `--realm`, `--channel`, `--topic`, `--zuliprc` | `deploy.open` |
| `watch` | `--unhealthy SERVICE…`, `--dry-run`; probes itself | `deploy.watch` and `hand status --json` piped into it |
| `repokey` | `--curve` | `deploy.repokey` |
| `status` | `--health host\|http\|hand\|bridge\|interpret` (exit status) | `hand status --json`, the five inline healthchecks |

Deleted on the way: `bridge outbox`, `mark-posted` and the printed post
commands (the hand's `outbox` and `post` are the one way, and `post` of a
draft goes where its world lives, Delve or Zulip), `post --wiki-page/--wiki-edit/--body-file`
(an agentwiki post is its header line), `zulip observe`
and `Observer.drain` (the hand's `inbox` reads the same table), the model's
one-request CLI, `add_host_args`/`connect`, every module-level `os.environ`
read, the transport's imports of `deploy` (`spend`, `genesis.OPENER`).
`deploy/` keeps the shell, compose, genesis and seed (the objects lane's),
`serve.py` (serve as a child for tests and scripts, its argv from `State`)
and the measurement tools. A data directory from before this moves the
town's per-world files into `worlds/town/` once (DEPLOY).

**Decision:** one `Config` (file, then `DELVETALK_*`), one `State` that owns
every path, one `python3 -m transport`; the town is a world like any other.

### Monitoring

What to watch, its source, and the number that means trouble. One probe,
`python3 -m transport watch --world W` per world, run by a systemd timer
every 5 minutes: it probes (`status`), appends the probe to the world's
`watch.jsonl` and reads the thresholds from it. No agent, no exporter.

| Watch | Source | Trouble |
| --- | --- | --- |
| 5xx answered by the front | `access.log`, `awk '$4 >= 500'` (ring gate: 0) | any in 5 minutes |
| refusals by class | `world-status.hour.refused` (ROOT §4; until then, the hour's `world-entries`) | `capacity` ≥ 1; `quota` > 5/h; `staleRoot` > 10% of turns |
| model calls and spend per hour | `hour.interpretations + attempts`; `model-spend.jsonl` summed by hour | > 120 calls/h, or the day past the cap (below) |
| reservations held | `world-status.posts.sources[delve]`: `used` of `quota`, `next` | 16 of 16 for two hours (the hand is not clicking, or a loop is drafting) |
| scratch worlds | `world-status.scratches {open, expiring}` (FEDERATION 2) | open > 40, or any over 16 MiB |
| journal height and size | `world-status.height`; `stat state/town.journal` | height unchanged for an hour while posts were observed; bytes > 200 MiB (see §c) |
| suspension median | `harvest.py`'s `medianSuspendedBytes` (weekly) | > 8 KB |
| the clock advancing | `world-status.clock` against `now // 60` | behind by > 3 minutes: the bridge is dead (its `tick` is the only clock) |
| pending interpretations | `world-interpretations`: count and the oldest's `attempts` | > 20, or any at attempt 8 |
| the backup verify | the timer's last exit and the newest tarball's age in `/var/backups/delvetalk` | exit ≠ 0, or age > 7 h |
| the processes | compose healthchecks (`delvetalk-host` answers status; the front's `entry N`; `bridge.pid`/`interpret.pid` younger than 180 s) | any unhealthy |
| disk | `df /var/lib/delvetalk /var/backups` | < 20% free |

**Decision:** one probe, one JSONL file, one timer; the counters the host
does not yet answer (`hour`) are ROOT §4's second item.

### Alerting

The watch posts to the owner's Zulip (the config's `watch_zuliprc`, a
stream `delvetalk-ops`), which reaches the phone through
Zulip's own push; nothing else is installed. One message per condition per 6
hours (the world's `alerted.json` of condition to last-sent), the message
naming the number and the playbook (below) by letter. Two conditions page at
once and repeat hourly: the host unhealthy, and the backup verify failed. The
rest are the daily loop's.

**Decision:** Zulip is the pager; two conditions repeat, the rest wait for
the morning.

### Backups off-box

Today: `backup.sh` every 6 h into `/var/backups/delvetalk` on the workhorse
(`verify.sh` replays every journal in a throwaway host with no network before
the tarball is written), pulled to hbox's `/tank/delvetalk-backups` 30 minutes
later and the newest replayed there (DEPLOY, "Off the box, by pull, to hbox";
since 2026-10-10). A backup on the box that holds the journal is a copy
of a torn tail, not custody.

The target is the owner's choice (a Hetzner storage box, a disk on the
laptop, hbox once `/tank` has room). The mechanism is a **pull**, not a push:
the puller holds a read-only key to the workhorse's `/var/backups/delvetalk`
and runs `rsync -a --ignore-existing` hourly; the workhorse holds no
credential to the target, so a box that is taken cannot reach its own
backups. Retention on the puller: every tarball 7 days, the first of each
day 8 weeks, the first of each month kept. A monthly drill on the puller:
`verify.sh --image delvetalk-host:<sha> <untarred>` on the newest tarball,
and once a quarter `restore.sh` into a scratch directory with the stack
brought up against it on another port. The verify is the backup; an
unverified tarball is a file.

**Decision:** pull hourly with a read-only key; retention 7/56/forever; the
monthly verify is a timer on the puller, the quarterly restore a calendar
entry.

### The upgrade path

*A new image, the same `replayEdition`.* DEPLOY's "A new binary": back up
with the old image, `build.sh` (two builds of one commit print one SHA-256;
record it), load, set `.env`, `docker compose --profile town up -d --wait`,
`smoke.sh --pin`. The journal is untouched; replay recompiles every pin from
journaled sources; if the new compiler refuses an old object, `world-open`
fails and the old tag goes back. Restart in place, ten minutes, no post.

*A new edition, or a new library.* The journal does not reopen ("carry
it", HOST-HANDOFF 6), or serve refuses the library's bytes. The world is
carried, never begun again (FOUNDATION §2): stack down, back up with the
old image, the head snapshots written by the old image (`verify.sh
--snapshot`), `python3 -m transport carry` into a new data directory under the
new image, up, smoke, and the hand's one line in the channel (DEPLOY "A new
binary", *It carries*). Kept: every object, name, receipt (by its old slug, in
the carried world itself; no archive is served), post address, grant,
suspension and setting. Lost: chain continuity (the carried genesis cites the
old head; entries before it are not re-judged) and whatever the owner lists
under `--leave`, which is carried retired. An hour, one post.

*No wipe.* A genesis while a town journal lives under `/var/lib/delvetalk`
is a wipe, and `deploy.genesis` refuses it, naming each journal, unless
`--wipe-with-the-owners-word R`: the owner's word, the town's first line and
the welcome's (DEPLOY "First start", FOUNDATION §2). A commit whose binary
neither replays nor carries the newest town backup does not merge:
`deploy/carry-check.sh` on hbox before each merge touching the host (DEPLOY
"Before a merge that touches the host").

**Decision:** same edition and library is a restart in place; anything else
is a carry; a genesis over a living town only with the owner's word; no
commit merges that does not carry the newest backup.

### Incident playbooks

Each: the symptom, the first command, the fix, the line in the channel, what
to record. The channel line is the host's or hob's register (VOICE): no
apology, what happened, what to do next.

**A. The host will not start.** Healthcheck red; every reply "host
unavailable". `docker compose logs delvetalk-host` names it: `journal
broken at height N: unterminated final line` (a torn tail: DEPLOY "A torn
tail", via a verified copy); `height out of sequence` (a second writer: find
it before anything else; `journal.lock` exit 75 says who); `journal replay
edition 1; this host is 2` (set the old tag back; a new edition is the
upgrade path above); `journal exceeds byte capacity` (§c); the library's
bytes differ (restore `<state>/library` from the image of the same commit).
Channel: `hob: the host is down; the hand is on it. Spells wait; nothing
sent is lost.` Record: the height and the cause in the moderation log.

**B. The bridge posts garbage.** On Delve nothing posts without a click:
`hand skip DRAFT --reason`. On Zulip the bot posts itself: `docker compose
stop delvetalk-bridge` first, then `hand unpost URI`, then find the card
(`hand find`) and `retire` it (ROOT §3) if its render is the cause. Restart
the bridge. Channel: `hob: the hand withdrew that; its receipt stays.`
Record: the object and the receipt.

**C. The model is down.** Interpretations pile up; `attempted` entries with
backoff to 60 clock minutes, 8 attempts, then `unclear: model: transport` as
the verdict; spells unaffected. Nothing to fix on the box: switch
`DELVETALK_MODEL_AUTH=oauth` (the fallback accounts) if the key is the
problem; otherwise wait. Channel: `hob: I cannot read words for now; a spell
needs no reading. The cards still answer.` Record: the hour and the count of
`attempted`.

**D. A quota is exhausted.** Three quotas. Post (16/h on Delve): drafts held
`rate_limited`, the strip shows `16 of 16`, `next` the clock; wait, or
`settings --post` if etiquette allows. Interpret (48/h per principal):
`quota` refusals with `next`; the resident is told by the host's own line;
nothing to do unless it is a loop (B). Model cap (below): the whole world's
words wait until the clock day turns; `settings --model` raises it with a
reading. Channel for the last: `hob: my readings for today are spent; spells
run as they always do.` Record: which, and whether it was a loop.

**E. A resident is abusive.** `hand quiet WHO --hours 24 --reading R`; if a
card carries it, `hide` then `retire`; `unpost` what the bot already said on
Zulip. Channel: hob's quiet line (ROOT §3), once. Record: the reading is the
record; it is on the receipt.

**F. The box is full.** `df`; stop the writers first: `docker compose stop
delvetalk-bridge delvetalk-interpret` (the host keeps answering reads; an
append whose fsync fails is a refused op, not a lost one). `du -sk` and rank:
`/var/backups/delvetalk` (same disk; move the target), old image tags,
`<state>/scratch` (scratch worlds, not custody: the hand may `expire` them), the access log (16 MB, one
generation). Delete only what the puller already holds. Channel: `hob: the host is full; the hand is making
room. Spells wait.` Record: what was removed and why.

**Decision:** six playbooks, one command each to diagnose; A and F lose data
if done in the wrong order, and both start by stopping the writers.

### The operator's loop

*Daily, 10 to 15 minutes:* the watch's morning summary in Zulip (every
counter, every threshold crossed); the outbox, since posting on Delve is a
human click (the playtest's three residents made 44 drafts in 74 minutes; at
~30 s a draft a hundred drafts is 50 minutes, the real cost of the town);
`hand log` for the night's refusals; the day's spend; the reports residents put in the mending basket
(`/hand/<world>/reports`, or polled: `GET /hand/<world>/reports.json?since=<cursor>`; docs/MENDING.md).

*Weekly, 30 minutes:* `harvest.py --run /var/lib/delvetalk/v2` (its layout,
journal beside `state/`, is the run directory's), read for the ring's
columns: recurring refusals per principal, cards drafted and never quoted,
no-reply posts; the newest tarball verified on the puller; `df`; the
Caddyfile against dregg-infra's source (it had drifted on 10-10); the key's
age (rotate quarterly).

**Decision:** the daily cost is the outbox, not the machine; budget the hand
for a hundred drafts a day before the ring says otherwise.

### Spend caps

Rates: Haiku at $0.10 per million input tokens and $0.50 output; the
playtest's calls were 800 to 1,200 in and 35 to 378 out, about $0.0002 a
call. The quota that exists is per principal per hour (48). Forty residents
at the cap is 1,920 calls an hour, $0.40 an hour, $10 a day: the money is
not the risk; the behaviour is (a loop, a card that reads everything).

A **hard cap per world per day on model calls, as a host quota**:
`modelQuota` in `settings` (journaled at first naming; moved by
`world-settings`, ROOT §3), counted by `record` from the clock day's
suspended-with-`interpretation` entries plus `attempted` retries; an
`interpret` past it refuses `quota` with `next` the next day's first minute,
and the opener and the clock are not exempt (the loop case is theirs).
Defaults: 2,000 for `town` (~$0.45), 500 for a Zulip world. `hand spend`
stays the monthly total against the grant.

**Decision:** `modelQuota` per world per day in the host, opener included;
2,000 and 500.

### What the ring's harvest already gives

`deploy/ring/harvest.py` over a run directory, no network: journal outcomes
and refusals by class, drafts (posted, skipped, usage, offerless, over 1,400,
refused without a voice line), bridge steps and holds, interpretations
settled and pending, model calls and tokens, hand actions, the access log's
4xx, 5xx and top paths, addressed posts with no reply, journal height, bytes
and median suspension; per principal, posts, spells, prose, `?`, Bend, refusals
and recurring refusals, minutes to first spell; the three arcs; cards quoted
and never quoted. It runs unchanged on the live data directory. What it does
not give: anything per hour, the clock, the backup, the disk, spend in
dollars, scratches; those are the watch's.

**Decision:** the harvest is the weekly report as it is; the watch is the
5-minute one; neither grows into the other.

## c. The three to do before the town

1. **The journal bound.** `Limits.maxJournalBytes` is 256 MiB and is checked
   at `world-open` only (`Session.lean:81`): a live host appends past it and
   the next restart refuses the file by name. The ring's go/no-go allows
   8 MB a day; that is day 33. Run 11 was 2.5 KB an entry. Raise the bound
   (4 GiB; the snapshot every 1,000 entries makes reopen a tail replay
   whatever the length) and refuse at append when within 1 MiB of it, so the
   limit is a `capacity` receipt and not a dead town. One line in `Store.lean`,
   one check in `durable`, one test.
2. **Backups off-box with one restore done.** DEPLOY says the off-box copy is
   not set up. The pull above, and a restore into a scratch directory
   brought up on another port once, before the welcome is posted. A town
   whose only copy of the journal is on the box that fsyncs it has no
   backup.
3. **The watch and its pager**, with the model cap as its first threshold:
   ~150 lines (`transport/watch.py`: the probe per world, the
   thresholds, the Zulip post, the dedupe file), one systemd timer. The
   playtest's 43 silent minutes were found by a resident asking "what ran?";
   the watch finds the next one in five.

ROOT's three (quiet, retire, the metarule; `world-settings` and `hour`; the
hand's verbs) are the moderation half of the same week.

**Decision:** 1, 2, 3 in that order; none of them needs the ring to run
first, and 1 is a day's work that otherwise ends the town in its second
month.
