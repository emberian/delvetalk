# Source objects

`objective-bend-object` binds one exact Bend package to the native source host.
The package exports `describe`, named methods and `view`. Native compilation
checks their argument/result schemas, and native admission checks current law,
exact roots and bounded effects. The physical adapter retains source and moves
requests and results; it does not implement object behavior.

`describe()` returns `{name,initial,methods,panels}` and may declare an allocation
limit. State is a closed serializable record; supported recursive sums use the
same checked source interface. The installed model retains typed Data. An unused
alternative cannot hide an incompatible or executable payload schema.

Ordinary methods take state, declared input and authenticated context, returning
`{accepted,reason,state,result}`. Context identifies the object, caller and actual
preceding transaction origin, including its program identity. Input fields cannot
forge that origin. A refusal or invalid result rolls back the transaction.

Use the shared [ABI](../world/lib/prelude/Abi.obend),
[preparation values](../world/lib/prelude/Preparation.obend), and
[encounter definitions](../world/lib/prelude/Encounter.obend). Metadata may select
a checked codec for heterogeneous inputs/results; codec changes are tracked in
[BACKLOG](../BACKLOG.md). The codec supplies neither authority nor missing-value
defaults. [Allocations](ALLOCATION.md) are explicit source decisions admitted
atomically with the invoking state change.

## Views and messages

`view(state,panel)` returns title, prose, offered actions and bounded children.
A child is a reference with a label and panel; following it acquires a fresh
observation under the child’s current read law. Copying a reference grants no
read or invocation authority. Source views may also offer documents, preparation
invitations and interpretation through their checked shared contracts.

An emitting decision returns the bounded linked collection in
[Emissions](../world/lib/prelude/Emissions.obend). There are no padded message
slots. A receive method additionally takes authenticated causal event facts;
source cannot fabricate those facts by direct invocation. A receiver may itself
emit within the retained chain budget. Each addressed event binds the recipient
program and faces current law at delivery. See [resident messages](../docs/RESIDENT-ACTIVITY.md).

## Exact source

Single-module and sealed multi-module source use the same `objective-bend-object`
interface. Installed selectors resolve against the object-local `sourcePackages`
table of exact ordered source. Native schema comparison joins initial state,
method state and view state; transparent alias indices are never treated as
portable type identity by the adapter.

See [module authoring](MODULE-AUTHORING.md), [source desks](DESK.md),
[the actual binding](../syntaxes/obend_object.py), and
[source-binding checks](../conformance/test_obend_data_object.py). Current receiving
qualification requires the matching native/source/consumer closure; a compiler
probe alone establishes neither deployment nor general behavioral correctness.
