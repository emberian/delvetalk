Read-only review of `foundation` at `a3e1fb2`. No edits, builds, or tests.

1. **Settling exposes other principals’ complete receipts.**  
   Evidence: [Session.lean:109](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Session.lean:109), [TurnLoop.lean:1599](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1599).  
   When Bob’s turn releases Alice’s suspended activity, Bob receives `resumed[].receipt`, including Alice’s result and journaled offers. `quiet` removes only the outer `offers` field, bypassing the requirement that complete receipts belong to their identity’s principal.  
   **Smallest fix:** Project every settling receipt for the requesting principal and remove protected results. **Lane:** host.

2. **The host’s default `publishPage` publicly exports unreadable objects.**  
   Evidence: [TurnLoop.lean:1819](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1819), [Ops.lean:3509](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:3509).  
   A stranger can directly request `publishPage` on a private object lacking that method, causing its renderer to consume the private state without a read-policy check. The resulting body is available through `world-publications` to every reader, so a renderer relying on the object’s read policy leaks its contents.  
   **Smallest fix:** Require public read permission before the host synthesizes a public page. **Lane:** host.

3. **`lawReads` bypasses the target objects’ read policies.**  
   Evidence: [Ops.lean:1722](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1722).  
   An attacker’s object can name a private object in `lawReads()` and receive its version and complete state inside the predicate request. A predicate can then disclose a private value through its admitted/refused verdict, although `world.view` would deny that principal.  
   **Smallest fix:** Check each target’s read policy against the judgment’s subject before supplying its state. **Lane:** host.

4. **Law-read expansion can durably admit an entry that cannot replay.**  
   Evidence: [Ops.lean:1643](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1643), [Ops.lean:283](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:283).  
   An object with 64 existing objects in `lawReads()` adds those roots to its own root, producing an admitted entry with 65 roots. Admission does not reject that total, but replay’s `parseRoots` rejects it with `too many roots`, making the journal unreopenable through full replay.  
   **Smallest fix:** Enforce the combined object-root and field-root limit after law-read expansion. **Lane:** host.

5. **Reprogramming can remove a fixed field’s protection and change its value.**  
   Evidence: [Ops.lean:1915](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1915), [Ops.lean:1924](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1924).  
   Replacing `n: fixed Nat` with `n: Nat` permits a migration to change `n`, because the migration guard checks only `prog.fixed`. Even without a migration, installing the replacement clears the old protection and permits a subsequent proposed write to change the supposedly permanent value.  
   **Smallest fix:** Preserve existing fixed declarations and check their values after migration and canonicalization. **Lane:** host.

6. **An arbitrary creator can invoke another object’s private `ended` helper.**  
   Evidence: [TurnLoop.lean:1473](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1473), [TurnLoop.lean:2160](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:2160), [TurnLoop.lean:973](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:973).  
   An attacker can create a child naming a victim as supervisor and exhaust the child’s budget, generating an `ended` delivery to the victim. That delivery bypasses the public-method check even when the victim never exposed `ended`; the child’s creator chose the supervisor, not the receiving object.  
   **Smallest fix:** Require the supervisor to expose `ended` before accepting the supervisor relationship. **Lane:** host.

7. **A rehashed snapshot can replace a journaled law without being rejected.**  
   Evidence: [Snapshot.lean:278](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Snapshot.lean:278), [Snapshot.lean:473](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Snapshot.lean:473).  
   Changing an object’s snapshot law and recomputing the snapshot CID leaves its checked version, pin, and state CID unchanged. Ordinary reopening accepts that snapshot at the journal head, allowing a previously forbidden write under a law the journal never admitted; only `verify: true` performs the comparison that catches it.  
   **Smallest fix:** Derive and compare effective laws from the journal during ordinary snapshot acceptance. **Lane:** host.

8. **`insertOnly` admits explicit retractions disguised as retention.**  
   Evidence: [Law.lean:95](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Law.lean:95), [Law.lean:200](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Law.lean:200).  
   For a limit-two relation containing keys `[1,2]`, proposing `retract 1` followed by `insert 3` produces `[2,3]` and passes `insertOnly`. No retention overflow occurred, but the predicate infers a retention drop solely from the final relation being full and its keys sorting above the missing row.  
   **Smallest fix:** Exempt only rows actually removed by canonical retention during edit application. **Lane:** host.

