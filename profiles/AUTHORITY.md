# Current receiving authority

Current law admits each new operation; retained receipts answer exact retries.
Lean owns both checks. Creator and `owner` names confer no implicit rights, and
management has no recovery bypass. Local transport asserts a principal; the
trusted authenticated service supplies its verified caller identity.

The current source law has one schema:

```json
{"profile":"delvetalk-scoped-law",
 "invoke":{"play":["player"],"review":["reviewer"]},
 "reprogram":["programmer"],"law":["steward"]}
```

All four fields are required. Optional `read`, `predicate`, `invariant`,
`contract` and `amendment` add independent restrictions; version numbers do not
select different receiving algorithms. Invocation names match exactly. Missing
names grant nobody, `*` is literal, and a command named `reprogram` grants no
management right. Grants may precede command installation. Current law controls
replacement; proposed law cannot authorize itself. Programming preserves law.
Empty grants deliberately lock out mutation.

`read` is either the exact string `public` or a list of permitted principals;
absence means public. An empty list denies everyone, including the creator and
managers. Native acquisition checks the current law before returning complete
roots, observations, source preparation, history or message evidence. Possessing
a retained root locator grants neither read access nor mutation authority.

A `predicate` restricts an existing mutation grant. An `invariant` checks every
candidate state independently of replaceable command code. Their source form is
`{package: {modules, entry}, config: JSON}`. The complete law-owned source export
takes a concrete checked facts record and `config: Preparation.Value`, returning
Bool. Predicate facts contain actual `object`, `principal`, `op`, `command`,
logical typed `state` and an `input` sum; invariants also contain logical typed
`nextState`. A guard declares its actual source record/state/input types, and the
native checker validates that complete schema. Only Boolean true admits. Wrong
types, source failures, effects and exhausted resources refuse the whole turn.

Invocation input is `invoke(command(payload))`: the inner variant names the
actual command and carries its normalized typed input. A guard declares the
finite command sum it understands; an unknown command alternative refuses before
the body runs. Administrative operations use `none({})`. Reserved message
settlement uses `settlement` with native-authored event, reason, source/program,
originating principal and causal metadata. It remains operation `invoke`, command
`$messages-settle`; callers cannot supply the native settlement context, and the
guard must explicitly admit that variant.

Physical input codec choice does not change these logical facts. Configuration
retains exact heterogeneous `Preparation.Value`, including decimal spelling.
The original physical request owns identity, expected roots, byte accounting and
retry. Typed policy construction is implemented in [SourcePolicy](SourcePolicy.lean);
its source-interface checks and matching receiving qualification are separate.
This contract does not claim every policy callback already bypasses physical
DataWire framing.

Invocation checks the installed invariant against actual staged and proposed
state. Programming checks its explicit replacement state; new code cannot erase
law-held restrictions. Creation and factory children use `state = nextState =
initial`, the child's identity and actual caller. Creation and management use
command `""` and input `none({})`. Law revision checks both old and proposed invariants
against unchanged state after old authority admits revision. An authorized
steward can remove an invariant when the old invariant allows that change.

A source `contract` checks candidate state against its law-owned schema and checks
required methods at creation, programming and law revision. A source `amendment`
restricts law replacement using actual staged laws and caller. Current and
proposed amendment guards must accept; identical complete descriptors reuse one
successful verdict only within the identical candidate context. A changed guard
still runs. See [source contracts](../protocols/source-contract/README.md) and
[source amendments](SOURCE-AMENDMENTS.md).

One ledger covers authority, guard conversion/evaluation, source execution,
candidate checks, allocation and message staging. The compiled host has 100,000
units; transactions share the ledger across all steps. Any refusal rolls back
objects, children and outboxes, including earlier transaction effects. Retained
exact retries recover their original receipt before mutation policy reevaluation;
a formerly refused operation needs a new intent.

Only the current source ABI and law schema are admitted. Retired prototype
expression commands, principal-array laws and versioned source adapters refuse.
Persisted invitations are never silently refreshed or reinterpreted. Receiving checks live in
`conformance/test_current_boundary.py`, `test_authority.py`,
`test_state_invariant.py`, `test_source_amendment.py` and `test_governed_reads.py`.
Source checks and immutable native snapshots establish different evidence;
current source changes require their joined native gate before runtime claims.
