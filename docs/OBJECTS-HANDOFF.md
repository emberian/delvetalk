# Objects handoff

Written by the objects lanes (lane/objects4, then lane/objects5) for their successor. Everything here was
measured against the real checker and host; nothing is from memory of the design
documents. Run suites on hbox (`~/scratch/dt-foundation` keeps a built Linux binary):
rsync the worktree to `hbox:~/scratch/<lane>/` and run
`DELVETALK_OBEND=$HOME/scratch/dt-foundation/.lake/build/bin/delvetalk-obend python3 -W ignore -m tests.run <names>`.
For compile-only checks locally, copy `<foundation>/.lake/build/bin/delvetalk-obend` into the
worktree and set `DELVETALK_OBEND`; never run `lake`, never commit the binary.

## 1. Conventions as they are

An object is one file under `world/objects/`; it imports modules by basename (flat
names; `world/lib`, `world/lib/prelude`, `world/lib/document`, `world/lib/game` are all
the library).

* **State, Seed, seeded, initial.** `record State`, `record Seed` (or `type Seed = {}`),
  `defaultSeed()`, `seeded(seed) -> State`, `initial() = seeded(defaultSeed())`. The host's
  `create` does NOT call `seeded`: it lays the seed (a record naming some State fields)
  over `initial()`. `world-create` takes a whole State.
