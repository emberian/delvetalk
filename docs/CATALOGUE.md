# Catalogue

Which objects DelveTalk offers, how they compose, and what a resident makes from them. GENESIS is the order genesis
makes them in, OBJECTS-HANDOFF how a card speaks and what is open, METAPHYSICS §5 and §7 why there are three packages
of thing.

## 1. Inventory

**Packages** (`world/objects/`), each sealed into the library at `world-open`:

| Package | Carries | Its own spells | Made |
| --- | --- | --- | --- |
| Record | lines keyed `{author, n}` with a `verb` column (the newest 128 kept; `next` counts every line; `marks` are never dropped), admissions, a keeper, marks, variables, doors (`cites`), the made header and its `credit`, a scene for rooms, things lying in it, `tended` | `write`, `admit`, `lines`, `tend`, `door`, `undoor`, `repair`; `act` for grown verbs | by a kind's `make`, or `world-create` |
| Thing | custody, holder, keeper, circle, copyable; offer and accept; a description that is its keeper's inspiriting | `acquire`, `drop / at`, `offer`, `withdraw`, `inspirit`, `copy`; lenses `name`, `description`, `copyable`, `circle`; want `claimed` | `world-create` only (a kind makes records) |
| Kind | form, head, voice, about, law (the text its things follow by `under`), body, `made`, `count` | `make`; `place / id:` (the owner's); `shape`, `reshape`, `repair` | `kinds make` |
| Avatar | `at`, `holding`, `inbox` (rule notes, tide notes, mentions), `heard`, `seen` | `go`, `move`, `note`, `accept`, `seen`, `since` | at a principal's arrival, id = the DID |
| Tide | `ticks`, `last`, `gap`; ticks itself by an `awaitUntil` chain | `tick` (its own; a hand's is `refused itself`) | genesis |
| Workshop | proposals held for a target's owner (twelve, oldest dropped) | `check`, `propose`, `adopt`, `withdraw`, `draft`, `make` (hob drafts), `create / like` | genesis |
| Library | pages and walks (docs/LIBRARY.md) | `read`, `laws`, `shelve`, `unshelve` | genesis |
| Policy | `model`, `examples`, `confirmFor`; hob's prompt | `confirm` | genesis, the world's one |
| Mending | reports, their status and answers (docs/MENDING.md) | `report`, `confide`, `read`, `mine`, `answer` | genesis: `mending` and its drawer |

**Kinds and bodies.** A kind is `world/kinds/<name>.kind` (`of`, `form`, `head`, `voice`, `about`, `text`, `body`);
its body is `world/bodies/<body>.obend`, a layer over Record laid on each thing it makes. Every body also takes
`write`, `lines`, `door` and `undoor` unless noted.

| Kind | Of | Verbs | Its rules, wants and laws |
| --- | --- | --- | --- |
| record | record | (Record's) | none |
| bell | record | `rain`, `ring`, `tend` | law `alive`; rules `seven`, `rang`; wants `rain`, `second`, `tend` |
| garden | record | `plant`, `dig` (bells and cisterns under itself), `chime` | want `five` |
| room, porch | record | `enter`, `choose`, `leave`, `say`, `emote`, `whisper`, `chime`, `rescene`; a ```spween block makes a room under it | want `company` |
| weather | record | `rain`, `drizzle`, by its rule alone; `arm` | places a rule on its tide at `made`; want `stranded` |
| door | record | `knock` (the first opens it) | want `shut` |
| lantern | record | `light`, by its rule alone; `arm` | places a rule on its door at `made` |
| cistern | record | `pour` | law `level` |
| bond | record | `countersign`, `withdraw`; at rest amends `amends` to `law` (empty: no amendment) | law `signer` |
| errand | record | `settle`, by its rule alone; `arm`, `repay` (the maker's) | a rule on `on` that settles it for the doer; `settle` marks `done` (never dropped), takes that rule off and places `pay`, which casts `pays` with `{request.subject}` as the doer at that write; `repay` fires it again for the same hand |
| front | record | `fill`, by its rule alone; `arm` | a rule on its tide and one on itself (cast `move` when whole); want `stranded` |
| counter, hexboard | record | `plus`, `minus`; `place / cell:` | drawn live on their pages (docs/VIEWS.md) |
| station | room | `vend`, `stitch`, `restitch` (the owner's, a scene in wings) | keeps no time |
| parlour | station | (the station's) | its planchette read into its scene |
| inhabitant | record | `haunt`, `arm` | rule `haunts`; want `stranded`; acts as itself, `@<id>` |
| regular, dj, bee, planchette | inhabitant | `nod`, `ask`, `come`, `go`; `request`, `call`, `play`, `between`; `name`, `fly`; `nudge`, `lift`, `move`, `drift` | dj rule `enough`; planchette rule `agreed` |
| register | record | `ask`, `voice`, `failed`, `snag`, `dispute`, `recheck`, `resolve`, `trail`, `more`, `unchecked`, `scrape`, `rounds`, `ring`, `witness`, `seal`, `next`, `volume`, `rotate` | laws `sealed`, `unkept`, `whole`, `authored`, `pen`, `scribe`, `close`, `clerk`; want `check` |

The commonplace's body (`world/bodies/commonplace.obend`, no kind) takes `since`, `write`, `admit`, `decline`,
`lines`, `door`, `undoor`. `kind/register` is created whole by genesis, not made by `kinds`, so the kinds card neither
lists nor counts it. Genesis makes the first twelve kinds (`KIND_NAMES`); station, parlour, the inhabitants, counter
and hexboard come with the station or an open town (docs/GENESIS.md).

**Libraries** (`world/lib/`): Card (the card protocol, `answer`, `tell`, `refusing`, clipping), World (every world
call, the placing arms `rule`, `want`, `grow`, `act` among them, `changed`), Plan, Relation, Rows, Form, Forms, Text,
Menu (the door trie), Paint (the paint's contract), Harmony (a colour's tone, docs/HARMONIC.md), View (drawn views),
Spell, Scenes and Spween (the scene body), Policies, and `prelude/` Abi, List, `document/` Document.
`tests/fixtures/objects/` keeps Bell, Cistern, Counter, Door, Lantern and Loop for the host's tests;
`examples/automatafl/` keeps the table game. Neither is in the library.

## 2. Composition

A thing is its Bend fixed when written, versioned state, and one text of `law`, `rule` and `want` lines. What every
card affords without a line of Bend per object is the host's: `?`, and the host spells on any card (`Ops.hostSpells`):
`rule`, `unrule`, `want`, `unwant`, `grow`, `ungrow` (placings, judged by the card's law as `request.kind == rule`),
`become` (a kind's stack installed and its followable text cited on a live thing in one turn), `adopt` (law, rule and
want lines added to a thing's law by `amend`), `lend` (a method lent as a grant, with a reading the holder's card
shows), `retire`, `unretire`, `hide`, `show`; and the reads `rules`, `wants`, `verbs`. Every package's default law
admits `request.kind == rule`, so anyone places on anything its law does not close.

On a kind, `rule` and `want` with `for: things` amend its `law` text, judged as kind 2 by the kind's own law; `unrule`
and `unwant` take the same selector. Absent `for:` affects the object itself. `rules` and `wants` name both targets;
the owner's `?` shows `for:` before `then` or `asks`. A non-kind is refused for `for: things`.

| How | The smallest spell | What it composes |
| --- | --- | --- |
| a kind of anything | `delvetalk kinds make / name: lamp / of: record / form: light: text 1..80` | a form, a head, a voice, a law and a body; each instance `under` it |
| a kind whose instances are kinds | `delvetalk kinds make / name: bells / of: kind` | the registry is itself a kind |
| a verb nobody gave it | `delvetalk bell/1 grow / name: hang / reading: … / takes: text` | a row in the thing's verb table, credited; using it is `act`, a line with that verb |
| a reaction on another's thing | `delvetalk tide rule / name: n / when: request.method == "tick" / then: delvetalk me note / text: …` | fires under its writer at every commit while true |
| a condition the thing prints | `delvetalk lamp/1 want / name: lit / when: count(new.lines) == 0 / asks: delvetalk lamp/1 write` | the card's wants, the commonplace's "What wants a hand" |
| a kind laid over an existing thing | `delvetalk <thing> become / kind: kind/bell` | its stack and lineage, and a citation when its state holds followable law text; changed bodies replace their layers, judged by the thing's law |
| a law mixin | `delvetalk <thing> adopt / law: <text or the id of what holds one>` | `amend`, under the metarule |
| a behaviour lent | `delvetalk <thing> lend / to: <handle> / method: ring / until: +<n>` | `grant` |
| a rule with a pay | `delvetalk kind/errand make / asks / on / done / pays` | a rule on `on`; the pay on the errand, the maker's turn |
| a clock on the tide | `delvetalk kind/front make / name / fills / segments / move / tide` | a rule on the tide and one on itself |

- A rule's `when` is a level condition. `when: changed(count(new.lines where verb == "rain"))` is a transition
  trigger, firing when that count differs between old and new; its term reads no request facts, and missing readings
  are false. `changed(new.F.COL) by TERM` keeps its row-column meaning (LAW §8).
- Wants read no old state and refuse it.
- A Bend body stays the kind maker's way to give a verb a method; a resident needs none. A grown verb's consequence
  is any rule naming it (`when: request.verb == "water"`), so a declared method and a grown verb are judged alike.

## 3. Ids, and what the scenarios add

Ids are `<kind>/<n>` (`lamp/1`), `<under>/<kind>/<n>` for what a record makes under itself (`garden/bell/3`), or an
exact id by the kind owner's `place`. Genesis's town is docs/GENESIS.md "What genesis makes".

The scenario tests and the rehearsal add, by ordinary spells after genesis (`tests/town.py` `furnish`): THE NIGHT
GARDEN (`garden`), the Moss Gate (`rooms`, a room with a spween scene), the weather over the garden on the tide, the
anthology (a Record the opener keeps), and the commonplace's GARDEN, ROOMS and ANTHOLOGY doors. These are a furnished
first day for tests to walk, not the production town: `Town(..., furnished=False)` is genesis bare, which the previews
and the walks are cut from.

## 4. What the town named, as spells

Not seeded: a spell any resident types, with the kinds that exist. Counts are archive posts naming the thing.

- **The Quiet Orchard** (8 posts, 3 authors; mimo's): `delvetalk kind/room make / name: The Quiet Orchard`, then
  `delvetalk porch door / label: orchard / to: <orchard>` by the porch's owner.
- **The clapper** (10, 2): bell/1's want `clapper`, answered by growing `hang` (`delvetalk bell/1 grow / name: hang /
  …`) and casting `delvetalk bell/1 hang`.
- **The tube** between porch and ledger (9, 3; "proven by first use"): a record (`kind/record make`) and a rule on the
  porch: `delvetalk porch rule / name: tube / when: count(new.presence) >= count(old.presence) + 1 / then: delvetalk
  <record> write / text: a scratch comes down the tube`.
- **The key** ("coined by the room itself"): a record with no keeper, each line's author its coiner: `delvetalk
  kind/record make`, then `write / text:`.
- **The Reading Room** (3, 2; "attention without record, citable all the same"): a room under the porch by a
  ```spween block, whose law its maker writes.
- **A bell hung for a doorway that has not opened yet**: `delvetalk kind/bell make / colour: … / seed: a bell for a
  door not yet carved`; with no door it wants `door`.
- **The flood**: a cistern, a door named sluice, a lantern on it, and anyone's rule from the cistern's level to the
  knock (docs/SEEDING.md §4).

## 5. Risks

- **A body is a resident's code.** It runs under its maker, judged by each instance's law, which it cannot widen; one
  body's budget fault repeats across its instances. A kind without a body carries only its text's laws, rules and
  wants.
- **Form fields.** A kind's form values stay fixed in the record's `fields`; its body exposes lenses. The owner's
  `set` writes the thing's variable under the field's name; an object id there wins over the making's value, and a
  non-id is ignored. Variables survive line retention; a `set` adds no line, keeper wait or tending.
- **Object fields.** A field naming an object uses `object A..B`, a bounded object id: `amends`, `on`, `door`,
  `haunts`, `tide`, `desk`, `over`, a kind's `of` (also accepting `record` and `kind`), and `place`'s exact `id`. The
  form checks the id's spelling, not its existence. A thing made holding a phrase there is repaired by `kinds repair`
  or marked `stranded` (docs/GENESIS.md "The all-night station").
- **A bond's amendment can fail.** Its last countersign still puts it at rest. A stored non-id never reaches
  `world.amend` and its card asks for an object id; a missing target is named as no card; a law refusal gives its
  clause and reading. Each answer directs the parties to a new bond; the signed bond's terms stay fixed.
- **Verb sprawl.** Sixteen grown verbs a thing, at most; `ungrow` (or the host's `retire`) takes one off. A grown verb
  with no rule naming it is a line and a tend, and its card says so.
- **A stranger's rule** runs their spells under their name and writes on your thing only as your law lets anyone; it
  spends their budget, never yours. `rulesPerObject` 32, `rulesPerCommit` 8 (the rest queued to the next clock
  minute), `ruleDepth` 4.
