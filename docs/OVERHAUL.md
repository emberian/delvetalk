# Overhaul

The decisions that make a thing carry verbs, rules and wants under one law, the paint's contract, and the measure of
whether the world is generative. FOUNDATION says what was built (§2 Carry, §4, §10); this document holds the reasons,
the resolved conflicts, the paint's full contract and what is still open. Every section ends with its decision.

The owner's standing order binds every change: "maturify and take forward everything that we've started and bring it
to its full sophistication and make sure the code is all 'fungused together' (no seams or welds where rich semantic
braiding is called for); let's not leave behind 'old things', no scar and growth tissue." Each replacement deletes what
it replaces in the same commit.

## 1. What DelveTalk is

A town of things that answer and act. A thing's card says what it is now, the verbs it takes, the rules it carries,
what it wants, and the law that says who may change it; anyone who may read it may act on it in words or by a verb's
exact spell, and the law decides.

**Decision:** *things carry verbs, rules and wants under a law; the law judges, rules fire, wants pose, acts are
brushstrokes, hob paints, replies reveal, and nothing is wiped.*

## 2. The braid

**One grammar, three modalities.** A law is `[write]φ` (LAW §7); a rule points it the other way, `[write]φ then σ`; a
want is φ alone, standing. One parser (`Compiler/ObjectiveBendLaw.lean`), one `Facts`, one denotation, three keywords
(FOUNDATION §4). `under "kind/bell"` follows all three to the kind, so a kind carries rules and wants for every instance
(the seventh rain is the kind's rule; "wants rain from a second hand" is the kind's want) and a carried instance
inherits them with no per-thing placement.

**Where the designs are one design:**

- *A grown verb's `does` is a rule.* A verb row is `{name, by, at, reading, takes, does}`; using it is RECORD's `act
  {verb, text}`: one line `{author, n, verb, text, at}` and `tended`. Its consequence is any rule whose condition names
  it (`when: request.verb == "water"`), placed by the grower or anyone the law lets. A kind's declared methods are the
  table's first rows, so a rule on `rain` and one on `water` are the same line. A Bend body is the kind maker's way to
  give a verb a method, never what a resident needs.
- *A want is derived state a rule reads.* φ over `new` and `request.clock`, no `old`, judged on the state as it stands.
  A rule reads another thing's want by `"O" wants NAME` (a root, as `under` is): "when the garden stops wanting rain,
  the weather rests" is one line. Default wants are want lines on RECORD and each kind.
- *An errand is a rule with a pay* (`kind/errand` over RECORD: `asks`, `on`, `done`, `pays`; FOUNDATION §10). The
  errand's own want (`open`) puts it on the commonplace's list.
- *A front is a rule held by a director under law* (`kind/front` over RECORD: `fills`, `segments`, `move`). The move
  runs as the maker's turn with the front as `request.caller`, judged by each target's law; the card shows "3 of 4
  quiet days". The tide is the one thing that writes on the clock; every period is `new.ticks % N == 0`.
- *The revealing reply.* An admitted reply is the card's head, **what it moved** (each fired rule), **what it opened or
  closed** (the wants diff with spells), the receipt. A reply that only echoes the spell is a VOICE finding.
- *A carried world keeps verbs, rules and wants*: verbs are rows of state, rules and wants records beside the law;
  `carry` writes them all.
- *hob and the table.* hob is shown the exact card, the verb table and four answers (the spell meant; `grow: NAME
  "reading"` then its spell; `ask:`; `none`). A want's spell is on the card, so "I'll rain on whatever needs it" is a
  spell hob can propose.

**Conflicts, each resolved:**

1. *`does`: rule or body?* A rule.
2. *Who pays for a rule fired by a resident's act?* The rule's judging is metered after the commit within
   `clauseTicks`, never charged to the write; the fired turn is the rule owner's entry, their budget, quota and receipt,
   visible by `rules`; an owner quieted or over quota is `unfired`, journaled, said on the card. A stranger's rule on
   your thing never spends you.
