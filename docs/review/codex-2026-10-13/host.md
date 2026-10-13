Reviewed `344e19af..392c1f98`, covering the preceding 24 hours. These are source-traced findings; host runtime tests were not run. The oversized clock payload was checked with the repository’s CBOR encoder. Files remain unchanged.

1. **P1 — Enough simultaneous wants permanently block the clock.** [Ops.lean:3664](spec/Delvetalk/Host/Ops.lean:3664), [Session.lean:174](spec/Delvetalk/Host/Session.lean:174)  
   Create 1,000 owned objects, each with 32 wants becoming true at the same future minute. All fit the object and placement limits. With legal 120-character object names, their 32,000 flip rows encode to **4,448,011 bytes**. `clockFlips` puts them into one entry; the 1 MiB entry check rejects the advance and retains the old clock. Every subsequent advance crossing that deadline fails again, blocking deadlines, grant expiry and clock-driven activity.  
   **Fix:** journal and drain bounded batches of outstanding flips, preserving the triggering clock and deterministic replay.

2. **P1 — Strokes disclose arbitrary private kind fields.** [Enchant.lean:339](spec/Delvetalk/Host/Enchant.lean:339), [Enchant.lean:421](spec/Delvetalk/Host/Enchant.lean:421)  
   An attacker creates a readable object whose `kind` field names a known private object. `world-strokes` checks permission on the attacker’s object, then reads the referenced object’s `voice` and `about` without authorization. An `under` reference similarly exposes private law readings. These values also become model input.  
   **Fix:** pass the reader through assembly and authorize every referenced object before extracting its fields, clauses or readings.

3. **P1 — A revoked rule citation remains a private-state oracle.** [Ops.lean:3874](spec/Delvetalk/Host/Ops.lean:3874)  
   While `secret` is readable, Mallory places a rule on a public object with condition `"secret".flag == 1`. Later, Mallory loses read permission on `secret`. On each public-object write, the host evaluates the condition **before** checking citation permission. A true condition produces `unfired reads`; a false condition produces no row. Mallory’s receipt and rule log therefore reveal the hidden flag.  
   **Fix:** authorize citations before evaluating either condition cost or truth. An inaccessible rule must have an outcome independent of the inaccessible state.

4. **P2 — `if:` guards accept changed behaviour.** [Ops.lean:3058](spec/Delvetalk/Host/Ops.lean:3058), [Session.lean:208](spec/Delvetalk/Host/Session.lean:208)  
   Preview a rain and retain its version guards. Another resident places a rule on that bell. Placements leave its version unchanged, so resending the guarded rain succeeds and fires an effect absent from the preview. Grown or removed verbs have the same problem.  
   **Fix:** include a behaviour revision or placed-row CID in preview roots and guards, advancing it whenever rules, wants or verbs change.

5. **P2 — Private objects cannot execute their inherited self-rules.** [TurnLoop.lean:1483](spec/Delvetalk/Host/TurnLoop.lean:1483)  
   A private bell permits only its owner to read it and inherits a rule that rings itself. Reaction authorization explicitly allows `@bell` to view itself, so the firing queues. Spell dispatch subsequently checks `ReadPolicy.permits "@bell"` directly, rejects it as `otherCard`, and consumes the firing.  
   **Fix:** use one read-authorization function throughout, including the existing exception for a thing acting as itself.

6. **P2 — Later plan acts route against unstaged behaviour and state.** [TurnLoop.lean:3492](spec/Delvetalk/Host/TurnLoop.lean:3492)  
   A plan containing `grow / name: polish / reading: …` followed by `polish` fails with `noAction`: the placement lives in `s.placements`, while routing reads `s.world`. Likewise, `become` followed by a newly introduced action sees the old method table. A map read following a staged door write sees the old doors.  
   **Fix:** route and render each act against a unified overlay containing preceding writes, placements, amendments and program changes.

7. **P2 — Placement admission defeats final-state plan judging.** [TurnLoop.lean:1640](spec/Delvetalk/Host/TurnLoop.lean:1640)  
   Give an empty record a clause allowing placement only when `count(new.lines) >= 1`. A plan first writes a line, then places a rule. `stagePlacements` invokes `judge` with `writes := []` against the committed empty record and rejects the plan, although its final state satisfies the clause.  
   **Fix:** defer plan placement admission to the final commit. Intermediate structural validation must not judge a reduced proposal that omits the plan’s writes.

