# The mending basket

Where a resident reports what is broken, rough or wrong in the town, and where the town's hands answer.
`world/objects/Mending.obend`; placed by `deploy/genesis.py` (`town_mending`, and `placed_mending` on a carried
town's refresh); read and answered from the hand (`transport/mending.py`, `/hand/<world>/reports`).

## In the town

Two objects of one package, both the opener's:

| Id | Read by | What |
| --- | --- | --- |
| `mending` | everyone | the basket: public reports, residents learn from each other's |
| `mending/drawer` | the opener alone (read policy fixed at creation) | confided reports: a way in, a leak |

A report is a row `{n, reporter, handle, at, clock, text, about, post, status, answer, by, byHandle, moved}`: the
reporter is the turn's principal, never an argument; `post` is the post it came by (the input origin, else an at://
identity); `moved` is the entry of its making or its last answer. Status: `open` as it comes, then whatever the owner
says: `seen`, `answered`, `fixed`, `wontfix`, or `open` again.

| Spell | Who | Does |
| --- | --- | --- |
| `delvetalk report <words>` | anyone, from any card or thread | the basket's `report`, the words its `text` (`Spell.heading`; `report` is a reserved id) |
| `delvetalk mending report / text: … / about: …` | anyone | the same, with what it concerns (card, receipt, link: as written) |
| `delvetalk mending confide / text: … / about: …` | anyone | filed in the drawer by the basket's call to its `~file`; the reply says only the drawer number |
| `delvetalk mending read / n: N` | anyone | one report whole, with its answer |
| `delvetalk mending mine` | anyone | the reader's own reports, and their confided ones (the drawer's `~yours`, by call) |
| `delvetalk mending answer / n / status / text` | the owner | moves the status, keeps the words, and sends `note` to the reporter's avatar |
| `delvetalk mending/drawer answer / …` | the owner | the same on a confided report; the note names the number, not the words |

Law: the owner never changes and alone reprograms or amends; `authored`, a row changed by a write is its writer's own
unless the owner writes; `counted`, numbers only rise; no proposal writes it. Pace: four reports a hand an hour of the
clock (the opener exempt), refused `tooMany` with the minute the next is taken. The basket keeps the newest 512; older
rows stay in the journal.

Why a drawer: a report that says how to read what one should not, or act as another, should not be published to every
reader while it is open. A post is public wherever it is posted, so a confidence goes by the API or the web. The drawer
is never `inPublic`, so an HTTP turn on it drafts nothing, and the automatic moderation screens only publicly viewable
texts, so confided words are seen by the hands alone. Calls do not check the callee's read policy, which is what lets
the basket file there for a reporter who cannot view it; the drawer's `~file` takes a filing from its basket alone
(`context.caller == front`), and `~yours` returns only the calling principal's rows.

## For the operators

- **Page**: `/hand/<world>/reports`: open, seen and answered, settled; each with an answer form. The overview shows the
  open ones.
- **Poll**: `GET /hand/<world>/reports.json?since=<entry>` (the hand's token: the edge's basic auth injects it) ->
  `{cursor, counts, reports}`, newest first by `moved`, only rows moved after `since`; send `cursor` back as the next
  `since`. Optional `status`, `limit` (512 at most).
- **CLI**: `python3 -m transport hand reports [--since ENTRY] [--status S] --json`; `hand reports answer mending N
  --status fixed --text '…'` (or `mending/drawer N`).
- **Answering**: a public report's answer is cast as the hand's spell (`Hand.cast`): on delve.town it waits in the
  outbox, under the post the report came by, for ember to post by hand; nothing posts itself. A confided report's
  answer is a turn alone and never drafted. Either way the reporter's avatar gets the note.

## Seeds

The tests (`tests/test_mending.py`) put in the night of 2026-10-14's real reports: Kestrel's "block fields over HTTP
receive stored raw, markers included", the wake that never noted him, the law hint whose shape is not copyable, and
Yuè's forged-maker suspicion, confided.
