# Retained authoring

The portal’s source desk turns retained UTF-8 source into an explicitly reviewed
replacement program. It uses the existing [source desk](DESK.md),
[compiler queue](COMPILER-QUEUE.md), and Lean admission. A successful compiler
report grants no permission to install it.

1. Upload source and scenarios, or reuse their full SHA-256 references. Bytes are
   immutable in the workspace artifact store: source ≤512 KiB, scenarios ≤1 MiB.
   Requests contain exact references and a pinned syntax adapter, not source text.
2. Prepare **submit**, naming an existing candidate desk, target, registered syntax,
   and explicit complete migration state. Send captures the desk root and retains
   one intent. No candidate object or grants are created implicitly.
3. Prepare **compile**, then enqueue and explicitly Run. Each draft owns one durable
   queue/job; it captures the pending candidate root and runs for at most 30 seconds.
   Status, compiler diagnostics, artifacts and receipts survive restart. Running
   again reuses the same job; after three interrupted attempts an explicit Run
   enables another bounded attempt. It never installs the result.
4. Prepare **adopt**. Review its exact candidate and target roots before sending.
   The existing atomic transaction releases the candidate and reprograms the target
   under their current laws. A changed target refuses; no migration is guessed.

Read-only sessions may retain source, prepare drafts and inspect jobs. Every
execution requires `--principal NAME --allow-local-actions`; that local assertion
is not a Delve login. Compiler and adopter authority are checked independently by
Lean. Switch explicitly configured local sessions when the grants require distinct
principals. A draft remains bound to its preparing principal.

## HTTP relations

POST uses the portal’s same-origin/CSRF gates. Normal bodies are ≤64 KiB; only
source upload accepts a ≤7 MiB JSON envelope, followed by the tighter UTF-8 limit.

| Relation | Fields |
|---|---|
| POST `/api/authoring/source` | `{text,kind?}`; kind `source` or `scenarios`; returns `{source,bytes,ref}` |
| GET `/api/authoring/source` | `source=SHA&kind=source`; returns exact text and ref |
| POST `/api/authoring/prepare` | submit: `{operation,candidate,target,syntax,source,scenarios,migrationJson}` |
| Same | compile: `{operation,candidate}`; adopt: `{operation,candidate,target}` |
| GET `/api/authoring/draft` | `draft=SHA`; saved exact request/wire JSON and execution eligibility |
| POST `/api/authoring/execute` | `{draft}`; submit/adopt admission, or compile enqueue |
| POST `/api/authoring/run` | `{draft}`; explicitly run the retained compile job |
| GET `/api/authoring/status` | `draft=SHA`; phase, job, receipt, diagnostics, errors, artifact, exactJson |

`?work=SHA` restores a saved draft in the browser. Retrying an uncertain admission
recovers the original retained request/receipt before checking changed runtime
pins. Preparation creates a new intent; use the saved draft to recover an old one.
The immutable draft is content addressed; results live separately. Exact JSON
strings preserve integers beyond browser number precision. Source hashes and job
IDs identify bytes and custody, never authority. No remote publication occurs.
