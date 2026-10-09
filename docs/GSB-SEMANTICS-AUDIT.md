# GSB semantics audit

2026-10-08; DelveTalk base `4169f086bdb25f139df28c7e5b949cee9b21b6c5`, Mini pin
`dcab86da8f6153ed2b522fc61c5064608694fd83`. The provisional card matches some
implemented boundaries but overstates its linear fallback and stuck census.

- **Shareable types differ from unrestricted uses.** Specification/prototype
  shareability recursively requires both component **types** shareable;
  reusable captures additionally require unrestricted used bindings
  ([types](../spec/upstream/Theory/ObjectiveBendTypes.lean#L35),
  [captures](../spec/upstream/Theory/ObjectiveBendTypes.lean#L190)). A specification
  containing an affine Nat was accepted with `shareable:true, uses:[1]`; passing
  that construction as an unrestricted argument refused ownership. Consequently,
  “all components unrestricted iff reusable” conflates distinct obligations.

- **“Else linear” is not an automatic fallback.** Explicit once closures and
  nonshareable wrappers can retain custody. Direct activities in wrapper
  components refuse statically; sum arms require shareable payloads. Partial
  linear checking enforces at-most-once, not eventual consumption
  ([rules](../spec/upstream/Theory/ObjectiveBendTyping.lean#L394),
  [arms](../spec/upstream/Theory/ObjectiveBendTyping.lean#L591),
  [tests](../conformance/test_typed.py#L85)). Checked conversion uses
  [`agree`](../spec/upstream/Theory/ObjectiveBendTyping.lean#L112) to prevent
  shadowed-custody laundering; the broader typing relation's conversion uses
  `sameType`, so its guarantees require separate care.

- **The four-form stuck census is incomplete.** Closed counterexamples include
  `app(1,2)`, `get(1,"x")`, `extend(1,[])`, wrong-kind `ifZero`, `ifBool`,
  and `case`; `add(true,false)` also shows that incompatible operands need not
  have disjoint scalar kinds. A record containing a stuck field remains a value
  until demanded. [`inspect`](../spec/Delvetalk/Core.lean#L1) emits undifferentiated
  `stuck`, without a completeness proof or classified E-context. Existing
  [fixtures](../conformance/cases.json) already include noncallable prototypes
  and wrong-kind Boolean conditions.

- **Zero division/remainder succeed:** `n/0=0`, `n%0=n`, neither stuck nor
  refused. [Pinned rules/theorems](../spec/upstream/Theory/ObjectiveBendOpenRecursion.lean#L169)
  and fixtures `divide-zero`/`modulo-zero` agree.

- **Specification binding matches its documented scope.** The
  [elaborator](../spec/upstream/Compiler/ObjectiveBendElaborate.lean#L1500)
  caches rigid templates, substitutes final Self/inherited Super, and checks
  [exact row contracts](../spec/upstream/Compiler/ObjectiveBendContract.lean#L31).
  Composition/checker theorems do not establish complete frontend observational
  equivalence. Portable contract certification remains proposed in
  [SPEC-BINDING](SPEC-BINDING.md).

- **Durable restrictions belong to current object law.**
  [References](../scripts/references.py#L16) carry identity only.
  [Admission](../profiles/WorldCore.lean#L201) checks current grants and predicates,
  including before replacement; [persistence](../scripts/world.py#L75) retains
  Lean's returned world. [Tests](../conformance/test_authority.py#L364) cover
  old-law management and predicate refusal. This does not establish portable
  reference-attached restrictions or deployment.

Evidence: ten targeted raw observations agreed across existing Lean/Python/JS/C
executables; five typed probes confirmed wrapper/capture distinctions;
`check_capsules.py` verified pins and declared compatibility projections. No fresh
build or full-suite claim. Numbered figures ①–③ were not recovered; figure ⑥'s
host seam was outside this audit.
