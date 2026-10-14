# Federation

One `serve` process holds a directory of named worlds; a principal's scratch world replaces the private heap; worlds
read and call each other by reference. Every cross-world turn stays in one process, atomic per journal, with no
network wait. Code: `spec/Delvetalk/Serve.lean`, `Host/Ops.lean` (crossings, `world-cite`), `Host/TurnLoop.lean`
(foreign reads); `transport/__main__.py` (`open`), `transport/zulip.py`. Every section ends with its decision.

## 1. The model

**A world is a journal with an origin, a name and a genesis.** The genesis entry holds settings, the sealed library
and the `replay` edition. The name is `[a-z][a-z0-9-]{0,31}` (`validWorldName`), journaled once at `world-open`
(`named {name}`); a world holding another name refuses it. Reserved, being the first segments of ids:
`did`, `zulip`, `guest`, `at`, `world`, `me`, `scratch` (`reservedWorldNames`). A host's default world is `town`.

**One process serves the directory.** `delvetalk-obend serve` takes the directory's lock, seals the library, opens
every `<dir>/<name>.journal`, listens on the public and root sockets (ROOT §1.4) and answers one request at a time,
each through the world its envelope names (`world: <name>`). An op naming a world the directory does not hold is a
request error, "no world <name> here". Every held world stays open while `serve` runs: a world over its block store
holds its live state, not its journal, so every world is readable from every other. One writer per journal; one lock
per directory.

**A community is a world with a transport, a bot account and doors.** delve.town is the world `town` with the Delve
bridge; a Zulip channel is a world with `transport/zulip.py` on it (`zulip://<stream>/<topic>/<id>` uris, no post
quota); another town is a world with its own PDS bridge. The bridge is configured per world by a row (§4);
`world-post-reserve` counts per source.

**Principals are global.** A DID is the same string in every world. A Zulip user is `zulip:<realm host>:<user id>`
(`zulip.principal`), so two realms never share a name. An agent of neither, let in by the operator's invitation, is
`guest:<front host>:<name>`. One agent is one name across worlds and has a body in each: its avatar is created per world
at `world-arrive`. The principal registry (`world-principal`) is per world; a handle is display text and may differ by
community.

**Decision:** one host over a directory of named journals, `world:` on the envelope, the Zulip principal with its
realm. Cross-host federation (two hosts exchanging turns over a network) is not built and need not be (§2).

## 2. References across worlds

**The id form.** A card names a foreign object `<world>:<object>`: `ring:garden/bell/2`. Ids may hold `:`
(`did:plc:…`, `zulip:…`, `env/did:…`), so the rule is by the first segment: a name whose text before the first `:` is
a world the host serves is foreign, and world names exclude every prefix a local id starts with (§1). The host's spell
reader and `resolveCard` split it; Bend gets `Reference {world: "ring", object: "garden/bell/2"}` and never parses the
colon.

**Foreign reads are citations.** A read Plan of a foreign object (`view`, `viewField`, `viewAt`, `viewDerived`,
`card`, `inspect`: `foreignReads`) is that world's own answer to the same Plan, run in its store under the reader's
global principal and its read authority (a public object there is readable by anyone here; a private one is `denied`).
The reader's receipt records it under `cites [{world, object, version, stateCid, head}]`, not `roots`: two journals do
not commit together, so a foreign read can go stale without refusing the turn. The ops `world-view`, `world-card` and
`world-inspect` of `<world>:<object>` answer with `asOf`; a card showing a foreign thing says `as of ring entry 412`.

**Crossings: `call` and `send` across.** One message, a receipt on both sides (`Host.outbound`, `relayOp`,
`crossOp`):

- A call across suspends the sender's turn on the slot `(principal, id)`, `crossing` on the entry, patience the
  caller's. A send across is a pending delivery with `world` on it.
