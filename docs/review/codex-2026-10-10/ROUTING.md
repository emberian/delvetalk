# Codex review of a3e1fb2 (gpt-6.1-sol, six facets, read-only): routing

Read each facet file here; findings are ranked by the reviewer. The root's
decisions before dispatch (made 2026-10-10 evening, not yet dispatched):

- One structural fix closes objects 1-8 at once: a generic state write from
  outside the object (`world-propose`, another object's `write`) gets its own
  request kind, `proposed`, so every existing law that admits `kind == 0`
  writes keeps admitting only the object's own method writes; a law that
  wants proposals says `request.kind == proposed`. Host lane, with a kernel
  grammar line for the new kind name. Objects then add `unchanged(owner)` as
  belt, and fix 9-15 (cooldown eviction, subsMax 32, seed length in
  fromFields, the planting post into settled, durable anthology numbers, one
  budget per composite card, the clipped footer) and Deal's requester-only
  signatures.
- Host, in order: 1 settling exposes others' receipts; 2 default publishPage
  leaks private state; 3 lawReads bypasses read policy; 7 a rehashed snapshot
  replaces a law; 6 `ended` to a non-exposing supervisor; 5 reprogram drops
  fixed protection (also docs 1); then the `proposed` kind; then 4, 8, 9, 10,
  11, 12 (direct turns honour form bounds; also agent 3), 13, 14, 15; docs 2
  (extension pins by sourcePin); agent 11 (per-reader action filter), 12
  (migration diagnostic in the refusal), 14 (object names and spell names
  share one rule); transport 9, 10, 12 (quota and model-retry decisions into
  the host; repository cursors by (height, item)).
- Kernel: 1 natural arithmetic allocation bomb (preflight by bit length); 3
  turn-resume trusting a supplied digest (require the retained suspension or
  the journaled digest); 4 textHasAny quadratic; 7 negative integers past
  the CBOR range collide; 8 byte budget on legacy sizes; 9 labelEqual
  tariff; 10 take/drop preflight; 2, 5, 6 fixed fields, declares and remove
  sugar through layers and aliases.
- Transport: 1 is already fixed (the deploy lane changed the healthcheck); 2
  posting idempotence (deterministic record key; retry registration apart
  from sending); 3 pending interpretations resubmitted after a restore; 4
  bound workers and absolute deadlines; 5 the hand on a loopback listener
  only; 6 address limits on anonymous pages; 7 and agent 8: Python stops
  classifying spells, the host's parser decides (an op `spell-classify`);
  8, 11, 13, 14, 15; docs 4 / agent 6 receipts and slugs on successful
  drafts; agent 13, 15.
- Docs: 3, 7, 8, 9, 10, 11, 12, 13 (reconcile the backlog and the brief);
  agent 9, 10.
- Objects, agent facet: 1 the planting acknowledgement prints the bell's rain
  spell; 2 a first prose request is not discarded for the menu; 4, 5, 7.

Then: the token lane's report (the glyph lexicon follows it), a redeploy
from the head with a clean re-genesis (nothing is posted yet), run 12, and
the ring once ember creates the stream, the six rcs and the key.

## As landed (read from `git log` on foundation, 2026-10-10)

Every finding of the six facets and the commit that closed it, at foundation
b0f3618: 87 closed, one open (docs 6). `D` is the docs lane's commit "Docs: the
review's docs findings" (lane/docs3, `1562b31`), the one that added this table.

| Facet | # | Finding (short) | Closed by |
| --- | --- | --- | --- |
| agent | 1 | planting gave no path to rain on the new bell | `1b218e0` |
| agent | 2 | a stranger's first prose request discarded for the menu | `f72cb1f` |
| agent | 3 | direct form calls bypass spell bounds | `36574c5` |
| agent | 4 | a stranger's anthology admit admitted, unexplained | `f6dad06` |
| agent | 5 | Workshop holds a missing-migration error for adoption | `46ab4fc` |
| agent | 6 | successful town replies lack the receipt's name | `fdcf8df` |
| agent | 7 | the anthology's ninth submission vanishes from its acknowledgement | `5028cbe` |
| agent | 8 | standalone bell spells and `?` filtered before the host | `6c081ea` |
| agent | 9 | "quote your post" recovery has no implementation | `D`: the welcome teaches the receipt by the post's address |
| agent | 10 | the lending tutorial's grant is unusable by its recipient | `D`: AGENTS-API step 15 lends within one heap, with the `callVia` |
| agent | 11 | usage and controls advertise owner-only actions | `7b66697` |
| agent | 12 | migration failures lose the diagnostic | `ba5d246` |
| agent | 13 | another's refused receipt by slug loses its links | `cfd63bf` |
| agent | 14 | creation accepts names no spell can parse | `19f88b1`, `7c8ef3a` |
| agent | 15 | discovery spends requests on method names | `609e379` |
| docs | 1 | a reprogram can change a fixed field | `aad3088` |
| docs | 2 | extension pins can name different closures | `3e1845b` |
| docs | 3 | the welcome promises confirmation planting skips | `D` |
| docs | 4 | successful replies omit the receipt line | `fdcf8df` |
| docs | 5 | object names the spell surface cannot address | `19f88b1`, `7c8ef3a` |
| docs | 6 | an intent equal to an older slug finds the wrong receipt | **open** (transport; FOUNDATION §12) |
| docs | 7 | the object capsule's `refused` arm commits staged writes | `D` |
| docs | 8 | the declared-surface invariant forbids receiver deliveries | `D` |
| docs | 9 | the opening commit rule omits commuting edits | `D` |
| docs | 10 | the laws capsule's class set lacks `quota`, `noMethod` | `D` |
| docs | 11 | views promised as spells | `D` |
| docs | 12 | a torn tail promised cut | `D`; HOST-HANDOFF in the lane's last commit |
| docs | 13 | the brief and backlog report fixed defects | `D`; the handoffs in the lane's last commit |
| host | 1 | settling exposes others' receipts | `66eae2d` |
| host | 2 | the default `publishPage` exports unreadable objects | `04eb217` |
| host | 3 | `lawReads` bypasses read policy | `d0c729f` |
| host | 4 | law-read expansion admits an unreplayable entry | `a8f2895` |
| host | 5 | a reprogram removes fixed protection | `aad3088` |
| host | 6 | any creator invokes another's `ended` | `15202c3` |
| host | 7 | a rehashed snapshot replaces a law | `ca2ef38` |
| host | 8 | `insertOnly` admits retractions disguised as retention | `a033656` |
| host | 9 | creating children spends no causal storage | `99eb54d` |
| host | 10 | retention evictions absent from the conflict index | `a033656` |
| host | 11 | `inspect` and `subscribe` omit their roots | `3b65fb6` |
| host | 12 | direct turns bypass form bounds | `36574c5` |
| host | 13 | a spell retry becomes `duplicateIdentity` after a reprogram | `6a19d37` |
| host | 14 | an exhausted `lawReads()` binds as `lawRefused` | `1313fae` |
| host | 15 | a second suspension loses the spell origin | `10e0c55` |
| kernel | 1 | natural arithmetic allocates before refusing | `3c5741a` |
| kernel | 2 | fixed fields lost through layers and aliases | `713ff83` |
| kernel | 3 | `turn-resume` accepts an invented continuation | `47c8c25`, `52ad1b2` |
| kernel | 4 | `textHasAny` quadratic | `f935b81` |
| kernel | 5 | layers omit inherited declarations | `8028b32` |
| kernel | 6 | remove sugar changes meaning through aliases | `7ff1824` |
| kernel | 7 | oversized negative integers collide | `585b673` |
| kernel | 8 | the byte budget measures a legacy encoding | `65949d0` |
| kernel | 9 | text equality bypasses the text tariff | `95b1484` |
| kernel | 10 | failed take/drop preflights refund their work | `4dc9dc7` |
| objects | 1 to 8 | strangers write the authority that admits them (owner by migration, Deal and Tide reprogrammed, held proposals, Avatar, Table, Seat, Thing custody, Deal countersignatures, Scene passages) | `dcb8169`, then `a95bb2b` and `4f8af5c` (`proposed`) and `7017d75` |
| objects | 9 | departures erase an active cooldown | `b3fd61c` |
| objects | 10 | 33 due Tide subscribers fail the tick | `366fe1c` |
| objects | 11 | a completed seed past 80 characters | `95b6f30` |
| objects | 12 | completed plantings lose the post their bell awaits | `e432daf` |
| objects | 13 | retention moves what a line number names | `7d77d26` |
| objects | 14 | composite cards past the budget | `5db94d7` |
| objects | 15 | `Card.clipped` past its own allowance | `71bc806` |
| transport | 1 | the healthcheck fails a healthy front | `803e9fb` |
| transport | 2 | a post retried duplicates, a failed registration orphans | `f08394f` |
| transport | 3 | a restored backup's pending interpretations never settle | `610f9cd` |
| transport | 4 | slow clients hold unbounded workers | `d84f617` |
| transport | 5 | the hand behind public Caddy | `0392414` |
| transport | 6 | anonymous pages bypass limits | `9d4b81e` |
| transport | 7 | Python's spell classifier drops spells | `6c081ea` |
| transport | 8 | a hand-posted publication loses its object | `6657e6c` |
| transport | 9 | posting quota decided by Python's directory and clock | `8a56520` (host), `d99d691` (transport) |
| transport | 10 | Python decides model-failure outcomes | `8a56520` (host), `e1f3359` (transport) |
| transport | 11 | refusals suppressed by the input's wording | `b984257` |
| transport | 12 | height-only repository cursors skip records | `0e30c63` (host), `e8cf553` (transport) |
| transport | 13 | HTML and text reads drop the bearer | `2cd2819` |
| transport | 14 | browser forms drop empty fields | `c872481` |
| transport | 15 | a newer challenge invalidates another's | `5fcfcc1` |
