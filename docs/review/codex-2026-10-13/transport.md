Reviewed `93481c5d..392c1f98`, covering the last day’s merges. Ranked by impact. No files changed.

1. **P1 — Public read replies disclose caller-only content.** [bridge.py:727](transport/bridge.py:727), [hand.py:445](transport/hand.py:445).  
   **Scenario:** Alice writes in a diary readable only by Alice, then posts `delvetalk me book`. The host renders her book under Alice’s authority; the bridge copies the complete read into a public draft. On the local feed, it is published automatically. Likewise, `hand morning` drafts wants read under the opener’s authority, including opener-private things.  
   **Fix:** Have the host produce a public projection for posted reads; render morning material as `PUBLIC`.

2. **P1 — Thread splitting can turn quotations into executable spells.** [post.py:242](transport/post.py:242).  
   **Scenario:** A long draft contains an indented `delvetalk bell/1 tend` immediately after a chunk boundary. `lstrip('\n ')` removes its indentation, so the next posted part contains a spell at the margin. Splitting inside a tagged fence also loses the fence context. The observer can execute an example that was originally quoted.  
   **Fix:** Preserve indentation and quoting context across parts. Split outside literal blocks, or explicitly continue their quoting in every part.

3. **P1 — A participant’s PDS can poison another participant’s request URI.** [requests.py:194](transport/requests.py:194), [requests.py:222](transport/requests.py:222).  
   **Scenario:** Attacker’s PDS lists `at://<victim>/online.fg-goose.gsb.request/R`, while supplying a valid signed proof for Attacker’s own request at key `R`. Verification checks Attacker’s DID and MST path, but the observation retains the supplied Victim URI. Its answer falsely names Victim’s request; `observer.seen(uri)` then suppresses Victim’s real request.  
   **Fix:** Validate or construct the URI from the verified DID, collection and rkey before any consumption/refusal lookup.

4. **P1 — Previously valid guest names can prevent the HTTP front from starting.** [identity.py:106](transport/identity.py:106).  
   **Scenario:** The existing identity database contains an accepted guest named `robin-`, permitted by the previous guest-name regex. After upgrading, startup provisions verified guests through [hosted.py:48](transport/hosted.py:48). The new mapping rejects that principal with an uncaught `ValueError`, aborting front initialization.  
   **Fix:** Preserve legacy principals and credentials. Give legacy names a reversible hostname encoding, or skip unsupported hosted provisioning without stopping the front.

5. **P1 — The local feed stops working when delve.town is unavailable.** [bridge.py:619](transport/bridge.py:619), [bridge.py:783](transport/bridge.py:783).  
   **Scenario:** A guest posts locally while delve.town search/feed reads fail. Every normal bridge invocation still constructs the external observer and calls its poll before ticking, processing local observations or posting local answers. The exception escapes the daemon step, stopping the bridge.  
   **Fix:** Support feed-only operation and isolate external polling failures; continue processing local work while reporting the failed source.

6. **P2 — Threaded posts permanently lose failed host registrations.** [post.py:284](transport/post.py:284), [feed.py:229](transport/feed.py:229).  
   **Scenario:** A part is posted successfully, but `world-posted` returns an error—or the process crashes after persisting `sentParts` and before registration. The automatic thread path discards registration results and eventually writes aggregate `recorded`. The feed path similarly overwrites per-part errors with aggregate success. `record_sent` never repairs those parts, so replies under them cannot reliably reach their card.  
   **Fix:** Persist each part’s intent and registration result. Retry registration for every sent part independently of sending and thread completion.

7. **P2 — Multi-spell requests receive a terminal answer while still suspended.** [bridge.py:353](transport/bridge.py:353).  
   **Scenario:** One request’s spell text produces several turns, including a suspended interpretation. The `spells` branch immediately writes its answer and creates no awaiting record. When interpretation settles, nothing updates that answer; subsequent bridge runs skip the request because the answer exists.  
   **Fix:** Track suspended child identities and update the parent answer when they settle, using the same lifecycle as suspended single-turn requests.

8. **P2 — Editing a partially posted draft mixes two different texts.** [hand.py:635](transport/hand.py:635), [post.py:262](transport/post.py:262).  
   **Scenario:** Part one has left; quota postpones part two. `hand edit` replaces `d['text']`. On resume, the guard compares the replacement body with that already-replaced field and passes. Posting resumes at the old part count using newly computed chunks, producing an old prefix followed by an unrelated new suffix.  
   **Fix:** Freeze the text and chunk boundaries once any part leaves. Reject edits or create a separate replacement draft.

9. **P2 — Withdrawing a thread deletes only its final part.** [hand.py:704](transport/hand.py:704).  
   **Scenario:** A completed three-part draft stores its last part in `sent`. `hand unpost` deletes and unregisters only that URI, then marks the whole draft withdrawn. Parts one and two remain public and registered. A partially posted thread cannot be withdrawn through this method at all.  
   **Fix:** Withdraw every distinct URI in `sentParts`/`byHand`, retain per-part progress, and allow withdrawal before thread completion.

