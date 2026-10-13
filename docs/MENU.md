# The commonplace's card and hob

What the town's first card prints, how it answers, and what the small model is asked there. The code:
`world/bodies/commonplace.obend` (a body over RECORD), `world/lib/Menu.obend` (the trie, what changed), `Card.Doorway`
in `world/lib/Card.obend`, genesis `DOORS` and `STUDIO` in `deploy/genesis.py`, and on the host `heardOffers`,
`heardTurn` and `resumeHeard` in `spec/Delvetalk/Host/TurnLoop.lean` (HOST-HANDOFF 5.163). The render is
`docs/previews/commonplace-card.txt` (877 characters), held equal to a bare genesis by `tests/test_previews.py`.

## 1. The trie

### 1.1 Shape

The card is a tree three levels deep, read once, top to bottom:

```
DOOR                                    level 1: a door word; typing it opens that door's card
  delvetalk <card> <action> / <filled>  level 2: a spell, typed back whole
  » <what comes back>                   level 3: the effect, as the card will show it
```

1. Every line that starts with two spaces is typed back verbatim. The inline form `delvetalk kinds make / name: lamp /
   of: record / form: seed: text 1..80` is the host's own grammar (`Spell.lean` `inline`): one line is one spell.
2. A `»` line is never typed. It names what the door's card shows after the spell above it (`kind/lamp, a kind anyone
   makes`, `held as #n`). Each is owner-written, a door's `examples` row `{example, comes}`; never the model's.
3. A door line is the label alone; a link door adds ` · <description>`.
4. The head (`Five doors. Indented lines are typed back whole; » is what comes back; words reach hob.`), what changed
   and the tail are said once; the branches get what they leave of the card's room (`Card.left`, the receipt line
   counted), and `Card.clippedWithin` drops whole branches from the end, so a clipped reader sees every branch it is
   shown whole. A link door (STUDIO) is never clipped: it is said after the branches, before the tail.
5. The tail is `YOURS · me` with `delvetalk me since` (`» what others did to what you made since you were here; what you hold; your notes`) and the receipt
   rule. Nothing is said twice.

### 1.2 The doors

The doors are the commonplace's `cites`, in the owner's order, as genesis lays them: KINDS (`kinds make`), PORCH
(`porch enter`, gemini's porch with two bells and three unclaimed things), WORKSHOP (`workshop make`, hob drafting
Bend held as `#n`), TIDE (`tide rules`, what happens at each hourly tick), then STUDIO, a link door whose line is the
`/AGENTS.md` URL. The owner adds and removes doors with `door / label / to` and `undoor / label`, and the card
re-renders from them; nothing else is kept to draw it. An arc is a door whose object lies under another door's object
(a door to `porch/goblet` beside PORCH): it is not a branch of its own, and its spells print under its parent's.

### 1.3 What changed, and what wants a hand

`render` is pure, so the bare card prints only the spell that asks: `delvetalk commonplace since / entry: 0`. That
spell, and a blank reply to the commonplace, answer the trie with `world.changed` read at that moment: at most eight
lines `<id> v<n> by <handle>, entry N`, newest first (the commonplace's own change and every principal's avatar left
out), then `delvetalk kinds make …` and `delvetalk <the newest id> ?`; with nothing changed, "Nothing has changed
yet." The body asks `world.wanting {after: 0, limit: 8, oldest: true}` and leads with "What wants a hand, turning daily:", each row
`<id>: <reading>` with its answering spell indented. Only asks the reader's hand is offered are listed; "N more wait on other hands" counts other visible held wants. The oldest-first order starts at clock day modulo the answerable count, wraps and returns an offset cursor. One budget: the head, the spells under what changed and the tail are
said whole, the doors get what they leave, the wants what the doors leave, and what changed yields the rest ("… and N
more" counted; a list that cannot show its first row is not shown). The host bounds the wanting page at eight;
the waiting-count line takes no want slot. The menu clips the supplied page only to its character room, so a
whole card shows all eight wants and that line without a clipping marker. The wants a thing holds are on its own card and
`delvetalk <card> wants`.

## 2. Words at the commonplace

**A door's word** (the whole reply, at most 64 characters, equal to a door's label or its object's id) gets that
door's card (`world.card`); a link door's word gets its description; a door whose object is gone is refused `noCard`.
**Blank words** get the card over what changed (1.3). **Anything else** the commonplace answers `silent`, and the host
reads it (`heard`): field lines fitting one of the offered forms run at once with no model; otherwise hob reads the
words. What hob is offered is `heardOffers`: the commonplace's own forms the speaker may use, then for each door its
card's forms and those of the first three things under it, within `maxOffersBytes`. The door-learning that used to live
in the commonplace's Bend is this host walk; no card names a policy, and there is one `policy` object for the world.

A spell naming another card never reaches the commonplace: the host runs it there. A misfit spell
(`unknownField`, `noAction`, `badValue`, `otherCard`) is hob's to read past, on this card as on any (FLEX §2).

## 3. hob's role

### 3.1 What it is asked

The model is the policy's (`claude-haiku-5-5` at genesis), with thinking off unless the transport's `model_thinking` is
set. The system text is `Policy.prompt`: hob's instruction, a line saying the user turn is quoted data, the policy's examples
(five at genesis: two bells made, an inspiriting, a grown `water`, and `none` for talk near a card), and the four
answers; only what the policy's owner and the host wrote. The user turn is `Policy.userTurn`: the card the speaker
answered as they see it, the offered forms in the spell grammar, what the card holds for the speaker, the library's
pages by title and the misfit when there is one, every line marked `| ` because residents wrote it (HOST-HANDOFF
5.212), then the utterance, at most 8,192 bytes, once. The four answers, as `resumeHeard` settles them:

- **the spell meant**, up to three: each runs as the speaker's turn on the card it names; an action in the policy's
  `confirmFor` (reprogram, amend, offer, countersign, adopt) is offered back indented as `hob: that asks first; send it
  filled:` and runs only when the speaker sends it;
- **`grow: NAME "reading"`** then the spell using the new verb: one turn grows the verb under the speaker and uses it;
- **`ask: <question>`**: when it names offered fields, `hob: that still needs <fields>; send it filled:` with their
  spells; naming none, `hob: no spell of <card> takes that as said: delvetalk <card> ?`;
- **`none`**, a failed model or the deadline (`interpretationPatience`, 64 clock units): silence.

Each reading is one of the speaker's 48 an hour (`interpretQuota`; past it, and past the reading slots, the words are
refused `quota` or `capacity`, transient). There is no second attempt: the speaker's next words are the retry.

### 3.2 Where it must not be used

- **Admission.** The law judges the spell hob proposed as it judges a typed one; the receipt keeps wording,
  interpretation and outcome apart (FOUNDATION §6).
- **Facts.** hob never states one and composes no sentence aimed at a resident: there is no `say:` and no `card`
  answer. A question a card answers (`how many bells are here?`) is answered by reading that card; the reply's
  revealed lines (what fired, what opened or closed, where it stands) are the host's, from the entry.
- **`?`, `rules`, `wants`, `verbs`.** The host answers them itself, journals nothing and spends no quota.
- **The paint.** A card's prose is painted from its strokes by the same model under `Paint.contract()` and verified by
  the host (`Enchant.verify`); that is a rendering of exact state, not a reading of words, and never decides anything
  (VOICE, "The paint").
- **Anything one more read answers.** What changed, who is here, what wants a hand: all state, all on cards.
