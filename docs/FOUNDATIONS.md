# DelveTalk's object model: specification, target, and authority

This account binds the workbench to two independently inspectable sources: Faré's *Lambda: The Ultimate Object* (LTUO), archived at [`fareoo-archive` `d7ddf53`](https://github.com/emberian/fareoo-archive/tree/d7ddf53fbdb818377b75c3d2bfafd14a072a0051), and Mini at [`dcab86da`](https://github.com/emberian/minidregg/tree/dcab86da8f6153ed2b522fc61c5064608694fd83). The archive's [capture manifest](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/manifest.json#L1-L12) records the canonical URL, fetch date and HTML digest. Links below use its readable primary text, not the archive's later research summaries.

Faré supplies a model of modular construction. Mini makes particular operational, typing and authority choices. DelveTalk supplies a small executable workbench. Those are related claims, not interchangeable credentials. In particular, a local core checker does not supply Mini's complete source frontend, native host, or deployment evidence. See [SPEC-BINDING](SPEC-BINDING.md) for the compiler contract and [the source relation](../spec/README.md) for the locally executable scope.

## What is being composed

A **specification** partially describes a computation; a **target** is the computation obtained when its outstanding dependencies are closed. The target need not be a record: it can be a function, scalar, or type descriptor. A specification may be useful before it has a usable target, precisely because another specification can supply what it lacks. Faré distinguishes the final module context (`self`) from the inherited partial value (`super`) in [LTUO §2.3.1](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/ltuo-readable.txt#L1205-L1211).

In Mini's argument order, an extension has the shape:

```text
E : Self → Inherited → Provided
mix(lower, upper) self seed = upper self (lower self seed)
fix(E, seed) → E (fix(E, seed)) seed
```

Both layers receive the **same final self**; the upper layer receives the lower layer's result as super. Faré writes the parent and child, and the self and super arguments, in a different order: `mix child parent super self = child (parent super self) self`. Translate the calling convention rather than copying the text mechanically. Compare [LTUO §5.4](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/ltuo-readable.txt#L2591-L2628) with Mini's [mix body](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendOpenRecursion.lean#L148-L153) and [reduction rules](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendOpenRecursion.lean#L246-L257).

`fix` is an unfolding rule, not a guarantee of termination, and it returns the target without inserting a prototype wrapper. The typed core permits heterogeneous intermediate types: lower may produce `Middle` from `Inherited`, and upper may produce `Provided` from `Middle`. A fixed extension must finally return its own self type. These are explicit premises of the [mix/fix typing rules](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L241-L259), not a requirement that every layer have one identical closed row.

## Two wrappers with different jobs

Faré calls bundling specification and target **conflation**: the same prototype can be extended through its specification and used through its target. His notional representation is `Spec × Target`; he also explicitly permits adding static annotations and debugging metadata. See [LTUO §6.1.2](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/ltuo-readable.txt#L2874-L2886).

Mini separates two wrappers:

| Mini term | Stores | Elimination |
| --- | --- | --- |
| `specification(metadata, extension)` | Description/provenance and construction code | `metadata` returns metadata; application forwards to extension |
| `prototype(spec, target)` | A specification and a target | `reflect` returns spec; `project` returns target |

The [constructors](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendOpenRecursion.lean#L24-L31) and [elimination rules](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendOpenRecursion.lean#L253-L260) establish these meanings. Thus Mini's `specification` wrapper is not itself Faré's specification/target conflation; Mini's `prototype` occupies that role.

The raw prototype constructor checks the two components independently. It does **not** prove that the target was constructed from the stored spec, nor that the spec is closed or its claims hold. This permissiveness is compatible with Faré's explicit discussion of independently typed, potentially out-of-sync specification and target components in [§8.4.1.2](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/ltuo-readable.txt#L4137-L4141). A provenance-preserving constructor is a separate interface.

There is an important implemented example of that interface: Mini's [term-library `instantiatePrototype`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendOpenRecursion.lean#L439-L450). In named-variable notation its body is:

```text
instantiatePrototype(spec, seed) =
  fix((λ whole. λ inherited. prototype(spec, spec whole inherited)), seed)
```

The wrapper is **inside** the recursive knot. A method's self is the whole prototype, and selecting target fields therefore goes through `project(self)`. This is Faré's recursive conflation `Y(R ∘ M)`, not simply `prototype(spec, fix(spec, seed))`, which wraps a target-only recursion from outside (`R(Y M)`). Faré explains the difference in [§6.1.3](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/ltuo-readable.txt#L2919-L2950). The library definition is concrete source evidence; it is not evidence of a complete typed surface API or host provenance certification. The older closing paragraph of Mini's `REFLECTION.md` leaves this choice open; this later executable definition resolves that particular term-library choice.

## Laziness preserves incomplete constructions

The wrapper's fields are terms, not a literal-only metadata language. For example, in core notation:

```text
metadata(specification(2 + 3, diverge))  →  2 + 3  →*  5
reflect(prototype(savedSpec, diverge))  →  savedSpec
```

The first step selects a field without evaluating its sibling. Later steps may evaluate the selected field. This distinction allows inspection and extension of incomplete specifications whose targets diverge, the problem identified in [LTUO §6.1.2.3](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/ltuo-readable.txt#L2901-L2917). Mini names two precise one-step theorems [`prototype_metadata_unforced` and `specification_metadata_unforced`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendOpenRecursion.lean#L446-L450). Neither theorem says arbitrary projected metadata terminates.

Nor does unforced mean effect-safe. The raw source relation can represent ill-typed terms, and DelveTalk's untyped conformance runner intentionally exposes their behavior. Typed Mini separately refuses a direct activity in either specification or prototype component, or in a record field. It recursively checks shareability through these wrappers; custody does not become duplicable by wrapping it. See [component rules](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L222-L240), [field rules](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L300-L305), and [shareability](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTypes.lean#L35-L56). A closure returning an activity is a different case from an activity suspended as a value; the closure's captures and reuse discipline still need checking.

## A small object built from three specifications

This is Mini Objective Bend source, reproduced from its compiler acceptance fixture; it is not a claim that DelveTalk parses the whole surface:

```text
edition ObjectiveBend 1
record Review:
  review(value: Nat) -> Nat
  twice(value: Nat) -> Nat

spec Base for Review:
  def review(value: Nat) -> Nat:
    value + 1n

spec Twice for Review:
  requires review(value: Nat) -> Nat
  def twice(value: Nat) -> Nat:
    self.review(self.review(value))

spec Augmented for Review:
  def review(value: Nat) -> Nat:
    super.review(value) + 1n

def run() -> Nat:
  fix(compose(Base, Twice, Augmented), {}).twice(3n)
```

The seed is empty. Base supplies `review`; Twice adds `twice`, whose self points to the final object; Augmented overrides `review` at the same type, calling the inherited implementation. Therefore final `review(x)` computes `x + 2`, and `twice(3)` computes `7`, not `5`. This arithmetic is a derivation from the displayed definitions. The cited [acceptance theorem and neighboring rejection fixtures](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendSpecificationClosure.lean#L225-L244) establish frontend acceptance/refusal, not an independently run evaluation of `7` in this document.

Omitting Base leaves Augmented's inherited call unsatisfied; putting Augmented first has the same problem. Twice can still appear before the final override because self names the completed object, not the current inherited row. Nothing in this construction needs mutation or possession of a host resource.

## Metadata, claims, and authority remain distinct

Mini's frontend makes composed specifications inspectable: it wraps core `mix` with `SpecMeta.composed`, retaining the metadata of each specification operand and marking a bare extension as `extension`. A declared specification retains name, interface text, and claim names/statuses. The [implementation](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1305-L1325) matters here: **core mix alone returns construction code and does not synthesize a metadata tree**.

This metadata is observable: `compose(compose(a, b), c)` and `compose(a, compose(b, c))` build differently nested `composed` trees even when their construction code follows the same extension pipeline. An optimizer must specify which observers its equivalence preserves; equal target behavior alone does not justify changing visible provenance. The row-checker composition theorem in [SPEC-BINDING](SPEC-BINDING.md) is not a theorem of full observational equivalence for source terms.

Claim bodies are checked to return Bool and retained as hidden code; their metadata status is `unchecked`. They are not evaluated or proven by that retention. The surface deliberately rejects the old `law` clause rather than presenting an unchecked claim as enforced law: see [claim lowering](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1791-L1813) and [the refusal test](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendSpecificationClosure.lean#L194-L211).

A receiving host decides authority from its own current state and admission rules. A reflected name, a Bool claim, or a copied prototype does not grant it. DelveTalk's deliberately small [local World profile](../profiles/WorldCore.lean) makes this separation concrete: `transition` calls `authorized` on the stored object and checks its exact preimage before an invocation or law change. That local principal-list fixture is not Mini's complete custody system. New profiles must state their own authority boundary; extending the metadata schema cannot silently change one.

For an implementer replying to the proposed three-part spec: **Give static row obligations an explicit contract in the typed frontend, but the core does not need a third runtime component just to carry them. Mini already retains metadata and unchecked claims; enforcing a law requires a named checker and admission point, not a richer descriptive value. Unforced fields may contain computations, while typed component/shareability rules and host admission independently prevent activity or authority from being obtained merely by wrapping it.**
