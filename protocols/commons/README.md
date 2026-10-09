# The commons

[Commons.obend](Commons.obend) owns a bounded place graph and declared presence.
An authenticated caller can enter an entry place, follow a directed path, or
leave. A call changes only that caller's presence. Another participant's copied
identity, a reference, or a grant alone cannot select or create a presence slot.

Presence is neither containment nor read permission. It does not establish a
physical location, a live connection, access to a referenced object, or agreement
with another registry. Disconnecting does not implicitly leave.

The source has typed collections for participants, places, paths and gates.
It checks topology and capacity on each transition: at most eight participants,
eight places, sixteen paths and sixteen gates. References remain explicit
world/object identities. Results carry the caller's entity, previous and next
place, all declared locations, and the destination's description and exits.
Leaving returns an empty destination record.

`generate.py` is now a physical package loader. Its existing
`build(participants, places, paths, entries, gates)` interface frames configuration
as data and invokes the source constructor. It does not generate guards, updates,
views or action sequences. Every configuration retains the same source modules.
The current compiled host executes them; no JSON protocol twin is maintained.
`law(...)` supplies explicit installation grants independently of the source graph.
The workshop seed uses this loader directly.

## A source door controls a path

A configured gate names one directed path and its receiving object/command.
`move` checks the host's authenticated input origin: the immediately preceding
successful invocation must be that exact gate. Explicit copied input, the same
result from another object or method, and an older result cannot satisfy it.
Both objects still check the caller's current law and exact read roots.
A later refusal rolls back the complete transaction.

[The paper gate](garden-gate.obend) is an ordinary source object. A crossing invokes
its `cross` method, then calls commons `move` with `inputFrom` pointing at that
result. Revising the door changes the gate's behavior without replacing commons.
This deliberate trust grants no additional authority on commons or garden objects.

The maker may revise a privately created door under its current law. Shared
commons policy is revised through its configured management/proposal path;
there is no owner-recovery bypass. Exact retries retain historical receipts even
when current grants have subsequently changed.

With native hosts already available:

```sh
python3 conformance/test_commons.py
python3 conformance/test_guarded_movement.py
python3 conformance/test_guarded_authoring.py
```

These check two-participant movement, wrong paths, impersonation, stale reads,
revocation, retries, transaction rollback and source authoring/adoption/restoration.
They establish local admitted execution, not deployment or message delivery.
