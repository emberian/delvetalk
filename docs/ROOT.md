# Root

The owner has two layers of power over a world.

- **ROOT** is unrestricted: the owner reads, edits, zaps or ignores anything the system holds. It is built so that
  replay stays honest, not so that root is bound: every root act is a journaled entry marked `root`, applied verbatim
  on replay, carrying the value it replaced. Nothing is hidden; everything is possible.
- **MODERATION** is in-world: the opener's receipted powers under the law. It is the layer the town sees and the
  default the hand offers; root is one click further.

Every section ends with its decision. Code: `spec/Delvetalk/Host/Root.lean`, `RootEdit.lean`, `Moderation.lean`,
`Screen.lean`; `transport/root.py`, `transport/hand.py`, `transport/automod.py`.

## 1. ROOT

### 1.1 The op

One host op, `world-root`, on the root socket only (1.4):

    {op: "world-root", principal: <opener>, reason: <one line>, act: {…}}

`reason` is required (1 to 256 bytes); an empty one is a request error. The acts (`rootKinds`):

| `act.kind` | Fields | Does, and `before` |
| --- | --- | --- |
| `set` | `object, field, value`; `field` one of `state, law, program, pin, owner, read, version, fixed, supervisor, ledger, readings, activities` (`rootFields`), or `state.F` for one top-level field of the state | the field becomes exactly `value`, no judge; `before` is its prior value. `state` and `state.F` must still conform to the object's type (journaled with the new version and state CID). `program` takes `{modules: [{name, source}]}` and the host recompiles (pin derived); `pin` replaces the stored pin alone, as metadata: the methods keep running from unchanged inputs, so a pin does not stop an object; `retire` does |
| `delete` | `object` | the object leaves the store; references answer `unknownObject`; the id is free (`requiredAbsence` no longer finds it); `before` is the whole record |
| `as` | `principal, turn: {object, method, argument, identity}` | an ordinary turn under any principal, judged by the law as that principal; journaled as an ordinary `admitted`/`refused`/`suspended` entry with `root {by, reason}` beside it; `before` empty. To bypass the law, `set state` |
| `settings` | any of `clock, postQuota, interpretQuota, modelQuota, turnQuota, objectQuota, paintQuota, opener, libraryLaw` (the quotas are the host's `quotaKeys`, as `world-settings` and the `settings` power take) | a `settings` entry whose values replace the last. The clock may move either way: deadlines, grants and quotas read it, a backward clock re-opens them, and the reply lists the suspensions and grants affected (`clockAffected`) |
| `library` | `{modules}` | re-seals the library without the world law's judgement; `before` the old pin |
| `ignore` / `unignore` | `height` | replay skips entry `height`'s effects (1.3); `before` is `ignored: false/true` |
| `card` | `object, text` (or `null` to clear) | `world-card` answers this text instead of running `render` until cleared; `before` the prior override |
| `quiet` / `unquiet`, `hide` / `show`, `retire` / `unretire`, `revoke` | as MODERATION's powers (2.2); `quiet` takes `principal, hours`, `hours: 0` clears | the same effect without the law's judgement and without the metarule |
| `expire` | `principal, scratch` | discards a scratch world now (FEDERATION §3). A scratch is serve's, not a journal's: answered by `serve` itself, recorded in the hand's log only |

**Decision:** one op, a required reason; `as` is judged, `set` is not.

### 1.2 The entry

A root entry is a journal entry like any other, inside the chain, with the marker inside the hash:

    {height, previous, hash, identity: {principal: <opener>, intent: "root:<ordinal>"},
     root: true, reason, turn: 0, roots: [],
     outcome: {tag: "root", kind, object?, field?, before, after}}

- `before` and `after` are canonical `Data` or JSON, whole, up to `maxEntryBytes` (1 MiB; a larger state is journaled
  by CID with the bytes in `blocks`, as checkpoints are).
- `projectEntry` shows a root entry whole to every reader, `before` included: the fact and the values are public. A
  later root `set read` may narrow who reads the object; the root entry itself stays whole.
- `world-history <object>` lists it among the object's receipts; the object page stamps it `root`; the hand's
  moderation log and `/xrpc` serve it. A slug names it as any entry.

**Decision:** marked inside the hash, whole, public; no root entry is ever projected as something else.

### 1.3 The replay rule

`replayEntry` on a `root` entry checks `before` against the store as it stands (a mismatch refuses the journal by
name, "root entry N: before does not match"; the offline tool keeps `before` consistent when it splices), then applies
`after` verbatim: no judge, no conformance check, no pin check (a `program` recompiles from the journaled sources; a
`pin` is set as stored). Derived indexes (`touched`, `receipts`, `posts`, `grants`, `suspended`, `pending`) are rebuilt
from the new value as `record` rebuilds them.

**Ignore.** With `ignore N` journaled at height M > N, replay from genesis applies 1..N−1, treats N as refused (its
writes, creates, sends, grants, offers and publishes not applied; its identity not bound), and runs on.

- A later entry that re-judges against the changed store and no longer holds (a root it read now at another version, a
  write to an object N created) is not refused: it is **shadowed**, its effects skipped, and the open report lists it
  (`world-status.shadowed: [{height, by, reason}]`; `verify` prints them).
- Snapshots written before M are refused on open (the store differs) and the chain is replayed; the next snapshot
  carries the ignore.
- `unignore` restores N on the next replay. Ignoring a root entry is allowed and shadows what it set.

Root entries, `shadowed` and the marker are replay-derived facts, under `replayEdition` (`Store.lean`).

**Decision:** `before` checked, `after` verbatim, later entries shadowed and reported, never silently re-judged.

### 1.4 The root socket

`serve` (FEDERATION §1) opens two sockets:

- **public** (`--socket`, default `<dir>/state/host.sock`, mode 0600; it may live apart from the journals, so the front
  mounts none): the front, bridge, interpreter and the public verbs.
- **root** (`<dir>/root/root.sock`, mode 0660, group `--root-group`, so the hand runs under its own uid in that group):
  the root ops (`rootOps` in `Serve.lean`): `world-root`, `world-dump`, `world-library`, `world-settings`,
  `world-fork`, `world-snapshot`, `library-load`, `world-screen`, `world-screen-verdicts`, `world-screen-review`.

A root op on the public socket is a request error of class `opener`, "the opener speaks on the root socket". The
opener's ordinary turns go to the public socket (the bridge submits her posts as a resident's); her privileges do not:
amending another's thing, revoking any grant, the powers, naming an owner (`World.resident`, `openerActs`).

