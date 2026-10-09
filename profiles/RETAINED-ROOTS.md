# Retained exact root guards

The native receiver accepts an optional compact guard:

```json
{"profile":"delvetalk-retained-root-v1","object":"counter","key":"<locator>"}
```

The locator selects a retained **complete Json preimage** for that object. It
does not establish equality, current authority or absence. Unknown, malformed,
wrong-object and ambiguous collision buckets refuse. Once selected, the normal
receiver compares the complete root and applies current law. Null remains the
distinct absence guard.

Only top-level `expected` and transaction `reads` are expanded. Values inside
command inputs, protocols and source data retain their ordinary meaning. The
wrapper runs inside the fresh admission callback of `World.handleWith`. Exact
retry compares the original compact request first; receipts and journal frames
retain that original request. Replacing a compact guard with its full preimage
under an already retained intent is a different request and therefore collides.

`capture-roots` accepts object identities, a principal and optional expected
guards. In one native read it returns each complete inspected root paired with
its reference, explicit null for absent objects, and the receipt count. Resident
responses also carry the committed custody head. Requests select at most 17
objects; root output is bounded to 60 MiB within the 64 MiB read frame. Large
roots therefore need not be uploaded again to obtain their references.

View capture first inspects the owner, projects its declared dependencies, then
captures their union with an expected guard for that original owner reference.
Native full-preimage comparison refuses owner drift between these stages. It
never refreshes an existing invitation. The final paired roots and references
come from the same world state.

The compatibility query `retained-root` with exactly `op`, `object` and the captured full `root` returns
the reference only when its complete preimage is retained. It never refreshes
the capture. `prepare-retained` accepts the same fields as `prepare`, resolves
captured owner/observation references into a synthetic captured world, and runs
the same source preparation entry. Native read binding emits compact guards
before checking the final request byte limit. Later receiving can refuse this
prepared turn if any read or current law has changed.

Capture, mint and captured preparation are read-only native queries. File queries
reject mutation operations before receiving and require the resulting world to
equal the original; they create no lock, candidate or snapshot file. The resident daemon
serves them on its physically separate read socket; that endpoint rejects
exchange and checkpoint operations regardless of client flags. Minting does not
enroll a preimage in the index, create a grant, or confer mutation authority.
Capture and historical preparation use the host's current native object read
contract independently of mutation grants; possession
of a locator does not replace the receiving principal or current-law checks.

Resident storage retains roots incrementally from successful read evidence and
object changes. Lookup does not scan receipt history. Checkpoint load rebuilds
the index from the retained world and admissions; journal replay reconstructs
it through the same receiving path. Stateless file receiving builds the index
from that retained world for capture or when a reference is used; legacy full-preimage requests
do not build it. No Python component resolves a reference.

Retention grows with distinct historical object roots, like retained admission
history. Buckets store exact Json values and are not a constant-memory cache.
There is no eviction or persistent transport cache, and existing reference
meaning is stable across restart. This is a new optional wire representation;
existing full-preimage requests and ordinary `prepare` remain supported.

Source invitations now declare observation state and law inspection explicitly.
This unlaunched preview ABI requires rebuilding old source invitations; stored
invitations are not silently refreshed or reinterpreted. Original admitted
requests retain their exact retry identity.

`RetainedRootsChecks.lean` exercises a forced collision against the actual
resolver. `conformance/test_retained_roots.py` exercises file/resident receiving,
exact receipt identity, stale reads, absence, checkpoint restart and current-law
retry ordering. These are receiving checks, not a general proof of the receiver.
`conformance/test_root_capture.py` additionally checks large roots, paired
references, guarded capture drift, explicit absence and restart. Resident capture
avoids a history scan; file capture rebuilds its index from the expanded retained
world. Neither path makes a constant-memory or constant-cost hashing claim.
