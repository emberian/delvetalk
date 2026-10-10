# Codex review of a3e1fb2 (gpt-6.1-sol, six facets, read-only): routing

Read each facet file here; findings are ranked by the reviewer. The root's
decisions before dispatch (made 2026-10-10 evening, not yet dispatched):

- One structural fix closes objects 1-8 at once: a generic state write from
  outside the object (`world-propose`, another object's `write`) gets its own
  request kind, `proposed`, so every existing law that admits `kind == 0`
  writes keeps admitting only the object's own method writes; a law that
  wants proposals says `request.kind == proposed`. Host lane, with a kernel
  grammar line for the new kind name. Objects then add `unchanged(owner)` as
  belt, and fix 9-15 (cooldown eviction, subsMax 32, seed length in
  fromFields, the planting post into settled, durable anthology numbers, one
  budget per composite card, the clipped footer) and Deal's requester-only
  signatures.
- Host, in order: 1 settling exposes others' receipts; 2 default publishPage
  leaks private state; 3 lawReads bypasses read policy; 7 a rehashed snapshot
  replaces a law; 6 `ended` to a non-exposing supervisor; 5 reprogram drops
  fixed protection (also docs 1); then the `proposed` kind; then 4, 8, 9, 10,
  11, 12 (direct turns honour form bounds; also agent 3), 13, 14, 15; docs 2
  (extension pins by sourcePin); agent 11 (per-reader action filter), 12
  (migration diagnostic in the refusal), 14 (object names and spell names
  share one rule); transport 9, 10, 12 (quota and model-retry decisions into
  the host; repository cursors by (height, item)).
- Kernel: 1 natural arithmetic allocation bomb (preflight by bit length); 3
  turn-resume trusting a supplied digest (require the retained suspension or
  the journaled digest); 4 textHasAny quadratic; 7 negative integers past
  the CBOR range collide; 8 byte budget on legacy sizes; 9 labelEqual
  tariff; 10 take/drop preflight; 2, 5, 6 fixed fields, declares and remove
  sugar through layers and aliases.
- Transport: 1 is already fixed (the deploy lane changed the healthcheck); 2
  posting idempotence (deterministic record key; retry registration apart
  from sending); 3 pending interpretations resubmitted after a restore; 4
  bound workers and absolute deadlines; 5 the hand on a loopback listener
  only; 6 address limits on anonymous pages; 7 and agent 8: Python stops
  classifying spells, the host's parser decides (an op `spell-classify`);
  8, 11, 13, 14, 15; docs 4 / agent 6 receipts and slugs on successful
  drafts; agent 13, 15.
- Docs: 3, 7, 8, 9, 10, 11, 12, 13 (reconcile the backlog and the brief);
  agent 9, 10.
- Objects, agent facet: 1 the planting acknowledgement prints the bell's rain
  spell; 2 a first prose request is not discarded for the menu; 4, 5, 7.

Then: the token lane's report (the glyph lexicon follows it), a redeploy
from the head with a clean re-genesis (nothing is posted yet), run 12, and
the ring once ember creates the stream, the six rcs and the key.
