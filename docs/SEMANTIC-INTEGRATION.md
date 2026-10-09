# Where meaning lives

DelveTalk reuses Mini's Bend frontend, checker and demand machine, **not its object
kernel**. Its Lean host implements a smaller, separate admission contract. Python
transports, retains and presents results. Independent C/Python/JS core evaluators
remain useful cross-checks, not production admission engines.
The separate object host is intentional: DelveTalk experiments with its own
programmable environment. Convergence with Mini is not a project requirement.

## Connected in this pass

- [Authored spells](../syntaxes/obend_spell.py) now carry real Objective Bend source.
  The pinned frontend checks it and the demand machine executes it. The examples
  use extensions, `self`, `super`, composition and `fix`; source also computes views.
  Generated JSON remains transport. The obsolete JSON spell implementations were
  removed.
- [Manual interpretation](../profiles/MANUAL-INTAKE.md) retains the original post
  and a separate operator attestation. It shares ordinary normalization, identity,
  current-law checks and admission. It is not proof that prose uniquely entails
  the action. Copyable syntax is optional.

## Priorities exposed by the review

1. **Whole Bend transitions — implemented locally.** The opt-in
   [source-transition profile](../profiles/COMPILED.md) executes one typed source
   call over state, input and host identity; its decision replaces complete state
   or refuses atomically. The [garden](../protocols/town-garden/Garden.obend) uses it.
   Compilation at installation and typed invocation do not establish permanent
   state invariants; this first profile has no outbox or allocation. Legacy
   commands remain intact. This is DelveTalk's chosen interface, not Mini's kernel.
2. **Admission contracts, not form promises.** Field types/lengths in affordances
   constrain offered requests. They do not automatically constrain raw requests:
   the text factory's unrestricted `write` can store nontext. Source types provide
   real checks, but bounds and migration invariants need explicit receiving rules.
   Management predicates currently cannot inspect proposed replacement state/code.
3. **Stable scene meaning — corrected in v2.** Spween v1 caches source-dependent string ranks in state.
   Adding an unrelated literal can change a migrated comparison. Preserve string
   text and derive ordering in the receiving program: v2 now does this, refusing
   ordering for migrated text outside its closed source domain. V1 remains explicit
   historical behavior. Source projections now check the receiving workspace's pins;
   standalone observations retain their actual runtime identity.
4. **Mechanical places.** Transaction [input origin](../profiles/TRANSACTIONS.md)
   now identifies the actual earlier result producer. Gated commons movement
   can require an immediately preceding door invocation; copied input carries no
   origin, and provenance grants no authority. Retained-event delivery and
   autonomous reactions remain a [separate future profile](RESIDENT-ACTIVITY.md).

Source `law` declarations and host grant predicates have different meanings. The
current compiler refuses source laws; integrating new-state invariants requires
explicit old/new/request checks across every write route, not a renaming.
Mini's pure declared-state and source-law judgments are possible reuse points,
if their contracts suit the chosen DelveTalk semantics. Importing them is not
an accepted migration plan.
DelveTalk does not inherit Mini's activities, protected cells, scoped nested-call
delegation, linear custody, drain/rebirth upgrades or resource accounting merely
because its own admission also runs in Lean.

Factory allocation, actor-bound work tickets, atomic desk adoption, exact replay
and compiled game execution are real receiving paths. Ticket acceptance acknowledges
review; it deliberately does not install a target. Scoped grants are not linear
custody. Finite tests, typed-core evidence and whole-host correctness remain
different claims.

The deployed checkpoint remains `2926fcb`; the new source-transition and
input-origin changes described here are not deployed there.

## Exchange with Mini

**Explore compatibility without prescribing convergence.** Reusing Mini's language
does not make DelveTalk's host a kernel subset or confer its proofs. Three examples:
DelveTalk assignments may add fields; Mini edits require existing declared fields.
DelveTalk advances a version on an empty update; Mini's keep-only return does not.
DelveTalk transactions retain one caller throughout; Mini nested calls require
explicit scoped delegation. These are design differences, not defects by themselves.

Choose each host behavior for resident use, composition, recovery and simplicity.
Share an implementation when its meaning matches; preserve separate semantics
when the experiment needs them. A future common fragment would need explicit
identity, authority, state, result, refusal and resource mappings. It would not
justify silently changing historical receipts or current programs.

Learnings can travel upstream without moving the host: source-derived affordances,
manual interpretation with explicit provenance, replayable authoring journeys,
and failures involving stale views, migration or uncertain replies. Reusable Bend
libraries and portable examples offer another exchange. Mini's methods, admission
judgments and proofs are references to study and selectively reuse, not a checklist
of facilities DelveTalk must acquire.

Python cleanup is independent: remove duplicate workflow machinery and put authored
behavior into Bend where that clarifies the system. Moving a module into Mini or
another language does not itself simplify it.
