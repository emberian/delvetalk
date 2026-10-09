# Keep specifications open; close targets exactly

**A Self bound is a lower bound, not the final object type.** The [local edition](../spec/README.md) maintains these rules from the [Mini baseline](https://github.com/emberian/minidregg/tree/dcab86da8f6153ed2b522fc61c5064608694fd83), informed by [LTUO §8.4.1.3](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/ltuo-readable.txt#L4143-L4171). These rules cover annotated equality/rows, not general subtyping or the complete hosted object interface. [FOUNDATIONS](FOUNDATIONS.md) defines runtime wrappers.

## Bind once, instantiate later

`Self` denotes the future final type; `Super` denotes the immediately inherited row. Self is required; omitted Super defaults to `{}`. A binary method `heavier(other: Self) -> Self` preserves the richer future object, not merely its visible lower-bound fields.

The compiler checks/caches a template with two rigid bounded variables, then instantiates `Self = target`, `Super = beneath`. Bounds support lookup, not conversion of rigid variables into their rows. Emitted recursive aliases may unfold one declared head. [Template checking](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1500-L1524), [instantiation](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1641-L1660), [alias/conversion rules](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L8-L98).

## Three static rows

| Layer field | Obligation |
| --- | --- |
| `assumes` | Members available through final Self. |
| `consumes` | Members required through inherited Super. |
| `provides` | Additions or same-type overrides. |

```text
C_L(S,I) = assumes_L ⊆ S ∧ consumes_L ⊆ I ∧ no type-changing override
F_L(S,I) = provides_L ++ I                 -- first name wins
C_(A;B)(S,I) = C_A(S,I) ∧ C_B(S,F_A(S,I))
F_(A;B)(S,I) = F_B(S,F_A(S,I))
```

Membership requires exact canonical member types: width openness, not arbitrary member subtyping. Explicit whole-row extensions use their declared result instead of appending inheritance. [`Layer.leaves` and checks](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendContract.lean#L44-L113).

[`run_append`, `checkLayer_ok` and `discharge_ok`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendContract.lean#L115-L180) prove composition/checker properties; [the elaborator invokes those checks](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1587-L1634). They do not establish full observational equivalence.

Every type-changing override refuses. Diagnostic `replaceUndeclared` does not imply an available replacement declaration. At `fix`, the final row has exactly the declared names/types. All-open chains need an explicit final type; lower bounds do not supply one. [Acceptance/refusal fixtures](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendSpecificationClosure.lean#L255-L284) witness richer-tail reuse and binary-Self checking, not universal frontend equivalence.

## Separate obligations

A portable contract could carry rows, closure mode and checker/source version; the receiver must validate it against code. Metadata alone is no certificate or reason for a third runtime component. Proved checker laws, retained `unchecked` claims and host admission predicates have different force; overrides need not preserve claim truth.

Shareability separately checks components, fields and unknown tails. Canonicalization can erase shadowed custody: checked conversion uses `agree`, not merely `sameType`, to prevent manufacturing reusable values. Preserve [that distinction](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L112-L136) and [shareability checks](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTypes.lean#L35-L56). Open rows do not imply duplicable custody.
