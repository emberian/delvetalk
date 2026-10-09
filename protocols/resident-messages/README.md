# A bell that opens a listening door

`Bell.obend`, `Door.obend` and `Lantern.obend` are independent Objective Bend
residents. The bell prepares a chord using its chosen recipient's captured
program; the door opens and can emit toward its own observed lantern. The
public forms ask for a chord and voice count or confirmation of a connection.
Their source preparations supply exact program pins from retained observations.

[package.py](package.py) supplies exact `Abi`, `Preparation`, `Encounter` and
`Emissions` modules plus the resident source to `objective-bend-object`.
`configured` constructors give Bell its recipient, Door its source and recipient,
and Lantern its source, allowing independently named courtyard instances.
Python assembles bytes and typed arguments; Bend owns their behavior.

The receiving profile is `compiled`, with `delvetalk-source-transition` and
explicit `messages: {emit, receive}` capabilities. State lives in `model`
DataWire. Emissions are an ordered `nil`/`cons` collection of addressed
`{to, command, recipientProgram, payload}` descriptors; payload uses
`Preparation.Value`. The native ceiling is sixteen emissions per call. Bell
also checks that bound before constructing the collection. Empty means no
emission and needs no messaging registry.

Trusted custody initializes messaging before creating objects. Native admission
captures the source's exact preimage once per emission call and retains the
principal, intent, call index and descriptor index. It validates current target
programs and receive capability, and commits events atomically with source state
and the receipt. Events stay separate from external outboxes.

Delivery supplies the retained event reference, recipient, current root and relay
principal. Native admission supplies a fourth `CausalEvent` argument containing
`id`, `source`, `sourceProgram`, `originatingPrincipal`, `root`, `parent`, `depth`
and `rootPrincipal`. The immediate emitter, original player and current relay
remain distinct. Direct invocation cannot manufacture those receiving facts.
A receiving turn can emit descendants under the same retained causal root.
Native depth, event, work and byte ceilings bound that continuation.

Each delivery faces the recipient's current law and exact program. Refusal
leaves the event pending; an accepted no-op can decline it. Changes to the source
after emission cannot erase admitted history. Exact retry recovers the original
receipt before rechecking authority or roots; a fresh attempt cannot consume the
event again. Batch failure rolls back all source and message changes.

Run `python3 -m unittest conformance.test_resident_messages -v` against a matching
native snapshot. Tests exercise source-desk adoption, observed preparations,
namespaced constructors, three-resident reactions, stale observations, authority,
capacity and exact retry. `Loop.obend` is a deliberately cyclic source fixture
for native causal-ceiling tests. Exported worlds remain separate custody branches;
copying one does not establish global exactly-once execution.
