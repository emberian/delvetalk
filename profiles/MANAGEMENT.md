# Clerk management

**Local management separates transport enrollment from Lean authority.** It uses trusted filesystem custody, makes no network requests and publishes nothing. `--principal` asserts a local identity; the CLI does not authenticate it. Lean still checks current law.

| Command | Effect |
| --- | --- |
| `register DID` / `unregister DID` | Enable/stop new observations; never grant/revoke law or cancel retained attempts |
| `law` | Replace complete law under current authority and exact root |
| `reprogram` | Replace protocol and complete state; preserve law |
| `add-object` | Locally create a reviewed object, then register custody |

```sh
STATE="$HOME/claude_state/delvetalk-clerk"
python3 scripts/manage.py --state "$STATE" register AUTHOR_DID
python3 scripts/clerk.py --state "$STATE" snapshot counter:live > /tmp/root.json
python3 scripts/manage.py --state "$STATE" law \
  --object counter:live --principal OPERATOR_DID --intent grant-1 \
  --expected-root /tmp/root.json --allow OPERATOR_DID --allow AUTHOR_DID
```

Use actual `did:plc` identifiers. `--allow` is the entire replacement law. Enrollment and law are separate commits: inspect `status`, recover uncertainty, then revise with a fresh intent/root or explicitly unregister. Revocation changes law first; unregister separately if desired. Expected roots may be raw roots or intact matching clerk snapshots; the CLI never refreshes them. Lean checks authority before preimage.

`--law-file FILE` replaces `--allow`/`--empty-law` and accepts:

```json
{"profile":"delvetalk-scoped-law-v1","invoke":{"add":["AUTHOR_DID"]},"reprogram":["OPERATOR_DID"],"law":["OPERATOR_DID"]}
```

Missing command grants deny. Legacy arrays grant invocation and management together. Proposed grants cannot authorize their own installation. `--empty-law` removes all authority; removing every scoped `law` principal locks future law revision. **No owner recovery bypass exists.**

```sh
python3 scripts/manage.py --state "$STATE" add-object \
  --object desk:source --principal OPERATOR_DID --intent create-1 \
  --source protocols/counter/protocol.json --syntax protocol-json@1 \
  --law-file /tmp/desk-law.json
python3 scripts/clerk.py --state "$STATE" snapshot counter:live > /tmp/root.json
python3 scripts/manage.py --state "$STATE" reprogram \
  --object counter:live --principal OPERATOR_DID --intent program-1 \
  --expected-root /tmp/root.json \
  --source protocols/welcome-once/protocol.json --syntax protocol-json@1 \
  --state /tmp/welcome-state.json
```

Creation uses protocol `initial`; existing names refuse. Reprogramming requires complete state (`{"welcome":null}` for this example), never implicit reset/migration. The global `--state` selects custody; the subcommand's selects replacement data. Explicit reviewed syntax lowers the protocol; Lean validates and atomically installs protocol/state with one version increment. Source caps at 512 KiB, state at 64 KiB, and the complete request at 64 KiB before intent reservation.

## Recovery

```sh
python3 scripts/manage.py --state "$STATE" status
python3 scripts/manage.py --state "$STATE" resume --principal OPERATOR_DID --intent grant-1
```

Each `(principal,supplied intent)` binds one operation and exact inputs across management commands. Lean prefixes are `operator-law:`, `operator-reprogram:` and `operator-create:`. Success and refusal are terminal; revised inputs require fresh intent.

Journals fsync exact requests, source/state bytes, translations and pins before admission. Resume uses retained requests without rereading files or rerunning adapters. Pending recovery requires original management/clerk/translation pins and blocks upgrades; completed receipts survive source changes, revocation and unenrollment.

After create commits, custody registration precedes terminal receipt export. Resume completes this recoverable sequence; refused creates never register. Clerk then world locks serialize admission. Previously retained remote requests survive unenrollment: uncommitted attempts face current law/root, committed attempts recover historical receipts.

Exit: 0 completion; 2 Lean refusal (also argument errors); 1 custody error. Inspect JSON.

[Implementation](../scripts/manage.py), [Lean/mock-PDS tests](../conformance/test_management.py), [adversarial tests](../conformance/test_management_adversarial.py).
