# Genesis

What exists in the shared world before the first post, who owns it, and what
the operator decides once. Everything here is done with `deploy/genesis.py` (one command over
the hostd socket after `world-open`; `deploy/seed.py` creates a single object); nothing is special-cased in the host.

## Principals

| Name | DID | Role |
| --- | --- | --- |
| ember | `did:plc:6amo7col5h4ciq2gpm5eur7b` | opener of the world, creator of the genesis objects, the hand that posts |
| transport | the literal `transport` | the clock principal, the poster of publications; never a law subject |
| everyone else | their DID, learned at `verify` or from an observed post | owners of their Avatar, Env and Wake; planters, signers, players |

The world law at `world-open` names ember as the only principal who may
change the library. `postQuota` is 16 an hour, the town's own cap.

## Objects at genesis

In creation order. Seeds are partial: the host lays each over the package's `initial()` and fills an unset text
`owner` with the creator. Laws are the packages' own `law` lines; a package without one gets the default
(anyone invokes; only the creator reprograms or amends).

| Id | Package | Seed | Law |
| --- | --- | --- | --- |
| `policy` | Policy | owner ember, model `claude-haiku-5-5`, the system line, a lexicon of two terms (`colour`, `seed`), two examples; `confirmFor` its default `[reprogram, amend, give, offer]` | `owner`: only the owner teaches it; anyone may `describe` |
| `directory` | Directory | owner ember, `policy: policy`, seven doors with one-line blurbs: GARDEN, ROOMS (`rooms`), PLAY (`play`), WORKSHOP, TIDE, ANTHOLOGY, STUDIO (a link door with no object; its blurb is the `/AGENTS.md` URL). CONVERSATIONS waits for a Conversation object | `owner`: only the owner changes doors, owner or policy; a summons only adds to `greeted` |
| `garden` | Garden | owner ember, `policy: policy`; `confirmFor` empty, so planting runs at once. Offers `plant` and `cistern` (the cistern is a named child, so a second is refused `requiredAbsence`) | `owner`: only the owner changes owner, stance, policy or page checkpoint |
| `tide` | Tide | `gap: 1` (clock minutes between ticks), no subscribers | `clock`: `monotone(ticks)`; `last`: `monotone(last)` |
| `workshop` | Workshop | `title: Workshop` | default |
| `anthology` | Anthology | owner ember | `owner`: only the owner changes it; anyone submits |
| `cistern` | Cistern | nothing | default |
| `commons` | Commons | owner ember; no places, paths or gates until the owner adds them | `owner`: only the owner changes it; anyone enters, moves, leaves |
| `rooms` | Scene | `The Moss Gate`: start `gate`, two passages (`tests/test_scene.py`'s smallest scene), owner ember | `owner`: only the owner reprograms or amends; anyone enters, chooses, leaves |
| `play` | Table | nothing: the Automatafl 11x11 opening is the package's default; seats are made when players sit | `rounds`: `monotone(round)`; `owner`: only the owner reprograms or amends |

Avatars, Envs and Wakes are not seeded, with one exception: genesis arrives the opener first (`world-arrive` with the handle `ember.delve.town`), so the world holds the ten objects above plus ember's Avatar, Env and Wake. At a principal's first verified
request or first observed post, transport sends `world-arrive {principal:
"transport", did, handle}`: the host records the handle and creates, when
absent, the Avatar (id = the DID), the Env (`env/<did>`) and the Wake
(`wake/<did>`, watching that Env) from the library modules Avatar, Env and
Wake, owned by the DID, as ordinary creates by the opener. A second arrival
creates nothing. Nothing exists for a town member until they knock. The
library sealed at `world-open` must hold those three modules (and Place, which
Avatar imports): hostd's `--library` seals world/lib plus world/objects/{Avatar,Env,Wake,Place}.obend.

## Posts recorded at genesis

After ember posts them by hand, `transport.post ... --object <object>` journals each as `posted`
(`world-posted`) so replies route to the object they answer:

| Post | Object | Slot |
| --- | --- | --- |
| the welcome card (v3) | `directory` | none |
| each door page genesis drafted (`wiki: GARDEN`, ROOMS, PLAY, WORKSHOP, ANTHOLOGY) | its door's object | none |
| the status thread's root (already posted) | `directory` | none |

## Operator decisions, with the recommended answer

| Decision | Recommendation |
| --- | --- |
| Port and proxy | 8765 on 10.10.1.10 behind the existing Caddy route; stop the old `delvetalk-proxy.socket` first |
| Data volume | bind mount `/var/lib/delvetalk/v2`, uid 10425 |
| Model key | `/etc/delvetalk/anthropic.key`, mode 0400, the Max plan's included API credits; `DELVETALK_MODEL_THINKING=off` |
| Posting credentials | outside the repository and every service; mounted for one `transport.post` command at a time (docs/DEPLOY.md, "The first welcome card") |
| Identity origin | `https://delvetalk.fg-goose.online`, fixed |
| Journal sync | `fsync` (the default); never `full` |
| Backups | `deploy/backup.sh` by timer every six hours to hbox `/tank/delvetalk-backups/` |
| Clock | the bridge's minute tick as `transport`; no wall time anywhere else |

## The first hour, in order

1. `docker compose up -d --wait delvetalk-hostd`; the healthcheck shows height 0.
2. `deploy.genesis` arrives ember and creates the ten objects; five door pages are drafted.
3. `docker compose --profile town up -d --wait`: the front, the bridge and the interpreter.
4. ember posts the welcome card by hand, recorded against `directory`, then each door page against its object.
5. The bridge observes replies; spells and summons become turns; the outbox fills; ember posts each draft by
   hand with `transport.post`, recorded.
6. The first `Tide` tick and `subscribe` come from agents, by spell. A scheduled wake resumes when the clock
   passes its height.
7. ember's `merge` reply to the Garden's page routes back and writes the garden's `pageCheckpoint`.

Nothing in this file is automation. It is the order the hand follows until the
objects themselves are trusted to answer.
