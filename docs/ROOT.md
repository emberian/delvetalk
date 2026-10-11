# Root

Two layers, written 2026-10-10 against foundation 447de51, FEDERATION
(`serve`, scratch worlds), HOST-HANDOFF §3 (the entry shape), §5.6 (replay
and snapshots), §6 (the replay edition) and the Zulip playtest.

**ROOT** is unrestricted: the owner reads, edits, zaps or ignores any
representation the system holds. The mechanism is designed so that replay
stays honest, not so that root is bound: every root act is a journaled
entry marked `root`, applied verbatim on replay, carrying the value it
replaced. Nothing is hidden; everything is possible.

**MODERATION** is in-world: the opener's receipted powers under the law,
the layer the town sees and the default the hand offers, with root one click
further.

Every section ends with its decision.

## 1. ROOT

### 1.1 The op

One host op, `world-root`, over the root socket only (1.4):

    {op: "world-root", principal: <opener>, reason: <one line>, act: {…}}

`reason` is required (1 to 256 bytes); an empty one is a request error. The
acts:

| `act.kind` | Fields | Does, and `before` |
| --- | --- | --- |
| `set` | `object, field, value` where `field` is one of `state, law, program, pin, owner, read, version, fixed, supervisor, ledger, readings, activities` | the object's field becomes exactly `value`, no judge, no type check; `before` is the field's prior value. `program` takes `{modules: [{name, source}]}` and the host recompiles (pin derived); `pin` sets the stored pin alone, so an object whose pin names no journaled closure answers every turn `programRefused: no sources for pin` until `program` is set, and the op says so in its reply |
| `delete` | `object` | the object leaves the store; references answer `unknownObject`; the id is free (`requiredAbsence` no longer finds it); `before` is the whole object record |
| `as` | `principal, turn: {object, method, argument, identity}` | an ordinary turn run under any principal, judged by the law as that principal; the entry is an ordinary `admitted`/`refused`/`suspended` entry with `root {by, reason}` beside it; `before` is empty. To bypass the law, `set state` |
| `settings` | any of `clock, postQuota, interpretQuota, modelQuota, opener, libraryLaw` | a `settings` entry whose values replace the last; the clock may move either way (deadlines, grants and quotas read it; a backward clock re-opens them, and the reply lists the suspensions and grants affected) |
| `library` | `{modules}` | re-seals the library without the world law's judgement; `before` the old pin |
| `ignore` / `unignore` | `height` | replay skips entry `height`'s effects (1.3); `before` is `ignored: false/true` |
| `card` | `object, text` (or `null` to clear) | `world-card` answers this text in place of running `render` until cleared; `before` the prior override |
| `quiet`, `hide`, `retire`, `expire`, `revoke` | as MODERATION's spells | the same effect without the law's judgement and without the metarule |

**Decision:** one op, nine acts, a required reason; `as` is judged, `set` is
not.

### 1.2 The entry

A root entry is a journal entry like any other, inside the chain, with the
marker inside the hash:

    {height, previous, hash, identity: {principal: <opener>, intent: "root:<ordinal>"},
     root: true, reason, turn: 0, roots: [],
     outcome: {tag: "root", kind, object?, field?, before, after}}

`before` and `after` are canonical `Data` or JSON, whole, up to
`maxEntryBytes` (1 MiB; a state past it is journaled by CID with the bytes
in `blocks`, as checkpoints are). `projectEntry` shows a root entry whole to
every reader, `before` included: the fact and the values are public. A root
`set read` that follows may narrow who reads the object; the root entry
itself stays whole. `world-history <object>` lists it among the object's
receipts; the object page stamps it `root`; the hand's moderation log and
`/xrpc` serve it. A slug names it as any entry.

**Decision:** marked inside the hash, whole, public; no root entry is ever
projected as something else.

### 1.3 The replay rule

`replayEntry` on a `root` entry: check `before` against the store as it
stands (a mismatch refuses the journal by name, "root entry N: before does
not match", as any replay disagreement does; the offline tool keeps `before`
consistent when it splices); apply `after` verbatim with no judge, no
conformance check and no pin check (a `program` recompiles from the
journaled sources; a `pin` is set as stored). Derived indexes (`touched`,
`receipts`, `posts`, `grants`, `suspended`, `pending`) are rebuilt from the
new value as `record` rebuilds them.

