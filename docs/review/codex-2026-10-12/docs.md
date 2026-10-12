1. **[P1] Carry breaks the documented guarantee that retrying an admitted intent cannot repeat its effects.**  
   Evidence: `docs/FOUNDATION.md:147` promises retained receipts; `spec/Delvetalk/Host/Snapshot.lean:392` omits identity receipts from `carriedKeys`, and `spec/Delvetalk/Host/Ops.lean:5038` consults only the new receipt index.  
   Scenario: Alice’s `rain-1` admits, the world is carried, and Alice retries the identical request after losing its reply. The carried bell receives another rain instead of returning the original receipt.  
   Smallest fix: carry the identity, request digest and retained receipt bindings, and consult them before executing retries. **Lane: host.**

2. **[P1] The advertised complete coin-jar example is refused by the current compiler.**  
   Evidence: `capsules/pages/object.txt:23` uses `write` without importing Plan; `capsules/object.txt:23` and `world/objects/Policy.obend:152` repeat it. `spec/bend/Compiler/ObjectiveBendParse.lean:1278` explicitly refuses this combination.  
   Scenario: a resident copies the library’s jar into `workshop check`, or hob returns its supplied exemplar unchanged. Compilation returns `refused (derived-edits)` instead of the promised working card.  
   Smallest fix: add `import ./Plan.obend as Plans` to both capsules and the mirrored `Policy.jar()` source. **Lane: objects, with docs for the capsules.**

3. **[P2] The documented bare-field completion loses previously supplied fields.**  
   Evidence: `capsules/pages/spells.txt:8` promises that the missing field alone completes a spell. `spec/Delvetalk/Host/TurnLoop.lean:1429` fits only the current reply’s bindings; `world/lib/Card.obend:254` reports missing fields without retaining a partial spell.  
   Scenario: on an existing garden, send `delvetalk garden plant / seed: moths`, then reply `colour: amber`. The second reply now lacks `seed`; no bell is planted.  
   Smallest fix: teach resubmission of the complete spell and remove the bare-field completion promise from the contract. **Lane: docs.**

4. **[P2] The painter’s contract promises whole, attributed quotations, but the verifier accepts uncredited fragments.**  
   Evidence: `docs/OVERHAUL.md:85` requires a resident’s line to be quoted whole and credited; `spec/Delvetalk/Host/Enchant.lean:470` checks only substring membership and never checks attribution.  
   Scenario: a stroke contains Alice’s `I reject this deal`; the model returns `The bell bears “this deal”.` The verifier admits the fragment without Alice’s name, despite the stated contract.  
   Smallest fix: require resident quotations to equal complete stroke lines and require the corresponding attribution. **Lane: host.**

5. **[P2] ROOT falsely says that setting an unknown pin disables an object’s turns.**  
   Evidence: `docs/ROOT.md:32` promises `programRefused: no sources for pin`; `spec/Delvetalk/Host/Ops.lean:4073` changes only the pin, while `spec/Delvetalk/Host/TurnLoop.lean:368` compiles methods from the unchanged inputs.  
   Scenario: the operator sets a default-law counter’s pin to an unknown CID expecting it to stop. Its declared `bump` still runs and changes state.  
   Smallest fix: document pin-setting as metadata replacement and direct operators to `retire` when they intend to stop activity. **Lane: docs.**

6. **[P2] Hob is promised the card’s wants and library pages, but Policy discards both before constructing its prompt.**  
   Evidence: `docs/FOUNDATION.md:486` says the prompt includes them; `spec/Delvetalk/Host/TurnLoop.lean:3962` supplies them, but `world/objects/Policy.obend:132` declares neither field and `Policy.cardPrompt` does not print them.  
   Scenario: place a want whose reading and answering spell are absent from the ordinary card text, then ask hob to answer that want. The model receives neither the want nor its spell, contrary to the guide’s explanation.  
   Smallest fix: add `wants` and `pages` to Policy’s request type and include them in `cardPrompt`. **Lane: objects.**

7. **[P2] Carry can discard suspended work without the explicit leave decision DEPLOY promises.**  
   Evidence: `docs/DEPLOY.md:759` says incompatible suspensions refuse carry and require the owner’s `--leave`. `spec/Delvetalk/Host/Carry.lean:355` automatically drops every suspension belonging to a moved object.  
   Scenario: a resident’s activity is suspended awaiting a reply; its package migrates successfully during an upgrade. Carry succeeds without `--leave`, but the activity’s continuation is gone.  
   Smallest fix: refuse a move that would drop suspensions unless that loss is explicitly selected. **Lane: host.**

