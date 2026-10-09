# Pure Bend views

**Installed views project snapshots without mutating live worlds.**
[Projection](../scene/projection.py) runs a synthetic result-only command through
prebuilt `delvetalk-world` or `delvetalk-compiled`; it builds nothing and touches
no live database.

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

Source views use `delvetalk-obend-view-v1` with a source-only package. Authors
write a real Bend `view(state, panel)` definition, as in the
[moon spell](../syntaxes/examples/moon-door.obend); Lean parses, types and executes
it. World-bound observations check their retained compiled-runtime pins before
execution. Captured cards must agree with their book's runtime, including panels.
Standalone observations retain their actual runtime instead of claiming a world's.

Contextual menus use `delvetalk-obend-menu-v1` with the same package descriptor.
Each source action adds `visible:Bool`, allowing a fixed typed row to offer different
actions as state changes:

```text
light: {visible: if state.lit then false else true,
        text: "Light the lantern", command: "light", input: {}}
```

Every descriptor is materialized and validated, including hidden entries; then
only visible actions enter ordinary `ViewData`, with `visible` removed. Inspection
retains both the raw source result and normalized view. Existing v1 is unchanged.
Views receive state and panel, **no authenticated viewer**. Hiding a method neither
denies its direct invocation nor replaces current-law checks or receiving guards.

```python
view = projection.project(committed_root, "workshop-sign", panel="main")
html = projection.html_view(view)
request = projection.request(view, "light", "bob", "bob-light-1")
```

Views retain exact root, panel, source, source digest and executable digest
(checked before/after). Requests preserve that root/action data; sending them
still requires current-law/exact-root admission. Panels grant no authority.
HTML escapes data; CSP forbids scripts, remote resources and form submission.

Conversion/reduction/materialization share 10,000 ticks for core views or the
compiled host's 100,000 for source views. Effects, closures,
stuckness and exhaustion refuse. Bounds: 64 KiB input, ten-second deadline,
1 MiB output checked **after capture**. Fuel does not bound arbitrary arithmetic
or memory: this remains a trusted local workbench. Hashes prove neither semantic
equivalence nor compiler refinement.

[Working sign programs](../scene/projections/sign-v1.json),
[upgrade](../scene/projections/sign-v2.json), [room integration](../scene/ROOM.md).
Check: `python3 conformance/test_projection.py` for upgrades, stale actions,
independent panels, escaping and adversarial results; `python3 conformance/test_obend_menu.py`
for source menus, hidden-descriptor validation, town/portal agreement and real admission.