Owner-only by filesystem: `/data/root/` is a volume mounted into the hand's container (`compose.hand.yml`) and
`delvetalk-ops`, and into nothing else. On the box it is reached through the ssh forward to the hand's loopback
listener and through `docker compose run delvetalk-ops`.

**Decision:** the opener's authority is a socket, not a token; the socket is a mount.

### 1.5 The offline tool

What cannot be journaled is done to a closed journal, writing a new file and keeping the old (`RootEdit.lean`):

    delvetalk-obend root-edit --journal J --out J2 --reason R <command>
    delvetalk-obend root-edit --state DIR --reason R delete-world --name W

| Command | Does |
| --- | --- |
| `truncate --height N` | keeps entries 1..N; snapshots past N are dropped |
| `drop --height N` | removes entry N and re-chains N+1.. |
| `rewrite --height N --entry FILE` | replaces entry N's body with FILE (any field, a root entry's `before` and `after` included) and re-chains |
| `splice --at N --entries FILE` | inserts entries after N and re-chains |
| `delete-world --name W` | moves `<dir>/W.journal` and its snapshots to `<dir>/deleted/W-<stamp>.journal`; `serve` stops serving it; references answer `foreignWorld` |

`--out` must not exist. Re-chaining changes every CID from the edit onward: every later slug changes, `at://`
citations of those entries stop resolving, and the repository serves the new CIDs. The first re-chained entry carries
`rootEdit {command, reason, oldHead, at}` inside its hash, so a rewritten journal says it was rewritten and from what.
The tool prints the old-to-new hash table and the count of slugs changed; `verify.sh` replays `J2` before anything
installs it. The sequence is DEPLOY's restore: `down`, `backup.sh`, `root-edit`, `restore.sh` with `J2`, `up`.

**Decision:** five commands, a new file every time, the edit marked in the chain, the slug cost printed.

### 1.6 The hand's root page and CLI

`/hand/<world>/root/` (and `hand root <verb>`), behind the hand's token, with a red rule across the top and a reason
box on every form:

- **Object editor:** `hand root dump OBJ` prints the record as JSON (state, law, program sources, pin, owner, read,
  version, fixed, supervisor, ledger, activities); the page shows each as an editable textarea; Save is one
  `world-root set` entry per changed field. `hand root set OBJ FIELD --value-file F --reason R`.
