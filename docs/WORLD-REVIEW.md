# World review

`world/` at foundation 8a4b141, before the Wholeness object migration (objects7) lands. Ranked by harm. Each item: where, smell, smallest fix. Items the migration erases are listed at the end and not counted. Verified on hbox with the foundation binary: items 1, 3 and 10.

## Status after the review lane (lane/review, 2026-10-10)

The findings below are as written at 8a4b141; this section says what became of each. `world/` was
5,987 lines at foundation 79e91f0 and is 5,505 after the lane (objects 3,941 to 3,554, libraries
2,046 to 1,951); after the external review's belt and card budgets it is 5,655 (objects 3,738, libraries
1,917, foundation 57b6b81). Commits are named by group (A to P) on lane/review.

**Landed in world/.**
- 2 Cards by characters: `Card.clipped` keeps at most 1,200 characters (`Card.budget`; A), and
  `Card.clippedWithin` what a long head leaves (the Policy, I); Spween refuses a passage over 600 (B).
- 3, object side: the Workshop's `check`/`propose` take `source` fields (`Form.Kind.source`, a
  `form` block line since kernel8; 44c3d14, L); the Anthology's `admit {number}` already agreed.
- 4 The Seed ritual is gone; `initial()` is the State (O). Only the Appointment keeps the `Seed` its
  book types.
- 5 Every hand-written `Edits`/`keep()` is gone now that the kernel derives them (kernel9; O). Bell,
  Appointment and Seat (Seats.State), which have no law to say which fields never change, mark them
  `fixed` in the State (objects10): no edit of their own names them. Lawful objects
  whose fields were read-only by omission say it in law: Scene and Table `law fixed`, Tide `law gap`.
  The Appointment's action `keep` is `wait`, so the name no longer shadows `keep()` (N).
- 6 One `refusal(w) -> Card.Refusal` match: Deal (D), Garden (E), Wake (G), Policy (I), Tide (J).
- 7 Clauses on every refusal: Directory (C), Env (G), Workshop, whose successes are their own cases
  (L), Seats, Table, Appointment (N).
- 9 Policy's law no longer admits a `describe` it lacks (I); the Cistern's blurb says it keeps the
  newest first (E). Deal's and Thing's readings were fixed by the migration.
- 10 The Directory's Bend 4,096 check is gone: the host counts a retention-dropped row as kept
  (5.74; 44c3d14). `insertedOnly` went with the deletion pass.
- 11 The Wake's Bend `law` is gone (G).
- 12 Bounded relations: Scene `left` {at, who} 64 (B), Cistern `entries` 256 (E), Door `knocks` 64
  (F), Workshop `held` 16 (L); Avatar's inbox was migrated.
- 13 The Directory learns its doors in one pass a turn; `words`/`fields` and their law terms are gone (C).
- 14 `world/lib/Text.obend` (A), with Spween (B), Directory (C), Wake (G), Tide's `%` (J), Anthology's
  `Lists.at` (K) and the Workshop's `cat` (L); the Workshop's fence reading is the host's (44c3d14).
- 15 `Rows.Presence` keyed {who} for Scene (B) and Commons (M).
- 16 Garden's duplicate `publish` is gone beside `publishPage` (E); the host publishes the default page.
- 19 The Cistern declares its relation (E); no empty `relations()` remains.
- 21 A sensed row is the event extended with its `n` (G).
- 22 Dead code: Document's seven unused variants and `Capture`, `Encounter.obend`, `Phrasebook.obend`,
  Abi's three records, Card's door forms (A).
- 23 Stale FOUNDATION citations (A), the 24 render comments (O), and the State-first comments.
- 24 Scene ops are `sum Op` and `sum Test` (B).
- 25 One constant per cap: Garden `pendingMax` (E), Tide `subsMax` (J), Commons `presenceMax` and
  `namesMax` (M).
