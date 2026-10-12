1. **[P1] Live backups can preserve transport completion markers for turns missing from the backed-up journal.**  
   Evidence: [deploy/backup.sh:35](/Users/ember/dev/delvetalk2-lanes/review2/deploy/backup.sh:35), [transport/bridge.py:357](/Users/ember/dev/delvetalk2-lanes/review2/transport/bridge.py:357).  
   **Scenario:** The backup copies the journal at height H; the bridge then commits H+1 and writes its draft; rsync subsequently copies that draft. After restoration, the observation exists but `draft_exists` suppresses its turn, so the restored world never receives the acknowledged write. Journal verification passes.  
   **Smallest fix:** Quiesce all writers while copying the journal and transport state, or reconcile completion markers against retained host receipts on restore.  
   **Lane:** transport.

2. **[P1] Concurrent posting of one intent can create two external posts under one reservation.**  
   Evidence: [transport/post.py:113](/Users/ember/dev/delvetalk2-lanes/review2/transport/post.py:113), [transport/post.py:126](/Users/ember/dev/delvetalk2-lanes/review2/transport/post.py:126).  
   **Scenario:** Two Post requests read an absent ledger before either writes it. Both receive the same host reservation, independently choose time-dependent record keys, and send `createRecord`. Both posts land; only one result survives locally, and the second registration cannot settle the already-posted reservation.  
   **Smallest fix:** Hold a per-intent process-safe lock across ledger lookup, network delivery, and result persistence.  
   **Lane:** transport.

3. **[P1] Addressed private offers are copied into public drafts without a host-approved public projection.**  
   Evidence: [transport/bridge.py:125](/Users/ember/dev/delvetalk2-lanes/review2/transport/bridge.py:125), [transport/zulip.py:235](/Users/ember/dev/delvetalk2-lanes/review2/transport/zulip.py:235), [transport/http.py:378](/Users/ember/dev/delvetalk2-lanes/review2/transport/http.py:378).  
   **Scenario:** Alice can read a private record; Bob cannot. Alice requests its lines through Zulip. The host offers the private text to Alice, but the bridge automatically posts it into their shared channel. The HTTP path similarly drafts every offer when merely one write in the transaction is public, including offers containing privately read data.  
   **Smallest fix:** Have the host return publishable reply text for the channel’s reader authority; draft only that projection.  
   **Lane:** transport.

4. **[P1] The HTTP healthcheck always rejects the current home-page markup.**  
   Evidence: [transport/watch.py:66](/Users/ember/dev/delvetalk2-lanes/review2/transport/watch.py:66), [transport/static/pages.html:13](/Users/ember/dev/delvetalk2-lanes/review2/transport/static/pages.html:13).  
   **Scenario:** A functioning front returns `<p class="shelf">entry 73 · …</p>`. The healthcheck requires `class="code">entry <digits><`, which the page does not emit. Compose marks the front unhealthy and `up --wait` fails on an otherwise functioning deployment.  
   **Smallest fix:** Match the current shelf markup, as `deploy/smoke.sh` already does, or use a structured health response.  
   **Lane:** transport.

5. **[P1] OAuth credentials remain authoritative after their recorded thirty-day expiry.**  
   Evidence: [transport/oauth.py:205](/Users/ember/dev/delvetalk2-lanes/review2/transport/oauth.py:205), [transport/identity.py:203](/Users/ember/dev/delvetalk2-lanes/review2/transport/identity.py:203).  
   **Scenario:** An OAuth credential is issued at T with `expires = T + KEEP`. At T+31 days, sending it as a bearer token still authenticates because the query checks only `state='verified'`. Cookie expiry does not revoke the credential.  
   **Smallest fix:** Enforce a session-expiry field during authentication; keep challenge deadlines and session lifetimes separate.  
   **Lane:** transport.

