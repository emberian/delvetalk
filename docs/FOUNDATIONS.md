# Specifications construct targets; hosts admit actions

**Faré supplies a construction model; Mini chooses semantics; DelveTalk exercises a pinned subset.** The sources are [LTUO archive `d7ddf53`](https://github.com/emberian/fareoo-archive/tree/d7ddf53fbdb818377b75c3d2bfafd14a072a0051), with [capture provenance](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/manifest.json), and [Mini `dcab86da`](https://github.com/emberian/minidregg/tree/dcab86da8f6153ed2b522fc61c5064608694fd83). Core checking, complete frontends and deployment are distinct claims; see [source scope](../spec/README.md).

## Construction

A specification partially describes a computation. Closing dependencies produces its target, which may be a record, function, scalar or type descriptor. Final `self` differs from inherited `super` ([LTUO §2.3.1](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/ltuo-readable.txt#L1205-L1211)). Mini uses:

```text
E : Self → Inherited → Provided
mix(lower, upper) self seed = upper self (lower self seed)
fix(E, seed) → E (fix(E, seed)) seed
```

Both layers receive the same final self. Intermediate types may differ; fixed output must match self. `fix` unfolds, without guaranteeing termination. Faré orders arguments differently: translate the convention. [Core rules](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendOpenRecursion.lean#L246-L260), [typing](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L241-L259).

## Two wrappers

| Term | Observations |
| --- | --- |
| `specification(metadata, extension)` | `metadata` selects description; application forwards to extension. |
| `prototype(spec, target)` | `reflect` selects spec; `project` selects target. |

The second implements Faré's conflation. Raw construction checks components independently, not whether target derives from spec. Mini's [library constructor](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendOpenRecursion.lean#L439-L450) instead ties:

```text
instantiatePrototype(spec, seed) =
  fix((λ whole. λ inherited. prototype(spec, spec whole inherited)), seed)
```

The wrapper is inside recursion: methods use `project(self)`. This is recursive conflation `Y(R ∘ M)`, not outside wrapping `R(Y M)` ([LTUO §6.1.3](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/ltuo-readable.txt#L2919-L2950)). It is not host provenance certification.

## Observation is not permission

Projection leaves the sibling unforced: `reflect(prototype(spec, diverge)) → spec`. Selected metadata may itself compute or diverge. Typed component/shareability checks independently reject directly wrapped activities; raw conformance terms can be ill-typed. Closures require their own capture/reuse checks. [Typing rules](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L222-L240).

Frontend composition retains nested metadata; core `mix` does not synthesize it. Reassociation can therefore change observable provenance despite equal target behavior. [Lowering](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1305-L1325).

Claim bodies typecheck as Bool and remain hidden code with status `unchecked`; retention neither evaluates nor proves them. The old `law` clause is rejected. [Claim lowering](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1791-L1813).

[Static row contracts](SPEC-BINDING.md), reflected claims and [current-law host admission](../profiles/WorldCore.lean) remain separate. Copying a prototype grants no authority. A third runtime component is unnecessary merely to carry static obligations; enforcing claims requires a named checker and admission point.
