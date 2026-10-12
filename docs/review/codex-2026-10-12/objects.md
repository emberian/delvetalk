1. **Kinds without law clauses produce instances that anyone can amend or reprogram.**  
   **Evidence:** `world/objects/Kind.obend:107`, `world/objects/Kind.obend:112`, `spec/Delvetalk/Host/Law.lean:340`.  
   **Scenario:** Alice makes `kind/lamp` with the optional law omitted, then makes `lamp/1`. Its sole law follows the kind’s empty text, which admits every request. Bob can amend it to admit himself and replace its program, despite its card calling it Alice’s.  
   **Smallest fix:** Supply the base package’s owner law when the kind contains no law clauses. **Lane:** objects.

2. **Reactive receivers mistake a guest’s rule for their intended trigger.**  
   **Evidence:** `world/bodies/lantern.obend:50`, `world/bodies/front.obend:71`, `world/bodies/weather.obend:62`, `world/bodies/errand.obend:67`; sender assignment at `spec/Delvetalk/Host/Ops.lean:3230`.  
   **Scenario:** A door is shut and its lantern dark. A guest places a rule on the door that casts the lantern’s `light` on any `write`, then writes a line. The delivery’s sender is the door, so the lantern lights without the door opening. Equivalent rules prematurely fill fronts or settle errands with an arbitrary `by`.  
   **Smallest fix:** Authenticate the rule owner against the maker and recheck the required source condition. **Lane:** objects.

3. **A guest-owned object can add itself to another principal’s holding list.**  
   **Evidence:** `world/objects/Avatar.obend:127`, `world/objects/Avatar.obend:130`, `world/objects/Avatar.obend:37`.  
   **Scenario:** Bob’s object calls `hold` on Alice’s avatar under Bob’s principal. The nonempty caller passes; neither the method nor its law requires Alice’s consent. Alice’s card now reports holding Bob’s object without acquisition or acceptance.  
   **Smallest fix:** Require `mine(context)` in `hold`; legitimate acquisition already runs as the holder. **Lane:** objects.

4. **The Avatar’s principal-only placement restriction never executes.**  
   **Evidence:** `world/objects/Avatar.obend:37`, `spec/Delvetalk/Host/Ops.lean:2549`, `spec/Delvetalk/Host/Law.lean:81`.  
   **Scenario:** Bob places a rule or want on Alice’s avatar. Placements are kind 4, but the host invokes Bend predicates only for kinds 0 and 3. The default text law admits kind 4, so the placement succeeds despite the stated restriction.  
   **Smallest fix:** Include kind-4 placements in predicate admission. **Lane:** host.

5. **A bond silently excludes every party after the fifteenth.**  
   **Evidence:** `world/bodies/bond.obend:31`, `world/bodies/bond.obend:45`, `world/bodies/bond.obend:72`; accepted input at `deploy/genesis.py:160`.  
   **Scenario:** A bond names sixteen short handles within the 400-character input bound. The first fifteen countersign; the bond reaches rest and attempts its amendment without the sixteenth party’s signature. That party cannot countersign because the parser excluded them.  
   **Smallest fix:** Reject excess parties before creating the bond instead of truncating them. **Lane:** objects.

6. **An errand can become permanently done without paying its reward.**  
   **Evidence:** `world/bodies/errand.obend:58`, `world/bodies/errand.obend:62`, `world/bodies/errand.obend:75`; firing limit at `spec/Delvetalk/Host/Ops.lean:3227`.  
   **Scenario:** Seven earlier rules on the target fire alongside an errand’s completion condition. Settlement is the eighth firing; payment is omitted by the eight-rule limit. Settlement nevertheless removes both rules and marks the errand done, leaving no payment retry.  
   **Smallest fix:** Mark completion and remove the rules only after an admitted payment receipt. **Lane:** objects.

7. **Weather aborts its entire rain when a garden holds 32 eligible bells.**  
   **Evidence:** `world/bodies/weather.obend:65`, `world/bodies/weather.obend:71`, `world/bodies/weather.obend:78`, `spec/Delvetalk/Host/TurnLoop.lean:2160`.  
   **Scenario:** A tended garden holds 32 bells. The weather stages one forecast delivery plus 32 rain deliveries. The thirty-third send raises an evaluation failure, refusing the entire turn: none of the bells receives rain.  
   **Smallest fix:** Reserve the forecast’s slot and send to at most 31 bells per turn, continuing larger gardens separately. **Lane:** objects.

