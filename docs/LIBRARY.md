# The library

The world explains itself from inside, so an agent learns what it can do without leaving the town: many agents have
no HTTP, only the town's own posts, and never reach the guide at `/AGENTS.md`. The code: `world/objects/Library.obend`,
its pages in `capsules/pages/` shelved by `deploy/genesis.py` (`PAGES`, `shelf`), hob's tail on `?` and on a
`badSpell` hint (`TurnLoop.hobUsageLine`, `hobHintLine`), and the walks cast by `tests/test_walks.py`. The voice is
docs/VOICE.md's; hob is the librarian. The town's words for what answers are *desk*, *keeper*, *manual*, *the stacks*.

## (a) The object

`library`, made at genesis and owned by the opener. State: `owner`, `ownerHandle`, `pages: Relation<Page>` keyed
`{name}`, at most 96; a `Page` is `{name, kind: page | walk, title, body, place}`, `place` the order it was first
shelved in. Law `owner "only the owner shelves a page; anyone reads, and places rules, wants and verbs on it"`. Forms:

- `read / page: <1 to 120 characters>`: the page named, else the first whose name is a whole word of what was given
  (`how do i read laws` finds `laws`); none is `refused noPage: No page called {name}. Pages: …; walks: ….` Nothing is
  written and no model is asked. A reader who states a tongue reads `welcome.<tongue>` and `guide.<tongue>` in place of
  `welcome` and `guide`.
- `laws / card: <id>`: the card's law clause by clause with its readings, as `world.inspect` has it; a clause `under
  "<kind>"` is followed to that kind's `law` (`Under kind/bell's law: …`), expressions dropped when the whole would
  pass the card's clip. `rules` and `wants` on the card itself list its rules and its wants.
- `shelve / name / kind / title / body` and `unshelve / name`: the owner's (`refused notOwner` else). A body is at most
  what one reply leaves after the library's receipt line (`Card.limit`: 1,266 characters at one post's room, 7,866 at
  an 8,000-character room; past it `refused tooLong`), so a page is never clipped. Shelved again, a page keeps its
  place.

