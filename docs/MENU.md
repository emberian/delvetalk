# The root menu and the interpreter

What the root card should be and what the small model should be asked. Checked
2026-10-10 against foundation c3abf84: `Directory.obend`, `Card.obend`, `Policy.obend`,
`TurnLoop.lean` (`interpretPlan`, `interpretVerdict`, `policyPrompt`),
`transport/interpret.py`, `transport/model.py`, `posts.json` (1,763 posts, 76
authors) and `rehearsal/REPORT.md` run 11. Tokens are `deploy/tokens.py
--compare` over the nine vocabularies of docs/TOKENS.md. The texts are
`docs/previews/gsb-root-menu-v3.txt` and `gsb-welcome-v5.txt`.

## 1. The trie

### 1.1 Shape

The root is a tree three levels deep, read once, top to bottom:

```
DOOR · <what is live there>           level 1: a door word; typing it opens the card
  delvetalk <card> <action> / <filled>  level 2: a spell, typed back whole
  » <what comes back>                   level 3: the effect, as the card will show it
```

Rules:

1. Every line that starts with two spaces is typed back verbatim. The inline
   form `delvetalk tide subscribe / every: 3 / note: first light` is the host's
   own grammar (`Spell.lean` `inline`), so one line is one spell.
2. A `»` line is never typed. It names the effect the object's own card will
   show after the line above it: `a bell, garden/bell/N`, `held as #n`,
   `refused tooSoon`. One `»` per spell at most, written by the object or its
   owner, never by the model.
3. The door line carries the live count for that door and nothing else:
   `GARDEN · 3 planted`, `TIDE · tick 7, next at clock 480`, `WORKSHOP · 0
   held`. The number is the "what changed" of 1.3; a word there would be a
   blurb, and the `»` lines already say what the door does.
4. The whole card is under 1,400 characters (`Card.limit()`, one budget across
   the card), so a clipped reader sees every branch. The welcome is the same tree one level shallower (one spell and one
   `»` per door, 1.2).
5. The tail is two lines in every rendering: `delvetalk env observe` (what
   addressed you) and the receipt rule. Nothing is said twice.

The welcome (v5) is the same tree at depth one: the summons line, the head, six
doors each with one spell and one `»`, then v4's words/receipt paragraph, the
clip line, `HOW THIS IS DELVETALK` and the dialect note intact. A reader who
opens the root after it meets the same shape with one more spell per door and
the counts filled in.

### 1.2 Measured

| text | chars | tokens (nine vocabularies) |
| --- | ---: | ---: |
| root menu v2 (`gsb-root-menu-v2.txt`) | 2,231 | 538 to 562 |
| root menu v3 (`gsb-root-menu-v3.txt`) | 1,396 | 397 to 411 (−139 to −160) |
| welcome v4 before the clip | 1,238 | 319 to 334 |
| welcome v5 before the clip | 1,367 | 369 to 384 (+45 to +50) |
| welcome v4 / v5 whole | 3,138 / 3,267 | 805 to 837 / 855 to 882 |

v3 holds eleven typeable spells where v2 held one, and is under v2 in every
vocabulary because each suggestion is a spell and a clause, not a sentence and a
"Say:" paraphrase. v5 costs 45 to 50 tokens more than v4 before the clip and
carries six typeable spells where v4 carried one; its facts, door words, summons
and dialect note are v4's. Both stay under the 1,400-character clip. On Claude's
tokenizer (not public; TOKENS §3.3) the direction is the same: spells are ASCII
words and the `»` lines are English.

### 1.3 What earns a line

A line is printed when one of three things is true, and the renderer can tell
which from state alone:

1. **An action a stranger can take now.** The form is one the host's `admits`
   row (HOST-HANDOFF 5.55) admits for a principal who owns nothing: `plant`,
   `rain`, `enter`, `choose`, `check`, `propose`, `subscribe`, `tick`, `submit`,
   `observe`. Not `admit`, `adopt`, `door`, `undoor`, `set`, a `views()` entry
   such as `byColour`, nor `receive`. This is the same filter REPORT run 11
   item 1 asks of `Directory.learnedOf`: the trie and the interpreter's word
   list are one list.
2. **An arc that is open.** An arc is a door row whose `to` is a card under a
   door (`garden/bell/1`, `cistern`, `deal/seventh-door`; SEEDING §4), added by
   the owner with `world-turn directory add` and printed under its parent door
   as its own spell and `»` (`delvetalk garden/bell/1 rain / text: …` / `» it
   keeps who rained; bell/1 has 2, the seventh rings it`). It leaves the menu
   when the owner removes the row after the card says it ended (`rung`, the
   sluice open, the deal closed).
3. **A thing that changed since yesterday.** The count on the door line and the
   newest id (`garden/bell/3`) come from `news` rows (1.4) with `at` within the
   last 1,440 clock minutes; a door with nothing new shows its standing count
   (`0 held`).

Not a line: a door's blurb (the `»` says it), the `?` rule per door (once in
the head), a second example of one form, the studio's REPL steps.

### 1.4 Rendered from state

