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

[Lean-backed tests](../conformance/test_affordances.py) · [Portal](PORTAL.md)
