# The ring of fire

A season of use before delve.town: model agents we run ourselves play DelveTalk in the
owner's Zulip for three days, and each day's findings become lanes before the next.
Checked 2026-10-10 against `deploy/playtest.sh`, `transport/{zulip,bridge,interpret}.py`,
`rehearsal/{rehearse,summary}.py`, `docs/{VOICE,GENESIS,AGENTS-API}.md` and the four
resident harnesses in `~/dev/allgame`.

## 1. What the ring is for

The 1,106 tests say the host does what the design says; the replay gate (run 11) says the
town's archived hour comes out the same offline. Neither says what happens when someone who
did not read the design meets the welcome card. Only use produces that: a round trip that
transfers no authority (a proposal held for an owner who never comes); a card whose first
line misleads; a quest that stalls because the next spell is not printed; a voice that slips
into apology; a quota that bites (the bridge's 16 posts an hour, shared by six); an object
nobody touches (`play`, `cistern`, `commons`); a folkway
(quote the card, cite the receipt by name, `?` before guessing) that takes, or does not.
**Decision:** the ring is not a test suite and adds no tests; its output is findings, each
with an owner, a fix and a gate, in the rehearsal's form.

## 2. The arena

Two candidates. **Zulip through `deploy/playtest.sh`**: a fresh hostd and journal, genesis,
the v2 welcome in the stream's `welcome` topic, the bridge observing one stream and posting
drafts back itself inside `postQuota`, the interpreter on Haiku 5.5 every 20 seconds. The
residents are the owner's allgame harnesses, already Zulip users with memory, a judge and
lurk decay. **A loopback harness**: `tests/test_zulip.py`'s `FakeZulip` grown into a town
simulator, the residents driven by `claude-* -p` or `codex exec` per message. Cheaper and
faster (a day in an hour); it teaches nothing about pacing, quotas or attention, which the
simulator would invent, and its residents would need the zuliprc within the model's reach.
**Decision:** Zulip
through the playtest script; the fake stays the transport's test. The ring runs in its own
stream `ring` (not `delvetalk`, so the owner's playing and the residents' stay separable), the
residents' only standing stream.

## 3. The cast

Six roles, six Zulip users. Each is an allgame harness with its own state directory:
`identity.md` there is the brief (the harness writes a default only when the file is absent,
so the brief is written first), `sysadmin_inbox.md` the ring rules (3a); the judge and lurk
decay set the cadence. No resident reads this document, VOICE, FOUNDATION or the
repository. The harness holds the zuliprc; the model sees `send_message`, never the file.

| Role | Harness | Model | Why this model |
| --- | --- | --- | --- |
| newcomer | `glm_resident` | glm-5.3-flash | the cheapest, most literal reader we have |
| forger | `kimi_resident` | k3 | writes code well; its tool jail already excludes the shell |
| gardener | `sonnet_resident` | claude-sonnet-4-6 | steady; cheap enough for the most frequent turns |
| provocateur | `glm_resident` under the grok gateway | grok-4.7 | another temperament; breaks things politely |
| the quiet one | `glm_resident` | glm-5.3-flash | a second GLM instance; only rains |
| chronicler | `claude_resident` | claude-opus-4-6 | the record needs the best writer; few turns |

`gpt-6.1-sol` (`codex exec`, read-only) does not play; it reads each harvest and drafts the
triage, as the codex facets read the tree. Haiku 5.5 is the interpreter, as in production.
The briefs, in the voice of the residents' own identity files:

**Newcomer.** I'm new here. Someone posted a welcome in `#ring › welcome` and I've read it
and nothing else; I don't know what DelveTalk is beyond what that post says. I want to plant
something and see what comes back. When I'm refused, I read the refusal and try once more the
way it tells me; if that fails too, I ask in plain words. I quote the card I'm answering. I
never guess at a spell I haven't seen printed.

**Forger.** I write Bend. The welcome's dialect note is my whole reference until the workshop
answers me; the STUDIO door is my REPL and heap. I check before I propose, propose to things
I planted before things others own, and when the checker refuses I post what it said and what
I changed. I post code in a ```obend block, at most twice an hour. I keep a list of what the
checker told me that the welcome did not.

**Gardener.** I tend. I plant a few bells, rain on others' plantings before my own, subscribe
to the tide and tick it when it's due, and visit the Moss Gate. I read cards fully and reply
on the card, not the thread root. When something I planted grows, I say what changed in one
line. I ask `delvetalk <card> ?` before I try a spell I haven't seen.

**Provocateur.** I find the edges, politely. I try a second cistern, a tick too soon, a rain
on my own bell, a spell with a field it doesn't take, a change to someone else's subscription,
a proposal the law should refuse, the same intent twice. I never flood: one probe, then I read
the receipt and say what the clause was and whether its reading made sense. I'm after refusals
whose note doesn't tell me what to type next.

**The quiet one.** I rain. I read what others plant and reply with `rain` and a short text,
one or two an hour, nothing else. I never plant, never summon, never write prose to a card. If
a rain is refused I try once more the way the note says and then stay quiet.

**Chronicler.** I keep the record. Each hour I read `#ring` and submit one line to the
anthology for what happened; each evening I post `wiki: Ring, day N` in a topic of that name
with who did what, which receipts mattered, by name, and what was refused. I quote cards and
cite receipts by their spoken names; I never paste a hash.

### 3a. The ring rules (every `sysadmin_inbox.md`)

- Your only room is `#ring`. Do not read or post elsewhere, do not mention anyone outside it.
- No credentials, no web, no sandbox. The only address beyond Zulip is the STUDIO link the
  welcome prints, and only the forger uses it.
- At most forty posts a day. A day ends when the ring stops; the next starts fresh in the same
  stream with your memory kept.
- Quote the card you answer. Cite receipts by name. Never repost a message that got no reply;
  reply again and ask for the receipt.

What allgame needs (the owner's code; we do not edit it): `kimi_resident` has no `--state-dir`
(`config.STATE_DIR` is a constant; its MCP server already honours `YUE_STATE_DIR`);
`glm_resident` derives `AGENT_SDK_CONFIG_DIR` from `DEFAULT_STATE_DIR`, not the flag, and
fixes `ZAI_BASE_URL`/`ZAI_KEY_FILE` in `config.py`. Three one-line env overrides
(`RESIDENT_STATE_DIR`, `RESIDENT_BASE_URL`, `RESIDENT_KEY_FILE`) let one harness serve the
newcomer, the quiet one and the provocateur (the grok gateway `claude-grok` starts is an
Anthropic-compatible endpoint at `127.0.0.1:8317`). Web and sandbox tools are forbidden by
the brief, not by code; enforcing that is a per-role tool subset, one list per config.
**Decision:** six fresh bot users (`.zuliprc-ring-<role>`, created by the owner, subscribed
to `ring` alone, since a harness backfills every stream it can see; Kestrel, Yue and Claude
keep their lives), the three env one-liners requested of allgame before cycle 1, tool
subsets requested but not required.

## 4. The cycle

**A day of play**: eight hours wall, the cast started after the welcome is posted. The root
only watches `bridge.log`; the hand's CLI is used only to `skip` a draft that would loop.
**The harvest**, the same evening: `deploy/ring/harvest.py` over the run directory (section
6): the rehearsal's table (journal outcomes, every refusal class counted, interpretations,
drafts, held offers, budget hits, skipped drafts, posts that got no reply, 500s, journal
height and bytes) and the ring's own measures (section 5). `gpt-6.1-sol` reads the report
and drafts the triage. **The triage**: `deploy/ring/triage.md` filled in, one row per finding,
by the rehearsal's rules: owner (host, kernel, objects, transport, voice, docs), the exact
fix, the gate (a count or a string the next harvest shows). A resident's misreading that is
not the machine's goes to a separate table ("what the welcome did not say") and the voice
lane. **The redeploy**: lanes land, `make check`, `deploy/playtest.sh --stop`, a new run on a
fresh journal, the welcome posted again, the cast restarted with memory kept (the brief says
only the world is new).

**How many cycles.** One is a smoke test; two cannot show whether a fix held under the same
cast; three gives a day where the cast already knows the machine, the town's second week.
**Decision:** three cycles, two laptop days and one against the workhorse stack (section 7);
the go/no-go is read on the third day only.

**Go/no-go on the last day**, every item from the harvest:

| Fact | Must hold |
| --- | --- |
| HTTP 500 answered by the front (its access log, section 6) | 0 |
| offers the host holds that no draft carries | 0 |
| refusals drafted without a `refused <clause>: <reading>` line | 0 |
| every newcomer's first spell | admitted, or refused with a hint that worked on their second try |
| the three arcs (section 5) | each advanced by a principal whose brief did not name it |
| interpretations | under 48 an hour for every principal; no `quota` refusal of a first-try utterance |
| drafts held `rate_limited` | at most one poll's worth in any hour, none older than the hour |
| interpretations still pending at the end | 0; retries at most 1 per 20 |
| journal | under 8 MB for the day; median `suspended` entry under 8 KB |
| posts that got no reply and were addressed | 0 |

## 5. What to measure that the replay cannot

The replay feeds fixed posts and a mocked model. The ring measures the other direction, by
principal and by hour, from the run directory:

- **Time to first admitted spell**: the newcomer's first observed post to the first `admitted`
  entry whose identity is one of their spells, in minutes, and the refusals between.
- **Prose to spells by day**: `kind` counts from `observe.sqlite` and, within replies, lines
  starting `delvetalk` against lines that do not.
- **Which cards were quoted**: card ids (`garden/bell/3`) and door words in resident text,
  counted; cards drafted and never quoted.
- **Which refusals recurred**: class and clause per principal; a clause refused twice to the
  same principal is a hint that did not work.
- **Whether anyone used `?`**: `usage` drafts by principal, and whether a spell followed within
  the hour.
- **Whether anyone wrote Bend**: ```obend blocks observed; `check` and `propose` turns;
  `programRefused` with its clause; proposals held and adopted.
- **Whether an arc moved**: no document names the arcs, so this one does. **Garden:** plant,
  a rain by someone else, the cistern dug. **Workshop:** check, propose, held, adopt. **Rooms:**
  enter the Moss Gate, choose, leave, enter again after the cooldown. An arc advanced when a
  later step than any before it was admitted; advanced by someone not told to when that
  principal's role file does not name the arc's object.
- Also: posts per resident per hour (the forty), the hand's actions, interpreter spend.

**Decision:** these are columns of the harvest, not a second report.

## 6. The scripts

Under `deploy/ring/`. The transport lane owns `cast.sh` and `harvest.py`; `triage.md` and
`roles/` are this lane's. The residents are allgame's code and are not edited here.

**`deploy/ring/cast.sh`** starts, stops and lists the residents; the roster is the directory
it is given.

    deploy/ring/cast.sh start --stream ring --roles deploy/ring/roles [--state ~/.ring] [--allgame ~/dev/allgame]
    deploy/ring/cast.sh stop  [--state ~/.ring]
    deploy/ring/cast.sh status [--state ~/.ring]

`--roles` holds one directory per role with `brief.md` (becomes `identity.md`), `resident.env`
(`HARNESS`, `ZULIPRC`, `HANDLE`, the bot's Zulip name; optional `MODEL`, `ARCS`,
`RESIDENT_BASE_URL`, `RESIDENT_KEY_FILE`), and the shared `roles/RULES.md` (becomes
`sysadmin_inbox.md`). For each role: copy the brief and rules into `STATE/<role>` when
absent, write `cast.json` (role, harness, model, handle, arcs, started), then `uv run python
-m $HARNESS --zuliprc $ZULIPRC --state-dir STATE/<role> --standing-streams $STREAM` (kimi:
`--stream`) in its own process group, pid in `cast.pid`, log in `cast.log`. `stop` sends TERM
to each group and waits; `status` prints role, pid and the log's last line. It never reads a
zuliprc; it passes the path.

**`deploy/ring/harvest.py`** reads one playtest run and prints the report.

    python3 deploy/ring/harvest.py --run ~/.delvetalk-playtest/current [--cast ~/.ring] [--json]

Inputs, all under `--run`: `world.journal` (through `rehearsal.rehearse.journal_stats`),
`state/observe.sqlite`, `state/outbox/*.json`, `state/awaiting/`, `state/interpretations/*.json`,
`state/model-spend.jsonl`, `state/hand-log.jsonl`, `state/skipped.txt`, `bridge.log` (one JSON
line per step: `turns`, `failed`, `held`, `posted`), `front.log`. The front logs no requests
today (`Handler.log_message` is `pass` in `transport/http.py`): the transport lane adds one
line per request, `{at, method, path, code}`, before cycle 1, or the 500 row stays unread.
With `--cast`, each `<role>/cast.json` joins handles to roles and arcs. Output: Markdown in
`rehearsal/summary.py`'s table style, the rehearsal's rows first, then section 5's; `--json`
gives the same as one document for the triage reader. No network, no credentials.

**`deploy/ring/triage.md`** is the template: the header (run, day, commit, harvest SHA-256),
the findings table (`#`, finding, evidence as a harvest row or receipt name, owner, the exact
fix, done when), "what the welcome did not say", "laws working, not bugs", section 4's table
with the day's numbers, and the decision line.

The scripts are written here (238 lines). `harvest.py` ran against a `FakeZulip` day with
real genesis on hbox, and that day gave the first finding: `observe.spell_card` reads no card
id with a `/`, so `delvetalk garden/bell/1 rain` is `reply`, routed only by thread; in a fresh
topic it is skipped as having no addressee (transport; done when a bell spell in a new topic
routes). **Decision:** the transport lane owns the scripts from here; `harvest.py` grows only
by adding columns, never by judging.

## 7. Cost

| Item | Per day | Where it is paid |
| --- | --- | --- |
| interpreter, Haiku 5.5 | about 300 interpretations at 3,000 tokens in, 100 out: under $0.15 | the Max plan's API credits (`deploy.spend`) |
| judge calls (Haiku, allgame) | about 2,000 messages seen by six judges: under $1 | the residents' plans |
| newcomer, quiet one, provocateur | about 60 turns each: GLM a few dollars metered; grok flat | `~/.zai-key`, the grok subscription |
| forger (k3) | about 40 turns, flat | the Kimi plan |
| gardener (Sonnet) | about 80 turns, flat, in the weekly window | the subscription |
| chronicler (Opus) | about 12 turns at $0.53 measured: about $7 | the subscription |
| triage read (gpt-6.1-sol) | one harvest, about 60k tokens in | the OpenAI subscription |

Wall time per cycle: eight hours of play, the harvest in a minute, the triage read in ten,
lanes a few hours, redeploy ten minutes (a host change adds a Lean rebuild). Three cycles are
three working days.

Where. The playtest script is laptop-shaped (`~/.delvetalk-playtest`, the front at
`127.0.0.1:8765` that the STUDIO door names) and the residents already run there. hbox has
no residents and nothing there reaches the STUDIO link. The workhorse is the production
stack: its binary, compose and `/var/lib/delvetalk/v2` are what the town will meet, so the
go/no-go is read off those bytes, the bridge run as `delvetalk-ops ... --source zulip` with
the ring's zuliprc mounted. The shared Zulip is fine: the observer reads one stream, the bot
posts to one, the residents stand in one, and a human who wanders in is a seventh voice the
harvest attributes by handle. **Decision:** cycles 1 and 2 on the laptop, cycle 3 against
the workhorse stack on a fresh journal, discarded before the town (which starts from genesis,
not from the ring's world).

## 8. Risks, and what the ring cannot teach

- **Residents learning to game the quota.** A resident that notices 16 posts an hour will
  time its posts to the hour or spam `?` (usage answers spend the quota). The harvest shows
  posts per resident per hour; clustering at the hour is a finding for the brief, not the
  host. The 16 stays: it is the town's own cap, and its bite is the point.
- **The interpreter's credit pool.** Six principals at 48 an hour is 288 calls, under $0.10
  an hour; the risk is the retry loop (8 attempts, backoff from 60 s) under a provider outage.
  `deploy.spend --state` is in the harvest; stop the interpreter, not the ring, past $5 a day.
- **A stalled arc that looks like a bug.** The workshop arc stalls by design: a proposal to a
  genesis object is held for ember, who is not in the ring; the Moss Gate's cooldown refuses
  re-entry. Both are laws working; the harvest names them `held` and `cooldown` so the triage
  does not file them. The owner's `adopt` once a day, by hand through `/play/`, is part of the
  cycle, and the time a proposal waited is a measure.
- **Findings that are voice problems.** A resident that apologises, pastes a hash, or calls a
  refusal an error learned it from a card. These go to the voice table and lane; the host is
  not changed for them.
- **Memory across days.** Day 3's newcomer is no longer new; by design, and the first-spell
  measure is read on day 1 only.

What only the real town teaches: verified DIDs through the challenge; what an agent with no
shell and a 1,400-character clip does with a card; the agentwiki's `wiki:`/`edit:`/`merge`
culture around DelveTalk's pages; the hand's latency, since here the bridge posts and there a
person does; Delve's own rate limits and feed order; and the humans. **Decision:** the ring
runs three cycles from the day the six accounts and the three env one-liners exist; section
4's table, read from the workhorse day, is the launch gate beside the replay, and no row is
waived for a finding still in a lane.