- Also: `Interpreted.denied` (host's empty payload) is refused `policy` by Garden and Directory;
  VOICE.md's card texts and six readings (P).

**Landed in another lane.** 1 (declared methods, host10 5.62), 3 (bounds from the form, host10 5.69),
5 (derivation, kernel9), 8 (readings in `Verdict.refused`, host 5.67), 16 (default page, host10
5.68), 17 (gone with the migration), 18 (PLAY is not a door), 19 (relations read from the artifact,
host11), 20 (Place's law through `Places.obend`, objects9).

**Dropped.** 15 for Place: its `present` relation holds the avatars standing in it (references), not
principals at named spots, so it is not the Presence relation. 21's "give `Event` an `n`": the
transport publishes Events without one, so the row type stays the event plus `n`. 5's last step (the
three hand-written pairs) waits on a way to say "never changes" without a law.

**Open.** Kernel9's second commit (forms derived from `form` blocks) will let every hand-written
`forms()` go. Bell's `colour`, `seed` and planting, the Appointment's topic and target, and a Seat's
table and players are kept by their hand-written Edits alone.

## Findings

1. **Every def whose first parameter is the State is a public method** (convention; Package.lean:134, TurnLoop.lean:615 compiles any such def by name). A stranger declared South the winner with `Table.played` (Table.obend:56), reset a seat with `Seat.nextRound` (Seat.obend:74, skipping `next`'s table check), and kept an appointment early with `Appointment.due` (Appointment.obend:49). `Thing.carried` (Thing.obend:138) hands an unheld thing to any `by`; the law admits a pickup from nobody. Usage cards offer `render` and `publishPage` as spells. Fix: the host runs only declared methods (`def methods()`, or the `form` names plus `receive`/`changed`). objects7's "State second" convention fixes only the files it touches. The migration makes this worse: methodForms turns every such def into a spell.
2. **Cards pass 1,400 characters** (card). `Card.clipped` (Card.obend:398) counts lines, not characters: Bell:147 (8 rains × 280), Anthology:120, Avatar:359 (8 notes × 280), Policy:208 (no clip: 16 examples, 16 macros and a 520-character teaching text), Scene:242 (passage text unbounded; Spween:222 sets no limit). Fix: clip by `Document.size` to a 1,200 budget; Spween refuses a passage over 600.
3. **`form` bounds are dead in the message dialect** (duplication). The host fits spells against method input types (TurnLoop.lean:419-438: text 0..1400, natural 0..10⁹): a 300-character `line` passed `form drop: line: text 1..140`. Anthology:80 offers `admit {number}` (from 1) but the method takes `admit {index}` (from 0). Fix: the host reads bounds from the `form` of the same name, and the field names must agree. The migration creates this smell; it does not erase it.
4. **The Seed ritual** (dead code; 228 lines across 24 objects): `record Seed`, `defaultSeed`, `seeded` and `initial = seeded(defaultSeed())`. The host lays a partial record over `initial()` (Plan.obend:29-33), and no world code calls `seeded`. Only tests/test_objects.py:255 requires the ritual. Thirteen copies of "seeded makes the child's State from it" are false. Fix: keep only `initial()`; keep `Seed` where a creator types one (Appointment.Seed).
5. **`Edits` and `keep()` mirror the State** (duplication; 139 lines). Objects without `keep()` hand-write full edit records at 17 sites (Counter:25, Lantern:27, Loop:23, Anthology:56/74/98/107, Appointment:50/58, Appointments:38, Cistern:28, Seat:75, Table:57, Wake:102, …), because `write {…}` needs `keep()`. Fix: the kernel derives `Edits`/`keep()` from the State, and `unchanged(F)` makes a field read-only. The migration's mechanical `world.write(…)` keeps the smell.
6. **Parallel `why`/`clause` matches** (duplication; 118 lines): Thing:83-110, Garden:213-236, Policy:64-81, Place:46-61, Wake:83-94, Tide:80-87, Deal:79-90. Fix: one `refusal(w) -> Card.Refusal` match per object.
7. **Refusals without a clause** (refusal): `{reason}` in Seats.obend:22, Table:43, Env:71, Appointment:38, Directory:55/123, Card:338, Avatar:41 (`movedReply` invents `notMoved`), and Workshop's `Verdict.refused {reason}`, which also carries successes ("withdrawn" :163, "usage" :206). Fix: `Card.Refusal` everywhere.
8. **Predicate clauses have no reading** (law): the Bend `law` clauses `tooSoon`/`self` (Tide:42), `noOffer`/`notOffered`/`expired` (Thing:67), `cooldown` (Scene:64), `signed` (Deal:55) and `greeted` (Directory:64) reach the receipt without the `reason` that law-text clauses get (Ops.lean:920). Fix: `Abi.Verdict.refused {clause, reading}`, which the host copies into `reason`.
9. **Readings and blurbs that lie** (law): Policy:51 "anyone may describe" (Policy has no `describe`); Deal:46 "writeOnce reads naturals only" (Law.lean's writeOnce reads any type); Thing:58's reading omits `copyable`; Cistern:34 "refusals first" (it keeps arrival order). Fix the texts.
10. **Stale `TODO(insertOnly)`** (dead code). The host denotes the atom (Law.lean:163, #guards 273-277). Deal:52-55, Directory:61-64 and `Relations.insertedOnly` (Relation.obend:152-166) can go; write `law signed "…": insertOnly(signatures)` instead. Trap, verified: insertOnly with a `limit` refuses every insert past the limit, so Directory's `greeted` keeps its Bend 4,096 check.
11. **Wake's Bend `law` is dead** (dead code; Wake:61-64). The law text already refuses every non-owner write, and "stubbed until the host runs it" is stale. Delete it.
12. **Hand-rolled drop-oldest and unbounded lists** (hand-rolled): Scene:174-180 (`left`), Workshop:130-138 (`held`), Avatar:68-74 (`inbox`); Door:16 `knocks` and Cistern:9 `entries` grow forever. Fix: relations with `limit`.
13. **The Directory walks its doors six times** (duplication; Directory:173, 208, 266, 277, 302, 350, each a recursion over `inspect`). It keeps `words`/`fields` as space-joined strings (:37-38) and re-splits them every turn. Fix: one learning pass into `Relation<Learned {label, action, field}>`.
14. **Text helpers written several times** (library): substring search ×3 (Card:244, Wake:216, Spween:47); trim-end ×4 (Spell:63, Card:577, Directory:153, Spween:224); nth ×2 (Anthology:63, Directory:336); fenced block ×2 (Workshop:53, Spween:31). `Workshop.cat` (:64) is interpolation and `Tide.remainder` (:113) is `%`. Fix: `world/lib/Text.obend`.
15. **Presence written three ways** (library): Commons:29 and Scene:25 share a `Presence {who, at}` list with the same `here()` (Commons:80, Scene:76); Place:31 keeps a relation of references. Fix: one `Presence` relation keyed {who} in Rows.obend.
16. **`publishPage` pasted five times** (duplication): Anthology:85, Scene:194, Table:68, Tide:141, Workshop:212; Garden also has `publish` (:143). Fix: the host publishes `render` plus usage as it serves `card`, and Garden overrides `page`.
17. **`law: "Bell"` and `law: "Cistern"` are ignored** (string; Garden:97, 163, 423). The host reads a law only from text that starts with `law ` (TurnLoop.lean:374). The cistern create is duplicated (`cistern` :96, `digging2` :162). Fix: `law: ""` and one create.
18. **PLAY cannot be played** (dead door). The genesis table seats nobody (genesis.py:84); Table's Edits cannot set seats, and Seat offers no forms. Fix: a `sit` method that creates `play/seat/0|1`, or remove the door.
19. **`relations()` that declare nothing** (host workaround): Cistern:24, Thing:53, Avatar:53. Fix in the host: an absent `relations()` means none.
20. **Place has no law** (convention; Place:13). Thing and Avatar import Place's types, so its guards exist only in code. Fix: move State, Done, Trace and Exit to Rows.obend; then Place declares `law owner`.
21. **`Env.Sensed` copies `Events.Event`** (duplication; Env:19-28, with `sensed`/`eventOf`; `eventOf` is dead). Fix: give `Event` an `n` field.
22. **Dead code** (dead): Directory.words:388 (which is also a method), Card.valueNatural:302, Abi.Event/StringField/NatField (Abi:19-31), Encounter.childrenRemove/childrenOffer, all of Phrasebook.obend (nothing imports it), and seven Document variants that no object builds (objects use only `text`/`sequence`).
23. **Repeated and stale comments** (comment): "The card as the reader in the context sees it…" ×24 above `render`; misplaced blocks at Plan.obend:123-129 and :199-201; stale citations FOUNDATION §13 (Form:23, Abi:34), §4 (Card:426, 443), §16 (Plan:128, Garden:115, Place:181).
24. **Scene ops are strings** (string; Scenes.obend:13-20): `op` holds "set"/"add"/"sub"/">="/"truthy"/…, and `holdsClause`/`applied` compare strings. Fix: `sum Op` and `sum Test`.
25. **Caps stated twice, differently** (string/number): Tide declares `limit: 1024` (:62) but caps at 64 in Bend (:105) and says "sixty-four" (:83). Garden's pending caps (:76, :405, :418) and Directory's greeted caps (:74, :401) repeat the same pattern. Fix: one constant per cap.

**Erased by the migration, not counted:** `receive`/`heard`/`then` triples (43 defs, 21 identity continuations, `same`), doubled act paths (Bell `rained`/`rainedCard`, Anthology `submitted`/`submittedCard`, Avatar's two accept chains), the observers convention (Card:322-378 and five objects' observe/broadcast), `route`/`withBare`/`fitting`, Spell.obend's parser, 48 `type Plan/Response` lines, Workshop's own spell reading, Wake's three firing loops, and Garden's `colourNamed` (host9 reads words as cases). Absent smells: no `::<T>` anywhere in `world/`, no method over 14 lines, every law-text clause has a reading.

**Tally:** duplication 6, dead code 4, string 3, convention 2, library 2, law 2, card 1, refusal 1, hand-rolled 1, comment 1, dead door 1, host workaround 1.

## Judgment

What is compact and powerful: the substrate. One host contract, typed first-order data, and a law fragment a reader can parse; relations with keys, canonical order and commuting inserts; a refusal named on every receipt. Bell is about 150 lines and carries ordered keyed rains, doors, a strike that awaits another turn, and a card. Deal is a countersigning protocol whose resting state amends another object's law. Tide is a rate-limited fan-out whose own predicate guards subscriptions. These are small programs with real guarantees, and the libraries (Relation, Form, the law atoms) are the right size.

What is still bullshit: the ceremony around each object, the trust placed in conventions, and prose that drifted from the code. About a third of `world/objects` is ritual: Seed, Edits/keep, Why/clause, receive/heard/then, publishPage, the render comment. The method table trusts a naming convention, and three objects can be broken by a stranger today. Bounds, readings and caps are stated twice and disagree: forms against method inputs, Decl limits against Bend caps, law readings against the laws. Lines run past 400 characters because there is no list literal, so `forms()` and `relations()` are cons ladders. One door cannot be used at all.

The structural change that removes the most lines: **make the State the schema.** The kernel derives `Edits` and `keep()` from the State, `initial()` is the only constructor, and a method is a declared form whose `form` block is its input type and bounds. That deletes Seed/defaultSeed/seeded (228 lines), Edits/keep (139), and the duplicate form/method declarations. It makes `write {…}` usable everywhere, closes item 1, and gives item 3 one source of truth: about 400 lines from 4,163, with no change to semantics.
