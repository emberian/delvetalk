1. **Critical — Inherited rules lend the kind owner’s authority to resident-controlled code.**  
   References: [AUTHORING §4](docs/AUTHORING.md:92), [Ops.lean:2322](spec/Delvetalk/Host/Ops.lean:2322), [TurnLoop.lean:628](spec/Delvetalk/Host/TurnLoop.lean:628).  
   **Scenario:** A resident derives a bell kind and overrides `ring`. The inherited seventh-rain rule invokes that override as the original kind’s owner. The override can call other objects with that principal—for example, change `policy` when the kind owner is the opener. Target laws admitting their owner do not stop this. Ordinary resident-authored methods similarly inherit a visiting user’s authority.  
   **Fix:** Give executable behavior scoped capabilities, not the invoking principal’s ambient authority. Bind automated grants to approved targets, methods, arguments and code revisions. Scene effects that cast spells need the same boundary; the current Spween parser rejects calls, so that particular extension is not yet implemented.

2. **Critical — Live `under` lets an upstream owner revoke downstream ownership and recovery.**  
   References: [LAW §4 F](docs/LAW.md:233), [AUTHORING §4](docs/AUTHORING.md:94), [Ops.lean:1152](spec/Delvetalk/Host/Ops.lean:1152).  
   **Scenario:** Alice makes an instance under Bob’s kind. Bob subsequently changes its shared law to admit amendments only by Bob. Alice can no longer detach or repair her instance. The metarule checked Alice’s rights at creation; it does not preserve them against upstream changes—or conditions that later expire. Rejecting code `relay` as an authority inversion while allowing live replacement of authorization is inconsistent.  
   **Fix:** Preserve a local amendment/recovery right outside inherited predicates. Pin inherited behavior revisions by default; make following upstream changes an explicit, revocable delegation.

3. **Critical — Adding one custom law silently removes the default ownership protections.**  
   Reference: [Kind.obend:155](world/objects/Kind.obend:155).  
   **Scenario:** A resident supplies `law small "seven lines maximum": count(new.lines) <= 7`. Because the text contains a law, `lawFor` omits RECORD’s entire base law. The instance now lacks its normal restrictions on amendment, reprogramming, admissions and proposals. Another resident can amend or reprogram it while the count condition holds.  
   **Fix:** Treat supplied clauses as additions to an explicit base policy. Replacing that policy should be a separate operation that exposes the permissions being removed.

4. **High — Spell interpolation turns resident text into executable syntax.**  
   References: [FOUNDATION §4](docs/FOUNDATION.md:378), [Law.lean:477](spec/Delvetalk/Host/Law.lean:477).  
   **Scenario:** An owner’s rule includes `then delvetalk me note / text: {new.message}`. A resident-controlled `message` contains a newline followed by another `delvetalk` command. `Law.fill` concatenates it verbatim, and the result is parsed as spell syntax under the rule owner’s authority. Checking that a hole names a valid field does not prevent this.  
   **Fix:** Compile the spell into a typed command with argument holes. Fill values without reparsing them as commands; validate target and method substitutions separately.

5. **High — The self-ticking tide is a finite causal chain.**  
   References: [Tide.obend:60](world/objects/Tide.obend:60), [Ops.lean:3633](spec/Delvetalk/Host/Ops.lean:3633), [TurnLoop.lean:3699](spec/Delvetalk/Host/TurnLoop.lean:3699).  
   **Scenario:** Each `tick` sends `due`; the resumed `due` sends the next `tick`. Suspension preserves the ledger, and each completed generation decrements it. With depth 100, this stops after roughly fifty hourly cycles, potentially earlier through work or storage exhaustion. Weather and fronts then stop with it.  
   **Fix:** Represent recurring schedules as persistent, authorized registrations. Each due period should receive a fresh, bounded execution budget, with per-owner quotas and an explicit missed-period policy.

6. **High — Public rule placement gives strangers control over an object’s availability.**  
   References: [OVERHAUL §2, conflicts 2 and 8](docs/OVERHAUL.md:35), [Ops.lean:2883](spec/Delvetalk/Host/Ops.lean:2883).  
   **Scenario:** A stranger fills a busy object’s rule slots with expensive conditions or many external dependencies. Every writer inherits the judging cost and roots. Writes can fail on budget or root capacity even though the stranger’s eventual spells spend their own authority. Removal is itself judged against the existing conditions, so cleanup can encounter the same obstruction.  
   **Fix:** Allocate observer storage and evaluation to the placer. Exhausting an observer’s allowance should disable that observer, not refuse the underlying write. Reserve an owner cleanup path and capacity for essential behavior.

