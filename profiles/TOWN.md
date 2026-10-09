# Town cards: a portal inside posts

**Reply in ordinary language.** An [operator retains an explicit interpretation](MANUAL-INTAKE.md); Lean checks the resulting request. Optional direct-execution spells use the offered card:

```text
delvetalk garden-1 plant
seed: fern
colour: silver
```

Reply **to its published post**. `METHOD` in `delvetalk CARD METHOD` names a unique captured command; `aN` remains a fallback. Fields use `field: literal`: remove one separator space, preserve other spaces/Unicode. Naturals require canonical ASCII decimal; Booleans require `true`/`false`. Multiline strings use `field: <<END`, literal lines, then standalone `END`; choose an absent delimiter. Framing linefeeds disappear; a blank final content line preserves a final linefeed. Unknown/duplicate fields refuse. Legacy `delvetalk CARD aN {JSON fields}` still works. Surrounding prose needs interpretation. [Field bounds](AFFORDANCES.md) apply.

New cards use authored field examples when provided; examples remain editable
guidance. Empty panels and internal version headers stay out of projected cards;
raw inspection retains state details. Existing captures keep their original bytes.

Cards retain exact readings; they never refresh during admission. After refusal, use a fresh card. After uncertainty, link the **original reply** for recovery. Do not repost or edit: a new record is a new attempt.

## Operator reference

These commands prepare local text or perform verified GETs; they neither publish nor schedule receiving:

```sh
python3 scripts/town.py --clerk-state /private/clerk --text capture garden --alias opening
python3 scripts/town.py --clerk-state /private/clerk bind opening at://ISSUER/town.delve.feed.post/KEY --cid CID
python3 scripts/town.py --clerk-state /private/clerk --text receive at://AUTHOR/town.delve.feed.post/KEY --cid CID
```

[CardBook](../scripts/town_cards.py) binds issuer, world and runtime. Immutable aliases retain exact view/root, catalogue, rendered bytes and digest. Capture is a draft; binding verifies an already-published issuer post. Each block must occur exactly once, byte-for-byte, with balanced, nonnested delimiters. No rebinding. Replies must name its actual parent URI **and CID**; receiving refetches publication. Copies/edits refuse. Clerk verification supplies author/intent and retains source/card/publication evidence before Lean admission. Labels grant nothing; AppView text alone is insufficient.

Preserve default `CLERK/town` custody. [Town](../scripts/town.py) retains source identity, receipt, snapshots, reserved response-card names and exact response bytes. Completed same-URI/CID retries recover them without admission, refresh or network; changed CID refuses. Unknown outcomes remain uncertain. Current-view snapshots may postdate the acknowledged receipt; unavailable views preserve it with a no-card notice. Allocated children use actual receipt roots. Response cards require publication binding before use.

Finish pending Town responses before runtime replacement: the clerk upgrade guard covers its own admissions, **not separate Town rendering**. Pending responses refuse changed profiles; completed responses survive missing pins/book/network. Discovery remains separate: manually supply replies outside watch coverage.

Installed `viewPanels` evaluate the same captured root; only main-view actions define the catalogue. Source views bind the configured compiled runtime's complete dependency/binary pins. Limits: eight panels, 12,000-byte cards, 10,000 retained cards; no silent eviction. [Projection](../scene/projection.py) defines checks.

[Forge follow-ups](../scripts/town_authoring.py) retain source, examples/results and adoption cards separately from submission replies; they neither compile nor publish. Adoption atomically releases the desk and replaces the target under both current laws/exact roots. A release alone is no installation.

[Card tests](../conformance/test_town_cards.py) · [recovery tests](../conformance/test_town_operator.py) · [authoring tests](../conformance/test_town_authoring.py) · [receiving journey](../conformance/test_town_forge_journey.py)
