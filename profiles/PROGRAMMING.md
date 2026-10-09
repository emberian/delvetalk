# Governed programming

`reprogram` atomically replaces an object’s program and complete state under its
current law and exact expected root. The native source host checks the actual
candidate source interface and held invariants. Success preserves identity and
law and advances the version. State replaces rather than merges; migration must
be explicit. No old invocation reruns under the new source.

Programming authority differs from compiler and invocation authority. An empty
management law can deliberately lock out future changes; there is no owner
recovery bypass. A refusal retains its outcome without modifying the object.
Exact `(principal,intent)` retries recover the original receipt before checking
changed source or authority; changed bytes under that identity refuse.

An ordered [transaction](TRANSACTIONS.md) may consume an earlier exact
`{protocol,state}` result using `inputFrom`. Source Candidate release and target
replacement commit together under both current laws. A late failure rolls the
whole batch back. [Source authoring](AUTHORING.md) and
[authority](AUTHORITY.md) describe the corresponding offered workflow and rules.

Build with `make build`; check [reprogram cases](../conformance/test_current_boundary.py)
against the matching native/source closure.
