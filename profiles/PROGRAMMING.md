# Governed programming of existing objects

`reprogram` replaces an existing object's protocol and state through the shared
Lean local host. It is available in both `delvetalk-world` and
`delvetalk-transactions`; no new transport or programming-specific authority is
introduced. A principal authorized by the object's current law may propose the
replacement against an exact current root.

```json
{
  "op": "reprogram",
  "object": "document",
  "principal": "alice",
  "intent": "document-v2",
  "expected": "<complete current object root>",
  "protocol": {
    "profile": "delvetalk-local-v1",
    "initial": {"body": "new-object default"},
    "commands": {
      "write": {
        "require": [],
        "set": {"body": ["input", "value"]},
        "result": ["state", "body"],
        "outbox": []
      }
    }
  },
  "state": {"body": "explicitly migrated existing content"}
}
```

The `expected` placeholder denotes the complete JSON root: old protocol, law,
version, and state. The request accepts exactly the seven fields shown. Unknown
fields are refused, including `law`, `initial`, or `migration` at request level;
an apparent combined authority change or implicit migration cannot be silently
ignored.

Admission first checks the existing object's current law and exact root. Lean
then validates the proposed protocol using the same installation validator as
`create`, including unused command bodies, and requires `state` to be a record.
On success it replaces both protocol and state, preserves law and object
identity, and increments the version once. There is no owner bypass and an
empty law still locks out every new management operation.

`state` is a complete replacement, not a merge. Missing state and non-record
state are refused. An explicit `{}` intentionally removes every state field.
`protocol.initial` remains required as part of a valid protocol definition but
does not initialize this existing object. The migration is pure data supplied
by the authorized caller; no migration expression runs, no command is invoked,
and no outbox is emitted by the replacement itself.

The normal receipt shape is preserved:

```json
{
  "intent": "document-v2",
  "object": "document",
  "kind": "committed",
  "data": {"root": "<new complete root>", "result": null, "outbox": []}
}
```

Any authorization, preimage, protocol, or state failure leaves the object
unchanged and retains one refused receipt. The entire request is bound to the
existing global `(principal, intent)` identity. Exact retries recover their
historical receipts even after subsequent programming or authority changes;
changing the candidate under the same identity is refused. An earlier invoke
receipt also remains historical evidence and is not reexecuted under the new
program. The old protocol remains in the retained upgrade request's exact
preimage and in any earlier receipts that already contained that root.

Changing the program invalidates old object roots, including transaction read
sets. Subsequent invocations and transactions use the new program under the
same current law. `reprogram` is also available inside ordered transactions. A prior candidate
call can supply the exact `{protocol,state}` result to a later reprogram call
through `inputFrom`; all calls share authorization, read roots and rollback.
See [TRANSACTIONS.md](TRANSACTIONS.md).

Protocol validation checks the local expression format, not migration
correctness, termination, application invariants, or compatibility with existing
clients. A valid new program may fail when invoked if the explicit replacement
state omits a field its commands need. Legacy array laws use one authority set for all operations. The
[scoped authority profile](AUTHORITY.md) separates named-command invocation,
programming and law revision. Command preconditions do not veto management
operations.
As with other local operations, principal strings are assertions by the local
caller, and committed outbox data is not proof of external delivery.

Build the two receiving paths serially and run the focused tests:

```sh
LEAN_NUM_THREADS=1 lake build delvetalk-world
LEAN_NUM_THREADS=1 lake build delvetalk-transactions
python3 conformance/test_reprogram.py
```

The tests exercise both host profiles: an upgraded program actually runs,
authority and identity remain unchanged, state has no implicit default,
unauthorized and stale requests cannot replace a program, invalid unused
commands fail atomically, old receipts survive upgrades and lockout, decimal
preimages remain exact, and a fresh transaction can call the new program while
an old read set is refused.
