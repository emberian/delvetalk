# The small spell forge

Make a chalk door, write an Objective Bend spell, and invite someone to try it.
The [paper door](../../syntaxes/examples/paper-door.obend) opens for **please**.
The [moon door](../../syntaxes/examples/moon-door.obend) composes a second extension
with the first, changing its rule, reply and inscription.

The spell is ordinary textual Objective Bend. Its `allowed(word)` decides whether
a knock proceeds; `knock(word)` answers; `view(state, panel)` supplies the visible
interface. The pinned Lean frontend parses and compiles that source. The adapter
`objective-bend-object` supplies the small host binding, without interpreting the
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
pass. Source and examples remain exact strings in a one-shot writing desk, retained
with its candidate. Each revision or challenge gets a fresh desk. A compiler reply
shows the actual outcome; passing examples do not install a spell. Its maker must
explicitly adopt the reviewed revision before a visitor sees the change.

This first binding has no mutable state. Installation explicitly starts with the
empty state, retained internally as `{}`. Current laws and both exact roots govern
the atomic desk-release/door-replacement transaction. A stale review refuses.

## Operator package

[generate.py](generate.py) loads explicit source modules and configuration.
`build(visitors, compiler)` supplies `objects`, `desks` and `writers` factories;
`factory_law(makers, managers=())` supplies explicit installation law data.
[ObjectFactory.obend](ObjectFactory.obend) owns child construction, creator law,
quota and its preparation invitation. The actual authenticated maker receives
revision authority; configured visitors receive the configured methods. Labels
cannot impersonate the maker.

The desk is the reviewed ordinary [Candidate](../editor/Candidate.obend).
The [Writing participant](../source-desk/Writing.obend) binds a candidate, target
and source syntax. Its invitation accepts source and examples, captures the
complete target state, and prepares submission. Factory creation and writing are
source preparations over captured roots; the client only transports their plans.

The bounded compiler service recognizes the reviewed Candidate body. Continuations
retain source, examples, reports and exact build custody. No generated desk or
factory JSON twin is maintained.

With the existing native hosts already built:

```sh
python3 conformance/test_town_forge.py
python3 conformance/test_town_forge_custody.py
```

The checks cover allocation, authority, source compilation, challenge failure,
adoption/use/revision, service discovery and continuation restore. See also the
[posts journey](../../conformance/test_town_forge_journey.py).
