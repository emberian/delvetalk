# Account heaps

The authentication service resolves a credential to one stable `{accountId,did}`.
`HeapManager` accepts that trusted identity; HTTP request data cannot choose an
account, filesystem path or principal. A persisted private HMAC key maps account
IDs to separate SQLite native worlds. Each starts with its own message lineage,
source-authored `notebook`, and ordinary source `source-desk`. Neither credential
rotation nor process restart replaces that heap.
The manager also binds its custody root to the exact shared world namespace,
database path and receiving profile; restarting against another realm refuses.

The notebook's source owns its record operation and encounter. REPL input is an
explicit sealed module table, entry and DataWire arguments. Native parsing,
checking and evaluation produce a result; a normal exact-root notebook admission
records the source and result. This does not install behavior. An exact retry
reuses the retained evaluation and native receipt. Changed source under the same
intent refuses. Source Desk submission, bounded checking and atomic adoption
provide the separate programming path. All operations use the account DID and
current law, including deliberate notebook or management lockout.

Authored cards, questions and drafts use the common Portal/native capture and
preparation machinery. Custody is separate per account and realm. An account can
recover its own saved reading and receipt; another account's aliases do not
resolve. Catalogue responses include roots only for the selected realm.

The shared realm uses its configured receiving profile and the authenticated
DID. Reading or evaluating a private object never publishes it. An explicit
shared create can copy a protocol and initial state into the returned
`sharedCreatePrefix` (`agent:<accountId>:`). Existing shared objects still require
their current invoke/reprogram/law grants. Source factories retain their own
native allocation rules. There is no cross-realm atomic operation or implicit
transfer of authority.

One manager owns its custody root and serializes native work. Defaults bound
accounts to 64, resident handles to 4, pending calls to 4, requests to 256 KiB,
source input to 64 KiB/16 modules, and admitted journal frames to 512 KiB.
Each account has 1,024 journal entries/16 MiB of journal payload, a separate
1,024-operation/16 MiB request ledger, and 1,024-entry/16 MiB encounter custody.
Native turn deadlines and separate CPU/output/memory limits bound pure evaluation.
Compiler work is serialized and uses the existing bounded Source Desk worker.
Compiler artifact custody has a separate 256 MiB limit, reserving exact missing
dependency sizes before writing; it includes the retained native binaries.
Checkpointing is operator/internal; no unauthenticated export endpoint exists.
Physical custody limits can refuse work; they confer no object authority.

The notebook uses the common source-owned conversation/document model. Optional
interpretation is explicit activity: the captured source selects its request and
preparation exports, the native evaluator constructs the provider job, and the
native preparer validates the opaque reply against that capture. The service
returns an ordinary saved draft for explicit execution. It never treats a model
reply as admission. Copied action tokens bypass the provider. Original text,
source job/envelope, provider receipt and draft remain private to the account and
realm; repeating the same text against the same card recovers the same saved
contribution. An uncertain provider attempt is retained and never spent again.
Reading or rendering a document makes no provider call.

On Linux each resident has a provisional 2 GiB virtual-address limit, distinct
from its actual resident memory and the deployment's aggregate memory limit.
The old receiver needs more than 1 GiB virtual space for its initial thread stack;
new deployment binaries require their own qualification. Other platforms expose
`residentMemoryBytes: null`; an explicitly requested unsupported address limit
refuses instead of pretending to enforce it.
