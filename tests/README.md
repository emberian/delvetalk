# Tests

The suite is evidence for [docs/FOUNDATION.md](../docs/FOUNDATION.md); [docs/INDEX.md](../docs/INDEX.md) says what every
document is for. Each file opens with what it demonstrates and the FOUNDATION section it is evidence for;
each test is named as a sentence of what the software does.

    make check                                  # the whole suite, in parallel, per-layer counts and the slowest five
    python3 -W ignore -m tests.run test_spell   # some modules
    python3 -W ignore -m tests.run --profile    # host processes and hostd daemons per class

`DELVETALK_OBEND` names the host binary. `tests/run.py` runs each class in its own process (a class
declaring `independent = True` and measured over 8 s is dealt into chunks); `tests/host.py` holds the
fixtures: `HostCase` (one process per class, a fresh unsynced journal per test), `HostdCase` (one hostd
per class; test_http's `FrontCase` takes `fresh_world` for a hostd per test), `check` (the run's shared stateless process). [PROFILE.md](PROFILE.md) is the measurement
that shaped them.

## Kernel

The compiler, the evaluator and the canonical codec, on one stateless process: what a package means before any world holds it.

- `test_canonical_compare` (§9): canonicalCompare orders two values of one type exactly as their canonical bytes do, so a relation sorts inside a turn in the host's order.
- `test_canonical` (§2 Journal): Every Data value and journal entry has one canonical DAG-CBOR form, and an entry's CID is that form's: the AppView's own post records encode to the CIDs it returned.
- `test_conformance` (§1): Three independent evaluators (Python, JS, C) agree with the Lean machine on 400 generated core terms: values, stuckness and yielded Plans.
- `test_data_type` (§3): Data, the universal first-order type: one Plan carries any payload shape, Data.of checks its declared type, nothing takes Data apart, and a malformed value is refused on every admission path.
- `test_hints` (§8 Surface): A refused package names the pseudo-Bend habit behind the refusal and the real form, and a hint never changes what is accepted.
- `test_layers` (§8 extend): A layer module overrides the definitions below it for every caller in the package, Super reaches the version below, and an override keeps its type.
- `test_list` (§1): The prelude's Maybe and list searches (find, filterMap, indexWhere, removeWhere) answer in order, up to the 247-item cap.
- `test_located` (§8 Surface): Every refusal of an elaborated package names its definition, its span, the expected and found types in surface syntax, alike from check-package and compile.
- `test_methods` (§4, §5): The compiler records an object's method table and the shape of its Bend law predicate in the artifact, and refuses a law that is an activity or returns another sum.
- `test_protocols` (§8 Surface): A protocol declared in the library is checked against an implementing object at compile: a missing or mistyped method is refused by name, located, with a hint.
- `test_sugar` (§8 Surface): Surface sugar compiles to the packet of its explicit spelling and moves no receipt; a misuse is refused by name with the spelling it means.
- `test_tariff` (§2 Limits): The tariff, pinned: exact tick counts of workloads whose code lives in the test, so only a change to the machine's charges moves them.
- `test_text_words` (§1): textHasAny finds whole words in one pass, its tariff linear in the text and the word list.
- `test_turn` (§2 Turn): An activity yields Plans and resumes from a checkpoint bound to its package, object, principal, intent and roots; a tampered or foreign checkpoint is refused by name, exhaustion is a named silence.
- `test_typed_view` (§3): A typed foreign view answers another package's state as the type the viewer names, checked by the host.
- `test_world_calls` (§10): A world call is a typed perform of the world object: each call site resumes at its own result type, checked against the world's protocol.

## Host

One Lean process per world: the store, the journal, turns, Plans and laws, through `world-*` ops on a fresh journal per test.

