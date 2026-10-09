# Objects handoff

Written by the objects lane for its successor. Everything here was measured or hit
against the real checker; nothing is from memory of the design documents. The
checker is `delvetalk-obend` (never run `lake`; copy the binary into the worktree
and set `DELVETALK_OBEND`).

## 1. Conventions as they actually are

An object is one file under `world/objects/`, imports `./Name.obend` by basename
(modules are flat; the name must be supplied earlier in the same job).

* **State, Seed, seeded.** `record State`, `record Seed` (or `type Seed = {}`),
  `defaultSeed() -> Seed`, `seeded(seed: Seed) -> State`,
  `initial() -> State = seeded(defaultSeed())`. A creator supplies a Seed; the
  child's `seeded` makes its State. Tests still create with the full state under
  entry `initial`; the host will move to `seeded`.
* **render / card.** `render(state) -> Document` (pure) and
  `card(state) -> String = Document.plain(render(state))`. A pure *method* must
  return the state record in the host, so a card is shown by an activity
  `describe` that performs `offer {to: "", document: render(state)}`.
* **Method signature.** `(state, [input,] context: Abi.Context)`, in that order.
  Input is a record. Activities return `Activity<Plan, Response, T>` with `T` a
  typed sum or Bool/Nat; every refusal path is a typed sum, never a silent default.
* **receive.** Cards that hear the town take `receive {text, who, post}`
  (`record Heard`). `post` is the post uri: it is the intent of the planting slot a
  Bell's strike later awaits, and a method cannot see its own turn identity. Garden,
  Directory and Workshop all take the same three fields; the bridge must send all.
* **One Edits record** per object, one field per state field you edit, each
  `Plans.Edit<T, D>` (scalars) or `Plans.Entries<D, U>` (lists). Omitting fields is
  fine. `keep()` helper builds all-keep; use `extend(keep(), {field: ...})`.
* **Plan/Response.** `type Plan = Plans.Plan<Edits, A>`,
  `type Response = Plans.Response<S, R>`. S is the state type of the object you
  `view` (own state if you view nothing; Thing/Avatar use `Place.State`, Garden uses
  `Policy.State`). R is the result type of what you `call` (all place/avatar calls
  answer `Place.Done`). `A` is ONE type for every call, send and create the object
  makes: all argument records must have the same shape, which is why Place.Handling
  `{thing, by}` is shared by take/put/hold/release. A creator of several kinds
  (Garden) makes `A` a sum `Child` with one constructor per package (lower case,
  the host unwraps the one `package` names).
* **amend replaces.** `Entries.amend {index, change}` stores `change` as the item,
  so U equals the item type (Anthology.admit rewrites the whole proposal).
* **Writes are staged**: `write` is always answered `written`; the law decides at
  commit and a refusal ends the whole turn. No `case refused` after a write (dead
  code). `create`, `call`, `view` can still answer refused/denied.
* **References.** `Plans.self(context)`, `Plans.nobody()`, `Plans.same`,
  `Plans.indexOf`. World `""` means the running world.
* **Avatar id = principal** (the DID string). `Thing.give` compares the holder to
  `{world: context.world, object: context.principal}`.
* **`who` arguments are still there** (law reads `request.subject`); the successor
  removes them now that Context carries `caller`/`intent`/`height`.
* Nesting limit: a list in state is a cons chain; the host bounds data depth, the
  248th item is refused `typeMismatch`, so **247 is the most any list field holds**
  and `world-create` refuses seeds with ~64-deep lists (`response nesting
  capacity`; stock by turns instead).

## 2. Library modules

* `lib/Plan.obend`: `Reference`, `Edit`, `Entries` (keep/append/amend/remove),
  `Slot`, `Outcome`, `Receipt`, `Interpret`, `Offering {to, document}`, `Plan<E,A>`
  (view write call send create await interpret offer publish reprogram amend
  inspect check), `Response<S,R>` (viewed denied written refused returned delivery
  created reply unknown timedOut broken proposal unclear offered published
  reprogrammed amended inspected checked), helpers above. Header documents the Seed
  rule and staged writes.
* `lib/Form.obend`: `Names`, `Kind` (text/natural/choice), `Field`, `Fields`,
  `Form {card, action, fields}`. Split out of Spell so Plan can carry forms.
