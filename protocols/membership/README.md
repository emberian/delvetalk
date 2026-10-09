# A welcome with explicit permissions

Proof-of-control verification identifies an account; it grants no shared-world
rights. `Welcome.obend` decides whether that verified account receives an invitation
under the configured enrollment service. The service is a separate principal,
not an operator impersonation and not the participant's identity.

`generate.welcome(service, targets)` loads the ordinary source constructor. Targets
are explicit `{object, commands}` configurations, such as the Garden's public
methods and a workshop factory's `make`. The source bounds membership to 64 identities, supports
closing enrollment, records the verification evidence hash, and refuses an already
welcomed DID. Re-verification therefore cannot silently undo a later revocation.

Each target uses `delvetalk-scoped-law-v4` with
`generate.amendment(service, commands)`. Its law grants the service **law revision
only**. `GrantPolicy.amend` runs inside native admission against the actual current
and proposed laws. For this service it admits only an unchanged law or exactly one
DID appended to the configured public invoke methods. It preserves existing grants,
management permissions, unrelated fields and its own configuration. Ordinary
managers retain only their separately granted revision rights; there is no recovery
bypass. The service cannot remove this guard or grant management to a participant.

The source's `prepareEnroll` requests explicit captured laws, constructs complete
law values in Bend, and returns one transaction: record the welcome and revise the
target laws. Current roots, grants, both amendment guards and every later call must
all admit it. A stale root, disabled service grant or later refusal leaves every
object unchanged. Observations, public references and verification claims never
supply authority themselves.

`service.enroll` is physical custody: capture the source invitation and its declared
observations, ask native preparation, retain the exact request before submitting it,
and retry that request unchanged after uncertainty. It neither edits grant arrays
nor chooses the permitted role. Its inputs must come from the proof verifier; callers
cannot turn an arbitrary claimed DID or proof string into a trusted observation.
The evidence contains URI, CID and verification basis, never a credential token.

HeapManager's configured welcome hook supplies the verified DID and a stable
account-bound intent. Normal participant turns still run as that DID. Shared-world
membership does not open another account's private heap or change ownership of an
existing object; a permitted source factory grants rights to its newly allocated
child under its own current law.

Run `python3 conformance/test_membership.py` after the joined native host is built.
The journey covers proof verification, a real Garden contribution, source factory
creation, management/private-boundary denial, malicious service amendments,
late rollback, stale captured laws, lost-reply recovery and revoked membership.
