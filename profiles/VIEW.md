# Pure Bend views

**Installed views project snapshots without mutating live worlds.**
[Projection](../scene/projection.py) runs a synthetic result-only command through
prebuilt `delvetalk-world`; it builds nothing and touches no live database.

Protocol metadata `viewProgram` contains
`{profile:"delvetalk-bend-view-v1",term:CORE_TERM}`. The contract is:

```text
program(committedState, selectedPanel) ->
 {title:String, prose:String,
  actions:{id:{text:String, command:String, input:Record}}}
```

Only Nat/Bool/String/nested records cross this boundary. Results contain exactly
these fields; ≤64 actions name existing commands and cannot set identity,
principal, root or management operation. Installation preserves metadata;
projection validates it dynamically. Malformed programs fail closed.

```python
view = projection.project(committed_root, "workshop-sign", panel="main")
html = projection.html_view(view)
request = projection.request(view, "light", "bob", "bob-light-1")
```

Views retain exact root, panel, source, source digest and executable digest
(checked before/after). Requests preserve that root/action data; sending them
still requires current-law/exact-root admission. Panels grant no authority.
HTML escapes data; CSP forbids scripts, remote resources and form submission.

Conversion/reduction/materialization share 10,000 ticks. Effects, closures,
stuckness and exhaustion refuse. Bounds: 64 KiB input, ten-second deadline,
1 MiB output checked **after capture**. Fuel does not bound arbitrary arithmetic
or memory: this remains a trusted local workbench. Hashes prove neither semantic
equivalence nor compiler refinement.

[Working sign programs](../scene/projections/sign-v1.json),
[upgrade](../scene/projections/sign-v2.json), [room integration](../scene/ROOM.md).
Check: `python3 conformance/test_projection.py` for upgrades, stale actions,
independent panels, escaping and adversarial results.
