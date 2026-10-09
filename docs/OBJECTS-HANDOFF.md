# Objects handoff

Written by the objects lane (lane/objects4) for its successor. Everything here was
measured against the real checker and host; nothing is from memory of the design
documents. Run suites on hbox (`~/scratch/dt-foundation` keeps a built Linux binary):
rsync the worktree to `hbox:~/scratch/<lane>/` and run
`DELVETALK_OBEND=$HOME/scratch/dt-foundation/.lake/build/bin/delvetalk-obend python3 -W ignore -m tests.run <names>`.
For compile-only checks locally, copy `<foundation>/.lake/build/bin/delvetalk-obend` into the
worktree and set `DELVETALK_OBEND`; never run `lake`, never commit the binary.

## 1. Conventions as they are

An object is one file under `world/objects/`; it imports modules by basename (flat
names; `world/lib`, `world/lib/prelude`, `world/lib/document`, `world/lib/game` are all
the library).

* **State, Seed, seeded, initial.** `record State`, `record Seed` (or `type Seed = {}`),
  `defaultSeed()`, `seeded(seed) -> State`, `initial() = seeded(defaultSeed())`. The host's
  `create` does NOT call `seeded`: it lays the seed (a record naming some State fields)
  over `initial()`. `world-create` takes a whole State.
* **The card protocol** (`world/lib/Card.obend`). Every object, Counter included, has
  `renderFor(state, context) -> Document` (the card as the reader in the context sees it),
  `render(state) = renderFor(state, Card.stranger())`, `forms() -> Card.Forms`, `door()`,
  and `receive(state, input: Card.Heard, context)` with `Heard = {text, post, slot}`.
  The host's `card {object}` and `world-card` still run `render` on the state alone: a
  two-argument `render` is refused there with clause `render`. When the host passes the
  reader's Context, rename `renderFor` to `render` and drop the wrapper (one mechanical
  commit). The usual receive is `Card.route(text, context, forms())`, `act` dispatched
  by action, anything else `Card.answer::<Edits, S, R>(routed, context, forms(),
  renderFor(state, context))`.
* **Reader-specific cards.** `Card.reads(principal, context)`, `Card.mine(principal,
  context)` (" (yours)"), `Card.stranger()`. A member sees more: an Env's events, a Wake's
  triggers and an Avatar's notes and follows are their owner's; a Deal shows a party
  its countersign spell; a Policy shows its owner how to teach; Garden reminds a reader
  of the proposal waiting for their yes; a Scene shows a present reader their passage; a
  Commons shows where the reader stands and which gates let them through.
* **Lenses and `set`/`?`.** `Form.Lens<E>.lens {field, form: Form.Kind, put: Form.Value -> E}`;
  an object exports `lenses()` and answers with `Card.answerLensed::<E, S, R>(routed,
  context, forms(), lenses(), guard, card)`: `delvetalk <card> set` plus one `<field>:
  <value>` line is judged against the kind and written through put (guard "" admits; a
  non-empty guard refuses by name first; the law judges the write); `delvetalk <card> ?`
  answers the usage card (forms, then lenses). Without lenses, `?` shows the forms and
  `set` says "Nothing here can be set." Lenses today: Policy (model, escalate, system),
  Avatar (handle). `Card.valueText/valueNatural` read a Value.
* **Spell names.** A card name is `[a-z0-9:/.-]+`, at most 160 bytes, so `env/did:plc:…` and
  an Avatar's DID are nameable; actions and fields stay `[a-z0-9-]+`; `?` is an action.
  The inline form is `delvetalk <card> <action> <field>: <value>, …` (no comma after the
  action). An Env lives at `Events.envOf(did)` = `env/<did>`; one elsewhere refuses publish.
* **List edits by item.** No object writes an index: `amendItem {item, change}` and
  `removeItem {item}` address the first item with the same canonical bytes (`absentItem`
  when none). Find the stored item with `Lists.find`, then address it.
