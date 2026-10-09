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
has type `(facts: Preparation.Value, config: Preparation.Value) -> Bool`.
Predicate facts contain actual `object`, `principal`, `op`, `command`, staged
`state` and resolved `input`. Invariant facts additionally contain `nextState`.
The Value bridge preserves JSON arrays, typed model state and decimal spelling;
source interprets its configuration. Only Boolean true admits. Wrong types,
source failures, effects and exhausted resources refuse the whole turn.

A pure core Bend term remains an explicit operator representation for these two
fields. Its context conversion supports Nat, Bool, String and records only; it
refuses incompatible JSON even when a field is unused. Source guards support the
complete bounded Value representation and avoid this restriction on typed state.

Invocation checks the installed invariant against actual staged and proposed
state. Programming checks its explicit replacement state; new code cannot erase
law-held restrictions. Creation and factory children use `state = nextState =
initial`, the child's identity and actual caller. Creation and management use
command `""` and input `{}`. Law revision checks both old and proposed invariants
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

The current cutover keeps older validation/adapter seams temporarily while
actual source consumers move. Those seams are not a second current source ABI.
Fresh previews use the current schema; persisted invitations are never silently
refreshed or reinterpreted. Receiving checks live in
`conformance/test_current_boundary.py`, `test_authority.py`,
`test_state_invariant.py`, `test_source_amendment.py` and `test_governed_reads.py`.
Source checks and immutable native snapshots establish different evidence;
current source changes require their joined native gate before runtime claims.
