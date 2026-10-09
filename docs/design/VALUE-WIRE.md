# Value and typed data representation

The source type owns the shape. Ordinary source records should use typed data
inputs; `Preparation.Value` is appropriate for an actually heterogeneous JSON
boundary (for example an offered model reply), rather than a substitute for
known records. The typed package checker already validates input types.

The physical logical-Value route is JSON → `Preparation.encodeValue` → recursive
`Data` variants (`text`, `record`, `array`, etc.) → `dataJson` → physical JSON.
Records and arrays are source cons lists, so every member has a cons variant,
payload record, named head/tail fields and a recursive tail. A typed package
then `PackageData.decode`s this physical JSON, quotes against the declared type,
checks the application and executes it. `executeDataValue` already returns
checked native Data; `decodeValueHeld` converts a logical Value back to JSON.
Custody roots retain exact artifact/source preimages independently of this
representation. These preimages and retained observations are not disposable
codec duplication.

Native preparation keeps contribution, observations and context as Data through
`executeDataValues` and `prepareValues`. Native quotation itself admits every
node, field and recursive payload against the declared type; no untyped
admission walk or wire parse is repeated first. Receiving normalizes physical
input once and carries its checked Data/type in a native PreparedInvocation;
laws see the same canonical facts while the body receives actual Data. The
physical request remains separate for custody, exact retry and byte accounting.
SourceState decodes a model against the exact retained compact schema once.
`dataJsonBytes` counts an exact DataWire frame where that physical API needs it;
receiving `executeDataValuesSized` charges the actual retained physical arguments.
The schema-directed storage boundary below replaces repeated tagged wrappers;
retained source/packet hashes continue to bind custody.

Record decoding uses a hash index for duplicate detection and a reverse builder,
replacing repeated list membership and append. Declared record validation also
indexes values once rather than repeated lookup. The generic response decoder
still preserves duplicates and order; strict package decoding refuses duplicates.
The encoder builds its JSON field array directly.

## Measurements

`scripts/measure_value_wire.py --binary PATH` checks its measurement model
against the actual native Value codec. These are explicit representative fixtures,
not production workloads. Frozen native source generation
`native-join-sol-20261009-final/build` matched every measurement on 2026-10-09:

| Fixture | Plain bytes | Value wire bytes | Plain JSON nodes | Wire JSON nodes |
| --- | ---: | ---: | ---: | ---: |
| Document, 20 paragraphs | 1,248 | 21,483 | 63 | 1,799 |
| Scene, 12 buttons | 1,006 | 26,321 | 75 | 2,263 |
| Candidate, one 64 KiB source | 65,600 | 67,462 | 6 | 165 |
| Gallery, 200 pages | 12,181 | 275,148 | 801 | 23,414 |

Fresh process codec times were 27.0, 27.1, 28.1 and 34.5 ms respectively in one
run; these include startup and are not a native execution improvement benchmark.
The large source string has little avoidable expansion. Structural document,
scene and gallery payloads are dominated by redundant logical list and wire
wrappers. Native-path removal avoids these transient trees; it does not claim
that the persisted logical Value representation has become compact.

The schema-directed compact codec below removes physical wrappers for declared
typed data. A separate change to the source Value algebra would still require
its source consumers to move together. Genuinely heterogeneous boundaries retain
Value; known application shapes should be source types.

`conformance/PackageDataCodec.lean` exercises exact wire byte counting,
record order, strict duplicate refusal versus generic duplicate preservation,
large-natural precision and bounded native quotation. Qualification
of receiving behavior belongs to the exact frozen native build using this source.

## Schema-directed compact boundary

The native compact codec now derives framing from the checked packet type.
Naturals are canonical decimal strings, booleans are JSON booleans, labels are
JSON strings, records are positional arrays in the declared canonical row order,
and variants are `[label, payload]`. It retains source constructors and recursive
aliases; it does not invent an application-specific schema or a second Value.
Record duplicates remain refused by the existing typed-package shape profile.
This is a claim about that profile, not all rows admitted by the core checker.

`encode-compact` / `decode-compact` take a `selection` containing the verified
artifact and explicit type path. Results carry `schemaPacketSha256`.
`run-compact` interprets arguments and results relative to that exact checked
artifact; normal execution ticks remain the same. Encoding and decoding are
bounded before returning physical frames. Exact natural precision and labels
remain unambiguous without per-value `tag/name/value` wrappers.

A current source transition can advertise `inputCodec: "compact"`. Its physical
input is `{schemaPacketSha256, value}`. The selected current packet must match
before the native runtime normalizes it. All source codecs now normalize to
canonical typed DataWire before source predicates, the body and candidate
invariants; physical codec choice does not change their input facts. Native loops keep the
original physical request for intent identity, expected roots and retry receipts.
`CallContext.physicalInput` is native-only accounting data, not authority.

Source-derived transaction results retain actual native Data, its checked type
and its own assumptions alongside public presentation JSON. The receiving
domain must be structurally equivalent under both packets before composition.
The semantic input comes directly from that native value, preserving source
list/field order. A dynamic Value result is not coerced into a typed record just
because its display JSON resembles one. Management replacement remains an
explicit protocol/state JSON boundary.

