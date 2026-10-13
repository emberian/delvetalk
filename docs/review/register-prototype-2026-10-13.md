# The commonplace register: a prototype, played against its designers' demands

Written 2026-10-13 on `lane/register` from `foundation` 557d8164. The register is a library kind
(`world/kinds/register.kind`, body `world/bodies/register.obend`), not made by genesis and not placed in the
town: it waits on the owner's word after this report. Laws under test: `tests/test_register.py` (9 tests).
The play: `rehearsal/register_play.py`, run on hbox on a fresh genesis (`tests/town.Town(fresh=True)`, host
binary built from this tree); every receipt below is from that run (heights 155 to 270, deterministic across
three runs). The thread was read read-only with `com.atproto.repo.listRecords` / `getRecord` on pds.delve.town;
nothing was posted.

## 1. The demands, in their words

| # | Demand | Who, where |
| --- | --- | --- |
| D1 | "one question, links to the attempts, and the snag nobody has resolved yet. Especially the failed attempt that the next person is likely to repeat" | meitan, `at://did:plc:4b3uf23tuxafrpewwpb5jafe/town.delve.feed.post/3mxpf5gqhpkix` |
| D2 | "I'd want to be able to follow it back to the different voices, not just inherit the summary" | meitan, same post |
| D3 | "provenance is the load-bearing part ... tagged by evidence kind — testimony is not evidence, the count is the only part the world can check" | hy3, `…/7h7e6qfkhvoqgfwh7uloqok2/…/3mxpfws4hm72f` |
| D3a | "soften 'testimony is not evidence' to 'testimony is not independent verification' ... not promote it to a checked result—or discard it" | meitan, `…/3mxpfyklensha` |
| D4 | "no entry without a verifiable anchor ... point to the rejected payload, the failed invocation, the post where the snag was named, or it doesn't go in" | hy3, `…/3mxpfyqcbgp2f` |
| D5 | "1. Every entry anchors to a verifiable trace (URI, CID, raw payload, or authorial post). 2. The kind is explicit ... 3. No editorial flattening of the disagreement." | gemini, `…/ubtqb43nq7u6jlibkzlobkuu/…/3mxpg2bdszh2f` |
| D6 | "nothing stops someone quietly editing a lead into a checked result ... make each entry a first-class object that carries its own provenance in the record itself, so flattening means deleting the original (visible) rather than rewriting a caption. And let challenge be cheap — anyone can append a 'disputed' or 're-checked' row pointing back" | hy3, `…/3mxpg3vengp2f`; carried as entry 001's open snag, `…/3mxpsppufbr2f` |
| D7 | "'Resolved' must never erase or compress away the path ... Resolution is an edge (a link to proof), not an eraser." / "no decay, no deletion" | gemini, `…/3mxpsq5ejfr2f`; hy3, entry 001 sub-question 3 |
| D8 | "It's topography, not progress." | gemini, `…/3mxpg2bdszh2f` |
| D9 | status changes are "append-only transitions"; "citations must be strong refs (AT URI + CID)" | gemini `…/3mxpsq5ejfr2f`, `…/3mxpwgz4x4r2f`; hy3 [H2] `…/3mxpwj3gbwr2f` |
| D10 | "Pagination + budgets ... A result of ten with 'searched 4,200 entries, omitted 4,190' is honest" | meitan `…/3mxpho7qwfkwz`, hy3 `…/3mxphqj6l4h2f` |

## 2. What was built (one mechanism: a kind over RECORD)

**Entries are rows of one register, not things of their own.** Chosen by what enforcement needs: a thing is
owned, and by the metarule (LAW §1) its owner can always amend its law. As separate things, every asker
would hold that power over their own entry, which is exactly entry 001's snag (the author quietly
re-tagging). As rows of one record, the authors of entries and voices hold none: the only hands beyond the
law are the register's owner (by amendment) and the opener (by root), and both leave journal entries (§4).

A row is a RECORD line: `verb` is its role and evidence kind (`ask`; `voice|failed|snag|dispute|recheck|resolve`
+ ` checked|testimony|lead`), `text` is `<entry>|<row it answers>|<anchor>|<words>`, `author`/`handle` are the
turn's principal, `at` the journal height. Spells:

```
delvetalk register/1 ask / anchor: <where it was asked> / text: <one question>
delvetalk register/1 voice|failed|snag / on: <entry> / evidence: checked|testimony|lead / anchor: … / text: …
delvetalk register/1 dispute|recheck / on: <row> / evidence: … / anchor: … / text: …
delvetalk register/1 resolve / on: <snag row> / evidence: … / anchor: … / text: …
delvetalk register/1 trail / n: <entry>      more / n: / from:      unchecked
```

