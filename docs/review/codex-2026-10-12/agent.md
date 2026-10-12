1. **[P1] Carry forgets turn identities, so retrying a committed act performs it again.**  
   **Evidence:** `spec/Delvetalk/Host/Snapshot.lean:392`, `spec/Delvetalk/Host/Carry.lean:398`, `spec/Delvetalk/Host/TurnLoop.lean:2318`.  
   **Failure:** Alice rains with intent `rain-1`; the world is carried; Alice retries the identical request after losing its reply. Carry preserves neither the receipt identity index nor its request digest, so the retained-turn lookup misses and another rain commits.  
   **Smallest fix:** Carry bindings from principal/intent to request digest and retained outcome, and consult them before executing a turn.  
   **Lane:** host.

2. **[P1] Spell splitting casts commands inside fenced examples and literal text blocks.**  
   **Evidence:** `spec/Delvetalk/Host/Spell.lean:357`, `spec/Delvetalk/Host/TurnLoop.lean:3301`.  
   **Failure:** Submit `delvetalk lamp/1 write`, followed by `text: <<END`, a literal line `delvetalk porch/goblet inspirit / surrounding: claimed`, and `END`. The splitter treats the literal line as another spell: the write loses its closing delimiter, while the goblet can be inspirited under the sender’s authority. Tagged fences have the same omission.  
   **Smallest fix:** Track fences and block delimiters while segmenting; split only executable spell lines.  
   **Lane:** host.

3. **[P1] A misspelled optional field silently discards a kind’s intended law.**  
   **Evidence:** `spec/Delvetalk/Host/Spell.lean:563`, `world/objects/Kind.obend:108`, `world/objects/Kind.obend:133`, `deploy/genesis.py:110`.  
   **Failure:** Send a `kinds make` spell with valid `name` and `of`, then `voce: lunar`, then the intended maker-only `law`. Fitting stops at `voce`; subsequent fields disappear and optional `law` defaults to empty. The kind is admitted without the requested protection, and its instances admit other writers.  
   **Smallest fix:** Refuse unknown field-shaped bindings instead of truncating the remaining fields.  
   **Lane:** host.

4. **[P1] Successfully grown verbs cannot be cast by their advertised spells on standard records and things.**  
   **Evidence:** `world/objects/Record.obend:257`, `world/objects/Thing.obend:313`, `spec/Delvetalk/Host/Ops.lean:1279`, `spec/Delvetalk/Host/TurnLoop.lean:708`.  
   **Failure:** Grow `trim` on `lamp/1`, then send `delvetalk lamp/1 trim`. Its `~act` method is filtered out before `withVerbs` searches for the form needed to derive grown verbs, so `trim` has no spell form and receives `noAction`. The reader-action filter also excludes `act`.  
   **Smallest fix:** Derive grown forms from callable `act` before hiding it, and make the reader filter recognize grown verbs.  
   **Lane:** host.

5. **[P1] Several acts in one hob reading cannot see each other’s writes.**  
   **Evidence:** `spec/Delvetalk/Host/TurnLoop.lean:3009`, `spec/Delvetalk/Host/TurnLoop.lean:1555`, `world/bodies/room.obend:186`.  
   **Failure:** A resident outside the porch says “enter the porch and say hello”; hob returns `porch enter` followed by `porch say`. Entering stages presence, but `say` reads the committed state, still sees the resident outside, and refuses `notPresent`; the whole reading loses the entry too.  
   **Smallest fix:** Execute each proposed spell against the world left by the preceding spell, or provide a state overlay containing staged writes.  
   **Lane:** host.

6. **[P1] Successful town spells with no offer disappear without a receipt reply.**  
   **Evidence:** `world/bodies/bell.obend:75`, `world/objects/Record.obend:191`, `transport/bridge.py:130`, `transport/bridge.py:414`.  
   **Failure:** A resident sends `delvetalk bell/1 ring` while the bell is silent. Ringing writes its mark without offering a card. `draft_text` returns empty despite the admitted receipt and revealed consequences, and the bridge hides the empty draft. The resident receives silence after a successful change.  
   **Smallest fix:** Draft the receipt and revealed lines whenever an admitted turn changed or placed something, even without an offer; retain silence for actual conversational no-ops.  
   **Lane:** transport.

7. **[P2] HTTP reports carried receipt slugs as nonexistent even when the host resolves them.**  
   **Evidence:** `spec/Delvetalk/Host/Ops.lean:5016`, `transport/http.py:718`.  
   **Failure:** After carry, request `/AGENTS.md/receipt/<old-slug>`. The host returns `resolved` with `carried` provenance but no `receipt` or `identity`. The HTTP handler falls through and returns 404, “no receipt is named …”.  
   **Smallest fix:** Pass through resolved carried receipts and their provenance.  
   **Lane:** transport.

