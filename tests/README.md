# Tests

The suite is evidence for [docs/FOUNDATION.md](../docs/FOUNDATION.md); [docs/INDEX.md](../docs/INDEX.md) says what every
document is for. Each file opens with what it demonstrates and the FOUNDATION section it is evidence for;
each test is named as a sentence of what the software does.

    make check                                  # the whole suite, in parallel, per-layer counts and the slowest five
    python3 -W ignore -m tests.run test_spell   # some modules
    python3 -W ignore -m tests.run --profile    # host and serve processes per class

`DELVETALK_OBEND` names the host binary. `tests/run.py` runs each class in its own process (a class
declaring `independent = True` and measured over 8 s, or never measured, is dealt into chunks; `tests/timings.json`
holds the slow classes' times so a fresh checkout schedules them first, `--baseline` rewrites it). A run shares one
compile cache (`DELVETALK_COMPILE_CACHE`), the binary's pin and one genesis per town shape (`DELVETALK_TOWN_TEMPLATES`:
`tests/town.py` copies its journal and head snapshot into each town; `test_town_template` holds a copy to a fresh
genesis). `tests/host.py` holds the
fixtures: `HostCase` (one process per class, a fresh unsynced journal per test), `ServeCase` (one `serve`
per class, `host` its public socket and `root` the opener's; test_http's `FrontCase` takes `fresh_world` for a `serve` per test), `check` (the run's shared stateless process).
Every `serve` a test starts goes through `served(state, cleanup=...)` or `Town(..., cleanup=...)`: the test's
`addCleanup`/`addClassCleanup` receives the stop before serve starts. serve runs in its own process group with
its PID in `<state>/served.pid`; SIGTERM/SIGHUP, interpreter exit and (Linux) the parent-death signal stop it, and
the binary copy (`dt-obend-*`, its `owner.pid`) goes with its owner or with the next copy after an owner's SIGKILL.
`tests/wire.py` writes and reads Data on the wire (`nat`, `label`, `record`, `variant`, `relation`, `field`, `rows`) and holds the independent
DAG-CBOR encoder; `tests/bend.py` loads the world's modules as packages (`closure`, `declared`). [PROFILE.md](PROFILE.md) is the measurement
that shaped them.

## Properties and scenarios

The town as `deploy/genesis.py` builds it (`tests/town.py`), driven by what it will meet. `DELVETALK_SEED=<n>` replays a property run; a failure names its seed.

- `test_properties` (§8 invariants 4-7, 11, 12): `RandomHour`, two hundred moves drawn from the archive's posts and the rehearsal's model answers: every refusal classed, every retry the retained receipt, every card within the clip and without a DID or hash; reopening, and reopening from a snapshot, reproduce every state CID at every version, and the same requests make the same journal. `EveryMethod`: every public method of every object, as owner and stranger, with a well-typed value, one outside a form bound and a malformed one; undeclared names are `noMethod`.
- `test_rules` (OVERHAUL §5 step 3): a rule placed on a bell fires once at the write that makes it hold, under its placer, with the reply saying what it moved, and `rules` reads it back with the receipt; forty rules fire eight and journal the rest `unfired rulesPerCommit`; a chain ends four firings deep; a hole that reads nothing and a quieted owner are `unfired`; placing and taking off by the placer or owner, a name once, the card's law judging; a want posing, `wanted`, `unwanted` and `since`; where a write stands. Each survives a reopen.
- `test_reaction` (FOUNDATION §10): the five outcomes as rules on the town's own objects: the porch's third arrival knocks a door open, once a crossing; a bell tended twice by the clock rings; a record seals itself by `adopt` at its seventh line; the tide writes the weather only while a garden bell was tended within the day; a rung first step hangs a door to the second; a firing read back after a restart.
- `test_scenarios` (§5, §8): one scenario per arc through the spells a reply carries: a kind's bell watched, rained on and rung; a garden planting; a workshop proposal held for the owner and adopted; a scene entered and chosen.

## Kernel

The compiler, the evaluator and the canonical codec, on one stateless process: what a package means before any world holds it.

- `test_canonical` (§2 Journal): Every Data value and journal entry has one canonical DAG-CBOR form, and an entry's CID is that form's: the AppView's own post records encode to the CIDs it returned.
- `test_canonical_compare` (§9): canonicalCompare orders two values of one type exactly as their canonical bytes do, so a relation sorts inside a turn in the host's order.
- `test_package_bounds` (§2 Limits): A module at the program bound compiles, and every bound a package meets (module bytes, import scan, generic instances) refuses by name.
- `test_conformance` (§1): Three independent evaluators (Python, JS, C) agree with the Lean machine on 400 generated core terms: values, stuckness and yielded Plans.
- `test_data_type` (§3): Data, the universal first-order type: one Plan carries any payload shape, Data.of checks its declared type, nothing takes Data apart, and a malformed value is refused on every admission path.
- `test_layers` (§8 extend): A layer module overrides the definitions below it for every caller in the package, Super reaches the version below, and an override keeps its type.
- `test_methods` (§4, §5): The compiler records an object's method table and the shape of its Bend law predicate in the artifact, and refuses a law that is an activity or returns another sum.
- `test_protocols` (§8 Surface): A protocol declared in the library is checked against an implementing object at compile: a missing or mistyped method is refused by name, located, with a hint.
- `test_relation_lib` (§9): `world/lib/Relation.obend` through the real checker: key order as canonical bytes order it, `fromList`, the queries, the merge join, the Bend mirrors of the host's edits.
- `test_sugar` (§8 Surface): Surface sugar compiles to the packet of its explicit spelling and moves no receipt; a misuse is refused by name with the spelling it means.
- `test_tariff` (§2 Limits): The tariff, pinned: exact tick counts of workloads whose code lives in the test, so only a change to the machine's charges moves them.
- `test_stored` (§9 State model): A state's relation arrives as stored cells: a turn fetches and pays for only the rows it forces, and reports them by key to be recorded as roots.
- `test_text_words` (§1): textHasAny finds whole words in one pass, its tariff linear in the text and the word list.
- `test_turn` (§2 Turn): An activity yields Plans and resumes from a checkpoint bound to its package, object, principal, intent and roots; a tampered or foreign checkpoint is refused by name, exhaustion is a named silence.
- `test_world_calls` (§10): A world call is a typed perform of the world object: each call site resumes at its own result type, checked against the world's protocol.

## Host

One Lean process per world: the store, the journal, turns, Plans and laws, through `world-*` ops on a fresh journal per test.

- `test_arrive` (§3 Context): An arrival records a principal's handle and creates their Avatar from the world's library, owned by their DID, once.
- `test_authority` (§3, §4): A write changes only the running object; a change to another object is a call its own law judges, and the law sees who called.
- `test_await` (§3): Objects are born in turns by create, and a turn suspended on another turn's receipt or a post resumes when it lands, times out by the clock, and survives restart.
- `test_call_reading` (§3): A refused `call` carries the refusal's reading, so a directory handing a reply on can say why.
- `test_chain` (§3 Delivery): Sends ring a bell that opens a door that lights a lantern, delivered in the settling pass.
- `test_changed` (`changed`, `delvetalk objects ?`): `world.changed {since, prefix, after}` answers the newest change of each readable object, newest first, 64 a page; `delvetalk objects ?` lists the readable cards by prefix.
- `test_commute` (§2 Turn, §8): Commutative edits (keep, add, append) commit against a moved root and are judged on the state as it is now; any other change of a moved root is stale.
- `test_compile_cache` (§2 Journal): The compile caches are content-addressed, so a world opened after another in one process reuses what it compiled.
- `test_deliveries` (§3 Delivery): A send runs as a later turn under the sender's principal with a causal ledger that only shrinks: depth and work run out by name, and a restart neither loses nor mints a delivery.
- `test_document` (§5): The host renders a Document byte for byte as Bend's Document.plain does, and an offer turn's card is retained on its receipt and replayed.
- `test_durability` (§2 Durability): Each sync mode opens, writes and reopens a journal to the same head.
- `test_extend` (§8 extend): Extend, not replace: a layer grafted by reprogram or the extend Plan overrides what it defines, stacks, survives snapshots and replay, and is judged by the object's law.
- `test_fork` (§8 fork): A fork is a private journal seeded from the shared world at a height: its turns never touch the shared journal, and private objects stay with their readers.
- `test_form_bounds` (§5): A spell, and a direct turn, are judged by the card's own form bounds; a `source` field takes Bend up to 128 KiB (`Bounds.maxPackageBytes`).
- `test_grants` (§4 Capabilities): A grant lets one grantee run one method of one object as its grantor, until a clock height, for a number of uses, until revoked; a law naming the grantor admits it.
- `test_handlers` (§8 handlers): A handler object answers a callee's Plans before the host does, and judge answers the law's verdict on edits without committing them.
- `test_host_spell` (§5): The host's `spell-parse` answers every recorded input as the fixtures say: parse, bare and fit, with the refusal clause names.
- `test_input_post` (§3 Context): `inputOrigin.post` is the post a turn came from, kept when the host reads the reply as a spell.
- `test_inspect_reads` (§5): `world-inspect` lists per method what the law admits for the asking principal, and `world-objects {methods}` names each object's methods.
- `test_integration` (§2 Turn): An argument the method does not take is the journaled class typeMismatch, saying what the method takes; a turn can be profiled without changing its receipt; inspect answers forms.
- `test_interpret_object` (§6): An interpretation's proposal names the card whose form it fitted; up to three spells come back as `proposals {items}`.
- `test_interpret_quota` (§6): `interpretQuota` (default 48) interpretations a principal may start per clock hour; the next is the transient `quota` with `next`.
- `test_journal` (§2 Journal): A source module is journaled once and named by CID after, a journal opens in one process at a time, and two hundred bells replay from one copy of Bell.
- `test_journal_bound` (HOST-HANDOFF 5.124): The journal's byte bound is met at append, as a `capacity` receipt, not at the next restart.
- `test_law` (§4): The two-tier law: the Bend predicate judges after the law text admits, reads the roots it declares, runs under its own budget, and can never seal out a reprogram or amendment.
- `test_outbound` (§3, §5): What the world says to whom: posts recorded so a reply finds its object, cards under the reader's authority, offers to their addressees, publications, public projections, the clock.
- `test_post_reserve` (§3 Time): Posting reservations and model retries are host facts: a delve.town post reserved against `postQuota`, Zulip uncounted, a transient model failure journaled `attempted` with a backoff.
- `test_make` (§3): `make` creates an object from a resident's own source under the maker's authority and journals `madeFrom {object, pin, receipt}`; a compile failure is refused with the checker's reading.
- `test_public_methods` (§2): A method is public only when its package declares it; a helper is `noMethod` to a direct turn, a call or a send.
- `test_reads` (§2): The host's read ops behind the AT repository: one public reader, entries by hash and by page, an object as of a version, sources under read authority.
- `test_reach` (§6): Only words that reached a card go to the model: prose with no reach is `unclear: not addressed` at once, a stated reach is checked by the host and journaled, a handed-on reply keeps its reach.
- `test_reflection` (§3): Programs read programs: the sealed library, inspect and check under the turn's principal, interpret as a suspension, the sending object as a delivered turn's caller, reprogram through a forge.
- `test_relation_limits` (§9 scale rule): every relation full at its widest rows is under 256 KiB and still takes a write.
- `test_relation` (§9): A Relation field stays sorted by its key's canonical bytes with no key twice, within its limit, and insert, upsert and retract commit or refuse by the nine-cell table.
- `test_reprogram` (§3, §4): An object is reprogrammed and its law amended from within, each judged by its own law; the default law lets anyone invoke and only the creator change the code.
- `test_replay_edition` (§2 Journal): A journal names the replay edition it was written under, and a host of another edition refuses it by name before replaying.
- `test_root` (ROOT §1, §2): The opener's root and moderation acts, journaled, judged on the root socket only.
- `test_slug` (§2 Receipt): A slug names a CID for people: fixed per CID, resolved back to the one receipt, pin or state it names, refused when ambiguous.
- `test_snapshot` (§2 Journal): A snapshot every thousand entries lets a reopen replay only the tail; a tampered, foreign or forged snapshot is refused by name and replay used instead.
- `test_spell_turns` (§5): A reply to a message-dialect card is parsed by the host and runs the method it names with the typed argument; a misfit is `badSpell`.
- `test_sum_words` (§5): A text word for a closed sum of empty cases at the boundary names the case.
- `test_supervisors` (§8 supervisors): A supervisor named at creation is told when a supervised activity breaks, runs out of budget or times out, and of nothing else.
- `test_turn_world` (§2 Turn): A turn runs against the durable store and commits once: receipts name roots, a retry returns the same receipt, views are typed by the reader's authority.
- `test_usage_voice` (§8 Voice): Usage and hints name a card as the speaker wrote it and show a bad value as a blank.
- `test_view_at` (§9): `viewAt {object, version}` rebuilds a past state from the journal under read authority, the root at the current version.
- `test_view_derived` (§9): `viewDerived {object, view}` answers a declared view as first-order Data under read authority; an undeclared one is refused by name.
- `test_world` (§2): The world kernel: create and view, per-field edits, commit on current roots, laws, retries, history, replay to the same head, and a tampered journal refused by height.
- `test_world_object` (§3): The world as an object: a yield is answered by the method's name, each call site at its own result type.

## Objects

`world/lib` and `world/objects` run through the host: the cards, laws and protocols the town meets.

- `test_artifact_pins` (§2 Store): Every entry of every world module keeps its source pin and still compiles, and every object activity yields over the Plan library and hears its silences.
- `test_deal` (§8 governance): A Deal at rest, countersigned by every party, applies its amendment under the target's own law; its own law keeps signatures append-only and a withdrawal final.
- `test_derived_views` (§9): Garden's `byColour`, read by another object with `viewDerived`.
- `test_interpret_text` (§6): The garden fits the model's own words with Spell: a spell plants, `unclear: not addressed` is silence, a miss is asked once more and then answered with what is still needed.
- `test_laws` (§4): The world's objects carry their laws in source: only owners change directories and admit anthology lines, and Tide's and Wake's predicates refuse what their code would.
- `test_kinds` (§8 extend): `kinds` makes a kind, a kind makes an instance of its package under its law, and a kind with a body grafts it on each instance.
- `test_lenses` (§5 Spell grammar): An object's exposed fields are lenses: `set` writes one through its kind and its owner, `?` lists every form and lens.
- `test_mailbox` (§8 claims): A post that mentions an avatar's resident is a note from its author and offers nothing; the principal marks the entry it has read through; the inbox keeps the newest 64.
- `test_objects` (§5): The library holds one Context and no dynamic universe; objects claim the Plans they perform; cards render in under 1,400 characters at their fullest.
- `test_rooms` (§8 MUD floor): Rooms, things and avatars are ordinary objects (a room is a record with the room's body, world/bodies/room.obend): entering, leaving, choosing, talking, taking and putting down, offering and accepting, scoped commands and copies, each refused by name where it should be.
- `test_policy` (§6): The interpretation policy is an object its owner teaches; prose to the garden suspends on it, and the model's answer plants, asks first, or is refused by name.
- `test_principal` (§3 Context): Who acted is the turn's principal: no argument can name another author, planter or sender.
- `test_receive` (§5): The garden and the root directory answer spells with cards: needs named, refusals in one line, the menu once per principal, door words, spells passed on.
- `test_scene` (§8): A room with passages keeps presence and variables per reader: only an offered choice moves its reader, a refusal writes nothing, every bound is refused at its edge.
- `test_spell` (§5 Spell grammar): The spell grammar as the host's `spell-parse` reads it: the last unquoted delvetalk line, field lines, slash forms, blocks, fences skipped, fitted to a form or refused by name, within budget at 4 KB.
- `test_spween` (§8): A spween scene parses to a Scene's seed and is made by posting one; guards, effects, END and the cooldown law hold.
- `test_strangers` (§4): The review's objects findings 1 to 8: a stranger's proposed write, reprogram or amendment does none of what the object's own methods refuse them.
- `test_table` (§3): Automatafl on commit-reveal seats: one opening round played through the host resolves to the qualified game's own result.
- `test_views` (§8 render): Render with a point of view: the same state shows its owner, its parties and a stranger different cards, and names people by handle.
- `test_workshop` (§8 forge): The workshop checks a fenced block or a target's source and offers diagnostics; a clean proposal reprograms the target under the target's own law.

## Transport

The Python around one `serve`, which carries bytes and credentials and decides nothing: the bridge, the HTTP front, the repository, Zulip, genesis.

- `test_bridge` (§7): The bridge turns observed posts into turns in creation order, routes a reply by its nearest recorded ancestor, and drafts each offer once, never posting.
- `test_genesis` (§7, §11): Genesis seeds the town's world once through a real `serve`'s root socket: every door resolves, the opener's handle shows, and the door pages are published.
- `test_town_template` (harness): A town copied from the run's genesis template (tests/town.py) is a fresh genesis: journal bytes, every object's state CID at every version, status, what waits.
- `test_hand` (§7): The owner's console at /hand/ over a real front, with a stub host and a stub poster.
- `test_root_console` (ROOT §1.6, §2.3): The hand's root console and moderation verbs, each from the CLI and the console, with a stub host and a live `serve`.
- `test_serve` (§7): `delvetalk-obend serve` is the one writer of a directory of worlds: two private sockets, one lock, concurrent clients in one chain, a restart replaying to the same receipts, named worlds, scratch worlds, the sealed library, and the opener and root ops on the root socket only.
- `test_http` (§7): The agent API at /AGENTS.md over a real `serve`: handle-claim login, turns and receipts, the REPL, scratch worlds, pages for people, limits.
- `test_hypermedia` (§7): A stranger acts from the replies alone: every JSON reply carries `_links`, `_actions` are projected from the host's method table and forms, every error is a named envelope, and the front survives bursts, stalls and malformed input.
- `test_model` (§6): The model client and interpreter: replies parsed, each pending interpretation asked once and settled verbatim, failures retried with backoff, credentials never shown.
- `test_oauth` (§7 Authentication): Log in with delve.town against a fake PDS and authorization server over loopback: PAR with PKCE and DPoP, the nonce, a wrong `sub`, a late or replayed state.
- `test_pages` (§7): Every route a browser reaches is a page in the theme; JSON stays JSON for agents.
- `test_publish` (§5, §7): A published page reaches the outbox as a draft, is recorded when posted, and a merge reply to it routes back to its object.
- `test_repo` (§2 Journal, §7): The journal as a read-only AT Protocol repository over a real `serve`: records by slug and CID agree with the host, blocks hash to their CIDs, private records stay private.
- `test_ring_harvest` (§11): `deploy/ring/harvest.py` reads the front's access log.
- `test_open` (FEDERATION §7): `python3 -m transport open` writes one bridge row per world, starting nothing; the world's bridge reads it.
- `test_pull_backups` (OPERATIONS §b): `deploy/pull-backups.sh` keeps the pulled tarballs 7 days whole, 56 days daily, months forever.
- `test_watch` (OPERATIONS §b): `python3 -m transport watch` probes against the thresholds, one line per crossed condition, six hours between two lines for one condition.
- `test_spend` (§6): `hand spend` totals a month of model calls and the grant left.
- `test_theme` (site): Both palettes pass WCAG AA, the site carries the front's palette, a receipt's fate is a word and an icon.
- `test_transport` (§7): Observation, identity and posting: posts classified, observed once, bounded; a handle claimed by a posted word; replies threaded and gated behind the posting flag.
- `test_zulip` (§7): The Zulip playtest transport against a fake Zulip and a real `serve`: topics route as threads, no hourly cap applies (delve.town's quota is not Zulip's), the welcome (`zulip-welcome.txt`) is recorded.

## Rehearsal

The gate (FOUNDATION §11): the town's archived hour, replayed post by post. `rehearsal/run.sh` is the whole integration test; these are its unit-sized pieces.

- `test_hub` (§11): The directory hears the gate's hour from the archived posts: field lines plant, rains and chatter get nothing, the model's spell reaches the door.
- `test_suspension_size` (§11, §12): A directory suspension journals only what changed: nine prose replies stay under a bounded median entry size.
- `test_archive` (§11): `rehearsal/rehearse.py` over the whole archive: the section 10 hour and the recorded routing (43 interpretations).