6. **[P1] The session cookie lacks `Secure`, allowing plaintext disclosure on HTTP requests.**  
   Evidence: [transport/http.py:577](/Users/ember/dev/delvetalk2-lanes/review2/transport/http.py:577).  
   **Scenario:** A client holds a credential cookie for the HTTPS origin but has no applicable HSTS policy. It requests that hostname over HTTP. The cookie is transmitted before any HTTPS redirect, exposing a reusable credential to a network observer.  
   **Smallest fix:** Add `Secure` whenever the configured origin uses HTTPS.  
   **Lane:** transport.

7. **[P1] Unauthenticated verification requests can exhaust another person’s challenge attempts.**  
   Evidence: [transport/identity.py:113](/Users/ember/dev/delvetalk2-lanes/review2/transport/identity.py:113), [transport/identity.py:131](/Users/ember/dev/delvetalk2-lanes/review2/transport/identity.py:131), [transport/identity.py:150](/Users/ember/dev/delvetalk2-lanes/review2/transport/identity.py:150).  
   **Scenario:** Alice has one pending challenge. An attacker sends eight `/verify` requests naming Alice’s handle, without her credential and with an invalid proof URI. `_rows` falls back to Alice’s challenges, and `_begin` consumes an attempt before parsing the URI. Alice’s genuine proof then fails with `too_many_attempts`.  
   **Smallest fix:** Require the requesting challenge’s credential and debit only that challenge.  
   **Lane:** transport.

8. **[P1] Multi-spell posts lose usage answers and suspended turns’ eventual replies.**  
   Evidence: [transport/bridge.py:383](/Users/ember/dev/delvetalk2-lanes/review2/transport/bridge.py:383), [transport/bridge.py:387](/Users/ember/dev/delvetalk2-lanes/review2/transport/bridge.py:387), [spec/Delvetalk/Host/TurnLoop.lean:3282](/Users/ember/dev/delvetalk2-lanes/review2/spec/Delvetalk/Host/TurnLoop.lean:3282).  
   **Scenario:** One post contains `delvetalk bell/1 rain / text: hello` followed by `delvetalk bell/1 ?`. The rain commits, but the receipt-less usage result makes the bridge discard the entire response on every poll. If a segment suspends instead, the bridge writes a final draft without an awaiting record; its eventual offer is never collected.  
   **Smallest fix:** Handle each segment by host status, retaining usage text and tracking suspended segment identities separately.  
   **Lane:** transport.

9. **[P1] The library-update command fails after deleting the live library directory because it requires deleted packages.**  
   Evidence: [deploy/library-update.sh:32](/Users/ember/dev/delvetalk2-lanes/review2/deploy/library-update.sh:32), [deploy/library-update.sh:34](/Users/ember/dev/delvetalk2-lanes/review2/deploy/library-update.sh:34).  
   **Scenario:** Run the documented library update against this tree. It removes and reconstructs `<state>/library`, copies Avatar, then raises `FileNotFoundError` for `world/objects/Env.obend`; Env and Wake are absent. No `world-library` request is sent, and the filesystem library has already changed.  
   **Smallest fix:** Copy only Avatar and prepare the replacement in a temporary directory before replacing the live directory.  
   **Lane:** transport.

10. **[P1] Carry overwrites the destination configuration after using it to choose the new host and library.**  
    Evidence: [transport/carry.py:67](/Users/ember/dev/delvetalk2-lanes/review2/transport/carry.py:67), [transport/carry.py:189](/Users/ember/dev/delvetalk2-lanes/review2/transport/carry.py:189), [deploy/playtest.sh:74](/Users/ember/dev/delvetalk2-lanes/review2/deploy/playtest.sh:74).  
    **Scenario:** Carry a playtest configured for port 8765 using `--port 18775`. The script writes the new configuration, and carry initially reads it. `copy_transport` then replaces it with the old `delvetalk.toml`; the new front listens on 8765, potentially colliding with another service and ignoring the requested origin.  
    **Smallest fix:** Exclude `delvetalk.toml` from the later copy when the destination already supplies one.  
    **Lane:** transport.

