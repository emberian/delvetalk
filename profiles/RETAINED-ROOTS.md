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

`retained-root` with exactly `op`, `object` and the captured full `root` returns
the reference only when its complete preimage is retained. It never refreshes
the capture. `prepare-retained` accepts the same fields as `prepare`, resolves
captured owner/observation references into a synthetic captured world, and runs
the same source preparation entry. Native read binding emits compact guards
before checking the final request byte limit. Later receiving can refuse this
prepared turn if any read or current law has changed.

Mint and captured preparation are read-only native queries. The resident daemon
serves them on its physically separate read socket; that endpoint rejects
exchange and checkpoint operations regardless of client flags. Minting does not
enroll a preimage in the index, create a grant, or confer mutation authority.
The current host's object inspection is public. Historical observation access is
subject to that host read contract independently of mutation grants; possession
of a locator does not replace the receiving principal or current-law checks.

Resident storage retains roots incrementally from successful read evidence and
object changes. Lookup does not scan receipt history. Checkpoint load rebuilds
the index from the retained world and admissions; journal replay reconstructs
it through the same receiving path. Stateless file receiving builds the index
from that retained world when a reference is used; legacy full-preimage requests
do not build it. No Python component resolves a reference.

Retention grows with distinct historical object roots, like retained admission
history. Buckets store exact Json values and are not a constant-memory cache.
There is no eviction or persistent transport cache, and existing reference
meaning is stable across restart. This is a new optional wire representation;
existing full-preimage requests and ordinary `prepare` remain supported.

`RetainedRootsChecks.lean` exercises a forced collision against the actual
resolver. `conformance/test_retained_roots.py` exercises file/resident receiving,
exact receipt identity, stale reads, absence, checkpoint restart and current-law
retry ordering. These are receiving checks, not a general proof of the receiver.
