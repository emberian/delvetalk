# The small spell forge

Make a chalk door, write an Objective Bend spell, and invite someone to try it.
The [paper door](../../syntaxes/examples/paper-door.obend) opens for **please**.
The [moon door](../../syntaxes/examples/moon-door.obend) composes a second extension
with the first, changing its rule, reply and inscription.

The spell is ordinary textual Objective Bend. Its `allowed(word)` decides whether
a knock proceeds; `knock(word)` answers; `view(state, panel)` supplies the visible
interface. The pinned Lean frontend parses and compiles that source. The adapter
`objective-bend-spell@1` supplies the small host binding, without interpreting the
spell itself. Residents do not write the internal JSON protocol or AST.

[Examples](paper-door.examples) are text too:

```text
examples DelveTalk 1
case a visitor opens the paper door
law visitor
as visitor
send knock
  word: please
expect result: The paper door swings open onto a tiny lantern-lit room.
```

Try [the moon challenge](moon-challenge.examples) against the paper spell. It
fails; the [moon spell's examples](moon-door.examples) include that challenge and
pass. Source and examples remain exact strings in a one-shot writing desk, readable
in its pending card. Each revision or challenge gets a fresh desk. A compiler reply
shows the actual outcome; passing examples do not install a spell. Its maker must
explicitly adopt the reviewed revision before a visitor sees the change.

This first binding has no mutable state. Installation explicitly starts with the
empty state, retained internally as `{}`. Current laws and both exact roots govern
the atomic desk-release/door-replacement transaction. A stale review refuses.

## Operator package

[generate.py](generate.py) exposes `build(visitors, compiler)` with `objects` and
`desks` factories, plus `factory_law(makers, managers=())`. Configure actual enrolled
DIDs for town use. `spell_source(revision)`, `example_source(revision)` and
`challenge_source()` read the exact textual fixtures.

Both factories expose `make {name}` with declared absence inputs and a 16-child
quota. Actual allocation receipts identify the children. A door gives its actual
maker reprogramming/law authority and that maker plus configured visitors `knock`.
A desk grants its maker submit/adopt and the configured compiler compiled/failed.
A factory manager inherits no child authority; input labels cannot impersonate
its maker.

Desk fields are `target`, `source`, `scenarios`; the latter two accept up to 4096
Unicode scalars in forms. Guards separately require nonempty strings and one-shot
submission. Empty/pending state stays inside the existing pure-view boundary;
finished compiler replies present the retained source, compiled result and
adoption action without dumping raw compiled state.

The bounded service recognizes exact approved desk bodies, not names or command
lists. Continuations retain original source and build custody. Machine factory and
migration descriptions remain JSON; authored behavior lives in the Bend source.

With the existing compiled and view hosts already built:

```sh
python3 protocols/town-forge/generate.py
python3 conformance/test_town_forge.py
python3 conformance/test_town_forge_custody.py
```

Tests cover real allocation, authority, textual source compilation, challenge
failure, adoption/use/revision, service discovery and exact continuation restore.
Live publication and the complete posts-only receiving journey are separate checks.
See the [complete posts journey](../../conformance/test_town_forge_journey.py).
