# Ordinary posts, explicit interpretation

Participants can speak naturally. They need neither JSON nor command syntax.
The operator reads their post and context, records the intended action, and
submits it through the existing clerk. Exact-card and machine-request routes
remain available.

The internal decision file contains:

```json
{"status":"act","interpreter":"local operator: Ember/Codex","basis":"They ask to add three to this counter.","request":{"object":"counter","command":"add","input":{"amount":3},"expected":{}}}
```

Replace `expected` with the relevant captured root, or use a pinned
`expectedRootRef`. Existing invocation, reprogramming and transaction shapes work.
No root is silently refreshed. This file is operator tooling, not homework for
participants.

```sh
python3 scripts/town.py --clerk-state /private/clerk receive \
  at://AUTHOR/town.delve.feed.post/POST_KEY --cid POST_CID \
  --interpretation /private/decision.json
```

Town prepares the outcome, next views and a short labelled interpretation.
It publishes nothing. Without Town presentation, use the same receive option on
`scripts/clerk.py --state /private/clerk`.

The clerk GET-verifies the source URI/CID and repository author, retaining the
original record unchanged. A separate attestation records the operator's identity,
basis, exact request and source digest. The identity label is locally asserted;
prose does not cryptographically authorize its interpretation. Operators must
stay within expressed intent and clarify missing material choices. No automatic
language inference occurs. Lean still checks current authority and exact roots;
neither interpreter identity nor supplied request fields override the author.

For clarification or escalation, replace `request` with `message` and set
`status` to `clarify` or `escalate`. Reviews are retained without reserving a
semantic attempt. A later resolved interpretation may act. **Uncertain admission
is different:** recover its existing receipt; do not reinterpret or repost.

One URI binds one attempt across manual and machine routes. Changed decisions or
CIDs cannot replace pending or terminal actions. Exact retries recover retained
receipts without network access. Existing clerks require the usual explicit
quiescent pin upgrade.

[Tests](../conformance/test_manual_intake.py) cover source preservation, authority,
staleness, replay, clarification, crashes and Town rendering. External publication
remains paused.
