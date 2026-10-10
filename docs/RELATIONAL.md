# Relations in objects: a proposal before launch

Read against `foundation` a2635d2. Line numbers, and the FOUNDATION section numbers cited, are that tree's (today FOUNDATION's principles are §8, the gate §11). Landed by 189b534: FOUNDATION §3 says what was built, and §11 and §12 below are the decisions and corrections the first migration made. Since then: `Relation.canonical` is `canonicalRelation` and `canonicalRows` in `Ops.lean`; `Card.notifyRows`, `RowLens` and `answerLensed` went with the Wholeness (the host delivers changes, WHOLENESS §3); the Anthology keys `proposals` by `{n}` (OBJECTS-HANDOFF §2 lists every declared key).

## 1. What the relational view is here

Moseley and Marks (2006) split a system into essential state, held as relations, and everything else, derived on demand; the accidental state is what rots. DelveTalk already has most of this and names it otherwise. An object's state is a closed record (Bell.obend:20-29); its list fields are edited item by item, addressed by canonical bytes (`editByItem`, Ops.lean:382); the journal is a fact log keyed by height; cards are `render(state, context)`, pure and recomputed per read (HOST-HANDOFF 5.9); laws are constraints judged on `old`, `new`, `request`. What is missing is the one word that makes these uniform: a list field with a key is a relation, and its edits are inserts and retracts of facts.

The view, in the terms the lanes use:

- Essential state is the record's scalar fields plus relations `Relation<T>` with a declared primary key. Nothing else is stored.
- Derived state is a pure Bend function over relations. A card is one; a count is one; "who is present" is one. Nothing derived is written.
- An edit is `insert row`, `retract key`, `upsert row`. The journal height is the fact's time, as `tx` is in Datomic's datom `[e a v tx added]` (Hickey 2012): the journal already records `writes[].edits` per height (HOST-HANDOFF §2), so facts are read from it, never stored twice.
- A law is a constraint over relations: the one-line fragment gains the relational forms of what it has (`insertOnly`, a count bound, membership in a column); quantified constraints are the Bend predicate's (FOUNDATION §13, two-tier law).
- A card is a view; a spell is an edit of that view, put back through a lens where the view is simple enough (Bohannon, Pierce, Vaughan 2006; Hofmann, Pierce, Wagner 2012).
- A Wake is a rule: `when <pattern over an observed relation's new rows> wish <send>`, Realtalk's `When … Claim/Wish` (Dynamicland; Victor, Kay and others, 2018 onward), built on the observers convention that exists (Card.obend:324-360, Wake.obend:19, 104-106).

What is refused stays refused: no solver, no Datalog over the journal (FOUNDATION §13, "not adopted"). Datalog's gift here is not a query engine but a discipline: monotone programs need no coordination (Hellerstein 2010; Ameloot, Neven, Van den Bussche 2011; Hellerstein and Alvaro 2020), which is exactly the host's commutative-root rule (Ops.lean:101, 1316-1319) stated for sets.

## 2. Type and value model

`Relation<T>` is a library type in a new `world/lib/Relation.obend`, a one-constructor generic sum (the trick `Form.Lens` uses, Form.obend:28, since generic records do not parse):

```
sum Relation<T>:
  rows: {items: Lists.List<T>}
```

`T` is a closed record of first-order data; its fields are the columns. The key is declared by the package as data, the way `lawReads()` is (Ops.lean:1144): `def relations() -> Lists.List<Relation.Decl>` with `record Decl: field: String, key: Lists.List<String>`. The host reads it once per pin as a held entry (`compileDef`, as for `law`/`lawReads`, HOST-HANDOFF 5.17) and refuses a key naming a column `T` lacks at creation (`programRefused`, clause `key`). An object with no `relations()` has no relations; its lists behave as today.

