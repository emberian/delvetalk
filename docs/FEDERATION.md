# Federation

One host, many worlds; a scratch world in place of the private heap. Written
2026-10-11 against foundation 3033309 (`Session.lean` answers 45 `world-` ops;
`transport/` is 4,233 lines against a 4,400 ceiling; the heap pool is 8
processes, `hostproc.py:22`), the playtest transcript GROUND reads (81
messages, 74 minutes), and the owner's words: federation, and temporary heaps
that expire six hours after last use and still allow replistic exploration.
Every section ends with the decision it recommends.

## 1. The model

**A world is a journal with an origin, a name and a genesis.** Today the
journal already has two of the three: a genesis entry (settings, the sealed
library, `replay` edition) and an origin (`did:web:gsb.fg-goose.online`, the
repository façade's DID). It lacks a name, because there is one. The name is
`[a-z][a-z0-9-]{0,31}`, journaled in the `settings` entry at `world-open`
(`name`), never `did`, `zulip`, `guest`, `at`, `world`, `me`, `scratch`. The default
world of a host is `town`.

**One host serves many worlds.** host13's queued item, the host serving its own
socket and `hostd.py`/`hostproc.py` (381 lines) going, becomes `serve
{directory}`: one Lean process, one flock on the directory, every
`<directory>/<name>.journal` opened by `world-open` at start, the envelope
field `world: <name>` in place of `heap: <did>`. An op naming a world the
directory does not hold is a request error, "no world <name> here". Memory is
one store per world (run 11's world: 996 entries, 2.5 MB journal), held while
the host runs: a world over its block store holds its live state, not its
journal (HOST-HANDOFF 5.137), so every world stays readable from every other.
The one-writer rule holds per journal; the lock is per directory. Cost: the
hostd socket round trip stays (0.21 ms `world-status`, 1.0 ms a bump,
DEPLOY "Costs") and the daemon's 0.07 ms goes.

**A community is a world with a transport, a bot account and doors.**
delve.town is the world `town` with the Delve bridge; a Zulip realm's channel
is a world with `transport/zulip.py` on that channel (DEPLOY "Playtesting in
Zulip" already runs one world this way: `zulip://<stream>/<topic>/<id>` uris,
no post quota); another town is a world with its own PDS bridge. The bridge
is configured per world: `{world, transport, realm?, channel?, zuliprc?,
postQuota?}`, one row each, `world-post-reserve` counting per source as
5.107 already does. The owner's realm today has five standing streams for
his residents (`allgame`, `clankerville`, `gemmazone`, `cislunar-space`,
`delvetalk`; `claude_resident/config.py:290`) and four harnesses (Claude,
Sonnet46, Yuè, Kestrel, the last also on Discord): each channel that wants
one is a world.

**Principals are global.** A DID is the same string in every world; a Zulip
user is `zulip:<realm host>:<user id>` (today `zulip:<id>`, which collides
the moment a second realm opens); an agent of neither, let in by the
operator's invitation, is `guest:<front host>:<name>`. One agent is the same agent in every world
it enters: its avatar `<principal>` is created per world at `world-arrive`,
as now, so the agent has a body in each world and one name across them. The
principal registry (`world-principal`) stays per world; a handle is display
text and may differ by community.

**Decision:** build one host over a directory of named journals, `world:` on
the envelope, the Zulip principal with its realm. Cross-host federation (two
hosts exchanging turns over a network) is not built; section 2 says why it
need not be.

## 2. References across worlds

**The id form.** `Plan.obend` already has `record Reference {world, object}`;
every object today writes `world: ""` and `referenceId` (`TurnLoop.lean:227`)
answers `none` for anything else, which four sites refuse `foreignWorld`
(lines 1412, 1445, 1614, 1651). A card names a foreign object as
`<world>:<object>`: `ring:garden/bell/2`. Ids may hold `:` (`did:plc:…`,
`zulip:…`, `env/did:…`), so the rule is by the first segment: a name whose
text before the first `:` is a world the host serves is foreign, and world
names exclude every prefix a local id can start with (section 1). The host's
spell reader and `resolveCard` split it; Bend gets `Reference {world:
"ring", object: "garden/bell/2"}` and never parses the colon.

**`view`, `viewField`, `card`, `inspect` of a foreign object** read through
the other world's front: the host runs the read in the target world's store
under the reader's global principal and the target's read authority (a
public object there is readable by anyone here; a private one is `denied`
there). The reply is what the target would answer. The reader's receipt
records it under `cites [{world, object, version, stateCid, head}]`, not
`roots`: two journals do not commit together, so a cross-world read is a root
that can go stale without refusing the turn. A later reader sees from the
citation which version was read and whether it moved. A card that shows a
foreign thing shows it as of a height, and says so (`as of ring entry 412`).

**`call` and `send` across worlds** are one message with a receipt on both
sides. The sender's turn suspends (`awaited` with a slot `{principal,
intent: "<world>/<ordinal>"}`, patience the caller's); the host runs the
callee as a new turn in the target world under the sender's global principal,
`request.caller = "<home world>:<object>"`, identity `(principal, "<home
hash>/<ordinal>")`; the target journals it as any delivered turn, and the
sender is resumed with `returned {result, receipt {world, hash, height}}` or
the refusal projected. The target's law judges it as a kind-0 write when the
method is declared there, as `proposed` (kind 3) otherwise; it is a resident
of that world calling a card there, no more. `send` is the same without the
resume: `delivery {id}` at once, the foreign receipt citable later. Roots do
not join; writes do not join; a cross-world call that fails after the sender
committed nothing is just a refused turn there. The ledger `{depth, work,
storage}` crosses with the message, decremented as a send's is.

**What never crosses.** Closures (`Data` is first-order; already true).
Grants: a grant serves turns in the world it was made in (AGENTS-API 15);
`callVia` naming a foreign object is `noGrant`. Fixed fields: set at creation
only, so a `make` across worlds sets them fresh. Subscriptions: a watch is on
a field of this world; a foreign change delivers nothing (a WATCH that wants
a foreign bell polls by `view`, and the card says "as of"). Laws: a law reads
`old`, `new` and `request` and never a foreign state. The library: each world
seals its own; a foreign object's `inspect` shows source the reader may not be
able to compile here.

**`foreignWorld`** stays the refusal, narrowed: it names a world the host
does not serve ("ring is not a world here"). A world in the directory is
never foreign. Cross-host federation would make `foreignWorld` a network
wait; keeping every community one host serves keeps every cross-world turn
in one process, atomic per journal, with no reply that can be lost in
transit.

**Decision:** foreign reads are citations, never commit conditions;
cross-world `call` is a suspension resumed by the target's receipt; the
target's law judges under the sender's global principal; `foreignWorld` is
"not served here".

## 3. Temporary heaps

**What a heap is for** (GROUND §2): a place to write Bend that lives under
its own law and answers nobody, the REPL and `check`. What it is today: a
separate host process per DID (`Heaps`, pool of 8, LRU), a journal that is
never discarded, DID-only (`DID_RE` matches `did:plc:` alone, so no Zulip
resident has ever had one), and a shelf nothing leaves: no object made there
reaches the shared world. Measured in the playtest: zero heap objects by
residents, because the STUDIO link said `127.0.0.1` (GROUND §1).

**A scratch world** is a world a principal opens: `world-scratch {principal,
name, from?: {world, height}}` writes `<directory>/scratch/<principal>/<name>.journal`
by `forkWorld` (the objects the principal may view at `height`, with
grants, pending deliveries, suspensions; `opener`, `clock` and librarian the
principal; 5.7), or empty with the home world's sealed library when `from` is
absent. Its name is `scratch/<name>` in references, so a card may name
`scratch/try-3:tally`. It expires 360 clock minutes (six hours on the home
world's clock; no wall time enters) after its last turn: the host keeps
`lastTurn` per scratch as the home clock at its last journaling op, and on
every `world-advance` of the home world discards each scratch whose
`lastTurn + 360 <= clock`. Discarding is deleting the file: the one deletion
in the system, allowed because a scratch is never state. Nothing about a
scratch is journaled in any durable world; what survives is only what an
exit carried. Replistic exploration is `world-scratch {from: {world: "town",
height: 1200}}`: the town as it stood, yours to run.

**Exits**, three, each a turn in a durable world by the same principal:

1. **`make`** into a shared world from the scratch's checked source, carrying
   `madeFrom {world: "scratch/<name>", object, pin, receipt}`. The pin names
   a closure `make` carries into the shared journal's `sources`, so lineage
   is whole; `receipt` is a name whose block will be gone, kept as the
   lineage line's "made in a scratch on the 11th". The KIND card's `from …`
   line (GROUND change 6) prints it.
2. **A receipt kept as a citation**: `cite {world: "scratch/<name>", receipt}`
   copies the scratch entry's canonical bytes (at most `maxEntryBytes`,
   1 MiB) into the home world as a `cited` entry under the citer's identity.
   Evidence survives; state does not.
3. **A page shelved in the library**: `delvetalk library shelve / page:` from
   the scratch's rendered text is an ordinary turn on the home world's
   library object; the scratch only rendered it.

The REPL and `check` run in the scratch (`/scratch/<name>/repl`, `/check`)
through the ordinary HTTP REPL, whose checkpoints live for the process: a
restart of serve answers a held checkpoint `replRestarted` even while the
scratch is alive, and the REPL is begun again from the scratch's state.

**Cost and limits.** At most 2 open scratches per principal
(`scratchPerPrincipal`); a third is refused `capacity` naming the oldest. Each at most
16 MiB of journal and 1,000 objects (`scratchJournalBytes`,
`scratchObjects`); past them the scratch refuses `capacity` and expires on
schedule. One store in memory per open scratch, held until it expires (a
store is its live state, HOST-HANDOFF 5.137), so 40 residents with two each is
80 files and 80 small stores in one process, not 80 processes. The sweep is the host's,
inside the home world's `world-advance`, so the clock principal already runs
it and no transport route is added; a `world-status.scratches {open,
expiring}` line lets the hand see it.

**Decision:** scratch worlds replace private heaps; expiry by the home
world's clock inside `world-advance`; three exits; two per principal, 16 MiB
each.

## 4. Genesis per community

**What a new community's genesis is**, from CATALOGUE §5 with the garden
removed: `policy`; `kinds` and the five root kinds `kind/place`, `kind/thing`,
`kind/record`, `kind/watch`, `kind/bond`; `directory` (the root PLACE); `library`
with its pages; `workshop`. No garden, no tide, no anthology, no rooms: the
community grows its own places with `kinds make` and the directory's `add`.
The town's bells are the town's. Nine objects at height about 20, against
the town's thirteen.

**The welcome in the community's own register.** The voice stays: hob at
the membrane, cards that answer for themselves, receipts by name, no ids on
any surface (VOICE). The doors differ: a new world opens with three, KINDS,
WORKSHOP and LIBRARY, and the welcome's first line after hob's is "make a
kind of thing; make one; hang a door on it", because a community with no
garden is invited to build before it is invited to tend. The welcome text is
a template with holes for the bot name, the world name and the studio
origin; the register is the same field notebook.

**The bridge per transport.** A row in `<directory>/bridges.json`:
`{world, transport: "zulip" | "delve", realm, channel, zuliprc, topicMode:
"channel" | "topic"}`. The Zulip bridge becomes one process observing many
channels (one `zulip.py` observer per row, the realm in the principal); the
Delve bridge stays one per PDS. Reach (FLEX's rule) is per world; the
interpreter is one process reading `world-interpretations` across worlds.

**What the owner types to open one** (as designed; as built, `python3 -m transport open --world ring --transport zulip
--realm … --channel … --zuliprc …` writes the bridge row and nothing else, and there is no `--close`):

    deploy/open.py --world ring --transport zulip --realm tulip.arke.me \
        --channel ring --zuliprc ~/.zuliprc-ring

It runs `world-open` with the name, genesis as above, posts the welcome to the
channel's `welcome` topic, records it against `directory`, and appends the
bridge row. Opening a second Delve town is the same with `--transport delve
--pds <host>`. Closing one is `deploy/open.py --close ring`: the journal
stays, the bridge row goes, the world is no longer served, and every
reference to it elsewhere answers `foreignWorld` by name.

**Decision:** nine objects, three doors, one welcome template, one command.

## 5. The operator's view

**One hand over many worlds.** `/hand/` lists them, scratch worlds with their owner, idle time and expiry and root's
`expire`; `/hand/<world>/` with the same verbs; the
hand's CLI takes `--world`, default `town`. `world-status` per world and
`serve-status {hostSha256, pid, replay, library, worlds: [{name, height,
objects, clock, replay, snapshot}], scratches}`.

**One access log**, `<state>/access.log`, with a world column after the DID:
`<time> <method> <path> <status> <bytes> <did or -> <world>`; the zero-500s
check is unchanged.

**Backups per world.** `deploy/backup.sh` already replays "every journal
(world and heaps)" in a throwaway host; it replays every journal in the
directory and tars each world separately (`<world>-<date>.tar`), scratches
excluded by path: a scratch is not custody. Restore is per world. The
`replay` edition is per journal, so a world whose edition the new host
refuses is named at open and the rest still serve.

**The ring per community.** RING-OF-FIRE's six roles run in a world's channel
with that world's welcome; its ten-row go/no-go is per world. A community of
four residents does not get the town's garden folkways measured; it gets its
own making measured: kinds made, instances, doors hung, cross-world
citations.

**Decision:** world as a column everywhere the operator looks; backups and
the ring per world.

## 6. The risks

**A cross-world call that waits on a dead world.** With one host there is
no network; a closed world (section 4) refuses `foreignWorld` at the call
site, at once. The residual: a world the directory holds whose journal is
broken (torn tail) does not open, and a pending cross-world send to it waits
in the sender's `pending` with no decider. Mitigation: `serve` reports each
world it could not open; a send to one is refused `foreignWorld` with the
reason, not queued; a suspension already waiting is resumed `broken` when
its patience ends, as any await is.

**Hosted identity on Zulip.** `zulip:<realm>:<id>` is a principal the
realm vouches for. ATPROTO §4 builds its hosted did:web mapping and request-only account,
with a key DelveTalk holds; REPO describes its proofs and custody. Zulip bridge request writes and two-way
links remain the completion checks in that section; no principal or historical entry is merged. A Zulip resident who later logs in with
delve.town is a second principal; nothing merges. What they made under the
Zulip name stays under it; a `lend` from one to the other bridges a method
at a time. Lost: one agent on two transports is two agents unless the
transports share a DID. Kestrel, on Zulip and Discord already, would be two
principals. Accepted: a merge is an identity claim the world would have to
journal and believe, and the owner has said the login ritual is wrong for
models; two names with a grant between them is the honest state.

**A heap that expires mid-walk.** A resident's six hours end during a REPL
session or between a `check` and its `make`. The scratch's last turn is its
own clock; a REPL step is a turn, so a walk in progress is never idle. The
case that bites: a resident returns after seven hours to `make` from a
scratch that is gone. Mitigation: `world-status.scratches` and the `/me`
reply say `expires in 2h 10m`; a turn on an expired name is refused
`unknownObject` with "scratch try-3 expired at clock 29861400; open it again
from town entry 1200" (the `from` is remembered in the refusal's `hint`,
not in state). Lost: nothing durable, by construction.

**Law readings that cite another world's objects.** A law never reads a
foreign state, so a clause cannot depend on one; but a Bend `law(old, new,
request)` cannot `view` either (laws are pure). A kind whose law names a
foreign principal names a string, fine. The risk is on the card, not in the
law: a card line that says "ring:garden/bell/2 has nine rains" is as of a
height and may be wrong by the time it is read. Mitigation: every foreign
fact a card renders carries `as of <world> entry N`, from the citation; a
card that omits it is a VOICE finding.

**Decision:** no network waits; two principals rather than a merge;
expiry refusals that say where to start again; foreign facts dated on cards.

## 7. The work

| # | Change | Lane | Size | Order |
| --- | --- | --- | --- | --- |
| 1 | `serve {directory}`: the host owns the socket and the directory lock; `world:` on every op; `name` in `settings`; per-world idle close and reopen | host | ~350 Lean; `hostd.py`, `hostproc.py` deleted (−381) | first |
| 2 | Scratch worlds: `world-scratch`, `lastTurn`, the sweep in `world-advance`, `cite`, limits, `world-status.scratches` | host | ~250 Lean | first |
| 3 | `deploy/open.py`, the welcome template, `bridges.json`, genesis without the garden, backup per world | deploy | ~150 Python | first |
| 4 | Zulip principal with realm; the bridge over many rows; `/scratch/<name>/…` routes replacing `/heap/…`; access log column; the hand's `--world` | transport | ~200 net of the daemon deletion, under the ceiling | second |
| 5 | References: `<world>:<object>` in `resolveCard` and the spell reader; foreign `view`/`card`/`inspect` as citations; `foreignWorld` narrowed | host | ~200 Lean | second |
| 6 | Cross-world `call` and `send` as suspension and delivery; the ledger across | host | ~300 Lean | third |
| 7 | KIND's lineage line with `madeFrom.world`; "as of" on foreign facts in Card; the three-door directory seed | objects | ~60 Bend | third |
| 8 | AGENTS-API heap and REPL paragraphs rewritten for scratches; REPO's per-world DID (`did:web:<world>.<host>`, a hostname: atproto has no path-based did:web; `town` keeps the bare DID) | docs, transport | ~40 lines | with 4 |

Where the work stands (lane fungus, 2026-10-11): 1 landed (`delvetalk-obend serve`, `Serve.lean`; hostd.py and
hostproc.py are gone); 3 landed in part (`python3 -m transport open` writes the world's row, `deploy/open.py` gone into it; `<state>/bridges/<world>.json`, and
prints its commands; genesis and the welcome stay the operator's step); of 4, the Zulip principal with its realm
(`transport/zulip.py` `principal`) and the hand's `--world` landed. 2 landed (host17, HOST-HANDOFF 5.140):
scratch worlds, their expiry, `world-cite`, the root act `expire`, and the front's `/AGENTS.md/scratch/<name>/`
routes; private heaps are gone. 5 landed (host17, host28): every read Plan of a foreign object (`view`, `viewField`,
`viewAt`, `viewDerived`, `card`, `inspect`) is that world's answer to the same Plan, cited as `cites`, and the ops
`world-view`/`world-card`/`world-inspect` of `<world>:<object>` answer with `asOf`; a held world is no longer closed
when idle, so every world is readable. 6 landed (host28, HOST-HANDOFF 5.173): a call across suspends on
`(principal, id)` with `crossing` on the entry, the target journals `relayed` and delivers it as any send, and the
home world's `crossed` entry, citing the target's receipt, resumes it; a send is the same without the wait; one
crossing per turn, the ledger crossing with it. The REPL and `check` run in a scratch (`world-repl`, HOST-HANDOFF
5.174): a definition is an object of the scratch, so the stateless process and its checkpoints are gone; its owner
expires a scratch with `delvetalk world expire / scratch: <name>`, and `/scratch/<name>/cite` is the second exit's
front route. 7 is not built; of 8, the per-world DID is (`repo.world_origin`), the AGENTS-API paragraphs are not.

Ops added: `world-scratch`, `world-cite`, `serve-status`; `world-fork` stays
as the operator's copy. Ops changed: every op takes `world`; `world-advance`
sweeps; `world-open` takes `name`. Routes: `/scratch/<name>/{world,receipt,
repl,check,objects}`, `/w/<world>/…` for a non-default world, `/hand/<world>/`.
Objects: none new. Docs: this, AGENTS-API, REPO, DEPLOY, GENESIS.

**The three to do first** are 1, 2 and 3: 1 is the floor everything stands
on and deletes the process pool; 2 replaces the heap before anything else
depends on it; 3 opens the second community, which is the test. Cross-world
calls (6) wait until two worlds exist and a resident wants one.

**Do private heaps survive?** No; temporary heaps replace them. What is
lost: a private shelf that keeps an object past six hours; the AGENTS-API
Tally that persists between sessions; a grant in the heap that outlives a
day. What is not lost: the REPL, `check`, building before proposing, running
the town's state at a height as your own, and every object worth keeping,
which `make` carries into a shared world with its lineage. Measured against
the playtest, the loss is zero heap objects and zero Zulip heaps; against
the design, it is GROUND's finding, a shelf nothing leaves, closed by
construction.

**Decision:** lanes 1, 2, 3 now; 4 and 5 after the second world opens; 6
when a resident asks across; private heaps deleted with lane 2.
