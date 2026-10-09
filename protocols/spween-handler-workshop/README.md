# The moth workshop

One author writes a Spween scene and its ordinary Bend handlers. Another changes
the repair from one counted repair to two and composes a lanternlight runtime
view over the ordinary base behavior. The same moth, inventory and passage
survive the revision. Old action cards refuse; restored history retains both
complete source documents and the installed state.

The explicit syntax `spween-handler-workshop@1` accepts one `spween` block and
ordered `obend NAME` blocks ending in `Handler`. Optional runtime modules follow
Handler and end in `SceneRuntime`. Optional entry modules follow, ending in
`Scene`, to describe additional typed methods. For example:

````text
spween handler workshop 1

```spween
---
id: example
title: A small workshop
---
=== bench
* [Repair]
  ~ repair
  -> bench
```

```obend Handler
...ordinary Objective Bend handler source...
```
````

Use the complete runnable source, including its Handler ABI:

```sh
python3 protocols/spween-handler-workshop/generate.py --source
python3 protocols/spween-handler-workshop/generate.py --source --revision 2
```

[Scene](moth.scene), [first handler](Handler.obend), [revision](Chorus.obend), and
[text examples](moth.examples) are editable source. The compiler supplies a pinned
ABI, encounter helpers, typed scene data and model, plus the final score and entry
module. Names `Abi`, `Encounter`, `Kernel`, `SceneData`, `SceneModel`,
`BaseRuntime` and `DefaultScene` are reserved; `Scene` may be the final authored
entry module. Handlers receive `Abi.Context`.

Without runtime blocks, the compiler selects the pinned ordinary Bend
`SceneRuntime`. To select another, append its ordered dependency blocks and a
final `obend SceneRuntime` block after Handler. That module exports the same
`behavior()` contract; a replacement can compose the pinned
`BaseRuntime.Default` with its own extension. The sealed package includes that
pinned ordinary base source; an import never looks it up elsewhere. The
[lanternlight revision](LanternRuntime.obend) changes the view while inheriting
start, choice and validation behavior. Writing cards accept bounded multiline source and examples. Larger replacements
use the source-reference/Desk API.
The complete selected runtime and dependency text stays in source custody.
An optional final `Scene` imports `DefaultScene` to reuse standard methods while
defining its own `describe()` and additional typed exports. See
[the resonant entry](../../scene/runtime/ResonantScene.obend) for a new method and
a receive-only method; the generic native source binder checks both.

The native frontend resolves and checks only the explicitly sealed package.
Python neither executes handlers nor searches for imports.

`generate.build(authors, compiler)` supplies governed object, Candidate and
writing-card factories. Its placeholder state comes from native `describe()`.
Each proposal gets a fresh immutable Candidate. A resident makes an ordinary
source writing participant naming that Candidate, the target and syntax. Its
view exposes a submission invitation; `submission_offer(writer, writer_root,
observations)` captures that actual invitation rather than constructing a plan.

The reusable [Writing source](../source-desk/Writing.obend) chooses the complete
proposal and captured target-state migration in ordinary Bend. The resident
supplies source and examples; native preparation binds the exact owner,
Candidate and target observations. A changed target refuses submission without
refreshing the capture. Checking produces a review card; adoption separately
checks current authority and the reviewed roots. Preservation does not prove
that an arbitrary replacement handler accepts the schema; explicit examples and
receiving admission still check that compatibility.

The source wrapper retains the complete document; the lowered program retains
exact scene and ordered handler/runtime strings. Adapter, parser, source-data helper
and native runtime dependencies are pinned with compiler custody. A source block
confers no authority. Two authors in the demonstration have explicit shared grants.

After the existing native hosts are built:

```sh
python3 conformance/test_spween_handler_authoring.py
```

The journey runs text posts through receiving custody, compiler queue, checked
adoption, two-person play, handler revision, stale refusal, history export and
restoration. Only public record GETs are simulated; nothing is posted externally.
