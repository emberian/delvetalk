Reviewed `392c1f98` against the first-parent state before October 11, 22:10 EDT. Python refresh failures were reproduced with in-memory fixtures; Bend failures below are source-traced. No files changed.

1. **P1 — Missing ancestry permits overwriting hand-edited kind laws and forms.** [deploy/genesis.py:634](deploy/genesis.py:634)  
   **Failure:** Carry a town without its ancestor journals after the owner customized `kind/bell.law`. The carried `made` row establishes genesis provenance but provides no previous field value, so `given` records `None`. Refresh treats that as permission to replace the customization with the image’s law. The same happens to forms, voices and descriptions.  
   **Fix:** Carry the last genesis/refresh value or its digest separately from the current value. With an unknown baseline, preserve the slot and report the uncertainty.

2. **P1 — Rebase applies RECORD’s law to unrelated resident programs.** [deploy/genesis.py:711](deploy/genesis.py:711)  
   **Failure:** A resident’s custom object has State `{owner, count}` and the sole law `law kind "kind/custom's law holds": under "kind/custom"`. Refresh matches the citation and prepends `RECORD_LAW`, despite the object having no `lines`, `admitted` or `marks`. Those `insertOnly` predicates then fail on every write. The opener’s amendment succeeds, leaving the resident’s program unusable.  
   **Fix:** Restrict rebase to the known old RECORD/KIND package families and migration provenance. Preserve unrelated citations and owner amendments.

3. **P1 — A stranger can disable an errand’s payment by taking the name `pay`.** [world/bodies/errand.obend:91](world/bodies/errand.obend:91), [errand.obend:113](world/bodies/errand.obend:113)  
   **Failure:** Before an open errand completes, another resident places a rule named `pay` on it. Settlement marks the errand `done`, but installing its real payment rule fails with `nameTaken`; the claim still commits and the completion rule is removed. Even after the maker removes the squatting rule, `repay` only writes a line—it never installs the missing payment rule.  
   **Fix:** Protect the settlement’s internal rule identity, and make payment retry reconstruct a missing rule from the recorded claimant. Do not consume completion on an unrecoverable registration failure.

4. **P1 — A partial station refresh becomes permanent while retries report success.** [deploy/genesis.py:667](deploy/genesis.py:667)  
   **Failure:** Refresh creates `station`, then fails while stitching a wing or creating the register. On retry, the presence of `station` alone yields `current`; the remaining wings, objects, want and doors are skipped. The second refresh can exit successfully with an incomplete station.  
   **Fix:** Resume installation step by step using the existing identities. Verify a completion manifest before reporting `current`.

5. **P2 — Refresh forgets its own previous law amendments.** [deploy/genesis.py:588](deploy/genesis.py:588)  
   **Failure:** Genesis supplies law A; one refresh installs B. The host records this under `outcome.amendments[{object, old, new}]`, but `given` reads `outcome.laws[{object, law}]`. A subsequent image supplying C compares the current B with baseline A and leaves it as “changed since genesis gave it.” Ordinary successive law upgrades stop working.  
   **Fix:** Read admitted `amendments[].new` using the host’s actual journal schema.

6. **P2 — Library refresh identities reject metadata changes and silently defeat rollbacks.** [deploy/genesis.py:689](deploy/genesis.py:689)  
   **Failure:** The identity includes the page name and body hash, but excludes title and kind. A title-only change returns `duplicateIdentity`. Refreshing body A, then B, then A returns A’s old admitted receipt without writing anything: refresh reports `refreshed` while B remains stored. Both cases reproduced.  
   **Fix:** Include the complete requested page and the current library version in the operation identity; verify the resulting page before reporting success.

7. **P2 — Room presence and avatar location disagree, trapping normal movement.** [world/bodies/room.obend:276](world/bodies/room.obend:276), [world/objects/Avatar.obend:221](world/objects/Avatar.obend:221)  
   **Failure:** Use `me go` to enter a scene, then choose an END exit. The room removes the resident from `presence`, but the avatar retains `at`. Subsequent `me go` calls first invoke `leave` on that old room, which refuses `notHere`; movement fails. Direct room `enter` produces the opposite disagreement: the resident is present while `me look` can say “nowhere.”  
   **Fix:** Make every entry, departure and END transition update one authoritative location transaction. Derive the avatar’s location from it, or maintain its cache atomically.

