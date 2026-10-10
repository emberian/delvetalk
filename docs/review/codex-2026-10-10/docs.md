Reviewed `a3e1fb2` by source inspection only; no edits, builds, or tests.

1. **A reprogram can change a field promised to be fixed forever.**  
   Evidence: [FOUNDATION.md:309](/Users/ember/dev/delvetalk2/docs/FOUNDATION.md:309), [Ops.lean:1915](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1915), [Ops.lean:1924](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1924).  
   Why: An owner can replace `x: fixed Nat` with `x: Nat` and supply a migration changing `x`; migration validation checks only the replacement program’s fixed fields. The turn can therefore admit the change and remove future protection, contradicting “set when made and never after.”  
   Smallest fix: Reject removal of existing fixed fields and check migrations against both existing and newly fixed fields. **Lane: host.**

2. **Extension pins can identify different sealed source closures.**  
   Evidence: [FOUNDATION.md:429](/Users/ember/dev/delvetalk2/docs/FOUNDATION.md:429), [Ops.lean:1140](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1140), [Ops.lean:1159](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1159).  
   Why: Extending the same base with the same layer under two different current libraries compiles different closures, but the extension pin hashes only the old pin and layer text. Those closures receive the same pin, contradicting the source-closure identity contract.  
   Smallest fix: Use the compiled closure’s `sourcePin` for extensions and update replay’s corresponding expectation. **Lane: host.**

3. **The root welcome copy promises confirmation that default planting skips.**  
   Evidence: [gsb-root-menu-v2.txt:45](/Users/ember/dev/delvetalk2/docs/previews/gsb-root-menu-v2.txt:45), [VOICE.md:13](/Users/ember/dev/delvetalk2/docs/VOICE.md:13), [GENESIS.md:28](/Users/ember/dev/delvetalk2/docs/GENESIS.md:28), [Garden.obend:352](/Users/ember/dev/delvetalk2/world/objects/Garden.obend:352).  
   Why: A complete interpreted planting grows immediately because genesis leaves Garden’s `confirmFor` empty, whereas the menu promises to show the spell before anything runs. Confirmation also differs by card: Directory asks for a filled spell rather than retaining a proposal for bare `yes` ([Directory.obend:341](/Users/ember/dev/delvetalk2/world/objects/Directory.obend:341)).  
   Smallest fix: State that confirmation is action-specific, planting normally runs immediately, and Directory confirmation requires resending the filled spell. **Lane: docs.**

4. **Successful town replies omit the promised receipt line and spoken name.**  
   Evidence: [FOUNDATION.md:141](/Users/ember/dev/delvetalk2/docs/FOUNDATION.md:141), [gsb-welcome-v4.txt:17](/Users/ember/dev/delvetalk2/docs/previews/gsb-welcome-v4.txt:17), [bridge.py:103](/Users/ember/dev/delvetalk2/transport/bridge.py:103), [bridge.py:159](/Users/ember/dev/delvetalk2/transport/bridge.py:159).  
   Why: A successful planting draft returns only the Garden’s offer text, and resumed offer drafts likewise concatenate only offer texts. Posting carries that text unchanged ([post.py:146](/Users/ember/dev/delvetalk2/transport/post.py:146)), so the promised receipt name is absent from the resulting post.  
   Smallest fix: Append the committed receipt line and slug to immediate and resumed offer drafts. **Lane: transport.**

5. **Creation accepts object names that the advertised spell surface cannot address.**  
   Evidence: [FOUNDATION.md:97](/Users/ember/dev/delvetalk2/docs/FOUNDATION.md:97), [capsules/spells.txt:3](/Users/ember/dev/delvetalk2/capsules/spells.txt:3), [Ops.lean:55](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:55), [Spell.lean:77](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Spell.lean:77).  
   Why: Creation admits `Coin_box`, but `delvetalk Coin_box drop` fails the spell heading check because uppercase letters and underscores are excluded. An object can therefore be valid and publish a spell template that the parser does not recognize.  
   Smallest fix: Align spell card names with the creation alphabet and byte limit, including the Bend header reader. **Lanes: host, objects.**

6. **An intent matching an existing receipt slug retrieves the wrong receipt.**  
   Evidence: [AGENTS-API.md:74](/Users/ember/dev/delvetalk2/docs/AGENTS-API.md:74), [AGENTS-API.md:257](/Users/ember/dev/delvetalk2/docs/AGENTS-API.md:257), [http.py:554](/Users/ember/dev/delvetalk2/transport/http.py:554).  
   Why: Choose an existing receipt’s spoken name as a new turn’s intent, then request `/receipt/<that intent>`: the front resolves the older receipt by slug first. The guide promises lookup by your intent but provides no way to disambiguate these overlapping namespaces.  
   Smallest fix: Add an explicit intent lookup route or query discriminator and document it. **Lane: transport.**

