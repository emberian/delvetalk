# Work ticket

A requester posts work; another participant claims and submits it for review.
Acceptance records review, not a target mutation or external effect.

```text
draft --post--> open --claim--> claimed --submit--> submitted --accept/reject--> terminal
```

[generate.py](generate.py) supplies `build(requester,links)` and
`law(requester,workers,managers)`, producing protocol, migration, law and scenarios.
Install through a source desk or authorized factory allocation with explicit child
law. Generation and family names confer no authority.

Lean checks phases, current law and actors. Post records the actual caller;
claim records the claimant. Only that claimant submits; only the configured
requester posts/reviews. Input actor fields cannot impersonate them. Default law
grants Moss/Iris claim/submit, requester post/review, steward law revision, and
nobody reprogramming. Law changes cannot bypass protocol guards. Terminal review
cannot be overwritten.

Optional fixed `context`, `about`, `replyTo` links group work, name its subject
and name its reply target. Each is
`{format:"delvetalk-object-ref-v1",world:"...",object:"..."}`;
[components](../../scripts/references.py) allow 1–256 Unicode scalars without
controls. Inputs cannot replace links. References establish no existence,
observation, foreign resolution or grant.

Cards name the phase and show the task while open/claimed, the submitted result
before review, and the review after acceptance/rejection; details retain the
exact full state. Saved portal cards expose phase actions:
`do CARD ACTION {"task":"Describe the wing."}`. Use the card's actual token;
claim takes `{}`, submit `{result}`, review `{review}`. Stale cards refuse.
Forms bound task/result to 2,048 characters and review to 1,024. Lean requires
nonempty strings; form lengths are not admission rules. Direct requests retain
the 64 KiB host limit. No scheduler, timeout, lease, reassignment or delivery exists.

Use `transactions` to batch independently authorized `target.change` and
`ticket.accept`; either failure rolls both back. Standalone acceptance remains
legal. **`inputFrom` transfers data, not authenticated provenance or authority.**

With hosts built:

```sh
python3 protocols/work-ticket/generate.py
python3 conformance/test_work_ticket.py
```

[Tests](../../conformance/test_work_ticket.py) cover claim races, actor/revocation
checks, stale/terminal review, composition/rollback, acceptance without target
change, lost-reply replay, identity collisions and source-bound typed tokens.
Scenario discovery also includes this package. Evidence is local admission,
not distributed execution.