7. **High — Rule limits permanently discard events instead of controlling their execution rate.**  
   References: [FOUNDATION §10](docs/FOUNDATION.md:745), [Ops.lean:3743](spec/Delvetalk/Host/Ops.lean:3743).  
   **Scenario:** Nine rules match a seventh-rain crossing. Eight enqueue; the ninth becomes `unfired`. On the next write, the crossing is gone, so the ninth never runs. Placed rules precede inherited rules, allowing residents to crowd out a kind’s behavior. Level conditions have the opposite problem: they fire repeatedly while true.  
   **Fix:** Distinguish transition triggers from level conditions explicitly. Persist matched events with stable identities, then schedule them fairly under execution limits. Report queued, executed and refused outcomes separately; a front must not say it “moved” merely because its move was queued.

8. **High — An errand’s payment and completion do not form one settlement.**  
   References: [OVERHAUL §2](docs/OVERHAUL.md:27), [errand.obend:62](world/bodies/errand.obend:62), [errand.obend:87](world/bodies/errand.obend:87).  
   **Scenario:** The implementation places separate payment and settlement rules. Payment can succeed while settlement fails or remains suspended; another qualifying write can pay again under a new height-based identity. If payment initially fails, a later unrelated writer can receive credit because `{request.subject}` identifies the triggering writer, not a durably claimed completer.  
   **Fix:** Introduce an explicit settlement record: completion evidence, claimant, reserved reward, stable payment identity and final status. Claim once before paying; retry payment against that claim. Where possible, transfer and completion should commit atomically.

9. **High — Retained presentation rows are also used as permanent semantic facts.**  
   References: [FOUNDATION §9](docs/FOUNDATION.md:675), [Record.obend:118](world/objects/Record.obend:118), [AUTHORING §6.1](docs/AUTHORING.md:153).  
   **Scenario:** The authoring example permits `ringAt: 768`, but its RECORD-based body retains 128 lines, so that threshold cannot be reached. Filtered counts can fall when old rows are evicted and cross the same threshold again later. The sixteen retained marks also implement “once”; evicting `rung` or `done` can make a completed event appear uncompleted.  
   **Fix:** Separate bounded recent history from durable counters, completion facts and uniqueness records. State explicitly whether a condition measures retained history or lifetime history. Do not silently evict facts used for authorization or one-time settlement.

10. **High — Wants have incompatible truth and discovery mechanisms.**  
   References: [OVERHAUL §2](docs/OVERHAUL.md:26), [Ops.lean:3751](spec/Delvetalk/Host/Ops.lean:3751), [Ops.lean:5375](spec/Delvetalk/Host/Ops.lean:5375).  
   **Scenario:** An untouched bell becomes untended overnight. Its own `wants` reports that fact, but the global index explicitly excludes wants that became true only through time. Likewise, changing an object cited by another thing’s want does not journal the dependent transition. The commonplace and chronicle therefore miss precisely the neglected things they are supposed to surface.  
   **Fix:** Maintain dependencies and scheduled reevaluation boundaries for wants. Derive local display, global discovery, transition history and paint invalidation from the same evaluation results, with a defined opening time.

11. **High — “Nothing is wiped” has no sustainable active-state lifecycle.**  
   References: [FOUNDATION §2, Journal and Carry](docs/FOUNDATION.md:174), [Store.lean:192](spec/Delvetalk/Host/Store.lean:192), [Ops.lean:2770](spec/Delvetalk/Host/Ops.lean:2770).  
   **Scenario:** Ordinary use eventually reaches 10,000 objects, 4 GiB of journal, or 4,096 grants—including expired and revoked grants. Retirement preserves objects, and carry preserves grants and state. Snapshotting reduces replay work but does not reclaim these capacities. Creating more child objects merely moves collection growth into the global object limit.  
   **Fix:** Define archival and reclamation while preserving names and receipts: segmented journals, inactive-object archives, compact grant tombstones and bounded live indexes. Specify which capacities archival releases and enforce fair per-principal allocations.

12. **Medium — A grown verb and a bodied verb have different authority, transaction and success semantics.**  
   References: [OVERHAUL §2](docs/OVERHAUL.md:25), [AUTHORING §3(b)](docs/AUTHORING.md:56).  
   **Scenario:** Gesture `water` commits a line and tending; its rule executes later as the rule’s owner and may fail. A bodied `water` executes synchronously as the user and rolls back with its turn. Adding a body can also leave the old rule active, producing two consequences. Residents cannot infer what “water admitted” means from the shared verb interface.  
   **Fix:** Give verbs one execution contract: declared inputs, authority, effects and completion result. Keep asynchronous reactions explicitly separate. Upgrading a gesture must atomically replace or deliberately retain its previous consequence.