* **Composition.** An activity composes only in tail position; a reusable method takes
  `then: Result -> T`. No `else match`: put the match in its own def.
* **Payloads are Data.** `Data.of::<T>(value)`; `Plans.nothing()` is the empty payload.
* **Observers / mailbox.** `Card.observing` (16) and `Card.observingUpTo(…, cap)`;
  `Card.broadcast`. An Avatar's mailing list holds 32, the host's `sendsPerTurn` (a turn
  past it is refused whole, "turn exceeds the send capacity"); its inbox keeps 64.
* **Laws in source** are kept by the host; a lawful module cannot be imported by a
  creator, so lawful objects (Policy, Env, Wake, Tide, Deal, Table, Directory, Anthology,
  Commons) are made with world-create by their owner. The host prints a law fully
  parenthesised. `law(old, new, request)` Bend predicates run after the text admits a
  kind-0 write (Tide: self, tooSoon; Wake: owner); `tests/test_laws.py` shows them biting.
* **Layers.** `world-reprogram {mode: extend}` with a module `type State = Super.State`
  overrides what it defines; `tests/test_layers.py` (Louder over Bell) keeps rain.

## 2. Limits found (measured)

* The closure cap is gone; Counter with Card runs 200 HTTP turns in 0.50 s on hbox
  (0.39 s bare). The REPL's `MAX_BODY` refuses Counter's closure with Card (413).
* Ticks: Bell card of 1,025 rains 75,997; spell parse of 64 fields 57,044; an Avatar send
  to 32 observers 5,213.
* An await only proves that some turn with that identity was admitted. A turn suspended
  on an object resumes refused `staleRoot` if anything wrote that object meanwhile,
  unless its writes are all keep/add/append (they now commute).
* `run` refuses variant arguments and recursive results: build in a probe module.
* A kernel hint can mislead: an unbalanced parenthesis is reported with "there is no
  Maybe builtin" or "definitions are `def name(x: T) -> U:`".

## 3. Objects

Counter, Garden, Bell, Cistern, Anthology (owner admits), Directory (owner adds and
removes), Door, Lantern, Loop, Place, Thing, Avatar (mailbox: subscribe, send,
unsubscribe; handle lens), Policy (owner law with `request.method`; lenses), Workshop
(check prints the checker's hint under its problem; inspect; propose), Env, Wake, Tide,
Appointments/Appointment, Deal, Seat and Table, Scene (passages and choices as data;
enter, choose, leave), Commons (places, paths, ways in, gates: open, members, object).

## 4. Open

* Rename `renderFor` to `render` once the host passes the reader's Context to `card`.
* Lenses for objects without an owner (Place, Thing, Workshop, Garden's confirm) need an
  owner or a law first; today anyone's kind-0 write is admitted there.
* `receive "merge"` recording `pageCheckpoint`: Garden has no owner to judge it.
* An addressee `slot` reaches receive but no object reads it yet.
* Scene passages are only the creator's seed; there is no activity that adds one.
* Main's other capabilities (appointments' factories, editor and desks, exhibitions,
  library beyond the mailbox) remain to port, one object per commit.

## 5. What the previous handoff said that was wrong by now

* "About 256 top-level declarations per closure" and "Counter stays outside the
  protocol": the cap is gone; Counter joined.
* "Spell card names are `[a-z0-9-]+`": `[a-z0-9:/.-]+`.
* "Data may not sit in a State yet": it may.
* "the host does not run Bend predicates": it does, after the law text.
* "Directory and Anthology admit anyone's add/remove/admit": owner laws now.
* Policy's teaching card showed `delvetalk garden plant, seed: …`, which the grammar
  does not parse (the action would be `plant,`); it reads `plant seed: …` now.
* The brief said the host passes the reader's Context for `card {object}`: it does not
  yet (foundation d1d2021), hence `renderFor`.
