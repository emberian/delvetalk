# Typed source objects

Select `objective-bend-spell@3` explicitly to author a durable object whose record
state contains supported recursive sums, such as an imported List. The shared
source adapter still binds `describe`, methods and a view from the same exact
ordered Bend package, retained once in the owning protocol's `sourcePackages` table.
Native local selectors resolve method/view entries against those exact bytes. Lean owns checking, evaluation and receiving admission.

`describe()` returns `{name,initial,methods,panels}` and optional `allocation:{limit:Nat}`. The adapter executes
it through the explicit native `run-data-v1` route, preserving `initial` as the
existing Objective Bend DataWire. Installed state is exactly `{model:DataWire}`;
the model's declared root must be a closed record. Nested closed recursive-sum
aliases are supported within native finite work/value bounds. Unknown/rigid types,
alias-only cycles, recursive row tails and any executable alternative refuse,
even when the initial value does not choose that alternative.

Methods receive `(state:State,input:DeclaredFormInput,context:Context2)` and return
exactly `{accepted:Bool,reason:String,state:State,result:PlainData}`. Inputs and
results retain the ordinary Nat/Bool/String/record boundary used by transactions.
The receiver explicitly converts the persisted model against the declared source
schema, runs the real checker and retains the new typed state. Failure rolls the
whole admission back. The ordinary transition profile emits no events; addressed messages require the
explicit additional ABIs described below.

Open structural data uses the shared [Preparation.Value](../world/lib/prelude/Preparation.obend)
sum. Method metadata may declare `inputCodec:"value"` or `resultCodec:"value"`;
the corresponding checked source argument/result must have that structural type.
The existing typed evaluator converts JSON through the same bounded native codec
used by preparation. State remains the declared typed record under `model`.
Arrays, null and numeric values need no application-specific Python decoder.
The native JSON representation normalizes signed zero; this is not preservation
of arbitrary numeric spelling. Codec metadata grants no authority or defaults.

A decision may also include [source-owned allocations](ALLOCATION.md). These are
explicit data effects, admitted atomically with state through the shared factory
checks. There is no second evaluator or source workflow interpreter.

`Context2` is `{object,principal,inputOrigin:{kind,object,command,immediatelyPrevious}}`.
The host supplies `kind` as `none`, `invoke` or `observe`. It grants no authority.
The adapter also permits this context on explicitly checked spell@2 methods and
selects plain `delvetalk-source-transition-v2` for those methods. Original Context1
methods keep transition-v1. Spell@1 is unchanged.

Native verified-artifact comparison checks that describe's initial state, each
method's state argument and returned state, and the view's state argument have
the same serializable structural schema. Transparent alias indices are local to
a compilation packet; Python never treats equal variable numbers as type identity.
The comparison retains row and alternative order. An empty List/Option value
cannot conceal incompatible declared payload schemas. Schema compatibility does
not prove behavior compatibility, source invariants or installation authority.

## Views and discovery

The @3 view receives `(state:State,panel:String)` and returns exactly
`{title,prose,actions,children}`. Title/prose/actions keep the existing plain menu
ABI. Children has this exact recursive schema:

```text
Child = {key:String,label:String,object:String,panel:String}
Children = nil:{} | cons:{head:Child,tail:Children}
```

The binding compares this schema with a separately compiled fixed contract using
the same native helper. Runtime projection retains the raw typed result and
normalizes bounded read-only children separately from parent actions. A child
reference confers no authority, enrollment or implicit fetch. Deliberate child
navigation captures a fresh distinct child card under its own current root and
law; the parent's captured catalogue remains a historical observation.

## Exact source custody

Single-module @3 uses the registered `lower_data` entry. Sealed multi-module @3
uses `lower_data_modules`. Select it before compilation:

```python
manifest = source_store.seal_modules(ordered_name_and_source_refs)
proposal = source_store.prepare_module_proposal(
    artifacts, manifest, scenario_bytes, syntax='objective-bend-spell@3')
```

The default remains spell@2. Both versions retain exact module refs/order/bytes,
examples, adapter pins and explicit desk adoption through the existing custody
pipeline. Old proposal/artifact formats retain their decoding. No fallback from
failed typed execution to plain execution exists; ordinary records named `tag`
remain ordinary data under the plain profile.

`conformance/test_obend_data_object.py` checks actual native binding and schema
refusals. The joined PlaceIndex journey separately checks receiving observation,
source-authored List membership, post-carried discovery and exact restoration;
compiler-only List probes do not establish that receiving behavior.

## Authored addressed messages

A checked source method can explicitly declare one of two additional ABIs. A
three-argument method returns Decision with the ordinary four fields plus
`emissions:{a,b,c,d}` to select `delvetalk-source-data-effects-v1`. Each fixed
slot is exactly `{enabled:Bool,to:String,command:String,recipientProgram:String,
payload:PlainRecord}`. Every slot's type is checked, including disabled slots.
There are at most four enabled emissions. The host validates each addressed
recipient command and its exact program digest, then stamps retained provenance;
source-supplied claims do not replace it. Ordinary plain results still compose
through `inputFrom`.

A receive method declares four unrestricted arguments:
`(state,input,Context2,EventFacts)->Decision4`, selecting
`delvetalk-source-data-receive-v1`. EventFacts is exactly
`{id:String,source:String,sourceProgram:String,originatingPrincipal:String}`.
The receiving core supplies these facts only for authenticated event delivery.
Direct invocation cannot manufacture them. Receive does not emit messages in this
initial profile. Context principal is the delivering caller; originating principal
is separate retained evidence. Both transitions preserve typed state under model
and current scoped law.

These declarations are actual compiler-checked argument/result types, rather than
extra behavior metadata. Existing three-argument Decision4 methods keep the ordinary
profile. Spell@2 can declare the analogous plain Context2 effects/receive ABIs,
selecting `delvetalk-source-effects-v1` or `delvetalk-source-receive-v1`. No record
named emissions in persisted plain state is interpreted as an effect declaration.

`conformance/test_obend_messages.py` checks the actual source binding and rejects
extra claimed event authority, a non-record payload and an absent Context2. The
separate resident-message journey establishes retained emission/delivery, current
law, exactly-once local consumption and recovery through real source adoption.