10. **P2 — Feed pagination does not bound work or response size.** [feed.py:166](transport/feed.py:166), [feed.py:173](transport/feed.py:173).  
    **Scenario:** A resident adds permitted 64 KiB replies to one thread over several days. One page fetch loads every reply in that thread; `limit=1` still returns arbitrarily many posts. A week at 60 replies/hour can materialize roughly 630 MiB of text before rendering. Every page also enumerates all thread roots.  
    **Fix:** Use database keyset pagination for roots and replies, with a total post/byte budget per response.

11. **P2 — Automatic matching can attach a historical invitation to a new playtest.** [hand.py:685](transport/hand.py:685), [byhand.py:159](transport/byhand.py:159).  
    **Scenario:** A fresh world drafts the same top-level invitation used yesterday. Yesterday’s owner post remains among the newest 50 records and is absent from this world’s linkage ledger. Opening the outbox automatically links it by text and parent, marking today’s invitation posted although no new invitation left.  
    **Fix:** Require automatic candidates to postdate draft creation and be unambiguous. Keep explicit manual linking available for older posts.

12. **P2 — A signed request with an invalid timestamp persistently breaks measurements.** [requests.py:84](transport/requests.py:84), [observe.py:134](transport/observe.py:134).  
    **Scenario:** An external repository supplies a correctly signed request with `createdAt: "not-a-date"` and a valid call. `before_start` converts the parse failure into “not before start,” so the request is consumed and run. Later, `measure.measures` parses the stored timestamp without handling that failure, crashing the Measure page/status path on every read.  
    **Fix:** Validate the timestamp before inserting the observation; quarantine malformed requests and make measurement readers tolerate already-stored invalid observations.

13. **P2 — Manual posting disappears from playtest accounting.** [measure.py:56](transport/measure.py:56), [measure.py:74](transport/measure.py:74).  
    **Scenario:** The owner posts the T+0 invitation manually and registers its link, or automatic matching finds it. Those paths log `what: "posted"`; both measurement readers accept only `"post"`. T0 falls back to the first resident observation, and responses to manually posted prompts are counted as unprompted.  
    **Fix:** Emit and consume one confirmed-post event across automatic, manual and matched posting, carrying the actual post timestamp.

14. **P2 — Carrying a world erases its outstanding wants from measurements.** [measure.py:85](transport/measure.py:85).  
    **Scenario:** A bell has wanted rain since entry 7. Carry preserves it in the genesis’s `outcome.index.wanting`, but this fold starts empty and reads only subsequent `wanted` events. It reports no outstanding want; if a resident then closes it, the answer is also discarded because `since` is missing.  
    **Fix:** Initialize holding wants and clock from carried genesis state/index, then fold the new journal tail.

15. **P2 — Concurrent matching/linking can crash on the shared temporary filename.** [hand.py:860](transport/hand.py:860), [state.py:79](transport/state.py:79).  
    **Scenario:** Two outbox tabs automatically match the same waiting draft, or matching overlaps explicit link registration. Both read the same draft and write its same `.tmp` path without a draft lock. After one renames it, the other rename raises `FileNotFoundError`; overlapping updates can also overwrite linkage state.  
    **Fix:** Serialize each draft’s complete read–modify–write operation and use unique temporary files for atomic writes.

Duplications and which mechanism to keep:

| Mechanisms doing the same job | Keep |
|---|---|
| [post.thread](transport/post.py:256), [feed.post_drafts](transport/feed.py:204), [byhand.record](transport/byhand.py:87): part progression, reservation, confirmation and completion | One durable posting state machine in `post.py`; retain channel-specific sending and manual evidence verification as adapters. |
| [draft_public](transport/bridge.py:209), [spell_line](transport/bridge.py:106), [public_view](transport/bridge.py:307), preview/read branches: deciding what public output contains | One host-projected public answer model; render text and record responses from it. |
| [principals.txt skip logic](transport/bridge.py:439) and host `world-arrive` registry/idempotency | The host’s journaled registry. Make any local arrival cache disposable and bound to the host head. |
| [measure’s package-law string heuristic](transport/measure.py:136) and the host’s inherited/amended law provenance | Host provenance; expose it to measurement instead of inferring authorship from the shortest seed law. |
| [observe.AT_URI](transport/observe.py:13), [Identity._parse](transport/identity.py:275), [byhand.at_uri](transport/byhand.py:38), [Client.record](transport/delve.py:280) | One structured AT-URI parser at the client boundary; retain claim restrictions and web-link conversion as explicit policies. |

Validation used in-memory checks and mocked I/O for the implicated source functions. The full suite was not run; the available Python environment lacks `cryptography`.