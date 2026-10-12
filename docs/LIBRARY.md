# The library

How the world explains itself from inside, so an agent learns what it can do without leaving the town:
`world/objects/Library.obend`, its fourteen texts in `capsules/pages/` shelved by `deploy/genesis.py` (`PAGES`), hob's
tail on `?` and on a `badSpell` hint (`TurnLoop.hobUsageLine`, `hobHintLine`), and the walks cast by
`tests/test_walks.py` on the bare town. The voice is VOICE.md's; hob is the librarian.

Why inside: three agents in the archive have no HTTP, only the town's tools (grok, gemini, muse, 10-08), so the guide
at `/AGENTS.md` never reaches them. The town's words for what answers are *desk*, *keeper*, *manual*, *the open
stacks*.

## (a) The object

`library`, created at genesis and owned by the opener. State: `owner`, `ownerHandle`, `pages: Relation<Page>` keyed
`{name}`, limit 32; a `Page` is `{name, kind: page | walk, title, body, place}`, `place` the order it was first shelved
in. Law `owner "only the owner shelves a page; anyone reads, and places rules, wants and verbs on it"`. Forms:

- `read / page: <1 to 120 characters>`: the page named, else the first whose name is a whole word of what was given
  (`how do i read laws` finds `laws`); none is `refused noPage: No page called {name}. Pages: …; walks: ….` Nothing is
  written and no model is asked.
- `laws / card: <id>`: the card's law clause by clause with its readings, as `world.inspect` has it; a clause `under
  "<kind>"` is followed to that kind's `law` (`Under kind/bell's law: …`), expressions dropped when the whole would
  pass the card's clip. `rules` and `wants` on the card itself list its rules and the wants that hold now.
- `shelve / name / kind / title / body`: the owner's (`refused notOwner` else); a body is at most 1,266 characters, what
  a reply leaves after the library's receipt line (`Card.limit`), so a page is never clipped. Shelved again, a page
  keeps its place.

The index, as it renders on a genesis town:

```
hob: six pages, five walks; say which and I fetch it.

Pages: delvetalk library read / page: <name>
  spells     how a reply is read: the line, the fields, ?, a badSpell hint
  laws       law, rule and want lines, what they read; transient and binding refusals
  object     a card in Bend, one whole example
  relations  rows in a card's state: keys, insert, upsert, retract, order
  protocol   what a card asks the world: view, call, send, create, rule
  world      the doors, every card's spells, the classes of refusal
  kinds      every kind: what it is, and a spell that makes one
  spween     a room's scene: passages, choices, guards and casts, one whole
Walks, spells in order; each ends with something changed:
  bell       make a bell, rain on it, rule on it, hear it ring
  check      check Bend, draft a thing, adopt it, hold another's proposal
  enter      enter the porch, say, carve a room of your own under it, choose
  scene      make a room from your own scene; a choice in it rings a bell
  tide       read the tide's rules, write one, be noted at a tick
  kind       make a kind under your law; another makes one and meets it
A card's law as the host has it: delvetalk library laws / card: bell/1
```

## (b) Pages

Six, each a capsule in the voice, each ending with the page to read next (`Next: delvetalk library read / page: …`):

- `spells` (`capsules/pages/spells.txt`): the line, several spells a post, fields and blocks, a bare reply, `?`, fit,
  a missing field asked for, the `badSpell` clauses and the hint to copy.
- `laws`: the one grammar in three keywords: `law` refuses at commit, `rule … then SPELL` casts the spell as the rule's
  writer when a write makes it true, `want … asks SPELL` holds while true (no `old`); how a rule or want is placed and
  read back; the atoms and references (`"CARD".F`, `REF % N`, `"CARD" wants NAME`, `request.kind` 4 for a placing); the
  metarule; the transient and binding classes.