9. **Creating children spends no causal storage budget.**  
   Evidence: [Ops.lean:2676](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:2676), [TurnLoop.lean:1801](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1801).  
   A delivered factory method can create large child objects and send itself another factory request without reducing its storage ledger. `childLedger` counts only updated objects, excluding creations, so a single delivery chain can allocate well beyond its stated storage allowance.  
   **Smallest fix:** Include created objects’ complete state sizes in the child-ledger deduction. **Lane:** host.

10. **Retention evictions are absent from per-key conflict history.**  
    Evidence: [Ops.lean:1773](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1773), [Ops.lean:1792](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1792).  
    If inserting key `3` into a limit-two relation `[1,2]` evicts key `1`, the conflict index records only key `3`. A suspended upsert or retract of key `1` therefore qualifies as untouched and returns admitted instead of `staleRoot`, despite an intervening write removing its row.  
    **Smallest fix:** Index retention-evicted keys alongside explicitly edited keys. **Lane:** host.

11. **`inspect` and subscription admission omit their target roots.**  
    Evidence: [TurnLoop.lean:1333](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1333), [TurnLoop.lean:1390](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1390).  
    A turn can inspect another object’s pin and law, suspend across its reprogramming, and commit using that obsolete information without a stale-root conflict. Likewise, a staged subscription can commit after its target is migrated to remove the checked field, because neither target was recorded and judgment checks only subscription capacity.  
    **Smallest fix:** Record the inspected object root and the subscription target’s applicable root before answering. **Lane:** host.

12. **Direct turns bypass declared form bounds.**  
    Evidence: [TurnLoop.lean:977](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:977), [TurnLoop.lean:992](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:992), [Spell.lean:318](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Spell.lean:318).  
    A method declaring `text 1..80` can receive an empty or 81-character string through a direct turn and commit, provided its Bend implementation accepts it. Direct execution checks the input type and uses declared bounds only to construct refusal hints, whereas the spell path enforces those bounds.  
    **Smallest fix:** Validate direct arguments against declared form constraints before running the method. **Lane:** host.

13. **An unchanged spell retry can become `duplicateIdentity` after reprogramming.**  
    Evidence: [TurnLoop.lean:1909](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1909), [TurnLoop.lean:1887](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1887).  
    After an admitted `receive` containing `delvetalk c bump`, removing `bump` and resending the identical request routes the retry through the new `noAction` refusal. That path compares an empty proposal digest against the original admitted proposal and returns `duplicateIdentity`, rather than the retained receipt promised for an identical request.  
    **Smallest fix:** Apply `retainedTurn` before parsing or routing the spell. **Lane:** host.

14. **Exhausting `lawReads()` produces a permanent law refusal instead of transient budget exhaustion.**  
    Evidence: [Ops.lean:1625](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1625), [Ops.lean:1720](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1720), [Ops.lean:1998](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1998).  
    A nonterminating `lawReads()` exhausts `lawTicks`, but its error becomes `lawRefused` with clause `lawReads`. That binds the identity permanently, so fixing the program still leaves an identical direct-turn retry returning the old refusal.  
    **Smallest fix:** Preserve budget exhaustion through `lawReadsOf` and return class `budget`. **Lane:** host.

15. **A second suspension loses the original spell origin needed for a later rerun.**  
    Evidence: [TurnLoop.lean:1767](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1767), [TurnLoop.lean:2033](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:2033), [TurnLoop.lean:2113](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:2113).  
    Resumption restores `post` but leaves `origin` and `command` at their defaults, so a spell activity that suspends again omits its original spell metadata from the second entry. If that suspension later triggers a stale-root rerun, the method receives `inputOrigin.kind = "request"` instead of `"spell"` and can take a different branch for the same originating request.  
    **Smallest fix:** Restore `origin` and `command` when constructing the resumed `TurnState`. **Lane:** host.