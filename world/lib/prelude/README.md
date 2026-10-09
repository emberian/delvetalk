# Explicit shared Bend source

Supply these modules before the consumer in a sealed source package. Imports
are ordinary Objective Bend imports, for example `import ./Abi.obend as Abi`.
The compiler does not read this directory, fetch dependencies, or inject a
standard environment. The exact ordered module names and source bytes travel
with the object in its retained source package table and sealed desk manifest.

`Abi.obend` exports `Origin`, `Context`, authenticated receive `Event`, and
`StringField`/`NatField` form declarations. These describe the current receiving
ABI; constructing one inside source does not create authenticated evidence or
grant authority. `Context` is the existing three-field context, with the four
fields of `Origin`; no new ambient object lookup is implied.

`Encounter.obend` exports `Child` and recursive `Children`, with ordinary source
functions `childrenLength`, `childrenContains`, `childrenAppend`,
`childrenRemove`, and `childrenOffer`. Offer retains order and leaves a full
collection or duplicate key unchanged. Remove removes every matching key.
Capacity is explicit source policy; native execution work remains bounded.
These are concrete encounter collections, not a pretend polymorphic List.
Domain-specific collection types can remain beside their behavior.

The bell and listening door in `protocols/resident-messages` explicitly import
both modules. Their desk journey seals `[Abi, Encounter, Bell]` or
`[Abi, Encounter, Door]`, checks the authored examples, adopts the exact package,
and delivers a real retained sound. `conformance/test_source_prelude.py` composes
source extensions over a shared encounter collection and runs inspection,
bounded addition and revision through the compiler and machine. Missing imports
are refused; there is no fallback to a host-installed library.
