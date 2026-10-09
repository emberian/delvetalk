# Objects handoff

Written by the objects lane (lane/objects2) for its successor. Everything here was
measured against the real checker and host; nothing is from memory of the design
documents. Copy the binary into the worktree (`cp <foundation>/.lake/build/bin/delvetalk-obend .`),
set `DELVETALK_OBEND=$PWD/delvetalk-obend`, never run `lake`.

## 1. Conventions as they are

An object is one file under `world/objects/`; it imports modules by basename (flat
names; `world/lib`, `world/lib/prelude`, `world/lib/document`, `world/lib/game` are all
the library).

* **State, Seed, seeded, initial.** `record State`, `record Seed` (or `type Seed = {}`),
  `defaultSeed()`, `seeded(seed) -> State`, `initial() = seeded(defaultSeed())`. The host's
  `create` does NOT call `seeded`: it lays the seed (a record naming some State fields)
  over `initial()`. So a Seed's fields must be State fields of the same name, and a derived
  field cannot be computed from a seed (Bell's planter is `planting.principal`, not a copy).
  `world-create` takes a whole State.
* **The card protocol** (`world/lib/Card.obend`). Every object (except Counter, the host
  suites' timed reference activity) has a pure `render(state) -> Document` (the card),
  `forms() -> Card.Forms` (its actions as data; a form's `card` is "", the spell names the
  object id), `door() -> Card.Door {word, blurb}`, and `receive(state, input: Card.Heard,
  context)` with `Heard = {text, post, slot}` (slot "" when the reply answers no awaiting
  post; the bridge always sends all three; the host refuses an argument with a field the
  method lacks). The usual receive is three lines: `Card.route(text, context, forms())`
  gives `act {action, fields}` or not; `act` dispatches; anything else is
  `Card.answer::<Edits, S, R>(routed, context, forms(), render(state))`, which offers the
  card, why ("Not done: ..."), and every form as a copyable spell. An empty reply shows the
  card; the HTTP front asks for it that way until `world-card` exists everywhere.
  `Card.text/natural(fields, name)` read typed fields. Garden and Workshop keep their own
  receive (policy fall-through, fenced blocks).
* **Composition.** An activity composes only in tail position (no effect in let, argument,
  field, payload or lambda). A method another activity reuses takes its finish as a pure
  function: `def rained<T>(state, text, context, then: Nat -> T) -> Activity<Plan, Response, T>`,
  then `rain = rained::<Nat>(..., fn(n: Nat) -> Nat: n)` and receive uses
  `rained::<Card.Reply>(..., fn(n) -> Card.Reply: Card.Reply.done(...))`. Fan-out is explicit
  recursion (`Card.broadcast`), never a send in a lambda.
* **Payloads are Data.** `Plan<E>`; call/send/create/callVia/sendVia carry
  `Data.of::<T>(value)`; `Plans.nothing()` is the empty payload. Data may not sit in a
  State yet. `Response<S, R>`: S the state you `view`, R the result of what you `call` and
  of an interpreted proposal (the proposal's argument is plain JSON: no variants, so a
  colour is a name; Garden's `Planting {colour: String, seed}`).
* **Principals.** No argument names one. `context.principal` is the actor, `context.caller`
  the calling object ("" for a direct turn), `context.intent` the turn's identity. An
  Avatar's id is its principal's DID. `Card.handle(did)` shows its last segment.
* **Observers** replace hand wiring: `observers: Card.Observers` in State, `observe`/
  `unobserve` methods that write `Card.observing/unobserving`'s one Entries edit (a generic
  activity over the object's Edits nested past the packet capacity when imported, so the
  object writes it), and `Card.broadcast::<Edits, S, R, T>(observers, Data, 0n, then)`.
* **Cards fit 1,400 characters**: `Card.clipped(lines, 8n)` shows eight and "… and N more".
* **Pages**: `page(state, context) -> Card.Page` (default `Card.defaultPage`), rendered by
  `Card.pageText` and emitted with `publish` (Garden.publish).
* **Laws in source** (`law NAME: EXPR`) are kept by the host, refused by the pure stateless
  compile ("package laws require a host law adapter"; `tests/test_objects.compile_job`
  strips them), and refused in any module a package imports ("a law belongs to the
  package's entry module"), so a lawful object cannot be made by a creator that imports
  it: tests make Policy, Env, Wake, Tide, Deal and Table with world-create. A law must admit
  an amendment by the one who installs it ("law has no amendment clause"): Env and Wake
  are made by their owner. `writeOnce` reads naturals only and passes a text field
  unjudged (Deal uses a `closed: Nat`). `request.method` and `REF in new.F` exist.
  Bend predicates `def law(old, new, request: Abi.Request) -> Abi.Verdict` (Tide, Wake) are
  recorded in the artifact; the host does not run them on a turn yet.

## 2. Hard limits found (measured)

* **About 256 top-level declarations per closure.** The typed packet nests the whole
  program's declarations as one row; `typeNestingCapacity` is 256, and a package whose
  closure (every module listed, imported or not) holds more is refused with
  `typed packet does not decode: type nesting capacity`. The library costs ~165 (Spell 52,
  Card ~37, Document 22, List 26, Plan 21, Abi 8, Form 5). Garden's closure (Bell,
  Cistern, Card, Spell) has 8 to spare: a creator test's Maker module (6) fits, a Spell
  probe does not. Measure with an `n` dummy-def bisection (see git history,
  `room.py`). The kernel should raise or restructure this before the queue below.
* Each module in a closure costs every turn: Counter with Card took 20 s for 200 HTTP
  turns (10 s before), so Counter stays outside the protocol.
* Spell card names are `[a-z0-9-]+`: `env/<did>` cannot be named in a spell.
* An await only proves that some turn with that identity was admitted; Seat reads the
  rival seat after its await. A turn suspended on an object resumes refused `staleRoot`
  if anything wrote that object meanwhile: keep waits on objects nobody else writes
  (one Appointment per booking; one Seat per player).
* `run` refuses variant arguments and recursive results: build in a probe module.

## 3. Objects

Counter (reference), Garden (plant, cistern, receive with policy fall-through and
yes/no, children, page/publish), Bell (rain, ring, strike, observers), Cistern, Anthology,
Directory, Door, Lantern, Loop, Place, Thing, Avatar, Policy (owner, law, 16 examples),
Workshop (check, inspect, propose = reprogram another object under its law), Env, Wake,
Tide, Appointments/Appointment, Deal (Exhibition = a deal with three parties and a piece),
Seat and Table (Automatafl on commit-reveal seats; game modules in `world/lib/game`).

## 4. Open

* `render(state, context)`, lenses (`set` through `Form.Lens`), Entries by item: not done;
  each adds declarations Garden's closure has no room for (section 2).
* `receive "merge"` recording `pageCheckpoint`: Garden has no owner to judge it.
* Workshop's diagnostics card would print the checker's `hint`, but the host's `check`
  answers `"<module>:<line>: <stage>: <message>"` without it.
* Directory and Anthology admit anyone's add/remove/admit under the default law.
* An addressee `slot` reaches receive but no object reads it yet.

## 5. What the previous handoff said that was wrong by now

* "the host will move to `seeded`": it overlays seeds on `initial()` instead.
* "247 is the most any list field holds": lists cross the wire as arrays; 248 notes are
  admitted.
* "8 KiB REPL module cap": 16 KiB.
* "A is ONE type for every call, send and create": payloads are Data.
* "`receive {text, who, post}`", `Plans.Position`, `describe`/`present`, Bell's
  `door/configure/lastDelivery`, Door's `lantern/configure`, and the expected failures of
  its section 4: all gone (create, await, interpret, check, inspect are the host's).
* It did not know the declaration cap (section 2), which now bounds every object.