8. **P2 — Any object can fabricate activity notifications about someone else’s things.** [world/objects/Avatar.obend:122](world/objects/Avatar.obend:122)  
   **Failure:** Bob’s programmable object sends Alice’s avatar `heard {thing: "alice/bell", verb: "rain"}` without touching that bell. The method checks that a sender exists and Alice made the named thing, but never checks that the sender is that thing. Alice’s “Since you were here” and book now report a rain that never happened; repeated fabrications can evict real notifications.  
   **Fix:** Require `context.sender == input.thing`, and bind notifications to the committed action they describe.

9. **P2 — Passage guards disappear across stitched wings.** [world/lib/Spween.obend:394](world/lib/Spween.obend:394), [world/bodies/station.obend:76](world/bodies/station.obend:76)  
   **Failure:** Wing one defines passage `a` with a choice pointing to `b`. Wing two later defines `=== b { unlocked >= 1 }`. Guard propagation only examines each wing’s own choices; the already-stored `a → b` choice receives no guard. With `unlocked` unset, the resident can enter `b`.  
   **Fix:** Store guards on passages and check the destination guard during movement. This also handles forward references without rewriting every incoming choice.

10. **P2 — Growing a verb with a body destroys Bend indentation.** [world/objects/Workshop.obend:323](world/objects/Workshop.obend:323)  
    **Failure:** Supply a valid body containing `match state…:` followed by indented `case` branches. `verbLayer` trims every line independently and prefixes each with two spaces, placing the cases at the same indentation as the match. The generated method fails compilation. Nested conditionals and multiline records suffer the same transformation.  
    **Fix:** Remove only common leading indentation, then indent the complete body while preserving relative indentation.

11. **P2 — Scene parsing accepts choices that the input form cannot select.** [world/lib/Spween.obend:319](world/lib/Spween.obend:319), [world/bodies/room.obend:288](world/bodies/room.obend:288)  
    **Failure:** Author `* [` followed by 65 `A` characters and `] -> END`. The scene parses and displays the choice, but `choose.choice` accepts at most 64 characters. The displayed exit cannot be taken. Empty labels are accepted too, despite the minimum being one.  
    **Fix:** Validate labels against the actual `choose` bounds, and require unique labels within each passage.

12. **P2 — The station’s register want becomes impossible to satisfy.** [deploy/genesis.py:314](deploy/genesis.py:314), [world/objects/Thing.obend:51](world/objects/Thing.obend:51)  
    **Failure:** After 33 distinct residents have departed, `count(station.left) == 33`. The register retains only 32 lines. Even if every visitor signs, `count(register.lines) + 1 <= 33` remains true forever. Additional signatures evict earlier ones instead of satisfying the want.  
    **Fix:** Track arrivals and signatures as durable identities, separate from bounded display history; compare unsigned visitors rather than retained row counts.

13. **P2 — A front reports that its move happened when it was refused.** [world/bodies/front.obend:110](world/bodies/front.obend:110)  
    **Failure:** A resident makes a one-segment front whose move attempts to set the town’s policy. One fill increments `fills`; the move is subsequently refused by the policy’s law. The card nevertheless says “it has moved once,” because it derives successful moves from `fills / segments`. Queued deliveries are also reported as completed moves.  
    **Fix:** Describe completed clock cycles as fills. Report the move’s pending, admitted or refused outcome from its delivery receipt; count successful moves only after admission.

Duplications and which mechanism to keep:

- **Ownership laws:** [genesis.py:181](deploy/genesis.py:181) versus [Record.obend:138](world/objects/Record.obend:138), and the corresponding KIND copies. Keep one Bend definition and obtain genesis’s law text from the sealed host library.
- **Form validation:** [Forms.obend:71](world/lib/Forms.obend:71) versus the host’s form binder. They already disagree: `specFault` requires omitted `text 0..N` fields, while the host supplies empty text. Keep the host binder and route `makeUnder` through it.
- **Resident location:** avatar `at` versus room `presence`. Keep room presence as authority; make avatar location a derived index.
- **Arrival history:** [room.obend:224](world/bodies/room.obend:224) independently reconstructs “while away” facts that the host’s telling machinery also selects from the journal. Keep the host’s structured history selection; let Bend render those facts, including the station’s different frame.
- **Custom verb execution:** grown gesture verbs plus rules versus `growBody` extending the object with a declared method. Keep the grown-verb registry as the single dispatch mechanism, with an optional pinned body and explicit execution authority; avoid two implementations of the same named verb with different completion semantics.