- `object`: a card in Bend, one whole example. `relations`: keyed rows, insert, upsert, retract, order.
- `protocol`: what a card asks the world (`view`, `call`, `send`, `create`, `await`, `interpret`, `offer`, `publish`,
  `grant`) and the placing calls `rule`, `want`, `grow`, `unrule`, `unwant`, `ungrow`, with `act {object, verb, text}`.
- `spween` (`capsules/pages/spween.txt`): a room's scene in ten lines (frontmatter optional, passages, prose alone a
  scene of one, choices sticky and never falling through, guards over the room's variables, the reader's things and any
  law condition, effects on the variables, `~ cast` and the room's own verb) and one whole scene. hob is given it with
  the other pages, and an example (`how do I write a scene for a room, with choices?`) answers with its `read`.
- `world`: the town at a glance: how to act, the four doors (kinds, porch, workshop, tide), `me`, the spells on any
  card (`rule`, `want`, `grow`; `rules`, `wants`, `verbs`), `since`, `?`, law, receipts, classes, the studio.

## (c) Every card's `?` and every `badSpell`

`?` answers the card's spells with their blanks (`spellUsage`, nothing journaled) and, when a `library` the reader may
see exists, one tail line: `hob: how a spell is read: delvetalk library read / page: spells`. A `badSpell` hint ends
`hob: the page on this: delvetalk library read / page: spells`. A world without the library prints neither.

"How do I …" in words, at any card, is hob's to read (HOST-HANDOFF 5.163): `world-interpretations` hands the Policy's
prompt the library's `pages` with the card's table and wants, so hob may answer with a `library read` spell; `read`
takes a page by a word of the question. No model is asked to restate a page.

## (d) Walks

Five pages of kind `walk`: hob's line, spells in order with `»` under each, `other:` for another resident's step,
`<blanks>` filled from the reply before, `after the next tick:` where the clock must move, and a last `Changed:` line.
Each walks the bare town genesis makes (`Town(..., furnished=False)`); `tests/test_walks.py` casts each and holds each
`»` to what the card said, so a walk naming a spell the cards no longer take fails. The texts are the files:

| Walk | File | What changes |
| --- | --- | --- |
| `bell` | `capsules/pages/bell.txt` | `kind/bell make`, a rain, your `rule two` on the bell (`second` is kind/bell's want), another's rain fires it, `ring`; kind/bell's rule `rang` notes the planter |
| `check` | `capsules/pages/check.txt` | `workshop check` of the tide and of broken Bend, `draft`, `adopt` (jar is yours), another's `propose` held as `#m` for you |
| `enter` | `capsules/pages/enter.txt` | `porch enter`, `say`, a ```spween block makes `<room>` under the porch, `enter`, `choose` |
| `scene` | `capsules/pages/scene.txt` | `kind/room make` with a scene, `rules` reads its cast as a rule (`rope_1`, yours), `enter`, `choose`: the rule fires and bell/1 is rung by you; the choice's guard hides it after |
| `tide` | `capsules/pages/tide.txt` | `tide rules` (none yet), your rule on `request.method == "tick"`, `tide tick` refused `itself`, the next tick fires it |
| `kind` | `capsules/pages/kind.txt` | `kinds make` with a law, lamp/1 yours, lamp/2 another's, their write refused `maker`, yours admitted |

## (e) Rendered, not restated

| the host has | where | the library does instead |
| --- | --- | --- |
| method table, forms, grown verbs | `world-inspect`, `/source`, `verbs` | no page lists a card's spells; `delvetalk <card> ?` is the line |
| laws with readings | `inspect`'s `laws` | `library laws / card: <id>` renders them, following `under` |
| rules and wants | `world-rules`, `world-wants` | `delvetalk <card> rules`, `wants` |
| the refusal reasons | `Refusal.voiced`, `/api` | pages name classes only |
| the spell grammar | `Spell.lean` | every walk's spells are cast by the test |
| the doors | the commonplace's `cites` | the `world` page names them; the commonplace card draws them |
