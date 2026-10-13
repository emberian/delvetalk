Reviewed `93481c5d..392c1f98`. Read-only; verified with in-memory handler, renderer and SQLite probes. No live requests or filesystem edits.

1. **P1 — Login CSRF can replace the browser’s principal.** [transport/http.py:1122](transport/http.py:1122), [transport/http.py:1177](transport/http.py:1177).  
   An attacker submits a top-level form from another origin to `/enter`, containing the attacker’s valid credential. The handler installs it without checking Origin or CSRF state. Subsequent private actions belong to the attacker’s account. `/leave` likewise accepts a foreign-origin POST without authentication; `/feed` accepts cookie-authenticated writes from an attacker-controlled same-site origin. Strict cookies can be set during cross-site top-level navigation and do not distinguish sibling origins. [Cookie specification](https://httpwg.org/http-extensions/draft-ietf-httpbis-rfc6265bis.html#section-5.7)  
   **Fix:** Apply one browser-write gate to login, logout, acceptance, play and feed: exact configured-origin validation plus CSRF protection. Preserve explicit bearer-authenticated API access.

2. **P1 — One thread can permanently break the feed’s first page.** [transport/http.py:1190](transport/http.py:1190), [transport/pages.py:437](transport/pages.py:437), [transport/feed.py:173](transport/feed.py:173).  
   Pagination limits threads, but fetches and renders every reply. One root plus 25 replies, each containing 65,536 `&` characters, are valid inputs within the hourly quota. Escaping produces over 8.52 MB of HTML, exceeding the 8 MiB response limit: `/feed` returns `replyTooLarge`. Fetching and rendering continue to grow with the thread before that limit is checked.  
   **Fix:** Bound posts and bytes per page, paginate replies, and select thread pages in SQL without materializing the entire thread index.

3. **P2 — Cookie-dependent private pages are cacheable without separating readers.** [transport/http.py:1361](transport/http.py:1361), [transport/http.py:551](transport/http.py:551).  
   An authenticated `GET /o/robin/book` can include deeds involving owner-only objects. Behind a shared cache using heuristic freshness, its 200 response can be reused for an anonymous request: neither `private`/`no-store` nor `Vary: Cookie` separates the responses. Cookie authentication lacks Authorization’s cache restriction. [HTTP caching specification](https://www.rfc-editor.org/rfc/rfc9111.html#section-3)  
   JSON `/enter` credential replies ([1098](transport/http.py:1098)) and door errors preserving unused invitation codes ([1136](transport/http.py:1136)) also omit the welcome page’s `no-store`.  
   **Fix:** Centralize `Cache-Control: private, no-store` for reader-dependent pages and every response carrying credentials or invitation codes, including errors and redirects.

4. **P2 — Retrying a feed submission creates another durable act.** [transport/http.py:1183](transport/http.py:1183), [transport/static/pages.html:202](transport/static/pages.html:202).  
   A POST commits a rain to the feed, but its 303 response is lost. Retrying the same body creates another post URI; the bridge consequently presents another identity to the host and rains twice. The form carries no submission identity. The store probe confirmed identical submissions create distinct records.  
   **Fix:** Give each submission an idempotency key, persist it with the author and payload digest, and return the existing post on an identical retry.

5. **P2 — Feed form POSTs bypass request throttling; hourly admission races.** [transport/http.py:1177](transport/http.py:1177), [transport/http.py:1148](transport/http.py:1148).  
   The posting branch returns before calling `limited`, allowing more than 32 requests per credential per minute. With 59 recent posts, concurrent requests can all observe 59 before their inserts and exceed the 60-post hourly ceiling.  
   **Fix:** Charge the credential request limit before processing POSTs, and perform hourly quota checking and insertion in one store transaction.

6. **P2 — `/leave` can falsely announce that the browser is signed out.** [transport/http.py:1107](transport/http.py:1107), [transport/pages.py:414](transport/pages.py:414).  
   A signed-in resident follows an external link to `/leave`. Strict suppresses the cookie on that navigation, so the page says “Signed out” and “This browser no longer speaks for you.” Nothing cleared the cookie; subsequent same-site navigation still authenticates. [Strict navigation behavior](https://httpwg.org/http-extensions/draft-ietf-httpbis-rfc6265bis.html#section-5.6.7.1)  
   **Fix:** Show the sign-out confirmation even when GET receives no cookie. Show completion only after the POST clears it.

7. **P2 — Waiting for an answer discards the next draft.** [transport/pages.py:442](transport/pages.py:442), [transport/http.py:1194](transport/http.py:1194).  
   After posting, the resident starts typing in the still-active composer while the town answers. The three-second document refresh replaces the textarea with an empty one, losing the draft; this can repeat eight times.  
   **Fix:** Update answers without replacing the composer. For the scriptless page, avoid automatic refresh while presenting an editable form.

8. **P2 — Suggestions truncate valid multiline source spells.** [transport/pages.py:140](transport/pages.py:140).  
   A card offers an indented `delvetalk workshop draft` with `source: <<END`, two definitions separated by a blank line, and its closing `END`. Extraction stops at the blank line. Selecting the suggestion fills the composer with an unterminated source block instead of the offered spell.  
   **Fix:** Obtain complete spell spans from the host’s grammar, preserving heredocs, fences and blank lines.

9. **P2 — A keyless front turns the guest door’s expected refusal into HTTP 500.** [transport/http.py:1134](transport/http.py:1134).  
   With an open invitation and no town repository key, account provisioning raises `Refusal(503, RepoNotServed)`. The HTML door catches only `IdentityError`, so dispatch emits `500 internal`. The JSON acceptance path catches this same refusal correctly.  
   **Fix:** Share acceptance and refusal handling; render the provisioning failure as a 503 with its actionable explanation.

Duplications and which mechanism to keep:

| Job | Competing mechanisms | Keep |
|---|---|---|
| Accept invitations | [http.py:1083](transport/http.py:1083) and [http.py:1133](transport/http.py:1133) independently accept, announce arrival and issue cookies | One acceptance operation; HTML/JSON renderers around it |
| Submit feed posts | [http.py:1155](transport/http.py:1155) and [http.py:1172](transport/http.py:1172) have separate authentication, throttling and input handling | One submission driver with common validation, quotas and idempotency |
| Submit host turns | [http.py:406](transport/http.py:406) and [http.py:1262](transport/http.py:1262) independently call the host and draft outcomes | `Front.turn`, extended for browser needs; keep tracing/rendering outside |
| Interpret spell structure | [pages.py:131](transport/pages.py:131) reconstructs syntax already owned by the host parser and templates | Host grammar and structured spell spans |
| Manage the session cookie | [http.py:669](transport/http.py:669), [788](transport/http.py:788), [1111](transport/http.py:1111) construct separate cookie policies | One cookie helper supporting issuance and deletion |