* `lib/Spell.obend`: `parse(text) -> Parsed` (`spell | notASpell`), `fit(parsed,
  form) -> Fit` (`proposal | unclear | refused`), `valueOf`, `joined`, `Entry/Value`.
  Grammar: skips every line before the first `delvetalk` line; `# ` and blank lines
  ignored; stops at `---`; fields `name: value`; one-line form
  `delvetalk card action a: x, b: y` (a comma continues a value unless what follows
  looks like `name:`). Field names are NOT validated at parse (78 ticks/scalar);
  fit refuses them as unknown. Naturals are canonical decimals, at most 18 digits.
* `lib/document/Document.obend`: `Document` sum, `text/concat/quote`, `plain`
  (flatten once + pairwise join, ~n log n), `size` (linear), `lines` (split on
  newline without growing accumulators), `Names`, `Documents`.
* `lib/prelude/Abi.obend`: `Context {world, object, principal, ...}`; `List.obend`:
  `List<T>` and traversals. Encounter*, examples: old, unused by objects.

Checker refusals that shaped them:
* Generic **records** do not parse (`unsupported Objective Bend declaration`):
  only generic sums. So Write/Call/Send/Create are inline sum payloads.
* **Recursion in Plans/Responses** (List, Document) was refused with the bare
  `the checker refused the front end's typed packet` (stage objective-typed-check)
  until the kernel change; now admitted. Early files still carry its workarounds'
  comments only in git history.
* **Phantom type arguments** need explicit instantiation:
  `Plans.Edit::<Bool, {}>.keep({})`, `Lists.List::<T>.nil()`.
* `sum match needs a resolved variant type`: a `match` whose only arm is `case _`,
  or `let x = if ... activity`. Put activities in `match perform(...)` arms or
  tail `if`; an activity in an `if` *condition* gives the bare typed-packet refusal.
* Named refusals (all asserted in `test_objects.Refusals`): effect-in-field,
  effect-in-payload, effect-in-plan, effect-as-argument, effect-in-let,
  perform-outside-activity, nullary-activity (needs a parameter).
* Multi-line `if/else if` chains do not parse: keep them on one line or split into
  helper defs. Deep `textConcat` nests easily lose a paren: use `let`s.
* **8 KiB REPL module cap** (`transport/http.py` MAX_SOURCE): a library module over
  8 KB makes any closure that includes it unusable through the REPL (`413`).
  Spell is ~11.8 KB, so nothing small (Counter) may import it, which is why Plan
  imports Form, not Spell. Keep Plan, Form, List, Abi small.
* The run op refuses variant arguments and recursive results; see the probe trick.

## 3. Objects (one line each; open ends)

* **Counter**: `bump` adds one. (reference activity.)
* **Garden**: `plant`/`sow` create a Bell; `cistern` creates a Cistern; `receive`
  parses, fits `plantForm`, plants, else interprets via `policy`, always offers a
  reply card. Open: `confirming` has no follow-up, a "yes" reply needs a pending
  proposal in state; `plant` still takes `post`; Child sum vs "A = Bell.Seed".
* **Bell**: rains (append), `ring` (write rung + send open to `door`), `strike`
  awaits `state.planting` (Slot written from the seed by Garden). Open: `strike`
  untested until the host's `await` merges; 1,025 rains cannot exist (247 cap).
* **Cistern**: `retain {receipt}` appends a Receipt. **Anthology**: `submit`,
  `admit` (rewrites the proposal). **Directory**: root menu, `add`/`remove`,
  `receive`, `describe`. **Lantern/Door/Loop**: the send chain; Loop cycles until
  the ledger's budgetExhausted.
* **Place**: enter/leave/take/put on `present`/`things` with `remove`; `describe`.
  **Thing**: acquire/drop/give via place and avatar calls; `inspect`.
  **Avatar** (Mover folded in): `move` (view, leave, enter, write `at`), `arrive`,
  `note`, `hold`/`release` (idempotent, never refuse), `describe`. Mover.holding is
  gone: `Avatar.holding` is written by `hold`/`release`. The recipient of a `give`
  learns through a note written by `hold` (a call, not a `send`: A has one shape).
* **Policy**: the interpretation policy (teach/define/setModel/describe, pure
  `prompt`). **Workshop**: `check`, `propose` (inspect, check, reprogram),
  `receive` (fenced obend block + spell). Open: host-dependent paths below.

