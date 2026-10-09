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
- Commit useful increments regularly; qualification and convergence are separate
  from checkpoints. Do not hold completed work hostage to the entire suite.
  Root owns named-path commits in this shared checkout; inspect concurrent edits.

- Lean owns the pinned source relation and local host admission. Python, JS and
  C are independent core evaluators. Python world code handles custody of a
  local file and process transport, not admission decisions.
- `spec/upstream/` pins Mini; normative semantics are byte-exact. Explicit
  audit/proof compatibility projections retain originals and exact edits in
  `spec/upstream.json`. Change its provenance and
  hashes deliberately when updating it. Do not silently fork normative rules.
- Reference dynamics, typed Mini execution, local host fixtures and deployment
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
