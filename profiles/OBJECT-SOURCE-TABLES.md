# Object-local source packages

An authored object retains its ordered module bytes once, in its own exact
protocol root. Methods and views select entry points from that same table:

```text
protocol.sourcePackages = {
  resident: {format: delvetalk-source-package-table-v1,
             modules: ordered [{name, source}, ...]}
}
transition.package = {
  format: delvetalk-source-package-ref-v1,
  name: resident,
  entry: method
}
viewProgram.package = {
  format: delvetalk-source-package-ref-v1,
  name: resident,
  entry: view
}
```

The selector resolves only within its owning protocol. There are no paths,
global source names, mutable imports, network lookups or authority transfers.
Native method admission and view evaluation use the same local resolver and the
same source-only package compiler. Existing inline `{modules,entry}` descriptors
remain supported with their original meaning. Transition/view profile selection
continues to determine plain/typed state, Context and receiving ABI.

The exact captured protocol root pins both selector and ordered table bytes.
An altered source snapshot is a different preimage and stale requests refuse.
Installing a changed source table still needs current programming rights and
native checking; no redundant content hash or caller claim replaces this boundary.
Missing tables, malformed selectors or invalid import order refuse.

The source desk still retains original proposal bytes, ordered module references,
source material, adapter/runtime dependencies and checked builds. A local source
table avoids repeating the same text in every installed method/view descriptor;
it does not erase original module custody or silently refresh saved revisions.
History/export/restore preserve the complete protocol table as part of the root.

`conformance/test_source_package_adapter.py` checks source text occurs once, actual native
method/view behavior matches equivalent inline packages, and missing/tampered
source, wrong import order and changed exact readings refuse. These are scoped
local admission checks, not a proof of arbitrary source compatibility.