8. **[P2] Default HTTP refusals discard the spell template needed to recover from a bad form.**  
   **Evidence:** `transport/http.py:163`, `transport/http.py:766`, `spec/Delvetalk/Host/TurnLoop.lean:1402`.  
   **Failure:** Submit a 201-character bell rain with no policy, or let hob settle the misfit as refused. The host supplies a corrected template in `hint`, but `turn_view` removes it. `_actions` is filtered to the endpoint method `receive`, rather than the offending `rain`, so the ordinary response lacks the promised corrected spell.  
   **Smallest fix:** Preserve the host’s refusal `hint` in the default turn response.  
   **Lane:** transport.

9. **[P2] Default HTTP and play replies conceal fired rules and changed wants.**  
   **Evidence:** `spec/Delvetalk/Host/TurnLoop.lean:2310`, `transport/http.py:170`, `transport/http.py:942`.  
   **Failure:** Rain on a bell whose rule fires or whose first-rain want closes. The host returns `revealed`, but default JSON drops it, and the play page passes only stamp lines and offers to its reply renderer. The agent sees admission without what the act opened or triggered.  
   **Smallest fix:** Carry `revealed` through both response renderers.  
   **Lane:** transport.

10. **[P2] Hob cannot propose the host’s rule, want, or law-adoption spells.**  
    **Evidence:** `spec/Delvetalk/Host/TurnLoop.lean:2957`, `spec/Delvetalk/Host/TurnLoop.lean:2910`, `spec/Delvetalk/Host/TurnLoop.lean:4005`.  
    **Failure:** At a bell, ask in prose to place a rule that notes the third rain. Hob’s offered table contains object method forms, omitting the host’s `rule` spell. A correct `delvetalk bell/1 rule …` answer is rejected as an unoffered action; ordinary proposal validation also expects a compiled object method. The reading consumes quota without performing the requested act.  
    **Smallest fix:** Include permitted host spell forms and validate their proposals through the host-spell dispatcher.  
    **Lane:** host.

11. **[P2] Hob’s prompt drops the wants and help pages the host assembled for it.**  
    **Evidence:** `spec/Delvetalk/Host/TurnLoop.lean:3962`, `world/objects/Policy.obend:132`, `transport/interpret.py:33`.  
    **Failure:** Place a want with a specific answering spell, then say “answer this thing’s want.” The host assembles its reading and spell, but Policy’s `asked` type omits `wants` and `pages`; its prompt contains neither. The worker sends only that prompt and the utterance, so hob lacks the supplied answer and help material.  
    **Smallest fix:** Add and render `asked.wants` and `asked.pages` in Policy’s prompt.  
    **Lane:** objects.

12. **[P2] The commonplace’s “What wants a hand” path always falls back without listing wants.**  
    **Evidence:** `world/bodies/commonplace.obend:83`, `world/lib/World.obend:182`, `spec/Delvetalk/Host/TurnLoop.lean:949`.  
    **Failure:** In minimal genesis, bells want rain and porch things want surrounding words. Ask `commonplace since / entry: 0`. Its `world.wanting` request is absent from the host’s method allowlist, receives `noMethod`, and takes the silent fallback displaying changes alone.  
    **Smallest fix:** Implement and register `wanting`, returning readable current wants in the promised order.  
    **Lane:** host.

13. **[P2] The advertised scratch pending and delivery routes omit the principal needed to select the scratch world.**  
    **Evidence:** `transport/http.py:744`, `transport/http.py:750`, `spec/Delvetalk/Serve.lean:334`.  
    **Failure:** Open scratch `try`, then follow `/AGENTS.md/scratch/try/pending` or POST its `/deliver` control. Those requests name `world: scratch/try` but omit `principal`; serve cannot resolve the owner’s scratch and rejects the request despite authentication.  
    **Smallest fix:** Include the authenticated principal in both host requests.  
    **Lane:** transport.

14. **[P2] The paint verifier accepts truncated, uncredited resident quotations that reverse their meaning.**  
    **Evidence:** `world/lib/Paint.obend:8`, `spec/Delvetalk/Host/Enchant.lean:467`.  
    **Failure:** A stroke contains Alice’s line `the bell is dangerous only in dreams`. Paint `The bell bears “the bell is dangerous”.` passes substring quotation validation, requires no attribution, and undergoes no negation check inside the quote. The displayed excerpt contradicts the contract’s whole-line-and-credit requirement.  
    **Smallest fix:** Require resident quotations to equal a complete stroke line and carry its associated handle.  
    **Lane:** host.

15. **[P2] The served worked sessions teach deleted objects and actions as current onboarding.**  
    **Evidence:** `transport/http.py:630`, `docs/AGENTS-EXAMPLES.md:105`, `docs/AGENTS-EXAMPLES.md:126`, `spec/Delvetalk/Host/Ops.lean:3852`.  
    **Failure:** A cold agent follows `/AGENTS.md/examples`, expects verification to create Env and Wake, then copies the keyword-watch session. Arrival now creates only Avatar; the taught Wake cards and methods do not exist in fresh genesis. The guide leads the agent into failures instead of teaching rules.  
    **Smallest fix:** Replace the served captures with current-genesis sessions covering rules, wants, grown verbs, and guest access.  
    **Lane:** docs.