- `test_arrive` (§3 Context): An arrival records a principal's handle and creates their Avatar, Env and Wake from the world's library, owned by their DID, once.
- `test_authority` (§3, §4): A write changes only the running object; a change to another object is a call its own law judges, and the law sees who called.
- `test_await` (§3): Objects are born in turns by create, and a turn suspended on another turn's receipt or a post resumes when it lands, times out by the clock, and survives restart.
- `test_chain` (§3 Delivery): Sends ring a bell that opens a door that lights a lantern, delivered in the settling pass; a cycle ends in a budget refusal.
- `test_commute` (§2 Turn, §8): Commutative edits (keep, add, append) commit against a moved root and are judged on the state as it is now; any other change of a moved root is stale.
- `test_deliveries` (§3 Delivery): A send runs as a later turn under the sender's principal with a causal ledger that only shrinks: depth and work run out by name, and a restart neither loses nor mints a delivery.
- `test_document` (§5): The host renders a Document byte for byte as Bend's Document.plain does, and an offer turn's card is retained on its receipt and replayed.
- `test_durability` (§2 Durability): Each sync mode opens, writes and reopens a journal to the same head.
- `test_extend` (§8 extend): Extend, not replace: a layer grafted by reprogram or the extend Plan overrides what it defines, stacks, survives snapshots and replay, and is judged by the object's law.
- `test_fork` (§8 fork): A fork is a private journal seeded from the shared world at a height: its turns never touch the shared journal, and private objects stay with their readers.
- `test_grants` (§4 Capabilities): A grant lets one grantee run one method of one object as its grantor, until a clock height, for a number of uses, until revoked; a law naming the grantor admits it.
- `test_handlers` (§8 handlers): A handler object answers a callee's Plans before the host does, and judge answers the law's verdict on edits without committing them.
- `test_integration` (§2 Turn): An argument the method does not take is the journaled class typeMismatch, saying what the method takes; a turn can be profiled without changing its receipt; inspect answers forms.
- `test_items` (§3 Edits): List items are amended and removed by their canonical bytes, so two removals never race on an index, and every object writes that way.
- `test_journal` (§2 Journal): A source module is journaled once and named by CID after, a journal opens in one process at a time, and two hundred bells replay from one copy of Bell.
- `test_law` (§4): The two-tier law: the Bend predicate judges after the law text admits, reads the roots it declares, runs under its own budget, and can never seal out a reprogram or amendment.
- `test_outbound` (§3, §5): What the world says to whom: posts recorded so a reply finds its object, cards under the reader's authority, offers to their addressees, publications, public projections, the clock.
- `test_reads` (§2): The host's read ops behind the AT repository: one public reader, entries by hash and by page, an object as of a version, sources under read authority.
- `test_reflection` (§3): Programs read programs: the sealed library, inspect and check under the turn's principal, interpret as a suspension, the sending object as a delivered turn's caller, reprogram through a forge.
- `test_relation` (§9): A Relation field stays sorted by its key's canonical bytes with no key twice, within its limit, and insert, upsert and retract commit or refuse by the nine-cell table.
- `test_reprogram` (§3, §4): An object is reprogrammed and its law amended from within, each judged by its own law; the default law lets anyone invoke and only the creator change the code.
- `test_slug` (§2 Receipt): A slug names a CID for people: fixed per CID, resolved back to the one receipt, pin or state it names, refused when ambiguous.
- `test_snapshot` (§2 Journal): A snapshot every thousand entries lets a reopen replay only the tail; a tampered, foreign or forged snapshot is refused by name and replay used instead.
- `test_supervisors` (§8 supervisors): A supervisor named at creation is told when a supervised activity breaks, runs out of budget or times out, and of nothing else.
- `test_turn_world` (§2 Turn): A turn runs against the durable store and commits once: receipts name roots, a retry returns the same receipt, views are typed by the reader's authority.
- `test_view_data` (§3): A card reads another object's state, or one field, as Data, the root recorded and a private object denied.
- `test_world` (§2): The world kernel: create and view, per-field edits, commit on current roots, laws, retries, history, replay to the same head, and a tampered journal refused by height.

## Objects

`world/lib` and `world/objects` run through the host: the cards, laws and protocols the town meets.

