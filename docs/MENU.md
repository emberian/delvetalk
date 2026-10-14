# The commonplace's card

What the town's first card prints and how it answers. The code: `world/bodies/commonplace.obend` (a body over
RECORD), `world/lib/Menu.obend` (the trie), `Card.Doorway` in `world/lib/Card.obend`, genesis `DOORS` and `STUDIO` in
`deploy/genesis.py`. The render is `docs/previews/commonplace-card.txt`, held equal to a bare genesis by
`tests/test_previews.py`. What hob reads there is docs/FLEX.md §4.

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
4. In order: the head (`Six doors. Indented lines are typed back whole; » is what comes back; words reach hob.`, the
   count in words), what wants a hand, what changed, the doors, the link doors, the tail.
5. The tail: `YOURS · me` with `delvetalk me since` (`» what others did to what you made since you were here; what you
   hold; your notes`), `READ · delvetalk chronicle · delvetalk map · delvetalk me book` (docs/VOICE.md "The book, the
   history, the map"), and the receipt rule. Nothing is said twice.

**One budget** across the card (`Card.left`, the receipt line under it counted): the head, the spells under what
changed and the tail are said whole; the doors get what those leave, and `Card.clippedWithin` drops whole branches from
the end, so a clipped reader sees every branch it is shown whole; what wants a hand gets what the doors leave; what
changed gets the rest (`… and N more` counted). A list that cannot show its first row is not shown. A link door
(STUDIO) is never clipped: it is said after the branches, before the tail.

### 1.2 The doors

The doors are the commonplace's `cites`, in the owner's order, as genesis lays them: KINDS (`kinds make`), PORCH
(`porch enter`: gemini's porch, three bells and three unclaimed things), WORKSHOP (`workshop make`: hob drafts the
Bend, held as `#n`), REGISTER (its word alone, so the wants keep their room), TIDE (`tide rules`: what happens at each
hourly tick), then STUDIO, a link door: `delvetalk try`, and the REPL at the town's `/AGENTS.md`. KINDS and WORKSHOP
come first because the card clips from the end. The owner adds and removes doors with `door / label / to` and
`undoor / label`; nothing else is kept to draw them. An arc is a door whose object lies under another door's object
(a door to `porch/goblet` beside PORCH): not a branch of its own, its spells print under its parent's.

### 1.3 What wants a hand, and what changed

`render` is pure, so the bare card prints only the spell that asks what changed: `delvetalk commonplace since / entry:
0`, and, where the world has the room, `delvetalk makings` (what residents made, to read and fork). That spell, and a
blank reply to the commonplace, answer the trie with `world.changed` read then: at most eight lines `<id> v<n> by
<handle>, entry N`, newest first (the commonplace's own change and every avatar left out), then `delvetalk kinds make
…` and `delvetalk <the newest id> ?`; with nothing changed, `Nothing has changed yet.`

What wants a hand leads the card: `world.wanting {after: 0, limit: 8, oldest: true}`, headed `What wants a hand,
turning daily:`, each row `<id>: <reading>` with its answering spell indented. Only asks this reader's hand is offered
are listed; `N more wait on other hands` counts the other visible held wants and takes no want slot. The oldest-first
page starts at clock day modulo the answerable count and wraps. A thing's own wants are on its card and
`delvetalk <card> wants`.

### 1.4 Its lines

The commonplace is a kept record: `write / text:` (1 to 280 characters) adds a numbered line, `[pending]` until its
keeper (the opener) admits or declines it; a resident's first line is admitted at once by the town's rule `firstline`
(`deploy/genesis.py` `FIRST_LINE`). The head of its lines says so.

## 2. Words at the commonplace

**A door's word** (the whole reply, at most 64 characters, equal to a door's label or its object's id) gets that
door's card (`world.card`); a link door's word gets its description; a door whose object is gone is refused `noCard`.
**Blank words** get the card over what changed (§1.3). **Anything else** the commonplace answers `silent`, and the host
reads it: field lines fitting an offered form run at once with no model; otherwise hob reads the words, offered
(`heardOffers`) the commonplace's own forms the speaker may use, then each door's card's forms and those of the first
three things under it, within `maxOffersBytes`. A spell naming another card never reaches the commonplace: the host
runs it there. A misfit spell is hob's to read past, as on any card (docs/FLEX.md §4).