* **The card protocol** (`world/lib/Card.obend`). Every object, Counter included, has
  `render(state, context) -> Document` (the card as the reader in the context sees it; the
  host's `card {object}` and `world-card` pass the reader's Context; `Card.stranger()` is
  nobody's), `forms() -> Card.Forms`, `door()`, and `receive(state, input: Card.Heard,
  context)` with `Heard = {text, post}` (a turn's argument may carry more fields, such as
  the bridge's `slot`; the record reads these two). The usual receive is `Card.route(text, context, forms())`, `act` dispatched
  by action, anything else `Card.answer(routed, context, forms(),
  render(state, context))`.
* **Handles and the clock.** `Card.name(did, context)` shows the reader's own observed
  handle (`context.handle`, from the host's registry) and anyone else as `Card.handle`:
  never a raw DID, a long fragment is `…` and its last eight. A handle stored when the
  host knew it shows by `Card.shown`: a bell's planter, a rain's author, a Tide subscriber,
  the Anthology's owner (stored at each admission), a lantern's lighter, a door's opener and
  knockers, a Deal's signers and withdrawer, a Thing's holder, an Avatar note's author, and
  an Env's and a Wake's owner (seeded at arrival). Deadlines (Thing offers,
  the Tide's gap) compare `context.clock`, which only world-advance moves.
* **Reader-specific cards.** `Card.reads(principal, context)`, `Card.mine(principal,
  context)` (" (yours)"), `Card.stranger()`. A member sees more: an Env's events, a Wake's
  triggers and an Avatar's notes and follows are their owner's; a Deal shows a party
  its countersign spell; a Policy shows its owner how to teach; Garden reminds a reader
  of the proposal waiting for their yes; a Scene shows a present reader their passage; a
  Commons shows where the reader stands and which gates let them through.
* **Lenses and `set`/`?`** (Policy, Avatar, Garden confirm, Place and Thing name and
  description; Workshop has none and says so; `Card.answerLensedAs` for an object's own
  result type). `Form.Lens<E>.lens {field, form: Form.Kind, put: Form.Value -> E}`;
  an object exports `lenses()` and answers with `Card.answerLensed(routed,
  context, forms(), lenses(), guard, card)`: `delvetalk <card> set` plus one `<field>:
  <value>` line is judged against the kind and written through put (guard "" admits; a
  non-empty guard refuses by name first; the law judges the write); `delvetalk <card> ?`
  answers the usage card (forms, then lenses). Without lenses, `?` shows the forms and
  `set` says "Nothing here can be set." Lenses today: Policy (model, escalate, system),
  Avatar (handle). `Card.valueText/valueNatural` read a Value.
* **Spell names and shapes.** A card name is `[a-z0-9:/.-]+`, at most 160 bytes, so
  `env/did:plc:…` and an Avatar's DID are nameable; actions and fields stay `[a-z0-9-]+`;
  `?` is an action. On the delvetalk line fields follow the action separated by ` / `
  (the town's form) or commas. The spell is the post's LAST delvetalk line that is not
  quotation (indented four or by a tab; taken only if nothing else), `>` and fence lines
  are never spell lines and are skipped among the fields (rehearsal finding 1).
* **Interpretation, the Card default** (Garden, Directory). A card with a policy views it
  first (`Plan.view`; the Response's state type is `Policies.State`, which lives in
  `world/lib/Policies.obend` because Policy declares a law and cannot be imported) and asks
  with `Card.asking(utterance, forms, reference, policy, attempt, needs)`. `Card.fitting(text,
  forms)` reads the model's `replied {text}`: `hit {card, parsed}` (a spell fitting an
  offered form), `silent` (`unclear: not addressed` or empty), else `miss {needs}` (a spell
  that does not fit, `unclear: <need>`, words that are no spell: needs nil). A first miss is
  asked once more, the utterance plus `\n\nmissing: <needs>` and `model:` the policy's
  `escalate`; a second offers the needs card (no card when needs is nil) and, when the
  policy's `escalateTo` (lens `escalate-to`) names a principal, `Card.escalation`'s copy to
  it: "<handle> said: <utterance>; I could not fit it (<card>).". A host `unclear {needs}`
  (a failed model call, a JSON proposal that does not fit) is not retried. An activity
  composes only in tail position, so the object owns the loop (Directory answers a miss
  that says the action is not offered at once and does not ask again: with the usage card
  of a door whose form has an action resembling the miss, else "A bell's card takes rain:
  reply to the planting post" when a kind of card under a door takes it, else no door; `interpreted`/`readBack` in
  Garden, `interpreting`/`readBack` in Directory) and Card gives the Plans, the pure
  reading and `Card.unfit` for a card with no writes of its own. A read-only root that moves
  while the interpretation waits does not make the resumption stale.
* **Confirmation is per action** (objects5). `Policies.State.confirmFor` (default
  reprogram, amend, give, offer; the owner's `delvetalk policy confirm / action: plant /
  ask: yes|no`) names what an interpreted proposal waits for a yes before; `Card.confirms`.
  Garden keeps its own `confirmFor` (its `confirm` lens adds or drops plant) and asks when
  either names plant; Directory shows a confirmed action's spell back to the speaker
  instead of passing it on (sending it is the yes). Everything else runs at once and the
  receipt is the answer. Thing's give and offer take a Reference, so no door offers them
  to a model yet.
* **Completing a spell** (objects5). An unclear spell is held for its speaker (Garden's
  `Pending {principal, spell, needs}`; needs empty is a proposal waiting for yes); a reply
  that is only `name: value` lines (`Card.onlyFields`, fences allowed) is appended to the
  held spell (`Card.completed`) and judged again. Directory passes field-only lines whose
  first name is a field (not an action) of a door's form to that door as they are, so
  "colour: violet" under the hub reaches the garden holding glm's cistern.
* **Macros** (Policy `macros`, taught by the owner with `delvetalk policy macro / name: … /
  pattern: moth for {who} / expansion: garden plant / colour: violet / seed: a bell for
  {who}`; every field after the expansion joins it as ` / field: value`; a same-named macro
  is replaced; sixteen; a pattern must start with a word). Garden and Directory, having
  viewed the policy, check `Card.expanded(text, policy)` before the model: words compared
  exactly (a trailing `.!?` dropped), a `{hole}` takes the shortest run of one or more words
  that lets the rest match; a hit is dispatched as a typed spell (Garden: no confirm) with no
  interpret. Garden's `?` with a policy appends `Card.macroUsage`; the policy's card lists
  them. A literal brace in Bend source is `{{`/`}}` (interpolation).
* **Handed to the directory** (objects5). Quiet prose (Routed.quiet now carries {text,
  post}; objects route with `Card.routeHeard(input, …)`) is sent by Card's default
  (`Card.forwarded`; Garden without a policy too) to `directory` (`Card.directory`, the
  genesis id) as `receive {text, post}` under the speaker; the card still offers nothing.
  A turn some object started forwards nothing. Whether a handed-on reply reaches the model
  is the directory's: it keeps `words` (door labels and ids, form actions) and `fields`
  (form fields) learned by inspect when a door is added (every door is relearned) or by the
  first handed-on reply after a seeded genesis (writeOnce for anyone else), and reads with
  the model only prose that `Card.mentions` (a word, or a field as `name:`). The same check
  guards the directory's own reading of hub prose. At judgement the directory also reads
  the first object listed under each door (`objects {prefix}`, then inspect: a garden's
  bell gives "rain"), and a handed-on reply does not count its caller's family: the
  caller's own actions and fields, and the door it lives under with that door's. A card cannot
  `view directory` itself: a view answers in the card's own Response state type, which is
  not the directory's, so the hand-off costs a delivery turn but no model call. A door added
  before its object exists learns only its label and id. The directory reads a handed-on reply with
  no menu, its field lines as usual, and with a policy the model; the owner's handed-on
  replies are read too. A send, not a call: a call's result must fit the caller's Response
  R, which the directory's Heard does not.
* **An admitted act answers with its card** (objects5): a rain from a reply
  (`Bell.rainedCard`) and a submission (`Anthology.submittedCard`) offer the card as the
  write leaves it to the speaker, as Garden does when it plants; the direct `rain` and
  `submit` methods still answer only their count.
* **Link doors** (objects5): a Directory door whose `to` is nobody (genesis's STUDIO) answers
  its word with `<label>\n<description>` (the URL is in the description) and is skipped
  when field lines and the model look for forms.
* **Env fills** (objects5). `Env.receive {text, post}` from anyone but the owner (any
  non-empty text, never read as a spell, nothing offered) is taken in as `mention` (`Event` gained `handle`, the author's as the host
  knew it); the law admits that receive (kind 0, method receive, owner/handle/seen/
  subscribers unchanged). Arrival seeds `handle`, and the card reads "ENV of <handle>":
  the newest eight events, one line each (first line, 100 characters), "… and N more".
* **No hash in a card** (objects5). A card or offer cites an object as `<object> v<n>`
  (Workshop views its target, its Response's state type being Data, and says "Was: bell-1
  v1 / Now: bell-1 v2"); `tests/host.py` fails any host reply whose card or offer text
  contains `bafy`, in every suite.
* **What prose costs** (objects5, run 8). Spell.parse's one walk notes whether any line
  might be a `name:` field line (`notASpell {reason, fielded}`; a name of up to 16
  letters); Card and Directory call Spell.bare only then. `Card.blank` replaces
  `textSpan == textLength` (textLength costs the whole text). glm's 1,788-character reply
  costs a bell 19,601 ticks (was 999,861); the directory's reading of it about 200,000, all
  interpretation overhead of a per-word loop (`Card.mentions`: split at blanks once, words
  by length, a first-letter filter); a kernel word-set builtin would remove it. The newline
  scan is the floor: 6 ticks a scalar.
* **Block field values** (objects5): `field: <<DELIM` (1 to 32 of A-Z 0-9 _) takes the
  following lines up to one that is exactly DELIM, joined by newlines, no trailing newline;
  unclosed is refused by name ("the block <<BEND for source is never closed by a line
  BEND"). Workshop reads `source:` as its code (the root menu's `source: <<BEND`). A 4 KB
  block parses in 98,132 ticks (just under a bare run's 100,000); the 64-field parse went
  75,421 -> 79,583.
* **Held proposals** (objects5): a Workshop `propose` the target's law refuses is held as
  `{n, target, package, migration, proposer, proposerHandle}` (sixteen; a seventeenth drops
  the oldest with a card line); the card lists them; `adopt / n` runs the reprogram under
  the adopter, so the target's law admits only its owner ("Only the owner of bell-1 adopts
  #1 (refused owner)" otherwise); `withdraw / n` is the proposer's. Compile, program,
  packageBytes and migration refusals are not held.
* **Scoped resolution** (objects5): an Avatar's own principal's prose with no spell and no
  field lines starting with an action word names its object by the first word that is a
  thing lying in its place (its card's first line, then its id's last segment), else an
  object of that id (the doors: garden, rooms, play); the avatar `send`s the object
  `delvetalk <id> <action>` with the rest of the line in the form's first field (a send,
  not a call: the callee's result would have to fit the avatar's Response R). Two of a name
  are answered "Which one: …?"; `look` offers `Place.render` for the reader.
* **Hub and silence.** Directory passes a spell naming another card to its receive by
  call (its Response result is Data), greets each principal once, is silent to its
  owner, and answers a door word with that door's card. Garden ends with no offer for
  prose the model calls `not addressed`; it reads the model's text (`replied {text}`)
  with Spell. Tide answers subscribe and tick with its card.
* **publishPage** (objects5): `Card.publishPage(door().word, page)` performs `publish {page:
  <door word>, section: "", body}`; Garden (its own page), Scene, Table, Workshop and
  Anthology (the default page, rendered for nobody at the object) expose `publishPage`,
  and the host lists the publication (`world-publications`). The card and its usage name
  the object's id; the page is titled by the door word.
* **Pages.** An object with a page keeps `owner` and `pageCheckpoint`; `Card.isMerge`
  and `Card.merge` record the owner's `merge` reply (Garden does).
* **Laws that guard fields** read `owner: request.subject == new.owner or (request.kind
  == 0 and unchanged(…))`: without the kind, anyone's reprogram or amendment (which
  change no field) passes (Garden, Thing, Directory). An Env lives at `Events.envOf(did)` = `env/<did>`; one elsewhere refuses publish.
* **List edits by item.** No object writes an index: `amendItem {item, change}` and
  `removeItem {item}` address the first item with the same canonical bytes (`absentItem`
  when none). Find the stored item with `Lists.find`, then address it.
* **Composition.** An activity composes only in tail position; a reusable method takes
  `then: Result -> T`. No `else match`: put the match in its own def.
* **Payloads are Data.** Give the value where Data is expected (the compiler injects it);
  `Plans.nothing()` is the empty payload.
* **Idioms** (kernel handoff section 11; world/ uses them throughout since objects5). No
  `::<…>`: type arguments are inferred (a definition whose parameter appears in no
  argument, like the old `Lists.kept<T, U>`, needs them or a smaller signature). A
  self-write is `write {field: add n | set v | append x | remove i | removeItem x, …}`
  (amendItem, keep-only and computed Entries stay `Plan.write(...)`); a write's answer is
  bound with `let written(_) = perform(…)` and the block goes on. Forms are `form ACTION [as
  NAME]:` blocks (default name `ACTIONForm`). Strings are interpolated (`"{expr}"`, a
  literal brace `{{`); an `if` inside a string is a `let` first. Every law has a reading:
  `law owner "only …": …`.
* **Refusals are sums** (objects5). `Card.Refusal {clause, reading}` is the payload of
  `Card.Reply.refused` and `Card.Routed.refused`; a card shows `refused <clause>: <reading>`.
  The protocol's own clauses: otherCard, noAction, oneField, spell, notSettable, noField,
  notOwner (a lens guard, a merge), badValue, noPost. An object keeps a `sum Why` (one arm
  per refusal, payload what the reading needs), `why(w) -> String` (the reading), `clause(w)
  -> String` (the arm's name) and a `refused(w)`/`refusal(w)` builder: Thing, Place (its
  Done is Thing's and Avatar's), Garden (`world {clause}` keeps a host clause such as
  requiredAbsence), Tide, Wake, Deal, Policy. Scene, Commons, Avatar, Anthology and
  Appointments give a clause at each site (no Why sum yet); Directory's `Heard.refused`,
  Bell, Seat, Workshop's `Verdict` and the observers' `Card.Change` still carry `{reason}`.
* **Observers / mailbox.** `Card.observing` (16) and `Card.observingUpTo(…, cap)`;
  `Card.broadcast`. An Avatar's mailing list holds 32, the host's `sendsPerTurn` (a turn
  past it is refused whole, "turn exceeds the send capacity"); its inbox keeps 64.
* **Owners.** Scene and Table keep `owner` (the host fills a text `owner` from the creating
  principal when the seed names none) and `law owner "...": request.kind == 0 or
  request.subject == new.owner`. `world-amend` does not parse a law text with a reading
  ("law syntax"): amend with `law NAME: EXPR`.
* **Laws in source** are kept by the host; a lawful module cannot be imported by a
  creator, so lawful objects (Policy, Env, Wake, Tide, Deal, Table, Directory, Anthology,
  Commons) are made with world-create by their owner. The host prints a law fully
  parenthesised. `law(old, new, request)` Bend predicates run after the text admits a
  kind-0 write (Tide: self, tooSoon; Wake: owner); `tests/test_laws.py` shows them biting.
* **Layers through the host** (objects5): `tests/test_extend.py` LouderBell grafts
  `layer over ./Bell.obend` by the extend Plan, and a rain reply's card starts LOUDER.
* **Layers.** `world-reprogram {mode: extend}` with a module `type State = Super.State`
  overrides what it defines; `tests/test_layers.py` (Louder over Bell) keeps rain.

## 2. Limits found (measured)

* The closure cap is gone; Counter with Card runs 200 HTTP turns in 0.50 s on hbox
  (0.39 s bare). The REPL's `MAX_BODY` refuses Counter's closure with Card (413).
* Ticks: Bell card of 1,025 rains 76,106 (76,476 before its head was interpolated); spell parse of 64 fields 75,412 (dense 4,057 bytes 83,238); an Avatar send
  to 32 observers 5,213.
* An await only proves that some turn with that identity was admitted. A turn suspended
  on an object resumes refused `staleRoot` if anything wrote that object meanwhile,
  unless its writes are all keep/add/append (they now commute).
* `run` refuses variant arguments and recursive results: build in a probe module.
* A kernel hint can mislead: an unbalanced parenthesis is reported with "there is no
  Maybe builtin" or "definitions are `def name(x: T) -> U:`".

## 3. Objects

Counter, Garden, Bell, Cistern, Anthology (owner admits), Directory (owner adds and
removes), Door, Lantern, Loop, Place, Thing, Avatar (mailbox: subscribe, send,
unsubscribe; handle lens), Policy (owner law with `request.method`; lenses), Workshop
(check prints the checker's hint under its problem; inspect; propose), Env, Wake, Tide,
Appointments/Appointment, Deal, Seat and Table, Scene (passages and choices as data;
enter, choose, leave), Commons (places, paths, ways in, gates: open, members, object). Scene now has guards,
effect lists, END, `requires` and a cooldown (its Bend `law` predicate over context.clock,
with no law text), and makes scenes from ```spween blocks.

## 4. Open

* Place cannot declare a law while Thing and Avatar import it for its State and Done;
  moving those types to a library module (as Seats did) would let it.
* **Host:** `Plan.interpret` now carries `model` ("" = the policy's own); the host
  (`TurnLoop.interpretPlan`, `interpretationsReply`) ignores it, so a second attempt still
  goes to the policy's `model`. It should copy `model` into the pending item and send it in
  place of `policy.model` when non-empty.
* An addressee `slot` reaches receive but no object reads it yet.
* Scenes (objects5): `world/lib/Scenes.obend` is the data (Choice {label, to, effects,
  guard}, Effect set/add/sub, Clause, Seed {title, start, passages, cooldown, requires});
  `world/lib/Spween.obend` lowers spween to it (refusing weight, `~ call`, has: by name); a
  ```spween block posted to a Scene makes `<scene>/<id>` (id's `_` become `-`). A passage
  is still not editable once made; spween's `tags`, custom fields, floats and negative
  numbers are skipped or compared as text; parsing the well example costs about 79,000
  ticks with the test's summary (a scene near the 16 x 8 limit should be measured).
* Main's other capabilities (appointments' factories, editor and desks, exhibitions,
  library beyond the mailbox) remain to port, one object per commit.

## 5. What the previous handoff said that was wrong by now

* (objects5) `Heard = {text, post, slot}`: the record is `{text, post}`; tests pass `slot`
  and the host admits the extra field. "Delete test_interpret_text's foundation pin": there
  was none left.

* "About 256 top-level declarations per closure" and "Counter stays outside the
  protocol": the cap is gone; Counter joined.
* "Spell card names are `[a-z0-9-]+`": `[a-z0-9:/.-]+`.
* "Data may not sit in a State yet": it may.
* "the host does not run Bend predicates": it does, after the law text.
* "Directory and Anthology admit anyone's add/remove/admit": owner laws now.
* Policy's teaching card showed `delvetalk garden plant, seed: …`, which the grammar
  does not parse (the action would be `plant,`); it reads `plant seed: …` now.
* The host passes the reader's Context to `card` since foundation 9c306a5 (host5); the
  interim `renderFor` is renamed to `render(state, context)`.
