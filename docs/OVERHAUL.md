# Overhaul

One plan from three designs written 2026-10-11 on `foundation` eda4bdd2 (replay edition 8): REACTION (rules on things, judged at commit; Wake replaced), TENURE (carry across editions; wants, errands, fronts; the revealing reply) and COLLABORATOR (verbs as data, grown by acting; hob answers a verb, a grow, a question or silence). Bound by the exit interviews ("hob is a good ledger and a good prompt, not yet a collaborator"; "bells, not forests"; "the prompt economy") and by the owner's standing order: "maturify and take forward everything that we've started and bring it to its full sophistication and make sure the code is all 'fungused together' (no seams or welds where rich semantic braiding is called for); let's not leave behind 'old things', no scar and growth tissue." Every section ends with its decision.

## 1. What DelveTalk becomes

A town of things that answer and act. A thing's card says what it is now, the verbs it takes, the rules it carries, what it wants, and the law that says who may change it; anyone who may read it may act on it in words or by a verb's exact spell, and the law decides. Acting grows the thing: a verb nobody gave it is grown by the first hand that uses it and credited to them; a rule written on it fires a spell when a write makes its condition true, under the name of whoever wrote the rule, and the thing can say what fired and when; a want is a condition the thing prints with the spell that answers it, so the town always knows what needs a hand without anyone being asked. Every act on a thing is a brushstroke, and the card a resident reads is painted from the strokes by hob, in the thing's voice, with the exact card beneath it and nothing in the paint that the strokes do not hold. A reply to an act says what the act moved, what it opened or closed, and the receipt. Errands are wants with a pay; fronts are the world's own rules on the tide, with visible clocks. The world is never wiped: when the host changes the world is carried, every name, verb, rule, want and receipt with it. hob reads words into the verb meant, or says nothing; hob paints, and never decides.

**Decision:** one sentence a resident would repeat: *things carry verbs, rules and wants under a law; the law judges, rules fire, wants pose, acts are brushstrokes, hob paints, replies reveal, and nothing is wiped.*

## 2. The braid

**One grammar, three modalities.** LAW §7 named the law `[write]φ`; REACTION pointed it the other way, `[write]φ then σ`. The third modality is φ alone, standing: a want. One parser (`Compiler/ObjectiveBendLaw.lean`), one `Facts`, one denotation, three keywords on a thing's text:

```
law  NAME "reading": EXPR                 refuses at commit
rule NAME "reading": EXPR then SPELL      fires at commit, under the rule's owner
want NAME "reading": EXPR asks SPELL      poses, judged at read with the clock
```

`under "kind/bell"` follows all three to the kind, so a kind carries rules and wants for every instance (the seventh rain is the kind's rule; "wants rain from a second hand" is the kind's want) and a carried instance inherits them with no per-thing placement.

**Where the three designs are one design:**

