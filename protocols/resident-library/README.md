# Resident behavior library

Two ordinary Objective Bend modules compose subscriptions and bounded mailboxes.
The independently authored [repair board](RepairBoard.obend) and
[reading circle](ReadingCircle.obend) reuse both; neither has a private delivery
engine or a generated copy of the behavior.

| Module | Reusable behavior |
| --- | --- |
| [Consent.obend](Consent.obend) | Ordered keyed consent/subscription collections, a global monotone consent epoch, cursor pagination, and a bounded emission collection encoder |
| [Mailbox.obend](Mailbox.obend) | A two-list FIFO with cached size, explicit acknowledgement, contextual forms/view, and an open-recursive receiving layer |

`Mailbox.Inbox` calls `self.accepts`, `self.capacity`, and `self.maxUnits`.
The repair layer uses `super` to derive room for two notices and four units; the circle
layer derives room for three notices and six units and accepts an additional `reading`
topic. Both accept `help` and `ready`. The inherited store method therefore
follows each final object's policy without being copied or replaced.
The description evaluates that same assembled behavior to obtain form limits:
four units for the repair board, six for the reading circle.

## Compose and use

Supply ordered exact modules `Abi`, `Preparation`, `Encounter`, `Emissions` (from `world/lib/prelude`),
`Consent`, `Mailbox`, then `RepairBoard` or
`ReadingCircle` to the existing `objective-bend-spell@3` module adapter. Imports
resolve those supplied bytes. The adapter derives state, methods, forms and
panels from source. No Python source generator is involved.

With the native hosts already built:

```sh
python3 conformance/test_resident_library.py
```

The receiving profile is `compiled`. A local world initializes native messaging
before creating objects. Each keeper has `selectPeer` and `configure`, each member has `announce`
and `acknowledge`, and a separately granted relay has the receive-only `receive`
method. Law management and reprogramming have their own grants. Names in the
local tests are caller assertions, not authenticated remote identities.

1. The recipient's keeper chooses `side="listen"`, the sender object, a
   collection key (`slot`, 1–65535), an enabled flag and a fresh generation.
   The source invitation then captures that peer and confirms consent with its
   observed program. The form never asks for a program hash. Generation must
   exceed the global epoch; an incoming source cannot occupy two enabled keys.
2. The sender's keeper similarly chooses `side="send"`, the recipient object,
   key and the recipient's generation, then confirms its captured observation.
   Peer drift refuses the captured request; a new observation can prepare it again.
3. A member calls `announce {topic,units,after,limit}`, starting with `after=0`
   and `limit=4`. Native admission retains addressed message evidence and
   validates target program identity. The result `{next,count,more}` identifies
   the admitted page; passing `after=next` requests the next page. Keys are sorted,
   so insertion order does not affect paging. Each invocation faces current state
   and current authority; the cursor is neither a snapshot nor a delivery grant.
4. A currently authorized relay explicitly delivers a retained event. The
   recipient's source checks native sender facts and its current consent,
   vocabulary, unit limit and mailbox capacity, with the outcomes below.
5. A member acknowledges the oldest notice before another delivery can fill
   that space. Answering a notice requires an explicit new announcement.

`configure` also takes `enabled`; disabling or renewing incoming consent must
advance the global epoch. An entry can keep its existing generation while other
entries change. Moving a withdrawn source to another key requires a fresh epoch,
so it cannot revive old events. Program values come from captured native observations; an event's source identity and program come from native
delivery facts, never a copied generation or payload assertion.

| Incoming event | Native outcome |
| --- | --- |
| Current matching consent, valid notice, available space | Commit `stored`; append a notice and consume the event |
| No matching consent; generation at or below the global epoch | Commit `declined-consent`; keep mailbox state and consume the event |
| Generation above the supported 65535 bound | Commit `declined-consent`; keep mailbox state and consume the event |
| No matching consent; generation ahead of the global epoch but within bounds | Refuse; retain the event for possible future explicit consent |
| Matching consent but unsupported topic or unit count | Commit `declined-notice`; keep mailbox state and consume the event |
| Matching consent and valid notice, but full mailbox | Refuse; retain the event until an acknowledgement makes room |

