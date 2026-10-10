Read-only review of `foundation@a3e1fb2`. No edits, builds, or tests.

1. **Planting does not provide a working path to rain on the new bell.**  
   Evidence: [Garden.obend:152](/Users/ember/dev/delvetalk2/world/objects/Garden.obend:152), [bridge.py:345](/Users/ember/dev/delvetalk2/transport/bridge.py:345), [post.py:153](/Users/ember/dev/delvetalk2/transport/post.py:153).  
   The planting acknowledgement says “reply on its card,” but contains neither the bell’s card nor its rain spell, and the posted response retains the original garden/directory address. Replying there with `rain: a drizzle` therefore cannot write the new bell’s rains.  
   **Smallest fix:** Print the complete `delvetalk <new-bell-id> rain` spell in the planting acknowledgement. **Lane:** objects.

2. **A stranger’s first prose request to the welcome card is discarded in favour of the menu.**  
   Evidence: [Directory.obend:214](/Users/ember/dev/delvetalk2/world/objects/Directory.obend:214), [Directory.obend:354](/Users/ember/dev/delvetalk2/world/objects/Directory.obend:354).  
   A never-greeted principal saying “please plant something amber for moths” receives only the greeting, without that request reaching the interpreter. The welcome advertises acting in words immediately, but the stranger must discover that they need another turn.  
   **Smallest fix:** After recording the greeting, continue processing the original request when it names an action. **Lane:** objects.

3. **Direct form calls bypass the bounds that spells enforce.**  
   Evidence: [TurnLoop.lean:576](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:576), [TurnLoop.lean:992](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:992), [Garden.obend:87](/Users/ember/dev/delvetalk2/world/objects/Garden.obend:87).  
   Posting `fields: {"colour":"amber","seed":"<81 ASCII characters>"}` directly to `garden/plant` passes the type check and reaches planting, while the equivalent spell is refused. The published 1–80 bound consequently depends on which advertised interface the agent chooses.  
   **Smallest fix:** Validate direct external arguments against the declared form’s bounds before running the method. **Lane:** host.

4. **A stranger’s anthology admission attempt produces an admitted receipt and no explanatory card.**  
   Evidence: [Anthology.obend:43](/Users/ember/dev/delvetalk2/world/objects/Anthology.obend:43), [TurnLoop.lean:1800](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1800), [bridge.py:107](/Users/ember/dev/delvetalk2/transport/bridge.py:107).  
   A non-owner sending `delvetalk anthology admit / number: 1` returns a `refused` result as ordinary data, stages no write, and gets an admitted receipt. Because this branch offers nothing, the town receives no explanation either.  
   **Smallest fix:** Let the owner law reject the attempted admission instead of returning early with an unoffered refusal value. **Lane:** objects.

5. **Workshop holds a missing-migration error as though owner adoption could resolve it.**  
   Evidence: [Workshop.obend:105](/Users/ember/dev/delvetalk2/world/objects/Workshop.obend:105), [Ops.lean:1164](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1164), [Workshop.obend:126](/Users/ember/dev/delvetalk2/world/objects/Workshop.obend:126).  
   Proposing a compiling package with a different State and blank migration returns `stateType`, which Workshop puts into its held proposals. Even the target’s owner then gets “Only the owner … adopts” when adoption encounters the same conversion error.  
   **Smallest fix:** Treat `stateType` as a package error and preserve non-authority errors during adoption. **Lane:** objects.

6. **Successful town replies omit the receipt name needed for the advertised slug lookup.**  
   Evidence: [bridge.py:103](/Users/ember/dev/delvetalk2/transport/bridge.py:103), [bridge.py:155](/Users/ember/dev/delvetalk2/transport/bridge.py:155), [gsb-welcome-v4.txt:17](/Users/ember/dev/delvetalk2/docs/previews/gsb-welcome-v4.txt:17).  
   An admitted planting drafts only its offered card, which contains no receipt slug. Resumed prose turns likewise draft their offers without a receipt name, despite the welcome promising one on every reply.  
   **Smallest fix:** Append the named receipt line to immediate and resumed successful drafts. **Lane:** transport.

7. **The anthology’s ninth submission disappears from its acknowledgement.**  
   Evidence: [Anthology.obend:38](/Users/ember/dev/delvetalk2/world/objects/Anthology.obend:38), [Anthology.obend:67](/Users/ember/dev/delvetalk2/world/objects/Anthology.obend:67).  
   After eight short submissions, submitting a ninth returns the same first eight rows plus a remaining-count notice. The new line and its admission number are absent, and the card offers no way to page to them.  
   **Smallest fix:** Include the submitted line and its number explicitly in the acknowledgement; add a numbered-page spell for review. **Lane:** objects.

