# Source-authored objects

**`objective-bend-spell@2` binds one Bend module's state, methods, forms and view.**
Start with [the lantern](examples/lantern.obend) and its
[readable examples](examples/lantern.examples):

```sh
python3 scripts/translate.py --syntax objective-bend-spell@2 syntaxes/examples/lantern.obend
python3 scripts/propose.py --syntax objective-bend-spell@2 --profile compiled syntaxes/examples/lantern.obend syntaxes/examples/lantern.examples
```

Three exports/contracts:

- `describe()` returns exactly `{name, initial, methods, panels}`. `initial` is a
  record; `methods` has 1–32 entries `{label, fields}`. `panels` maps up to eight
  IDs to labels. Names and declarations grant no authority.
- Each method name selects an exported `(state, input, context)` definition.
  Context is receiving-derived `{object: String, principal: String}`; output is
  `{accepted: Bool, reason: String, state, result}`. Existing
  [source-transition admission](../profiles/COMPILED.md) executes it once.
- `view(state, panel: String)` returns `title`, `prose`, and a fixed row of
  `{visible: Bool, text: String, command: String, input: record}` actions.
  `delvetalk-obend-menu-v1` validates every descriptor before hiding false entries.
  Hidden computations still materialize; visibility grants no authority.

Fields reuse [affordance metadata](../profiles/AFFORDANCES.md), including validated
examples. Because Bend's current plain-data boundary has no arrays, enum
`options` is a record of strings; values become choices in sorted-key order.
Examples supply no defaults. Children/allocation, outbox effects, viewer identity
and event context are outside this binding.

Lean compiles all named exports. Their checked types must agree on initial state,
input fields and context; every method preserves that state type. Views must
accept it. This checks a submitted module's ABI, **not a permanent receiving
invariant** or proof of its examples. Explicit adoption still supplies migration
state and preserves the target's current permissions.

Translation evaluates only `describe`, through the existing native package
machine. Fixed limits: 100,000 ticks/heap cells, 10,000 stack frames, 30 seconds
total, 10 seconds per process, 8 MiB input/output frames. Native runtime and adapter
dependencies are pinned and checked again before retaining the artifact. Modules
retain exact source; Python frames and validates data, never evaluates Bend.

`objective-bend-spell@1` remains the original stateless door binding. Existing
objects/cards are never rewritten by translation; revision uses explicit adoption
and fresh captures. [Tests](../conformance/test_obend_object.py) exercise actual
desk checking, town spells, refusal, replay and restoration.
