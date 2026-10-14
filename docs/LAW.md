# Law

What a law is, what each atom of its text means, and what a law will never say. The grammar is FOUNDATION §4 and the
head comment of `Compiler/ObjectiveBendLaw.lean`; `Host/Law.lean`'s `denote` is the definition of every form. Every
section ends with its decision.

## 1. What a law is

A law is an admission predicate on **one write of one object**, judged at commit on `(old, new, facts)`. It is a safety
property: it says what the new state may not be, given the old state and who asked. It says nothing about reads,
obligations or liveness. Two tiers:

**The text.** `law NAME "reading": EXPR`, one line a clause, parsed by `ObjectiveBendLaw.parse`, judged by `Law.denote`
for every kind of change (`write` 0, `reprogram` 1, `amend` 2, `proposed` 3, `rule` 4). `Facts` carries:

- `subject` (the principal, or the grantor under `via`), `caller` (the calling object, "" for the turn's own),
  `height` and `turn` (the entry's journal height), `pin`, `kind`, `method` ("" for an op), `verb` (the act's verb);
- `clock` (the world clock the turn read, in minutes) and `object` (the written object's id);
- `evicted`: rows the declared retention dropped, so `insertOnly` forgives them;
- `reads`: the state of every object the law cites, transitively through `under` and `wants`, recorded as roots;
- `wants`: the want clauses of every object cited by `"O" wants N`;
- `standing`: per object, its count of law clauses (`request.laws`) and of writes its law refused
  (`request.refusedBy`).

**The predicate.** `def law(old, new, request: Abi.Request) -> Abi.Verdict`, run under `Bounds.lawTicks` (100,000) after
the text admits a write of kind 0 or 3, or a placing (4). `Request` is `{context, method, argument, kind, pin, reads}`;
`reads` are the states of the objects `lawReads()` names, added to the turn's roots (within `maxRoots`, viewable by the
subject, else `lawRefused lawReads`). An object with a predicate also has its write arguments journaled
(`writtenFields`), so its entries are larger.

**The metarule.** `amendable`: a law is accepted at creation, amendment and reprogram only if it admits a kind-2
amendment by its proposer. An amendment by the world's opener is admitted whatever the law says, and the opener's own
amendments skip the dry run (ROOT §2.1, `openerAmends`). The default law of a lawless package is `owner: request.kind ==
0 or request.kind == rule or request.subject == "<creator>"`.

Beside the law the host refuses by rules that are not law: `fixed` fields, relation keys and limits, grants (`noGrant`,
`grantSpent`, `notGrantor`), the read policy, `quiet`, allocation shares; `retire` is an amendment.

**Decision:** one thing: a per-write safety predicate with a metarule. The text is what the cards print; the predicate
is where everything the text cannot say is paid for.

## 2. Whose it is

Laws say what may not happen to one thing. Rules and wants make things happen and pose (judged at commit, FOUNDATION
§10). Grants lend (`via`, `until`, `uses`). Bonds agree (a countersigned amendment, applied by the bond with itself as
caller). Read policy hides. Root overrides.

| Want | In law? | Whose it is |
| --- | --- | --- |
| rows changed by this write belong to the requester | yes | law (§4 B) |
| a clock comparison | yes: the clock is a journaled input, deterministic on replay | law (§4 A) |
| a filtered count, a quorum over a relation | yes: properties of `new` alone | law (§4 C, G) |
| `old.F` with arithmetic | yes | law (§4 E) |
| cross-object membership | yes, by reference, the object a root | law (§4 D) |
| a law shared by reference | yes | law (§4 F) |
| who may read | no: reads are authority, not writes (FOUNDATION §8 invariant 12) | read policy |
| what must happen; a review due; a period | no: a law is judged at one commit; a future is a rule on the tide, a want, `awaitUntil` or a supervisor's `ended` | rules, wants |
| a per-principal rate | no | host quotas (`interpretQuota`, `modelQuota`, `quiet`) |
| a procedure of amendment | no: the procedure is a bond's code; the law states its rest by a quorum | bond + law |
| a constraint joining two objects' states | no, beyond membership and a cited field: a second object is a root, and a moved root is `staleRoot` | predicate |
| the model's proposals | no: a proposal is never authority (FOUNDATION §6); asking first is `confirmFor` | Policy |
| the argument of the write | no, for the text: the predicate reads it and pays by journaling it | predicate |

**Decision:** six needs are the law's; the rest belong to another mechanism and stay there.

## 4. The atoms

Each atom is the host's to judge (`Law.denote`); the grammar is one term language (KERNEL-HANDOFF §11). Every atom is
linear in the rows of one write, and anything read elsewhere is a root.

**A. `request.clock`.** The world clock the turn read, in minutes. No root: the clock is a journaled input, re-derived
by replay at every height. METAPHYSICS's `alive` reads `request.method == "tend" or request.clock <= old.tended + 1440`,
with `tend` writing the clock.

**B. `changed(new.F.COL) by TERM`** (`request.subject`, `request.caller`, or a field). The rows of `old` absent from
`new` and the rows of `new` absent from `old`, compared whole by canonical bytes, less `evicted`: every such row's `COL`
canons to the term. At creation every row counts. An upsert that replaces a row contributes both rows, so you may only
replace your own with your own. No root; O(rows). A register: `changed(new.lines.author) by request.subject`, so a row's
author is the law's, not the method's; kind/bond: `changed(new.marks.who) by request.subject`, a party signs only for
themselves.

**C. Filtered counts.** `count(SIDE.F where COL == TERM [and COL == TERM …])`: rows meeting every test, with canonical
equality and the same term reads as a single test. Names, citations and clock dependencies include every predicate; work
charges each predicate's row walk and value read, inside the clause budget. SEEDING folkway 3 is `count(new.lines where
author == request.subject) <= 1`; `count(new.F where C == V) <= count(old.F where C == V) + 1` is a growth bound. Bell
wants and the seventh-rain rule count the rain domain (`verb == "rain"`), so a grown gesture supplies no completion
evidence for a rain want.

**G. The quorum** is a comparison of counts: `count(new.members) <= count(new.votes where vote == "yes") + 0`.

**D. `REF in "<object>".F.COL`** (and `"<object>".F`, `REF in "<object>".F`): membership read in another object, at the
version the write's turn read, recorded as a root and journaled so replay re-judges from it. An absent or unviewable
object reads false. A write racing a change to the circle is `staleRoot`, transient. Circles that own things: `law
circle "the circle changes it": request.subject in "circle/porch".members.principal`; keepers named by a bond:
`request.subject in "<bond>".marks.who`.

**E. `old.F` as a reference**, and `TERM + TERM`. At creation `old.F` reads the empty value of `new.F`'s type. A tide's
pacing: `new.ticks <= old.ticks or old.last + old.gap <= request.clock`.

**F. `under "<object>"`: a law by reference.** The cited object's text at its version, conjoined and judged with this
write's `facts`, `old`, `new`; depth bounded (`Limits.lawDepth`, 4; at depth 0 an `under` is false, so a cycle ends).
Root: the cited object at its version, so amending the shared law moves every dependent's root and re-laws every
instance at once. The citation is conjoined with the citing thing's own text, which holds its owner's law, and an
`under` atom holds of an amendment by the citing thing's owner (`Law.ownerAmends`): a cited law adds to a thing and
binds it while it follows, but never takes it from its owner (FOUNDATION §4 Tenure).

**H. `request.object`**, the written object's id: `request.subject == request.object` says a thing writes only itself.

**The rest of the term language.** `request.verb`; `request.laws` and `request.refusedBy` (what the object stands at);
`==`, `!=`, `<`, `<=`, `>`, `>=` (`A != B` holds only when both sides read and differ, where `not (A == B)` is true on
an unreadable side); `TERM % INT`, the remainder by a positive integer; `"O" wants NAME`; `changed(TERM)` (§8).

**Decision:** these atoms, and no other kind: none adds a language, a loop, or a read the host does not already make.

## 5. What not to add

- **A solver, or relational laws by one.** A second kernel.
- **Datalog or a query language over the journal.** The predicate with declared reads says the same under the same
  budget; D gives the text the one query it needs, membership at a version.
- **Obligations in laws.** A law is judged at one commit and can only refuse; "must happen by" is a future, and a
  future that fails needs a receipt of its own, which is a rule, `awaitUntil` or `ended`. A law that could promise
  would be a law that could lie.
- **Laws over reads.** Reads are under the read policy; a judged read would make every `view` a turn with a budget and
  an entry. If the read policy grows, it grows as a field with lenses, not a tier.
- **Nested paths `new.a.b`.** The fix is flat state (`holder: String`) or the predicate, not a path grammar whose
  aliasing `plainName` was written to exclude.
- **Literal text lists** `request.subject in ["a", "b"]`. A circle in a literal cannot be amended by the circle; a field
  or a cited object can.
- **Laws over arguments** in the text: the predicate has `request.argument` and pays by journaling it; the text would
  journal arguments for every object.
- **A `request.handle` fact.** Handles confer nothing.
- **Arithmetic beyond `+` and `%`.** Rates and decay are a rule's, on a tick.

**Decision:** the line is "one write, one object, linear in its rows, a root for anything read elsewhere".

## 7. The temporal layer

The two tiers are the safety fragment of a dynamic logic over single-step transitions. The programs are turns (the
protocol lines atomic; `call`, `send`, delivery and `await` the composition); a law is `[write]φ` with φ over `old`,
`new` and the request facts; admission at commit is the modality; the receipt is the proof term (clause, roots,
height); the metarule is the one sentence of meta-logic; replay is the semantics (every admitted transition re-judged);
`judge` is the modality without the commit; a fork at a height is a possible world. A rule is `[write]φ then σ`, a want
φ standing.

Refused on purpose: quantification over programs, liveness, laws over reads, two states at once beyond a cited root,
composition beyond conjunction and `under`. The step beyond it, when a town's laws want "never twice in a day" or "only
after X has happened" across more than one step, is a temporal layer over the journal: formulas over sequences of
heights, checked by replay as a proof. `old.F`, `request.clock` and insert-only relations cover the one-step cases.

**Decision:** not built; recorded so the one-step atoms are chosen with it in view.

## 8. Level conditions and transition triggers

A rule's `when` is a level condition, judged at each commit; it fires on every write while true. A bell can say either:

```
when: count(new.lines where verb == "rain") >= 1
when: changed(count(new.lines where verb == "rain"))
```

- The first fires on each write after the first rain, including a non-rain line. The second fires when the retained
  rain count changes, up or down; a count at its retention limit can stay equal despite another rain.
- The shipped bell's seventh rain is a crossing: `count(new.lines where verb == "rain") >= 7 and count(old.lines where
  verb == "rain") <= 6`.
- `changed(TERM)` takes a term, not a condition: `new.F`, a filtered count, or arithmetic with `+` and `%`. It evaluates
  the same term against the old and new state, including state references in count filters, with the equality of `==`.
  The term reads no `request.*` facts, even in filters; those refuse at parse. Explicit `old` references and cited
  objects keep their ordinary readings; cited objects are the commit's roots, not historical reads.
- Both evaluations are charged and all their fields and citations are recorded by the names walk. Missing or mistyped
  readings on either side make the atom false for a rule; no old state also makes it false.
- A want has no old state: `changed(…)` in a want refuses at parse or placing, because a want reads the thing as it
  stands.
- `changed(new.F.COL) by TERM` keeps its row-column meaning (§4 B). The `by` after the closing parenthesis selects that
  atom; without `by`, the parser reads a term, so `new.F.COL` still refuses as a nested path. Both forms print and parse
  back exactly. Level rules and transition rules use the same firing, queue and replay path.

**Decision:** level by default; a transition is said with `changed` or an explicit old/new crossing.