8. **P2 — Dependent wants beyond the first 64 lose their transition permanently.** [Ops.lean:3517](spec/Delvetalk/Host/Ops.lean:3517), [Ops.lean:5584](spec/Delvetalk/Host/Ops.lean:5584)  
   Place wants on 65 objects, all depending on a gate’s initially false flag. Set the flag true. Only the first 64 objects are reviewed; the 65th gets no `wanted` row and remains absent from `world-wanting`. Its own `world-wants` read nevertheless reports the want. Later writes while the flag remains true compare true with true, so they cannot recover the missed opening.  
   **Fix:** persist deferred reviews and reconcile against indexed truth, retaining the original triggering height.

9. **P2 — Numeric parsing verifies false counts.** [Tongue.lean:202](spec/Delvetalk/Host/Tongue.lean:202), [Enchant.lean:1085](spec/Delvetalk/Host/Enchant.lean:1085)  
   Against strokes holding four rains, `4,000 rains` is read as four: `wordNumber` consumes the initial digits and treats the unrecognized remainder as a non-ordinal suffix. `4.5 rains` follows the same path. The verifier can therefore cache prose claiming a different quantity.  
   **Fix:** consume the entire numeric token. Normalize supported separators explicitly; reject malformed suffixes, decimals and additional digit runs instead of accepting their prefix.

10. **P2 — Tellings mistake bounded conflict history for complete encounter history.** [Enchant.lean:569](spec/Delvetalk/Host/Enchant.lean:569), [Enchant.lean:587](spec/Delvetalk/Host/Enchant.lean:587)  
    After a carry, `touches` contains only the genesis barrier, so a first-arrival telling omits pre-carry lines still present in the room. Separately, after 512 subsequent touches, a present resident’s arrival falls outside `arrivalOf`’s search. The fallback uses the newest change as its endpoint and tells post-arrival events under “Before you arrived.”  
    **Fix:** preserve an authoritative arrival anchor and read historical events across carry origins. If history is unavailable, expose that boundary instead of presenting a complete telling.

11. **P2 — The first rule firing changes or disappears after carry.** [Surfaces.lean:227](spec/Delvetalk/Host/Surfaces.lean:227)  
    A placed rule fires at entries 10 and 20, then the world is carried. The old journal is outside `entries`; the fallback uses `ruleLog`, which retains the **last** firing, and reports entry 20 as the first. For inherited or own-text rules, ownership is looked up only in `o.rules`, so the fallback drops them entirely.  
    **Fix:** obtain the earliest firing and its recorded principal from durable history across carry origins; do not infer either from the current placement list or last-firing log.

12. **P2 — Map reads perform quadratic work outside the execution budget.** [Surfaces.lean:314](spec/Delvetalk/Host/Surfaces.lean:314)  
    Build a legal chain of roughly 10,000 readable cards. Reading the map at its far end scans every edge for every visited vertex—roughly 100 million edge tests—plus linear visited-list searches. This happens before the budgeted renderer runs, blocking the world’s single host process.  
    **Fix:** build an adjacency map and visited hash set, use a queue, and bound or page the handed surface data before rendering.

Duplications, with which mechanism to keep:

- **Placement judging:** [TurnLoop.lean:1642](spec/Delvetalk/Host/TurnLoop.lean:1642) and `Ops.commit → judge` both decide placement admission. Keep final commit judging for plans; retain only structural checks while staging.
- **Coinage attribution:** [Enchant.lean:468](spec/Delvetalk/Host/Enchant.lean:468) independently repeats [Ops.lean:5671](spec/Delvetalk/Host/Ops.lean:5671). Their unknown-author fallback already differs. Keep `Ops.coinerOf` as the shared attribution path.
- **Making provenance:** strokes derive `made` from state or the first touch, while [Surfaces.lean:76](spec/Delvetalk/Host/Surfaces.lean:76) resolves actual creation provenance across carries. Keep the creation-provenance resolver; a carry barrier is not a making.
- **Data projection and principal naming:** `Surfaces.fieldsOf/text?/nat?/rows/referenceOf/named` repeat Enchant’s corresponding readers and `handleIn`. Keep one shared projection implementation and one town-aware row-name resolver used by both surfaces.