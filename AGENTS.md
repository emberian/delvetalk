# Working on DelveTalk

DelveTalk is a small semantics and protocol workbench. Keep behavior precise
and contributions runnable; a convention becomes useful when its failure case
can be reproduced.

- DelveTalk is a self-contained-as-possible, metaprogrammed Bend system. World
  behavior, workflows, interaction logic, scene execution and metaprogramming
  belong in Bend. Python is not an application implementation language here:
  keep only necessary platform transport, physical custody and process I/O.
  A Python generator of executable AST/source still authors behavior; native
  execution of its output does not satisfy this boundary. Existing such code
  is replacement work, not precedent. See docs/design/BEND.md.
- Current swarm uses explicitly selected gpt-6.1-sol; never reactivate inherited Astra agents. Model changes need Ember instruction.
- Commit useful increments regularly; qualification and convergence are separate
  from checkpoints. Do not hold completed work hostage to the entire suite.
  Root owns named-path commits in this shared checkout; inspect concurrent edits.
- Review includes adjacent design and efficiency problems, not only the assigned
  checklist. Propose improvements and own coordinated fixes. Frozen snapshots
  preserve test evidence; they do not freeze development or suppress findings.
- Read `BACKLOG.md` when resuming or dispatching a wave. Record every discovered
  followup there with an owner or explicit queued status and a completion check;
  reconcile results before dispatching the next wave. Do not keep competing queues.

- Lean owns the DelveTalk source relation and local host admission. Python, JS
  and C are independent evaluators of their supported core fragment. Python world
  code handles physical custody and transport, not admission decisions.
- `spec/bend/` is the editable DelveTalk edition of Objective Bend, forked from
  Mini. `spec/bend/origin.json` attributes the upstream baseline; it does not
  constrain local source to upstream bytes. Edit semantics directly with their
  proofs, codecs and tests. Runtime pins bind the actual local source closure;
  local changes need no compatibility-replacement script or origin-hash update.
- Reference dynamics, typed edition execution, local host fixtures and deployment
  are different claims. Report the one actually checked.
- Preserve unrelated work. Stage named files; no blanket reset/stash/cleanup.
- Use `make check`. When debugging, use the narrow matching target first. Keep
  local Lean compilation to at most two processes; build the small targets
  serially. No Mathlib build is required here.
- Protocol contributions need explicit state/authority, positive and adversarial
  scenarios, and a named host profile. Exact preimages, current law and retained
  receipts must not be replaced by client-side conventions.
- A copied reference does not copy activity/custody or confer authority. An
  outbox intent does not establish exactly-once external delivery.
- Repository authorization does not authorize posting to Delve, editing the
  live wiki or messaging its participants. Keep personal files, notification
  transcripts, credentials, local databases and caches out of Git.
