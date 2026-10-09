# The scene relation is Bend source

`SceneRuntime.obend` defines configuration validation, guards, ordered effects,
short-circuit refusal, once-ever entry, passage lookup/navigation, and menus over
`SceneData.obend`'s typed AST. It imports the selected ordinary `Handler` and uses
its actual state. `SceneModel.obend` defines the shared typed session, decisions,
heterogeneous action list and `Behavior` interface. `Abi` and `Encounter` come
from the explicitly retained prelude.

The package retains the runtime library under the name `BaseRuntime`. The selected
`SceneRuntime` is normally `DefaultRuntime.obend`, a small source definition that
returns `Base.behavior()`. An inhabitant can instead supply a source extension:

```sh
python3 scene/handlers.py protocols/spween-handlers/repair.scene \
  --runtime scene/runtime/QuietRuntime.obend > /tmp/quiet-scene.json
```

`QuietRuntime.obend` uses `fix(compose(Base.Default, Quiet), {})`. Its view changes
the title, and its `choose` method refuses the principal `sleeper` while delegating
other calls to the same runtime. Neither the parser adapter nor the scene/handler
needs editing. The example is an authored policy, not a host identity rule.

The source workshop also accepts selected runtime modules after `Handler`, ending
with `SceneRuntime`; supporting modules remain explicitly ordered. All library,
handler, score and selected runtime bytes are part of the exact installed source
table. There is no mutable import lookup or extra authority from choosing code.

`scene/handlers.py` now serializes parser nodes into `Score.scene()` data. Its
output contains constructors and literals, not generated guards, branches,
transitions, effect loops, passage methods or menu fields. Null targets, named
end targets and passage names stay distinct data until the Bend runtime interprets
them. The fixed `Scene.obend` adapter delegates describe/start/choose/view to the
selected `Behavior`; it does not specialize per scene.

The runtime's `validate` export checks the supported configuration. The adapter
runs that ordinary source export and reports its result. Native source typing
checks the method ABI. Source authors can inspect and revise both definitions;
Python does not maintain an equivalent validation or execution relation.

State remains `{handler, passage, visited, started, ended}` inside the typed
`model`. Existing `start {}` and `choose {choice: Nat}` calls retain their meaning.
The menu is a recursive list of a source `Action` sum: start carries `{}` while a
choice carries its exact `{choice}`. The structural presentation bridge unwraps
the descriptor payload; constructor tags never select authority or execution.

Prose collection and joining are source functions using the checked `textConcat`
operation. The host's source/data limits still bound evaluation and presentation.
This runtime retains the supported i64 profile and its deliberate atomic-refusal
difference from upstream's partially mutable error paths; see
`protocols/spween-handlers/README.md` and the independent Rust comparison.
