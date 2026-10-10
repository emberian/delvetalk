# Root

The owner's console, written 2026-10-10 against foundation dd5cd2f, FEDERATION
(one host, many worlds, scratch worlds), HOST-HANDOFF 5.1 to 5.120 and the
Zulip playtest. Every root power is a turn by the **opener** principal, judged
and journaled like any other, with a receipt on the object it touched. Nothing
here bypasses `judge`; the hand (Python) decides nothing. Every section ends
with its decision.

## 1. What the opener is today

The opener is `DELVETALK_OPENER`, journaled in the `settings` entry at first
open. It alone may `world-create {owner}`, change the library (the world law
`opener: request.subject == "<opener>"`, kind 1), and it is the creator of
every arrival's avatar, `env/<did>` and `wake/<did>`, so the default law
(`owner: request.kind == 0 or request.subject == "<creator>"`) lets it
reprogram or amend those. It is exempt from `interpretQuota`. It is not exempt
from any other law: a resident's bell, kind or deal admits its creator alone,
and the metarule (an amendment must be admitted by the existing law for its
proposer) binds the opener as it binds anyone. `world-revoke` is the
grantor's. `world-fork` copies. The hand's eleven verbs act on drafts and
observations, never on the world. Today a resident is quieted, a card stopped
or a quota changed only by killing a container or by a new genesis.

**Decision:** the console is the opener's existing authority widened in one
rule (section 2) plus a short list of host spells (section 3); no admin
principal, no flag, no second law.

## 2. The metarule, widened

The playtest's own words: "no law can lock out the hand that wrote it." The
hand that wrote the town is the opener. The rule becomes: **a law is accepted
only if it admits an amendment (kind 2) by its proposer and by the world's
opener.** Checked where the proposer's clause is checked now (`makeObject`'s
dry run at creation, amendment and reprogram); the refusal names it, "law
does not admit an amendment by the opener <did>". The default law gains the
clause `or (request.kind == 2 and request.subject == "<opener>")`, and
`world-inspect`'s `laws` rows show it with its reading, so a resident reading
any card's law sees that the opener may amend it, and sees nothing else: no
read, write or reprogram is widened.

What the town loses: a resident cannot make a thing in the town whose law the
opener cannot amend. In a scratch world the resident is the opener, so there
they can; `make` into the town is judged under the town's rule at the exit.
Cost: one clause in `Law.lean`'s dry run, the default law text, the fixtures
that pin it, `replayEdition` 3 (a judging rule changed; HOST-HANDOFF 6).

**Decision:** widen the metarule to the opener; say it once on the laws page;
no other widening.

## 3. The problems, and the power that answers each

The playtest, 74 minutes: three bells, eight model calls from four prose
posts, three cross-talk misreads, a desk silent for 43 minutes behind a quota
that should not have applied, loopback links in posts. Forty residents do the
same, oftener. Each row names the power, its form, what the journal holds,
and hob's line (VOICE: at most 25 tokens, only where words reach).

