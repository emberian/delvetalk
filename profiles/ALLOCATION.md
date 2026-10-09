# Governed allocation

**Factory commands create children atomically with parent state and a retained
receipt.** Lean admits allocation in `world`, `transactions` and `compiled`.
Existing protocols remain valid.

Declare `"allocation": {"limit": 8}` in the factory protocol. Add this command
field:

```json
"allocate": [{
  "name": ["input", "name"],
  "protocol": ["state", "childProtocol"],
  "law": ["array", [["principal"]]]
}]
```

Expressions share the command's budget and read its pre-call state. The factory's
**current invocation grant and predicate** govern admission; management grants
alone confer no allocation authority.

Factory `desk` plus name `draft-1` creates `desk/draft-1`. Names contain 1–64 ASCII
letters, digits, underscores or hyphens. Child protocol and law are explicit,
validated results. Children start at version zero with their protocol's initial
state. No authority is inherited: an empty child law locks out its creator too.

The quota counts existing and staged **direct children**, regardless of creator.
Nested factories have independent quotas; this provides no global or descendant
storage bound. Authorized reprogramming can revise the quota without removing
existing children.

Standalone invocations supply the exact parent `expected` root and
`"absent": ["desk/draft-1"]`. Every child requires a checked absence guard;
collisions and batch duplicates refuse. Success adds complete child roots under
`data.allocated`, omitted when empty.

Transactions instead use
`"reads": {"desk": FACTORY_ROOT, "desk/draft-1": null}`: `null` asserts initial
absence. Later calls can use the child under its staged current law and the same
caller. Every called object needs a read entry. Final roots appear in
`data.roots`; unused absence guards remain `null`.

Any failure—including a later transaction failure—discards parent changes,
children and outbox, retaining the refusal. Exact retry returns the historical
receipt after revocation or a lost reply. Changing a request under the same
principal and intent refuses.

Local `create` remains operator bootstrap. Public authentication and child custody
belong to the receiving adapter; allocation establishes local admission.

[World admission](WorldCore.lean) · [Transactions](TransactionsCore.lean) ·
[Receiving tests](../conformance/test_allocation.py)

After building all three receivers, run `python3 conformance/test_allocation.py`.

Transaction `data.allocated` retains creation roots before later edits; `data.roots` retains final roots.