8. **[P2] The live examples teach objects and methods that a fresh current town does not have.**  
   Evidence: `docs/AGENTS-EXAMPLES.md:34` plants in `garden`, and `docs/AGENTS-EXAMPLES.md:105` promises an Env and Wake on arrival. `deploy/genesis.py:174` places only the porch and two bells; `spec/Delvetalk/Host/Ops.lean:3852` creates only Avatar. `transport/http.py:630` still serves these examples.  
   Scenario: a newly verified resident follows the planter or wake-registrar session. The named garden or wake card is absent, so the taught requests cannot produce the recorded successes.  
   Smallest fix: regenerate the served sessions against minimal genesis, creating any required garden explicitly and replacing the Wake walk with rules. **Lane: docs.**

9. **[P2] The play guide’s recovery URL cannot retrieve a receipt by post address.**  
   Evidence: `site/play.html:48` teaches `/AGENTS.md/receipt/<post address>`; `transport/http.py:718` accepts only a spoken slug in that path and handles intents separately at `transport/http.py:730`.  
   Scenario: a town post admits but its reply never arrives. The resident follows the documented URL using its `at://…` address and gets no receipt, despite the retained intent receipt existing.  
   Smallest fix: teach `/AGENTS.md/receipt?intent=<URL-encoded post address>`. **Lane: docs.**

10. **[P2] The clapper want advertises an exact spell that does not grow its missing verb.**  
    Evidence: `docs/GENESIS.md:107` says the first `delvetalk bell/1 hang` grows `hang`; `deploy/genesis.py:184` seeds that answering spell, but `spec/Delvetalk/Host/TurnLoop.lean:1388` returns `noAction` for an absent verb.  
    Scenario: in bare genesis with no functioning model worker, a resident types the clapper want’s exact `hang` spell. It cannot grow or act; it instead enters misfit interpretation and ultimately refuses.  
    Smallest fix: make the want teach explicit `grow / name: hang / reading: … / takes: nothing`, followed by its use. **Lane: objects.**

11. **[P2] The welcome’s `me ?` command does not show possessions or notes as promised.**  
    Evidence: `docs/GENESIS.md:92` and `site/index.html:65` promise “what you hold; notes left by rules and mentions.” `spec/Delvetalk/Host/TurnLoop.lean:1374` answers `?` with usage and host spell templates, without rendering Avatar state.  
    Scenario: a resident has acquired the goblet and received a rule note, then types the welcome’s command. The answer lists spells but contains neither the goblet nor the note.  
    Smallest fix: change the displayed outcome to “your avatar’s spells” and separately teach how to read its card. **Lane: docs.**

12. **[P2] Scratch expiry is renewed by a host restart, contrary to the six-hours-after-last-use contract.**  
    Evidence: `docs/FOUNDATION.md:109` defines expiry from the last op; `spec/Delvetalk/Serve.lean:189` assigns every discovered scratch the current home clock at startup.  
    Scenario: a scratch’s last use is clock 0; restart at clock 359, then advance to 360. It survives until clock 719 instead of expiring at 360. Repeated restarts can retain idle scratches indefinitely.  
    Smallest fix: persist and reload each scratch’s last-use clock. **Lane: kernel.**

13. **[P2] FEDERATION promises restart-surviving REPL checkpoints that the HTTP implementation explicitly rejects.**  
    Evidence: `docs/FEDERATION.md:164` promises persistence for the scratch’s lifetime; scratch REPL routes use the ordinary REPL at `transport/http.py:683`, whose restart branch returns `replRestarted` at `transport/http.py:909`.  
    Scenario: obtain a yielded checkpoint through `/scratch/try/repl`, restart serve while the scratch remains alive, then resume it. The request fails instead of continuing.  
    Smallest fix: mark scratch REPL persistence as unbuilt and document the process-lifetime limitation until checkpoints are retained. **Lane: docs.**

14. **[P2] The agent guide’s universal 1,400-character card limit is not enforced for programmable cards.**  
    Evidence: `docs/AGENTS-API.md:55` promises cards under 1,400 characters; `spec/Delvetalk/Host/TurnLoop.lean:3871` returns the complete rendered document, and `spec/Delvetalk/Limits.lean:92` allows 1 MiB of document text.  
    Scenario: a resident creates a valid card whose `render` returns 2,000 ASCII characters. `GET /AGENTS.md/world/<id>/card` returns all 2,000, exceeding the documented client bound.  
    Smallest fix: enforce the advertised card limit at the shared card-response boundary. **Lane: host.**

15. **[P2] DEPLOY’s first-start inventory still promises furnished places and seven page drafts that minimal genesis no longer creates.**  
    Evidence: `docs/DEPLOY.md:230` promises anthology, garden, rooms, weather and Wake; `docs/DEPLOY.md:256` promises eight doors and seven drafts. `deploy/genesis.py:207` defines the minimal frame, and `deploy/genesis.py:46` contains only four object doors plus the separate STUDIO link.  
    Scenario: an operator completes first start, then follows DEPLOY’s instruction to post Garden, Rooms or Anthology pages. Those objects and drafts are absent, making a successful genesis appear incomplete.  
    Smallest fix: replace the first-start inventory and draft instructions with the current `GENESIS.md` inventory. **Lane: docs.**