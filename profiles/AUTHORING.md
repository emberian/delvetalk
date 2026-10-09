# Source authoring

Authoring uses the ordinary source-owned encounter. Inspect a Writing object,
supply source and examples through its offered submission, then inspect the
Candidate. Its `requestCheck` records the requested generation and requester;
`prepareCompilerWork` offers exact physical compiler work to the service/queue.
Compiler custody retains roots, pins, artifacts and reports. A successful report
grants no installation right.

Release/adoption uses the Candidate’s source preparation and atomically replaces
the target under current law and exact captured roots. Migration is explicit;
no adapter guesses state. Recover an uncertain turn from its saved original
attempt before preparing another one. See [source desks](DESK.md),
[preparation](PREPARATION.md), and [compiler queue](COMPILER-QUEUE.md).

The portal text editor offers keep, open and copy. `/api/authoring/source` provides
physical exact UTF-8 custody only:

| Relation | Fields |
| --- | --- |
| POST `/api/authoring/source` | `{text,kind?}`; kind `source` or `scenarios`; returns `{source,bytes,ref}` |
| GET `/api/authoring/source` | `source=SHA&kind=source`; returns exact text and ref |

Source is bounded to 512 KiB and scenarios to 1 MiB. Upload uses the portal’s
same-origin/CSRF gates and a bounded envelope. Keeping bytes grants no authority,
submits no proposal and starts no compiler. Source hashes identify bytes rather
than authors. Ordinary encounter execution requires the configured authenticated
caller; local `--principal` assertions are not Delve logins.

Source compiler invitations and receiving changes require a matching qualified
native/source/consumer closure. [BACKLOG](../BACKLOG.md) owns that remaining work.
