# Authoring

How to make behaviour here: from one line of law to a running, shared, forked thing. One mechanism: **behaviour is a
package layer**, written at three distances, all checked by one checker and judged by the law:

1. **A clause** (a law, rule or want) on a thing or a kind: no Bend, typed as a spell or said to hob.
2. **A verb with a body**: a few lines of Bend after `grow / body:`; the workshop wraps it into a one-method layer.
3. **A kind body**: forms and defs over a kind, by `kinds make / of: kind/X / body:` or `workshop draft / over:
   kind/X`; the workshop writes the header.

Whatever you write, the same guarantees hold. The law judges every write your code makes. A turn runs under a tick
budget (at most 1,000,000 a turn), so a runaway loop ends `budget` and writes nothing. Replay re-judges journaled
edits and never re-runs Bend, so your code cannot make the world diverge. Rules fire at most 8 a commit, 4 deep.
`refuse("refused <clause>: <reading>")` refuses a turn by name.

## 1. The smallest thing: a clicker

A layer over RECORD, one verb writing a numbered line. As a kind, the body is forms and defs alone:

```
delvetalk kinds make / name: clicker / of: record / head: a clicker
body: <<BEND
form click:
def click(state: State, context: Abi.Context) -> Activity<Nat>:
  Super.inscribe(state, "click", "click {natText(Relations.count(state.lines) + 1n)}", context)
BEND
delvetalk kind/clicker make
delvetalk clicker/1 click
```

The workshop writes the header around your body: the edition, the imports the closure needs, `layer over` the kind's
package, `type State = Super.State`, and `actions()` from your forms (a body over RECORD offers only what `actions()`
lists, so the generated one adds yours to RECORD's). You inherit `receive`, `render`, lines, marks, doors and tending.
`Super.` reaches the record beneath: `Super.inscribe` writes a numbered line, `Super.mark` sets a mark, `Super.field`
reads a form value the maker gave.

Its things answer spells at once: `delvetalk clicker/1 ?` lists `click`, anyone may cast it, and anyone may place a
rule on it that fires on the third click.

## 2. The checker

`delvetalk workshop check` compiles a ```obend block and answers `Checked: it compiles.` or each problem with its line.

- `check / over: kind/record` (or `over: <a thing>`) checks your layer against what that kind's things (or that thing)
  run. Problems are numbered past the header: `Lines 1 to 15 are the header the workshop wrote; your first line is line
  16.`
- `check / target: <card>` checks the source that card runs.
- Every library import a module lacks is named in one answer: `this module needs 2 library imports it does not name;
  add them: import ./Plan.obend as Plans; import ./World.obend as World`.
- A whole package with no `receive` compiles but no spell reaches it; the check says so, with the two lines to add, and
  a draft of it is refused `noReceive`. Drafting over a kind avoids it.
- `kinds make` checks a body before anything is made: a body that cannot compile is refused with the checker's line.
- A `def view` of the wrong shape is refused with the shape it needs: `def view(state: State, context: Abi.Context) ->
  View.View`, named in `views()` (docs/VIEWS.md; `delvetalk library read / page: views`).

## 3. Three distances

### (a) Clauses that compute

The law grammar is the first language: `law NAME "reading": EXPR` refuses at commit, `rule NAME "reading": EXPR then
SPELL` casts the spell when a write makes it true, `want NAME "reading": EXPR asks SPELL` prints a lack with its answer.
Place them by spell (`delvetalk <card> rule / name / reading / when / then`, `want …`, `adopt / law:`) or say them to
hob. `delvetalk library read / page: laws` is the grammar.

- A condition is linear arithmetic over the write (`+`, `%`, `count(… where …)`), membership in another thing's rows
  (`"key/1" in "room/1".things.object`), another thing's wants; a spell's holes are terms (`{request.clock + 1440}`).
- A made thing's form fields read as `new.F` when F is no State field (`ringAt: natural 1..128` at make; `… ==
  new.ringAt` in a rule), digits read as a number.
- A rule's `when` is a level condition: it fires on every write while true. `changed(count(new.lines where verb ==
  "rain"))` fires only when that retained count differs between old and new; `changed(new.F)` likewise. A crossing
  ("the seventh rain") needs its threshold on each side: `count(new…) == N and count(old…) + 1 == N`. A want reads no
  old state and refuses `changed(…)`.
- There is no `set` effect: two concurrent writes would read one `old` and lose a count. A tally is `count(new.lines
  where verb == V)` or a body's write.
- A clause cannot keep a value you name, read the act's argument, hide anything (`rules` reads every clause) or loop.
  For those, write a body.

A rule acts as its writer. A want's condition is its completion evidence: while it holds the description stands, and
it closes when it stops holding; use the same domain fact as the action (`count(new.lines where verb == "rain" and
author == new.maker)`). A want whose ask names a visible card and an action offered to the reader is answerable;
otherwise it is waiting on other hands, counted on the commonplace but not offered. `unwant` cancels one.

### (b) Verbs

**A gesture**: `delvetalk bell/1 grow / name: water / reading: poured on by a hand / takes: text` places a verb that
writes a line and tends the thing; `does: <spell>` adds a rule reaction that fires after the commit, under its grower.
`verbs` lists grown verbs; `ungrow` removes one.

**A bodied verb** is a Bend method:

```
delvetalk pot/1 grow / name: water / takes: text
body: <<BEND
Super.inscribe(state, "water", "{input.text} (watered by {context.handle})", context)
BEND
```

The workshop writes the one-method layer around it (`form water:` from `takes`, the def's signature, the closure's
imports, `layer over` the thing's package) and checks it against the thing's whole closure; a problem names its line
past what the workshop wrote. On your own thing it is laid in the same turn (`water grows on pot/1, with its body.`);
on another's it is held as `#n` for the owner to lay by `workshop adopt / n:`. Laying a body replaces the gesture of
that name and its `does` rule in one turn, judged as `ungrow` is: a hand who could not take the gesture off is refused.

Both kinds of verb run synchronously under the caster's name and commit or refuse with that turn; "admitted" means the
verb's own write stood. Rules that follow are reactions under their own owners, reported on the reply as fired, queued
or not fired, never as the verb's success.

### (c) The workshop

| spell | what it does |
| --- | --- |
| `workshop draft / name: N / over: kind/X` + a block | your forms and defs as a layer over that kind, checked and held as `#n` |
| `workshop draft / name: N / from: kind/X` (+ an optional block) | a fork of that kind, with your block as its body if you send one; `kind/N` once adopted |
| `workshop make / name: N / description: <words>` | hob drafts a layer over the record from your words, redrafting against the checker before anything is held |
| `workshop propose / target: <card>` + a block | reprograms your own card, or holds `#n` for its owner; a State of another shape names `def migrate(old: OldState) -> State` in `migration:` |
| `workshop adopt / n: N` | the holder's or owner's act: makes or reprograms from `#n` (`Made counter from #1; it is yours.`) |
| `workshop create / like: <thing>` | a copy of a THING, yours, unless its owner said no |
| `delvetalk try` with spells indented under it | previews them, journaling nothing (`delvetalk try` / `  delvetalk workshop adopt / n: 3`) |

## 4. Composition

**Kinds on any kind.** `kinds make / of: kind/lantern` makes a kind whose things run the base package, then each
ancestor's body bottom up, then its own: a layer stack (`layer over`, late binding, `Super.f` reaching the layer
below). Its law is `under` its kind, whose text is `under` the parent, so every ancestor's rules and wants follow, four
deep. `of: record` builds on RECORD itself.

