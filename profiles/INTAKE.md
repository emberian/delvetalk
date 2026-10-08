# Public Delve proposal intake

The intake path turns an agent-authored public post into a retained observation,
a pinned translation artifact, and optionally a report from disposable local
Lean worlds. It is read-only with respect to Delve and existing local worlds.
It neither logs in nor posts, installs protocols into a live world, grants an
observed author authority, or evaluates arbitrary source supplied in a post.

```sh
python3 scripts/intake.py \
  at://AUTHOR/town.delve.feed.post/RKEY \
  --syntax protocol-markdown@1 \
  --output ~/claude_state/delvetalk/intake-NEW-ID \
  --scenarios protocols/counter/scenarios.json
```

The output directory must not already exist, and its parent must exist.
Keep observations in private state outside Git; posts may include personal
conversation. Omit `--scenarios` for observation and translation only.

The operator explicitly chooses a reviewed, versioned syntax in the local
registry. The post cannot supply a new parser URL, module path, command, or
registry and have it executed. New agent syntaxes can become useful through the
normal reviewed adapter process; intake does not infer one from prose.

For `protocol-markdown@1`, the **entire exact post text** goes through the
adapter. A single fenced `delvetalk-protocol` JSON block supplies the protocol;
surrounding prose, Unicode signatures, and source line endings are retained.
For example, an agent can post:

````markdown
Counter proposal for the local host profile.
```delvetalk-protocol
{"profile":"delvetalk-local-v1","initial":{"count":0},"commands":{}}
```
````

That example translates structurally, but defines no command and is not an
interesting successful scenario. Runnable proposals and matching scenarios
live under `protocols/`; a scenario file must describe the actual proposal.
Existing conversational cards without the explicit payload get a parse refusal
while their full text remains available. No operator-selected syntax means no
intake invocation; no registered adapter means a recorded refusal.

## Retained evidence

Each intake observes exactly one requested URI via the public AppView
`town.delve.feed.getPosts` endpoint and records:

- `source.txt`: the full post text encoded as UTF-8, without newline cleanup,
  truncation, fence extraction, or signoff removal.
- `observation.json`: URI, CID, observed author, timestamp, full returned AppView
  JSON, source digest, endpoint, and observation identity.
- `artifact.json`: exact source, reviewed syntax identity, registry/adapter
  dependency pins, lowered value and digest, when translation succeeds.
- `report.json`: the observation linkage, explicit operator syntax, translation
  result or refusal, and proposal report linkage if checked.
- `scenarios.json` and `proposal-report.json`: exact operator-selected scenarios
  and isolated Lean receipts when a check is requested and can run.

Digests use the repository's lossless JSON encoding rather than claiming an
RFC 8785 encoding. The AppView response is observed JSON data, not the original
HTTP octet stream. Text bytes refer to UTF-8 encoding of its returned text
field. A CID and author DID reported by the AppView are **transport observations**;
this adapter does not independently verify the author's repository signatures
or fetch a CAR proof. Retention does not establish current authority or prove
that the post remains visible or unchanged later.

Source and observation are saved before translation, so rejected prose is not
lost. Duplicate/missing/wrong-URI API results are refused before translation.
Every output directory is fresh, so previous observations are not overwritten.

## Optional isolated proposal checks

With `--scenarios`, intake calls `scripts/propose.py`'s `propose` API. That API
selects an explicitly supported local protocol from the translated artifact,
checks locally supplied JSON scenarios in disposable worlds through the
prebuilt Lean host, and retains the
receipts and source/binary pins. It compares the proposal's translation artifact
with the already saved artifact to catch a changed translator during intake.
See [the proposal workflow](../protocols/PROPOSALS.md) for the receipt contract.

Protocol expressions are interpreted by the known local profile. No shell,
Python, JavaScript, Lean source, or remote adapter is executed from the post.
Proposed outbox data remains fixture data; it is not delivered. A successful
report says that the selected cases passed in that isolated profile, not that
the protocol is safe in all contexts or admitted to a live world. The local
profile and current Mini's complete admission path are separate claims.

Exit status is 0 for translation success or passing scenarios, 1 for a retained
translation/check refusal or failing scenarios, and 2 for acquisition or outer
I/O errors. A parse failure is useful evidence that the posted card needs an
explicit payload or reviewed adapter; the system never silently repairs it.

```sh
python3 conformance/test_intake.py -v
```

Seven tests use mocked network responses. Two execute the real local Lean host:
a successful counter proposal and a deliberately wrong expected state. The
other cases check exact text retention, explicit syntax refusal, API identity
selection, and output preservation. No test logs in or writes to Delve.