**Ignore.** With `ignore N` journaled at height M > N, replay from genesis
applies entries 1..N−1, treats N as refused (its writes, creates, sends,
grants, offers and publishes not applied; its identity not bound), and runs
on. A later entry that re-judges against the changed store and no longer
holds (a root it read now at another version, a write to an object N
created) is not refused: it is **shadowed**, its effects skipped, and the
open report lists it (`world-status.shadowed: [{height, by, reason}]`,
`verify` prints them). Snapshots written before M are refused on open (the
store differs) and the chain is replayed; the next snapshot carries the
ignore. `unignore` restores N on the next replay. Ignoring a root entry is
allowed and shadows what it set.

**Edition.** Root entries, `shadowed` and the marker are replay-derived
facts: `replayEdition` 3, with MODERATION's rule in the same bump.

**Decision:** `before` checked, `after` verbatim, later entries shadowed
and reported, never silently re-judged; one edition bump for both layers.

### 1.4 The root socket

`serve` (FEDERATION 1) opens two sockets: the public one (`--socket`, default
`<dir>/state/host.sock`, mode 0600; it may live apart from the journals, so the
front mounts none) for the front, bridge, interpreter and the public verbs, and
`<dir>/root/root.sock` (mode 0660, group `--root-group`, so the hand runs under
its own uid in that group) for the root ops: `world-root`, `world-dump`,
`world-library`, `world-settings`, `world-fork`, `world-snapshot`. A root op on
the public socket is a request error, "the opener speaks on the root socket".
The opener's ordinary turns are the public socket's too (the bridge submits her
own posts as a resident's); there her privileges are not: amending another's
thing, revoking any grant, the powers, naming an owner (`World.resident`,
`openerActs`). Owner-only by filesystem:
`/data/root/` is a volume mounted into the hand's container
(`compose.hand.yml`) and `delvetalk-ops`, and into nothing else; on the box
it is reachable through the ssh forward to the hand's loopback listener and
through `docker compose run delvetalk-ops`. `serve` holds both sockets
(`Serve.lean`: the public one refuses the opener's ops by name).

**Decision:** the opener's authority is a socket, not a token; the socket is
a mount.

### 1.5 The offline tools

What cannot be journaled is done to a closed journal, writing a new file and
keeping the old:

    delvetalk-obend root-edit --journal J --out J2 --reason R <command>

| Command | Does |
| --- | --- |
| `truncate --height N` | keeps entries 1..N; snapshots past N are dropped |
| `drop --height N` | removes entry N and re-chains N+1.. |
| `rewrite --height N --entry FILE` | replaces entry N's body with FILE (any field, `before` and `after` of a root entry included) and re-chains |
| `splice --at N --entries FILE` | inserts entries after N and re-chains |
| `delete-world --name W` | removes `<dir>/W.journal` and its snapshots to `<dir>/deleted/W-<stamp>.journal`; `serve` stops serving it; references answer `foreignWorld` |

Re-chaining changes every CID from the edit onward: every slug after N
changes, `at://` citations of those entries stop resolving, and the
repository façade serves the new CIDs. The first re-chained entry carries
`rootEdit {command, reason, oldHead, at}` inside its hash, so a rewritten
journal says it was rewritten and from what. The tool prints the old-to-new
hash table and the count of slugs changed; `verify.sh` replays `J2` before
anything installs it. The sequence is DEPLOY's restore: `down`, `backup.sh`,
`root-edit`, `restore.sh` with `J2`, `up`.

**Decision:** five commands, a new file every time, the edit marked in the
chain, the slug cost printed.

### 1.6 The hand's root page and CLI

`/hand/root/` (and `hand root <verb>`), behind the same token, with a red
rule across the top and the reason box on every form:

- **The object editor**: `hand root dump OBJ` prints the object's record as
  JSON (state, law, program sources, pin, owner, read, version, fixed,
  supervisor, ledger, activities); the page shows each as an editable
  textarea; Save is `world-root set` for the fields that changed, one entry
  each. `hand root set OBJ FIELD --value-file F --reason R`.
- **The journal browser**: `hand root entries [--after N] [--object O]
  [--principal P]` pages `world-entries` raw; each entry has Ignore/Unignore
  (`hand root ignore N --reason R`) and Edit, which prints the `root-edit
  rewrite` command with the entry saved to a file, since an in-place edit
  is offline.
- **Act as**: a principal, an object, a method, an argument (JSON or a
  spell), an intent; `hand root as P OBJ METHOD --argument-file F --reason R`.
- **Delete, card, settings, library**: `hand root delete OBJ`, `hand root
  card OBJ --text-file F|--clear`, `hand root settings --clock N --post N
  --interpret N --model N`, `hand root library DIR`, each `--reason R`.
- **Shadowed**: the strip shows `world-status.shadowed` with a link to each.

Every verb logs to `hand-log.jsonl` as today (`who: cli|owner`, the entry's
height); the journal is the record.

**Decision:** a raw editor, a browser with ignore, an act-as field, and a
reason on all of them; no verb hides a root entry.

### 1.7 What root cannot do, because it is impossible

- Make a root entry look ordinary: `root: true` is inside the hash, and an
  unmarked state write that no method made fails replay's re-judge
  (`admitted` entries are re-judged; kind 3 without a law that admits it is
  refused). A forged ordinary entry breaks replay; a root entry replays.
- Recompute another's receipt hash to look original: any changed byte is a
  new CID; the old slug resolves to nothing; the façade serves the new
  record under a new name; the `rootEdit` marker names the old head.
- Un-reply: an entry a resident holds a slug for was fsynced before its
  reply. `truncate` can remove it, and then the resident's slug answers
  `unknown` and the chain says `rootEdit` at that height. That is the one
  root act a resident can detect from outside, and the marker is what they
  find.
- Un-send: a Delve or Zulip post, a model call, a reservation that left the
  box. `unpost` deletes and journals; the spend was spent.

**Decision:** root's only limits are hashes and the outside world; both are
named on the entry.

## 2. MODERATION

The layer the town sees: the opener's powers as judged, receipted turns,
offered first by the hand, with root one click further.

### 2.1 The metarule, widened

"No law can lock out the hand that wrote it." A law is accepted only if it
admits an amendment (kind 2) by its proposer and by the world's opener;
checked in `makeObject`'s dry run at creation, amendment and reprogram; the
refusal is "law does not admit an amendment by the opener <did>". The
default law gains `or (request.kind == 2 and request.subject == "<opener>")`
and `world-inspect`'s `laws` rows show it with its reading. In a scratch
world the resident is the opener. Root does not need this rule; the town
does, so that the opener's amendments are law and not root.

**Decision:** widen to the opener, say it on the laws page.

### 2.2 The powers

Each is a host spell the opener alone casts (`hostSpells` grows; a
non-opener is refused `badSpell`, clause `opener`), on the card it touches
or on `world`, the reserved id the host answers for; each journals one
entry under the opener's identity with a required reading, visible in
`world-history` and on the object page; hob's line within VOICE's 25 tokens.

| Problem | Power | Journaled as | hob |
| --- | --- | --- | --- |
| a resident floods a card | `delvetalk world quiet / who: <handle> / hours: N / reading: …`: their turns until `until` refused `quiet` (new transient class; `clause: until clock N`, `reason` the reading, `next`) | `quiets [{principal, until, reading}]` | `hob: the hand quieted you until clock N; the reason is on the receipt. Come back then.` |
| a law locks a thing | `amend / law:` or `adopt / law: <id>` as the opener (kind 2, under 2.1) | `amendments` | `hob: the hand amended that law; the clause is named on the receipt.` |
| a body burns the model on every instance; an interpretation loop | `retire / reading:`: an amendment appending `retired "reading": request.kind == 2 and request.subject == "<opener>"`, so writes refuse `refused retired: <reading>`, `?` lists nothing, `become / kind:` of it refuses; `unretire` amends it away; the world's `modelQuota` (OPERATIONS §b) holds the day | an amendment | `hob: that card is retired; the reason is on its page. The directory lists the doors.` |
| an abusive card text; a squatted name | `hide / reading:`: read policy `principals [owner, opener]`; the text leaves every page and draft, stays in the journal; the hiding entry is public; `show` reverses. Then retire. A name once taken stays taken; the doors are the opener's | `hides [{object, reading}]` | `hob: no public page for that now; its owner and the hand still see it.` |
| a scratch full of junk | `delvetalk world expire / scratch: <name> / reading:` (FEDERATION §3's sweep, now) | the hand's log only | `hob: that scratch is gone; open it again from town entry N.` |
| a model misread that admitted something | the write stands; the card's owner retracts its row; the opener sets `confirmFor` on `policy` so the action asks first | the policy's write | `hob: I read that as` then the spell, `yes, or correct it.` |
| a bridge posts the wrong thing | `hand skip` a draft; posted already: `hand unpost URI --reason` deletes the PDS record or Zulip message and journals `unposted {uri, reason}`; `hand reply` corrects, drafted `by hand` | `unposted` (clock principal, as `posted`) | `hob: the hand withdrew that post; its receipt stays.` |
| a grant the opener did not make | `delvetalk world revoke / grant: <id> / reading:` | `revokes [id]` with `by`, `reading` | `hob: that grant is revoked; the receipt says by whom.` |
| a quota wrong for a world | `delvetalk world settings / interpretQuota: 24 / reading:` (`world-settings`: a new `settings` entry; replay reads the latest) | `settings` | `hob: the hand set my hour to 24 readings; the spell itself needs no reading.` |
| a journal that will not reopen | no in-world power: a verified copy (DEPLOY), `world-fork` to a height into a fresh world, or root's `truncate`; `maxJournalBytes` is checked at open only (OPERATIONS §c) | `forked` | `hob: this town restarts from entry N; the old one still answers, read-only.` |

**Decision:** seven host spells (`quiet`, `retire`, `hide`/`show`,
`expire`, `revoke`, `settings`) and the host's `amend`/`adopt`; readings
required.

### 2.3 The hand's moderation verbs

`--world W` on every verb (default `town`); each a thin call over the root
socket under the opener, one page per power as a form:

| Verb | Op | Page |
| --- | --- | --- |
| `quiet WHO --hours N --reading R`, `unquiet WHO` | `world-turn` on `world`, `quiet` | PRINCIPALS: turns this hour, refusals, quieted-until |
| `retire OBJ --reading R`, `unretire OBJ` | `world-amend` | the object's row |
| `hide OBJ --reading R`, `show OBJ` | `world-turn` on `world`, `hide` | same row |
| `amend OBJ --law-file F --reading R`, `adopt OBJ --law ID` | `world-amend` | the law in a textarea beside its rows |
| `revoke GRANT --reading R` | `world-revoke` widened | GRANTS |
| `expire SCRATCH --reading R` | `world-scratch-expire` | SCRATCHES |
| `unpost URI --reason R` | transport delete, `world-unposted` | the inbox row |
| `settings --post N --interpret N --model N --reading R` | `world-settings` | the strip's quotas |
| `log [--tail N]` | `world-entries` filtered to the opener's and root entries | MODERATION, newest first, root entries stamped |
| `find TEXT` | the handle registry, `world-objects {prefix}`, `world-resolve` | one box |
| `status` | `world-status` plus `hour {turns, refused: {class: n}, interpretations, attempts}` (derived by `record`, nothing journaled) and `shadowed` | the strip |

The root page is one link from every object row and every log row ("root:
edit this object", "root: ignore this entry"), so the receipted power is
what the hand offers first and root is where it goes when that is not
enough.

**Decision:** moderation is the default face; root is one click further and
never the default.

## 3. The three to build first

1. **`world-root` with `set`, `delete`, `as`, `ignore` and `settings`, the
   entry shape, the replay rule with shadowing, and the root socket** (host;
   `replayEdition` 3). Unbounded first: the owner does not know what the
   mechanism will be needed for, and a journaled, marked, verbatim act is the
   whole of its honesty. `card`, `library` and the moderation shortcuts
   follow in the same lane.
2. **The hand's root page and CLI**: `dump`, `set`, `entries`, `ignore`, `as`,
   `delete`, the reason box; ~200 lines of Python over 1, under the ceiling
   (`hostd.py` and `hostproc.py` are gone). Tested by reading each entry back from
   `world-history` and by a replay of the test journal that reproduces the
   store.
3. **MODERATION's `quiet` and `retire` under the widened metarule, and
   `world-settings` with `hour`**: the layer the town sees, in the same
   edition bump as 1, so the town launches with both faces and one replay
   rule.

`root-edit` (1.5) is fourth: `truncate` is `head -n` plus `verify.sh` today,
and `splice`/`rewrite` need the re-chaining code, which is a day in Lean once
1 has landed the marker.

**Decision:** root first, its console second, the receipted layer third in
the same edition; the offline tool when the first splice is wanted.
