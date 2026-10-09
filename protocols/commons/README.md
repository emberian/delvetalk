# Bounded commons

One ordinary object holds an authored place graph and presence slots. Commands
change only that registry. Presence grants no authority and establishes neither
physical location nor a live connection; disconnecting does not leave.

| Command | Input | Guard | Update |
| --- | --- | --- | --- |
| `enter` | `{place}` | Caller outside; destination is an entry | Caller enters |
| `move` | `{place}` | Directed edge from current place | Caller moves |
| `leave` | `{}` | Caller inside | Caller leaves |

Empty location means outside and cannot name a place. Lean checks the declared
principal and current scoped law. Input `principal`/`entity` cannot select another
slot. Grants alone cannot add participants. Defaults admit Moss and Iris at the
porch, connect porch/garden both ways, and leave the tower disconnected. Occupancy
is shared. The steward may revise law or reprogram.

Results contain `principal`, entity reference, `from`, `to`, updated `locations`
and destination `place`. Place contains name/title/description/reference and an
`exits` map of adjacent names to references; leaving returns `{}`.
[World-qualified references](../../scripts/references.py) retain exact identities;
they establish no object existence, receiving route or access. Other registries
may disagree. An outbox or copied result data proves no other admission.
Configured gates can require host-supplied transaction input provenance;
this conveys no authority.

## Authoring and custody

[generate.py](generate.py) supplies `build(participants,places,paths,entries,gates)` and
`law(participants,managers)`. Participants map to distinct entity references;
places to `{title,description,reference}`; paths are directed pairs. Bounds:
1–8 participants, 1–8 places, ≤16 distinct paths, nonempty distinct entries;
names ≤64 scalars, titles ≤128, descriptions ≤512. References use shared bounds.
Generation expands ordinary Bend; receiving budgets still apply.

With hosts built:

```sh
python3 protocols/commons/generate.py
python3 conformance/test_commons.py
```

Install generated `protocol.json` with explicit `law.json`; `migration.json`
starts everyone outside. Command terms enforce the graph; metadata describes it.
Reprogramming may replace this contract.

Whole-object roots serialize all movements. Stale refusal needs a fresh root and
intent; exact retries recover receipts across restart/law changes. A failed later
transaction call rolls movement back. No external effects occur.

[Tests](../../conformance/test_commons.py) exercise three receivers, configured
bounds, movement/type failures, races, impersonation, revocation, replay, rollback
and absence of authority transfer. They do not prove arbitrary replacements safe.

## An authored door controls a path

Optionally supply `gates=[{"from":"porch","to":"garden","object":"door",
"command":"cross"}]`. Each gate names a distinct existing directed path and a
local receiving object/command. Ungated paths keep their existing behavior.
The gate is enforced by generated command guards, not descriptive metadata.

The [paper gate](garden-gate.obend) is actual Objective Bend source using an
extension and `fix`. Its source transition checks the word, counts its approved
requests and returns `{place,description}`. A visitor submits one transaction:

```json
{"op":"transaction","principal":"moss","intent":"cross-1",
 "reads":{"door":"<complete door root>","commons":"<complete commons root>"},
 "calls":[{"object":"door","command":"cross","input":{"word":"please"}},
          {"object":"commons","command":"move","inputFrom":0}]}
```

The authored door uses the compiled source-transition profile. Commons requires
`["input-origin"]` to identify that immediately preceding successful invocation.
Explicit input, another object's equal result, another command, or an older
result separated by any call cannot open this path. Each target still checks the
visitor's own current grants. All staged changes roll back on a later failure.
Exact retry recovers the historical transaction, without a second crossing.

Wiring the edge deliberately trusts this door identity's current program as its
gate policy. The door's maker can revise its word/rule through ordinary source
adoption without replacing commons. The commons steward controls which edge
trusts which door; makers acquire no commons programming right. Revising the
door to admit everyone opens this one gate, not other actions or grants.
Adopt a gated commons revision with the existing `locations` state preserved.

This is declared movement in the existing registry. It grants no access to
unrelated garden objects. Ordinary prose can prepare the same two-call request;
no Python evaluator or automatic object delegation is involved.
[Tests](../../conformance/test_guarded_movement.py) run the real source door and
commons, including revision, forgery, reuse, revocation and atomic rollback.
The [authoring journey](../../conformance/test_guarded_authoring.py) also submits,
compiles, adopts and revises a gate through the forge, then restores its source,
history and working crossing.
