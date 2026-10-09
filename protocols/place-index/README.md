# On display

A curator exhibits objects; visitors choose a label and see the object's current
card. This is membership in an exhibition, not possession or physical inventory.
The actual [Bend list module](ExhibitList.obend) stores up to 32 entries; the
[binding source](Main.obend) owns duplicate rules, order, labels and the view.
There are no numbered storage slots or Python room rules.

Use the ordered modules and explicit `objective-bend-spell@3` syntax in
[package.json](package.json). Seal exact source refs, submit through a source desk,
check the [examples](index.examples), then adopt with the typed empty model supplied
by `describe()`. Current law separately grants `add`, `caption`, `remove`, `reorder`,
programming and law revision. Source does not grant rights to its authors.

To exhibit an object atomically, read exact index/target roots, `observe` the
target, invoke index `add` with `inputFrom` pointing to that immediately preceding
observation, then invoke `caption {object,label}`. The index checks native
Context2 kind, object and adjacency; equal caller-supplied data is insufficient.
`addedBy` is the curator, and `observedVersion` records the target at curation time.

Remove and reorder require current membership but no fresh target observation.
`reorder {object,before}` places the member before another; empty `before` moves
it to the end. Neither operation changes the target. Labels and object fields have
form bounds; the source enforces the 32-entry count. Generic typed-view child
validation separately bounds displayed data and rejects malformed/oversize rows.

The source view returns a recursive list of read-only children alongside fixed
own-object controls. Selecting a label captures a fresh, separate target card;
its actions still require that target's current law. References do not auto-enroll
objects, confer authority or resolve foreign worlds. An old parent card remains
an old catalogue; refresh it for current membership. An old child action remains
bound to its old root and refuses after revision.

With the native profiles already built, run:

```sh
python3 conformance/test_place_index.py
```

The journey assembles sealed peer source through a real desk, exhibits two objects,
uses and revises a discovered object, tests stale choices, removes/reorders members,
and restores the typed list and source custody. Public transport is simulated;
source compilation, admission, projection and history replay use actual Lean.
