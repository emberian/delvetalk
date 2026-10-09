# Source specification reflection

Compile an entry returning `Specification<T>`, then send the compiled artifact to
`delvetalk-obend` with `op:"inspect-spec-v1"`. The receiver replays its exact source,
checks the entry, applies Mini's `metadata` observer, checks that wrapped expression,
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

The pinned frontend parses and lowers `prototype`, `reflect`, `metadata`, and
`targetOf`; the core checker and machine implement them. DelveTalk's explicit
frontend compatibility repair also supports `Prototype<S,T>` parameters, returns
and inferred local bindings. `reflect` returns `S`; `targetOf` returns `T`.
The two components are checked independently, as with the existing raw core pair.

[ReusablePrototype.obend](../syntaxes/examples/reflection/ReusablePrototype.obend)
returns a prototype, passes it through a specification revision, then reuses it
without forcing its unfinished target. It also uses `extend` after a `let` and
inside open Self/Super layers; synthesized extension types retain abstract row tails.
Prototypes remain executable values, not serializable package data.

The repair is recorded as exact reversible edits in `spec/upstream.json`, tied to
the original upstream Git commit and SHA-256. `scripts/check_source_pins.py` reconstructs
and verifies those original bytes without retaining a duplicate archive. Core rules
and the checker are unchanged. A provenance-establishing constructor or reflective
`self` inside the recursive knot remains a separate design.

[Native tests](../conformance/test_reflection.py) ·
[observer](../spec/Delvetalk/Reflection.lean)