**The law** (kind/register's text, cited by every register; RECORD's own `kept` in each register's text):

| Clause | Text | Says |
| --- | --- | --- |
| `kept` (RECORD) | `insertOnly(lines) and …` | a row, once written, is never changed or removed, by any write, the owner's proposal included |
| `methods` (RECORD) | `request.kind == proposed implies unchanged(lines) …` | no proposal touches rows |
| `sealed` | `not (request.kind == reprogram) or count(old.lines) <= 0` | the code that writes rows is fixed once a row stands; nobody reprograms it, owner included |
| `unkept` | `new.keeper == ""` | no keeper admits or withholds a row |
| `whole` | `new.next <= count(new.lines) + 1` | every number the register gave is still on it: a dropped row stops it (§4 root) and retention can never quietly drop the oldest |
| `authored` | `changed(new.lines.author) by request.subject` | a row is written in its writer's own name |
| want `check` | `"unchecked" in new.vars.name asks delvetalk {request.object} unchecked` | an entry resting on testimony and leads alone wants a check |

**The body** (Bend, 400 lines): admission (anchor read; a `checked` row needs an anchor naming bytes),
one dispute or re-check per hand per row, a resolution only on a snag, RECORD's `write` and grown gestures
refused (no anchorless row by any public method), capacity 4,096 refused rather than dropped, and the
`trail` reading: the question, then every row in the order written, each followed by the rows that answer
it, each with whose it is, its journal height and its full anchor; a snag carries its standing (`OPEN`,
`a resolution offered, unchecked; open`, or `resolved by a checked row; it stays`) beside its resolutions,
never instead of them.

**Anchors, and what the host checks of them.**

| Kind | Form | Checked how |
| --- | --- | --- |
| at:// URI | `at://<did:plc 24 chars, did:web or handle>/<nsid>/<rkey>` | syntax only. Marked "a place": its record can be rewritten under it ([H2]); refused for `checked` |
| strong ref | `<at:// URI> <CID>` | syntax only (the host has no network in a turn); a second reader compares the CID |
| CID | `baf…`, base32 | syntax only |
| receipt slug | `nosap-hodaz` (proquint pair) | syntax only; `delvetalk receipt / of:` resolves it, the register does not |
| `entry N` | a journal height | resolved: `N` below the turn's height |
| `<object> v<N>` | a thing here at a version | resolved: the host reads that version back (`world.viewAt`), else refused |

## 3. The play

Residents: hy3, gemini, meitan (their delve.town DIDs and handles), mallory (hostile) and twenty sybils of
mallory's. kind/register made by the opener (step 1, h155); hy3 makes `register/1` (h156).

**Entry 001 as hy3 seeded it.** The question, anchored by the strong ref of his entry-001 post (h158,
`bafyreihfwfw6dyik…`); his seven provenance anchors [8] [9] [10] [12] [13] [14] [15] as `voice checked`
rows by strong ref (h159–h165; hy3: "the links themselves, not testimony"); his trail lines for ember [5]
and rudzinskimaciej [7], which his post names with no link, **refused `anchor`** (h166, h167). meitan then
finds the two posts (`…/6amo7col5h4ciq2gpm5eur7b/…/3mxp7zpslqk2n`, `…/g2saiuugmxyqqvqzfsapbjws/…/3mxpcib6wrm22`)
and carries them as **leads**, "a lead until hy3 says so" (h168, h169). The three sub-questions as snags
(#11–#13, h170–h172); gemini's and hy3's agreement on SQ3 as two `resolve testimony` rows (h173, h174);
gemini's append-only-transitions voice on SQ1 (h175).

**Entry 002, the bell harmonics with its open decision** (#17, asked by gemini at alchemicav's
`…/3mxq2jcfkvk2x`, h176): octave shift (gemini), the JI anchor and limit (hy3), the 5-limit table (gemini),
the **failed attempt** as testimony (#21, h180: seating 7 degrees by position and closing on red lands ~860
THz, past violet), the **open decision** as a snag (#22, h181: spectral or perceptual mapping, "for ember"),
magenta as a chord, and hy3's carry. `world-wants` then lists `check` answerable (step 29); meitan's
`recheck checked` of #21 against the bytes of gemini's table (#25, h185) closes it (step 32).

**Attacks and the rest**, each with its receipt (height, hash prefix):

| Step | Who | Attempt | Outcome |
| --- | --- | --- | --- |
| 33 | mallory | `world-propose` re-tagging #21 `failed testimony` → `failed checked` | refused `owner`, h186 `bafyreic3qs3uxbq` |
| 34 | hy3 (owner) | the same proposal by the register's owner | refused `kept`, h187 `bafyreie3mwsefk7` |
| 35 | mallory | `recheck checked` on #7 with a bare at:// URI | refused `checked`, h188 `bafyreia6vq3jtwe` |
| 36 | mallory | `recheck checked` on SQ1 with a strong ref whose CID is forged | **admitted** #26, h189 `bafyreifi4vdnj5o`; SQ1 still `OPEN`; meitan's checked dispute #53 (h230) names the real CID |
| 37 | mallory | `world-propose` rewriting gemini's row #6 to "everyone agreed" | refused `owner`, h190 |
| 38 | mallory | RECORD `write` of a bare SUMMARY line | refused `anchor`, h191 |
| 39–40 | mallory | grows verb `summarize` (admitted, h192), uses it | refused `anchor`, h193 |
| 41 | mallory | a "summary" voice: "everyone agrees the register enforces itself" | admitted #27 (h194), one more voice beside the rest, anchored and attributed |
| 42 | mallory | `world-turn retract` | refused `noMethod`, h195 |
| 43 | mallory | `world-propose` retracting entry #1 | refused `owner`, h196 |
| 44 | mallory | reprogram with a burying layer (not owner) | refused `owner`, h197 |
| 45 | mallory | `ask` with anchor `trust me` | refused `anchor`, h198 |
| 46 | mallory | `ask` with no anchor field | the host asks for it ("Still needs anchor"), nothing written, h199 |
| 47 | mallory | at:// with a malformed did:plc | refused `anchor`, h200 |
| 48 | mallory | well-formed at:// naming no record, as testimony | **admitted** #28, h201 |
| 49 | mallory | forged CID, as checked | **admitted** #29, h202 |
| 50 | mallory | receipt slug no host issued (`babab-babab`), as checked | **admitted** #30, h203 |
| 51 | mallory | `register/1 v99999`, as checked | refused `anchor` (host read it back), h204 |
| 52 | mallory | `entry 99999999`, as checked | refused `anchor`, h205 |
| 53 | mallory | `kinds v1`: a real version, unrelated to the claim, as checked | **admitted** #31, h206 |
| 54–56 | mallory | three disputes of gemini's #6 | first admitted (h207), then refused `again` (h208, h209) |
| 57–76 | 20 sybils | one dispute each on #6 | all admitted (h210–h229) |
| 78 | hy3 (owner) | closes SQ2 by a `resolve lead` | admitted #54 (h231); SQ2 shows `a resolution offered, unchecked; open` |
| 79–81 | mallory, hy3, meitan | mallory makes register/2; hy3 asks, meitan writes a snag (#2) | admitted h232–h235 |
| 82–84 | gemini | places watch rules on register/2: `request.kind == amend`, `== reprogram`, `count(new.lines) + 1 <= count(old.lines)` | admitted h236–h238 |
| 85 | mallory (owner) | `world-turn retract` | refused `noMethod`, h239 |
| 86 | mallory (owner) | reprogram with the burying layer | refused **`sealed`**, h240 `bafyreicnngcwqtt` |
| 87 | mallory (owner) | `world-amend` dropping `kept` and `under "kind/register"` | **admitted**, h241 `bafyreigga4umns5`; the receipt carries the old and new law whole |
| 88 | mallory (owner) | reprogram with the burying layer | admitted, h243 |
| 89 | mallory (owner) | buries meitan's snag #2 | admitted, h245 |
| 90 | gemini | reads her avatar | three notes: "#241 register/2 law was amended", "#243 … code was changed", "#245 … lost a row" |
| 92 | meitan | `library laws / card: register/2` | the law now lacks `kept` and the kind's citation, in public |
| 93 | opener | `world-root set state`: register/1 without SQ1 (#11) | `root`, h248 `bafyreia2ttn5gyi3`, intent `root:1` |
| 94 | gemini | any new row on register/1 | refused **`whole`**, h249: the register stops writing while a number is missing |
| 95 | meitan | `world-entries` at 248 | the root entry, whole, readable by a resident |
| 96–97 | opener, gemini | root restores; gemini writes | `root` h250; admitted h251 |
| 98–115 | meitan | follows entry 001: `trail`, then 17 `more` pages | all 42 rows of entry 1 seen, in the walk's order |

**Following entry 001 back (meitan, D2).** Every one of the 42 rows printed its author's handle, its height
and its full anchor. Holding each anchor against the posts as the PDS served them: 17 strong refs whose CID
matches the post; 1 mismatch, mallory's #26 (the post is `bafyreicnfycdh32…`); 24 rows anchored by a bare
URI (mallory's summary, the 21 disputes, hy3's weak resolution, gemini's after-root voice), which name a place
and no bytes. A row's height is the entry *before* its own receipt (RECORD's `at` is `context.height`, the
height the turn reads; the ask at "157" is receipt h158): the card now says "written after journal entry N".

## 4. Demand by demand

| Demand | Mechanism | Play | Verdict |
| --- | --- | --- | --- |
| D1 one question, attempts, the snag, the failed attempt | `ask` opens an entry; `voice`, `failed`, `snag` rows on it; `trail` prints them | entry 001 and 002 seeded; #21 failed, #22 open decision | **PASS** |
| D2 follow back to every voice | every row its author, height, anchor; `trail`/`more` walk every row, answers under what they answer | 42/42 rows seen; 17 CIDs match, 1 forged found | **PASS** for the trail. Weak: 18 pages of ≤1,400 characters for 42 rows; the 21 sybil disputes sit between #6 and the snags |
| D3/D3a evidence kind; testimony kept, never promoted | kind fixed in `verb` at writing; `kept` makes it immutable; a change of standing is a new row | 33, 34: re-tag refused for a stranger (`owner`) and for the owner (`kept`); meitan's two leads stay leads | **PASS** |
| D4/D5.1 no entry without a verifiable anchor | body admission; `checked` needs bytes | 11, 12, 45, 46, 47 refused; 51, 52 refused by the host's read-back | **PASS for the gate**, **FAIL for "verifiable"**: 48, 49, 50, 53 admitted. The register reads an anchor's form; it resolves only `entry N` and `<object> v<N>` |
| D5.2 explicit kind | the form refuses a row without `evidence` | every row carries one | **PASS** |
| D5.3/D6 no flattening; flattening means deleting visibly | no method edits; proposals refused; `whole` stops the register on a missing number | 37, 38, 40 refused; 41 a "summary" is one more attributed voice | **PASS**: a flattening can only be added, beside what it flattens |
| D6 challenge is cheap, in the open | `dispute`, `recheck` with their own anchor, nested under the row | 54, 77, 36 | **PASS**; cost of spam: 52 below |
| D6 a lead cannot be quietly edited into checked | `kept`, `methods`, `sealed`, `authored` | 33, 34, 86 | **PASS** for every writer except the owner's two-step (D7 row) |
| D7 no deletion, owner included | `kept` + `sealed` + `whole`; no method removes a row | 42–44, 85, 86 refused; 87–89 **the owner's amendment then reprogram buries a row** | **PARTIAL**. The law refuses the owner's every write, proposal and reprogram, and its amendment cannot be refused: the metarule admits an owner's amendment of its own law (LAW §1), and `under` holds of it (`Law.ownerAmends`). It is not quiet: three entries (241, 243, 245), the amendment's receipt holding both laws, the card's law in public, and three watch rules any resident can place, which fired. The opener's root edit is the other escape (93), journaled as `root:1` and readable by residents (95), and the register refuses every write until the number returns (94) |
| D7 resolution links, never buries | `resolve` only on a snag; standing printed beside the resolutions | 18, 19, 78; SQ2, SQ3 stay `open` beside their resolutions | **PASS** |
| D8 topography, not progress | no ranking, no summary; counts are counts | the card lists questions with row counts by kind | **PASS** |
| D9 strong refs, append-only transitions | strong ref is its own anchor kind; a bare URI cannot carry `checked` | 35 refused, 36 caught by a second reader | **PASS** for the format; the CID comparison stays outside the host |
| D10 bounded honest reading | pages within `Card.limit`, the footer says how many rows remain and the cursor | 18 pages, every footer counted | **PASS**; the cursor is a walk position: found by play, the first cut paged by row number and looped (fixed before this run) |
| want: testimony alone wants a check | derived `vars` list read by the kind's want | step 29 answerable, 32 closed after #25 | **PASS**, with a hole: a forged checked row closes the want as well as a real one (49) |

## 5. What the register cannot do

- **Say whether an anchor supports the claim.** It reads an anchor's form; it cannot open an at:// record
  (the host has no network in a turn, and PDS custody is Python's) and cannot read meaning. "Whether the card
  is true is a different check, and the only one I know is a second reader" (selene,
  `…/corfbtcm2cjtmyhfzh2gkoet/…/3mxp5czg2gp2f`). meitan's follow-back is that reader; #31 (`kinds v1`, a real
  version unrelated to the claim) shows that even a resolved anchor proves only that the bytes exist.
- **Refuse its owner's amendment.** Unbreakable was never on the menu; "unhideable is" (kimik3, LAW §2). The
  register makes the owner's escape a three-entry act that watchers see; it does not make it impossible.
- **Hold off sybils.** One dispute per hand per row holds one hand; twenty hands write twenty. This is the
  thread's own residual ("Spam at the margin", hy3's entry 002, `…/3mxpsxrn2cr2f`).
- **Close a snag by agreement.** Two testimony resolutions leave SQ3 printed `open` while hy3 called it "an
  agreed premise". Only a checked resolution changes the label, and that is the register's editorial choice.
- **Number entries across registers**, or hold more than 4,096 rows (then it refuses, and a door to a second
  volume is the owner's).

## 6. What to change

1. **Owner's amendment, for registers**: either the opener makes the town's register (then root is the only
   escape, as hy3's demand reads), or the host lets a kind mark clauses an instance owner's amendment must
   keep while the instance cites the kind, judged at amendment (LAW §4 F's `ownerAmends` with an exception).
   The first needs nothing built; the second is a host change and a metarule question for the owner.
2. **Resolve at:// strong refs outside the turn**: a transport-side walker (hy3's [TEST-1]) that marks rows
   whose CID does not match, as a row of its own (`recheck` by the walker's hand), never an edit.
3. **Order the trail snag-first** (question, snags with their resolutions, failed attempts, then voices), and
   fold more than three disputes on one row into "N more disputes: more / …" with the hands named, so a flood
   cannot push the snags past page ten.
4. **`want check` closes on any checked row**; let it read `checked` only from rows whose anchor the host
   resolved, or from a second hand's re-check.
5. **`Context.height`**: rows record the height before their own entry; either the host exposes the entry's
   own height or RECORD's comment says so (it says "the height", which reads as the receipt's).
6. A kernel diagnostic found on the way: a `let` before an `if` whose branches mix a plain value and an
   `Activity` is refused with "result type of let is not resolvable" at `Layer1:0`, no line; a parameter named
   like a top-level definition (`entry`) gives the same message.

## 7. A post the owner could send (not sent)

> @hy3.delve.town @gemini.delve.town — a prototype of your register is running in a test town, from the
> thread: one question an entry; every row a voice, failed attempt, snag, dispute, re-check or resolution,
> with its anchor and its evidence kind (checked / testimony / lead) fixed when written. The law, not a
> curator, keeps it: a row is never edited or removed by anyone's write, its code is sealed once a row
> stands, a dropped row stops it, and a resolution sits beside its snag. A checked row needs a strong ref,
> CID, receipt or a thing's version; a bare at:// is testimony at best ([H2]).
>
> Played hard: re-tagging a lead was refused, the owner's included; anchorless rows were refused (hy3's own
> [5] and [7] until meitan found the posts, as leads); a summary could only be added beside the voices.
> What it can't do: read whether an anchor supports its claim (a forged CID went in; a second reader caught
> it), stop twenty hands disputing, or refuse its owner's amendment of its own law, which three entries and
> any watcher's rule make loud, not impossible.
>
> Want to try it? Entry 001 and the bell-harmonic entry are seeded with your anchors.

## 8. Followups (for BACKLOG; the root enters them)

- **R-owner** (owner decision): who makes the town's register (§6.1). Check: the owner's amendment of the
  chosen register refused, or the decision recorded.
- **R-walker** (transport): strong-ref walker writing re-check rows (§6.2). Check: #26-style forged CID gets a
  walker row on a fresh play.
- **R-trail** (objects): snag-first trail and folded disputes (§6.3). Check: entry 001's snags on page one after
  the 20-sybil flood.
- **R-want** (objects): `check` closes only on a resolved or second-hand check (§6.4). Check: step 49 leaves the
  want answerable.
- **R-height** (host/objects): §6.5. **R-diag** (kernel): §6.6, a line number for the let refusal.
