# Portal

**One saved action catalogue serves buttons, copied tokens and language proposals.**
The browser adds no evaluator. Existing Lean admission decides every submitted action.

```sh
python3 scripts/bootstrap.py run /tmp/cafe --profile compiled
python3 scripts/portal.py /tmp/cafe
# Explicit local interaction:
python3 scripts/portal.py /tmp/cafe --principal moss --allow-local-actions
# Optional API-funded interpretation: additionally --anthropic; key from environment.
```

Open `http://127.0.0.1:8765`. Inspect source, state, law and history behind
“Look inside.” Exact JSON strings preserve arbitrary-precision numbers.

## Interaction

1. Read an object. A short card reference retains its exact view and runtime.
2. Select an [offered action](AFFORDANCES.md), paste `do CARD a1`, or request an
   [interpretation](INTERPRET.md). Prepare creates a durable draft, not an admission.
3. Send explicitly. Lean checks the captured root and current law.
4. Retry an uncertain **draft**, preserving its original intent. `?draft=ID`
   survives reload. A fresh preparation creates a different intent.

References are random aliases, not permissions or hash prefixes. Normal cards
omit roots and hashes. Requests retain both. Draft exports omit principal and
intent; they are request material, not authenticated Delve messages.

## Interface

| Route | Input/result |
|---|---|
| GET `/api/world` | Objects, mode, CSRF token |
| GET `/api/object?object=ID` | New saved card; optional `panel` |
| GET `/api/card?card=ID` | Original card |
| GET `/api/detail?card=ID` | Exact captured source/root and history prefix |
| GET `/api/draft?draft=ID` | Retained draft/outcome |
| POST `/api/prepare` | `{card,action,fields?}` |
| POST `/api/interpret` | `{card,text}` |
| POST `/api/execute` | `{draft}` |
| POST `/api/repository/prepare` | `{draft}`; exact offline repository record |

POST requires JSON and `X-Delvetalk-CSRF`. Host/origin checks, no CORS, text-only
rendering and a restrictive CSP protect this local interface. They do not
establish public multi-user authentication.

Custody defaults to `WORLD/portal-custody`; `--state` overrides it. Each category
is capped at 4,096 records; nothing is silently evicted. Runtime changes refuse
pending execution; existing receipts remain recoverable. Host subprocesses are
bounded to 20 seconds. Resource bounds are not an OS sandbox.

**Delve supplies repository identity and publication context; Lean supplies
admission; the portal supplies a local view.** [Continuation export](CONTINUATION.md) and a [compiler queue](COMPILER-QUEUE.md)
are available separately. Public synchronization, unattended operation and
factory allocation cards remain [work](../TRACKING.md).

[Implementation](../scripts/portal.py) · [composition tests](../conformance/test_portal.py)

[Repository handoff](PORTAL-BRIDGE.md) exports saved drafts and reconciles trusted local clerk receipts; it publishes nothing.
