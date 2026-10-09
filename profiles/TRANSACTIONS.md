# Ordered transactions

The native source host stages ordered calls and commits them together, or retains
one refusal. Each call uses the caller’s current staged authority. Later calls see
prior staged state, programs and laws. All initial expected roots must match before
execution; extra reads guard the transaction too. An absence read can guard a
[source allocation](ALLOCATION.md).

`inputFrom` selects an earlier result. The host supplies authenticated origin,
including object, command, program and adjacency, to the source context. Copied
input cannot forge that origin and provenance grants no authority. Source methods
return checked decisions; admitted state replaces the complete prior state.

Programming consumes explicit program/state or a checked earlier release result.
Law revision checks old and proposed constraints; later calls use the revised law
immediately. Every ordered intermediate candidate must satisfy current rules.
Deliberate lockout may commit. An unauthorized later call refuses the whole batch.
See [programming](PROGRAMMING.md) and [authority](AUTHORITY.md).

Receipts retain final roots, ordered results and admitted effects. A retained send
is addressed work for a later admission, rather than proof of delivery. A shared
bounded work budget covers the batch; overflow refuses without partial effects.
Exact `(principal,intent)` retries return the original terminal outcome, even after
current authority changes. Changed bytes under that identity refuse.

[scripts/world.py](../scripts/world.py) supplies locked filesystem custody around
the single `compiled` host. Requests preserve exact decimal preimages. Cooperating
writers serialize; an uncertain reply requires the original request. This local
boundary does not establish distributed consensus or universal power-loss safety.
Check [transaction cases](../conformance/test_transactions.py) against a matching
native/source build.
