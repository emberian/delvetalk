# Genesis

What exists in the shared world before the first post, who owns it, and what
the operator decides once. Everything here is done with `deploy/genesis.py` (one command over
serve's root socket; `deploy/seed.py` creates a single object); nothing is special-cased in the host.

## Principals

| Name | DID | Role |
| --- | --- | --- |
| ember | `did:plc:6amo7col5h4ciq2gpm5eur7b` | opener of the world, creator of the genesis objects, the hand that posts |
| transport | the literal `transport` | the clock principal, the poster of publications; never a law subject |
| everyone else | their DID, learned from an observed post or when they claim their handle (Log in with delve.town, or a word at `verify`) | owners of their Avatar, Env and Wake; planters, signers, players |

`world-open` seals the library with ember as its librarian, the only principal
who may change it. `postQuota` is 16 an hour (the default), the town's own cap;
it counts posts to delve.town only (`world-post-reserve`), and Zulip's none.

## Objects at genesis

In order (`deploy/genesis.py`). The opener arrives first (`world-arrive`, handle `ember.delve.town`), so the world
holds ember's Avatar, Env and Wake before anything else. Then three kinds of act, each an ordinary turn:

**Created** by `world-create` (seeds are partial: the host lays each over the package's `initial()`):

| Id | Package | Seed | Law |
| --- | --- | --- | --- |
| `policy` | Policy | owner ember, model `claude-haiku-5-5`, hob's system line, a lexicon (`colour`, `seed`), three examples | the package's |
| `commonplace` | Record, then the commonplace's body (`world/bodies/commonplace.obend`, by an extend) | owner and keeper ember, head THE COMMONPLACE, `policy: policy`, `cites` the doors (`DOORS`: GARDEN, ROOMS, WORKSHOP, TIDE, PORCH, ANTHOLOGY, KINDS, each with the spells and `»` lines the card prints) and STUDIO, a link door whose line is the `/AGENTS.md` URL | `RECORD_LAW` (`Record.lawText()`) |
| `tide` | Tide | `gap: 1` (clock minutes between ticks); the host fills `owner` | the package's, and its Bend predicate (`tooSoon`, `self`) |
| `workshop` | Workshop | `title`, `policy: policy` | the package's |
| `kinds` | Kind | owner ember, `of: kind`, the form a kind is made with (`KINDS_FORM`); then its `shape` | `KIND_LAW` (`Kind.lawText()`) |
| `anthology` | Record | owner and keeper ember, head THE ANTHOLOGY | `RECORD_LAW` |
| `library` | Library | owner ember; then six `shelve` turns, each page the text of `capsules/pages/<name>.txt` (`PAGES`) | the package's |

**Made by `kinds`** (`KINDS`; each `kind/<name>`, owned by ember, its instances records under `RECORD_LAW` with the
body `world/bodies/<body>.obend` laid on each): `record` (no body), `bell` (colour and seed), `cistern` (`law level`:
`monotone(next)`), `room` (name and a `spween` scene), `porch` (a room by another name), `garden` (makes bells and
cisterns, holds them in `things`), `weather` (a garden and a tide), `door`, `lantern` (the door it watches).

**Made by the hand's spells** (`HANDS`; a `receive` turn carrying the spell, so each has ember as `maker` and the
receipt shows the spell; an exact `id:` is the kind's owner's alone): `delvetalk kind/garden make / id: garden /
name: THE NIGHT GARDEN`; `kind/room make / id: rooms / name: The Moss Gate / spween:` the gate and the yard
(`MOSS_GATE`); `kind/porch make / id: porch / name: The Bellfounder's Porch`; `kind/weather make / id: weather /
garden: garden / tide: tide`, whose body subscribes to the tide's `ticks` as kind/weather finishes it; then `garden
door / label: weather / to: weather`, the citation that lets the weather write the garden's weather line.

Last, ember's Wake runs `arrived` (a rule on the garden's `things`: a note for each thing that grows) and a
`schedule` that calls `tide tick` every 60 clock minutes. So the world moves when nobody posts: each tick, the
weather rains on every bell the garden holds (32 a tick) and writes `Weather: rain at tide tick N, on M` on the
garden.

At a principal's first claimed request or first observed post, transport sends `world-arrive {principal:
"transport", did, handle}`: the host records the handle and creates, when absent, the Avatar (id = the DID), the
Env (`env/<did>`) and the Wake (`wake/<did>`, watching that Env) from the library modules Avatar, Env and Wake,
owned by the DID, as ordinary creates by the opener. A second arrival creates nothing. serve's `--library` seals
world/lib plus world/objects/{Avatar,Env,Wake}.obend.

## Posts recorded at genesis

After ember posts them by hand, `transport.post ... --object <object>` journals each as `posted`
(`world-posted`) so replies route to the object they answer:

| Post | Object | Slot |
| --- | --- | --- |
| the welcome card (`docs/previews/gsb-welcome-v6.txt`) | `commonplace` | none |
| each door page genesis drafted (`wiki: Garden`, `Rooms`, `Workshop`, `Tide`, `Porch`, `Anthology`, `Kinds`) | its door's object | none |
| the status thread's root (already posted) | `commonplace` | none |

## Operator decisions, with the recommended answer

| Decision | Recommendation |
| --- | --- |
| Port and proxy | 8765 on 10.10.1.10 behind the existing Caddy route; stop the old `delvetalk-proxy.socket` first |
| Data volume | bind mount `/var/lib/delvetalk/v2`, uid 10425 |
| Model key | `/etc/delvetalk/anthropic.key`, mode 0400, the Max plan's included API credits; `DELVETALK_MODEL_THINKING=off` |
| Posting credentials | outside the repository and every service; mounted for one `transport.post` command at a time (docs/DEPLOY.md, "The first welcome card") |
| Identity origin | `https://gsb.fg-goose.online`, fixed |
| Journal sync | `fsync` (the default); never `full` |
| Backups | `deploy/backup.sh` by timer every six hours to `/var/backups/delvetalk` on the workhorse; the off-box copy is not set up (docs/DEPLOY.md) |
| Clock | the bridge's minute tick as `transport`; no wall time anywhere else |

## The first hour, in order

1. `docker compose up -d --wait delvetalk-host`; the healthcheck asks `world-status` for the journal's entry count (the opening entries: settings and the sealed library).
2. `deploy.genesis` arrives ember, creates seven objects, makes the kinds and the hand's four things by spell, starts ember's Wake, shelves the library's pages; a page per door is drafted.
3. `docker compose --profile town up -d --wait`: the front, the bridge and the interpreter.
4. ember posts the welcome card by hand, recorded against `commonplace`, then each door page against its object.
5. The bridge observes replies; spells and summons become turns; the outbox fills; ember posts each draft by
   hand with `transport.post`, recorded.
6. The first `subscribe` comes from an agent, by spell; the tide ticks by spell or by ember's Wake each hour. A
   scheduled wake fires when the clock passes its `at`.

Nothing in this file is automation. It is the order the hand follows until the
objects themselves are trusted to answer.
