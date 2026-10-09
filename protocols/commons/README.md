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
may disagree. No `inputFrom`, outbox or offered cross-object call authenticates
another place's admission.

## Authoring and custody

[generate.py](generate.py) supplies `build(participants,places,paths,entries)` and
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
