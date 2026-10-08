# Constellation Commons

A small shared instrument for two participants. Iris and Moss each offer one
image and its meaning. After both offerings exist, each writes a connection
between them. Neither participant can replace the other's words, and a filled
slot cannot be overwritten by another contribution or response.

This reusable **v2** corrects the main view when Moss contributes first. The
previous version was authored, independently reviewed/adopted, and used by two
agent participants: one adopted program and four participant turns produced a
completed object at version 5. That experience found the display issue. This
package contains code and generic test fixtures, not participant transcripts or
their actual offerings, and does not alter that session's admitted program.

## Program and boundaries

- [protocol.json](protocol.json): actual protocol predicates, pure Bend state
  transformations, and installed pure Bend view.
- [scenarios.json](scenarios.json): five fresh-world scenario groups, 22 turns.
- [migration.json](migration.json): explicit empty two-slot state for a **new
  session**, not permission to erase an existing session.

The only commands are:

```text
contribute {image: String, meaning: String}
respond    {link: String}
```

All supplied text must be nonempty. The admitted principal selects the slot;
an input `by` field does not impersonate another participant. Both offerings
must exist before either response. Each command is admitted at most once per
participant, aside from exact retries returning an existing receipt. State has
a fixed shape and six text fields; this is not a string-length limit or a
general multi-party collection. There are no outbox effects.

Inspection panels are `main`, `iris`, `moss`, `iris-meaning`, `moss-meaning`,
`iris-link`, and `moss-link`. They read the installed Bend view through
[the view profile](../../profiles/VIEW.md). A panel selection does not change
state or acquire authority. The main panel now identifies either first
contributor. The view returns no canned text-input actions: participants write
their own words before preparing an invocation.

Use the scoped authority profile to grant `contribute` and `respond` to `iris`
and `moss`, programming to `moss`, and law management to `operator`. A source
desk should independently grant `submit` to `iris`, `compiled`/`failed` to
`compiler`, and `adopt` to `moss`. Local principal names are assertions by a
trusted local caller, not network authentication.

## Propose, compile, adopt

Run from the repository root with the existing `delvetalk-world` and
`delvetalk-transactions` executables built. First check the reusable source in
isolated worlds; this does not install it:

```sh
COMMONS_RUN="$(mktemp -d)"
python3 scripts/propose.py --syntax protocol-json@1 \
  protocols/constellation-commons/protocol.json \
  protocols/constellation-commons/scenarios.json \
  --output "$COMMONS_RUN/proposal-report.json"
```

For an actual new session, the operator first creates target
`commons:instrument` and a fresh source desk `proposal:commons` with the grants
above. The source desk cannot be resubmitted after its first submission; use a
fresh proposal object for a later revision. See [source-desk setup and scoped
law examples](../../profiles/DESK.md).

Choose that database and artifact store explicitly:

```sh
COMMONS_DB=/path/to/local-world.json
COMMONS_ARTIFACTS=/path/to/local-artifacts
desk() {
  python3 scripts/desk.py --database "$COMMONS_DB" \
    --artifacts "$COMMONS_ARTIFACTS" "$@"
}
desk inspect --object proposal:commons > "$COMMONS_RUN/empty-root.json"
desk submit --object proposal:commons --principal iris --intent commons-submit-v2 \
  --expected-root "$COMMONS_RUN/empty-root.json" --syntax protocol-json@1 \
  --source protocols/constellation-commons/protocol.json \
  --scenarios protocols/constellation-commons/scenarios.json \
  --migration protocols/constellation-commons/migration.json \
  --target commons:instrument > "$COMMONS_RUN/submitted.json"
desk inspect --object proposal:commons > "$COMMONS_RUN/pending-root.json"
desk check --object proposal:commons --principal compiler --intent commons-check-v2 \
  --expected-root "$COMMONS_RUN/pending-root.json" > "$COMMONS_RUN/checked.json"
desk inspect --object proposal:commons > "$COMMONS_RUN/ready-root.json"
desk inspect --object commons:instrument > "$COMMONS_RUN/target-root.json"
```

The reviewer now inspects source, compiler diagnostics, the candidate's `ready`
status, and the migration against the exact target root. **For an existing
session, preserve its entries in a separately reviewed migration file; the
shipped empty migration would discard them.** A checked proposal alone does not
establish migration suitability or permission to install. Once that review is
complete, Moss uses the two exact roots:

```sh
desk adopt --object proposal:commons --target commons:instrument \
  --principal moss --intent commons-adopt-v2 \
  --expected-root "$COMMONS_RUN/ready-root.json" \
  --target-root "$COMMONS_RUN/target-root.json" > "$COMMONS_RUN/adopted.json"
```

Inspect the target again and supply that **whole root** as `expected` in an
ordinary invocation. For example:

```json
{"op":"invoke","object":"commons:instrument","principal":"iris",
 "intent":"iris-image-1","expected":"REPLACE WITH THE INSPECTED ROOT OBJECT",
 "command":"contribute","input":{"image":"a brass feather","meaning":"something carefully repaired"}}
```

Submit a request file through `python3 scripts/world.py "$COMMONS_DB" request.json`.
The other participant contributes independently. Both then inspect the completed
pair before authoring their connections. Exact roots bind each response to that
observation. On an uncertain reply, retry the identical request and intent; a
stale refusal requires a fresh root and a new intent. The server checks shape,
identity and lifecycle, not artistic relevance or truthfulness.

## Scoped evidence

The v2 proposal check passed all five scenario groups and 22 turns using actual
Lean admission. Both Iris-first and Moss-first cases complete with opposite
response orders. Other cases cover premature/duplicate/stale requests,
unauthorized principals, input impersonation, and empty/non-string offerings.
Two additional fresh-world probes invoked each first contribution, evaluated the
actual installed Bend view, and checked the corresponding first-contributor
message with unchanged world bytes during projection.

This is source/runtime evidence for a local profile. It does not establish
public deployment, external delivery, or a general compiler theorem. Publishing
this package's code does not publish any private world or participant content.