## 4. Test harness

* `tests/host.py`: shared host per test class (`HostCase`), fresh temp journal per
  test; `check()` serves stateless compile/run with memoized compiles; the binary
  is copied once per run. Set `DELVETALK_OBEND` to your own copy so rebuilds elsewhere
  never race you. `python3 -W ignore -m tests.run [names]` runs everything in
  parallel classes (`make check`); a single suite: `python3 -m unittest tests.x`.
* Build worlds with `Chain` (tests/test_chain.py: `make`, `state`, `turn`).
* **Probe-module trick**: `run` refuses variants as arguments and recursive results
  (`variant arguments are not in the package execution profile`, `package result
  must have first-order data type`). Compile your module list plus a final
  `Probe` module that builds the list/sum in Bend and returns a String or Nat
  (see `test_objects.BELL_PROBE`, `test_spell.PROBE`, `test_policy.PROBE`).
  `run` has a 100,000-tick default; pass `limits={"ticks": "1000000"}` (the host's
  turn budget) to measure larger costs.
* **Expected failures waiting on the host**, with exact messages:
  * `plan not supported: create` (test_replay steps 1 and 3; test_receive planted
    card test),
  * `plan not supported: await` (test_replay step 5, Bell.strike),
  * `plan not supported: interpret` (test_policy fall-through x3),
  * `plan not supported: check` and `plan not supported: inspect`
    (test_workshop x5; check is the first plan of block checks, inspect of
    target/propose paths).
  Each flips to "unexpected success": delete the decorator then.

## 5. Tick costs and expensive idioms (measured)

* Text tariff: `textBreak/Span` 2*(alphabet+2) per scalar examined; `textTake/Drop`
  2*min(size, 4*n) (about 8 per scalar!); `textConcat` 1+2*bytes of both inputs;
  `textLength` 1+bytes. So a field-line scalar costs about 21.6 ticks (break 6, take 8,
  drop 8) plus ~400 ticks of fixed work per line.
* **64-field parse**: a 4,096-byte reply with 64 fields and a `---` rule parses in
  97,355 ticks (just under the 100,000 run default); all-field-lines 4,057 bytes
  needs 113,942. Bytes after `---` cost nothing. Do not validate names at parse.
* **Never walk characters** recursively over a whole text, and never fold
  `textConcat` into a growing accumulator (quadratic): flatten leaves once and join
  pairwise (`Document.joinAll`, ~n log n) or split with `Document.lines`.
* `Document.plain` over 256 leaves: 72,085 ticks (was 555,890 with an accumulating
  fold). Bell with 1,025 rains: `Document.size` 316,764; `plain` 848,680;
  `lines` 617,660 (all moot given the 247 list cap). A Document of N lines should be
  a sequence of one text leaf per line (built with `map`), not one concatenation.
* Building a one-text-leaf-per-item card is ~300 ticks per item. Avatar with 247
  notes: describe turn 42,363 ticks. Place with 64 things: 13,728.
* Policy prompt with 64 examples: 208,606 ticks (includes making them). 32 KiB fenced
  block extraction (break+take+drop ~22/scalar): 426,751.
* `natText(n)` cost grows with n; use constant strings in large probes.

## 6. What I would do next

1. Drop `who`/`by` arguments where Context now carries the principal; keep `by` only
   where the argument is a *reference to another object* (Place.take's holder).
   Re-seed tests with the new Context fields.
2. Garden "yes": add `pending: Entries<Pending {who, spell}>` to Garden's state;
   `confirming` appends; `receive` of `yes` by the same `who` plants the stored
   spell, anything else replaces it. Cap at one per `who`.
3. Switch tests and the bridge to `seeded` seeds; delete full-state creates.
4. When the host lands create/await/interpret/check/inspect, remove the expected-
   failure decorators (section 4) and add the replay assertions that were blocked.
5. Decide Garden's A: sum `Child` (host unwraps by package) vs splitting cistern
   creation into its own creator so A is literally Bell's Seed.
6. Port the remaining capabilities one at a time as objects with a `receive` and a
   form (rooms, conversations, table); keep each module under 8 KB and each list
   under the 247 cap (page long lists across objects).