7. **The object capsule teaches a “refusal” that still commits staged writes.**  
   Evidence: [capsules/object.txt:45](/Users/ember/dev/delvetalk2/capsules/object.txt:45), [Card.obend:289](/Users/ember/dev/delvetalk2/world/lib/Card.obend:289), [TurnLoop.lean:1800](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1800).  
   Why: Returning a `refused` sum arm and offering refusal text produces an ordinary successful result, which `finishTurn` commits without inspecting its label. A method that stages an increment before following this recipe receives an admitted receipt and retains the increment.  
   Smallest fix: Distinguish an application result named `refused` from a turn abort, and teach `refuse("why")` when rollback is intended. **Lane: docs.**

8. **The declared-surface invariant incorrectly forbids helper deliveries that the host intentionally runs.**  
   Evidence: [FOUNDATION.md:433](/Users/ember/dev/delvetalk2/docs/FOUNDATION.md:433), [CODEX-BRIEF.md:46](/Users/ember/dev/delvetalk2/docs/CODEX-BRIEF.md:46), [TurnLoop.lean:2158](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:2158), [TurnLoop.lean:973](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:973).  
   Why: Change deliveries and supervisor notifications set `receiver`, bypassing the public-method check and allowing helpers. The stated invariant would reject this intended behavior, which OBJECTS-HANDOFF explicitly describes for Wake receivers.  
   Smallest fix: State the exception for explicitly selected subscription receivers and supervisor notifications. **Lane: docs.**

9. **The introductory commit rule contradicts the implemented commutative-root rule.**  
   Evidence: [FOUNDATION.md:9](/Users/ember/dev/delvetalk2/docs/FOUNDATION.md:9), [site/index.html:17](/Users/ember/dev/delvetalk2/site/index.html:17), [FOUNDATION.md:414](/Users/ember/dev/delvetalk2/docs/FOUNDATION.md:414), [Ops.lean:1838](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1838).  
   Why: A proposal adding to a counter after another admitted increment can still commit through `movedRootAdmits`. The opening paragraph and site say it must refuse whenever anything read has moved, while the later invariant correctly permits commuting edits.  
   Smallest fix: Add the commutative-rebase exception to both introductory descriptions and matching welcome copy. **Lane: docs.**

10. **The law capsule gives an incomplete closed refusal set and omits transient `quota`.**  
    Evidence: [capsules/laws.txt:26](/Users/ember/dev/delvetalk2/capsules/laws.txt:26), [Ops.lean:385](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:385), [Ops.lean:1998](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1998).  
    Why: A turn exceeding interpretation quota returns `quota` and releases its identity, but the capsule lists neither that class nor its retry behavior. It also omits binding `noMethod`, so its advertised class reference cannot classify two actual host outcomes.  
    Smallest fix: Add `quota` to transient classes and `noMethod` to binding classes. **Lane: docs.**

11. **The objects handoff says derived views appear as spells, but the host excludes them.**  
    Evidence: [OBJECTS-HANDOFF.md:61](/Users/ember/dev/delvetalk2/docs/OBJECTS-HANDOFF.md:61), [HOST-HANDOFF.md:626](/Users/ember/dev/delvetalk2/docs/HOST-HANDOFF.md:626), [TurnLoop.lean:784](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:784).  
    Why: `delvetalk garden ?` does not list `byColour`, contrary to the objects handoff’s explicit example. Spell fitting uses the same filtered forms, so sending that advertised view as a spell cannot invoke it.  
    Smallest fix: Describe views as inspectable and callable through `viewDerived`, without promising them in usage. **Lane: docs.**

12. **The host handoff promises automatic torn-tail cutting, while reopening refuses the journal.**  
    Evidence: [HOST-HANDOFF.md:35](/Users/ember/dev/delvetalk2/docs/HOST-HANDOFF.md:35), [FOUNDATION.md:180](/Users/ember/dev/delvetalk2/docs/FOUNDATION.md:180), [Snapshot.lean:513](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Snapshot.lean:513), [Session.lean:85](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Session.lean:85).  
    Why: Append an unterminated final fragment to an otherwise valid journal: reopening returns `unterminated final line` rather than cutting it. The handoff gives operators the wrong recovery expectation; FOUNDATION correctly assigns cutting to backup-copy handling.  
    Smallest fix: Replace “a torn tail is cut” with the named refusal and link the documented copy-and-verify recovery procedure. **Lane: docs.**

13. **The current review brief and backlog still report already-fixed defects as present.**  
    Evidence: [CODEX-BRIEF.md:81](/Users/ember/dev/delvetalk2/docs/CODEX-BRIEF.md:81), [FOUNDATION.md:603](/Users/ember/dev/delvetalk2/docs/FOUNDATION.md:603), [http.py:245](/Users/ember/dev/delvetalk2/transport/http.py:245), [ObjectiveBendElaborate.lean:2747](/Users/ember/dev/delvetalk2/spec/bend/Compiler/ObjectiveBendElaborate.lean:2747).  
    Why: The brief’s “sharpest” defect cites an unconditional `roots[0]` access that now has an empty-root guard. FOUNDATION also says `checkFormInputs` is absent and fixed-field proposal enforcement remains unfinished, although both implementations are present.  
    Smallest fix: Reconcile FOUNDATION’s backlog, CODEX-BRIEF, and the handoffs’ open sections against this commit, retaining only unresolved work. **Lane: docs.**