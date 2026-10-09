# Town cards: a portal inside posts

A participant needs the card post and the ability to reply. Websites are an
optional parallel interface. A card contains its visible state, typed action
fields and literal example commands:

```text
[[delvetalk-card garden-1]]
...the captured garden and available actions...
delvetalk garden-1 a1 {"seed":"fern"}
[[/delvetalk-card garden-1]]
```

Reply **to that published post** with one complete command, editing the example
values deliberately. The accepted grammar is exactly
`delvetalk CARD ACTION {JSON fields}`, apart from surrounding whitespace. No
extra prose, signoff, second command or natural-language inference is accepted.
Field names/types/bounds come from the existing [affordance contract](AFFORDANCES.md).
The command names a retained observation; it does not refresh it. Current law and
exact-root checks remain Lean's decision. Someone may act first; an old card can
be refused. Use the next card after a refusal. If no result appears, ask the
operator to check or link your **original reply**. Do not repost the command or
edit it into a new request: a new record is a new attempt.

## Local custody and publication

`CardBook.create(path, issuer_did=..., world_id=..., runtime=..., display_names={})`
creates explicit local custody. `CardBook(path)` reopens it. The metadata binds
issuer DID, world namespace, runtime and optional DID display labels. Labels do
not change identities or grants. A small SQLite database retains immutable cards
and publication bindings; transactions allocate stable `card-N` names. Explicit
names such as `garden-1` are accepted and cannot be reassigned to another view.
Nothing expires or is silently evicted (10,000-card bound).

`capture(view, alias=None)` retains the complete exact view/root, action catalogue,
world reference, runtime, rendered body and text digest. It creates a **local
draft** only. Runtime hashes are not printed in the card. Card bodies are bounded
to 12,000 UTF-8 bytes; use a smaller explicit view/projection if it does not fit.
Artist prose is prefixed as data, separate from generated control lines.

`bind(alias, {uri,cid}, fetch_record)` binds an already published card. The caller's
GET-only callback must authenticate the configured issuer repository and verify
that exact current URI/CID, returning the post record. This helper never publishes
or logs in. The post may contain a welcome message and several differently named
cards, but each bound block must appear exactly once, byte for byte, with balanced,
non-nested delimiters. A card cannot be rebound to another publication.

## Receiving and responding

`resolve(record, author, source, fetch_record, issuers)` returns `(wire, evidence)`.
The verified reply author/source are supplied by the receiving clerk, which must
explicitly configure this book and issuer allowlist. The reply's actual parent URI
**and CID** must equal the card publication. The publication is fetched again;
edited bodies, copied posts, unknown/unbound names and malformed/unknown fields
refuse. The helper calls `affordances.request` on the retained view and returns its
exact wire without principal or intent. The clerk derives those from the verified
reply and keeps its normal enrollment, current-law and runtime checks.

The evidence includes the complete captured card, original published record,
source and parsed fields. The clerk retains it before admission; pending/finished
recovery uses that journal, not a reconstructed card or an available website.
AppView display text alone is insufficient evidence. GET verification here uses
the configured custodian trust profile; hashes do not establish authorship.

`prepare_outcome(receipt, current_views)` prepares a receipt explanation plus new
cards/next actions from explicitly supplied snapshots. Committed allocations use
actual receipt creation roots. Unknown outcomes are distinguished from refusal.
The helper itself does not fetch state, admit requests or publish. The operator
loop below retains each prepared response under the original request identity
before returning it. Its new cards become usable only after verified binding.

## Programmable inline panels

A protocol can declare `viewPanels:[{id,label}, ...]` (at most eight; unique IDs;
nonempty UTF-8 IDs/labels at most 128 bytes). Capture evaluates each using the
existing installed pure view program against the **same captured root** and
retains every panel result. No state-specific Python rendering rule is added.
Main-view actions alone define the action catalogue; panels supply presentation.
The garden uses these panels for the image, contributions, authors and colour.
Explicit display labels can replace DIDs in prose while stored evidence retains
original identities. No remote code or model interpretation is executed.

[Implementation](../scripts/town_cards.py) · [actual Lean and custody tests](../conformance/test_town_cards.py)

## Operator loop

Use the clerk's explicitly configured cardbook and enrolled world. These commands
prepare local text or perform verified GETs; none publishes, enables a timer, or
starts background receiving.

```sh
# Retain an opening card and print the exact block for the welcome post.
python3 scripts/town.py --clerk-state /private/clerk --text capture garden --alias garden-opening
# After the authorized person publishes that block, bind its actual identity.
python3 scripts/town.py --clerk-state /private/clerk bind garden-opening 'at://ISSUER/town.delve.feed.post/KEY' --cid CID
# Check a participant's actual reply and retain the resulting response draft.
python3 scripts/town.py --clerk-state /private/clerk --text receive 'at://AUTHOR/town.delve.feed.post/KEY' --cid CID
```

`Town(clerk_state, state=None, request=None)` supplies the same `capture`, `bind`
and `receive` API. Operator custody defaults to `CLERK/town`; each book binds to
one operator custody directory. Preserve it across restarts. `receive` first
retains the exact source URI/CID, then delegates to `Clerk.receive`. It retains the
confirmed receipt, one snapshot of relevant current views, and reserved
`reply-N-M` card names before rendering. The full response body and digest are
durable before return. Repeating the operator command with the **same URI/CID**
returns that same body and card names, without another admission, network call,
or refresh. A changed CID on a retained URI refuses. A lost receipt is reported
as uncertain and recovered using the original identity.

Finish pending operator responses before replacing the clerk/cardbook runtime.
The clerk upgrade guard tracks its own pending admissions, while town rendering
has separate custody. A pending town response refuses profile replacement; a
completed response remains retrievable without current pins, book or network.

Current views may reflect turns after the acknowledged receipt; their roots are
explicitly captured and retained. Absent objects or unavailable presentations get
a no-card notice, preserving the confirmed receipt. Actual committed allocated
children get their own cards; existing clerk registration makes them receivable.
New response cards remain unbound drafts until their actual published post is
verified. An original response can never silently turn into a newly rendered one.

Discovery is separate. The existing watch follows its configured label/anchor;
ordinary replies outside that coverage are **not automatically found**. Supply
actual reply URI/CID manually here. The worker's record-receipt outbox is not a
substitute for this human-readable response loop.

[Operator implementation](../scripts/town.py) · [operator recovery tests](../conformance/test_town_operator.py)
