# The Room Between

A small exhibition jointly authored by two artists and a curator. Each artist
offers one piece with a title, note, display time, fragility flag and lighting
choice. The curator sets a caption and viewing order. Both artists must approve
that exact arrangement before the curator can open the room.

The installed pure Bend view offers the actions appropriate to the observed
phase. Its `north` and `south` panels show the artists' notes. Both artists can
submit first and either can approve first. Actions remain subject to current
law and their captured exact root; a visible action is not a grant.

## Use

With the existing `delvetalk-world` and `delvetalk-transactions` binaries:

```sh
python3 protocols/shared-exhibition/run.py /PRIVATE/new-exhibition
python3 scripts/portal.py /PRIVATE/new-exhibition --allow-local-actions --principal north
python3 conformance/test_exhibition_journey.py
```

The runner performs a complete local journey using generic fixture content,
then leaves the opened room and its continuation available for inspection. Use
a fresh destination. To supply your own text, pass `--content /PRIVATE/content.json`
with `north`, `south`, and `arrangement` objects matching the forms below. Its
private `events/`, portal custody, compiler queue, world and continuation remain
in that destination. No network, model API, external publication or build runs.

To inspect the resulting room, open the portal. Its final view has no mutations
left to offer. Use “Look inside” to inspect its source, state, current law and
admitted history. For an interactive new session, use the same desk and adoption
sequence in [run.py](run.py), stopping before its participant turns.

## Source and authority

- [generate.py](generate.py) is readable source authoring code. Running it writes
  the byte-stable [protocol.json](protocol.json), [scenarios.json](scenarios.json)
  and [migration.json](migration.json).
- The `protocol-json@1` source desk receives exact protocol and scenario bytes.
  The local compiler queue checks them without installing. Only the curator
  has the target's programming grant and the desk's adoption grant.
- The named host profile is `transactions`; pure projections use the prebuilt
  world host. Lean checks protocol transitions, laws, exact roots and adoption.
  The runner and portal only construct requests and retain custody.
- Artists `north` and `south` may only offer and approve their own slots.
  `curator` may arrange and open, `builder` submits source, `compiler` records
  checks, and `operator` manages current law. Local names are caller assertions.
- The empty migration is for a fresh exhibition. Adopting it over an inhabited
  room would replace the complete state; it does not preserve existing pieces.

The offered forms are:

| Command | Fields |
| --- | --- |
| `offer-north`, `offer-south` | `title`: nonempty string ≤120 scalars; `note`: nonempty string ≤320; `minutes`: Nat 1–30; `fragile`: Bool; `light`: `dim` or `bright` |
| `arrange` | `caption`: nonempty string ≤400; `first`: `north` or `south` |
| `consent-north`, `consent-south`, `open` | No fields |

Copied text inputs use `do CARD ACTION` followed by one JSON object. All four
field types are carried through the same saved card, interpretation, draft and
explicit execution path. The tests use actual copied tokens, including a
Boolean supplied where a Nat is required, and require clarification without
an admission for that malformed token.

Protocol guards independently enforce nonempty text, Nat range, Bool type,
enum membership, principal and lifecycle. String upper bounds and rejection of
extra fields belong to offered-form validation, not the protocol's raw invoke
semantics. Piece descriptions are claims, not certified physical properties.

## Coordination and evidence

Contributions and arrangements are one-shot. Neither artist can overwrite the
other's piece; nobody can change the arrangement after either consent. There
is no revision/cancellation flow in this small version. Law management and
reprogramming retain their normal authority and are not vetoed by these
invocation guards.

[scenarios.json](scenarios.json) contains two scenario groups and 27 turns:
complete agreement; role impersonation; empty and malformed values; Nat
bounds; duplicate offerings; stale reads; opening without both consents;
rearrangement after consent; and duplicate opening. The complete success case
asserts the exact final state, result and empty outbox.

[The composition test](../../conformance/test_exhibition_journey.py) exercises
source submission, queued compilation, denied compiler adoption, authorized
curator adoption, installed Bend projection, typed token preparation, denied
visitor admission, stale participant reads, exact receipt recovery, both
consents, opening, panel reads, and source-bound continuation export and replay.
Source authoring parity is checked separately. Participant content and saved
requests belong in private worlds, not this reusable package.

The continuation proves replay of its exact local artifacts and admissions;
it does not establish authenticated remote participants or public deployment.
