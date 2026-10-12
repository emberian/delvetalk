1. **[P1] Placed rules can exfiltrate fields from objects their owner cannot read.**

   **Evidence:** `spec/Delvetalk/Host/Ops.lean:3209`, `:3218`; the permission check at `:2533` covers law citations, not rule citations.  
   **Failure:** A private `secret` holds `code`. An attacker places on a public object a rule firing after a write, with `then delvetalk me note / text: {"secret".code}`. The host reads and substitutes the private code, then delivers it to the attacker’s avatar.  
   **Smallest fix:** Check every rule’s cited reads under its owner’s authority before evaluating or filling it; journal an unfired refusal when denied. **Lane:** host.

2. **[P1] Raw spell-hole substitution lets writable text redirect a rule owner’s authority.**

   **Evidence:** `spec/Delvetalk/Host/Law.lean:404`; `spec/Delvetalk/Host/Spell.lean:326`; `spec/Delvetalk/Host/Ops.lean:3229`.  
   **Failure:** An owner places `then delvetalk me note / text: {new.message}` on a thing strangers may update. A stranger sets `message` to `hello\n delvetalk…` with the injected spell at the margin, naming an owner-only transfer on another thing. The parser selects the later spell, which executes as the rule owner.  
   **Smallest fix:** Substitute holes into parsed spell values with delimiter-safe encoding, rather than concatenating executable spell text. **Lane:** host.

3. **[P1] Direct turns using a grant bypass its fixed arguments and use limit.**

   **Evidence:** `spec/Delvetalk/Host/TurnLoop.lean:2832`, `:2584`; compare the checked call path at `:584` and `:598`.  
   **Failure:** An owner’s object grants a guest its own `transfer` method, fixing the recipient and allowing one use. The guest directly invokes that method with another recipient, repeatedly. `lentVia` selects the grant, but the direct entry neither attenuates the argument nor spends a use; admission nevertheless judges writes as the grantor.  
   **Smallest fix:** Apply grant validation, argument attenuation, subject selection and use spending at direct granted entry, just as for `callVia`. **Lane:** host.

4. **[P1] Replaying an in-turn creation loses its package’s rules and wants.**

   **Evidence:** `spec/Delvetalk/Host/Ops.lean:1828`, `:4128`, `:3399`, `:4373`.  
   **Failure:** `world.create` creates a package with a want true in its initial state, without an explicit law override. First execution installs the package’s placed want and journals `wanted`. Replay rebuilds with an explicit serialized law, which suppresses all package placements; reaction comparison then rejects the admitted entry. A package containing only rules instead silently loses those rules.  
   **Smallest fix:** Journal and restore created rules and wants in both replay and suspension reconstruction. **Lane:** host.

5. **[P1] Snapshot validation accepts forged rule ownership and read authority.**

   **Evidence:** `spec/Delvetalk/Host/Snapshot.lean:338`, `:340`, `:485`, `:461`.  
   **Failure:** Modify a head snapshot’s placed rules to add a firing owned by another principal, or change a private object’s read policy to exposed, then recompute the snapshot CID. Version, state CID, pin and law remain unchanged, so fast reopen accepts the snapshot. The forged rule subsequently executes as its fabricated owner, or the private state becomes readable.  
   **Smallest fix:** Bind and validate authority-bearing metadata against journal records; rederive metadata lacking an independently verifiable anchor. **Lane:** host.

6. **[P1] Quieting a principal does not prevent writes through the proposal and reprogramming ops.**

   **Evidence:** `spec/Delvetalk/Host/TurnLoop.lean:3267`, `:3740`; `spec/Delvetalk/Host/Session.lean:407`.  
   **Failure:** A quieted maker submits `world-propose` with current roots and a permitted state edit, or `world-reprogram` for their own object. These paths reach `commit` without the quiet check used by `runOne`, and the write admits before the quiet period ends.  
   **Smallest fix:** Enforce quiet centrally for non-root mutating entries, including resumptions and deliveries. **Lane:** host.

7. **[P1] A locally placed rule can collide with an inherited rule’s delivery identity and suppress it.**

   **Evidence:** `spec/Delvetalk/Host/Ops.lean:2626`, `:2058`, `:3159`, `:3013`.  
   **Failure:** A bell inherits the kind’s `seven` rule. A stranger places another rule named `seven` on that bell, with the same triggering condition. Placement checks only local names. Both firings receive `rule:<bell>:seven:<height>`; the local rule runs first, and consuming its delivery removes both pending entries. The kind’s rule never runs.  
   **Smallest fix:** Include the clause holder or another stable clause identity in firing IDs, and reject inherited-name collisions where names must remain unique. **Lane:** host.

