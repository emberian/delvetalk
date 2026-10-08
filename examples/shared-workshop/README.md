# A shared workshop that participants can reprogram

Iris organizes a workshop; Moss estimates materials. Six benches need seven
boards each. They share a task, one offer, and two answer slots. Their actions
run through the existing Lean world and ordered transaction host, including a
real race between the two local callers. The runner does not decide admission.

```sh
make build
python3 examples/shared-workshop/run.py
# Keep a reviewable local world and all request/receipt evidence:
python3 examples/shared-workshop/run.py --output /tmp/workshop-example-1
python3 conformance/test_workshop.py
```

The output directory must not exist. With no `--output`, the example uses a
temporary world and prints its outcome. With an output directory it retains:

- `world.json`: objects and the host's durable original requests/receipts;
- `report.json`: the complete narrated request/receipt transcript, exact
  snapshots, the typed function check, and proposal identities;
- `proposal-report.json`: the existing proposal tool's exact-source,
  lowering, scenario and executable evidence.

These are local artifacts. Nothing is posted or delivered externally. Iris and
Moss are scripted principal names asserted by the caller, not authenticated
agents or model invocations. The selected host is `transactions`, which also
supports the existing single-object operations and governed `reprogram`.

## One continuous interaction

1. **Moss offers a materials estimate.** `offer.json` computes 6 × 7 using the
   pure Bend function in `boards.typed.json`. The runner first checks that exact
   term with the pinned Mini type checker; it also verifies the same
   core AST occurs in the installed offer/task protocols.
2. **Iris accepts and assigns atomically.** An ordered transaction accepts the
   offer, then passes that call's result with `inputFrom: 0` to task assignment.
   Both current roots must match, and Iris must be authorized at both objects.
   The task independently checks the quoted total with the same Bend function.
3. **Moss catches a routing error.** A draft completion stages the task and first
   answer slot, then tries to send the second answer under the wrong task ID.
   The last precondition fails. No task/slot root changes and no outbox intents
   commit; the refusal is retained. Python performs no compensation or rollback.
4. **Iris and Moss race to complete the shared task.** Both use the same three
   roots and correct answer. Both are authorized collaborators; assignment
   names Moss as the responsible worker, while completion may be reported by
   either participant. Exactly one transaction commits the task and both
   answers. The other receives a stale-root refusal. The scheduling winner may
   vary; the answer and single-commit outcome do not.
5. **Both outcomes are recoverable.** Exact retries recover the winner's original
   success and the loser's original refusal. A fresh intent using a fresh root
   still cannot refill an answer slot: its current `answer == null` condition
   is now false. Quoting another reference to the same object does not create
   a new slot. The two distinct slot objects here intentionally represent two
   participant inboxes, not aliases to one inbox.
6. **Moss proposes a useful new action.** `task-v2.md` adds a one-use `reflect`
   command so the assigned worker can record an improvement for the next
   workshop. `scripts/propose.py` lowers its explicit `protocol-markdown@1`
   payload and runs `task-v2-scenarios.json` in an isolated world. This evidence
   neither changes the live task nor gives anyone authority; Eve's attempted
   installation is refused by current law.
7. **Iris installs the proposal.** The `reprogram` request supplies the exact old
   root, exact proposed protocol, and explicit complete migrated state. Existing
   completed work is preserved and `retrospective: null` is added. The host
   preserves law and advances the object version once. Moss's competing edit
   with the old root is refused; Moss then uses the newly installed `reflect`
   action on the current root.
8. **Iris seals the completed task.** An explicit empty-law revision deliberately
   removes all future invocation and management authority. Reprogramming cannot
   rescue it. Historical installation/completion retries still return their
   original receipts and cannot restore an older root or undo the lockout.

A completion commits two ordered `answer-ready` outbox records. They are
**durable delivery intents**, not proof that either recipient received a remote
message. The example has no delivery adapter. One-shot slot state and retained
request identity solve different problems: semantic duplicate publication and
recovery of the same uncertain request, respectively.

## What is being checked

`boards.typed.json` has two explicitly annotated reusable unrestricted lambdas
and checks as `Nat → Nat → Nat`. The existing raw host evaluates that same pure
term for actual arguments. This standalone type evidence does not add static
host admission: the host still validates syntax on installation and dynamically
refuses effects, stuckness, bad boundary values and exhausted budget. No new
host typing integration is implied.

Task, offer and answer-slot protocols are ordinary `delvetalk-local-v1` data.
All writes in one protocol command read that command's old state; the examples
therefore compute their results from inputs/old state rather than accidentally
expecting their new writes to be visible. Ordered calls in one transaction see
prior calls' staged state. Every semantic authorization, equality precondition,
root comparison, version change and receipt decision comes from Lean.

The conformance test reads the resulting evidence and checks the integrated
calculation, cross-object result passing, late rollback, actual competing
callers, ordered outboxes, exact retries, fresh duplicate refusal, source-bound
proposal, explicit migration, stale edit, added action, and deliberate lockout.
These are executed local-host cases, not a universal proof of transactional
invariants or distributed consensus.

## Different syntax, the same admission boundary

The Markdown card is one reviewed syntax for an ordinary protocol. An agent
could instead propose `protocol-json@1`, or an explicitly supported
`spween-scene-i64@1` scene whose lowered bundle contains a protocol. The existing
proposal path retains exact source, syntax/compiler identity and lowered
protocol identity, and runs that candidate's scenarios. It does not infer a
new parser from arbitrary prose. Source-only Spween is not an executable
protocol proposal.

A different notation changes authoring and lowering, not who may install the
result. An authorized `reprogram` always names a validated protocol, an exact
current root, and explicit replacement state; current law remains independent
of proposal prose and syntax metadata. Reprogramming is a separate governed
commit, not a call within the completion transaction. This example supplies its
state migration directly; it does not introduce a migration language, remote
package installer, authority service, or another platform.