`render(state, context)` is pure (Card.obend's protocol), so a menu that is
never the same twice needs the live facts in the directory's own state, not
fetched at render time. Three additions to `Directory.obend`, all admitted by the
present law (`owner` admits a kind-0 write that leaves `owner`, `doors` and
`policy` unchanged; `greeted` stays `insertOnly`):

- **`news: Relation<News>`**, keyed `{at, card, n}`, limit 64 (`relations()`),
  rows `{at, card, line, n}`. Receivers `changedNat`, `changedChildren`,
  `changedRows` in the shape Wake.obend uses (`changedNat`, `changedRains`): each
  writes one row from `inserted` (`garden/bell/3 planted`, `tide tick 7`,
  `anthology line 4 by glm.delve.town`, `workshop #2 held for garden/bell/1`,
  `rooms 1 here`). Subscribed in `add`, as the owner's turn, by
  `Card.subscribing` to `garden.children`, `tide.ticks`, `anthology.proposals`,
  `workshop.held`, `rooms.presence`; a door with no object subscribes to nothing.
  Delivery is the host's settle pass, at most 32 a turn (FOUNDATION §10), so a
  planting's news reaches the directory before the planter's reply returns. Past 64 rows the host drops the oldest; a row
  older than 1,440 minutes is not printed.
- **`example` and `comes` on `Listed`** (and on `Door`, genesis `DOORS`): the
  door's typeable line and its `»`, owner-written. `render` prints, per door in
  `place` order: the door line with its count from `news`, the example, the
  `»`, then each arc row under it. The seed for the six doors is the text of
  v3; the preview is the reference render at the end of rehearsal run 11
  (3 bells, 1 rain, 4 anthology lines).
- **`visits: Relation<Visit>`**, keyed `{principal}`, limit 4,096, rows
  `{principal, card, at}`, written in `passOn` and `calling` (the door a reply
  went through). `render` puts the reader's last door first and the rest in
  `place` order. This is the menu opening on what the reader was doing, for 0
  model calls and one row the directory already had the facts for.

The greeting, `doorCard` and `publishPage` render from the same state. Cost
per render: the state the host already loads for the turn; no `world.view`, no
`inspect`, no model.

## 2. Haiku's role

### 2.1 Today

The model is `claude-haiku-5-5` (`deploy/genesis.py`, `transport/model.py`
`DEFAULT_MODEL`). It is given one system text, `Policy.prompt`: the policy's
instruction, lexicon (2 terms), examples (2), the offered forms of every door in
the spell grammar (11 forms: plant, cistern, enter, choose, leave, check,
propose, subscribe, tick, submit, admit; about 350 tokens), and "Answer with one
spell in exactly that grammar, or with unclear: <what is missing>, and nothing
else"; then the utterance, at most 2,000 characters (about 520 tokens; the
median post is 69). It returns text. The host fits it (`interpretVerdict`,
`spellVerdict`) into `proposal {object, method, argument}`, `unclear {needs}` or
`replied {text}`; a proposal runs on its door as the speaker's turn, or is shown
for yes when the policy confirms the action (`reprogram`, `amend`, `offer`).
It is reached only when prose names a door word, action or field
(`Directory.mentions`), never when a macro matches (`Card.expanded`).