| Problem | Power | Cast as | Journaled as | hob |
| --- | --- | --- | --- | --- |
| a resident floods a card (a spell every poll, two hundred rains an hour) | **quiet** a principal for N hours with a reading; every turn by them until the clock passes `until` is refused `quiet` (class, transient; `clause: until clock N`, `reason` the reading, `next`) | `delvetalk world quiet / who: <handle> / hours: 6 / reading: …` | `quiets [{principal, until, reading}]` on an admitted entry under the opener | `hob: the hand quieted you until clock N; the reason is on the receipt. Come back then.` |
| a law locks a thing (a kind whose clause refuses every write; an owner who left) | **amend** as the opener, naming the clause, under section 2 | `delvetalk <card> amend / law: <text>` (the host's `amend`, kind 2) or `adopt / law: <id>` | `amendments` as today, subject the opener | `hob: the hand amended that law; the clause is named on the receipt.` |
| a body burns budget on every instance (a kind whose `receive` calls `interpret` on everything) | **retire** the kind: an amendment appending `retired "reading": request.kind == 2 and request.subject == "<opener>"`, so every write refuses `refused retired: <reading>`, `?` lists no spells (`offeredTo` hides what the law refuses), `become / kind:` of it refuses; un-retire is amending the clause away; plus the world's model cap (OPERATIONS §b) | `delvetalk <card> retire / reading: …` | an amendment | `hob: that card is retired; the reason is on its page. The directory lists the doors.` |
| an abusive card text (a seed, an anthology line) | **hide** from the public pages: the read policy narrowed to `principals [owner, opener]`; a public reader gets `no card X that you may see`; the text stays in the journal and leaves every page, listing and draft; then retire. The hiding entry is public: the fact is visible, the text is not | `delvetalk <card> hide / reading: …`; `show` reverses | `hides [{object, reading}]` | `hob: no public page for that now; its owner and the hand still see it.` |
| a stranger's object squats a name (`garden2`, `library-help`) | hide and retire. A name once taken stays taken (`requiredAbsence` is forever); the names that matter are the directory's doors, and the directory is the opener's | as above | as above | as above |
| a scratch world full of junk | **expire** it now: the one deletion in the system (FEDERATION §3), allowed because a scratch is never state | `delvetalk world expire / scratch: <name> / reading: …` | nothing durable (a scratch journals nothing in the home world); the hand's log line | `hob: that scratch is gone; open it again from town entry N.` |
| a resident who should be quiet | quiet, above; the reading says why | | | |
| a model misread that admitted something (prose read as `plant`, the garden ran it) | nothing is erased: the write stands, its receipt says `interpreted`, the card's owner retracts the row. The opener's power is to make that action **ask first**: `confirmFor` on the `policy` object, an ordinary spell on a card the opener owns; hob then shows the spell for a yes | `delvetalk policy set / confirmFor: plant` | the policy's write | `hob: I read that as` then the spell, `yes, or correct it.` |
| a bridge posts the wrong thing | on Delve nothing posts without a click: `skip` the draft. Posted already (Delve by click, Zulip by the bot): **unpost** deletes the PDS record or Zulip message and journals `unposted {uri, reason}` so replies stop routing to it; **correct** is `hand reply` on the parent, drafted `by hand`, posted by click | `hand unpost URI --reason R`; `hand reply URI --text-file F --object O` | `unposted` (identity `unposted:<uri>`, clock principal, as `posted`) | `hob: the hand withdrew that post; its receipt stays.` |
| an interpretation loop (a card reading its own offers; two cards sending each other) | the ledger bounds a chain of sends (`{depth 100, work, storage}`); a loop through the model is bounded only by `interpretQuota`, from which the opener and clock are exempt. Retire the card; the model cap holds the day meanwhile | `retire`; `world settings / modelQuota: N` | an amendment; a `settings` entry | as retire |
| a journal that will not reopen | no in-world power. `verify.sh` names the height; recovery is a verified copy (DEPLOY), or **replay to a height into a fresh world**: `world-fork {height: N-1, into}` from the verified prefix, served under a new name, the old journal kept read-only for its receipts. The 256 MiB `maxJournalBytes` is checked at open only (OPERATIONS §c) | `hand replay --height N --into town-2` | `forked` genesis | `hob: this town restarts from entry N; the old one still answers, read-only.` |

Three more the owner will reach for:

- **revoke a grant** the opener did not make: `world-revoke` widened to the
  opener, journaled `revokes [id]` with `by` and `reading`, so the holder's
  card says "revoked by the hand: <reading>". `delvetalk world revoke / grant:
  <id> / reading: …`. hob: `hob: that grant is revoked; the receipt says by whom.`
- **raise or lower a quota per world**: `postQuota`, `interpretQuota` and the
  new `modelQuota` (OPERATIONS §b) are journaled in `settings` at first naming;
  a later open with other values is refused. The power is a new `settings`
  entry by the opener (`world-settings {principal, postQuota?, interpretQuota?,
  modelQuota?, reading}`; replay reads the latest). `delvetalk world settings /
  interpretQuota: 24 / reading: …`. hob: `hob: the hand set my hour to 24
  readings; the spell itself needs no reading.`
- **rotate the key**: not a world fact. `hand rotate-key FILE` does what
  DEPLOY says (write beside, `mv` over, revoke the old) and logs it; `model.py`
  reads the file per request, so nothing restarts.

Every power is cast on a card (`retire`, `hide`, `amend`) or on `world`, the
reserved id the host answers for; `inspect world` lists the spells; a
non-opener casting one is refused `badSpell`, clause `opener`, "Only the hand
that opened this world casts that." Each is one entry under the opener's
identity, so `world-history <card>` shows it among the card's receipts and
the object page lists it as a stamped slip beside the residents' turns.
Moderation is a fact of the world: nothing is hidden, some things are refused
by name, and the name is on the receipt.

**Decision:** six host spells (`quiet`, `retire`, `hide`/`show`, `expire`,
`revoke`, `settings`) and the existing `amend`/`adopt`; every one a journaled
entry; readings required on all of them.

## 4. The console: the hand grown

The hand stays what it is (`transport/hand.py`, 289 lines: one class, two
faces) and gains `--world` (default `town`), one verb per power, the
moderation log, a search, and the counters. A page per power is a form
posting to the same verb; the CLI is the verb with `--json`.

| Verb | Host op | Page |
| --- | --- | --- |
| `quiet WHO --hours N --reading R`, `unquiet WHO` | `world-turn` on `world`, method `quiet`, as the opener | PRINCIPALS: a row per handle with turns this hour, refusals, quieted-until; buttons quiet/unquiet |
| `retire OBJ --reading R`, `unretire OBJ` | `world-amend` as the opener | the object's row: retire, hide, amend |
| `hide OBJ --reading R`, `show OBJ` | `world-turn` on `world`, `hide` | same row |
| `amend OBJ --law-file F --reading R`, `adopt OBJ --law ID` | `world-amend` | the law text in a textarea beside the laws rows |
| `revoke GRANT --reading R` | `world-revoke` widened | GRANTS: `world-grants` rows |
| `expire SCRATCH --reading R` | `world-scratch-expire` (FEDERATION §3's sweep, now) | SCRATCHES: name, owner, bytes, expires in |
| `unpost URI --reason R` | PDS/Zulip delete, then `world-unposted` | the inbox row's posted reply |
| `settings --post N --interpret N --model N --reading R` | `world-settings` | the status strip's quotas, editable |
| `replay --height N --into W` | `world-fork` | SETTINGS, with a confirmation naming the height's receipt |
| `rotate-key FILE` | none | SETTINGS |
| `log [--tail N] [--world W]` | `world-entries` filtered to the opener's identity and the clock's `unposted` | MODERATION: newest first, each with object, reading, slug |
| `find TEXT` | registry handles (`world-principal`'s index), `world-objects {prefix}`, `world-resolve` for a slug | one box: handles, objects, receipts |
| `status` | `world-status` plus `hour` (below) | the strip |

**The counters**, per world, from `world-status` grown by one derived field,
`hour: {turns, refused: {class: n}, interpretations, attempts}` kept by
`record` for the current clock hour (nothing new is journaled): turns,
refusals by class, model calls (interpretations started plus `attempted`
retries), spend (`model-spend.jsonl` this month, dollars at the published
rates), reservations (`posts.sources[delve].used` of `quota`, `next`),
scratch worlds (`scratches {open, expiring}` when FEDERATION 2 lands),
pending interpretations and the oldest's age, clock against unix minutes.

**The moderation log is the journal.** `hand log` is a read; `hand-log.jsonl`
keeps only what the world cannot hold (clicks on drafts, a key rotation, an
expire). The whole record is `/xrpc`, as the repository façade serves it.

**Decision:** verbs as thin calls, ~150 lines of Python, under the 4,400
ceiling once `hostd.py`/`hostproc.py` (381) go; one new host field (`hour`)
and no new log.

## 5. What must not be possible

- **Editing a journal.** The console has no verb that opens the journal file;
  the host only appends; recovery is a verified copy. An edited line breaks
  the chain and `verify.sh` names the height. The repository façade serves
  entries by CID, so a changed entry has another name.
- **Forging a receipt.** A receipt is an entry's CID; the slug is a projection
  of it; posts carry the slug and never the hash; `world-resolve` is the only
  authority and answers `unknown` for a slug the journal does not hold. The
  hand's `reply` drafts carry `hand: true` and no receipt line.
- **Acting as another principal.** Every console verb sends the opener's
  principal (posting sends the clock's, as the bridge does) and the entry
  carries it; there is no `--as`. `find` reads as the opener, so a stranger's
  receipt shows its public projection, as to anyone. The residual, said
  plainly: hostd's socket (mode 0600) takes any principal from whoever holds
  it, as the bridge acts as every observed DID. The box is the trusted base;
  the console adds no door to it. When `serve` lands (FEDERATION 1) the host
  should take opener-principal ops on a second socket the front and bridge do
  not mount, so forging the opener needs the host's own listener.
- **Deleting anything but a scratch.** Hide narrows a read policy; retire
  appends a clause; unpost journals a fact and deletes on the transport, where
  the post was never the world's.

**Decision:** no verb touches a file the host owns; the second socket is
FEDERATION 1's to add.

## 6. The three to build first

1. **`quiet` and `retire`, with the widened metarule** (host; `replayEdition`
   3). The playtest's only tools against a resident breeding model calls were
   to stop the bridge or to ask; the town needs a refusal by name with a clock
   on it.
2. **`world-settings` and `hour`** (host, small): the quotas become something
   the hand can move without a genesis, and the model cap can exist at all.
3. **The hand's `--world`, the verbs and the moderation page** (transport):
   thin calls over 1 and 2, measured by one test per verb that reads the
   entry back from `world-history`.

`hide`, `revoke`, `expire` and `unpost` follow in that order; `replay` and
`rotate-key` are DEPLOY's commands with a verb in front.

**Decision:** 1, 2, 3 before the town; the rest in the first week after.