11. **[P2] Scratch-world interpretations have no model worker servicing them.**  
    Evidence: [transport/interpret.py:77](/Users/ember/dev/delvetalk2-lanes/review2/transport/interpret.py:77), [transport/interpret.py:37](/Users/ember/dev/delvetalk2-lanes/review2/transport/interpret.py:37), [spec/Delvetalk/Host/Session.lean:386](/Users/ember/dev/delvetalk2-lanes/review2/spec/Delvetalk/Host/Session.lean:386).  
    **Scenario:** Alice forks town into scratch `try` and sends prose to its commonplace. The scratch session retains an interpretation, but the deployed worker queries only town’s session. Town continues interpreting while Alice’s scratch turn remains suspended.  
    **Smallest fix:** Enumerate host-reported scratch worlds and service their jobs with the corresponding world and principal envelope.  
    **Lane:** transport.

12. **[P2] Scratch pending and delivery HTTP routes omit the principal required to select the world.**  
    Evidence: [transport/http.py:745](/Users/ember/dev/delvetalk2-lanes/review2/transport/http.py:745), [transport/http.py:750](/Users/ember/dev/delvetalk2-lanes/review2/transport/http.py:750), [spec/Delvetalk/Serve.lean:335](/Users/ember/dev/delvetalk2-lanes/review2/spec/Delvetalk/Serve.lean:335).  
    **Scenario:** An authenticated Alice requests `/AGENTS.md/scratch/try/pending` or posts to `/deliver`. The front sends `world: scratch/try` without `principal`; serve attempts to resolve an empty scratch owner and returns “a scratch world is a principal’s: name the principal.”  
    **Smallest fix:** Include the authenticated principal in both requests.  
    **Lane:** transport.

13. **[P2] Slot serialization corrupts identities whose intent contains a colon.**  
    Evidence: [transport/bridge.py:32](/Users/ember/dev/delvetalk2-lanes/review2/transport/bridge.py:32), [transport/post.py:62](/Users/ember/dev/delvetalk2-lanes/review2/transport/post.py:62).  
    **Scenario:** The host returns slot `{principal: "did:plc:alice", intent: "task:1"}`. The draft stores `did:plc:alice:task:1`; posting reconstructs `{principal: "did:plc:alice:task", intent: "1"}`. Replies are consequently attached to the wrong slot, leaving the original waiter unanswered. AT-URI intents have the same problem.  
    **Smallest fix:** Preserve the host’s structured slot object in drafts and pass it unchanged to `world-posted`.  
    **Lane:** transport.

14. **[P2] Default HTTP and browser act replies discard the host’s revealing lines.**  
    Evidence: [transport/http.py:170](/Users/ember/dev/delvetalk2-lanes/review2/transport/http.py:170), [transport/http.py:942](/Users/ember/dev/delvetalk2-lanes/review2/transport/http.py:942), [transport/bridge.py:179](/Users/ember/dev/delvetalk2-lanes/review2/transport/bridge.py:179).  
    **Scenario:** A rain fires a rule and closes a want; the host returns those facts in `revealed`. The default JSON reply exposes only the turn line, offers, and receipt location; the play page likewise omits the revelations. Resumed bridge replies reconstruct offers and a receipt without them. Agents cannot tell what the act moved without additional inspection.  
    **Smallest fix:** Carry the host-rendered `revealed` lines through each reply projection, including resumed replies.  
    **Lane:** transport.

15. **[P2] Repository object and law listings ignore the requested limit and advance the cursor past excess records.**  
    Evidence: [transport/repo.py:262](/Users/ember/dev/delvetalk2-lanes/review2/transport/repo.py:262), [transport/repo.py:271](/Users/ember/dev/delvetalk2-lanes/review2/transport/repo.py:271).  
    **Scenario:** With more than 64 readable objects, request object records with `limit=1`. The façade returns the host’s whole 64-object page and a cursor after object 64. A consumer processing its requested one-record page and following that cursor skips 63 objects. Law listings can expand each object into several records while using the same object-level cursor.  
    **Smallest fix:** Honor the record limit and use a cursor containing object ID plus law ordinal for law pages.  
    **Lane:** transport.