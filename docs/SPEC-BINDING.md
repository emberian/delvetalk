# Binding open specifications without closing them too early

This is the implementation contract at Mini [`dcab86da8f6153ed2b522fc61c5064608694fd83`](https://github.com/emberian/minidregg/tree/dcab86da8f6153ed2b522fc61c5064608694fd83), interpreted alongside Faré's archived LTUO. It describes the existing annotated row fragment, not a promise of general subtyping or of a complete Mini source frontend inside DelveTalk. Read [FOUNDATIONS](FOUNDATIONS.md) for the runtime specification/prototype distinction.

## The binder is a lower bound, not the final type

Mini supports source declarations of the form:

```text
spec Heavier[Self has {weight: Nat, heavier(other: Self) -> Self},
             Super has {weight: Nat}]:
  def heavier(other: Self) -> Self:
    if other.weight <= self.weight then self else other
```

(The actual source fixture writes the header on one line.) `Self` ranges over a future final type with at least those members, at the given types. `Super` ranges over the row inherited immediately beneath the layer. Omitting the Super binder defaults its bound to `{}`; a Self binder is required. See [binder parsing](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L641-L654).

The binary method's argument and result mention **the future Self**, not merely `{weight: Nat}`. Thus a layer can return the richer object supplied by a later composition without claiming that a freshly made record containing only `weight` is such an object. Faré makes the analogous parameterization explicit in [LTUO §8.4.1.3](https://github.com/emberian/fareoo-archive/blob/d7ddf53fbdb818377b75c3d2bfafd14a072a0051/raw/mirrors/ltuo/2026-10-03/ltuo-readable.txt#L4143-L4171): inherited, required, and provided types depend on the common final self. Mini implements a restricted annotated equality/row system inspired by that need; it does not implement every intersection/subtyping rule in those formulas.

The compiler elaborates an open template once with two rigid bounded variables and caches it. A later composition instantiates that checked template with `Self = target`, `Super = beneath`. See [template construction](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1500-L1524) and [instantiation](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1641-L1660). This is a source implementation connection, not by itself a general theorem about every imaginable compiler transformation.

The distinction between a rigid variable and an alias is essential. Lookup can consult a rigid variable's bound; conversion cannot unfold that variable to the bound row. After instantiation, emitted recursive aliases can unfold one declared head. [`Assumptions.alias`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L8-L35) enforces the distinction; [`sameType`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L84-L98) supplies the limited conversion. Replacing `Self` with its lower-bound row during template checking would erase the very future members the binder exists to preserve.

## Three row roles, one executable composition contract

A row triple is useful as a **static contract**. Mini already represents it with `Layer.assumes`, `Layer.consumes`, and `Layer.provides`:

| Row role | Checked against | Purpose |
| --- | --- | --- |
| `assumes` | Final Self | Members the layer can use through self, including requirements |
| `consumes` | Current inherited row | Members needed through super |
| `provides` | Row left by this layer | Additions or same-type overrides |

For an ordinary specification layer `L`, the row transformer is
`F_L(S, I) = provides_L ++ I`, with first occurrence of a name winning.
The contract is:

```text
C_L(S, I) = assumes_L ⊆ S
         ∧ consumes_L ⊆ I
         ∧ no provided member changes an inherited member's type

C_(A;B)(S,I) = C_A(S,I) ∧ C_B(S,F_A(S,I))
F_(A;B)(S,I) = F_B(S,F_A(S,I))
```

Here `⊆` means membership with **exact canonical member-type agreement**. It is width openness, not permission to substitute an arbitrary subtype for a member. An explicit `extension` can declare its whole result row; `Layer.whole` then uses that row rather than automatically appending the inherited row. This distinction is represented by [`Layer.leaves`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendContract.lean#L44-L68).

[`checkBounds`, `checkProvides`, `run`, and `close`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendContract.lean#L69-L113) implement the obligations. `run_append` proves the sequential composition equation; `checkLayer_ok` proves that an admitted layer met its assumptions and changed no inherited member type; `discharge_ok` proves the final declared row is supplied without extra names. These are [theorems about the executable row checks](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendContract.lean#L115-L180), which the elaborator [actually invokes](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1587-L1634).

**Every type-changing replacement is currently refused.** The diagnostic is named `replaceUndeclared`, but there is no source declaration form that authorizes a replacement. An absent member may be added and a present member may be overridden at the same type. A future replacement feature would need a different, explicit contract and its consumers; the current diagnostic name is not evidence that such a feature exists.

Closure is stricter than the open bounds. At `fix`, the final row must match the selected final self exactly: every declared member exists at its type, and there are no extra names. An all-open chain requires a final type supplied by its enclosing definition or an annotated binding; the compiler does not guess one from a lower bound. See [target selection](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1564-L1585). “Open while reusable, exact when closed” names two separate checks, not contradictory meanings of a row.

## A bound that survives a larger composition

Mini's source fixture defines:

```text
extension AddY[Self has {x: Nat}, Super has {x: Nat}]
  (self: Self, super: Super) -> Super with {y: Nat}:
    extend(super, {y: 2n * self.x})
```

This is displayed across lines for readability; the accepted fixture uses one header line. It is later composed with a closed extension `AddZW` at the final type `{x: Nat, y: Nat, z: Nat, w: Nat}`, starting with `{x: 5n}`. `AddY` was written with no knowledge of `z` or `w`; its result retains Super's row tail. The compiler fixture [`open_extension_reused_accepted`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendSpecificationClosure.lean#L255-L264) checks this reuse. The neighboring [`binary_self_accepted`, `f_bound_mismatch_refused`, and `unbound_self_member_refused`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendSpecificationClosure.lean#L266-L284) check that a self-dependent method closes at the declared recursive row, refuses another method signature, and cannot read an undeclared member even if some eventual instantiation could supply it.

These are finite compiler acceptance/refusal witnesses. They are useful regression targets for another frontend, but are not a proof that every independently implemented frontend elaborates all accepted programs identically.

## Where a proposed third specification component belongs

A structured row contract can improve interchange, diagnostics and tooling. It need not become a third runtime argument to `Term.specification`: the checked type/binder environment and compiler `Layer` already carry static obligations. Mini also serializes the declared interface and open binder text into metadata through [`interfaceLabel`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Compiler/ObjectiveBendElaborate.lean#L1785-L1789), but that string is an observation, not a replacement for checking.

If DelveTalk adds a portable contract object, a useful design would record `assumes`, `consumes`, `provides`, closure mode, and the checker/source version. Its receiving compiler should recompute or validate those obligations against the term and annotations. Treat this as a proposed interchange design, not an implemented proof certificate. Adding an unchecked rows field merely creates one more claim that can disagree with the code.

There are also three different senses of “law” to keep separate:

- A proved algebraic/checker theorem, such as `run_append`, licenses precisely its stated transformation or conclusion.
- A reflected specification claim retains descriptive/checkable intent; Mini currently marks it `unchecked`.
- A host admission predicate governs an actual requested state transition under current authority.

Moving any of these into the same metadata record does not make their evidential or operational roles identical. In particular, preserving a claim through composition does not prove that overrides preserve its truth.

## Shareability is another obligation, not a consequence of row openness

An unknown row is not automatically reusable because its visible members look immutable. Mini separately records explicitly assumed shareable variables and checks guarded bounds. Both components of specifications and prototypes participate in shareability, as do row members and tails. [`Assumptions.valid`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L72-L82) and [`Ty.shareableUnder`](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTypes.lean#L35-L56) give the actual checks.

One particularly easy implementation mistake is to normalize a row before tracking custody: canonicalization can erase a shadowed field. Mini's checked conversion uses `agree`, not just `sameType`, to prevent conversion from manufacturing shareability when such a field carried custody or a once closure. The [explanation, definition and theorem](https://github.com/emberian/minidregg/blob/dcab86da8f6153ed2b522fc61c5064608694fd83/Theory/ObjectiveBendTyping.lean#L112-L136) name that exact failure mode. Preserve this distinction in a portable checker; matching normalized field names and types alone is insufficient.

This document is a source audit and implementation guide. It makes no new theorem, hosted-execution, or deployment claim. DelveTalk's local executable evidence and any remaining frontend work belong in [TRACKING](../TRACKING.md), while the pinned core and local typed entry point are described by [spec/README](../spec/README.md).