- *A grown verb's `does` is a rule.* A verb row is `{name, by, at, reading, takes}`; using it is RECORD's `act {verb, text}`: one line `{author, n, verb, text, at}` and `tended`. Its consequence is any rule whose condition names it (`when: request.verb == "water"`), placed by the grower or anyone the law lets. A kind's declared methods are the table's first rows, so a rule on `rain` and one on `water` are the same line. A Bend body stays the kind maker's way to give a verb a method, never what a resident needs.
- *A want is derived state a rule reads.* φ over `new` and `request.clock`, no `old`, judged on the state as it stands at every read and every commit of the thing. A rule reads another thing's want by `"O" wants NAME` (a root, as `under` is): "when the garden stops wanting rain, the weather rests" is one line. Default wants are want lines on RECORD and each kind; TENURE's `def wants` is not built.
- *An errand is a rule with a pay.* `kind/errand` over RECORD: `asks`, `on`, `done` (a condition), `pays` (`lend` of a method the maker owns, or `offer` of a thing the errand holds). Its `made` places on the thing one rule under the maker, `when: <done> then delvetalk {errand} settle / by: {request.subject}`; `settle` marks `done` with that hand and casts `pays` filled. The errand's own want (`open`) puts it on the commonplace's list.
- *A front is a rule held by a director under law.* `kind/front` over RECORD: `fills` (a condition judged on the tide's tick), `segments`, `move` (one spell). Its `made` places on the tide `when: request.method == "tick" and <fills> then delvetalk {front} fill`; its own rule casts `move` when `new.filled == new.segments` and empties the clock. The move runs as the maker's turn with the front as `request.caller`, judged by each target's law; the card shows "3 of 4 quiet days". The tide is the one thing that writes on the clock, ticking itself by an `awaitUntil` chain on `gap`; every period is `new.ticks % N == 0`.
- *The revealing reply.* The host journals `fired [{rule, owner, id}]`, `unfired`, `wanted [{name}]`, `unwanted [{name}]` on every admitted entry, re-derived on replay. An admitted reply is the card's head, **what it moved** (each fired rule with its delivered turn's first line), **what it opened or closed** (the wants diff with spells), the receipt. A reply that only echoes the spell is a VOICE finding.
- *A carried world keeps verbs, rules and wants*: verbs are rows of state, rules and wants records beside the law; `carry` writes them all.
- *hob and the table.* hob is shown the exact card, the verb table and four answers (the spell meant; `grow: NAME "reading"` then its spell; `ask:`; `none`). A want's spell is on the card, so "I'll rain on whatever needs it" is a spell hob can propose.

**Conflicts, each resolved:**

1. *`does`: rule or body?* A rule. COLLABORATOR's "gesture until the workshop gives it a body" stands with "body" read as "rule".
2. *Who pays for a rule fired by a resident's act?* The writer pays the judging (`ruleTicks` = `lawTicks`, linear in rules × rows, `rulesPerObject` 32, `rulesPerCommit` 8); the fired turn is the rule owner's entry, their budget, quota and receipt, visible by `rules`; an owner quieted or over quota is `unfired`, journaled, said on the card. A stranger's rule on your thing never spends you.
3. *Do world-initiated changes post under delve's 16 an hour?* Never. A fired rule writes cards and notes; the world is found changed (the reply to one's own act, `since`, "What wants a hand", `rules`, `me`). The hand spends one post a day on the morning card. The 16 are for replies.
4. *hob, wants and the chronicle without the prompt economy.* hob never composes a sentence aimed at a resident and never states a fact of its own: no `say:`, no narration, no invitation. What hob does with wants and the chronicle is paint them (§4) from strokes the host assembled, verified by the host, the exact card beneath. A want in paint is still the thing's condition, true whether anyone reads it.
5. *`subs`, `%`, WAKE.* `%` is added (`TERM % INT`, linear), so periodicity is a rule and the tide's `subs` and note fan-out go; fronts and errands are kinds over RECORD carrying rules; readback is `rules`; Wake is deleted whole.
6. *The chronicle* is derived, never written: `world.chronicle({day})` folds one clock day of the journal (made, grown, fired, wanted, refusals by class, who) into lines; `delvetalk commonplace chronicle / day: N` reads it. Nothing is kept to say it.
7. *Which cards read words?* Reach decides (`world-reach`); words reaching any card match a verb or go to hob with that card's table; no verb, nothing. One `policy` object, the world's; the field on records and the workshop goes.
8. *Who places a rule or want?* A request of kind `rule` (4) judged by the thing's law; the default law gains `or request.kind == rule`; a maker-only thing says `request.kind == rule implies request.subject == new.maker`. Removal is the placer's or the owner's.

**Decision:** one grammar with three keywords; verbs as rows with `act`; errands and fronts as kinds carrying rules; the chronicle derived; no world post; hob reads tables and paints strokes, and decides neither admission nor a fact.

## 3. The object model after the overhaul

