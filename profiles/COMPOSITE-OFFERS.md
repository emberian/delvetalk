# Captured composite offers

A post can offer one atomic action spanning several objects. The operator captures
an exact plan; a participant supplies only its declared fields, in literal spell
syntax or ordinary speech retained with an operator interpretation. Lean admits
the existing transaction under that participant's current grants. The offer
confers no authority and installs no evaluator.

For a real source-authored garden door, capture this plan with
`CardBook.capture_composite(offer, alias='garden-crossing')`:

```python
{
    'format': 'delvetalk-composite-offer-v1',
    'title': 'The garden crossing',
    'label': 'Whisper to the door and cross',
    'command': 'cross',
    'reads': {'door': exact_door_root, 'commons': exact_commons_root},
    'calls': [
        {'object': 'door', 'command': 'cross', 'input': {'word': None}},
        {'object': 'commons', 'command': 'move', 'inputFrom': 0},
    ],
    'fields': [{'name': 'word', 'label': 'Word', 'type': 'string',
                'required': True, 'minLength': 1, 'maxLength': 64,
                'example': 'please'}],
    'bindings': [{'field': 'word', 'call': 0, 'input': 'word'}],
}
```

The captured post carries the reply:

```text
delvetalk garden-crossing cross
word: please
```

The `command` is an authored stable selector for the combined action; it does
not resolve or invoke a method by itself. `a1` remains accepted for compatibility
with typed JSON replies. Capturing/binding a composite card uses the existing
immutable CardBook publication verification and Clerk receiving path. No parent
post or plan field supplied by the resident replaces the captured plan.

## Plan contract

The shape above is exact. There are 1–8 existing-object reads and 1–8 invoke calls.
Each read retains the complete root (`law`, `protocol`, `state`, `version`),
including additional read-only guards. Every target has a read. Calls permit
only fixed `object`, `command` and either literal record `input` or an
`inputFrom` pointing to an earlier call. Reprogramming, allocation absence
reads, object-as-caller delegation and foreign resolution are not offered here.

Fields reuse the existing required string/nat/bool/enum schemas, examples and
bounds. At most 32 explicit bindings substitute values into top-level literal
input keys. Every destination must already contain an explicit null placeholder;
a destination is written once. Every declared field must be consumed. One field
may feed several calls only through several explicit bindings. Fields cannot
select calls, targets, reads, commands, principal, intent or `inputFrom`.
Examples are copyable samples, not supplied defaults.

These bounds govern offer construction and presentation. Semantic admission
continues to belong to each receiving command. `inputFrom` conveys the earlier
result and host-authenticated transaction origin, never authority. The source
door and commons both check the global caller; commons can require this exact
immediately preceding door identity/command. The registry's gate wiring trusts
that identity's current program.

Exact known reads are never refreshed by resolution. Stale refusal requires a
newly captured offer and a new reply. An uncertain original reply retains its
identity and is retried exactly through Clerk/Town custody. Card aliases cannot
be rebound to a different plan. Old adoption cards retain their historical
format and bytes.

## Ordinary speech

An operator can interpret “Please let me through the garden door” by building
`composite_offers.wire(captured['offer'], {'word': 'please'})` and supplying it to
the existing manual-intake `act` decision. This preserves the original prose,
operator basis and exact meaning separately. The operator selects the retained
plan; residents do not edit its wire representation. Manual interpretation is
an operator attestation, not cryptographic proof that the prose encoded the
transaction or a permission grant.

## Receiving evidence

`conformance/test_composite_offers.py` uses the shared actual Objective Bend
source-transition gate and the actual compiled Lean host, with simulated
GET-only authenticated post records. It checks atomic crossing, stale door or
commons reads, current revocation, rollback after the second call fails,
restarted lost-response recovery, alias/source collisions, field injection and
manual speech. It establishes this local receiving route, not live public
posting, unattended receiving, federation or delivery.