An obsolete consent can never become current again under the monotone epoch.
An invalid notice cannot become valid under its pinned recipient program.
Declining those events is an explicit source decision recorded in the retained
delivery receipt, not deletion of history. It releases native pending quota.
Current relay grants still govern every new delivery, including a decline.
After a source refusal, the local relay retains that exact attempt. Once consent
or capacity changes, explicitly enable its existing `retry EVENT` operation;
retrying the old request itself still recovers the old refusal.

## Boundaries

The default behavior permits 16 outgoing and 16 incoming entries independently,
with an explicit 64-entry traversal bound and at most four emissions per invocation.
These are policy/traversal bounds, not record fields or enumerated storage
positions. Each invocation also faces the native machine's total work budget.
Disabling an entry removes it and recovers capacity; the global epoch survives
removal. Updating an existing key uses no additional capacity. Source emits a `nil`/`cons` collection directly. The native ceiling is sixteen;
the mailbox policy selects its smaller page limit. No subscriber storage is
hand-enumerated.

The FIFO stores `size`, `front`, and reversed `rear` lists. Enqueue adds one
node; acknowledgement reverses the rear only when the front empties. Oldest
notice projection and capacity checks use constant-size source operations.
The object layers keep room for two or three notices. Topics and units have
semantic bounds; generation is bounded. Address/program form lengths are UI bounds, while native emission
and delivery validate addresses, hashes, payload size and exact program identity.
Bad subscription text cannot grant delivery authority. Every emitted descriptor
is checked against the exact recipient program.

Recipient consent and current command grants are separate requirements. A
copied subscription or old emission gives no relay grant. Source revocation
does not erase already-admitted message history. Exact native retries recover
receipts; the library does not invent another event-consumption ledger.
Receive stores a notice and emits nothing. There is no timer, polling loop,
implicit forwarding, external publication or exactly-once network claim.

The joined checks cover traffic both directions, both inherited capacities,
FIFO acknowledgement, finite vocabulary/unit guards, consent withdrawal and
renewal across independent sources, key/generation ABA refusal, copied-generation
forgery, current relay grant changes, retained refusals and declines,
an outside sender's impossible generations,
direct/forged receive attempts, exact retries, bounded collection fanout, target program
changes, assembled form limits, and installed pure views. The actual local relay
drains 32 obsolete events, recovers the pending quota and accepts a newly enrolled
notice. Worlds and participant activity stay in temporary private custody.


## Source examples and collection measurements

[RepairBoard.examples](RepairBoard.examples) runs through the existing proposal
fixture runner and actual compiled admission. It exercises sparse key 100,
withdrawal, attempted ABA at key 200, renewed consent and an empty FIFO refusal.
It also checks the source-owned initial menu. Cross-object delivery and custody
remain in the native receiving tests, since this example notation has one object.

[CollectionStudy.obend](CollectionStudy.obend) contains ordinary pure source
exports for collection measurements: `study(n)` fills and drains the FIFO,
selects the last subscription page, and checks an absent consent; `queue(n)` and
`subscriptions(n)` materialize typed data separately. These are synthetic values,
not installed authority or claimed delivery history. The conformance test runs
all algorithms with default machine limits and materializes sizes through 64.

Measured with copied native binaries and a private source snapshot on 2026-10-09:

| Entries | Combined algorithm ticks | Queue ticks + conversion | Consent pair ticks + conversion |
| --- | ---: | ---: | ---: |
| 8 | 3,824 | 939 + 251 | 1,080 + 383 |
| 32 | 13,832 | 3,555 + 755 | 4,056 + 1,295 |
| 64 | 27,176 | 7,043 + 1,427 | 8,024 + 2,511 |
| 128 | 53,864 | typed data nesting refusal | typed data nesting refusal |
| 200 | 83,888 | typed data nesting refusal | typed data nesting refusal |

The combined result adds 33 conversion nodes and stays below the default 100,000
work budget at 200. This establishes source algorithm execution, **not** support
for a 200-entry installed resident. Linked data exceeds the bridge's current
nesting bound before that size can be retained or passed back as state. More fuel
would not fix the representation limit. A future chunked/balanced source
representation must preserve these APIs and be checked through actual receiving
semantics before increasing installed capacities. Native request-byte and causal
budgets remain separate constraints.