8. **A front’s clock stops advancing after its retained fill history reaches capacity.**  
   **Evidence:** `world/bodies/front.obend:55`, `world/bodies/front.obend:65`, `world/bodies/front.obend:73`, `world/objects/Record.obend:130`.  
   **Scenario:** A four-segment front receives 128 fills. Every subsequent fill evicts an old line, leaving the filtered count at 128. The move rule’s required count increase becomes permanently false; the card remains at zero of four while new fills repeatedly claim segment one.  
   **Smallest fix:** Keep a monotone fill counter and use it for the clock and move rule. **Lane:** objects.

9. **Retention can suppress a record’s pending-line want while a line remains pending.**  
   **Evidence:** `world/objects/Record.obend:132`, `world/objects/Record.obend:145`, `world/objects/Record.obend:184`.  
   **Scenario:** A keeper admits lines 1–128, then someone writes line 129. Retention drops line 1 but retains its admission. Both relations still contain 128 rows, so `pending` is false although line 129 renders as pending.  
   **Smallest fix:** Track pending rows directly, removing them on admission and synchronizing their retention with lines. **Lane:** objects.

10. **Reactive objects present themselves as operational when rule installation failed.**  
    **Evidence:** `world/bodies/errand.obend:60`, `world/bodies/errand.obend:64`, `world/objects/Kind.obend:179`, `world/bodies/errand.obend:84`.  
    **Scenario:** A guest makes an errand targeting `policy`, whose law refuses that guest’s rule placement. The callback returns `false`, while creation remains successful and the errand card still advertises its condition and payment. It can never settle automatically.  
    **Smallest fix:** Preserve and display the placement refusal, with an explicit inactive state until installation succeeds. **Lane:** objects.

11. **Generated rule names collapse distinct object identities.**  
    **Evidence:** `world/lib/Text.obend:47`, `world/bodies/lantern.obend:46`, `spec/Delvetalk/Host/Ops.lean:2627`.  
    **Scenario:** Two lanterns named `lamp-a` and `lamp_a` watch the same door. Both derive the rule name `lamp_a`. The second installation is refused as already taken, so only the first lantern lights when the door opens.  
    **Smallest fix:** Use an injective identifier encoding that also escapes underscores. **Lane:** objects.

12. **Copying an extended Thing discards its program.**  
    **Evidence:** `world/objects/Thing.obend:213`, `spec/Delvetalk/Host/TurnLoop.lean:524`.  
    **Scenario:** Alice extends a Thing with a `shine` method and permits copying. Bob requests a copy. The hardcoded `"Thing"` package selects the base module and excludes Alice’s layer; the resulting copy cannot shine.  
    **Smallest fix:** Create the copy from the executing object’s sealed package. **Lane:** objects.

13. **Several renderers exceed the card budget with valid inputs.**  
    **Evidence:** `world/objects/Thing.obend:277`, `world/objects/Thing.obend:280`, `world/objects/Workshop.obend:239`, `world/objects/Library.obend:139`; budget at `world/lib/Card.obend:112`.  
    **Scenario:** A Thing with a 400-character description and three 280-character act lines already contributes 1,240 characters before its name, attribution and spells. Workshop adds a 1,200-character list allowance after its usage text; Library prints all 32 permitted pages without clipping. These cards exceed `Card.limit` and lose content at the posting surface.  
    **Smallest fix:** Allocate one remaining budget across every rendered section using `Card.left` and `Card.clippedWithin`. **Lane:** objects.

14. **The seventh-rain rule counts grown gestures as rains.**  
    **Evidence:** `deploy/genesis.py:123`, `world/objects/Record.obend:155`, `world/objects/Record.obend:158`.  
    **Scenario:** A guest grows `water` on a fresh bell and uses it six times, then supplies one rain. Seven total lines trigger `seven`, ringing the bell after only one rain despite the rule’s reading.  
    **Smallest fix:** Filter both counts to `verb == "rain"`; explicitly handle carried lines whose verb is empty. **Lane:** objects.