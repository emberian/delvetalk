Read-only source review of `a3e1fb2`; no edits, builds or tests.

1. **P1 — A healthy front always fails the deployment healthcheck.**  
   Evidence: [compose.yml:101](/Users/ember/dev/delvetalk2/deploy/compose.yml:101), [pages.html:8](/Users/ember/dev/delvetalk2/transport/static/pages.html:8), [smoke.sh:59](/Users/ember/dev/delvetalk2/deploy/smoke.sh:59).  
   Compose requires `journal height</dt><dd>`, but the current home page renders the height as `<span class="code">ht.N</span>`. Consequently `up --wait` fails for a functioning front, and the smoke script also rejects its current heading and height markup.  
   **Smallest fix:** Update both checks to recognize the current height element. **Lane:** transport.

2. **P1 — Retrying a post can duplicate it, while failed host registration can permanently orphan it.**  
   Evidence: [post.py:125](/Users/ember/dev/delvetalk2/transport/post.py:125), [post.py:151](/Users/ember/dev/delvetalk2/transport/post.py:151), [zulip.py:178](/Users/ember/dev/delvetalk2/transport/zulip.py:178).  
   A crash after external posting but before saving the draft’s completion causes another external post on retry: Delve’s `intent` is only logged, and Zulip’s send has no persisted delivery identity. Conversely, Delve’s `post_draft` marks the draft posted even when `world-posted` returns an error, without retaining the result in that draft for registration recovery.  
   **Smallest fix:** Persist posting stages and returned references; use a deterministic Delve record key and retry host registration independently of external sending. **Lane:** transport.

3. **P1 — A live backup can restore interpretations that Python permanently refuses to settle.**  
   Evidence: [backup.sh:21](/Users/ember/dev/delvetalk2/deploy/backup.sh:21), [interpret.py:46](/Users/ember/dev/delvetalk2/transport/interpret.py:46), [interpret.py:66](/Users/ember/dev/delvetalk2/transport/interpret.py:66).  
   If rsync copies the journal before an interpretation settles and copies its receipt file afterward, the backup contains a pending host request beside `settled: true`. After restoration, `interpret.run` sees that pending request but skips it indefinitely because the local flag overrides the host’s facts.  
   **Smallest fix:** When the host lists a request as pending, re-submit its saved reply regardless of the local settled flag. **Lane:** transport.

4. **P1 — Slow clients can hold unbounded worker threads beyond the advertised request deadline.**  
   Evidence: [http.py:263](/Users/ember/dev/delvetalk2/transport/http.py:263), [http.py:328](/Users/ember/dev/delvetalk2/transport/http.py:328), [http.py:384](/Users/ember/dev/delvetalk2/transport/http.py:384), [compose.yml:95](/Users/ember/dev/delvetalk2/deploy/compose.yml:95).  
   A client sending another request byte within each 30-second socket timeout can keep its worker occupied far longer than the advertised 30-second request limit. Thread creation has no application bound, so enough such connections exhaust the front’s 64-task container limit before routing or authentication limits help.  
   **Smallest fix:** Bound concurrent workers and enforce an absolute deadline for receiving headers and bodies. **Lane:** transport.

5. **P2 — The documented hand setup exposes the owner console through public Caddy.**  
   Evidence: [DEPLOY.md:142](/Users/ember/dev/delvetalk2/docs/DEPLOY.md:142), [compose.yml:8](/Users/ember/dev/delvetalk2/deploy/compose.yml:8), [http.py:451](/Users/ember/dev/delvetalk2/transport/http.py:451), [hand.py:197](/Users/ember/dev/delvetalk2/transport/hand.py:197).  
   Following the runbook adds the hand token and posting credentials to the same front already reachable through Caddy’s public reverse proxy. An SSH forward does not make `/hand/` private: its token login remains publicly reachable, contradicting the prescribed access boundary.  
   **Smallest fix:** Serve the hand on a separate loopback listener reached only through SSH. **Lane:** transport.

6. **P2 — Anonymous object pages bypass request limits while exercising the shared host.**  
   Evidence: [http.py:477](/Users/ember/dev/delvetalk2/transport/http.py:477), [http.py:486](/Users/ember/dev/delvetalk2/transport/http.py:486), [http.py:755](/Users/ember/dev/delvetalk2/transport/http.py:755), [http.py:760](/Users/ember/dev/delvetalk2/transport/http.py:760).  
   Repeated anonymous `GET /o/garden` requests never call `limited`, although each request asks the host for state, card, inspection and journal history. This provides an unrestricted route into the serialized host workload despite the limits applied to equivalent API and XRPC reads.  
   **Smallest fix:** Apply address-based admission limits to public routes before issuing host requests. **Lane:** transport.

7. **P2 — Python’s spell classifier silently drops spells the host accepts.**  
   Evidence: [observe.py:31](/Users/ember/dev/delvetalk2/transport/observe.py:31), [observe.py:43](/Users/ember/dev/delvetalk2/transport/observe.py:43), [bridge.py:174](/Users/ember/dev/delvetalk2/transport/bridge.py:174), [Spell.lean:77](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Spell.lean:77).  
   An observed standalone, unmentioned `delvetalk garden ?` is classified as ordinary traffic because Python’s action regex rejects `?`, and a spell naming `garden/bell/1` fails its card regex. These posts never reach the host, whose grammar explicitly accepts both inputs, so routing is decided by a conflicting Python parser.  
   **Smallest fix:** Have the host classify and address observed text using its existing spell parser. **Lane:** transport.

