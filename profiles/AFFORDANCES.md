# Action cards

**A card describes one captured view. It grants nothing.**
[`affordances.card(view)`](../scripts/affordances.py) emits title, prose, object,
version, mode and actions; roots/source/runtime stay in custody.
`request(view,'a1',principal,intent,fields={})` uses existing scene/projection
request constructors without refreshing or executing the view.

Aliases `a1`, `a2`, … are deterministic within a card. Transports must bind their
card reference to that exact reading. `available` means constructible;
`observedAvailable` is a scene guard hint. Lean still checks guards, current law
and exact roots. Old readings refuse; uncertain requests retain their identity.

## Declare forms

Raw commands default to inspect-only. Explicit protocol metadata enables forms:

```json
{"affordances":{"notice":{"label":"Leave a notice","fields":{
 "message":{"type":"string","maxLength":200},
 "copies":{"type":"nat","minimum":1,"maximum":8},
 "public":{"type":"bool"},
 "ink":{"type":"enum","options":["blue","amber"]}
}}}}
```

| Type | Bounds |
|---|---|
| string | Required `maxLength` ≤4096; optional `minLength`, default 0 |
| nat | Required `maximum` ≤2^53−1; optional `minimum`, default 0 |
| bool | Actual Boolean |
| enum | 1–32 distinct strings, each ≤256 scalars |

All fields are required; no defaults/coercions. Empty `fields` declares no input.
Unknown attributes, extra/missing values and malformed bounds refuse. Limits:
128 actions, 32 fields, names ≤128 scalars, optional labels ≤256. Strings count
Unicode scalars; surrogates refuse. These bounds do not restrict Bend's Nat.

Normalized fields are `{name,label,type,required:true,...bounds/options}`.
Projection inputs remain bound and cannot be overridden. Scene/projection labels
survive; metadata labels describe raw commands only. All supplied values enter
`request.input`, including fields named `principal` or `law`.

Pure `validate_fields_schema` and `validate_fields` serve renderers/interpreters.
Markup remains text. Labels are untrusted descriptions.

## Declare factory absence inputs

A factory form may additionally declare `children`, an ordered list of 1–32
distinct field names. Each names a required string field whose explicit bounds
lie within 1–64 characters:

```json
{"affordances":{"make":{"label":"Create an object","fields":{
 "name":{"type":"string","minLength":1,"maxLength":64}
},"children":["name"]}}}
```

For a captured object `workshop`, input `{"name":"lamp"}` prepares the existing
invoke envelope with `absent:["workshop/lamp"]`, alongside the exact captured
`expected` root. Child names admit only ASCII letters, digits, `_` and `-`.
No world read, program inspection, allocation prediction or authority check
occurs in preparation. Without a declaration, no absence root is invented,
even when the program's allocation expression looks obvious.

Public actions expose `children:[{"field":"name"}]`. When a projection binds
that field, the declaration is `{"field":"name","value":"lamp"}` and the
field is absent from the editable form. Bound values cannot be overridden.
`validate_children_schema(children, fields)` checks these public declarations;
`validate_fields` also checks supplied child-name values. Ordinary actions keep
their existing shape. Multiple fields may contain the same value: the absence
list is deduplicated in declaration order, while Lean owns allocation collision
and batch rollback. A lying declaration cannot authorize a different allocation:
Lean requires an absence root for every child actually created.

Admission still checks the current factory law, parent preimage, current absence,
child name, child law/protocol, shared direct-child quota and full batch validity.
The same exact prepared request recovers its retained receipt after uncertainty,
even after parent state or authority changes. Preparing another name creates
another request; it is not a retry.

`allocated_refs(receipt)` copies `[{object,root},…]` from a committed receipt's
`data.allocated`, ordered by object ID; refused or ordinary receipts yield `[]`.
The root is the creation root, which can already be stale after later transaction
steps. Renderers can link these actual child IDs and inspect them afresh. They
must authenticate receipt custody and must not manufacture successful child
links from proposed names or arbitrary command results. References grant nothing.

[Factory examples](../protocols/factories/README.md) ·
[Factory tests](../conformance/test_factory_affordances.py)

[Lean-backed tests](../conformance/test_affordances.py) · [Portal](PORTAL.md)