13. **Medium — A kind is not a consistent unit of behavior composition.**  
   References: [AUTHORING §4](docs/AUTHORING.md:92), [TurnLoop.lean:3008](spec/Delvetalk/Host/TurnLoop.lean:3008).  
   **Scenario:** Making an instance installs ancestor bodies and inherits clauses. Installing the same kind through `become` lays only its immediate body. A reusable watering kind whose law limits watering, or whose rule supplies the consequence, behaves differently when installed as the proposed “library of verbs.” Repeating `become` also stacks code rather than identifying and upgrading an installed component.  
   **Fix:** Define a versioned behavior component containing its code, clauses, dependencies and installation identity. Make instantiation and installation use the same composition rules, including conflict detection and replacement.

14. **Medium — “Rules on a kind” means two different things.**  
   References: [OVERHAUL §3](docs/OVERHAUL.md:48), [Ops.lean:2316](spec/Delvetalk/Host/Ops.lean:2316), [Law.lean:498](spec/Delvetalk/Host/Law.lean:498).  
   **Scenario:** A resident learns `rule` on a bell, then places the same rule on `kind/bell` expecting all bells to inherit it. Placed rows apply to the kind object itself; inheritance instead reads rule clauses inside its state’s `law` string. Its own governing law is yet another location. The same-looking concepts have different storage, ownership and propagation.  
   **Fix:** Use one structured clause collection with an explicit application target: this object or its instances. The same editing and inspection operations should expose and modify both deliberately.

15. **Medium — Behavior changes do not invalidate the versions used to approve actions.**  
   References: [FOUNDATION §3](docs/FOUNDATION.md:314), [Ops.lean:3009](spec/Delvetalk/Host/Ops.lean:3009).  
   **Scenario:** Hob reads a verb table and suspends. Someone removes a verb or changes its attached rules. These placements leave the object version unchanged, so a suspension rooted on that version remains valid despite the changed behavior. “Card version N” no longer identifies the affordances or consequences the user saw.  
   **Fix:** Include a behavior revision in roots, interpretation offers and action receipts. Relevant rule, want and verb edits must invalidate dependent suspended work. Paint already hashes strokes; the action-validation path needs equivalent dependency tracking.

16. **Medium — Wants are presented as answerable work without an answerability or closure contract.**  
   References: [Record.obend:136](world/objects/Record.obend:136), [VOICE, morning strokes](docs/VOICE.md:136), [bell.kind:19](world/kinds/bell.kind:19).  
   **Scenario:** The oldest wants can indefinitely occupy the morning card: a door only an absent owner may add, pending work only an absent keeper may admit, or an intentionally impossible condition. Their spells may only show blanks or a card. Conversely, a bell’s “wants rain” closes after any grown gesture because it counts all lines, although its ringing rule counts only `rain`.  
   **Fix:** Distinguish descriptive conditions from actionable tasks. Tasks need eligible actors, a concrete next action, completion evidence and blocked/cancelled states. Rotate or filter discovery so permanently blocked wants do not monopolize it; use the same domain facts for wants and effects.
   **Implementation:** [HOST-HANDOFF 5.223](../../HOST-HANDOFF.md): the existing want clause and cast admission supply reader eligibility, a waiting count, daily rotation and derived blocked/cancelled status; bell completion counts rain lines alone. Runtime and carry validation are pending with the supervisor; remaining deploy-owned asks are tracked in FOUNDATION §12.

17. **Medium — The paint’s factual guarantee exceeds what its verifier establishes.**  
   References: [OVERHAUL §4(b–d)](docs/OVERHAUL.md:85), [VOICE:165](docs/VOICE.md:165), [Enchant.lean:883](spec/Delvetalk/Host/Enchant.lean:883).  
   **Scenario:** “The bell has rung” can pass the listed token checks while no `rung` mark exists: it contains no forbidden number, identifier, quotation or negation. A historical seed such as “without a clapper” can also become a present-tense assertion after the world changes. Folding the exact card beneath this prose makes residents act on an unsupported state claim.  
   **Fix:** Render factual propositions from host-selected, structured facts. Let the model arrange those facts and add clearly nonfactual imagery, without inventing predicates or promoting historical text into current truth. Keep current status and available actions visible independently of the paint.
   **Implementation:** [HOST-HANDOFF 5.225](../../HOST-HANDOFF.md): factual lines select numbered structured facts and the host renders their clauses; historical words stay quoted as said/written, imagery has an explicit simile and vocabulary guard, and the exact card remains open below the paint. The guarantee is limited to host clauses, not arbitrary imagery semantics. Build/runtime and real-model validation remain with the supervisor; no journal derivation changes.
