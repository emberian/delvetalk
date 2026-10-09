# Generic sums and functions

**Implemented in source, 2026-10-09; native qualification is snapshot-scoped.**
The native hosted frontend specializes user-defined generic sums and functions
into ordinary Bend declarations. `Generics.lean` enforces 256 instances, 262144
expanded AST visits, 8 MiB of expanded string payload, and nesting depth 256.
Instance keys are fixed-size SHA-256 fingerprints, preventing nested JSON key
escaping from amplifying type identities. Open Self/Super specializations refuse;
regular concrete recursive instances remain supported. Instance identities bind the defining
module's exact source hash and resolved type argument declaration identities.
`genericInstances` records definition identity, arguments and source span in
package artifacts; source and locked import transcripts retain original bytes.

`List.obend` supplies length, append, concat, any, filter, map and fold.
Preparation Names/Values/Fields/Requests/Observations/Reads/Effects, Allocation.Allocations,
Emissions.Emissions, Encounter.Children, EncounterPages.Pages, ExhibitList.Entries,
Document.Documents, containment Relations.Members, Consent.Peers, Directory.Doors,
and Commons Participants/Places/Paths/Gates now alias its instances. Source membership, capacity,
first-match removal, and paging rules remain in their consumers. Paged encounters
use the canonical cons head/tail shape with a child list as each head.
Document's plainItems uses a generic fold, including the mutual Document/list
cycle. Private generic-development native qualification qualifies the concrete generic/list and eleven existing template tests, including typed offers, quotations, native
old/new list wire and type compatibility, and the actual conversation renderer
after serializing its retained contribution state. Concise test-local adversarial source
workloads also exercise instance, expanded syntax, and expanded string payload
capacity refusal before typing or evaluation. Scholar regressions cover method
rows and spec lexical binders, rigid open argument refusal, revised imported
helpers, recursive discovery-order symmetry, and sixteen nested list types.
Combined receiving-path and retained conversation qualification must use the
matching combined native build; the earlier shared binaries do not establish it.

## Proposed surface

```text
sum List<T>:
  nil: {}
  cons: {head: T, tail: List<T>}

def length<T>(xs: List<T>) -> Nat:
  match xs:
    case nil(_): 0n
    case cons(c): 1n + length::<T>(c.tail)

def example() -> Nat:
  length::<String>(List::<String>.cons({head: "moth", tail: List::<String>.nil()}))
```

Use explicit value specialization:
`length::<String>` and `List::<String>.nil`, with `List<String>` in type positions.
The explicit marker avoids ambiguity with existing comparison expressions.
Specialized functions remain ordinary first-class functions. Rank-1 parameters
suffice; polymorphic runtime values and higher-kinded parameters are out of scope.
Source aliases preserve domain names: `type Names = Lists.List<String>`.
Alias-qualified constructors such as `Names.cons(...)` resolve to the same
concrete sum instance.

## Specialization boundary

Parse type parameters and applications structurally, resolve names in the
defining sealed module, then instantiate referenced declarations before ordinary
elaboration. Do not substitute source strings. An instance key includes the exact
generic declaration identity and resolved type-argument identities, independent
of import spelling. Fresh generated names must not capture authored names.
Retain original source, selected imports, type arguments and instance-to-source
locations for inspection and diagnostics.

Allocate each recursive instance identity before expanding its fields. Initially,
recursive components must recur at identical type arguments: `List<T>` may contain
`List<T>`; expanding `Nest<T>` into `Nest<List<T>>` is refused. Support the regular
mutual cycle `Value` → `List<Value>` → `Value`. Bound both instance count and total
expanded syntax size, refusing before constructing an oversized result. Select
the concrete limits using the consumer cuts below; increasing evaluator budgets
is not the solution to expanding specialization.

The output uses existing sums, records, functions and checked recursive types.
There are no new evaluator forms, runtime type arguments, Python generators or
dynamic `Value` conversions. The existing checker must validate every concrete
instance, including quantity and sharing constraints. A successful instantiation
does not prove that every possible type argument would work. Wrong arity,
unresolved types, forbidden recursion and unsafe duplication must fail with the
generic definition and selected instance identified.

## Consumer cuts and acceptance

The reviewed families are `Children`, `Values`, `Fields`, `Names`, `Requests`,
`Observations`, `Reads`, `Effects`, `Allocations`, `Documents`, `Contributions`,
`Outcomes`, `Doors` and `Pages`. Thirteen use `nil`/`cons` with `head` and `tail`.
[`Pages`](../../world/lib/prelude/EncounterPages.obend) instead uses `items` and
`tail`, and its append/offer functions implement bounded paging. Preserve that
policy and wire shape, or supply an explicit adapter; it is not a drop-in rename
to `List<Children>`. Context records describe different domains and need a
separate interface decision.

1. Replace [`Preparation.Names`](../../world/lib/prelude/Preparation.obend) and
   [`Encounter.Children`](../../world/lib/prelude/Encounter.obend) with shared
   list instances and reusable traversals. Exercise a real preparation question
   and a paged encounter consumer. Keep membership keys, capacity checks and
   paging policy in source; generic `map`, `append` and predicates do not decide
   those policies.
2. Replace [`Document.Documents`](../../world/lib/document/Document.obend) with
   `List<Document>`, establishing the mutually recursive document/list case.
   Run the actual template and conversation renderers, including typed offers,
   quotations and retained history. Remove the duplicated traversal only after
   those consumers use its specialization.

Compare old/new serialized variants and native codec acceptance, retaining
`nil`/`cons` and `head`/`tail` where promised. Measure compile size, instance count,
runtime nodes and ticks. Test independently imported generics with identical
names, wrong element types, expansion refusal, and affine/linear payloads where
an operation would duplicate them. Wire compatibility does not authorize
reinterpretation of retained source identities; upgraded packages undergo normal
compilation and governed adoption.

The main risks are instance explosion, recursive-type identity canonicalization,
name capture, row conversion and weakening quantity checks. These two consumer
cuts are the qualification gate before a broad collection rewrite.

## Ownership scope

The current List API uses ordinary unrestricted parameters and matches whose
payload must be shareable. It is a collection API for shareable data and reusable
functions, not a generic affine container interface. Specializations still pass
the existing quantity checker: affine/linear duplication refuses. Supporting
owned payload traversal needs a deliberate core match/interface change; generic
syntax does not grant that capability.
