# Typed core

**`delvetalk-typed` checks array ASTs with DelveTalk's local annotated partial checker.**
It neither evaluates nor grants authority. Raw Lean/Python/JS/C evaluators remain
separate. [Adapter](../spec/Delvetalk/Typed.lean), [Mini origin](../spec/bend/origin.json),
[AST](../conformance/AST.md).

```sh
LEAN_NUM_THREADS=1 lake build delvetalk-typed
python3 conformance/test_typed.py
```

Each JSON input line yields one response; process exit 0 does not imply acceptance.
Required fields:

| Field | Value |
| --- | --- |
| `schema` | `delvetalk.typed-core.v1` |
| `name`, `term` | Echoed string; array AST |
| `types` | Reusable type table |
| `annotations` | `{path,domain,codomain,parameter,reuse}` entries |
| `bounds` | Distinct `{index,type}` entries |
| `shareableVariables`, `rigidVariables` | Distinct indices |

Optional `context` lists `{type,quantity}` in de Bruijn order; default `[]`.
`fuel` defaults to 4096, maximum 16384. Unknown top-level fields refuse;
nested decoders tolerate extras. Integers accept nonnegative JSON
integers/canonical decimal strings; core indices retain safe-integer limits.
Expanded type depth ≤256; table size ≤1048576.

Accepted responses contain `type,uses,shareable` under supplied assumptions.
Refusals classify `budget|ownership|typing`; decode errors classify `malformed`.
Malformed responses use `status:"error"`, `stage:"decode"`; checker refusals
use `status:"refused"`, `stage:"checker"`. Jobs continue after failure. Refusal establishes neither evaluator stuckness nor
untypability in richer systems.

Types have `tag` and these fields:

| Tag | Fields |
| --- | --- |
| `natural,boolean,label,emptyRow` | None |
| `variable,ref` | `index` (references select earlier table entries) |
| `custody` | `identity` |
| `field` | `name,member,tail` |
| `arrow` | `reuse,parameter,domain,codomain` |
| `specification` | `metadata,extension` |
| `prototype` | `spec,target` |
| `variant` | `row` |
| `computation` | `plan,response,result` |

[Local decoder](../spec/bend/Theory/ObjectiveBendTyping.lean).
References are finite; bounds provide aliases. Rigid bounds expose members
without identifying the variable with its row; this is not general subtyping.
Shareability premises must withstand custody/closure/activity and shadowed-field
checks.

Quantities: `erased|affine|linear|unrestricted`; reuse: `once|reusable`.
A once closure can capture custody but is not shareable.
Both affine and linear enforce **at most once**. Unrestricted types must be
shareable; reusable closures capture only used unrestricted shareable bindings.
Terminal discharge remains separate.

Annotation paths address source children, not JSON slots: unary `[0]`,
binary `[0|1]`, conditionals `[0|1|2]`, record field `[i]`, extend/case target
`[0]` and field/arm `[1,i]`. Only `lam,inject,perform,done` consume annotations;
duplicate/misplaced paths are malformed, missing annotations refuse. All payload
fields are explicit. `lam` supplies domain/codomain, parameter quantity and
closure reuse; `inject` supplies payload domain/variant codomain; `perform`
supplies Plan domain/response codomain; `done` supplies activity Plan/response.
`inject` requires unrestricted/reusable; `perform` requires
first-order Plan/response data. `done` only excludes computation-valued results;
it does not independently recheck Plan/data predicates. Activities cannot hide
in data or arguments; effectful cases need activity-valued arms.

[Executable cases](../conformance/test_typed.py) cover wire details and adversaries.
Accepted native results contain `PartialTyping` evidence internally, relying on
Lean compilation; receipts serialize no proof. Preservation, demand adequacy,
totality, ownership discharge, installation and deployment remain separate claims.
