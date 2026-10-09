# Exact physical source packaging

A caller names the entry root and an explicit allowlist of `(module name, path)`
pairs. `scripts/source_closure.py` reads those confined files once, sends their
exact UTF-8 text to the native `source-imports-v1` operation, follows its parsed
edges, and orders dependencies before their consumers. Ordered roots and the
native import transcript determine the order; the last root remains the selected
entry module. Missing edges, cycles, duplicate names, ambiguous file identities,
and paths outside the custody root refuse with a concrete error.

The native operation uses `FrontEnd.parseSource`, including document-template
lowering and its derived import transcript. Python neither recognizes import
syntax nor selects source types. The actual package compiler still validates
imports against earlier explicitly supplied modules and exact source hashes.
An import must match `./NAME.obend`; filesystem basenames do not select identities.
Different source aliases for one module retain one exact dependency.

`source_closure.assemble` returns ordinary module records plus the existing sealed
source-store manifest. Both preserve exact bytes, including line endings. The
manifest identifies the source preimages; it grants no authority and does not
claim that an object is checked, admitted or deployed. Existing artifact-store
preservation and source table retention supply those bytes to downstream callers.

`source_object.read_closure` selects the explicitly documented common library
allowlist together with the caller's named sources. It defaults to the last
supplied source as its root; `roots=` supports multiple roots. Unused common
sources are omitted from the retained package. Consumers need not duplicate the
transitive List/Preparation/Encounter/Document order. For a different library or
custody boundary, call `source_closure.read` with an explicit allowlist and root.
The compiler never installs or searches this library as an ambient environment.

`conformance/test_source_closure.py` checks physical custody failures separately
from actual native parsing, compilation and the six major loader closures.