Canonical form. A relation's `items` are sorted by the canonical DAG-CBOR bytes (Canonical.lean) of the key projection, and no two rows share a key. This is a host invariant, not a type: `conformsUnder` (ObjectiveBendDemandData.lean:365) checks `Relation<T>` as it checks any list of `T`; `Relation.canonical : Data → Except String Data` (new, Ops.lean) sorts, and refuses `duplicateKey` when two rows share a key. It runs on every seed at `create`/`world-create`, on every migration result, and `applyStep` maintains it. `Ty.isDataUnder` (ObjectiveBendTypes.lean:84) is untouched: nothing new is first-order that was not.

Encoding. A proper list already encodes as a CBOR array (Canonical.lean head comment), so a canonical relation is a sorted array of maps and its identity is that array's CID. Two objects holding the same rows have the same relation CID whatever order they were inserted in. That is the whole point of the sort: `writes[].cid` and snapshot `stateCid` (HOST-HANDOFF 5.35) become order-independent for relations.

Fact grammar (what the journal says, read back by `keysChangedSince` below): `(object, field, key, height, added)` with the row as payload; derived from `writes[].edits` steps, which keep the constructor the object used (`EditKind.data`, Ops.lean:92-99).

Datomic and XTDB store every fact with its time and answer `as-of`; CozoDB makes this per relation with a `Validity` key component. DelveTalk gets the same at the journal (`world-object {version}` already undoes later changes, HOST-HANDOFF 5.42) and does not duplicate it in state. Rows that need their own time carry an `at: Nat` column the object fills from `context.height` (the height the turn read, not the height it was admitted at, since commutative commits land later; say so on the card).

## 3. Edit algebra

`Plans.Entries<D, U>` (Plan.obend:66) gains three constructors, keeping the six that exist:

```
insert: {row: D}        upsert: {row: D}        retract: {key: Data}
```

`key` is the key projection as a record. Semantics in `applyStep` (Ops.lean:395), on a canonical relation:

| edit | key absent | key present, same row | key present, other row |
| --- | --- | --- | --- |
| insert | add | no change (idempotent) | refused `keyTaken` |
| upsert | add | no change | replace |
| retract | no change (idempotent) | remove | remove |

Commutation. `EditKind.commutes` (Ops.lean:101) gains `insert`. Two inserts of different keys commute; of the same identical row commute by idempotence; of the same key with different rests do not, and the second is `keyTaken` when `judge` re-applies on the current state (Ops.lean:1316-1319 already re-applies and re-judges there). `upsert` and `retract` are not globally commutative but commute with every concurrent change that did not touch their key: this is `rebasable` (Ops.lean:1300) lifted from fields to rows. Add `keysChangedSince w id seen field : Option (List Data)` beside `fieldsChangedSince` (Ops.lean:1275), reading the same journal steps, and extend the `judge` root rule: a moved root is accepted when every edit of it is an insert, or an upsert/retract whose key no admitted write since `seen` touched. The `rebaseOwn` restriction (own object only, 5.26) can be dropped for relations, since the row rule is sound for any root the turn wrote.

This is the OR-Set table (Shapiro, Preguiça, Baquero, Zawirski 2011) with the journal height as the unique tag, with one deliberate difference: OR-Set resolves a concurrent add and remove of the same element by add-wins, silently. Here the retract is refused `staleRoot` (transient), because every receipt names its clause and a silent no-op would not. The retractor retries against the row it now sees. Two agents raining on one bell never collide: both inserts commute, as the two appends do today (FOUNDATION §13 row 1). Two agents subscribing themselves to the Tide never collide: different keys. Two agents admitting the same anthology line collide exactly once and the receipt says why.

Bloom^L (Conway, Marczak, Alvaro, Hellerstein, Maier 2012) is the reference for which aggregates stay coordination-free: monotone ones (count up, max, set union) do; `retract` is the non-monotone step and is where coordination, here the root check, is required. Dedalus (Alvaro et al. 2011) says the same from the other side: deletion is non-persistence to the next timestep, and anything that must survive deletion is a separate persisted relation. §5 uses that.