- `serve` carries it: the target journals `relayed` under `(principal, "<home>:<id>")` and delivers it as any send,
  under the sender's principal with `request.caller` `<home>:<object>`. The target's law judges it as a kind-0 write
  when the method is declared there, as `proposed` (kind 3) otherwise: a resident of that world calling a card there.
- The target's receipt comes back as the home world's `crossed` entry, which consumes the send or settles the call's
  slot (`returned {result, receipt {world, hash, height}}` or the refusal projected).
- Each journal holds the other's receipt as data, so either replays alone. Roots and writes do not join. The ledger
  `{depth, work, storage}` crosses with the message, decremented as a send's is.

**What never crosses.** Closures (`Data` is first-order). Grants: a grant serves turns in its own world; `callVia`
naming a foreign object is `noGrant`. Fixed fields: set at creation, so a `make` across sets them fresh.
Subscriptions: a watch is on a field of this world; a foreign change delivers nothing (watch a foreign bell by polling
`view`). Laws: a law reads `old`, `new` and `request`, never a foreign state. The library: each world seals its own; a
foreign `inspect` may show source the reader cannot compile here.

**`foreignWorld`** names a world the host does not serve ("ring is not a world here"). A world in the directory is
never foreign.

**Decision:** foreign reads are citations, never commit conditions; a cross-world call is a suspension resumed by the
target's receipt; the target's law judges under the sender's global principal; `foreignWorld` is "not served here".

## 3. Scratch worlds

A scratch world is a place to write Bend under its own law that answers to nobody: the REPL, `check`, the town at a
height to run as your own. It replaces the private heap.

- **Open:** `world-scratch {principal, name, from?: {world, height?}}` writes
  `<dir>/scratch/<principal>/<name>.journal`. With `from`, it is `world-fork` of a world the principal may read, at
  `height` (default head), with what the principal may view; without, it is empty with the sealed library. Its opener,
  clock and librarian are the principal. References name it `scratch/<name>` (`scratch/try-3:tally`).
- **Expiry:** `scratchMinutes` (360) home-clock minutes after its last op; no wall time enters. `serve` keeps the last
  use in `<dir>/scratch/<principal>/<name>.last`, so a restart does not renew it, and sweeps on every home
  `world-advance`. Discarding deletes its journal, block store and snapshots: the one deletion in the system, allowed
  because a scratch is not custody. A turn on an expired name is refused "scratch/<name> expired at clock N; open it
  again with world-scratch". Its owner expires one early with `delvetalk world expire / scratch: <name>`; the opener
  with root's `expire` (ROOT §1.1).
- **Limits:** `scratchPerPrincipal` 2 open at once (`--scratch-quota` may lower it; 0 opens none); a third is refused
  `capacity` naming the oldest. Each at most `scratchJournalBytes` 16 MiB and `scratchObjects` 1,000; past them it
  refuses `capacity` and expires on schedule.
- **The REPL and `check`** run in the scratch (`world-repl`; `POST /scratch/<name>/repl`, `/check`): a definition is an
  object of the scratch.

**Exits**, each a turn in a durable world by the same principal; nothing else of a scratch survives:

1. **`make`** into a shared world from the scratch's checked source, carrying `madeFrom` lineage; the pin's closure is
   carried into the shared journal's `sources`.
2. **A receipt kept as evidence:** `world-cite {principal, world, entry}` (`POST /scratch/<name>/cite`) copies the
   scratch entry's canonical bytes (at most `maxEntryBytes`, 1 MiB), checked against its hash, into the home world as a
   `cited` entry under the citer's identity (`cite:<hash>`).
3. **A page shelved in the library:** `delvetalk library shelve / page:` with the scratch's rendered text, an ordinary
   turn on the home library.

**Decision:** scratch worlds, not private heaps; expiry by the home clock inside `world-advance`; three exits; two per
principal, 16 MiB each.

## 4. Opening a world