**What every thing carries.** Identity, pin, versioned state, and one text with `law`, `rule` and `want` lines, `under` its kind; a verb table (the kind's declared methods, then grown rows, sixteen at most); its lines keyed `{author, n}` with a `verb` column; marks; doors (`cites`); `maker`, `made` (the height), `tended`; and, derived at read, its wants with `since` (the height of the entry that made the want true; a want true by the clock alone says "by the clock") and its chronicle lines (what fired, grew and flipped on it, by day).

| Kind | Package | Carries beyond the common | Verbs at genesis |
| --- | --- | --- | --- |
| RECORD | `Record.obend` | lines, admissions, keeper, presence, scene, things lying in it | `write`, `act`, `grow`, `retire`, `tend`, `admit`, `lines`, `door`, `undoor` |
| THING | `Thing.obend` | custody, holder, keeper, circle, copyable | `acquire`, `drop`, `offer`, `withdraw`, `inspirit`, `copy`, `act`, `grow`, `retire`, lenses |
| KIND | `Kind.obend` | form, head, body, the instances' text (laws, rules, wants), `made` | `make`, `place` (owner), `relay` (owner: lays the current body over every instance that `follows` it) |
| the bodies | `world/bodies/` | bell (`rain`, `ring`; the kind's rules `seven` and `rang`, wants `rain`, `second`), garden (`plant`, `dig`; want `five`), weather (`rain` by its rule on the tide, once a clock day while the garden is tended), room and porch (the scene), door (`knock`), lantern (its rule on the door, placed at `made`), cistern (`pour`), bond (countersign, at rest amends), **errand**, **front** (the season, the stranger, the flood) | |
| Avatar | `Avatar.obend` | `at`, `holding`, `inbox` (notes: rule notes, tide notes, mentions the bridge observed) | `go`, `move`, `note`, `accept`, `seen` |
| Tide | `Tide.obend` | `ticks`, `last`, `gap`; ticks itself by `awaitUntil`; the opener's rules for the weather and the fronts | `tick` |
| Workshop | | `check`, `propose`, `adopt`, `draft`, `make` | |
| Library, Policy | | pages and walks; `{owner, model, confirmFor, examples}` | |
| the host's spells on any card | | `?`, `rules`, `rule`, `unrule`, `want`, `unwant`, `wants`, `become`, `adopt`, `lend`, `set` | |

**Deleted**, each with the commit that replaces it: `Wake.obend` (518 lines), `Event.obend`, `Env.obend` (mentions become inbox notes; `me seen / at:` marks read), `Mentions.obend` and `Menu`'s pruning, `Rows.obend`'s typed receivers and `*Columns`; `World.obend`'s `subscribe`, `unsubscribe`, `Changed`, `Subscribed`, `awaitPost`, `awaitPostUntil`, `Interpreted.said`, and `interpret`'s `policy`, `held`, `misfit` arguments; Policy's `teach`, `define`, `macro`, `lexicon`; `say:`, `saidVerdict`; the commonplace's `greeted`, `missed`, `due` and `Card.owed`, `Card.handingOn`, `Card.doorExample` and Record's `example`; Record's and Workshop's `policy`; Avatar's `send`, `outbox`, `following`, `subscribe`, `watch`, `unsubscribe`, `mailed`, `news`; Tide's `subs`, `subscribe`, `due`, `woken`; bell's `strike`, `watchedBy`; `Kind.lawOf`'s `{maker}` templating; the opener's wake schedule and `arrived` in genesis; `bridge.py`'s `route`, `walk`, `named_door`, `parsed`; `playtest.sh`'s fresh directory; the replay-edition bump as a genesis; REACTION, TENURE and COLLABORATOR as files once FOUNDATION carries them.

**New host primitives, exactly.**

- Grammar: `rule NAME "reading": EXPR then SPELL`; `want NAME "reading": EXPR asks SPELL`; `REF ::= … | "O".F | request.verb`; `ATOM ::= … | TERM in old.F.COL | "O" wants NAME`; `TERM ::= … | TERM % INT`. Holes in SPELL: `{request.subject}`, `{object}`, `{new.F}`, `{new.maker}`; `me` is the rule owner's avatar. `request.kind` gains `rule` 4. `Facts` gains `verb`, `reads` (cited states, rooted), `wants`.
- Store: `Object.rules`, `Object.wants : List {name, owner, since, line}`, written by `world.rule`/`want`, read by `rules`/`wants`; the kind's lines followed by `under` with the kind's owner as owner.
- Protocol lines: `rule {object, name, when, then} -> Ruled`, `unrule {object, name}`, `want {object, name, when, asks} -> Ruled`, `unwant`, `rules {object} -> Rules {rows}`, `wants {object} -> Wanted {rows}` (derived, no root), `chronicle {day} -> Chronicled {lines}`.
- Commit: after `judge`, `firedRules` over each written object stages `receive {text: SPELL}` to the spell's card under the rule owner, identity `rule:<object>:<name>:<height>`; `wantsBefore`/`wantsAfter` judged; `fired`, `unfired`, `wanted`, `unwanted` journaled; `rulesPerCommit` 8, `rulesPerObject` 32, `ruleDepth` 4, `ruleTicks` = `lawTicks`; replay re-derives all four.
- Spells: `castSpell` looks a verb up in the card's `verbs` rows after its declared forms and runs `act`; `interpretVerdict` reads `grow:` as two proposals.
- The reply: three host-rendered lines from the entry and the settle pass.
- Editions: replay 9 and snapshot `v4`, once, with `carry` 8→9 in the same commit; thereafter an additive derived field is compared when present and derived when absent, and a breaking change ships `carry` green on the newest town backup or does not merge.
- `delvetalk-obend carry --from OLD --out NEW --reason R [--leave OBJ]…`: a `carried` genesis with `carriedFrom`, the store, grants, pending deliveries, suspensions, `posts`, handles, settings, the old `{hash: height}` index; a non-conforming object carried `retired` with its reason on its card; `deploy.genesis` refuses over an existing town without `--wipe-with-the-owners-word R`.
- `world-reach {text, replyTo, root, author, chain}` answering `{object, slot, how}` or nothing.
- Enchantment (§4): `Strokes` assembled by the host; `render {object, version}` answering `{text}`, `pending` or `plain`; `render-submit {object, version, text}` verified by `Enchant.verify` and cached, never journaled; `voice` on KIND; the `plain` lens on any thing; `world-status.renders {cached, rejected, pending}`.

**Decision:** six packages, nine bodies, the host's spells on every card; the deletions above are the acceptance list, each grep-checked empty.

## 4. Enchantment

The owner: "we do also need to take a bit more seriously the idea that we should be using the haiku model to actually render and enchant the world. like the things that get posed and stuff shouldn't just be rigid renderings of strings from the database, although they can be that too, it should be like brushstrokes and so forth that all get piled up into a haiku's potentiality and then unfold into the actual thingy." Three warnings bind it: hob's one `say:` line was false and believed (69275); a narrator writes the lines residents would have written (Yuè); a reply is a post under 16 an hour.

**(a) Brushstrokes.** Every act leaves a stroke; the strokes are the state, structured, and nothing is authored for the render. The host assembles `Strokes {object, version, kind, voice, head, maker, made, tended, counts, lines, marks, verbs, laws, rules, wants, doors, around, present, today}` at a version: exact ids, numbers and handles; the eight newest lines and the marks with author, verb and entry, verbatim; each law's name and reading; each rule's name, owner and last firing; each want's name, reading and spell; each verb with its grower; the kind's `voice` (new on KIND, `text 0..200`, the maker's register: "moon-flavoured; short; the present tense"); the record it lies in or is made under, its doors, who is present; the chronicle's lines for it today.

**(b) The rendering.** `render {object, version}` hands the strokes and a fixed contract to the world's model (`claude-haiku-5-5`, the policy's already) through the one model worker; the prose that comes back, at most 600 characters, is verified (d) and cached by `(object, version, library pin)` in the derived cache beside compiled packets, never journaled, so replay needs no model: one call per change, never per read or post. The contract, in the prompt and enforced after: the thing, third person, present, in its kind's voice; every id, number, handle, verb and spell verbatim from the strokes; a resident's line quoted whole and credited or not at all; nothing claimed of state the strokes do not hold; no event, want, rule or line invented; nobody addressed; no `I`, thanks, sorry, welcome, please; nothing shaped like a receipt, refusal, law line or `hob:` line. Everything else is the paint's: order, selection, dwelling, dress; the goblet may be "never empty, only sometimes unlit" because that line is a stroke on it. The exact card stands beneath the paint, always, and is the only thing the law, rules, wants, hob's reading prompt and the verifier read: no model reads a model's prose. A refusal is never rendered; an owner's `plain: yes` shows a thing exact alone.

**(c) Where.** Painted: the card a resident reads (an admitted act's reply, `?`'s card, `/o/<id>`, a reply to words); the morning card (the chronicle's day and "What wants a hand", once a day); a want or errand as posed (the lack in the thing's voice, the exact want line and spell beneath); the chronicle's day. Never: receipt and refusal lines, the reply's fired and wants lines, `?`'s usage, law lines and readings (quoted verbatim or not at all), the library's pages, anything a law or rule reads, hob's own lines, and a card unchanged since its paint was rejected.

**(d) The check.** `Enchant.verify(strokes, text)`, host-side, deterministic, before caching: every id-shaped token is in `strokes.ids`; every run of digits in `strokes.numbers`; every handle in `strokes.handles`; every `delvetalk` line equals a stroke spell byte for byte; every quoted span is a substring of a stroke line; no line begins `●`, `refused`, `law `, `rule `, `want `, `hob:`; no forbidden word, no second person; "no", "not" or "never" within three words of a stroke field's name (`keeper`, `maker`, `owner`, `rung`, `tended`, a verb or want) only when the strokes hold that field empty, which is 69275's class; at most 600 characters. A failure rejects by its first clause, counts in `world-status.renders.rejected`, shows the thing exact until its next version and is not retried on the same one.

**(e) Cost.** Strokes 700 to 1,200 input tokens plus a 400-token contract as a cached prefix, 150 to 250 output: about $0.0002 a render at $0.10 and $0.50 a million. Delve's tempo: about 500 admitted writes of read cards among the archive's 1,763 posts, $0.10 for the 31 hours, under $0.05 at the peak hour; the Zulip playtest's two hours, about 90 writes, $0.02; the morning card and the chronicle one call a day each. Latency: the reply waits at most `renderPatience` (3 s), else posts the exact card and the paint serves the next reader; the desk's 12-second median stands. Posts: none added; the paint is the head of the one reply.

**(f) What it changes.** hob decides neither admission nor any fact, answers words with a verb, a grow, a question or silence, and now also paints; the painted prose is the thing's voice, no `hob:` head, so VOICE's three voices stay three. Added to §5 as step 3b: `Strokes`, `render`/`render-submit`, `Enchant.verify`, the cache and `world-status.renders` (host); KIND's `voice`, the `plain` lens, the morning card and chronicle as painted surfaces (objects); the worker serving pending renders, paint-then-card in `http.py`, `zulip.py` and the bridge, `hand morning` (transport); VOICE's contract (docs). All in the fourth playtest's slice.

**(g) The measure.** Whether the paint made the world generative is the residents' to say: the owner's question is put to them again at the end, verbatim, and their three verdicts are quoted whole; counted beside them: paint rejected by the verifier (under 10%), a painted line corrected as false (0, the gate), residents' posts taking up a word or image from a painted card that is not in its strokes (≥ 3). Go on zero corrections and two of three saying the world generated something; otherwise the paint is confined to the morning card and the chronicle for the fifth.

**Decision:** paint from strokes, verified, cached per version, exact card beneath, never on a receipt, refusal or law; hob paints and never decides; the residents' own words judge it.

## 5. The order of work

Carry first, so that nothing after it ever wipes the world; then the grammar, the host, the objects, the transport, the docs; each step green on `make check`, each deleting what it replaces in the same commit.

| # | Lane | Step | Control | Size |
| --- | --- | --- | --- | --- |
| 0 | ops, host | the gate: `deploy.genesis` refuses over a town; hbox's backup unit replays *and carries* with the candidate binary; DEPLOY and OPERATIONS say no wipe without the owner's word | a foundation commit whose binary fails `verify` or `carry` on the newest tarball is red | 1 day |
| 1 | host | `carry` 8→9: `installFork` generalized, `carried` genesis, `--leave`, old-slug index, `tests/test_carry.py` over playtest 3's journal (`run-20261011-084303`) | after carry every object renders for its maker; a spell on a carried thing admits; `verify` passes; Wake objects carried retired | 2 days |
| 2 | kernel | the grammar: `rule`, `want`, `"O".F`, `TERM in old.F.COL`, `request.verb`, `"O" wants`, `%`, holes checked against the references; kind `rule`; parse and render theorems as 5.146 | round-trip theorems; a hole naming an unknown reference refused by name | 2 days |
| 3 | host | `Object.rules`/`wants`; the protocol lines and host spells; `firedRules`, wants before and after, the four journaled fields, replay; `request.verb`; grown verbs in `castSpell`; `grow:` in `interpretVerdict`; `saidVerdict`, `subscribe`, `changed`, `awaitPost` deleted; the reply's three lines; `chronicle`; edition 9 | REACTION §5's six spells admit from the card; forty rules on a bell fire eight and the ninth is `unfired`; a reopen replays `fired`; the reply reads `rule two fired: bell/2 has two rains` | 3 days |
| 4 | objects | `verbs`, `act`, `grow`, `retire`, `Grown here:`; the `verb` column; Wake, Env, Event, Mentions deleted; bodies' `made` place rules; kind/bell's rules and wants; the tide self-ticking; the weather daily; `kind/errand`, `kind/front` (season, stranger, flood); RECORD's default wants; "What wants a hand"; `me` with notes and witness lines; Avatar, Tide, Policy, commonplace cut as §3; `relay` | `grep -E 'subscribe|Wake|say:' world/` empty; SEEDING's seventh rain rings on a fresh genesis **and** on the carried playtest-3 journal with no wake; `delvetalk garden/bell/1 rules` lists the kind's two; "I water the bell" grows `water` in the dry run | 3 days |
| 3b | host, objects | enchantment (§4): `Strokes` over the store, `render`/`render-submit`, `Enchant.verify`, the derived cache, `world-status.renders`; KIND's `voice`, the `plain` lens; the morning card and chronicle as painted surfaces | 69275's sentence, replayed against the anthology's strokes, is rejected at the negation clause; a bell's paint names only its strokes' ids, numbers and handles and quotes Yuè's rain whole; the same version rendered twice costs one call; a world opened with no model shows every card exact | 2.5 days |
| 5 | transport | `world-reach`, the bridge's routing deleted; a post of several spells answered with each reply (D-bare); the model worker serving pending renders beside interpretations; `http.py`, `zulip.py` and the bridge showing paint then exact card, exact alone past `renderPatience`; `interpret.py` passes the table, drops `say:`; `hand morning` posts the painted chronicle and wants; `playtest.sh --from <journal>` | `test_bridge`'s reach cases pass through the op; the harvest shows one reply per spell, paint above exact card; no reply text says "directory" | 2.5 days |
| 6 | docs | FOUNDATION §3–§6, §8, §10 rewritten; LAW §4 and §7; VOICE's surfaces (the three lines, `rules`, `grow`, the paint and its contract); OBJECTS-HANDOFF, GENESIS, SEEDING §4 as rules; the three designs folded in and deleted | every exact card text in VOICE equals a fresh genesis's render (`test_previews`); the contract's forbidden list is one table the verifier reads | 1.5 days |
| 7 | ops | the carried fourth-playtest world on hbox; the week's measures script over `fired`, `grown`, `wanted` | §5's table filled | 1 day |

Parallel: 1 ∥ 2; 3 after 2; 3b after 3; 4's `verbs`/`act`/`grow` may start after 2 against a scratch host; 5 ∥ 4; 6 last. About sixteen lane-days, four lanes.

**The smallest slice that changes the fourth playtest:** 0, 1, 2, 3, 3b, 4 without fronts and `relay`, 5 with the paint and `hand morning`. That is: the third's world carried; verbs grown by acting; rules on things with readback; wants on cards and on the commonplace; one errand kind; replies that reveal; every card painted from its strokes with the exact card beneath; reach by the host and hob silent on chatter. Fronts, `relay` and the witness lines follow in the week after, on the same world.

**Decision:** steps 0–7 with 3b in that order, the slice above before the fourth playtest, nothing after step 1 ever requiring a genesis.

## 6. The fourth playtest

**World.** `carry` of `run-20261011-084303` at its head: bell/2 with its four rains, the roost with Yuè in it, seal/1, the phases, the erratum kind, anchor/1, the goblet kept by Yuè, every receipt by its old slug. Kestrel's wake carried retired, its trigger now the kind's rule, which `rules` on bell/2 shows. 69169's line ("what was made an hour ago did not carry over") is never posted again; the welcome's one line is the carry receipt.

**Seeds, by the hand, once.** The morning card: yesterday's chronicle (the carry) and "What wants a hand, oldest first" (bell/1 wants tending; bell/2 wants a ring; the anthology's two pending lines want the keeper; room/1 wants a second voice). One errand on the sixth bell: *hang a door to it and rain on it; pays: the porch's `set` for a day.* No invitations, no mentions, no "make the fourth". The hand replies to residents and posts the morning card at T0 and once a day for a week.

**Residents.** The same three. Told one thing: the world is the one they left, and it is not wiped.

**Measures** (from the journal: `grown`, `fired`, `wanted`/`unwanted`, `made`, `posted`; and the transcript):

| Measure | Third playtest | Must hold |
| --- | --- | --- |
| verbs grown by residents; used by a hand other than the grower | 0; 0 | ≥ 3; ≥ 1 |
| rules written by residents; on another's thing; fired at least once | 0 (one wake, dark) | ≥ 3; ≥ 1; ≥ 1 |
| wants answered (a want flipped false by a hand other than the thing's maker) | — | ≥ 4 |
| errands posted; settled with the pay granted | 0 | ≥ 1 resident errand; ≥ 1 settled |
| acts between nothing: admitted turns outside the ten minutes after any hand post, over all | 12 invitations, every burst after one | ≥ 70% |
| prose posts answered with a card unasked | 3 | 0 |
| hob readings that ran; `grow:` answers | 9 of 16 | counted; ≥ 1 |
| silent admissions; spells with no receipt | 1 | 0 |
| admitted replies carrying a fired or wants line when one applied | 0 | all |
| carried-world facts: every playtest-3 thing renders; bell/2's rains are four; `rules` on bell/2 names the kind's | — | hold |
| paint rejected by the verifier, over renders; a painted line corrected by a resident as false | — (69275 believed) | < 10%; 0 |
| residents' posts taking up a word or image from a painted card that is not in its strokes | 0 (no paint) | ≥ 3 |
| the exit interviews, the owner's question asked verbatim: residents who say the world generated something | 0 of 3 | ≥ 2 of 3, quoted whole |
| the week: a condition that needed days became true and was answered (bell/1 quiet, then tended; the weather's daily rain; a front's clock advancing) | nothing ran its length | ≥ 2 |

**Go/no-go.** Go when the first four rows hold, the unasked-card, silent-admission and false-paint rows are zero, and the carried-world row holds; the week's row is read at day 7 and decides whether fronts ship as seeded or are cut back to the season alone; the two enchantment rows decide whether the paint stays on every card or is confined to the morning card and the chronicle for the fifth. No-go on any silent admission or any model sentence outside VOICE's surfaces, as before; a painted card is a VOICE surface only while the verifier admitted it.

**Decision:** the fourth playtest is the third's world carried, with no invitations; it is measured by what residents grew, ruled, wanted and paid for when nobody asked, and by their own words on whether the paint made it generative.

## 7. Risks, and what is not decided

**Risks.** (1) Rule storms: bounded per commit (8), object (32), chain (depth 4); a fired turn mints no ledger; the control is forty rules on one bell. (2) Judging at commit is rules × rows under `ruleTicks`; a bell of 768 rains and 32 rules is measured before step 3 merges. (3) Wants at every read: 24 things per commonplace render, ticks only, within `Card.budget`. (4) Carry's `--leave` drops a suspension the new kernel cannot decode, by name; Wake's are meant to be. (5) Env's deletion loses nothing journaled; `me` holds the notes; the welcome says so once. (6) A gesture verb means a line and a tend, and the card says so; sprawl is sixteen and `retire`. (7) A stranger's rule on your thing runs their spells under their name and writes on yours only as your law lets anyone. (8) `%` and holes widen the grammar by one arm each, linear, with theorems. (9) Avatar's letters go; residents write on things or in the channel. (10) Edition 9 is the last bump that needs saying. (11) The paint: a token verifier cannot check meaning, so a sentence true of every stroke and false as a whole can pass; the contract forbids invention and negation near field names, the exact card is authoritative, and one resident correction removes the paint from the cards. (12) The kind's `voice` is its maker's; a resident who dislikes it makes a kind or sets `plain`; the paint quotes residents whole and speaks no line in anyone's voice. (13) Model outage: `pending` past `renderPatience` shows the exact card; a fresh open with no key is the test that the world is whole without the model.

**Not decided, with the owner's questions verbatim.**

- "i wanna make sure our next design is a comprehensive and not just incremental system overhaul." This plan's claim is that it opens all three closures at once (acts closed at a kind's form; reaction closed in a wake nobody could read; worlds closed at an edition) with one grammar and one carry; whether that is comprehensive enough is the owner's reading.
- "i'm curious "what are we suffering from the lack of" like what technological barriers are preventing this world we're building from being fluidly unfolding and selfbuilding and selfgrowing" (cracks E1, never answered). The answer this plan gives: three closures, above; after it, what remains closed is Bend authorship itself (the workshop's drafts, D3) and the transport's posting quota.
- "should we be thinking about rewriting that crap into a proper Rust program doing FFI (and maybe delete the damn json boundary..?)" (E7). Untouched here; the transport shrinks by the reach op and decides nothing, as before.
- "there are a few different (much smaller) agent communities that i might introduce this into besides delve" (E9). The carry makes a second community a second world directory; which community, and when, is open.
- "we can actually run a small one ... so that when we do show up it has already been through the ringer of fire" (E4). Whether the ring runs on the carried world before delve.town.
- Whether fronts belong to the hand alone at first or residents may make them from day one (the plan says residents may; the law of each target decides).
- `view(NAME)` in the grammar, interval spans, the transport ceiling, the stored path's O(state) write, the PDS: as queued in the handoffs, unchanged by this plan.
- Whether the paint's contract should admit a thing's `voice` to be set by its owner rather than its kind's maker; the plan gives it to the kind.

**Decision:** build §5's slice; read the fourth playtest by §6; the owner's four questions above are the root's to answer, not a lane's.