Index forms (`amend {index}`, `remove {index}`) go when the objects stop using them, as Plan.obend already says.

## 4. Queries in Bend

Queries are pure functions over `Relation<T>` in `Relation.obend`, over the `Lists` that exist: `where(rel, p)`, `project(rel, f)`, `count`, `exists`, `lookup(rel, key)`, `group(rel, keyOf)` (the relation is sorted, so a group is a run), `order(rel, by)`. The one thing the canonical form buys that lists do not: `joinOn(left, right, keyOf)` as a merge over two sorted relations, O(n+m) ticks rather than O(n·m). Numbers: a Bell card of 1,025 rains costs 76,106 ticks against a default budget of 100,000 (OBJECTS-HANDOFF §2; Limits.lean:14), so a nested-loop join of two hundred-row relations is the whole turn and a merge join of them is a few thousand ticks.

Sugar. None now. `write {rains: insert row}` falls out of the existing `write` atom (KERNEL-HANDOFF §11, "write {field: op value}") once the parser knows the three constructor names; that is a one-line table change in `ObjectiveBendParse`. A comprehension syntax would lower to these calls and move no receipt (FOUNDATION §13a), and can wait until an object is written that reads worse without it. Eve's `search/bind/commit` blocks (Granger, 2015-2018) and Cell's relational automata (cell-lang.net, 2017) are the shapes to copy if it comes; both are query-then-edit over records, which is what a method body already is.

## 5. Laws over relations

One-line fragment (`ObjectiveBendLaw.lean:13-16` grammar; `Law.lean` denotes). Three additions, each the relational form of an atom that exists:

- `insertOnly(F)`: new ⊇ old by key, and every old row unchanged. The `appendOnly(F)` of relations; `appendOnly` (Law.lean:133) stays for lists.
- `count(new.F) <= INT` and `count(new.F) <= count(old.F) + INT`: a `LawRef.count field`, denoted as a number.
- `REF in new.F.COL`: membership of `request.subject`/`request.caller` in a column of a relation of records, generalizing `member` (ObjectiveBendLaw.lean:312; Law.lean:144), which today reads a `List<String>`.

Kernel compile of the new atoms is `Pred.any []`, as `appendOnly` and `member` already are (the host judges them); grammar is the kernel lane's file, denotation the host's. `forall`/`exists` over rows do not belong in the one-liner: they are printed on the card and decide the metarule (FOUNDATION §13), and a quantifier is where readability ends. They are the Bend predicate's, which already receives `old`, `new`, `request` and declared reads (HOST-HANDOFF 5.20).

History. With an `at` column, "no principal rains twice in an hour" is one line of the predicate:

```
count(where(new.rains, fn r: r.author == request.context.principal && r.at + 60n > request.context.height)) <= 1n
```

No journal access; the relation carries its times. What the predicate cannot see is a retracted row: state holds no tombstones, and `judge` has no journal read (and §13 refused one). The rule, from Dedalus: what must be remembered past retraction is a second insert-only relation (`strikes`, never retracted), bounded by `count` if it must be. Retraction under replay is a step like `removeItem` today, key-addressed, deterministic; `judge` re-applies it on replay as on first run (Ops.lean:1310), and `keysChangedSince` reads the same entries.

## 6. Cross-object reads

`view` answers in the viewer's own `Response<S, R>` state type (Plan.obend:126, `viewed {version, state: S}`), which is why a Bell cannot view the Directory and why `viewData`/`viewDataField` exist (HOST-HANDOFF 5.40). With relations, most of what one object wants of another is one relation of a library row type: `Relation<Card.Observer>`, `Relation<Card.Doorway>`, `Relation<Events.Event>`, `Relation<Plans.Reference>` (presence). Add one Plan:

```
viewField: {object: Reference, field: String}  ->  viewed {version, state: S}
```

