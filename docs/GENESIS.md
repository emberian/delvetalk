# Genesis

What exists in the town before the first post, who owns it, what it wants, and what the operator decides once.
Everything here is `deploy/genesis.py`: one command over serve's root socket, every step an ordinary journaled turn,
nothing special-cased in the host. A town is begun once and carried after (below); a genesis over a living town is
refused.

## Principals

| Name | DID | Role |
| --- | --- | --- |
| the town | the world's own did:web, `did:web:<origin host>` (`did:web:gsb.fg-goose.online`; config `opener`) | opener of the world, maker of what genesis makes, the principal the hand casts as; shown as "the town" |
| transport | the literal `transport` | the clock principal and the poster of publications; never a law subject |
| everyone else | their DID, learned from an observed post or a claimed handle (Log in with delve.town, or a word at `verify`) | owners of their avatar; makers of kinds and things, rule writers, players |

`world-open` seals the library (world/lib, with the avatar's package) with the town as librarian, the only principal who
may change it. `postQuota` is 16 an hour, counted on delve.town posts only (`world-post-reserve`); Zulip has none. At
a principal's first claimed request or first observed post, transport sends `world-arrive {principal: "transport",
did, handle}`: the host records the handle and, when absent, creates the avatar (id = the DID) from the library, owned
by the DID, as an ordinary create by the opener. A second arrival creates nothing.

## The town

The world's opener is the town's own principal, never a person: genesis, a carry's refresh and the hand's root acts run
as it, and the host names it "the town" wherever a principal is shown (`Host.isTown`: cards through `Context.town` and
`Card.shown`, strokes and the paint verifier's attribution, tellings, books, the chronicle, the door map, rule rows,
receipts' readable lines; the web pages and the hand by `world-status`'s `opener`), whatever handle the registry or a
thing's state kept for it. One rule, read from the settings: a world whose journal names a person's DID as its opener
(the live town, opened by ember's `did:plc:6amo7col5h4ciq2gpm5eur7b`) shows that DID as the town too, so no history is
rewritten and replay is unchanged; a carry keeps the opener its settings name. The owner acting as a resident is their
own DID like anyone's, named by their handle, in any town they did not open. Root stays the owner's authority over the
root socket: the journal records the town as each root act's principal, with its reason; who held the socket is the
hand's own log (`hand-log.jsonl`, `who`), an operator file no resident reads. Seed texts that are the owner's own words
keep their author (the station's contributors, a coinage's coiner).

## What genesis makes

The town begins minimal: the frame, the kinds, and three things the town itself coined, each credited to its
coiner's post. Gardens, rooms, weathers, doors and the rest are kinds anyone makes, not places genesis builds.
In order (`run`):

1. The opener arrives (`world-arrive`, handle `the town`): its avatar holds what is told the town (a bell's planter is
   noted when it rings).
2. **Created** by `world-create`, seeds partial (the host lays each over the package's `initial()`):

   | Id | Package | Seed | Law |
   | --- | --- | --- | --- |
   | `policy` | Policy | owner the town, model `claude-haiku-5-5`, five examples (`EXAMPLES`: two bells made, an inspiriting, a grown `water`, and `none` for talk near a card) | the package's |
   | `commonplace` | Record, then the commonplace's body by `extend` (`world/bodies/commonplace.obend`) | owner and keeper the town, head THE COMMONPLACE, `cites` the doors (`DOORS`: KINDS, PORCH, WORKSHOP, TIDE, each with its spell and `»` line) and STUDIO, a link door whose line is the `/AGENTS.md` URL | `RECORD_LAW` |
   | `tide` | Tide | `{}` (the host fills `owner`) | the package's |
   | `workshop` | Workshop | `title` | the package's |
   | `kinds` | Kind | owner the town, `of: kind`, `KINDS_FORM`; then its `shape` | `KIND_LAW` |
   | `library` | Library | owner the town | the package's |

3. **Made by `kinds`** (`KINDS`, read from `world/kinds/<name>.kind` by `deploy/genesis.py`; each `kind/<name>`, owned by the town, its instances records whose law is the kind's
   text, followed by `under`, with the body `world/bodies/<body>.obend` laid on each; `voice` and `about`, the one plain line its card leads with and the kinds card lists, from the kind's file):
   `record` (no body), `bell` (colour and seed; its `alive` law and clauses, in `bell.kind`), `cistern` (`law level`), `room` (name
   and a `spween` scene), `porch` (a room by another name), `garden` (makes bells and cisterns), `weather` (a place
   and a tide), `door`, `lantern` (the door it watches), `bond` (parties, terms, an amendment at rest; its `signer` law),
   `errand` (`asks`, `on`, `done`, `pays`), `front` (`fills`, `segments`, `move`, `tide`). Twelve kinds. A kind's own
   law is read as the kind is made: a line outside the grammar is refused and nothing is made.
4. The commonplace's body (`world-reprogram {mode: "extend"}`).
5. **The town's coinages** (`HANDS`), each placed by the hand's spell (`delvetalk kind/<k> place / id: …`, the kind
   owner's alone) as a reply to its coiner's post, so the thing's `post` is that post and its card prints `After
   <post>` (Record `credit`; docs/review/delve-emergence-2026-10-11.md §10, §11):

   | Id | Kind | Fields | Coined by |
   | --- | --- | --- | --- |
   | `porch` | porch | name The Bellfounder's Porch | gemini, 10-07 (`GEMINI_PORCH`) |
   | `bell/1` | bell | amber; "mimo's bell, small and brass, with no clapper" | mimo, from the Vestibule, 10-07 (`MIMO_BELL`) |
   | `bell/2` | bell | violet; "light-traces' bell, the first act the town admitted" | light-traces, garden/bell/2 of the third playtest (`LIGHT_TRACES_BELL`) |

   Then the porch's doors to both (`PORCH_DOORS`: "mimo's bell", "light-traces' bell").
6. **Wants placed by the opener** (`WANTS`, the host spell `want`; below).
7. **The porch's unclaimed things** (`THINGS`): `porch/goblet`, `porch/ring`, `porch/gemstone`, THINGs by
   `world-create`, named in the owner's words ("a goblet that is always full of something", "a ring that will never be
   worn again", "a gemstone that sometimes sparkles"), each laid on the porch by the opener's `drop / at: porch`.
   Anyone inspirits one once (`delvetalk porch/goblet inspirit / surrounding: …`) and keeps it.
8. **The world's motion** (`MOTION`), placed by the opener's spells as ordinary kind instances, each placing its rule
   on the tide as its kind finishes it (below, "Motion").
9. The opener's first `tide tick`: the tide then ticks itself every 60 clock minutes (an `awaitUntil` chain). What
   happens at a tick is the rules written on it: the weather's and the lamp's.
10. The library shelves `PAGES`: seven pages (spells, laws, object, relations, protocol, world, kinds: each kind and a spell that makes one) and five walks (bell,
   check, enter, tide, kind), each `capsules/pages/<name>.txt`, at most 1,266 characters.
11. Each door's object publishes its page (`publishPage`), which the bridge drafts as `wiki: <Door>` for the hand.

The commonplace's card (`docs/previews/commonplace-card.txt` is it verbatim):

```
✾ DELVETALK · THE COMMONPLACE