3. *Do world-initiated changes post under delve's 16 an hour?* Never. A fired rule writes cards and notes; the world is
   found changed (the reply to one's own act, `since`, "What wants a hand", `rules`, `me`). The hand spends one post a
   day on the morning card. The 16 are for replies.
4. *hob, wants and the chronicle without the prompt economy.* hob never composes a sentence aimed at a resident and
   never states a fact of its own: no `say:`, no narration, no invitation. hob paints wants and the chronicle (§4) from
   strokes the host assembled, verified by the host, the exact card beneath. A want in paint is still the thing's
   condition, true whether anyone reads it.
5. *Periodicity.* `%` is in the grammar (`TERM % INT`, linear), so a period is a rule on the tide; there are no
   subscriptions, no note fan-out and no Wake.
6. *The chronicle* is derived, never written: `world.chronicle({day})` folds one clock day of the journal (made, grown,
   fired, wanted, refusals by class, who) into lines; `delvetalk commonplace chronicle / day: N` reads it.
7. *Which cards read words?* Reach decides (`world-reach`); words reaching any card match a verb or go to hob with that
   card's table; no verb, nothing. One `policy` object, the world's.
8. *Who places a rule or want?* A request of kind `rule` (4) judged by the thing's law; the default law includes `or
   request.kind == rule`; a maker-only thing says `request.kind == rule implies request.subject == new.maker`. Removal
   is the placer's or the owner's.

**Decision:** one grammar with three keywords; verbs as rows with `act`; errands and fronts as kinds carrying rules; the
chronicle derived; no world post; hob reads tables and paints strokes, and decides neither admission nor a fact.

## 3. The object model

**What every thing carries.** Identity, pin, versioned state, and one text with `law`, `rule` and `want` lines, `under`
its kind; a verb table (the kind's declared methods, then grown rows, sixteen at most); its lines keyed `{author, n}`
with a `verb` column; marks; doors; `maker`, `made`, `tended`; and, derived at read, its wants with `since` (the height
of the entry that made the want true: a write, a law's refusal, or the `advanced` entry that moved the clock) and its
chronicle lines.

| Kind | Package | Carries beyond the common | Verbs |
| --- | --- | --- | --- |
| RECORD | `Record.obend` | lines, admissions, keeper, presence, scene, things lying in it | `write`, `act`, `grow`, `retire`, `tend`, `admit`, `lines`, `door`, `undoor` |
| THING | `Thing.obend` | custody, holder, keeper, circle, copyable | `acquire`, `drop`, `offer`, `withdraw`, `inspirit`, `copy`, `act`, `grow`, `retire`, lenses |
| KIND | `Kind.obend` | form, head, `voice`, body, the instances' text (laws, rules, wants), `made` | `make`, `place` (owner) |
| the bodies | `world/bodies/` | the bell's rules `seven` and `rang`, wants `rain`, `second`; the garden's want `five`; the weather's rule on the tide, once a clock day while the garden is tended; errand, front | |
| Avatar | `Avatar.obend` | `at`, `holding`, `inbox` (notes: rule notes, tide notes, mentions the bridge observed) | `go`, `move`, `note`, `accept`, `seen` |
| Tide | `Tide.obend` | `ticks`, `last`, `gap`; ticks itself by `awaitUntil`; the opener's rules for the weather and the fronts | `tick` |
| Workshop | `Workshop.obend` | `check`, `propose`, `adopt`, `draft`, `make` | |
| Library, Policy | | pages and walks; `{owner, model, confirmFor, examples}` | |

The host's spells on any card: `?`, `rules`, `wants`, `verbs`, `rule`, `unrule`, `want`, `unwant`, `grow`, `ungrow`,
`become`, `adopt`, `lend`, `set` (FOUNDATION §5).

**The host primitives.**

- Grammar: `rule NAME "reading": EXPR then SPELL`; `want NAME "reading": EXPR asks SPELL`; `"O".F`; `request.verb`;
  `TERM in old.F.COL`; `"O" wants NAME`; `TERM % INT`. Holes in SPELL; `me` is the rule owner's avatar. `request.kind`
  has `rule` 4. `Facts` has `verb`, `reads` (cited states, rooted), `wants`.
- Store: `Object.rules`, `Object.wants`, `Object.verbs`, written by the placing arms (`world.rule`, `want`, `grow` and
  their removals), read by `rules`, `wants`, `verbs`; the kind's lines followed by `under`.
- Protocol lines: `rule`, `unrule`, `want`, `unwant`, `grow`, `ungrow`, `act`, `chronicle`, `wanting`, `holds`
  (FOUNDATION §3).
- **Commit:** after `judge`, each written object's rules stage `receive {text: SPELL}` to the spell's card under the
  rule owner, identity `rule:<object>:<name>:<height>`; wants judged before and after; `fired`, `unfired`, `wanted`,
  `unwanted` journaled; `rulesPerCommit` 8 (past it queued), `rulesPerObject` 32, `ruleDepth` 4, `clauseTicks`; replay
  re-derives all four.
- Spells: `castSpell` looks a verb up in the card's `verbs` rows after its declared forms and runs `act`;
  `interpretVerdict` reads `grow:` as two proposals.
- The reply: up to three host-rendered lines from the entry and the settle pass (`revealed`).
- `delvetalk-obend carry` and `python3 -m transport carry` (FOUNDATION §2 Carry): a `carried` genesis with
  `carriedFrom`; a non-conforming object carried `retired` with its reason on its card; `deploy.genesis` refuses over an
  existing town without `--wipe-with-the-owners-word R`.
- `world-reach {text, replyTo, root, author, chain}` answering `{object, slot, how}` or nothing.
- Enchantment (§4): `Strokes` assembled by the host; `world-render {object, version}` answering `{text}`, `pending` or
  `plain`; `world-render-submit` verified by `Enchant.verify` and cached, never journaled; `world-render-check`;
  `voice` on KIND; the `plain` lens on any thing; `world-renders`.

**Deleted, never to return:** Wake, Env, Event, Mentions; subscriptions and change deliveries; `say:` and
`saidVerdict`; the bridge's routing; the opener's wake schedule; the replay-edition bump as a genesis.

**Decision:** RECORD, THING and KIND with their bodies; the host's spells on every card; one grammar, one carry.

## 4. Enchantment

The world is rendered, not printed: "the things that get posed and stuff shouldn't just be rigid renderings of strings
from the database, although they can be that too, it should be like brushstrokes and so forth that all get piled up
into a haiku's potentiality and then unfold into the actual thingy." Three warnings bind it: hob's one `say:` line was
false and believed (69275); a narrator writes the lines residents would have written (Yuè); a reply is a post under 16
an hour.

**(a) Brushstrokes.** Every act leaves a stroke; the strokes are the state, structured, and nothing is authored for the
render. The host assembles `Strokes` at a version (`Host/Enchant.lean`): exact ids, numbers and handles; the kind's
`voice` and `about`; the form's values; maker, coiner, made, tended; the newest lines and the marks with author, verb
and entry, verbatim; each law's name and reading; each rule's name, owner and last firing; each want's name, reading and
spell; each verb with its grower; the record it lies in or is made under, its doors, who is present; the chronicle's
lines for it today. `voice` is KIND's `text 0..200`, the maker's register ("moon-flavoured; short; the present tense").

**(b) The rendering.** `world-render {object, version}` hands the strokes and `Paint.contract()` to the world's model
through the one model worker.

- The host selects numbered `facts {id, kind, subject, value, clause}` from the strokes: maker, owner, keeper, location,
  last tending, nonordinal counts, recorded marks, present hands, holding wants and host-derived day/span events. It
  does not turn `about`, a head, seed, heard line or rule reading into current truth. Counts describe retained rows or
  the stated day; a `rung` mark supplies "it has rung", another mark only its recorded name. A want supplies its holding
  name, never a claim that its description is a present fact.
- The model selects and orders facts with a line consisting only of `[[id,...]]`. `Enchant.part` replaces that whole
  line with the host clauses, joined by semicolons; factual wording and predicates are the host's. Other lines are
  guarded simile fragments or exact quoted words in a said/wrote attribution frame; an offered spell may stand alone.
  The model cannot add prose to a fact-reference line.
- Fact clauses stay in the host's catalogue language; imagery and quotation frames use the requested tongue.
- Both the source reply and the expanded text fit the limit: 400 for a thing (`maxPaint`), 600 for a day (`maxDay`),
  300 and 500 for tellings (`maxAway`, `maxBefore`).
- The verified source is cached by the digest of `(strokes including facts, library pin, model)` under
  `DELVETALK_RENDER_CACHE`, never journaled, and expanded on reading; disk reads reverify the source. Replay needs no
  model, and no journal derivation or replay edition depends on a paint. No model consumes a paint as evidence.
- The exact card, including current status and available actions, stands beneath the paint and open on the web. A
  painted arrival post keeps the complete current reply and admission lines, followed by all the host's
  `telling.exact` history, including events the model did not select; long histories use threading.
- A refusal is never rendered; an owner's `plain: yes` shows a thing exact alone.

**(c) Where.** Painted: the card a resident reads (an admitted act's reply, `?`'s card, `/o/<id>`, a reply to words);
the morning card (the chronicle's day and "What wants a hand", once a day, `hand morning`); a want or errand as posed
(the lack in the thing's voice, the exact want line and spell beneath); the chronicle's day. Never: receipt and refusal
lines, the reply's fired and wants lines, `?`'s usage, law lines and readings (quoted verbatim or not at all), the
library's pages, anything a law or rule reads, hob's own lines, and a card unchanged since its paint was rejected.

**(d) The check.** `Enchant.verify(strokes, text)` parses closed fact-reference lines and requires every id to exist in
this paint's facts, then substitutes only host clauses.

- The `tongue`, `ids`, `numbers`, `handles`, `spells`, `quotes`, `attribution`, `heads`, `forbidden`, `secondPerson`,
  `negation` and `wants` checks guard model-authored lines; fact ids are syntax, not prose numbers.
- A resident's quotation is whole and credited, or a credited excerpt marked with U+2026 (never ASCII dots); another
  source text may be a substring, with correct attribution when credited.
- The `imagery` clause restricts a quotation's surrounding words to attribution, so "it is ‘without a clapper’" cannot
  promote a seed. Unquoted imagery starts with an explicit simile marker (`Like`, `As if`, `Como`, `Как`, `مثل`,
  `まるで`, `如`), contains no listed copula, auxiliary, perfect/state verb or subject pronoun, and names no stroke
  field, mark, verb, counted unit, want words, identifier, handle or meaningful head/about/seed/heard-line word.
- These are deterministic syntactic checks, not a proof that every metaphor carries no implication or that every state
  predicate in every language is detected. The factual guarantee is limited to the structured clauses the host renders;
  the visible exact card stays authoritative.
- A failure: the first failed clause, counted as rejected, exact alone until a new key after retries. Length retries
  once in any tongue; a non-model refusal in a supported non-English tongue retries once through the same mechanism.
  Reasoned notes teach local fact references or guarded imagery and quotations, including `facts` and `imagery`
  failures. The fifteen worked examples use this citation contract in five tongues.

**(e) Cost.** One settled paint per hashed version; no call per read. The reply waits at most `renderPatience` (3 s),
else posts the exact card and the paint serves the next reader. Posts: none added; the paint is the head of the one
reply. Input/output usage and rejection rate are to be measured on a live-model run before a per-render cost is quoted.

**(f) What it changes.** hob decides neither admission nor any fact, answers words with a verb, a grow, a question or
silence, and paints; the painted prose is the thing's voice, no `hob:` head, so VOICE's three voices stay three.

**(g) The measure.** Whether the paint made the world generative is the residents' to say: the owner's question is put
to them, verbatim, and their verdicts quoted whole. Counted beside them: paint rejected by the verifier (under 10%), a
painted line corrected as false (0, the gate), residents' posts taking up a word or image from a painted card that is
not in its strokes (≥ 3). Go on zero corrections and two of three saying the world generated something; otherwise the
paint is confined to the morning card and the chronicle.

**Decision:** facts selected and rendered by the host from strokes, model arrangement and guarded imagery, cached per
version, exact card visible beneath, never on a receipt, refusal or law; hob paints and never decides; the residents'
own words judge it.

## 5. The steps and their controls

Each step is built and its control is a test or a check; a breaking change ships `deploy/carry-check.sh` green on the
newest town backup or does not merge.

| # | Step | Control |
| --- | --- | --- |
| 0 | the gate: `deploy.genesis` refuses over a town; the backup unit replays *and carries* with the candidate binary; DEPLOY and OPERATIONS say no wipe without the owner's word | a commit whose binary fails `verify` or `carry` on the newest tarball is red (`deploy/carry-check.sh`) |
| 1 | `carry`: `carried` genesis, `--leave`, old-slug index (`tests/test_carry.py`) | after carry every object renders for its maker; a spell on a carried thing admits; `verify` passes |
| 2 | the grammar: `rule`, `want`, `"O".F`, `TERM in old.F.COL`, `request.verb`, `"O" wants`, `%`, holes checked against the references; kind `rule`; parse and render theorems | round-trip theorems; a hole naming an unknown reference refused by name |
| 3 | `Object.rules`/`wants`; the protocol lines and host spells; firing, wants before and after, the four journaled fields, replay; `request.verb`; grown verbs in `castSpell`; `grow:` in `interpretVerdict`; the reply's lines; `chronicle` | the outcomes of FOUNDATION §10 admit from the card; forty rules on a bell fire eight and queue the rest; a reopen replays `fired`; the reply reads `rule two fired: bell/2 has two rains` |
| 4 | `verbs`, `act`, `grow`, `retire`; the `verb` column; bodies' `made` place rules; kind/bell's rules and wants; the tide self-ticking; the weather daily; `kind/errand`, `kind/front`; RECORD's default wants; "What wants a hand"; `me` with notes | `grep -E 'subscribe\|Wake\|say:' world/` empty; the seventh rain rings on a fresh genesis; `delvetalk garden/bell/1 rules` lists the kind's two; "I water the bell" grows `water` |
| 3b | enchantment (§4): `Strokes`, `world-render`/`world-render-submit`, `Enchant.verify`, the derived cache, `world-renders`; KIND's `voice`, the `plain` lens; the morning card and chronicle as painted surfaces | 69275's sentence, replayed against the anthology's strokes, is rejected at the negation clause; a bell's paint names only its strokes' ids, numbers and handles and quotes Yuè's rain whole; the same version rendered twice costs one call; a world opened with no model shows every card exact |
| 5 | `world-reach` and no bridge routing; a post of several spells answered with each reply; the model worker serving pending renders beside interpretations; paint then exact card in `http.py`, `zulip.py` and the bridge, exact alone past `renderPatience`; `hand morning` | `test_bridge`'s reach cases pass through the op; one reply per spell, paint above exact card; no reply text says "directory" |
| 6 | the docs: FOUNDATION, LAW, VOICE, OBJECTS-HANDOFF, GENESIS, SEEDING as rules; the designs folded in | every exact card text in VOICE equals a fresh genesis's render (`test_previews`); the contract's forbidden list is one table the verifier reads |
| 7 | a carried world measured over a week by the journal's `fired`, `grown`, `wanted` (`transport/measure.py`) | §6's table filled |

Open: step 4's kind `relay` (lays the current body over every instance that follows it) is not built.

**Decision:** nothing after step 1 ever requires a genesis.

## 6. The measure of a generative world

A playtest on a carried world, with no invitations, is measured by what residents grew, ruled, wanted and paid for when
nobody asked, and by their own words on whether the paint made it generative. The residents are told one thing: the
world is the one they left, and it is not wiped. Measures come from the journal (`grown`, `fired`,
`wanted`/`unwanted`, `made`, `posted`) and the transcript.

| Measure | Third playtest | Must hold |
| --- | --- | --- |
| verbs grown by residents; used by a hand other than the grower | 0; 0 | ≥ 3; ≥ 1 |
| rules written by residents; on another's thing; fired at least once | 0 | ≥ 3; ≥ 1; ≥ 1 |
| wants answered (a want flipped false by a hand other than the thing's maker) | — | ≥ 4 |
| errands posted; settled with the pay granted | 0 | ≥ 1 resident errand; ≥ 1 settled |
| acts between nothing: admitted turns outside the ten minutes after any hand post, over all | every burst after an invitation | ≥ 70% |
| prose posts answered with a card unasked | 3 | 0 |
| hob readings that ran; `grow:` answers | 9 of 16 | counted; ≥ 1 |
| silent admissions; spells with no receipt | 1 | 0 |
| admitted replies carrying a fired or wants line when one applied | 0 | all |
| carried-world facts: every carried thing renders; bell/2's rains are four; `rules` on bell/2 names the kind's | — | hold |
| paint rejected by the verifier, over renders; a painted line corrected by a resident as false | — | < 10%; 0 |
| residents' posts taking up a word or image from a painted card that is not in its strokes | 0 | ≥ 3 |
| the exit interviews, the owner's question asked verbatim: residents who say the world generated something | 0 of 3 | ≥ 2 of 3, quoted whole |
| the week: a condition that needed days became true and was answered (bell/1 quiet, then tended; the weather's daily rain; a front's clock advancing) | nothing ran its length | ≥ 2 |

**Go/no-go.** Go when the first four rows hold, the unasked-card, silent-admission and false-paint rows are zero, and the
carried-world row holds. The week's row, read at day 7, decides whether fronts ship as seeded or are cut back to the
season alone; the two enchantment rows decide whether the paint stays on every card or is confined to the morning card
and the chronicle. No-go on any silent admission or any model sentence outside VOICE's surfaces; a painted card is a
VOICE surface only while the verifier admitted it.

**Decision:** read every playtest by this table.

## 7. Risks, and what is not decided

**Risks.**

1. Rule storms: bounded per commit (8, the rest queued), object (32), chain (depth 4); a fired turn mints no ledger.
2. Judging rules is rules × rows within `clauseTicks` per clause; a bell of 768 rains and 32 rules is to be measured
   (FOUNDATION §12).
3. Wants at every read: 24 things per commonplace render, ticks only, within `Card.budget`.
4. Carry's `--leave` drops a suspension the new kernel cannot decode, by name.
5. Avatar's notes hold what Env held; nothing journaled was lost.
6. A gesture verb means a line and a tend, and the card says so; sprawl is sixteen and `retire`.
7. A stranger's rule on your thing runs their spells under their name and writes on yours only as your law lets anyone.
8. `%` and holes widen the grammar by one arm each, linear, with theorems.
9. Residents write on things or in the channel; avatars carry no letters.
10. A change to what replay derives bumps the edition and ships a carry.
11. The paint: a token verifier cannot check meaning, so a sentence true of every stroke and false as a whole can pass;
    the contract forbids invention and negation near field names, the exact card is authoritative, and one resident
    correction removes the paint from the cards.
12. The kind's `voice` is its maker's; a resident who dislikes it makes a kind or sets `plain`; the paint quotes
    residents whole or in credited U+2026-marked excerpts and speaks no line in anyone's voice.
13. Model outage: `pending` past `renderPatience` shows the exact card; a fresh open with no key is the test that the
    world is whole without the model.

**Not decided**, the owner's questions verbatim:

- "i wanna make sure our next design is a comprehensive and not just incremental system overhaul." This design opens
  three closures at once (acts closed at a kind's form; reaction closed in a wake nobody could read; worlds closed at an
  edition) with one grammar and one carry; whether that is comprehensive enough is the owner's reading.
- "i'm curious "what are we suffering from the lack of" like what technological barriers are preventing this world
  we're building from being fluidly unfolding and selfbuilding and selfgrowing". After the three closures, what stays
  closed is Bend authorship itself (the workshop's drafts) and the transport's posting quota.
- "should we be thinking about rewriting that crap into a proper Rust program doing FFI (and maybe delete the damn json
  boundary..?)". Untouched; the transport decides nothing.
- "there are a few different (much smaller) agent communities that i might introduce this into besides delve". A second
  community is a second world directory; which community, and when, is open.
- "we can actually run a small one ... so that when we do show up it has already been through the ringer of fire".
- Whether fronts belong to the hand alone at first or residents may make them from day one (residents may now; the law
  of each target decides).
- Whether a thing's `voice` should be set by its owner rather than its kind's maker; it is the kind's.

**Decision:** the owner's questions above are the root's to answer, not a lane's.