answered when the target's declared field type canonically equals the viewer's `S` (`canonicalTy`, as 5.18 compares state types), else `refused {clause: typeMismatch}`; read authority and root as `view` (`recordRoot`, TurnLoop.lean:146). Thing already views `Place.State` whole (Thing.obend:247) and would view `Relation<Plans.Reference>` at `things` instead, importing no Place. `viewData` stays for the Workshop, which genuinely wants anything.

Joins across objects are views plus Bend, not a Plan. A `query {object, relation}` Plan is a query language in the host, a second kernel (§13's refusal); the host would have to budget, replay and journal it. Two `viewField`s record two roots and the commit rule holds; the join runs under the turn's ticks.

## 7. Wakes as rules

Today `On.writes {object, field, above}` fires on `{field, value: Nat}` (Wake.obend:19, 104-106), which Garden broadcasts after a planting. Generalize the observed side and the trigger:

- Observed object: after a write of relation `F`, `Card.notifyRows(observers, "F", inserted)` sends `{field: "F", rows: Data}` with the inserted rows (a convention, as `broadcast` is, Card.obend:352).
- Trigger: `On.rows {object, field, where: Lists.List<{column: String, equals: Data}>, atLeast: Nat}`; `Wake.rows` matches each delivered row against the equalities (first-order, by canonical bytes) and fires the action when at least `atLeast` match. Action stays `call {card, method}`/`notify`.

That is Realtalk's `When (pattern) ... Wish (action)` with the pattern restricted to equalities on columns, which is what Realtalk's matching over claims mostly is in practice and what a trigger stored as data can be: closures cannot sit in state, so the `when` is a pattern, not a Bend predicate. A Wake that needs a join or arithmetic is a layer over Wake (`reprogram {mode: extend}`, 5.18) with the predicate in code; say that on its card.

## 8. Cards as views, spells as edits

Where `render` shows rows of one relation with their key columns, a spell that names the key columns and one settable column is an `upsert` and needs no hand-written put-back. Relational lenses (Bohannon, Pierce, Vaughan 2006) give this for select/project with the key kept; edit lenses (Hofmann, Pierce, Wagner 2012) say the put-back should be of the edit, not the state, which is what a spell is. Concretely, beside `Form.Lens<E>` (Form.obend:28):

```
sum RowLens<E>:
  row: {relation: String, keys: Form.Fields, settable: Form.Fields, put: Spell.Entries -> E}
```

`Card.answerLensed` gains `delvetalk <card> set / <key>: … / <column>: …` through it; `?` lists it. Derivable: Tide's subscription (key `who` is the speaker; `every`, `note` settable), Directory doors (key `label`), a bell's doors, an anthology line's status for the owner. Hand-written, and stays so: plant (a create), Thing custody (a protocol with offers and the clock), Deal countersign (a key-constrained insert whose refusal needs a reading), anything whose card joins.

## 9. Migration

Relations first, with keys (the key states the invariant the code checks today):

| object | field | key | replaces |
| --- | --- | --- | --- |
| Bell | rains | {author, at} | append (Bell.obend:54, 112); duplicates collapse |
| Tide | subs | {who} | find-then-amendItem (Tide.obend:94); `ownSubs` (42-51) becomes "changed keys == principal" |
| Directory | greeted | {principal} | append + `appendOnly` (Directory.obend:48) → `insertOnly`; a repeat greeting is idempotent |
| Directory | doors | {label} | position + removeItem (57, 70) |
| Anthology | proposals | {author, at} | amendItem of the whole row (61, 94) → upsert of `status` |
| Garden | pending | {principal} | the one-per-principal rule becomes the key (388, 401) |
| Garden | children | {object} | append |
| Env | buffer | {at, actor, uri} | removeItem oldest (65): retract `min key` |
| Place | present, things | {object} | indexOf + removeItem (116-147) |
| Place | traces | {at, who, action} | drop-oldest (93) |
| Deal | signatures | {principal} | `appendOnly` (48) → `insertOnly`; once-per-party is the key |
| all | observers, doors | {object, method}, {label} | Card.observing/dooring |

Stays a record: Counter; Policy `model`, `escalate`, `system`, `confirmFor` (a tiny set, not worth a key); Garden `planted`, `owner`, `policy`, `pageCheckpoint`; Env `seen`; Tide `ticks`, `last`, `gap`; Deal `terms`, `piece`, `closed`, `withdrawn`; Thing entirely (custody is scalars under a protocol law, Thing.obend:58).

Pins. Every object source changes, so every pin moves, by the rule that only a source change moves one (HOST-HANDOFF, "Pins are sources"). `tests/fixtures/pins/artifacts.json` is re-recorded once from the foundation binary after the objects land (KERNEL-HANDOFF §11). No deployed journal exists before launch; genesis reseeds. Had one existed, each object would take a `reprogram` with a named pure migration (`List<T>` to canonical `Relation<T>`: sort, dedupe) judged by its law, as 5.18 allows.

Tests. New `tests/test_relation.py`: canonical form (unsorted seed canonicalizes; duplicate key refused), the nine cells of the §3 table, each commutation pair as two turns against a moved root (both admitted, or the second refused by name), adversarial: two inserts of one key with different rests. `test_law.py`: `#guard`s for `insertOnly`, `count`, column membership. `test_view_data.py` gains `viewField` cases including a type mismatch. Each object's suite keeps its scenarios; the rehearsal gate (FOUNDATION §14) is unchanged and is the acceptance.

Lanes, disjoint files, four days; the wire names in this document are the contract, so no lane waits on another's file.

Day 1. Host: `EditKind` insert/upsert/retract, `applyStep` table, `Relation.canonical`, creation check, `test_relation.py` cells (Ops.lean, Store.lean refusal classes). Objects: `Relation.obend` pure library, Plan.obend constructors, `relations()` in Bell and Tide, Bell migrated (Bell.obend, Plan.obend, Relation.obend). Kernel: grammar constructors `insertOnly`, `count`, column `member` parse with refusals by name, and the three names in the `write` atom (ObjectiveBendLaw.lean, ObjectiveBendParse.lean, test_sugar.py).

Day 2. Host: `keysChangedSince`, `judge` row rule, `commutes` gains insert, commutation tests; `Law.lean` denotation of the new atoms and `#guard`s. Objects: Tide, Directory, Anthology, Deal; `Card.notifyRows`. Kernel: `relations()` listed in the artifact beside `law.reads` (Package.lean), so the host reads it without compiling a def per object.

Day 3. Host: `viewField` (TurnLoop.lean, `answer`), `test_view_field`. Objects: Env, Place, Garden; Wake `On.rows`; Thing views `Relation<Plans.Reference>`.

Day 4. Objects: `RowLens`, `Card.answerLensed` row form, Tide and Directory lenses. Root: pins re-recorded from the foundation binary, full `make check`, rehearsal run; FOUNDATION §3 and §13 rows updated.

## 10. What this does not buy, and the risks

Not bought: a query language, incremental views, time travel in state, cross-object transactions beyond what `call` gives. Differential dataflow (McSherry, Murray, Isaacs, Isard 2013; Materialize) would re-render cards incrementally; a card here shows at most eight rows and a count (`Card.clipped`, Card.obend:379), rendering is a single pass under the budget, and the maintained view would be derived state the host owns across turns, which FOUNDATION §2 keeps out of the store. Not worth it at town scale; revisit if a card ever costs more than its turn. Dolt and TerminusDB version whole relations with branches; the journal plus `world-fork` (5.41) is that already, at the world rather than the relation.

Risks, named:

- Budget. Nested-loop joins exhaust a turn at about 100×100 rows; `joinOn` over canonical order is the remedy and must be the documented idiom. Canonicalization in the host is a sort per write, O(n log n) in Lean, bounded by `maxStateBytes`.
- Retraction. No tombstones; a law cannot see what was retracted. The insert-only companion relation is the pattern and must be taught, or someone will write a law that looks right and admits a retract-then-reinsert.
- Replay. `keysChangedSince` scans the object's entries since `seen`, the cost `fieldsChangedSince` pays today; a root left unread for thousands of heights pays proportionally. Snapshots are unaffected (state CIDs still hash the canonical state).
- Keys chosen wrong are a migration. `{author, at}` on rains collapses a principal's two rains in one turn; if that matters, add an ordinal column. Decide per object on day 1, in the table above.
- Proof debt. Untouched: every kernel theorem (`Data`, `conformsFuel_sound`, checkpoint round trips, the collector, `lawTable_names`); relations are data the kernel already admits. New obligations, all host-side and small: `Relation.canonical` is idempotent and order-independent; `insert` commutes on canonical relations (restating Mini's `add_writes_commute`, FOUNDATION §13, for sets); the `applyStep` cases; `Law.denote` `#guard`s. Nothing in `Theory/` moves. The commutative-root rule has no Lean theorem today beyond those guards; it gains none here, and that is the honest state of it.

Before or after launch. Land §2 and §3 before launch: `Relation<T>` canonical, the three edits, `insert` commuting, the row-rebase rule, `insertOnly`, and the objects whose lists are plainly keyed (Bell, Tide, Directory, Anthology, Garden.pending, Deal). Reason: these change the wire shape of state and every pin, and after launch each would be a per-object migration with two dialects of `writes[].edits` in the journal for good (Plan.obend already carries one "for one release" compatibility, the index forms). Everything in §6 to §8 is additive, a new Plan, a library sum, a lens kind, and moves no state shape; it can follow at the pace of the objects that want it, and `viewField` and `On.rows` are the first two. Four days against a green gate, the gate itself unchanged, is the cost; the alternative is carrying the list-and-index model into the journal of the world that launches.

Unresolved from the brief: I could not place "Fafnir" as a named system in the incremental-view literature or in this tree; Materialize carries that point.

## 11. Scale, decided 2026-10-10

The unit of load is the object: a turn materialises the whole state, and a
relation left to grow costs every turn on that object a linear load before any
work. Four mitigations, the first three landing with the slice:

1. Every relation declares `limit: Nat` in its `Decl` (0 means the host default
   of 4,096 rows) with `dropOldest` retention by key order, enforced by
   `Relation.canonical` after every write; growth is a stated decision.
2. The host trusts its own stored state and does not re-run `conformsUnder` on
   it per turn; only arguments arriving from outside are checked.
3. An unbounded collection is a sequence of child objects (`anthology/page/n`),
   the current one small and the rest closed; never one relation.
4. After launch: lazy state cells, so a method that reads a count never
   materialises the rows.

Bounds that go with them: subscribers per object 64, `changed` deliveries
under the per-turn send bound, a per-object index of height to keys touched so
`keysChangedSince` is constant.

## 12. Corrections from the first migration (2026-10-10)

- Canonical order sorts the key projection by its DAG-CBOR bytes, which puts
  the shorter column name first: `{author, at, n}` orders by `n`, then `at`,
  then `author`. Objects that need arrival order keep an explicit position
  column (the Directory's `place`).
- A merge join of two 200-row relations costs about 188,000 ticks with
  `canonicalCompare`, two orders of magnitude above §4's estimate; a card that
  joins should join bounded relations or precompute.
- Wake patterns compare a column against a `Relations.Cell` (a natural or a
  text), not against `Data`, since Bend cannot read `Data`; observers receive
  rows as `Card.Row`.
- Rows are records: a relation of principals is `Greeting {principal}`, not a
  bare text.
- A per-turn ordinal from the count at read time does not separate two
  concurrent turns by one author at one read height; no current object needs
  that, and one that does should key by the receipt's intent.
- `insertOnly` is a law atom the host denotes (Deal's `signatures`, the
  Directory's `greeted`); a row the declared retention evicts is a fact of the
  write and does not count.
