# Suite audit

Lane tests2, on foundation fcadbd6, 2026-10-10. The owner's brief: too many tests, too fine-grained,
some of them bullshit; more confidence, faster, with fewer lines. The external review of a3e1fb2
(`docs/review/codex-2026-10-10/`) found sixty-odd real holes that none of the then 1,100 tests caught:
direct turns past form bounds, a stranger's generic write to every object, cards past the clip, a
retry after reprogram. Each is the kind of claim one quantifies over every object, method and
request, not one example of. That is the measure here.

## Before

| | |
| --- | ---: |
| test files | 111 (`tests/test_*.py`) |
| `def test_` | 1,274 (1,285 run: inherited classes) |
| classes | 314 |
| lines in test files | 27,660 (plus 303 in `host.py`, `wire.py`; 187 in `run.py`) |
| wall time, hbox, whole suite | 70.0 s (`swarm-build`, load about 20), 0 failed |
| by layer | kernel 171, host 493, objects 242, transport 275, rehearsal 37, unlayered 67 |

## Verdicts

Every file was read whole. A verdict is one of: **keep**; **fold** into a scenario or property that
says the same thing once; **split** (the file's adversarial tests stay, the rest go); **delete**.
A test is flagged when it is a test of its own fixture, a literal that restates the code (whole card
texts, hint strings, CSS), one path three other tests already walk, a wall-clock bound, a tick count of
library code, or a failure that would not say what broke. `LATER` marks the files another lane has
open (rewrite2: 28 files with uncommitted edits; host13: 5; `test_make`): they are audited, not
touched in this pass.

| verdict | files | tests | lines |
| --- | ---: | ---: | ---: |
| keep | 33 | 354 | 6,832 |
| split | 59 | 843 | 18,810 |
| fold | 12 | 53 | 1,384 |
| delete | 7 | 24 | 634 |

What survives a split is overwhelmingly adversarial: forged checkpoints, tampered journals and
snapshots, a stranger's write, reprogram or amendment, grants past their use, the causal ledger across
restart, OAuth state replay, identity challenges, the front under malformed input. What goes is mostly
the same claim made with exact text: whole cards, hint strings, tick counts, page constants.

| file | layer | tests | lines | claim | verdict | flagged |
| --- | --- | ---: | ---: | --- | --- | --- |
| canonical | kernel | 12 | 307 | Every Data value and journal entry has one canonical DAG-CBOR form and the AppView's real post records re-encode to the CIDs it returned; foreign CBOR and tampered journals are refused by name. | keep | wallclock: 1 |
| canonical_compare | kernel | 3 | 113 | Bend's canonicalCompare orders values exactly as their canonical bytes do (what makes relations sort in-turn the host's way). | keep | - |
| conformance | kernel | 3 | 272 | Python, JS and C evaluators agree with the Lean machine on 400 generated core terms: values, stuckness and yielded Plans. | keep | fixture: 1 |
| data_type | kernel | 12 | 347 | Data is the universal first-order payload: one activity carries any shape, Data.of checks its type, Bend cannot take Data apart, and a malformed Data value (repeated record field) is refused on every admission path. | split | dup: 1; opaque: 1 |
| derived_forms | kernel | 1 | 51 | A derived forms() lowers to exactly the packet of the same object with forms() written out. | delete | - |
| hints | kernel | 5 | 119 | A refused package names the pseudo-Bend habit (untyped closure, Some/None, arrow arms, // comments...) behind the refusal and the real form; hints never change acceptance. | delete | literal: 2; dup: 1; opaque: 1; fixture: 1 |
| layers | kernel | 5 | 151 | A layer module overrides definitions below it for every caller in the package, Super reaches the version below, and an override cannot change a type. | split | literal: 2 |
| list | kernel | 5 | 90 | The prelude's find, indexWhere, filterMap and removeWhere answer in order, including at the 247-item cap. | delete | ticks: 1 |
| located | kernel | 3 | 90 | Every refusal of an elaborated package names definition, span, expected/found types in surface syntax, alike from check-package and compile. | fold:S-workshop | literal: 3 |
| methods | kernel | 4 | 93 | The compiler records an object's method table (which definitions are methods) and the shape of its Bend law predicate, and refuses a law that is an activity or returns another sum. | split | literal: 1 |
| protocols | kernel | 5 | 104 | A protocol declared in the library is checked against an implementing object at compile; a missing or mistyped method is refused by name, located, with a hint. | split | literal: 1; opaque: 1; dup: 1 |
| sugar | kernel | 52 | 1019 | Each surface sugar (Data injection, inferred type args, let-response, interpolation, form blocks, write{}, derived Edits/keep, fixed fields) compiles to the packet of its explicit spelling, and a misuse is refused by name. | split | literal: 7; dup: 3 |
| tariff | kernel | 10 | 269 | The tariff is pinned (exact ticks) and byte/time charging cannot be dodged: results run under exactly their canonical size, bignum squaring and long text equality and failed prefix scans are charged before they allocate or spin. | split | ticks: 4; dup: 1 |
| text_words | kernel | 3 | 94 | textHasAny finds whole case-folded words in one pass with a tariff linear in text and word list. | split | ticks: 1; wallclock: 1 |
| turn | kernel | 35 | 829 | The stateless kernel resumes an activity only from a checkpoint this process issued for this package, object, principal, intent and roots; budgets are named silences; the message dialect and closure pruning compile. | split | ticks: 1; literal: 2; dup: 1 |
| world_calls | kernel | 13 | 275 | A world call is a typed perform of the world object: each call site resumes at its own result type, checked against the world protocol, and misuse is refused by name. | split | fixture: 1; literal: 1; dup: 4 |
| arrive | host | 11 | 308 | An arrival from the clock principal records the newcomer's handle and creates their Avatar, Env and Wake owned by their DID exactly once, and the Wake hears plantings and its own bell. | LATER split | literal: 3; opaque: 1 |
| authority | host | 17 | 346 | A write changes only the running object; cross-object change is a call the callee's own law judges, and the law sees (and a client cannot forge) who called. | keep | literal: 1; dup: 1 |
| await | host | 19 | 362 | Objects are born in turns (create), and a turn suspended on a post or another turn's receipt resumes when it lands, times out by the journaled clock, survives restart, and is rebased or bounded. | LATER split | opaque: 1; dup: 4 |
| call_reading | host | 2 | 74 | A refused world.call (and world.run) carries the refusal's voiced reading beside its clause so a directory handing a reply on can say why. | fold:P-refusal | literal: 2 |
| chain | host | 2 | 133 | Sends/subscriptions ring a bell that opens a door that lights a lantern in the settling pass, and a send cycle ends in a budget-exhausted refusal. | LATER split | - |
| changes | host | 12 | 350 | Subscriptions: every admitted write touching a watched field delivers `changed` to the subscriber's named receiver (typed), capped at 64 subscribers and 32 changes a write, derived from the journal on replay, and a field-level root makes a suspended turn stale only when its field moved. | LATER split | dup: 2 |
| commute | host | 8 | 164 | Commutative edits (keep/add/append) commit against a moved root and are judged on the state as it is now; any other edit of a moved root, or a future version, is stale. | keep | dup: 1 |
| compile_cache | host | 4 | 101 | The compile caches are content addressed: a second world in the same process starts with what the first compiled, and an optional disk cache is read by another process and a damaged file is recompiled. | split | literal: 2; opaque: 1 |
| deliveries | host | 16 | 316 | A send runs as a later turn under the sender's principal with a causal ledger (depth, work, storage) that only shrinks; chains stop by named budget refusals and a restart neither loses nor mints a delivery. | split | dup: 1; ticks: 1; opaque: 1; literal: 1 |
| document | host | 5 | 184 | The host renders a Document byte for byte as Bend's Document.plain/lines does (20 generated documents), refuses oversized or malformed documents by name, and an offer turn's card is retained on its receipt and replayed. | split | literal: 1; dup: 1 |
| durability | host | 2 | 53 | Each sync mode (none/fsync/full/default) opens, writes and reopens a journal to the same head; any other value is refused by name. | split | dup: 1 |
| extend | host | 10 | 343 | Extend, not replace: a layer grafted by reprogram, the extend Plan or the host's become/adopt/lend spells overrides what it defines, stacks, survives snapshots and replay, and is judged by the object's law; late binding makes Bell's own reply use the layer. | split | dup: 3 |
| fork | host | 5 | 126 | A fork is a private journal seeded from the shared world at a height: its turns never touch the shared journal, it carries its origin, a fork at an earlier height holds the earlier state, and a private object is omitted for a stranger. | LATER keep | opaque: 1 |
| form_bounds | host | 7 | 183 | A spell and a direct turn are judged by the card's own declared form bounds: a source field takes up to 16 KiB, a fenced block is the source field, the declared min/max hold and are shown by inspect. | LATER split | literal: 1; forms: 1; dup: 2 |
| grants | host | 21 | 421 | A grant lets one grantee run one method of one object as its grantor, for a bounded number of uses and clock, revocable only by the grantor, optionally fixing part of the callee's argument; a law naming the grantor admits it; law membership facts read state. | keep | opaque: 2 |
| handlers | host | 7 | 238 | A handler object answers the Plans a callee yields before the host does (run), nested handlers pass outward, and judge answers the law's verdict on edits without committing. | split | dup: 2 |
| host_spell | host | 8 | 137 | The host's spell-parse answers every recorded fixture as recorded (parse, bare, fit, natural) and names the refusal clause. | keep | opaque: 1; literal: 1 |
| input_post | host | 4 | 162 | `inputOrigin.post` is the post a turn came from, kept when the host reads the reply as a spell, inherited by called frames, brought by delivered spells, and journaled across suspensions. | split | dup: 1; opaque: 1; edits: 1 |
| inspect_reads | host | 3 | 77 | world-inspect lists per method what the law admits for the asking principal (true, or the refusing clause and reading, state-reading clauses judged as they stand), omits source on request; world-objects {methods} lists only turnable methods of objects the reader may view. | LATER split | literal: 1; opaque: 1 |
| integration | host | 9 | 191 | An argument a method does not take is a journaled typeMismatch that says what the method takes (and binds the identity); profile does not change the receipt; inspect answers forms; writeOnce admits exactly one change. | LATER split | ticks: 1; literal: 2; dup: 2 |
| interpret_object | host | 6 | 212 | A model-fitted spell's proposal names the card whose form it fitted; hob's three non-spell answers (none, card, ask) and several spells in one answer come back as the right verdicts. | split | opaque: 1; dup: 1 |
| interpret_quota | host | 2 | 68 | interpretQuota (default 48) interpretations a principal may start per clock hour; the next is a transient `quota` refusal with `next`, counted from the journal and exempting the opener. | keep | opaque: 1 |
| items | host | 5 | 108 | List items are amended and removed by their canonical bytes (first equal item), an absent item is refused absentItem, and Place/Tide write by key not by index. | delete | opaque: 2; dup: 3 |
| journal | host | 4 | 85 | A source module is journaled once and named by CID after, a journal opens in one process at a time, and two hundred bells replay from one copy of Bell. | LATER split | wallclock: 1; dup: 1 |
| law | host | 16 | 338 | Two-tier law: the Bend predicate judges after the law text admits, reads declared roots under its own budget, never sees objects its subject may not view, cannot seal out reprogram/amend; readings reach the receipt and public projection; creation law; proposed (kind 3) writes. | split | literal: 3; opaque: 1; dup: 1 |
| make | host | 5 | 148 | `make` creates an object from a resident's own source under the maker's authority and journals madeFrom {object, pin, receipt}; a compile failure is refused with the checker's diagnostic; a kind can create and graft in one turn atomically. | LATER split | dup: 2 |
| outbound | host | 44 | 947 | The host-owned outbound channel: posts recorded so replies find their object, cards under the reader's authority, offers to their addressees, publications, public projections of receipts, the clock, minted ids, source pins and transient refusals. | split | literal: 6; dup: 4 |
| post_reserve | host | 4 | 122 | Posting reservations are host facts: a delve.town post is reserved against postQuota once per intent and given back only by release, Zulip is uncounted, and transient model failures are journaled `attempted` with a backoff until the last attempt. | split | literal: 1 |
| public_methods | host | 9 | 205 | A method is public only when its package declares it (forms(), methods(), views() or a conventional name); a helper is noMethod to a direct turn, call, send or run and absent from inspect/forms, except a change delivered to the receiver the subscriber named. | keep | literal: 2 |
| reach | host | 8 | 126 | Only words that reached a card go to the model: prose with no reach is answered 'not addressed' at once (no suspension, no quota); a stated mention, a reply to a recorded post, a named method or checked field lines reach; the reach is part of the request. | keep | dup: 1 |
| reads | host | 7 | 130 | The host's read ops behind the AT repository: one public reader name, entries by hash (bytes only for their own principal) and by page, an object as of a version, sources by cid and by page. | split | literal: 2 |
| reflection | host | 35 | 617 | Programs read programs: the sealed standard library (pinned, changed only by the opener), inspect/check under the turn's principal, interpret as a suspension settled by a model reply, the sending object as a delivered turn's caller, and reprogram/amend of another object through a forge judged by the target's law. | LATER split | literal: 3; dup: 2; fixture: 1 |
| relation | host | 20 | 362 | A Relation field stays sorted by its key's canonical bytes with no key twice and within its limit; insert/upsert/retract follow the nine-cell table; waiting turns' row edits commute or go stale by key. | keep | wallclock: 1; literal: 1 |
| replay_edition | host | 1 | 41 | A journal names the replay edition it was written under, and a host of another edition refuses it by name before replaying. | keep | - |
| reprogram | host | 25 | 303 | An object is reprogrammed and its law amended from within, each judged by the object's own law; the default law lets anyone invoke and only the creator change code; migrations convert state once; the metarule rejects a law that locks out its author. | keep | dup: 2; opaque: 2 |
| slug | host | 4 | 84 | A slug (two-word proquint of the first 32 digest bits) names a CID for people: fixed per CID, resolves back to the one receipt, pin or state, and an ambiguous slug is refused. | split | literal: 1; dup: 1 |
| snapshot | host | 11 | 281 | A snapshot every thousand entries lets a reopen replay only the tail; a tampered, foreign, forged or inconsistent snapshot is refused by name and the previous snapshot or full replay is used. | keep | wallclock: 1; literal: 1; opaque: 1 |
| spell_turns | host | 21 | 435 | A reply to a message-dialect card is parsed by the host and runs the method it names with the typed argument; misfits are refused badSpell with clause, reason and hint (or handed to receive as `misfit`); lenses `set` one field through its kind; fixed fields cannot be moved; a model's text fitted as a spell is a proposal/unclear/replied verdict. | split | literal: 4; dup: 5 |
| sum_words | host | 6 | 141 | A text word for a closed sum of empty cases at the boundary names the case (field, nested record, list); a word naming no case is refused typeMismatch naming the cases, or answered unclear for a model proposal. | split | opaque: 1; dup: 1 |
| supervisors | host | 7 | 151 | A supervisor named at creation is told with `ended {receipt, how}` (under the causal ledger) when a supervised activity breaks, runs out of budget or times out, and of nothing else; a child created under a supervisor reports to it. | keep | dup: 1 |
| turn_world | host | 23 | 458 | A world turn runs against the durable store, commits once, returns the retained receipt on retry, journals refusals, and reads respect a private object's policy. | split | ticks: 1; literal: 1; dup: 3 |
| usage_voice | host | 6 | 182 | Usage and hints speak as the speaker does: a resolved card (env) is named as typed, never env/<did>; a bad value is a blank in the hint; usage and inspect offer a reader only the actions the card's law and actions() leave them; a view is no spell. | split | literal: 4 |
| view_at | host | 2 | 71 | `viewAt {object, version}` rebuilds a past state from the journal under read authority and records the root at the object's current version; a future version is refused; a private object is denied. | fold:P-replay | - |
| view_data | host | 2 | 79 | A card reads another object's whole state or one field as Data (it may pass it on but not take it apart), the root recorded (field-level) and a private object denied. | delete | dup: 2 |
| view_derived | host | 4 | 87 | `viewDerived {object, view}` answers a view the package declares in views() as first-order Data under read authority with the root recorded; an undeclared definition is not a view; inspect lists declared views. | split | literal: 1; dup: 1 |
| world | host | 39 | 450 | The raw world-propose kernel: per-field edits, commit on current roots, laws, retry by identity, history paging, replay to the same head and a tampered journal refused by height. | split | dup: 5; literal: 1 |
| world_object | host | 5 | 153 | The world is an object: a message activity's yield addressed to `world` is answered by method name (write is the running object's, view and send), a method outside the protocol is refused noMethod, and the id `world` is reserved. | split | dup: 2; field: 1 |
| artifact_pins | objects | 1 | 127 | Every world module's source pin matches the recorded fixture and every top-level def still compiles (packet drift counted, not failed). | keep | - |
| card | objects | 4 | 85 | The card protocol on Lantern and Counter: a spell naming the card runs its action, an empty reply gets the card, prose to nobody gets nothing, a misfit spell is badSpell. | delete | literal: 1; dup: 2 |
| deal | objects | 5 | 141 | A Deal at rest, countersigned by every party, amends the target's law as caller; its own law keeps signatures insert-only and a withdrawal final; strangers, repeats and unposted signs are refused. | fold:S-deal | literal: 1 |
| interpret_text | objects | 8 | 146 | The garden fits the model's own words with Spell: a spell plants, `unclear: not addressed` is silence, a miss is asked again with its needs (escalate model), a second miss gives the needs card and a copy to escalateTo. | keep | dup: 1; literal: 1 |
| kinds | objects | 4 | 87 | The Kind object makes kinds; a kind makes instances under its law and head, and the bell and cistern bodies graft behaviour onto them. | fold:S-garden | fixture: 1; literal: 1 |
| laws | objects | 13 | 243 | The world's objects carry their laws in source: only owners change directories and admit anthology lines, a directory installed for someone else has no amendment clause, and Tide/Wake/Record predicates refuse what their code would even when the method skips its own check. | keep | literal: 1 |
| lenses | objects | 11 | 213 | An object's exposed fields are lenses: `set` writes one through its kind and its owner, `?` lists every form and lens, and strangers and bad values change nothing. | LATER keep | dup: 1; literal: 2 |
| mailbox | objects | 6 | 152 | An avatar follows another's outbox or watches any field and is told of changes; strangers cannot send as it, subscribe it or call its receiver; follows cap at 32, fanout reaches 32, inbox keeps the newest 64. | fold:S-watch | literal: 1; ticks: 1 |
| merge | objects | 3 | 80 | The page owner's `merge` reply checkpoints the garden page; anyone else's, a merge naming no post, prose containing 'merge', and a directly proposed forged checkpoint are all refused. | LATER fold:S-garden | literal: 1 |
| objects | objects | 23 | 504 | Checks the Bend library: one Context record, objects claim the Plans they perform, worst-case cards stay under 1,400 characters, nested effects are refused at compile time; also hosts the shared helper library every object test imports. | LATER split | literal: 6; ticks: 1; opaque: 2; fixture: 1 |
| page | objects | 3 | 100 | A garden publishes its page as an agentwiki post, one section per bell newest first capped at sixteen; door objects publish their card under the door word. | LATER fold:S-garden | literal: 1; dup: 1 |
| places | objects | 25 | 481 | Places, things and avatars are ordinary objects: moving, taking, offering and accepting, scoped commands, talk, copies and traces, each refused by name where it should be. | split | literal: 7; ticks: 2; dup: 1 |
| policy | objects | 20 | 546 | The interpretation policy is an object its owner teaches; prose to the garden suspends on it, the model's answer plants, asks first, or is refused by name, and the suspension machinery (capacity, rebase, replay) holds. | LATER split | literal: 4; dup: 3 |
| principal | objects | 6 | 101 | No argument can name another author, planter or sender: a forged who/by/author/from naming glm is refused or never seen, and the record names the turn's principal. | LATER keep | - |
| receive | objects | 16 | 312 | Garden.receive and Directory.receive answer spells with cards: needs named and held, refusals in one line, the menu once per principal, door words, spells passed to the card they name. | LATER split | literal: 6; dup: 2; ticks: 1 |
| relation_limits | objects | 5 | 90 | Every relation full at its declared limit and widest rows (Bell rains, Garden children, Directory greeted, Workshop held, Env buffer) is under 256 KiB of state and still takes a write. | LATER keep | - |
| scene | objects | 11 | 387 | A Scene keeps passages, presence and variables per reader: only an offered choice moves its reader, a refusal writes nothing, every bound (16 readers, 16 vars, 64 departures) is refused at its edge. | split | dup: 1; literal: 3 |
| spween | objects | 8 | 272 | A spween scene parses to a Scene seed (refusing weight, calls, has:, stray effects, dangling targets, over-long passages) and is made by posting one; guards, effects, END and the cooldown law hold. | split | literal: 2 |
| strangers | objects | 11 | 200 | A stranger's world-propose write, reprogram or amendment does none of what the object's own methods refuse them (codex objects review findings 1-8, plus garden, place and bell forgeries). | LATER keep | - |
| table | objects | 2 | 130 | Automatafl on commit-reveal seats: an opening round through the host (suspended reveal awaiting the rival's seal, lies and wrong seats refused) resolves to the pure game's result; a stranger cannot amend the table. | keep | literal: 1; dup: 1 |
| views | objects | 8 | 341 | Render with a point of view: the same state shows its owner, its parties and a stranger different cards (yours, events, notes, countersign spell) and names people by handle, never a raw DID. | LATER split | literal: 6; dup: 2 |
| wakes | objects | 25 | 562 | Env, Wake and Tide, the cards the town designed: senses owned by their DID, triggers only their owner changes, schedules re-arm, rules fire on rows and writes, a tide never ticks too soon. | LATER split | literal: 5; dup: 1 |
| workshop | objects | 13 | 247 | The workshop checks a fenced block or a target's source with diagnostics; a clean proposal reprograms the target under the target's own law, a stranger's is held for the owner to adopt, withdraw and the 12-held cap. | fold:S-workshop | literal: 3; opaque: 1; dup: 1 |
| bridge | transport | 44 | 723 | The bridge turns observed posts into turns in creation order, routes a reply by its nearest recorded ancestor only, drafts each offer once, never posts, and holds hashes out of drafts. | LATER split | wallclock: 1; opaque: 6; literal: 4; dup: 1 |
| genesis | transport | 7 | 230 | Genesis seeds the town once through a real hostd (every door resolves, the opener's handle shows, laws and pages), and the root menu is rendered from the directory's own state as the world moves. | LATER split | literal: 3; dup: 2 |
| hand | transport | 14 | 290 | The owner's /hand/ console: token-gated, drafts posted once with edited text and logged, skip/hold never post, a CLI over the same operations, served on a loopback listener only. | split | literal: 2; dup: 3 |
| hostd | transport | 15 | 276 | hostd is the one writer: a private socket, concurrent clients in one valid chain, one instance only, a killed host recovers the same receipts, heaps and stateless are separate, the sealed library, reconnect behaviour. | split | literal: 2; opaque: 3; dup: 1 |
| http | transport | 58 | 1039 | The agent API at /AGENTS.md and the browser pages over a real hostd: handle-claim login, turns and receipts, the REPL, private heaps, /play/, and the front's limits. | LATER split | literal: 9; dup: 6; opaque: 4; wallclock: 2 |
| hypermedia | transport | 21 | 489 | A stranger acts from the replies alone: every JSON reply carries _links, _actions come from the host's method table and forms, every error is a named envelope, and the front survives bursts, stalls and malformed input. | LATER split | wallclock: 2; literal: 6; opaque: 2; dup: 1 |
| library | transport | 6 | 92 | genesis shelves the library pages; anyone reads a page by name or by a word of what they said, a card's law with its readings, and only the owner shelves. | LATER split | literal: 2; opaque: 1; dup: 1 |
| model | transport | 27 | 332 | The model client and interpreter: replies parsed, each pending interpretation asked once and settled verbatim (failures included, the host retries them), accounts rotated, credentials never shown. | keep | literal: 6; fixture: 1; opaque: 1 |
| oauth | transport | 6 | 255 | Log in with delve.town against a fake PDS/PLC/authorization server: PAR with PKCE and DPoP, the nonce challenge, token exchange, tokens revoked and not stored, a wrong sub, late/replayed/other-browser state, and the client metadata document. | keep | literal: 1 |
| open | transport | 3 | 57 | deploy/open.py writes one bridge row per world and prints the start commands without starting anything. | keep | literal: 1; dup: 1 |
| publish | transport | 4 | 122 | A published page reaches the outbox as a draft exactly once, is recorded when posted, a section edit drafted before its page post later gets its replyTo, and a merge reply to the page post routes to the garden. | LATER fold:S-garden | - |
| repo | transport | 10 | 315 | The journal as a read-only AT Protocol repository over a real hostd: records by slug and CID agree with the host, a sync CAR block hashes to its CID under an independent DAG-CBOR decoder, private records stay private. | LATER keep | literal: 3 |
| spend | transport | 1 | 30 | The spend report totals one month of model calls at Haiku rates and prints the grant left. | keep | - |
| transport | transport | 45 | 608 | Observation, identity and posting: posts are classified and observed once and bounded; a handle is claimed only by posting a spoken word from the right account; replies are threaded and nothing is sent without the flag, even after a lost reply. | keep | literal: 4; fixture: 1; opaque: 1 |
| zulip | transport | 14 | 307 | The Zulip playtest transport against a fake Zulip and a real hostd: messages become observations, topics route as threads, no hourly cap applies, a lost send is adopted not repeated, the welcome is recorded. | split | literal: 2; opaque: 1; dup: 1 |
| hub | rehearsal | 29 | 752 | The directory hears the gate's hour from the archived posts: field lines plant, rains and chatter get nothing, the model's spell reaches the door, and the hub's quiet rules (one card an hour, only named words are read) hold. | LATER split | literal: 8; ticks: 1 |
| replay | rehearsal | 6 | 141 | The archived hour step by step on the host: glm plants a bell, two rains kept in admission order, the second cistern is refused requiredAbsence, the strike awaits the planting post, the anthology keeps lines pending until the keeper admits. | LATER fold:S-garden | fixture: 1; dup: 1 |
| suspension_size | rehearsal | 2 | 79 | A directory suspension journals only the changed part: nine prose replies keep the median suspension entry under 12 KB (one speaker) / 32 KB (nine speakers). | fold:P-archive | dup: 1 |
| derived_views | - | 3 | 88 | Garden's byColour counts bells by colour and Place's affordances lists its spells, read purely and then by another object through viewDerived. | LATER split | literal: 1 |
| pages | - | 8 | 218 | Every browser route is an HTML page in the theme, the plain-text view carries the same links and forms as the HTML, and JSON stays JSON for agents. | split | literal: 6 |
| relation_lib | - | 8 | 158 | world/lib/Relation.obend through the checker: key order as canonical bytes, fromList sort and dedupe, queries, merge join, and the Bend mirrors of insert/upsert/retract. | keep | ticks: 1 |
| ring_harvest | - | 2 | 52 | The rehearsal harvest script counts the front's access log by status class and reports 500s as the gate. | keep | - |
| spell | - | 35 | 352 | The spell grammar as the host's spell-parse reads it: last unquoted delvetalk line, field lines, slash forms, blocks, fences skipped, fitted to a form or refused by name, plus the Bend mirror of the spell line. | LATER keep | dup: 2 |
| theme | - | 9 | 130 | The theme without a browser: both palettes pass WCAG AA, the site carries the front's palette, every kind has its own mark, receipt fates are word plus icon, doors and spells are styled, the frog is one plate. | split | literal: 6 |
| world_protocol | - | 2 | 102 | An object in the message dialect compiles against World.obend, each protocol call lowers to one named world message, and the same object runs through the host (follow, bump, changed delivery, viewAt, viewDerived). | LATER delete | literal: 1 |

## After (lane tests2, on foundation f7865b0)

| | audit | pass 1 | pass 2 |
| --- | ---: | ---: | ---: |
| tests run | 1,285 | 1,008 | 663 |
| lines in `test_*.py` | 27,660 | 23,974 | 21,361 |
| wall time, hbox (`swarm-build`) | 70.0 s, load 20 | 48.4 s, load 20 | 104 s, load 37-40 |

Wall time is now the critical path of one class: `test_archive` runs `rehearsal/rehearse.py` over
the 1,763 posts (45 s at load 20, 104 s at load 40); the next slowest class takes 39 s. Every other
failure is a defect the properties found (below). How we know no behaviour went: each removed
test is named in its commit (b224238.., this lane's two deletion commits) with the property,
scenario or remaining test that asserts its claim; merged tests keep their assertions as table rows.

Tests are under half (663 of 1,285 run counted with inherited classes: 52%; 653 `def test_`).
Lines are not: 77%. What remains is mostly Bend fixture source the adversarial tests compile, and
the fixture backbone (`closure`, `record`, `label`, `nat`, `declared`, `Chain`, `garden_seed`,
`Reflection`, `get`, `rows`, `items`) that about eighty modules import from test_turn_world,
test_chain, test_reflection and test_replay. Halving lines needs step 5 below, which touches
`tests/host.py` (open on lane/rewrite3).

Defects found, reported, not fixed: methods without an input admit any argument (Avatar hold and
release, Env observe, Scene enter and leave, Tide tick; test_principal asserts the same admission
for Door.knock, Lantern.light, Place.enter, so one of the two is wrong once decided); on the
archive 54 interpretations not 43, three anthology lines of four, no planting recorded for glm's
bell (rehearse.py reads garden `children`, which the kind/bell cut renamed), a Workshop
publication draft of 1,444 characters; a second arrival under a new handle updates the registry
but not the Avatar's `handle` field.

## The plan

1. **Properties** (`test_properties`, layer properties): the town as genesis builds it, driven by a
   seeded generator (`DELVETALK_SEED`). `RandomHour`: eighty moves drawn from the archive's posts and
   the rehearsal's model answers, plantings, rains, rings, rows watches, workshop proposals,
   amendments, forks, clock ticks and interpretations; every refusal classed, every retry the
   retained receipt, every card within the clip and without a DID or hash; then reopen, reopen from
   a snapshot, and rerun the same requests on a second town: every state CID at every version, and
   the journal bytes, equal. `EveryMethod`: every public method of every object, as owner and
   stranger, with a well-typed value inside its form, one outside a form bound, and a malformed one;
   every undeclared helper `noMethod`; every card for three readers.
2. **The gate as a test** (`test_archive`, layer rehearsal): `rehearsal/rehearse.py` on the whole
   archive, asserting the section 10 hour and the recorded routing (43 interpretations, d02c60f).
3. **Scenarios** (`test_scenarios`, layer scenarios): one per arc through the spells a reply carries:
   a kind's bell watched, rained on, rung by its seventh rain; a garden planting; a workshop check,
   proposal held for the owner, refused to a stranger, adopted by the owner; a scene entered and
   chosen. The deal signed by two stays `test_deal` (every test in it is an attacker's move); the
   claim and the login stay `test_transport.Identity` and `test_oauth`.
4. **Deletions, this pass**: the seven delete verdicts outside `LATER` (`test_hints`, `test_items`,
   `test_list`, `test_view_data`, `test_derived_forms`, `test_card`, `test_located`), `test_kinds`
   (folded into the Bell scenario), and every flagged test in the files this pass may touch, except
   where the flagged test is a behaviour's only evidence (listed in the commit).
5. **Next** (needs `tests/host.py`, open on lane/rewrite3; and lane/kernel11's `test_conformance`,
   `test_stored`, `tests/conformance/`, deferred with `test_serve`): move the fixture backbone
   (`closure`, `record`, `label`, `nat`, `declared`, `Chain`, `garden_seed`, `Reflection`, `get`,
   `rows`, `items`) out of test_turn_world, test_chain, test_reflection and test_replay into
   `host.py`, so the test modules stop importing one another, and collapse test_canonical's and
   test_turn's private `Host` classes into it; then share one Bend fixture module per object kind
   instead of a source string per test file. That is where the remaining half of the lines is.
   Then decide the input-less-method defect and fix whichever of test_principal and
   EveryMethod is wrong.