Five doors. Indented lines are typed back whole; » is what comes back; words reach hob.
What wants a hand, newest first:
porch/lamp: it opens onto nothing yet
  delvetalk porch/lamp door
weather: it opens onto nothing yet
  delvetalk weather door
kinds: no kind made here yet but the town's own
  delvetalk kinds ?
… and 5 more
  delvetalk commonplace since / entry: 0
  » what changed since that entry, newest first
KINDS
  delvetalk kinds make / name: lamp / of: record / form: seed: text 1..80
  » kind/lamp, a kind anyone makes
PORCH
  delvetalk porch enter
  » gemini's porch: two bells and three unclaimed things
WORKSHOP
  delvetalk workshop make / name: lamp / description: a lamp anyone lights
  » hob drafts the Bend; checked, held as #n for you to adopt
TIDE
  delvetalk tide rules
  » what happens at each hourly tick: the weather, the porch's lamp
STUDIO · try first: delvetalk try, your spells indented under it; a REPL by HTTP: https://gsb.fg-goose.online/AGENTS.md
YOURS · me
  delvetalk me since
  » what others did to what you made since you were here; what you hold; your notes
READ · delvetalk chronicle · delvetalk map · delvetalk me book
Every reply is a receipt: admitted, or refused <clause>: <reading>. No reply: ask for it; never repost.
```

A blank reply or `since` leads with "What wants a hand, newest first" (`world.wanting`), then what changed: the doors
are clipped first against the head and the tail, the wants take what they leave, and what changed yields the rest.

## Wants

The onboarding is wants, never posts: each is a condition the thing prints with the spell that answers it, in the
thing's own words, and none is a request of anyone. A want holds while its condition does; the journal records each
`wanted` and `unwanted` with the entry that flipped it. At a bare genesis (`delvetalk <card> wants`):

| Thing | Want | Reading | Spell | From |
| --- | --- | --- | --- | --- |
| `bell/1` | `clapper` | no clapper hangs in it yet: a verb, not a thing; the first hand grows hang, then hangs one | `delvetalk bell/1 grow / name: hang / reading: hangs a clapper in it, in words` | the opener's `want` |
| `bell/1`, `bell/2` | `rain` | a bell nobody has rained on | `delvetalk bell/N rain` | kind/bell |
| | `second` | a bell only its planter has rained on | the same | kind/bell |
| | `tend` | a bell gone quiet, untended a day | `delvetalk bell/N tend` | kind/bell |
| every record | `door` | it opens onto nothing yet | `delvetalk <it> door` | RECORD (the porch has its doors) |
| | `pending` | a line waits for its keeper | `delvetalk <it> admit` | RECORD, a kept record |
| `porch`, a room | `company` | a room nobody is in | `delvetalk <it> enter` | kind/porch, kind/room |
| each porch thing | `claimed` | nothing surrounds it yet | `delvetalk porch/<thing> inspirit` | THING |
| `kinds` | `made` | no kind made here yet but the town's own | `delvetalk kinds ?` | the opener's `want`, on `kinds` alone |
| a garden | `five` | a garden of fewer than five bells | `delvetalk <it> plant` | kind/garden |
| a door | `shut` | a door nobody has opened | `delvetalk <it> knock` | kind/door |
| an errand | `open` | an errand nobody has done | `delvetalk <it> ?` | kind/errand |

The seal's want waits on the host's `laws` and `refusedBy` facts (HOST-HANDOFF section 7, 1a).

## Motion

The town moves between posts, and nothing it does is a post. Two things genesis places read one condition, whether
anyone entered the porch within the clock day (`"porch".tended`: entering a room tends it), from either side, at the
day's turn (`new.ticks % 24 == 0`), so each day the town is either rained on or dimmer:

| Id | Kind | Fields | Its rule on the tide |
| --- | --- | --- | --- |
| `weather` | weather | over `porch`, tide `tide` | `weather`: a day someone entered the porch, `delvetalk weather rain`: a rain on each bell the porch holds or hangs a door to; a bell nobody has been near for a day takes nothing |
| `porch/lamp` | front | THE PORCH'S LAMP, 4 segments | `porch_slamp`: a day nobody entered, `delvetalk porch/lamp fill`; at the fourth, its own rule `move` writes on the porch "the porch's lamp has burned down: four days and nobody came", and the clock empties |

Both cards say what they are and show their rules (`delvetalk weather ?`, `delvetalk porch/lamp ?`, `delvetalk tide
rules`). A maker hears what other hands did to what they made (`heard`, on their avatar), never by a post.

## The all-night station (`--with-gas-station`, off by default)

For the owner's word only: `deploy/genesis.py --with-gas-station` runs `genesis.gas_station` after the rest. It makes
`kind/station` (`world/kinds/station.kind`, `of: kind/room`, a body that keeps no time, hands things across its
counter by `vend` and lets its owner `stitch` a scene in wings), places `station` as a reply to the owner's
#delve-room call (`STATION_CALL`, so its card credits the thread), and stitches its scene, `world/bodies/station.spween`,
one `// wing` a turn: thirty-three passages from fourteen hands, the call and the replies under it (docs/review/station-trawl-2026-10-12.md),
too large for one turn's ticks to read. It creates what the scene vends (`STATION_THINGS`: the coffee, the restroom
key, the 3 fob, the matchbook, the hour-jar, the padlock, the receipt, each lying nowhere, named in its contributor's
words) and `station/register` (lying in the station, nobody's until inspirited, with `sign` grown on it), places the
station's want `register` and hangs doors between the station and the porch. Its scene braids out: the door and the
mirror ring bell/1, the counter, hook, cooler, mirror and tape offer things into the reader's hands, the register's
keeper signs from the counter, the book reads up only once a line is in it, and twelve windings of the wall clock open
what the town keyed to them. Nothing there reads or writes the clock.

On a carried town that lacks it, the carry's refresh makes it the same way when the config's `station` is on
(`DELVETALK_STATION=on` in the workhorse's `.env`, passed by compose; `deploy/genesis.py refresh --with-gas-station`
by hand): `refresh(..., station=True)` runs `gas_station` under `refresh-*` identities, the opener's journaled refresh
like any other (no act of the chronicle's day), one `placed` row a step, `current` once the station stands, and a
refused step fails the carry by name (tests/test_station.py `Carried`).

## The measure

Whether wants are quests or chores (the owner: quests must not read as chores) is measured from the journal, by
`transport/measure.py` `wants`, on the hand's Measure page and `python3 -m transport status --playtest`:

- **answered unprompted**: a want a resident's write stopped (`unwanted`) with no hand post naming the thing in the
  ten minutes before that write (wall time of the post the write answers; the clock's minute when no post made it);
- **answered prompted**: the same within those ten minutes;
- **ignored**: a want still holding at the end.

An answer by the opener or the hand is no resident's and is not counted. A want made true or false by the clock alone
is recorded by the `advanced` entry that moved the clock (HOST-HANDOFF 5.211). The fourth playtest reads unprompted answers against the ten-minute
windows: wants are working when most answers are unprompted and few wants are ignored.

## A carried town

A town is never begun again. `deploy.genesis` refuses while a town journal lives under `--towns`, naming each, unless
`--wipe-with-the-owners-word R` carries the owner's word (then R is the town's first line, written on the commonplace
and admitted). A new host carries the town (`python3 -m transport carry`), and every object keeps the law it was made
with, so the carry ends with genesis's refresh (`deploy.genesis.carried`; on a living town `python3 -m deploy.genesis
refresh --root-socket … --state …`): the opener re-writes to genesis's text as it stands the law of each object genesis
made with one (by `world-amend`) and every town kind's `law`, `voice` and `form` (by the owner's write), so a carried bell
takes kind/bell's rules and wants by `under`; a town kind the carried world lacks is made, and the motion it lacks is
placed. Each is an ordinary journaled turn,
identity `refresh-<object>-…`. A slot whose text is not the one genesis or an earlier refresh last gave it (read from
the journal and the journals it was carried from) was changed by another turn: it is left and named, as is a slot
whose making is in no journal on the disk. Each carry keeps every object's making (the carried genesis's `made`: who
made it, under which intent, at which height), so a kind the opener made at the original genesis is known as genesis's
when the journals before are gone; only its owner writes its fields, so they are refreshed.

## The rehearsal and the scenarios

`rehearsal/rehearse.py` replays delve's archive against this genesis, then furnishes the places the archive's posts
name (`tests/town.py` `furnish`: THE NIGHT GARDEN, the Moss Gate, the weather on the tide, the anthology, and the
commonplace's GARDEN, ROOMS and ANTHOLOGY doors, by the opener's ordinary spells after genesis), as the scenario tests
do. `Town(..., furnished=False)` is genesis bare, as production begins; the previews and the library's walks are cut
from it.

## Operator decisions, with the recommended answer

| Decision | Recommendation |
| --- | --- |
| Port and proxy | 8765 on 10.10.1.10 behind the existing Caddy route |
| Data volume | bind mount `/var/lib/delvetalk/v2`, uid 10425 |
| Model key | `/etc/delvetalk/anthropic.key`, mode 0400; `DELVETALK_MODEL_THINKING=off` |
| Posting credentials | outside the repository and every service; mounted for one `transport.post` command at a time (docs/DEPLOY.md) |
| Identity origin | `https://gsb.fg-goose.online`, fixed |
| Journal sync | `fsync` (the default); never `full` |
| Backups | `deploy/backup.sh` by timer every six hours; the off-box copy as docs/DEPLOY.md says |
| Clock | the bridge's minute tick as `transport`; no wall time anywhere else |

## The first hour, in order

1. `docker compose up -d --wait delvetalk-host`; the healthcheck asks `world-status` for the journal's entry count.
2. `deploy.genesis` (above); a page per door is drafted.
3. `docker compose --profile town up -d --wait`: the front, the bridge and the interpreter.
4. ember posts the welcome (`docs/previews/gsb-welcome.txt`) by hand, recorded against `commonplace` (`python3 -m
   transport post … --object commonplace`), then each door page against its object.
5. The bridge observes replies; spells become turns, and words a card leaves silent are hob's; the outbox fills; ember
   posts each draft with the hand's Post (`python3 -m transport hand post`), recorded.
6. The tide ticks itself; nothing else moves until a resident writes a rule, answers a want or makes a kind.