8. **[P1] Carry releases previously bound request identities, allowing duplicate effects.**

   **Evidence:** `spec/Delvetalk/Host/Snapshot.lean:392`, `:435`; `spec/Delvetalk/Host/Carry.lean:398`.  
   **Failure:** Principal P admits intent I, incrementing a counter. Carry preserves the counter but omits the receipt identity index. Retrying the identical request after carry executes again and increments it twice instead of returning the original receipt.  
   **Smallest fix:** Carry retained identity/request bindings and their receipts through a representation independent of old journal indexes. **Lane:** host.

9. **[P1] Carry can admit suspended writes based on cells changed by a migration.**

   **Evidence:** `spec/Delvetalk/Host/Carry.lean:299`; `spec/Delvetalk/Host/Snapshot.lean:392`; `spec/Delvetalk/Host/Ops.lean:2359`, `:2386`.  
   **Failure:** Unmoved object A suspends after reading `B.flag = 0` through `viewField`. Carry migrates B to `flag = 1` and increments its version, but starts with no touch history for that move. On resumption, `cellsCurrent` sees an empty edit history and admits A’s cached decision based on zero.  
   **Smallest fix:** Install a noncommuting touch barrier for every carried migration or code move, invalidating retained dependent roots. **Lane:** host.

10. **[P1] Nested want dependencies can make a law admit a write it should refuse.**

    **Evidence:** `spec/Delvetalk/Host/Ops.lean:1989`, `:2069`, `:2538`; `spec/Delvetalk/Host/Law.lean:363`.  
    **Failure:** C wants `blocked` while `flag = 1`; B’s placed want `blocked` is `"C" wants blocked`. A’s write law requires `not "B" wants blocked`. A’s facts include B’s want but omit C’s state and want, so the nested test returns false and A’s prohibited write admits, although B’s own wants read reports `blocked`.  
    **Smallest fix:** Transitively collect want dependencies, populate their states and clauses, and record all resulting roots within the existing bounds. **Lane:** host.

11. **[P1] Cross-object constraints judge an atomic commit against other objects’ pre-write states.**

    **Evidence:** `spec/Delvetalk/Host/Ops.lean:2532`, `:2543`, `:3300`.  
    **Failure:** A and B each have count zero and laws requiring their new count plus the other’s count to remain at most one, with amendments separately allowed. One turn increments both. Each judgment reads the other’s old zero, so both admit and the committed total becomes two. Either increment would be refused after the other landed.  
    **Smallest fix:** Construct the candidate world first and recheck cited constraints against its updates before installing the commit. **Lane:** host.

12. **[P2] `world.judge` reads law dependencies without retaining their roots.**

    **Evidence:** `spec/Delvetalk/Host/TurnLoop.lean:1859`, `:1864`, `:1868`.  
    **Failure:** A dry-run judgment depends on B’s flag and returns admitted. A then waits. B changes the flag, and A resumes to record that approval on C without performing the hypothetical edit. The expanded B root existed only in the temporary proposal, so C’s write commits using the obsolete verdict.  
    **Smallest fix:** Merge the judgment’s dependency roots into the running turn before returning its verdict. **Lane:** host.

13. **[P2] Relational law and rule evaluation performs quadratic work outside the tick budget.**

    **Evidence:** `spec/Delvetalk/Host/Law.lean:252`; `spec/Delvetalk/Host/Ops.lean:3211`.  
    **Failure:** An object holds 4,096 rows and 32 rules using `changed(new.lines.author) by request.subject`. A small write repeatedly compares every old row against every new row, re-encoding rows during membership checks. None of this work spends turn or law ticks, so a low-budget request can monopolize the single host far beyond its advertised judging budget.  
    **Smallest fix:** Meter fragment evaluation and reuse canonical row sets and diffs across clauses. **Lane:** host.

14. **[P2] Historical strokes mix old state with current wants, verbs and rule firings.**

    **Evidence:** `spec/Delvetalk/Host/Enchant.lean:254`, `:211`, `:226`, `:231`.  
    **Failure:** Version 1 of a bell wants a second hand; version 2 satisfies that want and grows a verb. Requesting strokes or paint for version 1 supplies its old lines and counts alongside version 2’s wants and verb table. The verifier consequently validates against facts that did not belong to the requested version.  
    **Smallest fix:** Assemble from historical object metadata and dependencies, or refuse historical painting until that reconstruction is supported. **Lane:** host.

15. **[P2] The paint verifier accepts truncated resident quotations credited to the wrong writer.**

    **Evidence:** `spec/Delvetalk/Host/Enchant.lean:465`, `:470`; the enforced contract is stated in `world/lib/Paint.obend:6`.  
    **Failure:** Strokes contain Yuè’s line `rain is the sky's erratum` and Claude’s handle elsewhere. Paint saying `claude.delve.town writes “rain is the sky”.` passes: the quotation is a substring and the handle appears independently in the strokes. It violates the promised whole-line quotation and attribution check.  
    **Smallest fix:** Require resident quotations to match a whole stroke line and bind each quotation’s credit to that line’s recorded writer. **Lane:** host.