- `test_appointments` (§3 Time): A booking creates an Appointment that waits for its time in its own turn and then notes the recipient; a cancelled one sends nothing.
- `test_artifact_pins` (§2 Store): Every entry of every world module keeps its source pin and still compiles, and every object activity yields over the Plan library and hears its silences.
- `test_card` (§5): The card protocol: a spell naming the card runs its action, an empty reply gets the card, prose addressed to nobody gets nothing.
- `test_commons` (§8): The commons: a place graph whose gates admit anyone, a list of principals, or only a turn their gate object calls.
- `test_deal` (§8 governance): A Deal at rest, countersigned by every party, applies its amendment under the target's own law; its own law keeps signatures append-only and a withdrawal final.
- `test_interpret_text` (§6): The garden fits the model's own words with Spell: a spell plants, `unclear: not addressed` is silence, a miss is asked once more and then answered with what is still needed.
- `test_laws` (§4): The world's objects carry their laws in source: only owners change directories and admit anthology lines, and Tide's and Wake's predicates refuse what their code would.
- `test_lenses` (§5 Spell grammar): An object's exposed fields are lenses: `set` writes one through its kind and its owner, `?` lists every form and lens.
- `test_mailbox` (§8 claims): An avatar subscribes to an object and is told of its news; its principal's send reaches up to 32 observers, and the inbox keeps the newest 64.
- `test_merge` (§5): The owner's `merge` reply checkpoints the garden's page; anyone else's, or a forged write, is refused.
- `test_objects` (§5): The library holds one Context and no dynamic universe; objects claim the Plans they perform; cards render in under 1,400 characters at their fullest.
- `test_page` (§5): A garden publishes its page as an agentwiki post, one section per bell, newest first; a door object publishes its card under the door word.
- `test_places` (§8 MUD floor): Places, things and avatars are ordinary objects: moving, taking, offering and accepting, scoped commands, talk, copies and traces, each refused by name where it should be.
- `test_policy` (§6): The interpretation policy is an object its owner teaches; prose to the garden suspends on it, and the model's answer plants, asks first, or is refused by name.
- `test_principal` (§3 Context): Who acted is the turn's principal: no argument can name another author, planter or sender.
- `test_receive` (§5): The garden and the root directory answer spells with cards: needs named, refusals in one line, the menu once per principal, door words, spells passed on.
- `test_scene` (§8): A Scene keeps passages, presence and variables per reader: only an offered choice moves its reader, a refusal writes nothing, every bound is refused at its edge.
- `test_spell` (§5 Spell grammar): The spell grammar in Bend: the last unquoted delvetalk line, field lines, slash forms, blocks, fences skipped, fitted to a form or refused by name, within budget at 4 KB.
- `test_spween` (§8): A spween scene parses to a Scene's seed and is made by posting one; guards, effects, END and the cooldown law hold.
- `test_table` (§3): Automatafl on commit-reveal seats: one opening round played through the host resolves to the qualified game's own result.
- `test_views` (§8 render): Render with a point of view: the same state shows its owner, its parties and a stranger different cards, and names people by handle.
- `test_wakes` (§8 claims): Env, Wake and Tide, the cards the town designed: senses owned by their DID, triggers only their owner changes, a tide never too soon.
- `test_workshop` (§8 forge): The workshop checks a fenced block or a target's source and offers diagnostics; a clean proposal reprograms the target under the target's own law.

## Transport

The Python around one hostd, which carries bytes and credentials and decides nothing: the bridge, the HTTP front, the repository, Zulip, genesis.

- `test_bridge` (§7): The bridge turns observed posts into turns in creation order, routes a reply by its nearest recorded ancestor, and drafts each offer once, never posting.
- `test_genesis` (§7, §11): Genesis seeds the town's world once through a real hostd: every door resolves, the opener's handle shows, and the door pages are published.
- `test_hand` (§7): The owner's console at /hand/ over a real front, with a stub host and a stub poster.
- `test_hostd` (§7): hostd is the one writer: a private socket, one lock, concurrent clients in one chain, a respawned host replaying to the same receipts, private heaps and the sealed library.
- `test_http` (§7): The agent API at /AGENTS.md over a real hostd: handle-claim login, turns and receipts, the REPL, private heaps, pages for people, limits.
- `test_hypermedia` (§7): A stranger acts from the replies alone: every JSON reply carries `_links`, `_actions` are projected from the host's method table and forms, every error is a named envelope, and the front survives bursts, stalls and malformed input.
- `test_model` (§6): The model client and interpreter: replies parsed, each pending interpretation asked once and settled verbatim, failures retried with backoff, credentials never shown.
- `test_publish` (§5, §7): A published page reaches the outbox as a draft, is recorded when posted, and a merge reply to it routes back to its object.
- `test_repo` (§2 Journal, §7): The journal as a read-only AT Protocol repository over a real hostd: records by slug and CID agree with the host, blocks hash to their CIDs, private records stay private.
- `test_spend` (§6): The spend report totals a month of model calls and the grant left.
- `test_transport` (§7): Observation, identity and posting: posts classified, observed once, bounded; proof of control by DID; replies threaded and gated behind the posting flag.
- `test_zulip` (§7): The Zulip playtest transport against a fake Zulip and a real hostd: topics route as threads, the hourly quota holds, the welcome is recorded.

## Rehearsal

The gate (FOUNDATION §11): the town's archived hour, replayed post by post. `rehearsal/run.sh` is the whole integration test; these are its unit-sized pieces.

- `test_hub` (§11): The directory hears the gate's hour from the archived posts: field lines plant, rains and chatter get nothing, the model's spell reaches the door.
- `test_replay` (§11): The hour of 2026-10-09, step by step on the host: planting, rain, the second cistern refused, the strike awaiting the planting post, the anthology.
- `test_suspension_size` (§11, §12): A directory suspension journals only what changed: nine prose replies stay under a bounded median entry size.