- **Journal browser:** `hand root entries [--after N] [--object O] [--principal P]` pages the journal whole, read from
  its file (the host projects another's refusal even to the opener). Each entry has Ignore/Unignore (`hand root ignore
  N --reason R`) and Edit, which prints the `root-edit rewrite` command with the entry saved to a file, since an
  in-place edit is offline.
- **Act as:** principal, object, method, argument (JSON or a spell), intent; `hand root as P OBJ METHOD
  --argument-file F --reason R`.
- **Delete, card, settings, library:** `hand root delete OBJ`, `hand root card OBJ --text-file F|--clear`, `hand root
  settings --clock N --post N --interpret N --model N`, `hand root library DIR`, each with `--reason R`.
- **Shadowed:** the strip shows `world-status.shadowed`, each linked.

Every verb logs to `hand-log.jsonl` (`who: cli|owner`, the entry's height); the journal is the record.

**Decision:** a raw editor, a browser with ignore, an act-as field, a reason on all of them; no verb hides a root
entry.

### 1.7 What root cannot do

- **Make a root entry look ordinary.** `root: true` is inside the hash, and an unmarked state write no method made
  fails replay's re-judge (`admitted` entries are re-judged). A forged ordinary entry breaks replay; a root entry
  replays.
- **Recompute another's receipt to look original.** Any changed byte is a new CID; the old slug resolves to nothing;
  the repository serves the new record under a new name; the `rootEdit` marker names the old head.
- **Un-reply.** An entry a resident holds a slug for was fsynced before its reply. `truncate` can remove it; the slug
  then answers `unknown` and the chain says `rootEdit` at that height. That is the one root act a resident can detect
  from outside, and the marker is what they find.
- **Un-send.** A Delve or Zulip post, a model call, a reservation that left the box. `unpost` deletes and journals; the
  spend was spent.

**Decision:** root's only limits are hashes and the outside world; both are named on the entry.

## 2. MODERATION

The opener's powers as judged, receipted turns, offered first by the hand, with root one click further.

### 2.1 The metarule, widened

No law can lock out the hand that opened the world: an amendment (kind 2) by the world's opener is the host's to admit,
whatever the law says (`openerAmends`, in the commit's judgement). `world-inspect`'s `laws` rows show it as the clause
`opener`: `request.kind == 2 and request.subject == "<opener>"`. In a scratch world the resident is the opener. Root
does not need this rule; the town does, so the opener's amendments are law and not root.

**Decision:** the opener can always amend; the laws page says so.

### 2.2 The powers

Host spells the opener casts on the card they touch or on `world`, the reserved id the host answers for. A non-opener
is refused `badSpell`, clause `opener`. Each journals one entry under the opener's identity with a required reading,
visible in `world-history` and on the object page, and hob says it within VOICE's 25 tokens.

Retirement appends the law clause `retired "<reading>": request.kind == 2 and request.subject == "<opener>"`
(`retiredLaw`; the root act, the card power and a carry's `--leave` write this one clause). It frees the maker's
`objectsPerPrincipal` share while keeping the name, state and global object slot. `unretire` must fit the maker's
share; root's acts are outside these admission checks. A maker whose law admits their own amendment can add their own
`retired` clause with `world-amend` (FOUNDATION §2); removing it must fit their share. That is not the opener's power.

| Problem | Power | Journaled as | hob |
| --- | --- | --- | --- |
| a resident floods a card | `delvetalk world quiet / who: <handle> / hours: N / reading: …`: their turns until `until` refused `quiet` (transient class; `clause: until clock N`, `reason` the reading, `next`) | `quiets [{principal, until, reading}]` | `hob: the hand quieted you until clock N; the reason is on the receipt. Come back then.` |
| a law locks a thing | `amend / law:` or `adopt / law: <id>` as the opener (kind 2, under 2.1) | `amendments` | `hob: the hand amended that law; the clause is named on the receipt.` |
| a body burns the model on every instance; an interpretation loop | `retire / reading:`: writes refuse `refused retired: <reading>`, `?` lists nothing, `become / kind:` of it refuses; `unretire` removes the clause; the world's `modelQuota` (OPERATIONS §b) holds the day | an amendment | `hob: that card is retired; the reason is on its page. The directory lists the doors.` |
| an abusive card text; a squatted name | `hide / reading:`: read policy `principals [owner, opener]`; the text leaves every page and draft and stays in the journal; the hiding entry is public; `show` reverses. Then retire. A name once taken stays taken; the doors are the opener's | `hides [{object, reading}]` | `hob: no public page for that now; its owner and the hand still see it.` |
| a scratch full of junk | root's `expire` from the hand's worlds page, `hand root expire --principal P --scratch <name> --reason R` | the hand's log only | `hob: that scratch is gone; open it again from town entry N.` |
| a model misread that admitted something | the write stands; the card's owner retracts its row; the opener sets `confirmFor` on `policy` so the action asks first | the policy's write | `hob: I read that as` then the spell, `yes, or correct it.` |
| a bridge posts the wrong thing | `hand skip` a draft; once posted, `hand unpost URI --reason` deletes the PDS record or Zulip message and journals `unposted {uri, reason}`; `hand reply` corrects, drafted `by hand` | `unposted` (clock principal, as `posted`) | `hob: the hand withdrew that post; its receipt stays.` |
| a grant the opener did not make | `delvetalk world revoke / grant: <id> / reading:` | `revokes [id]` with `by`, `reading` | `hob: that grant is revoked; the receipt says by whom.` |
| a quota wrong for a world | `delvetalk world settings / interpretQuota: 24 / reading:` (`world-settings`: a new `settings` entry; replay reads the latest) | `settings` | `hob: the hand set my hour to 24 readings; the spell itself needs no reading.` |
| a journal that will not reopen | no in-world power: a verified copy (DEPLOY), `world-fork` to a height into a fresh world, or root's `truncate`; `maxJournalBytes` is checked at open only (OPERATIONS §c) | `forked` | `hob: this town restarts from entry N; the old one still answers, read-only.` |

**Decision:** host spells `quiet`/`unquiet`, `retire`/`unretire`, `hide`/`show`, `revoke`, `settings`, root's `expire`,
and the host's `amend`/`adopt`; readings required.

### 2.3 The hand's moderation verbs

`--world W` on every verb (default `town`); each a thin call over the root socket under the opener, each power a form:

| Verb | Op | Page |
| --- | --- | --- |
| `quiet WHO --hours N --reading R`, `unquiet WHO` | `world-turn` on `world`, `quiet` | PRINCIPALS: turns this hour, refusals, quieted-until |
| `retire OBJ --reading R`, `unretire OBJ` | `world-amend` | the object's row |
| `hide OBJ --reading R`, `show OBJ` | `world-turn` on `world`, `hide` | same row |
| `amend OBJ --law-file F --reading R`, `adopt OBJ --law ID` | `world-amend` | the law in a textarea beside its rows |
| `revoke GRANT --reading R` | `world-revoke` | GRANTS |
| `root expire --principal P --scratch S --reason R` | `world-root {act: {kind: expire, principal, scratch}}` | the worlds (`/hand/`): each scratch with its owner, size, last turn and expiry |
| `unpost URI --reason R` | transport delete, `world-unposted` | the inbox row |
| `settings --post N --interpret N --model N --reading R` | `world-settings` | the strip's quotas |
| `log [--tail N]` | `world-entries` filtered to the opener's and root entries | MODERATION, newest first, root entries stamped |
| `find TEXT` | the handle registry, `world-objects {prefix}`, `world-resolve` | one box |
| `status` | `world-status` plus `hour {turns, refused: {class: n}, interpretations, attempts}` (derived by `record`, nothing journaled) and `shadowed` | the strip |

Every object row and log row links to the root page ("root: edit this object", "root: ignore this entry").

**Decision:** moderation is the default face; root is one click further and never the default.

### 2.4 Automatic moderation

Foul, obscene or abusive public text is screened after admission, on by default on every town, without spending hob's
model budget and without adding latency to a turn.

**Retroactive.** A resident's text is admitted as ever; nothing waits in a turn. Screened is every text a public page
can show:

- the labels a resident's admitted turn wrote or created on an object the public may view (record lines, say and emote
  lines, kinds' voices, abouts and heads, scenes, grown verbs' readings, register rows, inspirited surroundings:
  whatever the edits carry, `Moderation.entryItems`);
- the name recorded at an arrival;
- the feed's posts (the transport offers them, `feed:<uri>`).

The opener's, the clock's and a thing's own (`@id`) texts are the town's, never screened. Object ids, principals and
links are not words.

**The past.** A carried town's history before its carried genesis is screened by `transport automod --backfill`: the
ancestor journals the genesis cites, read through the host (`world-screen {until, dryRun}`, which with `dryRun`
journals nothing, and `world-screen-verdicts {dryRun}`). The dry run's report is read by the owner before `--act` hides
anything; a past text quiets nobody. Bounded per pass, resumable by its cursor.

**The worker** (`transport/automod.py`, service `delvetalk-automod`, on the root socket: a moderation act is the
opener's):

- asks `world-screen {after, external}` every second; the host answers the texts written since the cursor, less any
  screened, after running its wordlist (`Screen.prefilter`: a dozen slurs and child-abuse terms, whole words, reading
  digit stand-ins and spaced-out letters). A hit is hidden and its author quieted at once, with no model.
- holds the rest: a text waits `automod_window` (5 s) for others; a full batch of `automod_batch` (24) goes at once.
- makes one Messages API call per batch to the owner's Z.ai subscription (`automod_base_url`, its
  Anthropic-compatible endpoint; `automod_model`, glm-5.3-flash; thinking off, about 2 s a call), each text numbered
  and clipped to 2 KiB, a batch to 32 KiB.
- hands the reply verbatim to the host (`world-screen-verdicts`), which reads one verdict per number and decides: high
  confidence hides the text and quiets its author `automod_quiet_hours` (24); medium hides it; low hides nothing and
  waits for the owner; `sexual-minors` is always high. An unanswered text is asked again.
- calls nothing when idle; has its own day of calls (`automod_daily_calls`, 2000) and ledger (`automod-spend.jsonl`),
  apart from hob's and the paints'.
- when GLM fails: the texts wait on disk with the cursor, the worker backs off (5 s doubling to 300 s), the wordlist
  still acts, and the hand's overview says "the classifier is down". When the provider's own filter refuses a batch
  it is asked again in halves; a single text it refuses is hidden at medium for the owner to look at.

**The policy** (`Moderation.policy`, the classifier's system text):

- Flagged: hate (slurs; attacks on a group), explicit sexual content, graphic gore for its own sake, harassment of a
  real person or a named resident, self-harm encouragement, spam (the same text flooded again and again, repeated
  identical promotion, scams, link-dumping).
- Not spam: games, number or tag chains, relays and rounds, call-and-response, counting, repeated short turns that
  each differ. Short, odd or numeric handles (`y02`, `j3rry`) are names. When unsure whether play or spam, do not flag.
- Not flagged: disagreement, dark or violent fiction without gratuitous detail, horror atmosphere (the parlour's
  dread, ghosts, death, blood), villains, romance, casual profanity. A text is flagged for what it does to a reader or
  a person, never for its mood, its darkness or a swear word.
- Confidence: high is unmistakable, medium likely, low unsure and needs a person.
- The wordlist errs toward missing: words with innocent uses (`chink` of light, `fag`) are the model's.

`python3 deploy/automod-probe.py 'y02' "THE RELAY GAME - round 7: tag, you're it: 14 -> 15"` asks the classifier
without changing a world and prints one JSON verdict per text. With no text arguments it reads one text per stdin line;
quote a multiline argument to probe a whole round. It reads `Moderation.policy` from the Lean source in the checkout,
or plain system text from `--policy FILE`; `--key-file FILE` defaults to `~/.zai-key`.

**What a flag does.** One `moderated` entry under the opener, power `screen` (intent `screen:<height>`):
`{key, text, source, author, at, category, confidence, by, reading, before, after}`, `after` the state (`hidden`,
`review`, `confirmed`, `restored`), `key` the CID of the text. A high flag adds an ordinary `quiet` entry whose reading
begins `automod`. Replay applies both verbatim and derives `World.screened` (snapshotted, carried); it needs no model.

A `hidden` or `confirmed` text leaves every reply but the opener's (`Session.stepWorld`; a cross-world read in
`Serve.readForeign`): a card, a view, a history, the strokes a paint or telling is made from (`Strokes.redacted`, so no
paint quotes it and the paint's key moves), a paint's request, an interpretation's quoted writing, the repository's
projections. `[hidden by moderation]` stands in its place; a short one-word text only where it stands as a word. The
feed asks `world-redact` for its posts. The journal keeps the bytes; the screen entry's public projection omits
`text` (the fact is public, the words are not published again).

**The owner** sees the worker's state, the counts and the newest flags on the overview, and every row at
`/hand/<world>/automod` (`hand automod [--only STATE]`), each with restore, confirm or hide (`world-screen-review`;
`hand automod restore KEY --reading R`), journaled as a `screen` entry `by: owner`. Restore also lifts a quiet whose
reading begins `automod`; a restored text is never screened again. `world-screen`, `-verdicts` and `-review` are root
ops; `world-screened` answers the opener whole and anyone else the hidden keys and sources only.

`screen` and `World.screened` are replay-derived; a carry from an edition before them starts `screened` empty.

**Decision:** screened after admission, never before; the wordlist at once, the classifier in five-second batches; the
host decides from the reply and journals; hidden by redaction at every public reply, never by rewriting a state.