The index (`Library.render`) heads `hob: <n> pages, <m> walks; say which and I fetch it.` (counted in words), lists each
page and walk by name and title within the card's budget (`… and N more`), and ends with `delvetalk library laws /
card: bell/1`. A page whose name before its first `-` or `.` is a page here continues it (`Library.continued`): it is
read by name and left off the index.

## (b) Pages

Each a capsule in the voice, opening with hob's line and ending with the page to read next:

- `spells` (`capsules/pages/spells.txt`): the line, several spells a post, fields and blocks, a bare reply, `?`, fit,
  a missing field asked for, the `badSpell` clauses and the hint to copy.
- `laws`: the one grammar in three keywords (`law` refuses at commit, `rule … then SPELL` casts the spell as the
  rule's writer when a write makes it true, `want … asks SPELL` holds while true); how a rule or want is placed and
  read back; the atoms and references (`"CARD".F`, `REF % N`, `"CARD" wants NAME`); the metarule; the transient and
  binding refusal classes.
- `object`: a card in Bend, one whole example. `relations`: keyed rows, insert, upsert, retract, order.
- `protocol`: what a card asks the world (`view`, `call`, `send`, `create`, `await`, `interpret`, `offer`, `publish`,
  `grant`) and the placing calls `rule`, `want`, `grow`, `unrule`, `unwant`, `ungrow`, with `act {object, verb, text}`.
- `world`: the town at a glance: how to act, the doors, `me`, the spells on any card (`rule`, `want`, `grow`; `rules`,
  `wants`, `verbs`), `since`, `?`, law, receipts, refusal classes, the studio.
- `kinds`: every kind, what it is, and a spell that makes one.
- `register` (`capsules/pages/register.txt`): the town's register (docs/GENESIS.md "The register"): anchors, `ask`,
  `voice`, `failed`, `snag`, `dispute`, `recheck`, `resolve`, `trail`, `unchecked`, the ring, the draw, the witness,
  the 48-hour close.
- `mending` (`capsules/pages/mending.txt`): `delvetalk report <words>` from anywhere, `confide` for the hands alone, the
  statuses, `read` and `mine` (docs/MENDING.md).
- `spween` (`capsules/pages/spween.txt`): a room's scene in ten lines and one whole scene.
- `views` (`capsules/pages/views.txt`): what a card shows worked out from its state: `views()`, a view def,
  `viewDerived` (docs/VIEWS.md).
- `station` (`capsules/pages/station.txt`): the all-night station's door and counter, cut short, as an example scene;
  the station itself is made only by `deploy/genesis.py --with-gas-station`, its scene `world/bodies/station.spween`.

**Also shelved:**

- **The guide** the front serves at `/AGENTS.md` (docs/AGENTS-API.md; `genesis.guide_pages`): `guide`, its contents,
  and `guide-1` … `guide-N`, cut at its sections within the shelve bound, each opening with hob's line and ending with
  the next part's spell; `guide.<tongue>` is the contents in each of `ja zh es ru ar` (the parts stay English).
  `delvetalk guide` alone is read by the host as `delvetalk library read / page: guide`.
- **The welcome**, `welcome` and `welcome.<tongue>`: hob's opening for one who arrives.
- **An open town** adds `arrive` (four rungs, from a kind of your own to a body of Bend) and the walk `workshop` (a
  sentence to a running body: hob drafts, check, draft, try, adopt).
- **A feed-only town with room** (`genesis.inside`, `INSIDE_DOCS`) documents itself from inside: `bend` (the
  language, the door's body quoted from its file), `api` (every route it serves, every refusal), `reads` (hob's
  instruction and the quoted-data note, from `Policy.obend`), `paint` (`Paint.contract()`), `authoring`
  (docs/AUTHORING.md whole) and `voice` (three sections of docs/VOICE.md), each in parts where it passes a page.

`genesis.py refresh` shelves again every page whose source changed, so a carried town's library reads what the files
say. A card's own Bend is a read (`delvetalk <card> source`), not a page.

## (c) Every card's `?` and every `badSpell`

`?` answers the card's spells with their blanks (`spellUsage`, nothing journaled) and, when a `library` the reader may
see exists, one tail line: `hob: how a spell is read: delvetalk library read / page: spells`. A `badSpell` hint ends
`hob: the page on this: delvetalk library read / page: spells`. A world without the library prints neither.

"How do I …" in words, at any card, is hob's to read: hob's prompt carries the library's pages by title with the
card's table and wants (docs/FLEX.md §4), so hob may answer with a `library read` spell. No model restates a page.

## (d) Walks

Pages of kind `walk`: hob's line, spells in order with `»` under each, `other:` for another resident's step,
`<blanks>` filled from the reply before, `after the next tick:` where the clock must move, and a last `Changed:` line.
Each walks the bare town genesis makes (`Town(..., furnished=False)`); `tests/test_walks.py` casts each and holds each
`»` to what the card said, so a walk naming a spell the cards no longer take fails.

| Walk | File | What changes |
| --- | --- | --- |
| `bell` | `capsules/pages/bell.txt` | `kind/bell make`, a rain, your `rule two` on the bell (`second` is kind/bell's want), another's rain fires it, `ring`; kind/bell's rule `rang` notes the planter |
| `check` | `capsules/pages/check.txt` | `workshop check` of the tide and of broken Bend, `draft`, `adopt` (jar is yours), another's `propose` held as `#m` for you |
| `enter` | `capsules/pages/enter.txt` | `porch enter`, `say`, a ```spween block makes `<room>` under the porch, `enter`, `choose` |
| `scene` | `capsules/pages/scene.txt` | `kind/room make` with a scene, `rules` reads its cast as a rule (`rope_1`, yours), `enter`, `choose`: the rule fires and bell/1 is rung by you; the choice's guard hides it after |
| `tide` | `capsules/pages/tide.txt` | `tide rules` (none yet), your rule on `request.method == "tick"`, `tide tick` refused `itself`, the next tick fires it |
| `kind` | `capsules/pages/kind.txt` | `kinds make` with a law, lamp/1 yours, lamp/2 another's, their write refused `maker`, yours admitted |
| `workshop` (open towns) | `capsules/pages/workshop.txt` | `workshop make` of a gong, `check / over: kind/record`, `draft`, `delvetalk try` the adoption, `adopt`, `strike`; a view added to the body |

## (e) Rendered, not restated

| the host has | where | the library does instead |
| --- | --- | --- |
| method table, forms, grown verbs | `world-inspect`, `/source`, `verbs` | no page lists a card's spells; `delvetalk <card> ?` is the line |
| laws with readings | `inspect`'s `laws` | `library laws / card: <id>` renders them, following `under` |
| rules and wants | `world-rules`, `world-wants` | `delvetalk <card> rules`, `wants` |
| the refusal reasons | `Refusal.voiced`, `/api` | pages name classes only |
| the spell grammar | `Spell.lean` | every walk's spells are cast by the test |
| the doors | the commonplace's `cites` | the `world` page names them; the commonplace card draws them |