Compact state carries `{format, schema, value}`. The schema contains an
object-local source-package selector, explicit type path, packet hash and exact
source hash. `SourceState` resolves it solely in the caller-held protocol and
checks both hashes before decoding. Contracts, preparation and projection use
that single resolver. Source descriptions, constructor results and transition
outputs use compact state storage, independent of the input transport codec.
Older explicit tagged record fixtures remain accepted during the current fixture
port; new storage does not select that representation. No historical custody root
is rewritten. A preserved compact state crossing source revision is decoded
under its actual old retained schema, validated and recoded under the replacement
schema before installation. Explicit new-schema migrations are validated there.
`source_object.state_data(root)` is the shared native materialization API for
physical inspection; clients do not inspect compact layout themselves.

The dated native source/compiler/checker/machine differential measurement
passed a recursive natural list of 40 members: 6,060 → 640 physical bytes, identical returned value and machine ticks.
The measurement model predicts document 21,483 → 2,948, scene 26,321 → 3,054,
Candidate 67,462 → 65,761 and gallery200 275,148 → 34,202 bytes. These four compact
figures are model estimates until checked against the native selected schemas;
they are not receiving qualification. The existing semantic nesting/work caps
still apply, so a 200-member source cons list is not assumed admitted merely
because its compact physical size is small.

Actual compact input/source policy/current law/retry qualification is recorded
by `conformance/test_compact_policy.py` against its exact frozen native source.

Law-held source predicates receive a checked concrete record with `object`,
`principal`, `op`, `command`, `state`, and `input`; invariants also receive
`nextState`. States are logical source models, so an invariant can directly use
`facts.nextState.count`. Invocation input is `invoke(command(payload))`, where
the inner variant label is the actual current command and the payload is its
already normalized typed input. Administrative operations use `none({})` and
retain their authenticated operation name. A guard declares the finite command
sum it understands; a newly installed command outside that sum refuses before
its body runs. Each guard's actual compiled argument schema checks these facts;
no descriptor claim confers schema authority, row subtyping, or ignored fields.
Reserved message settlement uses a distinct `settlement` input variant with
native-authored metadata: `event: {lineage: String, id: String}`, `reason`,
`source`, `sourceProgram`, `originatingPrincipal` (all String), and
`causal: {root: String, parent: String, depth: Nat}`. Its existing authority
operation remains `invoke` with command `$messages-settle`; no installed command
body or command input schema is selected. A native-only optional Data argument
to the World policy helpers supplies this context. Caller request fields cannot
supply that argument or the internal settlement fact. Guards must explicitly
include the settlement variant to admit it. Unknown policy operations refuse.
Configuration remains exact `Preparation.Value`, including arbitrary decimal
spellings, natural numbers, and booleans. Bounded conversion, guard evaluation,
and body execution all spend the same receiving ledger. The plain, DataWire,
and compact physical input codecs do not change these logical facts.

The native report work repair compiles a charged, depth-bounded schema graph.
Each static record row and recursive sum alternative index is built once per
codec traversal. Variant nodes resolve the checked alias/index and their actual
payload; static alternatives are not rebuilt for every data node. Canonical
record sorting occurs once per static row, prepaid at n × (log₂ n + 1) units.
Native admission is fused into the complete typed quotation traversal, which
visits actual nodes and indexes actual fields. It performs no extra untyped walk
or JSON tag checks. Type-directed compact decoding and
encoding perform the complete conformance check themselves; SourceState avoids
a second discarded validation traversal. These are explicit work-accounting
changes; actual node, field, alias, index, and preprocessing visits remain charged.
Dynamic data depth and static schema depth are independently bounded at 256.
`scripts/test-data-codec.sh` runs the reusable codec regression in an independent
warmed snapshot under a coordinated compiler seat, including recursive depth
boundaries, rigid aliases, exact naturals, duplicate refusal and low-fuel failure.

The next native argument implementation is under qualification. It checks the
closed source once, admits each finite value against the selected argument
domain and the core quantity rule, and restores declared record order in the
same bounded traversal. It passes Data to lazy native demand cells rather than
constructing and repeatedly checking applied literal syntax. Finite first force
uses one native transition instead of source-thunk enter/evaluate/update; cached
force and source thunks retain their existing behavior. This deliberately changes
machine work to reflect removed transitions. It is not an assertion of equal
ticks, equal stack capacity, or successful adoption at the existing default
budget. Typed admission, erasure simulation, differential refusals and actual
receiving execution must qualify that implementation before those claims.

Checker fuel continues to bound initial annotated source admission. Native
argument admission instead uses the charged static/data graph depth and whole
execution work bounds; it does not rerun the whole source checker after each
argument. Consequently an initially admitted source with low checker fuel may
accept a valid finite argument whose quoted application exceeded that old
checker cutoff. This is an explicit admission-resource change, not a claim of
identical checker refusal thresholds. Quantity, context, alias and actual
value/domain obligations still require the same core typing evidence.
