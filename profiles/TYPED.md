# Typed core profile

`delvetalk-typed` checks the existing [array core AST](../conformance/AST.md)
with Mini's actual annotated partial checker. It does not evaluate terms or
change `delvetalk`, Python, JS, or C raw-core behavior. Mini's
`ObjectiveBendTypes.lean` and `ObjectiveBendTyping.lean` are byte-exact pins
recorded in [upstream.json](../spec/upstream.json). The DelveTalk adapter
imports their type decoder, quantities, contexts, assumptions, checker,
proof-carrying result, and refusal classifier. Python tests only construct
packets and compare the compiled Lean checker's answers.

```sh
LEAN_NUM_THREADS=1 lake build delvetalk-typed
python3 conformance/test_typed.py
printf '%s\n' '{"schema":"delvetalk.typed-core.v1","name":"identity","term":["lam",["bound",0]],"types":[],"annotations":[{"path":[],"domain":{"tag":"natural"},"codomain":{"tag":"natural"},"parameter":"unrestricted","reuse":"reusable"}],"bounds":[],"shareableVariables":[],"rigidVariables":[]}' | .lake/build/bin/delvetalk-typed
```

The answer is an `accepted` receipt with the arrow type, an empty external-use
vector, and `shareable: true`. This is a check against the supplied assumptions
and open context. A caller providing a custody binding does not thereby own
that custody; a successful receipt grants no authority.

## Packet and result

Each input line is one JSON object. These keys are required:

| Key | Meaning |
| --- | --- |
| `schema` | Exactly `delvetalk.typed-core.v1` |
| `name` | String echoed in the response |
| `term` | Existing array AST; naturals remain canonical decimal strings |
| `types` | Array of reusable type entries, possibly empty |
| `annotations` | Array of `{path, domain, codomain, parameter, reuse}` |
| `bounds` | Array of `{index, type}`, with distinct indices |
| `shareableVariables` | Distinct type-variable indices with checked shareability premises |
| `rigidVariables` | Distinct bounded indices treated as rigid lower bounds |

Optional `context` is an array of `{type, quantity}` in de Bruijn order (index
0 first); it defaults to `[]`. Optional `fuel` defaults to 4096 and must be at
most 16384. It bounds checking, not runtime recursion or evaluation. Unknown
top-level keys are rejected. Nested type/annotation objects use the upstream
decoder, which consumes named fields without rejecting extra fields.

Types, paths, bound indices, and fuel follow Mini's integer decoding: nonnegative
JSON integers or canonical decimal strings. Core bound-term indices retain the
core wire's safe-integer limit. Type nesting has Mini's capacity of 256, including
fully expanded table references; type tables have at most 1048576 entries.

Each input line produces exactly one output line. Normal process exit is 0
regardless of individual refusals; clients must inspect `status`. Invalid JSON,
malformed Unicode escapes, invalid packet fields, and misplaced annotations
produce `status: "error"` and
`diagnostic: {stage: "decode", kind: "malformed", message: ...}`. The name is
`null` when parsing failed or a valid name could not be read. Later jobs continue.

Successful checking returns:

```json
{"schema":"delvetalk.typed-core.v1","name":"example","status":"accepted","type":{"tag":"natural"},"uses":[],"shareable":true}
```

`type` is Mini's inferred type; `uses` counts each supplied context binding's
syntactic use; `shareable` is the inferred type's `shareableUnder` result under
the checked premises. Lambda captures have already been checked before a
reusable closure can receive its type.

A refused check returns `status: "refused"` with
`diagnostic: {stage: "checker", kind: "budget" | "ownership" | "typing", message: ...}`.
These are Mini's own diagnostic categories: it retries with ample fuel, then
with relaxed quantities. They are broad explanations, not unique failing-rule
locations. Refusal means outside the annotated fragment or budget. It is neither
the raw evaluator's `stuck` result nor a proof that no richer typing system can
accept the term. Messages are inherited upstream wording, including references
to its `limits.typeFuel`; this profile's corresponding field is `fuel`.

## Type and annotation wire

Types are JSON objects with `tag` and the following fields:

| `tag` | Additional fields |
| --- | --- |
| `natural`, `boolean`, `label`, `emptyRow` | None |
| `variable` | `index` |
| `custody` | `identity` |
| `field` | `name` string, `member` type, `tail` type |
| `arrow` | `reuse`, `parameter`, `domain` type, `codomain` type |
| `specification` | `metadata` type, `extension` type |
| `prototype` | `spec` type, `target` type |
| `variant` | `row` type |
| `computation` | `plan` type, `response` type, `result` type |
| `ref` | `index` of an earlier `types` entry |

