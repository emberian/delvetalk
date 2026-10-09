# Source-authored Spween handlers

`scene/handlers.py` compiles a pinned Spween scene into ordinary Objective Bend
source. It installs a native typed object with `start` and `choose` methods and a
computed menu. `Handler.obend` is executable source, not a Python callback registry.
The explicit profile is **`spween-obend-handlers-i64-v1`**. Existing
`spween-scene-i64-v1/v2` retain their fixed membership and call-batch semantics.

```sh
python3 scene/handlers.py protocols/spween-handlers/repair.scene \
  --handler protocols/spween-handlers/Handler.obend > /tmp/repair-bundle.json
```

The result's `protocol` is an ordinary `delvetalk-local-v1` protocol for the
`compiled` host. Install it through the existing desk/world workflow. A fresh
object has not run entry effects: invoke `start` with `{}` exactly once, then
`choose` with `{"choice": 0}` for a passage-local choice index. Use the existing
room/projection menu and exact-root action factories. The example repairs a moth,
sets `work` to ten inside its handler, increments it in the next scene effect,
and exposes the release choice only while the mutable inventory holds the moth
and `work == 11`.

## One typed relation

The compiler supplies `Kernel` and generates `Scene`; the author explicitly
supplies `Handler`, optionally preceded by supporting modules. Imports resolve
only in that ordered package. `compile_source(source, handler_modules=[...])`
accepts exact `{name, source}` records, requires the last module to be `Handler`,
and reserves `Kernel`/`Scene`. Native parsing, type checking and execution own
meaning. Python emits source and frames the native protocol.

The handler ABI is ordinary source definitions:

| Export | Type/meaning |
|---|---|
| `State` | Author's typed handler state; may contain recursive collections. |
| `initial()` | Initial `State`. |
| `get_var(state, name)` | `Kernel.Value`, missing variables conventionally Null. |
| `set_var(state, name, value)` | New `State`. |
| `has(state, category, key)` | Current Bool membership. |
| `begin(state)` | `Step` with a fresh emission accumulator. |
| `call(step, name, args, context)` | New `Step`; synchronous local source behavior. |
| `Slots` | The native four-slot emission record described below. |
| `Step` | `{accepted: Bool, reason: String, state: State, emissions: Slots}`. |

`call` receives the actual host `Context` including object/principal and input
origin. It gains no additional authority. `get_var`, `set_var` and `has` compose
with the same handler state as `call`; there is no mirrored inventory in the
renderer. A supplied handler defines its own behavior, including custom state,
argument checks, access rules and refusal reasons. The example closes unknown
call names and wrong argument counts. It exports useful ordinary helper functions
for variables, membership, integer arithmetic and emission accumulation; these
are reusable source, not extra host opcodes.

The generated state is `{handler, passage, visited, started, ended}` inside the
host's single typed `model`. Each choice checks its guard against that state,
threads effects in source order, navigates, then executes previously unvisited
passage entry effects. Later modification observes an earlier handler call's
variable changes; subsequent guards observe its membership changes. Refusal
short-circuits later effects. The receiving host admits the entire resulting
state and emission batch together, or refuses the entire turn. Even a target
entry failure rolls back the choice prefix and visitation marker.

This deliberately differs from upstream Spween's mutable `EffectHandler`: Rust
can retain prefix mutations, navigation and visitation when a later call fails.
Successful supported traces can be compared to that real Runtime. Failure
traces must record the different rollback boundary, not assert equivalence.

## Durable addressed effects

`Slots` has exactly `a`, `b`, `c`, `d`. Each slot has
`{enabled, to, command, recipientProgram, payload}`; payload is a typed plain
record chosen by the handler. The final method binds to
`delvetalk-source-data-effects-v1`. The example `send` takes three String
arguments (recipient, exact recipient program digest, chord), appends a `hear`
message, and refuses a fifth send within the combined choice-plus-entry turn.
Disabled slots still need well-formed identifier/digest fields.

These become native durable message records, with source preimage, original
principal and event identity. They are not inert outbox calls and do not execute
the recipient synchronously. The later `deliver` request requires an exact
recipient root, matching recipient program, authenticated event provenance and
current receiving law. Delivery refusal leaves the event pending. The existing
message profile owns retries, capacity, receipts and explicit consumption.

## Source, views and revisions

The protocol retains exact scene bytes and the pinned AST in `spweenSource`, plus
all executable module bytes in its object-local source table. Generated menu
availability runs as Bend against the committed typed model. Reading a menu
never executes entry effects. Old captured cards retain old roots; programming a
new source revision makes their actions stale. Revision/restart uses the same
native exact-preimage, current-law and durable-state machinery as any source
object. A handler state-shape change needs an explicit compatible migration;
code changes do not imply an automatic reset or conversion.

## Scope

The compiler supports Null, Bool, signed i64 and String equality, integer order,
mutable membership, conjunction/disjunction/negation, ordered assignment and
modification, explicit calls, navigation/end, and once-ever passage entry.
Float and String ordering refuse compilation. Integers are represented by typed
`Value.integer({value: n})`, where `n = i64 + 2^63`; authored handlers/migrations
must preserve that representation invariant. Checked source modification refuses
an overflow. Bool/Int equality follows upstream (true=1, false=0), while Bool is
not ordered numerically; modification of Bool/String preserves it. Source
requirements are compiled as a reporting function and do not gate startup.

There are at most 32 passages and 256 content items in this profile, alongside
native execution/package limits. Arbitrary custom handlers, external-world
completion and all possible Rust embeddings are not claimed equivalent.

Run `conformance/test_spween_handlers.py` for native ordered mutation, rollback,
source revision and authenticated delivery, and `test_spween_handler_oracle.py`
for the independent actual-Rust comparison including its partial-error behavior.
