# Source specification reflection

Compile an entry returning `Specification<T>`, then send the compiled artifact to
`delvetalk-obend` with `op:"inspect-spec-v1"`. The receiver replays its exact source,
checks the entry, applies the edition's `metadata` observer, checks that wrapped expression,
and evaluates its `SpecMeta` through the bounded typed-data route. The response
retains the source and packet hashes, entry, typed metadata and execution costs.

This inspects **source assembly**, not a live object address. Nothing loads ambient
code, changes a resource, establishes authorship or grants invocation rights.

[ReflectiveDoor.obend](../syntaxes/examples/reflection/ReflectiveDoor.obend) shows
the same operations inside ordinary Bend:

```text
def reflected() -> Specification<Door>:
  reflect(prototype(Base, unfinished()))

def assembly() -> Specification<Door>:
  compose(reflected(), Grow)

def inspect() -> SpecMeta:
  metadata(assembly())
```

`unfinished()` diverges, but reflecting and reusing its stored specification works.
Applying the composed specification computes 13; selecting the unfinished target
instead exhausts its budget. Association changes metadata trees even when completed
answers agree. A prototype is a raw lazy pair: its specification need not have built
its target. Reflection does not certify such provenance.

`SpecMeta` is the existing declared/composed/extension sum. A declared specification
provides its qualified name, interface **text**, and claims with `unchecked` status.
Claims are not enforced contracts. The interface string can be displayed or compared;
this route does not add a source-language JSON parser or closure-code introspection.

## Reusable typed prototypes

The DelveTalk frontend parses and lowers `prototype`, `reflect`, `metadata`, and
`targetOf`; the core checker and machine implement them. The
frontend also supports `Prototype<S,T>` parameters, returns
and inferred local bindings. `reflect` returns `S`; `targetOf` returns `T`.
The two components are checked independently, as with the existing raw core pair.

[ReusablePrototype.obend](../syntaxes/examples/reflection/ReusablePrototype.obend)
returns a prototype, passes it through a specification revision, then reuses it
without forcing its unfinished target. It also uses `extend` after a `let` and
inside open Self/Super layers; synthesized extension types retain abstract row tails.
Prototypes remain executable values, not serializable package data.

The frontend and checker are maintained as ordinary local source under
`spec/bend/`. [Mini origin](../spec/bend/origin.json) records the upstream baseline;
local repairs do not require replacement patches or upstream byte equality.
Runtime custody binds the actual local source and executable. A provenance-establishing
constructor or reflective `self` inside the recursive knot remains a separate design.

[Native tests](../conformance/test_reflection.py) ·
[observer](../spec/Delvetalk/Reflection.lean)

## Captured installed definitions

A source preparation invitation can additionally declare `definitions`, a bounded
list of `{object, package}` selectors. Each object must already be declared in the
invitation's observations. Custodians capture those roots under the actual caller's
current read law. Native preparation rechecks current reads and selects the exact
source table of that captured revision; it never refreshes modules from the current
object or reads host source files.

Such an export receives a fifth `Reflection.Definitions` argument. Ordinary
preparation exports keep their four arguments. A definition contains object,
version, program digest, package name and the table's ordered exact `{name, source}`
modules. Selection is limited to sixteen tables, sixty-four modules per table and
one MiB of aggregate source. Selection grants no effect or management authority.

The Writing card's `prepareInspect` uses this data to produce an `inspection`
response: source-authored message, logical Value and the existing Document ABI.
Module contents appear as `Document.source` nodes. The generic client renders this
read-only document; it does not supply an application-specific source inspector.
The retained source may then be revised, checked with authored examples and released
through the ordinary Candidate and current-law adoption pipeline. A source edit
invalidates earlier action roots. Current read revocation also blocks a retained
inspection, even when its earlier source revision remains admitted history.

This is source-environment reflection. The trusted compiler and admission boundary
remain responsible for checking the resulting revision; no native rebuild is part
of an object's source revision.
