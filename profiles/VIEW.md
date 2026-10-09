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

A package may be inline `{modules,entry}` or an object-local
`{format:"delvetalk-source-package-ref-v1",name,entry}` selector. The latter names
`protocol.sourcePackages[name] = {format:"delvetalk-source-package-table-v1",modules}`.
Projection preserves that owning table and selector; native code resolves it.
Inspection retains both, without fetching imports or expanding executable source.

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
Spween handler scenes use this same path: generated Bend computes prose and choice
visibility from committed handler state. Town and portal cards share those bound
choices; inspection includes the exact scene and handler modules. Inventory is not
a child catalogue. A rejected turn does not change the current view.

Views receive state and panel, **no authenticated viewer**. Hiding a method neither
denies its direct invocation nor replaces current-law checks or receiving guards.

Typed menus use `delvetalk-obend-data-menu-v1`. Their state is exactly
`{model:DataWire(State)}`; the native `package-data-v1` evaluator receives that model
and a typed panel string. The source returns four fields: `title`, `prose`, `actions`
and `children`. Typed actions can be a source `nil:{}` /
`cons:{head:Action,tail:Actions}` list. Each head is either a descriptor or one
ordinary source sum alternative carrying `{key,text,command,input,visible}`.
Different alternatives may have different closed record inputs (for example
`start {}` and `choose {choice:Nat}`); constructor tags confer no authority.
All selected descriptors, including hidden entries, are checked before filtering.
Keys are unique, with at most 64 entries. Source list order survives retained
canonical storage and determines the same offered actions in town and portal.
Fixed action rows remain readable while source objects migrate; no new profile
is introduced for this data representation. Native schema checking establishes
serializability of every alternative; projection checks the actual output shape.

Children is a typed
`nil:{}` / `cons:{head:Child,tail:Children}` list; each Child contains exactly
`{key:String,label:String,object:String,panel:String}`. No ordinary JSON record is
heuristically treated as a list.

Projection checks every entry, then retains ordered children separately from
ordinary action data. Limits: 32 unique keys; key/panel 128 UTF-8 bytes, label 256,
object 512 and existing local identity constraints. Excess entries refuse rather
than truncate. Captured observations retain the exact typed result and revalidate
its normalized catalogue when read.

Source preparation invitations are an optional `invitations` record in the current
typed view, with no new view profile. Each value contains exactly
`{visible:Bool,text:String,prepare:String,fields:Record,observations:Names}`.
`Names` is the source nil/cons list of exact object identities. All descriptors,
including hidden invitations, are checked before filtering; retained source keys
remain stable across canonical storage. The decoder reads no world state.

Capture must retain the owner's exact root/table and the explicitly supplied
requested roots. The current inspection route does not enforce read permissions;
this framing is not a read-protection claim. Answers supply contribution data only; they cannot
replace the captured export, package or observation list. The @3 adapter marks
invitation-bearing objects with `preparation =
{profile:"delvetalk-source-preparation-v1",sourcePackage:TABLE_NAME}`. This profile
uses typed state. The native preparation boundary checks the actual
selected export signature and observations; source produces a turn, a question or
a refusal. Invocation and admission remain separate. Native resolution combines that owning
table with the captured invitation's actual export; no placeholder function is claimed.

If typed projection fails, ordinary inspection still exposes the retained source
and state. That recovery card offers no actions or children and claims no successful
source evaluation. Child navigation instead reports the failed view as unavailable.

Children offer **looking**, not invoking. Town cards show numbered labels. An
operator selects a captured key, reads the child's current root and declared panel,
and prepares a distinct card:

```sh
python3 scripts/town.py --clerk-state STATE capture-child PARENT KEY --alias CHILD
```

The target must already be enrolled; missing objects, undeclared panels and failed
views report unavailable. No recursive traversal, enrollment, admission or external
publication occurs. Old parent references survive later catalogue removal; child
actions still face that child's current law and the new card's exact read root.

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
stuckness and exhaustion refuse. Bounds: 1 MiB expanded internal input, ten-second deadline,
1 MiB output checked **after capture**. External authored records retain their separate 64 KiB bound. Fuel does not bound arbitrary arithmetic
or memory: this remains a trusted local workbench. Hashes prove neither semantic
equivalence nor compiler refinement.

[Working sign programs](../scene/projections/sign-v1.json),
[upgrade](../scene/projections/sign-v2.json), [room integration](../scene/ROOM.md).
Check: `python3 conformance/test_projection.py` for upgrades, stale actions,
independent panels, escaping and adversarial results; `python3 conformance/test_obend_menu.py`
for source menus, hidden-descriptor validation, town/portal agreement and real admission.
Typed checks: `test_typed_view.py` and `test_child_navigation.py` under `conformance/`.

Source collection check: `conformance/test_view_action_lists.py` joins native evaluation, town capture and portal preparation.
