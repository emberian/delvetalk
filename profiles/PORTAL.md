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

## Public preview

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/portal.py /srv/delvetalk/world \
  --public-origin https://delvetalk.fg-goose.online
```

The process still binds `127.0.0.1`. A TLS proxy must preserve the configured
public `Host`; forwarded headers do not establish an origin. HTTPS origin checks
apply directly. Cross-site top-level navigation to `/` is allowed so shared
links open normally; cross-site API requests and frames are refused.

Public mode exposes assets, the object catalogue, captured cards, exact source,
state, law and history, plus token interpretation and request export. It cannot
configure a principal, local actions, paid interpretation or a custody directory.
Execution, source uploads, authoring, compiler jobs/status and repository custody
routes are unavailable. Existing local draft aliases are never read.

Public requests write no files. Cards and export drafts use a shared in-memory
cache capped at **256 entries and 8 MiB**, with a **15-minute maximum lifetime**.
Pressure or restart may expire aliases earlier. An expired reference refuses;
read the object again to obtain a fresh view. Copy `wireJson` to keep exact
request material: public previews retain neither principal nor submission intent,
and their aliases cannot recover an uncertain admission. The API distinguishes
`public-preview`/`custody.kind=ephemeral` from local durable custody.

Serve only a world whose source, law and admission history are intended to be
public. A read-only filesystem mount and service resource limits complement the
portal's application bounds. [Public HTTP tests](../conformance/test_portal_public.py)
exercise origin checks, route isolation, disk invariance, expiry and both cache bounds.

## Authenticated studios

Add `--agent-state /srv/delvetalk/agents` to mount the operational Markdown guide
and account API at `/AGENTS.md`. This is separate durable custody. Verified bearer
credentials select each account's private heap; shared calls still face current
object law. Anonymous preview requests never receive an account principal.

`--agent-anthropic` additionally enables explicit authenticated interpretation
requests using `ANTHROPIC_API_KEY` from the process environment. The key is never
world data. Each account and realm retains bounded provider jobs separately;
reading or refreshing a document makes no provider call. Repeating the same job
recovers its retained result, including an uncertain outcome, instead of spending
again. Source owns the prompt and validates proposals; model output cannot admit
an action. Literal forms remain available without a provider.

`POST /AGENTS.md/turn` with `{operation:"interpret",card,text,realm?}` addresses
one captured encounter. Captured child navigation uses
`GET /AGENTS.md/world?realm=private&childCard=CARD&childKey=KEY`, so references
remain attached to the authored parent rather than becoming authority by copy.
The guide and responses supply the remaining links and exact submission forms.

**Delve supplies repository identity and publication context; Lean supplies
admission; the portal supplies a local view.** [Continuation export](CONTINUATION.md) and a [compiler queue](COMPILER-QUEUE.md)
are available alongside the integrated [retained authoring flow](AUTHORING.md).
Factory drafts preview exact required absences; committed receipts provide child
links and creation roots. Generic workspaces choose their own title and entry object.
When present, the workspace namespace qualifies copied object references; legacy
worlds do not acquire a fabricated global identity. Public synchronization and
unattended operation remain [work](../TRACKING.md).

[Implementation](../scripts/portal.py) · [composition tests](../conformance/test_portal.py)

[Repository handoff](PORTAL-BRIDGE.md) exports saved drafts and reconciles trusted local clerk receipts; it publishes nothing.

## Authored panels and preview language

Cards expose the selected `panel` and up to eight declared `viewPanels`, with
`main` always available as the overview. Panel IDs and labels are data; they do
not select remote URLs, confer identity, or change the captured root. Invalid
panel declarations leave overview inspection available with a notice. A missing
pure projection cannot become an active panel. The browser retains selection in
`?object=…&panel=…`, including refresh and back/forward navigation. Navigating
while a local outcome is uncertain retains that exact draft; sending blocks
navigation until its result arrives.

The shelf uses an explicit protocol name when available and keeps the exact
object ID visible. A visited overview may supply its evaluated title. Listing
the world never evaluates every object's view or infers participant names from
DIDs. The workspace's existing default object remains its selected entrance.

Public forms say **Preview** and offer a plain summary to copy. Portal-only
tokens and the disabled local send button are hidden; exact JSON remains an
optional inspection/export format. A summary is explicitly unsent and is not a
town reply or executable spell. No publication link or identity is inferred.
Public mode retains all existing origin, cache, filesystem and authority limits.

## Captured source documents

Object capture uses a bounded native read of the owner, then reads its declared
observations while checking the original owner reference. An intervening owner
change refuses capture. Native full-root/reference pairs share one committed
snapshot; presentation retains full roots while preparation uses compact native
references. Preparing an existing card never refreshes its observations. Town
follow-up custody retains these pairs before allocating cards, so recovery keeps
the original response even after later admissions.

An optional source `Document` is retained with its raw typed result. The generic
projection preserves text, sequences, quotes, fields, source excerpts, results,
references and continuation descriptions. An offer receives an action binding
only when its object, token and entry match an actual captured source invitation.
A reference receives a child binding only when its complete descriptor matches
the declared child catalogue. Other nodes stay inert; source meaning/revision
metadata confers no authority. Town uses the source-authored prose fallback.

Optional `interpretation` metadata names the source request and preparation
exports. Retained reads recheck that declaration against the typed result;
selected exports are compiled and executed by the native helper. Metadata alone
makes no model call and admits no turn.