8. **P2 — Posting a publication through the hand loses its object address.**  
   Evidence: [bridge.py:275](/Users/ember/dev/delvetalk2/transport/bridge.py:275), [post.py:152](/Users/ember/dev/delvetalk2/transport/post.py:152), [hand.py:150](/Users/ember/dev/delvetalk2/transport/hand.py:150).  
   Publication drafts store their object under `publication.object`, but `post_draft` reads only the top-level `object`. Clicking Post on a genesis page therefore publishes it and marks it completed without calling `world-posted`, leaving replies and subsequent section edits without the recorded page address.  
   **Smallest fix:** Resolve the object from `publication.object` when the top-level field is absent, including the CLI draft path. **Lane:** transport.

9. **P2 — Posting quota admission depends on Python’s directory and wall clock.**  
   Evidence: [post.py:108](/Users/ember/dev/delvetalk2/transport/post.py:108), [post.py:128](/Users/ember/dev/delvetalk2/transport/post.py:128), [DEPLOY.md:124](/Users/ember/dev/delvetalk2/docs/DEPLOY.md:124), [hand.py:150](/Users/ember/dev/delvetalk2/transport/hand.py:150).  
   The welcome command counts posts under `/data/state/post`, while the hand counts them under `/data/state`, allowing two independent allowances against one host quota. Admission also consumes slots before credential loading or network success and changes with local wall time rather than journaled host facts.  
   **Smallest fix:** Move quota reservations and their outcomes into a host operation keyed by posting intent. **Lane:** host.

10. **P2 — Python decides whether model failures become host outcomes.**  
    Evidence: [interpret.py:33](/Users/ember/dev/delvetalk2/transport/interpret.py:33), [interpret.py:55](/Users/ember/dev/delvetalk2/transport/interpret.py:55), [TurnLoop.lean:2510](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:2510).  
    The same failed model result is hidden from the host on attempts one through seven but submitted on attempt eight, according to a local receipt file. That submission becomes a journaled `unclear` verdict, so Python’s counter and failure classification determine the activity’s outcome and additional credit spending.  
    **Smallest fix:** Journal attempts and retry decisions in the host; submit each transport result verbatim. **Lane:** host.

11. **P2 — Python suppresses host refusals based on the input’s wording.**  
    Evidence: [bridge.py:186](/Users/ember/dev/delvetalk2/transport/bridge.py:186), [bridge.py:349](/Users/ember/dev/delvetalk2/transport/bridge.py:349), [TurnLoop.lean:1164](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1164).  
    Once a principal has exhausted its interpretation quota, an ordinary prose reply to a recorded Garden card receives a host `quota` refusal. Unless that prose contains Python’s selected markers, the bridge replaces the refusal draft with empty text, so the participant never receives the host’s explanation or next step.  
    **Smallest fix:** Make refusal visibility a host fact and draft that projection without inspecting the original text. **Lane:** transport.

12. **P2 — Height-only repository cursors skip records sharing an entry.**  
    Evidence: [repo.py:133](/Users/ember/dev/delvetalk2/transport/repo.py:133), [repo.py:139](/Users/ember/dev/delvetalk2/transport/repo.py:139), [Ops.lean:3259](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:3259).  
    Listing sources with `limit=1` returns one source from a multi-module library entry and uses that entry’s height as the cursor. The next request selects strictly greater heights, permanently skipping the remaining sources from that entry; publications and grants have the same boundary problem.  
    **Smallest fix:** Page by a stable `(height, item)` cursor or preserve complete height groups. **Lane:** host.

13. **P2 — HTML and plain-text API reads discard the authenticated bearer principal.**  
    Evidence: [http.py:505](/Users/ember/dev/delvetalk2/transport/http.py:505), [http.py:525](/Users/ember/dev/delvetalk2/transport/http.py:525), [http.py:750](/Users/ember/dev/delvetalk2/transport/http.py:750).  
    A valid bearer request for a restricted object succeeds as JSON, but adding `Accept: text/html` or `?text=1` calls `object_page`, which authenticates only the cookie. With no cookie the same read becomes anonymous and returns 404, while a different account’s cookie changes which principal supplies the projection.  
    **Smallest fix:** Pass the already authenticated identity into `object_page`. **Lane:** transport.

14. **P2 — Browser form decoding removes valid empty fields before the host sees them.**  
    Evidence: [http.py:389](/Users/ember/dev/delvetalk2/transport/http.py:389), [http.py:719](/Users/ember/dev/delvetalk2/transport/http.py:719), [Workshop.obend:144](/Users/ember/dev/delvetalk2/world/objects/Workshop.obend:144), [TurnLoop.lean:992](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:992).  
    Submitting Workshop’s propose form with a deliberately blank `migration` causes `parse_qs` to discard that field. Python then sends an incomplete argument record, producing `typeMismatch` even though the method accepts an empty migration string.  
    **Smallest fix:** Decode form bodies with `keep_blank_values=True`. **Lane:** transport.

15. **P2 — Anyone can invalidate another account’s pending proof by requesting a newer challenge.**  
    Evidence: [identity.py:58](/Users/ember/dev/delvetalk2/transport/identity.py:58), [identity.py:86](/Users/ember/dev/delvetalk2/transport/identity.py:86), [identity.py:108](/Users/ember/dev/delvetalk2/transport/identity.py:108).  
    After a resident posts challenge A, an unauthenticated caller can request challenge B for that resident’s handle. Verification always selects the newest challenge, so the valid proof of A now returns `proof_text_mismatch` instead of authenticating A’s credential.  
    **Smallest fix:** Bind verification to the requester’s challenge credential rather than the latest challenge for the handle. **Lane:** transport.