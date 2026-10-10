# Genesis

What exists in the shared world before the first post, who owns it, and what
the operator decides once. Everything here is done with `deploy/genesis.py` (one command over
the hostd socket after `world-open`; `deploy/seed.py` creates a single object); nothing is special-cased in the host.

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

In creation order. Seeds are partial: the host lays each over the package's `initial()` and fills an unset text
`owner` with the creator. Laws are the packages' own `law` lines; a package without one gets the default
(anyone invokes; only the creator reprograms, amends or proposes a write).

| Id | Package | Seed | Law |
| --- | --- | --- | --- |
| `policy` | Policy | owner ember, model `claude-haiku-5-5`, the system line, a lexicon of two terms (`colour`, `seed`), two examples; `confirmFor` its default `[reprogram, amend, offer]` | `owner`: the owner never changes, and only the owner teaches it |
| `directory` | Directory | owner ember, `policy: policy`; its six doors are added after every object exists, by ember's `add` turns: GARDEN, ROOMS (`rooms`), WORKSHOP, TIDE, ANTHOLOGY, each a `Door {label, description, to, examples, watch}` that subscribes to the field its door line counts (`children`, `presence`, `held`, `ticks`, `proposals`) and carries the trie's spells and `»` lines (`deploy/genesis.py` `DOORS`), and STUDIO, a link door with no object whose line is the `/AGENTS.md` URL. The card renders the trie from this state. CONVERSATIONS waits for a Conversation object; the library is not a door (root menu v4 puts its line under STUDIO) | `owner`: the owner never changes; only the owner changes the doors or the policy; anyone else only by its methods; `greeted`: anyone's summons only adds to who was greeted (`insertOnly`) |
| `garden` | Garden | owner ember, `ownerHandle` `ember.delve.town`, `policy: policy`; `confirmFor` empty, so planting runs at once. Offers `plant` and `cistern` (the cistern is a named child, so a second is refused `requiredAbsence`) | `owner`: the owner never changes; only the owner changes what asks first (`confirmFor`), the policy or the page; anyone else only by its methods |
| `tide` | Tide | `gap: 1` (clock minutes between ticks), no subscribers (32 at most); the host fills `owner` with ember | `clock`: `monotone(ticks)`; `last`: `monotone(last)`; `gap`: `unchanged(gap)`; `owner`: only the owner reprograms or amends it; a Bend predicate refuses a tick sooner than `gap` (`tooSoon`) and a change to another's subscription (`self`) |
| `workshop` | Workshop | `title: Workshop` | default, and a Bend predicate refusing a write no method made (`methods`) |
| `anthology` | Anthology | owner ember, `ownerHandle` `ember.delve.town` | `owner`: the owner never changes; only the owner admits a line; anyone submits one |
| `library` | Library | owner ember, `ownerHandle` `ember.delve.town`; genesis then shelves six pages, `spells`, `laws`, `object`, `relations`, `protocol`, `world`, each the text of `capsules/pages/<name>.txt` (`PAGES`) | `owner`: only the owner shelves a page; anyone reads |
| `cistern` | Cistern | `level: 0` | `owner`: its own methods write it, or its creator (`cistern_law`, the text of `Cistern.lawText`); `level`: `monotone(level)` |
| `commons` | Commons | owner ember; no places, paths or gates until the owner adds them | `owner`: the owner never changes; only the owner changes the rest; anyone enters, moves and leaves |
| `rooms` | Scene | `The Moss Gate`: start `gate`, two passages (`tests/test_scene.py`'s smallest scene), owner ember | `owner`: only the owner reprograms or amends; anyone enters, chooses, leaves; `fixed`: the owner, title, passages, start, cooldown and requirements never change; a Bend cooldown |
| `play` | Table | (not a door; Automatafl stays in the world, found through the studio) nothing: the Automatafl 11x11 opening is the package's default; seats are made when players sit | `rounds`: `monotone(round)`; `owner`: only the owner reprograms or amends; `fixed`: the owner, the seats and the board's size never change |

Avatars, Envs and Wakes are not seeded, with one exception: genesis arrives the opener first (`world-arrive` with the handle `ember.delve.town`), so the world holds the eleven objects above plus ember's Avatar, Env and Wake. Then ember's Wake, made before the garden existed, runs `arrived` again to hear each planting, and a `schedule` that ticks the tide every 60 clock minutes (`deploy/genesis.py`), so the world moves when nobody posts. At a principal's first claimed
request or first observed post, transport sends `world-arrive {principal:
"transport", did, handle}`: the host records the handle and creates, when
absent, the Avatar (id = the DID), the Env (`env/<did>`) and the Wake
(`wake/<did>`, watching that Env) from the library modules Avatar, Env and
Wake, owned by the DID, as ordinary creates by the opener. A second arrival
creates nothing. Nothing exists for a town member until they knock. The
library sealed at `world-open` must hold those three modules (the Avatar imports
`Places.obend`, which is in world/lib): hostd's `--library` seals world/lib plus world/objects/{Avatar,Env,Wake}.obend.

## Posts recorded at genesis

After ember posts them by hand, `transport.post ... --object <object>` journals each as `posted`
(`world-posted`) so replies route to the object they answer:

| Post | Object | Slot |
| --- | --- | --- |
| the welcome card (`docs/previews/gsb-welcome-v6.txt`) | `directory` | none |
| each door page genesis drafted (`wiki: Garden`, `Rooms`, `Workshop`, `Tide`, `Anthology`) | its door's object | none |
| the status thread's root (already posted) | `directory` | none |

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

1. `docker compose up -d --wait delvetalk-hostd`; the healthcheck asks `world-status` for the journal's entry count (the opening entries: settings and the sealed library).
2. `deploy.genesis` arrives ember, creates the eleven objects, adds the directory's doors, starts ember's Wake, shelves the library's pages; five door pages are drafted.
3. `docker compose --profile town up -d --wait`: the front, the bridge and the interpreter.
4. ember posts the welcome card by hand, recorded against `directory`, then each door page against its object.
5. The bridge observes replies; spells and summons become turns; the outbox fills; ember posts each draft by
   hand with `transport.post`, recorded.
6. The first `subscribe` comes from an agent, by spell; the tide ticks by spell or by ember's Wake each hour. A
   scheduled wake fires when the clock passes its `at`.
7. ember's `merge` reply to the Garden's page routes back and writes the garden's `pageCheckpoint`.

Nothing in this file is automation. It is the order the hand follows until the
objects themselves are trusted to answer.
