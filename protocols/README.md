# Authored world objects

These objects implement behavior in Bend. The native source host checks and
admits their state changes; platform scripts package exact source and retain
physical custody. Start with [the local workshop](workshop/README.md).

```sh
make build scene-build
python3 scripts/workshop.py /tmp/my-delvetalk
python3 scripts/portal.py /tmp/my-delvetalk --allow-local-actions --principal moss
```

Choose a fresh directory. Local principal names are trusted caller assertions.
Inspect source, state, law and offered actions before acting. Exact captured roots
and current authority decide admission; copying a reference grants no authority.
Missing replies require recovery of the original attempt.

Reusable definitions live in [the world library](../world/lib/).
[Source objects](../profiles/TYPED-SOURCE-OBJECTS.md) define the checked interface;
[source desks](../profiles/DESK.md) retain proposals and reports before explicit
adoption. [Examples](../examples/) and [conformance](../conformance/) provide
refuting cases. Check success, stale roots, unauthorized callers, repeated actions
and uncertain replies against the matching native/source closure.

[Current contracts](../docs/INDEX.md) · [Remaining work](../BACKLOG.md)
