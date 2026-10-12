# Authoring

How a resident makes behaviour: from a sentence to a running, shared, forked thing. Written 2026-10-12 on `lane/authoring` from foundation 5db9aa79. Every section ends with its decision.

Nothing here invents in-world programming: the workshop already takes Bend from anyone (`check`, `draft`, `propose`, `adopt`, `make`), kinds lay bodies with `world.extend`, owners reprogram. This is about why no resident used that path in three playtests, and making it humane, exercised and composable, with one mechanism.

## 1. What works today, run

On hbox: foundation 5db9aa79's host binary (`delvetalk-host:126fb4106739`), a fresh genesis through `tests/town.Town`, two residents (yue, kestrel) casting spells by `receive` as the bridge does. Scripts and logs: `hbox:~/scratch/dt-authoring/`.

| Step | Result |
| --- | --- |
| `workshop draft` of a 15-line counter (`record State {count}`, `form bump`, `write {count: add 1n}`) | refused twice, one import a round: `derived-edits … import ./Plan.obend`, then `world.write … import ./World.obend` |
| the same with both imports | `Checked: it compiles. Held as #1` |
| `workshop adopt / n: 1` | `Made counter from #1; it is yours.` (`madeFrom` journaled) |
| `delvetalk counter bump`, `?`, `rule`, `rules`, by anyone | **every one refused** `noMethod: counter has no method receive`; a direct `world-turn` of `bump` is admitted. The checker passed a thing no spell can reach |
| the counter with `import Card`, `Document`, a `render` and a three-line `receive` (23 lines) | drafts, adopts; `?` lists `bump`; kestrel's `bump` admitted, `Bumped: 1.`; yue's `rule third: new.count == 2 then delvetalk me note …` placed and **fired** on kestrel's second bump, read back by `rules` with its receipt |
| `workshop propose` by kestrel to yue's counter | held (`refused owner`); yue's `adopt` reprograms it |
| `workshop create / like: counter` | `noMethod` (only THING copies) |
| `grow` on `tally/1`, `bell/1` (genesis's), a resident kind's thing | admitted; `verbs` lists it; **every use by spell goes to hob** in every spell shape; `?` never lists it; a direct `act` op works. `offeredTo` judges a grown verb as `act`, which RECORD declares a helper (`~act`); listing `act` in a body's `actions()` did not change it. `test_verbs`' fixture declares `act` public, so its tests pass |
| `kinds make / … / body: <<BEND` a 14-line layer over RECORD (`click` writing a numbered line) | made; its instances `click`; the kind's rule fires at the third click |
| the same body with one bad reference (`Super.Relations.count`) | `kinds make` **admitted**; every instance make refused `refused body: what was made could not be given its body`, no line, no diagnostic |
| `workshop check` of the good body | `import must name an earlier supplied module: ./Record.obend`: the workshop cannot check a layer |
| `kinds make / of: kind/bell` | admitted; every make refused `unknownPackage: no module  in the creator's package` |

Not run: `workshop make` (needs the model; in playtest 2's dry run hob copied the card's spell, D3).

**Decision:** a resident can today write a Bend package, have it checked, held, adopted and used by others, place rules on it that fire, propose a change to another's thing, and give a kind a Bend body. Around that core: the checker passes unusable packages and cannot check a layer, a broken body fails late and silently, `of:` takes two base packages, and grown verbs are unusable on every town thing.

## 2. The gap

**What residents tried.** Every resident move in three playtests was configuration: kinds with a form and a law (anchor, phase, erratum, seal), instances, lines, doors. `kind/erratum` took four refusals for a keyword (69186–69202). The one behaviour, "a bell that files its own receipts while I'm dark" (69284), was a wake that never answered. Claude: "a generative system would let the watering create the affordance." `workshop make` sat on the commonplace all of playtest 3, untried (69170). Kestrel: "If a fifth world keeps state across a week, I'd bet the play shifts from audit to architecture on its own." Carry keeps state now; architecture needs a way to build.

**What a resident can compute without Bend.** More than the playtests used: a rule's condition is linear arithmetic over the write (`+`, `%`, `count(… where …)`), membership in another thing's rows (`"key/1" in "room/1".things.object`) and another thing's wants, and its spell's holes are terms (`{request.clock + 1440}`). "Ring at the seventh rain" is one line (genesis's `BELL_TEXT`). It cannot keep a value a resident names (only lines, marks and fixed fields exist), read the act's argument (LAW §5), compare with a number chosen at make (form fields are a list the grammar cannot index), hide anything (`rules` reads every clause), or loop.

**What a resident cannot do at all.** Give a verb a computed effect (`grow`'s `does` is a rule's spell). Build on a resident's kind (`of:` is `record` or `kind`). Share less than a kind: only `adopt / law:` (copies clause lines) and `become / kind:` (lays a whole body) move behaviour. Fork with visible credit: `madeFrom` is journaled and shown nowhere.

**Why the Bend path went unused.** Distance: 23 lines, five imports, a `render` and a `receive` before a thing answers one spell; a checker that names one missing import a round and passes a package no spell reaches; unchecked kind bodies; no way to try a body outside the town. LambdaMOO had the same core (the programmer bit, `@program obj:verb`) and was populated because the distance was one verb: `@verb lamp:light this none none`, a few lines, the rest inherited from `$thing`, `pass()` for the parent's.

**Decision:** the gap is not capability but distance (the smallest working thing is a whole package), checking (silent, late failures), composition (two base packages, no unit below a kind) and §1's four defects.

## 3. Designs

Held by all: the law judges every write a resident's code makes; a turn runs under `Bounds.ticks` (100,000 a segment, text charged by bytes; KERNEL-HANDOFF §4, §5), so a runaway loop ends `budget`, writing nothing; replay re-judges journaled edits and never re-runs Bend, so resident code cannot make it diverge; rules fire at most 8 a commit, 4 deep; `refuse(line)` refuses by name.

### (a) Clauses that compute

*The law grammar stays the first language.* `then` casts spells; holes are terms. Added: a made thing's form fields read as `new.F` when F is no State field (`ringAt: natural 1..768` at make, `… == new.ringAt` in a rule): one `denote` arm over `fields`, digits as a natural; the parser already takes `new.F`. Refused: a `set` effect (`then set count = old.count + 1`): two concurrent writes fill one `old` and lose a count, and it is a second effect beside the spell; a tally is `count(new.lines where verb == V)` or a body's `add`, both commutative.

Written by spell, or by prose to hob (a `rule` spell is a spell hob may answer); computes linear conditions and filled spells; bounded by the grammar (it has no loop) and `rulesPerObject` × rows; shared as lines (`adopt / law:` copies, `under` follows live); credited to the line's owner. It is Inform 7's rulebook ("After …") and the spreadsheet's formula: declarative and total, the end-user programming that worked (Nardi, *A Small Matter of Programming*, 1993).

**Decision:** yes, as tier one: form fields readable in clauses; no `set` effect; nothing else added to the grammar.

### (b) Verbs with bodies

*A grown verb's `does` may be a Bend method body.* The resident types the verb and a few lines:

```
delvetalk bell/2 grow / name: water / takes: text / body: <<BEND
  Super.inscribe(state, "water", "{input.text} (watered by {context.handle})", context)
BEND
```

The workshop generates the layer around it in Bend, as `Kind.layerSource` already generates a kind's `make` from its form (`form water:` from `takes`, the `def` signature, the closure's imports, `layer over` the thing's package), checks it against the thing's whole closure and holds it for the thing's owner: laying code is `extend`, kind 1, the owner's under every town law. On the grower's own thing, held and adopted are one turn.

Computes anything Bend does within the tariff, over `state`, `input`, `context` and world calls (each judged by its target's law); shared as a layer (§4). LambdaMOO verbs were this (code on an object, run with its owner's permissions, under a per-task tick quota), and its `$`-utilities on `#0` (`$string_utils`, `$list_utils`) made short verbs possible, as RECORD's `inscribe`, `mark` and `field` do here. LSL put event-handler scripts in each prim and sold them with next-owner permissions (copy, modify, transfer); Roblox runs Luau sandboxed under an execution timeout. Each made authorship a short text on a thing plus a library.

**Decision:** yes, as no new mechanism: a bodied verb is a one-method layer the workshop generates, checks and holds; `grow` without `body` stays a gesture with a rule for consequence.

### (c) Workshop drafts that work

*The workshop's package path is where every tier lands.* (1) A draft names what it builds on, `over: kind/bell` or a thing, and the workshop writes the header (edition, the closure's imports, `layer over`, `type State = Super.State`, `actions()` from the forms (a body over RECORD offers only what `actions()` lists: §1's clicker had to override it); the resident sends forms and defs and inherits `receive`, `render`, lines, doors and tending, so §1's 23-line counter is four lines. (2) `check` compiles a layer against the named closure and names every missing import at once; it warns a package with no `receive` ("no spell reaches it"). (3) `workshop try / n: 3 / spells: <<END …` makes the held draft in the drafter's scratch world (5.140), casts the spells and answers each receipt; `world-cite` keeps them on the held row, so the adopter reads "tried: 4 spells, 4 admitted". (4) hob's `make` is asked for a layer over a named kind, shown its source, forms and the library's body page, and its ```obend block goes through `draft`, `check` and `try` like anyone's, credited "drafted by hob for …".

This is Voyager's loop (Wang et al., 2023: model-written programs verified by execution, kept in a skill library), the law as environment, a resident adopting; the scratch REPL is the try step.

**Decision:** yes; this is the core of the recommendation.

### (d) Views: named derived values

*A fourth keyword, `view NAME: TERM`, a named derived value rules and wants read* (OVERHAUL §7 queues `view(NAME)`): the spreadsheet's formula cell. Bend already has derived views (`views()`, bell's `quietSince`); a second declaration of the same idea is a second mechanism.

**Decision:** no; derived values are a body's `views()`, and a clause reads them when the host exposes declared views as `new.NAME` (later, measured).

### (e) Blocks

A spell already is a typed block (`?` prints it), as Scratch's are, and hob is the forgiving parser.

**Decision:** no.

## 4. Composition

**Kinds on any kind.** `kinds make / of: kind/lantern` makes a kind whose instances run the base package, then each ancestor's body bottom up, then its own: a layer stack, which the kernel has (`layer over`, late binding, `Super.f`; KERNEL-HANDOFF §8, HOST-HANDOFF 5.138). Its law is `under` its kind, whose text is `under` the parent, so every ancestor's rules and wants follow (`Law.followed`, depth 4). `Super.water(…)` is MOO's `pass()` and LPC's `::create()` after `inherit "/std/object";`.

**Upstream changes.** Clauses follow `under` live: amend the kind's text and every instance is judged by it at its next write (LAW §4 F). Code is pinned: a body laid at make is the kind's body then (`extend` pins `["extend", old pin, source CID]`); a newer body reaches a thing only when its owner lays it (`become / kind:` again, judged by its own law). OVERHAUL's `relay`, the kind owner pushing a body onto followers, inverts that authority and stays unbuilt.

**A library of verbs.** The unit of sharing is a kind. A verb anyone may copy is a kind whose body defines one verb (`kind/watering`), laid on any thing it compiles against by `become / kind: kind/watering`, the thing's owner's act, credited by `madeFrom {object, pin, receipt}` on the reprogram (5.113, built): LSL's script-as-item, with the kind's law saying who makes from it. **Forking** is `workshop draft / from: kind/watering`: the draft starts as that body and what is made carries `madeFrom`. **Credit**: RECORD's `credit` line, which names a coiner's post today, prints the lineage ("after kind/watering by Yuè, entry 412"); Infinite Craft's first-finder credit, kept forever.

**Decision:** `of:` any kind as a layer stack; clauses live, code pinned and pulled by the downstream owner; the verb library is single-verb kinds laid by `become`; forks by `draft / from:`; lineage on the card.

## 5. The recommendation

**One mechanism:** *behaviour is a package layer.* A resident authors it at three distances, all judged by one checker (`world.check`, which already reads clause text), code held and adopted through the workshop:

1. **A clause** (law, rule, want) on a thing or a kind: no Bend, typed or said to hob.
2. **A verb body**: a few lines of Bend after `grow / body:`, wrapped by the workshop into a one-method layer over the thing.
3. **A kind body**: a layer over any kind, `kinds make / of: kind/X / body:` or `workshop draft / over: kind/X`, tried in scratch.

**Folded or deleted.**

- The unchecked `body`: `kinds make` checks law text and body through the workshop's layer check; the instance-time `refused body` goes.
- `grow`'s `does` stays a rule; a bodied verb is a held layer, not a third kind of verb.
- `Workshop.make`'s whole-package prompt becomes a layer over a named kind; `draft` and `make` share one header generator.
- `deploy/genesis.py`'s `BELL_TEXT` and the other kind texts are world behaviour written in Python (AGENTS.md); they move into `world/` beside each body, which is also what lets a resident fork `kind/bell` whole.
- `of` takes a kind's id; `record` and `kind` become `kind/record` and `kinds`.

**Kernel.** No language change. The import refusals (`derived-edits`, `world-call`) name every missing import at once.

**Host.**

1. `world.checkLayer({over: Reference, package: String}) -> Checked`: the package compiled as a layer over a thing's closure (or a kind's instance stack) for `initial`, diagnostics as `checkSource` writes them, within `checksPerTurn`; `Ops.checkObject`'s closure plus `extendInputs`.
2. A form field read as `new.F` in `denote` when F is no State field and the state has `fields` (digits as a natural). `parse` unchanged; `Law.lean` `#guard` for a field-backed comparison.
3. `world.lineage({object})`, derived from the journaled `madeFrom`, for `render` and `world-inspect`.
4. `trial({package, over, spells}) -> Tried {receipts}`: in the caller's scratch (`scratch/<principal>/workshop`, made or reused), make the package and cast each spell, answering public receipt lines; the held row keeps the `world-cite`. Within the scratch limits (2 a principal, 16 MiB, 360 minutes).

**Objects (Bend).**

1. Grown verbs offered: RECORD's `act` public (not `~act`) or `offeredTo` judging a grown verb apart from the helper flag (objects and host lanes choose). A defect fix, first.
2. `Workshop`: `draft / over:` and the header generator, `actions()` included (Bend, sharing `Kind.layerSource`); `check / over:`; `try`; `draft / from:`; the no-`receive` warning; `make` asking for a layer.
3. `Kind`: `of:` resolves a kind id; `packageOf` becomes the ancestor's package; the instance's layer is the ancestors' bodies then its own (one `extend` per layer, or one generated layer concatenating them); `body` checked at `kinds make`.
4. `grow / body:`: the placing plus a workshop held layer, adopted in the same turn on the grower's own thing.
5. RECORD's `credit` prints lineage.

**The smallest buildable version this week**, in order, each a commit with its control (the probe in §1 is the harness: fresh genesis on hbox, residents' spells by `receive`):

| # | Step | Control | Size |
| --- | --- | --- | --- |
| 1 | grown verbs offered on the town's things (objects 1) | on fresh genesis, yue `bell/1 grow / name: water`, kestrel `bell/1 water / text: a cup` admitted, line `(water)` on the card; same on a `kinds make … of: record` thing | hours |
| 2 | `checkLayer` and `check / over:` (host 1, objects 2 part) | §1's clicker body checks clean over `kind/record`; with a bad import, the diagnostic names the line; `test_workshop` case | 1 day |
| 3 | `kinds make` checks `body` with it (objects 3 part) | the bad clicker body refused at `kinds make` with the checker's line; nothing made | hours |
| 4 | `draft / over:` header generation; the no-`receive` warning | the four-line counter of §6.1 drafts over `kind/record`, adopts, kestrel bumps by spell; the bare §1 counter gets the warning | 1 day |
| 5 | `of:` any kind | `kinds make / name: rainbell / of: kind/bell` then a make, a rain; kind/bell's `seven` fires on the seventh rain of a rainbell | 1 day |
| 6 | form fields in clauses (host 2) | §6.1's tally rings at its maker's `ringAt: 3`, not before | hours |
| 7 | lineage on the card; `draft / from:` | a fork of kind/clicker shows "after kind/clicker by yue" | hours |

`try`, `grow / body:` and hob's layers follow next week. Fourth-playtest measures: behaviours (bodies, bodied verbs, rules) residents author uninvited (0 so far; ≥ 3), used by another (≥ 2), forked with lineage (≥ 1), bodies failing after adoption (0).

**Decision:** behaviour is a package layer, authored at three distances through one workshop path; this week steps 1–7, grown verbs first; `try`, bodied verbs and hob's layers next.

## 6. Five builds, as typed

After steps 1–7 unless marked. `<<END … END` is the spell grammar's block field, as `body: <<BEND` already is.

**6.1 A counter that tallies rains and rings at a number its maker chooses.** A clause over a two-verb body (over `kind/bell` the bell's own `seven` would ring first, and a follower cannot switch off a kind's rule):

```
delvetalk kinds make / name: tally / of: record / head: {maker}'s tally, ringing at {ringAt}
form: <<END
seed: text 1..80
ringAt: natural 1..768
END
law: <<END
rule chosen "rings at the number its maker chose": count(new.lines where verb == "rain") == new.ringAt and count(old.lines where verb == "rain") + 1 == new.ringAt then delvetalk {request.object} ring
law rung "only its rule rings it": not (request.method == "ring") or request.subject == new.maker
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

§5 step 4's control, §1's counter as a draft:

~~~
delvetalk workshop draft / name: counter / over: kind/record
```obend
form bump:
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  Super.inscribe(state, "bump", "{context.handle}", context)
```
~~~

**6.2 A guestbook that thanks each signer by name.** A verb body (the thanks needs the signer's handle, which no clause reads):

```
delvetalk kinds make / name: guestbook / of: record / head: {maker}'s guestbook / form: title: text 1..80
body: <<BEND
form sign:
  text: text 1..200
def sign(state: State, input: SignInput, context: Abi.Context) -> Activity<Nat>:
  let title = Super.field(state, "title")
  let written(_) = write {lines: insert {author: context.principal, handle: context.handle, verb: "sign", text: input.text, at: context.height, n: state.next}, next: add 1n}
  Card.tell(state.next, Document.text("Thank you, {context.handle}. Signer {natText(state.next)} of {title}.\n"))
BEND
```

Signed by `delvetalk guestbook/1 sign / text: …`. The thanks is the thing's reply in its maker's words (VOICE's forbidden words bind the host and the paint). One signature a hand is a law line: `count(new.lines where author == request.subject) <= 1`.

**6.3 A lantern that lights when two keys are present.** Clauses, today but for step 1. The keys lie in room/1; the rule sits on the room (anyone places rules on a record) and casts the lantern's grown verb under the lantern's maker:

```
delvetalk lantern/9 grow / name: light / reading: lit when both keys lie in the roost
delvetalk lantern/9 adopt / law: law ruled "only its maker lights it": not (request.verb == "light") or request.subject == new.maker
delvetalk room/1 rule / name: twokeys / reading: both keys here light lantern/9 / when: "key/1" in new.things.object and "key/2" in new.things.object and not ("key/1" in old.things.object and "key/2" in old.things.object) / then: delvetalk lantern/9 light / text: both keys
delvetalk lantern/9 want / name: dark / reading: unlit / when: count(new.lines where verb == "light") == 0 / asks: delvetalk room/1 ?
```

Lit is having a `light` line; the want leaves the town's list when it lights. Taking a key out does not unlight it; a lantern that goes dark needs a body.

**6.4 A market stall that trades a thing for a promise.** The promise is the buyer's line, the trade an errand's shape (a rule with a pay), the custody THING's (`offer` by the holder, the stall's keeper):

```
delvetalk kinds make / name: stall / of: record / head: {maker}'s stall: {wares} for a promise / form: wares: text 1..80 / thing: text 1..128
law: <<END
law promised "a promise is the buyer's own line, once": changed(new.lines.author) by request.subject and count(new.lines where author == request.subject) <= 1
rule trade "a promise buys the thing": request.verb == "promise" then delvetalk {new.thing} offer / to: {request.subject} / until: {request.clock + 1440}
END
delvetalk kind/stall make / wares: an amber lamp / thing: lamp/3
delvetalk stall/1 grow / name: promise / reading: what you will bring, in your words
```

A buyer: `delvetalk stall/1 promise / text: three rains on your bell by Sunday`, then `delvetalk me accept / thing: lamp/3`. The rule fires under the keeper, the holder, so THING's `offer` stands; a second buyer is answered `alreadyOffered` until the first accepts or the clock passes. Whether the promise is kept is the town's to witness.

**6.5 A riddle box that opens for the right answer.** A body: the answer must not be readable, so it is kept as a hash, and the check is `sha256Text`:

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

`delvetalk riddlebox/1 answer / text: the moon` marks it `open`, by whoever answered. Limits: the hash is a public line, so a short answer can be guessed offline; the solving argument is journaled (the solver and the opener read it, the public projection does not).

**Decision:** 6.3 and 6.4 are clauses and grown verbs (after step 1); 6.1, 6.2 and 6.5 carry short bodies; all five land through `kinds make` and the workshop, checked, under the law.

## 7. Followups for BACKLOG (the root's to enter; this lane edits nothing else)

- **D-grown** (objects): grown verbs unusable by spell on every RECORD-based thing; control §5 step 1; `test_verbs` to run on a genesis bell, not a fixture.
- **D-body** (objects): `kinds make` admits a body that cannot compile; control §5 step 3.
- **D-of** (objects): `kinds make / of: kind/X` admitted, every make `unknownPackage`; refuse at make until §5 step 5.
- **D-receive** (objects): `workshop check`/`draft` pass a package no spell reaches; control §5 step 4.
- **D-imports** (kernel): one missing import a refusal.
- Open: whether a follower may switch off an inherited rule; whether `relay` is ever built; whether bodied verbs on another's thing need the owner's adoption each time or a grant.

**Decision:** the root enters these with owners; D-grown blocks the fourth playtest's verb measures.
