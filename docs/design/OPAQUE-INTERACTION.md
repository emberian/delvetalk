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
2. The host returns the existing retained-root content reference: object and
   custody digest, resolved through collision-preserving exact root buckets.
   It grants no authority. Invocation expansion still compares the complete
   selected root with the current object. No version uniqueness assumption is
   needed. A reference copied from another world can select only identical exact
   content already present in that receiving custody; it supplies no authority.
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

The first implementation uses `law.view[panel]` with `"public"` or an exact
principal array, independently of `read` and `invoke`. Missing view grants fall
back to current full-read authority for existing source objects. `opaque-view`
executes the installed `viewProgram` privately and returns its typed data plus
the content reference. `opaque-select` binds object, command, input, principal
and intent to a current invocation-authorized selection without running a body.
It returns an exact `opaque-invoke` envelope; selection does not reserve a grant.

The ordinary admission history retains that compact request and its projected
receipt. Full expanded preimages, native receipts and source diagnostics live
separately in trusted `opaqueCustody`; checkpoint reconstruction restores their
retained-root index. Participant history remains current-read guarded and cannot
select that private field. Projection is fixed at admission, including refusal,
so retry after revocation or restart never calls the source view or method again.
The source counter and authenticated Account route pass actual file, resident
and verified HTTP receiving regressions on the sealed evaluator generation
(native binary `449ef244b27fc8bc718ef0d5d5eff213bb7ff0a2c016137af6ca2a780dd26f21`,
2 tests, 10.325 seconds, 2026-10-09). This qualification covers single invocation,
current public view, stale exact source refusal, denied acquisition/history, and
original projected reply recovery after revocation and process restart. The
sealed prepared transaction extension below has its own receiving evidence.

Invitation selection uses `opaque-invitation` with an exact owner reference,
panel and source invitation key. Custody re-evaluates the granted source view;
the caller cannot choose a preparation export or substitute observation flags.
Declared dependencies are captured under the participant's current read grants.
The particular exposed invitation permits its bounded owner computation only;
it supplies no ambient authority over private peers.

`opaque-prepare` returns authored questions, refusals, or a summary and compact
`opaque-transaction` envelope containing the caller's original selection,
contribution and exact dependency references. Prepared calls and derived inputs
remain private. Fresh admission deterministically reconstructs those calls
against the exact selected source and dependencies, then checks current action
law atomically. View evaluation, typed conversion, preparation and transition
share the receiving budget. Exact admitted retries recover their retained
projection before reconstruction; source or dependency drift never refreshes a
captured invitation. This describes the receiving contract; runtime acceptance
is separately recorded against its checked source snapshot.

Questions and refusals carry `publicSelection`, the exact source invitation and
dependency witnesses that authorized their computation. A saved response can
revalidate that selection through `opaque-invitation` with its observations;
custody checks current view/read grants and refuses any owner or dependency
drift before the response is disclosed again. This check does not rerun
preparation or erase an already admitted caller receipt.

The sealed transaction path passes the ordinary private RootDirectory source
consumer (2 tests, 13.491 seconds) and source budget/private-derived-input tests
(2 tests, 5.842 seconds) on native binary
`75217d1ab992e6dbe67cae9b0e2ef39f2293cfb1656f6d6492f1c98e103c0269`.
The preparation view, typed conversion, source preparation and transaction body
consume one receiving allowance. A source-derived secret input remains in
private custody, while the public reply exposes only invocation results and
exact resulting references. Current peer read revocation hides the projected
history row; exact original receipts survive revocation and checkpoint restart.
Dependency drift refuses without refreshing captured roots. Non-invocation
transaction result slots are null in the exported projection.

This path grants no blind access to other private objects. Declared dependencies
and every explicit observation require current read authority. Allocation
metadata stays private unless the source deliberately returns a child identity;
subsequent child invocation still needs that child's current invocation grant.
