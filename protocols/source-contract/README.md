# A specification that constrains receiving programs

`Counter.obend` separates a reusable `Specification<Counter>` from an independent
counter implementation. Its checked target row requires `add` with the declared
state, input, context and decision types. The contract does not require the new
implementation to copy its body or prove its claims.

Retain the exact ordered modules. Compile entry `contract` with `delvetalk-obend`,
then observe that artifact with `inspect-spec-v1`. The returned `value` is actual
source-derived `SpecMeta`; store it unchanged in the law descriptor:

```text
contract = {
  profile: delvetalk-source-contract-v1,
  package: {modules: exact modules, entry: contract},
  stateProfile: plain,
  metadata: observed value
}
```

Use it in `delvetalk-scoped-law-v3`, alongside explicit `invoke`, `reprogram` and
`law` grants. The existing optional authority `predicate` still restricts grants;
optional core `invariant` retains the v2 before/after state rule. Plain invariants
retain their plain-data boundary. `stateProfile: model` selects typed source
method profiles, independently of plain form inputs/results.

Every proposed state, including writes from extra legacy commands, must fit each
required method's declared state schema. The receiving host additionally checks
the actual candidate's source signatures on creation, program replacement and law
replacement. Required methods are **at least** these
names; other methods may coexist. Each required command must be a source method
of the declared state profile. Its argument/result schemas and arrow quantities
must match. Recursive data aliases compare through their own verified packets,
not coincidentally equal local type-variable numbers. There is no Python type
checker or string comparison against the metadata's interface description.

Metadata is re-observed from the exact specification and must equal its durable
law snapshot. Applying the specification, invoking a method or replacing object
code never drops that snapshot. Method examples and `unchecked` claims remain
observations/claims; matching a signature does not prove behavioral refinement.
A separately installed state invariant enforces properties such as `count <= 3`.

Current law authorizes revision. Installing new law must satisfy both the old and
new source contracts against the unchanged program; ordinary reprogramming cannot
remove the law-held contract. Authorized law evolution can deliberately remove
it. Exact historical retries still return their retained outcome after lockout.

One admission budget covers metadata evaluation and schema comparison. Contracts
contain 1–16 required methods with at most eight first-order arguments each;
existing package/module bounds limit compilation. Compilation itself retains the
host's existing structural bounds, not a claimed complete CPU tariff. Ordinary
state-changing calls compile the one retained contract for its state schema; they
do not recompile candidate methods or re-evaluate unchanged metadata.

`conformance/test_source_contract.py` exercises these boundaries through the actual
compiled receiving host, including transaction rollback and separately retained
source-package selectors. Resident posts can name a specification and its desired
installation; the operator assembles the exact law revision, and ordinary current
law decides it. Source metadata never grants permission to install itself.