A field chain ending in `emptyRow` is a closed row. A variable tail retains an
unknown future row. Type-table references share finite type storage; they do
not introduce recursive type aliases or bypass nesting capacity. Bounds provide
Mini's separate explicit recursive-alias mechanism.

Quantities are exactly `erased`, `affine`, `linear`, or `unrestricted`.
Reuse is exactly `once` or `reusable`. There are no inferred/default annotations.
Both affine and linear mean **at most once** in this partial safety checker;
terminal exact discharge is a separate obligation. Unrestricted bindings require
shareable types. Reusable closures may capture only used unrestricted,
shareable bindings. A once closure can capture custody, but is not shareable.

Annotation `path` is an array of zero-based source-child positions, not an index
into the JSON arrays. The root is `[]`:

| Constructor | Child positions appended to its path |
| --- | --- |
| `lam`, `inject`, `perform`, `done`, `get`, `reflect`, `metadata`, `project` | Child `0` |
| `app`, `mix`, `fix`, `specification`, `prototype`, `binary` | Children `0`, `1` in source order |
| `ifZero`, `ifBool` | Children `0`, `1`, `2` |
| `record` | Field body `i` at `[i]` |
| `extend` | Inherited target `[0]`; field body `i` at `[1,i]` |
| `case` | Scrutinee `[0]`; arm body `i` at `[1,i]` |

Only `lam`, `inject`, `perform`, and `done` consume annotations. Duplicate paths
and paths not addressing such a node are malformed; missing annotations cause
checker refusal. Their payload meanings follow Mini:

- `lam`: domain, codomain, parameter quantity, closure reuse.
- `inject`: payload domain and declared variant codomain; parameter/reuse must
  be `unrestricted`/`reusable`.
- `perform`: domain is the Plan sum; codomain is response data.
- `done`: domain and codomain name the activity's Plan and response types.

All four annotation fields are explicit even where the upstream rule ignores
parameter/reuse. Activities have type `computation`. `perform` requires a sum
of first-order Plan data and a first-order response. The pinned `done` rule only
checks that its result is not itself a computation; its signature does not
independently re-check Plan/data predicates. This adapter preserves that rule.
Activities cannot occupy record/extend fields, specification/prototype
components, sum payloads, or application arguments, including affine arguments.
An effectful case requires each arm to return an activity; wrap a pure result
with explicitly annotated `done`.

## Rigid bounds and aliases

A bound listed in `rigidVariables` is a **lower bound**: field lookup may use
its declared members, but conversion cannot identify the variable with the
bound row. A bound not listed there is an alias and may unfold one head in
Mini's checked equality. This is the checker's actual `Assumptions.rigid`
distinction, exposed here because upstream's ordinary emitted-packet decoder
sets that list to empty. It is not general subtyping or F-sub.

For example, with bound `0 = field("n", natural, emptyRow)` and checked
`shareableVariables: [0]`, `get(bound(0), "n")` checks under a context whose
binding has type variable 0, even when 0 is rigid. A function annotated to
return variable 0 may construct `{n: 1}` when 0 is an alias. That same
construction is refused when 0 is rigid: the visible lower-bound members do
not establish the unknown future Self type.

Shareability premises must pass Mini's check against their bounds. A bound
hiding custody, a once closure, or an activity cannot be declared shareable.
Bounds may not directly name activities. Canonical row equality cannot launder
a shadowed custody member into a shareable row: Mini's `agree` checks that the
conversion does not manufacture shareability.

## Evidence and scope

`conformance/test_typed.py` executes the compiled checker on positive and
adversarial packets: quantities and captures, activity cases and hidden
activities, rigid-vs-alias conversion, false shareability premises, duplicate
field laundering, exact annotation addressing, type-table expansion, and
budget/decode diagnostics. The existing four raw evaluators remain a distinct
conformance claim; there is no independent Python/JS/C type checker.

A successful Mini result contains `PartialTyping` evidence for the exact
consumed runtime term and safe-use/context/assumption premises. Native results
rely on Lean compilation. This profile does not claim preservation, demand
adequacy, terminal ownership discharge, totality of `fix`, a source-language
parser, host installation, native authority, or deployment. Its annotations are
checker input, not a proof serialized back to the client.
