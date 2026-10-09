# Give an object a source promise

An author can post Objective Bend text and say: “Use my `contract` export as the
counter’s method promise.” They write a `Specification<Counter>` in ordinary
source; they never copy or invent metadata JSON. `Counter.obend` contains both a
specification export and a separate implementation. Its claim remains a claim,
while the declared method boundary becomes a law requirement.

The operator retains that exact source in an ordinary SourceDesk candidate,
submits its examples, and compiles it through the existing bounded compiler. The
maker can submit source; a compiler can admit a checked candidate; the steward
must have both the candidate's current `adopt` grant and the target's current
`law` grant. Source does not grant either permission.

`scripts/contract_authoring.py prepare` takes the captured ready candidate root,
the captured target root, and the named specification export. The native compiler
checks the retained original source. Native `inspect-spec-v1` computes its actual
metadata. The resulting immutable proposal retains source bindings, the checked
build, metadata, and the exact release request for review. Plain versus model
state follows the candidate's explicitly selected @2 or @3 syntax.

`release` calls the candidate's existing `adopt` command and revises the target
law in one exact-read transaction. It preserves the target's captured invoke,
reprogram, management, predicate and state-invariant rules, replacing only the
source contract. It leaves the installed program and state alone. The receiving
host checks the old and new law contracts against that unchanged program. A
failed law revision also rolls back the candidate release.

To add a required method, first install a compatible implementation with that
additional method under the original contract, then strengthen the law. A changed
input or result boundary is not silently accepted as a narrower promise. Required
method names are an at-least bound; signature agreement is not a proof that two
implementations behave alike.

The CLI uses ordinary operator custody files:

```sh
python3 scripts/contract_authoring.py --database WORLD --artifacts ARTIFACTS prepare \
  --candidate source-desk --target counter --principal steward --intent promise-1 \
  --candidate-root ready.json --target-root counter.json --entry contract > promise.json
python3 scripts/contract_authoring.py --database WORLD --artifacts ARTIFACTS release promise.json
```

The release plan is retained under `ARTIFACTS/contract-attempts`. Include that
directory as history journals and the ordinary compiler build attachments when
exporting. The actual law already retains the exact source package and native
metadata. An exported attempt can be restored with `Contracts.restore`; this
retains custody, not authority. Exact historical retries recover their receipt
before consulting changed grants, missing source blobs or current compiler pins.
New attempts must still pass custody, exact-root and current-law checks.