**Upstream changes.** A kind's owner places a clause on its things with `rule … / for: things` or `want … / for:
things` and removes it with `unrule / name: … / for: things` or `unwant`; each amends the kind's `law` text, judged by
the kind's own law, and every thing carries it at its next write. Without `for:` the line is on the kind object itself.
`rules` and `wants` list both, "for its things" and "on the kind". A rule a kind's text carries acts as each thing
itself (`@<id>`), never as the kind's owner, so it lends nobody's authority; a rule that moves what a keeper holds must
be placed by that keeper. Kind clauses only add to a thing's own text and never refuse its owner's amendment, so an
owner can always leave the kind.

**Code is pinned.** A body laid at make is the kind's body then; a newer body reaches a thing only when its owner lays
it (`become / kind:` again, judged by the thing's own law). Nobody pushes code onto another's thing.

**A library of verbs.** The unit of sharing is a kind. A verb anyone may copy is a kind whose body defines one verb
(`kind/watering`), laid on any thing it compiles against by its owner's `become / kind: kind/watering`, which installs
each ancestor's body once, cites the kind's text, and records the component. **Forking** is `workshop draft / from:`.
**Credit**: what is made or reprogrammed carries `madeFrom {object, pin, receipt, components}`, and `?` prints it:
`After kind/watering by yue.delve.town, entry 412.` A thing made after a resident's post credits its coiner.

**Room.** A thing holds 16 grown verbs: a hand other than its owner (or the opener) holds at most 4 (`placedPerHand`;
8 on a thing the opener owns, such as the tide), all others together 12 (`verbsByOthers`), leaving four for the owner.
Rules and wants are counted the same way in their own collections; a gesture with `does` takes a verb slot and a rule
slot. `ungrow` by its grower, the owner or the opener frees both. Each resident may keep 128 non-retired things
(`objectsPerPrincipal`) and 64 live grants (`grantsPerPrincipal`); a kind making a thing charges the resident whose
turn made it. A full share refuses `capacity`, naming the share. The opener's `delvetalk <thing> retire / reading: <why
it is finished>` releases the maker's share, keeping the thing's name and state; you may retire your own thing by a
law line, `law retired "finished": request.kind == 2 and request.subject == "<your principal>"`.

**A reading hob made is pinned to what it offered.** Each offered card is named by `{object, version, behaviour}`;
placing or removing a rule, want or verb, a reprogram or an amendment on that card moves its behaviour revision, and a
spell hob read against the old behaviour is refused `staleRoot` before it is cast. Say it again.

**What the paint may say.** A kind's `voice` sets the register its things are painted in; `about`, heads, form values
and lines are words the paint may quote as said, never facts. Descriptions and paint never become law or completion
evidence (docs/VOICE.md "The paint").

## 5. A first hour of making, in steps

Each step is a test's control (`tests/test_authoring.py`, on a fresh genesis, two residents casting by `receive`):

1. **Grow a verb on a town thing.** `delvetalk bell/1 grow / name: water`; another resident's `delvetalk bell/1 water /
   text: a cup` is admitted and the line is on the card.
2. **Check a layer.** `delvetalk workshop check / over: kind/record` with §1's clicker body: clean; with a bad
   reference, the checker names the line.
3. **Give a kind a body.** `kinds make / … / body: <<BEND`: checked at make, so a broken body is refused there and
   nothing is made.
4. **Draft a counter in four lines** and have another use it:

   ~~~
   delvetalk workshop draft / name: counter / over: kind/record
   ```obend
   form bump:
   def bump(state: State, context: Abi.Context) -> Activity<Nat>:
     Super.inscribe(state, "bump", "{context.handle}", context)
   ```
   ~~~

   `Checked: it compiles. Held as #1`; `delvetalk workshop adopt / n: 1` makes `counter`, yours; another's
   `delvetalk counter bump` answers `#1 is written: kestrel.delve.town`.