8. **Standalone bell spells and `?` requests are filtered out before the host reads them.**  
   Evidence: [observe.py:31](/Users/ember/dev/delvetalk2/transport/observe.py:31), [observe.py:43](/Users/ember/dev/delvetalk2/transport/observe.py:43), [bridge.py:174](/Users/ember/dev/delvetalk2/transport/bridge.py:174).  
   An otherwise observed standalone `delvetalk garden/bell/1 rain …` fails Python’s card-word regex, and `delvetalk garden ?` fails its action-word regex. Without a parent, mention, or summon tag, neither becomes a pending turn, although both are valid host spells.  
   **Smallest fix:** Route spell recognition through the host parser instead of the divergent Python grammar. **Lane:** transport.

9. **The welcome’s “quote your post” receipt-recovery instruction has no implementation.**  
   Evidence: [gsb-welcome-v4.txt:17](/Users/ember/dev/delvetalk2/docs/previews/gsb-welcome-v4.txt:17), [observe.py:104](/Users/ember/dev/delvetalk2/transport/observe.py:104), [http.py:563](/Users/ember/dev/delvetalk2/transport/http.py:563).  
   Quoting a previous planting with “receipt please” supplies an embedded post reference that the observation drops. No route converts that quote into receipt lookup, so following the recovery instruction yields silence or ordinary directory processing.  
   **Smallest fix:** Teach the supported authenticated receipt lookup using the original post URI as the intent. **Lane:** docs.

10. **The lending tutorial creates a grant its named recipient cannot use.**  
    Evidence: [AGENTS-API.md:160](/Users/ember/dev/delvetalk2/docs/AGENTS-API.md:160), [http.py:522](/Users/ember/dev/delvetalk2/transport/http.py:522), [hostproc.py:207](/Users/ember/dev/delvetalk2/transport/hostproc.py:207).  
    Tally’s `lend` records a grant to another DID inside the lender’s private heap. Requests authenticated as that recipient select the recipient’s own heap, where neither the Tally nor its grant exists.  
    **Smallest fix:** Replace this with a same-world, law-protected delegation example that includes the recipient’s successful `callVia`. **Lane:** docs.

11. **Usage and API controls advertise owner-only actions to strangers.**  
    Evidence: [TurnLoop.lean:803](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:803), [Anthology.obend:43](/Users/ember/dev/delvetalk2/world/objects/Anthology.obend:43), [Bell.obend:78](/Users/ember/dev/delvetalk2/world/objects/Bell.obend:78).  
    `methodAdmits` ignores every law clause that reads state, so anthology `admit` remains offered to non-owners. Bell `door` and `undoor` also remain offered although their Bend guards reject anyone except the planter, making discovery spend turns on unusable controls.  
    **Smallest fix:** Add a pure per-reader action filter, shared by usage and inspection, for these explicit owner guards. **Lane:** host.

12. **Migration failures lose the diagnostic that would tell the proposer what to correct.**  
    Evidence: [TurnLoop.lean:1293](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1293), [World.obend:81](/Users/ember/dev/delvetalk2/world/lib/World.obend:81), [Workshop.obend:105](/Users/ember/dev/delvetalk2/world/objects/Workshop.obend:105).  
    Proposing with an invalid or wrongly typed migration produces a detailed host preparation error, but `world.reprogram` discards its message. Workshop consequently offers only `Not done: migration`, without identifying the missing function or required conversion type.  
    **Smallest fix:** Carry the preparation diagnostic in the reprogram refusal and display it in Workshop. **Lane:** host.

13. **Reading someone else’s refused receipt by slug loses its object and recovery links.**  
    Evidence: [Ops.lean:3170](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:3170), [http.py:240](/Users/ember/dev/delvetalk2/transport/http.py:240), [http.py:255](/Users/ember/dev/delvetalk2/transport/http.py:255).  
    Public refused receipts carry top-level `class` and singular `root`, while `receipt_links` looks for nested `outcome` and plural `roots`. A stranger reading a law refusal therefore gets neither the source link nor the hint leading to its law.  
    **Smallest fix:** Derive controls from both the full receipt and public-refusal shapes. **Lane:** transport.

14. **Creation accepts object names whose zero-field spells cannot be parsed.**  
    Evidence: [Ops.lean:55](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:55), [Spell.lean:77](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Spell.lean:77), [Spell.lean:141](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Spell.lean:141).  
    A heap bell named `my_bell` is a valid creation, but `delvetalk my_bell ring` is rejected as a spell heading because `_` is outside the card alphabet. With no field lines to trigger bare-form fallback, the request reaches prose handling instead of ringing.  
    **Smallest fix:** Share the object-name rule between creation and spell parsing. **Lane:** host.

15. **Control-based discovery spends request quota on method information the host can already return together.**  
    Evidence: [http.py:532](/Users/ember/dev/delvetalk2/transport/http.py:532), [Ops.lean:3022](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:3022), [AGENTS-API.md:199](/Users/ember/dev/delvetalk2/docs/AGENTS-API.md:199).  
    The documented stranger walk spends fifteen object requests finding `plant` because the front never requests listing method names. Those requests consume the same 32-per-minute allowance needed for acting and recovering receipts.  
    **Smallest fix:** Expose and forward the host’s `methods: true` listing option, populating the existing item-action metadata. **Lane:** transport.