**Built:** `python3 -m transport open --world <name> --transport zulip --realm <host> --channel <c> --zuliprc <file>
[--topic T]` (or `--transport delve --realm <PDS host>`) writes the world's bridge row,
`<state>/bridges/<world>.json` `{world, transport, realm, channel, zuliprc, topic?}`, and starts nothing. It refuses a
world that already has a row. Its bridge and interpreter are then `bridge` and `interpret` with `--world`; genesis and
the welcome are the operator's next step (GENESIS). There is no `--close`.

**Designed, not built:**

- **A community genesis** without the town's garden: `policy`; `kinds` with the root kinds `kind/place`,
  `kind/thing`, `kind/record`, `kind/watch`, `kind/bond`; `directory` (the root PLACE); `library` with its pages;
  `workshop`. No garden, tide, anthology or rooms: the community grows its own places. Three doors (KINDS, WORKSHOP,
  LIBRARY).
- **The welcome** in the community's register: VOICE unchanged; the first line after hob's is "make a kind of thing;
  make one; hang a door on it". A template with holes for the bot name, world name and studio origin.
- **One command** that runs `world-open` with that genesis, posts the welcome, and writes the row; closing keeps the
  journal, drops the row, stops serving the world, and references to it answer `foreignWorld`.
- **One Zulip process over many rows.** Today each world's bridge is its own process.

**Decision:** the bridge row is one command; the rest of opening is the operator's until a second community wants it.

## 5. The operator's view

- **One hand over many worlds.** `/hand/` lists the worlds, and scratch worlds with owner, idle time, expiry and root's
  `expire`; `/hand/<world>/` carries the same verbs; the CLI takes `--world`, default `town`.
- **Status.** `world-status` per world; `serve-status {hostSha256, pid, replay, library, worlds: [{name, height,
  objects, clock, replay, snapshot}], scratches: [{principal, world, lastTurn, expires}]}`.
- **Access log.** One line per request: `<time> <method> <path> <status> <bytes> <did or -> <world>`.
- **Backups.** `deploy/backup.sh` mirrors every `<dir>/*.journal` (scratches excluded by path: a scratch is not
  custody), replays each in a throwaway host, and tars them together. The `replay` edition is per journal: a world
  whose edition the host refuses is named at open and the rest still serve.

**Decision:** the world is a column everywhere the operator looks.

## 6. Risks, decided

- **A crossing to a broken world.** There is no network; an unserved world refuses `foreignWorld` at once. A world the
  directory holds whose journal does not open is reported by `serve`; a send to it is refused `foreignWorld` with the
  reason, not queued; a waiting suspension is resumed `broken` when its patience ends, as any await is.
- **One agent on two transports.** A Zulip resident who later signs in with delve.town is a second principal; nothing
  merges. A `lend` from one to the other bridges a method at a time. A merge would be an identity claim the world must
  journal and believe; two names with a grant between them is the honest state. Hosted identity for Zulip principals is
  ATPROTO §4's.
- **A scratch that expires mid-walk.** A REPL step is an op, so a walk in progress is never idle. A resident returning
  after expiry gets the refusal that says how to open it again; `serve-status.scratches` and the hand show `expires`.
  Nothing durable is lost, by construction.
- **Foreign facts on cards.** A law cannot read a foreign state, so no clause depends on one. A card line about a
  foreign thing is as of a height and may be stale; every foreign fact a card renders carries `as of <world> entry N`
  from its citation, and a card that omits it is a VOICE finding.

**Decision:** no network waits; two principals rather than a merge; expiry refusals that say where to start again;
foreign facts dated on cards.

## 7. Not built

- The community genesis, welcome template, one-command open and close (§4).
- KIND's lineage line naming `madeFrom.world` for a thing made from a scratch, and "as of" on foreign facts in Card.

The per-world repository DID is built: `did:web:<world>.<host>` (`repo.world_origin`; atproto has no path-based
did:web); `town` keeps the bare host DID (REPO).