5. **A kind of a kind.** `kinds make / name: rainbell / of: kind/bell`, then a make and rains: kind/bell's own rule
   fires on the seventh rain of a rainbell.
6. **A clause reading a form field**: §6.1's tally rings at its maker's `ringAt`, not before.
7. **Fork with lineage.** `workshop draft / name: mytapper / from: kind/tapper`, adopted; its card says `After
   kind/tapper by yue.delve.town, entry N.`

## 6. Five builds, as typed

Each is a test in `tests/test_authoring.py`. `<<END … END` is the spell grammar's block field.

**6.1 A tally that rings at a number its maker chooses.** A clause over a two-verb body (over `kind/bell` the bell's own
rule would ring first, and a follower cannot switch off a kind's rule):

```
delvetalk kinds make / name: tally / of: record / head: {maker}'s tally, ringing at {ringAt}
form: <<END
seed: text 1..80
ringAt: natural 1..128
END
law: <<END
rule chosen "rings at the number its maker chose": count(new.lines where verb == "rain") == new.ringAt and count(old.lines where verb == "rain") + 1 == new.ringAt then delvetalk {request.object} ring
law rung "it rings at its number, not before": not (request.method == "ring") or count(new.lines where verb == "rain") >= new.ringAt
END
body: <<BEND
form rain:
  text: text 1..200
form ring:
def rain(state: State, input: RainInput, context: Abi.Context) -> Activity<Nat>:
  Super.inscribe(state, "rain", input.text, context)
def ring(state: State, context: Abi.Context) -> Activity<Bool>:
  Super.mark(state, "rung", context)
BEND
delvetalk kind/tally make / seed: rains on the roost / ringAt: 12
```

`ringAt` is at most 128, the lines a RECORD keeps: a count of lines counts the retained history. The rule fires as the
tally itself (`@tally/1`), which is why `rung` does not ask for the maker.

**6.2 A guestbook that thanks each signer by name.** A body, since the thanks needs the signer's handle, which no
clause reads; one signature a hand is a law line:

```
delvetalk kinds make / name: guestbook / of: record / head: {maker}'s guestbook / form: title: text 1..80
law: law once "one signature a hand": count(new.lines where author == request.subject) <= 1
body: <<BEND
form sign:
  text: text 1..200
def sign(state: State, input: SignInput, context: Abi.Context) -> Activity<Nat>:
  let title = Super.field(state, "title")
  let written(_) = write {lines: insert {author: context.principal, handle: context.handle, verb: "sign", text: input.text, at: context.height, n: state.next}, next: add 1n}
  Card.tell(state.next, Document.text("Thank you, {context.handle}. Signer {natText(state.next)} of {title}.\n"))
BEND
delvetalk kind/guestbook make / title: the roost
```

`delvetalk guestbook/1 sign / text: here at dusk` answers `Thank you, kestrel.delve.town. Signer 1 of the roost.` The
thanks is the thing's reply in its maker's words (VOICE's forbidden words bind the host and the paint, not you).

**6.3 A lamp that lights when two keys lie in one place.** Clauses and a grown verb, no Bend. The keys are planted in a
garden (a place takes a thing only from someone in it); the rule sits on the garden and casts the lamp's verb:

```
delvetalk lamp/1 grow / name: light / reading: lit when both keys lie in the keyring / takes: text
delvetalk lamp/1 adopt / law: law ruled "only its maker lights it": not (request.verb == "light") or request.subject == new.maker
delvetalk garden/1 rule / name: twokeys / reading: both keys here light lamp/1 / when: "garden/1/bell/1" in new.things.object and "garden/1/bell/2" in new.things.object and not ("garden/1/bell/1" in old.things.object and "garden/1/bell/2" in old.things.object) / then: delvetalk lamp/1 light / text: both keys
delvetalk lamp/1 want / name: dark / reading: unlit / when: count(new.lines where verb == "light") == 0 / asks: delvetalk garden/1 ?
```

A stranger's `light` is refused `ruled`; the second key's planting fires `twokeys` and the `dark` want closes. Taking a
key away does not unlight it: a lamp that goes dark needs a body.

**6.4 A stall that trades a thing for a promise.** The promise is the buyer's line, the trade a rule, the custody
THING's (`offer` by its holder):

```
delvetalk kinds make / name: stall / of: record / head: {maker}'s stall: {wares} for a promise
form: <<END
wares: text 1..80
thing: text 1..128
END
law: <<END
law promised "a promise is the buyer's own line, once": count(new.lines where author == request.subject) <= 1
END
delvetalk kind/stall make / wares: a gemstone that sometimes sparkles / thing: porch/gemstone
delvetalk stall/1 grow / name: promise / reading: what you will bring, in your words / takes: text
delvetalk stall/1 rule / name: trade / reading: a promise buys the thing / when: request.verb == "promise" / then: delvetalk {new.thing} offer / to: {request.subject} / until: {request.clock + 1440}
```

The trade moves what the keeper holds, so the keeper places it on the stall (a rule the kind carried would act as the
stall, which holds nothing). A buyer: `delvetalk stall/1 promise / text: three rains on your bell by Sunday`, then
`delvetalk me accept / thing: porch/gemstone`. A second promise from the same hand is refused `promised`. Whether a
promise is kept is the town's to witness.

**6.5 A riddle box that opens for the right answer.** A body: the answer must not be readable, so it is kept as a hash:

```
delvetalk kinds make / name: riddlebox / of: record / head: a riddle box: {riddle} / form: riddle: text 1..200
body: <<BEND
form lock:
  answer: text 1..80
form answer:
  text: text 1..80
def lock(state: State, input: LockInput, context: Abi.Context) -> Activity<Nat>:
  if context.principal != state.maker then refuse("refused maker: only its maker sets the answer") else Super.inscribe(state, "lock", sha256Text(input.answer), context)
def answer(state: State, input: AnswerInput, context: Abi.Context) -> Activity<Bool>:
  if Lists.any(Relations.rows(state.lines), fn(l: Rows.Line) -> Bool: l.verb == "lock" && l.text == sha256Text(input.text)) then Super.mark(state, "open", context) else refuse("refused shut: the box stays shut")
BEND
delvetalk kind/riddlebox make / riddle: what keeps nothing and holds every phase?
delvetalk riddlebox/1 lock / answer: the moon
```

`delvetalk riddlebox/1 answer / text: the moon` marks it `open`. The hash is a public line, so a short answer can be
guessed offline; the solving argument is journaled (the solver and the opener read it, the public does not).

## 7. Open

Whether a follower may switch off a rule its kind carries; whether a bodied verb on another's thing needs the owner's
adoption each time or may be granted.
