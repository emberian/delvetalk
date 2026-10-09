# Invoking private objects

DT-41 is the next receiving contract after governed acquisition. A visitor must
be able to read an authored invitation and invoke its offered operation without
acquiring the object's implementation or complete state. DT-07 closes leaks in
the existing whole-root ABI; its read prerequisite must not become a permanent
requirement for all invocation.

Keep three permissions distinct. `read` acquires full roots/source/history.
`invoke[command]` authorizes a state-changing method under current law. A named
view grant permits a pure source export to reveal its authored interface; it does
not permit raw inspection or use a service principal. Views have explicit public
or principal grants, with private objects closed unless such a grant is present.
Existing public-root objects retain their current views without new ceremony.
Executable rules remain source-owned. There is no universal host interpretation
of private state and no inference of permission from a reference.

The receiving host gains an explicit opaque-interaction route; it does not
silently change the existing full-root route:

1. A current authorized view is evaluated inside custody against the actual root.
   Its result contains authored prose, fields, offered actions and references,
   never the internal view program, root, state, law or preparation arguments.
   Source-authored outputs are intentional disclosures under that view grant.
2. The host returns a revision reference tied to this world lineage, object and
   exact root. Prefer the existing monotone object version plus a checked retained
   version-to-root index over an unguessable capability token: the reference
   grants no authority and need not hide that an object changed. Before adopting
   that representation, establish uniqueness for actual creation/allocation,
   every update and checkpoint reconstruction. Otherwise retain an opaque native
   lookup key; do not substitute an unchecked version comparison for exact roots.
3. Invocation carries that reference, command, typed contribution, authenticated
   principal and intent. The receiver checks current invocation policy and exact
   selected preimage, runs the same transition, and retains the full admission
   privately. Full-root acquisition is unnecessary on this explicit route.
4. The caller receives a separately retained projection: status, authored result
   or refusal, object/revision reference, and explicitly exposed created-object
   references. It does not receive native roots, code, law, transaction peers,
   debug/type traces or unselected outbox/evidence. Projection is fixed by the
   receiving ABI/source output at admission, not recomputed by later programs.
5. Exact retries compare the original compact request before root expansion and
   return that principal's same projected fact. Revocation blocks new invocations
   and new view acquisition; it does not erase a caller's already admitted result.
   Another principal cannot retrieve it by presenting its intent or reference.

Source preparation requires the same split. A participant selects an offered
invitation by owner/revision/key and sends contribution data. The host executes
its bound source export privately. Source-declared dependencies are acquired
under that participant's relevant grants, never ambient clerk access. Questions
and refusals return authored data; a prepared turn retains private exact roots
inside custody and exposes opaque per-object guards. Execution still checks all
current rules atomically. It must not send a full prepared internal request back
to the browser and then claim the object's state remained private.

A first coherent implementation should join one private source counter, its
public view, one invocation, native projection custody/retry and an authenticated
Portal/account path. Defer general blind multi-object workflows until the single
object path establishes the representation. Then generalize preparation using
the same guard/projection mechanism, rather than another token recipe language.

Acceptance: Bob views Alice's private counter invitation and increments it,
seeing only the authored number/result. Raw inspect/source/history fail; the
view and reply contain no hidden phrase planted in state or code. A stale guard
and revoked invocation fail. Lost reply/restart returns Bob's original result
without reexecuting; Carol cannot obtain it with Bob's intent. An old public view
cannot invoke a newly replaced private method. Malformed/private diagnostic data
stays in trusted custody. Alice can still obtain full inspection under `read`.

This is an implementable receiving design, not a claim that opaque interaction
or a noninterference proof is already present. It depends on DT-07's shared read
boundary and the single current-law profile; it reuses the actual native
transition, exact-retry custody, typed codec and authored view/preparation exports.
