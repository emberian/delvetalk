# A world of separately governed things

**Decision.** Code reuse and durable relationships are distinct. Importing an
inventory module provides functions; it does not access an existing inventory.
A scene may own a private prop. It must not duplicate a public object's state
and call that copy the public object. The same distinction applies to mailboxes,
rooms, clocks, workshops and games.

This design is the next source/host connection, not a claim that its full API is
implemented. Typed state, transactions, origin facts, retained messages,
containment and appointments already supply much of the substrate.

## Shared vocabulary

Use ordinary Bend definitions for a **relationship**, an **intention**, a
**prepared turn**, and a **completion**. These are proposed concepts, not newly
installed reserved keywords.

- A relationship names a durable identity and its role. It declares whether it
  follows that identity's governed interface or requires particular program bytes.
  Display names, imported module names and authority are separate.
- An intention retains the selected relationship, requested contribution and
  unresolved choices. It need not be executable yet.
- A prepared turn is source-produced bounded action data tied to explicit
  observations. Native binding retains exact reads and absences; it never silently
  refreshes an old intention into a different action.
- A completion comes from actual admission, with producer identity and applicable
  program/operation facts. Copying equivalent data cannot forge those facts.

Avoid universal inventory or entity schemas. Independent objects may implement
different representations behind useful typed interfaces. Source contracts check
signatures/state compatibility; they do not prove behavioral substitutability.

## Atomic collaboration

For work completed within one host, source composes a bounded transaction. A scene
can begin a choice, ask a placement relation to plan movement, ask a room to admit
it, record arrival, then complete the choice from the real result. Each step keeps
the actual caller and faces current law. Any refusal rolls back the whole turn.
The scene's temporary continuation is ordinary staged data, not a Python callback.

Existing containment already implements `plan → admit → arrive`. Two concrete
gaps need correction: `arrive` returns text while `inputFrom` accepts records;
synchronous origin records identity/command but not producing program identity.
Use explicit typed completion records and add the missing authenticated fact when
exact-code relationships require it. Do not copy a hash into input and call it
trusted provenance. Merely importing the relation's code cannot replace this join.

An external fact should normally come from a source method on its governing object.
The current `observe` returns identity/version, not arbitrary domain facts. Use
actual admitted accessors with their current version effects first. A general
read-only source call, if introduced, must have an explicit permission/effect
contract; no renderer gets unrestricted world access by calling itself a view.

## Asynchronous collaboration

Sending means sent, not completed. Source retains correlation and a pending state;
a recipient decides whether to act; an authenticated later result may complete
the original intention. Timeout, withdrawal, obsolete generations and abandonment
are authored policies. A clock supplies recorded logical-time events; a physical
driver does not decide their meaning. Receive handlers currently cannot emit
descendants: request/reply chaining therefore needs an explicit bounded causal
resource policy, not an invisible recursive relay.

Recipient program replacement exposes a present lifecycle hole: old pinned events
cannot reach source-owned decline because native delivery rejects the new program.
Add governed terminal settlement which records an explicit declined outcome under
recipient current authority, never executes the old payload against replacement
code, never rewrites old evidence and cannot race a successful consumption. This
is distinct from recalling an ordinary admitted send. Native consumption exclusion
and source-visible reasons should compose with the existing relay.

## Scenes are ordinary participants

Move scene execution into `SceneRuntime.obend` over typed condition/effect/passage
data, with an explicit imported Handler and its actual State. Parsing and data
serialization may remain at the environment boundary; effect order, short-circuit
refusal, entry visitation, navigation and menus belong to the Bend runtime.
Preserve the intended atomic rollback difference from the upstream Rust embedding.

Expose local choices, children and prepared joint actions through the same source
encounter. “Carry the repaired moth to the reading room” must operate the actual
placement relation and room. Notification uses an actual mailbox; a later action
uses an actual appointment. No scene-specific host dispatcher knows those names.

## Independent fronts

Scene-runtime extraction; relationship/completion source types; native preparation;
authenticated origin improvements; terminal event settlement; and ordinary source
composition of placement/mailbox/clock can progress separately. Their join should
exercise multiple independently governed objects and two inhabitants, including
refusal and revision. That join tests the architecture; it is not the sole product
or a critical path that displaces the other fronts.
