# Typed package data

`delvetalk-obend` operation `run-data-v1` executes an existing, source-verified
package artifact with typed arguments. `compile`, its artifact identity, legacy
`run`, and plain package execution retain their existing behavior.

```json
{"op":"run-data-v1","artifact":"<compiled artifact object>","arguments":[{"tag":"variant","label":"nil","payload":{"tag":"record","fields":[]}}]}
```

The wire is the existing Objective Bend typed data format: natural, boolean,
label, record and variant. Records contain ordered `{name,value}` fields;
variants contain `label` and `payload`. Missing, extra or duplicate fields refuse.
An ordinary record named `tag` is still a record, explicitly wrapped on this wire.

Supported types are scalars, closed records and sums, including guarded recursive
sum aliases. Every alternative must be serializable, even when unselected.
Unknown/rigid aliases, recursive row tails, closures, custody, specifications,
prototypes and activities refuse. Mini's global data/Plan rules are unchanged.

Arguments are quoted against their declared types with constructor annotations.
The existing checker accepts each complete application; the existing demand
machine executes it. Results contain `executionProfile:delvetalk-package-data-v1`,
typed `value`, `type`, machine `ticksUsed`, and bridge `conversionNodes`.

`limits.work` bounds shared shape, decoding, quotation and result-conformance work
(default: `ticks`, maximum 1,000,000). That work and machine ticks share the tick
allowance. Nesting is capped at 256. `limits.inputBytes` bounds the complete compact
typed-argument JSON in UTF-8 before data decoding, including scalar text and decimal
digits. It defaults to `limits.bytes` (1 MiB by default), with a 16 MiB maximum.
`bytes` separately bounds encoded result extraction; explicitly set `inputBytes`
when a large input should yield a small result. Existing heap, stack and
extraction-node bounds still apply. Capacity refusal yields no partial success.
Receiving hosts charge **both** `ticksUsed` and `conversionNodes`, plus their own
ordinary input/context/result conversions. This boundary grants no authority.

## Comparing persisted schemas

`compare-data-types-v1` takes `left` and `right`, each containing a verified
`artifact` and a `path`. A path selects arrow `"domain"`/`"codomain"` or record
`{"field":"name"}` steps; `[]` selects the whole checked type. Zero-argument
definitions have their result type directly. Paths have at most 64 steps.

Selected types must satisfy the same serializable profile. Comparison follows
transparent recursive aliases independently in each package, using the checker's
canonical field/alternative order. Duplicate fields refuse before canonicalization.
Alias numbers are not cross-package identity. The response is
`{status:"compared",equal:BOOL,conversionNodes:N}`; optional `work` bounds traversal.
Schema equality establishes neither behavior compatibility nor admission rights.

[Implementation](../spec/Delvetalk/PackageData.lean) ·
[native tests](../conformance/test_package_collections.py)

## Pure sessions

The package CLI accepts successive JSON lines and flushes each reply. The account
REPL reuses one bounded native process on its existing serial worker. Every request
still compiles or verifies its exact artifact; no result or authority cache exists.
Runtime changes restart the process. Deadline, framing or output failure kills it;
only a later explicit call starts a fresh process. World admission and durable
Notebook retries remain separate. Linux uses the shared finite address-space
ceiling; each exchange has a wall deadline, not a cumulative lifetime CPU quota.

[Transport tests](../conformance/test_package_session.py) ·
[REPL/gallery benchmark](../conformance/bench_package_session.py)
