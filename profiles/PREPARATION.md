# Pure source preparation

An invitation in a typed source view names an export, presentation fields, and
an explicit list of observation projections. Each request names an object and
`inspectState`/`inspectLaw` booleans. The owning protocol identifies its
retained source table with:

```json
{"preparation":{"profile":"delvetalk-source-preparation-v1","sourcePackage":"resident"}}
```

The source imports the explicitly retained `Preparation.obend` module and
exports an ordinary function:

```text
prepare(state: State, contribution: P.Value,
        observations: P.Observations, context: P.Context) -> P.Preparation
```

`Value` is a bounded JSON data codec, including records, arrays, null, and exact
numbers. A `retained` arm holds a captured state by exact object/root identity;
it is not a global locator. Value contains no substitutions or expression language. Source functions inspect these arguments and construct a complete
`Preparation.ready` turn, `question` with a message and needed argument names,
or `refused` with a message. Source helpers may combine typed effect lists using
ordinary functions.

The read-only native request contains exactly `op:prepare`, `object`, `root`,
`entry`, `contribution`, `observations`, `principal`, and `intent`. Each observation
contains `object`, its captured `root`, and both explicit inspection flags. Retained-file preparation resolves only those captured roots. Direct pure
preparation accepts a custody frame containing the same roots. The native boundary verifies their equality and
resolves the export from the owner's exact source table. It never fetches a
new root. Captured inputs and pure preparation establish no access grant or authenticated
receiving origin. Native inspection and later admission enforce their respective
current policies.

The source's ready turn lists existing or absent reads and complete structural
effects: invocation, observation, reprogramming, or law revision. Prior-result
consumers name an earlier result index. Native framing binds existing reads only
to supplied observations and automatically anchors the owner. An absent read is
an explicit assumption checked at later admission; allocation followed by a call
to that child is permitted. Duplicate reads, unobserved existing reads, missing
call reads, and forward result references refuse.

A ready result contains `kind`, `summary`, and an exact native transaction.
Questions and refusals contain `kind` and `message`; questions also contain
`needs`. Preparation changes no world and creates no semantic receipt or intent
reservation. Receiving the ready transaction later establishes current authority,
staged availability, exact roots, and prior-result provenance atomically.

An uninspected observation supplies stable object/version/program metadata and
its state as a retained Value. Only requested state or law contents undergo
bounded inspectable conversion; no size-dependent fallback changes source
meaning. Final effect decoding resolves retained values only against this
preparation's captured roots whose exact reads are bound. Foreign or manufactured
keys refuse. Authored JSON contributions cannot create that constructor through
the ordinary codec, and standalone Value decoding has no held root table.

Owner state is supplied as a typed argument; its automatic read anchor does not
add a source observation unless the invitation requested it. Retained state and
inspectable effects use the admitted typed-wire depth ceiling of 256, while authored
contributions and standalone Value conversion retain depth 64. Opaque state reuse avoids serializing typed wrappers through a second Value
encoding. Inspection remains subject to typed conversion and execution bounds;
it does not increase source execution fuel.

The boundary shares a 100,000-unit data/execution budget, 16 declared reads,
32 effects, and the native 1 MiB expanded request limit. Physical transports
retain a 64 KiB authored contribution bound and preserve exact decimal scale.
Town retains no-effect outcomes as `delvetalk-clerk-preparation-v1`, keyed by the
original verified reply URI/CID. Its exact retry does not fetch or reevaluate
source. Executable requests retain the existing admission and retry contract.

An invitation may explicitly declare `contributionCodec: "data"` for a typed
source argument. That contribution is bounded DataWire, checked against the
selected export's actual input type; it is not converted to Value. The default
`value` codec remains the public form path. A typed preparation may return an
`invokeData` effect carrying its already checked source Data. The native binder
preserves that wire and the receiving method's `inputCodec: "data"` checks its
own exported argument type. Neither spelling supplies observations or read
authority: existing reads still bind only to the captured root table.

Transported `Value.text` data shares the enclosing 1 MiB frame bound, so retained
source modules over 64 KiB can be inspected and released exactly. Presentation,
identity and numeric-text validation retain their narrower limits. This does
not change the 512 KiB source-module limit, authored contribution bound or native
execution allowance.

Required heterogeneous fields use `lookupField`, `textField`, `naturalField`, or
`booleanField`: each returns explicit `missing`, `wrongKind`, or `found`. A
legitimate empty string, zero, or false remains `found`. `lookupObservation`
returns `missing` or the actual captured observation, including version zero.
Consumers choose their own question or refusal; the codec supplies no authority.
`textOrEmpty`, `naturalOrZero`, `booleanOrFalse`, and `observationOrEmpty` are
explicitly lossy optional projections. The historical `text`, `natural`, and
`observation` exports retain that same compatibility behavior and must not
validate required fields. Typed conversation/model envelopes are checked as
their exported source type and do not need dynamic envelope decoding.
