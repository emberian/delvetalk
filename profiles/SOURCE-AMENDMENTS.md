# Source-governed law amendments

`delvetalk-scoped-law` retains the scoped invocation, reprogram and law grants.
Its optional `amendment` contains `profile: "delvetalk-source-amendment-v1"`,
a standalone source `package: {modules, entry}`, and opaque `config` data.
Existing `predicate`, `invariant` and source `contract` are optional independent
restrictions. Grants remain necessary; a guard cannot grant authority.

The checked Bend export takes one record and returns `Bool`:

```text
{object: String, principal: String,
 currentLaw: Preparation.Value, nextLaw: Preparation.Value} -> Bool
```

Lean supplies the actual staged laws and caller. Source interprets its own config,
for example to restrict a delegated enrollment service to named invocation grants.
Creation checks the guard against the same installed law on both sides. Revision
must satisfy both the current and proposed guards; management has no bypass.
When both complete amendment descriptors are identical, one successful evaluation
supplies both verdicts for that same actual context. Changed descriptors run both
guards. This reuse is local to one candidate check, never a cross-turn cache.
Explicitly permitted removal or lockout remains possible. Ordinary invocation and
reprogramming retain the amendment without executing it.

The existing compiled package evaluator and Value bridge share the turn budget.
Wrong arguments, non-Boolean results, exhaustion and source errors refuse the whole
turn. Default receivers reject this law profile's admission. Transactions use
staged laws; any later refusal rolls all effects back. Exact retry returns the
retained receipt before rechecking changed authority.

Source is held by law, independently of replaceable object code. No descriptor
text, opaque config or captured observation proves a user's external identity.
The trusted enrollment service and its source guard have separate obligations.

Receiving evidence: `python3 conformance/test_source_amendment.py`.
