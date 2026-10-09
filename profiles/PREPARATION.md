# Pure source preparation

An invitation in a typed source view names an export, presentation fields, and
an explicit list of observation identities. The owning protocol identifies its
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
numbers. It contains no operations, references, substitutions, or expression
language. Source functions inspect these arguments and construct a complete
`Preparation.ready` turn, `question` with a message and needed argument names,
or `refused` with a message. Source helpers may combine typed effect lists using
ordinary functions.

The read-only native request contains exactly `op:prepare`, `object`, `root`,
`entry`, `contribution`, `observations`, `principal`, and `intent`. Each observation
contains `object` and its captured `root`. The supplied custody frame contains
only those retained roots. The native boundary verifies their equality and
resolves the export from the owner's exact source table. It never fetches a
new root. The present read boundary has no private-read policy; captured inputs
and pure preparation establish no access grant or authenticated receiving origin.

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

The boundary shares a 100,000-unit data/execution budget, 16 declared reads,
32 effects, and the native 1 MiB expanded request limit. Physical transports
retain a 64 KiB authored contribution bound and preserve exact decimal scale.
Town retains no-effect outcomes as `delvetalk-clerk-preparation-v1`, keyed by the
original verified reply URI/CID. Its exact retry does not fetch or reevaluate
source. Executable requests retain the existing admission and retry contract.
