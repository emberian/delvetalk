# Pure Objective Bend view projection

`scene/projection.py` executes an installed view program through the existing
Lean host evaluator and materializer. It never calls a protocol action on the
live object or changes a world file. A renderer receives escaped data; an action
selection prepares an ordinary request for subsequent Lean admission.

## Installed program and result

A protocol may contain this opt-in field, which travels with its exact root:

```json
{"viewProgram":{"profile":"delvetalk-bend-view-v1","term":["lam",["lam",["record",[]]]]}}
```

That illustrative term returns an empty record and is rejected by the view
schema. Working complete protocols are [sign-v1](../scene/projections/sign-v1.json)
and [sign-v2](../scene/projections/sign-v2.json). The program contract is:

```text
program(committedState, selectedPanel) ->
  {title: String, prose: String,
   actions: {actionId: {text: String, command: String, input: Record}, ...}}
```

State enters as the whole committed state record; the panel is a String chosen
locally, defaulting to `main`. The boundary supports Nat, Bool, String and nested
records. Null, arrays, negative or fractional numbers are not silently coerced:
they refuse. Scene profiles with tagged representations can remain within this
boundary; a different data encoding needs an explicit profile.

The result has exactly the three displayed fields. `actions` contains at most
64 entries; each entry names an existing command and contains only text, command
and input. It cannot supply an object, principal, expected root or management
operation. A returned action is descriptive data, not evidence of permission.

This initial profile accepts core terms and checks the result dynamically. It
does not claim a typed surface compiler. Host installation preserves the program
as protocol metadata; view validity is checked when projected, not established
by accepting arbitrary metadata during installation. A malformed view may be
installed by an authorized programmer but fails closed when rendered. Future
checked package artifacts can strengthen this boundary without introducing a
second evaluator.

## API

```python
view = projection.project(committed_root, "workshop-sign", panel="main")
html = projection.html_view(view)
request = projection.request(view, "light", "bob", "bob-light-1")
```

The view envelope has `mode: "projection"`, object identity, a deep copy of the
exact root, selected panel, the actual installed source program, program digest,
receiving executable digest and materialized `data`. `request` retains that
same object/root and action input; it takes principal and intent separately.
Current-law and exact-preimage admission happen only when the request is sent.
Changing panels creates another presentation of the same snapshot, not another
object, session or authority grant.

The static HTML renderer escapes title, prose, action labels, object identity
and displayed source. Its content-security policy prohibits scripts, remote
resources and form submission. It does not auto-invoke actions. The shared room
adapter can expose this profile alongside source-bound Spween views; see
[ROOM](../scene/ROOM.md).

## Actual receiving path

The adapter constructs an isolated in-memory Lean world with a single synthetic
command whose result is the Bend application to state and panel. It has no
writes or outbox entries. This is an invocation of the existing `WorldCore`
materializer, not an invocation against the participant's live database; its
synthetic root/receipt are discarded. No `world.exchange`, file lock, source
compiler, evaluator written in Python, or Lean build runs during projection.

The materializer shares a 10,000-tick budget across argument conversion,
reduction and every selected result field. Effects, stuck terms, exhausted
computations, closures and nonmaterializable results refuse. The adapter rejects
inputs above 64 KiB, enforces a ten-second process deadline and rejects captured
outputs above 1 MiB. The output limit is checked after capture, and reduction
fuel does not bound arbitrary-precision arithmetic or memory use: this remains
a local trusted workbench, not a public untrusted-code sandbox.

The actual prebuilt `delvetalk-world` executable is required; there is no build
fallback. Its SHA256 is checked before and after projection and retained in the
view. The program hash describes the supplied JSON encoding, not semantic
equivalence. Neither hash grants authority or proves compiler refinement.

## Upgrade and adversarial journey

`sign-v1` reads its title and prose from committed state and selects a different
title for the details panel. Its `light` action changes the shared message.
`sign-v2` changes the main-panel prose while preserving the details panel's
state projection. Reprogramming the sign therefore changes actual Bend view
behavior, rather than a renderer-specific label.

The focused suite creates a sign with separate invocation/programming rights,
refuses a player's attempted upgrade, admits the programmer's exact-root
replacement with explicit preserved state, projects the changed view, and has
another participant invoke its action. Historical upgrade retries retain their
receipt; old view actions refuse as stale. The source-desk bootstrap can adopt
the same v2 protocol through `protocol-json@1`, preserving the same receiving
boundary.

```sh
python3 conformance/test_projection.py
```

The suite also checks independent panels without file mutation, missing command
and extra identity-field refusals, untrusted markup escaping, effect/function
results, unsupported state encodings and divergence. These are scoped executable
checks against the built local Lean host; no external network operations occur.