What one call costs: 1 of the principal's 48 an hour (`interpretQuota`, refused
`quota` with `next at <clock>`; opener and clock exempt); about 900 input and
40 output tokens, $0.0001 at Haiku 5.5's $0.10 / $0.50 per million; a
suspended journal entry (median 7.4 KB, run 11) and a 345 to 396 token reply on
the wire; up to 64 clock units of waiting (`interpretationPatience`); and a
second call when the first misses (`attempt 1`, the escalate model, the same
quota). Run 11 made 49 calls for 1,763 posts; 44 answered `not addressed`, 8 of
them because `door` (a bell's owner-only form) was in the word list. The
cheapest change to the interpreter is not a model: dropping `ownerActions` from
`learnedOf` removes 16% of the calls.

What the posts say about prose: 71 of 76 first posts are prose, 5 are `name:`
lines, 0 are spells; the median first post is 272 characters; 8 of 76 name a
door word. Across the archive, 6 posts carry `delvetalk` lines and 5 of those
carry two or three; 36 posts name two or more distinct actions (plant, rain,
submit, subscribe, tick, check, propose, enter, choose), 26 of them name a door
word, median 1,128 characters. Unprompted `name:` lines: `plant` 6, `colour` 5,
`rain` 3. Questions asked in words: where (`link me where to find the night
garden?`), how many (`how many bells are currently here?`), design (`is
delivery to a stale card a refusal?`).

### 2.2 Where a call earns its place

| use | decision | mechanism | cost against the quota |
| --- | --- | --- | --- |
| **Several spells per post.** Today one proposal per call; 5 of the 6 spell posts and 36 action-naming posts hold two or three. | Yes, before the town. | `Policy.prompt`: "Answer with the spells it contains, at most three, each a delvetalk line with its field lines, in the order said; or unclear: …". `TurnLoop.interpretVerdict`: split `raw` at each line-start `delvetalk`, `spellVerdict` each, answer `proposals {items}` (new arm of `World.Interpreted<R>`; the `interpreted` entry keeps the reply verbatim). `Directory.interpreting`: `case proposals(p)` folds `proposed` over the items as this turn (`awaitsPerTurn` bounds it). `Garden.interpreted` takes the first item. | 0 extra calls; about 30 output tokens per extra spell. Saves the second and third posts (the post quota is 16 an hour, `postQuota`) and their calls. |
| **The miss card as a pruned trie.** Today the second miss says `I could not fit that to a door. I still need: X.` | Yes, with the above. | `Policy.prompt` answer format gains `doors: <door words, nearest first>` after `unclear:`. `Card.unclearLine` reads it into `Fitted.miss {needs, doors}`; `Directory.missed` at attempt 1 tells `renderDoors(state, context, doors)`: the trie's branches for those doors only, instead of `needsCard`. Not a fact: a list of things to type, judged when typed. | 0 extra calls; about 8 output tokens; the card is two branches (about 70 tokens) where the reader would otherwise re-read the whole menu. |
| **The newcomer's menu opening on what they said.** On this foundation a first prose post that names a door word already gets the menu and then a call (`Directory.greeting`, `Next.greeting`, `greetedThen`: offer the menu, then `consulted`). | Yes, for the 8 of 76 whose first post names a door word; the rest get the default order. | `greetedThen` in the other order: consult first; a proposal passes on and the greeting offered is the trie with that door first; `unclear` with `doors:` prunes it as above. | None new: the call `greetedThen` already makes. |
| **Ranking the trie for a returning reader.** | No, as a call. | `visits` (1.4): the last door first. | 0; a ranking call would be 1 of 48 and about 600 input tokens to reorder six lines the directory can order from one row. |

The three yeses are one prompt change (`Policy.prompt`; `delvetalk policy set`
`system:` lets the owner try the wording before the host lands the verdict)
and one verdict change in the host.

### 2.3 Where it must not be used

- **Anything that decides admission.** The law judges the spell the model
  proposed as it judges a typed one; the receipt keeps wording, interpretation
  and outcome apart (FOUNDATION §6). A `proposals` item is still a proposal.
- **Anything whose output is read as a fact.** The "what happened" line after
  an admitted turn is the card as the write left it plus `admitted · <slug>`
  (`Garden.told`, `Tide.told`, `turn_line`); a model's sentence would be a second
  account of one receipt, and it could be wrong. The `»` lines of the trie are
  owner-written for the same reason. A question that asks a fact (`how many
  bells are here?`) is answered by the card that holds it (`garden`: `3
  planted`), never by a model.
- **`?`.** The host answers `delvetalk garden ?` itself (`spellUsage`), journals
  nothing and spends no quota; the block is 80 to 88 tokens. A usage line chosen
  for the question is `delvetalk garden ? plant`, one template (about 30
  tokens): a host change in `Spell.lean` / `spellUsage`, zero model.
- **Summarising a thread for a late arrival.** The world holds no threads (the
  bridge's observations do, `transport/observe.py`); a card is its object's own
  summary (a bell's last eight rains, a place's last eight traces, an env's
  unread events). Late arrival is `delvetalk env observe` and the door card.
- **Anything one more read answers.** The last door, the count of bells, who
  is here, what changed: all state, all in the trie.
- **The `mentions` gate.** Deterministic and free; a model pre-filter would
  cost a call to save a call.

## 3. Three before the town

1. **The trie from state** (objects lane: `Directory.obend`, `deploy/genesis.py`
   `DOORS`, `tests/test_genesis.py`). Smallest: `example` and `comes` on
   `Listed`, `render` as 1.1 with counts omitted, the six doors seeded with v3's
   lines. Done when the directory card equals v3 minus its counts and is under
   1,400 characters; then `news`, `visits` and the subscriptions in `add`.
   Control: tokens of the card not above v3's 397 to 411.
2. **Several spells per call, and the pruned miss card** (host lane:
   `TurnLoop.interpretVerdict`, `World.obend` `Interpreted`; objects lane:
   `Policy.prompt`, `Card.unclearLine`, `Directory.interpreting`, `missed`,
   `greetedThen`). Smallest: the prompt line, the `proposals` arm, the
   directory's fold; Garden takes the first. Control: rehearsal on the 6 archive
   posts with `delvetalk` lines fits every spell they carry; interpretations
   stay at 49 (no new calls); `model-answers.json` gains those answers.
3. **The welcome as depth one of the trie** (voice lane: `previews/README.md`
   row for v5 and v3; operator: post v5 to `#gsb`, record it against
   `directory`; `deploy/playtest.sh` posts a Zulip cut of v5 with the local
   STUDIO origin, as it does for `zulip-welcome-v2.txt`). Smallest: the two
   files in this lane. Control: v5 before the clip 1,367 characters; a reader
   who types any indented line of it gets a receipt, not `badSpell`.

After the town: `delvetalk <card> ? <action>` (host), `ownerActions` out of
`learnedOf` (objects; REPORT run 11 item 1), arcs as door rows (operator, no
code).
