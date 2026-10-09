# Explicit shared Bend source

Supply these modules before the consumer in a sealed source package. Imports
are ordinary Objective Bend imports, for example `import ./Abi.obend as Abi`.
The compiler does not read this directory, fetch dependencies, or inject a
standard environment. The exact ordered module names and source bytes travel
with the object in its retained source package table and sealed desk manifest.
Physical callers can use [source closure packaging](../../../docs/design/SOURCE_PACKAGING.md)
to select exact dependencies from an explicit allowlist using the native parser.

`Abi.obend` exports `Origin`, `Context`, authenticated receive `Event`, and
`StringField`/`NatField` form declarations. These describe the current receiving
ABI; constructing one inside source does not create authenticated evidence or
grant authority. `Context` is the existing three-field context, with the four
fields of `Origin`; no new ambient object lookup is implied.

`List.obend` exports bounded rank-1 generic lists and reusable source traversals.
`Encounter.obend` exports `Child` and `Children = Lists.List<Child>`, with source
functions `childrenLength`, `childrenContains`, `childrenAppend`,
`childrenRemove`, and `childrenOffer`. Offer retains order and leaves a full
collection or duplicate key unchanged. Remove removes every matching key.
Capacity is explicit source policy; native execution work remains bounded.
The shared list preserves `nil`/`cons` and `head`/`tail`; domain operations keep
key membership, capacity, and ordering policy in Encounter. Preparation.Names
and Document.Documents also use list instances. The current API supports
shareable data and reusable functions; owned-payload traversal requires further
core/interface work. See [generic specialization](../../../docs/design/GENERICS.md).

The bell and listening door in `protocols/resident-messages` explicitly import
their source dependencies. Their packages seal List, Abi, Preparation, Encounter,
and Emissions before Bell or Door, check the authored examples, adopt the exact package,
and delivers a real retained sound. `conformance/test_source_prelude.py` composes
source extensions over a shared encounter collection and runs inspection,
bounded addition and revision through the compiler and machine. Missing imports
are refused; there is no fallback to a host-installed library.

`EncounterPages.obend` stores those same children in pages of at most sixteen.
Starting empty, `append` fills the last page; `offer` first rejects duplicate keys
and the caller's total capacity. `remove` preserves order, removes every matching
key and drops empty pages without repacking survivors. `page` uses a zero-based
index and returns an ordinary `Encounter.Children` (empty when absent).
`length`, `pageCount` and `contains` inspect the collection. Constructors remain
ordinary public source data; the chunk bound is maintained by these operations,
not a privileged host invariant. This concrete module does not discard fields
from other protocols' richer records.

`examples/PageGallery.obend` retains pages and a shared selected page in a real
source object. Its view offers previous/next actions and at most sixteen children;
links do not grant access to their targets. The authored capacity is 200, subject
to the separate receiving and view wire limits. `test_encounter_pages.py` checks
200-entry source roundtrips and a seventeen-offer native object journey through
checkpoint, restart, exact retry, stale-root refusal and live page projection.
The opt-in `bench_source_collections.py --representation pages` records source
work at 8/32/50/200. Chunking solves the measured flat-list depth failure; it does
not promise unbounded storage or remove the full-root 64 KiB request/view limits.
