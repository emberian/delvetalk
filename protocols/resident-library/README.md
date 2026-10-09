# Resident behavior library

Two ordinary Objective Bend modules compose subscriptions and bounded mailboxes.
The independently authored [repair board](RepairBoard.obend) and
[reading circle](ReadingCircle.obend) reuse both; neither has a private delivery
engine or a generated copy of the behavior.

| Module | Reusable behavior |
| --- | --- |
| [Consent.obend](Consent.obend) | Four outgoing subscriptions and four recipient-owned incoming consents; a global monotone consent epoch; four bounded native emission descriptors |
| [Mailbox.obend](Mailbox.obend) | A typed FIFO notice list, explicit acknowledgement, contextual forms/view, and an open-recursive receiving layer |

`Mailbox.Inbox` calls `self.accepts`, `self.capacity`, and `self.maxUnits`.
The repair layer uses `super` to derive two slots and four units; the circle
layer derives three slots and six units and accepts an additional `reading`
topic. Both accept `help` and `ready`. The inherited store method therefore
follows each final object's policy without being copied or replaced.
The description evaluates that same assembled behavior to obtain form limits:
four units for the repair board, six for the reading circle.

## Compose and use

Supply ordered exact modules `Consent`, `Mailbox`, then `RepairBoard` or
`ReadingCircle` to the existing `objective-bend-spell@3` module adapter. Imports
resolve those supplied bytes. The adapter derives state, methods, forms and
panels from source. No Python source generator is involved.

With the native hosts already built:

```sh
python3 conformance/test_resident_library.py
```

The receiving profile is `compiled`. A local world initializes native messaging
before creating objects. Each keeper has `configure`, each member has `announce`
and `acknowledge`, and a separately granted relay has the receive-only `receive`
method. Law management and reprogramming have their own grants. Names in the
local tests are caller assertions, not authenticated remote identities.

1. The recipient's keeper calls `configure` with `side="listen"`, the sender's
   object and exact native program digest, a slot from 1–4, and a generation
   greater than its global epoch, bounded by 65535. A source already enabled in
   another incoming slot cannot be added twice.
2. The sender's keeper calls `configure` with `side="send"`, a slot from 1–4,
   the recipient's object/program digest, and that recipient's generation.
3. A member calls `announce {topic,units}`. Native admission retains addressed
   message evidence and validates target program identity.
4. A currently authorized relay explicitly delivers a retained event. The
   recipient's source checks native sender facts and its current consent,
   vocabulary, unit limit and mailbox capacity, with the outcomes below.
5. A member acknowledges the oldest notice before another delivery can fill
   that space. Answering a notice requires an explicit new announcement.

`configure` also takes `enabled`; disabling or renewing incoming consent must
advance the global epoch. A slot can keep its existing generation while other
slots change. Moving a withdrawn source to another slot requires a fresh epoch,
so it cannot revive old events. Program values come from native
`program-digest` results; an event's source identity and program come from native
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

The source stores at most four outgoing and four incoming consents and the
layer's two or three notices. Topics and units have semantic bounds; generation
is bounded. Address/program form lengths are UI bounds, while native emission
and delivery validate addresses, hashes, payload size and exact program identity.
Bad subscription text cannot grant delivery authority. All four descriptors,
including disabled slots, remain structurally valid.

Recipient consent and current command grants are separate requirements. A
copied subscription or old emission gives no relay grant. Source revocation
does not erase already-admitted message history. Exact native retries recover
receipts; the library does not invent another event-consumption ledger.
Receive stores a notice and emits nothing. There is no timer, polling loop,
implicit forwarding, external publication or exactly-once network claim.

The joined checks cover traffic both directions, both inherited capacities,
FIFO acknowledgement, finite vocabulary/unit guards, consent withdrawal and
renewal across independent sources, slot/generation ABA refusal, copied-generation
forgery, current relay grant changes, retained refusals and declines,
an outside sender's impossible generations,
direct/forged receive attempts, exact retries, four-slot fanout, target program
changes, assembled form limits, and installed pure views. The actual local relay
drains 32 obsolete events, recovers the pending quota and accepts a newly enrolled
notice. Worlds and participant activity stay in temporary private custody.
