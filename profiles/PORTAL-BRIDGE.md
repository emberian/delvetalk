# Portal repository handoff

The bridge prepares a saved [portal](PORTAL.md) draft for the existing
[repository request wire](CLERK.md). It performs no network requests, login,
publication or admission. Python preserves custody; the clerk derives the
repository author and Lean checks current authority and exact roots.

```sh
python3 scripts/portal_bridge.py /PRIVATE/world prepare DRAFT
python3 scripts/portal_bridge.py /PRIVATE/world bind DRAFT \
  at://AUTHOR/org.delvetalk.request/KEY --cid CID
python3 scripts/portal_bridge.py /PRIVATE/world reconcile DRAFT \
  --clerk-state /PRIVATE/clerk
```

Use `--state` for an existing separate portal custody directory. The Python API
is `Bridge(portal).prepare(draft)`, `.bind(draft, uri, cid)`, and
`.reconcile(draft, trusted_clerk)`.

Preparation reconstructs the captured card/action/fields and checks the saved
request, exact root, wire, runtime and local-session identity. It exports
`requestJson`, its `org.delvetalk.request` record and a stable `publicationIntent`
for the existing publisher. Principal and admission intent never enter the
wire. No refreshed root or replacement action is inferred. Preparing does not
make a publication claim or authorize a publisher invocation.

A URI/CID binding is an unverified transport claim and cannot be rebound. An
uncertain result retains that same identity. Reconciliation accepts an explicit
trusted **local clerk custody**, never callback JSON or a self-hashed receipt.
It compares source, record and derived request against the saved preparation,
then requires the exact retained world admission. This recovers a lost clerk
receipt write without rerunning admission or changing clerk custody. Completed
receipts remain recoverable after runtime pins change. Outcome records stay
separate from local-session execution receipts.

The result uses the portal's `kind`, `draft`, `reply`, `summary` and refresh link
shape. Stale roots and unauthorized authors remain terminal Lean refusals;
identity/receipt mismatches refuse reconciliation. Local filesystem custody and
operator-selected clerk paths are trusted, as in the existing clerk profile;
this is not signature/CAR verification or remote receipt authentication.

Run `python3 -m unittest conformance.test_portal_bridge` with the built Lean
world host. Tests cover card-to-request-to-receipt composition, restart, stale
roots, forged identity, enrollment without authority, substituted receipts and
interrupted-reply recovery using a GET-only fake PDS and actual Lean admission.
