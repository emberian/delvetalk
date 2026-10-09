# Where we are, and what we carry

These ordinary Objective Bend programs add placement and consented possession to
one local domain. They complement PlaceIndex: exhibiting a reference never moves
or gives the referenced thing.

The relation object is the **one authoritative record** of this domain's members.
A resident has one room. A portable thing is either held by a principal or directly
in one room; its effective location while carried is its holder's resident room.
Rooms contain no second inventory. They are independently programmable admission
policies. Their capacity counts resident bodies and directly placed things;
carried things do not consume another place. There are no nested containers.

Use [package.json](package.json) for the relation and
[room.package.json](room.package.json) for each room, through the existing sealed
source/desk route with `objective-bend-spell@3`. The checked binding module is last.
The initial source names the relation `habitat` and its room registrar `curator`.
Choose those identities before sealing, or edit those explicit source constants.
Room policy is `{open,capacity}` and can be revised under each room's own law.

Enrollment is a deliberate current-law permission: observe the entity, then invoke
`habitat.enroll` using the observation's `inputFrom` slot. It registers one portable
entity held by the enrolling caller. Observation proves existence, **not ownership**.
Only grant enrollment to participants authorized to establish these domain claims.
The source refuses duplicate identifiers and bounds the real recursive list at 32.
Use `act {action:"inhabit",object:BODY,to:""}` to select one resident body per caller;
only the named registrar may use `action:"room"` to designate an admission object.
Initial residents have no room until admission succeeds.

With exact current roots for `habitat` and `garden`, moving a resident or dropping
a carried thing uses one transaction:

```json
[
  {"object":"habitat","command":"plan","input":{"object":"alice-body","to":"garden"}},
  {"object":"garden","command":"admit","inputFrom":0},
  {"object":"habitat","command":"arrive","inputFrom":1}
]
```

`plan` computes occupancy from the authoritative relation. The room authenticates
its immediate producer and applies capacity, source policy and current law.
`arrive` authenticates that room and rechecks the actor, original relation and
occupancy before changing the sole placement. Omitting a leg leaves no partial
placement; a later failure rolls back every submitted call. Standalone plan/admit
may advance versions but change no relation. A plan cannot be copied into a new
call as an admission credential. All invocations retain the same caller and each
checks its own current law; provenance delegates no authority.

To drop a thing, use its identifier instead of the body; destination must be the
holder's current room. Other actions invoke `habitat.act`:

- `acquire`: the owner picks up their dropped thing when together.
- `offer`, with `to` naming a resident principal: the current owner/holder consents.
- `accept`: the recipient takes ownership and custody while together.
- `cancel`: the owner withdraws an outstanding offer.

Every action supplies `{action,object,to}`; unused `to` is empty. An accepted gift
clears the offer and old placement. Ownership here controls these source rules;
it does not rewrite the portable object's command, programming or management law.
Copying an identifier, possessing an object, and being able to operate it remain
separate. A designated room's current `admit` program is trusted for its policy;
reprogramming it changes that policy deliberately, not through a frozen-source pin.

Run `python3 conformance/test_containment.py` with the native host already built.
The journeys execute actual typed List source, two independent rooms, a portable
lamp, consent, capacity, current-law denial, forged/stale/repeated placement,
atomic rollback, room-source revision, and exact history export/replay followed
by further movement. Test decoding only inspects evidence; no Python code decides
placement. Host request budgets still apply independently of the source list bound.
