# Small governed factories

These are ordinary `delvetalk-local-v1` protocols admitted by the existing world,
transactions and compiled hosts. Install one as an object with an explicit law;
no helper creates children on its behalf. Both examples declare the `make` form
and a `name` input, and limit the factory to 16 current direct children. Their
`last` state records the supplied name after successful allocation.

* [object.json](object.json) creates a small editable text object. The maker
  receives its flat law, including write, reprogram and law authority. Its write
  form has a 512-character bound; form bounds are presentation constraints,
  not a new kernel policy for callers using raw requests.
* [source-desk.json](source-desk.json) creates an exact copy of the existing
  [source desk](../source-desk/protocol.json). The maker may submit and adopt;
  `initial.compiler` selects the sole compiled/failed reporter (`compiler` in
  the example). Child reprogram/law grants are empty. Factory management can
  explicitly replace the factory protocol/state to configure future children;
  it receives no implicit authority over existing desks. A source desk still
  needs the ordinary trusted compiler worker and target adoption authority.

The examples intentionally use literal child protocols and explicit child-law
expressions. Another authored protocol, including a place or work ticket, can
be embedded in the same allocation descriptor. Metadata does not evaluate that
protocol or establish its identity, and it does not infer allocation names.

Read a factory, retain its exact root, obtain `affordances.card(view)`, then
prepare `affordances.request(view, 'a1', principal, intent, {'name':'lamp'})`.
The resulting existing invoke envelope includes the declared absence input.
After execution, use `affordances.allocated_refs(receipt)` to obtain actual
creation references. Opening a child reads its current state; an old creation
root does not silently refresh.

The [actual Lean tests](../../conformance/test_factory_affordances.py) cover all
three receiving profiles, usable child forms, compiler/maker separation, exact
retry, current authority, quota, occupied names and complete rollback when
metadata disagrees with a program or a later child collides.
